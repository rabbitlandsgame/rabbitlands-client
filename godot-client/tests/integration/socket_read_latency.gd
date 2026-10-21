extends SceneTree
## Measures how late game packets reach the game, at a chosen frame rate.
##
## Driven by socket_read_latency.py, which runs a server writing probe packets
## on a fixed cadence the way the RL server writes (one write - one TLS record -
## per flush). This drives a real EloriaNetworkClient (or another network
## script, for a before/after) and records for every probe packet when
## packet_received dispatched it and when a Main-style deferred world sync
## presented it. Frames are made slow on purpose: a frame cap (the main thread
## sleeps) and/or busy work in the physics step, in _process before the world
## sync, and after it (standing in for rendering, which headless skips).
##
## Arguments after "--": --net-script=PATH --host=H --port=N [--tls --cert=PEM]
## --fps=N --busy-physics-ms=F --busy-process-ms=F --busy-after-ms=F
## --pair-ms=F (send two frames back to back every F ms, for the Nagle test)
## --timer-ms=F (record when a Timer of that wait really fires) --out=JSON

const CMD := 250

class Busy extends Node:
	var process_ms := 0.0
	var physics_ms := 0.0
	static func spin(ms: float) -> void:
		if ms <= 0.0:
			return
		var until := Time.get_ticks_usec() + int(ms * 1000.0)
		while Time.get_ticks_usec() < until:
			pass
	func _process(_delta: float) -> void:
		spin(process_ms)
	func _physics_process(_delta: float) -> void:
		spin(physics_ms)

class Sync extends Node:
	## Main._queue_world_sync: one call_deferred per frame after a change.
	var pending := false
	var dispatched_since: Array[int] = []
	var presented: Array = []
	func mark(index: int) -> void:
		dispatched_since.append(index)
		if not pending:
			pending = true
			_flush.call_deferred()
	func _flush() -> void:
		pending = false
		var now := Time.get_ticks_usec()
		for index: int in dispatched_since:
			presented.append([index, now])
		dispatched_since.clear()

var opts := {}
var net: Node
var sync: Sync
var records: Array = []
var frame_starts := PackedInt64Array()
var physics_starts := PackedInt64Array()
var timer_fires := PackedInt64Array()
var finished := false
var deadline_usec := 0
var pair_seq := 0
var next_pair_usec := 0
var busy_after_ms := 0.0

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--"):
			var kv := arg.substr(2).split("=", true, 1)
			opts[kv[0]] = kv[1] if kv.size() > 1 else "1"
	Engine.max_fps = int(opts.get("fps", "20"))
	var script: Script = load(str(opts.get("net-script", "res://src/network/network_client.gd")))
	net = script.new()
	net.name = "ProbeNetwork"
	root.add_child(net)
	var busy := Busy.new()
	busy.process_ms = float(opts.get("busy-process-ms", "0"))
	busy.physics_ms = float(opts.get("busy-physics-ms", "0"))
	root.add_child(busy)
	sync = Sync.new()
	root.add_child(sync)
	net.packet_received.connect(_on_packet)
	process_frame.connect(func() -> void: frame_starts.append(Time.get_ticks_usec()))
	physics_frame.connect(func() -> void: physics_starts.append(Time.get_ticks_usec()))
	# Scene-tree timers run after _process and the deferred flush, where the
	# frame would be drawn; a zero timer re-armed each frame stands in for it.
	busy_after_ms = float(opts.get("busy-after-ms", "0"))
	if busy_after_ms > 0.0:
		_arm_after()
	var timer_ms := float(opts.get("timer-ms", "0"))
	if timer_ms > 0.0:
		var timer := Timer.new()
		timer.wait_time = timer_ms / 1000.0
		timer.autostart = true
		timer.timeout.connect(func() -> void: timer_fires.append(Time.get_ticks_usec()))
		root.add_child(timer)
	var error: Error = net.connect_to_server(str(opts.get("host", "127.0.0.1")),
		int(opts.get("port", "24601")), opts.has("tls"), str(opts.get("cert", "")))
	if error != OK:
		push_error("connect failed: %s" % error_string(error))
	deadline_usec = Time.get_ticks_usec() + int(float(opts.get("timeout", "40")) * 1000000.0)

func _arm_after() -> void:
	create_timer(0.0).timeout.connect(func() -> void:
		Busy.spin(busy_after_ms)
		_arm_after())

func _on_packet(command: int, payload: PackedByteArray) -> void:
	if command != CMD:
		return
	if payload.size() == 1 and payload[0] == 255:
		_finish()
		return
	records.append([payload[0], payload.decode_u32(1), payload.decode_u64(5),
		Time.get_ticks_usec()])
	sync.mark(records.size() - 1)

func _process(_delta: float) -> bool:
	var now := Time.get_ticks_usec()
	var pair_ms := float(opts.get("pair-ms", "0"))
	if pair_ms > 0.0 and net.call("_link_ready") and now >= next_pair_usec:
		next_pair_usec = now + int(pair_ms * 1000.0)
		for index in 2:
			var payload := PackedByteArray()
			payload.resize(13)
			payload.encode_u32(0, pair_seq)
			payload.encode_u8(4, index)
			payload.encode_u64(5, Time.get_ticks_usec())
			net.send_frame(EloriaProtocol.encode(CMD, payload))
		pair_seq += 1
	if now > deadline_usec:
		_finish()
	return finished

## Microseconds per call of a read entry point on an open link with nothing
## waiting: what reading costs a frame that receives nothing.
func _idle_read_usec(method: StringName) -> float:
	if not net.has_method(method):
		return -1.0
	var count := 20000
	var started := Time.get_ticks_usec()
	for _i in count:
		if method == &"_process":
			net.call(method, 0.0)
		else:
			net.call(method)
	return float(Time.get_ticks_usec() - started) / count

func _finish() -> void:
	if finished:
		return
	finished = true
	var connected: bool = net.call("_link_ready")
	var out := {"opts": opts, "records": records, "presented": sync.presented,
		"frame_starts": Array(frame_starts), "physics_starts": Array(physics_starts),
		"timer_fires": Array(timer_fires), "pairs_sent": pair_seq,
		"idle_process_usec": _idle_read_usec(&"_process") if connected else -1.0,
		"idle_late_read_usec": _idle_read_usec(&"_read_late") if connected else -1.0,
		"engine": Engine.get_version_info().string}
	var file := FileAccess.open(str(opts.get("out", "user://socket_read_latency.json")),
		FileAccess.WRITE)
	file.store_string(JSON.stringify(out))
	file.close()
	net.call("disconnect_from_server")

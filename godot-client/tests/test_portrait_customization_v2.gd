extends SceneTree
## Protocol-only checks run without importing or rendering native actor assets.
const Wire = preload("res://src/network/protocol.gd")
const Custom = preload("res://src/actors/portrait_customization.gd")
const Ranking = preload("res://src/network/leaderboard_codec.gd")
const LOOK := {"facial_hair": 5, "jaw": 70, "cheekbones": 30, "nose": 60,
	"height": 90, "build": 85, "hair_detail": 2, "face_length": 12, "eye_size": 23,
	"eye_tilt": 34, "eye_spacing": 45, "nose_width": 56, "lip_fullness": 67,
	"brow_depth": 78, "hair_length": 89, "hair_volume": 100}
const FIXTURE := "50430205461e3c5a55020c17222d38434e5964"
var failures := 0
var checks := 0

func _init() -> void:
	run.call_deferred()

func expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(label)

func run() -> void:
	var encoded := Custom.encode(LOOK, 2)
	expect(encoded.hex_encode() == FIXTURE and encoded.size() == 19, "Python/Godot PC/2 fixed fixture matches all sixteen selections")
	# PC/3 decoders return every field (V3 neutral here): compare normalised.
	expect(Custom.decode(encoded, 0) == Custom.normalized(LOOK), "PC/2 roundtrip")
	var old := Custom.normalized(LOOK)
	for field: String in Custom.EXTRA_FIELDS:
		old[field] = 50
	expect(Custom.encode(LOOK).hex_encode() == "50430105461e3c5a5502", "PC/1 byte contract stays exact")
	expect(Custom.decode(Custom.encode(LOOK), 0) == old, "PC/1 supplies neutral PC/2 defaults")
	expect(Custom.decode(Custom.encode({}), 0) == Custom.DEFAULTS, "legacy choices default all controls neutral")
	for version: int in [1, 2]:
		var valid := Custom.encode(LOOK, version)
		for data: PackedByteArray in [valid.slice(0, valid.size() - 1), valid + PackedByteArray([0]), PackedByteArray([80, 67, 3]) + valid.slice(3)]:
			expect(Custom.decode(data, 0).is_empty(), "version %d malformed length/tag rejected" % version)
		for index: int in range(3, valid.size()):
			var bad := valid.duplicate()
			bad[index] = 255
			expect(Custom.decode(bad, 0).is_empty(), "version %d field %d rejects range" % [version, index])
	expect(Custom.decode(encoded, -1).is_empty(), "negative offsets rejected")
	for field: String in Custom.EXTRA_FIELDS:
		for invalid: Variant in [-1, 101, true, "50", null, 50.5]:
			expect(not Custom.validate({field: invalid}).ok, "%s invalid value rejected" % field)
		expect(Custom.normalized({field: true})[field] == 50, "%s invalid saved type defaults neutral" % field)
	for version: int in [1, 2]:
		var packet := Wire.create_character("Portrait", "secret", LOOK.merged({"actor_type": 1, "hair": 299}), 2, version)
		var nul := packet.find(0, 3)
		expect(packet[nul + 9] == 2, "class stays at creation suffix8")
		expect(Custom.decode(packet, nul + 10) == (Custom.normalized(LOOK) if version == 2 else old), "creation trailer roundtrip version %d" % version)
		for wardrobe: bool in [false, true]:
			var body := PackedByteArray()
			body.resize(28)
			body[10] = 1
			body.append_array("Portrait".to_ascii_buffer())
			body.append_array(PackedByteArray([0, 0, 0, 255, 3, 0]))
			if wardrobe:
				body.append_array(PackedByteArray([87, 65, 1, 7, 8, 9, 0]))
			body.append_array(Custom.encode(LOOK, version))
			var actor := Wire.decode_actor(body, true)
			for field: String in Custom.FIELDS:
				expect(actor.appearance.get(field) == (Custom.normalized(LOOK) if version == 2 else old)[field], "spawn version%d wardrobe%s %s" % [version, wardrobe, field])
	var portrait := {"actor_type": 1, "appearance": LOOK.duplicate(), "equipment_visuals": {"0": 20}}
	expect(Ranking._valid_portrait(portrait), "offline ranking accepts all PC/2 fields")
	for field: String in Custom.EXTRA_FIELDS:
		var corrupt := portrait.duplicate(true)
		corrupt.appearance[field] = 101
		expect(not Ranking._valid_portrait(corrupt), "ranking bounds %s" % field)
	expect(Wire.CLIENT_CAPABILITIES.has("actor_customization_v1") and Wire.CLIENT_CAPABILITIES.has("actor_customization_v2"), "both decoding capabilities advertised")
	expect(Wire.appearance_protocol_probe() == PackedByteArray([190, 4, 0, 80, 67, 2]), "optional probe is six bytes")
	expect(Wire.decode_server(190, PackedByteArray([80, 67, 2])).get("version") == 2, "server probe reply decoded")
	expect(Wire.decode_server(190, PackedByteArray([80, 67, 1])).type == "invalid", "unknown probe reply cannot enable PC/2")
	check_sending(old)
	await check_real_connection_probe()
	print("Portrait customization v2: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func check_sending(old: Dictionary) -> void:
	# Load after the autoloads exist, as the socket tests do. Preloading the
	# Network class from the entry script creates an AppState autoload cycle.
	var recorder := GDScript.new()
	recorder.source_code = "extends \"res://src/network/network_client.gd\"\nvar sent: Array[PackedByteArray] = []\nfunc send_frame(frame: PackedByteArray, _sensitive := false) -> Error:\n\tif offline_hud_preview: return ERR_UNAVAILABLE\n\tsent.append(frame)\n\treturn OK\n"
	if recorder.reload() != OK:
		expect(false, "recording network compiles")
		return
	var network = recorder.new()
	root.add_child(network)
	network.set_process(false)
	var changed: Array[int] = []
	network.appearance_protocol_changed.connect(func(version: int) -> void: changed.append(version))
	expect(network.appearance_protocol_version() == 1, "unacknowledged peer defaults to PC/1")
	expect(network.create_character("Portrait", "secret", LOOK) == ERR_UNAVAILABLE and network.sent.is_empty(), "unsupported nonneutral PC/2 creation sends nothing")
	expect(network.appearance_error.contains("server does not support"), "creation rejection explains server compatibility")
	expect(network.create_character("Portrait", "secret", old) == OK and network.sent[-1].slice(network.sent[-1].size() - 10) == Custom.encode(old), "neutral new fields fall back to PC/1 creation")
	var entries := PackedStringArray()
	for field: String in Custom.FIELDS:
		entries.append("%s=%d" % [field, old[field]])
	expect(network.send_chat("#appearance " + " ".join(entries)) == OK, "complete neutral Apply remains compatible")
	var compatible := Wire.nul_string(network.sent[-1].slice(3))
	for field: String in Custom.EXTRA_FIELDS:
		expect(not compatible.contains(field + "="), "old server command omits unsupported neutral %s" % field)
	var count: int = network.sent.size()
	expect(network.send_chat("#appearance eye_tilt=70") == ERR_UNAVAILABLE and network.sent.size() == count, "unsupported nonneutral Apply is refused atomically")
	expect(network.send_chat("#appearance eye_tilt=101") == ERR_INVALID_DATA, "invalid Apply does not become silent compatibility fallback")
	network.set("_rx", Wire.encode(190, PackedByteArray([80, 67, 2])))
	network.call("_drain_packets")
	expect(network.appearance_protocol_version() == 2 and changed == [2], "network consumes negotiated response before UI callbacks")
	expect(network.create_character("Portrait", "secret", LOOK) == OK and network.sent[-1].slice(network.sent[-1].size() - 19).hex_encode() == FIXTURE, "negotiated Network creation sends all sixteen values")
	expect(network.send_chat("#appearance eye_tilt=70") == OK and Wire.nul_string(network.sent[-1].slice(3)).contains("eye_tilt=70"), "negotiated Apply preserves PC/2 selections")
	network.call("_reset_coordinate_session")
	expect(network.appearance_protocol_version() == 1 and changed == [2, 1], "reconnect reset cannot retain another server's support")
	network.block_for_hud_preview()
	expect(network.connect_to_server("127.0.0.1", 1, false) == ERR_UNAVAILABLE, "offline preview cannot open socket")
	expect(network.create_character("Portrait", "secret", old) == ERR_UNAVAILABLE, "offline preview cannot send creation")
	network.queue_free()

func check_real_connection_probe() -> void:
	var listener := TCPServer.new()
	if listener.listen(0, "127.0.0.1") != OK:
		expect(false, "loopback fixture starts")
		return
	var network = (load("res://src/network/network_client.gd") as GDScript).new()
	root.add_child(network)
	for attempt: int in 2:
		expect(network.connect_to_server("127.0.0.1", listener.get_local_port(), false) == OK, "loopback connection starts")
		var peer: StreamPeerTCP
		var deadline := Time.get_ticks_msec() + 5000
		var received := PackedByteArray()
		var found := false
		while Time.get_ticks_msec() < deadline and not found:
			network.call("_process", 0.0)
			if peer == null and listener.is_connection_available():
				peer = listener.take_connection()
			if peer != null:
				peer.poll()
				if peer.get_available_bytes() > 0:
					received.append_array(peer.get_data(peer.get_available_bytes())[1])
				while not received.is_empty():
					var decoded := Wire.try_decode(received)
					if decoded.status != "ok": break
					if decoded.command == 190:
						# The PC/3 probe follows the PC/2 one in the same flush.
						found = found or decoded.payload == PackedByteArray([80, 67, 2])
					received = received.slice(decoded.consumed)
			await process_frame
		expect(found and network.appearance_protocol_version() == 1, "connection %d probes before choosing PC/2" % attempt)
		if found and attempt == 0:
			peer.put_data(Wire.encode(190, PackedByteArray([80, 67, 2])))
			deadline = Time.get_ticks_msec() + 2000
			while network.appearance_protocol_version() != 2 and Time.get_ticks_msec() < deadline:
				network.call("_process", 0.0)
				await process_frame
			expect(network.appearance_protocol_version() == 2, "real peer acknowledgement selects PC/2")
		network.disconnect_from_server()
		expect(network.appearance_protocol_version() == 1, "disconnect returns to PC/1 before another connection")
		if peer != null: peer.disconnect_from_host()
	listener.stop()
	network.queue_free()
	await process_frame

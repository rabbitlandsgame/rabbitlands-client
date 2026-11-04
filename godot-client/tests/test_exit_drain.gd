extends SceneTree
## AW-01 (avatar-worker, group B9): the bounded exit drain, the native exit
## watchdog and ExteriorRegionStream._exit_tree's orphaning of a live preload.
##
## `--mode=drain` (default) checks, then quits through ExitDrain.quit with the
## watchdog armed; its exit code is the failure count:
## - `ExitDrain`: the watchdog switch resolver, the repeat-close guard, and
##   bounded waits (idle at once, idle after frames, a never-idle stage that
##   times out, a callable whose object is gone);
## - the native `RabbitLandsExitWatchdog` through ClientRuntimeController's
##   bindings when the payload has it: limits, refusals, arm / re-arm / disarm
##   and state, and that none of this verifies or loads the payload; without it
##   (switched off, not loaded, an older payload) the reason and a plain quit;
## - `ExteriorRegionStream._exit_tree` with a real preload worker and the
##   default (legacy, empty) admission token: the worker is orphaned, not left
##   on the freed node, and the reaper joins it once it finishes;
## - the plan's case: an RL head prewarm parse and a real exterior preload are
##   running, they are drained the way Main._close_client drains them, and the
##   process quits. Run it under a timeout: it must exit within 10 s of the
##   `exit_drain result=` line, without an `exit_watchdog fired` line.
## `--mode=fire` (runner only): ExitDrain.quit(42) with the watchdog armed for
##   `--exit-watchdog=<ms>` (pass e.g. 1500), then `_finalize` blocks forever,
##   a hung teardown. Expect exit code 42 and one `exit_watchdog fired` line in
##   `<user data>/logs/exit_watchdog.log` and on stderr.
## `--mode=undrained` (runner only): AW-00's hang control, an RL head prewarm of
##   both heads and an immediate ExitDrain.quit(0) without draining. Without
##   the watchdog (`--exit-watchdog=off`) this hung 5 of 5 times in AW-00; with
##   it the process must end within the watchdog timeout plus teardown.
## `--mode=main` (runner only): the real Main scene closed the way the window's
##   close button closes it, twice, while an RL head parse runs. With the B5
##   hook applied (`_close_client` through ExitDrain) the drain begins, the
##   second request is refused and Main quits by itself (exit code 0, one
##   `exit_drain result=` line, no FAIL line); before the hook a NOTE and the
##   old close. The map cache is disabled for this process so no geometry
##   maintenance runs before Main is ready. `--main-script=<path>` replaces
##   Main's script before it enters the tree (a script extending main.gd), to
##   try a hook before it lands.
## Flags (after `--`): `--runtime-dir=<payload>` (loaded first; otherwise
## NativeLibrary.startup(), as Main._ready does); `--expect-native=present`
## (the watchdog must be armable) or `absent` (it must not be);
## `--preload-map=<registry id>` (amberwood).

const ExitDrain := preload("res://src/runtime/exit_drain.gd")
const ClientRuntime := preload("res://src/runtime/client_runtime.gd")
const NativeLibrary := preload("res://src/runtime/native_library.gd")
const MapMeshExtension := preload("res://src/world/map_mesh_extension.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const REGISTRY := "res://data/maps/registry.json"

var failures := 0
var checks := 0
var _mode := "drain"
var _loaded: Dictionary = {}

## A stand-in whose `idle` turns true after `frames_left` polls.
class Countdown extends RefCounted:
	var frames_left := 0
	var polls := 0
	func _init(frames: int) -> void:
		frames_left = frames
	func idle() -> bool:
		polls += 1
		frames_left -= 1
		return frames_left < 0
	func never() -> bool:
		return false

func _initialize() -> void:
	_mode = _argument("--mode=", "drain")
	if _mode == "main":
		OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	var directory := _argument("--runtime-dir=")
	_loaded = NativeLibrary.load_verified(directory) if not directory.is_empty() else NativeLibrary.startup()

func _init() -> void:
	call_deferred("_run")

func _finalize() -> void:
	if _mode == "fire":
		print("EXIT_DRAIN_FIRE teardown blocks now")
		while true:
			OS.delay_msec(20)

static func _argument(prefix: String, fallback := "") -> String:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with(prefix):
			return argument.trim_prefix(prefix)
	return fallback

func _expect(condition: bool, message: String) -> bool:
	checks += 1
	if condition:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return condition

func _run() -> void:
	print("EXIT_DRAIN mode=%s loader=%s" % [_mode, str(_loaded.get("code", ""))])
	match _mode:
		"fire":
			ExitDrain.begin("test_fire")
			var armed := ExitDrain.quit(self, 42, "test_fire")
			print("EXIT_DRAIN_FIRE armed=%s status=%s timeout_ms=%d log=%s" % [str(armed.armed), str(armed.status),
				int(armed.timeout_msec), str(armed.log_path)])
		"main":
			await _main_close()
		"undrained":
			RLHeadLibrary.prewarm(PackedStringArray([RLHeadLibrary.head_path("male"),
				RLHeadLibrary.head_path("female")]))
			await process_frame
			print("EXIT_DRAIN_UNDRAINED warming=%s" % str(RLHeadLibrary.warming()))
			ExitDrain.begin("test_undrained")
			ExitDrain.quit(self, 0, "test_undrained")
		_:
			await _drain_mode()

## Main's real close path; see the header (`--mode=main`). Main quits.
func _main_close() -> void:
	var app := root.get_node("/root/AppState")
	app.set("authenticated", false)
	app.set("current_map", "")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	var replacement := _argument("--main-script=")
	if not replacement.is_empty():
		main.set_script(load(replacement))
	root.add_child(main)
	var began := Time.get_ticks_msec()
	while auto_accept_quit and Time.get_ticks_msec() - began < 60000:
		await process_frame
	if not _expect(not auto_accept_quit, "Main took over the close request"):
		quit(failures)
		return
	RLHeadLibrary.prewarm(PackedStringArray([RLHeadLibrary.head_path("male"), RLHeadLibrary.head_path("female")]))
	await process_frame
	print("EXIT_DRAIN main closing warming=%s" % str(RLHeadLibrary.warming()))
	root.close_requested.emit()
	if not ExitDrain.closing():
		print("NOTE: Main._close_client does not use ExitDrain yet (AW-01 hook H1 pending); the old close quits")
		return
	await process_frame
	root.close_requested.emit()
	_expect(int(ExitDrain.snapshot().repeats) == 1, "a second close request is refused while Main drains")
	# Main quits by itself after its drains; a FAIL line is the result here.

func _drain_mode() -> void:
	# As Main._ready: glTF extensions are registered on the main thread before
	# any neighbouring-region worker starts (WorldLoader refuses otherwise).
	_expect(GltfQuantization.ensure_registered() and VramTextures.ensure_registered()
		and MapMeshExtension.ensure_registered(), "the runtime glTF extensions register on the main thread")
	_resolver()
	await _waits()
	var watchdog_present := _watchdog()
	await _exterior_exit_tree()
	await _close_like_main(watchdog_present)

## ExitDrain.resolve_watchdog: precedence, spellings and limits.
func _resolver() -> void:
	var none := PackedStringArray()
	var cases := [
		["", none, "auto", ExitDrain.WATCHDOG_TIMEOUT_MSEC, "default", []],
		["off", none, "off", 0, "environment", []],
		[" OFF ", none, "off", 0, "environment", []],
		["2500", none, "auto", 2500, "environment", []],
		["auto", none, "auto", ExitDrain.WATCHDOG_TIMEOUT_MSEC, "environment", []],
		["2500", PackedStringArray(["--exit-watchdog=off"]), "off", 0, "argument", []],
		["off", PackedStringArray(["--exit-watchdog=1500"]), "auto", 1500, "argument", []],
		["2500", PackedStringArray(["--exit-watchdog=soon"]), "auto", 2500, "environment", ["argument"]],
		["99", none, "auto", ExitDrain.WATCHDOG_TIMEOUT_MSEC, "default", ["environment"]],
		["600001", none, "auto", ExitDrain.WATCHDOG_TIMEOUT_MSEC, "default", ["environment"]],
		["100", none, "auto", 100, "environment", []],
		["600000", none, "auto", 600000, "environment", []],
		["1.5", none, "auto", ExitDrain.WATCHDOG_TIMEOUT_MSEC, "default", ["environment"]],
	]
	for case: Array in cases:
		var got := ExitDrain.resolve_watchdog(str(case[0]), case[1])
		_expect(str(got.mode) == str(case[2]) and int(got.timeout_msec) == int(case[3])
			and str(got.source) == str(case[4]) and ",".join(PackedStringArray(got.invalid)) == ",".join(PackedStringArray(case[5])),
			"watchdog switch env=%s args=%s -> %s" % [str(case[0]), str(case[1]), str(got)])

## Bounded waits and the repeat guard.
func _waits() -> void:
	ExitDrain.reset_for_tests()
	_expect(not ExitDrain.closing() and ExitDrain.begin("close"), "the first close request begins the drain")
	_expect(not ExitDrain.begin("close") and ExitDrain.closing(), "a repeat request while draining is refused")
	_expect(int(ExitDrain.snapshot().repeats) == 1, "the refused repeat is counted")
	var at_once := Countdown.new(0)
	var began := Time.get_ticks_msec()
	_expect(await ExitDrain.wait_until(self, "at_once", at_once.idle, 2000), "an idle stage returns true")
	var last: Dictionary = ExitDrain.snapshot().stages[-1]
	_expect(int(last.frames) == 0 and at_once.polls == 1, "an idle stage costs no frame (%s)" % str(last))
	var later := Countdown.new(3)
	_expect(await ExitDrain.wait_until(self, "later", later.idle, 5000), "a stage idle after three frames returns true")
	last = ExitDrain.snapshot().stages[-1]
	_expect(int(last.frames) == 3 and bool(last.idle), "it served exactly three frames (%s)" % str(last))
	var stuck := Countdown.new(0)
	began = Time.get_ticks_msec()
	var finished: bool = await ExitDrain.wait_until(self, "stuck", stuck.never, 300)
	var waited := Time.get_ticks_msec() - began
	_expect(not finished and waited >= 300 and waited < 2000,
		"a never-idle stage gives up after its deadline (%d ms)" % waited)
	_expect(",".join(PackedStringArray(ExitDrain.timed_out())) == "stuck", "only the stuck stage is reported as timed out")
	var gone := Countdown.new(1000)
	var orphaned_check := gone.never
	gone = null
	_expect(await ExitDrain.wait_until(self, "gone", orphaned_check, 2000),
		"a stage whose object is gone counts as idle")
	ExitDrain.reset_for_tests()

## The native watchdog through ClientRuntimeController's bindings. Returns
## whether it can be armed in this process.
func _watchdog() -> bool:
	var args := OS.get_cmdline_user_args()
	var before: Dictionary = NativeLibrary.stats()
	var reason := ClientRuntime.exit_watchdog_unavailable_reason()
	var state := ClientRuntime.exit_watchdog_state()
	print("EXIT_DRAIN watchdog reason=%s state=%s" % [reason, str(state)])
	if not reason.is_empty():
		_expect(not args.has("--expect-native=present"), "the watchdog is available (reason %s)" % reason)
		var refused := ClientRuntime.arm_exit_watchdog(1000, 0, "", "test")
		_expect(not bool(refused.armed) and str(refused.status) == reason,
			"without the watchdog arming reports %s and does nothing" % reason)
		if str(NativeLibrary.switch_state().mode) == "off":
			_expect(reason == "native_runtime_switched_off", "the kill switch names itself")
		_expect(not ClientRuntime.disarm_exit_watchdog(), "disarm without the watchdog is false")
		_expect(NativeLibrary.stats().verifications == before.verifications and NativeLibrary.stats().loads == before.loads,
			"the watchdog bindings never verify or load the payload")
		return false
	_expect(not args.has("--expect-native=absent"), "the watchdog is unavailable as expected")
	var watchdog := ClassDB.instantiate(ClientRuntime.EXIT_WATCHDOG_CLASS) as RefCounted
	var info: Dictionary = watchdog.call("api_info")
	_expect(int(info.get("exit_watchdog_api", 0)) == 1 and int(info.min_timeout_msec) == ExitDrain.WATCHDOG_MIN_MSEC
		and int(info.max_timeout_msec) == ExitDrain.WATCHDOG_MAX_MSEC and int(info.max_exit_code) == 255,
		"api_info states the limits ExitDrain uses (%s)" % str(info))
	_expect(not bool(state.armed) and not bool(state.fired), "nothing is armed before the test arms it")
	for bad: Array in [[99, 0], [600001, 0], [1000, -1], [1000, 256]]:
		var refused := ClientRuntime.arm_exit_watchdog(int(bad[0]), int(bad[1]), "", "test")
		_expect(not bool(refused.armed) and str(refused.status) == "invalid_argument",
			"arm(%d ms, code %d) is refused as invalid_argument" % [int(bad[0]), int(bad[1])])
	_expect(not bool(ClientRuntime.exit_watchdog_state().armed), "a refused arm leaves it unarmed")
	var log_path := ExitDrain.watchdog_log_path()
	var armed := ClientRuntime.arm_exit_watchdog(60000, 7, log_path, "test_arm")
	state = ClientRuntime.exit_watchdog_state()
	_expect(bool(armed.armed) and str(armed.status) == "armed", "arm(60 s, code 7) is accepted (%s)" % str(armed))
	_expect(bool(state.armed) and bool(state.pinned) and bool(state.thread_started) and int(state.exit_code) == 7
		and int(state.timeout_msec) == 60000 and int(state.remaining_msec) > 55000
		and int(state.remaining_msec) <= 60000 and str(state.reason) == "test_arm",
		"the armed state is reported (%s)" % str(state))
	var arms := int(state.arms)
	armed = ClientRuntime.arm_exit_watchdog(120000, 9, log_path, "test_rearm")
	state = ClientRuntime.exit_watchdog_state()
	_expect(bool(armed.armed) and int(state.exit_code) == 9 and int(state.timeout_msec) == 120000
		and int(state.arms) == arms + 1 and int(state.remaining_msec) > 60000, "a re-arm replaces the deadline and code")
	_expect(ClientRuntime.disarm_exit_watchdog(), "disarm cancels the pending deadline")
	state = ClientRuntime.exit_watchdog_state()
	_expect(not bool(state.armed) and not bool(state.fired) and int(state.remaining_msec) == 0
		and int(state.disarms) >= 1, "the disarmed state is reported (%s)" % str(state))
	_expect(not ClientRuntime.disarm_exit_watchdog(), "a second disarm finds nothing pending")
	var other := ClassDB.instantiate(ClientRuntime.EXIT_WATCHDOG_CLASS) as RefCounted
	_expect(int((other.call("state") as Dictionary).arms) == int(state.arms), "the watchdog state is process-wide")
	OS.set_environment(ExitDrain.SWITCH_ENVIRONMENT, "off")
	var switched := ExitDrain.arm_watchdog(0, "test_switch")
	OS.set_environment(ExitDrain.SWITCH_ENVIRONMENT, "")
	_expect(not bool(switched.armed) and str(switched.status) == "switched_off_by_setting"
		and not bool(ClientRuntime.exit_watchdog_state().armed), "RABBITLANDS_EXIT_WATCHDOG=off leaves it unarmed")
	_expect(NativeLibrary.stats().verifications == before.verifications and NativeLibrary.stats().loads == before.loads,
		"the watchdog bindings never verify or load the payload")
	return true

## One real preload worker on a stream whose admission is the default legacy
## path (empty token). Returns the stream, or null when nothing dispatched.
func _start_preload(label: String) -> ExteriorRegionStream:
	var map_id := _argument("--preload-map=", "amberwood")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY))
	var maps: Dictionary = (parsed as Dictionary).get("maps", {}) if parsed is Dictionary else {}
	if not _expect(maps.has(map_id), "the registry has %s" % map_id):
		return null
	var stream := ExteriorRegionStream.new()
	stream.name = "ExitDrainStream_" + label
	stream.registry = {map_id: maps[map_id]}
	stream.links = [{"seamless": true, "ends": [
		{"map": "current", "position": [0, 0, 0], "frame": {"anchor": [0, 0, 0], "outward": [0, -1], "viewHalfWidth": 80}},
		{"map": map_id, "position": [0, 0, 0]}]}]
	stream.active_map = "current"
	root.add_child(stream)
	stream.update_position(Vector3(0, 0, 10))
	if not _expect(stream._thread != null, "%s: a real %s preload worker is running" % [label, map_id]):
		root.remove_child(stream)
		stream.free()
		return null
	print("EXIT_DRAIN %s preload map=%s token=%s alive=%s at_ms=%d" % [label, map_id,
		"legacy" if stream._admission_token.is_empty() else "rust", str(stream._thread.is_alive()), Time.get_ticks_msec()])
	return stream

## ExteriorRegionStream._exit_tree orphans the worker whatever the token.
func _exterior_exit_tree() -> void:
	var orphans_before := ContinentChunkStream.orphans_pending()
	var stream := _start_preload("exit_tree")
	if stream == null:
		return
	var legacy := stream._admission_token.is_empty()
	var thread := stream._thread
	root.remove_child(stream)
	_expect(stream._thread == null and ContinentChunkStream.orphans_pending() == orphans_before + 1,
		"leaving the tree orphans the %s-token worker instead of keeping it on the node"
			% ("legacy" if legacy else "rust"))
	stream.free()
	var reaped: bool = await ExitDrain.wait_until(self, "orphan_reap",
		func() -> bool: return ContinentChunkStream.reap_orphans() <= orphans_before, 60000)
	_expect(reaped and not thread.is_alive(), "the reaper joins the orphan once it finishes (%s)"
		% str(ExitDrain.snapshot().stages[-1]))
	ExitDrain.reset_for_tests()

## The plan's case: RL head prewarm + exterior preload running, drained the
## way Main._close_client does, then ExitDrain.quit.
func _close_like_main(watchdog_present: bool) -> void:
	var stream := _start_preload("close")
	RLHeadLibrary.prewarm(PackedStringArray([RLHeadLibrary.head_path("male"), RLHeadLibrary.head_path("female")]))
	_expect(RLHeadLibrary.warming(), "an RL head prewarm parse is pending")
	_expect(ExitDrain.begin("test_close"), "the close begins")
	RLHeadLibrary.cancel_warm()
	_expect(await ExitDrain.wait_until(self, "rl_head_warm", func() -> bool: return not RLHeadLibrary.warming()),
		"the RL head parse drains within the stage deadline")
	if stream != null:
		stream.clear()
		_expect(await ExitDrain.wait_until(self, "exterior_stream", stream.is_idle),
			"the exterior preload drains within the stage deadline")
	_expect(ExitDrain.timed_out().is_empty(), "no stage timed out")
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	print("EXIT_DRAIN checks=%d failures=%d quitting" % [checks, failures])
	var result := ExitDrain.quit(self, mini(failures, 255), "test_close")
	# quit() takes effect at the end of this frame; a failure here still
	# changes the exit code.
	var setting := ExitDrain.watchdog_setting()
	if watchdog_present and str(setting.mode) != "off":
		_expect(bool(result.armed) and int(result.timeout_msec) == int(setting.timeout_msec)
			and bool(ClientRuntime.exit_watchdog_state().armed),
			"ExitDrain.quit arms the watchdog for this process's setting (%s)" % str(result))
	else:
		_expect(not bool(result.armed), "ExitDrain.quit quits without a watchdog (%s)" % str(result.status))
	if failures > 0:
		# The watchdog keeps the code it was armed with; re-arm it (the latest
		# arm wins) so a hung teardown still exits with the failure count.
		ExitDrain.arm_watchdog(mini(failures, 255), "test_close")
		quit(mini(failures, 255))

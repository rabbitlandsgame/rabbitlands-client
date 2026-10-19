extends SceneTree
## The arrival loading screen on the real Landfall chunks, driven through
## main.gd the way a login, a far teleport and a respawn arrive. No live
## server: AppState is set as the packets would set it.
##
## Checks that the character is not built until its ground is resident, that
## the curtain covers the wait and lifts once it stands, that the main thread
## keeps drawing while the ground loads (no synchronous prime), and that the
## ground under a respawn destination is loaded while the player is dead, so
## the respawn itself needs no curtain. Writes curtain/arrival captures to
## $ELORIA_ARTIFACT_DIR (default res://test-artifacts/arrival-curtain).
var main: Control
var output := ""
var failures := 0
const LOCAL := 99
const LANDING := Vector2i(130, 214)
## Far across Landfall from the landing: the Lantern Mine entrance.
const FAR := Vector2i(332, 86)
## A respawn prefetched while dead: Landfall's south-east chunk 12_08, about
## 345 m from both earlier arrivals (beyond the 240 m lead and 320 m retain).
const RESPAWN := Vector2i(496, 444)

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func capture(name: String) -> void:
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(name + ".png"))

func actor(x: int, y: int) -> Dictionary:
	return {"actor_id": LOCAL, "kind": 1, "actor_type": 0, "name": "Arrival", "map": "landfall",
		"x": x, "y": y, "rotation": 0, "health": 100, "max_health": 100, "alive": true,
		"appearance": {}, "equipment_visuals": CreationArchetypes.loadout_at(0)}

## Frames until the curtain is down, the longest frame seen while waiting.
func wait_for_arrival(label: String, deadline_msec := 90000) -> int:
	var curtain: CanvasLayer = main.arrival_curtain
	var longest := 0
	var last := Time.get_ticks_msec()
	var began := last
	var progress_seen: Array[float] = []
	var captured := false
	while curtain.visible and Time.get_ticks_msec() - began < deadline_msec:
		await process_frame
		var now := Time.get_ticks_msec()
		longest = maxi(longest, now - last)
		last = now
		progress_seen.append(curtain.progress())
		if not captured and curtain.progress() > 0.3:
			captured = true
			await capture(label + "-loading")
		var shown: Variant = main.actor_nodes.get(LOCAL)
		if is_instance_valid(shown) and (shown as Node3D).visible and not bool(main._arrival.get("ready", true)):
			expect(false, label + ": the character is never shown before its ground is resident")
			break
		if curtain.blocks_input() and is_instance_valid(shown) and not main._arrival_unreported:
			expect(false, label + ": the server is not told of the arrival behind the curtain")
			break
	var monotonic := true
	for index: int in range(1, progress_seen.size()):
		if progress_seen[index] < progress_seen[index - 1]:
			monotonic = false
	expect(not curtain.visible, "%s: the curtain lifts once the character stands (%d ms)" % [
		label, Time.get_ticks_msec() - began])
	expect(monotonic, label + ": the loading bar only moves forward")
	print("%s: longest frame while loading %d ms" % [label, longest])
	await expect_reported(label)
	return longest

## The server keeps a loading character out of every fight until the client
## says `#arrived` (main.gd `_report_arrival`); there is no link here, so the
## report is read off the flag it clears.
func expect_reported(label: String) -> void:
	for frame: int in 5:
		await process_frame
	expect(not main._arrival_unreported, label + ": the arrival is reported once the character stands")

func run() -> void:
	var requested := OS.get_environment("ELORIA_ARTIFACT_DIR")
	output = requested if not requested.is_empty() else \
		ProjectSettings.globalize_path("res://test-artifacts/arrival-curtain")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var state := root.get_node("AppState")
	var curtain: CanvasLayer = main.arrival_curtain

	# Signing in: the curtain goes up with the request, before LOG_IN_OK.
	main.call("_set_login_screen_visible", false)
	curtain.begin("Signing in…")
	await capture("login-curtain")
	state.authenticated = true
	state.connection_state = "connected"
	state.local_actor_id = LOCAL
	state.current_map = "landfall"
	state.game_minute = 600
	state.game_minute_anchor_msec = Time.get_ticks_msec()
	state.actors = {LOCAL: actor(LANDING.x, LANDING.y),
		100: {"actor_id": 100, "kind": 2, "actor_type": 307, "name": "Nash", "map": "landfall",
			"x": 133, "y": 220, "rotation": -24576, "health": 100, "max_health": 100, "alive": true}}
	main.game_view.show()
	main.call("_load_server_map")
	main.call("_sync_world")
	var stream := main.world_loader.world_root as ContinentChunkStream
	expect(stream != null, "Landfall streams its chunks")
	if stream == null:
		await finish()
		return
	expect(curtain.visible and not main.actor_nodes.has(LOCAL),
		"login: the character waits behind the curtain while its ground loads")
	expect(stream.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "ready").is_empty(),
		"login: no chunk was imported on the login frame")
	var login_longest := await wait_for_arrival("login")
	expect(main.actor_nodes.has(LOCAL) and main._grounded_actors.has(LOCAL),
		"login: the character stands grounded when the curtain lifts")
	var landing: Vector3 = main.adapter.tile_center(LANDING.x, LANDING.y)
	expect(stream.arrival_ready(landing), "login: every cell framing the landing is resident")
	expect(stream.events.filter(func(e: Dictionary) -> bool: return str(e.event) == "arrival_reprime").is_empty(),
		"login: no synchronous re-prime")
	var slowest_install := 0.0
	for event: Dictionary in stream.events:
		if str(event.event) == "ready":
			slowest_install = maxf(slowest_install, float(event.get("activate_ms", 0.0)))
	expect(slowest_install < 50.0,
		"login: the ground attached without stalling a frame (slowest chunk %.1f ms)" % slowest_install)
	# The first build of the character's and Nash's models is still one main-thread
	# step (about 2 s in a debug build, cached for every later arrival). It runs
	# behind the drawn curtain, overlapped with the chunk imports.
	print("login: longest frame %d ms (first actor model build, behind the curtain)" % login_longest)
	for frame: int in 10:
		await process_frame
	await capture("login-arrived")

	# A far teleport on the same map: KILL_ALL_ACTORS, then the actor elsewhere.
	state.actors = {}
	main.call("_sync_world")
	state.actors = {LOCAL: actor(FAR.x, FAR.y)}
	main.call("_sync_world")
	var far: Vector3 = main.adapter.tile_center(FAR.x, FAR.y)
	expect(curtain.visible and not main.actor_nodes.has(LOCAL) and not stream.arrival_ready(far),
		"teleport: an unloaded destination is covered while it loads")
	var teleport_longest := await wait_for_arrival("teleport")
	expect(main.actor_nodes.has(LOCAL) and stream.arrival_ready(far), "teleport: arrives on loaded ground")
	expect(teleport_longest < 1000, "teleport: no frame froze while the destination loaded (%d ms)" % teleport_longest)
	await capture("teleport-arrived")

	# Dead: the respawn destination's ground loads while the player waits.
	var respawn: Vector3 = main.adapter.tile_center(RESPAWN.x, RESPAWN.y)
	expect(not stream.arrival_ready(respawn), "death: the respawn ground starts unloaded")
	state.death = {"kind": "death", "dead": true, "ready": false, "remaining": 5.0,
		"destination": {"map": "landfall", "x": RESPAWN.x, "y": RESPAWN.y}}
	main.call("_prefetch_respawn")
	var deadline := Time.get_ticks_msec() + 60000
	while not stream.prefetch_ready() and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(stream.prefetch_ready() and stream.arrival_ready(respawn),
		"death: the respawn destination is loaded while the player is dead")
	expect(stream.focus.distance_to(far) < 64.0, "death: the prefetch leaves the camera's ground where it is")
	# The respawn: the server moves the character, then sends the death state.
	state.actors = {}
	main.call("_sync_world")
	state.actors = {LOCAL: actor(RESPAWN.x, RESPAWN.y)}
	main.call("_sync_world")
	expect(main.actor_nodes.has(LOCAL) and not curtain.visible,
		"respawn: the character stands at once, with no loading screen")
	await expect_reported("respawn")
	state.death = {"kind": "death", "dead": false, "ready": false, "remaining": 0.0}
	main.call("_prefetch_respawn")
	for frame: int in 10:
		await process_frame
	await capture("respawn-arrived")
	await finish()

func finish() -> void:
	if is_instance_valid(main):
		main.set_process(false)
		main.arrival_curtain.cancel()
	await process_frame
	if is_instance_valid(main):
		main.exterior_stream.clear()
		while not main.exterior_stream.is_idle():
			await process_frame
	await ContinentChunkStream.drain_workers(self)
	if is_instance_valid(main):
		main.queue_free()
	await process_frame
	print("arrival curtain tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

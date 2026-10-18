extends SceneTree
## Render the real Landfall chunks preloaded during creation, then run the
## production arrival with the starting player and Nash. No live account needed.
var main: Control
var output := ""
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func capture(name: String) -> void:
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(name + ".png"))

func run() -> void:
	var requested := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not requested.is_empty():
		output = requested
	else:
		output = ProjectSettings.globalize_path("res://test-artifacts/new-character-intro")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.call("_set_login_screen_visible", false)
	main.creation_panel.show()
	var intro: Node = main.character_intro
	intro.prewarm(MapRegistry.resolve(main.map_registry, "landfall"), main.world_root)
	var stream: ContinentChunkStream = intro._stream
	expect(is_instance_valid(stream), "creation starts the city's background stream")
	if not is_instance_valid(stream):
		await finish()
		return
	var began := Time.get_ticks_msec()
	var deadline := began + 120000
	while not stream.views_ready() and not stream.views_failed() and Time.get_ticks_msec() < deadline:
		await process_frame
	print("creation preload: ", stream.cells.size(), " cells, ", stream.resident_bytes / 1048576,
		" MiB, ", Time.get_ticks_msec() - began, " ms")
	expect(stream.views_ready(), "city sweep and spawn load while creation remains visible")
	if not stream.views_ready():
		await finish()
		return
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 99
	state.current_map = "landfall"
	state.game_minute = 600
	state.game_minute_anchor_msec = Time.get_ticks_msec()
	state.quest_offer_actors = {100: true}
	state.actor_occupations = {100: "Wayfinder"}
	state.actors = {
		99: {"actor_id":99, "kind":1, "actor_type":0, "name":"New arrival", "map":"landfall",
			"x":130, "y":214, "rotation":0, "health":100, "max_health":100, "alive":true,
			"appearance":{}, "equipment_visuals":CreationArchetypes.loadout_at(0)},
		100: {"actor_id":100, "kind":2, "actor_type":307, "name":"Nash", "map":"landfall",
			"x":134, "y":220, "rotation":-24576, "health":100, "max_health":100, "alive":true}}
	intro.arm(main.main_viewport)
	main.creation_panel.hide()
	main.game_view.show()
	main.call("_load_server_map")
	main.call("_sync_world")
	expect(main.world_loader.world_root == stream and main.world_loader.loaded_by_adoption,
		"login adopts the preloaded city and retains its chunk objects")
	var captures := [0.8, 3.0, 5.0, 7.7]
	var index := 0
	deadline = Time.get_ticks_msec() + 60000
	var saw_playing := false
	while intro.blocks_input() and Time.get_ticks_msec() < deadline:
		await process_frame
		if intro.playing:
			saw_playing = true
			if index < captures.size() and intro.elapsed >= float(captures[index]):
				await capture("arrival-%d" % index)
				index += 1
	expect(saw_playing and index == 4, "real camera flies over the city and descends to the player")
	for frame: int in range(5):
		await process_frame
	await capture("arrival-playable")
	var player: Node3D = main.actor_nodes.get(99)
	var nash: Node3D = main.actor_nodes.get(100)
	expect(is_instance_valid(player) and is_instance_valid(nash), "both arrivals are rendered")
	if is_instance_valid(player) and is_instance_valid(nash):
		var marker := nash.get_node_or_null("QuestOfferMarker") as Label3D
		expect(marker != null and marker.visible and nash.is_visible_in_tree(),
			"Nash's quest exclamation marker remains visible beside the player's HUD")
		print("final camera: ", main.camera_rig.camera_diagnostics())
		print("player: ", player.global_position, " Nash: ", nash.global_position)
	await finish()

func finish() -> void:
	if is_instance_valid(main):
		main.set_process(false)
		main.character_intro.cancel()
	await process_frame
	if is_instance_valid(main):
		main.exterior_stream.clear()
		while not main.exterior_stream.is_idle():
			await process_frame
	await ContinentChunkStream.drain_workers(self)
	if is_instance_valid(main):
		main.queue_free()
	await process_frame
	print("rendered character intro: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

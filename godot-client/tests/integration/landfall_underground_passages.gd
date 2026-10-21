extends SceneTree
## Underground passages through the real client (pass 2, 2026-10-21): a passage is a pair of portals on the same
## map (landfall_insides), so using one makes the server answer as for any portal - KILL_ALL_ACTORS, CHANGE_MAP to
## the map the player is already on, the player added again at the other end's arrival (eloria/world.py
## _change_map). Driven through main.gd with AppState fed as those packets feed it: the client must keep the loaded
## map (no reload, no loading curtain), stand the player at the arrival and show the section it lands in alone
## (SecretSections), with the cutaway following. Every passage end of the package is used once, in both directions.
## With no passage in the source it checks nothing and passes.
##   godot --headless --path godot-client --script res://tests/integration/landfall_underground_passages.gd

const PACKAGE := "res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"
const MAP_REFERENCE := "maps/nymara/landfall_insides.elm"
const LOCAL := 77
var failures := 0
var main: Control

func _init() -> void:
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func actor(tile: Array) -> Dictionary:
	return {"actor_id": LOCAL, "kind": 1, "actor_type": 0, "name": "Passage", "map": "landfall_insides",
		"x": int(tile[0]), "y": int(tile[1]), "rotation": 0, "health": 100, "max_health": 100, "alive": true,
		"appearance": {}, "equipment_visuals": CreationArchetypes.loadout_at(0)}

func change_map_payload() -> PackedByteArray:
	var payload := MAP_REFERENCE.to_utf8_buffer()
	payload.append(0)
	return payload

func frames(count: int) -> void:
	for unused in range(count):
		await process_frame

## The packets the server sends a player who used a portal onto the map it stands on, as AppState reads them.
func arrive(state: Node, tile: Array) -> void:
	state._on_packet(EloriaProtocol.ServerMessage.KILL_ALL_ACTORS, PackedByteArray())
	state._on_packet(EloriaProtocol.ServerMessage.CHANGE_MAP, change_map_payload())
	state.actors = {LOCAL: actor(tile)}
	state.mark_actor_changed(LOCAL)
	state.state_changed.emit(&"actors")

func run() -> void:
	var package: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PACKAGE))
	var own := str(package.asset.id)
	var ends: Array = (package.portals as Array).filter(func(p: Dictionary) -> bool:
		return str(p.destinationMap) == own)
	if ends.is_empty():
		print("Landfall underground passages: none in the package; nothing to check")
		print("Landfall underground passages: PASS (0 failures)")
		quit(0)
		return
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	root.get_node("Network").set_process(false)
	var state := root.get_node("AppState")
	main.call("_set_login_screen_visible", false)
	state.authenticated = true
	state.connection_state = "connected"
	state.local_actor_id = LOCAL
	main.game_view.show()
	var first: Dictionary = ends[0]
	state.actors = {LOCAL: actor(first.serverTile)}
	state._on_packet(EloriaProtocol.ServerMessage.CHANGE_MAP, change_map_payload())
	var deadline := Time.get_ticks_msec() + 120000
	while Time.get_ticks_msec() < deadline and (main.world_loader.world_root == null
			or not main.actor_nodes.has(LOCAL) or main.arrival_curtain.visible):
		await process_frame
	check(main.world_loader.world_root != null and main.actor_nodes.has(LOCAL), "The underground loads with the player in it")
	if main.world_loader.world_root == null:
		await finish()
		return
	await frames(6)
	var world_root: Node = main.world_loader.world_root
	var loaded := str(main.loaded_server_map)
	var adapter: CoordinateAdapter = main.adapter
	check(main.secret_sections.current_section() == str(first.section),
		"The player stands in the passage's section: " + str(first.section))
	for end: Dictionary in ends:
		# stand on the way on, then use it
		arrive(state, end.serverTile)
		await frames(4)
		check(main.secret_sections.current_section() == str(end.section),
			"Standing at %s puts the player in %s" % [end.id, end.section])
		arrive(state, end.destinationTile)
		await frames(6)
		var node := main.actor_nodes.get(LOCAL) as Node3D
		var wanted: Vector3 = adapter.tile_center(int(end.destinationTile[0]), int(end.destinationTile[1]))
		check(main.world_loader.world_root == world_root and str(main.loaded_server_map) == loaded
			and not main.arrival_curtain.visible,
			"Using %s keeps the loaded map (no reload, no curtain)" % end.id)
		check(node != null and Vector2(node.global_position.x, node.global_position.z).distance_to(
			Vector2(wanted.x, wanted.z)) < 0.75, "The player stands at the far end's arrival: " + str(end.destinationTile))
		check(main.secret_sections.current_section() == str(end.destinationSection),
			"Using %s shows the section it leads into: %s" % [end.id, end.destinationSection])
		var arrived := (world_root as Node3D).find_child("Walk_" + str(end.destinationSection) + "_*", true, false) as Node3D
		var left := (world_root as Node3D).find_child("Walk_" + str(end.section) + "_*", true, false) as Node3D
		check(arrived != null and arrived.visible and left != null and not left.visible,
			"Only the section it leads into is drawn: %s shown, %s hidden" % [end.destinationSection, end.section])
		var roof := (world_root as Node3D).find_child("Roof_" + str(end.destinationSection) + "_*", true, false) as Node3D
		check(roof != null and not roof.visible, "Its roof is cut away: " + str(end.destinationSection))
	await finish()

func finish() -> void:
	print("Landfall underground passages: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	await ContinentChunkStream.drain_workers(self)
	if is_instance_valid(main):
		main.queue_free()
	await frames(4)
	GlbSceneCache.clear()
	quit(0 if failures == 0 else 1)

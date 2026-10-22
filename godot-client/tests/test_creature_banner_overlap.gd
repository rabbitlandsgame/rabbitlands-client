extends SceneTree
## Creature names may overlap each other and NPCs, but yield to player names.

var failures := 0
var checks := 0
var main: Variant
var state: Node
var creatures: Array[ReplicatedActor3D] = []

func _init() -> void:
	_run.call_deferred()

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func make_actor(id: int, kind: int, name_colour := 0) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	main.world_root.add_child(actor)
	var dto := {"actor_id": id, "kind": kind, "name": "Actor %d" % id,
		"name_colour": name_colour, "x": 0, "y": 0, "rotation": 0,
		"health": 10, "max_health": 10}
	actor.configure(dto, CoordinateAdapter.new({"metresPerTile": 1.0}), {}, {})
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.set_health_visible(true)
	actor.position = Vector3.ZERO
	main.actor_nodes[id] = actor
	state.get("actors")[id] = dto
	return actor

func remove_actor(actor: ReplicatedActor3D) -> void:
	var id: int = actor.actor_id
	main.actor_nodes.erase(id)
	state.get("actors").erase(id)
	actor.free()

func expect_creatures_visible(visible: bool, message: String, target_id := -1) -> void:
	main._declutter_actor_overheads(target_id)
	for actor: ReplicatedActor3D in creatures:
		expect(actor.get_node("Nameplate").visible == visible,
			"%s: creature %d name" % [message, actor.actor_id])
		expect(actor.get_node("HealthBarFill").visible == visible,
			"%s: creature %d health" % [message, actor.actor_id])

func _run() -> void:
	root.size = Vector2i(1280, 720)
	state = root.get_node("AppState")
	state.set("local_actor_id", 1)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	await process_frame
	main.actor_resource_overlay.hide()
	var camera: Camera3D = main.gameplay_camera
	camera.global_position = Vector3(0, 8, 10)
	camera.look_at(Vector3(0, 1, 0))
	creatures.append(make_actor(901, ReplicatedActor3D.CREATURE_ACTOR_KIND))
	creatures.append(make_actor(902, ReplicatedActor3D.CREATURE_ACTOR_KIND))
	creatures.append(make_actor(903, ReplicatedActor3D.CREATURE_ACTOR_KIND,
		ReplicatedActor3D.INVASION_NAME_COLOUR))
	expect_creatures_visible(true, "overlapping ordinary and invasion creatures")
	expect_creatures_visible(true, "a creature target does not suppress its neighbours", 902)
	for offset: float in [-2.0, -1.0, 0.0, 1.0, 2.0]:
		camera.global_position.x = offset
		camera.look_at(Vector3(0, 1, 0))
		creatures[0].position.x = offset * 0.05
		expect_creatures_visible(true, "camera and creature movement preserve overlapping names")
	creatures[0].position = Vector3.ZERO
	var npc := make_actor(904, 2)
	expect_creatures_visible(true, "an NPC banner does not suppress creature names")
	remove_actor(npc)
	var player := make_actor(905, 1)
	expect_creatures_visible(false, "a visible player banner hides overlapping creature names")
	expect(player.get_node("Nameplate").visible, "the player keeps their banner")
	main._declutter_actor_overheads(902)
	expect(creatures[1].get_node("Nameplate").visible,
		"the combat target keeps its existing exception to player overlap")
	expect(player.get_node("Nameplate").visible,
		"a creature target does not suppress a player's banner")
	player.set_nameplate_visible(false)
	expect_creatures_visible(true, "a disabled player banner does not reserve space")
	player.set_nameplate_visible(true)
	player.position.x = 6.0
	expect_creatures_visible(true, "creature banners return when the player moves clear")
	remove_actor(player)
	var overlay: Control = main.actor_resource_overlay
	overlay.show()
	var point := creatures[0].global_position + Vector3.UP * (creatures[0].head_height() + 0.35)
	var screen := camera.unproject_position(point)
	var canvas_scale: Vector2 = main.viewport_container.size / Vector2(main.main_viewport.size)
	overlay.global_position = main.viewport_container.global_position + screen * canvas_scale - overlay.size * 0.5
	expect_creatures_visible(false, "the local player's banner also protects its space")
	overlay.hide()
	expect_creatures_visible(true, "creature banners return when the local banner clears")
	for actor: ReplicatedActor3D in creatures:
		remove_actor(actor)
	main.queue_free()
	await process_frame
	print("CREATURE_BANNER_OVERLAP checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)

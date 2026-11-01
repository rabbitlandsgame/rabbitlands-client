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

## Position real actor blocks by projecting through the gameplay camera. This
## controls the actual gap fed to Main's declutter, without a rendered frame,
## an artificial overlap predicate, or relying on a fixed font/name width.
func place_banner_with_gap(actor: ReplicatedActor3D, reference: ReplicatedActor3D,
		camera: Camera3D, gap: float) -> void:
	var point := reference.global_position + Vector3.UP * (reference.head_height() + 0.35)
	var screen := camera.unproject_position(point)
	var reference_dto: Dictionary = state.get("actors")[reference.actor_id]
	var actor_dto: Dictionary = state.get("actors")[actor.actor_id]
	var reference_rect: Rect2 = main.overhead_block_rect(screen, str(reference_dto.name))
	var actor_rect: Rect2 = main.overhead_block_rect(Vector2.ZERO, str(actor_dto.name))
	var separation := (reference_rect.size.x + actor_rect.size.x) * 0.5 + gap
	var camera_point := camera.global_transform.affine_inverse() * point
	actor.global_position = camera.project_position(screen + Vector2(separation, 0.0), -camera_point.z) \
		- Vector3.UP * (actor.head_height() + 0.35)
	var placed := camera.unproject_position(actor.global_position + Vector3.UP * (actor.head_height() + 0.35))
	var placed_rect: Rect2 = main.overhead_block_rect(placed, str(actor_dto.name))
	expect(absf(placed_rect.position.x - reference_rect.end.x - gap) < 0.1,
		"the real camera projects the requested %.1f-pixel banner gap" % gap)

func exercise_overlap_hysteresis(camera: Camera3D) -> void:
	var player := make_actor(907, 1)
	place_banner_with_gap(player, creatures[0], camera, 12.0)
	expect_creatures_visible(true, "a clear player banner starts with visible creature banners")
	for gap: float in [2.0, 4.0, 2.0, 4.0]:
		place_banner_with_gap(player, creatures[0], camera, gap)
		expect_creatures_visible(true, "small clear-edge motion keeps visible names and health stable")
	place_banner_with_gap(player, creatures[0], camera, -2.0)
	expect_creatures_visible(false, "actual player-banner overlap still hides creatures immediately")
	for gap: float in [2.0, 4.0, 2.0, 4.0]:
		place_banner_with_gap(player, creatures[0], camera, gap)
		expect_creatures_visible(false, "small clear-edge motion keeps overlap-hidden names and health stable")
	place_banner_with_gap(player, creatures[0], camera, 8.0)
	expect_creatures_visible(true, "clearing the reveal gap restores names and health in the same pass")
	place_banner_with_gap(player, creatures[0], camera, -2.0)
	main._declutter_actor_overheads(902)
	expect(creatures[1].get_node("Nameplate").visible
		and creatures[1].get_node("HealthBarFill").visible,
		"the combat target bypasses overlap hiding immediately inside the hysteresis band")
	creatures[1].set_nameplate_visible(false)
	main._declutter_actor_overheads(902)
	expect(not creatures[1].get_node("Nameplate").visible
		and not creatures[1].get_node("HealthBarFill").visible,
		"an explicit visibility choice still hides the combat target immediately")
	creatures[1].set_nameplate_visible(true)
	creatures[1].set_overhead_fade(0.0)
	main._declutter_actor_overheads(902)
	expect(not creatures[1].get_node("Nameplate").visible
		and not creatures[1].get_node("HealthBarFill").visible,
		"the hard distance fade still hides name and health immediately")
	creatures[1].set_overhead_fade(1.0)
	creatures[1].set_drawn(false)
	main._declutter_actor_overheads(902)
	expect(not creatures[1].get_node("Nameplate").visible
		and not creatures[1].get_node("HealthBarFill").visible,
		"an undrawn actor cannot regain a name or health through hysteresis")
	creatures[1].set_drawn(true)
	remove_actor(player)
	expect_creatures_visible(true, "removing the only obstacle restores banners without retained history")

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
	npc.set_nameplate_visible(false)
	var player := make_actor(905, 1)
	main._declutter_actor_overheads(-1)
	expect(player.get_node("Nameplate").visible
		and player.get_node("HealthBarFill").visible,
		"a hidden NPC banner does not claim the visible player's name or health space")
	npc.set_nameplate_visible(true)
	main._declutter_actor_overheads(-1)
	expect(npc.get_node("Nameplate").visible and not player.get_node("Nameplate").visible,
		"a visible NPC retains the existing stable same-distance ordering")
	npc.set_nameplate_visible(false)
	main._declutter_actor_overheads(-1)
	expect(player.get_node("Nameplate").visible
		and player.get_node("HealthBarFill").visible,
		"disabling the blocking NPC restores the player's name and health in the same pass")
	remove_actor(npc)
	expect_creatures_visible(false, "a visible player banner hides overlapping creature names")
	expect(player.get_node("Nameplate").visible, "the player keeps their banner")
	main._declutter_actor_overheads(902)
	expect(creatures[1].get_node("Nameplate").visible,
		"the combat target keeps its existing exception to player overlap")
	expect(player.get_node("Nameplate").visible,
		"a creature target does not suppress a player's banner")
	player.set_nameplate_visible(false)
	expect_creatures_visible(true, "a disabled player banner does not reserve space")
	var later_npc := make_actor(906, 2)
	main._declutter_actor_overheads(-1)
	expect(later_npc.get_node("Nameplate").visible,
		"a disabled earlier player banner does not hide a later NPC name")
	remove_actor(later_npc)
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
	exercise_overlap_hysteresis(camera)
	for actor: ReplicatedActor3D in creatures:
		remove_actor(actor)
	main.queue_free()
	await process_frame
	print("CREATURE_BANNER_OVERLAP checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)

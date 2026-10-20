extends SceneTree
## Production target state, scaled visual placement, and fresh strike playback.

var failures := 0
var checks := 0
var models: Dictionary
var animations: Dictionary
var equipment: Dictionary
var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})

func _init() -> void:
	call_deferred("run")

func expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)

func make_actor(stage: Node, model: String, id: int, creature := false) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var config: Dictionary = models[model]
	var actions: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
		if creature else animations)
	var errors := actor.configure({"actor_id": id, "actor_type": 218 if creature else 0,
		"kind": ReplicatedActor3D.CREATURE_ACTOR_KIND if creature else 0, "x": id, "y": 0, "rotation": 0,
		"name": model, "health": 100, "max_health": 100, "appearance": {}},
		adapter, config, actions, equipment)
	expect(errors.is_empty(), model + " imports: " + str(errors))
	actor.set_physics_process(false)
	actor.set_process(false)
	return actor

func run() -> void:
	models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	animations = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.hide()
	main.set_process(false)
	var stage := Node3D.new()
	root.add_child(stage)
	# A sloped navigation surface exercises the production ground drape.
	var ground := StaticBody3D.new()
	ground.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	stage.add_child(ground)
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(100, 0.2, 100)
	collision.shape = box
	ground.add_child(collision)
	ground.position.y = -0.1
	ground.rotation.z = 0.1
	await physics_frame
	var player := make_actor(stage, "greyhaven_male", 1)
	var wolf := make_actor(stage, "dire_wolf", 2, true)
	var other := make_actor(stage, "moorland_dire_wolf", 3, true)
	var crystal := make_actor(stage, "crystal_dire_wolf", 4, true)
	for actor: ReplicatedActor3D in [wolf, other, crystal]:
		placement_checks(actor)
	# Cover runtime enlargement as well as the original unboosted wolves.
	for model: String in ["red_fox", "crystal_wing_griffin", "giant_worm"]:
		var creature := make_actor(stage, model, 5, true)
		placement_checks(creature)
		creature.free()
	await target_checks(main, player, wolf, other)
	animation_checks(player, wolf)
	main.set("actor_nodes", {})
	main.queue_free()
	stage.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("COMBAT_READABILITY ", "PASS" if failures == 0 else "FAIL", " checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

func placement_checks(actor: ReplicatedActor3D) -> void:
	var visual := actor.get_node("NativeModel") as Node3D
	var expected: float = actor.get("_model_config").import.visualBacksetMetres * actor.get("_small_creature_scale")
	var origin := actor.position
	var collider := actor.get_node("SelectionCollision") as CollisionShape3D
	var capsule_radius: float = collider.shape.radius
	expect(is_equal_approx(visual.position.z, expected), "species setback is applied after import scale")
	for yaw: float in [0.0, PI * 0.5, PI, PI * 1.5]:
		actor.rotation.y = yaw
		var offset := visual.global_position - actor.global_position
		expect(Vector2(offset.x, offset.z).is_equal_approx(Vector2(sin(yaw), cos(yaw)) * expected),
			"visual setback follows creature facing")
		expect(actor.position == origin, "turning the offset visual preserves the server position")
	actor.set_server_scale(2.0)
	expect(is_equal_approx(visual.position.z, expected * 2.0), "invasion scale also scales the setback")
	expect(is_equal_approx(collider.shape.radius, capsule_radius), "visual setback does not change picking or collision")
	actor.set_server_scale(1.0)
	actor.rotation.y = 0.0

func marked(actor: ReplicatedActor3D) -> bool:
	var marker := actor.get_node_or_null("CombatTargetMarker") as Node3D
	return marker != null and marker.visible

func target_checks(main: Node, player: ReplicatedActor3D, wolf: ReplicatedActor3D, other: ReplicatedActor3D) -> void:
	var state := root.get_node("AppState")
	state.set("authenticated", true)
	var actors := {1: {"actor_id": 1, "name": "Player", "kind": 0},
		2: {"actor_id": 2, "name": "Wolf", "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND, "health": 100, "max_health": 100},
		3: {"actor_id": 3, "name": "Other wolf", "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND, "health": 100, "max_health": 100}}
	state.set("local_actor_id", 1)
	state.set("actors", actors)
	state.set("selected_actor_id", -1)
	state.set("combat_state", {"active": true, "target_id": 2})
	main.set("actor_nodes", {1: player, 2: wolf, 3: other})
	main.call("_on_state_changed", &"combat_state")
	expect(marked(wolf) and not marked(other), "automatic combat marks the confirmed opponent without a click")
	state.set("selected_actor_id", 2)
	main.call("_sync_selection")
	expect(not wolf.get_node("SelectionRing").visible and marked(wolf), "confirmed combat cue replaces the same actor's tentative circle")
	state.set("combat_state", {"active": false, "target_id": -1})
	main.call("_on_state_changed", &"combat_state")
	expect(wolf.get_node("SelectionRing").visible and not marked(wolf), "combat end restores a still-selected tentative circle")
	state.set("combat_state", {"active": true, "target_id": 2})
	main.call("_on_state_changed", &"combat_state")
	expect(not wolf.get_node("SelectionRing").visible, "combat re-entry hides the tentative circle without another click")
	state.set("selected_actor_id", 3)
	main.call("_sync_selection")
	expect(marked(wolf) and other.get_node("SelectionRing").visible,
		"clicking another actor keeps combat and selection cues independent")
	var marker := wolf.get_node("CombatTargetMarker") as Node3D
	var ring := marker.get_node("Ring") as MeshInstance3D
	var pointer := marker.get_node("Pointer") as Label3D
	wolf.set_nameplate_visible(false)
	wolf.set_overhead_crowded(true)
	expect(marker.visible and pointer.visible and pointer.no_depth_test, "target pointer survives hidden or crowded banners")
	expect(ring.layers == 2 and pointer.layers == preload("res://src/ui/world_label_style.gd").RENDER_LAYER, "combat cues are absent from map cameras")
	await physics_frame
	marker.call("_physics_process", 0.0)
	var surface := ring.mesh
	wolf.rotation.y = 1.2
	marker.call("_physics_process", 0.0)
	expect(marker.global_rotation.is_zero_approx(), "ground ring remains level while creature turns")
	expect(ring.mesh == surface, "stationary target reuses its draped mesh")
	var local_vertices: PackedVector3Array = ring.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var min_height := INF
	var max_height := -INF
	for vertex: Vector3 in local_vertices:
		min_height = minf(min_height, vertex.y)
		max_height = maxf(max_height, vertex.y)
	expect(max_height - min_height > 0.05, "ground ring follows the sloped navigation surface")
	wolf.set_footprint(Vector2i(2, 3))
	expect((ring.mesh as ArrayMesh).get_aabb().size.z > 3.0, "late footprint updates resize the combat cue")
	var old_pointer_height := pointer.position.y
	wolf.set_server_scale(2.0)
	expect(pointer.position.y > old_pointer_height, "target pointer follows scaled head height")
	wolf.set_server_scale(1.0)
	wolf.set_footprint(Vector2i.ONE)
	wolf.set_drawn(false)
	expect(not marked(wolf), "out-of-range target cue is hidden")
	state.set("combat_state", {"active": false, "target_id": -1})
	main.call("_on_state_changed", &"combat_state")
	wolf.set_drawn(true)
	expect(not marked(wolf), "returning in range cannot resurrect an ended target marker")
	state.set("combat_state", {"active": true, "target_id": 3})
	main.call("_on_state_changed", &"combat_state")
	expect(marked(other) and not marked(wolf), "retargeting removes the previous combat cue")
	expect(not other.get_node("SelectionRing").visible, "retargeting replaces the tentative circle on the newly confirmed opponent")
	actors[1]["aiming_at"] = 2
	state.set("actors", actors)
	main.call("_sync_overhead_health")
	expect(marked(wolf) and not marked(other), "confirmed ranged aim takes precedence")
	expect(other.get_node("SelectionRing").visible, "a different clicked actor keeps its tentative circle during ranged aim")
	actors[1]["aiming_at"] = -1
	state.set("actors", actors)
	main.call("_sync_overhead_health")
	expect(marked(other) and not marked(wolf), "clearing ranged aim restores the melee target")
	other.play_action(&"death", true)
	main.call("_sync_overhead_health")
	expect(not marked(other), "death clears the cue even before delayed combat cleanup")
	state.set("combat_state", {"active": false, "target_id": -1})
	main.call("_on_state_changed", &"combat_state")
	expect(not marked(other) and not marked(wolf), "combat end clears both cues")

func bone_rotations(actor: ReplicatedActor3D) -> Array[Quaternion]:
	var values: Array[Quaternion] = []
	var skeleton := actor.get_skeleton()
	for i: int in skeleton.get_bone_count():
		values.append(skeleton.get_bone_pose_rotation(i))
	return values

func animation_checks(actor: ReplicatedActor3D, wolf: ReplicatedActor3D) -> void:
	actor.apply_equipment_visuals({})
	expect(actor.resolver.clip_for_action(&"attack_primary") == &"Fighting_Left_Jab", "unarmed primary uses reference left jab")
	expect(actor.resolver.clip_for_action(&"attack_secondary") == &"Fighting_Right_Jab", "unarmed secondary uses reference right jab")
	expect(wolf.resolver.clip_for_action(&"attack_primary") == &"Sword_Attack", "creature's native bite mapping is preserved")
	actor.apply_equipment_visuals({0: 114})
	expect(actor.resolver.clip_for_action(&"attack_primary") == &"Combat_Slash_A", "equipping a weapon restores sword cuts")
	actor.play_action(&"combat_idle", true)
	actor.animation_player.advance(0.5)
	var before := bone_rotations(actor)
	actor.play_action(&"attack_primary", true)
	actor.animation_player.advance(1.0 / 60.0)
	var after := bone_rotations(actor)
	var largest := 0.0
	for i: int in before.size():
		if not str(actor.get_skeleton().get_bone_name(i)).contains("leaf"):
			largest = maxf(largest, rad_to_deg(before[i].angle_to(after[i])))
	expect(largest < 30.0, "fresh sword strike blends instead of the measured 78-degree snap")
	expect(is_equal_approx(actor.action_crossfade_seconds, 0.09), "fresh strike advertises its real blend duration")
	for repeat: int in 4:
		actor.animation_player.advance(0.3)
		actor.play_action(&"attack_primary", true)
		actor.animation_player.advance(0.001)
		expect(actor.presentation_action_time() < 0.01, "repeated same strike starts a fresh clock")
		expect(actor.action_crossfade_seconds > 0.0, "repeated same strike keeps a transition blend")
	expect(actor.animation_player.get_animation_library(&"action_restarts").get_animation_list().size() == 1,
		"restarting a clip reuses one alias instead of growing the library")
	var dto := {"actor_id": 1, "x": 1, "y": 0, "rotation": 0,
		"command": 46, "command_sequence": 10, "equipment_visuals": {}, "in_combat": true}
	actor.apply_server_state(dto, adapter)
	expect(actor.animation_player.assigned_animation == &"Fighting_Left_Jab", "same-packet weapon removal chooses an unarmed strike immediately")
	actor.animation_player.advance(0.2)
	var time := actor.presentation_action_time()
	actor.apply_server_state(dto, adapter)
	expect(is_equal_approx(actor.presentation_action_time(), time), "health restatement does not replay a strike")
	dto.command_sequence = 11
	actor.apply_server_state(dto, adapter)
	expect(actor.animation_player.assigned_animation == &"Fighting_Right_Jab", "fresh unarmed strikes alternate")
	actor.animation_player.advance(2.0)
	expect(actor.current_action == &"combat_idle", "unarmed strike recovers to combat idle")
	actor.play_action(&"death", true)
	actor.play_action(&"attack_primary", true)
	expect(actor.current_action == &"death", "animation changes retain latched death")
	print("STRIKE_FIRST_FRAME_MAX_JOINT_DEGREES ", largest)

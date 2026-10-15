extends SceneTree
## Large stone golems pound; the smaller variants keep their original punch.
## Exercise the shipped rigs through the real actor/importer and command path.

const LARGE_GOLEMS := ["mossbound_stone_golem", "amethyst_stone_golem",
	"frost_stone_golem", "river_stone_golem", "rune_stone_golem"]

var failures := 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func run() -> void:
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	var count := 0
	for model_name: String in catalog.models:
		if not model_name.contains("golem"):
			continue
		count += 1
		var model: Dictionary = catalog.models[model_name]
		var large: bool = model_name in LARGE_GOLEMS
		var expected_map := "res://data/animations/golem.json" if large else "res://data/animations/creature.json"
		var expected_clip := "Attack_Ground_Pound" if large else "Sword_Attack"
		var unused_clip := "Sword_Attack" if large else "Attack_Ground_Pound"
		check(model.animationMap == expected_map, model_name + " has the action map for its size")
		var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(model.animationMap))
		check(config.actions.attack_primary == expected_clip, model_name + " selects the correct attack")
		check(not config.actions.has("attack_secondary"), model_name + " does not alternate attacks")
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var dto := {"actor_id": 900 + count, "x": 0, "y": 0, "rotation": 0,
			"appearance": {}, "equipment_visuals": {}, "in_combat": true, "command": 15, "command_sequence": 1}
		var errors := actor.configure(dto, adapter, model, config, {})
		check(errors.is_empty(), model_name + " imports: " + str(errors))
		actor.set_physics_process(false)
		var player := actor.animation_player
		if player == null:
			check(false, model_name + " has an animation player")
			actor.free()
			continue
		check(player.has_animation(expected_clip), model_name + " imports its selected attack")
		check(not actor.resolver.required_clips().has(unused_clip), model_name + " does not map any action to the other attack")
		var clip := player.get_animation(expected_clip)
		check(clip.loop_mode == Animation.LOOP_NONE, model_name + " attack is a one-shot")
		if large:
			check(is_equal_approx(clip.length, 2.4), model_name + " keeps full pound recovery")
		actor.apply_server_state(dto, adapter)
		dto = ActorReducer.apply_command(dto, 46)
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"attack_primary", model_name + " starts its primary attack")
		check(player.current_animation == expected_clip, model_name + " first attack uses the selected clip")
		player.advance(player.current_animation_length + 0.1)
		dto = ActorReducer.apply_command(dto, 46)
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"attack_primary", model_name + " second attack stays primary")
		check(player.current_animation == expected_clip, model_name + " second attack uses the same clip")
		if large:
			var right_hands := {"mossbound_stone_golem": "hand_r", "amethyst_stone_golem": "Bone_018",
				"frost_stone_golem": "Bone_011", "river_stone_golem": "Bone_039", "rune_stone_golem": "Bone_016"}
			var rig := actor.get_skeleton()
			var hand := rig.find_bone(right_hands[model_name])
			check(hand >= 0, model_name + " identifies the anatomical right hand")
			player.advance(0.48)
			rig.force_update_all_bone_transforms()
			var raised := rig.global_transform * rig.get_bone_global_pose(hand).origin
			player.advance(0.40)
			rig.force_update_all_bone_transforms()
			var impact := rig.global_transform * rig.get_bone_global_pose(hand).origin
			check(raised.y > impact.y + 0.1, model_name + " right fist descends from its windup")
			check((impact-raised).dot(-actor.global_basis.z.normalized()) > 0.05,
				model_name + " strike advances toward the actor's target-facing direction")
		for tick in 12:
			player.advance(0.1)
			var skeleton := actor.get_skeleton()
			for bone in skeleton.get_bone_count():
				check(skeleton.get_bone_global_pose(bone).is_finite(), model_name + " bone pose stays finite")
		player.advance(clip.length + 0.1)
		check(actor.current_action == &"combat_idle", model_name + " recovers to combat guard")
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"combat_idle", model_name + " stale command does not repeat attack")
		dto = ActorReducer.apply_command(dto, 46)
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"attack_primary", model_name + " third attack stays primary")
		check(player.current_animation == expected_clip, model_name + " third attack still uses the selected clip")
		actor.play_action(&"attack_secondary", true)
		check(player.current_animation == expected_clip, model_name + " has no alternate attack action")
		actor.free()
		await process_frame
	check(count == 13, "all thirteen golems were exercised")
	var other: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/creature.json"))
	check(not other.actions.has("attack_secondary"), "other creatures retain their existing action map")
	NativeAnimationImporter.clear()
	await process_frame
	print("Golem ground pound: %d models, %d failures" % [count, failures])
	quit(1 if failures else 0)

extends SceneTree

var failures := 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	for option: Dictionary in models.creationOptions:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var dto := {"actor_id": 901, "x": 0, "y": 0, "rotation": 0, "appearance": {},
			"equipment_visuals": {0: 64}, "in_combat": false}
		var errors := actor.configure(dto, adapter, models.models[option.model], config, equipment)
		check(errors.is_empty(), "%s: %s" % [option.model, errors])
		check(actor.combat_presentation != null, "player rig has combat presentation")
		actor.set_physics_process(false)
		actor.apply_equipment_visuals({0: 164})
		actor.combat_presentation.update_pose()
		var idle_bow := actor.combat_presentation.bow
		var idle_visual := idle_bow.bow as Node3D
		var idle_string := idle_bow.get("_string_node") as MeshInstance3D
		check(idle_bow.visible and idle_visual != null and idle_string != null,
			"Ranger class bow replaces the hidden registry prop: " + str(option.model))
		for carry_action: StringName in [&"idle", &"combat_idle", &"walk"]:
			actor.play_action(carry_action, true)
			actor.animation_player.advance(0.5)
			actor.combat_presentation.update_pose()
			# The reviewed off-hand sword socket independently defines the
			# canonical left-fist bore; do not derive the expectation from
			# the bow presentation's own helper.
			var skeleton := actor.get_skeleton()
			var hand := skeleton.find_bone("hand_l")
			var rest := skeleton.get_bone_global_rest(hand)
			var fit := actor.rig_fit_scale("legacy")
			var socket: Dictionary = equipment.models["1:160"].socket
			var grip := (skeleton.global_transform * skeleton.get_bone_global_pose(hand) *
				rest.affine_inverse() * actor._socket_placement(socket, rest, fit, fit))
			check(idle_bow.global_position.distance_to(grip.origin) < 0.002,
				"carried Ranger handle stays in the left fist in %s: %s" % [carry_action, option.model])
			check(idle_bow.global_basis.orthonormalized().is_equal_approx(grip.basis.orthonormalized()),
				"carried Ranger haft follows the fist bore in %s: %s" % [carry_action, option.model])
			check(idle_visual.transform.is_equal_approx(Transform3D.IDENTITY) and
				idle_visual.global_transform.is_equal_approx(idle_string.global_transform),
				"carried Ranger mesh and live string share the grip frame: " + str(option.model))
		for effect_id: int in [2, 84, 83, 85, 0, 86, 10, 79, 19, 18, 75]:
			actor.set_spell_variant(effect_id)
			var action := SpellPresentation.action_for_effect(effect_id)
			actor.play_action(action, true)
			check(str(actor.animation_player.current_animation).begins_with("spell_variants/"), "spell has a generated rig animation")
			actor.animation_player.advance(0.45)
			check(actor.spell_release_origin().is_finite(), "generated spell hand pose is finite")
		actor.set_spell_variant(3)
		for action: StringName in [&"cast_aggressive", &"cast_defensive", &"heal", &"attack_primary", &"attack_secondary", &"ranged_attack"]:
			actor.play_action(action, true)
			actor.animation_player.advance(0.001)
			check(actor.spell_release_origin().is_finite() and actor.spell_release_origin().y > actor.global_position.y,
				"spell release follows posed hands: " + str(option.model))
			check(actor.spell_target_position().is_finite() and actor.spell_target_position().y > actor.global_position.y,
				"spell target follows the rig chest: " + str(option.model))
			var duration := actor.animation_player.current_animation_length
			check(duration > 0.1, "action has a real clip: " + action)
			actor.animation_player.advance(duration + 0.1)
			check(actor.current_action == &"idle", "action recovers to idle: " + action)
		actor.play_action(&"ranged_draw")
		actor.animation_player.advance(0.7)
		check(actor.current_action == &"ranged_hold", "draw transitions to hold")
		actor.combat_presentation.update_pose()
		check(idle_visual.transform.is_equal_approx(Transform3D.IDENTITY) and
			idle_string.transform.is_equal_approx(Transform3D.IDENTITY),
			"active Ranger draw clears the idle-only palm fit: " + str(option.model))
		for tick: int in 60:
			actor.animation_player.advance(1.0 / 60.0)
		actor._advance_facing_offset(1.0)
		await process_frame
		check(actor.animation_player.is_playing(), "bow hold loops beyond clip end")
		actor.combat_presentation.update_pose()
		var bow := actor.combat_presentation.bow
		check(bow.visible and bow.arrow.visible, "ranging shows bow and nocked arrow")
		check(bow.arrow.global_position.distance_to(actor.combat_presentation.hand_position(
			actor.get_skeleton().find_bone("hand_r"))) < 0.09, "arrow nock follows draw fingers: " + str(option.model))
		var arrow_point := bow.arrow.global_transform * Vector3(0, 0, -1.15)
		check((arrow_point-bow.global_position).dot(-bow.global_basis.z.normalized()) > 0.03,
			"broadhead extends past the bow at full draw: " + str(option.model))
		var aim_axis := -bow.global_basis.z.normalized()
		check(aim_axis.dot(-actor.global_basis.z.normalized()) > 0.97,
			"bow aim aligns with authoritative facing: %s aim=%s forward=%s offset=%s clip=%s time=%s" % [option.model, aim_axis, -actor.global_basis.z.normalized(), actor._facing_offset, actor.animation_player.current_animation, actor.animation_player.current_animation_position])
		actor.play_action(&"ranged_attack", true)
		actor.animation_player.advance(0.01)
		actor.combat_presentation.update_pose()
		check(not bow.arrow.visible, "arrow leaves hand on release")
		actor.play_action(&"cast_channel_enter")
		actor.combat_presentation.set_spell_power(10)
		actor.animation_player.advance(0.6)
		check(actor.current_action == &"cast_channel", "channel entry becomes a sustained loop")
		check(actor.combat_presentation.spell_power == 10, "channel loop retains invested power")
		actor.animation_player.advance(3.0)
		check(actor.animation_player.is_playing(), "channel remains animated")
		dto["command"] = 7
		dto["command_sequence"] = 1
		actor.apply_server_state(dto, adapter)
		actor.play_action(&"heal")
		actor.combat_presentation.update_pose()
		check(actor.combat_presentation.spell_power == 1, "a new cast cannot inherit old visual power")
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"heal", "unrelated state refresh does not interrupt healing")
		dto = ActorReducer.apply_command(dto, 46)
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"attack_primary", "fresh melee command starts first cut")
		actor.animation_player.advance(1.0)
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"idle", "stale command does not replay a completed cut")
		dto = ActorReducer.apply_command(dto, 46)
		actor.apply_server_state(dto, adapter)
		check(actor.current_action == &"attack_secondary", "next melee command alternates cut")
		dto = ActorReducer.apply_command(dto, 3)
		actor.apply_server_state(dto, adapter)
		actor.play_action(&"heal")
		check(actor.current_action == &"death", "late spell feedback cannot revive a dead actor")
		actor.queue_free()
		await process_frame
	var missile := MissileFlight3D.new()
	root.add_child(missile)
	var release := Vector3(0.2, 1.4, 0.1)
	missile.configure(Vector3.ZERO, Vector3(5, 0, -4), release, true)
	check(missile.origin == release, "arrow starts at actual nock position")
	check(is_equal_approx(missile.destination.y, 0.06), "ground shot lands at ground, not chest height")
	check(missile.point_at(0.5).y > missile.origin.lerp(missile.destination, 0.5).y, "arrow follows shallow arc")
	missile.free()
	check(SpellPresentation.action_for_effect(17).is_empty(), "harvest interruption is not a cast")
	check(SpellPresentation.action_for_spell(21) == &"heal", "group healing uses healing action")
	check(SpellPresentation.action_for_effect(73) == &"cast_aggressive", "poison uses aggressive action")
	var state := root.get_node("AppState")
	var requests: Array[Dictionary] = []
	state.actor_animation_requested.connect(func(request: Dictionary) -> void: requests.append(request))
	state.set("local_actor_id", 901)
	state.call("_on_packet", 70, PackedByteArray([4, 1]))
	check(requests.back().action == &"cast_channel_enter", "target selection channels after server confirmation")
	state.call("_on_packet", 70, PackedByteArray([1, 1]))
	check(requests.back().action == &"heal", "successful healing result releases healing animation")
	state.call("_on_packet", 70, PackedByteArray([1, 3]))
	check(requests.back().action == &"cast_defensive", "shield result releases defensive animation")
	state.call("_on_packet", 70, PackedByteArray([1, 6]))
	check(requests.back().action == &"cast_aggressive", "harm result releases aggressive animation")
	state.call("_on_packet", 84, PackedByteArray([0x85, 3, 2, 0]))
	check(requests.back().action == "ranged_draw", "actor aim packet drives draw animation")
	for effect_id: int in [1, 2, 3, 10, 12, 72, 73, 74]:
		var effect := WorldEffect3D.new()
		root.add_child(effect)
		effect.configure(effect_id, Vector3.ZERO, Vector3(0, 3, 0))
		effect._process(0.3)
		check(effect.get_node_or_null("EffectRunes") != null, "effect carries rune geometry")
		effect.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("combat presentation: ", "PASS (16 player rigs, action transitions, props, effects)" if failures == 0 else str(failures) + " FAILURES")
	quit(failures)

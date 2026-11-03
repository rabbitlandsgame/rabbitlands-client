extends SceneTree

var failures := 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

## The action of the last animation request, or "" when none came: a packet
## that requested nothing fails its check instead of stopping the script (and,
## with it, the run) on a null access.
func _last_requested_action(requests: Array[Dictionary]) -> String:
	return str(requests.back().get("action", "")) if not requests.is_empty() else ""

## Hand-cue switch (Low actor tier, LAT-L2). Main turns cues off for crowd
## bodies off the full animation rate at Low; with them off a body draws no cue
## geometry and reads its hands only to aim a bow, while every carried-prop
## decision is the same as with them on.
func _check_cue_gate(models: Dictionary, config: Dictionary, equipment: Dictionary,
		adapter: CoordinateAdapter) -> void:
	var cue_checks_before := failures
	var low := ActorRenderQuality.Quality.LOW
	for level: int in [ActorRenderQuality.Quality.MEDIUM, ActorRenderQuality.Quality.HIGH]:
		check(CombatPresentation3D.cues_wanted(level, false, false)
			and CombatPresentation3D.cues_wanted(level, true, false),
			"quality %d draws every body's cues, as before the Low tier" % level)
	check(not CombatPresentation3D.cues_wanted(low, false, false),
		"Low leaves a crowd body off the full rate without cues")
	check(CombatPresentation3D.cues_wanted(low, true, false)
		and CombatPresentation3D.cues_wanted(low, false, true),
		"Low still draws cues for full-rate bodies and priority actors")
	var option: Dictionary = models.creationOptions[0]
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	# A main-hand sword, so the melee swing has a trail tip.
	var dto := {"actor_id": 902, "x": 0, "y": 0, "rotation": 0, "appearance": {},
		"equipment_visuals": {0: 114}, "in_combat": false}
	var errors := actor.configure(dto, adapter, models.models[option.model], config, equipment)
	check(errors.is_empty(), "cue fixture builds: %s" % [errors])
	actor.set_physics_process(false)
	var cues := actor.combat_presentation
	check(cues != null and cues.cues_allowed, "a new body draws its cues")
	if cues == null:
		actor.queue_free()
		await process_frame
		return
	var mesh := (cues.get_node("ActionEffects") as MeshInstance3D).mesh as ImmediateMesh
	# A cast: drawn with cues, nothing without, and its palette survives.
	actor.play_action(&"cast_aggressive", true)
	cues.set_spell_palette(Color(0.2, 0.9, 0.3))
	actor.animation_player.advance(0.3)
	cues.update_pose()
	check(mesh.get_surface_count() == 1, "with cues a cast draws its hand arcs (control)")
	cues.set_cues_allowed(false)
	check(not cues.cues_allowed and mesh.get_surface_count() == 0,
		"turning cues off removes the arc drawn now")
	for step: int in 5:
		actor.animation_player.advance(1.0 / 30.0)
		cues.update_pose()
		check(mesh.get_surface_count() == 0, "without cues a cast draws nothing (step %d)" % step)
	check(cues.get("_spell_color") == Color(0.2, 0.9, 0.3),
		"a cast without cues keeps its spell colour for when cues return")
	cues.set_cues_allowed(true)
	actor.animation_player.advance(1.0 / 30.0)
	cues.update_pose()
	check(mesh.get_surface_count() == 1, "cues back on draw the cast again mid-clip")
	# A melee swing: no trail is gathered without cues.
	var tip: Variant = actor.weapon_trail_tip()
	check(tip is Vector3, "the sword gives the swing a trail tip")
	for allowed: bool in [false, true]:
		cues.set_cues_allowed(allowed)
		actor.play_action(&"attack_primary", true)
		var drawn_steps := 0
		var longest_trail := 0
		for step: int in 18:
			actor.animation_player.advance(1.0 / 30.0)
			cues.update_pose()
			drawn_steps += int(mesh.get_surface_count() > 0)
			longest_trail = maxi(longest_trail, (cues.get("_trail") as Array).size())
		if allowed:
			check(drawn_steps > 0 and longest_trail >= 2,
				"with cues a swing draws its trail (control: %d steps, %d points)" % [drawn_steps, longest_trail])
		else:
			check(drawn_steps == 0 and longest_trail == 0,
				"without cues a swing gathers and draws no trail (%d steps, %d points)" % [drawn_steps, longest_trail])
	cues.set_cues_allowed(true)
	actor.play_action(&"attack_secondary", true)
	for step: int in 10:
		actor.animation_player.advance(1.0 / 30.0)
		cues.update_pose()
	var trail_before := (cues.get("_trail") as Array).size()
	cues.set_cues_allowed(false)
	check(trail_before > 0 and (cues.get("_trail") as Array).is_empty()
		and mesh.get_surface_count() == 0,
		"turning cues off mid-swing forgets the trail (%d points) and its geometry" % trail_before)
	actor.animation_player.advance(1.0)
	# The Ranger bow: carry, draw and release poses are the same either way.
	actor.apply_equipment_visuals({0: 164})
	var bow_path := str((equipment.models["0:164"] as Dictionary).scene)
	for action: StringName in [&"idle", &"ranged_draw", &"ranged_attack", &"idle"]:
		actor.play_action(action, true)
		actor.animation_player.advance(0.7 if action == &"ranged_draw" else 0.05)
		var poses := {}
		for allowed: bool in [false, true]:
			cues.set_cues_allowed(allowed)
			cues.update_pose()
			var props := []
			for part: int in [0, 1]:
				for prop: Node in actor._equipment_nodes.get(part, []):
					props.append(is_instance_valid(prop) and prop is Node3D and (prop as Node3D).visible)
			poses[allowed] = [cues.bow != null and cues.bow.visible,
				cues.bow.global_transform if cues.bow != null else Transform3D(),
				cues.bow.nock_position() if cues.bow != null else Vector3.ZERO, props,
				mesh.get_surface_count()]
		var state := str(actor.current_action)
		check(bool(poses[false][0]) and bool(poses[true][0]),
			"the bow shows in %s with and without cues" % state)
		check(poses[false][1] == poses[true][1] and poses[false][2] == poses[true][2],
			"the bow's pose and nock in %s do not depend on cues" % state)
		check(poses[false][3] == poses[true][3], "hand props in %s do not depend on cues" % state)
		check(int(poses[false][4]) == 0, "without cues %s draws no cue geometry" % state)
		if state == "ranged_attack":
			check(int(poses[true][4]) == 1, "with cues the release draws its flash (control)")
	cues.set_cues_allowed(false)
	actor.play_action(&"ranged_draw", true)
	actor.animation_player.advance(0.7)
	cues.update_pose()
	check(cues.bow.nock_position().distance_to(cues.hand_position(
		actor.get_skeleton().find_bone("hand_r"))) < 0.09,
		"without cues the drawn string still follows the draw hand")
	actor.apply_equipment_visuals({})
	cues.update_pose()
	check(not cues.bow.visible, "unequipping the bow without cues still hides it")
	cues.set_cues_allowed(true)
	# Hand reads, counted on a probe presentation of the same body (which
	# keeps the Ranger bow, so it can draw; the probe's own bow is set per row).
	actor.apply_equipment_visuals({0: 164})
	var probe_script := GDScript.new()
	probe_script.source_code = "extends \"res://src/actors/combat_presentation_3d.gd\"\n" \
		+ "var hand_reads := 0\n" \
		+ "func hand_position(index: int) -> Vector3:\n" \
		+ "\thand_reads += 1\n" \
		+ "\treturn super(index)\n"
	check(probe_script.reload() == OK, "the hand-read probe compiles")
	var probe := probe_script.new() as CombatPresentation3D
	probe.configure(actor)
	actor.add_child(probe)
	var reads := {}
	for row: Array in [[&"cast_aggressive", true, ""], [&"cast_aggressive", false, ""],
			[&"ranged_draw", false, bow_path], [&"ranged_draw", false, ""],
			[&"ranged_draw", true, ""], [&"idle", false, bow_path]]:
		probe.set_equipped_bow(str(row[2]))
		probe.set_cues_allowed(bool(row[1]))
		actor.play_action(row[0], true)
		actor.animation_player.advance(0.05)
		probe.set("hand_reads", 0)
		probe.update_pose()
		reads["%s/%s/%s" % [row[0], "cues" if row[1] else "none", "bow" if row[2] != "" else "bare"]] \
			= int(probe.get("hand_reads"))
	check(reads == {"cast_aggressive/cues/bare": 2, "cast_aggressive/none/bare": 0,
		"ranged_draw/none/bow": 2, "ranged_draw/none/bare": 0, "ranged_draw/cues/bare": 2,
		"idle/none/bow": 0}, "hands are read for cues and to aim a bow only: %s" % reads)
	probe.free()
	# Cost per update, bare-handed (informational; this machine, not core-pinned).
	actor.apply_equipment_visuals({})
	cues.set_cues_allowed(true)
	actor.play_action(&"cast_aggressive", true)
	actor.animation_player.advance(0.3)
	check(actor.current_action == &"cast_aggressive", "the timed body is casting")
	var timings := {}
	for allowed: bool in [true, false, true, false]:
		cues.set_cues_allowed(allowed)
		var began := Time.get_ticks_usec()
		for repeat: int in 2000:
			cues.update_pose()
		var per_call := float(Time.get_ticks_usec() - began) / 2000.0
		var key := "cast_cues_on" if allowed else "cast_cues_off"
		timings[key] = minf(float(timings.get(key, INF)), per_call)
	actor.play_action(&"idle", true)
	actor.animation_player.advance(0.05)
	var idle_began := Time.get_ticks_usec()
	for repeat: int in 2000:
		cues.update_pose()
	timings["idle_fast_path"] = float(Time.get_ticks_usec() - idle_began) / 2000.0
	print("combat cues update_pose us per call (best of 2 x 2000): ", timings)
	actor.queue_free()
	await process_frame
	print("combat cues: ", "PASS" if failures == cue_checks_before else
		str(failures - cue_checks_before) + " FAILURES")

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})
	await _check_cue_gate(models, config, equipment, adapter)
	for option: Dictionary in models.creationOptions:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var dto := {"actor_id": 901, "x": 0, "y": 0, "rotation": 0, "appearance": {},
			"equipment_visuals": {0: 64}, "in_combat": false}
		var errors := actor.configure(dto, adapter, models.models[option.model], config, equipment)
		check(errors.is_empty(), "%s: %s" % [option.model, errors])
		check(actor.combat_presentation != null, "player rig has combat presentation")
		actor.set_physics_process(false)
		actor.apply_equipment_visuals({})
		for action: StringName in [&"attack_primary", &"attack_secondary"]:
			actor.play_action(action, true)
			var clip := actor.resolver.clip_for_action(action)
			check(clip in [&"Fighting_Left_Jab", &"Fighting_Right_Jab"],
				"unarmed rig selects a reference punch: " + str(option.model))
			actor.animation_player.advance(0.2)
			check(actor.spell_release_origin().is_finite(),
				"reference punch has a finite hand pose: " + str(option.model))
			actor.animation_player.advance(actor.animation_player.get_animation(clip).length + 0.1)
			check(actor.current_action == &"idle", "reference punch recovers: " + str(option.model))
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
			# The imported bow curves in X; the live string curves in Z. Verify
			# the source mesh's sampled grip and axes rather than identical roots.
			check((idle_visual.global_transform * Vector3(0.02325, 0, 0)).distance_to(idle_string.global_position) < 0.002 and
				idle_visual.global_basis.y.normalized().is_equal_approx(idle_string.global_basis.y.normalized()) and
				idle_visual.global_basis.x.normalized().is_equal_approx(idle_string.global_basis.z.normalized()),
				"carried current bow grip and live string stay aligned: " + str(option.model))
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
		check((idle_visual.transform * Vector3(0.02325, 0, 0)).length() < 0.001 and
			idle_string.transform.is_equal_approx(Transform3D.IDENTITY),
			"active draw centers the current bow's sampled grip and clears idle cant: " + str(option.model))
		for tick: int in 60:
			actor.animation_player.advance(1.0 / 60.0)
		actor._advance_facing_offset(1.0)
		await process_frame
		check(actor.animation_player.is_playing(), "bow hold loops beyond clip end")
		actor.combat_presentation.update_pose()
		var bow := actor.combat_presentation.bow
		check(bow.visible and bow.bow != null, "ranging shows the equipped current bow")
		check(bow.nock_position().distance_to(actor.combat_presentation.hand_position(
			actor.get_skeleton().find_bone("hand_r"))) < 0.09, "arrow nock follows draw fingers: " + str(option.model))
		check(bow.arrow == null and preload("res://src/actors/archived_model_policy.gd").is_retired_path(RangerBow3D.ARROW_PATH),
			"retired arrow art stays absent while the live string retains its release point")
		var aim_axis := -bow.global_basis.z.normalized()
		check(aim_axis.dot(-actor.global_basis.z.normalized()) > 0.97,
			"bow aim aligns with authoritative facing: %s aim=%s forward=%s offset=%s clip=%s time=%s" % [option.model, aim_axis, -actor.global_basis.z.normalized(), actor._facing_offset, actor.animation_player.current_animation, actor.animation_player.current_animation_position])
		actor.play_action(&"ranged_attack", true)
		actor.animation_player.advance(0.01)
		actor.combat_presentation.update_pose()
		check(bow.nock_position().is_finite(), "release origin remains finite without retired arrow art")
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
	check(_last_requested_action(requests) == "cast_channel_enter", "target selection channels after server confirmation")
	state.call("_on_packet", 70, PackedByteArray([1, 1]))
	check(_last_requested_action(requests) == "heal", "successful healing result releases healing animation")
	state.call("_on_packet", 70, PackedByteArray([1, 3]))
	check(_last_requested_action(requests) == "cast_defensive", "shield result releases defensive animation")
	state.call("_on_packet", 70, PackedByteArray([1, 6]))
	check(_last_requested_action(requests) == "cast_aggressive", "harm result releases aggressive animation")
	state.call("_on_packet", 84, PackedByteArray([0x85, 3, 2, 0]))
	check(_last_requested_action(requests) == "ranged_draw", "actor aim packet drives draw animation")
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

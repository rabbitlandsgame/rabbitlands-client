extends SceneTree
const Presentation = preload("res://src/world/technique_presentation.gd")
const Effect = preload("res://src/world/technique_effect_3d.gd")
const Icons = preload("res://src/ui/technique_icons.gd")
var failures := 0

func _init() -> void:
	create_timer(60).timeout.connect(func(): push_error("Technique check timed out"); quit(98))
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)

func run() -> void:
	root.size = Vector2i(960, 600)
	var actors_before: Dictionary = root.get_node("AppState").actors.duplicate(true)
	var review = load("res://src/dev/technique_showcase.tscn").instantiate()
	root.add_child(review)
	await process_frame
	var preview = review.preview
	preview.set_process(false)
	preview.stage.process_mode = Node.PROCESS_MODE_DISABLED
	check(Presentation.PROFILES.size() == 24 and Presentation.PROFILES.keys().all(func(key): return key in Icons.ORDER), "all 24 catalogued techniques have presentation")
	check(preview.viewport.own_world_3d and not preview.viewport.handle_input_locally, "preview has an isolated world without input")
	var actor: ReplicatedActor3D = preview.source
	var target: ReplicatedActor3D = preview.target
	actor.apply_equipment_visuals({0: 164})
	actor.play_action(&"ranged_draw", true)
	actor.animation_player.advance(0.4)
	actor.combat_presentation.update_pose()
	check(actor.combat_presentation.bow != null and actor.combat_presentation.bow.bow != null and actor.combat_presentation.bow.visible, "current imported bow remains visible during ranging")
	check(actor.combat_presentation.bow.get("_path").ends_with("amberwood_longbow.glb"), "ranging uses the equipped current bow rather than retired art")
	actor.apply_equipment_visuals({0: 114})
	check(not actor.combat_presentation.bow.visible, "unequipping the bow clears its combat presentation")
	var original_primary: String = actor.resolver.clip_for_action(&"attack_primary")
	for key: String in Icons.ORDER:
		var phase := "shot" if key in Presentation.RANGED else "activate" if key in Presentation.SUPPORT else "strike"
		var motion: Array = Presentation.motion_for(key, phase)
		actor.play_technique(key, phase)
		if not motion.is_empty():
			check(str(actor.animation_player.current_animation) == motion[0], key + " plays its real rig clip")
			var clip := actor.animation_player.get_animation(motion[0])
			check(clip.loop_mode == Animation.LOOP_NONE and clip.length <= 1.2, key + " is a bounded one-shot")
			for tick in range(1, 17):
				actor.animation_player.seek(clip.length * tick / 16.0, true)
				for bone in actor.get_skeleton().get_bone_count():
					check(actor.get_skeleton().get_bone_global_pose(bone).is_finite(), key + " has finite skeletal poses")
			# Seeking exactly to the last key does not emit animation_finished;
			# exercise ordinary playback from the beginning separately.
			actor.play_technique(key, phase)
			actor.animation_player.advance(clip.length + 0.1)
			check(actor.current_action in [&"idle", &"combat_idle"], key + " recovers after playback")
		check(actor.resolver.clip_for_action(&"attack_primary") == original_primary, key + " leaves ordinary attack mapping intact")
		var effect := Effect.new()
		preview.stage.add_child(effect)
		effect.configure(key, phase, actor, target, true)
		effect.sample(effect.contact + 0.2)
		check(effect.lifetime <= Effect.MAX_LIFETIME, key + " has a bounded visual lifetime")
		var arrays := effect._mesh.surface_get_arrays(0)
		check((arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() > 3, key + " produces visible geometry")
		for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX]: check(vertex.is_finite(), key + " geometry is finite")
		effect.free()
	actor.play_technique("riposte", "counter")
	check(str(actor.animation_player.current_animation) == "Technique_Riposte", "Riposte's counter has its own parry-to-strike motion")
	# A missed strike has a swing cue, but no successful target impact.
	var missed := Effect.new()
	preview.stage.add_child(missed)
	missed.configure("shield_bash", "impact", actor, target, false)
	missed.sample(0.3)
	check((missed._mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() == 12, "a miss draws no impact geometry")
	target.free()
	missed.sample(0.4)
	missed.free()
	check(root.get_node("AppState").actors == actors_before, "preview never registers gameplay actors")
	preview.hide()
	check(not preview.is_processing() and preview.viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED, "hidden preview stops drawing and processing")
	review.free()
	await process_frame
	await check_live_dispatch()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("technique presentation: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func check_live_dispatch() -> void:
	var main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	var source := ReplicatedActor3D.new()
	var target := ReplicatedActor3D.new()
	source.set_physics_process(false)
	target.set_physics_process(false)
	main.world_root.add_child(source)
	main.world_root.add_child(target)
	target.position.x = 1.5
	main.actor_nodes[991] = source
	main.actor_nodes[992] = target
	var state := root.get_node("AppState")
	var event := {"kind": "technique_effect", "key": "shield_bash", "actor_id": 991,
		"target_id": 992, "phase": "strike", "hit": true}
	state._on_packet(212, JSON.stringify(event).to_utf8_buffer())
	check(main.world_effects.size() == 1, "a real server frame reaches the live world effect")
	main._effects_enabled = false
	state._on_packet(212, JSON.stringify(event).to_utf8_buffer())
	check(main.world_effects.size() == 1, "the effects setting suppresses technique visuals")
	main._effects_enabled = true
	event.key = "unknown_technique"
	state._on_packet(212, JSON.stringify(event).to_utf8_buffer())
	check(main.world_effects.size() == 1, "unknown technique events are ignored")
	event.key = "shield_bash"
	event.actor_id = 9999
	state._on_packet(212, JSON.stringify(event).to_utf8_buffer())
	check(main.world_effects.size() == 1, "absent source actors do not create orphan effects")
	var effect: Node = main.world_effects[0]
	main._clear_world_presentation()
	await process_frame
	check(not is_instance_valid(effect), "world teardown clears transient technique effects")
	for frame in range(4): await process_frame
	main.free()
	await process_frame

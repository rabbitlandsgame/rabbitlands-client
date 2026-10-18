extends SceneTree
const Presentation = preload("res://src/world/technique_presentation.gd")
const Icons = preload("res://src/ui/technique_icons.gd")

func _init() -> void:
	create_timer(90).timeout.connect(func(): push_error("Technique render timed out"); quit(98))
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1100, 680)
	var review = load("res://src/dev/technique_showcase.tscn").instantiate()
	root.add_child(review)
	for frame in range(6): await process_frame
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty(): output = ProjectSettings.globalize_path("res://test-artifacts/techniques")
	DirAccess.make_dir_recursive_absolute(output)
	for key: String in Icons.ORDER:
		review.select_technique(key)
		var preview = review.preview
		preview.set_process(false)
		preview.stage.process_mode = Node.PROCESS_MODE_DISABLED
		preview._process(0.86 if key in Presentation.RANGED else 0.31)
		if key == "riposte":
			for effect in preview.effects.get_children(): effect.free()
			preview._emit_cue(key, "counter", true)
		var phase := "counter" if key == "riposte" else "shot" if key in Presentation.RANGED else "strike"
		var contact: float = Presentation.contact_delay(key, phase, preview.source.position.distance_to(preview.target.position))
		preview.source.animation_player.advance(contact + 0.18)
		preview.source._advance_facing_offset(1.0)
		preview.source.combat_presentation.update_pose()
		for effect in preview.effects.get_children():
			if effect.has_method("sample"): effect.sample(contact + 0.18)
			elif effect is MissileFlight3D: effect._process(1.0)
		for frame in range(4): await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(output.path_join(key + ".png"))
	review.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("technique renders: PASS (24)")
	quit()

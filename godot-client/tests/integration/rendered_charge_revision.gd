extends SceneTree
## Samples the real offline reviewer at a fixed cadence for full-motion review.
const RATE := 30
const KEYS := ["charge", "heavy_blow", "executioners_stroke", "sunder"]

func _init() -> void:
	create_timer(90).timeout.connect(func(): push_error("Charge revision render timed out"); quit(98))
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(960, 600)
	var review = load("res://src/dev/technique_showcase.tscn").instantiate()
	root.add_child(review)
	for frame in range(4): await process_frame
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty(): output = ProjectSettings.globalize_path("res://test-artifacts/charge-revision")
	for key in KEYS:
		review.select_technique(key)
		var preview = review.preview
		preview.set_process(false)
		preview.stage.process_mode = Node.PROCESS_MODE_DISABLED
		preview.source.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		preview.target.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var folder: String = output.path_join(key)
		DirAccess.make_dir_recursive_absolute(folder)
		for sample in range(54):
			preview._process(1.0 / RATE)
			preview.source.animation_player.advance(1.0 / RATE)
			preview.target.animation_player.advance(1.0 / RATE)
			preview.source._advance_facing_offset(1.0 / RATE)
			preview.source.combat_presentation.update_pose()
			for effect in preview.effects.get_children():
				if effect.has_method("sample"): effect.sample(effect.elapsed + 1.0 / RATE)
			await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(folder.path_join("%03d.png" % sample))
	review.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("charge revision renders: PASS (216 frames)")
	quit()

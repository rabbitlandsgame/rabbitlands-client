extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1440, 960)
	var path := "res://src/dev/spell_power_showcase.tscn" if OS.get_environment("ELORIA_COMPARE_SPELL_POWER") == "1" else "res://src/dev/spell_exchange_showcase.tscn"
	var showcase := (load(path) as PackedScene).instantiate()
	showcase.family_page = int(OS.get_environment("ELORIA_SPELL_FAMILY_PAGE"))
	root.add_child(showcase)
	showcase.set_process(false)
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/spell-exchanges")
	DirAccess.make_dir_recursive_absolute(output)
	for frame: int in 5:
		await process_frame
	var captures := {9: "gather", 20: "flight", 27: "contact", 39: "dissolve"}
	var record := OS.get_environment("ELORIA_RECORD_SPELLS") == "1"
	var errors := 0
	for frame: int in 66:
		showcase.advance(1.0 / 30.0)
		await process_frame
		await RenderingServer.frame_post_draw
		if captures.has(frame) or record:
			var rendered := root.get_texture().get_image()
			if rendered == null or rendered.get_size() != Vector2i(1440, 960):
				errors += 1
				continue
			# Check the stage, not just the title, so an empty/black viewport fails.
			var low := 1.0
			var high := 0.0
			for y: int in range(120, 440, 8):
				for x: int in range(30, 700, 8):
					var luminance := rendered.get_pixel(x, y).get_luminance()
					low = minf(low, luminance)
					high = maxf(high, luminance)
			if high - low < 0.1:
				errors += 1
				push_error("Empty spell exchange stage at frame %d" % frame)
			if captures.has(frame):
				errors += int(rendered.save_png(output.path_join("spell-%s.png" % captures[frame])) != OK)
			if record:
				errors += int(rendered.save_png(output.path_join("frame-%03d.png" % frame)) != OK)
	showcase.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("rendered spell exchanges: ", "PASS" if errors == 0 else "FAIL")
	quit(errors)

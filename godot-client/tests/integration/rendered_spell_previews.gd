extends SceneTree
## Exercise selection through the real spellbook and inspect rendered motion.
var failures := 0
var output := ""

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func settle() -> void:
	for frame: int in 5:
		await process_frame

func run() -> void:
	output = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await settle()
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	var window = main.spells_window
	window.toggle()
	for sample: Array in [[0, "heal"], [68, "fire"], [70, "frost"], [10, "life-drain"],
		[69, "burst"], [46, "allies"], [8, "transmute"], [9, "recall"]]:
		window.call("_on_spell_pressed", sample[0])
		await settle()
		await create_timer(0.25).timeout
		await RenderingServer.frame_post_draw
		var preview = window.effect_preview
		var before: Image = preview.viewport.get_texture().get_image()
		if not output.is_empty():
			root.get_texture().get_image().save_png(output.path_join("spellbook-%s.png" % sample[1]))
		await create_timer(0.30).timeout
		await RenderingServer.frame_post_draw
		var after: Image = preview.viewport.get_texture().get_image()
		check(before.get_data() != after.get_data(), "%s preview must animate" % sample[1])
		var description: Label = window.description_label
		var info: Control = window.panel.find_child("SpellInfoScroll", true, false)
		check(info.get_global_rect().intersects(description.get_global_rect()),
			"%s description is visible immediately" % sample[1])
	window.call("_on_spell_pressed", 68)
	window.power_picker.value = 10
	await settle()
	await create_timer(0.3).timeout
	await RenderingServer.frame_post_draw
	if not output.is_empty():
		root.get_texture().get_image().save_png(output.path_join("spellbook-power-10.png"))
	root.size = Vector2i(960, 600)
	await settle()
	await RenderingServer.frame_post_draw
	var bounds: Rect2 = window.get_viewport_rect()
	var rect: Rect2 = window.panel.get_global_rect()
	check(rect.position.x >= 0 and rect.position.y >= 0
		and rect.end.x <= bounds.end.x - 96
		and rect.end.y < main.get_node("GameView/Quickbar").global_position.y,
		"compact spellbook fits above the bottom HUD and beside the right rail")
	check(window.panel.get_global_rect().encloses(window.effect_preview.get_global_rect()),
		"compact preview fits within the spellbook")
	if not output.is_empty():
		root.get_texture().get_image().save_png(output.path_join("spellbook-compact.png"))
	window.close()
	# Let queued UI work finish before tearing down the complete HUD.
	await settle()
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("rendered spell previews: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

extends SceneTree
const Icons := preload("res://src/ui/item_effect_icons.gd")

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 800)
	root.transparent_bg = false
	RenderingServer.set_default_clear_color(Color("071416"))
	var panel := PanelContainer.new()
	panel.position = Vector2(28, 24)
	panel.size = Vector2(1224, 752)
	var box := StyleBoxFlat.new()
	box.bg_color = Color("071416")
	box.border_color = Color("9d7951")
	box.set_border_width_all(2)
	box.set_content_margin_all(20)
	panel.add_theme_stylebox_override("panel", box)
	root.add_child(panel)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 12)
	panel.add_child(content)
	var title := Label.new()
	title.text = "Rabbit Lands · Equipment effects"
	title.add_theme_font_size_override("font_size", 26)
	title.add_theme_color_override("font_color", Color("eee3c8"))
	content.add_child(title)
	var grid := GridContainer.new()
	grid.columns = 8
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 14)
	content.add_child(grid)
	for effect_name: String in Icons.PATHS:
		var cell := VBoxContainer.new()
		cell.custom_minimum_size = Vector2(137, 145)
		grid.add_child(cell)
		var icon := TextureRect.new()
		icon.texture = Icons.texture(effect_name)
		icon.custom_minimum_size = Vector2(88, 88)
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		cell.add_child(icon)
		var label := Label.new()
		label.text = effect_name
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.add_theme_font_size_override("font_size", 14)
		label.add_theme_color_override("font_color", Color("eee3c8"))
		cell.add_child(label)
	for _frame: int in range(5): await process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://test-artifacts/equipment-instances"))
	root.get_texture().get_image().save_png("res://test-artifacts/equipment-instances/effect-icons.png")
	print("Effect icon gallery: 32 glyphs rendered")
	quit()

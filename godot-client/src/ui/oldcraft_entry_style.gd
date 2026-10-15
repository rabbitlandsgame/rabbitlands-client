class_name OldcraftEntryStyle
extends RefCounted
## Low-cost entry-screen styling inspired by Oldcraft's fantasy materials and
## open, scenic login composition.
##
## The screens keep Eloria's logo, world painting, controls and navigation.
## This helper supplies the visual language: a restrained floating login card,
## warm brass edges, burgundy action buttons, inset fields and a moonlit
## preview stage. Character creation keeps its heavier carved-stone treatment.
## Both screens exist only during entry and add no gameplay or crowd cost.

## Sampled from the shipped reference UI rather than eyeballed from a concept:
## brass #F4C542/#B88A3B, carved stone #1E1E22/#333338, parchment
## #E9D5A8, oxblood #8E1B12 and warm type #F5F0E0.
const GOLD := Color(0.957, 0.773, 0.259, 1.0)
const GOLD_DARK := Color(0.722, 0.541, 0.231, 1.0)
const GOLD_BRIGHT := Color(1.0, 0.86, 0.48, 1.0)
const PARCHMENT := Color(0.914, 0.835, 0.659, 1.0)
const WARM_TEXT := Color(0.961, 0.941, 0.878, 1.0)
const MUTED := Color(0.69, 0.65, 0.58, 1.0)
const STONE := Color(0.118, 0.118, 0.133, 0.94)
const STONE_RAISED := Color(0.20, 0.20, 0.22, 0.96)
const FIELD := Color(0.025, 0.026, 0.032, 0.96)
const BURGUNDY := Color(0.557, 0.106, 0.071, 0.98)
const BURGUNDY_HOVER := Color(0.722, 0.169, 0.102, 1.0)
const BURGUNDY_PRESSED := Color(0.31, 0.045, 0.028, 1.0)
const PREVIEW_SKY := Color(0.018, 0.035, 0.075, 0.0)
const STYLE_META := &"eloria_oldcraft_entry_style"


static func _flat_box(background: Color, border: Color, width: int,
		corner: int, margin: float) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = background
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(corner)
	box.set_content_margin_all(margin)
	return box


static func apply(main: Control) -> void:
	if main == null:
		return
	_style_panel(main.get_node_or_null("%LoginPanel") as PanelContainer, false)
	_style_panel(main.get_node_or_null("%CreationPanel") as PanelContainer, true)
	_style_controls(main.get_node_or_null("%LoginPanel") as Control)
	_style_controls(main.get_node_or_null("%CreationPanel") as Control)
	_style_login_layout(main)
	_style_creation_layout(main)
	_style_titles(main)
	_style_preview(main)
	main.set_meta(STYLE_META, true)


static func _style_panel(panel: PanelContainer, wide: bool) -> void:
	if panel == null:
		return
	var frame := _flat_box(STONE, GOLD_DARK, 5, 4,
		18.0 if wide else 22.0)
	frame.shadow_color = Color(0.0, 0.0, 0.0, 0.78)
	frame.shadow_size = 12
	frame.shadow_offset = Vector2(0.0, 5.0)
	panel.add_theme_stylebox_override("panel", frame)
	# A thin brass inner edge catches the same warm light as the title and
	# buttons without needing a nine-patch texture.
	panel.add_theme_constant_override("outline_size", 1)


static func _style_controls(root: Control) -> void:
	if root == null:
		return
	var button_normal := _flat_box(BURGUNDY, GOLD_DARK,
		2, 4, 7.0)
	var button_hover := _flat_box(BURGUNDY_HOVER, GOLD_BRIGHT, 2, 4, 7.0)
	var button_pressed := _flat_box(BURGUNDY_PRESSED,
		Color(0.72, 0.48, 0.16, 1.0), 2, 4, 7.0)
	var button_disabled := _flat_box(Color(0.08, 0.065, 0.06, 0.86),
		Color(0.25, 0.22, 0.18, 0.8), 1, 4, 7.0)
	for value: Node in root.find_children("*", "Button", true, false):
		var button := value as Button
		button.add_theme_stylebox_override("normal", button_normal)
		button.add_theme_stylebox_override("hover", button_hover)
		button.add_theme_stylebox_override("pressed", button_pressed)
		button.add_theme_stylebox_override("hover_pressed", button_pressed)
		button.add_theme_stylebox_override("focus", button_hover)
		button.add_theme_stylebox_override("disabled", button_disabled)
		button.add_theme_color_override("font_color", WARM_TEXT)
		button.add_theme_color_override("font_hover_color", GOLD_BRIGHT)
		button.add_theme_color_override("font_pressed_color", GOLD)
		button.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.9))
		button.add_theme_constant_override("outline_size", 2)
		button.custom_minimum_size.y = maxf(button.custom_minimum_size.y, 36.0)
	var field_normal := _flat_box(FIELD, GOLD_DARK,
		2, 3, 8.0)
	var field_focus := _flat_box(Color(0.018, 0.019, 0.026, 1.0), GOLD,
		2, 3, 8.0)
	for value: Node in root.find_children("*", "LineEdit", true, false):
		var field := value as LineEdit
		field.add_theme_stylebox_override("normal", field_normal)
		field.add_theme_stylebox_override("focus", field_focus)
		field.add_theme_color_override("font_color", WARM_TEXT)
		field.add_theme_color_override("font_placeholder_color", MUTED)
		field.add_theme_color_override("caret_color", GOLD_BRIGHT)
		field.custom_minimum_size.y = maxf(field.custom_minimum_size.y, 36.0)
	for value: Node in root.find_children("*", "CheckBox", true, false):
		var check := value as CheckBox
		check.add_theme_color_override("font_color", WARM_TEXT)
		check.add_theme_color_override("font_hover_color", GOLD_BRIGHT)
	for value: Node in root.find_children("*", "Label", true, false):
		var label := value as Label
		label.add_theme_color_override("font_color", WARM_TEXT)
		label.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.95))
		label.add_theme_constant_override("outline_size", 2)


static func _style_login_layout(main: Control) -> void:
	var login_panel := main.get_node_or_null("%LoginPanel") as PanelContainer
	if login_panel != null:
		# The scenery remains the hero. This is intentionally closer to a smoky
		# glass control cluster than a modal window: enough contrast for the form,
		# but no large slab competing with the castle painting.
		var floating_card := _flat_box(Color(0.025, 0.028, 0.037, 0.64),
			Color(GOLD_DARK, 0.72), 2, 16, 12.0)
		floating_card.shadow_color = Color(0.0, 0.0, 0.0, 0.48)
		floating_card.shadow_size = 8
		floating_card.shadow_offset = Vector2(0.0, 4.0)
		login_panel.add_theme_stylebox_override("panel", floating_card)
	var content := main.get_node_or_null("LoginPanel/Content") as VBoxContainer
	if content != null:
		content.add_theme_constant_override("separation", 4)
	var field_normal := _flat_box(Color(0.018, 0.021, 0.028, 0.76),
		Color(GOLD_DARK, 0.82), 1, 8, 7.0)
	var field_focus := _flat_box(Color(0.014, 0.017, 0.024, 0.91),
		GOLD, 2, 8, 7.0)
	for value: Node in login_panel.find_children("*", "LineEdit", true, false):
		var field := value as LineEdit
		field.add_theme_stylebox_override("normal", field_normal)
		field.add_theme_stylebox_override("focus", field_focus)
		field.custom_minimum_size.y = maxf(field.custom_minimum_size.y, 36.0)
	var secure := main.get_node_or_null("%Secure") as CheckBox
	if secure != null:
		# Connection security is a quiet utility choice, not a destructive red
		# action. A faint translucent row leaves the check glyph clear without
		# competing with Log In.
		var secure_normal := _flat_box(Color(0.02, 0.024, 0.032, 0.20),
			Color(GOLD_DARK, 0.28), 1, 8, 4.0)
		var secure_hover := _flat_box(Color(0.055, 0.058, 0.07, 0.42),
			Color(GOLD_DARK, 0.56), 1, 8, 4.0)
		var secure_disabled := _flat_box(Color(0.02, 0.022, 0.028, 0.12),
			Color(GOLD_DARK, 0.18), 1, 8, 4.0)
		secure.add_theme_stylebox_override("normal", secure_normal)
		secure.add_theme_stylebox_override("hover", secure_hover)
		secure.add_theme_stylebox_override("pressed", secure_hover)
		secure.add_theme_stylebox_override("hover_pressed", secure_hover)
		secure.add_theme_stylebox_override("focus", secure_hover)
		secure.add_theme_stylebox_override("disabled", secure_disabled)
		secure.add_theme_color_override("font_color", WARM_TEXT)
		secure.add_theme_color_override("font_hover_color", GOLD_BRIGHT)
		secure.custom_minimum_size.y = maxf(secure.custom_minimum_size.y, 36.0)
	var secondary_normal := _flat_box(Color(0.045, 0.046, 0.058, 0.48),
		Color(GOLD_DARK, 0.76), 1, 9, 6.0)
	var secondary_hover := _flat_box(Color(0.12, 0.115, 0.12, 0.82),
		GOLD_BRIGHT, 2, 9, 6.0)
	var secondary_pressed := _flat_box(Color(0.035, 0.036, 0.045, 0.88),
		Color(0.72, 0.48, 0.16, 1.0), 2, 9, 6.0)
	var secondary_disabled := _flat_box(Color(0.025, 0.027, 0.034, 0.34),
		Color(GOLD_DARK, 0.30), 1, 9, 6.0)
	for node_name: StringName in [&"Connect", &"NewCharacter"]:
		var secondary := main.get_node_or_null("%" + str(node_name)) as Button
		if secondary == null:
			continue
		secondary.add_theme_stylebox_override("normal", secondary_normal)
		secondary.add_theme_stylebox_override("hover", secondary_hover)
		secondary.add_theme_stylebox_override("pressed", secondary_pressed)
		secondary.add_theme_stylebox_override("hover_pressed", secondary_pressed)
		secondary.add_theme_stylebox_override("focus", secondary_hover)
		secondary.add_theme_stylebox_override("disabled", secondary_disabled)
		secondary.add_theme_color_override("font_color", GOLD)
		secondary.custom_minimum_size.y = maxf(
			secondary.custom_minimum_size.y, 36.0)
	var login := main.get_node_or_null("%Login") as Button
	if login != null:
		var login_hover := _flat_box(BURGUNDY_HOVER, GOLD_BRIGHT, 2, 9, 6.0)
		var login_pressed := _flat_box(BURGUNDY_PRESSED,
			Color(0.72, 0.48, 0.16, 1.0), 2, 9, 6.0)
		var login_disabled := _flat_box(Color(0.12, 0.055, 0.045, 0.48),
			Color(GOLD_DARK, 0.34), 1, 9, 6.0)
		login.add_theme_stylebox_override("normal", _flat_box(
			Color(BURGUNDY, 0.92), Color(GOLD_DARK, 0.92), 2, 9, 6.0))
		login.add_theme_stylebox_override("hover", login_hover)
		login.add_theme_stylebox_override("pressed", login_pressed)
		login.add_theme_stylebox_override("hover_pressed", login_pressed)
		login.add_theme_stylebox_override("focus", login_hover)
		login.add_theme_stylebox_override("disabled", login_disabled)
		login.custom_minimum_size.y = maxf(login.custom_minimum_size.y, 36.0)
	var port := main.get_node_or_null("%Port") as SpinBox
	if port != null:
		var port_field := port.get_line_edit()
		port_field.add_theme_stylebox_override("normal", field_normal)
		port_field.add_theme_stylebox_override("focus", field_focus)
		port_field.add_theme_color_override("font_color", WARM_TEXT)
		port_field.add_theme_color_override("caret_color", GOLD_BRIGHT)
		port_field.custom_minimum_size.y = maxf(
			port_field.custom_minimum_size.y, 36.0)
		port.custom_minimum_size.y = maxf(port.custom_minimum_size.y, 36.0)
	var logo := main.get_node_or_null("%LoginLogo") as TextureRect
	if logo != null:
		# The crest is an independent corner mark, not part of the form. It remains
		# mouse-transparent so it never creates a dead region over the backdrop.
		logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
		logo.modulate = Color(1.0, 0.98, 0.91, 0.96)


static func _style_creation_layout(main: Control) -> void:
	var rail := main.get_node_or_null("%ClassRail") as PanelContainer
	if rail != null:
		var rail_box := _flat_box(Color(0.055, 0.06, 0.075, 0.94),
			GOLD_DARK, 3, 4, 10.0)
		rail_box.shadow_color = Color(0.0, 0.0, 0.0, 0.72)
		rail_box.shadow_size = 8
		rail.add_theme_stylebox_override("panel", rail_box)
	# Toggle buttons keep their pressed style after selection. A broad bright
	# brass edge makes the current class legible even when two icon silhouettes
	# have similar values or the player is using a dim display.
	var class_normal := _flat_box(BURGUNDY, GOLD_DARK, 2, 4, 5.0)
	var class_hover := _flat_box(BURGUNDY_HOVER, GOLD_BRIGHT, 3, 4, 5.0)
	var class_selected := _flat_box(Color(0.36, 0.055, 0.03, 1.0),
		GOLD_BRIGHT, 4, 4, 5.0)
	for node_name: StringName in [&"ClassChoice0", &"ClassChoice1",
			&"ClassChoice2", &"ClassChoice3"]:
		var class_button := main.get_node_or_null("%" + str(node_name)) as Button
		if class_button == null:
			continue
		class_button.add_theme_stylebox_override("normal", class_normal)
		class_button.add_theme_stylebox_override("hover", class_hover)
		class_button.add_theme_stylebox_override("pressed", class_selected)
		class_button.add_theme_stylebox_override("hover_pressed", class_selected)
	var form_panel := main.get_node_or_null("%FormPanel") as PanelContainer
	if form_panel != null:
		var form_frame := _flat_box(Color(0.055, 0.06, 0.075, 0.96),
			GOLD_DARK, 3, 4, 24.0)
		form_frame.shadow_color = Color(0.0, 0.0, 0.0, 0.78)
		form_frame.shadow_size = 10
		form_frame.shadow_offset = Vector2(0.0, 4.0)
		form_panel.add_theme_stylebox_override("panel", form_frame)
		for value: Node in form_panel.find_children("*", "Label", true, false):
			var label := value as Label
			label.add_theme_color_override("font_color", Color(0.22, 0.14, 0.07, 1.0))
			label.add_theme_color_override("font_outline_color", Color.TRANSPARENT)
			label.add_theme_constant_override("outline_size", 0)
	var parchment := main.get_node_or_null("%FormParchment") as Panel
	if parchment != null:
		# Expanding the painted insert beyond the shared content rectangle gives
		# the form a true inset margin without changing any established node path.
		var parchment_box := _flat_box(Color(PARCHMENT, 0.975),
			Color(0.43, 0.26, 0.095, 1.0), 2, 2, 0.0)
		parchment_box.expand_margin_left = 10.0
		parchment_box.expand_margin_top = 10.0
		parchment_box.expand_margin_right = 10.0
		parchment_box.expand_margin_bottom = 10.0
		parchment.add_theme_stylebox_override("panel", parchment_box)
	var option_normal := _flat_box(Color(0.055, 0.047, 0.042, 0.98),
		GOLD_DARK, 2, 3, 6.0)
	var option_hover := _flat_box(Color(0.09, 0.072, 0.054, 1.0),
		GOLD_BRIGHT, 2, 3, 6.0)
	for node_name: StringName in [&"CreateRace", &"CreateGender", &"CreateSkin",
			&"CreateHair", &"CreateEyes", &"CreateHairColor", &"CreateShirt",
			&"CreatePants", &"CreateBoots"]:
		var option := main.get_node_or_null("%" + str(node_name)) as OptionButton
		if option == null:
			continue
		option.add_theme_stylebox_override("normal", option_normal)
		option.add_theme_stylebox_override("hover", option_hover)
		option.add_theme_stylebox_override("pressed", option_hover)
		option.add_theme_stylebox_override("focus", option_hover)
		option.add_theme_color_override("font_color", WARM_TEXT)
		option.add_theme_color_override("font_hover_color", GOLD_BRIGHT)
	var randomize := main.get_node_or_null("%RandomizeAppearance") as Button
	if randomize != null:
		randomize.add_theme_stylebox_override("normal", _flat_box(
			Color(0.105, 0.095, 0.09, 0.98), GOLD_DARK, 2, 4, 6.0))
		randomize.add_theme_stylebox_override("hover", _flat_box(
			Color(0.16, 0.125, 0.08, 1.0), GOLD_BRIGHT, 2, 4, 6.0))
		randomize.add_theme_color_override("font_color", GOLD_BRIGHT)
	for path: String in [
			"CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AccountSection",
			"CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/IdentitySection",
			"CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceSection"]:
		var section := main.get_node_or_null(path) as Label
		if section == null:
			continue
		section.add_theme_color_override("font_color", BURGUNDY_PRESSED)
		section.add_theme_font_size_override("font_size", 12)
	var class_header := main.get_node_or_null("CreationPanel/Columns/ClassRail/ClassContent/ClassHeader") as Label
	if class_header != null:
		class_header.add_theme_color_override("font_color", GOLD_BRIGHT)
	var class_title := main.get_node_or_null("%ClassTitle") as Label
	if class_title != null:
		class_title.add_theme_color_override("font_color", GOLD_BRIGHT)
	var class_tagline := main.get_node_or_null("%ClassTagline") as Label
	if class_tagline != null:
		class_tagline.add_theme_color_override("font_color", GOLD)


static func _style_titles(main: Control) -> void:
	var login_title := main.get_node_or_null("LoginPanel/Content/Subtitle") as Label
	if login_title != null:
		login_title.text = "ENTER THE WORLD OF ELORIA"
		login_title.add_theme_color_override("font_color", GOLD_BRIGHT)
		login_title.add_theme_font_size_override("font_size", 18)
		login_title.add_theme_constant_override("outline_size", 3)
	var creation_title := main.get_node_or_null(
		"CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/Title") as Label
	if creation_title != null:
		creation_title.text = "FORGE YOUR HERO"
		creation_title.add_theme_color_override("font_color", BURGUNDY_PRESSED)
		creation_title.add_theme_font_size_override("font_size", 27)
		creation_title.add_theme_constant_override("outline_size", 0)
	var status := main.get_node_or_null("%Status") as Label
	if status != null:
		status.add_theme_color_override("font_color", MUTED)
	var create_status := main.get_node_or_null("%CreateStatus") as Label
	if create_status != null:
		create_status.add_theme_color_override("font_color", Color(0.31, 0.22, 0.13, 1.0))


static func _style_preview(main: Control) -> void:
	var preview_root := main.get_node_or_null("%PreviewRoot") as Node3D
	var world_environment := main.get_node_or_null(
		"CreationPanel/Columns/CharacterPreview/Viewport/PreviewRoot/PreviewEnvironment") \
		as WorldEnvironment
	if world_environment != null and world_environment.environment != null:
		world_environment.environment.background_mode = Environment.BG_COLOR
		world_environment.environment.background_color = PREVIEW_SKY
		world_environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		world_environment.environment.ambient_light_color = Color(0.34, 0.42, 0.56, 1.0)
		world_environment.environment.ambient_light_energy = 0.95
	var preview_viewport := main.get_node_or_null(
		"CreationPanel/Columns/CharacterPreview/Viewport") as SubViewport
	if preview_viewport != null:
		preview_viewport.transparent_bg = true
	var key := main.get_node_or_null("%KeyLight") as DirectionalLight3D
	if key != null:
		key.light_color = Color(1.0, 0.78, 0.48, 1.0)
		key.light_energy = 1.42
	var fill := main.get_node_or_null("%FillLight") as DirectionalLight3D
	if fill != null:
		fill.light_color = Color(0.22, 0.48, 0.78, 1.0)
		fill.light_energy = 0.52
	var rim := main.get_node_or_null("%RimLight") as DirectionalLight3D
	if rim != null:
		rim.light_color = Color(0.18, 0.72, 0.68, 1.0)
		rim.light_energy = 0.5
	var ground := main.get_node_or_null(
		"CreationPanel/Columns/CharacterPreview/Viewport/PreviewRoot/PreviewGround") \
		as MeshInstance3D
	if ground != null and ground.mesh != null:
		var ground_material := ground.get_active_material(0) as BaseMaterial3D
		if ground_material != null:
			ground_material.albedo_color = Color(0.13, 0.18, 0.19, 1.0)
			ground_material.roughness = 0.92
			ground_material.metallic_specular = 0.18
	if preview_root == null or preview_root.get_node_or_null("OldcraftStage") != null:
		return
	var stage := Node3D.new()
	stage.name = "OldcraftStage"
	preview_root.add_child(stage)
	_add_cylinder(stage, "StonePlinth", 0.95, 0.86, 0.14, -0.12,
		Color(0.075, 0.085, 0.09, 1.0), 24)
	_add_cylinder(stage, "BrassPlinthRing", 0.84, 0.84, 0.025, -0.035,
		Color(0.42, 0.29, 0.105, 1.0), 48, 0.58)


static func _material(color: Color, metallic := 0.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.86
	material.metallic = metallic
	material.metallic_specular = 0.24
	return material


static func _add_cylinder(parent: Node3D, node_name: String, top: float,
		bottom: float, height: float, y: float, color: Color, segments: int,
		metallic := 0.0) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = top
	mesh.bottom_radius = bottom
	mesh.height = height
	mesh.radial_segments = segments
	mesh.material = _material(color, metallic)
	var instance := MeshInstance3D.new()
	instance.name = node_name
	instance.position.y = y
	instance.mesh = mesh
	parent.add_child(instance)

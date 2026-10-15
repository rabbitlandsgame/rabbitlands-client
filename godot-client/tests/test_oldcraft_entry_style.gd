extends SceneTree

const EntryStyle := preload("res://src/ui/oldcraft_entry_style.gd")

var failures := 0
var checks := 0


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)


func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	EntryStyle.apply(main)
	var login := main.get_node("%LoginPanel") as PanelContainer
	var creation := main.get_node("%CreationPanel") as PanelContainer
	var login_frame := login.get_theme_stylebox("panel") as StyleBoxFlat
	var creation_frame := creation.get_theme_stylebox("panel") as StyleBoxFlat
	_expect(login_frame != null and login_frame.border_width_left == 2 and
		login_frame.bg_color.a < 0.7 and login_frame.corner_radius_top_left >= 14,
		"login uses a restrained translucent floating card")
	_expect(creation_frame != null and creation_frame.border_color.is_equal_approx(
		EntryStyle.GOLD_DARK), "creation uses the same forged frame")
	var rail_frame := (main.get_node("%ClassRail") as PanelContainer).get_theme_stylebox(
		"panel") as StyleBoxFlat
	_expect(rail_frame != null and rail_frame.border_width_left == 3,
		"creation class icons sit in a compact stone rail")
	var selected_class_frame := (main.get_node("%ClassChoice0") as Button).get_theme_stylebox(
		"pressed") as StyleBoxFlat
	_expect(selected_class_frame != null and selected_class_frame.border_width_left == 4 and
		selected_class_frame.border_color.is_equal_approx(EntryStyle.GOLD_BRIGHT),
		"selected class gets an unmistakable bright brass frame")
	var form_frame := (main.get_node("%FormPanel") as PanelContainer).get_theme_stylebox(
		"panel") as StyleBoxFlat
	_expect(form_frame != null and form_frame.bg_color.r < 0.1 and
		form_frame.border_color.is_equal_approx(EntryStyle.GOLD_DARK),
		"creation form echoes the class rail with carved stone and brass")
	var parchment_frame := (main.get_node("%FormParchment") as Panel).get_theme_stylebox(
		"panel") as StyleBoxFlat
	_expect(parchment_frame != null and parchment_frame.bg_color.is_equal_approx(
		Color(EntryStyle.PARCHMENT, 0.975)) and parchment_frame.expand_margin_left >= 10.0,
		"creation form keeps an inset parchment writing surface")
	var randomize := main.get_node_or_null("%RandomizeAppearance") as Button
	_expect(randomize != null and randomize.text == "Randomize Appearance" and
		randomize.get_theme_color("font_color").is_equal_approx(EntryStyle.GOLD_BRIGHT),
		"creation exposes a clearly styled appearance randomizer")
	_expect(randomize != null and randomize.pressed.is_connected(
		Callable(main, "_on_randomize_creation_pressed")),
		"appearance randomizer is wired to the creation controller")
	var login_button := main.get_node("%Login") as Button
	var normal := login_button.get_theme_stylebox("normal") as StyleBoxFlat
	_expect(normal != null and normal.bg_color.r > normal.bg_color.g * 4.0,
		"primary actions use Oldcraft burgundy")
	_expect(login_button.get_theme_color("font_color").r > 0.85,
		"action text stays warm and readable")
	_expect(login_button.custom_minimum_size.y >= 36.0 and
		(login_button.get_theme_stylebox("pressed") as StyleBoxFlat).
		corner_radius_top_left >= 8 and
		(login_button.get_theme_stylebox("disabled") as StyleBoxFlat).
		corner_radius_top_left >= 8,
		"primary action keeps an accessible hit area and rounded states")
	var secure := main.get_node("%Secure") as CheckBox
	var secure_normal := secure.get_theme_stylebox("normal") as StyleBoxFlat
	_expect(secure_normal != null and secure_normal.bg_color.a <= 0.22 and
		secure_normal.bg_color.r < 0.1 and secure.custom_minimum_size.y >= 36.0,
		"TLS choice is a subtle translucent utility row")
	var new_character := main.get_node("%NewCharacter") as Button
	_expect(new_character.custom_minimum_size.y >= 36.0 and
		(new_character.get_theme_stylebox("disabled") as StyleBoxFlat).
		corner_radius_top_left >= 8,
		"secondary actions keep accessible rounded disabled states")
	var username := main.get_node("%Username") as LineEdit
	var username_style := username.get_theme_stylebox("normal") as StyleBoxFlat
	_expect(username_style.border_width_left == 1 and
		username_style.corner_radius_top_left >= 8,
		"entry fields are subtly inset and rounded")
	_expect((main.get_node("LoginPanel/Content/Subtitle") as Label).text ==
		"ENTER THE WORLD OF ELORIA", "Eloria identity is retained")
	_expect(is_equal_approx(login.anchor_left, 0.77) and
		is_equal_approx(login.anchor_right, 0.77) and login.size.x <= 380.0 and
		login.size.y <= 440.0 and
		login.size.x * login.size.y < float(root.size.x * root.size.y) * 0.18,
		"compact login card preserves most of the scenic painting")
	var login_logo := main.get_node("%LoginLogo") as TextureRect
	_expect(login_logo.get_parent() == main and login_logo.position.x <= 32.0 and
		login_logo.position.y <= 26.0 and login_logo.size.x <= 300.0,
		"Eloria crest floats independently in the upper-left corner")
	_expect(login_logo.mouse_filter == Control.MOUSE_FILTER_IGNORE,
		"corner crest cannot intercept login-screen input")
	var login_material := (main.get_node("%LoginBackground") as TextureRect).material \
		as ShaderMaterial
	_expect(login_material != null and float(login_material.get_shader_parameter(
		"animation_strength")) > 0.0,
		"login painting has a low-cost adjustable ambient motion pass")
	var login_background := main.get_node("%LoginBackground") as TextureRect
	main.call("_set_login_screen_visible", false)
	_expect(not login.visible and not login_background.visible and not login_logo.visible,
		"leaving login removes the backdrop and corner crest from the draw pass")
	main.call("_set_login_screen_visible", true)
	_expect(login.visible and login_background.visible and login_logo.visible,
		"returning to login restores the card, crest and painted backdrop together")
	login.hide()
	_expect(not login_logo.visible,
		"directly hiding the detached login card also hides its corner crest")
	login.show()
	_expect(login_logo.visible,
		"directly restoring the login card also restores its corner crest")
	if not LookProfile.quality_forced():
		var saved_quality := LookProfile.player_quality()
		for quality_and_strength: Array in [
				[LookProfile.Quality.LOW, 0.0],
				[LookProfile.Quality.MEDIUM, 0.55],
				[LookProfile.Quality.HIGH, 1.0]]:
			LookProfile.set_player_quality(int(quality_and_strength[0]))
			main.call("_apply_login_backdrop_quality")
			_expect(is_equal_approx(float(login_material.get_shader_parameter(
				"animation_strength")), float(quality_and_strength[1])),
				"login motion follows the shared Low / Medium / High quality setting")
		LookProfile.set_player_quality(saved_quality)
		main.call("_apply_login_backdrop_quality")
	var environment := (main.get_node(
		"CreationPanel/Columns/CharacterPreview/Viewport/PreviewRoot/PreviewEnvironment") \
		as WorldEnvironment).environment
	_expect(environment.background_color.is_equal_approx(EntryStyle.PREVIEW_SKY),
		"creation preview keeps transparent moonlit ambient lighting")
	_expect((main.get_node(
		"CreationPanel/Columns/CharacterPreview/Viewport") as SubViewport).transparent_bg,
		"live character is composited over the painted stage")
	_expect(main.get_node_or_null("%CreationBackdrop") is TextureRect and
		main.get_node_or_null("%ClassChoice3") is Button,
		"creation exposes a scenic backdrop and four-class icon rail")
	var stage := main.get_node_or_null("%PreviewRoot/OldcraftStage")
	_expect(stage != null and stage.get_child_count() == 2,
		"creation preview has a lightweight two-piece plinth")
	EntryStyle.apply(main)
	_expect((main.get_node("%PreviewRoot/OldcraftStage") as Node).get_child_count() == 2,
		"re-applying entry style does not duplicate stage geometry")
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	print("oldcraft entry style: %s (%d checks)" % [
		"PASS" if failures == 0 else "FAIL", checks])
	quit(1 if failures else 0)

extends SceneTree
const Presets := preload("res://src/ui/hud_presets.gd")
const FadeShader := preload("res://src/ui/chat_soft_fade.gdshader")
const FOLDER := "res://test-artifacts/chat-opacity"
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")
func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
func frames(count := 4) -> void:
	for index: int in count: await process_frame

func opacity_control(workspace: Control) -> SpinBox:
	for row: Control in workspace.details.get_children():
		if row.get_meta("option_caption", "") == "Background opacity": return row.get_child(1)
	return null

func run() -> void:
	create_timer(120).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	var old := Presets.preset("adventure")
	old.erase("chat_opacity_version")
	old.parts.chat.background_color = Color(0.2, 0.3, 0.4, 0.5)
	old.chat_windows.chat.options.background_opacity = 0.8
	old.parts.system_chat.background_color.a = 0.6
	old.chat_windows.system_chat.options.background_opacity = 0.25
	var migrated := Presets.normalise(old)
	expect(is_equal_approx(migrated.chat_windows.chat.options.background_opacity, 0.4)
		and is_equal_approx(migrated.parts.chat.background_color.a, 0.4), "old multiplied chat opacity migrates to one equivalent value")
	expect(is_equal_approx(migrated.chat_windows.system_chat.options.background_opacity, 0.15), "System opacity migrates independently")
	expect(Presets.normalise(migrated) == migrated, "repeated normalization cannot multiply opacity again")
	var profile := Presets.new()
	profile.custom["custom_old"] = {"name":"Older design", "layout":old}
	profile.builtin_overrides.adventure = old
	profile.save_file(FOLDER.path_join("migration.cfg"))
	var reloaded := Presets.new()
	reloaded.load_file(FOLDER.path_join("migration.cfg"))
	reloaded.select("custom_old")
	expect(is_equal_approx(reloaded.working.parts.chat.background_color.a, 0.4), "older custom designs migrate when loaded")
	reloaded.select("adventure")
	expect(is_equal_approx(reloaded.working.parts.chat.background_color.a, 0.4), "older edited built-in designs migrate when loaded")
	var path := FOLDER.path_join("settings.cfg")
	ConfigFile.new().save(path)
	root.size = Vector2i(1440, 900)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = path
	root.add_child(main)
	await frames(8)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var w: Control = main.hud_workspace
	w.open_editor()
	for key: String in ["chat", "system_chat"]:
		w.select_component(key)
		var duplicates := 0
		for row: Control in w.details.get_children():
			if row.get_meta("option_caption", "") in ["Background opacity", "Backdrop opacity"]: duplicates += 1
		expect(duplicates == 1, key + " has one opacity percentage in the editor")
		var control := opacity_control(w)
		control.value = 100
		await frames()
		var material: ShaderMaterial = w.parts[key]._fade.material
		expect(is_equal_approx(w.parts[key].options.background_opacity, 1.0)
			and is_equal_approx(w.model.working.parts[key].background_color.a, 1.0)
			and is_equal_approx(material.get_shader_parameter("opacity"), 1.0)
			and is_equal_approx((material.get_shader_parameter("backdrop_color") as Color).a, 1.0), key + " reaches full opacity without a second multiplier")
		expect(w.model.working.parts[key].show_background, key + " opacity enables a previously hidden HUD background")
		control.value = 50
		expect(is_equal_approx(w.parts[key].options.background_opacity, 0.5), key + " 50 percent means 50 percent")
		await create_timer(0.45).timeout
		w.change_frame_color(key, "background_color", Color(0.2, 0.3, 0.4, 0.25))
		expect(is_equal_approx(control.value, 25) and is_equal_approx(w.parts[key].options.background_opacity, 0.25), key + " color picker alpha updates the same percentage")
		w.undo_edit()
		expect(is_equal_approx(w.parts[key].options.background_opacity, 0.5), key + " Undo restores the shared opacity")
		w.redo_edit()
		expect(is_equal_approx(w.parts[key].options.background_opacity, 0.25), key + " Redo restores the shared opacity")
		opacity_control(w).value = 0
		expect(is_zero_approx(w.parts[key].options.background_opacity), key + " can also become fully transparent")
		opacity_control(w).value = 100
	w.preset_name.text = "Opaque chat"
	w.save_custom(false)
	var custom: String = w.model.active
	w.commit_and_close()
	for key: String in ["chat", "system_chat"]:
		var setting: SpinBox = main.settings_window.panel.find_child(key + "_background_opacity", true, false)
		expect(is_equal_approx(setting.value, 100) and is_equal_approx(setting.max_value, 100), key + " Chat settings displays the same percentage")
		setting.value = 65
		expect(is_equal_approx(w.parts[key].options.background_opacity, 0.65)
			and is_equal_approx(w.model.working.parts[key].background_color.a, 0.65), key + " Chat settings edits the same underlying opacity")
	w.open_editor()
	w.select_component("chat")
	expect(is_equal_approx(opacity_control(w).value, 65), "reopening the editor reflects the Chat settings change")
	opacity_control(w).value = 10
	w.cancel_edit()
	expect(is_equal_approx(main.chat_hud.options.background_opacity, 0.65), "Cancel restores the shared opacity")
	w.choose_preset("adventure", true)
	w.choose_preset(custom)
	expect(is_equal_approx(main.chat_hud.options.background_opacity, 1.0)
		and is_equal_approx(main.system_chat_hud.options.background_opacity, 1.0), "the saved custom copy retains both opaque windows")
	w.commit()
	var saved := Presets.new()
	saved.load_file(path)
	expect(is_equal_approx(saved.working.parts.chat.background_color.a, 1.0)
		and is_equal_approx(saved.working.chat_windows.system_chat.options.background_opacity, 1.0), "full opacity survives saving and reloading")
	for id: String in Presets.BUILT_INS:
		w.choose_preset(id, true)
		w.open_editor()
		for key: String in ["chat", "system_chat"]:
			w.select_component(key)
			opacity_control(w).value = 100
			var material: ShaderMaterial = w.parts[key]._fade.material
			expect(is_equal_approx(material.get_shader_parameter("opacity"), 1.0)
				and is_equal_approx((material.get_shader_parameter("backdrop_color") as Color).a, 1.0), id + " supports fully opaque " + key)
		w.cancel_edit()
	main.queue_free()
	await frames()
	Input.set_custom_mouse_cursor(null, Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_IBEAM)
	(load("res://src/ui/hud_medallion.gd") as GDScript)._textures.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._cache.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._tinted.clear()
	(load("res://src/ui/technique_icons.gd") as GDScript)._cache.clear()
	if DisplayServer.get_name() != "headless": await check_rendered_alpha()
	print("CHAT OPACITY: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)

func check_rendered_alpha() -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(128, 96)
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var rect := ColorRect.new()
	rect.size = viewport.size
	var material := ShaderMaterial.new()
	material.shader = FadeShader
	material.set_shader_parameter("panel_width", 128.0)
	material.set_shader_parameter("panel_height", 96.0)
	material.set_shader_parameter("backdrop_color", Color(0.2, 0.3, 0.4, 1))
	rect.material = material
	viewport.add_child(rect)
	for amount: float in [0.0, 0.5, 1.0]:
		material.set_shader_parameter("opacity", amount)
		await frames()
		await RenderingServer.frame_post_draw
		var image := viewport.get_texture().get_image()
		expect(absf(image.get_pixel(64, 48).a - amount) < 0.01, "rendered center alpha matches %d percent" % roundi(amount * 100))
		if amount == 1:
			for point: Vector2i in [Vector2i.ZERO, Vector2i(127,0), Vector2i(0,95), Vector2i(127,95)]:
				expect(image.get_pixelv(point).a > 0.99, "100 percent also fills corner %s" % point)
		elif amount == 0.5:
			expect(image.get_pixel(0,0).a < 0.01, "partially transparent windows retain feathered edges")
	viewport.queue_free()
	await frames()

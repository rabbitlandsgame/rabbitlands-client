extends SceneTree
## Focused palette, persistence and reactive control checks. Uses an isolated
## settings file and does not require the world loader or a server connection.
const Colors := preload("res://src/ui/text_colors.gd")
const Settings := preload("res://src/ui/settings_window.gd")
const PATH := "res://test-artifacts/text-colors/settings.cfg"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://test-artifacts/text-colors"))
	var config := ConfigFile.new()
	config.set_value("audio", "music", 0.23)
	config.set_value(Colors.SECTION, "future_role", Color.CORAL)
	config.set_value(Colors.SECTION, "ui_label", Color("123456"))
	config.set_value(Colors.SECTION, "npc_reply", "not a color")
	config.save(PATH)
	Colors.load_colors(PATH)
	_expect(Colors.color("ui_label") == Color("123456"), "saved colors override defaults")
	_expect(Colors.color("npc_reply") == Color.YELLOW, "invalid saved colors use the default")
	_expect(Colors.color("login_input") == Color(0.0, 0.9, 1.0), "login input uses exact EL cyan")
	_expect(Colors.color("ui_button") == Color(0.77, 0.57, 0.39), "interface uses exact EL GUI brown")
	_expect(Colors.color("world_npc") == Color(0.3, 0.8, 1.0), "NPC labels use EL cyan")
	_expect(Colors.color("float_damage") == Color(1.0, 0.1, 0.2)
		and Colors.color("float_heal") == Color(0.3, 1.0, 0.3)
		and Colors.color("float_level") == Color(0.3, 0.3, 1.0), "floating feedback matches EL")
	var seen: Dictionary = {}
	for group: String in Colors.GROUPS:
		for role: String in Colors.GROUPS[group]:
			_expect(Colors.DEFAULTS.has(role) and not seen.has(role), "one settings catalog entry: " + role)
			seen[role] = true
	_expect(seen.size() == Colors.DEFAULTS.size(), "every text role is exposed in settings")
	_check_canvas_hud_colors()
	var label := Label.new()
	root.add_child(label)
	Colors.bind(label, "ui_label")
	_expect(label.get_theme_color("font_color") == Color("123456"), "binding uses the current color")
	Colors.set_color("ui_label", Color.MAGENTA)
	_expect(label.get_theme_color("font_color") == Color.MAGENTA, "live labels update immediately")
	root.remove_child(label)
	Colors.set_color("ui_label", Color.CYAN)
	root.add_child(label)
	_expect(label.get_theme_color("font_color") == Color.CYAN,
		"bindings survive window-stack reparenting and catch up on re-entry")
	label.set_meta("hud_text_color_override", Color.ORANGE)
	Colors.bind(label, "ui_label")
	_expect(label.get_theme_color("font_color") == Color.ORANGE,
		"a runtime text refresh preserves the HUD component's custom color")
	Colors.set_color("ui_label", Color.GREEN)
	_expect(label.get_theme_color("font_color") == Color.ORANGE,
		"global text changes preserve custom HUD component colors")
	Colors.bind(label, "ui_label")
	_expect(label.get_theme_color("font_color") == Color.ORANGE,
		"repeated semantic bindings retain the custom HUD color")
	label.remove_meta("hud_text_color_override")
	Colors.bind(label, "ui_label")
	_expect(label.get_theme_color("font_color") == Color.GREEN,
		"removing a HUD override restores the current shared text color")
	Colors.set_color("ui_label", Colors.DEFAULTS.ui_label)
	_expect(Colors.is_overridden("ui_label"), "an explicit default-color choice remains an override")
	Colors.reset("ui_label")
	_expect(label.get_theme_color("font_color") == Colors.DEFAULTS.ui_label
		and not Colors.is_overridden("ui_label"), "reset clears only the chosen override")
	var rich := RichTextLabel.new()
	root.add_child(rich)
	Colors.bind(rich, "npc_text", "default_color")
	Colors.set_color("npc_text", Color.CYAN)
	_expect(rich.get_theme_color("default_color") == Color.CYAN, "rich text uses its correct theme slot")
	var world_label := Label3D.new()
	root.add_child(world_label)
	Colors.bind_property(world_label, "world_npc", "modulate")
	Colors.set_color("world_npc", Color.RED)
	_expect(world_label.modulate == Color.RED, "3D text updates through direct-property binding")
	Colors.save_colors()
	config.clear()
	config.load(PATH)
	_expect(config.get_value("audio", "music") == 0.23, "saving preserves unrelated settings")
	_expect(config.get_value(Colors.SECTION, "future_role") == Color.CORAL, "saving preserves unknown future roles")
	_expect(not config.has_section_key(Colors.SECTION, "ui_label"), "reset defaults are not stored")
	Colors.load_colors(PATH)
	_expect(Colors.color("npc_text") == Color.CYAN and Colors.is_overridden("npc_text"), "explicit overrides survive reload")
	var window := Settings.new()
	root.add_child(window)
	await process_frame
	_expect(window.pages.has("TextColors"), "settings exposes a dedicated text colors tab")
	_expect(window.text_color_rows.size() == Colors.DEFAULTS.size(), "settings exposes every role")
	window.restore_text_colors()
	var picker := window.panel.find_child("text_color_float_level", true, false) as ColorPickerButton
	picker.color_changed.emit(Color.GREEN)
	_expect(Colors.color("float_level") == Color.GREEN, "settings picker changes its own role")
	config.clear()
	config.load(PATH)
	_expect(config.get_value(Colors.SECTION, "float_level") == Color.GREEN, "settings change is persisted immediately")
	var reset := window.panel.find_child("text_color_reset_float_level", true, false) as Button
	reset.pressed.emit()
	_expect(not Colors.is_overridden("float_level"), "per-role reset restores default behavior")
	window.text_color_group.select(0)
	window.text_color_search.text = "level"
	window._filter_text_colors()
	_expect((window.text_color_rows.float_level as Control).visible
		and not (window.text_color_rows.ui_label as Control).visible, "search filters the whole catalog")
	if "--rl-windows" in OS.get_cmdline_user_args():
		await _check_rl_windows()
	window.queue_free()
	label.queue_free()
	rich.queue_free()
	world_label.queue_free()
	await process_frame
	Colors.reset()
	Colors.save_colors()
	config.clear()
	config.load(PATH)
	_expect(config.get_value("audio", "music") == 0.23, "full reset preserves unrelated settings")
	_expect(Colors.overrides().is_empty(), "full reset removes only text preferences")
	print("text color tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _check_canvas_hud_colors() -> void:
	var workspace: Control = (load("res://src/ui/hud_workspace.gd") as Script).new()
	var model: RefCounted = workspace.get("model")
	var working: Dictionary = model.get("working")
	var before := working.duplicate(true)
	_expect(workspace.call("_text_config", "resources", "hud_meter").text_color == Color(0.8, 0.8, 0.8),
		"canvas meters resolve the shared EL meter default")
	_expect(workspace.call("_text_config", "clock", "hud_detail").text_color == Color("eee3c8"),
		"RL clock, compass and cards retain their decorative text default")
	Colors.set_color("hud_meter", Color.CYAN)
	var projected: Dictionary = workspace.call("_text_config", "resources", "hud_meter")
	_expect(projected.text_color == Color.CYAN, "canvas configs use the latest shared color")
	projected.text_color = Color.RED
	_expect(working == before, "projecting canvas colors never changes saved HUD preferences")
	working.parts.resources.text_color = Color.MAGENTA
	working.parts.resources.text_color_custom = true
	Colors.set_color("hud_meter", Color.YELLOW)
	_expect(workspace.call("_text_config", "resources", "hud_meter").text_color == Color.MAGENTA,
		"explicit component colors retain precedence over shared canvas colors")
	Colors.set_color("hud_detail", Color.CYAN)
	_expect(workspace.call("_text_config", "clock", "hud_detail").text_color == Color.CYAN,
		"decorative canvas text uses its own configurable role")
	workspace.free()
	Colors.reset("hud_meter")
	Colors.reset("hud_detail")

func _check_rl_windows() -> void:
	var scripts: Dictionary = {}
	for filename: String in ["gauntlet_loot_window", "leaderboards_window", "gauntlet_ready_window", "mounts_window"]:
		var script := load("res://src/ui/" + filename + ".gd") as Script
		_expect(script != null and script.can_instantiate(), "RL color integration compiles: " + filename)
		if script == null or not script.can_instantiate():
			return
		scripts[filename] = script
	var loot: Variant = scripts.gauntlet_loot_window.new()
	root.add_child(loot)
	Colors.set_color("loot_title", Color.MAGENTA)
	_expect(loot.heading.get_theme_color("font_color") == Color.MAGENTA,
		"gauntlet loot headings update without rebuilding its state")
	_expect(loot.editor.theme.get_color("title_color", "Window") == Color.MAGENTA,
		"gauntlet allocation dialogs update their inherited text theme")
	Colors.set_color("loot_primary", Color.CYAN)
	_expect(loot.send_button.get_theme_color("font_color") == Color.CYAN,
		"primary loot action has a separately configurable ink color")
	var boards: Variant = scripts.leaderboards_window.new()
	var silver: Label = boards._label("Second place", 14, Color("bbc9d7"))
	root.add_child(silver)
	Colors.set_color("leaderboard_silver", Color.GREEN)
	_expect(silver.get_theme_color("font_color") == Color.GREEN,
		"podium text updates independently of its artwork")
	boards.free()
	var ready: Variant = scripts.gauntlet_ready_window.new()
	root.add_child(ready)
	var ready_stack := WindowStack.new()
	ready.add_child(ready_stack)
	ready_stack.configure(ready)
	ready_stack.register(ready.panel)
	ready.apply_snapshot({"open": true, "route": "Landfall", "difficulty": "Normal", "level": 10,
		"is_leader": false, "can_start": false, "in_party": true,
		"members": [{"name": "Tavi", "self": true, "leader": false, "ready": true, "status": "Ready"}]})
	Colors.set_color("ready_success", Color.CYAN)
	var ready_status: Label = ready.rows.get_child(0).get_child(1)
	_expect(ready_status.get_theme_color("font_color") == Color.CYAN,
		"ready checks retain their live state while recoloring")
	var mounts: Variant = scripts.mounts_window.new()
	root.add_child(mounts)
	Colors.set_color("mount_text", Color.YELLOW)
	_expect(mounts.status.get_theme_color("font_color") == Color.YELLOW,
		"mount status text updates while the window is closed")
	Colors.set_color("mount_button", Color.MAGENTA)
	_expect(mounts.ride.get_theme_color("font_color") == Color.MAGENTA,
		"mount action text follows its own preference")
	loot.queue_free()
	silver.queue_free()
	ready.queue_free()
	mounts.queue_free()
	await process_frame

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

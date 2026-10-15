extends SceneTree
var failures := 0
var observed: Array[int] = []
var casts: Array[Dictionary] = []
var render := false
var main: Control
func _init() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
func key(code: Key, pressed := true) -> InputEventKey:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.keycode = code
	event.location = KEY_LOCATION_LEFT if code == KEY_SHIFT else KEY_LOCATION_UNSPECIFIED
	event.pressed = pressed
	event.shift_pressed = true
	return event
func run() -> void:
	render = "--render" in OS.get_cmdline_user_args()
	root.size = Vector2i(1280,720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var original_layout: Dictionary = main.casting_bar.hud_layout()
	main.casting_bar.restore_hud_layout({})
	var state := root.get_node("AppState")
	state.authenticated = true
	state.select_actor(-1)
	state.spell_power["heal"] = {"limit":10}
	main.game_view.show()
	main.login_panel.hide()
	main.spell_loadout.profile = ""
	main.spell_wheel.anchor_provider = func(): return Vector2(root.size) / 2
	main.spell_wheel.opened.connect(func(): observed.append(20))
	main.spell_wheel.tutorial_action.connect(func(action: int): observed.append(action))
	main.magic_selection.request_sender = func(data: Dictionary) -> Error:
		casts.append(data.duplicate(true))
		return OK
	await process_frame
	check(main.casting_bar.docked and main.casting_bar.panel.visible, "live spell bar starts attached beside item slots")
	main.casting_bar.dock_menu.get_popup().id_pressed.emit(3)
	check(not main.casting_bar.panel.visible and main.casting_bar.launcher.is_visible_in_tree(), "Hide spell bar leaves a reachable launcher")
	main.spell_loadout.set_ring_size(90)
	main._sync_spells()
	check(not main.casting_bar.panel.visible, "spell and size refreshes do not reopen the panel")
	var shortcut := key(KEY_1)
	shortcut.shift_pressed = false
	shortcut.alt_pressed = true
	root.push_input(shortcut, true)
	check(casts.size() == 1 and casts.back().get("id") == 0, "Alt+1 casts the saved slot with the panel closed")
	check(not main.casting_bar.panel.visible, "using a shortcut leaves the panel closed")
	var alt_release := key(KEY_ALT, false)
	alt_release.shift_pressed = false
	root.push_input(alt_release, true)
	casts.clear()
	show_lesson("spell_ring", "Your spell ring", "Hold Left Shift to open your spell ring, or click Ring on the quickbar. Alt remains available for quickbar shortcuts.")
	check(main.lantern_guide.control_for_step() == main.casting_bar.launcher, "closed-panel lesson highlights the visible Quickbar launcher")
	await capture("collapsed")
	click(main.casting_bar.launcher)
	await process_frame
	check(main.casting_bar.panel.visible and not main.casting_bar.launcher.visible, "Quickbar click opens the panel")
	check(main.lantern_guide.control_for_step() == main.casting_bar.wheel_button, "expanded-panel lesson highlights the Ring button")
	var size_picker: OptionButton = main.casting_bar.ring_size_picker
	size_picker.select(size_picker.get_item_index(110))
	size_picker.item_selected.emit(size_picker.selected)
	check(main.spell_loadout.ring_size == 110, "ring size remains adjustable from the opened panel")
	main.casting_bar.dock_menu.get_popup().id_pressed.emit(3)
	await process_frame
	check(not main.casting_bar.panel.visible, "the bar menu hides the spell panel")
	root.push_input(key(KEY_SHIFT), true)
	await process_frame
	check(observed == [20] and main.spell_wheel.visible, "Left Shift opens the live ring and records one tutorial observation")
	await capture("intro-open")
	root.push_input(key(KEY_1), true)
	await process_frame
	check(observed == [20,21] and main.spell_wheel.category == "Healing", "the displayed class shortcut records browsing")
	root.push_input(key(KEY_SHIFT,false), true)
	check(observed == [20,21,22] and casts.is_empty(), "release records dismissal without a spell request")
	main.casting_bar.open_wheel.emit()
	main.spell_wheel.enter_class("Healing")
	root.push_input(key(KEY_ESCAPE), true)
	check(observed.slice(-3) == [20,21,22], "mouse-only ring can browse and dismiss with Escape")
	main.spell_wheel.open_wheel(true)
	main.spell_wheel.enter_class("Healing")
	main.spell_wheel.select_scope("self")
	var before := observed.size()
	root.push_input(key(KEY_1), true)
	root.push_input(key(KEY_SHIFT,false), true)
	check(observed.size() == before and casts.back().get("op") == "cast", "casting and its Shift release cannot report tutorial cancellation")
	main.spell_wheel.open_wheel()
	main.spell_wheel.enter_class("Healing")
	for control in ["ring_target","ring_power"]:
		show_lesson(control, "Choose your cast", "Hold Left Shift, open Healing and hover Heal. Right click cycles Self, Target, Allies and Burst. Scroll to Power 2, then choose Heal. The quickbar saves the last cast target type and power in the icon corners.")
		await capture(control)
		check(main.lantern_guide.control_for_step() == (main.spell_wheel._scope_bar if control == "ring_target" else main.spell_wheel._power_label), "lesson highlights " + control + " visible=" + str(main.spell_wheel.visible) + " actual=" + str(main.lantern_guide.control_for_step()))
	for percent in [75,125]:
		main.spell_loadout.set_ring_size(percent)
		await capture("size-%d" % percent)
	main.spell_wheel.reset()
	show_lesson("quickbar", "A spell within reach", "Find Heal on the quickbar (default Alt+1). Its top-left badge is the saved target type; top-right is power. Click it or use its shortcut to heal this second wound.")
	check(main.lantern_guide.control_for_step() == main.casting_bar.launcher, "quickbar lesson points to the launcher while collapsed")
	click(main.casting_bar.launcher)
	await capture("quickbar")
	check(main.lantern_guide.control_for_step() == main.casting_bar.panel, "quickbar teaching highlights the panel rather than the whole viewport")
	main.casting_bar.restore_hud_layout(original_layout)
	main.call("_save_hud_settings")
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("magic ring tutorial: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
func show_lesson(control: String, title: String, hint: String) -> void:
	main.lantern_guide.apply_state({"active":true,"tutorial":"borrowed_sky","stage":1,"total":39,"control":control,"title":title,"hint":hint})
func click(control: Control) -> void:
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = control.get_global_rect().get_center()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		root.push_input(event, true)
func capture(name: String) -> void:
	for frame in range(6): await process_frame
	var card: Rect2 = main.lantern_guide.card.get_global_rect()
	var bar_surface: Control = main.casting_bar.panel if main.casting_bar.panel.visible else main.casting_bar.launcher
	check(not card.intersects(bar_surface.get_global_rect()), "tutorial instructions leave the spell bar and launcher clickable")
	check(not main.casting_bar.panel.get_global_rect().intersects(main.get_node("GameView/ItemQuickbar").get_global_rect()), "the attached spell bar leaves item slots clear")
	check(Rect2(Vector2.ZERO,Vector2(root.size)).encloses(card), "tutorial card stays in the viewport")
	if main.spell_wheel.visible:
		var bounds: Rect2 = main.spell_wheel.get_ring_bounds()
		check(not card.intersects(bounds), "tutorial card leaves ring sectors unobstructed")
	if render:
		await RenderingServer.frame_post_draw
		DirAccess.make_dir_recursive_absolute("res://test-artifacts/magic-casting")
		root.get_texture().get_image().save_png("res://test-artifacts/magic-casting/tutorial-"+name+".png")

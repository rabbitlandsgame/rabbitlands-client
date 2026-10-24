extends SceneTree
## The final perk must remain visible and clickable after scrolling at large
## UI scales, after resizing, and after opening another statistics tab.

var failures := 0
var checks := 0
var main: Control

func _init() -> void:
	_run.call_deferred()

func _frames(count := 8) -> void:
	for index: int in count:
		await process_frame

func _expect(value: bool, label: String) -> void:
	checks += 1
	if value:
		return
	failures += 1
	push_error(label)

func _inside_view(control: Control) -> bool:
	return main.game_view.get_global_rect().grow(1).encloses(control.get_global_rect())

func _check_gatherer(label: String) -> void:
	main.stats_tabs.current_tab = main.perk_tab.get_index()
	main.stats_panel.show()
	await _frames()
	_expect(_inside_view(main.stats_panel), label + ": statistics window fits the screen")
	var scroll: ScrollContainer = main.perk_rows.get_parent()
	_expect(_inside_view(scroll), label + ": perk scroll area fits the screen")
	scroll.scroll_vertical = ceili(scroll.get_v_scroll_bar().max_value)
	await _frames()
	var take: Button = main.perk_rows.get_node("PerkGatherer/Row/Take")
	_expect(scroll.get_global_rect().grow(1).encloses(take.get_global_rect()),
		label + ": scrolling to the bottom exposes Gatherer's entire button")
	_expect(_inside_view(take), label + ": Gatherer's button is on screen")
	var point := take.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	root.push_input(motion, true)
	var click := InputEventMouseButton.new()
	click.position = point
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	root.push_input(click, true)
	click.pressed = false
	root.push_input(click, true)
	await _frames()
	_expect(main.purchase_confirm.visible and main._pending_purchase == ["perk", "Gatherer"],
		label + ": Gatherer can be selected with the mouse")
	main._on_purchase_cancelled()

func _run() -> void:
	create_timer(120).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await _frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	for window: Control in main.window_stack._windows:
		window.hide()
	var state := root.get_node("AppState")
	state.perk_catalog.clear()
	for category: String in ["Combat", "Magic", "Utility"]:
		for index: int in 12:
			state.perk_catalog.append({"name": "%s %d" % [category, index],
				"category": category, "description": "A perk with a description that wraps onto another line.",
				"pickpoints": 3, "gold": 300, "tier": 0, "max_tier": 3, "blocker": ""})
	state.perk_catalog.append({"name": "Gatherer", "category": "Utility",
		"description": "One harvest in five yields a second item.",
		"pickpoints": 3, "gold": 300, "tier": 0, "max_tier": 3, "blocker": ""})
	main._sync_perk_catalog()
	await _check_gatherer("default size, All")
	main._ui_scale = 1.5
	main._apply_ui_scale()
	await _check_gatherer("150% UI scale, All")
	main._on_perk_filter_chosen("Utility")
	await _check_gatherer("150% UI scale, Utility")
	main.stats_tabs.current_tab = 1
	await _frames()
	_expect(_inside_view(main.stats_panel), "Knowledge tab also fits at 150% scale")
	await _check_gatherer("returning from Knowledge")
	main.stats_panel.global_position = Vector2(4000, 4000)
	main.stats_panel.get_node("WindowDrag").clamp_into_view()
	await _check_gatherer("dragged to the bottom edge")
	root.size = Vector2i(1280, 600)
	await _check_gatherer("shorter window at 150% UI scale")
	main.stats_panel.hide()
	root.size = Vector2i(1440, 900)
	main._ui_scale = 1.0
	main._apply_ui_scale()
	await _check_gatherer("reopened in a larger window")
	_expect(is_equal_approx(main.stats_panel.size.y, 545), "larger screens restore the normal window height")
	state.perk_catalog.clear()
	main.queue_free()
	await _frames(2)
	print("PERKS WINDOW FIT: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)

extends SceneTree
## Exercise both quest windows through their player-facing buttons.

var failures := 0
var checks := 0
var main: Control
var app_state: Node

func _init() -> void:
	call_deferred("run")

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func settle() -> void:
	for frame: int in range(4):
		await process_frame

func click(control: Control) -> void:
	var point := control.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	root.push_input(motion, true)
	var event := InputEventMouseButton.new()
	event.position = point
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await settle()

func capture(filename: String) -> void:
	var directory := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if directory.is_empty() or DisplayServer.get_name() == "headless":
		return
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(directory.path_join(filename + ".png"))

func journal(titles: Array) -> void:
	app_state.quest_journal.clear()
	for title: String in titles:
		app_state.quest_journal.append({"title": title, "objective": "Gather supplies",
			"location": "Four Gates", "current": 1, "target": 3, "ready": false})
	app_state.state_changed.emit(&"quest_journal")

func guide_state(value: Dictionary) -> void:
	app_state.lantern_tutorial = value.duplicate(true)
	app_state.state_changed.emit(&"lantern_tutorial")

func run() -> void:
	create_timer(60).timeout.connect(func(): push_error("Quest untracking timed out"); quit(1))
	root.size = Vector2i(1280, 720)
	app_state = root.get_node("AppState")
	root.get_node("Network").set_process(false)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await settle()
	main.set_process(false)
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	app_state.authenticated = true
	# Tracking is tested with its HUD component enabled, independently of the
	# player's chosen preset (Classic currently starts with objectives hidden).
	main.hud_workspace.change_part("objectives", "enabled", true)
	var windows: Control = main.extension_windows
	var guide: Control = main.lantern_guide
	journal(["First quest", "Second quest"])
	windows.quest_track_button.pressed.emit()
	await settle()
	expect(windows.tracked_quest.visible and windows.quest_track_button.text == "Untrack",
		"tracking an ordinary quest opens its window and offers Untrack")
	expect(windows.tracked_quest.get_global_rect().encloses(windows.quest_untrack_button.get_global_rect()),
		"the quest window's untrack control fits within its bounds")
	await capture("quest-tracker-untrack")
	windows.quest_list.select(1)
	windows.quest_list.item_selected.emit(1)
	expect(windows.quest_track_button.text == "Track", "selecting another quest updates the tracking action")
	await click(windows.quest_untrack_button)
	app_state.quest_journal[0].current = 2
	app_state.state_changed.emit(&"quest_journal")
	await settle()
	expect(not windows.tracked_quest.visible and app_state.quest_journal[0].current == 2,
		"the window closes for its own quest even with another row selected and stays closed on progress updates")
	windows.quest_list.select(0)
	windows.quest_list.item_selected.emit(0)
	windows.quest_track_button.pressed.emit()
	expect(windows.tracked_quest.visible, "Track restores an untracked quest")
	windows.quest_track_button.pressed.emit()
	expect(not windows.tracked_quest.visible, "Untrack in the journal also closes the quest window")

	for sample: Dictionary in [
		{"tutorial": "signed_ashore", "quest": "Signed Ashore"},
		{"tutorial": "watchpost", "quest": "Help for the Watchpost"},
		{"tutorial": "borrowed_sky", "quest": "The Borrowed Sky"},
		{"tutorial": "second_bell", "quest": "The Second Bell"},
		{"tutorial": "followup", "quest": "The Missing Caravan", "adventure": "The Missing Caravan"},
		{"tutorial": "lantern", "quest": "The Last Lantern"}]:
		journal([sample.quest])
		var snapshot := {"active": true, "tutorial": sample.tutorial, "stage": 1, "total": 4,
			"title": "Gather supplies", "hint": "Keep your supplies", "control": "world", "count": 1}
		if sample.has("adventure"):
			snapshot.adventure = sample.adventure
		guide_state(snapshot)
		await settle()
		expect(guide.visible and guide.card.is_visible_in_tree() and windows.quest_track_button.text == "Untrack",
			"the journal recognizes the active guide: " + sample.quest)
		if sample.tutorial == "signed_ashore":
			await capture("quest-guide-untrack")
		await click(guide.untrack)
		await settle()
		expect(not guide.visible and not guide.card.is_visible_in_tree()
			and not windows.tracked_quest.visible and windows.quest_track_button.text == "Track",
			"Untrack hides the guide and updates the journal: " + sample.quest)
		expect(app_state.lantern_tutorial == snapshot and bool(guide.state.active),
			"untracking preserves the active quest and its progress: " + sample.quest)
		snapshot.stage = 2
		snapshot.title = "Return the supplies"
		snapshot.count = 2
		guide_state(snapshot)
		app_state.state_changed.emit(&"quest_journal")
		await settle()
		expect(not guide.visible and not windows.tracked_quest.visible,
			"new objectives do not reopen an untracked guide: " + sample.quest)
		windows.quest_track_button.pressed.emit()
		await settle()
		expect(guide.visible and guide.heading.text == "Return the supplies" and not windows.tracked_quest.visible,
			"Track restores the latest objective without a duplicate tracker: " + sample.quest)
		windows.quest_track_button.pressed.emit()
		expect(not guide.visible, "Untrack in the journal hides the guide: " + sample.quest)
		guide_state({"active": false})
		guide_state(snapshot)
		expect(not guide.visible, "restated quest state retains the untracked choice: " + sample.quest)

	# A quest can first arrive as a journal row and later gain its guide. Once
	# untracked, neither presentation may return when the guide goes inactive.
	guide_state({"active": false})
	journal(["Help for the Watchpost"])
	windows.quest_track_button.pressed.emit()
	expect(windows.tracked_quest.visible, "a journal quest can be tracked before its guide arrives")
	guide_state({"active": true, "tutorial": "watchpost", "title": "Prepare medicine", "hint": "Keep your supplies"})
	windows.quest_track_button.pressed.emit()
	guide.untrack.pressed.emit()
	guide_state({"active": false})
	app_state.state_changed.emit(&"quest_journal")
	expect(not windows.tracked_quest.visible, "untracking the guide also clears any earlier tracked note")

	# Field dispatches retain the existing server-owned tracking request. A
	# disconnected request must keep the window visible and explain the failure.
	# A practice quest can share a title with a main-world dispatch. Its local
	# hidden choice must not override the server's explicit dispatch tracking.
	journal(["The Missing Caravan"])
	app_state.quest_journal[0].location = "Main world"
	guide_state({"active": true, "tutorial": "field_dispatch", "adventure": "The Missing Caravan",
		"title": "Gather supplies", "hint": "Keep your supplies"})
	expect(guide.visible and not guide.skip.visible, "dispatches expose Untrack without a duplicate Stop tracking action")
	guide.untrack.pressed.emit()
	expect(guide.visible and not app_state.chat_lines.is_empty()
		and str(app_state.chat_lines.back().get("text", "")).contains("Could not update quest tracking"),
		"a failed server tracking request reports the failure without pretending it succeeded")
	guide_state({"active": false, "tutorial": "field_dispatch"})
	expect(not guide.visible and not windows.tracked_quest.visible,
		"a server untrack acknowledgement closes the dispatch window")
	main.queue_free()
	await process_frame
	print("Quest untracking: %d checks, %d failures" % [checks, failures])
	quit(failures)

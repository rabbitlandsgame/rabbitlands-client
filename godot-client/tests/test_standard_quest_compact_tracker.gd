extends SceneTree
## The shared chrome must preserve ordinary journal ownership and tracking.
var checks := 0
var failures := 0

class GuideStub extends Control:
	signal tracking_changed()
	signal window_visibility_changed()
	var owned_title := ""
	var campaign := false
	func quest_title() -> String: return owned_title
	func is_quest_tracked() -> bool: return not owned_title.is_empty()
	func using_campaign() -> bool: return campaign
	func campaign_entry() -> Dictionary: return {}
	func prefer_standard_quest() -> void: campaign = false
	func is_window_hidden(_identity := "") -> bool: return false

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if not value: failures += 1; push_error(message)
func settle() -> void:
	for index in 6: await process_frame
func click(button: Control) -> void:
	var at := button.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new(); motion.position = at; root.push_input(motion, true)
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new(); event.button_index = MOUSE_BUTTON_LEFT
		event.position = at; event.pressed = pressed; root.push_input(event, true)
	await settle()
func run() -> void:
	create_timer(60).timeout.connect(func() -> void: push_error("Ordinary compact tracker timed out"); quit(1))
	root.size = Vector2i(1280,720)
	var network := root.get_node("Network")
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the isolated ordinary-tracker transport recorder compiles")
	network.set_script(recorder); network.block_for_hud_preview()
	var app := root.get_node("AppState"); app.authenticated = true
	var first := {"title":"A useful delivery", "objective":"Gather Sage.\n\n[b]Keep the crew's supplies safe.[/b]",
		"location":"Landfall", "current":1, "target":3, "ready":false}
	var second := {"title":"Another quest", "objective":"Speak with the guard.",
		"location":"Landfall", "current":0, "target":1, "ready":false}
	var first_before := first.duplicate(true)
	app.quest_journal.assign([first.duplicate(true), second.duplicate(true)])
	var guide := GuideStub.new(); root.add_child(guide)
	var windows: Control = load("res://src/ui/extension_windows.gd").new(); root.add_child(windows)
	windows.configure(null, guide); await settle()
	expect(not windows.tracked_quest.visible, "ordinary quests are not pinned without the player's Track action")
	windows._on_quest_track_pressed(); await settle()
	var tracker: PanelContainer = windows.tracked_quest
	expect(tracker.visible and tracker.has_method("apply_presentation") and not windows._tracked_quest_compact,
		"Track opens the reusable ordinary slim card by default")
	expect(tracker.get("heading").text == first.title and tracker.get("objective").text == "Gather Sage."
		and tracker.get("counter").text == "1 / 3" and absf(tracker.get("progress").value/100.0 - 1.0/3.0) < 0.01,
		"the slim card states the current native task and real progress")
	expect(not tracker.get("details").visible and windows.tracked_quest_text.text.contains("Keep the crew")
		and tracker.get("objective").tooltip_text == first.objective,
		"full instructions remain available without expanding the default card")
	var expected_notes: String = first.objective + "\n\nProgress: 1 / 3\nLocation: Landfall"
	expect(windows.tracked_quest_text.text == expected_notes
		and windows.tracked_quest_text.get_parsed_text() == expected_notes,
		"inline notes preserve exact objective paragraphs and literal brackets beside native progress and location")
	expect(not "QUEST TRACKER" in windows.tracked_quest_text.text and not first.title in windows.tracked_quest_text.text,
		"inline notes do not repeat the tracker banner or quest-title hierarchy")
	expect(windows.tracked_quest_text.get_parent() == tracker.get("details")
		and tracker.get("details").get_parent() == tracker.get("details_scroll"),
		"ordinary notes use the single common inline scroll body")
	await click(tracker.get("more"))
	expect(tracker.call("more_is_open") and tracker.get("replay_button").disabled,
		"More opens real actions and ordinary quests do not invent a cinematic replay")
	await click(tracker.get("instructions_button"))
	expect(windows._tracked_quest_details_open and windows.tracked_quest_text.is_visible_in_tree()
		and not tracker.call("more_is_open"), "More Instructions exposes the complete objective in the existing detail reader")
	await click(tracker.get("details_close"))
	expect(not windows._tracked_quest_details_open and tracker.visible and not windows._tracked_quest_compact
		and windows._tracked_quest_title == first.title,
		"the inline Close button keeps the quest card and tracking while closing only its full notes")
	await click(tracker.get("more")); await click(tracker.get("instructions_button"))
	await click(tracker.get("collapse"))
	expect(windows._tracked_quest_compact and not tracker.get("objective").visible
		and not tracker.get("details").visible and tracker.size.y < 70,
		"the collapse control makes a small quest ribbon and closes full details")
	var updated := first.duplicate(true); updated.current = 2
	app.quest_journal.assign([updated, second.duplicate(true)]); app.state_changed.emit(&"quest_journal"); await settle()
	expect(windows._tracked_quest_compact and tracker.get("heading").text == "Gather Sage."
		and tracker.get("counter").text == "2 / 3", "journal updates preserve the ribbon and refresh native progress")
	await click(tracker.get("more")); await click(tracker.get("instructions_button"))
	expect(not windows._tracked_quest_compact and windows._tracked_quest_details_open,
		"Instructions expands a collapsed ribbon without changing quest tracking")
	var ready := updated.duplicate(true); ready.current = 3; ready.ready = true
	app.quest_journal.assign([ready, second.duplicate(true)]); app.state_changed.emit(&"quest_journal"); await settle()
	expect(windows._tracked_quest_details_open and windows.tracked_quest_text.text == first.objective
		+ "\n\nProgress: 3 / 3\nLocation: Landfall\nReady to turn in.",
		"an open inline foldout follows native progress and ready status without losing its exact objective")
	app.quest_journal.assign([updated, second.duplicate(true)]); app.state_changed.emit(&"quest_journal"); await settle()
	windows.quest_list.select(1); windows.quest_list.item_selected.emit(1)
	await click(tracker.get("more")); await click(windows.quest_hide_button)
	expect(not tracker.visible and windows._tracked_quest_title == first.title,
		"Hide closes the pinned quest itself even while another journal row is selected")
	app.state_changed.emit(&"quest_journal"); await settle()
	expect(not tracker.visible and windows.tracked_quest_titles() == [first.title],
		"a hidden ordinary quest remains tracked across server journal updates")
	windows.quest_list.select(0); windows.quest_list.item_selected.emit(0); await settle()
	expect(windows.quest_show_button.visible and windows.quest_track_button.text == "Untrack",
		"the journal offers Show for the hidden tracked quest")
	windows.quest_show_button.pressed.emit(); await settle()
	expect(tracker.visible and not windows.quest_show_button.visible, "Show restores the latest ordinary quest presentation")
	guide.owned_title = first.title; windows._sync_tracked_quest(); await settle()
	expect(not tracker.visible, "a matching tutorial or field guide still owns and suppresses the duplicate ordinary card")
	guide.owned_title = ""; windows._sync_tracked_quest(); await settle()
	expect(tracker.visible, "the ordinary tracker returns after its guide becomes quiescent")
	guide.campaign = true; windows._sync_tracked_quest(); await settle()
	expect(not tracker.visible, "an active campaign guide retains precedence over the ordinary tracker")
	guide.campaign = false; windows._sync_tracked_quest(); await settle()
	windows.quest_list.select(1); windows.quest_list.item_selected.emit(1)
	await click(tracker.get("more")); await click(windows.quest_untrack_button)
	expect(not tracker.visible and windows._tracked_quest_title.is_empty(),
		"More Untrack removes the pinned quest rather than the selected journal row")
	app.state_changed.emit(&"quest_journal"); await settle()
	expect(not tracker.visible and first == first_before
		and app.quest_journal[0].current == 2 and app.quest_journal[1].title == second.title,
		"presentation controls never edit native quest entries or their current progress")
	windows.quest_list.select(0); windows.quest_list.item_selected.emit(0)
	windows.quest_track_button.pressed.emit(); await settle()
	root.size = Vector2i(720,480); root.content_scale_factor = 1.5; await settle()
	for compact: bool in [false,true]:
		if windows._tracked_quest_compact != compact: await click(tracker.get("collapse"))
		expect(root.get_visible_rect().encloses(tracker.get_global_rect()),
			"the ordinary slim card or ribbon stays inside a small scaled viewport")
		await click(tracker.get("more"))
		expect(tracker.call("more_is_open") and root.get_visible_rect().encloses(tracker.get("_menu").get_global_rect()),
			"the ordinary More menu stays reachable in a small scaled viewport")
		var escape := InputEventKey.new(); escape.keycode = KEY_ESCAPE; escape.pressed = true
		root.push_input(escape, true); await settle()
		expect(not tracker.call("more_is_open") and windows._tracked_quest_compact == compact,
			"Escape closes More without altering the tracked quest or ribbon preference")
	var long_notes := updated.duplicate(true)
	long_notes.objective = "\n\n".join(PackedStringArray(range(30).map(
		func(index: int) -> String: return "Journal paragraph %d: keep these native instructions intact." % index)))
	app.quest_journal.assign([long_notes, second.duplicate(true)]); app.state_changed.emit(&"quest_journal"); await settle()
	await click(tracker.get("more")); await click(tracker.get("instructions_button"))
	var scroll: ScrollContainer = tracker.get("details_scroll")
	expect(root.get_visible_rect().encloses(tracker.get_global_rect())
		and scroll.get_v_scroll_bar().max_value > scroll.get_v_scroll_bar().page,
		"long ordinary notes stay scrollable inside the inline foldout in a small scaled window")
	await click(tracker.get("details_close"))
	expect(tracker.visible and not windows._tracked_quest_details_open and windows._tracked_quest_title == first.title,
		"closing long instructions leaves the tracked slim card available")
	expect((network.get("sent_frames") as Array).is_empty(),
		"ordinary More, instructions, collapse, Hide, Show and Untrack emit no gameplay or dispatch commands")
	windows.queue_free(); guide.queue_free(); await process_frame; await process_frame
	print("Ordinary compact quest tracker: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)

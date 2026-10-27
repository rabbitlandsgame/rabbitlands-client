extends SceneTree
const Choice := preload("res://src/ui/campaign_choice.gd")
var checks := 0
var failures := 0
var requests: Array = []
var continues: Array[String] = []

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func payload(token := "run-a:plan-1") -> Dictionary:
	return {"id":"opening_rescue", "token":token, "title":"How do we reach the stranded crew?",
		"selected":"", "response":"", "can_choose":true, "owner":"Ari", "owner_is_you":true,
		"options":[
			{"id":"defend", "label":"Protect the crew", "detail":"Hold the approach while the crew reaches dry ground."},
			{"id":"repair", "label":"Mend the access", "detail":"Inspect the damage, fit the right packing, then test it."},
			{"id":"evacuate", "label":"Move the injured", "detail":"Give first aid and guide the worker along the safe route."}]}

func settle() -> void:
	for _frame: int in range(5):
		await process_frame

func key(code: Key) -> void:
	var press := InputEventKey.new()
	press.keycode = code
	press.pressed = true
	Input.parse_input_event(press)
	await process_frame
	var release := InputEventKey.new()
	release.keycode = code
	release.pressed = false
	Input.parse_input_event(release)
	await process_frame

func click(button: Button) -> void:
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.position = button.get_global_rect().get_center()
	press.pressed = true
	Input.parse_input_event(press)
	await process_frame
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	release.position = press.position
	release.pressed = false
	Input.parse_input_event(release)
	await process_frame

func _run() -> void:
	create_timer(60).timeout.connect(func() -> void: push_error("Campaign choice check timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	root.size = Vector2i(1280, 720)
	var host := Control.new()
	host.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(host)
	var widget = Choice.new()
	host.add_child(widget)
	widget.position = Vector2(16, 36)
	widget.size.x = 1248
	widget.option_selected.connect(func(id: String, token: String) -> void: requests.append([id, token]))
	widget.continue_requested.connect(func(token: String) -> void: continues.append(token))
	var offered := payload()
	var unchanged := offered.duplicate(true)
	widget.apply_choice(offered, false)
	await settle()
	var measured_revision: int = widget._measure_revision
	widget.fit_width(widget._width)
	widget.apply_choice(offered.duplicate(true), false)
	expect(widget._measure_revision == measured_revision, "unchanged frame updates do not queue more layout measurements")
	expect(widget.visible and widget.option_buttons.size() == 3, "all three approaches are visible in the choice")
	expect(not widget.continue_button.visible, "normal owner choice has no replay Continue")
	for option: Dictionary in offered.options:
		var button: Button = widget.option_buttons[option.id]
		expect(button.visible and not button.disabled and button.focus_mode == Control.FOCUS_ALL, str(option.id) + " supports keyboard focus and clicking")
		expect(widget._content[option.id].detail.text == option.detail, str(option.id) + " retains its plain-language consequence")
	(widget.option_buttons.defend as Button).grab_focus()
	await process_frame
	await key(KEY_TAB)
	expect(root.gui_get_focus_owner() == widget.option_buttons.repair, "Tab reaches the next real approach button")
	await key(KEY_SPACE)
	expect(requests == [["repair", "run-a:plan-1"]], "Space submits the focused choice with its captured scene token")
	expect(str(widget._payload.selected).is_empty() and offered == unchanged, "requesting a choice never invents an authoritative selection or changes its input")
	expect("confirmed" in widget.status_label.text, "the pending choice has visible confirmation feedback")
	for button: Button in widget.option_buttons.values():
		expect(button.disabled, "pending state disables every alternative")
	widget.apply_choice(offered.duplicate(true), false)
	widget._choose("defend", "run-a:plan-1")
	expect(requests.size() == 1, "identical per-frame state and a duplicate click cannot double-submit")
	widget.release_pending("The request could not be sent. Choose again.")
	expect(not (widget.option_buttons.defend as Button).disabled and "Choose again" in widget.status_label.text, "a send failure can release pending state for a visible retry")
	var stale_button: Button = widget.option_buttons.defend
	var next_offer := payload("run-b:plan-1")
	widget.apply_choice(next_offer, false)
	stale_button.pressed.emit()
	expect(requests.size() == 1, "a previous scene's queued button cannot choose in the new scene")
	await settle()
	await click(widget.option_buttons.defend)
	expect(requests.back() == ["defend", "run-b:plan-1"] and requests.size() == 2, "a real mouse click on the new scene binds its own current token")
	var recorded := next_offer.duplicate(true)
	recorded.selected = "defend"
	recorded.can_choose = false
	recorded.response = "Hold the approach. I will keep the crew moving."
	widget.apply_choice(recorded, false)
	expect(widget.option_buttons.size() == 3 and widget._pending.is_empty(), "the authoritative reply retains all options and clears pending")
	expect(widget._content.defend.heading.text.begins_with("✓ "), "the server-recorded approach gains a tick")
	expect(not widget._content.repair.heading.text.begins_with("✓ "), "unselected alternatives receive no invented tick")
	widget._choose("evacuate", "run-b:plan-1")
	expect(requests.size() == 2, "a recorded live selection cannot be overwritten through the widget")
	var helper := payload("party:plan-1")
	helper.can_choose = false
	helper.owner_is_you = false
	widget.apply_choice(helper, false)
	expect("Waiting for Ari" in widget.status_label.text and not widget.continue_button.visible, "a helper sees the named owner waiting state without a Continue bypass")
	widget._choose("repair", "party:plan-1")
	expect(requests.size() == 2, "helpers cannot submit owner choices")
	widget.apply_choice(recorded, true)
	await settle()
	var frozen_payload: Dictionary = widget._payload.duplicate(true)
	widget.set_embedded(true)
	await settle()
	expect(not widget.title_label.visible and widget.get_theme_stylebox("panel") is StyleBoxEmpty, "embedding removes only the duplicate title and outer panel")
	expect(widget.option_buttons.size() == 3 and widget._payload == frozen_payload and widget.continue_button.visible, "embedding preserves all approaches, the authoritative account and replay Continue")
	expect("3 approaches" in str(widget.get_meta(&"dialogue_scroll_hint","")), "embedded content exposes its approach count for a persistent scroll hint")
	expect(widget.status_label.get_theme_color("font_color") == Choice.GOLD, "the replay footer keeps the recorded choice emphatic even while details scroll")
	widget.set_embedded(false)
	await settle()
	expect(widget.title_label.visible and widget.get_theme_stylebox("panel") is StyleBoxFlat, "standalone presentation can be restored without changing the choice")
	expect(widget.continue_button.visible and not widget.continue_button.disabled, "replay offers a separate Continue")
	for id: String in widget.option_buttons:
		var button: Button = widget.option_buttons[id]
		expect(button.visible and button.disabled, "replay keeps " + id + " visible and read-only")
	var picked_box: StyleBoxFlat = (widget.option_buttons.defend as Button).get_theme_stylebox("disabled")
	expect(picked_box.border_color == Choice.GOLD and widget._content.defend.heading.get_theme_color("font_color") == Choice.GOLD, "replay emphasizes the recorded approach with the gold frame and name")
	widget._choose("evacuate", "run-b:plan-1")
	expect(requests.size() == 2, "replay never emits a replacement choice")
	widget.continue_button.grab_focus()
	await key(KEY_ENTER)
	expect(continues == ["run-b:plan-1"], "Enter continues replay with its captured context token")
	widget.apply_choice(recorded.duplicate(true), true)
	widget._continue("run-b:plan-1")
	expect(continues.size() == 1, "a replay Continue cannot double-fire across repeated updates")
	var old_continue: Callable = widget._continue_binding
	var unrecorded := payload("run-c:plan-1")
	widget.apply_choice(unrecorded, true)
	old_continue.call()
	expect(continues.size() == 1, "an earlier replay's queued Continue cannot resume a new scene")
	expect("No plan recorded yet" in widget.status_label.text, "an unchosen replay states that no plan was recorded")
	for row: Dictionary in widget._content.values():
		expect(not (row.heading as Label).text.begins_with("✓ "), "an unchosen replay fabricates no highlighted plan")
	for entry: Array in [[1280, 720, 1.0], [720, 480, 1.5]]:
		root.size = Vector2i(entry[0], entry[1])
		root.content_scale_factor = entry[2]
		await settle()
		var available := root.get_visible_rect().size
		widget.position = Vector2(16, 36)
		widget.size.x = available.x-32
		widget.fit_width(available.x-32)
		widget.apply_choice(recorded, true)
		await settle()
		print("choice layout: window=", entry, "; logical=", available, "; panel=", widget.size)
		expect(widget.get_combined_minimum_size().x <= available.x-32, "all choices fit the available width at " + str(entry))
		expect(widget.get_global_rect().end.y < available.y-16, "all choices and Continue stay on-screen at " + str(entry))
		for id: String in widget.option_buttons:
			var button: Button = widget.option_buttons[id]
			expect(widget.get_global_rect().encloses(button.get_global_rect()), "each approach remains visible inside its panel at " + str(entry))
			expect(button.size.y >= widget._content[id].lines.get_combined_minimum_size().y+16, "button height includes its complete wrapped text")
	var args := OS.get_cmdline_user_args()
	var render_index := args.find("--render")
	if render_index >= 0 and render_index+1 < args.size() and DisplayServer.get_name() != "headless":
		await _render(widget, recorded, args[render_index+1])
	widget.reset()
	widget._choose("repair", "run-b:plan-1")
	widget._continue("run-b:plan-1")
	expect(not widget.visible and requests.size() == 2 and continues.size() == 1, "reset hides the panel and rejects outstanding controls")
	host.queue_free()
	await process_frame
	print("campaign choice: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func _render(widget: Control, recorded: Dictionary, folder: String) -> void:
	DirAccess.make_dir_recursive_absolute(folder)
	for entry: Array in [[1280, 720, 1.0, false], [720, 480, 1.5, false], [720, 480, 1.5, true]]:
		root.size = Vector2i(entry[0], entry[1])
		root.content_scale_factor = entry[2]
		await settle()
		widget.size.x = root.get_visible_rect().size.x-32
		widget.call("fit_width", widget.size.x)
		widget.call("apply_choice", recorded if entry[3] else payload("proof:plan"), entry[3])
		await settle()
		await RenderingServer.frame_post_draw
		var file := "choice-%s-%s-%s.png" % [entry[0], roundi(float(entry[2])*100), "replay" if entry[3] else "live"]
		root.get_texture().get_image().save_png(folder.path_join(file))

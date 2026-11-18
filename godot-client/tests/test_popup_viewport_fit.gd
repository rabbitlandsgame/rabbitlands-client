extends SceneTree
## The server walkthrough's initial options must not leave a giant retained
## minimum that puts Dismiss off screen after declining the walkthrough.

var checks := 0
var failures := 0
var main: Control
var app: Node

func _init() -> void:
	run.call_deferred()

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func frames(count := 8) -> void:
	for index in count:
		await process_frame

func inside(control: Control) -> bool:
	return main.game_view.get_global_rect().grow(1).encloses(control.get_global_rect())

func check_layout(label: String) -> void:
	await frames()
	expect(main.popup_panel.is_visible_in_tree() and inside(main.popup_panel), label + ": popup fits viewport")
	expect(main.popup_dismiss.is_visible_in_tree() and inside(main.popup_dismiss), label + ": Dismiss is reachable")
	if main.popup_confirm.visible:
		expect(inside(main.popup_confirm), label + ": Send is reachable")
	var scroll: ScrollContainer = main.popup_panel.get_node("PopupContent/PopupScroll")
	expect(inside(scroll) and scroll.size.y > 0, label + ": the body stays within its allotted space")

func capture(name: String) -> void:
	var folder := OS.get_environment("RL_POPUP_FIT_CAPTURE_DIR")
	if folder.is_empty() or DisplayServer.get_name() == "headless":
		return
	DirAccess.make_dir_recursive_absolute(folder)
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(folder.path_join(name + ".png")) == OK,
		"saved " + name)

func sized(text: String) -> PackedByteArray:
	var bytes := text.to_utf8_buffer()
	return PackedByteArray([bytes.size()]) + bytes

func intro_payload() -> PackedByteArray:
	# The native Four Gates walkthrough INTRO, including its display-only lines.
	var body := "Twelve regions ring the lake. Mirrorhold counts its halls in reflections, Crownwater keeps a drowned king, the Whitehorn Range keeps the cold honest, and the Grey Moors keep whatever the barrows were given."
	var payload := PackedByteArray([160,15,0]) + sized("Nymara") + PackedByteArray([0,0]) + sized(body)
	for line: String in [
		"Eight peoples tell eight different stories about how the world began. All eight agree on one thing: the roads meet here, at Four Gates.",
		"You arrived carrying your name and nothing else. Gate Warden Ilyon will not ask you for more than that.",
		"Shall someone walk you through your first hour?"]:
		payload += PackedByteArray([EloriaProtocol.POPUP_DISPLAY_TEXT,0]) + sized(line)
	payload += PackedByteArray([EloriaProtocol.POPUP_TEXT_OPTION,0]) + sized("Show me the roads.") + PackedByteArray([1])
	payload += PackedByteArray([EloriaProtocol.POPUP_TEXT_OPTION,0]) + sized("I will find my own way.") + PackedByteArray([2])
	return payload

func show_intro() -> void:
	app.close_popup()
	app._on_packet(EloriaProtocol.ServerMessage.DISPLAY_POPUP, intro_payload())

func escape() -> void:
	var focused := root.gui_get_focus_owner()
	if focused != null:
		focused.release_focus()
	var event := InputEventKey.new()
	event.physical_keycode = KEY_ESCAPE
	event.keycode = KEY_ESCAPE
	event.pressed = true
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await frames(2)

func run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280,720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	main.set_process(false)
	app = root.get_node("AppState")
	app.authenticated = true
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	for window: Control in main.window_stack._windows:
		window.hide()
	await frames()
	show_intro()
	await check_layout("native INTRO at 1280x720")
	await capture("01-native-intro-1280x720")
	expect(app.popup.popup_id == 4000 and main.popup_options.get_child_count() == 5,
		"the actual decoded question keeps its display lines and both choices")
	var decline: Button = main.popup_options.get_child(4)
	var callback: Callable = decline.get_signal_connection_list(&"pressed")[0].callable
	expect(callback.get_bound_arguments() == [0,2], "declining keeps the native group and value")
	app._show_text_popup("Queued notice\nThis message must wait for the current choice.")
	expect(app.popup.popup_id == 4000 and app._pending_text_popups.size() == 1,
		"fitting never answers or replaces an unanswered question")
	app.close_popup()
	expect(main.popup_options.get_child_count() == 0 and app.popup.title == "Queued notice",
		"a queued replacement immediately detaches old option controls")
	app._show_text_popup("As You Like\n\nThe roads are marked and the gate is open.\n\nIf you change your mind, Gate Warden Ilyon will start the walkthrough at any time, or type #tutorial.")
	await check_layout("native DECLINED after INTRO")
	await capture("02-native-declined-1280x720")
	expect(main.popup_panel.size.y <= 340, "short replacement releases the previous content height")
	app.npc_dialogue = {"open":true,"name":"Ostrid Hollin","text":"Practice?","options":[]}
	app.state_changed.emit(&"npc_dialogue")
	app._on_packet(EloriaProtocol.ServerMessage.CLOSE_NPC_MENU, PackedByteArray())
	expect(not main.dialogue_panel.visible and not main.get_node("%DialogueBackdrop").visible
		and main.popup_panel.visible, "NPC close hides both NPC surfaces and preserves the unrelated popup")
	await escape()
	expect(not main.popup_panel.visible and not bool(app.popup.open), "native physical Escape dismisses the text popup")
	for viewport: Vector2i in [Vector2i(900,460), Vector2i(640,360)]:
		root.size = viewport
		await frames()
		show_intro()
		await check_layout("INTRO at " + str(viewport))
		app.popup = {"open":true,"popup_id":4100,"title":"Long instructions",
			"text":"Read the instructions before choosing. ".repeat(120),"options":[
				{"option_type":EloriaProtocol.POPUP_RADIO_OPTION,"group":3,"value":7,"label":"Protect the delivery"},
				{"option_type":EloriaProtocol.POPUP_TEXT_ENTRY,"group":4,"label":"A note for the driver"}]}
		app.state_changed.emit(&"popup")
		await check_layout("long question at " + str(viewport))
		var scroll: ScrollContainer = main.popup_panel.get_node("PopupContent/PopupScroll")
		expect(scroll.get_v_scroll_bar().max_value > scroll.size.y, "long instructions remain scrollable")
		scroll.scroll_vertical = ceili(scroll.get_v_scroll_bar().max_value)
		await frames()
		var radio: CheckBox = main.popup_options.get_child(0)
		radio.button_pressed = true
		expect(main._popup_radio_groups.get(3) == 7 and main._popup_entries.has(4)
			and app.popup.popup_id == 4100, "scrolling preserves radio and entry reply semantics")
		main.popup_dismiss.pressed.emit()
		expect(not bool(app.popup.open), "the visible Dismiss button closes without a reply")
	root.size = Vector2i(1280,720)
	await frames()
	show_intro()
	root.size = Vector2i(900,460)
	await check_layout("already-open question after resize")
	await capture("03-native-intro-short-after-resize")
	await escape()
	expect(not main.popup_panel.visible, "Escape also closes an unanswered choice after resizing")
	main.queue_free()
	await frames(2)
	print("POPUP VIEWPORT FIT: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)

extends SceneTree
## Exercise the actual button and bound action using real protocol encoders.
## Only the final socket write is recorded; no world or server is started.
var failures := 0
var checks := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func posture(frame: PackedByteArray, sitting: bool) -> bool:
	return frame == EloriaProtocol.set_sitting(sitting)

func run() -> void:
	create_timer(45).timeout.connect(func(): push_error("Sit control probe timed out"); quit(1))
	var network := root.get_node("Network")
	network.block_for_hud_preview()
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the offline transport recorder compiles")
	network.set_script(recorder)
	network.block_for_hud_preview()
	var app := root.get_node("AppState")
	app.authenticated = false
	var main = load("res://src/app/main.tscn").instantiate()
	main.set_script(load("res://tests/fixtures/offline_ui_main.gd"))
	root.add_child(main)
	for frame in range(8): await process_frame
	main.set_process(false)
	main.set_physics_process(false)
	main.login_panel.hide()
	main.game_view.show()
	main.chat_input.release_focus()
	app.authenticated = true
	app.local_actor_id = 1
	app.current_map = "landfall"
	app.actors = {1:{"actor_id":1,"x":310,"y":86,"health":40,"sitting":false}}
	network.move_intent_enabled = false
	var sent: Array = network.get("sent_frames")
	var shortcut := InputEventAction.new()
	shortcut.action = "toggle_sit"
	shortcut.pressed = true
	for source: String in ["button", "shortcut"]:
		app.actors[1].sitting = false
		main._keyboard_moving = true
		main._keyboard_intent_epoch = -1
		sent.clear()
		if source == "button": main.sit_button.pressed.emit()
		else: main._unhandled_input(shortcut)
		# This is the next frame's stop after movement keys are released or
		# Alt owns the keyboard. Before the fix it followed SIT with MOVE_TO.
		main._stop_keyboard_movement()
		expect(sent.size() == 2 and sent[0] == EloriaProtocol.move_to(310,86,false)
			and posture(sent[1], true),
			"%s cancels the legacy keyboard route before sitting, with no late move to stand back up" % source)
		expect(not main._keyboard_moving and main._keyboard_intent_epoch == -1,
			"%s retires the tracked keyboard motion" % source)
	# Server acknowledgements, rather than optimistic local posture changes,
	# determine what a subsequent press requests.
	app._on_packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([1,0,13]))
	sent.clear()
	main.sit_button.pressed.emit()
	expect(sent.size() == 1 and posture(sent[0], false),
		"an acknowledged seated player requests stand without a redundant movement packet")
	app._on_packet(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND, PackedByteArray([1,0,14]))
	sent.clear()
	main._unhandled_input(shortcut)
	expect(sent.size() == 1 and posture(sent[0], true),
		"an idle standing player requests sit through the bound action")
	app.authenticated = false
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("sit control: %d checks; %d failures" % [checks, failures])
	quit(1 if failures else 0)

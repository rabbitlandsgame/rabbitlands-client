extends SceneTree
## Exercise Main's existing approach route with a cave-mouth click and the
## real network encoders. Only the final socket write is recorded.
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func run() -> void:
	create_timer(60).timeout.connect(func(): push_error("Cave approach timed out"); quit(1))
	var network := root.get_node("Network")
	network.block_for_hud_preview()
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the isolated transport recorder compiles")
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
	app.authenticated = true
	app.local_actor_id = 1
	app.current_map = "landfall"
	app.campaign = {}
	app.actors = {1:{"x":310,"y":86,"health":40,"sitting":false}}
	app.map_objects = {59001:{"object_id":59001,"x":332,"y":86}}
	var mouth := MapObject3D.new()
	mouth.object_id = 59001
	mouth.server_tile = Vector2i(332,86)
	mouth.cave_entrance = true
	var sent: Array = network.get("sent_frames")
	# Releasing a tracked legacy key on the next frame used to send a stop
	# MOVE_TO after the new cave route, cancelling the click's approach.
	network.move_intent_enabled = false
	main._keyboard_moving = true
	main._keyboard_intent_epoch = -1
	main._activate_map_object(mouth, false)
	main._stop_keyboard_movement()
	expect(sent.size() == 2 and sent[0] == EloriaProtocol.move_to(310,86,false)
		and sent[1] == EloriaProtocol.move_to(332,86,false)
		and not main._keyboard_moving and main._keyboard_intent_epoch == -1
		and main._door_approach.get("object_id") == 59001,
		"a cave click retires legacy keyboard motion before its route, with no late origin move")
	# Modern held intent also releases before the new click route, without
	# leaving an intent that could be refreshed or released after the click.
	network.apply_move_intent_state({"enabled":true,"epoch":1,"keepalive_msec":1000})
	main._keyboard_moving = true
	main._keyboard_intent_epoch = 1
	sent.clear()
	main._activate_map_object(mouth, false)
	main._stop_keyboard_movement()
	expect(sent.size() == 2 and sent[0] == EloriaProtocol.move_intent(1, Vector2i.ZERO, false)
		and sent[1] == EloriaProtocol.move_to(332,86,false)
		and not main._keyboard_moving and main._keyboard_intent_epoch == -1
		and main._door_approach.get("object_id") == 59001,
		"a cave click releases modern held intent before its route and keeps the one-use approach")
	network.move_intent_enabled = false
	sent.clear()
	main._activate_map_object(mouth, false)
	expect(main._door_approach.get("object_id") == 59001 and sent.size() == 1,
		"one distant cave click starts a walk instead of an out-of-range use")
	app.actors[1].x = 326
	main._update_door_approach()
	main._update_door_approach()
	expect(main._door_approach.is_empty() and sent.size() == 2
		and int((sent[1] as PackedByteArray)[0]) == EloriaProtocol.ClientMessage.USE_MAP_OBJECT,
		"arrival uses the entrance once without a second click")
	app.actors[1].x = 310
	main._activate_map_object(mouth, false)
	network.move_to(Vector2i(300,80))
	var count := sent.size()
	app.actors[1].x = 326
	main._update_door_approach()
	expect(main._door_approach.is_empty() and sent.size() == count,
		"a replacement movement cancels the pending entrance action")
	app.actors[1].x = 310
	main._activate_map_object(mouth, false)
	network.apply_move_intent_state({"enabled":true,"epoch":1,"keepalive_msec":1000})
	main._update_keyboard_intent(Vector2i(1,0), false, Time.get_ticks_msec())
	expect(main._door_approach.is_empty(), "held keyboard movement cancels the pending entrance action")
	network.move_intent_enabled = false
	main._activate_map_object(mouth, false)
	app.current_map = "landfall_insides"
	main._update_door_approach()
	expect(main._door_approach.is_empty(), "a map change retires the pending entrance action")
	app.current_map = "landfall"
	app.actors[1].x = 326
	count = sent.size()
	main._activate_map_object(mouth, false)
	expect(main._door_approach.is_empty() and sent.size() == count + 1,
		"an entrance already in reach is used immediately")
	# A nearby use can change map immediately; its late keyboard stop must
	# not become an old-coordinate movement order on the destination map.
	main._keyboard_moving = true
	main._keyboard_intent_epoch = -1
	sent.clear()
	main._activate_map_object(mouth, false)
	main._stop_keyboard_movement()
	expect(sent.size() == 2 and sent[0] == EloriaProtocol.move_to(326,86,false)
		and int((sent[1] as PackedByteArray)[0]) == EloriaProtocol.ClientMessage.USE_MAP_OBJECT
		and main._door_approach.is_empty() and not main._keyboard_moving,
		"an immediate entrance use retires legacy movement before teleporting, with no late old-map stop")
	app.actors[1].x = 310
	main._activate_map_object(mouth, false)
	main._door_approach.until_msec = 0
	count = app.chat_lines.size()
	main._update_door_approach()
	main._update_door_approach()
	expect(main._door_approach.is_empty() and app.chat_lines.size() == count + 1
		and str(app.chat_lines.back().get("text", "")).contains("Could not reach the entrance"),
		"an unreachable entrance explains the failure once and stops retrying")
	mouth.free()
	app.authenticated = false
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("cave entrance approach: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

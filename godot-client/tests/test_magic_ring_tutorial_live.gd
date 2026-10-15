extends SceneTree
## Run only against the disposable account/server from run-magic-tutorial.ps1 -Check.
var main: Control
var state: Node
var network: Node
func _init() -> void: call_deferred("run")
func until(predicate: Callable, label: String) -> bool:
	var deadline := Time.get_ticks_msec()+40000
	while not predicate.call() and Time.get_ticks_msec()<deadline: await process_frame
	if not predicate.call():
		push_error("FAIL: " + label)
		quit(1)
		return false
	return true
func key(code: Key, pressed := true) -> InputEventKey:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.location = KEY_LOCATION_LEFT if code == KEY_SHIFT else KEY_LOCATION_UNSPECIFIED
	event.shift_pressed = true
	event.pressed = pressed
	return event
func run() -> void:
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	state = root.get_node("AppState")
	network = root.get_node("Network")
	main.user_edit.text = "RingStudent"
	main._on_connect_pressed()
	if not await until(func(): return network._state == "connected", "connect to disposable server"): return
	network.login("RingStudent","ringpractice")
	if not await until(func(): return state.authenticated, "log in to disposable account"): return
	network.send_chat("#tutorial magic")
	if not await until(func(): return state.lantern_tutorial.get("ring_training",false), "server negotiates ring training"): return
	if not await until(func(): return main._can_open_spell_wheel(), "world permits ring input"): return
	# Both routes into the book must notify the real server.
	main.casting_bar.open_book.emit()
	if not await until(func(): return state.lantern_tutorial.get("control") == "spell_ring", "book opening begins the ring introduction"): return
	main.spells_window.close()
	root.push_input(key(KEY_SHIFT),true)
	if not await until(func(): return str(state.lantern_tutorial.get("hint","")).contains("hover Healing"), "Left Shift opening reaches the server"): return
	root.push_input(key(KEY_1),true)
	if not await until(func(): return str(state.lantern_tutorial.get("hint","")).contains("Browse without casting"), "class shortcut reaches the server"): return
	root.push_input(key(KEY_SHIFT,false),true)
	if not await until(func(): return state.lantern_tutorial.get("key") == "borrow", "release completes the introduction on the server"): return
	if main.spell_wheel.visible or not main.magic_selection.pending.is_empty():
		push_error("FAIL: orientation must leave no open ring or armed spell")
		quit(1)
		return
	network.disconnect_from_server()
	main.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("live magic ring tutorial: PASS")
	quit(0)

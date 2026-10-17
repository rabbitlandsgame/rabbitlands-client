extends SceneTree
## Exercise real input routing while capturing requests before transport.

class CaptureNetwork extends EloriaNetworkClient:
	var outgoing: Array[PackedByteArray] = []
	func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
		outgoing.append(frame.duplicate())
		return OK

const SLOT_KEYS: Array[Key] = [KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6,
	KEY_7, KEY_8, KEY_9, KEY_0, KEY_MINUS, KEY_EQUAL]
const BLOCKING_PANELS := ["full_map", "storage_panel", "dialogue_panel",
	"trade_panel", "settings_panel", "item_lists_panel", "console_panel"]

var main: Control
var network: Node
var casts: Array[Dictionary] = []
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func run() -> void:
	network = root.get_node("Network")
	network.set_process(false)
	network.set_script(CaptureNetwork)
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	# Saved player bindings must not change which defaults this test exercises.
	InputMap.load_from_project_settings()
	main.get("game_view").show()
	main.get_node("LoginPanel").hide()
	var state: Node = root.get_node("AppState")
	var inventory := {}
	for slot in range(8):
		inventory[slot] = {"slot": slot, "inventory_usable": true, "quantity": 9}
	state.set("inventory", inventory)
	state.set("inventory_cooldowns", {})
	state.set("selected_actor_id", -1)
	main.get("spell_loadout").path = "user://quick-slot-test.cfg"
	for slot in range(SLOT_KEYS.size()):
		main.get("spell_loadout").assign_slot(slot, 0, 1)
	main.get("magic_selection").request_sender = func(data: Dictionary) -> Error:
		casts.append(data.duplicate(true))
		return OK
	# Old settings and newly saved defaults must keep the Ctrl aliases.
	var settings: Control = main.get("settings_window")
	settings.call("restore_bindings", {"quick_item_4": "4"})
	var stored: Dictionary = settings.call("stored_bindings")
	InputMap.action_erase_events("quick_item_4")
	settings.call("restore_bindings", stored)
	main.call("_sync_quick_slots")
	expect(str(settings.call("binding_text", "quick_item_4")) == "4 / Ctrl+4",
		"default item aliases survive saving and restoring")
	expect(str((settings.get("binding_rows") as Dictionary)["quick_item_4"].text) == "4 / Ctrl+4",
		"settings show both item shortcuts")
	var item_button: Button = (main.get("quick_slot_buttons") as Array)[3]
	expect(item_button.tooltip_text.contains("Shortcut: 4 / Ctrl+4"),
		"quick item tooltip shows both active shortcuts")
	reset_windows()
	for code: Key in SLOT_KEYS:
		await press_and_expect(key(code, true), 1, -1, "unblocked Alt+" + OS.get_keycode_string(code))
	for panel: String in BLOCKING_PANELS:
		reset_windows()
		if panel == "full_map":
			root.push_input(key(KEY_M), true)
			root.push_input(key(KEY_M, false, false), true)
		else:
			(main.get(panel) as Control).show()
		root.gui_release_focus()
		expect(not main.call("_can_open_spell_wheel"), panel + " blocks casting")
		for code: Key in SLOT_KEYS:
			await press_and_expect(key(code, true), 0, -1, panel + " / Alt+" + OS.get_keycode_string(code))
	# The spell selection popup and focused chat also block spell shortcuts.
	reset_windows()
	main.get("magic_selection").popup.show()
	expect(not main.call("_can_open_spell_wheel"), "spell popup blocks casting")
	await press_and_expect(key(KEY_1, true), 0, -1, "spell popup / Alt+1")
	reset_windows()
	main.get("chat_input").show()
	main.get("chat_input").grab_focus()
	expect(not main.call("_can_open_spell_wheel"), "text entry blocks casting")
	await press_and_expect(key(KEY_1, true), 0, -1, "text entry / Alt+1")
	# Both item shortcuts work, including Ctrl+4 in the tutorial and on the map.
	for blocked: bool in [false, true]:
		reset_windows()
		main.get("full_map").visible = blocked
		for slot in range(8):
			await press_and_expect(key(SLOT_KEYS[slot]), 0, slot, "plain item key %d / map=%s" % [slot + 1, blocked])
			var ctrl_key := key(SLOT_KEYS[slot])
			ctrl_key.ctrl_pressed = true
			await press_and_expect(ctrl_key, 0, slot, "Ctrl+%d item / map=%s" % [slot + 1, blocked])
	reset_windows()
	var ctrl_four := key(KEY_4)
	ctrl_four.ctrl_pressed = true
	main.get("chat_input").show()
	main.get("chat_input").grab_focus()
	await press_and_expect(ctrl_four, 0, -1, "chat owns Ctrl+4 while typing")
	reset_windows()
	inventory[3]["inventory_usable"] = false
	await press_and_expect(ctrl_four, 0, -1, "Ctrl+4 cannot use an unusable item")
	inventory[3]["inventory_usable"] = true
	state.set("inventory_cooldowns", {3: {"end_msec": Time.get_ticks_msec() + 60000}})
	await press_and_expect(ctrl_four, 0, -1, "Ctrl+4 respects item cooldown")
	state.set("inventory_cooldowns", {})
	# A custom binding replaces both defaults and is reflected in the tooltip.
	settings.call("restore_bindings", {"quick_item_4": "F8"})
	main.call("_sync_quick_slots")
	expect(item_button.tooltip_text.contains("Shortcut: F8")
		and not item_button.tooltip_text.contains("Ctrl+4"), "tooltip follows custom binding")
	await press_and_expect(key(KEY_4), 0, -1, "rebound item no longer uses 4")
	await press_and_expect(ctrl_four, 0, -1, "rebound item no longer uses Ctrl+4")
	await press_and_expect(key(KEY_F8), 0, 3, "restored custom item shortcut")
	settings.call("restore_bindings", {"quick_item_4": "4"})
	# Exact item matching must still protect Alt+1 after its spell is rebound.
	main.get("full_map").show()
	InputMap.action_erase_events("quick_spell_1")
	InputMap.action_add_event("quick_spell_1", key(KEY_F9))
	await press_and_expect(key(KEY_1, true), 0, -1, "rebound spell / Alt+1")
	await press_and_expect(key(KEY_F9), 0, -1, "blocked rebound spell")
	# Deliberately rebound item shortcuts still work with their exact modifiers.
	var item_key := key(KEY_1)
	item_key.ctrl_pressed = true
	InputMap.action_erase_events("quick_item_1")
	InputMap.action_add_event("quick_item_1", item_key)
	await press_and_expect(item_key, 0, 0, "rebound Ctrl+1 item")
	item_key = key(KEY_1, true)
	item_key.ctrl_pressed = true
	await press_and_expect(item_key, 0, -1, "extra Alt modifier cannot use rebound item")
	# A matching spell shortcut owns the event even with an overlapping item bind.
	InputMap.action_erase_events("quick_spell_1")
	InputMap.action_add_event("quick_spell_1", key(KEY_1, true))
	InputMap.action_erase_events("quick_item_1")
	InputMap.action_add_event("quick_item_1", key(KEY_1, true))
	await press_and_expect(key(KEY_1, true), 0, -1, "blocked spell owns overlapping shortcut")
	main.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("QUICK SLOT SHORTCUTS: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func reset_windows() -> void:
	for panel: String in BLOCKING_PANELS:
		(main.get(panel) as Control).hide()
	main.get("magic_selection").popup.hide()
	main.get("spell_wheel").reset()
	root.gui_release_focus()

func key(code: Key, alt := false, pressed := true) -> InputEventKey:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.pressed = pressed
	event.alt_pressed = alt
	return event

func press_and_expect(event: InputEventKey, expected_casts: int, item_slot: int, label: String) -> void:
	casts.clear()
	network.get("outgoing").clear()
	root.push_input(event, true)
	var release := event.duplicate() as InputEventKey
	release.pressed = false
	root.push_input(release, true)
	await process_frame
	var expected_frames: Array[PackedByteArray] = []
	if item_slot >= 0:
		expected_frames.append(EloriaProtocol.use_inventory_item(item_slot))
	expect(casts.size() == expected_casts, label + " / spell requests")
	expect(network.get("outgoing") == expected_frames, label + " / item requests")

func expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + label)

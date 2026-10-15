extends SceneTree
## Real party packets must update the roster without overriding dismissal.

var failures := 0
var windows: Control
var app_state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	app_state = root.get_node("/root/AppState")
	windows = (load("res://src/ui/extension_windows.gd") as GDScript).new() as Control
	root.add_child(windows)
	await process_frame
	_expect(not windows.party_panel.visible, "no party window opens without membership")
	_send_party(120)
	await process_frame
	_expect(windows.party_panel.visible and windows.party_rows.get_child_count() == 2,
		"joining opens the party roster")
	var close: Button = windows.party_panel.get_node("Body/Header/Close") as Button
	close.pressed.emit()
	_send_party(119)
	await process_frame
	_expect(not windows.party_panel.visible, "Close stays closed through a health update")
	windows.sync_all()
	_expect(not windows.party_panel.visible, "HUD resync respects dismissal")
	windows.toggle_party()
	await process_frame
	var health: ProgressBar = windows.party_rows.get_child(0).get_node("Vitals/Health") as ProgressBar
	_expect(windows.party_panel.visible and windows.party_header.text.contains("1 of 2")
		and is_equal_approx(health.value, 119.0), "reopening shows the latest roster and health")
	_expect(windows.close_top(), "the cancel cascade closes the party window")
	_send_party(118)
	await process_frame
	_expect(not windows.party_panel.visible, "updates respect cancel-cascade dismissal")
	windows.toggle_party()
	windows.toggle_party()
	_send_party(117)
	await process_frame
	_expect(not windows.party_panel.visible, "updates respect the party HUD toggle")
	_send_hex("00004b656c6c616e004b00")
	await process_frame
	_expect(windows.party_panel.visible and windows.party_invite_row.visible,
		"a new invitation opens its answer buttons")
	close.pressed.emit()
	_send_hex("00004b656c6c616e004600")
	await process_frame
	_expect(not windows.party_panel.visible, "invitation countdowns respect dismissal")
	windows.toggle_party()
	_expect(windows.party_panel.visible and windows.party_invite_row.visible,
		"a dismissed invitation can be reopened")
	_send_hex("0000000000")
	await process_frame
	_expect(not windows.party_panel.visible, "no party or invitation hides the window")
	_send_hex("00004b656c6c616e004b00")
	await process_frame
	_expect(windows.party_panel.visible, "a later invitation from the same player opens again")
	_send_hex("0000000000")
	await process_frame
	windows.toggle_party()
	_expect(windows.party_panel.visible and windows.party_header.text == "No party",
		"manual opening without membership explains the empty state")
	windows.queue_free()
	await process_frame
	print("party visibility tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _send_party(health: int) -> void:
	_send_hex("010203%02x00b40028003c000003e0014b656c6c616e00666f75725f67617465730004" % health
		+ "5a0096000a0037009a00b6004d6172656e006d6972726f72686f6c6400000000")

func _send_hex(value: String) -> void:
	var payload := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		payload.append(value.substr(index, 2).hex_to_int())
	app_state.call("_on_packet", 240, payload)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)

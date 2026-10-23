extends SceneTree
## Invitation answers must remain available when the HUD hides the roster.

const SETTINGS_PATH := "res://test-artifacts/party-invitation-hud/settings.cfg"
var failures := 0
var main: Control
var app: Node

func _init() -> void:
	call_deferred("_run")

func _frames() -> void:
	for index: int in 4:
		await process_frame

func _run() -> void:
	root.size = Vector2i(1280, 720)
	app = root.get_node("/root/AppState")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = SETTINGS_PATH
	root.add_child(main)
	await _frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var workspace: Control = main.hud_workspace
	var windows: Control = main.extension_windows
	workspace.choose_preset("heritage", true)
	await _frames()
	_expect(not workspace.model.working.parts.party.enabled,
		"Classic keeps its saved hidden-roster preference")
	_expect(not windows.party_panel.is_visible_in_tree(),
		"a disabled roster stays hidden without an invitation")
	_send_hex("00004b656c6c616e004b00")
	await _frames()
	_expect(windows.party_panel.is_visible_in_tree() and windows.party_invite_row.is_visible_in_tree(),
		"a real invitation packet stays visible through HUD processing")
	var accept: Button = windows.party_invite_row.get_node("PartyAccept")
	var decline: Button = windows.party_invite_row.get_node("PartyDecline")
	_expect(accept.is_visible_in_tree() and decline.is_visible_in_tree()
		and root.get_visible_rect().encloses(accept.get_global_rect())
		and root.get_visible_rect().encloses(decline.get_global_rect()),
		"both invitation answers are visible inside the viewport")
	workspace.apply_layout()
	await _frames()
	_expect(windows.party_panel.is_visible_in_tree(),
		"reapplying the HUD layout preserves the pending invitation")
	_expect(not workspace.model.working.parts.party.enabled,
		"showing an invitation does not enable the roster preference")
	windows.party_panel.get_node("Body/Header/Close").pressed.emit()
	_send_hex("00004b656c6c616e004600")
	await _frames()
	_expect(not windows.party_panel.visible,
		"an invitation refresh respects explicit dismissal")
	windows.toggle_party()
	await _frames()
	_expect(windows.party_panel.is_visible_in_tree(),
		"the Party toggle can reopen a pending invitation with the roster disabled")
	_send_hex("0000000000")
	await _frames()
	_expect(not windows.party_panel.visible,
		"clearing an invitation restores the hidden roster")
	_send_hex("00004b656c6c616e004b00")
	await _frames()
	_expect(windows.party_panel.is_visible_in_tree(),
		"another invitation from the same player opens again")
	_send_hex("0102037800b40028003c000003e0014b656c6c616e00666f75725f676174657300045a0096000a0037009a00b6004d6172656e006d6972726f72686f6c6400000000")
	await _frames()
	_expect(app.party.in_party and not windows.party_panel.visible,
		"acceptance restores the disabled roster without losing membership")
	_send_hex("0000000000")
	main.queue_free()
	await _frames()
	print("party invitation HUD tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _send_hex(value: String) -> void:
	var payload := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		payload.append(value.substr(index, 2).hex_to_int())
	app.call("_on_packet", 240, payload)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: ", label)

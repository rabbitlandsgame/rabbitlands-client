extends SceneTree
## Guards the guild window.
##
## Guilds were in the server for a long time with nothing drawing them, so the
## risk here is not that the window looks wrong - it is that it says something
## the server did not. Every payload below is the exact output of the server's
## own builder in `eloria/protocol.py`, and every button press is checked
## against the bytes it puts on the wire, because a button that sends almost
## the right command is a button that silently does nothing.

var failures := 0
## Everything the window asked the server to do, as text and as the frame that
## text becomes. `main.gd` hands the window `Network.send_chat`; this hands it
## the recorder instead, which is the same seam.
var sent: Array[String] = []
var frames: Array[PackedByteArray] = []

func _init() -> void:
	call_deferred("_run")

func _record(text: String) -> Error:
	sent.append(text)
	frames.append(EloriaProtocol.chat(text))
	return OK

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var game_view: Control = main.get_node("GameView") as Control
	game_view.show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var window: Control = main.get("guild_window") as Control
	var resource_rail: Control = main.get_node("GameView/ResourceHud") as Control
	if not _expect(window != null, "main.gd builds the guild window"):
		quit(failures)
		return
	window.call("configure", Callable(self, "_record"))
	await process_frame

	_expect(not bool(window.call("is_open")),
		"the guild window does not open itself")

	# --- a player with no guild ---------------------------------------------
	# The founding form, the price in the server's own numbers, and a
	# directory to apply from - which is the whole reason the directory is on
	# the wire, because #join_guild takes a long name nothing else here knows.
	app_state.call("_on_packet", 213, _hex(
		"01000000003075000027140000000000000000000000000000000100456c6f726961"
		+ "2056616e6775617264000100454c4f00456c6f7269612056616e6775617264000200"
		+ "02000072656400126461726b5f626c756500"))
	window.call("toggle")
	await process_frame
	_expect(bool(window.call("is_open")), "the key opens it")
	_expect(str(window.get("header").text).contains("no guild")
		and window.get("found_row").visible
		and str(window.get("found_cost").text).contains("30000")
		and str(window.get("found_cost").text).contains("39"),
		"a guildless player is told the price of founding one: "
			+ str(window.get("found_cost").text))
	_expect(str(window.get("pending_label").text).contains("Eloria Vanguard"),
		"and which guild they have already applied to")
	var directory: VBoxContainer = window.get("directory_rows") as VBoxContainer
	_expect(directory.get_child_count() == 1
		and directory.get_node("GuildELO/Apply") != null,
		"every guild in the directory can be applied to")
	(directory.get_node("GuildELO/Apply") as Button).pressed.emit()
	_expect_sent("#join_guild Eloria Vanguard", "Apply sends the long name")

	var found_tag: LineEdit = window.get("found_tag") as LineEdit
	found_tag.text = "ELO"
	_press(window, "GuildFound")
	_expect_sent("#make_guild ELO", "Found sends the tag that was typed")
	_expect(found_tag.text.is_empty(),
		"the tag field clears, so a second press cannot found a second guild")

	# --- the owner of a guild -----------------------------------------------
	app_state.call("_on_packet", 213, _hex(
		"010114ff00307500002714454c4f00456c6f7269612056616e6775617264004b656c"
		+ "6c616e004d7573746572206174206475736b2e00412074657374696e67206775696c"
		+ "640041736b20616e206f6666696365720068747470733a2f2f6578616d706c652e74"
		+ "65737400020014074b656c6c616e0005004d6172656e000100546f6d610001005249"
		+ "5600526976616c204775696c64000100125249560000000200454c4f00456c6f7269"
		+ "612056616e677561726400020052495600526976616c204775696c64000100020000"
		+ "72656400126461726b5f626c756500"))
	await process_frame
	_expect(str(window.get("header").text).contains("ELO")
		and str(window.get("header").text).contains("Eloria Vanguard")
		and str(window.get("header").text).contains("20"),
		"the header names the guild, its owner and the reader's rank")
	_expect(window.get("motd").visible
		and str(window.get("motd").text) == "Muster at dusk.",
		"the message of the day is shown when there is one")
	_expect(not window.get("found_row").visible,
		"a player in a guild is not offered the founding form")

	var members: VBoxContainer = window.get("member_rows") as VBoxContainer
	_expect(members.get_child_count() == 2,
		"every member has a row, present or not")
	_expect(_row_text(members.get_node("MemberKellan") as Control).contains("owner")
		and _row_text(members.get_node("MemberKellan") as Control).contains("you"),
		"the reader's own row and the owner's row are both marked")
	var absent: Control = members.get_node("MemberMaren") as Control
	_expect(_row_text(absent).contains("offline")
		and _row_text(absent).contains("rank 5"),
		"a member who is not here keeps their row and says so: "
			+ _row_text(absent))

	# Every control on a member's row, against the bytes it sends.
	(absent.get_node("Promote") as Button).pressed.emit()
	_expect_sent("#change_rank Maren 6", "Promote asks for one rank higher")
	(absent.get_node("Demote") as Button).pressed.emit()
	_expect_sent("#change_rank Maren 4", "Demote asks for one rank lower")
	(absent.get_node("Remove") as Button).pressed.emit()
	_expect_sent("#remove Maren", "Remove sends the command #remove is")
	(absent.get_node("HandOver") as Button).pressed.emit()
	_expect_sent("#change_owner Maren", "Hand over transfers the guild")
	_expect(not (members.get_node("MemberKellan") as Control).has_node("Remove"),
		"nobody is offered a button that removes the owner")

	var applicants: VBoxContainer = window.get("applicant_rows") as VBoxContainer
	_expect(applicants.get_child_count() == 1
		and window.get("applicant_title").visible,
		"somebody who may accept is shown the queue")
	(applicants.get_node("ApplicantToma/Accept") as Button).pressed.emit()
	_expect_sent("#accept Toma", "Accept takes the named applicant in")

	_expect(window.get("disband_button").visible
		and not window.get("leave_button").visible,
		"the owner is offered Disband and not Leave: they cannot simply go")
	_press(window, "GuildDisband")
	_expect_sent("#destroy_guild", "Disband sends #destroy_guild")

	# The six text fields, filled from the state and set by the command each
	# one belongs to.
	var motd_edit: LineEdit = (window.get("field_edits") as Dictionary)["#set_motd"]
	_expect(motd_edit.text == "Muster at dusk.",
		"an editable field is filled from the server's own value")
	motd_edit.text = "Muster at dawn."
	((window.get("field_rows") as Dictionary)["#set_motd"]
		as Control).get_node("Set").pressed.emit()
	_expect_sent("#set_motd Muster at dawn.", "Set sends the field's command")
	var name_row: Control = (window.get("field_rows") as Dictionary)["#set_name"]
	_expect(name_row.visible, "the owner may rename the guild")

	# Allies, and the colours this guild has chosen for other guilds' tags.
	var allies: VBoxContainer = window.get("ally_rows") as VBoxContainer
	_expect(allies.get_child_count() == 1
		and _row_text(allies.get_node("AllyRIV") as Control).contains("Rival Guild"),
		"an ally is named by tag and by name")
	(allies.get_node("AllyRIV/Unally") as Button).pressed.emit()
	_expect_sent("#unset_ally_guild RIV", "Unally drops the alliance")
	var colours: VBoxContainer = window.get("colour_rows") as VBoxContainer
	_expect(colours.get_child_count() == 1
		and colours.get_node("ColourRIV") != null,
		"the guild's chosen tag colours are shown")

	# The colour picker offers the server's own words, because #set_guild_color
	# takes a word and a list written into this client would go stale.
	var picker: OptionButton = window.get("colour_choice") as OptionButton
	_expect(picker.item_count == 2 and picker.get_item_text(0) == "red"
		and picker.get_item_text(1) == "dark_blue",
		"the colour picker is filled from the packet")
	picker.select(1)
	(directory.get_node("GuildRIV/Colour") as Button).pressed.emit()
	_expect_sent("#set_guild_color RIV dark_blue",
		"the colour button names the guild and the chosen word")
	# The directory's alliance button reads the state rather than always
	# offering to ally: RIV is an ally here, so the offer is to drop it.
	_expect((directory.get_node("GuildRIV/Ally") as Button).text == "Unally",
		"a guild already allied is offered the opposite")
	_expect(not directory.get_node("GuildELO").has_node("Ally"),
		"a guild cannot ally itself, so the button is not there to try")
	_expect(not directory.get_node("GuildELO").has_node("Apply"),
		"a player already in a guild is not offered a way to apply to another")

	# The same guild, as the server restates it once the alliance is gone.
	app_state.call("_on_packet", 213, _hex(
		"010114ff00307500002714454c4f00456c6f7269612056616e6775617264004b656c"
		+ "6c616e004d7573746572206174206475736b2e00412074657374696e67206775696c"
		+ "640041736b20616e206f6666696365720068747470733a2f2f6578616d706c652e74"
		+ "65737400020014074b656c6c616e0005004d6172656e000100546f6d610000000000"
		+ "00000200454c4f00456c6f7269612056616e67756172640002005249560052697661"
		+ "6c204775696c6400010002000072656400126461726b5f626c756500"))
	await process_frame
	directory = window.get("directory_rows") as VBoxContainer
	_expect((window.get("ally_rows") as VBoxContainer).get_child_count() == 0,
		"the allies tab follows the server rather than the button that was pressed")
	(directory.get_node("GuildRIV/Ally") as Button).pressed.emit()
	_expect_sent("#set_ally_guild RIV", "and the offer becomes Ally again")

	# Guild chat, which is the one thing on this window that is not a state.
	var say: LineEdit = window.get("say_entry") as LineEdit
	say.text = "muster at the north gate"
	_press(window, "GuildSay")
	_expect_sent("#gm muster at the north gate", "Say sends #gm")
	_expect(say.text.is_empty(), "the box clears rather than repeating itself")
	_expect_bytes("the command reaches the wire as a chat frame",
		frames[frames.size() - 1],
		EloriaProtocol.chat("#gm muster at the north gate"))

	# --- a plain member ------------------------------------------------------
	# Rank 5, no powers beyond talking. Nothing that would be refused may be
	# on screen: the packet says what this reader may do, and the window is
	# only allowed to draw that.
	app_state.call("_on_packet", 213, _hex(
		"0101050301307500002714454c4f00456c6f7269612056616e6775617264004b656c"
		+ "6c616e0000000000020014054b656c6c616e0005034d6172656e0000000000000000"
		+ "000100454c4f00456c6f7269612056616e677561726400020001000072656400"))
	await process_frame
	members = window.get("member_rows") as VBoxContainer
	_expect(not (members.get_node("MemberMaren") as Control).has_node("Promote")
		and not (members.get_node("MemberKellan") as Control).has_node("HandOver"),
		"a rank-5 member is offered nothing they cannot do")
	_expect(window.get("leave_button").visible
		and not window.get("disband_button").visible,
		"a member who does not own the guild is offered Leave and not Disband")
	_expect(not window.get("applicant_title").visible,
		"the applicant queue is not shown to somebody who cannot accept")
	_expect(not ((window.get("field_rows") as Dictionary)["#set_motd"]
		as Control).visible,
		"nor is the field they may not set")
	_expect(window.get("say_row").visible, "but a rank-5 member may talk")
	_press(window, "GuildLeave")
	_expect_sent("#leave_guild",
		"Leave sends it once; the second one is the server's own confirmation")

	# --- the window on screen ------------------------------------------------
	var rect: Rect2 = (window.get("panel") as Control).get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 and rect.end.y <= 720.0,
		"it fits within 1280x720: %s" % rect)
	_expect(not rect.intersects(resource_rail.get_global_rect()),
		"it does not cover the fixed resource rail")

	# --- the guild chat tab --------------------------------------------------
	# `#gm` arrives on the legacy CHAT_GM channel, where it used to be findable
	# only by reading past everything else in View All.
	var chat_output: RichTextLabel = main.get_node(
		"%ChatOutput") as RichTextLabel
	app_state.call("_on_packet", 0, _chat_line(2, "#GM from Kellan: at the gate"))
	app_state.call("_on_packet", 0, _chat_line(0, "somebody nearby says hello"))
	main.call("_on_chat_tab_pressed", "guild")
	await process_frame
	var guild_tab_text: String = chat_output.get_parsed_text()
	_expect(guild_tab_text.contains("at the gate")
		and not guild_tab_text.contains("somebody nearby"),
		"the Guild tab shows guild chat and nothing else")
	main.call("_on_chat_tab_pressed", "all")
	await process_frame
	_expect(chat_output.get_parsed_text().contains("at the gate")
		and chat_output.get_parsed_text().contains("somebody nearby"),
		"and View All still shows both, because nothing was filtered away")

	# --- the cancel cascade --------------------------------------------------
	_expect(bool(window.call("is_open")), "the window is still open")
	var escape: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	escape.pressed = true
	main.call("_unhandled_input", escape)
	await process_frame
	_expect(not bool(window.call("is_open")), "cancel closes the guild window")

	# --- the binding ---------------------------------------------------------
	_expect(InputMap.has_action("toggle_guild"),
		"the guild window has a key of its own")
	var settings: Control = main.get("settings_window") as Control
	var bindable: Dictionary = settings.get("BINDABLE") as Dictionary
	_expect((bindable["Windows"] as Array).has("toggle_guild"),
		"and it is listed in Settings -> Controls, so it can be rebound")

	# --- a disconnect --------------------------------------------------------
	window.call("toggle")
	await process_frame
	app_state.call("_on_connection_state_changed", "disconnected")
	await process_frame
	_expect(not bool(window.call("is_open"))
		and not bool((app_state.get("guild") as Dictionary).get("in_guild", true)),
		"a disconnect closes the window and forgets whose guild it was")

	print("guild window tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

## Presses a button somewhere under the window's panel, by name.
func _press(window: Control, button_name: String) -> void:
	var found: Node = (window.get("panel") as Node).find_child(button_name, true, false)
	if found == null or not found is Button:
		failures += 1
		push_error("FAIL: no button named " + button_name)
		return
	(found as Button).pressed.emit()

func _expect_sent(command: String, label: String) -> void:
	var last: String = sent[sent.size() - 1] if not sent.is_empty() else ""
	_expect(last == command, "%s (sent %s, wanted %s)" % [label, last, command])

func _expect_bytes(label: String, actual: PackedByteArray,
		expected: PackedByteArray) -> void:
	_expect(actual == expected, label + ": " + actual.hex_encode())

## Every Label under one row, joined: the row is several controls, so
## asserting against any single one of them would pin the layout instead.
func _row_text(row: Control) -> String:
	var parts := PackedStringArray()
	for child: Node in row.get_children():
		if child is Label:
			parts.append((child as Label).text)
		elif child is Container:
			parts.append(_row_text(child as Control))
	return " ".join(parts)

## A RAW_TEXT payload: the channel byte, then the line, then its terminator.
func _chat_line(channel: int, text: String) -> PackedByteArray:
	var payload := PackedByteArray([channel])
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	return payload

func _hex(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

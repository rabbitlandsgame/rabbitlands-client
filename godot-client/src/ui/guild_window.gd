extends Control
## The guild window: everything a guild is, and everything you may do to it.
##
## Guilds have been in the server since early on - tables, ranks, allies,
## per-guild colours, guild chat - and until now nothing drew any of it. The
## roster was `#list_guild`, a column of chat that scrolled away; joining one
## meant somebody telling you its long name, because no screen in this client
## would say one. This is the surface that was missing, built the way the
## extension windows are: the server states the whole thing in `ELORIA_GUILD_
## STATE(213)` and this draws that snapshot and nothing else.
##
## Nothing here decides anything. Every button sends the chat command a player
## could have typed, so the window and the commands cannot drift apart, and
## every button that exists at all exists because the packet's permissions
## field said this reader may use it - the rank each power starts at is the
## server's and is never worked out here.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

const PANEL_SIZE := Vector2(640.0, 470.0)
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0
## Rank 20 is the owner's seat and is reached by `#change_owner`, so the
## highest rank this window's promote button will ask for is one below it.
const HIGHEST_GRANTABLE_RANK := 19

## Dim what is not here, the way the party window dims an absent member.
const ABSENT_TINT := Color(1.0, 1.0, 1.0, 0.45)

var panel: PanelContainer
var tabs: TabContainer
var header: Label
var motd: Label
var status: Label

# Roster tab.
var found_row: HBoxContainer
var found_cost: Label
var found_tag: LineEdit
var pending_label: Label
var member_rows: VBoxContainer
var applicant_title: Label
var applicant_rows: VBoxContainer
var actions_row: HBoxContainer
var leave_button: Button
var disband_button: Button
var say_row: HBoxContainer
var say_entry: LineEdit

# Guild tab: the six text fields, keyed by the command that sets each.
var field_edits: Dictionary = {}
var field_rows: Dictionary = {}

# Allies and directory tabs.
var ally_rows: VBoxContainer
var colour_rows: VBoxContainer
var colour_choice: OptionButton
var directory_rows: VBoxContainer

## What this window says to the server. `main.gd` hands it `Network.send_chat`;
## a test hands it a recorder, which is how "this button sends this command" is
## a fact rather than a hope.
var _send: Callable = Callable()
## The field the player is editing, so a server push does not overwrite what
## they are halfway through typing.
var _editing: String = ""

## The six editable fields, in the order they are drawn: the command that sets
## one, its label, which state field holds it, and the permission bit that
## decides whether this reader may.
const TEXT_FIELDS: Array[Array] = [
	["#set_name", "Name", "name", EloriaProtocol.GUILD_CAN_OWN],
	["#set_short_name", "Tag", "tag", EloriaProtocol.GUILD_CAN_RANK],
	["#set_motd", "Message of the day", "motd", EloriaProtocol.GUILD_CAN_TEXT],
	["#set_desc", "Description", "description", EloriaProtocol.GUILD_CAN_TEXT],
	["#set_join_info", "Joining", "join_info", EloriaProtocol.GUILD_CAN_TEXT],
	["#set_url", "Website", "url", EloriaProtocol.GUILD_CAN_TEXT],
]

func _ready() -> void:
	name = "GuildLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	AppState.state_changed.connect(_on_state_changed)
	sync()

## `main.gd` lends the window its one seam to the server. Everything the
## window does goes through this and nothing else.
func configure(send: Callable) -> void:
	_send = send

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	panel.visible = not panel.visible
	if panel.visible:
		panel.move_to_front()
		status.text = ""
		sync()
		# The window is only ever as current as the last push, and a player
		# who has been logged in for an hour may have missed one.
		_command("#guild_info")

func close() -> void:
	panel.hide()

func _on_state_changed(path: StringName) -> void:
	if path == &"guild":
		sync()
	elif path == &"connection" and AppState.connection_state == "disconnected":
		close()
		sync()

# --- drawing -----------------------------------------------------------------

func sync() -> void:
	var state: Dictionary = AppState.guild
	var in_guild: bool = bool(state.get("in_guild", false))
	var rank: int = int(state.get("rank", 0))
	var tag: String = str(state.get("tag", ""))

	header.text = ("[%s] %s   -   %s   -   your rank %d" % [tag,
		str(state.get("name", "")), str(state.get("owner", "")), rank]
		if in_guild else "You are in no guild")
	motd.text = str(state.get("motd", ""))
	motd.visible = in_guild and not motd.text.is_empty()

	_sync_founding(state, in_guild)
	_sync_members(state)
	_sync_applicants(state)
	_sync_fields(state, in_guild)
	_sync_allies(state)
	_sync_palette(state)
	_sync_directory(state, in_guild)

	leave_button.visible = AppState.guild_may(EloriaProtocol.GUILD_CAN_LEAVE)
	disband_button.visible = AppState.guild_may(EloriaProtocol.GUILD_CAN_OWN)
	say_row.visible = AppState.guild_may(EloriaProtocol.GUILD_CAN_CHAT)
	actions_row.visible = in_guild

## What founding one costs, in the server's own numbers. A window that named a
## price of its own would be wrong the day the server changed it.
func _sync_founding(state: Dictionary, in_guild: bool) -> void:
	found_row.visible = not in_guild
	pending_label.visible = not in_guild
	if in_guild:
		return
	found_cost.text = "Found a guild: %d gold and a skill of %d." % [
		int(state.get("create_cost", 0)), int(state.get("create_level", 0))]
	var pending: Array = state.get("pending", []) as Array
	pending_label.text = ("Applied to: " + ", ".join(_strings(pending))
		if not pending.is_empty()
		else "Apply from the Directory tab. Joining needs a skill of %d."
			% int(state.get("join_level", 0)))

func _sync_members(state: Dictionary) -> void:
	_clear(member_rows)
	var may_rank: bool = AppState.guild_may(EloriaProtocol.GUILD_CAN_RANK)
	var may_own: bool = AppState.guild_may(EloriaProtocol.GUILD_CAN_OWN)
	var own_rank: int = int(state.get("rank", 0))
	for raw: Variant in state.get("members", []) as Array:
		var member: Dictionary = raw as Dictionary
		member_rows.add_child(_member_row(member, may_rank, may_own, own_rank))

func _member_row(member: Dictionary, may_rank: bool, may_own: bool,
		own_rank: int) -> Control:
	var member_name: String = str(member.get("name", ""))
	var rank: int = int(member.get("rank", 0))
	var online: bool = bool(member.get("online", false))
	var is_self: bool = bool(member.get("is_self", false))
	var is_owner: bool = bool(member.get("owner", false))

	var row := HBoxContainer.new()
	row.name = "Member" + member_name
	var marks := ""
	if is_owner:
		marks += "  (owner)"
	if is_self:
		marks += "  (you)"
	var title := Label.new()
	title.name = "Name"
	title.text = member_name + marks
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# A row that has stopped being here should look like it, rather than
	# reading as somebody standing next to you.
	title.modulate = Color.WHITE if online else ABSENT_TINT
	row.add_child(title)
	var standing := Label.new()
	standing.name = "Standing"
	standing.text = "rank %d   %s" % [rank, "online" if online else "offline"]
	standing.modulate = title.modulate
	row.add_child(standing)

	# The owner's rank is a seat rather than a number, so nothing but
	# #change_owner moves it - and nobody demotes themselves by accident.
	var may_change: bool = may_rank and not is_owner and not is_self
	if may_change:
		# The server refuses a rank at or above the granter's own unless they
		# own the guild, so a button that would be refused is not offered.
		var ceiling: int = (HIGHEST_GRANTABLE_RANK if may_own
			else own_rank - 1)
		row.add_child(_row_button("Promote", "+",
			func() -> void: _command("#change_rank %s %d"
				% [member_name, rank + 1]),
			rank < mini(ceiling, HIGHEST_GRANTABLE_RANK)))
		row.add_child(_row_button("Demote", "-",
			func() -> void: _command("#change_rank %s %d"
				% [member_name, rank - 1]), rank > 0))
		row.add_child(_row_button("Remove", "Remove",
			func() -> void: _command("#remove " + member_name), true))
	if may_own and not is_self:
		row.add_child(_row_button("HandOver", "Hand over",
			func() -> void: _command("#change_owner " + member_name), true))
	return row

func _sync_applicants(state: Dictionary) -> void:
	_clear(applicant_rows)
	var applicants: Array = state.get("applicants", []) as Array
	# The queue is only sent to somebody who may act on it, so an empty one
	# here means there is nothing waiting rather than nothing to see.
	applicant_title.visible = AppState.guild_may(EloriaProtocol.GUILD_CAN_ACCEPT)
	applicant_title.text = "Waiting to join: %d" % applicants.size()
	for raw: Variant in applicants:
		var applicant: String = str(raw)
		var row := HBoxContainer.new()
		row.name = "Applicant" + applicant
		var title := Label.new()
		title.name = "Name"
		title.text = applicant
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(title)
		row.add_child(_row_button("Accept", "Accept",
			func() -> void: _command("#accept " + applicant), true))
		applicant_rows.add_child(row)

func _sync_fields(state: Dictionary, in_guild: bool) -> void:
	for entry: Array in TEXT_FIELDS:
		var command: String = str(entry[0])
		var edit: LineEdit = field_edits[command] as LineEdit
		var row: Control = field_rows[command] as Control
		row.visible = in_guild and AppState.guild_may(int(entry[3]))
		# Never over what somebody is in the middle of typing.
		if _editing != command:
			edit.text = str(state.get(str(entry[2]), ""))

func _sync_allies(state: Dictionary) -> void:
	_clear(ally_rows)
	var may_ally: bool = AppState.guild_may(EloriaProtocol.GUILD_CAN_ALLY)
	for raw: Variant in state.get("allies", []) as Array:
		var ally: Dictionary = raw as Dictionary
		var tag: String = str(ally.get("tag", ""))
		var row := HBoxContainer.new()
		row.name = "Ally" + tag
		var title := Label.new()
		title.name = "Name"
		title.text = "[%s] %s" % [tag, str(ally.get("name", ""))]
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(title)
		if may_ally:
			row.add_child(_row_button("Unally", "Unally",
				func() -> void: _command("#unset_ally_guild " + tag), true))
		ally_rows.add_child(row)

	_clear(colour_rows)
	for raw: Variant in state.get("colours", []) as Array:
		var colour: Dictionary = raw as Dictionary
		var swatch := Label.new()
		swatch.name = "Colour" + str(colour.get("tag", ""))
		swatch.text = "[%s]" % str(colour.get("tag", ""))
		# The palette is Eternal Lands' own, and the index is the server's
		# choice, so it is drawn rather than reinterpreted.
		swatch.modulate = EloriaProtocol.el_text_colour(
			int(colour.get("colour", 0)))
		colour_rows.add_child(swatch)

## The colour words the server accepts, offered as the server sent them. A
## picker built from a list written into this client would offer a colour the
## server refuses the first time that list changed.
func _sync_palette(state: Dictionary) -> void:
	var palette: Array = state.get("palette", []) as Array
	if colour_choice.item_count == palette.size():
		return
	colour_choice.clear()
	for index: int in range(palette.size()):
		var colour: Dictionary = palette[index] as Dictionary
		colour_choice.add_item(str(colour.get("name", "")), index)
		colour_choice.set_item_metadata(index, str(colour.get("name", "")))
	if palette.size() > 0:
		colour_choice.select(0)

func _sync_directory(state: Dictionary, in_guild: bool) -> void:
	_clear(directory_rows)
	var may_ally: bool = AppState.guild_may(EloriaProtocol.GUILD_CAN_ALLY)
	var own_tag: String = str(state.get("tag", ""))
	var allied: Dictionary = {}
	for raw: Variant in state.get("allies", []) as Array:
		allied[str((raw as Dictionary).get("tag", ""))] = true
	for raw: Variant in state.get("directory", []) as Array:
		var entry: Dictionary = raw as Dictionary
		var tag: String = str(entry.get("tag", ""))
		var long_name: String = str(entry.get("name", ""))
		var row := HBoxContainer.new()
		row.name = "Guild" + tag
		var title := Label.new()
		title.name = "Name"
		title.text = "[%s] %s   -   %d member(s)" % [tag, long_name,
			int(entry.get("members", 0))]
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(title)
		if not in_guild:
			# `#join_guild` takes the long name, which is the whole reason the
			# directory is on the wire: nothing else in the client knows one.
			row.add_child(_row_button("Apply", "Apply",
				func() -> void: _command("#join_guild " + long_name), true))
		if may_ally and tag != own_tag:
			row.add_child(_row_button("Ally",
				"Unally" if allied.has(tag) else "Ally",
				func() -> void: _command(
					("#unset_ally_guild " if allied.has(tag)
						else "#set_ally_guild ") + tag), true))
			row.add_child(_row_button("Colour", "Colour",
				func() -> void: _set_colour(tag), true))
		directory_rows.add_child(row)

# --- what the buttons say ----------------------------------------------------

func _set_colour(tag: String) -> void:
	if colour_choice.selected < 0:
		status.text = "The server has not sent a colour list."
		return
	# The word rather than the index: `#set_guild_color` takes a colour name,
	# and the words are the server's own, sent with the state.
	_command("#set_guild_color %s %s" % [tag,
		str(colour_choice.get_item_metadata(colour_choice.selected))])

func _on_found_pressed() -> void:
	var tag: String = found_tag.text.strip_edges()
	if tag.is_empty():
		status.text = "A guild needs a three or four letter tag."
		return
	_command("#make_guild " + tag)
	found_tag.clear()

func _on_say_pressed() -> void:
	var message: String = say_entry.text.strip_edges()
	if message.is_empty():
		return
	_command("#gm " + message)
	say_entry.clear()

func _on_field_set(command: String) -> void:
	var value: String = (field_edits[command] as LineEdit).text.strip_edges()
	if value.is_empty():
		status.text = "Nothing to set."
		return
	_editing = ""
	_command("%s %s" % [command, value])

## Everything this window does goes through here, so there is one place that
## knows the window only ever *asks*: the state it draws next is the server's
## answer, not an assumption about what the command did.
func _command(text: String) -> void:
	var error: int = OK
	if _send.is_null():
		error = Network.send_chat(text)
	else:
		error = int(_send.call(text))
	status.text = ("Sent; the window updates when the server answers."
		if error == OK else "Guild request failed: " + error_string(error))

# --- construction ------------------------------------------------------------

func _strings(values: Array) -> PackedStringArray:
	var out := PackedStringArray()
	for value: Variant in values:
		out.append(str(value))
	return out

func _clear(container: Node) -> void:
	for child: Node in container.get_children():
		container.remove_child(child)
		child.queue_free()

func _row_button(button_name: String, text: String, pressed: Callable,
		enabled: bool) -> Button:
	var button := Button.new()
	button.name = button_name
	button.text = text
	button.disabled = not enabled
	button.pressed.connect(pressed)
	return button

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "GuildWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.position = Vector2(
		(1280.0 - RESERVED_RIGHT_RAIL - PANEL_SIZE.x) * 0.5,
		(720.0 - PANEL_SIZE.y) * 0.5)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.z_index = 26
	panel.hide()
	add_child(panel)

	var body := VBoxContainer.new()
	body.name = "Body"
	panel.add_child(body)
	var title_row := HBoxContainer.new()
	title_row.name = "Header"
	body.add_child(title_row)
	WindowDrag.attach(panel, title_row)
	var title := Label.new()
	title.name = "GuildTitle"
	title.text = "Guild"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_row.add_child(title)
	var close_button := Button.new()
	close_button.name = "GuildClose"
	close_button.text = "X"
	close_button.pressed.connect(close)
	title_row.add_child(close_button)

	header = Label.new()
	header.name = "GuildHeader"
	body.add_child(header)
	motd = Label.new()
	motd.name = "GuildMotd"
	motd.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(motd)

	tabs = TabContainer.new()
	tabs.name = "GuildTabs"
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(tabs)
	_build_roster(_tab("Roster"))
	_build_fields(_tab("Guild"))
	_build_allies(_tab("Allies"))
	_build_directory(_tab("Directory"))

	status = Label.new()
	status.name = "GuildStatus"
	body.add_child(status)

func _tab(tab_name: String) -> VBoxContainer:
	var page := VBoxContainer.new()
	page.name = tab_name
	tabs.add_child(page)
	return page

func _build_roster(page: VBoxContainer) -> void:
	found_row = HBoxContainer.new()
	found_row.name = "GuildFoundRow"
	page.add_child(found_row)
	found_cost = Label.new()
	found_cost.name = "GuildFoundCost"
	found_cost.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	found_row.add_child(found_cost)
	found_tag = LineEdit.new()
	found_tag.name = "GuildFoundTag"
	found_tag.placeholder_text = "tag"
	found_tag.max_length = 4
	found_tag.custom_minimum_size = Vector2(72.0, 0.0)
	found_tag.text_submitted.connect(func(_text: String) -> void:
		_on_found_pressed())
	found_row.add_child(found_tag)
	var found_button := Button.new()
	found_button.name = "GuildFound"
	found_button.text = "Found"
	found_button.pressed.connect(_on_found_pressed)
	found_row.add_child(found_button)

	pending_label = Label.new()
	pending_label.name = "GuildPending"
	pending_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(pending_label)

	var scroll := ScrollContainer.new()
	scroll.name = "GuildRosterScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page.add_child(scroll)
	member_rows = VBoxContainer.new()
	member_rows.name = "GuildMembers"
	member_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(member_rows)

	applicant_title = Label.new()
	applicant_title.name = "GuildApplicantsTitle"
	page.add_child(applicant_title)
	applicant_rows = VBoxContainer.new()
	applicant_rows.name = "GuildApplicants"
	page.add_child(applicant_rows)

	actions_row = HBoxContainer.new()
	actions_row.name = "GuildActions"
	page.add_child(actions_row)
	leave_button = Button.new()
	leave_button.name = "GuildLeave"
	leave_button.text = "Leave guild"
	# The server asks for the second one, which is its confirmation and not
	# something this window should invent a dialogue for.
	leave_button.pressed.connect(func() -> void: _command("#leave_guild"))
	actions_row.add_child(leave_button)
	disband_button = Button.new()
	disband_button.name = "GuildDisband"
	disband_button.text = "Disband"
	disband_button.pressed.connect(func() -> void: _command("#destroy_guild"))
	actions_row.add_child(disband_button)
	var refresh := Button.new()
	refresh.name = "GuildRefresh"
	refresh.text = "Refresh"
	refresh.pressed.connect(func() -> void: _command("#guild_info"))
	actions_row.add_child(refresh)

	say_row = HBoxContainer.new()
	say_row.name = "GuildSayRow"
	page.add_child(say_row)
	var say_label := Label.new()
	say_label.name = "GuildSayLabel"
	say_label.text = "Guild chat"
	say_row.add_child(say_label)
	say_entry = LineEdit.new()
	say_entry.name = "GuildChatEntry"
	say_entry.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	say_entry.text_submitted.connect(func(_text: String) -> void:
		_on_say_pressed())
	say_row.add_child(say_entry)
	var say_button := Button.new()
	say_button.name = "GuildSay"
	say_button.text = "Say"
	say_button.pressed.connect(_on_say_pressed)
	say_row.add_child(say_button)

func _build_fields(page: VBoxContainer) -> void:
	for entry: Array in TEXT_FIELDS:
		var command: String = str(entry[0])
		var row := HBoxContainer.new()
		row.name = "Field" + command.substr(1)
		page.add_child(row)
		var label := Label.new()
		label.name = "Label"
		label.text = str(entry[1])
		label.custom_minimum_size = Vector2(140.0, 0.0)
		row.add_child(label)
		var edit := LineEdit.new()
		edit.name = "Edit"
		edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		edit.focus_entered.connect(func() -> void: _editing = command)
		edit.focus_exited.connect(func() -> void:
			if _editing == command:
				_editing = "")
		edit.text_submitted.connect(func(_text: String) -> void:
			_on_field_set(command))
		row.add_child(edit)
		var button := Button.new()
		button.name = "Set"
		button.text = "Set"
		button.pressed.connect(func() -> void: _on_field_set(command))
		row.add_child(button)
		field_edits[command] = edit
		field_rows[command] = row

func _build_allies(page: VBoxContainer) -> void:
	var ally_title := Label.new()
	ally_title.name = "GuildAlliesTitle"
	ally_title.text = "Allies"
	page.add_child(ally_title)
	ally_rows = VBoxContainer.new()
	ally_rows.name = "GuildAllies"
	ally_rows.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page.add_child(ally_rows)
	var colour_title := Label.new()
	colour_title.name = "GuildColoursTitle"
	colour_title.text = "Tag colours your guild has chosen"
	page.add_child(colour_title)
	colour_rows = VBoxContainer.new()
	colour_rows.name = "GuildColours"
	page.add_child(colour_rows)

func _build_directory(page: VBoxContainer) -> void:
	var picker_row := HBoxContainer.new()
	picker_row.name = "GuildColourPicker"
	page.add_child(picker_row)
	var picker_label := Label.new()
	picker_label.name = "Label"
	picker_label.text = "Colour to apply"
	picker_row.add_child(picker_label)
	colour_choice = OptionButton.new()
	colour_choice.name = "GuildColourChoice"
	picker_row.add_child(colour_choice)

	var scroll := ScrollContainer.new()
	scroll.name = "GuildDirectoryScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page.add_child(scroll)
	directory_rows = VBoxContainer.new()
	directory_rows.name = "GuildDirectory"
	directory_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(directory_rows)

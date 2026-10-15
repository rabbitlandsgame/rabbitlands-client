extends Control
## The reference windows: help, notes, links and the encyclopedia.
##
## The legacy client had ten of these, all XML- or file-driven, and this client
## had none. The four here are the ones that can be built honestly:
##
## * **Help** is generated from the client's own input map and console table,
##   so it can never drift from what the keys and commands actually are. A
##   help page maintained by hand goes stale the first time a key moves.
## * **Notes** is the player's own notepad, kept in the client's settings file.
## * **Links** collects the addresses the server has said in chat, so a URL
##   scrolling past is not lost. It reads what arrived; it invents nothing.
## * **Encyclopedia** is laid out the way Eternal Lands lays its own out - an
##   index of categories, a page of links per category and a page per entry -
##   and lives in its own script. Half of it is original Eloria reference text
##   and half is built from the client's own catalogues.
## * **Almanac** is the game date, the special day in force and what it does,
##   and the catalogue of days the server can roll - all of it read from
##   `ELORIA_ALMANAC_STATE(238)`. This is the rules-and-astrology page the
##   traceability matrix recorded as blocked: the server used to state both
##   only as chat lines, so the page could not be built without parsing prose.
##   Nothing on it is shipped in the client, because which days exist and what
##   each does is the server's to decide.
##
## * **Buddies** is who the player has asked to be told about, and who of them
##   is here now. The list belongs to the server - it states all of it at
##   login - so this page is a view of what arrived rather than a copy the
##   client keeps. Adding somebody does not tell them and does not need their
##   agreement: it is a bookmark, not a friendship. The add button asks the
##   server via whoever listens; the window itself sends nothing.
##
## Skills are still not a page here: the statistics panel already shows every
## skill and its experience, so a second one would be a duplicate.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

const PANEL_SIZE := Vector2(640.0, 460.0)
## The tab the encyclopedia icon and Ctrl+E open on.
const ENCYCLOPEDIA_TAB := 3
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0

signal notes_changed(text: String)
signal bookmarks_changed(bookmarks: Array)
signal buddy_add_requested(name: String)

var panel: PanelContainer
var tabs: TabContainer
var help_text: RichTextLabel
var notes_edit: TextEdit
var links_list: ItemList
var encyclopedia: EncyclopediaView
var almanac_text: RichTextLabel
var buddy_list: ItemList
var buddy_name_edit: LineEdit

var console_commands: ConsoleCommands
var bindable: Dictionary = {}

func _ready() -> void:
	name = "ReferenceLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	AppState.state_changed.connect(_on_state_changed)

func configure(commands: ConsoleCommands, bindable_actions: Dictionary,
		notes: String, bookmarks: Array = []) -> void:
	console_commands = commands
	bindable = bindable_actions
	notes_edit.text = notes
	encyclopedia.set_bookmarks(bookmarks)
	_refresh_help()

## The catalogues the encyclopedia builds its generated pages from. They are
## read after this window is built, so they arrive separately.
func configure_catalogues(catalogues: Dictionary) -> void:
	encyclopedia.configure_catalogues(catalogues)

func is_open() -> bool:
	return panel.visible

## True only when the encyclopedia itself is on screen, which is what the HUD
## icon lights on rather than the window as a whole.
func is_encyclopedia_open() -> bool:
	return panel.visible and tabs.current_tab == ENCYCLOPEDIA_TAB

## What the HUD icon and Ctrl+E do: open on the encyclopedia, or close it if
## that is already what is showing. Landing on another tab moves to this one
## rather than closing the window under the player.
func toggle_encyclopedia() -> void:
	if is_encyclopedia_open():
		close()
		return
	if not panel.visible:
		toggle()
	else:
		panel.move_to_front()
	tabs.current_tab = ENCYCLOPEDIA_TAB
	encyclopedia.reset_to_index()

func toggle() -> void:
	panel.visible = not panel.visible
	if panel.visible:
		panel.move_to_front()
		_refresh_help()
		_refresh_links()
		_refresh_almanac()
		_refresh_buddies()

func close() -> void:
	panel.hide()

func tab_titles() -> Array[String]:
	var titles: Array[String] = []
	for index: int in range(tabs.get_tab_count()):
		titles.append(tabs.get_tab_title(index))
	return titles

func entry_count() -> int:
	return encyclopedia.entry_count()

## How many days the server said it can roll. Zero before the packet arrives.
func almanac_day_count() -> int:
	return (AppState.almanac.get("catalogue", []) as Array).size()

## Every address the server has said, oldest first and each one only once.
func known_links() -> Array[String]:
	var found: Array[String] = []
	for line_value: Variant in AppState.chat_lines:
		for url: String in ConsoleCommands.urls_in(
				str((line_value as Dictionary).get("text", ""))):
			if not found.has(url):
				found.append(url)
	return found

func _on_state_changed(path: StringName) -> void:
	if path == &"chat" and panel.visible:
		_refresh_links()
	elif path == &"almanac":
		_refresh_almanac()
	elif path == &"buddies":
		_refresh_buddies()

## Built from the input map and the console table rather than written out, so
## a rebound key or a new command is in the help the moment it exists.
func _refresh_help() -> void:
	var lines: Array[String] = ["[b]Keys[/b]"]
	for group: Variant in bindable:
		lines.append("[i]%s[/i]" % str(group))
		for action: Variant in bindable[group]:
			var name: String = str(action)
			if not InputMap.has_action(name):
				continue
			var events: Array[InputEvent] = InputMap.action_get_events(name)
			var described: String = "unbound"
			if not events.is_empty() and events[0] is InputEventKey:
				var key: InputEventKey = events[0] as InputEventKey
				var parts: Array[String] = []
				if key.ctrl_pressed:
					parts.append("Ctrl")
				if key.shift_pressed:
					parts.append("Shift")
				if key.alt_pressed:
					parts.append("Alt")
				parts.append(OS.get_keycode_string(key.physical_keycode))
				described = "+".join(parts)
			lines.append("  %s  -  %s" % [described, name.replace("_", " ")])
	lines.append("")
	lines.append("[b]Commands this client answers itself[/b]")
	if console_commands != null:
		for command: Variant in ConsoleCommands.COMMANDS:
			lines.append("  %s  -  %s" % [str(command),
				str(ConsoleCommands.COMMANDS[command])])
	lines.append("")
	lines.append("Anything else you type beginning with # is sent to the"
		+ " server exactly as written.")
	help_text.text = "\n".join(lines)

## Who is on the player's list, and who of them is here. Everything shown is
## what the server stated; the client keeps no list of its own.
func _refresh_buddies() -> void:
	if buddy_list == null:
		return
	buddy_list.clear()
	var names: Array = AppState.buddies.keys()
	names.sort()
	for name: Variant in names:
		var here: bool = bool(AppState.buddies[name])
		buddy_list.add_item("%s  -  %s" % [str(name),
			"here now" if here else "away"])
		buddy_list.set_item_custom_fg_color(buddy_list.item_count - 1,
			Color(0.62, 0.88, 0.62) if here else Color(0.66, 0.66, 0.70))
	if names.is_empty():
		buddy_list.add_item("Nobody is on your list. Add one below.")
		buddy_list.set_item_disabled(0, true)

## Asks for a name to be put on the list. The window sends nothing itself: it
## emits, and whoever listens asks the server with #add_buddy. The list only
## changes when the server answers.
func _on_add_buddy_pressed() -> void:
	var buddy_name: String = buddy_name_edit.text.strip_edges()
	if buddy_name.is_empty():
		return
	buddy_name_edit.clear()
	buddy_add_requested.emit(buddy_name)

func _on_buddy_name_submitted(_text: String) -> void:
	_on_add_buddy_pressed()

## The names the player is watching, in the order shown.
func buddy_names() -> Array[String]:
	var found: Array[String] = []
	for name: Variant in AppState.buddies:
		found.append(str(name))
	found.sort()
	return found

## Everything here is what arrived in command 238. Before it arrives the page
## says so rather than showing an empty frame or a guess at today's date.
func _refresh_almanac() -> void:
	if almanac_text == null:
		return
	var almanac: Dictionary = AppState.almanac
	if almanac.is_empty():
		almanac_text.text = "[i]The server has not sent the almanac yet.[/i]"
		return
	var lines: Array[String] = []
	lines.append("[b]%d %s, Year %d[/b]" % [int(almanac.get("day", 0)),
		_month_name(int(almanac.get("month", 0))), int(almanac.get("year", 0))])
	lines.append("")
	var kind: String = str(almanac.get("kind", "ordinary"))
	lines.append("[b]%s[/b]  [i](%s)[/i]" % [str(almanac.get("name", "")), kind])
	lines.append(str(almanac.get("description", "")))
	var multipliers: Dictionary = almanac.get("multipliers", {}) as Dictionary
	if not multipliers.is_empty():
		lines.append("")
		for skill: Variant in multipliers:
			lines.append("  %s experience x%s" % [str(skill).capitalize(),
				_trimmed(float(multipliers[skill]))])
	var bonus: float = float(almanac.get("experience_bonus", 1.0))
	if not is_equal_approx(bonus, 1.0):
		lines.append("  All experience x%s today" % _trimmed(bonus))
	var effects: Array = almanac.get("effects", []) as Array
	if not effects.is_empty():
		lines.append("")
		lines.append("Effects in force: %s" % ", ".join(
			PackedStringArray(effects)))
	lines.append("")
	lines.append("[b]Days this world can bring[/b]")
	for entry_value: Variant in almanac.get("catalogue", []) as Array:
		var entry: Dictionary = entry_value as Dictionary
		lines.append("  [b]%s[/b] (%s) - %s" % [str(entry.get("name", "")),
			str(entry.get("kind", "")), str(entry.get("description", ""))])
	almanac_text.text = "\n".join(lines)

## The Calendar of the Elders. The server sends the month as a number and this
## is the only place the names live, because they never change.
static func _month_name(month: int) -> String:
	const MONTHS: Array[String] = ["Aluwia", "Seedar", "Akbar", "Zartia",
		"Elandra", "Viasia", "Fruitfall", "Mortia", "Carnelar", "Nimlos",
		"Chimar", "Vesepia"]
	if month < 1 or month > MONTHS.size():
		return "?"
	return MONTHS[month - 1]

## "2" rather than "2.0", but "1.23" kept whole.
static func _trimmed(value: float) -> String:
	if is_equal_approx(value, roundf(value)):
		return str(int(roundf(value)))
	return "%.2f" % value

func _refresh_links() -> void:
	var links: Array[String] = known_links()
	if links.size() == links_list.item_count:
		return
	links_list.clear()
	for url: String in links:
		links_list.add_item(url)
	if links.is_empty():
		links_list.add_item("Nothing has been linked yet.")
		links_list.set_item_disabled(0, true)

## Kept because the reference window's own tests reach the encyclopedia this
## way: the nth entry across every category, in index order.
func _show_entry(index: int) -> void:
	encyclopedia.show_entry_at(index)

func _on_bookmarks_changed(bookmarks: Array) -> void:
	bookmarks_changed.emit(bookmarks)

func _on_notes_changed() -> void:
	notes_changed.emit(notes_edit.text)

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "ReferenceWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.position = Vector2(
		(1280.0 - RESERVED_RIGHT_RAIL - PANEL_SIZE.x) * 0.5, 80.0)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)

	var column := VBoxContainer.new()
	column.name = "ReferenceBody"
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "ReferenceHeader"
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.name = "ReferenceTitle"
	title.text = "Reference"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_button := Button.new()
	close_button.name = "ReferenceClose"
	close_button.text = tr("ELORIA_SETTINGS_CLOSE")
	close_button.pressed.connect(close)
	header.add_child(close_button)

	tabs = TabContainer.new()
	tabs.name = "ReferenceTabs"
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(tabs)

	var help_page := VBoxContainer.new()
	help_page.name = "Help"
	tabs.add_child(help_page)
	var adventures := Button.new()
	adventures.name = "PracticeAdventures"
	adventures.text = "Ask about watch work"
	adventures.tooltip_text = "Speak with Ilyon, Nesh, or Hemmen. A nearby conversation opens here; otherwise their post is marked on the map."
	adventures.pressed.connect(func():
		if AppState.authenticated:
			Network.send_chat("#tutorial lines")
			close())
	help_page.add_child(adventures)
	var help_scroll := ScrollContainer.new()
	help_scroll.name = "HelpScroll"
	help_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	help_page.add_child(help_scroll)
	help_text = RichTextLabel.new()
	help_text.name = "HelpText"
	help_text.bbcode_enabled = true
	help_text.fit_content = true
	help_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	help_scroll.add_child(help_text)

	var notes_page := VBoxContainer.new()
	notes_page.name = "Notes"
	tabs.add_child(notes_page)
	notes_edit = TextEdit.new()
	notes_edit.name = "NotesEdit"
	notes_edit.size_flags_vertical = Control.SIZE_EXPAND_FILL
	notes_edit.placeholder_text = "Your own notes. Kept on this machine."
	notes_edit.text_changed.connect(_on_notes_changed)
	notes_page.add_child(notes_edit)

	var links_page := VBoxContainer.new()
	links_page.name = "Links"
	tabs.add_child(links_page)
	links_list = ItemList.new()
	links_list.name = "LinksList"
	links_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	links_page.add_child(links_list)

	encyclopedia = EncyclopediaView.new()
	# Named before it is added: the tab container reads the child's name for
	# the tab title, and _ready() has not run yet.
	encyclopedia.name = "Encyclopedia"
	tabs.add_child(encyclopedia)
	encyclopedia.bookmarks_changed.connect(_on_bookmarks_changed)

	var almanac_page := VBoxContainer.new()
	almanac_page.name = "Almanac"
	tabs.add_child(almanac_page)
	var almanac_scroll := ScrollContainer.new()
	almanac_scroll.name = "AlmanacScroll"
	almanac_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	almanac_page.add_child(almanac_scroll)
	almanac_text = RichTextLabel.new()
	almanac_text.name = "AlmanacText"
	almanac_text.bbcode_enabled = true
	almanac_text.fit_content = true
	almanac_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	almanac_scroll.add_child(almanac_text)
	_refresh_almanac()

	var buddy_page := VBoxContainer.new()
	buddy_page.name = "Buddies"
	tabs.add_child(buddy_page)
	buddy_list = ItemList.new()
	buddy_list.name = "BuddyList"
	buddy_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	buddy_page.add_child(buddy_list)
	var buddy_add_row := HBoxContainer.new()
	buddy_add_row.name = "BuddyAddRow"
	buddy_page.add_child(buddy_add_row)
	buddy_name_edit = LineEdit.new()
	buddy_name_edit.name = "BuddyNameEdit"
	buddy_name_edit.placeholder_text = "Name"
	buddy_name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	buddy_name_edit.text_submitted.connect(_on_buddy_name_submitted)
	buddy_add_row.add_child(buddy_name_edit)
	var add_buddy_button := Button.new()
	add_buddy_button.name = "AddBuddyButton"
	add_buddy_button.text = "Add buddy"
	add_buddy_button.pressed.connect(_on_add_buddy_pressed)
	buddy_add_row.add_child(add_buddy_button)
	_refresh_buddies()

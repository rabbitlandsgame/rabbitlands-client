extends AcceptDialog
## A searchable music library, personal playlists, and ordered context rules.

const Jukebox := preload("res://src/audio/jukebox.gd")
var jukebox: Node
var tabs: TabContainer
var mode_option: OptionButton
var search: LineEdit
var context_filter: OptionButton
var library_list: ItemList
var library_count: Label
var library_playlist: OptionButton
var playlist_option: OptionButton
var playlist_name: LineEdit
var playlist_list: ItemList
var add_button: Button
var play_song: Button
var play_playlist: Button
var status: Label
var pause_button: Button
var previous_button: Button
var next_button: Button
var random_order: CheckBox
var repetition: OptionButton
var fade: SpinBox
var use_rules: CheckBox
var rules_list: ItemList
var condition: OptionButton
var action: OptionButton
var target: OptionButton
var rule_enabled: CheckBox
var rule_save: Button
var notice: Label
var _selected_playlist := ""
var _editing_rule := -1

func _ready() -> void:
	name = "JukeboxWindow"
	title = "Jukebox"
	exclusive = true
	# Wrapped help labels briefly have tall minima before their first layout.
	# The scrollable tabs own overflow; content must not enlarge the window.
	wrap_controls = false
	min_size = Vector2i(640, 460)
	size = Vector2i(920, 680)
	get_ok_button().text = "Close"
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 10)
	add_child(body)
	var top := _row(body)
	_label(top, "Default music")
	mode_option = _option(top, Jukebox.MODE_LABELS, Jukebox.MODES)
	mode_option.name = "MusicMode"
	mode_option.item_selected.connect(_choose_mode)
	status = _label(body, "")
	status.name = "JukeboxStatus"
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var transport := _row(body)
	previous_button = _button(transport, "Previous", func() -> void: jukebox.skip(-1))
	pause_button = _button(transport, "Pause", func() -> void: jukebox.toggle_pause())
	next_button = _button(transport, "Next", func() -> void: jukebox.skip())
	tabs = TabContainer.new()
	tabs.name = "JukeboxTabs"
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(tabs)
	_build_library()
	_build_playlists()
	_build_rules()
	notice = _label(body, "Changes save automatically on this device.")
	notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	jukebox.preferences_changed.connect(_refresh_preferences)
	jukebox.changed.connect(_refresh_status)
	_refresh_preferences()

func open() -> void:
	_refresh_preferences()
	popup_centered_clamped(Vector2i(920, 680), 0.9)
	search.grab_focus()
	# AcceptDialog lays out its content before wrapped labels have their width.
	# Fit once more after that layout so their transient minima cannot leave a
	# tall content rectangle inside the correctly sized popup.
	await get_tree().process_frame
	if visible:
		reset_size()
		popup_centered_clamped(Vector2i(920, 680), 0.9)

func _page(label: String) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = label
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	var page := VBoxContainer.new()
	page.name = label + "Body"
	page.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page.add_theme_constant_override("separation", 8)
	scroll.add_child(page)
	return page

func _row(parent: Node) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)
	return row

func _label(parent: Node, text: String) -> Label:
	var label := Label.new()
	label.text = text
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _option(parent: Node, labels: Array, values: Array) -> OptionButton:
	var option := OptionButton.new()
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	option.fit_to_longest_item = false
	parent.add_child(option)
	for index: int in labels.size():
		option.add_item(str(labels[index]))
		option.set_item_metadata(index, values[index])
	return option

func _selected(option: OptionButton) -> String:
	return str(option.get_item_metadata(option.selected)) if option.selected >= 0 else ""

func _select(option: OptionButton, value: String) -> void:
	for index: int in option.item_count:
		if str(option.get_item_metadata(index)) == value:
			option.select(index)
			return
	option.select(0 if option.item_count > 0 else -1)

func _list(parent: Node, label: String) -> ItemList:
	var list := ItemList.new()
	list.name = label
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.custom_minimum_size.y = 80
	parent.add_child(list)
	return list

func _build_library() -> void:
	var page := _page("Library")
	var filters := _row(page)
	search = LineEdit.new()
	search.name = "MusicSearch"
	search.placeholder_text = "Search songs, artists, or contexts…"
	search.clear_button_enabled = true
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.size_flags_stretch_ratio = 2.0
	filters.add_child(search)
	var keys: Array = [""]
	var labels: Array = ["All contexts"]
	for key: String in jukebox.contexts():
		keys.append(key)
		labels.append(jukebox.context_name(key))
	context_filter = _option(filters, labels, keys)
	context_filter.name = "MusicContextFilter"
	search.text_changed.connect(func(_text: String) -> void: _refresh_library())
	context_filter.item_selected.connect(func(_index: int) -> void: _refresh_library())
	library_count = _label(page, "")
	library_list = _list(page, "MusicLibrary")
	library_list.item_selected.connect(func(_index: int) -> void: _refresh_buttons())
	library_list.item_activated.connect(func(_index: int) -> void: _play_selected_song())
	var actions := _row(page)
	play_song = _button(actions, "Play song", _play_selected_song)
	library_playlist = _option(actions, [], [])
	library_playlist.name = "AddToPlaylist"
	library_playlist.tooltip_text = "Choose a playlist to add songs to."
	library_playlist.item_selected.connect(func(_index: int) -> void:
		_selected_playlist = _selected(library_playlist)
		_select(playlist_option, _selected_playlist)
		_refresh_playlist())
	add_button = _button(actions, "Add song", _add_selected_song)
	_button(actions, "Shuffle all", func() -> void: jukebox.choose("shuffle"))
	var help := _label(page, "Double-click a song to play. Search includes artist names and game contexts.")
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

func _build_playlists() -> void:
	var page := _page("Playlists")
	var picker := _row(page)
	playlist_option = _option(picker, [], [])
	playlist_option.name = "PlaylistPicker"
	playlist_option.item_selected.connect(func(_index: int) -> void:
		_selected_playlist = _selected(playlist_option)
		_select(library_playlist, _selected_playlist)
		_refresh_playlist())
	play_playlist = _button(picker, "Play playlist", func() -> void:
		jukebox.choose("playlist", _selected_playlist))
	var naming := _row(page)
	playlist_name = LineEdit.new()
	playlist_name.name = "PlaylistName"
	playlist_name.placeholder_text = "Playlist name"
	playlist_name.max_length = 64
	playlist_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	naming.add_child(playlist_name)
	_button(naming, "Create", func() -> void:
		var label := playlist_name.text.strip_edges().left(64)
		if jukebox.create_playlist(label):
			_selected_playlist = label
			_refresh_preferences()
		else:
			notice.text = "Choose a unique playlist name (up to 64 playlists).")
	_button(naming, "Rename", func() -> void:
		var label := playlist_name.text.strip_edges()
		if jukebox.rename_playlist(_selected_playlist, label):
			_selected_playlist = label
			_refresh_preferences()
		else:
			notice.text = "Choose a unique playlist name.")
	_button(naming, "Delete", _confirm_delete_playlist)
	playlist_list = _list(page, "PlaylistSongs")
	playlist_list.item_selected.connect(func(_index: int) -> void: _refresh_buttons())
	playlist_list.item_activated.connect(func(index: int) -> void:
		jukebox.choose("song", str(playlist_list.get_item_metadata(index))))
	var edit := _row(page)
	_button(edit, "Move up", func() -> void: _move_song(-1))
	_button(edit, "Move down", func() -> void: _move_song(1))
	_button(edit, "Remove song", _remove_song)
	_button(edit, "Add songs…", func() -> void: tabs.current_tab = 0; search.grab_focus())
	var options := _row(page)
	random_order = CheckBox.new()
	random_order.text = "Shuffle playlist"
	options.add_child(random_order)
	random_order.toggled.connect(func(_value: bool) -> void: _options_changed())
	_label(options, "Repeat")
	repetition = _option(options, ["Off", "All", "One song"], Jukebox.REPEATS)
	repetition.item_selected.connect(func(_index: int) -> void: _options_changed())
	_label(options, "Crossfade (s)")
	fade = SpinBox.new()
	fade.max_value = 8.0
	fade.step = 0.5
	options.add_child(fade)
	fade.value_changed.connect(func(_value: float) -> void: _options_changed())
	var help := _label(page, "Repeat and crossfade apply to personal music. Shuffle plays every song before starting a new round.")
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

func _build_rules() -> void:
	var page := _page("Rules")
	use_rules = CheckBox.new()
	use_rules.text = "Use context rules"
	page.add_child(use_rules)
	use_rules.toggled.connect(func(_value: bool) -> void: _options_changed())
	var help := _label(page, "The first enabled match overrides your default music.")
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	rules_list = _list(page, "MusicRules")
	rules_list.item_selected.connect(_edit_rule)
	var ordering := _row(page)
	_button(ordering, "Move up", func() -> void: _move_rule(-1))
	_button(ordering, "Move down", func() -> void: _move_rule(1))
	_button(ordering, "Delete rule", _delete_rule)
	_button(ordering, "New rule", _new_rule)
	var when := _row(page)
	_label(when, "When")
	var labels: Array = Jukebox.GROUPS.values()
	var keys: Array = Jukebox.GROUPS.keys()
	for key: String in jukebox.contexts():
		keys.append(key)
		labels.append(jukebox.context_name(key))
	condition = _option(when, labels, keys)
	condition.name = "RuleContext"
	condition.tooltip_text = "Contexts follow the game’s location and event cues."
	rule_enabled = CheckBox.new()
	rule_enabled.text = "Enabled"
	rule_enabled.button_pressed = true
	when.add_child(rule_enabled)
	var then := _row(page)
	_label(then, "Play")
	action = _option(then, Jukebox.MODE_LABELS, Jukebox.MODES)
	action.name = "RuleAction"
	action.tooltip_text = "Personal music uses the repeat, shuffle and crossfade options from Playlists."
	action.item_selected.connect(func(_index: int) -> void: _refresh_targets())
	target = _option(then, [], [])
	target.name = "RuleTarget"
	rule_save = _button(then, "Add rule", _save_rule)
	_refresh_targets()

func _refresh_preferences() -> void:
	_select(mode_option, str(jukebox.mode))
	random_order.set_pressed_no_signal(bool(jukebox.shuffle))
	_select(repetition, str(jukebox.repeat_mode))
	fade.set_value_no_signal(float(jukebox.fade_seconds))
	use_rules.set_pressed_no_signal(bool(jukebox.rules_enabled))
	if not jukebox.playlists.has(_selected_playlist):
		_selected_playlist = str(jukebox.active_playlist)
	playlist_option.clear()
	library_playlist.clear()
	for label: String in jukebox.playlists:
		playlist_option.add_item(label)
		playlist_option.set_item_metadata(playlist_option.item_count - 1, label)
		library_playlist.add_item(label)
		library_playlist.set_item_metadata(library_playlist.item_count - 1, label)
	_select(playlist_option, _selected_playlist)
	_select(library_playlist, _selected_playlist)
	_refresh_library()
	_refresh_playlist()
	_refresh_rules()
	_refresh_targets()
	_refresh_status()

func _refresh_status() -> void:
	var selection: Dictionary = jukebox.effective_selection()
	var track: String = jukebox.current_track()
	var context: String = jukebox.game_cue.trim_prefix("@").get_slice("|", 0)
	status.text = ("Paused: " if jukebox.paused else "Playing: ") + jukebox.title_for(track) if not track.is_empty() else "Music is quiet"
	if not jukebox.available:
		status.text = "Audio is disabled. Enable it in Audio settings to listen."
	elif selection.mode == "playlist" and jukebox.playlists.get(selection.target, []).is_empty():
		status.text = "This playlist is empty. Add songs from the Library."
	if not context.is_empty():
		status.text += "  •  " + jukebox.context_name(context)
	if jukebox.active_rule >= 0:
		status.text += "  •  Rule %d" % (jukebox.active_rule + 1)
	pause_button.text = "Resume" if jukebox.paused else "Play again" if jukebox.queue_ended() else "Pause"
	pause_button.disabled = not jukebox.available or (track.is_empty() and not jukebox.queue_ended())
	previous_button.disabled = not jukebox.can_skip()
	next_button.disabled = previous_button.disabled
	if not jukebox.save_error.is_empty():
		notice.text = jukebox.save_error

func _refresh_library() -> void:
	var selected := _selected_track(library_list)
	library_list.clear()
	var entries: Array = jukebox.library(search.text, _selected(context_filter))
	for entry: Dictionary in entries:
		var seconds := roundi(float(entry.get("seconds", 0.0)))
		var creator := str(entry.get("creator", ""))
		var index := library_list.add_item("%s   •   %d:%02d   •   %s" % [entry.title, seconds / 60, seconds % 60, creator])
		library_list.set_item_metadata(index, entry.name)
		library_list.set_item_tooltip(index, "%s\n%s\n%s" % [entry.title, creator, ", ".join(entry.contexts)])
		if str(entry.name) == selected:
			library_list.select(index)
	library_count.text = "%d songs%s" % [entries.size(), " — no matches; try another search or context" if entries.is_empty() else ""]
	_refresh_buttons()

func _refresh_playlist() -> void:
	var selected := _selected_track(playlist_list)
	playlist_list.clear()
	for track: String in jukebox.playlists.get(_selected_playlist, []):
		var index := playlist_list.add_item("%d. %s" % [playlist_list.item_count + 1, jukebox.title_for(track)])
		playlist_list.set_item_metadata(index, track)
		if track == selected:
			playlist_list.select(index)
	playlist_name.text = _selected_playlist
	play_playlist.disabled = playlist_list.item_count == 0
	_refresh_buttons()

func _refresh_buttons() -> void:
	play_song.disabled = _selected_track(library_list).is_empty()
	add_button.disabled = play_song.disabled or _selected_playlist.is_empty()
	add_button.tooltip_text = "Add the selected song to the chosen playlist." if not _selected_playlist.is_empty() else "Create a playlist in the Playlists tab first."

func _selected_track(list: ItemList) -> String:
	var selected := list.get_selected_items()
	return str(list.get_item_metadata(selected[0])) if not selected.is_empty() else ""

func _play_selected_song() -> void:
	var track := _selected_track(library_list)
	if not track.is_empty():
		jukebox.choose("song", track)

func _add_selected_song() -> void:
	var track := _selected_track(library_list)
	if not track.is_empty() and jukebox.playlists.has(_selected_playlist):
		var tracks: Array = jukebox.playlists[_selected_playlist].duplicate()
		if track in tracks:
			notice.text = "That song is already in this playlist."
			return
		tracks.append(track)
		jukebox.edit_playlist(_selected_playlist, tracks)
		notice.text = "Added %s to %s." % [jukebox.title_for(track), _selected_playlist]

func _move_song(direction: int) -> void:
	var selected := playlist_list.get_selected_items()
	if selected.is_empty():
		return
	var index := int(selected[0])
	var tracks: Array = jukebox.playlists.get(_selected_playlist, []).duplicate()
	var other := index + direction
	if other < 0 or other >= tracks.size():
		return
	var track: Variant = tracks[index]
	tracks[index] = tracks[other]
	tracks[other] = track
	jukebox.edit_playlist(_selected_playlist, tracks)
	playlist_list.select(other)

func _remove_song() -> void:
	var track := _selected_track(playlist_list)
	if not track.is_empty():
		var tracks: Array = jukebox.playlists[_selected_playlist].duplicate()
		tracks.erase(track)
		jukebox.edit_playlist(_selected_playlist, tracks)

func _confirm_delete_playlist() -> void:
	if not jukebox.playlists.has(_selected_playlist):
		return
	var dialog := ConfirmationDialog.new()
	dialog.title = "Delete playlist"
	dialog.dialog_text = "Delete “%s”? Its songs stay in the Library." % _selected_playlist
	add_child(dialog)
	var label := _selected_playlist
	dialog.confirmed.connect(func() -> void: jukebox.delete_playlist(label); dialog.queue_free())
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered()

func _choose_mode(index: int) -> void:
	var value := str(mode_option.get_item_metadata(index))
	if value == "song":
		var track := _selected_track(library_list)
		if track.is_empty():
			track = str(jukebox.song)
		if track.is_empty():
			tabs.current_tab = 0
			notice.text = "Select a song, then choose Play song."
			_select(mode_option, str(jukebox.mode))
			return
		jukebox.choose(value, track)
	elif value == "playlist":
		if _selected_playlist.is_empty():
			tabs.current_tab = 1
			notice.text = "Create a playlist and add songs from the Library."
			_select(mode_option, str(jukebox.mode))
			return
		jukebox.choose(value, _selected_playlist)
	else:
		jukebox.choose(value)

func _options_changed() -> void:
	jukebox.set_options(random_order.button_pressed, _selected(repetition), fade.value, use_rules.button_pressed)

func _refresh_rules() -> void:
	rules_list.clear()
	for index: int in jukebox.rules.size():
		var rule: Dictionary = jukebox.rules[index]
		var label := str(Jukebox.MODE_LABELS[Jukebox.MODES.find(str(rule.mode))])
		if rule.mode == "song":
			label = jukebox.title_for(str(rule.target))
		elif rule.mode == "playlist":
			label = "Playlist: " + str(rule.target)
		rules_list.add_item("%d. %s%s → %s" % [index + 1, "" if rule.enabled else "[Off] ", jukebox.context_name(str(rule.context)), label])
	if _editing_rule >= jukebox.rules.size():
		_editing_rule = -1
	if _editing_rule >= 0:
		rules_list.select(_editing_rule)
	rule_save.text = "Update rule" if _editing_rule >= 0 else "Add rule"

func _refresh_targets() -> void:
	var selected := _selected(target)
	target.clear()
	match _selected(action):
		"song":
			for entry: Dictionary in jukebox.library():
				target.add_item(str(entry.title))
				target.set_item_metadata(target.item_count - 1, entry.name)
		"playlist":
			for label: String in jukebox.playlists:
				target.add_item(label)
				target.set_item_metadata(target.item_count - 1, label)
	target.visible = _selected(action) in ["song", "playlist"]
	_select(target, selected)

func _new_rule() -> void:
	_editing_rule = -1
	rules_list.deselect_all()
	rule_enabled.set_pressed_no_signal(true)
	rule_save.text = "Add rule"

func _edit_rule(index: int) -> void:
	_editing_rule = index
	var rule: Dictionary = jukebox.rules[index]
	_select(condition, str(rule.context))
	_select(action, str(rule.mode))
	rule_enabled.set_pressed_no_signal(bool(rule.enabled))
	_refresh_targets()
	_select(target, str(rule.target))
	rule_save.text = "Update rule"

func _save_rule() -> void:
	if target.visible and _selected(target).is_empty():
		notice.text = "Choose a song or create a playlist first."
		return
	var value := {"enabled": rule_enabled.button_pressed, "context": _selected(condition),
		"mode": _selected(action), "target": _selected(target)}
	var rules: Array = jukebox.rules.duplicate(true)
	if _editing_rule >= 0:
		rules[_editing_rule] = value
	else:
		rules.append(value)
	jukebox.set_rules(rules)
	_new_rule()

func _move_rule(direction: int) -> void:
	if _editing_rule < 0:
		return
	var other := _editing_rule + direction
	var rules: Array = jukebox.rules.duplicate(true)
	if other < 0 or other >= rules.size():
		return
	var rule: Variant = rules[_editing_rule]
	rules[_editing_rule] = rules[other]
	rules[other] = rule
	_editing_rule = other
	jukebox.set_rules(rules)
	_edit_rule(other)

func _delete_rule() -> void:
	if _editing_rule >= 0:
		var rules: Array = jukebox.rules.duplicate(true)
		rules.remove_at(_editing_rule)
		_editing_rule = -1
		jukebox.set_rules(rules)
		_new_rule()

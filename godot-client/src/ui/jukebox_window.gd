extends AcceptDialog
## Moonlit Slate's full workbench. Each column is a live, accessible control.
const Jukebox := preload("res://src/audio/jukebox.gd")
const Slate := preload("res://src/ui/jukebox_style.gd")
const Transport := preload("res://src/ui/jukebox_transport.gd")
const RuleList := preload("res://src/ui/jukebox_rule_list.gd")
const SongList := preload("res://src/ui/jukebox_song_list.gd")
const FrameDetails := preload("res://src/ui/jukebox_frame.gd")
var jukebox: Node
var tabs: TabBar
var mode_option: OptionButton
var search: LineEdit
var context_filter: OptionButton
var library_list: ScrollContainer
var library_count: Label
var library_playlist: OptionButton
var playlist_option: OptionButton
var playlist_name: LineEdit
var playlist_list: ScrollContainer
var add_button: Button
var play_song: Button
var play_playlist: Button
var status: Label
var random_order: CheckBox
var repetition: OptionButton
var fade: SpinBox
var use_rules: CheckBox
var rules_list: ScrollContainer
var condition: OptionButton
var action: OptionButton
var target: OptionButton
var rule_enabled: CheckBox
var rule_save: Button
var notice: Label
var transport: PanelContainer
var columns: HBoxContainer
var panels: Array[PanelContainer] = []
var game_button: Button
var personal_button: Button
var _title: Label
var _body: VBoxContainer
var _wide_tabs: TabBar
var _playlist_summary: Label
var _playlist_cover: TextureRect
var _playlist_tools: Control
var _playback_options: Control
var _selected_playlist := ""
var _editing_rule := -1
var _dragging := false

func _ready() -> void:
	name = "JukeboxWindow"
	title = "Jukebox"
	borderless = true
	exclusive = true
	wrap_controls = false
	min_size = Vector2i(720, 460)
	size = Vector2i(1180, 700)
	theme = Slate.theme()
	get_ok_button().hide()
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 7)
	add_child(_body)
	_body.add_child(FrameDetails.new())
	_build_header()
	tabs = _navigation(_body)
	columns = HBoxContainer.new()
	columns.name = "MusicWorkbench"
	columns.add_theme_constant_override("separation", 6)
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_body.add_child(columns)
	_build_library()
	_build_playlists()
	_build_rules()
	transport = Transport.new()
	transport.compact = false
	transport.jukebox = jukebox
	_body.add_child(transport)
	status = _label(_body, "", 12)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.hide()
	notice = _label(_body, "", 12)
	notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	notice.hide()
	jukebox.preferences_changed.connect(_refresh_preferences)
	jukebox.changed.connect(_refresh_status)
	size_changed.connect(_adapt_layout)
	_refresh_preferences()
	_adapt_layout()

func open() -> void:
	_refresh_preferences()
	popup_centered_clamped(Vector2i(1180, 700), 0.95)
	search.grab_focus()
	await get_tree().process_frame
	if visible:
		reset_size()
		popup_centered_clamped(Vector2i(1180, 700), 0.95)
		_adapt_layout()

func _build_header() -> void:
	var header := PanelContainer.new()
	header.name = "MoonlitHeader"
	header.custom_minimum_size.y = 76
	header.add_theme_stylebox_override("panel", Slate.box(Color("152c40"), Color("6a8395"), 9))
	_body.add_child(header)
	var backdrop := Slate.texture_rect(Slate.art(Rect2(1050, 83, 430, 62)), Vector2.ZERO)
	backdrop.stretch_mode = TextureRect.STRETCH_SCALE
	backdrop.modulate.a = 0.5
	header.add_child(backdrop)
	var row := _row(header)
	row.add_theme_constant_override("separation", 12)
	row.add_child(Slate.texture_rect(Slate.art(Rect2(230, 87, 67, 58)), Vector2(60, 55)))
	var heading := _label(row, "Jukebox", 30)
	_title = heading
	heading.add_theme_font_override("font", Slate.serif())
	heading.custom_minimum_size.x = 220
	game_button = Slate.button(row, "Game decides", "game", func() -> void: jukebox.choose("game"))
	personal_button = Slate.button(row, "My music", "library", _resume_personal)
	mode_option = _option(row, Jukebox.MODE_LABELS, Jukebox.MODES)
	mode_option.name = "MusicMode"
	mode_option.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	mode_option.custom_minimum_size.x = 30
	mode_option.tooltip_text = "Choose a song, playlist, shuffle all music, or silence."
	mode_option.item_selected.connect(_choose_mode)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	var compact := Slate.button(row, "", "expand", func() -> void:
		jukebox.hud_player_requested.emit()
		hide())
	compact.tooltip_text = "Use compact player on the HUD"
	var close := Slate.button(row, "", "close", hide)
	close.name = "CloseJukebox"
	close.tooltip_text = "Close jukebox"
	header.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
			_dragging = event.pressed
		elif event is InputEventMouseMotion and _dragging:
			position += Vector2i(event.relative))

func _resume_personal() -> void:
	if not jukebox.playlists.get(_selected_playlist, []).is_empty():
		jukebox.choose("playlist", _selected_playlist)
	elif not str(jukebox.song).is_empty():
		jukebox.choose("song", str(jukebox.song))
	else:
		jukebox.choose("shuffle")

func _navigation(parent: Node) -> TabBar:
	var navigation := TabBar.new()
	for label: String in ["Library", "Playlists", "Rules"]: navigation.add_tab(label)
	for index: int in 3: navigation.set_tab_icon(index, Slate.icon(["library", "playlist", "rules"][index], Slate.TEXT, 18))
	navigation.add_theme_stylebox_override("tab_selected", Slate.selected())
	navigation.add_theme_stylebox_override("tab_unselected", Slate.box(Color("172938"), Color("3c556a"), 9))
	navigation.add_theme_stylebox_override("tab_hovered", Slate.box(Color("244052"), Slate.TEAL, 9))
	navigation.tab_changed.connect(func(index: int) -> void:
		if tabs != null and tabs.current_tab != index: tabs.current_tab = index
		if _wide_tabs != null and _wide_tabs.current_tab != index: _wide_tabs.current_tab = index
		_adapt_layout())
	parent.add_child(navigation)
	return navigation

func _panel(name_text: String, weight: float) -> VBoxContainer:
	var panel := PanelContainer.new()
	panel.name = name_text
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.size_flags_stretch_ratio = weight
	panel.add_theme_stylebox_override("panel", Slate.box(Color("101d2b"), Slate.EDGE, 9))
	columns.add_child(panel)
	panels.append(panel)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	panel.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 9)
	scroll.add_child(column)
	return column

func _adapt_layout() -> void:
	if panels.size() != 3: return
	var narrow := size.x < 1000
	tabs.visible = narrow
	_wide_tabs.visible = not narrow
	for index: int in panels.size():
		panels[index].visible = not narrow or tabs.current_tab == index
		if not narrow:
			panels[index].add_theme_stylebox_override("panel", Slate.box(Color("101d2b"), Slate.EDGE, 9))
	game_button.text = "Game" if size.x < 800 else "Game decides"
	_title.custom_minimum_size.x = 140 if narrow else 220
	personal_button.text = "My music"
	library_playlist.visible = narrow
	_playback_options.visible = narrow
	_playlist_tools.visible = _playlist_tools.visible and panels[1].visible

func _row(parent: Node) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)
	return row

func _label(parent: Node, text: String, font_size := 15) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, callback: Callable) -> Button:
	return Slate.button(parent, text, "", callback)

func _option(parent: Node, labels: Array, values: Array) -> OptionButton:
	var option := OptionButton.new()
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	option.fit_to_longest_item = false
	option.custom_minimum_size.y = 32
	option.size_flags_vertical = Control.SIZE_SHRINK_CENTER
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

func _list(parent: Node, label: String) -> ScrollContainer:
	var list := SongList.new()
	list.name = label
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.custom_minimum_size.y = 90
	list.fixed_icon_size = Vector2i(48, 48)
	parent.add_child(list)
	return list

func _build_library() -> void:
	var page := _panel("Library", 0.95)
	_wide_tabs = _navigation(page)
	var filters := _row(page)
	search = LineEdit.new()
	search.name = "MusicSearch"
	search.placeholder_text = "Search songs or artists"
	search.clear_button_enabled = true
	search.right_icon = Slate.icon("search", Slate.MUTED, 18)
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	filters.add_child(search)
	var contexts: Array = [""]
	var labels: Array = ["All contexts"]
	for key: String in jukebox.contexts():
		contexts.append(key)
		labels.append(jukebox.context_name(key))
	var filter_row := _row(page)
	context_filter = _option(filter_row, labels, contexts)
	context_filter.name = "MusicContextFilter"
	library_count = _label(filter_row, "", 12)
	library_count.add_theme_color_override("font_color", Slate.MUTED)
	search.text_changed.connect(func(_text: String) -> void: _refresh_library())
	context_filter.item_selected.connect(func(_index: int) -> void: _refresh_library())
	library_list = _list(page, "MusicLibrary")
	library_list.item_selected.connect(func(_index: int) -> void: _refresh_buttons())
	library_list.item_activated.connect(func(_index: int) -> void: _play_selected_song())
	var buttons := _row(page)
	play_song = Slate.button(buttons, "Play", "play", _play_selected_song)
	library_playlist = _option(buttons, [], [])
	library_playlist.name = "AddToPlaylist"
	library_playlist.item_selected.connect(func(_index: int) -> void:
		_selected_playlist = _selected(library_playlist)
		_select(playlist_option, _selected_playlist)
		_refresh_playlist())
	add_button = Slate.button(buttons, "Add", "plus", _add_selected_song)
	add_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL

func _build_playlists() -> void:
	var page := _panel("Playlists", 0.95)
	var heading := _row(page)
	var title_label := _label(heading, "Playlist", 21)
	title_label.add_theme_font_override("font", Slate.serif())
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var tools := Slate.button(heading, "", "dots", func() -> void: _playlist_tools.visible = not _playlist_tools.visible)
	tools.tooltip_text = "Create, rename or delete a playlist"
	var summary := _row(page)
	_playlist_cover = Slate.texture_rect(Slate.art(Rect2(621, 214, 54, 52)), Vector2(54, 54))
	summary.add_child(_playlist_cover)
	var detail := VBoxContainer.new()
	detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary.add_child(detail)
	playlist_option = _option(detail, [], [])
	playlist_option.name = "PlaylistPicker"
	playlist_option.item_selected.connect(func(_index: int) -> void:
		_selected_playlist = _selected(playlist_option)
		_select(library_playlist, _selected_playlist)
		_refresh_playlist())
	_playlist_summary = _label(detail, "", 12)
	_playlist_summary.add_theme_color_override("font_color", Slate.MUTED)
	_playlist_tools = VBoxContainer.new()
	page.add_child(_playlist_tools)
	_playlist_tools.hide()
	var naming := _row(_playlist_tools)
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
		else: _show_notice("Choose a unique playlist name (up to 64 playlists)."))
	var edit_name := _row(_playlist_tools)
	_button(edit_name, "Rename", func() -> void:
		var label := playlist_name.text.strip_edges()
		if jukebox.rename_playlist(_selected_playlist, label):
			_selected_playlist = label
			_refresh_preferences()
		else: _show_notice("Choose a unique playlist name."))
	_button(edit_name, "Delete", _confirm_delete_playlist)
	var edits := _row(page)
	Slate.button(edits, "Add song", "plus", func() -> void:
		if _selected_track(library_list).is_empty():
			tabs.current_tab = 0
			search.grab_focus()
			_show_notice("Select a song in the Library, then choose Add.")
		else: _add_selected_song())
	Slate.button(edits, "", "remove", _remove_song).tooltip_text = "Remove selected song"
	Slate.button(edits, "", "up", func() -> void: _move_song(-1)).tooltip_text = "Move song up"
	Slate.button(edits, "", "down", func() -> void: _move_song(1)).tooltip_text = "Move song down"
	playlist_list = _list(page, "PlaylistSongs")
	playlist_list.fixed_icon_size = Vector2i(26, 26)
	playlist_list.item_activated.connect(func(index: int) -> void: jukebox.choose("song", str(playlist_list.get_item_metadata(index))))
	play_playlist = Slate.button(page, "Play playlist", "play", func() -> void: jukebox.choose("playlist", _selected_playlist), true)

func _build_rules() -> void:
	var page := _panel("Rules", 1.4)
	var heading := _row(page)
	var title_label := _label(heading, "Rules", 21)
	title_label.add_theme_font_override("font", Slate.serif())
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	use_rules = CheckBox.new()
	use_rules.text = "Use rules"
	use_rules.tooltip_text = "The first enabled matching rule overrides your default music."
	heading.add_child(use_rules)
	use_rules.toggled.connect(func(_value: bool) -> void: _options_changed())
	Slate.button(heading, "", "plus", _new_rule).tooltip_text = "New rule"
	var help := _label(page, "Checked from top to bottom · first match", 12)
	help.add_theme_color_override("font_color", Slate.MUTED)
	rules_list = RuleList.new()
	rules_list.name = "MusicRules"
	page.add_child(rules_list)
	rules_list.item_selected.connect(_edit_rule)
	rules_list.rule_toggled.connect(func(index: int, enabled: bool) -> void:
		var rules: Array = jukebox.rules.duplicate(true)
		rules[index].enabled = enabled
		if _editing_rule == index: rule_enabled.set_pressed_no_signal(enabled)
		jukebox.set_rules(rules))
	rules_list.rule_moved.connect(func(from: int, to: int) -> void:
		var rules: Array = jukebox.rules.duplicate(true)
		var rule: Variant = rules[from]
		rules.remove_at(from)
		rules.insert(to, rule)
		_editing_rule = to
		jukebox.set_rules(rules)
		_edit_rule(to))
	var editor := PanelContainer.new()
	editor.name = "RuleEditor"
	editor.add_theme_stylebox_override("panel", Slate.box(Color("142534"), Slate.EDGE, 12))
	page.add_child(editor)
	var form := VBoxContainer.new()
	form.add_theme_constant_override("separation", 12)
	editor.add_child(form)
	var edit_heading := _row(form)
	var edit_title := _label(edit_heading, "Edit rule", 17)
	edit_title.add_theme_font_override("font", Slate.serif())
	edit_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	Slate.button(edit_heading, "", "up", func() -> void: _move_rule(-1)).tooltip_text = "Move rule up"
	Slate.button(edit_heading, "", "down", func() -> void: _move_rule(1)).tooltip_text = "Move rule down"
	Slate.button(edit_heading, "", "remove", _delete_rule).tooltip_text = "Delete rule"
	var when := _row(form)
	_label(when, "When").custom_minimum_size.x = 42
	var labels: Array = Jukebox.GROUPS.values()
	var keys: Array = Jukebox.GROUPS.keys()
	for key: String in jukebox.contexts():
		keys.append(key)
		labels.append(jukebox.context_name(key))
	condition = _option(when, labels, keys)
	condition.name = "RuleContext"
	var then := _row(form)
	_label(then, "Play").custom_minimum_size.x = 42
	action = _option(then, Jukebox.MODE_LABELS, Jukebox.MODES)
	action.name = "RuleAction"
	action.item_selected.connect(func(_index: int) -> void: _refresh_targets())
	target = _option(then, [], [])
	target.name = "RuleTarget"
	var save := _row(form)
	rule_enabled = CheckBox.new()
	rule_enabled.text = "Enabled"
	rule_enabled.button_pressed = true
	rule_enabled.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	save.add_child(rule_enabled)
	rule_save = Slate.button(save, "Save rule", "check", _save_rule, true)
	rule_save.custom_minimum_size = Vector2(130, 36)
	var options := _row(page)
	_playback_options = options
	random_order = CheckBox.new()
	random_order.text = "Shuffle"
	options.add_child(random_order)
	random_order.toggled.connect(func(_value: bool) -> void: _options_changed())
	repetition = _option(options, ["Repeat off", "Repeat all", "Repeat one"], Jukebox.REPEATS)
	repetition.item_selected.connect(func(_index: int) -> void: _options_changed())
	_label(options, "Fade", 12)
	fade = SpinBox.new()
	fade.max_value = 8.0
	fade.step = 0.5
	fade.suffix = "s"
	fade.tooltip_text = "Crossfade between personal songs"
	options.add_child(fade)
	fade.value_changed.connect(func(_value: float) -> void: _options_changed())
	_refresh_targets()

func _show_notice(text: String) -> void:
	notice.text = text
	notice.show()

func _refresh_preferences() -> void:
	_select(mode_option, str(jukebox.mode))
	mode_option.text = ""
	game_button.add_theme_stylebox_override("normal", Slate.selected() if jukebox.mode == "game" else Slate.box(Color("192b3a"), Slate.EDGE, 9))
	personal_button.add_theme_stylebox_override("normal", Slate.selected() if jukebox.mode != "game" else Slate.box(Color("192b3a"), Slate.EDGE, 9))
	random_order.set_pressed_no_signal(bool(jukebox.shuffle))
	_select(repetition, str(jukebox.repeat_mode))
	fade.set_value_no_signal(float(jukebox.fade_seconds))
	use_rules.set_pressed_no_signal(bool(jukebox.rules_enabled))
	if not jukebox.playlists.has(_selected_playlist): _selected_playlist = str(jukebox.active_playlist)
	playlist_option.clear()
	library_playlist.clear()
	for label: String in jukebox.playlists:
		for picker: OptionButton in [playlist_option, library_playlist]:
			picker.add_item(label)
			picker.set_item_metadata(picker.item_count - 1, label)
	_select(playlist_option, _selected_playlist)
	_select(library_playlist, _selected_playlist)
	_refresh_library()
	_refresh_playlist()
	_refresh_rules()
	_refresh_targets()
	_refresh_status()

func _refresh_status() -> void:
	var selection: Dictionary = jukebox.effective_selection()
	status.text = ""
	if not jukebox.available:
		status.text = "Audio is disabled. Enable audio in Settings to listen."
	elif selection.mode == "playlist" and jukebox.playlists.get(selection.target, []).is_empty():
		status.text = "This playlist is empty. Add songs from the Library."
	status.visible = not status.text.is_empty()
	if not jukebox.save_error.is_empty(): _show_notice(str(jukebox.save_error))

func _refresh_library() -> void:
	var selected := _selected_track(library_list)
	if selected.is_empty(): selected = jukebox.current_track()
	library_list.clear()
	var entries: Array = jukebox.library(search.text, _selected(context_filter))
	if search.text.is_empty() and _selected(context_filter).is_empty():
		for entry: Dictionary in entries:
			if str(entry.name) == jukebox.current_track():
				entries.erase(entry)
				entries.push_front(entry)
				break
	for entry: Dictionary in entries:
		var creator := str(entry.get("creator", "Game music"))
		var index: int = library_list.add_item("%s\n%s" % [entry.title, creator], Slate.cover(str(entry.name)))
		library_list.set_item_metadata(index, entry.name)
		library_list.set_item_tooltip(index, "%s\n%s\n%s" % [entry.title, creator, ", ".join(entry.contexts)])
		if str(entry.name) == selected: library_list.select(index)
	library_count.text = "%d songs" % entries.size()
	library_count.tooltip_text = "No matches — try another search or context." if entries.is_empty() else "Every music track shipped with this client."
	_refresh_buttons()

func _refresh_playlist() -> void:
	var selected := _selected_track(playlist_list)
	playlist_list.clear()
	var duration := 0.0
	for track: String in jukebox.playlists.get(_selected_playlist, []):
		var info: Dictionary = jukebox.track_info(track)
		duration += float(info.get("seconds", 0))
		var index: int = playlist_list.add_item("%d   %s" % [playlist_list.item_count + 1, jukebox.title_for(track)], Slate.cover(track))
		playlist_list.set_item_metadata(index, track)
		if track == selected: playlist_list.select(index)
	playlist_name.text = _selected_playlist
	_playlist_summary.text = "%d songs · %d min" % [playlist_list.item_count, roundi(duration / 60)]
	play_playlist.disabled = playlist_list.item_count == 0
	_refresh_buttons()

func _refresh_buttons() -> void:
	play_song.disabled = _selected_track(library_list).is_empty()
	add_button.disabled = play_song.disabled or _selected_playlist.is_empty()
	add_button.tooltip_text = "Add song to " + _selected_playlist if not _selected_playlist.is_empty() else "Create a playlist first."

func _refresh_rules() -> void:
	rules_list.clear()
	for rule: Dictionary in jukebox.rules:
		var label := str(Jukebox.MODE_LABELS[Jukebox.MODES.find(str(rule.mode))])
		if rule.mode == "game": label = "Game music"
		elif rule.mode == "song": label = jukebox.title_for(str(rule.target))
		elif rule.mode == "playlist": label = str(rule.target)
		rules_list.add_rule(jukebox.context_name(str(rule.context)), label, bool(rule.enabled))
	if _editing_rule >= jukebox.rules.size(): _editing_rule = -1
	if _editing_rule >= 0: rules_list.select(_editing_rule)
	rule_save.text = "Save rule" if _editing_rule >= 0 else "Add rule"

func _selected_track(list: ScrollContainer) -> String:
	var selected: PackedInt32Array = list.get_selected_items()
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
			_show_notice("That song is already in this playlist.")
			return
		tracks.append(track)
		jukebox.edit_playlist(_selected_playlist, tracks)
		_show_notice("Added %s to %s." % [jukebox.title_for(track), _selected_playlist])

func _move_song(direction: int) -> void:
	var selected: PackedInt32Array = playlist_list.get_selected_items()
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
			_show_notice("Select a song, then choose Play song.")
			_select(mode_option, str(jukebox.mode))
			return
		jukebox.choose(value, track)
	elif value == "playlist":
		if _selected_playlist.is_empty():
			tabs.current_tab = 1
			_show_notice("Create a playlist and add songs from the Library.")
			_select(mode_option, str(jukebox.mode))
			return
		jukebox.choose(value, _selected_playlist)
	else:
		jukebox.choose(value)

func _options_changed() -> void:
	jukebox.set_options(random_order.button_pressed, _selected(repetition), fade.value, use_rules.button_pressed)

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
	rule_save.text = "Save rule"

func _save_rule() -> void:
	if target.visible and _selected(target).is_empty():
		_show_notice("Choose a song or create a playlist first.")
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

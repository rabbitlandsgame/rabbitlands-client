extends PanelContainer
## The same playback controls in the full menu and the movable HUD component.
const Slate := preload("res://src/ui/jukebox_style.gd")
const FrameDetails := preload("res://src/ui/jukebox_frame.gd")

var jukebox: Node
var compact := true
var cover: TextureRect
var title_label: Label
var source: Label
var previous_button: Button
var pause_button: Button
var next_button: Button
var shuffle_button: Button
var repeat_button: Button
var volume_button: Button
var volume: HSlider
var expand_button: Button
var fade: HSlider
var _fade_controls: VBoxContainer
var _fade_caption: Label
var _unmuted_volume := 0.55
var _editor_preview := false
var _ornament: Node2D
var _source_icon: TextureRect

func _ready() -> void:
	name = "CompactJukebox" if compact else "JukeboxTransport"
	theme = Slate.theme()
	mouse_filter = Control.MOUSE_FILTER_STOP
	custom_minimum_size = Vector2(520, 64) if compact else Vector2(0, 78)
	add_theme_stylebox_override("panel", Slate.box(Color("0d1824f5"), Slate.EDGE, 9, 4))
	if compact:
		_ornament = FrameDetails.new()
		_ornament.inset = 1.5
		_ornament.hide()
		add_child(_ornament)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 5 if compact else 10)
	add_child(row)
	cover = Slate.texture_rect(Slate.cover("rising_moon"), Vector2.ONE * (36 if compact else 54))
	row.add_child(cover)
	var text := VBoxContainer.new()
	text.custom_minimum_size.x = 70 if compact else 90
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	text.add_theme_constant_override("separation", 3)
	row.add_child(text)
	title_label = Label.new()
	title_label.name = "CurrentSong"
	title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title_label.add_theme_font_size_override("font_size", 14 if compact else 17)
	text.add_child(title_label)
	source = Label.new()
	source.add_theme_font_size_override("font_size", 11 if compact else 12)
	source.add_theme_color_override("font_color", Slate.MUTED)
	source.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	if compact:
		source.text_overrun_behavior = TextServer.OVERRUN_NO_TRIMMING
		var badge := PanelContainer.new()
		badge.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		badge.add_theme_stylebox_override("panel", Slate.box(Color("1a2d3d"), Color("435f74"), 3, 2))
		text.add_child(badge)
		var badge_row := HBoxContainer.new()
		badge_row.add_theme_constant_override("separation", 3)
		badge.add_child(badge_row)
		_source_icon = Slate.texture_rect(Slate.icon("playlist", Slate.MUTED, 12), Vector2(12, 12))
		badge_row.add_child(_source_icon)
		badge_row.add_child(source)
	else:
		text.add_child(source)
	_separator(row)
	if not compact:
		shuffle_button = _icon(row, "shuffle", "Shuffle playlist", _toggle_shuffle)
	previous_button = _icon(row, "previous", "Previous song", func() -> void: jukebox.skip(-1))
	pause_button = _icon(row, "pause", "Pause", func() -> void: jukebox.toggle_pause())
	pause_button.name = "PlayPause"
	pause_button.custom_minimum_size = Vector2.ONE * (36 if compact else 48)
	var circle := Slate.box(Color("1c2d3a"), Color("91a5b5"), 8, 26)
	circle.set_border_width_all(2)
	pause_button.add_theme_stylebox_override("normal", circle)
	next_button = _icon(row, "next", "Next song", func() -> void: jukebox.skip())
	if compact:
		_separator(row)
		shuffle_button = _icon(row, "shuffle", "Shuffle playlist", _toggle_shuffle)
	repeat_button = _icon(row, "repeat", "Repeat", func() -> void: jukebox.cycle_repeat())
	_separator(row)
	if not compact:
		_fade_controls = VBoxContainer.new()
		_fade_controls.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		_fade_controls.add_theme_constant_override("separation", 4)
		row.add_child(_fade_controls)
		_fade_caption = Label.new()
		_fade_caption.add_theme_font_size_override("font_size", 12)
		_fade_controls.add_child(_fade_caption)
		fade = HSlider.new()
		fade.max_value = 8.0
		fade.step = 0.5
		fade.custom_minimum_size.x = 110
		fade.tooltip_text = "Crossfade between personal songs"
		_fade_controls.add_child(fade)
		fade.value_changed.connect(func(value: float) -> void:
			jukebox.set_options(bool(jukebox.shuffle), str(jukebox.repeat_mode), value, bool(jukebox.rules_enabled)))
		resized.connect(func() -> void: _fade_controls.visible = size.x >= 900)
	volume_button = _icon(row, "volume", "Mute music", _toggle_mute)
	volume = HSlider.new()
	volume.name = "MusicVolume"
	if compact: volume.focus_mode = Control.FOCUS_NONE
	volume.max_value = 1.0
	volume.step = 0.01
	volume.custom_minimum_size.x = 50 if compact else 80
	volume.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	volume.tooltip_text = "Music volume"
	volume.value_changed.connect(func(value: float) -> void: jukebox.set_music_volume(value))
	row.add_child(volume)
	if compact:
		expand_button = _icon(row, "expand", "Open full jukebox", func() -> void: jukebox.full_menu_requested.emit())
		expand_button.name = "ExpandJukebox"
	jukebox.changed.connect(refresh)
	refresh()

func _separator(parent: Node) -> void:
	var line := VSeparator.new()
	line.add_theme_stylebox_override("separator", Slate.box(Color.TRANSPARENT, Color("344b5c"), 0))
	parent.add_child(line)

func _icon(parent: Node, glyph: String, hint: String, callback: Callable) -> Button:
	var button := Slate.button(parent, "", glyph, callback)
	button.tooltip_text = hint
	if compact: button.focus_mode = Control.FOCUS_NONE
	button.icon = Slate.icon(glyph, Slate.TEXT, 18 if compact else 22)
	button.custom_minimum_size = Vector2(24 if compact else 32, 30)
	button.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	button.add_theme_stylebox_override("hover", Slate.box(Color("243d4e"), Slate.TEAL, 3))
	button.add_theme_stylebox_override("pressed", Slate.box(Color("214658"), Slate.TEAL, 3))
	button.add_theme_stylebox_override("disabled", StyleBoxEmpty.new())
	button.add_theme_stylebox_override("focus", Slate.box(Color.TRANSPARENT, Slate.TEAL, 0))
	return button

func refresh() -> void:
	var track: String = jukebox.current_track()
	var info: Dictionary = jukebox.track_info(track)
	var creator := str(info.get("creator", ""))
	title_label.text = jukebox.title_for(track) if not track.is_empty() else "Music is quiet"
	if not jukebox.available: title_label.text = "Audio disabled"
	cover.texture = Slate.cover(track)
	source.text = jukebox.source_label() if compact or creator.is_empty() else creator
	var selection: Dictionary = jukebox.effective_selection()
	if _source_icon != null:
		_source_icon.texture = Slate.icon({"game": "game", "song": "library", "playlist": "playlist", "shuffle": "shuffle", "silent": "muted"}.get(str(selection.mode), "playlist"), Slate.MUTED, 12)
	var description: String = jukebox.source_label()
	if not str(selection.target).is_empty(): description += ": " + jukebox.title_for(str(selection.target)) if selection.mode == "song" else ": " + str(selection.target)
	if jukebox.active_rule >= 0: description += " • Rule %d" % (jukebox.active_rule + 1)
	title_label.tooltip_text = "%s\n%s\n%s" % [title_label.text, creator, description]
	source.tooltip_text = description
	previous_button.disabled = not jukebox.can_skip()
	next_button.disabled = previous_button.disabled
	pause_button.icon = Slate.icon("play" if jukebox.paused or jukebox.queue_ended() or track.is_empty() else "pause")
	pause_button.tooltip_text = "Resume" if jukebox.paused else "Play again" if jukebox.queue_ended() else "Pause"
	pause_button.disabled = not jukebox.available or (track.is_empty() and not jukebox.queue_ended())
	var personal: bool = selection.mode not in ["game", "silent"]
	var pixels := 18 if compact else 22
	var random_order: bool = jukebox.shuffle or selection.mode == "shuffle"
	shuffle_button.icon = Slate.icon("shuffle", Slate.TEAL if random_order else Slate.TEXT, pixels)
	shuffle_button.disabled = not personal or selection.mode == "shuffle"
	shuffle_button.tooltip_text = "All music is shuffled; change source in the full jukebox." if selection.mode == "shuffle" else "Shuffle playlist"
	repeat_button.icon = Slate.icon("one" if jukebox.repeat_mode == "one" else "repeat", Slate.TEAL if jukebox.repeat_mode != "off" else Slate.TEXT, pixels)
	repeat_button.disabled = not personal
	repeat_button.tooltip_text = "Repeat: " + {"off": "Off", "all": "All songs", "one": "One song"}.get(str(jukebox.repeat_mode), "Off")
	volume.set_value_no_signal(float(jukebox.music_volume))
	volume.tooltip_text = "Music volume: %d%%" % roundi(volume.value * 100)
	volume_button.icon = Slate.icon("muted" if is_zero_approx(volume.value) else "volume", Slate.TEXT, pixels)
	volume_button.tooltip_text = "Unmute music" if is_zero_approx(volume.value) else "Mute music"
	if volume.value > 0: _unmuted_volume = volume.value
	if fade != null:
		fade.set_value_no_signal(float(jukebox.fade_seconds))
		_fade_caption.text = "Crossfade %ss" % str(float(jukebox.fade_seconds))

func _toggle_shuffle() -> void:
	jukebox.set_options(not bool(jukebox.shuffle), str(jukebox.repeat_mode), float(jukebox.fade_seconds), bool(jukebox.rules_enabled))

func _toggle_mute() -> void:
	jukebox.set_music_volume(_unmuted_volume if is_zero_approx(float(jukebox.music_volume)) else 0.0)

func configure_appearance(config: Dictionary) -> void:
	var background: Color = config.background_color
	var edge: Color = config.border_color
	if not bool(config.show_background): background.a = 0
	if not bool(config.show_border): edge.a = 0
	var style := Slate.box(background, edge, 9, 4)
	style.set_border_width_all(2 if config.get("hud_border_style", "plain") != "plain" else 1)
	if not bool(config.show_border): style.set_border_width_all(0)
	add_theme_stylebox_override("panel", style)
	title_label.add_theme_color_override("font_color", config.text_color if config.get("text_color_custom", false) else Slate.TEXT)
	source.add_theme_color_override("font_color", config.text_color if config.get("text_color_custom", false) else Slate.MUTED)
	if _ornament != null: _ornament.visible = bool(config.show_border) and config.get("hud_border_style", "plain") == "ornate"

func set_editor_preview(value: bool) -> void:
	_editor_preview = value
	queue_redraw()

func _draw() -> void:
	if not _editor_preview: return
	for x: int in 3:
		for y: int in 2:
			draw_circle(Vector2(size.x * 0.5 - 4 + x * 4, 4 + y * 3), 0.8, Slate.TEAL)

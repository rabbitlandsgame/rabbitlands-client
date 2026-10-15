class_name OldcraftDialogueStyle
extends RefCounted
## Event-driven fantasy styling for the one NPC dialogue window.
##
## One parchment surface carries the speaker, copy and compact response rows.
## A fine brass edge and oxblood quest accent retain Eloria's visual identity
## without a wide decorative surround. Styles are retained after scene setup
## or a dialogue packet; the treatment adds no per-frame or per-actor work.

const GOLD := Color(0.957, 0.773, 0.259, 1.0)
const GOLD_DARK := Color(0.722, 0.541, 0.231, 1.0)
const GOLD_BRIGHT := Color(1.0, 0.86, 0.48, 1.0)
const INK := Color(0.16, 0.095, 0.045, 1.0)
const WARM_TEXT := Color(0.961, 0.941, 0.878, 1.0)
const BURGUNDY := Color(0.42, 0.072, 0.045, 1.0)
const BURGUNDY_HOVER := Color(0.62, 0.12, 0.065, 1.0)
const QUEST_YELLOW := BURGUNDY
const TALK_GOLD := Color(0.40, 0.29, 0.17, 1.0)
const STYLE_META := &"eloria_oldcraft_dialogue_style"
const DECORATION_SIGNAL_META := &"eloria_dialogue_decoration_signal"
const PARCHMENT_TEXTURE := preload(
	"res://assets/ui/oldcraft_inspired/eloria_parchment.png")


static func _flat_box(background: Color, border: Color, width: int,
		corner: int, margin: float) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = background
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(corner)
	box.set_content_margin_all(margin)
	return box


static func _parchment_box() -> StyleBoxTexture:
	var box := StyleBoxTexture.new()
	box.texture = PARCHMENT_TEXTURE
	# The source is deliberately generous and square so it can be reused by
	# several surfaces. Crop its calm centre into the wide reading area rather
	# than crushing the paper grain into the dialogue aspect ratio.
	var texture_size := PARCHMENT_TEXTURE.get_size()
	var crop_height := texture_size.y * 0.62
	box.region_rect = Rect2(0.0, (texture_size.y - crop_height) * 0.5,
		texture_size.x, crop_height)
	box.modulate_color = Color(0.985, 0.94, 0.84, 1.0)
	box.set_content_margin_all(0.0)
	return box


static func _sync_decoration_rects(panel: PanelContainer, backdrop: Panel,
		frame_art: TextureRect) -> void:
	if backdrop != null:
		backdrop.position = panel.position
		backdrop.size = panel.size
	if frame_art != null:
		frame_art.position = panel.position
		frame_art.size = panel.size


static func apply(main: Control) -> void:
	if main == null:
		return
	var panel := main.get_node_or_null("%DialoguePanel") as PanelContainer
	var kicker := main.get_node_or_null("%DialogueKicker") as Label
	var speaker := main.get_node_or_null("%DialogueName") as Label
	var divider := main.get_node_or_null("%DialogueDivider") as HSeparator
	var body := main.get_node_or_null("%DialogueText") as RichTextLabel
	var instruction := main.get_node_or_null("%DialogueInstruction") as Label
	var footer := main.get_node_or_null("%DialogueFooter") as Label
	var frame_art := main.get_node_or_null("%DialogueFrameTexture") as TextureRect
	var backdrop := main.get_node_or_null("%DialogueBackdrop") as Panel
	if panel == null or speaker == null or body == null:
		return

	# Paper fills the entire window; the content host supplies just a fine edge
	# and a small inset. The old wide carved art no longer consumes reading room.
	var frame := _flat_box(Color.TRANSPARENT, GOLD_DARK, 2, 2, 16.0)
	frame.shadow_color = Color(0.0, 0.0, 0.0, 0.45)
	frame.shadow_size = 6
	panel.add_theme_stylebox_override("panel", frame)
	if backdrop != null:
		backdrop.add_theme_stylebox_override("panel", _parchment_box())
	if frame_art != null:
		frame_art.hide()
	if not panel.has_meta(DECORATION_SIGNAL_META):
		# The window drag contract moves only DialoguePanel. Mirror that rect from
		# its existing change signal so the decorative siblings follow without a
		# polling process or any work while the window is idle.
		panel.item_rect_changed.connect(func() -> void:
			_sync_decoration_rects(panel, backdrop, frame_art))
		var options := main.get_node_or_null("%DialogueOptions") as VBoxContainer
		if options != null:
			options.minimum_size_changed.connect(func() -> void:
				layout_content(main))
		panel.set_meta(DECORATION_SIGNAL_META, true)

	speaker.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	speaker.add_theme_color_override("font_color", INK)
	speaker.add_theme_constant_override("outline_size", 0)
	if kicker != null:
		kicker.add_theme_color_override("font_color", TALK_GOLD)
		kicker.add_theme_constant_override("outline_size", 0)
	if divider != null:
		var rule := StyleBoxFlat.new()
		rule.bg_color = GOLD_DARK
		rule.content_margin_top = 1.0
		rule.content_margin_bottom = 1.0
		divider.add_theme_stylebox_override("separator", rule)

	var page := StyleBoxEmpty.new()
	page.set_content_margin_all(2.0)
	body.add_theme_stylebox_override("normal", page)
	body.add_theme_stylebox_override("focus", page)
	body.add_theme_color_override("default_color", INK)
	body.add_theme_color_override("font_selected_color", Color(0.08, 0.045, 0.02, 1.0))
	body.add_theme_color_override("selection_color", Color(0.78, 0.58, 0.24, 0.45))
	body.add_theme_font_size_override("normal_font_size", 16)
	body.add_theme_constant_override("line_separation", 1)
	if instruction != null:
		instruction.add_theme_color_override("font_color", TALK_GOLD)
		instruction.add_theme_constant_override("outline_size", 0)
	if footer != null:
		footer.add_theme_color_override("font_color", TALK_GOLD)
	layout(main)
	main.set_meta(STYLE_META, true)


static func layout(main: Control) -> void:
	var panel := main.get_node_or_null("%DialoguePanel") as PanelContainer
	var game_view := main.get_node_or_null("%GameView") as Control
	var body := main.get_node_or_null("%DialogueText") as RichTextLabel
	var options_scroll := main.get_node_or_null("%DialogueOptionsScroll") as ScrollContainer
	var frame_art := main.get_node_or_null("%DialogueFrameTexture") as TextureRect
	var backdrop := main.get_node_or_null("%DialogueBackdrop") as Panel
	if panel == null or game_view == null:
		return
	# The reference puts conversation at the upper left so most of the world and
	# the NPC remain visible. Clamp the same composition into a short viewport
	# instead of letting the lower responses fall off-screen.
	var available := game_view.size
	var width := minf(560.0, maxf(420.0, available.x - 48.0))
	var height := minf(560.0, maxf(430.0, available.y - 48.0))
	width = minf(width, maxf(1.0, available.x - 32.0))
	height = minf(height, maxf(1.0, available.y - 32.0))
	var left := minf(32.0, maxf(16.0, available.x - width - 16.0))
	var top := minf(128.0, maxf(16.0, available.y - height - 24.0))
	panel.set_anchors_preset(Control.PRESET_TOP_LEFT)
	# Clear the old content minimum before shrinking for a shorter viewport.
	if body != null:
		body.custom_minimum_size.y = 0.0
	if options_scroll != null:
		options_scroll.custom_minimum_size.y = 0.0
	panel.position = Vector2(left, top)
	panel.size = Vector2(width, height)
	# The paper sibling follows the established draggable content panel.
	if backdrop != null:
		backdrop.z_index = 19
	if frame_art != null:
		frame_art.z_index = 20
	panel.z_index = 21
	_sync_decoration_rects(panel, backdrop, frame_art)
	layout_content(main)


static func layout_content(main: Control) -> void:
	var panel := main.get_node_or_null("%DialoguePanel") as PanelContainer
	var body := main.get_node_or_null("%DialogueText") as RichTextLabel
	var options_scroll := main.get_node_or_null("%DialogueOptionsScroll") as ScrollContainer
	var options := main.get_node_or_null("%DialogueOptions") as VBoxContainer
	if panel == null:
		return
	var room := maxf(1.0, panel.size.y - 132.0)
	if body != null:
		body.custom_minimum_size.y = minf(80.0, room * 0.3)
	if options_scroll != null and options != null:
		# Short choice lists use only their actual height. Longer lists can use
		# almost half the available space; the text receives the remaining room.
		options_scroll.size_flags_vertical = Control.SIZE_FILL
		options_scroll.custom_minimum_size.y = minf(
			options.get_combined_minimum_size().y, room * 0.45)


static func update_state(main: Control, quest: bool, quest_id: int,
		has_options: bool) -> void:
	var kicker := main.get_node_or_null("%DialogueKicker") as Label
	var instruction := main.get_node_or_null("%DialogueInstruction") as Label
	var footer := main.get_node_or_null("%DialogueFooter") as Label
	var options_scroll := main.get_node_or_null("%DialogueOptionsScroll") as ScrollContainer
	if kicker != null:
		kicker.text = (("QUEST MISSIVE  |  %d" % quest_id
			if quest_id > 0 else "QUEST MISSIVE") if quest
			else "A VOICE OF ELORIA")
		kicker.add_theme_color_override("font_color", QUEST_YELLOW if quest else TALK_GOLD)
	if instruction != null:
		instruction.visible = has_options
		instruction.text = "CHOOSE YOUR COURSE" if quest else "CHOOSE YOUR RESPONSE"
	if options_scroll != null:
		# Do not reserve an empty black response well when the server supplies a
		# farewell-only line. Restoring it here keeps branchy dialogue scrollable.
		options_scroll.visible = has_options
	if footer != null:
		footer.text = ("QUEST WORDS ARE RECORDED  /  ESC CLOSES"
			if quest else "ESC  Close conversation")


static func sync_visibility(main: Control, visible: bool) -> void:
	var frame_art := main.get_node_or_null("%DialogueFrameTexture") as TextureRect
	var panel := main.get_node_or_null("%DialoguePanel") as PanelContainer
	var backdrop := main.get_node_or_null("%DialogueBackdrop") as Panel
	if frame_art != null:
		if panel != null:
			panel.z_index = 21
			frame_art.z_index = 20
		frame_art.hide()
	if backdrop != null:
		backdrop.z_index = 19
		backdrop.visible = visible


static func option_label(label: String, quest: bool) -> String:
	return ("◆  " if quest else "›  ") + label


static func style_option(button: Button, quest: bool, index: int) -> void:
	if button == null:
		return
	var primary := quest and index == 0
	var normal := _flat_box(BURGUNDY if primary else Color(0.94, 0.86, 0.69, 0.4),
		GOLD_DARK, 2 if primary else 1, 4, 5.0)
	var hover := _flat_box(BURGUNDY_HOVER, GOLD_DARK, 2, 4, 5.0)
	var pressed := _flat_box(Color(0.25, 0.035, 0.022, 1.0),
		Color(0.72, 0.48, 0.16, 1.0), 2, 4, 5.0)
	for box: StyleBoxFlat in [normal, hover, pressed]:
		box.border_blend = true
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", pressed)
	button.add_theme_stylebox_override("hover_pressed", pressed)
	button.add_theme_stylebox_override("focus",
		_flat_box(Color.TRANSPARENT, BURGUNDY_HOVER, 2, 4, 5.0))
	button.add_theme_color_override("font_color", WARM_TEXT if primary else INK)
	button.add_theme_color_override("font_hover_color", GOLD_BRIGHT)
	button.add_theme_color_override("font_pressed_color", GOLD)
	button.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.88))
	button.add_theme_constant_override("outline_size", 0)
	button.add_theme_font_size_override("font_size", 15)
	button.custom_minimum_size.y = 32.0
	button.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT

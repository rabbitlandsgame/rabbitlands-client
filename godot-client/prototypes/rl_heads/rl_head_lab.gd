extends Node3D
## The RL head lab: the real client actor (ReplicatedActor3D) wearing the RL
## head prototype through the same `appearance.rl_head` path the game uses,
## on the shared stage (rl_head_stage.gd). Everything the head can do is on
## the left: sex and preset, every identity control from the head's own
## `rlHead.controls` grouped as it groups them, colours with the game's
## palettes, painted features, hairstyle, facial hair, headwear, a torso,
## clips, expressions, quality and hair motion, camera framings and stats.
##
## Launch with open-rl-head-lab.bat. Drag with the left or right mouse button
## to orbit, wheel to zoom, middle-drag to pan. Command-line options after
## `--`: --sex male --preset rowan --quality medium --look graded, and
## --selftest yes, which drives the panel's own handlers through a short tour,
## saves screenshots under .local/rl-heads/evidence/lab/ and quits.

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const QUALITY_LABELS: Array[String] = ["Low", "Medium", "High"]
const EXPRESSION_BUTTONS: Array[String] = ["neutral", "smile", "grin", "frown", "angry",
	"surprise", "sad", "squint", "pucker", "sneer"]
const CAMERA_BUTTONS := [["Front", "front"], ["3/4", "three_quarter"], ["Profile", "profile"],
	["Rear", "rear"], ["Close-up", "close"], ["Eyes", "eyes"], ["Hair", "hair"], ["Bust", "bust"],
	["Full body", "full"]]

var options: Dictionary = {}
var actor: ReplicatedActor3D
var face: RLHeadAppearance
var _archetype_library: Dictionary = {}

var _sex := "female"
var _headwear := 0
var _torso := false
var _cape := false
var _clip := "Idle"
var _quality := ActorRenderQuality.Quality.HIGH
var _hair_motion := true
var _auto_blink := true
var _talking := false
var _rebuilding := false

var _stage_parts: Dictionary = {}
var _camera: Camera3D
var _view := "three_quarter"
var _target := Vector3.ZERO
var _yaw := 0.0
var _pitch := 0.0
var _distance := 1.0
var _dragging := MOUSE_BUTTON_NONE

var _panel: VBoxContainer
var _sex_option: OptionButton
var _preset_option: OptionButton
var _controls_box: VBoxContainer
var _sliders: Dictionary = {}
var _colour_buttons: Dictionary = {}
var _amount_sliders: Dictionary = {}
var _hair_option: OptionButton
var _brow_option: OptionButton
var _beard_option: OptionButton
var _stats: Label
var _toast: Label
var _toast_until := 0


func _ready() -> void:
	var values := OS.get_cmdline_user_args()
	for index in range(0, values.size() - 1, 2):
		options[values[index].trim_prefix("--")] = values[index + 1]
	var window := get_window()
	window.title = "Rabbit Lands - RL head lab"
	window.size = Vector2i(int(options.get("width", "1600")), int(options.get("height", "1000")))
	window.min_size = Vector2i(1000, 640)
	get_viewport().msaa_3d = Viewport.MSAA_4X
	_sex = str(options.get("sex", _sex))
	_quality = maxi(0, ActorRenderQuality.QUALITY_NAMES.find(str(options.get("quality", "high"))))
	_stage_parts = Stage.build(self, str(options.get("look", "neutral")))
	_camera = Camera3D.new()
	_camera.cull_mask = 1
	_camera.near = 0.02
	add_child(_camera)
	_camera.current = true
	var names := RLHeadAppearance.preset_names(_sex)
	var preset := str(options.get("preset", names[0] if not names.is_empty() else ""))
	face = RLHeadAppearance.from_preset(preset)
	if face == null:
		face = RLHeadAppearance.new()
		face.sex = _sex
	else:
		_sex = face.sex
	_build_ui()
	await _rebuild_actor()
	_set_view(_view)
	if options.get("selftest", "no") == "yes":
		_selftest.call_deferred()


# ---------------------------------------------------------------- actor

func _visuals() -> Dictionary:
	var visuals := {}
	if _headwear > 0:
		visuals[3] = _headwear
	if _torso:
		visuals[5] = Stage.TORSO
	if _cape:
		visuals[2] = Stage.CAPE
	return visuals


## Selected human bases retain their saved body/clothes while the lab edits
## their raw head controls. Existing head-only presets keep the original path.
func _actor_appearance() -> Dictionary:
	if _archetype_library.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(
			"res://data/actors/rl_head_archetypes.json"))
		if parsed is Dictionary:
			_archetype_library = parsed
	var result := {}
	for row: Dictionary in _archetype_library.get("archetypes", []):
		if row.id == face.preset and row.sex == _sex:
			result = (row.appearance_pc3 as Dictionary).duplicate(true)
			break
	result["rl_head"] = face.to_dict()
	return result


func _rebuild_actor() -> void:
	_rebuilding = true
	if actor != null:
		actor.queue_free()
		actor = null
		await get_tree().process_frame
	face.sex = _sex
	actor = Stage.spawn(self, _sex, _actor_appearance(), _visuals(), _quality)
	var player := actor.animation_player
	if player != null and not player.animation_finished.is_connected(_on_clip_finished):
		player.animation_finished.connect(_on_clip_finished)
	_play_clip()
	_sync_rig_switches()
	_refresh_controls()
	_rebuilding = false


## Everything but a control slider goes through the actor's appearance pass,
## exactly as a changed appearance from the server would.
func _apply_face() -> void:
	if actor == null or _rebuilding:
		return
	actor.apply_appearance_variants(_actor_appearance())
	_sync_rig_switches()


func _sync_rig_switches() -> void:
	var rig := actor.rl_head() if actor != null else null
	if rig == null:
		return
	rig.set_hair_motion_allowed(_hair_motion)
	var expression := rig.expression()
	expression.always_update = true
	expression.set_auto_blink(_auto_blink)
	expression.set_talking(_talking)


func _play_clip() -> void:
	var player := actor.animation_player if actor != null else null
	if player == null:
		return
	var clip := str(Stage.CLIPS.get(_clip, _clip))
	if not player.has_animation(clip):
		_show_toast("Clip %s is not in this rig's library" % clip)
		return
	actor._advance_facing_offset(1.0)
	player.play(clip)


func _on_clip_finished(_name: StringName) -> void:
	# One-shot clips (the nod) repeat so they can be watched.
	if _clip != "Rest":
		_play_clip()


# ---------------------------------------------------------------- camera

func _set_view(view: String) -> void:
	_view = view
	if actor == null:
		return
	var spec: Dictionary = Stage.VIEWS.get(view, Stage.VIEWS["front"])
	var forward := Stage.face_forward(actor)
	_target = Stage.head_rest(actor).origin + Vector3.UP * float(spec["up"]) \
		+ forward * float(spec["forward"])
	_yaw = atan2(forward.x, forward.z) + deg_to_rad(float(spec["yaw"]))
	_pitch = deg_to_rad(float(spec["pitch"]))
	_distance = float(spec["distance"])
	_camera.fov = float(spec["fov"])
	_update_camera()


func _update_camera() -> void:
	var direction := Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch))
	_camera.global_position = _target + direction * _distance
	_camera.look_at(_target, Vector3.UP)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var button := event as InputEventMouseButton
		if button.button_index in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE]:
			_dragging = button.button_index if button.pressed else MOUSE_BUTTON_NONE
		elif button.pressed and button.button_index == MOUSE_BUTTON_WHEEL_UP:
			_distance = maxf(0.12, _distance * 0.9)
			_update_camera()
		elif button.pressed and button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_distance = minf(8.0, _distance * 1.1)
			_update_camera()
	elif event is InputEventMouseMotion and _dragging != MOUSE_BUTTON_NONE:
		var motion := (event as InputEventMouseMotion).relative
		if _dragging == MOUSE_BUTTON_MIDDLE:
			var right := _camera.global_basis.x
			var up := _camera.global_basis.y
			_target += (-right * motion.x + up * motion.y) * _distance * 0.0015
		else:
			_yaw -= motion.x * 0.008
			_pitch = clampf(_pitch + motion.y * 0.006, -1.2, 1.3)
		_update_camera()


# ---------------------------------------------------------------- UI

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var frame := PanelContainer.new()
	frame.position = Vector2(8, 8)
	frame.size = Vector2(380, get_window().size.y - 16)
	frame.anchor_bottom = 1.0
	frame.offset_bottom = -8
	layer.add_child(frame)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	frame.add_child(scroll)
	_panel = VBoxContainer.new()
	_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_panel.custom_minimum_size.x = 350
	scroll.add_child(_panel)
	_stats = Label.new()
	_stats.position = Vector2(get_window().size.x - 330, 10)
	_stats.add_theme_font_size_override("font_size", 13)
	_stats.add_theme_color_override("font_outline_color", Color.BLACK)
	_stats.add_theme_constant_override("outline_size", 4)
	layer.add_child(_stats)
	_toast = Label.new()
	_toast.position = Vector2(400, 12)
	_toast.add_theme_color_override("font_outline_color", Color.BLACK)
	_toast.add_theme_constant_override("outline_size", 5)
	layer.add_child(_toast)

	_heading("Head")
	_sex_option = _option("Sex", ["female", "male"], func(index: int) -> void:
		_sex = ["female", "male"][index]
		var names := RLHeadAppearance.preset_names(_sex)
		face = RLHeadAppearance.from_preset(names[0]) if not names.is_empty() else face
		_refresh_presets()
		_refresh_all()
		_rebuild_actor())
	_sex_option.select(0 if _sex == "female" else 1)
	_preset_option = _option("Preset", [], func(index: int) -> void:
		var picked := RLHeadAppearance.from_preset(_preset_option.get_item_text(index))
		if picked != null:
			face = picked
			_refresh_all()
			_apply_face())
	_refresh_presets()
	var row := _row()
	_button(row, "Randomize identity", _randomize_identity)
	_button(row, "Reset", func() -> void:
		var original := RLHeadAppearance.from_preset(face.preset)
		face = original if original != null else RLHeadAppearance.new()
		face.sex = _sex
		_refresh_all()
		_apply_face())
	_button(row, "Copy JSON", _copy_json)

	_heading("Hair and grooming")
	_hair_option = _option("Hairstyle", [], func(index: int) -> void:
		face.hair = _hair_option.get_item_metadata(index)
		_apply_face())
	_beard_option = _option("Facial hair", [], func(index: int) -> void:
		face.beard = _beard_option.get_item_metadata(index)
		_apply_face())
	_groom_slider("hair_length", "Length", -1.0, 1.0)
	_groom_slider("hair_volume", "Volume", -1.0, 1.0)
	_groom_slider("hair_detail", "Messiness", 0.0, 100.0)

	_heading("Identity")
	_controls_box = VBoxContainer.new()
	_panel.add_child(_controls_box)

	_heading("Colours")
	_colour_row("Skin", "skin", _palette(10, func(i: int) -> Color: return AppearanceVariants.skin_color(i)))
	_colour_row("Eyes", "eyes", _palette(12, func(i: int) -> Color: return AppearanceVariants.eye_color(i)))
	_colour_row("Hair", "hair_color", _palette(20, func(i: int) -> Color: return AppearanceVariants.hair_color(i)))
	_colour_row("Brows", "brow_color", [])
	var brow_row := _row()
	_button(brow_row, "Brows from hair", func() -> void:
		face.brow_color = face.hair_color.darkened(0.25)
		_refresh_all()
		_apply_face())
	_colour_row("Lips", "lip_tint", [])

	_heading("Painted features")
	for amount: String in ["freckles", "liner", "stubble"]:
		_amount_slider(amount)
	_amount_slider("liner_wing")

	_heading("Brows")
	var brow_names: Array = []
	for style: String in RLHeadAppearance.BROW_STYLES:
		brow_names.append(style.capitalize())
	_brow_option = _option("Brow style", brow_names, func(index: int) -> void:
		face.brow_style = float(index)
		_apply_face())
	_amount_slider("brow_thickness", -1.0)

	_heading("Headwear")
	var headwear_names: Array = []
	for entry: Array in Stage.HEADWEAR:
		headwear_names.append(("3:%d " % entry[0] if entry[0] > 0 else "") + str(entry[1]))
	_option("Headwear", headwear_names, func(index: int) -> void:
		_headwear = int(Stage.HEADWEAR[index][0])
		actor.apply_equipment_visuals(_visuals()))
	var gear_row := _row()
	_check(gear_row, "Torso (5:%d)" % Stage.TORSO, _torso, func(on: bool) -> void:
		_torso = on
		actor.apply_equipment_visuals(_visuals()))
	_check(gear_row, "Cape", _cape, func(on: bool) -> void:
		_cape = on
		actor.apply_equipment_visuals(_visuals()))

	_heading("Animation and face")
	_option("Clip", Stage.CLIPS.keys(), func(index: int) -> void:
		_clip = Stage.CLIPS.keys()[index]
		_play_clip()).select(Stage.CLIPS.keys().find(_clip))
	var expression_grid := GridContainer.new()
	expression_grid.columns = 4
	_panel.add_child(expression_grid)
	_button(expression_grid, "blink", func() -> void:
		if actor.rl_head() != null:
			actor.rl_head().expression().blink())
	for expression_name: String in EXPRESSION_BUTTONS:
		_button(expression_grid, expression_name, func() -> void:
			if actor.rl_head() != null:
				actor.rl_head().expression().set_expression(expression_name, 1.0, 0.25))
	var face_row := _row()
	_check(face_row, "Talk", _talking, func(on: bool) -> void:
		_talking = on
		_sync_rig_switches())
	_check(face_row, "Auto-blink", _auto_blink, func(on: bool) -> void:
		_auto_blink = on
		_sync_rig_switches())
	var look := _row()
	var look_label := Label.new()
	look_label.text = "Look"
	look.add_child(look_label)
	var look_slider := HSlider.new()
	look_slider.min_value = -0.6
	look_slider.max_value = 0.6
	look_slider.step = 0.01
	look_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	look_slider.value_changed.connect(func(value: float) -> void:
		if actor.rl_head() != null:
			actor.rl_head().expression().set_look(Vector2(value, 0.0)))
	look.add_child(look_slider)

	_heading("Quality")
	_option("Quality", QUALITY_LABELS, func(index: int) -> void:
		_quality = index
		actor.apply_render_quality(_quality, false)
		_sync_rig_switches()).select(_quality)
	var quality_row := _row()
	_check(quality_row, "Hair motion", _hair_motion, func(on: bool) -> void:
		_hair_motion = on
		_sync_rig_switches())
	_option("Stage look", ["Neutral (colour check)", "Game (Painted ground)",
			"Graded (Full painted)"], func(index: int) -> void:
		(_stage_parts["environment"] as WorldEnvironment).environment = Stage.environment(
			["neutral", "game", "graded"][index]))

	_heading("Camera")
	var camera_grid := GridContainer.new()
	camera_grid.columns = 3
	_panel.add_child(camera_grid)
	for entry: Array in CAMERA_BUTTONS:
		_button(camera_grid, entry[0], _set_view.bind(entry[1]))
	_refresh_all()


func _heading(text: String) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 17)
	label.add_theme_color_override("font_color", Color(0.95, 0.82, 0.55))
	_panel.add_child(label)


func _row() -> HBoxContainer:
	var row := HBoxContainer.new()
	_panel.add_child(row)
	return row


func _button(parent: Control, text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(action)
	parent.add_child(button)
	return button


func _check(parent: Control, text: String, on: bool, action: Callable) -> CheckBox:
	var box := CheckBox.new()
	box.text = text
	box.button_pressed = on
	box.toggled.connect(action)
	parent.add_child(box)
	return box


func _option(text: String, items: Array, action: Callable) -> OptionButton:
	var row := _row()
	var label := Label.new()
	label.text = text
	label.custom_minimum_size.x = 92
	row.add_child(label)
	var option := OptionButton.new()
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for item: Variant in items:
		option.add_item(str(item))
	option.item_selected.connect(action)
	row.add_child(option)
	return option


func _palette(count: int, colour_of: Callable) -> Array:
	var colours: Array = []
	for index: int in count:
		colours.append(colour_of.call(index))
	return colours


func _colour_row(text: String, field: String, palette: Array) -> void:
	var row := _row()
	var label := Label.new()
	label.text = text
	label.custom_minimum_size.x = 60
	row.add_child(label)
	var picker := ColorPickerButton.new()
	picker.custom_minimum_size = Vector2(56, 24)
	picker.edit_alpha = false
	picker.color_changed.connect(func(colour: Color) -> void:
		face.set(field, colour)
		_apply_face())
	row.add_child(picker)
	_colour_buttons[field] = picker
	if palette.is_empty():
		return
	var swatches := GridContainer.new()
	swatches.columns = 10
	_panel.add_child(swatches)
	for colour: Color in palette:
		var swatch := Button.new()
		swatch.custom_minimum_size = Vector2(26, 18)
		var style := StyleBoxFlat.new()
		style.bg_color = colour
		swatch.add_theme_stylebox_override("normal", style)
		swatch.add_theme_stylebox_override("hover", style)
		swatch.pressed.connect(func() -> void:
			face.set(field, colour)
			picker.color = colour
			_apply_face())
		swatches.add_child(swatch)


func _groom_slider(field: String, text: String, minimum: float, maximum: float) -> void:
	var row := _row()
	var label := Label.new()
	label.text = text
	label.custom_minimum_size.x = 92
	row.add_child(label)
	var slider := HSlider.new()
	slider.name = field
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = 1.0 if field == "hair_detail" else 0.01
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.tooltip_text = "Sleek (0) to messy (100); 50 is the authored finish." if field == "hair_detail" else "Relative to the authored style. Length changes loose strands on tied styles."
	slider.value_changed.connect(func(value: float) -> void:
		face.set(field, value)
		_apply_face())
	row.add_child(slider)
	_amount_sliders[field] = slider


func _amount_slider(field: String, minimum: float = 0.0) -> void:
	var row := _row()
	var label := Label.new()
	label.text = field.capitalize()
	label.custom_minimum_size.x = 92
	row.add_child(label)
	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = 1.0
	slider.step = 0.01
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.value_changed.connect(func(value: float) -> void:
		face.set(field, value)
		_apply_face())
	row.add_child(slider)
	_amount_sliders[field] = slider


## Rebuilds the identity sliders from the head's own controls, by group.
func _refresh_controls() -> void:
	for child: Node in _controls_box.get_children():
		child.queue_free()
	_sliders.clear()
	var info := RLHeadLibrary.head(_sex)
	var groups: Dictionary = {}
	for control: Dictionary in info.get("controls", []) as Array:
		var group := str(control.get("group", "other"))
		if not groups.has(group):
			groups[group] = []
		(groups[group] as Array).append(control)
	for group: String in groups:
		var title := Label.new()
		title.text = group.capitalize()
		title.add_theme_color_override("font_color", Color(0.7, 0.85, 1.0))
		_controls_box.add_child(title)
		for control: Dictionary in groups[group]:
			var control_name := str(control.get("name", ""))
			var row := HBoxContainer.new()
			_controls_box.add_child(row)
			var label := Label.new()
			label.text = str(control.get("label", control_name))
			label.custom_minimum_size.x = 120
			label.clip_text = true
			row.add_child(label)
			var slider := HSlider.new()
			slider.min_value = -1.0
			slider.max_value = 1.0
			slider.step = 0.01
			slider.value = face.control(control_name)
			slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var value_label := Label.new()
			value_label.custom_minimum_size.x = 40
			value_label.text = "%.2f" % slider.value
			slider.value_changed.connect(func(value: float) -> void:
				face.set_control(control_name, value)
				value_label.text = "%.2f" % value
				if actor != null and actor.rl_head() != null:
					actor.rl_head().set_control(control_name, value))
			row.add_child(slider)
			row.add_child(value_label)
			_sliders[control_name] = slider


func _refresh_presets() -> void:
	_preset_option.clear()
	for name: String in RLHeadAppearance.preset_names(_sex):
		_preset_option.add_item(name)
		if name == face.preset:
			_preset_option.select(_preset_option.item_count - 1)


## Puts every widget back in line with `face` without firing their handlers.
func _refresh_all() -> void:
	for field: String in _colour_buttons:
		(_colour_buttons[field] as ColorPickerButton).set_block_signals(true)
		(_colour_buttons[field] as ColorPickerButton).color = face.get(field)
		(_colour_buttons[field] as ColorPickerButton).set_block_signals(false)
	for field: String in _amount_sliders:
		(_amount_sliders[field] as HSlider).set_value_no_signal(float(face.get(field)))
	_brow_option.set_block_signals(true)
	_brow_option.select(clampi(roundi(face.brow_style), 0, RLHeadAppearance.BROW_STYLES.size() - 1))
	_brow_option.set_block_signals(false)
	for control_name: String in _sliders:
		(_sliders[control_name] as HSlider).set_value_no_signal(face.control(control_name))
	var hair_styles := RLHeadLibrary.hair_styles()
	hair_styles.append_array(RLHeadLibrary.legacy_hair_styles(_sex))
	_fill_styles(_hair_option, hair_styles, face.hair)
	_fill_styles(_beard_option, RLHeadLibrary.beard_styles(), face.beard)


func _fill_styles(option: OptionButton, names: PackedStringArray, current: String) -> void:
	option.set_block_signals(true)
	option.clear()
	var all := PackedStringArray([RLHeadAppearance.NONE])
	all.append_array(names)
	if not all.has(current):
		all.append(current)
	for name: String in all:
		var on_disk := name == RLHeadAppearance.NONE or names.has(name)
		option.add_item(name if on_disk else name + " (missing)")
		option.set_item_metadata(option.item_count - 1, name)
		if name == current:
			option.select(option.item_count - 1)
	option.set_block_signals(false)


func _randomize_identity() -> void:
	var random := RandomNumberGenerator.new()
	random.randomize()
	for control: Dictionary in RLHeadLibrary.head(_sex).get("controls", []) as Array:
		var value := clampf(random.randfn(0.0, 0.45), -1.0, 1.0)
		face.set_control(str(control.get("name", "")), value)
	_refresh_all()
	_apply_face()


func _copy_json(to_clipboard: bool = true) -> void:
	var names := RLHeadLibrary.head(_sex).get("control_names", PackedStringArray()) as PackedStringArray
	var text := JSON.stringify({"rl_head": face.to_dict(),
		"bytes": face.encode(names).hex_encode()}, "  ")
	if to_clipboard:
		DisplayServer.clipboard_set(text)
	print(text)
	_show_toast("Appearance JSON copied (%d bytes encoded)" % face.encode(names).size())


func _show_toast(text: String) -> void:
	_toast.text = text
	_toast_until = Time.get_ticks_msec() + 3000


# ---------------------------------------------------------------- stats

func _process(_delta: float) -> void:
	if _toast_until > 0 and Time.get_ticks_msec() > _toast_until:
		_toast.text = ""
		_toast_until = 0
	if Engine.get_process_frames() % 10 != 0:
		return
	var lines := PackedStringArray()
	lines.append("FPS %d   frame %.2f ms" % [Engine.get_frames_per_second(),
		Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0])
	lines.append("Draw calls %d   primitives %d" % [
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)])
	lines.append("Video memory %.1f MB (textures %.1f, buffers %.1f)" % [
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED) / 1048576.0,
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED) / 1048576.0,
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_BUFFER_MEM_USED) / 1048576.0])
	var rig := actor.rl_head() if actor != null else null
	if rig != null:
		lines.append("RL head %s, %d triangles near, quality %s" % [rig.appearance.sex,
			rig.near_triangle_count(), QUALITY_LABELS[rig.quality]])
		var motion := rig.hair_motion()
		lines.append("Hair motion: %s" % ("running" if motion != null and motion.is_running()
			else "none" if motion == null else "resting"))
		var weights := rig.expression().weights()
		var shown := PackedStringArray()
		for shape: Variant in weights:
			shown.append("%s %.2f" % [str(shape).trim_prefix("ex_"), float(weights[shape])])
		lines.append("Expression: " + (", ".join(shown) if not shown.is_empty() else "neutral"))
	_stats.text = "\n".join(lines)


# ---------------------------------------------------------------- self-test

func _selftest() -> void:
	var folder := ProjectSettings.globalize_path("res://").path_join(
		"../.local/rl-heads/evidence/lab").simplify_path()
	DirAccess.make_dir_recursive_absolute(folder)
	await _settle(folder, "01_start")
	var names := RLHeadLibrary.head(_sex).get("control_names", PackedStringArray()) as PackedStringArray
	(_sliders[names[0]] as HSlider).value = 1.0
	(_sliders[names[names.size() - 1]] as HSlider).value = -1.0
	await _settle(folder, "02_controls")
	_randomize_identity()
	(_colour_buttons["skin"] as ColorPickerButton).color_changed.emit(AppearanceVariants.skin_color(4))
	(_amount_sliders["freckles"] as HSlider).value = 0.9
	await _settle(folder, "03_random_skin")
	_headwear = 134
	_torso = true
	actor.apply_equipment_visuals(_visuals())
	actor.rl_head().expression().set_expression("smile", 1.0, 0.0)
	_set_view("three_quarter")
	await _settle(folder, "04_helm_torso_smile")
	_quality = ActorRenderQuality.Quality.LOW
	actor.apply_render_quality(_quality, false)
	_sync_rig_switches()
	await _settle(folder, "05_low")
	_sex_option.select(1)
	_sex_option.item_selected.emit(1)
	for frame in 10:
		await get_tree().process_frame
	_set_view("front")
	_hair_option.select(_hair_option.item_count - 1)
	_hair_option.item_selected.emit(_hair_option.item_count - 1)
	await _settle(folder, "06_male")
	_copy_json(false)
	print("RL_HEAD_LAB_SELFTEST_DONE ", folder)
	get_tree().quit()


func _settle(folder: String, name: String) -> void:
	for frame in 12:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(folder.path_join(name + ".png"))

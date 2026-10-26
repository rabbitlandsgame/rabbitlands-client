extends PanelContainer
## A portrait observes the supplied, authoritative actor; it never poses,
## clones, recolours or moves that actor or its animation clock.
const Art := preload("res://src/ui/leaderboard_art.gd")
const GOLD := Color("f1cd78")
const TEXT := Color("fffaf0")
const PORTRAIT_LAYER_MASK := 1 # Native models; excludes gameplay/map overlays.
const PORTRAIT_INTERVAL := 1.0 / 30.0

var speaker_label: Label
var body_label: Label
var _row: HBoxContainer
var _portrait_frame: PanelContainer
var _portrait_image: TextureRect
var _viewport: SubViewport
var _camera: Camera3D
var _actor: WeakRef
var _elapsed := 0.0
var _layout_width := -1.0

func _init() -> void:
	name = "CampaignDialogue"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	_row = HBoxContainer.new()
	_row.name = "DialogueRow"
	_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_row.add_theme_constant_override("separation", 18)
	add_child(_row)
	_portrait_frame = PanelContainer.new()
	_portrait_frame.name = "SpeakerPortrait"
	_portrait_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_portrait_frame.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var frame := StyleBoxFlat.new()
	frame.bg_color = Color("10171d")
	frame.border_color = GOLD.darkened(0.38)
	frame.set_border_width_all(2)
	frame.set_content_margin_all(5)
	_portrait_frame.add_theme_stylebox_override("panel", frame)
	_row.add_child(_portrait_frame)
	_portrait_image = TextureRect.new()
	_portrait_image.name = "NativeHeadshot"
	_portrait_image.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_portrait_image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait_image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_portrait_frame.add_child(_portrait_image)
	var gilding := Control.new()
	gilding.name = "PortraitGilding"
	gilding.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_portrait_frame.add_child(gilding)
	gilding.draw.connect(func() -> void: Art.frame(gilding, GOLD, false))
	gilding.resized.connect(gilding.queue_redraw)
	var column := VBoxContainer.new()
	column.name = "SpokenLine"
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	column.add_theme_constant_override("separation", 5)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_row.add_child(column)
	speaker_label = Label.new()
	speaker_label.name = "SpeakerName"
	speaker_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	speaker_label.add_theme_font_override("font", Art.title_font())
	speaker_label.add_theme_color_override("font_color", GOLD)
	speaker_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.95))
	speaker_label.add_theme_constant_override("shadow_offset_y", 2)
	speaker_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	column.add_child(speaker_label)
	body_label = Label.new()
	body_label.name = "DialogueText"
	body_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body_label.add_theme_color_override("font_color", TEXT)
	body_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.95))
	body_label.add_theme_constant_override("shadow_offset_y", 2)
	body_label.add_theme_constant_override("outline_size", 2)
	body_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.65))
	column.add_child(body_label)
	_viewport = SubViewport.new()
	_viewport.name = "SpeakerHeadCamera"
	_viewport.own_world_3d = false
	_viewport.size = Vector2i(256, 256)
	_viewport.transparent_bg = true
	_viewport.msaa_3d = Viewport.MSAA_2X
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_viewport)
	_camera = Camera3D.new()
	_camera.name = "PortraitCamera"
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.near = 0.02
	_camera.far = 2.2
	_camera.cull_mask = PORTRAIT_LAYER_MASK
	# This camera-local environment lights the real face during night scenes
	# without changing the world's environment, lights or actor materials.
	_camera.environment = Environment.new()
	_camera.environment.background_mode = Environment.BG_COLOR
	_camera.environment.background_color = Color(0, 0, 0, 0)
	_camera.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_camera.environment.ambient_light_color = Color("e5e4e0")
	_camera.environment.ambient_light_energy = 0.9
	_viewport.add_child(_camera)
	_portrait_image.texture = _viewport.get_texture()
	resized.connect(func() -> void: fit_width(size.x))
	fit_width(1280)
	reset()

func set_line(speaker: String, text: String, actor: Node3D = null) -> void:
	var bound := actor if is_instance_valid(actor) and not speaker.is_empty() else null
	var previous := _actor.get_ref() as Node3D if _actor != null else null
	var same_actor := (_actor == null and bound == null) or (is_instance_valid(previous) and previous == bound)
	if visible and speaker_label.text == speaker and body_label.text == text and same_actor:
		return
	speaker_label.text = speaker
	speaker_label.visible = not speaker.is_empty()
	body_label.text = text
	_actor = weakref(bound) if bound != null else null
	_elapsed = PORTRAIT_INTERVAL
	show()
	set_process(_actor != null)
	_update_portrait()

func reset() -> void:
	_actor = null
	speaker_label.text = ""
	body_label.text = ""
	speaker_label.hide()
	_portrait_frame.hide()
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	_viewport.world_3d = null
	set_process(false)
	hide()

func subtitle_text() -> String:
	return body_label.text if speaker_label.text.is_empty() else speaker_label.text + ": " + body_label.text

func portrait_visible() -> bool:
	return _portrait_frame.visible

func fit_width(width: float) -> void:
	if width <= 0 or is_equal_approx(width, _layout_width):
		return
	_layout_width = width
	var compact := width < 900
	var narrow := width < 600
	var side := 64 if narrow else 78 if compact else 104
	_portrait_frame.custom_minimum_size = Vector2(side, side)
	_row.add_theme_constant_override("separation", 10 if compact else 18)
	speaker_label.add_theme_font_size_override("font_size", 17 if narrow else 19 if compact else 24)
	body_label.add_theme_font_size_override("font_size", 15 if narrow else 17 if compact else 20)
	custom_minimum_size = Vector2(0, 78 if compact else 112)

func _process(delta: float) -> void:
	if not is_visible_in_tree():
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
		return
	_elapsed += delta
	if _elapsed >= PORTRAIT_INTERVAL:
		_elapsed = 0.0
		_update_portrait()

func _update_portrait() -> void:
	var actor := _actor.get_ref() as Node3D if _actor != null else null
	if not is_instance_valid(actor) or not actor.is_inside_tree() or not actor.has_method("get_skeleton"):
		_portrait_frame.hide()
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
		return
	var skeleton := actor.call("get_skeleton") as Skeleton3D
	var head_bone := skeleton.find_bone("Head") if is_instance_valid(skeleton) else -1
	if head_bone < 0:
		_portrait_frame.hide()
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
		return
	_viewport.world_3d = actor.get_world_3d()
	var head: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(head_bone).origin
	var height := maxf(0.5, head.y - actor.global_position.y)
	var focus := head + Vector3.UP * height * 0.025
	var forward := -actor.global_basis.z.normalized()
	var side := actor.global_basis.x.normalized()
	_camera.size = height * 0.37
	_camera.global_position = focus + forward * 0.9 - side * 0.07 + Vector3.UP * 0.025
	_camera.look_at(focus)
	_camera.current = true
	_portrait_frame.show()
	_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE

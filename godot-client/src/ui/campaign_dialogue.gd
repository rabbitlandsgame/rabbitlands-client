extends PanelContainer
## A portrait observes the supplied, authoritative actor; it never poses,
## clones, recolours or moves that actor or its animation clock.
const Art := preload("res://src/ui/leaderboard_art.gd")
const GOLD := Color("f1cd78")
const TEXT := Color("fffaf0")
const PORTRAIT_LAYER_MASK := 1 # Native models; excludes gameplay/map overlays.
const PORTRAIT_INTERVAL := 1.0 / 30.0
# Measured rest-space head envelopes of these existing imported rigs. Their
# bone names are not the humanoid "Head" convention; no actor pose is changed.
const CREATURE_HEAD_PROFILES := {
	"res://assets/actors/native/creatures/mire_goblin.glb": {
		"bone": "head", "bounds": AABB(Vector3(-0.69, 1.12, 0.10), Vector3(1.51, 0.60, 0.64))},
	"res://assets/actors/native/creatures/drowned_lich_king.glb": {
		"bone": "Bone_021", "bounds": AABB(Vector3(-0.15, 1.29, 0.10), Vector3(0.30, 0.41, 0.33))},
}

var speaker_label: Label
var body_label: Label
var content_slot: ScrollContainer
var _content_body: VBoxContainer
var _content_hint: Label
var _custom_content: WeakRef
var _content_height := 170.0
var _content_revision := 0
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
	_content_hint = Label.new()
	_content_hint.name = "ContentScrollHint"
	_content_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_content_hint.add_theme_color_override("font_color", Color("d2c4a8"))
	_content_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_content_hint.hide()
	column.add_child(_content_hint)
	content_slot = ScrollContainer.new()
	content_slot.name = "DialogueContentSlot"
	content_slot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_slot.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	content_slot.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	content_slot.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	content_slot.follow_focus = true
	content_slot.custom_minimum_size.y = _content_height
	column.add_child(content_slot)
	_content_body = VBoxContainer.new()
	_content_body.name = "DialogueContent"
	_content_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_slot.add_child(_content_body)
	content_slot.resized.connect(_schedule_content_hint)
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
	if visible and not content_slot.visible and speaker_label.text == speaker and body_label.text == text and same_actor:
		return
	_hide_content()
	speaker_label.text = speaker
	speaker_label.visible = not speaker.is_empty()
	body_label.text = text
	body_label.show()
	_actor = weakref(bound) if bound != null else null
	_elapsed = PORTRAIT_INTERVAL
	show()
	set_process(_actor != null)
	_update_portrait()

func set_content(speaker: String, content: Control, actor: Node3D = null) -> void:
	if not is_instance_valid(content) or content == self or content.is_ancestor_of(self):
		set_line(speaker, "", actor)
		return
	var current := _custom_content.get_ref() as Control if _custom_content != null else null
	var previous := _actor.get_ref() as Node3D if _actor != null else null
	var bound := actor if is_instance_valid(actor) and not speaker.is_empty() else null
	var same_actor := (_actor == null and bound == null) or (is_instance_valid(previous) and previous == bound)
	if visible and content_slot.visible and content.visible and current == content and speaker_label.text == speaker and same_actor:
		return
	_hide_content()
	if content.get_parent() != _content_body:
		if content.get_parent() != null:
			content.reparent(_content_body, false)
		else:
			_content_body.add_child(content)
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if not content.minimum_size_changed.is_connected(_schedule_content_hint):
		content.minimum_size_changed.connect(_schedule_content_hint)
	_custom_content = weakref(content)
	speaker_label.text = speaker
	speaker_label.visible = not speaker.is_empty()
	body_label.text = ""
	body_label.hide()
	_actor = weakref(bound) if bound != null else null
	_elapsed = PORTRAIT_INTERVAL
	content_slot.show()
	content.show()
	show()
	set_process(_actor != null)
	_update_portrait()
	_schedule_content_hint()

func fit_content_height(height: float) -> void:
	var bounded := maxf(56.0, height)
	if is_equal_approx(_content_height, bounded):
		return
	_content_height = bounded
	content_slot.custom_minimum_size.y = bounded
	_schedule_content_hint()

func content_active() -> bool:
	return content_slot.visible and _custom_content != null and is_instance_valid(_custom_content.get_ref())

func _hide_content() -> void:
	var content := _custom_content.get_ref() as Control if _custom_content != null else null
	if is_instance_valid(content):
		content.hide()
	_custom_content = null
	_content_hint.hide()
	content_slot.hide()
	_content_revision += 1

func _schedule_content_hint() -> void:
	_content_revision += 1
	if is_inside_tree():
		_update_content_hint.call_deferred(_content_revision)

func _update_content_hint(revision: int) -> void:
	await get_tree().process_frame
	if revision != _content_revision or not content_active():
		return
	var content := _custom_content.get_ref() as Control
	var bar := content_slot.get_v_scroll_bar()
	var overflow := bar.max_value > bar.page + 1.0
	_content_hint.text = str(content.get_meta(&"dialogue_scroll_hint", "Scroll to read more."))
	_content_hint.visible = overflow
	var focused := get_viewport().gui_get_focus_owner()
	if is_instance_valid(focused) and content.is_ancestor_of(focused):
		content_slot.ensure_control_visible(focused)

func reset() -> void:
	_hide_content()
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
	if speaker_label.text.is_empty():
		return body_label.text
	return speaker_label.text if body_label.text.is_empty() else speaker_label.text + ": " + body_label.text

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
	_content_hint.add_theme_font_size_override("font_size", 12 if narrow else 13)
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
	var creature_profile := _creature_head_profile(actor, skeleton) if head_bone < 0 else {}
	if not creature_profile.is_empty():
		head_bone = skeleton.find_bone(str(creature_profile.bone))
	if head_bone < 0:
		_portrait_frame.hide()
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
		return
	_viewport.world_3d = actor.get_world_3d()
	if not creature_profile.is_empty():
		_frame_creature_head(actor, skeleton, head_bone, creature_profile.bounds)
		_camera.current = true
		_portrait_frame.show()
		_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
		return
	var head: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(head_bone).origin
	var rest_head := skeleton.global_transform * skeleton.get_bone_global_rest(head_bone).origin
	var height := maxf(0.5, (rest_head - actor.global_position).dot(actor.global_basis.y.normalized()))
	var turn := _head_turn(skeleton, head_bone)
	var forward := (turn * -actor.global_basis.z).normalized()
	var side := (turn * actor.global_basis.x).normalized()
	var up := (turn * actor.global_basis.y).normalized()
	var focus := head + up * height * 0.025
	_camera.size = height * 0.37
	_camera.far = 2.2
	_camera.global_position = focus + forward * 0.9 - side * 0.07 + up * 0.025
	_camera.look_at(focus, up)
	_camera.current = true
	_portrait_frame.show()
	_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE

func _creature_head_profile(actor: Node3D, skeleton: Skeleton3D) -> Dictionary:
	if not is_instance_valid(skeleton) or not actor is ReplicatedActor3D:
		return {}
	var model: Dictionary = actor.get("_model_config")
	var profile: Dictionary = CREATURE_HEAD_PROFILES.get(str(model.get("scene", "")), {})
	if profile.is_empty() or skeleton.find_bone(str(profile.bone)) < 0:
		return {}
	return profile

func _frame_creature_head(actor: Node3D, skeleton: Skeleton3D, bone: int, bounds: AABB) -> void:
	var rest := skeleton.get_bone_global_rest(bone)
	var pose := skeleton.get_bone_global_pose(bone)
	var head_delta := pose * rest.affine_inverse()
	var focus := skeleton.global_transform * (head_delta * bounds.get_center())
	# A fallen goblin still speaks from its actual fallen head. Follow the
	# head's rest-to-pose rotation, including roll, rather than actor foot yaw.
	var turn := _head_turn(skeleton, bone)
	var forward := (turn * -actor.global_basis.z).normalized()
	var side := (turn * actor.global_basis.x).normalized()
	var up := (turn * actor.global_basis.y).normalized()
	var scale := skeleton.global_basis.get_scale().abs()
	var envelope := bounds.size * scale
	_camera.size = maxf(envelope.x, maxf(envelope.y, envelope.z)) * 1.12
	var distance := maxf(0.9, _camera.size * 1.6)
	_camera.far = maxf(2.2, distance + _camera.size * 1.5)
	_camera.global_position = focus + forward * distance - side * _camera.size * 0.04
	_camera.look_at(focus, up)

func _head_turn(skeleton: Skeleton3D, bone: int) -> Basis:
	var skeleton_basis := skeleton.global_basis.orthonormalized()
	return skeleton_basis * skeleton.get_bone_global_pose(bone).basis.orthonormalized() \
		* skeleton.get_bone_global_rest(bone).basis.orthonormalized().inverse() * skeleton_basis.inverse()

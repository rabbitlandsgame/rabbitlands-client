extends TextureRect
## A transparent, native-resolution text pass over the finished world, below
## the HUD and windows. Existing Label3D transforms and visibility remain the
## source of truth; only their rendering is separated from fog, glow and grade.

const LabelStyle := preload("res://src/ui/world_label_style.gd")
var source: Viewport
var text_viewport: SubViewport
var text_camera: Camera3D

func configure(world_viewport: Viewport) -> void:
	source = world_viewport
	name = "WorldTextOverlay"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	text_viewport = SubViewport.new()
	text_viewport.name = "TextViewport"
	text_viewport.transparent_bg = true
	text_viewport.handle_input_locally = false
	text_viewport.world_3d = source.find_world_3d()
	add_child(text_viewport)
	text_camera = Camera3D.new()
	text_camera.name = "TextCamera"
	text_camera.cull_mask = LabelStyle.RENDER_LAYER
	# Camera-local environment: the shared world's daylight and grading are
	# unchanged, and unlit text is composited with its authored colors.
	text_camera.environment = Environment.new()
	text_camera.environment.background_mode = Environment.BG_COLOR
	text_camera.environment.background_color = Color(0, 0, 0, 0)
	text_viewport.add_child(text_camera)
	text_camera.current = true
	texture = text_viewport.get_texture()
	RenderingServer.frame_pre_draw.connect(_sync_camera)
	_sync_camera()

func _exit_tree() -> void:
	if RenderingServer.frame_pre_draw.is_connected(_sync_camera):
		RenderingServer.frame_pre_draw.disconnect(_sync_camera)

func _sync_camera() -> void:
	var camera := source.get_camera_3d() if is_instance_valid(source) else null
	var active := is_visible_in_tree() and camera != null
	text_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS if active \
		else SubViewport.UPDATE_DISABLED
	if not active:
		return
	text_viewport.size = source.size
	text_camera.global_transform = camera.global_transform
	text_camera.projection = camera.projection
	text_camera.keep_aspect = camera.keep_aspect
	text_camera.fov = camera.fov
	text_camera.size = camera.size
	text_camera.frustum_offset = camera.frustum_offset
	text_camera.h_offset = camera.h_offset
	text_camera.v_offset = camera.v_offset
	text_camera.near = camera.near
	text_camera.far = camera.far

extends RefCounted
## Draw representative views behind the arrival curtain. Compatibility compiles
## some shader variants only when their geometry is first visible; doing this
## during the first player-controlled orbit can stall an otherwise fast frame.
## A separate camera leaves the player's rig and saved framing untouched. Render
## at a small resolution without a frame cap, then restore the original viewport,
## frame cap and VSync. Two draws per view retain the tested first-use coverage.

const FRAMES_PER_VIEW := 2
const LIMIT_MSEC := 20000
const PITCHES := [-60.0, -15.0]
const YAW_STEP := 3

var _source: Camera3D
var _camera: Camera3D
var _root: WeakRef
var _completed: Dictionary = {}
var _focus := Vector3.ZERO
var _distance := 1.0
var _yaw := 0.0
var _view := 0
var _last_draw := 0
var _started := 0
var _elapsed := 0
var _timed_out := false
var _viewport: SubViewport
var _source_viewport: SubViewport
var _source_update_mode := -1
var _saved_fps := -1
var _saved_vsync := -1
var _window_id := 0
var _frames_per_view := FRAMES_PER_VIEW
var _mode := "screen"
var _uncapped := false
var _max_draw_calls := 0
var _render_size := Vector2i.ZERO

func active() -> bool:
	return is_instance_valid(_camera)

func render_camera() -> Camera3D:
	return _camera if active() else null

func snapshot() -> Dictionary:
	return {"active": active(), "view": _view, "views": PITCHES.size() * (360 / YAW_STEP),
		"elapsed_msec": Time.get_ticks_msec() - _started if active() else _elapsed, "timed_out": _timed_out,
		"mode": _mode, "uncapped": _uncapped, "frames_per_view": _frames_per_view,
		"max_draw_calls": _max_draw_calls, "render_size": str(_render_size)}

func completed(world: Node3D, focus: Vector3) -> bool:
	if not is_instance_valid(world):
		return false
	var entry: Dictionary = _completed.get(world.get_instance_id(), {})
	return not entry.is_empty() and (entry.root as WeakRef).get_ref() == world \
		and (entry.focus as Vector3).distance_squared_to(focus) < 256.0

func begin(world: Node3D, source: Camera3D, focus: Vector3) -> bool:
	if active() or completed(world, focus) or not is_instance_valid(world) \
			or not is_instance_valid(source) or not source.is_inside_tree() \
			or source.get_viewport().get_camera_3d() != source:
		return false
	for identity: int in _completed.keys():
		if (_completed[identity].root as WeakRef).get_ref() == null:
			_completed.erase(identity)
	_source = source
	_root = weakref(world)
	_focus = focus
	_distance = maxf(1.0, source.global_position.distance_to(focus))
	_yaw = rad_to_deg(source.global_rotation.y)
	_view = 0
	_last_draw = Engine.get_frames_drawn()
	_started = Time.get_ticks_msec()
	_elapsed = 0
	_timed_out = false
	_max_draw_calls = 0
	_render_size = Vector2i(source.get_viewport().get_visible_rect().size)
	# One draw is a diagnostic comparison only: it reintroduced shallow-angle
	# hitches in qualification. Production keeps the two-draw safety margin.
	_frames_per_view = 1 if OS.get_environment("ELORIA_CAMERA_WARMUP_FRAMES") == "1" else FRAMES_PER_VIEW
	_uncapped = OS.get_environment("ELORIA_CAMERA_WARMUP_UNCAP") != "0"
	_mode = "small" if OS.get_environment("ELORIA_CAMERA_WARMUP_VIEWPORT") != "screen" \
		and source.get_viewport() is SubViewport else "screen"
	if _uncapped:
		_saved_fps = Engine.max_fps
		Engine.max_fps = 0
		if DisplayServer.get_name() != "headless":
			_window_id = source.get_window().get_window_id()
			_saved_vsync = DisplayServer.window_get_vsync_mode(_window_id)
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED, _window_id)
	_camera = Camera3D.new()
	_camera.name = "ArrivalShaderWarmupCamera"
	for property: String in ["projection", "fov", "size", "near", "far", "keep_aspect",
			"frustum_offset", "h_offset", "v_offset", "cull_mask", "environment", "attributes"]:
		_camera.set(property, source.get(property))
	if _mode == "small":
		var original := source.get_viewport() as SubViewport
		_source_viewport = original
		_viewport = SubViewport.new()
		_viewport.name = "ArrivalShaderWarmupViewport"
		_viewport.world_3d = source.get_world_3d()
		var scale := minf(1.0, 192.0 / float(maxi(original.size.x, original.size.y)))
		_viewport.size = Vector2i(maxi(2, roundi(original.size.x * scale)), maxi(2, roundi(original.size.y * scale)))
		_render_size = _viewport.size
		for property: String in ["msaa_3d", "screen_space_aa", "transparent_bg", "scaling_3d_mode",
				"scaling_3d_scale", "positional_shadow_atlas_size", "positional_shadow_atlas_16_bits"]:
			_viewport.set(property, original.get(property))
		# Retain full mesh formats instead of allowing the small viewport to pick
		# a cheaper geometry LOD which could hide a needed rendering variant.
		_viewport.mesh_lod_threshold = 0.0
		_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		source.get_tree().root.add_child(_viewport)
		_viewport.add_child(_camera)
		_source_update_mode = original.render_target_update_mode
		original.render_target_update_mode = SubViewport.UPDATE_DISABLED
	else:
		source.get_parent().add_child(_camera)
	_camera.top_level = true
	_show_view()
	_camera.make_current()
	return true

## Called once per gameplay process pass while the loading curtain is opaque.
## Count actual draws, so a skipped rendering frame never qualifies a view.
func advance(draw_count := Engine.get_frames_drawn()) -> void:
	if not active():
		return
	if not is_instance_valid(_source) or not _source.is_inside_tree() \
			or _root.get_ref() == null or _camera.get_viewport().get_camera_3d() != _camera \
			or (_mode == "small" and _source.get_viewport().get_camera_3d() != _source):
		cancel()
		return
	if Time.get_ticks_msec() - _started > LIMIT_MSEC:
		_timed_out = true
		_finish()
		return
	if draw_count - _last_draw < _frames_per_view:
		return
	if is_instance_valid(_viewport):
		_max_draw_calls = maxi(_max_draw_calls, _viewport.get_render_info(
			Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME))
	_last_draw = draw_count
	_view += 1
	if _view >= PITCHES.size() * (360 / YAW_STEP):
		_finish()
	else:
		_show_view()

func _show_view() -> void:
	var views_per_pitch := 360 / YAW_STEP
	var pitch := deg_to_rad(PITCHES[_view / views_per_pitch])
	var yaw := deg_to_rad(_yaw + float((_view % views_per_pitch) * YAW_STEP))
	var offset := Vector3(sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch)) * _distance
	_camera.look_at_from_position(_focus + offset, _focus + Vector3.UP * 1.2, Vector3.UP)

func _finish() -> void:
	var world: Object = _root.get_ref()
	if is_instance_valid(world):
		_completed[world.get_instance_id()] = {"root": weakref(world), "focus": _focus}
	cancel()

func cancel() -> void:
	if _saved_fps >= 0:
		Engine.max_fps = _saved_fps
	_saved_fps = -1
	if _saved_vsync >= 0:
		DisplayServer.window_set_vsync_mode(_saved_vsync, _window_id)
	_saved_vsync = -1
	if _source_update_mode >= 0 and is_instance_valid(_source_viewport):
		_source_viewport.render_target_update_mode = _source_update_mode
	_source_update_mode = -1
	_source_viewport = null
	if is_instance_valid(_camera):
		_elapsed = Time.get_ticks_msec() - _started
		if _mode == "screen" and _camera.is_inside_tree() and _camera.current \
				and is_instance_valid(_source) and _source.is_inside_tree():
			_source.make_current()
		_camera.queue_free()
	if is_instance_valid(_viewport):
		_viewport.queue_free()
	_viewport = null
	_camera = null
	_source = null
	_root = null

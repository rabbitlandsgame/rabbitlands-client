extends RefCounted
## Draw representative views behind the arrival curtain. Compatibility compiles
## some shader variants only when their geometry is first visible; doing this
## during the first player-controlled orbit can stall an otherwise fast frame.
## A separate camera leaves the player's rig and saved framing untouched. Render
## at a small resolution without a frame cap, then restore the original viewport,
## frame cap and VSync. Two draws per view retain the tested first-use coverage.
##
## A world keeps, for the session, the content its completed sweeps drew: keys
## naming what decides a shader variant (shader or material, vertex format,
## skinning or instancing, shadow casting, lights, environment), counted only
## where every sweep camera was inside its visibility range. A parked world
## keeps its record while parked. An arrival whose content adds no key - a
## door back out to a parked map, a respawn into scenery already drawn - has
## nothing new to compile, so it draws a short sweep (REUSE_YAW_STEP) that
## still exercises the occluder fades around its new focus. Any new key draws
## the full sweep. ELORIA_CAMERA_WARMUP_REUSE=0 always draws the full sweep.

const FRAMES_PER_VIEW := 2
const LIMIT_MSEC := 20000
const WEB_LIMIT_MSEC := 30000
const PITCHES := [-60.0, -15.0]
const YAW_STEP := 3
## Degrees between views when the arrival's content is already covered: a
## quarter of the full sweep's views.
const REUSE_YAW_STEP := 12
const REUSE_VARIABLE := "ELORIA_CAMERA_WARMUP_REUSE"

## Warm-up cameras drawing now, by warm-up: the sun's shadow fit leaves the
## scene's shadow distance in place for them (sun_shadow_fit.gd).
static var _drawing: Dictionary = {}

var _source: Camera3D
var _camera: Camera3D
var _root: WeakRef
var _completed: Dictionary = {}
## World instance id -> {"root": WeakRef, "keys": {key: true}}: the content
## every completed full sweep of that world drew.
var _coverage: Dictionary = {}
## The keys this sweep is sure to draw, credited to its world on completion.
var _credit: Dictionary = {}
var _yaw_step := YAW_STEP
var _reused := false
var _content_keys := 0
var _new_keys := 0
var _scan_usec := 0
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

## Whether any warm-up camera is drawing.
static func drawing() -> bool:
	for id: int in _drawing.keys():
		if (_drawing[id] as WeakRef).get_ref() == null:
			_drawing.erase(id)
	return not _drawing.is_empty()

func views() -> int:
	return PITCHES.size() * (360 / _yaw_step)

func snapshot() -> Dictionary:
	return {"active": active(), "view": _view, "views": views(),
		"elapsed_msec": Time.get_ticks_msec() - _started if active() else _elapsed, "timed_out": _timed_out,
		"mode": _mode, "uncapped": _uncapped, "frames_per_view": _frames_per_view,
		"max_draw_calls": _max_draw_calls, "render_size": str(_render_size),
		"reused": _reused, "content_keys": _content_keys, "new_keys": _new_keys,
		"scan_msec": _scan_usec / 1000.0}

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
	for identity: int in _coverage.keys():
		if (_coverage[identity].root as WeakRef).get_ref() == null:
			_coverage.erase(identity)
	_source = source
	_root = weakref(world)
	_focus = focus
	_distance = maxf(1.0, source.global_position.distance_to(focus))
	_yaw = rad_to_deg(source.global_rotation.y)
	_choose_sweep(world, source)
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
		# Browser presentation stays on requestAnimationFrame; changing window
		# VSync is unsupported there. Keep the native warmup policy unchanged.
		if DisplayServer.get_name() != "headless" and not OS.has_feature("web"):
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
	_drawing[get_instance_id()] = weakref(_camera)
	return true

## Full sweep, or the short one when every key of the content this sweep could
## draw is already in the world's record.
func _choose_sweep(world: Node3D, source: Camera3D) -> void:
	var started := Time.get_ticks_usec()
	var content := _content(world, source)
	var record: Dictionary = _coverage.get(world.get_instance_id(), {}) as Dictionary
	var covered: Dictionary = record.get("keys", {}) as Dictionary
	_content_keys = content[0].size()
	_new_keys = 0
	for key: String in content[0]:
		if not covered.has(key):
			_new_keys += 1
	_reused = _new_keys == 0 and not covered.is_empty() \
		and OS.get_environment(REUSE_VARIABLE) != "0"
	_yaw_step = REUSE_YAW_STEP if _reused else YAW_STEP
	_credit = {} if _reused else content[1]
	_scan_usec = Time.get_ticks_usec() - started

## What a sweep around `_focus` draws, as two key sets: what it could draw and
## what it is sure to draw. Geometry is read from the world root (the map, not
## its actors, whose materials are their own copies); lights and environment
## from the camera's whole world, since they decide variants of what they
## light. A node counts only where it is visible and on the camera's layers,
## and against its visibility range from the nearest and furthest sweep
## camera, each `_distance` from the focus.
func _content(world: Node3D, source: Camera3D) -> Array[Dictionary]:
	var possible := {}
	var certain := {}
	var materials := {}
	for node: Node in world.find_children("*", "GeometryInstance3D", true, false):
		var geometry := node as GeometryInstance3D
		if (geometry.layers & source.cull_mask) == 0 or not geometry.is_visible_in_tree():
			continue
		var span := (geometry.global_transform * geometry.get_aabb().get_center()).distance_to(_focus)
		var nearest := span - _distance
		var furthest := span + _distance
		var from := geometry.visibility_range_begin
		var to := geometry.visibility_range_end
		var from_margin := absf(geometry.visibility_range_begin_margin)
		var to_margin := absf(geometry.visibility_range_end_margin)
		if nearest > source.far or (to > 0.0 and nearest > to + to_margin) \
				or (from > 0.0 and furthest < from - from_margin):
			continue
		var sure := furthest <= source.far and (to <= 0.0 or furthest <= to - to_margin) \
			and (from <= 0.0 or nearest >= from + from_margin)
		for key: String in _geometry_keys(geometry, materials):
			possible[key] = true
			if sure:
				certain[key] = true
	var context: Array[String] = [_environment_key(source)]
	for node: Node in source.get_viewport().find_children("*", "Light3D", true, false):
		var light := node as Light3D
		if light.is_visible_in_tree():
			context.append(_light_key(light))
	for key: String in context:
		possible[key] = true
		certain[key] = true
	var sets: Array[Dictionary] = [possible, certain]
	return sets

static func _geometry_keys(geometry: GeometryInstance3D, materials: Dictionary) -> Array[String]:
	var keys: Array[String] = []
	var tail := "|%s|%d" % [_material_key(geometry.material_overlay, materials),
		int(geometry.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)]
	var mesh: Mesh
	var kind := "mesh"
	var instance := geometry as MeshInstance3D
	if instance != null:
		mesh = instance.mesh
		if instance.skin != null or instance.get_node_or_null(instance.skeleton) is Skeleton3D:
			kind = "skinned"
	elif geometry is MultiMeshInstance3D:
		var multimesh := (geometry as MultiMeshInstance3D).multimesh
		if multimesh != null:
			mesh = multimesh.mesh
			kind = "multimesh|%d|%d|%d" % [multimesh.transform_format,
				int(multimesh.use_colors), int(multimesh.use_custom_data)]
	else:
		# Particles, sprites, labels and the rest build their own materials:
		# the node itself is the key, which holds while the world is parked.
		keys.append("%s#%d%s" % [geometry.get_class(), geometry.get_instance_id(), tail])
		return keys
	if mesh == null:
		return keys
	var array_mesh := mesh as ArrayMesh
	for surface: int in mesh.get_surface_count():
		var material: Material = instance.get_active_material(surface) if instance != null \
			else (geometry.material_override if geometry.material_override != null
				else mesh.surface_get_material(surface))
		var format := "%d/%d" % [array_mesh.surface_get_format(surface),
			array_mesh.get_blend_shape_count()] if array_mesh != null else mesh.get_class()
		keys.append("%s|%s|%s%s" % [kind, format, _material_key(material, materials), tail])
	return keys

## A ShaderMaterial is its shader: the same code compiles the same variants
## whatever its parameters. Any other material is itself.
static func _material_key(material: Material, materials: Dictionary) -> String:
	if material == null:
		return "-"
	var id := material.get_instance_id()
	var key: String = materials.get(id, "")
	if not key.is_empty():
		return key
	var shader_material := material as ShaderMaterial
	if shader_material != null:
		key = "shader:%d" % (shader_material.shader.get_instance_id()
			if shader_material.shader != null else 0)
	else:
		key = "material:%d" % id
	materials[id] = key
	if material.next_pass != null and material.next_pass != material:
		key += ">" + _material_key(material.next_pass, materials)
		materials[id] = key
	return key

static func _light_key(light: Light3D) -> String:
	var key := "light|%s|%d|%d" % [light.get_class(), int(light.shadow_enabled),
		light.light_cull_mask]
	var sun := light as DirectionalLight3D
	if sun != null:
		return key + "|%d|%d" % [sun.directional_shadow_mode, int(sun.directional_shadow_blend_splits)]
	return key + "|%s|%s|%s" % [light.global_position.snapped(Vector3.ONE),
		snappedf(light.get_param(Light3D.PARAM_RANGE), 0.5),
		snappedf(light.get_param(Light3D.PARAM_SPOT_ANGLE), 0.5)]

static func _environment_key(source: Camera3D) -> String:
	var key := "environment|%s|%d" % [RenderingServer.get_current_rendering_method(),
		LookProfile.quality()]
	var world := source.get_world_3d()
	var environment: Environment = source.environment if source.environment != null \
		else (world.environment if world != null else null)
	if environment == null:
		return key
	key += "|%d|%d|%d|%d|%d|%d" % [environment.background_mode, environment.ambient_light_source,
		environment.reflected_light_source, int(environment.fog_enabled),
		int(environment.glow_enabled), environment.tonemap_mode]
	# Every bind builds a new sky material. A built-in sky draws one shader per
	# class and debanding/filter choice, so those name it rather than the copy.
	var sky: Material = environment.sky.sky_material if environment.sky != null else null
	if sky is ShaderMaterial:
		key += "|sky:" + _material_key(sky, {})
	elif sky != null:
		key += "|sky:%s|%s|%s" % [sky.get_class(), sky.get(&"use_debanding"), sky.get(&"filter")]
	return key

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
	var limit := WEB_LIMIT_MSEC if OS.has_feature("web") else LIMIT_MSEC
	if Time.get_ticks_msec() - _started > limit:
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
	if _view >= views():
		_finish()
	else:
		_show_view()

func _show_view() -> void:
	var views_per_pitch := 360 / _yaw_step
	var pitch := deg_to_rad(PITCHES[_view / views_per_pitch])
	var yaw := deg_to_rad(_yaw + float((_view % views_per_pitch) * _yaw_step))
	var offset := Vector3(sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch)) * _distance
	_camera.look_at_from_position(_focus + offset, _focus + Vector3.UP * 1.2, Vector3.UP)

func _finish() -> void:
	var world: Object = _root.get_ref()
	if is_instance_valid(world):
		var identity := world.get_instance_id()
		_completed[identity] = {"root": weakref(world), "focus": _focus}
		# Only a sweep that drew every view vouches for its content.
		if not _timed_out and not _credit.is_empty():
			var record: Dictionary = _coverage.get(identity, {}) as Dictionary
			if record.is_empty():
				record = {"root": weakref(world), "keys": {}}
				_coverage[identity] = record
			(record["keys"] as Dictionary).merge(_credit)
	cancel()

func cancel() -> void:
	_drawing.erase(get_instance_id())
	_credit = {}
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

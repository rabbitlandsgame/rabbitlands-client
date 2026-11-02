extends Node
## Fits the sun's shadow distance to the ground the camera can see.
##
## Nothing set the sun's `directional_shadow_max_distance`, so Godot fitted
## the cascades to its 100 m default from the camera. From the default framing
## (pitch -60, 26 m out) the ground at the top of the frame is about 37 m deep:
## the outer cascade - the only visible one on LOW and MEDIUM, and the unseen
## 50-100 m one on HIGH - rendered casters over ground nobody could see, at a
## resolution the visible ground could have had instead.
##
## This measures how deep the visible ground goes and brings the distance in
## to it, with margin, never past what the scene set (its own value, adopted
## whenever something else writes one). The measure is the walk surface under
## rays spread down the frame. Flat ground is deepest at the top edge, but view
## depth counts height too: from -60 degrees, ground dropping away mid-frame -
## a gorge, a valley floor, the land below a cliff - can lie deeper than the
## ground at the top edge behind it, so rows an eighth of the frame apart
## sample it, close enough that a rim missed between two rows stays within
## the margin. A ray that meets no walk surface - sky, open water, ground not
## loaded yet - keeps the scene's distance, and so does a warm-up camera
## (camera_shader_warmup.gd), which must see what the scene's distance shows.
##
## The cascade boundaries stay where Godot put them for the scene's distance,
## so no seam moves on screen. A boundary the shorter distance no longer
## reaches moves in front of the nearest visible ground, where it only splits
## the air below the camera; that nearest ground is held while it stays near,
## since a boundary moving each refit would make the cascade behind it swim.
## Every cascade that holds visible ground ends no further out than before,
## so shadows stay where they were and get sharper. The fade moves into the
## margin past the visible ground. The atlas, filter and number of cascades
## stay the graphics quality's (LookSwitch.apply_shadow_quality).
## ELORIA_SHADOW_FIT=0 turns this off.

const Warmup := preload("res://src/world/camera_shader_warmup.gd")
const NODE_NAME := "SunShadowFit"
const DISABLE_VARIABLE := "ELORIA_SHADOW_FIT"
## WorldLoader.NAVIGATION_SURFACE_LAYER and
## ExteriorRegionStream.PREVIEW_SURFACE_LAYER: the ground, not what stands on it.
const GROUND_MASK := 8 | 16
## Rays along the top edge, along the bottom edge, and along the ROWS - 2 rows
## between, spaced an eighth of the frame apart. Those rows alternate between
## three columns (both edges and the middle) and the two quarters between.
const TOP_SAMPLES := 7
const BOTTOM_SAMPLES := 3
const ROWS := 9
## The nearest visible ground is taken anew only once it comes nearer than
## this fraction of the held value, or goes further than its inverse.
const NEAREST_HOLD := 0.8
## The visible depth grows by this fraction plus these metres before the fit:
## ground between the sampled rays, and a frame's camera movement.
const DEPTH_MARGIN := 0.1
const DEPTH_MARGIN_METRES := 2.0
## Fraction of the fitted distance where shadows start to fade. The fade lies
## wholly past the visible ground, so it can be short.
const FITTED_FADE_START := 0.95
const MIN_DISTANCE := 8.0
const STEP_METRES := 2.0
## A shorter distance is taken only once it is this much shorter, so walking
## over uneven ground does not keep resizing the cascades.
const SHRINK_RATIO := 0.9
## Refit when the camera moves or turns this much, and at least this often.
const REFIT_METRES := 1.0
const REFIT_DOT := 0.9998
const REFIT_FRAMES := 15
const PROPERTIES: Array[StringName] = [&"directional_shadow_max_distance",
	&"directional_shadow_split_1", &"directional_shadow_split_2",
	&"directional_shadow_split_3", &"directional_shadow_fade_start"]

var _sun: DirectionalLight3D
## The scene's own values, by property, and the values last written here.
var _authored: Dictionary = {}
var _written: Dictionary = {}
## The fitted distance in use; 0 while the scene's values are.
var _distance := 0.0
## The nearest visible ground the moved boundaries stay in front of; 0 while
## the scene's values are.
var _nearest := 0.0
var _frame := -REFIT_FRAMES
var _origin := Vector3.INF
var _forward := Vector3.ZERO
var _lens: Array = []
var _query := PhysicsRayQueryParameters3D.new()

func _init() -> void:
	name = NODE_NAME
	_query.collision_mask = GROUND_MASK

func _enter_tree() -> void:
	_sun = get_parent() as DirectionalLight3D
	if _sun != null and not RenderingServer.frame_pre_draw.is_connected(_fit):
		RenderingServer.frame_pre_draw.connect(_fit)

func _exit_tree() -> void:
	if RenderingServer.frame_pre_draw.is_connected(_fit):
		RenderingServer.frame_pre_draw.disconnect(_fit)
	if is_instance_valid(_sun):
		_adopt()
		_restore()
	_sun = null

## The fitted distance in use, or 0 while the scene's own values are.
func fitted_distance() -> float:
	return _distance

## Runs just before every draw, after the frame's scripts have moved the
## camera, so the cascades drawn are fitted to the frame being drawn.
func _fit() -> void:
	if not is_instance_valid(_sun) or not _sun.is_inside_tree():
		return
	_adopt()
	if not _sun.shadow_enabled or not _sun.is_visible_in_tree():
		return
	var camera := _sun.get_viewport().get_camera_3d()
	if camera == null or camera.projection != Camera3D.PROJECTION_PERSPECTIVE \
			or Warmup.drawing():
		_restore()
		_frame = -REFIT_FRAMES
		return
	var forward := -camera.global_basis.z
	var lens: Array = [camera.fov, camera.near, camera.far, camera.keep_aspect,
		camera.get_viewport().get_visible_rect().size, _sun.directional_shadow_mode]
	var frame := Engine.get_frames_drawn()
	if frame - _frame < REFIT_FRAMES and lens == _lens \
			and camera.global_position.distance_squared_to(_origin) < REFIT_METRES * REFIT_METRES \
			and forward.dot(_forward) > REFIT_DOT:
		return
	_frame = frame
	_origin = camera.global_position
	_forward = forward
	_lens = lens
	var ceiling := minf(float(_authored[&"directional_shadow_max_distance"]), camera.far)
	var depths := visible_depths(camera, ceiling)
	if not is_finite(depths.y):
		_restore()
		return
	var reach := depths.y * (1.0 + DEPTH_MARGIN) + DEPTH_MARGIN_METRES
	var target := clampf(ceilf(reach / FITTED_FADE_START / STEP_METRES) * STEP_METRES,
		MIN_DISTANCE, ceiling)
	if target >= ceiling:
		_restore()
		return
	if _distance <= 0.0 or target > _distance or target < _distance * SHRINK_RATIO:
		_distance = target
	_nearest = held_nearest(_nearest, depths.x)
	var ratios := split_ratios(camera.near, ceiling, _distance, _nearest,
		_cascades(), [_authored[&"directional_shadow_split_1"],
			_authored[&"directional_shadow_split_2"], _authored[&"directional_shadow_split_3"]])
	_write(&"directional_shadow_max_distance", _distance)
	_write(&"directional_shadow_split_1", ratios[0])
	_write(&"directional_shadow_split_2", ratios[1])
	_write(&"directional_shadow_split_3", ratios[2])
	_write(&"directional_shadow_fade_start", FITTED_FADE_START)

## The view depth of the nearest (x) and of the deepest (y) ground the rays
## down the frame meet, each along the camera's view. y is INF when a ray
## meets no ground within `ceiling`.
func visible_depths(camera: Camera3D, ceiling: float) -> Vector2:
	var size := camera.get_viewport().get_visible_rect().size
	var space := camera.get_world_3d().direct_space_state
	var deepest := 0.0
	var nearest := INF
	for point: Vector2 in sample_points(size):
		var depth := _depth(camera, space, point, ceiling)
		if not is_finite(depth):
			return Vector2(0.0, INF)
		deepest = maxf(deepest, depth)
		nearest = minf(nearest, depth)
	return Vector2(nearest, deepest)

## The nearest ground to place moved boundaries by: `held` while `measured`
## stays within NEAREST_HOLD of it, else `measured`. Never more than
## `measured` / NEAREST_HOLD, so split_ratios' 0.8 keeps every moved boundary
## in front of the ground the frame shows.
static func held_nearest(held: float, measured: float) -> float:
	if held <= 0.0 or measured < held * NEAREST_HOLD or measured * NEAREST_HOLD > held:
		return measured
	return held

## Where in a frame of `size` the rays are cast, top row first.
static func sample_points(size: Vector2) -> PackedVector2Array:
	var points := PackedVector2Array()
	for index: int in TOP_SAMPLES:
		points.append(Vector2(size.x * index / float(TOP_SAMPLES - 1), 0.0))
	for row: int in range(1, ROWS - 1):
		var v := size.y * row / float(ROWS - 1)
		var staggered := row % 2 == 0
		for index: int in (2 if staggered else 3):
			points.append(Vector2(size.x * (index + (0.5 if staggered else 0.0)) / 2.0, v))
	for index: int in BOTTOM_SAMPLES:
		points.append(Vector2(size.x * index / float(BOTTOM_SAMPLES - 1), size.y))
	return points

func _depth(camera: Camera3D, space: PhysicsDirectSpaceState3D, point: Vector2,
		ceiling: float) -> float:
	var forward := -camera.global_basis.z
	var direction := camera.project_ray_normal(point)
	var along := direction.dot(forward)
	if along <= 0.05:
		return INF
	_query.from = camera.project_ray_origin(point)
	_query.to = _query.from + direction * (ceiling / along)
	var hit := space.intersect_ray(_query)
	if hit.is_empty():
		return INF
	return ((hit.position as Vector3) - camera.global_position).dot(forward)

## Split ratios for a fitted `distance`. Godot places boundary i at
## near + ratio_i * (distance - near). Boundaries the scene's own values put
## short of `distance` keep their place; the rest move geometrically between
## the near plane and the nearer of the first kept boundary and the nearest
## visible ground, so they split only the air below the camera. Ratios a
## cascade count does not use keep the scene's values.
static func split_ratios(near: float, ceiling: float, distance: float, nearest: float,
		cascades: int, authored: Array) -> Array[float]:
	var ratios: Array[float] = [float(authored[0]), float(authored[1]), float(authored[2])]
	var kept: Array[float] = []
	for index: int in cascades - 1:
		var boundary := near + float(authored[index]) * (ceiling - near)
		if boundary < distance:
			kept.append(boundary)
	var moved := cascades - 1 - kept.size()
	var first := kept[0] if not kept.is_empty() else distance
	var below := minf(first, nearest * 0.8)
	if below <= near * 1.5:
		below = first
	var boundaries: Array[float] = []
	for index: int in moved:
		boundaries.append(near * pow(below / near, float(index + 1) / float(moved + 1)))
	boundaries.append_array(kept)
	for index: int in boundaries.size():
		ratios[index] = clampf((boundaries[index] - near) / (distance - near), 0.0, 1.0)
	return ratios

func _cascades() -> int:
	match _sun.directional_shadow_mode:
		DirectionalLight3D.SHADOW_ORTHOGONAL:
			return 1
		DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS:
			return 2
	return 4

## Takes as the scene's own any value that something else wrote since this
## last wrote it (a map's or a tool's shadow distance).
func _adopt() -> void:
	for property: StringName in PROPERTIES:
		var value := float(_sun.get(property))
		if not _written.has(property) or not is_equal_approx(value, float(_written[property])):
			_authored[property] = value
			_written[property] = value
			if property == &"directional_shadow_max_distance":
				_distance = 0.0

func _restore() -> void:
	_distance = 0.0
	_nearest = 0.0
	for property: StringName in PROPERTIES:
		if _authored.has(property):
			_write(property, float(_authored[property]))

func _write(property: StringName, value: float) -> void:
	if not is_equal_approx(float(_sun.get(property)), value):
		_sun.set(property, value)
	_written[property] = float(_sun.get(property))

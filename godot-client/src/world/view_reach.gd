extends RefCounted
## How far the play camera draws (wave 2 WD-C4; the world-distance plan,
## section 3.5): its far plane fitted to the camera, the fog that hides where
## it cuts, and the ground sampler the sun's shadow fit shares.
##
## The far plane. The scene's camera draws to 1800 m. Nothing streams in
## beyond the 320 m retain distance, but that distance is measured to a
## chunk's or a region's bounds, so resident ground runs on well past it (a
## whole neighbouring region stays resident once its edge is near), and a low
## view (the rig tilts up to -15 degrees) fills the frame with it to the
## horizon. On LOW the camera draws to its orbit distance, rounded up to
## BUCKET_METRES so a zoom does not move it every frame, plus FAR_REACH:
## 232 m at the default 26 m, 296 m fully zoomed out, so about 200 m of
## ground beyond the player at every zoom. MEDIUM and HIGH keep the scene's
## far plane and their fog untouched (FAR_REACH 0): they have no fog at a cut,
## and the plan's 300 and 400 m would clip the resident ground described above.
##
## The fog at the cut. While the far plane is fitted the fog closes in so that
## it is whole FOG_CUT_METRES before the cut (Godot's depth fog grows with the
## distance from the camera, and every point of the far plane lies at least
## that far):
## - a depth fog (the painted sky's haze, the grade's fog, a fog bank) ends
##   there unless it already ends nearer, begins no further out than
##   FOG_BEGIN_SHARE of the far plane, and is opaque (FOG_DENSITY) at its end;
## - a map's exponential fog (the Original and Painted ground appearances)
##   becomes that depth fog, from FOG_BEGIN on FOG_CURVE (the painted haze's),
##   in the colour the map and the hour give it.
## The fog's colour, its share of the sky and its aerial perspective stay the
## binders'. The fit is made just before each draw over whatever the binders,
## the grade, the sky, the weather and main's border blend last wrote (they
## rewrite the fog ten times a second on the continent): a value someone else
## wrote is taken as the new base, as the shadow fit does with the sun, so
## the base comes back whole when the fit stops (a quality change, a map
## without fog, a campaign's own far plane).
##
## Only where fog can hide the cut: an outdoor map (WorldEnvironmentBinder
## marks its environment OUTDOOR_META: a declared sun, and a sky the look may
## paint, so not the dark-void "insides" maps) whose fog is on. An interior,
## a map without fog in the Original and Painted ground appearances, and the
## mine's dark sections keep the scene's far plane.
##
## The far plane is the rig's only while it holds the scene's own or a value
## the rig wrote: a campaign pose or an adopted world view that sets another
## far plane keeps it, and the rig takes the far plane back once it is
## returned. Any value the rig wrote counts, not only the last: a campaign
## saves the far plane as it begins, poses with it and puts it back as it
## ends, and a zoom or a quality switch during the scene changes the rig's own
## meanwhile; were only the last write the rig's, the restored one would be
## kept for the rest of the session (on HIGH, a 232 m cut with no fog over it).
## While someone else's far plane nearer than the scene's is in force on LOW
## (a campaign's blend between two of the rig's), the fog is fitted to it.
##
## The ground fit (an A/B, ELORIA_VIEW_REACH=ground): the rays below also fit
## what is drawn to the ground the frame shows. When every ray meets ground
## nearer than the far plane, the renderer draws only to the deepest of it
## plus GROUND_MARGIN and GROUND_MARGIN_METRES, so the far side of a hill or a
## valley behind a ridge is not drawn. It narrows only the renderer's camera
## for the frame (camera_set_perspective just before the draw), so a warm-up
## camera, a campaign pose and the shadow fit still read the far plane, not
## the fit. It is not the default: the rays are an eighth of the frame apart
## and ground seen through a narrower gap (a saddle at the top edge, a
## cenote) more than the margin deeper would be cut where no fog covers it,
## and LOW casts no rays otherwise (its sun casts no shadows).
##
## The ground sampler (wave 1's, moved here from sun_shadow_fit.gd, which now
## calls it): rays spread down the frame meet the walk surface; the view depth
## of the nearest and deepest ground they meet bounds what the frame shows.
## Within one frame, one camera pose and lens, a cast serves every later
## request with the same or a nearer ceiling (shared_depths), so the shadow
## fit and the ground fit never cast the same rays twice.
##
## ELORIA_VIEW_REACH=off, or ELORIA_WORLD_DISTANCE=off, leaves the far plane
## and the fog to the scene. Main thread only (the sampler's query and cache
## are shared).
##
## No class_name: callers preload this file.

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const Warmup := preload("res://src/world/camera_shader_warmup.gd")

const VARIABLE := "ELORIA_VIEW_REACH"
## "auto": the far plane and its fog on LOW; "ground": and the ground fit;
## "off": neither. Unset (or on) is "auto".
const MODES: Array[String] = ["auto", "ground", "off"]
## Set (true) by WorldEnvironmentBinder on the environment of an outdoor map.
const OUTDOOR_META := &"rl_view_reach_outdoor"

## The orbit distance is rounded up to this before the reach is added.
const BUCKET_METRES := 8.0
## Metres of reach past the bucket, by LookProfile.Quality (LOW, MEDIUM,
## HIGH); 0 keeps the scene's far plane.
const FAR_REACH: Array[float] = [200.0, 0.0, 0.0]
## The fog is whole this far in front of the far plane.
const FOG_CUT_METRES := 10.0
## The fog begins no further out than this share of the far plane.
const FOG_BEGIN_SHARE := 0.4
## The fog's density at its end while the far plane is fitted.
const FOG_DENSITY := 1.0
## Where an exponential fog's replacement begins, and its curve.
const FOG_BEGIN := LookProfile.HAZE_BEGIN
const FOG_CURVE := LookProfile.HAZE_CURVE
## The fog's shape, which the fit sets; nothing else of the fog is touched.
const FOG_PROPERTIES: Array[StringName] = [&"fog_mode", &"fog_depth_begin",
	&"fog_depth_end", &"fog_depth_curve", &"fog_density"]

## WorldLoader.NAVIGATION_SURFACE_LAYER and
## ExteriorRegionStream.PREVIEW_SURFACE_LAYER: the ground, not what stands on it.
const GROUND_MASK := 8 | 16
## Rays along the top edge, along the bottom edge, and along the ROWS - 2 rows
## between, spaced an eighth of the frame apart. Those rows alternate between
## three columns (both edges and the middle) and the two quarters between.
const TOP_SAMPLES := 7
const BOTTOM_SAMPLES := 3
const ROWS := 9
## Measure again when the camera moves or turns this much, and at least this
## often (frames).
const REFIT_METRES := 1.0
const REFIT_DOT := 0.9998
const REFIT_FRAMES := 15
## The ground fit: the deepest ground grows by this fraction plus these
## metres, rounded up to GROUND_STEP_METRES, never under GROUND_FAR_MIN; a
## nearer fit is taken only once it is this much nearer.
const GROUND_MARGIN := 0.25
const GROUND_MARGIN_METRES := 16.0
const GROUND_STEP_METRES := 8.0
const GROUND_FAR_MIN := 32.0
const GROUND_SHRINK_RATIO := 0.9

## Sets of rays cast since the client started (tests and diagnostics).
static var ray_sets := 0
static var _query: PhysicsRayQueryParameters3D
## The last shared cast: the camera, frame, pose and lens it was cast for, its
## ceiling, whether every ray met ground, and the depths it met.
static var _shared_key: Array = []
static var _shared_ceiling := 0.0
static var _shared_complete := false
static var _shared_depths := PackedFloat64Array()

# --- Policy --------------------------------------------------------------------

## The mode this launch asks for (VARIABLE; off with ELORIA_WORLD_DISTANCE=off).
static func mode_from_environment() -> String:
	if not HardwareTier.world_distance_enabled():
		return "off"
	return str(HardwareTier.resolve_switch(OS.get_environment(VARIABLE), MODES, "off").mode)

## The orbit distance rounded up to BUCKET_METRES.
static func bucket(distance: float) -> float:
	return ceilf(maxf(distance, 0.0) / BUCKET_METRES) * BUCKET_METRES

## FAR_REACH for a LookProfile.Quality.
static func reach(quality: int) -> float:
	return FAR_REACH[clampi(quality, 0, FAR_REACH.size() - 1)]

## The far plane for an orbit `distance` at `quality`: `scene_far` where the
## quality keeps it, else the bucket plus the reach, never past `scene_far`.
static func camera_far(distance: float, quality: int, scene_far: float) -> float:
	var metres := reach(quality)
	if metres <= 0.0:
		return scene_far
	return minf(scene_far, bucket(distance) + metres)

## True where a fog can hide the cut: an outdoor map's environment with fog on.
static func horizon_fog(environment: Environment) -> bool:
	return environment != null and environment.fog_enabled \
		and bool(environment.get_meta(OUTDOOR_META, false))

## The fog shape (FOG_PROPERTIES) that is whole FOG_CUT_METRES before a far
## plane `far`, from a `base` shape (the same keys, as the binders left it).
static func fitted_fog(base: Dictionary, far: float) -> Dictionary:
	var depth := int(base.get(&"fog_mode", Environment.FOG_MODE_EXPONENTIAL)) \
		== Environment.FOG_MODE_DEPTH
	var end := far - FOG_CUT_METRES
	var begin := FOG_BEGIN
	var curve := FOG_CURVE
	var density := FOG_DENSITY
	if depth:
		end = minf(end, float(base.get(&"fog_depth_end", end)))
		begin = float(base.get(&"fog_depth_begin", FOG_BEGIN))
		curve = float(base.get(&"fog_depth_curve", FOG_CURVE))
		density = maxf(FOG_DENSITY, float(base.get(&"fog_density", 0.0)))
	end = maxf(end, 1.0)
	begin = clampf(minf(begin, far * FOG_BEGIN_SHARE), 0.0, end - 1.0)
	return {&"fog_mode": Environment.FOG_MODE_DEPTH, &"fog_depth_begin": begin,
		&"fog_depth_end": end, &"fog_depth_curve": curve, &"fog_density": density}

## What the ground fit draws to for ground `deepest` m deep under a far plane
## `far`: never past it.
static func ground_far(deepest: float, far: float) -> float:
	var reach_metres := deepest * (1.0 + GROUND_MARGIN) + GROUND_MARGIN_METRES
	return clampf(ceilf(reach_metres / GROUND_STEP_METRES) * GROUND_STEP_METRES,
		minf(GROUND_FAR_MIN, far), far)

# --- Ground sampler ------------------------------------------------------------

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

## The view depth of the walk surface under `point`, or INF where the ray
## meets none within `ceiling` (sky, open water, ground not loaded yet).
static func ray_depth(camera: Camera3D, space: PhysicsDirectSpaceState3D, point: Vector2,
		ceiling: float) -> float:
	var forward := -camera.global_basis.z
	var direction := camera.project_ray_normal(point)
	var along := direction.dot(forward)
	if along <= 0.05:
		return INF
	var query := _ray_query()
	query.from = camera.project_ray_origin(point)
	query.to = query.from + direction * (ceiling / along)
	var hit := space.intersect_ray(query)
	if hit.is_empty():
		return INF
	return ((hit.position as Vector3) - camera.global_position).dot(forward)

## The view depth of the nearest (x) and of the deepest (y) ground the rays
## down the frame meet, each along the camera's view. y is INF when a ray
## meets no ground within `ceiling`. Always casts.
static func visible_depths(camera: Camera3D, ceiling: float) -> Vector2:
	var measured := _cast(camera, ceiling)
	return _reduce(bool(measured[0]), measured[1] as PackedFloat64Array, ceiling, false)

## visible_depths, served from this frame's cast for the same camera, pose and
## lens when that cast reached at least `ceiling`; otherwise cast (and kept).
## A hit within the nearer ceiling is the same hit; a ray that met nothing
## within the further one meets nothing within the nearer one.
static func shared_depths(camera: Camera3D, ceiling: float) -> Vector2:
	var key := _cast_key(camera)
	if key == _shared_key and ceiling <= _shared_ceiling:
		return _reduce(_shared_complete, _shared_depths, ceiling, ceiling < _shared_ceiling)
	var measured := _cast(camera, ceiling)
	_shared_key = key
	_shared_ceiling = ceiling
	_shared_complete = bool(measured[0])
	_shared_depths = measured[1] as PackedFloat64Array
	return _reduce(_shared_complete, _shared_depths, ceiling, false)

## Forgets the shared cast (tests).
static func forget_shared() -> void:
	_shared_key = []
	_shared_depths = PackedFloat64Array()

## [every ray met ground, depths met] down the frame, stopping at the first
## ray that meets none: one such ray already decides the answer.
static func _cast(camera: Camera3D, ceiling: float) -> Array:
	ray_sets += 1
	var size := camera.get_viewport().get_visible_rect().size
	var space := camera.get_world_3d().direct_space_state
	var depths := PackedFloat64Array()
	for point: Vector2 in sample_points(size):
		var depth := ray_depth(camera, space, point, ceiling)
		if not is_finite(depth):
			return [false, depths]
		depths.append(depth)
	return [true, depths]

static func _reduce(complete: bool, depths: PackedFloat64Array, ceiling: float,
		nearer: bool) -> Vector2:
	if not complete:
		return Vector2(0.0, INF)
	var deepest := 0.0
	var nearest := INF
	for depth: float in depths:
		if nearer and depth > ceiling:
			return Vector2(0.0, INF)
		deepest = maxf(deepest, depth)
		nearest = minf(nearest, depth)
	return Vector2(nearest, deepest)

static func _cast_key(camera: Camera3D) -> Array:
	return [camera.get_instance_id(), Engine.get_process_frames(), Engine.get_frames_drawn(),
		camera.global_transform,
		camera.fov, camera.near, camera.keep_aspect,
		camera.get_viewport().get_visible_rect().size]

static func _ray_query() -> PhysicsRayQueryParameters3D:
	if _query == null:
		_query = PhysicsRayQueryParameters3D.new()
		_query.collision_mask = GROUND_MASK
	return _query

# --- The play camera's fit -------------------------------------------------------

## The camera this fits (the rig's).
var camera: Camera3D
## MODES entry in use (mode_from_environment when made).
var mode := "auto"
## The scene's own far plane, given back whenever the fit stops.
var _far_scene := 0.0
## Every far plane this has written (as read back), as keys: one of them, or
## the scene's, in force is still this fit's (_owns_far).
var _far_values: Dictionary = {}
## The far plane fitted now; 0 while the scene's (or someone else's) is.
var _horizon := 0.0
## What the ground fit sent the renderer; 0 when it sent nothing.
var _drawn := 0.0
## The ground fit held between measures; 0 for none.
var _ground := 0.0
var _frame := -REFIT_FRAMES
var _origin := Vector3.INF
var _forward := Vector3.ZERO
var _lens: Array = []
## The environment whose fog this fitted, its base shape and what this wrote.
var _fog_environment: WeakRef
var _fog_base: Dictionary = {}
var _fog_written: Dictionary = {}
## The far plane the fog was last fitted to.
var _fog_far := 0.0

func _init(target: Camera3D = null) -> void:
	camera = target
	mode = mode_from_environment()
	if camera != null:
		_far_scene = camera.far

## Fits the far plane, its fog and (mode "ground") what is drawn, for the
## rig's orbit `distance` at LookProfile.Quality `quality`. Call once a frame,
## just before the draw (the rig does, from RenderingServer.frame_pre_draw).
func fit(distance: float, quality: int) -> void:
	if not is_instance_valid(camera) or not camera.is_inside_tree():
		return
	var wanted := mode != "off" and reach(quality) > 0.0 \
		and camera.projection == Camera3D.PROJECTION_PERSPECTIVE
	if not wanted and _fog_written.is_empty() and _drawn <= 0.0 and not _far_fitted():
		return
	var environment := _environment()
	var target := 0.0
	if wanted and horizon_fog(environment):
		target = camera_far(distance, quality, _far_scene)
	_horizon = _hold_far(target)
	var fog_far := _horizon
	if fog_far <= 0.0 and target > 0.0 and camera.far < _far_scene \
			and camera.far >= reach(quality):
		# Someone else's far plane, nearer than the scene's but no nearer
		# than this fit's nearest, where this would fit one (a campaign's
		# blend between two of this fit's): its cut is fogged as this fit's.
		fog_far = camera.far
	_fit_fog(environment, fog_far)
	_fit_ground(_horizon if mode == "ground" else 0.0)

## Gives the scene its far plane and fog back (the rig leaving the tree).
func release() -> void:
	if not is_instance_valid(camera):
		return
	_fit_ground(0.0)
	if _owns_far() and not is_equal_approx(camera.far, _far_scene):
		camera.far = _far_scene
	_horizon = 0.0
	var environment: Environment = _fog_environment.get_ref() as Environment \
		if _fog_environment != null else null
	if environment != null:
		_restore_fog(environment)
	_fog_environment = null

## The far plane fitted now (0 while the scene's is in force).
func horizon_far() -> float:
	return _horizon

## What the renderer draws to: the ground fit, else the far plane in force.
func drawn_far() -> float:
	if _drawn > 0.0:
		return _drawn
	return camera.far if is_instance_valid(camera) else 0.0

## For camera diagnostics and the benchmark probes.
func state() -> Dictionary:
	return {"mode": mode, "scene_far": _far_scene, "far": camera.far if is_instance_valid(camera) else 0.0,
		"horizon_far": _horizon, "drawn_far": drawn_far(), "ground_far": _drawn,
		"fog_fitted": not _fog_written.is_empty()}

func _environment() -> Environment:
	if camera.environment != null:
		return camera.environment
	var world := camera.get_world_3d()
	return world.environment if world != null else null

## True while the far plane in force is this fit's to change: the scene's own
## or one this wrote (see the header). Anything else someone else set.
func _owns_far() -> bool:
	var far := camera.far
	if is_equal_approx(far, _far_scene) or _far_values.has(far):
		return true
	for value: float in _far_values:
		if is_equal_approx(far, value):
			return true
	return false

## True while a far plane this wrote holds in place of the scene's.
func _far_fitted() -> bool:
	return not _far_values.is_empty() and is_instance_valid(camera) \
		and not is_equal_approx(camera.far, _far_scene) and _owns_far()

## Writes `target` (or, for 0, the scene's far plane back) while the far plane
## is this fit's; returns the far plane this holds, 0 for none.
func _hold_far(target: float) -> float:
	if not _owns_far():
		return 0.0
	if target > 0.0:
		if not is_equal_approx(camera.far, target):
			camera.far = target
		_far_values[camera.far] = true
		return camera.far
	if not is_equal_approx(camera.far, _far_scene):
		camera.far = _far_scene
	return 0.0

func _fit_fog(environment: Environment, far: float) -> void:
	var fitted: Environment = _fog_environment.get_ref() as Environment \
		if _fog_environment != null else null
	if fitted != environment:
		if fitted != null:
			_restore_fog(fitted)
		_fog_environment = weakref(environment) if environment != null else null
		_fog_base = {}
		_fog_written = {}
	if environment == null:
		return
	if far <= 0.0:
		_restore_fog(environment)
		return
	if far == _fog_far and _fog_written.size() == FOG_PROPERTIES.size() \
			and _fog_unchanged(environment):
		return
	_fog_far = far
	_adopt_fog(environment)
	var target := fitted_fog(_fog_base, far)
	for property: StringName in FOG_PROPERTIES:
		var value: Variant = target[property]
		if not _same(environment.get(property), value):
			environment.set(property, value)
		_fog_written[property] = environment.get(property)

## True while every fog value is still the one this wrote (the frames between
## the writers' rewrites cost five reads).
func _fog_unchanged(environment: Environment) -> bool:
	for property: StringName in FOG_PROPERTIES:
		if not _same(environment.get(property), _fog_written[property]):
			return false
	return true

## Takes as the base any fog value someone else wrote since this last wrote it.
func _adopt_fog(environment: Environment) -> void:
	for property: StringName in FOG_PROPERTIES:
		var value: Variant = environment.get(property)
		if not _fog_written.has(property) or not _same(value, _fog_written[property]):
			_fog_base[property] = value
			_fog_written.erase(property)

func _restore_fog(environment: Environment) -> void:
	if _fog_written.is_empty():
		return
	_adopt_fog(environment)
	for property: StringName in _fog_written.keys():
		environment.set(property, _fog_base[property])
	_fog_written = {}

## The ground fit for a far plane `far` (0: none).
func _fit_ground(far: float) -> void:
	if far <= 0.0 or not camera.current or Warmup.drawing() \
			or camera.attributes is CameraAttributesPhysical:
		_ground = 0.0
		_frame = -REFIT_FRAMES
		_lens = []
		_draw_to(0.0)
		return
	var forward := -camera.global_basis.z
	var lens: Array = [camera.fov, camera.near, far, camera.keep_aspect,
		camera.get_viewport().get_visible_rect().size]
	var frame := Engine.get_frames_drawn()
	if frame - _frame >= REFIT_FRAMES or lens != _lens \
			or camera.global_position.distance_squared_to(_origin) >= REFIT_METRES * REFIT_METRES \
			or forward.dot(_forward) <= REFIT_DOT:
		_frame = frame
		_origin = camera.global_position
		_forward = forward
		_lens = lens
		var depths := shared_depths(camera, far)
		if not is_finite(depths.y):
			_ground = 0.0
		else:
			var target := ground_far(depths.y, far)
			if _ground <= 0.0 or target > _ground or target < _ground * GROUND_SHRINK_RATIO:
				_ground = target
	_draw_to(_ground if _ground > 0.0 and _ground < far else 0.0)

## Narrows the renderer's camera to `value` for this frame, or (0) gives it
## the node's own lens back. Camera3D re-sends its lens whenever a property is
## set (the rig sets `near` on every move), so this is sent before every draw.
func _draw_to(value: float) -> void:
	if value > 0.0:
		RenderingServer.camera_set_perspective(camera.get_camera_rid(), camera.fov,
			camera.near, value)
	elif _drawn > 0.0:
		RenderingServer.camera_set_perspective(camera.get_camera_rid(), camera.fov,
			camera.near, camera.far)
	_drawn = value

static func _same(a: Variant, b: Variant) -> bool:
	if a is float or b is float:
		return is_equal_approx(float(a), float(b))
	return a == b

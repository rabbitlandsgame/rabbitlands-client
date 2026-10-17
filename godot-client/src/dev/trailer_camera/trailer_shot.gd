extends RefCounted
## One trailer shot: the camera path a JSON shot file describes (see README.md
## beside this script for the format). Parsing, key resolution and the path
## maths only - nothing here touches the scene, so tests/test_trailer_shot.gd
## checks it headless. trailer_camera.gd loads the map, resolves the keys
## against it and flies a Camera3D along `evaluate`.
##
## The path is a cubic Hermite spline through the keys, timed in seconds: a
## key's tangent is the chord from the key before it to the key after it
## divided by the time between them, so a path whose keys are spaced evenly in
## time and distance keeps one speed through every key. A key's `ease` shapes
## the segment that starts at it ("in" leaves the key from rest, "out" arrives
## at the next key at rest, "in-out" does both); "linear" keeps the speed.

const SCHEMA := "rabbitlands-trailer-shot/1"
const EASES: Array[String] = ["linear", "in", "out", "in-out"]
const INTERPOLATIONS: Array[String] = ["spline", "linear"]
## A key with no lookAt and no yaw looks this far along the path.
const LOOK_AHEAD_METRES := 40.0
## Eye height for a key placed by `tile` with no `aboveGround`.
const DEFAULT_EYE_HEIGHT := 1.7

var source_path := ""
## The shot file as parsed, for options trailer_camera.gd reads itself.
var data: Dictionary = {}
var errors: PackedStringArray = []
var name := ""
var interpolation := "spline"
var duration := 0.0
## Normalised keys, in order: t (seconds), position and target (map metres),
## fov (vertical degrees), roll (degrees), ease, minute (game minute or NAN).
var keys: Array[Dictionary] = []

## Reads and parses a shot file. Returns false and fills `errors` when it
## cannot be used.
func load_file(path: String) -> bool:
	source_path = path
	if not FileAccess.file_exists(path):
		errors.append("shot file not found: " + path)
		return false
	return parse(FileAccess.get_file_as_string(path))

func parse(text: String) -> bool:
	errors.clear()
	keys.clear()
	var parsed: Variant = JSON.parse_string(text)
	if parsed is not Dictionary:
		errors.append("the shot file is not a JSON object")
		return false
	data = parsed as Dictionary
	if str(data.get("schema", SCHEMA)) != SCHEMA:
		errors.append("unknown schema %s (expected %s)" % [data.get("schema"), SCHEMA])
	name = str(data.get("name", source_path.get_file().get_basename()))
	interpolation = str(data.get("interpolation", "spline"))
	if not interpolation in INTERPOLATIONS:
		errors.append("interpolation must be one of %s" % [INTERPOLATIONS])
	if str(data.get("map", "")).is_empty():
		errors.append("the shot names no map")
	var raw_keys: Variant = data.get("keys", [])
	if raw_keys is not Array or (raw_keys as Array).size() < 2:
		errors.append("a shot needs at least two keys")
		return false
	var default_fov := float(data.get("fov", 50.0))
	var default_ease := str(data.get("ease", "linear"))
	var default_minute: float = float(data.get("gameMinute")) if data.get("gameMinute") is float else NAN
	for index: int in (raw_keys as Array).size():
		var raw: Variant = (raw_keys as Array)[index]
		if raw is not Dictionary:
			errors.append("key %d is not an object" % index)
			continue
		var key: Dictionary = raw as Dictionary
		var label := "key %d" % index
		var normal := {
			"t": float(key["t"]) if key.get("t") is float else NAN,
			"fov": float(key.get("fov", default_fov)),
			"roll": float(key.get("roll", 0.0)),
			"ease": str(key.get("ease", default_ease)),
			"minute": float(key["gameMinute"]) if key.get("gameMinute") is float else default_minute,
		}
		if not normal.ease in EASES:
			errors.append("%s: ease must be one of %s" % [label, EASES])
		if normal.fov <= 1.0 or normal.fov >= 179.0:
			errors.append("%s: fov %.1f is not a vertical angle in degrees" % [label, normal.fov])
		# Where the camera stands: map metres, or a server tile (what #loc and
		# the minimap print) placed at aboveGround over the ground there.
		if _is_vector(key.get("position"), 3):
			normal.position = _vector3(key.position)
		elif _is_vector(key.get("tile"), 2):
			normal.tile = Vector2(float(key.tile[0]), float(key.tile[1]))
			normal.position = Vector3.INF
		else:
			errors.append("%s: needs position [x, y, z] or tile [x, y]" % label)
			continue
		if key.has("aboveGround"):
			normal.above_ground = float(key.aboveGround)
		elif normal.has("tile"):
			normal.above_ground = DEFAULT_EYE_HEIGHT
		# What it looks at: a point, a tile, a compass heading, or along the path.
		if _is_vector(key.get("lookAt"), 3):
			normal.target = _vector3(key.lookAt)
		elif _is_vector(key.get("lookAtTile"), 2):
			normal.target_tile = Vector2(float(key.lookAtTile[0]), float(key.lookAtTile[1]))
			normal.target = Vector3.INF
		elif key.has("yaw"):
			normal.yaw = float(key.yaw)
			normal.pitch = float(key.get("pitch", 0.0))
		else:
			normal.along_path = true
			normal.pitch = float(key.get("pitch", 0.0))
		if key.has("lookAtAboveGround"):
			normal.target_above_ground = float(key.lookAtAboveGround)
		elif normal.has("target_tile"):
			normal.target_above_ground = DEFAULT_EYE_HEIGHT
		keys.append(normal)
	if keys.size() < 2:
		return false
	if is_nan(float(keys[0].t)):
		keys[0].t = 0.0
	if is_nan(float(keys[-1].t)):
		errors.append("the last key needs a time t")
	var last := -INF
	for index: int in keys.size():
		var t := float(keys[index].t)
		if is_nan(t):
			continue
		if t <= last:
			errors.append("key %d: t %.3f does not come after %.3f" % [index, t, last])
		last = t
	return errors.is_empty()

## Places every key that is not already in map metres. `tile_to_world` takes a
## Vector2 server tile and returns its centre in metres (a CoordinateAdapter's
## tile_center); `ground_at` takes a point and returns the ground height under
## it, or NAN where there is none. Either may be invalid when no key needs it.
## Then times the keys that have no t and builds the look targets.
func resolve(tile_to_world: Callable, ground_at: Callable) -> bool:
	for index: int in keys.size():
		var key := keys[index]
		if (key.has("tile") or key.has("target_tile")) and not tile_to_world.is_valid():
			errors.append("key %d: a tile needs the map's coordinate transform" % index)
			continue
		if key.has("tile"):
			key.position = tile_to_world.call(key.tile)
		if key.has("target_tile"):
			key.target = tile_to_world.call(key.target_tile)
		if key.has("above_ground"):
			key.position = _grounded(key.position, float(key.above_ground), ground_at,
				"key %d" % index)
		if key.has("target_above_ground") and key.has("target"):
			key.target = _grounded(key.target, float(key.target_above_ground), ground_at,
				"key %d lookAt" % index)
	if not errors.is_empty():
		return false
	_time_untimed_keys()
	for index: int in keys.size():
		var key := keys[index]
		if key.has("yaw"):
			key.target = key.position + direction(float(key.yaw), float(key.pitch)) * LOOK_AHEAD_METRES
		elif key.has("along_path"):
			var heading := _position_tangent(index)
			if heading.length_squared() < 1e-8:
				heading = Vector3.FORWARD
			heading = Vector3(heading.x, 0.0, heading.z).normalized() \
				if Vector2(heading.x, heading.z).length() > 1e-4 else Vector3.FORWARD
			var yaw := rad_to_deg(atan2(heading.x, -heading.z))
			key.target = key.position + direction(yaw, float(key.pitch)) * LOOK_AHEAD_METRES
	duration = float(keys[-1].t) - float(keys[0].t)
	return errors.is_empty()

## The camera at `time` seconds into the shot (clamped to the shot): position,
## target, fov, roll and the game minute (NAN when the shot leaves the hour to
## the map).
func evaluate(time: float) -> Dictionary:
	var t := clampf(time + float(keys[0].t), float(keys[0].t), float(keys[-1].t))
	var segment := 0
	while segment < keys.size() - 2 and t >= float(keys[segment + 1].t):
		segment += 1
	var a := keys[segment]
	var b := keys[segment + 1]
	var span := float(b.t) - float(a.t)
	var u := clampf((t - float(a.t)) / span, 0.0, 1.0) if span > 0.0 else 1.0
	var eased := ease_value(u, str(a.ease))
	var minute := NAN
	if not is_nan(float(a.minute)) and not is_nan(float(b.minute)):
		minute = lerpf(float(a.minute), float(b.minute), eased)
	elif not is_nan(float(a.minute)):
		minute = float(a.minute)
	return {
		"position": _interpolate("position", segment, eased),
		"target": _interpolate("target", segment, eased),
		"fov": lerpf(float(a.fov), float(b.fov), eased),
		"roll": lerpf(float(a.roll), float(b.roll), eased),
		"minute": minute,
	}

## Every point the camera stands at or looks at, `step` seconds apart: what
## trailer_camera.gd keeps resident for the whole shot.
func samples(step := 0.25) -> PackedVector3Array:
	var points := PackedVector3Array()
	var time := 0.0
	while true:
		var pose := evaluate(time)
		points.append(pose.position)
		points.append(pose.target)
		if time >= duration:
			break
		time = minf(time + step, duration)
	return points

static func ease_value(u: float, kind: String) -> float:
	match kind:
		"in":
			return u * u
		"out":
			return 1.0 - (1.0 - u) * (1.0 - u)
		"in-out":
			return u * u * (3.0 - 2.0 * u)
	return u

## A unit view direction from a compass heading (0 north, 90 east, map north
## is -Z) and a pitch above the horizon in degrees.
static func direction(yaw_degrees: float, pitch_degrees: float) -> Vector3:
	var yaw := deg_to_rad(yaw_degrees)
	var pitch := deg_to_rad(pitch_degrees)
	return Vector3(sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch))

func _interpolate(field: String, segment: int, u: float) -> Vector3:
	var a := keys[segment]
	var b := keys[segment + 1]
	var p0: Vector3 = a[field]
	var p1: Vector3 = b[field]
	if interpolation == "linear":
		return p0.lerp(p1, u)
	var span := float(b.t) - float(a.t)
	var m0 := _tangent(field, segment) * span
	var m1 := _tangent(field, segment + 1) * span
	var u2 := u * u
	var u3 := u2 * u
	return p0 * (2.0 * u3 - 3.0 * u2 + 1.0) + m0 * (u3 - 2.0 * u2 + u) \
		+ p1 * (-2.0 * u3 + 3.0 * u2) + m1 * (u3 - u2)

## Metres per second through key `index`: the chord between its neighbours
## over the time between them, one-sided at the ends.
func _tangent(field: String, index: int) -> Vector3:
	var before := maxi(index - 1, 0)
	var after := mini(index + 1, keys.size() - 1)
	var span := float(keys[after].t) - float(keys[before].t)
	if span <= 0.0:
		return Vector3.ZERO
	return ((keys[after][field] as Vector3) - (keys[before][field] as Vector3)) / span

func _position_tangent(index: int) -> Vector3:
	var before := maxi(index - 1, 0)
	var after := mini(index + 1, keys.size() - 1)
	return (keys[after].position as Vector3) - (keys[before].position as Vector3)

## Keys without a t share the time between the timed keys either side of them
## in proportion to the distance travelled, so the camera keeps one speed.
func _time_untimed_keys() -> void:
	var start := 0
	while start < keys.size() - 1:
		var finish := start + 1
		while finish < keys.size() and is_nan(float(keys[finish].t)):
			finish += 1
		if finish >= keys.size():
			return
		if finish > start + 1:
			var lengths: Array[float] = [0.0]
			for index: int in range(start + 1, finish + 1):
				lengths.append(lengths[-1] + (keys[index].position as Vector3).distance_to(
					keys[index - 1].position as Vector3))
			var total: float = lengths[-1]
			var t0 := float(keys[start].t)
			var t1 := float(keys[finish].t)
			for index: int in range(start + 1, finish):
				var share: float = lengths[index - start] / total if total > 0.0 \
					else float(index - start) / float(finish - start)
				keys[index].t = lerpf(t0, t1, share)
		start = finish

func _grounded(point: Vector3, above: float, ground_at: Callable, label: String) -> Vector3:
	if not ground_at.is_valid():
		errors.append(label + ": aboveGround needs the map's ground")
		return point
	var ground: float = ground_at.call(point)
	if is_nan(ground):
		errors.append("%s: no ground under (%.1f, %.1f)" % [label, point.x, point.z])
		return point
	return Vector3(point.x, ground + above, point.z)

static func _is_vector(value: Variant, size: int) -> bool:
	if value is not Array or (value as Array).size() != size:
		return false
	for item: Variant in value as Array:
		if item is not float and item is not int:
			return false
	return true

static func _vector3(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))

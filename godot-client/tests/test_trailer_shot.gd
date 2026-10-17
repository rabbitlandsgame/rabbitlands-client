extends SceneTree

## The trailer camera's shot files (src/dev/trailer_camera): parsing, key
## resolution and the camera path, without loading a map. The sample shots are
## parsed too, so a format change that breaks them fails here first.
##
## Run: Godot_v4.7.2-stable_win64.exe --headless --path . \
##         --script tests/test_trailer_shot.gd

const TrailerShot := preload("res://src/dev/trailer_camera/trailer_shot.gd")
const SHOTS := "res://src/dev/trailer_camera/shots/"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_rejects()
	_check_keys_are_hit()
	_check_speed_is_kept()
	_check_eases()
	_check_untimed_keys()
	_check_tiles_and_ground()
	_check_look_directions()
	_check_samples()
	_check_sample_shots()
	print("trailer shot: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _shot(keys: Array, extra := {}) -> TrailerShot:
	var document := {"schema": TrailerShot.SCHEMA, "map": "landfall", "keys": keys}
	document.merge(extra, true)
	var shot := TrailerShot.new()
	shot.parse(JSON.stringify(document))
	return shot

func _check_rejects() -> void:
	var one := _shot([{"t": 0, "position": [0, 0, 0]}])
	_expect(not one.errors.is_empty(), "a single key is refused")
	var backwards := _shot([{"t": 1, "position": [0, 0, 0], "lookAt": [0, 0, -1]},
		{"t": 0.5, "position": [1, 0, 0], "lookAt": [0, 0, -1]}])
	_expect(not backwards.errors.is_empty(), "keys out of time order are refused")
	var untimed_end := _shot([{"t": 0, "position": [0, 0, 0]}, {"position": [1, 0, 0]}])
	_expect(not untimed_end.errors.is_empty(), "the last key must carry a time")
	var bad_ease := _shot([{"t": 0, "position": [0, 0, 0], "ease": "bounce"},
		{"t": 1, "position": [1, 0, 0]}])
	_expect(not bad_ease.errors.is_empty(), "an unknown ease is refused")
	var no_map := TrailerShot.new()
	no_map.parse(JSON.stringify({"keys": [{"t": 0, "position": [0, 0, 0]}, {"t": 1, "position": [1, 0, 0]}]}))
	_expect(not no_map.errors.is_empty(), "a shot must name its map")
	var tile_without_map := _shot([{"t": 0, "tile": [10, 10]}, {"t": 1, "position": [1, 0, 0]}])
	_expect(tile_without_map.errors.is_empty() and not tile_without_map.resolve(Callable(), Callable()),
		"a tile key cannot resolve without the map's transform")

func _check_keys_are_hit() -> void:
	var shot := _shot([
		{"t": 0, "position": [0, 2, 0], "lookAt": [0, 2, -10], "fov": 60},
		{"t": 2, "position": [10, 4, -5], "lookAt": [10, 0, -20]},
		{"t": 5, "position": [12, 30, -40], "lookAt": [0, 0, -60], "fov": 40, "roll": 10}])
	_expect(shot.resolve(Callable(), Callable()), "plain keys resolve")
	_expect(is_equal_approx(shot.duration, 5.0), "duration runs from the first key to the last")
	for key: Dictionary in shot.keys:
		var pose := shot.evaluate(float(key.t))
		_expect((pose.position as Vector3).is_equal_approx(key.position),
			"the path passes through the key at t=%.1f" % float(key.t))
		_expect((pose.target as Vector3).is_equal_approx(key.target),
			"the camera looks at the key's target at t=%.1f" % float(key.t))
	_expect(is_equal_approx(float(shot.evaluate(-1.0).fov), 60.0), "time before the shot clamps to the first key")
	_expect(is_equal_approx(float(shot.evaluate(99.0).roll), 10.0), "time after the shot clamps to the last key")
	_expect(is_equal_approx(float(shot.evaluate(1.0).fov), 55.0), "the default fov (50) is eased towards from 60")

## Keys evenly spaced in time and distance along a line move at one speed.
func _check_speed_is_kept() -> void:
	var shot := _shot([
		{"t": 0, "position": [0, 0, 0], "lookAt": [0, 0, -100]},
		{"t": 1, "position": [10, 0, 0], "lookAt": [0, 0, -100]},
		{"t": 2, "position": [20, 0, 0], "lookAt": [0, 0, -100]},
		{"t": 3, "position": [30, 0, 0], "lookAt": [0, 0, -100]}])
	shot.resolve(Callable(), Callable())
	var steps: Array[float] = []
	for frame: int in range(0, 180):
		var a: Vector3 = shot.evaluate(frame / 60.0).position
		var b: Vector3 = shot.evaluate((frame + 1) / 60.0).position
		steps.append(a.distance_to(b))
	_expect(steps.max() - steps.min() < 1e-4, "an evenly keyed line keeps one speed (%.5f..%.5f m per frame)" % [
		steps.min(), steps.max()])

func _check_eases() -> void:
	_expect(is_equal_approx(TrailerShot.ease_value(0.5, "linear"), 0.5), "linear is the identity")
	_expect(TrailerShot.ease_value(0.25, "in") < 0.25, "in starts slow")
	_expect(TrailerShot.ease_value(0.25, "out") > 0.25, "out starts fast")
	_expect(is_equal_approx(TrailerShot.ease_value(0.5, "in-out"), 0.5), "in-out is symmetric")
	var shot := _shot([
		{"t": 0, "position": [0, 0, 0], "lookAt": [0, 0, -100], "ease": "in-out"},
		{"t": 2, "position": [20, 0, 0], "lookAt": [0, 0, -100]}])
	shot.resolve(Callable(), Callable())
	var start_step := (shot.evaluate(1.0 / 60.0).position as Vector3).length()
	var middle_step := (shot.evaluate(61.0 / 60.0).position as Vector3).distance_to(shot.evaluate(1.0).position)
	_expect(start_step < middle_step * 0.05, "an in-out segment leaves its key from rest")
	_expect((shot.evaluate(2.0 - 1.0 / 60.0).position as Vector3).distance_to(Vector3(20, 0, 0)) < middle_step * 0.05,
		"and arrives at the next at rest")

func _check_untimed_keys() -> void:
	var shot := _shot([
		{"t": 0, "position": [0, 0, 0], "lookAt": [0, 0, -100]},
		{"position": [10, 0, 0], "lookAt": [0, 0, -100]},
		{"position": [40, 0, 0], "lookAt": [0, 0, -100]},
		{"t": 5, "position": [50, 0, 0], "lookAt": [0, 0, -100]}])
	_expect(shot.resolve(Callable(), Callable()), "untimed keys resolve")
	_expect(is_equal_approx(float(shot.keys[1].t), 1.0) and is_equal_approx(float(shot.keys[2].t), 4.0),
		"untimed keys share the time by distance (%.2f, %.2f)" % [float(shot.keys[1].t), float(shot.keys[2].t)])

func _check_tiles_and_ground() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [100, 100],
		"origin": [0, 0, 0], "walkingHeight": 20.0, "invertServerY": true})
	var tile_to_world := func(tile: Vector2) -> Vector3: return adapter.tile_center(int(tile.x), int(tile.y))
	var ground_at := func(point: Vector3) -> float: return 5.0 if point.x < 50.0 else NAN
	var shot := _shot([
		{"t": 0, "tile": [110, 90], "lookAtTile": [110, 80]},
		{"t": 1, "position": [20, 99, -20], "aboveGround": 3, "lookAt": [0, 0, -50], "lookAtAboveGround": 1}])
	_expect(shot.resolve(tile_to_world, ground_at), "tile keys resolve: %s" % [shot.errors])
	_expect((shot.keys[0].position as Vector3).is_equal_approx(Vector3(10.5, 5.0 + TrailerShot.DEFAULT_EYE_HEIGHT, 9.5)),
		"a tile key stands at eye height over the ground at the tile's centre (%s)" % [shot.keys[0].position])
	_expect((shot.keys[0].target as Vector3).is_equal_approx(Vector3(10.5, 5.0 + TrailerShot.DEFAULT_EYE_HEIGHT, 19.5)),
		"a lookAtTile target is placed the same way")
	_expect(is_equal_approx((shot.keys[1].position as Vector3).y, 8.0), "aboveGround replaces a key's y")
	_expect(is_equal_approx((shot.keys[1].target as Vector3).y, 6.0), "lookAtAboveGround replaces a target's y")
	var off_map := _shot([{"t": 0, "position": [90, 0, 0], "aboveGround": 2, "lookAt": [0, 0, 0]},
		{"t": 1, "position": [0, 0, 0], "lookAt": [0, 0, -1]}])
	_expect(not off_map.resolve(tile_to_world, ground_at), "a key with no ground under it is refused")

func _check_look_directions() -> void:
	_expect(TrailerShot.direction(0, 0).is_equal_approx(Vector3(0, 0, -1)), "yaw 0 looks north (-Z)")
	_expect(TrailerShot.direction(90, 0).is_equal_approx(Vector3(1, 0, 0)), "yaw 90 looks east (+X)")
	_expect(TrailerShot.direction(0, 90).is_equal_approx(Vector3(0, 1, 0)), "pitch 90 looks up")
	var shot := _shot([
		{"t": 0, "position": [0, 0, 0], "pitch": -10},
		{"t": 1, "position": [10, 0, 0], "yaw": 180}])
	_expect(shot.resolve(Callable(), Callable()), "keys without lookAt resolve")
	var along := ((shot.keys[0].target as Vector3) - (shot.keys[0].position as Vector3)).normalized()
	_expect(along.is_equal_approx(TrailerShot.direction(90, -10)), "a key without lookAt looks along the path")
	var heading := ((shot.keys[1].target as Vector3) - (shot.keys[1].position as Vector3)).normalized()
	_expect(heading.is_equal_approx(Vector3(0, 0, 1)), "a key with yaw 180 looks south")

func _check_samples() -> void:
	var shot := _shot([{"t": 0, "position": [0, 0, 0], "lookAt": [0, 0, -10]},
		{"t": 1, "position": [10, 0, 0], "lookAt": [10, 0, -10]}])
	shot.resolve(Callable(), Callable())
	var points := shot.samples(0.25)
	_expect(points.size() == 10, "samples hold camera and target every step, ends included (%d)" % points.size())

func _check_sample_shots() -> void:
	for file: String in DirAccess.get_files_at(SHOTS):
		if not file.ends_with(".json"):
			continue
		var shot := TrailerShot.new()
		_expect(shot.load_file(SHOTS + file), "sample %s parses: %s" % [file, shot.errors])
		_expect(shot.name == file.get_basename(), "sample %s is named after its file" % file)

func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("FAIL: " + message)

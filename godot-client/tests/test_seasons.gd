extends SceneTree

const SeasonSky = preload("res://src/world/season_sky.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# A complete old almanac: date, ordinary day, no effects or catalogue.
	var payload := PackedByteArray([1, 1, 1, 0, 0, 100, 0])
	payload.append_array("Ordinary Day".to_utf8_buffer())
	payload.append(0)
	payload.append_array("Nothing unusual.".to_utf8_buffer())
	payload.append_array(PackedByteArray([0, 0, 0, 0, 0]))
	var legacy := EloriaProtocol.decode_almanac(payload)
	_expect(legacy.type == "almanac" and (legacy.season as Dictionary).is_empty(),
		"old servers remain supported without guessing a season")
	var extended := payload.duplicate()
	extended.resize(payload.size() + 5)
	extended[payload.size()] = 2
	extended.encode_u32(payload.size() + 1, 1796083200)
	var decoded := EloriaProtocol.decode_almanac(extended)
	_expect(decoded.type == "almanac" and int(decoded.season.index) == 2
		and int(decoded.season.next_change) == 1796083200,
		"server season and next UTC boundary survive the wire")
	_expect(EloriaProtocol.decode_almanac(extended.slice(0, extended.size() - 1)).type == "invalid",
		"a truncated season is refused")
	extended[payload.size()] = 4
	_expect(EloriaProtocol.decode_almanac(extended).type == "invalid", "unknown season refused")
	_expect(SeasonSky.summary({"index": 3}) == "Season: Autumn", "HUD season label")

	var manifest := WorldManifest.new()
	manifest.data = {"environment": {
		"sun": {"color": "fff2d8", "energy": 1.4},
		"sky": {"zenith": "3d7ec2", "horizon": "bcc9cd"},
		"fog": {"color": "d8c9a4", "density": 0.002},
		"ambient": {"energy": 0.9, "skyColor": "c8ccd2"}}}
	var original := JSON.stringify(manifest.data)
	var winter := SeasonSky.seasonal(manifest, {"index": 0})
	var summer := SeasonSky.seasonal(manifest, {"index": 2})
	_expect(float(winter.data.environment.sun.energy) < float(summer.data.environment.sun.energy),
		"winter sun is softer than summer sun")
	var winter_sun := DayNightBinder._colour(winter.data.environment.sun.color, Color.WHITE)
	var summer_sun := DayNightBinder._colour(summer.data.environment.sun.color, Color.WHITE)
	_expect(winter_sun.b / winter_sun.r > summer_sun.b / summer_sun.r,
		"winter light is cooler than summer")
	_expect(JSON.stringify(manifest.data) == original, "source manifest remains unchanged")
	_expect(JSON.stringify(SeasonSky.seasonal(manifest, {"index": 0}).data) == JSON.stringify(winter.data),
		"repeated refreshes do not compound the tint")
	_expect(SeasonSky.seasonal(manifest, {}) == manifest, "no stated season keeps authored light")
	var indoors := WorldManifest.new()
	indoors.data = {"environment": {"sun": {"enabled": false}, "ambient": {"energy": 0.5}}}
	_expect(SeasonSky.seasonal(indoors, {"index": 0}) == indoors, "interior lighting remains authored")

	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	var sun := DirectionalLight3D.new()
	root.add_child(env)
	root.add_child(sun)
	for index: int in range(4):
		var seasonal := SeasonSky.seasonal(manifest, {"index": index})
		DayNightBinder.apply(seasonal, env, sun, 0.0)
		_expect(env.environment.ambient_light_energy >= DayNightBinder.NIGHT_AMBIENT_FLOOR,
			"season %d keeps midnight playable" % index)
		DayNightBinder.apply(seasonal, env, sun, 180.0)
		var painted := LookSky.sky_colours(seasonal, 180.0)
		_expect((painted.top as Color).is_equal_approx(
			DayNightBinder._colour(seasonal.data.environment.sky.zenith, Color.WHITE)),
			"painted sky shares season %d with procedural lighting" % index)
	sun.free()
	env.free()
	print("Seasons: %d failure(s)" % failures)
	quit(1 if failures else 0)

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

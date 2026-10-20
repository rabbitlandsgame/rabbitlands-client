extends RefCounted
## A restrained seasonal palette over the map's own daylight, before weather.
## The server names the season. No local wall clock or game-date inference.
## Rebuild from the source manifest each time so repeated binds cannot drift.

const NAMES: Array[String] = ["Winter", "Spring", "Summer", "Autumn"]
const SUN_TINTS: Array[Color] = [Color(0.82, 0.90, 1.0), Color(1.0, 0.97, 0.88),
	Color(1.0, 0.91, 0.73), Color(1.0, 0.82, 0.63)]
const HAZE_TINTS: Array[Color] = [Color(0.78, 0.87, 1.0), Color(0.90, 0.97, 0.89),
	Color(1.0, 0.94, 0.82), Color(1.0, 0.85, 0.70)]
const SUN_ENERGY: Array[float] = [0.88, 1.0, 1.08, 0.94]

static func seasonal(lighting: WorldManifest, season: Dictionary) -> WorldManifest:
	var index := int(season.get("index", -1))
	if index < 0 or index >= NAMES.size() or not DayNightBinder.drives(lighting):
		return lighting
	var copy := WorldManifest.new()
	copy.source_path = lighting.source_path
	copy.data = lighting.data.duplicate()
	var environment: Dictionary = (lighting.data.environment as Dictionary).duplicate(true)
	copy.data["environment"] = environment
	var sun: Dictionary = environment.get("sun", {}) as Dictionary
	_tint(sun, "color", SUN_TINTS[index], 0.35, Color.WHITE)
	sun["energy"] = float(sun.get("energy", 1.0)) * SUN_ENERGY[index]
	var sky: Dictionary = environment.get("sky", {}) as Dictionary
	for key: String in ["zenith", "topColor", "horizon", "horizonColor", "groundHorizon"]:
		if sky.has(key):
			_tint(sky, key, HAZE_TINTS[index], 0.18)
	var haze: Dictionary = environment.get("fog", {}) as Dictionary
	if not haze.is_empty():
		_tint(haze, "color", HAZE_TINTS[index], 0.25, Color("d8c9a4"))
	var ambient: Dictionary = environment.get("ambient", {}) as Dictionary
	for key: String in ["color", "colour", "skyColor"]:
		if ambient.has(key):
			_tint(ambient, key, HAZE_TINTS[index], 0.12)
	# Night colours and the binder's visibility floors stay authored; only
	# dawn/dusk sun warmth shares the season's tint.
	var variants: Dictionary = environment.get("variants", {}) as Dictionary
	for key: String in ["dawn", "dusk"]:
		var variant: Dictionary = variants.get(key, {}) as Dictionary
		var edge_sun: Dictionary = variant.get("sun", {}) as Dictionary
		if edge_sun.has("color"):
			_tint(edge_sun, "color", SUN_TINTS[index], 0.25)
	return copy

static func _tint(block: Dictionary, key: String, tint: Color, amount: float,
		fallback: Color = Color.WHITE) -> void:
	var colour := DayNightBinder._colour(block.get(key), fallback)
	# Multiply rather than replace: a violet barrens sky stays violet.
	var result := colour.lerp(colour * tint, amount)
	block[key] = [result.r, result.g, result.b, result.a]

static func summary(season: Dictionary) -> String:
	var index := int(season.get("index", -1))
	if index < 0 or index >= NAMES.size():
		return ""
	return "Season: %s" % NAMES[index]

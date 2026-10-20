extends RefCounted
## Local appearance preferences shared by settings and actor visuals.
const SECTION := "target_markers"
# Retain square_* as stored preference keys for the former selection square.
# They now style the tentative selection circle, using the active ring's rules.
const DEFAULTS := {
	"circle_size": 100.0, "circle_thickness": 100.0, "circle_color": Color("ff755f"),
	"square_size": 100.0, "square_thickness": 100.0, "square_color": Color("f4c746"),
	"triangle_size": 100.0, "triangle_thickness": 100.0, "triangle_color": Color("ff755f"),
}

static func defaults() -> Dictionary:
	return DEFAULTS.duplicate()

static func limits(key: String) -> Vector2:
	return Vector2(25.0 if key.ends_with("_thickness") else 50.0,
		200.0 if key in ["circle_size", "square_size"] else 300.0)

static func normalise(values: Dictionary) -> Dictionary:
	var result := defaults()
	for key: String in DEFAULTS:
		var value: Variant = values.get(key, DEFAULTS[key])
		if key.ends_with("_color"):
			if value is String and Color.html_is_valid(value): value = Color.html(value)
			if value is Color and is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a):
				result[key] = Color(clampf(value.r, 0.0, 1.0), clampf(value.g, 0.0, 1.0), clampf(value.b, 0.0, 1.0), clampf(value.a, 0.1, 1.0))
		elif (value is float or value is int) and is_finite(float(value)):
			var bounds := limits(key)
			result[key] = clampf(float(value), bounds.x, bounds.y)
	return result

static func read(config: ConfigFile) -> Dictionary:
	var values := {}
	for key: String in DEFAULTS:
		values[key] = config.get_value(SECTION, key, DEFAULTS[key])
	return normalise(values)

static func write(config: ConfigFile, values: Dictionary) -> void:
	var clean := normalise(values)
	for key: String in DEFAULTS:
		config.set_value(SECTION, key, clean[key])

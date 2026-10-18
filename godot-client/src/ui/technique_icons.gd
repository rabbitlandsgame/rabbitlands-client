extends RefCounted
## The painted technique icons (assets/ui/technique_icons.png): 64 px cells,
## eight to a row, in the server catalogue's order (eloria/techniques.py).
## See assets/ui/technique_icons_provenance.md for how they were made.

const ATLAS := preload("res://assets/ui/technique_icons.png")
const CELL := 64
const COLUMNS := 8
const ORDER: Array[String] = [
	"heavy_blow", "measured_strike", "fighting_retreat", "charge",
	"challenge", "second_wind", "war_cry", "executioners_stroke",
	"shield_bash", "brace", "intercept", "cleave",
	"sunder", "flurry", "hamstring", "riposte",
	"backstab", "lunge", "keep_at_bay", "aimed_shot",
	"pinning_shot", "volley", "step_back", "mark_target",
]

static var _cache: Dictionary = {}

## The icon for a technique key, or null for one this client has no art for.
static func icon_for(key: String) -> Texture2D:
	if _cache.has(key):
		return _cache[key]
	var index := ORDER.find(key)
	if index < 0:
		return null
	var texture := AtlasTexture.new()
	texture.atlas = ATLAS
	texture.region = Rect2((index % COLUMNS) * CELL, (index / COLUMNS) * CELL, CELL, CELL)
	_cache[key] = texture
	return texture

class_name CreationClassIcons
extends RefCounted
## The four unframed class emblems used by character creation.
##
## They share one texture so changing class does not trigger another resource
## load.  AtlasTexture instances are cached as well: the class rail may redraw
## while appearance controls change, but the rectangles inside the sheet do
## not.

const SHEET := "res://assets/ui/eloria_creation_class_icons.png"
const CELL := 128
const COLUMNS := 4

const INDICES := {
	"vanguard": 0,
	"ranger": 1,
	"arcanist": 2,
	"warden": 3,
}

static var _sheet: Texture2D
static var _cache: Dictionary = {}

## The emblem for a class key, or null for a class this client does not know.
static func icon_for(class_key: String) -> Texture2D:
	var key: String = class_key.strip_edges().to_lower()
	if not INDICES.has(key):
		return null
	if _cache.has(key):
		return _cache[key]
	if _sheet == null:
		_sheet = load(SHEET) as Texture2D
	if _sheet == null:
		return null
	var index: int = int(INDICES[key])
	var atlas := AtlasTexture.new()
	atlas.atlas = _sheet
	atlas.region = Rect2((index % COLUMNS) * CELL,
		floori(float(index) / COLUMNS) * CELL, CELL, CELL)
	_cache[key] = atlas
	return atlas


## Test and capture seam: callers can provide an in-memory sheet without
## importing the production PNG. Replacing the sheet also invalidates every
## cached subtexture so no AtlasTexture can keep pointing at the old resource.
static func set_sheet_override(texture: Texture2D) -> void:
	_sheet = texture
	_cache.clear()

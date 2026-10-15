class_name SubjectIcons
extends RefCounted
## The shared sheet of subject icons: one picture per thing this client puts
## on a shelf, a tab or a row - the world and its maps, the crafts, the
## schools of magic, and the rest.
##
## Shared because the same subject is named by more than one window. The
## encyclopedia shelves Alchemy, the manufacturing window tabs it, and the
## statistics window lists it as a skill. One sheet and one lookup means those
## three can never drift into three different pictures of the same thing.

const SHEET := "res://assets/ui/eloria_subject_icons.png"
const CELL := 32
const COLUMNS := 8

## Where each subject sits in the sheet, in the order it was drawn.
const INDICES := {
	"world": 0, "skills": 1, "combat": 2, "perks": 3, "gathering": 4,
	"commerce": 5, "alchemy": 6, "manufacturing": 7, "crafting": 8,
	"engineering": 9, "potions": 10, "tailoring": 11, "summoning": 12,
	"spells": 13, "books": 14, "maps": 15, "commands": 16,
	"attack": 17, "defense": 18, "ranging": 19, "overall": 20,
	"utility": 21, "all": 22,
}

## The same subject under the name another part of the client happens to use.
## The server calls the mixing skill "potion" and the encyclopedia shelves
## "potions"; neither is wrong, and neither is worth renaming over a picture.
const ALIASES := {
	"potion": "potions",
	"harvesting": "gathering",
	"magic": "spells",
	"spell": "spells",
	"trade": "commerce",
	"book": "books",
	"map": "maps",
	"defence": "defense",
	"everything": "all",
}

static var _sheet: Texture2D
static var _cache: Dictionary = {}

## The icon for a subject, or null when nothing has been drawn for it.
##
## Null rather than a placeholder: a caller with a glyph to fall back on
## should use it, and one without should draw nothing rather than draw
## something that names the wrong thing.
static func icon_for(subject: String) -> Texture2D:
	var key: String = subject.strip_edges().to_lower()
	key = str(ALIASES.get(key, key))
	if not INDICES.has(key):
		return null
	if _cache.has(key):
		return _cache[key]
	if _sheet == null:
		_sheet = load(SHEET) as Texture2D
	if _sheet == null:
		return null
	var index: int = int(INDICES[key])
	# Cached because the shelves and tab strips are rebuilt on every redraw,
	# and an AtlasTexture per row per redraw is a lot of objects for a picture
	# that never changes.
	var atlas := AtlasTexture.new()
	atlas.atlas = _sheet
	atlas.region = Rect2((index % COLUMNS) * CELL,
		floori(float(index) / COLUMNS) * CELL, CELL, CELL)
	_cache[key] = atlas
	return atlas

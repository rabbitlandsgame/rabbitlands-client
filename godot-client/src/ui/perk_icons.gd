class_name PerkIcons
extends RefCounted
## The sheet of perk emblems, one per perk a player can buy.
##
## A separate sheet from [SubjectIcons] because it is a separate kind of
## picture. A subject is a shelf or a tab, and its icon is a framed brass tile
## that reads as a button. A perk is a line in a list, and its emblem is an
## unframed bronze symbol that sits on whatever panel draws the row - which is
## how the window was drawn before it was built.
##
## The names are the server's, spelled as it spells them: the catalogue packet
## carries them and this table is looked up with what arrives, so a perk
## renamed there loses its emblem rather than getting somebody else's.

const SHEET := "res://assets/ui/eloria_perk_icons.png"
const CELL := 32
const COLUMNS := 8

const INDICES := {
	"lucky hitter": 0, "lucky dodger": 1, "dancing": 2, "life stealing": 3,
	"eagle eye": 4, "lucky archer": 5, "giantslayer": 6, "standard bearer": 7,
	"two handed wielding": 8, "mirror": 9, "berserker": 10, "closer": 11,
	"flanker": 12, "trophy hunter": 13, "armor piercing": 14, "durability": 15,
	"conjurer": 16, "efficient mage": 17, "offensive mage": 18,
	"defensive mage": 19, "summoner": 20, "lifebinder": 21, "artificer": 22,
	"fast regeneration": 23, "careful mixer": 24, "recycler": 25,
	"frugal mixer": 26, "lucky harvester": 27, "much nomz wow": 28,
	"bone eater": 29, "cooldown reduction": 30, "gatherer": 31,
}

static var _sheet: Texture2D
static var _cache: Dictionary = {}

## The emblem for a perk, or null when nothing has been drawn for it.
##
## Null rather than a placeholder, because the server can add a perk at any
## time and a row with no picture reads better than a row wearing the wrong
## one.
static func icon_for(perk: String) -> Texture2D:
	var key: String = perk.strip_edges().to_lower()
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

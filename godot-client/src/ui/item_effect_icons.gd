extends RefCounted
## Stable artwork for each saved effect. Full descriptions stay on hover.
const Perks := preload("res://src/ui/perk_icons.gd")
const PATHS := {
	"Emberstrike": "res://assets/ui/item-effects/emberstrike.png",
	"Frostbind": "res://assets/ui/item-effects/frostbind.png",
	"Siphoning": "res://assets/ui/item-effects/siphoning.png",
	"Soulreave": "res://assets/ui/item-effects/soulreave.png",
	"Mindfire": "res://assets/ui/item-effects/mindfire.png",
	"Renewal": "res://assets/ui/item-effects/renewal.png",
	"Second Wind": "res://assets/ui/item-effects/second-wind.png",
	"Stoneward": "res://assets/ui/item-effects/stoneward.png",
	"Sundering": "res://assets/ui/item-effects/sundering.png",
	"Brutal": "res://assets/ui/item-effects/brutal.png",
	"Balanced": "res://assets/ui/item-effects/balanced.png",
	"Trueflight": "res://assets/ui/item-effects/trueflight.png",
	"Flamebound": "res://assets/ui/item-effects/flamebound.png",
	"Frostbound": "res://assets/ui/item-effects/frostbound.png",
	"Runebound": "res://assets/ui/item-effects/runebound.png",
	"Irradiated": "res://assets/ui/item-effects/irradiated.png",
	"Bodkin": "res://assets/ui/item-effects/bodkin.png",
	"Lightweight": "res://assets/ui/item-effects/lightweight.png",
	"Reinforced": "res://assets/ui/item-effects/reinforced.png",
	"Plated": "res://assets/ui/item-effects/plated.png",
	"Elusive": "res://assets/ui/item-effects/elusive.png",
	"Vital": "res://assets/ui/item-effects/vital.png",
	"Attuned": "res://assets/ui/item-effects/attuned.png",
	"Warded": "res://assets/ui/item-effects/warded.png",
	"Insulated": "res://assets/ui/item-effects/insulated.png",
	"Winterbound": "res://assets/ui/item-effects/winterbound.png",
	"Shielded": "res://assets/ui/item-effects/shielded.png",
	"Arrowguard": "res://assets/ui/item-effects/arrowguard.png",
	"Channeling": "res://assets/ui/item-effects/channeling.png",
	"Penetrating": "res://assets/ui/item-effects/penetrating.png",
	"Restorative": "res://assets/ui/item-effects/restorative.png",
	"Spellguard": "res://assets/ui/item-effects/spellguard.png",
}
static var _textures: Dictionary = {}

static func texture(effect_name: String) -> Texture2D:
	if not PATHS.has(effect_name): return Perks.icon_for(effect_name)
	if not _textures.has(effect_name):
		_textures[effect_name] = load(PATHS[effect_name]) as Texture2D
	return _textures[effect_name] as Texture2D

static func presentation(description: String) -> Dictionary:
	var split := description.find(":")
	var effect_name := description.substr(0, split) if split >= 0 else description
	var body := description.substr(split + 1).strip_edges() if split >= 0 else ""
	var roll := ""
	var chance := RegEx.new()
	chance.compile("^(\\d+(?:\\.\\d+)?%) chance (on a landed hit|when hit) to (.+)\\.$")
	var found := chance.search(body)
	if found:
		roll = found.get_string(1)
		body = ("On hit: " if found.get_string(2) == "on a landed hit" else "When hit: ") + found.get_string(3) + "."
		body = body.replace("paralyze the target for ", "paralyze for ")
	else:
		var stat := RegEx.new()
		stat.compile("^(\\+?\\d+%?) (.+)\\.$")
		found = stat.search(body)
		if found:
			roll = found.get_string(1)
			body = found.get_string(2).substr(0, 1).to_upper() + found.get_string(2).substr(1) + "."
	return {"name": effect_name, "roll": roll, "body": body, "full": description}

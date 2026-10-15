class_name SpellPresentation
extends RefCounted
## Effect ids mirror eloria/world.py effect_by_spell. Harvest effects 14/17
## deliberately have no casting action. Unknown effects stay generic.
const EFFECT_ACTIONS := {0: &"cast_aggressive", 1: &"heal", 2: &"cast_aggressive",
	3: &"cast_defensive", 4: &"heal", 5: &"cast_aggressive",
	6: &"cast_defensive", 9: &"heal", 10: &"cast_aggressive", 12: &"heal",
	72: &"cast_defensive", 73: &"cast_aggressive", 74: &"cast_defensive", 75: &"cast_defensive", 76: &"cast_defensive",
	77: &"cast_defensive", 78: &"cast_defensive", 79: &"heal", 80: &"cast_defensive",
	81: &"cast_defensive", 82: &"cast_defensive", 83: &"cast_aggressive",
	84: &"cast_aggressive", 85: &"cast_aggressive", 86: &"cast_aggressive",
	87: &"cast_aggressive", 88: &"cast_aggressive", 89: &"cast_aggressive",
	90: &"cast_aggressive", 91: &"cast_aggressive", 92: &"cast_defensive",
	18: &"cast_defensive", 19: &"cast_defensive"}
static var _spells: Dictionary = {}

## Mirrors magic.MIN/MAX_SPELL_POWER. Scale geometry around its attachment,
## never the actor, projectile endpoints, animation clock or damage radius.
static func power_scale(power: int) -> float:
	return _power_curve(power, 1.9, 4.2)

static func power_radius(power: int) -> float:
	return _power_curve(power, 1.63, 2.2)

static func power_count(base: int, power: int) -> int:
	return roundi(base * _power_curve(power, 2.08, 4.5))

static func power_intensity(power: int) -> float:
	return _power_curve(power, 1.27, 2.7)

static func _power_curve(power: int, midpoint: float, maximum: float) -> float:
	var tier := clampi(power, 1, 10)
	# P5 reaches the former maximum. Mastery tiers then build more steeply;
	# P10 more than doubles its core size, brightness and particle population.
	if tier <= 5:
		return lerpf(1.0, midpoint, float(tier - 1) / 4.0)
	return lerpf(midpoint, maximum, pow(float(tier - 5) / 5.0, 1.3))

static func action_for_effect(effect: int) -> StringName:
	return EFFECT_ACTIONS.get(effect, &"")

static func action_for_spell(spell_id: int) -> StringName:
	if _spells.is_empty():
		var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json"))
		for spell: Dictionary in catalog.get("spells", []):
			_spells[int(spell.id)] = str(spell.get("effect", ""))
	var effect: String = _spells.get(spell_id, "")
	if effect in ["heal", "regeneration", "dispel", "remote_heal", "restoration", "heal_summoned", "group_heal"]:
		return &"heal"
	if effect in ["harm", "heat_bolt", "cold_bolt", "radiation_bolt", "poison", "life_drain", "mana_drain", "disrupt", "cripple", "expose_heat", "expose_cold", "expose_magic", "expose_radiation"]:
		return &"cast_aggressive"
	return &"cast_defensive"

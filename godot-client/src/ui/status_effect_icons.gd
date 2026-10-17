extends RefCounted
## Shared overhead art and ordering for creatures, other players and the local HUD.
const COLUMNS := 6
const SIZE := 20.0
const GAP := 3.0
## Keep in step with AppState.NEGATIVE_STATUSES. The last five are left by
## fighters' techniques (Shield Bash, Hamstring, Sunder, Mark Target, Challenge).
const NEGATIVE := ["poison", "cripple", "expose_heat", "expose_cold", "expose_magic", "expose_radiation",
	"stun", "root", "sunder", "mark", "challenge"]
const TEXTURES := {
	"poison": preload("res://assets/ui/status/poison.svg"),
	"cripple": preload("res://assets/ui/status/cripple.svg"),
	"expose_heat": preload("res://assets/ui/status/expose_heat.svg"),
	"expose_cold": preload("res://assets/ui/status/expose_cold.svg"),
	"expose_magic": preload("res://assets/ui/status/expose_magic.svg"),
	"expose_radiation": preload("res://assets/ui/status/expose_radiation.svg"),
	"stun": preload("res://assets/ui/status/stun.svg"),
	"root": preload("res://assets/ui/status/root.svg"),
	"sunder": preload("res://assets/ui/status/sunder.svg"),
	"mark": preload("res://assets/ui/status/mark.svg"),
	"challenge": preload("res://assets/ui/status/challenge.svg"),
	"shield": preload("res://assets/ui/status/shield.svg"),
	"magic_protection": preload("res://assets/ui/status/magic_protection.svg"),
	"heat_protection": preload("res://assets/ui/status/heat_protection.svg"),
	"cold_protection": preload("res://assets/ui/status/cold_protection.svg"),
	"radiation_protection": preload("res://assets/ui/status/radiation_protection.svg"),
	"regeneration": preload("res://assets/ui/status/regeneration.svg"),
	"haste": preload("res://assets/ui/status/haste.svg"),
	"invisibility": preload("res://assets/ui/status/invisibility.svg"),
	"magic_immunity": preload("res://assets/ui/status/magic_immunity.svg"),
	"accuracy": preload("res://assets/ui/status/accuracy.svg"),
	"elemental_weapon": preload("res://assets/ui/status/elemental_weapon.svg"),
	"mana_restore": preload("res://assets/ui/status/mana_restore.svg"),
	"true_sight": preload("res://assets/ui/status/true_sight.svg"),
	"brace": preload("res://assets/ui/status/brace.svg"),
	"riposte": preload("res://assets/ui/status/riposte.svg"),
	"war_cry": preload("res://assets/ui/status/war_cry.svg"),
	"intercept": preload("res://assets/ui/status/intercept.svg"),
}

static func known(effects: Array) -> Array[String]:
	var result: Array[String] = []
	for effect: String in TEXTURES:
		if effect in effects:
			result.append(effect)
	return result

static func width(count: int) -> float:
	return mini(count, COLUMNS) * (SIZE + GAP) - GAP if count > 0 else 0.0

static func extra_height(count: int) -> float:
	return float((maxi(1, count) - 1) / COLUMNS) * (SIZE + GAP)

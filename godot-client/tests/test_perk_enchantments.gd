extends SceneTree
const Effects := preload("res://src/ui/item_effect_icons.gd")
const Perks := preload("res://src/ui/perk_icons.gd")
const Glow := preload("res://src/ui/item_glow.gd")
var failures := 0

func _init() -> void:
	for perk: String in Perks.INDICES:
		if Effects.texture(perk) == null or Effects.texture(perk) != Perks.icon_for(perk):
			push_error("Enchantment uses its perk's existing emblem: " + perk)
			failures += 1
	var description := "Mirror: +1 Mirror perk level while equipped."
	var data := Effects.presentation(description)
	if data.name != "Mirror" or data.roll != "+1" or data.body != "Mirror perk level while equipped." or data.full != description:
		push_error("Fixed perk level is presented with its name, +1 and equipped-only description")
		failures += 1
	var glow := Glow.profile({"tier": "magic", "effects": ["Mirror"]})
	if glow.is_empty() or glow.families != [2]:
		push_error("Perk-only enchanted copies retain the arcane equipment glow")
		failures += 1
	if Effects.texture("Unknown future effect") != null:
		push_error("Unknown effects keep the existing empty-icon fallback")
		failures += 1
	print("Perk enchantment presentation: %d failures" % failures)
	quit(1 if failures else 0)

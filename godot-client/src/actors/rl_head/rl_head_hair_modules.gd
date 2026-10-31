class_name RLHeadHairModules
extends RefCounted
## Append-only PC/3 semantic hairstyle IDs. Existing single-sex entries stay
## valid. A future entry may instead supply `variants`, keyed by body sex:
## {"name": "shared_style", "fallback_style": 1, "variants": {
##     "female": {"name": "shared_style_female", "fallback_style": 3},
##     "male": "shared_style_male"}}
## A string variant inherits the entry's fallback; an absent sex is ineligible.
## Names identify concrete GLB files after resolution and must be unique per
## body sex, so the inverse is unambiguous. No wire fields change.

const ENTRIES := {
	2: {"name": "rowan_shag", "sex": "male"},
	3: {"name": "mira_bun", "sex": "female"},
	4: {"name": "rounded_afro", "sex": "male", "fallback_style": 1},
	5: {"name": "cornrows_low_knot", "sex": "female", "fallback_style": 7},
	6: {"name": "shoulder_waves", "sex": "female", "fallback_style": 2},
	7: {"name": "curly_twin_buns", "sex": "female", "fallback_style": 3},
	8: {"name": "receding_sweep", "sex": "male", "fallback_style": 1},
}


## The concrete asset and Low/Medium fallback for this body, or {}.
static func resolve(id: int, sex: String, entries: Dictionary = ENTRIES) -> Dictionary:
	if sex not in ["female", "male"] or not entries.has(id):
		return {}
	var entry: Dictionary = entries[id]
	var name := ""
	var fallback := int(entry.get("fallback_style", 1))
	if entry.has("variants"):
		var variants: Dictionary = entry["variants"]
		var variant: Variant = variants.get(sex)
		if variant is String:
			name = variant
		elif variant is Dictionary:
			name = str((variant as Dictionary).get("name", ""))
			fallback = int((variant as Dictionary).get("fallback_style", fallback))
	elif str(entry.get("sex", "")) == sex:
		name = str(entry.get("name", ""))
	if name.is_empty():
		return {}
	return {"name": name, "fallback_style": fallback,
		"semantic_name": str(entry.get("name", name))}


## Only eligible IDs, in registry order; the UI and renderer share this rule.
static func choices(sex: String, entries: Dictionary = ENTRIES) -> Dictionary:
	var result := {}
	for id: int in entries:
		var resolved := resolve(id, sex, entries)
		if not resolved.is_empty():
			result[id] = resolved
	return result


## Inverse of resolve for a concrete filename. Never accepts another sex's fit.
static func find(style: String, sex: String, entries: Dictionary = ENTRIES) -> int:
	for id: int in entries:
		if str(resolve(id, sex, entries).get("name", "")) == style and not style.is_empty():
			return id
	return 0


## A semantic name plus sex selects its concrete file. Concrete names also
## pass through, except a registered fit belonging only to the other sex.
## An omitted sex preserves the library's historical filename-only API.
static func file_name(style: String, sex: String = "", entries: Dictionary = ENTRIES) -> String:
	if sex.is_empty():
		return style
	var registered := false
	for id: int in entries:
		var entry: Dictionary = entries[id]
		var resolved := resolve(id, sex, entries)
		if str(entry.get("name", "")) == style:
			return str(resolved.get("name", ""))
		if str(resolved.get("name", "")) == style:
			return style
		for body: String in ["female", "male"]:
			registered = registered or str(resolve(id, body, entries).get("name", "")) == style
	return "" if registered else style

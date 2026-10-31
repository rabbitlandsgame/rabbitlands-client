class_name RLHeadHairModules
extends RefCounted
## Append-only PC/3 semantic hairstyle IDs. Existing single-sex entries stay
## valid. A future entry may instead supply `variants`, keyed by body sex:
## {"name": "shared_style", "fallback_style": 1, "variants": {
##     "female": {"name": "shared_style_female", "fallback_style": 3},
##     "male": "shared_style_male"}}
## A string variant inherits the entry's fallback; an absent sex is ineligible.
## Names identify concrete GLB files after resolution and must be unique per
## body sex, so the inverse is unambiguous. Semantic aliases belong to one ID
## globally and cannot name another ID's concrete fit, even on another body.
## Validate proposed entries before appending them. Invalid registries are
## rejected by every lookup with an explicit diagnostic. No wire fields change.

const ENTRIES := {
	2: {"name": "rowan_shag", "sex": "male"},
	3: {"name": "mira_bun", "sex": "female"},
	4: {"name": "rounded_afro", "sex": "male", "fallback_style": 1},
	5: {"name": "cornrows_low_knot", "sex": "female", "fallback_style": 7},
	6: {"name": "shoulder_waves", "sex": "female", "fallback_style": 2},
	7: {"name": "curly_twin_buns", "sex": "female", "fallback_style": 3},
	8: {"name": "receding_sweep", "sex": "male", "fallback_style": 1},
}

## The original saved hairstyle byte remains the player's family choice.
## A replacement is enabled only once its qualified body fit is registered.
const LEGACY_REPLACEMENTS := {1: 22, 2: 9, 3: 24, 4: 21, 5: 11,
	6: 15, 7: 18, 8: 25, 9: 23}

static var _default_validated := false
static var _default_validation: Dictionary = {}


## Authoring check for a proposed complete registry; does not reserve IDs or
## mutate the live table. The returned errors identify each namespace owner.
static func validate(entries: Dictionary = ENTRIES) -> Dictionary:
	var errors: Array[String] = []
	var aliases := {}
	var concrete := {"female": {}, "male": {}}
	for key: Variant in entries:
		if typeof(key) != TYPE_INT or int(key) < 2 or int(key) > 31:
			errors.append("Module ID %s must be an integer in 2..31" % str(key))
			continue
		var id := int(key)
		if entries[id] is not Dictionary:
			errors.append("Module %d must be a dictionary" % id)
			continue
		var entry: Dictionary = entries[id]
		var alias := str(entry.get("name", ""))
		if entry.get("name") is not String or alias.is_empty():
			errors.append("Module %d needs a nonempty semantic name" % id)
		elif aliases.has(alias) and int(aliases[alias]) != id:
			errors.append("Semantic name %s belongs to modules %d and %d" % [alias, aliases[alias], id])
		else:
			aliases[alias] = id
		var fallback: Variant = entry.get("fallback_style", 1)
		if typeof(fallback) != TYPE_INT or int(fallback) < 1 or int(fallback) > 9:
			errors.append("Module %d fallback_style must be an integer in 1..9" % id)
		if entry.has("tie_height") and entry.tie_height is not bool:
			errors.append("Module %d tie_height must be a boolean" % id)
		if entry.has("variants"):
			if entry.variants is not Dictionary or (entry.variants as Dictionary).is_empty():
				errors.append("Module %d variants must be a nonempty dictionary" % id)
				continue
			for body: Variant in entry.variants:
				if body not in ["female", "male"]:
					errors.append("Module %d has an unknown body variant %s" % [id, str(body)])
		else:
			if entry.get("sex", "") not in ["female", "male"]:
				errors.append("Module %d needs a body sex or variants" % id)
		for sex: String in ["female", "male"]:
			if entry.has("variants") and not (entry.variants as Dictionary).has(sex):
				continue
			if not entry.has("variants") and entry.get("sex", "") != sex:
				continue
			var variant: Variant = (entry.variants as Dictionary)[sex] if entry.has("variants") else alias
			var name := ""
			if variant is String:
				name = variant
			elif variant is Dictionary:
				if (variant as Dictionary).get("name") is String:
					name = str(variant.name)
				var style: Variant = (variant as Dictionary).get("fallback_style", fallback)
				if typeof(style) != TYPE_INT or int(style) < 1 or int(style) > 9:
					errors.append("Module %d %s fallback_style must be an integer in 1..9" % [id, sex])
				if variant.has("tie_height") and variant.tie_height is not bool:
					errors.append("Module %d %s tie_height must be a boolean" % [id, sex])
			if name.is_empty():
				errors.append("Module %d %s needs a nonempty concrete filename" % [id, sex])
			elif (concrete[sex] as Dictionary).has(name) and int(concrete[sex][name]) != id:
				errors.append("Concrete filename %s on %s belongs to modules %d and %d" % [name, sex, concrete[sex][name], id])
			else:
				concrete[sex][name] = id
	for sex: String in concrete:
		for name: String in concrete[sex]:
			if aliases.has(name) and int(aliases[name]) != int(concrete[sex][name]):
				errors.append("Semantic name %s belongs to module %d but names module %d's %s fit" % [name, aliases[name], concrete[sex][name], sex])
	return {"ok": errors.is_empty(), "errors": errors}


static func _usable(entries: Dictionary) -> bool:
	var result: Dictionary
	if entries == ENTRIES:
		if not _default_validated:
			_default_validation = validate(entries)
			_default_validated = true
		result = _default_validation
	else:
		result = validate(entries)
	if not result.ok:
		push_error("Invalid semantic hair registry: " + "; ".join(result.errors))
	return bool(result.ok)


## The concrete asset and compatibility fallback for this body, or {}.
static func resolve(id: int, sex: String, entries: Dictionary = ENTRIES) -> Dictionary:
	return _resolve(id, sex, entries) if _usable(entries) else {}


static func replacement_id(style: int, sex: String, entries: Dictionary = ENTRIES) -> int:
	var id := int(LEGACY_REPLACEMENTS.get(style, 0))
	return id if not resolve(id, sex, entries).is_empty() else 0


## A style advertises this only after both placement shapes and their limits
## have been qualified on the matching body. Older entries keep it disabled.
static func supports_tie_height(id: int, sex: String, entries: Dictionary = ENTRIES) -> bool:
	if not _usable(entries) or _resolve(id, sex, entries).is_empty():
		return false
	var entry: Dictionary = entries[id]
	var supported := bool(entry.get("tie_height", false))
	if entry.has("variants"):
		var variant: Variant = (entry.variants as Dictionary).get(sex)
		if variant is Dictionary:
			supported = bool(variant.get("tie_height", supported))
	return supported


static func _resolve(id: int, sex: String, entries: Dictionary) -> Dictionary:
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
	if not _usable(entries):
		return result
	for id: int in entries:
		var resolved := _resolve(id, sex, entries)
		if not resolved.is_empty():
			result[id] = resolved
	return result


## Inverse of resolve for a concrete filename. Never accepts another sex's fit.
static func find(style: String, sex: String, entries: Dictionary = ENTRIES) -> int:
	if not _usable(entries):
		return 0
	for id: int in entries:
		if str(_resolve(id, sex, entries).get("name", "")) == style and not style.is_empty():
			return id
	return 0


## A semantic name plus sex selects its concrete file. Concrete names also
## pass through, except a registered fit belonging only to the other sex.
## An omitted sex preserves the library's historical filename-only API.
static func file_name(style: String, sex: String = "", entries: Dictionary = ENTRIES) -> String:
	if not _usable(entries):
		return ""
	if sex.is_empty():
		return style
	var registered := false
	for id: int in entries:
		var entry: Dictionary = entries[id]
		var resolved := _resolve(id, sex, entries)
		if str(entry.get("name", "")) == style:
			return str(resolved.get("name", ""))
		if str(resolved.get("name", "")) == style:
			return style
		for body: String in ["female", "male"]:
			registered = registered or str(_resolve(id, body, entries).get("name", "")) == style
	return "" if registered else style

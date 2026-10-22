extends RefCounted
## Sparse overrides preserve the original resource ramps until a player edits them.
const LABELS := {"name":"Name", "health":"Health", "ether":"Ether", "food":"Food",
	"action":"Action", "load":"Load", "mount":"Mount status"}
const RESOURCES := {"health":"health", "ether":"mana", "food":"food", "action":"action",
	"load":"load", "mount":"mount_stamina"}
const DEFAULTS := {"name":Color.WHITE, "health":Color(0, 1, 0), "ether":Color(0.4, 0.4, 1),
	"food":Color(1, 1, 0), "action":Color(0.73, 0.28, 0.86), "load":Color("c49c72"), "mount":Color.WHITE}

static func normalise(raw: Variant) -> Dictionary:
	var result := {"colors":{}, "synced":{}}
	if not raw is Dictionary: return result
	var colors: Variant = raw.get("colors", {})
	if colors is Dictionary:
		for item: String in LABELS:
			var color: Variant = colors.get(item)
			if color is Color and is_finite(color.r) and is_finite(color.g) and is_finite(color.b) and is_finite(color.a):
				result.colors[item] = color.clamp()
	var synced: Variant = raw.get("synced", {})
	if synced is Dictionary:
		for item: String in RESOURCES:
			var flag: Variant = synced.get(item, false)
			result.synced[item] = flag is bool and flag
	return result

static func resolve(item: String, options: Dictionary, resources: Dictionary, fallback: Color) -> Color:
	if RESOURCES.has(item) and options.get("synced", {}).get(item, false):
		return resources.get(RESOURCES[item], fallback)
	return options.get("colors", {}).get(item, fallback)

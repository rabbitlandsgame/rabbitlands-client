extends RefCounted
## New-player availability only. The full actor catalog also serves NPCs,
## existing characters and authoring tools, so it must remain unchanged.
const ACTOR_TYPES: Array[int] = [0, 1]
const MESSAGE := "Only Human characters can be created right now."

static func allows_actor_type(value: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) \
		and floor(float(value)) == float(value) and int(value) in ACTOR_TYPES

static func options(registry: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var models: Dictionary = registry.get("models", {})
	var seen := {}
	for value: Variant in registry.get("creationOptions", []):
		if value is not Dictionary: continue
		var option := value as Dictionary
		var actor_type: Variant = option.get("actorType", -1)
		if not allows_actor_type(actor_type) or seen.has(int(actor_type)): continue
		var model: Dictionary = models.get(str(option.get("model", "")), {})
		var sex := "female" if int(actor_type) == 0 else "male"
		if str(model.get("culture", "")) != "luminous" \
				or str(model.get("gender", "")) != sex or bool(model.get("retired", false)):
			continue
		seen[int(actor_type)] = true
		result.append(option.duplicate(true))
	return result

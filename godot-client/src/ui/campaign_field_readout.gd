extends RefCounted
## Passive field summaries. Available actions still come from the server targets.
const RESOURCES := ["Sage", "Hearthroot", "Flint", "Coal", "Kelp", "Watercress"]

static func instructions(snapshot: Dictionary) -> String:
	var travel: Dictionary = snapshot.get("travel", {})
	if travel.is_empty(): return str(snapshot.get("hint", "Explore with the field crew."))
	var text := str(travel.get("route", snapshot.get("hint", "Follow the marked destination.")))
	# The rescue's old npc field can identify a place (Lantern Mine), rather
	# than a person. Its authored route already explains how to resume.
	var npc := str(travel.get("npc", ""))
	if not npc.is_empty() and (str(snapshot.get("kind", "")) != "rescue" or str(snapshot.get("key", "")) == "rescue_checkin"):
		text += "\nSpeak with " + npc + " to continue."
	return text

static func worker_activity(worker: Dictionary, working := "Harvesting") -> String:
	if bool(worker.get("downed", false)): return "DOWNED — use Heal Target"
	var resource := str(worker.get("resource", ""))
	if resource not in RESOURCES: resource = ""
	match str(worker.get("status", "")):
		"under_attack": return "Under attack"
		"loading": return "Loading recovered stock" if resource in ["Flint", "Coal"] else "Loading cargo"
		"returning": return "Carrying to storage"
		"moving": return "Moving to work"
		"waiting": return "Waiting"
		"repairing": return "Repairing the lift"
		"harvesting":
			if resource in ["Flint", "Coal"]: return "Mining " + resource
			if resource == "Kelp": return "Cutting Kelp"
			return "Gathering " + resource if not resource.is_empty() else working
	# Older servers cannot distinguish idle, approach and combat. Do not turn
	# the old 'harvest' assignment into a claim that a swing is taking place.
	if str(worker.get("activity", "")) == "return" and int(worker.get("cargo", 0)) > 0:
		return "Carrying to storage"
	return working if bool(worker.get("harvesting", false)) else "Moving / preparing"

static func _workers(snapshot: Dictionary) -> Array:
	var ledger: Dictionary = snapshot.get("shelves", {})
	for key: String in ["fire", "water", "growers"]:
		var field: Dictionary = ledger.get(key, {})
		if not field.is_empty(): return field.get("workers", [])
	return []

static func _crew_alert(workers: Array) -> String:
	for worker: Dictionary in workers:
		if bool(worker.get("downed", false)):
			return str(worker.get("name", "A worker")) + " is down — use Heal Target."
	for worker: Dictionary in workers:
		if str(worker.get("status", "")) == "under_attack":
			return str(worker.get("name", "A worker")) + " is under attack — intercept the attackers."
	return ""

static func _field_hint(field: Dictionary, fallback: String) -> String:
	var hint := str(field.get("field_hint", ""))
	return hint if not hint.is_empty() and hint.length() <= 240 else fallback

static func has_warning(field: Dictionary) -> bool:
	return (field.get("hazards", []) as Array).any(func(hazard: Dictionary) -> bool: return str(hazard.get("kind", "")) == "warning")

static func _supply(snapshot: Dictionary) -> Dictionary:
	var ledger: Dictionary = snapshot.get("shelves", {})
	if str(ledger.get("phase", "")) != "work": return {}
	var progress := ""
	var action := ""
	var fire: Dictionary = ledger.get("fire", {})
	var water: Dictionary = ledger.get("water", {})
	var growers: Dictionary = ledger.get("growers", {})
	if not fire.is_empty():
		if str(fire.get("stage", "")) == "fire_sapper":
			action = "Prepare the yard, then confront Krek."
			if has_warning(fire):
				return {"text":"MOVE OUT OF THE MARKED BLAST AREA", "urgent":true}
		else:
			progress = "Shipment secured: %d/%d · Carried: %d" % [int(fire.get("recovered", 0)) + int(fire.get("mined", 0)),
				int(fire.get("recovered_goal", 0)) + int(fire.get("mined_goal", 0)), int(fire.get("carried", 0))]
			if str(fire.get("stage", "")) == "fire_coal" and str(fire.get("step", "")) != "extract":
				action = "Protect the mechanic; use the lift to begin the next repair." if str(fire.get("route", "")) == "lift" \
					else "Clear the attackers and brace the marked passage supports."
			elif str(fire.get("stage", "")) == "fire" and str(fire.get("step", "")) != "extract":
				action = "Cut the signal rope, clear the guards, then release the crew." if str(fire.get("route", "")) == "silence" and not bool(fire.get("signal", false)) \
					else "Clear the barricade guards, then release the crew."
			else: action = "Protect the crew and the loading paths."
		action = _field_hint(fire, action)
	elif not water.is_empty():
		if has_warning(water):
			return {"text":"MOVE OUT OF THE MARKED SURGE", "urgent":true}
		match str(water.get("stage", "")):
			"water_cutters":
				var stored: Dictionary = water.get("stored", {})
				var goals: Dictionary = water.get("goals", {})
				progress = "Secured: %d/%d Kelp · %d/%d Watercress" % [int(stored.get("kelp", 0)), int(goals.get("kelp", 0)),
					int(stored.get("cress", 0)), int(goals.get("cress", 0))]
				match str(water.get("command", "wait")):
					"wait": action = "Crew waiting — choose Work when you are ready."
					"regroup": action = "The crew is regrouping. Follow the marked landing, then choose Work."
					_: action = "Protect the cutters and Ada's loading route. Only secured bags count."
			"water_barge":
				progress = "Barge hull: %d/100 · Landings reached: %d/3" % [int(water.get("hull", 0)), int(water.get("landing", 0))]
				action = "Repair the hull with Wood Planks before ordering Sail." if int(water.get("hull", 0)) <= 0 \
					else "Stay beside the barge and protect the crew." if bool(water.get("sailing", false)) \
					else "Barge waiting — clear the landing, then choose Sail."
			"water": action = "Restore the channels using the approach you chose with Iona."
			_: action = "Prepare the gatehouse, then confront Veyra."
		action = _field_hint(water, action)
	elif not growers.is_empty() and not bool(growers.get("raid", false)):
		var field := str(growers.get("field", "sage"))
		var crop := "Sage" if field == "sage" else "Hearthroot"
		var stored := int((growers.get("stored", {}) as Dictionary).get(field, 0))
		var goal := 10000 if field == "sage" else 5000
		progress = "%s secured: %d/%d · In bags: %d" % [crop, stored, goal, int(growers.get("carried", 0))]
		action = "Watch the Old Warren approach and protect the carrying workers."
	else: return {}
	var alert := _crew_alert(_workers(snapshot))
	var lines: PackedStringArray = []
	if not alert.is_empty(): lines.append(alert)
	if not progress.is_empty(): lines.append(progress)
	if alert.is_empty() and not action.is_empty(): lines.append(action)
	return {"text":"\n".join(lines), "urgent":not alert.is_empty()}

static func _rescue(snapshot: Dictionary) -> Dictionary:
	var rescue: Dictionary = snapshot.get("rescue", {})
	if rescue.is_empty() or rescue.has("checkin"): return {}
	if str(rescue.get("stage", "")) in ["reward", "aftermath", "complete"]: return {}
	var mother: Dictionary = rescue.get("mother", {})
	if bool(mother.get("downed", false)):
		if not bool(mother.get("configured", false)):
			return {"text":"The woman is hurt — use Heal Target to help her stand.", "urgent":true}
		return {"text":"Elen is down — use Heal Target before continuing together.", "urgent":true}
	if not bool(mother.get("configured", false)) or not bool(mother.get("enabled", false)):
		return {}
	if int(mother.get("health", 0)) < float(mother.get("max_health", 1)) * 0.35:
		return {"text":"Elen is badly hurt — use Heal Target and keep attackers away from her.", "urgent":true}
	var ether := int(mother.get("mana", 0))
	if ether < 8:
		return {"text":"Elen has too little ether left to heal. Keep yourself well with Heal or potions.", "urgent":true}
	if ether * 4 <= int(mother.get("max_mana", 1)):
		return {"text":"Elen is low on ether. Use Heal or potions to ease the strain, and stay close.", "urgent":true}
	return {}

static func summary(snapshot: Dictionary) -> Dictionary:
	if not bool(snapshot.get("active", false)) or not (snapshot.get("travel", {}) as Dictionary).is_empty(): return {}
	match str(snapshot.get("kind", "")):
		"shelves": return _supply(snapshot)
		"rescue": return _rescue(snapshot)
	return {}

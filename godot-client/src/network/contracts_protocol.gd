extends RefCounted
## Bounded, read-only shape checks for the Landfall contracts board.
const SKILLS := ["melee","magic","ranging","summoning","harvesting","alchemy"]
const TEMPLATES := {
	"watch_road":["melee",1090], "wardens_call":["magic",1091],
	"towpath_lookout":["ranging",1092], "watchful_companion":["summoning",1093],
	"gatherers_round":["harvesting",1094], "apprentice_order":["alchemy",1095],
	"hold_worksite":["melee",1100], "sweep_camps":["melee",1101],
	"healing_line":["magic",1102], "break_siege":["magic",1103],
	"ridge_sentinels":["ranging",1104], "trail_pursuit":["ranging",1105],
	"supply_guard":["summoning",1106], "hunt_burrows":["summoning",1107],
	"harvest_bundle":["harvesting",1108], "harvest_survey":["harvesting",1109],
	"alchemy_reagents":["alchemy",1110], "alchemy_stock":["alchemy",1111]}

static func number(value: Variant, maximum := 2147483647) -> bool:
	return typeof(value) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(value)) \
		and float(value) == floor(float(value)) and float(value) >= 0 and float(value) <= maximum

static func variant_skill(variant: String) -> String:
	if variant in SKILLS: return variant
	var binding: Array = TEMPLATES.get(variant,[])
	return str(binding[0]) if binding.size() == 2 and int(binding[1]) >= 1100 else ""

static func text(value: Variant, maximum := 256, empty := true) -> bool:
	return value is String and value.length() <= maximum and (empty or not value.is_empty())

static func identity(value: Variant, empty := false) -> bool:
	if not text(value,128,empty): return false
	for character: String in value:
		if character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:": return false
	return true

static func reward(value: Variant) -> bool:
	if not value is Dictionary or not value.get("xp") is Dictionary or value.xp.size() > 20 \
			or not number(value.get("gold")) or not number(value.get("marks")) \
			or not value.get("items") is Array or value.items.size() > 16: return false
	for skill: Variant in value.xp:
		if not identity(skill) or not number(value.xp[skill]): return false
	for item: Variant in value.items:
		if not item is Dictionary or not text(item.get("name"),128,false) or not number(item.get("count"),1000000): return false
	return true

static func location(value: Variant) -> bool:
	if not value is Dictionary or not text(value.get("map"),128,false) or not text(value.get("label"),256) \
			or not value.get("tile") is Array or value.tile.size() != 2: return false
	return value.tile.all(func(coordinate: Variant) -> bool:return number(coordinate,65535))

static func row(value: Variant) -> bool:
	if not value is Dictionary or not identity(value.get("id")) or value.get("skill") not in SKILLS: return false
	if not number(value.get("quest_id"),65535): return false
	if value.has("template_id"):
		if not identity(value.template_id) or not TEMPLATES.has(value.template_id): return false
		var binding: Array = TEMPLATES[value.template_id]
		if str(value.skill) != str(binding[0]) or int(value.quest_id) != int(binding[1]): return false
	elif int(value.quest_id) != 1090+SKILLS.find(value.skill): return false
	for key: String in ["title","description","route","tier","status","reason"]:
		if not text(value.get(key),1024 if key == "description" else 256,key not in ["title","status"]): return false
	if not value.get("eligible") is bool or not reward(value.get("reward")): return false
	if not value.get("objectives") is Array or value.objectives.size() > 16: return false
	var seen := {}
	for objective: Variant in value.objectives:
		if not objective is Dictionary or not identity(objective.get("id")) or seen.has(objective.id) \
				or not text(objective.get("label"),256,false) or not number(objective.get("current")) \
				or not number(objective.get("target")): return false
		seen[objective.id] = true
	if not location(value.get("location")): return false
	if value.has("next_step"):
		var step: Variant = value.next_step
		if not step is Dictionary or not identity(step.get("objective_id"),true) or not text(step.get("action"),256) \
				or not text(step.get("detail"),1024) or not location(step.get("location")) \
				or not number(step.get("current")) or not number(step.get("target")): return false
	if value.has("preparation"):
		var preparation: Variant = value.preparation
		if not preparation is Dictionary or not preparation.get("ready") is bool or not text(preparation.get("reason"),256) \
				or not preparation.get("checks") is Array or preparation.checks.size() > 8: return false
		for check: Variant in preparation.checks:
			if not check is Dictionary or not text(check.get("label"),128,false) or not check.get("ready") is bool \
					or not text(check.get("detail"),256): return false
	if value.has("can_reroll") and not value.can_reroll is bool: return false
	if value.has("reroll_reason") and not text(value.reroll_reason,256): return false
	if value.has("route_label") and not text(value.route_label,128): return false
	if value.has("donation"):
		var donation: Variant = value.donation
		if not donation is Dictionary or not text(donation.get("item"),128,false) \
				or not number(donation.get("count"),1000000) or not number(donation.get("gold")) \
				or not donation.get("eligible") is bool or not text(donation.get("reason"),256): return false
	return true

static func valid(value: Variant) -> bool:
	if not value is Dictionary or value.get("version") != 1 or not number(value.get("revision")) \
			or not text(value.get("day"),16,false) or not number(value.get("reset_at"),4294967295) \
			or value.get("accepted_limit") != 3 or not identity(value.get("tracked_id"),true) \
			or not number(value.get("marks")): return false
	if value.has("open") and not value.open is bool: return false
	if value.has("reset_token") and not number(value.reset_token): return false
	if value.has("reset_skills"):
		if not value.reset_skills is Array or value.reset_skills.size() > SKILLS.size(): return false
		var reset := {}
		for skill: Variant in value.reset_skills:
			if skill not in SKILLS or reset.has(skill): return false
			reset[skill] = true
	if value.has("current") and (not value.current is Dictionary or (not value.current.is_empty() and not row(value.current))): return false
	if value.has("joins"):
		if not value.joins is Array or value.joins.size() > 7: return false
		for join: Variant in value.joins:
			if not join is Dictionary or not identity(join.get("owner")) or not text(join.get("title"),256,false) \
					or not join.get("eligible") is bool or not text(join.get("reason"),256): return false
	if value.has("encounter"):
		var encounter: Variant = value.encounter
		if not encounter is Dictionary or not text(encounter.get("stage",""),64) or not text(encounter.get("phase",""),64) \
				or not number(encounter.get("waves",0)) or not encounter.get("workers",[]) is Array or encounter.get("workers",[]).size() > 8: return false
		var actors := {}
		for worker: Variant in encounter.get("workers",[]):
			if not worker is Dictionary or not number(worker.get("actor_id")) or int(worker.actor_id) < 1 or actors.has(worker.actor_id) \
					or not text(worker.get("name"),128,false) or not number(worker.get("health"),1000000) \
					or not number(worker.get("max_health"),1000000) or int(worker.max_health) < 1 \
					or int(worker.health) > int(worker.max_health) or not worker.get("downed") is bool: return false
			actors[worker.actor_id] = true
	var weekly: Variant = value.get("weekly")
	if not weekly is Dictionary or not number(weekly.get("count")) or weekly.get("target") != 5 \
			or not weekly.get("awarded") is bool or weekly.get("bonus_marks") != 3: return false
	for key: String in ["offers","accepted"]:
		var rows: Variant = value.get(key)
		if not rows is Array or rows.size() > (3 if key == "accepted" else 36): return false
		var seen := {}
		for entry: Variant in rows:
			if not row(entry) or seen.has(entry.id): return false
			seen[entry.id] = true
	if not value.get("catalog") is Array or value.catalog.size() > 16: return false
	var seen := {}
	for entry: Variant in value.catalog:
		if not entry is Dictionary or not identity(entry.get("id")) or seen.has(entry.id) \
				or not text(entry.get("title"),128,false) or not text(entry.get("description"),1024) \
				or not number(entry.get("cost")) or not entry.get("eligible") is bool \
				or not text(entry.get("reason"),256) or not reward(entry.get("reward")): return false
		seen[entry.id] = true
	return true

static func current(snapshot: Dictionary) -> Dictionary:
	var selected: Dictionary = (snapshot.get("contracts",{}) as Dictionary).get("current",{})
	if not selected.is_empty(): return selected
	for entry: Dictionary in (snapshot.get("contracts",{}) as Dictionary).get("accepted",[]):
		if str(entry.get("id","")) == str(snapshot.get("run_id","")): return entry
	return {}

extends RefCounted
## Presentation only. Counters and recovery identities come from current quest
## state; these summaries never issue actions or alter authoritative progress.
const FieldReadout := preload("res://src/ui/campaign_field_readout.gd")
const AllyRecovery := preload("res://src/ui/campaign_ally_recovery.gd")

static func _empty(full: String) -> Dictionary:
	return {"objective":"", "ribbon_objective":"", "counter":"", "ribbon_counter":"", "progress":-1.0, "urgent":false,
		"alert":"", "recovery":{}, "secondary":"", "full_objective":full}

static func _number(value: int) -> String:
	var digits := str(maxi(0,value))
	var grouped := ""
	while digits.length() > 3:
		grouped = "," + digits.right(3) + grouped
		digits = digits.left(digits.length()-3)
	return digits + grouped

static func _short_goal(value: int) -> String:
	# Abbreviate exact whole units only; never round an unfinished receipt.
	for scale: int in [1000000,1000]:
		if value >= scale and value % scale == 0:
			return _number(roundi(float(value)/float(scale))) + ("m" if scale == 1000000 else "k")
	return _number(value)

static func _counter(result: Dictionary, label: String, current: int, target: int) -> void:
	if target <= 1: return
	result.counter = "%s · %s / %s" % [label,_number(current),_number(target)]
	result.ribbon_counter = "%s / %s" % [_number(current),_short_goal(target)]
	result.progress = clampf(float(maxi(0,current))/float(target),0.0,1.0)

static func _unfinished(ledger: Dictionary, skip: Array = []) -> Dictionary:
	for row: Dictionary in ledger.get("objectives",[]):
		if str(row.get("id","")) in skip or str(row.get("label","")).begins_with("Optional:"): continue
		if int(row.get("current",0)) < int(row.get("target",0)): return row
	return {}

static func _named_objective(ledger: Dictionary, identity: String) -> Dictionary:
	for row: Dictionary in ledger.get("objectives",[]):
		if str(row.get("id","")) == identity: return row
	return {}

static func _task(result: Dictionary, row: Dictionary) -> void:
	if row.is_empty(): return
	result.objective = str(row.get("label",""))
	result.counter = ""; result.ribbon_counter = ""; result.progress = -1.0
	_counter(result,"Progress",int(row.get("current",0)),int(row.get("target",0)))

static func _preferred(snapshot: Dictionary) -> String:
	for identity: String in snapshot.get("preferred_targets",[]):
		for target: Dictionary in snapshot.get("targets",[]):
			if str(target.get("id","")) != identity or identity in ["storage","return","leave"] \
					or not bool(target.get("enabled",true)) or bool(target.get("completed",false)) \
					or str(target.get("label","")).begins_with("Optional"): continue
			return str(target.get("label",""))
	# Finish is a real next step once this player's required work is complete.
	for target: Dictionary in snapshot.get("targets",[]):
		if str(target.get("id","")) == "finish" and bool(target.get("enabled",false)):
			return str(target.get("label",""))
	return ""

static func _crew(result: Dictionary, workers: Array) -> void:
	if workers.is_empty(): return
	var standing := workers.filter(func(worker: Dictionary) -> bool:
		return not bool(worker.get("downed",false)) and int(worker.get("health",1)) > 0).size()
	result.secondary = "Crew %d / %d" % [standing,workers.size()]

static func _field_action(readout: Dictionary, fallback: String) -> String:
	# The shared readout places progress first and the actual current action
	# last. Keep that complete authored instruction, including needed materials.
	if bool(readout.get("urgent",false)): return fallback
	var lines := str(readout.get("text","")).split("\n",false)
	return str(lines[-1]) if not lines.is_empty() else fallback

static func _water_final_loads(ledger: Dictionary, water: Dictionary) -> bool:
	# Native cut includes secured stock, loading bins and bags. It can exceed
	# a shortened legacy goal, so compare to production objectives when present.
	var cut: Dictionary = water.get("cut",{})
	var unfinished := false
	for identity: String in ["kelp","cress"]:
		var row := _named_objective(ledger,identity)
		var goal := int(row.get("target",(water.get("goals",{}) as Dictionary).get(identity,0)))
		if goal <= 0 or not cut.has(identity) or int(cut[identity]) < goal: return false
		unfinished = unfinished or int((water.get("stored",{}) as Dictionary).get(identity,0)) < goal
	return unfinished

static func _supply(result: Dictionary, snapshot: Dictionary, readout: Dictionary) -> void:
	var ledger: Dictionary = snapshot.get("shelves",{})
	var fire: Dictionary = ledger.get("fire",{})
	var water: Dictionary = ledger.get("water",{})
	var growers: Dictionary = ledger.get("growers",{})
	if not fire.is_empty():
		_crew(result,fire.get("workers",[]))
		if str(fire.get("step","")) == "extract":
			if str(fire.get("stage","")) in ["fire","fire_coal"]:
				var goal := int(fire.get("recovered_goal",0))+int(fire.get("mined_goal",0))
				var secured := int(fire.get("recovered",0))+int(fire.get("mined",0))
				var final_bags := goal > 0 and secured < goal and secured+int(fire.get("carried",0)) >= goal
				result.objective = "Guard the final " + ("Coal" if str(fire.get("stage","")) == "fire_coal" else "Flint") \
					+ " delivery" if final_bags else "Protect miners and hauling paths"
				var resource := "Coal" if str(fire.get("stage","")) == "fire_coal" else "Flint"
				result.ribbon_objective = "Guard final " + resource + " load" if final_bags else "Guard " + resource + " crew"
			else: result.objective = _field_action(readout,"Protect the crew and loading paths")
			_counter(result,"Coal secured" if str(fire.get("stage","")) == "fire_coal" else "Flint secured",
				int(fire.get("recovered",0))+int(fire.get("mined",0)),
				int(fire.get("recovered_goal",0))+int(fire.get("mined_goal",0)))
		else:
			var preparation := _unfinished(ledger,["secured"])
			if not preparation.is_empty(): _task(result,preparation)
		return
	if not water.is_empty():
		_crew(result,water.get("workers",[]))
		result.objective = _field_action(readout,str(result.objective))
		if str(water.get("stage","")) == "water_cutters":
			match str(water.get("command","wait")):
				"wait":
					result.objective = "Order Work at the crew station"
					result.ribbon_objective = "Order Work"
				"regroup":
					result.objective = "Meet crew; then order Work"
					result.ribbon_objective = "Meet the crew"
				"work":
					var final_loads := _water_final_loads(ledger,water)
					result.objective = "Guard the final delivery route" if final_loads else "Protect cutters and Ada's route"
					result.ribbon_objective = "Guard final delivery" if final_loads else "Guard cutters"
			for identity: String in ["kelp","cress"]:
				var row := _named_objective(ledger,identity)
				var goal := int(row.get("target",(water.get("goals",{}) as Dictionary).get(identity,0)))
				var stored := int((water.get("stored",{}) as Dictionary).get(identity,0))
				if goal <= 0 or stored >= goal: continue
				_counter(result,("Kelp" if identity == "kelp" else "Watercress") + " secured",stored,goal)
				break
		elif str(water.get("stage","")) == "water_barge":
			var landings := _named_objective(ledger,"landings")
			_counter(result,"Landings reached",int(water.get("landing",0)),int(landings.get("target",0)))
		return
	if not growers.is_empty() and not bool(growers.get("raid",false)):
		_crew(result,growers.get("workers",[]))
		var identity := str(growers.get("field","sage"))
		var crop := "Sage" if identity == "sage" else "Hearthroot"
		result.objective = "Protect the " + crop + " harvesters"
		result.ribbon_objective = "Guard " + crop + " crew"
		var row := _named_objective(ledger,identity)
		_counter(result,crop + " secured",int((growers.get("stored",{}) as Dictionary).get(identity,0)),int(row.get("target",0)))

static func campaign(snapshot: Dictionary, current_map := "") -> Dictionary:
	var result := _empty(FieldReadout.instructions(snapshot))
	var travel: Dictionary = snapshot.get("travel",{})
	if not travel.is_empty():
		var npc := str(travel.get("npc",""))
		result.objective = "Speak with " + npc if not npc.is_empty() and (str(snapshot.get("kind","")) != "rescue" \
			or str(snapshot.get("key","")) == "rescue_checkin") else "Go to " + str(travel.label) if travel.has("label") else result.full_objective
		return result
	if bool(snapshot.get("completed",false)):
		result.objective = "Quest complete"
		return result
	if bool((snapshot.get("party",{}) as Dictionary).get("waiting_for_scene",false)):
		result.objective = "Wait for the party's conversation"
		return result
	var adoption: Dictionary = snapshot.get("adoption",{})
	if str(adoption.get("state","")) == "pending":
		result.objective = str(adoption.get("summary","Review the shared quest outcome"))
		return result
	var ledger: Dictionary = snapshot.get("shelves",{})
	var phase := str(ledger.get("phase",snapshot.get("stage","")))
	var local := current_map.is_empty() or EloriaProtocol.map_id_from_reference(current_map) \
		== EloriaProtocol.map_id_from_reference(str(snapshot.get("map","")))
	var readout := FieldReadout.summary(snapshot) if local else {}
	result.objective = result.full_objective
	if phase == "work":
		_task(result,_unfinished(ledger))
		if str(result.objective).is_empty(): result.objective = _preferred(snapshot)
		if str(snapshot.get("kind","")) == "shelves": _supply(result,snapshot,readout)
		var preferred := _preferred(snapshot)
		if not preferred.is_empty() and _unfinished(ledger).is_empty(): result.objective = preferred
	elif str(snapshot.get("kind","")) == "shelves" and phase == "report":
		result.objective = "Speak with Ilka Tarn" if bool(snapshot.get("available",false)) else "Return to Ilka at The True Note"
	if bool(readout.get("urgent",false)):
		result.urgent = true
		result.alert = str(readout.get("text","")).split("\n",false)[0]
	var patients := AllyRecovery.patients(snapshot,str(snapshot.get("map","")) if current_map.is_empty() else current_map)
	if not patients.is_empty():
		result.recovery = patients[0]
		if str(snapshot.get("kind","")) == "rescue": result.ribbon_objective = "Heal " + str(patients[0].name)
	return result

static func guide(payload: Dictionary) -> Dictionary:
	var full := str(payload.get("hint",""))
	var result := _empty(full)
	result.objective = full if not full.is_empty() else str(payload.get("title","Follow your current objective"))
	var item := str(payload.get("item",""))
	_counter(result,item if not item.is_empty() else "Progress",int(payload.get("count",0)),int(payload.get("required",0)))
	return result

extends SceneTree
const Summary := preload("res://src/ui/quest_tracker_summary.gd")
const Readout := preload("res://src/ui/campaign_field_readout.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)

func supplies() -> Dictionary:
	return {"kind":"shelves", "active":true, "run_id":"summary-test", "map":"landfall", "stage":"work",
		"hint":"Protect the Sage beds. Only deliveries to crew storage count.", "targets":[],
		"shelves":{"phase":"work", "objectives":[{"id":"sage","label":"Store 10,000 Sage","current":1200,"target":10000},
			{"id":"root","label":"Store 5,000 Hearthroot","current":0,"target":5000}],
			"growers":{"field":"sage","stored":{"sage":1200,"root":0},"carried":800,"raid":false,
				"workers":[{"actor_id":400,"name":"Ada","health":80,"downed":false},
					{"actor_id":401,"name":"Nell","health":1,"downed":true}]}}}

func ledger_value(detail: Dictionary, label: String) -> String:
	for row: Dictionary in detail.ledger:
		if str(row.label) == label: return str(row.value)
	return ""

func inline_instructions() -> void:
	var state := supplies()
	state.shelves.growers.stored.sage = 6240; state.shelves.growers.carried = 760
	state.shelves.growers.workers = []
	for index: int in 4:
		state.shelves.growers.workers.append({"actor_id":400+index,"name":"Worker "+str(index),"health":80,"downed":false})
	var before := JSON.stringify(state)
	var detail := Summary.instructions(state,"landfall")
	expect(detail.text == Readout.instructions(state) and JSON.stringify(state) == before,
		"inline Instructions preserves the exact native objective and never changes quest state")
	expect(ledger_value(detail,"Crew storage") == "6,240 / 10,000 Sage" \
		and ledger_value(detail,"In workers' bags") == "760 Sage" and ledger_value(detail,"Crew") == "4 / 4 standing",
		"the Sage foldout separates secured stock, actual carried bags and crew status")
	expect(detail.replaces_supply_ledger and detail.ledger.size() == 3,
		"a complete active-field production table can replace the verbose supply ledger")
	expect(detail.note == "Use Heal Target to revive a fallen worker.","a known native healthy crew keeps one brief actual recovery lesson")
	expect(detail.guidance == "Watch the Old Warren approach and protect the carrying workers.",
		"useful field guidance retains the complete nonurgent action line")
	var remote := Summary.instructions(state,"landfall_town")
	expect(remote.ledger.is_empty() and remote.note.is_empty() and not remote.replaces_supply_ledger,
		"Instructions never presents a remote crew as a current local encounter")
	state.travel = {"label":"Ilka Tarn","route":"Return to The True Note with the shipment."}
	detail = Summary.instructions(state,"landfall")
	expect(detail.text == Readout.instructions(state) and detail.ledger.is_empty() and detail.note.is_empty(),
		"native travel replaces suspended field readouts with its exact route")
	state.erase("travel")
	state.shelves.objectives = []
	detail = Summary.instructions(state,"landfall")
	expect(ledger_value(detail,"Crew storage") == "6,240 Sage" and not detail.replaces_supply_ledger,
		"a missing contract preserves the native storage value without inventing a goal or hiding the old checklist")
	for worker: Dictionary in state.shelves.growers.workers: worker.erase("actor_id")
	expect(Summary.instructions(state,"landfall").note.is_empty(),"crew metadata without a native ally identity does not promise Heal Target support")
	state.shelves.erase("growers")
	state.shelves.fire = {"stage":"fire_coal","step":"extract","recovered":50,"mined":30,
		"recovered_goal":100,"mined_goal":200,"carried":20,"workers":[],
		"field_hint":"Protect the miners and both hauling paths. Heal Target revives a fallen worker."}
	state.hint = state.shelves.fire.field_hint
	detail = Summary.instructions(state,"landfall")
	expect(ledger_value(detail,"Recovered secured") == "50 / 100 Coal" \
		and ledger_value(detail,"Mined secured") == "30 / 200 Coal" and ledger_value(detail,"In workers' bags") == "20 Coal",
		"Coal retains both actual quota requirements and never counts its bags as secured")
	expect(detail.replaces_supply_ledger and detail.guidance.is_empty(),
		"complete extraction quotas can replace the old ledger without duplicating the native instruction paragraph")
	state.shelves.fire.step = "repair"
	detail = Summary.instructions(state,"landfall")
	expect(not detail.replaces_supply_ledger and ledger_value(detail,"Recovered secured").is_empty(),
		"lift preparation keeps its existing work checklist instead of promising an extraction table")
	state.shelves.fire.step = "extract"; state.shelves.fire.erase("mined_goal")
	expect(not Summary.instructions(state,"landfall").replaces_supply_ledger,
		"an incomplete Fire quota cannot hide required supply work")
	state.shelves.erase("fire")
	state.shelves.objectives = [{"id":"kelp","label":"Secure Kelp","current":100,"target":400},
		{"id":"cress","label":"Secure Watercress","current":50,"target":200}]
	state.shelves.water = {"stage":"water_cutters","command":"work","workers":[],
		"stored":{"kelp":100,"cress":50},"bins":{"kelp":20,"cress":10},"cut":{"kelp":135,"cress":65},
		"goals":{"kelp":800,"cress":400},"field_hint":"Protect the cutters and Ada along the loading route."}
	state.hint = state.shelves.water.field_hint
	detail = Summary.instructions(state,"landfall")
	expect(ledger_value(detail,"Kelp secured") == "100 / 400" and ledger_value(detail,"Watercress secured") == "50 / 200",
		"Water preserves two production contracts and ignores inflated legacy wire goals")
	expect(ledger_value(detail,"At loading point") == "20 Kelp · 10 Watercress" \
		and ledger_value(detail,"In workers' bags") == "15 Kelp · 5 Watercress",
		"native allocated totals separate loading bins and actual typed worker cargo")
	expect(detail.replaces_supply_ledger,"both complete Water goal rows can replace its production ledger")
	state.shelves.water.erase("cut")
	expect(ledger_value(Summary.instructions(state,"landfall"),"In workers' bags").is_empty(),
		"missing allocation metadata does not invent zero or untyped worker cargo")
	state.shelves.water.cut = {"kelp":100,"cress":65}
	expect(ledger_value(Summary.instructions(state,"landfall"),"In workers' bags").is_empty(),
		"inconsistent allocated metadata is not clamped into a false bag count")
	state.shelves.objectives.remove_at(1)
	expect(not Summary.instructions(state,"landfall").replaces_supply_ledger,
		"a missing Water production contract keeps the existing full checklist")
	state.shelves.water.merge({"stage":"water_barge","hull":0,"landing":1,
		"field_hint":"Repair the hull with Wood Planks before ordering Sail."},true)
	state.hint = state.shelves.water.field_hint
	detail = Summary.instructions(state,"landfall")
	expect(detail.text == state.hint and not detail.replaces_supply_ledger,
		"barge material requirements and specialized controls remain in their original instructions")
	state.shelves.phase = "report"
	expect(Summary.instructions(state,"landfall").ledger.is_empty(),"reporting shows no stale harvesting ledger")
	state.shelves.phase = "work"; state.active = false
	expect(Summary.instructions(state,"landfall").note.is_empty(),"paused workers cannot advertise a local recovery lesson")
	var generic := {"kind":"rescue","active":true,"hint":"Stay with Elen and Liora until they reach safety."}
	detail = Summary.instructions(generic,"landfall_insides")
	expect(detail.text == generic.hint and detail.ledger.is_empty() and not detail.replaces_supply_ledger,
		"rescue and generic quest Instructions keep their exact objective and existing specialized controls")

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	inline_instructions()
	var state := supplies()
	var original := JSON.stringify(state)
	var summary := Summary.campaign(state,"landfall")
	expect(summary.objective == "Protect the Sage harvesters" and summary.counter == "Sage secured · 1,200 / 10,000",
		"the current field names its action and counts actual delivered Sage")
	expect(is_equal_approx(float(summary.progress),0.12),"bags do not inflate delivery progress")
	expect(summary.cargo == "In workers' bags · 800 Sage", "the slim card separates native carried Sage from secured delivery progress")
	var wire_state: Dictionary = JSON.parse_string(JSON.stringify(state))
	expect(Summary.campaign(wire_state,"landfall").cargo == summary.cargo,
		"whole native JSON numbers retain the carried readout after packet decoding")
	for unknown: Variant in [null,-1,2.5,"800"]:
		var invalid_cargo := {"cargo":""}; Summary._cargo(invalid_cargo,{"carried":unknown},"Sage")
		expect(invalid_cargo.cargo.is_empty(),"unknown, negative or fractional cargo cannot invent carried stock")
	var no_cargo := state.duplicate(true); no_cargo.shelves.growers.erase("carried")
	expect(Summary.campaign(no_cargo,"landfall").cargo.is_empty(),"older snapshots without a bag total omit the extra row")
	no_cargo.shelves.growers.carried = 0
	expect(Summary.campaign(no_cargo,"landfall").cargo.is_empty(),"empty bags keep the gameplay card compact")
	no_cargo.shelves.growers.carried = 800; no_cargo.active = false
	expect(Summary.campaign(no_cargo,"landfall").cargo.is_empty(),"a suspended encounter does not advertise local carried cargo")
	expect(summary.ribbon_counter == "1,200 / 10k", "the ribbon drops descriptive text while retaining exact receipt counts")
	expect(summary.ribbon_objective == "Guard Sage crew", "the Sage ribbon preserves its action in a short field-specific label")
	expect(summary.urgent and summary.alert.contains("Nell") and summary.recovery.actor_id == 401,
		"a fallen worker keeps the exact existing Heal Target identity")
	expect(summary.secondary == "Crew 1 / 2", "compact crew status keeps the actual standing count")
	expect(summary.full_objective == state.hint and JSON.stringify(state) == original,
		"the complete authored instruction and original quest state remain unchanged")
	var changed_goal := state.duplicate(true); changed_goal.shelves.objectives[0].target = 20000
	expect(Summary.campaign(changed_goal,"landfall").counter == "Sage secured · 1,200 / 20,000",
		"a changed native shipment goal replaces any historical production quantity")
	changed_goal.shelves.objectives[0].target = 12500
	expect(Summary.campaign(changed_goal,"landfall").ribbon_counter == "1,200 / 12,500",
		"nonwhole thousands remain exact rather than becoming rounded progress")
	changed_goal.shelves.objectives = []
	expect(Summary.campaign(changed_goal,"landfall").progress == -1.0,
		"a missing native goal never invents an overall progress percentage")
	var remote := Summary.campaign(state,"landfall_town")
	expect(not remote.urgent and remote.recovery.is_empty() and remote.cargo.is_empty(),"a worker on another map cannot offer local healing or carried cargo")
	state.travel = {"map":"landfall_town","npc":"Ilka Tarn","label":"The True Note", "route":"Return to The True Note with your delivery."}
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Speak with Ilka Tarn" and summary.progress == -1.0 \
		and not summary.urgent and summary.recovery.is_empty() and summary.cargo.is_empty(), "travel leads over stale field counters, bags and downed workers")
	expect(summary.full_objective == Readout.instructions(state),"the entire travel route is retained for details")
	state.erase("travel")
	state.party = {"waiting_for_scene":true}
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective.contains("Wait for the party") and summary.recovery.is_empty() and summary.cargo.is_empty(),"a party scene barrier does not prompt unavailable work or bags")
	state.erase("party")
	state.shelves.growers.field = "root"; state.shelves.growers.stored.root = 1250
	summary = Summary.campaign(state,"landfall")
	expect(summary.counter == "Hearthroot secured · 1,250 / 5,000" and is_equal_approx(float(summary.progress),0.25),
		"the next field uses its own native storage and goal")
	expect(summary.ribbon_objective == "Guard Hearthroot crew", "the next field keeps its own crop identity in the ribbon")
	expect(summary.cargo == "In workers' bags · 800 Hearthroot", "the next field names the actual carried crop")
	state.shelves.erase("growers")
	state.shelves.objectives = [{"id":"secured","label":"Secure Coal","current":20,"target":300},
		{"id":"machinery","label":"Protect three lift repairs","current":1,"target":3}]
	state.shelves.fire = {"stage":"fire_coal","step":"repair","route":"lift","recovered":20,"mined":0,"recovered_goal":100,"mined_goal":200,"carried":99,"workers":[]}
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Protect three lift repairs" and summary.counter == "Progress · 1 / 3",
		"lift preparations lead over a future shipment goal")
	expect(summary.ribbon_objective.is_empty(),"unmapped lift instructions remain intact for the ordinary objective fallback")
	expect(summary.cargo.is_empty(),"lift preparation does not advertise future extraction bags")
	state.shelves.fire.step = "extract"; state.shelves.fire.mined = 40; state.shelves.fire.carried = 99
	state.shelves.fire.field_hint = "Protect the miners and both hauling paths. Heal Target revives a fallen worker."
	state.hint = state.shelves.fire.field_hint
	summary = Summary.campaign(state,"landfall")
	expect(summary.counter == "Coal secured · 60 / 300" and is_equal_approx(float(summary.progress),0.2),
		"Fire shipment progress uses recovered and mined receipts, not bags")
	expect(summary.objective == "Protect miners and hauling paths" and summary.full_objective == state.hint,
		"Fire extraction uses a bounded action without trimming or replacing the source instructions")
	expect(summary.ribbon_objective == "Guard Coal crew", "the Coal extraction ribbon uses a compact action for its actual resource")
	expect(summary.cargo == "In workers' bags · 99 Coal", "Coal bags remain visible while the secured counter waits for delivery")
	state.shelves.fire.carried = 240
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Guard the final Coal delivery" and summary.ribbon_counter == "60 / 300",
		"actually allocated final Coal bags change the action but never inflate secured progress")
	expect(summary.ribbon_objective == "Guard final Coal load", "the final-load ribbon names delivery rather than implying more mining")
	expect(summary.cargo == "In workers' bags · 240 Coal" and is_equal_approx(float(summary.progress),0.2),
		"a full final load remains in transit rather than becoming secured progress")
	var quarry := state.duplicate(true); quarry.shelves.fire.stage = "fire"
	expect(Summary.campaign(quarry,"landfall").cargo == "In workers' bags · 240 Flint", "quarry hauling uses the native Flint resource identity")
	state.shelves.fire.hazards = [{"kind":"warning"}]; state.shelves.fire.stage = "fire_sapper"
	summary = Summary.campaign(state,"landfall")
	expect(summary.urgent and summary.alert.contains("BLAST"),"an actual blast warning retains the shared urgent instruction")
	expect(summary.cargo.is_empty(),"the sapper stage cannot retain an old extraction bag readout")
	state.shelves.erase("fire")
	state.shelves.water = {"stage":"water_cutters","command":"wait","stored":{"kelp":100,"cress":50},
		"goals":{"kelp":800,"cress":400},"cut":{"kelp":700,"cress":300},"bins":{"kelp":600,"cress":250},"workers":[]}
	state.shelves.water.field_hint = "The crew is holding position. Order Work at the crew station when ready."
	state.hint = state.shelves.water.field_hint
	state.shelves.objectives = [{"id":"kelp","label":"Secure Kelp","current":100,"target":400},
		{"id":"cress","label":"Secure Watercress","current":50,"target":200}]
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Order Work at the crew station" and summary.counter == "Kelp secured · 100 / 400" \
		and is_equal_approx(float(summary.progress),0.25), "Water respects current orders, secured bags and the actual production goal")
	expect(summary.ribbon_objective == "Order Work", "the waiting ribbon names the command rather than claiming workers are gathering")
	state.shelves.water.command = "regroup"
	expect(Summary.campaign(state,"landfall").objective == "Meet crew; then order Work",
		"regroup names the meeting step before the next native work order")
	expect(Summary.campaign(state,"landfall").ribbon_objective == "Meet the crew", "the regroup ribbon names the immediate meeting action")
	state.shelves.water.command = "work"; state.shelves.water.cut = {"kelp":300,"cress":200}
	state.shelves.water.field_hint = "Protect the cutters and Ada along the loading route. Heal Target gets a fallen worker back on her feet."
	state.hint = state.shelves.water.field_hint
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Protect cutters and Ada's route" and summary.full_objective == state.hint,
		"Water work has one bounded action while full instructions remain exact")
	expect(summary.ribbon_objective == "Guard cutters", "the work ribbon keeps its current guard action short")
	state.shelves.water.cut.kelp = 400
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Guard the final delivery route" and summary.counter == "Kelp secured · 100 / 400",
		"fully allocated Kelp and Watercress switch to guarding delivery without counting bins as secured")
	expect(summary.ribbon_objective == "Guard final delivery", "the final Water ribbon indicates hauling instead of more cutting")
	state.shelves.water.erase("cut")
	expect(Summary.campaign(state,"landfall").objective == "Protect cutters and Ada's route",
		"older snapshots without allocation metadata do not invent a final delivery")
	state.shelves.water.stored.kelp = 400
	summary = Summary.campaign(state,"landfall")
	expect(summary.counter == "Watercress secured · 50 / 200", "the remaining required crop becomes the primary counter")
	state.shelves.water.workers = [{"actor_id":501,"name":"Ada","health":1,"downed":true}]
	summary = Summary.campaign(state,"landfall")
	expect(summary.urgent and summary.alert.contains("Ada") and summary.recovery.actor_id == 501,
		"bounded Water objectives preserve the exact urgent alert and existing patient identity")
	state.shelves.water.workers = []
	state.shelves.water.merge({"stage":"water","route":"repair","field_hint":"Balance Fresh 2, Tide 1, Drain 0, then Test the channels."},true)
	expect(Summary.campaign(state,"landfall").objective == state.shelves.water.field_hint,
		"Water repair settings are preserved in full rather than being generically shortened")
	state.shelves.water.merge({"stage":"water_barge","hull":0,"landing":1,
		"field_hint":"Repair the hull with Wood Planks before ordering Sail."},true)
	expect(Summary.campaign(state,"landfall").objective == state.shelves.water.field_hint,
		"barge blockers and their Wood Plank requirements remain intact")
	state.shelves.erase("water")
	state.shelves.objectives = [{"id":"orc","label":"Defeat the raiders' leader","current":0,"target":1}]
	state.targets = [{"id":"storage","label":"Personal supply cache","enabled":true}]
	summary = Summary.campaign(state,"landfall")
	expect(summary.objective == "Defeat the raiders' leader" and summary.counter.is_empty() and summary.progress == -1.0,
		"an optional cache and nonrequired pack kills do not replace the actual raid objective")
	expect(summary.ribbon_counter.is_empty(),"switching to a single-action objective clears an earlier ribbon counter")
	var guide := {"title":"The Palace Grove","hint":"Click an olive bush once.","item":"Olive","count":2,"required":5,"stage":2,"total":10}
	summary = Summary.guide(guide)
	expect(summary.objective == guide.hint and summary.counter == "Olive · 2 / 5" and is_equal_approx(float(summary.progress),0.4),
		"standard tutorials use actual item counts rather than chapter position")
	guide.required = 1
	expect(Summary.guide(guide).counter.is_empty() and Summary.guide(guide).progress == -1.0,
		"a single interaction does not acquire a misleading overall quest percentage")
	var evidence := OS.get_environment("RL_TRACKER_SUMMARY_EVIDENCE")
	if not evidence.is_empty():
		var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(evidence))
		var records: Array = raw.get("records",[]) if raw is Dictionary else raw
		for record: Dictionary in records:
			var native: Dictionary = record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type == "campaign","current native tracker state decodes")
			if decoded.type != "campaign": continue
			var source: Dictionary = decoded.state
			var before := JSON.stringify(source)
			summary = Summary.campaign(source,str(source.map))
			expect(summary.full_objective == Readout.instructions(source) and JSON.stringify(source) == before,
				"native compact presentation preserves complete instructions and authoritative state")
			expect(float(summary.progress) >= -1.0 and float(summary.progress) <= 1.0 and not str(summary.objective).is_empty(),
				"native compact summary has an actionable instruction and a bounded real counter")
			expect(str(summary.counter).is_empty() == str(summary.ribbon_counter).is_empty(),
				"native ribbon counters exist only when a real descriptive counter exists")
			var ledger: Dictionary = source.get("shelves",{})
			var production: Dictionary = ledger.get("fire",ledger.get("growers",{}))
			var extraction := str(production.get("stage","")) in ["fire","fire_coal"] and str(production.get("step","")) == "extract"
			var field := ledger.has("growers") and not bool(production.get("raid",false))
			if bool(source.get("active",false)) and str(ledger.get("phase","")) == "work" \
					and (source.get("travel",{}) as Dictionary).is_empty() and (extraction or field) and int(production.get("carried",0)) > 0:
				expect(not str(summary.cargo).is_empty(),"actual native Life/Fire carried bags remain visible after decoder normalization")
			var detail := Summary.instructions(source,str(source.map))
			expect(detail.text == Readout.instructions(source) and JSON.stringify(source) == before,
				"native inline Instructions retain exact instructions without quest mutations")
			for row: Dictionary in detail.ledger:
				expect(row.label is String and row.value is String and not str(row.value).is_empty(),
					"native inline ledger consists only of readable passive values")
			if not (source.get("travel",{}) as Dictionary).is_empty():
				expect(summary.recovery.is_empty() and not summary.urgent and summary.progress == -1.0,
					"native travel never displays suspended encounter actions or shipment progress")
				expect(detail.ledger.is_empty() and detail.note.is_empty() and not detail.replaces_supply_ledger,
					"native travel leaves its suspended field ledger and recovery note hidden")
	print("Quest tracker summary: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)

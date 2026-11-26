extends SceneTree
const Contracts := preload("res://tests/test_landfall_contracts.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
const Recovery := preload("res://src/ui/campaign_ally_recovery.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)

static func journey(map_id := "pinebrow") -> Dictionary:
	return {"version":3,"map":map_id,"tile":[128,128],"label":"Orchard relief route",
		"description":"The orchard crew needs safe passage. Meet them at the marked route and stay together.",
		"objective":"I will stay with the crew and clear each threat along the marked route."}

static func packet(map_id := "pinebrow") -> Dictionary:
	var board := Contracts.board_state()
	var row := Contracts.offer("melee"); row.journey = journey(map_id)
	row.location = {"map":map_id,"tile":[128,128],"label":"Orchard relief route"}
	board.accepted = [row]; board.current = row
	var state := Contracts.snapshot(board); state.map = map_id
	state.travel = {"map":map_id,"tile":[128,128],"label":"Meet the orchard crew",
		"markers":[{"map":map_id,"tile":[128,128],"label":"Orchard relief route"}],
		"via":[{"map":"landfall_town","tile":[101,85],"label":"Leave the watch house"}]}
	return state

static func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	expect(EloriaProtocol.CONTRACT_JOURNEYS_CAPABILITY in EloriaProtocol.CLIENT_CAPABILITIES,
		"the client advertises regional daily travel support")
	expect("landfall_contracts_difficulty_v1" in EloriaProtocol.CLIENT_CAPABILITIES,
		"older difficulty servers still recognize the client")
	var document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	var published := 0
	for map_id: String in document.maps:
		if str(document.maps[map_id].get("status", "")) != "continent-v2-served": continue
		published += 1
		var state := packet(map_id)
		expect(decode(state).type == "campaign", "published contract destination decodes: "+map_id)
		var pins := Guidance.navigation_targets(state,map_id,true)
		expect(pins.size() == 1 and pins[0].label == "Orchard relief route",
			"regional navigation keeps the named quest marker: "+map_id)
		expect(Guidance.navigation_targets(state,map_id,false).is_empty(),"untracking hides regional pins: "+map_id)
	expect(published == 17,"the exercised regions are the published continent-v2 exteriors")
	var state := packet()
	expect(Guidance.navigation_targets(state,"landfall_town",true)[0].tile == [101,85],
		"the route shows the actual intermediate doorway on the current map")
	state.travel.markers[0].map = "./maps/continent-v2/pinebrow.elm"
	expect(decode(state).type == "campaign","registered region pins preserve legacy filename normalization")
	for map_id: String in ["unknown_region","landfall_contract_private","mirrorhold","serpent_deep_descent","PiNeBrOw"]:
		state = packet(); state.travel.markers[0].map = map_id
		expect(decode(state).get("error") == "campaign_travel_markers","unpublished or unrelated marker is rejected: "+map_id)
		state = packet(); state.travel.via[0].map = map_id
		expect(decode(state).get("error") == "campaign_travel_via","unpublished or unrelated route hop is rejected: "+map_id)
	state = packet(); state.kind = "shelves"; state.active = false; state.erase("contracts")
	expect(decode(state).get("error") == "campaign_travel_markers","regional daily support does not broaden shelves travel pins")
	state.erase("travel"); state.map = "landfall"
	expect(decode(state).type == "campaign","the inactive local shelves fixture is otherwise valid")
	state.map = "pinebrow"
	expect(decode(state).get("error") == "campaign_shelves_map","shelves root map remains confined to its existing maps")
	for value: Variant in [null,{},[1,2],{"version":2},journey("unknown_region")]:
		var row := Contracts.offer("melee"); row.journey = value
		expect(not EloriaProtocol.ContractsProtocol.row(row),"malformed or unregistered optional journey is rejected")
	for field: String in ["description","objective","label"]:
		var row := Contracts.offer("melee"); row.journey = journey(); row.journey[field] = ""
		expect(not EloriaProtocol.ContractsProtocol.row(row),"journey requires readable "+field)
	var row := Contracts.offer("melee"); row.journey = journey(); row.journey.tile = [-1,128]
	expect(not EloriaProtocol.ContractsProtocol.row(row),"negative regional coordinates are rejected")
	row.journey.tile = [2048,128]
	expect(not EloriaProtocol.ContractsProtocol.row(row),"regional coordinates keep the navigation bound")
	expect(EloriaProtocol.ContractsProtocol.row(Contracts.offer("melee")),"accepted legacy assignments remain valid without a journey")
	state = packet(); state.key = "magic"
	row = Contracts.offer("magic"); row.template_id = "healing_line"; row.quest_id = 1102
	row.journey = journey(); row.status = "work"
	row.objectives = [{"id":"stages","label":"Secure the camp","current":3,"target":3},
		{"id":"healing","label":"Help the crew recover","current":10,"target":10},
		{"id":"practice","label":"Use effective magic","current":0,"target":5}]
	state.contracts.current = row; state.contracts.accepted = [row]; state.contracts.tracked_id = row.id
	state.run_id = row.id; state.title = row.title
	state.contracts.encounter = {"phase":"complete","stage":"3","waves":3,"workers":[
		{"actor_id":20,"name":"Wounded warden","health":25,"max_health":50,"downed":false}]}
	state.erase("travel")
	expect(Recovery.patients(state,"pinebrow").size() == 1,"shared recovery can finish while a caster still uses paid healing for personal contribution")
	row.objectives[2].current = 5; row.status = "ready"
	expect(Recovery.patients(state,"pinebrow").is_empty(),"completed magic goals do not invent another postbattle healing task")
	row.erase("journey"); row.status = "work"; state.map = "landfall"
	row.objectives = [{"id":"healing","label":"Restore crew health","current":0,"target":40}]
	expect(Recovery.patients(state,"landfall").size() == 1,"legacy personal-healing Triage patients remain available")
	var native := OS.get_environment("RL_CONTRACTS_JOURNEYS_NATIVE")
	if not native.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(native))
		for record: Dictionary in records:
			var dto: Dictionary = record.get("snapshot",record)
			var decoded := decode(dto)
			expect(decoded.type in ["campaign","contracts_board"],"actual regional server packet decodes: "+str(record.get("label",""))+" "+str(decoded.get("error","")))
			if decoded.type not in ["campaign","contracts_board"]: continue
			var current: Dictionary = (dto.get("contracts",{}) as Dictionary).get("current",{})
			var encounter: Dictionary = (dto.get("contracts",{}) as Dictionary).get("encounter",{})
			if str(current.get("template_id","")) == "healing_line" and str(encounter.get("phase","")) == "complete":
				var remaining: bool = (current.get("objectives",[]) as Array).any(func(goal: Dictionary) -> bool:return str(goal.id) in ["healing","practice"] and int(goal.current) < int(goal.target))
				var wounded: bool = (encounter.get("workers",[]) as Array).any(func(worker: Dictionary) -> bool:return int(worker.health) > 0 and int(worker.health) < int(worker.max_health))
				if wounded:
					var has_patients := not Recovery.patients(dto,str(dto.map)).is_empty()
					expect(has_patients == remaining,
						"actual postbattle Triage keeps patients only while shared recovery or personal magic remains")
	print("Contract journeys: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

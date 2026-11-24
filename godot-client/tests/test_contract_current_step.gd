extends SceneTree
const Contracts := preload("res://tests/test_landfall_contracts.gd")
const Codec := preload("res://src/network/contracts_protocol.gd")
const Summary := preload("res://src/ui/quest_tracker_summary.gd")
const Readout := preload("res://src/ui/campaign_field_readout.gd")
const Recovery := preload("res://src/ui/campaign_ally_recovery.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)
func settle() -> void:
	for frame: int in 8: await process_frame

static func mixing_row() -> Dictionary:
	var row := Contracts.offer("alchemy")
	row.template_id = "alchemy_reagents"; row.quest_id = 1110; row.status = "work"
	row.objectives = [{"id":"reagents","label":"Gather fresh Sage","current":10,"target":10},
		{"id":"mix","label":"Mix fresh Life Essences","current":0,"target":10}]
	row.next_step = {"objective_id":"mix","action":"Mix 10 Life Essences","detail":"Take your fresh ingredients to The True Note and mix successful Life Essence batches.",
		"location":{"map":"landfall_town","tile":[178,26],"label":"The True Note"},"current":0,"target":10}
	row.preparation = {"ready":false,"reason":"Bring a Mortar and Pestle before mixing.","checks":[
		{"label":"Life Essence recipe","ready":true,"detail":"Learned"},
		{"label":"Mortar and Pestle","ready":false,"detail":"Missing from your pack"}]}
	return row

static func snapshot(row: Dictionary) -> Dictionary:
	var board := Contracts.board_state(); board.current = row; board.accepted = [row]; board.offers = []
	board.tracked_id = str(row.id)
	var value := Contracts.snapshot(board); value.run_id = str(row.id); value.key = str(row.skill)
	value.map = "landfall_town"; value.available = true
	return value

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var app: Node = root.get_node("AppState"); app.authenticated = true; app.current_map = "landfall_town"
	var row := mixing_row(); var value := snapshot(row); var original := JSON.stringify(value)
	expect(Codec.valid(value.contracts),"current-step location, proof counter and preparation have a valid bounded shape")
	var invalid: Dictionary = value.contracts.duplicate(true); invalid.current.next_step.target = -1
	expect(not Codec.valid(invalid),"negative current-step goals are rejected")
	invalid = value.contracts.duplicate(true); invalid.current.next_step.location.tile = [1,2,3]
	expect(not Codec.valid(invalid),"current-step destinations require exactly two coordinates")
	invalid = value.contracts.duplicate(true); invalid.current.next_step.objective_id = "bad\nproof"
	expect(not Codec.valid(invalid),"proof identity cannot contain control characters")
	invalid = value.contracts.duplicate(true); invalid.current.preparation.checks.resize(9)
	expect(not Codec.valid(invalid),"preparation is bounded to eight checks")
	invalid = value.contracts.duplicate(true); invalid.current.preparation.ready = "yes"
	expect(not Codec.valid(invalid),"preparation readiness remains a server boolean")
	expect(Codec.valid(Contracts.board_state()),"older contracts without the additive guidance fields remain compatible")
	var summary := Summary.campaign(value,"landfall_town")
	expect(summary.objective == str(row.next_step.action) and summary.counter.contains("0 / 10"),"the slim card uses the actual mixing step instead of the completed gathering objective")
	expect(Readout.instructions(value) == str(row.next_step.detail),"journal and foldout share the authoritative current instructions")
	var instructions := Summary.instructions(value,"landfall_town")
	expect(instructions.guidance == str(row.preparation.reason) and (instructions.ledger as Array).any(func(item: Dictionary) -> bool:return item.label == "Essentials · Mortar and Pestle" and item.value == "Missing from your pack"),"Instructions names the missing essential while retaining its objective ledger")
	var explained := snapshot(mixing_row()); explained.contracts.current.next_step.detail = str(row.preparation.reason)+" Then return to the worksite."
	expect(Summary.instructions(explained,"landfall_town").guidance.is_empty(),"a preparation reason already given in the current instructions is not repeated below it")
	var board: Control = load("res://src/ui/contracts_board.gd").new(); root.add_child(board); await settle()
	board.apply_state(value.contracts); board.tabs.current_tab = 1; await settle()
	var labels: Array = board.columns.Accepted.find_children("*","Label",true,false)
	expect(labels.any(func(label: Label) -> bool:return label.text == "Where · The True Note") and labels.any(func(label: Label) -> bool:return label.text == "Next · Mix 10 Life Essences"),"the Accepted board advances from the original Sage patch to the real mixing destination")
	expect(labels.any(func(label: Label) -> bool:return label.text == "Prepare · Mortar and Pestle"),"the board shows a concise essentials blocker")
	var preview := mixing_row(); preview.status = "offer"; preview.eligible = false
	preview.reason = str(preview.preparation.reason); preview.preparation.checks = []
	var preview_board: Dictionary = value.contracts.duplicate(true); preview_board.offers = [preview]
	board.apply_state(preview_board); await settle()
	var preview_labels: Array = board.columns.Available.get_child(0).find_children("*","Label",true,false)
	var reason_index := preview_labels.find_custom(func(label: Label) -> bool:return label.text == str(preview.reason))
	var description_index := preview_labels.find_custom(func(label: Label) -> bool:return label.text == str(preview.description))
	expect(reason_index >= 0 and reason_index < description_index and preview_labels.filter(func(label: Label) -> bool:return label.text == str(preview.reason)).size() == 1,"locked offer blockers appear near the title without repeating the same preparation reason")
	root.size = Vector2i(800,600); board._fit(); await settle()
	expect(root.get_visible_rect().encloses(board.panel.get_global_rect()),"the preparation board remains bounded in a small window")
	board.panel.hide()
	var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
	var requests: Array = []; hud.action_requested.connect(func(action: String) -> void: requests.append(action))
	hud.apply_state(value,Vector2i(178,26),"landfall_town")
	hud._entry.pressed.emit()
	expect(hud._entry.disabled and requests.is_empty() and hud._entry.tooltip_text == str(row.preparation.reason),"missing essentials explain and block Start without issuing a request")
	row.preparation.ready = true
	for check: Dictionary in row.preparation.checks: check.ready = true
	row.preparation.reason = ""; value = snapshot(row)
	hud.apply_state(value,Vector2i(178,26),"landfall_town"); hud._entry.pressed.emit()
	expect(not hud._entry.disabled and requests == ["contract_begin"],"prepared work keeps the existing explicit Start action")
	var stock := mixing_row(); stock.template_id = "alchemy_stock"; stock.quest_id = 1111
	stock.status = "ready"; stock.eligible = false; stock.reason = "Bring ordinary Life Essence for the handover."
	stock.next_step.objective_id = "handover_0"; stock.next_step.action = "Prepare 3 ordinary Life Essence"
	stock.next_step.detail = "Mix or retrieve ordinary stock. Enriched essences are kept."; stock.next_step.target = 3
	stock.objectives = [{"id":"mix","label":"Mix fresh Life Essences","current":10,"target":10},
		{"id":"handover_0","label":"Bring ordinary Life Essence","current":0,"target":3}]
	var missing := snapshot(stock); missing.available = false
	summary = Summary.campaign(missing,"landfall_town")
	expect(summary.objective == "Prepare 3 ordinary Life Essence" and summary.counter.contains("0 / 3"),"earned mixing proof does not falsely tell a player with missing ordinary stock to report")
	board.apply_state(missing.contracts); await settle()
	var reports: Array = board.columns.Accepted.find_children("*","Button",true,false).filter(func(button: Button) -> bool:return button.text == "Report contract")
	expect(reports.size() == 1 and reports[0].disabled,"the ordinary-stock blocker keeps the native report disabled")
	app.contracts_board = missing.contracts; app.quest_journal.clear()
	var journal: Control = load("res://src/ui/extension_windows.gd").new(); root.add_child(journal); await settle()
	journal._sync_quests()
	expect(journal._quest_entries.size() == 1 and not journal._quest_entries[0].ready and str(journal._quest_entries[0].objective).begins_with(str(stock.next_step.detail)),"the actual quest journal shows current instructions and does not mark missing ordinary stock report-ready")
	stock.objectives[1].current = 3
	app.contracts_board = snapshot(stock).contracts; journal._sync_quests()
	expect(journal._quest_entries[0].ready and not stock.eligible,"restocked goods mark the real journal report-ready even far from Batu")
	var survey := Contracts.offer("harvesting"); survey.template_id = "harvest_survey"; survey.quest_id = 1109; survey.status = "work"
	survey.objectives = [{"id":"gather","label":"Gather fresh Sage","current":100,"target":150},
		{"id":"sites","label":"Sample different Sage nodes","current":1,"target":3}]
	survey.next_step = {"objective_id":"gather","action":"Gather fresh Sage","detail":"Gather the remaining quota and sample new nodes.","location":survey.location,"current":100,"target":150}
	summary = Summary.campaign(snapshot(survey),"landfall_town")
	expect(summary.counter.contains("100 / 150") and summary.secondary == "Samples 1 / 3","survey sample progress stays visible alongside the gathering quota")
	survey.next_step.objective_id = "sites"; survey.next_step.current = 1; survey.next_step.target = 3
	survey.next_step.action = "Sample two new Sage nodes"
	summary = Summary.campaign(snapshot(survey),"landfall_town")
	expect(summary.counter.contains("1 / 3") and summary.secondary.is_empty(),"sampling becomes the main counter without duplicating a secondary count")
	var triage := Contracts.offer("magic"); triage.template_id = "healing_line"; triage.quest_id = 1102; triage.status = "work"
	triage.objectives = [{"id":"healing","label":"Restore real crew health","current":5,"target":20}]
	var recovery := snapshot(triage); recovery.map = "landfall"
	recovery.contracts.encounter = {"phase":"complete","stage":"3","waves":3,"workers":[
		{"actor_id":501,"name":"Wounded warden","health":55,"max_health":80,"downed":false},
		{"actor_id":502,"name":"Healthy warden","health":80,"max_health":80,"downed":false},
		{"actor_id":503,"name":"Fallen warden","health":0,"max_health":80,"downed":true}]}
	var patients := Recovery.patients(recovery,"landfall")
	expect(patients.size() == 2 and patients[0].actor_id == 503 and patients[1].actor_id == 501 and patients[1].wounded,"postbattle triage offers both valid patients with fallen allies first")
	recovery.contracts.encounter.workers.pop_back()
	summary = Summary.campaign(recovery,"landfall")
	expect(summary.recovery.actor_id == 501 and not summary.urgent and summary.alert.is_empty(),"living wounded crew get a recovery control without a false downed warning")
	hud.apply_state(recovery,Vector2i(64,249),"landfall")
	expect(hud._recovery_actions.get_child_count() == 1 and hud._recovery_actions.get_child(0).tooltip_text.contains("wounded ally"),"triage retains normal paid Heal Target instructions")
	expect(Recovery.patients(recovery,"landfall_town").is_empty(),"remote triage patients cannot be selected by the shortcut")
	triage.objectives[0].current = 20
	expect(Recovery.patients(recovery,"landfall").is_empty(),"living patients leave the shortcut when personal healing proof is complete")
	triage.objectives[0].current = 5; triage.template_id = "wardens_call"; triage.quest_id = 1091
	expect(Recovery.patients(recovery,"landfall").is_empty(),"other completed encounter templates do not gain triage-only living patients")
	expect(JSON.stringify(snapshot(mixing_row())) == original,"rendering and readiness controls never fabricate proof or alter authoritative guidance")
	var native_path := OS.get_environment("RL_CONTRACTS_NATIVE")
	if not native_path.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(native_path))
		for record: Dictionary in records:
			var dto: Dictionary = record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(dto).to_utf8_buffer())
			expect(decoded.type in ["campaign","contracts_board"],"native guidance packet decodes: "+str(record.get("label",""))+" "+str(decoded.get("error","")))
			var current := Codec.current(dto); var step: Dictionary = current.get("next_step",{})
			if not step.is_empty():
				expect(Summary.campaign(dto,str(dto.map)).objective == str(step.action),"native compact action matches the current authoritative step")
			if str(current.get("template_id","")) == "alchemy_stock" and str(current.get("status","")) == "ready":
				var waiting := (current.objectives as Array).any(func(goal: Dictionary) -> bool:return str(goal.id).begins_with("handover_") and int(goal.current) < int(goal.target))
				expect(bool(journal._contract_journal(current).ready) == not waiting,"native handover inventory, rather than contact eligibility, controls the journal's ready presentation")
			if str(record.get("label","")) == "board.private_melee_other_work":
				board.apply_state(dto.contracts,false); await settle()
				for accepted: Dictionary in dto.contracts.accepted:
					if str(accepted.id) == str(dto.run_id): continue
					var panels: Array = board.columns.Accepted.get_children().filter(func(panel: Node) -> bool:return str(panel.get_meta("contract_skill","")) == str(accepted.skill))
					var shown: Array = panels[0].find_children("*","Label",true,false)
					expect(shown.any(func(label: Label) -> bool:return label.text == "Next · "+str(accepted.next_step.action)) and shown.any(func(label: Label) -> bool:return label.text == "Where · "+str(accepted.next_step.location.label)),"other accepted work retains its own native action and destination while a patrol is active")
	hud.queue_free(); board.queue_free(); journal.queue_free(); await settle()
	print("Contract current step: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

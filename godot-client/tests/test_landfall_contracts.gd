extends SceneTree
const Codec := preload("res://src/network/contracts_protocol.gd")
const Board := preload("res://src/ui/contracts_board.gd")
const Summary := preload("res://src/ui/quest_tracker_summary.gd")
const Recovery := preload("res://src/ui/campaign_ally_recovery.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)

static func offer(skill: String) -> Dictionary:
	return {"id":"daily_"+skill,"quest_id":1090+Codec.SKILLS.find(skill),"skill":skill,"title":skill.capitalize()+" for Landfall",
		"description":"Complete the marked assignment, then return to Batu Ensh.","route":"road","tier":"Tier1","status":"accepted",
		"eligible":true,"reason":"","can_reroll":true,"reroll_reason":"",
		"objectives":[{"id":"proof","label":"Demonstrate your skill","current":0,"target":10}],
		"reward":{"xp":{skill:500},"gold":300,"marks":1,"items":[]},"location":{"map":"landfall","tile":[64,249],"label":"Landfall worksite"}}

static func board_state() -> Dictionary:
	var offers: Array = []
	for skill: String in Codec.SKILLS: offers.append(offer(skill))
	return {"version":1,"revision":7,"day":"2026-11-24","reset_at":1795564800,"accepted_limit":3,"tracked_id":"daily_melee","marks":4,"open":true,
		"weekly":{"count":2,"target":5,"awarded":false,"bonus_marks":3},"offers":offers,"accepted":[offer("melee")],"catalog":[],
		"joins":[{"owner":"Friend","title":"Magic for Landfall","eligible":true,"reason":""}]}

static func snapshot(board: Dictionary, board_only := false) -> Dictionary:
	return {"version":1,"kind":"contracts","active":not board_only,"available":false,"started":true,"completed":false,
		"title":"Melee for Landfall","hint":"Complete your contract.","map":"landfall","run_id":"daily_melee" if not board_only else "",
		"key":"melee","stage":"work","targets":[],"actors":{},"scene":{},"contracts":board,"board_only":board_only}

static func expanded_board(skill := "melee") -> Dictionary:
	var value := board_state(); value.offers = []
	for template: String in Codec.TEMPLATES:
		var binding: Array = Codec.TEMPLATES[template]
		if str(binding[0]) != skill: continue
		for route: String in ["standard","bold"]:
			var row := offer(str(binding[0])); row.id = template+"_"+route
			row.template_id = template; row.quest_id = int(binding[1]); row.route = route
			row.route_label = route.capitalize()+" terms"; row.title = template.replace("_"," ").capitalize()
			value.offers.append(row)
	value.reset_token = 0; value.reset_skills = []; value.offer_skill = skill; value.offer_total = 60
	return value

func settle() -> void:
	for frame: int in 5: await process_frame

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	expect(load("res://src/app/main.gd").can_instantiate(),"the contracts Main and extension integration compiles after autoloads are ready")
	var state := board_state(); var before := JSON.stringify(state)
	expect(Codec.valid(state),"the six novice offers and retained accepted contract have a valid bounded shape")
	var packet := snapshot(state,true)
	expect(EloriaProtocol.decode_campaign(JSON.stringify(packet).to_utf8_buffer()).type == "contracts_board","a board-only campaign packet has its own state event")
	var app: Node = root.get_node("AppState"); app.campaign = {"kind":"shelves","run_id":"story","active":true}
	app._on_packet(191,JSON.stringify(packet).to_utf8_buffer())
	expect(app.campaign.run_id == "story" and app.contracts_board.accepted.size() == 1,"opening the board does not replace a tracked story snapshot")
	var invalid := state.duplicate(true); invalid.accepted.resize(4)
	expect(not Codec.valid(invalid),"more than three accepted contracts is rejected")
	invalid = state.duplicate(true); invalid.offers[0].quest_id = 1095
	expect(not Codec.valid(invalid),"journal identities remain bound to their discipline")
	invalid = state.duplicate(true); invalid.offers[0].reward.gold = -1
	expect(not Codec.valid(invalid),"negative rewards cannot reach the board")
	invalid = state.duplicate(true); invalid.offers[0].id = "bad\ncommand"
	expect(not Codec.valid(invalid),"identities cannot inject another command")
	invalid = state.duplicate(true); invalid.offers.append(invalid.offers[0])
	expect(not Codec.valid(invalid),"duplicate offer identities are rejected")
	var expanded := expanded_board()
	expect(expanded.offers.size() == 10 and Codec.valid(expanded),"five templates and both routes fit one authoritative discipline page")
	invalid = expanded.duplicate(true); invalid.offers.append(offer("melee"))
	expect(not Codec.valid(invalid),"a discipline page rejects more than ten offers")
	var new_index: int = expanded.offers.find_custom(func(row: Dictionary) -> bool:return str(row.template_id) == "hold_worksite")
	invalid = expanded.duplicate(true); invalid.offers[new_index].quest_id = 1090
	expect(not Codec.valid(invalid),"a new template cannot borrow the legacy journal identity")
	invalid = expanded.duplicate(true); invalid.offers[0].template_id = "unknown"
	expect(not Codec.valid(invalid),"unknown templates are rejected")
	invalid = expanded.duplicate(true); invalid.offers[new_index].erase("template_id")
	expect(not Codec.valid(invalid),"new journal identities require their exact template binding")
	invalid = expanded.duplicate(true); invalid.reset_token = -1
	expect(not Codec.valid(invalid),"negative reset generations are rejected")
	invalid = expanded.duplicate(true); invalid.reset_skills = ["melee","melee"]
	expect(not Codec.valid(invalid),"reset disciplines are bounded and unique")
	var template_scene := snapshot(expanded)
	template_scene.contracts.current = expanded.offers[new_index].duplicate(true)
	template_scene.scene = {"id":"contracts.brief","token":"intro:1","requires_ack":true,"variant":"hold_worksite","actors":{"mentor":20,"recipient":1}}
	expect(EloriaProtocol.decode_campaign(JSON.stringify(template_scene).to_utf8_buffer()).type == "campaign","a new template selects its own introductory language")
	invalid = template_scene.duplicate(true); invalid.scene.variant = "healing_line"
	expect(EloriaProtocol.decode_campaign(JSON.stringify(invalid).to_utf8_buffer()).type == "invalid","template dialogue cannot cross to another discipline")
	invalid = template_scene.duplicate(true); invalid.scene.id = "contracts.report"
	expect(EloriaProtocol.decode_campaign(JSON.stringify(invalid).to_utf8_buffer()).type == "invalid","report and pause retain their compatible discipline variants")
	var transport: Node = load("res://tests/contracts_transport.gd").new()
	expect(transport.contract_request("accept","daily_melee",7) == OK and transport.sent[-1] == "#contract accept daily_melee 7","accept carries the displayed revision")
	expect(transport.contract_request("join","Friend") == OK and transport.sent[-1] == "#contract join Friend","visible party joining uses the normal contract command")
	expect(transport.contract_request("claim","daily_melee",-1) == ERR_INVALID_PARAMETER,"claim requires a nonnegative revision")
	expect(transport.contract_request("track","bad command") == ERR_INVALID_PARAMETER,"tracking rejects malformed identifiers")
	expect(transport.contract_scene_done("daily_melee","token:7") == OK and transport.sent[-1].begins_with("#contract scene_done"),"scene acknowledgement uses the contracts namespace")
	transport.free()
	var board: Control = Board.new(); root.add_child(board); await settle(); board.apply_state(state); await settle()
	expect(board.panel.visible and board.columns.Available.get_child_count() >= 2,"the legacy selected discipline and grouped party invitation are visible in the board")
	var actions: Array = []; board.action_requested.connect(func(action: String,id: String,revision: int) -> void: actions.append([action,id,revision]))
	var joins: Array = board.columns.Available.find_children("*","Button",true,false).filter(func(button: Button) -> bool: return button.text == "Join Friend")
	(joins[0] as Button).pressed.emit()
	expect(actions == [["join","Friend",7]] and state.accepted.size() == 1,"joining requests help without editing personal accepted contracts")
	board.apply_state(state)
	var first_row: Node = board.columns.Available.get_child(0)
	board.panel.hide(); board.apply_state(state,false)
	expect(not board.panel.visible and board.columns.Available.get_child(0) == first_row,"identical snapshots reuse board rows and a passive sync does not reopen a closed board")
	board.apply_state(state,true)
	expect(board.panel.visible,"an explicit open pulse can reopen the unchanged board")
	for size: Vector2i in [Vector2i(1280,720),Vector2i(720,480)]:
		root.size = size; board._fit(); await settle()
		expect(root.get_visible_rect().encloses(board.panel.get_global_rect()),"the board fits the viewport with scrollable offers")
	board.apply_state(expanded); await settle(); await settle()
	expect(board._offer_count.text == "10 offers","the page advertises its five choices and two routes")
	expect(board._discipline_row.size.y <= 48 and board._discipline_buttons.values().all(func(button: CheckBox) -> bool:return button.size.y <= 40),"the six radio options stay compact instead of wrapping their labels vertically")
	actions.clear(); board._discipline_buttons.magic.pressed.emit(); await settle()
	expect(actions == [["board","magic",7]] and board.state.offer_skill == "melee" and board.state.tracked_id == "daily_melee","changing discipline requests a page without altering accepted or tracked state")
	var magic_page := expanded_board("magic"); board.apply_state(magic_page); await settle()
	var visible_offers: Array = board.columns.Available.get_children().filter(func(row: Node) -> bool:return row.has_meta("contract_skill"))
	expect(visible_offers.size() == 10 and visible_offers.all(func(row: Node) -> bool:return row.get_meta("contract_skill") == "magic"),"the returned page shows all five Magic templates and both routes")
	expect(board.columns.Available.find_children("*","Button",true,false).any(func(button: Button) -> bool:return button.text == "Join Friend"),"party joining remains visible while offers are filtered")
	board.apply_state(magic_page); await settle()
	expect(board._discipline_buttons.magic.button_pressed and board.state.offers.size() == 10,"refresh retains the server page and selected radio without changing authoritative offers")
	board.tabs.current_tab = 1; await settle()
	expect(not board._discipline_row.visible and board.columns.Accepted.get_child_count() == 1,"the offer filter never hides accepted assignments")
	board._abandon = "daily_melee"; board._abandon_skill = "melee"; board._confirm.popup_centered()
	board.reset_contracts(["magic"])
	expect(board._confirm.visible,"an unrelated reset preserves an open abandonment confirmation")
	board.reset_contracts(["melee"])
	expect(not board._confirm.visible and board._abandon.is_empty(),"a matching reset invalidates the stale abandonment confirmation")
	board.tabs.current_tab = 0; board.apply_state(expanded)
	app.contracts_board = expanded.duplicate(true)
	var reset := expanded.duplicate(true); reset.reset_token = 1; reset.reset_skills = ["melee"]
	app._on_packet(191,JSON.stringify(snapshot(reset,true)).to_utf8_buffer())
	expect(app.campaign.run_id == "story","a daily testing reset leaves an unrelated story campaign untouched")
	var magic := snapshot(reset); magic.run_id = "daily_magic"; magic.key = "magic"; magic.contracts.current = offer("magic")
	app.campaign = magic
	reset.reset_token = 2
	app._on_packet(191,JSON.stringify(snapshot(reset,true)).to_utf8_buffer())
	expect(app.campaign.run_id == "daily_magic","a Melee reset preserves an active Magic assignment")
	reset.reset_token = 3; reset.reset_skills = ["magic"]
	app._on_packet(191,JSON.stringify(snapshot(reset,true)).to_utf8_buffer())
	expect(app.campaign.is_empty(),"a matching reset discards the old active campaign and its replay snapshot")
	var field := snapshot(expanded)
	field.contracts.encounter = {"phase":"work","stage":"1","waves":0,"workers":[]}
	field.targets = [{"id":"checkpoint","object_id":0,"tile":[68,249],"label":"Clear the second hostile post","enabled":true}]
	expect(Guidance.navigation_targets(field,"landfall",true) == [{"tile":[68,249],"label":"Clear the second hostile post"}],"a private field checkpoint gets a named map pin without public travel")
	expect(Guidance.navigation_targets(field,"landfall",false).is_empty() and Guidance.navigation_targets(field,"landfall_town",true).is_empty(),"untracked or remote private checkpoints stay off the map")
	field.contracts.encounter.phase = "complete"
	expect(Guidance.navigation_targets(field,"landfall",true).is_empty(),"a completed encounter hides any stale checkpoint")
	field.contracts.encounter.phase = "work"; field.targets[0].enabled = false
	expect(Guidance.navigation_targets(field,"landfall",true).is_empty(),"disabled checkpoints never advertise ready navigation")
	field.targets[0].enabled = true
	var field_hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(field_hud)
	field_hud.apply_state(field,Vector2i(64,249),"landfall")
	expect(not field.has("travel") and field_hud._leave.visible and field_hud._leave.text == "Pause and leave","a checkpoint retains private encounter Pause behavior")
	field_hud.queue_free(); await settle()
	var active := snapshot(state)
	var summary := Summary.campaign(active,"landfall")
	expect(summary.objective == "Demonstrate your skill" and summary.counter.contains("0 / 10"),"the shared quest card presents native personal proof")
	state.current = offer("magic"); state.current.id = "owner_contract"
	state.encounter = {"phase":"work","stage":"defend","waves":1,"workers":[{"actor_id":501,"name":"Worker","health":1,"max_health":80,"downed":true}]}
	active = snapshot(state); active.run_id = "owner_contract"
	expect(Codec.current(active).skill == "magic" and state.accepted.size() == 1,"the temporary helping view never inserts another accepted contract")
	expect(Recovery.patients(active,"landfall")[0].actor_id == 501,"contract workers reuse normal Heal Target recovery")
	expect(Summary.campaign(active,"landfall").urgent,"a fallen contract worker keeps an urgent recovery prompt")
	expect(Recovery.patients(active,"landfall_town").is_empty(),"remote contract workers cannot be targeted by the shortcut")
	app.authenticated = true; app.current_map = "landfall"; app.campaign = active
	app.actors = {501:{"kind":2,"x":64,"y":249}}
	app.contracts_board = state
	app.quest_journal.clear()
	app.quest_journal.append({"title":str(state.accepted[0].title),"objective":"Retained journal row","location":"Landfall","current":0,"target":10})
	var windows: Control = load("res://src/ui/extension_windows.gd").new(); root.add_child(windows); await settle()
	expect(windows._quest_entries.size() == 1 and windows._quest_entries[0]._contract_id == "daily_melee",
		"the accepted contract augments its journal row once using a stable contract identity")
	expect(windows.find_child("OpenLandfallContracts",true,false) != null,"the quest journal has a visible board entry point")
	expect(windows._quest_party_members().size() == 1 and windows._quest_party_members()[0].health == 0,
		"the current helping encounter supplies a real downed companion row without changing accepted contracts")
	var talking := active.duplicate(true)
	talking.scene = {"id":"contracts.brief","token":"accept:1","requires_ack":true,"variant":"magic","actors":{"mentor":501,"recipient":1}}
	windows.contracts_board.panel.show(); app._on_packet(191,JSON.stringify(talking).to_utf8_buffer())
	expect(not windows.contracts_board.panel.visible,"an acceptance conversation suspends the board behind the current-view portrait scene")
	app._on_packet(191,JSON.stringify(snapshot(state,true)).to_utf8_buffer())
	expect(windows.contracts_board.panel.visible,"the explicit post-conversation board open pulse restores the board")
	var main: Node = load("res://src/app/main.gd").new()
	expect(main._is_shelves_grower(501,{"kind":2}),"contract worker health remains visible before selection")
	main.free()
	var owner := Control.new(); root.add_child(owner)
	var guide_hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(guide_hud)
	var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide); guide.configure(owner); guide.set_process(false)
	guide.attach_campaign(guide_hud); guide_hud.apply_state(active,Vector2i(64,249),"landfall")
	guide.apply_campaign(active)
	expect(guide.is_campaign_tracked(),"an explicit private helping view can show temporary guidance")
	guide.set_campaign_tracked(false)
	expect(not guide.is_campaign_tracked() and str(state.tracked_id) == "daily_melee","untracking helper guidance preserves the helper's personal tracked contract")
	guide.set_campaign_tracked(true); guide.hide_window(); guide.set_campaign_tracked(false)
	var old_identity: String = guide.campaign_identity()
	guide.reset_contracts(["melee"])
	expect(guide.campaign_identity() == old_identity and guide.is_window_hidden("campaign:"+old_identity),"an unrelated reset preserves the player's hidden contract window")
	guide.reset_contracts(["magic"]); guide.apply_campaign(active)
	expect(guide.is_campaign_tracked() and not guide.is_window_hidden(),"a reset clears only that discipline's saved hidden and untracked presentation")
	guide.queue_free(); owner.queue_free(); await settle()
	var native_path := OS.get_environment("RL_CONTRACTS_NATIVE")
	if not native_path.is_empty():
		var native: Array = JSON.parse_string(FileAccess.get_file_as_string(native_path))
		for record: Dictionary in native:
			var dto: Dictionary = record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(dto).to_utf8_buffer())
			expect(decoded.type in ["campaign","contracts_board"],"the actual native contracts packet decodes: "+str(decoded.get("error","")))
			if decoded.type in ["campaign","contracts_board"]:
				app._on_packet(191,JSON.stringify(dto).to_utf8_buffer())
			if str(record.get("label","")) == "reset.magic_only":
				expect(str(app.campaign.get("key","")) == "melee" and (app.contracts_board.accepted as Array).all(func(row: Dictionary) -> bool:return str(row.skill) != "magic"),"the actual selective reset packet clears Magic while preserving the current Melee assignment")
			if str(record.get("label","")) == "reset.all":
				expect(app.campaign.is_empty() and (app.contracts_board.accepted as Array).is_empty(),"the actual full reset clears the old card snapshot and accepted board rows")
			if str(record.get("label","")) in ["board.accepted.travel","options.board36"]:
				root.size = Vector2i(1280,720); board.apply_state(dto.contracts)
				await settle(); await settle()
				expect(root.get_visible_rect().encloses(board.panel.get_global_rect()),"long native offers fit on their first opening after wrapping settles")
				for button: Button in board.columns.Available.find_children("*","Button",true,false):
					expect(button.size.x >= 80 and button.size.y <= 48,"native offer actions keep readable button proportions")
	windows.queue_free(); await settle()
	board.apply_state(board_state()); await settle()
	expect(JSON.stringify(board.state) == before,"the board does not optimistically alter authoritative progress or rewards")
	board.queue_free(); await settle()
	print("Landfall contracts client: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

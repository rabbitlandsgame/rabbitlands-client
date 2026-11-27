extends SceneTree
const Contracts := preload("res://tests/test_landfall_contracts.gd")
const Codec := preload("res://src/network/contracts_protocol.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)
func settle() -> void:
	for _frame: int in 5: await process_frame
func click(button: Button) -> void:
	var point := button.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new(); motion.position = point; root.push_input(motion,true)
	for pressed: bool in [true,false]:
		var event := InputEventMouseButton.new(); event.position = point; event.button_index = MOUSE_BUTTON_LEFT; event.pressed = pressed
		root.push_input(event,true)
	await settle()

static func snapshot(phase := "complete", ready := true, helper := false) -> Dictionary:
	var board := Contracts.board_state()
	var row := Contracts.offer("melee"); row.template_id = "watch_road"
	row.status = "ready" if ready else "work"
	row.eligible = false; row.reason = "Return to Batu Ensh to report."
	row.next_step = {"objective_id":"stages","action":"Return to Batu Ensh" if ready else "Finish your own patrol checks",
		"detail":"Earned progress is retained.","location":row.location,"current":3,"target":3}
	board.accepted = [row.duplicate(true)]
	if helper:
		row.id = "party_contract"; row.reason = "Helping the party. Your personal assignments are retained."
	board.current = row; board.tracked_id = row.id
	board.can_leave_encounter = true; board.encounter_complete = phase == "complete"
	board.encounter = {"phase":phase,"stage":"3","waves":3,"workers":[]}
	var value := Contracts.snapshot(board); value.run_id = row.id
	value.available = false; value.map = "landfall"
	value.targets = [{"id":"leave","object_id":63001,"tile":[64,249],"label":"Return to public map","enabled":true}]
	return value

func run() -> void:
	create_timer(45).timeout.connect(func() -> void:push_error("Contract exit checks timed out");quit(1))
	root.get_node("Network").block_for_hud_preview()
	var app: Node = root.get_node("AppState"); app.authenticated = true; app.current_map = "landfall"
	var transport: Node = load("res://tests/contracts_transport.gd").new()
	for dimensions: Vector2i in [Vector2i(1280,720),Vector2i(760,480)]:
		root.size = dimensions
		var owner := Control.new(); root.add_child(owner)
		var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
		var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide)
		guide.configure(owner); guide.set_process(false); guide.attach_campaign(hud)
		var requests: Array = []; hud.action_requested.connect(func(action: String) -> void:requests.append(action))
		var state := snapshot(); var original := JSON.stringify(state)
		expect(EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer()).type == "campaign","completed private fixture matches the native bounded contract shape")
		for compact: bool in [false,true]:
			guide.compact = compact; guide._details_open = false
			hud.apply_state(state,Vector2i(500,500),"landfall"); guide.apply_campaign(state); guide._process(0); await settle()
			var leave: Button = guide.card.encounter_leave_button
			expect(leave.is_visible_in_tree() and leave.text == "Leave and report" and root.get_visible_rect().encloses(leave.get_global_rect()),"completed slim card and ribbon keep an accessible exit at "+str(dimensions))
			var count := requests.size(); await click(leave)
			expect(requests.size() == count+1 and requests[-1] == "leave","the completion button requests native Leave while far from the entry object")
			expect(transport.contract_request(requests[-1]) == OK and transport.sent[-1] == "#contract leave","the exact HUD exit action uses the existing distance-independent wire command")
			expect(JSON.stringify(state) == original,"leaving requests no optimistic reward, party, tracking or progress mutation")
		for helper: bool in [false,true]:
			state = snapshot("complete",false,helper)
			hud.apply_state(state,Vector2i(500,500),"landfall"); guide.apply_campaign(state); guide._process(0); await settle()
			expect(guide.card.encounter_leave_button.text == "Leave encounter" and guide.card.encounter_leave_button.is_visible_in_tree(),"unfinished personal work and helpers can leave without a false report promise")
		state = snapshot("work",false); original = JSON.stringify(state)
		guide.compact = true; hud.apply_state(state,Vector2i(500,500),"landfall"); guide.apply_campaign(state); guide._process(0); await settle()
		expect(not guide.card.encounter_leave_button.visible,"ongoing combat keeps the card compact")
		await click(guide.card.more)
		expect(guide.card.more_is_open() and guide.card.encounter_leave_menu_button.is_visible_in_tree() and guide.card.encounter_leave_menu_button.text == "Pause and leave","More exposes an explicit pause-and-leave action from the ribbon")
		expect([guide.card.instructions_button,guide.card.replay_button,guide.card.hide_button,guide.card.untrack_button].all(func(button: Button) -> bool:return button.is_visible_in_tree()),"the four established More controls remain available")
		var count := requests.size(); await click(guide.card.encounter_leave_menu_button)
		expect(requests.size() == count+1 and requests[-1] == "leave" and not guide.card.more_is_open(),"the actual More action closes its menu and requests Leave once")
		expect(JSON.stringify(state) == original,"pausing preserves all received party and checkpoint data")
		state.contracts.erase("can_leave_encounter"); state.contracts.erase("encounter_complete")
		hud.apply_state(state,Vector2i(500,500),"landfall"); guide.apply_campaign(state)
		expect(not hud.contract_exit_action().is_empty(),"older servers retain a tracked private-encounter exit")
		state.contracts.can_leave_encounter = false; state.contracts.encounter_complete = false
		hud.apply_state(state,Vector2i(500,500),"landfall"); guide.apply_campaign(state); await settle()
		count = requests.size(); hud.request_contract_leave()
		expect(not guide.card.encounter_leave_button.visible and not guide.card.encounter_leave_menu_button.visible and requests.size() == count,"an explicit public-map response removes stale exits and rejects stale activation")
		hud.apply_state(snapshot(),Vector2i.ZERO,"landfall_town"); hud.request_contract_leave()
		expect(requests.size() == count,"a remote private snapshot cannot request an unrelated map exit")
		guide.queue_free(); owner.queue_free(); await settle()
	var board: Control = load("res://src/ui/contracts_board.gd").new(); root.add_child(board); await settle()
	var commands: Array = []; board.action_requested.connect(func(action: String,id: String,revision: int) -> void:commands.append([action,id,revision]))
	for phase: String in ["work","complete"]:
		var state := snapshot(phase,false,true)
		state.contracts.current = {}; state.contracts.tracked_id = ""
		var packet := Contracts.snapshot(state.contracts,true)
		var retained_story := {"kind":"shelves","run_id":"retained_story","active":true}; app.campaign = retained_story.duplicate(true)
		app._on_packet(191,JSON.stringify(packet).to_utf8_buffer())
		expect(app.campaign == retained_story and app.contracts_board.can_leave_encounter,"untracked board-only refresh retains another story while exposing the current private exit")
		board.apply_state(app.contracts_board); await settle()
		for tab: int in 3:
			board.tabs.current_tab = tab; await settle()
			expect(board.encounter_leave_button.is_visible_in_tree() and root.get_visible_rect().encloses(board.encounter_leave_button.get_global_rect()),"the independent exit remains accessible on every Contracts tab")
		expect(board.encounter_leave_button.text == ("Leave encounter" if phase == "complete" else "Pause and leave"),"untracked and helper board exits make no reward claim")
		var count := commands.size(); await click(board.encounter_leave_button)
		board.encounter_leave_button.pressed.emit()
		expect(commands.size() == count+1 and commands[-1][0] == "leave" and commands[-1][1] == "","the board dispatches Leave directly once without a tracked quest or owner identity")
		expect(transport.contract_request(commands[-1][0],commands[-1][1],commands[-1][2]) == OK and transport.sent[-1] == "#contract leave","the actual board action uses native Leave independently of the story HUD")
	var public_board := Contracts.board_state(); board.apply_state(public_board); await settle()
	expect(not board.encounter_leave_button.visible,"legacy or public boards do not show an unsupported exit")
	for field: String in ["can_leave_encounter","encounter_complete"]:
		for invalid: Variant in [1,"true",null,{}]:
			var value := public_board.duplicate(true); value[field] = invalid
			expect(not Codec.valid(value),"optional exit flags require real booleans: "+field)
	var path := OS.get_environment("RL_CONTRACT_EXIT_NATIVE")
	if not path.is_empty():
		var owner := Control.new(); root.add_child(owner)
		var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
		var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide)
		guide.configure(owner); guide.set_process(false); guide.attach_campaign(hud)
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(path))
		for record: Dictionary in records:
			var payload: PackedByteArray = Marshalls.base64_to_raw(str(record.payload_b64))
			var event := EloriaProtocol.decode_server(191,payload)
			expect(event.type in ["campaign","contracts_board"],"actual native exit packet decodes: "+str(record.label))
			if event.type not in ["campaign","contracts_board"]: continue
			var native_board: Dictionary = event.state.contracts if event.type == "campaign" else event.state
			if event.type == "campaign":
				app.current_map = str(event.state.map)
				hud.apply_state(event.state,Vector2i(500,500),app.current_map); guide.apply_campaign(event.state); guide._process(0); await settle()
				if bool(event.state.active):
					expect(guide.card.is_visible_in_tree() and guide.card.encounter_leave_button.visible == bool(native_board.encounter_complete) \
						and guide.card.encounter_leave_menu_button.visible != bool(native_board.encounter_complete),"actual tracked solo and party snapshots keep the appropriate compact exit")
				else:
					expect(not guide.visible and not guide.card.visible and hud.contract_exit_action().is_empty(),"actual untracked snapshots preserve the hidden quest card while the board exit remains available")
			board.apply_state(native_board); board.panel.show(); await settle()
			expect(board.encounter_leave_button.is_visible_in_tree() == bool(native_board.get("can_leave_encounter",false)),"the actual native private/public flag controls the independent exit")
			if bool(native_board.get("can_leave_encounter",false)):
				var native_current: Dictionary = native_board.get("current",{})
				var report := str(native_current.get("status","")) == "ready" and not str(native_current.get("reason","")).begins_with("Helping the party.")
				var label := "Pause and leave" if not bool(native_board.encounter_complete) else "Leave and report" if report else "Leave encounter"
				expect(board.encounter_leave_button.text == label,"actual native helper and incomplete rows receive an accurate exit label")
		guide.queue_free(); owner.queue_free(); await settle()
	board.queue_free(); transport.free(); await settle()
	print("Contract encounter exit: %d checks; %d failures" % [checks,failures]); quit(1 if failures else 0)

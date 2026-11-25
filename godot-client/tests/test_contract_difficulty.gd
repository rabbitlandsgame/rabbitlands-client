extends SceneTree
const Contracts := preload("res://tests/test_landfall_contracts.gd")
const Codec := preload("res://src/network/contracts_protocol.gd")
const Board := preload("res://src/ui/contracts_board.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool,message: String) -> void:
	checks += 1
	if not ok:failures += 1;push_error(message)
func settle() -> void:
	for frame: int in 8:await process_frame

static func expert() -> Dictionary:
	var row := Contracts.offer("melee")
	row.id = "expert-melee";row.template_id = "thornline_breakthrough";row.quest_id = 1113
	row.difficulty = {"id":"expert","rank":4,"label":"Expert","xp_multiplier":3000,"xp_levels":{"attack":137,"defense":89}}
	row.reward = {"xp":{"attack":411000,"defense":267000},"gold":10000,"marks":1,"items":[{"name":"Bandage","count":5}]}
	return row

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	expect("landfall_contracts_v1" in EloriaProtocol.CLIENT_CAPABILITIES and "landfall_contracts_difficulty_v1" in EloriaProtocol.CLIENT_CAPABILITIES,"the client advertises expanded difficulty decoding while retaining compatibility with older contract servers")
	var page := Contracts.expanded_board();page.offers[-1] = expert()
	expect(Codec.valid(page),"the thirty-template registry accepts an Expert melee quote with separate base levels")
	var invalid := page.duplicate(true);invalid.offer_skill = "all"
	expect(not Codec.valid(invalid),"the board cannot request an unbounded All discipline page")
	invalid = page.duplicate(true);invalid.offers[0].skill = "magic"
	expect(not Codec.valid(invalid),"a page cannot contain another discipline's quote")
	invalid = page.duplicate(true);invalid.offers.append(Contracts.offer("melee"))
	expect(not Codec.valid(invalid),"one board page cannot exceed ten offers")
	invalid = page.duplicate(true);invalid.offer_total = 61
	expect(not Codec.valid(invalid),"the advertised catalog remains bounded to sixty routes")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.rank = 5
	expect(not Codec.valid(invalid),"difficulty ranks remain bounded to the five defined choices")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.id = "routine"
	expect(not Codec.valid(invalid),"stable difficulty identities cannot contradict their rank")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.label = "x".repeat(129)
	expect(not Codec.valid(invalid),"server difficulty labels remain nonempty and bounded")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.xp_multiplier = 149
	expect(not Codec.valid(invalid),"XP multipliers below the supported range are refused")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.xp_multiplier = 3001
	expect(not Codec.valid(invalid),"XP multipliers above the supported range are refused")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.xp_multiplier = 2750
	expect(Codec.valid(invalid),"the server may balance a quoted multiplier within the supported range without client price assumptions")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.xp_levels.attack = 0
	expect(not Codec.valid(invalid),"effective quoted base levels cannot fall below the minimum one")
	invalid = page.duplicate(true);invalid.offers[-1].difficulty.xp_levels.erase("defense")
	expect(not Codec.valid(invalid),"each awarded skill needs its own quoted base level")
	var transport: Node = load("res://tests/contracts_transport.gd").new()
	expect(transport.contract_request("board","magic") == OK and transport.sent[-1] == "#contract board magic","the discipline selector uses the native read-only board command")
	expect(transport.contract_request("board") == OK and transport.sent[-1] == "#contract board","bare refresh preserves the remembered server page")
	expect(transport.contract_request("board","all") == ERR_INVALID_PARAMETER and transport.contract_request("board","magic\nclaim") == ERR_INVALID_PARAMETER,"page requests reject unknown or injected discipline names")
	transport.free()
	var row := expert();row.reward.xp.attack = 1234567
	expect(Board.reward_text(row.reward).contains("1,234,567 Attack XP") and Board.reward_text(row.reward).contains("267,000 Defense XP") and Board.reward_text(row.reward).contains("10,000 gold"),"the reward formatter retained for Marks preserves server amounts rather than recalculating them")
	expect(Codec.valid(Contracts.board_state()),"older accepted terms remain compatible without a difficulty quote")
	var app: Node = root.get_node("AppState");app.campaign = {"kind":"shelves","run_id":"standing-order","active":true}
	app._on_packet(191,JSON.stringify(Contracts.snapshot(page,true)).to_utf8_buffer())
	expect(app.campaign.run_id == "standing-order","opening a discipline page cannot replace an unrelated quest")
	var board: Control = Board.new();root.add_child(board);await settle();board.apply_state(page);await settle()
	var actions: Array = [];board.action_requested.connect(func(action: String,id: String,revision: int) -> void:actions.append([action,id,revision]))
	var frozen := JSON.stringify(board.state)
	board._discipline_buttons.magic.pressed.emit();await settle()
	expect(actions == [["board","magic",7]] and board.state.offer_skill == "melee" and board._offer_count.text == "Loading…" and board._discipline_buttons.melee.button_pressed and board._discipline_buttons.values().all(func(button: CheckBox) -> bool:return button.disabled),"a page switch keeps the authoritative radio selected and disables all six options while loading")
	expect(JSON.stringify(board.state) == frozen and board.state.accepted.size() == 1 and board.state.tracked_id == "daily_melee","loading another page never edits accepted work or tracking")
	var magic := Contracts.expanded_board("magic");board.apply_state(magic);await settle()
	expect(not board._discipline_buttons.magic.disabled and board._discipline_buttons.magic.button_pressed and board._offer_count.text == "10 offers","the returned server page settles the radio selection and ten available routes")
	board.panel.hide();board.apply_state(magic,false)
	expect(not board.panel.visible,"a passive snapshot does not reopen a closed board")
	# Exercise the same synchronous transport-failure fallback as ExtensionWindows.
	board.action_requested.connect(func(action: String,_id: String,_revision: int) -> void:
		if action == "board":board.apply_state(magic,false))
	board._discipline_buttons.melee.pressed.emit();await settle()
	expect(not board._discipline_buttons.magic.disabled and not board._pending and board._discipline_buttons.magic.button_pressed,"failed page transport can immediately restore the last authoritative radio selection without leaving disabled controls")
	var native_path := OS.get_environment("RL_CONTRACTS_NATIVE")
	var registry := {}
	if not native_path.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(native_path))
		for record: Dictionary in records:
			var dto: Dictionary = record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(dto).to_utf8_buffer())
			expect(decoded.type in ["campaign","contracts_board"],"actual difficulty packet decodes: "+str(record.get("label",""))+" "+str(decoded.get("error","")))
			var native: Dictionary = dto.contracts
			if not native.has("offer_skill"):continue
			expect(native.offers.size() == 10 and (native.offers as Array).all(func(entry: Dictionary) -> bool:return str(entry.skill) == str(native.offer_skill)),"native offers stay within their authoritative discipline page")
			for entry: Dictionary in native.offers:registry[str(entry.template_id)] = true
			board.apply_state(native,false);board.panel.show();board.tabs.current_tab = 0
			for dimensions: Vector2i in [Vector2i(1280,720),Vector2i(800,600)]:
				root.size = dimensions;board._fit();await settle()
				expect(root.get_visible_rect().encloses(board.panel.get_global_rect()) and board._discipline_row.size.y <= 48,"legacy ten-offer pages fit both supported window sizes with the compact card layout")
		if registry.size() > 0:expect(registry.size() == 30,"the captured six pages collectively expose all thirty template identities")
	board.queue_free();await settle()
	print("Contract difficulty: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

extends SceneTree
const Contracts := preload("res://tests/test_landfall_contracts.gd")
const Codec := preload("res://src/network/contracts_protocol.gd")
const Board := preload("res://src/ui/contracts_board.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)
func settle() -> void:
	for frame: int in 8: await process_frame

static func posted(skill := "melee") -> Dictionary:
	var page := Contracts.expanded_board(skill)
	page.offer_limit = 2
	page.offers = [page.offers[0],page.offers[-1]]
	page.current = page.accepted[0].duplicate(true)
	return page

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var page := posted()
	expect(Codec.valid(page),"the posted pair retains the full catalog count and its accepted assignment")
	var invalid := page.duplicate(true); invalid.offers.append(Contracts.expanded_board().offers[1])
	expect(not Codec.valid(invalid),"a limited board rejects a third posted offer")
	invalid = page.duplicate(true); invalid.offer_limit = 3
	expect(not Codec.valid(invalid),"an unsupported offer limit cannot expand the board")
	invalid = page.duplicate(true); invalid.offer_limit = "2"
	expect(not Codec.valid(invalid),"offer limits cannot be supplied as text")
	invalid = page.duplicate(true); invalid.erase("offer_skill"); invalid.erase("offer_total")
	expect(not Codec.valid(invalid),"a limited board requires its authoritative discipline page")
	invalid = page.duplicate(true); invalid.offer_total = 12
	expect(not Codec.valid(invalid),"the full catalog count remains distinct from the twelve globally posted offers")
	invalid = page.duplicate(true); invalid.offers[1] = posted("magic").offers[1]
	expect(not Codec.valid(invalid),"a limited page cannot mix disciplines")
	var partial := page.duplicate(true); partial.offers.pop_back()
	expect(Codec.valid(partial),"the optional limit is a maximum rather than a required row count")
	expect(Codec.valid(Contracts.expanded_board()) and Codec.valid(Contracts.board_state()),"older ten-offer pages and unpaged boards still decode without an offer limit")
	var app: Node = root.get_node("AppState")
	app.campaign = {"kind":"shelves","run_id":"standing-order","active":true}
	app._on_packet(191,JSON.stringify(Contracts.snapshot(page,true)).to_utf8_buffer())
	expect(app.campaign.run_id == "standing-order","opening a posted pair preserves an unrelated story quest")
	var board: Control = Board.new(); root.add_child(board); await settle()
	board.apply_state(page); await settle()
	expect(board._offer_count.text == "2 offers" and board.columns.Available.get_child_count() >= 2,"the existing board labels the actual posted pair")
	var accepted := JSON.stringify(board.state.accepted)
	var current := JSON.stringify(board.state.current)
	var tracked := str(board.state.tracked_id)
	var actions: Array = []
	board.action_requested.connect(func(action: String,id: String,revision: int) -> void: actions.append([action,id,revision]))
	board._discipline_buttons.magic.pressed.emit(); await settle()
	expect(actions == [["board","magic",7]],"changing discipline still requests a server-owned page")
	expect(JSON.stringify(board.state.accepted) == accepted and JSON.stringify(board.state.current) == current and str(board.state.tracked_id) == tracked,"requesting a new pair leaves all current and accepted terms intact")
	var magic := posted("magic"); board.apply_state(magic); await settle()
	expect(board._offer_count.text == "2 offers" and board._discipline_buttons.magic.button_pressed and not board._pending,"the returned posted pair settles the radio selection")
	var native_path := OS.get_environment("RL_CONTRACTS_NATIVE")
	if not native_path.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(native_path))
		for record: Dictionary in records:
			var dto: Dictionary = record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(dto).to_utf8_buffer())
			expect(decoded.type in ["campaign","contracts_board"],"actual posted-offer packet decodes: "+str(record.get("label",""))+" "+str(decoded.get("error","")))
			if decoded.type not in ["campaign","contracts_board"]: continue
			var native: Dictionary = dto.contracts
			expect(native.offer_limit == 2 and native.offer_total == 60 and native.offers.size() <= 2,"actual posted pages retain bounded rows and the complete catalog identity")
			board.apply_state(native,false); await settle()
			expect(board._offer_count.text == "%d offers" % native.offers.size() and JSON.stringify(board.state.accepted) == JSON.stringify(native.accepted) and JSON.stringify(board.state.get("current",{})) == JSON.stringify(native.get("current",{})) and str(board.state.tracked_id) == str(native.tracked_id),"actual page presentation preserves accepted/current assignments and tracking")
			root.size = Vector2i(800,600); board._fit(); await settle()
			expect(root.get_visible_rect().encloses(board.panel.get_global_rect()),"the unchanged board fits a small window with its native posted pair")
	board.queue_free(); await settle()
	print("Contract posted offers: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

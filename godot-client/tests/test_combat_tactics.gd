extends SceneTree
var failures := 0
var requests: Array[Dictionary] = []
const Protocol := preload("res://src/network/combat_tactics_protocol.gd")

func _init() -> void: run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func fixture() -> Dictionary:
	var path := OS.get_environment("RL_TACTICS_FIXTURE")
	if not path.is_empty(): return JSON.parse_string(FileAccess.get_file_as_string(path))
	var entry := {"enabled":true,"target":"self","condition":"health_below","value":40,"status":"poison","action":"spell:7","power":1}
	return {"kind":"combat_tactics","version":1,"subject":"self","context":"fixture","role":"self","active":false,"player_active":false,"status":"Paused","notice":"","max_rules":6,
		"subjects":[{"id":"self","name":"My combat actions"}],"actions":[{"id":"attack","name":"Weapon attack"},{"id":"spell:7","name":"Heal","scope":"self","hostile":false}],
		"plan":{"revision":0,"selected":0,"profiles":[{"name":"Balanced","rules":[entry]},{"name":"Defensive","rules":[]},{"name":"Offensive","rules":[]}]}}

func run() -> void:
	root.size = Vector2i(1024, 720)
	var state := fixture()
	check(Protocol.valid(state), "actual server tactics state passes the client contract")
	var app := root.get_node("AppState")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(state).to_utf8_buffer())
	check(app.combat_tactics.plan == state.plan, "the real protocol reducer receives the server plan")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify({"kind":"combat_tactics_status", "subject":"self", "active":true, "player_active":true, "status":"Healing", "revision":state.plan.revision}).to_utf8_buffer())
	check(app.player_tactics_active and app.combat_tactics.status == "Healing", "compact status messages update runtime state without replacing the plan")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(state).to_utf8_buffer())
	var invalid: Dictionary = state.duplicate(true)
	invalid.plan.selected = 0.5
	check(not Protocol.valid(invalid), "fractional preset is rejected")
	invalid = state.duplicate(true); invalid.plan.profiles[0].rules[0].enabled = "yes"
	check(not Protocol.valid(invalid), "untyped rule enable is rejected")
	invalid = state.duplicate(true); invalid.plan.profiles[0].rules.resize(7)
	check(not Protocol.valid(invalid), "oversized rule lists are rejected")
	var background := ColorRect.new()
	background.color = Color("100d09")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 18)
	root.add_child(margin)
	var panel = load("res://src/ui/combat_tactics_panel.gd").new()
	margin.add_child(panel)
	panel._request = func(data: Dictionary) -> void: requests.append(data.duplicate(true))
	panel.set_state(state)
	check(panel._rules == state.plan.profiles[0].rules, "editor uses authoritative ordered rules")
	var first_action: OptionButton = panel._rows.get_child(0).get_child(0).get_child(1).get_child(1)
	check(first_action.get_item_metadata(first_action.selected) == panel._rules[0].action, "the displayed action matches the saved spell identity")
	panel._run.pressed.emit()
	check(requests[-1].op == "run" and requests[-1].active, "Start sends an explicit opt-in")
	requests.clear()
	panel._add_rule()
	check(requests.is_empty() and panel._dirty, "editing does not execute or publish actions")
	var draft: Array = panel._rules.duplicate(true)
	var live: Dictionary = state.duplicate(true); live.status = "Waiting for ether"
	panel.set_state(live)
	check(panel._rules == draft, "live status preserves unsaved edits")
	panel._save.pressed.emit()
	check(requests[-1].op == "save" and requests[-1].revision == state.plan.revision and requests[-1].rules == draft, "Save includes complete rules and the authoritative revision")
	live.plan.profiles[0].rules = draft
	live.plan.revision += 1
	panel.set_state(live)
	check(not panel._dirty and panel._save.disabled, "acknowledged save clears dirty state")
	for index in range(8): panel._add_rule()
	check(panel._rules.size() == 6 and panel._add.disabled, "editor bounds the rule list to six")
	live.plan.profiles[0].rules = panel._rules.duplicate(true)
	for frame in range(8): await process_frame
	check(root.get_visible_rect().encloses(panel._save.get_global_rect()), "Save remains inside the supported viewport")
	app._on_connection_state_changed("disconnected")
	check(not panel._dirty and panel._state.is_empty(), "disconnect clears another account's unsaved draft")
	margin.queue_free(); background.queue_free()
	await process_frame
	var book = load("res://src/ui/spells_window.gd").new()
	root.add_child(book)
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	book.configure(catalog, func(_id: int) -> void: pass)
	book.tactics_panel._request = func(data: Dictionary) -> void: requests.append(data.duplicate(true))
	book.tactics_panel.set_state(live)
	book.open_tab("tactics")
	for dimensions: Vector2i in [Vector2i(1024, 720), Vector2i(960, 540), Vector2i(800, 450)]:
		root.size = dimensions
		book._fit_panel()
		for frame in range(8): await process_frame
		check(root.get_visible_rect().encloses(book.panel.get_global_rect()), "Tactics fits the real action book at %s" % dimensions)
		check(book.panel.get_global_rect().encloses(book.tactics_panel._save.get_global_rect()), "Save stays inside the real action book at %s" % dimensions)
	root.size = Vector2i(1024, 720)
	book._fit_panel()
	book.tactics_panel.set_state(state)
	for frame in range(8): await process_frame
	var evidence := OS.get_environment("RL_TACTICS_SCREENSHOT")
	if not evidence.is_empty():
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(evidence)
	book.queue_free()
	await process_frame
	print("Combat tactics editor: %d failures" % failures)
	quit(1 if failures else 0)

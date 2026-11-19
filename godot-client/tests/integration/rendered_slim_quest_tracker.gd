extends SceneTree
## Actual tracker controls on declared UI fixtures and retained native recovery.
const Supplies := preload("res://tests/test_campaign_shelves.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)

func settle() -> void:
	for _frame in 6: await process_frame

func run() -> void:
	Engine.max_fps = 30
	var output := OS.get_environment("RL_SLIM_RENDER_OUT")
	if output.is_empty(): quit(1); return
	DirAccess.make_dir_recursive_absolute(output)
	root.get_node("Network").block_for_hud_preview()
	var app: Node = root.get_node("AppState"); app.authenticated = true
	var backdrop := ColorRect.new(); root.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); backdrop.color = Color("1a2b29")
	var label := Label.new(); root.add_child(label); label.position = Vector2(12,12)
	label.text = "LOCAL QUEST UI PREVIEW\nDeclared fixture progress · native recovery state"
	var owner := Control.new(); root.add_child(owner)
	var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
	var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide)
	guide.configure(owner); guide.set_process(false); guide.attach_campaign(hud)
	var state: Dictionary = Supplies.snapshot()
	state.key = "life"; state.title = "A Harvest Worth Defending"; state.stage = "work"; state.scene = {}
	state.hint = "Protect the four harvesters until 10,000 Sage reaches crew storage. Use Heal Target if a worker falls."
	state.targets = []
	state.shelves.merge({"chapter":"life","phase":"work","private_practice":false,
		"objectives":[{"id":"sage","label":"Store Sage with the crew","current":6240,"target":10000,"personal":false}],
		"growers":{"field":"sage","raid":false,"stored":{"sage":6240,"root":0},"carried":760,"workers":[
			{"name":"Fenna","health":80,"max_health":80},{"name":"Sela","health":80,"max_health":80},
			{"name":"Nell","health":80,"max_health":80},{"name":"Ada","health":80,"max_health":80}]}},true)
	for worker: Dictionary in state.shelves.growers.workers:
		worker.merge({"cargo":190,"activity":"harvest","harvesting":true,"status":"harvesting","resource":"Sage","downed":false},true)
	var native: Dictionary = {}
	var path := OS.get_environment("RL_SLIM_RECOVERY_EVIDENCE")
	if not path.is_empty():
		var bundle: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
		var row: Dictionary = (bundle.records as Array).filter(func(record: Dictionary) -> bool: return record.label == "downed-cage-owner")[0]
		var decoded := EloriaProtocol.decode_campaign(JSON.stringify(row.snapshot).to_utf8_buffer())
		expect(decoded.type == "campaign","native downed-Elen state decodes")
		if decoded.type == "campaign": native = decoded.state
	var captures: Array = []
	for capture: Dictionary in [
		{"id":"slim","dimensions":Vector2i(1280,720),"compact":false,"details":false,"more":false},
		{"id":"ribbon","dimensions":Vector2i(1280,720),"compact":true,"details":false,"more":false},
		{"id":"more","dimensions":Vector2i(1280,720),"compact":false,"details":false,"more":true},
		{"id":"instructions","dimensions":Vector2i(1280,720),"compact":false,"details":true,"more":false},
		{"id":"instructions-small","dimensions":Vector2i(900,460),"compact":false,"details":true,"more":false},
		{"id":"ribbon-small-more","dimensions":Vector2i(900,460),"compact":true,"details":false,"more":true},
		{"id":"elen-small-ribbon","dimensions":Vector2i(900,460),"compact":true,"details":false,"more":false,"native":true}]:
		if bool(capture.get("native",false)) and native.is_empty(): continue
		var current := native if bool(capture.get("native",false)) else state
		var before := JSON.stringify(current)
		root.size = capture.dimensions; root.content_scale_factor = 1.25 if capture.dimensions.x < 1000 else 1.0
		app.current_map = current.map
		guide.card.close_more(); guide.compact = capture.compact; guide._details_open = capture.details
		hud.apply_state(current,Vector2i.ZERO,current.map); guide.apply_campaign(current); guide._process(0)
		await settle(); guide._process(0); await settle()
		if capture.more: guide.card.open_more(); await settle()
		expect(guide.card.is_visible_in_tree() and root.get_visible_rect().encloses(guide.card.get_global_rect()),capture.id+" card fits the viewport")
		expect(guide.card.more.is_visible_in_tree() and not guide.card.heading.text.is_empty(),capture.id+" keeps objective navigation and More accessible")
		if capture.more:
			expect(guide.card.more_is_open() and root.get_visible_rect().encloses(guide.card._menu.get_global_rect()),capture.id+" anchored controls fit")
		if capture.id == "slim": expect(guide.card.size.y < 165,"the default card remains compact")
		if capture.id == "ribbon": expect(guide.card.size.y < 70,"the collapsed state is a one-line ribbon")
		if capture.details:
			expect(guide.card.details_close.is_visible_in_tree(),"inline instructions retain their local Close control")
			expect(hud._inline_ledger.is_visible_in_tree() and not hud._shelves.is_visible_in_tree(),"the compact facts replace the repeated supply ledger")
			expect(hud._map_button.is_visible_in_tree(),"the map action remains in the foldout")
		if capture.id == "elen-small-ribbon": expect(hud._recovery_actions.is_visible_in_tree(),"native recovery stays visible with the ledger collapsed")
		expect(JSON.stringify(current) == before,"rendering changes no quest state")
		await RenderingServer.frame_post_draw
		var filename := str(capture.id)+".png"
		expect(root.get_texture().get_image().save_png(output.path_join(filename)) == OK,"captured "+capture.id)
		captures.append(filename)
	var report := FileAccess.open(output.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":checks,"failures":failures,"captures":captures,
		"scope":"Actual Godot quest controls; declared UI fixture progress and retained native Elen state; not a fresh gameplay run"},"  "))
	report.close(); guide.queue_free(); owner.queue_free()
	for _frame in 3: await process_frame
	print("Slim quest rendering: %d checks; %d failures" % [checks,failures]); quit(1 if failures else 0)

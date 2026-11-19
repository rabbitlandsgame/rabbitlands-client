extends SceneTree
## Actual offline Main layout with retained native Life DTOs. This is a UI
## regression, not a new combat/harvest playthrough or a live server session.
var checks := 0
var failures := 0
var main: Control
var app: Node
var guide: Control
var hud: Control
var minimap: Control
var workspace: Control

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func settle(frames := 12) -> void:
	for _frame: int in frames:
		if is_instance_valid(guide): guide._process(0)
		await process_frame

func press(button: Button, context: String) -> void:
	expect(button.is_visible_in_tree() and not button.disabled,context+" control is available")
	button.pressed.emit()
	await settle()

func open_instructions(tracker: Control, context: String) -> void:
	if tracker.more_is_open(): tracker.close_more()
	await press(tracker.more,context+" More")
	expect(tracker.more_is_open() and root.get_visible_rect().grow(0.75).encloses(tracker._menu.get_global_rect()),
		context+" More menu fits the scaled viewport")
	await press(tracker.instructions_button,context+" Instructions")

func actual_minimap_bounds() -> Rect2:
	var result := minimap.get_global_rect()
	var labels := minimap.get_node_or_null("HudMinimapLabels") as Control
	if labels != null and labels.is_visible_in_tree():
		expect(labels.has_method("drawn_bounds"),"the real minimap labels expose their visible overhang")
		if labels.has_method("drawn_bounds"):
			result = result.merge(labels.get_global_transform() * (labels.call("drawn_bounds") as Rect2))
	return result

func has_space_beside(tracker: Control, obstacle: Rect2) -> bool:
	# These are external layout constraints: eight-pixel screen edges and the
	# existing quickbar reserve. A floating card may choose any clear side.
	var safe := root.get_visible_rect().grow(-8)
	safe.size.y = maxf(1,safe.size.y-WindowDrag.RESERVED_BOTTOM_BAR)
	var dimensions := tracker.get_global_rect().size
	if dimensions.x > safe.size.x or dimensions.y > safe.size.y: return false
	return obstacle.position.x-safe.position.x >= dimensions.x+8 \
		or safe.end.x-obstacle.end.x >= dimensions.x+8 \
		or obstacle.position.y-safe.position.y >= dimensions.y+8 \
		or safe.end.y-obstacle.end.y >= dimensions.y+8

func check_card(tracker: Control, context: String, check_map := true) -> void:
	var area := root.get_visible_rect().grow(0.75)
	expect(tracker.is_visible_in_tree() and area.encloses(tracker.get_global_rect()),
		context+" entire quest card fits: "+str(tracker.get_global_rect())+" within "+str(area))
	expect(tracker.more.is_visible_in_tree() and area.encloses(tracker.more.get_global_rect()),context+" More remains reachable")
	expect(tracker.details_close.is_visible_in_tree() and area.encloses(tracker.details_close.get_global_rect()),
		context+" Close remains outside the scrolling body and on screen")
	if check_map and minimap.is_visible_in_tree():
		var obstacle := actual_minimap_bounds()
		if has_space_beside(tracker,obstacle):
			expect(not tracker.get_global_rect().intersects(obstacle),context+" avoids the actual minimap frame and label overhang")

func native_states() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var path := OS.get_environment("RL_QUEST_HUD_LAYOUT_EVIDENCE")
	expect(not path.is_empty() and FileAccess.file_exists(path),"RL_QUEST_HUD_LAYOUT_EVIDENCE identifies retained native Life snapshots")
	if path.is_empty() or not FileAccess.file_exists(path): return result
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	expect(raw is Array and raw.size() > 16,"native Life bundle retains healthy and downed worker cases")
	if not raw is Array or raw.size() <= 16: return result
	for index: int in [16,0]:
		var decoded := EloriaProtocol.decode_campaign(JSON.stringify(raw[index]).to_utf8_buffer())
		expect(decoded.type == "campaign","actual native Life state passes the campaign decoder at index "+str(index))
		if decoded.type == "campaign": result.append(decoded.state)
	return result

func apply_native(state: Dictionary) -> void:
	app.current_map = str(state.map)
	app.campaign = state
	hud.apply_state(state,Vector2i(57,242),str(state.map))
	guide.apply_campaign(state)
	if not guide.is_campaign_tracked(): guide.set_campaign_tracked(true)
	guide.compact = false
	guide._details_open = false
	guide._refresh()
	await settle()

func native_case(state: Dictionary, context: String) -> void:
	await apply_native(state)
	var before := JSON.stringify(state)
	var identity: String = guide.campaign_identity()
	await open_instructions(guide.card,context)
	check_card(guide.card,context)
	var scroll: ScrollContainer = hud._body_scroll
	var bar := scroll.get_v_scroll_bar()
	expect(scroll.is_visible_in_tree() and bar.max_value > bar.page,context+" complete Instructions retain a bounded active scroll")
	scroll.ensure_control_visible(hud._reduced)
	await settle()
	expect(scroll.get_global_rect().grow(0.75).encloses(hud._reduced.get_global_rect()),
		context+" the final existing instruction control is reachable by scrolling")
	var position: Vector2 = guide.card.global_position
	await settle(20)
	expect(guide.card.global_position.distance_to(position) < 0.75,context+" card placement settles without frame-to-frame oscillation")
	await press(guide.card.details_close,context+" Close")
	expect(not guide._details_open and guide.visible and guide.is_campaign_tracked(),context+" closing keeps the slim card tracked")
	await open_instructions(guide.card,context+" reopened")
	expect(guide._details_open and guide.campaign_identity() == identity and JSON.stringify(app.campaign) == before \
		and JSON.stringify(state) == before,context+" reopening preserves all native progress and tracking identity")
	await press(guide.card.details_close,context+" final Close")

func custom_minimap_cases(state: Dictionary) -> void:
	root.size = Vector2i(1280,720); root.content_scale_factor = 1.0
	workspace.choose_preset("adventure",true)
	await settle()
	await apply_native(state)
	await open_instructions(guide.card,"moved minimap")
	# A real user-movable minimap, including any preset label overhang, is moved
	# over the card's former location. This is UI state only, never a map packet.
	var former_card: Vector2 = guide.card.global_position
	workspace.change_part("minimap","dock_target","none")
	workspace.change_part("minimap","edge_dock","none")
	workspace.change_part("minimap","anchor","free")
	workspace.change_part("minimap","offset",Vector2.ZERO)
	workspace.change_part("minimap","position",former_card/main.game_view.size)
	await settle()
	check_card(guide.card,"moved minimap")
	expect(not guide.card.get_global_rect().intersects(actual_minimap_bounds()),"a moved custom minimap is avoided when there is clear screen space")
	var original_title: String = main._current_map_display_name
	main._current_map_display_name = "The Long Northern Approach to Landfall's Old Warren"
	workspace.change_part("minimap","map_title",true)
	workspace.change_part("minimap","map_directions","all")
	workspace.change_part("minimap","direction_offset",80.0)
	await settle()
	var expanded := actual_minimap_bounds()
	expect(expanded.size.x > minimap.get_global_rect().size.x \
		and expanded.position.y < minimap.get_global_rect().position.y,
		"long actual minimap names and distant cardinal labels have reserved drawn bounds")
	check_card(guide.card,"long minimap title and cardinal offset")
	main._current_map_display_name = original_title
	workspace.change_part("minimap","map_directions","north")
	workspace.change_part("minimap","direction_offset",21.0)
	# A normal custom map in the middle of a small scaled screen leaves no
	# card-sized clear side. The fallback keeps Close usable; last-click
	# priority is tested separately. Use actual editor settings so a deferred
	# preset layout cannot silently undo this declared placement.
	root.size = Vector2i(900,460); root.content_scale_factor = 1.5
	await settle()
	workspace.change_part("minimap","scale",1.0)
	workspace.change_part("minimap","dimensions",Vector2(360,360))
	var center: Vector2 = root.get_visible_rect().get_center()-Vector2(180,180)
	workspace.change_part("minimap","position",center/main.game_view.size)
	await settle()
	check_card(guide.card,"no-space fallback",false)
	expect(guide.card.get_global_rect().intersects(actual_minimap_bounds()),
		"the no-space fixture actually forces the safe overlap fallback: card="+str(guide.card.get_global_rect()) \
		+" map="+str(actual_minimap_bounds())+" viewport="+str(root.get_visible_rect()))
	await press(guide.card.details_close,"no-space Close")
	expect(guide.visible and guide.is_campaign_tracked(),"no-space Close does not hide or untrack the quest")

func ordinary_case() -> void:
	app.campaign = {}; app.lantern_tutorial = {}
	guide.apply_campaign({}); guide.apply_state({})
	hud.apply_state({},Vector2i.ZERO,"landfall")
	root.size = Vector2i(900,460); root.content_scale_factor = 1.5
	workspace.choose_preset("adventure",true)
	await settle()
	var paragraphs: PackedStringArray = []
	for index: int in 36:
		paragraphs.append("Journal paragraph %d: keep this complete ordinary objective and its [literal brackets] available." % index)
	var quest := {"title":"Layout journal fixture","objective":"\n\n".join(paragraphs),
		"location":"Landfall","current":2,"target":10,"ready":false}
	app.quest_journal.assign([quest.duplicate(true)])
	app.state_changed.emit(&"quest_journal")
	await settle()
	var windows: Control = main.extension_windows
	windows.quest_list.select(0)
	windows._on_quest_track_pressed()
	await settle()
	var tracker: Control = windows.tracked_quest
	var before := JSON.stringify(app.quest_journal)
	await open_instructions(tracker,"ordinary long paragraphs")
	check_card(tracker,"ordinary long paragraphs")
	expect(windows.tracked_quest_text.text.begins_with(str(quest.objective)) \
		and windows.tracked_quest_text.get_parsed_text().contains("[literal brackets]"),"all ordinary paragraphs and literal brackets remain intact")
	var scroll: ScrollContainer = tracker.details_scroll
	var bar := scroll.get_v_scroll_bar()
	expect(bar.max_value > bar.page,"ordinary long paragraphs have a real bounded scroll")
	scroll.scroll_vertical = int(bar.max_value)
	await settle()
	expect(bar.value > 0 and absf(bar.value-(bar.max_value-bar.page)) < 2,"the final ordinary journal paragraph can be reached")
	await press(tracker.details_close,"ordinary Close")
	expect(tracker.visible and windows._tracked_quest_title == quest.title,"ordinary Close preserves the pinned quest")
	await open_instructions(tracker,"ordinary reopen")
	expect(JSON.stringify(app.quest_journal) == before and windows._tracked_quest_title == quest.title,
		"ordinary reopening changes neither native paragraphs nor progress/tracking")
	workspace.change_part("objectives","scale",1.5)
	await settle()
	check_card(tracker,"ordinary card at custom scale 1.5")
	var actual_scale: float = absf(tracker.get_global_transform().get_scale().y)
	expect(is_equal_approx(float(workspace.model.working.parts.objectives.scale),1.5) and actual_scale > 1.0,
		"ordinary custom-scale fixture retains requested editor scale and exercises enlarged local units: "+str(actual_scale))
	expect(scroll.get_v_scroll_bar().max_value > scroll.get_v_scroll_bar().page,
		"the locally scaled ordinary card keeps a bounded instruction scroll")
	await press(tracker.details_close,"ordinary scaled Close")
	expect(JSON.stringify(app.quest_journal) == before and windows._tracked_quest_title == quest.title,
		"scaled ordinary Close still preserves native journal content and tracking")

func run() -> void:
	create_timer(120).timeout.connect(func() -> void: push_error("Quest HUD layout timed out"); quit(99))
	root.size = Vector2i(1280,720)
	var network: Node = root.get_node("Network")
	network.block_for_hud_preview()
	app = root.get_node("AppState"); app.authenticated = false
	var states := native_states()
	if states.size() != 2: quit(1); return
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate(); root.add_child(main)
	for _frame: int in 12: await process_frame
	expect(main.hud_workspace.ready_to_layout and not main.map_registry.is_empty(),"actual Main finishes its normal HUD initialization")
	main.set_process(false); main.set_physics_process(false)
	main.get_node("LoginPanel").hide(); main.get_node("LoginBackground").hide(); main.game_view.show()
	app.authenticated = true; app.current_map = "landfall"
	guide = main.lantern_guide; guide.set_process(false)
	hud = main.campaign_hud; minimap = main.minimap_frame; workspace = main.hud_workspace
	expect(guide.card.has_method("set_minimap") and guide.card.has_method("details_height_budget"),"normal quest cards expose bounded minimap-aware layout")
	for preset: String in ["adventure","heritage"]:
		for dimensions: Vector2i in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(900,460)]:
			for scale: float in [1.0,1.5]:
				root.size = dimensions; root.content_scale_factor = scale
				workspace.choose_preset(preset,true)
				await settle()
				# Classic intentionally disables its minimap by default. The
				# overlap case uses its ordinary editor option to enable one.
				if not workspace.model.working.parts.minimap.enabled:
					workspace.change_part("minimap","enabled",true)
					await settle()
				expect(minimap.is_visible_in_tree(),preset+" keeps its real minimap visible")
				for index: int in states.size():
					await native_case(states[index],"%s %s scale %.1f %s" % [preset,dimensions,scale,"healthy" if index == 0 else "downed"])
	await custom_minimap_cases(states[0])
	await ordinary_case()
	expect(network.offline_hud_preview and str(app.connection_state) != "connected","all checks stay offline without a gameplay connection")
	app.authenticated = false
	main._clear_world_presentation()
	expect(await ContinentChunkStream.drain_workers(self,30000),"the offline layout fixture leaves no map workers")
	main.queue_free(); await process_frame; await process_frame
	GlbSceneCache.clear(); NativeAnimationImporter.clear()
	print("Quest HUD layout: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)

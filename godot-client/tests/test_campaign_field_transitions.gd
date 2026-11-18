extends "res://tests/test_campaign_field_readout.gd"
## Saved field records must not masquerade as live work after pause or defeat.

func settle() -> void:
	for _i: int in range(4): await process_frame

func run() -> void:
	var network: Node=root.get_node("Network")
	var recorder := GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK, "the production transport recorder compiles")
	network.set_script(recorder);network.block_for_hud_preview()
	var app: Node=root.get_node("AppState");app.authenticated=true;app.current_map="landfall"
	var hud: Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud)
	var actions: Array=[];var targets: Array=[]
	hud.action_requested.connect(func(action: String) -> void: actions.append(action))
	hud.target_requested.connect(func(id: int,_tile: Vector2i,_near: bool) -> void: targets.append(id))
	var state := snapshot();state.scene={}
	state.hint="Protect the cutters until their bags are secured."
	state.shelves.objectives=[{"id":"kelp","label":"Secure Kelp","current":1000,"target":4000,"personal":false},
		{"id":"cress","label":"Secure Watercress","current":500,"target":2000,"personal":false}]
	state.targets=[{"id":"work","object_id":61845,"tile":[430,300],"label":"Work","enabled":true}]
	state.shelves.water.workers[0].downed=true
	state.shelves.water.hazards=[{"kind":"warning"}]
	hud.apply_state(state,Vector2i(430,300),"landfall")
	expect(hud._shelves.text.contains("DOWNED") and hud._shelves.text.contains("MOVE OUT"), "live field instructions retain the crew's urgent condition")
	hud._request_target("work",61845)
	expect(targets==[61845], "the actual field target is usable during local work")
	targets.clear()
	var paused := state.duplicate(true)
	paused.stage="travel";paused.shelves.phase="travel";paused.shelves.can_begin=false
	paused.travel={"map":"landfall","tile":[430,300],"label":"Loading point","route":"Return to the loading point to resume the saved shipment."}
	hud.apply_state(paused,Vector2i.ZERO,"landfall_town")
	expect(hud._shelves.text.contains("Secured") and not hud._shelves.text.contains("DOWNED") \
		and not hud._shelves.text.contains("MOVE OUT"), "paused work retains saved stock without stale healing or hazard orders")
	expect(not hud._field_summary.visible and not hud._scroll.visible, "travel suspends local work alerts and controls")
	hud._request_target("work",61845);hud._request_leave()
	expect(targets.is_empty() and actions.is_empty(), "hidden field and Return controls cannot fire after leaving a worksite")
	hud._request_entry()
	expect(actions==["shelves_destination"], "the paused assignment offers the existing destination map action")
	actions.clear()
	var retry := state.duplicate(true)
	retry.stage="arrival";retry.shelves.phase="arrival";retry.targets=[]
	retry.scene={"id":"measure.shelves.water.retry","token":"retry"}
	hud.apply_state(retry,Vector2i(430,300),"landfall")
	expect(not hud._field_summary.visible and not hud._shelves.text.contains("DOWNED") \
		and not hud._shelves.text.contains("MOVE OUT"), "defeat review does not tell the player to act on the suspended crew")
	hud._request_entry()
	expect(actions.is_empty(), "a hidden Begin control cannot restart the event before the retry decision")
	hud.apply_state(state,Vector2i(430,300),"landfall",false,true)
	hud._request_target("work",61845);hud._request_entry();hud._request_leave()
	expect(targets.is_empty() and actions.is_empty(), "queued field controls cannot act while a cinematic blocks the card")
	hud.apply_state(state,Vector2i(430,300),"landfall")
	expect(hud._shelves.text.contains("DOWNED") and hud._field_summary.visible, "resuming live work restores current crew instructions")
	var report := paused.duplicate(true)
	report.stage="report";report.shelves.phase="report";report.map="landfall_town"
	report.key="water_barge";report.title="A Boat Against the Current";report.shelves.chapter="water_barge"
	report.shelves.objectives=[{"id":"landings","label":"Reach three shipment landings","current":3,"target":3,"personal":false}]
	report.hint="Return to Ilka at The True Note for your reward."
	report.travel={"map":"landfall_town","tile":[178,26],"label":"Ilka Tarn — The True Note","route":report.hint}
	report.shelves.water.stage="water_barge";report.shelves.water.hull=73;report.shelves.water.landing=3
	report.available=false
	hud.apply_state(report,Vector2i.ZERO,"landfall")
	expect(hud._entry.text=="Do now · Show on map", "reporting from outside the shop first guides the player there")
	hud._request_entry();expect(actions==["shelves_destination"], "distant reporting never submits a remote report")
	actions.clear();report.available=true
	hud.apply_state(report,Vector2i(178,26),"landfall_town")
	expect(hud._entry.text=="Report to Ilka" and not hud._leave.visible, "arriving at Ilka offers reporting without a meaningless public-map Return")
	expect(hud._shelves.text.contains("Barge hull: 73/100") and not hud._shelves.text.contains("departure order") \
		and not hud._shelves.text.contains("Heal the crew"), "the report ledger keeps the barge record without suggesting another departure")
	hud._request_entry();expect(actions==["shelves"], "reporting uses the existing authoritative Ilka interaction")
	actions.clear();hud.apply_state(report,Vector2i.ZERO,"landfall")
	expect(hud._entry.text=="Do now · Show on map", "a stale shop snapshot cannot offer reporting after the player leaves")
	var rescue := Rescue.snapshot();rescue.scene={};rescue.active=false
	rescue.rescue.stage="mine";rescue.rescue.mother.following=true
	rescue.travel={"map":"landfall","npc":"Lantern Mine","route":"The rescue is suspended. Return to Lantern Mine to resume your saved encounter."}
	hud.apply_state(rescue,Vector2i.ZERO,"landfall")
	expect(not hud._rescue.visible and not hud._rescue_actions.visible and not hud._field_summary.visible, "a suspended rescue does not claim its absent companion is following")
	expect(hud._hint.text==rescue.travel.route and not hud._hint.text.contains("Speak with Lantern Mine"), "resume instructions treat Lantern Mine as a place to enter")
	var owner := Control.new();root.add_child(owner)
	var guide: Control=load("res://src/ui/lantern_guide.gd").new();root.add_child(guide)
	guide.configure(owner);guide.set_process(false);guide.attach_campaign(hud);guide.apply_campaign(rescue)
	expect(guide.campaign_entry().objective==hud._hint.text, "the journal and shared card use the same rescue resume instructions")
	hud.apply_state(report,Vector2i(178,26),"landfall_town");guide.apply_campaign(report)
	root.size=Vector2i(720,480);root.content_scale_factor=1.5
	guide._process(0);await settle()
	hud._body_scroll.ensure_control_visible(hud._entry);await settle()
	var bounds: Rect2=root.get_visible_rect()
	var clip: Rect2=hud._body_scroll.get_global_rect().intersection(bounds)
	expect(bounds.encloses(guide.card.get_global_rect()) and bounds.encloses(guide._buttons.get_global_rect()), "the report card and footer fit a small viewport at 150 percent")
	expect(clip.encloses(hud._entry.get_global_rect()), "Report to Ilka remains reachable by scrolling in the small window")
	var output := OS.get_environment("RL_FIELD_TRANSITIONS_OUT")
	if not output.is_empty() and DisplayServer.get_name()!="headless":
		DirAccess.make_dir_recursive_absolute(output);await RenderingServer.frame_post_draw
		expect(root.get_texture().get_image().save_png(output.path_join("report-ready-small.png"))==OK,"captured the small report card")
	guide.hide_button.pressed.emit();hud._request_entry()
	expect(actions.is_empty() and guide.is_campaign_tracked(), "Hide retains the assignment and suppresses its hidden report action")
	report.hint="Ilka is ready to hear your report.";guide.apply_campaign(report);hud.apply_state(report,Vector2i(178,26),"landfall_town")
	guide._refresh()
	expect(not guide.visible, "a report-ready update does not reopen the player's hidden quest card")
	guide.show_window();guide.collapse.pressed.emit();hud._request_entry()
	expect(guide.compact and actions.is_empty(), "minimizing retains the normal Instructions control without a hidden report request")
	guide.collapse.pressed.emit();guide.untrack.pressed.emit();hud._request_entry()
	expect(not guide.is_campaign_tracked() and actions.is_empty(), "Untrack preserves the normal quest behavior and suppresses hidden entry")
	var evidence := OS.get_environment("RL_SUPPLY_PAUSE_EVIDENCE")
	var native_report: Dictionary={}
	if not evidence.is_empty():
		var records: Array=JSON.parse_string(FileAccess.get_file_as_string(evidence))
		expect(not records.is_empty(), "the native transition capture contains saved worksite snapshots")
		for record: Dictionary in records:
			var native: Dictionary=record.get("snapshot",record)
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign", "the real pause/report snapshot decodes: "+str(decoded.get("error","")))
			if str((native.get("shelves",{}) as Dictionary).get("phase",""))=="report" and bool(native.get("available",false)):
				native_report=native
			hud.apply_state(native,Vector2i.ZERO,str(native.get("map","landfall")))
			if not (native.get("travel",{}) as Dictionary).is_empty() or str((native.get("shelves",{}) as Dictionary).get("phase",""))!="work":
				expect(not hud._field_summary.visible and not hud._shelves.text.contains("DOWNED") \
					and not hud._shelves.text.contains("MOVE OUT"), "native navigation and scene reviews keep suspended work alerts out of the card")
	for node: Node in [guide,owner]:node.queue_free()
	await process_frame;await process_frame
	if DisplayServer.get_name()=="headless":
		# Exercise the real shared-card signal connection through Main and Network,
		# using a server report capture when supplied, without starting a connection.
		app.authenticated=false
		var client: Control=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(client)
		client.set_process(false);client.set_physics_process(false);await process_frame
		var reporting: Dictionary=native_report if not native_report.is_empty() else report
		app.authenticated=true;app.current_map="landfall_town";app.campaign=reporting;app.death={}
		client.game_view.show()
		client.campaign_hud.apply_state(reporting,Vector2i(178,26),"landfall_town")
		client.lantern_guide.apply_campaign(reporting)
		var frames: Array=network.sent_frames;frames.clear()
		client.campaign_hud._entry.pressed.emit()
		expect(frames==[EloriaProtocol.chat("#campaign shelves")], "the visible report button reaches Main and the ordinary server campaign dispatcher (visible=%s, blocked=%s, label=%s, frames=%d)" \
			% [client.campaign_hud._entry.is_visible_in_tree(),client._world_input_blocked(),client.campaign_hud._entry.text,frames.size()])
		app.authenticated=false;client._clear_world_presentation()
		expect(await ContinentChunkStream.drain_workers(self,30000), "the report interaction leaves no world workers running")
		client.queue_free();await process_frame;await process_frame;GlbSceneCache.clear();NativeAnimationImporter.clear()
	print("Campaign field transitions: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

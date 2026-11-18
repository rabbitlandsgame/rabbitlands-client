extends "res://tests/test_shelves_water.gd"
const Readout := preload("res://src/ui/campaign_field_readout.gd")
const Rescue := preload("res://tests/test_campaign_rescue.gd")

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var worker: Dictionary = {"name":"Nell", "health":80, "max_health":80, "downed":false,
		"cargo":0, "activity":"harvest", "harvesting":false}
	expect(Readout.worker_activity(worker) == "Moving / preparing", "a legacy assignment does not falsely claim active harvesting")
	worker.activity="return"
	expect(Readout.worker_activity(worker) == "Moving / preparing", "an empty legacy hauler is not described as carrying cargo")
	worker.cargo=50
	expect(Readout.worker_activity(worker) == "Carrying to storage", "a real carried load is distinguished from work still at the patch")
	worker.merge({"status":"under_attack", "harvesting":true},true)
	expect(Readout.worker_activity(worker) == "Under attack", "combat overrides a lingering harvest animation")
	worker.status="moving"
	expect(Readout.worker_activity(worker) == "Moving to work", "moving workers are identified honestly")
	worker.status="loading";worker.resource="Coal"
	expect(Readout.worker_activity(worker) == "Loading recovered stock", "stock recovery is distinct from mining")
	worker.status="harvesting"
	expect(Readout.worker_activity(worker) == "Mining Coal", "native resource status gives the right work verb")
	worker.resource="Kelp"
	expect(Readout.worker_activity(worker) == "Cutting Kelp", "a gatherer helping Kelp is shown doing her actual task")
	worker.resource="Watercress"
	expect(Readout.worker_activity(worker) == "Gathering Watercress", "Watercress is not presented as mining or loading")
	worker.downed=true
	expect(Readout.worker_activity(worker).begins_with("DOWNED"), "a downed flag takes priority over the last assigned task")
	worker.downed=false;worker.status="unknown"
	expect(Readout.worker_activity(worker) != "unknown", "unknown optional status is never printed as an instruction")
	var state := snapshot();state.shelves.water.command="wait"
	state.hint="Protect the cutters and the loading route. Secure 400 Kelp and 200 Watercress."
	state.shelves.objectives=[{"id":"kelp","label":"Secure Kelp","current":100,"target":400,"personal":false},
		{"id":"cress","label":"Secure Watercress","current":50,"target":200,"personal":false}]
	state.shelves.water.merge({"stored":{"kelp":100,"cress":50},"bins":{"kelp":20,"cress":10},
		"cut":{"kelp":120,"cress":60},"goals":{"kelp":400,"cress":200}},true)
	var summary := Readout.summary(state)
	expect(str(summary.text).contains("choose Work") and str(summary.text).begins_with("Secured:"), "waiting crews lead with secured progress and their next command")
	state.shelves.water.command="regroup"
	expect(str(Readout.summary(state).text).contains("regrouping"), "regroup is explained before the player orders work")
	state.shelves.water.field_hint="Ada is bringing the last bags to storage. Protect her route."
	expect(str(Readout.summary(state).text).contains("last bags"), "the authoritative reason for waiting is shown")
	state.shelves.water.workers[2].downed=true
	summary=Readout.summary(state)
	expect(bool(summary.urgent) and str(summary.text).begins_with("Cutter 2 is down") and not str(summary.text).contains("last bags"),
		"a downed worker is the first actionable instruction")
	state.shelves.water.workers[2].downed=false;state.shelves.water.workers[0].status="under_attack"
	expect(str(Readout.summary(state).text).contains("under attack"), "the player knows which worker needs protection")
	state.shelves.water.hazards=[{"kind":"impact"}]
	expect(not str(Readout.summary(state).text).contains("MOVE OUT"), "a spent surge does not issue a stale dodge warning")
	state.shelves.water.hazards=[{"kind":"warning"}]
	expect(str(Readout.summary(state).text).contains("MOVE OUT"), "an upcoming hazard takes immediate priority")
	state.travel={"map":"landfall", "tile":[400,315]}
	expect(Readout.summary(state).is_empty(), "travel does not show combat alerts from a suspended worksite")
	state.erase("travel");state.shelves.water.hazards=[]
	var rescue := Rescue.snapshot();rescue.rescue.stage="mine";rescue.stage="mine";rescue.scene={}
	rescue.rescue.mother.merge({"configured":true,"enabled":true,"following":true,"mana":7},true)
	summary=Readout.summary(rescue)
	expect(bool(summary.urgent) and str(summary.text).contains("too little ether"), "the finite healer warns before a player expects another heal")
	rescue.rescue.mother.mana=15
	expect(str(Readout.summary(rescue).text).contains("low on ether"), "low ether is distinct from complete healing exhaustion")
	rescue.rescue.mother.mana=16
	expect(Readout.summary(rescue).is_empty(), "healthy ether above the inclusive quarter-pool boundary does not issue a low-resource alert")
	rescue.rescue.mother.downed=true
	expect(str(Readout.summary(rescue).text).contains("Heal Target") and not str(Readout.summary(rescue).text).contains("low on ether"),
		"reviving the companion takes priority over resource advice")
	rescue.rescue.stage="injured"
	expect(not str(Readout.summary(rescue).text).contains("Elen"), "the opening does not reveal the woman's name before her introduction")
	rescue.rescue.checkin={"visiting":true}
	expect(Readout.summary(rescue).is_empty(), "the safe inn conversation has no private-mine combat alerts")
	rescue.rescue.erase("checkin");rescue.rescue.stage="reward"
	expect(Readout.summary(rescue).is_empty(), "the safe outdoor farewell does not suggest another fight")
	var hud: Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud)
	var actions: Array=[];hud.action_requested.connect(func(value: String) -> void: actions.append(value))
	state.shelves.water.field_hint="The crew is regrouping at the next loading point. Follow the marker, then choose Work."
	hud.apply_state(state,Vector2i(430,300),"landfall")
	expect(hud._field_summary.visible and hud._field_summary.get_index() < hud._scroll.get_index(), "the action summary precedes the field controls")
	expect(hud._shelves.text.contains("At loading point") and hud._shelves.text.contains("Secured"), "detailed carried and secured counts remain in Instructions")
	expect(hud._shelves.text.contains("Moving / preparing"), "the detailed ledger uses the same honest legacy worker fallback")
	var native_path := OS.get_environment("RL_FIELD_READOUT_EVIDENCE")
	if not native_path.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(native_path))
		var validated: Dictionary = {}
		for native: Dictionary in records:
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign", "native field diagnostics decode: " + str(decoded.get("error", "")))
			hud.apply_state(native,Vector2i.ZERO,str(native.map))
			if not Readout.summary(native).is_empty():
				expect(not hud._field_summary.text.is_empty(), "actual field work receives its actionable summary")
			if not (native.get("shelves", {}) as Dictionary).get("fire", {}).is_empty() \
					and not (native.shelves.fire.get("workers", []) as Array).is_empty(): validated=native
		if not validated.is_empty():
			var invalid := validated.duplicate(true);invalid.shelves.fire.workers[0].status="unknown_activity"
			expect(EloriaProtocol.decode_campaign(JSON.stringify(invalid).to_utf8_buffer()).type=="invalid", "unknown wire activity is rejected")
			invalid=validated.duplicate(true);invalid.shelves.fire.workers[0].resource="Gold Coins"
			expect(EloriaProtocol.decode_campaign(JSON.stringify(invalid).to_utf8_buffer()).type=="invalid", "unrelated resources cannot enter the worker readout")
			invalid=validated.duplicate(true);invalid.shelves.fire.field_hint="x".repeat(241)
			expect(EloriaProtocol.decode_campaign(JSON.stringify(invalid).to_utf8_buffer()).type=="invalid", "field instructions have a bounded wire length")
	# Restore one complete cutters state after exercising unrelated native snapshots.
	state.shelves.water.command="wait"
	state.shelves.water.field_hint="The crew is paused at the loading point. Choose Work to resume cutting and hauling."
	for cutter: Dictionary in state.shelves.water.workers:
		cutter.status="waiting";cutter.harvesting=false
	state.targets=[]
	for command: Dictionary in [{"id":61845,"label":"Work"},{"id":61846,"label":"Regroup"},{"id":61847,"label":"Wait"}]:
		state.targets.append({"id":str(command.id),"object_id":command.id,"tile":[430,300],"label":command.label,"enabled":true})
	hud.apply_state(state,Vector2i(430,300),"landfall")
	var app: Node=root.get_node("AppState");app.authenticated=true;app.current_map="landfall"
	var owner := Control.new();root.add_child(owner)
	var guide: Control=load("res://src/ui/lantern_guide.gd").new();root.add_child(guide);guide.configure(owner);guide.set_process(false)
	guide.attach_campaign(hud);root.size=Vector2i(720,480);root.content_scale_factor=1.5
	guide.apply_campaign(state);guide._process(0)
	for _i: int in range(4):await process_frame
	expect(guide.heading.text==state.title and guide.instruction.text==state.hint,
		"the small viewport title and instructions describe the displayed cutters task")
	expect(hud._field_summary.text==str(Readout.summary(state).text) and hud._shelves.text.contains("Kelp") \
		and not hud._shelves.text.contains("Barge hull"), "the summary and ledger are restored to the same cutters snapshot")
	expect(hud._targets.get_child_count()==3 and hud._targets.get_child(0).text=="Work",
		"the displayed field commands belong to the cutters rather than the last native encounter")
	hud._body_scroll.ensure_control_visible(hud._field_summary)
	for _i: int in range(3):await process_frame
	expect(root.get_visible_rect().encloses(guide.card.get_global_rect()), "the existing card remains bounded in a small scaled viewport")
	expect(root.get_visible_rect().encloses(guide._buttons.get_global_rect()), "the existing footer controls remain reachable in the small scaled viewport")
	var clip: Rect2=hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._field_summary.get_global_rect()), "the summary remains readable by scrolling in the small window")
	var preview := OS.get_environment("RL_FIELD_READOUT_OUT")
	if not preview.is_empty() and DisplayServer.get_name() != "headless":
		DirAccess.make_dir_recursive_absolute(preview)
		await RenderingServer.frame_post_draw
		expect(root.get_texture().get_image().save_png(preview.path_join("field-readout-small.png"))==OK, "captured the small field card")
	guide.collapse.pressed.emit()
	for _i: int in range(2):await process_frame
	expect(guide.compact and not hud.is_visible_in_tree() and guide.collapse.text=="Instructions", "minimizing still uses the normal quest card behavior")
	guide.collapse.pressed.emit();guide.hide_button.pressed.emit()
	for _i: int in range(2):await process_frame
	expect(not guide.visible and guide.is_campaign_tracked(), "Hide keeps the assignment tracked without a second overlay")
	expect(actions.is_empty(), "passive summaries and visibility controls never request gameplay actions")
	for node: Node in [guide, owner]:node.queue_free()
	await process_frame;await process_frame
	print("Campaign field readout: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

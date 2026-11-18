extends "res://tests/test_quest_first_pass_cinematics.gd"
## An explicit server acknowledgement is durable viewing history. A fresh
## client must not mistake that retained recording for a new native scene.

func fresh_record() -> Dictionary:
	var f:=fixture()
	f.scene.cancel("fixture_setup")
	f.scene.reset_session()
	f.acks.clear()
	f.state.scene={"id":"measure.shelves.basics.heal_target","token":"saved-target",
		"requires_ack":false,"actors":{"mentor":2,"protagonist":1}}
	f.actions=[]
	f.scene.event_requested.connect(func(id:String)->void:f.actions.append(id))
	f.scene.inspection_requested.connect(func(action:String)->void:f.actions.append(action))
	f.scene.choice_requested.connect(func(option:String)->void:f.actions.append(option))
	return f

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var f:=fresh_record()
	var held:Transform3D=f.rig.camera.global_transform
	var before:=JSON.stringify(f.state)
	tick(f,0)
	expect(not f.scene.is_active() and not f.scene.blocks_input()
		and f.rig.camera.global_transform.is_equal_approx(held),
		"a fresh acknowledged recording leaves normal play and its viewport alone")
	expect(f.acks.is_empty() and f.actions.is_empty() and JSON.stringify(f.state)==before,
		"historical receipt observation emits no ACK, event, native action or proof")
	expect(f.scene.can_replay(f.state,"landfall_town") and f.scene.request_replay(f.state,"landfall_town"),
		"the acknowledged same-map recording remains available through explicit replay")
	tick(f,0)
	expect(f.scene.playing and f.scene.is_replaying() and not f.scene._caption.text.is_empty()
		and f.scene._dialogue.visible,"explicit replay shows the saved scene as read-only dialogue")
	f.scene.continue_dialogue()
	tick(f,0.8)
	expect(f.acks.is_empty() and f.actions.is_empty() and JSON.stringify(f.state)==before,
		"explicit replay supplies no original ACK, movement, choices or quest progress")
	dispose(f)
	await process_frame
	for explicit:bool in [false,true]:
		f=fresh_record()
		if explicit:f.state.scene.requires_ack=true
		else:f.state.scene.erase("requires_ack")
		tick(f,0)
		expect(f.scene.playing and f.scene.blocks_input() and not f.scene._caption.text.is_empty(),
			"a pending native scene still starts" if explicit else "legacy informational scenes with an omitted flag still start")
		f.state.scene.requires_ack=false
		var identity:String=f.scene._run+":"+f.scene._token
		tick(f,0.1)
		expect(f.scene.playing and not f.scene._handled.has(identity),
			"an ACK echo does not interrupt a scene already being presented")
		dispose(f)
		await process_frame
	var path:=OS.get_environment("RL_RESCUE_ACK_REJOIN_EVIDENCE")
	if not path.is_empty():
		var raw:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
		var native:Dictionary=raw.get("campaign",raw.get("snapshot",raw))
		var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
		expect(decoded.type=="campaign" and native.scene.id=="measure.rescue.descent"
			and native.scene.has("requires_ack") and not bool(native.scene.requires_ack),
			"the actual mine-rejoin packet contains an already-acknowledged descent")
		f=fresh_record()
		f.state=native.duplicate(true)
		before=JSON.stringify(f.state)
		held=f.rig.camera.global_transform
		for index in 3:
			f.scene.update(0.1,f.state,f.rig,f.nodes,1,str(native.map),true)
		expect(not f.scene.is_active() and f.acks.is_empty() and f.actions.is_empty()
			and f.rig.camera.global_transform.is_equal_approx(held) and JSON.stringify(f.state)==before,
			"the native retained descent cannot autoplay, move the viewport or request another transition")
		expect(f.scene._handled.has(str(native.run_id)+":"+str(native.scene.token)),
			"the explicit native receipt survives fresh client viewing-history initialization")
		dispose(f)
		await process_frame
		var legacy_native:Dictionary=native.duplicate(true)
		legacy_native.scene.erase("requires_ack")
		var payload:=JSON.stringify(legacy_native).to_utf8_buffer()
		var legacy_decoded:=EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE,payload)
		expect(legacy_decoded.type=="campaign" and not legacy_decoded.state.scene.has("requires_ack"),
			"the actual packet decoder preserves an omitted legacy ACK field")
		root.get_node("AppState")._on_packet(EloriaProtocol.ServerMessage.ELORIA_CAMPAIGN_STATE,payload)
		expect(not (root.get_node("AppState").campaign.scene as Dictionary).has("requires_ack"),
			"AppState packet reduction does not materialize false for an omitted informational field")
		f=fresh_record();f.state=legacy_decoded.state
		f.scene.update(0,f.state,f.rig,f.nodes,1,str(native.map),false)
		expect(f.scene.pending and not f.scene._handled.has(str(native.run_id)+":"+str(native.scene.token)),
			"a decoded legacy scene remains eligible to play once its ordinary cast and world are ready")
		dispose(f)
		await process_frame
	var final_path:=OS.get_environment("RL_RESCUE_REJOIN_FINAL_EVIDENCE")
	if not final_path.is_empty():
		var bundle:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(final_path))
		for native:Dictionary in bundle.snapshots:
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign","final native rejoin state decodes: "+str(native.capture_label))
			f=fresh_record();f.state=native.duplicate(true)
			f.scene.update(0,f.state,f.rig,f.nodes,1,str(native.map),false)
			if str(native.capture_label)=="pending-party-viewer":
				expect(bool(native.scene.requires_ack) and f.scene.pending and f.acks.is_empty() and f.actions.is_empty(),
					"an actually unacknowledged party viewer retains its pending descent film")
			else:
				expect((native.scene as Dictionary).is_empty() and not f.scene.is_active()
					and f.acks.is_empty() and f.actions.is_empty(),
					"normal minework has no historical film or new transition, including while another recipient is pending")
			dispose(f)
			await process_frame
	print("Acknowledged campaign rejoin: %d checks; %d failures"%[checks,failures])
	quit(0 if failures==0 else 1)

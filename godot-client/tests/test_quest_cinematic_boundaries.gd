extends "res://tests/test_quest_first_pass_cinematics.gd"
## Exercise authored scenes at real UI/lifecycle boundaries, without gameplay mutation.

func decision(id: String, selected := "") -> Dictionary:
	var ids: Array = {"rescue_response":["help","watch"], "rescue_accept":["accept","defer"],
		"rescue_checkin":["listen","rest"], "shelves_cape":["keeper","artificer"],
		"shelves_enriched":["life","fire","water","earth","wind","magic","death","frost"]}[id]
	var options: Array = []
	for option: String in ids: options.append({"id":option,"label":option,"detail":"Test approach."})
	return {"id":id,"title":"Choose","selected":selected,"response":"We will continue together.",
		"owner":"Aster","owner_is_you":true,"can_choose":selected.is_empty(),"options":options}

func authored(id: String, choice := {}) -> Dictionary:
	var f := fixture()
	f.scene.cancel("replace_fixture")
	f.scene._definitions = Scene.scene_definitions()
	f.scene._definition = f.scene._definitions[id].duplicate(true)
	f.scene._scene_id = id; f.scene._run = "boundaries"; f.scene._token = "original"
	f.scene._map = "landfall_town"; f.scene._variant = str(choice.get("selected", ""))
	f.scene._choice_state = choice.duplicate(true)
	var bindings := {"mother":2,"mentor":2,"recipient":1,"protagonist":1,"goblin_boss":2}
	bindings = bindings.duplicate()
	for role: String in bindings.keys():
		if role not in f.scene._definition.get("cast_roles", []): bindings.erase(role)
	if id=="measure.rescue.captive": bindings={"goblin_boss":2,"protagonist":1}
	f.scene._start(f.rig,f.rig.camera,f.player,f.nodes,bindings)
	f.state = {"active":true,"kind":"rescue","run_id":"boundaries","map":"landfall_town",
		"scene":{"id":id,"token":"original","requires_ack":true,"actors":bindings,"choice":choice.duplicate(true)}}
	f.acks.clear()
	return f

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	for id: String in ["measure.rescue.abduction","measure.rescue.descent"]:
		var f := authored(id, decision("rescue_response","watch") if id.ends_with("abduction") else {})
		f.scene.set_auto_dialogue(true,false)
		f.scene._choice_completed = true
		f.scene.elapsed = f.scene._duration() - 0.25
		f.scene._camera_entry_elapsed = f.scene.elapsed
		tick(f,0)
		expect(is_equal_approx(f.scene._screen.modulate.a,1.0),
			id+" keeps its cinematic frame opaque until its own handoff")
		expect(f.scene.blocks_input() and f.acks.is_empty(),
			"the outgoing scene has not acknowledged or released before its transition")
		dispose(f)

	var f := authored("measure.rescue.commitment",decision("rescue_accept"))
	var original_view: Transform3D = f.rig.camera.global_transform
	var old: Node3D = f.mentor
	var replacement := Ready.Actor.new(); root.add_child(replacement)
	replacement.position = old.global_position; replacement.server_target = replacement.position
	old.hide(); old.process_mode = Node.PROCESS_MODE_DISABLED
	f.nodes[2] = replacement
	tick(f,0)
	expect(not f.scene.is_active() and f.scene._last_return_reason=="actor_lost",
		"a parked but still-alive NPC cannot continue staging after native node replacement")
	expect(f.acks==[["original","actor_lost"]] and not f.scene._handled.has("boundaries:original"),
		"native cast replacement is recoverable and never acknowledges completion")
	expect(not old.visible and f.rig.camera.global_transform.is_equal_approx(original_view),
		"recovery preserves the native park and restores the player camera")
	expect(f.scene.request_interactive(f.state,"landfall_town"), "the replaced cast can be retried interactively")
	tick(f,0)
	expect(f.scene.playing and f.scene._actors.mother==replacement,
		"retry binds the current native mother rather than the parked body")
	dispose(f); replacement.queue_free()

	f=authored("measure.rescue.captive")
	f.scene.elapsed=30; f.scene._camera_entry_elapsed=30
	f.mentor.hide(); f.nodes.erase(2)
	tick(f,0)
	expect(f.scene.playing and not f.scene._actors.has("goblin_boss") and not f.mentor.visible,
		"a departed corpse is released after its authored final shot without interrupting the family")
	dispose(f)
	f=authored("measure.rescue.captive")
	var corpse := Ready.Actor.new(); root.add_child(corpse)
	corpse.position=f.mentor.server_target; corpse.server_target=corpse.position
	f.scene._replay_visuals[2]=corpse
	f.mentor.hide(); f.nodes[2]=corpse
	tick(f,0)
	expect(f.scene.playing and f.scene._actors.goblin_boss==corpse and f.acks.is_empty() and not f.mentor.visible,
		"authorized local dead-boss reconstruction preserves the unfinished death shot without reviving the parked corpse")
	dispose(f); corpse.queue_free()

	f=authored("measure.shelves.review",decision("shelves_cape","keeper"))
	f.state.kind="shelves"
	f.scene.skip(); tick(f,0); tick(f,0)
	var held: Transform3D = f.rig.camera.global_transform
	expect(f.scene.blocks_input() and not f.scene.playing and f.acks==[["original","skipped"]],
		"Skip carries through the confirmed reward into its authored next question")
	f.state.scene={}; f.state.active=false; tick(f,0.2)
	expect(f.scene.blocks_input() and f.rig.camera.global_transform.is_equal_approx(held),
		"the completed reward holds its view while the next question is in transit")
	f.state.active=true
	f.state.scene={"id":"measure.shelves.enriched","token":"enriched","requires_ack":true,
		"actors":{"mentor":2,"recipient":1},"choice":decision("shelves_enriched")}
	tick(f,0)
	expect(f.scene._choice_waiting and f.scene.elapsed==10 and f.scene._choice_dialog.option_buttons.size()==8
		and f.rig.camera.global_transform.is_equal_approx(held) and f.acks.size()==1,
		"the chained seek stops at the next native question in the same settled view")
	dispose(f)

	f=authored("measure.rescue.checkin",decision("rescue_checkin","listen"))
	var native_requests: Array = []
	f.scene.choice_requested.connect(func(id: String) -> void: native_requests.append(id))
	f.scene.cancel("finished"); f.state.scene.requires_ack=false
	expect(f.scene.request_replay(f.state,"landfall_town"), "the recorded visit can be replayed")
	tick(f,0); f.scene.skip(); tick(f,0)
	expect(f.scene._choice_review and f.scene._choice_waiting
		and f.scene._choice_dialog.option_buttons.size()==2,
		"replay seeking stops at both recorded options in the shared dialogue")
	expect(f.scene._choice_dialog._content.listen.heading.text.begins_with("✓ ")
		and f.scene._choice_dialog.option_buttons.rest.disabled,
		"replay highlights the recorded answer and cannot change it")
	var stale: Callable = f.scene._on_choice_continue.bind(f.scene._choice_token())
	f.scene.cancel("test_replay_end")
	expect(f.scene.request_replay(f.state,"landfall_town"), "the same token can be reviewed again")
	tick(f,0); f.scene.skip(); tick(f,0)
	stale.call_deferred(); await process_frame
	expect(f.scene._choice_waiting and not f.scene._choice_completed and native_requests.is_empty(),
		"a queued Continue from a previous replay cannot consume the current recorded decision")
	dispose(f)

	for interruption: String in ["inactive","map_changed"]:
		f=authored("measure.rescue.commitment",decision("rescue_accept"))
		f.scene.skip(); tick(f,0)
		expect(f.scene._choice_waiting and f.acks.is_empty(), "Skip stops at the native unanswered decision")
		var changed := Vector3(12,0,5)
		f.player.position=changed; f.player.server_target=changed
		if interruption=="inactive": f.state.active=false; tick(f,0)
		else: f.scene.update(0,f.state,f.rig,f.nodes,1,"landfall",true)
		expect(not f.scene.blocks_input() and f.rig.focus.is_equal_approx(changed)
			and f.scene._scene_handoff.is_empty(), interruption+" restores the current player and releases its decision")
		expect(not f.scene._handled.has("boundaries:original"), "interruption cannot complete the unanswered quest")
		f.state.active=true; tick(f,0)
		expect(f.scene.playing and not f.scene.is_replaying(), "resuming an interrupted visit retains native interaction")
		dispose(f)

	f=authored("measure.rescue.commitment",decision("rescue_accept"))
	var new_player := Ready.Actor.new(); root.add_child(new_player)
	new_player.position=Vector3(18,0,7); new_player.server_target=new_player.position
	f.player.hide(); f.nodes[1]=new_player
	f.state.active=false; tick(f,0)
	expect(not f.scene.blocks_input() and f.rig.focus.is_equal_approx(new_player.server_target) and not f.player.visible,
		"an interruption after native player replacement centers the new body and keeps the old one parked")
	dispose(f); new_player.queue_free()
	await process_frame
	print("Quest cinematic boundaries: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)

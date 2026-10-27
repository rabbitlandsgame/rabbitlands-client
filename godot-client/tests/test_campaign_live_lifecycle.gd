extends SceneTree
## Main's real crowd/body and cinematic pipeline, with a recorded transport.
## A finite test floor supplies the streaming precondition; no quest is solved.
const Presentation := preload("res://src/world/campaign_scene.gd")
const DecisionFixture := preload("res://tests/test_campaign_ferry_decision.gd")
const RescueFixture := preload("res://tests/test_campaign_rescue.gd")
var checks := 0
var failures := 0
var main: Node
var app: Node
var network: Node
var scene: Node
var results: Array = []
var replays: Array = []
var requests: Array[String] = []

class LocalActor extends Node3D:
	var server_target := Vector3.ZERO

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func state(token := "live-token") -> Dictionary:
	return {"version":1,"kind":"opening","active":true,"run_id":"live-run",
		"map":"landfall","title":"Live lifecycle fixture","targets":[],
		"actors":{"odo":20,"protagonist":1},"party":{"role":"owner"},
		"scene":{"id":"measure.landing.plan","token":token,"requires_ack":true,
			"ack_revision":0,"actors":{"odo":20,"protagonist":1},
			"choice":DecisionFixture.decision()}}

func definition() -> Dictionary:
	return {"duration":12,"entry_seconds":0,"exit_seconds":0,"anchor":"odo",
		"cast_roles":["odo"],"required_actors":["odo"],
		"shots":[{"t":0,"anchor":"odo","position":[4,4,8],"target":[0,1,0]}],
		"choice_id":"opening_rescue","choice_at":3,"choice_response_until":8,
		"response_actor":"odo","response_speaker":"Guide",
		"lines":[{"at":0,"speaker":"Guide","actor":"odo","text":"Wait for the whole crew."},
			{"at":3,"speaker":"Guide","actor":"odo","text":"Which approach will you take?"}]}

func actor_record() -> Dictionary:
	# The current imported goblin is intentionally far beyond ordinary body
	# build/release distances. Its inclusion in a film must be sufficient.
	return {"actor_id":20,"actor_type":624,"kind":2,"name":"Lifecycle guide",
		"map":"landfall","x":200,"y":0,"rotation":0,"frame":7,
		"health":20,"max_health":20,"alive":true,"appearance":{},
		"equipment_visuals":{},"equipment_fallback_parts":[]}

func tick(delta: float) -> void:
	main.call("_update_campaign", delta)

func sent() -> Array:
	return network.get("sent_frames") as Array

func duplicate_snapshot(revision: int) -> void:
	var next: Dictionary = app.campaign.duplicate(true)
	next.revision = revision
	app.campaign = next

func wait_for_body(ids: Array[int] = [20]) -> void:
	var deadline := Time.get_ticks_msec() + 45000
	while Time.get_ticks_msec() < deadline:
		main.call("_update_model_builds")
		var all_ready := true
		for id: int in ids:
			var actor: ReplicatedActor3D = main.actor_nodes.get(id)
			all_ready = all_ready and is_instance_valid(actor) and not actor.is_model_deferred()
		if all_ready: return
		await process_frame
		await physics_frame
	expect(false, "the imported required model finishes within the bounded build window")

func run() -> void:
	create_timer(120).timeout.connect(func() -> void: push_error("Live lifecycle checks timed out"); quit(1))
	root.size = Vector2i(1280,720)
	app = root.get_node("AppState")
	network = root.get_node("Network")
	# Keep actual Network validation/encoding and Main signal wiring. Only the
	# final socket write is replaced, so this process cannot contact a service.
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the isolated final-write recorder compiles")
	network.set_script(recorder)
	network.call("block_for_hud_preview")
	app.authenticated = false
	app.current_map = ""
	app.actors = {}
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	await process_frame
	scene = main.get("campaign_scene")
	scene.set_auto_dialogue(false, false)
	scene.set_reduced_motion(false, false)
	scene._definitions = {"measure.landing.plan":definition()}
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: results.append([token,reason]))
	scene.replay_finished.connect(func(token: String, reason: String) -> void: replays.append([token,reason]))
	scene.choice_requested.connect(func(id: String) -> void: requests.append(id))
	var floor := StaticBody3D.new()
	floor.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	floor.collision_mask = 0
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(600,0.1,600)
	collision.shape = box
	collision.position.y = -0.05
	floor.add_child(collision)
	main.world_root.add_child(floor)
	await physics_frame
	app.authenticated = true
	app.death = {}
	app.local_actor_id = 1
	app.selected_actor_id = -1
	app.combat_state = {}
	app.current_map = "landfall"
	app.campaign = {}
	app.actors = {1:{"actor_id":1,"kind":1,"health":20,"max_health":20,"x":0,"y":0},20:actor_record()}
	main.adapter = CoordinateAdapter.new({"walkingHeight":0.025,"invertServerY":true})
	var local := LocalActor.new()
	main.world_root.add_child(local)
	local.position = main.adapter.tile_center(0,0)
	local.server_target = local.position
	main.actor_nodes[1] = local
	main.camera_rig.set_focus(local.position)
	main.crowd.configure("all", "1")
	main._body_cap_distance = 0.0
	expect(main.call("_spawn_actor",20,false), "Main creates the real remote actor as a budgeted deferred node")
	var initial: ReplicatedActor3D = main.actor_nodes.get(20)
	expect(initial != null and initial.is_model_deferred() and initial.get_skeleton() == null,
		"the delayed cast starts without a native model or skeleton")
	app.campaign = state()
	expect(EloriaProtocol.decode_campaign(JSON.stringify(app.campaign).to_utf8_buffer()).get("type") == "campaign",
		"the repeated campaign record uses the real validated protocol shape")
	var original_camera: Transform3D = main.camera_rig.camera.global_transform
	for index: int in range(4):
		# Main's asynchronous startup surface work may have completed between
		# setup awaits. This subcase deliberately represents an ungrounded local.
		main._grounded_actors.clear()
		duplicate_snapshot(index)
		tick(3.0)
	expect(scene.pending and not scene.playing and is_equal_approx(scene._wait_elapsed,12.0),
		"world-loading snapshots remain pending before the bounded readiness timeout")
	expect(main.camera_rig.camera.global_transform.is_equal_approx(original_camera) and sent().is_empty(),
		"an unready world retains the player camera and sends no scene acknowledgement")
	main._grounded_actors.clear()
	tick(Presentation.WAIT_LIMIT)
	expect(not scene.is_active() and not scene.blocks_input()
		and results == [["live-token","loading_timeout"]],
		"a persistently unready world reaches a bounded failure and releases controls")
	expect(not scene._handled.has("live-run:live-token") and not scene._ack_requested and sent().is_empty(),
		"world-loading timeout cannot become a completed viewing or native ACK")
	main._grounded_actors[1] = true
	tick(0)
	expect(not main.campaign_hud._replay.disabled and main.campaign_hud._replay.text == "Retry scene"
		and scene.request_interactive(app.campaign,"landfall"),
		"once map readiness returns the interrupted first viewing offers native Retry")
	results.clear()
	tick(0.05)
	expect(scene.pending and not scene.playing and not scene._handled.has("live-run:live-token"),
		"a valid deferred required speaker cannot start or mark the film handled")
	expect(main.call("_crowd_priority_actor",20) and main.call("_body_cap_allows",20,200.0),
		"pending cinematic cast bypasses distance and the ordinary body cap")
	expect(main.crowd.pending_candidates() == 0, "the test begins without a distance-ranked promotion candidate")
	await wait_for_body()
	var built: ReplicatedActor3D = main.actor_nodes.get(20)
	if not is_instance_valid(built) or built.is_model_deferred():
		await cleanup()
		quit(1)
		return
	expect(built != initial and built.get_skeleton() != null and built.get_node_or_null("NativeModel") != null,
		"Main's critical promotion builds the actual imported skeleton even outside draw range and without a candidate queue")
	tick(0.05)
	expect(scene.playing and not scene.pending and not scene._handled.has("live-run:live-token"),
		"the real Main pipeline starts once the cast body is fully built without treating start as completion")
	# Simulate the live periodic stream and an already-computed demotion claim.
	# Frozen exported DTO fixtures do not exercise either of these interleavings.
	for index: int in range(160):
		duplicate_snapshot(index + 10)
		main.call("_release_bodies", [[200.0,20]])
		tick(0.05)
	expect(scene.playing and scene._choice_waiting and is_equal_approx(scene.elapsed,3.0),
		"many incoming snapshots retain the live film at its unresolved decision instead of jumping to the native HUD")
	expect(main.actor_nodes[20] == built and not built.is_model_deferred() and main.crowd.releases == 0,
		"a stale crowd release claim cannot demote a required cast body during the film")
	expect(results.is_empty() and sent().is_empty() and not scene._handled.has("live-run:live-token"),
		"periodic snapshots and a long reading pause produce neither already_seen nor a scene-done wire command")
	expect(scene._dialogue.content_active() and scene._choice_dialog.option_buttons.size() == 3,
		"the shared bottom dialogue still contains the actual three selectable options")
	# A genuine actor loss must restore play, but must never become a native ACK
	# on this frame or the next identical periodic snapshot.
	main.actor_nodes.erase(20)
	built.free()
	tick(0)
	for index: int in range(20):
		duplicate_snapshot(200 + index)
		tick(0.1)
	expect(results == [["live-token","actor_lost"]] and not scene.is_active(),
		"a real removed cast node reports one recoverable actor_lost failure")
	expect(sent().is_empty() and not scene._handled.has("live-run:live-token"),
		"Main never acknowledges actor loss and a repeated token never turns that failure into already_seen")
	expect(scene.live_actor_ids(app.campaign,"landfall").is_empty(),
		"an inactive failed film does not permanently pin unrelated live crowd bodies")
	expect(scene.request_replay(app.campaign,"landfall"),
		"the existing Replay entry can recover a failed original viewing")
	expect(not scene.is_replaying() and 20 in scene.live_actor_ids(app.campaign,"landfall"),
		"failed-view recovery queues native interaction and re-pins the cast, rather than a read-only replay")
	await process_frame
	expect(main.call("_spawn_actor",20,false), "the reappearing native cast gets its ordinary deferred node")
	await wait_for_body()
	tick(0.05)
	tick(3.0)
	expect(scene.playing and not scene.is_replaying() and scene._choice_waiting,
		"retry reopens the real undecided cinematic with live choice controls")
	var choice_token: String = scene._choice_token()
	scene._choice_dialog.option_buttons.repair.pressed.emit()
	scene._on_choice_option("repair",choice_token)
	expect(requests == ["repair"] and not sent().is_empty(),
		"retry uses Main's real choice signal/command once, not a local progress mutation")
	expect(sent() == [EloriaProtocol.chat("#campaign scene_choice live-run live-token repair")]
		and str(app.campaign.scene.choice.selected).is_empty(),
		"the single encoded choice request leaves the authoritative selection unchanged")
	app.campaign.scene.choice.selected = "repair"
	app.campaign.scene.choice.can_choose = false
	app.campaign.scene.choice.response = "Use the marked repair station."
	tick(0)
	expect(scene._choice_completed and not scene._choice_waiting and not scene.is_replaying(),
		"only the authoritative selected snapshot resumes the recovered live conversation")
	scene.cancel("finished")
	var expected_frames := [EloriaProtocol.chat("#campaign scene_choice live-run live-token repair"),
		EloriaProtocol.chat("#campaign scene_done live-run live-token")]
	expect(sent() == expected_frames and scene._handled.has("live-run:live-token"),
		"actual completion alone marks handled and emits exactly one native scene acknowledgement")
	for index: int in range(20):
		duplicate_snapshot(300 + index)
		tick(0.1)
	expect(sent() == expected_frames and not scene.is_active(),
		"completed same-revision periodic snapshots cannot duplicate the acknowledgement")
	expect(scene.live_actor_ids(app.campaign,"landfall").is_empty(),
		"completed native scenes release their crowd priority")
	expect(scene.request_replay(app.campaign,"landfall"), "a completed viewing remains replayable")
	tick(0)
	tick(3.0)
	expect(scene.is_replaying() and scene._choice_waiting and scene._choice_review,
		"the completed replay is read-only and retains the recorded decision")
	var all_disabled := true
	for button: Button in scene._choice_dialog.option_buttons.values():
		all_disabled = all_disabled and button.disabled
	expect(all_disabled and scene.live_actor_ids(app.campaign,"landfall").is_empty(),
		"replay cannot submit a fresh choice or pin the live crowd cast")
	scene.cancel("finished")
	expect(replays == [["live-token","finished"]] and sent() == expected_frames,
		"a completed replay emits no native ACK or gameplay command")
	# A known but never-built body has the same no-ACK guarantee at timeout.
	app.campaign = state("timeout-token")
	await process_frame
	main.call("_replace_actor_node",20,false)
	tick(0)
	tick(Presentation.WAIT_LIMIT + 0.01)
	for index: int in range(5): tick(0.1)
	expect(results.back() == ["timeout-token","loading_timeout"] and sent() == expected_frames,
		"an actual deferred-body timeout is recoverable and cannot acknowledge the native scene")
	expect(not scene.request_interactive(app.campaign,"greenlight"),
		"interactive recovery rejects a foreign map")
	await check_retry_surfaces()
	await check_mother_conversation()
	await check_missing_intro_retry_surfaces()
	await cleanup()
	print("Campaign live lifecycle checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

func check_retry_surfaces() -> void:
	var source := JSON.stringify(app.campaign)
	sent().clear()
	tick(0)
	var hud: Control = main.get("campaign_hud")
	var journal: Control = main.get("extension_windows")
	expect(hud._replay.text == "Retry scene" and not hud._replay.disabled,
		"Main labels an enabled field-guide action Retry scene after a failed viewing")
	expect(journal.quest_replay_button.text == "Retry current scene" and not journal.quest_replay_button.disabled,
		"the real journal action also identifies interactive recovery rather than read-only replay")
	hud._replay.pressed.emit()
	expect(not scene._interactive_requested_identity.is_empty() and not scene.uses_replay_cast(),
		"clicking the actual Retry scene button queues native viewing")
	await wait_for_body()
	tick(0)
	expect(scene.playing and not scene.is_replaying() and sent().is_empty() and JSON.stringify(app.campaign) == source,
		"the field-guide retry starts live without a direct interaction, decision, ACK or local state mutation")
	scene.cancel("actor_lost")
	tick(0)
	expect(journal.quest_replay_button.text == "Retry current scene" and not journal.quest_replay_button.disabled,
		"a subsequent failure leaves the actual journal retry enabled")
	journal.quest_replay_button.pressed.emit()
	expect(not scene._interactive_requested_identity.is_empty() and not scene.uses_replay_cast(),
		"clicking the journal's actual retry follows the same native path")
	tick(0)
	expect(scene.playing and not scene.is_replaying() and sent().is_empty() and JSON.stringify(app.campaign) == source,
		"journal recovery preserves native mode and never touches or submits a decision")
	scene.cancel("test_reset")

func rescue_state(token: String) -> Dictionary:
	var value := RescueFixture.snapshot()
	value.stage = "ready"
	value.rescue.stage = "ready"
	value.rescue.can_accept = true
	value.scene = {"id":"measure.rescue.commitment","token":token,"requires_ack":true,
		"actors":{"mother":20,"protagonist":1},
		"choice":{"id":"rescue_accept","title":"Will you help?","owner":"Aster",
			"owner_is_you":true,"can_choose":true,"selected":"","response":"",
			"options":[{"id":"accept","label":"I will help","detail":"Follow her to the mine."},
				{"id":"defer","label":"I need to prepare","detail":"Return later."}]}}
	return value

func check_mother_conversation() -> void:
	scene.cancel("test_reset")
	var authored := definition()
	authored.anchor = "mother"
	authored.cast_roles = ["mother"]
	authored.required_actors = ["mother"]
	authored.shots[0].anchor = "mother"
	authored.choice_id = "rescue_accept"
	authored.response_actor = "mother"
	scene._definitions["measure.rescue.commitment"] = authored
	app.campaign = rescue_state("mother-conversation")
	app.actors[20].x = 1
	app.actors[20].y = 0
	app.actors[21] = {"actor_id":21,"kind":2,"name":"Ordinary villager",
		"x":1,"y":0,"health":20,"max_health":20}
	var mother: ReplicatedActor3D = main.actor_nodes[20]
	mother.apply_server_state(app.actors[20],main.adapter,true)
	var source := JSON.stringify(app.campaign)
	sent().clear()
	expect(EloriaProtocol.decode_campaign(source.to_utf8_buffer()).type == "campaign",
		"the mother conversation uses a complete protocol-valid ready-stage rescue snapshot")
	expect(main.call("_try_rescue_conversation",20),
		"talking to the eligible nearby mother queues her unanswered commitment cinematic")
	expect(not scene._interactive_requested_identity.is_empty() and sent().is_empty() and JSON.stringify(app.campaign) == source,
		"ordinary conversation queues presentation only, without touching the mother, selecting an answer or changing progress")
	tick(0)
	tick(3)
	expect(scene.playing and not scene.is_replaying() and scene._choice_waiting,
		"the real Main conversation opens selectable native Accept and Defer options")
	scene.cancel("test_reset")
	for refusal: String in ["ordinary_actor","out_of_range","helper","selected","wrong_map","inactive"]:
		app.campaign = rescue_state("mother-refusal-"+refusal)
		app.actors[20].x = 1
		app.current_map = "landfall"
		var id := 20
		match refusal:
			"ordinary_actor": id = 21
			"out_of_range": app.actors[20].x = 5
			"helper":
				app.campaign.party.role = "helper"
				app.campaign.scene.choice.can_choose = false
				app.campaign.scene.choice.owner_is_you = false
			"selected":
				app.campaign.scene.choice.selected = "accept"
				app.campaign.scene.choice.can_choose = false
				app.campaign.scene.choice.response = "Follow me."
			"wrong_map": app.current_map = "greenlight"
			"inactive": app.campaign.active = false
		source = JSON.stringify(app.campaign)
		expect(not main.call("_try_rescue_conversation",id) and scene._interactive_requested_identity.is_empty()
			and sent().is_empty() and JSON.stringify(app.campaign) == source,
			refusal+" cannot reopen the mother's native decision or submit anything")
	for stage: String in ["injured","mine","boss_confrontation","boss_defeated","complete"]:
		app.current_map = "landfall"
		app.actors[20].x = 1
		app.campaign = rescue_state("mother-stage-"+stage)
		app.campaign.stage = stage
		app.campaign.rescue.stage = stage
		app.campaign.rescue.can_accept = false
		app.campaign.scene = {}
		expect(EloriaProtocol.decode_campaign(JSON.stringify(app.campaign).to_utf8_buffer()).type == "campaign",
			stage+" refusal uses a valid native rescue state without an offered choice")
		expect(not main.call("_try_rescue_conversation",20) and sent().is_empty(),
			stage+" cannot create a new commitment conversation from a stage with no decision")
	# A migrated opening may retain the actual unanswered decision after its
	# original departing cast has been removed. Re-admission is a server request.
	app.campaign = RescueFixture.snapshot()
	app.campaign.scene.requires_ack = true
	app.actors[20].x = 1
	source = JSON.stringify(app.campaign)
	expect(main.call("_try_rescue_conversation",20),
		"an old opening with missing required bindings requests native cast re-admission")
	expect(sent() == [EloriaProtocol.chat("#campaign rescue replay")]
		and scene._interactive_requested_identity.is_empty() and JSON.stringify(app.campaign) == source,
		"the real Network whitelist encodes exactly rescue replay, with no USE, direct touch or submitted choice")
	sent().clear()
	app.campaign.scene.choice.can_choose = false
	app.campaign.scene.choice.owner_is_you = false
	app.campaign.party.role = "helper"
	expect(not main.call("_try_rescue_conversation",20) and sent().is_empty(),
		"an ineligible helper cannot re-admit an old opening's missing cast")

func check_missing_intro_retry_surfaces() -> void:
	var authored := definition()
	authored.anchor = "mother"
	authored.shots[0].anchor = "mother"
	authored.choice_id = "rescue_response"
	authored.response_actor = "mother"
	var original: Dictionary = Presentation.scene_definitions()["measure.rescue.abduction"]
	authored.cast_roles = original.cast_roles.duplicate()
	authored.required_actors = original.required_actors.duplicate()
	scene._definitions["measure.rescue.abduction"] = authored
	var hud: Control = main.get("campaign_hud")
	var journal: Control = main.get("extension_windows")
	var extra_bindings := {"daughter":30,"abductor":31,"escort":32,"guard":33}
	for surface: String in ["HUD","journal"]:
		scene.cancel("test_reset")
		# The old packet's departing cast really is absent, not just hidden.
		for id: int in extra_bindings.values():
			var previous: Variant = main.actor_nodes.get(id)
			if is_instance_valid(previous):
				if not previous.is_model_deferred(): main._built_bodies = maxi(0,main._built_bodies-1)
				main.actor_nodes.erase(id)
				previous.queue_free()
			app.actors.erase(id)
		app.campaign = RescueFixture.snapshot()
		app.campaign.scene.token = "missing-intro-"+surface
		app.campaign.scene.requires_ack = true
		# Retry is intentionally usable away from the mother. Only ordinary
		# conversation should impose the native talking-distance requirement.
		app.actors[20].x = 50
		(main.actor_nodes[20] as ReplicatedActor3D).apply_server_state(app.actors[20],main.adapter,true)
		sent().clear()
		expect(EloriaProtocol.decode_campaign(JSON.stringify(app.campaign).to_utf8_buffer()).type == "campaign",
			surface+" missing-cast recovery starts from a valid unresolved legacy opening")
		tick(0)
		tick(Presentation.WAIT_LIMIT+0.01)
		expect(not scene.is_active() and scene.needs_retry(app.campaign) and sent().is_empty(),
			surface+" exposes a failed original viewing without acknowledging missing intro bindings")
		expect(not hud._replay.disabled and hud._replay.text == "Retry scene"
			and not journal.quest_replay_button.disabled and journal.quest_replay_button.text == "Retry current scene",
			surface+" exposes both real Retry actions for the missing-cast fault")
		expect(not main.call("_try_rescue_conversation",20) and sent().is_empty(),
			surface+" fixture is outside ordinary mother conversation range")
		var before := JSON.stringify(app.campaign)
		if surface == "HUD": hud._replay.pressed.emit()
		else: journal.quest_replay_button.pressed.emit()
		expect(sent() == [EloriaProtocol.chat("#campaign rescue replay")]
			and scene._interactive_requested_identity.is_empty() and not scene.is_active()
			and JSON.stringify(app.campaign) == before,
			surface+" Retry requests native cast re-admission once instead of queuing another local timeout or decision")
		# Model an actual server response: a new scene token and complete role
		# bindings. Every returning NPC gets its ordinary deferred native body.
		app.campaign = app.campaign.duplicate(true)
		app.campaign.scene.token = "restaged-intro-"+surface
		app.campaign.scene.actors.merge(extra_bindings,true)
		app.campaign.actors.merge(extra_bindings,true)
		expect(EloriaProtocol.decode_campaign(JSON.stringify(app.campaign).to_utf8_buffer()).type == "campaign",
			surface+" receives a valid new-token complete-cast native snapshot")
		var all_spawned := true
		for id: int in extra_bindings.values():
			var dto := actor_record()
			dto.actor_id = id
			dto.name = "Re-admitted cast "+str(id)
			dto.x = 50 + id - 29
			app.actors[id] = dto
			all_spawned = bool(main.call("_spawn_actor",id,false)) and all_spawned
		expect(all_spawned, surface+" re-admitted native actors enter Main through ordinary deferred spawning")
		await wait_for_body([20,30,31,32,33])
		var all_native := true
		for id: int in [20,30,31,32,33]:
			var actor: ReplicatedActor3D = main.actor_nodes.get(id)
			all_native = all_native and is_instance_valid(actor) and not actor.is_model_deferred() and actor.get_skeleton() != null
		expect(all_native, surface+" recovery finishes every imported cast model before the new establishing shot")
		var accepted := JSON.stringify(app.campaign)
		tick(0)
		expect(scene.playing and not scene.is_replaying() and scene._token == "restaged-intro-"+surface,
			surface+" server re-admission starts the new token as native viewing, not read-only replay")
		tick(3)
		expect(scene._choice_waiting and scene._choice_dialog.option_buttons.has("help")
			and scene._choice_dialog.option_buttons.has("watch")
			and not scene._choice_dialog.option_buttons.help.disabled and not scene._choice_dialog.option_buttons.watch.disabled,
			surface+" restaged intro retains both live Help and Watch choices")
		expect(sent() == [EloriaProtocol.chat("#campaign rescue replay")]
			and JSON.stringify(app.campaign) == accepted and str(app.campaign.scene.choice.selected).is_empty(),
			surface+" restaging and viewing send no direct touch, submitted decision or premature ACK")
		scene.cancel("test_reset")

func cleanup() -> void:
	app.authenticated = false
	scene.cancel("test_cleanup")
	main.call("_clear_world_presentation")
	expect(await ContinentChunkStream.drain_workers(self,30000), "the focused test drains every owned resource worker")
	main.queue_free()
	await process_frame
	await process_frame

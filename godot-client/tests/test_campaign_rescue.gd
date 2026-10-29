extends SceneTree
## Exercise the real decoder, transport, shared card, party roster and Main
## guards. No local timer or cinematic position can grant rescue progress.
var checks := 0
var failures := 0
var main: Node
var app: Node
var network: Node
var controller: Node
var local: Node3D
var mother: Node3D

static func snapshot() -> Dictionary:
	return {"version":1,"kind":"rescue","active":true,"available":false,"started":true,
		"run_id":"rescue-run","map":"landfall","stage":"choice","key":"rescue",
		"title":"A Daughter in the Dark","hint":"Decide how to respond.","targets":[],"anchors":{},
		"actors":{"mother":20,"protagonist":1},"party":{"role":"owner","owner":"Aster","members":[]},
		"scene":{"id":"measure.rescue.abduction","token":"rescue-run:measure.rescue.abduction",
			"actors":{"mother":20,"protagonist":1},"choice":{"id":"rescue_response","title":"Her daughter is being taken",
				"options":[{"id":"help","label":"Help her","detail":"Fight the goblins left at the ramp."},
					{"id":"watch","label":"Watch what happens","detail":"Stay back while she follows them."}],
				"selected":"","response":"","can_choose":true,"owner":"Aster","owner_is_you":true}},
		"rescue":{"stage":"choice","branch":"","can_accept":false,"can_defer":true,
			"mother":{"health":70,"max_health":70,"mana":60,"max_mana":60,"enabled":false,
				"following":false,"downed":false,"configured":false,"revives_spent":0,"level":10},
			"patient":{"actor_id":20,"can_cast":false,"lesson_remaining":1,"learned_patient_only":false},
			"daughter":{"caged":true,"rescued":false},"encounters":[{"id":"ramp_1","alive":true,"cleared":false}],
			"reward":{"can_choose":false,"claimed":false,"choice":""},"supplies":{"claimed":false,"can_claim":true}}}

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())

func reset_main() -> void:
	app.authenticated = true
	app.death = {}
	app.local_actor_id = 1
	app.current_map = "landfall"
	app.campaign = snapshot()
	app.actors = {1:{"kind":1,"health":20,"alive":true,"x":253,"y":154},20:{"kind":2,"name":"Injured woman","health":70,"alive":true,"x":253,"y":154},
		21:{"kind":2,"name":"Ordinary villager","health":20,"alive":true}}
	main.set("_disconnect_console_active", false)
	main.set("actor_nodes", {1:local,20:mother})
	(main.get("_grounded_actors") as Dictionary).clear()
	(main.get("_grounded_actors") as Dictionary)[1] = true
	controller.set("playing", true)
	controller.set("test_replay", false)
	controller.set("retries", 0)
	controller.set("test_events", [])
	controller.set("test_context", {"run_id":"rescue-run","token":"rescue-run:measure.rescue.abduction","id":"rescue_response","waiting":true})
	(network.get("sent_frames") as Array).clear()
	network.set("fail_send", false)

func run() -> void:
	create_timer(90).timeout.connect(func(): push_error("Rescue client checks timed out"); quit(1))
	root.size = Vector2i(1280, 720)
	expect("campaign_rescue_v1" in EloriaProtocol.CLIENT_CAPABILITIES and "landfall_underground_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "rescue admission advertises both its implementation and the ordinary underground map support")
	expect(decode(snapshot()).type == "campaign", "the full rescue packet and both native choice options decode")
	var current_schema := snapshot(); current_schema.rescue.patient.erase("learned_patient_only")
	current_schema.stage = "boss_confrontation"; current_schema.rescue.stage = "boss_confrontation"
	current_schema.scene = {}; current_schema.rescue.daughter.returned = false
	expect(decode(current_schema).type == "campaign", "the global Magic 0 contract needs no patient-only level permission and admits the real boss confrontation")
	current_schema.rescue.at_entrance = "yes"
	expect(decode(current_schema).type == "invalid", "mine entrance presentation metadata requires an actual boolean")
	current_schema.rescue.at_entrance = true; current_schema.map = "greenlight"
	expect(decode(current_schema).type == "invalid", "this rescue cannot borrow an unrelated campaign's map or private actors")
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	var no_knowledge: Array[int] = []
	var normal_reagents := {0:{"image_id":584,"quantity":1},1:{"image_id":586,"quantity":1}}
	expect(int(catalog.spell(1).level) == 0 and catalog.unavailable_reasons(1, no_knowledge, {"magic":0,"ether":5}, normal_reagents).is_empty(), "ordinary Heal Target is available at Magic 0 outside the rescue")
	expect(not catalog.unavailable_reasons(1, no_knowledge, {"magic":0,"ether":4}, normal_reagents).is_empty(), "Magic 0 does not waive the ordinary five-mana cost")
	expect(not catalog.unavailable_reasons(1, no_knowledge, {"magic":0,"ether":5}, {}).is_empty(), "Magic 0 retains ordinary reagent requirements")
	expect(decode({"version":1,"active":false}).type == "campaign", "legacy campaign availability packets stay compatible")
	for invalid: String in ["health","mana","level","lesson","patient_binding","stage","kind","claimed","option","three_options","wrong_scene","missing_patient"]:
		var state := snapshot()
		match invalid:
			"health": state.rescue.mother.health = 71
			"mana": state.rescue.mother.mana = -1
			"level": state.rescue.mother.level = 11
			"lesson": state.rescue.patient.lesson_remaining = 2
			"patient_binding": state.rescue.patient.actor_id = 21
			"stage": state.rescue.stage = "made_up"
			"kind": state.kind = "bank"
			"claimed": state.rescue.reward.claimed = true; state.rescue.reward.can_choose = true
			"option": state.scene.choice.options[1].id = "attack_mother"
			"three_options": state.scene.choice.options.append(state.scene.choice.options[0].duplicate())
			"wrong_scene": state.scene.id = "measure.landing.plan"
			"missing_patient": state.rescue.erase("patient")
		expect(decode(state).type == "invalid", "malformed rescue " + invalid + " is rejected")
	var injured := snapshot()
	injured.stage = "injured"; injured.rescue.stage = "injured"; injured.rescue.branch = "watch"
	injured.rescue.mother.health = 1; injured.rescue.mother.downed = true; injured.rescue.patient.can_cast = true
	injured.scene.id = "measure.rescue.injured"; injured.scene.choice.can_choose = false; injured.scene.choice.selected = "watch"
	expect(decode(injured).type == "campaign", "the injured scene retains the selected read-only choice and patient lesson")
	var missing := snapshot(); missing.erase("rescue")
	expect(decode(missing).type == "invalid", "an active rescue cannot omit its gameplay state")
	var corpse_state := snapshot()
	corpse_state.map = "landfall_insides"; corpse_state.stage = "boss_defeated"; corpse_state.rescue.stage = "boss_defeated"
	corpse_state.scene = {"id":"measure.rescue.captive","token":"rescue-run:measure.rescue.captive","actors":{"mother":20,"goblin_boss":31},
		"corpse_template":{"actor_id":31,"actor_type":624,"kind":5,"name":"Goblin captor","x":83,"y":62,
			"rotation":-16384,"frame":3,"health":0,"max_health":100,"scale":1.0,
			"death_presentation":{"kind":"actor_death","actor_id":31,"temporary":false,"hold_for_scene":true,
				"elapsed":3.0,"animation_seconds":2.7,"hold_seconds":3.0,"fade_seconds":4.0}}}
	expect(decode(corpse_state).type == "campaign", "one actual held dead boss can supply a bound non-gameplay scene template")
	for invalid: String in ["alive","foreign_kind","foreign_type","binding","coordinate","fractional_rotation","scale","name","hold_type","not_held","death_kind","death_id","negative_elapsed","oversized","wrong_scene"]:
		var state := corpse_state.duplicate(true)
		var body: Dictionary = state.scene.corpse_template
		match invalid:
			"alive": body.health = 1
			"foreign_kind": body.kind = 2
			"foreign_type": body.actor_type = 671
			"binding": body.actor_id = 32; body.death_presentation.actor_id = 32
			"coordinate": body.x = 2048
			"fractional_rotation": body.rotation = 1.5
			"scale": body.scale = 0
			"name": body.name = "x".repeat(129)
			"hold_type": body.death_presentation.hold_for_scene = "true"
			"not_held": body.death_presentation.hold_for_scene = false
			"death_kind": body.death_presentation.kind = "death"
			"death_id": body.death_presentation.actor_id = 32
			"negative_elapsed": body.death_presentation.elapsed = -1
			"oversized": body.padding = "x".repeat(4096)
			"wrong_scene": state.scene.id = "measure.rescue.resolved"
		expect(decode(state).type == "invalid", "corpse template " + invalid + " cannot create an unbound, live or oversized visual")
	network = root.get_node("Network"); network.set_process(false)
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nvar fail_send:=false\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tif fail_send:return ERR_UNAVAILABLE\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the production transport recorder compiles")
	network.set_script(recorder); network.call("block_for_hud_preview")
	var frames: Array = network.get("sent_frames")
	for option: String in ["help", "watch"]:
		frames.clear()
		expect(network.call("campaign_rescue_choice", "rescue-run", "rescue-run:measure.rescue.abduction", option) == OK \
			and frames.back() == EloriaProtocol.chat("#campaign rescue_choice rescue-run rescue-run:measure.rescue.abduction " + option), "native " + option + " transport binds the run and token")
	for args: Array in [["bad run","token","help"],["run","bad token","watch"],["run","token","repair"]]:
		frames.clear()
		expect(network.call("campaign_rescue_choice", args[0], args[1], args[2]) == ERR_INVALID_PARAMETER and frames.is_empty(), "invalid rescue choice identities never reach the wire")
	for reward: String in ["sword", "bow", "wand"]:
		frames.clear()
		expect(network.call("campaign_rescue_reward", reward) == OK and frames.back() == EloriaProtocol.chat("#campaign reward " + reward), "the " + reward + " reward uses the native one-time claim")
		frames.clear()
		expect(network.call("campaign_rescue_reward_choice", "rescue-run", "rescue-run:measure.rescue.resolved", reward) == OK \
			and frames[0] == EloriaProtocol.chat("#campaign rescue_reward rescue-run rescue-run:measure.rescue.resolved " + reward), "the " + reward + " cinematic reward is bound to the current run and film")
	frames.clear()
	expect(network.call("campaign_rescue_reward", "gold") == ERR_INVALID_PARAMETER and frames.is_empty(), "unoffered reward names are rejected")
	frames.clear()
	expect(network.call("campaign_rescue_burn", "rescue-run", "rescue-run:measure.rescue.shadow") == OK \
		and frames[0] == EloriaProtocol.chat("#campaign rescue_burn rescue-run rescue-run:measure.rescue.shadow"), "the authored fire event uses a token-bound native request")
	frames.clear()
	expect(network.call("campaign_rescue_burn", "bad run", "token") == ERR_INVALID_PARAMETER and frames.is_empty(), "invalid fire-event identities never reach the wire")
	expect(network.call("campaign_rescue_depart", "rescue-run", "rescue-run:measure.rescue.commitment") == OK \
		and frames[0] == EloriaProtocol.chat("#campaign rescue_depart rescue-run rescue-run:measure.rescue.commitment"), "the spoken agreement starts only its token-bound native departure")
	frames.clear()
	expect(network.call("campaign_rescue_depart", "bad run", "token") == ERR_INVALID_PARAMETER and frames.is_empty(), "invalid departure identities never reach the wire")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main); main.set_process(false); main.hide()
	var double := GDScript.new()
	double.source_code = 'extends "res://src/world/campaign_scene.gd"\nvar test_context:Dictionary={}\nvar test_events:Array=[]\nvar test_replay:=false\nvar retries:=0\nfunc choice_context()->Dictionary:return test_context\nfunc inspection_context()->Dictionary:return test_context\nfunc event_context()->Dictionary:return test_context\nfunc presentation_state()->Dictionary:return {"events":test_events}\nfunc is_replaying()->bool:return test_replay\nfunc choice_send_failed()->void:retries+=1\nfunc inspection_send_failed()->void:retries+=1\n'
	expect(double.reload() == OK, "the scene guard fixture preserves the production public API")
	var previous: Node = main.get("campaign_scene")
	controller = double.new(); main.add_child(controller); main.set("campaign_scene", controller); previous.queue_free()
	local = Node3D.new(); mother = Node3D.new(); root.add_child(local); root.add_child(mother)
	app = root.get_node("AppState")
	# These deliberately bare actor bindings exercise transport guards, not the
	# full actor selection-ring renderer (covered by the native integration).
	app.state_changed.disconnect(Callable(main, "_on_state_changed"))
	reset_main()
	var held_payload := {"kind":"actor_death","actor_id":20,"temporary":false,"hold_for_scene":true}
	var held := EloriaProtocol.decode_server(212, JSON.stringify(held_payload).to_utf8_buffer())
	expect(held.type == "magic_state" and bool(held.data.hold_for_scene), "the native corpse hold flag survives strict magic-state decoding")
	app.call("_on_packet", 212, JSON.stringify(held_payload).to_utf8_buffer())
	expect(bool(app.actors[20].death_presentation.get("hold_for_scene", false)), "the existing AppState reducer preserves the authored corpse hold")
	held_payload.hold_for_scene = false
	app.call("_on_packet", 212, JSON.stringify(held_payload).to_utf8_buffer())
	expect(not bool(app.actors[20].death_presentation.hold_for_scene), "a native release replaces the corpse hold rather than leaving stale presentation state")
	held_payload.hold_for_scene = "true"
	expect(EloriaProtocol.decode_server(212, JSON.stringify(held_payload).to_utf8_buffer()).type == "invalid", "malformed corpse hold values cannot enable an indefinite presentation")
	var replay_stage := Node3D.new(); root.add_child(replay_stage)
	var replay_adapter := CoordinateAdapter.new({"serverOrigin":[0,0],"metresPerTile":1.0,"walkingHeight":0.0})
	var corpse := {"actor_id":901,"actor_type":624,"kind":5,"name":"Mire goblin","x":5,"y":6,"rotation":0,
		"footprint":Vector2i.ONE,"health":0,"max_health":50,"alive":false,
		"death_presentation":{"temporary":true,"elapsed":50.0,"hold_for_scene":false}}
	var untouched := corpse.duplicate(true)
	var live_ids := (main.get("actor_nodes") as Dictionary).keys()
	var ungrounded: Node3D = main.call("_campaign_replay_visual", corpse, replay_stage, replay_adapter, func(_point: Vector3) -> float: return NAN)
	expect(ungrounded == null and replay_stage.get_child_count() == 0, "missing streamed ground is rejected before loading or instantiating the replay model")
	var replay_actor: Node3D = main.call("_campaign_replay_visual", corpse, replay_stage, replay_adapter, func(_point: Vector3) -> float: return 3.5)
	expect(is_instance_valid(replay_actor), "the preview seam can build a removed boss's native read-only replay body")
	if is_instance_valid(replay_actor):
		expect(int(replay_actor.get("collision_layer")) == 0 and int(replay_actor.get("collision_mask")) == 0, "a replay body cannot intercept native world input")
		expect(bool(replay_actor.get("_corpse_scene_held")) and not bool(replay_actor.get("_corpse_temporary")), "a dead replay body waits for the authored dissolve rather than the ordinary corpse timer")
		expect(float(replay_actor.get("_death_elapsed")) >= 50.0, "an already-dead missing body preserves its completed death pose rather than falling again")
		var dot := replay_actor.get_node_or_null("MapDot") as Node3D
		expect(dot == null or not dot.visible, "a replay clone creates no minimap ghost")
		expect(is_equal_approx(replay_actor.global_position.y, 3.5), "read-only replay bodies use the actual supplied surface sample")
	expect(corpse == untouched and (main.get("actor_nodes") as Dictionary).keys() == live_ids and not app.actors.has(901), "replay construction does not register a fake gameplay actor or mutate the cached native DTO")
	replay_stage.queue_free()
	for option: String in ["help", "watch"]:
		reset_main(); main.call("_on_campaign_scene_choice", option)
		expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign rescue_choice rescue-run rescue-run:measure.rescue.abduction " + option), "Main sends the live owner " + option + " choice during the modal film")
	for option: String in ["accept", "defer"]:
		reset_main()
		app.campaign.scene.id = "measure.rescue.commitment"; app.campaign.scene.token = "rescue-run:measure.rescue.commitment"
		app.campaign.scene.choice.id = "rescue_accept"
		app.campaign.scene.choice.options = [{"id":"accept","label":"Go together","detail":"Lead the rescue into the mine."},{"id":"defer","label":"Return later","detail":"Save the rescue and return."}]
		controller.set("test_context", {"run_id":"rescue-run","token":"rescue-run:measure.rescue.commitment","id":"rescue_accept","waiting":true})
		expect(decode(app.campaign).type == "campaign", "the two-way commitment uses the same strict choice schema")
		main.call("_on_campaign_scene_choice", option)
		expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign rescue_commit rescue-run rescue-run:measure.rescue.commitment " + option), "Main sends the owner " + option + " commitment without granting client progress")
	for option: String in ["sword", "bow", "wand"]:
		reset_main(); app.campaign.party.role = "eligible"
		app.campaign.scene.id = "measure.rescue.resolved"; app.campaign.scene.token = "rescue-run:measure.rescue.resolved"
		app.campaign.scene.actors = {"mother":20,"protagonist":2,"recipient":1}
		app.campaign.rescue.reward.can_choose = true
		app.campaign.scene.choice.id = "rescue_reward"
		app.campaign.scene.choice.options = [{"id":"sword","label":"Sword","detail":"Attack and Defense."},{"id":"bow","label":"Bow","detail":"Ranging."},{"id":"wand","label":"Wand","detail":"Magic."}]
		controller.set("test_context", {"run_id":"rescue-run","token":"rescue-run:measure.rescue.resolved","id":"rescue_reward","waiting":true})
		expect(decode(app.campaign).type == "campaign", "the three-way personal reward uses the shared strict choice schema")
		main.call("_on_campaign_scene_choice", option)
		expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign rescue_reward rescue-run rescue-run:measure.rescue.resolved " + option), "a guest chooses their own cinematic " + option + " while the story owner is elsewhere")
		frames.clear(); app.campaign.scene.actors.recipient = 2
		main.call("_on_campaign_scene_choice", option)
		expect(frames.is_empty(), "a portrait or queued " + option + " choice bound to another recipient cannot claim a reward")
	for blocker: String in ["replay","helper","not_owner","selected","old_run","old_token","old_choice","not_waiting","wrong_scene","map","inactive","death","disconnect","not_playing","ungrounded","missing_mother","foreign_mother","missing_owner"]:
		reset_main()
		match blocker:
			"replay": controller.set("test_replay", true)
			"helper": app.campaign.party.role = "eligible"
			"not_owner": app.campaign.scene.choice.owner_is_you = false
			"selected": app.campaign.scene.choice.selected = "help"; app.campaign.scene.choice.can_choose = false
			"old_run": controller.get("test_context").run_id = "older"
			"old_token": controller.get("test_context").token = "older"
			"old_choice": controller.get("test_context").id = "cart_release"
			"not_waiting": controller.get("test_context").waiting = false
			"wrong_scene": app.campaign.scene.id = "measure.rescue.resolved"
			"map": app.current_map = "greenlight"
			"inactive": app.campaign.active = false
			"death": app.death = {"dead":true}
			"disconnect": main.set("_disconnect_console_active", true)
			"not_playing": controller.set("playing", false)
			"ungrounded": (main.get("_grounded_actors") as Dictionary).clear()
			"missing_mother": (main.get("actor_nodes") as Dictionary).erase(20)
			"foreign_mother": app.actors[20].kind = 1
			"missing_owner": app.campaign.scene.actors.protagonist = 2
		main.call("_on_campaign_scene_choice", "help")
		expect(frames.is_empty(), blocker + " prevents a stale or unauthorized rescue choice")
	reset_main(); network.set("fail_send", true); main.call("_on_campaign_scene_choice", "help")
	expect(frames.is_empty() and int(controller.get("retries")) == 1, "failed transport releases the local choice for retry")
	reset_main(); app.death = {"dead":true}
	expect(main.call("_rescue_static_during_death"), "native revival can retain the current private rescue's static dressing while controls stay blocked")
	app.current_map = "greenlight"
	expect(not main.call("_rescue_static_during_death"), "death cannot retain rescue dressing across maps")
	reset_main(); app.death = {"dead":true}; app.authenticated = false
	expect(not main.call("_rescue_static_during_death"), "disconnect clears the rescue lighting lease even during death")
	reset_main(); controller.set("playing", false)
	expect(main.call("_spell_target_candidate", 1, 20), "the bound live mother is a friendly Heal Target candidate")
	expect(not main.call("_spell_target_candidate", 1, 21), "ordinary NPCs gain no heal permission")
	app.actors[20].alive = false; app.actors[20].health = 0
	expect(main.call("_spell_target_candidate", 1, 20), "the exact downed mother remains targetable for native recovery")
	app.current_map = "greenlight"
	expect(not main.call("_spell_target_candidate", 1, 20), "a mother from another map cannot become a spell target")
	reset_main(); controller.set("playing", false); app.campaign = injured.duplicate(true)
	var casts: Array = []
	main.get("magic_selection").set("request_sender", func(data: Dictionary) -> Error: casts.append(data.duplicate(true)); return OK)
	main.call("_on_rescue_patient_heal", "rescue-run", 20)
	expect(casts.size() == 1 and casts[0] == {"op":"cast","id":1,"power":1,"target_id":20}, "the lesson button casts native Heal Target on the explicit patient without a global Magic bypass")
	casts.clear(); app.campaign.rescue.patient.can_cast = false
	main.call("_on_rescue_patient_heal", "rescue-run", 20)
	expect(casts.is_empty(), "spent or unavailable patient permission does not cast again")
	reset_main(); controller.set("playing", false); app.campaign.rescue.reward.can_choose = true; app.campaign.party.role = "eligible"
	app.campaign.scene.id = "measure.rescue.resolved"; app.campaign.scene.token = "rescue-run:measure.rescue.resolved"
	app.campaign.scene.actors.recipient = 1
	main.call("_on_rescue_reward", "wand", "rescue-run")
	expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign rescue_reward rescue-run rescue-run:measure.rescue.resolved wand"), "a participating guest chooses their own reward independently of the owner")
	frames.clear(); main.call("_on_rescue_reward", "sword", "old-run")
	expect(frames.is_empty(), "a queued reward from an old run is ignored")
	for blocker: String in ["none", "replay", "helper", "old_token", "no_event", "not_requested", "not_aftermath", "not_rewarded"]:
		reset_main()
		app.campaign.stage = "aftermath"; app.campaign.rescue.stage = "aftermath"; app.campaign.rescue.reward.claimed = true
		app.campaign.scene.id = "measure.rescue.shadow"; app.campaign.scene.token = "rescue-run:measure.rescue.shadow"
		controller.set("test_context", {"run_id":"rescue-run","token":"rescue-run:measure.rescue.shadow","id":"measure.rescue.shadow"})
		controller.set("test_events", [{"id":"rescue_burn","request":true}])
		match blocker:
			"replay": controller.set("test_replay", true)
			"helper": app.campaign.party.role = "eligible"
			"old_token": controller.get("test_context").token = "older"
			"no_event": controller.set("test_events", [])
			"not_requested": controller.get("test_events")[0].request = false
			"not_aftermath": app.campaign.rescue.stage = "daughter_freed"
			"not_rewarded": app.campaign.rescue.reward.claimed = false
		main.call("_on_campaign_scene_event", "rescue_burn")
		expect(frames.size() == (1 if blocker == "none" else 0), "authored fire " + blocker + " respects the current owner, epoch and actual event window")
	for blocker: String in ["none","replay","helper","old_token","no_event","not_requested","wrong_stage","at_entrance","declined"]:
		reset_main()
		app.campaign.stage = "to_mine"; app.campaign.rescue.stage = "to_mine"
		app.campaign.scene.id = "measure.rescue.commitment"; app.campaign.scene.token = "rescue-run:measure.rescue.commitment"
		app.campaign.scene.choice.selected = "accept"
		controller.set("test_context", {"run_id":"rescue-run","token":"rescue-run:measure.rescue.commitment","id":"measure.rescue.commitment"})
		controller.set("test_events", [{"id":"rescue_depart","request":true}])
		match blocker:
			"replay": controller.set("test_replay", true)
			"helper": app.campaign.party.role = "eligible"
			"old_token": controller.get("test_context").token = "older"
			"no_event": controller.set("test_events", [])
			"not_requested": controller.get("test_events")[0].request = false
			"wrong_stage": app.campaign.rescue.stage = "ready"
			"at_entrance": app.campaign.rescue.at_entrance = true
			"declined": app.campaign.scene.choice.selected = "defer"
		main.call("_on_campaign_scene_event", "rescue_depart")
		expect(frames.size() == (1 if blocker == "none" else 0), "departure " + blocker + " requires the accepted owner scene and cannot be sent by replay")
	reset_main(); controller.set("playing", false)
	app.stats = {"magic":0,"ether":5}; app.inventory = normal_reagents.duplicate(true); app.known_knowledge.clear()
	var book: Node = main.get("spells_window")
	app.authenticated = false
	book.call("sync")
	book.call("_on_spell_pressed", 1)
	expect(not bool((book.get("cast_button") as Button).disabled) and str((book.get("name_label") as Label).tooltip_text).contains("Magic 0"), "the ordinary spell book displays Magic 0 and enables a supplied novice cast")
	app.inventory = {}; book.call("sync"); book.call("_refresh_details")
	expect(bool((book.get("cast_button") as Button).disabled), "the spell book still blocks a novice without normal materials")
	reset_main(); controller.set("playing", false)
	app.campaign.targets = [{"id":"mother","object_id":64000,"tile":[253,154],"approach":[253,153],"label":"Speak to her","enabled":true,"completed":false}]
	main.call("_on_campaign_target", 64000, Vector2i(253,154), false)
	expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign rescue replay"), "nearby field interaction restores the missing cinematic cast instead of trusting the queued nearby flag")
	frames.clear(); app.campaign.targets[0].enabled = false
	main.call("_on_campaign_target", 64000, Vector2i(253,154), true)
	expect(frames.is_empty(), "an obsolete field button cannot use a currently disabled rescue target")
	reset_main(); controller.set("playing", false)
	app.campaign.scene.requires_ack = true
	app.campaign.targets = [{"id":"mother","object_id":64000,"tile":[253,154],"label":"Speak with the woman","enabled":true,"completed":false}]
	main.call("_on_campaign_scene_finished", str(app.campaign.scene.token), "skipped")
	expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign scene_done rescue-run rescue-run:measure.rescue.abduction"), "Skip releases the actual scene barrier without inventing a response")
	frames.clear()
	main.get("campaign_hud").call("apply_state", app.campaign, Vector2i(253,154), "landfall")
	main.get("campaign_hud").call("_request_target", "mother", 64000)
	expect(frames.size() == 1 and frames[0] == EloriaProtocol.chat("#campaign rescue replay"), "after Skip the enabled mother card requests the current cinematic conversation without inventing a response")
	for response: int in [6400,6401,6402,6403]:
		frames.clear(); main.call("_on_dialogue_option", 20, response)
		expect(frames.size() == 1 and frames[0] == EloriaProtocol.npc_response(20,response), "native mother response " + str(response) + " remains available independently of replay")
	for blocker: String in ["none", "replay", "helper", "old_token", "foreign_actor", "not_allowed", "wrong_map", "not_playing", "cancel_after_stop", "send_failure"]:
		reset_main()
		app.current_map = "landfall_insides"; app.campaign.map = "landfall_insides"
		app.campaign.stage = "boss_defeated"; app.campaign.rescue.stage = "boss_defeated"
		app.campaign.scene.id = "measure.rescue.captive"; app.campaign.scene.token = "rescue-run:measure.rescue.captive"
		app.campaign.scene.erase("choice")
		app.campaign.scene.inspection = {"id":"rescue_family","status":"pending","can_start":true,"actor_id":20,
			"object_id":64003,"path":[[79,67],[79,69],[55,26]],"approach":[55,26]}
		controller.set("test_context", {"run_id":"rescue-run","token":"rescue-run:measure.rescue.captive","id":"rescue_family","waiting":true})
		if blocker == "none":
			expect(decode(app.campaign).type == "campaign", "family inspection binds the actual mother rather than requiring a local-player actor")
		match blocker:
			"replay": controller.set("test_replay", true)
			"helper": app.campaign.party.role = "eligible"
			"old_token": controller.get("test_context").token = "old"
			"foreign_actor": app.campaign.scene.inspection.actor_id = 21
			"not_allowed": app.campaign.scene.inspection.can_start = false
			"wrong_map": app.current_map = "landfall"
			"not_playing", "cancel_after_stop": controller.set("playing", false)
			"send_failure": network.set("fail_send", true)
		var action := "cancel" if blocker == "cancel_after_stop" else "start"
		main.call("_on_campaign_scene_inspection", action)
		var should_send := blocker in ["none", "cancel_after_stop"]
		expect(frames.size() == (1 if should_send else 0), "native family " + blocker + " keeps route proof server-owned and rejects stale requests")
		if should_send:
			expect(frames[0] == EloriaProtocol.chat("#campaign rescue_family rescue-run rescue-run:measure.rescue.captive" + (" cancel" if action == "cancel" else "")), "family " + action + " addresses only the current owned native task")
		if blocker == "send_failure":
			expect(int(controller.get("retries")) == 1, "a failed family cue releases the local retry state")
	var hud: Node = main.get("campaign_hud")
	hud.call("apply_state", injured, Vector2i(253,154), "landfall")
	expect((hud.get("_patient_heal") as Button).visible and not (hud.get("_patient_heal") as Button).disabled, "the shared quest card exposes the exact eligible patient's lesson")
	var reward_state := snapshot(); reward_state.party.role = "eligible"; reward_state.rescue.reward.can_choose = true
	hud.call("apply_state", reward_state, Vector2i(79,67), "landfall")
	expect((hud.get("_rescue_rewards") as Control).visible and (hud.get("_rescue_rewards") as Control).get_child_count() == 3, "all three personal weapon choices share the existing quest card")
	hud.call("apply_state", reward_state, Vector2i.ZERO, "greenlight")
	expect(not (hud.get("_rescue_rewards") as Control).is_visible_in_tree(), "foreign-map reward controls disappear")
	var guided := snapshot()
	guided.targets = [{"id":"mother","object_id":64000,"label":"Speak to the injured woman","tile":[253,154],"enabled":true,"completed":false},
		{"id":"burn","object_id":64004,"label":"Future shadow","tile":[255,154],"enabled":false,"completed":false},
		{"id":"reward","object_id":64005,"label":"Future reward","tile":[256,154],"enabled":false,"completed":false}]
	var adapter := CoordinateAdapter.new({"serverOrigin":[282,248],"metresPerTile":1.0,"walkingHeight":0.0})
	var objects: Dictionary = {}
	for target: Dictionary in guided.targets:
		var object := MapObject3D.new(); root.add_child(object)
		object.configure({"object_id":target.object_id,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"x":target.tile[0],"y":target.tile[1],"label":target.label}, adapter, {"interactives":{"roles":{},"models":{}}})
		objects[int(target.object_id)] = object
	var guidance := preload("res://src/world/campaign_guidance.gd").new(); root.add_child(guidance)
	guidance.apply_snapshot(guided, objects, {}, "landfall", Vector2i(253,154), true, false)
	expect((objects[64000].get_node("Ring") as Node3D).visible and objects[64000].collision_layer == MapObject3D.PICK_LAYER, "the current rescue action keeps its normal labelled interaction circle")
	for id: int in [64004,64005]:
		expect(not (objects[id].get_node("Ring") as Node3D).visible and not (objects[id].get_node("MapMarker") as Node3D).visible \
			and objects[id].collision_layer == 0, "future rescue " + str(id) + " has no ring, minimap pin or pick interception")
	hud.call("apply_state", guided, Vector2i(253,154), "landfall")
	expect((hud.get("_targets") as Control).get_child_count() == 1 and str((hud.get("_guidance") as Label).text).contains("Ground circles mark ready actions"), "the existing quest card lists ready rescue work without future ending spoilers")
	guidance.apply_snapshot(guided, objects, {}, "landfall", Vector2i(253,154), true, true)
	expect(not (objects[64000].get_node("Ring") as Node3D).visible and objects[64000].collision_layer == 0, "the cinematic blocks rescue marker clutter and picks")
	guidance.clear(); guidance.queue_free()
	for object: Node in objects.values(): object.queue_free()
	reset_main(); controller.set("playing", false)
	var windows: Node = main.get("extension_windows")
	app.party = {"in_party":true,"members":[]}
	for i: int in range(8):
		app.party.members.append({"name":"Friend " + str(i),"online":true,"health":20,"max_health":20,"ether":10,"max_ether":10})
	windows.call("_sync_party")
	expect((windows.get("party_rows") as Control).get_child_count() == 9 and app.party.members.size() == 8, "eight human rows and a scoped companion coexist without taking a ninth player slot")
	var row: Node = (windows.get("party_rows") as Control).get_child(8)
	expect(not row.has_node("RemoveBot") and str((row as Control).tooltip_text).contains("finite mana"), "the companion shows resources without becoming a gauntlet bot command target")
	app.campaign.active = false; windows.call("_sync_party")
	expect((windows.get("party_rows") as Control).get_child_count() == 8, "leaving the private rescue clears only its companion row")
	var guide: Node = main.get("lantern_guide")
	guide.call("apply_campaign", {"kind":"road","active":true,"run_id":"prior-road","title":"Prior story","map":"hearthcroft"})
	guide.call("prefer_standard_quest")
	guide.call("apply_campaign", snapshot())
	expect(guide.call("using_campaign"), "the newly discovered rescue becomes the foreground shared card")
	var mine := snapshot(); mine.map = "landfall_insides"
	guide.call("apply_campaign", mine)
	expect(guide.call("campaign_entry").get("location") == "Lantern Mine" and bool(guide.call("campaign_entry").get("_exact_title")), "the single canonical rescue journal row uses its actual mine name")
	guide.call("apply_campaign", {"kind":"road","active":true,"run_id":"prior-road","title":"Prior story","map":"hearthcroft"})
	expect(not guide.call("using_campaign") and guide.call("is_campaign_tracked"), "return restores the prior standard-card preference without erasing its saved campaign tracking")
	guide.call("set_campaign_tracked", true)
	guide.call("apply_campaign", snapshot()); guide.call("prefer_standard_quest")
	guide.call("apply_campaign", {"kind":"road","active":true,"run_id":"prior-road","title":"Prior story","map":"hearthcroft"})
	expect(not guide.call("using_campaign"), "choosing a standard quest during the rescue is still respected when the prior campaign returns")
	main.set("actor_nodes", {}); app.authenticated = false; main.queue_free(); local.queue_free(); mother.queue_free()
	await process_frame; await process_frame
	print("campaign rescue: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

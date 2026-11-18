extends SceneTree
## The actual public follow-up uses portraits, ordinary NPC talk and a bound answer.
const Ready := preload("res://tests/test_campaign_scene_recovery.gd")
const Scene := preload("res://src/world/campaign_scene.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
const RescueFixture := preload("res://tests/test_campaign_rescue.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, detail: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(detail)
func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())

func contract_records() -> Array:
	var pending := RescueFixture.snapshot()
	pending.merge({"run_id":"checkin_fixture","map":"landfall_town","key":"rescue_checkin","stage":"checkin",
		"title":"Check in with Liora","available":true,"completed":false,"scene":{},
		"actors":{"mother":20,"daughter":21,"protagonist":1,"recipient":1},
		"targets":[{"id":"checkin","role":"daughter","actor_id":21,"object_id":0,"tile":[28,29],
			"label":"Ask Liora how she is feeling","enabled":true,"range":4}],
		"travel":{"map":"landfall_town","tile":[28,29],"label":"Check in with Liora","route":"Visit the family at the inn.",
			"markers":[{"map":"landfall","tile":[107,250],"label":"Landfall inn"},
				{"map":"landfall_town","tile":[28,29],"label":"Liora"}],"via":[]}},true)
	pending.erase("party")
	pending.rescue.merge({"stage":"checkin","branch":"help","can_accept":false,"can_defer":false,
		"patient":{"actor_id":0,"can_cast":false,"lesson_remaining":0},
		"daughter":{"caged":false,"rescued":true,"returned":true},"encounters":[],
		"reward":{"can_choose":false,"claimed":true,"choice":"wand"},"supplies":{"claimed":true,"can_claim":false},
		"checkin":{"completed":false,"answer":"","visiting":false}},true)
	pending.rescue.mother.configured=true
	var visit := pending.duplicate(true); visit.erase("travel"); visit.targets=[]; visit.rescue.checkin.visiting=true
	visit.scene={"id":"measure.rescue.checkin","token":"visit","requires_ack":true,"actors":visit.actors,
		"choice":{"id":"rescue_checkin","title":"How will you answer Liora?","owner":"Visitor","owner_is_you":true,
			"can_choose":true,"selected":"","response":"","options":[
				{"id":"listen","label":"Tell me what you remember.","detail":"Listen."},
				{"id":"rest","label":"You do not have to talk about it today.","detail":"Let her rest."}]}}
	var answer := visit.duplicate(true); answer.scene.choice.selected="listen"; answer.scene.choice.can_choose=false
	answer.scene.choice.response="I counted the lanterns so I could remember the way out."; answer.rescue.checkin.answer="listen"
	return [pending,visit,answer]

func run() -> void:
	create_timer(60).timeout.connect(func() -> void: push_error("Check-in checks timed out"); quit(1))
	var path := OS.get_environment("RL_CHECKIN_EVIDENCE")
	var records := contract_records()
	if not path.is_empty(): records = JSON.parse_string(FileAccess.get_file_as_string(path))
	expect("campaign_rescue_checkin_v1" in EloriaProtocol.CLIENT_CAPABILITIES,
		"the new public episode advertises its own compatibility capability")
	for row: Dictionary in records:
		expect(decode(row).type == "campaign", "the actual public visit and guide decode: " + str(decode(row).get("error", "")))
	var pending: Dictionary = records.filter(func(row: Dictionary) -> bool: return row.scene.is_empty())[0].duplicate(true)
	var visit: Dictionary = records.filter(func(row: Dictionary) -> bool: return not row.scene.is_empty() and row.scene.choice.selected == "")[0].duplicate(true)
	var answered: Dictionary = records.filter(func(row: Dictionary) -> bool: return str(row.run_id) == str(visit.run_id) and not row.scene.is_empty() and row.scene.choice.selected == "listen")[0].duplicate(true)
	var malformed := visit.duplicate(true); malformed.map = "landfall"
	expect(decode(malformed).type == "invalid", "a public check-in cannot be rebound to the rescue mine")
	malformed = visit.duplicate(true); malformed.key = "rescue"
	expect(decode(malformed).type == "invalid", "the original rescue cannot admit the public follow-up ledger")
	malformed = visit.duplicate(true); malformed.rescue.checkin.answer = "force"
	expect(decode(malformed).type == "invalid", "unknown follow-up answers never reach the scene")
	expect(Guidance.navigation_targets(pending, "landfall", true).size() == 1,
		"tracking the check-in marks the actual inn entrance outdoors")
	expect(Guidance.navigation_targets(pending, "landfall_town", false).is_empty(), "untracking hides the inn and family markers")
	var hud := Hud.new(); root.add_child(hud)
	hud.apply_state(pending, Vector2i(29,28), "landfall_town")
	expect(hud._scroll.visible and not hud._rescue.visible and not hud._leave.visible,
		"the inn visit offers talk without private-map Return or old rescue combat controls")
	var talks: Array = []
	hud.actor_target_requested.connect(func(id: int, tile: Vector2i, near: bool) -> void: talks.append([id,tile,near]))
	hud._request_target("checkin", 0)
	expect(talks.size() == 1 and talks[0][0] == int(pending.actors.daughter), "the public Talk target requests the actual Liora actor")
	var revisit := answered.duplicate(true); revisit.completed = true; revisit.rescue.checkin.completed = true
	hud.apply_state(revisit, Vector2i(29,28), "landfall_town")
	expect(hud._title.text == "Check in with Liora" and not hud._hint.text.contains("maybe you should check"),
		"revisiting the family never reopens the original quest-complete notice")
	var guide: Control = load("res://src/ui/lantern_guide.gd").new(); root.add_child(guide)
	var previous := {"kind":"shelves","run_id":"previous","title":"Existing work","active":true,"map":"landfall","targets":[]}
	guide.apply_campaign(previous); guide.set_campaign_tracked(false)
	guide.apply_campaign(visit); guide.apply_campaign(previous)
	expect(not guide.using_campaign(), "closing an explicit visit restores an unrelated quest's prior tracking preference")
	guide.apply_campaign(revisit)
	expect(not guide.rescue_completed() and guide.campaign_entry().title == "Check in with Liora",
		"the completed rescue and the optional visit have independent presentation")
	var rig := IsometricCameraController.new(); var camera := Camera3D.new(); camera.name = "Camera"
	rig.add_child(camera); camera.owner = rig; camera.unique_name_in_owner = true; root.add_child(rig)
	var hero := Ready.Actor.new(); var mother := Ready.Actor.new(); var daughter := Ready.Actor.new()
	for body: Node3D in [hero,mother,daughter]: root.add_child(body)
	mother.position = Vector3(3,0,0); daughter.position = Vector3(4,0,0)
	rig.set_focus(hero.position)
	var hero_id := int(visit.actors.protagonist)
	var nodes := {hero_id:hero,int(visit.actors.mother):mother,int(visit.actors.daughter):daughter}
	var scene := Scene.new(); root.add_child(scene); scene.set_auto_dialogue(false,false)
	var acks: Array = []; scene.presentation_finished.connect(func(token: String, reason: String) -> void: acks.append([token,reason]))
	var network := root.get_node("Network")
	var recorder := GDScript.new(); recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the production network recorder compiles")
	network.set_script(recorder); network.block_for_hud_preview()
	var frames: Array = network.get("sent_frames")
	var app := root.get_node("AppState")
	app.authenticated = true; app.death = {}; app.current_map = "landfall_town"; app.local_actor_id = hero_id
	app.actors = {hero_id:{"kind":1,"health":40},int(visit.actors.mother):{"kind":2},int(visit.actors.daughter):{"kind":2}}
	app.campaign = visit
	var main: Node = load("res://src/app/main.gd").new()
	main.set("actor_nodes",nodes); main.set("campaign_scene",scene); (main.get("_grounded_actors") as Dictionary)[hero_id] = true
	scene.choice_requested.connect(main._on_campaign_scene_choice)
	scene.update(0,visit,rig,nodes,hero_id,"landfall_town",true)
	var held: Transform3D = camera.global_transform
	expect(scene.playing and scene._dialogue.speaker_label.text == "Elen Reed", "Elen opens the visit in the shared portrait dialogue")
	expect(scene._line_continue.visible, "Continue is available on the first line")
	scene.skip(); scene.update(0,visit,rig,nodes,hero_id,"landfall_town",true)
	expect(scene._choice_waiting and acks.is_empty() and camera.global_transform.is_equal_approx(held),
		"Return to Play stops at Liora's question without changing view or answering for the player")
	frames.clear(); (scene._choice_dialog.option_buttons.listen as Button).pressed.emit()
	expect(frames == [EloriaProtocol.chat("#campaign rescue_checkin_choice %s %s listen" % [visit.run_id,visit.scene.token])],
		"choosing Listen sends the exact public scene-bound command")
	expect(str(visit.scene.choice.selected).is_empty(), "a sent choice cannot invent completion locally")
	app.campaign = answered; scene.update(0,answered,rig,nodes,hero_id,"landfall_town",true)
	expect(scene._dialogue.speaker_label.text == "Liora Reed" and scene._dialogue.body_label.text == answered.scene.choice.response,
		"Liora gives the authoritative follow-up in the same dialogue frame")
	scene.continue_dialogue(); scene.update(0,answered,rig,nodes,hero_id,"landfall_town",true)
	expect(scene._dialogue.speaker_label.text == "Elen Reed" and scene.blocks_input() and acks.is_empty(),
		"Elen's closing reassurance continues without exposing player control")
	scene.continue_dialogue()
	expect(not scene.blocks_input() and acks.size() == 1 and camera.global_transform.is_equal_approx(held),
		"the final Continue acknowledges once and restores the same settled player view")
	frames.clear(); main._on_campaign_scene_choice("rest")
	expect(frames.is_empty(), "a stale queued answer cannot change the completed conversation")
	var replay := answered.duplicate(true); replay.scene.requires_ack = false
	expect(scene.request_replay(replay,"landfall_town"), "the answered visit can be replayed without reopening its quest")
	scene.update(0,replay,rig,nodes,hero_id,"landfall_town",true)
	scene.skip(); scene.update(0,replay,rig,nodes,hero_id,"landfall_town",true)
	expect(scene._choice_review and scene._choice_dialog.option_buttons.listen.disabled \
		and (scene._choice_dialog._content.listen.heading as Label).text.begins_with("✓"),
		"replay shows both answers, highlights the recorded Listen answer and disables new choices")
	(scene._choice_dialog.option_buttons.rest as Button).pressed.emit()
	expect(frames.is_empty(), "even a queued replay button cannot send a new answer")
	scene._choice_dialog.continue_button.pressed.emit()
	for _i: int in range(4):
		scene.continue_dialogue(); scene.update(0,replay,rig,nodes,hero_id,"landfall_town",true)
	expect(acks.size() == 1 and frames.is_empty(), "replay cannot complete the visit or acknowledge it a second time")
	for args: Array in [["other","token","listen"],["checkin_valid","bad token","rest"],["checkin_valid","token","force"]]:
		expect(network.campaign_rescue_checkin_choice(args[0],args[1],args[2]) == ERR_INVALID_PARAMETER and frames.is_empty(),
			"malformed public visit commands never reach the wire")
	app.campaign = {}; app.actors = {}; app.authenticated = false
	main.set("actor_nodes",{}); main.set("campaign_scene",null); main.free()
	for body: Node in [scene,rig,hero,mother,daughter,hud,guide]: body.queue_free()
	await process_frame; await process_frame
	print("Rescue check-in client: %d checks; %d failures" % [checks, failures])
	quit(1 if failures else 0)

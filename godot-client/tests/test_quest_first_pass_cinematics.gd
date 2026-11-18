extends SceneTree
## Adjacent chapter conversations retain the same frame across native replies.
const Ready := preload("res://tests/test_campaign_scene_recovery.gd")
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, detail: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(detail)

func fixture() -> Dictionary:
	var rig := IsometricCameraController.new()
	var camera := Camera3D.new(); camera.name = "Camera"; rig.add_child(camera)
	camera.owner = rig; camera.unique_name_in_owner = true; root.add_child(rig)
	var player := Ready.Actor.new(); var mentor := Ready.Actor.new()
	root.add_child(player); root.add_child(mentor)
	mentor.position = Vector3(3, 0, 0); mentor.server_target = mentor.position
	rig.set_focus(player.position)
	var scene := Scene.new(); root.add_child(scene); scene.set_auto_dialogue(false, false)
	scene._definition = {"duration":20,"live_camera":"gameplay","shots":[],
		"dialogue_holds":[20],"lines":[{"at":0,"speaker":"Ilka","speaker_actor":"mentor","text":"The load is safe."}],
		"handoff":{"mode":"hold","keep_dialogue":true,"to":["next"]}}
	scene._scene_id = "measure.shelves.fire.report"
	scene._run = "old"; scene._token = "one"; scene._map = "landfall_town"
	var bindings := {"mentor":2,"recipient":1,"protagonist":1}
	var nodes := {1:player,2:mentor}
	scene._start(rig, camera, player, nodes, bindings)
	var state := {"active":true,"kind":"shelves","run_id":"old","map":"landfall_town",
		"scene":{"id":scene._scene_id,"token":"one","requires_ack":true,"actors":bindings}}
	var acks: Array = []
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: acks.append([token, reason]))
	return {"scene":scene,"rig":rig,"player":player,"mentor":mentor,"nodes":nodes,"state":state,"acks":acks}

func tick(f: Dictionary, delta := 0.016, ready := true) -> void:
	f.scene.update(delta, f.state, f.rig, f.nodes, 1, "landfall_town", ready)

func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_done")
	for key: String in ["scene","rig","player","mentor"]: f[key].queue_free()

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	expect("campaign_shelves_early_magic_v1" in EloriaProtocol.CLIENT_CAPABILITIES,
		"the reordered lessons advertise their compatible final delivery and return flow")
	var flow_path := OS.get_environment("RL_EARLY_MAGIC_EVIDENCE")
	if not flow_path.is_empty():
		var flow: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(flow_path))
		for native: Dictionary in flow.snapshots:
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type == "campaign", "the reordered native basics flow remains readable: " + str(decoded.get("error", "")))
			if str(native.get("scene", {}).get("id", "")) == "measure.shelves.basics.victory":
				expect(str(native.scene.get("variant", "")) == "early", "the native early course advertises its fade to the public temple door")
	var pacing_path := OS.get_environment("RL_PACING_EVIDENCE")
	if not pacing_path.is_empty():
		for name: String in ["legacy-water-snapshot.json", "legacy-water-partial-snapshot.json"]:
			var native: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(pacing_path.path_join(name)))
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type == "campaign", "saved Water cargo remains readable after pacing changes: " + str(decoded.get("error", "")))
	for new_token: String in ["one", "two"]:
		var f := fixture()
		var held: Transform3D = f.rig.camera.global_transform
		expect(f.scene.continue_dialogue(), "the report offers Continue immediately")
		for _i: int in range(6): tick(f, 0.2)
		expect(f.scene.blocks_input() and f.scene._dialogue.visible and f.acks.size() == 1,
			"the report remains visible while the server creates the next chapter")
		f.state.scene = {}; f.state.active = false
		tick(f, 0.2)
		expect(f.scene.blocks_input() and f.scene._dialogue.visible and f.rig.camera.global_transform.is_equal_approx(held),
			"an intermediate completed chapter snapshot keeps the continuous conversation")
		f.state.run_id = ""
		tick(f, 0.2)
		expect(f.scene.blocks_input() and f.scene._dialogue.visible,
			"an empty transition snapshot does not flash the gameplay viewport")
		f.scene._definitions = {"next":{"duration":20,"live_camera":"gameplay","shots":[],
			"dialogue_holds":[20],"required_actors":["mentor"],"cast_roles":["mentor","recipient"],
			"lines":[{"at":0,"speaker":"Ilka","speaker_actor":"mentor","text":"The next crew is ready."}]}}
		f.state.run_id = "new"; f.state.active = true
		f.state.scene = {"id":"next","token":new_token,"requires_ack":true,"actors":{"mentor":2,"recipient":1,"protagonist":1}}
		tick(f, 0.2, false)
		expect(f.scene.blocks_input() and f.scene._dialogue.visible and f.rig.camera.global_transform.is_equal_approx(held),
			"a new run and pending native bodies do not expose the player viewport")
		tick(f)
		expect(f.scene.playing and f.scene._run == "new" and f.scene._dialogue.body_label.text == "The next crew is ready.",
			"the explicit successor starts even when its token is reused by the new run")
		expect(f.rig.camera.global_transform.is_equal_approx(held) and f.scene.blocks_input() and f.acks.size() == 1,
			"the next briefing inherits one settled camera and never acknowledges twice")
		f.scene.continue_dialogue()
		expect(not f.scene.blocks_input() and f.acks.size() == 2,
			"the final conversation returns control only after its final Continue")
		dispose(f)
	var f := fixture(); f.scene.continue_dialogue()
	f.state.run_id = "unrelated"; f.state.scene = {}
	tick(f)
	expect(not f.scene.blocks_input(), "an unrelated quest cannot inherit a previous cinematic input lease")
	dispose(f)
	for interruption: String in ["kind", "map"]:
		f = fixture(); f.scene.continue_dialogue()
		f.state.run_id = ""; f.state.scene = {}; f.state.active = false
		if interruption == "kind": f.state.kind = "opening"
		f.scene.update(0.016,f.state,f.rig,f.nodes,1,"landfall" if interruption == "map" else "landfall_town",true)
		expect(not f.scene.blocks_input(), "an unrelated empty " + interruption + " snapshot releases the input lease immediately")
		dispose(f)
	f = fixture(); f.scene.continue_dialogue()
	f.scene.update(0.016,f.state,f.rig,f.nodes,1,"landfall",true)
	expect(not f.scene.blocks_input(), "an unexpected map departure releases even before the old active snapshot is replaced")
	dispose(f)
	var definitions := Scene.scene_definitions()
	f = fixture(); f.scene.cancel("test_done")
	f.scene._definition = definitions["measure.shelves.basics.delivery"].duplicate(true)
	f.scene._variant = "final"
	f.scene._run = "supplies"; f.scene._token = "water"; f.scene._scene_id = "measure.shelves.basics.delivery"
	f.scene._start(f.rig, f.rig.camera, f.player, f.nodes, {"mentor":2,"recipient":1})
	f.acks.clear(); f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.scene._scene_handoff.is_empty() and f.acks.size() == 1,
		"the final Water practice delivery closes without waiting for a nonexistent briefing")
	dispose(f)
	f = fixture(); f.scene.cancel("test_done")
	f.scene._definition = definitions["measure.shelves.basics.victory"].duplicate(true)
	f.scene._variant = "early"; f.scene._scene_id = "measure.shelves.basics.victory"
	f.scene._start(f.rig,f.rig.camera,f.player,f.nodes,{"mentor":2,"recipient":1})
	f.acks.clear(); f.scene.continue_dialogue()
	expect(f.scene.blocks_input() and f.acks.is_empty(), "early temple exit begins a fade before acknowledging the actual map departure")
	tick(f,0.6)
	expect(f.acks.size() == 1 and f.scene._exit_black.color.a == 1.0, "the temple course acknowledges only under full black")
	f.state.map = "landfall"; f.state.scene = {}; f.state.travel = {"map":"landfall_town","route":"Return to Ilka."}
	f.scene.cancel("map_changed")
	f.scene.update(0.1,f.state,f.rig,f.nodes,1,"landfall",false)
	expect(f.scene.blocks_input() and f.scene._exit_black.color.a == 1.0, "the temple exit waits for the real outdoor world and body readiness")
	f.player.position = Vector3(15,0,7); f.player.server_target = f.player.position
	f.scene.update(0.016,f.state,f.rig,f.nodes,1,"landfall",true)
	expect(not f.scene.blocks_input() and f.rig.focus.is_equal_approx(f.player.position),
		"the early lesson fades to the actual player outside despite a shop travel destination")
	f.scene.update(0.6,f.state,f.rig,f.nodes,1,"landfall",true)
	expect(not f.scene._exit_black.visible, "the ready outdoor player view fades in without a camera flight")
	dispose(f)
	f = fixture(); f.scene.cancel("test_done")
	f.scene._definition = definitions["measure.shelves.basics.victory"].duplicate(true)
	f.scene._variant = ""; f.scene._scene_id = "measure.shelves.basics.victory"
	f.scene._start(f.rig,f.rig.camera,f.player,f.nodes,{"mentor":2,"recipient":1})
	f.acks.clear(); f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks.size() == 1, "legacy final-course completion does not wait for an early-course return snapshot")
	dispose(f)
	await process_frame
	print("Quest first-pass cinematics: %d checks; %d failures" % [checks, failures])
	quit(1 if failures else 0)

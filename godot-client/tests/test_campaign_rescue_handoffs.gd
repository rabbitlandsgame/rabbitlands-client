extends SceneTree
## Frame continuity with the real orbit rig, including delayed authoritative replies.
const ReadyChecks := preload("res://tests/test_campaign_scene_recovery.gd")
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(value: bool, detail: String) -> void:
	checks += 1
	if value: print("PASS: ", detail)
	else: failures += 1; push_error(detail)

func fixture(mode := "hold") -> Dictionary:
	var rig := IsometricCameraController.new()
	var camera := Camera3D.new(); camera.name="Camera"; rig.add_child(camera)
	camera.owner=rig; camera.unique_name_in_owner=true; root.add_child(rig)
	var actor := ReadyChecks.Actor.new(); root.add_child(actor)
	actor.server_target = Vector3.ZERO
	rig.set_focus(actor.global_position)
	var scene := Scene.new(); root.add_child(scene)
	scene.set_auto_dialogue(true, false)
	scene._definition = {"duration":10,"entry_seconds":0,"exit_seconds":0,
		"native_roles":["protagonist"],"live_camera":"gameplay",
		"handoff":{"mode":mode,"to":["next"]},"shots":[]}
	scene._token = "one"; scene._run = "continuity"; scene._map = "landfall"
	scene._start(rig,rig.camera,actor,{1:actor},{"protagonist":1})
	var state := {"active":true,"kind":"rescue","run_id":"continuity","map":"landfall",
		"scene":{"id":"first","token":"one","requires_ack":true,"actors":{"protagonist":1}}}
	var acks: Array = []
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: acks.append([token,reason]))
	return {"scene":scene,"actor":actor,"rig":rig,"state":state,"acks":acks}

func tick(f: Dictionary, delta := 0.016, ready := true, here := "landfall") -> void:
	f.scene.update(delta,f.state,f.rig,{1:f.actor},1,here,ready)
func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_done"); f.scene.queue_free(); f.actor.queue_free(); f.rig.queue_free()

func run() -> void:
	root.get_node("Network").call("block_for_hud_preview")
	var f := fixture()
	var original: Transform3D = f.rig.camera.global_transform
	f.actor.position += Vector3(3,0,2); f.actor.server_target = f.actor.position
	f.scene._apply_camera()
	expect(f.rig.camera.global_transform.basis.is_equal_approx(original.basis) and f.rig.camera.global_position.is_equal_approx(original.origin+Vector3(3,0,2)),"live conversations keep the player's lens and angle, following only real walking")
	var last: Transform3D = f.rig.camera.global_transform
	f.scene.cancel("finished")
	expect(f.scene.blocks_input() and f.acks.size()==1 and not f.scene.playing,"completion acknowledges once while retaining the scene until its successor arrives")
	for i in 4: tick(f,0.2)
	expect(f.rig.camera.global_transform.is_equal_approx(last) and f.scene._layer.visible and f.scene._screen.modulate.a==1.0 and f.acks.size()==1,"a delayed server reply never reveals gameplay or resets the camera between adjacent scenes")
	f.scene._definitions = {"next":{"duration":10,"live_camera":"gameplay","native_roles":["protagonist"],"shots":[]}}
	f.state.scene = {"id":"next","token":"two","requires_ack":true,"actors":{"protagonist":1}}
	tick(f)
	expect(f.scene.playing and f.scene._token=="two" and f.rig.camera.global_transform.is_equal_approx(last),"the authenticated successor starts in the held view without a return flight")
	dispose(f)

	f=fixture("fade"); f.scene.cancel("finished"); tick(f,0.6)
	expect(f.acks.size()==1 and f.scene._exit_black.color.a==1.0,"a travel transition acknowledges only after the screen is fully black")
	f.scene.cancel("map_changed")
	expect(f.scene.blocks_input() and f.scene._exit_black.color.a==1.0,"expected map replacement retains the blackout")
	f.scene._definitions = {"next":{"duration":10,"live_camera":"gameplay","native_roles":["protagonist"],"shots":[]}}
	f.state.map="landfall_insides"; f.state.scene={"id":"next","token":"two","requires_ack":true,"actors":{"protagonist":1}}
	tick(f,0.2,false)
	expect(f.scene.blocks_input() and f.scene._exit_black.color.a==1.0,"an early successor state packet cannot clear black before CHANGE_MAP")
	tick(f,0.2,false,"landfall_insides")
	expect(f.scene.pending and f.scene._exit_black.color.a==1.0,"the new location stays concealed until the world and native bodies are ready")
	f.actor.position=Vector3(100,0,50); f.actor.server_target=f.actor.position
	tick(f,0.016,true,"landfall_insides")
	expect(f.scene.playing and f.scene._exit_black.color.a==1.0 and f.rig.focus.is_equal_approx(f.actor.position),"the new scene rebases on the actual player under black before fading in")
	tick(f,0.6,true,"landfall_insides")
	expect(not f.scene._exit_black.visible,"the successor reveals its scene smoothly")
	dispose(f)

	f=fixture("fade"); f.scene._definition.handoff={"mode":"fade","gameplay_map":"landfall_insides"}
	f.scene.cancel("finished"); tick(f,0.6)
	f.state.map="landfall_insides"; f.state.scene.requires_ack=false
	f.actor.position=Vector3(90,0,40); f.actor.server_target=f.actor.position
	tick(f,0.016,true,"landfall_insides")
	expect(not f.scene.blocks_input() and f.rig.focus.is_equal_approx(f.actor.position),"descent hands off to playable mine from its real arrival position")
	dispose(f)

	for interruption: String in ["disconnected","handoff_timeout","escape"]:
		f=fixture(); f.scene.cancel("finished")
		if interruption=="escape":
			var key:=InputEventKey.new(); key.physical_keycode=KEY_ESCAPE; key.pressed=true
			expect(f.scene.handle_input(key),"Escape is available while awaiting the next scene")
		elif interruption=="handoff_timeout":tick(f,46)
		else:f.scene.cancel(interruption)
		expect(not f.scene.is_active() and f.acks.size()==1,interruption+" releases the transition without duplicate quest acknowledgement")
		dispose(f)
	f=fixture(); f.scene._replaying=true
	f.scene.cancel("finished")
	expect(not f.scene.blocks_input() and f.scene._scene_handoff.is_empty() and f.acks.is_empty(),"read-only replay restores its saved view without waiting for or acknowledging a quest transition")
	dispose(f)
	f=fixture()
	f.scene.presentation_finished.connect(func(_token: String, _reason: String) -> void: f.scene.cancel("disconnected"))
	f.scene.cancel("finished")
	expect(not f.scene.is_active(),"a synchronous disconnect during acknowledgement cannot revive the cinematic or its blackout")
	dispose(f)

	var definitions := Scene.scene_definitions()
	for id: String in ["injured","commitment","captive","resolved"]:
		expect(definitions["measure.rescue."+id].live_camera=="gameplay",id+" keeps live player framing")
	expect("protagonist" in definitions["measure.rescue.captive"].native_roles,"the real player can walk with the rescued family")
	expect(not definitions["measure.rescue.boss"].has("reveal_on_start"),"the boss and guards remain visible before the confrontation")
	await process_frame
	print("Rescue handoff checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

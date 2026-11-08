extends SceneTree
const Scene := preload("res://src/world/campaign_scene.gd")
const Bodies := preload("res://tests/test_campaign_scene_recovery.gd")
var checks:=0
var failures:=0

func _init() -> void: run.call_deferred()
func expect(ok:bool, detail:String) -> void:
	checks+=1
	if ok:print("PASS: ",detail)
	else:failures+=1;push_error(detail)

func fixture(id:String, helper:=false) -> Dictionary:
	var rig:=IsometricCameraController.new()
	var camera:=Camera3D.new();camera.name="Camera";rig.add_child(camera)
	camera.owner=rig;camera.unique_name_in_owner=true;root.add_child(rig)
	rig.yaw_degrees=31;rig.pitch_degrees=-53;rig.distance=24
	var actor:=Bodies.Actor.new();root.add_child(actor)
	actor.server_target=Vector3(15.5,0,20.5);actor.global_position=actor.server_target
	rig.set_focus(actor.global_position);camera.fov=64
	var mother:=Bodies.Actor.new();root.add_child(mother)
	mother.server_target=Vector3(20.5,0,22.5);mother.global_position=mother.server_target
	var owner:=Bodies.Actor.new();root.add_child(owner)
	owner.server_target=Vector3(22.5,0,23.5);owner.global_position=owner.server_target
	var scene:=Scene.new();root.add_child(scene)
	scene.set_auto_dialogue(true,false);scene.reduced_motion=false
	scene._scene_id="measure.rescue."+id;scene._token="initial";scene._run="return-run";scene._map="landfall"
	scene._definition=Scene.scene_definitions()[scene._scene_id].duplicate(true)
	scene._definition.cues=[] # Camera assertions use native body locations.
	scene._choice_state={"selected":"watch"}
	scene._anchors={"mother_intercept":mother.global_position}
	var original:Transform3D=camera.global_transform
	var bindings:={"mother":2,"protagonist":7 if helper else 1}
	scene._start(rig,camera,actor,{1:actor,2:mother,7:owner},bindings)
	var state:={"active":true,"kind":"rescue","run_id":"return-run","map":"landfall",
		"actors":bindings,"anchors":{"mother_intercept":[20,22],"player_watch":[15,20]},
		"scene":{"id":scene._scene_id,"token":"initial","actors":bindings,"requires_ack":true}}
	return {"rig":rig,"scene":scene,"actor":actor,"mother":mother,"owner":owner,"nodes":{1:actor,2:mother,7:owner},
		"state":state,"original":original,"helper":helper}

func tick(f:Dictionary,delta:=0.016,here:="landfall") -> void:
	f.scene.update(delta,f.state,f.rig,f.nodes,1,here,true,CoordinateAdapter.new({"walkingHeight":0}),func(_at:Vector3)->float:return 0.0)
func dispose(f:Dictionary) -> void:
	f.scene.cancel("test_done")
	for node:Node in [f.scene,f.rig,f.actor,f.mother,f.owner]:node.queue_free()
func centered(f:Dictionary,label:String) -> void:
	expect(f.rig.focus.is_equal_approx(f.actor.global_position) and f.rig.follow_offset==Vector3.ZERO,label+" follows the local player without a cinematic offset")
	var pixel:Vector2=f.rig.camera.unproject_position(f.actor.global_position+Vector3.UP*1.2)
	expect(pixel.distance_to(root.get_visible_rect().size/2)<0.02,label+" places the player at the viewport center")
	expect(f.rig.camera.fov==64 and is_equal_approx(f.rig.distance,24) and is_equal_approx(f.rig.yaw_degrees,31),label+" preserves the player's lens, zoom and orbit")

func run() -> void:
	root.get_node("Network").call("block_for_hud_preview")
	for helper:bool in [false,true]:
		for finish:String in ["finished","skipped"]:
			var f:=fixture("abduction",helper)
			f.scene.elapsed=f.scene._duration();f.scene._camera_entry_elapsed=f.scene.elapsed;f.scene._apply_camera()
			var held:Transform3D=f.rig.camera.global_transform
			f.scene.cancel("finished")
			expect(f.scene.blocks_input() and f.rig.camera.global_transform.is_equal_approx(held),"Watch retains its establishing view between connected films")
			f.state.scene={"id":"measure.rescue.injured","token":"injured","actors":f.state.actors,"requires_ack":true}
			tick(f,0)
			expect(f.scene.playing and f.rig.camera.global_transform.is_equal_approx(held),"the injured dialogue starts without a gameplay flash")
			if finish=="skipped":f.scene.skip();tick(f,0.7)
			else:f.scene.elapsed=f.scene._duration();f.scene._apply_camera();f.scene.cancel("finished")
			centered(f,"Watch "+finish+(" helper" if helper else " owner"))
			expect(f.rig.camera.global_transform.is_equal_approx(f.original),"Watch restores the original player framing after the chained dialogue")
			var old:Vector3=f.rig.camera.global_position
			f.actor.position+=Vector3(2,0,1);f.actor.server_target=f.actor.position;f.rig.set_focus(f.actor.position)
			expect(f.rig.camera.global_position.is_equal_approx(old+Vector3(2,0,1)),"ordinary walking keeps following after Watch")
			dispose(f);await process_frame
	for id:String in ["abduction","injured","commitment","descent","boss","captive","resolved","shadow"]:
		var f:=fixture(id)
		f.scene._definition.erase("handoff") # An actual return to gameplay, not another film.
		f.scene._definition.erase("exit_transition")
		f.actor.position+=Vector3(4,0,3);f.actor.server_target=f.actor.position
		f.scene.elapsed=f.scene._duration();f.scene._camera_entry_elapsed=f.scene.elapsed;f.scene._apply_camera()
		f.scene.cancel("finished")
		centered(f,id+" completion")
		dispose(f);await process_frame
	var f:=fixture("descent")
	f.scene.cancel("finished");tick(f,0.6);f.scene.cancel("map_changed")
	f.actor.position=Vector3(520,0,548);f.actor.server_target=f.actor.position
	f.state.map="landfall_insides";f.state.scene.requires_ack=false
	tick(f,0.016,"landfall_insides")
	centered(f,"mine arrival after a faded map handoff")
	dispose(f);await process_frame
	# The remote villain frame must never become the outdoor gameplay baseline.
	for helper:bool in [false,true]:
		f=fixture("resolved",helper)
		f.scene.cancel("finished");tick(f,0.6)
		f.state.anchors.boss_body=[20,22];f.state.anchors.lich=[22,23]
		f.state.scene={"id":"measure.rescue.shadow","token":"shadow","requires_ack":true,
			"actors":{"lich":2,"goblin_boss":7}}
		tick(f,0)
		expect(f.scene.playing and f.scene._scene_id=="measure.rescue.shadow","the reward fades directly into the villain scene")
		tick(f,0.6)
		f.scene.elapsed=f.scene._duration();f.scene._apply_camera();f.scene.cancel("finished")
		tick(f,0.9)
		centered(f,"final outdoor return"+(" helper" if helper else " owner"))
		expect(not f.scene.blocks_input() and f.scene._exit_fade.get("phase")=="in",
			"final fade restores the local player under black before gameplay is revealed")
		f.state.scene.requires_ack=false;tick(f,0.9)
		expect(not f.scene.is_active(),"final reveal releases the cinematic completely")
		dispose(f);await process_frame
	print("Rescue player-camera checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

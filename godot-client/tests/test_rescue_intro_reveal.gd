extends SceneTree
## Real Main spawn/presentation paths, including warm, deferred and parked bodies.
const Bodies := preload("res://tests/test_campaign_scene_recovery.gd")
const Family := preload("res://tests/test_rescue_npc_models.gd")
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else: failures += 1; push_error(message)

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Intro reveal timed out"); quit(1))
	var app := root.get_node("AppState")
	root.get_node("Network").block_for_hud_preview()
	app.authenticated = false; app.current_map = ""; app.actors = {}
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main); main.set_process(false); main.set_physics_process(false)
	await process_frame
	var scene: Node = main.campaign_scene
	scene.set_auto_dialogue(false, false); scene.set_reduced_motion(false, false)
	app.authenticated = true; app.current_map = "landfall"; app.local_actor_id = 1
	app.selected_actor_id = -1; app.death = {}; app.combat_state = {}
	main.adapter = CoordinateAdapter.new({"walkingHeight":0})
	main.crowd.configure("all", "1")
	var roles := {"protagonist":1,"mother":2,"daughter":3,"abductor":4,"escort":5,"guard":6}
	var anchors := {}
	var definition: Dictionary = Scene.scene_definitions()["measure.rescue.abduction"]
	for beat: Dictionary in definition.shots + definition.cues:
		for key: String in ["anchor", "destination", "from", "face"]:
			var value: Variant = beat.get(key)
			if value is String and not roles.has(value) and value != "post": anchors[value] = [273,115]
	anchors.player_watch = [264,140]; anchors.mother_intercept = [263,137]
	anchors.escape_turn = [273,115]; anchors.escape_turn_2 = [272,115]
	var snapshot := {"version":1,"kind":"rescue","active":true,"run_id":"intro-reveal",
		"map":"landfall","stage":"approach","actors":roles,"anchors":anchors,
		"scene":{"id":"measure.rescue.abduction","token":"intro","requires_ack":true,"actors":roles}}
	app.campaign = snapshot
	var family := Family.new()
	app.actors = {2:family.family("Elen Reed",2),3:family.family("Liora",3,true)}
	family.free()
	for id: int in [1,4,5,6]:
		var actor := Bodies.Actor.new(); main.world_root.add_child(actor)
		actor.server_target = main.adapter.tile_center(264,140); actor.position = actor.server_target
		main.actor_nodes[id] = actor
	main.camera_rig.set_focus(main.actor_nodes[1].position)
	expect(main._spawn_actor(2,true), "warm native mother is admitted")
	expect(main._spawn_actor(3,false), "deferred daughter is admitted")
	var mother: ReplicatedActor3D = main.actor_nodes[2]
	var daughter: ReplicatedActor3D = main.actor_nodes[3]
	expect(not mother.visible and mother.collision_layer == 0, "mother cannot flash or be picked at the ramp before the film")
	expect(not daughter.visible and daughter.collision_layer == 0, "even a deferred daughter has no visible cylinder before the film")
	scene.update(0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall",false,main.adapter)
	main._present_actor(2); main._present_actor(3)
	expect(scene.pending and not scene.playing and not mother.visible and not daughter.visible, "waiting for terrain and repeated packets keep the family hidden")
	scene.cancel("test_cancel")
	expect(mother.visible and daughter.visible and mother.collision_layer != 0, "interruption releases the pending visibility lease")
	# A parked warm model takes its own fast arrival path.
	snapshot.scene.token = "intro-retry"
	main._revive_actor(2,mother,app.actors[2],main.adapter)
	expect(not mother.visible and mother.collision_layer == 0, "reviving a parked body reapplies intro hiding after drawing decisions")
	expect(main._spawn_actor(3,true,daughter), "the daughter promotes through Main's native model constructor")
	daughter = main.actor_nodes[3]
	expect(not daughter.visible and not daughter.is_model_deferred(), "a newly built daughter remains hidden until scene readiness")
	scene.update(0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall",true,main.adapter,func(_p:Vector3)->float:return 0.0)
	expect(scene.playing and mother.visible and daughter.visible, "ready terrain and the complete cast reveal the family in the film")
	expect(mother.position.is_equal_approx(main.adapter.tile_center(273,115))
		and daughter.position.is_equal_approx(main.adapter.tile_center(272,115)), "the first visible frame stages both family members at their running entrance, away from the ramp")
	var entrance: Vector3 = mother.position
	scene.update(1,snapshot,main.camera_rig,main.actor_nodes,1,"landfall",true,main.adapter,func(_p:Vector3)->float:return 0.0)
	expect(mother.position.distance_to(entrance)>0.1, "the mother then runs along the authored entrance path")
	main._present_actor(2)
	expect(mother.visible, "authoritative packets do not conceal an already playing entrance")
	scene.cancel("test_cleanup")
	snapshot.scene.requires_ack = false
	main._present_actor(2)
	expect(mother.visible and mother.collision_layer != 0, "acknowledged family remains available for normal gameplay")
	snapshot.scene.requires_ack = true; snapshot.scene.token = "map-interruption"
	scene.update(0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall",false,main.adapter)
	expect(not mother.visible, "a renewed pending entrance takes its own lease")
	scene.update(0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter)
	expect(mother.visible and mother.collision_layer != 0, "leaving the scene releases visibility and picking")
	app.authenticated = false; main._clear_world_presentation()
	expect(await ContinentChunkStream.drain_workers(self,30000), "owned loading jobs drain")
	main.queue_free(); await process_frame; await process_frame
	GlbSceneCache.clear(); NativeAnimationImporter.clear()
	print("Rescue intro-reveal checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

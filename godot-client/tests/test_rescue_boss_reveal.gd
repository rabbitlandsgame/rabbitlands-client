extends SceneTree
## Main's staged NPC arrival must wait for the cinematic to own its view.
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

class Actor extends Node3D:
	var server_target := Vector3.ZERO
	func set_cinematic_presentation(at: Vector3, yaw: float, _action: StringName, _speed: float) -> void:
		global_position = at
		rotation.y = yaw
	func end_cinematic_presentation() -> void:
		global_position = server_target

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Boss reveal timed out"); quit(1))
	var app := root.get_node("AppState")
	root.get_node("Network").block_for_hud_preview()
	app.authenticated = false
	app.current_map = ""
	app.actors = {}
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	await process_frame
	var scene: Node = main.campaign_scene
	scene.set_auto_dialogue(false, false)
	scene.set_reduced_motion(false, false)
	app.authenticated = true
	app.current_map = "landfall_insides"
	app.local_actor_id = 1
	app.selected_actor_id = -1
	app.death = {}
	app.combat_state = {}
	main.adapter = CoordinateAdapter.new({"walkingHeight":0.025})
	main.crowd.configure("all", "1")
	var roles := {"protagonist":1,"mother":2,"daughter":3,"goblin_boss":20,"boss_minion_1":21,"boss_minion_2":22}
	var snapshot := {"version":1,"kind":"rescue","active":true,"run_id":"reveal-run",
		"map":"landfall_insides","stage":"boss_confrontation","actors":roles,
		"anchors":{"boss_return":[1,0],"boss_minion_1":[3,0],"boss_minion_2":[-1,0]},
		"scene":{"id":"measure.rescue.boss","token":"boss-entry","requires_ack":true,"actors":roles}}
	app.campaign = snapshot
	app.actors = {20:{"actor_id":20,"actor_type":624,"kind":2,"name":"Goblin boss",
		"map":"landfall_insides","x":1,"y":0,"rotation":0,"health":28,"max_health":28,
		"alive":true,"appearance":{},"equipment_visuals":{},"equipment_fallback_parts":[]}}
	for role: String in roles:
		if int(roles[role]) in [20,22]: continue
		var actor := Actor.new()
		main.world_root.add_child(actor)
		main.actor_nodes[int(roles[role])] = actor
	# A campaign announcement arrives before the staged body, as on the wire.
	expect(main.call("_spawn_actor",20,true), "Main builds the actual staged goblin")
	var boss: ReplicatedActor3D = main.actor_nodes[20]
	expect(not boss.visible and boss.collision_layer == 0, "staged boss is hidden and unpickable immediately after arrival")
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter,func(_p:Vector3)->float:return 0.0)
	expect(scene.pending and not scene.playing and not boss.visible, "missing terrain or cast cannot leak the boss into gameplay")
	expect(not main.actor_nodes[21].visible, "the staged minion also waits for the establishing shot")
	main.call("_present_actor",20)
	expect(not boss.visible and boss.collision_layer == 0, "a repeated actor snapshot cannot reveal a waiting boss")
	scene.cancel("test_cancel")
	expect(boss.visible and boss.collision_layer != 0, "cancelling a pending film releases its visibility lease")
	snapshot.scene.token = "boss-entry-2"
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter,func(_p:Vector3)->float:return 0.0)
	expect(not boss.visible, "an existing staged boss is concealed for a renewed presentation")
	var late := Actor.new()
	main.world_root.add_child(late)
	main.actor_nodes[22] = late
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",true,main.adapter,func(_p:Vector3)->float:return 0.0)
	expect(scene.playing and boss.visible and boss.collision_layer != 0, "the complete cast is revealed as the cinematic starts")
	for frame in 4:
		main.call("_present_actor",20)
		scene.update(0.1,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",true,main.adapter,func(_p:Vector3)->float:return 0.0)
		expect(boss.visible, "snapshots keep the boss visible during its establishing shot")
	# A new authoritative token can interrupt a previous read-only replay.
	scene._replaying = true
	snapshot.scene.token = "boss-after-replay"
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter)
	expect(scene.pending and not boss.visible and boss.collision_layer == 0, "a replaced replay cannot expose the next pending cast")
	scene.cancel("test_cleanup")
	expect(boss.visible and boss.collision_layer != 0, "cinematic cleanup restores ordinary boss presentation")
	snapshot.scene.requires_ack = false
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter)
	expect(boss.visible and boss.collision_layer != 0, "an acknowledged live boss is not hidden again")
	snapshot.scene.requires_ack = true
	snapshot.scene.token = "map-interruption"
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter)
	expect(not boss.visible, "a new pending reveal acquires its own lease")
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall",false,main.adapter)
	expect(boss.visible and boss.collision_layer != 0, "map interruption restores visibility and picking")
	snapshot.scene.token = "timed-out-reveal"
	scene.update(0.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter)
	scene.update(46.0,snapshot,main.camera_rig,main.actor_nodes,1,"landfall_insides",false,main.adapter)
	main.call("_present_actor",20)
	expect(boss.visible and boss.collision_layer != 0, "failed loading never leaves the boss permanently invisible")
	app.authenticated = false
	main.call("_clear_world_presentation")
	expect(await ContinentChunkStream.drain_workers(self,30000), "owned resource jobs drain")
	main.queue_free()
	await process_frame
	await process_frame
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	print("RESCUE_BOSS_REVEAL checks=",checks," failures=",failures)
	quit(0 if failures == 0 else 1)

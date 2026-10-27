extends SceneTree
## Real published mine + real Main visual factory in native headless physics.
## Only the film's proxy is rewritten; no local action awards quest progress.
const Cutaway := preload("res://src/world/campaign_cutaway.gd")
const RescueFixture := preload("res://tests/test_campaign_rescue.gd")
var checks := 0
var failures := 0

class LocalActor extends Node3D:
	var server_target := Vector3.ZERO

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ",message)
	else:
		failures += 1
		push_error(message)

func snapshot() -> Dictionary:
	var state := RescueFixture.snapshot()
	state.stage = "aftermath"
	state.scene = {"id":"measure.rescue.shadow","token":"remote-shadow","requires_ack":true,
		"actors":{"protagonist":1},"cutaway":{"map":"landfall_insides",
		"anchors":{"boss_body":[83,62],"lich":[85,64]},"actors":{
			"goblin_boss":{"actor_id":2242,"actor_type":624,"kind":5,"name":"Goblin captor",
				"x":83,"y":62,"rotation":-16384,"frame":3,"health":0,"max_health":100,
				"scale":1.0,"appearance":{},"equipment_visuals":{},
				"death_presentation":{"actor_id":2242,"animation_seconds":3.0,"elapsed":3.0,
					"hold_seconds":3.0,"fade_seconds":4.0,"hold_for_scene":true,"temporary":false}},
			"lich":{"actor_id":2247,"actor_type":671,"kind":2,"name":"???","x":85,"y":64,
				"rotation":0,"frame":7,"health":20,"max_health":20,"scale":1.0,"appearance":{},"equipment_visuals":{}}}}}
	return state

func run() -> void:
	create_timer(150).timeout.connect(func() -> void: push_error("Cutaway test timed out"); quit(1))
	var network := root.get_node("Network")
	network.call("block_for_hud_preview")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	await process_frame
	var module: Node3D = main.campaign_cutaway
	var state := snapshot()
	var original := JSON.stringify(state)
	var registry: Dictionary = main.map_registry
	var outside := CoordinateAdapter.new(MapRegistry.resolve(registry,"landfall").coordinateTransform)
	var local := LocalActor.new()
	main.world_root.add_child(local)
	local.position = outside.tile_center(332,81)
	local.server_target = local.position
	var nodes := {1:local}
	var dtos := {1:{"actor_id":1,"x":332,"y":81,"health":100}}
	module.prepare(state,"landfall",0)
	var pending: Dictionary = module.view_context(state,nodes,dtos,outside,func(_p: Vector3) -> float:return NAN)
	expect(pending.remote and not pending.ready and pending.snapshot.map == "landfall","remote loading leaves the authenticated map outdoors and waits without moving the player")
	expect(pending.snapshot.scene.anchors.boss_body == [83,62] and pending.snapshot.scene.actors.goblin_boss < 0,"remote anchors and proxy-only role IDs exist before shared-controller readiness is evaluated")
	expect(pending.dtos[pending.snapshot.scene.actors.goblin_boss].death_presentation.actor_id == pending.snapshot.scene.actors.goblin_boss,"the copied held-death record uses the visual clone ID consistently")
	var deadline := Time.get_ticks_msec()+70000
	while not module.status().ready and str(module.status().error).is_empty() and Time.get_ticks_msec()<deadline:
		await process_frame
		await physics_frame
		module.prepare(state,"landfall",0.016)
	expect(module.status().ready,"the actual maintained published mine imports and grounds both real native visual models")
	if not module.status().ready:
		push_error(str(module.status()))
		module.clear()
		await ContinentChunkStream.drain_workers(self,30000)
		main.queue_free()
		await process_frame
		quit(1)
		return
	var view: Dictionary = module.view_context(state,nodes,dtos,outside,func(_p: Vector3) -> float:return NAN)
	expect(view.ready and view.adapter != outside and view.nodes.size() == 3 and nodes.size() == 1,"the remote context augments a separate actor view and adapter without registering gameplay actors")
	expect(JSON.stringify(state) == original and state.scene.actors == {"protagonist":1} and state.scene.cutaway.actors.goblin_boss.actor_id == 2242,"neither the native source state nor any original native ID is rewritten")
	var boss: ReplicatedActor3D = view.nodes[view.snapshot.scene.actors.goblin_boss]
	var lich: ReplicatedActor3D = view.nodes[view.snapshot.scene.actors.lich]
	expect(boss.collision_layer == 0 and boss.collision_mask == 0 and lich.collision_layer == 0,"remote native-looking bodies cannot become gameplay collision or pick targets")
	boss._death_elapsed = 100
	boss._update_corpse_pose()
	expect(boss._corpse_scene_held and is_zero_approx(boss._corpse_transparency),"the real held goblin body cannot auto-dissolve before the authored flame")
	expect(is_finite(module.surface_height(module.focus_world)),"the remote camera and bodies use real published navigation surfaces")
	var ray := PhysicsRayQueryParameters3D.create(module.focus_world+Vector3.UP*200,module.focus_world+Vector3.DOWN*1800,WorldLoader.NAVIGATION_SURFACE_LAYER)
	expect(module.get_world_3d().direct_space_state.intersect_ray(ray).is_empty(),"remote floor collision is absent from ordinary gameplay navigation rays")
	module.set_presenting(true)
	expect(module.presenting and boss.is_visible_in_tree(),"the private remote cast and actual room appear only for an active film")
	var wrong_rooms_hidden := true
	var mine_lamps := 0
	for light: Node3D in module.map_lights.get_children():
		if str(light.name).begins_with("lantern_mine-lamp-"): mine_lamps += 1
		elif str(light.name) != "lantern_mine-daylight": wrong_rooms_hidden = wrong_rooms_hidden and not light.is_visible_in_tree()
	expect(mine_lamps == 10 and wrong_rooms_hidden,"ordinary SecretSections excludes other-room fill lights from the ten real mine lanterns")
	var replay: Dictionary = module.view_context(state,nodes,dtos,outside,func(_p: Vector3) -> float:return NAN,true)
	module.set_presenting(true,false)
	expect(not replay.nodes.has(view.snapshot.scene.actors.lich) and not lich.is_visible_in_tree() and module.presenting,"replay geometry stays available while base actors are hidden for the controller's fresh scoped clones")
	module.set_presenting(false)
	expect(not boss.is_visible_in_tree() and not lich.is_visible_in_tree(),"returning at black hides all remote visuals before outdoor gameplay is revealed")
	expect(local.global_position == local.server_target and nodes.size() == 1,"loading and replay never move or replace the real outdoor player")
	# Exercise Main's real pending/proxy/lighting/return path with the loaded room.
	var app := root.get_node("AppState")
	app.authenticated = true
	app.local_actor_id = 1
	app.current_map = "landfall"
	app.death = {}
	app.actors = dtos
	app.campaign = state
	main.adapter = outside
	main.actor_nodes = nodes
	main._grounded_actors[1] = true
	main.camera_rig.set_focus(local.global_position)
	var camera_before: Transform3D = main.camera_rig.camera.global_transform
	main._update_campaign(0)
	expect(main.campaign_scene.playing and module.presenting and main.lantern_mine_lighting.is_active(),"Main starts the remote film through the normal shared controller and mine lighting lease")
	expect(main.campaign_scene._actors.has("goblin_boss"),"the shared film binds its authorized remote goblin role")
	main.campaign_scene.skip()
	main._update_campaign(0.8)
	expect(not main.campaign_scene.playing and not module.presenting and main.camera_rig.camera.global_transform.is_equal_approx(camera_before),"Main restores the exact outdoor player view under full black before hiding the remote room")
	expect(not main.lantern_mine_lighting.is_active() and main.campaign_scene._exit_black.color.a == 1,"the mine environment lease ends at the hidden camera handoff")
	main._update_campaign(0.8)
	expect(not main.campaign_scene._exit_black.visible and JSON.stringify(app.campaign) == original,"gameplay fade-in completes without rewriting the accepted quest state")
	expect(main.campaign_scene.request_replay(state,"landfall") and main.campaign_scene.uses_replay_cast(),"the queued replay requests its private cast before the first shared-controller update")
	main._update_campaign(0)
	var replay_boss: Node3D = main.campaign_scene._actors.get("goblin_boss")
	var replay_lich: Node3D = main.campaign_scene._actors.get("lich")
	expect(main.campaign_scene.is_replaying() and replay_boss != boss and replay_lich != lich,"the real controller binds fresh replay visuals instead of already-burned base actors")
	expect(not boss.is_visible_in_tree() and not lich.is_visible_in_tree() and replay_boss.is_visible_in_tree(),"the replay has exactly one visible cast while its actual remote room stays present")
	main._update_campaign(0.1)
	expect(main.campaign_scene.playing and main.campaign_scene._actors.goblin_boss == replay_boss,"the second replay update retains its same cast rather than aborting for actor replacement")
	main.campaign_scene.skip()
	main._update_campaign(0.8)
	main._update_campaign(0.8)
	expect(not main.campaign_scene.playing and main.camera_rig.camera.global_transform.is_equal_approx(camera_before),"remote replay returns to the exact outdoor camera through the same fade")
	main._clear_campaign_cutaway()
	expect(module.status().identity.is_empty() and module.status().cast == 0,"Main cleanup releases remote geometry and every private visual binding")
	var failed := Cutaway.new()
	main.world_root.add_child(failed)
	failed.configure({},Callable())
	failed.prepare(state,"landfall",0)
	expect(not str(failed.status().error).is_empty() and not failed.presenting,"an unavailable remote resource fails closed without changing the player's view or input")
	failed.queue_free()
	# Main's failure path acknowledges a cosmetic timeout once and stays playable.
	module.configure({},main._campaign_replay_visual)
	app.campaign = state.duplicate(true)
	app.campaign.run_id = "missing-room-run"
	app.campaign.scene.token = "missing-room-token"
	var skips: Array = []
	main.campaign_scene.presentation_finished.connect(func(_token: String,reason: String) -> void:skips.append(reason))
	main._update_campaign(0)
	main._update_campaign(0)
	expect(skips == ["loading_timeout"] and not main.campaign_scene.blocks_input(),"an unavailable cutaway skips cosmetically exactly once without hanging controls")
	main._clear_campaign_cutaway()
	app.authenticated = false
	main.actor_nodes = {}
	main.campaign_scene.cancel("test_complete")
	expect(await ContinentChunkStream.drain_workers(self,30000),"all owned remote import workers drain before test shutdown")
	main.queue_free()
	await process_frame
	await process_frame
	print("Campaign cutaway checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

extends SceneTree
var failures := 0
var checks := 0

func _init() -> void: call_deferred("run")
func check(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	root.size = Vector2i(1280, 720)
	root.get_node("Network").block_for_hud_preview()
	var main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	for frame: int in 8: await process_frame
	main.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 1
	state.actors = {1:{"actor_id":1,"name":"Player","x":0,"y":0,"rotation":0,"health":100,"sitting":false,"appearance":{"weapon":0}}}
	(main._banner_option_boxes["ranging_lock"] as CheckBox).set_pressed_no_signal(false)
	(main._banner_option_boxes["sit_lock"] as CheckBox).set_pressed_no_signal(false)
	state.player_tactics_active = true
	state.combat_state = {"active":true,"target_id":902}
	check(main._movement_locked(false), "tactics combat ignores accidental ground movement")
	check(not main._movement_locked(true), "Ctrl deliberately permits a retreat")
	check(not main._actor_input_locked(false), "Attack and Charge remain available while tactics is active")
	state.combat_state = {"active":false,"target_id":-1}
	check(not main._movement_locked(false), "enabled tactics permits ordinary travel outside combat")
	state.player_tactics_active = false
	state.combat_state = {"active":true,"target_id":902}
	check(not main._movement_locked(false), "manual combat retains ordinary movement controls")
	main.actor_resource_overlay.hide()
	main.gameplay_camera.global_position = Vector3(0, 8, 10)
	main.gameplay_camera.look_at(Vector3(0, 1, 0))
	var enemies: Array[ReplicatedActor3D] = []
	for id: int in [901,902,903]:
		var actor := ReplicatedActor3D.new()
		main.world_root.add_child(actor)
		var dto := {"actor_id":id,"kind":ReplicatedActor3D.CREATURE_ACTOR_KIND,"name":"Enemy %d" % id,"x":0,"y":0,"rotation":0,"health":10,"max_health":10}
		actor.configure(dto, CoordinateAdapter.new({"metresPerTile":1.0}), {}, {})
		actor.set_process(false); actor.set_physics_process(false)
		actor.set_nameplate_visible(true); actor.set_health_visible(true)
		actor.position = Vector3.ZERO
		main.actor_nodes[id] = actor
		state.actors[id] = dto
		enemies.append(actor)
	main._declutter_actor_overheads(902)
	check(not enemies[1].overhead_crowded(), "current opponent keeps its name and health")
	check(enemies[0].overhead_crowded() and enemies[2].overhead_crowded(), "secondary enemy labels do not overlap the opponent")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		var folder := "res://test-artifacts/stream-fixes"
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
		root.get_texture().get_image().save_png(folder.path_join("combat-labels.png"))
	enemies[0].position.x = 8.0
	main._declutter_actor_overheads(902)
	check(not enemies[0].overhead_crowded(), "secondary health returns when there is room")
	main._declutter_actor_overheads(-1)
	check(not enemies[2].overhead_crowded(), "ordinary creature banners remain visible outside combat")
	var player := ReplicatedActor3D.new()
	main.world_root.add_child(player)
	state.actors[1]["name"] = "Player"
	player.configure(state.actors[1], CoordinateAdapter.new({"metresPerTile":1.0}), {}, {})
	player.set_process(false); player.set_physics_process(false)
	main.actor_nodes[1] = player
	(main._banner_option_boxes["show_names"] as CheckBox).set_pressed_no_signal(true)
	state.combat_state = {"active":false,"target_id":-1}
	main._update_actor_resource_overlay()
	var scale_to_view: Vector2 = Vector2(main.main_viewport.size) / main.viewport_container.size
	var own: Rect2 = main.actor_resource_overlay.get_global_rect()
	var own_rect := Rect2((own.position - main.viewport_container.global_position) * scale_to_view, own.size * scale_to_view)
	var target := enemies[1]
	var shape: Rect2 = main.overhead_block_rect(Vector2.ZERO, "Enemy 902", target.occupation(), target.status_effect_count())
	var point: Vector2 = own_rect.get_center() - shape.get_center()
	var depth: float = main.gameplay_camera.global_position.distance_to(target.global_position)
	target.global_position = main.gameplay_camera.project_position(point, depth) - Vector3.UP * (target.head_height() + 0.35)
	state.combat_state = {"active":true,"target_id":902}
	main._update_actor_resource_overlay()
	var target_rect: Rect2 = main.overhead_block_rect(main.gameplay_camera.unproject_position(target.global_position + Vector3.UP * (target.head_height() + 0.35)), "Enemy 902", target.occupation(), target.status_effect_count())
	check(own_rect.intersects(target_rect), "resource panel fixture starts with an overlapping opponent label")
	own = main.actor_resource_overlay.get_global_rect()
	own_rect = Rect2((own.position - main.viewport_container.global_position) * scale_to_view, own.size * scale_to_view)
	check(not own_rect.intersects(target_rect), "own resource panel moves clear of the current opponent's banner")
	check(Rect2(Vector2.ZERO, Vector2(main.main_viewport.size)).encloses(own_rect), "resource panel remains inside the viewport near the top edge")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://test-artifacts/stream-fixes/combat-resource-panel.png")
	main.queue_free()
	await process_frame
	print("STREAM_COMBAT_CONTROLS checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)

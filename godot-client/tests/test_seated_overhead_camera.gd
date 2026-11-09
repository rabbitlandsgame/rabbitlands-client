extends SceneTree
## Real character poses, banner projection, floating feedback and camera follow.
var checks := 0
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	create_timer(90).timeout.connect(func(): push_error("Seated overhead probe timed out"); quit(99))
	root.size = Vector2i(1280, 720)
	root.get_node("Network").block_for_hud_preview()
	var app := root.get_node("AppState")
	var main = load("res://src/app/main.tscn").instantiate()
	main.set_script(load("res://tests/fixtures/offline_ui_main.gd"))
	root.add_child(main)
	for frame: int in 8: await process_frame
	main.set_process(false)
	main.set_physics_process(false)
	main.login_panel.hide()
	main.game_view.show()
	app.authenticated = true
	app.local_actor_id = 42
	app.actors = {42: {"actor_id":42, "kind":1, "health":40, "alive":true}}
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var adapter := CoordinateAdapter.new({"walkingHeight":0.0})
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		main.world_root.add_child(actor)
		var config: Dictionary = models[body]
		var dto := {"actor_id":42, "kind":1, "x":0, "y":0, "rotation":0,
			"health":40, "alive":true, "name":"Seated test", "sitting":false}
		var errors := actor.configure(dto, adapter, config,
			JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
		expect(errors.is_empty(), body + " loads: " + str(errors))
		actor.set_process(false)
		actor.set_physics_process(false)
		main.actor_nodes[42] = actor
		main.camera_rig.distance = 8.0
		main.camera_rig.pitch_degrees = -35.0
		main.camera_rig.reset_follow_offset()
		main._update_local_actor_follow()
		var standing_camera: Vector3 = main.gameplay_camera.global_position
		var standing_anchor: Vector3 = main._above_head(actor)
		main._update_actor_resource_overlay()
		var standing_banner_y: float = main.actor_resource_overlay.position.y
		actor.play_action(&"sit", true)
		actor.animation_player.advance(0.0)
		var offset := actor.posture_height_offset()
		expect(offset < -0.5, body + " seated head drops substantially")
		expect(is_equal_approx(actor.banner_head_height(), actor.head_height() + offset),
			body + " banner uses the seated height")
		var rig := actor.get_skeleton()
		var head := rig.find_bone("Head")
		var actual_drop := (actor.global_basis.inverse() * rig.global_basis *
			(rig.get_bone_global_pose(head).origin - rig.get_bone_global_rest(head).origin)).y
		expect(absf(actual_drop - offset) < 0.01, body + " height matches the rendered seated head")
		expect(is_equal_approx(actor.get_node("Nameplate").position.y,
			actor.banner_head_height() + ReplicatedActor3D.NAMEPLATE_CLEARANCE),
			body + " remote banner is lowered too")
		main._update_actor_resource_overlay()
		expect(main.actor_resource_overlay.position.y > standing_banner_y + 20.0,
			body + " local banner projects lower above the seated head")
		var seated_anchor: Vector3 = main._above_head(actor)
		expect(seated_anchor.is_equal_approx(standing_anchor + Vector3.UP * offset),
			body + " XP and level anchor share the banner drop")
		for kind: String in ["experience", "level"]:
			main._spawn_floating_feedback({"kind":kind, "skill":"harvesting", "amount":9, "level":11})
			var label: Label = main._active_floating_labels.back()
			expect(label.position.y + label.size.y < main.actor_resource_overlay.position.y,
				body + " " + kind + " appears above the lowered banner")
		main._update_local_actor_follow()
		expect(main.gameplay_camera.global_position.is_equal_approx(standing_camera + Vector3.UP * offset),
			body + " camera lowers by the same amount")
		expect(main.player_map_marker.global_position.is_equal_approx(actor.global_position + Vector3.UP * 5.0),
			body + " map marker stays at the authoritative actor position")
		actor.animation_player.advance(0.8)
		expect(is_equal_approx(actor.posture_height_offset(), offset), body + " breathing keeps the camera steady")
		actor.play_action(&"cast_defensive", true)
		expect(is_equal_approx(actor.posture_height_offset(), offset), body + " seated cast keeps the lower anchor")
		actor.set_server_scale(1.25)
		expect(is_equal_approx(actor.posture_height_offset(), offset * 1.25), body + " head drop follows actor scale")
		actor.set_server_scale(1.0)
		actor.play_action(&"stand", true)
		main._update_local_actor_follow()
		expect(is_zero_approx(actor.posture_height_offset()) and main._above_head(actor).is_equal_approx(standing_anchor),
			body + " standing restores the banner and feedback height")
		expect(main.gameplay_camera.global_position.is_equal_approx(standing_camera), body + " standing restores camera height")
		dto.sitting = true
		dto.command = 13
		actor.apply_server_state(dto, adapter)
		expect(actor.posture_height_offset() < -0.5, body + " server seating update lowers anchors")
		dto.sitting = false
		dto.command = 14
		actor.apply_server_state(dto, adapter)
		expect(is_zero_approx(actor.posture_height_offset()), body + " server standing update restores anchors")
		main.actor_nodes.erase(42)
		actor.free()
		var seated_login := ReplicatedActor3D.new()
		main.world_root.add_child(seated_login)
		dto.sitting = true
		seated_login.configure(dto, adapter, config,
			JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
		expect(seated_login.posture_height_offset() < -0.5 and is_equal_approx(
			seated_login.get_node("Nameplate").position.y,
			seated_login.banner_head_height() + ReplicatedActor3D.NAMEPLATE_CLEARANCE),
			body + " login while seated starts with a lowered banner")
		print("SEATED_HEAD_DROP ", body, " ", offset)
		seated_login.free()
	app.authenticated = false
	main.free()
	await process_frame
	ReplicatedActor3D.clear_static_caches()
	print("SEATED_OVERHEAD_CAMERA checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

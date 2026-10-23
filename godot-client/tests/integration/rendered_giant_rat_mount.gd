extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1500, 1000)
	var view: Variant = (load("res://src/dev/giant_rat_mount_showcase.tscn") as PackedScene).instantiate()
	root.add_child(view)
	view.manual = true
	var audit := "--audit" in OS.get_cmdline_user_args()
	if audit:
		var cameras := [Vector3(0,2.1,-6),Vector3(6,2.1,0),Vector3(0,2.1,6),
			Vector3(0,6,.501),Vector3(6,2.1,0),Vector3(6,2.1,0)]
		var labels := ["SOURCE / FRONT","SOURCE / SIDE","SOURCE / REAR","SOURCE / TOP","SOURCE / WALK","SOURCE / RUN"]
		for index: int in view.actors.size():
			var actor: ReplicatedActor3D = view.actors[index]
			actor.get_node("NativeModel").hide()
			actor._mount_visual.tack.hide()
			actor._mount_visual.reins.hide()
			var stage := actor.get_parent()
			var camera := stage.find_children("*","Camera3D",false,false)[0] as Camera3D
			camera.position = cameras[index]
			camera.size = 4.2 if index == 3 else 3.4
			camera.look_at(Vector3(0,1.15,.5 if index == 3 else 0.0))
			(stage.get_parent().get_parent().get_parent().get_child(0) as Label).text = labels[index]
	for actor: ReplicatedActor3D in view.actors:
		actor._mount_visual.set_process(false)
	for frame: int in 4:
		await process_frame
	var travel := "--travel" in OS.get_cmdline_user_args()
	var artifacts := ProjectSettings.globalize_path("res://test-artifacts/giant-rat-mount" + ("-source" if audit else ("-travel" if travel else "")))
	if not OS.get_environment("ELORIA_ARTIFACT_DIR").is_empty(): artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(artifacts.path_join("frames"))
	var video := "--video" in OS.get_cmdline_user_args()
	var frames := 135 if video else 45
	var max_contact := 0.0
	var max_cloth_link := 0.0
	var cloth_peak := {}
	for frame: int in frames:
		view.advance_sequence(1.0 / 30.0)
		for actor: ReplicatedActor3D in view.actors:
			if not audit:
				actor._mount_visual._process(1.0 / 30.0)
				for error: float in actor._mount_visual.pose.last_errors.values():
					max_contact = maxf(max_contact,error)
				if actor._cape_cloth != null and actor._cape_cloth_worn:
					for chain: int in 3:
						var points: PackedVector3Array = actor._cape_cloth.get("_points")[chain]
						var lengths: PackedFloat32Array = actor._cape_cloth.get("_lengths")[chain]
						for link: int in range(1,points.size()):
							var error := absf(points[link].distance_to(points[link-1])-lengths[link-1])
							if error > max_cloth_link:
								max_cloth_link = error
								cloth_peak = {"frame":frame,"actor":actor.actor_id,"action":actor._mount_visual.action,"chain":chain,"link":link}
		if audit:
			for index: int in view.actors.size():
				var pony: ReplicatedActor3D = view.actors[index]._mount_visual.pony
				var clip := "Walk" if index == 4 else ("Jog" if index == 5 else "Idle_A")
				pony.animation_player.play(clip)
				pony.animation_player.seek(fposmod(frame / 30.0,pony.animation_player.get_animation(clip).length),true)
				pony.animation_player.pause()
		await process_frame
		await RenderingServer.frame_post_draw
		if video:
			root.get_texture().get_image().save_png(artifacts.path_join("frames/%04d.png" % frame))
	root.get_texture().get_image().save_png(artifacts.path_join("giant-rat-mount.png"))
	print("GIANT_RAT_MOUNT_CAPTURE ", artifacts, " frames=", frames)
	var report := {"frames":frames,"fps":30,"max_contact_error_metres":max_contact,"max_cape_link_error_metres":max_cloth_link,"cape_peak":cloth_peak}
	FileAccess.open(artifacts.path_join("render-checks.json"),FileAccess.WRITE).store_string(JSON.stringify(report,"  "))
	var failed := max_contact >= .06 or max_cloth_link >= .02
	view.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failed else 0)

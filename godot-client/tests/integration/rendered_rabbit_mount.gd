extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1500, 1000)
	var view: Variant = (load("res://src/dev/rabbit_mount_showcase.tscn") as PackedScene).instantiate()
	root.add_child(view)
	view.manual = true
	var audit := "--audit" in OS.get_cmdline_user_args()
	if audit:
		var cameras := [Vector3(0,2.1,-6),Vector3(6,2.1,0),Vector3(0,2.1,6),
			Vector3(0,6,.001),Vector3(6,2.1,0),Vector3(6,2.1,0)]
		var labels := ["SOURCE / FRONT","SOURCE / SIDE","SOURCE / REAR","SOURCE / TOP","SOURCE / WALK","SOURCE / BOUNDS"]
		for index: int in view.actors.size():
			var actor: ReplicatedActor3D = view.actors[index]
			actor.get_node("NativeModel").hide()
			actor._mount_visual.tack.hide()
			actor._mount_visual.reins.hide()
			var stage := actor.get_parent()
			var camera := stage.find_children("*","Camera3D",false,false)[0] as Camera3D
			camera.position = cameras[index]
			camera.size = 3.0
			camera.look_at(Vector3(0,1.0,0))
			(stage.get_parent().get_parent().get_parent().get_child(0) as Label).text = labels[index]
	for actor: ReplicatedActor3D in view.actors:
		actor._mount_visual.set_process(false)
	for frame: int in 4:
		await process_frame
	var artifacts := ProjectSettings.globalize_path("res://test-artifacts/rabbit-mount" + ("-source" if audit else ""))
	DirAccess.make_dir_recursive_absolute(artifacts.path_join("frames"))
	var video := "--video" in OS.get_cmdline_user_args()
	var frames := 135 if video else 18
	for frame: int in frames:
		view.advance_sequence(1.0 / 30.0)
		for actor: ReplicatedActor3D in view.actors:
			if not audit:
				actor._mount_visual._process(1.0 / 30.0)
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
	root.get_texture().get_image().save_png(artifacts.path_join("rabbit-mount.png"))
	print("RABBIT_MOUNT_CAPTURE ", artifacts, " frames=", frames)
	view.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit()

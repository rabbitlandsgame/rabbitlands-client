extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1500, 1000)
	var view: Variant = (load("res://src/dev/horse_mount_showcase.tscn") as PackedScene).instantiate()
	root.add_child(view)
	view.manual = true
	for actor: ReplicatedActor3D in view.actors:
		actor._mount_visual.set_process(false)
	for frame: int in 4:
		await process_frame
	var artifacts := ProjectSettings.globalize_path("res://test-artifacts/horse-mount")
	DirAccess.make_dir_recursive_absolute(artifacts.path_join("frames"))
	var video := "--video" in OS.get_cmdline_user_args()
	var frames := 135 if video else 18
	for frame: int in frames:
		view.advance_sequence(1.0 / 30.0)
		for actor: ReplicatedActor3D in view.actors:
			actor._mount_visual._process(1.0 / 30.0)
		await process_frame
		await RenderingServer.frame_post_draw
		if video:
			root.get_texture().get_image().save_png(artifacts.path_join("frames/%04d.png" % frame))
	root.get_texture().get_image().save_png(artifacts.path_join("horse-mount.png"))
	print("HORSE_MOUNT_CAPTURE ", artifacts, " frames=", frames)
	view.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit()

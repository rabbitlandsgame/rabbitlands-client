extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1500, 1080)
	var scene := load("res://src/dev/combat_showcase.tscn") as PackedScene
	var showcase := scene.instantiate()
	root.add_child(showcase)
	showcase.set_process(false)
	await process_frame
	var actors: Array = showcase.actors
	var times := [0.8, 0.53, 0.48, 0.90, 0.59, 0.31]
	for i: int in actors.size():
		var actor := actors[i] as ReplicatedActor3D
		if i == 0:
			actor.play_action(&"cast_channel", true)
		actor.animation_player.stop()
		actor.animation_player.play(actor.resolver.clip_for_action(actor.current_action), 0.0)
		actor.animation_player.advance(0.0)
		actor._advance_facing_offset(1.0)
		if i == 5:
			for frame: int in 7:
				actor.animation_player.seek(times[i]-0.06+frame*0.01, true)
				actor.combat_presentation.update_pose()
		actor.animation_player.seek(times[i], true)
		actor.animation_player.pause()
		actor.combat_presentation.update_pose()
	for frame: int in 5:
		await process_frame
	await RenderingServer.frame_post_draw
	var path := ProjectSettings.globalize_path("res://test-artifacts/combat")
	DirAccess.make_dir_recursive_absolute(path)
	var output := path.path_join("combat-showcase.png")
	var result := root.get_texture().get_image().save_png(output)
	print("COMBAT_CAPTURE ", output, " result=", result)
	showcase.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(result)

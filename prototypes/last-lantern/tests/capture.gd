extends "res://tests/playthrough.gd"

var output := ""

func shot(name: String) -> void:
	for i in range(16):
		await process_frame
	await RenderingServer.frame_post_draw
	var result := root.get_texture().get_image().save_png(output.path_join(name+".png"))
	expect(result == OK,"capture saved: "+name)

func _run() -> void:
	output = OS.get_environment("LANTERN_ARTIFACTS")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://artifacts")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1440,900)
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	q = scene.q
	q.reset()
	scene.player.position = scene.tile_position(Vector2i(q.state.tile[0],q.state.tile[1]))
	scene._update_camera(1)
	await shot("01-arrival")
	scene.overview = true
	scene._refresh()
	scene._update_camera(1)
	await shot("02-island-overview")
	scene._open("map")
	await shot("03-route-map")
	scene.window.hide()
	play(false,"Matter",false)
	scene.overview = false
	scene._refresh()
	scene.player.position = scene.tile_position(Vector2i(95,97))
	scene._update_camera(1)
	await shot("04-beacon-restored")
	scene.overview = true
	scene._refresh()
	scene._update_camera(1)
	scene.boat.position = Vector3(110,-.5,-22)
	await shot("05-rescued-boat")
	scene._open("complete")
	await shot("06-handoff")
	print("Rendered draft captures: %d checks, %d failures." % [checks,failures])
	quit(1 if failures else 0)

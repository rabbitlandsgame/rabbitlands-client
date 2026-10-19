extends SceneTree
## Continuous production-camera traversal with ordinary background streaming.
## No OS cache claim; arrival and subsequent traversal are reported separately.
func _init() -> void: call_deferred("run")
func run() -> void:
	root.size = Vector2i(1280,720)
	var stage := Node3D.new()
	root.add_child(stage)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 50
	camera.far = 1500
	stage.add_child(camera)
	var points := PackedVector3Array([Vector3(-205,115,14),Vector3(-149,121,-17),Vector3(-115,122,6),Vector3(50.5,106.15,161.5)])
	var began := Time.get_ticks_msec()
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/landfall/client/world.json"),points[0])
	var arrival_ms := Time.get_ticks_msec()-began
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	WorldEnvironmentBinder.apply(loader.manifest,environment,sun)
	var stream := loader.world_root as ContinentChunkStream
	camera.look_at_from_position(points[0]+Vector3(22,30,35),points[0])
	var draw_began := Time.get_ticks_usec()
	for unused in range(3): await process_frame
	var first_draw_ms := float(Time.get_ticks_usec()-draw_began)/1000.0
	var frames: Array[float] = []
	var hitches: Array[Dictionary] = []
	var missing := 0
	var here := points[0]
	var leg := 1
	var previous := Time.get_ticks_usec()
	var walking_since := previous
	while leg < points.size():
		await process_frame
		var now := Time.get_ticks_usec()
		var delta := float(now-previous)/1000000.0
		previous = now
		frames.append(delta*1000)
		if delta > .05: hitches.append({"seconds":float(now-walking_since)/1000000,"ms":delta*1000,"at":[here.x,here.z]})
		here = here.move_toward(points[leg],5.0*minf(delta,.25))
		if here.distance_to(points[leg]) < .01: leg += 1
		stream.update_focus(here)
		if not stream.arrival_resident(here):
			# Overhanging prop bounds can await a neighbour even when the actual
			# navigation floor exists. Count true missing ground separately.
			var ray := PhysicsRayQueryParameters3D.create(here+Vector3.UP*200,here-Vector3.UP*200,8)
			if stage.get_world_3d().direct_space_state.intersect_ray(ray).is_empty(): missing += 1
		camera.look_at_from_position(here+Vector3(22,30,35),here)
	frames.sort()
	var result := {"arrival_ms":arrival_ms,"first_three_draws_ms":first_draw_ms,"frames":frames.size(),"max_frame_ms":frames.back(),
		"p95_frame_ms":frames[int(frames.size()*.95)],"missing_ground_frames":missing,
		"hitches_over_50ms":hitches,"camera_metres_per_second":5,"application_cache_disabled":OS.get_environment("ELORIA_NO_MAP_CACHE")=="1"}
	var path := ProjectSettings.globalize_path("res://test-artifacts/stream-walk.json")
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_string(JSON.stringify(result,"  ")+"\n")
	file.close()
	print("STREAM_WALK_COMPLETE ",JSON.stringify(result))
	await ContinentChunkStream.drain_workers(self)
	stage.queue_free()
	for unused in range(8): await process_frame
	GlbSceneCache.clear()
	for unused in range(4): await process_frame
	quit(1 if missing else 0)

extends SceneTree
## Measures Sunmane Steppe load time and frame cost in the running client at
## several camera distances and graphics settings, and writes the numbers as
## JSON beside the other test artefacts.

const PACKAGE := "res://../eloria-assets/maps/nymara-regions/sunmane_steppe/"
const FRAMES := 90
const PACKAGES := [["lod1", "world.json"], ["lod2", "world-lod2.json"]]

var _failures := 0

func _init() -> void:
	call_deferred("_run_all")

func _run_all() -> void:
	# The load column here is what building the region costs. A cache entry
	# left by an earlier run would turn it into what reading one back costs,
	# which is a different number in a column that does not say so.
	OS.set_environment(MapSceneCache.DISABLE_ENVIRONMENT, "1")
	var artifacts := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path("res://test-artifacts/sunmane-steppe")
	DirAccess.make_dir_recursive_absolute(artifacts)
	var report := {"packages": {}}
	for entry: Array in PACKAGES:
		var measured: Dictionary = await _run(PACKAGE + str(entry[1]))
		report["packages"][str(entry[0])] = measured
	var file := FileAccess.open(artifacts.path_join("performance.json"),
		FileAccess.WRITE)
	_expect(file != null, "performance.json is writable")
	if file != null:
		file.store_string(JSON.stringify(report, "  "))
		file.close()
	print("sunmane performance: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

func _run(manifest_path: String) -> Dictionary:
	root.size = Vector2i(1280, 720)

	var stage := Node3D.new()
	root.add_child(stage)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	stage.add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	var camera := Camera3D.new()
	camera.far = 900.0
	camera.current = true
	stage.add_child(camera)

	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	stage.add_child(loader)
	var started := Time.get_ticks_usec()
	loader.load_world(ProjectSettings.globalize_path(manifest_path))
	var deadline := Time.get_ticks_msec() + 120000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	var load_ms := float(Time.get_ticks_usec() - started) / 1000.0
	if not _expect(loader.world_root != null, "world loads: " + manifest_path):
		return {}
	WorldEnvironmentBinder.apply(loader.manifest, world_environment, sun)

	var population := AmbientPopulation.new()
	stage.add_child(population)
	for unused: int in range(4):
		await physics_frame
	var animals := population.populate(loader.manifest,
		stage.get_world_3d().direct_space_state)

	var mesh_instances := loader.world_root.find_children("*", "MeshInstance3D", true,
		false)
	var static_bodies := loader.world_root.find_children("*", "StaticBody3D", true, false)

	var results := {
		"manifest": manifest_path,
		"godotVersion": "%d.%d.%d" % [Engine.get_version_info()["major"],
			Engine.get_version_info()["minor"], Engine.get_version_info()["patch"]],
		"renderer": str(ProjectSettings.get_setting(
			"rendering/renderer/rendering_method")),
		"adapter": RenderingServer.get_video_adapter_name(),
		"viewport": [root.size.x, root.size.y],
		"loadMilliseconds": snappedf(load_ms, 0.1),
		"meshInstances": mesh_instances.size(),
		"collisionBodies": static_bodies.size(),
		"ambientAnimals": animals,
		"samples": [],
	}

	for sample: Array in [
			["gameplay-default", Vector3(0.0, 22.0, 26.0), Vector3(0.0, 9.0, 0.0),
			 Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_16, true, 1.0],
			["gameplay-zoomed-out", Vector3(0.0, 60.0, 78.0), Vector3(0.0, 9.0, 0.0),
			 Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_16, true, 1.0],
			["region-overview", Vector3(96.0, 140.0, 160.0), Vector3(0.0, 8.0, -4.0),
			 Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_4, true, 1.0],
			["low-settings-no-shadows", Vector3(0.0, 22.0, 26.0), Vector3(0.0, 9.0, 0.0),
			 Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_1, false, 0.75],
			["high-settings", Vector3(0.0, 18.0, 22.0), Vector3(0.0, 9.5, -2.0),
			 Viewport.SHADOW_ATLAS_QUADRANT_SUBDIV_64, true, 1.0]]:
		sun.shadow_enabled = bool(sample[4])
		root.scaling_3d_scale = float(sample[5])
		camera.look_at_from_position(sample[1] as Vector3, sample[2] as Vector3,
			Vector3.UP)
		for unused: int in range(20):
			await process_frame
		var frame_start := Time.get_ticks_usec()
		for unused: int in range(FRAMES):
			await process_frame
		var elapsed := float(Time.get_ticks_usec() - frame_start) / 1000.0
		var per_frame := elapsed / float(FRAMES)
		results["samples"].append({
			"id": str(sample[0]),
			"shadows": bool(sample[4]),
			"renderScale": float(sample[5]),
			"frameMilliseconds": snappedf(per_frame, 0.01),
			"framesPerSecond": snappedf(1000.0 / maxf(per_frame, 0.0001), 0.1),
			"drawCalls": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)),
			"primitivesInFrame": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)),
			"videoMemoryBytes": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)),
			"textureMemoryBytes": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED)),
			"bufferMemoryBytes": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_BUFFER_MEM_USED)),
		})
		print("  %s %s: %.2f ms/frame, %d draw calls, %d primitives" % [
			manifest_path.get_file(), str(sample[0]), per_frame,
			results["samples"][-1]["drawCalls"],
			results["samples"][-1]["primitivesInFrame"]])

	print("%s: load %.1f ms, %d mesh instances, %d collision bodies, %d animals" % [
		manifest_path.get_file(), results["loadMilliseconds"],
		results["meshInstances"], results["collisionBodies"],
		results["ambientAnimals"]])
	loader.unload_world()
	population.clear()
	stage.queue_free()
	await process_frame
	return results

func _expect(condition: bool, message: String) -> bool:
	if not condition:
		_failures += 1
		push_error("FAIL: " + message)
	return condition

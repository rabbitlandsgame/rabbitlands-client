extends SceneTree

var stage: Node3D
var loader: WorldLoader
var camera: Camera3D
var environment: WorldEnvironment
var sun: DirectionalLight3D
var artifacts := "res://test-artifacts/stream-world"
var failures := 0

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(artifacts))
	stage = Node3D.new()
	root.add_child(stage)
	environment = WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	camera = Camera3D.new()
	camera.cull_mask = 3
	camera.far = 1500
	camera.fov = 50
	camera.current = true
	stage.add_child(camera)
	loader = WorldLoader.new()
	stage.add_child(loader)
	var manifest := "res://../eloria-assets/maps/continent-v2/landfall/client/world.json"
	var began := Time.get_ticks_msec()
	loader.load_world(ProjectSettings.globalize_path(manifest), Vector3(-205,115,14))
	print("STREAM_WORLD_LOAD_MS ", Time.get_ticks_msec()-began)
	bind_environment()
	await capture("west-gate",Vector3(-205,115,14),Vector3(-177,145,49))
	await capture("herb-passage",Vector3(-218,121,-10),Vector3(-190,143,20))
	await capture("town-overview",Vector3(-115,122,6),Vector3(-65,185,80))
	await capture("orchard-approach",Vector3(-149,121,-17),Vector3(-125,153,17))
	loader.manifest.data.environment.fog["weather"] = 1.0
	LookSky.apply(loader.manifest,environment,900)
	loader.manifest.data.environment["presentation"] = {"mist":{"enabled":true,"density":.6}}
	var mist := PresentationEffects.new()
	stage.add_child(mist)
	mist.bind(loader.manifest)
	var mist_focus := Vector3(-149,121,-17)
	for i in range(60):
		mist.update(mist_focus,900,1.0,0,environment.environment.fog_light_color,1.0/60.0)
		await process_frame
	await capture("mist-current",mist_focus,Vector3(-125,153,17))
	environment.environment.fog_density = 1.0
	environment.environment.fog_depth_begin = 6
	environment.environment.fog_depth_end = 150
	var mist_colour: Color = mist._mist_material.albedo_color
	mist_colour.a = .1*.8*.6
	mist._mist_material.albedo_color = mist_colour
	await capture("mist-previous",mist_focus,Vector3(-125,153,17))
	mist.queue_free()
	loader.manifest.data.environment.fog["weather"] = 0.0
	LookSky.apply(loader.manifest,environment,900)
	await capture("south-gate",Vector3(-25,116,100),Vector3(3,143,135))
	await capture("south-gate-inside",Vector3(-33,121,86),Vector3(-55,148,53))
	var entry_adapter := loader.manifest.coordinate_adapter()
	var entry_catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	var entrance := MapObject3D.new()
	stage.add_child(entrance)
	entrance.configure({"object_id":59001,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"label":"Lantern Mine","x":332,"y":86},entry_adapter,entry_catalog)
	await physics_frame
	var entry_height: Variant = GroundDrape.surface_height(stage.get_world_3d().direct_space_state,50.5,161.5)
	if entry_height != null: entrance.set_surface_height(entry_height)
	await capture("lantern-mine",Vector3(50.5,106.15,161.5),Vector3(68,123,185))
	entrance.queue_free()
	await ContinentChunkStream.drain_workers(self)
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/gauntlets/harrowcrag_gauntlet/client/world.json"))
	bind_environment()
	var adapter := loader.manifest.coordinate_adapter()
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	var cache := MapObject3D.new()
	stage.add_child(cache)
	cache.configure({"object_id":798,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"label":"Cache","x":257,"y":225},adapter,catalog)
	await physics_frame
	await physics_frame
	var here := cache.global_position
	var query := PhysicsRayQueryParameters3D.create(here+Vector3.UP*500,here+Vector3.DOWN*500,WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit := stage.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		push_error("Reward cache tile has no production navigation surface")
		failures += 1
	else:
		cache.set_surface_height(hit.position.y)
		print("STREAM_CACHE_GROUNDED ",cache.global_position)
	await capture("reward-cache",cache.global_position,cache.global_position+Vector3(-10,9,8))
	var visitor := Node3D.new()
	stage.add_child(visitor)
	visitor.position = cache.position+Vector3(-.8,0,.4)
	var fade := OccluderFade.new()
	fade.configure(loader.manifest,loader.world_root)
	camera.look_at_from_position(cache.position+Vector3(-22,22,26),cache.position)
	for i in range(40):
		fade.update(1.0/60.0,camera,visitor)
		await process_frame
	await capture("reward-cache-player-view",cache.position,camera.position)
	fade.reset()
	visitor.queue_free()
	await ContinentChunkStream.drain_workers(self)
	stage.queue_free()
	for i in range(8): await process_frame
	GlbSceneCache.clear()
	for i in range(4): await process_frame
	print("STREAM_WORLD_RENDER_COMPLETE failures=",failures)
	quit(failures)

func bind_environment() -> void:
	WorldEnvironmentBinder.apply(loader.manifest,environment,sun)
	LookGround.paint_bound(loader.world_root,loader.manifest)
	LookSky.install(loader.manifest,environment)
	DayNightBinder.apply(loader.manifest,environment,sun,900)
	LookGrade.apply(loader.manifest,environment,sun)
	LookSky.apply(loader.manifest,environment,900)

func capture(label: String, focus: Vector3, eye: Vector3) -> void:
	var stream := loader.world_root as ContinentChunkStream
	if stream != null:
		var preload_began := Time.get_ticks_msec()
		var frame_began := Time.get_ticks_msec()
		var slowest_frame := 0
		stream.preload_views(PackedVector3Array([focus]),80)
		var deadline := Time.get_ticks_msec()+60000
		while not stream.views_ready() and not stream.views_failed() and Time.get_ticks_msec()<deadline:
			stream.update_focus(focus)
			await process_frame
			slowest_frame = maxi(slowest_frame,Time.get_ticks_msec()-frame_began)
			frame_began = Time.get_ticks_msec()
		if not stream.views_ready():
			push_error(label+" chunks did not become ready")
			failures += 1
		print("STREAM_PRELOAD ",label," ms=",Time.get_ticks_msec()-preload_began," slowest_frame_ms=",slowest_frame," cells=",stream.cells.size())
	camera.look_at_from_position(eye,focus)
	for i in range(8): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(ProjectSettings.globalize_path(artifacts.path_join(label+".png")))
	print("STREAM_WORLD_CAPTURE ",label)

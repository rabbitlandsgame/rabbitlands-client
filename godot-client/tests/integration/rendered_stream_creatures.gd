extends SceneTree
## Render the shipped rigs and approved strongbox through the real actor loader.
var failures := 0
var stage: Node3D
var actors: Array[ReplicatedActor3D] = []
var artifacts := "res://test-artifacts/stream-creatures"

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1280,720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(artifacts))
	stage = Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("697c8c")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_energy = .7
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45,-30,0)
	stage.add_child(light)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(30,30)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("899469")
	plane.material = material
	floor_mesh.mesh = plane
	stage.add_child(floor_mesh)
	var camera := Camera3D.new()
	camera.cull_mask = 3
	camera.fov = 42
	stage.add_child(camera)
	camera.look_at_from_position(Vector3(0,5,13),Vector3(0,1,0))
	camera.current = true
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var index := 0
	for species: String in ["zombie","skeleton","black_iron_death_knight","cerberus"]:
		var config: Dictionary = models[species]
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id":index+1,"kind":5,"name":species.capitalize(),"x":0,"y":0,"rotation":0,"health":100,"max_health":100},CoordinateAdapter.new({}),config,JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
		if not errors.is_empty():
			failures += 1
			push_error(str(errors))
		actor.position = Vector3(-4.5+index*3,0,0)
		if species == "cerberus": actor.set_server_scale(1.6)
		actor.set_physics_process(false)
		actor.set_health_visible(false)
		actors.append(actor)
		index += 1
	var chest := MapObject3D.new()
	stage.add_child(chest)
	chest.configure({"object_id":798,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"label":"Cache","x":0,"y":0},CoordinateAdapter.new({}),JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json")))
	chest.position = Vector3(0,0,3)
	for action: StringName in [&"walk",&"run",&"attack_primary",&"death"]:
		for actor: ReplicatedActor3D in actors:
			actor.set_cinematic_presentation(actor.position,PI,action,1.67 if action == &"walk" else 5.0)
			actor.set_physics_process(false)
		for i in range(30): await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(ProjectSettings.globalize_path(artifacts.path_join(str(action)+".png")))
		for actor: ReplicatedActor3D in actors:
			print("STREAM_CREATURE ",actor.name," ",action," clip=",actor.animation_player.current_animation," speed=",actor.animation_player.speed_scale)
	for actor: ReplicatedActor3D in actors:
		actor.set("_cinematic_active",false)
		actor.apply_vitals(0,100)
		actor.apply_server_state({"x":floori(actor.position.x),"y":0,"rotation":0,"health":0,"alive":false,"command":3,
			"death_presentation":{"temporary":false,"elapsed":0,"animation_seconds":3,"hold_seconds":3,"fade_seconds":4,"received_msec":Time.get_ticks_msec()}},CoordinateAdapter.new({}))
	for phase: Dictionary in [{"name":"corpse-held","advance":3.2},{"name":"corpse-fading","advance":4.8},{"name":"corpse-cleared","advance":3.0}]:
		for actor: ReplicatedActor3D in actors: actor._process(float(phase.advance))
		for i in range(3): await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(ProjectSettings.globalize_path(artifacts.path_join(str(phase.name)+".png")))
	for mesh: Node in chest.find_children("*","MeshInstance3D",true,false):
		print("STREAM_CHEST_MESH ",mesh.name," visible=",mesh.is_visible_in_tree()," box=",mesh.get_aabb()," at=",mesh.global_transform)
	stage.queue_free()
	for i in range(8): await process_frame
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	for i in range(4): await process_frame
	print("STREAM_CREATURE_RENDER_COMPLETE failures=",failures)
	quit(failures)

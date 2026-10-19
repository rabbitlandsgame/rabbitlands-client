extends SceneTree
## Compare shipped gaits with preserved originals or an explicit local candidate.
var failures := 0
const OUTPUT := "res://test-artifacts/undead-gaits"

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1280,720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("394750")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_energy = .7
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45,-30,0)
	stage.add_child(light)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(20,20)
	var material := ShaderMaterial.new()
	material.shader = Shader.new()
	material.shader.code = "shader_type spatial; render_mode cull_disabled; void fragment(){vec2 line=abs(fract(UV*40.0)-0.5);float mark=step(0.475,max(line.x,line.y));ALBEDO=mix(vec3(0.27,0.31,0.25),vec3(0.45,0.49,0.4),mark);ROUGHNESS=1.0;}"
	plane.material = material
	ground.mesh = plane
	stage.add_child(ground)
	var camera := Camera3D.new()
	camera.current = true
	camera.cull_mask = 3
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 7.5
	stage.add_child(camera)
	camera.look_at_from_position(Vector3(4,3,8),Vector3(0,1,1.5))
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var species_list := ["skeleton","zombie","cerberus","black_iron_death_knight"]
	var candidate_stage := ""
	var args := OS.get_cmdline_user_args()
	if args.size() == 4 and args[0] == "--species" and args[2] == "--stage":
		species_list = [args[1]]
		candidate_stage = args[3]
	for species: String in species_list:
		var actors: Array[ReplicatedActor3D] = []
		for candidate in [false,true]:
			var config: Dictionary = models[species].duplicate(true)
			var map: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
			var authoring := ProjectSettings.globalize_path("res://../.local/asset-authoring/working/stream-playtest-20261019")
			if candidate:
				if not candidate_stage.is_empty():
					config.scene = candidate_stage.path_join(species+".glb")
					config.animationLibrary = config.scene
					var fit: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.scene.get_basename()+".fit.json"))
					map.strideMetresPerSecond = {"walk":float(fit.clips.Walk.speedNative)*float(config.import.scale),"run":float(fit.clips.Jog.speedNative)*float(config.import.scale)}
			elif FileAccess.file_exists(authoring.path_join("baseline/"+species+".glb")):
				config.scene = authoring.path_join("baseline/"+species+".glb")
				config.animationLibrary = config.scene
				map = JSON.parse_string(FileAccess.get_file_as_string(authoring.path_join("baseline/"+species+".animation.json")))
			print("UNDEAD_RUNTIME_SOURCE ",species," candidate=",candidate," ",FileAccess.get_sha256(config.scene))
			var actor := ReplicatedActor3D.new()
			stage.add_child(actor)
			var errors := actor.configure({"actor_id":actors.size()+1,"kind":5,"name":species,"x":0,"y":0,"rotation":0,"health":100,"max_health":100},CoordinateAdapter.new({}),config,map)
			if not errors.is_empty():
				push_error(str(errors))
				failures += 1
			actor.set_physics_process(false)
			if species == "cerberus": actor.set_server_scale(1.6)
			actor.set_health_visible(false)
			actors.append(actor)
		for action: StringName in [&"walk",&"run"]:
			var folder := ProjectSettings.globalize_path(OUTPUT.path_join(species+"-"+str(action)))
			DirAccess.make_dir_recursive_absolute(folder)
			var speed := 1.666667 if action == &"walk" else 3.333333
			for index in range(48):
				var t := float(index)/24.0
				var focus := Vector3(0,1,t*speed)
				camera.look_at_from_position(focus+Vector3(4,2,6.5),focus)
				for slot in range(actors.size()):
					var actor := actors[slot]
					actor.set_cinematic_presentation(Vector3(-1.5+slot*3,0,t*speed),PI,action,speed)
					actor.set_physics_process(false)
					actor.rotation.y = PI
					# Apply the full pose without holding an interrupted crossfade
					# at zero weight when the deterministic fixture pauses playback.
					actor.animation_player.play(actor.resolver.clip_for_action(action),0.0)
					actor.animation_player.seek(t*actor.animation_player.speed_scale,true)
					actor.animation_player.advance(0)
					actor.animation_player.pause()
				await process_frame
				await RenderingServer.frame_post_draw
				if root.get_texture().get_image().save_png(folder.path_join("%04d.png"%index)) != OK:
					failures += 1
			print("UNDEAD_GAIT_SEQUENCE ",species," ",action," frames=48")
		for actor in actors: actor.queue_free()
		await process_frame
	stage.queue_free()
	for unused in range(8): await process_frame
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	for unused in range(4): await process_frame
	print("UNDEAD_GAIT_RENDER_COMPLETE failures=",failures)
	quit(failures)

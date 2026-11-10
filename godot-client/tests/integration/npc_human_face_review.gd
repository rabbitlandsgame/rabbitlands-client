extends SceneTree
## Actual production selection and actor construction, with optional PNG review.
var failures := 0
var checks := 0
var captures: Array = []
var camera: Camera3D
var stage: Node3D
var out := ""
var main: Control
const MOTION := ["Mara Vell","Hanne Ashby","Wynn Vell","Pim","Aldith","Jessamy Reel",
	"Odo Fenn","Brannic","Elen Reed","Liora Reed","Fenna Ash","Nash"]
func _init() -> void:
	_run.call_deferred()
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)
func read(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary
func _run() -> void:
	out = OS.get_environment("ELORIA_NPC_FACE_REVIEW")
	if not out.is_empty(): DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(600,720)
	var registry := read("res://data/actors/models.json")
	main = (load("res://src/app/main.gd") as Script).new() as Control
	main.models = registry.models
	main.actor_type_models = registry.actorTypes
	main.npc_looks = registry.npcLooks
	main.npc_characters = read("res://data/actors/npc_characters.json")
	main.npc_human_faces = read("res://data/actors/npc_human_faces.json")
	main.equipment_config = read("res://data/actors/equipment.json")
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color(.13,.16,.19)
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color.WHITE
	world.environment.ambient_light_energy = .65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-30,-25,0)
	light.light_energy = .8
	stage.add_child(light)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.current = true
	stage.add_child(camera)
	var inputs := read(OS.get_environment("ELORIA_NPC_FACE_INPUTS"))
	var wanted := OS.get_environment("ELORIA_NPC_FACE_NAMES").split(",",false)
	var count := 0
	for key: String in main.npc_human_faces.npcs:
		for row: Dictionary in main.npc_human_faces.npcs[key]:
			if not wanted.is_empty() and row.name not in wanted: continue
			var id := key + ":" + str(int(row.actorType))
			var raw: Dictionary = inputs.get(id, {}).duplicate(true)
			check(not raw.is_empty(),id + " native input")
			if raw.is_empty():continue
			if raw.has("opcode"):
				raw = EloriaProtocol.decode_server(int(raw.opcode),str(raw.payload).hex_decode())
				check(raw.get("type","") == "actor_spawn",id + " real spawn packet")
			var saved := raw.duplicate(true)
			var shown: Dictionary = main._presentation_dto(raw)
			var model: Dictionary = main.models[main._model_for_actor(raw)]
			var actor := ReplicatedActor3D.new()
			actor.apply_render_quality(ActorRenderQuality.Quality.HIGH,true)
			stage.add_child(actor)
			var errors := actor.configure(shown,CoordinateAdapter.new({"walkingHeight":0.0}),
				model,main._animation_for_model(model),main.equipment_config)
			check(errors.is_empty(),id + " constructs " + str(errors))
			actor.global_position = Vector3.ZERO
			actor.rotation.y = PI
			actor._advance_facing_offset(1.0)
			actor.set_nameplate_visible(false)
			actor.set_process(false)
			actor.set_physics_process(false)
			actor.hold_portrait_pose(self)
			check(actor.rl_head() != null,id + " High draws the updated head")
			if actor.rl_head() != null:
				check(actor.rl_head().appearance.preset == row.archetype,id + " exact identity")
			check(raw == saved,id + " replicated state unchanged")
			check(actor.equipment_diagnostics().get("fallback",0) == 0,id + " native outfit")
			var slug := str(row.name).to_snake_case().validate_filename()+"-"+str(int(row.actorType))
			await capture(actor,slug+"-front",0,false,"Idle_Subtle",row)
			if row.name in MOTION:
				await capture(actor,slug+"-side",PI/2,false,"Idle_Subtle",row)
				await capture(actor,slug+"-walk",PI/3,true,"Walk",row)
			# Quality switches must release the new head and retain the native
			# body, with no portrait override forcing detailed heads at distance.
			actor.release_portrait_pose(self)
			for quality: int in [ActorRenderQuality.Quality.MEDIUM,ActorRenderQuality.Quality.LOW]:
				actor.apply_render_quality(quality,true)
				check(actor.rl_head() == null,id + " native lower quality")
				check(actor.get_skeleton() != null,id + " lower quality keeps rig")
			actor.free()
			await process_frame
			count += 1
			print("NPC_FACE_REVIEW ",count," ",id," failures=",failures)
	if not out.is_empty():
		var f := FileAccess.open(out.path_join("report.json"),FileAccess.WRITE)
		f.store_string(JSON.stringify({"profiles":count,"checks":checks,"failures":failures,"captures":captures},"\t"))
		f.close()
	for property: Dictionary in main.get_property_list():
		if int(property.usage) & PROPERTY_USAGE_SCRIPT_VARIABLE:
			var value: Variant = main.get(str(property.name))
			if value is Node and is_instance_valid(value) and value != main and value.get_parent() == null:value.free()
	main.free()
	stage.free()
	print("NPC FACE REVIEW: %d profiles, %d checks, %d captures, %d failures" % [count,checks,captures.size(),failures])
	quit(1 if failures else 0)
func capture(actor: ReplicatedActor3D,slug: String,angle: float,whole: bool,clip: String,row: Dictionary) -> void:
	actor.rotation.y = PI+angle
	actor.animation_player.play(clip)
	actor.animation_player.advance(.35)
	actor.animation_player.pause()
	var scale := actor.server_scale
	var skeleton := actor.get_skeleton()
	var centre := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin)
	if whole:centre = Vector3(0,1.0*scale,0)
	else:centre += Vector3(0,.03*scale,0)
	camera.size = (2.5 if whole else .75)*scale
	camera.position = centre+Vector3(0,0,4)
	camera.look_at(centre)
	for frame in 4:await process_frame
	if not out.is_empty():
		await RenderingServer.frame_post_draw
		var path := out.path_join(slug+".png")
		check(root.get_texture().get_image().save_png(path) == OK,slug + " saved")
		captures.append({"name":row.name,"actorType":row.actorType,"archetype":row.archetype,
			"path":path,"clip":clip,"angle":angle,"wholeBody":whole})

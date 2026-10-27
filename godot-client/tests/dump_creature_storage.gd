extends SceneTree
## Actual mesh arrays and native-library states, driven by an ignored job.
const Cache := preload("res://src/actors/glb_scene_cache.gd")
const Importer := preload("res://src/actors/native_animation_importer.gd")
var job: Dictionary
var models: Array[Dictionary] = []
var descriptions := []
var samples := []
var output: String
var mode: String

func _init() -> void:
	run.call_deferred()

func matrix(value: Transform3D) -> Array:
	return [value.basis.x.x,value.basis.y.x,value.basis.z.x,value.origin.x,value.basis.x.y,value.basis.y.y,value.basis.z.y,value.origin.y,value.basis.x.z,value.basis.y.z,value.basis.z.z,value.origin.z]

func save(path: String, bytes: PackedByteArray) -> void:
	FileAccess.open(path,FileAccess.WRITE).store_buffer(bytes)

func vector(value: Vector3) -> Array:
	return [value.x,value.y,value.z]

func describe(fixture: Dictionary) -> void:
	var model: Node3D
	var holder: Node3D
	var player: AnimationPlayer
	if mode == "fit":
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = job.config.duplicate(true)
		config.scene = fixture.path; config.animationLibrary = fixture.path
		var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
		assert(actor.configure({"actor_id":5,"x":0,"y":0,"rotation":0,"kind":5,"name":job.actor},CoordinateAdapter.new(),config,mapping).is_empty())
		actor.set_process(false); actor.set_physics_process(false)
		model = actor.get_node("NativeModel") as Node3D
		holder = actor
		player = actor.animation_player
	else:
		model = Cache.instantiate(fixture.path)
		assert(model != null)
		root.add_child(model)
		holder = model
		for old: AnimationPlayer in model.find_children("*","AnimationPlayer",true,false): old.active = false
	var skeleton := model.find_children("*","Skeleton3D",true,false)[0] as Skeleton3D
	if mode != "fit":
		var imported := Importer.import_library(model,fixture.path,skeleton)
		assert(imported.errors.is_empty(),str(imported.errors))
		player = imported.player as AnimationPlayer
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var groups: Array[Dictionary] = []
	var serial := []
	for mesh: MeshInstance3D in model.find_children("*","MeshInstance3D",true,false):
		for surface in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES] != null else PackedInt32Array()
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS] != null else PackedFloat32Array()
			var prefix := output.path_join(str(fixture.name)+"-"+str(mesh.name)+"-surface"+str(surface))
			save(prefix+"-positions.f32",vertices.to_byte_array())
			save(prefix+"-normals.f32",normals.to_byte_array())
			save(prefix+"-joints.i32",joints.to_byte_array())
			save(prefix+"-weights.f32",weights.to_byte_array())
			var raw := RenderingServer.mesh_get_surface(mesh.mesh.get_rid(),surface)
			save(prefix+"-skin.bin",raw.get("skin_data",PackedByteArray()))
			var positions := FileAccess.open(prefix+"-shape-positions.f32",FileAccess.WRITE)
			var shape_normals := FileAccess.open(prefix+"-shape-normals.f32",FileAccess.WRITE)
			for shape: Array in mesh.mesh.surface_get_blend_shape_arrays(surface):
				positions.store_buffer((shape[Mesh.ARRAY_VERTEX] as PackedVector3Array).to_byte_array())
				shape_normals.store_buffer((shape[Mesh.ARRAY_NORMAL] as PackedVector3Array).to_byte_array())
			positions.close(); shape_normals.close()
			var bones := []
			var binds := []
			if mesh.skin != null:
				for bind in mesh.skin.get_bind_count():
					var bone := skeleton.find_bone(mesh.skin.get_bind_name(bind))
					bones.append(bone if bone >= 0 else mesh.skin.get_bind_bone(bind))
					binds.append(matrix(mesh.skin.get_bind_pose(bind)))
			groups.append({"mesh":mesh})
			serial.append({"name":str(mesh.name),"surface":surface,"prefix":prefix,"vertices":vertices.size(),"targets":mesh.mesh.get_blend_shape_count(),"mode":mesh.mesh.blend_shape_mode,"bones":bones,"binds":binds,"aabb_position":vector(mesh.mesh.get_aabb().position),"aabb_size":vector(mesh.mesh.get_aabb().size),"blend_buffer_bytes":raw.get("blend_shape_data",PackedByteArray()).size(),"mesh_surfaces":mesh.mesh.get_surface_count()})
	models.append({"model":holder,"skeleton":skeleton,"player":player,"groups":groups})
	descriptions.append({"name":fixture.name,"sha256":FileAccess.get_sha256(fixture.path),"meshes":serial,"model_global":[vector(model.global_transform.origin),vector(model.global_transform.basis.x),vector(model.global_transform.basis.y),vector(model.global_transform.basis.z)]})

func snapshot(label: String) -> void:
	var state := {"label":label,"models":[]}
	for model: Dictionary in models:
		model.skeleton.force_update_all_bone_transforms()
		var poses := []
		for bone in model.skeleton.get_bone_count(): poses.append(matrix(model.skeleton.global_transform*model.skeleton.get_bone_global_pose(bone)))
		var weights := []
		var transforms := []
		for group: Dictionary in model.groups:
			var values := []
			for shape in group.mesh.mesh.get_blend_shape_count(): values.append(group.mesh.get_blend_shape_value(shape))
			weights.append(values)
			transforms.append(matrix(group.mesh.global_transform))
		state.models.append({"poses":poses,"weights":weights,"mesh_transforms":transforms})
	samples.append(state)

func run() -> void:
	var arguments := OS.get_cmdline_user_args()
	job = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
	mode = str(arguments[1]) if arguments.size() > 1 else "native"
	assert(mode in ["native","imported","fit"])
	output = str(job.output).path_join(mode)
	DirAccess.make_dir_recursive_absolute(output)
	var fixtures: Array = job.get("native_fixtures",[]) if mode == "native" else job.get("imported_fixtures",[])
	if mode == "fit": fixtures = [job.actor_fixtures[0]]
	assert(fixtures.size() == (1 if mode == "fit" else 2))
	for fixture: Dictionary in fixtures: describe(fixture)
	if mode == "fit":
		for clip: StringName in models[0].player.get_animation_list():
			if clip == &"RESET": continue
			var duration: float = models[0].player.get_animation(clip).length
			var fractions := [.0,.37,.79,1.]
			for frame in range(ceili(duration*24.0)+1): fractions.append(minf(frame/24.0/duration,1.0))
			var seen := {}
			for fraction: float in fractions:
				if seen.has(fraction): continue
				seen[fraction] = true
				models[0].player.play("RESET",0.0); models[0].player.seek(0.0,true)
				models[0].player.play(clip,0.0); models[0].player.seek(duration*fraction,true)
				snapshot(str(clip)+"@"+str(fraction))
		write_report()
		return
	for clip: StringName in models[0].player.get_animation_list():
		for fraction in [0.0,.037,.139,.25,.499,.731,.933,1.0]:
			for model: Dictionary in models:
				model.player.play("RESET",0.0); model.player.seek(0.0,true)
				model.player.play(clip,0.0); model.player.seek(model.player.get_animation(clip).length*fraction,true)
			snapshot(str(clip)+"@"+str(fraction))
	for from: StringName in models[0].player.get_animation_list():
		if from == &"RESET": continue
		for to: StringName in models[0].player.get_animation_list():
			if to == &"RESET" or to == from: continue
			for step in [.03,.09,.15,.21]:
				for model: Dictionary in models:
					model.player.play("RESET",0.0); model.player.seek(0.0,true)
					model.player.play(from,0.0); model.player.seek(model.player.get_animation(from).length*.613,true)
					model.player.play(to,.25); model.player.advance(step)
				snapshot(str(from)+"->"+str(to)+"@"+str(step))
	write_report()

func write_report() -> void:
	FileAccess.open(output.path_join("runtime.json"),FileAccess.WRITE).store_string(JSON.stringify({"descriptions":descriptions,"samples":samples,"mode":mode,"engine":Engine.get_version_info()}))
	for model: Dictionary in models: model.model.free()
	Importer.clear(); Cache.clear()
	print("CREATURE_STORAGE_DUMP_PASS ",job.actor," ",mode," ",samples.size())
	quit()

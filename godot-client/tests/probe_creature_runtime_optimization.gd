extends SceneTree
## Headless actual-client measurement, not an artistic acceptance gate.
## Usage: --headless --path ISOLATED_PROJECT --script res://tests/probe_creature_runtime_optimization.gd -- JOB.json
const Cache := preload("res://src/actors/glb_scene_cache.gd")
const Importer := preload("res://src/actors/native_animation_importer.gd")
var job: Dictionary
var models: Array[Dictionary] = []
var descriptions: Array = []
var records: Array = []
var stream: FileAccess
var output: String

func _init() -> void:
	run.call_deferred()

func matrix(t: Transform3D) -> Array:
	return [t.basis.x.x,t.basis.y.x,t.basis.z.x,t.origin.x,t.basis.x.y,t.basis.y.y,t.basis.z.y,t.origin.y,t.basis.x.z,t.basis.y.z,t.basis.z.z,t.origin.z]

func save(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path,FileAccess.WRITE)
	assert(file != null,"Cannot write "+path)
	file.store_buffer(bytes)

func describe(fixture: Dictionary) -> void:
	assert(FileAccess.get_sha256(fixture.path)==str(fixture.sha256),"Fixture hash changed")
	# Force the production raw builder for both sides, even for res:// aliases.
	# ResourceLoader/editor PackedScenes are deliberately outside this probe's scope.
	Cache.install_prepared({str(fixture.path):Cache._build_raw(str(fixture.path))})
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var config: Dictionary = job.config.duplicate(true)
	config.scene=fixture.path
	config.animationLibrary=fixture.path
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(job.qa_animation_map_path))
	var dto: Dictionary = job.get("dto",{"actor_id":5,"x":0,"y":0,"rotation":0,"kind":5,"name":job.actor}).duplicate(true)
	if dto.get("footprint") is Array:
		dto.footprint=Vector2i(int(dto.footprint[0]),int(dto.footprint[1]))
	assert(int(dto.get("kind",0))==5,"Creature DTO required")
	var errors := actor.configure(dto,CoordinateAdapter.new(),config,mapping)
	assert(errors.is_empty(),str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	var player := actor.animation_player
	assert(player != null)
	if player.animation_finished.is_connected(actor._on_animation_finished):
		player.animation_finished.disconnect(actor._on_animation_finished)
	player.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	assert(player.has_animation("RESET"),"Missing native RESET")
	var clips := {}
	for clip: String in job.all_native_clips:
		assert(player.has_animation(clip),"Actual Actor omitted native clip: "+clip)
		clips[clip]={"length":player.get_animation(clip).length,"loop_mode":player.get_animation(clip).loop_mode}
	var native := actor.get_node("NativeModel") as Node3D
	var skeletons: Array = native.find_children("*","Skeleton3D",true,false)
	var skeleton_rows := []
	var offsets := {}
	var bone_count := 0
	for skeleton: Skeleton3D in skeletons:
		offsets[skeleton.get_instance_id()]=bone_count
		var names := []
		var rests := []
		var parents := []
		for bone in skeleton.get_bone_count():
			names.append(str(skeleton.get_bone_name(bone)))
			rests.append(matrix(skeleton.get_bone_rest(bone)))
			parents.append(skeleton.get_bone_parent(bone))
		skeleton_rows.append({"path":str(native.get_path_to(skeleton)),"offset":bone_count,"names":names,"rests":rests,"parents":parents,"global":matrix(skeleton.global_transform)})
		bone_count+=skeleton.get_bone_count()
	var groups: Array = []
	var meshes := []
	for mesh: MeshInstance3D in native.find_children("*","MeshInstance3D",true,false):
		if mesh.mesh == null: continue
		var skeleton := mesh.get_node_or_null(mesh.skeleton) as Skeleton3D
		for surface in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			assert(normals.size()==vertices.size(),"Missing native normals")
			var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES]!=null else PackedInt32Array()
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS]!=null else PackedFloat32Array()
			var prefix := output.path_join(str(fixture.name)+"-surface"+str(meshes.size()))
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
			positions.close()
			shape_normals.close()
			var bones := []
			var binds := []
			if not joints.is_empty():
				assert(mesh.skin!=null and skeleton!=null,"Missing skin/skeleton")
				assert(offsets.has(skeleton.get_instance_id()),"Skeleton outside model")
				for bind in mesh.skin.get_bind_count():
					var bone := skeleton.find_bone(mesh.skin.get_bind_name(bind))
					if bone<0: bone=mesh.skin.get_bind_bone(bind)
					assert(bone>=0 and bone<skeleton.get_bone_count())
					bones.append(int(offsets[skeleton.get_instance_id()])+bone)
					binds.append(matrix(mesh.skin.get_bind_pose(bind)))
			groups.append(mesh)
			meshes.append({"path":str(native.get_path_to(mesh)),"surface":surface,"prefix":prefix,"vertices":vertices.size(),"targets":mesh.mesh.get_blend_shape_count(),"mode":mesh.mesh.blend_shape_mode,"bones":bones,"binds":binds,"skeleton_index":skeletons.find(skeleton),"blend_buffer_bytes":raw.get("blend_shape_data",PackedByteArray()).size()})
	assert(not meshes.is_empty())
	var collision := actor.get_node("SelectionCollision") as CollisionShape3D
	var capsule := collision.shape as CapsuleShape3D
	models.append({"actor":actor,"skeletons":skeletons,"player":player,"groups":groups})
	descriptions.append({"name":fixture.name,"sha256":FileAccess.get_sha256(fixture.path),"load_proof":{"actual_loader":"ReplicatedActor3D.configure + GlbSceneCache._build_raw","source_path":fixture.path},"bone_count":bone_count,"skeletons":skeleton_rows,"meshes":meshes,"clips":clips,"model_global":matrix(native.global_transform),"actor_global":matrix(actor.global_transform),"selection":{"transform":matrix(collision.global_transform),"radius":capsule.radius,"height":capsule.height}})

func snapshot(label: String, category: String) -> void:
	for model: Dictionary in models:
		var flat := PackedFloat32Array()
		for skeleton: Skeleton3D in model.skeletons:
			skeleton.force_update_all_bone_transforms()
			for bone in skeleton.get_bone_count():
				flat.append_array(PackedFloat32Array(matrix(skeleton.global_transform*skeleton.get_bone_global_pose(bone))))
		for skeleton: Skeleton3D in model.skeletons:
			flat.append_array(PackedFloat32Array(matrix(skeleton.global_transform)))
		for mesh: MeshInstance3D in model.groups:
			for shape in mesh.mesh.get_blend_shape_count(): flat.append(mesh.get_blend_shape_value(shape))
			flat.append_array(PackedFloat32Array(matrix(mesh.global_transform)))
		stream.store_buffer(flat.to_byte_array())
	records.append({"label":label,"category":category})

func reset(model: Dictionary) -> void:
	model.player.stop()
	model.player.play("RESET",0.0)
	model.player.seek(0.0,true)

func run() -> void:
	job=JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var probe_sha256 := FileAccess.get_sha256(get_script().resource_path)
	assert(probe_sha256==str(job.probe_sha256),"Prepared probe differs from job SHA256")
	output=str(job.output).path_join("client")
	DirAccess.make_dir_recursive_absolute(output)
	stream=FileAccess.open(output.path_join("states.f32"),FileAccess.WRITE)
	for fixture: Dictionary in job.actor_fixtures: describe(fixture)
	assert(models.size()==2)
	snapshot("configured-default","default")
	for clip: String in job.all_native_clips:
		var length: float = models[0].player.get_animation(clip).length
		assert(length==models[1].player.get_animation(clip).length,"Clip duration changed: "+clip)
		# Independent shifted grid, with exact endpoints, not the fitting samples.
		for fraction: float in job.sample_fractions:
			for model: Dictionary in models:
				reset(model)
				model.player.play(clip,0.0)
				model.player.seek(length*fraction,true)
			snapshot(clip+"@"+str(fraction),"clip")
		for model: Dictionary in models:
			reset(model)
			var animation: Animation = model.player.get_animation(clip)
			var old_loop := animation.loop_mode
			animation.loop_mode=Animation.LOOP_NONE
			model.player.play(clip,0.0)
			model.player.seek(length,true)
			model.player.advance(0.417)
			animation.loop_mode=old_loop
		snapshot(clip+"@held-end+0.417","held_end")
	for previous: String in job.all_native_clips:
		for following: String in job.all_native_clips:
			if previous==following: continue
			for time: float in job.switch_times:
				for model: Dictionary in models:
					reset(model)
					model.player.play(previous,0.0)
					model.player.seek(model.player.get_animation(previous).length*.61731,true)
					model.player.play(following,.25)
					model.player.advance(time)
				snapshot(previous+"->"+following+"@"+str(time),"switch")
	for model: Dictionary in models: reset(model)
	snapshot("RESET-after-switches","RESET")
	stream.close()
	var report := {"descriptions":descriptions,"records":records,"engine":Engine.get_version_info(),"probe_sha256":probe_sha256,"state_format":"float32 little-endian; per model: all bone world matrices(3x4), skeleton global matrices(3x4), then per surface: morph values, mesh world matrix(3x4)","job":job}
	FileAccess.open(output.path_join("metadata.json"),FileAccess.WRITE).store_string(JSON.stringify(report))
	for model: Dictionary in models: model.actor.free()
	Importer.clear()
	Cache.clear()
	print("CREATURE_RUNTIME_CLIENT_PASS ",job.actor," ",records.size())
	quit()

extends SceneTree
const Preparation := preload("res://src/world/map_material_preparation.gd")
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")

func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func stored(material: Material) -> Dictionary:
	var result := {}
	for property: Dictionary in material.get_property_list():
		if (int(property.usage)&PROPERTY_USAGE_STORAGE)==0 or property.name in ["resource_path","resource_scene_unique_id"]: continue
		result[property.name] = material.get(property.name)
	return result

func importer(material: Material) -> ImporterMesh:
	var source := ImporterMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.BACK])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.DOWN])
	source.add_surface(Mesh.PRIMITIVE_TRIANGLES,arrays,[],{},material,"Fixture")
	return source

func run() -> void:
	var old := OS.get_environment(Preparation.ENVIRONMENT)
	OS.set_environment(Preparation.ENVIRONMENT,"1")
	var image := Image.create(2,2,false,Image.FORMAT_RGB8)
	image.fill(Color(0.2,0.4,0.6))
	var texture := ImageTexture.create_from_image(image)
	var original := StandardMaterial3D.new()
	original.resource_name = "SourceIdentity"
	original.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	original.albedo_texture = texture
	original.albedo_color = Color(0.3,0.4,0.5,1)
	original.normal_enabled = true
	original.roughness = 0.62
	var legacy := original.duplicate(false) as StandardMaterial3D
	var state := GLTFState.new()
	var orm := ORMMaterial3D.new()
	var shader := ShaderMaterial.new()
	var materials: Array[Material] = [original,orm,shader]
	state.set_materials(materials)
	var source := importer(original)
	var old_source := importer(legacy)
	var old_mesh := old_source.get_mesh()
	legacy.texture_filter = Preparation.FILTER
	expect(Preparation.prepare(state)==2,"all BaseMaterial3D subclasses receive the final map filter")
	expect(state.get_materials()[0]==original and state.get_materials()[1]==orm and state.get_materials()[2]==shader,"preparation preserves exact material identities")
	expect(original.texture_filter==Preparation.FILTER and orm.texture_filter==Preparation.FILTER,"final filter is exact anisotropic sampler")
	expect(shader.shader==null,"custom shader materials remain unchanged")
	var mesh := source.get_mesh()
	expect(mesh.surface_get_material(0)==original,"first ImporterMesh materialization binds the original final material")
	expect(stored(original)==stored(legacy),"every authored stored material property matches legacy late preparation")
	expect(var_to_bytes(mesh.surface_get_arrays(0))==var_to_bytes(old_mesh.surface_get_arrays(0)),"geometry/normal/UV bytes are unchanged")
	expect(original.albedo_texture==texture and texture.get_image().get_data()==image.get_data(),"texture identity and pixel bytes are unchanged")
	expect(Preparation.prepare(state)==0,"already-final materials need no repeated mutation")
	expect(Preparation.prepare(null)==0,"absent state is harmless")
	var disabled := StandardMaterial3D.new()
	disabled.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	state.set_materials([disabled])
	var before := stored(disabled)
	OS.set_environment(Preparation.ENVIRONMENT,"0")
	expect(not Preparation.enabled() and Preparation.prepare(state)==0 and stored(disabled)==before,"zero preserves legacy pre-materialization state for controls")
	OS.set_environment(Preparation.ENVIRONMENT,"")
	expect(Preparation.enabled(),"default enables early final preparation")
	var worker := Thread.new()
	worker.start(func() -> int: return Preparation.prepare(state))
	while worker.is_alive(): await process_frame
	expect(int(worker.wait_to_finish())==1 and disabled.texture_filter==Preparation.FILTER,"owning worker can prepare Resources without Nodes or replacement")
	OS.set_environment(Preparation.ENVIRONMENT,old)
	for frame: int in 60: await process_frame
	print("map material preparation: ","PASS" if failures==0 else "FAIL"," (",checks," checks, ",failures," failures)")
	quit(0 if failures==0 else 1)

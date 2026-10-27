extends SceneTree
const Preparation := preload("res://src/world/map_material_preparation.gd")
const Scenes := preload("res://src/actors/glb_scene_cache.gd")

## Called inside generate_scene, before _build_raw's late material pass. This
## observes the real loader boundary rather than testing a feature flag alone.
class GenerationWitness extends GLTFDocumentExtension:
	# Godot duplicates registered extensions for each import. Test-only shared
	# scalar results observe those clones without retaining state or Resources.
	static var filters: Array[int] = []
	static var parsed_ids: Array[int] = []
	static var generated_ids: Array[int] = []
	func _import_preflight(_state: GLTFState,_extensions: PackedStringArray) -> Error:
		return OK
	func _import_post_parse(state: GLTFState) -> Error:
		for material: Material in state.get_materials():
			if material is BaseMaterial3D: parsed_ids.append(material.get_instance_id())
		return OK
	func _import_pre_generate(state: GLTFState) -> Error:
		for material: Material in state.get_materials():
			if material is BaseMaterial3D:
				generated_ids.append(material.get_instance_id())
				filters.append((material as BaseMaterial3D).texture_filter)
		return OK
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

func loaded_properties(material: Material) -> Dictionary:
	var result := stored(material)
	for key: Variant in result:
		if result[key] is Texture2D:
			var texture := result[key] as Texture2D
			result[key] = [texture.get_class(),texture.get_width(),texture.get_height(),
				(texture as ImageTexture).get_format() if texture is ImageTexture else -1]
	return result

func capture_build(path: String) -> Dictionary:
	GenerationWitness.filters.clear()
	GenerationWitness.parsed_ids.clear()
	GenerationWitness.generated_ids.clear()
	var packed := Scenes._build_raw(path)
	var before: Array[int] = GenerationWitness.filters.duplicate()
	var properties: Array = []
	var identities := GenerationWitness.parsed_ids == GenerationWitness.generated_ids
	if packed != null:
		var state := packed.get_state()
		var seen := {}
		for node: int in state.get_node_count():
			for property: int in state.get_node_property_count(node):
				if state.get_node_property_name(node,property) != &"mesh": continue
				var mesh := state.get_node_property_value(node,property) as Mesh
				if mesh == null: continue
				for surface: int in mesh.get_surface_count():
					var material := mesh.surface_get_material(surface) as BaseMaterial3D
					if material == null or seen.has(material.get_instance_id()): continue
					var id := material.get_instance_id()
					seen[id] = true
					properties.append(loaded_properties(material))
	return {"ok":packed != null and not before.is_empty(),"before":before,"properties":properties,"identities":identities}

func actual_world_object_boundary() -> void:
	var old_world := OS.get_environment(Scenes.EARLY_WORLD_FILTER_ENVIRONMENT)
	var old_map := OS.get_environment(Preparation.ENVIRONMENT)
	var witness := GenerationWitness.new()
	GLTFDocument.register_gltf_document_extension(witness,true)
	OS.set_environment(Preparation.ENVIRONMENT,"1")
	OS.set_environment(Scenes.EARLY_WORLD_FILTER_ENVIRONMENT,"0")
	var old_world_build := capture_build("res://assets/world/underground/wooden_pail.glb")
	var old_actor_build := capture_build("res://assets/actors/native/races/votary_male.glb")
	OS.set_environment(Scenes.EARLY_WORLD_FILTER_ENVIRONMENT,"1")
	var new_world_build := capture_build("res://assets/world/underground/wooden_pail.glb")
	var new_actor_build := capture_build("res://assets/actors/native/races/votary_male.glb")
	expect(bool(old_world_build.ok) and bool(new_world_build.ok) and bool(old_actor_build.ok) and bool(new_actor_build.ok),"actual world object and actor raw builds succeed")
	expect(bool(new_world_build.identities) and bool(new_actor_build.identities),"raw preparation preserves material identities from completed parse to first generation")
	expect((new_world_build.before as Array).all(func(value: int) -> bool: return value == Preparation.FILTER) \
		and (old_world_build.before as Array).any(func(value: int) -> bool: return value != Preparation.FILTER),"world-object sampler is final inside generate_scene while the opt-out retains late ordering")
	expect(new_world_build.properties == old_world_build.properties,"actual world-object final stored properties match legacy ordering")
	expect(new_actor_build.before == old_actor_build.before and new_actor_build.properties == old_actor_build.properties,"actual actor material preparation is unchanged across the world-object switch")
	OS.set_environment(Preparation.ENVIRONMENT,"0")
	var global_disabled := capture_build("res://assets/world/underground/wooden_pail.glb")
	expect(global_disabled.before == old_world_build.before and global_disabled.properties == old_world_build.properties,"global map-filter opt-out also restores old world-object ordering and final properties")
	GLTFDocument.unregister_gltf_document_extension(witness)
	OS.set_environment(Scenes.EARLY_WORLD_FILTER_ENVIRONMENT,old_world)
	OS.set_environment(Preparation.ENVIRONMENT,old_map)

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
	actual_world_object_boundary()
	OS.set_environment(Preparation.ENVIRONMENT,old)
	for frame: int in 60: await process_frame
	print("map material preparation: ","PASS" if failures==0 else "FAIL"," (",checks," checks, ",failures," failures)")
	quit(0 if failures==0 else 1)

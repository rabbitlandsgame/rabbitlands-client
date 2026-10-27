extends SceneTree
const Writer := preload("res://src/world/map_geometry_writer.gd")
const CACHE_ROOT := "user://map-geometry-writer-tests/blobs"
var _failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if value: print("ok ", message)
	else:
		_failures += 1
		push_error("FAIL " + message)

func _triangle(material: Material) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.FORWARD,Vector3.FORWARD,Vector3.FORWARD])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.DOWN])
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	mesh.surface_set_material(0,material)
	return mesh

func _scene(mesh: Mesh) -> PackedScene:
	var origin := Node3D.new()
	origin.name = "Fixture"
	for label: String in ["A","B"]:
		var node := MeshInstance3D.new()
		node.name = label
		node.mesh = mesh
		origin.add_child(node)
		node.owner = origin
	var packed := PackedScene.new()
	_expect(packed.pack(origin) == OK,"synthetic scene packs")
	origin.free()
	return packed

func _texture() -> ImageTexture:
	return ImageTexture.create_from_image(Image.create_from_data(1,1,false,Image.FORMAT_RGBA8,
		PackedByteArray([12,34,56,255])))

func _run() -> void:
	var writer := Writer.new()
	_expect(not writer.configure("user://map-geometry-writer-tests/../other"),"noncanonical writer root is rejected")
	_expect(writer.configure(CACHE_ROOT),"owned native directory is writable")
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(.25,.5,.75,1)
	material.roughness = .6
	var mesh := _triangle(material)
	var packed := _scene(mesh)
	var original_editor_ids: Variant = (packed.get("_bundled") as Dictionary).get("node_ids")
	var result: Dictionary = writer.write(packed)
	_expect(bool(result.ok),"native geometry writes: "+str(result.get("error","")))
	if bool(result.ok):
		_expect(result.payloads.size() == 1,"local geometry, shapes and materials stay in one primary file")
		_expect(result.bindings.is_empty(),"texture-free scene needs no bindings")
		_expect(mesh.resource_path.is_empty() and material.resource_path.is_empty(),"source resource paths stay unchanged")
		_expect((packed.get("_bundled") as Dictionary).get("node_ids") == original_editor_ids,"generated editor-ID normalization does not mutate source scene")
		_expect(mesh.surface_get_material(0) == material,"source material sharing stays unchanged")
		_expect(writer.saved_resources.get(mesh.get_instance_id()) != mesh,"native mesh is a private duplicate")
		var native := ResourceLoader.load(str(result.path),"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
		_expect(native != null,"native file and dependency closure reload")
		if native != null:
			var state := native.get_state()
			var source_state := packed.get_state()
			var hierarchy_same := state.get_node_count() == source_state.get_node_count()
			for index: int in mini(state.get_node_count(),source_state.get_node_count()):
				hierarchy_same = hierarchy_same and state.get_node_path(index) == source_state.get_node_path(index) \
					and state.get_node_type(index) == source_state.get_node_type(index)
			_expect(hierarchy_same,"normalized native scene preserves effective hierarchy and node types")
			var root := native.instantiate() as Node3D
			var a := root.get_node("A") as MeshInstance3D
			var b := root.get_node("B") as MeshInstance3D
			_expect(a.mesh == b.mesh,"round-trip retains within-scene mesh sharing")
			_expect(a.mesh.surface_get_material(0) == b.mesh.surface_get_material(0),"round-trip retains material sharing")
			_expect(a.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX],"vertex arrays are lossless")
			root.free()
		var repeated: Dictionary = writer.write(packed)
		_expect(bool(repeated.ok) and repeated.path == result.path,"identical content reuses the same native blobs")
		var other_material := StandardMaterial3D.new()
		other_material.albedo_color = material.albedo_color
		other_material.roughness = material.roughness
		var independently_created: Dictionary = writer.write(_scene(_triangle(other_material)))
		_expect(bool(independently_created.ok) and independently_created.path == result.path,"equivalent independent graphs deduplicate deterministically: "+str(result.path)+" / "+str(independently_created.get("path","")))
		writer.external_mesh_ids = {mesh.get_instance_id(): "fixture-prototype"}
		var external: Dictionary = writer.write(packed)
		_expect(bool(external.ok) and external.payloads.size() == 2,"a declared prototype is the only external resource blob")
		var prototype_path := str(writer.saved_paths.get(mesh.get_instance_id(),""))
		_expect(not prototype_path.is_empty() and not writer.saved_paths.has(material.get_instance_id()),"prototype path is exposed while its material stays inline")
		var other_root := Node3D.new()
		other_root.name = "AnotherChunk"
		var local_mesh := _triangle(material)
		for item: Array in [["Before",local_mesh],["Prototype",mesh]]:
			var instance := MeshInstance3D.new()
			instance.name = str(item[0])
			instance.mesh = item[1]
			other_root.add_child(instance)
			instance.owner = other_root
		var other_scene := PackedScene.new()
		_expect(other_scene.pack(other_root) == OK,"second chunk fixture packs")
		other_root.free()
		var reordered: Dictionary = writer.write(other_scene)
		_expect(bool(reordered.ok) and writer.saved_paths.get(mesh.get_instance_id(),"") == prototype_path,"prototype bytes ignore local resource visitation order")
	var texture := _texture()
	var textured := StandardMaterial3D.new()
	textured.albedo_texture = texture
	var textured_mesh := _triangle(textured)
	var textured_result: Dictionary = writer.write(_scene(textured_mesh))
	_expect(bool(textured_result.ok),"material texture becomes an explicit binding: "+str(textured_result.get("error","")))
	if bool(textured_result.ok):
		_expect(textured_result.bindings.size() == 1,"one stable texture binding is recorded")
		_expect(textured.albedo_texture == texture and texture.resource_path.is_empty(),"original pixels and material are not mutated")
		var saved := writer.saved_resources.get(textured.get_instance_id()) as Material
		_expect(saved != null and saved.get("albedo_texture") == null,"native material contains no texture payload")
		_expect(saved != null and saved.get_meta(Writer.SLOT_META,{}).has("albedo_texture"),"native material records the texture slot")
		_expect(not writer.saved_resources.has(mesh.get_instance_id()),"per-entry strong memo does not retain prior chunk geometry")
	var animation_result: Dictionary = writer.write(Animation.new())
	_expect(not bool(animation_result.ok),"animation clocks are rejected rather than narrowed")
	var leaked_image := Resource.new()
	leaked_image.set_meta("texture",texture)
	_expect(not bool(writer.write(leaked_image).ok),"textures outside material slots are rejected")
	var live_node := Node.new()
	var live := Resource.new()
	live.set_meta("callback_target",live_node)
	_expect(not bool(writer.write(live).ok),"live object graph is rejected")
	live_node.free()
	var cyclic := Resource.new()
	cyclic.set_meta("self",cyclic)
	_expect(not bool(writer.write(cyclic).ok),"cyclic resource graph is rejected")
	cyclic.remove_meta("self")
	var shader := Shader.new()
	shader.code = "shader_type spatial;\nuniform sampler2D sample_texture;\nvoid fragment(){ALBEDO=texture(sample_texture,UV).rgb;}"
	shader.set_default_texture_parameter("sample_texture",texture)
	_expect(not bool(writer.write(shader).ok),"Shader-owned default texture is rejected")
	var before := writer.root_path
	var worker := Thread.new()
	worker.start(func() -> Dictionary: return writer.write(packed))
	var off_thread: Dictionary = worker.wait_to_finish()
	_expect(not bool(off_thread.ok) and writer.root_path == before,"worker write rejects before mutating writer state")
	_expect(FileAccess.file_exists(str(result.get("path",""))),"failed attempts preserve earlier qualified blobs")
	print("map geometry writer: ","PASS" if _failures == 0 else "FAIL", " (",_failures,")")
	quit(_failures)

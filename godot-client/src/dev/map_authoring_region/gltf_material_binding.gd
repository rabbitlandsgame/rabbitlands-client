@tool
extends RefCounted

# Temporary, in-memory provenance. ImporterMesh conversion copies this metadata
# to the live mesh; GLTFState's old Node pointers must never be read afterward.
const META := "__eloria_baked_gltf_node_index"

class Capture extends GLTFDocumentExtension:
	func _import_node(state: GLTFState, gltf_node: GLTFNode,
			_json: Dictionary, node: Node) -> Error:
		node.set_meta("__eloria_baked_gltf_node_index", state.get_nodes().find(gltf_node))
		return OK

var _sources: Dictionary = {}


func clear() -> void:
	for context: Dictionary in _sources.values():
		if is_instance_valid(context.get("generated")):
			context.generated.free()
	_sources.clear()


func bind(source_path: String, source_sha256: String, content: Node3D,
		mesh_path: String, surface_index: int) -> Dictionary:
	if not _sources.has(source_path):
		_sources[source_path] = _load_source(source_path)
	var context: Dictionary = _sources[source_path]
	if context.has("error") or not context.get("required", false):
		return context
	if context.sha256 != source_sha256:
		return {"error": "GLB changed while binding material overrides."}
	return bind_context(context, content, mesh_path, surface_index)


func _load_source(source_path: String) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(source_path)
	var file := FileAccess.open(absolute, FileAccess.READ)
	if file == null or file.get_length() < 20:
		return {"error": "Material source is not a complete GLB."}
	if file.get_32() != 0x46546c67 or file.get_32() != 2 or file.get_32() != file.get_length():
		return {"error": "Material source has an invalid GLB header."}
	var length := file.get_32()
	if file.get_32() != 0x4e4f534a or length > file.get_length() - 20:
		return {"error": "Material source has an invalid GLB JSON chunk."}
	var raw: Variant = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	file.close()
	if not raw is Dictionary:
		return {"error": "Material source GLB JSON is not an object."}
	var scenes: Array = raw.get("scenes", [])
	var scene := int(raw.get("scene", 0))
	if scene < 0 or scene >= scenes.size():
		return {"error": "Material source has no selected GLB scene."}
	if scenes[scene].get("nodes", []).is_empty():
		return {"error": "Material source has no selected GLB roots."}
	# Imported names can differ even for a single root. Bind every overridden GLB.
	var bytes := FileAccess.get_file_as_bytes(absolute)
	var context := generate_context(raw, bytes, absolute)
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	context["sha256"] = hash.finish().hex_encode()
	return context


func generate_context(raw: Dictionary, bytes: PackedByteArray, source_path := "") -> Dictionary:
	var capture := Capture.new()
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_handle_binary_image(GLTFState.HANDLE_BINARY_EMBED_AS_UNCOMPRESSED)
	GLTFDocument.register_gltf_document_extension(capture)
	var error := document.append_from_file(source_path, state) if not source_path.is_empty() \
		else document.append_from_buffer(bytes, "", state)
	var generated: Node = null
	if error == OK:
		generated = document.generate_scene(state)
	GLTFDocument.unregister_gltf_document_extension(capture)
	if error != OK or generated == null:
		if is_instance_valid(generated):
			generated.free()
		return {"error": "Could not generate GLB material provenance."}
	var counts := {}
	_count_indices(generated, counts)
	return {"required": true, "generated": generated, "raw": raw, "indexCounts": counts}


func _count_indices(node: Node, counts: Dictionary) -> void:
	if node.has_meta(META):
		var index: int = node.get_meta(META)
		counts[index] = int(counts.get(index, 0)) + 1
	for child in node.get_children():
		_count_indices(child, counts)


func bind_context(context: Dictionary, content: Node3D,
		mesh_path: String, surface_index: int) -> Dictionary:
	var generated: Node = context.generated
	var target := generated.get_node_or_null(NodePath(mesh_path)) as MeshInstance3D
	var cached := content.get_node_or_null(NodePath(mesh_path)) as MeshInstance3D
	if target == null or cached == null or target.mesh == null or cached.mesh == null:
		return {"error": "Material path must resolve to a mesh in both imported trees."}
	var index: int = target.get_meta(META, -1)
	var raw: Dictionary = context.raw
	var nodes: Array = raw.get("nodes", [])
	if index < 0 or index >= nodes.size() or int(context.indexCounts.get(index, 0)) != 1:
		return {"error": "Material target has no unique original GLB node binding."}
	var current: Node = target
	while current != generated:
		var peer := content.get_node_or_null(generated.get_path_to(current))
		if not current is Node3D or not peer is Node3D or current.transform != peer.transform:
			return {"error": "Material target ancestor transforms differ from imported source."}
		current = current.get_parent()
	if not generated is Node3D or generated.transform != content.transform:
		return {"error": "Material Content root transform differs from imported source."}
	var mesh_index := int(nodes[index].get("mesh", -1))
	var meshes: Array = raw.get("meshes", [])
	if mesh_index < 0 or mesh_index >= meshes.size():
		return {"error": "Bound original GLB node has no mesh."}
	var primitives: Array = meshes[mesh_index].get("primitives", [])
	if surface_index < 0 or surface_index >= primitives.size() or \
			target.mesh.get_surface_count() != primitives.size() or cached.mesh.get_surface_count() != primitives.size():
		return {"error": "Material surface counts or target index differ from original GLB."}
	var accessors: Array = raw.get("accessors", [])
	var materials: Array = raw.get("materials", [])
	for i in primitives.size():
		var primitive: Dictionary = primitives[i]
		var material_index := int(primitive.get("material", -1))
		var name := String(materials[material_index].get("name", "")) if material_index >= 0 and material_index < materials.size() else ""
		var generated_arrays := target.mesh.surface_get_arrays(i)
		var cached_arrays := cached.mesh.surface_get_arrays(i)
		var generated_indices: PackedInt32Array = generated_arrays[Mesh.ARRAY_INDEX]
		var cached_indices: PackedInt32Array = cached_arrays[Mesh.ARRAY_INDEX]
		if generated_arrays[Mesh.ARRAY_VERTEX].size() != cached_arrays[Mesh.ARRAY_VERTEX].size() or \
				generated_indices.size() != cached_indices.size():
			return {"error": "Generated and cached material surface geometry counts differ."}
		for mesh: Mesh in [target.mesh, cached.mesh]:
			if not mesh is ArrayMesh or mesh.surface_get_name(i) != name:
				return {"error": "Material surface order/name differs from original GLB."}
			# Native import may weld redundant vertices. A sole surface has no
			# primitive-order ambiguity; the exporter still retains original bytes.
			if primitives.size() == 1:
				continue
			var arrays := mesh.surface_get_arrays(i)
			var position := int(primitive.get("attributes", {}).get("POSITION", -1))
			var indices := int(primitive.get("indices", -1))
			if position < 0 or position >= accessors.size() or \
					arrays[Mesh.ARRAY_VERTEX].size() != int(accessors[position].get("count", -1)):
				return {"error": "Material surface vertex count differs from original GLB."}
			var actual_indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if (indices >= 0 and (indices >= accessors.size() or actual_indices.size() != int(accessors[indices].get("count", -1)))) or \
					(indices < 0 and not actual_indices.is_empty()):
				return {"error": "Material surface index count differs from original GLB."}
	return {"bakedMeshNodeIndex": index}

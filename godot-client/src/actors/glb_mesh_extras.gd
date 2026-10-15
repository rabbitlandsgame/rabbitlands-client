class_name GlbMeshExtras
extends RefCounted
## Reads only the JSON metadata needed by equipment presentation.
##
## Equipment geometry is loaded through GlbSceneCache so it can retain Godot's
## imported LOD chains. Running a second GLTFDocument import merely to recover
## `bodyCover` and `coversHair` would undo much of that win, so this reader stops
## after the small JSON chunk and never decodes buffers, images or meshes.

const GLB_MAGIC := 0x46546C67
const GLB_VERSION := 2
const JSON_CHUNK := 0x4E4F534A
const HEADER_BYTES := 12
const CHUNK_HEADER_BYTES := 8


## Returns mesh/node name -> the mesh's extras dictionary.
static func read(path: String) -> Dictionary:
	var external_path := (ProjectSettings.globalize_path(path)
		if path.begins_with("res://") else path)
	if not FileAccess.file_exists(external_path):
		return {}
	var document: Variant
	match external_path.get_extension().to_lower():
		"glb":
			document = _read_glb_json(external_path)
		"gltf":
			document = JSON.parse_string(FileAccess.get_file_as_string(external_path))
		_:
			return {}
	if document is not Dictionary:
		return {}
	return _index_extras(document as Dictionary)


static func _read_glb_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() < HEADER_BYTES:
		return null
	file.big_endian = false
	if file.get_32() != GLB_MAGIC or file.get_32() != GLB_VERSION:
		return null
	var declared_length := int(file.get_32())
	var safe_length := mini(declared_length, file.get_length())
	while file.get_position() + CHUNK_HEADER_BYTES <= safe_length:
		var chunk_length := int(file.get_32())
		var chunk_type := file.get_32()
		var remaining := safe_length - file.get_position()
		if chunk_length < 0 or chunk_length > remaining:
			return null
		if chunk_type == JSON_CHUNK:
			var bytes := file.get_buffer(chunk_length)
			# JSON chunks normally use spaces for four-byte alignment. Tolerate
			# NULs from older exporters without handing them to the JSON parser.
			while not bytes.is_empty() and bytes[bytes.size() - 1] in [0, 9, 10, 13, 32]:
				bytes.resize(bytes.size() - 1)
			return JSON.parse_string(bytes.get_string_from_utf8())
		file.seek(file.get_position() + chunk_length)
	return null


static func _index_extras(document: Dictionary) -> Dictionary:
	var indexed: Dictionary = {}
	var by_index: Array[Dictionary] = []
	var meshes_value: Variant = document.get("meshes", [])
	if meshes_value is not Array:
		return indexed
	for mesh_value: Variant in meshes_value as Array:
		var mesh := mesh_value as Dictionary
		var extras: Dictionary = {}
		if mesh.get("extras", {}) is Dictionary:
			extras = (mesh.get("extras", {}) as Dictionary).duplicate(true)
		by_index.append(extras)
		var mesh_name := str(mesh.get("name", ""))
		if not mesh_name.is_empty():
			indexed[mesh_name] = extras

	# Godot names a MeshInstance3D from its glTF node. Generated equipment
	# currently uses matching mesh/node names, but indexing both makes the
	# metadata survive future authoring files that distinguish them.
	var nodes_value: Variant = document.get("nodes", [])
	if nodes_value is Array:
		for node_value: Variant in nodes_value as Array:
			var node := node_value as Dictionary
			if not node.has("mesh"):
				continue
			var mesh_index := int(node.get("mesh", -1))
			var node_name := str(node.get("name", ""))
			if not node_name.is_empty() and mesh_index >= 0 and mesh_index < by_index.size():
				indexed[node_name] = by_index[mesh_index]
	return indexed

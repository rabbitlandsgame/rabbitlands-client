extends RefCounted
## Recompute the reviewed head-fit invariant from actual GLB payloads.
## Only declared skin rows and appended joints may differ. No extras digest is trusted.
const COMPONENT_BYTES := {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
const COMPONENTS := {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
const SKIN_ATTRIBUTES := ["JOINTS_0", "WEIGHTS_0", "JOINTS_1", "WEIGHTS_1"]

static func _feed(context: HashingContext, label: String, data: PackedByteArray) -> void:
	context.update(("%d:%s:%d:" % [label.length(), label, data.size()]).to_utf8_buffer())
	if not data.is_empty():
		context.update(data)

static func _json(context: HashingContext, label: String, value: Variant) -> void:
	_feed(context, label, JSON.stringify(value, "", true, true).to_utf8_buffer())

static func _accessor(g: Dictionary, blob: PackedByteArray, index: int) -> Array:
	var accessor: Dictionary = g.accessors[index]
	var metadata: Dictionary = accessor.duplicate(true)
	for key: String in ["bufferView", "byteOffset", "sparse"]:
		metadata.erase(key)
	var width := int(COMPONENT_BYTES[int(accessor.componentType)]) * int(COMPONENTS[str(accessor.type)])
	var data := PackedByteArray()
	if accessor.has("bufferView"):
		var view: Dictionary = g.bufferViews[int(accessor.bufferView)]
		var start := int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
		var stride := int(view.get("byteStride", width))
		if stride == width:
			data = blob.slice(start, start + int(accessor.count) * width)
		else:
			for row: int in int(accessor.count):
				data.append_array(blob.slice(start + row * stride, start + row * stride + width))
	var extras: Array[PackedByteArray] = []
	if accessor.has("sparse"):
		var sparse: Dictionary = accessor.sparse
		metadata.sparse = {"count": sparse.count, "indexComponentType": sparse.indices.componentType}
		for key: String in ["indices", "values"]:
			var part: Dictionary = sparse[key]
			var view: Dictionary = g.bufferViews[int(part.bufferView)]
			var start := int(view.get("byteOffset", 0)) + int(part.get("byteOffset", 0))
			var size := int(COMPONENT_BYTES[int(part.componentType)]) if key == "indices" else width
			extras.append(blob.slice(start, start + int(sparse.count) * size))
	return [metadata, data, extras]

static func _add_accessor(context: HashingContext, label: String, g: Dictionary,
		blob: PackedByteArray, index: int, excluded: Array = []) -> void:
	var parts := _accessor(g, blob, index)
	_json(context, label + ".meta", parts[0])
	var data: PackedByteArray = parts[1]
	if not excluded.is_empty():
		var accessor: Dictionary = g.accessors[index]
		var stride := int(COMPONENT_BYTES[int(accessor.componentType)]) * int(COMPONENTS[str(accessor.type)])
		var skip := {}
		for row: Variant in excluded:
			skip[int(row)] = true
		var kept := PackedByteArray()
		for row: int in int(accessor.count):
			if not skip.has(row):
				kept.append_array(data.slice(row * stride, (row + 1) * stride))
		data = kept
	_feed(context, label + ".data", data)
	for i: int in (parts[2] as Array).size():
		_feed(context, label + ".sparse" + str(i), parts[2][i])

static func digest(path: String, scope: Dictionary) -> String:
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.size() < 28 or bytes.decode_u32(0) != 0x46546c67:
		return ""
	var json_size := bytes.decode_u32(12)
	var parsed: Variant = JSON.parse_string(bytes.slice(20, 20 + json_size).get_string_from_utf8())
	if parsed is not Dictionary:
		return ""
	var g: Dictionary = parsed
	var binary_header := 20 + json_size
	var blob := bytes.slice(binary_header + 8, binary_header + 8 + bytes.decode_u32(binary_header))
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	var masks: Dictionary = scope.allowed_weight_masks
	var source_nodes := int(scope.source_node_count)
	var asset: Dictionary = g.asset.duplicate(true)
	((asset.get("extras", {}) as Dictionary).get("rlHead", {}) as Dictionary).erase("skinRepair")
	_json(context, "asset", asset)
	for key: String in ["materials", "textures", "samplers", "scenes"]:
		_json(context, key, g.get(key, []))
	_json(context, "scene", g.get("scene", 0))
	_json(context, "masks", masks)
	for i: int in source_nodes:
		var node: Dictionary = g.nodes[i].duplicate(true)
		if node.has("children"):
			var kept: Array = []
			for child: Variant in node.children:
				if int(child) < source_nodes:
					kept.append(child)
			node.children = kept
		_json(context, "node" + str(i), node)
	var skin: Dictionary = g.skins[0]
	var names: Array = []
	for i: int in 3:
		names.append(g.nodes[int(skin.joints[i])].get("name", ""))
	_json(context, "skin.prefix", names)
	var skin_metadata: Dictionary = skin.duplicate(true)
	skin_metadata.erase("joints")
	skin_metadata.erase("inverseBindMatrices")
	_json(context, "skin.metadata", skin_metadata)
	var ibm := _accessor(g, blob, int(skin.inverseBindMatrices))
	_feed(context, "skin.ibm3", (ibm[1] as PackedByteArray).slice(0, 3 * 16 * 4))
	for mi: int in g.meshes.size():
		var mesh: Dictionary = g.meshes[mi]
		var metadata: Dictionary = mesh.duplicate(true)
		metadata.erase("primitives")
		_json(context, "mesh%d.metadata" % mi, metadata)
		for pi: int in mesh.primitives.size():
			var primitive: Dictionary = mesh.primitives[pi]
			var label := "mesh%d.prim%d" % [mi, pi]
			metadata = primitive.duplicate(true)
			for key: String in ["attributes", "targets", "indices"]:
				metadata.erase(key)
			_json(context, label + ".metadata", metadata)
			var keys: Array = primitive.attributes.keys()
			keys.sort()
			_json(context, label + ".attributes", keys)
			for key: String in keys:
				var excluded: Array = masks.get("%d:%d" % [mi, pi], []) if key in SKIN_ATTRIBUTES else []
				_add_accessor(context, label + "." + key, g, blob, int(primitive.attributes[key]), excluded)
			if primitive.has("indices"):
				_add_accessor(context, label + ".indices", g, blob, int(primitive.indices))
			var targets: Array = primitive.get("targets", [])
			_json(context, label + ".targetCount", targets.size())
			for ti: int in targets.size():
				keys = targets[ti].keys()
				keys.sort()
				_json(context, label + ".target%d.attributes" % ti, keys)
				for key: String in keys:
					_add_accessor(context, label + ".target%d." % ti + key, g, blob, int(targets[ti][key]))
	var images: Array = g.get("images", [])
	for i: int in images.size():
		var image: Dictionary = images[i]
		var metadata: Dictionary = image.duplicate(true)
		metadata.erase("bufferView")
		_json(context, "image" + str(i), metadata)
		if image.has("bufferView"):
			var view: Dictionary = g.bufferViews[int(image.bufferView)]
			var start := int(view.get("byteOffset", 0))
			_feed(context, "imageBytes" + str(i), blob.slice(start, start + int(view.byteLength)))
		elif image.has("uri"):
			# These heads have no external GLB images; reject rather than omit one.
			return ""
	var external: Dictionary = scope.get("external_images", {})
	var paths: Array = external.keys()
	paths.sort()
	for image_path: String in paths:
		if FileAccess.get_sha256(image_path) != str(external[image_path]):
			return ""
		_feed(context, "externalImage:" + image_path, FileAccess.get_file_as_bytes(image_path))
	var absent: Array = scope.get("absent_external_images", [])
	_json(context, "absentExternalImages", absent)
	for image_path: String in absent:
		if FileAccess.file_exists(image_path):
			return ""
	var dependency: Dictionary = scope.get("texture_manifest_dependency", {})
	if not dependency.is_empty():
		var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(str(dependency.path)))
		if manifest is not Dictionary:
			return ""
		var top := {}
		var materials := {}
		var material_entries: Dictionary = (manifest as Dictionary).get("materials", {})
		for key: String in dependency["keys"]:
			top[key] = (manifest as Dictionary).get(key)
			materials[key] = material_entries.get(key)
		_json(context, "textureManifest", {"top": top, "materials": materials,
			"eye_iris": (manifest as Dictionary).get("eye_iris")})
	return context.finish().hex_encode()

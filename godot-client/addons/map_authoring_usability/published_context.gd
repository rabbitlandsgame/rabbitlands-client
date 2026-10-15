@tool
extends RefCounted
## The walk decks and solids the continent composer adds to a territory's
## published package that its authoring scene does not contain: border
## thresholds, cave-door and discovery decks, designed decks, composed bridge
## parts. Live walkability uses them as fixed, read-only context, so the next
## bake's estimate is not wrong at every threshold the map team composes.
##
## They are read from the package the bake itself reads (the manifest's
## world.glb): mesh nodes under a Walk_ ancestor without a ceiling word are
## decks, meshes under a manifest collision.nodeNames root (and not under a
## surface) are solids, exactly as collision_export._mesh_groups classifies
## them. Anything whose ancestry names something the scene carries (a placed
## asset's node name, a bridge) is left out: the scene's own version wins.
##
## Only the GLB's JSON and the accessors of the chosen meshes are read, and
## the result is cached per file revision.

const TimeOfDay := preload("res://addons/map_authoring_usability/time_of_day_preview.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")
const CEILINGS := ["ceiling", "soffit", "underside", "roof"]
const SURFACE_PREFIXES := ["Terrain_", "Walk_"]

static var _cache := {}


## {"decks": [{name, triangles}], "solids": [{name, triangles}], "path",
## "error"} for `root`'s published package, triangles in the territory frame
## in glTF (counter-clockwise) order.
static func context_for(root: Node3D) -> Dictionary:
	var manifest_path := TimeOfDay.manifest_path_for(String(root.get("region_id")))
	if manifest_path.is_empty():
		return {"decks": [], "solids": [], "error": "No published package."}
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not manifest is Dictionary:
		return {"decks": [], "solids": [], "error": "The published manifest could not be read."}
	var asset: Dictionary = (manifest as Dictionary).get("asset", {})
	var glb := manifest_path.get_base_dir().path_join(String(asset.get("glb", "world.glb")))
	var solid_roots := {}
	for name: Variant in ((manifest as Dictionary).get("collision", {}) as Dictionary).get("nodeNames", []):
		solid_roots[String(name)] = true
	var prefixes: Array = ((manifest as Dictionary).get("navigation", {}) as Dictionary).get(
		"surfaceNodePrefixes", SURFACE_PREFIXES)
	return read_package(glb, solid_roots, prefixes, scene_names(root))


## What the scene carries itself, whose published versions it replaces:
## {"assets": {placed asset node name: true}, "bridges": [bridge names]}.
static func scene_names(root: Node3D) -> Dictionary:
	var assets := {}
	var holder := root.get_node_or_null("AuthoredAssets")
	if holder != null:
		for child in holder.get_children():
			if child.get_script() == ASSET_SCRIPT:
				assets[String(child.get("node_name"))] = true
	var bridges := PackedStringArray()
	var bridge_holder := root.get_node_or_null("Bridges")
	if bridge_holder != null:
		for child in bridge_holder.get_children():
			bridges.append(String(child.name))
			if child.get("bridge_id") != null and not String(child.get("bridge_id")).is_empty():
				bridges.append(String(child.get("bridge_id")))
	return {"assets": assets, "bridges": bridges}


## Whether a published node name belongs to something the scene carries: a
## placed asset (its node, its companions, its Walk_ subtree root) or a bridge.
static func carried_by_scene(name: String, excluded: Dictionary) -> bool:
	var assets: Dictionary = excluded.get("assets", {})
	var bare := name.substr(5) if name.begins_with("Walk_") else name
	if assets.has(name) or assets.has(bare) or assets.has(name.get_slice("__", 0)) or 			assets.has(bare.get_slice("__", 0)):
		return true
	for bridge: String in excluded.get("bridges", PackedStringArray()):
		if not bridge.is_empty() and (bare == bridge or bare.begins_with(bridge + "_")):
			return true
	return false


## Reads the composer-only decks and solids of a GLB (see the header).
static func read_package(glb_path: String, solid_roots: Dictionary, prefixes: Array,
		excluded: Dictionary) -> Dictionary:
	if not FileAccess.file_exists(glb_path):
		return {"decks": [], "solids": [], "error": "The published package %s is missing." % glb_path}
	var key := "%s|%d|%d|%s|%s" % [glb_path, FileAccess.get_modified_time(glb_path),
		hash(solid_roots.keys()), hash(prefixes), hash([(excluded.get("assets", {}) as Dictionary).keys(),
			excluded.get("bridges", PackedStringArray())])]
	if _cache.has(key):
		return _cache[key]
	var file := FileAccess.open(glb_path, FileAccess.READ)
	if file == null or file.get_32() != 0x46546C67:
		return {"decks": [], "solids": [], "error": "%s is not a GLB." % glb_path.get_file()}
	file.get_32()
	file.get_32()
	var json_length := file.get_32()
	file.get_32()
	var document: Variant = JSON.parse_string(file.get_buffer(json_length).get_string_from_utf8())
	if not document is Dictionary:
		return {"decks": [], "solids": [], "error": "%s has no readable JSON." % glb_path.get_file()}
	file.get_32()
	file.get_32()
	var binary_start := file.get_position()
	var gltf: Dictionary = document
	var nodes: Array = gltf.get("nodes", [])
	var parents := {}
	for index in nodes.size():
		for child: Variant in (nodes[index] as Dictionary).get("children", []):
			parents[int(child)] = index
	var worlds := {}
	var decks: Array = []
	var solids: Array = []
	var meshes := {}
	for index in nodes.size():
		var node: Dictionary = nodes[index]
		if not node.has("mesh"):
			continue
		var ancestry := PackedStringArray()
		var current := index
		while true:
			ancestry.append(String((nodes[current] as Dictionary).get("name", "")))
			if not parents.has(current):
				break
			current = int(parents[current])
		var surface := false
		var walk := false
		var ceiling := false
		var solid_root := false
		for name in ancestry:
			for prefix: String in prefixes:
				surface = surface or name.begins_with(prefix)
			walk = walk or name.begins_with("Walk_")
			var lower := name.to_lower()
			for word: String in CEILINGS:
				ceiling = ceiling or word in lower
			solid_root = solid_root or solid_roots.has(name)
		var deck := surface and walk and not ceiling
		var solid := solid_root and not (surface and not ceiling)
		if not deck and not solid:
			continue
		var skip := false
		for name in ancestry:
			skip = skip or carried_by_scene(name, excluded)
		if skip:
			continue
		var mesh_index := int(node.mesh)
		if not meshes.has(mesh_index):
			meshes[mesh_index] = _mesh_triangles(file, binary_start, gltf, mesh_index)
		var local: PackedVector3Array = meshes[mesh_index]
		if local.is_empty():
			continue
		var transform := _world_transform(nodes, parents, index, worlds)
		var triangles := PackedVector3Array()
		triangles.resize(local.size())
		for vertex in local.size():
			triangles[vertex] = transform * local[vertex]
		var label := ancestry[ancestry.size() - 1] if ancestry.size() > 1 else ancestry[0]
		for name in ancestry:
			if name.begins_with("Walk_") or solid_roots.has(name):
				label = name
				break
		var record := {"name": label, "triangles": triangles}
		if deck:
			decks.append(record)
		if solid:
			solids.append(record)
	var result := {"decks": decks, "solids": solids, "path": glb_path}
	_cache[key] = result
	return result


static func _world_transform(nodes: Array, parents: Dictionary, index: int,
		worlds: Dictionary) -> Transform3D:
	if worlds.has(index):
		return worlds[index]
	var node: Dictionary = nodes[index]
	var local := Transform3D.IDENTITY
	if node.has("matrix"):
		var m: Array = node.matrix
		local = Transform3D(Basis(Vector3(m[0], m[1], m[2]), Vector3(m[4], m[5], m[6]),
			Vector3(m[8], m[9], m[10])), Vector3(m[12], m[13], m[14]))
	else:
		var t: Array = node.get("translation", [0.0, 0.0, 0.0])
		var r: Array = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
		var s: Array = node.get("scale", [1.0, 1.0, 1.0])
		local = Transform3D(Basis(Quaternion(r[0], r[1], r[2], r[3])).scaled(
			Vector3(s[0], s[1], s[2])), Vector3(t[0], t[1], t[2]))
	var world := local
	if parents.has(index):
		world = _world_transform(nodes, parents, int(parents[index]), worlds) * local
	worlds[index] = world
	return world


## The triangle corners of a glTF mesh's triangle primitives, in file order.
static func _mesh_triangles(file: FileAccess, binary_start: int, gltf: Dictionary,
		mesh_index: int) -> PackedVector3Array:
	var result := PackedVector3Array()
	var mesh: Dictionary = (gltf.get("meshes", []) as Array)[mesh_index]
	for primitive_value: Variant in mesh.get("primitives", []):
		var primitive: Dictionary = primitive_value
		if int(primitive.get("mode", 4)) != 4:
			continue
		var positions := _positions(file, binary_start, gltf,
			int((primitive.attributes as Dictionary).POSITION))
		if primitive.has("indices"):
			for corner in _indices(file, binary_start, gltf, int(primitive.indices)):
				if corner < positions.size():
					result.append(positions[corner])
		else:
			result.append_array(positions)
	return result


static func _accessor_bytes(file: FileAccess, binary_start: int, gltf: Dictionary,
		accessor_index: int, element_size: int) -> Dictionary:
	var accessor: Dictionary = (gltf.accessors as Array)[accessor_index]
	var view: Dictionary = (gltf.bufferViews as Array)[int(accessor.bufferView)]
	var stride := int(view.get("byteStride", element_size))
	var count := int(accessor.count)
	var start := binary_start + int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
	file.seek(start)
	var length := stride * (count - 1) + element_size if count > 0 else 0
	return {"bytes": file.get_buffer(length), "stride": stride, "count": count,
		"type": int(accessor.componentType)}


static func _positions(file: FileAccess, binary_start: int, gltf: Dictionary,
		accessor_index: int) -> PackedVector3Array:
	var read := _accessor_bytes(file, binary_start, gltf, accessor_index, 12)
	var bytes: PackedByteArray = read.bytes
	var result := PackedVector3Array()
	result.resize(int(read.count))
	var stride := int(read.stride)
	for index in int(read.count):
		var at := index * stride
		result[index] = Vector3(bytes.decode_float(at), bytes.decode_float(at + 4),
			bytes.decode_float(at + 8))
	return result


static func _indices(file: FileAccess, binary_start: int, gltf: Dictionary,
		accessor_index: int) -> PackedInt32Array:
	var component := int(((gltf.accessors as Array)[accessor_index] as Dictionary).componentType)
	var size := 4 if component == 5125 else 2 if component == 5123 else 1
	var read := _accessor_bytes(file, binary_start, gltf, accessor_index, size)
	var bytes: PackedByteArray = read.bytes
	var stride := int(read.stride)
	var result := PackedInt32Array()
	result.resize(int(read.count))
	for index in int(read.count):
		var at := index * stride
		result[index] = bytes.decode_u32(at) if size == 4 else bytes.decode_u16(at) if size == 2 \
			else bytes.decode_u8(at)
	return result

extends SceneTree

const BINDING := preload("res://src/dev/map_authoring_region/gltf_material_binding.gd")
const SNAPSHOT := preload("res://src/dev/map_authoring_region/region_snapshot.gd")
const ASSET := preload("res://src/dev/map_authoring_region/asset_control.gd")
const OVERRIDE := preload("res://src/dev/map_authoring_region/asset_surface_override.gd")
var failures := 0
var assertions := 0


func _initialize() -> void:
	call_deferred("run")


func expect(value: bool, label: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error(label)


func glb(raw: Dictionary, body: PackedByteArray) -> PackedByteArray:
	var json := JSON.stringify(raw).to_utf8_buffer()
	while json.size() % 4:
		json.append(32)
	var bytes := PackedByteArray()
	bytes.resize(20)
	bytes.encode_u32(0, 0x46546c67)
	bytes.encode_u32(4, 2)
	bytes.encode_u32(8, 28 + json.size() + body.size())
	bytes.encode_u32(12, json.size())
	bytes.encode_u32(16, 0x4e4f534a)
	bytes.append_array(json)
	var header := PackedByteArray()
	header.resize(8)
	header.encode_u32(0, body.size())
	header.encode_u32(4, 0x004e4942)
	bytes.append_array(header)
	bytes.append_array(body)
	return bytes


func find_index(node: Node, index: int) -> Node:
	if node.get_meta(BINDING.META, -1) == index:
		return node
	for child in node.get_children():
		var found := find_index(child, index)
		if found != null:
			return found
	return null


func representation_mesh(vertices: int, indices: int = 3, surfaces: int = 1) -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	var points := PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.BACK])
	while points.size() < vertices:
		points.append(Vector3.ZERO)
	var elements := PackedInt32Array([0, 1, 2])
	while elements.size() < indices:
		elements.append(elements.size() % 3)
	arrays[Mesh.ARRAY_VERTEX] = points
	arrays[Mesh.ARRAY_INDEX] = elements
	var mesh := ArrayMesh.new()
	for i in surfaces:
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_name(i, "stone")
	return mesh


func test_single_root_representation(binder, raw: Dictionary, body: PackedByteArray) -> void:
	var single := raw.duplicate(true)
	single.scenes[0].nodes = [4]
	var context: Dictionary = binder.generate_context(single, glb(single, body))
	var peer: Dictionary = binder.generate_context(single, glb(single, body))
	expect(not context.has("error") and not peer.has("error"), "single-root GLB imports")
	if context.has("error") or peer.has("error"):
		if context.has("generated"):
			context.generated.free()
		if peer.has("generated"):
			peer.generated.free()
		return
	var generated: Node3D = context.generated
	var cached: Node3D = peer.generated
	var target := find_index(generated, 1) as MeshInstance3D
	expect(target != null, "single-root live target has original provenance")
	if target == null:
		generated.free()
		cached.free()
		return
	var path := String(generated.get_path_to(target))
	var cached_target := cached.get_node(NodePath(path)) as MeshInstance3D
	expect(binder.bind_context(context, cached, path, 0).get("bakedMeshNodeIndex", -1) == 1,
		"actual single-root imported path binds exact raw node")
	# Model a redundant vertex representation without changing the source GLB.
	# Both imported trees agree; the original sole primitive remains three vertices.
	target.mesh = representation_mesh(4)
	cached_target.mesh = representation_mesh(4)
	expect(binder.bind_context(context, cached, path, 0).get("bakedMeshNodeIndex", -1) == 1,
		"sole-surface identity permits equal imported counts differing from raw")
	cached_target.mesh = representation_mesh(3)
	expect(binder.bind_context(context, cached, path, 0).has("error"),
		"cached/generated vertex count mismatch rejected")
	cached_target.mesh = representation_mesh(4, 6)
	expect(binder.bind_context(context, cached, path, 0).has("error"),
		"cached/generated index count mismatch rejected")
	context.raw.meshes[0].primitives.append(context.raw.meshes[0].primitives[0].duplicate(true))
	target.mesh = representation_mesh(4, 3, 2)
	cached_target.mesh = representation_mesh(4, 3, 2)
	expect(binder.bind_context(context, cached, path, 0).has("error"),
		"multi-surface representation changes retain strict raw count guard")
	generated.free()
	cached.free()


func run() -> void:
	# Synthetic GLB bytes only: no fixture files, imports, scenes or resources saved.
	var body := PackedFloat32Array([0, 0, 0, 1, 0, 0, 0, 0, 1]).to_byte_array()
	body.append_array(PackedInt32Array([0, 1, 2]).to_byte_array())
	var raw := {"asset": {"version": "2.0"}, "scene": 0,
		"scenes": [{"nodes": [4, 2]}],
		"nodes": [{"name": "Pier", "children": [1]}, {"name": "Stone", "mesh": 0},
			{"name": "Walk", "mesh": 0, "translation": [0, 0, 2]}, {"name": "Unused"},
			{"name": "Pier", "children": [0], "translation": [1, 2, 3]}],
		"meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
		"materials": [{"name": "stone"}], "buffers": [{"byteLength": 48}],
		"bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
			{"buffer": 0, "byteOffset": 36, "byteLength": 12}],
		"accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
			"min": [0, 0, 0], "max": [1, 0, 1]},
			{"bufferView": 1, "componentType": 5125, "count": 3, "type": "SCALAR"}]}
	var binder := BINDING.new()
	var context := binder.generate_context(raw, glb(raw, body))
	var peer := binder.generate_context(raw, glb(raw, body))
	expect(not context.has("error") and not peer.has("error"), "synthetic multi-root imports")
	if context.has("error") or peer.has("error"):
		if context.has("generated"):
			context.generated.free()
		if peer.has("generated"):
			peer.generated.free()
		quit(1)
		return
	var generated: Node3D = context.generated
	var cached: Node3D = peer.generated
	var target := find_index(generated, 1)
	expect(target is MeshInstance3D, "preconversion metadata survives live mesh replacement")
	var path := String(generated.get_path_to(target))
	var result := binder.bind_context(context, cached, path, 0)
	expect(result.get("bakedMeshNodeIndex", -1) == 1, "exact raw node index through duplicate names")
	expect(path.split("/").size() == 3, "both duplicate wrapper levels retained")
	expect(binder.bind_context(context, cached, "Pier/Stone", 0).has("error"), "stale saved path rejected")
	expect(binder.bind_context(context, cached, ".", 0).has("error"), "container target rejected")
	expect(binder.bind_context(context, cached, path, 1).has("error"), "out-of-range surface rejected")
	context.indexCounts[1] = 2
	expect(binder.bind_context(context, cached, path, 0).has("error"), "ambiguous provenance rejected")
	context.indexCounts[1] = 1
	var cached_target := cached.get_node(NodePath(path)) as MeshInstance3D
	cached_target.position.x += 1
	expect(binder.bind_context(context, cached, path, 0).has("error"), "transform mismatch rejected")
	cached_target.position.x -= 1
	context.raw.meshes[0].primitives[0].material = -1
	expect(binder.bind_context(context, cached, path, 0).has("error"), "raw material mismatch rejected")
	context.raw.meshes[0].primitives[0].material = 0
	# Exercise actual snapshot target rejection, independently of source binding.
	var asset := ASSET.new()
	asset.name = "FixtureAsset"
	root.add_child(asset)
	asset.add_child(cached)
	var override := OVERRIDE.new()
	asset.material_overrides = [override]
	var snapshot := SNAPSHOT.new()
	for invalid: Array in [["Missing", 0], [".", 0], [path, 1]]:
		override.mesh_node_path = invalid[0]
		override.surface_index = invalid[1]
		snapshot.errors.clear()
		expect(snapshot._asset_surface_records(asset).is_empty() and not snapshot.errors.is_empty(),
			"snapshot rejects invalid saved mesh/surface: %s" % str(invalid))
	asset.free()
	generated.free()
	test_single_root_representation(binder, raw, body)
	binder.clear()
	print("GLTF material binding: %d assertions, %d failures" % [assertions, failures])
	quit(1 if failures else 0)

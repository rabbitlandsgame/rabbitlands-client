class_name RLHeadBodyCut
extends RefCounted
## Takes the body's own head off a luminous body wearing an RL head.
##
## The head module brings the face, the cranium and the neck down to a rim; the
## body keeps everything below. Which body triangles go is the head's to say:
## `rlHead.bodyCut.hiddenBodyTriangles` lists them, as runs of triangle indices
## of the body mesh's single primitive in file order, against the body file
## whose SHA-256 it names. The list is trusted only after it has been checked
## against the mesh Godot actually built: the same triangle count and every
## listed triangle's corners where the file puts them (a runtime GLTFDocument
## parse keeps the file's order and positions; an optimising importer would
## not). Anything else falls back to the head's geometric rule (`bodyCut.rule`):
## a triangle goes when its corners lie past the plane `travel` metres up the
## neck_01 -> Head axis, in the body's bind space - all three of them, or any
## one when the rule says "any corner", as it does since the head brought its
## own `rl_bodypatch` to fill the clipped part back in. On the v1 and v2
## bodies the list and the rule agree exactly.
##
## A cut is an index-buffer copy, shared by every actor with the same source
## mesh and the same head, like TorsoBodyCover's. It composes with that cover
## by always cutting whatever mesh the body is showing: the actor re-applies
## it after each wardrobe pass (ReplicatedActor3D._refresh_wardrobe_cover),
## and since a torso cut keeps the body's vertex buffer and only filters its
## triangles, the hidden set is held as vertex-index triplets, which identify a
## triangle in the original and in every cut derived from it. The original
## stays on the node as TorsoBodyCover's `uncovered_body_mesh`, so the cover
## and NecklineSkin keep working from the uncut body exactly as they do for
## every other actor.

const SOURCE_META := &"rl_head_cut_source"
const CUT_META := &"rl_head_cut"
const KEY_META := &"rl_head_cut_head"
## How close a listed corner must be to the built one, in metres.
const POSITION_TOLERANCE := 0.0002

## Original body mesh id + head path -> {"source": WeakRef, "hidden": {Vector3i: true},
## "hidden_vertices": {int: true}, "method": String}.
static var _plans: Dictionary = {}
## Source mesh id + head path -> {"source": WeakRef, "mesh": ArrayMesh}.
static var _cuts: Dictionary = {}


static func clear() -> void:
	_plans.clear()
	_cuts.clear()


## Cuts the body node for the head `head_info` (RLHeadLibrary.head). The body's
## current mesh is the one cut; `body_scene` is the body GLB the list was made
## against. Safe to call again: a node already showing its cut is left alone.
static func apply(body: MeshInstance3D, head_info: Dictionary, body_scene: String,
		skeleton: Skeleton3D) -> void:
	if body == null or body.mesh == null or head_info.is_empty():
		return
	var head_path := str(head_info.get("path", ""))
	if body.has_meta(CUT_META) and body.get_meta(CUT_META) == body.mesh:
		if str(body.get_meta(KEY_META, "")) == head_path:
			return
		restore(body)
	if not body.has_meta(&"uncovered_body_mesh"):
		# TorsoBodyCover keeps the uncut body here once it has cut one; seeding
		# it now means its passes, and NecklineSkin's, read the original rather
		# than this head cut.
		body.set_meta(&"uncovered_body_mesh", body.mesh)
	var original := body.get_meta(&"uncovered_body_mesh") as Mesh
	var plan := _plan(original, head_info, body_scene, body, skeleton)
	if plan.is_empty():
		return
	var source := body.mesh
	var key := "%d|%s" % [source.get_instance_id(), head_path]
	var entry: Dictionary = _cuts.get(key, {}) as Dictionary
	var cut: Mesh = null
	if not entry.is_empty() and (entry["source"] as WeakRef).get_ref() == source:
		cut = entry["mesh"] as Mesh
	if cut == null:
		_evict_stale()
		cut = _cut(source, plan)
		_cuts[key] = {"source": weakref(source), "mesh": cut}
	body.set_meta(SOURCE_META, source)
	body.set_meta(CUT_META, cut)
	body.set_meta(KEY_META, head_path)
	body.mesh = cut


## Puts the mesh the cut was made from back on the node.
static func restore(body: MeshInstance3D) -> void:
	if body == null:
		return
	if body.has_meta(CUT_META) and body.get_meta(CUT_META) == body.mesh and body.has_meta(SOURCE_META):
		body.mesh = body.get_meta(SOURCE_META) as Mesh
	for meta: StringName in [CUT_META, SOURCE_META, KEY_META]:
		if body.has_meta(meta):
			body.remove_meta(meta)


## How the hidden set for `original` was decided: "list" or "geometric", with
## the triangle count; {} before anything was cut. For tests and the lab.
static func describe(original: Mesh, head_path: String) -> Dictionary:
	var plan: Dictionary = _plans.get("%d|%s" % [original.get_instance_id(), head_path], {}) as Dictionary
	if plan.is_empty():
		return {}
	return {"method": plan["method"], "hidden_triangles": (plan["hidden"] as Dictionary).size(),
		"reason": plan.get("reason", "")}


static func _plan(original: Mesh, head_info: Dictionary, body_scene: String,
		body: MeshInstance3D, skeleton: Skeleton3D) -> Dictionary:
	var key := "%d|%s" % [original.get_instance_id(), str(head_info.get("path", ""))]
	var cached: Dictionary = _plans.get(key, {}) as Dictionary
	if not cached.is_empty() and (cached["source"] as WeakRef).get_ref() == original:
		return cached
	if original.get_surface_count() < 1:
		return {}
	var arrays := original.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var spec: Dictionary = head_info.get("body_cut", {}) as Dictionary
	var hidden_ids := PackedInt32Array()
	var method := "list"
	var reason := _list_problem(spec, body_scene, vertices, indices)
	if reason.is_empty():
		hidden_ids = _listed_triangles(spec)
	else:
		method = "geometric"
		hidden_ids = _geometric_triangles(vertices, indices, float(spec.get("travel", 0.075)),
			str(spec.get("rule", "")).contains("any corner"), body, skeleton)
		RLHeadLibrary.warn_once("cut:" + str(head_info.get("path", "")),
			"body cut falls back to the geometric rule (%s)" % reason)
	var hidden := {}
	var corner_use := {}
	for triangle: int in hidden_ids:
		var a := indices[triangle * 3]
		var b := indices[triangle * 3 + 1]
		var c := indices[triangle * 3 + 2]
		hidden[_triplet(a, b, c)] = true
	for triangle: int in range(indices.size() / 3):
		var kept := not hidden.has(_triplet(indices[triangle * 3], indices[triangle * 3 + 1],
			indices[triangle * 3 + 2]))
		for corner: int in 3:
			var vertex := indices[triangle * 3 + corner]
			corner_use[vertex] = bool(corner_use.get(vertex, false)) or kept
	# Vertices only hidden triangles use: a generated LOD triangle touching
	# one belongs to the removed head, whatever its own corners are.
	var hidden_vertices := {}
	for vertex: Variant in corner_use:
		if not bool(corner_use[vertex]):
			hidden_vertices[vertex] = true
	var plan := {"source": weakref(original), "hidden": hidden,
		"hidden_vertices": hidden_vertices, "method": method, "reason": reason}
	_plans[key] = plan
	return plan


## Why the authored list cannot be used on this mesh, or "" when it can.
static func _list_problem(spec: Dictionary, body_scene: String,
		vertices: PackedVector3Array, indices: PackedInt32Array) -> String:
	if spec.get("hiddenBodyTriangles") is not Array:
		return "no triangle list"
	var expected := str(spec.get("bodySHA256", ""))
	if not expected.is_empty() and FileAccess.file_exists(body_scene) \
			and FileAccess.get_sha256(body_scene) != expected:
		return "body file differs from the one the list was made for"
	var file := _body_primitive(body_scene)
	if file.is_empty():
		return "body file unreadable"
	var file_indices: PackedInt32Array = file["indices"]
	var file_positions: PackedVector3Array = file["positions"]
	if file_indices.size() != indices.size():
		return "triangle count differs (%d in the file, %d built)" % [
			file_indices.size() / 3, indices.size() / 3]
	for triangle: int in _listed_triangles(spec):
		if triangle * 3 + 2 >= indices.size():
			return "list names a triangle past the end"
		for corner: int in 3:
			var wanted := file_positions[file_indices[triangle * 3 + corner]]
			var found := false
			for other: int in 3:
				if vertices[indices[triangle * 3 + other]].distance_to(wanted) <= POSITION_TOLERANCE:
					found = true
					break
			if not found:
				return "triangle %d is not where the file puts it" % triangle
	return ""


static func _listed_triangles(spec: Dictionary) -> PackedInt32Array:
	var result := PackedInt32Array()
	for run: Variant in spec.get("hiddenBodyTriangles", []) as Array:
		if run is Array and (run as Array).size() >= 2:
			var start := int((run as Array)[0])
			for offset: int in int((run as Array)[1]):
				result.append(start + offset)
	return result


static func _geometric_triangles(vertices: PackedVector3Array, indices: PackedInt32Array,
		travel: float, any_corner: bool, body: MeshInstance3D, skeleton: Skeleton3D) -> PackedInt32Array:
	var result := PackedInt32Array()
	if skeleton == null or skeleton.find_bone("Head") < 0 or skeleton.find_bone("neck_01") < 0:
		return result
	var head := skeleton.get_bone_global_rest(skeleton.find_bone("Head")).origin
	var neck := skeleton.get_bone_global_rest(skeleton.find_bone("neck_01")).origin
	var direction := (head - neck).normalized()
	var origin := neck + direction * travel
	var to_rig := Transform3D.IDENTITY
	if body.is_inside_tree() and skeleton.is_inside_tree():
		to_rig = skeleton.global_transform.affine_inverse() * body.global_transform
	for triangle: int in range(indices.size() / 3):
		var above := 0
		for corner: int in 3:
			if (to_rig * vertices[indices[triangle * 3 + corner]] - origin).dot(direction) > 0.0:
				above += 1
		if above == 3 or (any_corner and above > 0):
			result.append(triangle)
	return result


## The body node's first primitive as the file stores it: positions and
## indices, read straight from the GLB's binary chunk.
static func _body_primitive(path: String) -> Dictionary:
	var document := RLHeadLibrary.glb_document(path)
	var nodes: Array = document.get("nodes", []) as Array
	var mesh_index := -1
	for node: Variant in nodes:
		if node is Dictionary and str((node as Dictionary).get("name", "")) == "body":
			mesh_index = int((node as Dictionary).get("mesh", -1))
			break
	var meshes: Array = document.get("meshes", []) as Array
	if mesh_index < 0 or mesh_index >= meshes.size():
		return {}
	var primitive: Dictionary = (((meshes[mesh_index] as Dictionary).get("primitives", []) as Array)[0]) as Dictionary
	var binary := _glb_binary(path)
	if binary.is_empty():
		return {}
	var positions := _accessor_vec3(document, binary, int((primitive["attributes"] as Dictionary)["POSITION"]))
	var indices := _accessor_indices(document, binary, int(primitive.get("indices", -1)))
	if positions.is_empty() or indices.is_empty():
		return {}
	return {"positions": positions, "indices": indices}


static func _glb_binary(path: String) -> PackedByteArray:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() < 20:
		return PackedByteArray()
	file.seek(12)
	while file.get_position() + 8 <= file.get_length():
		var length := int(file.get_32())
		var kind := file.get_32()
		if kind == 0x004E4942:
			return file.get_buffer(length)
		file.seek(file.get_position() + length)
	return PackedByteArray()


static func _view_span(document: Dictionary, accessor: Dictionary, element: int) -> Array:
	var view: Dictionary = (document.get("bufferViews", []) as Array)[int(accessor["bufferView"])]
	var offset := int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
	var stride := int(view.get("byteStride", element))
	return [offset, stride]


static func _accessor_vec3(document: Dictionary, binary: PackedByteArray, index: int) -> PackedVector3Array:
	var result := PackedVector3Array()
	var accessors: Array = document.get("accessors", []) as Array
	if index < 0 or index >= accessors.size():
		return result
	var accessor: Dictionary = accessors[index]
	if int(accessor.get("componentType", 0)) != 5126 or str(accessor.get("type", "")) != "VEC3":
		return result
	var span := _view_span(document, accessor, 12)
	var count := int(accessor["count"])
	result.resize(count)
	for element: int in count:
		var at: int = int(span[0]) + element * int(span[1])
		result[element] = Vector3(binary.decode_float(at), binary.decode_float(at + 4),
			binary.decode_float(at + 8))
	return result


static func _accessor_indices(document: Dictionary, binary: PackedByteArray, index: int) -> PackedInt32Array:
	var result := PackedInt32Array()
	var accessors: Array = document.get("accessors", []) as Array
	if index < 0 or index >= accessors.size():
		return result
	var accessor: Dictionary = accessors[index]
	var component := int(accessor.get("componentType", 0))
	var width := {5121: 1, 5123: 2, 5125: 4}.get(component, 0) as int
	if width == 0:
		return result
	var span := _view_span(document, accessor, width)
	var count := int(accessor["count"])
	result.resize(count)
	for element: int in count:
		var at: int = int(span[0]) + element * int(span[1])
		result[element] = (binary.decode_u8(at) if width == 1 else binary.decode_u16(at)
			if width == 2 else binary.decode_u32(at))
	return result


static func _triplet(a: int, b: int, c: int) -> Vector3i:
	var low := mini(a, mini(b, c))
	var high := maxi(a, maxi(b, c))
	return Vector3i(low, a + b + c - low - high, high)


## The source with its hidden triangles taken out of every surface and LOD.
## Vertex arrays, blend shapes, skinning and materials are carried unchanged.
static func _cut(source: Mesh, plan: Dictionary) -> ArrayMesh:
	var hidden: Dictionary = plan["hidden"]
	var hidden_vertices: Dictionary = plan["hidden_vertices"]
	var result := ArrayMesh.new()
	for blend: int in source.get_blend_shape_count():
		result.add_blend_shape(source.get_blend_shape_name(blend))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var kept := PackedInt32Array()
		for index: int in range(0, indices.size(), 3):
			if not hidden.has(_triplet(indices[index], indices[index + 1], indices[index + 2])):
				kept.append_array(indices.slice(index, index + 3))
		if kept.is_empty():
			kept = PackedInt32Array([0, 0, 0])
		var lods: Dictionary = {}
		var source_lods := TorsoBodyCover._surface_lods(source, surface)
		for distance: Variant in source_lods:
			var lod_source: PackedInt32Array = source_lods[distance]
			var lod_kept := PackedInt32Array()
			for index: int in range(0, lod_source.size(), 3):
				var a := lod_source[index]
				var b := lod_source[index + 1]
				var c := lod_source[index + 2]
				if hidden.has(_triplet(a, b, c)) or hidden_vertices.has(a) \
						or hidden_vertices.has(b) or hidden_vertices.has(c):
					continue
				lod_kept.append_array(PackedInt32Array([a, b, c]))
			if not lod_kept.is_empty() and lod_kept.size() < kept.size():
				lods[distance] = lod_kept
		arrays[Mesh.ARRAY_INDEX] = kept
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays,
			source.surface_get_blend_shape_arrays(surface), lods,
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
	result.resource_name = source.resource_name + " (RL head cut)"
	return result


static func _evict_stale() -> void:
	for key: Variant in _cuts.keys():
		if (_cuts[key]["source"] as WeakRef).get_ref() == null:
			_cuts.erase(key)
	for key: Variant in _plans.keys():
		if (_plans[key]["source"] as WeakRef).get_ref() == null:
			_plans.erase(key)

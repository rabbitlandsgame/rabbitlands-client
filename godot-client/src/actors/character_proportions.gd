class_name CharacterProportions
extends RefCounted
## Cosmetic body scale lives on the complete visual hierarchy: body, rig,
## garments, sockets, hair and cloth receive the same affine transform. No
## gameplay dimensions or authored meshes on disk are changed.
const CACHE_LIMIT := 12
const SOURCE_META := &"portrait_face_source"
const RESULT_META := &"portrait_face_result"
const LODS := preload("res://src/actors/wardrobe_shirt_fit.gd")
static var _meshes: Dictionary = {}

static func value(appearance: Dictionary, key: String) -> float:
	var raw: Variant = appearance.get(key, 50)
	if raw is not int and raw is not float:
		return 50.0
	var number := float(raw)
	return clampf(number, 0.0, 100.0) if is_finite(number) else 50.0

static func visual_scale(appearance: Dictionary) -> Vector3:
	var height := lerpf(0.90, 1.10, value(appearance, "height") / 100.0)
	var breadth := lerpf(0.85, 1.15, value(appearance, "build") / 100.0)
	return Vector3(breadth, height, breadth)

static func clear() -> void:
	_meshes.clear()

## Restore before body-cover filtering, so neither that cache nor this one
## ever treats a previous face shape as its authored source.
static func restore(root: Node3D) -> void:
	if root == null:
		return
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if instance.has_meta(RESULT_META) and instance.mesh == instance.get_meta(RESULT_META):
			instance.mesh = instance.get_meta(SOURCE_META) as Mesh
		instance.remove_meta(SOURCE_META)
		instance.remove_meta(RESULT_META)

static func apply(root: Node3D, skeleton: Skeleton3D, appearance: Dictionary) -> void:
	if root == null or skeleton == null:
		return
	var shape := Vector3((value(appearance, "jaw") - 50.0) / 50.0,
		(value(appearance, "cheekbones") - 50.0) / 50.0,
		(value(appearance, "nose") - 50.0) / 50.0)
	if shape.is_zero_approx():
		return
	var frame := face_frame(root, skeleton)
	if frame.is_empty():
		return
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		# The field fades to zero before eyes, ears, scalp and neckline. Only
		# skin geometry below the eyes needs a derived mesh; headwear keeps its
		# approved cap and perimeter instead of acquiring another fit variant.
		if instance.name.to_lower() not in ["body", "char1", "mesh_node"] or instance.mesh == null:
			continue
		var source := instance.mesh
		var to_head: Transform3D = frame.to_head * _to_root(skeleton, root).affine_inverse() * _to_root(instance, root)
		var key := "%s|%s|%s|%s|%s" % [source.get_instance_id(), shape, to_head, frame.eye_y, frame.scale]
		if not _meshes.has(key):
			if _meshes.size() >= CACHE_LIMIT:
				_meshes.erase(_meshes.keys()[0])
			_meshes[key] = fit(source, to_head, frame, shape)
		instance.set_meta(SOURCE_META, source)
		instance.mesh = _meshes[key] as Mesh
		instance.set_meta(RESULT_META, instance.mesh)

## Work in the shared visual root rather than cancelling world transforms.
## This keeps shape-cache identity independent of map position and avoids
## precision loss when a character stands far from the origin.
static func _to_root(node: Node3D, root: Node3D) -> Transform3D:
	var result := Transform3D.IDENTITY
	var current: Node = node
	while current != null and current != root:
		if current is Node3D:
			result = (current as Node3D).transform * result
		current = current.get_parent()
	return result

## Head-local reference from the actual eyes, using indexed vertices only.
## Raw glTF groups share an attribute array covering the entire body.
static func face_frame(root: Node3D, skeleton: Skeleton3D) -> Dictionary:
	var head := skeleton.find_bone("Head")
	if head < 0:
		return {}
	var to_head := skeleton.get_bone_global_rest(head).affine_inverse()
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	var found := false
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var eyes := node as MeshInstance3D
		if eyes.name.to_lower() != "eyes" or eyes.mesh == null:
			continue
		var transform := to_head * _to_root(skeleton, root).affine_inverse() * _to_root(eyes, root)
		for surface: int in range(eyes.mesh.get_surface_count()):
			var arrays := eyes.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var used := indices if not indices.is_empty() else PackedInt32Array(range(vertices.size()))
			for index: int in used:
				var point: Vector3 = transform * vertices[index]
				low = low.min(point)
				high = high.max(point)
				found = true
	if not found:
		return {}
	return {"to_head": to_head, "eye_y": (low.y + high.y) * 0.5,
		"eye_z": (low.z + high.z) * 0.5,
		"scale": clampf((high.x - low.x) / 0.10, 0.8, 1.4)}

## Smooth local sculpting field, confined to the front face. The maximum
## authored displacement is 12 mm at standard scale. The neck seam, eyelids,
## ears and skull perimeter remain exact, including at slider extremes.
static func face_point(point: Vector3, frame: Dictionary, shape: Vector3) -> Vector3:
	var size: float = frame.scale
	var y := (point.y - float(frame.eye_y)) / size
	var x := point.x / size
	var z := (point.z - float(frame.eye_z)) / size
	var front := smoothstep(-0.055, -0.005, z)
	var sides := 1.0 - smoothstep(0.055, 0.080, absf(x))
	var top := 1.0 - smoothstep(-0.015, 0.0, y)
	var bottom := smoothstep(-0.16, -0.12, y)
	var mask := front * sides * top * bottom
	if mask <= 0.0:
		return point
	var jaw := exp(-pow((y + 0.095) / 0.034, 2.0))
	var cheeks := exp(-pow((y + 0.035) / 0.023, 2.0))
	var centre := 1.0 - smoothstep(0.012, 0.028, absf(x))
	var nose := exp(-pow((y + 0.035) / 0.025, 2.0)) * centre
	var width := smoothstep(0.0, 0.035, absf(x))
	point.x += signf(x) * width * (0.012 * jaw * shape.x + 0.008 * cheeks * shape.y) * mask * size
	point.z += 0.010 * nose * shape.z * mask * size
	return point

static func fit(source: Mesh, to_head: Transform3D, frame: Dictionary, shape: Vector3) -> Mesh:
	var result := ArrayMesh.new()
	result.resource_name = source.resource_name + " Portrait Face"
	for blend: int in range(source.get_blend_shape_count()):
		result.add_blend_shape(source.get_blend_shape_name(blend))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	var from_head := to_head.affine_inverse()
	for surface: int in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface)
		var blends := source.surface_get_blend_shape_arrays(surface)
		var lods := LODS._surface_lods(source, surface)
		compact(arrays, blends, lods)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		var normal_to_head := to_head.basis.inverse().transposed()
		var normal_from_head := from_head.basis.inverse().transposed()
		for index: int in range(vertices.size()):
			var point := to_head * vertices[index]
			var moved := face_point(point, frame, shape)
			if moved.is_equal_approx(point):
				continue
			vertices[index] = from_head * moved
			# Transform the authored normal through the sculpt's Jacobian. This
			# retains the source's smooth/painted shading and UV seams.
			var epsilon := 0.0001
			var jacobian := Basis((face_point(point + Vector3.RIGHT * epsilon, frame, shape) - moved) / epsilon,
				(face_point(point + Vector3.UP * epsilon, frame, shape) - moved) / epsilon,
				(face_point(point + Vector3.BACK * epsilon, frame, shape) - moved) / epsilon)
			if normals.size() == vertices.size():
				normals[index] = (normal_from_head * jacobian.inverse().transposed() * normal_to_head * normals[index]).normalized()
			if tangents.size() == vertices.size() * 4:
				var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
				tangent = (from_head.basis * jacobian * to_head.basis * tangent).normalized()
				for component: int in range(3):
					tangents[index * 4 + component] = tangent[component]
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_NORMAL] = normals
		if not tangents.is_empty():
			arrays[Mesh.ARRAY_TANGENT] = tangents
		if not shape.is_zero_approx():
			_finish_face_normals(arrays, to_head, frame)
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays, blends, lods,
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result

## Reconcile shading with the sculpted front face. Area weighting replaces
## inconsistent imported seam normals while refusing opposite-facing mouth
## surfaces and preserving the authored neck, ears, eyelids and scalp.
## This runs only while constructing an existing custom-face derivative.
static func _finish_face_normals(arrays: Array, to_head: Transform3D, frame: Dictionary) -> void:
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if normals.size() != points.size() or indices.is_empty():
		return
	var geometric := PackedVector3Array()
	geometric.resize(points.size())
	for triangle: int in range(0, indices.size() - 2, 3):
		var a := indices[triangle]
		var b := indices[triangle + 1]
		var c := indices[triangle + 2]
		var face_normal := (points[b] - points[a]).cross(points[c] - points[a])
		if face_normal.dot(normals[a] + normals[b] + normals[c]) < 0.0:
			face_normal = -face_normal
		for index: int in [a, b, c]:
			geometric[index] += face_normal
	var normal_to_head := to_head.basis.inverse().transposed()
	var groups := {}
	var used := {}
	for index: int in indices:
		used[index] = true
	for index: int in used:
		var point := to_head * points[index]
		var normal := (normal_to_head * normals[index]).normalized()
		if point.y < frame.eye_y - 0.13 or point.y > frame.eye_y or absf(point.x) > 0.09 or point.z < frame.eye_z - 0.05 or normal.z < 0.15:
			continue
		var key := Vector3i(roundi(point.x * 100000.0), roundi(point.y * 100000.0), roundi(point.z * 100000.0))
		if not groups.has(key):
			groups[key] = []
		groups[key].append(index)
	var original := normals.duplicate()
	var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
	for group: Array in groups.values():
		for index: int in group:
			var sum := Vector3.ZERO
			for other: int in group:
				# Preserve a crease sharper than 75 degrees instead of averaging
				# a visible lip with the inner mouth at the same location.
				if original[index].dot(original[other]) > 0.258819:
					sum += geometric[other]
			if sum.is_zero_approx():
				continue
			var point := to_head * points[index]
			var blend := smoothstep(frame.eye_y - 0.13, frame.eye_y - 0.09, point.y) * (1.0 - smoothstep(frame.eye_y - 0.015, frame.eye_y, point.y))
			blend *= 1.0 - smoothstep(0.07, 0.09, absf(point.x))
			blend *= smoothstep(frame.eye_z - 0.05, frame.eye_z - 0.02, point.z)
			if blend <= 0.0:
				continue
			normals[index] = original[index].lerp(sum.normalized(), blend).normalized()
			if tangents.size() == points.size() * 4:
				var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
				tangent -= normals[index] * tangent.dot(normals[index])
				if tangent.is_zero_approx():
					tangent = normals[index].cross(Vector3.RIGHT if absf(normals[index].x) < 0.9 else Vector3.UP)
				tangent = tangent.normalized()
				for component: int in range(3):
					tangents[index * 4 + component] = tangent[component]
	arrays[Mesh.ARRAY_NORMAL] = normals
	if not tangents.is_empty():
		arrays[Mesh.ARRAY_TANGENT] = tangents

## Compact unused attribute slots before caching. All surface and LOD indices,
## blend arrays and four/eight skin influences retain their original meaning.
static func compact(arrays: Array, blends: Array, lods: Dictionary) -> void:
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if indices.is_empty():
		return
	var used := {}
	for index: int in indices:
		used[index] = true
	for chain: PackedInt32Array in lods.values():
		for index: int in chain:
			used[index] = true
	var order: Array = used.keys()
	order.sort()
	if order.size() == vertices.size():
		return
	var remap := PackedInt32Array()
	remap.resize(vertices.size())
	for index: int in range(order.size()):
		remap[int(order[index])] = index
	var groups: Array = [arrays]
	groups.append_array(blends)
	for group: Array in groups:
		for channel: int in range(Mesh.ARRAY_INDEX):
			if group[channel] == null or group[channel].is_empty():
				continue
			var original: Variant = group[channel]
			var stride: int = original.size() / vertices.size()
			var reduced: Variant = original.duplicate()
			reduced.resize(order.size() * stride)
			for index: int in range(order.size()):
				for component: int in range(stride):
					reduced[index * stride + component] = original[int(order[index]) * stride + component]
			group[channel] = reduced
	for index: int in range(indices.size()):
		indices[index] = remap[indices[index]]
	arrays[Mesh.ARRAY_INDEX] = indices
	for distance: Variant in lods:
		var chain: PackedInt32Array = lods[distance]
		for index: int in range(chain.size()):
			chain[index] = remap[chain[index]]
		lods[distance] = chain

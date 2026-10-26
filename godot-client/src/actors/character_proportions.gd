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
const BODY_CACHE_LIMIT := 64
const BODY_SOURCE_META := &"human_body_refinement_source"
const BODY_RESULT_META := &"human_body_refinement_result"
static var _body_meshes: Dictionary = {}
static var _body_unchanged: Dictionary = {}

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
	_body_meshes.clear()
	_body_unchanged.clear()

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

## The refinement is a shared continuous field, evaluated in the wearer's
## canonical rest space after equipment has acquired its final rebound Skin.
## It never edits a bone, a socket, a source Mesh or an equipment file.
static func restore_body_refinement(root: Node3D) -> void:
	if root == null:
		return
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if instance.has_meta(BODY_RESULT_META) and instance.mesh == instance.get_meta(BODY_RESULT_META):
			_swap_body_mesh(instance, instance.get_meta(BODY_SOURCE_META) as Mesh)
		instance.remove_meta(BODY_SOURCE_META)
		instance.remove_meta(BODY_RESULT_META)

static func apply_body_refinement(root: Node3D, skeleton: Skeleton3D, config: Dictionary) -> void:
	if root == null or skeleton == null or str(config.get("culture", "")) != "luminous" or str(config.get("bodyTemplate", "")) not in ["luminous_male", "luminous_female"]:
		return
	var frame := body_frame(skeleton, str(config.get("gender", "male")))
	if frame.is_empty():
		return
	var skeleton_to_root := _to_root(skeleton, root)
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if instance.mesh == null or instance.skin == null or instance.has_meta(&"occlusion_silhouette_clone") or instance.has_meta("portrait_groom") or _is_appearance_hair(instance, root):
			continue
		if instance.has_meta(BODY_RESULT_META) and instance.mesh == instance.get_meta(BODY_RESULT_META):
			continue
		var source := instance.mesh
		var to_rig := skeleton_to_root.affine_inverse() * _to_root(instance, root)
		var binding := body_binding(instance.skin, skeleton, to_rig)
		if binding.is_empty():
			continue
		var key := "%s|%s|%s" % [source.get_instance_id(), frame.sex, var_to_bytes([to_rig, binding.rests]).hex_encode()]
		if _body_unchanged.has(key):
			continue
		if not _body_meshes.has(key):
			var candidate := fit_body_mesh(source, binding, frame)
			if candidate == source:
				if _body_unchanged.size() >= BODY_CACHE_LIMIT:
					_body_unchanged.erase(_body_unchanged.keys()[0])
				_body_unchanged[key] = true
				continue
			if _body_meshes.size() >= BODY_CACHE_LIMIT:
				_body_meshes.erase(_body_meshes.keys()[0])
			_body_meshes[key] = candidate
		var fitted := _body_meshes[key] as Mesh
		instance.set_meta(BODY_SOURCE_META, source)
		_swap_body_mesh(instance, fitted)
		instance.set_meta(BODY_RESULT_META, fitted)

static func body_cache_metrics() -> Dictionary:
	var bytes := 0
	var refined := 0
	var packed := 0
	var seen := {}
	for mesh: Mesh in _body_meshes.values():
		if seen.has(mesh.get_instance_id()) or not mesh.resource_name.ends_with(" Human Body Refinement"):
			continue
		seen[mesh.get_instance_id()] = true
		refined += 1
		for surface: int in range(mesh.get_surface_count()):
			var stored: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
			for key: String in ["vertex_data", "attribute_data", "skin_data", "index_data", "blend_shape_data"]:
				var stream: Variant = stored.get(key)
				if stream is PackedByteArray:
					packed += stream.size()
			for lod: Dictionary in stored.get("lods", []):
				var indices: Variant = lod.get("index_data")
				if indices is PackedByteArray:
					packed += indices.size()
			var groups: Array = [mesh.surface_get_arrays(surface)]
			groups.append_array(mesh.surface_get_blend_shape_arrays(surface))
			for arrays: Array in groups:
				for channel: Variant in arrays:
					if channel != null:
						bytes += channel.to_byte_array().size()
	return {"entries": _body_meshes.size(), "unchanged_entries": _body_unchanged.size(), "refined_meshes": refined, "array_bytes": bytes, "packed_buffer_bytes": packed, "limit": BODY_CACHE_LIMIT}

static func _is_appearance_hair(node: Node, root: Node) -> bool:
	var current := node
	while current != null and current != root:
		if str(current.name).begins_with("AppearanceHair_"):
			return true
		current = current.get_parent()
	return false

static func _swap_body_mesh(instance: MeshInstance3D, mesh: Mesh) -> void:
	var values := {}
	if instance.mesh != null:
		for shape: int in range(instance.mesh.get_blend_shape_count()):
			values[instance.mesh.get_blend_shape_name(shape)] = instance.get_blend_shape_value(shape)
	instance.mesh = mesh
	for shape: int in range(mesh.get_blend_shape_count()):
		var name: StringName = mesh.get_blend_shape_name(shape)
		if values.has(name):
			instance.set_blend_shape_value(shape, values[name])

static func body_frame(skeleton: Skeleton3D, sex: String) -> Dictionary:
	var points := {}
	for name: String in ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "upperarm_l", "lowerarm_l", "hand_l", "middle_01_l", "upperarm_r", "lowerarm_r", "hand_r", "middle_01_r"]:
		var bone := skeleton.find_bone(name)
		if bone < 0:
			return {}
		points[name] = skeleton.get_bone_global_rest(bone).origin
	var anchors := {}
	for bone: int in range(skeleton.get_bone_count()):
		var point := skeleton.get_bone_global_rest(bone).origin
		var bucket := floori(point.x / 0.15)
		if not anchors.has(bucket):
			anchors[bucket] = []
		anchors[bucket].append(point)
	var limbs: Array[Dictionary] = []
	for side: String in ["l", "r"]:
		for part: int in range(3):
			var names: Array[String] = ["upperarm_", "lowerarm_", "hand_", "middle_01_"]
			var start: Vector3 = points[names[part] + side]
			var end: Vector3 = points[names[part + 1] + side]
			var span := end - start
			limbs.append({"start": start, "axis": span.normalized(), "inverse_length": 1.0 / span.length(), "length": span.length(), "part": part})
	return {"sex": sex, "points": points, "anchors": anchors, "neck_y": (points.neck_01 as Vector3).y, "chest_y": (points.spine_03 as Vector3).y, "waist_y": (points.spine_01 as Vector3).y + 0.07, "spine": [points.pelvis, points.spine_01, points.spine_02, points.spine_03, points.neck_01], "limbs": limbs}

## Exact identity near every named joint protects fingertips, the palm grip,
## elbows, shoulder pivots and cape-chain anchors. Radial shape changes taper
## between them; no arm, finger or body segment gets longer.
static func body_point(point: Vector3, frame: Dictionary) -> Vector3:
	var neck_y: float = frame.neck_y
	if point.y < 0.80 or point.y > neck_y + 0.24:
		return point
	var delta := Vector3.ZERO
	var torso := smoothstep(0.88, 1.03, point.y) * (1.0 - smoothstep(neck_y - 0.105, neck_y - 0.025, point.y))
	torso *= 1.0 - smoothstep(0.16, 0.27, absf(point.x))
	if torso > 0.0:
		var centre_z := 0.0
		var spine: Array = frame.spine
		for index: int in range(spine.size() - 1):
			var a: Vector3 = spine[index]
			var b: Vector3 = spine[index + 1]
			if point.y >= a.y and point.y <= b.y:
				centre_z = lerpf(a.z, b.z, (point.y - a.y) / maxf(b.y - a.y, 0.001))
				break
		torso *= 1.0 - smoothstep(0.23, 0.50, absf(point.z - centre_z))
		var chest := exp(-pow((point.y - float(frame.chest_y)) / 0.13, 2.0))
		var waist := exp(-pow((point.y - float(frame.waist_y)) / 0.09, 2.0))
		var male: bool = frame.sex == "male"
		var wide := (0.025 if male else 0.016) * chest - (0.030 if male else 0.016) * waist
		var deep := (0.035 if male else 0.022) * chest - (0.022 if male else 0.012) * waist
		delta += Vector3(point.x * wide, 0, (point.z - centre_z) * deep) * torso
	for limb: Dictionary in frame.limbs:
		delta += _limb_delta(point, limb)
	if delta.length_squared() < 0.000000000001:
		return point
	var keep := 1.0
	var bucket := floori(point.x / 0.15)
	for offset: int in range(-1, 2):
		for anchor: Vector3 in frame.anchors.get(bucket + offset, []):
			var distance_squared := point.distance_squared_to(anchor)
			if distance_squared < 0.0004:
				keep = minf(keep, smoothstep(0.000016, 0.0004, distance_squared))
	return point + delta * keep

static func _limb_delta(point: Vector3, limb: Dictionary) -> Vector3:
	var start: Vector3 = limb.start
	var axis: Vector3 = limb.axis
	var along: float = (point - start).dot(axis) * float(limb.inverse_length)
	if along <= 0.0 or along >= 1.0:
		return Vector3.ZERO
	var radial := point - (start + axis * (float(limb.length) * along))
	var radius := radial.length()
	var part: int = limb.part
	var support := 1.0 - smoothstep(0.09 if part != 2 else 0.055, 0.18 if part != 2 else 0.10, radius)
	support *= smoothstep(0.0, 0.12, along) * (1.0 - smoothstep(0.88, 1.0, along))
	var amount := 0.0
	if part == 0:
		amount = 0.027 * exp(-pow((along - 0.34) / 0.25, 2.0)) - 0.018 * exp(-pow((along - 0.80) / 0.15, 2.0))
	elif part == 1:
		amount = 0.018 * exp(-pow((along - 0.25) / 0.22, 2.0)) - 0.035 * exp(-pow((along - 0.78) / 0.17, 2.0))
	else:
		amount = -0.028 * pow(sin(PI * along), 2.0)
	return radial * amount * support

static func _body_jacobian(point: Vector3, moved: Vector3, frame: Dictionary) -> Basis:
	var epsilon := 0.0001
	return Basis((body_point(point + Vector3.RIGHT * epsilon, frame) - moved) / epsilon,
		(body_point(point + Vector3.UP * epsilon, frame) - moved) / epsilon,
		(body_point(point + Vector3.BACK * epsilon, frame) - moved) / epsilon)

## At rest, the final garment map is to_rig * sum(weight * rest * bind).
## Inverting that SAME map writes the shared field back into the garment's
## authored coordinates, including assets with different bone-space fitting.
static func body_binding(skin: Skin, skeleton: Skeleton3D, to_rig: Transform3D) -> Dictionary:
	var rests: Array[Transform3D] = []
	for bind: int in range(skin.get_bind_count()):
		var bone := skeleton.find_bone(skin.get_bind_name(bind))
		if bone < 0:
			bone = skin.get_bind_bone(bind)
		if bone < 0 or bone >= skeleton.get_bone_count():
			return {}
		rests.append(skeleton.get_bone_global_rest(bone) * skin.get_bind_pose(bind))
	if rests.is_empty():
		return {}
	var common := true
	for rest: Transform3D in rests:
		if not rest.is_equal_approx(rests[0]):
			common = false
			break
	var constant := to_rig * rests[0]
	return {"rests": rests, "to_rig": to_rig, "common": common, "constant": constant, "inverse": constant.affine_inverse(), "normal_to_rig": constant.basis.inverse().transposed()}

static func _body_vertex_map(arrays: Array, index: int, binding: Dictionary) -> Transform3D:
	if binding.common:
		return binding.constant
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var stride := bones.size() / maxi(vertices.size(), 1)
	var x := Vector3.ZERO
	var y := Vector3.ZERO
	var z := Vector3.ZERO
	var origin := Vector3.ZERO
	for influence: int in range(stride):
		var at := index * stride + influence
		if weights[at] <= 0.0:
			continue
		var rest: Transform3D = binding.rests[bones[at]]
		x += rest.basis.x * weights[at]
		y += rest.basis.y * weights[at]
		z += rest.basis.z * weights[at]
		origin += rest.origin * weights[at]
	return binding.to_rig * Transform3D(Basis(x, y, z), origin)

static func _body_target(point: Vector3, normal: Vector3, tangent: Vector3,
		map: Transform3D, frame: Dictionary, binding: Dictionary, samples: Dictionary) -> Array:
	var rest_point := map * point
	# Authored UV/material seams and generated backings repeat corner positions.
	# Reuse the field and Jacobian at micrometre-equivalent rest positions;
	# normals/tangents still transform independently for every corner.
	var key := Vector3i(roundi(rest_point.x * 1000000.0), roundi(rest_point.y * 1000000.0), roundi(rest_point.z * 1000000.0))
	var sample: Array = samples.get(key, [])
	if sample.is_empty():
		var moved := body_point(rest_point, frame)
		var changed := moved != rest_point
		var jacobian := _body_jacobian(rest_point, moved, frame) if changed else Basis.IDENTITY
		sample = [moved - rest_point, jacobian, jacobian.inverse().transposed(), changed]
		if changed and binding.common:
			var common_inverse: Transform3D = binding.inverse
			var common_normal: Basis = binding.normal_to_rig
			sample.append(common_inverse.basis * (sample[0] as Vector3))
			sample.append(map.basis.transposed() * (sample[2] as Basis) * common_normal)
			sample.append(common_inverse.basis * jacobian * map.basis)
		samples[key] = sample
	if not bool(sample[3]):
		return [point, normal, tangent, false]
	if binding.common:
		var next_normal := ((sample[5] as Basis) * normal).normalized()
		var next_tangent := ((sample[6] as Basis) * tangent).normalized() if not tangent.is_zero_approx() else tangent
		if not next_tangent.is_zero_approx():
			next_tangent = (next_tangent - next_normal * next_tangent.dot(next_normal)).normalized()
		return [point + (sample[4] as Vector3), next_normal, next_tangent, true]
	var jacobian: Basis = sample[1]
	var inverse: Transform3D = binding.inverse if binding.common else map.affine_inverse()
	var normal_to_rig: Basis = binding.normal_to_rig if binding.common else map.basis.inverse().transposed()
	var next_normal := (map.basis.transposed() * (sample[2] as Basis) * normal_to_rig * normal).normalized()
	var next_tangent := (inverse.basis * jacobian * map.basis * tangent).normalized() if not tangent.is_zero_approx() else tangent
	if not next_tangent.is_zero_approx():
		next_tangent = (next_tangent - next_normal * next_tangent.dot(next_normal)).normalized()
	return [inverse * (rest_point + (sample[0] as Vector3)), next_normal, next_tangent, true]

static func fit_body_mesh(source: Mesh, binding: Dictionary, frame: Dictionary) -> Mesh:
	var result := ArrayMesh.new()
	result.resource_name = source.resource_name + " Human Body Refinement"
	for shape: int in range(source.get_blend_shape_count()):
		result.add_blend_shape(source.get_blend_shape_name(shape))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	var any_moved := false
	var samples := {}
	for surface: int in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface)
		var shapes := source.surface_get_blend_shape_arrays(surface)
		var lods := LODS._surface_lods(source, surface)
		compact(arrays, shapes, lods)
		var original := arrays.duplicate(true)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		for index: int in range(points.size()):
			var map := _body_vertex_map(original, index, binding)
			if absf(map.basis.determinant()) < 0.000001:
				continue
			var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2]) if tangents.size() == points.size() * 4 else Vector3.ZERO
			var next := _body_target(points[index], normals[index], tangent, map, frame, binding, samples)
			points[index] = next[0]
			normals[index] = next[1]
			any_moved = any_moved or bool(next[3])
			if tangents.size() == points.size() * 4:
				for component: int in range(3):
					tangents[index * 4 + component] = (next[2] as Vector3)[component]
			# Normalized morph arrays carry complete positions; relative arrays
			# carry deltas. Preserve that representation after the same field.
			for shape_arrays: Array in shapes:
				var shape_points: PackedVector3Array = shape_arrays[Mesh.ARRAY_VERTEX]
				if shape_points.size() != points.size():
					continue
				var shape_normals: PackedVector3Array = shape_arrays[Mesh.ARRAY_NORMAL] if shape_arrays[Mesh.ARRAY_NORMAL] != null else PackedVector3Array()
				var relative := result.blend_shape_mode == Mesh.BLEND_SHAPE_MODE_RELATIVE
				var shape_point: Vector3 = shape_points[index] + (original[Mesh.ARRAY_VERTEX][index] if relative else Vector3.ZERO)
				var shape_normal: Vector3 = (shape_normals[index] + original[Mesh.ARRAY_NORMAL][index]).normalized() if relative and shape_normals.size() == points.size() else (shape_normals[index] if shape_normals.size() == points.size() else original[Mesh.ARRAY_NORMAL][index])
				var shape_tangents: PackedFloat32Array = shape_arrays[Mesh.ARRAY_TANGENT] if shape_arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
				var shape_tangent := Vector3.ZERO
				if shape_tangents.size() == points.size() * 4:
					shape_tangent = Vector3(shape_tangents[index * 4], shape_tangents[index * 4 + 1], shape_tangents[index * 4 + 2])
					if relative:
						var authored_tangents: PackedFloat32Array = original[Mesh.ARRAY_TANGENT]
						shape_tangent += Vector3(authored_tangents[index * 4], authored_tangents[index * 4 + 1], authored_tangents[index * 4 + 2])
				var shape_next := _body_target(shape_point, shape_normal, shape_tangent, map, frame, binding, samples)
				shape_points[index] = (shape_next[0] as Vector3) - (points[index] if relative else Vector3.ZERO)
				shape_arrays[Mesh.ARRAY_VERTEX] = shape_points
				if shape_normals.size() == points.size():
					shape_normals[index] = (shape_next[1] as Vector3) - (normals[index] if relative else Vector3.ZERO)
					shape_arrays[Mesh.ARRAY_NORMAL] = shape_normals
				if shape_tangents.size() == points.size() * 4:
					var shape_next_tangent: Vector3 = shape_next[2]
					if relative:
						shape_next_tangent -= Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
					for component: int in range(3):
						shape_tangents[index * 4 + component] = shape_next_tangent[component]
					shape_arrays[Mesh.ARRAY_TANGENT] = shape_tangents
				any_moved = any_moved or bool(shape_next[3])
		arrays[Mesh.ARRAY_VERTEX] = points
		arrays[Mesh.ARRAY_NORMAL] = normals
		if not tangents.is_empty():
			arrays[Mesh.ARRAY_TANGENT] = tangents
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays, shapes, lods,
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result if any_moved else source

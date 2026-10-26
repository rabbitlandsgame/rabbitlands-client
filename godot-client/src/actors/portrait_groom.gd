class_name PortraitGroom
extends RefCounted
## Once-on-change grooming of imported geometry. No rest pose, animation,
## equipment asset or source Mesh is modified. Bounded caches share derivatives.

const HAIR_SHADER := preload("res://src/actors/portrait_hair.gdshader")
const BEARD_SHADER := preload("res://src/actors/portrait_beard.gdshader")
const HAIR_CACHE_LIMIT := 40
const BEARD_CACHE_LIMIT := 32
const SOURCE_META := "portrait_groom_source"
static var _hair_meshes: Dictionary = {}
static var _beard_meshes: Dictionary = {}
static var _hair_materials: Dictionary = {}
static var _beard_materials: Dictionary = {}
static var _beard_base_material: ShaderMaterial

static func clear() -> void:
	_hair_meshes.clear()
	_beard_meshes.clear()
	_hair_materials.clear()
	_beard_materials.clear()
	_beard_base_material = null

static func cache_metrics() -> Dictionary:
	var bytes := 0
	for cache: Dictionary in [_hair_meshes, _beard_meshes]:
		for mesh: Mesh in cache.values():
			for surface: int in mesh.get_surface_count():
				for attribute: Variant in mesh.surface_get_arrays(surface):
					if attribute != null:
						bytes += attribute.to_byte_array().size()
	return {"hair_meshes": _hair_meshes.size(), "beard_meshes": _beard_meshes.size(), "array_bytes": bytes}

static func apply(native_root: Node3D, skeleton: Skeleton3D,
		appearance: Dictionary, model_config: Dictionary) -> void:
	if not is_instance_valid(native_root) or not is_instance_valid(skeleton):
		return
	# The first art pass is deliberately scoped to the two Human source bodies.
	if str(model_config.get("culture", "")) != "luminous" or str(model_config.get("bodyTemplate", "")) not in ["luminous_male", "luminous_female"]:
		return
	var head := skeleton.find_bone("Head")
	if head < 0:
		return
	var frame := skeleton.get_bone_global_rest(head)
	var body := native_root.find_child("body", true, false) as MeshInstance3D
	if body == null or body.mesh == null:
		return
	var eyes := native_root.find_child("eyes", true, false) as MeshInstance3D
	var eye_height := _eye_height(eyes, skeleton, frame, native_root)
	var color := AppearanceVariants.hair_color(int(appearance.get("hair", 0)))
	var detail := clampi(int(appearance.get("hair_detail", 0)), 0, 2)
	var updo := str(model_config.get("gender", "")) == "female" and AppearanceVariants.hair_style(int(appearance.get("hair", 0))) == 3
	for node: Node in native_root.find_children("*", "MeshInstance3D", true, false):
		var hair := node as MeshInstance3D
		if hair.get_parent() != null and str(hair.get_parent().name).begins_with("AppearanceHair_"):
			_groom_hair(hair, skeleton, frame, eye_height, detail, color, native_root, updo)
	var old := native_root.get_node_or_null("PortraitFacialHair")
	if old != null:
		native_root.remove_child(old)
		old.queue_free()
	var style := clampi(int(appearance.get("facial_hair", 0)), 0, 5)
	if style == 0:
		return
	var transform := _to_root(skeleton, native_root).affine_inverse() * _to_root(body, native_root)
	var key := "%d:%d:%s" % [body.mesh.get_instance_id(), style, transform]
	var beard_mesh := _beard_meshes.get(key) as ArrayMesh
	if beard_mesh == null:
		beard_mesh = _build_beard(body.mesh, transform, frame, eye_height, style)
		if beard_mesh.get_surface_count() == 0:
			return
		_cache(_beard_meshes, key, beard_mesh, BEARD_CACHE_LIMIT)
	var beard := MeshInstance3D.new()
	beard.name = "PortraitFacialHair"
	var material_key := "%s:%d:%.5f" % [color.to_html(), style, eye_height]
	var material := _beard_materials.get(material_key) as ShaderMaterial
	if material == null:
		material = ShaderMaterial.new()
		material.shader = BEARD_SHADER
		material.set_shader_parameter("hair_color", color)
		material.set_shader_parameter("density", 0.25 if style == 1 else 1.0)
		material.set_shader_parameter("eye_height", eye_height)
		material.set_shader_parameter("style", style)
		_cache(_beard_materials, material_key, material, 128)
	beard.material_override = material
	beard.mesh = beard_mesh
	beard.skin = body.skin
	beard.layers = body.layers
	beard.cast_shadow = body.cast_shadow
	beard.extra_cull_margin = 0.04
	beard.set_meta("portrait_groom", true)
	beard.set_meta("uncovered_head_visible", true)
	native_root.add_child(beard)
	beard.transform = _to_root(body, native_root)
	beard.skeleton = beard.get_path_to(skeleton)

static func _eye_height(eyes: MeshInstance3D, skeleton: Skeleton3D,
		frame: Transform3D, native_root: Node3D) -> float:
	if eyes == null or eyes.mesh == null:
		return 0.075
	var to_head := frame.affine_inverse() * _to_root(skeleton, native_root).affine_inverse() * _to_root(eyes, native_root)
	var total := 0.0
	var count := 0
	for surface: int in eyes.mesh.get_surface_count():
		var arrays := eyes.mesh.surface_get_arrays(surface)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for index: int in indices:
			total += (to_head * points[index]).y
			count += 1
	return total / float(count) if count > 0 else 0.075

static func _groom_hair(hair: MeshInstance3D, skeleton: Skeleton3D,
		frame: Transform3D, eye_height: float, detail: int, color: Color, native_root: Node3D, updo: bool) -> void:
	if hair.mesh == null:
		return
	if not hair.has_meta(SOURCE_META):
		hair.set_meta(SOURCE_META, hair.mesh)
	var source := hair.get_meta(SOURCE_META) as Mesh
	# The production actor's tint pass installs a whole-instance override.
	# Grooming owns the material on each imported surface from here onward.
	hair.material_override = null
	if detail == 0:
		hair.mesh = source
		for surface: int in source.get_surface_count():
			var original := source.surface_get_material(surface) as StandardMaterial3D
			if original != null:
				var tinted := original.duplicate() as StandardMaterial3D
				tinted.albedo_color = original.albedo_color * color
				hair.set_surface_override_material(surface, tinted)
		return
	var to_head := frame.affine_inverse() * _to_root(skeleton, native_root).affine_inverse() * _to_root(hair, native_root)
	var from_head := to_head.affine_inverse()
	var key := "%d:%d:%s" % [source.get_instance_id(), detail, to_head]
	var groomed := _hair_meshes.get(key) as ArrayMesh
	if groomed == null:
		groomed = ArrayMesh.new()
		for surface: int in source.get_surface_count():
			var arrays := source.surface_get_arrays(surface).duplicate(true)
			var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
			var buns := _bun_groups(arrays, to_head) if updo and detail == 2 else {}
			var normal_to_head := to_head.basis.inverse().transposed()
			var normal_from_head := from_head.basis.inverse().transposed()
			for index: int in positions.size():
				var local := to_head * positions[index]
				var moved := _hair_point(local, eye_height, detail)
				var bun := int(buns.vertices[index]) if not buns.is_empty() else 0
				if bun > 0:
					moved = _bun_point(local, bun, buns.centres[bun])
				positions[index] = from_head * moved
				var epsilon := 0.0001
				var jacobian := Basis((_hair_point(local + Vector3.RIGHT * epsilon, eye_height, detail) - moved) / epsilon,
					(_hair_point(local + Vector3.UP * epsilon, eye_height, detail) - moved) / epsilon,
					(_hair_point(local + Vector3.BACK * epsilon, eye_height, detail) - moved) / epsilon)
				if bun > 0:
					jacobian = Basis.from_scale(Vector3(0.82, 0.90, 0.82) if bun == 1 else Vector3(0.64, 0.75, 0.70))
				if normals.size() == positions.size():
					normals[index] = (normal_from_head * jacobian.inverse().transposed() * normal_to_head * normals[index]).normalized()
				if tangents.size() == positions.size() * 4:
					var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
					tangent = (from_head.basis * jacobian * to_head.basis * tangent).normalized()
					for component: int in 3:
						tangents[index * 4 + component] = tangent[component]
			arrays[Mesh.ARRAY_VERTEX] = positions
			arrays[Mesh.ARRAY_NORMAL] = normals
			if not tangents.is_empty():
				arrays[Mesh.ARRAY_TANGENT] = tangents
			# Imported UV/skin arrays and LODs remain intact. Smooth sculpting
			# transforms the authored shading frame without changing binding.
			groomed.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays,
				[], _lods(source, surface), source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
			groomed.surface_set_material(surface, source.surface_get_material(surface))
		_cache(_hair_meshes, key, groomed, HAIR_CACHE_LIMIT)
	hair.mesh = groomed
	for surface: int in source.get_surface_count():
		var original := source.surface_get_material(surface) as StandardMaterial3D
		if original == null:
			continue
		var material_key := "%d:%s" % [original.get_instance_id(), color.to_html()]
		var material := _hair_materials.get(material_key) as ShaderMaterial
		if material == null:
			material = ShaderMaterial.new()
			material.shader = HAIR_SHADER
			if original.albedo_texture != null:
				material.set_shader_parameter("base_texture", original.albedo_texture)
			material.set_shader_parameter("use_texture", original.albedo_texture != null)
			material.set_shader_parameter("hair_color", color * original.albedo_color)
			if original.normal_texture != null:
				material.set_shader_parameter("normal_texture", original.normal_texture)
			material.set_shader_parameter("use_normal", original.normal_enabled and original.normal_texture != null)
			material.set_shader_parameter("normal_scale", minf(original.normal_scale, 0.8))
			_cache(_hair_materials, material_key, material, 128)
		hair.set_surface_override_material(surface, material)

static func _hair_point(point: Vector3, eye_height: float, detail: int) -> Vector3:
	var crown := smoothstep(eye_height - 0.005, eye_height + 0.07, point.y)
	var fringe := smoothstep(-0.01, 0.065, point.z) * crown
	if detail == 1:
		var lock := 0.5 + 0.5 * sin(point.x * 125.0 + point.z * 78.0)
		var offset := Vector3(sin(point.z * 63.0 + point.x * 31.0) * 0.004,
			0.004 + lock * 0.012, sin(point.x * 107.0) * 0.004) * crown
		offset.y -= fringe * (0.004 + 0.010 * pow(sin(point.x * 120.0 + 0.8), 2.0))
		offset.x += sin(point.y * 44.0) * 0.004 * fringe
		return point + offset
	return point + Vector3(0.012 * fringe, 0.005 * crown, -0.008 * fringe)

static func _build_beard(source: Mesh, mesh_to_skeleton: Transform3D,
		frame: Transform3D, eye_height: float, style: int) -> ArrayMesh:
	var result := ArrayMesh.new()
	var to_head := frame.affine_inverse() * mesh_to_skeleton
	var from_head := to_head.affine_inverse()
	# Each retained triangle and all skin influences come from the imported
	# lower face. Geometry is fitted after face sculpting, including other races.
	for surface: int in source.get_surface_count():
		var input := source.surface_get_arrays(surface)
		var points: PackedVector3Array = input[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = input[Mesh.ARRAY_NORMAL]
		var indices: PackedInt32Array = input[Mesh.ARRAY_INDEX]
		var selected := PackedInt32Array()
		var coverage := PackedFloat32Array()
		coverage.resize(points.size())
		for index: int in points.size():
			coverage[index] = _beard_coverage(to_head * points[index], eye_height, style)
		for triangle: int in range(0, indices.size() - 2, 3):
			if maxf(coverage[indices[triangle]], maxf(coverage[indices[triangle + 1]], coverage[indices[triangle + 2]])) > 0.15:
				selected.append_array(indices.slice(triangle, triangle + 3))
		if selected.is_empty():
			continue
		# Refine only the retained imported lower-face patch. The original
		# source stays unchanged; all UV-independent attributes and full skin
		# influences interpolate over its existing triangles.
		var refined := _subdivide_patch(input, selected)
		points = refined.points
		normals = refined.normals
		selected = refined.indices
		input[Mesh.ARRAY_BONES] = refined.bones
		input[Mesh.ARRAY_WEIGHTS] = refined.weights
		coverage.resize(points.size())
		for index: int in points.size():
			coverage[index] = _beard_coverage(to_head * points[index], eye_height, style)
		var remap: Dictionary = {}
		var vertex := PackedVector3Array()
		var normal := PackedVector3Array()
		var uv := PackedVector2Array()
		var colors := PackedColorArray()
		var bones := PackedInt32Array()
		var weights := PackedFloat32Array()
		var mapped := PackedInt32Array()
		var influences := 0
		if input[Mesh.ARRAY_BONES] != null:
			influences = (input[Mesh.ARRAY_BONES] as PackedInt32Array).size() / points.size()
		for source_index: int in selected:
			if not remap.has(source_index):
				remap[source_index] = vertex.size()
				var local := to_head * points[source_index]
				var original_local := local
				var direction := (to_head.basis * normals[source_index]).normalized()
				var lower := 1.0 - smoothstep(eye_height - 0.095, eye_height - 0.045, local.y)
				var length: float = [0.0, 0.0011, 0.0035, 0.005, 0.007, 0.014][style]
				var amount := coverage[source_index]
				local += direction * (0.0008 + length * amount * (0.35 + 0.65 * lower))
				if style in [3, 4, 5]:
					local.y -= lower * length * amount * 0.65
					local.x *= 1.0 - lower * amount * (0.08 if style == 5 else 0.03)
				vertex.append(from_head * local)
				normal.append(normals[source_index])
				uv.append(Vector2(original_local.x, original_local.y))
				colors.append(Color(amount, maxf(original_local.z, 0.0), 0, 1))
				for influence: int in influences:
					bones.append(input[Mesh.ARRAY_BONES][source_index * influences + influence])
					weights.append(input[Mesh.ARRAY_WEIGHTS][source_index * influences + influence])
			mapped.append(int(remap[source_index]))
		var arrays: Array = []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertex
		arrays[Mesh.ARRAY_NORMAL] = normal
		arrays[Mesh.ARRAY_TEX_UV] = uv
		arrays[Mesh.ARRAY_COLOR] = colors
		arrays[Mesh.ARRAY_INDEX] = mapped
		if influences > 0:
			arrays[Mesh.ARRAY_BONES] = bones
			arrays[Mesh.ARRAY_WEIGHTS] = weights
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {},
			Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS if influences == 8 else 0)
		if _beard_base_material == null:
			_beard_base_material = ShaderMaterial.new()
			_beard_base_material.shader = BEARD_SHADER
		result.surface_set_material(result.get_surface_count() - 1, _beard_base_material)
	return result

static func _beard_coverage(point: Vector3, eye_height: float, style: int) -> float:
	var y := point.y - eye_height
	var x := absf(point.x)
	var front := smoothstep(-0.012, 0.014, point.z)
	var edge := 1.0 - smoothstep(0.065, 0.085, x)
	var bottom := smoothstep(-0.123, -0.100, y)
	var cheek_top := -0.060 + 0.028 * smoothstep(0.015, 0.060, x)
	var jaw := 1.0 - smoothstep(cheek_top - 0.005, cheek_top + 0.006, y)
	var mouth := sqrt(pow(point.x / 0.024, 2.0) + pow((y + 0.063) / 0.008, 2.0))
	var lips_clear := smoothstep(0.90, 1.25, mouth)
	var moustache := smoothstep(-0.066, -0.060, y) * (1.0 - smoothstep(-0.047, -0.040, y))
	moustache *= 1.0 - smoothstep(0.030, 0.046, x)
	var mask := maxf(jaw * lips_clear, moustache)
	if style == 2:
		mask = moustache
	elif style == 3:
		mask = maxf(jaw * lips_clear * (1.0 - smoothstep(0.026, 0.042, x)), moustache)
	return clampf(mask * front * edge * bottom, 0.0, 1.0)

static func _subdivide_patch(input: Array, selected: PackedInt32Array) -> Dictionary:
	var points: PackedVector3Array = input[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = input[Mesh.ARRAY_NORMAL]
	var bones: PackedInt32Array = input[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = input[Mesh.ARRAY_WEIGHTS]
	var influences := bones.size() / points.size()
	var edge_ids: Dictionary = {}
	var edges: Array[Vector2i] = []
	var indices := PackedInt32Array()
	for triangle: int in range(0, selected.size(), 3):
		var a := selected[triangle]
		var b := selected[triangle + 1]
		var c := selected[triangle + 2]
		var mid := PackedInt32Array()
		for pair: Vector2i in [Vector2i(a, b), Vector2i(b, c), Vector2i(c, a)]:
			var edge := Vector2i(mini(pair.x, pair.y), maxi(pair.x, pair.y))
			if not edge_ids.has(edge):
				edge_ids[edge] = points.size() + edges.size()
				edges.append(edge)
			mid.append(edge_ids[edge])
		indices.append_array(PackedInt32Array([a, mid[0], mid[2], mid[0], b, mid[1],
			mid[2], mid[1], c, mid[0], mid[1], mid[2]]))
	var original_size := points.size()
	points.resize(original_size + edges.size())
	normals.resize(points.size())
	bones.resize(points.size() * influences)
	weights.resize(bones.size())
	for edge_index: int in edges.size():
		var edge := edges[edge_index]
		var next := original_size + edge_index
		points[next] = (points[edge.x] + points[edge.y]) * 0.5
		normals[next] = (normals[edge.x] + normals[edge.y]).normalized()
		var combined: Dictionary = {}
		for source_index: int in [edge.x, edge.y]:
			for influence: int in influences:
				var offset := source_index * influences + influence
				var joint := bones[offset]
				combined[joint] = float(combined.get(joint, 0.0)) + weights[offset] * 0.5
		var joint_ids: Array = combined.keys()
		joint_ids.sort_custom(func(first: int, second: int) -> bool: return combined[first] > combined[second])
		var total := 0.0
		for slot: int in mini(influences, joint_ids.size()):
			total += float(combined[joint_ids[slot]])
		for slot: int in influences:
			var offset := next * influences + slot
			bones[offset] = int(joint_ids[slot]) if slot < joint_ids.size() else 0
			weights[offset] = float(combined[joint_ids[slot]]) / maxf(total, 0.00001) if slot < joint_ids.size() else 0.0
	return {"points": points, "normals": normals, "bones": bones, "weights": weights, "indices": indices}

static func _lods(source: Mesh, surface: int) -> Dictionary:
	return preload("res://src/actors/torso_body_cover.gd")._surface_lods(source, surface)

static func _cache(cache: Dictionary, key: String, value: Resource, limit: int) -> void:
	if cache.size() >= limit:
		cache.erase(cache.keys()[0])
	cache[key] = value

static func _to_root(node: Node3D, root: Node3D) -> Transform3D:
	var result := Transform3D.IDENTITY
	var cursor: Node = node
	while cursor != root and cursor != null:
		if cursor is Node3D:
			result = (cursor as Node3D).transform * result
		cursor = cursor.get_parent()
	return result

static func _bun_point(point: Vector3, bun: int, centre: Vector3) -> Vector3:
	# Both imported side coils overlap at the rear crown as one asymmetric
	# loose updo. Their connected cap and face-framing locks stay authored.
	var target := Vector3(-0.012, 0.218, -0.082) if bun == 1 else Vector3(0.015, 0.220, -0.105)
	var scale := Vector3(0.82, 0.90, 0.82) if bun == 1 else Vector3(0.64, 0.75, 0.70)
	return target + (point - centre) * scale

static func _bun_groups(arrays: Array, to_head: Transform3D) -> Dictionary:
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var parents := PackedInt32Array()
	parents.resize(points.size())
	var ranks := PackedByteArray()
	ranks.resize(points.size())
	var weld: Dictionary = {}
	for index: int in points.size():
		var key := Vector3i((points[index] * 100000.0).round())
		parents[index] = int(weld.get(key, index))
		weld[key] = parents[index]
	for triangle: int in range(0, indices.size(), 3):
		var first := _component_root(parents, indices[triangle])
		for corner: int in [1, 2]:
			var second := _component_root(parents, indices[triangle + corner])
			if first == second:
				continue
			if ranks[first] < ranks[second]:
				parents[first] = second
				first = second
			else:
				parents[second] = first
				if ranks[first] == ranks[second]:
					ranks[first] += 1
	var bounds: Dictionary = {}
	for index: int in points.size():
		var component := _component_root(parents, index)
		var point := to_head * points[index]
		var box: Dictionary = bounds.get(component, {"low": point, "high": point, "sum": Vector3.ZERO, "count": 0})
		box.low = (box.low as Vector3).min(point)
		box.high = (box.high as Vector3).max(point)
		box.sum += point
		box.count += 1
		bounds[component] = box
	var selected: Dictionary = {}
	var centres: Dictionary = {}
	for component: int in bounds:
		var box: Dictionary = bounds[component]
		if box.count < 500 or box.high.z > -0.035 or box.low.y < 0.075:
			continue
		var side := 1 if box.high.x < -0.055 else (2 if box.low.x > 0.055 else 0)
		if side > 0:
			selected[component] = side
			centres[side] = box.sum / float(box.count)
	var vertices := PackedByteArray()
	vertices.resize(points.size())
	for index: int in points.size():
		vertices[index] = int(selected.get(_component_root(parents, index), 0))
	return {"vertices": vertices, "centres": centres}

static func _component_root(parents: PackedInt32Array, index: int) -> int:
	while parents[index] != index:
		index = parents[index]
	return index

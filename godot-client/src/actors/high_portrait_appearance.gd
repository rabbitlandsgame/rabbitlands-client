class_name HighPortraitAppearance
extends RefCounted
## Optional Human portrait artwork. Low/Medium return before loading any High
## image or creating a derivative mesh. High refines only the front head;
## canonical skin bindings, UV1 and every lower-tier resource stay exact.
const HIGH := 2
const SHADER := preload("res://src/actors/high_portrait_appearance.gdshader")
const COMPACTOR := preload("res://src/actors/character_proportions.gd")
const LODS := preload("res://src/actors/wardrobe_shirt_fit.gd")
const META := &"rl_high_portrait"
const USER_META := &"rl_high_portrait_user"
const EXIT_META := &"rl_high_portrait_exit_hook"
const CACHE_LIMIT := 24
const CANONICAL_CACHE_LIMIT := 8
const PARTS := ["body", "eyes", "eyebrows", "scalp"]
const BEARD := "PortraitFacialHair"
static var _meshes: Dictionary = {}
static var _canonical_meshes: Dictionary = {}
static var _bundles: Dictionary = {}
static var _users: Dictionary = {}

static func apply(native_root: Node3D, skeleton: Skeleton3D,
		appearance: Dictionary, model_config: Dictionary, level: int) -> void:
	if not is_instance_valid(native_root):
		return
	if level != HIGH or not _supported(model_config) or not is_instance_valid(skeleton):
		if native_root.has_meta(USER_META):
			release(native_root)
		return
	restore(native_root)
	var sex := str(model_config.get("gender", ""))
	var bundle := _bundle(sex)
	if bundle.is_empty():
		release(native_root)
		return
	var head := skeleton.find_bone("Head")
	if head < 0:
		return
	_users[native_root.get_instance_id()] = weakref(native_root)
	native_root.set_meta(USER_META, sex)
	if not native_root.has_meta(EXIT_META):
		native_root.tree_exiting.connect(func() -> void: release(native_root), CONNECT_ONE_SHOT)
		native_root.set_meta(EXIT_META, true)
	var to_head := skeleton.get_bone_global_rest(head).affine_inverse() * _to_root(skeleton, native_root).affine_inverse()
	var projection: Dictionary = bundle.descriptor.projection
	var frame := COMPACTOR.face_frame(native_root, skeleton)
	var shape := Vector3((COMPACTOR.value(appearance, "jaw") - 50.0) / 50.0,
		(COMPACTOR.value(appearance, "cheekbones") - 50.0) / 50.0,
		(COMPACTOR.value(appearance, "nose") - 50.0) / 50.0)
	for part: String in PARTS + [BEARD]:
		var node := native_root.find_child(part, true, false) as MeshInstance3D
		if node == null or node.mesh == null:
			continue
		var previous: Dictionary = node.get_meta(META, {})
		var source := node.mesh
		var original_override := node.material_override
		var originals: Array[Material] = []
		if not previous.is_empty() and node.mesh == previous.result:
			source = previous.source
			original_override = previous.override
			originals.assign(previous.surfaces)
		else:
			for surface: int in source.get_surface_count():
				originals.append(node.get_surface_override_material(surface))
		var transform := to_head * _to_root(node, native_root)
		# The face sliders replace body with a derivative whose metadata retains
		# the neutral, already-refined source. Subdivide/sample that stable mesh
		# once; a new slider value only reapplies the cheap face field below.
		var neutral := source
		if part == "body" and node.has_meta(COMPACTOR.SOURCE_META) and source == node.get_meta(COMPACTOR.RESULT_META):
			neutral = node.get_meta(COMPACTOR.SOURCE_META) as Mesh
		var canonical_key := "%d:%s:%s:%s" % [neutral.get_instance_id(), transform, sex, part]
		var key := "%s:%s" % [canonical_key, shape if part == "body" else Vector3.ZERO]
		var result := _meshes.get(key) as ArrayMesh
		if result == null:
			if part == BEARD:
				result = _project_mesh(source, transform, projection, bundle, frame, shape, part)
			else:
				var canonical_mesh := _canonical_meshes.get(canonical_key) as ArrayMesh
				if canonical_mesh == null:
					canonical_mesh = _project_mesh(neutral, transform, projection, bundle, frame, Vector3.ZERO, part)
					if _canonical_meshes.size() >= CANONICAL_CACHE_LIMIT:
						_canonical_meshes.erase(_canonical_meshes.keys()[0])
					_canonical_meshes[canonical_key] = canonical_mesh
				result = _shape_mesh(canonical_mesh, transform, frame, shape) if part == "body" and not shape.is_zero_approx() else canonical_mesh
			if _meshes.size() >= CACHE_LIMIT:
				_meshes.erase(_meshes.keys()[0])
			_meshes[key] = result
		if part == BEARD:
			node.mesh = result
			node.set_meta(META, {"source": source, "result": result, "override": original_override,
				"surfaces": originals, "material": original_override})
			continue
		var active := original_override as ShaderMaterial
		if active == null and not originals.is_empty():
			active = originals[0] as ShaderMaterial
		if active == null:
			continue
		var material := ShaderMaterial.new()
		material.shader = SHADER
		var uniforms: Dictionary = {}
		for value: Dictionary in SHADER.get_shader_uniform_list():
			uniforms[str(value.name)] = true
		for value: Dictionary in active.shader.get_shader_uniform_list():
			var name := str(value.name)
			if uniforms.has(name):
				var data: Variant = active.get_shader_parameter(name)
				if data != null:
					material.set_shader_parameter(name, data)
		material.set_shader_parameter("portrait_paint", bundle.paint)
		material.set_shader_parameter("portrait_regions", bundle.regions)
		material.set_shader_parameter("portrait_normal", bundle.normal)
		node.material_override = material
		node.mesh = result
		node.set_meta(META, {"source": source, "result": result, "override": original_override,
			"surfaces": originals, "material": material})
	_prune_users()

static func restore(native_root: Node3D) -> void:
	if not is_instance_valid(native_root):
		return
	for part: String in PARTS + [BEARD]:
		var node := native_root.find_child(part, true, false) as MeshInstance3D
		if node == null or not node.has_meta(META):
			continue
		var previous: Dictionary = node.get_meta(META)
		if node.mesh == previous.result:
			node.mesh = previous.source as Mesh
		if node.material_override == previous.material:
			node.material_override = previous.override as Material
		var surfaces: Array = previous.surfaces
		for surface: int in mini(surfaces.size(), node.mesh.get_surface_count()):
			if node.get_surface_override_material(surface) == previous.material:
				node.set_surface_override_material(surface, surfaces[surface] as Material)
		node.remove_meta(META)

static func release(native_root: Node3D) -> void:
	if is_instance_valid(native_root):
		restore(native_root)
		native_root.remove_meta(USER_META)
		_users.erase(native_root.get_instance_id())
	_prune_users()

static func clear() -> void:
	for reference: WeakRef in _users.values():
		var node := reference.get_ref() as Node3D
		if is_instance_valid(node):
			restore(node)
			node.remove_meta(USER_META)
	_users.clear()
	_bundles.clear()
	_meshes.clear()
	_canonical_meshes.clear()

static func cache_metrics() -> Dictionary:
	var bytes := 0
	var seen := {}
	var sculpt_bytes := 0
	for bundle: Dictionary in _bundles.values():
		sculpt_bytes += (bundle.get("sculpt", PackedByteArray()) as PackedByteArray).size()
	for mesh: Mesh in _meshes.values() + _canonical_meshes.values():
		if seen.has(mesh.get_instance_id()):
			continue
		seen[mesh.get_instance_id()] = true
		for surface: int in mesh.get_surface_count():
			for attribute: Variant in mesh.surface_get_arrays(surface):
				if attribute != null:
					bytes += attribute.to_byte_array().size()
	return {"mesh_entries": _meshes.size(), "canonical_mesh_entries": _canonical_meshes.size(), "texture_bundles": _bundles.size(), "high_users": _users.size(),
		"array_bytes": bytes, "sculpt_cpu_bytes": sculpt_bytes,
		"compressed_texture_bytes": _bundles.size() * 4194384}

static func _bundle(sex: String) -> Dictionary:
	if _bundles.has(sex):
		return _bundles[sex]
	var path := "res://data/actors/portraits_high/%s.json" % sex
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if parsed is not Dictionary:
		return {}
	var descriptor := parsed as Dictionary
	var result: Dictionary = {"descriptor": descriptor}
	for name: String in ["paint", "regions", "normal"]:
		var texture := load(str(descriptor.textures[name])) as Texture2D
		if texture == null:
			return {}
		result[name] = texture
	if descriptor.has("geometry"):
		var geometry: Dictionary = descriptor.geometry
		var compressed := FileAccess.get_file_as_bytes(str(geometry.path))
		var decoded := compressed.decompress(int(geometry.size) * int(geometry.size) * int(geometry.stride), FileAccess.COMPRESSION_GZIP)
		if decoded.size() != int(geometry.size) * int(geometry.size) * int(geometry.stride):
			push_error("Human High sculpt payload is incomplete: " + str(geometry.path))
			return {}
		result.sculpt = decoded
	_bundles[sex] = result
	return result

static func _prune_users() -> void:
	var needed: Dictionary = {}
	for id: int in _users.keys():
		var node := (_users[id] as WeakRef).get_ref() as Node3D
		if not is_instance_valid(node) or not node.has_meta(USER_META):
			_users.erase(id)
		else:
			needed[str(node.get_meta(USER_META))] = true
	for sex: String in _bundles.keys():
		if not needed.has(sex):
			_bundles.erase(sex)
	if _users.is_empty():
		_meshes.clear()
		_canonical_meshes.clear()

static func _supported(config: Dictionary) -> bool:
	return str(config.get("culture", "")) == "luminous" and str(config.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func _project_mesh(source: Mesh, to_head: Transform3D, projection: Dictionary,
		bundle: Dictionary, frame: Dictionary, shape: Vector3, part: String) -> ArrayMesh:
	var result := ArrayMesh.new()
	for blend: int in source.get_blend_shape_count():
		result.add_blend_shape(source.get_blend_shape_name(blend))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var blends := source.surface_get_blend_shape_arrays(surface)
		var lods := LODS._surface_lods(source, surface)
		COMPACTOR.compact(arrays, blends, lods)
		var custom := part == "body" and not shape.is_zero_approx() and not frame.is_empty()
		if part != BEARD and bundle.has("sculpt"):
			_subdivide(arrays, blends, to_head, bundle, frame, shape, custom)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		var from_head := to_head.affine_inverse()
		var normal_to_head := to_head.basis.inverse().transposed()
		var normal_from_head := from_head.basis.inverse().transposed()
		var uv := PackedVector2Array()
		var colors := PackedColorArray()
		uv.resize(points.size())
		colors.resize(points.size())
		for index: int in points.size():
			var p := to_head * points[index]
			var canonical := _canonical(p, frame, shape) if custom else p
			if part == BEARD:
				# Groom retains the underlying skin point in its UV/color payload.
				# Follow that same field without changing the fitted shell's shape,
				# shader attributes or the exact lower-tier source identity.
				var groom_uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
				var groom_color: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
				var anchor := Vector3(groom_uv[index].x, groom_uv[index].y, groom_color[index].g - 0.2)
				var raw_anchor := _canonical(anchor, frame, shape) if not shape.is_zero_approx() else anchor
				var moved_anchor := _sculpt_point(raw_anchor, bundle)
				if not shape.is_zero_approx():
					moved_anchor = COMPACTOR.face_point(moved_anchor, frame, shape)
				points[index] = from_head * (p + moved_anchor - anchor)
				continue
			var sculpted := _sculpt_point(canonical, bundle)
			var moved := COMPACTOR.face_point(sculpted, frame, shape) if custom else sculpted
			points[index] = from_head * moved
			var influence := _sculpt_mask(canonical)
			if normals.size() == points.size() and influence > 0.0 and bundle.has("sculpt"):
				var n := _sample_sculpt(canonical, bundle, 3).normalized()
				if custom:
					var e := 0.0001
					var jacobian := Basis((COMPACTOR.face_point(sculpted + Vector3.RIGHT * e, frame, shape) - moved) / e,
						(COMPACTOR.face_point(sculpted + Vector3.UP * e, frame, shape) - moved) / e,
						(COMPACTOR.face_point(sculpted + Vector3.BACK * e, frame, shape) - moved) / e)
					n = (jacobian.inverse().transposed() * n).normalized()
				var original_normal := (normal_to_head * normals[index]).normalized()
				normals[index] = (normal_from_head * original_normal.lerp(n, influence).normalized()).normalized()
				if tangents.size() == points.size() * 4:
					var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
					tangent = (tangent - normals[index] * tangent.dot(normals[index])).normalized()
					for component: int in 3:
						tangents[index * 4 + component] = tangent[component]
			uv[index] = Vector2((canonical.x - float(projection.x_min)) / (float(projection.x_max) - float(projection.x_min)),
				(float(projection.y_max) - canonical.y) / (float(projection.y_max) - float(projection.y_min)))
			var mask := smoothstep(-0.065, -0.030, p.y) * (1.0 - smoothstep(0.180, 0.202, p.y))
			mask *= 1.0 - smoothstep(0.067, 0.091, absf(p.x))
			mask *= smoothstep(-0.020, 0.014, p.z)
			colors[index] = Color(mask, 0, 0, 1)
		arrays[Mesh.ARRAY_VERTEX] = points
		if part != BEARD:
			arrays[Mesh.ARRAY_NORMAL] = normals
			if not tangents.is_empty():
				arrays[Mesh.ARRAY_TANGENT] = tangents
			arrays[Mesh.ARRAY_TEX_UV2] = uv
			arrays[Mesh.ARRAY_COLOR] = colors
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays, blends, lods,
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result

## Reuse the completed High topology and source-normal field for every slider
## value. Only the face's existing bounded field and its Jacobian vary here.
static func _shape_mesh(source: Mesh, to_head: Transform3D, frame: Dictionary, shape: Vector3) -> ArrayMesh:
	var result := ArrayMesh.new()
	for blend: int in source.get_blend_shape_count():
		result.add_blend_shape(source.get_blend_shape_name(blend))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	var from_head := to_head.affine_inverse()
	var normal_to_head := to_head.basis.inverse().transposed()
	var normal_from_head := from_head.basis.inverse().transposed()
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		for index: int in points.size():
			var p := to_head * points[index]
			var moved := COMPACTOR.face_point(p, frame, shape)
			if moved == p:
				continue
			points[index] = from_head * moved
			var e := .0001
			var jacobian := Basis((COMPACTOR.face_point(p + Vector3.RIGHT * e, frame, shape) - moved) / e,
				(COMPACTOR.face_point(p + Vector3.UP * e, frame, shape) - moved) / e,
				(COMPACTOR.face_point(p + Vector3.BACK * e, frame, shape) - moved) / e)
			if normals.size() == points.size():
				normals[index] = (normal_from_head * jacobian.inverse().transposed() * normal_to_head * normals[index]).normalized()
			if tangents.size() == points.size() * 4:
				var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
				tangent = (from_head.basis * jacobian * to_head.basis * tangent).normalized()
				for component: int in 3:
					tangents[index * 4 + component] = tangent[component]
		arrays[Mesh.ARRAY_VERTEX] = points
		arrays[Mesh.ARRAY_NORMAL] = normals
		if not tangents.is_empty():
			arrays[Mesh.ARRAY_TANGENT] = tangents
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays,
			source.surface_get_blend_shape_arrays(surface), LODS._surface_lods(source, surface),
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result

## A pure rest-position field keeps duplicated UV-seam positions coincident.
## Neck, ears, rear skull and helmet/hair perimeter have exactly zero delta.
static func _sculpt_mask(p: Vector3) -> float:
	return smoothstep(-0.060, -0.030, p.y) * (1.0 - smoothstep(0.120, 0.145, p.y)) * \
		(1.0 - smoothstep(0.067, 0.083, absf(p.x))) * smoothstep(-0.004, 0.014, p.z)

static func _canonical(p: Vector3, frame: Dictionary, shape: Vector3) -> Vector3:
	var result := p
	for _iteration: int in 12:
		var residual := p - COMPACTOR.face_point(result, frame, shape)
		result += residual
		if residual.length_squared() < 0.0000000000000001:
			break
	return result

static func _sculpt_point(p: Vector3, bundle: Dictionary) -> Vector3:
	if not bundle.has("sculpt") or _sculpt_mask(p) <= 0.0:
		return p
	return p + _sample_sculpt(p, bundle, 0) * float(bundle.descriptor.geometry.max_delta_m) * _sculpt_mask(p)

static func _sample_sculpt(p: Vector3, bundle: Dictionary, offset: int) -> Vector3:
	var geometry: Dictionary = bundle.descriptor.geometry
	var projection: Dictionary = bundle.descriptor.projection
	var size := int(geometry.size)
	var stride := int(geometry.stride)
	var x := clampf((p.x - float(projection.x_min)) / (float(projection.x_max) - float(projection.x_min)), 0.0, 1.0) * (size - 1)
	var y := clampf((float(projection.y_max) - p.y) / (float(projection.y_max) - float(projection.y_min)), 0.0, 1.0) * (size - 1)
	var xi := floori(x)
	var yi := floori(y)
	var data: PackedByteArray = bundle.sculpt
	var samples: Array[Vector3] = []
	for point: Vector2i in [Vector2i(xi, yi), Vector2i(mini(xi + 1, size - 1), yi), Vector2i(xi, mini(yi + 1, size - 1)), Vector2i(mini(xi + 1, size - 1), mini(yi + 1, size - 1))]:
		var at := (point.y * size + point.x) * stride + offset
		samples.append(Vector3(data[at], data[at + 1], data[at + 2]) / 127.5 - Vector3.ONE)
	return samples[0].lerp(samples[1], x - xi).lerp(samples[2].lerp(samples[3], x - xi), y - yi)

## Adaptive red/green triangle splitting shares edge decisions between both
## incident faces. UV seams retain separate attributes but identical midpoints.
static func _subdivide(arrays: Array, blends: Array, to_head: Transform3D, bundle: Dictionary,
		frame: Dictionary, shape: Vector3, custom: bool) -> void:
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if indices.is_empty():
		return
	var edges := {}
	var out := PackedInt32Array()
	var limit := float(bundle.descriptor.geometry.edge_length_m)
	var canonical := PackedVector3Array()
	canonical.resize(points.size())
	for index: int in points.size():
		var p := to_head * points[index]
		canonical[index] = _canonical(p, frame, shape) if custom else p
	for triangle: int in range(0, indices.size(), 3):
		var ids: Array[int] = [indices[triangle], indices[triangle + 1], indices[triangle + 2]]
		var mids: Array[int] = [-1, -1, -1]
		for edge: int in 3:
			var a := ids[edge]
			var b := ids[(edge + 1) % 3]
			var pa := canonical[a]
			var pb := canonical[b]
			var midpoint := (pa + pb) * 0.5
			if midpoint.y < -0.045 or midpoint.y > 0.135 or absf(midpoint.x) > 0.080 or midpoint.z < 0.006 or pa.distance_to(pb) <= limit:
				continue
			var key := Vector2i(mini(a, b), maxi(a, b))
			if not edges.has(key):
				var added := (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
				_append_midpoint(arrays, a, b)
				# Canonical midpoint is sculpted once, rather than averaging two
				# already-displaced endpoints through a nonlinear custom face.
				var expanded: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				expanded[added] = to_head.affine_inverse() * (COMPACTOR.face_point(midpoint, frame, shape) if custom else midpoint)
				arrays[Mesh.ARRAY_VERTEX] = expanded
				for blend: Array in blends:
					_append_midpoint(blend, a, b)
				edges[key] = added
			mids[edge] = int(edges[key])
		var count := int(mids[0] >= 0) + int(mids[1] >= 0) + int(mids[2] >= 0)
		if count == 0:
			out.append_array(PackedInt32Array(ids))
		elif count == 3:
			out.append_array(PackedInt32Array([ids[0], mids[0], mids[2], mids[0], ids[1], mids[1], mids[2], mids[1], ids[2], mids[0], mids[1], mids[2]]))
		elif count == 1:
			var edge := 0 if mids[0] >= 0 else (1 if mids[1] >= 0 else 2)
			var a := ids[edge]
			var b := ids[(edge + 1) % 3]
			var c := ids[(edge + 2) % 3]
			out.append_array(PackedInt32Array([a, mids[edge], c, mids[edge], b, c]))
		else:
			var edge := 0 if mids[0] < 0 else (1 if mids[1] < 0 else 2)
			var a := ids[edge]
			var b := ids[(edge + 1) % 3]
			var c := ids[(edge + 2) % 3]
			var bc := mids[(edge + 1) % 3]
			var ca := mids[(edge + 2) % 3]
			out.append_array(PackedInt32Array([a, b, bc, a, bc, ca, ca, bc, c]))
	arrays[Mesh.ARRAY_INDEX] = out

static func _append_midpoint(arrays: Array, a: int, b: int) -> void:
	for attribute: int in Mesh.ARRAY_MAX:
		if attribute in [Mesh.ARRAY_INDEX, Mesh.ARRAY_BONES, Mesh.ARRAY_WEIGHTS] or arrays[attribute] == null:
			continue
		var values: Variant = arrays[attribute]
		if values is PackedVector3Array or values is PackedVector2Array or values is PackedColorArray:
			values.append(values[a].lerp(values[b], 0.5))
		elif values is PackedFloat32Array:
			var width := 4 if attribute == Mesh.ARRAY_TANGENT else 1
			for component: int in width:
				values.append((values[a * width + component] + values[b * width + component]) * 0.5)
		arrays[attribute] = values
	if arrays[Mesh.ARRAY_BONES] == null or arrays[Mesh.ARRAY_WEIGHTS] == null:
		return
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var width := int(bones.size() / ((arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() - 1))
	var merged := {}
	for index: int in width:
		merged[bones[a * width + index]] = float(merged.get(bones[a * width + index], 0.0)) + weights[a * width + index] * 0.5
		merged[bones[b * width + index]] = float(merged.get(bones[b * width + index], 0.0)) + weights[b * width + index] * 0.5
	var ordered: Array = merged.keys()
	ordered.sort_custom(func(left: int, right: int) -> bool: return float(merged[left]) > float(merged[right]))
	var total := 0.0
	for index: int in mini(width, ordered.size()):
		total += float(merged[ordered[index]])
	for index: int in width:
		bones.append(int(ordered[index]) if index < ordered.size() else 0)
		weights.append(float(merged[ordered[index]]) / maxf(total, 0.00001) if index < ordered.size() else 0.0)
	arrays[Mesh.ARRAY_BONES] = bones
	arrays[Mesh.ARRAY_WEIGHTS] = weights

static func _to_root(node: Node3D, root: Node3D) -> Transform3D:
	var result := Transform3D.IDENTITY
	var cursor: Node = node
	while cursor != root and cursor != null:
		if cursor is Node3D:
			result = (cursor as Node3D).transform * result
		cursor = cursor.get_parent()
	return result

extends RefCounted
## A mounted-only attachment adapter. The spine/neck policy follows the nape
## anatomically while keeping shoulder-root motion bounded. A pure canonical
## rebase preserves the reference rendered fit. Optional shoulder
## relief deliberately changes that fit while pinning the central neckline
## and the lower panel; its target error is reported separately.
## The source mesh, source skin and all body poses remain unchanged.
const Data := preload("res://src/actors/cape_approved_data.gd")
const HEAD := 16
const NECK := 15
const SPINE := 12
const MAX_CACHE := 64
static var _cache: Dictionary = {}

static func recommended_relief(profile: String) -> Vector2:
	return Vector2(.02, .02) if profile == "armour" else Vector2(.008, 0.0)

static func attachment_recipe(mode: String) -> Dictionary:
	if mode == "spine_neck":
		return {"body_slot_12": "spine_03 with original slot-12 bind",
			"body_slots_13_to_16": "neck_01 with original slot-15 bind",
			"root_reference": "Canonical spine skin frame for controls 0, 4 and 8",
			"root_pose": "G(current) * inverse(G(canonical)) * canonical_spine_frame",
			"root_neck_fractions": "Left, centre and right .50",
			"G": "Normalized quaternion blend, translated to preserve the blended transformed material centroid",
			"centroid": "Mounted rest vertex centroid weighted by that root control, plus its idle translation"}
	return {"mode": mode, "reference": "Canonical global-rest palettes"}

static func relief_recipe() -> Dictionary:
	return {"coordinate_space": "Original approved native anatomical positions",
		"direction": "Vector2(posterior -Z metres, upward +Y metres)",
		"posterior_height": Vector2(1.22, 1.38),
		"neck_pin_height": Vector2(1.44, 1.53),
		"neck_pin_abs_x": Vector2(.035, .11),
		"upward_height": Vector2(1.36, 1.50),
		"upward_abs_x": Vector2(.05, .12),
		"interpolation": "Quintic smootherstep, with analytic derivatives",
		"fixed_neckline": "abs(source.x) <= .035 and source.y >= 1.53",
		"fixed_lower_panel": "source.y <= 1.22"}

static func _quintic(value: float, low: float, high: float) -> Vector2:
	var t := clampf((value - low) / (high - low), 0.0, 1.0)
	return Vector2(t * t * t * (10.0 + t * (-15.0 + 6.0 * t)),
		30.0 * t * t * (t - 1.0) * (t - 1.0) / (high - low))

## Delta and its three derivative columns, evaluated in the original fit.
static func relief_field(point: Vector3, relief: Vector2) -> PackedVector3Array:
	var height := _quintic(point.y, 1.22, 1.38)
	var neck := _quintic(point.y, 1.44, 1.53)
	var lateral := _quintic(absf(point.x), .035, .11)
	var side := signf(point.x)
	var pin_release := 1.0 - neck.x * (1.0 - lateral.x)
	var back := height.x * pin_release
	var back_x := height.x * neck.x * lateral.y * side
	var back_y := height.y * pin_release - height.x * neck.y * (1.0 - lateral.x)
	var up_height := _quintic(point.y, 1.36, 1.50)
	var up_lateral := _quintic(absf(point.x), .05, .12)
	var up := up_height.x * up_lateral.x
	var up_x := up_height.x * up_lateral.y * side
	var up_y := up_height.y * up_lateral.x
	return PackedVector3Array([Vector3(0.0, relief.y * up, -relief.x * back),
		Vector3(0.0, relief.y * up_x, -relief.x * back_x),
		Vector3(0.0, relief.y * up_y, -relief.x * back_y), Vector3.ZERO])

static func _zero_basis() -> Basis:
	return Basis(Vector3.ZERO, Vector3.ZERO, Vector3.ZERO)

static func _blend(palettes: Array[Transform3D], bones: PackedInt32Array,
		weights: PackedFloat32Array, first: int) -> Transform3D:
	var basis := _zero_basis()
	var origin := Vector3.ZERO
	for slot: int in 8:
		var weight := weights[first + slot]
		if weight == 0.0:
			continue
		var pose := palettes[bones[first + slot]]
		basis.x += pose.basis.x * weight
		basis.y += pose.basis.y * weight
		basis.z += pose.basis.z * weight
		origin += pose.origin * weight
	return Transform3D(basis, origin)

static func _cache_key(profile: String, source: Mesh,
		palettes: Array[Transform3D], mode: String, relief: Vector2) -> String:
	var values := PackedFloat64Array()
	values.append(relief.x)
	values.append(relief.y)
	for pose: Transform3D in palettes:
		for column: Vector3 in [pose.basis.x, pose.basis.y, pose.basis.z, pose.origin]:
			values.append(column.x)
			values.append(column.y)
			values.append(column.z)
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(values.to_byte_array())
	return "%s|%s|%s|%s" % [profile, mode, source.get_instance_id(), hash.finish().hex_encode()]

## Returns an empty dictionary when the source is not a compatible approved
## cape. The canonical global-rest reference makes the mounted variant
## independent of the first received gait or upper-body action.
static func build(profile: String, source_mesh: Mesh, skeleton: Skeleton3D,
		mode: String = "head_neck", relief: Vector2 = Vector2.ZERO) -> Dictionary:
	if source_mesh == null or skeleton == null or not Data.compatible(skeleton):
		return {}
	if mode != "head_neck" and mode != "rigid_neck" and mode != "rigid_spine" \
			and mode != "spine_neck":
		return {}
	if not relief.is_finite() or relief.x < 0.0 or relief.y < 0.0 \
			or relief.x > .020001 or relief.y > .020001:
		return {}
	var names := Data.bone_names()
	var binds := Data.binds(profile)
	var idle := Data.idle(profile)
	var fit: Dictionary = Data.catalog().get("fits", {}).get(profile, {})
	var surfaces: Array = fit.get("surfaces", [])
	if binds.size() != 17 or names.size() != 17 or idle.size() != 12 \
			or names[HEAD] != "Head" or names[NECK] != "neck_01" \
			or source_mesh.get_surface_count() != surfaces.size() \
			or source_mesh.get_blend_shape_count() != 0:
		return {}
	var reference: Array[Transform3D] = []
	var frame := skeleton.get_bone_global_rest(skeleton.find_bone("spine_03")) * binds[SPINE]
	for i: int in 17:
		reference.append(frame * Transform3D(Basis.IDENTITY, idle[i]) if i < 12 else
			skeleton.get_bone_global_rest(skeleton.find_bone(names[i])) * binds[i])
	var key := _cache_key(profile, source_mesh, reference, mode, relief)
	if _cache.has(key):
		return _cache[key] as Dictionary
	var modified := reference.duplicate()
	var rigid := mode == "rigid_neck" or mode == "rigid_spine"
	var mixed := mode == "spine_neck"
	var attachment := SPINE if mode == "rigid_spine" or mixed else NECK
	for i: int in 17:
		if mixed and i >= 12:
			modified[i] = reference[SPINE if i == SPINE else NECK]
		elif i == HEAD or (rigid and i >= 12):
			modified[i] = reference[attachment]
		elif rigid and i % 4 == 0:
			modified[i] = reference[attachment] * Transform3D(Basis.IDENTITY, idle[i])
	var skin := Skin.new()
	for i: int in 17:
		var alias := i == HEAD or (rigid and i >= 12)
		var target := (SPINE if i == SPINE else NECK) if mixed and i >= 12 \
			else (attachment if alias else i)
		skin.add_named_bind(names[target], binds[target])
	var mesh := ArrayMesh.new()
	mesh.resource_name = "Cape mounted %s attachment: %s" % [mode, profile]
	var source_positions: Array[PackedVector3Array] = []
	var source_weights: Array[PackedFloat32Array] = []
	var reference_deltas: Array[PackedVector3Array] = []
	var affected := 0
	var affected_head := 0
	var maximum_rest_change := 0.0
	var pure_rebase_error := 0.0
	var maximum_relief := 0.0
	var neckline_relief := 0.0
	var lower_relief := 0.0
	var relief_vertices := 0
	for surface: int in surfaces.size():
		var arrays := source_mesh.surface_get_arrays(surface)
		var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
		var raw_weights := Data._floats(str(fit.get("file", "")), surfaces[surface].get("weights", {}))
		if positions.size() != int(surfaces[surface].get("vertices", 0)) \
				or bones.size() != positions.size() * 8 or weights.size() != bones.size() \
				or raw_weights.size() != weights.size():
			return {}
		source_positions.append(positions.duplicate())
		source_weights.append(weights.duplicate())
		positions = positions.duplicate()
		normals = normals.duplicate()
		tangents = tangents.duplicate()
		var deltas := PackedVector3Array()
		deltas.resize(positions.size())
		for vertex: int in positions.size():
			var original := positions[vertex]
			var field := relief_field(original, relief)
			var delta := frame.basis * field[0]
			deltas[vertex] = delta
			var relief_length := delta.length()
			maximum_relief = maxf(maximum_relief, relief_length)
			if absf(original.x) <= .035 and original.y >= 1.53:
				neckline_relief = maxf(neckline_relief, relief_length)
			if original.y <= 1.22:
				lower_relief = maxf(lower_relief, relief_length)
			if relief_length > 0.0:
				relief_vertices += 1
			var head_weight := 0.0
			var changed_weight := 0.0
			for slot: int in 8:
				var bone := bones[vertex * 8 + slot]
				var weight := weights[vertex * 8 + slot]
				if bone == HEAD:
					head_weight += weight
				if bone == HEAD or (mixed and bone >= 12) \
						or (rigid and (bone >= 12 or bone % 4 == 0)):
					changed_weight += weight
			if changed_weight == 0.0 and relief_length == 0.0:
				continue
			if head_weight > 0.0:
				affected_head += 1
			var old := _blend(reference, bones, weights, vertex * 8)
			var replacement := _blend(modified, bones, weights, vertex * 8)
			if absf(replacement.basis.determinant()) < .00000001:
				return {}
			var inverse := replacement.basis.inverse()
			var rebased := inverse * (old * original - replacement.origin)
			pure_rebase_error = maxf(pure_rebase_error,
				(old * original).distance_to(replacement * rebased))
			positions[vertex] = rebased + inverse * delta
			maximum_rest_change = maxf(maximum_rest_change, positions[vertex].distance_to(original))
			# The relief is a smooth geometric warp of the reference surface.
			# Normal covectors and tangent vectors take its inverse transpose
			# and forward Jacobian, before undoing the replacement skin basis.
			var derivative := frame.basis * Basis(field[1], field[2], field[3])
			var warped := Basis(old.basis.x + derivative.x,
				old.basis.y + derivative.y, old.basis.z + derivative.z)
			var warp := warped * old.basis.inverse()
			if warp.determinant() < .00000001:
				return {}
			var normal_vectors := inverse * warp.inverse().transposed() * old.basis
			var tangent_vectors := inverse * warp * old.basis
			if normals.size() == positions.size():
				normals[vertex] = (normal_vectors * normals[vertex]).normalized()
			if tangents.size() == positions.size() * 4:
				var at := vertex * 4
				var tangent := tangent_vectors * Vector3(tangents[at], tangents[at + 1], tangents[at + 2])
				tangent = tangent.normalized()
				tangents[at] = tangent.x
				tangents[at + 1] = tangent.y
				tangents[at + 2] = tangent.z
			affected += 1
		reference_deltas.append(deltas)
		arrays[Mesh.ARRAY_VERTEX] = positions
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_TANGENT] = tangents
		# Repacking readback UNORM16 values would quantize them a second time.
		# Original authoring float32 values produce the same native GPU weights.
		arrays[Mesh.ARRAY_WEIGHTS] = raw_weights
		mesh.add_surface_from_arrays(source_mesh.surface_get_primitive_type(surface),
			arrays, [], {}, Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		mesh.surface_set_material(surface, source_mesh.surface_get_material(surface))
		mesh.surface_set_name(surface, source_mesh.surface_get_name(surface))
	var maximum_error := 0.0
	for surface: int in surfaces.size():
		var arrays := mesh.surface_get_arrays(surface)
		var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		if weights.to_byte_array() != source_weights[surface].to_byte_array():
			return {}
		for vertex: int in positions.size():
			var old := _blend(reference, bones, source_weights[surface], vertex * 8)
			var replacement := _blend(modified, bones, weights, vertex * 8)
			maximum_error = maxf(maximum_error,
				(old * source_positions[surface][vertex] + reference_deltas[surface][vertex]).distance_to(replacement * positions[vertex]))
	var result := {"mesh": mesh, "skin": skin, "reference_error_m": maximum_error,
		"pure_rebase_error_m": pure_rebase_error,
		"reference_frame": frame,
		"reference_target": "original_reference_plus_intentional_relief",
		"has_intentional_relief": relief != Vector2.ZERO,
		"intentional_relief": relief, "maximum_intentional_relief_m": maximum_relief,
		"neckline_maximum_relief_m": neckline_relief, "lower_maximum_relief_m": lower_relief,
		"relief_vertices": relief_vertices, "relief_recipe": relief_recipe(),
		"reference_palettes": reference, "modified_reference_palettes": modified,
		"original_mesh": source_mesh, "original_skin": Data.fit_skin(profile),
		"affected_head_vertices": affected_head, "affected_attachment_vertices": affected,
		"maximum_rest_change_m": maximum_rest_change,
		"gpu_weights_preserved": true, "source_profile": profile, "mode": mode,
		"attachment_bone": "spine_03+neck_01" if mixed else names[attachment],
		"attachment_recipe": attachment_recipe(mode),
		"reference_pose": "canonical_global_rest",
		"root_controls_follow_attachment": rigid,
		"root_controls_follow_neck": mode == "rigid_neck"}
	if _cache.size() >= MAX_CACHE:
		_cache.clear()
	_cache[key] = result
	return result

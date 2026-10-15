class_name WardrobeShirtFit
extends RefCounted
## A shared, one-time mesh fit for the native shirt shown by wardrobe-only
## class torsos.
##
## The approved source shirt carries deliberately full upper arms.  That is a
## good anatomical source beneath generated armour, but reads as a padded
## shoulder when the class torso is only a recolour of that shirt.  Contract
## the shirt around each humerus using its existing upper-arm skin weights.
## The edit is radial in Y/Z only: shoulder width, sleeve length, UVs, indices,
## skinning, the collar and the centre-front placket remain authored data.

const RADIAL_SCALE := 0.88
const PLACKET_HALF_WIDTH := 0.10
const COLLAR_HALF_WIDTH := 0.20
const COLLAR_FLOOR := 1.38

const _ORIGINAL_META := &"wardrobe_shirt_unfitted_mesh"
const _RESULT_META := &"wardrobe_shirt_fitted_mesh"

static var _cache: Dictionary = {}


## Release derived meshes with the imported-scene/body-cover caches when a
## world session ends; the next session will populate only the shirts it uses.
static func clear() -> void:
	_cache.clear()


## Remove this presentation-only fit before another wardrobe/body-cover pass.
## TorsoBodyCover can then always cut its canonical, unfitted source mesh.
static func restore(instance: MeshInstance3D) -> void:
	if not instance.has_meta(_ORIGINAL_META):
		return
	instance.mesh = instance.get_meta(_ORIGINAL_META) as Mesh
	instance.remove_meta(_RESULT_META)


## Fit the mesh currently on `instance`. Call after TorsoBodyCover has selected
## the appropriate uncovered/cut variant. Results are shared by every actor
## that reaches the same source mesh and skin.
static func apply(instance: MeshInstance3D, skeleton: Skeleton3D) -> void:
	if instance.mesh == null or instance.skin == null or skeleton == null:
		return
	if instance.has_meta(_RESULT_META):
		var prior: Variant = instance.get_meta(_RESULT_META)
		if prior is Mesh and instance.mesh == prior:
			return
	if not instance.has_meta(_ORIGINAL_META):
		instance.set_meta(_ORIGINAL_META, instance.mesh)
	var source: Mesh = instance.mesh
	# Imported scenes can materialise an equivalent Skin resource per actor.
	# Key on its ordered bind meaning, not its transient instance ID, so a crowd
	# shares one fitted mesh per source instead of building one per wearer.
	var key := "%s|%s" % [source.get_instance_id(),
		_bind_signature(instance.skin, skeleton)]
	if not _cache.has(key):
		_cache[key] = contract(source, instance.skin, skeleton)
	instance.mesh = _cache[key] as Mesh
	instance.set_meta(_RESULT_META, instance.mesh)


static func contract(source: Mesh, skin: Skin, skeleton: Skeleton3D) -> Mesh:
	if source == null or skin == null or skeleton == null:
		return source
	var upper_binds := PackedInt32Array([-1, -1])
	var shoulder := PackedVector3Array([Vector3.ZERO, Vector3.ZERO])
	var elbow := PackedVector3Array([Vector3.ZERO, Vector3.ZERO])
	for side: int in range(2):
		var suffix := "_l" if side == 0 else "_r"
		var upper_name := StringName("upperarm" + suffix)
		var lower_name := StringName("lowerarm" + suffix)
		upper_binds[side] = _bind_for(skin, skeleton, upper_name)
		var upper_bone := skeleton.find_bone(upper_name)
		var lower_bone := skeleton.find_bone(lower_name)
		if upper_binds[side] < 0 or upper_bone < 0 or lower_bone < 0:
			return source
		shoulder[side] = skeleton.get_bone_global_rest(upper_bone).origin
		elbow[side] = skeleton.get_bone_global_rest(lower_bone).origin

	var result := ArrayMesh.new()
	result.resource_name = source.resource_name + " Wardrobe Shoulder Fit"
	for blend: int in range(source.get_blend_shape_count()):
		result.add_blend_shape(source.get_blend_shape_name(blend))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	var moved := false
	for surface: int in range(source.get_surface_count()):
		var arrays: Array = source.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var stride := bones.size() / maxi(vertices.size(), 1)
		if stride > 0 and weights.size() == bones.size():
			for index: int in range(vertices.size()):
				var point: Vector3 = vertices[index]
				# These two authored construction details define the class shirt.
				# Protect them explicitly as well as through their spine/neck weights.
				if absf(point.x) <= PLACKET_HALF_WIDTH or (point.y >= COLLAR_FLOOR
						and absf(point.x) <= COLLAR_HALF_WIDTH):
					continue
				var influence := Vector2.ZERO
				for slot: int in range(stride):
					var at := index * stride + slot
					if bones[at] == upper_binds[0]:
						influence.x += weights[at]
					elif bones[at] == upper_binds[1]:
						influence.y += weights[at]
				var side := 0 if influence.x >= influence.y else 1
				var share: float = influence[side]
				if share <= 0.0001:
					continue
				# Both approved rigs hold the rest arms almost horizontally. Interpolate
				# the Y/Z centre at this X but never alter X itself, so neither the
				# shoulder span nor sleeve length can drift.
				var span: float = elbow[side].x - shoulder[side].x
				if absf(span) <= 0.0001:
					continue
				var along: float = (point.x - shoulder[side].x) / span
				var centre: Vector3 = shoulder[side].lerp(elbow[side], along)
				var scale := lerpf(1.0, RADIAL_SCALE, clampf(share, 0.0, 1.0))
				vertices[index] = Vector3(point.x,
					centre.y + (point.y - centre.y) * scale,
					centre.z + (point.z - centre.z) * scale)
				moved = true
		arrays[Mesh.ARRAY_VERTEX] = vertices
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface),
			arrays, source.surface_get_blend_shape_arrays(surface),
			_surface_lods(source, surface),
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result if moved else source


static func _bind_for(skin: Skin, skeleton: Skeleton3D, wanted: StringName) -> int:
	for bind: int in range(skin.get_bind_count()):
		var name := skin.get_bind_name(bind)
		if name.is_empty():
			var bone := skin.get_bind_bone(bind)
			if bone >= 0 and bone < skeleton.get_bone_count():
				name = skeleton.get_bone_name(bone)
		if name == wanted:
			return bind
	return -1


static func _bind_signature(skin: Skin, skeleton: Skeleton3D) -> String:
	var ordered := PackedStringArray()
	for bind: int in range(skin.get_bind_count()):
		var name := skin.get_bind_name(bind)
		if name.is_empty():
			var bone := skin.get_bind_bone(bind)
			if bone >= 0 and bone < skeleton.get_bone_count():
				name = skeleton.get_bone_name(bone)
		ordered.append(str(name))
	return ",".join(ordered)


## Godot 4.7 exposes generated LODs through RenderingServer as packed index
## buffers. Convert them back to the dictionary accepted by ArrayMesh.
static func _surface_lods(source: Mesh, surface: int) -> Dictionary:
	if source is not ArrayMesh:
		return {}
	var raw: Dictionary = RenderingServer.mesh_get_surface(
		source.get_rid(), surface)
	var raw_lods: Variant = raw.get("lods", [])
	if raw_lods is not Array:
		return {}
	var index_width := 2 if int(raw.get("vertex_count", 0)) <= 65536 else 4
	var result: Dictionary = {}
	for lod_value: Variant in raw_lods as Array:
		if lod_value is not Dictionary:
			continue
		var lod := lod_value as Dictionary
		var distance := float(lod.get("edge_length", 0.0))
		var bytes_value: Variant = lod.get("index_data", PackedByteArray())
		if distance <= 0.0 or bytes_value is not PackedByteArray:
			continue
		var bytes := bytes_value as PackedByteArray
		if bytes.is_empty() or bytes.size() % index_width != 0:
			continue
		var indices := PackedInt32Array()
		indices.resize(bytes.size() / index_width)
		for index: int in range(indices.size()):
			var offset := index * index_width
			indices[index] = (bytes.decode_u16(offset) if index_width == 2
				else bytes.decode_u32(offset))
		result[distance] = indices
	return result

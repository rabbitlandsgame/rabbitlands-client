extends RefCounted
## The reviewed cape is shared geometry with the existing cape's materials.
## Files contain only fitted surfaces and twelve-control motion, never a body
## animation library. All vectors/binds are in the native skeleton's space.

const CATALOG := "res://data/actors/cape_motion/catalog.json"
const TEMPLATE := "res://assets/actors/native/equipment/generic_cape.glb"
static var _catalog: Dictionary = {}
static var _loaded := false
static var _buffers: Dictionary = {}
static var _meshes: Dictionary = {}
static var _skins: Dictionary = {}

static func catalog() -> Dictionary:
	if not _loaded:
		_loaded = true
		if FileAccess.file_exists(CATALOG):
			var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
			if value is Dictionary:
				_catalog = value
	return _catalog

static func ready() -> bool:
	return int(catalog().get("schema_version", 0)) == 1 and not (catalog().get("fits", {}) as Dictionary).is_empty()

static func bone_names() -> PackedStringArray:
	return PackedStringArray(catalog().get("bones", []))

static func compatible(skeleton: Skeleton3D) -> bool:
	if skeleton == null or not ready():
		return false
	var names := bone_names()
	if names.size() != 17:
		return false
	for name: String in names:
		if skeleton.find_bone(name) < 0:
			return false
	return true

static func _bytes(file: String) -> PackedByteArray:
	var path := file if file.begins_with("res://") else CATALOG.get_base_dir().path_join(file)
	if not _buffers.has(path):
		_buffers[path] = FileAccess.get_file_as_bytes(path)
	return _buffers[path] as PackedByteArray

static func _view(file: String, descriptor: Dictionary) -> PackedByteArray:
	var bytes := _bytes(file)
	var offset := int(descriptor.get("offset", 0))
	var length := int(descriptor.get("count", 0)) * 4
	if offset < 0 or length < 0 or offset + length > bytes.size():
		return PackedByteArray()
	return bytes.slice(offset, offset + length)

static func _floats(file: String, descriptor: Dictionary) -> PackedFloat32Array:
	return _view(file, descriptor).to_float32_array()

static func _vectors3(values: PackedFloat32Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	out.resize(values.size() / 3)
	for i: int in out.size():
		out[i] = Vector3(values[i * 3], values[i * 3 + 1], values[i * 3 + 2])
	return out

static func _vectors2(values: PackedFloat32Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	out.resize(values.size() / 2)
	for i: int in out.size():
		out[i] = Vector2(values[i * 2], values[i * 2 + 1])
	return out

static func fit_mesh(profile: String, template: Mesh) -> ArrayMesh:
	var key := "%s|%s" % [profile, template.get_instance_id()]
	if _meshes.has(key):
		return _meshes[key] as ArrayMesh
	var fit: Dictionary = (catalog().get("fits", {}) as Dictionary).get(profile, {})
	var surfaces: Array = fit.get("surfaces", [])
	if surfaces.is_empty() or template.get_surface_count() != surfaces.size():
		return null
	var mesh := ArrayMesh.new()
	var file := str(fit.get("file", ""))
	for i: int in surfaces.size():
		var surface: Dictionary = surfaces[i]
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = _vectors3(_floats(file, surface.get("positions", {})))
		arrays[Mesh.ARRAY_NORMAL] = _vectors3(_floats(file, surface.get("normals", {})))
		arrays[Mesh.ARRAY_TANGENT] = _floats(file, surface.get("tangents", {}))
		arrays[Mesh.ARRAY_TEX_UV] = _vectors2(_floats(file, surface.get("uv", {})))
		arrays[Mesh.ARRAY_INDEX] = _view(file, surface.get("indices", {})).to_int32_array()
		arrays[Mesh.ARRAY_BONES] = _view(file, surface.get("bones", {})).to_int32_array()
		arrays[Mesh.ARRAY_WEIGHTS] = _floats(file, surface.get("weights", {}))
		var count: int = (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		if count == 0 or (arrays[Mesh.ARRAY_BONES] as PackedInt32Array).size() != count * 8 \
				or (arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array).size() != count * 8:
			return null
		mesh.add_surface_from_arrays(int(surface.get("primitive", Mesh.PRIMITIVE_TRIANGLES)),
			arrays, [], {}, Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		mesh.surface_set_material(i, template.surface_get_material(i))
		mesh.surface_set_name(i, template.surface_get_name(i))
	_meshes[key] = mesh
	return mesh

static func _transform(values: Array) -> Transform3D:
	if values.size() != 16:
		return Transform3D.IDENTITY
	return Transform3D(Basis(Vector3(values[0], values[4], values[8]),
		Vector3(values[1], values[5], values[9]), Vector3(values[2], values[6], values[10])),
		Vector3(values[3], values[7], values[11]))

static func binds(profile: String) -> Array[Transform3D]:
	var out: Array[Transform3D] = []
	var fit: Dictionary = (catalog().get("fits", {}) as Dictionary).get(profile, {})
	for value: Variant in fit.get("binds", []):
		out.append(_transform(value as Array))
	return out

static func fit_skin(profile: String) -> Skin:
	if _skins.has(profile):
		return _skins[profile] as Skin
	var names := bone_names()
	var poses := binds(profile)
	if names.size() != poses.size():
		return null
	var skin := Skin.new()
	for i: int in names.size():
		skin.add_named_bind(names[i], poses[i])
	_skins[profile] = skin
	return skin

static func neutral_rests(skeleton: Skeleton3D, profile: String) -> Dictionary:
	var result := {}
	var names := bone_names()
	var poses := binds(profile)
	if names.size() != poses.size() or names.find("spine_03") < 0:
		return result
	var frame := skeleton.get_bone_global_rest(skeleton.find_bone("spine_03")) * poses[names.find("spine_03")]
	for i: int in 12:
		result[skeleton.find_bone(names[i])] = frame * poses[i].affine_inverse()
	return result

static func _profiles() -> Dictionary:
	return (catalog().get("motion", {}) as Dictionary).get("profiles", {}) as Dictionary

static func idle(profile: String) -> PackedVector3Array:
	var data: Dictionary = _profiles().get(profile, {})
	return _vectors3(PackedFloat32Array(data.get("idle", [])))

static func motion_clip(profile: String, clip: String) -> Dictionary:
	var profiles := _profiles()
	for name: String in [profile, "wardrobe", "armour"]:
		var entry: Dictionary = (profiles.get(name, {}) as Dictionary).get("clips", {}).get(clip, {})
		if not entry.is_empty():
			entry["source_profile"] = name
			if not entry.has("decoded"):
				entry["decoded"] = _floats(str((catalog().get("motion", {}) as Dictionary).get("file", "")), entry.get("values", {}))
				if entry.has("entry"):
					var start: Dictionary = entry["entry"]
					start["decoded"] = _floats(str((catalog().get("motion", {}) as Dictionary).get("file", "")), start.get("values", {}))
			return entry
	return {}

static func sample(entry: Dictionary, seconds: float) -> PackedVector3Array:
	var out := PackedVector3Array()
	var values: PackedFloat32Array = entry.get("decoded", PackedFloat32Array())
	var count := int(entry.get("samples", 0))
	if count < 1 or values.size() != count * 36:
		return out
	var duration := maxf(float(entry.get("duration", 0.0)), 0.000001)
	var time := fposmod(seconds, duration) if bool(entry.get("loop", false)) else clampf(seconds, 0.0, duration)
	var phase := time / duration * float(count - 1)
	var at := mini(int(phase), count - 1)
	var next := mini(at + 1, count - 1)
	var fraction := phase - at
	out.resize(12)
	for bone: int in 12:
		var offset := at * 36 + bone * 3
		var after := next * 36 + bone * 3
		out[bone] = Vector3(values[offset], values[offset + 1], values[offset + 2]).lerp(
			Vector3(values[after], values[after + 1], values[after + 2]), fraction)
	return out

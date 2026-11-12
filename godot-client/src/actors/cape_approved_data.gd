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
## shade(): rounds of turning shell triangles against their smooth normal, and
## the weld quantum (positions rounded to 0.01 mm).
const SHADE_PASSES := 2
const WELD_SCALE := 100000.0

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

## The lining surface: single-sided, wound toward the body.
static func is_lining(surface: Dictionary) -> bool:
	return str(surface.get("name", "")).ends_with("Detail")

## The fit's triangles, each wound the way the shared cape's build winds them
## (eloria-assets/tools/build_shared_cape.py). The approved fits were exported
## with their authoring winding, which that build corrects but the export did
## not: about 4 % of the cloth and trim triangles faced against the shading
## normal their corners carry, and about 200 lining triangles faced away from
## the body. The cloth and trim are double-sided and Godot turns a back face's
## normal round, so such a triangle in a fold was lit from inside the cape: a
## dark slit across the cloth. The lining is single-sided so that it is culled
## wherever it comes through the outer layer; facing out, it showed there.
## - Cloth and trim: a triangle faces the way its corners' normals point.
## - Lining: a triangle faces the trunk axis (native model space, Y up).
## Only the order within a triangle changes; vertices, the triangle set and the
## surface sizes stay exactly the approved ones. Godot's front faces are
## clockwise, so a triangle (a, b, c) faces along (c - a) x (b - a).
static func wound(indices: PackedInt32Array, vertices: PackedVector3Array,
		normals: PackedVector3Array, lining: bool) -> PackedInt32Array:
	var out := indices.duplicate()
	var count := vertices.size()
	for at: int in range(0, out.size() - 2, 3):
		var a := out[at]
		var b := out[at + 1]
		var c := out[at + 2]
		if a < 0 or b < 0 or c < 0 or a >= count or b >= count or c >= count:
			continue
		var facing := (vertices[c] - vertices[a]).cross(vertices[b] - vertices[a])
		var wanted: Vector3
		if lining:
			var centre := (vertices[a] + vertices[b] + vertices[c]) / 3.0
			wanted = Vector3(-centre.x, 0.0, -centre.z)
		elif normals.size() == count:
			wanted = normals[a] + normals[b] + normals[c]
		else:
			continue
		if facing.dot(wanted) < 0.0:
			out[at + 1] = c
			out[at + 2] = b
	return out

## Smooth shading for the approved fits, as the shared cape's build gives the
## shipped cape. The fits carry split normals from their authoring: the copies
## of one vertex on either side of a UV seam point up to 180 degrees apart
## (median 60), so each of the decimated cloth's ~1000 small UV islands was lit
## on its own and the cape looked faceted and sharp. Here each layer gets
## normals welded by position and summed from its triangles (area-weighted):
## the cloth and trim together, as one shell, and the lining on its own (where
## it meets the cloth their normals point opposite ways and would cancel).
## Twice, a shell triangle facing against its corners' smooth normal is turned
## and the normals are summed again; the lining is first turned toward the
## trunk. Tangents keep their UV direction, made perpendicular to the new
## normal. Vertices, UVs, skin and the triangle set are untouched, so the
## approved fit files, and the hashes that certify them, stay as they are.
## `surfaces` holds mesh arrays (edited in place); `linings` flags each one.
static func shade(surfaces: Array, linings: Array[bool]) -> void:
	var shell: Array = []
	var lining: Array = []
	for i: int in surfaces.size():
		var arrays: Array = surfaces[i]
		if linings[i]:
			arrays[Mesh.ARRAY_INDEX] = wound(arrays[Mesh.ARRAY_INDEX],
				arrays[Mesh.ARRAY_VERTEX], PackedVector3Array(), true)
			lining.append(arrays)
		else:
			shell.append(arrays)
	_shade_layer(shell, SHADE_PASSES)
	_shade_layer(lining, 0)

## One layer: weld by position (0.01 mm, as the shared cape's build does),
## `passes` rounds of turning triangles against their smooth normal, then the
## final normals and tangents.
static func _shade_layer(layer: Array, passes: int) -> void:
	if layer.is_empty():
		return
	var ids := {}
	var welds: Array[PackedInt32Array] = []
	for arrays: Array in layer:
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var weld := PackedInt32Array()
		weld.resize(vertices.size())
		for v: int in vertices.size():
			var point := vertices[v]
			var cell := Vector3i(roundi(point.x * WELD_SCALE), roundi(point.y * WELD_SCALE),
				roundi(point.z * WELD_SCALE))
			var id: int = ids.get(cell, -1)
			if id < 0:
				id = ids.size()
				ids[cell] = id
			weld[v] = id
		welds.append(weld)
	var smooth := PackedVector3Array()
	for round_index: int in passes + 1:
		smooth = PackedVector3Array()
		smooth.resize(ids.size())
		for s: int in layer.size():
			var vertices: PackedVector3Array = layer[s][Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = layer[s][Mesh.ARRAY_INDEX]
			var weld := welds[s]
			for at: int in range(0, indices.size() - 2, 3):
				var a := indices[at]
				var b := indices[at + 1]
				var c := indices[at + 2]
				var face := (vertices[c] - vertices[a]).cross(vertices[b] - vertices[a])
				smooth[weld[a]] += face
				smooth[weld[b]] += face
				smooth[weld[c]] += face
		for id: int in smooth.size():
			smooth[id] = smooth[id].normalized()
		if round_index == passes:
			break
		for s: int in layer.size():
			var vertices: PackedVector3Array = layer[s][Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = layer[s][Mesh.ARRAY_INDEX]
			var weld := welds[s]
			for at: int in range(0, indices.size() - 2, 3):
				var a := indices[at]
				var b := indices[at + 1]
				var c := indices[at + 2]
				var face := (vertices[c] - vertices[a]).cross(vertices[b] - vertices[a])
				if face.dot(smooth[weld[a]] + smooth[weld[b]] + smooth[weld[c]]) < 0.0:
					indices[at + 1] = c
					indices[at + 2] = b
			layer[s][Mesh.ARRAY_INDEX] = indices
	for s: int in layer.size():
		var stored: PackedVector3Array = layer[s][Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = layer[s][Mesh.ARRAY_TANGENT]
		var weld := welds[s]
		var normals := PackedVector3Array()
		normals.resize(weld.size())
		for v: int in weld.size():
			var normal := smooth[weld[v]]
			if normal.length_squared() < 0.5:
				normal = stored[v].normalized()
			normals[v] = normal
			var tangent := Vector3(tangents[v * 4], tangents[v * 4 + 1], tangents[v * 4 + 2])
			tangent -= normal * normal.dot(tangent)
			if tangent.length_squared() < 1e-12:
				tangent = normal.cross(Vector3.UP if absf(normal.y) < 0.9 else Vector3.RIGHT)
			tangent = tangent.normalized()
			tangents[v * 4] = tangent.x
			tangents[v * 4 + 1] = tangent.y
			tangents[v * 4 + 2] = tangent.z
		layer[s][Mesh.ARRAY_NORMAL] = normals
		layer[s][Mesh.ARRAY_TANGENT] = tangents

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
	var built: Array = []
	var linings: Array[bool] = []
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
				or (arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array).size() != count * 8 \
				or (arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array).size() != count \
				or (arrays[Mesh.ARRAY_TANGENT] as PackedFloat32Array).size() != count * 4 \
				or int(surface.get("primitive", Mesh.PRIMITIVE_TRIANGLES)) != Mesh.PRIMITIVE_TRIANGLES:
			return null
		built.append(arrays)
		linings.append(is_lining(surface))
	shade(built, linings)
	for i: int in built.size():
		var arrays: Array = built[i]
		# After the welded shading this turns only the few triangles a fold
		# still leaves facing against their corners.
		arrays[Mesh.ARRAY_INDEX] = wound(arrays[Mesh.ARRAY_INDEX], arrays[Mesh.ARRAY_VERTEX],
			arrays[Mesh.ARRAY_NORMAL], linings[i])
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {},
			Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
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

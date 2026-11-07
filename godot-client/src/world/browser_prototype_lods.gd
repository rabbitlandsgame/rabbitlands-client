extends RefCounted
## Optional portable index-only WD-C5 result. Native loads keep their existing
## generator. Browser files are packaged beside the original prototype GLB.
const Classes := preload("res://src/world/world_distance_classes.gd")
const SCHEMA := 1
const POLICY := "rl-browser-prototype-lods-v1"
const SUFFIX := ".browser-lods.json"
const MAX_BYTES := 16 * 1024 * 1024
const MAX_SURFACES := 256
const MAX_LEVELS := 32
static var _base64 := RegEx.create_from_string("^[A-Za-z0-9+/]*={0,2}$")

static func engine_identity() -> String:
	return str(Engine.get_version_info().string)

static func generation() -> Dictionary:
	return {"minimum_triangles": Classes.LOD_MIN_TRIANGLES,
		"minimum_radius": Classes.LOD_MIN_RADIUS,
		"normal_merge_angle": Classes.LOD_NORMAL_MERGE_ANGLE,
		"normal_split_angle": Classes.LOD_NORMAL_SPLIT_ANGLE}

static func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	if not bytes.is_empty(): hash.update(bytes)
	return hash.finish().hex_encode()

static func is_digest(value: Variant) -> bool:
	return value is String and value.length() == 64 and value == value.to_lower() \
		and value.is_valid_hex_number(false) and not value.begins_with("+") and not value.begins_with("-")

static func _integer(value: Variant, low: int, high: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) \
		and float(value) == floorf(float(value)) and float(value) >= low and float(value) <= high

static func _keys(value: Variant, expected: Array[String]) -> bool:
	if not value is Dictionary or value.size() != expected.size(): return false
	for key: String in expected:
		if not value.has(key): return false
	return true

static func _indices(mesh: ImporterMesh, surface: int) -> PackedInt32Array:
	var value: Variant = mesh.get_surface_arrays(surface)[Mesh.ARRAY_INDEX]
	return value if value is PackedInt32Array else PackedInt32Array()

## The same CPU gate as ExternalMeshPool.lod_shape; keeping it here also lets
## the offline producer run without initializing any gameplay/autoload nodes.
static func shape(mesh: ImporterMesh) -> Dictionary:
	var triangles := 0
	var lists: Array[PackedVector3Array] = []
	for surface: int in mesh.get_surface_count():
		if mesh.get_surface_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: continue
		var arrays := mesh.get_surface_arrays(surface)
		var vertices: Variant = arrays[Mesh.ARRAY_VERTEX]
		if not vertices is PackedVector3Array: continue
		var indices: Variant = arrays[Mesh.ARRAY_INDEX]
		triangles += indices.size() / 3 if indices is PackedInt32Array else vertices.size() / 3
		lists.append(vertices)
	if triangles < Classes.LOD_MIN_TRIANGLES: return {"triangles": triangles, "radius": 0.0}
	var low := Vector3.INF
	var high := -Vector3.INF
	var enough := pow(Classes.LOD_MIN_RADIUS * 2.0, 2.0)
	var seen := 0
	for vertices: PackedVector3Array in lists:
		for vertex: Vector3 in vertices:
			low = low.min(vertex)
			high = high.max(vertex)
			seen += 1
			if seen % 64 == 0 and (high - low).length_squared() >= enough: break
		if (high - low).length_squared() >= enough: break
	var size := high - low
	return {"triangles": triangles, "radius": size.length() * 0.5 if size.is_finite() else 0.0}

static func qualifies(mesh: ImporterMesh) -> bool:
	var found := shape(mesh)
	return Classes.generates_lods(int(found.triangles), float(found.radius))

## Called only by the offline producer after the ordinary WD-C5 generation.
static func document(mesh: ImporterMesh, source_sha256: String, source_bytes: int) -> Dictionary:
	var surfaces: Array = []
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.get_surface_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices := _indices(mesh, surface)
		var lods: Array = []
		for level: int in mesh.get_surface_lod_count(surface):
			var next := mesh.get_surface_lod_indices(surface, level)
			lods.append({"edge": mesh.get_surface_lod_size(surface, level), "count": next.size(),
				"indices": Marshalls.raw_to_base64(next.to_byte_array())})
		surfaces.append({"primitive": mesh.get_surface_primitive_type(surface),
			"vertex_count": vertices.size(), "vertex_sha256": digest(vertices.to_byte_array()),
			"index_count": indices.size(), "index_sha256": digest(indices.to_byte_array()), "lods": lods})
	return {"schema": SCHEMA, "policy": POLICY, "engine": engine_identity(),
		"source_sha256": source_sha256, "source_bytes": source_bytes, "generation": generation(),
		"mesh": {"name": str(mesh.resource_name), "surfaces": surfaces}}

## A supplied digest is the WorldLoader's already-verified externalMeshes
## identity. Standalone callers without that proof hash only when a sidecar
## exists and the pool is actually parsing a new mesh; no digest/source cache
## survives the existing weak mesh's lifetime or a source-group retirement.
static func apply_file(mesh: ImporterMesh, path: String, verified_sha256 := "",
		browser := OS.has_feature("web")) -> Dictionary:
	if not browser: return {"applied": false, "reason": "native"}
	var sidecar := FileAccess.open(path + SUFFIX, FileAccess.READ)
	if sidecar == null: return {"applied": false, "reason": "missing"}
	if sidecar.get_length() <= 0 or sidecar.get_length() > MAX_BYTES:
		return {"applied": false, "reason": "size"}
	var text := sidecar.get_as_text()
	var parser := JSON.new()
	if parser.parse(text) != OK: return {"applied": false, "reason": "json"}
	var source := FileAccess.open(path, FileAccess.READ)
	if source == null: return {"applied": false, "reason": "source_missing"}
	var bytes := source.get_length()
	var identity := verified_sha256 if is_digest(verified_sha256) else FileAccess.get_sha256(path)
	return apply_document(mesh, parser.data, identity, bytes)

## Validate the entire sidecar before modifying a single surface. Boolean
## failure always leaves the ImporterMesh ready for the original generator.
static func apply_document(mesh: ImporterMesh, data: Variant, source_sha256: String,
		source_bytes: int) -> Dictionary:
	var checked := _validate(mesh, data, source_sha256, source_bytes)
	if not checked.get("ok", false):
		return {"applied": false, "reason": checked.get("reason", "header")}
	var original := _capture(mesh)
	var changed: Array = original.surfaces.duplicate()
	for surface: int in changed.size():
		changed[surface] = (changed[surface] as Dictionary).duplicate()
		changed[surface].lods = checked.surfaces[surface]
	if not _fill(mesh, original, changed):
		_fill(mesh, original, original.surfaces)
		return {"applied": false, "reason": "rebuild"}
	return {"applied": true, "reason": "hit", "levels": checked.levels}

static func _validate(mesh: ImporterMesh, data: Variant, identity: String, bytes: int) -> Dictionary:
	if mesh == null or not is_digest(identity) \
			or not _keys(data, ["schema", "policy", "engine", "source_sha256", "source_bytes", "generation", "mesh"]): return {"reason": "header"}
	if not _integer(data.schema, SCHEMA, SCHEMA) or data.policy != POLICY or data.engine != engine_identity():
		return {"reason": "policy"}
	if data.source_sha256 != identity or not _integer(data.source_bytes, bytes, bytes): return {"reason": "source"}
	var policy := generation()
	if not data.generation is Dictionary or data.generation.size() != policy.size(): return {"reason": "generation"}
	for key: String in policy:
		if data.generation.get(key) != policy[key]: return {"reason": "generation"}
	if not _keys(data.mesh, ["name", "surfaces"]) or data.mesh.name != str(mesh.resource_name) \
			or not data.mesh.surfaces is Array or data.mesh.surfaces.size() != mesh.get_surface_count() \
			or mesh.get_surface_count() > MAX_SURFACES: return {"reason": "shape"}
	if not qualifies(mesh): return {"reason": "gate"}
	var planned: Array = []
	var levels := 0
	var decoded_bytes := 0
	for surface: int in mesh.get_surface_count():
		var row: Variant = data.mesh.surfaces[surface]
		if not _keys(row, ["primitive", "vertex_count", "vertex_sha256", "index_count", "index_sha256", "lods"]):
			return {"reason": "surface"}
		var arrays := mesh.get_surface_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var base := _indices(mesh, surface)
		if not _integer(row.primitive, mesh.get_surface_primitive_type(surface), mesh.get_surface_primitive_type(surface)) \
				or not _integer(row.vertex_count, vertices.size(), vertices.size()) \
				or not _integer(row.index_count, base.size(), base.size()) \
				or row.index_sha256 != digest(base.to_byte_array()) \
				or row.vertex_sha256 != digest(vertices.to_byte_array()) \
				or not row.lods is Array or row.lods.size() > MAX_LEVELS: return {"reason": "base"}
		var lods := {}
		var previous_edge := 0.0
		var previous_count := base.size() if not base.is_empty() else vertices.size()
		for level: Variant in row.lods:
			if not _keys(level, ["edge", "count", "indices"]) or not (level.edge is float or level.edge is int) \
					or not is_finite(float(level.edge)) or float(level.edge) <= previous_edge \
					or not _integer(level.count, 3, previous_count - 1) or int(level.count) % 3 != 0 \
					or not level.indices is String or level.indices.length() != 4 * ceili(float(level.count) * 4.0 / 3.0) \
					or _base64.search(level.indices) == null:
				return {"reason": "lod"}
			decoded_bytes += int(level.count) * 4
			if decoded_bytes > MAX_BYTES: return {"reason": "budget"}
			var packed := Marshalls.base64_to_raw(level.indices)
			if packed.size() != int(level.count) * 4 or Marshalls.raw_to_base64(packed) != level.indices: return {"reason": "encoding"}
			var indices := packed.to_int32_array()
			for index: int in indices:
				if index < 0 or index >= vertices.size(): return {"reason": "index"}
			lods[float(level.edge)] = indices
			previous_edge = float(level.edge)
			previous_count = indices.size()
			levels += 1
		planned.append(lods)
	return {"ok": levels > 0, "reason": "empty", "surfaces": planned, "levels": levels}

static func _capture(mesh: ImporterMesh) -> Dictionary:
	var names := PackedStringArray()
	for shape_index: int in mesh.get_blend_shape_count(): names.append(mesh.get_blend_shape_name(shape_index))
	var surfaces: Array = []
	for surface: int in mesh.get_surface_count():
		var shapes: Array[Array] = []
		for shape_index: int in mesh.get_blend_shape_count(): shapes.append(mesh.get_surface_blend_shape_arrays(surface, shape_index))
		var lods := {}
		for level: int in mesh.get_surface_lod_count(surface): lods[mesh.get_surface_lod_size(surface, level)] = mesh.get_surface_lod_indices(surface, level)
		surfaces.append({"primitive": mesh.get_surface_primitive_type(surface), "arrays": mesh.get_surface_arrays(surface),
			"shapes": shapes, "lods": lods, "material": mesh.get_surface_material(surface),
			"name": mesh.get_surface_name(surface), "flags": mesh.get_surface_format(surface)})
	return {"names": names, "mode": mesh.get_blend_shape_mode(), "lightmap": mesh.get_lightmap_size_hint(), "surfaces": surfaces}

static func _fill(mesh: ImporterMesh, original: Dictionary, surfaces: Array) -> bool:
	mesh.clear()
	for name: String in original.names: mesh.add_blend_shape(name)
	mesh.set_blend_shape_mode(original.mode)
	mesh.set_lightmap_size_hint(original.lightmap)
	for surface: Dictionary in surfaces:
		mesh.add_surface(surface.primitive, surface.arrays, surface.shapes, surface.lods,
			surface.material, surface.name, surface.flags)
	return mesh.get_surface_count() == surfaces.size()

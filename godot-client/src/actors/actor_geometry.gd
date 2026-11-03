extends RefCounted
## Runtime applier for package-time actor geometry (actor LODs, wave 2).
##
## `apply(state, path)` runs on a parsed GLTFState of an actor glTF, after the
## parse and before generate_scene(). When the catalogue lists the file and its
## sidecar validates against this exact parse, each changed ImporterMesh is
## rebuilt with the sidecar's base indices, vertex compaction and LOD index
## chains; every other surface keeps its parsed arrays. Anything that does not
## validate leaves the state exactly as parsed (fail closed to the plain parse)
## and is counted; a mismatch is logged once per file. Format and catalogue:
## actor_geometry_format.gd.
##
## Validation, in order: catalogue entry for the logical path; the sidecar's
## size and SHA-256 against the catalogue, hashed as it is consumed; decode and
## structure; engine build; the sidecar's source against the entry; with the
## catalogue's `source_check` "file" (the default), the actor file's SHA-256
## (or the caller's hash of the bytes it parsed) against the entry; mesh count,
## names and surface counts; per surface vertex and index counts, and for every
## surface it changes the SHA-256 of the parsed index buffer.
##
## Threads: CPU only, no RenderingServer or scene calls. The memoized catalogue
## and the counters sit behind one Mutex, so the creature worker and the
## main-thread equipment parse share it.
##
## RABBITLANDS_ACTOR_GEOMETRY=sidecar (default) | off | generate. `generate`
## runs ImporterMesh.generate_lods at parse time; it is for developers on the
## editor binary only and never takes effect in an exported build.
## RABBITLANDS_ACTOR_GEOMETRY_ROOT names the catalogue folder (tests, measuring
## a cook). Otherwise an editor checkout reads the ignored dev root
## `<client repo>/.local/actor-geometry/<policy>/`; the installed release root
## arrives with release packaging (actor LODs C9).

const Format := preload("res://src/actors/actor_geometry_format.gd")
const PreparedContent := preload("res://src/world/prepared_content.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")

const MODE_ENVIRONMENT := "RABBITLANDS_ACTOR_GEOMETRY"
const ROOT_ENVIRONMENT := "RABBITLANDS_ACTOR_GEOMETRY_ROOT"
const MODES: Array[String] = ["sidecar", "off", "generate"]
const DEFAULT_MODE := "sidecar"
const DEV_ROOT := "res://../.local/actor-geometry"
## ImporterMesh.generate_lods arguments of the dev-only `generate` mode (the
## cook's own policy lives in tools/actor_geometry/).
const GENERATE_MERGE_ANGLE := 60.0
const GENERATE_SPLIT_ANGLE := 25.0
const LOGGED_LIMIT := 256
## Mismatches that are routine rather than worth a log line.
const QUIET_REASONS: Array[String] = ["not_listed"]

static var _mutex := Mutex.new()
static var _config: Dictionary = {}
static var _statuses: Dictionary = {}
static var _reasons: Dictionary = {}
static var _logged: Dictionary = {}
static var _surfaces_rebuilt := 0
static var _lod_levels := 0
static var _usec_total := 0
static var _usec_max := 0

## Applies the listed sidecar to `state`, the parse of `path` (a res:// or
## absolute actor path). `source_sha256`, when the caller hashed the bytes it
## parsed, replaces the applier's own file hash. Returns {status, reason,
## path, surfaces, lods, usec}; status is applied, unchanged, generated,
## skipped (off, out_of_scope, no_catalog) or rejected (with the reason).
static func apply(state: GLTFState, path: String, source_sha256 := "") -> Dictionary:
	var began := Time.get_ticks_usec()
	var config := _configuration()
	var mode: String = config.mode
	if mode == "off":
		return _finish(began, "skipped", "off", "")
	var key := logical_path(path)
	if key.is_empty():
		return _finish(began, "skipped", "out_of_scope", "")
	if state == null:
		return _finish(began, "rejected", "state", key)
	if mode == "generate":
		return _generate(state, key, began)
	if str(config.status) == "absent":
		return _finish(began, "skipped", "no_catalog", key)
	if str(config.status) != "ready":
		# Logged once when the catalogue was read, not again per file.
		return _finish(began, "rejected", str(config.reason), key, 0, 0, true)
	var catalog: Dictionary = config.catalog
	var entry: Variant = (catalog.entries as Dictionary).get(key)
	if entry == null:
		return _finish(began, "rejected", "not_listed", key)
	if not Format.validate_entry(entry).is_empty():
		return _finish(began, "rejected", "catalog", key)
	var read := _read_sidecar(str(config.root), entry)
	if read.has("error"):
		return _finish(began, "rejected", str(read.error), key)
	var sidecar: Dictionary = read.sidecar
	if str(sidecar.engine) != Format.engine_identity():
		return _finish(began, "rejected", "engine", key)
	var source: Dictionary = sidecar.source
	if str(source.path) != key or str(source.sha256) != str(entry.source_sha256) \
			or int(source.bytes) != int(entry.source_bytes):
		return _finish(began, "rejected", "catalog", key)
	if not source_sha256.is_empty() or str(catalog.get("source_check", Format.DEFAULT_SOURCE_CHECK)) == "file":
		var actual := source_sha256 if not source_sha256.is_empty() else CreaturePayload.source_sha256(path)
		if actual != str(entry.source_sha256):
			return _finish(began, "rejected", "source", key)
	var plan := _bind(state, sidecar)
	if plan.has("error"):
		return _finish(began, "rejected", str(plan.error), key)
	if not _rebuild_all(plan.meshes):
		return _finish(began, "rejected", "rebuild", key)
	var rebuilt := 0
	var levels := 0
	for mesh_plan: Dictionary in plan.meshes:
		rebuilt += int(mesh_plan.changed)
		levels += int(mesh_plan.levels)
	return _finish(began, "applied" if rebuilt > 0 else "unchanged", "", key, rebuilt, levels)

## The res:// path the catalogue lists `path` under, or "" when the file is not
## an actor glTF the cook covers (RL heads, world objects, external files).
static func logical_path(path: String) -> String:
	var logical := PreparedContent.logical_source(path)
	if not logical.begins_with("godot-client/"):
		return ""
	var key := "res://" + logical.trim_prefix("godot-client/")
	return key if Format.in_scope(key) else ""

## The catalogue folder this process reads, or "" when there is none to read.
static func catalog_root() -> String:
	var override := OS.get_environment(ROOT_ENVIRONMENT).strip_edges()
	if not override.is_empty():
		return ProjectSettings.globalize_path(override).replace("\\", "/").simplify_path()
	if OS.has_feature("editor"):
		return ProjectSettings.globalize_path(DEV_ROOT.path_join(Format.POLICY)).replace("\\", "/").simplify_path()
	return ""

## Reads the catalogue now (off the main thread, for example) instead of on
## the first actor parse. Returns its status: ready, absent or rejected.
static func warm() -> String:
	return str(_configuration().status)

## Forgets the memoized mode and catalogue and zeroes the counters. The
## catalogue is otherwise read once per process: its entries only point at
## sidecars, and each sidecar is hashed and bound to the parse it changes.
static func reset() -> void:
	_mutex.lock()
	_config = {}
	_statuses = {}
	_reasons = {}
	_logged = {}
	_surfaces_rebuilt = 0
	_lod_levels = 0
	_usec_total = 0
	_usec_max = 0
	_mutex.unlock()

## Counters for diagnostics and benchmarks.
static func snapshot() -> Dictionary:
	_mutex.lock()
	var result := {"mode": str(_config.get("mode", "")), "root": str(_config.get("root", "")),
		"catalog": str(_config.get("status", "unread")), "catalog_reason": str(_config.get("reason", "")),
		"entries": (_config.get("catalog", {}).get("entries", {}) as Dictionary).size() if _config.get("catalog") is Dictionary else 0,
		"statuses": _statuses.duplicate(), "reasons": _reasons.duplicate(),
		"surfaces_rebuilt": _surfaces_rebuilt, "lod_levels": _lod_levels,
		"apply_usec_total": _usec_total, "apply_usec_max": _usec_max}
	_mutex.unlock()
	return result

static func _configuration() -> Dictionary:
	_mutex.lock()
	if _config.is_empty():
		_config = _load_configuration()
	var config := _config
	_mutex.unlock()
	return config

## The mode a RABBITLANDS_ACTOR_GEOMETRY value selects, as {mode, rejected}:
## only the three mode names count (trimmed, lower-cased); any other non-empty
## value, and `generate` outside the editor binary, is the default and is
## returned in "rejected". HardwareTier.resolve_actor_geometry reports the same
## choice in the startup record; the test holds the two to each other.
static func resolve_mode(value: String, editor: bool) -> Dictionary:
	var text := value.strip_edges().to_lower()
	if text.is_empty():
		return {"mode": DEFAULT_MODE, "rejected": ""}
	if not text in MODES or (text == "generate" and not editor):
		return {"mode": DEFAULT_MODE, "rejected": text}
	return {"mode": text, "rejected": ""}

static func _load_configuration() -> Dictionary:
	var resolved := resolve_mode(OS.get_environment(MODE_ENVIRONMENT), OS.has_feature("editor"))
	var mode := str(resolved.mode)
	if str(resolved.rejected) == "generate":
		push_warning("actor geometry: generate mode is editor-only; using %s" % mode)
	elif not str(resolved.rejected).is_empty():
		push_warning("actor geometry: unknown %s=%s, using %s" % [MODE_ENVIRONMENT, resolved.rejected, mode])
	var root := catalog_root()
	var config := {"mode": mode, "root": root, "status": "absent", "reason": "", "catalog": {}}
	if mode != "sidecar" or root.is_empty():
		return config
	var path := root.path_join(Format.CATALOG_FILE)
	if not FileAccess.file_exists(path):
		return config
	config.status = "rejected"
	config.reason = "catalog"
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() > Format.MAX_CATALOG_BYTES:
		push_warning("actor geometry: unreadable or oversized catalogue %s" % path)
		return config
	var text := file.get_buffer(file.get_length()).get_string_from_utf8()
	file.close()
	var parser := JSON.new()
	if parser.parse(text) != OK or not Format.validate_catalog(parser.data).is_empty():
		push_warning("actor geometry: invalid catalogue %s" % path)
		return config
	var catalog: Dictionary = parser.data
	if str(catalog.engine) != Format.engine_identity():
		config.reason = "engine"
		push_warning("actor geometry: catalogue %s was cooked for %s, not %s" % [
			path, str(catalog.engine), Format.engine_identity()])
		return config
	config.status = "ready"
	config.reason = ""
	config.catalog = catalog
	return config

static func _read_sidecar(root: String, entry: Dictionary) -> Dictionary:
	var path := root.path_join(str(entry.sidecar))
	if not FileAccess.file_exists(path):
		return {"error": "sidecar_missing"}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"error": "sidecar_missing"}
	if file.get_length() != int(entry.sidecar_bytes):
		return {"error": "sidecar_digest"}
	var bytes := file.get_buffer(file.get_length())
	file.close()
	if bytes.size() != int(entry.sidecar_bytes) or Format.sha256_hex(bytes) != str(entry.sidecar_sha256):
		return {"error": "sidecar_digest"}
	var decoded := Format.decode(bytes)
	return {"error": "decode"} if decoded.has("error") else decoded

## Checks the sidecar against this parse without changing it. Returns
## {meshes: [{mesh, surfaces, changed, levels}]} (meshes with a changed
## surface only; `changed` counts those surfaces) or {error}.
static func _bind(state: GLTFState, sidecar: Dictionary) -> Dictionary:
	var meshes: Array = state.get_meshes()
	var plans: Array = sidecar.meshes
	if meshes.size() != plans.size():
		return {"error": "shape"}
	var bound: Array = []
	for mesh_index: int in meshes.size():
		var gltf_mesh := meshes[mesh_index] as GLTFMesh
		var mesh: ImporterMesh = gltf_mesh.mesh if gltf_mesh != null else null
		var mesh_plan: Dictionary = plans[mesh_index]
		var surfaces: Array = mesh_plan.surfaces
		if mesh == null or str(mesh.resource_name) != str(mesh_plan.name) \
				or mesh.get_surface_count() != surfaces.size():
			return {"error": "shape"}
		var changed := 0
		var levels := 0
		for surface_index: int in surfaces.size():
			var plan: Dictionary = surfaces[surface_index]
			var arrays := mesh.get_surface_arrays(surface_index)
			var vertices: Variant = arrays[Mesh.ARRAY_VERTEX]
			var indices: Variant = arrays[Mesh.ARRAY_INDEX]
			var vertex_count := (vertices as PackedVector3Array).size() if vertices is PackedVector3Array else 0
			var index_buffer: PackedInt32Array = indices if indices is PackedInt32Array else PackedInt32Array()
			if vertex_count != int(plan.vertex_count) or index_buffer.size() != int(plan.index_count):
				return {"error": "surface"}
			if not Format.changes_surface(plan):
				continue
			if mesh.get_surface_primitive_type(surface_index) != Mesh.PRIMITIVE_TRIANGLES \
					or Format.index_digest(index_buffer) != str(plan.index_digest):
				return {"error": "surface"}
			if plan.has("compact_runs") and not _compactable(mesh, surface_index, arrays, vertex_count):
				return {"error": "surface"}
			changed += 1
			levels += (plan.lods as Array).size()
		if changed > 0:
			bound.append({"mesh": mesh, "surfaces": surfaces, "changed": changed, "levels": levels})
	return {"meshes": bound}

## Every per-vertex array (and blend shape array) of the surface divides evenly
## by its vertex count, so runs can slice it.
static func _compactable(mesh: ImporterMesh, surface: int, arrays: Array, vertex_count: int) -> bool:
	var sources: Array = [arrays]
	for shape: int in mesh.get_blend_shape_count():
		sources.append(mesh.get_surface_blend_shape_arrays(surface, shape))
	for source_arrays: Array in sources:
		for slot: int in mini(source_arrays.size(), Mesh.ARRAY_MAX):
			var values: Variant = source_arrays[slot]
			if slot == Mesh.ARRAY_INDEX or values == null:
				continue
			if not _packed(values) or values.size() % vertex_count != 0:
				return false
	return true

static func _packed(value: Variant) -> bool:
	return typeof(value) in [TYPE_PACKED_BYTE_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_INT64_ARRAY,
		TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY, TYPE_PACKED_VECTOR2_ARRAY,
		TYPE_PACKED_VECTOR3_ARRAY, TYPE_PACKED_COLOR_ARRAY, TYPE_PACKED_VECTOR4_ARRAY]

## Rebuilds every bound mesh. ImporterMesh has no per-surface setter, so all
## surfaces of a changed mesh are re-added: unchanged ones with their own
## arrays, blend shapes, LODs, material, name and flags. If the engine refuses
## a surface, every mesh rebuilt so far gets its parsed surfaces back.
static func _rebuild_all(bound: Array) -> bool:
	var captured: Array[Dictionary] = []
	for mesh_plan: Dictionary in bound:
		var mesh: ImporterMesh = mesh_plan.mesh
		var original := _capture(mesh)
		captured.append(original)
		var planned: Array[Dictionary] = []
		for surface: int in (original.surfaces as Array).size():
			var plan: Dictionary = mesh_plan.surfaces[surface]
			planned.append(_planned(original.surfaces[surface], plan) if Format.changes_surface(plan)
				else original.surfaces[surface])
		if not _fill(mesh, original, planned):
			for index: int in captured.size():
				_fill(bound[index].mesh, captured[index], captured[index].surfaces)
			return false
	return true

static func _capture(mesh: ImporterMesh) -> Dictionary:
	var shape_names := PackedStringArray()
	for shape: int in mesh.get_blend_shape_count():
		shape_names.append(mesh.get_blend_shape_name(shape))
	var surfaces: Array[Dictionary] = []
	for surface: int in mesh.get_surface_count():
		surfaces.append(_surface(mesh, surface))
	return {"shape_names": shape_names, "shape_mode": mesh.get_blend_shape_mode(),
		"lightmap_hint": mesh.get_lightmap_size_hint(), "surfaces": surfaces}

static func _surface(mesh: ImporterMesh, surface: int) -> Dictionary:
	var shapes: Array[Array] = []
	for shape: int in mesh.get_blend_shape_count():
		shapes.append(mesh.get_surface_blend_shape_arrays(surface, shape))
	var lods := {}
	for level: int in mesh.get_surface_lod_count(surface):
		lods[mesh.get_surface_lod_size(surface, level)] = mesh.get_surface_lod_indices(surface, level)
	return {"primitive": mesh.get_surface_primitive_type(surface), "arrays": mesh.get_surface_arrays(surface),
		"shapes": shapes, "lods": lods, "material": mesh.get_surface_material(surface),
		"name": mesh.get_surface_name(surface), "flags": mesh.get_surface_format(surface)}

## The planned surface. Never writes into the parsed arrays (ImporterMesh
## returns its own Array, not a copy). Parsed LODs are dropped with any change:
## they index the parsed base.
static func _planned(original: Dictionary, plan: Dictionary) -> Dictionary:
	var arrays: Array = (original.arrays as Array).duplicate()
	var shapes: Array[Array] = original.shapes
	if plan.has("compact_runs"):
		var runs: PackedInt32Array = plan.compact_runs
		var vertex_count := (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		arrays = _compact(arrays, runs, vertex_count)
		var compacted: Array[Array] = []
		for shape: Array in shapes:
			compacted.append(_compact(shape, runs, vertex_count))
		shapes = compacted
	if plan.has("base"):
		arrays[Mesh.ARRAY_INDEX] = plan.base
	var lods := {}
	for level: Array in plan.lods:
		lods[float(level[0])] = level[1]
	var planned := original.duplicate()
	planned.arrays = arrays
	planned.shapes = shapes
	planned.lods = lods
	return planned

static func _compact(arrays: Array, runs: PackedInt32Array, vertex_count: int) -> Array:
	var out := arrays.duplicate()
	for slot: int in mini(out.size(), Mesh.ARRAY_MAX):
		if slot != Mesh.ARRAY_INDEX and out[slot] != null:
			out[slot] = _gather(out[slot], runs, vertex_count)
	return out

## Concatenates the kept runs of one per-vertex array (any packed type; the
## stride is its size per vertex: 4 for tangents or 4-weight bones).
static func _gather(values: Variant, runs: PackedInt32Array, vertex_count: int) -> Variant:
	var stride: int = values.size() / vertex_count
	var out: Variant = values.slice(0, 0)
	var index := 0
	var count := runs.size()
	while index < count:
		var start: int = runs[index] * stride
		out.append_array(values.slice(start, start + runs[index + 1] * stride))
		index += 2
	return out

static func _fill(mesh: ImporterMesh, captured: Dictionary, surfaces: Array) -> bool:
	mesh.clear() # Also drops the blend shape names, which add_surface checks.
	for shape_name: String in captured.shape_names:
		mesh.add_blend_shape(shape_name)
	mesh.set_blend_shape_mode(captured.shape_mode)
	mesh.set_lightmap_size_hint(captured.lightmap_hint)
	for surface: Dictionary in surfaces:
		mesh.add_surface(surface.primitive, surface.arrays, surface.shapes, surface.lods,
			surface.material, surface.name, surface.flags)
	return mesh.get_surface_count() == surfaces.size()

static func _generate(state: GLTFState, key: String, began: int) -> Dictionary:
	var surfaces := 0
	var levels := 0
	for gltf_mesh_value: Variant in state.get_meshes():
		var gltf_mesh := gltf_mesh_value as GLTFMesh
		var mesh: ImporterMesh = gltf_mesh.mesh if gltf_mesh != null else null
		if mesh == null or mesh.get_surface_count() == 0:
			continue
		mesh.generate_lods(GENERATE_MERGE_ANGLE, GENERATE_SPLIT_ANGLE, [])
		for surface: int in mesh.get_surface_count():
			var surface_levels := mesh.get_surface_lod_count(surface)
			surfaces += int(surface_levels > 0)
			levels += surface_levels
	return _finish(began, "generated", "", key, surfaces, levels)

static func _finish(began: int, status: String, reason: String, key: String, surfaces := 0,
		levels := 0, quiet := false) -> Dictionary:
	var elapsed := Time.get_ticks_usec() - began
	var log_line := false
	_mutex.lock()
	_statuses[status] = int(_statuses.get(status, 0)) + 1
	if not reason.is_empty():
		_reasons[reason] = int(_reasons.get(reason, 0)) + 1
	_surfaces_rebuilt += surfaces
	_lod_levels += levels
	_usec_total += elapsed
	_usec_max = maxi(_usec_max, elapsed)
	if status == "rejected" and not quiet and not reason in QUIET_REASONS and not _logged.has(key) \
			and _logged.size() < LOGGED_LIMIT:
		_logged[key] = reason
		log_line = true
	_mutex.unlock()
	if log_line:
		push_warning("actor geometry: %s kept as parsed (%s)" % [key, reason])
	return {"status": status, "reason": reason, "path": key, "surfaces": surfaces, "lods": levels,
		"usec": elapsed}

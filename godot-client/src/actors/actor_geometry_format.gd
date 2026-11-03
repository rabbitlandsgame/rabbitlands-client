extends RefCounted
## Actor geometry sidecars (actor LODs, wave 2): the schema, serialisation and
## validation shared by the package-time cook (tools/actor_geometry/) and the
## runtime applier (src/actors/actor_geometry.gd). Docs: actor-geometry-lods.md.
##
## A sidecar carries index-only changes for the surfaces of ONE actor glTF as
## GLTFDocument parses it at runtime: a replacement base index buffer (hidden
## lining faces removed), an optional vertex compaction by kept runs, and LOD
## index chains. Vertex buffers are never rewritten, only compacted by runs, so
## every derivation that reads the parsed arrays keeps working.
##
## Sidecar file `blobs/<sha256>.rlgeo`: the 8-byte magic, the decoded size as a
## little-endian u64, then zstd(var_to_bytes(Dictionary)). Read back with
## bytes_to_var (never objects). The Dictionary:
##   {schema: 1, policy: POLICY, engine: engine_identity(),
##    source: {path: "res://assets/actors/native/...glb", sha256, bytes},
##    meshes: [{name, surfaces: [{vertex_count, index_count, index_digest,
##      base?: PackedInt32Array, compact_runs?: PackedInt32Array,
##      lods: [[edge_length, PackedInt32Array], ...]}]}]}
## `meshes` follows GLTFState.get_meshes() order. `index_digest` is the SHA-256
## of the parsed index buffer (PackedInt32Array.to_byte_array()). With
## `compact_runs` ([start, length] pairs of original vertices, ascending and
## disjoint) `base` and `lods` index the compacted vertex order. LOD edge
## lengths ascend strictly and every level is smaller than the one before it
## (Godot ignores a level that is not smaller than the base).
##
## Catalogue `catalog.json` in the same root:
##   {schema, policy, engine, source_check: "file"|"parsed",
##    entries: {<res:// logical path>: {source_sha256, source_bytes, sidecar:
##      "blobs/<sidecar_sha256>.rlgeo", sidecar_sha256, sidecar_bytes, inputs?}}}
## `source_check` "file" (the default) makes the runtime hash the actor file
## against `source_sha256`; "parsed" relies on the parsed index digests, for a
## root installed and verified together with the actor files.

const SCHEMA := 1
const POLICY := "rl-actor-geometry-v1"
const MAGIC := "RLGEO001"
const HEADER_BYTES := 16
const MAX_RAW_BYTES := 32 * 1024 * 1024
const MAX_ENCODED_BYTES := 32 * 1024 * 1024
const MAX_CATALOG_BYTES := 64 * 1024 * 1024
const CATALOG_FILE := "catalog.json"
const BLOB_FOLDER := "blobs"
const EXTENSION := "rlgeo"
const SOURCE_ROOT := "res://assets/actors/native/"
## Authored LODs of their own (RL heads) are never cooked.
const EXCLUDED_ROOTS: Array[String] = ["res://assets/actors/native/rl_heads/"]
const SOURCE_CHECKS: Array[String] = ["file", "parsed"]
const DEFAULT_SOURCE_CHECK := "file"
const MAX_LOD_LEVELS := 8
## Keys a v1 surface may carry. Anything else (a later stage's `replace`) is
## rejected rather than ignored, so an older runtime never half-applies a plan.
const SURFACE_KEYS: Array[String] = ["vertex_count", "index_count", "index_digest",
	"base", "compact_runs", "lods"]
const MESH_KEYS: Array[String] = ["name", "surfaces"]

## The exact engine build that parses at runtime, for example
## "4.7.2.stable.official.ed1daf0bf". Editor and export templates of one release
## share it; any engine change rejects every sidecar until the cook reruns.
static func engine_identity() -> String:
	var version := Engine.get_version_info()
	var parts := PackedStringArray(["%d.%d.%d" % [int(version.major), int(version.minor),
		int(version.patch)], str(version.status), str(version.build)])
	var commit := str(version.get("hash", "")).left(9)
	if not commit.is_empty():
		parts.append(commit)
	return ".".join(parts)

static func sha256_hex(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	if not bytes.is_empty():
		hashing.update(bytes)
	return hashing.finish().hex_encode()

static func index_digest(indices: PackedInt32Array) -> String:
	return sha256_hex(indices.to_byte_array())

static func is_digest(value: Variant) -> bool:
	if not value is String:
		return false
	var text: String = value
	return text.length() == 64 and text == text.to_lower() and text.is_valid_hex_number(false) \
		and not text.begins_with("+") and not text.begins_with("-")

## True for an actor glTF the cook covers, given its res:// logical path.
static func in_scope(logical_path: String) -> bool:
	if not logical_path.begins_with(SOURCE_ROOT) or logical_path != logical_path.simplify_path():
		return false
	if ".." in logical_path or "\\" in logical_path:
		return false
	for excluded: String in EXCLUDED_ROOTS:
		if logical_path.begins_with(excluded):
			return false
	return logical_path.get_extension().to_lower() in ["glb", "gltf"]

static func blob_path(sidecar_sha256: String) -> String:
	return "%s/%s.%s" % [BLOB_FOLDER, sidecar_sha256, EXTENSION]

## Counts and digest of one parsed surface (ImporterMesh.get_surface_arrays).
static func surface_record(arrays: Array) -> Dictionary:
	var vertices: Variant = arrays[Mesh.ARRAY_VERTEX] if arrays.size() == Mesh.ARRAY_MAX else null
	var indices: Variant = arrays[Mesh.ARRAY_INDEX] if arrays.size() == Mesh.ARRAY_MAX else null
	var index_buffer: PackedInt32Array = indices if indices is PackedInt32Array else PackedInt32Array()
	return {"vertex_count": (vertices as PackedVector3Array).size() if vertices is PackedVector3Array else 0,
		"index_count": index_buffer.size(), "index_digest": index_digest(index_buffer)}

static func encode(sidecar: Dictionary) -> PackedByteArray:
	var raw := var_to_bytes(sidecar)
	var out := MAGIC.to_ascii_buffer()
	var size := PackedByteArray()
	size.resize(8)
	size.encode_u64(0, raw.size())
	out.append_array(size)
	out.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))
	return out

## {"sidecar": Dictionary} for a valid sidecar, else {"error": reason}.
static func decode(bytes: PackedByteArray) -> Dictionary:
	if bytes.size() <= HEADER_BYTES or bytes.size() > MAX_ENCODED_BYTES + HEADER_BYTES:
		return {"error": "length"}
	if bytes.slice(0, MAGIC.length()).get_string_from_ascii() != MAGIC:
		return {"error": "magic"}
	var raw_size := bytes.decode_u64(MAGIC.length())
	if raw_size <= 0 or raw_size > MAX_RAW_BYTES:
		return {"error": "size"}
	var raw := bytes.slice(HEADER_BYTES).decompress(raw_size, FileAccess.COMPRESSION_ZSTD)
	if raw.size() != raw_size:
		return {"error": "zstd"}
	var value: Variant = bytes_to_var(raw)
	var problem := validate_sidecar(value)
	if not problem.is_empty():
		return {"error": problem}
	return {"sidecar": value}

## "" when `value` is a structurally valid v1 sidecar, else what is wrong.
## Bindings to an actual parse (engine, source, counts, digests) are the
## applier's; index ranges are checked here against the recorded counts.
static func validate_sidecar(value: Variant) -> String:
	if not value is Dictionary:
		return "not a dictionary"
	var sidecar: Dictionary = value
	if not sidecar.get("schema") is int or int(sidecar.schema) != SCHEMA:
		return "schema"
	if str(sidecar.get("policy", "")) != POLICY or not sidecar.get("policy") is String:
		return "policy"
	if not sidecar.get("engine") is String or str(sidecar.engine).is_empty():
		return "engine"
	var source: Variant = sidecar.get("source")
	if not source is Dictionary or not (source as Dictionary).get("path") is String \
			or not in_scope(str(source.path)) or not is_digest((source as Dictionary).get("sha256")) \
			or not (source as Dictionary).get("bytes") is int or int(source.bytes) < 0:
		return "source"
	var meshes: Variant = sidecar.get("meshes")
	if not meshes is Array or (meshes as Array).is_empty():
		return "meshes"
	for mesh_index: int in (meshes as Array).size():
		var mesh: Variant = meshes[mesh_index]
		if not mesh is Dictionary or not mesh.get("name") is String or not mesh.get("surfaces") is Array:
			return "mesh %d" % mesh_index
		for key: Variant in (mesh as Dictionary).keys():
			if not key in MESH_KEYS:
				return "mesh %d key %s" % [mesh_index, str(key)]
		var surfaces: Array = mesh.surfaces
		for surface_index: int in surfaces.size():
			var problem := validate_surface(surfaces[surface_index])
			if not problem.is_empty():
				return "mesh %d surface %d %s" % [mesh_index, surface_index, problem]
	return ""

static func validate_surface(value: Variant) -> String:
	if not value is Dictionary:
		return "not a dictionary"
	var surface: Dictionary = value
	for key: Variant in surface.keys():
		if not key in SURFACE_KEYS:
			return "unsupported key " + str(key)
	if not surface.get("vertex_count") is int or int(surface.vertex_count) <= 0:
		return "vertex_count"
	var index_count: Variant = surface.get("index_count")
	if not index_count is int or int(index_count) < 0 or int(index_count) % 3 != 0:
		return "index_count"
	if not is_digest(surface.get("index_digest")):
		return "index_digest"
	if not surface.get("lods") is Array or (surface.lods as Array).size() > MAX_LOD_LEVELS:
		return "lods"
	if changes_surface(surface) and int(index_count) == 0:
		return "changes a surface without indices"
	var vertex_limit := int(surface.vertex_count)
	if surface.has("compact_runs"):
		if not surface.has("base"):
			return "compact_runs without base"
		vertex_limit = compacted_vertex_count(surface.compact_runs, int(surface.vertex_count))
		if vertex_limit <= 0:
			return "compact_runs"
	var level_limit := int(index_count)
	if surface.has("base"):
		var base: Variant = surface.base
		if not base is PackedInt32Array or (base as PackedInt32Array).is_empty() \
				or (base as PackedInt32Array).size() % 3 != 0 or (base as PackedInt32Array).size() > int(index_count) \
				or not indices_within(base, vertex_limit):
			return "base"
		level_limit = (base as PackedInt32Array).size()
	var previous_edge := 0.0
	for level: Variant in surface.lods:
		if not level is Array or (level as Array).size() != 2:
			return "lod entry"
		var edge: Variant = level[0]
		var indices: Variant = level[1]
		if not (edge is float or edge is int) or not is_finite(float(edge)) or float(edge) <= previous_edge:
			return "lod edge order"
		if not indices is PackedInt32Array or (indices as PackedInt32Array).is_empty() \
				or (indices as PackedInt32Array).size() % 3 != 0 or (indices as PackedInt32Array).size() >= level_limit:
			return "lod size"
		if not indices_within(indices, vertex_limit):
			return "lod range"
		previous_edge = float(edge)
		level_limit = (indices as PackedInt32Array).size()
	return ""

## True when a (validated) surface plan changes the parsed surface at all.
static func changes_surface(surface: Dictionary) -> bool:
	return surface.has("base") or surface.has("compact_runs") \
		or (surface.get("lods") is Array and not (surface.lods as Array).is_empty())

## Vertices kept by `runs`, or -1 when the runs are not ascending, disjoint,
## non-empty pairs inside [0, vertex_count).
static func compacted_vertex_count(value: Variant, vertex_count: int) -> int:
	if not value is PackedInt32Array:
		return -1
	var runs: PackedInt32Array = value
	var count := runs.size()
	if count < 2 or count % 2 != 0:
		return -1
	var kept := 0
	var end := 0
	var index := 0
	while index < count:
		var start: int = runs[index]
		var length: int = runs[index + 1]
		if start < end or length <= 0 or start + length > vertex_count:
			return -1
		end = start + length
		kept += length
		index += 2
	return kept

## Every index in [0, limit). A sorted copy keeps the scan in native code.
static func indices_within(indices: PackedInt32Array, limit: int) -> bool:
	if indices.is_empty():
		return false
	var ordered := indices.duplicate()
	ordered.sort()
	return ordered[0] >= 0 and ordered[ordered.size() - 1] < limit

static func new_catalog(source_check := DEFAULT_SOURCE_CHECK) -> Dictionary:
	return {"schema": SCHEMA, "policy": POLICY, "engine": engine_identity(),
		"source_check": source_check, "entries": {}}

static func catalog_entry(source_sha256: String, source_bytes: int, sidecar_bytes: PackedByteArray,
		inputs := {}) -> Dictionary:
	var digest := sha256_hex(sidecar_bytes)
	var entry := {"source_sha256": source_sha256, "source_bytes": source_bytes,
		"sidecar": blob_path(digest), "sidecar_sha256": digest, "sidecar_bytes": sidecar_bytes.size()}
	if not inputs.is_empty():
		entry["inputs"] = inputs
	return entry

## "" when the catalogue header is valid (entries are checked on lookup).
static func validate_catalog(value: Variant) -> String:
	if not value is Dictionary:
		return "not a dictionary"
	var catalog: Dictionary = value
	if not _whole(catalog.get("schema")) or int(catalog.schema) != SCHEMA:
		return "schema"
	if not catalog.get("policy") is String or str(catalog.policy) != POLICY:
		return "policy"
	if not catalog.get("engine") is String or str(catalog.engine).is_empty():
		return "engine"
	if not str(catalog.get("source_check", DEFAULT_SOURCE_CHECK)) in SOURCE_CHECKS \
			or not catalog.get("source_check", DEFAULT_SOURCE_CHECK) is String:
		return "source_check"
	if not catalog.get("entries") is Dictionary:
		return "entries"
	return ""

static func validate_entry(value: Variant) -> String:
	if not value is Dictionary:
		return "not a dictionary"
	var entry: Dictionary = value
	if not is_digest(entry.get("source_sha256")) or not _whole(entry.get("source_bytes")) \
			or int(entry.source_bytes) < 0:
		return "source"
	if not is_digest(entry.get("sidecar_sha256")) or str(entry.get("sidecar", "")) != blob_path(str(entry.sidecar_sha256)) \
			or not entry.get("sidecar") is String:
		return "sidecar"
	if not _whole(entry.get("sidecar_bytes")) or int(entry.sidecar_bytes) <= HEADER_BYTES \
			or int(entry.sidecar_bytes) > MAX_ENCODED_BYTES + HEADER_BYTES:
		return "sidecar_bytes"
	if entry.has("inputs") and not entry.inputs is Dictionary:
		return "inputs"
	return ""

## JSON numbers arrive as floats.
static func _whole(value: Variant) -> bool:
	return value is int or (value is float and is_finite(value) and float(value) == floorf(value))

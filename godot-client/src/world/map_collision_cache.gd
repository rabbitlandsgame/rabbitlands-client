extends RefCounted
## Maintenance extracts authoritative cooked collision. Play reads plain CPU
## vectors only: no Nodes, mesh/texture uploads, or renderer serialization getters.
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const Archived := preload("res://src/actors/archived_model_policy.gd")
const GeometryPolicy := preload("res://src/world/map_geometry_policy.gd")
const Installed := preload("res://src/world/installed_world_cache.gd")
const POLICY := "map-collision-faces-v1"
const VERSION := 1
const DIRECTORY := "user://map-collision-cache"
const MAX_METADATA_BYTES := 4194304
const MAX_RAW_BYTES := 134217728
const MAX_BLOB_BYTES := 67108864
const MAX_PATHS := 65536
const MAX_POINTS := 8000000
const MAX_COORDINATE := 10000000.0
static var _sequence := 0

static func _hash(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

static func _digest(value: Variant) -> String:
	return Sources.digest_bytes(JSON.stringify(value,"",true,true).to_utf8_buffer())

static func _logical(path: String) -> String:
	return path if not Sources.source_path(path).is_empty() else Sources.logical_source(path)

static func policy() -> String:
	var engine := Engine.get_version_info()
	return _digest([POLICY,VERSION,GeometryPolicy.VERSION,MapCache.CACHE_FORMAT_VERSION,engine.get("hash",""),
		engine.get("string",""),RenderingServer.get_current_rendering_method(),Archived.cache_token()])

static func _root() -> String:
	return DIRECTORY.path_join(policy())

static func _entry_path(source: String) -> String:
	return _root().path_join("entries/"+_digest(_logical(source))+".json")

static func _owned(path: String, extension: String, root := "") -> bool:
	var directory := _root() if root.is_empty() else root
	var folder := "entries" if extension == "json" else "blobs"
	var local := path == path.replace("\\","/").simplify_path() \
		and path.get_base_dir() == directory.path_join(folder) \
		and path.get_extension() == extension and _hash(path.get_file().get_basename())
	return local or (root.is_empty() and extension == "rlc" and Installed.owns_blob(path,"collision",policy(),extension))

static func _read(path: String, limit := MAX_METADATA_BYTES) -> Dictionary:
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null and _owned(path,"json"): file = FileAccess.open(path+".previous",FileAccess.READ)
	if file == null or file.get_length() > limit: return {}
	var value: Variant = JSON.parse_string(file.get_as_text())
	return value if value is Dictionary else {}

static func _miss(reason: String) -> Dictionary:
	return {"ok":false,"reason":reason,"error":reason,"faces":{},"bytes":0}

static func _node_path(path: Variant) -> bool:
	if not path is String or path.is_empty() or path.length() > 4096: return false
	if path == ".": return true
	if path.is_absolute_path() or ":" in path or "\\" in path or path != path.simplify_path(): return false
	for segment: String in path.split("/"):
		if segment.is_empty() or segment in [".",".."]: return false
	return true

static func _inputs(inputs: Variant, source: String, verified: Dictionary = {}, diagnostics: Dictionary = {}) -> bool:
	if not inputs is Array or inputs.is_empty() or inputs.size() > MAX_PATHS: return false
	var measure := not diagnostics.is_empty()
	var seen := {}
	for row: Variant in inputs:
		if not row is Dictionary or not row.get("path") is String: return false
		var schema_began := Time.get_ticks_usec() if measure else 0
		var hash_valid := _hash(row.get("sha256"))
		if measure: diagnostics["schema_us"] = int(diagnostics.get("schema_us",0))+Time.get_ticks_usec()-schema_began
		if not hash_valid: return false
		var path_began := Time.get_ticks_usec() if measure else 0
		var path := str(row.path)
		if _logical(path) != path or Sources.source_path(path).is_empty(): return false
		if seen.has(path) and seen[path] != row.sha256: return false
		seen[path] = row.sha256
		if measure: diagnostics["paths_us"] = int(diagnostics.get("paths_us",0))+Time.get_ticks_usec()-path_began
		if verified.get(path,"") == row.sha256:
			if measure: diagnostics["proof_hits"] = int(diagnostics.get("proof_hits",0))+1
			continue
		var began := Time.get_ticks_usec() if measure else 0
		var actual := FileAccess.get_sha256(Sources.source_path(path))
		if measure:
			var elapsed := Time.get_ticks_usec()-began
			diagnostics["hash_calls"] = int(diagnostics.get("hash_calls",0))+1
			diagnostics["hash_us"] = int(diagnostics.get("hash_us",0))+elapsed
			var slow: Array = diagnostics.get("slow_files",[])
			slow.append({"path":path,"us":elapsed})
			slow.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return int(a.us)>int(b.us))
			if slow.size()>4: slow.resize(4)
			diagnostics["slow_files"] = slow
		if actual != row.sha256: return false
	return seen.has(source)

static func _faces(value: Variant) -> Dictionary:
	if not value is Dictionary or value.size() > MAX_PATHS: return _miss("collision_faces_schema")
	var count := 0
	for path: Variant in value:
		if not _node_path(path) or not value[path] is PackedVector3Array: return _miss("collision_faces_schema")
		var points: PackedVector3Array = value[path]
		if points.is_empty() or points.size() % 3 != 0: return _miss("collision_triangle_count")
		count += points.size()
		if count > MAX_POINTS: return _miss("collision_face_limit")
		for point: Vector3 in points:
			if not point.is_finite() or maxf(absf(point.x),maxf(absf(point.y),absf(point.z))) > MAX_COORDINATE:
				return _miss("collision_coordinate_bounds")
	return {"ok":true,"points":count,"bytes":count*12}

## Preflight exactly the data-only Variant layout we write. Never hand nested
## dictionaries, object records, bogus allocation counts, or trailing data to
## bytes_to_var. Both float32 and float64 vector encodings are bounded.
static func _layout(raw: PackedByteArray) -> bool:
	if raw.size() < 8 or raw.size() > MAX_RAW_BYTES or raw.decode_u32(0) != TYPE_DICTIONARY: return false
	var count := int(raw.decode_u32(4))
	if count > MAX_PATHS: return false
	var offset := 8
	var total := 0
	var paths := {}
	for item: int in count:
		if offset+8 > raw.size() or raw.decode_u32(offset) != TYPE_STRING: return false
		var length := int(raw.decode_u32(offset+4))
		offset += 8
		if length <= 0 or length > 16384 or offset+length > raw.size(): return false
		var path := raw.slice(offset,offset+length).get_string_from_utf8()
		if not _node_path(path) or paths.has(path): return false
		paths[path] = true
		offset += (length+3) & ~3
		if offset+8 > raw.size(): return false
		var kind := int(raw.decode_u32(offset))
		if (kind & 65535) != TYPE_PACKED_VECTOR3_ARRAY or (kind & ~65535) not in [0,65536]: return false
		var points := int(raw.decode_u32(offset+4))
		if points <= 0 or points % 3 != 0: return false
		total += points
		if total > MAX_POINTS: return false
		offset += 8+points*(24 if (kind & 65536) != 0 else 12)
		if offset > raw.size(): return false
	return offset == raw.size()

static func acquire(source: String, digest: String, verified: Dictionary = {}) -> Dictionary:
	var logical := _logical(source)
	if logical.is_empty() or not logical.ends_with(".json") or not _hash(digest): return _miss("collision_source_invalid")
	var installed := Installed.entry("collision","world|"+logical,policy())
	if not installed.is_empty():
		var result := _acquire_entry(installed,source,digest,verified)
		if bool(result.ok): return result
	return _acquire_entry(_read(_entry_path(logical)),source,digest,verified)

static func _acquire_entry(entry: Dictionary, source: String, digest: String, verified: Dictionary = {}) -> Dictionary:
	var logical := _logical(source)
	if entry.is_empty(): return _miss("collision_not_prepared")
	if int(entry.get("schema",0)) != VERSION or entry.get("policy") != policy() \
			or entry.get("source") != logical or entry.get("source_digest") != digest: return _miss("collision_source_or_policy_changed")
	var path := str(entry.get("blob",""))
	if not _owned(path,"rlc") or not _hash(entry.get("sha256")) or path.get_file().get_basename() != entry.sha256:
		return _miss("collision_blob_path")
	var size := int(entry.get("blob_bytes",0))
	var raw_size := int(entry.get("raw_bytes",0))
	if size <= 16 or size > MAX_BLOB_BYTES or raw_size < 8 or raw_size > MAX_RAW_BYTES: return _miss("collision_size_bounds")
	if not _inputs(entry.get("inputs"),logical,verified): return _miss("collision_dependency_changed")
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null or file.get_length() != size: return _miss("collision_blob_missing")
	var bytes := file.get_buffer(size)
	if Sources.digest_bytes(bytes) != entry.sha256: return _miss("collision_blob_changed")
	if bytes.slice(0,4).get_string_from_ascii() != "RLCC" or bytes.decode_u32(4) != VERSION \
			or bytes.decode_u32(8) != raw_size or bytes.decode_u32(12) != FileAccess.COMPRESSION_ZSTD:
		return _miss("collision_blob_header")
	var raw := bytes.slice(16).decompress(raw_size,FileAccess.COMPRESSION_ZSTD)
	if raw.size() != raw_size or not _layout(raw): return _miss("collision_data_layout")
	var faces: Variant = bytes_to_var(raw)
	var valid := _faces(faces)
	if not bool(valid.ok) or int(entry.get("points",-1)) != int(valid.get("points",0)): return _miss("collision_faces_invalid")
	return {"ok":true,"faces":faces,"bytes":int(valid.bytes),"blob_bytes":size,"entry":entry,
		"coverage":entry.get("coverage",{})}

static func current(source: String, digest: String) -> bool:
	return bool(acquire(source,digest).ok)

static func _parent(path: String) -> String:
	var parent := path.get_base_dir()
	return "." if parent.is_empty() else parent

static func _extract(packed: PackedScene) -> Dictionary:
	if packed == null or packed.get_script() != null: return _miss("collision_scene_invalid")
	var state := packed.get_state()
	if state.get_connection_count() != 0 or state.get_node_count() > MAX_PATHS*3: return _miss("collision_scene_invalid")
	var nodes := {}
	for index: int in state.get_node_count():
		var path := str(state.get_node_path(index)).trim_prefix("./")
		if not _node_path(path) or nodes.has(path) or state.get_node_instance(index) != null \
				or not state.get_node_instance_placeholder(index).is_empty(): return _miss("collision_scene_hierarchy")
		var properties := {}
		for property: int in state.get_node_property_count(index):
			var name := str(state.get_node_property_name(index,property))
			var value: Variant = state.get_node_property_value(index,property)
			if name == "script" and value != null: return _miss("collision_scene_script")
			properties[name] = value
		nodes[path] = {"type":str(state.get_node_type(index)),"properties":properties}
	var faces := {}
	var coverage := {"concave_shapes":0,"mesh_paths":0,"duplicate_shapes":0,"unmapped_shapes":0}
	for path: String in nodes:
		var node: Dictionary = nodes[path]
		if node.type != "CollisionShape3D": continue
		var shape := node.properties.get("shape") as ConcavePolygonShape3D
		if shape == null: continue
		coverage.concave_shapes += 1
		var body_path := _parent(path)
		var mesh_path := _parent(body_path)
		if not nodes.has(body_path) or not nodes.has(mesh_path) or nodes[body_path].type != "StaticBody3D" \
				or nodes[mesh_path].type != "MeshInstance3D":
			coverage.unmapped_shapes += 1
			continue
		if node.properties.get("transform",Transform3D.IDENTITY) != Transform3D.IDENTITY \
				or nodes[body_path].properties.get("transform",Transform3D.IDENTITY) != Transform3D.IDENTITY:
			return _miss("collision_shape_transform")
		var points := shape.get_faces()
		if faces.has(mesh_path):
			if faces[mesh_path] != points: return _miss("collision_shape_conflict")
			coverage.duplicate_shapes += 1
		else:
			faces[mesh_path] = points
	coverage.mesh_paths = faces.size()
	var valid := _faces(faces)
	if not bool(valid.ok): return valid
	return {"ok":true,"faces":faces,"points":valid.points,"bytes":valid.bytes,"coverage":coverage}

static func _temporary(path: String) -> String:
	_sequence += 1
	return path+"."+str(OS.get_process_id())+"."+str(_sequence)+".tmp"

static func _write_bytes(path: String, bytes: PackedByteArray) -> bool:
	var file := FileAccess.open(path,FileAccess.WRITE)
	if file == null: return false
	file.store_buffer(bytes)
	file.flush()
	var error := file.get_error()
	file.close()
	return error == OK

static func _write_metadata(path: String, entry: Dictionary) -> bool:
	if not _owned(path,"json") or DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK: return false
	var temporary := _temporary(path)
	if not _write_bytes(temporary,JSON.stringify(entry,"",true,true).to_utf8_buffer()): return false
	if not FileAccess.file_exists(path): return DirAccess.rename_absolute(temporary,path) == OK
	var previous := path+".previous"
	if FileAccess.file_exists(previous) and DirAccess.remove_absolute(previous) != OK: return false
	if DirAccess.rename_absolute(path,previous) != OK: return false
	if DirAccess.rename_absolute(temporary,path) != OK:
		DirAccess.rename_absolute(previous,path)
		return false
	DirAccess.remove_absolute(previous)
	return true

static func write_packed(packed: PackedScene, source: String, digest: String, inputs: Array) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id(): return _miss("collision_producer_requires_main")
	var logical := _logical(source)
	if logical.is_empty() or not logical.ends_with(".json") or not _hash(digest) or not _inputs(inputs,logical):
		return _miss("collision_source_invalid")
	var extracted := _extract(packed)
	if not bool(extracted.ok): return extracted
	var ordered := {}
	var paths: Array = extracted.faces.keys()
	paths.sort()
	for path: String in paths: ordered[path] = extracted.faces[path]
	var raw := var_to_bytes(ordered)
	if raw.size() > MAX_RAW_BYTES or not _layout(raw): return _miss("collision_data_layout")
	var bytes := "RLCC".to_ascii_buffer()
	bytes.resize(16)
	bytes.encode_u32(4,VERSION)
	bytes.encode_u32(8,raw.size())
	bytes.encode_u32(12,FileAccess.COMPRESSION_ZSTD)
	bytes.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))
	if bytes.size() <= 16 or bytes.size() > MAX_BLOB_BYTES: return _miss("collision_size_bounds")
	var sha := Sources.digest_bytes(bytes)
	var path := _root().path_join("blobs/"+sha+".rlc")
	if DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK: return _miss("collision_folder_unwritable")
	if FileAccess.file_exists(path):
		if FileAccess.get_sha256(path) != sha: return _miss("collision_existing_blob_changed")
	else:
		var temporary := _temporary(path)
		if not _write_bytes(temporary,bytes): return _miss("collision_blob_unwritable")
		if DirAccess.rename_absolute(temporary,path) != OK:
			DirAccess.remove_absolute(temporary)
			if FileAccess.get_sha256(path) != sha: return _miss("collision_blob_unwritable")
	if not _inputs(inputs,logical): return _miss("collision_dependency_changed")
	var entry := {"schema":VERSION,"policy":policy(),"source":logical,"source_digest":digest,
		"blob":path,"sha256":sha,"blob_bytes":bytes.size(),"raw_bytes":raw.size(),"points":extracted.points,
		"inputs":inputs.duplicate(true),"coverage":extracted.coverage}
	if not _write_metadata(_entry_path(logical),entry): return _miss("collision_metadata_unwritable")
	return {"ok":true,"bytes":extracted.bytes,"blob_bytes":bytes.size(),
		"entry":entry,"coverage":extracted.coverage}

static func _geometry_blob(path: Variant, geometry_policy := "") -> bool:
	if not path is String or path != path.replace("\\","/").simplify_path(): return false
	if path.get_extension() in ["scn","res"] and _hash(path.get_file().get_basename()) \
			and not geometry_policy.is_empty() and Installed.release_blob_directory(path.get_base_dir(),geometry_policy): return true
	if not geometry_policy.is_empty() and Installed.owns_blob(path,"geometry",geometry_policy,path.get_extension()): return true
	var prefix := "user://map-geometry-cache/"
	if not path.begins_with(prefix): return false
	var parts: PackedStringArray = str(path).trim_prefix(prefix).split("/")
	return parts.size() == 3 and _hash(parts[0]) and parts[1] == "blobs" \
		and parts[2].get_extension() in ["scn","res"] and _hash(parts[2].get_basename())

static func write_from_geometry(entry: Dictionary) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id(): return _miss("collision_producer_requires_main")
	if entry.get("kind") != "world" or not entry.get("payloads") is Dictionary \
			or entry.payloads.size() > MAX_PATHS or not _geometry_blob(entry.get("primary"),str(entry.get("policy",""))) \
			or not entry.payloads.has(entry.primary): return _miss("collision_geometry_invalid")
	for path: Variant in entry.payloads:
		if not _geometry_blob(path,str(entry.get("policy",""))) or not _hash(entry.payloads[path]) \
				or FileAccess.get_sha256(path) != entry.payloads[path]: return _miss("collision_geometry_changed")
	if not _inputs(entry.get("inputs"),str(entry.get("source",""))): return _miss("collision_dependency_changed")
	var packed := ResourceLoader.load(str(entry.primary),"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	return write_packed(packed,str(entry.source),str(entry.get("source_digest","")),entry.inputs)

static func busy() -> bool:
	var directory := DirAccess.open("user://map-geometry-cache")
	if directory == null: return false
	for name: String in directory.get_directories():
		if not _hash(name): continue
		var owner := _read("user://map-geometry-cache/"+name+"/preparing.lock/owner.json",8192)
		var pid := int(owner.get("pid",0))
		if pid > 0 and OS.is_process_running(pid): return true
	return false

static func _disk_files() -> PackedStringArray:
	var files := PackedStringArray()
	var directory := DirAccess.open(DIRECTORY)
	if directory == null: return files
	for name: String in directory.get_directories():
		if not _hash(name): continue
		var root := DIRECTORY.path_join(name)
		for folder: String in ["entries","blobs"]:
			var child := DirAccess.open(root.path_join(folder))
			if child == null: continue
			for file: String in child.get_files():
				var path := root.path_join(folder).path_join(file)
				if _owned(path.trim_suffix(".previous"),"json" if folder == "entries" else "rlc",root): files.append(path)
	return files

static func total_bytes() -> int:
	var bytes := 0
	for path: String in _disk_files():
		var file := FileAccess.open(path,FileAccess.READ)
		if file != null: bytes += file.get_length()
	return bytes

static func clear_disk() -> int:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or busy(): return 0
	var removed := 0
	for path: String in _disk_files():
		if DirAccess.remove_absolute(path) == OK: removed += 1
	return removed

static func prune_unreferenced() -> int:
	# The caller holds its producer lock and has completed the exact full scope.
	# Invalid metadata aborts pruning; partial/failed preparation never calls it.
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or not busy(): return 0
	var directory := DirAccess.open(_root().path_join("entries"))
	if directory == null: return 0
	var retained := {}
	for name: String in directory.get_files():
		var path := _root().path_join("entries").path_join(name)
		if not _owned(path.trim_suffix(".previous"),"json"): continue
		var entry := _read(path)
		if int(entry.get("schema",0)) != VERSION or entry.get("policy") != policy() \
				or not _owned(str(entry.get("blob","")),"rlc"): return 0
		retained[str(entry.blob)] = true
	var blobs := DirAccess.open(_root().path_join("blobs"))
	if blobs == null: return 0
	var removed := 0
	for name: String in blobs.get_files():
		var path := _root().path_join("blobs").path_join(name)
		if _owned(path,"rlc") and not retained.has(path) and DirAccess.remove_absolute(path) == OK: removed += 1
	return removed

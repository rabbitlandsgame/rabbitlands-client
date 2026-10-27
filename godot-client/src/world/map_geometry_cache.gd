extends RefCounted
## Read-only during play. Native geometry is produced by the maintenance
## preparer; source/texture failures always retain the ordinary raw loader.
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Writer := preload("res://src/world/map_geometry_writer.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const Archived := preload("res://src/actors/archived_model_policy.gd")
const CollisionCache := preload("res://src/world/map_collision_cache.gd")
const GeometryPolicy := preload("res://src/world/map_geometry_policy.gd")
const PavingCache := preload("res://src/world/map_paving_cache.gd")
const GroundProfile := preload("res://src/world/look/look_profile.gd")
const SCOPE := "res://data/maps/geometry-cache-scope.json"
const REGISTRY := "res://data/maps/registry.json"
const DIRECTORY := "user://map-geometry-cache"
const VERSION := GeometryPolicy.VERSION
const MAX_METADATA_BYTES := 16777216
const DIAGNOSTICS_ENVIRONMENT := "ELORIA_GEOMETRY_DIAGNOSTICS"
const CONTAINER_REUSE_ENVIRONMENT := "ELORIA_GEOMETRY_CONTAINER_REUSE"
const PIPELINE_INPUTS := [
	"res://assets/world/biome_blend/catalog.json",
	"res://assets/world/biome_blend/object-materials.json",
]
static var cooking := false
static var _initialized := false
static var _targets: Dictionary = {}
static var _roots: Dictionary = {}
static var _policy := ""
static var _scope_error := ""
static var _mutex := Mutex.new()
static var _hits := 0
static var _misses := 0

static func _read(path: String) -> Dictionary:
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null and path.begins_with(DIRECTORY+"/"):
		file = FileAccess.open(path+".previous",FileAccess.READ)
	if file == null or file.get_length() > MAX_METADATA_BYTES: return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}

static func logical(path: String) -> String:
	if not Sources.source_path(path).is_empty(): return path
	return Sources.logical_source(path)

static func _digest(value: Variant) -> String:
	return Sources.digest_bytes(JSON.stringify(value,"",true,true).to_utf8_buffer())

static func initialize() -> void:
	_mutex.lock()
	if _initialized:
		_mutex.unlock()
		return
	var engine := Engine.get_version_info()
	_policy = _digest([VERSION,Writer.POLICY,Sources.POLICY,Bindings.POLICY,MapCache.CACHE_FORMAT_VERSION,engine.get("hash",""),
		engine.get("string",""),RenderingServer.get_current_rendering_method(),Archived.cache_token()])
	var scope := _read(SCOPE)
	var registry: Dictionary = _read(REGISTRY).get("maps",{})
	if int(scope.get("schema",0)) != 1 or not scope.get("maps") is Array:
		_scope_error = "geometry_scope_invalid"
	else:
		for id: String in scope.maps:
			var resolved := MapRegistry.resolve(registry,id)
			var path := str(resolved.get("manifest",""))
			var document := _read(path)
			if document.is_empty():
				_scope_error = "geometry_scope_manifest_missing: "+id
				break
			_roots[logical(path)] = true
			if document.has("streamingChunks"):
				for chunk: Dictionary in document.streamingChunks.get("chunks",[]):
					var child := path.get_base_dir().path_join(str(chunk.get("manifest",""))).simplify_path()
					# The parent declares the complete leaf list. Opening every leaf
					# merely for a progress label adds thousands of startup reads.
					_add_target("world",child,str(document.get("asset",{}).get("id",id))+"__chunk_"+str(chunk.get("id","")))
			else:
				_add_target("world",path,str(document.get("asset",{}).get("id",id)))
		for overlay: Dictionary in scope.get("asset_overlays",[]):
			var config := _read(str(overlay.get("config","")))
			var assets: Dictionary = config.get("assets",{})
			for placement: Dictionary in config.get("placements",[]):
				var key := str(placement.get("asset",""))
				var path := str(assets.get(key,""))
				_add_target("asset",path,str(overlay.get("owner",""))+":"+key)
	_initialized = true
	_mutex.unlock()

static func _add_target(kind: String, path: String, id: String) -> void:
	var source := logical(path)
	if source.is_empty() or id.is_empty():
		_scope_error = "geometry_scope_target_invalid"
		return
	_targets[kind+"|"+source] = {"kind":kind,"source":source,"id":id}

static func targets() -> Array:
	initialize()
	var keys: Array = _targets.keys()
	keys.sort()
	var result: Array = []
	for key: String in keys: result.append((_targets[key] as Dictionary).duplicate())
	return result

static func eligible(kind: String, path: String) -> bool:
	initialize()
	return _scope_error.is_empty() and _targets.has(kind+"|"+logical(path))

static func scoped_map(path: String) -> bool:
	initialize()
	return _scope_error.is_empty() and _roots.has(logical(path))

static func policy() -> String:
	initialize()
	return _policy

static func root_path() -> String:
	return DIRECTORY.path_join(policy())

static func blobs_path() -> String:
	return root_path().path_join("blobs")

static func entry_path(kind: String, path: String) -> String:
	return root_path().path_join("entries/"+_digest([kind,logical(path)])+".json")

static func _miss(reason: String) -> Dictionary:
	_mutex.lock()
	_misses += 1
	_mutex.unlock()
	return {"status":"miss","reason":reason}

static func _hash_valid(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

static func _owned_blob(path: String) -> bool:
	return path == path.replace("\\","/").simplify_path() and path.get_base_dir() == blobs_path() \
		and path.get_extension() in ["scn","res"] and _hash_valid(path.get_file().get_basename())

static func _diagnostic_add(diagnostics: Dictionary, section: String, key: String, value: int) -> void:
	var values: Dictionary = diagnostics.get(section,{})
	values[key] = int(values.get(key,0))+value
	diagnostics[section] = values

static func _diagnostic_size(path: String, diagnostics: Dictionary) -> int:
	# Byte accounting is diagnostic-only. Keep the extra open/length probe
	# outside the measured native SHA call, and expose its own overhead.
	var began := Time.get_ticks_usec()
	var file := FileAccess.open(path,FileAccess.READ)
	var size := 0
	if file != null:
		size = file.get_length()
		file.close()
	_diagnostic_add(diagnostics,"timings_us","geometryVerifySizeProbe",Time.get_ticks_usec()-began)
	return size

static func _copy_diagnostic_timings(timings: Dictionary, diagnostics: Dictionary) -> void:
	for key: String in diagnostics.get("timings_us",{}):
		timings[key] = diagnostics.timings_us[key]

static func _validate_inputs(entry: Dictionary, verified: Dictionary = {}, diagnostics: Dictionary = {}) -> bool:
	if not entry.get("inputs") is Array or entry.inputs.is_empty() or entry.inputs.size() > 65536: return false
	var capture := not diagnostics.is_empty()
	var seen := {}
	for row: Variant in entry.inputs:
		var began := Time.get_ticks_usec() if capture else 0
		if not row is Dictionary or not row.get("path") is String or not _hash_valid(row.get("sha256")): return false
		if seen.has(row.path) and seen[row.path] != row.sha256: return false
		seen[row.path] = row.sha256
		if capture:
			_diagnostic_add(diagnostics,"timings_us","geometryVerifySourceSchema",Time.get_ticks_usec()-began)
			began = Time.get_ticks_usec()
		var path := Sources.source_path(str(row.path))
		if capture: _diagnostic_add(diagnostics,"timings_us","geometryVerifySourcePath",Time.get_ticks_usec()-began)
		if path.is_empty(): return false
		if verified.get(str(row.path),"") == str(row.sha256):
			if capture: _diagnostic_add(diagnostics,"counts","sourceProofHits",1)
			continue
		if capture:
			_diagnostic_add(diagnostics,"counts","sourceHashCalls",1)
			_diagnostic_add(diagnostics,"counts","sourceHashBytes",_diagnostic_size(path,diagnostics))
			began = Time.get_ticks_usec()
		var digest := FileAccess.get_sha256(path)
		if capture: _diagnostic_add(diagnostics,"timings_us","geometryVerifySourceSha",Time.get_ticks_usec()-began)
		if digest != str(row.sha256): return false
	return true

static func _valid_entry(kind: String, path: String, source_digest: String, verified: Dictionary = {}, diagnostics: Dictionary = {}) -> Dictionary:
	var capture := not diagnostics.is_empty()
	var began := Time.get_ticks_usec() if capture else 0
	if capture: _diagnostic_add(diagnostics,"counts","entryValidationCalls",1)
	if not eligible(kind,path): return _miss("outside_geometry_scope")
	var entry := _read(entry_path(kind,path))
	if capture:
		_diagnostic_add(diagnostics,"timings_us","geometryVerifyMetadataRead",Time.get_ticks_usec()-began)
		began = Time.get_ticks_usec()
	if entry.is_empty(): return _miss("not_prepared")
	if int(entry.get("schema",0)) != VERSION or str(entry.get("policy","")) != policy() \
			or str(entry.get("kind","")) != kind or str(entry.get("source","")) != logical(path) \
			or str(entry.get("source_digest","")) != source_digest:
		return _miss("source_or_policy_changed")
	if not entry.get("bindings") is Dictionary or not entry.get("payloads") is Dictionary \
			or not entry.get("shared_meshes",{}) is Dictionary or not _owned_blob(str(entry.get("primary",""))):
		return _miss("geometry_metadata_invalid")
	if not entry.get("inputs") is Array or entry.inputs.size() > 65536 \
			or entry.bindings.size() > Bindings.MAX_BINDINGS or entry.payloads.size() > 16384:
		return _miss("geometry_metadata_bounds")
	var declared_inputs := {}
	for row: Variant in entry.get("inputs",[]):
		if row is Dictionary: declared_inputs[str(row.get("path",""))] = str(row.get("sha256",""))
	for binding: Variant in entry.bindings.values():
		if not binding is Dictionary or not binding.get("inputs") is Array: return _miss("geometry_binding_inputs")
		for row: Variant in binding.inputs:
			if not row is Dictionary or declared_inputs.get(str(row.get("path","")),"") != str(row.get("sha256","")):
				return _miss("geometry_binding_input_undeclared")
	if capture: _diagnostic_add(diagnostics,"timings_us","geometryVerifyEntrySchema",Time.get_ticks_usec()-began)
	if not _validate_inputs(entry,verified,diagnostics): return _miss("geometry_dependency_changed")
	for blob: Variant in entry.payloads:
		began = Time.get_ticks_usec() if capture else 0
		if not blob is String or not _owned_blob(blob) or not _hash_valid(entry.payloads[blob]):
			return _miss("geometry_payload_changed")
		if capture:
			_diagnostic_add(diagnostics,"timings_us","geometryVerifyPayloadSchema",Time.get_ticks_usec()-began)
			_diagnostic_add(diagnostics,"counts","payloadHashCalls",1)
			_diagnostic_add(diagnostics,"counts","payloadHashBytes",_diagnostic_size(blob,diagnostics))
			began = Time.get_ticks_usec()
		var digest := FileAccess.get_sha256(blob)
		if capture: _diagnostic_add(diagnostics,"timings_us","geometryVerifyPayloadSha",Time.get_ticks_usec()-began)
		if digest != str(entry.payloads[blob]): return _miss("geometry_payload_changed")
	if not entry.payloads.has(str(entry.primary)): return _miss("geometry_primary_undeclared")
	for mesh: Variant in entry.shared_meshes:
		if not entry.payloads.has(mesh) or not _hash_valid(entry.shared_meshes[mesh]): return _miss("geometry_prototype_invalid")
	return {"status":"hit","entry":entry}

static func world_proof(manifest: WorldManifest, _source_digest: String) -> Dictionary:
	# This proof lives for this load call only. It reuses the immediately
	# completed production full-hash verification, never file timestamps.
	var proof := {}
	if manifest == null or not manifest.verification_diagnostics.has("failures") \
			or int(manifest.verification_diagnostics.failures) != 0: return proof
	for uri: String in manifest.data.get("externalResources",{}):
		proof[logical(manifest.glb_path().get_base_dir().path_join(uri).simplify_path())] = str(manifest.data.externalResources[uri])
	# package_digest normalizes manifest line endings, while geometry inputs
	# record exact bytes. Do not treat that combined digest as a raw-file proof.
	return proof

static func acquire(kind: String, path: String, source_digest: String, verified: Dictionary = {}, allowed := true) -> Dictionary:
	if cooking or not allowed or OS.get_environment("ELORIA_NO_GEOMETRY_CACHE") == "1": return _miss("geometry_disabled")
	var timings_us := {"geometryVerify":0,"geometryRead":0,"geometryImagePrepare":0,
		"geometryTextureBind":0,"geometryInstantiate":0}
	var diagnostics: Dictionary = {"timings_us":{},"counts":{}} if OS.get_environment(DIAGNOSTICS_ENVIRONMENT) == "1" else {}
	var began := Time.get_ticks_usec()
	var result := _valid_entry(kind,path,source_digest,verified,diagnostics)
	timings_us["geometryVerify"] = Time.get_ticks_usec()-began
	_copy_diagnostic_timings(timings_us,diagnostics)
	if str(result.status) != "hit": return result
	began = Time.get_ticks_usec()
	var packed := ResourceLoader.load(str(result.entry.primary),"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	timings_us["geometryRead"] = Time.get_ticks_usec()-began
	if packed == null: return _miss("geometry_unreadable")
	began = Time.get_ticks_usec()
	var texture_policy := Bindings.runtime_policy()
	var container_source := str(result.entry.source) if kind == "asset" and OS.get_environment(CONTAINER_REUSE_ENVIRONMENT) != "0" else ""
	var prepared := Bindings.prepare(result.entry.bindings,OS.get_thread_caller_id() != OS.get_main_thread_id(),container_source,diagnostics)
	if not diagnostics.is_empty(): prepared["geometry_diagnostics"] = diagnostics
	timings_us["geometryImagePrepare"] = Time.get_ticks_usec()-began
	_copy_diagnostic_timings(timings_us,diagnostics)
	if not bool(prepared.get("ok",false)): return _miss("geometry_texture_prepare: "+str(prepared.get("error","")))
	if texture_policy != Bindings.runtime_policy(): return _miss("geometry_texture_policy_changed")
	_mutex.lock()
	_hits += 1
	_mutex.unlock()
	return {"status":"hit","entry":result.entry,"resource":packed,"textures":prepared,
		"source_digest":source_digest,"prepared_on_main":OS.get_thread_caller_id() == OS.get_main_thread_id(),
		"timings_us":timings_us,"texture_policy":texture_policy,"diagnostics":diagnostics}

static func revalidate(record: Dictionary) -> bool:
	var entry: Dictionary = record.get("entry",{})
	if entry.is_empty(): return false
	var source := Sources.source_path(str(entry.get("source","")))
	var began := Time.get_ticks_usec()
	var diagnostics: Dictionary = record.get("diagnostics",{})
	var current := _valid_entry(str(entry.get("kind","")),source,str(record.get("source_digest","")),{},diagnostics)
	var timings_us: Dictionary = record.get("timings_us",{})
	timings_us["geometryVerify"] = int(timings_us.get("geometryVerify",0))+Time.get_ticks_usec()-began
	_copy_diagnostic_timings(timings_us,diagnostics)
	record["timings_us"] = timings_us
	return str(current.status) == "hit" and current.entry == entry

## Main-only Resource publication. It releases decoded CPU carriers after
## binding a private template, without creating Nodes or skipping validation.
static func bind(record: Dictionary, verify_again := true) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or str(record.get("status","")) != "hit": return false
	if not bool(record.get("bound",false)) and record.get("texture_policy",[]) != Bindings.runtime_policy(): return false
	if verify_again and not revalidate(record): return false
	var packed := record.get("resource") as PackedScene
	if packed == null: return false
	var timings_us: Dictionary = record.get("timings_us",{})
	var diagnostics: Dictionary = record.get("diagnostics",{})
	record["timings_us"] = timings_us
	if not bool(record.get("bound",false)):
		var began := Time.get_ticks_usec()
		var bound := Bindings.apply(packed,record.get("textures",{}))
		timings_us["geometryTextureBind"] = int(timings_us.get("geometryTextureBind",0))+Time.get_ticks_usec()-began
		_copy_diagnostic_timings(timings_us,diagnostics)
		if not bound: return false
		record["bound"] = true
		# The bound Resource graph now owns its textures. Decoded CPU images
		# and temporary worker carriers must not survive a cached asset session.
		record["textures"] = {}
	return true

static func instantiate(record: Dictionary, verify_again := true) -> Node3D:
	if not bind(record,verify_again): return null
	var packed := record.get("resource") as PackedScene
	var timings_us: Dictionary = record.get("timings_us",{})
	var diagnostics: Dictionary = record.get("diagnostics",{})
	# This graph and every native payload were verified above. Do not reload
	# unbound dependency templates merely to inspect them a second time.
	var entry: Dictionary = record.entry
	# A resident bound template stays immutable. Rewalking every serialized
	# material property for thousands of identical scenery placements would
	# repeat the same safety check without changing its result.
	var began := Time.get_ticks_usec()
	var verified := int(record.get("verified_template_id",0)) == packed.get_instance_id()
	var instance: Node3D
	if str(entry.kind) == "asset" and entry.shared_meshes.is_empty():
		# GlbSceneCache's static scenery already shares immutable mesh/material
		# templates. Mineral styling and fading create their own overrides. Keep
		# those existing ownership semantics rather than pre-copying materials
		# for all 6,110 underground placements on every arrival.
		if not verified:
			var validation_began := Time.get_ticks_usec() if not diagnostics.is_empty() else 0
			var valid := Lifecycle._data_only(packed,{})
			if not diagnostics.is_empty():
				_diagnostic_add(diagnostics,"timings_us","geometryTemplateDataOnly",Time.get_ticks_usec()-validation_began)
				_diagnostic_add(diagnostics,"counts","templateDataOnlyCalls",1)
				_copy_diagnostic_timings(timings_us,diagnostics)
			if not valid: return null
		var node := packed.instantiate()
		if node is Node3D: instance = node as Node3D
		elif node != null: node.free()
	else:
		# World look/fade passes receive private materials and MultiMesh buffers.
		instance = Lifecycle.instantiate({"status":"hit","resource":packed,"entry":{
			"source":entry.source,"payloads":[],"shared_meshes":entry.shared_meshes,"shared_images":{}}})
	timings_us["geometryInstantiate"] = int(timings_us.get("geometryInstantiate",0))+Time.get_ticks_usec()-began
	if instance != null: record["verified_template_id"] = packed.get_instance_id()
	return instance

static func current(kind: String, path: String, source_digest: String) -> bool:
	return str(_valid_entry(kind,path,source_digest).status) == "hit"

static func publish(entry: Dictionary) -> bool:
	if not cooking or OS.get_thread_caller_id() != OS.get_main_thread_id(): return false
	if not _validate_inputs(entry): return false
	var path := entry_path(str(entry.kind),Sources.source_path(str(entry.source)))
	return write_json(path,entry)

static func write_json(path: String, data: Dictionary) -> bool:
	if DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK: return false
	var temporary := path+"."+str(OS.get_process_id())+".tmp"
	var file := FileAccess.open(temporary,FileAccess.WRITE)
	if file == null: return false
	file.store_string(JSON.stringify(data,"",true,true))
	file.flush()
	var error := file.get_error()
	file.close()
	if error != OK: return false
	if not FileAccess.file_exists(path): return DirAccess.rename_absolute(temporary,path) == OK
	var previous := path+".previous"
	if FileAccess.file_exists(previous) and DirAccess.remove_absolute(previous) != OK: return false
	if DirAccess.rename_absolute(path,previous) != OK: return false
	if DirAccess.rename_absolute(temporary,path) != OK:
		DirAccess.rename_absolute(previous,path)
		return false
	DirAccess.remove_absolute(previous)
	return true

static func _has_release_identity() -> bool:
	var identity := _read("res://data/client_release.json")
	return not str(identity.get("commit","")).is_empty() and str(identity.get("platform","source")) != "source"

static func startup_signature() -> String:
	var overlay_hashes: Array = []
	for overlay: Dictionary in _read(SCOPE).get("asset_overlays",[]):
		overlay_hashes.append(FileAccess.get_sha256(str(overlay.get("config",""))))
	# Development checkouts have no release identity. Modification times are
	# only a cheap maintenance hint; runtime acceptance always hashes bytes.
	var development_inputs: Array = []
	var region_hashes := {}
	for target: Dictionary in targets():
		if str(target.get("kind","")) != "world" or not str(target.get("id","")).contains("__chunk_"): continue
		var region := str(target.id).get_slice("__chunk_",0)
		if not region_hashes.has(region):
			var path := GroundProfile.region_path(region)
			region_hashes[region] = FileAccess.get_sha256(path) if FileAccess.file_exists(path) else "missing"
	if not _has_release_identity():
		for target: Dictionary in targets():
			var path := Sources.source_path(str(target.source))
			development_inputs.append([target.source,FileAccess.get_modified_time(path)])
	return _digest([policy(),CollisionCache.policy(),PavingCache.policy(),region_hashes,FileAccess.get_sha256(SCOPE),FileAccess.get_sha256(REGISTRY),
		FileAccess.get_sha256("res://data/client_release.json") if FileAccess.file_exists("res://data/client_release.json") else "source",overlay_hashes,development_inputs])

static func needs_preparation() -> bool:
	if DisplayServer.get_name() == "headless" or OS.get_environment("ELORIA_NO_GEOMETRY_CACHE") == "1" \
			or not MapCache.is_enabled(): return false
	var complete := _read(root_path().path_join("complete.json"))
	var keys: Array = _targets.keys()
	keys.sort()
	if str(complete.get("signature","")) != startup_signature() or complete.get("target_keys",[]) != keys: return true
	if not _has_release_identity():
		if not complete.get("input_hints") is Dictionary or complete.input_hints.is_empty(): return true
		for path: Variant in complete.input_hints:
			var actual := Sources.source_path(str(path))
			if actual.is_empty(): return true
			var modified := FileAccess.get_modified_time(actual)
			if modified != int(complete.input_hints[path]) \
					or (modified == 0 and not FileAccess.file_exists(actual)): return true
	return false

static func input_hints() -> Dictionary:
	var hints := {}
	if _has_release_identity(): return hints
	for target: Dictionary in targets():
		var entry := _read(entry_path(str(target.kind),str(target.source)))
		for row: Dictionary in entry.get("inputs",[]):
			var path := str(row.path)
			hints[path] = FileAccess.get_modified_time(Sources.source_path(path))
	return hints

static func _disk_files() -> PackedStringArray:
	var result := PackedStringArray()
	var directory := DirAccess.open(DIRECTORY)
	if directory == null: return result
	for name: String in directory.get_directories():
		if not _hash_valid(name): continue
		var root := DIRECTORY.path_join(name)
		for sub: String in ["entries","blobs"]:
			var child := DirAccess.open(root.path_join(sub))
			if child == null: continue
			for file: String in child.get_files():
				var finished := file.trim_suffix(".previous")
				var stem := finished.get_basename()
				if not _hash_valid(stem): continue
				if (sub == "blobs" and finished.get_extension() in ["scn","res"]) \
						or (sub == "entries" and finished.get_extension() == "json"):
					result.append(root.path_join(sub).path_join(file))
		for file: String in ["complete.json","complete.json.previous"]:
			if FileAccess.file_exists(root.path_join(file)): result.append(root.path_join(file))
	return result

static func total_bytes() -> int:
	var total := 0
	for path: String in _disk_files():
		var file := FileAccess.open(path,FileAccess.READ)
		if file != null: total += file.get_length()
	return total

static func clear_disk() -> int:
	if cooking: return 0
	var directory := DirAccess.open(DIRECTORY)
	if directory != null:
		for name: String in directory.get_directories():
			if not _hash_valid(name): continue
			var owner := _read(DIRECTORY.path_join(name).path_join("preparing.lock/owner.json"))
			var pid := int(owner.get("pid",0))
			if pid > 0 and OS.is_process_running(pid): return 0
	var removed := 0
	for path: String in _disk_files():
		if DirAccess.remove_absolute(path) == OK: removed += 1
	return removed

static func prune_unreferenced() -> int:
	# Called only after a complete successful preparation while its producer
	# lock is held. Never touch files outside this format's owned flat blobs.
	if not cooking or OS.get_thread_caller_id() != OS.get_main_thread_id(): return 0
	var retained := {}
	for target: Dictionary in targets():
		var entry := _read(entry_path(str(target.kind),str(target.source)))
		if not entry.get("payloads") is Dictionary: return 0
		for path: Variant in entry.payloads:
			if not path is String or not _owned_blob(path): return 0
			retained[path] = true
	var directory := DirAccess.open(blobs_path())
	if directory == null: return 0
	var removed := 0
	for name: String in directory.get_files():
		var path := blobs_path().path_join(name)
		if _owned_blob(path) and not retained.has(path) and DirAccess.remove_absolute(path) == OK: removed += 1
	return removed

static func snapshot() -> Dictionary:
	initialize()
	_mutex.lock()
	var result := {"policy":_policy,"targets":_targets.size(),"scope_error":_scope_error,"hits":_hits,"misses":_misses,"cooking":cooking}
	_mutex.unlock()
	return result

extends Node
## Maintenance-only producer. Runs before play (or through the explicit CLI),
## one source at a time; no worker is allowed to serialize GPU-backed meshes.
const Cache := preload("res://src/world/map_geometry_cache.gd")
const CollisionCache := preload("res://src/world/map_collision_cache.gd")
const PavingCache := preload("res://src/world/map_paving_cache.gd")
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const Writer := preload("res://src/world/map_geometry_writer.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
const TexturePool := preload("res://src/world/external_texture_pool.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const MapMesh := preload("res://src/world/map_mesh_extension.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const GroundProfile := preload("res://src/world/look/look_profile.gd")
signal progress(completed: int,total: int,label: String)
var _cancelled := false

func cancel() -> void:
	_cancelled = true

static func _paving_target(target: Dictionary) -> bool:
	var id := str(target.get("id",""))
	return str(target.get("kind","")) == "world" and id.contains("__chunk_") \
		and not GroundProfile.kit_paving(id.get_slice("__chunk_",0)).is_empty()

static func _source_input(path: String, expected := "") -> Dictionary:
	var logical := Cache.logical(path)
	var actual := Sources.source_path(logical)
	var digest := FileAccess.get_sha256(actual) if not actual.is_empty() else ""
	if logical.is_empty() or not Cache._hash_valid(digest) or (not expected.is_empty() and digest != expected):
		return {"ok":false,"error":"Source data is missing or changed: "+logical}
	return {"ok":true,"path":logical,"sha256":digest}

static func _add_input(inputs: Dictionary, path: String, expected := "") -> Dictionary:
	var logical := Cache.logical(path)
	if inputs.has(logical):
		if not expected.is_empty() and str(inputs[logical]) != expected:
			return {"ok":false,"error":"Package dependencies disagree: "+logical}
		return {"ok":true,"path":logical,"sha256":str(inputs[logical])}
	var row := _source_input(path,expected)
	if bool(row.ok): inputs[str(row.path)] = str(row.sha256)
	return row

static func _relative_source(directory: String, uri: String) -> String:
	var decoded := uri.uri_file_decode()
	if decoded.is_empty() or decoded.is_absolute_path() or ":" in decoded or "\\" in decoded:
		return ""
	return Sources.source_path(Cache.logical(directory.path_join(decoded).simplify_path()))

static func _declared_inputs(directory: String, declarations: Variant, inputs: Dictionary) -> Dictionary:
	if not declarations is Dictionary:
		return {"ok":false,"error":"Invalid package dependency declarations."}
	var paths := {}
	var hashes := {}
	for uri: Variant in declarations:
		if not uri is String or not declarations[uri] is String or not Cache._hash_valid(str(declarations[uri])):
			return {"ok":false,"error":"Invalid package dependency hash."}
		var path := _relative_source(directory,str(uri))
		if path.is_empty(): return {"ok":false,"error":"Invalid package dependency path: "+str(uri)}
		var row := _add_input(inputs,path,str(declarations[uri]))
		if not bool(row.ok): return row
		paths[str(row.path)] = str(row.sha256)
		hashes[str(row.sha256)] = true
	return {"ok":true,"paths":paths,"hashes":hashes}

## Read only the JSON chunk, not a second copy of a map's mesh buffers.
static func _gltf_document(path: String) -> Dictionary:
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null: return {}
	var prefix := file.get_buffer(20)
	if prefix.size() < 20 or prefix.slice(0,4).get_string_from_ascii() != "glTF" \
			or prefix.decode_u32(4) != 2 or prefix.decode_u32(8) != file.get_length() \
			or prefix.decode_u32(16) != 0x4e4f534a:
		return {}
	var length := int(prefix.decode_u32(12))
	if length <= 0 or length > Cache.MAX_METADATA_BYTES or length+20 > file.get_length(): return {}
	var parsed: Variant = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	return parsed if parsed is Dictionary else {}

static func _gltf_inputs(path: String, declarations: Dictionary, require_declared: bool, inputs: Dictionary) -> Dictionary:
	var document := _gltf_document(path)
	if document.is_empty(): return {"ok":false,"error":"Invalid source glTF package: "+Cache.logical(path)}
	for category: String in ["images","buffers"]:
		var items: Variant = document.get(category,[])
		if not items is Array: return {"ok":false,"error":"Invalid glTF dependency list."}
		for item: Variant in items:
			if not item is Dictionary: return {"ok":false,"error":"Invalid glTF dependency."}
			var uri := str(item.get("uri",""))
			if uri.is_empty() or uri.begins_with("data:"): continue
			var actual := _relative_source(path.get_base_dir(),uri)
			if actual.is_empty(): return {"ok":false,"error":"Invalid glTF dependency path: "+uri}
			var expected := str((declarations.get("paths",{}) as Dictionary).get(Cache.logical(actual),""))
			var row := _add_input(inputs,actual,expected)
			if not bool(row.ok): return row
			# Some packages name another byte-identical shared image alias. Record
			# that actual URI too, and verify it against the declared content hash.
			if require_declared and not (declarations.get("hashes",{}) as Dictionary).has(str(row.sha256)):
				return {"ok":false,"error":"Undeclared glTF dependency: "+str(row.path)}
	var prototypes := {}
	var nodes: Variant = document.get("nodes",[])
	if not nodes is Array: return {"ok":false,"error":"Invalid glTF nodes."}
	for node: Variant in nodes:
		if not node is Dictionary: return {"ok":false,"error":"Invalid glTF node."}
		var extras: Variant = node.get("extras",{})
		var identity: Variant = extras.get(MapMesh.EXTRAS_KEY,{}) if extras is Dictionary else {}
		if not identity is Dictionary: continue
		var key: Variant = identity.get(MapMesh.PROTOTYPE_FIELD,"")
		if not key is String: return {"ok":false,"error":"Invalid glTF prototype identity."}
		if not str(key).is_empty(): prototypes[str(key)] = true
	return {"ok":true,"prototypes":prototypes}

static func _prototype_inputs(path: String, expected: String, inputs: Dictionary, indexes: Dictionary) -> Dictionary:
	var key := path.get_file().get_basename()
	if not Cache._hash_valid(key) or path.get_extension().to_lower() != "glb":
		return {"ok":false,"error":"Invalid shared model identity."}
	var index_path := path.get_base_dir().path_join("index.json")
	var row := _add_input(inputs,index_path)
	if not bool(row.ok): return row
	# Many prototypes in one chunk share this index. Parse its current bytes
	# once per source, while retaining its hash in every dependent entry.
	if not indexes.has(index_path): indexes[index_path] = Cache._read(index_path).get("prototypes",{})
	var fresh: Variant = indexes[index_path]
	var current: Variant = fresh.get(key) if fresh is Dictionary else null
	var pooled: Variant = MeshPool.index_for(path).get(key)
	if not current is Dictionary or not pooled is Dictionary or Cache._digest(current) != Cache._digest(pooled) \
			or str(current.get("sha256","")) != expected:
		return {"ok":false,"error":"Shared model index is missing, changed or disagrees with the map: "+key}
	var declared := _declared_inputs(path.get_base_dir(),current.get("images",{}),inputs)
	if not bool(declared.ok): return declared
	var actual := _gltf_inputs(path,declared,true,inputs)
	if not bool(actual.ok): return actual
	if not (actual.prototypes as Dictionary).is_empty():
		return {"ok":false,"error":"Nested shared model dependencies are unsupported."}
	return {"ok":true,"key":key}

static func _base_inputs(kind: String, source: String) -> Dictionary:
	var inputs := {}
	var first := _add_input(inputs,source)
	if not bool(first.ok): return first
	if kind == "world":
		var manifest := Cache._read(source)
		if manifest.is_empty() or manifest.has("streamingChunks"): return {"ok":false,"error":"Only complete leaf maps can be prepared."}
		var roads: Dictionary = preload("res://src/world/road_ground/road_ground.gd").dependency_closure(manifest.get("roadGround", {}), source)
		if not bool(roads.get("ok", false)): return roads
		for path: String in roads.get("files", {}):
			var road_input := _add_input(inputs, path, str(roads.files[path]))
			if not bool(road_input.ok): return road_input
		var glb := _relative_source(source.get_base_dir(),str(manifest.get("asset",{}).get("glb","")))
		var geometry := _add_input(inputs,glb)
		if not bool(geometry.ok): return geometry
		var images := _declared_inputs(glb.get_base_dir(),manifest.get("externalResources",{}),inputs)
		if not bool(images.ok): return images
		var meshes := _declared_inputs(glb.get_base_dir(),manifest.get("externalMeshes",{}),inputs)
		if not bool(meshes.ok): return meshes
		var actual := _gltf_inputs(glb,images,true,inputs)
		if not bool(actual.ok): return actual
		var declared_keys := {}
		var indexes := {}
		for logical: String in meshes.paths:
			var prototype := _prototype_inputs(Sources.source_path(logical),str(meshes.paths[logical]),inputs,indexes)
			if not bool(prototype.ok): return prototype
			declared_keys[str(prototype.key)] = true
		for key: String in actual.prototypes:
			if not declared_keys.has(key): return {"ok":false,"error":"Undeclared shared model: "+key}
		for path: String in Cache.PIPELINE_INPUTS:
			if not FileAccess.file_exists(path): continue
			var row := _add_input(inputs,path)
			if not bool(row.ok): return row
	else:
		var actual := _gltf_inputs(source,{},false,inputs)
		if not bool(actual.ok): return actual
		if not (actual.prototypes as Dictionary).is_empty():
			return {"ok":false,"error":"Shared models need a declaring map package."}
	var rows: Array = []
	var paths: Array = inputs.keys()
	paths.sort()
	for path: String in paths: rows.append({"path":path,"sha256":inputs[path]})
	return {"ok":true,"inputs":rows}

static func _target_keys(targets: Array) -> Dictionary:
	var unique := {}
	for target: Variant in targets:
		if not target is Dictionary: return {"ok":false}
		var kind := str(target.get("kind",""))
		var source := Cache.logical(str(target.get("source","")))
		var key := kind+"|"+source
		if not kind in ["world","asset"] or source.is_empty() or unique.has(key): return {"ok":false}
		unique[key] = true
	var keys: Array = unique.keys()
	keys.sort()
	return {"ok":true,"keys":keys}

static func _source_digest(kind: String, source: String) -> String:
	if kind == "asset": return FileAccess.get_sha256(source)
	var manifest := Cache._read(source)
	return MapCache.package_digest(source,source.get_base_dir().path_join(str(manifest.get("asset",{}).get("glb",""))))

func _lock() -> bool:
	if DirAccess.make_dir_recursive_absolute(Cache.root_path()) != OK: return false
	var path := Cache.root_path().path_join("preparing.lock")
	for attempt in range(2400):
		if _cancelled: return false
		var error := DirAccess.make_dir_absolute(path)
		if error == OK:
			Cache.write_json(path.path_join("owner.json"),{"pid":OS.get_process_id()})
			return true
		var owner := Cache._read(path.path_join("owner.json"))
		var pid := int(owner.get("pid",0))
		if pid > 0 and not OS.is_process_running(pid):
			DirAccess.remove_absolute(path.path_join("owner.json"))
			DirAccess.remove_absolute(path)
			continue
		if pid == OS.get_process_id(): return false
		await get_tree().create_timer(.5).timeout
	return false

func _unlock() -> void:
	var path := Cache.root_path().path_join("preparing.lock")
	DirAccess.remove_absolute(path.path_join("owner.json"))
	DirAccess.remove_absolute(path)

func run(job: Dictionary = {}) -> Dictionary:
	var report := {"ok":false,"prepared":0,"reused":0,"collisions_prepared":0,"paving_prepared":0,"failed":[],"entries":[],"cancelled":false}
	if DisplayServer.get_name() == "headless":
		report.failed.append({"error":"World preparation needs the normal graphics renderer."})
		return report
	Cache.initialize()
	var targets: Array = job.get("targets",Cache.targets())
	var selected := _target_keys(targets)
	if targets.is_empty() or not bool(selected.ok) or not str(Cache.snapshot().scope_error).is_empty():
		report.failed.append({"error":"The world preparation scope is unavailable."})
		return report
	if not await _lock():
		report.failed.append({"error":"Another world preparation is still running."})
		return report
	var started := Time.get_ticks_msec()
	var old_vram := OS.get_environment(Vram.ENVIRONMENT)
	var old_skip := Graphics._texture_skip
	OS.set_environment(Vram.ENVIRONMENT,"0")
	Graphics._texture_skip = 0
	Vram.reconfigure()
	Cache.cooking = true
	Sources.set_recording(true)
	Sources.set_external_resolver(TexturePool.source_description)
	Quantization.ensure_registered()
	Vram.ensure_registered()
	MapMesh.ensure_registered()
	var writer := Writer.new()
	if not writer.configure(Cache.blobs_path()):
		report.failed.append({"error":"The prepared world folder is not writable."})
	else:
		for index: int in targets.size():
			if _cancelled:
				report.cancelled = true
				break
			var target: Dictionary = targets[index]
			var kind := str(target.get("kind",""))
			var source := Sources.source_path(Cache.logical(str(target.get("source",""))))
			var label := str(target.get("id",source.get_file()))
			progress.emit(index,targets.size(),label)
			if not kind in ["world","asset"] or not Cache.eligible(kind,source):
				report.failed.append({"id":label,"error":"Target is outside the configured world scope."})
				continue
			var digest := _source_digest(kind,source)
			if Cache.current(kind,source,digest):
				if kind == "world" and str(target.get("id","")).contains("__chunk_") \
						and not CollisionCache.current(source,digest):
					var entry := Cache._read(Cache.entry_path(kind,source))
					var faces := CollisionCache.write_from_geometry(entry)
					if not bool(faces.ok):
						report.failed.append({"id":label,"source":Cache.logical(source),"error":str(faces.get("error","Collision preparation failed"))})
						await get_tree().process_frame
						continue
					report.collisions_prepared += 1
				if _paving_target(target) and not PavingCache.current(source,digest):
					var entry := Cache._read(Cache.entry_path(kind,source))
					var paving := PavingCache.write_from_geometry(entry)
					if not bool(paving.ok):
						report.failed.append({"id":label,"source":Cache.logical(source),"error":str(paving.get("error","Paving preparation failed"))})
						await get_tree().process_frame
						continue
					report.paving_prepared += 1
				report.reused += 1
				report.entries.append({"id":label,"kind":kind,"source":Cache.logical(source),"reused":true})
				await get_tree().process_frame
				continue
			var prepared := _prepare_one(target,source,digest,writer)
			if bool(prepared.get("ok",false)):
				report.prepared += 1
				if bool(prepared.entry.get("collision_prepared",false)): report.collisions_prepared += 1
				if bool(prepared.entry.get("paving_prepared",false)): report.paving_prepared += 1
				report.entries.append(prepared.entry)
			else:
				report.failed.append({"id":label,"source":Cache.logical(source),"error":str(prepared.get("error","Unknown preparation error"))})
			GlbSceneCache.clear()
			# Let renderer/physics registrations and the previous raw tree retire
			# before opening another source; do not retain an entire continent.
			for frame in range(3): await get_tree().process_frame
	var expected := _target_keys(Cache.targets())
	var complete: bool = report.failed.is_empty() and not bool(report.cancelled) and bool(expected.ok) \
		and selected["keys"] == expected["keys"]
	if complete:
		report.pruned = Cache.prune_unreferenced()
		report.collisions_pruned = CollisionCache.prune_unreferenced()
		report.paving_pruned = PavingCache.prune_unreferenced()
	Sources.set_recording(false)
	Sources.set_external_resolver(Callable())
	Cache.cooking = false
	Graphics._texture_skip = old_skip
	OS.set_environment(Vram.ENVIRONMENT,old_vram)
	Vram.reconfigure()
	GlbSceneCache.clear()
	report.ok = report.failed.is_empty() and not bool(report.cancelled)
	report.elapsed_ms = Time.get_ticks_msec()-started
	report.policy = Cache.policy()
	report.targets = targets.size()
	if bool(job.get("release_preparation",false)):
		var collision_keys: Array = []
		var paving_keys: Array = []
		for target: Dictionary in targets:
			var key := str(target.kind)+"|"+Cache.logical(str(target.source))
			if str(target.kind) == "world" and str(target.id).contains("__chunk_"):
				collision_keys.append(key)
			if _paving_target(target): paving_keys.append(key)
		collision_keys.sort()
		paving_keys.sort()
		var engine := Engine.get_version_info()
		report.release_metadata = {"scope_complete":complete,"platform":OS.get_name(),
			"renderer":RenderingServer.get_current_rendering_method(),
			"engine":{"hash":str(engine.get("hash","")),"string":str(engine.get("string",""))},
			"engine_executable_sha256":FileAccess.get_sha256(OS.get_executable_path()),
			"user_data_path":ProjectSettings.globalize_path("user://"),
			"geometry_policy":Cache.policy(),"geometry_schema":Cache.VERSION,
			"geometry_root":Cache.root_path(),
			"collision_policy":CollisionCache.policy(),"paving_policy":PavingCache.policy(),
			"scope_sha256":FileAccess.get_sha256(Cache.SCOPE),
			"registry_sha256":FileAccess.get_sha256(Cache.REGISTRY),
			"target_keys":selected.get("keys",[]),"collision_target_keys":collision_keys,
			"paving_target_keys":paving_keys}
	if complete and not Cache.write_json(Cache.root_path().path_join("complete.json"),{"signature":Cache.startup_signature(),
			"targets":targets.size(),"target_keys":selected["keys"],"policy":Cache.policy(),"input_hints":Cache.input_hints()}):
		report.failed.append({"error":"The completed world preparation could not be recorded."})
		report.ok = false
	progress.emit(targets.size(),targets.size(),"")
	_unlock()
	return report

func _prepare_one(target: Dictionary, source: String, digest: String, writer: RefCounted) -> Dictionary:
	var kind := str(target.kind)
	var base := _base_inputs(kind,source)
	if not bool(base.get("ok",false)): return base
	var loader: WorldLoader
	var packed: PackedScene
	if kind == "world":
		loader = WorldLoader.new()
		loader.geometry_capture = true
		add_child(loader)
		loader.load_world(source,Vector3.INF,true)
		if loader.world_root != null: packed = loader.take_geometry_snapshot()
	else:
		packed = GlbSceneCache._build_raw(source)
	if packed == null:
		if loader != null:
			loader.unload_world()
			loader.queue_free()
		return {"ok":false,"error":"The source scene could not be prepared."}
	var prototype_keys := MeshPool.source_keys()
	writer.external_mesh_ids = prototype_keys
	var written: Dictionary = writer.write(packed)
	if loader != null:
		loader.unload_world()
		loader.queue_free()
	if not bool(written.get("ok",false)): return written
	if _source_digest(kind,source) != digest: return {"ok":false,"error":"The source changed during world preparation."}
	var inputs := {}
	for row: Dictionary in base.inputs+written.inputs:
		if inputs.has(str(row.path)) and str(inputs[str(row.path)]) != str(row.sha256):
			return {"ok":false,"error":"Source dependencies changed during preparation."}
		inputs[str(row.path)] = str(row.sha256)
	var rows: Array = []
	var paths: Array = inputs.keys()
	paths.sort()
	for path: String in paths: rows.append({"path":path,"sha256":inputs[path]})
	var shared_meshes := {}
	for identity: Variant in prototype_keys:
		if writer.saved_paths.has(identity): shared_meshes[str(writer.saved_paths[identity])] = str(prototype_keys[identity])
	var entry := {"schema":Cache.VERSION,"policy":Cache.policy(),"kind":kind,"source":Cache.logical(source),
		"source_digest":digest,"primary":str(written.path),"payloads":written.payloads,"bindings":written.bindings,
		"shared_meshes":shared_meshes,"inputs":rows,"id":str(target.get("id",""))}
	if not Cache.publish(entry): return {"ok":false,"error":"Prepared world data changed or could not be recorded."}
	if kind == "world" and str(target.get("id","")).contains("__chunk_"):
		var faces := CollisionCache.write_packed(packed,source,digest,rows)
		if not bool(faces.ok): return faces
	if _paving_target(target):
		var paving := PavingCache.write_packed(packed,source,digest,rows)
		if not bool(paving.ok): return paving
	return {"ok":true,"entry":{"id":entry.id,"kind":kind,"source":entry.source,"primary":entry.primary,
		"payloads":entry.payloads.size(),"textures":entry.bindings.size(),"reused":false,
		"collision_prepared":kind == "world" and str(target.get("id","")).contains("__chunk_"),
		"paving_prepared":_paving_target(target)}}

func show_and_run(job: Dictionary = {}) -> Dictionary:
	var canvas := CanvasLayer.new()
	canvas.layer = 100
	var background := ColorRect.new()
	background.color = Color(.035,.043,.055,1)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	canvas.add_child(background)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.add_child(center)
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(420,0)
	center.add_child(column)
	var label := Label.new()
	label.text = "Preparing Rabbit Lands world data…"
	column.add_child(label)
	var bar := ProgressBar.new()
	column.add_child(bar)
	var detail := Label.new()
	detail.text = "This happens after installation or an update."
	column.add_child(detail)
	var skip := Button.new()
	skip.text = "Skip for now"
	skip.tooltip_text = "Prepared maps are kept. Preparation resumes next time you open the client."
	skip.pressed.connect(func() -> void:
		skip.disabled = true
		cancel())
	column.add_child(skip)
	add_child(canvas)
	var update := func(done: int,total: int,_name: String) -> void:
		bar.max_value = maxi(1,total)
		bar.value = done
		label.text = "Preparing world data… %d of %d" % [done,total]
	progress.connect(update)
	await get_tree().process_frame
	var report := await run(job)
	progress.disconnect(update)
	canvas.queue_free()
	return report

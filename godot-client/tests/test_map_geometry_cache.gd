extends SceneTree
## Small isolated contract checks for geometry-cache validation/publication.
## No authored map or player cache is mutated by these fixtures.
const Cache := preload("res://src/world/map_geometry_cache.gd")
const Writer := preload("res://src/world/map_geometry_writer.gd")
const SOURCE := "user://map-geometry-cache-tests/source.glb"
const DEPENDENCY := "user://map-geometry-cache-tests/dependency.json"
var _failures := 0
var _entry: Dictionary = {}
var _source_digest := ""
var _source_bytes := "source-geometry-v1".to_utf8_buffer()
var _dependency_bytes := "dependency-state-v1".to_utf8_buffer()
var _blob_bytes := PackedByteArray()

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if value: print("ok ",message)
	else:
		_failures += 1
		push_error("FAIL "+message)

func _bytes(path: String, value: PackedByteArray) -> bool:
	if DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK: return false
	var file := FileAccess.open(path,FileAccess.WRITE)
	if file == null: return false
	file.store_buffer(value)
	file.flush()
	var error := file.get_error()
	file.close()
	return error == OK

func _publish(value: Dictionary) -> bool:
	Cache.cooking = true
	var result := Cache.publish(value)
	Cache.cooking = false
	return result

func _acquire() -> Dictionary:
	return Cache.acquire("asset",SOURCE,_source_digest)

func _miss(record: Dictionary, reason: String) -> bool:
	return str(record.get("status","")) == "miss" and str(record.get("reason","")) == reason

func _fixture() -> bool:
	if not _bytes(SOURCE,_source_bytes) or not _bytes(DEPENDENCY,_dependency_bytes): return false
	_source_digest = FileAccess.get_sha256(SOURCE)
	var node := Node3D.new()
	node.name = "GeometryFixture"
	var child := Node3D.new()
	child.name = "Landmark"
	child.position = Vector3(2,3,4)
	node.add_child(child)
	child.owner = node
	var packed := PackedScene.new()
	var packed_ok := packed.pack(node) == OK
	node.free()
	if not packed_ok: return false
	var writer := Writer.new()
	if not writer.configure(Cache.blobs_path()): return false
	var written: Dictionary = writer.write(packed)
	if not bool(written.get("ok",false)):
		push_error("fixture writer: "+str(written.get("error","")))
		return false
	_entry = {"schema":Cache.VERSION,"policy":Cache.policy(),"kind":"asset","source":SOURCE,
		"source_digest":_source_digest,"primary":written.path,"payloads":written.payloads,
		"bindings":written.bindings,"shared_meshes":{},"generation":"first",
		"inputs":[{"path":SOURCE,"sha256":_source_digest},
			{"path":DEPENDENCY,"sha256":FileAccess.get_sha256(DEPENDENCY)}]}
	_blob_bytes = FileAccess.get_file_as_bytes(str(written.path))
	return true

func _run() -> void:
	var old_environment := OS.get_environment("ELORIA_NO_GEOMETRY_CACHE")
	OS.unset_environment("ELORIA_NO_GEOMETRY_CACHE")
	Cache.initialize()
	_run_scope_contracts()
	if str(Cache._read("res://data/client_release.json").get("platform","source")) == "source":
		_expect(not Cache._has_release_identity(),"source release stub keeps development preparation hints enabled")
	var old_targets: Dictionary = Cache._targets
	var old_roots: Dictionary = Cache._roots
	var old_scope := Cache._scope_error
	var old_cooking := Cache.cooking
	Cache._targets = old_targets.duplicate()
	Cache._targets["asset|"+SOURCE] = {"kind":"asset","source":SOURCE,"id":"geometry-cache-test"}
	Cache._roots = old_roots.duplicate()
	Cache._scope_error = ""
	Cache.cooking = false
	_expect(_fixture(),"isolated geometry fixture is writable")
	if not _entry.is_empty():
		_run_contracts()
	Cache._targets = old_targets
	Cache._roots = old_roots
	Cache._scope_error = old_scope
	Cache.cooking = old_cooking
	if old_environment.is_empty(): OS.unset_environment("ELORIA_NO_GEOMETRY_CACHE")
	else: OS.set_environment("ELORIA_NO_GEOMETRY_CACHE",old_environment)
	print("map geometry cache: ","PASS" if _failures == 0 else "FAIL"," (",_failures,")")
	quit(_failures)

func _run_scope_contracts() -> void:
	var registry: Dictionary = Cache._read(Cache.REGISTRY).get("maps",{})
	var scope := Cache._read(Cache.SCOPE)
	var candidates := Cache._read("res://data/maps/geometry-cache-interior-candidates.json")
	var interiors := {"landfall_insides":true}
	for key: String in registry:
		var row: Dictionary = registry[key]
		if not row.has("interiorOf") and not row.has("insidesOf"): continue
		var resolved := MapRegistry.resolve(registry,key)
		var canonical := str(resolved.get("registryKey",""))
		if not canonical.contains("gauntlet"): interiors[canonical] = true
	var grouped: Array = candidates.get("groups",{}).get("interiors",[])
	var covered := grouped.size() == interiors.size()
	var unique_targets := true
	var target_counts := {}
	for row: Dictionary in Cache.targets():
		if str(row.get("kind","")) == "world":
			var source := str(row.get("source",""))
			target_counts[source] = int(target_counts.get(source,0))+1
	for canonical: String in interiors:
		var source := str(MapRegistry.resolve(registry,canonical).get("manifest",""))
		var admitted := canonical == "landfall_insides"
		covered = covered and grouped.has(canonical) and (candidates.get("maps",[]) as Array).has(canonical)
		unique_targets = unique_targets and Cache.scoped_map(source) == admitted and Cache.eligible("world",source) == admitted \
			and int(target_counts.get(Cache.logical(source),0)) == (1 if admitted else 0)
	_expect(covered,"candidate inventory covers every registered non-gauntlet interior and Landfall Underground")
	_expect(unique_targets,"production admits the existing Landfall interior while extra candidates remain opt-in")
	var production_roots := {}
	for group: String in ["landfall_continent","gauntlets","landfall_insides"]:
		for identity: String in scope.get("groups",{}).get(group,[]): production_roots[identity] = true
	var production_retained := (scope.get("maps",[]) as Array).size() == production_roots.size()
	for identity: String in scope.get("maps",[]): production_retained = production_retained and production_roots.has(identity)
	_expect(production_retained,"automatic preparation retains the established production root groups")
	var aliases_covered := true
	for key: String in registry:
		if not (registry[key] as Dictionary).has("alias"): continue
		var resolved := MapRegistry.resolve(registry,key)
		if interiors.has(str(resolved.get("registryKey",""))):
			aliases_covered = aliases_covered and Cache.eligible("world",str(resolved.get("manifest",""))) == (str(resolved.registryKey) == "landfall_insides")
	_expect(aliases_covered,"interior aliases follow their canonical production admission")

func _run_contracts() -> void:
	var metadata := Cache.entry_path("asset",SOURCE)
	# Remove only this private test entry. Blob files remain content-addressed
	# and are kept for inspection in the isolated test profile.
	if FileAccess.file_exists(metadata): DirAccess.remove_absolute(metadata)
	if FileAccess.file_exists(metadata+".previous"): DirAccess.remove_absolute(metadata+".previous")
	_expect(_miss(_acquire(),"not_prepared"),"absent entry falls back")
	_expect(not Cache.publish(_entry),"play cannot publish geometry files")
	_expect(_publish(_entry),"maintenance publishes a source-verified entry")
	_expect(str(_acquire().get("status","")) == "hit","valid native geometry is acquired")
	_expect(Cache.current("asset",SOURCE,_source_digest),"current reports a valid entry")
	var record := _acquire()
	var instance := Cache.instantiate(record)
	_expect(instance != null,"main thread instantiates a valid record")
	if instance != null:
		_expect(instance.get_node("Landmark").position == Vector3(2,3,4),"native hierarchy and transform are preserved")
		instance.free()
	_run_diagnostic_contracts()
	_expect(_miss(Cache.acquire("asset",SOURCE,_source_digest,{},false),"geometry_disabled"),"caller can explicitly bypass geometry")
	Cache.cooking = true
	_expect(_miss(_acquire(),"geometry_disabled"),"cooking cannot consume cached gameplay geometry")
	Cache.cooking = false
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE","1")
	_expect(_miss(_acquire(),"geometry_disabled"),"environment bypass retains the raw fallback")
	OS.unset_environment("ELORIA_NO_GEOMETRY_CACHE")
	_expect(_miss(Cache.acquire("asset","user://map-geometry-cache-tests/unlisted.glb",_source_digest),"outside_geometry_scope"),"unlisted source cannot opt into the cache")

	var blob := str(_entry.primary)
	_expect(DirAccess.remove_absolute(blob) == OK,"private native blob can be removed for recovery test")
	_expect(_miss(_acquire(),"geometry_payload_changed"),"missing native blob falls back")
	_expect(_bytes(blob,_blob_bytes),"native blob can be restored")
	var corrupted := _blob_bytes.duplicate()
	corrupted[corrupted.size()/2] = corrupted[corrupted.size()/2] ^ 1
	_expect(_bytes(blob,corrupted),"private native blob can be corrupted for validation test")
	_expect(_miss(_acquire(),"geometry_payload_changed"),"corrupt native bytes are rejected before loading")
	_expect(_bytes(blob,_blob_bytes),"verified native bytes are restored")

	_expect(_bytes(SOURCE,"source-geometry-v2".to_utf8_buffer()),"source bytes can change in isolated fixture")
	_expect(_miss(_acquire(),"geometry_dependency_changed"),"changed source bytes invalidate an old proof")
	_expect(_miss(Cache.acquire("asset",SOURCE,FileAccess.get_sha256(SOURCE)),"source_or_policy_changed"),"new source digest invalidates old geometry")
	_expect(_bytes(SOURCE,_source_bytes),"source fixture is restored")
	_expect(_bytes(DEPENDENCY,"dependency-state-v2".to_utf8_buffer()),"dependency can change without changing scene identity")
	_expect(_miss(_acquire(),"geometry_dependency_changed"),"changed dependency bytes invalidate geometry")
	_expect(not _publish(_entry),"maintenance refuses stale dependency proofs")
	_expect(_bytes(DEPENDENCY,_dependency_bytes),"dependency fixture is restored")

	var changed := _entry.duplicate(true)
	changed.policy = "f".repeat(64)
	_expect(_publish(changed),"wrong-policy fixture metadata is staged")
	_expect(_miss(_acquire(),"source_or_policy_changed"),"wrong engine/cook policy falls back")
	changed = _entry.duplicate(true)
	changed.schema = Cache.VERSION+1
	_expect(_publish(changed),"wrong-schema fixture metadata is staged")
	_expect(_miss(_acquire(),"source_or_policy_changed"),"unsupported cache schema falls back")

	changed = _entry.duplicate(true)
	changed.bindings = {"a".repeat(64):{"kind":"external","inputs":[
		{"path":"user://map-geometry-cache-tests/undeclared.png","sha256":"0".repeat(64)}]}}
	_expect(_publish(changed),"undeclared binding fixture metadata is staged")
	_expect(_miss(_acquire(),"geometry_binding_input_undeclared"),"binding cannot consume an undeclared source")
	changed = _entry.duplicate(true)
	changed.primary = Cache.blobs_path().path_join("../"+"b".repeat(64)+".scn").simplify_path()
	_expect(_publish(changed),"escaped primary fixture metadata is staged")
	_expect(_miss(_acquire(),"geometry_metadata_invalid"),"native primary path cannot escape its blob directory")
	changed = _entry.duplicate(true)
	changed.payloads["user://outside-geometry-cache/"+"c".repeat(64)+".res"] = "c".repeat(64)
	_expect(_publish(changed),"escaped dependency fixture metadata is staged")
	_expect(_miss(_acquire(),"geometry_payload_changed"),"native dependency cannot escape its blob directory")
	changed = _entry.duplicate(true)
	changed.payloads = {}
	_expect(_publish(changed),"undeclared primary fixture metadata is staged")
	_expect(_miss(_acquire(),"geometry_primary_undeclared"),"primary must belong to the verified payload set")
	_expect(_publish(_entry),"valid entry is restored after invalid metadata tests")

	var replacement := _entry.duplicate(true)
	replacement.generation = "replacement"
	_expect(_publish(replacement),"maintenance atomically replaces its old entry")
	_expect(str(Cache._read(metadata).get("generation","")) == "replacement","new metadata is visible after publication")
	_expect(not FileAccess.file_exists(metadata+".previous"),"completed replacement retires only its metadata backup")
	_expect(not FileAccess.file_exists(metadata+"."+str(OS.get_process_id())+".tmp"),"completed replacement leaves no staging entry")
	_expect(DirAccess.rename_absolute(metadata,metadata+".previous") == OK,"interrupted-promotion fixture is staged")
	_expect(str(_acquire().get("status","")) == "hit","previous entry is readable during a promotion gap")
	_expect(DirAccess.rename_absolute(metadata+".previous",metadata) == OK,"promotion-gap fixture is restored")

	var before_nodes := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var worker := Thread.new()
	worker.start(func() -> Dictionary:
		var acquired := _acquire()
		return {"record":acquired,"worker_instantiation":Cache.instantiate(acquired) != null})
	var completed: Dictionary = worker.wait_to_finish()
	var worker_record: Dictionary = completed.record
	_expect(str(worker_record.get("status","")) == "hit" and worker_record.get("resource") is PackedScene,"worker acquisition returns native Resources")
	_expect(not bool(completed.worker_instantiation),"worker cannot instantiate Nodes")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes,"worker acquisition creates no Nodes")
	_expect(_bytes(SOURCE,"source-geometry-v2".to_utf8_buffer()),"source changes after worker acquisition")
	var stale := Cache.instantiate(worker_record)
	_expect(stale == null,"main publication rejects a source that changed after preparation")
	if stale != null: stale.free()
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes,"stale publication creates no Nodes")
	_expect(_bytes(SOURCE,_source_bytes),"source restored for generation retirement test")
	worker_record = _acquire()
	replacement.generation = "new-generation"
	_expect(_publish(replacement),"new generation replaces an in-flight entry")
	stale = Cache.instantiate(worker_record)
	_expect(stale == null,"old-generation completion is rejected before Nodes exist")
	if stale != null: stale.free()
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes,"retired-generation publication creates no Nodes")
	var current := _acquire()
	instance = Cache.instantiate(current)
	_expect(instance != null,"new generation remains playable")
	if instance != null: instance.free()
	_expect(_publish(_entry),"private fixture metadata restored for a repeatable test")

func _run_diagnostic_contracts() -> void:
	var old_environment := OS.get_environment(Cache.DIAGNOSTICS_ENVIRONMENT)
	OS.unset_environment(Cache.DIAGNOSTICS_ENVIRONMENT)
	var ordinary := _acquire()
	_expect((ordinary.get("diagnostics",{}) as Dictionary).is_empty(),"ordinary acquisition retains no fine diagnostic counters")
	OS.set_environment(Cache.DIAGNOSTICS_ENVIRONMENT,"1")
	var record := _acquire()
	var diagnostics: Dictionary = record.get("diagnostics",{})
	var counts: Dictionary = diagnostics.get("counts",{})
	_expect(int(counts.get("entryValidationCalls",0)) == 1 and int(counts.get("sourceHashCalls",0)) == 2 \
		and int(counts.get("payloadHashCalls",0)) == 1,"optional diagnostic counts the existing validation operations")
	_expect(int(counts.get("sourceHashBytes",0)) == _source_bytes.size()+_dependency_bytes.size() \
		and int(counts.get("payloadHashBytes",0)) == _blob_bytes.size(),"optional diagnostic records exact source and payload byte totals")
	var instance := Cache.instantiate(record)
	counts = diagnostics.get("counts",{})
	_expect(instance != null and int(counts.get("entryValidationCalls",0)) == 2 \
		and int(counts.get("templateDataOnlyCalls",0)) == 1 and int(counts.get("textureApplyCalls",0)) == 1,
		"optional publication diagnostics preserve validation and template safety checks")
	var phases: Dictionary = record.get("timings_us",{})
	_expect(phases.has("geometryVerifySourceSha") and phases.has("geometryVerifyPayloadSha") \
		and phases.has("geometryTexturePoolUpload") and phases.has("geometryTextureSlotGraph") \
		and phases.has("geometryTemplateDataOnly"),"optional diagnostic splits hashing, texture publication and template traversal")
	if instance != null: instance.free()
	if old_environment.is_empty(): OS.unset_environment(Cache.DIAGNOSTICS_ENVIRONMENT)
	else: OS.set_environment(Cache.DIAGNOSTICS_ENVIRONMENT,old_environment)

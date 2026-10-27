extends SceneTree
const Cache := preload("res://src/world/map_collision_cache.gd")
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const SOURCE := "user://collision-cache-tests/world.json"
const DEPENDENCY := "user://collision-cache-tests/dependency.glb"
var _checks := 0
var _failures := 0
var _digest := ""
var _inputs: Array = []
var _packed: PackedScene
var _entry := {}
var _points := PackedVector3Array([Vector3(-1.2345,0,-1.4321),Vector3(1.1234,0,-1.4321),Vector3(-1.2345,0,1.5432)])

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> void:
	_checks += 1
	if not ok:
		_failures += 1
		push_error(label)

func _bytes(path: String, bytes: PackedByteArray) -> bool:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	return Cache._write_bytes(path,bytes)

func _scene(conflict := false, transformed := false) -> PackedScene:
	var root_node := Node3D.new()
	root_node.name = "Fixture"
	var mesh := MeshInstance3D.new()
	mesh.name = "Ground"
	root_node.add_child(mesh)
	mesh.owner = root_node
	for index: int in 2:
		var body := StaticBody3D.new()
		body.name = "Collision"+str(index)
		mesh.add_child(body)
		body.owner = root_node
		if transformed: body.position = Vector3.ONE
		var collision := CollisionShape3D.new()
		collision.name = "Shape"
		var shape := ConcavePolygonShape3D.new()
		var faces := _points.duplicate()
		if conflict and index == 1: faces[0] += Vector3.ONE
		shape.set_faces(faces)
		collision.shape = shape
		body.add_child(collision)
		collision.owner = root_node
	var navigation := StaticBody3D.new()
	navigation.name = "Navigation"
	root_node.add_child(navigation)
	navigation.owner = root_node
	var shape_node := CollisionShape3D.new()
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(_points)
	shape_node.shape = shape
	navigation.add_child(shape_node)
	shape_node.owner = root_node
	var packed := PackedScene.new()
	_expect(packed.pack(root_node) == OK,"fixture packs")
	root_node.free()
	return packed

func _acquire() -> Dictionary:
	return Cache.acquire(SOURCE,_digest)

func _data(value: Variant) -> bool:
	if value is Object or value is Callable or value is Signal: return false
	if value is Dictionary:
		for key: Variant in value:
			if not _data(key) or not _data(value[key]): return false
	elif value is Array:
		for item: Variant in value:
			if not _data(item): return false
	return true

func _malformed(raw: PackedByteArray) -> void:
	var bytes := "RLCC".to_ascii_buffer()
	bytes.resize(16)
	bytes.encode_u32(4,Cache.VERSION)
	bytes.encode_u32(8,raw.size())
	bytes.encode_u32(12,FileAccess.COMPRESSION_ZSTD)
	bytes.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))
	var entry := _entry.duplicate(true)
	entry.sha256 = Sources.digest_bytes(bytes)
	entry.blob = Cache._root().path_join("blobs/"+str(entry.sha256)+".rlc")
	entry.raw_bytes = raw.size()
	entry.blob_bytes = bytes.size()
	_expect(_bytes(entry.blob,bytes) and Cache._write_metadata(Cache._entry_path(SOURCE),entry),"malformed private fixture saves")

func _contracts() -> void:
	Cache.clear_disk()
	_expect(not bool(_acquire().ok),"absent cache falls back")
	var before := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var written := Cache.write_packed(_packed,SOURCE,_digest,_inputs)
	_expect(bool(written.ok),"maintenance publishes exact cooked faces")
	if not bool(written.ok):
		print("fixture error ",written)
		return
	_entry = written.entry
	_expect(not written.has("faces"),"producer summary releases face buffers")
	_expect(int(written.coverage.concave_shapes) == 3 and int(written.coverage.mesh_paths) == 1
		and int(written.coverage.duplicate_shapes) == 1 and int(written.coverage.unmapped_shapes) == 1,"coverage distinguishes duplicate and nonmesh shapes")
	var result := _acquire()
	_expect(bool(result.ok) and result.faces.get("Ground") == _points,"face order, winding and nongrid coordinates are exact")
	_expect(int(result.bytes) == _points.size()*12 and _data(result),"reader returns only typed CPU data with byte accounting")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before,"reader and producer instantiate no Nodes")
	_expect(Cache.current(SOURCE,_digest),"current validates completed collision data")
	var again := Cache.write_packed(_packed,SOURCE,_digest,_inputs)
	_expect(bool(again.ok) and again.entry.blob == _entry.blob,"identical writes deduplicate compressed blobs")
	_expect(not bool(Cache.write_packed(_scene(true),SOURCE,_digest,_inputs).ok),"different duplicate mesh faces reject publication")
	_expect(not bool(Cache.write_packed(_scene(false,true),SOURCE,_digest,_inputs).ok),"transformed child shapes cannot replace mesh-local faces")
	_expect(bool(_acquire().ok),"failed producer leaves previous valid data")
	var blob := FileAccess.get_file_as_bytes(_entry.blob)
	var corrupt := blob.duplicate()
	corrupt[corrupt.size()-1] ^= 1
	_expect(_bytes(_entry.blob,corrupt) and not bool(_acquire().ok),"bad full blob hash rejects before decode")
	_expect(_bytes(_entry.blob,blob),"blob restores")
	_expect(DirAccess.remove_absolute(_entry.blob) == OK and not bool(_acquire().ok),"missing blob falls back")
	_expect(_bytes(_entry.blob,blob),"missing blob restores")
	_expect(_bytes(DEPENDENCY,"changed".to_utf8_buffer()) and not bool(_acquire().ok),"changed dependency invalidates collision")
	_expect(not bool(Cache.write_packed(_packed,SOURCE,_digest,_inputs).ok),"producer refuses stale input proofs")
	_expect(_bytes(DEPENDENCY,"dependency".to_utf8_buffer()),"dependency restores")
	_expect(not bool(Cache.acquire(SOURCE,"f".repeat(64)).ok),"changed package digest rejects old entry")
	for field: String in ["policy","source","source_digest","schema","blob","raw_bytes","blob_bytes","points"]:
		var changed := _entry.duplicate(true)
		match field:
			"policy","source_digest": changed[field] = "e".repeat(64)
			"source": changed[field] = "user://collision-cache-tests/other.json"
			"schema": changed[field] = Cache.VERSION+1
			"blob": changed[field] = Cache._root().path_join("../escape.rlc")
			"raw_bytes": changed[field] = Cache.MAX_RAW_BYTES+1
			"blob_bytes": changed[field] = Cache.MAX_BLOB_BYTES+1
			"points": changed[field] = _points.size()+3
		_expect(Cache._write_metadata(Cache._entry_path(SOURCE),changed) and not bool(_acquire().ok),"invalid metadata falls back: "+field)
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),_entry),"valid metadata restores")
	_expect(Cache._layout(var_to_bytes({"Mesh":_points})),"preflight accepts only the expected serialized layout")
	_expect(not Cache._layout(var_to_bytes({"Mesh":{"nested":_points}})),"nested serialized data rejects before decoding")
	_expect(not Cache._layout(var_to_bytes({"Mesh":[Vector3.ZERO,Vector3.ONE,Vector3.UP]})),"generic vector arrays cannot replace typed arrays")
	var raw := var_to_bytes({"Mesh":_points})
	_expect(not Cache._layout(raw.slice(0,raw.size()-1)),"truncated serialized vectors reject")
	_malformed(var_to_bytes({"Mesh":{"nested":_points}}))
	_expect(not bool(_acquire().ok),"valid hash cannot qualify invalid Variant layout")
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),_entry),"valid metadata restores after malformed fixture")
	for path: String in ["../escape","/absolute","Mesh:property","Mesh//Child"]:
		_expect(not bool(Cache._faces({path:_points}).ok),"node path is confined: "+path)
	var invalid := _points.duplicate()
	invalid[0] = Vector3(INF,0,0)
	_expect(not bool(Cache._faces({"Mesh":invalid}).ok),"finite coordinate bounds are mandatory")
	invalid[0] = Vector3(Cache.MAX_COORDINATE+1,0,0)
	_expect(not bool(Cache._faces({"Mesh":invalid}).ok),"coordinate magnitude is bounded")
	var metadata := Cache._entry_path(SOURCE)
	_expect(DirAccess.rename_absolute(metadata,metadata+".previous") == OK and bool(_acquire().ok),"reader tolerates atomic promotion gap")
	_expect(DirAccess.rename_absolute(metadata+".previous",metadata) == OK,"promotion fixture restores")
	var worker := Thread.new()
	_expect(worker.start(func() -> Dictionary:
		return {"record":_acquire(),"write":Cache.write_packed(_packed,SOURCE,_digest,_inputs)}) == OK,"reader worker starts")
	while worker.is_alive(): await process_frame
	var completed: Dictionary = worker.wait_to_finish()
	_expect(bool(completed.record.ok) and _data(completed.record),"worker receives only CPU vectors/data")
	_expect(not bool(completed.write.ok),"worker cannot produce maintenance data")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before,"worker creates no Nodes")
	var temporary := "user://map-geometry-cache/"+"a".repeat(64)+"/blobs/native.scn"
	DirAccess.make_dir_recursive_absolute(temporary.get_base_dir())
	_expect(ResourceSaver.save(_packed,temporary) == OK,"native fixture saves")
	var sha := FileAccess.get_sha256(temporary)
	var native := temporary.get_base_dir().path_join(sha+".scn")
	if FileAccess.file_exists(native): DirAccess.remove_absolute(temporary)
	else: DirAccess.rename_absolute(temporary,native)
	var geometry := {"kind":"world","source":SOURCE,"source_digest":_digest,"primary":native,"payloads":{native:sha},"inputs":_inputs}
	var converted := Cache.write_from_geometry(geometry)
	_expect(bool(converted.ok) and converted.entry.blob == _entry.blob,"existing native geometry yields the identical CPU collision blob")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before,"native extraction creates no Nodes")
	_expect(_bytes(native,"corrupt native".to_utf8_buffer()) and not bool(Cache.write_from_geometry(geometry).ok),"changed native bytes reject before loading")
	var keep := Cache._root().path_join("blobs/keep.txt")
	_expect(_bytes(keep,"unrelated".to_utf8_buffer()),"unrelated evidence fixture saves")
	var orphan := Cache._root().path_join("blobs/"+"f".repeat(64)+".rlc")
	_expect(_bytes(orphan,"orphan".to_utf8_buffer()) and Cache.prune_unreferenced() == 0,"pruning requires a producer lock")
	var owner := "user://map-geometry-cache/"+"b".repeat(64)+"/preparing.lock/owner.json"
	_expect(_bytes(owner,JSON.stringify({"pid":OS.get_process_id()}).to_utf8_buffer()),"producer-lock fixture saves")
	_expect(Cache.busy() and Cache.clear_disk() == 0,"clear cannot race active geometry preparation")
	_expect(Cache.prune_unreferenced() > 0 and not FileAccess.file_exists(orphan) and FileAccess.file_exists(_entry.blob),"pruning preserves referenced blobs")
	DirAccess.remove_absolute(owner)
	DirAccess.remove_absolute(owner.get_base_dir())
	_expect(Cache.total_bytes() > 0 and Cache.clear_disk() > 0,"size and clear include finished cache files")
	_expect(FileAccess.file_exists(keep),"clear preserves unrelated evidence")

func _run() -> void:
	_expect(_bytes(SOURCE,"{\"fixture\":1}".to_utf8_buffer()) and _bytes(DEPENDENCY,"dependency".to_utf8_buffer()),"private source fixtures save")
	_digest = FileAccess.get_sha256(SOURCE)
	_inputs = [{"path":SOURCE,"sha256":_digest},{"path":DEPENDENCY,"sha256":FileAccess.get_sha256(DEPENDENCY)}]
	_packed = _scene()
	await _contracts()
	print("map collision cache: ","PASS" if _failures == 0 else "FAIL"," (",_checks," checks, ",_failures," failures)")
	quit(0 if _failures == 0 else 1)

extends SceneTree
const Cache := preload("res://src/world/map_paving_cache.gd")
const Faces := preload("res://src/world/map_collision_cache.gd")
const Ground := preload("res://src/world/look/look_ground.gd")
const SOURCE := "user://paving-cache-tests/world.json"
const DEPENDENCY := "user://paving-cache-tests/geometry.glb"
var _failures := 0
var _checks := 0
var _digest := ""
var _inputs: Array = []
var _raw: ArrayMesh
var _packed: PackedScene
var _entry := {}

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> void:
	_checks += 1
	if not ok:
		_failures += 1
		push_error(label)

func _bytes(path: String, value: String) -> bool:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	return Faces._write_bytes(path,value.to_utf8_buffer())

func _mesh() -> ArrayMesh:
	var mesh := ArrayMesh.new()
	mesh.resource_name = "RawPaving"
	for surface: int in 2:
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-1,0,-1),Vector3(1,0,-1),Vector3(1,0,1),Vector3(-1,0,1),Vector3.ZERO]) \
			if surface == 0 else PackedVector3Array([Vector3(3.23456,0,-1.23456),Vector3(4.34567,0,0),Vector3(3.23456,0,1.34567)])
		var normals := PackedVector3Array()
		var uvs := PackedVector2Array()
		var tangents := PackedFloat32Array()
		for index: int in (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size():
			normals.append(Vector3.UP)
			uvs.append(Vector2(index*0.125,index*0.25))
			tangents.append_array(PackedFloat32Array([1,0,0,1]))
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_TANGENT] = tangents
		arrays[Mesh.ARRAY_TEX_UV] = uvs
		if surface == 0: arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,4,1,2,4,2,3,4,3,0,4])
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		mesh.surface_set_name(surface,"Surface"+str(surface))
		var material := StandardMaterial3D.new()
		material.resource_name = "Material"+str(surface)
		mesh.surface_set_material(surface,material)
	return mesh

func _tree() -> Node3D:
	var node := Node3D.new()
	node.name = "Fixture"
	for index: int in 2:
		var instance := MeshInstance3D.new()
		instance.name = "Walk_garden_paving_"+str(index)
		instance.mesh = _raw
		node.add_child(instance)
		instance.owner = node
	return node

func _same_arrays(a: ArrayMesh, b: ArrayMesh) -> bool:
	if a.get_surface_count() != b.get_surface_count(): return false
	for surface: int in a.get_surface_count():
		if a.surface_get_name(surface) != b.surface_get_name(surface): return false
		var x := a.surface_get_arrays(surface)
		var y := b.surface_get_arrays(surface)
		for slot: int in Mesh.ARRAY_MAX:
			if typeof(x[slot]) != typeof(y[slot]): return false
			if x[slot] == null: continue
			if x[slot].to_byte_array() != y[slot].to_byte_array(): return false
	return true

func _acquire() -> Dictionary:
	return Cache.acquire(SOURCE,_digest)

func _contracts() -> void:
	Cache.clear_disk()
	var bounds_mesh := ArrayMesh.new()
	var bounds_arrays := []
	bounds_arrays.resize(Mesh.ARRAY_MAX)
	bounds_arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-17.412857055664062,0,-43.846858978271484),Vector3(48.125999450683594,0,-43.846858978271484),Vector3(0,0,-17.80806541442871)])
	bounds_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,bounds_arrays)
	var restored: Dictionary = JSON.parse_string(JSON.stringify(Cache._signature(bounds_mesh),"",true,true))
	_expect(Cache._matches(bounds_mesh,restored),"JSON decimal bounds restore exact native real precision")
	restored.aabb[2] = float(restored.aabb[2])+0.01
	_expect(not Cache._matches(bounds_mesh,restored),"native bounds mismatch still rejects exactly")
	_expect(not bool(_acquire().ok),"absent paving data falls back")
	var before := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var written := Cache.write_packed(_packed,SOURCE,_digest,_inputs)
	_expect(bool(written.ok),"offline producer bakes eligible paving")
	if not bool(written.ok):
		print(written)
		return
	_entry = written.entry
	_expect(written.coverage.mesh_paths == 2,"both stable MeshInstance paths are recorded")
	var legacy := Ground.kit_paving_mesh(_raw)
	var record := _acquire()
	_expect(bool(record.ok),"native paving meshes acquire")
	if not bool(record.ok):
		print(record)
		return
	var paths: Array = record.meshes.keys()
	paths.sort()
	for path: String in paths:
		var mesh := record.meshes[path] as ArrayMesh
		_expect(_same_arrays(mesh,legacy),"all vertex/index/normal/tangent/UV/COLOR bytes equal legacy: "+path)
		_expect(mesh.get_meta(Ground.KIT_MESH_META,false) == true,"native paving carries exact feather marker")
		for surface: int in mesh.get_surface_count():
			_expect(mesh.surface_get_material(surface) == null,"native paving contains no texture/material resources")
	_expect(record.meshes[paths[0]] != record.meshes[paths[1]],"each path owns a private mesh even when native bytes deduplicate")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before,"producer/acquire create no Nodes")
	var repeated := Cache.write_packed(_packed,SOURCE,_digest,_inputs)
	_expect(bool(repeated.ok) and repeated.entry.meshes[paths[0]].blob == _entry.meshes[paths[0]].blob,"identical offline writes deduplicate native payloads")
	var node := _tree()
	var second := node.get_node(paths[1]) as MeshInstance3D
	second.mesh = _raw.duplicate(false) as ArrayMesh
	var current := StandardMaterial3D.new()
	current.albedo_color = Color(0.2,0.4,0.6)
	second.mesh.surface_set_material(0,current)
	_expect(Cache.apply(record,node) == 2,"owning thread applies baked geometry before painting")
	_expect((node.get_node(paths[0]) as MeshInstance3D).mesh.surface_get_material(0) == _raw.surface_get_material(0)
		and second.mesh.surface_get_material(0) == current,"current runtime materials retain exact identity per private mesh")
	_expect((node.get_node(paths[0]) as MeshInstance3D).mesh != second.mesh,"per-node surface material changes cannot leak")
	_expect(record.meshes.is_empty() and Cache.apply(record,node) == 0,"successful application releases record carriers and is idempotent")
	_expect(not _raw.has_meta(Ground.KIT_MESH_META) and (_raw.surface_get_format(0) & Mesh.ARRAY_FORMAT_COLOR) == 0,"raw pooled source mesh remains untouched")
	node.free()
	var stale := _acquire()
	var unchanged := _tree()
	_expect(_bytes(DEPENDENCY,"changed") and Cache.apply(stale,unchanged) == 0,"source mutation after acquire rejects before swapping any node")
	_expect((unchanged.get_node(paths[0]) as MeshInstance3D).mesh == _raw,"stale failure leaves raw tree unchanged")
	unchanged.free()
	_expect(not bool(_acquire().ok),"changed source dependency rejects acquisition")
	_expect(_bytes(DEPENDENCY,"dependency"),"private dependency restores")
	var wrong_tree := _tree()
	(wrong_tree.get_node(paths[1]) as MeshInstance3D).mesh = ArrayMesh.new()
	_expect(Cache.apply(_acquire(),wrong_tree) == 0 and (wrong_tree.get_node(paths[0]) as MeshInstance3D).mesh == _raw,
		"one ineligible path rejects the whole plan before mutation")
	wrong_tree.free()
	var escaped := _entry.duplicate(true)
	escaped.meshes[paths[0]].blob = "user://outside/paving.res"
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),escaped) and not bool(_acquire().ok),"native payload path escape rejects")
	var changed := _entry.duplicate(true)
	changed.region.sha256 = "f".repeat(64)
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),changed) and not bool(_acquire().ok),"region JSON provenance must match")
	changed = _entry.duplicate(true)
	changed.policy = "e".repeat(64)
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),changed) and not bool(_acquire().ok),"wrong engine/coverage policy rejects")
	changed = _entry.duplicate(true)
	changed.meshes[paths[0]].erase("raw")
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),changed) and not bool(_acquire().ok),"missing raw-mesh signature rejects without runtime errors")
	changed = _entry.duplicate(true)
	changed.meshes[paths[0]].baked.surfaces[0].vertices = Cache.MAX_VERTICES+1
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),changed) and not bool(_acquire().ok),"native allocation counts are bounded before Resource loading")
	_expect(Cache._write_metadata(Cache._entry_path(SOURCE),_entry),"valid metadata restores")
	var blob := str(_entry.meshes[paths[0]].blob)
	var original := FileAccess.get_file_as_bytes(blob)
	_expect(Faces._write_bytes(blob,"corrupt".to_utf8_buffer()) and not bool(_acquire().ok),"full native hash and length reject corruption before load")
	_expect(Faces._write_bytes(blob,original),"native payload restores")
	var worker := Thread.new()
	worker.start(func() -> Dictionary: return _acquire())
	while worker.is_alive(): await process_frame
	var worker_record: Dictionary = worker.wait_to_finish()
	_expect(bool(worker_record.ok) and worker_record.meshes[paths[0]] is ArrayMesh,"worker acquisition returns private Resources only")
	var released: WeakRef = weakref(worker_record.meshes[paths[0]])
	worker_record.clear()
	_expect(released.get_ref() == null,"cancelled private native candidates release without a pool alias")
	worker = Thread.new()
	worker.start(func() -> Dictionary:
		var ready := _acquire()
		var tree := _tree()
		var applied := Cache.apply(ready,tree)
		tree.free()
		return {"applied":applied,"released":ready.meshes.is_empty()})
	while worker.is_alive(): await process_frame
	var worker_applied: Dictionary = worker.wait_to_finish()
	_expect(int(worker_applied.applied) == 2 and bool(worker_applied.released),"owning detached worker binds private geometry without main-thread Node publication")
	_expect(Cache.total_bytes() > 0 and Cache.current(SOURCE,_digest),"maintenance size/current validate finished native files")
	_expect(Cache.clear_disk() > 0 and not bool(_acquire().ok),"clear removes only owned native products and metadata")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.PAINTED_GROUND)
	_expect(_bytes(SOURCE,"{\"asset\":{\"id\":\"landfall__chunk_fixture\"}}") and _bytes(DEPENDENCY,"dependency"),"private fixture sources save")
	_digest = FileAccess.get_sha256(SOURCE)
	_inputs = [{"path":SOURCE,"sha256":_digest},{"path":DEPENDENCY,"sha256":FileAccess.get_sha256(DEPENDENCY)}]
	_raw = _mesh()
	var tree := _tree()
	_packed = PackedScene.new()
	_expect(_packed.pack(tree) == OK,"paving source scene packs")
	tree.free()
	await _contracts()
	_packed = null
	_raw = null
	for frame: int in 60: await process_frame
	print("map paving cache: ","PASS" if _failures == 0 else "FAIL"," (",_checks," checks, ",_failures," failures)")
	quit(0 if _failures == 0 else 1)

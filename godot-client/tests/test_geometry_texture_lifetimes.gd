extends SceneTree
## Isolated contracts for call-owned containers and Main-only early binding.
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const Cache := preload("res://src/world/map_geometry_cache.gd")
const Scenes := preload("res://src/actors/glb_scene_cache.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const DIRECTORY := "user://geometry-texture-lifetime-tests"
const SOURCE := DIRECTORY+"/fixture.glb"
var _failures := 0
var _checks := 0
var _origins: Dictionary = {}
var _source_bytes := PackedByteArray()
var _digest := ""
var _entry: Dictionary = {}
var _blob_bytes := PackedByteArray()

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, label: String) -> void:
	_checks += 1
	if value: print("ok ",label)
	else:
		_failures += 1
		push_error("FAIL "+label)

func _bytes(path: String, bytes: PackedByteArray) -> bool:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path,FileAccess.WRITE)
	if file == null: return false
	file.store_buffer(bytes)
	file.close()
	return true

func _make_fixture(path: String, padding := 0) -> Dictionary:
	var images: Array = []
	var encoded: Array[PackedByteArray] = []
	for index: int in 3:
		var image := Image.create(8,8,false,Image.FORMAT_RGBA8)
		image.fill(Color(0.2+index*0.2,0.3,0.6,0.8))
		encoded.append(image.save_png_to_buffer())
		images.append({"uri":"data:image/png;base64,"+Marshalls.raw_to_base64(encoded[-1])})
	var binary := PackedByteArray()
	binary.resize(36+padding)
	for index: int in 9: binary.encode_float(index*4,float([0,0,0,1,0,0,0,0,1][index]))
	var document := {"asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":[0]}],
		"nodes":[{"name":"RawGeometry","mesh":0}],"buffers":[{"byteLength":binary.size()}],
		"bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":36}],
		"accessors":[{"bufferView":0,"componentType":5126,"count":3,"type":"VEC3","min":[0,0,0],"max":[1,0,1]}],
		"meshes":[{"primitives":[{"attributes":{"POSITION":0},"material":0}]}],
		"images":images,"textures":[{"source":0},{"source":1},{"source":2}],
		"materials":[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0}}}]}
	var json := JSON.stringify(document).to_utf8_buffer()
	while json.size()%4: json.append(32)
	var bytes := PackedByteArray()
	bytes.resize(20)
	bytes.encode_u32(0,0x46546c67)
	bytes.encode_u32(4,2)
	bytes.encode_u32(8,28+json.size()+binary.size())
	bytes.encode_u32(12,json.size())
	bytes.encode_u32(16,0x4e4f534a)
	bytes.append_array(json)
	var bin_header := PackedByteArray()
	bin_header.resize(8)
	bin_header.encode_u32(0,binary.size())
	bin_header.encode_u32(4,0x004e4942)
	bytes.append_array(bin_header)
	bytes.append_array(binary)
	if not _bytes(path,bytes): return {}
	var digest := Sources.digest_bytes(bytes)
	var bindings := {}
	for index: int in 3:
		var origin := {"kind":"gltf_image","file":path,"file_sha256":digest,"image_index":index,
			"image_sha256":Sources.digest_bytes(encoded[index]),"decoded_format":Image.FORMAT_RGBA8,
			"width":8,"height":8,"roles":["base"],"mip_policy":"full",
			"inputs":[{"path":path,"sha256":digest}]}
		bindings[Bindings._identity(origin)] = origin
	return {"bytes":bytes,"digest":digest,"bindings":bindings}

func _diagnostics() -> Dictionary:
	return {"timings_us":{},"counts":{}}

func _run() -> void:
	var environment := {}
	for key: String in ["ELORIA_VRAM_TEXTURES","ELORIA_NO_GEOMETRY_CACHE","ELORIA_NO_MAP_CACHE",
		"RABBITLANDS_PREPARED_CONTENT",Cache.CONTAINER_REUSE_ENVIRONMENT,Scenes.BOUND_MAIN_ENVIRONMENT]:
		environment[key] = OS.get_environment(key)
		OS.unset_environment(key)
	OS.set_environment("ELORIA_VRAM_TEXTURES","0")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT","raw")
	var old_skip := Graphics._texture_skip
	var old_enabled: Variant = MapCache._enabled_cache
	Graphics._texture_skip = 0
	MapCache._enabled_cache = true
	Vram.reconfigure()
	Cache.initialize()
	var old_targets: Dictionary = Cache._targets
	Cache._targets = old_targets.duplicate()
	Cache._targets["asset|"+SOURCE] = {"kind":"asset","source":SOURCE,"id":"texture-lifetime-fixture"}
	var fixture := _make_fixture(SOURCE)
	_expect(not fixture.is_empty(),"three-image GLB fixture saves")
	if not fixture.is_empty():
		_origins = fixture.bindings
		_source_bytes = fixture.bytes
		_digest = str(fixture.digest)
		_container_contracts()
		if _publish_fixture():
			await _binding_contracts()
			await _pipeline_contracts()
	Scenes.clear()
	Cache._targets = old_targets
	MapCache._enabled_cache = old_enabled
	Graphics._texture_skip = old_skip
	for key: String in environment:
		if str(environment[key]).is_empty(): OS.unset_environment(key)
		else: OS.set_environment(key,str(environment[key]))
	Vram.reconfigure()
	for frame: int in 3: await process_frame
	print("geometry texture lifetimes: ","PASS" if _failures == 0 else "FAIL"," (",_checks," checks)")
	quit(_failures)

func _container_contracts() -> void:
	var old_diagnostics := _diagnostics()
	var legacy := Bindings.prepare(_origins,false,"",old_diagnostics)
	var new_diagnostics := _diagnostics()
	var shared := Bindings.prepare(_origins,false,SOURCE,new_diagnostics)
	_expect(bool(legacy.ok) and bool(shared.ok),"legacy and bounded embedded preparation succeed")
	if not bool(legacy.ok) or not bool(shared.ok): return
	_expect(int(old_diagnostics.counts.get("embeddedContainerReads",0)) == 3 \
		and int(new_diagnostics.counts.get("embeddedContainerReads",0)) == 1,"one full container read/hash replaces three")
	_expect(int(new_diagnostics.counts.get("embeddedContainerBytes",0)) == _source_bytes.size(),"shared container byte accounting is exact")
	var exact := true
	for id: String in _origins:
		var before: Image = legacy.jobs[int(legacy.by_binding[id])].image
		var after: Image = shared.jobs[int(shared.by_binding[id])].image
		exact = exact and before.get_format() == after.get_format() and before.get_mipmap_count() == after.get_mipmap_count() and before.get_data() == after.get_data()
	_expect(exact,"every decoded pixel, format and mip byte matches the old path")
	var released := true
	for job: Dictionary in shared.jobs: released = released and not job.has("verified_container")
	_expect(released,"prepared jobs retain no source container buffers")
	var bad := _origins.duplicate(true)
	var first := str(bad.keys()[0])
	var bad_origin: Dictionary = bad[first]
	bad.erase(first)
	bad_origin.image_sha256 = "f".repeat(64)
	bad[Bindings._identity(bad_origin)] = bad_origin
	_expect(not bool(Bindings.prepare(bad,false,SOURCE).ok),"shared source still verifies each embedded image SHA")
	var changed := _source_bytes.duplicate()
	changed[changed.size()-1] ^= 1
	_bytes(SOURCE,changed)
	_expect(not bool(Bindings.prepare(_origins,false,SOURCE).ok),"source mutation rejects the shared container")
	_bytes(SOURCE,_source_bytes)
	var oversized_path := DIRECTORY+"/oversized.glb"
	var oversized := _make_fixture(oversized_path,Bindings.MAX_SHARED_CONTAINER_BYTES)
	var oversized_diagnostics := _diagnostics()
	var fallback := Bindings.prepare(oversized.bindings,false,oversized_path,oversized_diagnostics)
	_expect(bool(fallback.ok) and int(oversized_diagnostics.counts.get("embeddedContainerReads",0)) == 3 \
		and int(oversized_diagnostics.counts.get("embeddedContainerSharedJobs",0)) == 0,"oversized sources retain bounded per-job fallback")
	DirAccess.remove_absolute(oversized_path)

func _publish_fixture() -> bool:
	var source := Node3D.new()
	var child := MeshInstance3D.new()
	child.name = "Mesh"
	var mesh := BoxMesh.new()
	var material := StandardMaterial3D.new()
	material.normal_enabled = true
	var ids: Array = _origins.keys()
	material.set_meta(Bindings.SLOT_META,{"albedo_texture":ids[0],"normal_texture":ids[1],"ao_texture":ids[2]})
	mesh.material = material
	child.mesh = mesh
	source.add_child(child)
	child.owner = source
	var packed := PackedScene.new()
	var packed_ok := packed.pack(source) == OK
	source.free()
	if not packed_ok: return false
	DirAccess.make_dir_recursive_absolute(Cache.blobs_path())
	var temporary := Cache.blobs_path()+"/texture-lifetime-fixture.scn"
	if ResourceSaver.save(packed,temporary,ResourceSaver.FLAG_COMPRESS) != OK: return false
	_blob_bytes = FileAccess.get_file_as_bytes(temporary)
	var sha := Sources.digest_bytes(_blob_bytes)
	var path := Cache.blobs_path()+"/"+sha+".scn"
	if FileAccess.file_exists(path): DirAccess.remove_absolute(temporary)
	elif DirAccess.rename_absolute(temporary,path) != OK: return false
	_entry = {"schema":Cache.VERSION,"policy":Cache.policy(),"kind":"asset","source":SOURCE,
		"source_digest":_digest,"primary":path,"payloads":{path:sha},"bindings":_origins,
		"shared_meshes":{},"inputs":[{"path":SOURCE,"sha256":_digest}]}
	var ok := _publish(_entry)
	_expect(ok,"isolated native template publishes")
	return ok

func _publish(entry: Dictionary) -> bool:
	var old := Cache.cooking
	Cache.cooking = true
	var ok := Cache.publish(entry)
	Cache.cooking = old
	return ok

func _acquire() -> Dictionary:
	return Cache.acquire("asset",SOURCE,_digest)

func _image_refs(record: Dictionary) -> Array[WeakRef]:
	var refs: Array[WeakRef] = []
	for job: Dictionary in record.textures.jobs: refs.append(weakref(job.image))
	return refs

func _template_material(record: Dictionary) -> Material:
	var state := (record.resource as PackedScene).get_state()
	for node: int in state.get_node_count():
		for property: int in state.get_node_property_count(node):
			if state.get_node_property_name(node,property) == &"mesh":
				return (state.get_node_property_value(node,property) as Mesh).surface_get_material(0)
	return null

func _binding_contracts() -> void:
	var record := _acquire()
	_expect(str(record.get("status","")) == "hit","native texture fixture acquires")
	if str(record.get("status","")) != "hit": return
	var refs := _image_refs(record)
	var before_nodes := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	_expect(Cache.bind(record),"main binds a verified template without instantiating")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes \
		and bool(record.get("bound",false)) and (record.textures as Dictionary).is_empty(),"binding creates no Nodes and drops its CPU carrier")
	for frame: int in 3: await process_frame
	var released := true
	for reference: WeakRef in refs: released = released and reference.get_ref() == null
	_expect(released,"decoded Images retire after binding")
	var second := _acquire()
	_expect(Cache.bind(second) and _template_material(record) != _template_material(second),"separate loads retain private template materials")
	var stale := _acquire()
	var changed := _source_bytes.duplicate()
	changed[-1] ^= 1
	_bytes(SOURCE,changed)
	_expect(not Cache.bind(stale),"binding retains full stale-source rejection")
	_bytes(SOURCE,_source_bytes)
	stale = _acquire()
	var broken := _blob_bytes.duplicate()
	broken[broken.size()/2] ^= 1
	_bytes(str(_entry.primary),broken)
	_expect(not Cache.bind(stale),"binding retains corrupt-payload rejection")
	_bytes(str(_entry.primary),_blob_bytes)
	stale = _acquire()
	var replacement := _entry.duplicate(true)
	replacement.policy = "f".repeat(64)
	_publish(replacement)
	_expect(not Cache.bind(stale),"binding retains current policy validation")
	_publish(_entry)
	stale = _acquire()
	Graphics._texture_skip = 1
	_expect(not Cache.bind(stale),"binding rejects a changed runtime texture policy")
	Graphics._texture_skip = 0
	var worker := Thread.new()
	worker.start(func() -> bool: return Cache.bind(stale))
	_expect(not bool(worker.wait_to_finish()),"worker cannot publish bound textures")

func _pipeline_contracts() -> void:
	Scenes.clear()
	var before_nodes := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	_expect(Scenes.prepare_bound_main(PackedStringArray([SOURCE,SOURCE])),"main prepares and binds each scoped asset")
	var path := ProjectSettings.globalize_path(SOURCE)
	# user:// is retained by GlbSceneCache's established canonical namespace.
	path = SOURCE if SOURCE.begins_with("user://") else path
	var record: Dictionary = Scenes._geometry_entries.get(path,{})
	_expect(not record.is_empty() and bool(record.get("bound",false)) and (record.get("textures",{}) as Dictionary).is_empty() \
		and Scenes._geometry_entries.size() == 1,"duplicate paths share one bound resource template")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes,"sequential publication creates no Nodes")
	var model := Scenes.instantiate(SOURCE)
	_expect(model != null,"a bound template still produces the ordinary real instance")
	if model != null: model.free()
	Scenes.clear()
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE","1")
	_expect(not Scenes.prepare_bound_main(PackedStringArray([SOURCE])) and Scenes.cached_scene_count() == 0,"raw bypass keeps the old bulk caller path")
	OS.unset_environment("ELORIA_NO_GEOMETRY_CACHE")
	_expect(not Scenes.prepare_bound_main(PackedStringArray([SOURCE,DIRECTORY+"/outside.glb"])) and Scenes.cached_scene_count() == 0,"scope preflight cannot partially publish a mixed request")
	var worker := Thread.new()
	worker.start(func() -> bool: return Scenes.prepare_bound_main(PackedStringArray([SOURCE])))
	_expect(not bool(worker.wait_to_finish()) and Scenes.cached_scene_count() == 0,"worker preparation API remains unchanged")
	var before_publications := int(Pool.retention_snapshot().publications)
	worker = Thread.new()
	worker.start(_acquire)
	while worker.is_alive(): await process_frame
	var acquired: Dictionary = worker.wait_to_finish()
	_expect(str(acquired.get("status","")) == "hit" and int(Pool.retention_snapshot().publications) == before_publications \
		and int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes,"worker acquisition remains Resources-only without pool publication")
	Scenes.install_prepared({SOURCE:{"geometry_record":acquired}})
	_expect(Scenes.prepare_bound_main(PackedStringArray([SOURCE])) and bool(acquired.get("bound",false)),"main can finish an installed worker completion")
	Scenes.clear()
	var broken := _blob_bytes.duplicate()
	broken[broken.size()/2] ^= 1
	_bytes(str(_entry.primary),broken)
	_expect(Scenes.prepare_bound_main(PackedStringArray([SOURCE])) and not Scenes._geometry_entries.has(SOURCE) \
		and Scenes.cached_scene_count() == 1,"a corrupt native entry retains the existing raw scene fallback")
	_bytes(str(_entry.primary),_blob_bytes)
	Scenes.clear()

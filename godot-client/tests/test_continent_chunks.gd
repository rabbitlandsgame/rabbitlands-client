extends SceneTree

## Real GLB fixtures: the territory's review GLB is intentionally not importable.
## A successful load therefore proves only selected independent GLBs are read.
const SCRATCH := "user://continent-chunks-test"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func _write_json(path: String, data: Dictionary) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()

func _manifest(identity: String) -> Dictionary:
	return {"schemaVersion":"1.0.0", "asset":{"id":identity,"name":identity,
		"glb":"world.glb", "units":"meters", "origin":[0,0,0],
		"coordinateSystem":{"upAxis":"Y","northAxis":"-Z","handedness":"right"},
		"bounds":{"min":[-32,0,-32],"max":[1300,10,32]}, "serverCells":[1400,80]},
		"coordinateTransform":{"metresPerTile":1,"serverOrigin":[0,40],"origin":[0,0,0],
		"walkingHeight":0,"invertServerY":true,"serverCells":[1400,80]},
		"spawnPoints":[{"id":"default","position":[0,0,0]}],
		"collision":{"nodeNames":[]},"navigation":{"surfaceNodePrefixes":["Terrain_"]}}

func _write_chunk(identity: String, x: float) -> Dictionary:
	var directory := SCRATCH.path_join(identity)
	DirAccess.make_dir_recursive_absolute(directory)
	var stage := Node3D.new()
	var ground := MeshInstance3D.new()
	ground.name = "Terrain_" + identity
	var mesh := PlaneMesh.new()
	mesh.size = Vector2(64,64)
	ground.mesh = mesh
	var material := StandardMaterial3D.new()
	var image := Image.create(4,4,false,Image.FORMAT_RGBA8)
	image.fill(Color(.3,.55,.2,1))
	material.albedo_texture = ImageTexture.create_from_image(image)
	mesh.material = material
	ground.position.x = x
	stage.add_child(ground)
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	_expect(doc.append_from_scene(stage,state) == OK, "fixture GLB scene serializes")
	_expect(doc.write_to_filesystem(state,directory.path_join("world.glb")) == OK, "fixture independent GLB writes")
	stage.free()
	var data := _manifest("fixture_" + identity)
	data.externalResources = _externalize(directory.path_join("world.glb"))
	_write_json(directory.path_join("world.json"), data)
	return {"id":identity,"manifest":identity + "/world.json",
		"bounds":{"min":[x-32,0,-32],"max":[x+32,1,32]},"estimatedResidentBytes":50}

func _externalize(path: String) -> Dictionary:
	var file := FileAccess.open(path,FileAccess.READ)
	file.seek(12)
	var length := file.get_32()
	file.get_32()
	var json: Dictionary = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	var bin_length := file.get_32()
	file.get_32()
	var binary := file.get_buffer(bin_length)
	file.close()
	var image: Dictionary = json.images[0]
	var view: Dictionary = json.bufferViews[int(image.bufferView)]
	var shared := SCRATCH.path_join("shared")
	DirAccess.make_dir_recursive_absolute(shared)
	var texture_path := shared.path_join("ground.png")
	file = FileAccess.open(texture_path,FileAccess.WRITE)
	file.store_buffer(binary.slice(int(view.get("byteOffset",0)),int(view.get("byteOffset",0))+int(view.byteLength)))
	file.close()
	image.erase("bufferView")
	image.uri = "../shared/ground.png"
	var encoded := JSON.stringify(json).to_utf8_buffer()
	while encoded.size() % 4 != 0:
		encoded.append(32)
	file = FileAccess.open(path,FileAccess.WRITE)
	for value: int in [0x46546c67,2,28+encoded.size()+binary.size(),encoded.size(),0x4e4f534a]:
		file.store_32(value)
	file.store_buffer(encoded)
	file.store_32(binary.size())
	file.store_32(0x004e4942)
	file.store_buffer(binary)
	file.close()
	return {"../shared/ground.png":FileAccess.get_sha256(texture_path)}

func _test_shared_memory_accounting() -> void:
	var stream := ContinentChunkStream.new()
	stream.maximum_resident_bytes = 100
	stream.maximum_chunks = 3
	# b and c lie beyond the framed radius, where the byte budget decides.
	var near := {"min":[-10,0,-10],"max":[10,1,10]}
	var lead := {"min":[100,0,-10],"max":[120,1,10]}
	for identity: String in ["a", "b", "c"]:
		var entry := {"id":identity, "bounds":near if identity == "a" else lead, "estimatedResidentBytes":80,
			"geometryResidentBytes":20, "sharedResourceResidentBytes":{"a".repeat(64):60}}
		if identity == "c":
			entry.sharedResourceResidentBytes = {"b".repeat(64):60}
		stream.entries.append(entry)
	var selected := stream.selection(Vector3.ZERO)
	_expect(selected.size() == 2 and str(selected[0].id) == "a" and str(selected[1].id) == "b",
		"shared PNG budget admits two near cells while distinct texture exceeds the limit")
	for entry: Dictionary in selected:
		var cell := Node3D.new()
		stream.add_child(cell)
		stream.cells[str(entry.id)] = {"root":cell, "entry":entry}
	stream._update_resident_bytes()
	_expect(stream.resident_bytes == 100, "resident byte estimate counts identical texture hash once")
	stream._retire_cell("a")
	_expect(stream.resident_bytes == 100, "hidden retirement geometry and shared image stay counted until freed")
	stream._drain_retired()
	_expect(stream.resident_bytes == 80, "retiring one sharer releases geometry but preserves the other texture cost")
	stream._retire_cell("b")
	stream._drain_retired()
	_expect(stream.resident_bytes == 0, "last shared image leaves the resident estimate after actual node release")
	stream.maximum_resident_bytes = 1
	_expect(stream.selection(Vector3.ZERO).size() == 1, "one oversized nearest cell preserves arrival ground")
	stream.free()

## The Amberwood life pass made single cells cost more than the whole budget.
## The nearest-first prefix then kept one cell and dropped a second cell under
## the focus and the neighbour beside it, which rendered as flat planes.
func _test_framed_cells_outlast_budget() -> void:
	var stream := ContinentChunkStream.new()
	stream.maximum_resident_bytes = 256
	var cells := {"under_a":[[-40,-40],[5,40]], "under_b":[[-5,-40],[40,40]],
		"beside":[[-40,50],[40,100]], "lead":[[-40,150],[40,200]]}
	for identity: String in cells:
		var span: Array = cells[identity]
		stream.entries.append({"id":identity, "estimatedResidentBytes":400 if identity != "lead" else 8,
			"bounds":{"min":[span[0][0],0,span[0][1]],"max":[span[1][0],1,span[1][1]]}})
	var chosen := stream.selection(Vector3.ZERO)
	var selected := chosen.map(func(entry: Dictionary) -> String: return str(entry.id))
	_expect(selected == ["under_a", "under_b", "beside"],
		"every framed cell stays selected when each alone outgrows the byte budget")
	_expect(not selected.has("lead"), "a cheap cell beyond the framed ground still waits for budget")
	var beyond := chosen.map(func(entry: Dictionary) -> bool: return bool(entry.beyond_budget))
	_expect(beyond == [false, true, true],
		"cells past the budget are marked so an arrival leaves the framed neighbour to the worker")
	# Both under_* cells cover the origin. The Amberwood deep grove lay under a
	# resident neighbour's overhanging props while its own ground cell was
	# missing, and the actor grounded on nothing 19 m above the canopy deck.
	stream.cells = {"under_b": {}}
	_expect(not stream.arrival_resident(Vector3.ZERO),
		"a resident overlapping neighbour does not stand in for the missing ground cell")
	_expect(stream.arrival_resident(Vector3(30, 0, 0)), "a position only one resident cell covers is ready")
	stream.cells = {"under_a": {}, "under_b": {}}
	_expect(stream.arrival_resident(Vector3.ZERO), "the arrival is ready once every covering cell is resident")
	_expect(not stream.arrival_resident(Vector3(0, 0, 45)), "a position no cell covers is never reported as ready")
	stream.free()

func _run() -> void:
	_test_shared_memory_accounting()
	_test_framed_cells_outlast_budget()
	DirAccess.make_dir_recursive_absolute(SCRATCH)
	var config := _manifest("fixture_territory")
	config.streamingChunks = {"schemaVersion":"1.0","coordinateSpace":"territory-local",
		"preloadDistance":60,"retainDistance":100,"maximumLoadedChunks":2,"maximumResidentBytes":100,
		"chunks":[_write_chunk("west",0),_write_chunk("middle",600),_write_chunk("east",1200)]}
	# This missing faraway package must not even be opened while it is distant.
	config.streamingChunks.chunks.append({"id":"unbuilt","manifest":"unbuilt/world.json",
		"bounds":{"min":[3000,0,0],"max":[3050,1,50]},"estimatedResidentBytes":50})
	_write_json(SCRATCH.path_join("world.json"),config)
	var review := FileAccess.open(SCRATCH.path_join("world.glb"),FileAccess.WRITE)
	review.store_string("Review export deliberately unavailable to runtime GLB parser")
	review.close()
	var stage := Node3D.new()
	root.add_child(stage)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	loader.load_world(SCRATCH.path_join("world.json"),Vector3.INF,true)
	_expect(loader.world_root is ContinentChunkStream, "chunk territory does not import the invalid full review GLB")
	_expect(not loader.loaded_by_adoption, "cold destination is distinguished from a preloaded root adoption")
	var chunks := loader.world_root as ContinentChunkStream
	if chunks == null:
		quit(1)
		return
	_expect(chunks.cells.is_empty() and not chunks.has_focus, "cold map metadata waits for the actual server arrival")
	_expect(not chunks.initial_focus.is_finite(), "cold metadata records no invented/default arrival position")
	_expect(loader.ensure_chunk_arrival(Vector3(600,0,0)), "first server arrival primes its exact position")
	_expect(chunks.initial_focus == Vector3(600,0,0), "cold destination records the actual distant landing as its initial focus")
	_expect(chunks.cells.keys() == ["middle"], "distant cells and the default spawn are never imported")
	_expect(not loader.ensure_chunk_arrival(Vector3(600,0,0)), "subsequent actor updates do not re-prime an already loaded arrival")
	_expect(loader.cache_status == &"chunked" and loader.cache_file.is_empty(), "partial territory cannot read or write a full-map scene cache")
	_expect(is_equal_approx(ContinentChunkStream.bounds_distance(Vector3(672,400,62),config.streamingChunks.chunks[1].bounds),50),
		"selection uses full XZ bounds, including prop overhangs and finite corners")
	var cell_root: Node3D = chunks.cells.middle.root
	var cell_id := cell_root.get_instance_id()
	var other := WorldLoader.prepare_detached(SCRATCH.path_join("west/world.json"),false)
	var first_ground := cell_root.find_child("Terrain_middle",true,false) as MeshInstance3D
	var other_ground := other.world_root.find_child("Terrain_west",true,false) as MeshInstance3D
	var first_texture := (first_ground.mesh.surface_get_material(0) as BaseMaterial3D).albedo_texture
	var other_texture := (other_ground.mesh.surface_get_material(0) as BaseMaterial3D).albedo_texture
	_expect(first_texture == other_texture and first_texture.get_image().has_mipmaps(),
		"independent external-image GLBs share the same mipmapped GPU texture")
	other.free()
	var external_manifest := WorldManifest.load_file(SCRATCH.path_join("middle/world.json"))
	_expect(external_manifest.verify_external_resources().is_empty(), "relative shared PNG resolves and verifies inside the package scope")
	var windows_manifest := WorldManifest.load_file(ProjectSettings.globalize_path(
		SCRATCH.path_join("middle/world.json")).replace("/", "\\"))
	_expect(windows_manifest.verify_external_resources().is_empty(),
		"native Windows manifest paths normalize before shared texture scope checks")
	external_manifest.data.externalResources = {"../shared/ground.png":"0".repeat(64)}
	_expect(not external_manifest.verify_external_resources().is_empty(), "changed external texture bytes cannot silently reuse a chunk cache")
	external_manifest.data.externalResources = {"C:/outside.png":"0".repeat(64)}
	_expect(not external_manifest.verify_external_resources().is_empty(), "absolute external paths are rejected before resource reads")
	ExteriorRegionStream._set_collision(chunks,false,true,"",true)
	await physics_frame
	await physics_frame
	var space := stage.get_world_3d().direct_space_state
	var ray := PhysicsRayQueryParameters3D.create(Vector3(600,10,0),Vector3(600,-10,0),16)
	_expect(not space.intersect_ray(ray).is_empty(), "loaded neighbor ground is an actual layer-16 picking surface")
	ray.collision_mask = 8
	_expect(space.intersect_ray(ray).is_empty(), "neighbor ground cannot steal active actor grounding")
	var resident := loader.release_world()
	var source_loader := WorldLoader.new()
	stage.add_child(source_loader)
	source_loader.world_root = Node3D.new()
	source_loader.add_child(source_loader.world_root)
	source_loader.manifest = WorldManifest.new()
	source_loader.manifest.data = _manifest("fixture_source")
	var stream := ExteriorRegionStream.new()
	stage.add_child(stream)
	stream.add_child(resident.root)
	stream.residents.fixture_territory = resident
	stream.links = [{"seamless":true,"ends":[
		{"map":"fixture_source","position":[0,0,0],"frame":{"id":"road","anchor":[0,0,0],"outward":[1,0],"geometryMode":"continent-owned-v1"}},
		{"map":"fixture_territory","position":[0,0,0],"frame":{"id":"road","anchor":[0,0,0],"outward":[-1,0],"geometryMode":"continent-owned-v1"}}]}]
	stream.activate("fixture_source",source_loader.world_root,source_loader.manifest)
	await physics_frame
	await physics_frame
	_expect(stream.pick_neighbor(space,Vector3(600.2,10,.2),Vector3.DOWN,true) == Vector3.ZERO,
		"clicking rendered neighbor cell follows its real territory crossing")
	_expect(stream.pending_walk.get("tile") == Vector2i(600,39) and bool(stream.pending_walk.get("run",false)),
		"chunk picking retains exact destination tile and run intent")
	var handoff := stream.take_ready("fixture_territory",source_loader,Vector3.ZERO)
	_expect(bool(handoff.get("continuous",false)), "ready chunk territory uses the continuous exterior handoff")
	loader.adopt_world(handoff.resident)
	_expect(loader.loaded_by_adoption, "adoption remains observable without classifying a ferry as a walking seam")
	ExteriorRegionStream._set_collision(loader.world_root,true)
	await physics_frame
	await physics_frame
	_expect(chunks.cells.middle.root.get_instance_id() == cell_id and not space.intersect_ray(ray).is_empty(),
		"adoption retains exact cell instances and promotes active grounding")
	stream.residents.clear()
	var digest := MapSceneCache.package_digest(SCRATCH.path_join("east/world.json"),SCRATCH.path_join("east/world.glb"))
	var east: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SCRATCH.path_join("east/world.json")))
	east.assetVersion = "changed"
	_write_json(SCRATCH.path_join("east/world.json"),east)
	_expect(digest != MapSceneCache.package_digest(SCRATCH.path_join("east/world.json"),SCRATCH.path_join("east/world.glb")),
		"individual chunk cache keys invalidate when its manifest changes")
	chunks.update_focus(Vector3(1200,0,0))
	for frame: int in 900:
		await process_frame
		if chunks.cells.has("east") and chunks._thread == null and chunks._retiring.is_empty():
			break
	_expect(chunks.cells.keys() == ["east"], "movement loads a new independent GLB and evicts the old cell")
	_expect(not is_instance_id_valid(cell_id) and chunks.resident_bytes == 50,
		"eviction releases old nodes and memory accounting after bounded retirement")
	_expect(chunks.events.filter(func(e: Dictionary) -> bool: return str(e.chunk) == "unbuilt").is_empty(),
		"missing distant data is never requested or parsed")
	ExteriorRegionStream._set_collision(chunks,false,true,"",true)
	chunks._next_update = 0
	chunks.update_focus(Vector3.ZERO)
	for frame: int in 900:
		await process_frame
		if chunks.cells.has("west") and chunks._thread == null and chunks._retiring.is_empty():
			break
	await physics_frame
	await physics_frame
	ray = PhysicsRayQueryParameters3D.create(Vector3(0,10,0),Vector3(0,-10,0),16)
	_expect(not space.intersect_ray(ray).is_empty(), "later asynchronously loaded neighbor cells inherit preview picking ownership")
	chunks.preload_distance = 2000
	chunks.maximum_resident_bytes = 51
	_expect(chunks.selection(Vector3(1200,0,0)).size() == 1, "decoded byte budget limits requested cells")
	chunks.maximum_resident_bytes = 100000
	chunks.maximum_chunks = 1
	_expect(chunks.selection(Vector3(1200,0,0)).size() == 1, "cell count budget is independent of estimated bytes")
	_expect(loader.ensure_chunk_arrival(Vector3(600,0,0)) and chunks.cells.keys() == ["middle"],
		"same-territory teleport loads its authoritative destination before grounding")
	_expect(chunks.initial_focus == Vector3(600,0,0), "subsequent travel preserves initial cold-load provenance")
	chunks.pause_streaming()
	_expect(chunks.can_retire(), "retirement can safely release an idle chunk root")
	stage.queue_free()
	await process_frame
	print("continent chunk tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

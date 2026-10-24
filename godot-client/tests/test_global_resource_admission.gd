extends SceneTree
## Actual stream launch/join/install/discard/retirement integration with a
## deterministic native-ABI fixture. Rust unit tests independently test ABI policy.
const Admission := preload("res://src/runtime/resource_admission.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const MapExtension := preload("res://src/world/map_mesh_extension.gd")
const Controller := preload("res://src/runtime/client_runtime.gd")
const SCRATCH := "user://global-admission-fixture"
var failures := 0

class FakeNative extends RefCounted:
	var epoch := 1
	var next_id := 1
	var leases: Dictionary = {}
	var status := 0
	var last_input := PackedInt64Array()
	var graph: Dictionary = {}
	var graph_registrations := 0
	func admission_begin(value: int, input: PackedInt64Array) -> PackedInt64Array:
		status = 0
		last_input = input.duplicate()
		if value != epoch or input.size() != 10:
			status = 2
			return PackedInt64Array()
		var reserved := 0
		for lease: Dictionary in leases.values():
			reserved += 1 if str(lease.state) == "reserved" else 0
		var reason := 0
		if input[9] == 0:
			if input[5] > 0: reason = 3
			elif input[3] + reserved >= input[4]: reason = 2
			elif input[8] == 0 and input[0] + input[1] > input[2]: reason = 1
			elif input[8] == 0 and input[6] > input[7]: reason = 4
		if reason:
			return PackedInt64Array([0, reason])
		var id := next_id
		next_id += 1
		leases[id] = {"epoch": epoch, "state": "reserved", "cancelled": false}
		return PackedInt64Array([id, 0])
	func admission_event(id: int, value: int, event: int) -> int:
		status = 0
		if not leases.has(id) or int(leases[id].epoch) != value:
			status = 2
			return status
		var lease: Dictionary = leases[id]
		match event:
			Admission.LAUNCHED: lease.state = "loading"
			Admission.READY: lease.state = "ready"
			Admission.INSTALLED:
				if value != epoch or bool(lease.cancelled):
					status = 2
					return status
				lease.state = "active"
			Admission.RETIRING: lease.state = "retiring"
			Admission.CANCEL: lease.cancelled = true
			Admission.RELEASED, Admission.FAILED: leases.erase(id)
		return status
	func admission_snapshot() -> Dictionary:
		return {"leases": leases.size()}
	func admission_dependencies(id: int, value: int, records: PackedInt64Array, edges: PackedInt64Array) -> int:
		status = 0
		if not leases.has(id) or int(leases[id].epoch) != value or records.size() % 9 != 0:
			status = 1
			return status
		var keys: Array[String] = []
		for offset: int in range(0, records.size(), 9):
			var key := preload("res://src/runtime/resource_residency.gd")._digest(records, offset)
			var dependencies: Array[String] = []
			for index: int in int(records[offset + 8]):
				dependencies.append(preload("res://src/runtime/resource_residency.gd")._digest(edges, (int(records[offset + 7]) + index) * 4))
			graph[key] = {"dependencies": dependencies}
			keys.append(key)
		leases[id]["dependency_keys"] = keys
		graph_registrations += 1
		return status
	func admission_release_dependencies(words: PackedInt64Array) -> PackedInt64Array:
		status = 0
		var requested: Array[String] = []
		for offset: int in range(0, words.size(), 4):
			requested.append(preload("res://src/runtime/resource_residency.gd")._digest(words, offset))
		var result := PackedInt64Array()
		var progress := true
		while progress:
			progress = false
			for key: String in requested.duplicate():
				var owned := false
				for lease: Dictionary in leases.values():
					owned = owned or key in lease.get("dependency_keys", [])
				for node: Dictionary in graph.values():
					owned = owned or key in node.dependencies
				if not owned and graph.has(key):
					graph.erase(key)
					requested.erase(key)
					result.append_array(preload("res://src/runtime/resource_residency.gd")._key(key))
					progress = true
		return result
	func admission_graph_snapshot() -> Dictionary:
		return {"schema": 1, "resources": graph.size(), "registrations": graph_registrations}
	func get_last_status() -> int:
		return status

class FakeController extends ClientRuntimeController:
	var service: FakeNative
	func native_runtime() -> RefCounted:
		return service

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("global admission: " + message)

func _cache_counts() -> Dictionary:
	return {"strong_scene_entries": 7, "bytes_estimate_available": false}

func _write_chunk(identity: String) -> Dictionary:
	var directory := SCRATCH.path_join(identity)
	DirAccess.make_dir_recursive_absolute(directory)
	var stage := Node3D.new()
	var ground := MeshInstance3D.new()
	ground.name = "Terrain_" + identity
	ground.mesh = PlaneMesh.new()
	stage.add_child(ground)
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	_expect(document.append_from_scene(stage, state) == OK, "real GLB fixture encodes")
	_expect(document.write_to_filesystem(state, directory.path_join("world.glb")) == OK, "real GLB fixture writes")
	stage.free()
	var data := {"schemaVersion": "1.0.0", "asset": {"id": identity, "name": identity,
		"glb": "world.glb", "units": "meters", "origin": [0,0,0],
		"coordinateSystem": {"upAxis": "Y", "northAxis": "-Z", "handedness": "right"},
		"bounds": {"min": [-10,0,-10], "max": [10,1,10]}, "serverCells": [20,20]},
		"coordinateTransform": {"metresPerTile": 1, "serverOrigin": [0,10], "origin": [0,0,0],
			"walkingHeight": 0, "invertServerY": true, "serverCells": [20,20]},
		"spawnPoints": [{"id": "default", "position": [0,0,0]}],
		"collision": {"nodeNames": []}, "navigation": {"surfaceNodePrefixes": ["Terrain_"]}}
	var file := FileAccess.open(directory.path_join("world.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()
	return {"id": identity, "path": directory.path_join("world.json"), "estimatedResidentBytes": 50,
		"bounds": {"min": [-10,0,-10], "max": [10,1,10]}}

func _stream(entry: Dictionary) -> ContinentChunkStream:
	var stream := ContinentChunkStream.new()
	root.add_child(stream)
	stream.set_process(false) # The fixture drives actual process boundaries.
	stream._cache_enabled = false
	stream.has_focus = true
	stream.focus = Vector3.ZERO
	stream.entries.append(entry)
	return stream

func _join(stream: ContinentChunkStream) -> bool:
	for _frame: int in 600:
		await process_frame
		stream.poll_pending()
		if stream._thread == null:
			return true
	_expect(false, "real fixture worker joins within bounded frames")
	return false

func _drain(stream: ContinentChunkStream) -> void:
	for _frame: int in 60:
		await process_frame
		stream._drain_retired()
		if stream._retiring.is_empty():
			await process_frame
			return
	_expect(false, "real shared-clock retirement drains")

func _shared_resource_lifetime(owner_node: Node3D, native: FakeNative) -> void:
	var shared: Mesh = BoxMesh.new()
	var imported_a := Node3D.new()
	var imported_b := Node3D.new()
	var mesh_a := MeshInstance3D.new()
	var mesh_b := MeshInstance3D.new()
	mesh_a.mesh = shared
	mesh_b.mesh = shared
	imported_a.add_child(mesh_a)
	imported_b.add_child(mesh_b)
	root.add_child(imported_a)
	root.add_child(imported_b)
	for row: Dictionary in [{"entry": _write_chunk("shared-a"), "root": imported_a},
			{"entry": _write_chunk("shared-b"), "root": imported_b}]:
		var request := Admission.request(owner_node, row.entry, "chunk", true, true)
		var token: Dictionary = request.get("token", {})
		_expect(not token.is_empty(), "shared-resource fixture owns a real admission lease")
		Admission.event(token, Admission.LAUNCHED)
		Admission.ready(token, WorldManifest.load_file(str(row.entry.path)))
		Admission.hold(token, row.root)
	var resources := native.graph.size()
	_expect(resources >= 2, "distinct source roots register independent dependency records")
	imported_a.free()
	await process_frame
	await process_frame
	_expect(native.leases.size() == 1 and native.graph.size() == resources,
		"freeing one root cannot release a shared Resource still used by another resident")
	imported_b.free()
	await process_frame
	await process_frame
	_expect(native.leases.is_empty() and native.graph.size() == resources,
		"cache-owned actual Mesh keeps conservative dependency records after both roots are physically gone")
	shared = null
	await process_frame
	await process_frame
	_expect(native.graph.is_empty() and Admission.current()._dependencies.is_empty(),
		"last actual Resource release permits native dependency release without a second destruction clock")

func _finished_worker_exit(native: FakeNative) -> bool:
	var stream := _stream(_write_chunk("finished-owner-exit"))
	stream.update_focus(Vector3.ZERO)
	_expect(stream._thread != null, "finished-exit fixture owns an actual worker")
	if stream._thread == null:
		return false
	for _frame: int in 600:
		if not stream._thread.is_alive():
			break
		await process_frame
	if stream._thread.is_alive():
		_expect(false, "finished-exit worker finishes within bounded frames; owned runner must terminate")
		return false
	var before := ContinentChunkStream.orphans_pending()
	stream.free() # Finished, but intentionally not joined by poll_pending().
	_expect(ContinentChunkStream.orphans_pending() == before + 1 and not native.leases.is_empty(),
		"finished admitted worker transfers to existing reaper instead of losing Resource lifetime carriers")
	ContinentChunkStream.reap_orphans()
	_expect(ContinentChunkStream.orphans_pending() == before and not native.leases.is_empty() \
		and not Admission.current()._carrier_groups.is_empty(),
		"actual join captures weak Resource carriers before ordinary root queued-free")
	await process_frame
	await process_frame
	_expect(native.leases.is_empty(), "finished-owner-exit lease releases after actual root destruction")
	return true

func _prepared_resource_discard(stream: ContinentChunkStream, native: FakeNative) -> void:
	var entry := _write_chunk("prepared-resource-discard")
	var seed := MeshInstance3D.new()
	seed.mesh = BoxMesh.new() # No globally cached material can pin the fixture.
	var packed := PackedScene.new()
	_expect(packed.pack(seed) == OK, "prepared-only fixture packs a Resource before the no-Node boundary")
	seed.free()
	var path := SCRATCH.path_join("prepared-resource-discard.scn")
	_expect(ResourceSaver.save(packed, path) == OK, "prepared alias fixture saves native bytes")
	packed = null
	var held := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	var cached := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_REUSE) as PackedScene
	_expect(held != null and held == cached, "real CACHE_MODE_REUSE returns the same native primary alias")
	cached = null
	var reference: WeakRef = weakref(held)
	var request := Admission.request(stream, entry, "chunk", true, true)
	var token: Dictionary = request.get("token", {})
	_expect(bool(request.get("allowed", false)) and not token.is_empty(), "prepared discard owns a native source-DAG lease")
	if token.is_empty():
		return
	Admission.event(token, Admission.LAUNCHED)
	Admission.event(token, Admission.CANCEL)
	var builder := WorldLoader.new()
	builder.detached_build = true
	builder.manifest = WorldManifest.load_file(str(entry.path))
	builder._prepared_native = {"status": "hit", "resource": held, "entry": {}}
	var pending := entry.duplicate()
	pending["_admission_token"] = token
	var builder_weak: WeakRef = weakref(builder)
	var before_nodes := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var before_orphans := int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT))
	var before_retired := stream._retiring.size()
	stream._discard_builder(pending, builder)
	# OBJECT_NODE_COUNT is SceneTree membership, not detached Node lifetime.
	# The actual builder must die, tree membership stays unchanged, and debug
	# orphan accounting proves no detached replacement leaked from discard.
	_expect(builder_weak.get_ref() == null
		and int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == before_nodes
		and (not OS.is_debug_build() or int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)) == before_orphans - 1)
		and stream.cells.is_empty() and stream._retiring.size() == before_retired,
		"unmaterialized prepared discard frees only its builder and never creates a resident Node")
	await process_frame
	await process_frame
	var service := Admission.current()
	_expect(native.leases.is_empty() and not native.graph.is_empty()
		and not service._carrier_groups.is_empty() and reference.get_ref() != null,
		"released prepared job retains actual source DAG while external PackedScene cache alias survives")
	held = null
	for _frame: int in 120:
		await process_frame
		if reference.get_ref() == null and service._carrier_groups.is_empty() and native.graph.is_empty():
			break
	_expect(reference.get_ref() == null and service._carrier_groups.is_empty() and native.graph.is_empty(),
		"last prepared primary alias release permits actual weak-carrier DAG acknowledgement")
	# This async helper may resume its caller inside the same signal stack.
	# Drop its explicit service owner before testing final Tree-only ownership.
	service = null

func _run() -> void:
	var registered := Quantization.ensure_registered() and Vram.ensure_registered() and MapExtension.ensure_registered()
	_expect(registered, "complete runtime extension set is main-owned before worker fixtures")
	if not registered:
		quit(1)
		return
	var old_mode := OS.get_environment("RABBITLANDS_RESOURCE_ADMISSION")
	OS.set_environment("RABBITLANDS_RESOURCE_ADMISSION", "rust")
	var old_controller := Controller._current_ref
	var native := FakeNative.new()
	var controller := FakeController.new()
	controller.service = native
	Controller._current_ref = weakref(controller)
	var a := _stream(_write_chunk("a"))
	# register_stream returned without any caller retaining the RefCounted.
	var service_id := Admission.current().get_instance_id()
	var service_weak: WeakRef = weakref(Admission.current())
	await process_frame
	await process_frame
	_expect(Admission.current() != null and Admission.current().get_instance_id() == service_id,
		"SceneTree owns one admission service across frames without a strong static or caller")
	var b := _stream(_write_chunk("b"))
	var empty_loader := WorldLoader.new()
	root.add_child(empty_loader)
	Admission.register_loader(empty_loader, {"fixture_cache": _cache_counts})
	a.update_focus(Vector3.ZERO)
	_expect(a._thread != null, "real first worker launch is admitted")
	b.update_focus(Vector3.ZERO)
	_expect(b._thread == null and native.leases.size() == 1, "global owner blocks a second actual stream worker")
	_expect(native.last_input[6] >= 7, "unknown actor/cache allocation is explicit in native admission input")
	a.pause_streaming()
	_expect(native.leases.size() == 1 and bool(native.leases.values()[0].cancelled),
		"cancellation retains the live worker lease")
	var joined := await _join(a)
	if not joined:
		# The strict owned-process runner must terminate this timed-out process.
		# Do not quit with an executing private GLTF worker still owned.
		return
	_expect(a.cells.is_empty() and not a._retiring.is_empty(), "cancelled real completion enters existing retirement")
	_expect(native.leases.size() == 1 and native.leases.values()[0].state == "retiring",
		"joined completion remains accounted until actual root release")
	await _drain(a)
	_expect(native.leases.is_empty(), "actual free and following owner observation acknowledge release")
	# B retained FIFO order while denied. A is called first again but cannot
	# reclaim the just-freed global slot ahead of the renewing waiting owner.
	a._paused = false
	a._next_update = 0
	a.update_focus(Vector3.ZERO)
	_expect(a._thread == null, "continuously first caller yields to previously waiting stream")
	b._next_update = 0
	b.update_focus(Vector3.ZERO)
	_expect(b._thread != null, "waiting second stream makes real progress")
	joined = await _join(b)
	if not joined:
		return
	_expect(b.cells.has("b") and native.leases.values()[0].state == "active", "real install acknowledges active residency")
	var global_snapshot: Dictionary = Admission.snapshot()
	_expect(int(global_snapshot.dependency_graph.registrations) >= 2 \
		and global_snapshot.dependency_graph.failures.is_empty() and not native.graph.is_empty(),
		"real launch and joined builder publish a validated native source DAG")
	_expect(int(global_snapshot.estimated_bytes) == 50 and int(global_snapshot.active_chunks) == 1,
		"global phase3 snapshot counts actual resident content once")
	var owner := Admission.current()
	var stopped := Node3D.new()
	root.add_child(stopped)
	owner._waiters["stopped"] = {"reference": weakref(stopped), "pinned": true,
		"order": -1, "renewed": Time.get_ticks_msec() - Admission.WAITER_LIFETIME_MSEC - 1}
	_expect(owner._first_waiter() != "stopped", "live stopped requester cannot reserve global credit permanently")
	stopped.free()
	Admission.retiring(b)
	_expect(b.cells.has("b") and native.leases.values()[0].state == "retiring",
		"outer retirement updates child-cell lease state without moving or freeing its existing queue")
	b.pause_streaming()
	b._retire_cell("b")
	owner._snapshot_frame = -1
	_expect(int(Admission.snapshot().estimated_bytes) == 50, "hidden retiring content retains its manifest estimate")
	await _drain(b)
	# A native cancel alone must prevent publication even if a caller did not
	# also pause the stream's ordinary process state.
	a._next_update = 0
	a.update_focus(Vector3.ZERO)
	_expect(a._thread != null, "cancel-only fixture starts a real worker")
	Admission.event(a._pending.get("_admission_token", {}), Admission.CANCEL)
	joined = await _join(a)
	if not joined:
		return
	_expect(not a._paused and a.cells.is_empty() and not a._retiring.is_empty(),
		"sticky cancellation guards actual publication while preserving the ordinary discard queue")
	await _drain(a)
	a._next_update = 0
	a.update_focus(Vector3.ZERO)
	_expect(a._thread != null, "pause-resume fixture starts a real worker")
	a.pause_streaming()
	a._paused = false # Resume before join cannot erase a token's cancellation.
	joined = await _join(a)
	if not joined:
		return
	_expect(a.cells.is_empty() and not a._retiring.is_empty(), "pause then resume before join still discards cancelled native completion")
	await _drain(a)
	# An old-epoch worker can finish only into discard/retirement, while its
	# original token remains accepted for cleanup in the same native runtime.
	a._next_update = 0
	a.update_focus(Vector3.ZERO)
	_expect(a._thread != null, "next real worker starts")
	controller._epoch = 2
	native.epoch = 2
	# Do not pause: the lease epoch itself must guard the actual Godot install.
	joined = await _join(a)
	if not joined:
		return
	_expect(a.cells.is_empty() and not native.leases.is_empty(), "old epoch completion cannot become a new active cell")
	await _drain(a)
	_expect(native.leases.is_empty() and owner._leases.is_empty(), "old epoch is released after actual discard retirement")
	await _shared_resource_lifetime(a, native)
	var finished_exit: bool = await _finished_worker_exit(native)
	if not finished_exit:
		return
	await _prepared_resource_discard(a, native)
	_expect(owner._graph_failures.is_empty(), "all real join and actual Resource lifetime transitions preserve DAG identity")
	a.free()
	b.free()
	empty_loader.free()
	# All actual roots/workers/leases were released; metadata is the sole
	# service owner after this local is dropped. The standard signal must not
	# create a hidden RefCounted cycle or extend native/controller lifetime.
	remove_meta(Admission.TREE_OWNER)
	owner = null
	# Finish the signal/coroutine stack which just returned the final helper.
	await process_frame
	_expect(service_weak.get_ref() == null and Admission.current() == null,
		"releasing SceneTree ownership releases the service and its standard signal")
	Controller._current_ref = old_controller
	if old_mode.is_empty(): OS.unset_environment("RABBITLANDS_RESOURCE_ADMISSION")
	else: OS.set_environment("RABBITLANDS_RESOURCE_ADMISSION", old_mode)
	await process_frame
	print("global resource admission tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

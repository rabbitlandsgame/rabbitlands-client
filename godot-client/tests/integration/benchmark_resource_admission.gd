extends RefCounted
## Functional lifetime qualification, never a timed workload. The existing
## stream/executor/reaper owns every Node and worker; this uses the real DLL.
const Admission := preload("res://src/runtime/resource_admission.gd")
const Controller := preload("res://src/runtime/client_runtime.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const MapExtension := preload("res://src/world/map_mesh_extension.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const DIRECTORY := "user://native-streaming-lifetime-fixture"
var _tree: SceneTree
var _controller: ClientRuntimeController
var _native: RefCounted
var _failures := 0
var _requires_termination := false
var _stages: Array[Dictionary] = []
var _environment: Dictionary = {}
var _owns_domain := false

func _expect(value: bool, message: String) -> void:
	if not value:
		_failures += 1
		push_error("native streaming lifetime: " + message)

func _lease_count() -> int:
	var row: Dictionary = _native.call("admission_snapshot")
	return int(row.get("reserved", 0)) + int(row.get("loading", 0)) + int(row.get("ready", 0)) \
		+ int(row.get("active", 0)) + int(row.get("retiring", 0))

func _graph() -> Dictionary:
	return _native.call("admission_graph_snapshot") as Dictionary

func _stage(label: String) -> void:
	_stages.append({"stage": label, "admission": Admission.snapshot(),
		"native": _native.call("admission_snapshot"), "graph": _graph(),
		"orphans": ContinentChunkStream.orphans_pending()})

func _write_chunk(identity: String) -> Dictionary:
	var directory := DIRECTORY.path_join(identity)
	DirAccess.make_dir_recursive_absolute(directory)
	var source := Node3D.new()
	var ground := MeshInstance3D.new()
	ground.name = "Terrain_Fixture"
	ground.mesh = PlaneMesh.new() # No global material/shader cache carrier.
	source.add_child(ground)
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var encoded := document.append_from_scene(source, state)
	_expect(encoded == OK, "synthetic material-free source encodes")
	var written := document.write_to_filesystem(state, directory.path_join("world.glb"))
	_expect(written == OK, "synthetic source writes actual GLB bytes")
	source.free()
	var data := {"schemaVersion": "1.0.0", "asset": {"id": identity, "glb": "world.glb",
		"units": "meters", "coordinateSystem": {"upAxis": "Y"},
		"bounds": {"min": [-10,0,-10], "max": [10,1,10]}},
		"coordinateTransform": {"metresPerTile": 1, "origin": [0,0,0],
			"serverOrigin": [0,10], "walkingHeight": 0, "invertServerY": true},
		"spawnPoints": [{"position": [0,0,0]}], "collision": {"nodeNames": []},
		"navigation": {"surfaceNodePrefixes": ["Terrain_"]}}
	var file := FileAccess.open(directory.path_join("world.json"), FileAccess.WRITE)
	_expect(file != null, "synthetic manifest opens")
	if file != null:
		file.store_string(JSON.stringify(data))
		file.close()
	return {"id": identity, "path": directory.path_join("world.json"),
		"estimatedResidentBytes": 1024, "distance": 0,
		"bounds": {"min": [-10,0,-10], "max": [10,1,10]}}

func _stream(entry: Dictionary) -> ContinentChunkStream:
	var stream := ContinentChunkStream.new()
	_tree.root.add_child(stream)
	stream.set_process(false)
	stream._cache_enabled = false
	stream.has_focus = true
	stream.focus = Vector3.ZERO
	stream.entries.append(entry)
	return stream

func _join(stream: ContinentChunkStream) -> bool:
	for _frame: int in 600:
		await _tree.process_frame
		stream.poll_pending()
		if stream._thread == null:
			return true
	_expect(false, "owned actual loader joins within bounded frames")
	_requires_termination = true # Do not quit/free an executing private worker.
	return false

func _drain(stream: ContinentChunkStream) -> bool:
	for _frame: int in 600:
		await _tree.process_frame
		stream._drain_retired()
		if stream._retiring.is_empty():
			await _tree.process_frame
			await _tree.process_frame
			return true
	_expect(false, "existing shared retirement owner drains within bounded frames")
	_requires_termination = true
	return false

func _settle_zero(label: String) -> bool:
	for _frame: int in 120:
		await _tree.process_frame
		if _lease_count() == 0 and int(_graph().get("resources", -1)) == 0:
			return true
	_expect(false, label + " releases actual leases and weak dependency carriers")
	return false

func _finish() -> Dictionary:
	var result := {"schemaVersion": 1, "workload": "native-streaming-lifetime",
		"ready": _failures == 0 and not _requires_termination,
		"requiresRunnerTermination": _requires_termination, "failures": _failures,
		"executionKind": "exported" if not OS.has_feature("editor") else "source",
		"controller": _controller.snapshot() if _controller != null else {},
		"nativeClass": _native.get_class() if _native != null else "",
		"librarySha256": str(_controller._manifest.get("library_sha256", "")) if _controller != null else "",
		"stages": _stages}
	var destination := OS.get_environment("RABBITLANDS_RESOURCE_LIFETIME_REPORT").strip_edges()
	if destination.is_empty():
		destination = DIRECTORY.path_join("report.json")
	DirAccess.make_dir_recursive_absolute(destination.get_base_dir())
	var file := FileAccess.open(destination, FileAccess.WRITE)
	if file == null:
		_expect(false, "functional lifetime report opens")
		result.ready = false
	else:
		file.store_string(JSON.stringify(result, "  "))
		file.flush()
		file.close()
	if not _requires_termination and _owns_domain:
		# No live jobs or roots remain. The metadata owner can now release its
		# native references before the controller closes; no extension unloading.
		if _tree.has_meta(Admission.TREE_OWNER):
			_tree.remove_meta(Admission.TREE_OWNER)
		if _controller != null:
			_controller.close()
		_controller = null
		_native = null
		for name: String in _environment:
			var previous := str(_environment[name])
			if previous.is_empty(): OS.unset_environment(name)
			else: OS.set_environment(name, previous)
	print("native streaming lifetime: ", "PASS" if bool(result.ready) else "FAIL",
		" report=", destination)
	return result

func run(tree: SceneTree) -> Dictionary:
	_tree = tree
	_expect(Controller.current() == null and Admission.current() == null,
		"functional fixture owns one fresh controller/admission domain")
	if Controller.current() != null or Admission.current() != null:
		return _finish()
	_owns_domain = true
	for name: String in ["RABBITLANDS_CLIENT_RUNTIME", "RABBITLANDS_RESOURCE_ADMISSION",
			"RABBITLANDS_PREPARED_CONTENT", "ELORIA_LOOK"]:
		_environment[name] = OS.get_environment(name)
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "services")
	OS.set_environment("RABBITLANDS_RESOURCE_ADMISSION", "rust")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	OS.set_environment("ELORIA_LOOK", "original")
	var registered := Quantization.ensure_registered() and Vram.ensure_registered() and MapExtension.ensure_registered()
	_expect(registered, "complete main-thread glTF registration precedes actual workers")
	_controller = Controller.new()
	_controller.initialize() # Verified manifest + actual descriptor/DLL SHA.
	_native = _controller.native_runtime()
	_expect(_native != null and _native.get_class() == "RabbitLandsClientRuntime"
		and _native.get_script() == null, "actual verified native class required; no fake adapter or skip")
	if _native == null:
		return _finish()
	for method: StringName in [&"admission_begin", &"admission_event", &"admission_snapshot",
			&"admission_dependencies", &"admission_release_dependencies", &"admission_graph_snapshot"]:
		_expect(_native.has_method(method), "actual native capability " + str(method))
	_expect(Admission.requested() and Prepared.selected_mode() == "raw"
		and not _controller.is_rust_mode(), "only resource services enabled; raw/legacy presentation retained")
	if _failures > 0:
		return _finish()
	_expect(_lease_count() == 0 and int(_graph().get("resources", -1)) == 0,
		"native domain starts empty")
	var stream := _stream(_write_chunk("native-lifetime-primary"))
	stream.update_focus(Vector3.ZERO)
	_expect(stream._thread != null and not (stream._pending.get("_admission_token", {}) as Dictionary).is_empty(),
		"production request hook owns a native lease before actual Thread launch")
	_stage("actual-worker-launched")
	var joined: bool = await _join(stream)
	if not joined:
		return _finish()
	_expect(stream.cells.has("native-lifetime-primary"), "actual production join/install creates the resident cell")
	if not stream.cells.has("native-lifetime-primary"):
		stream.free()
		return _finish()
	var imported := stream.cells["native-lifetime-primary"].root as Node3D
	var root_weak: WeakRef = weakref(imported)
	var mesh_nodes: Array[Node] = imported.find_children("*", "MeshInstance3D", true, false)
	var held_mesh: Mesh = (mesh_nodes[0] as MeshInstance3D).mesh if not mesh_nodes.is_empty() else null
	_expect(held_mesh != null, "external hold references the actual loader-produced Mesh")
	var graph_before := _graph()
	_expect(int(graph_before.get("resources", 0)) > 0 and int(graph_before.get("lease_links", 0)) > 0
		and int(graph_before.get("active", 0)) > 0, "actual DLL records active source dependency ownership")
	_stage("actual-resident-active")
	stream.pause_streaming()
	stream._retire_cell("native-lifetime-primary")
	_expect(int(_graph().get("retiring", 0)) > 0, "real retirement callback transitions native DAG")
	var drained: bool = await _drain(stream)
	if not drained:
		return _finish()
	_expect(root_weak.get_ref() == null and _lease_count() == 0
		and int(_graph().get("lease_links", -1)) == 0,
		"physical root destruction releases native lease independently of held Resource")
	_expect(int(_graph().get("resources", 0)) == int(graph_before.get("resources", -1)),
		"external actual Mesh retains conservative closure after real root destruction")
	_stage("root-gone-external-mesh-held")
	held_mesh = null
	var released: bool = await _settle_zero("last actual Mesh release")
	stream.free()
	if not released:
		return _finish()
	_expect(int(_graph().get("physical_releases", 0)) > 0, "actual DLL acknowledges physical dependency release")
	_stage("external-mesh-released")
	stream = _stream(_write_chunk("native-lifetime-owner-exit"))
	stream.update_focus(Vector3.ZERO)
	_expect(stream._thread != null and _lease_count() == 1,
		"pending owner-exit fixture starts a second real admitted worker")
	var old_orphans := ContinentChunkStream.orphans_pending()
	stream.free() # Review contract transfers alive OR finished unjoined jobs.
	_expect(ContinentChunkStream.orphans_pending() == old_orphans + 1 and _lease_count() == 1,
		"owner exit hands actual worker to reaper without releasing its native lease")
	var pending: Dictionary = _native.call("admission_snapshot")
	_expect(int(pending.get("cancelled", 0)) == 1, "actual native pending worker is cancelled but remains charged")
	_stage("owner-exited-worker-owned-by-reaper")
	for _frame: int in 600:
		ContinentChunkStream.reap_orphans()
		if ContinentChunkStream.orphans_pending() == old_orphans:
			break
		await _tree.process_frame
	if ContinentChunkStream.orphans_pending() != old_orphans:
		_expect(false, "existing orphan reaper joins actual worker within bounded frames")
		_requires_termination = true
		return _finish()
	released = await _settle_zero("joined orphan root and actual Resources")
	var final := Admission.snapshot()
	var dependency: Dictionary = final.get("dependency_graph", {})
	_expect(str(final.get("mode", "")) == "rust" and int(final.get("issued_leases", -1)) == 0
		and int(final.get("transition_failures", -1)) == 0,
		"actual global owner finishes without fallback or lost native leases")
	_expect(dependency.get("failures", {}) == {} and int(dependency.get("incomplete_retained_groups", -1)) == 0
		and int(dependency.get("carrier_groups", -1)) == 0 and int(dependency.get("resources", -1)) == 0,
		"production DAG and weak carrier ledger fully release after material-free lifetime fixture")
	_expect(int(_graph().get("registrations", 0)) >= 2 and int(_graph().get("physical_releases", 0)) >= 2
		and int(_graph().get("lease_links", -1)) == 0 and released,
		"actual DLL proves both production registration and joined physical release")
	_stage("joined-cleanup-complete")
	return _finish()

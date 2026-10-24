extends SceneTree

## A worker-owned import must not publish deletion of its owned placeholders to
## the main thread before it finishes changing the private owner's list.
const ExternalMeshPool := preload("res://src/world/external_mesh_pool.gd")
const KEY := "rl-detached-loader-lifetime-fixture"
const MAX_WORKER_MSEC := 5000

var failures := 0
var _worker: Thread
var _mesh: Mesh

class LifetimeTrace extends RefCounted:
	var mutex := Mutex.new()
	var events: Array[Dictionary] = []

	func record(label: String) -> void:
		mutex.lock()
		events.append({"label": label, "thread": OS.get_thread_caller_id()})
		mutex.unlock()

	func snapshot() -> Array[Dictionary]:
		mutex.lock()
		var result := events.duplicate(true)
		mutex.unlock()
		return result

class TracedNode extends Node3D:
	var trace: LifetimeTrace
	var label := ""

	func _notification(what: int) -> void:
		if what == NOTIFICATION_PREDELETE and trace != null:
			trace.record(label)

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _fixture(detached: bool, trace: LifetimeTrace) -> Dictionary:
	var loader := WorldLoader.new()
	loader.detached_build = detached
	var imported := Node3D.new()
	imported.name = "PrivateImport"
	loader.add_child(imported)
	loader.world_root = imported
	var first := Node3D.new()
	first.name = "Before"
	imported.add_child(first)
	var placeholder := TracedNode.new()
	placeholder.name = "Placement"
	placeholder.label = "placeholder-predelete"
	placeholder.trace = trace
	placeholder.position = Vector3(2, 3, 4)
	placeholder.visible = false
	placeholder.set_meta(ExternalMeshPool.POOLED_META, KEY)
	imported.add_child(placeholder)
	placeholder.owner = imported
	var child := Node3D.new()
	child.name = "RetainedChild"
	placeholder.add_child(child)
	child.owner = imported
	var last := Node3D.new()
	last.name = "After"
	imported.add_child(last)
	var manifest := WorldManifest.new()
	manifest.source_path = "user://synthetic-loader-lifetime/world.json"
	manifest.data = {"externalMeshes": {KEY + ".glb": "synthetic-published-mesh"}}
	return {"loader": loader, "imported": imported, "placeholder": placeholder,
		"child": child, "manifest": manifest}

func _replace(fixture: Dictionary, trace: LifetimeTrace) -> Dictionary:
	var loader := fixture.loader as WorldLoader
	var imported := fixture.imported as Node3D
	var child := fixture.child as Node3D
	var placed := loader._resolve_shared_meshes(fixture.manifest as WorldManifest, imported)
	trace.record("resolve-returned")
	var replacement := imported.get_child(1) as MeshInstance3D
	return {"placed": placed,
		"placeholderAlive": is_instance_valid(fixture.placeholder),
		"replacementContract": replacement != null and replacement.name == &"Placement"
			and replacement.position == Vector3(2, 3, 4) and not replacement.visible
			and replacement.get_child_count() == 1 and replacement.get_child(0) == child
			and child.owner == imported and imported.get_child(0).name == &"Before"
			and imported.get_child(2).name == &"After"}

func _replace_on_worker(trace: LifetimeTrace) -> Dictionary:
	var thread_id := OS.get_thread_caller_id()
	var fixture := _fixture(true, trace)
	var result := _replace(fixture, trace)
	var loader := fixture.loader as WorldLoader
	# Exercise the other private root disposal path while the builder still owns
	# it. Both paths must finish before any worker result is handed to the main.
	var discarded := TracedNode.new()
	discarded.trace = trace
	discarded.label = "private-unload-predelete"
	loader.unload_world()
	loader.add_child(discarded)
	loader.world_root = discarded
	loader.unload_world()
	result["privateRootAliveAfterUnload"] = is_instance_valid(discarded)
	trace.record("private-unload-returned")
	loader.free()
	result["workerThread"] = thread_id
	return result

func _event_index(events: Array[Dictionary], label: String) -> int:
	for index: int in events.size():
		if str(events[index].label) == label:
			return index
	return -1

func _run() -> void:
	# Publish an in-memory mesh first: acquire() takes the real pool hit path,
	# without asset files, GLTF import, extension registration or GPU readback.
	_mesh = BoxMesh.new()
	ExternalMeshPool._publish_or_adopt(KEY, _mesh)
	var trace := LifetimeTrace.new()
	_worker = Thread.new()
	var error := _worker.start(_replace_on_worker.bind(trace))
	_expect(error == OK, "private import fixture starts on a worker")
	if error != OK:
		_worker = null
		quit(failures)
		return
	var deadline := Time.get_ticks_msec() + MAX_WORKER_MSEC
	while _worker.is_alive() and Time.get_ticks_msec() < deadline:
		await process_frame
	if _worker.is_alive():
		_expect(false, "private import worker completes without a blocking main-thread join")
		# The owning test runner enforces its timeout; never join a live worker
		# which might still need the main rendering loop to serve a request.
		quit(failures)
		return
	var result: Dictionary = _worker.wait_to_finish()
	_worker = null
	var events := trace.snapshot()
	var disposed := _event_index(events, "placeholder-predelete")
	var returned := _event_index(events, "resolve-returned")
	_expect(result.workerThread != OS.get_main_thread_id(), "fixture actually ran off the main thread")
	_expect(result.placed == 1 and bool(result.replacementContract),
		"replacement preserves name, transform, visibility, children, owner and sibling order")
	_expect(not bool(result.placeholderAlive) and disposed >= 0 and disposed < returned,
		"replaced placeholder is destroyed before the detached builder continues")
	_expect(disposed >= 0 and int(events[disposed].thread) == int(result.workerThread),
		"placeholder destruction stays on its creating worker")
	var unloaded := _event_index(events, "private-unload-predelete")
	var unload_returned := _event_index(events, "private-unload-returned")
	_expect(not bool(result.privateRootAliveAfterUnload) and unloaded >= 0
		and unloaded < unload_returned and int(events[unloaded].thread) == int(result.workerThread),
		"unloading a private world completes destruction on the worker before returning")

	# Ordinary loading still defers deletion. This is an owned placeholder too,
	# so its owner's list remains alive until the main deletion queue drains.
	var main_trace := LifetimeTrace.new()
	var main_fixture := _fixture(false, main_trace)
	var main_result := _replace(main_fixture, main_trace)
	_expect(bool(main_result.placeholderAlive) and (main_fixture.placeholder as Node).is_queued_for_deletion(),
		"ordinary loading retains queued placeholder deletion")
	_expect(_event_index(main_trace.snapshot(), "placeholder-predelete") == -1,
		"ordinary placeholder destruction remains deferred")
	await process_frame
	await process_frame
	var main_events := main_trace.snapshot()
	var main_disposed := _event_index(main_events, "placeholder-predelete")
	_expect(main_disposed >= 0 and int(main_events[main_disposed].thread) == OS.get_main_thread_id(),
		"ordinary queued placeholder is destroyed on the main thread")
	var main_loader := main_fixture.loader as WorldLoader
	var ordinary_root: Variant = main_fixture.imported
	main_loader.unload_world()
	_expect(is_instance_valid(ordinary_root) and (ordinary_root as Node).is_queued_for_deletion(),
		"ordinary world unloading retains deferred deletion")
	await process_frame
	await process_frame
	main_loader.free()
	_mesh = null
	print("detached loader node lifetime: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

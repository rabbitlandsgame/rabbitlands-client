extends SceneTree

## No asset import or renderer is required. Exercise real scene ownership,
## collision disabling and destruction, including a resident under a loader.
var failures := 0

class SlowLeaf extends Node:
	func _notification(what: int) -> void:
		if what == NOTIFICATION_PREDELETE:
			OS.delay_usec(3000)

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var stream := ExteriorRegionStream.new()
	stage.add_child(stream)
	stream.set_process(false) # The test supplies deterministic budget slices.
	var loader_parent := Node3D.new()
	stage.add_child(loader_parent)
	var imported := _large_tree()
	loader_parent.add_child(imported)
	var before := imported.find_children("*", "", true, false).size() + 1
	var body := imported.get_node("Group0/Body0") as StaticBody3D
	stream.residents["old"] = {"root": imported}
	stream._evict("old")
	_expect(stream.residents.is_empty(), "eviction immediately removes neighbour picking/adoption access")
	_expect(not imported.visible and body.collision_layer == 0,
		"retired geometry is immediately hidden and non-colliding")
	_expect(imported.get_parent() == loader_parent and not imported.is_queued_for_deletion(),
		"retirement does not detach or schedule whole-tree destruction")
	_expect(not stream._can_dispatch_preload() and not stream.is_idle(),
		"retirement debt blocks new preload allocation and keeps shutdown waiting")
	stream.active_map = "current"
	stream.links = [{"ends": [{"map": "current", "position": [0, 0, 0]},
		{"map": "next", "position": [0, 0, 0]}]}]
	stream.registry = {"next": {"manifest": "user://retirement-dispatch-must-not-run.json"}}
	stream.update_position(Vector3.ZERO)
	_expect(stream._thread == null, "a nearby eligible map cannot dispatch a worker while retirement occupies its slot")
	var first_freed := stream._drain_retired(7, 100000)
	var remaining := imported.find_children("*", "", true, false).size() + 1
	_expect(first_freed == 7 and before - remaining == 7,
		"a seven-node budget destroys exactly seven nodes, including collision leaves")
	_expect(is_instance_valid(imported), "a large tree survives the first retirement slice")
	var frames := 1
	var total := first_freed
	while not stream.is_idle() and frames < 200:
		var count := stream._drain_retired(7, 100000)
		_expect(count <= 7, "each later slice respects the node budget")
		total += count
		frames += 1
	_expect(stream.is_idle() and not is_instance_valid(imported) and total == before,
		"all descendants and their externally parented root are eventually released")
	_expect(frames > 1 and stream._can_dispatch_preload(),
		"preloading resumes only after multi-slice retirement finishes")
	var slow := Node3D.new()
	for index: int in 4:
		slow.add_child(SlowLeaf.new())
	stream._retire({"root": slow}, "slow-release")
	var slow_freed := stream._drain_retired(64, 1000)
	_expect(slow_freed <= 1 and is_instance_valid(slow) and slow.get_child_count() >= 3,
		"one slow destructor exhausts the time budget without releasing the rest of its siblings")
	while not stream.is_idle():
		stream._drain_retired(64, 100000)
	var visuals: Dictionary = {}
	var weak_resources: Array[WeakRef] = []
	for index: int in 3:
		_add_prepared_visual(visuals, weak_resources, index)
	stream._retire({"root": Node3D.new(), "visuals": visuals}, "prepared-visuals")
	stream._drain_retired(1, 100000)
	_expect(_live_resources(weak_resources) == 6 and not stream.is_idle(),
		"freeing the last scene node does not bulk-release prepared models and meshes")
	stream._drain_retired(1, 100000)
	_expect(_live_resources(weak_resources) == 4 and visuals.size() == 2,
		"one resource budget unit releases exactly one PackedScene and its owned mesh")
	stream._drain_retired(2, 100000)
	_expect(_live_resources(weak_resources) == 0 and stream.is_idle(),
		"prepared model resources are eventually released without a final dictionary burst")
	# clear() may retire all three neighbours together. The single worker slot is
	# represented by a stale completion, which must use the same bounded queue.
	for index: int in 3:
		var old := _large_tree()
		loader_parent.add_child(old)
		stream.residents[str(index)] = {"root": old}
	stream.clear()
	var discarded := _large_tree()
	stream._retire({"root": discarded}, "stale-worker")
	_expect(stream._retiring.size() == 4 and not stream._can_dispatch_preload(),
		"three neighbour slots plus one existing worker result are bounded retirement debt")
	stream.set_process(true)
	var deadline := Time.get_ticks_msec() + 5000
	while not stream.is_idle() and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(stream.is_idle() and loader_parent.get_child_count() == 0 and not is_instance_valid(discarded),
		"normal process slices drain disconnect and stale-worker cleanup without a bulk free")
	stage.free()
	print("exterior retirement tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _large_tree() -> Node3D:
	var imported := Node3D.new()
	for group_index: int in 12:
		var group := Node3D.new()
		group.name = "Group%d" % group_index
		imported.add_child(group)
		for body_index: int in 4:
			var body := StaticBody3D.new()
			body.name = "Body%d" % body_index
			body.collision_layer = ExteriorRegionStream.PREVIEW_SURFACE_LAYER
			group.add_child(body)
			var shape := CollisionShape3D.new()
			shape.shape = BoxShape3D.new()
			body.add_child(shape)
	return imported

func _add_prepared_visual(visuals: Dictionary, weak_resources: Array[WeakRef], index: int) -> void:
	var model := Node3D.new()
	var visual := MeshInstance3D.new()
	visual.mesh = BoxMesh.new()
	model.add_child(visual)
	visual.owner = model
	var packed := PackedScene.new()
	packed.pack(model)
	weak_resources.append(weakref(packed))
	weak_resources.append(weakref(visual.mesh))
	visuals[str(index)] = packed
	model.free()

func _live_resources(references: Array[WeakRef]) -> int:
	var count := 0
	for reference: WeakRef in references:
		if reference.get_ref() != null:
			count += 1
	return count

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

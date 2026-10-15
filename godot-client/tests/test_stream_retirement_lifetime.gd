extends SceneTree

## Retirement can run callbacks and encounter nodes already released by their
## owner. Neither case may let a second traversal free an in-flight node.
var failures := 0

class ProcessProbe extends ContinentChunkStream:
	var in_process_callback := false
	func _process(delta: float) -> void:
		in_process_callback = true
		super._process(delta)
		in_process_callback = false

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _chunk(stream: ContinentChunkStream, identity: String) -> Node3D:
	var imported := Node3D.new()
	imported.name = "RetiredChunk"
	stream.add_child(imported)
	stream.cells[identity] = {"root": imported,
		"entry": {"id": identity, "estimatedResidentBytes": 1}}
	return imported

func _run() -> void:
	var chunks := ContinentChunkStream.new()
	root.add_child(chunks)
	chunks.set_process(false)
	var imported := _chunk(chunks, "stale")
	var leaf := Node.new()
	imported.add_child(leaf)
	chunks._retire_cell("stale")
	_expect(imported.process_mode == Node.PROCESS_MODE_DISABLED,
		"a retired chunk stops its inherited processing before destruction")
	# A previously visited leaf can disappear at the frame boundary, e.g. a
	# pick proxy queued by MapObject3D.release_placement().
	(chunks._retiring[0].stack as Array).append(leaf)
	leaf.free()
	chunks._drain_retired()
	_expect(chunks._retiring.is_empty() and not is_instance_valid(imported),
		"chunk cleanup skips stale traversal entries and finishes the tree")
	chunks.free()

	var exterior := ExteriorRegionStream.new()
	root.add_child(exterior)
	exterior.set_process(false)
	var map_root := Node3D.new()
	var callback_leaf := Node.new()
	map_root.add_child(callback_leaf)
	root.add_child(map_root)
	var nested_counts: Array[int] = []
	callback_leaf.tree_exiting.connect(func() -> void:
		# A destructor emits signals before it finishes detaching the node.
		if nested_counts.is_empty():
			nested_counts.append(-1)
			nested_counts[0] = exterior._drain_retired(64, 100000))
	exterior._retire({"root": map_root}, "reentrant")
	var freed := exterior._drain_retired(64, 100000)
	_expect(nested_counts == [0] and freed == 2 and exterior.is_idle(),
		"exit callbacks cannot re-enter exterior destruction or free a node twice")
	exterior.free()

	var second := ContinentChunkStream.new()
	root.add_child(second)
	second.set_process(false)
	var cell := _chunk(second, "reentrant")
	var second_leaf := Node.new()
	cell.add_child(second_leaf)
	var exits: Array[int] = []
	second_leaf.tree_exiting.connect(func() -> void:
		if exits.is_empty():
			exits.append(1)
			second._drain_retired())
	second._retire_cell("reentrant")
	second._drain_retired()
	_expect(exits == [1] and second._retiring.is_empty() and not is_instance_valid(cell),
		"exit callbacks cannot re-enter chunk destruction")
	second.free()

	var probe := ProcessProbe.new()
	root.add_child(probe)
	var deferred_cell := _chunk(probe, "after-process")
	var callback_states: Array[bool] = []
	deferred_cell.tree_exiting.connect(func() -> void:
		callback_states.append(probe.in_process_callback))
	probe._retire_cell("after-process")
	await process_frame
	await process_frame
	_expect(callback_states == [false] and probe._retiring.is_empty(),
		"automatic chunk destruction runs after process callbacks return")
	probe.free()
	print("stream retirement lifetime: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

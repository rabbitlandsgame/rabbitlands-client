extends SceneTree
## Real, asset-free retirement trees. A keeps more than a frame of work queued
## and always calls first; B stops requesting while alive, then resumes. The
## scheduler may remove B's waiting slot but must never discard B's jobs.
const Budget := preload("res://src/world/resource_retirement_budget.gd")
var failures := 0
var _created := {"a": 0, "b": 0, "exterior": 0}
var _freed := {"a": 0, "b": 0, "exterior": 0}
var _seen: Dictionary = {}
var _duplicates := 0
var _sequence := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _track(node: Node, label: String) -> void:
	_created[label] = int(_created[label]) + 1
	node.tree_exiting.connect(_on_exit.bind(label, node.get_instance_id()))

func _on_exit(label: String, identity: int) -> void:
	if _seen.has(identity):
		_duplicates += 1
	_seen[identity] = true
	_freed[label] = int(_freed[label]) + 1

func _tree(parent: Node3D, label: String, leaves: int) -> Node3D:
	var imported := Node3D.new()
	parent.add_child(imported)
	_track(imported, label)
	for index: int in leaves:
		var leaf := Node.new()
		imported.add_child(leaf)
		_track(leaf, label)
	return imported

func _chunk(stream: ContinentChunkStream, label: String, leaves: int) -> void:
	_sequence += 1
	var identity := "%s-%d" % [label, _sequence]
	var imported := _tree(stream, label, leaves)
	stream.cells[identity] = {"root": imported,
		"entry": {"id": identity, "estimatedResidentBytes": 1}}
	stream._retire_cell(identity)

func _remaining(label: String) -> int:
	return int(_created[label]) - int(_freed[label])

func _visual_releases(exterior: ExteriorRegionStream) -> int:
	var timings := exterior.get("_resource_timings") as Dictionary
	return int((timings.get(&"prepared_visual_release", {}) as Dictionary).get("count", 0))

func _total_freed() -> int:
	return int(_freed.a) + int(_freed.b) + int(_freed.exterior)

func _pass(a: ContinentChunkStream, b: ContinentChunkStream,
		exterior: ExteriorRegionStream, request_b: bool) -> void:
	# Match the real teardown observer, including an immediate repeated
	# observation before fixed-order drains. TTL pruning happens first.
	var before := Budget.diagnostic_snapshot()
	var waiting_before := int(before.waiting_owners)
	a.pause_streaming()
	b.pause_streaming()
	a.pause_streaming()
	b.pause_streaming()
	expect(int(Budget.diagnostic_snapshot().waiting_owners) == waiting_before,
		"repeated pause observations retain FIFO waiting slots within the same frame")
	var nodes_before := _total_freed()
	var visuals_before := _visual_releases(exterior)
	a._drain_retired()
	if request_b:
		b._drain_retired()
	exterior._drain_retired(100000, 1000000)
	var report := Budget.diagnostic_snapshot()
	var issued := _total_freed() - nodes_before + _visual_releases(exterior) - visuals_before
	# A process_frame waiter can resume before Engine's process-frame counter
	# advances. Compare this synchronous pass's charge, including repeated
	# observations within the same engine frame, against its actual releases.
	var charged := int(report.freed_nodes) - int(before.freed_nodes)
	expect(int(report.frame) == int(before.frame) and charged == issued
		and int(report.freed_nodes) <= Budget.FRAME_NODE_LIMIT,
		"every real node/visual release charges the same aggregate allowance")

func _run() -> void:
	var a := ContinentChunkStream.new()
	var b := ContinentChunkStream.new()
	var exterior := ExteriorRegionStream.new()
	root.add_child(a)
	root.add_child(b)
	root.add_child(exterior)
	a.set_process(false)
	b.set_process(false)
	exterior.set_process(false)
	_chunk(a, "a", 256)
	_chunk(b, "b", 70)
	var imported := _tree(exterior, "exterior", 70)
	var prepared: PackedScene = PackedScene.new()
	var prepared_reference: WeakRef = weakref(prepared)
	exterior._retire({"root": imported, "visuals": {"fixture": prepared}}, "fixture")
	prepared = null
	var expired_before := int(Budget.diagnostic_snapshot().expired_owners)
	var stopped_freed := 0
	var c_progress_while_b_stopped := false
	var finished_frame := -1
	for frame: int in 120:
		# More than 64 pending nodes before A calls makes a first-caller-only
		# policy spend every allowance on A forever, even at fixed caller order.
		if _remaining("a") <= 128:
			_chunk(a, "a", 256)
		expect(_remaining("a") > Budget.FRAME_NODE_LIMIT,
			"first caller stays continuously replenished while later queues wait")
		if frame == 1:
			stopped_freed = int(_freed.b)
		var request_b := frame == 0 or frame >= 4
		_pass(a, b, exterior, request_b)
		if frame >= 1 and frame < 4:
			expect(int(_freed.b) == stopped_freed and not b._retiring.is_empty(),
				"stopped caller retains its exact pending jobs without callbacks")
			c_progress_while_b_stopped = c_progress_while_b_stopped or int(_freed.exterior) > 0
		if not exterior._retiring.is_empty():
			expect(not exterior._can_dispatch_preload(), "retained exterior root preserves preload backpressure")
		if frame >= 4 and b._retiring.is_empty() and exterior._retiring.is_empty():
			finished_frame = frame
			break
		await process_frame
	expect(c_progress_while_b_stopped,
		"another real retirement advances after stopped-owner expiry despite continuously renewed first caller")
	expect(int(Budget.diagnostic_snapshot().expired_owners) > expired_before,
		"live stopped-owner reservation expires instead of blocking unrelated queues")
	expect(finished_frame >= 4 and finished_frame < 120,
		"later real queues complete within a bounded multi-frame run while first caller remains busy")
	expect(_remaining("b") == 0 and _remaining("exterior") == 0
		and prepared_reference.get_ref() == null and _visual_releases(exterior) == 1,
		"resumed caller and exterior release every owned node and prepared scene")
	# Stop replenishing A, then drain the remaining queues rather than making a
	# bulk free look like successful bounded retirement in the assertions.
	for frame: int in 120:
		await process_frame
		_pass(a, b, exterior, true)
		if a._retiring.is_empty() and b._retiring.is_empty() and exterior._retiring.is_empty():
			break
	expect(a._retiring.is_empty() and b._retiring.is_empty() and exterior._retiring.is_empty()
		and exterior._can_dispatch_preload(), "all queues finish and preload becomes eligible again")
	expect(_duplicates == 0 and _created == _freed,
		"all synthetic retirement nodes exit exactly once with no lost jobs")
	expect(int(Budget.diagnostic_snapshot().waiting_owners) == 0,
		"finished queues leave no owner reservation")
	a.free()
	b.free()
	exterior.free()
	await process_frame
	print("resource retirement liveness: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

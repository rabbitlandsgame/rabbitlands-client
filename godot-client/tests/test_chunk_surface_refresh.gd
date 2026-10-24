extends SceneTree
const Queue := preload("res://src/world/chunk_surface_refresh.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func cell(stream: ContinentChunkStream, identity: String, bounds: Dictionary) -> Node3D:
	var imported := Node3D.new()
	stream.add_child(imported)
	stream.cells[identity] = {"root": imported, "manifest": WorldManifest.new(),
		"entry": {"id": identity, "bounds": bounds, "estimatedResidentBytes": 1}}
	return imported

func _run() -> void:
	var stream := ContinentChunkStream.new()
	var neighbour := ContinentChunkStream.new()
	root.add_child(stream)
	root.add_child(neighbour)
	stream.set_process(false)
	neighbour.set_process(false)
	var bounds := {"min": [0, -10, 0], "max": [10, 10, 10]}
	var imported := cell(stream, "same-id", bounds)
	var other := cell(neighbour, "same-id", bounds)
	var queue := Queue.new()
	queue.queue_chunk("same-id", imported)
	queue.queue_chunk("same-id", imported)
	queue.queue_chunk("same-id", other)
	var batch := queue.take()
	expect(int(batch.notifications) == 3 and batch.regions.size() == 2
		and queue.pending_notifications() == 0,
		"notifications coalesce by stream and cell rather than a repeated chunk ID")
	stream.transform = Transform3D(Basis(Vector3.UP, PI / 2.0), Vector3(100, 0, 200))
	neighbour.position = Vector3(-100, 0, -200)
	var inside := stream.global_transform * Vector3(5, 0, 5)
	var outside := stream.global_transform * Vector3(20, 0, 20)
	expect(Queue.should_refresh(batch, inside) and not Queue.should_refresh(batch, outside),
		"translated and rotated stream bounds classify world-space grounding rays")
	expect(Queue.should_refresh(batch, outside, true) and Queue.should_refresh(batch, outside, false, true),
		"priority and ungrounded actors remain eligible outside the arriving bounds")
	var changed := Queue.current_chunks(batch, stream)
	expect(changed.size() == 1 and changed.has("same-id"), "binding scope includes only the current map's changed cells")
	stream.position += Vector3(100, 0, 0)
	var rebased := stream.global_transform * Vector3(5, 0, 5)
	expect(Queue.should_refresh(batch, rebased) and not Queue.should_refresh(batch, inside),
		"a handoff rebase invalidates the cached inverse transform")
	queue.queue_chunk("same-id", imported)
	stream.cells.erase("same-id")
	var retired := queue.take()
	expect(retired.regions.is_empty() and int(retired.invalidated_regions) == 1
		and not Queue.should_refresh(retired, rebased, true, true),
		"retired cells cannot schedule stale grounding even for priority exceptions")
	expect(not Queue.should_refresh(batch, rebased)
		and Queue.should_refresh(batch, neighbour.global_transform * Vector3(5, 0, 5)),
		"remaining live neighbour regions remain valid after current-cell retirement")
	queue.queue_chunk("same-id", other)
	neighbour.process_mode = Node.PROCESS_MODE_DISABLED
	var retiring_root := queue.take()
	expect(retiring_root.regions.is_empty() and not Queue.has_live_changes(retiring_root),
		"an attached exterior-retirement root is excluded before its descendants are freed")
	neighbour.process_mode = Node.PROCESS_MODE_INHERIT
	queue.queue_chunk("same-id", other)
	neighbour.free()
	var removed := queue.take()
	expect(removed.regions.is_empty() and not Queue.has_live_changes(removed)
		and not Queue.should_refresh(batch, rebased, true, true),
		"destroying a stream before the physics flush leaves no strong-root or stale-node work")
	var replacement := cell(stream, "same-id", bounds)
	expect(not queue.queue_chunk("same-id", imported), "a replaced cell's stale ready notification is ignored")
	queue.queue_chunk("same-id", replacement)
	queue.queue_full()
	queue.queue_full()
	var full := queue.take()
	expect(bool(full.full) and int(full.notifications) == 3
		and Queue.should_refresh(full, Vector3(100000, 0, 100000)),
		"resident full fallbacks coalesce with chunk notifications into one conservative batch")
	queue.queue_chunk("same-id", replacement)
	queue.clear()
	expect(queue.pending_notifications() == 0 and not Queue.has_live_changes(queue.take()),
		"session cancellation empties pending readiness work")
	stream.free()
	print("chunk surface refresh tests: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

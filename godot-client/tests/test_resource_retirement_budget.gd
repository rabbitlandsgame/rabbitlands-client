extends SceneTree
const Budget := preload("res://src/world/resource_retirement_budget.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _owners(count: int) -> Array[Node]:
	var result: Array[Node] = []
	for index: int in count:
		result.append(Node.new())
	return result

func _dispose(owners: Array[Node]) -> void:
	for owner: Node in owners:
		Budget.cancel(owner)
		owner.free()

func _consume(owner: Node, still_pending := true) -> bool:
	var lease := Budget.begin_slice(owner, 64, 2000)
	if lease.is_empty():
		return false
	# Deterministic scheduler accounting, not a measurement of Node.free().
	return Budget.end_slice(lease, 64, 2000, still_pending)

func _run() -> void:
	await _lease_accounting()
	await _renewing_fairness()
	await _stopped_and_freed_owners()
	await _abandoned_and_stale_tickets()
	await _repeated_abandonment()
	await _stream_cancel_hooks()
	print("resource retirement budget: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

func _lease_accounting() -> void:
	var owners := _owners(3)
	var before := Budget.diagnostic_snapshot()
	var first := Budget.begin_slice(owners[0], 10, 1000)
	expect(not first.is_empty() and int(first.nodes) == 10 and int(first.usec) == 1000,
		"first owner receives bounded scalar lease")
	if first.is_empty():
		_dispose(owners)
		return
	expect(Budget.begin_slice(owners[1], 64, 2000).is_empty(),
		"nested owner registers but cannot spend an uncharged lease")
	Budget.cancel(owners[0])
	expect(Budget.begin_slice(owners[1], 64, 2000).is_empty(),
		"cancelling the active owner does not unlock its uncharged work")
	var wrong := first.duplicate()
	wrong.ticket = int(first.ticket) + 1
	expect(not Budget.end_slice(wrong, 10, 1000, true)
		and bool(Budget.diagnostic_snapshot().slice_active),
		"wrong ticket cannot end another lease")
	expect(Budget.end_slice(first, 10, 1000, true), "matching cancelled-owner lease still charges actual work")
	var second := Budget.begin_slice(owners[1], 100000, 1000000)
	expect(not second.is_empty() and int(second.nodes) == 54 and int(second.usec) == 1000,
		"next owner receives only remaining aggregate credit")
	if not second.is_empty():
		Budget.end_slice(second, 54, 1500, false)
	expect(Budget.begin_slice(owners[2], 64, 2000).is_empty(),
		"indivisible time overrun blocks every later owner this frame")
	var after := Budget.diagnostic_snapshot()
	expect(int(after.freed_nodes) == 64 and int(after.spent_us) == 2500
		and int(after.overrun_frames) == int(before.overrun_frames) + 1,
		"actual overrun remains visible without clamping to the lease")
	_dispose(owners)
	await process_frame

func _renewing_fairness() -> void:
	var owners := _owners(3)
	var history: Array[int] = []
	for frame: int in 10:
		var granted := -1
		for index: int in owners.size():
			if _consume(owners[index]):
				expect(granted == -1, "full synthetic allowance grants only one owner per frame")
				granted = index
		history.append(granted)
		await process_frame
	for start: int in range(1, history.size() - 2):
		var seen: Dictionary = {}
		for offset: int in 3:
			seen[history[start + offset]] = true
		expect(seen.has(0) and seen.has(1) and seen.has(2),
			"fixed caller order gives each continuously renewing owner a turn in every three-frame window")
	_dispose(owners)
	await process_frame

func _stopped_and_freed_owners() -> void:
	var owners := _owners(3)
	_consume(owners[0])
	_consume(owners[1]) # Registers behind the initial owner without credit.
	_consume(owners[2])
	await process_frame
	expect(_consume(owners[0]), "initial owner takes the next queued turn")
	# Owner1 is now the head but deliberately stops requesting, without cancel.
	expect(not _consume(owners[2]), "live stopped head receives only its bounded callback-order grace")
	var before := Budget.diagnostic_snapshot()
	await process_frame
	expect(not _consume(owners[0]) and _consume(owners[2]),
		"stopped head expires so later owner advances on the next frame")
	expect(int(Budget.diagnostic_snapshot().expired_owners) > int(before.expired_owners),
		"stopped live owner expiry is explicit")
	await process_frame
	expect(_consume(owners[0]), "the other renewing owner also resumes")
	_dispose(owners)
	await process_frame
	var departed := Node.new()
	var survivor := Node.new()
	var lease := Budget.begin_slice(departed, 1, 1)
	if not lease.is_empty():
		Budget.end_slice(lease, 0, 0, true)
	var reference: WeakRef = weakref(departed)
	departed.free() # No cancel hook: the scheduler must not retain this Node.
	var survivor_lease := Budget.begin_slice(survivor, 64, 2000)
	expect(reference.get_ref() == null and not survivor_lease.is_empty(),
		"freed weak owner is pruned immediately without reserving remaining credit")
	if not survivor_lease.is_empty():
		Budget.end_slice(survivor_lease, 0, 0, false)
	survivor.free()
	await process_frame

func _abandoned_and_stale_tickets() -> void:
	var owners := _owners(2)
	var before := Budget.diagnostic_snapshot()
	var abandoned := Budget.begin_slice(owners[0], 1, 1)
	Budget.begin_slice(owners[1], 64, 2000) # Nested request keeps the waiting turn.
	await process_frame
	var recovered := Budget.diagnostic_snapshot()
	expect(int(recovered.abandoned_slices) == int(before.abandoned_slices) + 1
		and not bool(recovered.slice_active) and not bool(recovered.abandoned_cost_known),
		"abandoned synchronous lease recovers without claiming a measured zero cost")
	# Recovery must let the waiting owner run without manually cancelling A.
	var current := Budget.begin_slice(owners[1], 64, 2000)
	expect(not current.is_empty() and not Budget.end_slice(abandoned, 0, 0, false)
		and bool(Budget.diagnostic_snapshot().slice_active),
		"stale previous-frame ticket cannot unlock the current owner's lease")
	if not current.is_empty():
		Budget.end_slice(current, 0, 0, false)
	_dispose(owners)
	await process_frame

func _repeated_abandonment() -> void:
	var owners := _owners(3)
	var before := Budget.diagnostic_snapshot()
	var grants := [0, 0, 0]
	for frame: int in 12:
		# A always calls first and deliberately abandons each granted lease.
		# No owner is cancelled until after the progress assertions below.
		var abandoned := Budget.begin_slice(owners[0], 64, 2000)
		if not abandoned.is_empty():
			grants[0] = int(grants[0]) + 1
		for index: int in [1, 2]:
			if _consume(owners[index]):
				grants[index] = int(grants[index]) + 1
		await process_frame
	expect(int(grants[0]) >= 3 and int(grants[1]) >= 3 and int(grants[2]) >= 3,
		"repeatedly retrying/abandoning first caller yields bounded progress to both renewing waiters")
	var after := Budget.diagnostic_snapshot()
	expect(int(after.abandoned_slices) >= int(before.abandoned_slices) + 3
		and not bool(after.abandoned_cost_known),
		"repeated abandoned work keeps explicit unknown cost diagnostics")
	_dispose(owners)
	await process_frame

func _stream_cancel_hooks() -> void:
	var chunks := ContinentChunkStream.new()
	var exterior := ExteriorRegionStream.new()
	root.add_child(chunks)
	root.add_child(exterior)
	chunks.set_process(false)
	exterior.set_process(false)
	var chunk_lease := Budget.begin_slice(chunks, 1, 100)
	if not chunk_lease.is_empty():
		Budget.end_slice(chunk_lease, 0, 0, true)
	chunks.pause_streaming()
	expect(int(Budget.diagnostic_snapshot().waiting_owners) == 0,
		"initial pause cancels the chunk owner's old waiting turn")
	var renewed := Budget.begin_slice(chunks, 1, 100)
	if not renewed.is_empty():
		Budget.end_slice(renewed, 0, 0, true)
	var paused_waiting := int(Budget.diagnostic_snapshot().waiting_owners)
	chunks.pause_streaming()
	chunks.pause_streaming()
	expect(paused_waiting == 1 and int(Budget.diagnostic_snapshot().waiting_owners) == paused_waiting,
		"repeated pause in the same frame preserves a renewed waiting slot")
	exterior._retire({"root": chunks}, "paused-takeover")
	expect(int(Budget.diagnostic_snapshot().waiting_owners) == 0 and not exterior._retiring.is_empty(),
		"actual exterior takeover cancels an already-paused owner without dropping the retirement job")
	var exterior_lease := Budget.begin_slice(exterior, 1, 100)
	if not exterior_lease.is_empty():
		Budget.end_slice(exterior_lease, 0, 0, true)
	exterior.clear()
	expect(int(Budget.diagnostic_snapshot().waiting_owners) == 0,
		"clear cancels an exterior waiting turn without resetting shared credit")
	for frame: int in 8:
		await process_frame
		exterior._drain_retired()
		if exterior._retiring.is_empty():
			break
	expect(exterior._retiring.is_empty() and not is_instance_valid(chunks),
		"clear preserves the transferred retirement job until its bounded drainer completes it")
	exterior.free()
	await process_frame
	var exiting := ExteriorRegionStream.new()
	root.add_child(exiting)
	exiting.set_process(false)
	var exit_lease := Budget.begin_slice(exiting, 1, 100)
	if not exit_lease.is_empty():
		Budget.end_slice(exit_lease, 0, 0, true)
	var cancelled_before := int(Budget.diagnostic_snapshot().cancelled_owners)
	exiting.free()
	expect(int(Budget.diagnostic_snapshot().cancelled_owners) == cancelled_before + 1,
		"exit hook explicitly cancels its live owner before weak pruning")
	await process_frame

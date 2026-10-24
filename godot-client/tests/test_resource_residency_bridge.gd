extends SceneTree
const Bridge := preload("res://src/runtime/resource_residency.gd")
const KEY := "1111111111111111111111111111111111111111111111111111111111111111"
var failures := 0

class FakeRuntime extends RefCounted:
	var catalog_calls := 0
	var captured := PackedInt64Array()
	var next := PackedInt64Array()
	var status := 0
	var completions: Array[PackedInt64Array] = []
	var stats := {"schema": 1, "loading": 0, "ready": 0, "active": 0, "retiring": 0}
	func runtime_info() -> Dictionary: return {"residency_schema": 1}
	func residency_catalog(records: PackedInt64Array, _dependencies: PackedInt64Array) -> int:
		catalog_calls += 1
		captured = records.duplicate()
		return 0
	func residency_reconcile(_records: PackedInt64Array, _epoch: int) -> int: return 0
	func residency_events(records: PackedInt64Array) -> int:
		completions.append(records.duplicate())
		return 0
	func residency_retry(_keys: PackedInt64Array, _epoch: int) -> int: return 0
	func residency_step(_epoch: int, _budget: PackedInt64Array, _capacity: int) -> PackedInt64Array:
		var result := next
		next = PackedInt64Array()
		return result
	func residency_snapshot(_budget: PackedInt64Array) -> Dictionary: return stats.duplicate()
	func get_last_status() -> int: return status

class FakeController extends RefCounted:
	var native := FakeRuntime.new()
	var epoch := 1
	func native_runtime() -> RefCounted: return native
	func current_epoch() -> int: return epoch

func _init() -> void: _run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if value: print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _row(kind: int, epoch := 1, generation := 7, key := KEY) -> PackedInt64Array:
	var result := Bridge._key(key)
	result.append_array(PackedInt64Array([generation, epoch, kind, 0]))
	return result

func _foreign(bridge: ClientResourceResidency, action: Dictionary) -> bool:
	return not bridge.complete(action, Bridge.LOADED) and bridge.outstanding().is_empty() \
		and str(bridge.snapshot().get("failure")) == "foreign_thread_snapshot"

func _run() -> void:
	var controller := FakeController.new()
	var invalid := Bridge.new()
	_expect(not invalid.initialize(controller, [{"key": "bad", "dependencies": []}])
		and controller.native.catalog_calls == 0, "invalid identity rejects before native catalog mutation")
	var bridge := Bridge.new()
	_expect(bridge.initialize(controller, [{"key": KEY, "dependencies": []}]), "optional schema capability initializes")
	_expect(controller.native.captured[6] == 3 and controller.native.captured[4] == 0 \
		and controller.native.captured[5] == 0, "missing CPU/GPU measurements stay explicitly unknown")
	var second := Bridge.new()
	_expect(not second.initialize(controller, []), "two planners cannot reserve independent global budgets")
	controller.native.next = _row(Bridge.LOAD)
	var load := bridge.next_actions(100, 100, 2, 1, 2)[0]
	_expect(bridge.outstanding().size() == 1, "issued load persists before callback dispatch/completion")
	controller.native.next = _row(Bridge.CANCEL_LOAD)
	var cancel := bridge.next_actions(100, 100, 2, 1, 2)[0]
	_expect(bridge.outstanding().size() == 1 and bool(bridge.outstanding()[0].cancel_requested)
		and int(bridge.outstanding()[0].kind) == Bridge.LOAD,
		"cancel request retains the original owned load rather than fabricating release")
	_expect(not bridge.complete(cancel, Bridge.RELEASED) and controller.native.completions.is_empty(),
		"a cancellation token cannot acknowledge resource destruction")
	controller.epoch = 2
	var worker := Thread.new()
	var started := worker.start(_foreign.bind(bridge, load))
	_expect(started == OK, "foreign-thread guard fixture starts")
	if started == OK:
		var deadline := Time.get_ticks_msec() + 5000
		while worker.is_alive() and Time.get_ticks_msec() < deadline: await process_frame
		if worker.is_alive():
			_expect(false, "foreign guard finishes without joining a live worker")
			quit(1)
			return
		_expect(bool(worker.wait_to_finish()) and bridge.outstanding().size() == 1,
			"foreign completion cannot mutate owner-thread action ledger")
	_expect(bridge.complete(load, Bridge.LOADED) and int(controller.native.completions[0][5]) == 1,
		"old-epoch owned completion remains accountable after session reset")
	controller.native.next = _row(Bridge.RELEASE_READY, 1)
	var release := bridge.next_actions(100, 100, 2, 1, 2)[0]
	_expect(bridge.request_close() and not bridge.finish_close(), "close cannot finish before actual release acknowledgement")
	_expect(bridge.complete(release, Bridge.RELEASED) and bridge.finish_close(), "drained close releases bridge only after acknowledgement")
	# Invalid whole batches must not overwrite an existing owned handle.
	var next_controller := FakeController.new()
	var guarded := Bridge.new()
	_expect(guarded.initialize(next_controller, [{"key": KEY, "dependencies": [], "cpu_bytes": 1, "gpu_bytes": 1}]),
		"new authority initializes only after prior drain")
	next_controller.native.next = _row(Bridge.LOAD)
	var guarded_load := guarded.next_actions(10, 10, 1, 0)[0]
	next_controller.native.next = _row(Bridge.INSTALL, 1, 9, "2".repeat(64))
	_expect(guarded.next_actions(10, 10, 1, 0).is_empty() and guarded.outstanding().size() == 1,
		"malformed native output preserves already-issued load ownership")
	_expect(guarded.request_close() and guarded.complete(guarded_load, Bridge.LOAD_FAILED) and guarded.finish_close(),
		"owned completion can drain after planning failure without a blanket purge")
	print("resource residency bridge: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

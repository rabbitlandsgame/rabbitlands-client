extends SceneTree
## Requires the freshly built, verified optional adapter. No silent skip.
const Controller := preload("res://src/runtime/client_runtime.gd")
const Words := preload("res://src/runtime/resource_residency.gd")
var failures := 0
func _init() -> void:
	_run.call_deferred()
func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("native admission: " + message)
func _foreign(native: RefCounted, dto: PackedInt64Array) -> Variant:
	return native.call("admission_begin", 2, dto)
func _run() -> void:
	var previous := OS.get_environment("RABBITLANDS_CLIENT_RUNTIME")
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "services")
	var controller := Controller.new()
	controller.initialize()
	var native := controller.native_runtime()
	_expect(native != null and native.has_method("admission_begin"), "verified native admission API required")
	if native == null or not native.has_method("admission_begin"):
		quit(1)
		return
	_expect(not controller.is_rust_mode(), "services mode leaves mounted/remote presentation on legacy")
	var dto := PackedInt64Array([50,20,100,0,1,0,7,8,0,0])
	var first: PackedInt64Array = native.call("admission_begin", 1, dto)
	_expect(first.size() == 2 and first[0] > 0 and first[1] == 0, "native grants first actual reservation")
	if first.size() != 2:
		quit(1)
		return
	var id := first[0]
	var root_key := Words._key("native-dag-root".sha256_text())
	var mesh_key := Words._key("native-dag-mesh".sha256_text())
	var image_key := Words._key("native-dag-image".sha256_text())
	var records := PackedInt64Array()
	for row: Array in [[root_key,0,1],[mesh_key,1,1],[image_key,2,0]]:
		records.append_array(row[0])
		records.append_array(PackedInt64Array([0,0,3,int(row[1]),int(row[2])]))
	var edges := mesh_key.duplicate()
	edges.append_array(image_key)
	_expect(native.has_method("admission_dependencies") \
		and native.call("admission_dependencies", id, 1, records, edges) == 0,
		"actual adapter registers a full source-SHA dependency graph before launch")
	var dependency_snapshot: Dictionary = native.call("admission_graph_snapshot")
	_expect(int(dependency_snapshot.resources) == 3 and int(dependency_snapshot.edges) == 2 \
		and int(dependency_snapshot.loading) == 3, "native graph tracks reserved dependencies as in-flight unknown allocations")
	var denied: PackedInt64Array = native.call("admission_begin", 1, dto)
	_expect(denied == PackedInt64Array([0,2]), "unlaunched reservation blocks competing claim")
	_expect(native.call("admission_event", id, 1, 1) == 0, "actual launch acknowledged")
	_expect(native.call("admission_event", id, 1, 7) == 0, "cancel request acknowledged")
	var before: Dictionary = native.call("admission_snapshot")
	_expect(int(before.loading) == 1 and int(before.cancelled) == 1, "cancel preserves actual live-worker accounting")
	_expect(native.call("reset_epoch", 2) == 0, "core session reset succeeds")
	var after: Dictionary = native.call("admission_snapshot")
	_expect(int(after.loading) == 1 and int(after.old_epoch) == 1, "old lease survives session reset")
	_expect(native.call("admission_event", id, 1, 2) == 0, "old worker's actual join remains valid")
	_expect(native.call("admission_event", id, 1, 3) != 0, "old completion cannot install into current epoch")
	_expect(native.call("admission_event", id, 1, 4) == 0, "old raw result can enter retirement")
	_expect(native.call("admission_event", id, 1, 5) == 0, "actual release clears old lease")
	dependency_snapshot = native.call("admission_graph_snapshot")
	_expect(int(dependency_snapshot.resources) == 3 and int(dependency_snapshot.retiring) == 3,
		"root release does not falsely acknowledge surviving cache/shared Resources")
	var not_released: PackedInt64Array = native.call("admission_release_dependencies", image_key)
	_expect(not_released.is_empty(), "an incoming retained prototype reference prevents premature image release")
	var all_keys := root_key.duplicate()
	all_keys.append_array(mesh_key)
	all_keys.append_array(image_key)
	var released: PackedInt64Array = native.call("admission_release_dependencies", all_keys)
	dependency_snapshot = native.call("admission_graph_snapshot")
	_expect(released.size() == 12 and int(dependency_snapshot.resources) == 0 \
		and int(dependency_snapshot.physical_releases) == 3,
		"actual physical-liveness acknowledgement releases dependents before dependencies")
	var forced: PackedInt64Array = native.call("admission_begin", 2,
		PackedInt64Array([500,500,1,2,1,3,20,1,1,1]))
	_expect(forced.size() == 2 and forced[0] > 0, "mandatory synchronous arrival preserves ground over soft limits")
	if forced.size() == 2:
		_expect(native.call("admission_event", forced[0], 2, 6) == 0, "failed unlaunched claim releases reservation")
	native.call("admission_event", 0, 2, 99) # Deliberate integer error, no engine diagnostic.
	var status: int = native.call("get_last_status")
	var thread := Thread.new()
	var error := thread.start(_foreign.bind(native, dto))
	_expect(error == OK, "foreign-thread guard fixture starts")
	if error == OK:
		for _frame: int in 120:
			if not thread.is_alive(): break
			await process_frame
		if thread.is_alive():
			push_error("native admission foreign guard timed out; focused runner must terminate its owned process")
			return
		var foreign: Variant = thread.wait_to_finish()
		_expect(foreign is PackedInt64Array and foreign.is_empty()
			and native.call("get_last_status") == status, "foreign call neither admits nor mutates owner status")
	var final: Dictionary = native.call("admission_snapshot")
	_expect(int(final.reserved) + int(final.loading) + int(final.ready) + int(final.active) + int(final.retiring) == 0,
		"no owned reservation disappears or remains")
	_expect(int(final.forced_sync) == 1, "mandatory overrun is reported explicitly")
	controller.close()
	native = null
	if previous.is_empty(): OS.unset_environment("RABBITLANDS_CLIENT_RUNTIME")
	else: OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", previous)
	print("native resource admission tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

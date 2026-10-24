class_name ClientResourceResidency
extends RefCounted
## Bulk data planner bridge. The existing Godot loader/stream owns every
## Resource, worker, Node and retirement queue. Actions persist here until the
## engine owner acknowledges actual completion; cancellation is not release.
const LOAD := 1
const INSTALL := 2
const RETIRE := 3
const CANCEL_LOAD := 4
const RELEASE_READY := 5
const LOADED := 1
const LOAD_FAILED := 2
const RELEASED := 3
const INSTALLED := 4
const INSTALL_FAILED := 5
const UNKNOWN_CPU := 1
const UNKNOWN_GPU := 2
static var _current: WeakRef
var _controller: RefCounted
var _native: RefCounted
var _epoch := 1
var _catalog: Dictionary = {}
var _issued: Dictionary = {} # token -> action and cancellation bit, never Node.
var _closing := false
var _closed := false
var _failure := "not_initialized"

static func current() -> ClientResourceResidency:
	return _current.get_ref() as ClientResourceResidency if _current != null else null

static func _main() -> bool:
	return OS.get_thread_caller_id() == OS.get_main_thread_id()

static func _key(value: Variant) -> PackedInt64Array:
	if not value is String or value.length() != 64:
		return PackedInt64Array()
	var digest: String = value
	for index: int in digest.length():
		if not digest.substr(index, 1) in "0123456789abcdef":
			return PackedInt64Array()
	var bytes := digest.hex_decode()
	return PackedInt64Array([bytes.decode_s64(0), bytes.decode_s64(8), bytes.decode_s64(16), bytes.decode_s64(24)])

static func _digest(words: PackedInt64Array, offset: int) -> String:
	var bytes := PackedByteArray()
	bytes.resize(32)
	for index: int in 4:
		bytes.encode_s64(index * 8, words[offset + index])
	return bytes.hex_encode()

static func _token(action: Dictionary) -> String:
	return "%s|%d|%d" % [str(action.get("key", "")), int(action.get("generation", 0)), int(action.get("epoch", 0))]

func initialize(controller: RefCounted, entries: Array) -> bool:
	if not _main() or _native != null or _closed or controller == null \
			or not controller.has_method("native_runtime") or not controller.has_method("current_epoch"):
		return false
	var prior := current()
	if prior != null and prior != self and not prior._closed:
		_failure = "one_residency_authority_per_runtime"
		return false
	var native: Variant = controller.call("native_runtime")
	if not native is RefCounted:
		_failure = "optional_runtime_absent"
		return false
	for method: String in ["residency_catalog", "residency_reconcile", "residency_events",
			"residency_retry", "residency_step", "residency_snapshot", "get_last_status", "runtime_info"]:
		if not native.has_method(method):
			_failure = "optional_residency_capability_absent"
			return false
	var info: Variant = native.call("runtime_info")
	if not info is Dictionary or int(info.get("residency_schema", -1)) != 1:
		_failure = "residency_schema_mismatch"
		return false
	var records := PackedInt64Array()
	var dependencies := PackedInt64Array()
	var candidate: Dictionary = {}
	if entries.size() > 65536:
		return false
	for value: Variant in entries:
		if not value is Dictionary:
			return false
		var entry: Dictionary = value
		var key := _key(entry.get("key"))
		if key.is_empty() or candidate.has(str(entry.key)) or not entry.get("dependencies", []) is Array:
			return false
		var cpu: Variant = entry.get("cpu_bytes")
		var gpu: Variant = entry.get("gpu_bytes")
		if (cpu != null and (not cpu is int or int(cpu) < 0)) \
				or (gpu != null and (not gpu is int or int(gpu) < 0)):
			return false
		var flags := (UNKNOWN_CPU if cpu == null else 0) | (UNKNOWN_GPU if gpu == null else 0)
		var start := dependencies.size() / 4
		for dependency: Variant in entry.get("dependencies", []):
			var dependency_key := _key(dependency)
			if dependency_key.is_empty():
				return false
			dependencies.append_array(dependency_key)
		if dependencies.size() / 4 > 262144:
			return false
		records.append_array(key)
		records.append_array(PackedInt64Array([int(cpu) if cpu != null else 0,
			int(gpu) if gpu != null else 0, flags, int(start), entry.get("dependencies", []).size()]))
		candidate[str(entry.key)] = {"key": str(entry.key), "dependencies": entry.get("dependencies", []).duplicate(),
			"cpu_bytes": cpu, "gpu_bytes": gpu, "unknown_flags": flags}
	var status: Variant = native.call("residency_catalog", records, dependencies)
	if not status is int or int(status) != 0:
		_failure = "catalog_rejected"
		return false
	_controller = controller
	_native = native
	_epoch = int(controller.call("current_epoch"))
	_catalog = candidate
	_failure = ""
	_current = weakref(self)
	return true

func _sync_epoch() -> bool:
	if not _main() or _native == null or _controller == null or _closed:
		return false
	if _controller.call("native_runtime") != _native:
		_failure = "runtime_replaced_before_drain"
		return false
	_epoch = int(_controller.call("current_epoch"))
	return _epoch > 0

func reconcile(wanted: Array) -> bool:
	if not _sync_epoch() or (_closing and not wanted.is_empty()) or not _failure.is_empty():
		return false
	var records := PackedInt64Array()
	var seen: Dictionary = {}
	for value: Variant in wanted:
		if not value is Dictionary:
			return false
		var row: Dictionary = value
		var name := str(row.get("key", ""))
		if not _catalog.has(name) or seen.has(name) or not row.get("priority", 0) is int \
				or not row.get("pinned", false) is bool:
			return false
		seen[name] = true
		records.append_array(_key(name))
		records.append_array(PackedInt64Array([int(row.get("priority", 0)), 1 if bool(row.get("pinned", false)) else 0]))
	var status: Variant = _native.call("residency_reconcile", records, _epoch)
	return status is int and int(status) == 0

func next_actions(cpu_bytes: int, gpu_bytes: int, in_flight: int,
		unknown_resources: int, capacity := 32) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not _sync_epoch() or (not _failure.is_empty() and not _closing) or mini(cpu_bytes, gpu_bytes) < 0 \
			or in_flight <= 0 or unknown_resources < 0 or capacity < 0 or capacity > 4096:
		return result
	var words: Variant = _native.call("residency_step", _epoch,
		PackedInt64Array([cpu_bytes, gpu_bytes, in_flight, unknown_resources]), capacity)
	var status: Variant = _native.call("get_last_status")
	if not status is int or int(status) != 0 or not words is PackedInt64Array \
			or words.size() % 8 != 0 or words.size() / 8 > capacity:
		_failure = "planner_output_rejected"
		return result
	var seen: Dictionary = {}
	for offset: int in range(0, words.size(), 8):
		var name := _digest(words, offset)
		var generation := int(words[offset + 4])
		var epoch := int(words[offset + 5])
		var kind := int(words[offset + 6])
		var pinned := int(words[offset + 7])
		if not _catalog.has(name) or seen.has(name) or generation <= 0 or epoch <= 0 \
				or kind not in [LOAD, INSTALL, RETIRE, CANCEL_LOAD, RELEASE_READY] or pinned not in [0, 1] \
				or (kind in [LOAD, INSTALL] and epoch != _epoch):
			_failure = "planner_action_identity_rejected"
			return []
		seen[name] = true
		var action := {"key": name, "generation": generation, "epoch": epoch,
			"kind": kind, "pinned": pinned == 1}
		var token := _token(action)
		if kind == CANCEL_LOAD:
			if not _issued.has(token) or int(_issued[token].kind) != LOAD:
				_failure = "cancellation_without_owned_job"
				return []
		elif _issued.has(token):
			_failure = "duplicate_outstanding_action"
			return []
		result.append(action)
	# Publish all handles before returning any action to callback-capable code.
	for action: Dictionary in result:
		var token := _token(action)
		if int(action.kind) == CANCEL_LOAD:
			_issued[token]["cancel_requested"] = true
		else:
			_issued[token] = action.duplicate()
	return result

func complete(action: Dictionary, event: int) -> bool:
	# Completion is still allowed after a local planning failure so an engine
	# owner can finish/release jobs already accepted. Never discard that ledger.
	if not _sync_epoch():
		return false
	if not action.get("key") is String or not action.get("generation") is int or not action.get("epoch") is int:
		return false
	var token := _token(action)
	if not _issued.has(token):
		return false
	var issued: Dictionary = _issued[token]
	var kind := int(issued.kind)
	var allowed := (kind == LOAD and event in [LOADED, LOAD_FAILED]) \
		or (kind == INSTALL and event in [INSTALLED, INSTALL_FAILED]) \
		or (kind in [RETIRE, RELEASE_READY] and event == RELEASED)
	if not allowed:
		return false
	var words := _key(str(issued.key))
	words.append_array(PackedInt64Array([int(issued.generation), int(issued.epoch), event]))
	var status: Variant = _native.call("residency_events", words)
	if not status is int or int(status) != 0:
		_failure = "completion_rejected_owned_job_retained"
		return false
	_issued.erase(token)
	return true

func retry_failed(keys: PackedStringArray) -> bool:
	if not _sync_epoch() or _closing or not _failure.is_empty():
		return false
	var records := PackedInt64Array()
	for name: String in keys:
		if not _catalog.has(name):
			return false
		records.append_array(_key(name))
	var status: Variant = _native.call("residency_retry", records, _epoch)
	return status is int and int(status) == 0

func request_close() -> bool:
	if not _sync_epoch():
		return false
	_closing = true
	# Keep issuing actual cancellation/retirement work until idle, using the
	# same Godot queues and shared retirement allowance as normal streaming.
	var status: Variant = _native.call("residency_reconcile", PackedInt64Array(), _epoch)
	return status is int and int(status) == 0

func finish_close() -> bool:
	if not _main() or not _closing or not _issued.is_empty() or _native == null:
		return false
	var native: Variant = _native.call("residency_snapshot", PackedInt64Array([0, 0, 1, 0]))
	if not native is Dictionary:
		return false
	for name: String in ["loading", "ready", "active", "retiring"]:
		if int(native.get(name, -1)) != 0:
			return false
	_closed = true
	_native = null
	_controller = null
	_catalog.clear()
	return true

func outstanding() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not _main():
		return result
	for value: Dictionary in _issued.values():
		result.append(value.duplicate())
	return result

func snapshot(limits := PackedInt64Array([0, 0, 1, 0])) -> Dictionary:
	if not _main():
		return {"failure": "foreign_thread_snapshot"}
	return {"schema": 1, "epoch": _epoch, "issued": _issued.size(), "closing": _closing,
		"closed": _closed, "failure": _failure,
		"native": _native.call("residency_snapshot", limits) if _native != null and _main() else {},
		"execution_clock": "existing_godot_retirement_allowance", "verification_reuse": false}

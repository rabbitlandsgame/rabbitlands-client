class_name ClientResourceAdmission
extends RefCounted
## One main-thread admission owner for real chunk/exterior loader launches.
## Streams keep workers, Resources, Nodes and queues; the shared retirement
## allowance remains the only destruction clock. Defaults to legacy.
const Controller := preload("res://src/runtime/client_runtime.gd")
const DependencyGraph := preload("res://src/runtime/resource_dependency_graph.gd")
const ResidencyWords := preload("res://src/runtime/resource_residency.gd")
const TOKEN := &"rl_resource_admission_token"
const TREE_OWNER := &"rl_client_resource_admission_owner"
const DEFAULT_ESTIMATE_BUDGET := 805306368
const MAX_WORKERS := 1
const UNKNOWN_LIMIT := 2048
const WAITER_LIFETIME_MSEC := 1500
const LAUNCHED := 1
const READY := 2
const INSTALLED := 3
const RETIRING := 4
const RELEASED := 5
const FAILED := 6
const CANCEL := 7
static var _current_ref: WeakRef
static var _request_mode := -1
static var _budget_bytes := -1
var _native: RefCounted
var _epoch := 1
var _reason := "native_not_ready"
var _broken := false
var _streams: Dictionary = {}
var _loaders: Dictionary = {}
var _cache_providers: Dictionary = {}
var _orphan_provider: Callable
var _cost: Callable
var _leases: Dictionary = {}
var _waiters: Dictionary = {}
var _next_order := 0
var _snapshot_frame := -1
var _captured: Dictionary = {}
var _tree: SceneTree
var _admitted := 0
var _denied := 0
var _transition_failures := 0
var _publish_frame := -1
var _publication_grants := 0
var _publication_deferrals := 0
var _dependencies: Dictionary = {}
var _carrier_groups: Dictionary = {}
var _graph_failures: Dictionary = {}
var _graph_registrations := 0
var _graph_verify_total_us := 0
var _graph_verify_largest_atomic_us := 0
var _graph_carrier_total_us := 0
var _graph_carrier_largest_atomic_us := 0

static func _main() -> bool:
	return OS.get_thread_caller_id() == OS.get_main_thread_id()

static func requested() -> bool:
	if not _main():
		return false
	if _request_mode >= 0:
		return _request_mode == 1
	var value := OS.get_environment("RABBITLANDS_RESOURCE_ADMISSION").strip_edges().to_lower()
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--resource-admission="):
			value = argument.trim_prefix("--resource-admission=")
	_request_mode = 1 if value == "rust" else 0
	return _request_mode == 1

static func current() -> ClientResourceAdmission:
	if not _main():
		return null
	return _current_ref.get_ref() as ClientResourceAdmission if _current_ref != null else null

static func estimate_budget() -> int:
	if not _main():
		return 0
	if _budget_bytes >= 0:
		return _budget_bytes
	var value := OS.get_environment("RABBITLANDS_RESOURCE_BUDGET_MIB").strip_edges()
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--resource-admission-budget-mib="):
			value = argument.trim_prefix("--resource-admission-budget-mib=")
	_budget_bytes = DEFAULT_ESTIMATE_BUDGET
	if not value.is_empty():
		_budget_bytes = int(value) * 1048576 if value.is_valid_int() and int(value) >= 64 and int(value) <= 8192 else 0
	return _budget_bytes

static func _ensure() -> ClientResourceAdmission:
	if not _main() or not requested():
		return null
	var known := current()
	if known != null:
		return known
	var owner := ClientResourceAdmission.new()
	owner._tree = Engine.get_main_loop() as SceneTree
	if owner._tree == null:
		return null
	_current_ref = weakref(owner)
	# A standard Callable holds only ObjectID. Tree metadata, not the
	# signal connection, owns this RefCounted until SceneTree destruction.
	owner._tree.set_meta(TREE_OWNER, owner)
	owner._tree.process_frame.connect(owner._tick)
	return owner

static func register_stream(stream: Node, family: String, cost := Callable(), orphan := Callable()) -> void:
	var owner := _ensure()
	if owner == null:
		return
	owner._streams[stream.get_instance_id()] = {"reference": weakref(stream), "family": family}
	if cost.is_valid():
		owner._cost = cost
	if orphan.is_valid():
		owner._orphan_provider = orphan
	owner._snapshot_frame = -1

static func register_loader(loader: Node, caches: Dictionary) -> void:
	var owner := _ensure()
	if owner == null:
		return
	owner._loaders[loader.get_instance_id()] = weakref(loader)
	owner._cache_providers.merge(caches, true)
	owner._snapshot_frame = -1

static func register_actor_provider(provider: Callable) -> void:
	var owner := _ensure()
	if owner != null and provider.is_valid():
		owner._cache_providers["actor_bodies"] = provider
		owner._snapshot_frame = -1

func _bind() -> bool:
	var controller := Controller.current()
	if controller == null:
		_reason = "controller_absent"
		return false
	var candidate := controller.native_runtime()
	if candidate == null or not candidate.has_method("admission_begin") \
			or not candidate.has_method("admission_event") or not candidate.has_method("admission_snapshot") \
			or not candidate.has_method("admission_dependencies") or not candidate.has_method("admission_release_dependencies") \
			or not candidate.has_method("admission_graph_snapshot"):
		_reason = "optional_admission_api_absent"
		return false
	if candidate != _native:
		_native = candidate
		_broken = false
	_epoch = controller.current_epoch()
	if _broken:
		return false
	_reason = "rust_global_admission"
	return true

func _tick() -> void:
	if not _main():
		return
	for key: String in _leases.keys():
		var lease: Dictionary = _leases[key]
		if bool(lease.get("watch_root", false)):
			var reference := lease.get("root") as WeakRef
			if reference == null or reference.get_ref() == null:
				_event(key, RELEASED)
	_prune_dependencies()
	_prune_waiters()
	_snapshot_frame = -1

func _graph_failure(reason: String) -> void:
	_graph_failures[reason] = int(_graph_failures.get(reason, 0)) + 1
	# Keep all accepted workers/leases and real queues drainable. Subsequent
	# launches use legacy until a fresh native controller is established.
	_broken = true
	_reason = "dependency_graph_rejected_legacy_fallback"

func _bind_dependencies(key: String, manifest: WorldManifest) -> void:
	var lease: Dictionary = _leases[key]
	var began := Time.get_ticks_usec()
	var graph := DependencyGraph.describe(manifest)
	var elapsed := Time.get_ticks_usec() - began
	_graph_verify_total_us += elapsed
	_graph_verify_largest_atomic_us = maxi(_graph_verify_largest_atomic_us, elapsed)
	if not bool(graph.get("complete", false)):
		if lease.has("dependency_keys"):
			lease["joined_identity_valid"] = false
		_graph_failure(str(graph.get("reason", "dependency_graph_incomplete")))
		return
	var signature := JSON.stringify(graph.nodes, "", true, true).sha256_text()
	if lease.has("dependency_keys"):
		if str(lease.get("dependency_signature", "")) != signature:
			lease["joined_identity_valid"] = false
			_graph_failure("joined_dependency_identity_changed")
		return
	var records := PackedInt64Array()
	var edges := PackedInt64Array()
	var keys: Array[String] = []
	for row: Dictionary in graph.nodes:
		var words := ResidencyWords._key(str(row.key))
		var start := edges.size() / 4
		for dependency: String in row.dependencies:
			edges.append_array(ResidencyWords._key(dependency))
		words.append_array(PackedInt64Array([0, 0, 3, int(start), row.dependencies.size()]))
		records.append_array(words)
		keys.append(str(row.key))
	var native := lease.native as RefCounted
	var status: Variant = native.call("admission_dependencies", int(lease.id), int(lease.epoch), records, edges)
	if not status is int or status != 0:
		_graph_failure("native_dependency_catalog_rejected")
		return
	for row: Dictionary in graph.nodes:
		var identity := "%d|%s" % [native.get_instance_id(), str(row.key)]
		if not _dependencies.has(identity):
			_dependencies[identity] = {"key": str(row.key), "native": native,
				"record": row.duplicate(true), "groups": {}}
	lease["dependency_keys"] = keys
	lease["dependency_root"] = str(graph.root)
	lease["dependency_coverage"] = str(graph.coverage)
	lease["dependency_signature"] = signature
	_graph_registrations += 1

func _retain_dependency_carriers(lease: Dictionary, imported: Node) -> void:
	if not lease.has("dependency_keys"):
		return
	var began := Time.get_ticks_usec()
	var carriers := DependencyGraph.carriers(imported)
	var elapsed := Time.get_ticks_usec() - began
	_graph_carrier_total_us += elapsed
	_graph_carrier_largest_atomic_us = maxi(_graph_carrier_largest_atomic_us, elapsed)
	if not bool(carriers.get("complete", false)):
		_graph_failure(str(carriers.get("reason", "resource_carrier_incomplete")))
	var group_id := imported.get_instance_id()
	if not _carrier_groups.has(group_id):
		var references: Dictionary = {}
		for reference: WeakRef in carriers.references:
			var resource: Variant = reference.get_ref()
			if resource != null:
				references[resource.get_instance_id()] = reference
		_carrier_groups[group_id] = {"root": weakref(imported), "references": references,
			"incomplete": not bool(carriers.get("complete", false))}
	# On incomplete enumeration retain the logical closure indefinitely. Honest
	# unknown retention is safer than acknowledging resources we did not see.
	for key: String in lease.dependency_keys:
		var identity := "%d|%s" % [(lease.native as RefCounted).get_instance_id(), key]
		var dependency: Dictionary = _dependencies[identity]
		dependency.groups[group_id] = true

func _retain_prepared_carriers(lease: Dictionary, prepared: Resource) -> void:
	if not lease.has("dependency_keys"):
		return
	var began := Time.get_ticks_usec()
	var carriers := DependencyGraph.resource_carriers(prepared)
	var elapsed := Time.get_ticks_usec() - began
	_graph_carrier_total_us += elapsed
	_graph_carrier_largest_atomic_us = maxi(_graph_carrier_largest_atomic_us, elapsed)
	if not bool(carriers.get("complete", false)):
		_graph_failure(str(carriers.get("reason", "prepared_resource_carrier_incomplete")))
	var group_id := prepared.get_instance_id()
	if not _carrier_groups.has(group_id):
		var references: Dictionary = {}
		for reference: WeakRef in carriers.references:
			var resource: Variant = reference.get_ref()
			if resource != null:
				references[resource.get_instance_id()] = reference
		_carrier_groups[group_id] = {"root": weakref(prepared), "references": references,
			"resource_only": true, "incomplete": not bool(carriers.get("complete", false))}
	for key: String in lease.dependency_keys:
		var identity := "%d|%s" % [(lease.native as RefCounted).get_instance_id(), key]
		var dependency: Dictionary = _dependencies[identity]
		dependency.groups[group_id] = true

func _prune_dependencies() -> void:
	# One carrier table per resident, shared by all logical dependencies. Do
	# not multiply a full Resource weakref table by every image/prototype key.
	for group_id: int in _carrier_groups.keys():
		var group: Dictionary = _carrier_groups[group_id]
		if (group.root as WeakRef).get_ref() != null:
			continue # A live root already prevents any dependency release.
		for id: int in group.references.keys():
			if (group.references[id] as WeakRef).get_ref() == null:
				group.references.erase(id)
		if not bool(group.incomplete) and (group.root as WeakRef).get_ref() == null and group.references.is_empty():
			_carrier_groups.erase(group_id)
	var by_native: Dictionary = {}
	var requested: Dictionary = {}
	for identity: String in _dependencies:
		var dependency: Dictionary = _dependencies[identity]
		for group_id: int in dependency.groups.keys():
			if not _carrier_groups.has(group_id):
				dependency.groups.erase(group_id)
		if not dependency.groups.is_empty():
			continue
		var native := dependency.native as RefCounted
		var native_id := native.get_instance_id()
		if not by_native.has(native_id):
			by_native[native_id] = {"native": native, "words": PackedInt64Array()}
		var words: PackedInt64Array = by_native[native_id].words
		words.append_array(ResidencyWords._key(str(dependency.key)))
		by_native[native_id]["words"] = words
		requested[identity] = true
	for batch: Dictionary in by_native.values():
		var native := batch.native as RefCounted
		var removed: Variant = native.call("admission_release_dependencies", batch.words)
		var status: Variant = native.call("get_last_status")
		if not status is int or status != 0 or not removed is PackedInt64Array or removed.size() % 4 != 0:
			_graph_failure("dependency_physical_release_rejected")
			continue
		var accepted: Array[String] = []
		for offset: int in range(0, removed.size(), 4):
			var identity := "%d|%s" % [native.get_instance_id(), ResidencyWords._digest(removed, offset)]
			if not requested.has(identity) or identity in accepted:
				_graph_failure("dependency_release_output_rejected")
				accepted.clear()
				break
			accepted.append(identity)
		for identity: String in accepted:
			_dependencies.erase(identity)

func _prune_waiters() -> void:
	var now := Time.get_ticks_msec()
	for key: String in _waiters.keys():
		var row: Dictionary = _waiters[key]
		var stream: Variant = (row.reference as WeakRef).get_ref()
		if not is_instance_valid(stream) or stream.is_queued_for_deletion() \
				or not stream.is_inside_tree() or now - int(row.renewed) > WAITER_LIFETIME_MSEC:
			_waiters.erase(key)

func _first_waiter() -> String:
	_prune_waiters()
	var first := ""
	for key: String in _waiters:
		var row: Dictionary = _waiters[key]
		if first.is_empty() or (bool(row.pinned) and not bool(_waiters[first].pinned)) \
				or (bool(row.pinned) == bool(_waiters[first].pinned) and int(row.order) < int(_waiters[first].order)):
			first = key
	return first

func _root(imported: Variant, shared: Dictionary, seen: Dictionary, result: Dictionary) -> void:
	if not is_instance_valid(imported) or not imported is Node3D or seen.has(imported.get_instance_id()):
		return
	seen[imported.get_instance_id()] = true
	if imported.has_method("resource_estimates"):
		var row: Dictionary = imported.call("resource_estimates", shared)
		result.estimated_bytes += int(row.get("total_estimated_bytes", 0))
		result.active_chunks += int(row.get("active_cells", 0))
		result.retiring_roots += int(row.get("retiring_cells", 0))
		result.live_workers += int(row.get("in_flight_cells", 0))
		# The stream's estimate already owns these actual roots. A native lease
		# below must not count the same cell again as an unknown whole map.
		for resident: Dictionary in imported.cells.values():
			if is_instance_valid(resident.get("root")):
				seen[resident.root.get_instance_id()] = true
		for retired: Dictionary in imported._retiring:
			if is_instance_valid(retired.get("root")):
				seen[retired.root.get_instance_id()] = true
	else:
		result.unknown_whole_map_roots += 1

func _capture() -> Dictionary:
	var frame := Engine.get_process_frames()
	if _snapshot_frame == frame:
		return _captured
	var shared: Dictionary = {}
	var seen: Dictionary = {}
	var result := {"estimated_bytes": 0, "active_chunks": 0, "retiring_roots": 0, "live_workers": 0,
		"unknown_whole_map_roots": 0, "unknown_outer_workers": 0, "unknown_cache_entries": 0,
		"actor_caches": {}, "estimate_kind": "manifest_estimate_not_measured_cpu_or_gpu_allocation"}
	for identity: int in _streams.keys():
		var registered: Dictionary = _streams[identity]
		var stream: Variant = (registered.reference as WeakRef).get_ref()
		if not is_instance_valid(stream):
			_streams.erase(identity)
			continue
		if str(registered.family) == "exterior":
			_root(stream.active_root, shared, seen, result)
			for resident: Dictionary in stream.residents.values():
				_root(resident.get("root"), shared, seen, result)
			for retired: Dictionary in stream._retiring:
				_root(retired.resident.get("root"), shared, seen, result)
				result.retiring_roots += 1
			if stream._thread != null:
				result.live_workers += 1
				result.unknown_outer_workers += 1
	# Exterior roots first deduplicate their nested chunk streams and whole maps.
	for registered: Dictionary in _streams.values():
		if str(registered.family) == "chunk":
			_root((registered.reference as WeakRef).get_ref(), shared, seen, result)
	for identity: int in _loaders.keys():
		var loader: Variant = (_loaders[identity] as WeakRef).get_ref()
		if not is_instance_valid(loader):
			_loaders.erase(identity)
		else:
			_root(loader.world_root, shared, seen, result)
	if _orphan_provider.is_valid():
		var orphan: Dictionary = _orphan_provider.call(shared)
		result.live_workers += int(orphan.get("workers", 0))
		result.estimated_bytes += int(orphan.get("estimated_bytes", 0))
		result.unknown_outer_workers += int(orphan.get("unknown_worker_bytes", 0))
	# An unexpected owner exit hands a worker to the existing global reaper.
	# After joining, its queued raw root still occupies memory until actually
	# freed. Retain it here even though its original stream no longer exists.
	for lease: Dictionary in _leases.values():
		var reference := lease.get("root") as WeakRef
		var imported: Variant = reference.get_ref() if reference != null else null
		if not is_instance_valid(imported) or seen.has(imported.get_instance_id()):
			continue
		if str(lease.family) == "chunk" and not imported.has_method("resource_estimates") and _cost.is_valid():
			result.estimated_bytes += int(_cost.call(lease.entry, shared))
			seen[imported.get_instance_id()] = true
		else:
			_root(imported, shared, seen, result)
		result.retiring_roots += 1
	for name: String in _cache_providers:
		var provider: Callable = _cache_providers[name]
		if not provider.is_valid():
			continue
		var row: Dictionary = provider.call()
		result.actor_caches[name] = row
		for field: String in ["strong_scene_entries", "strong_library_entries", "strong_source_scenes", "prewarming_sources", "active_actor_nodes", "parked_actor_nodes"]:
			result.unknown_cache_entries += int(row.get(field, 0))
	result["unknown_resources"] = int(result.unknown_whole_map_roots) + int(result.unknown_outer_workers) + int(result.unknown_cache_entries)
	result["_shared"] = shared
	_captured = result
	_snapshot_frame = frame
	return result

static func request(stream: Node, entry: Dictionary, family := "chunk", pinned := false, synchronous := false) -> Dictionary:
	var owner := _ensure()
	if owner == null or not owner._bind():
		return {"allowed": true, "token": {}, "mode": "legacy"}
	return owner._request(stream, entry, family, pinned, synchronous)

func _request(stream: Node, entry: Dictionary, family: String, pinned: bool, synchronous: bool) -> Dictionary:
	if not _main() or not is_instance_valid(stream):
		return {"allowed": false, "reason": "invalid_owner"}
	var waiter := "%d|%s|%s" % [stream.get_instance_id(), family, str(entry.get("path", entry.get("id", "")))]
	if not _waiters.has(waiter):
		_next_order += 1
		_waiters[waiter] = {"reference": weakref(stream), "order": _next_order}
	_waiters[waiter]["pinned"] = pinned
	_waiters[waiter]["renewed"] = Time.get_ticks_msec()
	if not synchronous and _first_waiter() != waiter:
		_denied += 1
		return {"allowed": false, "reason": "global_fifo_turn"}
	var snapshot := _capture()
	var budget := estimate_budget()
	if budget <= 0:
		_broken = true
		_reason = "invalid_residency_budget_legacy_fallback"
		return {"allowed": true, "token": {}, "mode": "legacy"}
	var incremental := 0
	if family == "chunk" and _cost.is_valid():
		incremental = int(_cost.call(entry, (snapshot._shared as Dictionary).duplicate()))
	var unknown := int(snapshot.unknown_resources) + (1 if family == "exterior" else 0)
	var output: Variant = _native.call("admission_begin", _epoch, PackedInt64Array([
		int(snapshot.estimated_bytes), incremental, budget,
		int(snapshot.live_workers), MAX_WORKERS, int(snapshot.retiring_roots), unknown, UNKNOWN_LIMIT,
		1 if pinned else 0, 1 if synchronous else 0]))
	var status: Variant = _native.call("get_last_status")
	if not status is int or status != 0 or not output is PackedInt64Array or output.size() != 2 \
			or int(output[0]) < 0 or int(output[1]) not in [0, 1, 2, 3, 4] \
			or (int(output[0]) > 0 and int(output[1]) != 0) or (int(output[0]) == 0 and int(output[1]) == 0):
		_broken = true
		_reason = "native_admission_output_rejected_legacy_fallback"
		return {"allowed": true, "token": {}, "mode": "legacy"}
	if int(output[0]) == 0:
		_denied += 1
		return {"allowed": false, "reason": "native_budget_%d" % int(output[1])}
	var key := "%d|%d" % [_native.get_instance_id(), int(output[0])]
	var token := {"key": key, "id": int(output[0]), "epoch": _epoch}
	_leases[key] = {"id": int(output[0]), "epoch": _epoch, "native": _native, "state": "reserved",
		"owner": weakref(stream), "family": family, "entry": entry.duplicate(),
		"source": str(entry.get("path", "")), "watch_root": false, "cancel_requested": false}
	# Register the actual source closure before launch. Join verifies the same
	# identity against the actual builder's manifest before READY/install.
	_bind_dependencies(key, WorldManifest.load_file(str(entry.get("path", ""))))
	_waiters.erase(waiter)
	_admitted += 1
	_snapshot_frame = -1
	return {"allowed": true, "token": token, "mode": "rust"}

func _event(key: String, event: int) -> bool:
	if not _leases.has(key):
		return false
	var lease: Dictionary = _leases[key]
	var native := lease.native as RefCounted
	var status: Variant = native.call("admission_event", int(lease.id), int(lease.epoch), event)
	if not status is int or status != 0:
		_transition_failures += 1
		if event != INSTALLED: # Old epoch installation rejection is expected.
			_broken = true
			_reason = "owned_admission_event_rejected"
		return false
	if event == CANCEL:
		lease["cancel_requested"] = true
	if event in [RELEASED, FAILED]:
		_leases.erase(key)
	else:
		lease.state = {LAUNCHED: "loading", READY: "ready", INSTALLED: "active", RETIRING: "retiring", CANCEL: "cancelled"}.get(event, lease.state)
	_snapshot_frame = -1
	return true

static func event(token: Dictionary, value: int) -> void:
	if not _main():
		return
	var owner := current()
	if _main() and owner != null and not token.is_empty():
		owner._event(str(token.get("key", "")), value)

static func ready(token: Dictionary, manifest: WorldManifest = null) -> void:
	if not _main():
		return
	var owner := current()
	var key := str(token.get("key", ""))
	if _main() and owner != null and owner._leases.has(key) and owner._leases[key].state in ["loading", "cancelled"]:
		if manifest != null:
			owner._bind_dependencies(key, manifest)
		owner._event(key, READY)

static func can_install(token: Dictionary) -> bool:
	if token.is_empty():
		return true # Unchanged legacy path has no native ownership token.
	if not _main():
		return false
	var owner := current()
	var key := str(token.get("key", ""))
	var controller := Controller.current()
	if owner == null or not owner._leases.has(key) or controller == null:
		return false
	var lease: Dictionary = owner._leases[key]
	return not bool(lease.get("cancel_requested", false)) \
		and bool(lease.get("joined_identity_valid", true)) \
		and controller.native_runtime() == lease.native \
		and controller.current_epoch() == int(lease.epoch)

static func retain_prepared(token: Dictionary, prepared: Resource) -> void:
	if not _main() or prepared == null:
		return
	var owner := current()
	var key := str(token.get("key", ""))
	if owner != null and owner._leases.has(key):
		owner._retain_prepared_carriers(owner._leases[key], prepared)

static func hold(token: Dictionary, imported: Node3D, installed := true) -> void:
	if not _main():
		return
	var owner := current()
	var key := str(token.get("key", ""))
	if not _main() or owner == null or not owner._leases.has(key):
		return
	if imported == null:
		owner._event(key, RELEASED)
		return
	imported.set_meta(TOKEN, token)
	owner._leases[key]["root"] = weakref(imported)
	owner._leases[key]["watch_root"] = true
	owner._retain_dependency_carriers(owner._leases[key], imported)
	owner._event(key, INSTALLED if installed else RETIRING)

static func retiring(imported: Node) -> void:
	if not _main() or not is_instance_valid(imported):
		return
	if imported.has_meta(TOKEN):
		event(imported.get_meta(TOKEN), RETIRING)
	# An exterior owner keeps a whole chunk stream's existing queues. Its
	# child leases become retiring too; no cells are moved or freed here.
	if imported.has_method("resource_estimates"):
		var cells: Variant = imported.get("cells")
		if cells is Dictionary:
			for resident: Dictionary in cells.values():
				var child := resident.get("root") as Node
				if is_instance_valid(child) and child.has_meta(TOKEN):
					event(child.get_meta(TOKEN), RETIRING)

static func can_publish() -> bool:
	if not _main():
		return false
	# Keep a finished worker unjoined/owned until a main-frame turn is free.
	# This bounds the number of atomic installs, never claims to preempt one.
	var owner := _ensure()
	if owner == null or not owner._bind():
		return true
	var frame := Engine.get_process_frames()
	if owner._publish_frame == frame:
		owner._publication_deferrals += 1
		return false
	owner._publish_frame = frame
	owner._publication_grants += 1
	return true

static func snapshot() -> Dictionary:
	if not _main():
		return {"mode": "legacy", "reason": "foreign_thread_snapshot"}
	var owner := current()
	if not _main() or owner == null:
		return {"mode": "legacy", "requested": requested()}
	var result: Dictionary = owner._capture().duplicate(true)
	result.erase("_shared")
	result.merge({"mode": "rust" if owner._bind() else "legacy", "reason": owner._reason,
		"issued_leases": owner._leases.size(), "waiters": owner._waiters.size(),
		"admitted": owner._admitted, "denied": owner._denied, "transition_failures": owner._transition_failures,
		"publication_grants": owner._publication_grants, "publication_deferrals": owner._publication_deferrals,
		"publication_policy": "one_atomic_async_join_install_per_process_frame; mandatory_sync_preserved",
		"dependency_graph": owner._dependency_snapshot(),
		"unknown_cache_bytes": true, "cpu_gpu_split_known": false, "verification_reuse": false,
		"estimate_budget": estimate_budget(), "estimated_over_budget_bytes": maxi(0, int(result.estimated_bytes) - estimate_budget()),
		"unknown_entries_over_limit": maxi(0, int(result.unknown_resources) - UNKNOWN_LIMIT), "worker_limit": MAX_WORKERS,
		"native": owner._native.call("admission_snapshot") if owner._native != null else {}})
	return result

func _dependency_snapshot() -> Dictionary:
	var inventory: Array[Dictionary] = []
	var identities: Dictionary = {}
	var weak_carriers := 0
	var incomplete := 0
	for group: Dictionary in _carrier_groups.values():
		weak_carriers += group.references.size()
		incomplete += 1 if bool(group.incomplete) else 0
	for value: Dictionary in _dependencies.values():
		identities[str(value.record.key)] = value.record.duplicate(true)
		var row: Dictionary = value.record.duplicate(true)
		var resource_carriers := 0
		var root_carriers := 0
		for group_id: int in value.groups:
			if _carrier_groups.has(group_id):
				var group: Dictionary = _carrier_groups[group_id]
				resource_carriers += group.references.size()
				root_carriers += 1 if not bool(group.get("resource_only", false)) and (group.root as WeakRef).get_ref() != null else 0
		row["root_carriers"] = root_carriers
		row["resource_carriers"] = resource_carriers
		inventory.append(row)
	inventory.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.key) < str(b.key))
	var source_inventory: Array = identities.values()
	source_inventory.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.key) < str(b.key))
	return {"schema": 1, "coverage": "world-glb-embedded-images-and-transitive-external-prototype-images",
		"registrations": _graph_registrations, "resources": _dependencies.size(), "weak_carriers": weak_carriers,
		"carrier_groups": _carrier_groups.size(), "incomplete_retained_groups": incomplete,
		"incomplete_retained_resources": incomplete, "failures": _graph_failures.duplicate(),
		"inventory": inventory, "source_content_hash": JSON.stringify(source_inventory, "", true, true).sha256_text(),
		"native": _native.call("admission_graph_snapshot") if _native != null else {},
		"verification_total_us": _graph_verify_total_us, "verification_largest_atomic_us": _graph_verify_largest_atomic_us,
		"carrier_total_us": _graph_carrier_total_us, "carrier_largest_atomic_us": _graph_carrier_largest_atomic_us,
		"lifetime_policy": "conservative_whole_resident_resource_graph_weak_carriers",
		"allocation_kind": "unknown_cpu_gpu_allocation", "verification_reuse": false}

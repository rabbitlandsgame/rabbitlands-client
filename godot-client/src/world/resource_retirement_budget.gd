extends RefCounted
## Main-thread aggregate retirement allowance. Streams retain their own jobs.
## Weak owners take FIFO turns, at most once per process frame. Denied owners
## renew by retrying next frame; abandoned live owners expire after one missed
## frame. An indivisible free/upload can exceed a lease and is charged in full.
const FRAME_BUDGET_USEC := 2000
const FRAME_NODE_LIMIT := 64
const OWNER_GRACE_FRAMES := 1
static var _frame := -1
static var _spent_usec := 0
static var _freed_nodes := 0
static var _owners: Dictionary = {}
static var _waiters: Array[int] = []
static var _served: Dictionary = {}
static var _lease: Dictionary = {}
static var _next_ticket := 0
static var _slices := 0
static var _max_frame_usec := 0
static var _overrun_frames := 0
static var _abandoned_slices := 0
static var _invalid_ends := 0
static var _turn_denials := 0
static var _nested_denials := 0
static var _expired_owners := 0
static var _cancelled_owners := 0

static func _forget(identity: int) -> void:
	_owners.erase(identity)
	_waiters.erase(identity)

static func _prune_owners() -> void:
	for identity: int in _waiters.duplicate():
		var entry: Dictionary = _owners.get(identity, {})
		var reference := entry.get("reference") as WeakRef
		var owner: Variant = reference.get_ref() if reference != null else null
		if not is_instance_valid(owner) \
				or _frame - int(entry.get("last_request_frame", -1)) > OWNER_GRACE_FRAMES:
			_forget(identity)
			_expired_owners += 1

static func _advance_frame() -> void:
	var frame := Engine.get_process_frames()
	if frame != _frame:
		# Drainers are synchronous. A lease surviving a frame was abandoned;
		# its unreported cost is unknown, not a measured zero-cost operation.
		if not _lease.is_empty():
			var abandoned_owner := int(_lease.owner_id)
			# Recovery must yield the turn as well as the lock: a live caller
			# that retries and aborts cannot retain the head every frame.
			if _owners.has(abandoned_owner):
				_waiters.erase(abandoned_owner)
				_waiters.append(abandoned_owner)
			_abandoned_slices += 1
		_lease.clear()
		_frame = frame
		_spent_usec = 0
		_freed_nodes = 0
		_served.clear()
	_prune_owners()

static func _next_waiter() -> int:
	for identity: int in _waiters:
		if not _served.has(identity):
			return identity
	return 0

## Register even when denied: a later caller must retain its place next frame.
## The ticket/owner/frame fields are scalar copies, never strong owner refs.
static func begin_slice(owner: Node, max_nodes: int, budget_usec: int) -> Dictionary:
	_advance_frame()
	if not is_instance_valid(owner) or max_nodes <= 0 or budget_usec <= 0:
		return {}
	var identity := owner.get_instance_id()
	if not _owners.has(identity):
		_owners[identity] = {"reference": weakref(owner), "last_request_frame": _frame}
		_waiters.append(identity)
	else:
		(_owners[identity] as Dictionary)["last_request_frame"] = _frame
	# Destruction callbacks can request other owners, but cannot share a live
	# lease before its actual cost has been charged.
	if not _lease.is_empty():
		_nested_denials += 1
		return {}
	if _next_waiter() != identity:
		_turn_denials += 1
		return {}
	var nodes := mini(max_nodes, maxi(0, FRAME_NODE_LIMIT - _freed_nodes))
	var usec := mini(budget_usec, maxi(0, FRAME_BUDGET_USEC - _spent_usec))
	if nodes == 0 or usec == 0:
		return {}
	_next_ticket += 1
	_lease = {"ticket": _next_ticket, "owner_id": identity, "frame": _frame,
		"nodes": nodes, "usec": usec}
	_served[identity] = true
	return _lease.duplicate()

## A wrong/denied/stale caller cannot unlock another owner's lease. Charge
## reported work in full, even if it exceeds the issued allowance. Completing
## a zero-progress slice still yields the turn to another waiting owner.
static func end_slice(lease: Dictionary, freed_nodes: int, elapsed_usec: int,
		still_pending: bool) -> bool:
	_advance_frame()
	if _lease.is_empty() or int(lease.get("ticket", -1)) != int(_lease.ticket) \
			or int(lease.get("owner_id", -1)) != int(_lease.owner_id) \
			or int(lease.get("frame", -1)) != _frame:
		_invalid_ends += 1
		return false
	var identity := int(_lease.owner_id)
	var previous := _spent_usec
	_freed_nodes += maxi(0, freed_nodes)
	_spent_usec += maxi(0, elapsed_usec)
	_lease.clear()
	_slices += 1
	_max_frame_usec = maxi(_max_frame_usec, _spent_usec)
	if previous <= FRAME_BUDGET_USEC and _spent_usec > FRAME_BUDGET_USEC:
		_overrun_frames += 1
	_waiters.erase(identity)
	if still_pending and _owners.has(identity):
		_waiters.append(identity)
	else:
		_owners.erase(identity)
	return true

## Clearing/exiting a stream cancels its waiting slot, never its jobs. Keep an
## active lease locked until its matching end (or next-frame abandonment), so
## cancel inside a destructor cannot admit uncharged nested retirement work.
static func cancel(owner: Node) -> void:
	if not is_instance_valid(owner):
		return
	var identity := owner.get_instance_id()
	if _owners.has(identity):
		_forget(identity)
		_cancelled_owners += 1

static func diagnostic_snapshot() -> Dictionary:
	_advance_frame()
	return {"frame": _frame, "spent_us": _spent_usec, "freed_nodes": _freed_nodes,
		"frame_budget_us": FRAME_BUDGET_USEC, "frame_node_limit": FRAME_NODE_LIMIT,
		"slice_active": not _lease.is_empty(), "slices": _slices,
		"max_frame_us": _max_frame_usec, "overrun_frames": _overrun_frames,
		"abandoned_slices": _abandoned_slices, "abandoned_cost_known": false,
		"waiting_owners": _waiters.size(), "served_owners_this_frame": _served.size(),
		"invalid_ends": _invalid_ends, "turn_denials": _turn_denials,
		"nested_denials": _nested_denials, "expired_owners": _expired_owners,
		"cancelled_owners": _cancelled_owners, "owner_grace_frames": OWNER_GRACE_FRAMES}

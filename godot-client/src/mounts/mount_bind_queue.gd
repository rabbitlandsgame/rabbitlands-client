extends RefCounted
## Mount binds that Main makes outside the packet handler (avatar-worker AW-07).
##
## Binding a rider to a mount (ReplicatedActor3D.set_mount_state building a
## MountedPlayerVisual) reads the mount's glTF files through GlbSceneCache and
## builds the mount body. A first-seen species parsed those files inside the
## packet handler: 0.9-2.9 s on the development laptop (plan baseline). Main
## now asks the actor preparer for the mount's files
## (ActorAssetClosure.mount_closure) and keeps the rider here while:
##   * "files": its mount's files are being prepared on the worker (or, before
##     the process's first bind, the visual's script is loading on a
##     ResourceLoader thread). The rider is drawn as it is (on foot, or on the
##     mount it showed) meanwhile;
##   * "turn": its files are ready but the bind waits for Main's per-frame
##     actor work (`_bind_pending_mounts`, at most BINDS_PER_FRAME a frame),
##     so a burst of mount rows binds over several frames instead of in one
##     handler. A ready bind that has waited OVERDUE_MSEC is made even when
##     that frame's actor work is spent.
## It only holds ids, times and counters; Main decides from the actor's node
## and AppState each time it asks (`_apply_actor_mount`).
const BINDS_PER_FRAME := 1
const OVERDUE_MSEC := 1000
## The mount visual's script, which a bind loads (Main loads it on a
## ResourceLoader thread ahead of the first bind).
const VISUAL_SCRIPT := "res://src/mounts/mounted_player_visual.gd"

## actor id -> {"since": msec first kept, "reason": "files" | "turn"}.
var _pending: Dictionary = {}
var _bind_frame := -1
var _binds_in_frame := 0
var file_waits := 0
var turn_waits := 0
var bound := 0
var bound_at_once := 0
var overdue_binds := 0
var dropped := 0
var last_bind_usec := 0
var maximum_bind_usec := 0
var last_wait_msec := 0
var maximum_wait_msec := 0

## Keeps `id` (or updates why it waits). Counted once per wait and reason.
func keep(id: int, reason: String, now_msec: int) -> void:
	var row: Dictionary = _pending.get(id, {})
	if row.is_empty():
		_pending[id] = {"since": now_msec, "reason": reason}
		_count(reason)
		return
	if str(row.reason) != reason:
		row.reason = reason
		_count(reason)

func _count(reason: String) -> void:
	if reason == "files":
		file_waits += 1
	else:
		turn_waits += 1

func has(id: int) -> bool:
	return _pending.has(id)

func reason(id: int) -> String:
	return str((_pending.get(id, {}) as Dictionary).get("reason", ""))

func is_empty() -> bool:
	return _pending.is_empty()

## Kept ids, oldest first.
func ids() -> Array:
	var out: Array = _pending.keys()
	out.sort_custom(func(a: Variant, b: Variant) -> bool:
		var sa := int(_pending[a].since)
		var sb := int(_pending[b].since)
		return sa < sb or (sa == sb and int(a) < int(b)))
	return out

## Whether `id`'s bind has waited OVERDUE_MSEC.
func overdue(id: int, now_msec: int) -> bool:
	return _pending.has(id) and now_msec - int(_pending[id].since) >= OVERDUE_MSEC

## Whether another kept bind may be made in process frame `frame`.
func may_bind(frame: int) -> bool:
	if frame != _bind_frame:
		_bind_frame = frame
		_binds_in_frame = 0
	return _binds_in_frame < BINDS_PER_FRAME

## A kept bind was made (`usec` on main) in process frame `frame`.
func note_bound(id: int, usec: int, frame: int, now_msec: int, was_overdue := false) -> void:
	may_bind(frame)
	_binds_in_frame += 1
	bound += 1
	overdue_binds += int(was_overdue)
	last_bind_usec = usec
	maximum_bind_usec = maxi(maximum_bind_usec, usec)
	var row: Dictionary = _pending.get(id, {})
	if not row.is_empty():
		last_wait_msec = now_msec - int(row.since)
		maximum_wait_msec = maxi(maximum_wait_msec, last_wait_msec)
	_pending.erase(id)

## A bind made where it was asked for (a body's build, the player's own with
## its files ready, or a path that binds as before).
func note_at_once() -> void:
	bound_at_once += 1

## `id` no longer waits: its bind is made where it was asked for (a body's
## build, or a path that binds at once).
func release(id: int) -> void:
	_pending.erase(id)

## `id` no longer waits and needs no bind: dismounted, its mount already
## shown, or its actor or node gone.
func drop(id: int) -> void:
	if _pending.erase(id):
		dropped += 1

func clear() -> void:
	dropped += _pending.size()
	_pending.clear()

## Counts only (no ids), for the client diagnostics snapshot, with the
## per-process mount file reads (one per species once cached).
func snapshot(now_msec: int) -> Dictionary:
	var files := 0
	var oldest := 0
	for row: Dictionary in _pending.values():
		files += int(str(row.reason) == "files")
		oldest = maxi(oldest, now_msec - int(row.since))
	# The visual's script is loaded for the first bind; until then it has read nothing.
	# Never waits for a load in progress on a ResourceLoader thread.
	var loaded := ResourceLoader.has_cached(VISUAL_SCRIPT) \
		and ResourceLoader.load_threaded_get_status(VISUAL_SCRIPT) != ResourceLoader.THREAD_LOAD_IN_PROGRESS
	var map_reads: Variant = (load(VISUAL_SCRIPT) as Script).get("animation_map_reads") if loaded else 0
	return {"pending": _pending.size(), "waitingForFiles": files, "oldestMsec": oldest,
		"fileWaits": file_waits, "turnWaits": turn_waits, "bound": bound, "boundAtOnce": bound_at_once,
		"overdueBinds": overdue_binds, "dropped": dropped, "lastBindUsec": last_bind_usec,
		"maximumBindUsec": maximum_bind_usec, "lastWaitMsec": last_wait_msec,
		"maximumWaitMsec": maximum_wait_msec, "bindsPerFrame": BINDS_PER_FRAME,
		"profileFileReads": preload("res://src/mounts/mount_profiles.gd").file_reads,
		"animationMapReads": int(map_reads) if map_reads != null else 0}

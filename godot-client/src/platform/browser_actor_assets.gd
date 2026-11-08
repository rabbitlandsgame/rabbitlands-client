extends RefCounted
## Admit visible bodies only after their public source files are available.
## Keep the displayed outfit pinned while its replacement is downloading.
var service: Variant
var _actors: Dictionary = {}
var _pending: Dictionary = {}
var _next_poll := 0
var _active_groups: Dictionary = {}
var _retired: Array[String] = []
var _next_retired := 0
var _owner_prefix := "actor"

func _init(provider: Variant, owner_prefix := "actor") -> void:
	service = provider
	_owner_prefix = owner_prefix

func _owner(id: int, pending: bool) -> String:
	return "%s_%s:%d" % [_owner_prefix, "pending" if pending else "active", id]

func admit(id: int, model: String, equipment: Dictionary, mount := "", high_priority := false,
		extra_groups: Array = [], selection_key: Array = []) -> bool:
	var row: Dictionary = _actors.get(id, {})
	if row.is_empty() or row.model != model or row.equipment != equipment or row.mount != mount \
			or row.extra_groups != extra_groups or row.selection_key != selection_key:
		var groups: Array = service.model_groups(model).duplicate()
		groups.append_array(service.equipment_groups(equipment))
		if not mount.is_empty(): groups.append_array(service.mount_groups(mount))
		groups.append_array(extra_groups)
		# Catalog dependencies handle shared files; duplicate group IDs need no
		# second request or ownership entry.
		var unique := {}
		for group: String in groups: unique[group] = true
		row = {"model":model, "equipment":equipment.duplicate(true), "mount":mount,
			"extra_groups":extra_groups.duplicate(), "selection_key":selection_key.duplicate(true),
			"groups":unique.keys(), "ready":false, "high_priority":high_priority}
		_actors[id] = row
		_pending[id] = true
	else:
		if not bool(row.ready) and high_priority and not bool(row.high_priority):
			row.high_priority = true
			return _try_ready(id, row)
		return bool(row.ready)
	return _try_ready(id, row)

func _try_ready(id: int, row: Dictionary) -> bool:
	if not bool(service.ensure_groups(row.groups, _owner(id, true), 2 if bool(row.high_priority) else 1)): return false
	_retire_active(id)
	service.pin_groups(_owner(id, false), row.groups)
	_active_groups[id] = row.groups.duplicate()
	service.release_groups(_owner(id, true))
	row.ready = true
	_pending.erase(id)
	return true

func _retire_active(id: int) -> void:
	if not _active_groups.has(id): return
	_next_retired += 1
	var owner := "actor_retired:%d:%d:%d" % [get_instance_id(), id, _next_retired]
	service.pin_groups(owner, _active_groups[id])
	_retired.append(owner)
	_active_groups.erase(id)

## Main releases these only after the head library's asynchronous reads drain.
func release_retired() -> void:
	for owner: String in _retired: service.release_groups(owner)
	_retired.clear()

func poll() -> Array[int]:
	var ready: Array[int] = []
	if _pending.is_empty(): return ready
	var now := Time.get_ticks_msec()
	if now < _next_poll: return ready
	_next_poll = now + 100
	for id: int in _pending.keys():
		var row: Dictionary = _actors[id]
		if not bool(row.ready) and _try_ready(id, row): ready.append(id)
	return ready

func prune(live: Dictionary, parked: Array = []) -> void:
	var keep := {}
	for id: int in parked: keep[id] = true
	for id: int in _actors.keys():
		if not live.has(id) and not keep.has(id):
			_retire_active(id)
			service.release_groups(_owner(id, true))
			service.release_groups(_owner(id, false))
			_actors.erase(id)
			_pending.erase(id)

func clear() -> void:
	prune({})

func pending_for(id: int) -> bool:
	return _pending.has(id)

func groups_for(id: int) -> Array:
	return (_actors.get(id, {}) as Dictionary).get("groups", []).duplicate()

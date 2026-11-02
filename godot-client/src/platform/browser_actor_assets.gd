extends RefCounted
## Admit visible bodies only after their public source files are available.
## Keep the displayed outfit pinned while its replacement is downloading.
var service: Variant
var _actors: Dictionary = {}
var _pending: Dictionary = {}
var _next_poll := 0

func _init(provider: Variant) -> void:
	service = provider

func _owner(id: int, pending: bool) -> String:
	return "actor_%s:%d" % ["pending" if pending else "active", id]

func admit(id: int, model: String, equipment: Dictionary, mount := "") -> bool:
	var row: Dictionary = _actors.get(id, {})
	if row.is_empty() or row.model != model or row.equipment != equipment or row.mount != mount:
		var groups: Array = service.model_groups(model).duplicate()
		groups.append_array(service.equipment_groups(equipment))
		if not mount.is_empty(): groups.append_array(service.model_groups(mount))
		# Catalog dependencies handle shared files; duplicate group IDs need no
		# second request or ownership entry.
		var unique := {}
		for group: String in groups: unique[group] = true
		row = {"model":model, "equipment":equipment.duplicate(true), "mount":mount,
			"groups":unique.keys(), "ready":false}
		_actors[id] = row
		_pending[id] = true
	else:
		return bool(row.ready)
	return _try_ready(id, row)

func _try_ready(id: int, row: Dictionary) -> bool:
	if not bool(service.ensure_groups(row.groups, _owner(id, true))): return false
	service.pin_groups(_owner(id, false), row.groups)
	service.release_groups(_owner(id, true))
	row.ready = true
	_pending.erase(id)
	return true

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
			service.release_groups(_owner(id, true))
			service.release_groups(_owner(id, false))
			_actors.erase(id)
			_pending.erase(id)

func clear() -> void:
	prune({})

func pending_for(id: int) -> bool:
	return _pending.has(id)

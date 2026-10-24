extends AnimationGate
## Rust owns ordinary shared group clocks. Godot owns weak bindings and actual
## AnimationPlayer/Skeleton sampling. Mounted coupled clocks never enter here.
var _owner: Variant
var _native: RefCounted
var _scope: WeakRef
var _tokens: Dictionary = {} # player Variant (may expire) -> {id,generation}
var _by_id: Dictionary = {}
var _next_generation := 1
var _clock_generation := 0
var _stats := {"advance_calls": 0, "due_players": 0, "player_advances": 0,
	"skeleton_advances": 0, "membership_calls": 0, "advance_total_us": 0,
	"membership_total_us": 0, "classify_calls": 0, "classify_records": 0,
	"classify_total_us": 0, "failures": 0}

func configure(owner: Node, native: RefCounted) -> void:
	_owner = owner
	_native = native
	_scope = weakref(owner.get_parent()) if owner != null and owner.get_parent() != null else null

func native_failed() -> void:
	# Keep mirrored group clocks/membership. An in-progress valid due list may
	# finish after a clip callback trips another family; future frames use base.
	_native = null
	_owner = null
	_stats.failures += 1

func classify_batch(records: PackedFloat64Array) -> PackedInt64Array:
	if _native == null: return PackedInt64Array()
	var started := Time.get_ticks_usec()
	var planes := PackedFloat64Array()
	for plane: Plane in _planes:
		planes.append_array(PackedFloat64Array([plane.normal.x, plane.normal.y, plane.normal.z, plane.d]))
	var result: Variant = _native.call("classify_batch", records, planes,
		PackedFloat64Array([_camera_position.x, _camera_position.y, _camera_position.z]))
	var valid: bool = result is Dictionary and result.get("status") is int and result.status == 0 \
		and result.get("tiers") is PackedInt64Array and result.tiers.size() == records.size() / 4
	if valid:
		for tier: int in result.tiers:
			if tier not in [Tier.FULL, Tier.HALF, Tier.PAUSED]: valid = false
	if not valid:
		var owner: Variant = _owner
		if owner != null: owner.fail_closed("gate_classify_invalid")
		return PackedInt64Array()
	_stats.classify_calls += 1
	_stats.classify_records += result.tiers.size()
	_stats.classify_total_us += Time.get_ticks_usec() - started
	return result.tiers

func _join(player: AnimationPlayer, tier: Tier, skeleton: Skeleton3D) -> void:
	if _native == null:
		super._join(player, tier, skeleton)
		return
	var started := Time.get_ticks_usec()
	if not _tokens.has(player):
		_tokens[player] = {"id": player.get_instance_id(), "generation": _next_generation}
		_by_id[player.get_instance_id()] = weakref(player)
		_next_generation += 1
	var token: Dictionary = _tokens[player]
	token["parent"] = weakref(player.get_parent())
	token["skeletonParent"] = weakref(skeleton.get_parent()) if skeleton != null and skeleton.get_parent() != null else null
	var chosen: Variant = _native.call("gate_apply", int(token.id), int(token.generation), int(tier), stagger)
	_stats.membership_calls += 1
	if not chosen is int or chosen < 0 or chosen >= _groups.size() or int(_groups[chosen].tier) != tier:
		var owner: Variant = _owner
		if owner != null: owner.fail_closed("gate_join_invalid")
		super._join(player, tier, skeleton)
		return
	var old: int = int(_group_of.get(player, -1))
	if old >= 0 and old != chosen: (_groups[old].members as Dictionary).erase(player)
	(_groups[chosen].members as Dictionary)[player] = skeleton
	_group_of[player] = chosen
	_stats.membership_total_us += Time.get_ticks_usec() - started

func discard(player: Variant) -> void:
	var token: Dictionary = _tokens.get(player, {})
	if _native != null and not token.is_empty():
		var status: Variant = _native.call("gate_discard", int(token.id), int(token.generation))
		if not status is int or status != 0:
			var owner: Variant = _owner
			if owner != null: owner.fail_closed("gate_discard_invalid")
	if not token.is_empty(): _by_id.erase(int(token.id))
	_tokens.erase(player)
	super.discard(player)

func advance(delta: float) -> void:
	if _native == null:
		super.advance(delta)
		return
	var started := Time.get_ticks_usec()
	var result: Variant = _native.call("gate_advance", delta)
	_stats.advance_calls += 1
	if not _valid_result(result, delta):
		var owner: Variant = _owner
		if owner != null: owner.fail_closed("gate_output_invalid")
		super.advance(delta)
		return
	var meta: PackedInt64Array = result.meta
	var values: PackedFloat64Array = result.values
	var count := meta.size() / 3
	_tick += 1
	for index: int in _groups.size(): _groups[index].delta = values[count + index]
	var clock_generation := _clock_generation
	_stats.due_players += count
	for index: int in count:
		if _clock_generation != clock_generation: break
		var id: int = meta[index * 3]
		var group_index: int = meta[index * 3 + 2]
		var player: Variant = _by_id[id].get_ref() if _by_id.has(id) else null
		if not is_instance_valid(player):
			# Expired keys are forgotten on their due group, as in the base gate.
			var gone: Array = []
			for value: Variant in _groups[group_index].members:
				if not is_instance_valid(value): gone.append(value)
			for value: Variant in gone: discard(value)
			continue
		if not _can_advance(player, id, meta[index * 3 + 1], group_index): continue
		if player.active and player.is_inside_tree():
			var skeleton: Variant = _groups[group_index].members[player]
			player.advance(values[index])
			_stats.player_advances += 1
			# Animation callbacks may clear/reparent/free either node or change tier.
			if _clock_generation != clock_generation or not is_instance_valid(player) \
					or not _can_advance(player, id, meta[index * 3 + 1], group_index): continue
			if is_instance_valid(skeleton) and skeleton.is_inside_tree() \
					and not skeleton.is_queued_for_deletion() \
					and _groups[group_index].members.get(player) == skeleton \
					and (_tokens[player].skeletonParent == null \
						or skeleton.get_parent() == _tokens[player].skeletonParent.get_ref()):
				skeleton.advance(values[index])
				_stats.skeleton_advances += 1
	_stats.advance_total_us += Time.get_ticks_usec() - started

func _can_advance(player: Variant, id: int, generation: int, group: int) -> bool:
	var token: Dictionary = _tokens.get(player, {})
	return not token.is_empty() and int(token.id) == id and int(token.generation) == generation \
		and int(_group_of.get(player, -1)) == group and not player.is_queued_for_deletion() \
		and player.get_parent() == token.parent.get_ref() \
		and (_scope == null or (is_instance_valid(_scope.get_ref()) \
			and not _scope.get_ref().is_queued_for_deletion() and _scope.get_ref().is_ancestor_of(player)))

func _valid_result(result: Variant, delta: float) -> bool:
	if not result is Dictionary or not result.get("status") is int or result.status != 0 \
			or not result.get("meta") is PackedInt64Array or not result.get("values") is PackedFloat64Array:
		return false
	var meta: PackedInt64Array = result.meta
	var values: PackedFloat64Array = result.values
	if meta.size() % 3 != 0 or values.size() != meta.size() / 3 + 7: return false
	for value: float in values:
		if not is_finite(value) or value < 0: return false
	var at := 0
	var steps := 0
	for index: int in _groups.size():
		var group: Dictionary = _groups[index]
		var due := (_tick + 1 + int(group.phase)) % int(group.stride) == 0
		var step: float = float(group.delta) + delta
		var expected_clock := 0.0 if due else step
		if absf(values[meta.size() / 3 + index] - expected_clock) > 0.000000001: return false
		if not due: continue
		for player: Variant in group.members:
			var token: Dictionary = _tokens.get(player, {})
			if token.is_empty() or at + 2 >= meta.size() or meta[at] != int(token.id) \
					or meta[at + 1] != int(token.generation) or meta[at + 2] != index \
					or absf(values[steps] - step) > 0.000000001: return false
			at += 3
			steps += 1
	return at == meta.size() and values[-1] == _tick + 1

func reset(restore_idle: bool = true) -> void:
	_clock_generation += 1
	if _native != null:
		var status: Variant = _native.call("gate_reset")
		if not status is int or status != 0:
			var owner: Variant = _owner
			if owner != null: owner.fail_closed("gate_reset_invalid")
	_tokens.clear()
	_by_id.clear()
	super.reset(restore_idle)

func snapshot() -> Dictionary:
	var d := _stats.duplicate()
	d.merge({"backend": "rust" if _native != null else "legacy", "tick": _tick,
		"halfGroups": group_sizes(Tier.HALF), "quarterGroups": group_sizes(Tier.QUARTER),
		"scope": "ordinary shared clocks only; mounted manager retains its coupled clock"}, true)
	return d

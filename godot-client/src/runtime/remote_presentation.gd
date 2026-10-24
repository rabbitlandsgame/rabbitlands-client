class_name RemotePresentation
extends Node
const OptimizationProfile := preload("res://src/runtime/optimization_profile.gd")
## Derived state only. AppState, network records and UI stay authoritative.
## AnimationPlayer samples clips; the native service never runs a second clip clock.
const ACTIONS: Array[StringName] = [&"idle", &"combat_idle", &"walk", &"run", &"turn", &"death",
	&"sit", &"seated_idle", &"stand", &"ranged_draw", &"ranged_hold", &"ranged_attack", &"cast",
	&"cast_channel_enter", &"cast_channel", &"cast_aggressive", &"cast_defensive", &"heal",
	&"cast_exit", &"attack_primary", &"attack_secondary", &"pain", &"defend"]
const FIXED := 47
const GateScript = preload("res://src/runtime/remote_animation_gate.gd")
const ServerTimePacing = preload("res://src/actors/server_time_pacing.gd")
static var _current: WeakRef
var _controller: ClientRuntimeController
var _app_state: WeakRef
var _native: RefCounted
var _gate: AnimationGate
var _rows: Dictionary = {} # id -> weak node/parent + generation + last validated complete state
var _epoch := 1
var _map_frame := 0
var _sequence := 0
var _ready_native := false
var _applying := false
var _reason := "legacy_selected"
var _requested := "legacy"
var _stats := {"enrolled": 0, "removed": 0, "event_calls": 0, "physics_calls": 0,
	"physics_outputs": 0, "action_decisions": 0, "fallbacks": 0, "unsupported": {},
	"motion_total_us": 0, "action_total_us": 0, "surface_total_us": 0, "sink_total_us": 0,
	"event_boundary_us_nested": 0, "physics_total_us": 0, "physics_apply_us_nested": 0,
	"transfer_total_us": 0, "map_frames": 0, "full_server_apply_us": 0, "full_action_sink_us": 0}

static func current() -> RemotePresentation:
	return _current.get_ref() as RemotePresentation if _current != null else null

func initialize(controller: ClientRuntimeController, gate: AnimationGate) -> AnimationGate:
	if _ready_native or not _rows.is_empty(): close()
	_controller = controller
	_gate = gate
	_current = weakref(self)
	_requested = OptimizationProfile.selected("remote_presentation")
	set_physics_process(false)
	# Coverage needs actual local authority even when the native owner is off.
	# Resolve after SceneTree initialization without an autoload parser dependency.
	var tree := get_tree() if is_inside_tree() else null
	var state: Variant = tree.root.get_node_or_null("AppState") if tree != null else null
	_app_state = weakref(state) if state != null else null
	if _requested != "rust":
		_reason = "legacy_selected" if _requested == "legacy" else "unsupported_mode"
		return gate
	if state == null:
		_reason = "app_state_unavailable"
		return gate
	if controller == null or not controller.is_rust_mode() \
			or not ClassDB.class_exists("RabbitLandsRemotePresentationRuntime"):
		_reason = "verified_runtime_unavailable"
		return gate
	_native = ClassDB.instantiate("RabbitLandsRemotePresentationRuntime") as RefCounted
	var info: Dictionary = _native.call("runtime_info") if _native != null else {}
	if not bool(info.get("ready", false)) or int(info.get("remote_api", -1)) != 1 \
			or int(info.get("state_width", -1)) != FIXED:
		_native = null
		_reason = "remote_api_unavailable"
		return gate
	_epoch = controller.current_epoch()
	if _epoch > 1 and int(_native.call("reset_epoch", _epoch)) != 0:
		_native = null
		_reason = "initial_epoch_rejected"
		return gate
	_ready_native = true
	_reason = "experimental_remote_rust"
	var replacement := GateScript.new()
	replacement.configure(self, _native)
	replacement.gate_skeletons = gate.gate_skeletons
	replacement.stagger = gate.stagger
	replacement.one_shot_tier = gate.one_shot_tier
	_gate = replacement
	set_physics_process(true)
	return replacement

func _session_valid() -> bool:
	return _ready_native and is_inside_tree() and not is_queued_for_deletion() \
		and is_instance_valid(get_parent()) and not get_parent().is_queued_for_deletion() \
		and _native != null and _controller != null and _app_state != null \
		and is_instance_valid(_app_state.get_ref()) \
		and _controller.is_rust_mode() and _controller.current_epoch() == _epoch

func is_local_actor(id: int) -> bool:
	var state: Variant = _app_state.get_ref() if _app_state != null else null
	return is_instance_valid(state) and id == int(state.local_actor_id)

func owns(node) -> bool:
	if not _session_valid() or not is_instance_valid(node): return false
	var row: Dictionary = _rows.get(int(node.actor_id), {})
	return not row.is_empty() and row.node.get_ref() == node \
		and int(row.generation) == int(node._remote_generation) and _binding_valid(int(node.actor_id))

func _unsupported(node) -> String:
	if is_local_actor(int(node.actor_id)): return "local_player"
	if node._cinematic_active: return "cinematic"
	if node._charge_leap != null: return "charge"
	if node._predicted_turn_pending: return "predicted_turn"
	if not ACTIONS.has(node.current_action): return "custom_action"
	return ""

func consider(node) -> bool:
	if not _session_valid() or not is_instance_valid(node) or not node.is_inside_tree() \
			or node.is_queued_for_deletion() or not node._remote_enrollment_ready \
			or get_parent() == null or not get_parent().is_ancestor_of(node): return false
	if not node._remote_pending_transfer.is_empty(): return false
	var why := _unsupported(node)
	if not why.is_empty():
		if owns(node): detach(node, why)
		return false
	if owns(node): return true
	var started := Time.get_ticks_usec()
	var id: int = node.actor_id
	var candidate_parent: WeakRef = weakref(node.get_parent())
	var expected_native := _native
	var expected_epoch := _epoch
	var expected_map := _map_frame
	# Replacement exports first; the successor already adopted the old derived
	# state through the existing Main contract. Failed replacement leaves old live.
	if _rows.has(id):
		var old: Variant = _rows[id].node.get_ref()
		if is_instance_valid(old): detach(old, "body_replacement")
		else: _remove_row(id)
	# Exporting the old body writes transforms and may synchronously remove
	# this manager, queue/reparent the successor, or enroll it reentrantly.
	if not _session_valid() or _native != expected_native or _epoch != expected_epoch or _map_frame != expected_map \
			or not is_instance_valid(node) or not node.is_inside_tree() or node.is_queued_for_deletion() \
			or node.get_parent() != candidate_parent.get_ref() or not get_parent().is_ancestor_of(node) \
			or int(node.actor_id) != id or not node._remote_enrollment_ready \
			or not node._remote_pending_transfer.is_empty() or not _unsupported(node).is_empty():
		return false
	if _rows.has(id):
		return owns(node) # A callback already committed the new binding once.
	var generation: int = _controller.allocate_instance_generation()
	var state := snapshot_actor(node)
	if not _state_valid(state, true):
		_count_unsupported("unrepresentable_transfer")
		return false
	_sequence += 1
	var result: Variant = _native.call("event", 1, id, generation, _epoch, _sequence, _map_frame, state)
	if not _valid_event(result, id, generation, _sequence, 5, true):
		fail_closed("register_rejected")
		return false
	_rows[id] = {"node": weakref(node), "parent": weakref(node.get_parent()),
		"generation": generation, "state": result.values}
	node._remote_generation = generation
	node.set_physics_process(false)
	_stats.enrolled += 1
	_stats.transfer_total_us += Time.get_ticks_usec() - started
	return true

func _count_unsupported(why: String) -> void:
	var counts: Dictionary = _stats.unsupported
	counts[why] = int(counts.get(why, 0)) + 1

func _remove_row(id: int) -> void:
	if not _rows.has(id): return
	var row: Dictionary = _rows[id]
	_sequence += 1
	var result: Variant = _native.call("event", 5, id, int(row.generation), _epoch, _sequence,
		_map_frame, PackedFloat64Array()) if _native != null else null
	_rows.erase(id)
	_stats.removed += 1
	if _ready_native and not _valid_event(result, id, int(row.generation), _sequence, 5, false):
		fail_closed("remove_rejected")

func detach(node, why := "unsupported") -> void:
	if not is_instance_valid(node): return
	var id: int = node.actor_id
	var row: Dictionary = _rows.get(id, {})
	if row.is_empty() or row.node.get_ref() != node: return
	var started := Time.get_ticks_usec()
	if not _restore(node, row.state, true):
		# A callback may already replace this ID. The old frame may remove
		# only its original node/generation, never the successor's binding.
		var current_row: Dictionary = _rows.get(id, {})
		if not current_row.is_empty() and int(current_row.generation) == int(row.generation) \
				and current_row.node.get_ref() == node:
			_remove_row(id)
		return
	node._remote_generation = 0
	_remove_row(id)
	node.set_physics_process((int(row.state[29]) & (4 | 512)) == 0)
	_count_unsupported(why)
	_stats.transfer_total_us += Time.get_ticks_usec() - started

func release_departing(node) -> void:
	# Tree exit is a discard boundary, not a request to reactivate the departing
	# actor. Do not write transforms or callbacks while its destructor runs.
	if not is_instance_valid(node): return
	var id: int = node.actor_id
	var row: Dictionary = _rows.get(id, {})
	if row.is_empty() or row.node.get_ref() != node: return
	# Reparenting can exit/re-enter without deleting the Node. Transfer script
	# data now and apply its latest trusted transform only after it re-enters.
	node._remote_pending_transfer = row.state.duplicate()
	node._remote_generation = 0
	_remove_row(id)

static func restore_pending(node) -> void:
	if not is_instance_valid(node) or not node.is_inside_tree() or node.is_queued_for_deletion(): return
	var state: PackedFloat64Array = node._remote_pending_transfer
	if state.is_empty(): return
	node._remote_pending_transfer = PackedFloat64Array()
	var service := current()
	var temporary := service == null
	if temporary: service = RemotePresentation.new()
	if service._restore(node, state, true):
		node.set_physics_process((int(state[29]) & (4 | 512)) == 0)
	elif is_instance_valid(node) and not node.is_queued_for_deletion() and node._remote_pending_transfer.is_empty():
		# A reentrant reparent may invalidate the attempted publication. Retain
		# the trusted state for the following legal tree-completion boundary.
		node._remote_pending_transfer = state
		node.call_deferred("_restore_remote_pending")
	if temporary: service.free()

func _valid_event(result: Variant, id: int, generation: int, sequence: int,
		width: int, has_state: bool) -> bool:
	if not result is Dictionary or not result.get("status") is int or result.status != 0 \
			or not result.get("meta") is PackedInt64Array or not result.get("values") is PackedFloat64Array:
		return false
	var meta: PackedInt64Array = result.meta
	if meta.size() != width or meta[0] != id or meta[1] != generation or meta[2] != _epoch \
			or meta[3] != _map_frame or meta[4] != sequence: return false
	if width == 8 and (meta[5] not in [0, 1] or meta[6] not in [0, 1] or meta[7] not in [0, 1]): return false
	if width == 7 and (meta[5] < -1 or meta[5] >= ACTIONS.size() or meta[6] not in [0, 1]): return false
	return _state_valid(result.values, true) if has_state else result.values.is_empty()

func _event(node, operation: int, values: PackedFloat64Array, width := 5) -> Dictionary:
	var started := Time.get_ticks_usec()
	if not owns(node): return {}
	var id: int = node.actor_id
	var generation: int = _rows[id].generation
	var native := _native
	var epoch := _epoch
	var map := _map_frame
	_sequence += 1
	_stats.event_calls += 1
	var result: Variant = _native.call("event", operation, id, generation, _epoch,
		_sequence, _map_frame, values)
	if not _valid_event(result, id, generation, _sequence, width, true):
		fail_closed("event_output_invalid")
		return {}
	_rows[id].state = result.values
	if not _restore(node, result.values, true): return {}
	if not _submission_valid(id, generation, epoch, map, native): return {}
	node.set_physics_process(false)
	_stats.event_boundary_us_nested += Time.get_ticks_usec() - started
	return result

func motion(node, dto: Dictionary, adapter: CoordinateAdapter, teleport: bool) -> Dictionary:
	var started := Time.get_ticks_usec()
	if not consider(node): return {}
	var target: Vector3 = adapter.footprint_center(int(dto.x), int(dto.y), node.footprint)
	target.y = node.server_target.y
	var command := int(dto.get("command", -1))
	var facing := int(dto.get("facing_command", command))
	var yaw: float = node.target_yaw_for_state(node._target_yaw, facing, int(dto.rotation), adapter)
	var hastened: bool = (int(dto.get("buffs", 0)) & EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED) != 0 \
		or "haste" in node._status_effects
	var mounted := is_instance_valid(node._mount_visual)
	var scale: float = node._small_creature_scale * node.server_scale
	var walk := 0.0
	var run := 0.0
	if node.resolver != null:
		walk = node.resolver.stride_speed_for_action(&"walk", scale)
		run = node.resolver.stride_speed_for_action(&"run", scale)
	var values := PackedFloat64Array([target.x, target.y, target.z, yaw, node._movement_time_msec(),
		int(dto.get(ServerTimePacing.STEP_KEY, 0)), float(dto.get(ServerTimePacing.PLAYOUT_KEY, 0.0)),
		command, int(dto.get("command_sequence", -1)), int(bool(dto.get("in_combat", node._in_combat))),
		int(hastened), int(dto.has(ServerTimePacing.STEP_KEY)), int(teleport), facing,
		float(node.mount_state.get("step_us", 200000)) / 1000000.0, int(mounted), walk, run,
		node._metres_per_tile, node.walk_presentation_speed, node.run_presentation_speed,
		node.initial_server_interval, node.initial_run_interval, node.turn_speed_radians,
		node.arrival_margin, node.maximum_buffer_seconds, node.catch_up_factor,
		node.minimum_segment_duration, node.maximum_segment_duration, node.movement_coast_seconds,
		node.action_blend_seconds])
	var result := _event(node, 2, values, 8)
	_stats.motion_total_us += Time.get_ticks_usec() - started
	if result.is_empty(): return {}
	return {"target_changed": bool(result.meta[5]), "combat_changed": bool(result.meta[6]),
		"fresh_command": bool(result.meta[7]), "actor_command": command,
		"command_sequence": int(dto.get("command_sequence", -1))}

func choose_action(node, resolved: StringName, target_changed: bool,
		combat_changed: bool, fresh: bool, sequence: int, secondary: bool) -> bool:
	var started := Time.get_ticks_usec()
	var action := ACTIONS.find(resolved)
	if action < 0:
		detach(node, "custom_resolved_action")
		return false
	var result := _event(node, 7, PackedFloat64Array([action, int(target_changed),
		int(combat_changed), int(fresh), sequence, int(secondary)]), 7)
	if result.is_empty(): return false
	var selected: int = result.meta[5]
	if selected < -1 or selected >= ACTIONS.size() or result.meta[6] not in [0, 1]:
		fail_closed("action_output_invalid")
		return false
	_stats.action_decisions += 1
	if selected >= 0 and owns(node): node.play_action(ACTIONS[selected], bool(result.meta[6]))
	_stats.action_total_us += Time.get_ticks_usec() - started
	return true

func surface(node, height: float) -> bool:
	var started := Time.get_ticks_usec()
	var ok := not _event(node, 3, PackedFloat64Array([height])).is_empty()
	_stats.surface_total_us += Time.get_ticks_usec() - started
	return ok

func finished(node) -> bool:
	var started := Time.get_ticks_usec()
	var result := _event(node, 8, PackedFloat64Array(), 7)
	if result.is_empty(): return false
	var action: int = result.meta[5]
	if action >= 0 and owns(node): node.play_action(ACTIONS[action])
	_stats.action_total_us += Time.get_ticks_usec() - started
	return true

func sync_sink(node, wake := false) -> void:
	if not owns(node): return
	var why := _unsupported(node)
	if not why.is_empty():
		detach(node, why)
		return
	var started := Time.get_ticks_usec()
	if wake: node._settled = false
	var action := ACTIONS.find(node.current_action)
	if action < 0:
		detach(node, "custom_action_sink")
		return
	_event(node, 4, PackedFloat64Array([action, node._facing_offset, node._facing_offset_from,
		node._facing_offset_to, node._facing_offset_elapsed, int(node._native_model != null),
		int(node._ranged_aiming), int(is_instance_valid(node._mount_visual)),
		float(node.mount_state.get("step_us", 200000)) / 1000000.0, int(node._settled), int(wake)]))
	_stats.sink_total_us += Time.get_ticks_usec() - started

func sync_transfer(node) -> void:
	if owns(node): _event(node, 6, snapshot_actor(node))

func next_map_frame() -> void:
	if not _session_valid(): return
	_map_frame += 1
	if int(_native.call("set_map_frame", _map_frame)) != 0:
		fail_closed("map_frame_rejected")
	_stats.map_frames += 1

func classify_slice(actors: Dictionary, ids: Array, gate: AnimationGate) -> Dictionary:
	if not _session_valid() or not gate.has_method("classify_batch"): return {}
	var started := Time.get_ticks_usec()
	var records := PackedFloat64Array()
	var captured: Dictionary = {}
	for raw_id: Variant in ids:
		var node: Variant = actors.get(raw_id)
		if not is_instance_valid(node) or not node.is_inside_tree() or not node.has_method("view_radius") \
				or is_local_actor(int(raw_id)): continue
		var anchor: Vector3 = node.global_position + Vector3.UP
		var radius: float = node.view_radius()
		records.append_array(PackedFloat64Array([anchor.x, anchor.y, anchor.z, radius]))
		captured[raw_id] = {"anchor": anchor, "radius": radius}
	var tiers: PackedInt64Array = gate.call("classify_batch", records)
	if tiers.size() != captured.size(): return {}
	var index := 0
	for raw_id: Variant in captured:
		captured[raw_id].tier = tiers[index]
		index += 1
	_stats["classify_slice_total_us"] = int(_stats.get("classify_slice_total_us", 0)) + Time.get_ticks_usec() - started
	return captured

func coverage(actors: Array) -> Dictionary:
	var d := {"actorNodes": 0, "localLegacy": 0, "eligibleRemote": 0, "nativeOwned": 0,
		"legacySupported": 0, "unsupportedRemote": {}, "mountedOwned": 0, "deferredOwned": 0}
	for node: Variant in actors:
		if not is_instance_valid(node) or not node.is_inside_tree() or not node.has_method("view_radius"): continue
		d.actorNodes += 1
		if is_local_actor(int(node.actor_id)):
			d.localLegacy += 1
			continue
		var why := _unsupported(node)
		if not why.is_empty():
			d.unsupportedRemote[why] = int(d.unsupportedRemote.get(why, 0)) + 1
			continue
		d.eligibleRemote += 1
		if owns(node):
			d.nativeOwned += 1
			d.mountedOwned += int(is_instance_valid(node._mount_visual))
			d.deferredOwned += int(node.is_model_deferred())
		else: d.legacySupported += 1
	return d

func _physics_process(delta: float) -> void:
	_advance_physics(delta, Engine.get_physics_frames())

func _advance_physics(delta: float, frame: int) -> void:
	if not _session_valid():
		if _ready_native: fail_closed("session_changed")
		return
	var started := Time.get_ticks_usec()
	# Exceptional ownership changes are rare and are checked before advancing.
	# Iterating weak bindings exports no DTO/history dictionary per physics frame.
	for id: int in _rows.keys():
		var value: Variant = _rows[id].node.get_ref()
		if not _binding_valid(id): _remove_row(id)
		elif not _unsupported(value).is_empty(): detach(value, _unsupported(value))
	if not _session_valid(): return
	var native := _native
	var epoch := _epoch
	var map := _map_frame
	var result: Variant = native.call("physics_tick", epoch, map, frame, delta)
	_stats.physics_calls += 1
	if not _valid_physics(result, frame):
		var legacy_once: Array = []
		for id: int in _rows:
			if _binding_valid(id) and (int(_rows[id].state[29]) & (4 | 512)) == 0:
				legacy_once.append(_rows[id].node)
		fail_closed("physics_output_invalid")
		# Nothing from the malformed batch was published. Replay this one delta
		# from the last validated mirrors, never from untrusted native state.
		for binding: WeakRef in legacy_once:
			var node: Variant = binding.get_ref()
			if is_instance_valid(node) and not node.is_queued_for_deletion() and node.is_inside_tree():
				node._physics_process(delta)
		return
	var meta: PackedInt64Array = result.meta
	var values: PackedFloat64Array = result.values
	# Publish all mirrors first. Reentrant failure transfers this completed tick,
	# never reruns delta through the old per-actor integrator.
	for at: int in range(0, meta.size(), 7):
		var row: Dictionary = _rows[meta[at]]
		var full: PackedFloat64Array = row.state.duplicate()
		for k: int in FIXED: full[k] = values[meta[at + 5] + k]
		row.state = full
	var applying := Time.get_ticks_usec()
	for at: int in range(0, meta.size(), 7):
		var id: int = meta[at]
		if _native != native or _epoch != epoch or _map_frame != map or not _session_valid(): break
		if not _binding_valid(id) or int(_rows[id].generation) != meta[at + 1]: continue
		var node = _rows[id].node.get_ref()
		if not _restore(node, _rows[id].state, false): continue
		if not _submission_valid(id, meta[at + 1], epoch, map, native): continue
		node._level_selection_ring()
		if not _submission_valid(id, meta[at + 1], epoch, map, native): continue
		var model: Variant = node._native_model
		if is_instance_valid(model) and not model.is_queued_for_deletion() \
				and node.is_ancestor_of(model) and not is_instance_valid(node._mount_visual):
			model.rotation.y = node._base_model_yaw + node._facing_offset
		if not _submission_valid(id, meta[at + 1], epoch, map, native): continue
		if node._speech_bubble_expiry_msec > 0 and Time.get_ticks_msec() >= node._speech_bubble_expiry_msec:
			node.clear_speech_bubble()
		if not _submission_valid(id, meta[at + 1], epoch, map, native): continue
		var action: int = meta[at + 6]
		if action >= 0 and _submission_valid(id, meta[at + 1], epoch, map, native): node.play_action(ACTIONS[action])
		_stats.physics_outputs += 1
	_stats.physics_apply_us_nested += Time.get_ticks_usec() - applying
	_stats.physics_total_us += Time.get_ticks_usec() - started

func _binding_valid(id: int) -> bool:
	var row: Dictionary = _rows.get(id, {})
	if row.is_empty(): return false
	var node: Variant = row.node.get_ref()
	return is_instance_valid(node) and node.is_inside_tree() and not node.is_queued_for_deletion() \
		and node.get_parent() == row.parent.get_ref() and is_instance_valid(node.get_parent()) \
		and not node.get_parent().is_queued_for_deletion() and int(node.actor_id) == id \
		and int(node._remote_generation) == int(row.generation)

func _submission_valid(id: int, generation: int, epoch: int, map: int, native: RefCounted) -> bool:
	return _session_valid() and _native == native and _epoch == epoch and _map_frame == map \
		and _binding_valid(id) and int(_rows[id].generation) == generation

func _valid_physics(result: Variant, frame: int) -> bool:
	if not result is Dictionary or not result.get("status") is int or result.status != 0 \
			or not result.get("meta") is PackedInt64Array or not result.get("values") is PackedFloat64Array:
		return false
	var meta: PackedInt64Array = result.meta
	var values: PackedFloat64Array = result.values
	if meta.size() % 7 != 0 or values.size() != meta.size() / 7 * FIXED: return false
	var seen: Dictionary = {}
	for at: int in range(0, meta.size(), 7):
		var id: int = meta[at]
		if seen.has(id) or not _binding_valid(id) or meta[at + 1] != int(_rows[id].generation) \
				or meta[at + 2] != _epoch or meta[at + 3] != _map_frame or meta[at + 4] != frame \
				or meta[at + 5] != at / 7 * FIXED or meta[at + 6] not in [-1, 0]: return false
		if not _state_valid(values.slice(meta[at + 5], meta[at + 5] + FIXED), false): return false
		seen[id] = true
	for id: int in _rows:
		if (int(_rows[id].state[29]) & (4 | 512)) == 0 and not seen.has(id): return false
	return true

func _state_valid(values: PackedFloat64Array, full: bool) -> bool:
	if values.size() < FIXED or (not full and values.size() != FIXED): return false
	for value: float in values:
		if not is_finite(value): return false
	for k: int in [14, 19, 26, 27, 28, 29, 46]:
		if values[k] != floor(values[k]) or absf(values[k]) > 9007199254740991.0: return false
	if int(values[19]) not in range(4) or int(values[26]) not in range(ACTIONS.size()) \
			or int(values[46]) not in [-1, 0, 1, 2, 3] or values[29] < 0 or values[29] > 1023 \
			or values[12] < 0 or values[13] < 0 or values[15] <= 0 or values[18] <= 0 \
			or values[30] <= 0 or values[31] <= 0 or values[34] <= 0 or values[35] <= 0 \
			or values[36] < 0 or values[38] < 0 or values[40] < 0 or values[41] < values[40] \
			or values[42] < 0 or values[43] < 0: return false
	if not full: return true
	var offset := FIXED
	for index: int in 5:
		if offset >= values.size() or values[offset] != floor(values[offset]) or values[offset] < 0 \
				or values[offset] > (12 if index < 4 else 65536): return false
		var count := int(values[offset])
		offset += 1
		if offset + count > values.size(): return false
		for at: int in range(offset, offset + count):
			if values[at] <= 0 or values[at] > 3.402823466e38: return false
		offset += count
	return offset == values.size()

static func snapshot_actor(n) -> PackedFloat64Array:
	var flags := int(n._snap_pending) | (int(n._travel_yaw_active) << 1) | (int(n._settled) << 2) \
		| (int(n._in_combat) << 3) | (int(n._ranged_aiming) << 4) | (int(n._hastened) << 5) \
		| (int(is_instance_valid(n._mount_visual)) << 6) | (int(n._is_creature) << 7) \
		| (int(n._native_model != null) << 8)
	var remote := current()
	if remote != null and remote.owns(n):
		flags |= int(remote._rows[int(n.actor_id)].state[29]) & 512
	elif n.current_action == &"death" and not n.is_physics_processing():
		flags |= 512
	var walk := 0.0
	var run := 0.0
	if n.resolver != null:
		walk = n.resolver.stride_speed_for_action(&"walk", n._small_creature_scale * n.server_scale)
		run = n.resolver.stride_speed_for_action(&"run", n._small_creature_scale * n.server_scale)
	var v := PackedFloat64Array([n.global_position.x, n.global_position.y, n.global_position.z,
		n.server_target.x, n.server_target.y, n.server_target.z,
		n._segment_start.x, n._segment_start.y, n._segment_start.z, n.rotation.y, n._target_yaw,
		n._travel_yaw, n._segment_elapsed, n._segment_duration, n._last_movement_update_msec,
		n._smoothed_server_interval, n._jitter_allowance, n._schedule_due, n._previous_step_tiles,
		n._previous_step_gait, n._presentation_speed, n._movement_coast_remaining, n._facing_offset,
		n._facing_offset_from, n._facing_offset_to, n._facing_offset_elapsed, ACTIONS.find(n.current_action),
		n._last_command_sequence, n._swing_index, flags, float(n.mount_state.get("step_us", 200000)) / 1000000.0,
		n._metres_per_tile, n.walk_presentation_speed, n.run_presentation_speed, n.initial_server_interval,
		n.initial_run_interval, n.turn_speed_radians, n.arrival_margin, n.maximum_buffer_seconds,
		n.catch_up_factor, n.minimum_segment_duration, n.maximum_segment_duration, n.movement_coast_seconds,
		n.action_blend_seconds, walk, run, n._unconfirmed_gait])
	for gait: int in 4:
		var history: PackedFloat32Array = n._pace_histories.get(gait, PackedFloat32Array())
		v.append(history.size())
		for value: float in history: v.append(value)
	v.append(n._unconfirmed_paces.size())
	for value: float in n._unconfirmed_paces: v.append(value)
	return v

func _restore(n, v: PackedFloat64Array, histories: bool) -> bool:
	if not is_instance_valid(n): return false
	var parent: Node = n.get_parent()
	var guarded := owns(n)
	var id: int = n.actor_id
	var generation: int = n._remote_generation
	var native := _native
	var epoch := _epoch
	var map := _map_frame
	n._segment_start = Vector3(v[6], v[7], v[8])
	n._segment_elapsed = v[12]
	n._segment_duration = v[13]
	n._movement_coast_remaining = v[21]
	n._facing_offset = v[22]
	n._facing_offset_elapsed = v[25]
	var flags := int(v[29])
	n._snap_pending = (flags & 1) != 0
	n._travel_yaw_active = (flags & 2) != 0
	n._settled = (flags & 4) != 0
	if histories:
		# Dirty events/transfers restore the whole derived state. Physics outputs
		# write only fields the integrator can change, not pacing histories or
		# action memory for every actor on every tick.
		n.server_target = Vector3(v[3], v[4], v[5])
		n._target_yaw = v[10]
		n._travel_yaw = v[11]
		n._last_movement_update_msec = int(v[14])
		n._smoothed_server_interval = v[15]
		n._jitter_allowance = v[16]
		n._schedule_due = v[17]
		n._previous_step_tiles = v[18]
		n._previous_step_gait = int(v[19])
		n._presentation_speed = v[20]
		n._facing_offset_from = v[23]
		n._facing_offset_to = v[24]
		n.current_action = ACTIONS[int(v[26])]
		n._last_command_sequence = int(v[27])
		n._swing_index = int(v[28])
		n._in_combat = (flags & 8) != 0
		n._ranged_aiming = (flags & 16) != 0
		n._hastened = (flags & 32) != 0
		n._unconfirmed_gait = int(v[46])
		n._pace_histories.clear()
		var at := FIXED
		for gait: int in 4:
			var count := int(v[at])
			at += 1
			var h := PackedFloat32Array()
			for k: int in count: h.append(v[at + k])
			if not h.is_empty(): n._pace_histories[gait] = h
			at += count
		var count := int(v[at])
		at += 1
		n._unconfirmed_paces = PackedFloat32Array()
		for k: int in count: n._unconfirmed_paces.append(v[at + k])
	n.global_position = Vector3(v[0], v[1], v[2])
	if not is_instance_valid(n) or n.is_queued_for_deletion() or n.get_parent() != parent: return false
	if guarded and not _submission_valid(id, generation, epoch, map, native): return false
	n.rotation.y = v[9]
	if not is_instance_valid(n) or n.is_queued_for_deletion() or n.get_parent() != parent: return false
	if guarded and not _submission_valid(id, generation, epoch, map, native): return false
	return true

func reset_world(next_epoch: int, discard_owned := false) -> void:
	if not _ready_native: return
	if _gate != null: _gate.reset(not discard_owned)
	for id: int in _rows.keys():
		if not _rows.has(id): continue
		var node: Variant = _rows[id].node.get_ref()
		if is_instance_valid(node):
			if not discard_owned:
				if not _restore(node, _rows[id].state, true): continue
				node.set_physics_process((int(_rows[id].state[29]) & (4 | 512)) == 0)
			node._remote_generation = 0
	_rows.clear()
	if _native == null: return
	if int(_native.call("reset_epoch", next_epoch)) != 0:
		fail_closed("world_reset_rejected")
		return
	_epoch = next_epoch
	_map_frame = 0
	_sequence = 0

func fail_closed(why: String) -> void:
	if not _ready_native: return
	_ready_native = false
	_reason = why
	_stats.fallbacks += 1
	for id: int in _rows.keys():
		if not _rows.has(id): continue
		var row: Dictionary = _rows[id]
		var node: Variant = row.node.get_ref()
		if is_instance_valid(node) and not node.is_queued_for_deletion():
			if not _restore(node, row.state, true): continue
			node._remote_generation = 0
			node.set_physics_process((int(row.state[29]) & (4 | 512)) == 0)
	_rows.clear()
	if _gate != null and _gate.has_method("native_failed"): _gate.native_failed()
	_native = null
	set_physics_process(false)

func close() -> void:
	var was_ready := _ready_native
	fail_closed("closed")
	if was_ready: _stats.fallbacks -= 1
	if _current != null and _current.get_ref() == self: _current = null

func _exit_tree() -> void:
	close()

func snapshot() -> Dictionary:
	var d := _stats.duplicate(true)
	d.merge({"requested": _requested, "backend": "rust" if _ready_native else "legacy",
		"reason": _reason, "epoch": _epoch, "mapFrame": _map_frame, "sequence": _sequence,
		"ownedActors": _rows.size(), "completeCrowdBenefitQualified": false,
		"clipClockOwner": "godot_animation_player_or_mounted_manager",
		"timingScope": "inclusive boundary timers; nested fields overlap; lifetime counters"}, true)
	d["native"] = _native.call("runtime_info") if _native != null else {}
	d["ordinaryGate"] = _gate.call("snapshot") if _gate != null and _gate.has_method("snapshot") else {}
	return d

func record_boundary(name: String, microseconds: int) -> void:
	_stats[name] = int(_stats.get(name, 0)) + microseconds

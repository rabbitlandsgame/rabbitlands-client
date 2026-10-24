extends SceneTree
## Real native/Godot derived-state parity. No network, imported rig or scene assets.
const Controller = preload("res://src/runtime/client_runtime.gd")
const Remote = preload("res://src/runtime/remote_presentation.gd")
const NativeGate = preload("res://src/runtime/remote_animation_gate.gd")
const ServerTimePacing = preload("res://src/actors/server_time_pacing.gd")
var failures := 0
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})
var holder: Node3D
var controller: ClientRuntimeController
var service: RemotePresentation
var frame := 1
var old_env: Dictionary = {}
var app_state: Variant

class TimedActor extends ReplicatedActor3D:
	var clock := 100000
	var legacy_physics_calls := 0
	func _movement_time_msec() -> int: return clock
	func _physics_process(delta: float) -> void:
		legacy_physics_calls += 1
		super._physics_process(delta)
	func apply_equipment_visuals(_visuals: Dictionary, _fallback_parts: Array = []) -> void: pass

class ReentrantActor extends TimedActor:
	var ring_callback: Callable
	func _level_selection_ring() -> void:
		if ring_callback.is_valid():
			var callback := ring_callback
			ring_callback = Callable()
			callback.call()

class TransformActor extends TimedActor:
	var transform_callback: Callable
	func _notification(what: int) -> void:
		if what == NOTIFICATION_LOCAL_TRANSFORM_CHANGED and transform_callback.is_valid():
			var callback := transform_callback
			transform_callback = Callable()
			callback.call()

class FastMount extends Node3D:
	var coupled_time := 0.0
	var actions: Array[StringName] = []
	func play_action(action: StringName, _restart := false) -> void: actions.append(action)
	func presentation_view_radius() -> float: return 2.0

class BadPhysics extends RefCounted:
	var delegate: RefCounted
	var fault := "id"
	func event(op: int, id: int, generation: int, epoch: int, seq: int, map: int,
			values: PackedFloat64Array) -> Dictionary:
		return delegate.call("event", op, id, generation, epoch, seq, map, values)
	func physics_tick(epoch: int, map: int, tick: int, delta: float) -> Variant:
		var result: Dictionary = delegate.call("physics_tick", epoch, map, tick, delta)
		match fault:
			"type": return []
			"status": result.status = "0"
			"short": result.values.resize(result.values.size() - 1)
			"nan": result.values[0] = NAN
			"id": result.meta[0] += 100
			"generation": result.meta[1] += 1
			"epoch": result.meta[2] += 1
			"map": result.meta[3] += 1
			"frame": result.meta[4] += 1
			"offset": result.meta[5] += 1
			"action": result.meta[6] = 22
			"missing":
				result.meta = PackedInt64Array()
				result.values = PackedFloat64Array()
		return result

class GateOwner extends Node:
	var gate: Variant
	var failures := 0
	func fail_closed(_reason: String) -> void:
		failures += 1
		gate.native_failed()

func _init() -> void: call_deferred("_run")

func _check(ok: bool, label: String) -> bool:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	return ok

func _run() -> void:
	app_state = root.get_node("AppState")
	for key: String in ["RABBITLANDS_CLIENT_RUNTIME", "RABBITLANDS_REMOTE_PRESENTATION"]:
		old_env[key] = OS.get_environment(key)
	OS.set_environment("RABBITLANDS_CLIENT_RUNTIME", "rust")
	OS.set_environment("RABBITLANDS_REMOTE_PRESENTATION", "rust")
	var old_local: int = app_state.local_actor_id
	app_state.local_actor_id = 9000
	holder = Node3D.new()
	root.add_child(holder)
	controller = Controller.new()
	controller.initialize()
	service = Remote.new()
	holder.add_child(service)
	service.initialize(controller, AnimationGate.new())
	service.set_physics_process(false)
	var expected := "--expect-native" in OS.get_cmdline_user_args()
	if not service._ready_native:
		_check(not expected, "requested actual native remote service is available")
		var fallback := _actor(70, false)
		fallback._remote_enrollment_ready = true
		_check(not service.consider(fallback), "absent/unselected native keeps ordinary physics ownership")
		fallback.free()
		print("remote presentation tests: ", "PASS (native unavailable; explicit fallback)" if failures == 0 else "FAIL")
	else:
		_check(controller.is_rust_mode(), "native owner is verified client runtime")
		_check_yaw_readback()
		_check_parity()
		_check_surface_orientation()
		_check_finished_and_death()
		_check_mount_floor()
		_check_transfers()
		_check_gate()
		_check_bad_outputs()
		await _check_replacement_callbacks()
		await _check_manager_lifetime()
		await _check_queued_owner()
		print("remote presentation tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	service.close()
	controller.close()
	holder.free()
	app_state.local_actor_id = old_local
	for key: String in old_env: OS.set_environment(key, old_env[key])
	await process_frame
	quit(failures)

func _actor(id: int, enroll: bool) -> TimedActor:
	var node := TimedActor.new()
	holder.add_child(node)
	node.actor_id = id
	node.server_target = adapter.footprint_center(0, 0, Vector2i.ONE)
	node.global_position = node.server_target
	node._segment_start = node.server_target
	node._snap_pending = false
	node._settled = true
	node.set_physics_process(false)
	node.set_process(false)
	var actions: Dictionary = {}
	for action: StringName in Remote.ACTIONS: actions[String(action)] = String(action)
	node.resolver = AnimationResolver.new({"actions": actions, "serverCommands": {
		"22": "walk", "32": "run", "18": "combat_idle", "19": "idle",
		"40": "attack_primary", "41": "pain", "42": "sit", "43": "stand"},
		"facingOffsets": {"walk": 12.0, "run": -6.0},
		"strideMetresPerSecond": {"walk": 0.8, "run": 2.0}})
	var model := Node3D.new()
	node.add_child(model)
	node._native_model = model
	var player := AnimationPlayer.new()
	node.add_child(player)
	node.animation_player = player
	var library := AnimationLibrary.new()
	for action: StringName in Remote.ACTIONS:
		var clip := Animation.new()
		clip.length = 0.8
		clip.loop_mode = (Animation.LOOP_LINEAR if action in [&"idle", &"combat_idle", &"walk", &"run", &"turn", &"seated_idle", &"ranged_hold", &"cast_channel"] else Animation.LOOP_NONE)
		library.add_animation(action, clip)
	player.add_animation_library(&"", library)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.animation_finished.connect(node._on_animation_finished)
	player.play(&"idle")
	node._remote_enrollment_ready = enroll
	if enroll:
		var admitted: bool = service.consider(node)
		_check(admitted == (id != app_state.local_actor_id), "remote admission/local exclusion")
	return node

func _compare(a: TimedActor, b: TimedActor, label: String) -> void:
	var left := Remote.snapshot_actor(a)
	var right := Remote.snapshot_actor(b)
	if not _check(left.size() == right.size(), label + " complete history length"): return
	for index: int in left.size():
		if absf(left[index] - right[index]) > 0.0002:
			_check(false, "%s state[%d]: %.9f vs %.9f" % [label, index, left[index], right[index]])
			return
	_check(a.current_action == b.current_action, label + " action")

func _step(delta: float) -> void:
	service._advance_physics(delta, frame)
	frame += 1

func _check_yaw_readback() -> void:
	var legacy := _actor(111, false)
	var native := _actor(112, false)
	for actor: TimedActor in [legacy, native]:
		actor.rotation.y = PI - 0.01
		actor._target_yaw = -PI + 0.3
		actor._movement_coast_remaining = 1.0
		actor._settled = false
	native._remote_enrollment_ready = true
	_check(service.consider(native), "yaw readback case is actually native-owned")
	legacy._physics_process(0.005)
	_step(0.005)
	_compare(legacy, native, "yaw crossing current setter")
	_check(legacy.rotation.y > PI and native.rotation.y > PI,
		"current setter preserves an unwrapped crossing until next position write")
	legacy._physics_process(0.005)
	_step(0.005)
	_compare(legacy, native, "yaw next global-position readback")
	_check(legacy.rotation.y < 0.0 and native.rotation.y < 0.0,
		"next position write canonicalizes the actual yaw before turning")
	# A resting height placement writes global_position but has no explicit
	# yaw setter in legacy. The native surface event must preserve that readback.
	legacy.rotation.y = 4.0
	native.rotation.y = 4.0
	legacy._segment_duration = 0.0
	native._segment_duration = 0.0
	service.sync_transfer(native)
	legacy.set_surface_height(2.0)
	native.set_surface_height(2.0)
	_compare(legacy, native, "surface placement yaw readback")
	_check(legacy.rotation.y < 0.0 and native.rotation.y < 0.0,
		"height placement canonicalizes yaw only when actual position is written")
	legacy.free()
	native.free()

func _check_parity() -> void:
	var legacy := _actor(101, false)
	var native := _actor(102, true)
	var sequence := 0
	for index: int in 160:
		# Ordered touched updates: gait changes, hold/burst gaps, repeated sequence,
		# combat reset, stamped vs arrival clocks, tiles/diagonals and hills.
		var command := 22 if index % 4 < 2 else 32
		if index % 17 == 0: command = 18
		if index % 19 == 0: command = 40
		if index % 23 == 0: command = 41
		if index % 7 != 0: sequence += 1
		legacy.clock += 200 + (700 if index % 13 == 0 else 0)
		native.clock = legacy.clock
		var dto := {"x": index % 5, "y": index % 3, "rotation": 0, "command": command,
			"facing_command": 22 if index % 2 == 0 else 24, "command_sequence": sequence,
			"in_combat": index % 17 < 4, "buffs": EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED if index % 8 < 4 else 0}
		if index % 3 != 0:
			dto[ServerTimePacing.STEP_KEY] = legacy.clock - 50 - (100 if index % 11 == 0 else 0)
			dto[ServerTimePacing.PLAYOUT_KEY] = 0.12
		legacy.apply_server_state(dto, adapter, index == 0 or index == 91)
		native.apply_server_state(dto, adapter, index == 0 or index == 91)
		legacy.set_surface_height(float(index % 4) * 0.3)
		native.set_surface_height(float(index % 4) * 0.3)
		_compare(legacy, native, "packet %d" % index)
		for delta: float in [0.016, 0.05, 0.12]:
			legacy._physics_process(delta)
			_step(delta)
			legacy.animation_player.advance(delta)
			native.animation_player.advance(delta)
			_compare(legacy, native, "physics %d" % index)
	_check(native.legacy_physics_calls == 0, "native actors never run the legacy integrator while owned")
	_check(service.snapshot().physics_outputs > 0 and service.snapshot().action_decisions > 0,
		"actual native interpolation and action decisions executed")
	legacy.free()
	native.free()

func _check_surface_orientation() -> void:
	var legacy := _actor(121, false)
	var native := _actor(122, true)
	var normal := Vector3(-0.4, 1.0, 0.3).normalized()
	var dto := {"x": 2, "y": 1, "rotation": 0, "command": 32, "command_sequence": 1}
	for actor: TimedActor in [legacy, native]:
		actor.apply_server_state(dto, adapter)
		actor.set_surface_height(2.0, normal)
	for tick: int in 30:
		legacy._physics_process(1.0 / 120.0)
		_step(1.0 / 120.0)
		_check(legacy._native_model.transform.is_equal_approx(native._native_model.transform),
			"native moving body retains slope lean and facing correction parity")
	for tick: int in 180:
		legacy._physics_process(1.0 / 60.0)
		_step(1.0 / 60.0)
	_check(legacy._native_model.transform.is_equal_approx(native._native_model.transform),
		"native body finishes the sampled lean before sleeping")
	var outputs: int = service.snapshot().physics_outputs
	for tick: int in 30: _step(1.0 / 60.0)
	_check(service.snapshot().physics_outputs == outputs, "settled slope adds no recurring native physics outputs")
	# A refreshed surface at the same height must also wake/finish native lean.
	var changed := Vector3(0.2, 1.0, -0.3).normalized()
	native.set_surface_height(native.server_target.y, changed)
	_step(1.0 / 60.0)
	_check(native._surface_up.is_equal_approx(changed), "native stationary terrain refresh does not freeze the previous normal")
	# Remote mounts use the same completed tick, without a second integrator.
	native._clear_native_surface_tilt()
	var mount := FastMount.new()
	native.add_child(mount)
	native._mount_visual = mount
	native.mount_state = {"mode": "mounted", "step_us": 133333}
	native._surface_applied_up = Vector3(NAN, NAN, NAN)
	service.sync_transfer(native)
	native.set_surface_height(native.server_target.y, normal)
	_step(1.0 / 60.0)
	_check(mount.global_basis.y.is_equal_approx(normal), "native remote mount follows the sampled traversal plane")
	_check(native.global_basis.y.is_equal_approx(Vector3.UP) and native.legacy_physics_calls == 0,
		"native slope presentation leaves authoritative frame and physics ownership intact")
	native._mount_visual = null
	mount.free()
	legacy.free()
	native.free()

func _check_transfers() -> void:
	var actor := _actor(202, true)
	var dto := {"x": 3, "y": 1, "rotation": 0, "command": 32, "command_sequence": 8}
	actor.apply_server_state(dto, adapter)
	_step(0.1)
	var full := Remote.snapshot_actor(actor)
	service.detach(actor, "fixture_transfer")
	_check(not service.owns(actor) and actor.is_physics_processing(), "transfer resumes legacy moving actor")
	_check(Remote.snapshot_actor(actor) == full, "fallback preserves complete histories/schedule/current action")
	_check(service.consider(actor), "normal remote can be re-enrolled with a new generation")
	var old_generation := actor._remote_generation
	var transform := Transform3D(Basis(Vector3.UP, 0.4), Vector3(30, 2, -10))
	service.next_map_frame()
	actor.rebase_world(transform)
	_step(0.05)
	_check(actor._remote_generation == old_generation and service.snapshot().mapFrame == 1,
		"continuous rebase retains generation and changes map-frame identity")
	actor.predict_turn(0.3)
	_check(not service.owns(actor), "predicted movement transfers before exceptional mutation")
	actor.clear_turn_prediction()
	_check(service.consider(actor), "normal ownership restored after exceptional turn")
	var old := actor
	var next := _actor(203, false)
	next.actor_id = old.actor_id
	next.adopt_command_memory_from(old)
	next.apply_server_state(dto, adapter, true)
	next.adopt_presentation_from(old)
	next._remote_enrollment_ready = true
	_check(service.consider(next) and next._remote_generation > old_generation,
		"replacement has a new binding generation")
	_check(next._last_command_sequence == old._last_command_sequence and next._swing_index == old._swing_index,
		"replacement does not replay command/strike memory")
	_check(next._pace_histories == old._pace_histories and next._unconfirmed_paces == old._unconfirmed_paces,
		"replacement keeps full gait histories")
	old.free()
	next.pause_for_parking(service._gate)
	_check(not service.owns(next), "parking releases native motion ownership")
	next.free()
	var local := _actor(app_state.local_actor_id, true)
	_check(not service.owns(local), "local player stays legacy")
	local.free()

func _check_finished_and_death() -> void:
	var a := _actor(151, false)
	var b := _actor(152, true)
	for action: StringName in [&"sit", &"stand", &"ranged_draw", &"cast_channel_enter", &"attack_primary", &"pain"]:
		a.play_action(action, true)
		b.play_action(action, true)
		a.animation_player.advance(1.0)
		b.animation_player.advance(1.0)
		_check(a.current_action == b.current_action, "single Godot finish event selects same next action: " + String(action))
	# Moving death stops physics without manufacturing a settled state; it
	# remains latched after AnimationPlayer finishes, and transfer keeps that.
	var dto := {"x": 2, "y": 0, "rotation": 0, "command": 22, "command_sequence": 3}
	a.apply_server_state(dto, adapter)
	b.apply_server_state(dto, adapter)
	a.play_action(&"death")
	b.play_action(&"death")
	a._physics_process(0.05)
	_step(0.05)
	a.animation_player.advance(1.0)
	b.animation_player.advance(1.0)
	_check(a.current_action == &"death" and b.current_action == &"death", "death never replays or exits on clip completion")
	_check(a._settled == b._settled, "dead physics sleep is separate from standing settled state")
	service.detach(b, "death_transfer")
	_check(not b.is_physics_processing(), "dead transfer does not restart stopped physics")
	a.free()
	b.free()

func _check_mount_floor() -> void:
	var a := _actor(171, false)
	var b := _actor(172, false)
	var left := FastMount.new()
	var right := FastMount.new()
	a.add_child(left)
	b.add_child(right)
	a._mount_visual = left
	b._mount_visual = right
	a.mount_state = {"step_us": 40000}
	b.mount_state = {"step_us": 40000}
	b._remote_enrollment_ready = true
	_check(service.consider(b), "mounted motion can be owned without ordinary pose clock ownership")
	var dto := {"x": 1, "y": 0, "rotation": 0, "command": 32, "facing_command": 32, "command_sequence": 1,
		ServerTimePacing.STEP_KEY: a.clock - 100, ServerTimePacing.PLAYOUT_KEY: 0.0}
	a.apply_server_state(dto, adapter)
	b.apply_server_state(dto, adapter)
	_check(absf(a._segment_duration - 0.04) < 0.000001 and absf(b._segment_duration - 0.04) < 0.000001,
		"fast mount uses supplied .040 cadence instead of ordinary .060 segment floor")
	for delta: float in [0.01, 0.015, 0.025]:
		a._physics_process(delta)
		_step(delta)
		_compare(a, b, "fast mount")
	_check(a.current_action == b.current_action and left.actions == right.actions,
		"mounted action sink does not overwrite rider current_action")
	_check(right.coupled_time == 0.0, "remote motion never advances coupled mounted pose clock")
	a.free()
	b.free()

func _player(parent: Node) -> AnimationPlayer:
	var player := AnimationPlayer.new()
	parent.add_child(player)
	var library := AnimationLibrary.new()
	var clip := Animation.new()
	clip.length = 60.0
	clip.loop_mode = Animation.LOOP_LINEAR
	library.add_animation(&"idle", clip)
	player.add_animation_library(&"", library)
	player.play(&"idle")
	return player

func _check_gate() -> void:
	var owner := GateOwner.new()
	holder.add_child(owner)
	var gate := NativeGate.new()
	owner.gate = gate
	gate.configure(owner, ClassDB.instantiate("RabbitLandsRemotePresentationRuntime"))
	var legacy := AnimationGate.new()
	var players: Array[Array] = []
	for index: int in 12:
		var pair: Array = [_player(owner), _player(owner)]
		var tier: AnimationGate.Tier = AnimationGate.Tier.HALF if index < 5 else AnimationGate.Tier.QUARTER
		legacy.apply(pair[0], tier)
		gate.apply(pair[1], tier)
		players.append(pair)
	for step: int in 31:
		var delta := 0.01 + float(step % 4) * 0.013
		legacy.advance(delta)
		gate.advance(delta)
		_check(legacy.group_sizes(AnimationGate.Tier.HALF) == gate.group_sizes(AnimationGate.Tier.HALF), "shared half groups")
		_check(legacy.group_sizes(AnimationGate.Tier.QUARTER) == gate.group_sizes(AnimationGate.Tier.QUARTER), "shared quarter groups")
		for pair: Array in players:
			_check(absf(pair[0].current_animation_position - pair[1].current_animation_position) < 0.000001,
				"manual ordinary clip time matches shared accumulated group delta")
		if step == 9:
			legacy.discard(players[0][0])
			gate.discard(players[0][1])
			legacy.apply(players[0][0], AnimationGate.Tier.QUARTER)
			gate.apply(players[0][1], AnimationGate.Tier.QUARTER)
	_check(owner.failures == 0, "ordinary group batches never fall back")
	var camera := Camera3D.new()
	owner.add_child(camera)
	camera.look_at_from_position(Vector3(0, 20, 26), Vector3.ZERO)
	gate.begin(camera)
	legacy.begin(camera)
	var records := PackedFloat64Array()
	for p: Vector3 in [Vector3.ZERO, Vector3(0, 1, -40), Vector3(200, 1, 0), Vector3(0, 1, 60)]:
		records.append_array(PackedFloat64Array([p.x, p.y, p.z, 2.0]))
	var tiers: PackedInt64Array = gate.classify_batch(records)
	for index: int in 4:
		_check(tiers[index] == legacy.classify(Vector3(records[index * 4], records[index * 4 + 1], records[index * 4 + 2]), 2.0),
			"same-slice native frustum classification")
	gate.reset(false)
	_check(players[0][1].callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL,
		"discard reset never restores queued modifier callback modes")
	legacy.reset(false)
	owner.free()

func _check_bad_outputs() -> void:
	# Fresh native epoch per corruption: no bad batch can publish its first row.
	for fault: String in ["type", "status", "short", "nan", "id", "generation", "epoch", "map", "frame", "offset", "action", "missing"]:
		var a := _actor(301, false)
		var b := _actor(302, true)
		var dto := {"x": 3, "y": 0, "rotation": 0, "command": 32, "command_sequence": 1}
		a.apply_server_state(dto, adapter)
		b.apply_server_state(dto, adapter)
		var bad := BadPhysics.new()
		bad.delegate = service._native
		bad.fault = fault
		service._native = bad
		a._physics_process(0.125)
		_step(0.125)
		_compare(a, b, "malformed " + fault)
		_check(not service.owns(b) and b.legacy_physics_calls == 1,
			"bad whole output falls back with exactly one current-frame delta")
		a.free()
		b.free()
		service.close()
		service.queue_free()
		service = Remote.new()
		holder.add_child(service)
		service.initialize(controller, AnimationGate.new())
		service.set_physics_process(false)

func _check_replacement_callbacks() -> void:
	# Node3D global_position synchronously notifies LOCAL_TRANSFORM_CHANGED.
	# These callbacks run inside detach(old), before consider(new) resumes.
	for mode: int in 3:
		var old := TransformActor.new()
		holder.add_child(old)
		old.actor_id = 700 + mode
		old._remote_enrollment_ready = true
		old._snap_pending = false
		old._settled = true
		old.set_physics_process(false)
		old.set_process(false)
		_check(service.consider(old), "replacement callback owns old binding: %d" % mode)
		var next := _actor(old.actor_id, false)
		next._remote_enrollment_ready = true
		next.set_physics_process(true)
		var native: RefCounted = service._native
		var before_calls := int(native.call("runtime_info").event_calls)
		var observed := {"calls": 0, "nested": false}
		old.set_notify_local_transform(true)
		old.transform_callback = func():
			observed.calls += 1
			if mode == 0:
				holder.remove_child(service) # Legal unrelated Node exit; no self.free.
			elif mode == 1:
				next.queue_free()
			else:
				observed.nested = service.consider(next)
		var accepted := service.consider(next)
		_check(observed.calls == 1, "real old-body local transform callback executes: %d" % mode)
		if mode == 0:
			_check(not accepted and not service._ready_native and service._rows.is_empty()
				and next._remote_generation == 0 and next.is_physics_processing(),
				"manager exit during replacement leaves successor legacy without stale registration")
			_check(int(native.call("runtime_info").event_calls) == before_calls,
				"closed-session replacement submits no later native registration")
		elif mode == 1:
			_check(not accepted and next.is_queued_for_deletion() and next._remote_generation == 0
				and service._rows.is_empty(), "queued successor cannot gain a native binding")
		else:
			_check(accepted and bool(observed.nested) and service.owns(next)
				and service._rows.size() == 1 and old._remote_generation == 0,
				"reentrant same-ID registration survives old detach and commits once")
			_check(int(native.call("runtime_info").active_bindings) == 1,
				"one physical successor has exactly one native binding")
		old.free()
		if is_instance_valid(next) and not next.is_queued_for_deletion(): next.free()
		service.close()
		if service.get_parent() != null: service.get_parent().remove_child(service)
		service.free()
		native = null
		await process_frame
		service = Remote.new()
		holder.add_child(service)
		service.initialize(controller, AnimationGate.new())
		service.set_physics_process(false)

func _check_manager_lifetime() -> void:
	var actor := _actor(401, true)
	actor.apply_server_state({"x": 3, "y": 0, "rotation": 0, "command": 22, "command_sequence": 1}, adapter)
	_step(0.05)
	var before := Remote.snapshot_actor(actor)
	holder.remove_child(service)
	_check(actor._remote_generation == 0 and actor.is_physics_processing(),
		"removing manager alone restores surviving actor physics")
	_check(Remote.snapshot_actor(actor) == before, "manager-only exit transfers full state")
	service.free()
	actor.free()
	service = Remote.new()
	holder.add_child(service)
	service.initialize(controller, AnimationGate.new())
	service.set_physics_process(false)
	var first := ReentrantActor.new()
	holder.add_child(first)
	first.actor_id = 501
	first._remote_enrollment_ready = true
	first._snap_pending = false
	first._settled = false
	first.server_target = Vector3(1, 0, 0)
	first._segment_duration = 1.0
	first.set_physics_process(false)
	_check(service.consider(first), "reentrant first binding")
	var later := _actor(502, true)
	later.apply_server_state({"x": 3, "y": 0, "rotation": 0, "command": 22, "command_sequence": 1}, adapter)
	var other_world := Node3D.new()
	root.add_child(other_world)
	var trusted := {"state": PackedFloat64Array()}
	first.ring_callback = func():
		trusted.state = service._rows[502].state.duplicate()
		later.reparent(other_world)
	_step(0.05)
	_check(not service.owns(later) and later._remote_generation == 0
		and not later._remote_pending_transfer.is_empty(),
		"callback reparent immediately rejects old-owner publication and retains trusted transfer")
	# Reparent restores the old transform after enter_tree. The deferred
	# transfer runs afterwards; disable fixture physics before the next tick.
	later.call_deferred("set_physics_process", false)
	await process_frame
	_check(later.get_parent() == other_world and later._remote_pending_transfer.is_empty()
		and Remote.snapshot_actor(later) == trusted.state,
		"post-reparent completion restores the exact latest native state without replay")
	first.free()
	later.free()
	other_world.free()
	var survivor := _actor(503, true)
	survivor.apply_server_state({"x": 2, "y": 0, "rotation": 0, "command": 22, "command_sequence": 1}, adapter)
	service.reset_world(controller.current_epoch() + 1)
	controller.reset_session()
	_check(survivor._remote_generation == 0 and survivor.is_physics_processing(),
		"default epoch reset transfers survivors; only Main full-discard opts out")
	_check(service.consider(survivor), "reconnect binds into new controller epoch")
	survivor.free()


func _check_queued_owner() -> void:
	var first := ReentrantActor.new()
	holder.add_child(first)
	first.actor_id = 601
	first._remote_enrollment_ready = true
	first._snap_pending = false
	first._settled = false
	first.server_target = Vector3(1, 0, 0)
	first._segment_duration = 1.0
	first.set_physics_process(false)
	first.process_mode = Node.PROCESS_MODE_DISABLED
	_check(service.consider(first), "queued-owner first binding")
	var later := _actor(602, true)
	later.process_mode = Node.PROCESS_MODE_DISABLED
	later.apply_server_state({"x":3,"y":0,"rotation":0,"command":22,"command_sequence":1}, adapter)
	var observed := {"calls":0}
	first.ring_callback = func():
		observed.calls += 1
		# Legal while this Script method is on the stack: defer owner deletion.
		service.queue_free()
	_step(0.05)
	_check(observed.calls == 1 and not service._session_valid(),
		"legal queued-owner callback immediately invalidates native publication")
	var first_state: PackedFloat64Array = service._rows[601].state.duplicate()
	var later_state: PackedFloat64Array = service._rows[602].state.duplicate()
	await process_frame
	_check(not is_instance_valid(service), "queued manager is released at legal engine barrier")
	_check(first._remote_generation == 0 and later._remote_generation == 0
		and first.is_physics_processing() and later.is_physics_processing(),
		"manager-only queue restores surviving actor callback ownership")
	_check(Remote.snapshot_actor(first) == first_state and Remote.snapshot_actor(later) == later_state,
		"queued manager transfers completed tick exactly once to both survivors")
	first.free()
	later.free()
	service = Remote.new()
	holder.add_child(service)
	service.initialize(controller, AnimationGate.new())
	service.set_physics_process(false)

extends Node
## Public synthetic workload, never replay/player data. Packet identities and
## positions stay in memory; reports retain counters and workload policy only.
var _main: WeakRef
var _state: WeakRef
var _send: Callable
var _moving: Array[int] = []
var _fighting: Array[int] = []
var _rows: Dictionary = {}
var _counts: Dictionary = {}
var _power_packets: Dictionary = {}
var _power_admitted: Dictionary = {}
var _backends := {"rust":0,"cpp":0,"gd":0}
var _roles: Array[String] = []
var _probing := false
var _probe_effect: WeakRef
var _probe_expired := false
var _saved_selected := -1
var _saved_combat: Dictionary = {}
var _window := "warmup"

func _init() -> void:
	process_priority = 200 # Observe both default effects and native manager100.

func configure(main: Node, state: Node, plan: Dictionary, send_packet: Callable) -> void:
	_main = weakref(main)
	_state = weakref(state)
	_send = send_packet
	_moving.assign(plan.moving)
	_fighting.assign(plan.fighting)
	_saved_selected = int(state.get("selected_actor_id"))
	_saved_combat = (state.get("combat_state") as Dictionary).duplicate(true)
	state.set("selected_actor_id", _fighting[1])
	var combat := _saved_combat.duplicate(true)
	combat["active"] = true
	combat["target_id"] = _fighting[2]
	state.set("combat_state", combat)

func _inc(key: String, amount := 1) -> void:
	_counts[key] = int(_counts.get(key,0)) + amount

func _u16(bytes: PackedByteArray, value: int) -> void:
	bytes.append(value & 255)
	bytes.append((value >> 8) & 255)

func drive_tick(tick: int, cadence_ms: int) -> void:
	# The profile is wall-clock paced like the normal live driver. Every2s one
	# explicit packet burst contains143 spells. Sixteen separate actors move.
	var step_ticks := maxi(1, roundi(600.0/cadence_ms))
	if tick % step_ticks == 0:
		var commands := PackedByteArray()
		for id: int in _moving:
			_u16(commands,id)
			commands.append(22 if (tick / step_ticks) % 2 == 0 else 26)
		_send.call(EloriaProtocol.ServerMessage.ADD_ACTOR_COMMAND,commands)
		_inc("movement_packets")
	var round_ticks := maxi(1,roundi(2000.0/cadence_ms))
	if tick % round_ticks != 0:
		return
	_inc("bursts")
	# Priority casts are last, after ordinary visuals have filled the soft cap.
	for offset: int in _fighting.size():
		var index := (offset+3)%_fighting.size()
		var source := _fighting[index]
		var target := _fighting[(index+1)%_fighting.size()]
		if index == 0:
			target = int((_state.get_ref() as Node).get("local_actor_id"))
		elif index == 1:
			target = _fighting[1] if source != _fighting[1] else _fighting[2]
		elif index % 5 == 0:
			target = _moving[index % _moving.size()]
			_inc("moving_target_casts")
		_cast(source,target,1+(index%10))

func _cast(source: int, target: int, power: int) -> void:
	var state := _state.get_ref() as Node
	var combat: Dictionary = state.get("combat_state")
	_roles.clear()
	if source == int(state.get("local_actor_id")) or target == int(state.get("local_actor_id")):
		_roles.append("local")
	if source == int(state.get("selected_actor_id")) or target == int(state.get("selected_actor_id")):
		_roles.append("selected")
	if source == int(combat.get("target_id",-1)) or target == int(combat.get("target_id",-1)):
		_roles.append("combat")
	for role: String in _roles:
		_inc(role+"_priority_packets")
	var payload := PackedByteArray([2])
	_u16(payload,source)
	_u16(payload,target)
	payload.append(power)
	_inc("spell_packets")
	_power_packets[str(power)] = int(_power_packets.get(str(power),0))+1
	_send.call(EloriaProtocol.ServerMessage.SEND_SPECIAL_EFFECT,payload)
	_roles.clear()

func observe(node: Node) -> void:
	var effect := node as WorldEffect3D
	if effect == null or effect.effect_id != 2 or effect.flight == null:
		return
	_inc("admitted_visuals")
	for role: String in _roles:
		_inc(role+"_priority_admitted")
	var backend := "gd"
	if node is RustSpellEffect3D and (node as RustSpellEffect3D)._batched:
		backend = "rust"
	elif bool(effect.flight.call("native_presentation_active")):
		backend = "cpp"
	_backends[backend] = int(_backends[backend])+1
	_power_admitted[str(effect.power_level)] = int(_power_admitted.get(str(effect.power_level),0))+1
	_rows[node.get_instance_id()] = {"weak":weakref(node),"launched":false,"arrived":false,"expired":false,"probe":_probing}
	_counts["maximum_observed_live"] = maxi(int(_counts.get("maximum_observed_live",0)),_rows.size())
	if _probing:
		_probe_effect = weakref(node)

func _process(_delta: float) -> void:
	poll()

func poll() -> void:
	for id: int in _rows.keys():
		var row: Dictionary = _rows[id]
		var effect: WorldEffect3D = row.weak.get_ref() as WorldEffect3D
		if not is_instance_valid(effect):
			if not bool(row.expired):
				_inc("external_retirements")
			_rows.erase(id)
			continue
		if bool(row.launched) and not effect._launched or bool(row.arrived) and not effect.impact_started:
			_inc("phase_regressions")
		if effect._launched and not bool(row.launched):
			row.launched = true
			_inc("observed_releases")
		if effect.impact_started and not bool(row.arrived):
			row.arrived = true
			_inc("observed_arrivals")
		var age: float = effect.elapsed-effect.release_delay-float(effect.flight.duration)
		if age >= WorldEffect3D.LIFETIME_SECONDS and not bool(row.expired):
			row.expired = true
			if bool(row.probe):
				_probe_expired = true
			_inc("observed_expiries")
		if effect.is_queued_for_deletion():
			if not bool(row.expired):
				_inc("external_retirements")
			_rows.erase(id)

func snapshot() -> Dictionary:
	poll()
	return {"counters":_counts.duplicate(),"powerPackets":_power_packets.duplicate(),
		"powerAdmitted":_power_admitted.duplicate(),"admittedBackends":_backends.duplicate(),
		"trackedLive":_rows.size(),"window":_window}

func begin_sample() -> Dictionary:
	_window = "sample"
	return snapshot()

func sample_report(before: Dictionary) -> Dictionary:
	var after := snapshot()
	var deltas: Dictionary = {}
	for key: String in after.counters:
		if key != "maximum_observed_live":
			deltas[key] = int(after.counters[key])-int(before.counters.get(key,0))
	return {"schemaVersion":1,"kind":"synthetic_heat_bolt_packets","family":"heat_bolt",
		"clockPolicy":"benchmark Main adds fixed0.2s release and0.4s flight after packet decoding",
		"burstPeriodMilliseconds":2000,"castsPerBurst":_fighting.size(),
		"priorityPacketOrder":"after-normal-burst",
		"movingActors":_moving.size(),"onFootActors":160,"sampleCounters":deltas,
		"sampleStart":before,"sampleEnd":after,"lifetimeMaximumObservedLive":int(_counts.get("maximum_observed_live",0)),
		"counterScope":"sample end-minus-start; lifetime maximum is not a sample maximum"}

func removal_probe() -> Dictionary:
	# Outside timing: real REMOVE_ACTOR packet, effect survives it, then restore
	# the exact authored synthetic record. Parked actors can remain allocated;
	# report that honestly rather than asserting WeakRef destruction.
	_window = "untimed_removed_target_probe"
	var state := _state.get_ref() as Node
	var main := _main.get_ref() as Node
	var target := _moving[0]
	var source := _fighting[_fighting.size()-1]
	var actors: Dictionary = state.get("actors")
	var saved: Dictionary = (actors[target] as Dictionary).duplicate(true)
	var old_node: Node3D = (main.get("actor_nodes") as Dictionary).get(target) as Node3D
	var old_ref: WeakRef = weakref(old_node) if old_node != null else null
	var selected := int(state.get("selected_actor_id"))
	state.set("selected_actor_id",target)
	_probe_effect = null
	_probe_expired = false
	_probing = true
	_cast(source,target,10)
	_probing = false
	var payload := PackedByteArray()
	_u16(payload,target)
	_send.call(EloriaProtocol.ServerMessage.REMOVE_ACTOR,payload)
	main.call("_sync_world")
	await get_tree().physics_frame
	await get_tree().process_frame
	await get_tree().process_frame
	var absent: bool = not (state.get("actors") as Dictionary).has(target)
	var presentation_absent: bool = not (main.get("actor_nodes") as Dictionary).has(target)
	var retained: bool = old_ref != null and is_instance_valid(old_ref.get_ref())
	var finite_endpoints := true
	var completed := false
	var was_admitted := _probe_effect != null
	var deadline := Time.get_ticks_msec()+5000
	while was_admitted and Time.get_ticks_msec() < deadline:
		var effect: WorldEffect3D = _probe_effect.get_ref() as WorldEffect3D
		if not is_instance_valid(effect):
			completed = _probe_expired
			break
		finite_endpoints = finite_endpoints and effect.flight.start.is_finite() and effect.flight.destination.is_finite()
		poll()
		if effect.is_queued_for_deletion():
			completed = effect.impact_started and effect.elapsed >= effect.release_delay+float(effect.flight.duration)+1.1
			break
		await get_tree().physics_frame
		await get_tree().process_frame
	var restored: Dictionary = (state.get("actors") as Dictionary).duplicate()
	restored[target] = saved
	state.set("actors",restored)
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	state.set("selected_actor_id",selected)
	return {"success":was_admitted and absent and presentation_absent and finite_endpoints and completed,
		"outsideTimedSample":true,"spellAdmitted":was_admitted,"actorRecordRemoved":absent,
		"actorPresentationRemoved":presentation_absent,"removedActorNodeRetained":retained,
		"finiteFlightEndpoints":finite_endpoints,"effectCompleted":completed,
		"removalScope":"network actor removal; parked node destruction is not required",
		"restoredRecord":(state.get("actors") as Dictionary).has(target)}

func finish() -> void:
	var state := _state.get_ref() as Node
	if state != null:
		state.set("selected_actor_id",_saved_selected)
		state.set("combat_state",_saved_combat)
	var main := _main.get_ref() as Node
	if main != null:
		main.set("benchmark_heat_bolt",null)
	_rows.clear()
	queue_free()

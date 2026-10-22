extends SceneTree
## Crowd presentation (src/world/crowd_presentation.gd): bodies are built only
## for actors near enough to be drawn, nearest first; a body far out of range
## is given up again; a body the server removes is parked for a return; the
## optional body cap keeps the nearest; the paused tier stops a body's
## skeleton; and the live-effect budget bounds combat visuals.
##
## main.gd is loaded at run time, not preloaded: it reads the autoload
## singletons, which a SceneTree script is compiled before.

const CROWD := preload("res://src/world/crowd_presentation.gd")
const BUDGET := preload("res://src/world/live_effect_budget.gd")
const LOCAL := 100
const HUMANOID_KIT := {0: 114, 1: 106, 3: 117, 4: 171, 5: 184, 6: 192}

var failures := 0
var _main: Control
var _app_state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_test_policy_parsing()
	_test_effect_budget()
	var main_script := load("res://src/app/main.gd") as GDScript
	if not _expect(main_script != null and main_script.can_instantiate(), "main.gd compiles"):
		quit(failures)
		return
	await _set_up()
	await _test_lazy_bodies()
	await _test_parking()
	await _test_release()
	await _test_body_cap()
	await _test_paused_tier()
	_test_rate_ranking()
	_test_cloth_budget()
	await _test_bulk_removal()
	print("crowd presentation tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)


func _test_policy_parsing() -> void:
	var policy: RefCounted = CROWD.new()
	policy.call("configure", "")
	_expect(policy.lazy and policy.gate and policy.effects and policy.park and policy.body_cap == 0,
		"an empty setting is the full crowd presentation, no body cap")
	policy.call("configure", "legacy")
	_expect(not policy.lazy and not policy.gate and not policy.effects and not policy.park,
		"legacy switches every part off")
	policy.call("configure", "lazy,gate", "160")
	_expect(policy.lazy and policy.gate and not policy.effects and not policy.park
		and policy.body_cap == 160, "a list keeps only what it names, and the cap is read")
	policy.call("configure", "-park")
	_expect(policy.lazy and policy.gate and policy.effects and not policy.park,
		"-name drops one part from the full set")
	policy.call("configure", "")
	_expect(policy.stagger and policy.quarter and policy.half_rate_bodies == policy.HALF_RATE_BODIES,
		"the full set staggers the stepped bodies and has the quarter tier")
	policy.call("configure", "-quarter", "", "half=8")
	_expect(policy.stagger and not policy.quarter and policy.half_rate_bodies == 8,
		"the quarter tier can be dropped alone, and the half-rate budget tuned")
	policy.call("configure", "-gate")
	_expect(not policy.stagger and not policy.quarter,
		"staggering and the quarter tier go with the gate they refine")
	policy.call("configure", "legacy")
	_expect(not policy.stagger and not policy.quarter, "legacy has neither")


func _test_effect_budget() -> void:
	var budget: RefCounted = BUDGET.new()
	var limit := int((BUDGET.LIMITS as Dictionary)[&"number"])
	var parent := Node.new()
	root.add_child(parent)
	var labels: Array[Node] = []
	var admitted := 0
	for index: int in range(limit):
		admitted += int(budget.call("admit", &"number", false))
		var label := Node.new()
		parent.add_child(label)
		budget.call("track", label, &"number")
		labels.append(label)
	_expect(admitted == limit, "numbers fit the budget up to its limit (%d)" % admitted)
	_expect(int(budget.call("live", &"number")) == limit, "every tracked number counts as live")
	_expect(not budget.call("admit", &"number", false), "past the limit an ordinary number is skipped")
	_expect(budget.call("admit", &"number", true), "the player's own fight is always drawn")
	labels[0].free()
	_expect(int(budget.call("live", &"number")) == limit - 1, "a number leaving the tree frees its place")
	_expect(budget.call("admit", &"number", false), "and the next one fits again")
	budget.set("enabled", false)
	parent.free()
	_expect(budget.call("admit", &"spell", false), "a disabled budget admits everything")


func _set_up() -> void:
	root.size = Vector2i(1280, 720)
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("GameView") as Control).show()
	(_main.get_node("LoginPanel") as Control).hide()
	_app_state = root.get_node("/root/AppState")
	_app_state.set("authenticated", true)
	_app_state.set("local_actor_id", LOCAL)
	await process_frame


func _record(id: int, x: int, y: int, humanoid := true) -> Dictionary:
	var record := {"actor_id": id, "x": x, "y": y, "rotation": 0,
		"actor_type": 1 if humanoid else _creature_type(), "kind": 1 if humanoid else 5,
		"name": "Crowd %d" % id, "health": 50, "max_health": 50, "alive": true,
		"appearance": {}, "equipment_visuals": HUMANOID_KIT.duplicate() if humanoid else {},
		"equipment_fallback_parts": []}
	return record


func _creature_type() -> int:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var types: Dictionary = (parsed as Dictionary).get("actorTypes", {}) as Dictionary
	var models: Dictionary = (parsed as Dictionary).get("models", {}) as Dictionary
	for raw: Variant in types:
		var model := models.get(str(types[raw]), {}) as Dictionary
		if int(str(raw)) >= 200 and FileAccess.file_exists(str(model.get("scene", ""))) \
				and not bool(model.get("retired", false)):
			return int(str(raw))
	return 1


func _nodes() -> Dictionary:
	return _main.get("actor_nodes") as Dictionary


func _sync() -> void:
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	await process_frame


## One gate pass and the builds it queues, as a frame would run them.
func _gate_and_build() -> void:
	_main.set("_animation_gate_refresh_msec", 0)
	_main.call("_update_animation_gate", 0.0)
	_main.call("_update_model_builds")
	await process_frame


func _put(records: Array) -> void:
	var actors: Dictionary = (_app_state.get("actors") as Dictionary)
	for record: Dictionary in records:
		actors[int(record.actor_id)] = record
		_app_state.call("mark_actor_changed", int(record.actor_id))


func _test_lazy_bodies() -> void:
	_put([_record(LOCAL, 500, 500), _record(101, 510, 500), _record(102, 700, 500, false)])
	await _sync()
	var nodes := _nodes()
	var near := nodes.get(101) as ReplicatedActor3D
	var far := nodes.get(102) as ReplicatedActor3D
	if not _expect(near != null and far != null, "both arrivals get a node on the pass they arrive"):
		return
	_expect(not (nodes[LOCAL] as ReplicatedActor3D).is_model_deferred(), "the player's own body is built at once")
	_expect(not near.is_model_deferred() and near.get_node_or_null("NativeModel") != null,
		"an actor 10 m away is built at once")
	_expect(far.is_model_deferred() and far.get_node_or_null("NativeModel") == null
		and far.get_skeleton() == null and far.animation_player == null,
		"an actor 200 m away is a deferred node: no model, skeleton or animation")
	_expect(far.get_node_or_null("MapDot") != null and far.get_node_or_null("Nameplate") != null
		and far.get_node_or_null("SelectionCollision") != null,
		"but keeps its map dot, its overhead block and its picking shape")
	_expect(not far.is_drawn() and not far.stand_in_visible(),
		"out of draw range it is not drawn, and neither is its stand-in")
	# It walks into range: the next gate pass ranks it, and a build replaces it.
	_put([_record(102, 560, 500, false)])
	await _sync()
	far = _nodes().get(102) as ReplicatedActor3D
	_expect(far.is_model_deferred(), "presenting a record does not build its body by itself")
	var deferred_at: Vector3 = far.global_position
	await _gate_and_build()
	var built := _nodes().get(102) as ReplicatedActor3D
	_expect(built != null and built != far and not built.is_model_deferred()
		and built.get_skeleton() != null, "within range the gate pass builds its body in a new node")
	_expect(built != null and built.global_position.distance_to(deferred_at) < 0.01,
		"the built body stands where the deferred node stood")
	_expect(not is_instance_valid(far) or far.is_queued_for_deletion(), "the deferred node is let go")
	# Nearest first: with more arrivals than the per-pass budget, the nearest
	# are built and the rest deferred, whatever order they arrived in.
	var batch: Array = []
	for index: int in range(8):
		batch.append(_record(110 + index, 500 + 30 - index * 3, 520))
	_put(batch)
	await _sync()
	var built_ids: Array[int] = []
	for index: int in range(8):
		if not (_nodes()[110 + index] as ReplicatedActor3D).is_model_deferred():
			built_ids.append(110 + index)
	_expect(built_ids.size() == ACTOR_SPAWN_BUDGET(),
		"one pass builds exactly the spawn budget (%d of 8)" % built_ids.size())
	_expect(built_ids == [114, 115, 116, 117], "and builds the nearest ones: %s" % [built_ids])
	var waiting := _nodes()[110] as ReplicatedActor3D
	_expect(waiting.is_model_deferred() and waiting.is_drawn() and waiting.stand_in_visible(),
		"one still waiting inside the draw distance shows its stand-in")
	await _gate_and_build()
	# Four a frame within a time budget: the queue may need a frame or two more.
	for unused: int in range(4):
		await process_frame
	var remaining := 0
	for index: int in range(8):
		remaining += int((_nodes()[110 + index] as ReplicatedActor3D).is_model_deferred())
	_expect(remaining == 0, "the following frames' builds take the rest (%d left)" % remaining)


func _test_parking() -> void:
	var before := _nodes().get(101) as ReplicatedActor3D
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR, PackedByteArray([101, 0]))
	await _sync()
	_expect(not _nodes().has(101), "a removed actor leaves the table on the next pass")
	_expect(is_instance_valid(before) and not before.visible
		and before.process_mode == Node.PROCESS_MODE_DISABLED and before.collision_layer == 0,
		"its body is parked: hidden, not processing and not pickable")
	var crowd: RefCounted = _main.get("crowd")
	_expect(int(crowd.call("parked_count")) == 1, "and counted as parked")
	_put([_record(101, 511, 500)])
	await _sync()
	var after := _nodes().get(101) as ReplicatedActor3D
	_expect(after == before and after.visible and after.process_mode != Node.PROCESS_MODE_DISABLED
		and after.collision_layer == 2, "the same actor coming back wears the parked body again")
	_expect(int(crowd.call("parked_count")) == 0, "and the parking place is empty")
	# A different actor under a recycled id does not get the body.
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR, PackedByteArray([101, 0]))
	await _sync()
	var other := _record(101, 511, 500)
	other["name"] = "Someone else"
	_put([other])
	await _sync()
	_expect(_nodes().get(101) != before, "a recycled id with a different actor is built afresh")


func _test_release() -> void:
	var crowd: RefCounted = _main.get("crowd")
	_put([_record(103, 520, 500)])
	await _sync()
	await _gate_and_build()
	_expect(not (_nodes()[103] as ReplicatedActor3D).is_model_deferred(), "a near actor has a body")
	_put([_record(103, 680, 500)])
	await _sync()
	await _gate_and_build()
	_expect(not (_nodes()[103] as ReplicatedActor3D).is_model_deferred(),
		"one gate pass beyond the release radius does not give the body up")
	(crowd.get("_far_since") as Dictionary)[103] = Time.get_ticks_msec() - 60000
	await _gate_and_build()
	var released := _nodes()[103] as ReplicatedActor3D
	_expect(released.is_model_deferred() and released.get_skeleton() == null,
		"a body that has stayed far out of range is given up")


func _test_body_cap() -> void:
	var crowd: RefCounted = _main.get("crowd")
	crowd.set("body_cap", 6)
	var batch: Array = []
	for index: int in range(16):
		batch.append(_record(130 + index, 500 + 2 + index * 4, 540))
	_put(batch)
	await _sync()
	for pass_index: int in range(6):
		await _gate_and_build()
	var built := 0
	var hidden := 0
	var nearest_built := true
	for index: int in range(16):
		var actor := _nodes()[130 + index] as ReplicatedActor3D
		built += int(not actor.is_model_deferred())
		hidden += int(actor.crowd_hidden())
		if index < 4 and actor.is_model_deferred():
			nearest_built = false
	# Some earlier actors from the other tests are nearer, so the cap reaches
	# only part of this batch; what matters is that bodies stop near the cap.
	var total_bodies := int(_main.get("_built_bodies"))
	_expect(total_bodies <= 6 + 1 + 4, "the cap holds the bodies near it (%d built)" % total_bodies)
	_expect(hidden > 0, "actors past the cap keep only their map dot (%d hidden)" % hidden)
	var far := _nodes()[145] as ReplicatedActor3D
	_expect(far.crowd_hidden() and not far.stand_in_visible() and far.collision_layer == 0,
		"one past the cap shows no stand-in and cannot be clicked")
	crowd.set("body_cap", 0)
	for pass_index: int in range(6):
		await _gate_and_build()
	_expect(not is_instance_valid(far) or not far.crowd_hidden(), "without the cap it is shown again")


func _test_paused_tier() -> void:
	var actor := _nodes().get(LOCAL) as ReplicatedActor3D
	var other: ReplicatedActor3D = null
	for value: Variant in _nodes().values():
		var candidate := value as ReplicatedActor3D
		if candidate != null and candidate.actor_id != LOCAL and not candidate.is_model_deferred() \
				and candidate.animation_player != null:
			other = candidate
			break
	if not _expect(other != null, "a built remote body exists for the tier check"):
		return
	var gate := _main.get("animation_gate") as AnimationGate
	other.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	_expect(not other.model_processing() and not other.animation_player.active,
		"a paused body stops its player and its model's processing")
	other.set_animation_tier(AnimationGate.Tier.FULL, gate)
	_expect(other.model_processing() and other.animation_player.active, "and a woken one resumes both")
	other.set_animation_tier(AnimationGate.Tier.HALF, gate)
	_expect(other.get_skeleton().modifier_callback_mode_process
		== Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
		and other.animation_player.callback_mode_process
			== AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL,
		"a half-rate body steps its skeleton's modifiers with its player")
	other.set_animation_tier(AnimationGate.Tier.FULL, gate)
	_expect(other.get_skeleton().modifier_callback_mode_process
		== Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_IDLE,
		"and a full-rate one hands them back to the engine's clock")
	_expect(actor != null, "the player is present")


## The sweep's ranking: the nearest `full_rate_bodies` animate at full rate,
## the next `half_rate_bodies` at half, the rest every fourth frame; a body
## past 45 m is never ranked above half rate.
func _test_rate_ranking() -> void:
	var bodies: Array[ReplicatedActor3D] = []
	for value: Variant in _nodes().values():
		var candidate := value as ReplicatedActor3D
		if candidate != null and candidate.actor_id != LOCAL and not candidate.is_model_deferred() \
				and candidate.animation_player != null and bodies.size() < 2:
			bodies.append(candidate)
	if not _expect(bodies.size() == 2, "two built remote bodies exist for the ranking check"):
		return
	var crowd: RefCounted = _main.get("crowd")
	var saved := [crowd.get("full_rate_bodies"), crowd.get("half_rate_bodies"), crowd.get("quarter")]
	crowd.set("full_rate_bodies", 1)
	crowd.set("half_rate_bodies", 0)
	crowd.set("quarter", true)
	_main.call("_apply_crowd_full_rate", [[1.0, bodies[0], AnimationGate.Tier.FULL],
		[2.0, bodies[1], AnimationGate.Tier.FULL]])
	_expect(bodies[0].animation_tier() == AnimationGate.Tier.FULL
		and bodies[1].animation_tier() == AnimationGate.Tier.QUARTER,
		"past the full and half budgets a body is stepped at quarter rate")
	_expect(bodies[1].get_skeleton().modifier_callback_mode_process
		== Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL,
		"a quarter-rate body steps its skeleton's modifiers with its player")
	_main.call("_apply_crowd_full_rate", [[1.0, bodies[0], AnimationGate.Tier.HALF],
		[2.0, bodies[1], AnimationGate.Tier.FULL]])
	_expect(bodies[0].animation_tier() == AnimationGate.Tier.HALF,
		"a body past 45 m is not ranked above half rate")
	crowd.set("quarter", false)
	_main.call("_apply_crowd_full_rate", [[1.0, bodies[0], AnimationGate.Tier.FULL],
		[2.0, bodies[1], AnimationGate.Tier.FULL]])
	_expect(bodies[1].animation_tier() == AnimationGate.Tier.HALF,
		"without the quarter tier the rest are stepped at half rate")
	crowd.set("full_rate_bodies", saved[0])
	crowd.set("half_rate_bodies", saved[1])
	crowd.set("quarter", saved[2])
	var gate := _main.get("animation_gate") as AnimationGate
	for body: ReplicatedActor3D in bodies:
		body.set_animation_tier(AnimationGate.Tier.FULL, gate)


## The cloth budget is a hard limit: a simulating cape counts as
## CLOTH_HYSTERESIS places nearer than it is, but never adds a place.
func _test_cloth_budget() -> void:
	var bodies: Array[ReplicatedActor3D] = []
	for value: Variant in _nodes().values():
		var candidate := value as ReplicatedActor3D
		if candidate != null and candidate.actor_id != LOCAL and not candidate.is_model_deferred() \
				and bodies.size() < 3:
			bodies.append(candidate)
	if not _expect(bodies.size() == 3, "three built remote bodies exist for the cloth check"):
		return
	var crowd: RefCounted = _main.get("crowd")
	var saved: int = crowd.get("cloth_bodies")
	crowd.set("cloth_bodies", 1)
	for body: ReplicatedActor3D in bodies:
		body.set_cape_cloth_allowed(false)
	var allowed := func() -> Array:
		return bodies.map(func(body: ReplicatedActor3D) -> bool: return body.cape_cloth_allowed())
	_main.call("_apply_cloth_budget", [[1.0, bodies[0]], [2.0, bodies[1]], [3.0, bodies[2]]])
	_expect(allowed.call() == [true, false, false], "the nearest cape gets the one place")
	_main.call("_apply_cloth_budget", [[1.0, bodies[1]], [2.0, bodies[0]], [3.0, bodies[2]]])
	_expect(allowed.call() == [true, false, false],
		"a simulating cape keeps its place when another comes a little nearer")
	# The third body stands in for four capes between them.
	_main.call("_apply_cloth_budget", [[1.0, bodies[1]], [2.0, bodies[2]], [3.0, bodies[2]],
		[4.0, bodies[2]], [5.0, bodies[2]], [6.0, bodies[0]]])
	_expect(allowed.call() == [false, true, false],
		"and gives it up once it falls the hysteresis behind")
	crowd.set("cloth_bodies", 2)
	_main.call("_apply_cloth_budget", [[1.0, bodies[2]], [2.0, bodies[0]], [3.0, bodies[1]]])
	var simulating := 0
	for flag: bool in allowed.call():
		simulating += int(flag)
	_expect(simulating == 2, "never more capes than the budget (%d)" % simulating)
	crowd.set("cloth_bodies", saved)
	for body: ReplicatedActor3D in bodies:
		body.set_cape_cloth_allowed(true)


func _test_bulk_removal() -> void:
	var count_before := _nodes().size()
	_expect(count_before > 3, "the table holds the earlier actors")
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.KILL_ALL_ACTORS, PackedByteArray())
	await _sync()
	_expect(_nodes().is_empty(), "KILL_ALL_ACTORS takes every node away, change set or not (%d left)" % _nodes().size())
	_main.queue_free()
	await process_frame


func ACTOR_SPAWN_BUDGET() -> int:
	return int((_main.get_script() as Script).get_script_constant_map().get("ACTOR_SPAWN_BUDGET", 4))


func _expect(value: bool, label: String) -> bool:
	if value:
		print("PASS: ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
	return value

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
const MEMORY := preload("res://src/runtime/memory_budgets.gd")
const LOCAL := 100
const HUMANOID_KIT := {0: 114, 1: 106, 3: 117, 4: 171, 5: 184, 6: 192}

var failures := 0
var _main: Control
var _app_state: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_test_policy_parsing()
	_test_quality_caps()
	_test_overhead_pass()
	_test_effect_budget()
	_test_park_pool_by_class()
	_test_park_expiry_clock()
	var main_script := load("res://src/app/main.gd") as GDScript
	if not _expect(main_script != null and main_script.can_instantiate(), "main.gd compiles"):
		quit(failures)
		return
	await _set_up()
	await _test_lazy_bodies()
	await _test_parking()
	await _test_parked_body_paused()
	await _test_park_expiry_on_gate()
	await _test_park_expiry_keeps_shown_assets()
	await _test_release()
	await _test_body_cap()
	_test_player_settings()
	_test_quality_body_cap()
	await _test_paused_tier()
	_test_rate_ranking()
	_test_cloth_budget()
	await _test_overhead_cap()
	await _test_bulk_removal()
	print("crowd presentation tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)


func _test_policy_parsing() -> void:
	var policy: RefCounted = CROWD.new()
	policy.call("configure", "")
	_expect(policy.lazy and policy.gate and policy.effects and policy.park
		and policy.body_cap == CROWD.BODY_CAP_DEFAULT and policy.cloth_bodies == CROWD.CLOTH_BODIES,
		"an empty setting is the full crowd presentation, with the default cap and cloth budget")
	policy.call("set_player_budgets", 90, 3)
	_expect(policy.body_cap == 90 and policy.cloth_bodies == 3,
		"the player's crowd settings set the cap and the cloth budget")
	policy.call("configure", "", "0", "cloth=12")
	policy.call("set_player_budgets", 90, 3)
	_expect(policy.body_cap == 0 and policy.cloth_bodies == 12,
		"a benchmark's environment keeps its own cap (0 = off) and cloth budget over the player's")
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


## The Low actor tier's crowd caps (LAT-L5): the body cap follows the graphics
## quality until the player picks a number, a forced cap wins over both, and
## Low caps the overhead banners at 24.
func _test_quality_caps() -> void:
	var policy: RefCounted = CROWD.new()
	policy.call("configure", "")
	_expect(policy.body_cap_auto and policy.body_cap == 160 and policy.overhead_cap == 0,
		"a fresh policy follows the quality, which starts High: 160 bodies, no banner cap")
	policy.call("set_quality", 0)
	_expect(policy.body_cap == 60 and policy.overhead_cap == 24 and policy.quality_body_cap() == 60,
		"at Low it draws 60 bodies and 24 banners")
	policy.call("set_quality", 1)
	_expect(policy.body_cap == 160 and policy.overhead_cap == 0, "Medium is unchanged: 160, no banner cap")
	policy.call("set_quality", 2)
	_expect(policy.body_cap == 160 and policy.overhead_cap == 0, "and so is High")
	policy.call("set_quality", 0)
	policy.call("set_quality", 2)
	_expect(policy.body_cap == 160, "switching Low then High in one session restores 160")
	policy.call("set_player_budgets", 90, 3)
	policy.call("set_quality", 0)
	_expect(not policy.body_cap_auto and policy.body_cap == 90,
		"a number the player chose stays at every quality")
	policy.call("set_player_budgets", 90, 3, true)
	_expect(policy.body_cap_auto and policy.body_cap == 60 and policy.cloth_bodies == 3,
		"following the quality again gives Low's 60, and the capes are still the player's")
	policy.call("set_quality", 2)
	_expect(policy.body_cap == 160, "and High's 160")
	policy.call("configure", "", "120", "banners=5")
	policy.call("set_quality", 0)
	policy.call("set_player_budgets", 90, 3, true)
	_expect(policy.body_cap == 120 and policy.overhead_cap == 5,
		"RABBITLANDS_CROWD_BODY_CAP and a banners= tuning win over the quality and the setting")
	policy.call("set_quality", 2)
	_expect(policy.body_cap == 120 and policy.overhead_cap == 5, "at every quality")
	policy.call("configure", "", "", "banners=0")
	policy.call("set_quality", 0)
	_expect(policy.overhead_cap == 0 and policy.body_cap == 60, "banners=0 measures Low without the banner cap")
	var described: Dictionary = policy.call("describe")
	_expect(described.get("bodyCapAuto") == true and described.get("overheadCap") == 0
		and described.has("overheadsShown"), "the policy report says whether the cap follows the quality")
	# The saved-settings migration (low-actor-tier.md L5): a saved switch
	# decides; before it existed 160 or nothing followed the quality, as did
	# the first-run low tier's 60, and any other number was the player's.
	var cases := [
		[null, null, "", true, "nothing saved follows the quality"],
		[null, 160, "", true, "the old default 160 follows the quality"],
		[null, 160.0, "high", true, "160 read back as a float follows it too"],
		[null, 60, "low", true, "the first-run low tier's 60 follows the quality"],
		[null, 60, "", false, "60 the player chose (the old Performance preset) stays 60"],
		[null, 60, "high", false, "60 on a profile seeded High stays 60"],
		[null, 90, "low", false, "any other number is the player's own"],
		[null, "lots", "", true, "a value that is not a number reads as the default"],
		[true, 90, "", true, "a saved switch on decides"],
		[false, 160, "low", false, "a saved switch off decides"],
	]
	for case: Array in cases:
		_expect(CROWD.follows_quality(case[0], case[1], str(case[2])) == bool(case[3]), str(case[4]))


## The overhead banner cap's bookkeeping, as main.gd's declutter pass drives
## it: the cap counts shown banners in the pass's order, exempt ones are never
## capped or counted, and a banner shown last pass sorts 2 m nearer.
func _test_overhead_pass() -> void:
	var policy: RefCounted = CROWD.new()
	policy.call("configure", "")
	_expect(is_equal_approx(float(policy.call("overhead_sort_distance", 7, 100.0)), 100.0),
		"without a cap the sort distance is the distance")
	policy.call("set_quality", 0)
	policy.call("begin_overhead_pass")
	var shown: Array[int] = []
	var capped: Array[int] = []
	for id: int in range(30):
		var exempt := id == 27
		if policy.call("overhead_capped", exempt):
			capped.append(id)
			continue
		shown.append(id)
		if not exempt:
			policy.call("count_overhead", id)
	policy.call("end_overhead_pass")
	_expect(shown.size() == 25 and shown.has(27) and capped.size() == 5 and capped[0] == 24
		and int(policy.call("overheads_shown")) == 24,
		"the 25th banner and later are capped; the exempt one shows and is not counted (%d shown)" % shown.size())
	var nearer := float(policy.call("overhead_sort_distance", 5, 100.0))
	_expect(is_equal_approx(nearer, 64.0), "a banner shown last pass sorts 2 m nearer (10 m -> 8 m: %f)" % nearer)
	_expect(is_equal_approx(float(policy.call("overhead_sort_distance", 26, 100.0)), 100.0),
		"one that was capped sorts where it is")
	_expect(is_equal_approx(float(policy.call("overhead_sort_distance", 5, 1.0)), 0.0),
		"and never nearer than the focus")
	# The 24th shown (10 m) and the first capped (9 m): the shown one keeps
	# its place until the other is more than 2 m nearer.
	_expect(float(policy.call("overhead_sort_distance", 23, 100.0)) < float(policy.call("overhead_sort_distance", 24, 81.0)),
		"a shown banner keeps its place against one up to 2 m nearer")
	_expect(float(policy.call("overhead_sort_distance", 23, 100.0)) > float(policy.call("overhead_sort_distance", 24, 49.0)),
		"and yields to one more than 2 m nearer")
	policy.call("set_quality", 2)
	_expect(int(policy.call("overheads_shown")) == 0
		and is_equal_approx(float(policy.call("overhead_sort_distance", 5, 100.0)), 100.0),
		"leaving Low forgets the shown banners")


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


## The park pool's size follows the machine's memory class (memory-classes
## M7a): 16 bodies on a small machine, today's PARK_LIMIT (48) on medium and
## large ones. `configure` reads the class, so one policy follows a change.
func _test_park_pool_by_class() -> void:
	_expect(CROWD.PARK_LIMIT == 48 and CROWD.park_limit_for(MEMORY.SMALL) == 16
		and CROWD.park_limit_for(MEMORY.MEDIUM) == CROWD.PARK_LIMIT
		and CROWD.park_limit_for(MEMORY.LARGE) == CROWD.PARK_LIMIT,
		"the pool holds 16 bodies on a small machine and 48 on medium and large ones")
	_expect(CROWD.park_limit_for("unknown") == CROWD.PARK_LIMIT,
		"a class the table does not know reads medium's")
	_expect(int(CROWD.new().park_limit) == CROWD.PARK_LIMIT,
		"an unconfigured policy keeps today's 48")
	var policy: RefCounted = CROWD.new()
	var cases := [[MEMORY.SMALL, 16], [MEMORY.MEDIUM, 48], [MEMORY.LARGE, 48], [MEMORY.SMALL, 16]]
	for case: Array in cases:
		MEMORY.override_for_tests(str(case[0]))
		policy.call("configure", "")
		var limit := int(case[1])
		var nodes: Array[Node3D] = []
		var accepted := 0
		for index: int in range(limit + 1):
			var node := Node3D.new()
			nodes.append(node)
			accepted += int(policy.call("park_node", 1000 + index, node, "key", 0))
		_expect(int(policy.park_limit) == limit and accepted == limit
			and int(policy.call("parked_count")) == limit
			and (policy.call("describe") as Dictionary).get("parkLimit") == limit,
			"as %s: %d bodies are parked and the next one is refused" % [case[0], limit])
		policy.call("clear_parked")
		for node: Node3D in nodes:
			if is_instance_valid(node) and not node.is_queued_for_deletion():
				node.free()
	policy.call("configure", "legacy")
	var refused := Node3D.new()
	_expect(not bool(policy.call("park_node", 1, refused, "key", 0)),
		"with parking off nothing is parked, whatever the class")
	refused.free()
	MEMORY.reset()


## Parked bodies are freed once PARK_MSEC is up by a clock the gate pass asks
## every frame (`expire_parked_due`) but which looks at most every
## PARK_EXPIRY_PERIOD_MSEC.
func _test_park_expiry_clock() -> void:
	var policy: RefCounted = CROWD.new()
	policy.call("configure", "")
	var first := Node3D.new()
	var second := Node3D.new()
	policy.call("park_node", 1, first, "a", 0)
	policy.call("park_node", 2, second, "b", 1000)
	var period: int = CROWD.PARK_EXPIRY_PERIOD_MSEC
	var look: int = CROWD.PARK_MSEC - period + 100
	_expect(period == 500 and int(policy.call("expire_parked_due", look)) == 0
		and int(policy.call("parked_count")) == 2, "nothing is freed before its time")
	_expect(int(policy.call("expire_parked_due", CROWD.PARK_MSEC)) == 0
		and int(policy.call("parked_count")) == 2 and not first.is_queued_for_deletion(),
		"a body whose time is up waits for the clock's next look, at most %d ms" % period)
	_expect(int(policy.call("expire_parked_due", look + period)) == 1
		and first.is_queued_for_deletion() and not second.is_queued_for_deletion()
		and policy.call("parked_actor_ids") == [2], "the next look frees it, and only it")
	_expect(int(policy.call("expire_parked_due", 1000 + CROWD.PARK_MSEC)) == 1
		and second.is_queued_for_deletion() and int(policy.call("parked_count")) == 0,
		"and a look once the second one's time is up frees that one")
	var third := Node3D.new()
	policy.call("park_node", 3, third, "c", 0)
	_expect(int(policy.call("expire_parked", CROWD.PARK_MSEC)) == 1 and third.is_queued_for_deletion(),
		"expire_parked itself frees whatever is due and says how many")
	var fourth := Node3D.new()
	policy.call("park_node", 4, fourth, "d", 0)
	policy.call("clear_parked")
	_expect(int(policy.get("_park_expiry_at")) == 0 and fourth.is_queued_for_deletion(),
		"clearing the pool frees its bodies and resets the clock")


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


func _wait_for_bodies(ids: Array) -> void:
	for unused: int in range(90):
		var waiting := false
		for id: int in ids:
			var actor := _nodes().get(id) as ReplicatedActor3D
			if actor == null or actor.is_model_deferred():
				waiting = true
				break
		if not waiting:
			return
		await _gate_and_build()


## Arrivals get their nodes within the spawn budget, over as many passes as
## that takes.
func _wait_for_nodes(ids: Array) -> void:
	await _sync()
	for unused: int in range(60):
		if _has_nodes(ids):
			return
		await _sync()


func _has_nodes(ids: Array) -> bool:
	for id: Variant in ids:
		if not _nodes().has(int(id)):
			return false
	return true


func _put(records: Array) -> void:
	var actors: Dictionary = (_app_state.get("actors") as Dictionary)
	for record: Dictionary in records:
		actors[int(record.actor_id)] = record
		_app_state.call("mark_actor_changed", int(record.actor_id))


func _test_lazy_bodies() -> void:
	_put([_record(LOCAL, 500, 500), _record(101, 510, 500), _record(102, 700, 500, false)])
	await _sync()
	await _wait_for_bodies([101])
	var nodes := _nodes()
	var near := nodes.get(101) as ReplicatedActor3D
	var far := nodes.get(102) as ReplicatedActor3D
	if not _expect(near != null and far != null, "both arrivals get a node on the pass they arrive"):
		return
	_expect(not (nodes[LOCAL] as ReplicatedActor3D).is_model_deferred(), "the player's own body is built at once")
	_expect(not near.is_model_deferred() and near.get_node_or_null("NativeModel") != null,
		"an actor 10 m away receives its body within bounded successive frames")
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
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	far = _nodes().get(102) as ReplicatedActor3D
	_expect(far.is_model_deferred(), "presenting a record does not build its body by itself")
	var deferred_at: Vector3 = far.global_position
	await _wait_for_bodies([102])
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
	_main.call("_sync_world", _app_state.call("take_changed_actors"))
	var built_ids: Array[int] = []
	for index: int in range(8):
		if not (_nodes()[110 + index] as ReplicatedActor3D).is_model_deferred():
			built_ids.append(110 + index)
	_expect(built_ids.size() <= ACTOR_SPAWN_BUDGET(),
		"one process frame stays within the count allowance (%d of 8)" % built_ids.size())
	var expected: Array = [117, 116, 115, 114, 113, 112, 111, 110].slice(0, built_ids.size())
	expected.sort()
	_expect(built_ids == expected, "and any bodies admitted are the nearest ones: %s" % [built_ids])
	var waiting := _nodes()[110] as ReplicatedActor3D
	_expect(waiting.is_model_deferred() and waiting.is_drawn() and waiting.stand_in_visible(),
		"one still waiting inside the draw distance shows its stand-in")
	await _wait_for_bodies([110, 111, 112, 113, 114, 115, 116, 117])
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


## A parked body leaves the gate's stepped groups and is stepped no more; a
## revived one animates again.
func _test_parked_body_paused() -> void:
	var gate := _main.get("animation_gate") as AnimationGate
	var body: ReplicatedActor3D = null
	var body_id := -1
	for raw_id: Variant in _nodes():
		var candidate := _nodes()[raw_id] as ReplicatedActor3D
		if candidate != null and int(raw_id) != LOCAL and not candidate.is_model_deferred() \
				and candidate.animation_player != null:
			body = candidate
			body_id = int(raw_id)
			break
	if not _expect(body != null, "a built remote body exists for the parked-body check"):
		return
	body.set_animation_tier(AnimationGate.Tier.QUARTER, gate)
	var stepped_before := gate.quarter_rate_count()
	var record: Dictionary = (_app_state.get("actors") as Dictionary)[body_id]
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR,
		PackedByteArray([body_id & 0xff, (body_id >> 8) & 0xff]))
	await _sync()
	_expect(gate.quarter_rate_count() == stepped_before - 1
		and body.animation_tier() == AnimationGate.Tier.PAUSED
		and not body.animation_player.active,
		"a parked body is paused and no longer stepped by the gate")
	_put([record])
	await _sync()
	_expect(_nodes().get(body_id) == body and body.animation_tier() != AnimationGate.Tier.PAUSED
		and body.animation_player.active, "the revived body animates again")


## The gate pass frees a parked body once its time is up without any change
## to the actor list (memory-classes M7a): a crowd that has gone sends nothing
## more, and its bodies used to stay parked until the next arrival.
func _test_park_expiry_on_gate() -> void:
	var crowd: RefCounted = _main.get("crowd")
	_expect(int(crowd.get("park_limit")) == CROWD.park_limit_for(MEMORY.memory_class()),
		"Main's park pool is this session's memory class's (%s: %d bodies)"
		% [MEMORY.memory_class(), int(crowd.get("park_limit"))])
	_put([_record(150, 512, 500)])
	await _wait_for_nodes([150])
	await _wait_for_bodies([150])
	var body := _nodes().get(150) as ReplicatedActor3D
	if not _expect(body != null and not body.is_model_deferred(), "a built body to park for the expiry check"):
		return
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR, PackedByteArray([150, 0]))
	await _sync()
	if not _expect(150 in (crowd.call("parked_actor_ids") as Array) and is_instance_valid(body)
			and not body.is_queued_for_deletion(), "its body is parked when the server removes it"):
		return
	# Only the gate pass runs from here on: no `_sync_world`, no actor change.
	crowd.set("_park_expiry_at", 0)
	_main.call("_update_animation_gate", 0.0)
	_expect(150 in (crowd.call("parked_actor_ids") as Array) and not body.is_queued_for_deletion(),
		"a gate pass inside its %d ms keeps it parked" % CROWD.PARK_MSEC)
	((crowd.get("_parked") as Dictionary)[150] as Dictionary)["until"] = Time.get_ticks_msec() - 1
	crowd.set("_park_expiry_at", Time.get_ticks_msec() + 60000)
	_main.call("_update_animation_gate", 0.0)
	_expect(150 in (crowd.call("parked_actor_ids") as Array) and not body.is_queued_for_deletion(),
		"between the clock's looks (every %d ms) the gate leaves the pool alone"
		% CROWD.PARK_EXPIRY_PERIOD_MSEC)
	crowd.set("_park_expiry_at", 0)
	_main.call("_update_animation_gate", 0.0)
	_expect(not (150 in (crowd.call("parked_actor_ids") as Array)) and body.is_queued_for_deletion(),
		"once its time is up the clock's next look in the gate pass frees it, with no world sync")
	await process_frame
	_expect(not is_instance_valid(body), "and the body is gone after the frame")


## Records what the gate's expiry asks the browser build's actor files to keep
## (browser_actor_assets.gd `prune`); only the browser build has one.
class PruneRecorder extends RefCounted:
	var calls := 0
	var kept: Array = []

	func prune(_live: Dictionary, parked: Array = []) -> void:
		calls += 1
		kept = parked.duplicate()


## On the browser build the gate's expiry also lets go of the files of actors
## that are gone. An actor AppState has just removed keeps its node until the
## deferred world sync parks or frees it, so the expiry keeps that actor's
## files: only the expired body's are let go.
func _test_park_expiry_keeps_shown_assets() -> void:
	var crowd: RefCounted = _main.get("crowd")
	_put([_record(151, 513, 500), _record(152, 514, 500)])
	await _wait_for_nodes([151, 152])
	await _wait_for_bodies([151, 152])
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR, PackedByteArray([151, 0]))
	await _sync()
	var shown := _nodes().get(152) as ReplicatedActor3D
	if not _expect(151 in (crowd.call("parked_actor_ids") as Array) and shown != null
			and not shown.is_model_deferred(), "a parked body to expire beside a shown one"):
		return
	((crowd.get("_parked") as Dictionary)[151] as Dictionary)["until"] = Time.get_ticks_msec() - 1
	# No world sync before the gate pass: AppState no longer has 152, but its
	# node is still on screen.
	_app_state.call("_on_packet", EloriaProtocol.ServerMessage.REMOVE_ACTOR, PackedByteArray([152, 0]))
	var recorder := PruneRecorder.new()
	_main.set("_browser_actor_assets", recorder)
	crowd.set("_park_expiry_at", 0)
	_main.call("_update_animation_gate", 0.0)
	_main.set("_browser_actor_assets", null)
	_expect(recorder.calls == 1 and not (151 in recorder.kept) and 152 in recorder.kept
		and not (_app_state.get("actors") as Dictionary).has(152)
		and is_instance_valid(shown) and not shown.is_queued_for_deletion(),
		"the expiry lets the expired body's files go and keeps those of a body still on screen")
	await _sync()
	if 152 in (crowd.call("parked_actor_ids") as Array):
		((crowd.get("_parked") as Dictionary)[152] as Dictionary)["until"] = 0
		crowd.set("_park_expiry_at", 0)
		_main.call("_update_animation_gate", 0.0)
	await process_frame


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
	var ids: Array = []
	for index: int in range(16):
		batch.append(_record(130 + index, 500 + 2 + index * 4, 540))
		ids.append(130 + index)
	_put(batch)
	# Every arrival gets its node within the spawn budget's passes first;
	# indexing a node that has not arrived yet stopped this test early.
	await _wait_for_nodes(ids)
	if not _expect(_has_nodes(ids), "every capped arrival has a node"):
		return
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


## The two Graphics settings reach the crowd presentation, within their ranges.
func _test_player_settings() -> void:
	var crowd: RefCounted = _main.get("crowd")
	var panel := (_main.get("settings_window") as Control).get("panel") as Control
	var bodies := panel.find_child("crowd_bodies", true, false) as HSlider
	var capes := panel.find_child("swaying_capes", true, false) as HSlider
	_expect(bodies != null and capes != null and int(bodies.value) == 160 and int(capes.value) == 8,
		"Graphics offers both crowd settings, at 160 characters and 8 capes by default (%s, %s)" % [
			str(bodies.value) if bodies != null else "missing", str(capes.value) if capes != null else "missing"])
	_main.call("_set_crowd_settings", 120, 4)
	_expect(int(crowd.get("body_cap")) == 120 and int(crowd.get("cloth_bodies")) == 4,
		"a changed setting reaches the crowd presentation")
	_main.call("_set_crowd_settings", 5, 99)
	_expect(int(crowd.get("body_cap")) == 40 and int(crowd.get("cloth_bodies")) == 32,
		"settings are held to their sliders' ranges")
	_main.call("_set_crowd_settings", 160, 8)
	crowd.set("body_cap", 0)


## LAT-L5 in the client: the crowd count follows the graphics quality until
## the player picks a number, the server is told the count that is drawn, and
## the window shows both.
func _test_quality_body_cap() -> void:
	var crowd: RefCounted = _main.get("crowd")
	var network: Node = root.get_node("Network")
	var panel := (_main.get("settings_window") as Control).get("panel") as Control
	var bodies := panel.find_child("crowd_bodies", true, false) as HSlider
	var capes := panel.find_child("swaying_capes", true, false) as HSlider
	var follow := panel.find_child("crowd_bodies_auto", true, false) as CheckBox
	if not _expect(bodies != null and capes != null and follow != null,
			"Graphics has a Follow graphics quality box under the crowd count"):
		return
	var saved_quality := LookProfile.player_quality()
	_main.call("_on_client_setting_changed", "Graphics", "crowd_bodies_auto", true)
	_expect(bool(_main.get("_crowd_bodies_auto")) and follow.button_pressed and not bodies.editable,
		"with the box on the count cannot be moved")
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	_main.call("_apply_graphics_quality")
	_expect(int(crowd.get("body_cap")) == 60 and int(_main.get("_crowd_bodies")) == 60
		and int(bodies.value) == 60 and int(network.get("declared_actor_cap")) == 60,
		"at Low it draws 60, shows 60 and asks the server for 60 (%s, %s, %s)" % [
			crowd.get("body_cap"), bodies.value, network.get("declared_actor_cap")])
	_expect(int(crowd.get("overhead_cap")) == 24 and not capes.editable,
		"Low caps the banners at 24 and greys out the swaying capes")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	_main.call("_apply_graphics_quality")
	_expect(int(crowd.get("body_cap")) == 160 and int(bodies.value) == 160
		and int(network.get("declared_actor_cap")) == 160 and int(crowd.get("overhead_cap")) == 0
		and capes.editable, "High in the same session restores 160, no banner cap, and the capes")
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	_main.call("_apply_graphics_quality")
	follow.button_pressed = false
	_expect(not bool(_main.get("_crowd_bodies_auto")) and bodies.editable
		and int(crowd.get("body_cap")) == 60 and int(bodies.value) == 60,
		"clearing the box keeps the count it showed, and the slider can move")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	_main.call("_apply_graphics_quality")
	_expect(int(crowd.get("body_cap")) == 60 and int(network.get("declared_actor_cap")) == 60,
		"a number stays at every quality, and is what the server is asked for")
	bodies.value = 90
	_expect(int(crowd.get("body_cap")) == 90 and int(network.get("declared_actor_cap")) == 90,
		"moving the slider sets the count")
	follow.button_pressed = true
	_expect(int(crowd.get("body_cap")) == 160 and int(bodies.value) == 160 and not bodies.editable,
		"turning the box back on shows High's 160 again")
	crowd.set("body_cap_forced", true)
	crowd.set("body_cap", 0)
	_main.call("_sync_declared_actor_cap")
	_expect(int(network.get("declared_actor_cap")) == 160,
		"a benchmark's forced no-cap asks the server for the most")
	crowd.set("body_cap", 25)
	_main.call("_sync_declared_actor_cap")
	_expect(int(network.get("declared_actor_cap")) == 25, "and a forced cap is what is drawn and declared")
	crowd.set("body_cap_forced", false)
	_main.call("_set_crowd_settings", 160, 8, true)
	LookProfile.set_player_quality(saved_quality)
	_main.call("_apply_graphics_quality")
	crowd.set("body_cap", 0)


## The Low banner cap in main.gd's declutter pass: past the cap the nearest
## banners show and the rest are hidden, while the target, the selection and
## the party show whatever their place. Uses a small cap so the fixture's
## banners fit the screen without overlapping one another.
func _test_overhead_cap() -> void:
	var crowd: RefCounted = _main.get("crowd")
	var camera: Camera3D = _main.get("gameplay_camera")
	var adapter: Object = _main.get("adapter")
	var main_script := _main.get_script() as GDScript
	# Only the player and the banners placed here: the earlier tests' actors
	# leave, so the count below is the placed banners' alone.
	var actors := _app_state.get("actors") as Dictionary
	for raw: Variant in actors.keys():
		if int(raw) != LOCAL:
			actors.erase(raw)
			_app_state.call("mark_actor_changed", int(raw))
	await _sync()
	var taken: Array[Rect2] = []
	var view := Rect2(Vector2.ZERO, Vector2((_main.get("main_viewport") as SubViewport).size)).grow(-40.0)
	var placed: Array[Vector2i] = []
	for dy: int in range(-24, 25, 2):
		for dx: int in range(-24, 25, 2):
			if placed.size() >= 12 or (dx == 0 and dy == 0):
				continue
			var tile := Vector2i(500 + dx, 500 + dy)
			var point: Vector3 = adapter.call("tile_center", tile.x, tile.y) + Vector3.UP * 2.2
			if camera.is_position_behind(point):
				continue
			var screen := camera.unproject_position(point)
			var rect: Rect2 = main_script.call("overhead_block_rect", screen,
				"Crowd %d" % (300 + placed.size())).grow(24.0)
			if not view.encloses(rect):
				continue
			var clear := true
			for other: Rect2 in taken:
				if other.intersects(rect):
					clear = false
					break
			if clear:
				taken.append(rect)
				placed.append(tile)
	if not _expect(placed.size() >= 10, "the fixture finds room for ten separate banners (%d)" % placed.size()):
		return
	var batch: Array = []
	var ids: Array[int] = []
	for index: int in placed.size():
		batch.append(_record(300 + index, placed[index].x, placed[index].y))
		ids.append(300 + index)
	_put(batch)
	await _wait_for_nodes(ids)
	await _gate_and_build()
	await _gate_and_build()
	if not _expect(_has_nodes(ids), "every placed actor has a node"):
		return
	# The cap counts in the pass's order, nearest the camera focus first; the
	# three exempt actors are the farthest of the batch.
	var focus: Vector3 = (_main.get("camera_rig") as Node).get("focus")
	ids.sort_custom(func(a: int, b: int) -> bool:
		var near_a := (_nodes()[a] as Node3D).global_position.distance_squared_to(focus)
		var near_b := (_nodes()[b] as Node3D).global_position.distance_squared_to(focus)
		return near_a < near_b if near_a != near_b else a < b)
	var target: int = ids[-1]
	var selected: int = ids[-2]
	var partner: int = ids[-3]
	var saved_party: Dictionary = _app_state.get("party")
	_app_state.set("selected_actor_id", selected)
	_app_state.set("party", {"in_party": true, "invited_by": "", "invite_seconds": 0,
		"members": [{"name": "Crowd %d" % partner, "is_self": false},
			{"name": "Crowd %d" % LOCAL, "is_self": true}]})
	var shown := func(id: int) -> bool:
		var actor := _nodes().get(id) as ReplicatedActor3D
		actor.set_overhead_fade(1.0)
		return actor.call("_overhead_shown")
	var count_shown := func() -> int:
		var total := 0
		for id: int in ids:
			total += int(shown.call(id))
		return total
	crowd.set("overhead_cap", 0)
	for id: int in ids:
		(_nodes()[id] as ReplicatedActor3D).set_overhead_fade(1.0)
	_main.call("_declutter_actor_overheads", target)
	var uncapped: int = count_shown.call()
	_expect(uncapped == ids.size(), "without a cap every placed banner shows (%d of %d)" % [uncapped, ids.size()])
	crowd.set("overhead_cap", 4)
	_main.call("_declutter_actor_overheads", target)
	var capped_shown: int = count_shown.call()
	_expect(capped_shown == 4 + 3, "a cap of four shows the four nearest, plus the three exempt (%d)" % capped_shown)
	_expect(shown.call(target) and shown.call(selected) and shown.call(partner),
		"the target, the selection and a party member show though they are the farthest")
	var nearest_shown := true
	for index: int in 4:
		nearest_shown = nearest_shown and shown.call(ids[index])
	_expect(nearest_shown and not shown.call(ids[4]) and not shown.call(ids[ids.size() - 4])
		and (_nodes()[ids[4]] as ReplicatedActor3D).overhead_crowded(),
		"the four nearest show and the fifth on is hidden as crowded")
	_expect(int(crowd.call("overheads_shown")) == 4,
		"the pass counted exactly the cap (%d)" % int(crowd.call("overheads_shown")))
	crowd.set("overhead_cap", 0)
	_main.call("_declutter_actor_overheads", target)
	_expect(count_shown.call() == ids.size(), "without the cap they all show again")
	_app_state.set("selected_actor_id", -1)
	_app_state.set("party", saved_party)
	# Hysteresis, with two creatures under a cap of one: a creature's banner
	# never hides another creature's, so only the cap decides between them.
	# The players above are faded out of the pass meanwhile.
	_put([_record(400, 506, 500, false), _record(401, 494, 500, false)])
	await _wait_for_nodes([400, 401])
	await _gate_and_build()
	var near := _nodes().get(400) as ReplicatedActor3D
	var far := _nodes().get(401) as ReplicatedActor3D
	if not _expect(near != null and far != null, "two creatures stand in for the cap's boundary"):
		return
	for id: int in ids:
		(_nodes()[id] as ReplicatedActor3D).set_overhead_fade(0.0)
	var place := func(actor: ReplicatedActor3D, side: float, metres: float) -> void:
		actor.global_position = focus + Vector3(side, 0.0, 0.25).normalized() * metres
		actor.set_overhead_fade(1.0)
	var both := func() -> Array:
		return [bool(near.call("_overhead_shown")), bool(far.call("_overhead_shown"))]
	crowd.set("overhead_cap", 0)
	place.call(near, 1.0, 5.0)
	place.call(far, -1.0, 7.0)
	_main.call("_declutter_actor_overheads", -1)
	if not _expect(both.call() == [true, true], "both creatures' banners show without a cap"):
		return
	crowd.set("overhead_cap", 1)
	_main.call("_declutter_actor_overheads", -1)
	var first: Array = both.call()
	# The shown banner moves 1 m past the other: inside the 2 m band it stays.
	place.call(near, 1.0, 8.0)
	_main.call("_declutter_actor_overheads", -1)
	var inside: Array = both.call()
	# 3 m past it: the other is nearer by more than the band and takes over.
	place.call(near, 1.0, 10.0)
	_main.call("_declutter_actor_overheads", -1)
	var outside: Array = both.call()
	_expect(first == [true, false] and inside == [true, false] and outside == [false, true],
		"the shown banner keeps its place 1 m behind the next and yields 3 m behind (%s %s %s)" % [
			first, inside, outside])
	crowd.set("overhead_cap", 0)


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

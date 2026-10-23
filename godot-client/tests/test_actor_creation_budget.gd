extends SceneTree
## Deterministic state/ownership tests. No actor assets or authored herd needed.
var failures := 0

class TrackedPopulation extends AmbientPopulation:
	var applied: Array[int] = []
	var pending := 0
	func apply_render_quality(level: int) -> void:
		applied.append(level)
	func pending_creation_count() -> int:
		return pending

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var script := load("res://src/app/main.gd") as GDScript
	if not _expect(script != null and script.can_instantiate(), "Main compiles"):
		quit(failures)
		return
	var app := root.get_node("/root/AppState")
	var old_local: int = app.local_actor_id
	var old_selected: int = app.selected_actor_id
	var old_actors: Dictionary = app.actors
	var old_combat: Dictionary = app.combat_state
	app.local_actor_id = 1
	app.selected_actor_id = 2
	app.actors = {1: {"aiming_at": 3}}
	app.combat_state = {}
	var main: Variant = script.new()
	# The two sites use the same counters even across repeated deferred flushes.
	for id: int in [100, 101]:
		_expect(main.call("_actor_creation_may_start", id, 10), "initial body admitted")
		main.call("_record_actor_creation", id, 1000, 10)
	for id: int in [102, 103]:
		_expect(main.call("_actor_creation_may_start", id, 10), "deferred promotion shares remaining slots")
		main.call("_record_actor_creation", id, 1000, 10)
	_expect(not main.call("_actor_creation_may_start", 104, 10), "same process frame cannot receive a second count allowance")
	for id: int in [1, 2, 3]:
		_expect(main.call("_actor_creation_may_start", id, 10), "player/selection/combat target remain prioritized")
		main.call("_record_actor_creation", id, 1000, 10)
		_expect(not main.call("_actor_creation_may_start", id, 10), "a critical id cannot repeatedly bypass the exhausted allowance")
	app.selected_actor_id = 4
	_expect(not main.call("_actor_creation_may_start", 4, 10), "changing selection cannot add unbounded critical bypasses in one frame")
	app.selected_actor_id = 2
	var status: Dictionary = main.call("actor_creation_budget_snapshot", 10)
	_expect(status.bodiesThisFrame == 7 and status.totals.priorityBypasses == 3,
		"bounded critical exceptions are counted, not hidden in ordinary budget")
	_expect(status.totals.framesOverBudget == 1, "frame overrun counted only once")
	_expect(main.call("_actor_creation_may_start", 104, 11), "the next process frame receives fresh slots")
	main.call("_record_actor_creation", 104, 7000, 11)
	_expect(not main.call("_actor_creation_may_start", 105, 11), "one indivisible overrun stops further ordinary builds")
	status = main.call("actor_creation_budget_snapshot", 11)
	_expect(status.totals.atomicOverruns == 1 and status.totals.maximumAtomicUsec == 7000,
		"atomic overrun is measured honestly")
	# Elapsed time can bind before the count does.
	main.call("_record_actor_creation", 106, 4000, 12)
	main.call("_record_actor_creation", 107, 2000, 12)
	_expect(not main.call("_actor_creation_may_start", 108, 12), "elapsed body work is shared across both creation paths")
	main.crowd.configure("legacy")
	_expect(main.call("_actor_creation_may_start", 109, 13), "legacy mode retains body creation with a fresh bounded allowance")
	_expect(main.call("_actor_arrival_priority", 1) < main.call("_actor_arrival_priority", 2)
		and main.call("_actor_arrival_priority", 2) < main.call("_actor_arrival_priority", 3)
		and main.call("_actor_arrival_priority", 3) < main.call("_actor_arrival_priority", 100),
		"critical arrivals sort before ordinary distance ranks")
	_test_denied_replacement(main, app)
	_test_resident_quality(main)
	main.free()
	app.local_actor_id = old_local
	app.selected_actor_id = old_selected
	app.actors = old_actors
	app.combat_state = old_combat
	print("actor creation budget tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _test_denied_replacement(main: Variant, app: Node) -> void:
	# A denied rebuild must preserve the original visible node and body census.
	# The budget gate is reached before configure(), so no actor assets load.
	var previous := ReplicatedActor3D.new()
	previous.visible = true
	previous.collision_layer = 2
	main.adapter = CoordinateAdapter.new()
	main.actor_nodes[200] = previous
	main._built_bodies = 1
	app.actors[200] = {"actor_id": 200, "actor_type": 1, "kind": 1, "name": "Replacement", "x": 0, "y": 0}
	main.call("_record_actor_creation", 201, 6000)
	_expect(not main.call("_replace_actor_node", 200, true), "exhausted elapsed allowance rejects a replacement")
	_expect(main.actor_nodes.get(200) == previous and previous.visible
		and previous.collision_layer == 2 and not previous.is_queued_for_deletion()
		and main._built_bodies == 1, "a denied replacement retains its previous presentation and census")
	main.actor_nodes.erase(200)
	main.adapter = null
	app.actors.erase(200)
	previous.free()

func _test_resident_quality(main: Variant) -> void:
	var holder := Node3D.new()
	var active := Node3D.new()
	var neighbour := Node3D.new()
	holder.add_child(active)
	holder.add_child(neighbour)
	var first := TrackedPopulation.new()
	first.name = "AmbientPopulation"
	first.pending = 2
	active.add_child(first)
	var second := TrackedPopulation.new()
	second.name = "AmbientPopulation"
	second.pending = 3
	neighbour.add_child(second)
	var loader := WorldLoader.new()
	loader.world_root = active
	main.world_root = holder
	main.world_loader = loader
	main.ambient_population = first
	var exterior := ExteriorRegionStream.new()
	main.exterior_stream = exterior
	main.exterior_stream.residents = {"active": {"root": active}, "neighbour": {"root": neighbour}}
	main.call("_apply_ambient_render_quality", 0)
	_expect(first.applied == [0] and second.applied == [0], "active/resident populations receive quality once each")
	_expect(main.call("ambient_creation_pending_count") == 5, "readiness includes queued creation in every resident population")
	main.exterior_stream.residents.clear()
	main.exterior_stream = null
	exterior.free()
	main.ambient_population = null
	main.world_root = null
	main.world_loader = null
	loader.world_root = null
	loader.free()
	holder.free()

func _expect(condition: bool, label: String) -> bool:
	if not condition:
		failures += 1
		push_error("FAIL: " + label)
	return condition

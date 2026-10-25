extends SceneTree
## Repeated crowd packets must not rebuild unchanged target presentation;
## transitions, death, footprint and draw changes still refresh it.
var failures := 0

class ObservedActor extends ReplicatedActor3D:
	var marker_updates := 0
	func _sync_combat_target_marker() -> void:
		marker_updates += 1
		super._sync_combat_target_marker()

func expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func _init() -> void:
	run.call_deferred()

func run() -> void:
	var app_state := root.get_node("AppState")
	var previous_actors: Dictionary = app_state.actors.duplicate(true)
	# Load Main only after the networking autoload has entered the tree.
	var arrivals: Control = load("res://tests/fixtures/slow_arrival_main.gd").new()
	var ids: Array = [30001, 30002, 30003]
	for id: int in ids:
		app_state.actors[id] = {"x": 0, "y": 0}
	arrivals.crowd.lazy = false
	arrivals._spawn_arrivals(ids)
	expect(arrivals.built_ids == [30001] and arrivals._spawn_backlog,
		"an expensive immediate build leaves remaining arrivals queued")
	arrivals._spawn_arrivals(ids)
	expect(arrivals.built_ids == [30001], "a second sync cannot renew the same-frame allowance")
	await process_frame
	await process_frame
	arrivals.built_ids.clear()
	arrivals._spawn_backlog = false
	arrivals.crowd.lazy = true
	arrivals._spawn_arrivals(ids)
	expect(arrivals.built_ids == [30001] and arrivals.deferred_ids.is_empty() and arrivals._spawn_backlog,
		"an expensive build also stops placeholder work for this frame")
	await process_frame
	await process_frame
	arrivals.built_ids.clear()
	arrivals.model_ready = false
	arrivals._spawn_arrivals(ids)
	expect(arrivals.built_ids.is_empty() and arrivals.deferred_ids == ids,
		"cold bodies get deferred representations without synchronous imports")
	await process_frame
	await process_frame
	arrivals.deferred_ids.clear()
	arrivals._charge_actor_work(10000)
	arrivals._spawn_arrivals(ids)
	expect(arrivals.deferred_ids.is_empty(),
		"gate and presentation work consume the same allowance as new nodes")
	await process_frame
	await process_frame
	var capped := ReplicatedActor3D.new()
	capped._model_deferred = true
	root.add_child(capped)
	arrivals.actor_nodes[30001] = capped
	arrivals._body_cap_distance = -1.0
	arrivals.crowd.set_candidates([[1.0, 30001]])
	arrivals.resource_checks = 0
	arrivals._update_model_builds()
	expect(arrivals.resource_checks == 0,
		"actors excluded by the body cap never enter resource readiness or warmup")
	capped.free()
	arrivals.actor_nodes.clear()
	arrivals.free()
	app_state.actors = previous_actors
	var actor := ObservedActor.new()
	root.add_child(actor)
	for index: int in range(500):
		actor.set_combat_target(false)
		actor.set_mount_state({}, {})
	expect(actor.marker_updates == 0, "non-target crowd updates do not touch marker geometry")
	expect(actor.mount_state.is_empty(), "ordinary actors retain their empty mount state")
	actor.set_combat_target(true)
	expect(actor.marker_updates == 1 and actor._combat_target, "target acquisition is presented")
	for index: int in range(500):
		actor.set_combat_target(true)
	expect(actor.marker_updates == 1, "unchanged target updates do not reconfigure its marker")
	actor.set_footprint(Vector2i(2, 2))
	expect(actor.marker_updates == 2, "footprint updates still resize a selected target")
	actor.set_drawn(false)
	expect(not actor._combat_target_marker.visible, "out-of-range target markers stay hidden")
	actor.set_drawn(true)
	expect(actor._combat_target_marker.visible, "returning into range restores a target marker")
	var before_death := actor.marker_updates
	actor.current_action = &"death"
	actor.set_combat_target(true)
	expect(actor.marker_updates == before_death + 1 and not actor._combat_target, "death clears a target even if packets still select it")
	actor.current_action = &"idle"
	actor.set_combat_target(true)
	expect(actor.marker_updates == before_death + 2 and actor._combat_target, "revival can reacquire the target")
	actor.set_combat_target(false)
	expect(actor.marker_updates == before_death + 3 and not actor._combat_target, "target departure is presented")
	actor.mount_state = {"mode": "summoning", "mount_id": "moor_pony"}
	actor.set_mount_state({}, {})
	expect(actor.mount_state.is_empty(), "an empty packet still clears a previous summon state")
	actor.free()
	await process_frame
	# An inherited scene replaces Main's script before _ready. Helper Nodes
	# constructed by the displaced script must not be abandoned outside a tree.
	var benchmark := load("res://tests/integration/crowd_benchmark_main.tscn") as PackedScene
	var orphans_before := int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT))
	var unopened := benchmark.instantiate()
	unopened.free()
	await process_frame
	expect(int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)) == orphans_before,
		"constructing and discarding an inherited Main scene leaks no helper nodes")
	print("crowd state updates: %d failures" % failures)
	quit(failures)

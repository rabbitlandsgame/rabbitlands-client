extends SceneTree
const CrowdPresentation := preload("res://src/world/crowd_presentation.gd")
## A parked body misses live quality walks. Real Main revival must reconcile it
## before rebinding mounts, including when the actor's local-player role changed.
var failures := 0

class SpyActor extends ReplicatedActor3D:
	var events: Array[Dictionary] = []

	func apply_server_state(dto: Dictionary, _adapter: CoordinateAdapter,
			_teleport := false) -> void:
		# Keep the test independent of actor models and authoritative movement.
		actor_id = int(dto.actor_id)

	func apply_render_quality(level: int, is_local_actor: bool = false) -> void:
		super.apply_render_quality(level, is_local_actor)
		events.append({"kind": "quality", "level": _render_quality,
			"local": _render_quality_local_actor})

	func set_mount_state(state: Dictionary, _models: Dictionary) -> void:
		# Observe the exact inherited state a real mount would receive, without
		# importing a horse, rider, equipment or authored textures.
		events.append({"kind": "mount", "level": _render_quality,
			"local": _render_quality_local_actor, "state": state.duplicate(true)})

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var script := load("res://src/app/main.gd") as GDScript
	if not _expect(script != null and script.can_instantiate(), "Main compiles"):
		quit(failures)
		return
	var app := root.get_node("/root/AppState")
	var saved := {"local_actor_id": app.local_actor_id, "selected_actor_id": app.selected_actor_id,
		"actors": app.actors, "actor_titles": app.actor_titles,
		"actor_occupations": app.actor_occupations, "quest_offer_actors": app.quest_offer_actors,
		"actor_mounts": app.actor_mounts}
	var old_quality := LookProfile.player_quality()
	var had_override := OS.has_environment(LookProfile.QUALITY_VARIABLE)
	var old_override := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	app.local_actor_id = 401
	app.selected_actor_id = -1
	app.actor_titles = {}
	app.actor_occupations = {}
	app.quest_offer_actors = {}
	var main: Variant = script.new()
	# Deliberately never add Main to the scene tree or enter its real _ready.
	main.crowd.configure("all")
	for scenario: Dictionary in [
			{"id": 401, "from": LookProfile.Quality.HIGH, "to": LookProfile.Quality.LOW},
			{"id": 402, "from": LookProfile.Quality.LOW, "to": LookProfile.Quality.MEDIUM},
			{"id": 401, "from": LookProfile.Quality.MEDIUM, "to": LookProfile.Quality.HIGH}]:
		_check_park_change_revive(main, app, scenario)
	main.free()
	for key: String in saved:
		app.set(key, saved[key])
	LookProfile.set_player_quality(old_quality)
	if had_override:
		OS.set_environment(LookProfile.QUALITY_VARIABLE, old_override)
	else:
		OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	print("actor revival quality: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _check_park_change_revive(main: Variant, app: Node, scenario: Dictionary) -> void:
	var id := int(scenario.id)
	var is_local: bool = id == app.local_actor_id
	var dto := {"actor_id": id, "actor_type": 1, "kind": 1, "name": "RevivalFixture",
		"map": "fixture", "x": 0, "y": 0}
	app.actors = {id: dto}
	app.actor_mounts = {id: {"owner": "RevivalFixture", "map": "fixture", "profile": "fixture"}}
	var actor := SpyActor.new()
	root.add_child(actor)
	actor.set_process(false)
	actor.set_physics_process(false)
	LookProfile.set_player_quality(int(scenario.from))
	# A recycled local role must also be corrected when the body returns.
	actor.apply_render_quality(int(scenario.from), not is_local)
	actor.events.clear()
	var key := CrowdPresentation.identity_key(dto)
	if not _expect(main.crowd.park_node(id, actor, key, 0), "fixture parks a reusable body"):
		actor.free()
		return
	LookProfile.set_player_quality(int(scenario.to))
	main.call("_apply_actor_render_quality")
	_expect(actor._render_quality == int(scenario.from) and actor.events.is_empty(),
		"a parked body is outside the live actor quality walk")
	var revived := main.crowd.take_parked(id, key) as SpyActor
	if not _expect(revived == actor, "parking returns the same body"):
		main.crowd.clear()
		if is_instance_valid(actor):
			actor.free()
		return
	main.call("_revive_actor", id, revived, dto, CoordinateAdapter.new())
	_expect(main.actor_nodes.get(id) == actor and main._built_bodies == 1,
		"real Main revival restores body ownership and census")
	_expect(actor._render_quality == int(scenario.to)
		and actor._render_quality_local_actor == is_local,
		"revival applies the current quality and current local-player role")
	_expect(actor.events.size() == 2 and actor.events[0].kind == "quality"
		and actor.events[1].kind == "mount" and actor.events[1].level == int(scenario.to)
		and actor.events[1].local == is_local and not actor.events[1].state.is_empty(),
		"quality is reconciled before the valid mount state is rebound")
	main.actor_nodes.erase(id)
	main._built_bodies = 0
	actor.free()

func _expect(condition: bool, label: String) -> bool:
	if not condition:
		failures += 1
		push_error("FAIL: " + label)
	return condition

extends SceneTree
## Live body readiness and interrupted first-view recovery. All choices remain
## native requests; the controller never changes the authoritative snapshot.
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

class Actor extends Node3D:
	var server_target := Vector3.ZERO
	var skeleton := Skeleton3D.new()
	func _init() -> void:
		add_child(skeleton)
		skeleton.add_bone("Head")
		skeleton.set_bone_rest(0, Transform3D(Basis.IDENTITY, Vector3(0, 1.7, 0)))
	func is_model_deferred() -> bool: return false
	func get_skeleton() -> Skeleton3D: return skeleton
	func set_cinematic_presentation(point: Vector3, yaw: float, _action: StringName, _speed: float) -> void:
		global_position = point; rotation.y = yaw
	func end_cinematic_presentation() -> void: global_position = server_target

class Rig extends Node3D:
	var camera: Camera3D
	var focus := Vector3.ZERO
	var distance := 26.0
	var pitch_degrees := -60.0
	var yaw_degrees := 0.0

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if value: print("PASS: ", message)
	else: failures += 1; push_error(message)

func fixture(deferred := false) -> Dictionary:
	var stage := Node3D.new(); root.add_child(stage)
	var adapter := CoordinateAdapter.new({"walkingHeight":0})
	var hero := Actor.new(); stage.add_child(hero)
	hero.server_target = adapter.tile_center(269, 128); hero.global_position = hero.server_target
	var mother: Node3D
	if deferred:
		var pending := ReplicatedActor3D.new(); stage.add_child(pending)
		pending.configure({"actor_id":20,"actor_type":0,"kind":2,"name":"Elen Reed","x":268,"y":128,
			"rotation":0,"frame":7,"health":50,"max_health":50}, adapter, {}, {}, {}, false)
		pending.set_process(false); pending.set_physics_process(false)
		mother = pending
	else:
		var ready := Actor.new(); stage.add_child(ready)
		ready.server_target = adapter.tile_center(268, 128); ready.global_position = ready.server_target
		mother = ready
	var rig := Rig.new(); stage.add_child(rig)
	rig.camera = Camera3D.new(); rig.add_child(rig.camera)
	rig.camera.position = Vector3(0, 12, 12); rig.camera.look_at(Vector3.ZERO)
	var scene := Scene.new(); root.add_child(scene); scene.configure()
	scene.set_auto_dialogue(true, false)
	var state := {"version":1,"kind":"rescue","active":true,"run_id":"recovery-run","map":"landfall",
		"actors":{"mother":20,"protagonist":1},
		"anchors":{"mother_intercept":[268,128],"escape_turn":[273,115],"runoff_start":[268,128],
			"runoff_mid":[273,124],"runoff_end":[273,115],"runoff_player_start":[269,128],
			"runoff_player_mid":[272,124],"runoff_player_end":[272,115]},
		"scene":{"id":"measure.rescue.commitment","token":"recovery-run:commitment","requires_ack":true,
			"actors":{"mother":20,"protagonist":1},"choice":{"id":"rescue_accept","title":"Will you help?",
				"owner":"Aster","owner_is_you":true,"can_choose":true,"selected":"","response":"",
				"options":[{"id":"accept","label":"I will help","detail":"Follow her to the mine."},
					{"id":"defer","label":"I need to prepare","detail":"Return later."}]}}}
	var events := {"finished":[],"replay":[],"choices":[]}
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: events.finished.append([token, reason]))
	scene.replay_finished.connect(func(token: String, reason: String) -> void: events.replay.append([token, reason]))
	scene.choice_requested.connect(func(option: String) -> void: events.choices.append(option))
	return {"stage":stage,"scene":scene,"nodes":{1:hero,20:mother},"rig":rig,"adapter":adapter,"state":state,"events":events}

func identity(f: Dictionary) -> String: return str(f.state.run_id) + ":" + str(f.state.scene.token)
func tick(f: Dictionary, delta := 0.016, here := "landfall") -> void:
	f.scene.update(delta, f.state, f.rig, f.nodes, 1, here, true, f.adapter, func(_at: Vector3) -> float: return 0.0)
func ready_mother(f: Dictionary) -> Actor:
	var actor := Actor.new(); f.stage.add_child(actor)
	actor.server_target = f.adapter.tile_center(268, 128); actor.global_position = actor.server_target
	if is_instance_valid(f.nodes.get(20)): f.nodes[20].queue_free()
	f.nodes[20] = actor
	return actor
func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_complete"); f.scene.queue_free(); f.stage.queue_free()

func run() -> void:
	create_timer(60).timeout.connect(func() -> void: push_error("Campaign recovery checks timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var first := fixture(true)
	expect(first.scene.has_method("request_interactive"), "the shared controller exposes explicit interactive recovery")
	if not first.scene.has_method("request_interactive"): dispose(first); quit(1); return
	tick(first)
	expect(first.scene.pending and not first.scene.playing and first.events.finished.is_empty(),
		"a genuine native deferred mother keeps the first authored conversation pending")
	ready_mother(first); await process_frame
	tick(first, 2.1)
	expect(first.scene.playing and first.scene._dialogue.portrait_visible() and not first.scene._caption.text.is_empty(),
		"the same snapshot starts with the ready mother's portrait after ordinary body promotion")
	expect(not first.scene._handled.has(identity(first)), "starting a first viewing does not mark it successfully handled")
	dispose(first); await process_frame

	for interruption: String in ["map_changed", "replaced"]:
		var f := fixture(); tick(f, 2.1)
		var original: Dictionary = f.state.duplicate(true)
		if interruption == "map_changed": tick(f, 0.01, "greenlight")
		else:
			f.state.scene.token = "replacement-token"; tick(f)
			f.scene.cancel("test_complete")
		expect(not f.scene._handled.has(str(original.run_id) + ":" + str(original.scene.token)),
			interruption + " leaves an interrupted first viewing unhandled")
		f.state = original; tick(f, 2.1)
		var already_seen := false
		for event: Array in f.events.finished: already_seen = already_seen or event[1] == "already_seen"
		expect(f.scene.playing and not already_seen, interruption + " cannot convert the next first attempt into an already-seen acknowledgment")
		dispose(f); await process_frame

	var timeout := fixture(true)
	timeout.state.scene.choice.can_choose = false
	tick(timeout, Scene.WAIT_LIMIT + 0.01)
	expect(not timeout.scene.is_active() and not timeout.scene._handled.has(identity(timeout)) and not timeout.scene._ack_requested,
		"loading timeout remains retryable without a successful-viewing marker or acknowledgment")
	expect(timeout.scene.call("request_interactive", timeout.state, "landfall"),
		"a failed first viewing exposes interactive retry even without an offered choice")
	ready_mother(timeout); await process_frame; tick(timeout, 2.1)
	expect(timeout.scene.playing and not timeout.scene.is_replaying(), "loading retry starts a native interactive viewing rather than read-only replay")
	dispose(timeout); await process_frame

	var lost := fixture(); tick(lost, 2.1)
	lost.nodes[20].free(); lost.nodes.erase(20); tick(lost)
	expect(lost.scene._last_return_reason == "actor_lost" and not lost.scene._handled.has(identity(lost)) and not lost.scene._ack_requested,
		"an actual freed cast node exposes actor loss without silently completing its viewing")
	ready_mother(lost); tick(lost)
	expect(not lost.scene.playing, "failure does not create a disruptive automatic restart loop")
	expect(lost.scene.call("request_interactive", lost.state, "landfall"), "a restored cast can explicitly resume the failed first viewing")
	tick(lost, 2.1)
	expect(lost.scene.playing and not lost.scene.is_replaying(), "actor-loss recovery preserves native interaction mode")
	dispose(lost); await process_frame

	var camera := fixture(); tick(camera, 2.1)
	camera.rig.camera.free(); tick(camera)
	expect(camera.scene._last_return_reason == "camera_lost" and not camera.scene._handled.has(identity(camera)),
		"camera loss also leaves the first viewing incomplete")
	camera.rig.camera = Camera3D.new(); camera.rig.add_child(camera.rig.camera)
	camera.rig.camera.position = Vector3(0, 12, 12); camera.rig.camera.look_at(Vector3.ZERO)
	expect(camera.scene.request_replay(camera.state, "landfall"), "the existing replay affordance routes a failed viewing to interactive retry")
	tick(camera, 2.1)
	expect(camera.scene.playing and not camera.scene.is_replaying(), "retry through the replay affordance remains able to send native decisions")
	dispose(camera); await process_frame

	var interactive := fixture(); tick(interactive, 2.1)
	interactive.scene.cancel("skipped"); interactive.state.scene.requires_ack = false
	expect(interactive.scene._handled.has(identity(interactive)), "an explicit user Skip still records a completed first viewing")
	expect(interactive.scene.call("request_interactive", interactive.state, "landfall"),
		"talking to the mother can reopen an unchosen current scene after Skip")
	tick(interactive, 28.0)
	expect(interactive.scene._choice_waiting and not interactive.scene._choice_review and not interactive.scene.is_replaying(),
		"interactive re-entry presents an actionable native choice in the portrait dialogue")
	interactive.scene._choice_dialog.option_buttons.accept.pressed.emit()
	expect(interactive.events.choices == ["accept"] and str(interactive.state.scene.choice.selected).is_empty(),
		"the real choice button emits one native request while the authoritative snapshot stays unchanged")
	dispose(interactive); await process_frame

	var completed := fixture(); tick(completed, 2.1)
	completed.scene.cancel("finished"); completed.state.scene.requires_ack = false
	completed.state.scene.choice.selected = "accept"; completed.state.scene.choice.can_choose = false
	completed.state.scene.choice.response = "Follow me to the mine."
	expect(not completed.scene.call("request_interactive", completed.state, "landfall"),
		"an already answered successful conversation cannot reopen a mutable decision")
	expect(completed.scene.request_replay(completed.state, "landfall"), "a successfully viewed scene retains ordinary read-only replay")
	tick(completed, 28.0)
	expect(completed.scene.is_replaying() and completed.scene._choice_review, "successful replay shows the recorded option in review mode")
	completed.scene._choice_dialog.option_buttons.defer.pressed.emit()
	expect(completed.events.choices.is_empty(), "recorded-choice replay cannot emit a different native decision")
	dispose(completed); await process_frame
	print("Campaign scene recovery: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

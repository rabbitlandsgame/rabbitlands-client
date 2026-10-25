extends SceneTree
const Fixture := preload("res://tests/test_campaign_scene.gd")
const Presentation := preload("res://src/world/campaign_scene.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const Works := preload("res://src/world/campaign_works.gd")
var failures := 0
var checks := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func state() -> Dictionary:
	return {"version": 1, "active": true, "run_id": "party-run", "map": "twinbrook", "stage": 7,
		"title": "The Work at Twinbrook", "hint": "Brace the bypass and release the crew before installing the fitting.",
		"actors": {"odo": 2, "worker": 3, "voss": 4},
		"targets": [{"id": "bypass", "object_id": 62001, "label": "Hold the bypass", "tile": [368, 87], "approach": [368, 88], "enabled": true, "completed": false}],
		"party": {"owner": "Aster", "role": "eligible", "can_join": false, "can_start_own": false,
			"waiting_for_owner": false, "waiting_for_scene": false,
			"members": [{"name": "Aster", "role": "owner", "online": true, "present": true, "adoption": "adopted"},
				{"name": "Birch", "role": "eligible", "online": true, "present": true, "adoption": "pending"}]},
		"adoption": {"state": "pending", "run_id": "party-run", "revision": 12, "can_adopt": true,
			"summary": "The pump fittings were prioritized; the account will be public.", "reason": ""},
		"anchors": {"bypass": [368, 88], "sluice_prop": [370, 85], "voss_work": [370, 87], "gauge": [367, 95], "flow": [366, 91],
			"worker_trapped": [372, 87], "worker_safe": [372, 97], "intake": [360, 89],
			"diversion": [364, 89], "fitting": [363, 87], "test": [368, 91]},
		"mechanism": {"bypass_open": true, "fitting": false, "crew_safe": false, "flow": 0, "gauge": 0, "claimed_gauge": 2},
		"scene": {"id": "measure.twinbrook.voss_rescue", "token": "rescue-1", "variant": "pump", "requires_ack": true}}

func height(point: Vector3) -> float:
	return 145.0 + point.z * 0.1

func run() -> void:
	var snapshot := state()
	expect("campaign_party_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "party admission advertises the implemented capability")
	expect(EloriaProtocol.decode_campaign(JSON.stringify(snapshot).to_utf8_buffer()).get("type") == "campaign", "party, adoption, anchors and live mechanisms decode together")
	expect(EloriaProtocol.decode_campaign(JSON.stringify({"version": 1, "active": false, "available": true}).to_utf8_buffer()).get("type") == "campaign", "original campaign_v1 snapshots remain compatible")
	var invalid: Array[Dictionary] = []
	var bad := snapshot.duplicate(true)
	bad.party.role = "secret_owner"
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.party.members.resize(9)
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.adoption.erase("revision")
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.mechanism.gauge = 3
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.anchors.gauge = [1.25, 2]
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.travel = {"npc": "Odo Fenn"}
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.companion = {"name": "Odo", "mode": "teleport", "status": "Ready", "can_command": true}
	invalid.append(bad)
	bad = snapshot.duplicate(true)
	bad.companion = {"name": "Odo", "mode": "wait", "status": "Ready", "can_command": "true"}
	invalid.append(bad)
	for malformed: Dictionary in invalid:
		expect(EloriaProtocol.decode_campaign(JSON.stringify(malformed).to_utf8_buffer()).get("type") == "invalid", "malformed authority/adoption/geometry state is rejected")
	# Use the loaded singleton: the network class also refers to AppState, so
	# resolving it while this script is parsed can precede autoload setup.
	var network := root.get_node("Network")
	expect(bool(network.call("_campaign_identifier", "party-run:measure.twinbrook.rescue")), "revision-bound scene identifiers accept the supported wire format")
	expect(not bool(network.call("_campaign_identifier", "party-run\n#campaign adopt")) and not bool(network.call("_campaign_identifier", "")), "command identifiers cannot inject another command")
	var hud := Hud.new()
	root.add_child(hud)
	var decisions: Array = []
	var actions: Array = []
	var targets: Array = []
	var orders: Array = []
	hud.decision_requested.connect(func(action: String, run_id: String, revision: int) -> void: decisions.append([action, run_id, revision]))
	hud.action_requested.connect(func(action: String) -> void: actions.append(action))
	hud.target_requested.connect(func(id: int, tile: Vector2i, near: bool) -> void: targets.append([id, tile, near]))
	hud.companion_requested.connect(func(command: String) -> void: orders.append(command))
	hud.apply_state(snapshot, Vector2i(368, 88), "twinbrook")
	expect(hud._party.text.contains("Story owner: Aster") and hud._party.text.contains("Birch"), "the roster identifies the story owner and participant")
	expect(hud._record.visible and not hud._record.disabled and hud._help_only.visible, "eligible players receive explicit personal outcome choices")
	hud._request_decision("adopt")
	expect(decisions == [["adopt", "party-run", 12]], "adoption requests bind the exact run and revision")
	expect(snapshot.adoption.state == "pending", "clicking Record does not fabricate a saved outcome")
	var blocked := snapshot.duplicate(true)
	blocked.adoption.can_adopt = false
	blocked.adoption.reason = "Complete a useful personal contribution first."
	hud.apply_state(blocked, Vector2i(368, 88), "twinbrook")
	hud._request_decision("adopt")
	hud._request_decision("help")
	expect(decisions.size() == 2 and decisions.back() == ["help", "party-run", 12], "a blocked adoption still permits Help Only without recording another player's choice")
	var owner := blocked.duplicate(true)
	owner.party.role = "owner"
	hud.apply_state(owner, Vector2i(368, 88), "twinbrook")
	expect(hud._record.is_visible_in_tree() and hud._record.disabled and not hud._help_only.visible, "an owner who still needs personal practice can see the pending Record control")
	hud._request_decision("help")
	expect(decisions.size() == 2, "the story owner cannot become Help Only")
	owner.adoption.can_adopt = true
	owner.adoption.reason = ""
	hud.apply_state(owner, Vector2i(368, 88), "twinbrook")
	hud._request_decision("adopt")
	expect(not hud._record.disabled and decisions.back() == ["adopt", "party-run", 12], "the owner's Record action becomes available after server-confirmed practice")
	owner.adoption = {}
	hud.apply_state(owner, Vector2i(368, 88), "twinbrook")
	expect(not hud._adoption_actions.visible and not hud._adoption.text.contains("Recorded"), "an initial empty adoption state never claims an outcome was recorded")
	owner.companion = {"name": "Odo Fenn", "mode": "wait", "status": "Waiting beside the work.", "can_command": true}
	expect(EloriaProtocol.decode_campaign(JSON.stringify(owner).to_utf8_buffer()).get("type") == "campaign", "the optional server companion status decodes without changing legacy snapshots")
	hud.apply_state(owner, Vector2i(368, 88), "twinbrook")
	for command: String in ["follow", "wait", "regroup", "help"]:
		hud._request_companion(command)
	hud._request_companion("teleport")
	expect(orders == ["follow", "wait", "regroup", "help"] and hud._companion.text.contains("Waiting beside"), "four explicit companion orders use the displayed authoritative status")
	expect(owner.companion.mode == "wait", "a companion order does not fabricate a successful movement")
	owner.companion.can_command = false
	hud.apply_state(owner, Vector2i(368, 88), "twinbrook")
	hud._request_companion("help")
	expect(orders.size() == 4 and hud._companion_buttons.help.disabled, "nonowners receive a truthful companion status without field command authority")
	var helper := snapshot.duplicate(true)
	helper.party.role = "helper"
	helper.adoption.state = "help_only"
	hud.apply_state(helper, Vector2i(368, 88), "twinbrook")
	expect(not hud._adoption_actions.visible and hud._adoption.text.contains("unchanged"), "helpers see clearly that their own story is unchanged")
	var travel := snapshot.duplicate(true)
	travel.map = "greenlight"
	travel.started = true
	travel.available = false
	travel.scene = {}
	travel.travel = {"map": "twinbrook", "npc": "Odo Fenn", "title": "Meet Odo at Twinbrook", "route": "Follow the public roads through Brambleshaw, Reedfall and Hearthcroft to Twinbrook."}
	hud.apply_state(travel, Vector2i(450, 308), "greenlight")
	hud._request_target("bypass", 62001)
	expect(hud.visible and not hud._scroll.visible and not hud._entry.visible and targets.is_empty(), "travel guidance never sends destination-map coordinates from the current public map")
	travel.available = true
	hud.apply_state(travel, Vector2i(361, 85), "twinbrook")
	expect(hud._entry.visible and hud._entry.text.contains("Odo"), "continuation appears only when the server makes the local contact available")
	var own := helper.duplicate(true)
	own.active = false
	own.available = false
	own.party.can_start_own = true
	hud.apply_state(own, Vector2i(361, 85), "twinbrook")
	hud._own.pressed.emit()
	expect(hud.visible and hud._own.visible and actions.back() == "own", "Help Only has an explicit Continue My Story exit")
	var adapter := CoordinateAdapter.new({"serverOrigin": [459, 219], "walkingHeight": 158.0})
	var rig := Fixture.Rig.new()
	root.add_child(rig)
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.global_position = Vector3(-95, 173, 142)
	camera.look_at(Vector3(-90, 158, 128), Vector3.UP)
	var original_camera := camera.global_transform
	var actors := {}
	for row: Array in [[1, [359, 99]], [2, [363, 93]], [3, [372, 97]], [4, [370, 87]]]:
		var actor := Fixture.Actor.new()
		root.add_child(actor)
		var point := adapter.tile_center(row[1][0], row[1][1])
		point.y = height(point)
		actor.global_position = point
		actor.post = actor.global_transform
		actors[row[0]] = actor
	var scene := Presentation.new()
	root.add_child(scene)
	scene.set_reduced_motion(false, false)
	var finished: Array = []
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: finished.append([token, reason]))
	var resident := [false]
	var cold_sample := func(point: Vector3) -> float: return height(point) if resident[0] else NAN
	scene.update(0, snapshot, rig, actors, 1, "twinbrook", true, adapter, cold_sample)
	expect(scene.pending and not scene.blocks_input() and camera.global_transform.is_equal_approx(original_camera), "a cold neighboring terrain chunk cannot start a floating cinematic or lock gameplay")
	resident[0] = true
	scene.update(0, snapshot, rig, actors, 1, "twinbrook", true, adapter, cold_sample)
	expect(scene.playing and (actors[3] as Node3D).global_position.z > 130, "the earned rescue begins at the trapped anchor while authoritative state remains safe")
	scene.update(5, snapshot, rig, actors, 1, "twinbrook", true, adapter, height)
	var worker_point: Vector3 = actors[3].global_position
	expect(worker_point.z > 121.5 and worker_point.z < 131.5 and is_equal_approx(worker_point.y, height(worker_point)), "the worker walks a real ten-metre route and follows sampled terrain height")
	expect(actors[4].action == &"defend", "Voss visibly braces the bypass during the crew's escape")
	expect(is_equal_approx(actors[4].global_position.z, actors[4].post.origin.z + 1.0) and is_equal_approx(actors[4].global_position.y, height(actors[4].global_position)), "Voss makes one reversible metre of terrain-following contact toward the actual gate")
	expect(not scene.work_readouts_visible(), "cinematic closeups suppress field labels that would cover the cast")
	scene.skip()
	expect(camera.global_transform.is_equal_approx(original_camera) and actors[3].global_transform.is_equal_approx(actors[3].post), "skip restores camera and the server-confirmed worker position")
	expect(actors[4].global_transform.is_equal_approx(actors[4].post) and scene.work_readouts_visible(), "skip restores Voss and the gameplay readouts")
	scene.update(0.1, snapshot, rig, actors, 1, "twinbrook", true, adapter, height)
	expect(finished.size() == 1, "ordinary resends do not flood the scene-ready barrier")
	scene.cancel("disconnected")
	scene.update(0.1, snapshot, rig, actors, 1, "twinbrook", true, adapter, height)
	expect(not scene.playing and finished.back() == ["rescue-1", "already_seen"], "rejoining re-acknowledges an already-seen scene without replay")
	scene.update(0.1, snapshot, rig, actors, 1, "twinbrook", true, adapter, height)
	expect(finished.size() == 2, "the rejoin acknowledgment is deduplicated")
	var works := Works.new()
	root.add_child(works)
	resident[0] = false
	works.apply_snapshot(snapshot, adapter, "twinbrook", cold_sample)
	expect(works.gate == null and not works.visible, "the native prop waits for actual terrain instead of using registry fallback elevation")
	resident[0] = true
	works.apply_snapshot(snapshot, adapter, "twinbrook", height)
	expect(is_instance_valid(works.gate), "the demonstration uses the approved native timber sluice asset")
	expect(is_equal_approx(works.gate.global_position.y, height(works.gate.global_position)), "the apparatus grounds in Twinbrook's actual height frame")
	expect(works.gate.global_position.is_equal_approx(works.points.sluice_prop) and not works.gate.global_position.is_equal_approx(works.points.bypass), "the physical gate uses its validated footprint rather than the operator's approach")
	expect(works.gate.scale.is_equal_approx(Vector3.ONE) and is_zero_approx(works.gate.rotation.y) and absf(works.gate.rotation.x) > 0.01, "the approved unit-scale gate aligns its ground plane to the sampled slope")
	var stable := snapshot.duplicate(true)
	stable.mechanism.flow = 2
	stable.mechanism.gauge = 1
	stable.mechanism.fitting = true
	stable.mechanism.crew_safe = true
	works.apply_snapshot(stable, adapter, "twinbrook", height, true)
	works._process(1.0)
	var stable_y: float = works.gauge_marker.global_position.y
	expect(works.labels.gauge.text.contains("Measured: 1 unit") and works.labels.gauge.text.contains("Permit: 2 units"), "a stable one-unit measurement visibly disagrees with the two-unit claim")
	expect(works.labels.flow.text == "Flow · controlled" and works.flow_material.get_shader_parameter("reduced_motion") == true, "controlled flow status and reduced-motion effects follow the server snapshot")
	stable.cargo = "medical"
	works.apply_snapshot(stable, adapter, "twinbrook", height)
	expect(works.labels.fitting.text == "Manual bypass · braced", "the medical branch describes the actual manual bypass instead of a nonexistent pump fitting")
	works.set_readouts_visible(false)
	expect(not works.labels.gauge.visible and not works.labels.fitting.visible, "cinematic suppression hides the labels without removing the physical apparatus")
	works.set_readouts_visible(true)
	scene.update_ambient(stable, actors, adapter, height, 1)
	expect(actors[4].global_transform.is_equal_approx(actors[4].post), "Voss is free to leave the brace after the crew reaches safety")
	scene.update_ambient(snapshot, actors, adapter, height, 1)
	var braced: Vector3 = actors[4].global_position
	scene.update_ambient(snapshot, actors, adapter, height, 1)
	expect(actors[4].global_position.is_equal_approx(braced) and is_equal_approx(braced.z, actors[4].post.origin.z + 1), "ambient bracing remains a single metre with no per-frame positional drift")
	scene.cancel("map_changed")
	expect(actors[4].global_transform.is_equal_approx(actors[4].post), "map changes also restore the ambient Voss presentation")
	var unstable := stable.duplicate(true)
	unstable.mechanism.flow = 1
	unstable.mechanism.gauge = 2
	works.apply_snapshot(unstable, adapter, "twinbrook", height)
	works._process(1.0)
	expect(works.gauge_marker.global_position.y > stable_y and works.labels.flow.text.contains("check"), "changing the valve state moves the gauge and changes the visible water condition")
	works.apply_snapshot(stable, adapter, "greenlight", height)
	expect(not works.visible and works.gate == null, "private machinery never persists onto another map")
	works.queue_free()
	hud.queue_free()
	scene.queue_free()
	for actor: Node in actors.values():
		actor.queue_free()
	rig.queue_free()
	await process_frame
	await process_frame
	print("campaign party: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

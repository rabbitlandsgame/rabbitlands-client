extends SceneTree
const Fixture := preload("res://tests/test_campaign_scene.gd")
const Presentation := preload("res://src/world/campaign_scene.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const Works := preload("res://src/world/campaign_bank_works.gd")
var checks := 0
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

static func state() -> Dictionary:
	return {"version": 1, "kind": "bank", "active": true, "started": true,
		"run_id": "bank-fixture", "map": "landfall", "stage": "model", "key": "model",
		"title": "The Brook's Other Bank", "hint": "Test the intake alone, then compare the stable return.",
		"actors": {"odo": 2, "ammet": 4, "worker": 3},
		"scene": {"id": "measure.bank.remedy", "token": "bank-model", "requires_ack": true},
		"anchors": {"entry": [130, 275], "recovery": [130, 275], "briefing": [135, 278],
			"model": [160, 289], "intake": [156, 288], "diversion": [163, 291], "flow": [161, 294],
			"gauge": [158, 294], "reserve": [165, 290], "crossing": [145, 280],
			"crossing_near": [142, 280], "crossing_far": [148, 280], "tree": [153, 284],
			"marker_1": [162, 282], "marker_2": [154, 291], "marker_3": [152, 289],
			"destination": [163, 280], "worker": [166, 284], "maintenance_1": [141, 302],
			"maintenance_2": [165, 299], "bypass": [166, 296]},
		"targets": [{"id": "trace_intake", "object_id": 63020, "label": "Lift the misplaced intake marker",
			"tile": [152, 289], "approach": [152, 288], "enabled": true, "completed": false}],
		"party": {"owner": "Aster", "role": "eligible", "members": [
			{"name": "Aster", "role": "owner", "present": true, "online": true, "adoption": ""},
			{"name": "Birch", "role": "eligible", "present": true, "online": true, "adoption": "pending"}]},
		"adoption": {}, "bank": {"approach": "planks", "remedy": "", "disclosure": "",
			"inherited_disclosure": "protected", "diversion": 0, "reading": 0, "claimed_gauge": 2,
			"crossing_ready": false, "remedy_complete": false, "route_step": 1, "route_total": 4,
			"sequence_step": 0, "sequence_total": 3, "sequence_correct": false, "misplaced": "",
			"last_error": "", "tree_cared": false, "bypass_ready": false,
			"cost": "Crossing: 2 Wood Planks.", "consequence": "The existing public grove and old sluice stay unchanged."}}

func height(_point: Vector3) -> float:
	return 121.525

func run() -> void:
	var snapshot := state()
	expect("campaign_bank_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "the client negotiates the additive bank chapter capability")
	expect(EloriaProtocol.decode_campaign(JSON.stringify(snapshot).to_utf8_buffer()).get("type") == "campaign", "the server-shaped bank state decodes with existing party and marker data")
	for field: String in ["approach", "remedy", "disclosure", "diversion", "sequence_step", "sequence_correct", "last_error", "crossing_ready"]:
		var bad := snapshot.duplicate(true)
		bad.bank[field] = {"approach": "teleport", "remedy": "free", "disclosure": "force_party",
			"diversion": 3, "sequence_step": 4, "sequence_correct": "yes", "last_error": 7, "crossing_ready": 1}[field]
		expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).get("type") == "invalid", "malformed bank " + field + " is rejected")
	for approach: String in ["detour", "planks", "secure"]:
		for remedy: String in ["reserve", "material", "maintenance"]:
			var branch := snapshot.duplicate(true)
			branch.bank.approach = approach
			branch.bank.remedy = remedy
			expect(EloriaProtocol.decode_campaign(JSON.stringify(branch).to_utf8_buffer()).get("type") == "campaign", approach + " / " + remedy + " uses the canonical server choices")
	expect(EloriaProtocol.decode_campaign(JSON.stringify({"version": 1, "active": false, "available": true}).to_utf8_buffer()).get("type") == "campaign", "bank support retains original campaign snapshots")
	var adapter := CoordinateAdapter.new({"serverOrigin": [282, 248], "metresPerTile": 1.0, "walkingHeight": 90.0})
	var works := Works.new()
	root.add_child(works)
	var resident := [false]
	var sample := func(point: Vector3) -> float: return height(point) if resident[0] else NAN
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(not works.visible and works.gate == null, "a cold orchard cannot create floating props at the registry fallback height")
	resident[0] = true
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(is_instance_valid(works.gate) and is_instance_valid(works.crossing) and is_instance_valid(works.reserve), "the work uses the approved gate, jetty and reserve crate")
	expect(works.gate.global_position.is_equal_approx(works.points.model), "the model stands on its validated ground anchor")
	expect(works.gate.scale.is_equal_approx(Vector3.ONE) and works.crossing.scale.is_equal_approx(Vector3.ONE), "placement wrappers preserve each imported prop's baked transform")
	var helper: MeshInstance3D
	for mesh: Node in works.crossing.find_children("Walk_*", "MeshInstance3D", true, false):
		helper = mesh as MeshInstance3D
		break
	expect(helper != null and not helper.visible, "the native jetty's walk helper never becomes visible scenery")
	if helper != null:
		var top: Vector3 = helper.global_transform * Vector3(0, helper.get_aabb().end.y, 0)
		expect(absf(top.y - height(top) - Works.DECK_CLEARANCE) < 0.03, "the baked jetty deck clears decorative grass by its bounded navigation offset")
	expect(works.deck_surface.collision_layer == 0, "the closed private crossing never provides a client navigation surface")
	expect(not works.crossing.visible, "choosing planks alone never fabricates the prepared crossing")
	snapshot.bank.crossing_ready = true
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(works.crossing.visible and works.labels.crossing.text.contains("2 Wood Planks used"), "the native crossing appears only after the server confirms real preparation")
	expect(works.deck_surface.collision_layer == WorldLoader.NAVIGATION_SURFACE_LAYER and works.deck_surface.collision_mask == 0, "only the prepared server walk lane supplies the native deck's foot height")
	snapshot.bank.approach = "secure"
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(not works.crossing.visible and works.labels.crossing.text.contains("anchors secured"), "the secured short route does not fabricate a purchased plank structure")
	snapshot.bank.diversion = 1
	snapshot.bank.reading = 2
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	works._process(1)
	var unsafe_y: float = works.gauge_marker.global_position.y
	expect(works.labels.model.text.contains("unsteady") and works.labels.gauge.text.contains("Measured: 2 units"), "the intake-only experiment shows an explicitly unsteady two-unit reading")
	snapshot.bank.diversion = 2
	snapshot.bank.reading = 1
	works.apply_snapshot(snapshot, adapter, "landfall", sample, true)
	works._process(1)
	expect(works.labels.gauge.text.contains("Measured: 1 unit") and works.labels.gauge.text.contains("Permit: 2 units") and works.gauge_marker.global_position.y < unsafe_y, "the stable experiment visibly supplies one unit against the two-unit permit")
	expect(works.flow_material.get_shader_parameter("verified") == true and works.flow_material.get_shader_parameter("reduced_motion") == true, "the visible water follows controlled status and the reduced-motion preference")
	snapshot.bank.remedy = "reserve"
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(works.reserve.visible and works.labels.reserve.text.contains("unspent"), "selecting a remedy does not visually spend its reserve")
	snapshot.bank.remedy_complete = true
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(not works.reserve.visible and works.labels.reserve.text.contains("spent"), "completed reserve work visibly removes the spent reserve crate")
	snapshot.bank.remedy = "material"
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(works.reserve.visible and works.labels.reserve.text.contains("1 Wood Plank used"), "the material remedy keeps the reserve and names the actual board cost")
	snapshot.bank.remedy = "maintenance"
	snapshot.bank.sequence_step = 1
	snapshot.bank.misplaced = "trace_intake"
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(works.labels.reserve.text.contains("maintenance shift"), "maintenance names its crew obligation instead of pretending it consumed an item")
	expect(works.labels.marker_1.text.contains("verified") and works.labels.marker_3.text.contains("Lift misplaced"), "a wrong marker can be lifted while the earlier verified marker stays in place")
	snapshot.bank.misplaced = ""
	snapshot.bank.tree_cared = true
	snapshot.bank.bypass_ready = true
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(works.labels.marker_1.text.contains("verified") and not works.labels.marker_3.text.contains("Lift"), "lifting a wrong marker never erases stable reconstruction progress")
	expect(works.labels.tree.text.contains("cleared") and works.labels.bypass.text.contains("checked"), "optional care and the new bypass read their own server-confirmed state")
	var rig := Fixture.Rig.new()
	root.add_child(rig)
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.global_position = Vector3(-125, 134, -30)
	camera.look_at(Vector3(-124, 122, -40), Vector3.UP)
	var saved_camera := camera.global_transform
	var actors := {}
	for row: Array in [[1, [130, 275]], [2, [133, 281]], [3, [166, 284]], [4, [135, 281]]]:
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
	var authoritative := snapshot.duplicate(true)
	scene.update(0, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	var speaking_camera := camera.global_transform
	scene.update(3, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	expect(scene.playing and actors[3].action == &"idle" and not scene.work_readouts_visible(), "the grounded worker speaks before walking, with all field readouts hidden")
	expect(camera.global_transform.is_equal_approx(speaking_camera), "the close speaking view holds instead of interpolating through orchard foliage")
	scene.update(5, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	expect(scene.playing and actors[3].action == &"walk" and not actors[3].global_transform.is_equal_approx(actors[3].post), "the native worker walks to demonstrate the actual private controls")
	expect(is_equal_approx(actors[3].global_position.y, height(actors[3].global_position)) and not scene.work_readouts_visible(), "control demonstration blocking follows real ground without oversized field labels")
	scene.update(5, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	expect(scene.work_readouts_visible() and camera.global_position.is_equal_approx(scene._anchors.gauge + Vector3(2, 2.6, -3)), "the gauge cut selects its readable view and only then reveals the numeric readouts")
	scene.skip()
	expect(camera.global_transform.is_equal_approx(saved_camera) and actors[3].global_transform.is_equal_approx(actors[3].post), "skipping the bank scene restores the camera and latest server actor post")
	expect(snapshot == authoritative, "cinematic staging cannot complete a model test or reconstruction marker")
	snapshot.scene.token = "reduced-model"
	scene.set_reduced_motion(true, false)
	scene.update(0, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	var reduced_view := camera.global_transform
	scene.update(13, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	expect(camera.global_transform.is_equal_approx(reduced_view) and not scene.work_readouts_visible(), "reduced camera motion keeps the first view and its hidden readouts through later cuts")
	scene.skip()
	snapshot.scene = {"id": "measure.bank.arrival", "token": "inherited", "variant": "protected"}
	scene.set_reduced_motion(true, false)
	scene.update(0, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	var still := camera.global_transform
	scene.update(6, snapshot, rig, actors, 1, "landfall", true, adapter, height)
	expect(camera.global_transform.is_equal_approx(still) and scene.transcript_text().contains("unnamed"), "the inherited protected account changes the briefing while reduced camera motion holds its view")
	scene.cancel("map_changed")
	expect(not scene.blocks_input() and camera.global_transform.is_equal_approx(saved_camera), "a map change cancels bank staging and immediately restores play")
	var hud := Hud.new()
	root.add_child(hud)
	var actions: Array = []
	hud.action_requested.connect(func(action: String) -> void: actions.append(action))
	var entry := snapshot.duplicate(true)
	entry.active = false
	entry.available = true
	hud.apply_state(entry, Vector2i(124, 262), "landfall")
	hud._entry.pressed.emit()
	expect(hud._entry.text.contains("Brook's Other Bank") and actions == ["bank"], "the new chapter's local entry requests its own physical contact handler")
	snapshot.key = "reconstruction"
	snapshot.bank.misplaced = "trace_intake"
	snapshot.bank.last_error = "That marker contradicts the delivery traces. Lift it and check the channel split."
	hud.apply_state(snapshot, Vector2i(152, 288), "landfall")
	expect(hud._bank.text.contains("witness protected") and hud._bank.text.contains("2 Wood Planks") and hud._bank.text.contains("1/3"), "the HUD keeps inherited context, visible costs and shared reconstruction progress together")
	expect(hud._bank.text.contains("Lift the misplaced") and hud._bank.text.contains("Verified observations stay saved"), "the correction explains the physical lift action and preserves earlier work")
	snapshot.targets.append({"id": "tracks", "object_id": 63002, "label": "Inspect cart tracks",
		"tile": [135, 280], "enabled": false, "completed": false})
	snapshot.targets.append({"id": "route_walk", "object_id": 0, "label": "Next detour observation",
		"tile": [137, 304], "approach": [137, 304], "enabled": true, "completed": false})
	hud.apply_state(snapshot, Vector2i(137, 304), "landfall")
	expect((hud._targets.get_child(0) as Button).text.begins_with("Walk to · "), "the next physical waypoint stays ahead of disabled destination interactions in the checklist")
	expect((hud._targets.get_child(1) as Button).text.contains("Lift the misplaced") and (hud._targets.get_child(2) as Button).text.contains("Inspect cart tracks") and snapshot.targets[0].id == "trace_intake", "prioritizing a walking pin preserves the server's physical clue order and snapshot")
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(works.checkpoint.visible and adapter.godot_to_server(works.checkpoint.global_position) == Vector2i(137, 304), "the current route checkpoint has its own grounded field pin")
	snapshot.targets.back().tile = [163, 304]
	snapshot.targets.back().approach = [163, 304]
	works.apply_snapshot(snapshot, adapter, "landfall", sample)
	expect(adapter.godot_to_server(works.checkpoint.global_position) == Vector2i(163, 304) and snapshot.bank.route_step == 1, "only a new authoritative waypoint moves the pin; presentation never grants walking proof")
	# Exercise production Main with an in-memory transport. No socket, account
	# or server is involved, and every requested native packet stays observable.
	var network := root.get_node("Network")
	var recorder := GDScript.new()
	recorder.source_code = "extends \"res://src/network/network_client.gd\"\nvar sent_frames: Array = []\nfunc send_frame(frame: PackedByteArray, _sensitive := false) -> Error:\n\tsent_frames.append(frame)\n\treturn OK\n"
	expect(recorder.reload() == OK, "the native packet recorder compiles after autoload initialization")
	network.set_script(recorder)
	network.call("block_for_hud_preview")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.hide()
	var app_state := root.get_node("AppState")
	app_state.set("campaign", snapshot)
	app_state.set("current_map", "landfall")
	(network.get("sent_frames") as Array).clear()
	main.call("_on_campaign_target", 0, Vector2i(163, 304), true)
	var sent: Array = network.get("sent_frames")
	expect(sent.size() == 1 and sent[0] == EloriaProtocol.move_to(163, 304), "production Main sends MOVE_TO for an adjacent zero-object waypoint, never USE_MAP_OBJECT(0)")
	main.call("_on_campaign_target", 63020, Vector2i(152, 289), true)
	expect(sent.size() == 2 and sent[1] == EloriaProtocol.use_map_object(63020), "physical clue targets keep their ordinary native use packet")
	snapshot.travel = {"map": "twinbrook", "npc": "Odo Fenn"}
	main.call("_on_campaign_target", 0, Vector2i(361, 85), true)
	expect(sent.size() == 2, "a travel card cannot send another map's waypoint through production Main")
	main.queue_free()
	works.apply_snapshot(snapshot, adapter, "twinbrook", sample)
	expect(works.gate == null and not works.visible and works.markers.is_empty(), "all bank props and marker effects clear when leaving Landfall")
	for node: Node in [hud, scene, works, rig]:
		node.queue_free()
	for actor: Node in actors.values():
		actor.queue_free()
	await process_frame
	await process_frame
	print("campaign bank: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

extends "res://tests/integration/rendered_campaign_road.gd"
## Actual Greenlight terrain and native actors. Every experiment/route update is
## an offline server-shaped fixture; no account, socket or objective is changed.
const LampsWorks := preload("res://src/world/campaign_lamps_works.gd")
const LampsFixture := preload("res://tests/test_campaign_lamps.gd")
var _live_state: Dictionary = {}
var _review_attack := false

func _init() -> void:
	run.call_deferred()
	_watchdog.call_deferred()
	process_frame.connect(_tick_ambient)

func _tick_ambient() -> void:
	if not _live_state.is_empty() and is_instance_valid(_presentation) and _adapter != null:
		if _presentation.playing:
			# Hold the selected authored shot while native skeletons animate,
			# retaining Main's per-frame camera/NPC staging semantics.
			_presentation.update(0, _live_state, _rig, _actors, 1, "greenlight", true, _adapter, surface_height)
		else:
			_presentation.update_ambient(_live_state, _actors, _adapter, surface_height, 1.0 / 30.0)
	if _review_attack and is_instance_valid(_actors.get(5)):
		(_actors[5] as ReplicatedActor3D).play_action(&"attack_primary")

func _watchdog() -> void:
	var previous := -1
	var stalled := 0
	while true:
		await create_timer(30).timeout
		stalled = stalled + 30 if previous == _assertions else 0
		previous = _assertions
		if stalled >= 120:
			push_error("The lamp preview stopped making progress; draining its workers and exiting.")
			_fade.reset()
			await ContinentChunkStream.drain_workers(self)
			quit(1)
			return

func load_bay() -> bool:
	_stage = Node3D.new()
	root.add_child(_stage)
	_stage_world = _stage.get_world_3d()
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_energy = 0.8
	_stage.add_child(sun)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("8ba9b6")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b8c8d2")
	environment.environment.ambient_light_energy = 0.55
	_stage.add_child(environment)
	_adapter = CoordinateAdapter.new({"serverOrigin": [435, 448], "metresPerTile": 1.0, "walkingHeight": 2.5})
	_preview_loader = WorldLoader.new()
	_stage.add_child(_preview_loader)
	var loaded := [false]
	_preview_loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	_preview_loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/greenlight/client/world.json"), _adapter.tile_center(333, 423))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(loaded[0], "the actual Greenlight shore work bay package loads")
	if not loaded[0]:
		return false
	_rig = PreviewRig.new()
	_stage.add_child(_rig)
	_preview_camera = Camera3D.new()
	_rig.add_child(_preview_camera)
	_rig.camera = _preview_camera
	_preview_camera.current = true
	_preview_camera.cull_mask = 3
	_preview_camera.fov = 55
	_preview_focus = Node3D.new()
	_stage.add_child(_preview_focus)
	_fade.set_enabled(true)
	_works = LampsWorks.new()
	_stage.add_child(_works)
	return true

func reading(state: Dictionary, cycle: int, load := 0) -> void:
	var data: Dictionary = state.lamps
	data.cycle = cycle
	data.tide = [0, 1, 2, 1][cycle]
	data.load = load
	data.water = maxi(0, int(data.tide) + load - int(data.settings.bleed))
	data.marker_number = int(data.settings.marker) + 1
	data.beam_height = int(data.settings.shutter) + 1
	data.clearance = int(data.marker_number) - int(data.water)
	var aligned := int(data.water) == int(data.beam_height) and int(data.water) <= int(data.marker_number)
	data.lamp_word = "ALIGNED" if aligned else "ABOVE MARK" if int(data.water) > int(data.marker_number) else "OFF BEAM"
	data.lamp_shape = "circle" if aligned else "triangle" if int(data.water) > int(data.marker_number) else "square"
	data.indicator = "level" if aligned else "raised" if int(data.water) > int(data.marker_number) else "offset"
	_works.apply_snapshot(state, _adapter, "greenlight", surface_height)
	_works._process(1)

func walk_actor(id: int, path: Array) -> void:
	for tile: Array in path:
		place_actor(id, Vector2i(tile[0], tile[1]), false)
		var actor: ReplicatedActor3D = _actors[id]
		var goal := _adapter.tile_center(tile[0], tile[1])
		var deadline := Time.get_ticks_msec() + 4000
		while Vector2(actor.global_position.x - goal.x, actor.global_position.z - goal.z).length() > 0.12 and Time.get_ticks_msec() < deadline:
			var ground := surface_height(actor.global_position)
			if is_finite(ground):
				actor.set_surface_height(ground)
			await physics_frame
		expect(Vector2(actor.global_position.x - goal.x, actor.global_position.z - goal.z).length() <= 0.12, "the native person actually walks to the accepted work post")

func run() -> void:
	Engine.max_fps = 30
	_directory = OS.get_environment("RL_LAMPS_PREVIEW_OUT")
	if _directory.is_empty():
		_directory = "C:/rabbitlands/work-output/campaign-lamps-preview"
	DirAccess.make_dir_recursive_absolute(_directory)
	root.size = Vector2i(1280, 720)
	root.get_node("Network").call("block_for_hud_preview")
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(_main)
	await process_frame
	expect(_main.get("campaign_lamps_works") != null, "production Main owns the isolated lamp apparatus")
	_main.hide()
	_presentation = Presentation.new()
	root.add_child(_presentation)
	_presentation.set_reduced_motion(false, false)
	if not await load_bay():
		quit(1)
		return
	for spec: Array in [[1, 1, "Field observer", 338, 427], [2, 323, "Edda Tine", 336, 431],
		[3, 308, "Teren Wick", 315, 411], [4, 348, "Serit Voss", 334, 414], [5, 225, "River otter", 318, 411]]:
		spawn(int(spec[0]), int(spec[1]), str(spec[2]), Vector2i(spec[3], spec[4]), 0 if int(spec[0]) == 1 else 2)
	(_actors[5] as Node3D).hide()
	var state := LampsFixture.state()
	_live_state = state
	state.lamps.unsafe_zones = [{"key": "outer_work", "bounds": [312, 408, 318, 414], "active": true}, {"key": "service_cut", "bounds": [323, 417, 327, 421], "active": true}]
	state.lamps.board_text = "Advance the cycle. Water is tide plus visible load, minus drain, never below zero. Match beam and water without exceeding the marker. Hold the separate live mechanism before escorting anyone."
	state.lamps.inheritance = {"worker_ally": true, "refuge_provisions": true}
	var deadline := Time.get_ticks_msec() + 30000
	while _works.lamp == null and Time.get_ticks_msec() < deadline:
		_works.apply_snapshot(state, _adapter, "greenlight", surface_height)
		await process_frame
	expect(_works.lamp != null and _works.zones.size() == 2, "the native apparatus and thin closed-work markings wait for real bay ground")
	aim(Vector2i(333, 423), Vector3(10, 9, 12))
	await apply_scene(state)
	await capture("01-greenlight-work-bay-establishing.png")
	await apply_scene(state, 5)
	await capture("02-edda-and-held-road-consignment.png")
	expect(_presentation.transcript_text().contains("stays under witnessed hold"), "the opening does not teleport Tobin's held shipment")
	await apply_scene(state, 6)
	await capture("03-three-setting-apparatus-instruction-cut.png")
	_presentation.skip()
	state.scene = {}
	_works.set_readouts_visible(true)
	aim(Vector2i(331, 414), Vector3(0, 8, 14), 1.2)
	for cycle: int in range(4):
		reading(state, cycle)
		state.lamps.observations.append({"cycle": cycle, "water": state.lamps.water, "clearance": state.lamps.clearance,
			"lamp_word": state.lamps.lamp_word, "lamp_shape": state.lamps.lamp_shape})
		await capture("04-cycle-%d-marker-lamp-pointer.png" % cycle)
	var stopped: int = state.lamps.cycle
	for frame: int in range(20):
		await process_frame
	expect(state.lamps.cycle == stopped, "elapsed render time cannot advance a held experiment")
	state.lamps.challenge = true
	state.lamps.prediction = {"candidate": 2, "revision": 8, "status": "contradicted", "feedback": "Water3 differs from beam1 and exceeds marker2. Retry freely.", "can_choose": true}
	reading(state, 2, 1)
	place_actor(1, Vector2i(325, 412))
	var hud := FieldHud.new()
	root.add_child(hud)
	hud.apply_state(state, Vector2i(325, 412), "greenlight")
	await process_frame
	await process_frame
	hud._body_scroll.ensure_control_visible(hud._prediction_actions)
	await capture("05-altered-load-contradiction-and-four-choices.png")
	var all_equal := true
	for button: Button in hud._prediction_buttons:
		all_equal = all_equal and not button.disabled and button.visible
	expect(all_equal, "the changed challenge presents all four choices equally")
	state.lamps.prediction = {"candidate": 0, "revision": 8, "status": "selected", "feedback": "Advance and observe at your selected interval.", "can_choose": true}
	reading(state, 3, 1)
	reading(state, 0, 1)
	state.lamps.prediction.status = "verified"
	state.lamps.prediction.feedback = "Fresh observation: water1 equals beam1 and stays below marker2."
	hud.apply_state(state, Vector2i(325, 412), "greenlight")
	await capture("06-fresh-independent-observation.png")
	hud.hide()
	state.key = "rescue"
	state.scene = {"id": "measure.lamps.rescue", "token": "rescue", "variant": "protect"}
	await apply_scene(state)
	await capture("07-teren-and-real-refuge-route.png")
	await apply_scene(state, 6)
	await capture("08-refuges-and-held-mechanism.png")
	_presentation.skip()
	state.scene = {}
	state.lamps.approach = "protect"
	(_actors[5] as Node3D).show()
	_review_attack = true
	(_actors[5] as ReplicatedActor3D).play_action(&"attack_primary", true)
	expect((_actors[5] as ReplicatedActor3D).current_action == &"attack_primary", "the protection preview uses the creature's actual approved attack action")
	aim(Vector2i(318, 411), Vector3(3, 2.5, 4), 0.5)
	for frame: int in range(12):
		await process_frame
	await capture("09-current-river-otter-protection-animation.png")
	expect((_actors[5] as ReplicatedActor3D).get("_native_model") != null, "the existing current river otter has its native model")
	_review_attack = false
	(_actors[5] as Node3D).hide()
	state.lamps.holder = "Edda Tine"
	state.lamps.holder_active = false
	await walk_actor(2, [[336, 430], [336, 429], [335, 428], [335, 427], [334, 426], [333, 425], [333, 424], [333, 423], [333, 422], [333, 421], [333, 420], [333, 419]])
	state.lamps.holder_active = true
	state.lamps.route_ready = true
	for zone: Dictionary in state.lamps.unsafe_zones:
		zone.active = false
	_works.apply_snapshot(state, _adapter, "greenlight", surface_height)
	_presentation.update_ambient(state, _actors, _adapter, surface_height, 1)
	_works.set_readouts_visible(false)
	aim(Vector2i(333, 418), Vector3(4, 3, -4), 1.0)
	for frame: int in range(25):
		await process_frame
	await capture("10-edda-reaches-and-holds-the-gate.png")
	expect(_adapter.godot_to_server(_actors[2].global_position) == Vector2i(333, 418), "Edda's reversible hand-contact stance follows her actual arrival")
	expect((_actors[2] as ReplicatedActor3D).current_action == &"defend", "the physically held post keeps Edda's native working pose active")
	state.lamps.worker_status = "incapacitated"
	state.lamps.last_error = "Work stopped. Treat Teren and return to the last stable refuge."
	state.lamps.prediction.can_choose = false
	(_actors[3] as ReplicatedActor3D).play_action(&"sit", true)
	aim(Vector2i(315, 411), Vector3(3, 2.5, 4))
	hud.apply_state(state, Vector2i(316, 411), "greenlight")
	hud._body_scroll.scroll_vertical = 0
	await capture("11-recoverable-worker-treatment.png")
	hud.hide()
	(_actors[3] as ReplicatedActor3D).play_action(&"idle", true)
	state.lamps.worker_status = "returning"
	state.lamps.last_error = ""
	state.targets = [{"id": "escort_walk", "object_id": 0, "label": "Walk with Teren to the first refuge", "tile": [322, 416], "approach": [321, 416], "enabled": true, "completed": false}]
	await walk_actor(3, [[316, 412], [317, 413], [318, 414], [319, 415], [320, 416], [321, 416], [322, 416]])
	state.lamps.refuge_step = 1
	_works.apply_snapshot(state, _adapter, "greenlight", surface_height)
	_works.set_readouts_visible(true)
	aim(Vector2i(322, 416), Vector3(5, 4, 7))
	await capture("12-actual-worker-at-first-stable-refuge.png")
	await walk_actor(3, [[323, 417], [324, 418], [325, 419], [326, 420], [327, 421], [328, 422], [329, 422], [330, 422], [331, 423], [332, 424], [333, 424], [334, 424], [335, 424], [336, 424], [337, 424], [338, 424], [339, 424], [340, 424]])
	state.lamps.worker_status = "safe"
	state.lamps.refuge_step = 3
	state.lamps.holder = ""
	state.lamps.holder_active = false
	_presentation.update_ambient(state, _actors, _adapter, surface_height, 1)
	state.scene = {"id": "measure.lamps.worker_safe", "token": "worker-safe"}
	await apply_scene(state)
	await capture("13-teren-safe-and-equipment-handoff.png")
	_presentation.skip()
	state.scene = {}
	state.targets = []
	state.lamps.evidence_method = "witnessed_move"
	state.lamps.evidence_readings = [{"post": "reference", "value": 1, "claimed": 1}, {"post": "fitting", "value": 1, "claimed": 2}]
	for tile: Array in [[337, 411], [337, 412], [337, 413], [337, 414], [337, 415], [338, 416], [339, 417], [340, 417]]:
		state.lamps.equipment_tile = tile
		_works.apply_snapshot(state, _adapter, "greenlight", surface_height)
		for frame: int in range(8):
			await process_frame
	_works.set_readouts_visible(true)
	aim(Vector2i(340, 417), Vector3(4, 3.5, 6))
	await capture("14-witnessed-physical-fixture-in-holding.png")
	expect(_adapter.godot_to_server(_works.equipment.global_position) == Vector2i(340, 417), "only accepted saved crate positions move evidence into holding")
	state.lamps.evidence_secure = true
	state.scene = {"id": "measure.lamps.admission", "token": "admission", "variant": "witnessed_move"}
	await apply_scene(state, 1)
	await capture("15-voss-admission-after-independent-evidence.png")
	expect(not _works.labels.equipment.visible and not _works.pointer.visible, "the speaking shot hides field captions and pointer readouts")
	await apply_scene(state, 7)
	await capture("15b-secured-independent-reading-before-explanation.png")
	expect(_works.labels.equipment.text.contains("Measured 1 / stamp 2"), "the secured counterpart visibly preserves the actual measured contradiction")
	_presentation.skip()
	state.scene = {}
	state.adoption = {"state": "pending", "run_id": state.run_id, "revision": 12, "can_adopt": true, "summary": "The worker is safe and the local counterpart is held under witness. Public, protected or conditional terms remain your own decision.", "reason": ""}
	for name_text: String in ["Birch", "Cedar", "Dahlia", "Elm", "Fern", "Gorse", "Hazel"]:
		state.party.members.append({"name": name_text, "role": "helper", "online": true, "present": true, "adoption": "help_only"})
	root.size = Vector2i(900, 600)
	root.content_scale_factor = 1.5
	state.lamps.prediction.can_choose = true
	hud.apply_state(state, Vector2i(325, 412), "greenlight")
	await process_frame
	await process_frame
	hud._body_scroll.ensure_control_visible(hud._prediction_actions)
	await capture("16-four-equal-choices-at-150-percent.png")
	var clip := hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	var choices_visible := true
	for button: Button in hud._prediction_buttons:
		choices_visible = choices_visible and button.is_visible_in_tree() and clip.encloses(button.get_global_rect())
	expect(choices_visible, "every actual interval choice remains visible in the scaled small window")
	hud._body_scroll.ensure_control_visible(hud._record)
	await capture("17-eight-person-record-or-help-at-150-percent.png")
	clip = hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(hud._help_only.is_visible_in_tree() and clip.encloses(hud._record.get_global_rect()) and clip.encloses(hud._help_only.get_global_rect()), "actual Record and Help decisions remain visible with eight people")
	hud._body_scroll.ensure_control_visible(hud._reduced)
	await capture("18-bottom-return-and-camera-controls.png")
	clip = hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._leave.get_global_rect()) and clip.encloses(hud._reduced.get_global_rect()), "all bottom controls remain reachable")
	hud.hide()
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1
	state.lamps.lamp_done = true
	state.lamps.board_done = true
	_works.apply_snapshot(state, _adapter, "greenlight", surface_height)
	_works.set_readouts_visible(true)
	aim(Vector2i(326, 428), Vector3(3, 3, 5))
	await capture("19-spare-reed-service-wick-in-provided-holder.png")
	expect(_works.service_light.light_energy > 0, "the completed optional service wick gives actual light")
	state.lamps.terms = "protected"
	state.scene = {"id": "measure.lamps.resolved", "token": "resolved", "variant": "protected"}
	await apply_scene(state, 1)
	await capture("20-protected-examination-and-coastal-reserve-lead.png")
	_presentation.skip()
	state.scene.token = "reduced"
	_presentation.set_reduced_motion(true, false)
	await apply_scene(state)
	var pose := _preview_camera.global_transform
	await apply_scene(state, 8)
	expect(_preview_camera.global_transform.is_equal_approx(pose) and not _works.pointer.visible, "reduced motion preserves its first shot and matching readout visibility")
	_presentation.skip()
	_works.clear()
	_live_state = {}
	_fade.reset()
	expect(await ContinentChunkStream.drain_workers(self), "all Greenlight loader workers retire before closing")
	var report := FileAccess.open(_directory.path_join("report.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"assertions": _assertions, "captures": _captures, "failures": _failures, "offline": true, "map": "greenlight", "party_members": 8, "viewport": [900, 600], "ui_scale": 1.5}, "  "))
	hud.queue_free()
	_presentation.queue_free()
	_stage.queue_free()
	_main.queue_free()
	for frame: int in range(6):
		await process_frame
	print("rendered lamps campaign: ", _assertions, " checks including ", _captures, " captures; ", _failures, " failures")
	quit(1 if _failures else 0)

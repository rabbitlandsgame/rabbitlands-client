extends SceneTree
## Offline reproducible presentation preview. Uses the existing Greenlight
## package and current imported actors; it never connects or changes a save.
const Presentation := preload("res://src/world/campaign_scene.gd")
const FieldHud := preload("res://src/ui/campaign_hud.gd")
var _failures := 0
var _directory := ""

class PreviewRig extends Node3D:
	var camera: Camera3D
	var focus := Vector3(15.5, 2.5, 140.5)
	var distance := 17.0
	var pitch_degrees := -45.0
	var yaw_degrees := 0.0
	func cancel_rotation() -> void:
		pass

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		_failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func run() -> void:
	Engine.max_fps = 30
	_directory = OS.get_environment("RL_CAMPAIGN_PREVIEW_OUT")
	if _directory.is_empty():
		_directory = "C:/rabbitlands/work-output/campaign-preview"
	DirAccess.make_dir_recursive_absolute(_directory)
	root.size = Vector2i(1280, 720)
	var network := root.get_node("Network")
	network.call("block_for_hud_preview")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	expect(main.has_method("_update_campaign"), "production main includes the campaign integration")
	main.hide()
	var stage := Node3D.new()
	root.add_child(stage)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-48, -35, 0)
	light.light_energy = 1.3
	stage.add_child(light)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("8ba9b6")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b8c8d2")
	environment.environment.ambient_light_energy = 0.7
	stage.add_child(environment)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	var loaded := [false]
	loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/greenlight/client/world.json"), Vector3(15.5, 2.5, 135.5))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(loaded[0], "the real Greenlight quay package loads")
	if not loaded[0]:
		quit(1)
		return
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [435, 448], "walkingHeight": 2.5})
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var actors := {}
	for spec: Dictionary in [
		{"id": 1, "type": 1, "name": "New arrival", "x": 450, "y": 308, "kind": 0},
		{"id": 2, "type": 360, "name": "Odo Fenn", "x": 450, "y": 313, "kind": 2},
		{"id": 3, "type": 308, "name": "Landing worker", "x": 457, "y": 319, "kind": 2},
		{"id": 4, "type": 348, "name": "Serit Voss", "x": 452, "y": 303, "kind": 2}]:
		var dto: Dictionary = main.call("_presentation_dto", {"actor_id": spec.id, "actor_type": spec.type,
			"kind": spec.kind, "name": spec.name, "x": spec.x, "y": spec.y, "rotation": 0,
			"health": 100, "max_health": 100, "frame": 0, "appearance": {}})
		var config: Dictionary = registry.models[registry.actorTypes[str(spec.type)]]
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure(dto, adapter, config,
			main.call("_animation_for_model", config), main.get("equipment_config"))
		expect(errors.is_empty(), str(spec.name) + " uses the current imported actor")
		actor.apply_server_state(dto, adapter, true)
		actor.set_nameplate_visible(false)
		for overlay: String in ["MapDot", "Nameplate"]:
			var node := actor.get_node_or_null(overlay) as Node3D
			if node != null:
				node.hide()
		actors[int(spec.id)] = actor
	var rig := PreviewRig.new()
	stage.add_child(rig)
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.current = true
	camera.cull_mask = 3 # Match the production gameplay camera, excluding map-only discs.
	camera.global_position = Vector3(20, 16, 154)
	camera.look_at(Vector3(20, 3.5, 134), Vector3.UP)
	var presentation := Presentation.new()
	root.add_child(presentation)
	presentation.set_reduced_motion(false, false)
	var ordinary: Array = []
	presentation.presentation_finished.connect(func(token: String, reason: String) -> void: ordinary.append([token, reason]))
	var state := {"version": 1, "active": true, "run_id": "offline-preview", "map": "greenlight",
		"title": "The Ferry That Arrived Twice", "hint": "Inspect the landing, then choose a practical way to help.",
		"actors": {"odo": 2, "worker": 3, "voss": 4}, "scene": {"id": "measure.landing.arrival", "token": "preview-arrival", "requires_ack": true, "ack_revision": 1},
		"targets": [{"id": "assess", "object_id": 61001, "label": "Inspect the damaged landing", "tile": [450, 310], "enabled": true, "completed": false}]}
	for frame: int in range(12):
		await process_frame
	presentation.update(0.0, state, rig, actors, 1, "greenlight", true)
	await capture("01-establishing.png")
	presentation.update(6.0, state, rig, actors, 1, "greenlight", true)
	await capture("02-odo-gesture-and-subtitle.png")
	presentation.update(8.0, state, rig, actors, 1, "greenlight", true)
	await capture("03-worker-dialogue.png")
	presentation.skip()
	presentation.update(0.7, state, rig, actors, 1, "greenlight", true)
	expect(not presentation.blocks_input(), "rendered skip restores gameplay control")
	var restored_camera := camera.global_transform
	expect(presentation.request_replay(state, "greenlight"), "the current rendered scene offers explicit replay")
	presentation.update(0.0, state, rig, actors, 1, "greenlight", true)
	await capture("08-replay-establishing.png")
	presentation.update(6.0, state, rig, actors, 1, "greenlight", true)
	await capture("09-replay-odo-gesture.png")
	expect(presentation.playing and bool((actors[2] as Node).get("_cinematic_active")), "replay animates the production imported NPC")
	var odo: ReplicatedActor3D = actors[2]
	var old_target := odo.server_target
	odo.server_target += Vector3(1, 0, 0)
	presentation.skip()
	presentation.update(0.7, state, rig, actors, 1, "greenlight", true)
	expect(odo.global_position.is_equal_approx(odo.server_target), "native replay restores the NPC to its latest replicated target")
	expect(camera.global_transform.is_equal_approx(restored_camera), "native replay restores the gameplay camera")
	presentation.update(0.1, state, rig, actors, 1, "greenlight", true)
	expect(ordinary.size() == 1, "native replay and its next snapshot send no extra original completion")
	odo.server_target = old_target
	odo.global_position = old_target
	var hud := FieldHud.new()
	root.add_child(hud)
	hud.apply_state(state, Vector2i(450, 308), "greenlight")
	await capture("04-gameplay-field-guide.png")
	hud.hide()
	var demonstration := state.duplicate(true)
	demonstration.scene = {"id": "measure.sluice.demonstration", "token": "preview-demonstration", "variant": "pump"}
	presentation.update(0.0, demonstration, rig, actors, 1, "greenlight", true)
	await capture("07-voss-at-the-test-work.png")
	presentation.skip()
	root.size = Vector2i(900, 600)
	root.content_scale_factor = 1.5
	var large_state := state.duplicate(true)
	large_state.hint = "Inspect the damaged landing and help the field crew. Different approaches use different actions. Your cargo priority is a separate decision, with a visible consequence."
	large_state.party_notice = "Opening prototype: solo play. Completed milestones remain saved when you return."
	large_state.targets.clear()
	for index: int in range(14):
		large_state.targets.append({"id": "site-%d" % index, "object_id": 61001 + index,
			"label": "Inspect and stabilize work site %d" % (index + 1), "tile": [450, 310], "enabled": true, "completed": false})
	hud.apply_state(large_state, Vector2i(450, 308), "greenlight")
	await capture("05-small-window-150-percent.png")
	var logical := root.get_visible_rect().size
	expect(hud._panel.get_global_rect().end.y <= logical.y + 0.5, "the field guide stays inside a small window at 150 percent scale")
	hud._body_scroll.ensure_control_visible(hud._reduced)
	await capture("06-small-window-scroll-controls.png")
	expect(hud._body_scroll.get_v_scroll_bar().max_value > hud._body_scroll.get_v_scroll_bar().page,
		"the whole guide scrolls so its last controls remain reachable")
	expect(await ContinentChunkStream.drain_workers(self), "preview workers retire before renderer shutdown")
	var report := FileAccess.open(_directory.path_join("report.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"failures": _failures, "offline": true, "map": "greenlight",
		"actor_models": ["ssarathi_male", "luminous_male", "voss-type-348"], "logical_small_window": [logical.x, logical.y]}, "  "))
	hud.queue_free()
	presentation.queue_free()
	stage.queue_free()
	main.queue_free()
	for frame: int in range(6):
		await process_frame
	print("rendered campaign presentation: ", _failures, " failures")
	quit(1 if _failures else 0)

func capture(filename: String) -> void:
	for frame: int in range(6):
		await process_frame
	await RenderingServer.frame_post_draw
	var error := root.get_texture().get_image().save_png(_directory.path_join(filename))
	expect(error == OK, "captured " + filename)

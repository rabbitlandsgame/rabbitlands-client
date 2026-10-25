extends "res://tests/integration/rendered_campaign_scene.gd"
## Offline visual QA of the real Twinbrook package, private apparatus, native
## cast and party controls. No server, account, save or paid asset work is used.
const Works := preload("res://src/world/campaign_works.gd")
var _stage_world: World3D

func surface_height(point: Vector3) -> float:
	if _stage_world == null:
		return NAN
	var query := PhysicsRayQueryParameters3D.create(Vector3(point.x, 400, point.z),
		Vector3(point.x, -100, point.z), WorldLoader.NAVIGATION_SURFACE_LAYER)
	var result := _stage_world.direct_space_state.intersect_ray(query)
	var hit: Variant = result.get("position")
	return (hit as Vector3).y + 0.025 if hit is Vector3 else NAN

func run() -> void:
	Engine.max_fps = 30
	_directory = "C:/rabbitlands/work-output/campaign-twinbrook-preview"
	DirAccess.make_dir_recursive_absolute(_directory)
	root.size = Vector2i(1280, 720)
	root.get_node("Network").call("block_for_hud_preview")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	expect(main.has_method("_on_campaign_scene_finished"), "production main includes party scene acknowledgments")
	main.hide()
	var stage := Node3D.new()
	root.add_child(stage)
	_stage_world = stage.get_world_3d()
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_energy = 0.85
	stage.add_child(sun)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("8ba9b6")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b8c8d2")
	environment.environment.ambient_light_energy = 0.5
	stage.add_child(environment)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	var loaded := [false]
	loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/twinbrook/client/world.json"), Vector3(-99.5, 158, 120.5))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(loaded[0], "the existing Twinbrook terrain package loads")
	if not loaded[0]:
		quit(1)
		return
	for frame: int in range(30):
		await process_frame
	var adapter := CoordinateAdapter.new({"serverOrigin": [459, 219], "walkingHeight": 121.6})
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var actors := {}
	var worker_dto: Dictionary = {}
	for spec: Dictionary in [
		{"id": 1, "type": 1, "name": "New arrival", "x": 359, "y": 99, "kind": 0},
		{"id": 2, "type": 360, "name": "Odo Fenn", "x": 363, "y": 93, "kind": 2},
		{"id": 3, "type": 308, "name": "Works Hand", "x": 372, "y": 87, "kind": 2},
		{"id": 4, "type": 348, "name": "Serit Voss", "x": 370, "y": 87, "kind": 2}]:
		var dto: Dictionary = main.call("_presentation_dto", {"actor_id": spec.id, "actor_type": spec.type,
			"kind": spec.kind, "name": spec.name, "x": spec.x, "y": spec.y, "rotation": 0,
			"health": 100, "max_health": 100, "frame": 0, "appearance": {}})
		var config: Dictionary = registry.models[registry.actorTypes[str(spec.type)]]
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure(dto, adapter, config,
			main.call("_animation_for_model", config), main.get("equipment_config"))
		expect(errors.is_empty(), str(spec.name) + " uses the approved native actor")
		actor.apply_server_state(dto, adapter, true)
		var grounded := surface_height(actor.global_position)
		expect(is_finite(grounded), str(spec.name) + " has a real navigation surface")
		if is_finite(grounded):
			actor.set_surface_height(grounded)
		actor.set_nameplate_visible(false)
		for overlay: String in ["MapDot", "Nameplate"]:
			var node := actor.get_node_or_null(overlay) as Node3D
			if node != null:
				node.hide()
		actors[int(spec.id)] = actor
		if int(spec.id) == 3:
			worker_dto = dto
	var rig := PreviewRig.new()
	stage.add_child(rig)
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.current = true
	camera.cull_mask = 3
	camera.global_position = Vector3(-90, 175, 145)
	camera.look_at(Vector3(-91, 159, 128), Vector3.UP)
	var state := {"version": 1, "active": true, "run_id": "offline-party-preview", "map": "twinbrook",
		"title": "The Work at Twinbrook", "hint": "Release the crew before installing the saved fitting.",
		"actors": {"odo": 2, "worker": 3, "voss": 4},
		"scene": {"id": "measure.twinbrook.arrival", "token": "arrival", "variant": "pump"},
		"anchors": {"bypass": [368, 88], "sluice_prop": [370, 85], "voss_work": [370, 87], "gauge": [367, 95], "flow": [366, 91], "worker_trapped": [372, 87],
			"worker_safe": [372, 97], "intake": [360, 89], "diversion": [364, 89], "fitting": [363, 87]},
		"mechanism": {"bypass_open": false, "fitting": false, "crew_safe": false, "flow": 0, "gauge": 0, "claimed_gauge": 2},
		"targets": [{"id": "gauge", "object_id": 62009, "label": "Read the independent gauge", "tile": [367, 94], "enabled": true, "completed": false}],
		"party": {"owner": "Aster", "role": "eligible", "members": [
			{"name": "Aster", "role": "owner", "online": true, "present": true, "adoption": "adopted"},
			{"name": "Birch", "role": "eligible", "online": true, "present": true, "adoption": "pending"},
			{"name": "Cedar", "role": "helper", "online": true, "present": true, "adoption": "help_only"}]},
		"adoption": {"state": "pending", "run_id": "offline-party-preview", "revision": 15, "can_adopt": true,
			"summary": "The saved pump fitting is installed. The owner chose a public account.", "reason": ""}}
	var works := Works.new()
	stage.add_child(works)
	deadline = Time.get_ticks_msec() + 15000
	while not is_instance_valid(works.gate) and Time.get_ticks_msec() < deadline:
		works.apply_snapshot(state, adapter, "twinbrook", surface_height)
		await process_frame
	expect(is_instance_valid(works.gate), "the approved timber sluice stands at the private work")
	if not is_instance_valid(works.gate):
		await ContinentChunkStream.drain_workers(self)
		quit(1)
		return
	expect(works.gate.global_position.y > 155 and works.gate.global_position.is_equal_approx(works.points.sluice_prop), "the physical gate ignores the cold registry fallback and uses its separate grounded footprint")
	expect(works.gate.scale.is_equal_approx(Vector3.ONE) and is_zero_approx(works.gate.rotation.y), "the approved native asset retains unit scale and its validated orientation")
	var presentation := Presentation.new()
	root.add_child(presentation)
	presentation.set_reduced_motion(false, false)
	presentation.update(0, state, rig, actors, 1, "twinbrook", true, adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("01-twinbrook-establishing.png")
	presentation.update(6, state, rig, actors, 1, "twinbrook", true, adapter, surface_height)
	expect(is_equal_approx((actors[4] as Node3D).global_position.z, adapter.tile_center(370, 87).z + 1.0), "Voss steps one metre toward the real timber surface before bracing")
	expect(not works.labels.bypass.visible and not works.labels.gauge.visible, "the close shot keeps interface labels off the cast")
	await capture("02-voss-braces-native-sluice.png")
	presentation.skip()
	state.mechanism.bypass_open = true
	works.apply_snapshot(state, adapter, "twinbrook", surface_height)
	worker_dto.x = 372
	worker_dto.y = 97
	(actors[3] as ReplicatedActor3D).apply_server_state(worker_dto, adapter, true)
	(actors[3] as ReplicatedActor3D).set_surface_height(surface_height(adapter.tile_center(372, 97)))
	state.scene = {"id": "measure.twinbrook.voss_rescue", "token": "rescue", "variant": "pump"}
	presentation.update(0, state, rig, actors, 1, "twinbrook", true, adapter, surface_height)
	presentation.update(5, state, rig, actors, 1, "twinbrook", true, adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("03-worker-crosses-to-safety.png")
	presentation.update(12, state, rig, actors, 1, "twinbrook", true, adapter, surface_height)
	expect(not presentation.blocks_input(), "the rescue returns control before fitting work")
	state.scene = {}
	works.set_readouts_visible(true)
	state.hint = "Open the intake and diversion, run a controlled test, then compare the independent gauge with the permit."
	state.mechanism.crew_safe = true
	state.mechanism.fitting = true
	state.mechanism.flow = 1
	state.mechanism.gauge = 2
	works.apply_snapshot(state, adapter, "twinbrook", surface_height)
	works._process(1)
	var gauge: Vector3 = works.points.gauge
	camera.global_position = gauge + Vector3(3, 3.2, 5)
	camera.look_at(gauge + Vector3(0, 1.3, 0), Vector3.UP)
	await capture("04-intake-only-reading-two.png")
	state.mechanism.flow = 2
	state.mechanism.gauge = 1
	works.apply_snapshot(state, adapter, "twinbrook", surface_height)
	works._process(1)
	await capture("05-stable-reading-one-versus-claim-two.png")
	state.hint = "The tested delivery is one unit; the permit claims two. Choose whether to record the expedition's account for your own story."
	state.companion = {"name": "Odo Fenn", "mode": "wait", "status": "Waiting beside the work.", "can_command": false}
	var hud := FieldHud.new()
	root.add_child(hud)
	hud.apply_state(state, Vector2i(367, 95), "twinbrook")
	await capture("06-party-personal-adoption.png")
	root.size = Vector2i(900, 600)
	root.content_scale_factor = 1.5
	for name: String in ["Dahlia", "Elm", "Fern", "Gorse", "Hazel"]:
		state.party.members.append({"name": name, "role": "helper", "online": true, "present": true, "adoption": "help_only"})
	hud.apply_state(state, Vector2i(367, 95), "twinbrook")
	await process_frame
	await process_frame
	hud._body_scroll.ensure_control_visible(hud._record)
	await capture("07-eight-person-roster-at-150-percent.png")
	var clip := hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._record.get_global_rect()) and clip.encloses(hud._help_only.get_global_rect()), "both actual Record and Help Only button rectangles are visible after scrolling an eight-player 150-percent window")
	hud._body_scroll.ensure_control_visible(hud._companion_buttons.help)
	await capture("08-small-window-companion-controls.png")
	clip = hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._companion_buttons.follow.get_global_rect()) and clip.encloses(hud._companion_buttons.help.get_global_rect()), "the entire compact companion command row is reachable in the scaled viewport")
	root.content_scale_factor = 1.0
	root.size = Vector2i(1280, 720)
	state.party.role = "owner"
	state.adoption = {}
	state.cargo = "medical"
	state.hint = "The crew operates the manual bypass. Odo can follow, wait, regroup at a safe post, or help with the physical work."
	state.companion = {"name": "Odo Fenn", "mode": "help", "status": "Helping brace the manual bypass.", "can_command": true}
	works.apply_snapshot(state, adapter, "twinbrook", surface_height)
	var fitting: Vector3 = works.points.fitting
	camera.global_position = fitting + Vector3(5, 4, 7)
	camera.look_at(fitting + Vector3(1, 1, -1), Vector3.UP)
	hud.apply_state(state, Vector2i(363, 87), "twinbrook")
	await process_frame
	await process_frame
	hud._body_scroll.ensure_control_visible(hud._companion_buttons.help)
	await capture("09-medical-bypass-and-owner-companion.png")
	expect(works.labels.fitting.text == "Manual bypass · braced" and not hud._companion_buttons.help.disabled, "medical work and owner companion commands describe the actual branch")
	expect(await ContinentChunkStream.drain_workers(self), "all map imports retire before renderer shutdown")
	var report := FileAccess.open(_directory.path_join("report.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"failures": _failures, "offline": true, "map": "twinbrook",
		"native_asset": Works.SLUICE_ASSET, "measured_stable": 1, "claimed": 2, "party_members": 8}, "  "))
	hud.queue_free()
	presentation.queue_free()
	stage.queue_free()
	main.queue_free()
	for frame: int in range(6):
		await process_frame
	print("rendered Twinbrook campaign: ", _failures, " failures")
	quit(1 if _failures else 0)

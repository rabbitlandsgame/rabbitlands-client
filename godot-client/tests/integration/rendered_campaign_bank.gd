extends "res://tests/integration/rendered_campaign_scene.gd"
## Offline QA of the actual Landfall package and approved cast/props. Server-
## shaped updates demonstrate the visuals; no account or objective is changed.
const BankWorks := preload("res://src/world/campaign_bank_works.gd")
const BankFixture := preload("res://tests/test_campaign_bank.gd")
const FadeManager := preload("res://src/world/occluder_fade_manager.gd")
var _stage_world: World3D
var _adapter: CoordinateAdapter
var _actors: Dictionary = {}
var _actor_dtos: Dictionary = {}
var _fade := FadeManager.new()
var _preview_loader: WorldLoader
var _preview_camera: Camera3D
var _preview_focus: Node3D
var _presentation: Node

func _look_at(point: Vector3, _up := Vector3.UP) -> void:
	_preview_camera.look_at(point, Vector3.UP)
	_preview_focus.global_position = point - Vector3.UP

func capture(filename: String) -> void:
	for frame: int in range(12):
		_fade.sync_worlds(_preview_loader.manifest, _preview_loader.world_root, {})
		var focus := _presentation.occlusion_focus() as Node3D if is_instance_valid(_presentation) and _presentation.playing else _preview_focus
		_fade.update(1.0 / 30.0, _preview_camera, focus)
		await process_frame
	await RenderingServer.frame_post_draw
	var error := root.get_texture().get_image().save_png(_directory.path_join(filename))
	expect(error == OK, "captured " + filename)

func surface_height(point: Vector3) -> float:
	if _stage_world == null:
		return NAN
	var query := PhysicsRayQueryParameters3D.create(Vector3(point.x, 400, point.z),
		Vector3(point.x, -100, point.z), WorldLoader.NAVIGATION_SURFACE_LAYER)
	var result := _stage_world.direct_space_state.intersect_ray(query)
	var hit: Variant = result.get("position")
	return (hit as Vector3).y + 0.025 if hit is Vector3 else NAN

func place_actor(id: int, tile: Vector2i, teleport := true) -> void:
	var dto: Dictionary = _actor_dtos[id]
	dto.x = tile.x
	dto.y = tile.y
	var actor: ReplicatedActor3D = _actors[id]
	actor.apply_server_state(dto, _adapter, teleport)
	var ground := surface_height(_adapter.tile_center(tile.x, tile.y))
	if is_finite(ground):
		actor.set_surface_height(ground)

func run() -> void:
	Engine.max_fps = 30
	_directory = OS.get_environment("RL_BANK_PREVIEW_OUT")
	if _directory.is_empty():
		_directory = "C:/rabbitlands/work-output/campaign-bank-preview"
	DirAccess.make_dir_recursive_absolute(_directory)
	root.size = Vector2i(1280, 720)
	root.get_node("Network").call("block_for_hud_preview")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	expect(main.get("campaign_bank_works") != null, "production Main owns the isolated bank presenter")
	main.hide()
	var stage := Node3D.new()
	root.add_child(stage)
	_stage_world = stage.get_world_3d()
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_energy = 0.8
	stage.add_child(sun)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("8ba9b6")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b8c8d2")
	environment.environment.ambient_light_energy = 0.55
	stage.add_child(environment)
	var loader := WorldLoader.new()
	_preview_loader = loader
	stage.add_child(loader)
	var loaded := [false]
	loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/landfall/client/world.json"), Vector3(-151.5, 121.5, -27.5))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(loaded[0], "the existing Landfall orchard terrain package loads")
	if not loaded[0]:
		quit(1)
		return
	_adapter = CoordinateAdapter.new({"serverOrigin": [282, 248], "metresPerTile": 1.0, "walkingHeight": 90.0})
	var state := BankFixture.state()
	state.key = "trail"
	state.scene = {"id": "measure.bank.arrival", "token": "arrival", "variant": "protected"}
	state.bank.approach = ""
	state.hint = "Choose a safe approach and read the cart, packing and channel traces."
	var works := BankWorks.new()
	stage.add_child(works)
	deadline = Time.get_ticks_msec() + 20000
	while not is_instance_valid(works.gate) and Time.get_ticks_msec() < deadline:
		works.apply_snapshot(state, _adapter, "landfall", surface_height)
		await process_frame
	expect(is_instance_valid(works.gate), "the work props wait for real terrain and then stand at the approved anchors")
	if not is_instance_valid(works.gate):
		await ContinentChunkStream.drain_workers(self)
		quit(1)
		return
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	for spec: Dictionary in [
		{"id": 1, "type": 1, "name": "Field observer", "x": 130, "y": 275, "kind": 0},
		{"id": 2, "type": 360, "name": "Odo Fenn", "x": 133, "y": 281, "kind": 2},
		{"id": 3, "type": 308, "name": "Grove Works Hand", "x": 166, "y": 284, "kind": 2},
		{"id": 4, "type": 376, "name": "Ammet Sorrel", "x": 135, "y": 281, "kind": 2}]:
		var dto: Dictionary = main.call("_presentation_dto", {"actor_id": spec.id, "actor_type": spec.type,
			"kind": spec.kind, "name": spec.name, "x": spec.x, "y": spec.y, "rotation": 0,
			"health": 100, "max_health": 100, "frame": 0, "appearance": {}})
		var config: Dictionary = registry.models[registry.actorTypes[str(spec.type)]]
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure(dto, _adapter, config,
			main.call("_animation_for_model", config), main.get("equipment_config"))
		expect(errors.is_empty(), str(spec.name) + " uses the approved native actor")
		_actors[int(spec.id)] = actor
		_actor_dtos[int(spec.id)] = dto
		place_actor(int(spec.id), Vector2i(spec.x, spec.y))
		expect(is_finite(surface_height(actor.global_position)), str(spec.name) + " has real ground beneath the feet")
		actor.set_nameplate_visible(false)
		for overlay: String in ["MapDot", "Nameplate"]:
			var node := actor.get_node_or_null(overlay) as Node3D
			if node != null:
				node.hide()
	var rig := PreviewRig.new()
	stage.add_child(rig)
	var camera := Camera3D.new()
	_preview_camera = camera
	_preview_focus = Node3D.new()
	stage.add_child(_preview_focus)
	_fade.set_enabled(true)
	rig.add_child(camera)
	rig.camera = camera
	camera.current = true
	camera.cull_mask = 3
	camera.global_position = works.points.briefing + Vector3(8, 8, 12)
	_look_at(works.points.briefing + Vector3(0, 1, -2))
	var presentation := Presentation.new()
	_presentation = presentation
	root.add_child(presentation)
	presentation.set_reduced_motion(false, false)
	if OS.get_environment("RL_BANK_CAMERA_SWEEP") == "1":
		DirAccess.make_dir_recursive_absolute(_directory.path_join("qa-angles"))
		for key: String in ["gauge", "model"]:
			var index := 0
			for offset: Vector3 in [Vector3(0, 3.5, 6), Vector3(6, 3.5, 0), Vector3(-6, 3.5, 0), Vector3(0, 3.5, -6), Vector3(4, 4, 4), Vector3(-4, 4, 4), Vector3(4, 4, -4), Vector3(-4, 4, -4)]:
				camera.global_position = works.points[key] + offset
				_look_at(works.points[key] + Vector3.UP * 1.3)
				await capture("qa-angles/%s-%d.png" % [key, index])
				index += 1
	presentation.update(0, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("01-orchard-establishing.png")
	presentation.update(10, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	await capture("02-ammet-and-inherited-witness-account.png")
	expect(presentation.transcript_text().contains("unnamed"), "the protected opening changes Ammet's actual briefing")
	presentation.skip()
	state.bank.approach = "planks"
	state.bank.crossing_ready = true
	state.targets.append({"id": "route_walk", "object_id": 0, "label": "Walk the prepared crossing",
		"tile": [145, 280], "approach": [145, 280], "enabled": true, "completed": false})
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	state.scene = {"id": "measure.bank.trail", "token": "trail", "variant": "planks"}
	presentation.update(0, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	presentation.update(5, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("03-native-route-cinematic.png")
	presentation.skip()
	state.scene = {}
	works.set_readouts_visible(true)
	state.bank.route_step = 2
	state.targets.back().tile = [148, 280]
	state.targets.back().approach = [148, 280]
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	place_actor(1, Vector2i(145, 280))
	camera.global_position = works.points.crossing + Vector3(5, 3.5, 6)
	_look_at(works.points.crossing + Vector3(0, 0.7, 0))
	await capture("04-prepared-native-jetty-and-walk-pin.png")
	expect(works.crossing.visible and works.checkpoint.visible, "the prepared crossing and next walking checkpoint are visibly distinct")
	var deck_helper := works.crossing.find_child("Walk_*", true, false) as MeshInstance3D
	if deck_helper != null:
		var deck_top: Vector3 = deck_helper.global_transform * Vector3(0, deck_helper.get_aabb().end.y, 0)
		expect(absf((_actors[1] as Node3D).global_position.y - deck_top.y - 0.025) < 0.04, "the native observer's feet follow the visible deck rather than sinking into decorative grass")
	state.targets.pop_back()
	state.key = "remedy"
	state.scene = {"id": "measure.bank.remedy", "token": "model", "variant": ""}
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	presentation.update(0, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	presentation.update(3, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("05-worker-speaking-without-field-readouts.png")
	expect(not works.labels.gauge.visible and not works.labels.model.visible, "the worker closeup hides every field readout")
	presentation.update(6, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("05b-worker-at-the-model-controls.png")
	presentation.skip()
	state.scene = {}
	state.bank.diversion = 1
	state.bank.reading = 2
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	works.set_readouts_visible(true)
	works._process(1)
	camera.global_position = works.points.gauge + Vector3(2, 2.6, -3)
	_look_at(works.points.gauge + Vector3(0, 1.3, 0))
	await capture("06-unsteady-two-unit-model.png")
	state.bank.diversion = 2
	state.bank.reading = 1
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	works._process(1)
	await capture("07-steady-one-unit-model.png")
	state.bank.remedy = "reserve"
	state.bank.cost = "Spend the grove's finite emergency reserve."
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	camera.global_position = works.points.reserve + Vector3(2, 2.1, -3)
	_look_at(works.points.reserve + Vector3(0, 0.8, 0))
	await capture("08-reserve-selected-before-physical-work.png")
	state.bank.remedy_complete = true
	state.bank.consequence = "The grove emergency reserve is spent."
	state.key = "account"
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	await capture("09-reserve-spent-after-physical-work.png")
	expect(not works.reserve.visible, "the paid physical remedy visibly consumes its bounded reserve")
	state.scene = {"id": "measure.bank.reconstruction", "token": "reconstruction", "variant": "reserve"}
	presentation.update(0, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	presentation.update(6, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("10-odo-sets-up-the-reconstruction.png")
	presentation.skip()
	state.scene = {}
	works.set_readouts_visible(true)
	state.bank.sequence_step = 1
	place_actor(1, Vector2i(163, 282))
	place_actor(2, Vector2i(162, 282))
	for tile: Vector2i in [Vector2i(161, 283), Vector2i(160, 284), Vector2i(159, 285), Vector2i(158, 286), Vector2i(157, 287)]:
		place_actor(2, tile, false)
		place_actor(1, tile + Vector2i(1, 0), false)
		for frame: int in range(5):
			await process_frame
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	camera.global_position = _actors[2].global_position + Vector3(5, 4, 7)
	_look_at(_actors[2].global_position + Vector3(0, 1, -1))
	await capture("11-walking-the-physical-markers-with-odo.png")
	state.bank.misplaced = "trace_intake"
	state.bank.last_error = "That marker contradicts the load traces. Lift it, then compare the channel split."
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	place_actor(1, Vector2i(152, 288))
	place_actor(2, Vector2i(153, 288))
	camera.global_position = works.points.marker_3 + Vector3(1.5, 2.0, -3)
	_look_at(works.points.marker_3 + Vector3(0, 0.8, 0))
	await capture("12-liftable-wrong-marker-with-saved-progress.png")
	expect((works.markers.marker_3.material_override as StandardMaterial3D).albedo_color.is_equal_approx(Color("ef6f55")), "the misplaced physical marker is red while the verified delivery marker remains saved")
	state.adoption = {"state": "pending", "run_id": state.run_id, "revision": 9, "can_adopt": true,
		"summary": "The crossing used two boards. This remedy spent the grove's bounded reserve.", "reason": ""}
	state.companion = {"name": "Odo Fenn", "mode": "follow", "status": "Walking the field observations with the story owner.", "can_command": false}
	for name: String in ["Cedar", "Dahlia", "Elm", "Fern", "Gorse", "Hazel"]:
		state.party.members.append({"name": name, "role": "helper", "online": true, "present": true, "adoption": "help_only"})
	var hud := FieldHud.new()
	root.add_child(hud)
	root.size = Vector2i(900, 600)
	root.content_scale_factor = 1.5
	hud.apply_state(state, Vector2i(152, 288), "landfall")
	await process_frame
	await process_frame
	hud._body_scroll.ensure_control_visible(hud._record)
	await capture("13-eight-person-costs-and-personal-record-at-150-percent.png")
	var clip := hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._record.get_global_rect()) and clip.encloses(hud._help_only.get_global_rect()), "both actual personal decision buttons stay visible in the eight-person scaled window")
	hud._body_scroll.ensure_control_visible(hud._reduced)
	await capture("14-small-window-bottom-controls.png")
	clip = hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._leave.get_global_rect()) and clip.encloses(hud._reduced.get_global_rect()), "Return and reduced-motion controls remain reachable at the bottom")
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1
	hud.hide()
	state.bank.misplaced = ""
	state.bank.last_error = ""
	state.bank.sequence_step = 3
	state.bank.sequence_correct = true
	state.bank.disclosure = "protected"
	state.scene = {"id": "measure.bank.resolved", "token": "resolved", "variant": "protected"}
	place_actor(1, Vector2i(136, 282))
	place_actor(2, Vector2i(133, 281))
	works.apply_snapshot(state, _adapter, "landfall", surface_height)
	presentation.update(0, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	presentation.update(6, state, rig, _actors, 1, "landfall", true, _adapter, surface_height)
	works.set_readouts_visible(presentation.work_readouts_visible())
	await capture("15-account-and-next-work-team-lead.png")
	presentation.skip()
	_fade.reset()
	expect(await ContinentChunkStream.drain_workers(self), "all Landfall import workers retire before the preview closes")
	var deck_height: float = surface_height(_adapter.tile_center(145, 280))
	works.clear()
	await physics_frame
	await physics_frame
	expect(surface_height(_adapter.tile_center(145, 280)) < deck_height - 0.05, "leaving the private work removes its temporary deck navigation surface")
	var report := FileAccess.open(_directory.path_join("report.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"failures": _failures, "offline": true, "map": "landfall",
		"native_assets": [BankWorks.SLUICE_ASSET, BankWorks.JETTY_ASSET, BankWorks.CRATE_ASSET],
		"measured_stable": 1, "claimed": 2, "party_members": 8, "screenshots": 16}, "  "))
	hud.queue_free()
	presentation.queue_free()
	stage.queue_free()
	main.queue_free()
	for frame: int in range(6):
		await process_frame
	print("rendered bank campaign: ", _failures, " failures")
	quit(1 if _failures else 0)

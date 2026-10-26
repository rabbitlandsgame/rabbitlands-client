extends "res://tests/integration/rendered_campaign_bank.gd"
## Offline, native-world acceptance. Updates below are saved-server-shaped poses;
## this fixture neither connects nor claims that cinematics complete gameplay.
const RoadWorks := preload("res://src/world/campaign_road_works.gd")
const RoadFixture := preload("res://tests/test_campaign_road.gd")
var _stage: Node3D
var _rig: PreviewRig
var _main: Node
var _works: Node
var _assertions := 0
var _captures := 0

func expect(ok: bool, message: String) -> void:
	_assertions += 1
	super.expect(ok, message)

func capture(filename: String) -> void:
	_captures += 1
	await super.capture(filename)

func spawn(id: int, type: int, name_text: String, tile: Vector2i, kind := 2) -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var dto: Dictionary = _main.call("_presentation_dto", {"actor_id": id, "actor_type": type,
		"kind": kind, "name": name_text, "x": tile.x, "y": tile.y, "rotation": 0,
		"health": 100, "max_health": 100, "frame": 0, "appearance": {}})
	var config: Dictionary = registry.models[registry.actorTypes[str(type)]]
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	var errors := actor.configure(dto, _adapter, config,
		_main.call("_animation_for_model", config), _main.get("equipment_config"))
	expect(errors.is_empty(), name_text + " uses an approved native body and animations")
	_actors[id] = actor
	_actor_dtos[id] = dto
	place_actor(id, tile)
	actor.set_nameplate_visible(false)
	for overlay: String in ["MapDot", "Nameplate"]:
		var node := actor.get_node_or_null(overlay) as Node3D
		if node != null:
			node.hide()

func load_site(map: String) -> bool:
	_stage = Node3D.new()
	root.add_child(_stage)
	_stage_world = _stage.get_world_3d()
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-48, -35, 0)
	light.light_energy = 0.8
	_stage.add_child(light)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("8ba9b6")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b8c8d2")
	environment.environment.ambient_light_energy = 0.55
	_stage.add_child(environment)
	var maps: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_adapter = CoordinateAdapter.new(maps.maps[map].coordinateTransform)
	_preview_loader = WorldLoader.new()
	_stage.add_child(_preview_loader)
	var loaded := [false]
	_preview_loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	var tile := Vector2i(218, 101) if map == "hearthcroft" else Vector2i(291, 77)
	_preview_loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/" + map + "/client/world.json"), _adapter.tile_center(tile.x, tile.y))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(loaded[0], "the actual " + map + " terrain package loads")
	if not loaded[0]:
		return false
	_rig = PreviewRig.new()
	_stage.add_child(_rig)
	_preview_camera = Camera3D.new()
	_rig.add_child(_preview_camera)
	_rig.camera = _preview_camera
	_preview_camera.current = true
	_preview_camera.cull_mask = 3
	_preview_focus = Node3D.new()
	_stage.add_child(_preview_focus)
	_fade.set_enabled(true)
	_works = RoadWorks.new()
	_stage.add_child(_works)
	return true

func aim(tile: Vector2i, offset: Vector3, target_height := 1.0) -> void:
	var at := _adapter.tile_center(tile.x, tile.y)
	at.y = surface_height(at)
	_preview_camera.global_position = at + offset
	_look_at(at + Vector3.UP * target_height)

func apply_scene(state: Dictionary, seconds := 0.0) -> void:
	_works.apply_snapshot(state, _adapter, str(state.map), surface_height)
	_presentation.update(0, state, _rig, _actors, 1, str(state.map), true, _adapter, surface_height)
	var deadline := Time.get_ticks_msec() + 45000
	while not _presentation.playing and Time.get_ticks_msec() < deadline:
		await process_frame
		_presentation.update(0, state, _rig, _actors, 1, str(state.map), true, _adapter, surface_height)
	expect(_presentation.playing, "the scene waits for its actual cast and every required ground anchor")
	if seconds > 0:
		_presentation.update(seconds, state, _rig, _actors, 1, str(state.map), true, _adapter, surface_height)
	_works.set_readouts_visible(_presentation.work_readouts_visible())

func run() -> void:
	Engine.max_fps = 30
	_directory = OS.get_environment("RL_ROAD_PREVIEW_OUT")
	if _directory.is_empty():
		_directory = "C:/rabbitlands/work-output/campaign-road-preview"
	DirAccess.make_dir_recursive_absolute(_directory)
	root.size = Vector2i(1280, 720)
	root.get_node("Network").call("block_for_hud_preview")
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(_main)
	await process_frame
	expect(_main.get("campaign_road_works") != null, "production Main owns the isolated road presenter")
	_main.hide()
	_presentation = Presentation.new()
	root.add_child(_presentation)
	_presentation.set_reduced_motion(false, false)
	if not await load_site("hearthcroft"):
		quit(1)
		return
	for spec: Array in [[1, 1, "Field observer", 202, 92], [2, 360, "Odo Fenn", 208, 98],
		[3, 308, "Farm Works Hand", 205, 101], [4, 332, "Oyun Tarag", 210, 98],
		[7, 593, "Crown Stag", 224, 96], [8, 593, "Crown Stag", 226, 96], [9, 593, "Crown Stag", 228, 96],
		[10, 308, "Nessa Reed", 193, 92], [11, 225, "Injured river otter", 191, 95]]:
		spawn(int(spec[0]), int(spec[1]), str(spec[2]), Vector2i(spec[3], spec[4]), 0 if int(spec[0]) == 1 else 2)
	spawn(12, 308, "Perrin Vale", Vector2i(207, 107))
	spawn(13, 308, "Iva Moss", Vector2i(199, 107))
	var state := RoadFixture.state()
	state.actors = {"odo": 2, "worker": 3, "oyun": 4, "missing_worker": 10, "lead_driver": 12, "rear_driver": 13}
	var rear: Dictionary = state.road.carts[0].duplicate(true)
	rear.id = "rear"
	rear.tile = [199, 105]
	state.road.carts.append(rear)
	state.anchors.stable_2 = [261, 103]
	var deadline := Time.get_ticks_msec() + 20000
	while _works.carts.size() != 2 and Time.get_ticks_msec() < deadline:
		_works.apply_snapshot(state, _adapter, "hearthcroft", surface_height)
		await process_frame
	expect(_works.carts.size() == 2, "both accepted cart poses wait for actual terrain before appearing")
	aim(Vector2i(207, 101), Vector3(9, 9, 13))
	await apply_scene(state)
	await capture("01-hearthcroft-crew-and-native-carts.png")
	await apply_scene(state, 5)
	await capture("02-oyun-free-meal-and-six-workers.png")
	expect(not _works.labels.cart_lead.visible, "the speaking closeup hides the field readouts")
	await apply_scene(state, 7)
	await capture("03-clear-loading-work-view.png")
	_presentation.skip()
	state.scene = {}
	state.road.preparation = "shared_load"
	for row: Dictionary in state.road.carts:
		row.cargo_units = 3
	_works.apply_snapshot(state, _adapter, "hearthcroft", surface_height)
	_works.set_readouts_visible(true)
	aim(Vector2i(203, 105), Vector3(3, 4, 8))
	await capture("04-shared-load-on-both-actual-carts.png")
	for step: int in range(1, 14):
		for row: Dictionary in state.road.carts:
			row.tile = [207 + step if row.id == "lead" else 199 + step, 105]
			row.route_index = step
			row.motion_seq = step
			row.state = "moving" if step < 13 else "waiting"
		_works.apply_snapshot(state, _adapter, "hearthcroft", surface_height)
		place_actor(12, Vector2i(207 + step, 107), false)
		place_actor(13, Vector2i(199 + step, 107), false)
		for frame: int in range(8):
			await process_frame
	state.scene = {"id": "measure.road.herd", "token": "herd", "variant": ""}
	state.key = "convoy"
	state.road.stage = "convoy"
	place_actor(2, Vector2i(219, 102))
	place_actor(3, Vector2i(210, 103))
	await apply_scene(state)
	await capture("05-harmless-herd-before-crossing.png")
	for step: int in range(97, 108):
		for id: int in [7, 8, 9]:
			place_actor(id, Vector2i(224 + (id - 7) * 2, step), false)
		for frame: int in range(8):
			await process_frame
	await apply_scene(state, 3)
	await capture("06-animals-cross-ahead-of-stopped-carts.png")
	expect(state.road.carts[0].route_index == 13 and state.road.hazard.state == "warning", "watching animals and a scene never advances a cart checkpoint or resolves its hazard")
	_presentation.skip()
	state.scene = {}
	state.road.hazard = {"index": 2, "kind": "soft_ground", "state": "warning", "solution": ""}
	for row: Dictionary in state.road.carts:
		row.tile = [244 if row.id == "lead" else 236, 105]
		row.route_index = 37
		row.motion_seq = 37
		row.state = "recovering" if row.id == "rear" else "waiting"
		row.lean_deg = 7 if row.id == "rear" else 0
	place_actor(2, Vector2i(241, 102))
	place_actor(3, Vector2i(238, 102))
	place_actor(12, Vector2i(244, 107))
	place_actor(13, Vector2i(236, 107))
	state.scene = {"id": "measure.road.rear_cart", "token": "rear", "variant": "anchor"}
	await apply_scene(state)
	await capture("07-rear-cart-recoverable-ground-warning.png")
	await apply_scene(state, 6)
	await capture("08-crew-and-second-physical-work-site.png")
	_presentation.skip()
	state.scene = {}
	aim(Vector2i(191, 94), Vector3(-4, 3, 6))
	await capture("09-nessa-and-native-injured-otter.png")
	state.road.optional.supper = "safe"
	for tile: Vector2i in [Vector2i(194, 93), Vector2i(195, 94), Vector2i(196, 95), Vector2i(197, 96), Vector2i(198, 97), Vector2i(199, 98), Vector2i(200, 99), Vector2i(201, 99), Vector2i(202, 99)]:
		place_actor(10, tile, false)
		for frame: int in range(5):
			await process_frame
	aim(Vector2i(202, 99), Vector3(4, 3, 6))
	await capture("10-recovered-worker-at-safe-crew-post.png")
	state.adoption = {"state": "pending", "run_id": state.run_id, "revision": 9, "can_adopt": true,
		"summary": "The crew shared the load and kept two finite portions for late arrivals.", "reason": ""}
	for name_text: String in ["Birch", "Cedar", "Dahlia", "Elm", "Fern", "Gorse", "Hazel"]:
		state.party.members.append({"name": name_text, "role": "helper", "online": true, "present": true, "adoption": "help_only"})
	state.companion = {"name": "Odo Fenn", "mode": "follow", "status": "Walking with the story owner.", "can_command": true}
	state.party.role = "eligible"
	var hud := FieldHud.new()
	root.add_child(hud)
	root.size = Vector2i(900, 600)
	root.content_scale_factor = 1.5
	hud.apply_state(state, Vector2i(202, 99), "hearthcroft")
	await process_frame
	await process_frame
	hud._body_scroll.ensure_control_visible(hud._record)
	await capture("11-eight-person-personal-consent-at-150-percent.png")
	var clip := hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(hud._record.is_visible_in_tree() and hud._help_only.is_visible_in_tree() and clip.encloses(hud._record.get_global_rect()) and clip.encloses(hud._help_only.get_global_rect()), "both actual consent buttons remain visible with eight people at 150 percent")
	hud._body_scroll.ensure_control_visible(hud._convoy_actions)
	await capture("12-independent-convoy-orders-at-150-percent.png")
	clip = hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._convoy_buttons.follow.get_global_rect()) and clip.encloses(hud._convoy_buttons.help.get_global_rect()), "the actual convoy commands remain reachable in the small scaled window")
	hud._body_scroll.ensure_control_visible(hud._reduced)
	await capture("13-bottom-return-and-camera-options.png")
	clip = hud._body_scroll.get_global_rect().intersection(root.get_visible_rect())
	expect(clip.encloses(hud._leave.get_global_rect()) and clip.encloses(hud._reduced.get_global_rect()), "Return and camera options remain reachable")
	hud.hide()
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1
	_works.clear()
	expect(_works.carts.is_empty() and _works.props.is_empty(), "leaving the field removes its cart bodies and food presentation")
	_fade.reset()
	expect(await ContinentChunkStream.drain_workers(self), "Hearthcroft workers retire before changing regions")
	_stage.queue_free()
	_actors.clear()
	_actor_dtos.clear()
	for frame: int in range(6):
		await process_frame
	if not await load_site("brambleshaw"):
		quit(1)
		return
	for spec: Array in [[1, 1, "Field observer", 290, 78], [2, 360, "Odo Fenn", 268, 68],
		[5, 348, "Tobin Ware", 291, 77], [6, 308, "Current Carrier", 273, 76]]:
		spawn(int(spec[0]), int(spec[1]), str(spec[2]), Vector2i(spec[3], spec[4]), 0 if int(spec[0]) == 1 else 2)
	state = RoadFixture.state(true)
	state.scene.token = "consignment"
	state.scene.variant = "remembered_casks"
	state.road.tobin_memory = "remembered_casks"
	state.actors = {"odo": 2, "tobin": 5, "carrier": 6}
	deadline = Time.get_ticks_msec() + 20000
	while _works.carts.is_empty() and Time.get_ticks_msec() < deadline:
		_works.apply_snapshot(state, _adapter, "brambleshaw", surface_height)
		await process_frame
	aim(Vector2i(291, 77), Vector3(7, 6, 10))
	await apply_scene(state)
	await capture("14-tobin-witnesses-current-shipment-terms.png")
	expect(_presentation.transcript_text().contains("boat and toll observations"), "Tobin's remembered observations change the personal spoken introduction")
	await apply_scene(state, 7)
	await capture("15-carrier-speaking-clear-of-readouts.png")
	expect(not _works.labels.cart_consignment.visible, "the current carrier closeup hides shipment readouts")
	await apply_scene(state, 5)
	await capture("16-current-cart-seal-weight-and-fittings.png")
	_presentation.skip()
	state.scene = {}
	_works.set_readouts_visible(true)
	for step: int in range(1, 24):
		state.road.carts[0].tile = [273 + step, 80]
		state.road.carts[0].motion_seq = step
		state.road.carts[0].route_index = step
		state.road.carts[0].state = "moving" if step not in [7, 15, 23] else "waiting"
		_works.apply_snapshot(state, _adapter, "brambleshaw", surface_height)
		place_actor(6, Vector2i(273 + step, 76), false)
		for frame: int in range(8):
			await process_frame
		if step in [7, 15, 23]:
			aim(Vector2i(273 + step, 80), Vector3(4, 4, 7))
			await capture("16b-current-consignment-checkpoint-%d.png" % step)
			expect(_works.poses.consignment.seq == step, "the cart and walking carrier reach the accepted discovery checkpoint")
	state.scene = {"id": "measure.road.resolved", "token": "resolved", "variant": "safe_hold"}
	state.road.consignment = {"id": "current-greenlight-fitting", "method": "measure", "agreement": true, "inspected": true, "custody": "safe_hold"}
	await apply_scene(state, 1)
	await capture("17-agreed-safe-custody-and-crew-account.png")
	expect(_presentation.transcript_text().contains("agreed terms") and _presentation.transcript_text().contains("Edda"), "the closing account names custody terms and the next actual crew lead")
	_presentation.skip()
	state.scene.token = "reduced"
	_presentation.set_reduced_motion(true, false)
	await apply_scene(state)
	var pose := _preview_camera.global_transform
	await apply_scene(state, 8)
	expect(_preview_camera.global_transform.is_equal_approx(pose) and not _works.labels.cart_consignment.visible, "reduced motion retains its first speaking shot and matching readout visibility")
	_presentation.skip()
	_works.clear()
	_fade.reset()
	expect(await ContinentChunkStream.drain_workers(self), "all Brambleshaw workers retire before closing")
	var report := FileAccess.open(_directory.path_join("report.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"assertions": _assertions, "captures": _captures,
		"failures": _failures, "offline": true, "maps": ["hearthcroft", "brambleshaw"],
		"party_members": 8, "viewport": [900, 600], "ui_scale": 1.5}, "  "))
	hud.queue_free()
	_presentation.queue_free()
	_stage.queue_free()
	_main.queue_free()
	for frame: int in range(6):
		await process_frame
	print("rendered road campaign: ", _assertions, " checks including ", _captures, " captures; ", _failures, " failures")
	quit(1 if _failures else 0)

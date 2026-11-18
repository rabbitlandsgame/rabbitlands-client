extends "res://tests/integration/rendered_campaign_road.gd"
## Real server-shaped family/mentor and actual published Town interiors.
var _record: Dictionary = {}
var _hero := 1

func load_town(tile: Vector2i) -> bool:
	_stage = Node3D.new(); root.add_child(_stage); _stage_world = _stage.get_world_3d()
	var light := DirectionalLight3D.new(); light.rotation_degrees = Vector3(-48,-35,0); light.light_energy = 0.8
	_stage.add_child(light)
	var env := WorldEnvironment.new(); env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR; env.environment.background_color = Color("171d25")
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color("d8cdb8"); env.environment.ambient_light_energy = 0.8
	_stage.add_child(env)
	var maps: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_adapter = CoordinateAdapter.new(maps.maps.landfall_town.coordinateTransform)
	_preview_loader = WorldLoader.new(); _stage.add_child(_preview_loader)
	var loaded := [false]
	_preview_loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	_preview_loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/landfall_town/client/world.json"), _adapter.tile_center(tile.x,tile.y))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline: await process_frame
	expect(loaded[0], "the real Landfall Town interiors load")
	if not loaded[0]: return false
	_rig = PreviewRig.new(); _stage.add_child(_rig)
	_preview_camera = Camera3D.new(); _rig.add_child(_preview_camera); _rig.camera = _preview_camera
	_preview_camera.current = true; _preview_camera.cull_mask = 3
	_preview_focus = Node3D.new(); _stage.add_child(_preview_focus); _fade.set_enabled(true)
	return true

func native_actor(raw: Dictionary) -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var dto: Dictionary = _main._presentation_dto(raw)
	var model: Dictionary = registry.models[registry.actorTypes[str(int(dto.actor_type))]]
	var body := ReplicatedActor3D.new(); _stage.add_child(body)
	var errors := body.configure(dto, _adapter, model, _main._animation_for_model(model), _main.equipment_config)
	expect(errors.is_empty(), str(dto.name) + " uses an approved native model")
	_actors[int(dto.actor_id)] = body; _actor_dtos[int(dto.actor_id)] = dto
	place_actor(int(dto.actor_id), Vector2i(int(dto.x),int(dto.y)))
	body.set_nameplate_visible(false)

func show_record(state: Dictionary, cast: Dictionary) -> bool:
	_presentation.cancel("next_preview")
	for body: Node in _actors.values(): body.queue_free()
	_actors.clear(); _actor_dtos.clear()
	_record = state.duplicate(true); _hero = int(state.actors.protagonist)
	for raw: Dictionary in cast.values(): native_actor(raw)
	var subject: Dictionary = cast.values()[0]
	var visitor: Dictionary = cast.get("protagonist", {})
	var point := Vector2i(int(visitor.get("x",int(subject.x)-2)),int(visitor.get("y",int(subject.y)-2)))
	if visitor.is_empty():
		# Older evidence did not include the player. Never substitute a
		# different speaking NPC; this fallback is only the regular Human.
		native_actor({"actor_id":_hero,"actor_type":0,"kind":1,"name":"Traveller","x":point.x,"y":point.y,
			"rotation":0,"health":40,"max_health":40,"frame":0,
			"appearance":{"skin":2,"hair":121,"shirt":4,"pants":9,"boots":1,"head":0,"eyes":2}})
	var deadline := Time.get_ticks_msec()+15000
	while not is_finite(surface_height(_adapter.tile_center(point.x,point.y))) and Time.get_ticks_msec()<deadline: await process_frame
	for id: int in _actors: place_actor(id,Vector2i(int(_actor_dtos[id].x),int(_actor_dtos[id].y)))
	aim(point+Vector2i(1,1),Vector3(7,8,10))
	_rig.focus = _adapter.tile_center(point.x,point.y)
	_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	while not _presentation.playing and Time.get_ticks_msec()<deadline:
		await process_frame
		_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	expect(_presentation.playing, "the native actor and terrain readiness barrier admits the scene")
	return _presentation.playing

func run() -> void:
	Engine.max_fps = 30; root.size = Vector2i(1280,720)
	_directory = OS.get_environment("RL_FIRST_PASS_PREVIEW_OUT")
	DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate(); root.add_child(_main)
	await process_frame; _main.hide()
	_presentation = Presentation.new(); root.add_child(_presentation); _presentation.set_auto_dialogue(false,false)
	var family: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_CHECKIN_EVIDENCE")))
	var visit: Dictionary = family.filter(func(row: Dictionary) -> bool: return not row.scene.is_empty() and row.scene.choice.selected=="")[0]
	if not await load_town(Vector2i(29,29)): quit(1); return
	if not await show_record(visit,visit.native_cast): quit(1); return
	expect(_presentation._dialogue._portrait_frame.visible, "Elen's headshot is visible at the real inn")
	await capture("01-liora-at-the-inn.png")
	_presentation.continue_dialogue(); _presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	await capture("02-liora-shares-her-drawing.png")
	_presentation.continue_dialogue(); _presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	expect(_presentation._choice_waiting and _presentation._dialogue._portrait_frame.visible, "the player answers Liora inside the portrait dialogue")
	await capture("03-player-listen-or-rest.png")
	_presentation.cancel("next_preview"); _fade.reset()
	_stage.queue_free(); _actors.clear(); _actor_dtos.clear()
	for _i: int in 4: await process_frame
	var lessons: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_EARLY_MAGIC_EVIDENCE")))
	var heal: Dictionary = (lessons.snapshots as Array).filter(func(row: Dictionary) -> bool: return str(row.scene.get("id",""))=="measure.shelves.basics.heal")[0]
	var teacher: Dictionary = lessons.actors.mentor
	if not await load_town(Vector2i(int(teacher.x),int(teacher.y))): quit(1); return
	if not await show_record(heal,lessons.actors): quit(1); return
	expect(_presentation._dialogue.body_label.text.split(" ").size()<65, "Ostrid gives one short practical instruction")
	await capture("04-early-heal-lesson.png")
	_presentation.cancel("preview_done"); _fade.reset()
	expect(await ContinentChunkStream.drain_workers(self), "map workers drain cleanly after preview")
	var report := FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":_assertions,"captures":_captures,"failures":_failures,"native_evidence":true,"map":"landfall_town","geometry_changed":false},"  "))
	_presentation.queue_free(); _stage.queue_free(); _main.queue_free()
	for _i: int in 8: await process_frame
	NativeAnimationImporter.clear(); GlbSceneCache.clear(); CharacterProportions.clear()
	print("Quest first-pass render: %d checks; %d captures; %d failures"%[_assertions,_captures,_failures])
	quit(1 if _failures else 0)

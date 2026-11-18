extends "res://tests/integration/rendered_quest_first_pass.gd"
## Actual retry record/native cast, viewed in the published gathering worksite.

func load_ground(map: String, tile: Vector2i) -> bool:
	_stage=Node3D.new(); root.add_child(_stage); _stage_world=_stage.get_world_3d()
	var light:=DirectionalLight3D.new(); light.rotation_degrees=Vector3(-48,-35,0); light.light_energy=0.8
	_stage.add_child(light)
	var env:=WorldEnvironment.new(); env.environment=Environment.new()
	env.environment.background_mode=Environment.BG_COLOR; env.environment.background_color=Color("8ba9b6")
	env.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_energy=0.7; _stage.add_child(env)
	var maps: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_adapter=CoordinateAdapter.new(maps.maps[map].coordinateTransform)
	_preview_loader=WorldLoader.new(); _stage.add_child(_preview_loader)
	var loaded: Array=[false]
	_preview_loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0]=true)
	_preview_loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/"+map+"/client/world.json"),_adapter.tile_center(tile.x,tile.y))
	var deadline:=Time.get_ticks_msec()+90000
	while not loaded[0] and Time.get_ticks_msec()<deadline: await process_frame
	expect(loaded[0],"the actual retry worksite loads its published terrain")
	if not loaded[0]: return false
	_rig=PreviewRig.new(); _stage.add_child(_rig)
	_preview_camera=Camera3D.new(); _rig.add_child(_preview_camera); _rig.camera=_preview_camera
	_preview_camera.current=true; _preview_camera.cull_mask=3
	_preview_focus=Node3D.new(); _stage.add_child(_preview_focus); _fade.set_enabled(true)
	return true

func run() -> void:
	Engine.max_fps=30; root.size=Vector2i(1280,720)
	_directory=OS.get_environment("RL_RETRY_OUTCOMES_OUT"); DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	_main=(load("res://src/app/main.tscn") as PackedScene).instantiate(); root.add_child(_main)
	await process_frame; _main.hide()
	_presentation=Presentation.new(); root.add_child(_presentation); _presentation.set_auto_dialogue(false,false)
	var records: Array=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_RETRY_NATIVE_EVIDENCE")))
	_record=records[0].duplicate(true); _hero=int(_record.actors.protagonist)
	var viewer: Dictionary=_record.native_cast.protagonist
	var point:=Vector2i(int(viewer.x),int(viewer.y)); var map:=str(_record.map)
	if not await load_ground(map,point): quit(1); return
	for raw: Dictionary in _record.native_cast.values(): native_actor(raw)
	var deadline:=Time.get_ticks_msec()+15000
	while not is_finite(surface_height(_adapter.tile_center(point.x,point.y))) and Time.get_ticks_msec()<deadline: await process_frame
	for id: int in _actors: place_actor(id,Vector2i(int(_actor_dtos[id].x),int(_actor_dtos[id].y)))
	aim(point+Vector2i(1,1),Vector3(7,8,10)); _rig.focus=_adapter.tile_center(point.x,point.y)
	while not _presentation.playing and Time.get_ticks_msec()<deadline:
		_presentation.update(0,_record,_rig,_actors,_hero,map,true,_adapter,surface_height)
		await process_frame
	expect(_presentation.playing and _presentation._choice_completed,"the recorded native cancel resumes its acknowledged outcome")
	expect(_presentation._dialogue.portrait_visible() and _presentation._dialogue._actor.get_ref()==_actors[_hero]
		and _presentation._caption.text==_record.scene.choice.response,"native retry follow-up shows the current player's headshot and authoritative text")
	await capture("01-native-retry-followup.png")
	_presentation.cancel("finished"); _record.scene.requires_ack=false
	var choices: Array=[]; var acknowledgements: Array=[]
	_presentation.choice_requested.connect(func(id: String) -> void: choices.append(id))
	_presentation.presentation_finished.connect(func(token: String, reason: String) -> void: acknowledgements.append([token,reason]))
	expect(_presentation.request_replay(_record,map),"the actual retry record admits local replay")
	_presentation.update(0,_record,_rig,_actors,_hero,map,true,_adapter,surface_height)
	var held: Transform3D=_preview_camera.global_transform
	for _i: int in 8: await process_frame
	expect(_presentation._choice_review and _presentation._choice_waiting
		and _presentation._dialogue.portrait_visible(),"retry replay retains the profile beside both read-only options")
	expect(_presentation._choice_dialog._content.cancel.heading.text.begins_with("✓ "),"the native recorded cancel is visibly highlighted")
	for row: Dictionary in _presentation._choice_dialog._content.values():
		expect(_presentation._choice_scroll.get_global_rect().grow(1).encloses((row.heading as Label).get_global_rect()),"each retry option heading is visible before scrolling")
	expect(_preview_camera.global_transform.is_equal_approx(held) and choices.is_empty() and acknowledgements.is_empty(),"review neither moves the camera nor changes the native outcome")
	await capture("02-native-retry-recorded-choice.png")
	_presentation.cancel("preview_done"); _fade.reset()
	expect(await ContinentChunkStream.drain_workers(self),"native map workers drain after retry review")
	var report:=FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":_assertions,"captures":_captures,"failures":_failures,
		"native_evidence":true,"geometry_changed":false},"  "))
	_presentation.queue_free(); _stage.queue_free(); _main.queue_free()
	for _i: int in 8: await process_frame
	NativeAnimationImporter.clear(); GlbSceneCache.clear(); CharacterProportions.clear()
	print("Quest retry outcomes render: %d checks; %d captures; %d failures"%[_assertions,_captures,_failures])
	quit(1 if _failures else 0)

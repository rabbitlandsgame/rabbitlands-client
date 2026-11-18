extends "res://tests/integration/rendered_quest_first_pass.gd"
## Recorded native family choices retain their portraits and settled framing.
## External fixture records and output locations are supplied only by environment.

func run() -> void:
	Engine.max_fps=30; root.size=Vector2i(1280,720)
	_directory=OS.get_environment("RL_CINEMATIC_BOUNDARY_OUT")
	DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	_main=(load("res://src/app/main.tscn") as PackedScene).instantiate(); root.add_child(_main)
	await process_frame; _main.hide()
	_presentation=Presentation.new(); root.add_child(_presentation); _presentation.set_auto_dialogue(false,false)
	var rows: Array=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_CHECKIN_EVIDENCE")))
	var visit: Dictionary=rows.filter(func(row: Dictionary) -> bool:
		return str((row.get("scene",{}) as Dictionary).get("choice",{}).get("selected",""))=="listen")[0]
	if not await load_town(Vector2i(29,29)): quit(1); return
	if not await show_record(visit,visit.native_cast): quit(1); return
	_presentation.cancel("finished")
	# Model the ordinary scene ACK echo, never a different personal answer.
	_record.scene.requires_ack=false
	var choices: Array=[]; var acknowledgements: Array=[]
	_presentation.choice_requested.connect(func(id: String) -> void: choices.append(id))
	_presentation.presentation_finished.connect(func(token: String, reason: String) -> void:
		acknowledgements.append([token,reason]))
	expect(_presentation.request_replay(_record,"landfall_town"),"the native recorded visit admits local replay")
	_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	var held: Transform3D=_preview_camera.global_transform
	_presentation.skip()
	_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	expect(_presentation._choice_waiting and _presentation._choice_review
		and _presentation._choice_dialog._content.listen.heading.text.begins_with("✓ "),
		"the actual recorded option is visibly highlighted in read-only replay")
	expect(_presentation._dialogue.portrait_visible() and _preview_camera.global_transform.is_equal_approx(held),
		"seeking to the recorded question keeps the player portrait and one settled family view")
	for _i: int in 8: await process_frame
	for row: Dictionary in _presentation._choice_dialog._content.values():
		expect(_presentation._choice_scroll.get_global_rect().grow(1).encloses((row.heading as Label).get_global_rect()),
			"native replay opens with each recorded approach heading visible instead of scrolled to its footer")
	await capture("01-native-recorded-answer.png")
	var stale: Callable=_presentation._on_choice_continue.bind(_presentation._choice_token())
	_presentation.cancel("next_preview")
	expect(_presentation.request_replay(_record,"landfall_town"),"the same native answer can be reviewed again")
	_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	_presentation.skip()
	_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	stale.call_deferred(); await process_frame
	expect(_presentation._choice_waiting and not _presentation._choice_completed,
		"a previous viewing's queued Continue leaves the new recorded question open")
	expect(choices.is_empty() and acknowledgements.is_empty(),"recorded review sends neither native choices nor scene acknowledgements")
	await capture("02-native-repeated-review.png")
	_presentation.cancel("preview_done"); _fade.reset()
	expect(await ContinentChunkStream.drain_workers(self),"map workers drain after native review")
	var report:=FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":_assertions,"captures":_captures,"failures":_failures,
		"native_evidence":true,"geometry_changed":false},"  "))
	_presentation.queue_free(); _stage.queue_free(); _main.queue_free()
	for _i: int in 8: await process_frame
	NativeAnimationImporter.clear(); GlbSceneCache.clear(); CharacterProportions.clear()
	print("Quest cinematic boundary render: %d checks; %d captures; %d failures"%[_assertions,_captures,_failures])
	quit(1 if _failures else 0)

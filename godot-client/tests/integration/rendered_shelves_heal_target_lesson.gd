extends "res://tests/integration/rendered_quest_first_pass.gd"
## Inspect real pre/post-heal states without simulating a cast or advancing work.
const LabelStyle := preload("res://src/ui/world_label_style.gd")

func settle_native_appearance() -> void:
	var deadline:=Time.get_ticks_msec()+15000
	var ready:=false
	while not ready and Time.get_ticks_msec()<deadline:
		await process_frame
		ready=true
		for body: ReplicatedActor3D in _actors.values():
			ready=ready and not body._rl_head_waiting and body._rl_head_pending==null and body._rl_hair_pending==null
	expect(ready,"native head and hair loading finishes before portrait comparison")

func capture_record(records: Array, label: String) -> Dictionary:
	for row: Dictionary in records:
		if str(row.get("capture_label",""))==label: return row
	return {}

func run() -> void:
	Engine.max_fps=30; root.size=Vector2i(1280,720)
	_directory=OS.get_environment("RL_HEAL_TARGET_RENDER_OUT"); DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	_main=(load("res://src/app/main.tscn") as PackedScene).instantiate(); root.add_child(_main)
	await process_frame; _main.hide(); _main.set_process(false)
	_presentation=Presentation.new(); root.add_child(_presentation); _presentation.set_auto_dialogue(false,false)
	var evidence: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_HEAL_TARGET_LESSON_EVIDENCE")))
	var prompt:=capture_record(evidence.snapshots,"target-prompt")
	var play:=capture_record(evidence.snapshots,"target-play")
	var following:=capture_record(evidence.snapshots,"ally-healed-fire")
	expect(not prompt.is_empty() and not play.is_empty() and not following.is_empty(),"native proof includes the prompt, playable target and confirmed-heal successor")
	if prompt.is_empty() or play.is_empty() or following.is_empty(): quit(1); return
	var visitor: Dictionary=prompt.native_cast.protagonist
	var app:=root.get_node("AppState")
	app.current_map="landfall_town"; app.local_actor_id=int(prompt.actors.protagonist)
	app.campaign=prompt.duplicate(true)
	if not await load_town(Vector2i(int(visitor.x),int(visitor.y))): quit(1); return
	_preview_camera.cull_mask |= LabelStyle.RENDER_LAYER
	if not await show_record(prompt,prompt.native_cast): quit(1); return
	await settle_native_appearance()
	var view: Transform3D=_preview_camera.global_transform
	expect(_presentation._dialogue.portrait_visible() and _presentation._line_continue.visible,
		"the injured instructor speaks with her portrait and immediate Continue")
	expect("Life Essence" in _presentation._caption.text and "Water Essence" in _presentation._caption.text,
		"both native healing ingredients are readable in the instruction")
	await capture("01-friendly-target-instruction.png")
	_presentation.continue_dialogue()
	_record=play.duplicate(true)
	_presentation.update(0,_record,_rig,_actors,_hero,"landfall_town",true,_adapter,surface_height)
	var mentor_id:=int(play.actors.mentor)
	var patient:=_actors[mentor_id] as ReplicatedActor3D
	var actual: Dictionary=play.native_cast.mentor
	patient.apply_vitals(int(actual.health),int(actual.max_health)); patient.set_nameplate_visible(true)
	app.current_map="landfall_town"; app.local_actor_id=_hero; app.campaign=play.duplicate(true)
	app.actors=_actor_dtos.duplicate(true)
	patient.set_health_visible(bool(_main.call("_overhead_health_for",mentor_id,actual,-1)))
	expect(not _presentation.blocks_input() and patient._health_shown and int(actual.health)<int(actual.max_health),
		"after the native acknowledgement the player has control and sees real injured health")
	expect(patient._health_bar_background.visible and patient._health_label.visible
		and (_preview_camera.cull_mask & LabelStyle.RENDER_LAYER)!=0,
		"the native injured bar and health numbers are actually drawable in the evidence camera")
	expect(_preview_camera.global_transform.is_equal_approx(view),"targeted healing begins from the established player view")
	await capture("02-playable-injured-ally.png")
	var after: Dictionary=following.native_cast.mentor
	expect(int(after.health)>int(actual.health) and following.scene.variant=="ally_healed",
		"the successor follows an actual positive native heal, not an acknowledgement")
	if not await show_record(following,following.native_cast): quit(1); return
	await settle_native_appearance()
	expect(_presentation._caption.text.begins_with("That helped") and _presentation._dialogue.portrait_visible()
		and _presentation._line_continue.visible,"Ostrid confirms the actual heal and explains the next spell in one portrait panel")
	expect(_preview_camera.global_transform.is_equal_approx(view),"the confirmed-heal follow-up adds no shot or camera movement")
	await capture("03-confirmed-heal-followup.png")
	_presentation.cancel("preview_done"); _fade.reset(); app.campaign={}; app.actors={}
	expect(await ContinentChunkStream.drain_workers(self),"practice map workers drain after the native evidence render")
	var report:=FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":_assertions,"captures":_captures,"failures":_failures,
		"native_evidence":true,"geometry_changed":false},"  "))
	_presentation.queue_free(); _stage.queue_free(); _main.queue_free()
	for _i: int in 8: await process_frame
	NativeAnimationImporter.clear(); GlbSceneCache.clear(); CharacterProportions.clear()
	print("Heal Target native render: %d checks; %d captures; %d failures"%[_assertions,_captures,_failures])
	quit(1 if _failures else 0)

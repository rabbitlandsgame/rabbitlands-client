extends "res://tests/integration/rendered_quest_first_pass.gd"
## Automated UI fixture using externally supplied native blocked states/cast.
## No network, quest mutation, production-paced gameplay or camera new shots.
const MineLighting:=preload("res://src/world/lantern_mine_lighting.gd")
var _mine_lighting:=MineLighting.new()
var _mine_environment:WorldEnvironment
var _mine_sun:DirectionalLight3D
var _mine_lights:Node3D

func load_mine(map:String,tile:Vector2i) -> bool:
	_stage=Node3D.new();root.add_child(_stage);_stage_world=_stage.get_world_3d()
	_mine_sun=DirectionalLight3D.new();_stage.add_child(_mine_sun)
	_mine_environment=WorldEnvironment.new();_mine_environment.environment=Environment.new()
	_stage.add_child(_mine_environment)
	_mine_lights=Node3D.new();_stage.add_child(_mine_lights)
	var maps:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_adapter=CoordinateAdapter.new(maps.maps[map].coordinateTransform)
	_preview_loader=WorldLoader.new();_stage.add_child(_preview_loader)
	var loaded:=[false]
	_preview_loader.load_completed.connect(func(manifest:WorldManifest)->void:
		LightMarkerBinder.apply(manifest,_mine_lights);loaded[0]=true)
	_preview_loader.load_world(ProjectSettings.globalize_path(str(maps.maps[map].manifest)),_adapter.tile_center(tile.x,tile.y))
	var deadline:=Time.get_ticks_msec()+90000
	while not loaded[0] and Time.get_ticks_msec()<deadline:await process_frame
	expect(loaded[0],"the existing native mine geometry loads for the UI fixture")
	if not loaded[0]:return false
	_rig=PreviewRig.new();_stage.add_child(_rig)
	_preview_camera=Camera3D.new();_rig.add_child(_preview_camera);_rig.camera=_preview_camera
	_preview_camera.current=true;_preview_camera.cull_mask=3|(1<<19)
	_preview_focus=Node3D.new();_stage.add_child(_preview_focus);_fade.set_enabled(true)
	_mine_lighting.apply(_preview_loader.manifest,
		MineLighting.section_at(_preview_loader.manifest,_adapter.tile_center(tile.x,tile.y)),
		_mine_environment,_mine_sun,null,_mine_lights)
	return true

func run() -> void:
	Engine.max_fps=30;root.size=Vector2i(1280,720)
	_directory=OS.get_environment("RL_BLOCKED_FAMILY_RENDER_OUT")
	var path:=OS.get_environment("RL_BLOCKED_FAMILY_RENDER_EVIDENCE")
	if _directory.is_empty() or path.is_empty():push_error("Set blocked-family native evidence and private output paths");quit(1);return
	DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	_main=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(_main)
	await process_frame;_main.set_process(false);_main.set_physics_process(false);_main.hide()
	_main.world_root.hide();_main.world_environment.environment=null
	var bundle:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
	var rows:Array=bundle.get("snapshots",bundle.get("packets",[]))
	expect(not rows.is_empty(),"an external native blocked-state/cast fixture is present")
	if rows.is_empty():quit(1);return
	var banner_layer:=CanvasLayer.new();banner_layer.layer=124;root.add_child(banner_layer)
	var banner:=Label.new();banner.add_theme_font_size_override("font_size",13)
	banner.text="AUTOMATED VISUAL FIXTURE · native blocked state/cast · no live combat, walk or recovery acceptance"
	banner_layer.add_child(banner);banner.position=Vector2(12,8)
	var emitted:Array=[]
	var permission_states:Array=[]
	for row:Dictionary in rows:
		var native:Dictionary=row.get("snapshot",row.get("state",row))
		if str(native.get("scene",{}).get("inspection",{}).get("status",""))!="blocked":continue
		var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
		expect(decoded.type=="campaign","the exact native blocked state decodes")
		if decoded.type!="campaign":quit(1);return
		_record=native.duplicate(true)
		_hero=int(row.get("local_actor_id",native.actors.protagonist))
		var cast:Dictionary=(row.get("native_cast",{}) as Dictionary).duplicate(true)
		var all_rows:Variant=row.get("actor_dtos",[])
		if all_rows is Dictionary:all_rows=all_rows.values()
		for dto:Dictionary in all_rows:
			if int(dto.actor_id)==_hero:cast["local_viewer"]=dto
		expect(not cast.is_empty(),"same-run native actor appearances accompany the blocked state")
		if cast.is_empty():quit(1);return
		var visitor:Dictionary={}
		for dto:Dictionary in cast.values():
			if int(dto.actor_id)==_hero:visitor=dto
		expect(not visitor.is_empty(),"the actual local viewer's native body is included")
		if visitor.is_empty():quit(1);return
		var point:=Vector2i(int(visitor.get("x",visitor.get("tile",[0,0])[0])),int(visitor.get("y",visitor.get("tile",[0,0])[1])))
		if _stage==null:
			if not await load_mine(str(native.map),point):quit(1);return
		if is_instance_valid(_presentation):_presentation.cancel("next_fixture");_presentation.queue_free()
		for body:Node in _actors.values():body.queue_free()
		_actors.clear();_actor_dtos.clear();await process_frame
		var seen:Dictionary={}
		for raw:Dictionary in cast.values():
			if seen.has(int(raw.actor_id)):continue
			seen[int(raw.actor_id)]=true;native_actor(raw)
		var deadline:=Time.get_ticks_msec()+15000
		while Time.get_ticks_msec()<deadline:
			var ready:=true
			for body:Node in _actors.values():
				if bool(body.get("_rl_head_waiting")) or body.get("_rl_head_pending")!=null or body.get("_rl_hair_pending")!=null:ready=false
			if ready:break
			await process_frame
		for id:int in _actors:place_actor(id,Vector2i(int(_actor_dtos[id].x),int(_actor_dtos[id].y)))
		aim(point+Vector2i(1,1),Vector3(7,8,10));_rig.focus=_adapter.tile_center(point.x,point.y)
		_presentation=Presentation.new();root.add_child(_presentation);_presentation.set_auto_dialogue(false,false)
		_presentation.event_requested.connect(func(id:String)->void:emitted.append(id))
		_presentation.inspection_requested.connect(func(action:String)->void:emitted.append(action))
		var before:=JSON.stringify(native)
		# Model a recipient already viewing the film, then apply the untouched
		# blocked packet/ACK echo. This is a presentation fixture, not a receipt.
		var start:Dictionary=_record.duplicate(true);start.scene.requires_ack=true
		_presentation.update(0,start,_rig,_actors,_hero,str(native.map),true,_adapter,surface_height)
		expect(_presentation.playing,"the native cast admits the existing scene")
		var held:Transform3D=_preview_camera.global_transform
		# Read the existing opening, then press its real Continue controls. A
		# raw elapsed jump would leave unreleased dialogue holds in front of
		# the inspection barrier and capture the wrong spoken frame.
		_presentation.update(2.01,_record,_rig,_actors,_hero,str(native.map),true,_adapter,surface_height)
		var advances:=0
		while _presentation._inspection_error.is_empty() and advances<8:
			if _presentation._line_continue.visible:
				_presentation._line_continue.pressed.emit()
				advances+=1
				_presentation.update(0,_record,_rig,_actors,_hero,str(native.map),true,_adapter,surface_height)
			else:
				_presentation.update(0.1,_record,_rig,_actors,_hero,str(native.map),true,_adapter,surface_height)
				advances+=1
			await process_frame
		for index in 8:await process_frame
		expect(not _presentation._line_holding and not _presentation._inspection_error.is_empty()
			and _presentation._caption.text==_presentation._inspection_error,
			"the captured frame has actually reached the native blocked-action feedback")
		var permission:bool=bool(native.scene.inspection.can_start)
		permission_states.append(permission)
		expect(not _presentation._inspection_error.is_empty() and _presentation._inspection_retry.visible
			and _presentation._inspection_retry.disabled==not permission,"native permission controls the readable Retry button")
		expect(_presentation._skip.text=="Return to play · Esc","blocked recovery offers the actual return-to-gameplay action")
		var viewport:=Rect2(Vector2.ZERO,Vector2(root.size))
		for control:Control in [_presentation._inspection_retry,_presentation._skip]:
			expect(viewport.encloses(control.get_global_rect()),"the entire recovery action stays inside1280x720")
		expect(_presentation._dialogue.portrait_visible() and _preview_camera.global_transform.is_equal_approx(held),
			"blocked feedback keeps the NPC portrait and established camera")
		expect(emitted.is_empty() and JSON.stringify(native)==before,"rendering emits no native action and changes no authoritative state")
		await capture("blocked-family-"+("retry-ready" if permission else "retry-unavailable")+".png")
	expect(true in permission_states and false in permission_states,"both ready and unavailable recovery states are inspected")
	_presentation.cancel("fixture_complete");_mine_lighting.clear();_fade.reset()
	expect(await ContinentChunkStream.drain_workers(self),"native map workers drain")
	var report:=FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":_assertions,"captures":_captures,"failures":_failures,
		"automated_visual_fixture":true,"native_gameplay_acceptance":false,"source":path,
		"source_sha256":FileAccess.get_sha256(path),"fixture_metadata":bundle.get("metadata",{}),"actions":emitted,
		"controller_sha256":FileAccess.get_sha256("res://src/world/campaign_scene.gd"),
		"harness_sha256":FileAccess.get_sha256("res://tests/integration/rendered_rescue_blocked_feedback.gd")},"  "));report.close()
	_presentation.queue_free();_stage.queue_free();_main.queue_free()
	for index in 8:await process_frame
	NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	print("Blocked family visual fixture: %d checks; %d captures; %d failures"%[_assertions,_captures,_failures])
	quit(1 if _failures else 0)

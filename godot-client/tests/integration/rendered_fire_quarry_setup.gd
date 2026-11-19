extends "res://tests/integration/rendered_quest_first_pass.gd"
## Read-only native terrain/cast staging review. Later stock depletion is an
## explicitly declared presentation checkpoint, never gameplay completion.
const FireWorks:=preload("res://src/world/campaign_fire_works.gd")
var _banner:Label

func load_quarry(tile:Vector2i)->bool:
	_stage=Node3D.new();root.add_child(_stage);_stage_world=_stage.get_world_3d()
	var sun:=DirectionalLight3D.new();sun.rotation_degrees=Vector3(-48,-35,0);sun.light_energy=0.8
	_stage.add_child(sun)
	var env:=WorldEnvironment.new();env.environment=Environment.new()
	env.environment.background_mode=Environment.BG_COLOR;env.environment.background_color=Color("8ba9b6")
	env.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color=Color("b8c8d2");env.environment.ambient_light_energy=0.55
	_stage.add_child(env)
	var maps:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_adapter=CoordinateAdapter.new(maps.maps.landfall.coordinateTransform)
	_preview_loader=WorldLoader.new();_stage.add_child(_preview_loader)
	var loaded:=[false]
	_preview_loader.load_completed.connect(func(_manifest:WorldManifest)->void:loaded[0]=true)
	_preview_loader.load_world(ProjectSettings.globalize_path(str(maps.maps.landfall.manifest)),_adapter.tile_center(tile.x,tile.y))
	var deadline:=Time.get_ticks_msec()+90000
	while not loaded[0] and Time.get_ticks_msec()<deadline:await process_frame
	expect(loaded[0],"the actual Landfall quarry terrain loads for the accepted anchor positions")
	if not loaded[0]:return false
	_rig=PreviewRig.new();_stage.add_child(_rig)
	_preview_camera=Camera3D.new();_rig.add_child(_preview_camera);_rig.camera=_preview_camera
	_preview_camera.current=true;_preview_camera.cull_mask=3
	_preview_focus=Node3D.new();_stage.add_child(_preview_focus);_fade.set_enabled(true)
	_works=FireWorks.new();_stage.add_child(_works)
	return true

func replace_cast(cast:Dictionary)->void:
	for body:Node in _actors.values():body.queue_free()
	_actors.clear();_actor_dtos.clear();await process_frame
	var seen:Dictionary={}
	for raw:Dictionary in cast.values():
		if seen.has(int(raw.actor_id)):continue
		seen[int(raw.actor_id)]=true;native_actor(raw.duplicate(true))
	var deadline:=Time.get_ticks_msec()+30000
	while Time.get_ticks_msec()<deadline:
		var ready:=true
		for actor:Node in _actors.values():
			if not _presentation._body_ready(actor):ready=false
		if ready:break
		await process_frame
	for id:int in _actors:place_actor(id,Vector2i(int(_actor_dtos[id].x),int(_actor_dtos[id].y)))
	var death_deadline:=Time.get_ticks_msec()+6000
	while Time.get_ticks_msec()<death_deadline:
		var resting:=true
		for id:int in _actors:
			if int(_actor_dtos[id].get("health",1))<=0 and not _actors[id].death_animation_finished():resting=false
		if resting:break
		await process_frame

func stock_loads()->int:
	var count:=0
	for body:Node3D in _works._stock_loads.values():
		if body.is_visible_in_tree():count+=1
	return count

func run()->void:
	Engine.max_fps=30;root.size=Vector2i(1280,720)
	_directory=OS.get_environment("RL_FIRE_QUARRY_RENDER_OUT")
	var path:=OS.get_environment("RL_FIRE_STAGING_EVIDENCE")
	if _directory.is_empty() or path.is_empty():push_error("Set native Fire staging and private render output paths");quit(1);return
	DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	# Reuse production DTO/catalogue methods without entering Main or creating
	# its login/UI/neighbor-world startup. This review owns one explicit stage.
	_main=(load("res://src/app/main.gd") as GDScript).new()
	var models:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	_main.npc_looks=models.get("npcLooks",{})
	_main.npc_characters=_main._json("res://data/actors/npc_characters.json")
	_main.npc_human_faces=_main._json("res://data/actors/npc_human_faces.json")
	_main.npc_workstations=_main._json("res://data/actors/workstations.json")
	_main.equipment_config=preload("res://src/actors/equipment_registry_snapshot_cache.gd").prepare(_main._json("res://data/actors/equipment.json"))
	var bundle:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
	var held_record:Dictionary=(bundle.records as Array).filter(func(row:Dictionary)->bool:return row.label=="quarry-held-silence")[0]
	var released_record:Dictionary=(bundle.records as Array).filter(func(row:Dictionary)->bool:return row.label=="quarry-released-silence")[0]
	var held:Dictionary=held_record.snapshot
	var released:Dictionary=released_record.snapshot
	for native:Dictionary in [held,released]:
		expect(EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer()).type=="campaign","the actual current-source native visual checkpoint decodes")
	var unchanged:=[JSON.stringify(held),JSON.stringify(released)]
	var gate:Array=held.anchors.release
	if not await load_quarry(Vector2i(int(gate[0]),int(gate[1]))):quit(1);return
	_presentation=Presentation.new();root.add_child(_presentation);_presentation.set_auto_dialogue(false,false)
	await replace_cast(held_record.actor_dtos)
	_hero=int(held.actors.protagonist)
	var terrain_deadline:=Time.get_ticks_msec()+30000
	while Time.get_ticks_msec()<terrain_deadline:
		_works.apply_snapshot(held,_adapter,"landfall",surface_height,_actors)
		if _works.props.has("stranded_cart") and _works.props.has("release"):break
		await process_frame
	expect(_works.props.has("stranded_cart") and stock_loads()==4,"the imported loaded wagon waits for the actual quarry ground")
	for id:int in _actors:place_actor(id,Vector2i(int(_actor_dtos[id].x),int(_actor_dtos[id].y)))
	aim(Vector2i(int(gate[0]),int(gate[1])),Vector3(10,9,12));_rig.focus=_adapter.tile_center(int(gate[0]),int(gate[1]))
	var banner_layer:=CanvasLayer.new();banner_layer.layer=124;root.add_child(banner_layer)
	_banner=Label.new();_banner.add_theme_font_size_override("font_size",12);_banner.position=Vector2(12,8)
	_banner.text="AUTOMATED VISUAL REVIEW · actual native quarry terrain/cast · explicit read-only scene replay"
	banner_layer.add_child(_banner)
	# Observe the already-acknowledged packet through the normal controller
	# path before offering its explicit read-only replay.
	_presentation.update(0,held,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
	expect(_presentation.request_replay(held,"landfall"),"the existing native introduction can be replayed without inventing an acknowledgement")
	var deadline:=Time.get_ticks_msec()+30000
	while not _presentation.playing and Time.get_ticks_msec()<deadline:
		_presentation.update(0,held,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
		await process_frame
	for frame:int in 60:
		_presentation.update(1.0/30.0,held,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
		await process_frame
	expect(_presentation.playing and _presentation._dialogue.portrait_visible(),"the native Brenna portrait and held introduction establish one conversation view")
	var camera_pose:=_preview_camera.global_transform
	var camera_ground:=surface_height(_preview_camera.global_position)
	expect(is_finite(camera_ground) and _preview_camera.global_position.y>camera_ground+1.0,
		"the established camera is above actual terrain rather than inside the quarry bank")
	var lens:={"fov":_preview_camera.fov,"size":_preview_camera.size,"projection":_preview_camera.projection,
		"near":_preview_camera.near,"far":_preview_camera.far}
	var held_focus:=_presentation.occlusion_focus() as Node3D
	var comparison_focus:=held_focus.global_position if is_instance_valid(held_focus) else _preview_focus.global_position
	var probe:Array=[]
	var focus:=_adapter.tile_center(int(gate[0]),int(gate[1]));focus.y=surface_height(focus)+1.0
	for offset:Vector3 in [Vector3(22,17,12),Vector3(16,13,8),Vector3(18,18,0),Vector3(10,18,-12),Vector3(-11,10,16)]:
		var at:=Vector3(focus.x,focus.y-1.0,focus.z)+offset
		var query:=PhysicsRayQueryParameters3D.create(focus,at,WorldLoader.WORLD_COLLISION_LAYER)
		var obstruction:Dictionary=_stage_world.direct_space_state.intersect_ray(query)
		probe.append({"offset":[offset.x,offset.y,offset.z],"ground_at_camera":surface_height(at),"camera_y":at.y,
			"line_clear":obstruction.is_empty(),"obstruction":str(obstruction.get("position",""))})
	var geometry_report:=FileAccess.open(_directory.path_join("terrain-probe.json"),FileAccess.WRITE)
	var cast_probe:Dictionary={}
	for role:String in ["mentor","crew_one","crew_two","crew_three"]:
		var body:Node3D=_actors[int(held.actors[role])]
		var query:=PhysicsRayQueryParameters3D.create(body.global_position+Vector3.UP,_preview_camera.global_position,WorldLoader.WORLD_COLLISION_LAYER)
		var obstruction:Dictionary=_stage_world.direct_space_state.intersect_ray(query)
		cast_probe[role]={"position":str(body.global_position),"screen":str(_preview_camera.unproject_position(body.global_position+Vector3.UP)),"line_clear":obstruction.is_empty(),"obstruction":str(obstruction.get("position",""))}
	var stock:Array=held.anchors.stock
	var pickup:=_adapter.tile_center(int(stock[0]),int(stock[1]));pickup.y=surface_height(pickup)
	geometry_report.store_string(JSON.stringify({"camera":str(camera_pose),"focus":str(focus),"candidates":probe,
		"cast":cast_probe,"stock_pickup":str(pickup)},"  "));geometry_report.close()
	var visible_world:=Rect2(24,40,1232,450)
	for role:String in ["mentor","crew_one","crew_two","crew_three"]:
		var body:Node3D=_actors[int(held.actors[role])]
		expect(body.is_visible_in_tree() and not _preview_camera.is_position_behind(body.global_position+Vector3.UP) \
			and visible_world.has_point(_preview_camera.unproject_position(body.global_position+Vector3.UP)),
			role+" is inside the established conversation frame above the dialogue")
	var wagon:Node3D=_works.props.stranded_cart
	expect(visible_world.has_point(_preview_camera.unproject_position(wagon.global_position+Vector3.UP)),"the loaded wagon is framed with the pinned crew")
	await capture("01-held-crew-loaded-wagon.png")
	# Keep this accepted view for explicit side-by-side prop comparisons. The
	# second packet is another genuine native test run; this is not a live walk.
	_presentation.cancel("native_prop_comparison")
	_preview_camera.global_transform=camera_pose
	for key:String in lens:_preview_camera.set(key,lens[key])
	_preview_focus.global_position=comparison_focus
	await replace_cast(released_record.actor_dtos)
	_banner.text="AUTOMATED PROP COMPARISON · actual native release state · camera held for comparison"
	_works.apply_snapshot(released,_adapter,"landfall",surface_height,_actors)
	for frame:int in 8:await process_frame
	expect(not _works.props.release.visible and stock_loads()==4,"the real release packet clears the gate while its stock is still undelivered")
	expect(_preview_camera.global_transform.is_equal_approx(camera_pose) and is_equal_approx(_preview_camera.fov,float(lens.fov)),
		"native release prop updates preserve the accepted camera and lens")
	await capture("02-released-gate-clear.png")
	var depleted:Dictionary=released.duplicate(true)
	depleted.shelves.fire.recovered=depleted.shelves.fire.recovered_goal
	_banner.text="DECLARED STOCK-VISUAL CHECKPOINT · secured recovery goal projected for visual review only"
	_works.apply_snapshot(depleted,_adapter,"landfall",surface_height,_actors)
	for frame:int in 8:await process_frame
	expect(stock_loads()==0 and _works.props.stranded_cart.visible and not _works.props.release.visible,
		"a declared fully delivered recovery checkpoint leaves the wagon empty and the exit clear")
	expect(_preview_camera.global_transform.is_equal_approx(camera_pose) and is_equal_approx(_preview_camera.fov,float(lens.fov)),
		"stock depletion preserves the accepted camera and lens")
	await capture("03-stock-delivered-empty-wagon.png")
	expect([JSON.stringify(held),JSON.stringify(released)]==unchanged,"rendering alters neither actual native checkpoint")
	_presentation.cancel("visual_review_complete");_fade.reset()
	expect(await ContinentChunkStream.drain_workers(self),"quarry loading workers drain cleanly")
	var report:=FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks":_assertions,"failures":_failures,"captures":_captures,
		"native_source":path,"source_sha256":FileAccess.get_sha256(path),"terrain":"actual Landfall package",
		"comparison_lens":lens,
		"scope":"Explicit native introduction replay and held-view prop comparison; final depletion is a declared presentation checkpoint, not gameplay acceptance.",
		"geometry_changed":false},"  "));report.close()
	_works.clear();_presentation.queue_free();_stage.queue_free();_main.queue_free()
	for frame:int in 8:await process_frame
	NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	print("Fire quarry visual review: %d checks; %d captures; %d failures"%[_assertions,_captures,_failures])
	quit(1 if _failures else 0)

extends "res://tests/integration/rendered_campaign_road.gd"
## Offline visual qualification using real native snapshots and Landfall terrain.
const WaterWorks=preload("res://src/world/campaign_water_works.gd")
var _live:Dictionary={}
var _hero:=1

func load_water_site(tile:Vector2i)->bool:
	_stage=Node3D.new();root.add_child(_stage);_stage_world=_stage.get_world_3d()
	var sun:=DirectionalLight3D.new();sun.rotation_degrees=Vector3(-48,-35,0);sun.light_energy=0.8;_stage.add_child(sun)
	var env:=WorldEnvironment.new();env.environment=Environment.new()
	env.environment.background_mode=Environment.BG_COLOR;env.environment.background_color=Color("8ba9b6")
	env.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR;env.environment.ambient_light_color=Color("b8c8d2");env.environment.ambient_light_energy=0.55
	_stage.add_child(env)
	var maps:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	_adapter=CoordinateAdapter.new(maps.maps.landfall.coordinateTransform)
	_preview_loader=WorldLoader.new();_stage.add_child(_preview_loader)
	var loaded:=[false]
	_preview_loader.load_completed.connect(func(_manifest:WorldManifest)->void:loaded[0]=true)
	_preview_loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/landfall/client/world.json"),_adapter.tile_center(tile.x,tile.y))
	var deadline:=Time.get_ticks_msec()+90000
	while not loaded[0] and Time.get_ticks_msec()<deadline:await process_frame
	expect(loaded[0],"the real coastal Landfall terrain loads")
	if not loaded[0]:return false
	_rig=PreviewRig.new();_stage.add_child(_rig)
	_preview_camera=Camera3D.new();_rig.add_child(_preview_camera);_rig.camera=_preview_camera
	_preview_camera.current=true;_preview_camera.cull_mask=3
	_preview_focus=Node3D.new();_stage.add_child(_preview_focus);_fade.set_enabled(true)
	_works=WaterWorks.new();_stage.add_child(_works)
	return true

func show_cast(record:Dictionary)->void:
	_presentation.cancel("next_preview")
	for body:Node in _actors.values():body.queue_free()
	_actors.clear();_actor_dtos.clear();_works.clear()
	_live=record.campaign.duplicate(true);_hero=int(_live.actors.protagonist)
	var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	for raw:Dictionary in record.actors:
		var dto:Dictionary=_main._presentation_dto(raw)
		var model:Dictionary=registry.models[registry.actorTypes[str(int(dto.actor_type))]]
		var actor:=ReplicatedActor3D.new();_stage.add_child(actor)
		var errors:=actor.configure(dto,_adapter,model,_main._animation_for_model(model),_main.equipment_config)
		expect(errors.is_empty(),str(dto.name)+" has an approved native body")
		_actors[int(dto.actor_id)]=actor;_actor_dtos[int(dto.actor_id)]=dto
		place_actor(int(dto.actor_id),Vector2i(int(dto.x),int(dto.y)))
		actor.set_nameplate_visible(false)
	var tile:Array=_live.anchors.entry
	var deadline:=Time.get_ticks_msec()+15000
	while not is_finite(surface_height(_adapter.tile_center(int(tile[0]),int(tile[1])))) and Time.get_ticks_msec()<deadline:await process_frame
	for _i:int in 15:
		_works.apply_snapshot(_live,_adapter,"landfall",surface_height,false)
		await process_frame

func start_film()->bool:
	_presentation.update(0,_live,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
	var deadline:=Time.get_ticks_msec()+15000
	while not _presentation.playing and Time.get_ticks_msec()<deadline:
		await process_frame
		_presentation.update(0,_live,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
	expect(_presentation.playing,"the native cast and ground anchors admit the cinematic")
	if not _presentation.playing:return false
	_presentation.update(1.6,_live,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
	return true

func _watchdog()->void:
	await create_timer(150).timeout
	push_error("Water render exceeded its deadline")
	await ContinentChunkStream.drain_workers(self)
	quit(1)

func run()->void:
	Engine.max_fps=30;root.size=Vector2i(1280,720)
	_watchdog.call_deferred()
	_directory=OS.get_environment("RL_WATER_PREVIEW_OUT");DirAccess.make_dir_recursive_absolute(_directory)
	root.get_node("Network").block_for_hud_preview()
	_main=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(_main);await process_frame;_main.hide()
	_presentation=Presentation.new();root.add_child(_presentation);_presentation.set_auto_dialogue(false,false)
	var rows:Array=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("RL_WATER_RENDER_EVIDENCE")))
	if not await load_water_site(Vector2i(400,315)):quit(1);return
	var entry:Dictionary=rows.filter(func(v:Dictionary)->bool:return str(v.campaign.scene.get("id",""))=="measure.shelves.water.entry_water" and str(v.campaign.scene.get("choice",{}).get("selected",""))=="")[0]
	await show_cast(entry);aim(Vector2i(400,315),Vector3(12,12,18))
	if not await start_film():quit(1);return
	expect(_presentation._dialogue.visible and not _presentation._dialogue.body_label.text.is_empty(),"Iona's portrait dialogue appears immediately")
	await capture("01-iona-and-the-coastal-gates.png")
	_presentation.continue_dialogue();_presentation.update(0,_live,_rig,_actors,_hero,"landfall",true,_adapter,surface_height)
	await capture("02-player-route-choice.png")
	expect(_presentation._dialogue._portrait_frame.visible,"the real player's headshot remains beside the route choices")
	var barge:Dictionary=rows.filter(func(v:Dictionary)->bool:return str(v.campaign.key)=="water_barge" and str(v.campaign.shelves.water.route)=="sheltered")[0]
	await show_cast(barge);_live.scene={};_works.apply_snapshot(_live,_adapter,"landfall",surface_height,false)
	aim(Vector2i(403,315),Vector3(17,18,23));await capture("03-native-boat-and-waterway.png")
	expect(_works.water_props.has("boat") and _works._streams.size()>10,"the boat and channel follow the accepted native route")
	var boss:Dictionary=rows.filter(func(v:Dictionary)->bool:return str(v.campaign.scene.get("id",""))=="measure.shelves.water.boss")[0]
	await show_cast(boss)
	var dto:Dictionary=_actor_dtos[int(_live.actors.boss)];aim(Vector2i(int(dto.x),int(dto.y)),Vector3(10,12,16))
	if not await start_film():quit(1);return
	await capture("04-veyra-at-the-gatehouse.png")
	_presentation.skip();_works.clear();_fade.reset()
	var before_drain:=Performance.get_monitor(Performance.OBJECT_NODE_COUNT)
	expect(await ContinentChunkStream.drain_workers(self),"the coastal map workers drain before exit")
	var report:=FileAccess.open(_directory.path_join("report.json"),FileAccess.WRITE)
	report.store_string(JSON.stringify({"assertions":_assertions,"captures":_captures,"failures":_failures,"native_evidence":true,"map":"landfall","nodes_before_drain":before_drain,"static_map_geometry_changed":false},"  "))
	_presentation.queue_free();_stage.queue_free();_main.queue_free()
	for _i:int in 8:await process_frame
	_actors.clear();_actor_dtos.clear()
	NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	for _i:int in 4:await process_frame
	print("Water rendered preview: ",_assertions," checks; ",_captures," captures; ",_failures," failures")
	quit(1 if _failures else 0)

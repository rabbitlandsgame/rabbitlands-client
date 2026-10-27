extends SceneTree
## Offline review of revision-two native packets, actors and the approved cart.
## RL_FERRY_NATIVE_BUNDLE supplies the server test export; no connection/save.
const Presentation := preload("res://src/world/campaign_scene.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const Cart := preload("res://src/world/campaign_cart.gd")
var checks := 0
var failures := 0
var directory := ""
var bundle: Dictionary
var main: Control
var stage: Node3D
var rig: IsometricCameraController
var presentation: Node
var guide: Control
var hud: Control
var guidance: Node
var cart: Node3D
var adapter: CoordinateAdapter
var actors: Dictionary = {}
var objects: Dictionary = {}
var state: Dictionary = {}
var local_id := -1
var results: Array = []
var captures: Array = []
var choice_calls: Array = []
var preview_run := ""
var fixture_source := ""
var inspection_calls: Array = []
var inspection_delivery := -1.0
var selected_route := "unload"
var manual_holds := 0
var film_step := 1.0 / 15.0 # Automated review clock; KEEP_OPEN uses actual frame time.
var playthrough_source := ""
var selected_lead := "physical"

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func snapshot(label: String) -> Dictionary:
	for row: Dictionary in bundle.snapshots:
		if str(row.label) == label:
			var frame := Marshalls.base64_to_raw(str(row.packet191_base64))
			var decoded := EloriaProtocol.decode_server(191, frame.slice(3))
			expect(decoded.get("type") == "campaign", "native " + label + " packet decodes: " + str(decoded.get("error","valid")))
			if decoded.get("type") != "campaign": return {}
			var value: Dictionary = decoded.get("state", {})
			# An offline reviewer can try any route. The three independently
			# recorded native fixtures use different UUIDs; keep this review's
			# presentation identity while projecting their unchanged route data.
			if OS.get_environment("RL_FERRY_KEEP_OPEN") == "1" and not preview_run.is_empty():
				value.run_id = preview_run
				value.scene.token = preview_run + ":" + str(value.scene.id)
			return value
	return {}

func run() -> void:
	if OS.get_environment("RL_FERRY_KEEP_OPEN") != "1":
		create_timer(360).timeout.connect(func() -> void: push_error("Native cart preview timed out"); quit(1))
	Engine.max_fps = 30
	var source := OS.get_environment("RL_FERRY_NATIVE_BUNDLE")
	if source.is_empty():
		push_error("Set RL_FERRY_NATIVE_BUNDLE to the native-session ferry fixture JSON.")
		quit(1)
		return
	bundle = JSON.parse_string(FileAccess.get_file_as_string(source))
	selected_route = OS.get_environment("RL_CART_ROUTE")
	if selected_route not in ["unload","lever","haul"]: selected_route="unload"
	selected_lead={"unload":"physical","lever":"chronology","haul":"records"}[selected_route]
	local_id = int(bundle.local_actor_id)
	load_playthrough_rows(source)
	adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [435, 448], "walkingHeight": 2.5})
	fixture_source = source
	directory = OS.get_environment("RL_FERRY_PREVIEW_OUT")
	if directory.is_empty(): directory = "user://ferry-preview"
	DirAccess.make_dir_recursive_absolute(directory)
	root.size = Vector2i(1280, 720)
	root.title = "Rabbit Lands · Last Cart cinematic review (offline)"
	root.get_node("Network").call("block_for_hud_preview")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	main.hide()
	Engine.max_fps = 30 # Main applies the saved runtime limit during _ready.
	stage = Node3D.new()
	root.add_child(stage)
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
	environment.environment.ambient_light_energy = 0.45
	stage.add_child(environment)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	var loaded := [false]
	loader.load_completed.connect(func(_manifest: WorldManifest) -> void: loaded[0] = true)
	var entry: Array = bundle.players[0].tile
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/greenlight/client/world.json"), adapter.tile_center(int(entry[0]), int(entry[1])))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline: await process_frame
	expect(loaded[0], "the production Greenlight quay loads")
	if not loaded[0]: quit(1); return
	main.gameplay_world = stage.get_world_3d()
	main.adapter = adapter
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var people: Array = bundle.players.duplicate(true)
	for person: Dictionary in bundle.cast.values(): people.append(person)
	for spec: Dictionary in people:
		var dto: Dictionary = spec.duplicate(true)
		dto.x = spec.tile[0]; dto.y = spec.tile[1]
		dto = main.call("_presentation_dto", dto)
		var config: Dictionary = registry.models[registry.actorTypes[str(int(spec.actor_type))]]
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure(dto, adapter, config, main.call("_animation_for_model", config), main.equipment_config)
		expect(errors.is_empty(), str(spec.name) + " uses its real native actor and appearance")
		actor.apply_server_state(dto, adapter, true)
		actor.set_nameplate_visible(false)
		for overlay: String in ["MapDot", "Nameplate"]:
			var node := actor.get_node_or_null(overlay) as Node3D
			if node != null: node.hide()
		actors[int(spec.actor_id)] = actor
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	for spec: Dictionary in bundle.map_objects:
		var dto: Dictionary = spec.duplicate(true)
		dto.x = spec.tile[0]; dto.y = spec.tile[1]
		var object := MapObject3D.new()
		stage.add_child(object)
		object.configure(dto, adapter, catalog)
		objects[int(spec.object_id)] = object
	await physics_frame
	deadline = Time.get_ticks_msec() + 15000
	while Time.get_ticks_msec() < deadline:
		var all_surfaces := true
		for actor: ReplicatedActor3D in actors.values():
			if not is_finite(float(main.call("_campaign_surface_height", actor.global_position))):
				all_surfaces = false
		if all_surfaces: break
		await process_frame
		await physics_frame
	for actor: ReplicatedActor3D in actors.values():
		var ground: float = main.call("_campaign_surface_height", actor.global_position)
		expect(is_finite(ground), "a native actor stands on a real navigation surface")
		if is_finite(ground): actor.set_surface_height(ground)
	for object: MapObject3D in objects.values(): main.call("_place_map_object_on_surface", object)
	await physics_frame
	await process_frame
	rig = main.camera_rig
	rig.reparent(stage)
	rig.distance = 26.0
	rig.pitch_degrees = -55.0
	rig.yaw_degrees = 30.0
	rig.set_focus((actors[local_id] as Node3D).global_position)
	rig.camera.fov = 62.0
	rig.camera.cull_mask = 3 | (1 << 19) # Geometry plus normal world-text overlay.
	rig.camera.current = true
	presentation = Presentation.new()
	root.add_child(presentation)
	presentation.set_reduced_motion(false, false)
	presentation.set_auto_dialogue(false, false)
	presentation.presentation_finished.connect(func(token: String, reason: String) -> void: results.append([token, reason]))
	presentation.choice_requested.connect(preview_choose)
	presentation.inspection_requested.connect(preview_inspection)
	guidance = Guidance.new()
	stage.add_child(guidance)
	cart = Cart.new()
	stage.add_child(cart)
	guide = (load("res://src/ui/lantern_guide.gd") as GDScript).new()
	root.add_child(guide)
	guide.configure(main)
	guide.set_process(false)
	hud = Hud.new()
	root.add_child(hud)
	guide.attach_campaign(hud)
	hud.transcript_requested.connect(presentation.show_transcript)
	hud.reduced_motion_changed.connect(presentation.set_reduced_motion)
	hud.replay_requested.connect(func() -> void: presentation.request_replay(state, "greenlight"))
	root.get_node("AppState").authenticated = true
	state = snapshot("initial")
	if state.is_empty():await finish_preview();return
	preview_run = str(state.run_id)
	var original: Transform3D = rig.camera.global_transform
	var initial_position: Vector3 = (actors[local_id] as Node3D).global_position
	var immutable_fixture := JSON.stringify(bundle)
	tick(0.0)
	deadline = Time.get_ticks_msec() + 15000
	while not presentation.playing and Time.get_ticks_msec() < deadline:
		await process_frame
		tick(0.0)
	expect(presentation.playing and rig.camera.global_transform.is_equal_approx(original), "native entry begins in the player's unchanged viewport")
	if not presentation.playing:await finish_preview();return
	if OS.get_environment("RL_CART_FRAMING_ONLY")=="1":
		await framing_review();await finish_preview();return
	if OS.get_environment("RL_CART_QUICK_ROUTE")=="1":
		await quick_route_review();await finish_preview();return
	if OS.get_environment("RL_FERRY_KEEP_OPEN") == "1":
		var smoke := OS.get_environment("RL_FERRY_REVIEW_SMOKE")
		if smoke in ["unload", "lever", "haul"]: await review_smoke(smoke)
		else: await review_loop()
		await finish_preview()
		return
	await run_arrival(selected_route, original, initial_position, immutable_fixture)
	await replay_arrival()
	if selected_route == "unload":
		for pair: Array in [["unload-first-crate",1],["unload-second-crate",2]]:
			if not has_snapshot(pair[0]):continue
			state=snapshot(pair[0]);tick(0)
			var count:=0
			for load:Node3D in cart.loads:
				if load.visible:count+=1
			expect(count==2-int(pair[1]) and int(state.cart.unloaded)==int(pair[1]),"native unloading moves exactly the recorded number of physical crates")
			await capture("21-"+str(pair[0]))
	await render_followups()
	await finish_preview()

func has_snapshot(label: String) -> bool:
	for row:Dictionary in bundle.snapshots:
		if str(row.label)==label:return true
	return false

func load_playthrough_rows(source: String) -> void:
	var path:=source.get_base_dir().path_join("native-cart-playthrough-packets.json")
	if not FileAccess.file_exists(path):return
	var recorded:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not recorded is Dictionary:return
	playthrough_source=path
	for row:Dictionary in recorded.get("packets",[]):
		if str(row.get("route",""))!=selected_route or int(row.get("local_actor_id",-1))!=local_id:continue
		var present:=false
		for old:Dictionary in bundle.snapshots:
			if str(old.label)==str(row.label):present=true;break
		if not present:bundle.snapshots.append(row.duplicate(true))

func seek_with_manual_gates(target: float) -> void:
	var attempts:=0
	while presentation.playing and float(presentation.elapsed)<target-.00001 and attempts<800:
		if presentation.is_dialogue_waiting():presentation.continue_dialogue()
		tick(minf(.25,target-float(presentation.elapsed)))
		await process_frame
		attempts+=1

func framing_review() -> void:
	await seek_with_manual_gates(6.8)
	await create_timer(1.8).timeout
	await capture("framing-01-cart-and-worker-contact")
	var fixed:Transform3D=rig.camera.global_transform
	await seek_with_manual_gates(10)
	await create_timer(.5).timeout
	await capture("framing-02-odo-dialogue")
	await seek_with_manual_gates(60)
	if presentation.is_dialogue_waiting():presentation.continue_dialogue();tick(.01)
	expect(presentation.choice_context().waiting,"the framing sample reaches the actual choice after native inspection")
	expect(fixed.is_equal_approx(rig.camera.global_transform),"the tightened camera remains one fixed group shot")
	await create_timer(.5).timeout
	await capture("framing-03-live-player-options")
	root.size=Vector2i(720,480);root.content_scale_factor=1.5
	await capture("framing-04-small-player-options-150-percent")
	await expect_choice_reachable("tight framing small-window options")
	expect_conversation_heads("tight framing small-window options")
	presentation.cancel("framing_complete")

func quick_route_review() -> void:
	await seek_with_manual_gates(60)
	if presentation.is_dialogue_waiting():presentation.continue_dialogue();tick(.01)
	expect(presentation.choice_context().waiting and inspection_calls==["start"],"the alternate route reaches its native inspected decision")
	presentation._choice_dialog.option_buttons[selected_route].pressed.emit();tick(0)
	expect(str(state.scene.choice.selected)==selected_route and presentation._caption.text==state.scene.choice.response,"the alternate "+selected_route+" button gives the recorded Odo response")
	await capture("quick-01-"+selected_route+"-odo-response")
	presentation.skip();tick(.7)
	var original_calls:=choice_calls.duplicate()
	var count:=results.size()
	expect(presentation.request_replay(state,"greenlight"),"the alternate rescue plan can be replayed")
	tick(0);await seek_with_manual_gates(60)
	if presentation.is_dialogue_waiting():presentation.continue_dialogue();tick(.01)
	for button:Button in presentation._choice_dialog.option_buttons.values():
		expect(button.disabled,"alternate rescue replay keeps every plan read-only")
	expect(presentation._choice_dialog._content[selected_route].heading.text.begins_with("✓ "),"alternate replay highlights its actual recorded plan")
	await capture("quick-02-"+selected_route+"-recorded-replay")
	presentation._choice_dialog.continue_button.pressed.emit();tick(1)
	expect(presentation._caption.text==state.scene.choice.response,"alternate replay continues to its recorded Odo instruction")
	presentation.skip();tick(.7)
	expect(choice_calls==original_calls and results.size()==count and inspection_calls==["start"],"alternate rescue replay sends no repeated choice, inspection or normal ACK")
	if not has_snapshot("inquiry-initial"):
		expect(false,"actual inquiry rows are present for the alternate lead");return
	for row:Dictionary in bundle.snapshots:
		if str(row.label)=="inquiry-initial":
			state=snapshot("inquiry-initial");apply_row_positions(row);break
	tick(0);await seek_with_manual_gates(32)
	if presentation.is_dialogue_waiting():presentation.continue_dialogue();tick(.01)
	expect(presentation.choice_context().waiting,"the alternate inquiry presents three actual native leads")
	presentation._choice_dialog.option_buttons[selected_lead].pressed.emit();tick(0)
	expect(str(state.scene.choice.selected)==selected_lead and str(state.inquiry.finding)=="unresolved","the "+selected_lead+" lead selects guidance without proof or rewards")
	await capture("quick-03-"+selected_lead+"-odo-guidance")
	presentation.skip();tick(.7)
	var unchanged:=JSON.stringify(state)
	original_calls=choice_calls.duplicate();count=results.size()
	expect(presentation.request_replay(state,"greenlight"),"the alternate inquiry guidance can be replayed")
	tick(0);await seek_with_manual_gates(32)
	if presentation.is_dialogue_waiting():presentation.continue_dialogue();tick(.01)
	for button:Button in presentation._choice_dialog.option_buttons.values():
		expect(button.disabled,"alternate inquiry replay keeps every lead read-only")
	await capture("quick-04-"+selected_lead+"-recorded-guidance")
	presentation._choice_dialog.continue_button.pressed.emit();tick(1)
	expect(presentation._caption.text==state.scene.choice.response,"alternate inquiry replay repeats its recorded guidance")
	presentation.skip();tick(.7)
	expect(choice_calls==original_calls and results.size()==count and JSON.stringify(state)==unchanged,"alternate inquiry replay creates no new lead request, proof or normal ACK")

func run_arrival(route: String, original: Transform3D, initial_position: Vector3, immutable_fixture: String) -> void:
	var duration:=float(Presentation.scene_definitions()["measure.cart.arrival"].duration)
	var samples := {0.0:"01-player-viewport",1.2:"02-camera-approach",2.6:"03-real-pier-establishing",
		5.0:"04-cart-roll-and-tip",6.8:"05-ground-seated-worker-contact",36.7:"07-player-running-to-cart",
		42.2:"08-player-examines-cart",44.0:"09-player-turns-to-odo",61.0:"13-odo-route-response",
		duration-1.6:"14-gameplay-camera-return",duration-.1:"15-camera-nearly-home"}
	var frames:=0
	var chose:=false
	var held_once:=false
	var group_view:=Transform3D.IDENTITY
	while presentation.playing and frames<2600:
		var elapsed:float=presentation.elapsed
		for stamp:float in samples.keys():
			if elapsed<stamp:continue
			if stamp==36.7:
				expect(inspection_calls==["start"] and actors[local_id]._cinematic_action in [&"walk",&"run"],"one native inspection request accompanies the visible approach")
			if stamp==42.2:
				expect(actors[local_id]._cinematic_action==&"pickup","the player examines the actual cart before receiving choices")
			await capture(str(samples[stamp]));samples.erase(stamp)
		if presentation.is_dialogue_waiting():
			manual_holds+=1
			if not held_once:
				held_once=true
				var at:float=presentation.elapsed
				var camera:Transform3D=rig.camera.global_transform
				var unchanged:=JSON.stringify(state)
				tick(65)
				expect(presentation.is_dialogue_waiting() and is_equal_approx(presentation.elapsed,at) and results.is_empty(),"manual speech waits indefinitely for Continue without acknowledging")
				expect(camera.is_equal_approx(rig.camera.global_transform) and JSON.stringify(state)==unchanged,"a manual dialogue hold preserves the fixed camera and authoritative state")
				await capture("06-manual-dialogue-continue")
				root.size=Vector2i(720,480);root.content_scale_factor=1.5
				await capture("06b-small-manual-line-hold-150-percent")
				expect(root.get_visible_rect().encloses(presentation._line_continue.get_global_rect()),"small manual dialogue keeps Continue fully reachable")
				expect(root.get_visible_rect().encloses(presentation._auto.get_global_rect()) \
					and root.get_visible_rect().encloses(presentation._skip.get_global_rect()),"small manual dialogue keeps Auto and Return fully on screen")
				root.size=Vector2i(1280,720);root.content_scale_factor=1
			expect(presentation.continue_dialogue(),"the public Continue API advances a real dialogue gate")
		if presentation.choice_context().waiting and not chose:
			chose=true
			expect(is_instance_valid(cart.native) and is_equal_approx(cart._display_tilt,17),"the actual tipped cart remains visible when a rescue method is chosen")
			expect(str(state.scene.inspection.status)=="complete","all rescue choices wait for actual recorded inspection proof")
			await create_timer(.35).timeout
			expect_player_dialogue("live rescue decision")
			group_view=rig.camera.global_transform
			var unchanged:=JSON.stringify(state)
			tick(65)
			expect(is_equal_approx(presentation.elapsed,60) and rig.camera.global_transform.is_equal_approx(group_view) and JSON.stringify(state)==unchanged,"the player may consider all approaches while one steady shot and state are held")
			await capture("10-player-profile-three-approaches")
			root.size=Vector2i(720,480);root.content_scale_factor=1.5
			await capture("11-small-player-options-150-percent")
			await expect_choice_reachable("small live rescue decision")
			expect_conversation_heads("small live rescue decision")
			root.size=Vector2i(1280,720);root.content_scale_factor=1
			presentation._choice_dialog.option_buttons[route].pressed.emit();tick(0);tick(0)
			expect(choice_calls==[route] and str(state.scene.choice.selected)==route,"the button receives the actual native "+route+" confirmation")
			expect(not presentation._dialogue.content_active() and presentation._dialogue.speaker_label.text=="Odo Fenn" and presentation._caption.text==state.scene.choice.response,"Odo's native portrait and recorded instructions replace the choices in the same row")
			expect(rig.camera.global_transform.is_equal_approx(group_view),"Odo answers inside the same steady view")
			await capture("12-odo-confirmed-"+route+"-instructions")
		await process_frame;tick(film_step);frames+=1
	expect(chose and not presentation.is_active(),"the complete rescue conversation finishes after its decision and manual gates")
	var expected:=original
	expected.origin+=(actors[local_id] as ReplicatedActor3D).server_target-initial_position
	expect(rig.camera.global_transform.is_equal_approx(expected),"the camera returns to the owner's actual accepted inspection position")
	expect((actors[local_id] as Node3D).global_position.is_equal_approx((actors[local_id] as ReplicatedActor3D).server_target),"the player returns to native control without a positional snap")
	expect(results.size()==1 and inspection_calls==["start"] and JSON.stringify(bundle)==immutable_fixture,"one original scene requests one inspection and one ACK without modifying recorded fixtures")

func replay_arrival() -> void:
	var before:=JSON.stringify(state)
	var calls:=choice_calls.duplicate()
	var acknowledgements:=results.size()
	var requested:bool=presentation.request_replay(state,"greenlight")
	expect(requested,"the complete Last Cart conversation remains replayable")
	if not requested:return
	tick(0)
	var frames:=0
	while presentation.playing and not presentation.choice_context().waiting and frames<2200:
		if presentation.is_dialogue_waiting():presentation.continue_dialogue()
		await process_frame;tick(film_step);frames+=1
	expect(presentation._choice_review and presentation.choice_context().waiting,"replay pauses for read-only review of the recorded rescue approach")
	await create_timer(.35).timeout
	expect_player_dialogue("recorded rescue replay")
	for id:String in presentation._choice_dialog.option_buttons:
		expect(presentation._choice_dialog.option_buttons[id].disabled,"replay "+id+" remains read-only")
	await capture("16-replay-profile-recorded-choice")
	root.size=Vector2i(720,480);root.content_scale_factor=1.5
	await capture("17-small-replay-profile-150-percent")
	await expect_choice_reachable("small recorded replay")
	expect_conversation_heads("small recorded replay")
	presentation._choice_dialog.continue_button.pressed.emit();tick(1)
	expect(presentation._caption.text==state.scene.choice.response and presentation._dialogue.speaker_label.text=="Odo Fenn","replay Continue restores the selected Odo instructions")
	await capture("18-small-replay-odo-instructions")
	presentation.skip();tick(.7)
	expect(results.size()==acknowledgements and inspection_calls==["start"] and choice_calls==calls and JSON.stringify(state)==before,"replay sends no inspection, selection, normal ACK or progress change")
	root.size=Vector2i(1280,720);root.content_scale_factor=1

func render_followups() -> void:
	var shown:Dictionary={}
	for row:Dictionary in bundle.snapshots:
		var scene_id:=str((row.state.get("scene",{}) as Dictionary).get("id",""))
		if scene_id not in ["measure.cart.resolved","measure.claims.inquiry","measure.claims.verified"] or shown.has(scene_id):continue
		if EloriaProtocol.map_id_from_reference(str(row.state.get("map","")))!="greenlight":continue
		shown[scene_id]=true
		state=snapshot(str(row.label))
		if state.is_empty():continue
		apply_row_positions(row)
		tick(0)
		var frames:=0
		var captured:=false
		var choice_submitted:=false
		while presentation.playing and frames<1800:
			if presentation.is_dialogue_waiting():
				if not captured:
					captured=true;await capture("22-"+scene_id.replace(".","-")+"-speech")
				presentation.continue_dialogue()
			if presentation.choice_context().waiting and not choice_submitted:
				choice_submitted=true
				await capture("23-inquiry-player-three-leads")
				if not has_snapshot("inquiry-"+selected_lead+"-selected"):
					expect(false,"native inquiry guidance fixture is available")
					presentation.cancel("fixture_missing");break
				presentation._choice_dialog.option_buttons[selected_lead].pressed.emit();tick(0)
				expect(str(state.scene.choice.selected)==selected_lead and str(state.inquiry.finding)=="unresolved","the inquiry selection records native guidance without inventing a finding")
				await capture("24-inquiry-odo-guidance")
			await process_frame;tick(film_step);frames+=1
		expect(not presentation.is_active(),scene_id+" completes through manual dialogue gates")
		if scene_id=="measure.claims.inquiry" and choice_submitted:
			var unchanged:=JSON.stringify(state)
			var original_calls:=choice_calls.duplicate()
			var count:=results.size()
			expect(presentation.request_replay(state,"greenlight"),"the inquiry guidance scene can be replayed")
			tick(0)
			var replay_frames:=0
			while presentation.playing and not presentation.choice_context().waiting and replay_frames<1400:
				if presentation.is_dialogue_waiting():presentation.continue_dialogue()
				await process_frame;tick(film_step);replay_frames+=1
			for button:Button in presentation._choice_dialog.option_buttons.values():
				expect(button.disabled,"recorded inquiry leads remain read-only during replay")
			await capture("25-inquiry-recorded-lead-replay")
			presentation._choice_dialog.continue_button.pressed.emit();tick(1)
			expect(presentation._caption.text==state.scene.choice.response,"the inquiry replay repeats its recorded Odo guidance")
			presentation.skip();tick(.7)
			expect(JSON.stringify(state)==unchanged and choice_calls==original_calls and results.size()==count,"inquiry replay creates no new guidance request, proof, reward or normal ACK")
	print("Native follow-up scene IDs available: ",shown.keys())

func apply_row_positions(row: Dictionary) -> void:
	if row.has("local_tile"):set_local_tile(Vector2i(row.local_tile[0],row.local_tile[1]),true)
	for key:String in row.get("actor_dtos",{}):
		var id:=int(key)
		if not actors.has(id):continue
		var dto:Dictionary=row.actor_dtos[key].duplicate(true)
		dto.x=dto.tile[0];dto.y=dto.tile[1];dto=main.call("_presentation_dto",dto)
		actors[id].apply_server_state(dto,adapter,true)
	var tiles:Dictionary=row.get("actor_tiles",{})
	for role:String in state.get("actors",{}):
		var id:=int(state.actors[role])
		if not actors.has(id) or role=="protagonist":continue
		var tile:Variant=tiles.get(str(id),tiles.get(role))
		if tile==null and role=="worker":tile=(state.get("cart",{}) as Dictionary).get("worker_tile")
		if not tile is Array:continue
		if row.get("actor_dtos",{}).has(str(id)):continue
		var dto:Dictionary=bundle.cast.get(role,{}).duplicate(true)
		if dto.is_empty():continue
		dto.x=tile[0];dto.y=tile[1];dto=main.call("_presentation_dto",dto)
		actors[id].apply_server_state(dto,adapter,true)

func preview_inspection(action: String) -> void:
	inspection_calls.append(action)
	if action=="start":
		inspection_delivery=42.5
		if has_snapshot("inspection-started"):state=snapshot("inspection-started")
	elif action=="cancel":inspection_delivery=-1

func preview_choose(option_id: String) -> void:
	choice_calls.append(option_id)
	var inquiry:=str((state.scene.get("choice",{}) as Dictionary).get("id",""))=="claims_lead"
	if inquiry:
		var label:="inquiry-"+option_id+"-selected"
		if not has_snapshot(label):presentation.choice_send_failed();return
		state=snapshot(label);return
	if OS.get_environment("RL_FERRY_KEEP_OPEN")=="1":
		var name:="native-opening-bundle.json" if option_id=="unload" else "native-opening-"+option_id+"-bundle.json"
		var path:=fixture_source.get_base_dir().path_join(name)
		if not FileAccess.file_exists(path):presentation.choice_send_failed();return
		bundle=JSON.parse_string(FileAccess.get_file_as_string(path))
	var selected:=snapshot(option_id+"-selected")
	if selected.is_empty():presentation.choice_send_failed();return
	state=selected

func expect_player_dialogue(label: String) -> void:
	expect(presentation._dialogue.content_active() and not presentation._dialogue.body_label.visible \
		and presentation._dialogue.speaker_label.text == str(state.scene.choice.owner), label + " uses the player's named dialogue space")
	expect(presentation._dialogue.portrait_visible() and presentation._dialogue._actor.get_ref() == actors[local_id], label + " uses the actual player headshot")
	expect(presentation._choice_dialog.option_buttons.size() == 3 \
		and presentation._bottom.is_ancestor_of(presentation._choice_dialog), label + " puts all three options inside the NPC dialogue panel")
	var toward: Vector3 = ((actors[int(state.actors.odo)] as Node3D).global_position - (actors[local_id] as Node3D).global_position).normalized()
	expect((-((actors[local_id] as Node3D).global_basis.z)).dot(toward) > 0.8, label + " has the player facing Odo")

func expect_choice_reachable(label: String) -> void:
	var scroll: ScrollContainer = presentation._choice_scroll
	for button: Button in presentation._choice_dialog.option_buttons.values():
		scroll.ensure_control_visible(button)
		await process_frame; await process_frame
		expect(root.get_visible_rect().encloses(button.get_global_rect()) and scroll.get_global_rect().encloses(button.get_global_rect()), label + " can show " + button.name)
	if presentation._choice_dialog.continue_button.visible:
		scroll.ensure_control_visible(presentation._choice_dialog.continue_button)
		await process_frame; await process_frame
		expect(root.get_visible_rect().encloses(presentation._choice_dialog.continue_button.get_global_rect()), label + " can show Continue")
	expect(root.get_visible_rect().encloses(presentation._skip.get_global_rect()) and root.get_visible_rect().encloses(presentation._reduced.get_global_rect()), label + " keeps scene controls outside the scrolling choices")
	expect(root.get_visible_rect().encloses(presentation._auto.get_global_rect()),label+" keeps the Auto dialogue control fully on screen")

func expect_conversation_heads(label: String) -> void:
	for role: String in ["odo", "foreman", "worker", "protagonist"]:
		var binding: Dictionary = state.scene.get("actors", state.actors)
		var actor: ReplicatedActor3D = actors[int(binding[role])]
		var skeleton := actor.get_skeleton()
		var bone:=skeleton.find_bone("Head")
		if bone<0:bone=skeleton.find_bone("head")
		expect(bone>=0,label+" has a native head bone for "+role)
		if bone<0:continue
		var head := skeleton.global_transform * skeleton.get_bone_global_pose(bone).origin
		var screen := rig.camera.unproject_position(head)
		expect(screen.y > 70.0 and screen.y + 12.0 < presentation._bottom.position.y \
			and root.get_visible_rect().has_point(screen), label + " keeps " + role + " visible above the dialogue")

func review_smoke(option_id: String) -> void:
	var original:Transform3D=rig.camera.global_transform
	var initial:Vector3=actors[local_id].global_position
	await run_arrival(option_id,original,initial,JSON.stringify(bundle))
	await replay_arrival()

func review_loop() -> void:
	root.title = "Rabbit Lands · Last Cart review · Choose a plan in your dialogue panel · Space to replay · Esc to return/close"
	var escaped := false
	var spaced := false
	var close := [false]
	set_auto_accept_quit(false)
	root.close_requested.connect(func() -> void: close[0] = true)
	var review_seconds := OS.get_environment("RL_FERRY_REVIEW_SECONDS").to_float()
	var began := Time.get_ticks_msec()
	while not close[0]:
		await process_frame
		if review_seconds > 0 and Time.get_ticks_msec() - began > review_seconds * 1000: break
		if not presentation.is_active() and not results.is_empty():
			state.scene.requires_ack = false
			state.party.waiting_for_scene = false
		var escape := Input.is_physical_key_pressed(KEY_ESCAPE)
		var space := Input.is_physical_key_pressed(KEY_SPACE)
		if escape and not escaped:
			if presentation._transcript.visible: presentation._transcript.hide()
			elif presentation.playing: presentation.skip()
			else: break
		if space and not spaced: presentation.request_replay(state, "greenlight")
		escaped = escape; spaced = space
		tick(minf(root.get_process_delta_time(), 0.1))
	presentation.cancel("preview_closed")

func finish_preview() -> void:
	expect(await ContinentChunkStream.drain_workers(self), "native preview streaming workers retire")
	var report := FileAccess.open(directory.path_join("report.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"checks": checks, "failures": failures, "captures": captures, "route":selected_route, "manual_holds":manual_holds, "source_bundle":fixture_source, "source_presenter_sha256":FileAccess.get_sha256("res://src/world/campaign_cart.gd"),
		"native_cast": bundle.cast.keys(), "native_objects": objects.size(), "offline": true, "choice_calls": choice_calls, "inspection_calls": inspection_calls,
		"playthrough_source":playthrough_source,"multiple_recorded_native_sessions":not playthrough_source.is_empty()}, "  "))
	presentation.queue_free(); guide.queue_free(); stage.queue_free(); main.queue_free()
	await process_frame; await process_frame
	print("native cart: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func set_local_tile(tile: Vector2i, teleport := false) -> void:
	var actor: ReplicatedActor3D = actors[local_id]
	var dto: Dictionary = bundle.players[0].duplicate(true)
	dto.x = tile.x; dto.y = tile.y
	dto = main.call("_presentation_dto", dto)
	actor.apply_server_state(dto, adapter, teleport)
	var height: float = main.call("_campaign_surface_height", actor.global_position)
	if is_finite(height): actor.set_surface_height(height)
	if not presentation.is_active(): rig.set_focus(actor.global_position)

func tick(delta: float) -> void:
	if inspection_delivery >= 0.0 and presentation.elapsed + delta >= inspection_delivery:
		inspection_delivery = -1.0
		state = snapshot("post-inspect")
		var approach: Array = state.scene.inspection.approach
		set_local_tile(Vector2i(int(approach[0]), int(approach[1])))
	cart.apply_snapshot(state, adapter, "greenlight", Callable(main, "_campaign_surface_height"))
	presentation.update_ambient(state,actors,adapter,Callable(main,"_campaign_surface_height"),delta)
	presentation.update(delta, state, rig, actors, local_id, "greenlight", true, adapter, Callable(main, "_campaign_surface_height"))
	var progress:float=presentation.cart_accident_progress()
	if progress>=0:cart.set_cinematic_accident(progress)
	else:cart.clear_cinematic_presentation()
	var tile: Vector2i = adapter.godot_to_server((actors[local_id] as Node3D).global_position)
	hud.apply_state(state, tile, "greenlight", presentation.reduced_motion, presentation.is_active())
	hud.set_replay_available(presentation.can_replay(state, "greenlight"))
	guide.apply_campaign(state)
	guide._process(0.0)
	guidance.apply_snapshot(state, objects, actors, "greenlight", tile, guide.using_campaign(), presentation.is_active())
	cart.set_readouts_visible(guide.using_campaign() and not presentation.is_active())

func visible_rings() -> int:
	var count := 0
	for object: MapObject3D in objects.values():
		var ring := object.get_node_or_null("Ring") as Node3D
		if is_instance_valid(ring) and ring.visible: count += 1
	return count

func capture(label: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(directory.path_join(label + ".png")) == OK, "captured " + label)
	captures.append(label)

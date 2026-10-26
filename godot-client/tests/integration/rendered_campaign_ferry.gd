extends SceneTree
## Offline review of actual native-session packets, imported actors and quay.
## RL_FERRY_NATIVE_BUNDLE supplies the server test export; no connection/save.
const Presentation := preload("res://src/world/campaign_scene.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const Crossing := preload("res://src/world/campaign_crossing.gd")
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
var crossing: Node3D
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
			expect(decoded.get("type") == "campaign", "native " + label + " packet decodes")
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
		create_timer(200).timeout.connect(func() -> void: push_error("Native ferry preview timed out"); quit(1))
	Engine.max_fps = 30
	var source := OS.get_environment("RL_FERRY_NATIVE_BUNDLE")
	if source.is_empty():
		push_error("Set RL_FERRY_NATIVE_BUNDLE to the native-session ferry fixture JSON.")
		quit(1)
		return
	bundle = JSON.parse_string(FileAccess.get_file_as_string(source))
	local_id = int(bundle.local_actor_id)
	adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [435, 448], "walkingHeight": 2.5})
	fixture_source = source
	directory = OS.get_environment("RL_FERRY_PREVIEW_OUT")
	if directory.is_empty(): directory = "user://ferry-preview"
	DirAccess.make_dir_recursive_absolute(directory)
	root.size = Vector2i(1280, 720)
	root.title = "Rabbit Lands · Ferry cinematic review (offline)"
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
	presentation.presentation_finished.connect(func(token: String, reason: String) -> void: results.append([token, reason]))
	presentation.choice_requested.connect(preview_choose)
	presentation.inspection_requested.connect(preview_inspection)
	guidance = Guidance.new()
	stage.add_child(guidance)
	crossing = Crossing.new()
	stage.add_child(crossing)
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
	if OS.get_environment("RL_FERRY_KEEP_OPEN") == "1":
		var smoke := OS.get_environment("RL_FERRY_REVIEW_SMOKE")
		if smoke in ["defend", "repair", "evacuate"]: await review_smoke(smoke)
		else: await review_loop()
		await finish_preview()
		return
	var samples := {0.0:"01-player-viewport", 1.2:"02-camera-approach", 2.4:"03-quay-establishing",
		6.1:"04-odo-briefing", 10.2:"05-clerk-dialogue", 14.2:"06-foreman-dialogue",
		19.7:"07-player-walking-to-damage", 22.4:"08-player-inspecting-damage", 24.7:"09-player-turns-to-odo",
		27.2:"13-odo-response-in-same-dialogue", 37.2:"14-crew-returning", 39.2:"15-camera-return", 39.9:"16-camera-nearly-home"}
	var frames := 0
	var chose := false
	var group_view := Transform3D.IDENTITY
	while presentation.playing and frames <= 1260:
		var time: float = presentation.elapsed
		for stamp: float in samples.keys():
			if time >= stamp:
				if stamp == 19.7:
					expect(inspection_calls == ["start"] and (actors[local_id] as ReplicatedActor3D)._cinematic_action in [&"walk", &"run"], "the protagonist approaches the real pier during one native inspection request")
				if stamp == 22.4:
					expect((actors[local_id] as ReplicatedActor3D)._cinematic_action == &"pickup", "the protagonist visibly examines the damaged boards before deciding")
				await capture(str(samples[stamp]))
				samples.erase(stamp)
		if presentation.choice_context().waiting and not chose:
			chose = true
			expect(is_instance_valid(crossing.native) and crossing.debris.visible, "the damaged access has a visible approved debris model on the real pier")
			expect(str(state.scene.inspection.status) == "complete", "choices wait for the native inspection proof")
			expect_player_dialogue("live decision")
			group_view = rig.camera.global_transform
			var unchanged := JSON.stringify(state)
			tick(65.0)
			expect(is_equal_approx(presentation.elapsed, 26.0) and rig.camera.global_transform.is_equal_approx(group_view) and JSON.stringify(state) == unchanged, "the inspection and decision share one steady shot while the player considers the options")
			await capture("10-player-profile-and-options")
			root.size = Vector2i(720,480); root.content_scale_factor = 1.5
			await capture("11-small-player-profile-and-options-150-percent")
			await expect_choice_reachable("live small-window decision")
			expect_conversation_heads("live small-window decision")
			root.size = Vector2i(1280,720); root.content_scale_factor = 1.0
			presentation._choice_dialog.option_buttons.repair.pressed.emit()
			tick(0.0); tick(0.0)
			expect(choice_calls == ["repair"] and str(state.scene.choice.selected) == "repair", "the player's option receives the actual native repair confirmation")
			expect(not presentation._dialogue.content_active() and presentation._dialogue.speaker_label.text == "Odo Fenn" and presentation._caption.text == state.scene.choice.response, "Odo's portrait and instructions replace the player options in the same dialogue row")
			expect(rig.camera.global_transform.is_equal_approx(group_view), "Odo responds without changing the established group camera")
			await capture("12-odo-instructions-after-choice")
		await process_frame
		tick(1.0 / 30.0)
		frames += 1
	var expected := original
	expected.origin += (actors[local_id] as ReplicatedActor3D).server_target - initial_position
	expect(not presentation.is_active() and rig.camera.global_transform.is_equal_approx(expected), "the viewport returns smoothly to the player's real inspection position")
	expect((actors[local_id] as Node3D).global_position.is_equal_approx((actors[local_id] as ReplicatedActor3D).server_target), "the protagonist returns to native control without a position snap")
	expect(results.size() == 1 and inspection_calls == ["start"] and JSON.stringify(bundle) == immutable_fixture, "the single scene requests one native inspection and acknowledges once without modifying the recorded fixture")
	var recorded := JSON.stringify(state)
	expect(presentation.request_replay(state, "greenlight"), "the complete inspection conversation can be replayed")
	tick(0.0); tick(19.7)
	expect(inspection_calls == ["start"], "replaying the walk sends no native inspection or movement request")
	tick(6.4)
	# A direct seek changes the native actor's target yaw. Let its ordinary
	# turn interpolation catch up, as it does during the authored two-second turn.
	await create_timer(0.35).timeout
	expect_player_dialogue("recorded replay")
	expect(presentation._choice_dialog.continue_button.visible and presentation._choice_dialog.status_label.text.begins_with("Recorded choice:"), "replay shows the recorded plan and waits for Continue")
	for id: String in presentation._choice_dialog.option_buttons:
		expect(presentation._choice_dialog.option_buttons[id].disabled, "replay " + id + " stays read-only")
	await capture("17-replay-player-profile-recorded-choice")
	root.size = Vector2i(720,480); root.content_scale_factor = 1.5
	await capture("18-small-replay-player-profile-150-percent")
	await expect_choice_reachable("replay small-window decision")
	expect_conversation_heads("replay small-window decision")
	presentation._choice_dialog.continue_button.pressed.emit(); tick(1.0)
	expect(presentation._caption.text == state.scene.choice.response and presentation._dialogue.speaker_label.text == "Odo Fenn", "replay Continue restores Odo and his recorded follow-up")
	await capture("19-small-odo-followup-150-percent")
	presentation.skip(); tick(0.7)
	expect(results.size() == 1 and inspection_calls == ["start"] and choice_calls == ["repair"] and JSON.stringify(state) == recorded, "replay cannot repeat inspection, choice, progress or scene acknowledgment")
	root.size = Vector2i(1280,720); root.content_scale_factor = 1.0
	state = snapshot("repair-seal-inspected")
	for row: Dictionary in bundle.snapshots:
		if str(row.label) == "repair-seal-inspected":
			set_local_tile(Vector2i(int(row.local_tile[0]), int(row.local_tile[1])), true)
	tick(0.0)
	await capture("20-next-quest-action-after-conversation")
	await finish_preview()

func preview_inspection(action: String) -> void:
	inspection_calls.append(action)
	if action == "start": inspection_delivery = 23.0
	elif action == "cancel": inspection_delivery = -1.0

func preview_choose(option_id: String) -> void:
	choice_calls.append(option_id)
	if OS.get_environment("RL_FERRY_KEEP_OPEN") == "1":
		var name := "native-opening-bundle.json" if option_id == "repair" else "native-opening-" + option_id + "-bundle.json"
		var path := fixture_source.get_base_dir().path_join(name)
		if not FileAccess.file_exists(path):
			presentation.choice_send_failed()
			return
		bundle = JSON.parse_string(FileAccess.get_file_as_string(path))
	state = snapshot(option_id + "-selected")

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

func expect_conversation_heads(label: String) -> void:
	for role: String in ["odo", "clerk", "foreman", "protagonist"]:
		var binding: Dictionary = state.scene.get("actors", state.actors)
		var actor: ReplicatedActor3D = actors[int(binding[role])]
		var skeleton := actor.get_skeleton()
		var head := skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin
		var screen := rig.camera.unproject_position(head)
		expect(screen.y > 70.0 and screen.y + 12.0 < presentation._bottom.position.y \
			and root.get_visible_rect().has_point(screen), label + " keeps " + role + " visible above the dialogue")

func review_smoke(option_id: String) -> void:
	tick(19.0); tick(5.0); tick(2.0)
	expect(presentation.choice_context().waiting and inspection_calls == ["start"], "offline review walks, inspects and opens options in one scene")
	presentation._choice_dialog.option_buttons[option_id].pressed.emit()
	tick(0.0); tick(1.0)
	expect(choice_calls == [option_id] and str(state.scene.choice.selected) == option_id and presentation._caption.text == state.scene.choice.response, "offline " + option_id + " shows its native confirmed response")
	tick(20.0)
	state.scene.requires_ack = false; state.party.waiting_for_scene = false
	tick(0.0)
	var recorded := JSON.stringify(state)
	expect(presentation.request_replay(state, "greenlight"), "offline inspection conversation remains replayable")
	tick(0.0); tick(26.1)
	await create_timer(0.35).timeout
	expect_player_dialogue("offline replay")
	await capture("offline-" + option_id + "-player-recorded-choice")
	presentation._choice_dialog.continue_button.pressed.emit(); tick(1.0)
	expect(presentation._caption.text == state.scene.choice.response, "offline Continue repeats the recorded response")
	presentation.skip(); tick(0.7)
	expect(results.size() == 1 and choice_calls == [option_id] and inspection_calls == ["start"] and JSON.stringify(state) == recorded, "offline replay is read-only")

func review_loop() -> void:
	root.title = "Rabbit Lands · Ferry review · Choose a plan in your dialogue panel · Space to replay · Esc to return/close"
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
	report.store_string(JSON.stringify({"checks": checks, "failures": failures, "captures": captures,
		"native_cast": bundle.cast.keys(), "native_objects": objects.size(), "offline": true, "choice_calls": choice_calls, "inspection_calls": inspection_calls}, "  "))
	presentation.queue_free(); guide.queue_free(); stage.queue_free(); main.queue_free()
	await process_frame; await process_frame
	print("native ferry: ", checks, " checks; ", failures, " failures")
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
	crossing.apply_snapshot(state, adapter, "greenlight", Callable(main, "_campaign_surface_height"))
	presentation.update(delta, state, rig, actors, local_id, "greenlight", true, adapter, Callable(main, "_campaign_surface_height"))
	var tile: Vector2i = adapter.godot_to_server((actors[local_id] as Node3D).global_position)
	hud.apply_state(state, tile, "greenlight", presentation.reduced_motion, presentation.is_active())
	hud.set_replay_available(presentation.can_replay(state, "greenlight"))
	guide.apply_campaign(state)
	guide._process(0.0)
	guidance.apply_snapshot(state, objects, actors, "greenlight", tile, guide.using_campaign(), presentation.is_active())
	crossing.set_readouts_visible(guide.using_campaign() and not presentation.is_active())

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

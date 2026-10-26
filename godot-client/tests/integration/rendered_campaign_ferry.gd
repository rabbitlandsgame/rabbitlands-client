extends SceneTree
## Offline review of actual native-session packets, imported actors and quay.
## RL_FERRY_NATIVE_BUNDLE supplies the server test export; no connection/save.
const Presentation := preload("res://src/world/campaign_scene.gd")
const Guidance := preload("res://src/world/campaign_guidance.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
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
	loader.load_world(ProjectSettings.globalize_path("res://../eloria-assets/maps/continent-v2/greenlight/client/world.json"), Vector3(15.5, 2.5, 140.5))
	var deadline := Time.get_ticks_msec() + 90000
	while not loaded[0] and Time.get_ticks_msec() < deadline: await process_frame
	expect(loaded[0], "the production Greenlight quay loads")
	if not loaded[0]: quit(1); return
	main.gameplay_world = stage.get_world_3d()
	adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [435, 448], "walkingHeight": 2.5})
	main.adapter = adapter
	local_id = int(bundle.local_actor_id)
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
	guidance = Guidance.new()
	stage.add_child(guidance)
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
	hud.target_requested.connect(func(_id: int, _tile: Vector2i, _nearby: bool) -> void:
		if OS.get_environment("RL_FERRY_KEEP_OPEN") == "1" and str(state.scene.id) == "measure.landing.arrival" and not presentation.is_active():
			state = snapshot("post-inspect")
			set_local_tile(Vector2i(450, 309)))
	root.get_node("AppState").authenticated = true
	state = snapshot("initial")
	preview_run = str(state.run_id)
	var source_state := JSON.stringify(state)
	var original: Transform3D = rig.camera.global_transform
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
	if OS.get_environment("RL_FERRY_PLAN_ONLY") == "1": tick(28.0)
	var samples := {0.0: "01-player-viewport", 1.2: "02-camera-approach", 2.4: "03-quay-establishing",
		6.1: "04-odo-briefing", 10.2: "05-clerk-dialogue", 14.2: "06-foreman-dialogue",
		19.2: "07-first-step-instruction", 24.8: "08-crew-returning", 27.2: "09-camera-return", 27.9: "10-camera-nearly-home"}
	var frames := 0
	while presentation.playing and frames <= 850:
		var time: float = presentation.elapsed
		for stamp: float in samples.keys():
			if time >= stamp:
				await capture(str(samples[stamp]))
				samples.erase(stamp)
		await process_frame
		tick(1.0 / 30.0)
		frames += 1
	expect(not presentation.is_active() and rig.camera.global_transform.is_equal_approx(original), "native completion returns to the exact original camera")
	expect(results.size() == 1 and JSON.stringify(state) == source_state, "the whole scene leaves native objectives untouched and completes once")
	state = snapshot("initial-ready")
	tick(0.0)
	expect(visible_rings() == 1 and guidance._labels.assess.visible, "only the named first work circle is visible after the briefing")
	await capture("11-first-objective-and-marker")
	state = snapshot("post-inspect")
	set_local_tile(Vector2i(450, 309))
	tick(0.0)
	tick(6.1)
	expect(presentation.choice_context().waiting and presentation._choice_dialog.option_buttons.size() == 3, "inspection opens all three native rescue plans inside Odo's scene")
	var group_view: Transform3D = rig.camera.global_transform
	tick(20.0)
	expect(is_equal_approx(presentation.elapsed, 6.0) and rig.camera.global_transform.is_equal_approx(group_view), "the group camera and conversation wait steadily for a decision")
	await capture("12-three-rescue-plans")
	root.size = Vector2i(720, 480); root.content_scale_factor = 1.5
	await capture("13-small-rescue-plans-150-percent")
	expect_choice_fits("live small-window choice")
	expect_conversation_heads("live small-window choice")
	root.size = Vector2i(1280, 720); root.content_scale_factor = 1.0
	var source_choice := JSON.stringify(state.scene.choice)
	presentation._choice_dialog.option_buttons.repair.pressed.emit()
	expect(choice_calls == ["repair"] and str(state.scene.choice.selected) == "repair", "the real repair option requests the native fixture's authoritative confirmation once")
	tick(0.0); tick(1.0)
	expect(presentation._dialogue.speaker_label.text == "Odo Fenn" and presentation._caption.text == state.scene.choice.response, "Odo explains the selected route after confirmation")
	expect(rig.camera.global_transform.is_equal_approx(group_view) and source_choice != JSON.stringify(state.scene.choice), "the response keeps the established group view")
	await capture("14-odo-repair-instructions")
	tick(20.0)
	expect(not presentation.is_active() and results.size() == 2, "the plan scene returns control after its response")
	state = snapshot("repair-seal-inspected")
	set_local_tile(Vector2i(449, 301))
	tick(0.0)
	await capture("15-branch-objective")
	var replay_state := JSON.stringify(state)
	expect(presentation.request_replay(state, "greenlight"), "the current native plan can be replayed after completion")
	tick(0.0); tick(6.1)
	expect(presentation._choice_dialog.option_buttons.size() == 3 and presentation._choice_dialog.continue_button.visible, "replay displays all three options and waits for Continue")
	for id: String in presentation._choice_dialog.option_buttons:
		expect(presentation._choice_dialog.option_buttons[id].disabled, "replay " + id + " is read-only")
	expect(presentation._choice_dialog.status_label.text.begins_with("Recorded choice: Repair"), "replay identifies the owner's recorded plan")
	await capture("16-replay-recorded-choice")
	root.size = Vector2i(720, 480); root.content_scale_factor = 1.5
	await capture("17-small-replay-choice-150-percent")
	expect_choice_fits("replay small-window choice")
	expect_conversation_heads("replay small-window choice")
	presentation._choice_dialog.continue_button.pressed.emit()
	tick(1.0)
	expect(presentation._caption.text == state.scene.choice.response, "replay repeats Odo's recorded instructions after Continue")
	await capture("18-small-replay-followup-150-percent")
	presentation.skip(); tick(0.7)
	expect(results.size() == 2 and choice_calls == ["repair"] and JSON.stringify(state) == replay_state, "replay changes no native objective, reward, decision or scene acknowledgment")
	root.size = Vector2i(1280, 720); root.content_scale_factor = 1.0
	state = snapshot("initial-ready")
	set_local_tile(Vector2i(450, 308))
	root.size = Vector2i(720, 480)
	root.content_scale_factor = 1.5
	tick(0.0)
	await capture("19-small-quest-guidance-150-percent")
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1.0
	tick(0.0)
	expect(presentation.request_replay(state, "greenlight"), "native replay remains available after reviewing the same current scene")
	tick(0.0); tick(10.2)
	expect(presentation._dialogue.portrait_visible() and presentation._dialogue.speaker_label.text == "Landing clerk", "the cinematic headshot follows the actual speaking clerk")
	root.size = Vector2i(720, 480); root.content_scale_factor = 1.5
	await capture("20-small-clerk-headshot-150-percent")
	presentation.skip(); tick(0.7)
	expect(results.size() == 2 and not presentation.is_active(), "native replay's smooth return never repeats the original completion")
	await finish_preview()

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

func expect_choice_fits(label: String) -> void:
	var viewport := root.get_visible_rect()
	var scroll: ScrollContainer = presentation._choice_scroll
	for button: Button in presentation._choice_dialog.option_buttons.values():
		expect(viewport.encloses(button.get_global_rect()) and scroll.get_global_rect().encloses(button.get_global_rect()), label + " shows " + button.name)
	if presentation._choice_dialog.continue_button.visible:
		expect(viewport.encloses(presentation._choice_dialog.continue_button.get_global_rect()), label + " shows Continue")

func expect_conversation_heads(label: String) -> void:
	for role: String in ["odo", "clerk", "foreman"]:
		var actor: ReplicatedActor3D = actors[int(state.actors[role])]
		var skeleton := actor.get_skeleton()
		var head := skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin
		var screen := rig.camera.unproject_position(head)
		expect(screen.y > 70.0 and screen.y + 12.0 < presentation._choice_scroll.position.y \
			and root.get_visible_rect().has_point(screen), label + " keeps " + role + " visible between the title and options")

func review_smoke(option_id: String) -> void:
	presentation.skip(); tick(0.7)
	state = snapshot("initial-ready"); tick(0.0)
	hud.target_requested.emit(61001, Vector2i(450,309), true)
	tick(0.0); tick(6.1)
	expect(str(state.scene.id) == "measure.landing.plan" and presentation.choice_context().waiting, "offline Inspect starts the interactive plan scene")
	presentation._choice_dialog.option_buttons[option_id].pressed.emit()
	tick(0.0); tick(1.0)
	expect(choice_calls == [option_id] and str(state.scene.choice.selected) == option_id \
		and str(state.run_id) == preview_run and presentation._caption.text == state.scene.choice.response, "offline " + option_id + " shows that native route's confirmed response")
	tick(20.0)
	state.scene.requires_ack = false
	state.party.waiting_for_scene = false
	tick(0.0)
	var recorded := JSON.stringify(state)
	expect(presentation.request_replay(state, "greenlight"), "offline recorded plan remains replayable")
	tick(0.0); tick(6.1)
	expect(presentation._choice_dialog.option_buttons.size() == 3 \
		and presentation._choice_dialog.status_label.text.begins_with("Recorded choice:"), "offline replay shows all three plans with the recorded highlight")
	await capture("offline-" + option_id + "-recorded-choice")
	presentation._choice_dialog.continue_button.pressed.emit()
	tick(1.0)
	expect(presentation._caption.text == state.scene.choice.response, "offline Continue repeats the recorded response")
	presentation.skip(); tick(0.7)
	expect(results.size() == 2 and choice_calls == [option_id] and JSON.stringify(state) == recorded, "offline replay is read-only and does not repeat a decision")

func review_loop() -> void:
	root.title = "Rabbit Lands · Ferry review · Inspect landing in guide to choose a plan · Space to replay · Esc to return/close"
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
		if not presentation.is_active() and not results.is_empty() and bool((state.get("party", {}) as Dictionary).get("waiting_for_scene", false)):
			if str(state.scene.id) == "measure.landing.arrival":
				state = snapshot("initial-ready")
			else:
				# This view only acknowledges presentation locally. No server,
				# objective completion, items or persistent player save is used.
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
		"native_cast": bundle.cast.keys(), "native_objects": objects.size(), "offline": true, "choice_calls": choice_calls}, "  "))
	presentation.queue_free(); guide.queue_free(); stage.queue_free(); main.queue_free()
	await process_frame; await process_frame
	print("native ferry: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func set_local_tile(tile: Vector2i) -> void:
	var actor: ReplicatedActor3D = actors[local_id]
	var dto: Dictionary = bundle.players[0].duplicate(true)
	dto.x = tile.x; dto.y = tile.y
	dto = main.call("_presentation_dto", dto)
	actor.apply_server_state(dto, adapter, true)
	var height: float = main.call("_campaign_surface_height", actor.global_position)
	if is_finite(height): actor.set_surface_height(height)
	rig.set_focus(actor.global_position)

func tick(delta: float) -> void:
	presentation.update(delta, state, rig, actors, local_id, "greenlight", true, adapter, Callable(main, "_campaign_surface_height"))
	var tile: Vector2i = adapter.godot_to_server((actors[local_id] as Node3D).global_position)
	hud.apply_state(state, tile, "greenlight", presentation.reduced_motion, presentation.is_active())
	hud.set_replay_available(presentation.can_replay(state, "greenlight"))
	guide.apply_campaign(state)
	guide._process(0.0)
	guidance.apply_snapshot(state, objects, actors, "greenlight", tile, guide.using_campaign(), presentation.is_active())

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

extends SceneTree
## Run through the real creation form, tutorial dialogue and return against
## the disposable server started by new_character_greeting_local.py.
var main: Control
var state: Node
var output := ""
var failures := 0
var decline := false

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func capture(name: String) -> void:
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(name + ".png"))

func run() -> void:
	decline = OS.get_environment("ELORIA_GREETING_DECLINE") == "1"
	output = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/new-character-greeting")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1280,720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	main.call("_on_connect_pressed")
	var deadline := Time.get_ticks_msec() + 15000
	while state.connection_state != "connected" and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(state.connection_state == "connected", "connected to disposable local server")
	if state.connection_state != "connected":
		await finish()
		return
	main.call("_on_new_character_pressed")
	main.create_name.text = "Arrival%d" % (Time.get_ticks_msec() % 1000000)
	main.create_password.text = "GreetingFixture42"
	main.create_confirm.text = "GreetingFixture42"
	var intro: Node = main.character_intro
	var stream: ContinentChunkStream = intro._stream
	deadline = Time.get_ticks_msec() + 90000
	while is_instance_valid(stream) and not stream.views_ready() and Time.get_ticks_msec() < deadline:
		await process_frame
	main.call("_on_create_pressed")
	deadline = Time.get_ticks_msec() + 15000
	while not state.authenticated and Time.get_ticks_msec() < deadline:
		await process_frame
	expect(state.authenticated, "character created and logged in through the production form")
	if not state.authenticated:
		await finish()
		return
	var captured := {}
	var answered := false
	var closed := false
	var conversation_at := 0
	var saw_return := false
	deadline = Time.get_ticks_msec() + 90000
	while intro.blocks_input() and Time.get_ticks_msec() < deadline:
		await process_frame
		var phase: StringName = intro.greeting_phase
		if phase == &"wave" and intro._phase_elapsed > 0.7 and not captured.has("wave"):
			captured.wave = true
			var guide: ReplicatedActor3D = intro._guide
			expect(guide.current_action == &"emote_greet", "Nash plays the imported greeting animation")
			expect(not bool(state.lantern_tutorial.get("active", false)) and main.quest_trail.points.is_empty(),
				"the quest and trail wait for the player's acceptance")
			await capture("greeting-wave")
		if phase == &"approach" and intro._phase_elapsed > 0.3 and not captured.has("approach"):
			captured.approach = true
			expect((intro._guide as ReplicatedActor3D).current_action == &"run", "approach uses the running animation")
			expect((intro._guide_beacon as Node3D).global_position.distance_to((intro._guide as Node3D).global_position) < 0.01,
				"green particle animation follows Nash's running feet")
			await capture("greeting-approach")
		if phase == &"conversation":
			if not captured.has("conversation"):
				captured.conversation = true
				conversation_at = Time.get_ticks_msec()
				expect(main.dialogue_panel.visible and str(state.npc_dialogue.get("text", "")).contains("Ilyon"),
					"Nash automatically opens the real first tutorial conversation")
				expect(bool(main.call("_movement_locked", true)), "dialogue keeps player movement locked")
				expect((state.npc_dialogue.get("options", []) as Array).any(func(option: Dictionary) -> bool:
					return int(option.get("response_id", option.get("id", -1))) == 1523), "Nash offers a not-right-now choice")
				await capture("greeting-conversation")
			if not answered and Time.get_ticks_msec() - conversation_at > 1200:
				answered = true
				main.call("_on_dialogue_option", int(intro._guide_id), 1523 if decline else 1520)
				if decline:
					closed = true
			if answered and not closed and Time.get_ticks_msec() - conversation_at > 2800:
				closed = true
				expect(_has_item("Mortar and Pestle"), "the real dialogue issues the tutorial field kit")
				main.call("_on_dialogue_option", int(intro._guide_id), 900)
		if phase == &"return":
			saw_return = true
			if intro._phase_elapsed > 0.3 and not captured.has("return"):
				captured.return = true
				expect(bool(main.call("_movement_locked", true)), "closing dialogue keeps movement locked during Nash's return")
				expect((intro._guide_beacon as Node3D).global_position.distance_to((intro._guide as Node3D).global_position) < 0.01,
					"green animation follows the return to Nash's post")
				await capture("greeting-return")
	expect(saw_return and not intro.blocks_input(), "player control unlocks after Nash returns to his post")
	expect(captured.size() == 4 and answered and closed, "all stages completed without a skipped conversation")
	for frame: int in range(3):
		await process_frame
	await capture("greeting-finished")
	if decline:
		expect(not bool(state.lantern_tutorial.get("active", false)) and main.quest_trail.points.is_empty()
			and not _has_item("Cloth Roll"), "declining leaves no assigned quest, field kit, or trail")
	else:
		if int(state.lantern_tutorial.get("stage", 0)) == 1:
			for slot: Variant in state.inventory_names:
				if state.inventory.has(slot) and state.inventory_names[slot] == "Militia Arming Sword" and int(slot) < 36:
					main.call("_equip_inventory_slot", int(slot))
					break
		deadline = Time.get_ticks_msec() + 10000
		while main.quest_trail.points.size() < 4 and Time.get_ticks_msec() < deadline:
			await process_frame
		await create_timer(0.6).timeout
		expect(main.quest_trail.points.size() > 4 and main.quest_trail._visible.size() > 1,
			"accepting and equipping reveals the ground trail to Sage")
		await capture("quest-trail-ground")
		var pitch: float = main.camera_rig.pitch_degrees
		main.camera_rig.pitch_degrees = -55.0
		await create_timer(0.3).timeout
		await capture("quest-trail-overhead")
		main.camera_rig.pitch_degrees = pitch
		main.call("_toggle_full_map")
		await create_timer(1.0).timeout
		expect(main.full_map.visible and main.quest_trail.map_marks().size() > 1, "full map retains the quest route")
		await capture("quest-trail-map")
	await finish()

func _has_item(name: String) -> bool:
	for slot: Variant in state.inventory_names:
		if state.inventory.has(slot) and str(state.inventory_names[slot]) == name:
			return true
	return false

func finish() -> void:
	if is_instance_valid(main):
		main.set_process(false)
		main.character_intro.cancel()
		root.get_node("Network").disconnect_from_server()
	await process_frame
	if is_instance_valid(main):
		main.exterior_stream.clear()
		while not main.exterior_stream.is_idle():
			await process_frame
	await ContinentChunkStream.drain_workers(self)
	if is_instance_valid(main):
		main.queue_free()
	await process_frame
	print("rendered new-character greeting: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

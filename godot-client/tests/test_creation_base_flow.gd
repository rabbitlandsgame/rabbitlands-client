extends SceneTree
## Actual Main entry, staged previews, cancellation and protocol-safe form values.
## Use the real renderer and -- --no-map-cache to skip unrelated map cooking.
const PC := preload("res://src/actors/portrait_customization.gd")
var failures: Array[String] = []
var checks := 0
var main: Control
var flow: Variant
var network: Node
var _scene_viewport_budget := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func settle() -> void:
	for frame: int in 4:
		await process_frame

func capture(label: String) -> void:
	if DisplayServer.get_name() == "headless":
		return
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--capture-dir="):
			var folder := argument.trim_prefix("--capture-dir=")
			DirAccess.make_dir_recursive_absolute(folder)
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(folder.path_join(label + ".png")) == OK,
				"Saved UI review capture " + label)

func appearance() -> Dictionary:
	return main.call("_creation_appearance")

func form_state() -> Dictionary:
	return {"appearance": appearance().duplicate(true),
		"actor_type": (main.get_node("%CreateGender") as OptionButton).get_selected_id(),
		"calling": main.get("selected_creation_class"),
		"name": (main.get_node("%CreateName") as LineEdit).text,
		"password": (main.get_node("%CreatePassword") as LineEdit).text,
		"confirm": (main.get_node("%CreateConfirm") as LineEdit).text}

func choose(id: String) -> void:
	flow.picker._select_card(id)
	flow.picker._use_basis()
	await settle()

func ssarathi_id(actor_type: int) -> String:
	for row: Dictionary in flow._rows:
		if int(row.look.actor_type) == actor_type:
			return str(row.id)
	return ""

func check_preview_budget(phase: String) -> void:
	var actors: Array[Node] = []
	for node: Node in main.find_children("*", "Node", true, false):
		if node is ReplicatedActor3D and not node.is_queued_for_deletion():
			actors.append(node)
	check(actors.size() == 1 and actors[0] == main.get("preview_actor"),
		phase + ": only the selected creation preview owns a live actor")
	check(main.find_children("*", "SubViewport", true, false).size() == _scene_viewport_budget
		and main.get_node("CreationPanel").find_children("*", "SubViewport", true, false).size() == 1,
		phase + ": only the existing scene viewports and one creation preview, no card bake viewport")
	check(flow.picker.find_children("*", "SubViewport", true, false).is_empty()
		and flow.picker.find_children("*", "Node3D", true, false).is_empty(),
		phase + ": 25 cards contain no live 3D stage")

func run() -> void:
	root.size = Vector2i(1366, 768)
	var state := root.get_node("AppState")
	network = root.get_node("Network")
	var old_connection: String = state.get("connection_state")
	var old_protocol: int = network.call("appearance_protocol_version")
	# Local state only: no socket, authentication or character-create request.
	state.set("connection_state", "connected")
	network.call("_set_appearance_protocol", 3)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await settle()
	# No map is entered in this fixture; omit the unrelated arrival warm-up.
	main.set("map_registry", {})
	flow = main.get("creation_base_flow")
	var ready_deadline := Time.get_ticks_msec() + 15000
	while not is_instance_valid(flow) and Time.get_ticks_msec() < ready_deadline:
		await process_frame
		flow = main.get("creation_base_flow")
	check(is_instance_valid(flow), "Actual Main configures the starting-look controller")
	if not is_instance_valid(flow):
		main.queue_free()
		await settle()
		state.set("connection_state", old_connection)
		network.call("_set_appearance_protocol", old_protocol)
		quit(1)
		return
	_scene_viewport_budget = main.find_children("*", "SubViewport", true, false).size()
	print("Creation preview budget: existing scene viewports=%d; one active actor; no card viewports" % _scene_viewport_budget)
	main.call("_on_new_character_pressed")
	await settle()
	check(flow.is_open() and flow.picker.is_open(), "First creation entry opens the picker")
	check_preview_budget("first open")
	await capture("picker-first-open")
	check(not main.get_node("%FormPanel").visible and not main.get_node("%ClassRail").visible,
		"First entry chooses a look before exposing the editor")
	flow.picker._dismiss()
	await settle()
	check(main.get_node("%LoginPanel").visible and not main.get_node("%CreationPanel").visible,
		"Cancelling the initial picker returns to login")
	check(not flow.is_open() and not flow.picker.is_open(), "Initial cancellation closes the whole modal")
	(main.get_node("%CreateName") as LineEdit).text = "Flow Test Hero"
	(main.get_node("%CreatePassword") as LineEdit).text = "test-only-password"
	(main.get_node("%CreateConfirm") as LineEdit).text = "test-only-password"
	main.call("_set_creation_class", 2)
	main.call("_on_new_character_pressed")
	await settle()
	var row: Dictionary = flow._find("human_08")
	check(not row.is_empty(), "Qualified bearded base is available through the real controller")
	var before := form_state()
	await choose("human_08")
	check(not flow.is_open() and main.get_node("%FormPanel").visible,
		"Use this basis opens the full editor")
	check(int(main.get("_creation_preview_actor_type")) == 1
		and (main.get_node("%CreateGender") as OptionButton).get_selected_id() == 1,
		"Corin applies the male body to both form and actor")
	check(PC.normalized(appearance()) == PC.normalized(row.look.appearance),
		"Corin transfers its complete palette, grooming and morph controls")
	var applied := form_state()
	for field: String in ["calling", "name", "password", "confirm"]:
		check(applied[field] == before[field], "Applying a basis preserves " + field)
	var edited := appearance().duplicate(true)
	edited["nose_width"] = 33
	edited["shirt_hue"] = 120
	main.get("portrait_form").set_values(edited)
	main.get("creation_colours").set_values(edited)
	main.call("_refresh_creation_preview")
	main.set("preview_yaw", 0.72)
	main.set("preview_pitch", -0.11)
	main.set("preview_distance", 3.4)
	main.set("creation_face_focus", true)
	main.call("_frame_preview_actor")
	var saved := form_state()
	var camera := {"yaw": main.get("preview_yaw"), "pitch": main.get("preview_pitch"),
		"distance": main.get("preview_distance"), "face": main.get("creation_face_focus")}
	flow._button.pressed.emit()
	check(flow.is_open() and flow.picker.is_open(), "The editor's starting-look button reopens the library")
	flow.picker._select_card("human_01")
	await settle()
	check(form_state() == saved, "Browsing another look does not mutate the edited form")
	check_preview_budget("select")
	await capture("picker-selected-preview")
	check(int(main.get("_creation_preview_actor_type")) == 0,
		"Browsing updates the preview independently of the male form")
	flow.picker._dismiss()
	await settle()
	check(form_state() == saved, "Cancel restores the edited appearance, credentials and calling")
	check(int(main.get("_creation_preview_actor_type")) == int(saved.actor_type),
		"Cancel restores the preview body from the edited form")
	check(main.get("_creation_preview_appearance") == saved.appearance,
		"Cancel restores the preview palette and morphs")
	check(is_equal_approx(float(main.get("preview_yaw")), float(camera.yaw))
		and is_equal_approx(float(main.get("preview_pitch")), float(camera.pitch))
		and is_equal_approx(float(main.get("preview_distance")), float(camera.distance))
		and main.get("creation_face_focus") == camera.face, "Cancel restores the prior camera framing")
	# Static cards never add actors while scrolling/filtering. Same-body grooming
	# transitions still exercise the one active preview and preserve Cancel.
	flow.open(false)
	flow.picker.scroll.scroll_vertical = int(flow.picker.scroll.get_v_scroll_bar().max_value)
	await settle()
	check_preview_budget("scroll")
	await capture("picker-scrolled")
	flow.picker.search.text = "Bram"
	flow.picker._filter_rows()
	await settle()
	check_preview_budget("filter")
	await capture("picker-filtered")
	flow.picker._reset_filters()
	flow.picker._select_card("human_20")
	await settle()
	check(form_state() == saved, "A same-body hair-route preview keeps editor changes staged")
	flow.picker._dismiss()
	await settle()
	check(form_state() == saved and main.get("_creation_preview_appearance") == saved.appearance,
		"Cancelling the same-body hair-route preview restores the edited appearance")
	check_preview_budget("cancel and reopen")
	for actor_type: int in [41, 42]:
		flow.open(false)
		var id := ssarathi_id(actor_type)
		check(not id.is_empty(), "Ssarathi body %d is available" % actor_type)
		await choose(id)
		check((main.get_node("%CreateGender") as OptionButton).get_selected_id() == actor_type
			and (main.get_node("%CreateRace") as OptionButton).get_selected_metadata() == "ssarathi",
			"Ssarathi selection updates race and sex together")
		check(int(main.get("_creation_preview_actor_type")) == actor_type,
			"Ssarathi selection reaches the actual preview actor")
		var payload := appearance().duplicate(true)
		payload["actor_type"] = actor_type
		check(network.call("validate_creation_appearance", payload) == OK,
			"Ssarathi form is valid without leaked Human customization")
	for version: int in [1, 2, 3]:
		network.call("_set_appearance_protocol", version)
		flow.open(false)
		await choose("human_08")
		var payload := appearance().duplicate(true)
		payload["actor_type"] = 1
		check(network.call("validate_creation_appearance", payload) == OK,
			"Applied real form validates for negotiated protocol %d" % version)
		flow.open(false)
		await choose("human_34")
		var bram_payload := appearance().duplicate(true)
		bram_payload["actor_type"] = 1
		check(network.call("validate_creation_appearance", bram_payload) == OK,
			"Approved Bram applies through the real controller on PC/%d" % version)
	flow.open(false)
	flow.picker._select_card("human_08")
	network.call("_set_appearance_protocol", 2)
	await choose("human_08")
	var reconnect_payload := appearance().duplicate(true)
	reconnect_payload["actor_type"] = 1
	check(network.call("validate_creation_appearance", reconnect_payload) == OK,
		"A protocol downgrade while browsing is resolved again on Use")
	flow.open(false)
	main.get_node("%CreationPanel").hide()
	await settle()
	check(not flow.is_open() and not flow.picker.is_open(), "Hiding creation dismisses the popup")
	main.queue_free()
	await settle()
	state.set("connection_state", old_connection)
	network.call("_set_appearance_protocol", old_protocol)
	print("Creation base flow: %d checks, %d failures" % [checks, failures.size()])
	quit(0 if failures.is_empty() else 1)

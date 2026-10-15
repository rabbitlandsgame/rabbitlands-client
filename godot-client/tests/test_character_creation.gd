extends SceneTree
## Exercise the real selectors, rendered skin materials, and creation bytes.

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func choose(control: OptionButton, index: int) -> void:
	control.select(index)
	control.item_selected.emit(index)

func run() -> void:
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.get_node("%LoginPanel").hide()
	main.get_node("%CreationPanel").show()
	await process_frame
	var race := main.get_node("%CreateRace") as OptionButton
	var sex := main.get_node("%CreateGender") as OptionButton
	var skin := main.get_node("%CreateSkin") as OptionButton
	var hair := main.get_node("%CreateHair") as OptionButton
	var eyes := main.get_node("%CreateEyes") as OptionButton
	var hair_color := main.get_node("%CreateHairColor") as OptionButton
	var shirt := main.get_node("%CreateShirt") as OptionButton
	var pants := main.get_node("%CreatePants") as OptionButton
	var boots := main.get_node("%CreateBoots") as OptionButton
	expect(race.item_count == 8 and sex.item_count == 2, "eight races and two separate sex choices")
	expect(race.selected >= 0 and race.selected < race.item_count and
		sex.selected >= 0 and sex.selected < sex.item_count,
		"the initial complete-character roll selects a valid race and sex")
	for selector: OptionButton in [skin, hair, hair_color, eyes, shirt, pants, boots]:
		expect(selector.selected >= 0 and selector.selected < selector.item_count,
			"initial appearance randomization selects a valid option")
	var class_buttons: Array[Button] = [main.get_node("%ClassChoice0"),
		main.get_node("%ClassChoice1"), main.get_node("%ClassChoice2"),
		main.get_node("%ClassChoice3")]
	expect(class_buttons.size() == 4 and (main.get_node("%ClassTitle") as Label).text ==
		"Vanguard", "four illustrated classes default to Vanguard")
	expect(main.get("preview_actor") is ReplicatedActor3D,
		"the one-time initial appearance roll builds the preview")
	var vanguard_loadout: Dictionary = main.call("_creation_class_loadout")
	expect(vanguard_loadout == {0: 114, 1: 106, 2: 105, 3: 134, 4: 220, 5: 209, 6: 249},
		"Vanguard previews the whole militia set: helm, jack, kneecops, warboots, sword and shield")
	expect(CreationArchetypes.loadout_at(1) ==
		{0: 164, 3: 159, 4: 230, 5: 225, 6: 226},
		"Ranger previews hood, vest, breeches and fieldboots with the longbow")
	expect(CreationArchetypes.loadout_at(2) ==
		{0: 142, 3: 115, 4: 185, 5: 222, 6: 198} and
		str(CreationArchetypes.at(2).get("starting_items", "")).contains("Acolyte"),
		"Arcanist previews the whole Acolyte set and names it")
	expect(CreationArchetypes.loadout_at(3) ==
		{0: 163, 2: 100, 3: 122, 4: 176, 5: 189, 6: 205},
		"Warden previews the Antler Hood and the Furtrim set with the quarterstaff")
	for index in CreationArchetypes.count():
		var parts: Dictionary = CreationArchetypes.loadout_at(index)
		expect(parts.has(0) and parts.has(3) and parts.has(4) and parts.has(5) and parts.has(6),
			"every calling previews a weapon and a head, body, legs and feet piece")
	var original_class := int(main.get("selected_creation_class"))
	main.get_node("%CreateName").text = "Seeded Hero"
	main.get_node("%CreatePassword").text = "secret"
	main.get_node("%CreateConfirm").text = "secret"
	var preview_root := main.get_node("%PreviewRoot") as Node3D
	var preview_children_before := preview_root.get_child_count()
	var form_panel := main.get_node("%FormPanel") as PanelContainer
	var form_rect_before := form_panel.get_global_rect()
	var selector_sizes_before: Array[Vector2] = []
	for selector: OptionButton in [race, sex, skin, hair, hair_color, eyes, shirt, pants, boots]:
		selector_sizes_before.append(selector.size)
	var first_rng := RandomNumberGenerator.new()
	first_rng.seed = 1729
	var expected_rng := RandomNumberGenerator.new()
	expected_rng.seed = 1729
	var expected_race_index := expected_rng.randi_range(0, race.item_count - 1)
	var expected_sex_index := expected_rng.randi_range(0, sex.item_count - 1)
	main.call("_randomize_creation_appearance", first_rng)
	var seeded_appearance: Dictionary = main.call("_creation_appearance")
	var seeded_race := race.selected
	var seeded_sex := sex.selected
	expect(preview_root.get_child_count() == preview_children_before + 1,
		"one randomized roll rebuilds the preview exactly once")
	expect(seeded_race == expected_race_index and seeded_sex == expected_sex_index,
		"appearance randomization includes the seeded race and sex rolls")
	for frame in range(2):
		await process_frame
	var form_rect_after := form_panel.get_global_rect()
	expect(form_rect_after.position.is_equal_approx(form_rect_before.position) and
		form_rect_after.size.is_equal_approx(form_rect_before.size),
		"randomized option text does not move or resize the creation form")
	var selectors: Array[OptionButton] = [race, sex, skin, hair, hair_color, eyes, shirt, pants, boots]
	for index: int in range(selectors.size()):
		expect(selectors[index].size.is_equal_approx(selector_sizes_before[index]),
			"randomized option text keeps selector %d at a fixed width" % index)
	var second_rng := RandomNumberGenerator.new()
	second_rng.seed = 1729
	main.call("_randomize_creation_appearance", second_rng)
	expect(main.call("_creation_appearance") == seeded_appearance and
		race.selected == seeded_race and sex.selected == seeded_sex,
		"the same seed produces the same complete race, sex and appearance")
	var button_rng := main.get("_creation_appearance_rng") as RandomNumberGenerator
	button_rng.seed = 1729
	(main.get_node("%RandomizeAppearance") as Button).pressed.emit()
	expect(main.call("_creation_appearance") == seeded_appearance,
		"the Randomize appearance button uses the testable RNG seam")
	expect(race.selected == seeded_race and sex.selected == seeded_sex and
		int(main.get("selected_creation_class")) == original_class,
		"appearance randomization changes identity independently of class")
	expect(main.get_node("%CreateName").text == "Seeded Hero" and
		main.get_node("%CreatePassword").text == "secret" and
		main.get_node("%CreateConfirm").text == "secret",
		"appearance randomization preserves name and credentials")
	var app_state := root.get_node("AppState")
	var connection_before := str(app_state.get("connection_state"))
	app_state.set("connection_state", "connected")
	main.call("_on_creation_back_pressed")
	main.call("_on_new_character_pressed")
	expect(main.call("_creation_appearance") == seeded_appearance,
		"reopening creation preserves the rolled appearance")
	app_state.set("connection_state", connection_before)
	main.call("_set_creation_class", -1)
	expect(int(main.get("selected_creation_class")) == 3 and
		(main.get_node("%ClassTitle") as Label).text == "Warden",
		"class carousel wraps backwards")
	main.call("_on_creation_class_rotated", 1)
	expect(int(main.get("selected_creation_class")) == 0,
		"class carousel wraps forwards")
	main.call("_set_creation_class", 1)
	var ranger_actor := main.get("preview_actor") as ReplicatedActor3D
	var ranger_bow := ranger_actor.combat_presentation.bow
	expect(ranger_bow != null and ranger_bow.visible,
		"Ranger selection shows its equipped bow")
	main.call("_set_creation_class", 2)
	var class_loadout: Dictionary = main.call("_creation_class_loadout")
	var class_actor := main.get("preview_actor") as ReplicatedActor3D
	expect((class_actor.equipment_diagnostics().visuals as Dictionary) == class_loadout,
		"selecting Arcanist updates the live equipment preview")
	expect(ranger_bow != null and not ranger_bow.visible and
		int((class_actor.equipment_diagnostics().visuals as Dictionary).get(0, -1)) == 142,
		"leaving Ranger removes its bow before showing the next class weapon")
	for non_ranger_class: int in [0, 3]:
		main.call("_set_creation_class", non_ranger_class)
		class_actor = main.get("preview_actor") as ReplicatedActor3D
		expect(ranger_bow != null and not ranger_bow.visible,
			"Ranger bow stays hidden for class %d" % non_ranger_class)
	main.call("_set_creation_class", 2)
	class_loadout = main.call("_creation_class_loadout")
	class_actor = main.get("preview_actor") as ReplicatedActor3D
	(main.get_node("%ShowClassGear") as CheckBox).set_pressed_no_signal(false)
	main.call("_on_creation_class_gear_toggled", false)
	expect((class_actor.equipment_diagnostics().visuals as Dictionary).is_empty(),
		"class gear can be hidden while editing the base wardrobe")
	(main.get_node("%ShowClassGear") as CheckBox).set_pressed_no_signal(true)
	main.call("_on_creation_class_gear_toggled", true)
	expect((class_actor.equipment_diagnostics().visuals as Dictionary) == class_loadout,
		"class gear toggle restores the selected loadout")
	var human_index := -1
	for race_index in range(race.item_count):
		if race.get_item_text(race_index) == "Human":
			human_index = race_index
			break
	expect(human_index >= 0, "Human remains available after randomized initialization")
	var models: Dictionary = main.get("models")
	var options: Array = main.get("creation_options")
	var actor_types: Dictionary = {}
	var previous_sex := str(sex.get_selected_metadata())
	for race_index in range(race.item_count):
		var eyes_before := eyes.get_selected_id()
		choose(race, race_index)
		var culture := str(race.get_selected_metadata())
		if culture in ["orun", "mycelari"]:
			expect(eyes.get_selected_id() == 3, "a new %s opens on Amber gold eyes" % culture)
		else:
			expect(eyes.get_selected_id() == eyes_before,
				"changing race to %s keeps the chosen eyes" % culture)
		expect(int(main.get("selected_creation_class")) == 2 and
			((main.get("preview_actor") as ReplicatedActor3D).equipment_diagnostics().visuals
			as Dictionary) == class_loadout,
			"class selection and starting-kit preview survive race switch: " + culture)
		expect(str(sex.get_selected_metadata()) == previous_sex, "changing race preserves sex: " + culture)
		var expected_skin := 1 if culture == "luminous" else 0
		expect(skin.get_selected_id() == expected_skin, "race switch selects its default skin: " + culture)
		for sex_index in range(sex.item_count):
			choose(sex, sex_index)
			var actor_type := sex.get_selected_id()
			actor_types[actor_type] = true
			var matches := options.filter(func(option: Dictionary) -> bool: return int(option.actorType) == actor_type)
			expect(matches.size() == 1, "selected actor type exists exactly once")
			var model: Dictionary = models[matches[0].model]
			expect(model.culture == culture and model.gender == sex.get_selected_metadata(), "race and sex resolve the matching model")
			var actor := main.get("preview_actor") as ReplicatedActor3D
			expect(actor.get("_model_config") == model, "preview uses the selected race and sex")
			expect(skin.get_selected_id() == expected_skin, "sex change preserves race default")
			var look: Dictionary = main.call("_creation_appearance")
			look["actor_type"] = actor_type
			var packet := EloriaProtocol.create_character("Preview", "secret", look)
			var tail := packet.slice(packet.size() - 9)
			expect(tail[0] == expected_skin and tail[5] == actor_type, "creation bytes preserve race, sex and default skin")
			var class_packet := EloriaProtocol.create_character(
				"Preview", "secret", look, int(main.get("selected_creation_class")))
			var class_tail := class_packet.slice(class_packet.size() - 9)
			expect(class_tail.slice(0, 8) == tail.slice(0, 8) and class_tail[8] == 2,
				"class is an independent ninth byte and never replaces race appearance")
			var materials: Dictionary = actor.get("_skin_materials")
			expect(not materials.is_empty(), "preview has real skin materials")
			for material: ShaderMaterial in materials.values():
				expect(bool(material.get_shader_parameter("recolor_skin")) == (expected_skin != 0), "race default keeps the authored texture")
			if sex_index == 1:
				await capture(culture)
		# Customize the skin, then change sex in both directions.
		choose(skin, skin.get_item_index(6))
		hair.select(hair.get_item_index(4))
		eyes.select(eyes.get_item_index(4))
		var customized: Dictionary = main.call("_creation_appearance")
		for sex_index in [0, 1]:
			choose(sex, sex_index)
			expect(main.call("_creation_appearance") == customized, "sex changes preserve all customized appearance values")
		# Leave Race default selected so returning to Human must choose a valid tone.
		if culture != "luminous":
			choose(skin, skin.get_item_index(0))
		previous_sex = str(sex.get_selected_metadata())
	expect(actor_types.keys().size() == 16, "all sixteen existing actor types remain selectable")
	# A customized skin must also reset on a non-human to non-human switch.
	choose(skin, skin.get_item_index(8))
	choose(race, 0)
	expect(skin.get_selected_id() == 0, "changing non-human race resets a custom skin")
	choose(race, human_index)
	expect(skin.get_selected_id() == 1 and skin.get_item_index(0) == -1, "returning to Human selects a valid human tone")
	for window_size: Vector2i in [Vector2i(1280, 720), Vector2i(1920, 1080)]:
		root.size = window_size
		for frame in range(3):
			await process_frame
		var race_rect := race.get_global_rect()
		var sex_rect := sex.get_global_rect()
		expect(is_equal_approx(race_rect.position.y, sex_rect.position.y) and race_rect.end.x <= sex_rect.position.x, "race and sex boxes sit side by side")
		expect(main.get_global_rect().encloses(race_rect) and main.get_global_rect().encloses(sex_rect), "both selectors fit the window")
	# Orun and Mycelari are amber-eyed: a roll for either keeps to the two
	# ambers, every other race rolls the whole palette.
	var amber_rolls := 0
	var other_rolls := 0
	var other_eyes: Dictionary = {}
	var ambers_seen: Dictionary = {}
	for seed_value in range(60):
		var amber_rng := RandomNumberGenerator.new()
		amber_rng.seed = 4000 + seed_value
		main.call("_randomize_creation_appearance", amber_rng)
		var rolled_culture := AppearanceVariants.culture_for_actor_type(sex.get_selected_id())
		if rolled_culture in ["orun", "mycelari"]:
			amber_rolls += 1
			ambers_seen[eyes.get_selected_id()] = true
			expect(eyes.get_selected_id() in [3, 9],
				"a rolled %s has amber eyes, got %d" % [rolled_culture, eyes.get_selected_id()])
		else:
			other_rolls += 1
			other_eyes[eyes.get_selected_id()] = true
	expect(amber_rolls > 0 and ambers_seen.size() == 2,
		"rolls reach Orun or Mycelari and both ambers (%d rolls)" % amber_rolls)
	expect(other_rolls > 0 and other_eyes.size() > 2,
		"other races still roll the whole eye palette")
	main.call("_set_creation_class", 0)
	await capture("character-creation-ui")
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	# Release the local material references before the renderer shuts down.
	call_deferred("finish")

func finish() -> void:
	print("CHARACTER_CREATION: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func capture(filename: String) -> void:
	var directory := OS.get_environment("ELORIA_CREATION_CAPTURE_DIR")
	if directory.is_empty() or DisplayServer.get_name() == "headless":
		return
	DirAccess.make_dir_recursive_absolute(directory)
	for frame in range(4):
		await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(directory.path_join(filename + ".png")) == OK, "saved creation preview " + filename)

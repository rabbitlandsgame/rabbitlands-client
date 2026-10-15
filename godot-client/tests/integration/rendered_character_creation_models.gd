extends SceneTree

const SCREEN_SIZE := Vector2i(1280, 720)
var _artifact_directory := ""
var _failures := 0
var _results: Array[Dictionary] = []
var _structure_only := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_structure_only = OS.get_environment("ELORIA_STRUCTURE_ONLY") == "1"
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path(
			"res://test-artifacts/character-models")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"character-model artifact directory is writable")
	root.size = SCREEN_SIZE
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "character creation scene loads")
	if scene_resource is not PackedScene:
		_finish()
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	for unused_frame: int in range(4):
		await process_frame
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).hide()
	(main.get_node("CreationPanel") as Control).show()
	(main.get_node("%ShowClassGear") as CheckBox).set_pressed_no_signal(false)
	main.call("_on_creation_class_gear_toggled", false)
	# Capture a close three-quarter view so face, hair, clothing fit, and
	# culture features are large enough for the CI artifact to review.
	main.set("preview_yaw", PI + 0.28)
	main.set("preview_pitch", 0.08)
	main.set("preview_distance", 2.4)
	main.call("_update_preview_camera")

	var selector: OptionButton = main.get_node("%CreateGender") as OptionButton
	var preview: SubViewport = main.get_node(
		"CreationPanel/Columns/CharacterPreview/Viewport") as SubViewport
	var spin_names: Array[String] = ["CreateSkin", "CreateEyes",
		"CreateShirt", "CreatePants", "CreateBoots"]
	var hair := main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/CreateHair") as OptionButton
	var hair_color := main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/CreateHairColor") as OptionButton
	_expect(hair.item_count == 10 and hair_color.item_count == 20, "independent named hairstyle and color choices")
	_expect(main.get_node_or_null("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/CreateHead") == null, "broken head control removed")
	hair.select(0)
	hair_color.select(0)
	# The shared bodies expose native wardrobe dye surfaces. Exercise their
	# existing controls alongside the hair choices, including the bald default.
	for garment: String in ["CreateShirt", "CreatePants", "CreateBoots"]:
		_expect(main.get_node_or_null(
			"CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + garment) is OptionButton,
			"creation offers native wardrobe dye " + garment)
	for spin_name: String in spin_names:
		(main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + spin_name) as OptionButton).select((main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + spin_name) as OptionButton).get_item_index(1 if spin_name == "CreateSkin" else 0))

	var creation_options: Array = main.get("creation_options")
	for index: int in range(creation_options.size()):
		var option: Dictionary = creation_options[index]
		_select_actor_type(main, int(option.actorType))
		for choice_name: String in spin_names + ["CreateHair", "CreateHairColor"]:
			var choice := main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + choice_name) as OptionButton
			var seen: Dictionary = {}
			for item: int in range(choice.item_count):
				var label_text := choice.get_item_text(item)
				_expect(not seen.has(label_text) and not label_text.is_valid_int(), "customization choices have unique descriptive names")
				seen[label_text] = true
		main.call("_refresh_creation_preview")
		for unused_frame: int in range(10):
			await process_frame
		var label: String = option.label
		var slug: String = label.to_lower().replace(" ", "-")
		await _capture_preview(preview, "default-%02d-%s.png" % [index, slug])
		_validate_actor(main.get("preview_actor") as ReplicatedActor3D, label)

	# Exercise all four runtime appearance families through the same creation
	# controls: skin, eyes, native hair, and wardrobe palettes.
	_select_actor_type(main, 0)
	for style: int in range(AppearanceVariants.HAIR_STYLE_COUNT):
		hair.select(hair.get_item_index(style))
		hair_color.select(hair_color.get_item_index(style))
		for spin_name: String in spin_names:
			(main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + spin_name) as OptionButton).select(mini(style, (main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + spin_name) as OptionButton).item_count - 1))
		main.call("_refresh_creation_preview")
		for unused_frame: int in range(10):
			await process_frame
		await _capture_preview(preview, "appearance-variant-%d.png" % style)
		_validate_actor(main.get("preview_actor") as ReplicatedActor3D,
			"appearance variant %d" % style, style)

	# Changing colour must leave the selected mesh alone, and changing style
	# must keep its colour. Exercise the real controls/materials and wire value.
	for spin_name: String in spin_names:
		(main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + spin_name) as OptionButton).select((main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid/" + spin_name) as OptionButton).get_item_index(1 if spin_name == "CreateSkin" else 0))
	for model_index: int in [0, 1]:
		selector.select(selector.get_item_index(model_index))
		main.call("_populate_creation_choices")
		for style: int in range(AppearanceVariants.HAIR_STYLE_COUNT):
			var chosen_meshes: Array[Mesh] = []
			for color: int in range(20):
				hair.select(hair.get_item_index(style))
				hair_color.select(hair_color.get_item_index(color))
				if color == 0:
					hair.item_selected.emit(style)
				else:
					hair_color.item_selected.emit(color)
				await process_frame
				var look: Dictionary = main.call("_creation_appearance")
				var packet := EloriaProtocol.create_character("Test", "secret", look)
				var expected := AppearanceVariants.pack_hair(style, color)
				_expect(AppearanceVariants.hair_from_wire(packet[16], packet[21]) == expected,
					"creation saves every independent hair choice")
				var actor := main.get("preview_actor") as ReplicatedActor3D
				var meshes: Array[Mesh] = []
				for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
					var mesh := node as MeshInstance3D
					if str(mesh.name).begins_with("wardrobe_head_"):
						_expect(not mesh.visible, "retired headwear remains hidden")
					if not str(mesh.name).begins_with("NativeHair_"):
						continue
					meshes.append(mesh.mesh)
					for surface: int in range(mesh.mesh.get_surface_count()):
						var original := mesh.mesh.surface_get_material(surface) as StandardMaterial3D
						var tinted := mesh.get_active_material(surface) as StandardMaterial3D
						_expect(tinted != null and tinted.albedo_color.is_equal_approx(
							original.albedo_color * AppearanceVariants.hair_color(color)),
							"selected colour reaches the rendered hair material")
				if color == 0:
					chosen_meshes = meshes
				_expect(meshes == chosen_meshes and meshes.is_empty() == (style == 0),
					"colour selection preserves the chosen hairstyle geometry")
				if style == 1 and color in [2, 3, 4, 6]:
					await _capture_preview(preview, "hair-%d-color-%02d.png" % [model_index, color])
	# Leave the full UI proof showing a readily visible hairstyle and colour.
	selector.select(selector.get_item_index(1))
	main.call("_populate_creation_choices")
	hair.select(hair.get_item_index(1))
	hair_color.select(hair_color.get_item_index(3))
	main.call("_refresh_creation_preview")
	(main.get_node("%ShowClassGear") as CheckBox).set_pressed_no_signal(true)
	main.call("_on_creation_class_gear_toggled", true)
	for unused_frame: int in range(4):
		await process_frame

	if not _structure_only:
		RenderingServer.force_draw(false)
		var full_texture: ViewportTexture = root.get_texture()
		if full_texture == null:
			_expect(false, "full character creation UI texture is available")
			_finish()
			return
		var full_image: Image = full_texture.get_image()
		_expect(not full_image.is_empty() and full_image.get_size() == SCREEN_SIZE,
			"full character creation UI renders at reference dimensions")
		_expect(full_image.save_png(_artifact_directory.path_join(
			"character-creation-ui.png")) == OK, "saved character creation UI")
	var report := FileAccess.open(_artifact_directory.path_join("validation.json"),
		FileAccess.WRITE)
	_expect(report != null, "character-model validation report is writable")
	if report != null:
		report.store_string(JSON.stringify({"models": _results,
			"failures": _failures}, "  ") + "\n")
	_finish()

func _capture_preview(viewport: SubViewport, file_name: String) -> void:
	for unused_frame: int in range(3):
		await process_frame
	if _structure_only:
		return
	RenderingServer.force_draw(false)
	var texture: ViewportTexture = viewport.get_texture()
	if texture == null:
		_expect(false, "rendered preview texture is available")
		return
	var image: Image = texture.get_image()
	if image == null:
		_expect(false, "rendered preview image is available")
		return
	_expect(not image.is_empty() and image.get_size() == viewport.size and
		image.get_width() >= 420 and image.get_height() >= 620,
		"rendered preview fills the responsive centre stage")
	var sampled_colors: Dictionary = {}
	for y: int in range(0, image.get_height(), 16):
		for x: int in range(0, image.get_width(), 16):
			sampled_colors[image.get_pixel(x, y).to_html()] = true
	_expect(sampled_colors.size() >= 32, "rendered preview contains model detail")
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"saved " + file_name)

func _validate_actor(actor: ReplicatedActor3D, label: String, hair_style := 0) -> void:
	_expect(actor != null, label + " preview actor exists")
	if actor == null:
		return
	var equipment: Dictionary = actor.equipment_diagnostics()
	# Modified 2026-08-28 for Eloria Client: shirt, pants, and boots now use the
	# same skinned equipment path as the world actor. The creation preview should
	# contain those garments, but no socketed prop or fallback placeholder.
	# Modified 2026-09-01 for Eloria Client: an empty wardrobe slot renders
	# bare now -- the race bodies carry their clothing in their own texture --
	# so a preview with nothing equipped has no garments at all.  What must
	# still hold is that nothing was socketed that should have been skinned,
	# and nothing fell back to a placeholder.
	_expect(int(equipment.get("socket", -1)) == 0 and
		int(equipment.get("fallback", -1)) == 0,
		label + " creation preview has no props or fallback placeholders")
	var mesh_names: Array[String] = []
	var maximum_extent := 0.0
	var body_meshes := 0
	# The nameplate, ring and map dot are drawn by the actor, not by the
	# model, and the map dot alone is 15 units across -- measuring them here
	# failed the placeholder check on every body, shipped ones included.
	var furniture: Array[String] = ["SelectionRing", "HealthBarBackground",
		"HealthBarFill", "OverheadBackground", "MapDot", "MapDotOutline"]
	for node_value: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh_node: MeshInstance3D = node_value as MeshInstance3D
		mesh_names.append(mesh_node.name)
		if furniture.has(mesh_node.name):
			continue
		var hair: bool = mesh_node.name.begins_with("NativeHair_")
		var garment: bool = mesh_node.name.begins_with("EquipmentSkin_")
		if not hair and not garment:
			body_meshes += 1
		var size: Vector3 = mesh_node.get_aabb().size
		maximum_extent = maxf(maximum_extent, maxf(size.x, maxf(size.y, size.z)))
	# Modified 2026-09-01 for Eloria Client: a race used to be a nude Body
	# under separate Wardrobe_Shirt/Pants/Boots meshes.  The bodies are now
	# one skinned mesh wearing its clothing in its own texture, so the check
	# is that a body rendered at all, not that it rendered in four pieces.
	_expect(body_meshes >= 1, label + " renders a skinned body")
	_expect(mesh_names.any(func(name: String) -> bool:
		return name.begins_with("NativeHair_")) == (hair_style != 0),
		label + " renders the chosen hair or bald style")
	_expect(maximum_extent < 2.1,
		label + " contains no oversized placeholder geometry")
	_results.append({"label": label, "meshes": mesh_names,
		"maximum_extent": maximum_extent, "equipment": equipment})

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _select_actor_type(main: Control, actor_type: int) -> void:
	var race := main.get_node("%CreateRace") as OptionButton
	var sex := main.get_node("%CreateGender") as OptionButton
	var culture := AppearanceVariants.culture_for_actor_type(actor_type)
	for index in range(race.item_count):
		if str(race.get_item_metadata(index)) == culture:
			race.select(index)
			break
	main.call("_populate_creation_sexes")
	sex.select(sex.get_item_index(actor_type))
	main.call("_populate_creation_choices", true)

func _finish() -> void:
	print("rendered character creation models: ",
		"PASS" if _failures == 0 else "FAIL")
	quit(_failures)

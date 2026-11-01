extends SceneTree
## Remaining-Human catalog qualification. Run in the candidate client project.
## Optional: --catalog-path=<JSON> --pilot-baseline=<JSON> --check-editor-flow
## The optional flow uses real Main controls; it never connects or creates an account.

const LIBRARY := preload("res://src/ui/creation_base_library.gd")
const PC := preload("res://src/actors/portrait_customization.gd")
const MAP := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
const MODULES := preload("res://src/actors/rl_head/rl_head_hair_modules.gd")
const VARIANTS := preload("res://src/actors/appearance_variants.gd")
const PILOTS := ["human_01", "human_08", "human_14", "human_20", "human_27", "human_34"]
const FEMALE_IDS := [1, 3, 5, 7, 9, 11, 14, 15, 17, 19, 21, 23, 25, 27, 29, 32, 33, 35]
var checks := 0
var failures: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)


func argument(prefix: String, fallback: String = "") -> String:
	for value: String in OS.get_cmdline_user_args():
		if value.begins_with(prefix + "="):
			return value.trim_prefix(prefix + "=")
	return fallback


func read_dictionary(path: String) -> Dictionary:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	check(value is Dictionary, "Readable JSON object: " + path)
	return value if value is Dictionary else {}


func _run() -> void:
	var registry := read_dictionary("res://data/actors/models.json")
	var catalog := read_dictionary(argument("--catalog-path", LIBRARY.ARCHETYPES_PATH))
	var before := registry.duplicate(true)
	var entries := LIBRARY.rows(registry, 4)
	check(PC.LATEST == 4, "This qualification includes the current PC/4 age controls")
	check(entries.size() == 41, "All 36 matrix Humans plus five existing studies/native choices")
	var raw_ids := {}
	for item: Dictionary in catalog.get("archetypes", []):
		var id := str(item.get("id", ""))
		check(not raw_ids.has(id), "No duplicate source ID: " + id)
		raw_ids[id] = item
	check(raw_ids.size() == 36, "Exactly 36 matrix source records")
	var names := {}
	var sexes := {"female": 0, "male": 0}
	for row: Dictionary in entries:
		var id := str(row.id)
		check(row.race_id == "luminous" and int(row.look.actor_type) in [0, 1], id + " is Human-only")
		check(not str(row.label).is_empty() and not names.has(row.label), "Unique nonempty name: " + str(row.label))
		names[row.label] = true
		check(row.label == LIBRARY.HUMAN_NAMES.get(id, ""), id + " retains its registered display name")
		check(row.sex == ("female" if int(row.look.actor_type) == 0 else "male"), id + " uses the correct body sex")
		check(row.look.keys().size() == 3 and row.look.equipment_visuals.is_empty(), id + " stores cosmetics without account or equipment data")
	for number: int in range(1, 37):
		var id := "human_%02d" % number
		check(raw_ids.has(id), "Complete matrix source: " + id)
		var row := LIBRARY.find(entries, id)
		check(not row.is_empty(), "Complete selectable matrix: " + id)
		if row.is_empty() or not raw_ids.has(id):
			continue
		var sex := "female" if number in FEMALE_IDS else "male"
		sexes[sex] += 1
		check(row.sex == sex and raw_ids[id].sex == sex and raw_ids[id].body_template == "luminous_" + sex,
			id + " preserves the concept's sex and source body binding")
		if id not in PILOTS:
			var source: Variant = raw_ids[id].get("appearance_pc4")
			check(source is Dictionary and not source.is_empty(), id + " has an explicit PC/4 source")
			if source is Dictionary:
				for field: String in PC.V4_FIELDS:
					check(source.has(field), id + " explicitly records " + field)
			_check_editable(row)
	check(sexes.female == 18 and sexes.male == 18, "All 36 retain the balanced source roster")
	_check_protocols(registry, raw_ids)
	_check_pilots(raw_ids)
	check(registry == before, "Building catalogs does not mutate the NPC/body registry")
	check((registry.get("creationOptions", []) as Array).size() == 16, "All source NPC race/sex bodies remain in the registry")
	if "--check-editor-flow" in OS.get_cmdline_user_args() and entries.size() == 41:
		await _check_editor_flow(entries)
	print("Remaining Human bases: %d checks, %d failures" % [checks, failures.size()])
	quit(0 if failures.is_empty() else 1)


func _check_protocols(registry: Dictionary, sources: Dictionary) -> void:
	for version: int in [2, 3, 4]:
		var entries := LIBRARY.rows(registry, version)
		check(entries.size() == 41, "All starting looks survive PC/%d negotiation" % version)
		for row: Dictionary in entries:
			var app: Dictionary = row.look.appearance
			check(PC.validate(app, version).get("ok", false), "%s validates on PC/%d" % [row.id, version])
			check(PC.decode(PC.encode(app, version), 0) == PC.normalized(app), "%s exactly round-trips its PC/%d cosmetics" % [row.id, version])
			for field: String in app:
				check(field in LIBRARY.LEGACY_FIELDS or field in PC.FIELDS, "%s contains only public cosmetic fields: %s" % [row.id, field])
			for field: String in PC.FIELDS:
				if PC.field_version(field) > version:
					check(int(app.get(field, PC.DEFAULTS[field])) == int(PC.DEFAULTS[field]),
						"%s PC/%d neutralizes unsupported %s" % [row.id, version, field])
			if sources.has(row.id):
				var selected := LIBRARY._archetype_appearance(sources[row.id], version)
				for field: String in PC.fields_for(version):
					check(int(app[field]) == int(PC.normalized(selected)[field]),
						"%s PC/%d preserves its saved %s" % [row.id, version, field])
			var hair := int(app.hair)
			check(VARIANTS.hair_from_wire(hair & 255, VARIANTS.hair_wire_head(hair, int(app.head))) == hair,
				"%s PC/%d preserves its packed hair family and color" % [row.id, version])


func _check_editable(row: Dictionary) -> void:
	var app: Dictionary = row.look.appearance
	var sex := str(row.sex)
	var hair := MAP.hair(app, sex)
	check(not hair.begins_with("legacy:"), row.id + " resolves to a current hairstyle")
	if VARIANTS.hair_style(int(app.hair)) == 0:
		check(hair == "none", row.id + " preserves a deliberately bald concept")
	else:
		var module := MODULES.resolve(int(app.hair_module), sex)
		check(not module.is_empty() and str(module.get("name", "")) == hair, row.id + " explicitly selects its correct sex-specific module")
		for pair: Array in [["hair_length", "length"], ["hair_volume", "volume"], ["hair_finish", "detail"]]:
			var low := app.duplicate(true)
			var high := app.duplicate(true)
			low[pair[0]] = 1 if pair[0] == "hair_finish" else 0
			high[pair[0]] = 101 if pair[0] == "hair_finish" else 100
			if pair[0] == "hair_finish":
				low.merge(HairFinish.canonical(0), true)
				high.merge(HairFinish.canonical(100), true)
			var low_shapes := MAP.hair_shapes(low, hair)
			var high_shapes := MAP.hair_shapes(high, hair)
			check(float(high_shapes[pair[1]]) > float(low_shapes[pair[1]]) + 0.1,
				row.id + " has a meaningful mapped " + str(pair[0]) + " range")
			check(MAP.hair(low, sex) == hair and MAP.hair(high, sex) == hair,
				row.id + " keeps its selected style while adjusting " + str(pair[0]))
	var age := app.duplicate(true)
	age.skin_age = 73
	age.hair_grey = 0
	var aged := MAP.face(age, sex)
	check(is_equal_approx(aged.skin_age, .73) and is_zero_approx(aged.hair_grey), row.id + " adjusts skin age independently of greying")
	age.skin_age = 0
	age.hair_grey = 42
	var grey := MAP.face(age, sex)
	check(is_zero_approx(grey.skin_age) and is_equal_approx(grey.hair_grey, .42), row.id + " adjusts greying independently of skin age")
	check(aged.controls == grey.controls and aged.hair == grey.hair and aged.hair_length == grey.hair_length
		and aged.hair_volume == grey.hair_volume and aged.hair_detail == grey.hair_detail,
		row.id + " age edits preserve identity and grooming")


func _check_pilots(sources: Dictionary) -> void:
	var path := argument("--pilot-baseline")
	if path.is_empty():
		return
	var baseline := read_dictionary(path)
	for id: String in PILOTS:
		check(baseline.has(id) and sources.has(id) and baseline[id] == sources[id],
			id + " remains byte-value equivalent to its pre-task source record")


func _settle() -> void:
	for frame: int in 3:
		await process_frame


func _editor_appearance(main: Control) -> Dictionary:
	return main.call("_creation_appearance").duplicate(true)


func _check_editor_flow(entries: Array[Dictionary]) -> void:
	var state := root.get_node("AppState")
	var network := root.get_node("Network")
	var old_connection: String = state.get("connection_state")
	var old_protocol: int = network.call("appearance_protocol_version")
	state.set("connection_state", "connected")
	network.call("_set_appearance_protocol", 4)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await _settle()
	main.set("map_registry", {})
	var flow: Variant = main.get("creation_base_flow")
	var deadline := Time.get_ticks_msec() + 15000
	while not is_instance_valid(flow) and Time.get_ticks_msec() < deadline:
		await process_frame
		flow = main.get("creation_base_flow")
	check(is_instance_valid(flow), "Real character editor provides its starting-look flow")
	if is_instance_valid(flow):
		main.call("_on_new_character_pressed")
		await _settle()
		for row: Dictionary in entries:
			if not str(row.id).begins_with("human_") or str(row.id) in PILOTS:
				continue
			if not flow.is_open():
				flow.open(false)
			flow.picker._select_card(row.id)
			flow.picker._use_basis()
			await _settle()
			check(PC.normalized(_editor_appearance(main)) == PC.normalized(row.look.appearance), row.id + " applies its exact complete saved look")
			for field: String in LIBRARY.LEGACY_FIELDS:
				check(int(_editor_appearance(main).get(field, 0)) == int(row.look.appearance.get(field, 0)), row.id + " applies its saved " + field)
			check(int(main.get("_creation_preview_actor_type")) == int(row.look.actor_type), row.id + " applies its saved preview body")
			var edited := _editor_appearance(main)
			edited.nose_width = 33
			edited.skin_age = 67
			edited.hair_grey = 31
			main.get("portrait_form").set_values(edited)
			main.get("creation_colours").set_values(edited)
			main.call("_refresh_creation_preview")
			var before := _editor_appearance(main)
			flow.open(false)
			flow.picker._select_card("human_01" if row.sex == "male" else "human_08")
			await _settle()
			check(_editor_appearance(main) == before, row.id + " remains unchanged while browsing another basis")
			flow.picker._dismiss()
			await _settle()
			check(_editor_appearance(main) == before and main.get("_creation_preview_appearance") == before,
				row.id + " cancels back to its edited face, age and grooming")
			check(flow.picker.find_children("*", "SubViewport", true, false).is_empty()
				and flow.picker.find_children("*", "Node3D", true, false).is_empty(), row.id + " uses static cards while only the active look is rendered")
			var live := 0
			for node: Node in main.find_children("*", "Node", true, false):
				if node is ReplicatedActor3D and not node.is_queued_for_deletion():
					live += 1
			check(live == 1, row.id + " keeps exactly one active creation actor")
	main.queue_free()
	await _settle()
	state.set("connection_state", old_connection)
	network.call("_set_appearance_protocol", old_protocol)

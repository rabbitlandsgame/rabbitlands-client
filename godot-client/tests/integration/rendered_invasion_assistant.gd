extends SceneTree
## Rendered evidence that the halved invasion assistant still shows its work.
##
## The window used to open at 1120x720 over a 1280x720 client, which left an
## invasion master staging a wave they could not watch. It opens at 784x504
## now, so the question this fixture exists to answer is whether the three
## tabs still read at that size: the map list beside the tactical canvas and
## its roster, the group builder with its composition list, and the monster
## catalog beside a full stat block. Every payload below travels through the
## real command 233 decoder, so a tab can only appear here if it is drawing
## what the server sends.

const SCREEN_SIZE := Vector2i(1280, 720)
const INVASION_ASSISTANT_STATE := 233
const SETTINGS_PATH := "user://eloria_hud.cfg"

var _artifacts := ""
var _failures := 0
var _main: Control
var _app_state: Node
var _assistant: Window


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/invasion-assistant")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	# The window remembers the size it was left at, so a previous run of this
	# fixture would otherwise decide what the first capture shows.
	_forget_stored_size()
	await _open_client()

	# The index and one loaded map. Eleven maps and a roster of eight is the
	# busy case: the sidebar, the canvas and the roster all have to hold real
	# content at once for the capture to prove anything.
	_send({"kind": "index", "selected_map": "four_gates",
		"totals": {"players": 34, "invasions": 61, "active_groups": 3},
		"maps": _index_maps()})
	await _settle()
	_assistant = _main.get("invasion_assistant_window") as Window
	_expect(_assistant != null and _assistant.visible,
		"the assistant is on screen")
	_expect(_assistant.size == Vector2i(784, 504),
		"the assistant covers about half the footprint it used to")
	_expect(_assistant.size.x <= SCREEN_SIZE.x
		and _assistant.size.y <= SCREEN_SIZE.y,
		"the assistant fits the client it opens over")

	_send(_map_state())
	await _settle()
	_expect(_assistant.map_list.item_count == 11,
		"every map in the index is listed")
	_expect(_assistant.location_picker.item_count > 1,
		"the loaded map's named locations are offered")
	await _capture("invasion-assistant-maps.png",
		"the maps tab at 784x504: eleven-map sidebar, legend, tactical canvas"
			+ " with player and invader markers, and the live roster beside it")

	_send(_groups_state())
	await _settle()
	_assistant.tabs.current_tab = 1
	_assistant._on_group_selected(0)
	await _settle()
	_expect(_assistant.group_list.item_count == 4,
		"the configured and live groups are listed")
	_expect(_assistant.group_composition.item_count == 3,
		"the selected group's composition is listed")
	_expect(_assistant.group_detail.text.contains("none — spawns once"),
		"a group built in the assistant states that it spawns once")
	_expect(_assistant.group_maximum.value == 920,
		"the largest wave remains editable without truncation")
	_expect(_assistant.group_detail.text.contains("300 alive · 620 queued"),
		"the live group reports its queued reinforcements")
	await _capture("invasion-assistant-groups.png",
		"the spawn-groups tab: group list, detail block - including the respawn"
			+ " window, which reads none for a group built here - and the live"
			+ " builder's eight fields, with the composition list one scroll below")

	# The composition list is the shortest list in the window and the one
	# most likely to have been squeezed to nothing by the halving, so it
	# gets a capture of its own rather than a caption promising it exists.
	var detail_column: Node = _assistant.group_composition.get_parent()
	var detail_scroll := detail_column.get_parent() as ScrollContainer
	_expect(detail_scroll != null, "the group detail column scrolls")
	if detail_scroll != null:
		detail_scroll.scroll_vertical = 10000
	await _settle()
	await _capture("invasion-assistant-composition.png",
		"the foot of the group builder: three composition rows and the"
			+ " remove control, still legible at the reduced font")

	_send(_monsters_state())
	await _settle()
	_assistant.tabs.current_tab = 2
	_assistant._on_monster_selected(0)
	await _settle()
	_expect(_assistant.monster_list.item_count == 9,
		"the invadable monsters are listed")
	await _capture("invasion-assistant-monsters.png",
		"the monsters tab: the catalog beside a full ten-line stat block and"
			+ " the add-to-group row, six of the nine still marked * for a"
			+ " stand-in model")

	# Most of the shipped roster is still on a stand-in model, so a designer
	# building an invasion that has to look finished wants the short list.
	_assistant.monster_updated_only.button_pressed = true
	await _settle()
	_expect(_assistant.monster_list.item_count == 3,
		"the updated-models filter leaves only the reviewed creatures")
	await _capture("invasion-assistant-monsters-updated.png",
		"the same tab with Updated models only ticked: the six creatures"
			+ " marked * are gone and three reviewed ones remain")
	_assistant.monster_updated_only.button_pressed = false
	await _settle()

	# The corner grip: the same handle the inventory panel carries. The pair of
	# captures below is the whole argument for scaling the window rather than
	# resizing its frame - the same eleven maps, the same canvas and the same
	# roster are in both, drawn larger and smaller.
	_assistant.tabs.current_tab = 0
	_assistant.resize_to_scale(1.35)
	await _settle()
	_expect(_assistant.size.x > 1000, "the grip enlarges the window")
	await _capture("invasion-assistant-enlarged.png",
		"the maps tab dragged out to its largest scale on a 1280x720 client:"
			+ " the same layout, drawn bigger")

	_assistant.resize_to_scale(0.65)
	await _settle()
	_expect(_assistant.size == Vector2i(510, 328),
		"the grip shrinks the window to its smallest scale")
	_expect(absf(_assistant.get_visible_rect().size.x - 784.0) <= 2.0,
		"the smallest window still lays its contents out across the full 784")
	await _capture("invasion-assistant-smallest.png",
		"the maps tab at its smallest scale, 510x328: the sidebar, the canvas"
			+ " and the roster are all still there, just smaller")

	_forget_stored_size()
	await _settle()

	_app_state.set("authenticated", false)
	_main.queue_free()
	await process_frame
	print("rendered invasion assistant: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _forget_stored_size() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return
	if not config.has_section_key(WindowPreferences.SECTION,
			"invasion_assistant_scale"):
		return
	config.erase_section_key(WindowPreferences.SECTION, "invasion_assistant_scale")
	config.save(SETTINGS_PATH)


func _open_client() -> void:
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("GameView") as Control).show()
	(_main.get_node("LoginPanel") as Control).hide()
	_app_state = root.get_node("/root/AppState")
	_app_state.set("authenticated", true)
	await _settle()


## Through the real decoder rather than straight into the window: command 233
## carries the assistant's state as JSON, and a payload that cannot survive
## that round trip is not evidence of anything.
func _send(state: Dictionary) -> void:
	_app_state.call("_on_packet", INVASION_ASSISTANT_STATE,
		JSON.stringify(state).to_utf8_buffer())


func _index_maps() -> Array:
	var maps: Array = []
	for entry: Array in [["four_gates", "Four Gates City", 12, 24, 2],
			["ember", "Emberhaven", 4, 11, 1], ["crownwater", "Crownwater", 3, 0, 0],
			["mirrorhold", "Mirrorhold", 2, 9, 0], ["grey_moors", "Grey Moors", 5, 6, 0],
			["sunmane", "Sunmane Steppe", 1, 4, 0], ["westhaven", "Westhaven", 2, 0, 0],
			["verdant", "Verdant Hollow", 0, 3, 0], ["whitehorn", "Whitehorn", 3, 2, 0],
			["amethyst", "Amethyst Barrens", 1, 2, 0],
			["manymouth", "Manymouth Marsh", 1, 0, 0]]:
		maps.append({"id": entry[0], "name": entry[1],
			"file": "maps/%s.elm" % entry[0], "players": entry[2],
			"invasions": entry[3], "active_groups": entry[4]})
	return maps


func _map_state() -> Dictionary:
	var players: Array = []
	for entry: Array in [["Kellan", 78, 96, 45], ["Maren", 120, 60, 38],
			["Toma Reed", 44, 150, 62], ["Ivet Somer", 160, 132, 21],
			["Halden", 90, 40, 55], ["Nyx", 30, 110, 33],
			["Sorrel", 140, 90, 47], ["Bram", 70, 170, 29]]:
		players.append({"name": entry[0], "x": entry[1], "y": entry[2],
			"combat_level": entry[3]})
	var creatures: Array = []
	for entry: Array in [["Ash Wyrm", 82, 100, 150, 180, "Formidable", true],
			["Cinder Hound", 88, 104, 60, 60, "Dangerous", false],
			["Cinder Hound", 76, 92, 44, 60, "Dangerous", false],
			["Ember Shade", 110, 70, 90, 120, "Fearsome", false],
			["Ember Shade", 118, 66, 120, 120, "Fearsome", false],
			["Slag Crawler", 50, 140, 30, 45, "Average", false]]:
		creatures.append({"name": entry[0], "x": entry[1], "y": entry[2],
			"health": entry[3], "max_health": entry[4], "tier": entry[5],
			"boss": entry[6]})
	return {"kind": "map",
		"map": {"id": "four_gates", "name": "Four Gates City",
			"file": "maps/startmap.elm", "width": 256, "height": 256},
		"locations": [{"name": "North Gate", "kind": "invasion_spawn", "x": 128, "y": 20},
			{"name": "South Gate", "kind": "invasion_spawn", "x": 128, "y": 232},
			{"name": "Storage", "kind": "portal", "x": 96, "y": 118}],
		"players": players, "creatures": creatures}


func _groups_state() -> Dictionary:
	return {"kind": "groups", "groups": [
		{"name": "North Gate Wave", "description": "Opening pressure on the north road",
			"map_id": "four_gates", "map_name": "Four Gates City", "minimum": 340,
			"maximum": 920, "points": 3, "creatures": ["ash_wyrm", "cinder_hound"],
			"composition": [{"type": "ash_wyrm", "name": "Ash Wyrm", "quantity": 4},
				{"type": "cinder_hound", "name": "Cinder Hound", "quantity": 12},
				{"type": "ember_shade", "name": "Ember Shade", "quantity": 6}],
			"locations": [{"x": 128, "y": 20, "quantity": 12}], "strength": 1840,
			"active": true, "alive": 300, "queued": 620, "boss": "The Cinder Maw",
			"boss_type": "ash_wyrm", "boss_name": "The Cinder Maw",
			"health_multiplier": 1.5, "auto_respawn_minutes": -1, "dynamic": true},
		{"name": "Ashfall Ridge", "description": "Emberhaven escalation",
			"map_id": "ember", "map_name": "Emberhaven", "minimum": 4, "maximum": 8,
			"points": 1, "creatures": ["ash_wyrm"],
			"composition": [{"type": "ash_wyrm", "name": "Ash Wyrm", "quantity": 4}],
			"locations": [{"x": 80, "y": 90, "quantity": 4}], "strength": 480,
			"active": false, "alive": 0, "boss": "", "boss_type": "",
			"boss_name": "", "health_multiplier": 1.0, "auto_respawn_minutes": 0,
			"dynamic": false},
		{"name": "Marsh Creep", "description": "Slow build in the reeds",
			"map_id": "manymouth", "map_name": "Manymouth Marsh", "minimum": 6,
			"maximum": 10, "points": 2, "creatures": ["slag_crawler"],
			"composition": [{"type": "slag_crawler", "name": "Slag Crawler",
				"quantity": 8}],
			"locations": [{"x": 40, "y": 60, "quantity": 8}], "strength": 320,
			"active": false, "alive": 0, "boss": "", "boss_type": "",
			"boss_name": "", "health_multiplier": 1.0, "dynamic": false},
		{"name": "Steppe Riders", "description": "Mounted sweep",
			"map_id": "sunmane", "map_name": "Sunmane Steppe", "minimum": 8,
			"maximum": 16, "points": 2, "creatures": ["ember_shade"],
			"composition": [{"type": "ember_shade", "name": "Ember Shade",
				"quantity": 10}],
			"locations": [{"x": 200, "y": 44, "quantity": 10}], "strength": 990,
			"active": false, "alive": 0, "boss": "", "boss_type": "",
			"boss_name": "", "health_multiplier": 1.0, "dynamic": true}]}


func _monsters_state() -> Dictionary:
	var monsters: Array = []
	# The last column is the server's placeholder_model: only 57 of the 244
	# shipped creatures carry "model: final", so a roster where two thirds are
	# still on a stand-in is the honest case for the filter to work against.
	for entry: Array in [["ash_wyrm", "Ash Wyrm", "Formidable", 120, true, false],
			["cinder_hound", "Cinder Hound", "Dangerous", 74, true, false],
			["ember_shade", "Ember Shade", "Fearsome", 96, true, true],
			["slag_crawler", "Slag Crawler", "Average", 38, false, true],
			["moss_bear", "Moss Bear", "Dangerous", 66, false, false],
			["moss_horn_ram", "Moss Horn Ram", "Average", 41, false, true],
			["abyssal_armored_fish", "Abyssal Armored Fish", "Formidable", 118, false, true],
			["amber_lantern_moth", "Amber Lantern Moth", "Harmless", 9, false, true],
			["amberwood_great_owl", "Amberwood Great Owl", "Average", 45, false, true]]:
		var rating: int = entry[3]
		var placeholder: bool = entry[5]
		monsters.append({"type": entry[0],
			"name": ("*" if placeholder else "") + str(entry[1]), "tier": entry[2],
			"rating": rating, "combat_level": rating / 2, "level": rating / 12,
			"health": rating * 3, "ether": rating, "attack": rating / 3,
			"defense": rating / 4, "damage_min": rating / 20,
			"damage_max": rating / 10, "armor_min": rating / 40,
			"armor_max": rating / 24, "configured": entry[4],
			"placeholder_model": placeholder})
	return {"kind": "monsters", "monsters": monsters}


func _settle() -> void:
	for _frame: int in range(4):
		await process_frame


func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)


func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02


func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value

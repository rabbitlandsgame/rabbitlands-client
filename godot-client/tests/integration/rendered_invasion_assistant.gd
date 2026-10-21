extends SceneTree
## Rendered evidence for the map-first builder, compact monitor and movement tools.

const SCREEN_SIZE := Vector2i(1280, 720)
const INVASION_ASSISTANT_STATE := 233

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
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/invasion-assistant")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK, "artifact directory is writable")
	root.size = SCREEN_SIZE
	await _open_client()
	_send({"kind":"index", "selected_map":"four_gates", "totals":{"players":34,"invasions":61,"active_groups":3}, "maps":_index_maps()})
	await _settle()
	_assistant = _main.get("invasion_assistant_window") as Window
	_assistant.monitor_preferences_path = _artifacts.path_join("monitor-preferences.cfg")
	_assistant.set_monitor_docked(true)
	_assistant._preferred_scale = 1.0
	_assistant._fit_to_viewport()
	_send(_map_state())
	_send(_groups_state())
	_send(_monsters_state())
	_assistant._on_group_selected(0)
	_assistant.tabs.current_tab = 0
	await _settle()
	_expect(_assistant.size == Vector2i(1100,620), "readable builder fits the game viewport")
	_expect(_assistant.map_list.item_count == 11, "all server maps remain selectable")
	_expect(_assistant.group_composition.item_count == 3, "composition is beside the map")
	_expect(_assistant._map_texture("four_gates") != null, "published player Tab-map artwork is reused")
	await _capture("invasion-assistant-builder.png", "Map-first builder with persistent composition and player cartography")
	_assistant.inspector_tabs.current_tab = 1
	_assistant.anchor_enabled.button_pressed = true
	_assistant.anchor_x.value = 128
	_assistant.anchor_y.value = 20
	_assistant.anchor_radius.value = 16
	_assistant._on_region_selected(Rect2i(110,4,37,33))
	await _capture("invasion-assistant-movement.png", "Center and rectangular region preview in logical server coordinates")
	_assistant.inspector_tabs.current_tab = 0
	_assistant.tabs.current_tab = 2
	_assistant._on_monster_selected(0)
	await _capture("invasion-assistant-creatures.png", "Creature catalog retains the selected group's composition")
	_assistant.monster_updated_only.button_pressed = true
	_expect(_assistant.monster_list.item_count == 3, "reviewed-model filter retains only reviewed creatures")
	_assistant.monster_updated_only.button_pressed = false
	_assistant.set_monitor_mode(true)
	await _settle()
	_expect(_assistant.size.x <= 390, "monitor leaves most of the game visible")
	var dock_area: Rect2 = _main._invasion_monitor_dock_rect()
	_expect(_assistant.position == Vector2i(dock_area.end.x - _assistant.size.x, dock_area.position.y)
		and _assistant.size.y == int(dock_area.size.y), "monitor joins the actual right rail and bottom HUD")
	_expect(_assistant.borderless, "docked monitor has no floating title-bar gap")
	_expect(_assistant.monitor_clear.get_global_rect().end.y <= _assistant.size.y, "monitor controls stay reachable")
	await _capture("invasion-assistant-monitor.png", "Monitor docked flush against the right HUD and bottom action bar")
	_assistant.monitor_dock_button.pressed.emit()
	_assistant._monitor_drag_offset = Vector2i(60, 14)
	_assistant._drag_monitor_to(Vector2i(520, 34))
	var floating_position: Vector2i = _assistant.position
	await _capture("invasion-assistant-monitor-undocked.png", "Detached monitor with a draggable title and Dock right control")
	_assistant.hide()
	_assistant.show()
	await _settle()
	_expect(_assistant.position == floating_position, "reopened monitor keeps its floating position")
	_assistant.set_monitor_docked(true)
	await _settle()
	var rail := _main.get_node("GameView/RightRail") as Control
	var previous_rail_left := rail.offset_left
	rail.offset_left -= 30
	await _settle()
	dock_area = _main._invasion_monitor_dock_rect()
	_expect(_assistant.position.x + _assistant.size.x == int(dock_area.end.x),
		"docked monitor follows a changed resource rail width")
	rail.offset_left = previous_rail_left
	root.size = Vector2i(960, 540)
	await _settle()
	dock_area = _main._invasion_monitor_dock_rect()
	_expect(Rect2(_assistant.position, _assistant.size).is_equal_approx(
		Rect2(dock_area.end.x - _assistant.size.x, dock_area.position.y, _assistant.size.x, dock_area.size.y)),
		"small-screen dock stays attached to the live HUD")
	await _capture("invasion-assistant-monitor-small.png", "Docked monitor on a smaller game window")
	root.size = SCREEN_SIZE
	await _settle()
	_assistant.set_monitor_mode(false)
	_assistant.tabs.current_tab = 0
	_assistant.resize_to_scale(0.65)
	_assistant._size_save_countdown = 0
	await _settle()
	_expect(not _assistant.map_sidebar.visible and _assistant.content_scale_factor == 1.0, "compact builder reflows without shrinking text")
	await _capture("invasion-assistant-compact-builder.png", "Narrow builder collapses the map sidebar and preserves readable type")
	_assistant.resize_to_scale(1.0)
	_assistant._size_save_countdown = 0
	root.size = Vector2i(960,540)
	await _settle()
	_expect(_assistant.size.x <= 960 and _assistant.size.y <= 540, "small viewport fits with scrollable workspace")
	root.size = SCREEN_SIZE
	await _settle()
	_app_state.set("authenticated", false)
	_main.queue_free()
	await process_frame
	print("rendered invasion assistant: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


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
	_expect(image != null and image.get_size() == root.size,
		"%s is a full %dx%d frame" % [name, root.size.x, root.size.y])
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

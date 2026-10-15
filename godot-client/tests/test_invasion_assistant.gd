extends SceneTree

const AssistantScript := preload("res://src/ui/invasion_assistant.gd")
const SETTINGS_PATH := "user://eloria_hud.cfg"

var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(1280, 720)
	_forget_stored_size()
	var assistant = AssistantScript.new()
	root.add_child(assistant)
	# The assistant used to open at 1120x720 and swallow a 1280x720 client.
	_expect(assistant.size == Vector2i(784, 504),
		"the assistant opens at about half the footprint it used to claim")
	var commands: Array[String] = []
	assistant.command_requested.connect(func(command: String) -> void: commands.append(command))
	var registry_file := FileAccess.open("res://data/maps/registry.json", FileAccess.READ)
	if registry_file != null:
		var registry_json: Dictionary = JSON.parse_string(registry_file.get_as_text()) as Dictionary
		assistant.configure_registry(registry_json.get("maps", {}) as Dictionary)
	assistant.apply_update({
		"kind": "index", "selected_map": "ember",
		"totals": {"players": 1, "invasions": 2, "active_groups": 1},
		"maps": [{"id": "ember", "name": "Emberhaven",
			"file": "maps/ember.elm", "players": 1, "invasions": 2,
			"active_groups": 1}]})
	_expect(assistant.map_list.item_count == 1, "map index populates")
	assistant.apply_update({
		"kind": "map",
		"map": {"id": "ember", "name": "Emberhaven", "file": "maps/ember.elm",
			"width": 256, "height": 192},
		"locations": [{"name": "Ashfall Ridge", "kind": "invasion_spawn",
			"x": 80, "y": 90}],
		"players": [{"name": "Master", "x": 30, "y": 40, "combat_level": 45}],
		"creatures": [{"name": "Ash Wyrm", "x": 75, "y": 88,
			"health": 150, "max_health": 180, "tier": "Formidable", "boss": true}]})
	_expect(assistant.map_canvas.state.players.size() == 1, "player marker populates")
	_expect(assistant.map_canvas.state.creatures[0].boss, "boss marker populates")
	_expect(not assistant.teleport_button.disabled, "teleport enables for a loaded map")
	var long_named: Dictionary = assistant.map_state.duplicate(true)
	long_named["locations"] = [{"name": ("The Drowned Arcades: The Campanile Stair "
		+ "(mid, 0: heavies of abyssal_armored_fish) #1"), "kind": "invasion_spawn",
		"x": 16, "y": 72}]
	assistant.apply_update(long_named)
	# The picker, both coordinates and Teleport share the row beside the
	# 190-pixel map list; a gauntlet's spawn names used to widen it until
	# Teleport sat off the window's right edge.
	var location_row: Control = assistant.teleport_button.get_parent()
	_expect(location_row.get_combined_minimum_size().x <= 784 - 190 - 16,
		"a long location name leaves Teleport inside the window")
	var busy_map: Dictionary = assistant.map_state.duplicate(true)
	var invaders: Array = []
	for i in range(921):
		invaders.append({"actor_id": i, "name": "Rabbit", "x": i % 32,
			"y": i / 32, "health": 10, "max_health": 10, "boss": i == 0})
	busy_map["page"] = 0
	busy_map["pages"] = 2
	busy_map["creatures"] = invaders.slice(0, 500)
	assistant.apply_update(busy_map)
	_expect(assistant.map_canvas.state.creatures.size() == 1,
		"a partial live map keeps the previous view until all actors arrive")
	busy_map["page"] = 1
	busy_map["creatures"] = invaders.slice(500)
	assistant.apply_update(busy_map)
	_expect(assistant.map_canvas.state.creatures.size() == 921,
		"the map shows every actor from all pages of a large wave")
	_expect(assistant.map_canvas.state.creatures[920].actor_id == 920,
		"the final reinforcement marker survives the paged update")
	busy_map.erase("page")
	busy_map.erase("pages")
	busy_map["creatures"] = []
	assistant.apply_update(busy_map)
	_expect(assistant.map_canvas.state.creatures.is_empty(),
		"an empty refresh clears the previous large wave")
	_expect(assistant._map_texture("four_gates") != null,
		"minimap loads directly from the external asset workspace")
	_check_map_coordinates_and_labels(assistant)
	root.size = Vector2i(960, 540)
	assistant._fit_to_viewport()
	_expect(assistant.size.x <= root.size.x and assistant.size.y <= root.size.y,
		"assistant stays within the viewport")

	# Resizing from the corner grip, and the preference that outlives it.
	root.size = Vector2i(1280, 720)
	assistant._fit_to_viewport()
	var full_extent: Vector2 = assistant.get_visible_rect().size
	_expect(absf(full_extent.x - 784.0) <= 1.0 and absf(full_extent.y - 504.0) <= 1.0,
		"the layout is 784x504 at its shipped scale")

	# The point of scaling rather than resizing: a smaller window draws the
	# same layout smaller. A frame that shrank without its contents would take
	# the roster or the map sidebar off the edge instead.
	assistant.resize_to_scale(0.1)
	_expect(assistant.size.x < 784 and assistant.size.y < 504,
		"the grip shrinks the window")
	var shrunk: Vector2 = assistant.get_visible_rect().size
	_expect(absf(shrunk.x - full_extent.x) <= 2.0
		and absf(shrunk.y - full_extent.y) <= 2.0,
		"a shrunken window lays its contents out across the same extent,"
			+ " so the elements get smaller rather than cut off")
	_expect(assistant.size.x >= roundi(784.0 * 0.65),
		"the grip cannot shrink the assistant past its smallest scale")
	assistant.resize_to_scale(9.0)
	_expect(assistant.size.x <= root.size.x and assistant.size.y <= root.size.y,
		"the grip cannot grow the assistant past the viewport")
	var grown: Vector2 = assistant.get_visible_rect().size
	_expect(absf(grown.x - full_extent.x) <= 2.0
		and absf(grown.y - full_extent.y) <= 2.0,
		"an enlarged window draws the same layout larger rather than"
			+ " stretching it into more room than it has content for")

	assistant.resize_to_scale(1.25)
	_expect(assistant.size == Vector2i(980, 630), "the grip scales the window")
	assistant._flush_size_preference()
	root.size = Vector2i(640, 400)
	assistant._fit_to_viewport()
	_expect(assistant.size.x < 980
		and is_equal_approx(assistant._preferred_scale, 1.25),
		"a viewport too small for the chosen scale draws it smaller without"
			+ " forgetting the choice")
	root.size = Vector2i(1280, 720)
	assistant._fit_to_viewport()
	_expect(assistant.size == Vector2i(980, 630),
		"the remembered scale comes back once the viewport can hold it")

	# A window opened again - in this session or the next one - starts at the
	# size the player left it at rather than at the shipped one.
	var reopened = AssistantScript.new()
	root.add_child(reopened)
	_expect(reopened.size == Vector2i(980, 630),
		"a freshly opened assistant restores the stored size preference")
	reopened.queue_free()

	assistant.apply_update({"kind": "groups", "groups": [{
		"name": "ashfall", "description": "Ashfall Ridge", "map_id": "ember",
		"map_name": "Emberhaven", "minimum": 4, "maximum": 8, "points": 1,
		"creatures": ["ash_wyrm"], "composition": [{"type": "ash_wyrm",
			"name": "Ash Wyrm", "quantity": 4}],
		"locations": [{"x": 80, "y": 90, "quantity": 4}],
		"strength": 120, "active": false, "alive": 0,
		"boss": "The Cinder Maw", "boss_type": "ash_wyrm",
		"boss_name": "The Cinder Maw", "health_multiplier": 1.0,
		"dynamic": true}]})
	_expect(assistant.group_list.item_count == 1, "spawn groups populate")

	# The served profile ships 600 invasion groups, which is eight times what
	# one packet holds, so the server sends them a page at a time. A page is a
	# whole message on its own; what the window must not do is show only the
	# last one.
	var _page := func(index: int, total: int, names: Array) -> Dictionary:
		var entries: Array = []
		for entry_name: String in names:
			entries.append({
				"name": entry_name, "description": "", "map_id": "ember",
				"map_name": "Emberhaven", "minimum": 1, "maximum": 1,
				"points": 1, "creatures": ["ash_wyrm"], "composition": [],
				"locations": [], "strength": 1, "active": false, "alive": 0,
				"boss": "", "boss_type": "", "boss_name": "",
				"health_multiplier": 1.0, "dynamic": false})
		return {"kind": "groups", "groups": entries,
			"page": index, "pages": total}

	assistant.apply_update(_page.call(0, 3, ["one", "two"]))
	_expect(assistant.group_list.item_count == 1,
		"a partial list does not replace the one on screen")
	assistant.apply_update(_page.call(1, 3, ["three"]))
	assistant.apply_update(_page.call(2, 3, ["four", "five"]))
	_expect(assistant.group_list.item_count == 5,
		"every page is kept, not just the last")
	_expect(str(assistant.groups_state.get("groups")[0].get("name")) == "one",
		"the first page survives to the end")

	# And a server that sends the state whole, with no page fields, still
	# replaces rather than appending forever.
	assistant.apply_update({"kind": "groups", "groups": [{
		"name": "ashfall", "description": "Ashfall Ridge", "map_id": "ember",
		"map_name": "Emberhaven", "minimum": 4, "maximum": 8, "points": 1,
		"creatures": ["ash_wyrm"], "composition": [{"type": "ash_wyrm",
			"name": "Ash Wyrm", "quantity": 4}],
		"locations": [{"x": 80, "y": 90, "quantity": 4}],
		"strength": 120, "active": false, "alive": 0,
		"boss": "The Cinder Maw", "boss_type": "ash_wyrm",
		"boss_name": "The Cinder Maw", "health_multiplier": 1.0,
		"dynamic": true}]})
	_expect(assistant.group_list.item_count == 1,
		"an unpaged state replaces the accumulated one")
	assistant._on_group_selected(0)
	_expect(not assistant.group_spawn.disabled, "defined group can be spawned")
	_expect(not assistant.group_save.disabled, "dynamic group is editable")
	var large_group: Dictionary = assistant.selected_group.duplicate(true)
	large_group["minimum"] = 600
	large_group["maximum"] = 920
	large_group["active"] = true
	large_group["alive"] = 300
	large_group["queued"] = 620
	assistant.apply_update({"kind": "groups", "groups": [large_group]})
	assistant._on_group_selected(0)
	_expect(assistant.group_minimum.value == 600 and assistant.group_maximum.value == 920,
		"large wave counts are not clamped to the old 500 limit")
	_expect(assistant.group_detail.text.contains("300 alive · 620 queued"),
		"the group distinguishes living creatures from queued reinforcements")
	assistant._save_group()
	_expect(commands[-1].contains("|600|920|"),
		"saving a duplicated large wave preserves both population endpoints")
	large_group["queued"] = 0
	large_group["active"] = false
	assistant.apply_update({"kind": "groups", "groups": [large_group]})
	assistant._on_group_selected(0)

	# A group built in the assistant spawns once. The three respawn windows
	# the server can report have to read differently, because activating a
	# wave that comes back forever in front of players is not recoverable.
	_expect(assistant._respawn_summary({"auto_respawn_minutes": -1})
		== "none — spawns once",
		"a shut respawn window reads as spawning once")
	_expect(assistant._respawn_summary({"auto_respawn_minutes": 0})
		== "every wipe, while active",
		"an open respawn window reads as respawning for as long as it is active")
	_expect(assistant._respawn_summary({"auto_respawn_minutes": 30})
		== "every wipe for 30 min", "a timed respawn window reads as its length")
	_expect(assistant._respawn_summary({}) == "every wipe, while active",
		"a server that says nothing is read as the server default, not as none")
	_expect(assistant.group_detail.text.contains("Respawns"),
		"the selected group states its respawn window")
	assistant.apply_update({"kind": "monsters", "monsters": [{
		"type": "ash_wyrm", "name": "Ash Wyrm", "tier": "Formidable",
		"rating": 120, "combat_level": 60, "level": 10, "health": 180,
		"ether": 30, "attack": 40, "defense": 20, "damage_min": 6,
		"damage_max": 12, "armor_min": 2, "armor_max": 5,
		"configured": true, "placeholder_model": false},
		{"type": "slag_crawler", "name": "*Slag Crawler", "tier": "Average",
		"rating": 38, "combat_level": 19, "level": 3, "health": 45,
		"ether": 10, "attack": 12, "defense": 8, "damage_min": 1,
		"damage_max": 3, "armor_min": 0, "armor_max": 1,
		"configured": false, "placeholder_model": true},
		{"type": "moss_bear", "name": "*Moss Bear", "tier": "Dangerous",
		"rating": 66, "combat_level": 33, "level": 5, "health": 90,
		"ether": 20, "attack": 20, "defense": 14, "damage_min": 3,
		"damage_max": 6, "armor_min": 1, "armor_max": 2,
		"configured": false}]})
	_expect(assistant.monster_list.item_count == 3, "monster catalog populates")

	# Only the creatures whose model has been through review - the ones the
	# server does not mark with a leading asterisk.
	assistant.monster_updated_only.button_pressed = true
	_expect(assistant.monster_list.item_count == 1,
		"the updated-models filter hides the creatures still on a stand-in model")
	_expect(str(assistant.monster_list.get_item_text(0)).contains("Ash Wyrm"),
		"the reviewed creature is the one left")
	_expect(not assistant.has_placeholder_model({"placeholder_model": false,
			"name": "*Mislabelled"}),
		"the server's own flag decides, not the decorated name")
	_expect(assistant.has_placeholder_model({"name": "*Moss Bear"}),
		"a server that sends only the mark is still filtered on")
	assistant.monster_updated_only.button_pressed = false
	_expect(assistant.monster_list.item_count == 3,
		"clearing the filter brings the whole catalog back")
	assistant._on_monster_selected(0)
	assistant.monster_quantity.value = 3
	assistant._add_monster_to_group()
	_expect(commands[-1] == "#invasion_assistant group add ashfall|ash_wyrm|3|80|90",
		"selected monster can be added to a selected live group")
	assistant._spawn_monster_here()
	_expect(commands[-1] == "#invasion_assistant monster spawn ash_wyrm|3",
		"selected monster can be quick-spawned at the invasion master's location")
	commands.clear()
	assistant.tabs.current_tab = 0
	assistant.show()
	assistant._process(5.1)
	_expect(commands.has("#invasion_assistant map ember"),
		"visible map refreshes periodically")
	assistant._teleport()
	_expect(commands[-1].begins_with("#invasion_assistant teleport ember "),
		"teleport requests an immediate server-authoritative refresh response")
	assistant.god_storage_button.pressed.emit()
	_expect(commands[-1] == "#god_storage",
		"header button opens the invasion-master god storage")
	assistant.queue_free()
	_forget_stored_size()
	if failures == 0:
		print("invasion assistant tests passed")
	quit(failures)


## The preference is written to the real settings file, so the assertions
## above have to start from a client that has never been resized.
func _forget_stored_size() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return
	if not config.has_section_key(WindowPreferences.SECTION,
			"invasion_assistant_scale"):
		return
	config.erase_section_key(WindowPreferences.SECTION, "invasion_assistant_scale")
	config.save(SETTINGS_PATH)


func _check_map_coordinates_and_labels(assistant: Window) -> void:
	var canvas := InvasionMapCanvas.new()
	root.add_child(canvas)
	canvas.size = Vector2(600, 400)
	var state := {"map": {"id": "test", "width": 256, "height": 192}}
	canvas.set_map_state(state)
	var north := canvas._point(Vector2(40, 170))
	var south := canvas._point(Vector2(40, 20))
	_expect(north.y < south.y and is_equal_approx(north.x, south.x),
		"north draws above south without reversing east and west")
	for tile: Vector2i in [Vector2i.ZERO, Vector2i(255, 191), Vector2i(40, 170)]:
		_expect(canvas._tile(canvas._point(Vector2(tile))) == tile,
			"clicking a marker selects its exact server tile, including edge tiles")
	var rect := canvas._map_rect()
	_expect(canvas._tile(rect.position) == Vector2i(0, 191)
		and canvas._tile(rect.end) == Vector2i(255, 0),
		"map corners clamp to the north-west and south-east server tiles")
	# The background contains more world than the server's addressable grid.
	# A flip alone would still put every off-centre marker in the wrong place.
	var image := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	var texture := ImageTexture.create_from_image(image)
	var projection := {"minimap": {"worldMin": [-100, -80], "worldMax": [300, 220]},
		"coordinateTransform": {"metresPerTile": 2.0, "serverOrigin": [100, 90],
			"origin": [10, 0, 20], "invertServerY": true}}
	canvas.set_map_state(state, texture, projection)
	var tile := Vector2i(120, 110)
	# Tile centre -> world (51, -21) -> image UV (151/400, 59/300).
	var expected := rect.position + Vector2(151.0 / 400.0, 59.0 / 300.0) * rect.size
	_expect(canvas._point(Vector2(tile)).is_equal_approx(expected),
		"markers use the background's world bounds and coordinate transform")
	var selected: Array[Vector2i] = []
	canvas.coordinate_selected.connect(func(value: Vector2i) -> void: selected.append(value))
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = expected
	canvas._gui_input(click)
	_expect(selected == [tile] and canvas.selected_tile == tile,
		"clicking the terrain stages the server coordinate under the cursor")
	# Verify the real Four Gates package is wired into the same projection.
	var actual: Dictionary = assistant._map_projection("four_gates")
	canvas.set_map_state({"map": {"id": "four_gates", "width": 720, "height": 720}},
		assistant._map_texture("four_gates"), actual)
	_expect(canvas._adapter != null and canvas._tile(canvas._point(Vector2(360, 500)))
		== Vector2i(360, 500), "the shipped map uses its authored projection")
	var locations: Array[Dictionary] = []
	for index: int in range(24):
		locations.append({"name": "Spawn %d" % index, "kind": "invasion_spawn",
			"x": 20 + (index % 4) * 60, "y": 15 + (index / 4) * 28})
	locations.append({"name": "Waygate", "kind": "portal", "x": 100, "y": 100})
	state["locations"] = locations
	canvas.set_map_state(state)
	var labels := canvas._location_labels(ThemeDB.fallback_font)
	_expect(labels.size() > 0 and labels.size() <= 6 and labels[0].text == "Waygate",
		"busy maps show at most six names and prioritise portals")
	for a: int in range(labels.size()):
		for b: int in range(a + 1, labels.size()):
			_expect(not (labels[a].rect as Rect2).intersects(labels[b].rect),
				"location names do not overlap")
	canvas._update_hover(canvas._point(Vector2(20, 15)))
	_expect(canvas.tooltip_text.begins_with("Spawn 0") and canvas.state.locations.size() == 25,
		"locations without drawn names remain available on hover")
	canvas.queue_free()


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("FAIL: " + message)

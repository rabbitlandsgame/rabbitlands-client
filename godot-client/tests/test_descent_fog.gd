extends SceneTree
## A descent's fog of war (descent_v1, server message 188): the state as
## AppState keeps it, the explored bits in the contract's order, the tile to
## cell lookup, the black volume and the map picture built from them, the
## culling that hides creatures and objects in the fog, and what a closed
## state leaves behind - in the pure helper and through Main.

const DescentFog := preload("res://src/world/descent_fog.gd")
const SectionsScript := preload("res://src/world/secret_sections.gd")
const SECTION := "serpent_deep_f3v2"
const ORIGIN := Vector2i(100, 200)
const WIDTH := 6
const HEIGHT := 5
## Revealed cells of the 6 x 5 fixture. Row-major i = cy * 6 + cx, bit i & 7 of
## byte i >> 3: (0,0) i0, (1,0) i1, (2,0) i2, (1,1) i7 -> byte 0 = 0x87;
## (2,1) i8, (3,2) i15 -> byte 1 = 0x81; byte 2 = 0; (5,4) i29 -> byte 3 = 0x20.
const REVEALED_CELLS: Array[Vector2i] = [Vector2i(0, 0), Vector2i(1, 0), Vector2i(2, 0),
	Vector2i(1, 1), Vector2i(2, 1), Vector2i(3, 2), Vector2i(5, 4)]
const MASK_BYTES := [0x87, 0x81, 0x00, 0x20]
const EXPLORED := "h4EAIA=="

var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _state(explored := EXPLORED, extra := {}) -> Dictionary:
	var state := {"version": 1, "kind": "state", "open": true,
		"run": "a91c", "dungeon": "serpent_deep", "name": "The Serpent Deep", "difficulty": "Hard",
		"floor": 3, "floors": 6, "floor_name": "The Buried Streets",
		"section": SECTION, "origin": [ORIGIN.x, ORIGIN.y],
		"cell_tiles": 2, "width": WIDTH, "height": HEIGHT,
		"explored": explored, "time_left": 2345, "boss": ""}
	state.merge(extra, true)
	return state

func _bytes(value: Dictionary) -> PackedByteArray:
	return JSON.stringify(value).to_utf8_buffer()

func _decode(value: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(value))

## An insides-style frame: one metre a tile, server y running north.
func _adapter() -> CoordinateAdapter:
	return CoordinateAdapter.new({"metresPerTile": 1.0, "origin": [0.0, 0.0, 0.0],
		"serverOrigin": [0.0, 840.0], "invertServerY": true, "walkingHeight": 0.0})

func _run() -> void:
	create_timer(120).timeout.connect(func() -> void:
		push_error("FAIL: descent fog test timed out")
		quit(1))
	root.size = Vector2i(1280, 720)
	var app: Node = root.get_node("AppState")
	_check_decoding()
	_check_state(app)
	var grid := DescentFog.view(app.descent)
	_check_lookup(grid)
	_check_mesh(grid)
	_check_image(grid)
	_check_sections_cull(grid)
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		_bytes({"version": 1, "kind": "state", "open": false}))
	_expect(app.descent.is_empty() and DescentFog.view(app.descent).is_empty(),
		"open false clears the descent state")
	_expect(not DescentFog.tile_hidden(DescentFog.view(app.descent), 106, 200)
		and DescentFog.build_mesh(DescentFog.view(app.descent), _adapter(), 0.0) == null,
		"a closed descent hides no tile and builds no fog")
	await _check_main(app)
	print("descent fog checks: %d, failures: %d" % [checks, failures])
	quit(failures)

func _check_decoding() -> void:
	_expect("descent_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "descent_v1 is advertised")
	_expect(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE == 188, "the descent state is message 188")
	var decoded := _decode(_state())
	_expect(decoded.type == "descent_state", "the contract's state decodes")
	_expect(decoded.data.mask == PackedByteArray(MASK_BYTES), "the explored text decodes to its bytes")
	_expect(DescentFog.decode_mask(EXPLORED, WIDTH, HEIGHT) == PackedByteArray(MASK_BYTES)
		and Marshalls.raw_to_base64(PackedByteArray(MASK_BYTES)) == EXPLORED,
		"the fixture's mask is ceil(30 / 8) = 4 bytes of base64")
	for case: Array in [
			["a mask one byte short", _state(Marshalls.raw_to_base64(PackedByteArray([0x87, 0x81, 0x00])))],
			["a mask one byte long", _state(Marshalls.raw_to_base64(PackedByteArray([0x87, 0x81, 0, 0x20, 0])))],
			["text that is not base64", _state("h4E*IA==")],
			["padding inside the text", _state("h4=AIA==")],
			["another version", _state(EXPLORED, {"version": 2})],
			["no open flag", _state(EXPLORED, {"open": null})],
			["an unknown kind", _state(EXPLORED, {"kind": "map"})],
			["a fractional width", _state(EXPLORED, {"width": 6.5})],
			["a zero cell size", _state(EXPLORED, {"cell_tiles": 0})],
			["a floor past the last", _state(EXPLORED, {"floor": 7})],
			["an origin of one number", _state(EXPLORED, {"origin": [100]})],
			["an unknown boss phase", _state(EXPLORED, {"boss": "asleep"})]]:
		_expect(_decode(case[1]).type == "invalid", "%s is refused" % case[0])
	var closed := _decode({"version": 1, "kind": "state", "open": false})
	_expect(closed.type == "descent_state" and not closed.data.open, "a closed state decodes")
	var boss := _decode(_state(EXPLORED, {"boss": "defeated"}))
	_expect(boss.type == "descent_state" and boss.data.boss == "defeated", "the boss phase is kept")

func _check_state(app: Node) -> void:
	app.descent.clear()
	var changes: Array[StringName] = []
	var listener := func(path: StringName) -> void: changes.append(path)
	app.state_changed.connect(listener)
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(_state()))
	app.state_changed.disconnect(listener)
	var state: Dictionary = app.descent
	_expect(&"descent" in changes, "a state announces itself as descent")
	_expect(bool(state.open) and state.run == "a91c" and state.dungeon == "serpent_deep"
		and state.name == "The Serpent Deep" and state.difficulty == "Hard",
		"the run's identity is kept")
	_expect(int(state.floor) == 3 and int(state.floors) == 6 and state.floor_name == "The Buried Streets"
		and state.section == SECTION, "the floor is kept")
	_expect(state.origin == [ORIGIN.x, ORIGIN.y] and int(state.cell_tiles) == 2
		and int(state.width) == WIDTH and int(state.height) == HEIGHT, "the grid is kept")
	_expect(state.mask == PackedByteArray(MASK_BYTES) and int(state.time_left) == 2345
		and app.descent_anchor_msec > 0, "the explored bits and the clock are kept")

func _check_lookup(grid: Dictionary) -> void:
	_expect(not grid.is_empty() and grid.origin == ORIGIN and grid.section == SECTION,
		"the state gives a fog grid")
	var wrong := 0
	for cy: int in range(HEIGHT):
		for cx: int in range(WIDTH):
			if DescentFog.revealed(grid.mask, WIDTH, cx, cy) != (Vector2i(cx, cy) in REVEALED_CELLS):
				wrong += 1
	_expect(wrong == 0, "every cell reads revealed exactly when its bit (i = cy * width + cx) is set")
	# Two tiles a cell, counted from the origin tile, rounded down.
	for case: Array in [
			[100, 200, DescentFog.REVEALED, "the origin tile is cell (0, 0)"],
			[101, 201, DescentFog.REVEALED, "the cell's far tile is still cell (0, 0)"],
			[102, 200, DescentFog.REVEALED, "two tiles east is cell (1, 0)"],
			[106, 200, DescentFog.UNREVEALED, "cell (3, 0) is unrevealed"],
			[103, 203, DescentFog.REVEALED, "cell (1, 1) is revealed"],
			[100, 202, DescentFog.UNREVEALED, "cell (0, 1) is unrevealed"],
			[107, 205, DescentFog.REVEALED, "cell (3, 2) is revealed"],
			[111, 209, DescentFog.REVEALED, "the far corner tile is cell (5, 4)"],
			[110, 208, DescentFog.REVEALED, "cell (5, 4) from its first tile"],
			[99, 200, DescentFog.OFF_GRID, "a tile west of the origin is off the grid"],
			[100, 199, DescentFog.OFF_GRID, "a tile north of the origin is off the grid"],
			[112, 209, DescentFog.OFF_GRID, "a tile past the last column is off the grid"],
			[100, 210, DescentFog.OFF_GRID, "a tile past the last row is off the grid"]]:
		_expect(DescentFog.tile_state(grid, case[0], case[1]) == case[2], case[3])
	_expect(DescentFog.tile_hidden(grid, 106, 200) and not DescentFog.tile_hidden(grid, 99, 200)
		and DescentFog.tile_revealed(grid, 100, 200),
		"only an unrevealed cell on the grid hides; off the grid is not fog")
	_expect(DescentFog.cell_of(grid, 99, 199) == Vector2i(-1, -1), "cells round down west and north of the origin")

## The Godot point (y = 0) of a grid coordinate: a cell's corner at whole
## numbers, its centre at halves.
func _grid_point(adapter: CoordinateAdapter, cell: Vector2) -> Vector3:
	return adapter.server_to_godot(ORIGIN.x + cell.x * 2.0, ORIGIN.y + cell.y * 2.0, 0.0)

func _check_mesh(grid: Dictionary) -> void:
	var adapter := _adapter()
	var mesh: ArrayMesh = DescentFog.build_mesh(grid, adapter, 0.5)
	_expect(mesh != null and mesh.get_surface_count() == 1, "the fog is one surface: one draw call")
	if mesh == null:
		return
	var arrays := mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	_expect(vertices.size() % 4 == 0 and indices.size() == vertices.size() / 4 * 6, "the fog is built of quads")
	var tops: Array[Rect2] = []
	var sides: Dictionary = {}
	var heights_ok := true
	var facing_ok := true
	for quad: int in range(vertices.size() / 4):
		var corners := vertices.slice(quad * 4, quad * 4 + 4)
		var normal := normals[quad * 4]
		# Normals come back octahedral-compressed: near, not exactly, up.
		if normal.y > 0.9:
			var rect := Rect2(Vector2(corners[0].x, corners[0].z), Vector2.ZERO)
			for corner: Vector3 in corners:
				rect = rect.expand(Vector2(corner.x, corner.z))
				heights_ok = heights_ok and is_equal_approx(corner.y, 0.5 + DescentFog.TOP_METRES)
			tops.append(rect)
			continue
		var low := INF
		var high := -INF
		var ends: Dictionary = {}
		for corner: Vector3 in corners:
			low = minf(low, corner.y)
			high = maxf(high, corner.y)
			ends["%.2f,%.2f" % [corner.x, corner.z]] = Vector2(corner.x, corner.z)
		heights_ok = heights_ok and is_equal_approx(low, 0.5 - DescentFog.BELOW_METRES) \
			and is_equal_approx(high, 0.5 + DescentFog.TOP_METRES)
		var keys: Array = ends.keys()
		keys.sort()
		var key := "|".join(PackedStringArray(keys))
		sides[key] = true
		# A side faces the revealed cell it bounds.
		var middle: Vector2 = (ends[keys[0]] + ends[keys[1]]) * 0.5
		var into := Vector2(normal.x, normal.z) * 0.5
		var inside: Vector2i = adapter.godot_to_server(Vector3(middle.x + into.x, 0, middle.y + into.y))
		facing_ok = facing_ok and DescentFog.tile_revealed(grid, inside.x, inside.y)
	_expect(heights_ok, "tops stand at 7 m over the floor and sides reach from below it to the top")
	_expect(facing_ok, "every side faces the revealed cell beside it")
	var covered_wrong := 0
	for cy: int in range(HEIGHT):
		for cx: int in range(WIDTH):
			var centre := _grid_point(adapter, Vector2(cx + 0.5, cy + 0.5))
			var covered := false
			for rect: Rect2 in tops:
				covered = covered or rect.has_point(Vector2(centre.x, centre.z))
			if covered == (Vector2i(cx, cy) in REVEALED_CELLS):
				covered_wrong += 1
	_expect(covered_wrong == 0, "a top face lies over every unrevealed cell and over no revealed one")
	var outside := _grid_point(adapter, Vector2(-0.5, 0.5))
	var past := false
	for rect: Rect2 in tops:
		past = past or rect.has_point(Vector2(outside.x, outside.z))
	_expect(not past, "no top face reaches off the grid")
	# Expected sides: every cell edge with a revealed cell on exactly one side,
	# the grid's own edge counting as unrevealed.
	var expected: Dictionary = {}
	var is_open := func(cell: Vector2i) -> bool: return cell in REVEALED_CELLS
	for cy: int in range(HEIGHT):
		for cx: int in range(WIDTH + 1):
			if is_open.call(Vector2i(cx - 1, cy)) != is_open.call(Vector2i(cx, cy)):
				expected[_edge_key(adapter, Vector2(cx, cy), Vector2(cx, cy + 1))] = true
	for cy: int in range(HEIGHT + 1):
		for cx: int in range(WIDTH):
			if is_open.call(Vector2i(cx, cy - 1)) != is_open.call(Vector2i(cx, cy)):
				expected[_edge_key(adapter, Vector2(cx, cy), Vector2(cx + 1, cy))] = true
	_expect(sides.size() == expected.size() and sides.keys().all(func(key: String) -> bool: return expected.has(key)),
		"side faces stand exactly on the revealed boundaries, the grid's edge included (%d sides)" % expected.size())
	# The (5, 4) corner cell: walls on its west and north, and on the grid's
	# east and south edges beside it.
	_expect(sides.has(_edge_key(adapter, Vector2(6, 4), Vector2(6, 5)))
		and sides.has(_edge_key(adapter, Vector2(5, 5), Vector2(6, 5))),
		"a revealed cell at the grid's edge is walled on that edge")
	var all_open := grid.duplicate()
	all_open["mask"] = PackedByteArray([0xff, 0xff, 0xff, 0xff])
	var walls: ArrayMesh = DescentFog.build_mesh(all_open, adapter, 0.0)
	var wall_normals: PackedVector3Array = walls.surface_get_arrays(0)[Mesh.ARRAY_NORMAL] if walls != null else PackedVector3Array()
	_expect(walls != null and wall_normals.size() == (WIDTH + HEIGHT) * 2 * 4
		and Array(wall_normals).all(func(normal: Vector3) -> bool: return absf(normal.y) < 0.1),
		"a fully explored floor has no top, only the walls round the grid's edge")
	var none_open := grid.duplicate()
	none_open["mask"] = PackedByteArray([0, 0, 0, 0])
	var dark: ArrayMesh = DescentFog.build_mesh(none_open, adapter, 0.0)
	var dark_vertices: PackedVector3Array = dark.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] if dark != null else PackedVector3Array()
	_expect(dark != null and dark_vertices.size() == HEIGHT * 4,
		"an unexplored floor is one top quad a row and no sides")
	var black := DescentFog.material()
	_expect(black.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED and black.albedo_color == Color.BLACK
		and black.cull_mode == BaseMaterial3D.CULL_DISABLED
		and black.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED,
		"the fog is plain opaque unshaded black, seen from either side")

func _edge_key(adapter: CoordinateAdapter, a: Vector2, b: Vector2) -> String:
	var keys: Array[String] = []
	for cell: Vector2 in [a, b]:
		var point := _grid_point(adapter, cell)
		keys.append("%.2f,%.2f" % [point.x, point.z])
	keys.sort()
	return "|".join(PackedStringArray(keys))

func _check_image(grid: Dictionary) -> void:
	var adapter := _adapter()
	var picture := DescentFog.image(grid, adapter)
	_expect(picture != null and picture.get_width() == WIDTH and picture.get_height() == HEIGHT,
		"the map fog is one pixel a cell")
	if picture == null:
		return
	var wrong := 0
	for cy: int in range(HEIGHT):
		for cx: int in range(WIDTH):
			# Image y runs along Godot +Z, which is south: the grid's first row
			# (northmost) is the image's last.
			var pixel := picture.get_pixel(cx, HEIGHT - 1 - cy)
			var open := Vector2i(cx, cy) in REVEALED_CELLS
			if (open and pixel.a != 0.0) or (not open and (pixel.a != 1.0 or pixel.r != 0.0)):
				wrong += 1
	_expect(wrong == 0, "the map fog is opaque black over unrevealed cells and clear over revealed ones")
	var extent := DescentFog.extent(grid, adapter)
	_expect(extent.position.is_equal_approx(Vector2(100, 630)) and extent.size.is_equal_approx(Vector2(12, 10)),
		"the map fog covers the floor's rectangle in metres (%s)" % str(extent))

## SecretSections hides by the fog in its own culling pass, with and without
## sections, and gives the nodes back when the fog lifts.
func _check_sections_cull(grid: Dictionary) -> void:
	var adapter := _adapter()
	var world := Node3D.new()
	root.add_child(world)
	var fog_volume := MeshInstance3D.new()
	fog_volume.name = "DescentFog"
	fog_volume.add_to_group(SectionsScript.EXEMPT_GROUP)
	fog_volume.position = _grid_point(adapter, Vector2(3, 2.5))
	world.add_child(fog_volume)
	var floor_mesh := MeshInstance3D.new()
	floor_mesh.name = "Walk_%s_stone" % SECTION
	world.add_child(floor_mesh)
	var manifest := WorldManifest.new()
	manifest.data = {"sectioned": true, "sections": [{"id": SECTION, "bounds": {"min": [90, 620], "max": [120, 650]}}]}
	var sections = SectionsScript.new()
	_expect(sections.configure(manifest, world) == 1, "the fog volume is never sorted into a section")
	sections.update(_grid_point(adapter, Vector2(0.5, 0.5)), true)
	var hidden_node := Node3D.new()
	hidden_node.set_meta("tile", Vector2i(106, 200))
	hidden_node.position = adapter.tile_center(106, 200)
	var shown_node := Node3D.new()
	shown_node.set_meta("tile", Vector2i(100, 200))
	shown_node.position = adapter.tile_center(100, 200)
	world.add_child(hidden_node)
	world.add_child(shown_node)
	var predicate := func(node: Node3D) -> bool:
		var tile: Vector2i = node.get_meta("tile")
		return DescentFog.tile_hidden(grid, tile.x, tile.y)
	sections.fog_hides = predicate
	sections.cull_dynamic([hidden_node, shown_node])
	_expect(not hidden_node.visible and shown_node.visible, "the fog hides a node on an unrevealed cell in its section")
	sections.fog_hides = Callable()
	sections.cull_dynamic([hidden_node, shown_node])
	_expect(hidden_node.visible and shown_node.visible, "a lifted fog shows it again on the next pass")
	var plain = SectionsScript.new()
	plain.configure(WorldManifest.new(), world)
	plain.fog_hides = predicate
	plain.cull_dynamic([hidden_node, shown_node])
	_expect(not hidden_node.visible and shown_node.visible, "the fog hides on a map without sections too")
	plain.fog_hides = Callable()
	plain.restore_dynamic()
	_expect(hidden_node.visible, "restoring after the fog shows what it hid")
	_expect(fog_volume.visible, "the culling never touches the fog volume")
	world.queue_free()

## Main: the state builds the volume, the picture and the culling test, and a
## closed state takes all three away.
func _check_main(app: Node) -> void:
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var adapter := _adapter()
	main.adapter = adapter
	var manifest := WorldManifest.new()
	manifest.data = {"sectioned": true, "sections": [{"id": SECTION,
		"bounds": {"min": [90, 620], "max": [120, 650]}}]}
	main.world_loader.manifest = manifest
	app.authenticated = true
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(_state()))
	var volume: MeshInstance3D = main._descent_fog_node
	_expect(is_instance_valid(volume) and volume.get_parent() == main.world_root and volume.mesh != null
		and volume.visible and volume.is_in_group(SectionsScript.EXEMPT_GROUP),
		"a descent state stands the fog volume under the world root")
	_expect(not main._descent_fog_picture.is_empty()
		and main.minimap_background._pictures.any(func(row: Dictionary) -> bool:
			return row.texture == main._descent_fog_picture.texture)
		and main.full_map_background._pictures.any(func(row: Dictionary) -> bool:
			return row.texture == main._descent_fog_picture.texture),
		"the fog picture lies on the minimap and the full map")
	_expect(main.secret_sections.fog_hides.is_valid(), "the culling pass hides by the fog")
	var built_mesh: Mesh = volume.mesh if is_instance_valid(volume) else null
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		_bytes(_state(EXPLORED, {"time_left": 2344})))
	_expect(is_instance_valid(volume) and volume.mesh == built_mesh, "a clock tick does not rebuild the fog")
	# Objects and creatures in the fog: hidden, not marked and not clicked.
	var chest := MapObject3D.new()
	chest.server_tile = Vector2i(106, 200)
	var open_chest := MapObject3D.new()
	open_chest.server_tile = Vector2i(100, 200)
	_expect(main._descent_fog_hides(chest) and not main._descent_fog_hides(open_chest),
		"an object on an unrevealed cell is in the fog")
	var creature := ReplicatedActor3D.new()
	creature.actor_id = 9001
	var player := ReplicatedActor3D.new()
	player.actor_id = 9002
	var companion := ReplicatedActor3D.new()
	companion.actor_id = 9003
	app.actors[9001] = {"kind": ReplicatedActor3D.CREATURE_ACTOR_KIND, "x": 106, "y": 200, "name": "Cave Rat"}
	app.actors[9002] = {"kind": 1, "x": 106, "y": 200, "name": "Rowan"}
	app.actors[9003] = {"kind": 2, "x": 106, "y": 200, "name": "Bramble"}
	main._descent_party_names = {"bramble": true}
	_expect(main._descent_fog_hides(creature), "a creature on an unrevealed cell is in the fog")
	_expect(not main._descent_fog_hides(player) and not main._descent_fog_hides(companion),
		"players and party members are never hidden by the fog")
	app.actors[9001]["x"] = 100
	_expect(not main._descent_fog_hides(creature), "a creature on a revealed cell is seen")
	var marks: Array[Dictionary] = main._without_fogged_marks([
		{"position": adapter.tile_center(106, 200), "type": &"npc"},
		{"position": adapter.tile_center(100, 200), "type": &"npc"},
		{"position": adapter.tile_center(99, 200), "type": &"player"}])
	_expect(marks.size() == 2 and marks[0].position == adapter.tile_center(100, 200),
		"marks on unrevealed cells are left off the maps")
	chest.collision_layer = MapObject3D.PICK_LAYER
	chest.position = adapter.tile_center(106, 200)
	main.world_root.add_child(chest)
	chest.add_child(_pick_shape())
	main.map_object_nodes[59500] = chest
	main.secret_sections.cull_dynamic([chest])
	_expect(not chest.visible, "the culling pass hides an object in the fog")
	await physics_frame
	await physics_frame
	var screen := _aim(main, chest)
	_expect(main._pick_map_object(screen) == null, "an object in the fog cannot be clicked")
	# Reveal the chest's cell: (3, 0) is i3, bit 3 of byte 0.
	var revealed := PackedByteArray(MASK_BYTES)
	revealed[0] |= 1 << 3
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		_bytes(_state(Marshalls.raw_to_base64(revealed))))
	main.secret_sections.cull_dynamic([chest])
	screen = _aim(main, chest)
	_expect(chest.visible and main._pick_map_object(screen) == chest,
		"once its cell is revealed the object shows and can be clicked")
	# Another map that lacks the floor's section draws no fog from the state.
	var other := WorldManifest.new()
	other.data = {"sectioned": true, "sections": [{"id": "landfall_town_square", "bounds": {"min": [0, 0], "max": [10, 10]}}]}
	main.world_loader.manifest = other
	main._sync_descent_fog()
	_expect(main._descent_fog_node == null and main._descent_fog_picture.is_empty(),
		"a map without the floor's section draws no fog")
	main.world_loader.manifest = manifest
	main._sync_descent_fog()
	_expect(is_instance_valid(main._descent_fog_node), "the fog comes back on the descent's map")
	volume = main._descent_fog_node
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		_bytes({"version": 1, "kind": "state", "open": false}))
	_expect(main._descent_fog_node == null and (not is_instance_valid(volume) or volume.is_queued_for_deletion()),
		"leaving the descent removes the fog volume")
	_expect(main._descent_fog_picture.is_empty()
		and main.minimap_background._pictures.size() == main.full_map_background._pictures.size()
		and not main.minimap_background._pictures.any(func(row: Dictionary) -> bool:
			return row.texture is ImageTexture and (row.texture as ImageTexture).get_width() == WIDTH),
		"leaving the descent removes the map fog")
	_expect(not main.secret_sections.fog_hides.is_valid(), "leaving the descent stops the fog culling")
	main.secret_sections.cull_dynamic([chest])
	_expect(chest.visible, "an object the fog hid is shown again")
	main.map_object_nodes.erase(59500)
	chest.queue_free()
	open_chest.free()
	for actor: ReplicatedActor3D in [creature, player, companion]:
		actor.free()
	for actor_id: int in [9001, 9002, 9003]:
		app.actors.erase(actor_id)
	app.authenticated = false
	main.queue_free()
	await process_frame

## Puts the gameplay camera over `target` and returns where it is on screen.
func _aim(main: Control, target: Node3D) -> Vector2:
	var camera: Camera3D = main.camera_rig.get_node("Camera")
	camera.global_position = target.global_position + Vector3(0, 18, 0.01)
	camera.look_at(target.global_position)
	return camera.unproject_position(target.global_position + Vector3.UP * 0.5)

func _pick_shape() -> CollisionShape3D:
	var shape := CollisionShape3D.new()
	var cylinder := CylinderShape3D.new()
	cylinder.radius = 0.9
	cylinder.height = 1.2
	shape.shape = cylinder
	shape.position.y = 0.6
	return shape

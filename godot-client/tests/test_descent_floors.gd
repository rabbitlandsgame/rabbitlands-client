extends SceneTree
## Procedural descent floors (descent_layout_v1, server message 188 `kind`
## "layout"): the layout as the protocol decodes it and AppState keeps it, the
## floor DescentFloorBuilder builds from it - a walk surface that is the
## server's walk grid, rock faces and stair mouths named and registered for the
## cutaway, lamps as light markers, the map picture - DescentFloors keeping one
## run's floors on the frame and in its manifest, and Main showing them.
## The layouts are three floors of one server-generated run
## (tests/fixtures/descent_layouts.json).

const Builder := preload("res://src/world/descent_floor_builder.gd")
const Floors := preload("res://src/world/descent_floors.gd")
const DescentFog := preload("res://src/world/descent_fog.gd")
const FIXTURE := "res://tests/fixtures/descent_layouts.json"
const FRAME := "res://../eloria-assets/maps/continent-v2/serpent_deep_descent/client/world.json"
const OPEN := [1, 2, 3]

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

func _bytes(value: Dictionary) -> PackedByteArray:
	return JSON.stringify(value).to_utf8_buffer()

func _decode(value: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_server(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(value))

func _adapter() -> CoordinateAdapter:
	return CoordinateAdapter.new({"metresPerTile": 1.0, "origin": [0.0, 0.0, 0.0],
		"serverOrigin": [0.0, 512.0], "invertServerY": true, "walkingHeight": 0.0})

func _fixtures() -> Array:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FIXTURE))
	return data.layouts

func _run() -> void:
	create_timer(300).timeout.connect(func() -> void:
		push_error("FAIL: descent floors test timed out")
		quit(1))
	root.size = Vector2i(1280, 720)
	var raw: Array = _fixtures()
	var decoded: Array[Dictionary] = []
	for layout: Dictionary in raw:
		var event := _decode(layout)
		_expect(event.get("type") == "descent_layout", "floor %d's layout decodes" % int(layout.floor))
		decoded.append(event.get("data", {}))
	_check_decoding(raw)
	for layout: Dictionary in decoded:
		await _check_floor(layout)
	_check_manager(decoded)
	var app: Node = root.get_node("AppState")
	_check_state(app, raw)
	await _check_main(app, raw)
	print("descent floors checks: %d, failures: %d" % [checks, failures])
	quit(failures)

func _check_decoding(raw: Array) -> void:
	var good: Dictionary = raw[0]
	var data: Dictionary = _decode(good).data
	_expect(data.cells is PackedByteArray and (data.cells as PackedByteArray).size() == int(good.width) * int(good.height)
		and data.origin == [int(good.origin[0]), int(good.origin[1])] and data.section == "serpent_deep_f1"
		and data.theme == "catacomb",
		"the cells come back decoded, one code a cell, with the floor's place and theme")
	_expect((data.stairs as Array).size() == 2 and (data.props as Array).size() == (good.props as Array).size(),
		"its stairs and kit pieces come through")
	for broken: Dictionary in [{"cells": "AAAA"}, {"cells": "not base64!"}, {"width": 0},
			{"section": ""}, {"origin": [-1, 0]},
			{"stairs": [{"way": "sideways", "x": 1, "y": 1, "facing": [1, 0]}]},
			{"stairs": [{"way": "up", "x": 1, "y": 1, "facing": [1, 1]}]},
			{"props": [{"asset": 3, "x": 1, "y": 1}]}]:
		var bad := good.duplicate(true)
		bad.merge(broken, true)
		_expect(_decode(bad).get("type") == "invalid", "a layout with %s is refused" % JSON.stringify(broken))

## The floor `layout` builds, checked against the grid it came from.
func _check_floor(layout: Dictionary) -> void:
	var adapter := _adapter()
	var themes := Builder.load_themes()
	var section := str(layout.section)
	var started := Time.get_ticks_msec()
	var built := Builder.build(layout, themes, adapter, false)
	var took := Time.get_ticks_msec() - started
	_expect(not built.is_empty() and (built.root as Node3D).name == "Section_%s_floor" % section,
		"%s builds (%d ms, shell only)" % [section, took])
	var floor_root: Node3D = built.root
	var walk := floor_root.get_node_or_null("Walk_%s_floor" % section) as MeshInstance3D
	var body := walk.get_child(0) as StaticBody3D if walk != null and walk.get_child_count() > 0 else null
	_expect(walk != null and walk.mesh != null and body != null and body.collision_layer == 8
		and (body.get_child(0) as CollisionShape3D).shape is ConcavePolygonShape3D,
		"%s has a Walk_ floor with a layer 8 walk collider" % section)
	# The cutaway knows every rock face and stair mouth, by the bake's names.
	var faces := 0
	var mouths := 0
	for wall: Dictionary in built.walls:
		var node := floor_root.find_child(str(wall.node), true, false) as MeshInstance3D
		var facing := str(wall.node).get_slice("_", str(wall.node).get_slice_count("_") - 1)
		if facing.begins_with("mouth"):
			mouths += 1
		elif node != null and Vector3(wall.outward[0], 0, wall.outward[2]) == Builder.FACE_OUT[facing]:
			faces += 1
		_expect(node != null and wall.section == section, "%s: %s stands under the floor" % [section, wall.node])
	_expect(faces == 4, "%s registers a rock face for each of the four facings" % section)
	_expect(mouths == (layout.stairs as Array).size(), "%s registers a mouth for each stair" % section)
	# Lamps are light markers at their flames.
	var lamps := 0
	for prop: Dictionary in layout.props:
		if str(prop.asset) in ["candle_stake", "incense_brazier"]:
			lamps += 1
	_expect((built.markers as Array).size() == lamps and lamps > 0
		and (built.markers as Array).all(func(m: Dictionary) -> bool: return float(m.position[1]) > 1.0),
		"%s lights each of its %d lamps" % [section, lamps])
	# The map picture: two pixels a metre over the floor's rectangle.
	var picture: Image = built.picture
	var width := int(layout.width)
	var height := int(layout.height)
	_expect(picture != null and picture.get_size() == Vector2i(width * 4, height * 4)
		and built.extent == DescentFog.extent({"origin": Vector2i(layout.origin[0], layout.origin[1]),
			"cell_tiles": 2, "width": width, "height": height}, adapter),
		"%s draws its map picture over its own rectangle" % section)
	# The walk surface is the server's walk grid: every open tile outside the
	# wells has floor at 0 m under it, wells and solid rock have none.
	var world := Node3D.new()
	root.add_child(world)
	world.add_child(floor_root)
	await physics_frame
	await physics_frame
	var space := world.get_world_3d().direct_space_state
	var cells: PackedByteArray = layout.cells
	var wells := {}
	for stair: Dictionary in layout.stairs:
		wells[Vector2i(int(stair.x) / 2 + int(stair.facing[0]), int(stair.y) / 2 + int(stair.facing[1]))] = true
	var origin := Vector2i(int(layout.origin[0]), int(layout.origin[1]))
	var missed := 0
	var stray := 0
	var walked := 0
	for cy: int in range(height):
		for cx: int in range(width):
			var code := cells[cy * width + cx]
			var deep_rock := code == 0
			for oy: int in [-1, 0, 1]:
				for ox: int in [-1, 0, 1]:
					var near := Vector2i(cx + ox, cy + oy)
					if near.x >= 0 and near.y >= 0 and near.x < width and near.y < height \
							and cells[near.y * width + near.x] != 0:
						deep_rock = false
			if not (code in OPEN or wells.has(Vector2i(cx, cy)) or deep_rock):
				continue
			for ty: int in [cy * 2, cy * 2 + 1]:
				for tx: int in [cx * 2, cx * 2 + 1]:
					var at := adapter.tile_center(origin.x + tx, origin.y + ty)
					var query := PhysicsRayQueryParameters3D.create(at + Vector3.UP * 20, at + Vector3.DOWN * 20, 8)
					var hit := space.intersect_ray(query)
					if code in OPEN and not wells.has(Vector2i(cx, cy)):
						walked += 1
						if hit.is_empty() or absf((hit.position as Vector3).y) > 0.01:
							missed += 1
					elif not hit.is_empty():
						stray += 1
	_expect(walked > 500 and missed == 0, "%s: all %d open tiles stand on the walk floor (%d missed)" % [section, walked, missed])
	_expect(stray == 0, "%s: no walk floor over a stair's well or solid rock (%d stray)" % [section, stray])
	world.queue_free()

func _check_manager(decoded: Array[Dictionary]) -> void:
	var manifest := WorldManifest.load_file(FRAME)
	_expect(manifest != null and manifest.errors.is_empty() and Floors.applies(manifest),
		"the Serpent Deep's package is a procedural descent frame")
	var sections: Array = (manifest.data.sections as Array).map(func(s: Dictionary) -> String: return str(s.id))
	_expect(sections == ["serpent_deep_f1", "serpent_deep_f2", "serpent_deep_f3", "serpent_deep_f4",
		"serpent_deep_f5", "serpent_deep_f6"], "the frame declares one section a floor")
	for layout: Dictionary in decoded:
		_expect(DescentFog.applies_to(manifest.data, str(layout.section)), "%s's fog applies on the frame" % layout.section)
		var bounds: Dictionary = (manifest.data.sections as Array).filter(func(s: Dictionary) -> bool:
			return s.id == layout.section)[0].bounds
		var extent: Rect2 = DescentFog.extent({"origin": Vector2i(layout.origin[0], layout.origin[1]),
			"cell_tiles": 2, "width": int(layout.width), "height": int(layout.height)}, _adapter())
		_expect(Rect2(Vector2(bounds.min[0], bounds.min[1]), Vector2(bounds.max[0] - bounds.min[0],
			bounds.max[1] - bounds.min[1])) == extent, "%s's section is where the server places its floor" % layout.section)
	var frame := Node3D.new()
	root.add_child(frame)
	var floors: RefCounted = Floors.new()
	var layouts := {str(decoded[0].section): decoded[0]}
	_expect(floors.sync(frame, manifest, _adapter(), layouts, "f1x7", false), "a run's first layout builds")
	var node := frame.get_node_or_null(Floors.NODE_NAME)
	_expect(node != null and str(node.get_meta("run")) == "f1x7" and node.get_child_count() == 1,
		"the floors stand under the frame, marked with their run")
	var walls := (manifest.data.cutaway.walls as Array).filter(func(w: Dictionary) -> bool:
		return bool(w.get(Floors.RUNTIME_KEY, false)))
	var markers := (manifest.data.lighting.markers as Array).filter(func(m: Dictionary) -> bool:
		return bool(m.get(Floors.RUNTIME_KEY, false)))
	_expect(walls.size() >= 6 and markers.size() > 0, "its walls and lamps join the frame's cutaway and lights")
	_expect(not floors.sync(frame, manifest, _adapter(), layouts, "f1x7", false), "the same layouts change nothing")
	layouts[str(decoded[1].section)] = decoded[1]
	_expect(floors.sync(frame, manifest, _adapter(), layouts, "f1x7", false) and node.get_child_count() == 2
		and not (floors.picture(str(decoded[1].section)) as Dictionary).is_empty(), "a second floor joins the first")
	_expect(floors.sync(frame, manifest, _adapter(), {str(decoded[0].section): decoded[0]}, "z9q2", false)
		and frame.get_node(Floors.NODE_NAME) != node
		and frame.get_node(Floors.NODE_NAME).get_child_count() == 1, "another run's layout throws the last run's floors away")
	_expect(floors.sync(frame, manifest, _adapter(), {}, "", false)
		and frame.get_node_or_null(Floors.NODE_NAME) == null
		and (manifest.data.cutaway.walls as Array).all(func(w: Dictionary) -> bool: return not w.has(Floors.RUNTIME_KEY))
		and (manifest.data.lighting.markers as Array).all(func(m: Dictionary) -> bool: return not m.has(Floors.RUNTIME_KEY)),
		"leaving the descent clears the floors and the manifest's runtime entries")
	frame.queue_free()

func _check_state(app: Node, raw: Array) -> void:
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(raw[0]))
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(raw[1]))
	_expect(app.descent_layout_run == "f1x7" and app.descent_layouts.size() == 2
		and app.descent_layouts.has("serpent_deep_f1"), "AppState keeps a run's layouts by section")
	var other: Dictionary = raw[2].duplicate(true)
	other.run = "z9q2"
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(other))
	_expect(app.descent_layout_run == "z9q2" and app.descent_layouts.keys() == ["serpent_deep_f6"],
		"another run's layout replaces the last run's")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		_bytes({"version": 1, "kind": "state", "open": false}))
	_expect(app.descent_layouts.is_empty() and app.descent_layout_run.is_empty(), "leaving the descent forgets them")
	_expect("descent_layout_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "the client declares descent_layout_v1")

## Main builds the floors of a loaded frame when their layouts arrive, then
## lights them, cuts them away, sorts them into sections and draws their map
## picture.
func _check_main(app: Node, raw: Array) -> void:
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.adapter = _adapter()
	var manifest := WorldManifest.load_file(FRAME)
	var map_root := Node3D.new()
	map_root.name = "serpent_deep_frame"
	main.world_loader.add_child(map_root)
	main.world_loader.world_root = map_root
	main.world_loader.manifest = manifest
	main._descent_bound_manifest = manifest
	app.current_map = "serpent_deep_descent"
	main.loaded_server_map = "serpent_deep_descent"
	app.authenticated = true
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(raw[0]))
	var floors := map_root.get_node_or_null(Floors.NODE_NAME)
	_expect(floors != null and floors.has_node("Section_serpent_deep_f1_floor"),
		"a layout arriving on the loaded frame builds its floor")
	_expect(main.map_light_root != null and main.map_light_root.get_child_count() > 0, "its lamps burn")
	_expect(int(main.interior_cutaway.call("configure", manifest, main.world_root)) > 0,
		"its faces are cutaway walls")
	var state := {"version": 1, "kind": "state", "open": true, "run": "f1x7", "dungeon": "serpent_deep",
		"name": "The Serpent Deep", "difficulty": "Hard", "floor": 1, "floors": 6,
		"floor_name": "The Ossuary Stair", "section": "serpent_deep_f1", "origin": raw[0].origin,
		"cell_tiles": 2, "width": raw[0].width, "height": raw[0].height,
		"explored": Marshalls.raw_to_base64(_bits(int(raw[0].width) * int(raw[0].height))),
		"time_left": 3000, "boss": ""}
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE, _bytes(state))
	_expect(not main._descent_fog_grid.is_empty(), "the floor's fog applies on the frame")
	main.secret_sections.call("update", main.adapter.tile_center(int(raw[0].origin[0]) + 20, int(raw[0].origin[1]) + 20), true)
	main._install_map_picture(manifest)
	_expect(not main._map_picture.is_empty() and main._map_picture.texture is ImageTexture,
		"the minimap and full map show the floor's own picture")
	app._on_packet(EloriaProtocol.ServerMessage.ELORIA_DESCENT_STATE,
		_bytes({"version": 1, "kind": "state", "open": false}))
	_expect(map_root.get_node_or_null(Floors.NODE_NAME) == null, "leaving the descent takes its floors away")
	main.queue_free()
	await process_frame

func _bits(count: int) -> PackedByteArray:
	var bits := PackedByteArray()
	bits.resize((count + 7) / 8)
	bits[0] = 1
	return bits

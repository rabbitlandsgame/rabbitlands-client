extends SceneTree
## Actors on the maps adjoining the player's across a land seam render like the
## actors of the player's own map: their packets carry the neighbour's handle in
## the stock "z" field, the state tags them with the neighbour's name once, and
## Main places them through the neighbour's adapter carried by the frame its
## resident scene stands in. A seamless crossing keeps every actor. The Tab map
## and the minimap draw the region's own picture on a map-only layer.

var failures: int = 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_protocol()
	_framed_adapter()
	_map_picture_geometry()
	await _state_and_main()
	print("test_adjacent_actors failures=%d" % failures)
	quit(failures)

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: " + message)

## Whether a flat mesh's bounds cover `extent` on X and Z at `height`, within
## the tolerance a mesh AABB carries (a flat surface may be padded a little).
static func _spans(aabb: AABB, extent: Rect2, height: float) -> bool:
	return (absf(aabb.position.x - extent.position.x) < 0.05 and absf(aabb.position.z - extent.position.y) < 0.05
		and absf(aabb.end.x - extent.end.x) < 0.05 and absf(aabb.end.z - extent.end.y) < 0.05
		and absf(aabb.position.y - height) < 0.05 and aabb.size.y < 0.05)

static func _u16(value: int) -> PackedByteArray:
	return PackedByteArray([value & 0xff, (value >> 8) & 0xff])

## A stock ADD_NEW_ACTOR payload with `handle` in the "z" field.
static func _creature_payload(actor_id: int, x: int, y: int, handle: int, actor_name: String) -> PackedByteArray:
	var payload := PackedByteArray()
	payload.append_array(_u16(actor_id))
	payload.append_array(_u16(x))
	payload.append_array(_u16(y))
	payload.append_array(_u16(handle))
	payload.append_array(_u16(0))          # rotation
	payload.append(6)                      # actor type
	payload.append(0)                      # frame
	payload.append_array(_u16(50))         # max health
	payload.append_array(_u16(50))         # health
	payload.append(1)                      # kind
	payload.append_array(actor_name.to_ascii_buffer())
	payload.append(0)
	return payload

static func _adjacent_payload(entries: Dictionary) -> PackedByteArray:
	var payload := PackedByteArray([entries.size()])
	for handle: Variant in entries:
		payload.append_array(_u16(int(handle)))
		payload.append_array(str(entries[handle]).to_ascii_buffer())
		payload.append(0)
	return payload

func _protocol() -> void:
	var maps: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_ADJACENT_MAPS,
		_adjacent_payload({1: "whitehorn_range", 2: "grey_moors"}))
	_expect(maps.get("type") == "adjacent_maps" and maps.get("maps", {}).get(1) == "whitehorn_range"
		and maps.get("maps", {}).get(2) == "grey_moors", "ELORIA_ADJACENT_MAPS decodes handle -> map name")
	var bad: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ELORIA_ADJACENT_MAPS, PackedByteArray([1, 1, 0]))
	_expect(bad.get("type") == "invalid", "a truncated handle table is invalid, not a crash")
	var creature: Dictionary = EloriaProtocol.decode_server(
		EloriaProtocol.ServerMessage.ADD_NEW_ACTOR, _creature_payload(1000, 100, 120, 1, "Hound"))
	_expect(creature.get("type") == "actor_spawn" and int(creature.get("map_handle", -1)) == 1
		and int(creature.get("x", 0)) == 100 and int(creature.get("y", 0)) == 120,
		"an actor packet's stock z field decodes as the map handle without disturbing the tile")
	_expect("adjacent_actors_v1" in EloriaProtocol.CLIENT_CAPABILITIES,
		"the client advertises adjacent_actors_v1")

func _framed_adapter() -> void:
	var base := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [10, 20],
		"invertServerY": true, "walkingHeight": 5.0, "origin": [0, 0, 0]})
	var frame := Transform3D(Basis(Vector3.UP, PI / 2.0), Vector3(100.0, 2.0, 50.0))
	var framed := FramedCoordinateAdapter.wrap(base, frame)
	var expected: Vector3 = frame * base.tile_center(12, 22)
	_expect(framed.tile_center(12, 22).is_equal_approx(expected),
		"a neighbour tile is placed through the neighbour's adapter and then its frame")
	_expect(framed.footprint_center(12, 22, Vector2i(2, 2)).is_equal_approx(frame * base.footprint_center(12, 22, Vector2i(2, 2))),
		"footprint centres ride the frame too")
	_expect(framed.godot_to_server(expected) == Vector2i(12, 22),
		"the inverse undoes the frame before the neighbour's own conversion")
	_expect(is_equal_approx(framed.rotation_to_godot(0), base.rotation_to_godot(0) + PI / 2.0),
		"rotations gain the frame's yaw")
	_expect(is_equal_approx(framed.fallback_height(), 7.0),
		"the fallback height is the neighbour's walking height where the frame puts it")
	_expect(is_equal_approx(base.fallback_height(), 5.0), "a plain adapter falls back to its walking height")

func _map_picture_geometry() -> void:
	var minimap := {"worldMin": [-224.0, -246.0], "worldMax": [232.0, 346.0], "pixelsPerMetre": 1,
		"bounds": {"min": [-224.0, -23.0, -246.0], "max": [232.0, 289.6, 346.0]}}
	var whole := MapPicture.extent(minimap, {"region": [0, 0, 456, 592]})
	_expect(whole.is_equal_approx(Rect2(-224.0, -246.0, 456.0, 592.0)),
		"the picture covers the region's minimap frame")
	var cropped := MapPicture.extent(minimap, {"region": [10, 20, 100, 200]})
	_expect(cropped.is_equal_approx(Rect2(-214.0, -226.0, 100.0, 200.0)),
		"a cartography crop maps back to world metres")
	_expect(MapPicture.extent({}, {}) == Rect2(), "a map without a minimap frame has no picture extent")
	_expect(is_equal_approx(MapPicture.height_below({"minimap": minimap}), -24.0),
		"the picture lies a metre under the lowest ground")
	var texture := ImageTexture.create_from_image(Image.create(4, 4, false, Image.FORMAT_RGB8))
	var picture := MapPicture.build(texture, whole, -24.0, 8)
	var aabb := picture.mesh.get_aabb()
	_expect(picture.layers == 8 and picture.name == "MapPicture", "the picture stands on the map layer")
	_expect(_spans(aabb, whole, -24.0), "the quad spans the extent at the given height (%s)" % aabb)
	var mesh := picture.mesh as ArrayMesh
	var arrays: Array = mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	_expect(vertices[0].z < vertices[3].z and uvs[0].y < uvs[3].y,
		"the top row of the picture lies at the north edge")
	picture.free()

func _state_and_main() -> void:
	var scene_resource: Resource = load("res://src/app/main.tscn")
	_expect(scene_resource is PackedScene, "main scene loads")
	if not scene_resource is PackedScene:
		return
	var main: Control = (scene_resource as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var app_state: Node = root.get_node("AppState")
	# The server names the map, then the neighbours' handles, then the actors.
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.CHANGE_MAP, "amberwood".to_ascii_buffer() + PackedByteArray([0]))
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_ADJACENT_MAPS, _adjacent_payload({1: "whitehorn_range"}))
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_NEW_ACTOR, _creature_payload(1000, 100, 120, 1, "Hound"))
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.ADD_NEW_ACTOR, _creature_payload(1001, 30, 40, 0, "Stag"))
	var actors: Dictionary = app_state.get("actors")
	_expect(str(actors.get(1000, {}).get("map", "")) == "whitehorn_range",
		"an actor with a neighbour handle is tagged with the neighbour's map")
	_expect(str(actors.get(1001, {}).get("map", "")) == "amberwood",
		"an actor with handle 0 is tagged with the map the client stands on")
	# A seamless crossing: the server changes the map without KILL_ALL_ACTORS.
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.CHANGE_MAP, "whitehorn_range".to_ascii_buffer() + PackedByteArray([0]))
	actors = app_state.get("actors")
	_expect(actors.has(1000) and actors.has(1001) and str(actors[1000].get("map")) == "whitehorn_range",
		"a change of map keeps the actors and their tags")
	_expect((app_state.get("adjacent_maps") as Dictionary).is_empty(), "the old handle table is dropped at a change of map")
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.KILL_ALL_ACTORS, PackedByteArray())
	_expect((app_state.get("actors") as Dictionary).is_empty(), "KILL_ALL_ACTORS still empties the table")
	# Main places a neighbour's actor through the resident frame.
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.CHANGE_MAP, "amberwood".to_ascii_buffer() + PackedByteArray([0]))
	var active := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [0, 0], "invertServerY": true, "walkingHeight": 1.0})
	main.set("adapter", active)
	var neighbour_root := Node3D.new()
	neighbour_root.transform = Transform3D(Basis(Vector3.UP, PI / 2.0), Vector3(700.0, 0.0, -20.0))
	root.add_child(neighbour_root)
	var neighbour_manifest := WorldManifest.new()
	neighbour_manifest.data = {"schemaVersion": "1.0", "asset": {"id": "whitehorn_range", "origin": [0, 0, 0]},
		"coordinateTransform": {"metresPerTile": 1.0, "serverOrigin": [362, 186], "invertServerY": true, "walkingHeight": 3.0, "origin": [0, 0, 0]},
		"minimap": {"worldMin": [-362.0, -522.0], "worldMax": [346.0, 186.0], "pixelsPerMetre": 1, "northUp": true,
			"bounds": {"min": [-362.0, -22.0, -522.0], "max": [346.0, 176.0, 186.0]}}}
	var stream: Node = main.get("exterior_stream")
	(stream.get("residents") as Dictionary)["whitehorn_range"] = {"root": neighbour_root, "manifest": neighbour_manifest}
	var own: CoordinateAdapter = main.call("_adapter_for_actor", {"map": "amberwood"})
	_expect(own == active, "an actor on the client's own map uses the active adapter")
	var framed: CoordinateAdapter = main.call("_adapter_for_actor", {"map": "whitehorn_range"})
	_expect(framed is FramedCoordinateAdapter, "an actor on a resident neighbour gets a framed adapter")
	if framed is FramedCoordinateAdapter:
		var expected: Vector3 = neighbour_root.transform * neighbour_manifest.coordinate_adapter().tile_center(192, 93)
		_expect(framed.tile_center(192, 93).is_equal_approx(expected),
			"the neighbour's tile lands where its resident scene stands")
		var again: CoordinateAdapter = main.call("_adapter_for_actor", {"map": "whitehorn_range"})
		_expect(again == framed, "the framed adapter is reused while the root stands still")
		neighbour_root.transform = neighbour_root.transform.translated(Vector3(1, 0, 0))
		var moved: CoordinateAdapter = main.call("_adapter_for_actor", {"map": "whitehorn_range"})
		_expect(moved != framed and moved.tile_center(192, 93).is_equal_approx(expected + Vector3(1, 0, 0)),
			"a moved root rebuilds the framed adapter")
	_expect(main.call("_adapter_for_actor", {"map": "grey_moors"}) == null,
		"an actor on a neighbour that is not resident waits for its ground")
	# The map picture: the current region's own picture on the map layer, and the
	# map cameras render that layer alone; a map without a picture keeps the live render.
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.CHANGE_MAP, "mirrorhold".to_ascii_buffer() + PackedByteArray([0]))
	var manifest := WorldManifest.new()
	manifest.data = {"schemaVersion": "1.0", "asset": {"id": "mirrorhold", "origin": [0, 0, 0]},
		"minimap": {"worldMin": [-224.0, -246.0], "worldMax": [232.0, 346.0], "pixelsPerMetre": 1, "northUp": true,
			"bounds": {"min": [-224.0, -23.0, -246.0], "max": [232.0, 289.6, 346.0]}}}
	main.call("_install_map_picture", manifest)
	var picture: Variant = main.get("_map_picture")
	var map_camera: Camera3D = main.get("map_camera")
	var full_map_camera: Camera3D = main.get("full_map_camera")
	_expect(picture is MeshInstance3D and is_instance_valid(picture),
		"the current region's picture is installed")
	if picture is MeshInstance3D:
		var aabb: AABB = (picture as MeshInstance3D).mesh.get_aabb()
		# The published cartography crops the picture: frame it as the neighbour's is framed below, inside the minimap.
		var region: Dictionary = (main.get("cartography_regions") as Array)[main.call("_region_index_for_map", "mirrorhold")] as Dictionary
		var extent: Rect2 = MapPicture.extent(manifest.data.get("minimap", {}) as Dictionary, region.get("tabMap", {}) as Dictionary)
		_expect(extent.size.x > 0.0 and Rect2(-224.0, -246.0, 456.0, 592.0).encloses(extent),
			"the region's cartography frames its picture inside its minimap (%s)" % extent)
		_expect(_spans(aabb, extent, -24.0),
			"the picture spans the region's framed minimap (%s)" % aabb)
		_expect((picture as MeshInstance3D).layers == main.get("MAP_PICTURE_LAYER"), "the picture is on the map layer")
	_expect(map_camera.cull_mask == main.get("MAP_PICTURE_LAYER") and full_map_camera.cull_mask == main.get("MAP_PICTURE_LAYER"),
		"the map cameras render the picture layer alone")
	# The resident neighbour's picture stands under its root, in its frame, on the
	# same layer, so the minimap window past the seam shows that map and not the background.
	var neighbour_pictures: Dictionary = main.get("_neighbour_pictures")
	var neighbour_picture: Variant = neighbour_pictures.get("whitehorn_range")
	_expect(neighbour_picture is MeshInstance3D and is_instance_valid(neighbour_picture),
		"a resident neighbour's picture is installed")
	if neighbour_picture is MeshInstance3D:
		_expect((neighbour_picture as Node).get_parent() == neighbour_root, "the neighbour's picture stands under its resident root")
		_expect((neighbour_picture as MeshInstance3D).layers == main.get("MAP_PICTURE_LAYER"), "the neighbour's picture is on the map layer")
		var neighbour_aabb: AABB = (neighbour_picture as MeshInstance3D).mesh.get_aabb()
		var neighbour_region: Dictionary = (main.get("cartography_regions") as Array)[main.call("_region_index_for_map", "whitehorn_range")] as Dictionary
		var neighbour_extent: Rect2 = MapPicture.extent(neighbour_manifest.data.get("minimap", {}) as Dictionary, neighbour_region.get("tabMap", {}) as Dictionary)
		_expect(neighbour_extent.size.x > 0.0 and Rect2(-362.0, -522.0, 708.0, 708.0).encloses(neighbour_extent),
			"the neighbour's cartography frames its picture inside its minimap (%s)" % neighbour_extent)
		_expect(_spans(neighbour_aabb, neighbour_extent, -23.0),
			"the neighbour's picture spans its framed minimap a metre under its lowest ground (%s)" % neighbour_aabb)
	(stream.get("residents") as Dictionary).erase("whitehorn_range")
	stream.emit_signal("residents_changed")
	_expect(not (main.get("_neighbour_pictures") as Dictionary).has("whitehorn_range"), "a neighbour that leaves takes its picture with it")

	# Every region the registry places on the continent stands on the map layer,
	# loaded or not: the Tab map frames the neighbours, and the grey hole where an
	# unloaded region stood is what the pictures are for. An unloaded region is
	# laid in the world root on the continent translations, its picture framed by
	# the cartography alone, a little under the current region's own.
	stream.set("active_map", "mirrorhold")
	main.call("_install_map_picture", manifest)
	var registry: Dictionary = main.get("map_registry") as Dictionary
	var far_pictures: Dictionary = main.get("_neighbour_pictures") as Dictionary
	var far_picture: Variant = far_pictures.get("four_gates")
	_expect(far_picture is MeshInstance3D and is_instance_valid(far_picture),
		"a region that is not loaded still has its picture")
	if far_picture is MeshInstance3D:
		_expect((far_picture as Node).get_parent() == main.get("world_root"),
			"an unloaded region's picture stands in the world root")
		var here_translation: Array = (MapRegistry.resolve(registry, "mirrorhold").get(
			"continentGeography", {}) as Dictionary).get("translation", []) as Array
		var there_translation: Array = (MapRegistry.resolve(registry, "four_gates").get(
			"continentGeography", {}) as Dictionary).get("translation", []) as Array
		var offset := Vector3(float(there_translation[0]) - float(here_translation[0]),
			float(there_translation[1]) - float(here_translation[1]),
			float(there_translation[2]) - float(here_translation[2]))
		_expect((far_picture as MeshInstance3D).transform.origin.is_equal_approx(offset),
			"it stands where the continent translations put it (%s for %s)" % [
				(far_picture as MeshInstance3D).transform.origin, offset])
		var far_index: int = main.call("_region_index_for_map", "four_gates")
		var far_region: Dictionary = (main.get("cartography_regions") as Array)[far_index] as Dictionary
		var far_extent: Rect2 = MapPicture.tab_map_extent(far_region.get("tabMap", {}) as Dictionary)
		var sunk: float = float(main.get("_map_picture_height")) - float(main.get("MAP_PICTURE_SINK_METRES")) * float(far_index + 1)
		_expect(far_extent.size.x > 0.0 and _spans((far_picture as MeshInstance3D).mesh.get_aabb(), far_extent, sunk),
			"its picture spans the framing its cartography publishes (%s)" % (far_picture as MeshInstance3D).mesh.get_aabb())
		# A click out there names that region and its tile, though no link joins
		# the two maps directly: the walk is then routed leg by leg as ever.
		var middle: Vector2 = far_extent.get_center()
		var beyond_far: Dictionary = stream.call("map_at_local", Vector3(middle.x + offset.x, 0.0, middle.y + offset.z))
		_expect(str(beyond_far.get("map", "")) == "four_gates",
			"a map click on a region that is not next door names that region (%s)" % beyond_far)
		# Whose ground a map click is on is read from the territory outlines the
		# maps draw, not from which square of served cells holds it: those squares
		# reach far into the neighbours' ground, and a click on the neighbour's side
		# of a border went to the server as a walk on this map that stopped there.
		var previous_map: String = str(app_state.get("current_map"))
		app_state.set("current_map", "mirrorhold")
		var continent: Dictionary = (main.get("cartography") as Dictionary).get("continent", {}) as Dictionary
		var origin: Array = continent.get("originMetres", []) as Array
		var metres_per_pixel: float = float(continent.get("metresPerPixel", 0.0))
		var here_index: int = main.call("_region_index_for_map", "mirrorhold")
		var here_region: Dictionary = (main.get("cartography_regions") as Array)[here_index] as Dictionary
		var here_offset: Array = here_region.get("globalTranslation", []) as Array
		for probe: Array in [[far_region, "four_gates"], [here_region, "mirrorhold"]]:
			var label: Array = (probe[0] as Dictionary).get("continentLabel", []) as Array
			var point := Vector3(float(origin[0]) + float(label[0]) * metres_per_pixel - float(here_offset[0]), 0.0,
				float(origin[1]) + float(label[1]) * metres_per_pixel - float(here_offset[2]))
			_expect(str(main.call("_map_owning_point", point)) == str(probe[1]),
				"a map click on %s's own ground is a walk to %s" % [probe[1], probe[1]])
		var owned: Dictionary = stream.call("map_at_local", Vector3(middle.x + offset.x, 0.0, middle.y + offset.z), "four_gates")
		_expect(str(owned.get("map", "")) == "four_gates" and owned.get("tile") is Vector2i,
			"the owning map's own tile answers for the click (%s)" % owned)
		app_state.set("current_map", previous_map)
	# A map click past the seam: the direct neighbour whose served tiles hold
	# the point is found through the surveyed join, and the walk is armed in legs.
	stream.set("active_map", "mirrorhold")
	var coordinates := {"metresPerTile": 1.0, "serverOrigin": [0, 0], "serverCells": [400, 400], "invertServerY": true, "walkingHeight": 2.0, "origin": [0, 0, 0]}
	var here := {"map": "mirrorhold", "position": [100.0, 2.0, -200.0], "coordinateTransform": coordinates,
		"frame": {"anchor": [100.0, 2.0, -209.0], "outward": [0.0, -1.0], "globalTranslation": [0, 0, 0]}}
	var there_coordinates := {"metresPerTile": 1.0, "serverOrigin": [0, 400], "serverCells": [400, 400], "invertServerY": true, "walkingHeight": 2.0, "origin": [0, 0, 0]}
	var there := {"map": "whitehorn_range", "position": [100.0, 2.0, 200.0], "coordinateTransform": there_coordinates,
		"frame": {"anchor": [100.0, 2.0, 209.0], "outward": [0.0, 1.0], "globalTranslation": [0, 0, -418]}}
	stream.set("links", [{"id": "mirrorhold--whitehorn_range", "seamless": true, "ends": [here, there]}])
	var frame_value: Variant = stream.call("neighbour_transform", "whitehorn_range")
	_expect(frame_value is Transform3D and ((frame_value as Transform3D).origin - Vector3(0, 0, -418)).length() < 0.01,
		"a neighbour that is not resident is framed by the surveyed join (%s)" % frame_value)
	var beyond: Dictionary = stream.call("map_at_local", Vector3(150.0, 2.0, -300.0))
	_expect(str(beyond.get("map", "")) == "whitehorn_range" and (beyond.get("tile") as Vector2i).x == 150 and absi((beyond.get("tile") as Vector2i).y - 282) <= 1,
		"a point past the seam belongs to the neighbour, in its own tiles (%s)" % beyond)
	_expect((stream.call("map_at_local", Vector3(150.0, 2.0, -900.0)) as Dictionary).is_empty(),
		"a point beyond the neighbour's served cells belongs to no one")
	var leg_value: Variant = stream.call("arm_walk_to", "whitehorn_range", Vector2i(150, 282), false, Vector3(150.0, 2.0, -300.0))
	var pending: Dictionary = stream.get("pending_walk")
	_expect(leg_value is Vector3 and (leg_value as Vector3).is_equal_approx(Vector3(100.0, 2.0, -200.0)),
		"the walk's first leg ends at the surveyed crossing (%s)" % leg_value)
	_expect(str(pending.get("map", "")) == "whitehorn_range" and pending.get("tile") == Vector2i(150, 282)
		and str(pending.get("next_map", "")) == "whitehorn_range" and str(pending.get("issued_from", "")) == "mirrorhold",
		"the pending walk carries the neighbour, its tile and the next map (%s)" % pending)
	_expect(stream.call("arm_walk_to", "whitehorn_range", Vector2i(900, 900), false, Vector3.ZERO) == null,
		"a tile outside the neighbour's cells is refused")
	# A view-only link draws a neighbour across a border nobody can cross; a walk
	# routed over it went to the middle of that border and stopped there.
	var road_links: Array = stream.get("links")
	var view_there := {"map": "four_gates", "position": [0.0, 2.0, -100.0], "coordinateTransform": coordinates,
		"frame": {"anchor": [0.0, 2.0, -100.0], "outward": [1.0, 0.0], "globalTranslation": [0, 0, 0]}}
	stream.set("links", [{"id": "view--mirrorhold--four_gates", "seamless": true, "visualOnly": true,
		"ends": [here.duplicate(true), view_there]}])
	_expect(stream.call("arm_walk_to", "four_gates", Vector2i(10, 10), false, Vector3.ZERO) == null,
		"no walk is routed over a view-only link")
	stream.set("links", road_links)
	# The region boundaries: every cartography polygon in this map's metres, the
	# current one flagged; the first point of a polygon converts through the continent frame.
	var boundaries: Array = main.call("_map_boundaries")
	var regions: Array = main.get("cartography_regions")
	# Only the regions of mirrorhold's own continent frame: the rebuilt continent's
	# isles share the picture's pixel lattice but no ground with it.
	var same_frame: int = 0
	for region_value: Variant in regions:
		if str((region_value as Dictionary).get("frame", "")).is_empty():
			same_frame += 1
	_expect(boundaries.size() == same_frame and boundaries.size() > 0 and same_frame < regions.size(),
		"one boundary a region of this continent (%d of %d rows)" % [boundaries.size(), regions.size()])
	var continent: Dictionary = (main.get("cartography") as Dictionary).get("continent", {})
	var current_index: int = main.call("_region_index_for_map", "mirrorhold")
	if current_index >= 0 and boundaries.size() == same_frame:
		var mirror: Dictionary = regions[current_index]
		var first: Array = (regions[0] as Dictionary).get("continentPolygon", [[0, 0]])[0]
		var expected := Vector3(float(continent.originMetres[0]) + float(first[0]) * float(continent.metresPerPixel) - float(mirror.globalTranslation[0]), 0,
			float(continent.originMetres[1]) + float(first[1]) * float(continent.metresPerPixel) - float(mirror.globalTranslation[2]))
		var got: Vector3 = (boundaries[0].get("points") as PackedVector3Array)[0]
		_expect(Vector2(got.x, got.z).is_equal_approx(Vector2(expected.x, expected.z)),
			"a polygon pixel converts through the continent frame into this map's metres (%s vs %s)" % [got, expected])
		_expect(bool(boundaries[current_index].get("current", false)) and str(boundaries[current_index].get("name", "")) == str(mirror.get("name", "")),
			"the current region is flagged with its name")
	var interior := WorldManifest.new()
	interior.data = {"schemaVersion": "1.0", "asset": {"id": "amberwood_estate", "origin": [0, 0, 0]}}
	app_state.call("_on_packet", EloriaProtocol.ServerMessage.CHANGE_MAP, "amberwood_estate".to_ascii_buffer() + PackedByteArray([0]))
	main.call("_install_map_picture", interior)
	_expect(main.get("_map_picture") == null, "a map without a picture installs none")
	_expect(map_camera.cull_mask == 1 and full_map_camera.cull_mask == 1,
		"the map cameras return to the live render on a map without a picture")
	# The neighbours' pictures are decoded ahead of a crossing, one a frame, into the Tab map's cache.
	var textures: Dictionary = main.get("_tab_map_textures")
	textures.erase("whitehorn_range")
	app_state.set("adjacent_maps", {1: "whitehorn_range", 2: "no_such_region"})
	main.call("_queue_map_picture_warmup")
	var queued: Array = main.get("_map_picture_warmup")
	_expect(queued == ["whitehorn_range"], "an adjacent region without a cached picture is queued, an unknown map is not (%s)" % [queued])
	_expect(not textures.has("whitehorn_range"), "queueing decodes nothing on the handoff frame")
	main.call("_warm_one_map_picture")
	_expect(textures.has("whitehorn_range") and textures["whitehorn_range"] is Texture2D, "the queued region's texture is decoded on a later frame")
	_expect((main.get("_map_picture_warmup") as Array).is_empty(), "the queue is drained")
	main.call("_queue_map_picture_warmup")
	_expect((main.get("_map_picture_warmup") as Array).is_empty(), "a cached region is not queued again")
	main.queue_free()
	await process_frame

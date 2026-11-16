extends SceneTree
## The cave glint (map polish, owner-approved 2026-11-16): on a dark interior
## map (Landfall's underground and every cave, barrow or vault) a harvest node
## wears a few faint winking flares, drawn by the gameplay camera only, so it
## can be found by looking at the world; harvestables are still never marked on
## the maps (owner 2026-11-14), and an exterior map's nodes never glint.

const REGISTRY := "res://data/world/objects.json"
const GLINT := preload("res://src/world/harvest_glint.gd")
const INSIDES := "res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"
const EXTERIOR := "res://../eloria-assets/maps/continent-v2/landfall/client/world.json"
const DESCENT := "res://../eloria-assets/maps/continent-v2/serpent_deep_descent/client/world.json"
const GAUNTLET := "res://../eloria-assets/maps/nymara-regions/interiors/amberwood_gauntlet/world.json"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_which_maps()
	var catalog: Dictionary = _json(REGISTRY)
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [0.0, 0.0]})
	_check_node(adapter, catalog)
	await _check_main()
	print("harvest cave glint tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --- which maps glint ----------------------------------------------------------------

func _check_which_maps() -> void:
	var insides := _json(INSIDES)
	_expect(not insides.is_empty() and GLINT.wanted_for(insides), "Landfall's underground glints")
	_expect((insides.get("harvestables", []) as Array).size() >= 700,
		"and that is where the dark nodes are (%d)" % (insides.get("harvestables", []) as Array).size())
	var exterior := _json(EXTERIOR)
	_expect(not exterior.is_empty() and not GLINT.wanted_for(exterior), "an exterior Landfall map never glints")
	var descent := _json(DESCENT)
	_expect(descent.is_empty() or GLINT.wanted_for(descent), "the Serpent Deep's cave floors glint")
	var gauntlet := _json(GAUNTLET)
	if not gauntlet.is_empty():
		_expect(not GLINT.wanted_for(gauntlet, {"interiorOf": "amberwood"}), "a brightly lit gauntlet arena does not")
	_expect(not GLINT.wanted_for({"asset": {"interiorClass": "insides"},
		"environment": {"sun": {"energy": 1.1}, "ambient": {"energy": 0.6}}}), "an interior under a full sun does not")
	_expect(GLINT.wanted_for({"asset": {}}, {"insidesOf": "grey_moors"}),
		"an interior the registry names, with no lighting of its own, is taken as dark")
	_expect(not GLINT.wanted_for({"environment": {"profile": "cave-interior"}}),
		"and a map that is no interior never glints, whatever its profile")

# --- one node ---------------------------------------------------------------------------

func _check_node(adapter: CoordinateAdapter, catalog: Dictionary) -> void:
	var node := _object(adapter, catalog, "Mushroom", 7001)
	var bounds := MapObject3D.model_space_bounds(node.get_node("Model") as Node3D)
	_expect(node.cave_glint() == null, "a node does not glint unless its map asks")
	node.set_cave_glint(true)
	var glint := node.cave_glint()
	_expect(glint != null and glint.get_parent() == node.get_node("Model") and glint.visible,
		"a glinting node wears the glint on its model (so it takes the model's yaw and seat)")
	if glint == null:
		return
	_expect(glint.layers == MapObject3D.GAMEPLAY_LAYER
		and (glint.layers & MapMarkerDisc.MAP_MARKER_LAYER) == 0
		and (glint.layers & preload("res://src/ui/world_label_style.gd").RENDER_LAYER) == 0,
		"it is drawn by the gameplay camera only, on no map layer (layers %d)" % glint.layers)
	var material := glint.material_override as ShaderMaterial
	_expect(material != null and material.shader == GLINT.SHADER
		and material.get_shader_parameter("flare_texture") is Texture2D,
		"with the glint shader and the harvest sparkle's flare")
	_expect(glint.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		and glint.visibility_range_end > 0.0 and glint.visibility_range_end <= 40.0,
		"casting nothing, and culled beyond %.0f m" % glint.visibility_range_end)
	_expect(node.get_node_or_null("MapMarker") == null, "and the node still has no map marker")
	_expect(MapObject3D.model_space_bounds(node.get_node("Model") as Node3D).is_equal_approx(bounds),
		"the glint is not counted as the model's own geometry")
	var flares := glint.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array
	var spread := AABB(flares[0], Vector3.ZERO)
	for flare: Vector3 in flares:
		spread = spread.expand(flare)
	var placed := glint.transform * spread
	_expect(bounds.grow(0.05).encloses(placed), "its flares stand on the model's bounds: %s in %s" % [placed, bounds])
	node.set_cave_glint(false)
	_expect(not glint.visible and node.cave_glint() == glint, "turned off, it is hidden")
	node.set_cave_glint(true)
	_expect(glint.visible and node.get_node("Model").get_children().filter(
		func(child: Node) -> bool: return child.name == GLINT.NODE_NAME).size() == 1,
		"and turned on again it is the same glint")
	var other := _object(adapter, catalog, "Lotus", 7002)
	other.set_cave_glint(true)
	_expect(other.cave_glint() != null and other.cave_glint().mesh == glint.mesh
		and other.cave_glint().material_override == material, "every node shares one mesh and one material")
	# A vein set into the rock: its flares stand on the face in front.
	var test_catalog: Dictionary = catalog.duplicate(true)
	var models: Dictionary = test_catalog.harvestables.models
	var seam: Dictionary = (models.get(str(test_catalog.harvestables.resources.get("Coal", "")), {}) as Dictionary).duplicate()
	seam["placement"] = "wall"
	models["test_coal_wall"] = seam
	test_catalog.harvestables["wallVariants"] = {"Coal": ["test_coal_wall"]}
	var wall := _object(adapter, test_catalog, "Coal", 7003, {"placement": "wall", "variant": 0.0, "yaw": 90.0, "inset": 0.6})
	wall.set_cave_glint(true)
	var wall_flares := wall.cave_glint().mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] as PackedVector3Array
	_expect(wall.cave_glint().mesh != glint.mesh and wall_flares[0].z > 0.4,
		"a wall seam's flares stand on the face, out of the rock (+Z)")
	# A node standing no model of its own glints over its tile.
	var bare := _object(adapter, catalog, "Cotton", 7004)
	bare.set_cave_glint(true)
	_expect(bare.get_node_or_null("Model") == null and bare.cave_glint() != null
		and bare.cave_glint().get_parent() == bare, "a node with no model glints over its tile")
	# Only harvest nodes glint.
	var notice := MapObject3D.new()
	notice.configure({"object_id": 7005, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 4, "y": 4, "label": "Information", "detail": ""},
		adapter, catalog)
	root.add_child(notice)
	notice.set_cave_glint(true)
	_expect(notice.cave_glint() == null, "an interactive never glints")
	for value: Node in [node, other, wall, bare, notice]:
		value.free()

# --- main ---------------------------------------------------------------------------------

func _check_main() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var state: Node = root.get_node("AppState")
	root.get_node("Network").set_process(false)
	var table: Dictionary = preload("res://src/world/underground_scenery.gd").harvest_presentation("landfall_insides")
	var insides := WorldManifest.new()
	insides.data = _json(INSIDES)
	state.current_map = "landfall_insides"
	# A wall vein (1001), a floor seam (1010) and a node the table leaves bare (1209).
	var listed := {1001: "Coal", 1010: "Quartz", 1209: "Geode"}
	var objects := {}
	for identity: int in listed:
		objects[identity] = {"object_id": identity, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
			"x": 100 + identity % 50, "y": 200, "label": listed[identity], "detail": ""}
	state.map_objects = objects
	# Listed while the map is still loading: no glint yet, then the map binds.
	main._sync_map_objects()
	var early: MapObject3D = main.map_object_nodes[1209]
	_expect(early.cave_glint() == null, "an object listed before its map binds does not glint yet")
	main._bind_map_presentation(insides)
	_expect(table.has("1001") and table.has("1010"), "the underground's table lays out 1001 and 1010")
	main._sync_map_objects()
	await process_frame
	for identity: int in listed:
		var node: MapObject3D = main.map_object_nodes[identity]
		_expect(node.cave_glint() != null and node.cave_glint().visible,
			"underground %s node %d glints (%s)" % [listed[identity], identity, node.model_id])
	_expect((main.map_object_nodes[1001] as MapObject3D).is_wall_placed(), "1001 is a wall vein")
	var marks: Array[Dictionary] = main._collect_minimap_marks()
	var harvest := marks.filter(func(mark: Dictionary) -> bool:
		return mark.get("type") == &"harvest" or mark.has("grouping"))
	_expect(harvest.is_empty(), "the maps still mark no harvestable (%d harvest marks)" % harvest.size())
	var layer := (main.map_object_nodes[1010] as MapObject3D).cave_glint().layers
	_expect(((main.map_camera as Camera3D).cull_mask & layer) == 0
		and ((main.full_map_camera as Camera3D).cull_mask & layer) == 0,
		"and neither map camera draws the glint's layer")
	# The glint is a way to find a node, not particle eye candy: the particles
	# setting leaves it.
	main.call("_on_client_setting_changed", "graphics", "particles", false)
	_expect((main.map_object_nodes[1010] as MapObject3D).cave_glint().visible,
		"turning particles off leaves the glint")
	main.call("_on_client_setting_changed", "graphics", "particles", true)

	# Out on an exterior map the same kind of node does not glint.
	var exterior := WorldManifest.new()
	exterior.data = _json(EXTERIOR)
	state.current_map = "landfall"
	main._bind_map_presentation(exterior)
	main._sync_map_objects()
	await process_frame
	for identity: int in listed:
		var node: MapObject3D = main.map_object_nodes[identity]
		_expect(node.cave_glint() == null or not node.cave_glint().visible,
			"on an exterior map node %d does not glint" % identity)
	state.map_objects = {}
	main._sync_map_objects()
	await process_frame

# --- helpers --------------------------------------------------------------------------------

func _object(adapter: CoordinateAdapter, catalog: Dictionary, label: String, object_id: int,
		presentation: Dictionary = {}) -> MapObject3D:
	var node := MapObject3D.new()
	node.configure({"object_id": object_id, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
		"x": 10, "y": 10, "label": label, "detail": ""}, adapter, catalog, false, presentation)
	root.add_child(node)
	return node

static func _json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

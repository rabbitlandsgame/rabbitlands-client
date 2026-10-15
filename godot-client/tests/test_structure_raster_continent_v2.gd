extends SceneTree
## The walkability overlay's LIVE structure rules for a continent-v2 territory
## (structure_raster.gd with gather's continent_v2), against the rules
## _continent_v2/export_collision.py publishes with: an open solid's walled-in
## ground blocks unless a way out or its own Walk_ deck leaves it open
## (enclosed), and a tree blocks only its trunk (trunk). A legacy territory
## keeps collision_export.py's rules, and the overlay tells the two apart by the
## region's authoring spec (walkability_overlay.gd continent_v2).
##
## Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##     --script res://tests/test_structure_raster_continent_v2.gd

const Structures := preload("res://addons/map_authoring_usability/structure_raster.gd")
const Walkability := preload("res://addons/map_authoring_usability/walkability_overlay.gd")
const ASSET := preload("res://src/dev/map_authoring_region/asset_control.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const MARKER := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const SPEC_DIR := "res://test-artifacts/structure-raster-v2"

var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var fixture := Node3D.new()
	fixture.name = "StructureFixture"
	get_root().add_child(fixture)
	var assets := Node3D.new()
	assets.name = "AuthoredAssets"
	fixture.add_child(assets)
	var heights := PackedFloat32Array()
	heights.resize(49)
	heights.fill(0.0)
	# 12 × 12 m of flat ground, half-cells centred on odd quarter metres.
	var ground := Structures.ground_frame({"heights": heights, "grid": Vector2i(7, 7),
		"cell": 2.0, "terrain_x0": -6.0, "terrain_z0": -6.0, "x0": -6.0, "z0": -6.0,
		"tile": 1.0, "width": 12, "rows": 12})
	var middle := _half_cell(0.25, 0.25)
	_test_open_ring(fixture, assets, ground, middle)
	_test_doorway(fixture, assets, ground, middle)
	_test_own_deck(fixture, assets, ground)
	_test_closed_solid(fixture, assets, ground, middle)
	_test_tree(fixture, assets, ground)
	fixture.free()
	_test_harvest(ground)
	_test_gate()
	_finish()


## Four open walls round a 4 × 4 m floor: the legacy rule blocks the walls
## only; continent-v2 blocks the floor they wall in as well.
func _test_open_ring(fixture: Node3D, assets: Node3D, ground: Dictionary, middle: int) -> void:
	_fixture_asset(assets, "House", "solid", "", _ring_walls(false))
	var legacy := _structure_result(fixture, ground, false)
	_fixture_asset(assets, "House", "solid", "", _ring_walls(false))
	var v2 := _structure_result(fixture, ground, true)
	_expect(legacy.blocked.has(_half_cell(1.75, 0.25)) and not legacy.blocked.has(middle),
		"legacy: an open wall ring blocks its walls and leaves its floor open")
	var floor_cells := 0
	for x in [-1.25, -0.75, -0.25, 0.25, 0.75, 1.25]:
		for z in [-1.25, -0.75, -0.25, 0.25, 0.75, 1.25]:
			if v2.blocked.has(_half_cell(x, z)):
				floor_cells += 1
	_expect(floor_cells == 36, "continent-v2: the walled-in floor is blocked (%d of 36 cells)" % floor_cells)
	_expect(not v2.blocked.has(_half_cell(2.75, 0.25)) and not v2.blocked.has(_half_cell(-2.75, 0.25)),
		"continent-v2: the ground outside the ring stays open")


## The same ring with a 2 m doorway in its south wall leaves a way out, so its
## floor is not enclosed.
func _test_doorway(fixture: Node3D, assets: Node3D, ground: Dictionary, middle: int) -> void:
	_fixture_asset(assets, "Shop", "solid", "", _ring_walls(true))
	var v2 := _structure_result(fixture, ground, true)
	_expect(not v2.blocked.has(middle) and not v2.blocked.has(_half_cell(0.25, -1.75)) and
		v2.blocked.has(_half_cell(-1.75, 0.25)),
		"continent-v2: a ring with a doorway keeps its floor open and its walls blocked")


## A closed ring whose own Walk_ deck covers its west half: the deck stays open
## (a gatehouse passage, a pier between parapets); the rest is enclosed.
func _test_own_deck(fixture: Node3D, assets: Node3D, ground: Dictionary) -> void:
	var meshes := _ring_walls(false)
	meshes.append(_fixture_mesh("Walk_Floor", _quad(-2.0, -2.0, 0.0, 2.0, 0.02)))
	_fixture_asset(assets, "Gatehouse", "solid", "", meshes)
	var v2 := _structure_result(fixture, ground, true)
	_expect(not v2.blocked.has(_half_cell(-1.25, 0.25)) and not v2.blocked.has(_half_cell(-0.25, 0.25)) and
		v2.blocked.has(_half_cell(0.25, 0.25)) and v2.blocked.has(_half_cell(1.25, 0.25)),
		"continent-v2: the placement's own Walk_ deck stays open inside its walls")
	var other := _ring_walls(false)
	_fixture_asset(assets, "Hall", "solid", "", other)
	_fixture_asset(assets, "Walk_Boardwalk", "walk_surface", "",
		[_fixture_mesh("Planks", _quad(-2.0, -2.0, 0.0, 2.0, 0.02))])
	var foreign := _structure_result(fixture, ground, true)
	_expect(foreign.blocked.has(_half_cell(-1.25, 0.25)),
		"continent-v2: another placement's deck does not open an enclosed floor")


## A watertight solid was already blocked inside (the winding rule); the fill
## changes nothing for it, and its cells match the legacy rule.
func _test_closed_solid(fixture: Node3D, assets: Node3D, ground: Dictionary, middle: int) -> void:
	_fixture_asset(assets, "Rock", "solid", "", [_fixture_mesh("Rock", _box(-2, -1, -2, 2, 8, 2))])
	var legacy := _structure_result(fixture, ground, false)
	_fixture_asset(assets, "Rock", "solid", "", [_fixture_mesh("Rock", _box(-2, -1, -2, 2, 8, 2))])
	var v2 := _structure_result(fixture, ground, true)
	_expect(legacy.blocked.has(middle) and legacy.blocked.keys().size() == v2.blocked.keys().size(),
		"a closed solid blocks the same cells under both rules")


## A palm whose trunk stands 2 m off the model origin, under a crown that droops
## into the actor's height: legacy blocks the whole crown, continent-v2 only a
## trunk-sized footprint where the trunk stands.
func _test_tree(fixture: Node3D, assets: Node3D, ground: Dictionary) -> void:
	var centre := Vector2(2.25, 0.25)
	var tree: Array[Node] = [_fixture_mesh("Trunk", _column(centre, 0.3)),
		_fixture_mesh("Crown", _box(-3, 1.5, -3, 3, 4, 3))]
	_fixture_asset(assets, "Palm", "solid", "res://world_authoring/kit-test-palm-tree-1.glb", tree)
	var legacy := _structure_result(fixture, ground, false)
	tree = [_fixture_mesh("Trunk", _column(centre, 0.3)), _fixture_mesh("Crown", _box(-3, 1.5, -3, 3, 4, 3))]
	_fixture_asset(assets, "Palm", "solid", "res://world_authoring/kit-test-palm-tree-1.glb", tree)
	var v2 := _structure_result(fixture, ground, true)
	var far := 0.0
	for cell_index: int in v2.blocked:
		var x := -6.0 + (float(cell_index % 24) + 0.5) * 0.5
		var z := -6.0 + (float(cell_index / 24) + 0.5) * 0.5
		far = maxf(far, Vector2(x, z).distance_to(centre))
	_expect(legacy.blocked.has(_half_cell(-2.25, -2.25)) and legacy.blocked.size() > 100,
		"legacy: a tree's drooping crown blocks the ground under it (%d cells)" % legacy.blocked.size())
	_expect(v2.blocked.has(_half_cell(centre.x, centre.y)) and v2.blocked.size() <= 9 and far < 0.8 and
		not v2.blocked.has(_half_cell(-2.25, -2.25)) and not v2.blocked.has(_half_cell(0.25, 0.25)),
		"continent-v2: a tree blocks only its trunk (%d cells, farthest %.2f m from it)" % [
			v2.blocked.size(), far])
	var prism := Structures.trunk(_points(_column(centre, 0.3)))
	var radius := 0.0
	for point in prism:
		radius = maxf(radius, Vector2(point.x, point.z).distance_to(centre))
	_expect(prism.size() == 8 * 4 * 3 and is_equal_approx(radius, 0.3) and
		Structures.closed_faces(prism), "the trunk prism is a closed 8-gon at the trunk's radius")
	var thin := Structures.trunk(_points(_column(centre, 0.05)))
	var thin_radius := 0.0
	for point in thin:
		thin_radius = maxf(thin_radius, Vector2(point.x, point.z).distance_to(centre))
	_expect(is_equal_approx(thin_radius, 0.25), "a trunk thinner than 0.25 m is widened to 0.25 m")
	_fixture_asset(assets, "Bush", "solid", "res://world_authoring/kit-test-shrub-1.glb",
		[_fixture_mesh("Crown", _box(-3, 1.5, -3, 3, 4, 3))])
	var bush := _structure_result(fixture, ground, true)
	_expect(bush.blocked.has(_half_cell(-2.25, -2.25)),
		"continent-v2: a solid without \"tree\" in its file name keeps its whole body")


## A harvest node closes its own served tile (export_collision.harvest_mask);
## other gameplay markers close nothing.
func _test_harvest(ground: Dictionary) -> void:
	var region: Node3D = REGION.new()
	region.set("server_origin", Vector2i(10, 10))
	get_root().add_child(region)
	var gameplay := Node3D.new()
	gameplay.name = "Gameplay"
	region.add_child(gameplay)
	for entry: Array in [["harvest-1-sage", "harvestable", Vector3(2.5, 0.0, 3.5)],
			["spawn-1", "spawn", Vector3(-2.5, 0.0, -3.5)]]:
		var marker: Node3D = MARKER.new()
		marker.set("record_id", entry[0])
		marker.set("kind", entry[1])
		marker.position = entry[2]
		gameplay.add_child(marker)
	var classes := PackedByteArray()
	classes.resize(144)
	classes.fill(Walkability.Tile.WALKABLE)
	var data := {"classes": classes, "blockers": {}, "width": 12, "rows": 12}
	Walkability.harvest_pass(region, data, ground)
	region.free()
	var blocked: Array = []
	for index in (data.classes as PackedByteArray).size():
		if (data.classes as PackedByteArray)[index] == Walkability.Tile.BLOCKED:
			blocked.append(index)
	_expect(blocked == [9 * 12 + 8] and String(data.blockers.get(9 * 12 + 8, "")) == "harvest node harvest-1-sage",
		"continent-v2: a harvest node closes its own tile and a spawn closes nothing (%s)" % str(blocked))


## The overlay applies these rules only where the region's authoring spec names
## the continent-v2 pipeline.
func _test_gate() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SPEC_DIR))
	var v2_spec := SPEC_DIR.path_join("v2")
	var legacy_spec := SPEC_DIR.path_join("legacy")
	for directory in [v2_spec, legacy_spec]:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	_write_json(v2_spec.path_join("region-authoring-spec.json"),
		{"adapter": "continent-v2-meshy-v1", "continentV2": {}})
	_write_json(legacy_spec.path_join("region-authoring-spec.json"), {"adapter": "published-generic-v1"})
	var root := Node3D.new()
	root.scene_file_path = v2_spec.path_join("fixture.tscn")
	var v2 := Walkability.continent_v2(root)
	root.scene_file_path = legacy_spec.path_join("fixture.tscn")
	var legacy := Walkability.continent_v2(root)
	root.scene_file_path = ""
	var bare := Walkability.continent_v2(root)
	root.free()
	_expect(v2 and not legacy and not bare, "the gate reads the generic region fixtures' authoring specs")


func _structure_result(fixture: Node3D, ground: Dictionary, continent_v2: bool) -> Dictionary:
	var shapes := Structures.gather(fixture, continent_v2)
	var blocked := {}
	for solid: Dictionary in shapes.solids:
		for index in Structures.blocked_cells(solid.parts, ground, bool(solid.enclose), solid.deck):
			blocked[index] = true
	for asset in fixture.get_node("AuthoredAssets").get_children():
		asset.free()
	return {"blocked": blocked}


## Open walls 3 m tall round the square x, z in [-2, 2] (two triangles each, so
## no part is closed); `doorway` leaves the south wall open for |x| < 1.
func _ring_walls(doorway: bool) -> Array[Node]:
	var meshes: Array[Node] = [_fixture_mesh("WallNorth", _wall(Vector2(-2, 2), Vector2(2, 2))),
		_fixture_mesh("WallEast", _wall(Vector2(2, -2), Vector2(2, 2))),
		_fixture_mesh("WallWest", _wall(Vector2(-2, -2), Vector2(-2, 2)))]
	if doorway:
		meshes.append(_fixture_mesh("WallSouthWest", _wall(Vector2(-2, -2), Vector2(-1, -2))))
		meshes.append(_fixture_mesh("WallSouthEast", _wall(Vector2(1, -2), Vector2(2, -2))))
	else:
		meshes.append(_fixture_mesh("WallSouth", _wall(Vector2(-2, -2), Vector2(2, -2))))
	return meshes


func _wall(a: Vector2, b: Vector2) -> Array[Vector3]:
	var result: Array[Vector3] = [Vector3(a.x, 0, a.y), Vector3(b.x, 0, b.y), Vector3(b.x, 3, b.y),
		Vector3(a.x, 0, a.y), Vector3(b.x, 3, b.y), Vector3(a.x, 3, a.y)]
	return result


## An 8-sided trunk of `radius` round `centre`, ringed at heights that sit
## inside the exporter's 0.3 m slices.
func _column(centre: Vector2, radius: float) -> Array[Vector3]:
	var levels := [0.0, 0.45, 0.75, 1.05, 1.35, 1.65, 1.95, 2.25, 3.0]
	var result: Array[Vector3] = []
	for level in levels.size() - 1:
		var y0: float = levels[level]
		var y1: float = levels[level + 1]
		for side in 8:
			var a := centre + Vector2.from_angle(float(side) * TAU / 8.0) * radius
			var b := centre + Vector2.from_angle(float(side + 1) * TAU / 8.0) * radius
			result.append_array([Vector3(a.x, y0, a.y), Vector3(b.x, y1, b.y), Vector3(b.x, y0, b.y),
				Vector3(a.x, y0, a.y), Vector3(a.x, y1, a.y), Vector3(b.x, y1, b.y)])
	return result


func _points(triangles: Array[Vector3]) -> PackedVector3Array:
	return PackedVector3Array(triangles)


func _half_cell(x: float, z: float) -> int:
	return floori((z + 6.0) / 0.5) * 24 + floori((x + 6.0) / 0.5)


func _fixture_asset(parent: Node3D, node_name: String, role: String, scene_path: String,
		meshes: Array) -> void:
	var asset: Node3D = ASSET.new()
	asset.name = node_name
	asset.set("node_name", node_name)
	asset.set("collision_role", role)
	asset.set("scene_path", scene_path)
	var content := Node3D.new()
	content.name = "fixture-scene"
	asset.add_child(content)
	var scene_root := Node3D.new()
	scene_root.name = node_name
	content.add_child(scene_root)
	for mesh: Node in meshes:
		scene_root.add_child(mesh)
	parent.add_child(asset)


## A mesh from glTF-wound (counter-clockwise) triangles; Godot stores them
## clockwise, as its glTF importer does.
func _fixture_mesh(label: String, triangles: Array[Vector3]) -> MeshInstance3D:
	var vertices := PackedVector3Array()
	for index in range(0, triangles.size(), 3):
		vertices.append_array([triangles[index], triangles[index + 2], triangles[index + 1]])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var node := MeshInstance3D.new()
	node.name = label
	node.mesh = mesh
	return node


func _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> Array[Vector3]:
	var v := [Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x0, y0, z1),
		Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x0, y1, z1)]
	var result: Array[Vector3] = []
	for face: Array in [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 3, 7], [0, 7, 4],
			[1, 5, 6], [1, 6, 2], [0, 4, 5], [0, 5, 1], [3, 2, 6], [3, 6, 7]]:
		for corner: int in face:
			result.append(v[corner])
	return result


func _quad(x0: float, z0: float, x1: float, z1: float, y: float) -> Array[Vector3]:
	var result: Array[Vector3] = [Vector3(x0, y, z0), Vector3(x1, y, z1), Vector3(x1, y, z0),
		Vector3(x0, y, z0), Vector3(x0, y, z1), Vector3(x1, y, z1)]
	return result


func _write_json(path: String, value: Variant) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(value))
	file.close()


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: %s" % message)
	else:
		failures += 1
		push_error("FAIL: %s" % message)
	return condition


func _finish() -> void:
	print("structure raster continent-v2: %d failure(s)" % failures)
	quit(1 if failures > 0 else 0)

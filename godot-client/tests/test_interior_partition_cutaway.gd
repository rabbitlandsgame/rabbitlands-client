extends SceneTree
## InteriorCutaway's partitions (src/world/interior_cutaway.gd), headless:
##
##   godot --headless --path godot-client --script res://tests/test_interior_partition_cutaway.gd
##
## A synthetic two-room section split by a partition (its wall and a banner
## decal, two `partitions` rows) and a shelf against it: the partition drops
## while it stands between the camera and the player and returns when the
## player crosses back, with hysteresis on the side and the span; edge-on and
## outside its span it stands; the shelf and the decal go with it; another
## section's partition is left alone; outer walls keep the facing rule. Then
## the real Landfall Town package (when present): its rows group into
## partitions that each measure a span.

const TOWN := "landfall_town"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func _box(name: String, size: Vector3, at: Vector3) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name = name
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.position = at
	return mesh

func _run() -> void:
	await _test_synthetic()
	await _test_town()
	for frame: int in 3:
		await process_frame
	print("Interior partition cutaway: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)

func _test_synthetic() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_test"
	root.add_child(world)
	# Rooms 0 (north, z < 10) and 1 (south) of section "house", 8 m wide
	# (x 0..8), split by a partition along x at z = 10.
	var wall := _box("Part_house_0_lime_plaster", Vector3(8, 3, 0.2), Vector3(4, 1.5, 10))
	var banner := _box("Part_house_0_decal_banner_orun", Vector3(1.2, 1.6, 0.02), Vector3(6, 1.8, 9.88))
	var outer := _box("Build_house_south_lime_plaster", Vector3(8, 3, 0.2), Vector3(4, 1.5, 20))
	var other := _box("Part_shop_0_lime_plaster", Vector3(8, 3, 0.2), Vector3(4, 1.5, 60))
	var shelf := _box("shelf_3", Vector3(1, 2, 0.4), Vector3(2, 1, 9.6))
	shelf.set_meta(InteriorCutaway.WALL_PROP_META, "Part_house_0_lime_plaster")
	for node: Node3D in [wall, banner, outer, other, shelf]:
		world.add_child(node)
	var row := {"section": "house", "rooms": [0, 1], "centre": [4.0, 10.0], "along": [1.0, 0, 0.0],
		"normal": [0.0, 0, -1.0]}
	var wall_row := row.duplicate()
	wall_row["node"] = "Part_house_0_lime_plaster"
	var banner_row := row.duplicate()
	banner_row["node"] = "Part_house_0_decal_banner_orun"
	# The same partition stated the other way round is still one partition.
	banner_row["along"] = [-1.0, 0, 0.0]
	var manifest := WorldManifest.new()
	manifest.data = {"cutaway": {"facingThreshold": 0.35,
		"walls": [{"node": "Build_house_south_lime_plaster", "outward": [0, 0, 1], "section": "house"}],
		"props": {"facingThreshold": 0.35, "radiusMetres": 40},
		"partitions": [wall_row, banner_row, {"node": "Part_shop_0_lime_plaster", "section": "shop",
			"rooms": [0, 1], "centre": [4.0, 60.0], "along": [1.0, 0, 0.0], "normal": [0.0, 0, -1.0]}]}}
	var cutaway := InteriorCutaway.new()
	var claimed := cutaway.configure(manifest, world)
	_expect(claimed >= 5 and cutaway.is_active(),
		"the partitions, the outer wall and the shelf against the partition are taken (%d)" % claimed)
	# yaw 0: the camera stands south (+z) of the player, looking north.
	cutaway.update(0.0, true, "house", Vector3(4, 1, 5))
	_expect(not wall.visible and not banner.visible and not shelf.visible,
		"a partition between the camera and the player drops, with its decal and the shelf against it")
	_expect(not outer.visible, "(the outer wall facing the camera drops by its own facing rule)")
	_expect(cutaway.hidden_partitions().size() == 1, "the partition counts as cut away once")
	cutaway.update(0.0, false, "house", Vector3(4, 1, 10.2))
	_expect(not wall.visible, "a step back to just past it keeps it cut away (hysteresis)")
	cutaway.update(0.0, false, "house", Vector3(4, 1, 11.2))
	_expect(wall.visible and banner.visible and shelf.visible,
		"on the camera's side of it, the partition, its decal and the shelf stand")
	cutaway.update(0.0, false, "house", Vector3(4, 1, 9.85))
	_expect(wall.visible, "just past it from the camera's side is not yet enough to drop it")
	cutaway.update(0.0, false, "house", Vector3(4, 1, 8.9))
	_expect(not wall.visible, "a metre past it drops it")
	cutaway.update(0.0, false, "house", Vector3(14.5, 1, 5))
	_expect(wall.visible, "beyond its span (+2 m) it stands")
	cutaway.update(0.0, false, "house", Vector3(13.5, 1, 5.5))
	_expect(wall.visible, "coming back within the span margin, a shown partition only drops inside +2 m")
	cutaway.update(0.0, false, "house", Vector3(9.5, 1, 5))
	_expect(not wall.visible, "within its span +2 m it drops")
	cutaway.update(0.0, false, "house", Vector3(10.6, 1, 5))
	_expect(not wall.visible, "a cut-away partition returns only past the span's extra metre")
	cutaway.update(90.0, false, "house", Vector3(4, 1, 5))
	_expect(wall.visible, "seen edge-on (camera to the east) it stands")
	cutaway.update(180.0, false, "house", Vector3(4, 1, 5))
	_expect(wall.visible, "with the camera to the north, the player north of it is on the camera's side")
	cutaway.update(180.0, false, "house", Vector3(4, 1, 15))
	_expect(not wall.visible and outer.visible,
		"and the player south of it has it dropped, while the south outer wall (now facing away) stands")
	other.visible = true
	cutaway.update(0.0, true, "house", Vector3(4, 1, 65))
	_expect(other.visible, "another section's partition is not judged from this one")
	cutaway.update(0.0, true, "shop", Vector3(4, 1, 55))
	_expect(not other.visible, "its own section's player drops it")
	cutaway.reset()
	_expect(wall.visible and banner.visible and shelf.visible and other.visible and outer.visible,
		"reset shows everything it hid")
	world.queue_free()
	await process_frame

func _test_town() -> void:
	var registry: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")) as Dictionary).get("maps", {})
	var path := ProjectSettings.globalize_path(str(MapRegistry.resolve(registry, TOWN).get("manifest", "")))
	if not FileAccess.file_exists(path):
		print("SKIP: the Landfall Town package is not on disk")
		return
	preload("res://src/world/gltf_quantization.gd").ensure_registered()
	preload("res://src/world/vram_textures.gd").ensure_registered()
	preload("res://src/world/map_mesh_extension.gd").ensure_registered()
	var builder := WorldLoader.prepare_detached(path, false)
	var resident := builder.release_world(true, true)
	builder.free()
	var shell := resident.get("root") as Node3D
	var manifest := resident.get("manifest") as WorldManifest
	_expect(shell != null and manifest != null, "(fixture) the Town's shell builds")
	if shell == null:
		return
	var rows: Array = (manifest.data.get("cutaway", {}) as Dictionary).get("partitions", [])
	var cutaway := InteriorCutaway.new()
	cutaway.configure(manifest, shell)
	var groups: Array = cutaway.get("_partitions")
	var spans: Array = groups.map(func(group: Dictionary) -> float: return float(group.half))
	var nodes := 0
	for group: Dictionary in groups:
		nodes += (group.nodes as Array).size()
	_expect(not rows.is_empty() and nodes == rows.size() and groups.size() < rows.size(),
		"every partitions row resolves and the rows group into partitions (%d rows, %d partitions)" % [rows.size(), groups.size()])
	_expect(spans.all(func(half: float) -> bool: return half >= 1.0 and half < 30.0),
		"every partition measures a span from its nodes (%s)" % [spans])
	cutaway.reset()
	shell.free()

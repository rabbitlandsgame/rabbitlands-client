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
## section's partition is left alone; outer walls keep the facing rule. The
## sightline rule (final review 2026-10-27): a partition running toward the
## camera drops while the player stands at its end or alongside it, not
## from beside it or past where the line rises over it; `screens` tells a
## point behind a standing partition from one in front of it. Then the real
## Landfall Town package (when present): its rows group into partitions that
## each measure a span; from Hemmen's bedroom (clerk_house-b2, tile 27,88) his
## study/kitchen wall is cut away; from the Gate Hall (castle-a, 26,154)
## Corbin Lask in the Palace Chancery is screened and Oswin is not.

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
	await _test_sightline()
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

func _test_sightline() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_sightline"
	root.add_child(world)
	# A partition running north-south at x = 20, z 0..6, 3 m tall on a floor
	# at y = 0, with a shelf against its east face; and one across the view
	# at z = 10 (x 0..8) to screen points behind.
	var wall := _box("Part_house_1_lime_plaster", Vector3(0.2, 3, 6), Vector3(20, 1.5, 3))
	var shelf := _box("shelf_k", Vector3(0.4, 2, 1), Vector3(20.3, 1, 4))
	shelf.set_meta(InteriorCutaway.WALL_PROP_META, "Part_house_1_lime_plaster")
	var across := _box("Part_house_2_lime_plaster", Vector3(8, 3, 0.2), Vector3(4, 1.5, 10))
	for node: Node3D in [wall, shelf, across]:
		world.add_child(node)
	var manifest := WorldManifest.new()
	manifest.data = {"cutaway": {"props": {"radiusMetres": 40}, "partitions": [
		{"node": "Part_house_1_lime_plaster", "section": "house", "rooms": [0, 1], "centre": [20.0, 3.0],
			"along": [0.0, 0, -1.0], "normal": [-1.0, 0, 0.0]},
		{"node": "Part_house_2_lime_plaster", "section": "house", "rooms": [1, 2], "centre": [4.0, 10.0],
			"along": [1.0, 0, 0.0], "normal": [0.0, 0, -1.0]}]}}
	var cutaway := InteriorCutaway.new()
	cutaway.configure(manifest, world)
	cutaway.fallback_distance = 8.0
	_expect(cutaway.camera_position(0.0, Vector3(20, 0, -2)).is_equal_approx(
			Vector3(20, 0, -2) + Vector3(0, sin(deg_to_rad(50.0)), cos(deg_to_rad(50.0))) * 8.0),
		"(fixture) with no camera in the viewport the rig's orbit stands in")
	# yaw 0: the camera south. The player 2 m past its north end, on its line.
	cutaway.update(0.0, true, "house", Vector3(20, 0, -2))
	_expect(not wall.visible and not shelf.visible,
		"a partition running toward the camera drops while the player stands 2 m past its end (its top crossed their legs)")
	cutaway.update(0.0, true, "house", Vector3(20, 0, -3.6))
	_expect(wall.visible and shelf.visible, "3.6 m past its end the line to the camera clears its top: it stands")
	cutaway.update(0.0, true, "house", Vector3(20, 0, -1))
	_expect(not wall.visible, "a metre past its end it drops again")
	cutaway.update(0.0, true, "house", Vector3(21.3, 0, 2))
	_expect(wall.visible, "a metre clear beside it, the line to the camera passes it by")
	cutaway.update(0.0, true, "house", Vector3(20.65, 0, 2))
	_expect(wall.visible, "with the body's edge just clear of its face it stands")
	cutaway.update(0.0, true, "house", Vector3(20.38, 0, 2))
	_expect(not wall.visible, "alongside it, with the body's edge over its top, it drops")
	cutaway.update(0.0, true, "house", Vector3(20.65, 0, 2))
	_expect(not wall.visible, "and stays dropped there (hysteresis)")
	cutaway.update(0.0, true, "house", Vector3(21.3, 0, 2))
	_expect(wall.visible, "until the body is well clear of it")
	cutaway.update(0.0, true, "house", Vector3(20, 0, 8))
	_expect(wall.visible, "past its camera-side end it is behind the player: it stands")
	cutaway.update(90.0, true, "house", Vector3(14, 0, 3))
	_expect(not wall.visible, "seen face-on (camera to the east) the facing rule still drops it for a player west of it")
	cutaway.update(90.0, true, "house", Vector3(26, 0, 3))
	_expect(wall.visible, "and keeps it for a player on the camera's side")
	# `screens`: the camera south of the across-partition, the player in front of it.
	cutaway.update(0.0, true, "house", Vector3(4, 0, 13))
	var camera := cutaway.camera_position(0.0, Vector3(4, 0, 13))
	_expect(across.visible and cutaway.screens(camera, Vector3(4, 1.7, 9.5)),
		"a head half a metre behind a standing partition is screened from the camera")
	_expect(not cutaway.screens(camera, Vector3(4, 1.7, 12)) and not cutaway.screens(camera, Vector3(4, 1.7, 4)),
		"one in front of it is not, nor one far enough behind to be seen over its top")
	cutaway.update(0.0, true, "house", Vector3(4, 0, 8))
	_expect(not across.visible and not cutaway.screens(camera, Vector3(4, 1.7, 9.5)),
		"a partition cut away screens nothing")
	cutaway.update(0.0, true, "shop", Vector3(4, 0, 13))
	_expect(not cutaway.screens(camera, Vector3(4, 1.7, 9.5)), "nor does another section's")
	cutaway.reset()
	_expect(wall.visible and shelf.visible and across.visible, "reset shows everything it hid")
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
	var adapter := manifest.coordinate_adapter()
	# Hemmen's bedroom (clerk_house-b2: tile 27,88, the close camera at 8 m):
	# his study/kitchen wall runs toward the camera and ends 2 m from him.
	var study_wall: Dictionary = {}
	var gate_wall: Dictionary = {}
	for group: Dictionary in groups:
		var first := str(((group.nodes as Array)[0] as Node3D).name)
		if str(group.section) == "clerk_house" and first.begins_with("Part_clerk_house_0_"):
			study_wall = group
		if str(group.section) == "castle" and first.begins_with("Part_castle_2_"):
			gate_wall = group
	_expect(not study_wall.is_empty() and not gate_wall.is_empty(),
		"(fixture) the study/kitchen wall and the Gate Hall's north wall are partitions")
	if not study_wall.is_empty():
		var box: AABB = study_wall.box
		var bedroom := adapter.tile_center(27, 88)
		bedroom.y = box.position.y
		print("study/kitchen wall: box %s half %.2f thick %.2f; bedroom tile at %s" % [box, float(study_wall.half),
			float(study_wall.thick), bedroom])
		for distance: float in [8.0, 12.0]:
			cutaway.fallback_distance = distance
			cutaway.update(0.0, true, "clerk_house", bedroom)
			_expect(bool(study_wall.hidden) and not ((study_wall.nodes as Array)[0] as Node3D).visible,
				"from Hemmen's bedroom (27,88), camera at %.0f m, his study/kitchen wall is cut away" % distance)
		cutaway.fallback_distance = 12.0
		var study := adapter.tile_center(23, 83)
		study.y = box.position.y
		cutaway.update(0.0, true, "clerk_house", study)
		_expect(not bool(study_wall.hidden), "from his study (clerk_house-a, 23,83) that wall stands")
	if not gate_wall.is_empty():
		var hall := adapter.tile_center(26, 154)
		hall.y = (gate_wall.box as AABB).position.y
		cutaway.fallback_distance = 12.0
		cutaway.update(0.0, true, "castle", hall)
		var camera := cutaway.camera_position(0.0, hall)
		var corbin := adapter.tile_center(23, 164)
		corbin.y = hall.y + 1.7
		var oswin := adapter.tile_center(23, 156)
		oswin.y = hall.y + 1.7
		print("Gate Hall north wall: box %s; camera %s; Corbin's head %s" % [gate_wall.box, camera, corbin])
		_expect(not bool(gate_wall.hidden) and cutaway.screens(camera, corbin),
			"from the Gate Hall (26,154) Corbin Lask in the Palace Chancery is behind its standing north wall")
		_expect(not cutaway.screens(camera, oswin), "while Oswin in the Gate Hall is in plain sight")
	cutaway.reset()
	shell.free()

extends SceneTree
## Validate destination planning without instantiating Main or running a renderer.
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	# Relative to this test script, so an imported project can supply autoloads
	# while this script and the probe remain unstaged external source files.
	var probe_path: String = get_script().resource_path.get_base_dir().path_join("integration/camera_rotation_probe.gd")
	var probe: Script = load(probe_path)
	if probe == null or not probe.can_instantiate():
		_check(false, "probe loads after autoload registration")
		quit(1)
		return
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json"))
	var maps: Dictionary = registry.maps
	var before_nodes := get_node_count()
	var location: Dictionary = probe.probe_location(maps, "", "")
	_check(location.get("map") == "landfall" and location.get("tile") == Vector2i(61, 250),
		"existing Landfall defaults remain unchanged")
	for row: Array in [
		["sunmane_gauntlet", "25,319", Vector2i(25, 319)],
		["sunmane_gauntlet", "21,29", Vector2i(21, 29)],
		["harrowcrag_gauntlet", "44,83", Vector2i(44, 83)],
		["harrowcrag_gauntlet", "216,221", Vector2i(216, 221)],
		["resin_road_gauntlet", "52,327", Vector2i(52, 327)],
		["resin_road_gauntlet", "96,83", Vector2i(96, 83)]]:
		location = probe.probe_location(maps, row[0], row[1])
		_check(location.get("map") == row[0] and location.get("tile") == row[2]
			and str(location.get("manifest", "")).ends_with("world.json"),
			"authored entry/boss anchor resolves: " + str(row))
	location = probe.probe_location(maps, "./maps/SUNMANE_GAUNTLET_2.elm", " 25, 319 ")
	_check(location.get("map") == "sunmane_gauntlet" and location.get("tile") == Vector2i(25, 319),
		"legacy names and aliases use the canonical map in state and reports")
	location = probe.probe_location(maps, "", "61,251")
	_check(location.get("map") == "landfall" and location.get("tile") == Vector2i(61, 251),
		"tile override works independently for the default map")
	for row: Array in [["missing-gauntlet", "25,319"], ["sunmane_gauntlet", ""],
		["sunmane_gauntlet", "25"], ["sunmane_gauntlet", "25,319,0"],
		["sunmane_gauntlet", "25.5,319"], ["sunmane_gauntlet", "25,no"],
		["sunmane_gauntlet", "25,"], ["sunmane_gauntlet", "-1,319"],
		["sunmane_gauntlet", "25,-1"], ["sunmane_gauntlet", "65536,319"],
		["sunmane_gauntlet", "25,65536"]]:
		_check(probe.probe_location(maps, row[0], row[1]).has("error"),
			"invalid destination is rejected before Main: " + str(row))
	_check(get_node_count() == before_nodes, "destination validation creates no scene or world nodes")
	print("CAMERA_PROBE_CONFIG_CHECKS checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

func _check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

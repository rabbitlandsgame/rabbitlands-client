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
	_pose_and_setting_checks(probe)
	print("CAMERA_PROBE_CONFIG_CHECKS checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

## Wave 2 WD-C0: the world-distance baseline poses, game minute, turns, settle
## and Graphics overrides, validated before Main exists.
func _pose_and_setting_checks(probe: Script) -> void:
	var plan: Dictionary = probe.probe_poses("", "")
	_check(plan.get("poses") == [{"distance": 14.0, "pitch": -60.0}],
		"unset distance and pitch keep the calibrated 14 m, -60 degree pose")
	plan = probe.probe_poses("", "-35")
	_check(plan.get("poses") == [{"distance": 14.0, "pitch": -35.0}], "a single pitch still works alone")
	plan = probe.probe_poses("26, 90", "-60,-35,-15")
	var expected := []
	for distance: float in [26.0, 90.0]:
		for pitch: float in [-60.0, -35.0, -15.0]:
			expected.append({"distance": distance, "pitch": pitch})
	_check(plan.get("poses") == expected, "the baseline matrix is distance-major: " + str(plan))
	for row: Array in [["0", ""], ["91", ""], ["26,26", ""], ["26;90", ""], ["nan", ""], ["inf", ""],
			["", "-10"], ["", "-81"], ["", "-60,-60"], ["", "x"], ["", "-60,"],
			["1.5,2,3,4,5", "-15,-20,-25,-30,-35"]]:
		_check(probe.probe_poses(row[0], row[1]).has("error"), "invalid pose list is rejected: " + str(row))
	_check(probe.probe_poses("1.5,90", "-80,-15").get("poses", []).size() == 4,
		"the rig's own distance and pitch limits are accepted")
	_check(probe.probe_minute("").get("value") == 600, "default minute keeps mid-morning sun shadows")
	_check(probe.probe_minute("0").get("value") == 0, "minute 0 is midnight")
	_check(probe.probe_minute(" 1439 ").get("value") == 1439, "last minute of the day")
	for text: String in ["-1", "1440", "6.5", "noon"]:
		_check(probe.probe_minute(text).has("error"), "invalid minute is rejected: " + text)
	_check(probe.probe_turns("").get("value") == 3, "three turns by default, as before")
	_check(probe.probe_turns("1").get("value") == 1 and probe.probe_turns("0").has("error")
		and probe.probe_turns("11").has("error"), "turns are 1..10")
	_check(probe.probe_pose_settle("").get("value") == 2000 and probe.probe_pose_settle("0").get("value") == 0
		and probe.probe_pose_settle("-5").has("error"), "pose settle defaults to 2 s and is non-negative")
	var graphics: Dictionary = probe.probe_graphics("")
	_check(graphics.get("overrides") == {}, "no Graphics overrides by default")
	graphics = probe.probe_graphics('{"quality":"low","appearance":"original","render_scale":0.75,"shadows":false}')
	_check(graphics.get("overrides", {}).get("appearance") == "original"
		and graphics.get("overrides", {}).get("quality") == "low",
		"appearance joins the supported Graphics controls for the Original-vs-Painted A/B")
	_check(probe.probe_graphics('{"appearance":"painted_ground"}').has("overrides")
		and probe.probe_graphics('{"appearance":"full_painted"}').has("overrides"), "every appearance mode is named")
	for text: String in ['[1]', '{"fps_limit":30}', '{"appearance":"sepia"}', '{"quality":"ultra"}', 'not json']:
		_check(probe.probe_graphics(text).has("error"), "invalid Graphics override is rejected: " + text)

func _check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

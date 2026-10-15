extends SceneTree
## Guards the look pass's per-map and per-region data
## (src/world/look/regions/<id>.json, read by LookProfile).
##
## Every shipped region file must parse with nothing unknown or mistyped in
## it and name itself; the pilot files must hold exactly the values the pass
## was reviewed with (they were constants in look_profile.gd until the files
## replaced them); a map without a file takes the defaults; renderer suffixes
## win in their renderer; colours arrive as Colors whatever JSON made of the
## numbers; the foliage lists extend every map's; and a continent region's
## grade trims are ignored.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.reload_regions()
	var forward := LookProfile.forward_plus()

	# --- Every shipped file ---------------------------------------------------
	var ids := LookProfile.region_ids()
	_expect(ids.has("lantern_reach") and ids.has("four_gates") and ids.has("amberwood"),
		"the pilot's region files ship (%s)" % ", ".join(ids))
	for id: String in ids:
		var problems := LookProfile.region_problems(id)
		_expect(problems.is_empty(), "%s.json is clean%s" % [id,
			"" if problems.is_empty() else ": " + "; ".join(problems)])
		_expect(str(LookProfile.region(id).get("id", "")) == id,
			"%s.json names itself" % id)
		_expect(LookProfile.region(id).is_read_only(), "%s's data is read-only" % id)

	# --- The pilot's values, exactly as reviewed -------------------------------
	_expect(LookProfile.map_trim("lantern_reach", "exposure") == (1.04 if forward else 1.6)
		and LookProfile.map_trim("lantern_reach", "saturation") == (1.15 if forward else 1.0)
		and LookProfile.map_trim("four_gates", "exposure") == 1.0
		and LookProfile.map_trim("no_such_map", "saturation") == 1.0,
		"Lantern Reach's grade trims, and none elsewhere")
	_expect(LookProfile.map_trim("lantern_reach", "exposure", true) == 1.0,
		"a continent region's grade section is ignored")
	var amber_tint: Variant = LookProfile.ground_value("amberwood", "path_tint",
		LookProfile.PATH_TINT)
	_expect(amber_tint is Color and amber_tint == Color(0.74, 0.62, 0.46)
		and LookProfile.ground_value("amberwood", "path_luma", -1.0) == 0.1
		and LookProfile.ground_value("amberwood", "verge_value_earth", -1.0) == 0.9
		and LookProfile.ground_value("four_gates", "path_tint", LookProfile.PATH_TINT)
			== LookProfile.PATH_TINT,
		"Amberwood's ground trims; Four Gates has none")
	_expect(LookProfile.ground_value("lantern_reach", "verge_value_green", -1.0)
			== (0.9 if forward else 0.82)
		and LookProfile.ground_value("lantern_reach", "verge_green_red", -1.0)
			== (0.55 if forward else -1.0)
		and LookProfile.ground_value("lantern_reach", "verge_saturation", -1.0)
			== (0.85 if forward else 0.92),
		"Lantern Reach's ground trims, the `_forward` ones in Forward+ only")
	var palettes := {
		"four_gates": [Color(0.09, 0.17, 0.06), Color(0.52, 0.62, 0.28), 1.2 if forward else 1.0],
		"amberwood": [Color(0.13, 0.1, 0.05), Color(0.56, 0.44, 0.23), 1.0],
		"lantern_reach": [Color(0.05, 0.14, 0.05), Color(0.4, 0.55, 0.22), 1.7 if forward else 0.9],
	}
	for id: String in palettes:
		var expected: Array = palettes[id]
		var palette := LookProfile.grass_palette(id)
		_expect(palette.get("root") == (expected[0] as Color) * float(expected[2])
			and palette.get("tip") == (expected[1] as Color) * float(expected[2]),
			"%s's grass palette and its value trim" % id)
	_expect(LookProfile.grass_palette("no_such_map").is_empty()
		and LookProfile.GRASS_PALETTE_DEFAULT.root == Color(0.09, 0.15, 0.06),
		"a map without a palette grows the default one")
	var reach_sky := LookProfile.sky_fallback("lantern_reach")
	var plain_sky := LookProfile.sky_fallback("no_such_map")
	_expect(reach_sky.top == Color(0.16, 0.42, 0.8) and reach_sky.horizon == Color(0.66, 0.82, 0.9)
		and plain_sky.top == Color("3d7ec2") and plain_sky.horizon == Color("bcc9cd"),
		"Lantern Reach's fallback sky; the binder's defaults elsewhere")
	LookProfile.define_region("dark_cave_test", {"id": "dark_cave_test", "schema": 1,
		"sky": {"paint": 0}})
	_expect(not LookProfile.sky_painted("dark_cave_test")
		and LookProfile.sky_painted("four_gates") and LookProfile.sky_painted("no_such_map"),
		"a map may keep its own dark sky (sky.paint 0); every other map's sky is painted")
	LookProfile.define_region("open_ground_test", {"id": "open_ground_test", "schema": 1,
		"grass": {"open": 0.6}})
	_expect(is_equal_approx(float(LookProfile.region_value("open_ground_test", "grass", "open",
			1.0)), 0.6) and LookProfile.grass_palette("open_ground_test").is_empty(),
		"a region's open ground may be less grassy, which gives it no palette of its own")
	_expect(LookProfile.water_decode_value("lantern_reach",
			"res://src/world/lantern_water.gdshader") == 2.5
		and LookProfile.water_decode_value("four_gates",
			"res://src/world/lantern_water.gdshader") == 0.0,
		"Lantern Reach's sea is decoded at 2.5, and only there")
	_expect(LookProfile.foliage_words("amberwood", "crown_materials")
			== LookProfile.CROWN_MATERIALS
		and LookProfile.foliage_words("", "tree_words") == LookProfile.KIT_TREE_WORDS,
		"a region without a foliage section uses every map's lists")

	# --- The schema ------------------------------------------------------------
	# JSON gives every number as a float, and Godot's Array == is type-strict
	# ([0.0, 0.0] != [0, 0]); the typed data must not care which one a value was.
	var parsed: Dictionary = JSON.parse_string(JSON.stringify({"id": "test_schema",
		"grass": {"root": [0, 1, 0], "tip": "#ffcc00", "value": 2},
		"ground": {"path_luma_compat": 0.3, "path_luma": 0.2, "path_tint": [1, 0.5, 0.25]},
		"foliage": {"crown_materials": ["foliage_green", "foliage_amber"],
			"shrub_words": ["tussock"]}}))
	var problems := LookProfile.define_region("test_schema", parsed)
	_expect(problems.is_empty(), "a good file has no problems (%s)" % "; ".join(problems))
	var palette := LookProfile.grass_palette("test_schema")
	_expect(palette.get("root") == Color(0, 1, 0) * 2.0 and palette.get("tip") == Color("#ffcc00") * 2.0,
		"colours from integer arrays and from hex, times an integer trim")
	_expect(LookProfile.ground_value("test_schema", "path_luma", -1.0)
			== (0.2 if forward else 0.3)
		and LookProfile.ground_value("test_schema", "path_tint", Color.BLACK) == Color(1, 0.5, 0.25),
		"`_compat` wins only in the compatibility renderer")
	var crowns := LookProfile.foliage_words("test_schema", "crown_materials")
	_expect(crowns.has("foliage_green") and crowns.count("foliage_amber") == 1
		and crowns.size() == LookProfile.CROWN_MATERIALS.size() + 1
		and LookProfile.foliage_words("test_schema", "shrub_words").has("tussock")
		and LookProfile.foliage_words("test_schema", "shrub_words").has("fern"),
		"a region's foliage lists extend every map's")
	var material := StandardMaterial3D.new()
	material.resource_name = "foliage_green"
	var atlas := StandardMaterial3D.new()
	atlas.resource_name = "kit_atlas"
	var schema_words := LookFoliage.words_for("test_schema")
	_expect(LookFoliage.kind_of("Tree_1_oak_Canopy", material, schema_words)
			== LookFoliage.Kind.CROWN
		and LookFoliage.kind_of("Tree_1_oak_Canopy", material) == LookFoliage.Kind.NONE
		and LookFoliage.kind_of("kit-tussock-3", atlas, schema_words) == LookFoliage.Kind.KIT_SHRUB
		and LookFoliage.kind_of("kit-tussock-3", atlas) == LookFoliage.Kind.NONE,
		"a region's crown materials and kit words count on its roots only")
	var bad := LookProfile.define_region("test_bad", {"id": "someone_else",
		"weather": {}, "ground": {"verge_value": 1.0, "path_luma": "bright",
			"path_tint": [1, 2]},
		"grass": {"layers_forward": {"moss": 1.0}, "layers": {"moss": "lots"}},
		"foliage": {"tree_words": "oak"}})
	for needle: String in ["someone_else", "unknown section \"weather\"",
			"unknown key \"ground.verge_value\"", "ground.path_luma", "ground.path_tint",
			"grass.layers_forward", "grass.layers\" is not", "foliage.tree_words"]:
		var found := false
		for problem: String in bad:
			found = found or problem.contains(needle)
		_expect(found, "a bad file's problems name %s" % needle)
	_expect(LookProfile.region_section("test_bad", "ground").is_empty()
		and LookProfile.ground_value("test_bad", "path_luma", -1.0) == (
			float(LookProfile.GROUND_FORWARD.path_luma) if forward else -1.0),
		"a bad value is left out, and the default is used")
	LookProfile.reload_regions()
	_expect(LookProfile.region("test_schema").is_empty(),
		"reload_regions forgets defined regions")

	print("test_look_regions: %s (%d failures)" % [
		"PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		push_error("FAIL " + message)

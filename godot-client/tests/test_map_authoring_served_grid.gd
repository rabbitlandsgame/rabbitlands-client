extends SceneTree
## The editor's reader of the server's 16-bit served grid ("ESCG version 2")
## and the play-test walker on it, against the golden fixture eloria-server
## pins: the decoder (header, row delta, CRC, SHA-256), the walk rule (any
## non-zero code walks, a 1.0 m climb, the corner rule) through every walk path
## of the walker, the server's route, a package's servedGrid block, and the
## live estimate's half-up quantisation. Version 1 grids keep their rule.
##
## Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##     --script res://tests/test_map_authoring_served_grid.gd

const ServedGrid := preload("res://addons/map_authoring_usability/served_grid.gd")
const Walker := preload("res://addons/map_authoring_usability/playtest_walker.gd")
const Walkability := preload("res://addons/map_authoring_usability/walkability_overlay.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
## Byte copies of eloria-server tests/fixtures/served_grid_golden.escg.gz, its
## description and the odd fixtures it lists. The SHA-256 of the .gz and of the
## JSON are literals here and in the server's tests/test_served_grid_format.py;
## neither test reads the other checkout, so a fixture or its answers changed on
## one side alone fail that side's suite. .gitattributes keeps the bytes exact.
const FIXTURES := "res://tests/fixtures"
const GOLDEN_PATH := "res://tests/fixtures/served_grid_golden.escg.gz"
const GOLDEN_JSON_PATH := "res://tests/fixtures/served_grid_golden.json"
const GOLDEN_SHA256 := "7e4522023885486b2a47298826b3fad1d30ba6d660dcc80249c8690d30e66c12"
const GOLDEN_JSON_SHA256 := "2b213842cba146059f59dcddba7ecb590b625d0aa70260fc5f5d3bcdc5b48eae"
const PACKAGE_DIR := "res://test-artifacts/served-grid"
const ORDER_DIR := "res://test-artifacts/served-grid-order"
## The size of a 2 km continent-v2 map, for the decode timing (target < 2 s).
const LARGE := 2046
## Set to time the walker's flood over that map too (about 3-7 s, no assertion).
const FLOOD_TIMING_ENV := "ELORIA_SERVED_GRID_FLOOD_TIMING"

var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var blob := FileAccess.get_file_as_bytes(GOLDEN_PATH)
	var description: Variant = JSON.parse_string(FileAccess.get_file_as_string(GOLDEN_JSON_PATH))
	_expect(not blob.is_empty() and description is Dictionary,
		"the golden fixture and its description are in res://tests/fixtures")
	if blob.is_empty() or not description is Dictionary:
		_finish()
		return
	_test_pin(blob, description)
	_test_odd_fixtures(description)
	var grid := ServedGrid.decode_file(blob, GOLDEN_SHA256)
	_expect(not grid.has("error"), "the golden fixture decodes (%s)" % String(grid.get("error", "ok")))
	if grid.has("error"):
		_finish()
		return
	_test_decode(grid, description)
	_test_reach(grid, description)
	_test_route(grid, description)
	_test_walk_paths()
	_test_flood_matches_the_step_rule()
	_test_refusals(blob)
	_test_declared_package(blob)
	_test_load_grid_order(blob)
	_test_live_estimate()
	_test_large_grid()
	_finish()


func _test_pin(blob: PackedByteArray, description: Dictionary) -> void:
	_expect(ServedGrid.sha256_hex(blob) == GOLDEN_SHA256 and
		String(description.get("sha256", "")) == GOLDEN_SHA256,
		"the client's copy of the golden fixture is the server's, by its pinned SHA-256")
	_expect(ServedGrid.sha256_hex(FileAccess.get_file_as_bytes(GOLDEN_JSON_PATH)) == GOLDEN_JSON_SHA256,
		"and so is its description, byte for byte (LF, as .gitattributes keeps it)")


## The server codec's own 5 x 7 files: an odd number of codes (the reader stops
## half way through its last 32-bit word) and row deltas that wrap both ways,
## gzipped with filter 1 and raw with filter 0 as an ELM block holds it.
func _test_odd_fixtures(description: Dictionary) -> void:
	var entries: Array = description.get("oddFixtures", [])
	var matching := 0
	var filters := {}
	for entry: Dictionary in entries:
		var data := FileAccess.get_file_as_bytes(FIXTURES.path_join(String(entry.file)))
		var grid := ServedGrid.decode_file(data, String(entry.sha256))
		if grid.has("error"):
			push_error("%s: %s" % [String(entry.file), String(grid.error)])
			continue
		var expected := PackedInt32Array(entry.codes)
		if (int(grid.width) == 5 and int(grid.height) == 7 and grid.codes == expected and
				int(grid.filter) == int(entry.filter) and expected.size() % 2 == 1 and
				ServedGrid.sha256_hex(ServedGrid.payload_bytes(grid.codes)) ==
					String(entry.decodedPayloadSha256)):
			matching += 1
			filters[int(grid.filter)] = true
	_expect(entries.size() == 2 and matching == 2 and filters.has(0) and filters.has(1),
		"the server's odd-sized fixtures decode to its codes with both filters (%d of %d)" % [matching,
			entries.size()])


func _test_decode(grid: Dictionary, description: Dictionary) -> void:
	_expect(int(grid.width) == int(description.width) and int(grid.height) == int(description.height) and
		int(grid.datum_mm) == int(description.datumMillimetres) and int(grid.datum_mm) == -100000 and
		int(grid.unit_mm) == int(description.unitMillimetres) and int(grid.unit_mm) == 50 and
		int(grid.climb_mm) == int(description.climbMillimetres) and int(grid.climb_mm) == 1000 and
		int(grid.climb_units) == int(description.climbUnits) and int(grid.climb_units) == 20 and
		int(grid.filter) == int(description.filter) and int(grid.filter) == 1,
		"the header reads as the server wrote it: 24 x 16, datum -100 m, 50 mm, climb 1.0 m, row delta")
	var codes: PackedInt32Array = grid.codes
	_expect(ServedGrid.sha256_hex(ServedGrid.payload_bytes(codes)) ==
		String(description.decodedPayloadSha256),
		"the decoded codes hash to the server's decoded payload (little-endian u16)")
	var matching := 0
	var seen := {}
	for sample: Dictionary in description.samples:
		if codes[int(sample.y) * int(grid.width) + int(sample.x)] == int(sample.code):
			matching += 1
		seen[int(sample.code)] = true
	_expect(matching == (description.samples as Array).size() and seen.has(64) and seen.has(128) and
		seen.has(4032) and seen.has(4096) and seen.has(32704),
		"every sample tile has the server's code (%d of %d), 64, 128, 4,032, 4,096 and 32,704 among them" %
			[matching, (description.samples as Array).size()])


## The reach from each seed, through the walker's flood and its reach tint.
func _test_reach(grid: Dictionary, description: Dictionary) -> void:
	var width := int(grid.width)
	var rows := int(grid.height)
	var codes: PackedInt32Array = grid.codes
	var flood_matches := 0
	var tint_matches := 0
	var walker := _walker(grid)
	for reach: Dictionary in description.reach:
		var seed := Vector2i(int(reach.seed[0]), int(reach.seed[1]))
		var seen := PackedByteArray()
		seen.resize(codes.size())
		var count := Walker._flood(codes, width, rows, seed.y * width + seed.x, seen,
			PackedInt32Array(), 1, int(grid.climb_units), Walker.WALK_BITS_V2)
		if count == int(reach.tiles) and ServedGrid.sha256_hex(seen) == String(reach.maskSha256):
			flood_matches += 1
		walker.show_reachable(true, seed)
		var tinted: PackedByteArray = walker.grid().get("reach_seen", PackedByteArray())
		if ServedGrid.sha256_hex(tinted) == String(reach.maskSha256):
			tint_matches += 1
	var reaches := (description.reach as Array).size()
	_expect(flood_matches == reaches and tint_matches == reaches,
		"the walker's flood and reach tint cover the server's tile set from every seed (%d, %d of %d)" % [
			flood_matches, tint_matches, reaches])
	var corridor: Dictionary = description.reach[0]
	_expect(Walker.largest_component(codes, width, rows, int(grid.climb_units), Walker.WALK_BITS_V2) ==
		int(corridor.tiles),
		"the largest connected area is the %d-tile corridor, dead end included" % int(corridor.tiles))


## The server's World.find_path route through the serpentine corridor.
func _test_route(grid: Dictionary, description: Dictionary) -> void:
	var walker := _walker(grid)
	var route: Dictionary = description.route
	var found: Array[Vector2i] = walker.search(Vector2i(int(route.start[0]), int(route.start[1])),
		Vector2i(int(route.goal[0]), int(route.goal[1])))
	var expected: Array[Vector2i] = []
	for tile: Array in route.tiles:
		expected.append(Vector2i(int(tile[0]), int(tile[1])))
	_expect(found == expected, "the walker's route equals the server's route tile for tile (%d steps)" %
		found.size())
	var dead_end: Dictionary = description.deadEnd
	var tile := Vector2i(int(dead_end.x), int(dead_end.y))
	var entered := false
	for direction: Vector2i in Walker.DIRECTIONS:
		if walker.step_allowed(tile + direction, tile):
			entered = true
	_expect(walker.is_walkable(tile) and entered and not found.has(tile) and
		not walker.can_step(tile + Vector2i(0, -1), tile),
		"the dead end is walkable and reachable but 21 codes off the row it would shortcut")


## Codes with zero low bits walk on version 2 through every walk path, and the
## climb is 20 codes (1.00 m) but not 21.
func _test_walk_paths() -> void:
	for code: int in [64, 128, 4096, 32704]:
		var codes := PackedInt32Array([code, code, code, code, code, code])
		var walker := Walker.new()
		walker.set("_grid", {"format": 2, "codes": codes, "width": 3, "rows": 2, "origin": Vector2i.ZERO,
			"climb": 20, "walk_bits": Walker.WALK_BITS_V2})
		var route: Array[Vector2i] = walker.search(Vector2i(0, 0), Vector2i(2, 1))
		var shown := walker.show_reachable(true, Vector2i(0, 0))
		var classes: PackedByteArray = walker.grid().get("reach_classes", PackedByteArray())
		_expect(walker.is_walkable(Vector2i(1, 1)) and walker.can_step(Vector2i(0, 0), Vector2i(1, 1)) and
			walker.step_allowed(Vector2i(0, 0), Vector2i(1, 1)) and
			Walker.largest_component(codes, 3, 2, 20, Walker.WALK_BITS_V2) == 6 and
			route.size() == 2 and route[route.size() - 1] == Vector2i(2, 1) and shown and
			classes.count(1) == 6,
			"code %d is walkable in is_walkable, can_step, the flood, the reach tint and the search" % code)
	var v1 := Walker.new()
	v1.set("_grid", {"codes": PackedByteArray([64, 64, 5, 5]), "width": 4, "rows": 1,
		"origin": Vector2i.ZERO})
	_expect(not v1.is_walkable(Vector2i(0, 0)) and v1.is_walkable(Vector2i(2, 0)) and
		v1.grid_climb() == 2 and Walker.largest_component(PackedByteArray([64, 64, 5, 5]), 4, 1) == 2,
		"a version 1 grid keeps the server's byte rule (h & 0x3F, a climb of 2) and byte arrays")
	var ramp := Walker.new()
	ramp.set("_grid", {"format": 2, "codes": PackedInt32Array([4000, 4020, 4041, 4041]), "width": 4,
		"rows": 1, "origin": Vector2i.ZERO, "climb": 20, "walk_bits": Walker.WALK_BITS_V2})
	_expect(ramp.can_step(Vector2i(0, 0), Vector2i(1, 0)) and ramp.can_step(Vector2i(1, 0), Vector2i(0, 0)) and
		not ramp.can_step(Vector2i(1, 0), Vector2i(2, 0)) and
		ramp.search(Vector2i(0, 0), Vector2i(3, 0)).is_empty(),
		"a rise of 20 codes (1.00 m) is a legal step and 21 (1.05 m) is not")
	# The corner rule: a diagonal needs both orthogonal steps from its start.
	var corner := Walker.new()
	corner.set("_grid", {"format": 2, "codes": PackedInt32Array([4000, 4100, 4000, 4000]), "width": 2,
		"rows": 2, "origin": Vector2i.ZERO, "climb": 20, "walk_bits": Walker.WALK_BITS_V2})
	var round_corner: Array[Vector2i] = [Vector2i(0, 1), Vector2i(1, 1)]
	_expect(corner.can_step(Vector2i(0, 0), Vector2i(1, 1)) and
		not corner.step_allowed(Vector2i(0, 0), Vector2i(1, 1)) and
		corner.search(Vector2i(0, 0), Vector2i(1, 1)) == round_corner,
		"a diagonal past a ledge corner is refused and the route goes round it")


## The flood writes the step test out inline for speed; it must reach exactly
## what _step_ok and the corner rule allow, on both versions' walk tests, with
## ledges at the climb and one past it, blocked tiles and one-way corners.
func _test_flood_matches_the_step_rule() -> void:
	var random := RandomNumberGenerator.new()
	random.seed = 20261003
	var agree := 0
	var cases := 0
	for trial in 24:
		var width := random.randi_range(1, 23)
		var rows := random.randi_range(1, 17)
		var version_two := trial % 2 == 0
		var climb := 20 if version_two else 2
		var bits := Walker.WALK_BITS_V2 if version_two else Walker.WALK_BITS_V1
		var codes := PackedInt32Array()
		codes.resize(width * rows)
		for index in codes.size():
			if random.randf() < 0.2:
				continue
			codes[index] = (4000 + random.randi_range(0, 3) * (climb / 2 + random.randi_range(0, 1))) \
				if version_two else random.randi_range(1, 7) * (64 if random.randf() < 0.1 else 1)
		for start in [0, codes.size() / 2, codes.size() - 1]:
			cases += 1
			var seen := PackedByteArray()
			seen.resize(codes.size())
			var count := Walker._flood(codes, width, rows, start, seen, PackedInt32Array(), 1, climb, bits)
			var expected := _plain_flood(codes, width, rows, start, climb, bits)
			if seen == expected and count == expected.count(1):
				agree += 1
	_expect(agree == cases,
		"the flood reaches exactly what the step rule and the corner rule allow (%d of %d)" % [agree, cases])


## The flood as the step rule reads: every direction through _step_ok, a
## diagonal also through both orthogonal steps from its start.
func _plain_flood(codes: PackedInt32Array, width: int, rows: int, start: int, climb: int,
		bits: int) -> PackedByteArray:
	var seen := PackedByteArray()
	seen.resize(codes.size())
	seen[start] = 1
	var queue: Array[int] = [start]
	while not queue.is_empty():
		var current: int = queue.pop_back()
		var cx := current % width
		var cy := current / width
		for direction: Vector2i in Walker.DIRECTIONS:
			var nx := cx + direction.x
			var ny := cy + direction.y
			if nx < 0 or ny < 0 or nx >= width or ny >= rows or seen[ny * width + nx] != 0:
				continue
			var here := codes[current]
			var ok := Walker._step_ok(codes, width, codes.size(), cx, cy, nx, ny, here, climb, bits)
			if ok and direction.x != 0 and direction.y != 0:
				ok = Walker._step_ok(codes, width, codes.size(), cx, cy, nx, cy, here, climb, bits) and \
					Walker._step_ok(codes, width, codes.size(), cx, cy, cx, ny, here, climb, bits)
			if ok:
				seen[ny * width + nx] = 1
				queue.append(ny * width + nx)
	return seen


func _test_refusals(blob: PackedByteArray) -> void:
	var tampered := blob.duplicate()
	tampered[blob.size() / 2] = tampered[blob.size() / 2] ^ 0x01
	var refused := ServedGrid.decode_file(tampered, GOLDEN_SHA256)
	_expect(refused.has("error") and "SHA-256" in String(refused.error),
		"a tampered file is refused by its SHA-256 (%s)" % String(refused.get("error", "accepted")))
	_expect(ServedGrid.decode_file(tampered).has("error"),
		"and refused without a declared hash too, by the gzip or the grid's own CRC")
	var raw := blob.decompress(blob.decode_u32(blob.size() - 4), FileAccess.COMPRESSION_GZIP)
	var keywords := ["not a served grid", "version", "header size", "filter", "flags", "reserved",
		"does not divide", "dimensions", "CRC"]
	var refusals := 0
	var notes := PackedStringArray()
	for keyword: String in keywords:
		var result := ServedGrid.decode(_mutated(raw, keyword))
		if result.has("error") and keyword in String(result.error):
			refusals += 1
		else:
			notes.append("%s: %s" % [keyword, String(result.get("error", "accepted"))])
	var truncated := ServedGrid.decode(raw.slice(0, raw.size() - 2))
	var trailing := raw.duplicate()
	trailing.append_array(PackedByteArray([0, 0]))
	var after := ServedGrid.decode(trailing)
	var high := ServedGrid.decode(_encode(PackedInt32Array([4000, 40000]), 2, 1, 0))
	_expect(refusals == keywords.size() and "truncated" in String(truncated.get("error", "")) and
		"after its payload" in String(after.get("error", "")) and
		"exceeds" in String(high.get("error", "")),
		"the header, payload and CRC refusals of the server's reader all hold%s" % (
			"" if notes.is_empty() else " except " + ", ".join(notes)))
	# Bytes after the gzip stream. decompress_dynamic never returned on these in
	# Godot 4.7 (the editor froze when the play test started); the reader now
	# sizes its inflate from the member's length field and refuses them at once,
	# as the server's reader does.
	var padded := blob.duplicate()
	padded.append_array(PackedByteArray([0, 0, 0, 0]))
	var garbage := blob.duplicate()
	garbage.append_array("garbage!".to_ascii_buffer())
	var two_members := PackedByteArray([1, 2, 3]).compress(FileAccess.COMPRESSION_GZIP)
	two_members.append_array(blob)
	var cut := blob.slice(0, blob.size() - 9)
	var started := Time.get_ticks_msec()
	var after_stream := 0
	for bad: PackedByteArray in [padded, garbage, two_members, cut]:
		if "gzip" in String(ServedGrid.decode_file(bad).get("error", "")):
			after_stream += 1
	_expect(after_stream == 4 and Time.get_ticks_msec() - started < 2000,
		"padding, garbage or a second member after the gzip stream, and a cut stream, are refused at once (%d of 4, %d ms)" % [
			after_stream, Time.get_ticks_msec() - started])
	# Dimensions whose product passes 2^63 wrapped negative and slipped past the
	# size checks into an out-of-bounds write and a script error in the caller.
	var huge := raw.slice(0, ServedGrid.HEADER_SIZE)
	huge.encode_u32(8, 2147516416)
	huge.encode_u32(12, 4294901761)
	var payload := PackedByteArray()
	payload.resize(65536)
	huge.append_array(payload)
	var wrapped := ServedGrid.decode(huge)
	_expect("truncated" in String(wrapped.get("error", "")),
		"dimensions whose product overflows are refused as a truncated payload (%s)" % String(
			wrapped.get("error", "accepted")))
	var raw_filter := ServedGrid.decode(_encode(PackedInt32Array([64, 4096, 0, 32704, 128, 1]), 3, 2, 0))
	_expect(not raw_filter.has("error") and int(raw_filter.filter) == 0 and
		raw_filter.codes == PackedInt32Array([64, 4096, 0, 32704, 128, 1]),
		"filter 0 (the ELM block's raw payload) decodes too")


## A package that declares its served grid in world.json, as the walker loads it.
func _test_declared_package(blob: PackedByteArray) -> void:
	var directory := ProjectSettings.globalize_path(PACKAGE_DIR)
	DirAccess.make_dir_recursive_absolute(directory)
	var manifest_path := PACKAGE_DIR + "/world.json"
	var spec := {"binary": "served-grid.escg.gz", "format": "ESCG-v2", "unitMetres": 0.05,
		"climbMetres": 1.0, "originMetres": -100.0, "sha256": GOLDEN_SHA256}
	var manifest := {"collision": {"binary": "collision.bin", "servedGrid": spec},
		"portals": [{"serverTile": [3, 1], "label": "Gate"}]}
	_write_json(manifest_path, manifest)
	_write_bytes(PACKAGE_DIR + "/served-grid.escg.gz", blob)
	var loaded := Walker.load_served_grid(manifest_path, Vector2i(5, 7))
	_expect(String(loaded.get("source", "")) == "published" and int(loaded.get("format", 0)) == 2 and
		int(loaded.get("climb", 0)) == 20 and int(loaded.get("walk_bits", 0)) == Walker.WALK_BITS_V2 and
		int(loaded.get("width", 0)) == 24 and int(loaded.get("rows", 0)) == 16 and
		loaded.get("origin") == Vector2i(5, 7) and is_equal_approx(float(loaded.unit_metres), 0.05) and
		is_equal_approx(float(loaded.datum_metres), -100.0) and
		(loaded.get("crossings", {}) as Dictionary).has(Vector2i(3, 1)),
		"a package's servedGrid loads as the server's tiles, climb and walk rule, with its portals")
	var walker := Walker.new()
	walker.set("_grid", loaded)
	walker.set("_position", Vector3(1.5 - 5.0, 0.0, 7.0 - 1.5))
	var description := walker.grid_description()
	_expect(walker.cell_of(Vector3(1.5 - 5.0, 0.0, 7.0 - 1.5)) == Vector2i(1, 1) and
		is_equal_approx(walker.cell_point(Vector2i(1, 1)).y, -100.0 + 4032 * 0.05) and
		"served grid" in description and "climb 1.00 m" in description,
		"the walker stands on the tile's own 50 mm height and says which grid it walks (%s)" % description)
	# The frame the package states must be the scene's: a stale server_origin
	# (D2b moved sw_isle's by 30 tiles) or another size is refused, not walked.
	var frame := {"serverOrigin": [5, 7], "serverCells": [24, 16], "metresPerTile": 1.0,
		"invertServerY": true}
	var framed := manifest.duplicate(true)
	framed["coordinateTransform"] = frame
	_write_json(manifest_path, framed)
	var aligned := Walker.load_served_grid(manifest_path, Vector2i(5, 7))
	var stale := Walker.load_served_grid(manifest_path, Vector2i(5, 37))
	var refusals := {}
	for change: Dictionary in [{"serverCells": [2046, 2046]}, {"metresPerTile": 2.0},
			{"invertServerY": false}]:
		framed["coordinateTransform"] = frame.merged(change, true)
		_write_json(manifest_path, framed)
		refusals[change.keys()[0]] = Walker.load_served_grid(manifest_path, Vector2i(5, 7))
	_expect(int(aligned.get("format", 0)) == 2 and not aligned.has("error") and
		"serverOrigin" in String(stale.get("error", "")) and "(5, 37)" in String(stale.get("error", "")) and
		not bool(stale.get("missing", false)) and
		"24 x 16" in String((refusals.serverCells as Dictionary).get("error", "")) and
		"metresPerTile" in String((refusals.metresPerTile as Dictionary).get("error", "")) and
		"invertServerY" in String((refusals.invertServerY as Dictionary).get("error", "")),
		"a package framed as the scene loads; a stale server_origin, another size, scale or y sense is refused (%s)" %
			String(stale.get("error", "accepted")))
	_write_json(manifest_path, {"collision": {"servedGrid": spec.merged({"sha256": "0".repeat(64)}, true)}})
	var wrong_hash := Walker.load_served_grid(manifest_path, Vector2i.ZERO)
	_write_json(manifest_path, {"collision": {"servedGrid": spec.merged({"climbMetres": 1.2}, true)}})
	var wrong_climb := Walker.load_served_grid(manifest_path, Vector2i.ZERO)
	_write_json(manifest_path, {"collision": {"servedGrid": spec.merged({"binary": "absent.escg.gz"},
		true)}})
	var missing := Walker.load_served_grid(manifest_path, Vector2i.ZERO)
	_write_json(manifest_path, {"collision": {"binary": "collision.bin"}})
	var version_one := Walker.load_served_grid(manifest_path, Vector2i.ZERO)
	# As strict as the sync: a binary must be named, and the hash compares
	# exactly (the sync's hexdigest is lowercase).
	var unnamed := spec.duplicate()
	unnamed.erase("binary")
	_write_json(manifest_path, {"collision": {"servedGrid": unnamed}})
	var no_binary := Walker.load_served_grid(manifest_path, Vector2i.ZERO)
	_write_json(manifest_path, {"collision": {"servedGrid": spec.merged({"sha256": GOLDEN_SHA256.to_upper()},
		true)}})
	var upper := Walker.load_served_grid(manifest_path, Vector2i.ZERO)
	_expect("names no binary" in String(no_binary.get("error", "")) and
		not bool(no_binary.get("missing", false)) and "SHA-256" in String(upper.get("error", "")),
		"a servedGrid naming no binary, or an uppercase hash, is refused as the sync refuses it")
	_expect("SHA-256" in String(wrong_hash.get("error", "")) and
		"climbMetres" in String(wrong_climb.get("error", "")) and
		bool(missing.get("missing", false)) and version_one.is_empty(),
		"a wrong hash or climb is refused, a missing file is reported, and no servedGrid means version 1")
	for name in ["world.json", "served-grid.escg.gz"]:
		DirAccess.remove_absolute(directory.path_join(name))
	DirAccess.remove_absolute(directory)


## The live estimate of a version 2 territory: codes from the terrain heights,
## rounded half up as the codec does (0.125 m is 2,002.5 codes: 2,003, where
## half to even would give 2,002).
func _test_live_estimate() -> void:
	var heights := PackedFloat32Array()
	heights.resize(5 * 4)
	heights.fill(0.125)
	var owned := Image.create(4, 3, false, Image.FORMAT_RGBA8)
	owned.fill(Color(1.0, 1.0, 1.0, 1.0))
	var classes := PackedByteArray()
	classes.resize(12)
	classes.fill(Walkability.Tile.WALKABLE)
	classes[5] = Walkability.Tile.BLOCKED
	var live := {"classes": classes, "owned": owned, "tile": 1.0, "width": 4, "rows": 3, "x0": 0.0,
		"z0": -3.0, "heights": heights, "grid": Vector2i(5, 4), "cell": 1.0, "terrain_x0": 0.0,
		"terrain_z0": -3.0}
	var served := Walker.fold_live(live, Vector2i.ZERO, null, 2)
	var codes: PackedInt32Array = served.get("codes", PackedInt32Array())
	var legacy := Walker.fold_live(live, Vector2i.ZERO, null)
	_expect(int(served.get("format", 0)) == 2 and int(served.get("climb", 0)) == 20 and
		codes.size() == 12 and codes.count(2003) == 11 and codes.count(0) == 1 and
		int(legacy.get("format", 0)) == 1 and int(legacy.get("climb", 0)) == 2 and
		ServedGrid.quantise_mm(-100000.0 + 2.5 * 50.0 - 1e-9) == 3 and
		ServedGrid.quantise_mm(-100000.0 + 3.4999 * 50.0) == 3 and
		ServedGrid.quantise_mm(-100000.0 - 0.5 * 50.0) == 0,
		"the live estimate quantises half up to 50 mm codes for version 2 and keeps version 1 apart")


## Decode time for a 2 km map's grid (plan target: under 2 s); the walker's
## flood over it only when FLOOD_TIMING_ENV is set.
func _test_large_grid() -> void:
	var codes := PackedInt32Array()
	codes.resize(LARGE * LARGE)
	for y in LARGE:
		var row := y * LARGE
		for x in LARGE:
			# Gentle relief (under the climb) with a blocked lattice every 64 tiles.
			codes[row + x] = 0 if (x % 64 == 0 and y % 3 == 0) else 2000 + (x + 2 * y) % 400 / 25
	var blob := _encode(codes, LARGE, LARGE, 1).compress(FileAccess.COMPRESSION_GZIP)
	var sha := ServedGrid.sha256_hex(blob)
	var started := Time.get_ticks_usec()
	var decoded := ServedGrid.decode_file(blob, sha)
	var decode_ms := float(Time.get_ticks_usec() - started) / 1000.0
	var same: bool = not decoded.has("error") and decoded.codes == codes
	var flood := "walker flood not timed (set %s=1)" % FLOOD_TIMING_ENV
	if not OS.get_environment(FLOOD_TIMING_ENV).is_empty():
		started = Time.get_ticks_usec()
		var seen := PackedByteArray()
		seen.resize(codes.size())
		var reached := Walker._flood(codes, LARGE, LARGE, LARGE + 1, seen, PackedInt32Array(), 1, 20,
			Walker.WALK_BITS_V2)
		flood = "walker flood of %d tiles %.0f ms" % [reached,
			float(Time.get_ticks_usec() - started) / 1000.0]
	print("served grid %d x %d: %d KiB gzipped, decode %.0f ms (SHA-256, gunzip, row delta, CRC), " %
		[LARGE, LARGE, blob.size() / 1024, decode_ms] + flood)
	_expect(same and decode_ms < 2000.0,
		"a %d x %d grid decodes exactly in %.0f ms (target under 2 s)" % [LARGE, LARGE, decode_ms])


## load_grid's order, driven through its manifest path on a small region root:
## a declared served grid wins; a refused one stops the play test rather than
## falling back; one the package does not ship is estimated with the version
## 2 rules; a manifest with no servedGrid is a version 1 territory.
func _test_load_grid_order(blob: PackedByteArray) -> void:
	var directory := ProjectSettings.globalize_path(ORDER_DIR)
	DirAccess.make_dir_recursive_absolute(directory)
	var heights_path := ORDER_DIR + "/heights.f32le"
	var heights := FileAccess.open(heights_path, FileAccess.WRITE)
	for index in 9 * 7:
		heights.store_float(0.125)
	heights.close()
	var root: Node3D = REGION.new()
	root.name = "ServedGridOrderFixture"
	root.set("region_id", "served_grid_order_fixture")
	root.set("metres_per_tile", 1.0)
	root.set("server_origin", Vector2i(5, 7))
	var terrain: Node3D = TERRAIN.new()
	terrain.name = "Terrain"
	terrain.set("origin", Vector2.ZERO)
	terrain.set("grid_size", Vector2i(9, 7))
	terrain.set("cell_metres", 1.0)
	terrain.set("base_heights_path", heights_path)
	terrain.set("preview_enabled", false)
	root.add_child(terrain)
	for container in ["Roads", "Rivers", "Bridges", "AuthoredAssets", "Gameplay", "GeneratedPreview"]:
		var node := Node3D.new()
		node.name = container
		root.add_child(node)
	get_root().add_child(root)
	var manifest_path := ORDER_DIR + "/world.json"
	var spec := {"binary": "served-grid.escg.gz", "format": "ESCG-v2", "sha256": GOLDEN_SHA256}
	_write_bytes(ORDER_DIR + "/served-grid.escg.gz", blob)
	_write_json(manifest_path, {"collision": {"servedGrid": spec}})
	var served := Walker.load_grid(root, manifest_path)
	_write_json(manifest_path, {"collision": {"servedGrid": spec.merged({"sha256": "0".repeat(64)}, true)}})
	var refused := Walker.load_grid(root, manifest_path)
	_write_json(manifest_path, {"collision": {"servedGrid": spec.merged({"binary": "absent.escg.gz"},
		true)}})
	var estimated := Walker.load_grid(root, manifest_path)
	_write_json(manifest_path, {"collision": {"binary": "collision.bin"}})
	var version_one := Walker.load_grid(root, manifest_path)
	root.free()
	for name in ["world.json", "served-grid.escg.gz", "heights.f32le"]:
		DirAccess.remove_absolute(directory.path_join(name))
	DirAccess.remove_absolute(directory)
	var codes: PackedInt32Array = estimated.get("codes", PackedInt32Array())
	_expect(String(served.get("source", "")) == "published" and int(served.get("format", 0)) == 2 and
		int(served.get("width", 0)) == 24 and
		"SHA-256" in String(refused.get("error", "")) and not refused.has("format") and
		String(estimated.get("source", "")) == "live" and int(estimated.get("format", 0)) == 2 and
		int(estimated.get("climb", 0)) == 20 and codes.count(2003) > 0 and
		codes.count(2003) + codes.count(0) == codes.size() and
		String(version_one.get("source", "")) == "live" and int(version_one.get("format", 0)) == 1 and
		int(version_one.get("climb", 0)) == 2,
		"load_grid takes the served grid, refuses a bad one, estimates a missing one with the version 2 rules, and keeps version 1 without one (%s; %s; %s; %s)" % [
			String(served.get("source", served.get("error", "?"))), String(refused.get("error", "accepted")),
			String(estimated.get("error", "format %d, %d codes of 2003" % [int(estimated.get("format", 0)),
				codes.count(2003)])),
			String(version_one.get("error", "format %d" % int(version_one.get("format", 0))))])


func _walker(grid: Dictionary) -> Walker:
	var walker := Walker.new()
	walker.set("_grid", {"source": "published", "format": 2, "codes": grid.codes,
		"width": int(grid.width), "rows": int(grid.height), "origin": Vector2i.ZERO,
		"climb": int(grid.climb_units), "walk_bits": Walker.WALK_BITS_V2, "unit_metres": 0.05,
		"datum_metres": -100.0, "stage_metres": 0.05})
	return walker


## The golden grid's uncompressed bytes with one header field broken, named by
## a word of the refusal it must cause.
func _mutated(raw: PackedByteArray, keyword: String) -> PackedByteArray:
	var bytes := raw.duplicate()
	match keyword:
		"not a served grid":
			bytes[0] = 0x58
		"version":
			bytes.encode_u16(4, 1)
		"header size":
			bytes.encode_u16(6, 24)
		"filter":
			bytes.encode_u8(24, 2)
		"flags":
			bytes.encode_u8(25, 1)
		"reserved":
			bytes.encode_u16(26, 1)
		"does not divide":
			bytes.encode_u16(20, 30)
		"dimensions":
			bytes.encode_u32(8, 0)
		"CRC":
			bytes.encode_u32(28, bytes.decode_u32(28) ^ 1)
	return bytes


## An uncompressed served grid as the server's codec writes it.
func _encode(codes: PackedInt32Array, width: int, height: int, filter: int) -> PackedByteArray:
	var header := PackedByteArray()
	header.resize(ServedGrid.HEADER_SIZE)
	header.encode_u32(0, 0x47435345)  # "ESCG"
	header.encode_u16(4, ServedGrid.VERSION)
	header.encode_u16(6, ServedGrid.HEADER_SIZE)
	header.encode_u32(8, width)
	header.encode_u32(12, height)
	header.encode_s32(16, ServedGrid.DATUM_MM)
	header.encode_u16(20, ServedGrid.UNIT_MM)
	header.encode_u16(22, ServedGrid.CLIMB_MM)
	header.encode_u8(24, filter)
	header.encode_u32(28, ServedGrid.crc32(ServedGrid.payload_bytes(codes)))
	var stored := codes
	if filter == ServedGrid.FILTER_ROW_DELTA:
		stored = PackedInt32Array()
		stored.resize(codes.size())
		for y in height:
			var previous := 0
			for x in width:
				var value := codes[y * width + x]
				stored[y * width + x] = (value - previous) & 0xFFFF
				previous = value
	header.append_array(ServedGrid.payload_bytes(stored))
	return header


func _write_json(path: String, value: Variant) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(value))
	file.close()


func _write_bytes(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	failures += 1
	push_error("FAIL: " + message)
	return false


func _finish() -> void:
	print("map authoring served grid: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

extends SceneTree
## Guards the look pass's region borders (LookBorders), which fade a region's
## ground trims and grass palette into its neighbour's instead of stepping at
## the border.
##
## Both sides of a border must evaluate the same blend at the same spot (the
## neighbour's weight on one side is the other's own share), so a road or a
## field running across it never steps; the blend must reach a half on the
## border line and nothing a feather inside either region; and the continent's
## real regions must find the borders they share.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var feather := LookProfile.BORDER_FEATHER_METRES

	# --- Two squares side by side on the 2 m grid, one wound backwards -------
	LookBorders.define({
		"west": [[0, 0], [100, 0], [100, 100], [0, 100]],
		"east": [[100, 0], [100, 100], [200, 100], [200, 0]],
	})
	_expect(LookBorders.neighbours_of("west") == PackedStringArray(["east"])
		and LookBorders.neighbours_of("east") == PackedStringArray(["west"]),
		"two regions that share an edge are each other's neighbours")
	var area := Rect2(40, 0, 120, 100)
	var west := LookBorders.near("west", area, feather)
	var east := LookBorders.near("east", area, feather)
	_expect(west.segments.size() > 0 and east.segments.size() == west.segments.size(),
		"both sides are handed the border (%d, %d segments)"
		% [west.segments.size(), east.segments.size()])
	var worst := 0.0
	for x: float in [60.0, 80.0, 90.0, 99.0, 100.0, 101.0, 110.0, 130.0, 150.0]:
		for z: float in [10.0, 50.0, 90.0]:
			var here := Vector2(x, z)
			var west_other := _weight(here, west)
			var east_other := _weight(here, east)
			# West paints west * (1 - w) + east * w; east paints east * (1 - v)
			# + west * v. They agree when w = 1 - v.
			worst = maxf(worst, absf(west_other - (1.0 - east_other)))
	_expect(worst < 0.0001, "both sides blend to the same colour anywhere (worst %.5f)" % worst)
	_expect(absf(_weight(Vector2(100, 50), west) - 0.5) < 0.0001,
		"the two meet at their mean on the border line")
	_expect(_weight(Vector2(100.0 - feather, 50), west) < 0.0001
		and _weight(Vector2(100.0 + feather, 50), east) < 0.0001,
		"each is wholly its own a feather inside")
	_expect(_weight(Vector2(100.0 + feather, 50), west) > 0.9999,
		"a region's material inside its neighbour takes the neighbour's look")
	_expect(LookBorders.near("west", Rect2(0, 0, 20, 100), feather).segments.is_empty(),
		"a chunk away from every border is handed none")
	_expect(LookBorders.near("nowhere", area, feather).segments.is_empty(),
		"a map off the continent is handed none")

	# --- A staircase border, as the ownership polygons draw them ------------
	var stairs_west: Array = [[0, 0]]
	var stairs_east: Array = []
	for step: int in 20:
		stairs_west.append([60 + step * 2, step * 2])
		stairs_west.append([60 + step * 2, step * 2 + 2])
	stairs_west.append([0, 40])
	stairs_east.append([200, 0])
	stairs_east.append([200, 40])
	for step: int in range(19, -1, -1):
		stairs_east.append([60 + step * 2, step * 2 + 2])
		stairs_east.append([60 + step * 2, step * 2])
	LookBorders.define({"west": stairs_west, "east": stairs_east})
	var stair_area := Rect2(40, 0, 80, 40)
	west = LookBorders.near("west", stair_area, feather)
	east = LookBorders.near("east", stair_area, feather)
	_expect(west.segments.size() >= 1 and west.segments.size() <= 4,
		"a staircase border is simplified to a few segments (%d)" % west.segments.size())
	worst = 0.0
	for x: float in range(50, 110, 3):
		for z: float in range(1, 40, 3):
			worst = maxf(worst, absf(_weight(Vector2(x, z), west)
				- (1.0 - _weight(Vector2(x, z), east))))
	_expect(worst < 0.0001, "a staircase border blends the same from both sides (worst %.5f)"
		% worst)

	# --- Regions in different continent frames never share a border ---------
	LookBorders.define({
		"west": [[0, 0], [100, 0], [100, 100], [0, 100]],
		"east": [[100, 0], [100, 100], [200, 100], [200, 0]],
		"v2_east": [[100, 0], [100, 100], [200, 100], [200, 0]],
	}, {"v2_east": "continent-v2"})
	_expect(LookBorders.neighbours_of("west") == PackedStringArray(["east"])
		and LookBorders.neighbours_of("v2_east").is_empty(),
		"a region of another continent frame on the same ground borders nothing there")

	# --- The continent's own regions ----------------------------------------
	LookBorders.reload()
	var neighbours := LookBorders.neighbours_of("four_gates")
	_expect(neighbours.has("amberwood") and neighbours.has("westhaven")
		and neighbours.has("manymouth_delta") and neighbours.has("mirrorhold"),
		"Four Gates borders Amberwood, Westhaven, Manymouth and Mirrorhold (%s)"
		% ", ".join(neighbours))
	_expect(LookBorders.neighbours_of("verdant_stair").has("ssarathi_ruins"),
		"Verdant Stair borders Ssarathi")
	_expect(LookBorders.neighbours_of("lantern_reach").is_empty(),
		"Lantern Reach, an island off the continent, borders nothing")
	_test_partition_borders()

	print("test_look_borders: %s (%d failures)" % ["PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

## Read the authored exact polygons independently of Look's registry reader.
## Every component contributes edges, including disconnected islands.
func _test_partition_borders() -> void:
	var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://world_authoring/continent-v2/territories.json"))
	_expect(catalog is Dictionary, "the active Look catalog parses")
	if catalog is not Dictionary:
		return
	var partition: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(catalog.partitionSpecPath))) as Dictionary
	var expected_ids := PackedStringArray()
	for section: Dictionary in partition.sections:
		expected_ids.append(str(section.get("mapId", section.id)))
	expected_ids.sort()
	var polygons := {}
	for entry: Dictionary in catalog.entries:
		var stub: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(entry.manifestPath))) as Dictionary
		var geography: Dictionary = stub.get("continentGeography", {})
		var rings: Array = geography.get("ownershipPolygons", [geography.get("ownershipPolygon", [])])
		_expect(not rings.is_empty(), "%s has its complete ownership rings" % str(entry.id))
		polygons[str(entry.id)] = rings
	var ids: Array = polygons.keys()
	ids.sort()
	var actual_ids := PackedStringArray(ids)
	_expect(actual_ids == expected_ids and not ids.is_empty(), "Look covers every exact partition section")
	var shared := {}
	for id: String in ids:
		shared[id] = {}
	var pairs := 0
	for ia: int in ids.size():
		var first := String(ids[ia])
		for ib: int in range(ia + 1, ids.size()):
			var second := String(ids[ib])
			var edges := _shared_edges(polygons[first], polygons[second])
			if edges.is_empty():
				continue
			pairs += 1
			shared[first][second] = edges
			shared[second][first] = edges
	_expect(pairs > 0, "the partition has real shared borders (%d pairs)" % pairs)
	for id: String in ids:
		var expected_neighbours := PackedStringArray((shared[id] as Dictionary).keys())
		expected_neighbours.sort()
		var actual_neighbours := LookBorders.neighbours_of(id)
		actual_neighbours.sort()
		_expect(actual_neighbours == expected_neighbours, "%s finds all and only exact polygon neighbours" % id)
		var actual_segments := {}
		for border: Dictionary in LookBorders._borders.get(id, []):
			var neighbour := String(border.neighbour)
			var keys := PackedStringArray()
			for segment: Vector4 in border.segments:
				keys.append(_edge_key(Vector2(segment.x, segment.y), Vector2(segment.z, segment.w)))
				var point := Vector2((segment.x + segment.z) * 0.5, (segment.y + segment.w) * 0.5)
				var own := {"neighbours": PackedStringArray([neighbour]), "slots": PackedFloat32Array([0]),
					"segments": PackedVector4Array([segment])}
				var reverse := {"neighbours": PackedStringArray([id]), "slots": PackedFloat32Array([0]),
					"segments": PackedVector4Array([Vector4(segment.z, segment.w, segment.x, segment.y)])}
				var direction := (Vector2(segment.z, segment.w) - Vector2(segment.x, segment.y)).normalized()
				var normal := Vector2(-direction.y, direction.x)
				var reciprocal := absf(_weight(point, own) - 0.5) < 0.0001
				for offset: float in [-30.0, -1.0, 1.0, 30.0]:
					reciprocal = reciprocal and absf(_weight(point + normal * offset, own)
						+ _weight(point + normal * offset, reverse) - 1.0) < 0.0001
				_expect(reciprocal, "%s / %s border paints reciprocal weights" % [id, neighbour])
			keys.sort()
			actual_segments[neighbour] = keys
		for neighbour: String in expected_neighbours:
			_expect(actual_segments.get(neighbour, PackedStringArray()) == shared[id][neighbour],
				"%s / %s uses every exact shared segment" % [id, neighbour])
			var expected_reverse := PackedStringArray()
			for border: Dictionary in LookBorders._borders.get(id, []):
				if String(border.neighbour) == neighbour:
					for segment: Vector4 in border.segments:
						expected_reverse.append(_directed_edge_key(Vector2(segment.z, segment.w), Vector2(segment.x, segment.y)))
			expected_reverse.sort()
			var reverse_keys := PackedStringArray()
			for border: Dictionary in LookBorders._borders.get(neighbour, []):
				if String(border.neighbour) == id:
					for segment: Vector4 in border.segments:
						reverse_keys.append(_directed_edge_key(Vector2(segment.x, segment.y), Vector2(segment.z, segment.w)))
			reverse_keys.sort()
			_expect(reverse_keys == expected_reverse, "%s / %s shares reversed reciprocal geometry" % [id, neighbour])
		_expect(not LookBorders.neighbours_of("westhaven").has(id), "%s has no legacy continent border" % id)
	for retired: String in catalog.get("retiredMapIds", []):
		_expect(LookBorders.neighbours_of(retired).is_empty(), "retired %s has no active Look borders" % retired)


func _directed_edge_key(a: Vector2, b: Vector2) -> String:
	return "%.3f,%.3f/%.3f,%.3f" % [a.x, a.y, b.x, b.y]


func _edge_key(a: Vector2, b: Vector2) -> String:
	if a.x > b.x or (is_equal_approx(a.x, b.x) and a.y > b.y):
		var swap := a
		a = b
		b = swap
	return "%.3f,%.3f/%.3f,%.3f" % [a.x, a.y, b.x, b.y]


## A positive collinear overlap of two edges is a border; point contact is not.
func _shared_edges(first: Array, second: Array) -> PackedStringArray:
	var result := PackedStringArray()
	for a: Array in first:
		for i: int in a.size():
			var start := Vector2(float(a[i][0]), float(a[i][1]))
			var finish := Vector2(float(a[(i + 1) % a.size()][0]), float(a[(i + 1) % a.size()][1]))
			var length := start.distance_to(finish)
			if length < 0.0001:
				continue
			var direction := (finish - start) / length
			for b: Array in second:
				for j: int in b.size():
					var p := Vector2(float(b[j][0]), float(b[j][1]))
					var q := Vector2(float(b[(j + 1) % b.size()][0]), float(b[(j + 1) % b.size()][1]))
					if absf(direction.cross(p - start)) > 0.0001 or absf(direction.cross(q - start)) > 0.0001:
						continue
					var lo := maxf(0.0, minf(direction.dot(p - start), direction.dot(q - start)))
					var hi := minf(length, maxf(direction.dot(p - start), direction.dot(q - start)))
					if hi - lo > 0.0001:
						result.append(_edge_key(start + direction * lo, start + direction * hi))
	result.sort()
	return result


## How much of the (one) neighbour `selection` holds the look takes at `xz`.
func _weight(xz: Vector2, selection: Dictionary) -> float:
	var weights := LookBorders.weights(xz, selection)
	return weights[0] if weights.size() > 0 else 0.0

func _expect(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		failures += 1

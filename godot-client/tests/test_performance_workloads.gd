extends SceneTree
## Data/selection contracts; no Main, imports, GPU work or network connection.
## The route checks read the published registry, exterior seams and streamed
## chunk bounds, so a moved map or seam that would turn a fixture tile into an
## uncovered (re-priming) or wrongly continuous arrival fails here first.
const Workloads := preload("res://tests/integration/performance_workloads.gd")
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
const REGISTRY := "res://data/maps/registry.json"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check(Benchmark.cells_for("phase4").size() == 12, "legacy phase4 membership is unchanged")
	_check(Benchmark.cells_for("quick").size() == 2, "legacy quick membership is unchanged")
	var phase_one := Benchmark.cells_for("phase1")
	_check(phase_one.size() == 7, "phase1 selects its seven required workloads")
	_check(Benchmark.cells_for("mixed-mounted-160").size() == 1, "mounted cell selects directly")
	_check(Benchmark.cells_for("authored-herd").size() == 1, "herd support remains independently selectable")
	_check(Workloads.resolution("1920x1080") == Vector2i(1920, 1080), "resolution is parsed")
	_check(Workloads.resolution("bad") == Vector2i(1280, 720), "malformed resolution has a safe default")
	var records := {}
	for index: int in range(160):
		records[14000 + index] = {"actor_id": 14000 + index, "name": "Synthetic rider %d" % index}
	var mounts := Workloads.mount_rows(records, 80, "four_gates")
	_check(mounts.size() == 80 and mounts.has(14000), "exactly80 mounts include the local actor")
	var counts := Workloads.mount_profile_counts(mounts)
	_check(counts == {"crystalback_tortoise": 14, "giant_rat": 14,
		"golden_plains_horse": 13, "jadefeather_raptor": 13, "moor_pony": 13, "rabbit": 13},
		"original six-profile cohort includes five native profiles and the Giant Rat fallback")
	for id: int in mounts:
		var row := mounts[id] as Dictionary
		_check(row.owner == records[id].name and row.map == records[id].map,
			"mount ownership/map matches the synthetic actor")
		_check(Workloads.MountProfiles.supports(str(row.mount_id)), "mount comes from the supported profile catalog")
	var route := Workloads.southern_route()
	var kinds := {}
	var ids := {}
	for leg: Dictionary in route:
		_check(not ids.has(leg.id), "route leg ids are unique")
		ids[leg.id] = true
		kinds[leg.kind] = true
		_check((leg.start as Array).size() == 2 and (leg.arrival as Array).size() == 2,
			"route coordinates are explicit public fixture coordinates")
	_check(route.size() == 6 and kinds.has("border") and kinds.has("interior")
		and kinds.has("interior_return") and kinds.has("teleport") and kinds.has("teleport_return"),
		"route covers consecutive borders, interior, teleport and return")
	_check(route[0].map == route[-1].destination, "route returns to its starting territory")
	# Route version 2 (wave 2 AW-00).
	_check(Workloads.ROUTE_VERSION == 2, "route fixture version is 2")
	_check(route[0].start == route[-1].arrival, "the route returns to its start tile, so a warm repeat loads nothing")
	var relocations := 0
	for index: int in range(1, route.size()):
		_check(route[index].map == route[index - 1].destination,
			"%s starts on the map %s arrived on" % [route[index].id, route[index - 1].id])
		if bool(route[index].get("relocateStart", false)):
			relocations += 1
			continue
		_check(route[index].start == route[index - 1].arrival,
			"%s starts where %s arrived (no harness relocation inside a map)" % [route[index].id, route[index - 1].id])
	_check(relocations == 1 and bool(route.filter(func(leg: Dictionary) -> bool: return leg.kind == "interior")[0]
		.get("relocateStart", false)), "only the interior entry relocates (a curtain arrival beside its door cannot ground)")
	var interior: Dictionary = route.filter(func(leg: Dictionary) -> bool: return leg.kind == "interior")[0]
	_check(interior.start != interior.approach, "the interior leg walks up to its door")
	var seam := Workloads.seam_route()
	_check(seam.size() == 1 and seam[0].id == "walking-seam" and seam[0].kind == "seam"
		and bool(seam[0].get("expectContinuous", false)), "the seam route is one expected-continuous walking crossing")
	_check(seam[0].destination == route[0].map and seam[0].arrival == route[0].start,
		"the seam walk arrives on the southern route's start tile")
	_check(Workloads.step_msec(seam[0]) == Workloads.CRUISE_STEP_MSEC and Workloads.CRUISE_STEP_MSEC == 133
		and Workloads.step_msec(route[0]) == Workloads.WALK_STEP_MSEC and Workloads.WALK_STEP_MSEC == 600,
		"the seam walk cruises at 7.5 tiles/s; the other legs walk at the historical 600 ms step")
	_check(Workloads.route("seam") == seam and Workloads.route("southern") == route
		and Workloads.route("") == route, "route ids select their fixtures; southern is the default")
	var traversal := Benchmark.cells_for("traversal")
	_check(traversal.size() == 3 and traversal.all(func(cell: Dictionary) -> bool: return cell.shape == "traversal"),
		"the traversal profile selects the cold, warm and seam traversal cells")
	var seam_cell := Benchmark.cells_for("traversal-seam-walk")
	_check(seam_cell.size() == 1 and str(seam_cell[0].get("routeId", "")) == "seam",
		"the seam cell selects directly and drives the seam route")
	_check(not Benchmark.cells_for("all").any(func(cell: Dictionary) -> bool: return cell.id == "traversal-seam-walk"),
		"the historical all profile keeps its membership")
	_check(Benchmark.cells_for("traversal-southern-cold")[0].get("routeId", "southern") == "southern",
		"the southern cells keep the southern route")
	# The Landfall underground round trip (wave-2 memory measurement): explicit only.
	var underground := Workloads.underground_route()
	_check(Workloads.route("underground") == underground and underground.size() == 4
		and underground.map(func(leg: Dictionary) -> String: return str(leg.id)) == [
			"underground-entry", "underground-exit", "underground-reentry", "underground-reexit"],
		"the underground route is in, out, in and out")
	for index: int in range(1, underground.size()):
		_check(underground[index].map == underground[index - 1].destination
			and underground[index].start == underground[index - 1].arrival,
			"%s starts where %s arrived" % [underground[index].id, underground[index - 1].id])
	_check(underground.all(func(leg: Dictionary) -> bool:
			return (str(leg.kind) == "interior_return") == (int(leg.get("dwellMsec", 0)) > 0)),
		"every exit, and only an exit, holds the player on arrival")
	_check(underground[0].start != underground[0].approach
		and Benchmark.cells_for("traversal-underground-roundtrip").size() == 1
		and str(Benchmark.cells_for("traversal-underground-roundtrip")[0].get("routeId", "")) == "underground"
		and not Benchmark.cells_for("traversal").any(func(cell: Dictionary) -> bool:
			return str(cell.id) == "traversal-underground-roundtrip"),
		"the underground cell walks up to the door, selects directly and stays out of the traversal profile")
	_check_route_against_maps(route + seam + underground)
	print("PERFORMANCE_WORKLOAD_CHECKS failures=", failures)
	quit(1 if failures else 0)


## Every territory tile a leg stands on is inside a streamed chunk (an uncovered
## tile re-primes on every world sync and never grounds); the seam walk's path
## is covered, starts beyond 160 m of the seam, ends within the crossing slack
## and arrives on the tile across it; other approaches stay outside the slack of
## their destination's seam, so they remain curtain map changes.
func _check_route_against_maps(legs: Array) -> void:
	var parsed: Variant = _json(REGISTRY)
	_check(parsed is Dictionary, "map registry parses")
	if not parsed is Dictionary:
		return
	var registry: Dictionary = (parsed as Dictionary).get("maps", {})
	var links := _links()
	for leg: Dictionary in legs:
		var origin := _map(registry, str(leg.map))
		var destination := _map(registry, str(leg.destination))
		if not _check(not origin.is_empty() and not destination.is_empty(), "%s: both maps resolve" % leg.id):
			continue
		var start := Workloads.tile(leg.start)
		var approach := Workloads.tile(leg.approach)
		var arrival := Workloads.tile(leg.arrival)
		_check(_covered(origin, start), "%s: start %s is on a streamed cell" % [leg.id, start])
		_check(_covered(origin, approach), "%s: approach %s is on a streamed cell" % [leg.id, approach])
		_check(_covered(destination, arrival), "%s: arrival %s is on a streamed cell" % [leg.id, arrival])
		var join := _join(links, str(leg.map), str(leg.destination))
		var approach_at: Vector3 = (origin.adapter as CoordinateAdapter).tile_center(approach.x, approach.y)
		if str(leg.kind) != "seam":
			if not join.is_empty():
				_check(not ExteriorRegionStream.continuous_crossing(bool(join.seamless),
					_handoff_distance(approach_at, join), _collar(join)),
					"%s: the approach is outside the continuous-crossing slack of its destination" % leg.id)
			continue
		if not _check(not join.is_empty() and bool(join.seamless), "%s: a seamless link joins its maps" % leg.id):
			continue
		var at_seam := _handoff_distance(approach_at, join)
		_check(at_seam <= 2.0 and ExteriorRegionStream.continuous_crossing(true, at_seam, _collar(join)),
			"%s: the approach is on the seam (%.2f m)" % [leg.id, at_seam])
		var start_at: Vector3 = (origin.adapter as CoordinateAdapter).tile_center(start.x, start.y)
		_check(_handoff_distance(start_at, join) >= 160.0, "%s: the walk starts beyond 160 m of the seam" % leg.id)
		var step := Vector2i(signi(approach.x - start.x), signi(approach.y - start.y))
		var path_covered := true
		var tile := start
		while tile != approach:
			path_covered = path_covered and _covered(origin, tile)
			tile += Vector2i(signi(approach.x - tile.x), signi(approach.y - tile.y))
		_check(path_covered and step != Vector2i.ZERO, "%s: every walked tile is on a streamed cell" % leg.id)
		var here: Dictionary = join.here
		var there: Dictionary = join.there
		var across := ExteriorRegionStream.frame_transform(here.frame, there.frame).affine_inverse() * approach_at
		var arrival_at: Vector3 = (destination.adapter as CoordinateAdapter).tile_center(arrival.x, arrival.y)
		var gap := Vector2(across.x - arrival_at.x, across.z - arrival_at.z).length()
		_check(gap <= 1.5, "%s: the arrival is the tile across the seam (%.2f m)" % [leg.id, gap])


## The seam joining `from` to `to` as the client sees it from `from`
## (ExteriorRegionStream._candidates): {"here", "there", "seamless"}.
static func _join(links: Array, from: String, to: String) -> Dictionary:
	for link: Dictionary in links:
		var ends: Array = link.get("ends", [])
		for index: int in ends.size():
			if str(ends[index].map) == from and str(ends[1 - index].map) == to:
				return {"here": ends[index], "there": ends[1 - index], "seamless": bool(link.get("seamless", false))}
	return {}


## What ExteriorRegionStream.take_ready measures a crossing by.
static func _handoff_distance(position: Vector3, join: Dictionary) -> float:
	var here: Dictionary = join.here
	if not (here.get("preloadEdges", []) as Array).is_empty():
		return ExteriorRegionStream._seam_distance(position, here, bool(join.seamless))
	var at := ExteriorRegionStream._vector(here.position)
	return Vector2(position.x - at.x, position.z - at.z).length()


static func _collar(join: Dictionary) -> float:
	return float((join.here as Dictionary).get("frame", {}).get("collarDepth", 42))


static func _links() -> Array:
	var links: Array = []
	for path: String in [ExteriorRegionStream.CONNECTIONS, ExteriorRegionStream.CONTINENT_V2_CONNECTIONS]:
		var raw: Variant = _json(path)
		if raw is Dictionary:
			links.append_array((raw as Dictionary).get("connections", []))
			links.append_array((raw as Dictionary).get("visualConnections", []))
	return links


## {"adapter", "chunks"} for a registered map; chunks is empty for a whole map.
static func _map(registry: Dictionary, map_id: String) -> Dictionary:
	var entry: Variant = registry.get(map_id)
	if not entry is Dictionary:
		return {}
	var manifest: Variant = _json(ProjectSettings.globalize_path(str((entry as Dictionary).get("manifest", ""))))
	if not manifest is Dictionary:
		return {}
	var streaming: Dictionary = (manifest as Dictionary).get("streamingChunks", {})
	return {"adapter": CoordinateAdapter.new((entry as Dictionary).get("coordinateTransform", {})),
		"chunks": streaming.get("chunks", [])}


## Whether a streamed map has a cell whose bounds hold the tile's centre
## (ContinentChunkStream.arrival_resident); a whole map always does.
static func _covered(map: Dictionary, tile: Vector2i) -> bool:
	var chunks: Array = map.chunks
	if chunks.is_empty():
		return true
	var at: Vector3 = (map.adapter as CoordinateAdapter).tile_center(tile.x, tile.y)
	for chunk: Dictionary in chunks:
		if ContinentChunkStream.bounds_distance(at, chunk.bounds) <= .01:
			return true
	return false


static func _json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _check(ok: bool, label: String) -> bool:
	if not ok:
		failures += 1
		push_error(label)
	return ok

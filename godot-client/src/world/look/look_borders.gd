class_name LookBorders
extends RefCounted
## Look pass: where the continent's regions meet, so that a region's own look
## (its ground trims, its grass palette) fades into its neighbour's across the
## border instead of stepping at it.
##
## A region's ground trims are baked into its chunks' painted materials. Where
## a road or a field runs on unchanged into the neighbour, two regions with
## different trims drew their border as a straight (or cell-stepped) line
## across it: Ssarathi's laterite road against Verdant's cream, Amberwood's
## dim ochre against Four Gates' dust, a Whitehorn snow trim against the same
## snow in Amberwood's blend. Every region agent of the migration had to
## choose between its own look and a seam.
##
## So every painted ground material near a border is handed that border, as a
## few straight segments, and each neighbour's trims. The paint works out a
## signed distance to the border (positive on its own side) and blends its
## trims towards the neighbour's by 1 - smoothstep(-F, F, distance), where F
## is LookProfile.BORDER_FEATHER_METRES. On the border line both regions are
## at the mean of the two; F metres inside either, each is its own. Both sides
## evaluate the same function of position (the neighbour's material sees the
## same segments reversed), so the blend is continuous wherever the chunks'
## meshes actually end - which is the ownership polygon's 2 m staircase, not
## the simplified line.
##
## The borders come from the ownership polygons in the regions' manifests
## (continentGeography.ownershipPolygon, continent metres on a 2 m grid):
## every polygon's boundary is cut into one-metre steps, a step owned by two
## regions is shared border, the shared runs are chained in the smaller
## region id's boundary order and simplified to within
## LookProfile.BORDER_SIMPLIFY_METRES. The segments are worked out once per
## pair and read by both regions, so the two sides never disagree. Read on
## first use, on whichever thread paints first, behind a lock.

const REGISTRY_PATH := "res://data/maps/registry.json"
const OWNERSHIP_GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")

static var _mutex := Mutex.new()
static var _loaded := false
## Region id -> PackedVector2Array: its ownership polygon, continent metres.
static var _polygons: Dictionary = {}
static var _components: Dictionary = {}
## Region id -> its registry geography's continent frame ("" for the
## twelve-territory continent): regions in different frames share continent
## coordinates but never a border.
static var _frames: Dictionary = {}
## Region id -> Array of {"neighbour": String, "segments": PackedVector4Array
## (a.x, a.z, b.x, b.z)}, each segment oriented so the region lies on its
## left (cross(b - a, p - a) > 0).
static var _borders: Dictionary = {}

## The borders of `region` that come within `margin` metres of `rect`
## (continent x, z), as the paint takes them: at most
## LookProfile.BORDER_SEGMENTS_MAX segments (the nearest, when there are
## more) and LookProfile.BORDER_NEIGHBOURS_MAX neighbours.
##   segments  PackedVector4Array, oriented with `region` on the left
##   slots     PackedFloat32Array, the index into `neighbours` of each segment
##   neighbours PackedStringArray
## Empty arrays away from every border, and off the continent.
static func near(region: String, rect: Rect2, margin: float) -> Dictionary:
	var result := {"segments": PackedVector4Array(), "slots": PackedFloat32Array(),
		"neighbours": PackedStringArray()}
	if region.is_empty():
		return result
	_ensure()
	var borders: Variant = _borders.get(region)
	if borders is not Array:
		return result
	var area := rect.grow(margin)
	var centre := rect.get_center()
	var found: Array[Dictionary] = []
	for border: Dictionary in borders:
		var neighbour := String(border.neighbour)
		for segment: Vector4 in (border.segments as PackedVector4Array):
			var a := Vector2(segment.x, segment.y)
			var b := Vector2(segment.z, segment.w)
			var box := Rect2(a, Vector2.ZERO).expand(b)
			if not box.grow(0.01).intersects(area):
				continue
			found.append({"segment": segment, "neighbour": neighbour,
				"distance": _distance(centre, a, b)})
	if found.is_empty():
		return result
	found.sort_custom(func(x: Dictionary, y: Dictionary) -> bool:
		return float(x.distance) < float(y.distance))
	# Filled as locals and stored at the end: a packed array read out of a
	# Dictionary is a copy, so appending to it there would be lost.
	var segments := PackedVector4Array()
	var slots := PackedFloat32Array()
	var neighbours := PackedStringArray()
	for entry: Dictionary in found:
		if segments.size() >= LookProfile.BORDER_SEGMENTS_MAX:
			break
		var neighbour := String(entry.neighbour)
		var slot := neighbours.find(neighbour)
		if slot < 0:
			if neighbours.size() >= LookProfile.BORDER_NEIGHBOURS_MAX:
				continue
			neighbours.append(neighbour)
			slot = neighbours.size() - 1
		segments.append(entry.segment)
		slots.append(float(slot))
	result.segments = segments
	result.slots = slots
	result.neighbours = neighbours
	return result

## How much of each neighbour in `selection` (from `near`) the look takes at
## `xz`, as the paint shader works it out (look_border_weights): per
## neighbour, 1 - smoothstep(-feather, feather, signed distance to its
## border), scaled down together when they add up to more than 1.
static func weights(xz: Vector2, selection: Dictionary,
		feather := LookProfile.BORDER_FEATHER_METRES) -> PackedFloat32Array:
	var neighbours: PackedStringArray = selection.get("neighbours", PackedStringArray())
	var result := PackedFloat32Array()
	result.resize(neighbours.size())
	if neighbours.is_empty():
		return result
	var best := PackedFloat32Array()
	var side := PackedFloat32Array()
	best.resize(neighbours.size())
	side.resize(neighbours.size())
	best.fill(INF)
	side.fill(1.0)
	var segments: PackedVector4Array = selection.segments
	var slots: PackedFloat32Array = selection.slots
	for index: int in segments.size():
		var segment := segments[index]
		var a := Vector2(segment.x, segment.y)
		var b := Vector2(segment.z, segment.w)
		var slot := int(slots[index])
		var distance := _distance(xz, a, b)
		if distance < best[slot]:
			best[slot] = distance
			side[slot] = 1.0 if (b - a).cross(xz - a) >= 0.0 else -1.0
	var total := 0.0
	for slot: int in neighbours.size():
		if best[slot] == INF:
			continue
		result[slot] = 1.0 - smoothstep(-feather, feather, side[slot] * best[slot])
		total += result[slot]
	if total > 1.0:
		for slot: int in neighbours.size():
			result[slot] /= total
	return result

## Every region with an ownership polygon, and the regions it borders.
static func neighbours_of(region: String) -> PackedStringArray:
	_ensure()
	var result := PackedStringArray()
	var borders: Variant = _borders.get(region)
	if borders is Array:
		for border: Dictionary in borders:
			if String(border.neighbour) not in result:
				result.append(String(border.neighbour))
	return result

## Uses `polygons` (region id -> Array of [x, z] points, continent metres)
## instead of the manifests' until `reload`, each in the continent frame
## `frames` names for it (none: the twelve-territory continent); for tests.
static func define(polygons: Dictionary, frames := {}) -> void:
	_mutex.lock()
	_polygons.clear()
	_components.clear()
	_frames.clear()
	for id: Variant in polygons:
		var raw: Variant = polygons[id]
		var rings: Array[PackedVector2Array] = []
		if raw is PackedVector2Array:
			rings = OWNERSHIP_GEOMETRY.polygons(raw)
		elif raw is Array and not raw.is_empty() and raw[0] is Array and not raw[0].is_empty():
			rings = OWNERSHIP_GEOMETRY.polygons([raw] if raw[0][0] is int or raw[0][0] is float else raw)
		if rings.is_empty():
			continue
		_components[String(id)] = rings
		_polygons[String(id)] = rings[0]
		_frames[String(id)] = str(frames.get(id, ""))
	_build()
	_loaded = true
	_mutex.unlock()

## Forgets the borders, so the next use reads the manifests again.
static func reload() -> void:
	_mutex.lock()
	_loaded = false
	_polygons.clear()
	_components.clear()
	_frames.clear()
	_borders.clear()
	_mutex.unlock()

static func _ensure() -> void:
	_mutex.lock()
	if not _loaded:
		_loaded = true
		_load_polygons()
		_build()
	_mutex.unlock()

## Every continent region's ownership polygon, from the manifests the map
## registry names (each read once, whatever aliases point at it).
static func _load_polygons() -> void:
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string(REGISTRY_PATH))
	if registry is not Dictionary:
		return
	var maps: Variant = (registry as Dictionary).get("maps")
	if maps is not Dictionary:
		return
	var read := {}
	for key: Variant in maps:
		var entry: Variant = (maps as Dictionary)[key]
		if entry is not Dictionary or not (entry as Dictionary).has("continentGeography"):
			continue
		var path := str((entry as Dictionary).get("manifest", ""))
		if path.is_empty() or read.has(path):
			continue
		read[path] = true
		var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if manifest is not Dictionary:
			continue
		var geography: Variant = (manifest as Dictionary).get("continentGeography")
		var asset: Variant = (manifest as Dictionary).get("asset")
		if geography is not Dictionary or asset is not Dictionary:
			continue
		var rings := OWNERSHIP_GEOMETRY.from_geography(geography as Dictionary)
		var id := str((asset as Dictionary).get("id", ""))
		if not rings.is_empty() and not id.is_empty():
			_polygons[id] = rings[0]
			_components[id] = rings
			_frames[id] = str(((entry as Dictionary).get("continentGeography") as Dictionary).get("frame", ""))

static func _points(raw: Variant) -> PackedVector2Array:
	var points := PackedVector2Array()
	if raw is not Array:
		return points
	for point: Variant in raw:
		if point is Array and (point as Array).size() >= 2:
			points.append(Vector2(float(point[0]), float(point[1])))
	return points

## The shared borders of every pair of regions, from their polygons.
static func _build() -> void:
	_borders.clear()
	# Every one-metre step of every boundary, keyed by its midpoint on a
	# half-metre grid: the polygons share a 2 m grid, so a step two regions
	# both have lands on the same key.
	var owners := {}
	var steps := {}
	for id: String in _polygons:
		if str(_frames.get(id, "")) == "continent-v2" or (_components.get(id, []) as Array).size() > 1:
			continue
		var list: Array[Dictionary] = []
		var polygon: PackedVector2Array = _polygons[id]
		for index: int in polygon.size():
			var a := polygon[index]
			var b := polygon[(index + 1) % polygon.size()]
			var count := maxi(1, roundi(a.distance_to(b)))
			for step: int in count:
				var start := a.lerp(b, float(step) / count)
				var end := a.lerp(b, float(step + 1) / count)
				var key: Variant = _key((start + end) * 0.5)
				var frame := str(_frames.get(id, ""))
				if not frame.is_empty():
					key = "%s|%s" % [frame, str(key)]
				if not owners.has(key):
					owners[key] = []
				(owners[key] as Array).append(id)
				list.append({"start": start, "end": end, "key": key})
		steps[id] = list
	for id: String in _polygons:
		_borders[id] = []
	for id: String in _polygons:
		if not steps.has(id):
			continue
		var list: Array = steps[id]
		var count := list.size()
		if count == 0:
			continue
		var neighbour_at := PackedStringArray()
		neighbour_at.resize(count)
		for index: int in count:
			var other := ""
			for owner: Variant in owners[list[index].key]:
				if String(owner) != id:
					other = String(owner)
			neighbour_at[index] = other
		# Start where a run begins, so no run wraps past the list's end.
		var first := 0
		for index: int in count:
			if neighbour_at[index] != neighbour_at[(index - 1 + count) % count]:
				first = index
				break
		var area := _signed_area(_polygons[id])
		var index := 0
		while index < count:
			var at := (first + index) % count
			var neighbour := neighbour_at[at]
			var run := PackedVector2Array([list[at].start])
			while index < count and neighbour_at[(first + index) % count] == neighbour:
				run.append(list[(first + index) % count].end)
				index += 1
			# Each pair is worked out once, from the smaller id's boundary, and
			# read by both; empty is the coast or the continent's edge.
			if neighbour.is_empty() or id > neighbour:
				continue
			var simple := _simplify(run, LookProfile.BORDER_SIMPLIFY_METRES)
			var own := PackedVector4Array()
			var theirs := PackedVector4Array()
			for point: int in simple.size() - 1:
				var a := simple[point]
				var b := simple[point + 1]
				# A polygon wound with positive area has its inside on the left.
				if area < 0.0:
					var swap := a
					a = b
					b = swap
				own.append(Vector4(a.x, a.y, b.x, b.y))
				theirs.append(Vector4(b.x, b.y, a.x, a.y))
			(_borders[id] as Array).append({"neighbour": neighbour, "segments": own})
			(_borders[neighbour] as Array).append({"neighbour": id, "segments": theirs})
	_build_exact_components()

## Exact edge intersections support angled borders and disconnected components.
## The established staircase simplifier above remains the legacy single-ring path.
static func _build_exact_components() -> void:
	var ids: Array = _components.keys()
	ids.sort()
	for ia: int in ids.size():
		var first := String(ids[ia])
		var a_rings: Array = _components[first]
		for ib: int in range(ia + 1, ids.size()):
			var second := String(ids[ib])
			var b_rings: Array = _components[second]
			if str(_frames.get(first, "")) != str(_frames.get(second, "")):
				continue
			if str(_frames.get(first, "")) != "continent-v2" and a_rings.size() == 1 and b_rings.size() == 1:
				continue
			var own := PackedVector4Array()
			var theirs := PackedVector4Array()
			for a: PackedVector2Array in a_rings:
				var area := _signed_area(a)
				for ai: int in a.size():
					var p := a[ai]
					var d := a[(ai + 1) % a.size()] - p
					var length_squared := d.length_squared()
					if length_squared < 0.000001:
						continue
					for b: PackedVector2Array in b_rings:
						for bi: int in b.size():
							var q := b[bi]
							var end := b[(bi + 1) % b.size()]
							if absf(d.cross(q-p)) / sqrt(length_squared) > 0.0001 or absf(d.cross(end-p)) / sqrt(length_squared) > 0.0001:
								continue
							var t0 := (q-p).dot(d) / length_squared
							var t1 := (end-p).dot(d) / length_squared
							var lo := maxf(0.0,minf(t0,t1))
							var hi := minf(1.0,maxf(t0,t1))
							if (hi-lo) * sqrt(length_squared) < 0.0001:
								continue
							var start := p + d * lo
							var finish := p + d * hi
							if area < 0.0:
								var swap := start
								start = finish
								finish = swap
							own.append(Vector4(start.x,start.y,finish.x,finish.y))
							theirs.append(Vector4(finish.x,finish.y,start.x,start.y))
			if not own.is_empty():
				(_borders[first] as Array).append({"neighbour":second,"segments":own})
				(_borders[second] as Array).append({"neighbour":first,"segments":theirs})

static func _key(point: Vector2) -> Vector2i:
	return Vector2i(roundi(point.x * 2.0), roundi(point.y * 2.0))

static func _signed_area(polygon: PackedVector2Array) -> float:
	var area := 0.0
	for index: int in polygon.size():
		var a := polygon[index]
		var b := polygon[(index + 1) % polygon.size()]
		area += a.x * b.y - b.x * a.y
	return area * 0.5

## Douglas-Peucker: the run's points kept to within `tolerance` metres.
static func _simplify(points: PackedVector2Array, tolerance: float) -> PackedVector2Array:
	if points.size() <= 2:
		return points
	var keep := PackedByteArray()
	keep.resize(points.size())
	keep[0] = 1
	keep[points.size() - 1] = 1
	var stack: Array[Vector2i] = [Vector2i(0, points.size() - 1)]
	while not stack.is_empty():
		var span: Vector2i = stack.pop_back()
		var farthest := -1.0
		var at := -1
		for index: int in range(span.x + 1, span.y):
			var distance := _distance(points[index], points[span.x], points[span.y])
			if distance > farthest:
				farthest = distance
				at = index
		if at >= 0 and farthest > tolerance:
			keep[at] = 1
			stack.append(Vector2i(span.x, at))
			stack.append(Vector2i(at, span.y))
	var result := PackedVector2Array()
	for index: int in points.size():
		if keep[index] == 1:
			result.append(points[index])
	return result

## Distance from `p` to the segment ab.
static func _distance(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var length_squared := ab.length_squared()
	if length_squared < 0.000001:
		return p.distance_to(a)
	var t := clampf((p - a).dot(ab) / length_squared, 0.0, 1.0)
	return p.distance_to(a + ab * t)

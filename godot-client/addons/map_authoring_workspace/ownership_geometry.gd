@tool
extends RefCounted
## Ordered ownership components. Their union is authoritative; empty gaps stay
## outside. A single ring keeps its existing serialization and SHA unchanged.

static func polygons(value: Variant) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	if value is PackedVector2Array:
		if value.size() >= 3:
			for point in value:
				if not point.is_finite():
					return []
			result.append(value)
		return result
	if not value is Array:
		return result
	for raw: Variant in value:
		var polygon := PackedVector2Array()
		if raw is PackedVector2Array:
			polygon = raw
		elif raw is Array:
			for point: Variant in raw:
				if not point is Array or point.size() != 2:
					return []
				var parsed := Vector2(float(point[0]), float(point[1]))
				if not parsed.is_finite():
					return []
				polygon.append(parsed)
		for point in polygon:
			if not point.is_finite():
				return []
		if polygon.size() < 3:
			return []
		result.append(polygon)
	return result

static func from_entry(entry: Dictionary) -> Array[PackedVector2Array]:
	return polygons(entry.get("ownership_polygons", entry.get("ownership_polygon", PackedVector2Array())))

static func from_geography(geography: Dictionary) -> Array[PackedVector2Array]:
	if geography.has("ownershipPolygons"):
		return polygons(geography.ownershipPolygons)
	return polygons([geography.get("ownershipPolygon", [])])

static func contains(point: Vector2, rings: Array[PackedVector2Array]) -> bool:
	for polygon in rings:
		if Geometry2D.is_point_in_polygon(point, polygon):
			return true
	return false

static func edge_distance(point: Vector2, rings: Array[PackedVector2Array]) -> float:
	var distance := INF
	for polygon in rings:
		for edge in polygon.size():
			var a := polygon[edge]
			var segment := polygon[(edge + 1) % polygon.size()] - a
			var amount := clampf((point - a).dot(segment) / maxf(segment.length_squared(), 0.000001), 0.0, 1.0)
			distance = minf(distance, point.distance_to(a + segment * amount))
	return distance

static func bounds(rings: Array[PackedVector2Array]) -> Rect2:
	if rings.is_empty():
		return Rect2()
	var result := Rect2(rings[0][0], Vector2.ZERO)
	for polygon in rings:
		for point in polygon:
			result = result.expand(point)
	return result

static func local(rings: Array[PackedVector2Array], translation: Vector3) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []
	for polygon in rings:
		var ring := PackedVector2Array()
		for point in polygon:
			ring.append(point - Vector2(translation.x, translation.z))
		result.append(ring)
	return result

static func hash(rings: Array[PackedVector2Array]) -> String:
	var serialized: Array = []
	for polygon in rings:
		var ring: Array = []
		for point in polygon:
			ring.append([point.x, point.y])
		serialized.append(ring)
	return JSON.stringify(serialized[0] if serialized.size() == 1 else serialized).sha256_text()

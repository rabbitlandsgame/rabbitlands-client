@tool
extends RefCounted
## Source validation only. Logical-to-world transforms never use storage minima.

static func bounds(server: Variant) -> Dictionary:
	if server is not Dictionary or not _integers(server.get("cells"), 2):
		return {"error": "Server storage cells must contain two integers."}
	var cells: Array = server.cells
	if cells[0] < 1 or cells[1] < 1 or cells[0] > 2048 or cells[1] > 2048:
		return {"error": "Server storage extents must be within 1..2048."}
	var versioned: bool = server.has("serverStorageVersion")
	if versioned != server.has("serverTileMin"):
		return {"error": "serverStorageVersion and serverTileMin must be supplied together."}
	var minimum: Array = [0, 0]
	if versioned:
		if not _integers([server.serverStorageVersion], 1) or server.serverStorageVersion != 1:
			return {"error": "Unsupported serverStorageVersion; expected 1."}
		if not _integers(server.serverTileMin, 2):
			return {"error": "serverTileMin must contain two integers."}
		minimum = server.serverTileMin
	for axis in 2:
		if minimum[axis] < -2147483648 or minimum[axis] + cells[axis] - 1 > 2147483647:
			return {"error": "Logical storage bounds exceed signed 32-bit coordinates."}
	return {"error": "", "cells": Vector2i(int(cells[0]), int(cells[1])),
		"minimum": Vector2i(int(minimum[0]), int(minimum[1])), "versioned": versioned}


static func validate(server: Variant) -> Dictionary:
	var result := bounds(server)
	if not String(result.error).is_empty():
		return result
	if not _integers(server.get("origin"), 2):
		return {"error": "Server origin must contain two integers."}
	if not same_vector(server.get("localOrigin", [0, 0, 0]), [0, 0, 0]) or \
			not _numbers([server.get("metresPerTile", 1)], 1) or server.get("metresPerTile", 1) != 1 or \
			server.get("invertServerY", true) is not bool or server.get("invertServerY", true) != true:
		return {"error": "Authoring storage requires zero localOrigin, one metre tiles and inverted server Y; unsupported explicit frame."}
	if server.has("walkingHeight") and not _numbers([server.walkingHeight], 1):
		return {"error": "Server walkingHeight must be finite when supplied."}
	if not same_vector(server.get("collisionOriginMetres"), [
			result.minimum.x - server.origin[0], server.origin[1] - result.minimum.y]):
		return {"error": "Server collisionOriginMetres must equal [minX-originX, originY-minY] in the supported authoring frame."}
	return result


static func contains(outer: Dictionary, inner: Dictionary) -> bool:
	return outer.minimum.x <= inner.minimum.x and outer.minimum.y <= inner.minimum.y and \
		outer.minimum.x + outer.cells.x >= inner.minimum.x + inner.cells.x and \
		outer.minimum.y + outer.cells.y >= inner.minimum.y + inner.cells.y


static func same_vector(value: Variant, expected: Array) -> bool:
	if not _numbers(value, expected.size()):
		return false
	for axis in expected.size():
		if value[axis] != expected[axis]:
			return false
	return true


static func _integers(value: Variant, count: int) -> bool:
	if not _numbers(value, count):
		return false
	for part: Variant in value:
		if float(part) != floor(float(part)):
			return false
	return true


static func _numbers(value: Variant, count: int) -> bool:
	if value is not Array or value.size() != count:
		return false
	for part: Variant in value:
		if (part is not int and part is not float) or not is_finite(float(part)):
			return false
	return true

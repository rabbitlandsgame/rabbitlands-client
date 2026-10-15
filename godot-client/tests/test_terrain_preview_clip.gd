extends SceneTree
## The terrain preview's viewer-only clip (terrain_control.gd preview_clip_inside / preview_clip_outside): a viewer
## wrapper draws each map of a shared grid once, so a map clipped to its polygon and its neighbour clipped to
## everything outside that polygon must cover every cell exactly once, in continent coordinates.

const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var parent := Node3D.new()
	var script := GDScript.new()
	script.source_code = "extends Node3D\nvar continent_translation := Vector3(100.0, 0.0, 200.0)\n"
	script.reload()
	parent.set_script(script)
	var terrain := TERRAIN.new() as MapAuthoringTerrainControl
	terrain.preview_enabled = false
	terrain.origin = Vector2(-10.0, -10.0)
	terrain.cell_metres = 2.0
	terrain.grid_size = Vector2i(11, 11)
	parent.add_child(terrain)
	root.add_child(parent)
	_expect(terrain.preview_clip_mask().is_empty(), "nothing clipped: an empty mask, every cell drawn")
	# cell centres run from continent x 91 to 109 and z 191 to 209 (origin + translation + half a cell)
	var square := PackedVector2Array([Vector2(90.0, 190.0), Vector2(96.0, 190.0), Vector2(96.0, 194.0),
		Vector2(90.0, 194.0)])
	terrain.preview_clip_inside = square
	var inside: PackedByteArray = terrain.preview_clip_mask()
	_expect(inside.size() == 100 and _count(inside) == 6, "a 6 x 4 m square holds 3 x 2 cell centres (%d)" % _count(inside))
	_expect(inside[0] == 1 and inside[2] == 1 and inside[3] == 0 and inside[10] == 1 and inside[20] == 0,
		"the square's cells are the first three of the first two rows")
	var diamond := PackedVector2Array([Vector2(100.0, 189.0), Vector2(111.0, 200.0), Vector2(100.0, 211.0),
		Vector2(89.0, 200.0)])
	terrain.preview_clip_inside = diamond
	var own: PackedByteArray = terrain.preview_clip_mask()
	terrain.preview_clip_inside = PackedVector2Array()
	terrain.preview_clip_outside = [diamond, square]
	var rest: PackedByteArray = terrain.preview_clip_mask()
	var once := true
	for i in own.size():
		var square_cell: bool = inside[i] == 1
		if square_cell:
			continue
		once = once and (own[i] + rest[i] == 1)
	_expect(once, "a polygon's own cells and its neighbour's clipped-out cells cover every cell exactly once")
	var brute := 0
	var agree := true
	for z_index in 10:
		for x_index in 10:
			var centre := Vector2(91.0 + 2.0 * x_index, 191.0 + 2.0 * z_index)
			var hit := Geometry2D.is_point_in_polygon(centre, diamond)
			brute += 1 if hit else 0
			agree = agree and (own[z_index * 10 + x_index] == (1 if hit else 0))
	_expect(agree and _count(own) == brute, "the row scan agrees cell by cell with a point-in-polygon test (%d)" % brute)
	parent.queue_free()
	await process_frame
	print("terrain preview clip: %d failures" % _failures)
	quit(1 if _failures > 0 else 0)


func _count(mask: PackedByteArray) -> int:
	var total := 0
	for value in mask:
		total += value
	return total


func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
	else:
		_failures += 1
		print("FAIL: ", message)

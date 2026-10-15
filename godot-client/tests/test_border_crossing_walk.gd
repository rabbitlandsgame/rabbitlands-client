extends SceneTree

## A walk to a neighbour aims at the crossing on its way, not at the gate the
## survey anchors: a border open along its length can be stepped across.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func _run() -> void:
	var adapter := CoordinateAdapter.new({})
	# The border is open from x 10 to 30 on row 5; its gate is at x 20.
	var gate := adapter.tile_center(20, 5)
	var open := {"position": [gate.x, gate.y, gate.z], "crossingRuns": {"axis": "x", "runs": [[5, 10, 30]]}}
	var tiles := ExteriorRegionStream.crossing_tiles(open)
	_expect(tiles.size() == 21 and tiles[0] == Vector2i(10, 5) and tiles[20] == Vector2i(30, 5),
		"a run ships twenty-one crossings as three numbers")
	var column := {"crossingRuns": {"axis": "y", "runs": [[7, 2, 4], [8, 5, 5]]}}
	_expect(ExteriorRegionStream.crossing_tiles(column) == [Vector2i(7, 2), Vector2i(7, 3), Vector2i(7, 4), Vector2i(8, 5)],
		"runs along y read as columns, one run a step of the border")
	var from := adapter.tile_center(12, 0)
	var to := adapter.tile_center(12, 10)
	_expect(ExteriorRegionStream.best_crossing(open, adapter, from, to) == Vector2i(12, 5),
		"a walker eight tiles from the gate steps straight across the border")
	var beyond_from := adapter.tile_center(40, 0)
	var beyond_to := adapter.tile_center(40, 10)
	_expect(ExteriorRegionStream.best_crossing(open, adapter, beyond_from, beyond_to) == Vector2i(30, 5),
		"past the end of the open border the walk goes by its nearest end")
	var surveyed := {"position": [gate.x, gate.y, gate.z]}
	_expect(ExteriorRegionStream.best_crossing(surveyed, adapter, from, to) == Vector2i(20, 5),
		"a survey without crossings still walks to its gate")
	print("border crossing walk test: %d failures" % failures)
	quit(1 if failures > 0 else 0)

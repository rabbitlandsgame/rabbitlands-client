extends RefCounted
## Shared geometry for real menu, item and prepared-spell controls. Resizing
## the area reflows cells; artwork keeps its aspect ratio inside each cell.
static func measure(config: Dictionary, count: int, cell: Vector2, padding: Vector2, limit: Vector2) -> Dictionary:
	count = maxi(1, count)
	var gap := float(config.get("slot_gap", 2.0))
	var requested: Vector2 = config.get("dimensions", Vector2.ZERO)
	var columns := int(config.get("columns", 0))
	if config.get("grid_mode", "fixed") == "aspect" and requested.x > 0 and requested.y > 0:
		var ratio := maxf(1, requested.x - padding.x) / maxf(1, requested.y - padding.y)
		var best := INF
		for candidate: int in range(1, count + 1):
			var rows := ceili(float(count) / candidate)
			var shape := (candidate * cell.x) / (rows * cell.y)
			var score := absf(log(shape / ratio)) + float(candidate * rows - count) / count * 0.75
			if score < best:
				best = score
				columns = candidate
	if columns <= 0:
		var rows := maxi(1, int(config.get("rows", 1)))
		columns = ceili(float(count) / rows) if config.get("orientation", "horizontal") == "horizontal" else rows
	columns = clampi(columns, 1, count)
	columns = mini(columns, maxi(1, floori((limit.x - padding.x + gap) / (minf(cell.x, 30) + gap))))
	if config.has("fit_columns"): columns = clampi(int(config.fit_columns), 1, count)
	var rows := ceili(float(count) / columns)
	var grid := Vector2(columns, rows)
	var minimum_cell := Vector2(minf(cell.x, 26), minf(cell.y, 30))
	var dimensions := grid * cell + (grid - Vector2.ONE) * gap + padding
	if requested.x > 0 and requested.y > 0:
		dimensions = requested.max(grid * minimum_cell + (grid - Vector2.ONE) * gap + padding)
	dimensions = dimensions.min(limit.max(Vector2(32, 32)))
	var fitted_cell := ((dimensions - padding - (grid - Vector2.ONE) * gap) / grid).max(Vector2(16, 16))
	return {"columns":columns, "rows":rows, "size":dimensions, "cell":fitted_cell, "gap":gap}

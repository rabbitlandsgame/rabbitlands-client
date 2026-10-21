extends RefCounted
## Edge alignment while resizing. Work in game-view coordinates, including
## both ends of each target window and the actual viewport edges.
static func snap(proposed: Rect2, axes: Vector2, targets: Array[Dictionary], bounds: Rect2, threshold: Vector2) -> Dictionary:
	var rect := proposed
	var guides: Array[Dictionary] = []
	var options: Array[Dictionary] = targets.duplicate()
	options.append({"key":"screen", "rect":bounds})
	for axis: int in 2:
		if axes[axis] == 0: continue
		var negative := axes[axis] < 0
		var edge := rect.position[axis] if negative else rect.end[axis]
		var best := threshold[axis]
		var match_value := edge
		var match_target: Dictionary = {}
		for target: Dictionary in options:
			var other: Rect2 = target.rect
			for value: float in [other.position[axis], other.end[axis]]:
				var distance := absf(edge - value)
				if distance < best:
					var new_size := rect.end[axis] - value if negative else value - rect.position[axis]
					if new_size < 16: continue
					best = distance
					match_value = value
					match_target = target
		if match_target.is_empty(): continue
		if negative:
			var end := rect.end[axis]
			rect.position[axis] = match_value
			rect.size[axis] = end - match_value
		else: rect.size[axis] = match_value - rect.position[axis]
		guides.append({"axis":axis, "value":match_value, "target":match_target.key, "target_rect":match_target.rect})
	return {"rect":rect, "guides":guides}

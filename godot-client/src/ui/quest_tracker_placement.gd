extends RefCounted
## Transient HUD placement only. The caller owns the card's bounded size and
## saved preference; avoiding a neighbour never rewrites either one.

static func _clamped(rect: Rect2, viewport: Rect2) -> Rect2:
	return Rect2(Vector2(
		clampf(rect.position.x,viewport.position.x,maxf(viewport.position.x,viewport.end.x-rect.size.x)),
		clampf(rect.position.y,viewport.position.y,maxf(viewport.position.y,viewport.end.y-rect.size.y))),rect.size)

static func _clear(rect: Rect2, obstacles: Array[Rect2]) -> bool:
	for obstacle: Rect2 in obstacles:
		if rect.intersects(obstacle): return false
	return true

static func place(preferred: Rect2, viewport: Rect2, obstacles: Array[Rect2], gap := 8.0) -> Rect2:
	var origin := _clamped(preferred,viewport)
	var blocked: Array[Rect2] = []
	for obstacle: Rect2 in obstacles:
		if not obstacle.has_area(): continue
		var expanded := obstacle.grow(maxf(0.0,gap))
		if expanded.intersects(viewport): blocked.append(expanded)
	if viewport.encloses(origin) and _clear(origin,blocked): return origin
	var points: Array[Vector2] = []
	var xs: Array[float] = [origin.position.x,viewport.position.x,maxf(viewport.position.x,viewport.end.x-origin.size.x)]
	var ys: Array[float] = [origin.position.y,viewport.position.y,maxf(viewport.position.y,viewport.end.y-origin.size.y)]
	for obstacle: Rect2 in blocked:
		var left := obstacle.position.x-origin.size.x
		var right := obstacle.end.x
		var above := obstacle.position.y-origin.size.y
		var below := obstacle.end.y
		# Direct alternatives come first so equal-distance ties are stable:
		# above, left, right, below, in the caller's obstacle order.
		points.append_array([Vector2(origin.position.x,above),Vector2(left,origin.position.y),
			Vector2(right,origin.position.y),Vector2(origin.position.x,below)])
		xs.append_array([left,right]); ys.append_array([above,below])
	# Combining obstacle edge coordinates also finds nearby clear corners when
	# a second HUD window blocks every direct alternative. HUD obstacle sets
	# are small; no scene state, camera data or layout measurements are needed.
	for x: float in xs:
		for y: float in ys: points.append(Vector2(x,y))
	var best := origin
	var distance := INF
	for point: Vector2 in points:
		var candidate := _clamped(Rect2(point,origin.size),viewport)
		if not viewport.encloses(candidate) or not _clear(candidate,blocked): continue
		var candidate_distance := candidate.position.distance_squared_to(origin.position)
		if candidate_distance < distance:
			distance = candidate_distance
			best = candidate
	# A crowded viewport must not shrink the card or erase a saved position.
	# The caller can stack the most recently opened window when no space fits.
	return best

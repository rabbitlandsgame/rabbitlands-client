extends RefCounted
## A server-approved ground route with a cosmetic jump arc. Server tiles remain
## authoritative; no collision, reach, damage or immunity decisions happen here.
var points: PackedVector3Array
var duration: float
var elapsed := 0.0
var length := 0.0
var height: float

func _init(route: PackedVector3Array, seconds: float) -> void:
	points = route.duplicate()
	duration = clampf(seconds, 0.18, 0.6)
	for i in range(1, points.size()): length += points[i - 1].distance_to(points[i])
	height = clampf(length * 0.18, 0.65, 1.15)

func ground_at(time: float) -> Vector3:
	# Keep a few frames for takeoff and landing even on the fastest jump.
	var progress := clampf((time / duration - 0.14) / 0.76, 0.0, 1.0)
	var remaining := length * progress
	for i in range(1, points.size()):
		var segment := points[i - 1].distance_to(points[i])
		if remaining <= segment:
			return points[i - 1].lerp(points[i], remaining / maxf(segment, 0.001))
		remaining -= segment
	return points[-1]

func position_at(time: float) -> Vector3:
	var progress := clampf(time / duration, 0.0, 1.0)
	return ground_at(time) + Vector3.UP * (4.0 * progress * (1.0 - progress) * height)

func rebase(frame: Transform3D) -> void:
	for i in points.size(): points[i] = frame * points[i]

extends SceneTree

## A surveyed road crossing is continuous within the interpolation slack of the
## seam, even when the continent frame's collar is only its two-metre
## threshold-floor extent; remote map changes remain cold.
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
	_expect(ExteriorRegionStream.continuous_crossing(true, 2.77, 2.0), "a crossing 2.77 m from a two-metre continent collar is continuous")
	_expect(ExteriorRegionStream.continuous_crossing(true, 7.9, 2.0), "a crossing inside the eight-metre slack is continuous")
	_expect(not ExteriorRegionStream.continuous_crossing(true, 8.0, 2.0), "a change eight metres from the seam is not continuous")
	_expect(not ExteriorRegionStream.continuous_crossing(true, 120.0, 2.0), "an admin teleport far from any seam is a cold load")
	_expect(ExteriorRegionStream.continuous_crossing(true, 30.0, 42.0), "the legacy 42 m collar keeps its whole approach continuous")
	_expect(not ExteriorRegionStream.continuous_crossing(false, 1.0, 42.0), "a ferry or visual-only link is never continuous")
	_expect(not ExteriorRegionStream.continuous_crossing(true, INF, 2.0), "an unknown crossing distance is never continuous")
	# What the slack is measured from. A continent seam ships the border it
	# stands on, and every tile along that border is a way across, so a walker
	# who leaves by its far end is as continuous as one who leaves by the gate
	# the survey anchors at.
	var stream := ExteriorRegionStream.new()
	stream.active_map = "here"
	stream.links = [_seam([[[-150, 0], [150, 0]]])]
	var along: Dictionary = stream._candidates(Vector3(120, 0, 3))[0]
	_expect(is_equal_approx(float(along.handoff_distance), 3.0),
		"a crossing 120 m along a shipped border is measured from the border")
	_expect(float(along.crossing_distance) > 120.0,
		"the same crossing stands far from the seam's own anchor")
	_expect(ExteriorRegionStream.continuous_crossing(true, float(along.handoff_distance), 2.0),
		"walking over the far end of a wide seam is a continuous handoff")
	# A link that ships no border keeps the anchor: its view flank says how far
	# the neighbour is drawn, not how far it can be walked into.
	stream.links = [_seam([])]
	var flank: Dictionary = stream._candidates(Vector3(120, 0, 3))[0]
	_expect(float(flank.handoff_distance) > 120.0,
		"a link with no shipped border measures its handoff from the anchor as before")
	stream.free()
	print("handoff zone test: %d failures" % failures)
	quit(1 if failures > 0 else 0)

## One seamless link whose near end is the active map, with or without the
## shared border the continent survey ships.
func _seam(edges: Array) -> Dictionary:
	var here := {"map": "here", "position": [0, 0, 0], "frame": {
		"anchor": [0, 0, 0], "outward": [0, -1], "viewHalfWidth": 240, "collarDepth": 2}}
	if not edges.is_empty():
		here["preloadEdges"] = edges
	return {"seamless": true, "ends": [here, {"map": "there", "position": [0, 0, 0]}]}

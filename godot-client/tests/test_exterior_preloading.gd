extends SceneTree

## Selection tests do not import region assets or start a rendering context.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var stream := ExteriorRegionStream.new()
	_expect(stream.preload_distance == 240 and stream.retain_distance == 320,
		"default loading lead and retention hysteresis are 240/320 metres")
	_expect(stream.maximum_neighbours == 3, "three neighbours are available by default")
	stream.active_map = "current"
	stream.registry = {"next": {"manifest": "user://selection-only.json"}}
	stream.links = [_link("next", [0, 0, 0], [0, -1], 80)]
	var candidates := stream._candidates(Vector3(79, 900, 239))
	_expect(is_equal_approx(float(candidates[0].distance), 239),
		"a lateral camera approach measures to the visible seam rather than its centre")
	_expect(float(candidates[0].crossing_distance) > 240,
		"the actual crossing distance remains separate for handoff safety")
	_expect(stream._preload_candidate(candidates, stream._wanted_neighbours(candidates)).get("map") == "next",
		"the visible flank loads before the old centre-distance threshold permits it")
	var loader := WorldLoader.new()
	var incoming := Node3D.new()
	stream.residents["next"] = {"root": incoming}
	var handoff := stream.take_ready("next", loader, Vector3(79, 0, 0))
	_expect(not bool(handoff.continuous),
		"a point beside the visible flank cannot turn a distant crossing into a continuous handoff")
	incoming.free()
	loader.free()
	for sample: Array in [[240.0, true], [240.01, false]]:
		candidates = stream._candidates(Vector3(0, 0, float(sample[0])))
		_expect(not stream._preload_candidate(candidates, stream._wanted_neighbours(candidates)).is_empty() == bool(sample[1]),
			"preload threshold respects %s metres" % sample[0])
	for sample: Array in [[320.0, true], [320.01, false]]:
		stream._last_position = Vector3(0, 0, float(sample[0]))
		_expect(stream._nearby("next") == bool(sample[1]), "retention respects %s metres" % sample[0])
	var finite := _link("next", [0, 0, 0], [0, -1], 160)
	_expect(is_equal_approx(ExteriorRegionStream._seam_distance(Vector3(200, 8, 30), finite.ends[0], true), 50),
		"beyond a seam endpoint the finite segment measures the 30/40/50 triangle")
	var rotated := _link("next", [0, 0, 0], [2, 0], 160)
	_expect(is_equal_approx(ExteriorRegionStream._seam_distance(Vector3(30, -80, 200), rotated.ends[0], true), 50),
		"east-facing seams normalize their direction and ignore elevation")
	_expect(ExteriorRegionStream._seam_distance(Vector3(200, 0, 30), finite.ends[0], false) > 200,
		"an unsurveyed transition keeps point-distance preloading")
	var shore := {"position": [500,0,500], "preloadEdges": [
		[[0,0],[400,0]], [[400,0],[400,200]]]}
	_expect(is_equal_approx(ExteriorRegionStream._seam_distance(Vector3(390,80,150), shore, false), 10),
		"irregular shore loading measures the nearest actual edge, including its turn")
	_expect(is_equal_approx(ExteriorRegionStream._seam_distance(Vector3(430,0,240), shore, false), 50),
		"the end of a physical shore remains a finite distance target")
	stream.links = [_link("d", [40, 0, 0]), _link("b", [20, 0, 0]),
		_link("a", [10, 0, 0]), _link("c", [30, 0, 0]), _link("a", [15, 0, 0])]
	stream.registry = {}
	for identity: String in ["a", "b", "c", "d"]:
		stream.registry[identity] = {"manifest": "user://selection-only.json"}
	candidates = stream._candidates(Vector3.ZERO)
	var wanted := stream._wanted_neighbours(candidates)
	_expect(wanted.keys() == ["a", "b", "c"],
		"the nearest three distinct regions win; repeated links cannot consume another slot")
	stream.residents = {"a": {}, "b": {}}
	_expect(stream._preload_candidate(candidates, wanted).get("map") == "c",
		"two resident neighbours permit exactly the third eligible preload")
	stream.residents["c"] = {}
	_expect(not stream._can_dispatch_preload() and stream._preload_candidate(candidates, wanted).is_empty(),
		"a full three-neighbour budget cannot allocate a fourth worker result")
	stream.maximum_neighbours = 99
	_expect(not stream._can_dispatch_preload() and stream._wanted_neighbours(candidates).size() == 3,
		"the root limit remains three even if a caller supplies an excessive budget")
	stream.maximum_neighbours = 3
	stream.residents.erase("c")
	stream._thread = Thread.new()
	_expect(stream._preload_candidate(candidates, wanted).is_empty(), "the existing single worker excludes another dispatch")
	stream._thread = null
	stream._retiring = [{"map": "retiring"}]
	_expect(stream._preload_candidate(candidates, wanted).is_empty(), "retirement debt still excludes new loading")
	stream._retiring.clear()
	stream._retry_after["c"] = Time.get_ticks_msec() + 10000
	_expect(stream._preload_candidate(candidates, wanted).is_empty(), "failed third neighbour respects retry backoff without loading a fourth")
	stream._retry_after.clear()
	stream.maximum_neighbours = 0
	_expect(stream._wanted_neighbours(candidates).is_empty() and not stream._can_dispatch_preload(),
		"a zero-neighbour budget still disables proximity loading")
	stream.residents.clear()
	stream.free()
	print("exterior preloading tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _link(identity: String, anchor: Array, outward := [0, -1], half_width := 0.0) -> Dictionary:
	return {"seamless": true, "ends": [
		{"map": "current", "position": anchor,
			"frame": {"anchor": anchor, "outward": outward, "viewHalfWidth": half_width}},
		{"map": identity, "position": [0, 0, 0]}]}

func _expect(ok: bool, description: String) -> void:
	if ok:
		print("PASS: ", description)
	else:
		failures += 1
		push_error("FAIL: " + description)

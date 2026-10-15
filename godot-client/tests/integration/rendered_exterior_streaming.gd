extends "res://tests/integration/rendered_landscape_walk.gd"

## Real-client proof: retain both scene and traveller identities, transport the
## camera rigidly, sample every rendered handoff, and save adjacent frames.
var _last_map := ""
var _last_camera := Transform3D.IDENTITY
var _last_actor_id := 0
var _last_image: Image
var _handoffs: Array = []
var _frame_times: Array = []
var _peak_neighbours := 0
var _peak_static_bytes := 0.0
var _last_frame_time := 0
var _saving_capture := false
var _crossing_images: Array = []
var _walking_route := false
var _continuous_approach := false
var _approach: Dictionary = {}
var _step_transition_timeout := TIMEOUT

func _issue_walk(step: Dictionary) -> void:
	_walking_route = true
	_step_transition_timeout = maxf(TIMEOUT, float(step.get("walkTimeout", TIMEOUT)))
	if _continuous_approach:
		_expect(_approach.is_empty(), "continuous approach uses one movement request")
		var stream: ExteriorRegionStream = _main.get("exterior_stream")
		var destination := str(step.get("destination", ""))
		var distance := INF
		for candidate: Dictionary in stream._candidates(_main.get("camera_rig").focus):
			if str(candidate.map) == destination:
				distance = float(candidate.distance)
		_approach = {"source": str(_state.get("current_map")), "destination": destination,
			"began_ms": Time.get_ticks_msec(), "start_seam_distance_metres": distance,
			"resident_at_start": stream.residents.has(destination),
			"pending_at_start": stream._pending_map == destination,
			"preload_distance_metres": stream.preload_distance, "waited_for_neighbor": false}
		_expect(is_finite(distance) and distance >= stream.preload_distance + 20,
			"uninterrupted approach begins beyond the eager preload threshold")
		_expect(not bool(_approach.resident_at_start) and not bool(_approach.pending_at_start),
			"destination is neither resident nor already loading at the first movement request")
	super._issue_walk(step)
	if bool(step.get("clickNeighbor", false)):
		var intent: Dictionary = _main.get("exterior_stream").pending_walk
		var tile: Vector2i = intent.get("tile", Vector2i(-1, -1))
		if not _report.has("neighbor_click_intents"):
			_report["neighbor_click_intents"] = []
		(_report["neighbor_click_intents"] as Array).append({
			"at_ms": Time.get_ticks_msec(), "requested_map": str(step.destination),
			"requested_tile": step.tile, "map": str(intent.get("map", "")),
			"tile": [tile.x, tile.y], "run": bool(intent.get("run", false)),
			"issued_from": str(intent.get("issued_from", "")),
			"next_map": str(intent.get("next_map", "")), "routed": bool(intent.get("routed", false))})
		if step.has("expectRun"):
			_expect(not intent.is_empty() and bool(intent.get("run", false)) == bool(step.expectRun),
				"original neighbor click retains its expected run intent")

func _run() -> void:
	_continuous_approach = OS.get_environment("ELORIA_STREAM_CONTINUOUS_APPROACH") == "1"
	RenderingServer.frame_post_draw.connect(_measure_frame)
	await super._run()

func _settle(frames: int) -> void:
	await super._settle(frames)
	if _main == null or _continuous_approach:
		return
	var stream: ExteriorRegionStream = _main.get("exterior_stream")
	for candidate: Dictionary in stream._candidates(_main.get("camera_rig").focus):
		if (bool(candidate.seamless) or bool(candidate.visual_only)) and float(candidate.distance) < 80 and not stream.residents.has(str(candidate.map)):
			_expect(await _wait(func() -> bool: return stream.residents.has(str(candidate.map)), 60),
				"neighbor became resident before crossing")

func _on_map(name: String) -> bool:
	if not _continuous_approach and _step_transition_timeout == TIMEOUT:
		return await super._on_map(name)
	# Explicit long approach/detour steps exceed the warm default's 90 s gate.
	# This only waits for the authoritative destination, never a resident tree.
	return await _wait(func() -> bool:
		return (str(_state.get("current_map")) == name and _loader.world_root != null
			and (_main.get("actor_nodes") as Dictionary).has(int(_state.get("local_actor_id")))),
		_step_transition_timeout)

func _observe_approach_transition(map_id: String, stream: ExteriorRegionStream) -> void:
	if (not _continuous_approach or _approach.is_empty() or _approach.has("crossed_ms")
			or map_id == str(_approach.source)):
		return
	var handoff: Dictionary = stream.last_handoff
	var matched := (str(handoff.get("from", "")) == str(_approach.source)
		and str(handoff.get("to", "")) == map_id)
	_approach.merge({"crossed_ms": Time.get_ticks_msec(), "actual_destination": map_id,
		"crossing_frame_ms": (Time.get_ticks_usec() - _last_frame_time) / 1000.0 if _last_frame_time > 0 else 0,
		"matching_resident_handoff": matched,
		"continuous_handoff": matched and bool(handoff.get("continuous", false)),
		"cold_load_fallback": not matched,
		"noncontinuous_resident_adoption": matched and not bool(handoff.get("continuous", false)),
		"fallback_ground_visible": bool(_main.get("fallback_ground").visible)})
	_expect(map_id == str(_approach.destination), "continuous approach reaches its intended map")
	_expect(bool(_approach.continuous_handoff), "eager preload completes before the uninterrupted crossing")
	if not matched:
		# Cold loads have no last_handoff record; retain their actual outcome too.
		if _last_image != null:
			_crossing_images.append(["continuous-cold-before.png", _last_image])
		_crossing_images.append(["continuous-cold-after.png", root.get_texture().get_image()])

func _measure_frame() -> void:
	if not is_instance_valid(_main) or _loader == null or _loader.world_root == null:
		return
	var stream: ExteriorRegionStream = _main.get("exterior_stream")
	var map_id: String = _state.get("current_map")
	var rig: IsometricCameraController = _main.get("camera_rig")
	var actor: Variant = _main.get("actor_nodes").get(int(_state.get("local_actor_id")))
	if not is_instance_valid(actor):
		return
	_peak_neighbours = maxi(_peak_neighbours, stream.residents.size())
	_peak_static_bytes = maxf(_peak_static_bytes, Performance.get_monitor(Performance.MEMORY_STATIC))
	if _walking_route:
		_observe_approach_transition(map_id, stream)
	# Route setup uses an admin teleport, which may also reuse a resident map.
	# Only player movement is expected to preserve the border camera transform.
	if (_walking_route and map_id != _last_map and not _last_map.is_empty()
			and stream.last_handoff.get("from", "") == _last_map
			and stream.last_handoff.get("to", "") == map_id):
		_expect(bool(stream.last_handoff.get("continuous", false)), "surveyed road uses continuous handoff")
		var expected: Transform3D = stream.last_handoff.rebase * _last_camera
		var current := rig.camera.global_transform
		var translation := expected.origin.distance_to(current.origin)
		var rotation := expected.basis.get_rotation_quaternion().angle_to(current.basis.get_rotation_quaternion())
		var item := {"from": _last_map, "to": map_id, "camera_step_metres": translation,
			"handoff_frame_ms": (Time.get_ticks_usec() - _last_frame_time) / 1000.0 if _last_frame_time > 0 else 0,
			"camera_rotation_degrees": rad_to_deg(rotation), "traveller_retained": actor.get_instance_id() == _last_actor_id,
			"scene_reused": _loader.world_root.get_instance_id() == int(stream.last_handoff.root_id),
			"resident_neighbours": stream.residents.size()}
		item["detail"] = str(stream.last_handoff)
		item["camera_before"] = str(_last_camera)
		item["camera_after"] = str(current)
		_handoffs.append(item)
		_expect(translation < 1.5, "camera crosses without a position jump")
		_expect(rotation < .001, "camera direction and zoom survive the handoff")
		_expect(bool(item.traveller_retained), "same traveller node crosses the border")
		_expect(bool(item.scene_reused), "arrival reuses the preloaded scene")
		_expect(not bool(_main.get("fallback_ground").visible), "no fallback ground frame")
		var stem := "crossing-%02d" % _handoffs.size()
		if _last_image != null:
			_crossing_images.append([stem + "-before.png", _last_image])
		_crossing_images.append([stem + "-after.png", root.get_texture().get_image()])
	var near_border := false
	for candidate: Dictionary in stream._candidates(rig.focus):
		if bool(candidate.seamless) and float(candidate.distance) < 8:
			near_border = true
	if near_border and _walking_route:
		_last_image = root.get_texture().get_image()
		if _last_frame_time > 0 and not _saving_capture:
			_frame_times.append((Time.get_ticks_usec() - _last_frame_time) / 1000.0)
	else:
		_last_image = null
	_last_map = map_id
	_last_camera = rig.camera.global_transform
	_last_actor_id = actor.get_instance_id()
	_last_frame_time = Time.get_ticks_usec()

func _write_report() -> void:
	if _continuous_approach and not _approach.is_empty() and not _report.has("continuous_approach"):
		var stream: ExteriorRegionStream = _main.get("exterior_stream")
		var requested: Dictionary = {}
		var ready: Dictionary = {}
		for event: Dictionary in stream.events:
			if str(event.get("map", "")) != str(_approach.destination) or int(event.at_ms) < int(_approach.began_ms):
				continue
			if str(event.event) == "requested" and requested.is_empty(): requested = event.duplicate(true)
			if str(event.event) == "ready" and ready.is_empty(): ready = event.duplicate(true)
		_approach["first_requested"] = requested
		_approach["first_ready"] = ready
		_approach["requested_distance_metres"] = requested.get("distance")
		_approach["preload_load_ms"] = ready.get("load_ms")
		_approach["travel_seconds"] = (int(_approach.get("crossed_ms", Time.get_ticks_msec())) - int(_approach.began_ms)) / 1000.0
		if _approach.has("crossed_ms") and not ready.is_empty():
			_approach["ready_lead_before_handoff_ms"] = int(_approach.crossed_ms) - int(ready.at_ms)
		_expect(_approach.has("crossed_ms"), "continuous approach records its actual map transition")
		_expect(not requested.is_empty() and not ready.is_empty(), "continuous approach records fresh preload request and completion")
		_report["continuous_approach"] = _approach.duplicate(true)
	_walking_route = false
	for capture: Array in _crossing_images:
		(capture[1] as Image).save_png(_artifacts.path_join(capture[0]))
	_crossing_images.clear()
	_last_frame_time = 0
	_report["stream_handoffs"] = _handoffs
	_report["border_frame_ms"] = _frame_times
	_report["peak_resident_neighbours"] = _peak_neighbours
	_report["peak_static_bytes"] = _peak_static_bytes
	_report["stream_events"] = _main.get("exterior_stream").events
	super._write_report()

func _capture(name: String) -> void:
	_saving_capture = true
	await super._capture(name)
	_saving_capture = false
	_last_frame_time = 0

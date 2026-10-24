class_name ExteriorRegionStream
extends Node3D

const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const RetirementBudget := preload("res://src/world/resource_retirement_budget.gd")

## One private loader worker, the current region and at most three neighbours.
## Only surveyed reciprocal neighbors are displayed simultaneously. The
## server still selects the map and is the sole owner of actors/interactions.
const CONNECTIONS := "res://data/maps/exterior_connections.json"
## The rebuilt continent's land links (eloria-assets/maps/continent-v2/
## _continent_v2/publish_links.py), kept apart from CONNECTIONS: the legacy
## continent publisher writes that file whole, and its checks hold it equal to
## the server's own copy. Its links join only continent-v2 maps.
const CONTINENT_V2_CONNECTIONS := "res://data/maps/exterior_connections-continent-v2.json"
const PREVIEW_SURFACE_LAYER := 16
const DEFAULT_PRELOAD_DISTANCE := 240.0
const DEFAULT_RETAIN_DISTANCE := 320.0
const MAXIMUM_NEIGHBOURS := 3
## The server returns at most 512 path steps per MOVE_TO. Renew the same
## target before that prefix ends; never substitute a guessed client waypoint.
const WALK_RENEW_COMMANDS := 448
const MAX_WALK_RENEWALS_PER_LEG := 16
var registry: Dictionary = {}
var links: Array = []
var residents: Dictionary = {}
var active_map := ""
var active_root: Node3D
var active_manifest: WorldManifest
var preload_distance := DEFAULT_PRELOAD_DISTANCE
var retain_distance := DEFAULT_RETAIN_DISTANCE
var maximum_neighbours := MAXIMUM_NEIGHBOURS
var _thread: Thread
var _pending_map := ""
var _pending_started_usec := 0
var _resource_timings: Dictionary = {}
var _last_preparation: Dictionary = {}
var _generation := 0
var _pending_generation := 0
var _retry_after: Dictionary = {}
var _last_position := Vector3.ZERO
var _next_update := 0
var events: Array[Dictionary] = []
var last_handoff: Dictionary = {}
var pending_walk: Dictionary = {}
## Optional live network context. Offline scenery/tests retain legacy routing.
var coordinate_context: RefCounted
## Retiring trees still occupy their old neighbour slots until their resources
## are released. Do not dispatch another preload while any retirement remains.
## One worker already in flight may finish: the temporary allowance is the
## existing maximum_neighbours trees plus that single worker result, not an
## additional cache of retired maps.
var _retiring: Array[Dictionary] = []
var _retirement_scheduled := false
var _retirement_draining := false
const RETIRE_NODES_PER_FRAME := 64
const RETIRE_BUDGET_USEC := 2000

## The resident table changed: a neighbour arrived, left, or the maps swapped
## at a crossing. Main lays the neighbours' map pictures by it.
signal residents_changed

func configure(maps: Dictionary) -> void:
	registry = maps
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(CONNECTIONS))
	if raw is Dictionary:
		links = raw.get("connections", [])
		links.append_array(raw.get("visualConnections", []))
		preload_distance = maxf(0, float(raw.get("preloadDistance", DEFAULT_PRELOAD_DISTANCE)))
		retain_distance = maxf(preload_distance, float(raw.get("retainDistance", DEFAULT_RETAIN_DISTANCE)))
		maximum_neighbours = clampi(int(raw.get("maximumNeighbours", MAXIMUM_NEIGHBOURS)), 0, MAXIMUM_NEIGHBOURS)
	if FileAccess.file_exists(CONTINENT_V2_CONNECTIONS):
		var v2: Variant = JSON.parse_string(FileAccess.get_file_as_string(CONTINENT_V2_CONNECTIONS))
		if v2 is Dictionary:
			links.append_array((v2 as Dictionary).get("connections", []))

func activate(map_id: String, imported: Node3D, manifest: WorldManifest) -> void:
	active_map = MapRegistry.normalize_server_map_id(map_id)
	active_root = imported
	active_manifest = manifest
	_next_update = 0
	_refresh_views()

func update_position(position: Vector3) -> void:
	_last_position = position
	if active_root is ContinentChunkStream:
		(active_root as ContinentChunkStream).update_focus(position)
	for resident: Dictionary in residents.values():
		var imported: Node3D = resident.root
		if imported is ContinentChunkStream:
			(imported as ContinentChunkStream).update_focus(imported.transform.affine_inverse() * position)
	if Time.get_ticks_msec() < _next_update or active_map.is_empty():
		return
	_next_update = Time.get_ticks_msec() + 250
	var candidates := _candidates(position)
	var wanted := _wanted_neighbours(candidates)
	for map_id: String in residents.keys():
		if not wanted.has(map_id):
			_evict(map_id)
	_refresh_views()
	var candidate := _preload_candidate(candidates, wanted)
	if candidate.is_empty():
		return
	var map_id := str(candidate.map)
	var entry := MapRegistry.resolve(registry, map_id)
	_pending_map = map_id
	_pending_generation = _generation
	_thread = Thread.new()
	var path := ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	var visuals := GlbSceneCache.missing(PackedStringArray(candidate.there.get("visualScenes", [])))
	var arrival := Vector3.INF
	if candidate.here.has("frame") and candidate.there.has("frame"):
		arrival = frame_transform(candidate.here.frame, candidate.there.frame).affine_inverse() * position
	_pending_started_usec = Time.get_ticks_usec()
	var error := _thread.start(WorldLoader.prepare_detached.bind(path, MapSceneCache.is_enabled(), visuals, arrival))
	if error != OK:
		_thread = null
		_retry_after[map_id] = Time.get_ticks_msec() + 30000
		_record("failed", map_id, {"error": error_string(error)})
	else:
		_record("requested", map_id, {"distance": candidate.distance})

func _wanted_neighbours(candidates: Array[Dictionary]) -> Dictionary:
	var wanted: Dictionary = {}
	for candidate: Dictionary in candidates:
		var map_id := str(candidate.map)
		if (float(candidate.distance) <= retain_distance and not wanted.has(map_id)
				and wanted.size() < mini(maximum_neighbours, MAXIMUM_NEIGHBOURS)):
			wanted[map_id] = candidate
	return wanted

func _preload_candidate(candidates: Array[Dictionary], wanted: Dictionary) -> Dictionary:
	if not _can_dispatch_preload():
		return {}
	for candidate: Dictionary in candidates:
		var map_id := str(candidate.map)
		if (float(candidate.distance) <= preload_distance and not residents.has(map_id)
				and wanted.has(map_id) and Time.get_ticks_msec() >= int(_retry_after.get(map_id, 0))
				and not MapRegistry.resolve(registry, map_id).is_empty()):
			return candidate
	return {}

func _process(_delta: float) -> void:
	if not _retiring.is_empty() and not _retirement_scheduled:
		_retirement_scheduled = true
		_drain_retired_deferred.call_deferred()
	ContinentChunkStream.reap_orphans()
	if _thread == null or _thread.is_alive():
		return
	var install_began := Time.get_ticks_usec()
	var builder := _thread.wait_to_finish() as WorldLoader
	if _pending_started_usec > 0:
		ResourceDiagnostics.record(_resource_timings, &"prepare_request_to_poll", _pending_started_usec)
	_thread = null
	var map_id := _pending_map
	_pending_map = ""
	if builder == null:
		_retry_after[map_id] = Time.get_ticks_msec() + 30000
		return
	var resident := builder.release_world()
	builder.free()
	if resident.root == null:
		_retry_after[map_id] = Time.get_ticks_msec() + 30000
		_record("failed", map_id)
		return
	var imported := resident.root as Node3D
	var prepared_manifest := resident.manifest as WorldManifest
	_last_preparation = {"map": map_id, "load_phases_us": resident.phases.duplicate(),
		"timings": ResourceDiagnostics.snapshot(resident.get("resource_timings", {})),
		"verification": prepared_manifest.verification_diagnostics.duplicate(true) if prepared_manifest != null else {}}
	# Login, teleport, disconnect or a second map change can supersede a load.
	if (_pending_generation != _generation or map_id == active_map or not _nearby(map_id)
			or residents.size() >= mini(maximum_neighbours, MAXIMUM_NEIGHBOURS)):
		_retire(resident, map_id)
		_record("discarded", map_id)
		return
	imported.visible = false
	var operation_began := Time.get_ticks_usec()
	_set_collision(imported, false)
	ResourceDiagnostics.record(_resource_timings, &"collision_activation", operation_began)
	operation_began = Time.get_ticks_usec()
	add_child(imported)
	ResourceDiagnostics.record(_resource_timings, &"scene_attach", operation_began, true)
	residents[map_id] = resident
	MapSceneCache.note_local_digest((resident.manifest as WorldManifest).asset_id(), str(resident.digest))
	_record("ready", map_id, {"load_ms": float(resident.phases.get(&"total", 0)) / 1000.0})
	_refresh_views()
	residents_changed.emit()
	ResourceDiagnostics.record(_resource_timings, &"install_with_signal", install_began)

func _drain_retired_deferred() -> void:
	_retirement_scheduled = false
	if is_inside_tree() and can_process():
		_drain_retired()

func _nearby(map_id: String) -> bool:
	return _wanted_neighbours(_candidates(_last_position)).has(map_id)

static func _seam_distance(position: Vector3, here: Dictionary, seamless: bool) -> float:
	var edges: Array = here.get("preloadEdges", [])
	if not edges.is_empty():
		var nearest := INF
		var xz := Vector2(position.x, position.z)
		for edge: Array in edges:
			var a := Vector2(float(edge[0][0]), float(edge[0][1]))
			var b := Vector2(float(edge[1][0]), float(edge[1][1]))
			nearest = minf(nearest, xz.distance_to(Geometry2D.get_closest_point_to_segment(xz, a, b)))
		return nearest
	var point := _vector(here.position)
	var point_distance := Vector2(position.x - point.x, position.z - point.z).length()
	var frame: Dictionary = here.get("frame", {})
	var half_width := maxf(0, float(frame.get("viewHalfWidth", 0)))
	if not seamless or half_width == 0 or not frame.has("anchor") or not frame.has("outward"):
		return point_distance
	var normal := Vector2(float(frame.outward[0]), float(frame.outward[1]))
	if normal.is_zero_approx():
		return point_distance
	normal = normal.normalized()
	var anchor := _vector(frame.anchor)
	var delta := Vector2(position.x - anchor.x, position.z - anchor.z)
	var lateral := absf(delta.dot(Vector2(-normal.y, normal.x)))
	# Clamp to the actual finite visible edge, not its infinite supporting line.
	return Vector2(delta.dot(normal), maxf(0, lateral - half_width)).length()

func _candidates(position: Vector3) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for link: Dictionary in links:
		var ends: Array = link.ends
		for index: int in 2:
			if str(ends[index].map) != active_map:
				continue
			var here: Dictionary = ends[index]
			var there: Dictionary = ends[1 - index]
			var at := _vector(here.position)
			var seamless := bool(link.get("seamless", false))
			var seam := _seam_distance(position, here, seamless)
			var anchor_distance := Vector2(position.x - at.x, position.z - at.z).length()
			# Where the survey ships the shared border itself, the border is what
			# a handoff is judged against: every tile along it is a way across,
			# so leaving by its far end is as continuous as leaving by the middle.
			# A link that ships only an anchor and a view flank keeps the anchor:
			# its flank says how far the neighbour is drawn, not how far it can be
			# walked into, and a point out on the flank is not a crossing at all.
			var edged := not (here.get("preloadEdges", []) as Array).is_empty()
			result.append({"map": str(there.map), "distance": seam,
				"crossing_distance": anchor_distance,
				"handoff_distance": seam if edged else anchor_distance,
				"here": here, "there": there, "seamless": seamless,
				"visual_only": bool(link.get("visualOnly", false))})
	result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return str(a.map) < str(b.map) if float(a.distance) == float(b.distance) else float(a.distance) < float(b.distance))
	return result

## Transfer already-instantiated nodes. A surveyed join rebases the old world
## and camera into the destination's coordinate frame; nothing moves on screen.
## Server steps are one metre and the rendered traveller interpolates up to a
## few steps behind the authoritative crossing packet, so a crossing is judged
## continuous within this slack of the seam even when the frame's collar is
## only the continent's two-metre threshold-floor extent. Teleports and other
## remote map changes stay far outside it.
const CONTINUOUS_CROSSING_SLACK_METRES := 8.0

static func continuous_crossing(seamless: bool, seam_distance: float, collar: float) -> bool:
	return seamless and seam_distance < maxf(collar, CONTINUOUS_CROSSING_SLACK_METRES)

func take_ready(destination: String, loader: WorldLoader, position: Vector3) -> Dictionary:
	last_handoff = {}
	if not residents.has(destination):
		return {}
	var join: Dictionary = {}
	for candidate: Dictionary in _candidates(position):
		if str(candidate.map) == destination:
			join = candidate
			break
	var collar := float(join.get("here", {}).get("frame", {}).get("collarDepth", 42))
	# Measured to the seam itself and not to the crossing's anchor. The two were
	# the same thing while a seam was one gate seven lanes wide, and the slack is
	# written as a slack "of the seam"; but a border walkable along its length is
	# crossed wherever the ground allows.
	var continuous := continuous_crossing(bool(join.get("seamless", false)),
		float(join.get("handoff_distance", INF)), collar)
	var resident: Dictionary = residents[destination]
	residents.erase(destination)
	var rebase := Transform3D.IDENTITY
	if continuous:
		rebase = frame_transform(join.here.frame, join.there.frame).affine_inverse()
		var previous := loader.release_world(false)
		var old := previous.root as Node3D
		_set_collision(old, false)
		old.transform = rebase
		residents[active_map] = previous
		residents_changed.emit()
	else:
		for stale: String in residents.keys():
			_evict(stale)
	var imported := resident.root as Node3D
	_set_view(imported)
	_set_collision(imported, true)
	imported.visible = true
	_generation += 1
	last_handoff = {"from": active_map, "to": destination, "continuous": continuous,
		"rebase": rebase, "root_id": imported.get_instance_id(),
		"source_distance": join.get("handoff_distance", INF),
		"anchor_distance": join.get("crossing_distance", INF)}
	_record("handoff", destination, {"continuous": continuous})
	return {"resident": resident, "continuous": continuous, "rebase": rebase}

func _refresh_views() -> void:
	if not is_instance_valid(active_root):
		return
	_set_view(active_root)
	var visible_borders: Dictionary = {}
	for candidate: Dictionary in _candidates(_last_position):
		var map_id := str(candidate.map)
		if not residents.has(map_id):
			continue
		var imported := residents[map_id].root as Node3D
		if bool(candidate.seamless) or bool(candidate.visual_only):
			var identity := str(candidate.there.frame.id)
			var full_owned := str(candidate.there.frame.get("geometryMode", "")) in ["continent-owned-v1", "continent-chunks-v1"]
			imported.transform = frame_transform(candidate.here.frame, candidate.there.frame)
			imported.visible = true
			_set_view(imported, identity, full_owned)
			_set_collision(imported, false, true, identity, full_owned)
			visible_borders[str(candidate.here.frame.id)] = true
		else:
			imported.visible = false
			_set_collision(imported, false)
	_set_overflow(active_root, visible_borders)

static func _set_view(imported: Node3D, border := "", full_owned := false) -> void:
	var active := imported.get_node_or_null("StreamActive") as Node3D
	if active == null:
		return
	active.visible = border.is_empty() or full_owned
	for node: Node in imported.get_children():
		if node.has_meta("stream_borders"):
			(node as Node3D).visible = border.is_empty() or full_owned or border in node.get_meta("stream_borders")
		if str(node.name).begins_with("StreamPreview_"):
			(node as Node3D).visible = not full_owned and str(node.name) == "StreamPreview_" + border

static func frame_transform(here: Dictionary, there: Dictionary) -> Transform3D:
	var outward := Vector3(float(here.outward[0]), 0, float(here.outward[1]))
	var incoming := -Vector3(float(there.outward[0]), 0, float(there.outward[1]))
	var angle := atan2(outward.x, outward.z) - atan2(incoming.x, incoming.z)
	var basis := Basis(Vector3.UP, angle)
	return Transform3D(basis, _vector(here.anchor) - basis * _vector(there.anchor))

static func _vector(raw: Array) -> Vector3:
	return Vector3(float(raw[0]), float(raw[1]), float(raw[2]))

static func _set_collision(imported: Node3D, enabled: bool, preview_enabled := false, border := "", full_owned := false) -> void:
	if imported is ContinentChunkStream:
		(imported as ContinentChunkStream).set_physics_mode(enabled, preview_enabled)
	var mode := str(enabled) + ":" + str(preview_enabled) + ":" + border + ":" + str(full_owned)
	if imported.get_meta("stream_physics", "") == mode:
		return
	var has_views := imported.has_node("StreamActive")
	var shared := bool(imported.get_meta("shared_stream_cells", false))
	for node: Node in imported.find_children("*", "CollisionObject3D", true, false):
		var body := node as CollisionObject3D
		if not body.has_meta("stream_collision_layer"):
			body.set_meta("stream_collision_layer", body.collision_layer)
		var original := int(body.get_meta("stream_collision_layer"))
		var view := ""
		var cells: Array = []
		var threshold := false
		var ancestor := body.get_parent()
		while ancestor != null and ancestor != imported:
			if ancestor.has_meta("stream_borders"): cells = ancestor.get_meta("stream_borders")
			if ancestor.has_meta("stream_threshold"): threshold = true
			if str(ancestor.name).begins_with("StreamPreview_"):
				view = str(ancestor.name).trim_prefix("StreamPreview_")
				break
			ancestor = ancestor.get_parent()
		var preview := 0
		var visible_navigation := full_owned or (border in cells if shared else
			(view == border if has_views else not "_StreamOverflow" in str(body.get_parent().name)))
		if preview_enabled and (original & WorldLoader.NAVIGATION_SURFACE_LAYER) != 0 and not threshold and visible_navigation:
			preview = PREVIEW_SURFACE_LAYER
		body.collision_layer = (original if shared or view.is_empty() else 0) if enabled else preview
	imported.set_meta("stream_physics", mode)

static func _set_overflow(imported: Node3D, visible_borders: Dictionary) -> void:
	var key := JSON.stringify(visible_borders)
	if imported.get_meta("stream_overflow_visible", "") == key:
		return
	for node: Node in imported.find_children("*_StreamOverflow*", "Node3D", true, false):
		var title := str(node.name)
		var identity := title.get_slice("_StreamOverflow_", 1) if "_StreamOverflow_" in title else ""
		(node as Node3D).visible = not visible_borders.has(identity) if not identity.is_empty() else visible_borders.is_empty()
	imported.set_meta("stream_overflow_visible", key)

func _evict(map_id: String) -> void:
	var resident: Dictionary = residents[map_id]
	residents.erase(map_id)
	_retire(resident, map_id)
	_record("evicted", map_id, {"retiring": _retiring.size()})
	residents_changed.emit()

func _can_dispatch_preload() -> bool:
	return (_thread == null and _retiring.is_empty()
		and residents.size() < mini(maximum_neighbours, MAXIMUM_NEIGHBOURS))

func _retire(resident: Dictionary, map_id: String) -> void:
	var began := Time.get_ticks_usec()
	var imported := resident.root as Node3D
	if imported is ContinentChunkStream:
		(imported as ContinentChunkStream).pause_streaming()
		# This transfer takes the descendants even if an observer had already
		# paused preload dispatch. Cancel that obsolete owner explicitly.
		RetirementBudget.cancel(imported)
	imported.visible = false
	_set_collision(imported, false)
	imported.process_mode = Node.PROCESS_MODE_DISABLED
	# Keep the root attached: remove_child/queue_free on the complete tree
	# would unregister all renderer/physics instances in one handoff frame.
	# Prepared visual PackedScenes are released separately after the nodes;
	# dropping their complete dictionary here would merely move the spike.
	_retiring.append({"resident": resident, "map": map_id, "stack": [imported],
		"visual_keys": (resident.get("visuals", {}) as Dictionary).keys(),
		"freed": 0, "released_visuals": 0, "release_usec": 0, "max_slice_usec": 0})
	ResourceDiagnostics.record(_resource_timings, &"retire_enqueue", began)

func _drain_retired(max_nodes := RETIRE_NODES_PER_FRAME,
		budget_usec := RETIRE_BUDGET_USEC) -> int:
	# Exit signals run synchronously inside free(). Re-entering this walk
	# would find the same child before its destructor has detached it.
	if _retirement_draining:
		return 0
	if _retiring.is_empty():
		RetirementBudget.cancel(self)
		return 0
	var allowance := RetirementBudget.begin_slice(self, max_nodes, budget_usec)
	if allowance.is_empty():
		return 0
	_retirement_draining = true
	var began := Time.get_ticks_usec()
	var freed := 0
	while not _retiring.is_empty() and freed < int(allowance.nodes) and Time.get_ticks_usec() - began < int(allowance.usec):
		var retired: Dictionary = _retiring[0]
		var imported: Variant = retired.resident.root
		if is_instance_valid(imported) and imported is ContinentChunkStream and not (imported as ContinentChunkStream).can_retire():
			break
		var stack: Array = retired.stack
		var visual_keys: Array = retired.visual_keys
		if stack.is_empty():
			var visuals: Dictionary = retired.resident.get("visuals", {})
			var release_started := Time.get_ticks_usec()
			visuals.erase(visual_keys.pop_back())
			retired.release_usec += Time.get_ticks_usec() - release_started
			ResourceDiagnostics.record(_resource_timings, &"prepared_visual_release", release_started, true)
			retired.released_visuals += 1
			freed += 1
		else:
			var node: Variant = stack.back()
			if not is_instance_valid(node):
				stack.pop_back()
			elif node.get_child_count() > 0:
				# Walk down only one branch at a time; even descent through a very
				# deep import is covered by the time budget. Last-child removal
				# avoids repeatedly shifting a wide sibling array.
				stack.append(node.get_child(node.get_child_count() - 1))
			else:
				stack.pop_back()
				var release_started := Time.get_ticks_usec()
				node.free()
				retired.release_usec += Time.get_ticks_usec() - release_started
				ResourceDiagnostics.record(_resource_timings, &"node_free", release_started, true)
				retired.freed += 1
				freed += 1
		retired.max_slice_usec = maxi(int(retired.max_slice_usec), Time.get_ticks_usec() - began)
		if stack.is_empty() and visual_keys.is_empty():
			_record("retired", str(retired.map), {"nodes": retired.freed,
				"visuals": retired.released_visuals,
				"max_slice_ms": float(retired.max_slice_usec) / 1000.0,
				"release_ms": float(retired.release_usec) / 1000.0})
			_retiring.pop_front()
	_retirement_draining = false
	RetirementBudget.end_slice(allowance, freed, Time.get_ticks_usec() - began, not _retiring.is_empty())
	ResourceDiagnostics.record(_resource_timings, &"retire_slice", began)
	return freed

## Cheap, explicitly incomplete accounting: chunk estimates deduplicate shared
## identities across roots; whole-map/outer-worker bytes are unknown here.
## The caller must read this on the main thread. Never joins or polls workers.
func diagnostic_snapshot() -> Dictionary:
	var shared: Dictionary = {}
	var seen: Dictionary = {}
	var roots: Array[Dictionary] = []
	var active := _diagnostic_root(active_root, shared, seen)
	active["state"] = "active"
	active["map"] = active_map
	roots.append(active)
	for map_id: String in residents:
		var row := _diagnostic_root(residents[map_id].root, shared, seen)
		row["state"] = "neighbour"
		row["map"] = map_id
		roots.append(row)
	for retired: Dictionary in _retiring:
		var row := _diagnostic_root(retired.resident.root, shared, seen)
		row["state"] = "retiring"
		row["map"] = str(retired.map)
		row["nodes_freed"] = int(retired.freed)
		row["prepared_visuals_remaining"] = (retired.visual_keys as Array).size()
		roots.append(row)
	var known_bytes := 0
	var unknown_whole_maps := 0
	for row: Dictionary in roots:
		known_bytes += int(row.get("total_estimated_bytes", 0))
		if row.get("kind", "") == "whole_map":
			unknown_whole_maps += 1
	return {"roots": roots, "known_chunk_estimated_bytes": known_bytes,
		"unknown_whole_map_roots": unknown_whole_maps,
		"in_flight_maps": 1 if _thread != null else 0,
		"in_flight_map": _pending_map if _thread != null else "",
		"in_flight_map_age_us": maxi(0, Time.get_ticks_usec() - _pending_started_usec) if _thread != null else 0,
		"outer_worker_bytes_known": false,
		"orphan_workers": ContinentChunkStream.orphan_diagnostic_snapshot(),
		"shared_retirement": RetirementBudget.diagnostic_snapshot(),
		"timings": ResourceDiagnostics.snapshot(_resource_timings),
		"last_preparation": _last_preparation.duplicate(true)}

static func _diagnostic_root(imported: Variant, shared: Dictionary, seen: Dictionary) -> Dictionary:
	if not is_instance_valid(imported) or not imported is Node3D:
		return {"kind": "absent"}
	var identity := (imported as Node3D).get_instance_id()
	if seen.has(identity):
		return {"kind": "already_counted"}
	seen[identity] = true
	if imported is ContinentChunkStream:
		var result := (imported as ContinentChunkStream).resource_estimates(shared)
		result["kind"] = "chunks"
		result["timings"] = (imported as ContinentChunkStream).resource_timings_snapshot()
		return result
	return {"kind": "whole_map", "estimate_available": false}

## How far each side of a border between two Landfall isles their light
## blends. The links publish no blend (blendDistance 0), so the sky, the sun
## and the haze switched at a line through the link's anchor, and once every
## isle had its own sky that line showed. The owner's rule for the isles is a
## gradual change across about 260 m (the ground regrade's featherMetres 130
## each side); the light now takes the same width.
const ISLE_LIGHT_BLEND_METRES := 130.0

## True for a seamless link between two continent-v2 isles that ships its
## shared border (preloadEdges), whose distance is then the seam's.
func _isle_border(candidate: Dictionary) -> bool:
	if (candidate.here.get("preloadEdges", []) as Array).is_empty():
		return false
	for map_id: String in [active_map, str(candidate.map)]:
		if str(MapRegistry.resolve(registry, map_id).get("status", "")) != "continent-v2-served":
			return false
	return true

func lighting_manifest(position: Vector3) -> WorldManifest:
	if active_manifest == null:
		return null
	for candidate: Dictionary in _candidates(position):
		if not bool(candidate.seamless) or not residents.has(str(candidate.map)):
			continue
		var here: Dictionary = candidate.here.frame
		var normal := Vector3(float(here.outward[0]), 0, float(here.outward[1]))
		var depth := (position - _vector(here.anchor)).dot(normal)
		var width := float(here.get("blendDistance", 65))
		if width <= 0.0 and _isle_border(candidate):
			# Measured from the shared border itself, which the player is
			# always on this side of: half the neighbour's light on the line,
			# none ISLE_LIGHT_BLEND_METRES in.
			width = ISLE_LIGHT_BLEND_METRES
			depth = -float(candidate.distance)
		if depth <= -width:
			continue
		var weight := smoothstep(-width, width, depth)
		var other: WorldManifest = residents[str(candidate.map)].manifest
		var far: Dictionary = other.data.get("environment", {}).duplicate(true)
		# A region's authored sun direction must never turn the shared sun as
		# the player approaches it. Blend its colour/energy and atmosphere only.
		for block: Dictionary in [far, far.get("goldenHour", {})]:
			var sun: Dictionary = block.get("sun", {})
			sun.erase("direction")
			sun.erase("rotationDegrees")
		var blended := WorldManifest.new()
		blended.source_path = active_manifest.source_path
		blended.data = active_manifest.data.duplicate()
		blended.data.environment = _blend(active_manifest.data.get("environment", {}), far, weight)
		return blended
	return active_manifest

static func _blend(a: Variant, b: Variant, weight: float) -> Variant:
	if a is Dictionary and b is Dictionary:
		var result: Dictionary = a.duplicate(true)
		for key: Variant in b:
			result[key] = _blend(a[key], b[key], weight) if a.has(key) else b[key]
		return result
	if a is Array and b is Array and a.size() == b.size():
		var values: Array = []
		for index: int in a.size():
			values.append(_blend(a[index], b[index], weight))
		return values
	if (a is float or a is int) and (b is float or b is int):
		return lerpf(float(a), float(b), weight)
	return a

func clear(preserve_expected_walk := false) -> void:
	# Keep existing retirement jobs; surrender only the old waiting turn.
	RetirementBudget.cancel(self)
	var tree := Engine.get_main_loop() as SceneTree
	var state := tree.root.get_node_or_null("AppState") if tree != null else null
	var current := MapRegistry.normalize_server_map_id(str(state.get("current_map"))) if state != null else ""
	var keep_walk := (preserve_expected_walk and bool(pending_walk.get("routed", false))
		and not current.is_empty() and current == str(pending_walk.get("next_map", ""))
		and current != str(pending_walk.get("issued_from", "")))
	_generation += 1
	active_map = ""
	active_root = null
	active_manifest = null
	for map_id: String in residents.keys():
		_evict(map_id)
	_retry_after.clear()
	if not keep_walk:
		pending_walk.clear()

func pick_neighbor(space: PhysicsDirectSpaceState3D, origin: Vector3, direction: Vector3, run: bool) -> Variant:
	pending_walk.clear()
	var query := PhysicsRayQueryParameters3D.create(origin, origin + direction * 2000, PREVIEW_SURFACE_LAYER)
	var hit := space.intersect_ray(query)
	if hit.is_empty():
		return null
	var point: Vector3 = hit.position
	var foreground := space.intersect_ray(PhysicsRayQueryParameters3D.create(
		origin, origin + direction * 2000, WorldLoader.NAVIGATION_SURFACE_LAYER))
	if (not foreground.is_empty()
			and not "_StreamOverflow" in str(foreground.collider.get_parent().name)
			and not "_StreamThreshold" in str(foreground.collider.get_parent().name)
			and origin.distance_squared_to(foreground.position) + .01 < origin.distance_squared_to(point)):
		return null
	for candidate: Dictionary in _candidates(_last_position):
		var map_id := str(candidate.map)
		if not (bool(candidate.seamless) or bool(candidate.visual_only)) or not residents.has(map_id):
			continue
		var imported := residents[map_id].root as Node3D
		if not imported.is_ancestor_of(hit.collider):
			continue
		var frame: Dictionary = candidate.here.frame
		var outward := Vector3(float(frame.outward[0]), 0, float(frame.outward[1]))
		var anchor := _vector(frame.anchor)
		# Owned footprints can wrap behind the road plane at a shared corner.
		# Their real geometry, foreground occlusion and served bounds decide the
		# target; a local collar still needs the legacy outward-side restriction.
		var full_owned := str(candidate.there.frame.get("geometryMode", "")) in ["continent-owned-v1", "continent-chunks-v1"]
		if not full_owned and (point - anchor).dot(outward) <= 0:
			continue
		var target_manifest := residents[map_id].manifest as WorldManifest
		var adapter := target_manifest.coordinate_adapter()
		var tile := adapter.godot_to_server(imported.transform.affine_inverse() * point)
		var dimensions: Variant = target_manifest.data.get("coordinateTransform", {}).get("serverCells",
			target_manifest.data.get("asset", {}).get("serverCells", 0))
		var bounds: Dictionary = target_manifest.data.get("coordinateTransform", {}).duplicate(true)
		bounds["serverCells"] = dimensions
		if not tile_inside(bounds, tile):
			return null
		# Route through the centre of the surveyed road. The server decides
		# whether the approach and the continuation are walkable.
		return arm_walk_to(map_id, tile, run, point)
	return null

## A walk order to a tile of a neighbour: the first leg to the surveyed seam
## crossing, the rest carried by take_continuation at the map change. Returns
## the leg's target point in the active map, or null when the tile lies
## outside that map's served cells or no seamless road leads there.
func arm_walk_to(map_id: String, tile: Vector2i, run: bool, world_point: Vector3) -> Variant:
	pending_walk.clear()
	if not tile_inside(region_coordinates(map_id), tile):
		return null
	var leg := _first_walk_leg(active_map, map_id)
	if leg.is_empty():
		return null
	pending_walk = {"map": map_id, "tile": tile, "run": run, "world_point": world_point,
		"routed": true, "issued_from": active_map, "next_map": str(leg.there.map)}
	if coordinate_context != null and coordinate_context.selected:
		if not coordinate_context.ready():
			pending_walk.clear()
			return null
		pending_walk["coordinate_token"] = coordinate_context.token()
	var fallback: Dictionary = active_manifest.data.get("coordinateTransform", {}) if active_manifest != null else {}
	var here_adapter := CoordinateAdapter.new(leg.here.get("coordinateTransform", fallback))
	var crossing := best_crossing(leg.here, here_adapter, _last_position, world_point)
	_arm_walk_leg(active_map, crossing, _local_walk_actor(active_map))
	if crossing == here_adapter.godot_to_server(_vector(leg.here.position)):
		return _vector(leg.here.position)
	return here_adapter.tile_center(crossing.x, crossing.y)

## Where a border can be crossed, in its near map's own tiles: the runs the
## survey ships with each end, expanded. Empty for a survey written before the
## borders opened, which leaves a walk to the gate the survey anchors.
static func crossing_tiles(end: Dictionary) -> Array[Vector2i]:
	var result: Array[Vector2i] = []
	var packed: Variant = end.get("crossingRuns")
	if packed is not Dictionary:
		return result
	var along_x := str((packed as Dictionary).get("axis", "x")) == "x"
	for run: Variant in (packed as Dictionary).get("runs", []) as Array:
		if run is not Array or (run as Array).size() != 3:
			continue
		var line := int(run[0])
		for step: int in range(int(run[1]), int(run[2]) + 1):
			result.append(Vector2i(step, line) if along_x else Vector2i(line, step))
	return result

## The crossing of a border that makes the shortest walk from `from` to `to`,
## both in the active map's frame. A border open along its length is crossed on
## whichever of its tiles is on the way, not at the gate the survey anchors; a
## click a step across the border used to send the walker round by the gate,
## which could be the far end of the border. Without shipped crossings, the gate.
static func best_crossing(end: Dictionary, adapter: CoordinateAdapter, from: Vector3, to: Vector3) -> Vector2i:
	var best := adapter.godot_to_server(_vector(end.position))
	var best_cost := INF
	for tile: Vector2i in crossing_tiles(end):
		var at := adapter.tile_center(tile.x, tile.y)
		var cost := Vector2(at.x - from.x, at.z - from.z).length() + Vector2(to.x - at.x, to.z - at.z).length()
		if cost < best_cost:
			best_cost = cost
			best = tile
	return best

## The direct seamless links out of the active map, as {map, here, there}.
func _direct_links() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for link: Dictionary in links:
		if not bool(link.get("seamless", false)):
			continue
		var ends: Array = link.ends
		for index: int in 2:
			if str(ends[index].map) == active_map:
				result.append({"map": str(ends[1 - index].map), "here": ends[index], "there": ends[1 - index]})
	return result

## A neighbour's rigid frame in the active map: its resident root's while it
## stands, else the surveyed join of the direct seamless link. Null with neither.
func neighbour_transform(map_id: String) -> Variant:
	var resident: Variant = residents.get(map_id)
	if resident is Dictionary and is_instance_valid((resident as Dictionary).get("root") as Node3D):
		return ((resident as Dictionary).get("root") as Node3D).transform
	for candidate: Dictionary in _direct_links():
		if str(candidate.map) == map_id:
			return frame_transform(candidate.here.frame, candidate.there.frame)
	return null

## Any exterior region's placement in the active map's frame, loaded or not:
## the surveyed join of a direct seamless link where there is one (a resident
## root's own transform first), else the continent translations the registry
## publishes, where a region's metres are its global metres less its own
## translation. Null for a map the registry does not place on the continent.
func region_transform(map_id: String) -> Variant:
	var direct: Variant = neighbour_transform(map_id)
	if direct is Transform3D:
		return direct
	var here: Variant = _continent_translation(active_map)
	var there: Variant = _continent_translation(map_id)
	if here is Vector3 and there is Vector3:
		return Transform3D(Basis(), (there as Vector3) - (here as Vector3))
	return null

## Any exterior region's coordinate transform: a resident manifest's or a link
## end's, else the one the registry publishes for every map.
func region_coordinates(map_id: String) -> Dictionary:
	var known := neighbour_coordinates(map_id)
	if not known.is_empty():
		return known
	return MapRegistry.resolve(registry, map_id).get("coordinateTransform", {}) as Dictionary

## Where a region stands on the continent, from the registry's geography.
func _continent_translation(map_id: String) -> Variant:
	var geography: Dictionary = MapRegistry.resolve(registry, map_id).get("continentGeography", {}) as Dictionary
	var translation: Array = geography.get("translation", []) as Array
	if translation.size() != 3:
		return null
	return Vector3(float(translation[0]), float(translation[1]), float(translation[2]))

## The continent frame a region's geography names (`continentGeography.frame`):
## empty for the twelve-territory continent, "continent-v2" for the rebuilt one,
## whose regions share continent coordinates with nothing in the old frame.
func continent_frame(map_id: String) -> String:
	var geography: Dictionary = MapRegistry.resolve(registry, map_id).get("continentGeography", {}) as Dictionary
	return str(geography.get("frame", ""))

## Every exterior region the registry places on the active map's continent (its
## frame), the active map last.
func continent_maps() -> Array[String]:
	var result: Array[String] = []
	var frame := continent_frame(active_map)
	for key: Variant in registry.keys():
		var map_id: String = MapRegistry.normalize_server_map_id(str(key))
		if map_id == active_map or result.has(map_id):
			continue
		if _continent_translation(map_id) is Vector3 and continent_frame(map_id) == frame:
			result.append(map_id)
	return result

## A neighbour's coordinate transform: the resident manifest's, else the link end's.
func neighbour_coordinates(map_id: String) -> Dictionary:
	var resident: Variant = residents.get(map_id)
	if resident is Dictionary and (resident as Dictionary).get("manifest") is WorldManifest:
		return ((resident as Dictionary).get("manifest") as WorldManifest).data.get("coordinateTransform", {}) as Dictionary
	for candidate: Dictionary in _direct_links():
		if str(candidate.map) == map_id:
			return candidate.there.get("coordinateTransform", {}) as Dictionary
	return {}

## Logical minima do not alter the map's world/tile frame.
static func tile_inside(coordinates: Dictionary, tile: Vector2i) -> bool:
	var minimum: Array = coordinates.get("serverTileMin", [0, 0])
	var relative := tile - Vector2i(int(minimum[0]), int(minimum[1]))
	if relative.x < 0 or relative.y < 0:
		return false
	var dimensions: Variant = coordinates.get("serverCells", 0)
	var width := int(dimensions[0]) if dimensions is Array else int(dimensions)
	var height := int(dimensions[1]) if dimensions is Array else width
	return width <= 0 or (relative.x < width and relative.y < height)

## The region whose served tiles hold a point of the active map's frame, with
## that tile: what a map click past the seam means. The direct neighbours are
## asked first, on their surveyed joins; then every other region the registry
## places on the continent, so a click on a far map answers as well as one on
## the map next door. Empty when no region holds the point.
func map_at_local(point: Vector3, owner := "") -> Dictionary:
	# The territory that owns the ground, when the caller knows it: served cells
	# are squares that overlap their neighbours', so the first square holding the
	# point is not always the map whose ground it is.
	if not owner.is_empty():
		var tile_value: Variant = tile_on(owner, point)
		if tile_value is Vector2i:
			return {"map": owner, "tile": tile_value}
	var order: Array[String] = []
	for candidate: Dictionary in _direct_links():
		if not order.has(str(candidate.map)):
			order.append(str(candidate.map))
	for map_id: String in continent_maps():
		if not order.has(map_id):
			order.append(map_id)
	for map_id: String in order:
		var frame_value: Variant = region_transform(map_id)
		var coordinates := region_coordinates(map_id)
		if not frame_value is Transform3D or coordinates.is_empty():
			continue
		var local_point: Vector3 = (frame_value as Transform3D).affine_inverse() * point
		var tile: Vector2i = CoordinateAdapter.new(coordinates).godot_to_server(local_point)
		if tile_inside(coordinates, tile):
			return {"map": map_id, "tile": tile}
	return {}

## A map's tile under a point of the active map's frame, or null outside its cells.
func tile_on(map_id: String, point: Vector3) -> Variant:
	var frame_value: Variant = region_transform(map_id)
	var coordinates := region_coordinates(map_id)
	if not frame_value is Transform3D or coordinates.is_empty():
		return null
	var tile: Vector2i = CoordinateAdapter.new(coordinates).godot_to_server(
		(frame_value as Transform3D).affine_inverse() * point)
	return tile if tile_inside(coordinates, tile) else null

func _local_walk_actor(map_id: String) -> Dictionary:
	var tree := Engine.get_main_loop() as SceneTree
	var state := tree.root.get_node_or_null("AppState") if tree != null else null
	if state == null or MapRegistry.normalize_server_map_id(str(state.get("current_map"))) != map_id:
		return {}
	var actors: Dictionary = state.get("actors")
	return actors.get(int(state.get("local_actor_id")), {})

func _arm_walk_leg(map_id: String, tile: Vector2i, actor: Dictionary) -> void:
	pending_walk.issued_from = map_id
	pending_walk.leg_tile = tile
	pending_walk.observed_commands = 0
	pending_walk.renewals = 0
	pending_walk.last_sequence = int(actor.get("command_sequence", -1))
	pending_walk.last_tile = Vector2i(int(actor.get("x", -1)), int(actor.get("y", -1)))

func take_continuation(map_id: String, actor := {}) -> Dictionary:
	if pending_walk.is_empty():
		return {}
	if not _walk_context_current(map_id):
		pending_walk.clear()
		return {}
	if actor.is_empty():
		actor = _local_walk_actor(map_id)
	if not actor.is_empty() and (not bool(actor.get("alive", true))
			or bool(actor.get("in_combat", false)) or bool(actor.get("sitting", false))):
		pending_walk.clear()
		return {}
	var destination := str(pending_walk.get("map", ""))
	var issued_from := str(pending_walk.get("issued_from", ""))
	if issued_from != map_id:
		# An unrelated doorway or teleport must not turn into a new road order.
		# The final walking leg has no next map at all; a warm resident adoption
		# skips clear(), so it must reject an unexpected transition here too.
		if str(pending_walk.get("next_map", "")) != map_id:
			_record("walk_cancelled", map_id, {"reason": "unexpected map"})
			pending_walk.clear()
			return {}
		var target: Vector2i
		if map_id == destination:
			target = pending_walk.tile
			pending_walk.erase("next_map")
		else:
			var leg := _first_walk_leg(map_id, destination)
			if leg.is_empty():
				pending_walk.clear()
				return {}
			var adapter := CoordinateAdapter.new(leg.here.coordinateTransform)
			target = adapter.godot_to_server(_vector(leg.here.position))
			var destination_coordinates := region_coordinates(destination)
			var here_translation: Variant = _continent_translation(map_id)
			var destination_translation: Variant = _continent_translation(destination)
			if actor.has("x") and actor.has("y") and not destination_coordinates.is_empty() \
					and here_translation is Vector3 and destination_translation is Vector3:
				var from := adapter.tile_center(int(actor.x), int(actor.y))
				var destination_adapter := CoordinateAdapter.new(destination_coordinates)
				var to := destination_adapter.tile_center(pending_walk.tile.x, pending_walk.tile.y)
				to += (destination_translation as Vector3) - (here_translation as Vector3)
				target = best_crossing(leg.here, adapter, from, to)
			pending_walk.next_map = str(leg.there.map)
		_arm_walk_leg(map_id, target, actor)
		if map_id == destination and not actor.is_empty() and pending_walk.last_tile == target:
			pending_walk.clear()
			return {}
		return {"tile": target, "run": pending_walk.run}
	if actor.is_empty() or not pending_walk.has("leg_tile"):
		return {}
	var here := Vector2i(int(actor.get("x", -1)), int(actor.get("y", -1)))
	var target: Vector2i = pending_walk.leg_tile
	if here == target:
		if map_id == destination:
			pending_walk.clear()
		return {} # At a gate, preserve the exact final click until its handoff.
	var sequence := int(actor.get("command_sequence", -1))
	var prior_sequence := int(pending_walk.get("last_sequence", -1))
	var prior_tile: Vector2i = pending_walk.get("last_tile", here)
	# Multiple packets can be reduced before one visual update. Sequence deltas
	# retain that movement count even around bends; distance-to-target cannot.
	if here != prior_tile and prior_sequence >= 0 and sequence > prior_sequence:
		pending_walk.observed_commands = int(pending_walk.get("observed_commands", 0)) + sequence - prior_sequence
	pending_walk.last_sequence = sequence
	pending_walk.last_tile = here
	if int(pending_walk.get("observed_commands", 0)) < WALK_RENEW_COMMANDS:
		return {}
	if int(pending_walk.get("renewals", 0)) >= MAX_WALK_RENEWALS_PER_LEG:
		_record("walk_cancelled", map_id, {"reason": "road renewal budget exhausted"})
		pending_walk.clear()
		return {}
	pending_walk.renewals = int(pending_walk.get("renewals", 0)) + 1
	pending_walk.observed_commands = 0
	_record("walk_renewed", map_id, {"target": [target.x, target.y], "renewal": pending_walk.renewals})
	return {"tile": target, "run": pending_walk.run}

func _walk_context_current(map_id: String) -> bool:
	if coordinate_context == null or not coordinate_context.selected:
		# A route from an earlier capable connection must never become legacy.
		return not pending_walk.has("coordinate_token")
	if not coordinate_context.ready() or not pending_walk.has("coordinate_token"):
		return false
	var old: Dictionary = pending_walk.coordinate_token
	var current: Dictionary = coordinate_context.token()
	if current == old:
		return true
	# Only the immediately expected next road leg may capture the new epoch.
	# Same-map teleports and A→B→A before presentation cannot revive a click.
	if current.generation != old.generation or current.epoch != old.epoch + 1 \
			or current.map == old.map or map_id != current.map \
			or str(pending_walk.get("next_map", "")) != current.map:
		return false
	pending_walk.coordinate_token = current
	return true

func _first_walk_leg(source: String, destination: String) -> Dictionary:
	# Visible geography can meet across a river or cliff without a crossing.
	# A click there follows surveyed roads, retaining the exact final tile.
	var queue: Array[Dictionary] = [{"map": source, "first": {}}]
	var visited := {source: true}
	while not queue.is_empty():
		var at: Dictionary = queue.pop_front()
		for link: Dictionary in links:
			# A view-only link draws a neighbour across a border nobody can cross:
			# a walk routed over it went to the middle of that border and stopped.
			if not bool(link.get("seamless", false)) or bool(link.get("visualOnly", false)):
				continue
			for i: int in 2:
				var here: Dictionary = link.ends[i]
				var there: Dictionary = link.ends[1-i]
				if str(here.map) != str(at.map) or visited.has(str(there.map)):
					continue
				var first: Dictionary = at.first if not at.first.is_empty() else {"here": here, "there": there}
				if str(there.map) == destination:
					return first
				visited[str(there.map)] = true
				queue.append({"map": str(there.map), "first": first})
	return {}

func is_idle() -> bool:
	ContinentChunkStream.reap_orphans()
	return _thread == null and _retiring.is_empty() and ContinentChunkStream.orphans_pending() == 0

func _record(kind: String, map_id: String, detail := {}) -> void:
	var entry := {"event": kind, "map": map_id, "at_ms": Time.get_ticks_msec()}
	entry.merge(detail)
	events.append(entry)
	if events.size() > 100:
		events.pop_front()
	print("exterior_stream ", JSON.stringify(entry))

func _exit_tree() -> void:
	RetirementBudget.cancel(self)

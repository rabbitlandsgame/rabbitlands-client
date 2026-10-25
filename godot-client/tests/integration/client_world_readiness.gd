extends RefCounted
## Shared test-only world readiness. Ordinary Main does not need profiling.
const STABLE_RESOURCE_FRAMES := 12
const MINIMUM_READINESS_MSEC := 1000
const STARTUP_TIMEOUT_MSEC := 180000

static func snapshot(main: Node) -> Dictionary:
	var world_loader := main.get("world_loader") as WorldLoader
	var exterior_stream := main.get("exterior_stream") as ExteriorRegionStream
	var camera_rig: Variant = main.get("camera_rig")
	var ambient_population := main.get("ambient_population") as Node
	var loaded_server_map := str(main.get("loaded_server_map"))
	var current_map := str(main.get_tree().root.get_node("AppState").get("current_map"))
	var _deferred_map_load := bool(main.get("_deferred_map_load"))
	var _actor_surface_snap_pending := bool(main.get("_actor_surface_snap_pending"))
	var chunk_states: Array[Dictionary] = []
	var roots: Array[Node3D] = []
	if is_instance_valid(world_loader.world_root):
		roots.append(world_loader.world_root)
	for resident: Dictionary in exterior_stream.residents.values():
		var resident_root := resident.get("root") as Node3D
		if is_instance_valid(resident_root) and resident_root not in roots:
			roots.append(resident_root)
	var ready := world_loader.world_root != null and loaded_server_map == current_map and not _deferred_map_load \
		and not _actor_surface_snap_pending and exterior_stream.is_idle() \
		and int(world_loader.get("_cache_write_countdown")) <= 0
	for candidate: Node3D in roots:
		var chunk := candidate as ContinentChunkStream
		if chunk == null:
			continue
		var views := chunk.get("_preload_views") as Array
		var state := {"cells": chunk.cells.size(), "pendingThread": chunk.get("_thread") != null,
			"retiring": (chunk.get("_retiring") as Array).size(),
			"viewsReady": views.is_empty() or chunk.views_ready(), "viewsFailed": chunk.views_failed(),
			"prefetchReady": chunk.prefetch_ready()}
		if chunk == world_loader.world_root:
			state["arrivalReady"] = chunk.arrival_ready(camera_rig.focus)
		ready = ready and not bool(state.pendingThread) and int(state.retiring) == 0 \
			and bool(state.viewsReady) and not bool(state.viewsFailed) and bool(state.prefetchReady) \
			and bool(state.get("arrivalReady", true))
		chunk_states.append(state)
	var ambient_pending := 0
	if is_instance_valid(ambient_population):
		ambient_pending = (ambient_population.get("_pending_cells") as Dictionary).size()
	var ambient_creation_pending := ambient_pending
	if main.has_method("ambient_creation_pending_count"):
		ambient_creation_pending = int(main.call("ambient_creation_pending_count"))
	elif is_instance_valid(ambient_population) and ambient_population.has_method("pending_creation_count"):
		ambient_creation_pending = int(ambient_population.call("pending_creation_count"))
	var followup := {"pending": 0, "available": false}
	if main.has_method("surface_work_snapshot"):
		followup = main.call("surface_work_snapshot") as Dictionary
	ready = ready and ambient_creation_pending == 0 and int(followup.get("pending", 0)) == 0 \
		and ContinentChunkStream.orphans_pending() == 0
	return {"ready": ready, "loadedMap": loaded_server_map, "chunks": chunk_states,
		"actorGroundingPending": _actor_surface_snap_pending,
		"ambientPendingCells": ambient_pending, "ambientPendingCreation": ambient_creation_pending,
		"surfaceFollowups": followup,
		"orphanImports": ContinentChunkStream.orphans_pending(),
		"exteriorIdle": exterior_stream.is_idle()}


static func resource_signature(main: Node) -> String:
	var loader := main.get("world_loader") as WorldLoader
	var chunk := loader.world_root as ContinentChunkStream if loader != null else null
	return "%d|%d|%d" % [GlbSceneCache.cached_scene_count(),
		int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT)),
		chunk.cells.size() if chunk != null else -1]


class StableResources:
	extends RefCounted
	var started_msec: int
	var stable_frames := 0
	var previous := ""

	func _init(start: int) -> void:
		started_msec = start

	func observe(signature: String, idle: bool, now: int) -> bool:
		stable_frames = stable_frames + 1 if signature == previous and idle else 0
		previous = signature
		return now - started_msec >= MINIMUM_READINESS_MSEC and stable_frames >= STABLE_RESOURCE_FRAMES

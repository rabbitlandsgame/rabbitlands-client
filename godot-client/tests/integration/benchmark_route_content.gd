extends RefCounted
## Synthetic benchmark boundaries only. No disk reads, worker joins, budget
## overrides or production telemetry. All returned values are JSON scalars.
const VramTextures := preload("res://src/world/vram_textures.gd")

static func clock() -> Dictionary:
	return {"unixTime": Time.get_unix_time_from_system(), "ticksUsec": Time.get_ticks_usec()}

static func _ids(entries: Array) -> Array[String]:
	var result: Array[String] = []
	for entry: Dictionary in entries:
		result.append(str(entry.get("id", "")))
	result.sort()
	return result

static func _keys(values: Dictionary) -> Array[String]:
	var result: Array[String] = []
	for key: Variant in values:
		result.append(str(key))
	result.sort()
	return result

static func _manifest(value: WorldManifest) -> Dictionary:
	if value == null:
		return {"assetId": "", "parsedManifestSha256": ""}
	# This is a fingerprint of the parsed manifest, not a verification result or
	# an attestation of loose bytes. The runner still verifies the asset closure.
	return {"assetId": value.asset_id(),
		"parsedManifestSha256": JSON.stringify(value.data).sha256_text()}

static func _transform(value: Transform3D) -> Array:
	return [value.basis.x.x, value.basis.x.y, value.basis.x.z,
		value.basis.y.x, value.basis.y.y, value.basis.y.z,
		value.basis.z.x, value.basis.z.y, value.basis.z.z,
		value.origin.x, value.origin.y, value.origin.z]

static func _root(map_id: String, role: String, root: Node3D,
		manifest: WorldManifest, digest: String, allow_selection: bool, errors: Array[String]) -> Dictionary:
	var result := {"map": map_id, "role": role, "manifest": _manifest(manifest),
		"actualPackageDigest": digest}
	if not is_instance_valid(root):
		errors.append("missing root: " + map_id)
		return result
	result["transform"] = _transform(root.transform)
	result["visible"] = root.visible
	if manifest == null or not manifest.is_valid():
		errors.append("missing or invalid manifest: " + map_id)
	var stream := root as ContinentChunkStream
	if stream == null:
		result["kind"] = "whole_map"
		return result
	result["kind"] = "chunked"
	result["hasFocus"] = stream.has_focus
	result["focus"] = [stream.focus.x, stream.focus.y, stream.focus.z]
	result["paused"] = bool(stream.get("_paused"))
	result["policy"] = {"preloadDistance": stream.preload_distance,
		"retainDistance": stream.retain_distance, "maximumChunks": stream.maximum_chunks,
		"maximumResidentBytes": stream.maximum_resident_bytes}
	var pending := stream.get("_pending") as Dictionary
	var retiring := stream.get("_retiring") as Array
	result["pendingId"] = str(pending.get("id", ""))
	result["pendingThread"] = stream.get("_thread") != null
	var retired_ids: Array[String] = []
	for retired: Dictionary in retiring:
		retired_ids.append(str((retired.get("entry", {}) as Dictionary).get("id", "")))
	retired_ids.sort()
	result["retiringIds"] = retired_ids
	var idle := not bool(result.pendingThread) and pending.is_empty() and retiring.is_empty()
	if not idle:
		errors.append("non-idle stream: " + map_id)
	var views := stream.get("_preload_views") as Array
	var prefetch := stream.get("_prefetch") as Array
	result["preloadViewIds"] = _ids(views)
	result["prefetchIds"] = _ids(prefetch)
	result["residentIds"] = _keys(stream.cells)
	var residents: Array[Dictionary] = []
	for identity: String in result.residentIds:
		var resident := stream.cells[identity] as Dictionary
		var imported := resident.get("root") as Node3D
		var entry := resident.get("entry", {}) as Dictionary
		var resident_manifest := resident.get("manifest") as WorldManifest
		residents.append({"id": identity, "package": str(entry.get("manifest", "")),
			"declaredPackageDigest": str(entry.get("packageDigest", "")),
			"actualPackageDigest": str(resident.get("digest", "")),
			"manifest": _manifest(resident_manifest)})
		if not is_instance_valid(imported) or imported.get_parent() != stream \
				or resident_manifest == null or not resident_manifest.is_valid():
			errors.append("invalid resident: " + map_id + "/" + identity)
	result["residents"] = residents
	result["selectedIds"] = []
	result["wantedIds"] = []
	# selection() normally refreshes accounting before choosing. Do not let a
	# diagnostic trigger that mutation: with ready workers and no await, a
	# matching generation makes the existing selector a read-only calculation.
	var corrected := int(stream.get("_corrected_generation"))
	var generation := VramTextures.budget_generation()
	result["selectionFresh"] = corrected == generation
	if not allow_selection or not idle or not stream.has_focus or bool(result.paused) or corrected != generation:
		errors.append("selection unavailable or stale: " + map_id)
		return result
	var selected: Array[Dictionary] = stream.selection(stream.focus, true)
	result["selectedIds"] = _ids(selected)
	var wanted: Dictionary = {}
	for identity: String in result.selectedIds:
		wanted[identity] = true
	for identity: String in result.prefetchIds:
		wanted[identity] = true
	result["wantedIds"] = _keys(wanted)
	if int(stream.get("_corrected_generation")) != corrected \
			or VramTextures.budget_generation() != generation:
		errors.append("selection generation changed during capture: " + map_id)
	return result

static func capture(main: Node) -> Dictionary:
	var began := Time.get_ticks_usec()
	var errors: Array[String] = []
	var readiness := main.call("benchmark_readiness_snapshot") as Dictionary
	var result := {"schemaVersion": 1, "clock": clock(), "readiness": readiness,
		"complete": false, "errors": errors,
		"selectionSemantics": "current retention selector at stored focus; not a historical admission trace"}
	if not bool(readiness.get("ready", false)):
		errors.append("world not ready at boundary")
	var loader := main.get("world_loader") as WorldLoader
	var exterior := main.get("exterior_stream") as ExteriorRegionStream
	if loader == null or exterior == null:
		errors.append("missing loader or exterior stream")
		result["captureMicroseconds"] = Time.get_ticks_usec() - began
		return result
	var loaded_map := str(main.get("loaded_server_map"))
	result["loadedMap"] = loaded_map
	var runtime := main.call("benchmark_runtime_snapshot") as Dictionary
	result["effectiveSettings"] = (runtime.get("effectiveSettings", {}) as Dictionary).duplicate(true)
	result["vram"] = {"mode": VramTextures.mode_name(),
		"formats": VramTextures.format_names(VramTextures.usable_formats())}
	var selected_maps: Dictionary = {}
	if not exterior.active_map.is_empty():
		# Both methods only calculate from the already-stored exterior position.
		var candidates := exterior.call("_candidates", exterior.get("_last_position")) as Array
		selected_maps = exterior.call("_wanted_neighbours", candidates) as Dictionary
	var retired_maps: Array[String] = []
	for retired: Dictionary in exterior.get("_retiring") as Array:
		retired_maps.append(str(retired.get("map", "")))
	retired_maps.sort()
	result["exterior"] = {"activeMap": exterior.active_map,
		"selectedMaps": _keys(selected_maps), "residentMaps": _keys(exterior.residents),
		"retiringMaps": retired_maps, "pendingMap": str(exterior.get("_pending_map")),
		"pendingThread": exterior.get("_thread") != null,
		"policy": {"preloadDistance": exterior.preload_distance,
			"retainDistance": exterior.retain_distance, "maximumNeighbours": exterior.maximum_neighbours}}
	if exterior.get("_thread") != null or not retired_maps.is_empty() \
			or not str(exterior.get("_pending_map")).is_empty():
		errors.append("non-idle exterior stream")
	if is_instance_valid(exterior.active_root) and exterior.active_root != loader.world_root:
		errors.append("active exterior/loader root mismatch")
	var streams: Array[Dictionary] = []
	var allow_selection := bool(readiness.get("ready", false)) and errors.is_empty()
	streams.append(_root(loaded_map, "active", loader.world_root, loader.manifest,
		loader.package_digest, allow_selection, errors))
	for map_id: String in _keys(exterior.residents):
		var resident := exterior.residents[map_id] as Dictionary
		streams.append(_root(map_id, "neighbour", resident.get("root") as Node3D,
			resident.get("manifest") as WorldManifest, str(resident.get("digest", "")), allow_selection, errors))
	result["streams"] = streams
	result["complete"] = errors.is_empty()
	result["captureMicroseconds"] = Time.get_ticks_usec() - began
	return result

extends RefCounted
## Explicit benchmark boundaries only: no selectors, loads, worker joins or
## materialization during capture. JSON output contains no live Node/Resource.
const Placements := preload("res://src/world/prepared_placements.gd")
const Prepared := preload("res://src/world/prepared_content.gd")

static func _enabled(node: Node) -> bool:
	if not is_instance_valid(node) or not node.is_inside_tree():
		return false
	var current: Node = node
	while current != null:
		if current.is_queued_for_deletion() or current.process_mode == Node.PROCESS_MODE_DISABLED:
			return false
		current = current.get_parent()
	return true

static func _counts(node: Node) -> Dictionary:
	var nodes := 0
	var visuals := 0
	var pending: Array[Node] = [node]
	while not pending.is_empty():
		var current: Node = pending.pop_back()
		if not is_instance_valid(current):
			continue
		nodes += 1
		visuals += 1 if current is VisualInstance3D else 0
		for child: Node in current.get_children(true):
			pending.append(child)
	return {"nodes": nodes, "visualInstances": visuals}

static func _gather(map_id: String, role: String, imported: Node3D, manifest: WorldManifest,
		chunk_id: String, entry: Dictionary, seen: Dictionary, rows: Array[Dictionary]) -> void:
	if not is_instance_valid(imported) or seen.has(imported.get_instance_id()):
		return
	seen[imported.get_instance_id()] = true
	var stream := imported as ContinentChunkStream
	if stream != null:
		var identities: Array = stream.cells.keys()
		identities.sort()
		for identity: String in identities:
			var resident: Dictionary = stream.cells[identity]
			var child := resident.get("root") as Node3D
			if is_instance_valid(child) and child.get_parent() == stream:
				_gather(map_id, role, child, resident.get("manifest") as WorldManifest,
					identity, resident.get("entry", {}) as Dictionary, seen, rows)
		return
	rows.append({"map": map_id, "role": role, "chunkId": chunk_id,
		"root": imported, "manifest": manifest, "entry": entry})

static func _resident_roots(loader: WorldLoader, exterior: ExteriorRegionStream, map_id: String) -> Array[Dictionary]:
	var rows: Array[Dictionary] = []
	var seen: Dictionary = {}
	if is_instance_valid(loader):
		_gather(map_id, "active", loader.world_root, loader.manifest, "", {}, seen, rows)
	if is_instance_valid(exterior):
		var identities: Array = exterior.residents.keys()
		identities.sort()
		for identity: String in identities:
			var resident: Dictionary = exterior.residents[identity]
			_gather(identity, "neighbour", resident.get("root") as Node3D,
				resident.get("manifest") as WorldManifest, "", {}, seen, rows)
	return rows

static func _snapshot(row: Dictionary) -> Dictionary:
	var imported := row.root as Node3D
	var manifest := row.manifest as WorldManifest
	var source := Prepared.logical_source(manifest.source_path) if manifest != null else ""
	var entry: Dictionary = row.entry
	var entry_ids: Array[String] = []
	var policies: Array[String] = []
	for handle: Placements.Handle in Placements.handles(imported):
		var identity := str(handle.entry.get("entry_id", ""))
		if not identity.is_empty() and identity not in entry_ids:
			entry_ids.append(identity)
		var policy := str(handle.entry.get("node_policy", ""))
		if not policy.is_empty() and policy not in policies:
			policies.append(policy)
	entry_ids.sort()
	policies.sort()
	return {"map": str(row.map), "role": str(row.role), "chunkId": str(row.chunkId),
		"worldSource": source, "assetId": manifest.asset_id() if manifest != null else "",
		"declaredChunkId": str(entry.get("id", "")),
		"declaredPackageDigest": str(entry.get("packageDigest", "")),
		"processEnabled": _enabled(imported), "counts": _counts(imported),
		"runtimeEntryIds": entry_ids, "runtimeEntryNodePolicies": policies,
		"placements": Placements.snapshot(imported)}

static func capture(loader: WorldLoader, exterior: ExteriorRegionStream, map_id: String, ready: bool) -> Dictionary:
	var began := Time.get_ticks_usec()
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return {"status": "unavailable", "reason": "foreign_thread", "roots": []}
	var rows: Array[Dictionary] = []
	var total_nodes := 0
	var total_visuals := 0
	for resident: Dictionary in _resident_roots(loader, exterior, map_id):
		var row := _snapshot(resident)
		total_nodes += int(row.counts.nodes)
		total_visuals += int(row.counts.visualInstances)
		rows.append(row)
	return {"schemaVersion": 1, "status": "captured", "readyBoundary": ready,
		"selectedNodePolicy": Placements.selected_policy(), "roots": rows,
		"counts": {"nodes": total_nodes, "visualInstances": total_visuals},
		"scope": "disjoint imported resident roots; excludes stream containers and retiring queues",
		"counterWindow": "cumulative for each currently resident root; not per-sample deltas",
		"captureMicroseconds": Time.get_ticks_usec() - began}

static func restore_one(loader: WorldLoader, exterior: ExteriorRegionStream, map_id: String,
		target_map: String, target_chunk: String, ready: bool) -> Dictionary:
	var result := {"functionalOnly": true, "targetMap": target_map, "targetChunk": target_chunk,
		"status": "not_ready", "readyBoundary": ready}
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or not ready:
		return result
	var matches: Array[Dictionary] = []
	for row: Dictionary in _resident_roots(loader, exterior, map_id):
		if str(row.map) == target_map and str(row.chunkId) == target_chunk:
			matches.append(row)
	if matches.size() != 1:
		result["status"] = "target_not_unique"
		result["matches"] = matches.size()
		return result
	var row: Dictionary = matches[0]
	var imported := row.root as Node3D
	if not _enabled(imported):
		return result
	result["before"] = _snapshot(row)
	for handle: Placements.Handle in Placements.handles(imported):
		if handle.root_node() != imported or handle.node() != null or handle.pinned:
			continue
		var restored := handle.restore(false)
		if not is_instance_valid(restored):
			result["status"] = "restore_failed"
			return result
		result["afterRestore"] = _snapshot(row)
		var repeated := handle.restore(false)
		result["afterRepeat"] = _snapshot(row)
		result["repeatSameNode"] = repeated == restored
		var before: Dictionary = result.before
		var after: Dictionary = result.afterRestore
		var again: Dictionary = result.afterRepeat
		var checks := {"nodeCountPlusOne": int(after.counts.nodes) == int(before.counts.nodes) + 1,
			"visualCountPlusOne": int(after.counts.visualInstances) == int(before.counts.visualInstances) + 1,
			"reifiedPlusOne": int(after.placements.reified_sources) == int(before.placements.reified_sources) + 1,
			"remainingMinusOne": int(after.placements.remaining_node_reduction) == int(before.placements.remaining_node_reduction) - 1,
			"initialRemovalStable": after.placements.initial_removed_sources == before.placements.initial_removed_sources,
			"unpinned": after.placements.pinned_interactives == before.placements.pinned_interactives,
			"repeatSameNode": repeated == restored, "repeatUnchanged": again == after}
		var valid := true
		for value: bool in checks.values():
			valid = valid and value
		result["checks"] = checks
		result["status"] = "restored" if valid else "contract_failed"
		result["fadeReturn"] = {"status": "not_run", "reason": "this probe qualifies lazy creation and repeat only"}
		return result
	result["status"] = "no_unreified_placement"
	return result

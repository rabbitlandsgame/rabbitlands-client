class_name PreparedPlacements
extends RefCounted
const OptimizationProfile := preload("res://src/runtime/optimization_profile.gd")
## Optional prepared representation: a static MultiMesh draws every placement,
## with one original source per uniform batch and lazy leaf sources for fade or
## server binding. Native templates contain Resources and data, never live Nodes.
const POLICY := "lazy-source-v1"
const DATA := &"rl_prepared_placements_v1"
const REGISTRY := &"rl_prepared_placement_registry"
const BATCH := &"static_batch"
const BATCH_PATH := &"static_batch_path"
const BATCH_INDEX := &"static_batch_index"
const AUTHORED_ORDER := &"rl_prepared_authored_child_order"
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const SeasonSurfaces := preload("res://src/world/season_surfaces.gd")
static var _registry_mutex := Mutex.new()
static var _registry_roots: Dictionary = {}
static var _discovery_calls := 0
static var _discovery_fast_bypasses := 0
static var _discovery_nodes_visited := 0

class Handle extends RefCounted:
	var root_ref: WeakRef
	var node_ref: WeakRef
	var row: Dictionary
	var entry: Dictionary
	var manifest: WorldManifest
	var pinned := false
	var restores := 0
	var restore_usec := 0
	var maximum_restore_usec := 0
	var verification_usec := 0
	var maximum_verification_usec := 0
	var verification_rejections := 0
	var publication_rejections := 0
	var _restoring := false

	func root_node() -> Node3D:
		if OS.get_thread_caller_id() != OS.get_main_thread_id():
			return null
		var value: Variant = root_ref.get_ref() if root_ref != null else null
		if not is_instance_valid(value) or not value is Node3D:
			return null
		# Shared-budget retirement intentionally leaves roots attached for many
		# frames. An enclosing retired stream or teardown owner is also final.
		var owner: Node = value as Node3D
		while owner != null:
			if owner.is_queued_for_deletion() or owner.process_mode == Node.PROCESS_MODE_DISABLED:
				return null
			owner = owner.get_parent()
		return value as Node3D

	func node() -> MeshInstance3D:
		var value: Variant = node_ref.get_ref() if node_ref != null else null
		return value as MeshInstance3D if is_instance_valid(value) and not value.is_queued_for_deletion() else null

	func batch() -> MultiMeshInstance3D:
		var root := root_node()
		return root.get_node_or_null(NodePath(str(row.batch_path))) as MultiMeshInstance3D if root != null else null

	func mesh() -> Mesh:
		return row.get("mesh") as Mesh

	func global_placement() -> Transform3D:
		var root := root_node()
		return root.global_transform * (row.root_transform as Transform3D) if root != null else Transform3D.IDENTITY

	func relative_to(other: Node3D) -> Transform3D:
		return other.global_transform.affine_inverse() * global_placement()

	func _still_owned(root_weak: WeakRef, parent_weak: WeakRef, batch_weak: WeakRef,
			candidate_weak: WeakRef, expected_multi: MultiMesh, index: int) -> bool:
		var imported := root_node()
		var parent := parent_weak.get_ref() as Node3D
		var target := batch_weak.get_ref() as MultiMeshInstance3D
		var candidate := candidate_weak.get_ref() as MeshInstance3D
		return imported != null and imported == root_weak.get_ref() \
			and is_instance_valid(parent) and not parent.is_queued_for_deletion() \
			and imported.get_node_or_null(NodePath(str(row.parent_path))) == parent \
			and is_instance_valid(target) and not target.is_queued_for_deletion() and batch() == target \
			and target.multimesh == expected_multi and expected_multi != null \
			and index >= 0 and index < expected_multi.instance_count \
			and is_instance_valid(candidate) and not candidate.is_queued_for_deletion() \
			and candidate.get_parent() == parent and str(candidate.name) == str(row.name)

	func _abandon(candidate_weak: WeakRef, parent_weak: WeakRef, root_weak: WeakRef, began: int) -> void:
		publication_rejections += 1
		var elapsed := Time.get_ticks_usec() - began
		restore_usec += elapsed
		maximum_restore_usec = maxi(maximum_restore_usec, elapsed)
		var candidate := candidate_weak.get_ref() as Node
		var parent := parent_weak.get_ref() as Node
		var imported := root_weak.get_ref() as Node
		# Never free a foreign/reparented node, the root, its parent or batch.
		# A queued ancestor already owns cleanup of this unpublished candidate.
		if not is_instance_valid(candidate) or candidate.is_queued_for_deletion() \
				or not is_instance_valid(parent) or candidate.get_parent() != parent \
				or parent.is_queued_for_deletion() \
				or (is_instance_valid(imported) and imported.is_queued_for_deletion()):
			return
		candidate.queue_free()

	func restore(pin := false) -> MeshInstance3D:
		if OS.get_thread_caller_id() != OS.get_main_thread_id():
			return null
		if _restoring:
			return null
		_restoring = true
		var result := _restore(pin)
		_restoring = false
		return result

	func _restore(pin: bool) -> MeshInstance3D:
		if OS.get_thread_caller_id() != OS.get_main_thread_id():
			return null
		var root := root_node()
		if root == null:
			return null
		var existing := node()
		if existing != null:
			pinned = pinned or pin
			return existing
		var parent := root.get_node_or_null(NodePath(str(row.parent_path))) as Node3D
		var target_batch := batch()
		if parent == null or target_batch == null or target_batch.multimesh == null:
			return null
		var index := int(row.batch_index)
		if index < 0 or index >= target_batch.multimesh.instance_count:
			return null
		# A new unrelated child with this name is not ours to replace.
		if parent.get_node_or_null(NodePath(str(row.name))) != null:
			return null
		var began := Time.get_ticks_usec()
		var materialization_entry: Dictionary = entry
		if not entry.is_empty():
			# A new materialization must not turn an old active-root permit into
			# a fresh unverified payload read or mix catalog generations.
			if manifest == null or Prepared.entry_identity(entry) != str(entry.get("entry_id", "")):
				verification_rejections += 1
				return null
			var verification_began := Time.get_ticks_usec()
			var current := Prepared.acquire("world", manifest.source_path,
				str(entry.get("source_digest", "")),
				Vram.cache_token(manifest.data, manifest.glb_path().get_base_dir()))
			var verification_elapsed := Time.get_ticks_usec() - verification_began
			verification_usec += verification_elapsed
			maximum_verification_usec = maxi(maximum_verification_usec, verification_elapsed)
			if str(current.get("status", "")) != "hit" \
					or str(current.get("entry_id", "")) != str(entry.get("entry_id", "")):
				verification_rejections += 1
				return null
			materialization_entry = current.entry
		var candidate := Lifecycle.instantiate({"status": "hit", "resource": row.template, "entry": materialization_entry})
		if not candidate is MeshInstance3D:
			if candidate != null:
				candidate.free()
			return null
		var restored := candidate as MeshInstance3D
		restored.name = str(row.name)
		var root_weak: WeakRef = weakref(root)
		var parent_weak: WeakRef = weakref(parent)
		var batch_weak: WeakRef = weakref(target_batch)
		var candidate_weak: WeakRef = weakref(restored)
		var expected_multi := target_batch.multimesh
		parent.add_child(restored)
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		# Sparse restoration cannot use the old numeric child index: absent
		# siblings compress that index. Order against surviving/reified authored
		# siblings, keeping later runtime children after the authored sequence.
		var insertion := 0
		for sibling: Node in parent.get_children():
			if sibling == restored or not sibling.has_meta(AUTHORED_ORDER):
				continue
			if int(sibling.get_meta(AUTHORED_ORDER)) > int(row.child_index):
				insertion = sibling.get_index()
				break
			insertion = sibling.get_index() + 1
		parent.move_child(restored, mini(insertion, parent.get_child_count() - 1))
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		restored.owner = root
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		restored.set_meta(BATCH, target_batch)
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		restored.set_meta(BATCH_PATH, NodePath(str(row.batch_path)))
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		restored.set_meta(BATCH_INDEX, index)
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		restored.visible = false
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		# Original root coordinates preserve tint/seed/border classification.
		var region := LookGround.region_of(manifest) if manifest != null else ""
		LookFoliage.paint(root, region, [restored])
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		LookFoliage.keep_chroma(root, region, [restored])
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		SeasonSurfaces.apply(root, manifest, true, [restored])
		if not _still_owned(root_weak, parent_weak, batch_weak, candidate_weak, expected_multi, index):
			_abandon(candidate_weak, parent_weak, root_weak, began)
			return null
		node_ref = candidate_weak
		pinned = pinned or pin
		var elapsed := Time.get_ticks_usec() - began
		restores += 1
		restore_usec += elapsed
		maximum_restore_usec = maxi(maximum_restore_usec, elapsed)
		return restored

class Registry extends RefCounted:
	var handles: Array[Handle] = []
	var original_nodes := 0
	var retained_nodes := 0
	var original_visuals := 0
	var retained_visuals := 0

static func selected_policy() -> String:
	var policy := OptimizationProfile.selected("prepared_node_policy")
	return POLICY if policy == POLICY else "retain"

static func _counts(root: Node) -> Vector2i:
	var result := Vector2i(1, 1 if root is VisualInstance3D else 0)
	for child: Node in root.get_children():
		result += _counts(child)
	return result

static func _relative(node: Node3D, root: Node3D) -> Transform3D:
	var result := node.transform
	var parent := node.get_parent() as Node3D
	while parent != null and parent != root:
		result = parent.transform * result
		parent = parent.get_parent() as Node3D
	return result

static func _signature(node: MeshInstance3D, root: Node3D, region: String) -> String:
	if node.mesh == null or node.mesh.get_surface_count() != 1 or node.get_child_count() != 0 \
			or node.skin != null or not node.skeleton.is_empty() or node.visible \
			or node.material_override != null or node.material_overlay != null or node.get_script() != null \
			or node.unique_name_in_owner or not node.get_groups().is_empty():
		return ""
	for surface: int in node.get_surface_override_material_count():
		if node.get_surface_override_material(surface) != null:
			return ""
	var ancestor: Node = node
	while ancestor != null and ancestor != root:
		if not NightLamps.kind_of(str(ancestor.name)).is_empty() or ancestor.has_meta("stream_borders"):
			return ""
		ancestor = ancestor.get_parent()
	var name := str(node.name)
	# Ground and all declared collision/children stay as sparse real Nodes.
	if LookGround.kind_of(name) != LookGround.Kind.NONE or LookGround.is_kit_paving(name, region):
		return ""
	var material := node.mesh.surface_get_material(0) as BaseMaterial3D
	if material == null or material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
		return ""
	var words := LookFoliage.words_for(region)
	return "%d|%d|%s|%s" % [LookFoliage.kind_of(LookFoliage._plain_name(name), material, words),
		SeasonSurfaces.kind_of(SeasonSurfaces._label(node, root), material, region),
		str(LookFoliage.is_tree_wood(name)), str(LookFoliage._untamed(name, words))]

static func _claim(root: Node, owner: Node) -> void:
	for child: Node in root.get_children():
		child.owner = owner
		_claim(child, owner)

## Offline/main only. Reduces actual packed Nodes and renderer instances;
## no runtime claim is made from metadata alone. Mixed semantic batches stay.
static func cook_reduce(packed: PackedScene, manifest: WorldManifest, identity: String) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or packed == null \
			or not Lifecycle._data_only(packed, {}):
		return {}
	var root := packed.instantiate() as Node3D
	if root == null:
		return {}
	for node: Node in root.find_children("*", "", true, false):
		if node is AnimationPlayer or node is AnimationTree or node is Skeleton3D or node.get_script() != null:
			root.free()
			return {}
	var before := _counts(root)
	var region := LookGround.region_of(manifest) if manifest != null else ""
	var groups: Dictionary = {}
	var original_indices: Dictionary = {}
	var ordered_parents: Dictionary = {}
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		if not node.has_meta(BATCH_PATH):
			continue
		var path := str(node.get_meta(BATCH_PATH))
		if not groups.has(path):
			groups[path] = []
		(groups[path] as Array).append(node)
		original_indices[node.get_instance_id()] = node.get_index()
		var parent := node.get_parent()
		if not ordered_parents.has(parent.get_instance_id()):
			ordered_parents[parent.get_instance_id()] = true
			for sibling: Node in parent.get_children():
				sibling.set_meta(AUTHORED_ORDER, sibling.get_index())
	var rows: Array[Dictionary] = []
	var reduced_batches := 0
	for path: String in groups:
		var batch := root.get_node_or_null(NodePath(path)) as MultiMeshInstance3D
		var members: Array = groups[path]
		members.sort_custom(func(a: MeshInstance3D, b: MeshInstance3D) -> bool:
			return int(a.get_meta(BATCH_INDEX, -1)) < int(b.get_meta(BATCH_INDEX, -1)))
		if batch == null or batch.multimesh == null or members.size() < 2 \
				or members.size() != batch.multimesh.instance_count:
			continue
		var signature := _signature(members[0] as MeshInstance3D, root, region)
		var eligible := not signature.is_empty()
		var indices: Dictionary = {}
		for value: Variant in members:
			var member := value as MeshInstance3D
			var index := int(member.get_meta(BATCH_INDEX, -1))
			if _signature(member, root, region) != signature or member.mesh != batch.multimesh.mesh \
					or index < 0 or index >= batch.multimesh.instance_count or indices.has(index):
				eligible = false
			indices[index] = true
		if not eligible:
			continue
		# The original first member remains the batch's look/season representative.
		for ordinal: int in range(1, members.size()):
			var member := members[ordinal] as MeshInstance3D
			var original_path := str(root.get_path_to(member))
			var parent := member.get_parent()
			var template := PackedScene.new()
			# Object-valued runtime links must not enter native scene templates.
			if member.has_meta(BATCH):
				member.remove_meta(BATCH)
			# Runtime ownership leases deliberately outlive the VisualInstance
			# destructor. They are not authored data or portable template state.
			var member_ownership := Ownership.strip_runtime_metadata(member)
			var template_error := template.pack(member)
			Ownership.restore_runtime_metadata(member_ownership)
			if template_error != OK:
				root.free()
				return {}
			rows.append({"id": (identity + "\n" + original_path).sha256_text(),
				"name": str(member.name), "parent_path": str(root.get_path_to(parent)),
				"child_index": int(original_indices[member.get_instance_id()]), "root_transform": _relative(member, root),
				"batch_path": path, "batch_index": int(member.get_meta(BATCH_INDEX)),
				"mesh": member.mesh, "template": template})
			parent.remove_child(member)
			member.free()
		reduced_batches += 1
	var after := _counts(root)
	var stats := {"policy": POLICY, "removed_sources": rows.size(), "reduced_batches": reduced_batches,
		"nodes_before": before.x, "nodes_after": after.x,
		"visuals_before": before.y, "visuals_after": after.y}
	root.set_meta(DATA, {"rows": rows, "stats": stats})
	_claim(root, root)
	var result := PackedScene.new()
	var root_ownership := Ownership.strip_runtime_metadata(root)
	var error := result.pack(root)
	Ownership.restore_runtime_metadata(root_ownership)
	root.free()
	return {"scene": result, "stats": stats} if error == OK else {}

static func install(root: Node3D, manifest: WorldManifest, entry: Dictionary) -> void:
	if root == null:
		return
	if root.has_meta(REGISTRY):
		_remember_registry(root)
		return
	if not root.has_meta(DATA):
		return
	var data: Dictionary = root.get_meta(DATA)
	var registry := Registry.new()
	var stats: Dictionary = data.get("stats", {})
	registry.original_nodes = int(stats.get("nodes_before", 0))
	registry.retained_nodes = int(stats.get("nodes_after", 0))
	registry.original_visuals = int(stats.get("visuals_before", 0))
	registry.retained_visuals = int(stats.get("visuals_after", 0))
	for row: Dictionary in data.get("rows", []):
		var handle := Handle.new()
		handle.root_ref = weakref(root)
		handle.row = row
		handle.entry = entry
		handle.manifest = manifest
		registry.handles.append(handle)
	root.set_meta(REGISTRY, registry)
	_remember_registry(root)

static func _remember_registry(root: Node) -> void:
	var identity := root.get_instance_id()
	var reference: WeakRef = weakref(root)
	_registry_mutex.lock()
	_registry_roots[identity] = reference
	_registry_mutex.unlock()

static func _registries_possible() -> bool:
	_registry_mutex.lock()
	if _registry_roots.is_empty():
		_registry_mutex.unlock()
		return false
	var references := _registry_roots.duplicate()
	_registry_mutex.unlock()
	var possible := false
	var expired: Dictionary = {}
	for identity: int in references:
		var reference := references[identity] as WeakRef
		# Another owner may be building/freeing a detached registry root. A
		# live WeakRef is sufficient; never inspect that foreign Node here.
		if reference != null and reference.get_ref() != null:
			possible = true
		else:
			expired[identity] = reference
	if not expired.is_empty():
		_registry_mutex.lock()
		for identity: int in expired:
			if _registry_roots.get(identity) == expired[identity]:
				_registry_roots.erase(identity)
		_registry_mutex.unlock()
	return possible

static func _record_discovery(visited: int, bypassed: bool) -> void:
	_registry_mutex.lock()
	_discovery_calls += 1
	_discovery_nodes_visited += visited
	_discovery_fast_bypasses += 1 if bypassed else 0
	_registry_mutex.unlock()

## Plain aggregate counters: no tree walk, Resource ownership or expiry work.
static func discovery_snapshot() -> Dictionary:
	_registry_mutex.lock()
	var result := {"calls": _discovery_calls, "fast_bypasses": _discovery_fast_bypasses,
		"nodes_visited": _discovery_nodes_visited, "weak_registry_slots": _registry_roots.size()}
	_registry_mutex.unlock()
	return result

static func handles(root: Node) -> Array[Handle]:
	var result: Array[Handle] = []
	if root == null or root.is_queued_for_deletion():
		return result
	# Retained/live registries keep working even if the requested profile has
	# changed. A fresh raw session has none, so its discovery costs no tree walk.
	if root.has_meta(REGISTRY):
		_remember_registry(root)
	elif not _registries_possible():
		_record_discovery(0, true)
		return result
	var visited := _collect_handles(root, result)
	_record_discovery(visited, false)
	return result

static func _collect_handles(root: Node, result: Array[Handle]) -> int:
	if root.is_queued_for_deletion():
		return 0
	var visited := 1
	if root.has_meta(REGISTRY):
		var registry := root.get_meta(REGISTRY) as Registry
		if registry != null:
			result.append_array(registry.handles)
	for child: Node in root.get_children():
		visited += _collect_handles(child, result)
	return visited

static func restore_named(root: Node, names: Dictionary) -> void:
	# Restore matching leaves before the existing breadth-first lookup so name
	# precedence and current-map root scoping remain the consumer's policy.
	for handle: Handle in handles(root):
		var requested := names.has(str(handle.row.name))
		var imported := handle.root_node()
		var parent: Node = imported.get_node_or_null(NodePath(str(handle.row.parent_path))) if imported != null else null
		# Server bindings commonly name the retained placement wrapper. Its
		# descendant meshes must exist before bounds, picking or highlight scans.
		while not requested and parent != null and parent != root:
			requested = names.has(str(parent.name))
			parent = parent.get_parent()
		if requested:
			handle.restore(true)

static func snapshot(root: Node) -> Dictionary:
	var removed := 0
	var restored := 0
	var pinned := 0
	var total_usec := 0
	var maximum_usec := 0
	var verification_usec := 0
	var maximum_verification_usec := 0
	var verification_rejections := 0
	var publication_rejections := 0
	for handle: Handle in handles(root):
		removed += 1
		restored += 1 if handle.node() != null else 0
		pinned += 1 if handle.pinned else 0
		total_usec += handle.restore_usec
		maximum_usec = maxi(maximum_usec, handle.maximum_restore_usec)
		verification_usec += handle.verification_usec
		maximum_verification_usec = maxi(maximum_verification_usec, handle.maximum_verification_usec)
		verification_rejections += handle.verification_rejections
		publication_rejections += handle.publication_rejections
	return {"policy": POLICY, "initial_removed_sources": removed, "reified_sources": restored,
		"remaining_node_reduction": removed - restored, "remaining_visual_reduction": removed - restored,
		"pinned_interactives": pinned, "restore_total_us": total_usec, "restore_largest_atomic_us": maximum_usec,
		"verification_total_us": verification_usec, "verification_largest_atomic_us": maximum_verification_usec,
		"verification_rejections": verification_rejections, "verification_overlaps_restore": true,
		"publication_rejections": publication_rejections, "restore_time_includes_rejected_publication": true,
		"cost_kind": "observed_main_thread_restore_time", "qualification": "requires_exported_counts_and_parity"}

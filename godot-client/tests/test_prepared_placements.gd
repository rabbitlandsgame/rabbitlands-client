extends SceneTree
## Actual source removal, stable-root restore, material/season, batch, collision
## and geometric-fade parity. This fixture does not claim exported qualification.
const Placements := preload("res://src/world/prepared_placements.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")
const Fade := preload("res://src/world/occluder_fade.gd")
const Surfaces := preload("res://src/world/season_surfaces.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("prepared placements: " + message)

func _claim(node: Node, owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = owner
		_claim(child, owner)

func _relink(world: Node3D) -> void:
	var linker := WorldLoader.new()
	linker.world_root = world
	linker._resolve_batch_links()
	linker.world_root = null
	linker.free()

func _world() -> PackedScene:
	var world := Node3D.new()
	world.name = "Fixture"
	var material := StandardMaterial3D.new()
	material.resource_name = "leaf_atlas"
	var mesh := BoxMesh.new()
	mesh.size = Vector3(2, 3, 2)
	mesh.material = material
	var group := Node3D.new()
	group.name = "TranslatedGroup"
	group.transform = Transform3D(Basis(Vector3.UP, 0.4), Vector3(3, 0, 2))
	world.add_child(group)
	var batch := MultiMeshInstance3D.new()
	batch.name = "Batch"
	batch.multimesh = MultiMesh.new()
	batch.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	batch.multimesh.mesh = mesh
	batch.multimesh.instance_count = 6
	world.add_child(batch)
	for index: int in 6:
		var node := MeshInstance3D.new()
		node.name = "kit-oak-tree-%d" % index
		node.mesh = mesh
		node.position = Vector3(index * 4, 2, 0)
		node.visible = false
		node.set_meta(Placements.BATCH_PATH, NodePath("Batch"))
		node.set_meta(Placements.BATCH_INDEX, index)
		group.add_child(node)
		batch.multimesh.set_instance_transform(index, group.transform * node.transform)
		if index == 2:
			var retained := Node3D.new()
			retained.name = "RetainedBetweenSources"
			group.add_child(retained)
	# Sparse live collision and lamp nodes must survive; they are not a batch.
	var solid := MeshInstance3D.new()
	solid.name = "InteractiveSolid"
	solid.mesh = mesh
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	shape.shape = BoxShape3D.new()
	body.add_child(shape)
	solid.add_child(body)
	world.add_child(solid)
	var lamp := MeshInstance3D.new()
	lamp.name = "kit-lantern-post-1"
	lamp.mesh = mesh
	world.add_child(lamp)
	# A positive contaminated-input control proves the cooker strips both
	# full-root and removed-leaf template boundaries, not just pristine inputs.
	Ownership.attach(batch)
	for geometry: Node in world.find_children("*", "MeshInstance3D", true, false):
		Ownership.attach(geometry as GeometryInstance3D)
	_claim(world, world)
	var packed := PackedScene.new()
	_expect(packed.pack(world) == OK, "synthetic source packs")
	world.free()
	return packed

func _check_packed_ownership(source: PackedScene, reduced: PackedScene) -> void:
	var original := source.instantiate()
	_expect(original.get_node("Batch").has_meta(Ownership.META),
		"input control really carries runtime ownership metadata")
	original.free()
	var plain := reduced.instantiate()
	for geometry: Node in plain.find_children("*", "GeometryInstance3D", true, false):
		_expect(not geometry.has_meta(Ownership.META), "full packed scene excludes runtime ownership metadata")
	var data: Dictionary = plain.get_meta(Placements.DATA)
	for row: Dictionary in data.rows:
		var leaf := (row.template as PackedScene).instantiate()
		_expect(not leaf.has_meta(Ownership.META), "each sparse template excludes runtime ownership metadata")
		leaf.free()
	plain.free()

func _publication_child(child: Node, handle: Placements.Handle, root_weak: WeakRef,
		batch_weak: WeakRef, mode: int, observed: Dictionary) -> void:
	if str(child.name) != str(handle.row.name):
		return
	observed["calls"] += 1
	if mode == 0:
		(root_weak.get_ref() as Node).queue_free()
	elif mode == 1:
		(batch_weak.get_ref() as Node).free()
	elif mode == 2:
		child.queue_free()
	elif mode == 3:
		observed["nested"] += 1
		observed["nested_null"] = handle.restore(true) == null
	elif mode == 5:
		(child as Node3D).visible = true
		(child as Node3D).visibility_changed.connect(_publication_visibility.bind(root_weak, observed))

func _publication_visibility(root_weak: WeakRef, observed: Dictionary) -> void:
	observed["visibility_calls"] += 1
	var imported := root_weak.get_ref() as Node
	if is_instance_valid(imported):
		imported.queue_free()

func _publication_order(batch_weak: WeakRef, observed: Dictionary) -> void:
	observed["order_calls"] += 1
	# add_child emits the first change; move_child must trigger the second.
	if int(observed.order_calls) == 2:
		var batch := batch_weak.get_ref() as Node
		if is_instance_valid(batch):
			batch.free()

func _foreign_restore(handle: Placements.Handle) -> bool:
	return handle.restore(true) == null

func _foreign_thread_restore(scene: PackedScene, manifest: WorldManifest) -> void:
	var imported := Lifecycle.instantiate({"status": "hit", "resource": scene, "entry": {}})
	root.add_child(imported)
	Placements.install(imported, manifest, {})
	var handle: Placements.Handle = Placements.handles(imported)[0]
	var baseline := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var before := [handle._restoring, handle.pinned, handle.restores, handle.restore_usec,
		handle.maximum_restore_usec, handle.verification_rejections, handle.publication_rejections,
		handle.node_ref]
	var worker := Thread.new()
	var started := worker.start(_foreign_restore.bind(handle))
	_expect(started == OK, "foreign-thread restore control starts")
	if started == OK:
		_expect(bool(worker.wait_to_finish()), "foreign-thread restore rejects before accessing ownership state")
	_expect(before == [handle._restoring, handle.pinned, handle.restores, handle.restore_usec,
		handle.maximum_restore_usec, handle.verification_rejections, handle.publication_rejections,
		handle.node_ref] and int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == baseline,
		"foreign-thread restore leaves guard, pin, counters, reference and Node count unchanged")
	_expect(handle.restore(false) != null and handle.restores == 1 and not handle.pinned,
		"main-thread restore remains usable after rejected foreign-thread call")
	imported.free()

func _publication_callbacks(scene: PackedScene, manifest: WorldManifest) -> void:
	for mode: int in 6:
		var baseline := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
		var imported := Lifecycle.instantiate({"status": "hit", "resource": scene, "entry": {}})
		root.add_child(imported)
		Placements.install(imported, manifest, {})
		var handle: Placements.Handle = Placements.handles(imported)[0]
		var parent := imported.get_node(NodePath(str(handle.row.parent_path)))
		var root_weak: WeakRef = weakref(imported)
		var batch_weak: WeakRef = weakref(handle.batch())
		var observed := {"calls": 0, "nested": 0, "nested_null": false,
			"order_calls": 0, "visibility_calls": 0}
		parent.child_entered_tree.connect(_publication_child.bind(handle, root_weak, batch_weak, mode, observed))
		if mode == 4:
			parent.child_order_changed.connect(_publication_order.bind(batch_weak, observed))
		var restored := handle.restore(true)
		_expect(int(observed.calls) == 1, "real child_entered_tree callback executes once: %d" % mode)
		if mode == 3:
			_expect(int(observed.nested) == 1 and bool(observed.nested_null)
				and restored != null and handle.node() == restored and handle.restores == 1
				and handle.pinned and handle.publication_rejections == 0,
				"same-handle callback reentry creates no second candidate and outer commit succeeds once")
		else:
			_expect(restored == null and handle.node() == null and handle.restores == 0
				and not handle.pinned and handle.publication_rejections == 1,
				"callback invalidation never commits a stale source/ref/promotion: %d" % mode)
			if mode in [1, 4]:
				_expect(is_instance_valid(imported) and not imported.is_queued_for_deletion(),
					"failed publication never frees the surviving root owned by another consumer")
			if mode == 4:
				_expect(int(observed.order_calls) >= 2, "real move_child callback boundary is exercised")
			if mode == 5:
				_expect(int(observed.visibility_calls) == 1, "real mutable visibility callback boundary is exercised")
		await process_frame
		await process_frame
		if is_instance_valid(imported):
			imported.free()
		await process_frame
		_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == baseline,
			"callback case leaves no orphan candidate Nodes after owned cleanup: %d" % mode)

func _expect_autoloads() -> bool:
	var ready := root.has_node("Network") and root.has_node("AppState")
	_expect(ready, "deferred fixture starts after Network and AppState registration")
	return ready

func _raw_discovery_bypass(label: String) -> void:
	var raw := Node3D.new()
	for _branch: int in 64:
		var branch := Node3D.new()
		raw.add_child(branch)
		for _leaf: int in 4:
			branch.add_child(Node3D.new())
	var before := Placements.discovery_snapshot()
	_expect(Placements.handles(raw).is_empty(), label + ": raw tree has no placement handles")
	Placements.restore_named(raw, {"never-present": true})
	var after := Placements.discovery_snapshot()
	_expect(int(after.calls) == int(before.calls) + 2
		and int(after.fast_bypasses) == int(before.fast_bypasses) + 2
		and int(after.nodes_visited) == int(before.nodes_visited),
		label + ": neither direct discovery nor named binding visits the 320 descendants")
	raw.free()

func _legacy_registry_discovery(scene: PackedScene, manifest: WorldManifest) -> void:
	var names: Array[String] = ["RABBITLANDS_OPTIMIZATION_PROFILE", "RABBITLANDS_PREPARED_CONTENT",
		"RABBITLANDS_PREPARED_NODE_POLICY"]
	var saved: Dictionary = {}
	for name: String in names:
		saved[name] = {"present": OS.has_environment(name), "value": OS.get_environment(name)}
	OS.set_environment(names[0], "legacy")
	OS.set_environment(names[1], "raw")
	OS.set_environment(names[2], "retain")
	var wrapper := Node3D.new()
	root.add_child(wrapper)
	var imported := Lifecycle.instantiate({"status": "hit", "resource": scene, "entry": {}})
	wrapper.add_child(imported)
	_relink(imported)
	Placements.install(imported, manifest, {})
	var before := Placements.discovery_snapshot()
	var handles := Placements.handles(wrapper)
	var after := Placements.discovery_snapshot()
	_expect(Placements.selected_policy() == "retain" and Placements.Prepared.selected_mode() == "raw",
		"installed-registry control explicitly requests legacy/raw/retain")
	_expect(handles.size() == 5 and int(after.nodes_visited) > int(before.nodes_visited),
		"nested installed registries keep their original traversal under legacy/raw/retain")
	if not handles.is_empty():
		Surfaces.set_season({"index": 3})
		Surfaces.apply(imported, manifest, true)
		Placements.restore_named(wrapper, {str(handles[0].row.name): true})
		var restored: MeshInstance3D = handles[0].node()
		_expect(restored != null and handles[0].pinned and restored.get_active_material(0).has_meta(Surfaces.META),
			"profile changes do not strand installed handles or skip deferred season/material binding")
		Surfaces.set_season({})
	var reference: WeakRef = weakref(imported)
	wrapper.free()
	_expect(reference.get_ref() == null, "weak registry index does not pin installed roots")
	for name: String in names:
		if bool(saved[name].present):
			OS.set_environment(name, str(saved[name].value))
		else:
			OS.unset_environment(name)
	_raw_discovery_bypass("After installed-root release")
	# A direct caller may carry existing runtime metadata from before the
	# index was populated. It must remain discoverable without a policy gate.
	var direct := Node3D.new()
	var registry := Placements.Registry.new()
	var direct_handle := Placements.Handle.new()
	registry.handles.append(direct_handle)
	direct.set_meta(Placements.REGISTRY, registry)
	_expect(Placements.handles(direct) == [direct_handle], "direct-root registry metadata remains discoverable")
	direct.free()
	_raw_discovery_bypass("After direct metadata-root release")

func _run() -> void:
	# A SceneTree --script is parsed before autoload singleton registration.
	# Main must compile only after deferred startup; these checks use its real
	# static lookup without constructing another Main or replacing its script.
	if not _expect_autoloads():
		quit(1)
		return
	var main_script: Script = load("res://src/app/main.gd")
	var old_look := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	_raw_discovery_bypass("Fresh legacy/raw process")
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "amberwood__chunk_fixture"}, "continentGeography": {},
		"environment": {"sun": {"enabled": true}}}
	var source := _world()
	var reduced := Placements.cook_reduce(source, manifest, "user://prepared-fixture/source")
	_expect(not reduced.is_empty(), "eligible uniform batch reduces")
	if reduced.is_empty():
		quit(1)
		return
	_check_packed_ownership(source, reduced.scene as PackedScene)
	_legacy_registry_discovery(reduced.scene as PackedScene, manifest)
	_foreign_thread_restore(reduced.scene as PackedScene, manifest)
	await _publication_callbacks(reduced.scene as PackedScene, manifest)
	var stats: Dictionary = reduced.stats
	_expect(int(stats.removed_sources) == 5 and int(stats.nodes_before) - int(stats.nodes_after) == 5,
		"five actual packed source Nodes removed")
	_expect(int(stats.visuals_before) - int(stats.visuals_after) == 5,
		"five actual VisualInstances removed")
	var a := Lifecycle.instantiate({"status": "hit", "resource": reduced.scene, "entry": {}})
	var b := Lifecycle.instantiate({"status": "hit", "resource": reduced.scene, "entry": {}})
	root.add_child(a)
	root.add_child(b)
	_relink(a)
	_relink(b)
	a.transform = Transform3D(Basis(Vector3.UP, 0.7), Vector3(100, 0, -40))
	b.transform = Transform3D(Basis(Vector3.UP, -0.2), Vector3(-100, 0, 30))
	Placements.install(a, manifest, {})
	Placements.install(b, manifest, {})
	var handles := Placements.handles(a)
	var other := Placements.handles(b)
	_expect(handles.size() == 5 and other.size() == 5, "independent root registries")
	_expect(a.find_children("*", "CollisionShape3D", true, false).size() == 1
		and a.get_node_or_null("kit-lantern-post-1") != null, "collision and lamp Nodes retained")
	var abatch := a.get_node("Batch") as MultiMeshInstance3D
	var bbatch := b.get_node("Batch") as MultiMeshInstance3D
	_expect(abatch.multimesh != bbatch.multimesh, "batch transform buffers remain private")
	# Retiring roots stay attached and are not yet queued. Neither their
	# direct handles nor a child of a disabled retiring owner may reify Nodes.
	var retirement_owner := Node3D.new()
	root.add_child(retirement_owner)
	var retiring := Lifecycle.instantiate({"status": "hit", "resource": reduced.scene, "entry": {}})
	retirement_owner.add_child(retiring)
	Placements.install(retiring, manifest, {})
	var retiring_handle: Placements.Handle = Placements.handles(retiring)[0]
	var retired_count := Placements._counts(retiring)
	retiring.process_mode = Node.PROCESS_MODE_DISABLED
	retiring.visible = false
	_expect(retiring.is_inside_tree() and not retiring.is_queued_for_deletion()
		and retiring_handle.restore() == null and Placements._counts(retiring) == retired_count,
		"attached shared-budget retired root cannot reify before its eventual queued/free state")
	retiring.process_mode = Node.PROCESS_MODE_INHERIT
	retirement_owner.process_mode = Node.PROCESS_MODE_DISABLED
	_expect(retiring_handle.restore() == null and Placements._counts(retiring) == retired_count,
		"disabled enclosing retirement owner also blocks child-source resurrection")
	retirement_owner.free()
	# Production entries cannot authorize a new payload read from stale metadata.
	handles[4].entry = {"source_digest": "0".repeat(64), "entry_id": "never-verified"}
	_expect(handles[4].restore() == null and handles[4].node() == null
		and handles[4].verification_rejections == 1, "unverified active-root metadata cannot authorize late materialization")
	handles[4].entry = {}
	var before_transform := abatch.multimesh.get_instance_transform(int(handles[0].row.batch_index))
	var fade := Fade.new()
	var index_count := fade.configure(manifest, a)
	_expect(index_count == 8, "all six tree placements plus two sparse sources keep fade registrations")
	var handle := handles[0]
	var registered: Variant = null
	for occluder: Variant in fade._occluders:
		if occluder.placement == handle:
			registered = occluder
	_expect(registered != null, "removed source is geometrically registered without restoration")
	if registered != null:
		var world_centre := handle.global_placement().origin
		_expect(Fade._segment_hits_box(registered.box,
			handle.global_placement().affine_inverse() * (world_centre + Vector3(0, 0, -5)),
			handle.global_placement().affine_inverse() * (world_centre + Vector3(0, 0, 5))),
			"translated rotated placement retains local geometric intersection")
		registered.apply()
		_expect(handle.node() != null and registered.applied, "first fade recreates only its leaf source")
		registered.restore()
		_expect(abatch.multimesh.get_instance_transform(int(handle.row.batch_index)).is_equal_approx(before_transform),
			"fade restores exact batch transform")
	_expect(Placements.snapshot(a).remaining_node_reduction == 4, "live actual reduction falls honestly after restoration")
	_expect(Placements.snapshot(b).remaining_node_reduction == 5, "same IDs in another root remain independent")
	var target := handles[2]
	Surfaces.set_season({"index": 3})
	Surfaces.apply(a, manifest, true)
	var stamp: Variant = a.get_meta(Surfaces.STAMP_META)
	var restored := target.restore(true)
	_expect(restored != null and restored.get_active_material(0).has_meta(Surfaces.META),
		"late source receives the current season")
	_expect(a.get_meta(Surfaces.STAMP_META) == stamp, "partial season binding does not replace full-root stamp")
	_expect(target.restore() == restored and target.restores == 1, "repeated restore preserves single ownership")
	var lookup: Dictionary = main_script.call("_named_nodes", a, {str(handles[3].row.name): true})
	_expect(lookup.get(str(handles[3].row.name)) == handles[3].node() and handles[3].pinned,
		"real Main named lookup promotes and pins the correct root-scoped placement")
	_expect(other[3].node() == null, "repeated source name in another root is untouched")
	# Rebuild in reverse order around a retained authored sibling. Numeric old
	# indices alone append late sources on the wrong side of sparse siblings.
	for index: int in range(handles.size() - 1, -1, -1):
		handles[index].restore()
	var reference := source.instantiate()
	var expected_order: Array[String] = []
	var actual_order: Array[String] = []
	for child: Node in reference.get_node("TranslatedGroup").get_children():
		expected_order.append(str(child.name))
	for child: Node in a.get_node("TranslatedGroup").get_children():
		actual_order.append(str(child.name))
	_expect(actual_order == expected_order, "reverse sparse restoration preserves exact authored sibling order")
	reference.free()
	var wrapper_lookup: Dictionary = main_script.call("_named_nodes", b, {"TranslatedGroup": true})
	_expect(wrapper_lookup.get("TranslatedGroup") == b.get_node("TranslatedGroup")
		and b.get_node("TranslatedGroup").find_children("*", "MeshInstance3D", true, false).size() == 6,
		"binding a retained wrapper restores its descendant source meshes before bounds/picking scans")
	fade.reset()
	a.queue_free()
	_expect(handles[4].restore() == null, "queued retiring root cannot resurrect a source")
	await process_frame
	_expect(handles[4].restore() == null, "freed root cannot resurrect a source")
	b.free()
	Surfaces.set_season({})
	if old_look.is_empty():
		OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	else:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, old_look)
	await process_frame
	print("prepared placement tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

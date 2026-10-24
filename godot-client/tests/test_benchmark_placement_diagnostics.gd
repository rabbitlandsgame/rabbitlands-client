extends SceneTree
const Diagnostics := preload("res://tests/integration/benchmark_placement_diagnostics.gd")
const Placements := preload("res://src/world/prepared_placements.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
var failures := 0
func _init() -> void:
	_run.call_deferred()
func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)
func _run() -> void:
	var manifest := WorldManifest.new()
	manifest.source_path = "user://placement-fixture/world.json"
	manifest.data = {"asset": {"id": "amberwood__chunk_fixture"}, "environment": {"sun": {"enabled": true}}}
	var source := Node3D.new()
	source.name = "Fixture"
	var material := StandardMaterial3D.new()
	material.resource_name = "leaf_atlas"
	var mesh := BoxMesh.new()
	mesh.material = material
	var batch := MultiMeshInstance3D.new()
	batch.name = "Batch"
	batch.multimesh = MultiMesh.new()
	batch.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	batch.multimesh.mesh = mesh
	batch.multimesh.instance_count = 3
	source.add_child(batch)
	batch.owner = source
	for index: int in 3:
		var leaf := MeshInstance3D.new()
		leaf.name = "kit-oak-tree-%d" % index
		leaf.mesh = mesh
		leaf.visible = false
		leaf.set_meta(Placements.BATCH_PATH, NodePath("Batch"))
		leaf.set_meta(Placements.BATCH_INDEX, index)
		source.add_child(leaf)
		leaf.owner = source
		batch.multimesh.set_instance_transform(index, Transform3D.IDENTITY)
	var packed := PackedScene.new()
	_expect(packed.pack(source) == OK, "actual synthetic source packs")
	source.free()
	var reduced := Placements.cook_reduce(packed, manifest, "user://placement-fixture/source")
	_expect(not reduced.is_empty(), "synthetic placement batch really reduces")
	if reduced.is_empty():
		quit(1)
		return
	var imported := Lifecycle.instantiate({"status": "hit", "resource": reduced.scene, "entry": {}}) as Node3D
	var stream := ContinentChunkStream.new()
	root.add_child(stream)
	stream.add_child(imported)
	Placements.install(imported, manifest, {})
	stream.cells["02_07"] = {"root": imported, "manifest": manifest, "entry": {"id": "02_07"}}
	var loader := WorldLoader.new()
	loader.world_root = stream
	loader.manifest = manifest
	var exterior := ExteriorRegionStream.new()
	# Deliberately duplicate the active owned root in the exterior inventory.
	exterior.residents["four_gates"] = {"root": stream, "manifest": manifest}
	var first := Diagnostics.capture(loader, exterior, "four_gates", true)
	_expect(first.roots.size() == 1, "active/resident references deduplicate actual roots")
	var before: Dictionary = first.roots[0]
	_expect(before.chunkId == "02_07" and before.worldSource == manifest.source_path,
		"chunk and source identities survive capture")
	_expect(before.placements.initial_removed_sources == 2 and before.placements.reified_sources == 0,
		"passive capture does not restore a source")
	var rejected := Diagnostics.restore_one(loader, exterior, "four_gates", "four_gates", "02_07", false)
	_expect(rejected.status == "not_ready", "functional restore rejects non-ready boundary")
	var probe := Diagnostics.restore_one(loader, exterior, "four_gates", "four_gates", "02_07", true)
	_expect(probe.status == "restored" and probe.repeatSameNode, "explicit owned restore and repeat succeed")
	_expect(probe.afterRestore.counts.nodes == probe.before.counts.nodes + 1
		and probe.afterRestore.counts.visualInstances == probe.before.counts.visualInstances + 1,
		"actual Node and renderer instance counts increase by one")
	_expect(probe.afterRestore.placements.reified_sources == 1
		and probe.afterRestore.placements.remaining_node_reduction == 1
		and probe.afterRestore.placements.pinned_interactives == 0,
		"one unpinned source restores with consistent remaining count")
	_expect(probe.afterRepeat == probe.afterRestore, "repeat is idempotent including counters")
	var final := Diagnostics.capture(loader, exterior, "four_gates", true)
	_expect(final.roots[0].counts == probe.afterRestore.counts, "passive final census remains unchanged")
	exterior.residents.clear()
	exterior.free()
	loader.world_root = null
	loader.free()
	stream.cells.clear()
	stream.free()
	await physics_frame
	await process_frame
	await process_frame
	print("benchmark placement diagnostics failures=", failures)
	quit(1 if failures else 0)

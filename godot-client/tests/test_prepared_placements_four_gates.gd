extends SceneTree
## Root-only real-source qualification: actual Node/Visual counts must fall.
## Run with a fresh isolated user profile/cache and --prepared-content=raw.
const Placements := preload("res://src/world/prepared_placements.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Fade := preload("res://src/world/occluder_fade.gd")
const SOURCE := "res://../eloria-assets/maps/four-gates/chunks/02_07/world.json"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("Four Gates prepared placements: " + message)

func _link(world: Node3D) -> void:
	var linker := WorldLoader.new()
	linker.world_root = world
	linker._resolve_batch_links()
	linker.world_root = null
	linker.free()

func _run() -> void:
	# Main depends on autoload names registered after --script parsing.
	var main_script: Script = load("res://src/app/main.gd")
	_expect(Prepared.selected_mode() == "raw", "fresh raw reference required")
	var loader := WorldLoader.new()
	root.add_child(loader)
	loader.load_world(SOURCE)
	_expect(loader.world_root != null and loader.cache_status == &"miss"
		and not loader._cache_nodes.is_empty(), "real source cold pristine snapshot exists")
	if loader.world_root == null or loader._cache_nodes.is_empty():
		loader.free()
		quit(1)
		return
	var manifest := loader.manifest
	var restore := loader._restore_pristine()
	for node: Node in loader._cache_nodes:
		if is_instance_valid(node):
			if node.has_meta(WorldLoader.BATCH_META):
				node.remove_meta(WorldLoader.BATCH_META)
			node.owner = loader.world_root
	var source := PackedScene.new()
	_expect(source.pack(loader.world_root) == OK, "real pristine reference packs")
	loader._undo_pristine(restore)
	loader._release_snapshot()
	loader.free()
	var reduced := Placements.cook_reduce(source, manifest, SOURCE)
	_expect(not reduced.is_empty(), "real Four Gates source is reducible")
	if reduced.is_empty():
		quit(1)
		return
	var stats: Dictionary = reduced.stats
	_expect(int(stats.removed_sources) > 0 and int(stats.nodes_after) < int(stats.nodes_before)
		and int(stats.visuals_after) < int(stats.visuals_before), "actual Node and renderer-instance counts fall")
	var reference := Lifecycle.instantiate({"status": "hit", "resource": source, "entry": {}})
	var candidate := Lifecycle.instantiate({"status": "hit", "resource": reduced.scene, "entry": {}})
	root.add_child(reference)
	root.add_child(candidate)
	_link(reference)
	_link(candidate)
	Placements.install(candidate, manifest, {})
	_expect(Placements._counts(reference).x - Placements._counts(candidate).x == int(stats.removed_sources),
		"live Node census confirms packed reduction")
	_expect(reference.find_children("*", "CollisionShape3D", true, false).size()
		== candidate.find_children("*", "CollisionShape3D", true, false).size(), "all collision shapes retained")
	for handle: Placements.Handle in Placements.handles(candidate):
		var path := NodePath(str(handle.row.parent_path) + "/" + str(handle.row.name))
		var original := reference.get_node_or_null(path) as MeshInstance3D
		_expect(original != null, "stable source path resolves in raw reference")
		if original != null:
			_expect(Placements._relative(original, reference).is_equal_approx(handle.row.root_transform),
				"removed transform exactly matches raw source")
		var batch := handle.batch()
		var reference_batch := reference.get_node_or_null(NodePath(str(handle.row.batch_path))) as MultiMeshInstance3D
		_expect(batch != null and reference_batch != null
			and batch.multimesh.get_instance_transform(int(handle.row.batch_index)).is_equal_approx(
				reference_batch.multimesh.get_instance_transform(int(handle.row.batch_index))),
			"batch instance transform is unchanged")
	var original_fade := Fade.new()
	var reduced_fade := Fade.new()
	_expect(original_fade.configure(manifest, reference) == reduced_fade.configure(manifest, candidate),
		"real Four Gates retained sources and sparse handles preserve geometric fade registrations")
	for collision: Node in reference.find_children("*", "CollisionShape3D", true, false):
		var path := reference.get_path_to(collision)
		var retained := candidate.get_node_or_null(path) as CollisionShape3D
		var body := collision.get_parent() as CollisionObject3D
		var retained_body := retained.get_parent() as CollisionObject3D if retained != null else null
		_expect(retained != null and retained.shape == (collision as CollisionShape3D).shape
			and retained_body != null and body != null and retained_body.collision_layer == body.collision_layer
			and retained_body.collision_mask == body.collision_mask,
			"real collision shape identity/layers/masks survive source removal: " + str(path))
	var sparse: Array[Placements.Handle] = Placements.handles(candidate)
	if not sparse.is_empty():
		var chosen := sparse[0]
		var named: Dictionary = main_script.call("_named_nodes", candidate, {str(chosen.row.name): true})
		var raw_named: Dictionary = main_script.call("_named_nodes", reference, {str(chosen.row.name): true})
		var restored := chosen.node()
		var bound := named.get(str(chosen.row.name)) as Node
		var raw_bound := raw_named.get(str(chosen.row.name)) as Node
		_expect(restored != null and chosen.pinned and bound != null and raw_bound != null
			and candidate.get_path_to(bound) == reference.get_path_to(raw_bound),
			"real Main named binding reifies sources and retains raw breadth-first name precedence")
		if restored != null:
			_expect(Placements._relative(restored, candidate).is_equal_approx(chosen.row.root_transform),
				"actual bound source retains its exact root-frame transform")
		var reified := int(Placements.snapshot(candidate).reified_sources)
		_expect(reified > 0 and Placements._counts(reference).x - Placements._counts(candidate).x == int(stats.removed_sources) - reified,
			"actual live Node census deducts every matching source restored by first binding")
	original_fade.reset()
	reduced_fade.reset()
	print("Four Gates prepared source census: ", JSON.stringify(stats))
	print("Four Gates live reduction: ", JSON.stringify(Placements.snapshot(candidate)))
	# Root owns serial runtime. This source fixture is not exported texture,
	# season/night/picking or timing qualification; those remain separate gates.
	reference.free()
	candidate.free()
	await process_frame
	print("Four Gates prepared placement tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

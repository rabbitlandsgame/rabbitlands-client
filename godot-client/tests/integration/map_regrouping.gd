extends SceneTree
## The regrouped tree draws what the package drew.
##
## `WorldLoader` buckets an over-wide sibling list under empty grouping nodes
## before Godot builds the scene, because Godot's builder is quadratic in the
## width of a sibling list and the regions are built wide - it is 3.4 s of
## Amberwood's 4.7 and 6.1 s of Verdant Stair's 7.9. The nodes move down a
## level; nothing else about them may change.
##
## This loads a real package through the production loader and rebuilds the
## same package the way the package itself is shaped, straight through
## `GLTFDocument`, then compares the two: every mesh instance by name, mesh,
## surface count and world placement, and the meshes they share. A grouping
## node carries an identity transform, so a difference here is a difference on
## screen.
##
##     Godot --headless --path . --script res://tests/integration/map_regrouping.gd
##
## Environment:
##   ELORIA_REGROUP_MAPS  comma list of registry ids (default four_gates,sunmane_steppe)

const REGISTRY := "res://data/maps/registry.json"

## Two packages with different shapes: Four Gates hangs 1 276 nodes off a node
## inside the scene, Sunmane Steppe hangs 1 106 off the scene root itself, and
## the root list is bucketed by a different branch of the pass.
const DEFAULT_MAPS := "four_gates,sunmane_steppe"

var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.low_processor_usage_mode_sleep_usec = 1
	Engine.max_fps = 0
	# This is a test of what happens before Godot builds the scene, so it has
	# to be the package that builds it. A cached region would pass every
	# assertion below - the groups are in the cached tree too - while proving
	# nothing about the pass that put them there.
	OS.set_environment(MapSceneCache.DISABLE_ENVIRONMENT, "1")
	var registry: Dictionary = _json(REGISTRY).get("maps", {}) as Dictionary
	var stage := Node3D.new()
	root.add_child(stage)
	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	stage.add_child(loader)
	await process_frame

	var requested: String = OS.get_environment("ELORIA_REGROUP_MAPS")
	if requested.strip_edges().is_empty():
		requested = DEFAULT_MAPS
	for identifier: String in requested.split(",", false):
		await _check_map(loader, registry, identifier.strip_edges())

	loader.unload_world()
	stage.queue_free()
	await process_frame
	print("map regrouping: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _check_map(loader: WorldLoader, registry: Dictionary, identifier: String) -> void:
	var entry: Dictionary = MapRegistry.resolve(registry, identifier)
	if not _expect(not entry.is_empty(), identifier + " resolves in the map registry"):
		return
	var manifest_path: String = ProjectSettings.globalize_path(
		str(entry.get("manifest", "")))
	var manifest: WorldManifest = WorldManifest.load_file(manifest_path)
	if not _expect(manifest.is_valid(), identifier + " has a valid manifest"):
		return

	# The package as it is shipped, built the way Godot would build it with no
	# help from the loader. This is the picture the regrouped tree has to match.
	var reference: Node3D = _generate_reference(manifest.glb_path())
	if not _expect(reference != null, identifier + ": the package builds on its own"):
		return
	root.add_child(reference)
	await process_frame
	var shipped_widest: int = _widest(reference)
	var shipped: Dictionary = _mesh_placements(reference)
	reference.queue_free()
	await process_frame

	loader.load_world(manifest_path)
	var deadline: int = Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(loader.world_root != null, identifier + " loads"):
		return
	var loaded: Dictionary = _mesh_placements(loader.world_root)
	var loaded_widest: int = _widest(loader.world_root)
	var groups: int = 0
	var shaped: int = 0
	for node: Node in loader.world_root.find_children("*", "Node3D", true, false):
		if not node.name.begins_with(WorldLoader.GROUP_NAME_PREFIX):
			continue
		groups += 1
		var group: Node3D = node as Node3D
		if group.get_class() == "Node3D" and group.visible \
				and group.transform.is_equal_approx(Transform3D.IDENTITY):
			shaped += 1
	_expect(groups > 0 and shaped == groups,
		"%s: all %d grouping nodes are visible empty identity transforms (%d)" % [
			identifier, groups, shaped])

	# The test is only worth running on a package the pass actually touches.
	_expect(shipped_widest > WorldLoader.MAX_SIBLINGS,
		"%s: the package is wide enough to exercise the pass (%d siblings)" % [
			identifier, shipped_widest])
	_expect(groups > 0, identifier + ": the loader added grouping nodes")
	_expect(loaded_widest <= WorldLoader.MAX_SIBLINGS,
		"%s: no sibling list survives wider than the limit (%d)" % [
			identifier, loaded_widest])

	# And the picture is the same one.
	_expect(int(loaded["count"]) == int(shipped["count"]),
		"%s: the same %d mesh instances are in the tree (%d)" % [
			identifier, int(shipped["count"]), int(loaded["count"])])
	_expect(int(loaded["meshes"]) == int(shipped["meshes"]),
		"%s: the same %d meshes are shared between them (%d)" % [
			identifier, int(shipped["meshes"]), int(loaded["meshes"])])
	var differences: PackedStringArray = _differences(
		shipped["placements"] as Dictionary, loaded["placements"] as Dictionary)
	_expect(differences.is_empty(),
		"%s: every mesh instance keeps its name, mesh and world placement to the last bit%s" % [
			identifier, "" if differences.is_empty()
			else " (" + ", ".join(differences) + ")"])
	loader.unload_world()
	await process_frame

## The package built straight through GLTFDocument, with the mip chains the
## loader rebuilds but none of its other passes and no regrouping.
func _generate_reference(glb_path: String) -> Node3D:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(glb_path, state) != OK:
		return null
	return document.generate_scene(state) as Node3D

## Every mesh instance in `world`, keyed by name, as the mesh it draws and
## where it draws it. Batched instances are hidden by the loader and their
## geometry moves to a MultiMeshInstance3D at the same transforms, so
## visibility is deliberately not part of the key: the batching pass is guarded
## by its own tests, and this one is about the tree the parser built.
##
## The transform is held as a `Transform3D` and compared with `==`, which is
## exact float equality rather than a tolerance. It can be, because a grouping
## node's transform is exactly the identity and multiplying by it changes no
## bit: every component of the child's world transform is a sum of the same
## products with the same zeroes. A tolerance here would hide the one thing
## worth knowing.
func _mesh_placements(world: Node3D) -> Dictionary:
	var placements: Dictionary = {}
	var meshes: Dictionary = {}
	var count := 0
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		count += 1
		if mesh_instance.mesh != null:
			meshes[mesh_instance.mesh.get_instance_id()] = true
		placements[mesh_instance.name] = [
			"" if mesh_instance.mesh == null else mesh_instance.mesh.resource_name,
			0 if mesh_instance.mesh == null else mesh_instance.mesh.get_surface_count(),
			mesh_instance.global_transform, mesh_instance.layers,
			mesh_instance.cast_shadow]
	return {"placements": placements, "meshes": meshes.size(), "count": count}

## The first few names that disagree, so a failure says which prop moved.
func _differences(shipped: Dictionary, loaded: Dictionary) -> PackedStringArray:
	var out := PackedStringArray()
	for key: Variant in shipped:
		if out.size() >= 5:
			break
		if not loaded.has(key):
			out.append(str(key) + " missing")
		elif loaded[key] != shipped[key]:
			out.append(str(key) + " moved")
	for key: Variant in loaded:
		if out.size() >= 5:
			break
		if not shipped.has(key):
			out.append(str(key) + " unexpected")
	return out

func _widest(node: Node) -> int:
	var widest: int = node.get_child_count()
	for child: Node in node.get_children():
		widest = maxi(widest, _widest(child))
	return widest

func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed as Dictionary if parsed is Dictionary else {}

func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("ok   ", message)
	else:
		printerr("FAIL ", message)
		_failures += 1
	return condition

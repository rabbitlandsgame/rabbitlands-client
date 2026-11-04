extends SceneTree

## Size-class static batch cells (wave 2 WD-C2).
##
## On the continent and in gauntlets `WorldLoader._batch_static_instances`
## splits each batch it makes into WorldDistanceClasses cells (32/48/64/96 m by
## the instance's mesh-box radius times its scale), stands each batch at its members' centre
## and holds their transforms relative to that. Which instances batch at all is
## still the legacy rule (four of one mesh in one 180 m cell): a split never
## turns a member back into a loose node and never batches a loose one. Other
## maps keep the legacy batches exactly.
##
## Checked here on hand-built worlds: the class table, the partition, batch
## counts and names, class meta, centred frames, relative instance transforms
## (where the rendering server keeps them), the member links, membership equal
## to the legacy rule, the manifest cell cap, a detached (off-tree) build, a
## PackedScene round trip with `_resolve_batch_links`, and OccluderFade lifting
## a member out of a centred batch and handing it back.
##
## Run: Godot_v4.7.2-stable_win64.exe --headless --path . \
##         --script tests/test_static_batch_cells.gd

const Classes := preload("res://src/world/world_distance_classes.gd")
const OccluderFadeScript := preload("res://src/world/occluder_fade.gd")
const SCRATCH := "user://static-batch-cells-test"
const CONTINENT := {"continentGeography": {"geometryMode": "continent-chunks-v1"}}
const GAUNTLET := {"gauntlet": {"id": "test"}}
const SETTLE := 0.5

var failures := 0
var _stores_transforms := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_stores_transforms = _multimesh_stores_transforms()
	print("static batch cells: multimesh transforms readable = ", _stores_transforms)
	_check_table()
	_check_partition()
	_check_scope()
	await _check_continent_cells()
	await _check_legacy_maps_unchanged()
	await _check_mixed_classes_stay_batched()
	await _check_loose_stays_loose()
	await _check_manifest_cap()
	_check_detached_build()
	await _check_round_trip()
	await _check_occluder_fade()
	_remove_tree(SCRATCH)
	print("static batch cells tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --------------------------------------------------------------------------
# The table and the pure helpers
# --------------------------------------------------------------------------

func _check_table() -> void:
	_expect(Classes.size_class(0.0) == "S" and Classes.size_class(1.49) == "S",
		"under 1.5 m is S")
	_expect(Classes.size_class(1.5) == "M" and Classes.size_class(3.99) == "M",
		"1.5-4 m is M")
	_expect(Classes.size_class(4.0) == "L" and Classes.size_class(9.99) == "L",
		"4-10 m is L")
	_expect(Classes.size_class(10.0) == "XL" and Classes.size_class(400.0) == "XL",
		"10 m and over is XL")
	_expect(Classes.cell_metres("S") == 32.0 and Classes.cell_metres("M") == 48.0
		and Classes.cell_metres("L") == 64.0 and Classes.cell_metres("XL") == 96.0,
		"the plan's cells: 32/48/64/96 m")
	_expect(Classes.cell_metres("XL", 180.0) == 96.0 and Classes.cell_metres("S", 20.0) == 20.0,
		"a positive cap only ever shrinks a cell")
	_expect(Classes.cell_metres("unknown", 180.0) == 180.0,
		"an unknown class takes the cap")
	_expect(is_equal_approx(Classes.radius_of(AABB(Vector3.ZERO, Vector3(2, 2, 1))), 1.5),
		"the radius is the box's half-diagonal")
	var hall := AABB(Vector3(-6, -2, -6), Vector3(12, 4, 12))
	var flat := Classes.placement_radius(hall, Basis())
	_expect(is_equal_approx(Classes.placement_radius(hall, Basis(Vector3.UP, PI / 4.0)), flat)
		and Classes.size_class(flat) == "L",
		"turning an instance does not change its radius or class (a 12 x 4 x 12 m hall is L)")
	_expect(is_equal_approx(Classes.placement_radius(hall, Basis().scaled(Vector3(2, 1, 2))),
		Vector3(24, 4, 24).length() * 0.5), "the placement's scale does")
	for name: String in Classes.CLASSES:
		_expect(Classes.CELL_METRES.has(name), "every class has a cell: " + name)

func _check_partition() -> void:
	var origins := PackedVector3Array([Vector3(0, 0, 0), Vector3(40, 0, 0), Vector3(10, 0, 0),
		Vector3(0, 0, 0), Vector3(70, 0, 0), Vector3(-1, 0, 0)])
	var radii := PackedFloat32Array([0.5, 0.5, 0.5, 5.0, 5.0, 0.5])
	var parts := Classes.partition(origins, radii, 180.0)
	var shapes: Array = parts.map(func(part: Dictionary) -> Array:
		return [part["class"], Array(part["members"] as PackedInt32Array)])
	_expect(shapes == [["S", [0, 2]], ["S", [1]], ["L", [3]], ["L", [4]], ["S", [5]]],
		"cells by class then 3D cell, in first-met order, members in their order: %s" % [shapes])
	var seen := {}
	for part: Dictionary in parts:
		for index: int in part["members"] as PackedInt32Array:
			seen[index] = int(seen.get(index, 0)) + 1
	_expect(seen.size() == origins.size() and seen.values().all(func(n: int) -> bool: return n == 1),
		"every member lands in exactly one cell")
	_expect(Classes.partition(origins, radii, 180.0) == parts, "the partition is deterministic")
	var capped := Classes.partition(PackedVector3Array([Vector3(0, 0, 0), Vector3(25, 0, 0)]),
		PackedFloat32Array([0.5, 0.5]), 20.0)
	_expect(capped.size() == 2, "a 20 m cap splits what a 32 m S cell would keep together")
	var boxes: Array[AABB] = [AABB(Vector3(-1, 0, -1), Vector3(2, 2, 2)),
		AABB(Vector3(9, 0, -1), Vector3(2, 4, 2))]
	_expect(Classes.frame_origin(boxes, PackedVector3Array()).is_equal_approx(Vector3(5, 2, 0)),
		"the frame is the centre of the merged boxes")
	var none: Array[AABB] = []
	_expect(Classes.frame_origin(none, PackedVector3Array([Vector3(0, 0, 0), Vector3(4, 2, 0)])
		).is_equal_approx(Vector3(2, 1, 0)), "with no boxes, the mean origin")

func _check_scope() -> void:
	_expect(Classes.applies_to(CONTINENT), "continent territories and chunks are split")
	_expect(Classes.applies_to(GAUNTLET), "gauntlets are split")
	_expect(not Classes.applies_to({}), "an interior or an older map is not")
	_expect(not Classes.applies_to({"continentGeography": true, "gauntlet": "yes"}),
		"only the manifests' own blocks count")

# --------------------------------------------------------------------------
# The loader
# --------------------------------------------------------------------------

## Two prototypes, 20 placements each along x every 10 m: a 1 m crate (S) on
## z = 0 and a 12 x 4 x 12 m hall (L) on z = 100, the hall turned a little more
## at each placement. Legacy rule: x 0-170 share the first 180 m cell (18 of
## each batch), x 180-190 are two of a kind (loose).
func _two_prototype_world(data: Dictionary) -> Dictionary:
	var world := Node3D.new()
	world.name = "ImportedWorld_cells"
	root.add_child(world)
	var crate := _array_mesh(Vector3(1, 1, 1))
	var hall := _array_mesh(Vector3(12, 4, 12))
	var small: Array[MeshInstance3D] = []
	var large: Array[MeshInstance3D] = []
	for index: int in 20:
		small.append(_place(world, "Crate_%02d" % index, crate,
			Transform3D(Basis(), Vector3(index * 10.0, 0.0, 0.0))))
		large.append(_place(world, "Hall_%02d" % index, hall,
			Transform3D(Basis(Vector3.UP, index * 0.3), Vector3(index * 10.0, 2.0, 100.0))))
	var loader := _loader(world, data)
	return {"world": world, "loader": loader, "small": small, "large": large}

func _check_continent_cells() -> void:
	var built := _two_prototype_world(CONTINENT)
	var world: Node3D = built.world
	var loader: WorldLoader = built.loader
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	var batches := _batches(world)
	# S (32 m): x 0-30 | 40-60 | 70-90 | 100-120 | 130-150 | 160-170 -> 6 cells.
	# L (64 m): x 0-60 | 70-120 | 130-170 on z = 100 -> 3 cells.
	_expect(batches.size() == 9, "18 crates in six 32 m cells, 18 halls in three 64 m cells (%d)" % batches.size())
	var names := {}
	for batch: MultiMeshInstance3D in batches:
		names[str(batch.name)] = true
	_expect(names.size() == batches.size() and names.has("StaticBatch_0_Crate_00"),
		"batch names stay StaticBatch_<n>_<first member> and unique")
	_expect(int(loader.load_phases.get(&"staticBatches", -1)) == 9
		and int(loader.load_phases.get(&"staticBatchInstances", -1)) == 36,
		"the load report counts batches and the instances they swallowed")
	var classes := {}
	for batch: MultiMeshInstance3D in batches:
		var kind := str(batch.get_meta(Classes.CLASS_META, ""))
		classes[kind] = int(classes.get(kind, 0)) + 1
	_expect(classes == {"S": 6, "L": 3}, "every split batch carries its class: %s" % [classes])
	var first := world.get_node("StaticBatch_0_Crate_00") as MultiMeshInstance3D
	_expect(first != null and first.multimesh.instance_count == 4
		and first.transform.origin.is_equal_approx(Vector3(15.0, 0.0, 0.0))
		and first.transform.basis.is_equal_approx(Basis()),
		"a batch stands at its members' centre, unturned (x 0-30 -> 15)")
	var members_by_batch := _members_by_batch(world)
	var batched := 0
	var all_relative := true
	var all_centred := true
	for batch: MultiMeshInstance3D in batches:
		var members: Array = members_by_batch.get(batch, [])
		batched += members.size()
		_expect(members.size() == batch.multimesh.instance_count,
			"%s draws exactly its stamped members" % batch.name)
		var box := AABB()
		for slot: int in members.size():
			var member := members[slot] as MeshInstance3D
			var placed := member.transform
			box = placed * member.mesh.get_aabb() if slot == 0 else box.merge(placed * member.mesh.get_aabb())
			if _stores_transforms:
				var drawn := batch.transform * batch.multimesh.get_instance_transform(slot)
				all_relative = all_relative and drawn.is_equal_approx(placed)
		all_centred = all_centred and batch.transform.origin.is_equal_approx(box.get_center())
	_expect(all_centred, "every batch's origin is its members' box centre")
	if _stores_transforms:
		_expect(all_relative, "every instance draws where its member stands (batch frame x instance)")
	_expect(batched == 36, "36 members batched, as the legacy rule batches them (%d)" % batched)
	for index: int in [18, 19]:
		var crate := (built.small as Array)[index] as MeshInstance3D
		var hall := (built.large as Array)[index] as MeshInstance3D
		_expect(crate.visible and hall.visible and not crate.has_meta(WorldLoader.BATCH_META)
			and not hall.has_meta(WorldLoader.BATCH_PATH_META),
			"the two-of-a-kind placements past 180 m stay loose: %d" % index)
	_free(world, loader)

## The same world under a manifest without continent or gauntlet blocks: the
## batches the loader made before WD-C2, exactly.
func _check_legacy_maps_unchanged() -> void:
	var built := _two_prototype_world({})
	var world: Node3D = built.world
	var loader: WorldLoader = built.loader
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	var batches := _batches(world)
	_expect(batches.size() == 2, "one batch per mesh per 180 m cell (%d)" % batches.size())
	var plain := true
	for batch: MultiMeshInstance3D in batches:
		plain = plain and batch.transform == Transform3D.IDENTITY \
			and not batch.has_meta(Classes.CLASS_META) and batch.multimesh.instance_count == 18
	_expect(plain, "legacy batches stand at the identity with no class and 18 members")
	_expect(world.get_node_or_null("StaticBatch_0_Crate_00") != null
		and world.get_node_or_null("StaticBatch_1_Hall_00") != null,
		"and keep their names")
	if _stores_transforms:
		var hall := (built.large as Array)[5] as MeshInstance3D
		var batch := hall.get_meta(WorldLoader.BATCH_META) as MultiMeshInstance3D
		_expect(batch.multimesh.get_instance_transform(int(hall.get_meta(WorldLoader.BATCH_INDEX_META))
			).is_equal_approx(hall.transform), "and hold the imported-root transform itself")
	# Membership: the split world hides exactly the members this one hides.
	var split := _two_prototype_world(CONTINENT)
	await process_frame
	(split.loader as WorldLoader).call("_batch_static_instances", _meshes(split.world))
	_expect(_hidden_names(world) == _hidden_names(split.world as Node3D),
		"the class split batches exactly the instances the legacy rule batches")
	_free(world, loader)
	_free(split.world, split.loader)

## Six of one mesh in one cell, three at scale 1 (S) and three at scale 2
## (r ~1.73 m, M): the legacy rule batches all six, the split makes two
## batches of three - below the minimum, and still batched.
func _check_mixed_classes_stay_batched() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_mixed"
	root.add_child(world)
	var mesh := _array_mesh(Vector3(1, 1, 1))
	for index: int in 6:
		var scale := 1.0 if index % 2 == 0 else 2.0
		_place(world, "Rock_%d" % index, mesh,
			Transform3D(Basis().scaled(Vector3.ONE * scale), Vector3(index * 2.0, 0, 0)))
	var loader := _loader(world, GAUNTLET)
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	var batches := _batches(world)
	var classes: Array = batches.map(func(batch: MultiMeshInstance3D) -> Array:
		return [str(batch.get_meta(Classes.CLASS_META, "")), batch.multimesh.instance_count])
	classes.sort()
	_expect(classes == [["M", 3], ["S", 3]], "S and M members split into two batches of three: %s" % [classes])
	_expect(_hidden_names(world).size() == 6, "and none of the six is turned loose")
	_free(world, loader)

## Four of a kind across the 180 m boundary (two each side) fall in one 32 m S
## cell: the legacy rule leaves them loose, and so does the split.
func _check_loose_stays_loose() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_loose"
	root.add_child(world)
	var mesh := _array_mesh(Vector3(1, 1, 1))
	for x: float in [170.0, 175.0, 182.0, 186.0]:
		_place(world, "Post_%d" % int(x), mesh, Transform3D(Basis(), Vector3(x, 0, 0)))
	var loader := _loader(world, CONTINENT)
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	_expect(_batches(world).is_empty() and _hidden_names(world).is_empty(),
		"a loose group the legacy rule does not batch is not batched by its class cell")
	_free(world, loader)

## `rendering.batchCellMetres` stays the manifest's override: the membership
## cell and the cap on every class cell.
func _check_manifest_cap() -> void:
	var data: Dictionary = CONTINENT.duplicate(true)
	data["rendering"] = {"batchCellMetres": 20.0}
	var world := Node3D.new()
	world.name = "ImportedWorld_cap"
	root.add_child(world)
	var mesh := _array_mesh(Vector3(1, 1, 1))
	# Eight crates in one 20 m cell (x 0-14 every 2 m) and eight in the next.
	for index: int in 16:
		_place(world, "Crate_%02d" % index, mesh, Transform3D(Basis(), Vector3(index * 2.0 + (4.0 if index >= 8 else 0.0), 0, 0)))
	var loader := _loader(world, data)
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	var batches := _batches(world)
	_expect(batches.size() == 2 and batches.all(func(batch: MultiMeshInstance3D) -> bool:
			return batch.multimesh.instance_count == 8),
		"a 20 m manifest cell caps the 32 m S cell: two batches of eight (%d)" % batches.size())
	_free(world, loader)

## A detached build (a worker's private tree, never in the scene) batches the
## same way: nothing in the split asks the tree.
func _check_detached_build() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_detached"
	var mesh := _array_mesh(Vector3(1, 1, 1))
	for index: int in 8:
		_place(world, "Bush_%d" % index, mesh, Transform3D(Basis(), Vector3(index * 8.0, 0, 0)))
	var loader := WorldLoader.new()
	loader.detached_build = true
	loader.manifest = WorldManifest.new()
	loader.manifest.data = CONTINENT.duplicate(true)
	loader.world_root = world
	loader.call("_batch_static_instances", _meshes(world))
	var batches := _batches(world)
	# S cells: x 0-24 (4) and 32-56 (4).
	_expect(batches.size() == 2 and batches.all(func(batch: MultiMeshInstance3D) -> bool:
			return batch.has_meta(Classes.CLASS_META) and batch.multimesh.instance_count == 4),
		"an off-tree detached build splits its batches too (%d)" % batches.size())
	loader.world_root = null
	loader.free()
	world.free()

## The batch frame, its class and the member links survive packing into a
## scene, the way the geometry cache and the map cache store a region.
func _check_round_trip() -> void:
	var built := _two_prototype_world(CONTINENT)
	var world: Node3D = built.world
	var loader: WorldLoader = built.loader
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	var expected := {}
	for batch: MultiMeshInstance3D in _batches(world):
		expected[str(batch.name)] = [batch.transform, str(batch.get_meta(Classes.CLASS_META, ""))]
	for node: Node in world.find_children("*", "", true, false):
		node.owner = world
		if node.has_meta(WorldLoader.BATCH_META):
			node.remove_meta(WorldLoader.BATCH_META)
	var packed := PackedScene.new()
	_expect(packed.pack(world) == OK, "a split region packs")
	DirAccess.make_dir_recursive_absolute(SCRATCH)
	var path := SCRATCH + "/cells.scn"
	_expect(ResourceSaver.save(packed, path, ResourceSaver.FLAG_COMPRESS) == OK, "and saves")
	_free(world, loader)
	await process_frame
	var reloaded := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	var restored := reloaded.instantiate() as Node3D
	root.add_child(restored)
	await process_frame
	var reader := WorldLoader.new()
	root.add_child(reader)
	reader.world_root = restored
	var resolved: int = reader.call("_resolve_batch_links")
	_expect(resolved == 36, "every member link resolves after the round trip (%d)" % resolved)
	var same := true
	for batch: MultiMeshInstance3D in _batches(restored):
		var row: Array = expected.get(str(batch.name), [])
		same = same and not row.is_empty() and (batch.transform as Transform3D).is_equal_approx(row[0]) \
			and str(batch.get_meta(Classes.CLASS_META, "")) == str(row[1])
	_expect(same and _batches(restored).size() == expected.size(),
		"every batch comes back with its frame and its class")
	var hall := restored.get_node("Hall_09") as MeshInstance3D
	var link: Variant = hall.get_meta(WorldLoader.BATCH_META, null)
	_expect(link is MultiMeshInstance3D and (link as MultiMeshInstance3D).get_meta(Classes.CLASS_META, "") == "L"
		and restored.get_node(hall.get_meta(WorldLoader.BATCH_PATH_META) as NodePath) == link,
		"a hall's link names the L batch that draws it")
	reader.world_root = null
	reader.queue_free()
	restored.queue_free()
	await process_frame

## OccluderFade lifts a member out of a centred batch to fade it and hands it
## back: the lifted instance keeps its (batch-relative) origin.
func _check_occluder_fade() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_fade"
	root.add_child(world)
	var camera := Camera3D.new()
	camera.position = Vector3(0.0, 10.0, 10.0)
	world.add_child(camera)
	var player := Node3D.new()
	world.add_child(player)
	var mesh := _array_mesh(Vector3(2, 2, 2))
	# One on the camera-to-player line and three more of the kind beside it, all
	# in one 180 m cell and one 48 m M cell (a 2 m barrel has r ~1.73 m).
	var on_line := _place(world, "Barrel_0", mesh, Transform3D(Basis(), Vector3(0.0, 5.5, 5.0)))
	for index: int in [1, 2, 3]:
		_place(world, "Barrel_%d" % index, mesh, Transform3D(Basis(), Vector3(5.0 + index * 3.0, 0.0, 5.0)))
	var loader := _loader(world, CONTINENT)
	await process_frame
	loader.call("_batch_static_instances", _meshes(world))
	var batch := on_line.get_meta(WorldLoader.BATCH_META, null) as MultiMeshInstance3D
	if not _expect(batch != null and not batch.transform.origin.is_zero_approx(),
			"the barrel is drawn by a batch standing off the origin"):
		_free(world, loader)
		return
	var slot := int(on_line.get_meta(WorldLoader.BATCH_INDEX_META))
	var relative := Transform3D(Basis(), on_line.transform.origin - batch.transform.origin)
	var fade: RefCounted = OccluderFadeScript.new()
	fade.configure(null, world)
	fade.set_enabled(true)
	fade.update(SETTLE, camera, player)
	_expect(on_line.visible and on_line.get_surface_override_material(0) != null,
		"a member on the sight line is lifted out of its centred batch to fade")
	if _stores_transforms:
		var lifted := batch.multimesh.get_instance_transform(slot)
		_expect(lifted.basis.determinant() == 0.0 and lifted.origin.is_equal_approx(relative.origin),
			"the batch stops drawing it and keeps its batch-relative origin")
	player.global_position = Vector3(0.0, 0.0, 60.0)
	camera.global_position = Vector3(0.0, 10.0, 70.0)
	await process_frame
	fade.update(SETTLE, camera, player)
	_expect(not on_line.visible and on_line.get_surface_override_material(0) == null,
		"and is handed back to the batch afterwards")
	if _stores_transforms:
		_expect(batch.multimesh.get_instance_transform(slot).is_equal_approx(relative),
			"the batch draws it where it stood")
	fade.reset()
	_free(world, loader)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

func _loader(world: Node3D, data: Dictionary) -> WorldLoader:
	var loader := WorldLoader.new()
	loader.manifest = WorldManifest.new()
	loader.manifest.data = data.duplicate(true)
	loader.world_root = world
	return loader

func _free(world: Node, loader: WorldLoader) -> void:
	loader.world_root = null
	loader.free()
	if is_instance_valid(world):
		world.queue_free()

## A box as an ArrayMesh with one opaque StandardMaterial3D surface, centred
## on its origin, as an imported prototype mesh is.
func _array_mesh(size: Vector3) -> ArrayMesh:
	var box := BoxMesh.new()
	box.size = size
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, box.get_mesh_arrays())
	mesh.surface_set_material(0, StandardMaterial3D.new())
	return mesh

func _place(parent: Node3D, node_name: String, mesh: Mesh, placement: Transform3D) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.transform = placement
	parent.add_child(node)
	return node

func _meshes(world: Node) -> Array:
	return world.find_children("*", "MeshInstance3D", true, false)

func _batches(world: Node) -> Array[MultiMeshInstance3D]:
	var found: Array[MultiMeshInstance3D] = []
	for node: Node in world.find_children("StaticBatch_*", "MultiMeshInstance3D", true, false):
		found.append(node as MultiMeshInstance3D)
	return found

## batch -> its members in slot order.
func _members_by_batch(world: Node) -> Dictionary:
	var by_batch := {}
	for node: Node in _meshes(world):
		if not node.has_meta(WorldLoader.BATCH_META):
			continue
		var batch: Variant = node.get_meta(WorldLoader.BATCH_META)
		var members: Array = by_batch.get(batch, [])
		members.append(node)
		by_batch[batch] = members
	for batch: Variant in by_batch:
		(by_batch[batch] as Array).sort_custom(func(a: Node, b: Node) -> bool:
			return int(a.get_meta(WorldLoader.BATCH_INDEX_META)) < int(b.get_meta(WorldLoader.BATCH_INDEX_META)))
	var linked := true
	for batch: Variant in by_batch:
		var members: Array = by_batch[batch]
		for slot: int in members.size():
			var member := members[slot] as Node
			linked = linked and int(member.get_meta(WorldLoader.BATCH_INDEX_META)) == slot \
				and not (member as MeshInstance3D).visible \
				and world.get_node_or_null(member.get_meta(WorldLoader.BATCH_PATH_META) as NodePath) == batch
	_expect(linked, "members are hidden, slotted 0..n-1, and their paths name their batch")
	return by_batch

func _hidden_names(world: Node) -> Array:
	var names: Array = []
	for node: Node in _meshes(world):
		if not (node as MeshInstance3D).visible:
			names.append(str(node.name))
	names.sort()
	return names

## See tests/test_occluder_fade.gd: the headless rendering server may accept
## MultiMesh writes and report identity back.
func _multimesh_stores_transforms() -> bool:
	var probe := MultiMesh.new()
	probe.transform_format = MultiMesh.TRANSFORM_3D
	probe.mesh = BoxMesh.new()
	probe.instance_count = 1
	var written := Transform3D(Basis(), Vector3(1.0, 2.0, 3.0))
	probe.set_instance_transform(0, written)
	return probe.get_instance_transform(0).origin.is_equal_approx(written.origin)

func _remove_tree(path: String) -> void:
	var directory := DirAccess.open(path)
	if directory == null:
		return
	for file: String in directory.get_files():
		directory.remove(file)
	for child: String in directory.get_directories():
		_remove_tree(path.path_join(child))
	DirAccess.remove_absolute(path)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

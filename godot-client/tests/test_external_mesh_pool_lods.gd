extends SceneTree

## Generated prototype LODs (wave 2 WD-C5).
##
## ExternalMeshPool.acquire gives a shared prototype meshoptimizer LODs
## (ImporterMesh.generate_lods) before it becomes an ArrayMesh, when the mesh
## it publishes has at least WorldDistanceClasses.LOD_MIN_TRIANGLES triangles
## and a mesh box half-diagonal of at least LOD_MIN_RADIUS (the S limit). The
## levels leave the vertices and the full index list as parsed; the distance
## pass's lod_bias decides how early they are drawn.
##
## Checked here: the rule and its numbers; the shape the rule reads (triangle
## surfaces only, non-indexed surfaces, the radius); synthetic meshes on both
## sides of each limit; surfaces untouched by the levels; two shipped
## prototypes (a broadleaf tree and a temple wall: more than one level, LOD1 at
## most 60 % of LOD0, the tree's ladder exactly as the plan measured it), a
## small dense tussock and a sparse meadow left whole, an M undergrowth given
## levels; determinism across parses; a parse on a worker thread; the byte
## ledger and counters, the live entries with levels among them; a cooked-blob
## round trip (duplicate + ResourceSaver, as MapGeometryWriter saves a
## prototype) keeping levels and their byte figure, and counted as live with
## levels once published without a generation; and the distance pass biasing
## a placement of an LOD'd prototype.
##
## Run: Godot_v4.7.2-stable_win64.exe --headless --path . \
##         --script tests/test_external_mesh_pool_lods.gd

const Pool := preload("res://src/world/external_mesh_pool.gd")
const Classes := preload("res://src/world/world_distance_classes.gd")
const WorldDistance := preload("res://src/world/world_distance.gd")
const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

const MESHES := "res://../eloria-assets/maps/_shared/meshes"
## kit-sw-broadleaf-tree-b: 5,781 triangles, 7.5 x 14 x 6.3 m.
const TREE := "64bc632c1deedb3354a3f089b6de80d210224a6e70bbaf642df23ef25e9f2fc4"
## The plan's measured ladder for the tree (section 3.7, editor and release
## template agree): LOD0 5,781 then these.
const TREE_LADDER: Array[int] = [2890, 1445, 672, 258, 116]
## kit-temple-tier-wall-1: 3,576 triangles, 16 x 3.8 x 3.5 m.
const WALL := "7739c3be2a5da7c8d9e9dd8835855e8e9797c2567e5521d73f30d3935d7d00c3"
## kit-coastal-rock-3: 2,838 triangles, 6 x 2.1 x 6 m (the worker parse).
const ROCK := "28915a615734b4c4d12b874819d97dc6a29008d55dd9712a43194136e240a1bb"
## kit-jungle-undergrowth-3: 1,500 triangles, half-diagonal 1.68 m (M).
const UNDERGROWTH := "685acd61a5b414a66b95dccb1f9025bd60e78c9e41157681313a6b7335e535ef"
## kit-tussock-grass-1: 1,666 triangles, half-diagonal 0.96 m (S): whole.
const TUSSOCK := "18edc61842e11baf523328b61203e5985e2a5d6876582d41ab4a8ddcd3a15c82"
## kit-flower-meadow-1: 356 triangles, half-diagonal 1.93 m: whole.
const MEADOW := "172cfaaa0772b8bb77ac4f2d380a6825b7de6897fe070d816bdde9b2ac72fc20"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.unset_environment(HardwareTier.WORLD_DISTANCE_VARIABLE)
	# As Main and the loader do: the glTF extensions are registered on Main
	# before any parse, worker parses included.
	_expect(GltfQuantization.ensure_registered(), "the glTF extensions register on Main")
	_check_rule()
	_check_shape()
	_check_synthetic()
	_check_shipped()
	_check_left_whole()
	_check_determinism()
	await _check_worker()
	_check_ledger()
	_check_cooked_round_trip()
	_check_distance_bias()
	WorldDistance.reset_state()
	print("external mesh pool lod tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------

func _check_rule() -> void:
	_expect(Classes.LOD_MIN_TRIANGLES == 600 and is_equal_approx(Classes.LOD_MIN_RADIUS, 1.5)
		and is_equal_approx(Classes.LOD_MIN_RADIUS, Classes.CLASS_RADIUS_LIMITS[0]),
		"the plan's rule: at least 600 triangles and the S radius limit (1.5 m)")
	_expect(is_equal_approx(Classes.LOD_NORMAL_MERGE_ANGLE, 25.0)
		and is_equal_approx(Classes.LOD_NORMAL_SPLIT_ANGLE, 60.0),
		"the plan's generate_lods(25, 60) angles")
	_expect(Classes.generates_lods(600, 1.5) and Classes.generates_lods(5781, 8.6)
		and not Classes.generates_lods(599, 8.6) and not Classes.generates_lods(5781, 1.49)
		and not Classes.generates_lods(0, 0.0), "both limits are inclusive lower bounds")

# --------------------------------------------------------------------------
# What the rule reads
# --------------------------------------------------------------------------

func _sphere(radius: float, segments: int, rings: int) -> Array:
	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	sphere.radial_segments = segments
	sphere.rings = rings
	return sphere.get_mesh_arrays()

func _importer(surfaces: Array, primitive := Mesh.PRIMITIVE_TRIANGLES) -> ImporterMesh:
	var mesh := ImporterMesh.new()
	for arrays: Array in surfaces:
		mesh.add_surface(primitive, arrays)
	return mesh

func _triangles(arrays: Array) -> int:
	var indices: Variant = arrays[Mesh.ARRAY_INDEX]
	return (indices as PackedInt32Array).size() / 3 if indices is PackedInt32Array \
		else (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3

func _check_shape() -> void:
	var small := _sphere(0.5, 64, 32)
	var shape := Pool.lod_shape(_importer([small]))
	_expect(int(shape.triangles) == _triangles(small) and int(shape.triangles) >= 600,
		"the shape counts the indexed triangles (%d)" % int(shape.triangles))
	var drawn := ArrayMesh.new()
	drawn.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, small)
	_expect(absf(float(shape.radius) - drawn.get_aabb().size.length() * 0.5) < 1e-4,
		"the radius is the mesh box's half-diagonal (%.4f, the ArrayMesh's %.4f)" % [
			float(shape.radius), drawn.get_aabb().size.length() * 0.5])
	# Two surfaces: the counts add up and the box spans both.
	var two := _importer([small, small])
	_expect(int(Pool.lod_shape(two).triangles) == 2 * _triangles(small), "triangles add up over surfaces")
	# A line surface is no triangle surface.
	var lines := ImporterMesh.new()
	var line_arrays: Array = []
	line_arrays.resize(Mesh.ARRAY_MAX)
	var points := PackedVector3Array()
	for index: int in 2000:
		points.append(Vector3(float(index) * 0.01, 0.0, 0.0))
	line_arrays[Mesh.ARRAY_VERTEX] = points
	lines.add_surface(Mesh.PRIMITIVE_LINES, line_arrays)
	_expect(int(Pool.lod_shape(lines).triangles) == 0, "line surfaces do not count")
	# Non-indexed triangles count by their vertices.
	var loose: Array = []
	loose.resize(Mesh.ARRAY_MAX)
	var corners := PackedVector3Array()
	for index: int in 700:
		var x := float(index % 50)
		var z := float(index / 50)
		corners.append(Vector3(x, 0, z))
		corners.append(Vector3(x + 1, 0, z))
		corners.append(Vector3(x, 1, z))
	loose[Mesh.ARRAY_VERTEX] = corners
	var loose_shape := Pool.lod_shape(_importer([loose]))
	_expect(int(loose_shape.triangles) == 700 and float(loose_shape.radius) >= Classes.LOD_MIN_RADIUS,
		"non-indexed triangles count by vertices, and a large box reaches the limit")
	# A sparse mesh is not measured at all.
	_expect(float(Pool.lod_shape(_importer([_sphere(2.0, 8, 4)])).radius) == 0.0,
		"a mesh under the triangle limit is not measured")

func _surface_digest(mesh: ImporterMesh) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	for surface: int in mesh.get_surface_count():
		context.update(var_to_bytes(mesh.get_surface_arrays(surface)))
	return context.finish().hex_encode()

func _check_synthetic() -> void:
	var dense := _importer([_sphere(2.0, 64, 32)])
	var before := _surface_digest(dense)
	var levels := Pool.generate_lods(dense)
	_expect(levels > 0 and dense.get_surface_lod_count(0) == levels,
		"a dense 4 m sphere gets levels (%d)" % levels)
	_expect(_surface_digest(dense) == before, "the levels leave the vertices and the full index list alone")
	var first := dense.get_surface_lod_indices(0, 0).size() / 3 if levels > 0 else 0
	_expect(levels > 0 and first < _triangles(dense.get_surface_arrays(0)),
		"the first level draws fewer triangles than the mesh")
	var tiny := _importer([_sphere(0.5, 64, 32)])
	_expect(Pool.generate_lods(tiny) == -1 and tiny.get_surface_lod_count(0) == 0,
		"a dense prop under the S limit stays whole")
	var sparse := _importer([_sphere(2.0, 8, 4)])
	_expect(Pool.generate_lods(sparse) == -1 and sparse.get_surface_lod_count(0) == 0,
		"a large prop under 600 triangles stays whole")

# --------------------------------------------------------------------------
# Shipped prototypes
# --------------------------------------------------------------------------

func _path(key: String) -> String:
	return MESHES.path_join(key + ".glb")

## The levels of `mesh`'s surface `surface` as triangle counts, read from the
## ArrayMesh's stored surface (headless: the dummy renderer keeps it).
func _ladder(mesh: Mesh, surface := 0) -> Array[int]:
	var result: Array[int] = []
	var stored: Variant = mesh.get("_surfaces")
	if not stored is Array or (stored as Array).size() <= surface:
		return result
	var lods: Variant = ((stored as Array)[surface] as Dictionary).get("lods")
	if not lods is Array:
		return result
	var array_mesh := mesh as ArrayMesh
	var stride := RenderingServer.mesh_surface_get_format_index_stride(array_mesh.surface_get_format(surface),
		array_mesh.surface_get_array_len(surface))
	for index: int in range(1, (lods as Array).size(), 2):
		result.append(((lods as Array)[index] as PackedByteArray).size() / stride / 3)
	return result

func _lod_bytes(mesh: Mesh) -> int:
	var total := 0
	var stored: Variant = mesh.get("_surfaces")
	if not stored is Array:
		return -1
	for surface: Dictionary in stored:
		var lods: Variant = surface.get("lods")
		if lods is Array:
			for index: int in range(1, (lods as Array).size(), 2):
				total += ((lods as Array)[index] as PackedByteArray).size()
	return total

## The prototype parsed as the pool parses it, without levels.
func _reference(key: String) -> ArrayMesh:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var entry: Dictionary = Pool.index_for(_path(key)).get(key, {})
	var plan: Dictionary = VramTextures.plan_for(Pool._image_manifest(entry))
	if not plan.is_empty():
		state.set_additional_data(VramTextures.PLAN_KEY, plan)
	if document.append_from_file(_path(key), state) != OK or state.get_meshes().is_empty():
		return null
	return (state.get_meshes()[0] as GLTFMesh).mesh.get_mesh()

func _same_surfaces(left: Mesh, right: Mesh) -> bool:
	if left == null or right == null or left.get_surface_count() != right.get_surface_count():
		return false
	for surface: int in left.get_surface_count():
		var a := left.surface_get_arrays(surface)
		var b := right.surface_get_arrays(surface)
		for slot: int in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_INDEX]:
			if a[slot] != b[slot]:
				return false
		if (left as ArrayMesh).surface_get_format(surface) != (right as ArrayMesh).surface_get_format(surface):
			return false
	return true

func _check_shipped() -> void:
	var before: Dictionary = Pool.retention_snapshot().prototype_lods
	var tree := Pool.acquire(TREE, _path(TREE))
	var wall := Pool.acquire(WALL, _path(WALL))
	_expect(tree != null and wall != null, "the tree and the wall parse")
	if tree == null or wall == null:
		return
	var tree_ladder := _ladder(tree)
	var wall_ladder := _ladder(wall)
	var tree_base: int = (tree as ArrayMesh).surface_get_array_index_len(0) / 3
	var wall_base: int = (wall as ArrayMesh).surface_get_array_index_len(0) / 3
	_expect(tree_ladder.size() > 1 and wall_ladder.size() > 1,
		"both get more than one level (tree %s, wall %s)" % [tree_ladder, wall_ladder])
	_expect(not tree_ladder.is_empty() and not wall_ladder.is_empty()
		and float(tree_ladder[0]) <= 0.6 * float(tree_base) and float(wall_ladder[0]) <= 0.6 * float(wall_base),
		"LOD1 draws at most 60 %% of LOD0 (tree %d of %d, wall %d of %d)" % [
			tree_ladder[0] if not tree_ladder.is_empty() else -1, tree_base,
			wall_ladder[0] if not wall_ladder.is_empty() else -1, wall_base])
	_expect(tree_base == 5781 and tree_ladder == TREE_LADDER,
		"the tree's ladder is the plan's measurement (5781 -> %s)" % [tree_ladder])
	_expect(_same_surfaces(tree, _reference(TREE)) and _same_surfaces(wall, _reference(WALL)),
		"the published surfaces equal a parse without levels")
	_expect(int(tree.get_meta(Pool.LOD_BYTES_META, -1)) == _lod_bytes(tree)
		and int(wall.get_meta(Pool.LOD_BYTES_META, -1)) == _lod_bytes(wall) and _lod_bytes(tree) > 0,
		"the byte figure on the mesh is its levels' index bytes (tree %d)" % _lod_bytes(tree))
	var undergrowth := Pool.acquire(UNDERGROWTH, _path(UNDERGROWTH))
	_expect(undergrowth != null and not _ladder(undergrowth).is_empty(),
		"an M undergrowth (r 1.68 m, 1,500 triangles) gets levels %s" % [_ladder(undergrowth) if undergrowth != null else []])
	var after: Dictionary = Pool.retention_snapshot().prototype_lods
	_expect(int(after.generated) == int(before.generated) + 3
		and int(after.levels) >= int(before.levels) + tree_ladder.size() + wall_ladder.size() + 1,
		"the session counters count the three prototypes and their levels")
	# A second sharer adopts the published mesh: no second parse or generation.
	var shared_before := Pool.last_shared
	_expect(Pool.acquire(TREE, _path(TREE)) == tree and Pool.last_shared == shared_before + 1
		and int(Pool.retention_snapshot().prototype_lods.generated) == int(after.generated),
		"a second sharer adopts the published tree")

func _check_left_whole() -> void:
	var before: Dictionary = Pool.retention_snapshot().prototype_lods
	var tussock := Pool.acquire(TUSSOCK, _path(TUSSOCK))
	var meadow := Pool.acquire(MEADOW, _path(MEADOW))
	_expect(tussock != null and _ladder(tussock).is_empty() and not tussock.has_meta(Pool.LOD_BYTES_META),
		"a dense S tussock (r 0.96 m) stays whole")
	_expect(meadow != null and _ladder(meadow).is_empty() and not meadow.has_meta(Pool.LOD_BYTES_META),
		"a sparse meadow (356 triangles) stays whole")
	_expect(int(Pool.retention_snapshot().prototype_lods.skipped) == int(before.skipped) + 2,
		"both count as left whole")

## A cooked blob is content-addressed: the same prototype must give the same
## levels on every parse.
func _check_determinism() -> void:
	var first := _ladder_bytes(Pool.acquire(WALL, _path(WALL)))
	# Hold nothing: the weak entry expires, the next acquire parses again.
	var parsed_before := Pool.last_parsed
	var again := Pool.acquire(ROCK, _path(ROCK))
	var rock := _ladder_bytes(again)
	again = null
	var reparsed := Pool.acquire(ROCK, _path(ROCK))
	_expect(Pool.last_parsed >= parsed_before + 2 and not rock.is_empty() and _ladder_bytes(reparsed) == rock,
		"two parses of the rock give byte-identical levels")
	_expect(not first.is_empty(), "the wall's levels are readable")

func _ladder_bytes(mesh: Mesh) -> Array:
	var out: Array = []
	if mesh == null:
		return out
	var stored: Variant = mesh.get("_surfaces")
	if stored is Array:
		for surface: Dictionary in stored:
			var lods: Variant = surface.get("lods")
			if lods is Array:
				out.append_array(lods as Array)
	return out

# --------------------------------------------------------------------------
# A worker parse
# --------------------------------------------------------------------------

var _worker_result: Mesh = null

func _worker_acquire() -> void:
	# Nothing holds the wall any more, so its weak entry has expired and the
	# worker parses it again, as a raw background chunk would.
	_worker_result = Pool.acquire(WALL, _path(WALL))

func _check_worker() -> void:
	var generated_before := int(Pool.retention_snapshot().prototype_lods.generated)
	_expect(Pool.live_count() >= 0 and Pool._published(WALL) == null, "the wall's entry has expired")
	var thread := Thread.new()
	_expect(thread.start(_worker_acquire) == OK, "the worker starts")
	# Never block Main on a worker that may wait for the rendering server.
	while thread.is_alive():
		await process_frame
	thread.wait_to_finish()
	var ladder := _ladder(_worker_result) if _worker_result != null else []
	_expect(_worker_result != null and ladder.size() > 1,
		"a worker parse gives the wall its levels %s" % [ladder])
	_expect(int(Pool.retention_snapshot().prototype_lods.generated) == generated_before + 1,
		"the worker's generation is counted")
	_worker_result = null

# --------------------------------------------------------------------------
# The byte ledger
# --------------------------------------------------------------------------

func _check_ledger() -> void:
	var tree := Pool.acquire(TREE, _path(TREE))
	var figure := int(tree.get_meta(Pool.LOD_BYTES_META, 0))
	_expect(figure > 0 and Pool.mesh_bytes(tree) == ResourceBytes.mesh_bytes(tree) + figure,
		"the ledger adds the levels' index bytes to the mesh's own")
	var plain := ArrayMesh.new()
	plain.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, _sphere(1.0, 8, 4))
	_expect(Pool.mesh_bytes(plain) == ResourceBytes.mesh_bytes(plain), "a mesh without levels counts as before")
	var snapshot := Pool.retention_snapshot()
	_expect(snapshot.has("prototype_lods") and int(snapshot.prototype_lods.index_bytes) >= figure
		and int(snapshot.prototype_lods.generated) >= 3 and int(snapshot.prototype_lods.empty) >= 0,
		"retention_snapshot reports prototype_lods %s" % [snapshot.get("prototype_lods")])
	# The live figures: the held tree carries levels, a held tussock does not.
	var tussock := Pool.acquire(TUSSOCK, _path(TUSSOCK))
	var held: Dictionary = Pool.retention_snapshot().prototype_lods
	_expect(tussock != null and int(held.get("live_entries", -1)) >= 1
		and int(held.get("live_index_bytes", -1)) >= figure,
		"the live entries carrying levels are counted (%s)" % [held])
	tree = null
	var released: Dictionary = Pool.retention_snapshot().prototype_lods
	_expect(int(released.get("live_entries", -1)) == int(held.get("live_entries", 0)) - 1
		and int(released.get("live_index_bytes", -1)) == int(held.get("live_index_bytes", 0)) - figure,
		"an expired tree leaves the live figures; the tussock never counted (%s)" % [released])
	tussock = null
	Pool.reset_counters()
	_expect(Pool.last_lods == 0 and Pool.last_parsed == 0, "reset_counters clears the per-load lod count")
	var reparsed := Pool.acquire(UNDERGROWTH, _path(UNDERGROWTH))
	_expect(reparsed != null and Pool.last_parsed == 1 and Pool.last_lods == 1,
		"a load's lod count follows its parses (parsed %d, lods %d)" % [Pool.last_parsed, Pool.last_lods])

# --------------------------------------------------------------------------
# A cooked blob
# --------------------------------------------------------------------------

func _check_cooked_round_trip() -> void:
	var tree := Pool.acquire(TREE, _path(TREE))
	# MapGeometryWriter._save_resource: duplicate(false), then a compressed
	# binary resource.
	var native := tree.duplicate(false) as ArrayMesh
	var path := "user://wdc5_lod_round_trip.res"
	var error := ResourceSaver.save(native, path, ResourceSaver.FLAG_COMPRESS)
	var loaded := ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE) as ArrayMesh
	_expect(error == OK and loaded != null, "the prototype saves and loads as a binary resource")
	if loaded != null:
		_expect(_ladder_bytes(loaded) == _ladder_bytes(tree) and _ladder(loaded) == TREE_LADDER,
			"the cooked copy keeps the levels byte for byte")
		_expect(int(loaded.get_meta(Pool.LOD_BYTES_META, -1)) == int(tree.get_meta(Pool.LOD_BYTES_META, -2))
			and Pool.mesh_bytes(loaded) == Pool.mesh_bytes(tree),
			"and its byte figure, so the ledger counts a cooked prototype the same")
		# A cooked arrival publishes the loaded blob (PreparedSceneLifecycle):
		# nothing is generated, yet the live figures show its levels.
		var before: Dictionary = Pool.retention_snapshot().prototype_lods
		var cooked_key := "wdc5-cooked-round-trip"
		_expect(Pool._publish_or_adopt(cooked_key, loaded) == loaded, "the cooked copy publishes")
		var after: Dictionary = Pool.retention_snapshot().prototype_lods
		_expect(int(after.generated) == int(before.generated)
			and int(after.get("live_entries", -1)) == int(before.get("live_entries", 0)) + 1
			and int(after.get("live_index_bytes", -1)) == int(before.get("live_index_bytes", 0))
				+ int(loaded.get_meta(Pool.LOD_BYTES_META, 0)),
			"a published cooked prototype counts as live with levels without a generation (%s)" % [after])
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))

# --------------------------------------------------------------------------
# The distance pass biases the levels
# --------------------------------------------------------------------------

func _check_distance_bias() -> void:
	var tree := Pool.acquire(TREE, _path(TREE))
	var root := Node3D.new()
	root.name = "ImportedWorld_test"
	var placement := MeshInstance3D.new()
	placement.name = "kit-sw-broadleaf-tree-b"
	placement.mesh = tree
	placement.set_meta(Pool.POOLED_META, TREE)
	root.add_child(placement)
	WorldDistance.reset_state()
	WorldDistance.apply_root(root, WorldDistance.state_for(26.0, LookProfile.Quality.LOW))
	_expect(is_equal_approx(placement.lod_bias, Classes.lod_bias("LOW")),
		"a placement of the LOD'd tree takes LOW's bias (%.2f)" % placement.lod_bias)
	WorldDistance.apply_root(root, WorldDistance.state_for(26.0, LookProfile.Quality.HIGH))
	_expect(is_equal_approx(placement.lod_bias, 1.0), "and HIGH's 1.0 on a re-apply")
	root.free()

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

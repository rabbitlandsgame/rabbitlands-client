class_name WorldLoader
extends Node3D

const WORLD_COLLISION_LAYER := 1
const NAVIGATION_SURFACE_LAYER := 8
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")
const BiomeBlendMaterial := preload("res://src/world/biome_blend_material.gd")
const ObjectMaterialRefresh := preload("res://src/world/object_material_refresh.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const ExternalMeshPool := preload("res://src/world/external_mesh_pool.gd")
const MapMeshExtension := preload("res://src/world/map_mesh_extension.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const UndergroundScenery := preload("res://src/world/underground_scenery.gd")
const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const GauntletSurfaceContrast := preload("res://src/world/gauntlet_surface_contrast.gd")

# Static-instance batching. A region such as Four Gates imports ~1700 mesh
# nodes that between them reference only 42 meshes, so almost every draw call
# repeats geometry the GPU already holds. Groups of identical opaque meshes are
# collapsed into one MultiMeshInstance3D per spatial cell, which keeps frustum
# culling meaningful while cutting draw calls by more than an order of
# magnitude. The rendered result is the same geometry with the same materials
# at the same transforms.
const BATCH_MINIMUM_INSTANCES := 4
const BATCH_CELL_METRES := 180.0
# Stamped on every source node a batch swallowed, naming the MultiMeshInstance3D
# that now draws it and its slot in that multimesh. A batched prop is otherwise
# untraceable from the node the rest of the client still holds, and OccluderFade
# has to reach the slot to lift one instance back out while it fades.
const BATCH_META := "static_batch"
const BATCH_INDEX_META := "static_batch_index"
# The same link written as a path from the imported root, which is the half of
# it that survives being packed into a scene.
#
# Node metadata is stored in a PackedScene, but a Node is not a Resource, and a
# Variant holding one is dropped on the way out - not nulled, dropped: after a
# round trip the key is not in `get_meta_list()` at all. A cached region whose
# batched props had only the object link would leave OccluderFade unable to
# find the MultiMesh drawing them, so it would fade a node that is not drawing
# and the prop in front of the player would stay solid. A NodePath is a
# built-in type and survives, so both are written and `_resolve_batch_links()`
# turns the path back into the object after a cache load.
const BATCH_PATH_META := "static_batch_path"

# The widest sibling list a package may hand Godot's scene builder.
#
# `GLTFDocument.generate_scene()` adds every node with a readable name, and
# that path checks the proposed name against the children the parent already
# holds, so it is quadratic in the width of a sibling list. The regions are
# built wide - Amberwood hangs 7 935 nodes off one parent, Verdant Stair 9 449
# - and that is where their load went: 3.9 s and 4.2 s of scene building
# against Four Gates' 117 ms for 1 276 siblings. Bucketing an over-wide list
# under empty grouping nodes before the scene is generated takes those two to
# 209 ms and 180 ms and costs about 9 ms.
#
# The groups carry an identity transform and no geometry, so every mesh keeps
# the world placement, name, mesh and visibility it had; only its depth in the
# tree changes, and every pass in this file and every consumer of the loaded
# world reaches nodes by a recursive search or by name. A list at or under
# this width is left exactly as the package built it: a thousand siblings cost
# a millisecond, and an untouched tree is the one the package author sees.
const MAX_SIBLINGS := 512
# Grouping nodes are named after the parent they were split out of. No node in
# any shipped package starts with this prefix, which is what keeps the name
# index the collision declarations are resolved through unambiguous.
const GROUP_NAME_PREFIX := "WorldGroup_"

# How many frames after a load the cache is packed and written.
#
# Not zero, and not "deferred": writing an entry costs 350-1050 ms on the frame
# it lands on, and deferring by one frame would put that inside the frame that
# draws the region for the first time - exactly the frame the player is waiting
# on. Three frames puts it in the arrival instead, where the transition is
# still resolving and the wait is already expected, and it is paid once per
# region for the life of an install. See `_write_cache` for why none of it can
# go on a worker thread.
const CACHE_WRITE_DELAY_FRAMES := 3
# Compression on the cache file: a slower write for a third of the disk.
#
# Measured on Four Gates, packing once and saving both ways: compressed is
# 32.9 MB, saves in 600 ms and reads in 285; uncompressed is 87.8 MB, saves in
# 74 ms and reads in 136. Across the twelve regions that is 383 MB against
# 1.02 GB, and across all 53 packages a player could visit, roughly 1.2 GB
# against 3.2 GB.
#
# Compressed, because disk is the resource the player did not agree to spend
# and there is no eviction policy to spend it against; the write it pays for is
# one hitch per region per install, and the read it costs is 150 ms on a load
# that is still 40% faster than building the region. Flip this if that trade
# ever reads the other way - nothing else has to change, because an entry
# written either way is read by the same call.
const CACHE_COMPRESS := true

signal load_started(manifest_path: String)
signal load_completed(manifest: WorldManifest)
signal load_failed(errors: Array[String])

var manifest: WorldManifest
var coordinate_adapter: CoordinateAdapter
var world_root: Node3D

## True when the region in the tree was read back from the map cache rather
## than parsed out of its package. Read by the benchmarks and by the tests that
## prove a second visit hits.
var loaded_from_cache := false
## A resident territory can be adopted even when a ferry is discontinuous.
var loaded_by_adoption := false

## What the last load did about the cache, one of `&"disabled"`, `&"miss"`,
## `&"hit"`, `&"unreadable"` or `&"no_digest"`. A miss is the normal state of a
## first visit; `&"unreadable"` means a file was there and did not load, which
## is the only one of the five worth looking into.
var cache_status: StringName = &"disabled"

## The file the last load read or would write. Empty when the package could not
## be hashed or the cache is off.
var cache_file := ""

## The package digest of the region in the tree - the same value the server
## sends in ELORIA_MAP_DIGEST, and the thing the cache key is derived from.
var package_digest := ""

## Microseconds the last load spent in each of its steps, in the order they
## ran, plus `total`. A map load is a handful of long steps over a package the
## client did not author, and which of them a region is paying for is not
## guessable from the outside: Four Gates builds three thousand mesh nodes in
## 88 ms and Amberwood nine thousand in 2.6 s. Reading the clock a dozen times
## costs nothing against a load measured in seconds, so the loader always says
## where it went and `tests/integration/map_load_phases.gd` only has to read it.
var load_phases: Dictionary = {}
var _resource_timings: Dictionary = {}

## Trimesh shapes built during the load in progress, keyed by the mesh they
## were built from, so a mesh a region places hundreds of times is walked once.
## Cleared when the load finishes; the shapes themselves stay alive under the
## bodies that hold them.
var _collision_shapes: Dictionary = {}

# A preloader builds a private tree on one worker. It never enters the active
# SceneTree, writes a disk cache, or mutates the shared digest registry there.
var detached_build := false
var detached_cache_enabled := true
var _prepared_visuals: Dictionary = {}

static func prepare_detached(path: String, cache_enabled: bool, visual_paths := PackedStringArray(), arrival := Vector3.INF) -> WorldLoader:
	var builder := WorldLoader.new()
	builder.detached_build = true
	builder.detached_cache_enabled = cache_enabled
	builder.load_world(path, arrival)
	if builder.world_root != null:
		var start := Time.get_ticks_usec()
		builder._prepared_visuals = GlbSceneCache.prepare(visual_paths)
		builder.load_phases[&"visualPreload"] = Time.get_ticks_usec() - start
		builder.load_phases[&"total"] += builder.load_phases[&"visualPreload"]
	return builder

func release_world(detach := true) -> Dictionary:
	_cache_write_countdown = 0
	_release_snapshot()
	var resident := {"root": world_root, "manifest": manifest,
		"digest": package_digest, "phases": load_phases,
		"from_cache": loaded_from_cache, "cache_status": cache_status,
		"cache_file": cache_file, "visuals": _prepared_visuals,
		"resource_timings": _resource_timings}
	_prepared_visuals = {}
	if detach and is_instance_valid(world_root) and world_root.get_parent() != null:
		world_root.get_parent().remove_child(world_root)
	world_root = null
	manifest = null
	return resident

func adopt_world(resident: Dictionary) -> void:
	unload_world()
	loaded_by_adoption = true
	GlbSceneCache.install_prepared(resident.get("visuals", {}))
	world_root = resident.root as Node3D
	manifest = resident.manifest as WorldManifest
	coordinate_adapter = manifest.coordinate_adapter()
	package_digest = str(resident.digest)
	loaded_from_cache = bool(resident.from_cache)
	cache_status = resident.cache_status
	cache_file = str(resident.cache_file)
	load_phases = resident.phases
	_resource_timings = resident.get("resource_timings", {})
	world_root.transform = Transform3D.IDENTITY
	# An already-resident tree stays attached. Re-entering the SceneTree would
	# destroy and recreate thousands of renderer/physics registrations at the
	# very instant a preloaded crossing is supposed to avoid that work.
	if world_root.get_parent() == null:
		add_child(world_root)
	else:
		# Grounding is queried by load_completed in this same frame. Flush the
		# rebased static bodies before a ray can see their previous map frame.
		for body: Node3D in world_root.find_children("*", "CollisionObject3D", true, false):
			body.force_update_transform()
	MapSceneCache.note_local_digest(manifest.asset_id(), package_digest)
	load_completed.emit(manifest)

func load_world(manifest_path: String, arrival := Vector3.INF, wait_for_arrival := false) -> void:
	unload_world()
	# A standalone streamed territory can start chunk workers below and return
	# before the raw-GLB branch. Complete all global registration first.
	if not GltfQuantization.ensure_registered() or not VramTextures.ensure_registered() \
			or not MapMeshExtension.ensure_registered():
		push_error("world_load stage=gltf_registration requires main-thread initialization")
		load_failed.emit(["gltf_extensions_uninitialized"])
		return
	loaded_by_adoption = false
	var began: int = Time.get_ticks_usec()
	var mark: int = began
	load_phases = {}
	_resource_timings = {}
	print("world_load stage=manifest_open path=", manifest_path)
	load_started.emit(manifest_path)
	manifest = WorldManifest.load_file(manifest_path)
	if not manifest.is_valid():
		push_error("world_load stage=manifest_validate errors=%s" % [manifest.errors])
		load_failed.emit(manifest.errors)
		return
	var resolved_glb_path: String = manifest.glb_path()
	print("world_load stage=manifest_valid asset=", manifest.asset_id(),
		" glb_path=", resolved_glb_path)
	coordinate_adapter = manifest.coordinate_adapter()
	mark = _phase(&"manifest", mark)

	# The package's own bytes, which are both the cache key and the value the
	# server's ELORIA_MAP_DIGEST is checked against. 56-91 ms on an 18-33 MB
	# region, which is the price of the whole contract: an entry that does not
	# match the package on disk is never read, so a client update rebuilds
	# itself with nothing to remember.
	package_digest = MapSceneCache.package_digest(manifest_path, resolved_glb_path)
	if not detached_build:
		MapSceneCache.note_local_digest(manifest.asset_id(), package_digest)
	# The token names the texture formats a package with external images is
	# built with (VramTextures.cache_token); empty, and the key unchanged, for
	# any other package.
	cache_file = MapSceneCache.cache_path(manifest.asset_id(), package_digest,
		VramTextures.cache_token(manifest.data, resolved_glb_path.get_base_dir()) + ArchivedModelPolicy.cache_token())
	mark = _phase(&"digest", mark)
	if manifest.has_streaming_chunks():
		# A partially resident territory must never be packed/read as a complete
		# map cache. Individual independent chunk packages use the normal loader.
		cache_status = &"chunked"
		cache_file = ""
		var chunks := ContinentChunkStream.new()
		chunks.name = "ImportedWorld_" + manifest.asset_id()
		chunks.configure(manifest, detached_cache_enabled if detached_build else MapSceneCache.is_enabled())
		world_root = chunks
		add_child(chunks)
		if not wait_for_arrival:
			if not arrival.is_finite():
				var spawns: Array = manifest.data.get("spawnPoints", [])
				var position: Array = spawns[0].get("position", [0,0,0]) if not spawns.is_empty() else [0,0,0]
				arrival = Vector3(float(position[0]), float(position[1]), float(position[2]))
			chunks.prime(arrival)
		mark = _phase(&"chunks", mark)
		load_phases[&"total"] = mark - began
		load_completed.emit(manifest)
		return
	var external_errors := manifest.verify_external_resources()
	mark = _phase(&"externalVerify", mark)
	if not external_errors.is_empty():
		load_failed.emit(external_errors)
		push_error("world_load stage=external_resources errors=%s" % [external_errors])
		return
	if _load_from_cache(mark, began):
		return

	var document: GLTFDocument = GLTFDocument.new()
	var state: GLTFState = GLTFState.new()
	# The already-registered map image extension prepares the package's
	# external images before the parse uploads them; see vram_textures.gd.
	var image_plan: Dictionary = VramTextures.plan_for(manifest.data)
	if not image_plan.is_empty():
		state.set_additional_data(VramTextures.PLAN_KEY, image_plan)
	var operation_began := Time.get_ticks_usec()
	var error: Error = document.append_from_file(resolved_glb_path, state)
	ResourceDiagnostics.record(_resource_timings, &"gltf_parse", operation_began, true)
	if error != OK:
		push_error("world_load stage=glb_import error=%s path=%s" % [
			error_string(error), resolved_glb_path])
		load_failed.emit(["glb_import_failed: " + error_string(error), resolved_glb_path])
		return
	print_debug("world_load stage=glb_imported path=", resolved_glb_path)
	mark = _phase(&"parse", mark)
	var image_stats: Variant = state.get_additional_data(VramTextures.STATS_KEY)
	if image_stats is Dictionary:
		for counter: String in image_stats:
			load_phases[StringName(counter)] = int(image_stats[counter])
	ExternalTexturePool.share(state, manifest.data.get("externalResources", {}))
	var mipped: int = _build_texture_mipmaps(state)
	print_debug("world_load stage=texture_mipmaps rebuilt=", mipped)
	mark = _phase(&"mipmaps", mark)
	var groups: int = _regroup_wide_siblings(state)
	if groups > 0:
		print_debug("world_load stage=regroup groups=", groups)
	mark = _phase(&"regroup", mark)
	ArchivedModelPolicy.apply_to_gltf_state(state, resolved_glb_path)
	operation_began = Time.get_ticks_usec()
	var generated: Node = document.generate_scene(state)
	ResourceDiagnostics.record(_resource_timings, &"gltf_generate_scene", operation_began, true)
	if generated == null:
		push_error("world_load stage=scene_generate error=null_scene path=%s" % resolved_glb_path)
		load_failed.emit(["glb_scene_generation_failed"])
		return
	world_root = generated as Node3D
	if world_root == null:
		push_error("world_load stage=scene_generate error=root_not_node3d path=%s" % resolved_glb_path)
		load_failed.emit(["glb_scene_root_not_node3d"])
		return
	mark = _phase(&"generateScene", mark)
	# Before anything walks the import: a placement of a shared prototype is a
	# bare node until its pooled mesh is on it, and every pass below expects
	# the MeshInstance3D the package used to carry.
	var prototypes: int = _resolve_shared_meshes(manifest, generated)
	if prototypes > 0:
		print_debug("world_load stage=shared_meshes placements=", prototypes,
			" parsed=", ExternalMeshPool.last_parsed, " shared=", ExternalMeshPool.last_shared)
	load_phases[&"sharedMeshPlacements"] = prototypes
	load_phases[&"sharedMeshParsed"] = ExternalMeshPool.last_parsed
	mark = _phase(&"sharedMeshes", mark)
	world_root.name = "ImportedWorld_" + manifest.asset_id()
	operation_began = Time.get_ticks_usec()
	add_child(world_root)
	ResourceDiagnostics.record(_resource_timings, &"scene_attach", operation_began, true)
	print_debug("world_load stage=scene_attached node=", world_root.name,
		" children=", world_root.get_child_count(), " transform=", world_root.transform)
	mark = _phase(&"attach", mark)
	# One walk of the import, not five. A region imports up to fifteen thousand
	# nodes and every pass below wanted either the mesh instances or a node by
	# name; each of them used to ask the scene tree for its own copy of the
	# list. The passes see exactly the nodes they saw before: the bodies the
	# collision passes add are not MeshInstance3D, so nothing they add belongs
	# in this list, and the batching pass took its list before it created any
	# batch.
	_group_streaming_views()
	var index: Dictionary = _index_import()
	var mesh_instances: Array = index["meshInstances"] as Array
	mark = _phase(&"index", mark)
	_apply_continent_water(mesh_instances)
	_apply_material_passes(mesh_instances)
	_apply_biome_blend(mesh_instances)
	ObjectMaterialRefresh.apply_catalog(manifest.data, mesh_instances)
	mark = _phase(&"materials", mark)
	_apply_collision_declarations(index["byName"] as Dictionary)
	mark = _phase(&"collision", mark)
	_apply_rendered_walk_surfaces(mesh_instances)
	mark = _phase(&"walkSurfaces", mark)
	_apply_navigation_collision()
	_disable_streaming_preview_collision()
	mark = _phase(&"navigation", mark)
	# Must run last: it skips anything that carries collision, so the collision
	# passes above decide what stays an individually culled MeshInstance3D.
	_batch_static_instances(mesh_instances)
	_collision_shapes.clear()
	mark = _phase(&"batching", mark)
	# What the loader produced, before anything else in the client has been
	# handed it. See `_snapshot_for_cache`.
	if cache_status == &"miss" and not detached_build:
		_snapshot_for_cache()
	mark = _phase(&"cacheSnapshot", mark)
	# Look pass (a no-op with ELORIA_LOOK=0): paint the ground and
	# the crowns. After the cache snapshot, so the cache keeps the loader's own
	# materials.
	LookGround.paint_loaded(world_root, manifest)
	LookFoliage.paint_loaded(world_root, manifest)
	GauntletSurfaceContrast.apply(manifest, world_root)
	UndergroundScenery.apply(manifest, world_root)
	mark = _phase(&"lookBinding", mark)
	load_phases[&"total"] = mark - began
	load_completed.emit(manifest)
	if cache_status == &"miss" and not detached_build:
		_cache_write_countdown = CACHE_WRITE_DELAY_FRAMES
		set_process(true)

func ensure_chunk_arrival(position: Vector3) -> bool:
	if not world_root is ContinentChunkStream:
		return false
	return (world_root as ContinentChunkStream).ensure_position(position)

## Called by diagnostics on the owning thread, never to poll or join a worker.
## Engine operation timings overlap phase timings; do not add them together.
func diagnostic_snapshot() -> Dictionary:
	var result := {"cache_status": str(cache_status), "detached": detached_build,
		"load_phases_us": load_phases.duplicate(),
		"timings": ResourceDiagnostics.snapshot(_resource_timings),
		"verification": manifest.verification_diagnostics.duplicate(true) if manifest != null else {},
		"cache_write_pending": _cache_write_countdown > 0,
		"cache_snapshot_nodes": _cache_nodes.size(),
		"prepared_visual_scenes": _prepared_visuals.size()}
	if is_instance_valid(world_root) and world_root is ContinentChunkStream:
		result["chunks"] = (world_root as ContinentChunkStream).diagnostic_snapshot()
	return result

# --------------------------------------------------------------------------
# The map cache
# --------------------------------------------------------------------------

## Frames left before the queued cache write runs, or 0 for none.
var _cache_write_countdown := 0
## The tree the loader itself produced, and the parts of it a consumer is
## allowed to change afterwards. See `_snapshot_for_cache`.
var _cache_nodes: Array[Node] = []
var _cache_visible := PackedByteArray()
var _cache_overrides: Dictionary = {}
## The loader's own `material_override` by node index, for the nodes that had
## one (see `_snapshot_for_cache`).
var _cache_material_overrides: Dictionary = {}

## Reads the region back from the cache, if there is an entry for exactly this
## package and this format version. Returns true when the world is in the tree
## and `load_completed` has been emitted, which is the caller's signal to stop.
##
## Every failure here falls through to the ordinary load. A cache is an
## optimisation; a client that cannot read one still has the package.
func _load_from_cache(mark: int, began: int) -> bool:
	if not (detached_cache_enabled if detached_build else MapSceneCache.is_enabled()):
		cache_status = &"disabled"
		return false
	if cache_file.is_empty():
		# The package could not be hashed, so it cannot be keyed either.
		cache_status = &"no_digest"
		return false
	if not FileAccess.file_exists(cache_file):
		cache_status = &"miss"
		return false
	# IGNORE_DEEP so a second load in one session builds its own meshes and
	# materials rather than handing back the ones the last load is still
	# holding. That is what a fresh load does, and the point of the cache is to
	# be indistinguishable from one.
	var operation_began := Time.get_ticks_usec()
	var packed: PackedScene = ResourceLoader.load(
		cache_file, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	ResourceDiagnostics.record(_resource_timings, &"cache_read", operation_began, true)
	mark = _phase(&"cacheRead", mark)
	if packed == null:
		push_warning("map cache: %s did not load; rebuilding" % cache_file)
		DirAccess.remove_absolute(cache_file)
		cache_status = &"unreadable"
		return false
	operation_began = Time.get_ticks_usec()
	var restored: Node3D = packed.instantiate() as Node3D
	ResourceDiagnostics.record(_resource_timings, &"cache_instantiate", operation_began, true)
	if restored == null:
		push_warning("map cache: %s is not a Node3D; rebuilding" % cache_file)
		DirAccess.remove_absolute(cache_file)
		cache_status = &"unreadable"
		return false
	world_root = restored
	world_root.name = "ImportedWorld_" + manifest.asset_id()
	operation_began = Time.get_ticks_usec()
	add_child(world_root)
	ResourceDiagnostics.record(_resource_timings, &"scene_attach", operation_began, true)
	mark = _phase(&"cacheInstantiate", mark)
	var relinked: int = _resolve_batch_links()
	mark = _phase(&"cacheLinks", mark)
	loaded_from_cache = true
	cache_status = &"hit"
	print_debug("world_load stage=cache_hit file=", cache_file,
		" batches_relinked=", relinked)
	# Look pass (not with ELORIA_LOOK=0): paint the ground and the crowns, as a
	# fresh load does.
	LookGround.paint_loaded(world_root, manifest)
	LookFoliage.paint_loaded(world_root, manifest)
	GauntletSurfaceContrast.apply(manifest, world_root)
	UndergroundScenery.apply(manifest, world_root)
	mark = _phase(&"lookBinding", mark)
	load_phases[&"total"] = mark - began
	load_completed.emit(manifest)
	return true

## Turns every batch link back from a path into the MultiMeshInstance3D it
## names, and returns how many it resolved.
##
## Runs after a cache load, where the object half of the link did not survive
## the round trip. Harmless on a freshly parsed tree, where it re-resolves the
## links to the same nodes they already point at.
func _resolve_batch_links() -> int:
	var resolved := 0
	for node: Node in world_root.find_children("*", "MeshInstance3D", true, false):
		if not node.has_meta(BATCH_PATH_META):
			continue
		var path: NodePath = node.get_meta(BATCH_PATH_META) as NodePath
		var batch: MultiMeshInstance3D = world_root.get_node_or_null(
			path) as MultiMeshInstance3D
		if batch == null:
			# The batch it names is gone, so the mesh is drawing itself again.
			node.remove_meta(BATCH_PATH_META)
			if node.has_meta(BATCH_META):
				node.remove_meta(BATCH_META)
			node.visible = true
			push_warning("map cache: batch %s missing for %s" % [path, node.name])
			continue
		node.set_meta(BATCH_META, batch)
		resolved += 1
	return resolved


## Gives every placement of a shared prototype the mesh it names.
##
## `shared_meshes.py` publishes a mesh that repeats across map files once, as
## `maps/_shared/meshes/<identity>.glb`, and leaves the placement as a node
## with its old name and transform carrying `extras.eloria.prototype`
## (stamped onto the node as meta by `map_mesh_extension.gd`). Here each marked
## node becomes the MeshInstance3D the package used to hold, drawing the pooled
## mesh.
##
## The name is the contract - `collision.nodeNames`, the navigation surface
## prefixes, the water and object-material passes, the look pass and the cache
## snapshot all key on it - so the replacement keeps the name, the transform,
## the visibility, the children and the sibling order of the node it replaces.
##
## Runs before `_index_import`, so every pass below sees the tree a package
## without prototypes would have produced.
func _resolve_shared_meshes(package: WorldManifest, root: Node) -> int:
	ExternalMeshPool.reset_counters()
	if package == null or root == null:
		return 0
	var declared: Variant = package.data.get("externalMeshes", {})
	if not declared is Dictionary or (declared as Dictionary).is_empty():
		return 0
	# The manifest keys by URI and records the file's sha256 (the packager
	# checks that); the placement names the prototype's identity, which is the
	# file's stem, so the lookup is by stem.
	var base: String = package.source_path.get_base_dir()
	var paths: Dictionary = {}
	for uri: String in (declared as Dictionary):
		paths[uri.get_file().get_basename()] = base.path_join(uri).simplify_path()
	var placed := 0
	var missing: Dictionary = {}
	var pending: Array[Node] = [root]
	var marked: Array[Node] = []
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		for child: Node in node.get_children():
			pending.append(child)
		if node.has_meta(ExternalMeshPool.POOLED_META):
			marked.append(node)
	for node: Node in marked:
		var key := str(node.get_meta(ExternalMeshPool.POOLED_META))
		if ArchivedModelPolicy.is_retired_prototype(key):
			node.set_meta("retired_model", true)
			continue
		var path: Variant = paths.get(key)
		if path == null:
			missing[key] = true
			continue
		var mesh: Mesh = ExternalMeshPool.acquire(key, str(path))
		if mesh == null:
			missing[key] = true
			continue
		var source := node as Node3D
		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		# A pooled mesh is drawn by every placement in every resident chunk, so
		# the passes that would write to a mesh or its materials must override
		# per instance instead. This meta is how they tell.
		instance.set_meta(ExternalMeshPool.POOLED_META, key)
		if source != null:
			instance.transform = source.transform
			instance.visible = source.visible
		var parent: Node = node.get_parent()
		var at: int = node.get_index()
		var name: StringName = node.name
		for child: Node in node.get_children():
			node.remove_child(child)
			instance.add_child(child)
		if parent != null:
			parent.remove_child(node)
		_dispose_import_node(node)
		instance.name = name
		if parent != null:
			parent.add_child(instance)
			parent.move_child(instance, at)
		placed += 1
	if not missing.is_empty():
		push_error("world_load stage=shared_meshes unresolved=%d first=%s manifest=%s" % [
			missing.size(), str(missing.keys()[0]), package.source_path])
	return placed

## A detached import belongs to one builder until its worker returns. Removing
## a node outside SceneTree does not clear its owner in Godot; queue_free()
## would let the main thread erase that owner's list while this worker is still
## replacing siblings/reparenting children. Finish private destruction here.
## Ordinary live/main-thread loading retains its deferred deletion behavior.
func _dispose_import_node(node: Node) -> void:
	if detached_build and not node.is_inside_tree():
		node.free()
	else:
		node.queue_free()

## What the loader produced, taken while the tree is still only the loader's.
##
## The cache has to hold the region as the loader built it, and by the time the
## write runs the rest of the client has had the tree for three frames: the
## interior cutaway may have hidden a wall the camera is looking through, the
## secret sections may have hidden a section, and the occluder fade may have
## swapped a translucent material onto whatever is between the camera and the
## player. Baking any of those in would make the cached region quietly
## different from a fresh one - a rock that is permanently glass.
##
## So the things a consumer can change are recorded here, while nothing but
## the loader has touched the tree, and put back for the length of the pack:
## visibility, surface overrides, and whole-mesh overrides. The last is the
## look pass's (a painted crown or a kept colour goes onto a static batch's
## `material_override`, which has no surfaces), and baked in, a client with
## the look switched off read painted batches back out of a cache written with
## it on. Nodes a consumer *adds* need no handling: `PackedScene.pack` only
## stores nodes owned by the packed root, the owners are set from this list,
## and anything not in it is left out for free.
func _snapshot_for_cache() -> void:
	_cache_nodes = world_root.find_children("*", "", true, false)
	var count: int = _cache_nodes.size()
	_cache_visible.resize(count)
	_cache_overrides.clear()
	_cache_material_overrides.clear()
	for index: int in count:
		var node: Node = _cache_nodes[index]
		var spatial: Node3D = node as Node3D
		_cache_visible[index] = 1 if spatial == null or spatial.visible else 0
		var geometry: GeometryInstance3D = node as GeometryInstance3D
		if geometry != null and geometry.material_override != null:
			_cache_material_overrides[index] = geometry.material_override
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		if mesh_instance == null:
			continue
		var overrides: Array[Material] = []
		var any := false
		for surface: int in mesh_instance.get_surface_override_material_count():
			var material: Material = mesh_instance.get_surface_override_material(surface)
			overrides.append(material)
			any = any or material != null
		if any:
			_cache_overrides[index] = overrides

func _release_snapshot() -> void:
	_cache_nodes.clear()
	_cache_material_overrides.clear()
	_cache_visible.resize(0)
	_cache_overrides.clear()

func _process(_delta: float) -> void:
	if _cache_write_countdown <= 0:
		set_process(false)
		return
	_cache_write_countdown -= 1
	if _cache_write_countdown > 0:
		return
	set_process(false)
	_write_cache()

## Packs the region and writes it, three frames after the load.
##
## Both halves are on the main thread, and the second half is not by choice.
##
## The pack has to be: it reads the scene tree. The save was on a worker
## `Thread` first, because it is the larger half and appears to touch nothing
## but the `PackedScene` - and it worked, until the client was asked to quit
## while one was in flight. `ResourceSaver.save` of a scene full of imported
## `ArrayMesh`es reaches the rendering server to get their surface arrays back,
## and off the main thread that is a synchronous request the main thread has to
## serve. At shutdown the main thread stops serving, the worker never returns,
## and `wait_to_finish()` waits for it forever: a client that will not close.
## Measured, not deduced - `Godot --script` on a probe that loads a region and
## quits five frames later hangs every time, with the worker stopped inside
## `ResourceSaver.save`.
##
## So it is done here, and it is a real cost: 350-1050 ms on the frame it lands
## on, once per region for the life of an install. Three frames after
## `load_completed` is chosen to put it inside the arrival - the player is
## already waiting, the transition is still resolving - rather than under their
## feet a minute later. `CACHE_COMPRESS` is the dial if that is the wrong
## trade: uncompressed saves in about an eighth of the time and takes 2.7x the
## disk.
func _write_cache() -> void:
	if not is_instance_valid(world_root) or cache_file.is_empty():
		_release_snapshot()
		return
	if not MapSceneCache.ensure_directory():
		_release_snapshot()
		return
	var began: int = Time.get_ticks_usec()
	var undo: Array = _restore_pristine()
	for node: Node in _cache_nodes:
		if is_instance_valid(node):
			node.owner = world_root
	var packed := PackedScene.new()
	var operation_began := Time.get_ticks_usec()
	var error: Error = packed.pack(world_root)
	ResourceDiagnostics.record(_resource_timings, &"cache_pack", operation_began, true)
	_undo_pristine(undo)
	load_phases[&"cachePack"] = Time.get_ticks_usec() - began
	_release_snapshot()
	if error != OK:
		push_warning("map cache: pack failed for %s (%s)" % [
			cache_file, error_string(error)])
		return
	_save_entry(packed, cache_file,
		manifest.asset_id() if manifest != null else "")

## Writes the packed region.
##
## The file lands under a temporary name and is renamed into place, so a write
## that does not finish - the disk fills, the process is killed - leaves no
## half a region for the next launch to read as a whole one.
func _save_entry(packed: PackedScene, path: String, map_id: String) -> void:
	var began: int = Time.get_ticks_usec()
	var staging: String = MapSceneCache.staging_path(path)
	var flags: int = ResourceSaver.FLAG_COMPRESS if CACHE_COMPRESS else 0
	var operation_began := Time.get_ticks_usec()
	var error: Error = ResourceSaver.save(packed, staging, flags)
	ResourceDiagnostics.record(_resource_timings, &"cache_save", operation_began, true)
	if error != OK:
		push_warning("map cache: save failed for %s (%s)" % [path, error_string(error)])
		DirAccess.remove_absolute(staging)
		return
	DirAccess.remove_absolute(path)
	error = DirAccess.rename_absolute(staging, path)
	if error != OK:
		push_warning("map cache: could not place %s (%s)" % [path, error_string(error)])
		DirAccess.remove_absolute(staging)
		return
	var pruned: int = MapSceneCache.prune(map_id, path)
	load_phases[&"cacheSave"] = Time.get_ticks_usec() - began
	print("world_load stage=cache_written file=", path, " milliseconds=",
		(Time.get_ticks_usec() - began) / 1000, " stale_removed=", pruned)

## Puts back what the loader left, and returns what to undo afterwards.
func _restore_pristine() -> Array:
	var undo: Array = []
	for index: int in _cache_nodes.size():
		var node: Node = _cache_nodes[index]
		if not is_instance_valid(node):
			continue
		var spatial: Node3D = node as Node3D
		if spatial != null:
			var wanted: bool = _cache_visible[index] == 1
			if spatial.visible != wanted:
				undo.append([spatial, "visible", spatial.visible])
				spatial.visible = wanted
		var geometry: GeometryInstance3D = node as GeometryInstance3D
		if geometry != null:
			var own_override: Material = _cache_material_overrides.get(index) as Material
			if geometry.material_override != own_override:
				undo.append([geometry, "material_override", geometry.material_override])
				geometry.material_override = own_override
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		if mesh_instance == null:
			continue
		var wanted_overrides: Variant = _cache_overrides.get(index)
		for surface: int in mesh_instance.get_surface_override_material_count():
			var current: Material = mesh_instance.get_surface_override_material(surface)
			var pristine: Material = null
			if wanted_overrides is Array and surface < (wanted_overrides as Array).size():
				pristine = (wanted_overrides as Array)[surface] as Material
			if current == pristine:
				continue
			undo.append([mesh_instance, surface, current])
			mesh_instance.set_surface_override_material(surface, pristine)
	return undo

func _undo_pristine(undo: Array) -> void:
	for entry_value: Variant in undo:
		var entry: Array = entry_value as Array
		var node: Node = entry[0] as Node
		if not is_instance_valid(node):
			continue
		if entry[1] is String and str(entry[1]) == "material_override":
			(node as GeometryInstance3D).material_override = entry[2] as Material
		elif entry[1] is String:
			(node as Node3D).visible = bool(entry[2])
		else:
			(node as MeshInstance3D).set_surface_override_material(
				int(entry[1]), entry[2] as Material)

## Records the microseconds since `started` under `name` and returns the clock
## reading that closed it, which is the next phase's start.
func _phase(name: StringName, started: int) -> int:
	var now: int = Time.get_ticks_usec()
	load_phases[name] = now - started
	return now

## Splits every sibling list wider than `MAX_SIBLINGS` under empty grouping
## nodes, so Godot's scene builder never pays its quadratic name check on one.
## Returns how many groups were added. See MAX_SIBLINGS for what this is worth.
##
## Runs on the parsed glTF rather than on the built tree, because the cost is
## in the building: by the time there are nodes to reparent it has been paid.
##
## Packages that carry a skin or a skeleton are left alone. Godot decides where
## a Skeleton3D goes from the joints' place among their siblings, and a rig is
## small enough that it would never be split anyway; skipping the whole package
## is a cheaper promise to keep than a rule about which lists may be split.
func _regroup_wide_siblings(state: GLTFState) -> int:
	var rendering: Dictionary = _rendering_settings()
	if not bool(rendering.get("regroupWideSiblings", true)):
		return 0
	if not state.get_skins().is_empty() or not state.get_skeletons().is_empty():
		return 0
	var limit: int = maxi(16, int(rendering.get("maxSiblings", MAX_SIBLINGS)))
	var nodes: Array = state.get_nodes()
	# Only the nodes the package brought: the groups appended below are built
	# narrow, so revisiting them would find nothing to do.
	var parsed: int = nodes.size()
	var added := 0
	# The scene root Godot generates is a parent too, and a package whose nodes
	# are all roots - Sunmane Steppe's thousand props are - hangs every one of
	# them off it.
	var roots: PackedInt32Array = state.root_nodes
	if roots.size() > limit:
		var root_groups: PackedInt32Array = _bucket_siblings(nodes, roots, -1)
		state.root_nodes = root_groups
		added += root_groups.size()
	for index: int in range(parsed):
		var node: GLTFNode = nodes[index] as GLTFNode
		if node == null:
			continue
		var children: PackedInt32Array = node.get_children()
		if children.size() <= limit:
			continue
		var groups: PackedInt32Array = _bucket_siblings(nodes, children, index)
		node.set_children(groups)
		added += groups.size()
	if added > 0:
		state.set_nodes(nodes)
	return added

## Splits `children` into buckets of about sqrt(n), appends a grouping node per
## bucket to `nodes`, and returns the indices of those groups.
##
## sqrt is where the two costs meet: smaller buckets leave the groups
## themselves a wide sibling list, larger ones leave the buckets wide, and the
## builder pays the same quadratic on either. 7 935 children become 90 groups
## of 90.
func _bucket_siblings(nodes: Array, children: PackedInt32Array,
		parent: int) -> PackedInt32Array:
	var bucket: int = maxi(1, int(ceil(sqrt(float(children.size())))))
	var groups := PackedInt32Array()
	var cursor := 0
	while cursor < children.size():
		var group := GLTFNode.new()
		group.set_name("%s%d_%d" % [GROUP_NAME_PREFIX, parent + 1, groups.size()])
		group.parent = parent
		var slice := PackedInt32Array()
		var stop: int = mini(cursor + bucket, children.size())
		while cursor < stop:
			slice.append(children[cursor])
			cursor += 1
		group.set_children(slice)
		nodes.append(group)
		var group_index: int = nodes.size() - 1
		for child_index: int in slice:
			(nodes[child_index] as GLTFNode).parent = group_index
		groups.append(group_index)
	return groups

## The map's `rendering` block, or an empty one. Both the batching and the
## regrouping are per-map switches a package can turn off.
func _rendering_settings() -> Dictionary:
	if manifest == null:
		return {}
	var value: Variant = manifest.data.get("rendering", {})
	return value as Dictionary if value is Dictionary else {}

## The import's mesh instances, and the first node of each name. Both lists the
## load passes need, taken in a single traversal.
func _index_import() -> Dictionary:
	var mesh_instances: Array = []
	var by_name: Dictionary = {}
	for node: Node in world_root.find_children("*", "", true, false):
		if not by_name.has(node.name):
			by_name[node.name] = node
		if node is MeshInstance3D:
			mesh_instances.append(node)
	return {"meshInstances": mesh_instances, "byName": by_name}

## GLTFDocument builds its textures at runtime with no mip chain, so every
## roof and every stretch of ground aliased against the pixel grid and swam as
## the camera moved. The images the state carries are the same objects the
## generated materials will reference, so rebuilding them here reaches the
## whole map. Must run before generate_scene().
##
## Images the map image extension produced (VramTextures.DONE_KEY) already
## have their chain and are skipped without reading them back from the GPU.
func _build_texture_mipmaps(state: GLTFState) -> int:
	var rebuilt := 0
	var done_value: Variant = state.get_additional_data(VramTextures.DONE_KEY)
	var done: Dictionary = done_value if done_value is Dictionary else {}
	var images: Array[Texture2D] = state.get_images()
	for index: int in images.size():
		if done.has(index):
			continue
		var texture: ImageTexture = images[index] as ImageTexture
		if texture == null:
			continue
		var image: Image = texture.get_image()
		if image == null or image.is_empty() or image.has_mipmaps():
			continue
		if image.is_compressed() and image.decompress() != OK:
			continue
		image.generate_mipmaps()
		texture.set_image(image)
		rebuilt += 1
	return rebuilt

## The two material passes a freshly imported map needs, over one list of its
## mesh instances. Each is described below; a material is touched once by
## either, whichever instance reaches it first.
##
## Anisotropic sampling: a mip chain on its own blurs ground seen at a grazing
## angle, which is most of an isometric view. Anisotropic sampling is what
## keeps the far end of a road readable rather than smeared.
##
## Vertex coverage: a ground class is cut against its neighbour by an alpha
## test on the coverage the map stores in COLOR_0's alpha, which is what lets a
## diagonal road read as a diagonal instead of a flight of steps the width of a
## terrain cell. Godot's glTF importer brings the colours in and sets the alpha
## mode, but leaves `vertex_color_use_as_albedo` off, and without it the vertex
## alpha never reaches the shader and every class draws over its whole quad.
##
## Legacy coverage colours are white apart from alpha. The shared continent
## also stores opaque biome and worn-road RGB in COLOR_0; those materials use
## the same flag. Transparent water retains its authored material behaviour.
##
## Returns how many materials the coverage flag reached.
func _apply_continent_water(mesh_instances: Array) -> int:
	if manifest == null or not manifest.data.has("continentGeography"):
		return 0
	# Islands with ferry-only connections still belong to the same sea. Their
	# canonical placement must not depend on having a walking-border record.
	var translation: Array = manifest.data.continentGeography.get("translation", [])
	if translation.size() != 3:
		var borders: Array = manifest.data.get("streamingBorders", [])
		if not borders.is_empty():
			translation = borders[0].get("globalTranslation", [])
	if translation.size() != 3:
		return 0
	var origin := Vector3(float(translation[0]), float(translation[1]), float(translation[2]))
	var shared_drainage := str(manifest.data.continentGeography.get("geometryMode", "")) == "continent-chunks-v1"
	var territory := manifest.asset_id().get_slice("__chunk_", 0)
	# Shared pixels are exported unchanged from the toolkit's water_lake.
	# Loading the PNG directly also works without an editor import or a local
	# water_lake material (Grey Moors only packages its regional bog material).
	var wave_texture := preload("res://src/world/external_texture_pool.gd").load_image(
		"res://assets/world/continent-water.png")
	var applied := 0
	for value: Variant in mesh_instances:
		var node := value as MeshInstance3D
		if node.mesh == null or not str(node.name).begins_with("Water_"):
			continue
		var local := node.transform
		var parent := node.get_parent()
		while parent != world_root and parent is Node3D:
			local = (parent as Node3D).transform * local
			parent = parent.get_parent()
		var to_continent := Transform3D(Basis.IDENTITY, origin) * local
		var bounds := to_continent * node.mesh.get_aabb()
		if shared_drainage:
			# The global terrain exporter names both sea and elevated/sloping
			# drainage Water_<territory>_<cellX>_<cellZ>, with water_sea material.
			# Require both declarations so retained fountains and authored pools
			# keep their own material even when their world height is zero.
			var prefix := "Water_" + territory + "_"
			if not str(node.name).begins_with(prefix):
				continue
			var cell := str(node.name).trim_prefix(prefix).split("_", false)
			if cell.size() != 2 or not cell[0].is_valid_int() or not cell[1].is_valid_int():
				continue
		else:
			# Preserve the sea-only rule for legacy territory exports.
			if absf(bounds.position.y) > .06 or absf(bounds.end.y) > .06:
				continue
		for surface: int in node.mesh.get_surface_count():
			var original := node.mesh.surface_get_material(surface) as BaseMaterial3D
			if original == null:
				continue
			if shared_drainage and original.resource_name != "water_sea":
				continue
			var water := ShaderMaterial.new()
			water.resource_name = "continent_sea"
			water.shader = preload("res://src/world/continent_water.gdshader")
			water.set_shader_parameter("water_to_continent", to_continent)
			water.set_shader_parameter("wave_texture", wave_texture)
			water.set_shader_parameter("has_wave_texture", wave_texture != null)
			node.set_surface_override_material(surface, water)
			applied += 1
	return applied


func _apply_material_passes(mesh_instances: Array) -> int:
	var applied := 0
	var continent_colors := manifest != null and str(manifest.data.get("continentGeography", {}).get(
		"geometryMode", "")) == "continent-chunks-v1"
	var filtered: Dictionary = {}
	var covered: Dictionary = {}
	var soft_materials: Dictionary = {}
	for node_value: Variant in mesh_instances:
		var mesh: Mesh = (node_value as MeshInstance3D).mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var material: BaseMaterial3D = mesh.surface_get_material(
				surface) as BaseMaterial3D
			if material == null:
				continue
			var id: int = material.get_instance_id()
			if not filtered.has(id):
				filtered[id] = true
				material.texture_filter = (
					BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC)
			if (mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) == 0:
				continue
			# Optional lowland overlays retain opaque depth and framebuffer alpha.
			if material.resource_name.ends_with("_soft_ground"):
				if not soft_materials.has(id):
					var soft := ShaderMaterial.new()
					soft.resource_name = material.resource_name
					soft.shader = preload("res://src/world/soft_ground.gdshader")
					soft.set_shader_parameter("soil_texture", material.albedo_texture)
					soft.set_shader_parameter("soil_color", material.albedo_color)
					soft.set_shader_parameter("soil_roughness", material.roughness)
					soft.set_shader_parameter("soil_normal", material.normal_texture)
					soft.set_shader_parameter("soil_normal_depth", material.normal_scale)
					soft.set_shader_parameter("has_soil_normal", material.normal_enabled and material.normal_texture != null)
					soft_materials[id] = soft
					applied += 1
				# A pooled prototype's mesh is shared with every other chunk
				# that places it, so it is overridden per instance, never
				# written to (external_mesh_pool.gd).
				if ExternalMeshPool.is_pooled(node_value as Node):
					(node_value as MeshInstance3D).set_surface_override_material(
						surface, soft_materials[id])
				else:
					mesh.surface_set_material(surface, soft_materials[id])
				continue
			if covered.has(id):
				continue
			if material.transparency != BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR and not (
				continent_colors and material.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED):
				continue
			covered[id] = true
			# The shared continent stores biome and worn-road RGB in opaque
			# COLOR_0. glTF import otherwise leaves those colours disabled.
			material.vertex_color_use_as_albedo = true
			applied += 1
	return applied


## Restores the shared world-space biome material after glTF import. Only the
## explicitly named base terrain receives it; roads, local ground overlays,
## water, and authored objects retain their own materials. Invalid portable
## resources leave the exported dominant PBR fallback untouched.
func _apply_biome_blend(mesh_instances: Array) -> int:
	if manifest == null:
		return 0
	var config: Variant
	if manifest.data.has("biomeBlend"):
		config = manifest.data.get("biomeBlend")
		# Presence is current export authority. Null or an explicit disabled
		# sentinel prevents an older portable catalog from resurrecting a blend
		# the author turned off. Malformed present data also fails closed.
		if config == null or (config is Dictionary and not bool(config.get(
				"enabled", true))):
			return 0
		if not config is Dictionary:
			push_warning("Child biome blend is invalid; the exported terrain material remains active.")
			return 0
	else:
		config = BiomeBlendMaterial.catalog_config(manifest.data)
	if not config is Dictionary:
		return 0
	var raw_translation: Variant = manifest.data.get("continentGeography", {}).get(
		"translation", [0.0, 0.0, 0.0])
	if not raw_translation is Array or raw_translation.size() != 3:
		return 0
	var translation := Vector3(float(raw_translation[0]), float(raw_translation[1]),
		float(raw_translation[2]))
	var material := BiomeBlendMaterial.create_runtime(config, translation)
	if material == null:
		push_warning("Biome blend was not applied; the exported terrain material remains active.")
		return 0
	var applied := 0
	for value: Variant in mesh_instances:
		var node := value as MeshInstance3D
		if node == null or node.mesh == null or not _is_authored_base_terrain(
				node.name, config.palettes):
			continue
		var local := node.transform
		var parent := node.get_parent()
		while parent != world_root and parent is Node3D:
			local = (parent as Node3D).transform * local
			parent = parent.get_parent()
		var node_material := material.duplicate(true) as ShaderMaterial
		BiomeBlendMaterial.set_terrain_to_continent(node_material,
			Transform3D(Basis.IDENTITY, translation) * local)
		for surface in node.mesh.get_surface_count():
			node.set_surface_override_material(surface, node_material)
			applied += 1
	return applied


static func _is_authored_base_terrain(node_name: StringName,
		palettes: Array) -> bool:
	var text := String(node_name)
	for palette: Dictionary in palettes:
		var palette_id := String(palette.get("id", ""))
		var region_id := palette_id.get_slice(":", 0)
		if region_id.is_empty():
			continue
		var expected := "AuthoredGround_%sBase" % region_id
		if text == expected or text.begins_with(expected + "_"):
			return true
	return false

func unload_world() -> void:
	# A map change while a cache write is still queued drops the write: the
	# tree it would pack is about to be freed, and the region will be built
	# again the next time it is entered, which is the state it was in before.
	_cache_write_countdown = 0
	set_process(false)
	_release_snapshot()
	if is_instance_valid(world_root):
		_dispose_import_node(world_root)
	world_root = null
	loaded_from_cache = false
	cache_status = &"disabled"
	cache_file = ""
	package_digest = ""
	_collision_shapes.clear()
	manifest = null
	coordinate_adapter = null

func _apply_collision_declarations(by_name: Dictionary) -> void:
	var collision: Dictionary = manifest.data.get("collision", {})
	var declared: Array = collision.get("nodeNames", [])
	if declared.is_empty():
		return
	# A map may declare collision on the geometry the player sees, or on separate
	# proxy boxes tucked inside it. A proxy is a physics volume, never a surface:
	# drawn, it sits millimetres inside the wall it stands for and the two fight
	# for the same pixels. The shape is still built from the proxy's mesh, and
	# CollisionShape3D is not a VisualInstance3D, so hiding the node it hangs off
	# costs nothing in physics.
	var proxies: bool = bool(collision.get("nodesAreProxies", false))
	# `by_name` is the index taken by the single walk in load_world: one walk of
	# a 15 000-node import instead of one walk per declared name.
	for node_name in declared:
		var node: Node = by_name.get(str(node_name)) as Node
		if node is MeshInstance3D:
			_create_static_collision(node as MeshInstance3D)
			if proxies:
				(node as MeshInstance3D).visible = false
		elif node == null:
			manifest.warnings.append("collision node not found: " + str(node_name))

func _apply_navigation_collision() -> void:
	var navigation: Dictionary = manifest.data.get("navigation", {})
	var navmesh_value: Variant = navigation.get("navmesh", {})
	if not navmesh_value is Dictionary:
		return
	var navmesh: Dictionary = navmesh_value as Dictionary
	var polygons_value: Variant = navmesh.get("polygons", [])
	if not polygons_value is Array:
		return
	var body: StaticBody3D = StaticBody3D.new()
	body.name = "NavigationSurfaceCollision"
	# Keep walk surfaces separate from gates, bridges, and other authored
	# collision. Actor grounding and MOVE_TO picking must never snap to the top
	# of structural collision merely because it is the first ray hit.
	body.collision_layer = NAVIGATION_SURFACE_LAYER
	body.collision_mask = 0
	for polygon_value: Variant in polygons_value as Array:
		if not polygon_value is Dictionary:
			continue
		var polygon: Dictionary = polygon_value as Dictionary
		var vertices_value: Variant = polygon.get("vertices", [])
		if not vertices_value is Array:
			continue
		var raw_vertices: Array = vertices_value as Array
		if raw_vertices.size() < 3:
			continue
		var vertices: Array[Vector3] = []
		for raw_vertex: Variant in raw_vertices:
			if raw_vertex is Array and (raw_vertex as Array).size() >= 3:
				var values: Array = raw_vertex as Array
				vertices.append(Vector3(float(values[0]), float(values[1]), float(values[2])))
		if vertices.size() < 3:
			continue
		var faces: PackedVector3Array = PackedVector3Array()
		for index: int in range(1, vertices.size() - 1):
			faces.append(vertices[0])
			faces.append(vertices[index])
			faces.append(vertices[index + 1])
		var shape: ConcavePolygonShape3D = ConcavePolygonShape3D.new()
		var operation_began := Time.get_ticks_usec()
		shape.set_faces(faces)
		ResourceDiagnostics.record(_resource_timings, &"navigation_shape_set_faces", operation_began, true)
		var collision: CollisionShape3D = CollisionShape3D.new()
		collision.name = "Nav_" + str(polygon.get("id", body.get_child_count()))
		collision.shape = shape
		body.add_child(collision)
	if body.get_child_count() == 0:
		_dispose_import_node(body)
		manifest.warnings.append("navigation polygons did not produce collision")
		return
	world_root.add_child(body)

func _batch_static_instances(mesh_instances: Array) -> void:
	var rendering: Dictionary = _rendering_settings()
	if not bool(rendering.get("batchStaticInstances", true)):
		return
	var minimum: int = maxi(2, int(rendering.get("batchMinimumInstances",
		BATCH_MINIMUM_INSTANCES)))
	var cell_size: float = maxf(1.0, float(rendering.get("batchCellMetres",
		BATCH_CELL_METRES)))
	var groups: Dictionary = {}
	for node_value: Variant in mesh_instances:
		var mesh_instance: MeshInstance3D = node_value as MeshInstance3D
		if not _is_batchable(mesh_instance):
			continue
		var origin: Vector3 = _import_transform(mesh_instance).origin
		var key: String = "%d|%d|%d|%d|%d|%d|%d" % [
			mesh_instance.mesh.get_instance_id(), mesh_instance.layers,
			mesh_instance.cast_shadow, mesh_instance.gi_mode,
			floori(origin.x / cell_size), floori(origin.y / cell_size),
			floori(origin.z / cell_size)]
		if not groups.has(key):
			groups[key] = []
		(groups[key] as Array).append(mesh_instance)
	var batches: int = 0
	var collapsed: int = 0
	for key_value: Variant in groups:
		var members: Array = groups[key_value] as Array
		if members.size() < minimum:
			continue
		_create_batch(members, batches)
		batches += 1
		collapsed += members.size()
	if batches > 0:
		print_debug("world_load stage=static_batching batches=", batches,
			" instances=", collapsed)

func _is_batchable(mesh_instance: MeshInstance3D) -> bool:
	var ancestor: Node = mesh_instance
	while ancestor != null and ancestor != world_root:
		if str(ancestor.name).begins_with("StreamPreview_") or ancestor.has_meta("stream_borders"):
			return false
		ancestor = ancestor.get_parent()
	var mesh: Mesh = mesh_instance.mesh
	if mesh == null or mesh.get_surface_count() == 0:
		return false
	# Anything that carries collision, an animation target, a skin or an author
	# override keeps its own node so lookups, physics and skinning are untouched.
	if mesh_instance.get_child_count() > 0:
		return false
	if mesh_instance.skin != null or not mesh_instance.skeleton.is_empty():
		return false
	if mesh_instance.material_override != null or mesh_instance.material_overlay != null:
		return false
	if not mesh_instance.visible or (not detached_build and not mesh_instance.is_visible_in_tree()):
		return false
	if mesh_instance.visibility_range_end > 0.0:
		return false
	for surface: int in mesh_instance.get_surface_override_material_count():
		# MultiMeshInstance3D has no per-surface overrides to carry these onto.
		if mesh_instance.get_surface_override_material(surface) != null:
			return false
	for surface: int in mesh.get_surface_count():
		var material: Material = mesh.surface_get_material(surface)
		if material == null:
			continue
		if material is not BaseMaterial3D:
			return false
		# Blended surfaces are sorted per instance; batching them would change
		# the draw order and therefore the picture.
		if (material as BaseMaterial3D).transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			return false
	return true

func _create_batch(members: Array, index: int) -> void:
	var reference: MeshInstance3D = members[0] as MeshInstance3D
	var multimesh: MultiMesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = reference.mesh
	multimesh.instance_count = members.size()
	var batch: MultiMeshInstance3D = MultiMeshInstance3D.new()
	batch.name = "StaticBatch_%d_%s" % [index, reference.name]
	batch.multimesh = multimesh
	batch.layers = reference.layers
	batch.cast_shadow = reference.cast_shadow
	batch.gi_mode = reference.gi_mode
	var parent := world_root.get_node_or_null("StreamActive")
	(parent if parent != null else world_root).add_child(batch)
	batch.transform = Transform3D.IDENTITY
	# Taken after add_child, which is what settles the name: a package that
	# already carries a node called StaticBatch_0_Rock would have had this one
	# renamed, and a path written before that would point at the wrong node.
	var batch_path: NodePath = world_root.get_path_to(batch)
	for member_index: int in members.size():
		var member: MeshInstance3D = members[member_index] as MeshInstance3D
		multimesh.set_instance_transform(member_index, _import_transform(member))
		# The source node stays in the tree so name lookups, manifest
		# declarations and tooling keep resolving; it simply stops drawing.
		member.visible = false
		member.set_meta(BATCH_META, batch)
		member.set_meta(BATCH_PATH_META, batch_path)
		member.set_meta(BATCH_INDEX_META, member_index)

func _import_transform(node: Node3D) -> Transform3D:
	# Local to the imported root; global_transform needs an active SceneTree.
	var result := node.transform
	var parent := node.get_parent() as Node3D
	while parent != null and parent != world_root:
		result = parent.transform * result
		parent = parent.get_parent() as Node3D
	return result

func _apply_rendered_walk_surfaces(mesh_instances: Array) -> void:
	var navigation: Dictionary = manifest.data.get("navigation", {})
	var prefixes_value: Variant = navigation.get("surfaceNodePrefixes", [])
	if not prefixes_value is Array:
		return
	var prefixes: Array = prefixes_value as Array
	for node_value: Variant in mesh_instances:
		var mesh_instance: MeshInstance3D = node_value as MeshInstance3D
		var node_name: String = mesh_instance.name
		if node_name.begins_with("StreamView_"):
			node_name = node_name.get_slice("__", 1)
		var matches_surface: bool = false
		for prefix_value: Variant in prefixes:
			if node_name.begins_with(str(prefix_value)):
				matches_surface = true
				break
		if matches_surface:
			_create_static_collision(mesh_instance, NAVIGATION_SURFACE_LAYER,
				"_WalkSurfaceCollision")

func _create_static_collision(mesh_instance: MeshInstance3D,
		layer: int = WORLD_COLLISION_LAYER, suffix: String = "_Collision") -> void:
	if mesh_instance.mesh == null:
		return
	var body := StaticBody3D.new()
	body.name = mesh_instance.name + suffix
	body.collision_layer = layer
	var shape := CollisionShape3D.new()
	shape.shape = _trimesh_shape(mesh_instance.mesh)
	body.add_child(shape)
	mesh_instance.add_child(body)

## The trimesh shape for `mesh`, built once per mesh per load.
##
## A region names the same handful of meshes over and over: Amberwood declares
## collision on 862 nodes that between them reference 91 meshes, and the walk
## surfaces of a region repeat too. `create_trimesh_shape()` walks every
## triangle and the physics server builds a BVH per shape, so building one per
## node paid for the same geometry ten times over - 638 ms of Amberwood's load
## and 528 ms of Verdant Stair's.
##
## Sharing is exact rather than approximate: the faces are in the mesh's own
## space and the placement lives on the CollisionShape3D's parent, which is
## what lets one shape stand under many bodies, and is how an instanced scene
## has always worked. The table is per load, so a map change does not hold the
## last map's geometry.
func _trimesh_shape(mesh: Mesh) -> ConcavePolygonShape3D:
	var key: int = mesh.get_instance_id()
	var cached: ConcavePolygonShape3D = _collision_shapes.get(key) as ConcavePolygonShape3D
	if cached != null:
		return cached
	var operation_began := Time.get_ticks_usec()
	var built: ConcavePolygonShape3D = mesh.create_trimesh_shape()
	ResourceDiagnostics.record(_resource_timings, &"trimesh_shape_build", operation_began, true)
	_collision_shapes[key] = built
	return built


func _group_streaming_views() -> void:
	if manifest.data.get("streamingBorders", []).is_empty():
		return
	if manifest.data.streamingBorders[0].get("geometryMode", "") in ["shared-cells-v2", "continent-owned-v1", "continent-chunks-v1"]:
		_group_shared_streaming_cells()
		return
	var views: Array[Node3D] = []
	for node: Node in world_root.find_children("StreamView_*", "Node3D", true, false):
		if not str(node.get_parent().name).begins_with("StreamView_"):
			views.append(node as Node3D)
	var active := Node3D.new()
	active.name = "StreamActive"
	var children := world_root.get_children()
	world_root.add_child(active)
	for child: Node in children:
		child.owner = null
		child.reparent(active, false)
		child.owner = world_root
	for view: Node3D in views:
		var identity := str(view.name).trim_prefix("StreamView_").get_slice("__", 0)
		var group := world_root.get_node_or_null("StreamPreview_" + identity) as Node3D
		if group == null:
			group = Node3D.new()
			group.name = "StreamPreview_" + identity
			group.visible = false
			world_root.add_child(group)
		var local := _import_transform(view)
		view.owner = null
		view.reparent(group, false)
		view.owner = world_root
		view.transform = local

func _group_shared_streaming_cells() -> void:
	var membership: Dictionary = {}
	for border: Dictionary in manifest.data.streamingBorders:
		for title: String in border.get("sceneNodes", []):
			if not membership.has(title): membership[title] = []
			membership[title].append(str(border.id))
	var selected: Array[Node3D] = []
	for node: Node in world_root.find_children("*", "Node3D", true, false):
		if membership.has(str(node.name)): selected.append(node as Node3D)
		if "_StreamThreshold_" in str(node.name):
			(node as Node3D).visible = false
			node.set_meta("stream_threshold", true)
	var core := Node3D.new()
	core.name = "StreamActive"
	var children := world_root.get_children()
	world_root.add_child(core)
	for child: Node in children:
		child.owner = null
		child.reparent(core, false)
		child.owner = world_root
	var groups: Dictionary = {}
	for node: Node3D in selected:
		var borders: Array = membership[str(node.name)]
		borders.sort()
		var key := "+".join(borders)
		if not groups.has(key):
			var group := Node3D.new()
			group.name = "StreamCell_" + key
			group.set_meta("stream_borders", borders)
			world_root.add_child(group)
			groups[key] = group
		var local := _import_transform(node)
		node.owner = null
		node.reparent(groups[key], false)
		node.owner = world_root
		node.transform = local
	world_root.set_meta("shared_stream_cells", true)

func _disable_streaming_preview_collision() -> void:
	for group: Node in world_root.get_children():
		if not str(group.name).begins_with("StreamPreview_"):
			continue
		for body: Node in group.find_children("*", "CollisionObject3D", true, false):
			body.set_meta("stream_collision_layer", (body as CollisionObject3D).collision_layer)
			(body as CollisionObject3D).collision_layer = 0

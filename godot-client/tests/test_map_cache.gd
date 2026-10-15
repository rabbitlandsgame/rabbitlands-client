extends SceneTree

## The map cache: the key, the invalidation contract, and the batch links.
##
## `WorldLoader` writes the region it built to `user://map-cache` and reads it
## back on the next visit instead of parsing the package again. The thing that
## makes that safe rather than reckless is the key: an entry is named after the
## package's own bytes and the loader's cache-format version, so an entry that
## does not match what is on disk is not found at all, and the region is
## rebuilt. Everything below is that contract.
##
## The region used is `four-gates-deposit-four-keys`, the smallest shipped
## package at 3.1 MB, copied into a scratch directory first: the tests that
## prove a changed package misses have to change a package, and they may not
## change one in the repository.
##
## Run: Godot_v4.7.2-stable_win64.exe --headless --path . \
##         --script tests/test_map_cache.gd

const MapCache := preload("res://src/world/map_scene_cache.gd")
const OccluderFadeScript := preload("res://src/world/occluder_fade.gd")

const REGISTRY := "res://data/maps/registry.json"
const FIXTURE_REGION := "four-gates-deposit-four-keys"
const SCRATCH := "user://map-cache-test"

var failures := 0
var _loader: WorldLoader
var _stage: Node3D
var _manifest_path := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.low_processor_usage_mode_sleep_usec = 1
	Engine.max_fps = 0

	_check_digest()
	_check_key()
	_check_directory()

	if _prepare_fixture():
		_stage = Node3D.new()
		root.add_child(_stage)
		_loader = WorldLoader.new()
		_loader.name = "WorldLoader"
		_stage.add_child(_loader)
		await process_frame
		await _check_round_trip()
		await _check_consumer_mutations()
		await _check_package_change()
		await _check_disabled()
		_loader.unload_world()
		_stage.queue_free()
		await process_frame
	await _check_occluder_fade_after_a_round_trip()

	MapCache.clear_disk()
	_remove_tree(SCRATCH)
	print("map cache tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------

## The digest is over both files, in a fixed order, and it is blind to the line
## endings of the text one - which is the only reason the server can publish
## the same number for a package a player checked out on another platform.
func _check_digest() -> void:
	var directory: String = SCRATCH + "/digest"
	DirAccess.make_dir_recursive_absolute(directory)
	var glb: String = directory + "/world.glb"
	var json: String = directory + "/world.json"
	_write_bytes(glb, PackedByteArray([1, 2, 3, 4]))
	_write_bytes(json, "{\n  \"a\": 1\n}\n".to_utf8_buffer())
	var base: String = MapCache.package_digest(json, glb)
	_expect(base.length() == 64, "the package digest is a sha256")

	_write_bytes(json, "{\r\n  \"a\": 1\r\n}\r\n".to_utf8_buffer())
	_expect(MapCache.package_digest(json, glb) == base,
		"the same manifest with CRLF endings hashes the same")

	_write_bytes(json, "{\n  \"a\": 2\n}\n".to_utf8_buffer())
	_expect(MapCache.package_digest(json, glb) != base,
		"a changed manifest changes the digest")

	_write_bytes(json, "{\n  \"a\": 1\n}\n".to_utf8_buffer())
	_expect(MapCache.package_digest(json, glb) == base,
		"and changing it back changes it back")

	_write_bytes(glb, PackedByteArray([1, 2, 3, 5]))
	_expect(MapCache.package_digest(json, glb) != base,
		"a changed glb changes the digest")

	# The order is fixed rather than incidental: swapping the two files must
	# not produce the same number, or two packages could share an entry.
	_write_bytes(glb, "{\n  \"a\": 1\n}\n".to_utf8_buffer())
	_write_bytes(json, PackedByteArray([1, 2, 3, 4]))
	_expect(MapCache.package_digest(json, glb) != base,
		"the glb and the manifest are hashed in a fixed order")

	_expect(MapCache.package_digest(directory + "/missing.json", glb).is_empty(),
		"a package that cannot be read has no digest")
	_expect(MapCache.cache_path("anything", "").is_empty(),
		"and no digest means no cache file")

func _check_key() -> void:
	var digest: String = "0".repeat(64)
	var other: String = "1".repeat(64)
	var key: String = MapCache.cache_key(digest)
	_expect(key.length() == MapCache.KEY_CHARACTERS,
		"the key is the length the file name reserves for it")
	_expect(key != MapCache.cache_key(other),
		"two packages get two keys")
	_expect(key == MapCache.cache_key_for(digest, MapCache.CACHE_FORMAT_VERSION),
		"the key is the digest under the current format version")
	_expect(key != MapCache.cache_key_for(digest, MapCache.CACHE_FORMAT_VERSION + 1),
		"raising the format version misses every entry on disk")
	_expect(MapCache.cache_path("amberwood", digest)
			== "%s/amberwood-%s%s" % [MapCache.CACHE_DIRECTORY, key,
				MapCache.CACHE_EXTENSION],
		"the entry is named after the map and the key")
	# A map id arrives from a package the client did not author, so it is
	# reduced to a file name rather than trusted as one: no separators, no dot
	# segments, nothing that could put an entry outside the cache directory.
	var awkward: String = MapCache.cache_path("Grey Moors/../x", digest)
	_expect(awkward.begins_with(MapCache.CACHE_DIRECTORY + "/")
			and not awkward.trim_prefix(MapCache.CACHE_DIRECTORY + "/").contains("/")
			and not awkward.contains(".."),
		"a map id that is not a file name is reduced to one: %s" % awkward)
	_expect(MapCache.staging_path(MapCache.cache_path("amberwood", digest))
			.ends_with(MapCache.CACHE_EXTENSION),
		"the half-written file keeps the extension ResourceSaver needs")
	_expect(not MapCache.format_version_note().is_empty(),
		"the format version says out loud what raising it is for")

func _check_directory() -> void:
	MapCache.clear_disk()
	_expect(MapCache.ensure_directory(), "the cache directory is creatable")
	_expect(MapCache.total_bytes() == 0 and MapCache.entries().is_empty(),
		"an empty cache is empty")
	_expect(MapCache.describe_size(0) == "empty"
			and MapCache.describe_size(2048) == "2 KB"
			and MapCache.describe_size(33554432) == "32.0 MB",
		"the settings row has a size to show: %s" % MapCache.describe_size(33554432))

	# A staging file is not an entry: it is not readable yet, and counting it
	# would make the settings row jump while a region is being packed.
	var staging: String = MapCache.staging_path(
		MapCache.CACHE_DIRECTORY + "/probe-0000000000000000.scn")
	_write_bytes(staging, PackedByteArray([0, 1, 2]))
	_expect(MapCache.entries().is_empty(), "a write in flight is not an entry")
	_expect(MapCache.clear_disk() == 1, "clearing removes it anyway")

# --------------------------------------------------------------------------
# The region
# --------------------------------------------------------------------------

## A copy of the smallest shipped package, in a directory the tests may write
## to. Returns false when the package cannot be found, which fails loudly
## rather than passing quietly.
func _prepare_fixture() -> bool:
	var registry_value: Variant = JSON.parse_string(_read_text(REGISTRY))
	var maps: Dictionary = {}
	if registry_value is Dictionary:
		maps = (registry_value as Dictionary).get("maps", {}) as Dictionary
	var entry: Dictionary = MapRegistry.resolve(maps, FIXTURE_REGION)
	if not _expect(not entry.is_empty(), FIXTURE_REGION + " resolves in the registry"):
		return false
	var source: String = ProjectSettings.globalize_path(str(entry.get("manifest", "")))
	var manifest := WorldManifest.load_file(source)
	if not _expect(manifest.is_valid(), FIXTURE_REGION + " has a valid manifest"):
		return false
	var directory: String = SCRATCH + "/package"
	DirAccess.make_dir_recursive_absolute(directory)
	_manifest_path = directory + "/world.json"
	var glb: String = directory + "/world.glb"
	if not _expect(_copy(source, _manifest_path) and _copy(manifest.glb_path(), glb),
			"the fixture package is copied somewhere writable"):
		return false
	# The copy names its own glb, so the manifest's relative path still holds.
	_expect(str((JSON.parse_string(_read_text(_manifest_path)) as Dictionary)
			.get("asset", {}).get("glb", "")) == "world.glb",
		"the copied manifest points at the copied glb")
	# The smallest package is small partly because it repeats little, and at
	# the shipped minimum of four it produces no batches at all - which would
	# leave the batch links, the one thing a PackedScene cannot carry, untested
	# on a real region. The minimum is a per-map setting, so the copy lowers it.
	var copied: Dictionary = JSON.parse_string(_read_text(_manifest_path)) as Dictionary
	copied["rendering"] = {"batchMinimumInstances": 2}
	_write_text(_manifest_path, JSON.stringify(copied, "  "))
	return true

## The whole contract in one pass: a first visit misses and writes, a second
## visit hits, and what comes back is what the loader built.
func _check_round_trip() -> void:
	MapCache.clear_disk()
	MapCache.forget_setting()

	var fresh: Dictionary = await _load("first visit")
	_expect(_loader.cache_status == &"miss",
		"a region with no entry is a miss (%s)" % _loader.cache_status)
	_expect(not _loader.loaded_from_cache, "and is parsed from the package")
	_expect(_loader.package_digest.length() == 64, "the load records the digest")
	_expect(_loader.cache_file.ends_with(
			MapCache.cache_key(_loader.package_digest) + MapCache.CACHE_EXTENSION),
		"and names the entry it will write after the package's own bytes")
	var expected_file: String = _loader.cache_file
	await _settle_for_the_write(expected_file)
	_expect(FileAccess.file_exists(expected_file),
		"the first visit writes the entry once the world is up")
	_expect(MapCache.entries().size() == 1, "there is one entry on disk")
	_expect(MapCache.total_bytes() > 0, "the settings row has a size to report")
	_expect(int(_loader.load_phases.get(&"cachePack", 0)) > 0,
		"the pack is timed as its own phase, off the load")

	var warm: Dictionary = await _load("second visit")
	_expect(_loader.cache_status == &"hit",
		"a second visit hits (%s)" % _loader.cache_status)
	_expect(_loader.loaded_from_cache, "and says it came from the cache")
	_expect(int(_loader.load_phases.get(&"parse", 0)) == 0,
		"a hit does not parse the package")
	_expect(int(_loader.load_phases.get(&"cacheInstantiate", 0)) > 0,
		"a hit instantiates the entry instead")

	# And it is the same region. Every count the loader's passes produce, and a
	# hash over the name, world placement, layers and shadow casting of every
	# mesh instance in the tree.
	for key: Variant in fresh:
		_expect(warm.get(key) == fresh[key],
			"the cached region matches the built one: %s (built %s, cached %s)" % [
				key, fresh[key], warm.get(key)])
	_expect(int(fresh.get("meshInstances", 0)) > 0,
		"the fixture has meshes to compare")
	_expect(int(fresh.get("bodies", 0)) > 0,
		"the fixture has collision bodies, so the cache is carrying some")
	_expect(int(fresh.get("walkSurfaceBodies", 0)) > 0,
		"and walk surfaces, which is what holds the player up")
	_expect(int(fresh.get("batchLinks", 0)) > 0,
		"and batched props, whose links are what a PackedScene cannot carry")
	_expect(int(warm.get("resolvedLinks", 0)) == int(warm.get("batchLinks", -1)),
		"every batch link in the cached region names a live MultiMeshInstance3D")

## Touching the package's bytes retires the entry built from them, and the
## replacement takes its place rather than joining it.
func _check_package_change() -> void:
	var before: String = _loader.cache_file
	var text: String = _read_text(_manifest_path)
	# A comment the loader ignores: the manifest is still valid, the region is
	# still the same one, and the bytes are not the bytes the entry was built
	# from. That is the whole test.
	_write_text(_manifest_path, text.replace("\"schemaVersion\"",
		"\"cacheTestMarker\": 1, \"schemaVersion\""))

	await _load("after the package changed")
	_expect(_loader.cache_status == &"miss",
		"a package whose bytes changed misses its entry (%s)" % _loader.cache_status)
	_expect(_loader.cache_file != before, "and is keyed somewhere else")
	await _settle_for_the_write(_loader.cache_file)
	_expect(FileAccess.file_exists(_loader.cache_file), "the new entry is written")
	# The stale entry goes after the new one lands, on the same worker thread,
	# so it is a moment behind it rather than beside it.
	await _settle_until_gone(before)
	_expect(not FileAccess.file_exists(before),
		"and the entry for the package that is gone is removed with it")
	_expect(MapCache.entries().size() == 1,
		"one map leaves one entry behind, not one per build (%d)" % MapCache.entries().size())

	# An entry that is on disk but will not load is not a dead end either.
	_write_bytes(_loader.cache_file, PackedByteArray([1, 2, 3, 4, 5]))
	await _load("with a corrupt entry")
	_expect(_loader.cache_status == &"unreadable",
		"an entry that will not load is reported, not trusted (%s)" % _loader.cache_status)
	_expect(_loader.world_root != null, "and the region is built from the package")

## The hazard the deferred write creates, and the answer to it.
##
## The entry is packed three frames after the load, and by then the rest of the
## client has had the tree: `InteriorCutaway` hides a wall the camera is
## looking through, `SecretSections` hides an undiscovered section, and
## `OccluderFade` hangs a duplicated translucent material on whatever stands
## between the camera and the player and makes a batched prop's own node
## visible so it can be seen fading. None of that is the region; all of it is
## the client's opinion of the region a moment ago. Packed in, it would be
## permanent, and it would be permanent only for players whose cache happened
## to be written on a frame where the camera was in the wrong place - the worst
## kind of bug to be handed.
##
## So the loader takes the three values that can move while the tree is still
## only its own, puts them back for the length of the pack, and restores
## whatever the client had afterwards. This does to a real region exactly what
## those three consumers do, and then reads the region back.
func _check_consumer_mutations() -> void:
	MapCache.clear_disk()
	await _load("before a consumer touches it")
	if not _expect(_loader.cache_status == &"miss", "a fresh region to pack"):
		return

	# Three mutations, one for each consumer, chosen from the tree by hand so
	# the names can be looked up again in the cached copy.
	var hide_me: MeshInstance3D = _first_mesh(true)
	var fade_me: MeshInstance3D = _first_mesh(true, hide_me)
	var lifted: MeshInstance3D = _first_mesh(false)
	if not _expect(hide_me != null and fade_me != null and lifted != null,
			"the fixture has a visible mesh to hide, one to fade and a hidden one to lift"):
		return
	var hidden_name: String = hide_me.name
	var faded_name: String = fade_me.name
	var lifted_name: String = lifted.name

	hide_me.visible = false                      # the interior cutaway
	lifted.visible = true                        # the occluder fade, lifting
	var glass := StandardMaterial3D.new()        # the occluder fade, fading
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.albedo_color = Color(1.0, 1.0, 1.0, 0.35)
	fade_me.set_surface_override_material(0, glass)
	# The look pass paints a static batch of crowns through its whole-mesh
	# override, which has no surfaces to record.
	var batch: MultiMeshInstance3D = _first_batch()
	var painted := StandardMaterial3D.new()
	painted.albedo_color = Color(1.0, 0.0, 1.0)
	var batch_name := ""
	if batch != null:
		batch_name = batch.name
		batch.material_override = painted

	await _settle_for_the_write(_loader.cache_file)
	# The client's own state is its own: the loader borrowed the tree for the
	# length of the pack and gave it back exactly as it found it.
	_expect(not hide_me.visible and lifted.visible
			and fade_me.get_surface_override_material(0) == glass
			and (batch == null or batch.material_override == painted),
		"packing leaves the client's view of the region alone")

	await _load("read back after a consumer touched it")
	if not _expect(_loader.loaded_from_cache,
			"the mutated region comes back from the cache (%s)" % _loader.cache_status):
		return
	var restored_hidden: MeshInstance3D = _find_mesh(hidden_name)
	var restored_faded: MeshInstance3D = _find_mesh(faded_name)
	var restored_lifted: MeshInstance3D = _find_mesh(lifted_name)
	_expect(restored_hidden != null and restored_hidden.visible,
		"a wall the cutaway had hidden is not hidden in the cached region")
	_expect(restored_lifted != null and not restored_lifted.visible,
		"a prop the fade had lifted out of its batch is back in it")
	_expect(restored_faded != null
			and restored_faded.get_surface_override_material(0) == null,
		"a rock the fade had turned to glass is solid again")
	if _expect(not batch_name.is_empty(), "the fixture has a static batch to paint"):
		var restored_batch := _loader.world_root.find_child(batch_name, true, false) \
			as MultiMeshInstance3D
		_expect(restored_batch != null and restored_batch.material_override == null,
			"a batch the look had painted draws the loader's own material again")

## The first static batch the loader made, or null.
func _first_batch() -> MultiMeshInstance3D:
	for node: Node in _loader.world_root.find_children("StaticBatch_*", "MultiMeshInstance3D",
			true, false):
		return node as MultiMeshInstance3D
	return null

## The first mesh instance in the tree with the visibility asked for, skipping
## `except`. Deliberately the first rather than a chosen one: any mesh will do,
## and naming one would tie this test to a package that may be regenerated.
func _first_mesh(visible: bool, except: MeshInstance3D = null) -> MeshInstance3D:
	for node: Node in _loader.world_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		if mesh_instance.visible != visible or mesh_instance == except:
			continue
		if mesh_instance.mesh == null or mesh_instance.mesh.get_surface_count() == 0:
			continue
		return mesh_instance
	return null

func _find_mesh(node_name: String) -> MeshInstance3D:
	return _loader.world_root.find_child(node_name, true, false) as MeshInstance3D

func _check_disabled() -> void:
	MapCache.clear_disk()
	MapCache.set_enabled(false)
	await _load("with the cache off")
	_expect(_loader.cache_status == &"disabled",
		"the setting turns the cache off (%s)" % _loader.cache_status)
	_expect(_loader.world_root != null, "and the region still loads")
	for frame: int in 8:
		await process_frame
	_expect(MapCache.entries().is_empty(),
		"a switched-off cache writes nothing")
	_expect(_loader.package_digest.length() == 64,
		"the package is still hashed, because the server's digest is checked either way")
	MapCache.set_enabled(true)
	_expect(MapCache.is_enabled(), "and the setting comes back")

# --------------------------------------------------------------------------
# The batch links
# --------------------------------------------------------------------------

## The one thing a PackedScene cannot carry, and what is done about it.
##
## `WorldLoader` stamps every mesh a batch swallowed with the
## MultiMeshInstance3D now drawing it, and `OccluderFade` reaches through that
## to lift one instance back out of the multimesh while it fades. A Node is not
## a Resource: after a scene round trip the key is not in the metadata at all.
## So the link is written twice, and the path half is re-resolved on the way
## back in. Without that, `OccluderFade` would see a hidden node with no batch,
## decide it is not drawing, and leave the prop in front of the player solid.
func _check_occluder_fade_after_a_round_trip() -> void:
	var built := _build_batched_world()
	root.add_child(built)
	await process_frame

	var packed := PackedScene.new()
	for node: Node in built.find_children("*", "", true, false):
		node.owner = built
	_expect(packed.pack(built) == OK, "a batched region packs")
	var path: String = SCRATCH + "/batched.scn"
	_expect(ResourceSaver.save(packed, path, ResourceSaver.FLAG_COMPRESS) == OK,
		"and saves")
	built.queue_free()
	await process_frame

	var reloaded: PackedScene = ResourceLoader.load(
		path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	var world: Node3D = reloaded.instantiate() as Node3D
	root.add_child(world)
	await process_frame

	var batched: MeshInstance3D = world.get_node("BatchedProp") as MeshInstance3D
	_expect(not batched.has_meta(WorldLoader.BATCH_META),
		"the object half of the link does not survive the round trip - this is the bug")
	_expect(batched.has_meta(WorldLoader.BATCH_PATH_META),
		"the path half does")

	var loader := WorldLoader.new()
	root.add_child(loader)
	loader.world_root = world
	var resolved: int = loader.call("_resolve_batch_links")
	_expect(resolved == 1, "the loader resolves the link on the way in (%d)" % resolved)
	_expect(batched.get_meta(WorldLoader.BATCH_META)
			== world.get_node("StaticBatch_0_BatchedProp"),
		"and it names the MultiMeshInstance3D that is actually drawing the prop")

	# And now the behaviour that link exists for.
	var camera: Camera3D = world.get_node("Camera") as Camera3D
	var player: Node3D = world.get_node("Player") as Node3D
	var fade: RefCounted = OccluderFadeScript.new()
	fade.configure(null, world)
	fade.set_enabled(true)
	fade.update(0.5, camera, player)
	_expect(batched.visible and batched.get_surface_override_material(0) != null,
		"a batched prop from a cached region is lifted out of the batch to fade")
	fade.reset()
	_expect(not batched.visible and batched.get_surface_override_material(0) == null,
		"and handed back afterwards")

	loader.world_root = null
	loader.queue_free()
	world.queue_free()
	await process_frame

## The shape `WorldLoader` leaves behind for one batched prop: the source node
## hidden and stamped with both halves of the link, and a MultiMeshInstance3D
## drawing it. Deliberately hand-built rather than loaded, so this test says
## what it means without a 3 MB package in the way.
func _build_batched_world() -> Node3D:
	var world := Node3D.new()
	world.name = "ImportedWorld_batched"

	var camera := Camera3D.new()
	camera.name = "Camera"
	camera.position = Vector3(0.0, 10.0, 10.0)
	world.add_child(camera)
	var player := Node3D.new()
	player.name = "Player"
	world.add_child(player)

	var mesh := BoxMesh.new()
	mesh.size = Vector3(2.0, 2.0, 2.0)
	mesh.material = StandardMaterial3D.new()
	var prop := MeshInstance3D.new()
	prop.name = "BatchedProp"
	prop.mesh = mesh
	# On the segment from the camera to the player's chest.
	prop.position = Vector3(0.0, 5.5, 5.0)
	world.add_child(prop)

	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = mesh
	multimesh.instance_count = 1
	multimesh.set_instance_transform(0, prop.transform)
	var batch := MultiMeshInstance3D.new()
	batch.name = "StaticBatch_0_BatchedProp"
	batch.multimesh = multimesh
	world.add_child(batch)

	prop.visible = false
	prop.set_meta(WorldLoader.BATCH_META, batch)
	prop.set_meta(WorldLoader.BATCH_PATH_META, NodePath("StaticBatch_0_BatchedProp"))
	prop.set_meta(WorldLoader.BATCH_INDEX_META, 0)
	for node: Node in [camera, player, prop, batch]:
		node.owner = world
	return world

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

func _load(label: String) -> Dictionary:
	_loader.load_world(_manifest_path)
	var deadline: int = Time.get_ticks_msec() + 120000
	while _loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(_loader.world_root != null, "the fixture loads: " + label):
		return {}
	return _shape(_loader.world_root)

## Waits for the deferred write, and then for the worker thread that does it.
func _settle_for_the_write(path: String) -> void:
	var deadline: int = Time.get_ticks_msec() + 60000
	while not FileAccess.file_exists(path) and Time.get_ticks_msec() < deadline:
		await process_frame

func _settle_until_gone(path: String) -> void:
	var deadline: int = Time.get_ticks_msec() + 60000
	while FileAccess.file_exists(path) and Time.get_ticks_msec() < deadline:
		await process_frame

## Everything about the built region a cached one has to reproduce.
func _shape(world: Node3D) -> Dictionary:
	var nodes := 0
	var meshes := 0
	var batches := 0
	var bodies := 0
	var walk_bodies := 0
	var hidden := 0
	var links := 0
	var resolved := 0
	var mesh_ids: Dictionary = {}
	var placement := 0
	var stack: Array[Node] = [world]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		nodes += 1
		if node is MeshInstance3D:
			var mesh_instance: MeshInstance3D = node as MeshInstance3D
			meshes += 1
			if mesh_instance.mesh != null:
				mesh_ids[mesh_instance.mesh.get_instance_id()] = true
			if not mesh_instance.visible:
				hidden += 1
			if mesh_instance.has_meta(WorldLoader.BATCH_PATH_META):
				links += 1
			if mesh_instance.has_meta(WorldLoader.BATCH_META) \
					and mesh_instance.get_meta(WorldLoader.BATCH_META) is MultiMeshInstance3D:
				resolved += 1
			# Visibility and surface overrides are in the hash because they are
			# exactly what a consumer changes: the cutaway hides a wall, the
			# occluder fade hangs a translucent material on a rock. If either
			# could reach the cache, this is the number that would move.
			var overridden := false
			for surface: int in mesh_instance.get_surface_override_material_count():
				overridden = overridden \
					or mesh_instance.get_surface_override_material(surface) != null
			placement = hash([placement, mesh_instance.name,
				mesh_instance.global_transform, mesh_instance.layers,
				mesh_instance.cast_shadow, mesh_instance.visibility_range_end,
				mesh_instance.visible, overridden])
		elif node is MultiMeshInstance3D:
			batches += 1
		elif node is StaticBody3D:
			bodies += 1
			if (node as StaticBody3D).collision_layer == WorldLoader.NAVIGATION_SURFACE_LAYER:
				walk_bodies += 1
		for child: Node in node.get_children():
			stack.append(child)
	return {
		"nodes": nodes, "meshInstances": meshes, "distinctMeshes": mesh_ids.size(),
		"batches": batches, "bodies": bodies, "walkSurfaceBodies": walk_bodies,
		"hiddenMeshes": hidden, "batchLinks": links, "resolvedLinks": resolved,
		"placementHash": placement,
	}

func _copy(from: String, to: String) -> bool:
	var source := FileAccess.open(from, FileAccess.READ)
	if source == null:
		return false
	var bytes: PackedByteArray = source.get_buffer(source.get_length())
	source.close()
	return _write_bytes(to, bytes)

func _write_bytes(path: String, bytes: PackedByteArray) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(bytes)
	file.close()
	return true

func _write_text(path: String, text: String) -> bool:
	return _write_bytes(path, text.to_utf8_buffer())

func _read_text(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	var text: String = file.get_as_text()
	file.close()
	return text

func _remove_tree(path: String) -> void:
	var directory := DirAccess.open(path)
	if directory == null:
		return
	for name: String in directory.get_files():
		DirAccess.remove_absolute(path + "/" + name)
	for name: String in directory.get_directories():
		_remove_tree(path + "/" + name)
	DirAccess.remove_absolute(path)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

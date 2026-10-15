extends SceneTree

## Map images: prepared once, with their mip chain, before GLTFDocument
## uploads them, and uploaded as their pre-compressed sidecars when the
## package has them (src/world/vram_textures.gd, map_image_extension.gd).
##
## Uses the committed package in tests/fixtures/vram (see make_fixture.py):
## six external, content-addressed images in every role plus one embedded
## image the client must leave to GLTFDocument, and the sidecars
## tools/build_vram_textures.py made for four of them (base, base with alpha,
## ORM, normal; the role conflict and the 62 px image are excluded).
## Fallback cases run on copies under user://.
##
## Run: Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##         --script res://tests/test_vram_textures.gd

const VramTextures := preload("res://src/world/vram_textures.gd")
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const MapImageExtension := preload("res://src/world/map_image_extension.gd")

const FIXTURE := "res://tests/fixtures/vram"
const SCRATCH := "user://vram-textures-test"
const EXTERNAL_IMAGES := 6
const EMBEDDED_INDEX := 6
## glTF image index -> the format its sidecar uploads as (fixture order:
## opaque base, MASK base, normal, ORM, 62 px base, role conflict).
const SIDECAR_FORMATS := {0: Image.FORMAT_BPTC_RGBA, 1: Image.FORMAT_BPTC_RGBA,
	2: Image.FORMAT_RGTC_RG, 3: Image.FORMAT_DXT1}
const SIDECARS := 4

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)
	return ok

func _run() -> void:
	OS.set_environment("ELORIA_LOOK", "0")
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	OS.low_processor_usage_mode_sleep_usec = 1
	VramTextures.ensure_registered()
	_check_sniff()
	_check_untouched_without_plan()

	# Sidecars off: the preparation alone, which must equal develop's path.
	_set_mode("0")
	_check_prepared_matches_legacy()
	_check_serial_equals_parallel()
	await _check_pool_sharing()
	await _check_worker_load()

	# Sidecars on, whatever a headless renderer reports.
	_set_mode("force")
	_check_sidecars_upload_compressed()
	_check_serial_equals_parallel()
	_check_no_mipmap_rebuilds()
	await _check_pool_sharing()
	await _check_worker_load()
	await _check_concurrent_loads()
	_check_fallbacks()
	_check_unusable_formats()
	_check_index_rejected()
	_check_shared_pool()
	_check_stale_roles()
	await _check_pooled_roles()
	_check_index_without_roles()
	_check_self_test()
	await _check_warm_cache()

	_set_mode("")
	_remove_tree(SCRATCH)
	print("vram textures tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

func _set_mode(value: String) -> void:
	OS.set_environment(VramTextures.ENVIRONMENT, value)
	VramTextures.reconfigure()

func _manifest(directory := FIXTURE) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(directory.path_join("world.json")))

## Parses a fixture GLB (`name`.glb, world or stale_roles). With `plan`, the
## way WorldLoader does.
func _parse(plan: bool, directory := FIXTURE, name := "world") -> GLTFState:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if plan:
		state.set_additional_data(VramTextures.PLAN_KEY, VramTextures.plan_for(_manifest(directory)))
	_expect(document.append_from_file(directory.path_join(name + ".glb"), state) == OK,
		"the fixture %s parses (plan=%s, mode=%s)" % [name, plan, VramTextures.mode_name()])
	return state

## Develop's path for one parsed image: read it back and build the chain.
func _legacy_image(texture: Texture2D) -> Image:
	var image := texture.get_image()
	if image != null and not image.has_mipmaps():
		if image.is_compressed():
			image.decompress()
		image.generate_mipmaps()
	return image

func _same_image(a: Image, b: Image) -> bool:
	return a != null and b != null and a.get_format() == b.get_format() \
		and a.get_size() == b.get_size() and a.get_mipmap_count() == b.get_mipmap_count() \
		and a.get_data() == b.get_data()

func _stats(state: GLTFState) -> Dictionary:
	var value: Variant = state.get_additional_data(VramTextures.STATS_KEY)
	return value if value is Dictionary else {}

func _done(state: GLTFState) -> Dictionary:
	var value: Variant = state.get_additional_data(VramTextures.DONE_KEY)
	return value if value is Dictionary else {}

func _formats(state: GLTFState) -> Array:
	var formats := []
	for texture: Texture2D in state.get_images():
		formats.append(texture.get_image().get_format())
	return formats

## A copy of the fixture under user://, for the cases that break files.
func _copy_fixture(name: String) -> String:
	var target := SCRATCH.path_join(name)
	_remove_tree(target)
	for relative: String in ["", "shared-assets", "shared-assets/vram"]:
		DirAccess.make_dir_recursive_absolute(target.path_join(relative))
		for file: String in DirAccess.get_files_at(FIXTURE.path_join(relative)):
			DirAccess.copy_absolute(FIXTURE.path_join(relative).path_join(file),
				target.path_join(relative).path_join(file))
	return target

func _remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for directory: String in DirAccess.get_directories_at(path):
		_remove_tree(path.path_join(directory))
	for file: String in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	DirAccess.remove_absolute(path)

func _index_path(directory: String) -> String:
	return directory.path_join("shared-assets/vram/index.json")

func _read_index(directory: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(_index_path(directory)))

func _write_index(directory: String, index: Dictionary) -> void:
	var file := FileAccess.open(_index_path(directory), FileAccess.WRITE)
	file.store_string(JSON.stringify(index, " "))
	file.close()

func _sha256(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()

## Rewrites one sidecar and records its new hash, so the check after the
## hash check is the one that has to catch it.
func _rewrite_sidecar(directory: String, recipe: String, bytes_of: Callable) -> String:
	var index := _read_index(directory)
	for sha: String in index.images:
		var entry: Dictionary = index.images[sha]
		if entry.recipe != recipe:
			continue
		var path := directory.path_join("shared-assets/vram").path_join(entry.file)
		var bytes: PackedByteArray = bytes_of.call(FileAccess.get_file_as_bytes(path))
		var file := FileAccess.open(path, FileAccess.WRITE)
		file.store_buffer(bytes)
		file.close()
		entry.sha256 = _sha256(bytes)
		_write_index(directory, index)
		return sha
	return ""

# --------------------------------------------------------------------------
# The preparation (sidecars off)
# --------------------------------------------------------------------------

func _check_sniff() -> void:
	var resources: Dictionary = _manifest().externalResources
	var kinds := {}
	for uri: String in resources:
		var mime := VramTextures.sniff(FileAccess.get_file_as_bytes(FIXTURE.path_join(uri)))
		kinds[uri.get_extension() + ":" + mime] = true
	_expect(kinds.has("jpg:image/jpeg") and kinds.has("png:image/png") and kinds.size() == 2,
		"images are typed by their bytes: %s" % [kinds.keys()])
	_expect(VramTextures.sniff(PackedByteArray([1, 2, 3])) == "", "unknown bytes are not typed")

func _check_untouched_without_plan() -> void:
	var state := _parse(false)
	var images: Array = state.get_json().images
	_expect(state.get_additional_data(VramTextures.STATS_KEY) == null
		and state.get_additional_data(VramTextures.DONE_KEY) == null,
		"a GLB without a plan is left to GLTFDocument (actor GLBs are untouched)")
	_expect(str(images[0].uri).begins_with("shared-assets/") and not images[0].has("mimeType"),
		"and its image descriptors are as written")

func _check_prepared_matches_legacy() -> void:
	var legacy := _parse(false)
	var planned := _parse(true)
	var stats := _stats(planned)
	var done := _done(planned)
	_expect(int(stats.get("imagesPrepared", -1)) == EXTERNAL_IMAGES
		and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES
		and int(stats.get("imagesSidecar", -1)) == 0
		and int(stats.get("imagesFailed", -1)) == 0 and int(stats.get("imagesPooled", -1)) == 0,
		"=0: every external image is decoded before the parse, none from a sidecar: %s" % [stats])
	_expect(int(stats.get("imagesPreparedOnMainThread", -1)) == 0,
		"the preparation ran on the WorkerThreadPool, not the main thread")
	_expect(done.size() == EXTERNAL_IMAGES and not done.has(EMBEDDED_INDEX),
		"the extension produced the external images and left the embedded one")
	var images: Array = planned.get_json().images
	var restored := true
	for index: int in EXTERNAL_IMAGES:
		restored = restored and str(images[index].uri).begins_with("shared-assets/") \
			and not images[index].has("mimeType")
	_expect(restored, "the original URIs are restored after the parse")
	var legacy_images := legacy.get_images()
	var planned_images := planned.get_images()
	var equal := 0
	for index: int in EXTERNAL_IMAGES:
		var mine := planned_images[index].get_image()
		if mine.has_mipmaps() and _same_image(mine, _legacy_image(legacy_images[index])):
			equal += 1
	_expect(equal == EXTERNAL_IMAGES,
		"=0: images equal develop's decode + mip chain in format, size, mips and bytes (%d/%d)"
		% [equal, EXTERNAL_IMAGES])
	_expect(not planned_images[EMBEDDED_INDEX].get_image().has_mipmaps(),
		"the embedded image is still GLTFDocument's (the loader adds its chain later)")

func _check_serial_equals_parallel() -> void:
	var planned := _parse(true)
	var resources: Dictionary = _manifest().externalResources
	var images: Array = planned.get_json().images
	var equal := 0
	for index: int in EXTERNAL_IMAGES:
		var source := FIXTURE.path_join(images[index].uri)
		var job := {"sha": str(resources[images[index].uri]), "source": source,
			"sidecar": VramTextures.sidecar_entry(str(resources[images[index].uri]), source.get_base_dir())}
		VramTextures.prepare(job)
		if _same_image(job.image, planned.get_images()[index].get_image()):
			equal += 1
	_expect(equal == EXTERNAL_IMAGES,
		"mode=%s: a serial preparation gives the same images as the parallel one (%d/%d)"
		% [VramTextures.mode_name(), equal, EXTERNAL_IMAGES])

## A second load while the first is resident: every external image comes from
## the pool, nothing is prepared, and no 1x1 placeholder survives share().
func _check_pool_sharing() -> void:
	var first := WorldLoader.new()
	root.add_child(first)
	first.load_world(FIXTURE.path_join("world.json"))
	_expect(first.world_root != null, "the fixture loads through WorldLoader")
	_expect(int(first.load_phases.get(&"imagesPrepared", -1)) == EXTERNAL_IMAGES,
		"the loader reports the prepared images in load_phases")
	var builder := WorldLoader.prepare_detached(FIXTURE.path_join("world.json"), false)
	_expect(int(builder.load_phases.get(&"imagesPooled", -1)) == EXTERNAL_IMAGES
		and int(builder.load_phases.get(&"imagesPrepared", -1)) == 0,
		"mode=%s: a second load takes every external image from the pool: %s"
		% [VramTextures.mode_name(), builder.load_phases])
	var first_textures := _textures(first.world_root)
	var second_textures := _textures(builder.world_root)
	var shared := 0
	var placeholders := 0
	for name: String in second_textures:
		var texture: Texture2D = second_textures[name]
		if texture.get_width() <= 1:
			placeholders += 1
		if name != "embedded" and first_textures.get(name) == texture:
			shared += 1
	_expect(placeholders == 0, "no 1x1 placeholder survives share()")
	_expect(shared == second_textures.size() - 1,
		"the second load binds the first load's textures (%d of %d)" % [shared, second_textures.size() - 1])
	var resident: Dictionary = builder.release_world()
	builder.free()
	(resident.root as Node).free()
	first.unload_world()
	first.queue_free()
	await process_frame

## Base colour textures by material name.
func _textures(world: Node) -> Dictionary:
	var found := {}
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			if material != null and material.albedo_texture != null:
				found[material.resource_name] = material.albedo_texture
	return found

func _check_worker_load() -> void:
	var thread := Thread.new()
	thread.start(WorldLoader.prepare_detached.bind(FIXTURE.path_join("world.json"), false))
	var deadline := Time.get_ticks_msec() + 20000
	while thread.is_alive() and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(not thread.is_alive(), "a worker-thread load finishes"):
		return
	var builder: WorldLoader = thread.wait_to_finish()
	_expect(int(builder.load_phases.get(&"imagesPrepared", -1)) == EXTERNAL_IMAGES
		and int(builder.load_phases.get(&"imagesPreparedOnMainThread", -1)) == 0,
		"mode=%s: a load from a Thread prepares its images and none on the main thread: %s"
		% [VramTextures.mode_name(), builder.load_phases])
	var threads := int(builder.load_phases.get(&"prepareThreads", -1))
	_expect(threads >= 1 and threads <= MapImageExtension.WORKER_IMPORT_TASKS_MAX,
		"a worker's images take at most %d pool threads, not the whole pool (%d)"
		% [MapImageExtension.WORKER_IMPORT_TASKS_MAX, threads])
	var resident: Dictionary = builder.release_world()
	builder.free()
	if resident.root != null:
		(resident.root as Node).free()

## A chunk worker's import (low-priority group, at most two threads) and a
## main-thread load (high priority, every thread) of the same images at once,
## as a primed cell during streaming does: both finish, the worker prepares
## nothing on the main thread, both bind full textures (no placeholder left),
## and the two maps end up sharing one texture per image. On a CI runner's few
## cores this is also the small-pool case.
func _check_concurrent_loads() -> void:
	var thread := Thread.new()
	thread.start(WorldLoader.prepare_detached.bind(FIXTURE.path_join("world.json"), false))
	var main_load := WorldLoader.new()
	root.add_child(main_load)
	main_load.load_world(FIXTURE.path_join("world.json"))
	var deadline := Time.get_ticks_msec() + 20000
	while thread.is_alive() and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(not thread.is_alive() and main_load.world_root != null,
			"mode=%s: a worker load and a main-thread load at once both finish" % VramTextures.mode_name()):
		return
	var builder: WorldLoader = thread.wait_to_finish()
	var counts := []
	var placeholders := 0
	for phases: Dictionary in [builder.load_phases, main_load.load_phases]:
		counts.append(int(phases.get(&"imagesPrepared", 0)) + int(phases.get(&"imagesPooled", 0)))
	for world: Node in [builder.world_root, main_load.world_root]:
		for texture: Texture2D in _textures(world).values():
			if texture.get_width() <= 1:
				placeholders += 1
	_expect(counts == [EXTERNAL_IMAGES, EXTERNAL_IMAGES] and placeholders == 0
		and int(builder.load_phases.get(&"imagesPreparedOnMainThread", -1)) == 0,
		"mode=%s: each prepared or pooled all %d images, the worker none on the main thread, no placeholder left: %s %d"
		% [VramTextures.mode_name(), EXTERNAL_IMAGES, counts, placeholders])
	var resident: Dictionary = builder.release_world()
	builder.free()
	if resident.root != null:
		(resident.root as Node).free()
	resident.clear()
	main_load.unload_world()
	main_load.queue_free()
	thread = null
	var left := EXTERNAL_IMAGES
	for frame: int in 60:
		await process_frame
		left = 0
		for sha: String in _manifest().externalResources.values():
			if ExternalTexturePool._published(sha) != null:
				left += 1
		if left == 0:
			break
	_expect(left == 0, "and both maps' textures leave the pool once they are gone (%d left)" % left)

# --------------------------------------------------------------------------
# Sidecars (mode=force)
# --------------------------------------------------------------------------

func _check_sidecars_upload_compressed() -> void:
	var planned := _parse(true)
	var stats := _stats(planned)
	_expect(int(stats.get("imagesSidecar", -1)) == SIDECARS
		and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES - SIDECARS
		and int(stats.get("sidecarRejected", -1)) == 0,
		"listed images come from their sidecars, the excluded ones are decoded: %s" % [stats])
	var formats := _formats(planned)
	var right := 0
	for index: int in SIDECAR_FORMATS:
		var image := planned.get_images()[index].get_image()
		if image.get_format() == SIDECAR_FORMATS[index] and image.get_mipmap_count() == 6:
			right += 1
	_expect(right == SIDECARS, "BC7 base, BC7 cutout, BC5 normal and BC1 ORM, each with its 6 mips: %s"
		% [formats])
	_expect(formats[4] == Image.FORMAT_RGB8 and formats[5] == Image.FORMAT_RGB8,
		"the excluded 62 px and role-conflict images are decoded as before: %s" % [formats])
	_expect(formats[EMBEDDED_INDEX] == Image.FORMAT_RGB8, "the embedded image is untouched")

func _check_no_mipmap_rebuilds() -> void:
	var planned := _parse(true)
	var loader := WorldLoader.new()
	var rebuilt: int = loader._build_texture_mipmaps(planned)
	loader.free()
	_expect(rebuilt == 1, "only the embedded image needs the loader's mip pass (%d rebuilt)" % rebuilt)

func _case(name: String, mutate: Callable, recipe: String, reason: String) -> void:
	VramTextures.reconfigure()
	var directory := _copy_fixture(name)
	var sha: String = mutate.call(directory)
	var planned := _parse(true, directory)
	var stats := _stats(planned)
	var resources: Dictionary = _manifest(directory).externalResources
	var images: Array = planned.get_json().images
	var fell_back := false
	for index: int in EXTERNAL_IMAGES:
		if str(resources[images[index].uri]) == sha:
			fell_back = not planned.get_images()[index].get_image().is_compressed() \
				and planned.get_images()[index].get_image().has_mipmaps()
	_expect(fell_back and int(stats.get("imagesSidecar", -1)) == SIDECARS - 1
		and int(stats.get("sidecarRejected", -1)) == 1 and int(stats.get("imagesFailed", -1)) == 0,
		"%s: the %s image falls back to its decode, the rest keep their sidecars (%s): %s"
		% [name, recipe, reason, stats])

func _check_fallbacks() -> void:
	_case("corrupt_header", _break_header, "base", "header")
	_case("truncated_zstd", _truncate_zstd, "normal", "size")
	_case("wrong_size_dds", _misstate_size, "orm", "mismatch")
	_case("missing_file", _delete_sidecar, "base_alpha", "missing")
	_case("tampered_bytes", _flip_last_byte, "base", "sha256")

func _break_header(directory: String) -> String:
	return _rewrite_sidecar(directory, "base", func(bytes: PackedByteArray) -> PackedByteArray:
		bytes.encode_u8(0, 0x58)
		return bytes)

func _truncate_zstd(directory: String) -> String:
	return _rewrite_sidecar(directory, "normal", func(bytes: PackedByteArray) -> PackedByteArray:
		return bytes.slice(0, bytes.size() - 64))

func _sha_of_recipe(index: Dictionary, recipe: String) -> String:
	for sha: String in index.images:
		if index.images[sha].recipe == recipe:
			return sha
	return ""

## The index claims 32 px for a 64 px DDS: a self-consistent entry (its GPU
## bytes still cover a 32 px top level) that the DDS check must catch at load.
func _misstate_size(directory: String) -> String:
	var index := _read_index(directory)
	var sha := _sha_of_recipe(index, "orm")
	index.images[sha].width = 32
	_write_index(directory, index)
	return sha

func _delete_sidecar(directory: String) -> String:
	var index := _read_index(directory)
	var sha := _sha_of_recipe(index, "base_alpha")
	DirAccess.remove_absolute(directory.path_join("shared-assets/vram").path_join(index.images[sha].file))
	return sha

## Changed bytes with the index's old hash: caught by the hash check.
func _flip_last_byte(directory: String) -> String:
	var index := _read_index(directory)
	var sha := _sha_of_recipe(index, "base")
	var path := directory.path_join("shared-assets/vram").path_join(index.images[sha].file)
	var bytes := FileAccess.get_file_as_bytes(path)
	bytes.encode_u8(bytes.size() - 1, bytes[bytes.size() - 1] ^ 0xFF)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
	return sha

func _check_unusable_formats() -> void:
	VramTextures.reconfigure()
	VramTextures.force_formats(VramTextures.FORMAT_BITS.bc1 | VramTextures.FORMAT_BITS.bc5)
	var planned := _parse(true)
	var stats := _stats(planned)
	var formats := _formats(planned)
	_expect(int(stats.get("imagesSidecar", -1)) == 2 and formats[0] == Image.FORMAT_RGB8
		and formats[2] == Image.FORMAT_RGTC_RG and formats[3] == Image.FORMAT_DXT1,
		"a renderer without BC7 decodes the BC7 images and keeps BC5/BC1: %s %s" % [stats, formats])
	VramTextures.reconfigure()
	VramTextures.force_formats(0)
	stats = _stats(_parse(true))
	_expect(int(stats.get("imagesSidecar", -1)) == 0 and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES,
		"a renderer with no BC format decodes everything: %s" % [stats])
	VramTextures.reconfigure()

func _check_index_rejected() -> void:
	for change: Array in [["schema", 2], ["recipeVersion", 9]]:
		VramTextures.reconfigure()
		var directory := _copy_fixture("index_" + str(change[0]))
		var index := _read_index(directory)
		index[change[0]] = change[1]
		_write_index(directory, index)
		var stats := _stats(_parse(true, directory))
		var info := VramTextures.index_for_directory(directory.path_join("shared-assets"))
		_expect(int(stats.get("imagesSidecar", -1)) == 0 and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES
			and str(info.status).begins_with("rejected:"),
			"an index with %s %s is refused whole (%s) and every image decodes" % [change[0], change[1], info.status])
	VramTextures.reconfigure()
	var directory := _copy_fixture("index_garbage")
	var file := FileAccess.open(_index_path(directory), FileAccess.WRITE)
	file.store_string("{ not json")
	file.close()
	var stats := _stats(_parse(true, directory))
	_expect(int(stats.get("imagesSidecar", -1)) == 0 and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES,
		"an unreadable index decodes every image")
	VramTextures.reconfigure()
	directory = _copy_fixture("index_missing")
	DirAccess.remove_absolute(_index_path(directory))
	stats = _stats(_parse(true, directory))
	_expect(int(stats.get("imagesSidecar", -1)) == 0 and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES
		and VramTextures.index_for_directory(directory.path_join("shared-assets")).status == "missing",
		"no index (a checkout that never ran the tool) decodes every image")
	VramTextures.reconfigure()

## A package ships a sidecar two pools hold once (tools/package_client.py
## share_identical_sidecars): the second pool's index names the first pool's
## directory in `pool` and keeps its own entry. The file is read there, its
## sha256 still checked; a pool that lacks it decodes, and a `pool` that is
## not a relative path makes the entry no entry.
func _check_shared_pool() -> void:
	VramTextures.reconfigure()
	var first := _copy_fixture("pool_first")
	var second := _copy_fixture("pool_second")
	var index := _read_index(second)
	for sha: String in index.images:
		index.images[sha]["pool"] = "../../pool_first/shared-assets"
		DirAccess.remove_absolute(second.path_join("shared-assets/vram").path_join(index.images[sha].file))
	_write_index(second, index)
	var state := _parse(true, second)
	var stats := _stats(state)
	var formats := _formats(state)
	var right := 0
	for image: int in SIDECAR_FORMATS:
		if formats[image] == SIDECAR_FORMATS[image]:
			right += 1
	var sha := _sha_of_recipe(index, "base")
	var entry := VramTextures.sidecar_entry(sha, second.path_join("shared-assets"))
	var expected := ProjectSettings.globalize_path(first.path_join("shared-assets/vram")).replace("\\", "/") \
		.simplify_path().path_join(str(index.images[sha].file))
	_expect(int(stats.get("imagesSidecar", -1)) == SIDECARS and int(stats.get("sidecarRejected", -1)) == 0
		and right == SIDECARS and str(entry.get("path", "")) == expected,
		"a pooled entry uploads the other pool's file (%s, %s): %s" % [entry.get("path", ""), formats, stats])
	_expect(VramTextures.resident_bytes(sha, 999999999) == int(index.images[sha].gpuBytes),
		"and the budget counts its sidecar's GPU bytes")
	var line := VramTextures.self_test_pool(second.path_join("shared-assets"))
	_expect(line.begins_with("vram_textures self_test pool ok pooled=%d of %d" % [SIDECARS, SIDECARS]),
		"the smoke launch's pool test decodes a pooled sidecar: " + line)
	line = VramTextures.self_test_pool(first.path_join("shared-assets"))
	_expect(line.begins_with("vram_textures self_test pool failed pooled=0"),
		"and fails on an index that names no other pool: " + line)
	VramTextures.reconfigure()
	var absent := _copy_fixture("pool_absent")
	index = _read_index(absent)
	for key: String in index.images:
		index.images[key]["pool"] = "../../pool_nowhere/shared-assets"
		DirAccess.remove_absolute(absent.path_join("shared-assets/vram").path_join(index.images[key].file))
	_write_index(absent, index)
	stats = _stats(_parse(true, absent))
	_expect(int(stats.get("imagesSidecar", -1)) == 0 and int(stats.get("sidecarRejected", -1)) == SIDECARS
		and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES and int(stats.get("imagesFailed", -1)) == 0,
		"a pool without the file decodes those images: %s" % [stats])
	_expect(VramTextures.self_test_pool(absent.path_join("shared-assets")).begins_with(
		"vram_textures self_test pool failed"), "and the smoke launch's pool test fails there")
	for pool: Variant in ["", "/pool_first/shared-assets", "C:/pool_first/shared-assets",
			"..\\..\\pool_first\\shared-assets", 7]:
		VramTextures.reconfigure()
		var refused := _copy_fixture("pool_refused")
		index = _read_index(refused)
		for key: String in index.images:
			index.images[key]["pool"] = pool
		_write_index(refused, index)
		stats = _stats(_parse(true, refused))
		var info := VramTextures.index_for_directory(refused.path_join("shared-assets"))
		_expect(info.status == "ok" and int(info.entries) == 0 and int(info.skipped) == SIDECARS
			and int(stats.get("imagesSidecar", -1)) == 0 and int(stats.get("imagesDecoded", -1)) == EXTERNAL_IMAGES,
			"a pool %s is no pool: the entries are skipped and the images decode (%s)" % [JSON.stringify(pool),
			stats])
	VramTextures.reconfigure()

# --------------------------------------------------------------------------
# Roles: a sidecar serves only what it was encoded for
# --------------------------------------------------------------------------

## The sha of the fixture's `image_index`-th glTF image (from the GLB's JSON
## chunk; parsing it would decode every image).
func _image_sha(image_index: int) -> String:
	var bytes := FileAccess.get_file_as_bytes(FIXTURE.path_join("world.glb"))
	var document: Dictionary = JSON.parse_string(bytes.slice(20, 20 + bytes.decode_u32(12)).get_string_from_utf8())
	return str(_manifest().externalResources[document.images[image_index].uri])

## stale_roles.glb: materials changed after the index was made. Its opaque
## base (image 0) is now also a MASK cutout, and its ORM map (image 3) also a
## base colour. Uploading their sidecars would draw the cutout as a solid quad
## (an opaque base has alpha 255) and the colour from a BC1 ORM encode.
func _check_stale_roles() -> void:
	VramTextures.reconfigure()
	var state := _parse(true, FIXTURE, "stale_roles")
	var stats := _stats(state)
	var formats := _formats(state)
	_expect(int(stats.get("sidecarRoleMismatch", -1)) == 2 and int(stats.get("imagesSidecar", -1)) == 2
		and int(stats.get("sidecarRejected", -1)) == 0 and int(stats.get("imagesFailed", -1)) == 0,
		"a map sampling two images in roles their sidecars were not encoded for decodes those two: %s" % [stats])
	var mipped := state.get_images()[0].get_image().has_mipmaps() and state.get_images()[3].get_image().has_mipmaps()
	_expect(formats[0] == Image.FORMAT_RGB8 and formats[3] == Image.FORMAT_RGB8 and mipped
		and formats[1] == Image.FORMAT_BPTC_RGBA and formats[2] == Image.FORMAT_RGTC_RG,
		"the opaque base now a cutout and the ORM now a colour are decoded with mips; the cutout and normal keep BC7/BC5: %s"
		% [formats])
	var published := 64 * 64 * 4 * 4 / 3
	_expect(VramTextures.resident_bytes(_image_sha(0), published) == published
		and VramTextures.resident_bytes(_image_sha(3), published) == published,
		"and the chunk budget counts those two at their published figure")
	VramTextures.reconfigure()
	_expect(int(_stats(_parse(true)).get("sidecarRoleMismatch", -1)) == 0,
		"the package the index was made from has no mismatch")

## The pool holds the first map's textures; the stale map samples two of its
## sidecars in other roles: it decodes its own copies, keeps them out of the
## pool and leaves the first map's textures alone. The other four (the BC7
## cutout, the BC5 normal and the two decoded images) come from the pool.
func _check_pooled_roles() -> void:
	VramTextures.reconfigure()
	var first := WorldLoader.new()
	root.add_child(first)
	first.load_world(FIXTURE.path_join("world.json"))
	var pooled_base := ExternalTexturePool._published(_image_sha(0))
	var builder := WorldLoader.prepare_detached(FIXTURE.path_join("stale_roles.json"), false)
	var phases := builder.load_phases
	_expect(int(phases.get(&"imagesPrivate", -1)) == 2 and int(phases.get(&"imagesPooled", -1)) == 4
		and int(phases.get(&"sidecarRoleMismatch", -1)) == 2,
		"a pooled sidecar encoded for other roles is not taken: 2 private copies, 4 pooled: %s" % [phases])
	var stale := _textures(builder.world_root)
	var cutout: Texture2D = stale.get("became_cutout")
	_expect(cutout != null and cutout != pooled_base and cutout.get_image().get_format() == Image.FORMAT_RGB8
		and cutout.get_image().has_mipmaps(),
		"the stale map's cutout samples its own decoded texture with mips")
	_expect(ExternalTexturePool._published(_image_sha(0)) == pooled_base
		and pooled_base.get_image().get_format() == Image.FORMAT_BPTC_RGBA
		and _textures(first.world_root).get("opaque") == pooled_base,
		"the pool and the first map keep their BC7 texture")
	var resident: Dictionary = builder.release_world()
	builder.free()
	(resident.root as Node).free()
	first.unload_world()
	first.queue_free()
	pooled_base = null
	cutout = null
	stale.clear()
	for frame: int in 3:
		await process_frame
	_expect(ExternalTexturePool._published(_image_sha(0)) == null, "and the pool lets them go with the maps")

## An index written before entries listed their roles: the recipe decides.
## An opaque base recipe never serves a cutout.
func _check_index_without_roles() -> void:
	VramTextures.reconfigure()
	var directory := _copy_fixture("index_without_roles")
	var index := _read_index(directory)
	for sha: String in index.images:
		(index.images[sha] as Dictionary).erase("roles")
	_write_index(directory, index)
	var stats := _stats(_parse(true, directory))
	_expect(int(stats.get("imagesSidecar", -1)) == SIDECARS and int(stats.get("sidecarRoleMismatch", -1)) == 0,
		"without roles in the index each recipe serves its own roles: %s" % [stats])
	VramTextures.reconfigure()
	var cutout := _sha_of_recipe(index, "base_alpha")
	index.images[cutout].recipe = "base"
	_write_index(directory, index)
	var state := _parse(true, directory)
	stats = _stats(state)
	_expect(int(stats.get("imagesSidecar", -1)) == SIDECARS - 1 and int(stats.get("sidecarRoleMismatch", -1)) == 1
		and _formats(state)[1] == Image.FORMAT_RGBA8,
		"and an opaque-base recipe offered for a MASK material decodes it with its alpha: %s" % [stats])
	VramTextures.reconfigure()

func _check_self_test() -> void:
	var line := VramTextures.self_test(FIXTURE.path_join("shared-assets"))
	_expect(line.begins_with("vram_textures self_test ok entries=4 format="), line)
	var directory := _copy_fixture("self_test_broken")
	for entry: String in DirAccess.get_files_at(directory.path_join("shared-assets/vram")):
		if entry.ends_with(".evt"):
			DirAccess.remove_absolute(directory.path_join("shared-assets/vram").path_join(entry))
	VramTextures.reconfigure()
	line = VramTextures.self_test(directory.path_join("shared-assets"))
	_expect(line.begins_with("vram_textures self_test failed"), line)
	VramTextures.reconfigure()
	_expect(VramTextures.status_line().begins_with("vram_textures mode=force formats=bc1+bc5+bc7 index="),
		VramTextures.status_line())

# --------------------------------------------------------------------------
# The map cache
# --------------------------------------------------------------------------

## The textures of a loaded fixture by role, from its "opaque" material.
func _opaque_textures(world: Node) -> Dictionary:
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface) as StandardMaterial3D
			if material != null and material.resource_name == "opaque":
				return {"base": material.albedo_texture, "normal": material.normal_texture,
					"orm": material.roughness_texture}
	return {}

func _load_and_wait(loader: WorldLoader) -> void:
	loader.load_world(FIXTURE.path_join("world.json"))
	for frame: int in 12:
		await process_frame

## A cache written from sidecar textures reads back BC with every mip, and a
## client whose texture formats differ (here: sidecars off) never reads it.
func _check_warm_cache() -> void:
	OS.set_environment("ELORIA_NO_MAP_CACHE", "")
	MapCache.forget_setting()
	if not _expect(MapCache.is_enabled(), "the map cache is enabled for this case"):
		return
	_set_mode("force")
	var loader := WorldLoader.new()
	root.add_child(loader)
	await _load_and_wait(loader)
	var digest := loader.package_digest
	_expect(loader.cache_status == &"miss" and FileAccess.file_exists(loader.cache_file),
		"a first load writes the cache entry (%s)" % loader.cache_status)
	_expect(loader.cache_file != MapCache.cache_path("vram_fixture", digest),
		"a package with external images keys its entry with the texture token")
	var plain := _manifest()
	plain.erase("externalResources")
	_expect(VramTextures.cache_token(plain, FIXTURE) == "" and MapCache.CACHE_FORMAT_VERSION == 7,
		"a package without external images adds nothing to its key at format 7: players keep develop's entries")
	var written := loader.cache_file
	loader.unload_world()
	await process_frame
	await _load_and_wait(loader)
	var textures := _opaque_textures(loader.world_root)
	var formats := []
	var mips := []
	for role: String in ["base", "normal", "orm"]:
		var image: Image = (textures[role] as Texture2D).get_image() if textures.get(role) != null else null
		formats.append(image.get_format() if image != null else -1)
		mips.append(image.get_mipmap_count() if image != null else -1)
	_expect(loader.cache_status == &"hit" and formats == [Image.FORMAT_BPTC_RGBA, Image.FORMAT_RGTC_RG,
		Image.FORMAT_DXT1] and mips == [6, 6, 6],
		"a cache hit keeps the sidecar formats and their mips: %s %s %s" % [loader.cache_status, formats, mips])
	loader.unload_world()
	await process_frame
	_set_mode("0")
	await _load_and_wait(loader)
	var base: Texture2D = _opaque_textures(loader.world_root).get("base")
	_expect(loader.cache_file != written and loader.cache_status == &"miss"
		and base != null and base.get_image().get_format() == Image.FORMAT_RGB8,
		"with sidecars off the same package misses that entry and decodes (%s)" % loader.cache_status)
	loader.unload_world()
	loader.queue_free()
	await process_frame
	MapCache.prune("vram_fixture", "")
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")

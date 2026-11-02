extends SceneTree
## A raw map load hashes each external image where it consumes it: the source
## bytes the import decodes, or the VRAM sidecar (hashed as it is read) that is
## uploaded instead of a source it never reads. Every other listed file is still
## hashed in the same load. Any consumed or listed file that fails its digest
## must fail the load with exactly the errors the up-front check reports.
##
## Uses copies of tests/fixtures/vram under user:// (four sidecar-backed
## images, two decoded ones and one listed file the GLB never samples).
const VramTextures := preload("res://src/world/vram_textures.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const FIXTURE := "res://tests/fixtures/vram"
const SCRATCH := "user://external-consumption-test"
const SIDECAR_PNG := "shared-assets/b48124c90b62f2a02746ddf40ca7f6d2f41097d57e4f282856a9bf066043438e.png"
const SIDECAR_JPG := "shared-assets/90c51de41c0f4fffd8a6c225f67472eb77d262a183e2fcae827383d3e10d32f4.jpg"
const DECODED_PNG := "shared-assets/25ee162b44d0b73bd9dd6fe993ba190ef0fdb8533625d6f19b2683542f0da467.png"
const DECODED_JPG := "shared-assets/bd27ed1484f5857e7bdf7d09c9142a530a14e9df4bdf71a9777aa4203c352a0c.jpg"
const UNSAMPLED := "shared-assets/bef267d22f4fb763b3a875d5e4fb4fbc359cd51ad06d6d957899bff3e982cccb.png"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	OS.set_environment("ELORIA_LOOK", "0")
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	GltfQuantization.ensure_registered()
	VramTextures.ensure_registered()
	set_mode("force")
	# First, while no pool holds the fixture's images: a sidecar-backed source
	# is never read, so its own bytes do not decide the load.
	var directory := copy_fixture("sidecar_source")
	flip_last_byte(directory.path_join(SIDECAR_PNG))
	var result := await load_map(directory)
	expect(result.loaded and result.errors.is_empty(), "a sidecar upload does not read or hash the unread source")
	var verification: Dictionary = result.verification
	expect(int(verification.consumption_attested) == 6 and int(verification.hashes_attempted) == 1
		and int(verification.resource_references) == 7 and int(verification.failures) == 0,
		"six consumed images are attested as read; only the unsampled file is hashed separately (%s)" % verification)
	result = await load_map(copy_fixture("clean"))
	expect(result.loaded and result.errors.is_empty(), "an untouched package loads")

	await reject("decoded_source", func(path: String) -> void: flip_last_byte(path.path_join(DECODED_PNG)),
		"a changed decoded source")
	await reject("missing_source", func(path: String) -> void: DirAccess.remove_absolute(path.path_join(DECODED_JPG)),
		"a missing decoded source")
	await reject("unsampled", func(path: String) -> void: flip_last_byte(path.path_join(UNSAMPLED)),
		"a changed listed file the GLB never samples")
	await reject("sidecar_and_source", change_sidecar_and_source, "a changed source behind a rejected sidecar")
	set_mode("0")
	await reject("sidecars_off", func(path: String) -> void: flip_last_byte(path.path_join(SIDECAR_PNG)),
		"a changed source decoded with sidecars off")
	set_mode("force")
	await process_frame
	check_manifest_passes()
	set_mode("")
	remove_tree(SCRATCH)
	print("external consumption verification: ", failures, " failures")
	quit(failures)

## The sidecar fails its own digest, so the import decodes the source instead.
func change_sidecar_and_source(directory: String) -> void:
	flip_last_byte(directory.path_join("shared-assets/vram").path_join(SIDECAR_JPG.get_file().get_basename() + ".base.evt"))
	flip_last_byte(directory.path_join(SIDECAR_JPG))

## Loads a changed copy and expects the up-front check's exact failures.
func reject(name: String, change: Callable, label: String) -> void:
	var directory := copy_fixture(name)
	change.call(directory)
	var expected := WorldManifest.load_file(directory.path_join("world.json")).verify_external_resources()
	var result := await load_map(directory)
	expect(not expected.is_empty() and not result.loaded and result.errors == expected,
		"%s fails the load with the up-front errors %s (got %s)" % [label, expected, result.errors])

func load_map(directory: String) -> Dictionary:
	var loader := WorldLoader.new()
	root.add_child(loader)
	var errors: Array[String] = []
	loader.load_failed.connect(func(reported: Array[String]) -> void: errors.assign(reported))
	loader.load_world(directory.path_join("world.json"))
	var result := {"loaded": loader.world_root != null, "errors": errors,
		"verification": loader.manifest.verification_diagnostics.duplicate(true) if loader.manifest != null else {}}
	loader.unload_world()
	loader.queue_free()
	for frame: int in 4:
		await process_frame
	return result

## Pending-hash bookkeeping on a bare manifest: one read per path, and an
## attestation never covers a URI whose digest another path also claims.
func check_manifest_passes() -> void:
	var folder := SCRATCH.path_join("manifest")
	DirAccess.make_dir_recursive_absolute(folder.path_join("a"))
	DirAccess.make_dir_recursive_absolute(folder.path_join("b"))
	var image := Image.create(8, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color.WHITE)
	image.save_png(folder.path_join("a/image.png"))
	image.save_png(folder.path_join("b/image.png"))
	var sha := FileAccess.get_sha256(folder.path_join("a/image.png"))
	var manifest := WorldManifest.new()
	manifest.source_path = folder.path_join("world.json")
	manifest.data = {"asset": {"glb": "world.glb"}, "externalResources": {"a/image.png": sha, "a/./image.png": sha}}
	expect(manifest.verify_external_resources().is_empty() and int(manifest.verification_diagnostics.hashes_attempted) == 1,
		"two URIs naming one file hash it once in one pass")
	manifest.data.externalResources = {"a/image.png": sha, "b/image.png": sha}
	expect(manifest.verify_external_resources(true).is_empty() and manifest.external_hashes_pending()
		and int(manifest.verification_diagnostics.hashes_attempted) == 0, "a deferred pass reads nothing")
	flip_last_byte(folder.path_join("b/image.png"))
	var errors := manifest.verify_pending_external({"a/image.png": true, "b/image.png": true})
	expect(errors == ["external resource missing or digest mismatch: b/image.png"]
		and int(manifest.verification_diagnostics.hashes_attempted) == 2 and not manifest.external_hashes_pending(),
		"one digest at two paths is hashed at both paths, whatever was attested")
	manifest.data.externalResources = {"a/image.png": "bad", "b/image.png": sha}
	expect(manifest.verify_external_resources(true) == ["external resource missing or digest mismatch: a/image.png",
		"external resource missing or digest mismatch: b/image.png"] and not manifest.external_hashes_pending(),
		"a deferred pass with a failure reports every failure, hashes included")
	manifest.data.externalResources = {"a/image.png": sha, "b/image.png": "f".repeat(64)}
	manifest.verify_external_resources(true)
	errors = manifest.verify_pending_external({}, {"a/image.png": true})
	expect(errors == ["external resource missing or digest mismatch: a/image.png",
		"external resource missing or digest mismatch: b/image.png"],
		"a consumer's mismatch and a pending mismatch both fail, in manifest order")
	image.save_png(folder.path_join("a/escaped%41.png"))
	manifest.data.externalResources = {"a/image.png": sha,
		"a/escaped%41.png": FileAccess.get_sha256(folder.path_join("a/escaped%41.png"))}
	expect(manifest.verify_external_resources(true).is_empty() and int(manifest.verification_diagnostics.hashes_attempted) == 1
		and manifest.external_hashes_pending() and manifest.external_verified.has("a/escaped%41.png"),
		"an escaped URI, which the import reads under another name, is hashed in the deferred pass")

func set_mode(value: String) -> void:
	OS.set_environment(VramTextures.ENVIRONMENT, value)
	VramTextures.reconfigure()

func flip_last_byte(path: String) -> void:
	var bytes := FileAccess.get_file_as_bytes(path)
	bytes[bytes.size() - 1] = bytes[bytes.size() - 1] ^ 1
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()

func copy_fixture(name: String) -> String:
	var target := SCRATCH.path_join(name)
	remove_tree(target)
	for relative: String in ["", "shared-assets", "shared-assets/vram"]:
		DirAccess.make_dir_recursive_absolute(target.path_join(relative))
		for file: String in DirAccess.get_files_at(FIXTURE.path_join(relative)):
			DirAccess.copy_absolute(FIXTURE.path_join(relative).path_join(file),
				target.path_join(relative).path_join(file))
	return target

func remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for directory: String in DirAccess.get_directories_at(path):
		remove_tree(path.path_join(directory))
	for file: String in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	DirAccess.remove_absolute(path)

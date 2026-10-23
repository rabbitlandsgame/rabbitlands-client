extends SceneTree
## Run with an isolated user directory. No renderer or network is needed.
const Options := preload("res://src/world/graphics_options.gd")
const Vram := preload("res://src/world/vram_textures.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func rgba8_bytes(image: Image) -> int:
	var total := 0
	for level: int in image.get_mipmap_count() + 1:
		total += maxi(1, image.get_width() >> level) * maxi(1, image.get_height() >> level) * 4
	return total

func _run() -> void:
	var folder := "user://phase3-resource-policy"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	var source_path := folder.path_join("image.png")
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.25, 0.5, 0.75, 1.0))
	image.save_png(source_path)
	var sha := FileAccess.get_sha256(source_path)
	var manifest := WorldManifest.new()
	manifest.source_path = folder.path_join("world.json")
	manifest.data = {"asset": {"glb": "world.glb"}, "externalResources": {"image.png": sha}}
	var policy := WorldManifest.external_verification_policy()
	expect(not policy.reuse_enabled and policy.mode == "full_hash"
		and str(policy.sealed_generation).is_empty(), "loose content never claims a sealed generation")
	expect(manifest.verify_external_resources().is_empty(), "valid external image verifies")
	expect(manifest.verify_external_resources().is_empty()
		and int(manifest.verification_diagnostics.hashes_attempted) == 1,
		"a revisit still hashes mutable content")
	var bytes := FileAccess.get_file_as_bytes(source_path)
	bytes[bytes.size() - 1] = bytes[bytes.size() - 1] ^ 1
	var file := FileAccess.open(source_path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
	expect(not manifest.verify_external_resources().is_empty(),
		"same-size replacement at the same path is rejected")
	image.save_png(source_path)
	var saved_skip := Options.active_texture_skip()
	var saved_mode := OS.get_environment(Vram.ENVIRONMENT)
	OS.set_environment(Vram.ENVIRONMENT, "0")
	Vram.reconfigure()
	Options._texture_skip = 1
	image.generate_mipmaps()
	var published := image.get_data().size()
	expect(Vram.resident_bytes(sha, published, PackedStringArray([folder])) == published,
		"unknown fallback dimensions retain the full published estimate")
	var generation := Vram.budget_generation()
	var job := {"sha": sha, "source": source_path}
	Vram.prepare(job)
	var reduced: Image = job.image
	expect(reduced != null and reduced.get_width() == 32
		and Vram.resident_bytes(sha, published, PackedStringArray([folder])) == rgba8_bytes(reduced),
		"successful decode prices actual reduced RGBA8 dimensions and mip levels")
	expect(Vram.budget_generation() > generation, "known dimensions invalidate stale budget corrections")
	var private_job := {"sha": sha, "source": source_path, "private": true}
	Vram.prepare(private_job)
	expect(Vram.resident_bytes(sha, published, PackedStringArray([folder])) == published,
		"coexisting private role copies retain conservative accounting")
	var small_path := folder.path_join("small.png")
	var small := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	small.fill(Color.WHITE)
	small.save_png(small_path)
	var small_sha := FileAccess.get_sha256(small_path)
	Options._texture_skip = 2
	var small_job := {"sha": small_sha, "source": small_path}
	Vram.prepare(small_job)
	expect((small_job.image as Image).get_width() == 4
		and Vram.resident_bytes(small_sha, 85, PackedStringArray([folder])) == 85,
		"small authored textures whose mip skip is zero keep the published figure")
	Options._texture_skip = saved_skip
	OS.set_environment(Vram.ENVIRONMENT, saved_mode)
	Vram.reconfigure()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(source_path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(small_path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(folder))
	print("phase 3 resource policy tests: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

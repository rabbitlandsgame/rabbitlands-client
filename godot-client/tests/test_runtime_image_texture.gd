extends SceneTree
## Fresh process per --quality full|half|quarter; real renderer for readback.
## Select the session's quality once, without editing any saved user settings.
const Pool := preload("res://src/world/external_texture_pool.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const WATER := "res://assets/world/continent-water.png"
const COUNTERS := ["image_load_calls", "image_path_hits", "image_hash_reads", "image_decodes", "image_resource_fallbacks", "image_uploads"]
var checks := 0
var failures := 0
var quality := "full"
var imported_only := false
var reference_path := WATER

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	for index: int in args.size():
		if args[index].begins_with("--quality="):
			quality = args[index].trim_prefix("--quality=")
		elif args[index] == "--quality" and index + 1 < args.size():
			quality = args[index + 1]
		elif args[index] == "--imported-only":
			imported_only = true
		elif args[index].begins_with("--reference-path="):
			reference_path = args[index].trim_prefix("--reference-path=")
	_run.call_deferred()

func _check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("runtime image: " + message)

func _drain() -> void:
	await process_frame
	await physics_frame
	await process_frame

func _snapshot() -> Dictionary:
	var result := Pool.retention_snapshot()
	for key: String in COUNTERS:
		_check(result.has(key), "actual image-operation counter exists: " + key)
	return result

func _delta(after: Dictionary, before: Dictionary, key: String) -> int:
	return int(after.get(key, -1000)) - int(before.get(key, 1000))

func _cold_operations(after: Dictionary, before: Dictionary, label: String) -> void:
	_check(_delta(after, before, "image_hash_reads") == (0 if imported_only else 1), label + " exact raw-file hash count")
	_check(_delta(after, before, "image_decodes") == (0 if imported_only else 1), label + " exact raw-buffer decode count")
	_check(_delta(after, before, "image_resource_fallbacks") == (1 if imported_only else 0), label + " exact imported-resource fallback count")
	_check(_delta(after, before, "image_uploads") == 1, label + " one runtime-owned GPU upload")

func _pixels(texture: ImageTexture, reference: Image, label: String) -> void:
	var image := texture.get_image()
	_check(image != null and not image.is_empty(), label + " readable GPU image")
	if image == null or image.is_empty():
		return
	_check(texture.get_width() == reference.get_width() and texture.get_height() == reference.get_height(),
		label + " exact quality dimensions")
	_check(image.has_mipmaps() and image.get_mipmap_count() == reference.get_mipmap_count(), label + " complete mip chain")
	_check(image.get_format() == reference.get_format() and image.get_data() == reference.get_data(),
		label + " exact old PNG-buffer/mipmap/slice pixels at every mip level")

static func _worker(path: String, gate: Semaphore) -> ImageTexture:
	gate.wait()
	return Pool.load_image(path)

func _run() -> void:
	_check(quality in Graphics.TEXTURE_QUALITIES, "known per-process texture quality")
	if quality not in Graphics.TEXTURE_QUALITIES:
		_finish()
		return
	# One initialization for this isolated test process, never a live quality
	# transition. No file in the player's settings directory is modified.
	Graphics._texture_skip = Graphics.TEXTURE_QUALITIES.find(quality)
	_check(Graphics.active_texture_skip() == Graphics.TEXTURE_QUALITIES.find(quality), "session quality selected exactly once")
	if imported_only:
		_check(not FileAccess.file_exists(WATER), "imported-only PCK has no raw water PNG")
		_check(ResourceLoader.exists(WATER, "Texture2D"), "imported-only PCK resolves the real Texture2D remap")
		_check(not reference_path.begins_with("res://") and FileAccess.file_exists(reference_path), "independent reference PNG exists outside PCK")
	else:
		_check(FileAccess.file_exists(WATER), "source/loose-file control has the actual raw PNG")
	var reference := Image.new()
	_check(reference.load_png_from_buffer(FileAccess.get_file_as_bytes(reference_path)) == OK, "real water PNG reference decodes")
	reference.generate_mipmaps()
	reference = Graphics.reduced_image(reference)
	_check(reference.get_width() == (512 >> Graphics.active_texture_skip())
		and reference.get_height() == (512 >> Graphics.active_texture_skip()), "real water full/half/quarter is 512/256/128")
	await _drain()
	var before := _snapshot()
	var first := Pool.load_image(WATER)
	_check(first != null, "actual runtime-owned water texture loads")
	if first == null:
		_finish()
		return
	_pixels(first, reference, "cold water")
	var cold := _snapshot()
	_cold_operations(cold, before, "cold water")
	var held_id := first.get_instance_id()
	for _index: int in 12:
		var hot := Pool.load_image(WATER)
		_check(hot == first, "retained warm caller shares the actual ImageTexture")
		hot = null
	var warm := _snapshot()
	_check(_delta(warm, cold, "image_load_calls") == 12 and _delta(warm, cold, "image_path_hits") == 12,
		"each retained lookup takes its path alias")
	for key: String in ["image_hash_reads", "image_decodes", "image_resource_fallbacks", "image_uploads"]:
		_check(_delta(warm, cold, key) == 0, "warm alias performs no additional " + key)
	var weak: WeakRef = weakref(first)
	first = null
	await _drain()
	_check(weak.get_ref() == null, "neither path alias nor hash pool pins the GPU texture")
	var reloaded := Pool.load_image(WATER)
	_check(reloaded != null and reloaded.get_instance_id() != held_id, "expired weak resource is recreated")
	if reloaded != null:
		_pixels(reloaded, reference, "reloaded water")
	var reload_stats := _snapshot()
	_cold_operations(reload_stats, warm, "weak expiry")
	var reload_weak: WeakRef = weakref(reloaded)
	reloaded = null
	await _drain()
	_check(reload_weak.get_ref() == null, "reloaded texture also has no cache-owned strong reference")
	var threads: Array[Thread] = []
	var gate := Semaphore.new()
	for _index: int in 6:
		var thread := Thread.new()
		_check(thread.start(_worker.bind(WATER, gate)) == OK, "concurrent texture worker starts")
		threads.append(thread)
	for _index: int in threads.size():
		gate.post()
	var deadline := Time.get_ticks_msec() + 10000
	while threads.any(func(thread: Thread) -> bool: return thread.is_alive()) and Time.get_ticks_msec() < deadline:
		await process_frame
	if threads.any(func(thread: Thread) -> bool: return thread.is_alive()):
		_check(false, "workers finish while main thread serves renderer; never join a live worker")
		_finish()
		return
	var results: Array = []
	for thread: Thread in threads:
		results.append(thread.wait_to_finish())
	var identities: Dictionary = {}
	for index: int in results.size():
		_check(results[index] is ImageTexture, "worker result preserves glTF-compatible ImageTexture contract")
		if results[index] is ImageTexture:
			identities[results[index].get_instance_id()] = true
	_check(identities.size() == 1, "concurrent publishers/hot adopters converge on one actual GPU texture")
	if not results.is_empty() and results[0] is ImageTexture:
		_pixels(results[0] as ImageTexture, reference, "concurrent water")
	var concurrent_weak: WeakRef = weakref(results[0]) if not results.is_empty() and results[0] != null else null
	results.clear()
	threads.clear()
	await _drain()
	_check(concurrent_weak != null and concurrent_weak.get_ref() == null, "all concurrent results release without a pool pin")
	_finish()

func _finish() -> void:
	print("RUNTIME_IMAGE_TEXTURE_CHECKS quality=", quality, " imported_only=", imported_only, " checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

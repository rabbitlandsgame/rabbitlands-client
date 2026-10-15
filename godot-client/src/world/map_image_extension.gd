extends GLTFDocumentExtension

## Produces every content-addressed image of a map package once, before
## GLTFDocument builds the package's textures. See vram_textures.gd for why.
##
## Only a document whose GLTFState carries `VramTextures.PLAN_KEY` (set by
## WorldLoader for a manifest with `externalResources`) is touched; actor GLBs
## and embedded (bufferView) images take GLTFDocument's own path.
##
## For each external image the plan names:
##   pooled   - ExternalTexturePool already holds this sha: the state keeps a
##              strong reference and the image becomes a 1x1 placeholder that
##              ExternalTexturePool.share swaps for the pooled texture. No
##              decode, no upload.
##   sidecar  - the package's pre-compressed copy (vram/<sha>.<recipe>.evt,
##              BC7 / BC5 / BC1 with its whole mip chain) when the index lists
##              it and the renderer samples its format; checked, then handed
##              to GLTFDocument as is, so the texture stays compressed on the
##              GPU. Any failed check falls back to the next line.
##   prepared - read, decoded by its magic bytes and given its mip chain.
##   (Both run on a WorkerThreadPool group task, never on the RenderingServer.)
##   failed   - left to GLTFDocument, with the mimeType its bytes declare.
##
## The image's URI is pointed at a one-byte data URI with a private mimeType
## for the parse, so GLTFDocument neither reads the file again nor tries it as
## PNG first; `_import_post_parse` puts the original URIs back for the code
## that keys on them (ExternalTexturePool.share).

const VramTextures := preload("res://src/world/vram_textures.gd")
const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")

const MIME_PREFIX := "image/x-eloria-map;"
const PLACEHOLDER_URI := "data:application/octet-stream;base64,AA=="
const ORIGINALS_KEY := &"eloria_vram_originals"
const PREPARED_KEY := &"eloria_vram_prepared"
## Pool threads one chunk worker's images may use at once. Uncapped (-1) a
## streamed cell's preparation could take as many low-priority threads as
## Godot's low_priority_thread_ratio allows for the whole streaming window;
## develop decoded on the chunk worker alone, and one or two threads keep about
## that background footprint on any core count. Measured on 24 threads the cap
## changed neither the streaming frames nor the settle time: frames are slower
## while cells stream in because the same main-thread work now lands in a
## window 2-3x shorter (no readback per image), not because of this group.
const WORKER_IMPORT_TASKS_MAX := 2

static func worker_import_tasks() -> int:
	return clampi(floori(OS.get_processor_count() / 8.0), 1, WORKER_IMPORT_TASKS_MAX)

func _import_preflight(state: GLTFState, _extensions: PackedStringArray) -> Error:
	var plan: Variant = state.get_additional_data(VramTextures.PLAN_KEY)
	if not plan is Dictionary or (plan as Dictionary).is_empty():
		return ERR_SKIP
	var resources: Dictionary = (plan as Dictionary).get("resources", {})
	var images: Array = state.get_json().get("images", [])
	# The roles this document samples each image in: a sidecar (prepared here
	# or pooled by another map) is used only where it was encoded for them.
	var document_roles := VramTextures.image_roles(state.get_json())
	var base := state.get_base_path()
	var jobs: Array[Dictionary] = []
	var by_sha: Dictionary = {}
	var assigned: Dictionary = {}
	var pooled: Dictionary = {}
	var private: Dictionary = {}
	for index: int in images.size():
		var descriptor: Variant = images[index]
		if not descriptor is Dictionary or not (descriptor as Dictionary).has("uri"):
			continue
		var uri := str((descriptor as Dictionary).uri)
		if uri.begins_with("data:") or not resources.has(uri):
			continue
		var sha := str(resources[uri])
		if sha.length() != 64:
			continue
		var roles: Dictionary = document_roles.get(index, {})
		var source := base.path_join(uri.uri_file_decode()).simplify_path()
		var shared := ExternalTexturePool._published(sha)
		if shared != null:
			if VramTextures.pooled_fits(shared, sha, source.get_base_dir(), roles):
				pooled[index] = shared
				continue
			# Another map's sidecar, encoded for other roles: this map decodes
			# its own copy, which share() neither replaces nor publishes.
			private[index] = true
		var job: Dictionary = by_sha.get(sha, {})
		if job.is_empty():
			job = {"sha": sha, "source": source, "roles": {},
				"sidecar": VramTextures.sidecar_entry(sha, source.get_base_dir())}
			by_sha[sha] = job
			jobs.append(job)
		(job.roles as Dictionary).merge(roles)
		if private.has(index):
			job["private"] = true
		assigned[index] = job
	if assigned.is_empty() and pooled.is_empty():
		return ERR_SKIP
	var role_mismatches := 0
	for job: Dictionary in jobs:
		var sidecar: Dictionary = job.sidecar
		if sidecar.is_empty():
			continue
		if bool(job.get("private", false)) or not VramTextures.sidecar_fits(sidecar, job.roles):
			job["sidecar"] = {}
			role_mismatches += 1
			VramTextures.note_decoded_instead(str(job.sha))
			VramTextures._warn_once(str(job.sha), "vram_textures: %s is sampled as %s here, which sidecar %s (%s) was not encoded for; decoding it" % [
				str(job.source).get_file(), "+".join(PackedStringArray((job.roles as Dictionary).keys())),
				str(sidecar.file), "+".join(PackedStringArray(sidecar.get("roles", VramTextures.RECIPE_ROLES.get(str(sidecar.recipe), []))))])

	var began := Time.get_ticks_usec()
	if not jobs.is_empty():
		# When the main thread is the one waiting (a primed cell or a whole-map
		# load), every pool thread at high priority. A chunk worker's import is
		# background work: at most WORKER_IMPORT_TASKS_MAX low-priority threads,
		# so streaming does not take the CPU the frames need (see that constant).
		var on_main := OS.get_thread_caller_id() == OS.get_main_thread_id()
		var task := WorkerThreadPool.add_group_task(
			func(job_index: int) -> void: VramTextures.prepare(jobs[job_index]),
			jobs.size(), -1 if on_main else worker_import_tasks(), on_main, "Eloria map images")
		WorkerThreadPool.wait_for_group_task_completion(task)
	var stats := {"imagesPrepared": 0, "imagesSidecar": 0, "imagesDecoded": 0, "imagesFailed": 0,
		"sidecarRejected": 0, "imagesPooled": pooled.size(), "imagesPreparedOnMainThread": 0,
		"prepareWaitUs": Time.get_ticks_usec() - began, "prepareThreads": 0,
		"sidecarRoleMismatch": role_mismatches, "imagesPrivate": private.size()}
	var threads: Dictionary = {}
	for job: Dictionary in jobs:
		threads[job.get("thread", 0)] = true
		match str(job.get("kind", "failed")):
			"sidecar":
				stats.imagesPrepared += 1
				stats.imagesSidecar += 1
			"decoded":
				stats.imagesPrepared += 1
				stats.imagesDecoded += 1
			_:
				stats.imagesFailed += 1
		if job.has("rejected"):
			stats.sidecarRejected += 1
		if bool(job.get("onMainThread", false)):
			stats.imagesPreparedOnMainThread += 1
	stats.prepareThreads = threads.size()

	var originals: Dictionary = {}
	var prepared: Dictionary = {}
	for index: int in assigned:
		var job: Dictionary = assigned[index]
		var descriptor: Dictionary = images[index]
		originals[index] = [descriptor.get("uri"), descriptor.get("mimeType")]
		var image: Image = job.get("image")
		if image != null:
			prepared[index] = image
			descriptor["uri"] = PLACEHOLDER_URI
			descriptor["mimeType"] = MIME_PREFIX + "prepared;" + str(index)
		elif not str(job.get("mime", "")).is_empty() and not descriptor.has("mimeType"):
			# Not decodable here; GLTFDocument tries it itself, as the type its
			# bytes declare rather than PNG first.
			descriptor["mimeType"] = str(job.mime)
	for index: int in pooled:
		var descriptor: Dictionary = images[index]
		originals[index] = [descriptor.get("uri"), descriptor.get("mimeType")]
		descriptor["uri"] = PLACEHOLDER_URI
		descriptor["mimeType"] = MIME_PREFIX + "pooled;" + str(index)
	state.set_additional_data(ORIGINALS_KEY, originals)
	state.set_additional_data(PREPARED_KEY, prepared)
	state.set_additional_data(VramTextures.POOLED_KEY, pooled)
	state.set_additional_data(VramTextures.PRIVATE_KEY, private)
	state.set_additional_data(VramTextures.DONE_KEY, {})
	state.set_additional_data(VramTextures.STATS_KEY, stats)
	return OK

## GLTFDocument 4.7 asks every active extension about every image and logs any
## answer but OK, so an image that is not ours gets OK with `ret_image` empty.
func _parse_image_data(state: GLTFState, _image_data: PackedByteArray, mime_type: String,
		ret_image: Image) -> Error:
	if not mime_type.begins_with(MIME_PREFIX):
		return OK
	var kind := mime_type.get_slice(";", 1)
	var index := int(mime_type.get_slice(";", 2))
	match kind:
		"prepared":
			var prepared: Variant = state.get_additional_data(PREPARED_KEY)
			var image: Image = (prepared as Dictionary).get(index) if prepared is Dictionary else null
			if image == null:
				return OK
			ret_image.copy_from(image)
		"pooled":
			ret_image.set_data(1, 1, false, Image.FORMAT_RGBA8, PackedByteArray([0, 0, 0, 0]))
		_:
			return OK
	var done: Variant = state.get_additional_data(VramTextures.DONE_KEY)
	if done is Dictionary:
		(done as Dictionary)[index] = true
	return OK

func _import_post_parse(state: GLTFState) -> Error:
	var originals: Variant = state.get_additional_data(ORIGINALS_KEY)
	if originals is Dictionary:
		var images: Array = state.get_json().get("images", [])
		for index: int in originals:
			var descriptor: Dictionary = images[index]
			var original: Array = originals[index]
			descriptor["uri"] = original[0]
			if original[1] == null:
				descriptor.erase("mimeType")
			else:
				descriptor["mimeType"] = original[1]
	# GLTFState keeps its own reference to each source image; ours is done.
	state.set_additional_data(PREPARED_KEY, {})
	return OK

extends RefCounted
## Split geometry texture bindings. prepare() owns Resources only; an actual
## worker can create private texture candidates, but never publishes the pool.
## apply() is main-only and mutates a newly loaded private PackedScene template.
## The geometry catalog verifies the complete source/payload closure before
## calling prepare(); this helper never treats timestamps as content evidence.
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const MapImages := preload("res://src/world/map_image_extension.gd")
const POLICY := "map-geometry-texture-bindings-v3"
const SLOT_META := &"rl_geometry_texture_slots"
const MAX_BINDINGS := 16384
const MAX_SHARED_CONTAINER_BYTES := 8 * 1024 * 1024

static func runtime_policy() -> Array:
	return [Graphics.active_texture_skip(), Vram.usable_formats(), Vram.mode_name()]

static func _identity(origin: Dictionary) -> String:
	# Slot IDs describe pixel/conversion semantics, not the current discovery
	# order, role union, or which byte-identical URI alias was encountered first.
	var identity := {"kind": str(origin.get("kind", "")),
		"image_sha256": str(origin.get("image_sha256", "")),
		"decoded_format": int(origin.get("decoded_format", -1)),
		"mip_policy": str(origin.get("mip_policy", "")),
		"width": int(origin.get("width", 0)), "height": int(origin.get("height", 0))}
	if origin.has("policy_directory"):
		identity["policy_directory"] = str(origin.policy_directory)
	if origin.has("sidecar_eligible"): identity["sidecar_eligible"] = origin.sidecar_eligible
	if identity.kind == "constant":
		identity["format"] = int(origin.get("format", -1))
		identity["mips"] = int(origin.get("mips", 0))
	elif identity.kind == "imported":
		identity["file"] = str(origin.get("file", ""))
		identity["inputs"] = origin.get("inputs", [])
	return Sources.digest_bytes(JSON.stringify(identity, "", true, true).to_utf8_buffer())

static func merge_origin(existing: Dictionary, incoming: Dictionary) -> Dictionary:
	if _identity(existing) != _identity(incoming):
		return {"ok": false, "error": "texture_origin_identity_conflict"}
	var existing_source := "%s|%s" % [str(existing.get("file", "")), str(existing.get("image_index", -1))]
	var incoming_source := "%s|%s" % [str(incoming.get("file", "")), str(incoming.get("image_index", -1))]
	var origin := (existing if existing_source <= incoming_source else incoming).duplicate(true)
	var roles := _roles(existing)
	roles.merge(_roles(incoming))
	var ordered_roles: Array = roles.keys()
	ordered_roles.sort()
	origin["roles"] = ordered_roles
	var inputs := {}
	for record: Variant in existing.get("inputs", []) + incoming.get("inputs", []):
		if not record is Dictionary: return {"ok": false, "error": "texture_origin_inputs"}
		var path := str(record.get("path", ""))
		var sha := str(record.get("sha256", ""))
		if inputs.has(path) and str(inputs[path]) != sha:
			return {"ok": false, "error": "texture_origin_input_conflict"}
		inputs[path] = sha
	var input_paths: Array = inputs.keys()
	input_paths.sort()
	var combined: Array = []
	for path: String in input_paths:
		combined.append({"path": path, "sha256": inputs[path]})
	origin["inputs"] = combined
	return {"ok": true, "origin": origin}

static func describe(texture: Texture2D) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return {"ok": false, "error": "texture_discovery_requires_main"}
	var origin := Sources.lookup(texture)
	if origin.is_empty(): return {"ok": false, "error": "texture_origin_unknown"}
	if str(origin.get("kind", "")) in ["external", "gltf_image"] \
			and int(origin.get("decoded_format", -1)) < 0:
		return {"ok": false, "error": "cook_requires_decoded_texture_sources"}
	if str(origin.get("mip_policy", "")) == "map" and Graphics.active_texture_skip() != 0:
		return {"ok": false, "error": "cook_requires_full_map_texture_quality"}
	return {"ok": true, "id": _identity(origin), "origin": origin,
		"inputs": (origin.get("inputs", []) as Array).duplicate(true)}

static func _fail(error: String) -> Dictionary:
	return {"ok": false, "error": error, "jobs": [], "pooled": {}, "bindings": {}, "candidates": {}}

static func _digest_valid(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

static func _origin_error(origin: Dictionary) -> String:
	var kind := str(origin.get("kind", ""))
	if not kind in ["external", "gltf_image", "imported", "constant"]: return "texture_origin_kind"
	if not _digest_valid(origin.get("image_sha256")): return "texture_source_digest"
	if not origin.get("roles", []) is Array and not origin.get("roles", []) is PackedStringArray:
		return "texture_roles_schema"
	for role: Variant in origin.get("roles", []):
		if not role is String: return "texture_roles_schema"
	for field: String in ["width", "height", "decoded_format"]:
		if not typeof(origin.get(field)) in [TYPE_INT, TYPE_FLOAT]: return "texture_dimensions_schema"
	if int(origin.width) <= 0 or int(origin.height) <= 0: return "texture_dimensions"
	if not str(origin.get("mip_policy", "")) in ["map", "full", "preserve"]: return "texture_mip_policy"
	if not origin.get("inputs", []) is Array: return "texture_inputs_schema"
	var inputs := {}
	for row: Variant in origin.get("inputs", []):
		if not row is Dictionary or not row.get("path") is String or not _digest_valid(row.get("sha256")):
			return "texture_inputs_schema"
		if Sources.source_path(str(row.path)).is_empty(): return "texture_source_scope"
		if inputs.has(str(row.path)) and str(inputs[str(row.path)]) != str(row.sha256): return "texture_inputs_conflict"
		inputs[str(row.path)] = str(row.sha256)
	if origin.has("policy_directory"):
		if kind != "external" or not origin.policy_directory is String or not (str(origin.policy_directory).begins_with("eloria-assets/maps/") \
				or str(origin.policy_directory).begins_with("godot-client/assets/world/")) \
				or Sources.source_path(str(origin.policy_directory)).is_empty(): return "texture_policy_scope"
	if origin.has("sidecar_eligible") and (kind != "external" or not origin.sidecar_eligible is bool): return "texture_sidecar_policy"
	if kind == "constant":
		if not origin.get("data") is String or str(origin.data).is_empty() or str(origin.data).length() > 128 \
				or not str(origin.data).is_valid_hex_number(false): return "constant_texture_data"
		if not typeof(origin.get("format")) in [TYPE_INT, TYPE_FLOAT] or int(origin.format) < 0 or int(origin.format) >= Image.FORMAT_MAX:
			return "constant_texture_format"
		if not typeof(origin.get("mips")) in [TYPE_INT, TYPE_FLOAT] or int(origin.mips) < 0:
			return "constant_texture_mips"
		return "" if int(origin.width) * int(origin.height) <= 16 and inputs.is_empty() else "constant_texture_size"
	if not origin.get("file") is String or _source(origin).is_empty(): return "texture_source_scope"
	if kind == "imported":
		return "" if not inputs.is_empty() and inputs.values().has(str(origin.image_sha256)) else "imported_texture_inputs"
	if not _digest_valid(origin.get("file_sha256")) or str(inputs.get(str(origin.file), "")) != str(origin.file_sha256):
		return "texture_source_input_missing"
	if kind == "external" and str(origin.file_sha256) != str(origin.image_sha256): return "texture_external_digest"
	if int(origin.decoded_format) < 0 or int(origin.decoded_format) >= Image.FORMAT_MAX:
		return "texture_decoded_format"
	if kind == "gltf_image" and (not typeof(origin.get("image_index")) in [TYPE_INT, TYPE_FLOAT] or int(origin.image_index) < 0):
		return "texture_image_index"
	return ""

static func _roles(origin: Dictionary) -> Dictionary:
	var roles := {}
	for value: Variant in origin.get("roles", []): roles[str(value)] = true
	return roles

static func _source(origin: Dictionary) -> String:
	return Sources.source_path(str(origin.get("file", "")))

static func _policy_directory(origin: Dictionary) -> String:
	return Sources.source_path(str(origin.policy_directory)) if origin.has("policy_directory") else _source(origin).get_base_dir()

static func _roles_key(origin: Dictionary) -> String:
	var key := str(origin.image_sha256) + "|policy=" + str(origin.policy_directory) if origin.has("policy_directory") else str(origin.image_sha256)
	return key + "|eligible=" + str(origin.sidecar_eligible) if origin.has("sidecar_eligible") else key

static func _entry(origin: Dictionary) -> Dictionary:
	return Vram.sidecar_entry(str(origin.image_sha256), _policy_directory(origin)) if bool(origin.get("sidecar_eligible", true)) else {}

static func _pool_key(origin: Dictionary, roles: Dictionary, actual: Texture2D = null) -> String:
	if not origin.has("policy_directory"): return str(origin.image_sha256)
	var entry := _entry(origin)
	if not entry.is_empty() and not Vram.sidecar_fits(entry, roles): entry = {}
	if actual is ImageTexture and not Vram.IMAGE_FORMATS.values().has((actual as ImageTexture).get_format()): entry = {}
	return Vram.variant_pool_key(str(origin.image_sha256), entry, _policy_directory(origin), 0 if str(origin.get("mip_policy", "map")) == "full" else -1)

static func _pool_fits(texture: Texture2D, origin: Dictionary, roles: Dictionary) -> bool:
	if not texture is ImageTexture: return false
	var image_texture := texture as ImageTexture
	var format := image_texture.get_format()
	var compressed := Vram.IMAGE_FORMATS.values().has(format)
	if compressed:
		var entry := _entry(origin)
		if entry.is_empty() or not Vram.sidecar_fits(entry, roles) \
				or int(Vram.IMAGE_FORMATS[str(entry.format)]) != format:
			return false
		if not Vram.pooled_fits(texture, str(origin.image_sha256), _policy_directory(origin), roles, origin.has("policy_directory")):
			return false
	elif int(origin.get("decoded_format", -1)) >= 0 and format != int(origin.decoded_format):
		return false
	var width := int(origin.get("width", texture.get_width()))
	var height := int(origin.get("height", texture.get_height()))
	if str(origin.get("mip_policy", "map")) == "map":
		var levels := floori(log(float(maxi(width, height))) / log(2.0)) if maxi(width, height) > 0 else 0
		var skip := Graphics.mip_skip(width, height, levels, Graphics.active_texture_skip(), compressed)
		width = maxi(1, width >> skip)
		height = maxi(1, height >> skip)
	return texture.get_width() == width and texture.get_height() == height

static func prepare(bindings: Dictionary, worker: bool, container_source := "", diagnostics: Dictionary = {}) -> Dictionary:
	if bindings.size() > MAX_BINDINGS: return _fail("texture_binding_limit")
	var normalised := {}
	var union_roles := {}
	var ids: Array = bindings.keys()
	ids.sort()
	for key: Variant in ids:
		if not key is String or not bindings[key] is Dictionary: return _fail("texture_binding_schema")
		var record: Dictionary = bindings[key]
		var value: Variant = record.get("origin", record)
		if not value is Dictionary: return _fail("texture_binding_schema")
		var origin: Dictionary = value
		var origin_error := _origin_error(origin)
		if not origin_error.is_empty(): return _fail(origin_error)
		if _identity(origin) != str(key): return _fail("texture_binding_identity")
		var kind := str(origin.get("kind", ""))
		if not kind in ["external", "gltf_image", "imported", "constant"]: return _fail("texture_origin_kind")
		if kind != "constant" and _source(origin).is_empty(): return _fail("texture_source_scope")
		var sha := str(origin.get("image_sha256", ""))
		if sha.length() != 64: return _fail("texture_source_digest")
		var roles: Dictionary = union_roles.get(_roles_key(origin), {})
		roles.merge(_roles(origin))
		union_roles[_roles_key(origin)] = roles
		normalised[key] = origin.duplicate(true)
	var result := {"ok": true, "error": "", "bindings": normalised, "roles": union_roles,
		"jobs": [], "by_binding": {}, "pooled": {}, "imported": {}, "textures": {}, "candidates": {},
		"worker": worker or OS.get_thread_caller_id() != OS.get_main_thread_id()}
	var jobs: Array = []
	var jobs_by_key := {}
	for id: String in ids:
		var origin: Dictionary = normalised[id]
		var kind := str(origin.kind)
		var sha := str(origin.image_sha256)
		var roles: Dictionary = union_roles[_roles_key(origin)]
		if kind == "imported":
			var path := _source(origin)
			if not path.begins_with("res://") and not path.begins_with("user://"):
				return _fail("imported_texture_scope")
			# Exported PNGs can exist only as a remap plus a CTEX product. Verify
			# the actual recorded input closure, not a nonexistent source PNG.
			for input: Variant in origin.get("inputs", []):
				if not input is Dictionary: return _fail("imported_texture_input")
				var input_path := Sources.source_path(str(input.get("path", "")))
				if input_path.is_empty() or FileAccess.get_sha256(input_path) != str(input.get("sha256", "")):
					return _fail("imported_texture_source_changed")
			if not ResourceLoader.exists(path, "Texture2D"):
				path = Sources.source_path(str(origin.get("load_path", "")))
			if path.is_empty() or not ResourceLoader.exists(path, "Texture2D"):
				return _fail("imported_texture_unavailable")
			var texture := ResourceLoader.load(path, "Texture2D", ResourceLoader.CACHE_MODE_REUSE) as Texture2D
			if texture == null: return _fail("imported_texture_unavailable")
			(result.imported as Dictionary)[id] = texture
			continue
		var pooled := Pool._published(_pool_key(origin, roles))
		if kind in ["external", "gltf_image"] and pooled != null and _pool_fits(pooled, origin, roles):
			(result.pooled as Dictionary)[id] = pooled
			continue
		# Include source directory/policy: two catalogs may deliberately refuse
		# different sidecars for identical bytes. Role requirements still union
		# across the source SHA before either job selects an encoding.
		var job_key := "%s|%s|%s|%s|%s" % [sha, kind, str(origin.get("file", "")),
			str(origin.get("image_index", -1)), str(origin.get("mip_policy", "map")) + "|" + str(origin.get("policy_directory", "")) + "|" + str(origin.get("sidecar_eligible", true))]
		if not jobs_by_key.has(job_key):
			var source := _source(origin)
			var entry := _entry(origin) if kind in ["external", "gltf_image"] else {}
			if not entry.is_empty() and not Vram.sidecar_fits(entry, roles):
				entry = {}
				Vram.note_decoded_instead(sha)
			var job := {"origin": origin, "sha": sha, "source": source, "roles": roles,
				"sidecar": entry, "private": pooled != null, "key": job_key}
			if not diagnostics.is_empty(): job["diagnostic"] = true
			jobs_by_key[job_key] = jobs.size()
			jobs.append(job)
		(result.by_binding as Dictionary)[id] = jobs_by_key[job_key]
	if not container_source.is_empty():
		var shared := _share_embedded_container(jobs,container_source,diagnostics)
		if not bool(shared.ok): return _fail(str(shared.error))
	if not jobs.is_empty():
		var background := bool(result.worker)
		var task := WorkerThreadPool.add_group_task(
			func(index: int) -> void: _prepare_job(jobs[index]), jobs.size(),
			MapImages.worker_import_tasks() if background else -1, not background, "Map geometry images")
		WorkerThreadPool.wait_for_group_task_completion(task)
	# The shared bytes belong only to this decode call. Results retain Images
	# for publication, never an extra copy of the source container.
	for job: Dictionary in jobs:
		job.erase("verified_container")
		if not diagnostics.is_empty():
			for key: String in ["embeddedContainerReads","embeddedContainerBytes"]:
				_diagnostic_add(diagnostics,"counts",key,int(job.get(key,0)))
			_diagnostic_add(diagnostics,"timings_us","geometryEmbeddedContainerReadHash",int(job.get("container_read_hash_us",0)))
	for job: Dictionary in jobs:
		if job.get("image") == null:
			return _fail(str(job.get("error", "texture_prepare_failed")))
	result["jobs"] = jobs
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		# Raw detached GLTF preparation already creates GPU-backed Resources on
		# this worker while the main thread keeps polling. Keep candidates private
		# until publication: a canceled completion must not populate the weak pool.
		for id: String in ids:
			if not (result.by_binding as Dictionary).has(id): continue
			var candidate := _image_candidate(normalised[id], jobs[int(result.by_binding[id])])
			if candidate == null: return _fail("texture_upload_failed")
			(result.candidates as Dictionary)[id] = candidate
		# The candidates own the uploaded pixels. Admission retains the entire
		# completion graph, including these Resources, until main-thread release.
		for job: Dictionary in jobs: job.erase("image")
	return result

static func _share_embedded_container(jobs: Array, source: String, diagnostics: Dictionary) -> Dictionary:
	var selected: Array[Dictionary] = []
	var expected := ""
	for job: Dictionary in jobs:
		var origin: Dictionary = job.origin
		if str(origin.kind) != "gltf_image" or str(origin.file) != source or not (job.sidecar as Dictionary).is_empty(): continue
		var sha := str(origin.file_sha256)
		if not expected.is_empty() and expected != sha: return {"ok":false,"error":"embedded_texture_source_changed"}
		expected = sha
		selected.append(job)
	if selected.size() < 2: return {"ok":true}
	var path := Sources.source_path(source)
	var began := Time.get_ticks_usec() if not diagnostics.is_empty() else 0
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null: return {"ok":false,"error":"embedded_texture_source_changed"}
	var size := file.get_length()
	if size <= 0 or size > MAX_SHARED_CONTAINER_BYTES:
		file.close()
		return {"ok":true} # Oversized sources retain the original per-job path.
	var bytes := file.get_buffer(size)
	file.close()
	if Sources.digest_bytes(bytes) != expected: return {"ok":false,"error":"embedded_texture_source_changed"}
	if not diagnostics.is_empty():
		_diagnostic_add(diagnostics,"counts","embeddedContainerReads",1)
		_diagnostic_add(diagnostics,"counts","embeddedContainerBytes",bytes.size())
		_diagnostic_add(diagnostics,"counts","embeddedContainerSharedJobs",selected.size())
		_diagnostic_add(diagnostics,"timings_us","geometryEmbeddedContainerReadHash",Time.get_ticks_usec()-began)
	for job: Dictionary in selected: job["verified_container"] = bytes
	return {"ok":true}

static func _prepare_job(job: Dictionary) -> void:
	var origin: Dictionary = job.origin
	var kind := str(origin.kind)
	if kind == "external" and str(origin.get("mip_policy", "map")) == "map":
		Vram.prepare(job)
		return
	if kind == "constant":
		var data := str(origin.get("data", "")).hex_decode()
		if data.is_empty() or data.size() > 64 or Sources.digest_bytes(data) != str(origin.image_sha256):
			job["error"] = "constant_texture_data"
			return
		var image := Image.create_from_data(int(origin.get("width", 0)), int(origin.get("height", 0)),
			int(origin.get("mips", 0)) > 0, int(origin.get("format", -1)), data)
		if image == null or image.is_empty():
			job["error"] = "constant_texture_image"
			return
		job["image"] = image
		job["kind"] = "constant"
		return
	# Embedded sources have no standalone image file. Sidecars, when actually
	# supplied for this image's own directory, retain the ordinary validation.
	var entry: Dictionary = job.get("sidecar", {})
	if not entry.is_empty():
		var loaded := Vram.decode_sidecar(entry)
		if loaded.image != null:
			job["image"] = Graphics.reduced_image(loaded.image, 0) if str(origin.get("mip_policy", "map")) == "full" else Graphics.reduced_image(loaded.image)
			job["kind"] = "sidecar"
			return
		job["rejected"] = str(loaded.reason)
		Vram.note_decoded_instead(str(origin.image_sha256))
	var bytes: PackedByteArray
	if kind == "external":
		bytes = FileAccess.get_file_as_bytes(str(job.source))
		if Sources.digest_bytes(bytes) != str(origin.image_sha256):
			job["error"] = "external_texture_source_changed"
			return
	else:
		var container: PackedByteArray
		if job.has("verified_container"):
			# Immutable, call-owned bytes already checked against this origin's
			# complete container SHA. Every extracted image is still hashed below.
			container = job.verified_container
		else:
			var detailed := bool(job.get("diagnostic",false))
			var began := Time.get_ticks_usec() if detailed else 0
			container = FileAccess.get_file_as_bytes(str(job.source))
			var digest := Sources.digest_bytes(container)
			if detailed:
				job["embeddedContainerReads"] = 1
				job["embeddedContainerBytes"] = container.size()
				job["container_read_hash_us"] = Time.get_ticks_usec()-began
			if digest != str(origin.get("file_sha256", "")):
				job["error"] = "embedded_texture_source_changed"
				return
		var extracted := Sources.embedded_bytes(container, int(origin.get("image_index", -1)))
		if not bool(extracted.get("ok", false)) or Sources.digest_bytes(extracted.get("bytes", PackedByteArray())) != str(origin.image_sha256):
			job["error"] = "embedded_texture_bytes"
			return
		bytes = extracted.bytes
	var image := Image.new()
	var error := ERR_FILE_UNRECOGNIZED
	match Vram.sniff(bytes):
		"image/png": error = image.load_png_from_buffer(bytes)
		"image/jpeg": error = image.load_jpg_from_buffer(bytes)
		"image/webp": error = image.load_webp_from_buffer(bytes)
	if error != OK or image.is_empty():
		job["error"] = "embedded_texture_decode"
		return
	if not image.has_mipmaps(): image.generate_mipmaps()
	job["image"] = image if str(origin.get("mip_policy", "map")) == "full" else Graphics.reduced_image(image)
	job["kind"] = "decoded"

static func _apply_error(prepared: Dictionary, error: String) -> bool:
	prepared["ok"] = false
	prepared["error"] = error
	return false

static func _image_candidate(origin: Dictionary, job: Dictionary) -> ImageTexture:
	var image := job.get("image") as Image
	if image == null or image.is_empty(): return null
	var target_format := int(origin.get("decoded_format", -1))
	# Preserve the cook's observed importer normalization (RGB normal -> RGBA)
	# without ever decompressing a selected BC sidecar to guess its format.
	if not image.is_compressed() and target_format >= 0 and image.get_format() != target_format:
		image = image.duplicate()
		image.convert(target_format)
	return ImageTexture.create_from_image(image)

static func _diagnostic_add(diagnostics: Dictionary, section: String, key: String, value: int) -> void:
	var values: Dictionary = diagnostics.get(section,{})
	values[key] = int(values.get(key,0))+value
	diagnostics[section] = values

static func apply(packed: PackedScene, prepared: Dictionary) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return _apply_error(prepared, "texture_publication_requires_main")
	if packed == null or not bool(prepared.get("ok", false)): return false
	# Supplied by this acquire call only. No module/global state or Resource
	# retention is added when the optional geometry diagnostic is enabled.
	var diagnostics: Dictionary = prepared.get("geometry_diagnostics",{})
	var capture := not diagnostics.is_empty()
	var began := Time.get_ticks_usec() if capture else 0
	if capture: _diagnostic_add(diagnostics,"counts","textureApplyCalls",1)
	var textures: Dictionary = (prepared.get("imported", {}) as Dictionary).duplicate()
	var bindings: Dictionary = prepared.bindings
	var ids: Array = bindings.keys()
	ids.sort()
	for id: String in ids:
		if textures.has(id):
			if capture: _diagnostic_add(diagnostics,"counts","textureImportedBindings",1)
			continue
		var origin: Dictionary = bindings[id]
		var sha := str(origin.image_sha256)
		var roles: Dictionary = prepared.roles[_roles_key(origin)]
		var pooled := Pool._published(_pool_key(origin, roles))
		if str(origin.kind) in ["external", "gltf_image"] and pooled != null and _pool_fits(pooled, origin, roles):
			textures[id] = pooled
			if capture: _diagnostic_add(diagnostics,"counts","texturePublishedPoolHits",1)
			continue
		var held: Texture2D = (prepared.pooled as Dictionary).get(id)
		if held != null and _pool_fits(held, origin, roles):
			textures[id] = held
			if capture: _diagnostic_add(diagnostics,"counts","textureHeldPoolHits",1)
			continue
		var candidate := (prepared.get("candidates", {}) as Dictionary).get(id) as ImageTexture
		if candidate != null and not _pool_fits(candidate, origin, roles):
			return _apply_error(prepared, "texture_candidate_policy_changed")
		if candidate == null:
			if not (prepared.by_binding as Dictionary).has(id): return _apply_error(prepared, "texture_job_missing")
			var job: Dictionary = prepared.jobs[int(prepared.by_binding[id])]
			if job.get("image") == null: return _apply_error(prepared, "texture_image_missing")
			candidate = _image_candidate(origin, job)
			if capture: _diagnostic_add(diagnostics,"counts","textureCandidatesCreated",1)
		elif capture:
			_diagnostic_add(diagnostics,"counts","textureWorkerCandidates",1)
		if candidate == null: return _apply_error(prepared, "texture_upload_failed")
		if str(origin.kind) in ["external", "gltf_image"]:
			# A concurrent publication may have installed another representation
			# of this SHA. Incompatible roles/formats keep this map's private copy.
			var canonical := Pool._publish_or_adopt(_pool_key(origin, roles, candidate), candidate)
			textures[id] = canonical if _pool_fits(canonical, origin, roles) else candidate
		else:
			textures[id] = candidate
	prepared["textures"] = textures
	(prepared.get("candidates", {}) as Dictionary).clear()
	if capture:
		_diagnostic_add(diagnostics,"timings_us","geometryTexturePoolUpload",Time.get_ticks_usec()-began)
		began = Time.get_ticks_usec()
	var bound := _apply_slots(packed, textures, {}, prepared, diagnostics)
	if capture: _diagnostic_add(diagnostics,"timings_us","geometryTextureSlotGraph",Time.get_ticks_usec()-began)
	return bound

static func _apply_slots(value: Variant, textures: Dictionary,
		visited: Dictionary, prepared: Dictionary, diagnostics: Dictionary = {}) -> bool:
	if value is Resource:
		var resource := value as Resource
		var identity := resource.get_instance_id()
		if visited.has(identity): return true
		visited[identity] = true
		if not diagnostics.is_empty(): _diagnostic_add(diagnostics,"counts","textureGraphResources",1)
		if resource is Texture2D: return _apply_error(prepared, "undeclared_embedded_texture")
		if resource is Image or resource is Shader or resource is Shape3D: return true
		if resource is Mesh:
			for surface: int in (resource as Mesh).get_surface_count():
				if not _apply_slots((resource as Mesh).surface_get_material(surface), textures, visited, prepared, diagnostics): return false
			return true
		if resource is MultiMesh:
			return _apply_slots((resource as MultiMesh).mesh, textures, visited, prepared, diagnostics)
		var bound_slots := {}
		if resource.has_meta(SLOT_META):
			if not resource is Material or not resource.get_meta(SLOT_META) is Dictionary:
				return _apply_error(prepared, "texture_slot_metadata")
			var properties := {}
			var slot_properties := resource.get_property_list()
			if not diagnostics.is_empty(): _diagnostic_add(diagnostics,"counts","textureGraphProperties",slot_properties.size())
			for property: Dictionary in slot_properties:
				properties[str(property.name)] = true
			var slots: Dictionary = resource.get_meta(SLOT_META)
			for name: Variant in slots:
				if not name is String or not properties.has(name) or not textures.has(str(slots[name])):
					return _apply_error(prepared, "texture_slot_unresolved")
				resource.set(str(name), textures[str(slots[name])])
				if not diagnostics.is_empty(): _diagnostic_add(diagnostics,"counts","textureSlotsBound",1)
				bound_slots[str(name)] = true
		var stored_properties := resource.get_property_list()
		if not diagnostics.is_empty(): _diagnostic_add(diagnostics,"counts","textureGraphProperties",stored_properties.size())
		for property: Dictionary in stored_properties:
			var name := str(property.name)
			if (int(property.get("usage", 0)) & PROPERTY_USAGE_STORAGE) == 0 \
					or name in ["resource_path", "resource_name", "script"] or name.begins_with("metadata/") or bound_slots.has(name):
				continue
			if not _apply_slots(resource.get(name), textures, visited, prepared, diagnostics): return false
	elif value is Array:
		for child: Variant in value:
			if not _apply_slots(child, textures, visited, prepared, diagnostics): return false
	elif value is Dictionary:
		for key: Variant in value:
			if not _apply_slots(value[key], textures, visited, prepared, diagnostics): return false
	elif value is Node or value is Callable or value is Signal:
		return _apply_error(prepared, "executable_texture_carrier")
	return true

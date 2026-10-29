extends SceneTree
## Headless CPU contract: canonical pixels retain each original sidecar policy.
const Vram := preload("res://src/world/vram_textures.gd")
const Extension := preload("res://src/world/map_image_extension.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
var failures := 0
var checks := 0
var fixture := ""
var sha := ""
var entry: Dictionary = {}
var source_image: Image

func check(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	else: print("PASS: " + label)

func write(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
	var stream := FileAccess.open(path, FileAccess.WRITE)
	stream.store_buffer(bytes)
	stream.close()

func policy_index(directory: String, broken := false) -> void:
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/vram/shared-assets/vram/index.json"))
	var chosen := entry.duplicate(true)
	if broken: chosen["sha256"] = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	index["images"] = {sha: chosen}
	index["excluded"] = {}
	write(directory.path_join("vram/index.json"), JSON.stringify(index).to_utf8_buffer())
	write(directory.path_join("vram").path_join(str(entry.file)), FileAccess.get_file_as_bytes("res://tests/fixtures/vram/shared-assets/vram/" + str(entry.file)))

func raw(directory: String) -> Dictionary:
	var state := GLTFState.new()
	state.set_base_path(fixture.path_join("chunk"))
	var relative := directory.trim_prefix(fixture + "/")
	var descriptor := {"uri": "../canonical.png", "extras": {Vram.POLICY_DIRECTORY_EXTRA: "../" + relative}}
	state.set_json({"images": [descriptor], "textures": [{"source": 0}], "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]})
	state.set_additional_data(Vram.PLAN_KEY, {"resources": {"../canonical.png": sha}, "policies": {"../canonical.png": ["../" + relative]}})
	var extension := Extension.new()
	var error := extension._import_preflight(state, PackedStringArray())
	var prepared: Dictionary = state.get_additional_data(Extension.PREPARED_KEY)
	var keys: Dictionary = state.get_additional_data(Vram.POOL_KEYS_KEY)
	return {"error": error, "image": prepared.get(0), "key": keys.get(0, ""), "state": state}

func origin(directory: String) -> Dictionary:
	return {"kind": "external", "file": Sources.logical_source(fixture.path_join("canonical.png")),
		"file_sha256": sha, "image_sha256": sha, "roles": ["base"], "mip_policy": "map",
		"policy_directory": Sources.logical_source(directory), "decoded_format": source_image.get_format(),
		"width": source_image.get_width(), "height": source_image.get_height(),
		"inputs": [{"path": Sources.logical_source(fixture.path_join("canonical.png")), "sha256": sha}]}

func native(directory: String) -> Dictionary:
	var source := origin(directory)
	return Bindings.prepare({Bindings._identity(source): {"origin": source}}, false)

func _initialize() -> void:
	OS.set_environment("ELORIA_VRAM_TEXTURES", "force")
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	fixture = "res://../eloria-assets/maps/_shared/images/vram/policy-contract-%d" % Time.get_ticks_usec()
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/vram/shared-assets/vram/index.json"))
	for key: String in index.images:
		if str(index.images[key].recipe) == "base":
			sha = key
			entry = index.images[key]
			break
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/vram/world.json"))
	for uri: String in manifest.externalResources:
		if str(manifest.externalResources[uri]) == sha:
			write(fixture.path_join("canonical.png"), FileAccess.get_file_as_bytes("res://tests/fixtures/vram/" + uri))
	source_image = Vram.decode_source(fixture.path_join("canonical.png")).image
	check(source_image != null, "canonical source retains exact encoded bytes")
	var a := fixture.path_join("a")
	var b := fixture.path_join("b")
	var skipped := fixture.path_join("skipped")
	policy_index(a)
	policy_index(b)
	var ra := raw(a)
	var rb := raw(b)
	var rr := raw(skipped)
	check(ra.error == OK and rb.error == OK and rr.error == OK, "explicit original policies parse in raw path")
	check(ra.image != null and ra.image.is_compressed() and rr.image != null and not rr.image.is_compressed(), "canonical URI cannot enable the skipped directory")
	check(ra.key == rb.key and ra.key != rr.key, "identical accepted payloads share while raw and BC variants stay separate")
	var candidate := ImageTexture.create_from_image(ra.image)
	var first := Pool._publish_or_adopt(str(ra.key), candidate)
	var second := Pool._publish_or_adopt(str(rb.key), ImageTexture.create_from_image(rb.image))
	check(first == second, "different policy directories share one actual compatible GPU resource")
	var na := native(a)
	var nr := native(skipped)
	check(bool(na.ok) and bool(nr.ok), "native origins retain original policy directory")
	var normalised_a := origin(a)
	var normalised_raw := origin(skipped)
	var a_image: Image = na.jobs[0].image if not na.jobs.is_empty() else null
	var r_image: Image = nr.jobs[0].image if not nr.jobs.is_empty() else null
	check(na.pooled.size() == 1 or (a_image != null and a_image.is_compressed()), "native accepted policy agrees with raw import")
	check(r_image != null and not r_image.is_compressed(), "native skipped policy decodes canonical pixels")
	check(Bindings._pool_key(normalised_a, {"base": true}) == str(ra.key) and Bindings._pool_key(normalised_raw, {"base": true}) == str(rr.key), "raw and native paths use identical variant identities")
	var wrong := Bindings.prepare({Bindings._identity(normalised_a): {"origin": normalised_a}}, false)
	check(bool(wrong.ok), "valid source integrity remains independent of image folder")
	var mismatch := normalised_a.duplicate(true)
	mismatch["roles"] = ["normal"]
	var refused := Bindings.prepare({Bindings._identity(mismatch): {"origin": mismatch}}, false)
	check(bool(refused.ok) and refused.jobs.size() == 1 and not (refused.jobs[0].image as Image).is_compressed(), "mismatched role rejects accepted sidecar and compatible pool")
	policy_index(a, true)
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	var failed := raw(a)
	check(failed.image != null and not failed.image.is_compressed() and failed.key == rr.key, "rejected sidecar publishes the actual raw fallback identity")
	var nf := native(a)
	check(bool(nf.ok) and nf.jobs.size() == 1 and not (nf.jobs[0].image as Image).is_compressed(), "native rejected-sidecar fallback matches raw importer")
	var invalid := {"uri": "../canonical.png", "extras": {Vram.POLICY_DIRECTORY_EXTRA: "../../../../../../../../outside"}}
	check(Vram.image_policy_directory(invalid, fixture.path_join("chunk")).is_empty(), "unsafe explicit policy fails instead of using canonical directory")
	var before := Vram.variant_pool_key(sha)
	Sources.set_recording(true)
	check(Vram.variant_pool_key(sha, {}, a) != Vram.variant_pool_key(sha, {}, b), "offline discovery preserves distinct original directory provenance")
	Sources.set_recording(false)
	check(Vram.variant_pool_key(sha) == before, "normal play returns to representation sharing")
	var weak_key := sha + "|weak-contract"
	var transient: Texture2D = Pool._publish_or_adopt(weak_key, ImageTexture.create_from_image(rr.image))
	var reference: WeakRef = weakref(transient)
	transient = null
	check(reference.get_ref() == null and Pool._published(weak_key) == null, "variant pool retains no strong GPU resource references")
	print("map image policy: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

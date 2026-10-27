extends SceneTree
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Cache := preload("res://src/world/map_geometry_cache.gd")
const DIRECTORY := "user://geometry-texture-binding-test"
const PNG := DIRECTORY + "/source.png"
var failures := 0
var fixture_origins: Dictionary = {}

func _init() -> void:
	_run.call_deferred()

func _expect(ok: bool, message: String) -> void:
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _run() -> void:
	OS.set_environment("ELORIA_VRAM_TEXTURES", "0")
	Graphics._texture_skip = 0
	Vram.reconfigure()
	Vram.ensure_registered()
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	_expect(Sources.source_path("godot-client/assets/a.png") == "res://assets/a.png", "portable project source resolves")
	_expect(Sources.source_path("eloria-assets/maps/a.png") == "res://../eloria-assets/maps/a.png", "portable world source resolves")
	_expect(Sources.source_path("godot-client/../private.png").is_empty()
		and Sources.source_path("C:/private.png").is_empty(), "source traversal and absolute author paths are refused")
	_embedded_extraction()
	var reference := _record_fixture()
	await process_frame
	_expect(reference == null or reference.get_ref() == null, "source registry does not retain parsed GPU textures")
	Sources.set_recording(false)
	_sidecars_and_embedded()
	await _external_binding()
	await _constant_worker()
	await _worker_source_revalidation()
	_imported_input()
	Sources.set_external_resolver(Callable())
	Sources.set_recording(false)
	print("map geometry texture bindings: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _embedded_extraction() -> void:
	var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.2, 0.4, 0.6, 0.8))
	var encoded := image.save_png_to_buffer()
	var document := {"asset": {"version": "2.0"}, "images": [
		{"uri": "data:image/png;base64," + Marshalls.raw_to_base64(encoded)},
		{"uri": "data:application/octet-stream,%00%20%FF"}]}
	var bytes := JSON.stringify(document).to_utf8_buffer()
	var first := Sources.embedded_bytes(bytes, 0)
	_expect(bool(first.get("ok", false)) and first.get("bytes") == encoded, "data URI image extracts exact encoded bytes without a mesh parse")
	var second := Sources.embedded_bytes(bytes, 1)
	_expect(bool(second.get("ok", false)) and second.get("bytes") == PackedByteArray([0, 32, 255]), "percent data URI preserves binary bytes")
	_expect(not bool(Sources.embedded_bytes(bytes, 10).get("ok", true)), "invalid embedded image index fails gracefully")
	var fixture := FileAccess.get_file_as_bytes("res://tests/fixtures/vram/world.glb")
	var embedded := Sources.embedded_bytes(fixture, 6)
	_expect(bool(embedded.get("ok", false)) and Vram.sniff(embedded.get("bytes", PackedByteArray())) == "image/png", "GLB bufferView image extracts without importing geometry")

func _record_fixture() -> WeakRef:
	Sources.set_recording(true)
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/vram/world.json"))
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_additional_data(Vram.PLAN_KEY, Vram.plan_for(manifest))
	var error := document.append_from_file("res://tests/fixtures/vram/world.glb", state)
	_expect(error == OK, "small map image fixture imports")
	if error != OK: return null
	Pool.share(state, manifest.externalResources)
	Sources.note(state, "res://tests/fixtures/vram/world.glb")
	var external := Sources.lookup(state.get_images()[0])
	var embedded := Sources.lookup(state.get_images()[6])
	for index: int in [0, 6]:
		fixture_origins[index] = Bindings.describe(state.get_images()[index])
	_expect(str(external.get("kind", "")) == "external" and not (external.get("inputs", []) as Array).is_empty(), "external image provenance names portable source input")
	_expect(str(embedded.get("kind", "")) == "gltf_image" and int(embedded.get("image_index", -1)) == 6, "embedded image provenance records GLB and image index")
	return weakref(state.get_images()[0])

func _sidecars_and_embedded() -> void:
	if not fixture_origins.has(0) or not fixture_origins.has(6): return
	var embedded: Dictionary = fixture_origins[6]
	var embedded_ready := Bindings.prepare({str(embedded.id): embedded.origin}, false)
	_expect(bool(embedded_ready.get("ok", false)) and embedded_ready.jobs.size() == 1
		and embedded_ready.jobs[0].image is Image, "embedded GLB preparation returns CPU image without loading its mesh")
	var description: Dictionary = fixture_origins[0]
	OS.set_environment("ELORIA_VRAM_TEXTURES", "force")
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	var ready := Bindings.prepare({str(description.id): description.origin}, false)
	_expect(bool(ready.get("ok", false)) and str(ready.jobs[0].kind) == "sidecar", "runtime chooses existing compatible sidecar dynamically")
	if not bool(ready.get("ok", false)): return
	var packed := _packed(str(description.id))
	_expect(Bindings.apply(packed, ready), "sidecar image publishes without conversion")
	var published: ImageTexture = ready.textures[str(description.id)]
	_expect(published.get_format() == Image.FORMAT_BPTC_RGBA, "compressed BC7 image is retained on publication")
	var expanded: Dictionary = description.origin.duplicate(true)
	expanded.roles = ["base", "base_cutout"]
	var private_ready := Bindings.prepare({str(description.id): expanded}, false)
	_expect(bool(private_ready.get("ok", false)) and str(private_ready.jobs[0].kind) == "decoded", "incompatible cutout role rejects opaque sidecar and pooled encoding")
	var private_packed := _packed(str(description.id))
	_expect(Bindings.apply(private_packed, private_ready), "role mismatch publishes a private decoded image")
	_expect((private_ready.textures[str(description.id)] as ImageTexture).get_format() == int(description.origin.decoded_format)
		and Pool._published(str(description.origin.image_sha256)) == published, "private fallback leaves existing pooled sidecar unchanged")
	Graphics._texture_skip = 1
	var half_ready := Bindings.prepare({str(description.id): description.origin}, false)
	var half_packed := _packed(str(description.id))
	_expect(bool(half_ready.get("ok", false)) and Bindings.apply(half_packed, half_ready), "reduced quality prepares and publishes without adopting wrong-sized pool resource")
	_expect((half_ready.textures[str(description.id)] as ImageTexture).get_width() == int(description.origin.width) / 2,
		"map quality slices compressed mip levels without decompression")
	Graphics._texture_skip = 0
	OS.set_environment("ELORIA_VRAM_TEXTURES", "0")
	Vram.reconfigure()

func _resolver(_texture: Texture2D) -> Dictionary:
	return {"path": PNG, "sha": FileAccess.get_sha256(PNG), "roles": ["base"]}

func _external_binding() -> void:
	var image := Image.create(8, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.25, 0.5, 0.75, 1.0))
	_expect(image.save_png(PNG) == OK, "small external texture fixture saves")
	image.generate_mipmaps()
	var original := ImageTexture.create_from_image(image)
	Sources.set_external_resolver(_resolver)
	var description := Bindings.describe(original)
	_expect(bool(description.get("ok", false)), "external resolver supplies portable binding")
	Sources.set_external_resolver(Callable())
	if not bool(description.get("ok", false)): return
	var alias: Dictionary = description.origin.duplicate(true)
	alias["file"] = DIRECTORY + "/alias.png"
	_expect(DirAccess.copy_absolute(PNG, str(alias.file)) == OK, "byte-identical alias fixture saves")
	alias["inputs"] = [{"path": alias.file, "sha256": alias.file_sha256}]
	alias["roles"] = ["emissive"]
	var merged := Bindings.merge_origin(description.origin, alias)
	_expect(bool(merged.get("ok", false)) and merged.origin.roles == ["base", "emissive"]
		and merged.origin.inputs.size() == 2, "same-image aliases and roles merge without changing slot identity")
	var descriptor_bindings := {str(description.id): merged.origin}
	var merged_ready := Bindings.prepare(descriptor_bindings, false)
	_expect(bool(merged_ready.get("ok", false)), "merged alias origin retains stable binding ID")
	merged_ready.clear()
	var bindings := {str(description.id): description.origin}
	var ready := Bindings.prepare(bindings, false)
	_expect(bool(ready.get("ok", false)) and ready.jobs.size() == 1, "external image prepares through production image decoder")
	if not bool(ready.get("ok", false)): return
	var packed := _packed(str(description.id))
	_expect(Bindings.apply(packed, ready), "material texture slots publish on main")
	var tree := packed.instantiate() as Node3D
	var material := (tree.get_node("Mesh") as MeshInstance3D).mesh.surface_get_material(0) as BaseMaterial3D
	_expect(material.albedo_texture.get_image().get_data() == image.get_data(), "published external texture retains every mip byte")
	_expect(is_equal_approx(material.normal_scale, 0.37) and material.uv1_scale == Vector3(2, 3, 1), "binding preserves material parameters")
	_expect(not bool(Bindings.prepare({"incorrect": description.origin}, false).get("ok", true)), "incorrect stable binding ID is rejected")
	tree.free()
	material = null
	packed = null
	ready.clear()
	var full_origin: Dictionary = description.origin.duplicate(true)
	full_origin.mip_policy = "full"
	var full_id := Bindings._identity(full_origin)
	Graphics._texture_skip = 1
	var full_ready := Bindings.prepare({full_id: full_origin}, false)
	var full_packed := _packed(full_id)
	_expect(bool(full_ready.get("ok", false)) and Bindings.apply(full_packed, full_ready)
		and (full_ready.textures[full_id] as Texture2D).get_width() == 8,
		"world-object full mip policy stays full when map texture quality is reduced")
	Graphics._texture_skip = 0

func _packed(id: String) -> PackedScene:
	var source := Node3D.new()
	var child := MeshInstance3D.new()
	child.name = "Mesh"
	var mesh := BoxMesh.new()
	var material := StandardMaterial3D.new()
	material.normal_scale = 0.37
	material.uv1_scale = Vector3(2, 3, 1)
	material.set_meta(Bindings.SLOT_META, {"albedo_texture": id})
	mesh.material = material
	child.mesh = mesh
	source.add_child(child)
	child.owner = source
	var packed := PackedScene.new()
	_expect(packed.pack(source) == OK, "synthetic geometry scene packs")
	source.free()
	return packed

func _prepare_worker(bindings: Dictionary) -> Dictionary:
	return Bindings.prepare(bindings, true)

func _apply_worker(packed: PackedScene, ready: Dictionary) -> Dictionary:
	var success := Bindings.apply(packed, ready)
	return {"success": success, "error": ready.get("error", "")}

func _constant_worker() -> void:
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.8, 0.4, 0.2, 1.0))
	var original := ImageTexture.create_from_image(image)
	var description := Bindings.describe(original)
	_expect(bool(description.get("ok", false)) and description.origin.kind == "constant", "tiny constants are explicit bounded origins")
	if not bool(description.get("ok", false)): return
	var main_ready := Bindings.prepare({str(description.id): description.origin}, true)
	_expect(bool(main_ready.get("ok", false)) and (main_ready.candidates as Dictionary).is_empty()
		and main_ready.jobs[0].image is Image, "main-thread preparation keeps CPU images even when worker scheduling is requested")
	main_ready.clear()
	var pool_publications := int(Pool.retention_snapshot().publications)
	var node_count := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var worker := Thread.new()
	_expect(worker.start(_prepare_worker.bind({str(description.id): description.origin})) == OK, "Resource texture worker starts")
	while worker.is_alive(): await process_frame
	var ready: Dictionary = worker.wait_to_finish()
	_expect(bool(ready.get("ok", false)) and ready.candidates[str(description.id)] is ImageTexture
		and not ready.jobs[0].has("image"), "worker returns normalized texture candidate and releases its CPU image")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == node_count
		and int(Pool.retention_snapshot().publications) == pool_publications,
		"Resource preparation constructs no Nodes and never publishes the texture pool")
	var packed := _packed(str(description.id))
	var reject_worker := Thread.new()
	_expect(reject_worker.start(_apply_worker.bind(packed, ready.duplicate())) == OK, "publication guard worker starts")
	while reject_worker.is_alive(): await process_frame
	var rejected: Dictionary = reject_worker.wait_to_finish()
	_expect(not bool(rejected.success) and str(rejected.error) == "texture_publication_requires_main", "off-main publication fails gracefully")
	_expect(Bindings.apply(packed, ready), "worker-prepared constant publishes on main")
	_expect((ready.candidates as Dictionary).is_empty(), "main publication releases private candidate carriers")

func _acquire_worker(path: String, digest: String) -> Dictionary:
	return Cache.acquire("asset", path, digest)

func _worker_source_revalidation() -> void:
	# Isolated user-data inputs exercise the actual cache boundary without
	# changing any authored world, native product or source asset.
	var path := DIRECTORY + "/worker-source.png"
	var image := Image.create(8, 8, false, Image.FORMAT_RGB8)
	image.fill(Color(0.31, 0.52, 0.73))
	_expect(image.save_png(path) == OK, "worker revalidation fixture saves")
	var sha := FileAccess.get_sha256(path)
	var origin := {"kind": "external", "file": path, "file_sha256": sha,
		"image_sha256": sha, "roles": ["base"], "decoded_format": Image.FORMAT_RGBA8,
		"width": 8, "height": 8, "mip_policy": "map", "inputs": [{"path": path, "sha256": sha}]}
	var id := Bindings._identity(origin)
	var packed := _packed(id)
	Cache.initialize()
	Cache._add_target("asset", path, "test-private-worker-source")
	DirAccess.make_dir_recursive_absolute(Cache.blobs_path())
	var temporary := Cache.blobs_path() + "/worker-fixture.scn"
	_expect(ResourceSaver.save(packed, temporary) == OK, "worker revalidation geometry saves")
	var payload_sha := FileAccess.get_sha256(temporary)
	var payload := Cache.blobs_path() + "/" + payload_sha + ".scn"
	if FileAccess.file_exists(payload): DirAccess.remove_absolute(temporary)
	else: _expect(DirAccess.rename_absolute(temporary, payload) == OK, "worker revalidation geometry enters private content store")
	var entry := {"schema": Cache.VERSION, "policy": Cache.policy(), "kind": "asset", "source": path,
		"source_digest": sha, "inputs": origin.inputs, "bindings": {id: origin},
		"primary": payload, "payloads": {payload: payload_sha}, "shared_meshes": {}}
	_expect(Cache.write_json(Cache.entry_path("asset", path), entry), "worker revalidation entry saves")
	var pool_publications := int(Pool.retention_snapshot().publications)
	var node_count := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var worker := Thread.new()
	_expect(worker.start(_acquire_worker.bind(path, sha)) == OK, "qualified native preparation worker starts")
	while worker.is_alive(): await process_frame
	var record: Dictionary = worker.wait_to_finish()
	_expect(str(record.get("status", "")) == "hit" and record.textures.candidates.get(id) is ImageTexture,
		"native worker retains private image candidate in completion record")
	if str(record.get("status", "")) != "hit": return
	_expect((record.textures.candidates[id] as ImageTexture).get_format() == Image.FORMAT_RGBA8,
		"worker normalizes decoded pixel format before upload")
	_expect(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == node_count
		and int(Pool.retention_snapshot().publications) == pool_publications,
		"native worker neither instantiates Nodes nor publishes texture candidates")
	var retained: WeakRef = weakref(record.textures.candidates[id])
	var prepared_policy := Bindings.runtime_policy()
	Graphics._texture_skip = 1
	_expect(Bindings.runtime_policy() != prepared_policy and Cache.instantiate(record) == null
		and not bool(record.get("bound", false)) and int(Pool.retention_snapshot().publications) == pool_publications,
		"unbound worker completion rejects a graphics policy switch before pool publication")
	Graphics._texture_skip = 0
	image.fill(Color(0.73, 0.52, 0.31))
	_expect(image.save_png(path) == OK, "isolated source changes after worker preparation")
	_expect(Cache.instantiate(record) == null and int(Pool.retention_snapshot().publications) == pool_publications,
		"full source revalidation rejects changed source before candidate publication or Nodes")
	record.clear()
	await process_frame
	_expect(retained.get_ref() == null and int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == node_count,
		"main-thread stale completion release drops private GPU candidate without constructing Nodes")
	Cache._targets.erase("asset|" + path)

func _imported_input() -> void:
	var image := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	image.fill(Color.WHITE)
	image.generate_mipmaps()
	var texture := ImageTexture.create_from_image(image)
	var path := DIRECTORY + "/imported.tres"
	_expect(ResourceSaver.save(texture, path) == OK, "native texture resource fixture saves")
	var sha := FileAccess.get_sha256(path)
	var origin := {"kind": "imported", "file": path, "file_sha256": sha, "load_path": path,
		"image_sha256": sha, "roles": [], "decoded_format": Image.FORMAT_RGBA8,
		"width": 4, "height": 4, "mip_policy": "preserve", "inputs": [{"path": path, "sha256": sha}]}
	var id := Bindings._identity(origin)
	var ready := Bindings.prepare({id: origin}, false)
	_expect(bool(ready.get("ok", false)) and ready.imported[id].get_image().get_data() == image.get_data(), "imported resource preserves native image/mip data")
	var product_only := origin.duplicate(true)
	product_only.file = DIRECTORY + "/absent-source.png"
	product_only.file_sha256 = ""
	var product_id := Bindings._identity(product_only)
	var product_ready := Bindings.prepare({product_id: product_only}, false)
	_expect(bool(product_ready.get("ok", false)) and product_ready.imported[product_id] is Texture2D,
		"verified native product loads when exported source PNG is absent")
	var changed := FileAccess.open(path, FileAccess.WRITE)
	changed.store_string("changed")
	changed.close()
	_expect(not bool(Bindings.prepare({id: origin}, false).get("ok", true)), "imported resource input mutation fails before cached ResourceLoader reuse")

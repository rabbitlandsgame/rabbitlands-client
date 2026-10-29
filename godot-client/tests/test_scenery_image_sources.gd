extends SceneTree
const Source := preload("res://src/world/scenery_image_sources.gd")
const WorldImages := preload("res://src/world/world_object_images.gd")
const MapImages := preload("res://src/world/map_image_extension.gd")
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Origins := preload("res://src/world/map_geometry_texture_sources.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
var failures := 0
var checks := 0
var fixture := ""

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

func _initialize() -> void:
	call_deferred("run")

func glb_bytes(document: Dictionary, binary: PackedByteArray) -> PackedByteArray:
	var text := JSON.stringify(document).to_utf8_buffer()
	while text.size() % 4: text.append(32)
	while binary.size() % 4: binary.append(0)
	var bytes := PackedByteArray()
	bytes.resize(20)
	bytes.encode_u32(0, 0x46546c67)
	bytes.encode_u32(4, 2)
	bytes.encode_u32(8, 28 + text.size() + binary.size())
	bytes.encode_u32(12, text.size())
	bytes.encode_u32(16, 0x4e4f534a)
	bytes.append_array(text)
	var header := PackedByteArray()
	header.resize(8)
	header.encode_u32(0, binary.size())
	header.encode_u32(4, 0x004e4942)
	bytes.append_array(header)
	bytes.append_array(binary)
	return bytes

func run() -> void:
	check(Vram.resource_root("", "D:/Games/Rabbit Lands/RabbitLands.exe") == "D:/Games/Rabbit Lands",
		"exported PCK root follows executable directory without app basename")
	check(Vram.resource_root("C:/arbitrary/project/", "D:/irrelevant.exe") == "C:/arbitrary/project",
		"editor resource root takes precedence over executable directory")
	fixture = ProjectSettings.globalize_path("res://assets/world/.local/scenery-contract-%d" % OS.get_process_id())
	Graphics._texture_skip = 2
	var image := Image.create(64, 64, false, Image.FORMAT_RGB8)
	image.fill(Color(0.2, 0.5, 0.8))
	var encoded := image.save_png_to_buffer()
	var sha := Source.digest(encoded)
	write(fixture.path_join("shared.png"), encoded)
	var descriptor := {"uri": "shared.png", "extras": {Vram.POLICY_DIRECTORY_EXTRA: ".", Source.ELIGIBLE_EXTRA: true}}
	var document := {"images": [descriptor], "textures": [{"source": 0}],
		"materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
		"extras": {Source.KEY: {"schema": Source.SCHEMA, "mipPolicy": "full",
			"resources": {"shared.png": sha}, "imagePolicies": {"shared.png": ["."]}}}}
	var verified := Source.verify_document(document, fixture)
	check(verified.ok and verified.tagged and verified.hash_reads == 1, "full encoded-byte closure verification")
	var state := GLTFState.new()
	state.set_base_path(fixture)
	state.set_json(document.duplicate(true))
	state.set_additional_data(WorldImages.ENABLED, true)
	state.set_additional_data(Source.VERIFIED_KEY, verified)
	var extension := WorldImages.new()
	check(extension._import_preflight(state, PackedStringArray()) == OK, "external scenery preflight")
	var prepared: Dictionary = state.get_additional_data(MapImages.PREPARED_KEY)
	var decoded: Image = prepared.get(0)
	check(decoded != null and decoded.get_width() == 64 and decoded.has_mipmaps(), "world retains all mips at quarter map quality")
	var output := Image.new()
	var mime: String = state.get_json().images[0].mimeType
	extension._parse_image_data(state, PackedByteArray([0]), mime, output)
	check(output.get_width() == 64 and int(state.get_additional_data(WorldImages.PREPARED)) == 1,
		"handled image count avoids fallback GPU readback")
	var keys: Dictionary = state.get_additional_data(Vram.POOL_KEYS_KEY)
	check(str(keys[0]).ends_with("mip-skip=0"), "world raw variant uses effective skip zero")
	var texture := ImageTexture.create_from_image(output)
	Pool._publish_or_adopt(str(keys[0]), texture)
	var held_state := GLTFState.new()
	held_state.set_base_path(fixture)
	held_state.set_json(document.duplicate(true))
	held_state.set_additional_data(WorldImages.ENABLED, true)
	held_state.set_additional_data(Source.VERIFIED_KEY, verified)
	var held_extension := WorldImages.new()
	held_extension._import_preflight(held_state, PackedStringArray())
	var placeholder := Image.new()
	held_extension._parse_image_data(held_state, PackedByteArray([0]), str(held_state.get_json().images[0].mimeType), placeholder)
	check(int(held_state.get_additional_data(WorldImages.PREPARED)) == 1 and placeholder.get_width() == 1,
		"pooled image counts as handled without reading texture pixels")
	var origin := {"kind": "external", "file": Origins.logical_source(fixture.path_join("shared.png")),
		"file_sha256": sha, "image_sha256": sha, "roles": ["base"], "mip_policy": "full",
		"policy_directory": Origins.logical_source(fixture), "sidecar_eligible": true,
		"decoded_format": Image.FORMAT_RGB8, "width": 64, "height": 64,
		"inputs": [{"path": Origins.logical_source(fixture.path_join("shared.png")), "sha256": sha}]}
	check(Bindings._origin_error(origin).is_empty(), "native accepts explicit world directory provenance")
	check(Bindings._pool_key(origin, {"base": true}) == str(keys[0]), "native and raw full-mip representation keys agree")
	var job := {"origin": origin, "source": fixture.path_join("shared.png"), "sidecar": {}}
	Bindings._prepare_job(job)
	check(job.image.get_width() == 64 and job.image.has_mipmaps(), "native external preparation retains full mips")
	var changed := encoded.duplicate()
	changed[changed.size() - 1] ^= 1
	write(fixture.path_join("shared.png"), changed)
	check(not Source.verify_document(document, fixture).ok, "same-path external mutation rejects fresh acceptance")
	write(fixture.path_join("shared.png"), encoded)
	var bad := document.duplicate(true)
	bad.images[0].extras[Vram.POLICY_DIRECTORY_EXTRA] = "../actors"
	check(not Source.verify_document(bad, fixture).ok, "policy outside original world directory fails closed")
	bad = document.duplicate(true)
	bad.images[0].extras[Vram.POLICY_DIRECTORY_EXTRA] = "%2e"
	check(not Source.verify_document(bad, fixture).ok, "encoded policy paths fail closed")
	bad = document.duplicate(true)
	bad.extras[Source.KEY].imagePolicies["shared.png"] = [".", ".."]
	check(not Source.verify_document(bad, fixture).ok, "aggregate cannot add a different original policy directory")
	# Exercise the real importer with both globally registered extensions. This
	# catches extension ordering, restoration, normalized material carriers and
	# the PREPARED threshold used by GlbSceneCache's no-readback worker path.
	Quantization.ensure_registered()
	Vram.ensure_registered()
	var real := document.duplicate(true)
	var geometry := PackedFloat32Array([0,0,0, 1,0,0, 0,1,0]).to_byte_array()
	real.asset = {"version": "2.0"}
	real.buffers = [{"byteLength": geometry.size()}]
	real.bufferViews = [{"buffer": 0, "byteOffset": 0, "byteLength": geometry.size()}]
	real.accessors = [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0,0,0], "max": [1,1,0]}]
	real.meshes = [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}]
	real.nodes = [{"mesh": 0}]
	real.scenes = [{"nodes": [0]}]
	real.scene = 0
	var raw_state := GLTFState.new()
	raw_state.set_additional_data(WorldImages.ENABLED, true)
	var importer := GLTFDocument.new()
	check(importer.append_from_buffer(glb_bytes(real, geometry), fixture + "/", raw_state) == OK, "real ordinary GLB imports with both extensions")
	check(int(raw_state.get_additional_data(WorldImages.PREPARED)) == raw_state.get_images().size(),
		"real import handles every image before any fallback readback")
	check(raw_state.get_json().images[0].uri == "shared.png" and raw_state.get_images()[0] != null and raw_state.get_images()[0].get_width() == 64,
		"real import restores URI and replaces pooled placeholder")
	DirAccess.remove_absolute(fixture.path_join("shared.png"))
	DirAccess.remove_absolute(fixture)
	print("SCENERY IMAGE SOURCES: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

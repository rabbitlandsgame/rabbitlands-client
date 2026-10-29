extends SceneTree
## A valid captured closure is deliberately made stale before the raw decode.
## Expected negative imports emit Godot's postparse failure diagnostic.
const Cache := preload("res://src/actors/glb_scene_cache.gd")
const Source := preload("res://src/world/scenery_image_sources.gd")
const WorldImages := preload("res://src/world/world_object_images.gd")
const MapImages := preload("res://src/world/map_image_extension.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
var checks := 0
var failures := 0

func check(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: " + label)
	else:
		failures += 1
		push_error("scenery decode integrity: " + label)

func write(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()

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

func _init() -> void:
	run.call_deferred()

func run() -> void:
	var directory := Vram.runtime_absolute("res://assets/world/underground/vram/scenery-decode-integrity-%d" % OS.get_process_id())
	var path := directory.path_join("fixture.glb")
	var image_path := directory.path_join("shared.png")
	var a := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	a.fill(Color(0.25, 0.5, 0.75, 1))
	var a_bytes := a.save_png_to_buffer()
	var a_sha := Source.digest(a_bytes)
	var b := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	b.fill(Color(0.75, 0.5, 0.25, 1))
	var b_bytes := b.save_png_to_buffer()
	var geometry := PackedFloat32Array([0,0,0, 1,0,0, 0,1,0]).to_byte_array()
	var document := {"asset": {"version": "2.0"}, "buffers": [{"byteLength": geometry.size()}],
		"bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": geometry.size()}],
		"accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0,0,0], "max": [1,1,0]}],
		"images": [{"uri": "shared.png", "mimeType": "image/png", "extras": {
			Vram.POLICY_DIRECTORY_EXTRA: ".", Source.ELIGIBLE_EXTRA: true}}],
		"textures": [{"source": 0}], "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
		"meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
		"nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
		"extras": {Source.KEY: {"schema": Source.SCHEMA, "mipPolicy": "full",
			"resources": {"shared.png": a_sha}, "imagePolicies": {"shared.png": ["."]}}}}
	write(path, glb_bytes(document, geometry))
	write(image_path, a_bytes)
	var verified := Source.verify(path)
	check(bool(verified.get("ok", false)), "capture verified A closure before mutation")
	var previous_skip := Graphics._texture_skip
	Graphics._texture_skip = 2
	var previous_mode := OS.get_environment(Vram.ENVIRONMENT)
	OS.set_environment(Vram.ENVIRONMENT, "0")
	Vram.reconfigure()
	Quantization.ensure_registered()
	Vram.ensure_registered()
	var key := Vram.variant_pool_key(a_sha, {}, directory, 0)
	check(Pool._published(key) == null, "A representation is not already pooled")
	write(image_path, b_bytes)
	var state := GLTFState.new()
	state.set_additional_data(WorldImages.ENABLED, true)
	state.set_additional_data(Source.VERIFIED_KEY, verified)
	var importer := GLTFDocument.new()
	var result := importer.append_from_buffer(verified.bytes, directory + "/", state)
	check(result != OK, "actual GLTF import fails when decode read differs from captured verification")
	var errors: Dictionary = state.get_additional_data(MapImages.SOURCE_ERRORS_KEY)
	check(WorldImages.has_source_errors(state) and errors.get(0) == "source_sha256", "strict source mismatch remains an explicit state failure")
	check(WorldImages.new()._import_post_parse(state) == ERR_FILE_CORRUPT, "postparse also fails for direct extension callers")
	check(Pool._published(key) == null, "changed B pixels never enter A shared-pool identity")
	check(Cache._build_raw(path, verified) == null, "raw scene builder rejects captured-proof mismatch before generating a scene")
	check(Pool._published(key) == null, "raw rejection cannot publish a decoder fallback or sentinel")
	var native_job := {"origin": {"kind": "external", "mip_policy": "full", "image_sha256": a_sha},
		"source": image_path, "sidecar": {}}
	Bindings._prepare_job(native_job)
	check(native_job.get("image") == null and native_job.get("error") == "external_texture_source_changed",
		"native external-image preparation rejects the same stale-source read")
	write(image_path, a_bytes)
	var restored := Source.verify(path)
	check(restored.get("closure_token") == verified.get("closure_token"), "restored A has the original valid closure")
	var packed := Cache._build_raw(path, restored)
	check(packed != null, "restored A imports after rejected B without poisoned reuse")
	var actual := Pool._published(key)
	var actual_image := actual.get_image() if actual != null else null
	a.generate_mipmaps()
	check(actual_image != null and actual_image.get_width() == 64 and actual_image.has_mipmaps()
		and actual_image.get_data() == a.get_data(), "restored pooled A has exact full-mip pixels at quarter map quality")
	# Strict failures other than a digest mismatch must not take the legacy URI
	# fallback either: a declared but undecodable image rejects the whole model.
	var undecodable := PackedByteArray([1, 2, 3, 4])
	var bad_sha := Source.digest(undecodable)
	write(image_path, undecodable)
	document.extras[Source.KEY].resources["shared.png"] = bad_sha
	write(path, glb_bytes(document, geometry))
	var bad_verified := Source.verify(path)
	check(bool(bad_verified.get("ok", false)) and Cache._build_raw(path, bad_verified) == null,
		"strict matching-SHA decode failure also rejects the scene")
	check(Pool._published(Vram.variant_pool_key(bad_sha, {}, directory, 0)) == null,
		"undecodable source cannot publish a fallback under its declared hash")
	DirAccess.remove_absolute(path)
	DirAccess.remove_absolute(image_path)
	DirAccess.remove_absolute(directory)
	Graphics._texture_skip = previous_skip
	OS.set_environment(Vram.ENVIRONMENT, previous_mode)
	Vram.reconfigure()
	print("SCENERY DECODE INTEGRITY: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

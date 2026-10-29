extends SceneTree
## Real raw scene handoffs with valid, changing loose scenery inputs. No import
## products, production models, native cache entries or renderer are required.
const Cache := preload("res://src/actors/glb_scene_cache.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Source := preload("res://src/world/scenery_image_sources.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
var checks := 0
var failures := 0
var directory := ""

func _init() -> void:
	run.call_deferred()

func check(value: bool, label: String) -> void:
	checks += 1
	if value:
		print("PASS: " + label)
	else:
		failures += 1
		push_error("scenery cache inputs: " + label)

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

func fixture(path: String, identity: String, color: Color) -> void:
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	image.fill(color)
	var encoded := image.save_png_to_buffer()
	write(directory.path_join("shared.png"), encoded)
	var positions := PackedFloat32Array([0,0,0, 1,0,0, 0,1,0]).to_byte_array()
	var normals := PackedFloat32Array([0,0,1, 0,0,1, 0,0,1]).to_byte_array()
	var uvs := PackedFloat32Array([0,0, 1,0, 0,1]).to_byte_array()
	var binary := positions + normals + uvs
	var document := {
		"asset": {"version": "2.0"}, "buffers": [{"byteLength": binary.size()}],
		"bufferViews": [
			{"buffer": 0, "byteOffset": 0, "byteLength": positions.size()},
			{"buffer": 0, "byteOffset": positions.size(), "byteLength": normals.size()},
			{"buffer": 0, "byteOffset": positions.size() + normals.size(), "byteLength": uvs.size()}],
		"accessors": [
			{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0,0,0], "max": [1,1,0]},
			{"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
			{"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"}],
		"images": [{"uri": "shared.png", "mimeType": "image/png", "extras": {
			Vram.POLICY_DIRECTORY_EXTRA: ".", Source.ELIGIBLE_EXTRA: true}}],
		"textures": [{"source": 0}],
		"materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
		"meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "material": 0}]}],
		"nodes": [{"mesh": 0, "name": identity}], "scenes": [{"nodes": [0]}], "scene": 0,
		"extras": {Source.KEY: {"schema": Source.SCHEMA, "mipPolicy": "full",
			"resources": {"shared.png": Source.digest(encoded)}, "imagePolicies": {"shared.png": ["."]}}}}
	write(path, glb_bytes(document, binary))

func verification_count() -> int:
	var timings: Dictionary = Cache.retention_snapshot().timings
	var operations: Dictionary = timings.get("operations", {})
	return int((operations.get(&"scenery_source_verify", {}) as Dictionary).get("count", 0))

func mesh_in(root: Node) -> MeshInstance3D:
	if root is MeshInstance3D: return root as MeshInstance3D
	return root.find_child("*", true, false) as MeshInstance3D

func check_image(root: Node3D, expected: Color, label: String) -> void:
	var mesh := mesh_in(root)
	var material := mesh.mesh.surface_get_material(0) as StandardMaterial3D if mesh != null else null
	var texture: Texture2D = material.albedo_texture if material != null else null
	var image := texture.get_image() if texture != null else null
	check(image != null and image.get_width() == 64 and image.has_mipmaps(), label + " retains full image and mip chain")
	check(image != null and image.get_pixel(0, 0).is_equal_approx(expected), label + " has the matching image bytes")

func run() -> void:
	var previous_skip := Graphics._texture_skip
	var environment := {}
	for key: String in ["RABBITLANDS_PREPARED_CONTENT", "ELORIA_NO_GEOMETRY_CACHE", Vram.ENVIRONMENT]:
		environment[key] = OS.get_environment(key)
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", "1")
	OS.set_environment(Vram.ENVIRONMENT, "0")
	Vram.reconfigure()
	Cache.clear()
	var parent := ProjectSettings.globalize_path("res://assets/world/underground/vram/scenery-cache-inputs-%d" % OS.get_process_id())
	directory = parent.path_join("fixture with space")
	var path := directory.path_join("fixture.glb")
	var before_color := Color(0, 0, 1, 1)
	var after_color := Color(0, 1, 0, 1)
	fixture(path, "BeforePublication", before_color)
	var verified := Source.verify(path)
	check(bool(verified.get("ok", false)) and bool(verified.get("tagged", false)), "synthetic scenery has a valid external image closure")
	Graphics._texture_skip = 0
	var world_full := Prepared.scene_texture_token(path, verified)
	var actor_full := Prepared.scene_texture_token("res://assets/actors/cache-token-fixture.glb")
	Graphics._texture_skip = 2
	check(Prepared.scene_texture_token(path, verified) == world_full and "world-full-mips" in world_full,
		"scenery texture token is invariant between full and quarter map quality")
	check(Prepared.scene_texture_token("res://assets/actors/cache-token-fixture.glb") != actor_full,
		"actor texture token retains its legacy quality distinction")
	var prepared := Cache.prepare(PackedStringArray([path]))
	var handoff: Dictionary = prepared.get(path, {})
	check(handoff.get("raw_scene") is PackedScene and handoff.get("source_sha256") == verified.source_sha256,
		"prepare captures a real raw scene and its current source bytes")
	Cache.install_prepared(prepared)
	check(Cache.packed_scene(path) == handoff.get("raw_scene"), "unchanged valid handoff publishes its captured immutable scene")
	var warm_began := verification_count()
	var warm_instances := 0
	for _placement: int in 10:
		var instance := Cache.instantiate(path)
		if instance != null:
			warm_instances += 1
			instance.free()
	check(warm_instances == 10, "ten warm placements instantiate the installed scene")
	check(verification_count() == warm_began, "ten warm placements add zero scenery source verification reads")
	Cache.clear()
	prepared = Cache.prepare(PackedStringArray([path]))
	handoff = prepared.get(path, {})
	var captured := handoff.get("raw_scene") as PackedScene
	check(captured != null, "second detached handoff captures the original scene")
	fixture(path, "CurrentAtPublication", after_color)
	var current := Source.verify(path)
	check(bool(current.get("ok", false)) and current.get("source_sha256") != verified.source_sha256
		and current.get("closure_token") != verified.closure_token, "replacement image plus updated GLB are a different valid source closure")
	Cache.install_prepared(prepared)
	var published := Cache.packed_scene(path)
	check(published != null and published != captured, "publication discards a valid but stale raw scene snapshot")
	var actual := Cache.instantiate(path)
	var old := captured.instantiate() as Node3D if captured != null else null
	check(actual != null and mesh_in(actual) != null and str(mesh_in(actual).name) == "CurrentAtPublication",
		"publication builds the current GLB rather than the captured node tree")
	if actual != null: check_image(actual, after_color, "current published scene")
	if old != null: check_image(old, before_color, "captured scene")
	if actual != null: actual.free()
	if old != null: old.free()
	Cache.clear()
	DirAccess.remove_absolute(path)
	DirAccess.remove_absolute(directory.path_join("shared.png"))
	DirAccess.remove_absolute(directory)
	DirAccess.remove_absolute(parent)
	Graphics._texture_skip = previous_skip
	for key: String in environment: OS.set_environment(key, environment[key])
	Vram.reconfigure()
	print("SCENERY CACHE INPUTS: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

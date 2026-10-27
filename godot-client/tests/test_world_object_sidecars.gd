extends SceneTree

## World-object (scenery) GLBs embed their images; when the GLB's directory
## has a vram/index.json listing an embedded image by the sha256 of its bytes,
## WorldObjectImages uploads that pre-compressed sidecar instead of decoding
## (src/world/world_object_images.gd; tools/build_vram_textures.py
## --scenery-config writes the folder). Any doubt decodes, as before.
##
## Builds small GLBs under user:// that embed images of tests/fixtures/vram
## (whose committed vram/ has a BC7 sidecar for the opaque base colour and a
## BC5 one for the normal map) and copies that vram/ folder beside them.
##
## Run: Godot_v4.7.2-stable_win64_console.exe --headless --path . \
##         --script res://tests/test_world_object_sidecars.gd

const VramTextures := preload("res://src/world/vram_textures.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const WorldObjectImages := preload("res://src/world/world_object_images.gd")

const FIXTURE := "res://tests/fixtures/vram/shared-assets"
## The fixture's opaque base colour (BC7 sidecar, roles [base]) and normal map (BC5, roles [normal]).
const BASE := "90c51de41c0f4fffd8a6c225f67472eb77d262a183e2fcae827383d3e10d32f4.jpg"
const NORMAL := "5168b5c2d5238b41c0b8b9626b2987775d00fe27f953b84aa9bb8bc7f11349ab.png"
const SCRATCH := "user://world-object-sidecars-test"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)
	return ok

func _set_mode(value: String) -> void:
	OS.set_environment(VramTextures.ENVIRONMENT, value)
	VramTextures.reconfigure()

func _run() -> void:
	GltfQuantization.ensure_registered()
	VramTextures.ensure_registered()
	_remove_tree(SCRATCH)
	var base := FileAccess.get_file_as_bytes(FIXTURE.path_join(BASE))
	var normal := FileAccess.get_file_as_bytes(FIXTURE.path_join(NORMAL))
	_expect(not base.is_empty() and not normal.is_empty(), "the fixture images read")
	# A prop sampling the base colour and the normal map as encoded.
	var prop := _glb([[base, "image/jpeg"], [normal, "image/png"]],
		[{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}, "normalTexture": {"index": 1}}])
	# The same base-colour bytes sampled as a normal map: not what the sidecar was encoded for.
	var misused := _glb([[base, "image/jpeg"]], [{"normalTexture": {"index": 0}}])
	var with_index := _directory("indexed", true)
	var without_index := _directory("plain", false)
	_write(with_index.path_join("prop.glb"), prop)
	_write(with_index.path_join("misused.glb"), misused)
	_write(without_index.path_join("prop.glb"), prop)

	_set_mode("force")
	var result := _parse(with_index.path_join("prop.glb"))
	_expect(result.formats == [Image.FORMAT_BPTC_RGBA, Image.FORMAT_RGTC_RG],
		"sidecars upload compressed: BC7 base colour, BC5 normal (%s)" % str(result.formats))
	_expect(result.sidecars == 2 and result.prepared == 2,
		"both images counted as prepared from sidecars, so GlbSceneCache reads nothing back (%d/%d)" % [
			result.sidecars, result.prepared])
	_expect(result.mipmaps.all(func(value: bool) -> bool: return value), "sidecar images carry their mip chain")
	_expect(result.scene_ok, "the scene generates from the compressed images")

	var decoded := _parse(without_index.path_join("prop.glb"))
	_expect(decoded.sidecars == 0 and decoded.prepared == 2 and _uncompressed(decoded.formats),
		"a directory without vram/ decodes as before (%s)" % str(decoded.formats))
	_expect(decoded.mipmaps.all(func(value: bool) -> bool: return value), "decoded images get their mip chain")

	var wrong_role := _parse(with_index.path_join("misused.glb"))
	_expect(wrong_role.sidecars == 0 and wrong_role.prepared == 1 and _uncompressed(wrong_role.formats),
		"an image sampled in a role its sidecar was not encoded for decodes (%s)" % str(wrong_role.formats))

	_set_mode("0")
	var off := _parse(with_index.path_join("prop.glb"))
	_expect(off.sidecars == 0 and off.prepared == 2 and _uncompressed(off.formats),
		"ELORIA_VRAM_TEXTURES=0 decodes every image (%s)" % str(off.formats))

	_set_mode("")
	VramTextures.force_formats(0)
	var no_formats := _parse(with_index.path_join("prop.glb"))
	_expect(no_formats.sidecars == 0 and _uncompressed(no_formats.formats),
		"a renderer without BC formats decodes (%s)" % str(no_formats.formats))

	_set_mode("force")
	var corrupt := _directory("corrupt", true)
	_write(corrupt.path_join("prop.glb"), prop)
	var sidecar := corrupt.path_join("vram").path_join(BASE.get_basename() + ".base.evt")
	var bytes := FileAccess.get_file_as_bytes(sidecar)
	bytes[bytes.size() - 1] = bytes[bytes.size() - 1] ^ 0xFF
	_write(sidecar, bytes)
	var damaged := _parse(corrupt.path_join("prop.glb"))
	_expect(damaged.formats.size() == 2 and _uncompressed([damaged.formats[0]])
		and damaged.formats[1] == Image.FORMAT_RGTC_RG and damaged.sidecars == 1 and damaged.prepared == 2,
		"a corrupt sidecar decodes that image only (%s)" % str(damaged.formats))

	_set_mode("")
	_remove_tree(SCRATCH)
	print("world object sidecars tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

static func _uncompressed(formats: Array) -> bool:
	return not formats.is_empty() and formats.all(func(format: int) -> bool:
		return format in [Image.FORMAT_RGB8, Image.FORMAT_RGBA8])

## Parses a GLB the way GlbSceneCache._build_raw does for a world asset.
func _parse(path: String) -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_additional_data(WorldObjectImages.ENABLED, true)
	var error := document.append_from_file(ProjectSettings.globalize_path(path), state)
	var formats: Array = []
	var mipmaps: Array = []
	for texture: Variant in state.get_images():
		var image_texture := texture as ImageTexture
		formats.append(image_texture.get_format() if image_texture != null else -1)
		var image := image_texture.get_image() if image_texture != null else null
		mipmaps.append(image != null and image.has_mipmaps())
	var scene := document.generate_scene(state) if error == OK else null
	var scene_ok := scene != null
	if scene != null:
		scene.free()
	return {"error": error, "formats": formats, "mipmaps": mipmaps, "scene_ok": scene_ok,
		"sidecars": int(state.get_additional_data(WorldObjectImages.SIDECARS)),
		"prepared": int(state.get_additional_data(WorldObjectImages.PREPARED))}

func _directory(name: String, sidecars: bool) -> String:
	var directory := SCRATCH.path_join(name)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory.path_join("vram") if sidecars else directory))
	if sidecars:
		for file: String in DirAccess.get_files_at(FIXTURE.path_join("vram")):
			if file == "index.json" or file.ends_with(".evt"):
				_write(directory.path_join("vram").path_join(file),
					FileAccess.get_file_as_bytes(FIXTURE.path_join("vram").path_join(file)))
	return directory

func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()

func _remove_tree(path: String) -> void:
	var absolute := ProjectSettings.globalize_path(path)
	if not DirAccess.dir_exists_absolute(absolute):
		return
	for directory: String in DirAccess.get_directories_at(absolute):
		_remove_tree(path.path_join(directory))
	for file: String in DirAccess.get_files_at(absolute):
		DirAccess.remove_absolute(absolute.path_join(file))
	DirAccess.remove_absolute(absolute)

## A GLB with one triangle per material and every image embedded in the BIN chunk.
static func _glb(images: Array, materials: Array) -> PackedByteArray:
	var binary := PackedByteArray()
	var views: Array = []
	var positions := PackedFloat32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]).to_byte_array()
	var uvs := PackedFloat32Array([0, 0, 1, 0, 0, 1]).to_byte_array()
	for payload: PackedByteArray in [positions, uvs]:
		views.append({"buffer": 0, "byteOffset": binary.size(), "byteLength": payload.size()})
		binary.append_array(payload)
	var image_list: Array = []
	var textures: Array = []
	for pair: Array in images:
		while binary.size() % 4:
			binary.append(0)
		var payload: PackedByteArray = pair[0]
		image_list.append({"bufferView": views.size(), "mimeType": pair[1]})
		textures.append({"source": textures.size()})
		views.append({"buffer": 0, "byteOffset": binary.size(), "byteLength": payload.size()})
		binary.append_array(payload)
	while binary.size() % 4:
		binary.append(0)
	var primitives: Array = []
	for index: int in materials.size():
		primitives.append({"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "material": index})
	var document := {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
		"nodes": [{"mesh": 0, "name": "prop"}], "meshes": [{"primitives": primitives}],
		"materials": materials, "textures": textures, "images": image_list,
		"accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
			"min": [0, 0, 0], "max": [1, 1, 0]}, {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"}],
		"bufferViews": views, "buffers": [{"byteLength": binary.size()}]}
	var json := JSON.stringify(document).to_utf8_buffer()
	while json.size() % 4:
		json.append(0x20)
	var out := PackedByteArray()
	out.append_array("glTF".to_ascii_buffer())
	out.append_array(_u32(2))
	out.append_array(_u32(12 + 8 + json.size() + 8 + binary.size()))
	out.append_array(_u32(json.size()))
	out.append_array("JSON".to_ascii_buffer())
	out.append_array(json)
	out.append_array(_u32(binary.size()))
	out.append_array(PackedByteArray([0x42, 0x49, 0x4E, 0x00]))
	out.append_array(binary)
	return out

static func _u32(value: int) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.resize(4)
	bytes.encode_u32(0, value)
	return bytes

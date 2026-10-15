extends SceneTree

## The VRAM texture sidecars on a real renderer (the headless tests run on the
## dummy renderer, where `get_image()` only checks the CPU Image and the
## format query is forced).
##
## Loads tests/fixtures/vram in the default (automatic) mode and checks:
## - the renderer reports the BC formats it samples (RenderingDevice on
##   Forward+/Mobile, the GL driver on Compatibility), and at least one;
## - every fixture image whose sidecar format the renderer samples is that
##   format ON THE GPU with its whole mip chain (RenderingDevice texture format
##   on Forward+, the texture read back from GL on Compatibility), and every
##   other image is uncompressed with mips;
## - the frame drawn from the sidecars matches the frame drawn from the
##   decoded images (ELORIA_VRAM_TEXTURES=0) within a few levels, and has no
##   missing-texture magenta.
##
## Run (needs a display; CI: xvfb + Mesa, gl_compatibility):
##   Godot_v4.7.2-stable_win64_console.exe --audio-driver Dummy \
##     --rendering-method gl_compatibility --path . \
##     --script res://tests/integration/rendered_vram_textures.gd

const VramTextures := preload("res://src/world/vram_textures.gd")

const FIXTURE := "res://tests/fixtures/vram/world.json"
const INDEX := "res://tests/fixtures/vram/shared-assets/vram/index.json"
## Material -> the fixture image (glTF index) each texture slot samples.
const SLOTS := {"opaque": {"albedo_texture": 0, "normal_texture": 2, "roughness_texture": 3},
	"cutout": {"albedo_texture": 1}, "odd": {"albedo_texture": 4}}
const RD_FORMATS := {"bc1": [RenderingDevice.DATA_FORMAT_BC1_RGB_UNORM_BLOCK,
		RenderingDevice.DATA_FORMAT_BC1_RGB_SRGB_BLOCK, RenderingDevice.DATA_FORMAT_BC1_RGBA_UNORM_BLOCK,
		RenderingDevice.DATA_FORMAT_BC1_RGBA_SRGB_BLOCK],
	"bc5": [RenderingDevice.DATA_FORMAT_BC5_UNORM_BLOCK],
	"bc7": [RenderingDevice.DATA_FORMAT_BC7_UNORM_BLOCK, RenderingDevice.DATA_FORMAT_BC7_SRGB_BLOCK]}
## Mean channel difference allowed between the sidecar and decoded frames.
const MAX_MEAN_DIFF := 4.0

var failures := 0
var _stage: Node3D
var _camera: Camera3D

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)
	return ok

func _run() -> void:
	OS.set_environment("ELORIA_LOOK", "0")
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	OS.set_environment(VramTextures.ENVIRONMENT, "")
	VramTextures.reconfigure()
	root.size = Vector2i(512, 512)
	_build_stage()
	VramTextures.ensure_registered()
	var method := RenderingServer.get_current_rendering_method()
	var formats := VramTextures.usable_formats()
	print("renderer ", method, " ", RenderingServer.get_video_adapter_name(), " ",
		RenderingServer.get_video_adapter_api_version())
	print(VramTextures.status_line())
	_expect(method != "dummy" and DisplayServer.get_name() != "headless",
		"runs on a real renderer (%s, display %s)" % [method, DisplayServer.get_name()])
	_expect(formats != 0, "the renderer samples at least one BC format (%s)" % VramTextures.format_names(formats))

	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FIXTURE))
	var uris: Array = (manifest.externalResources as Dictionary).keys()
	var sidecar_frame := await _load_and_check(index, formats)
	OS.set_environment(VramTextures.ENVIRONMENT, "0")
	VramTextures.reconfigure()
	var decoded_frame := await _load_and_check(index, 0)
	OS.set_environment(VramTextures.ENVIRONMENT, "")
	VramTextures.reconfigure()
	if sidecar_frame != null and decoded_frame != null:
		_compare(sidecar_frame, decoded_frame)
	print("uris ", uris.size())
	print("rendered vram textures: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

func _build_stage() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.1, 0.1, 0.1)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.6, 0.6, 0.6)
	_stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-70, 20, 0)
	_stage.add_child(light)
	# Straight down on the first three quads (opaque, cutout, odd: x 0, 2.5, 5).
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 7.4
	_camera.position = Vector3(2.5, 10, 0)
	_camera.rotation_degrees = Vector3(-90, 0, 0)
	_camera.current = true
	_stage.add_child(_camera)

## Loads the fixture, checks each texture's GPU format against what the
## renderer samples, draws a frame and returns it (or null).
func _load_and_check(index: Dictionary, formats: int) -> Image:
	var mode := VramTextures.mode_name()
	var loader := WorldLoader.new()
	_stage.add_child(loader)
	loader.load_world(FIXTURE)
	if not _expect(loader.world_root != null, "mode=%s: the fixture loads" % mode):
		loader.queue_free()
		return null
	for frame: int in 4:
		await process_frame
	var images: Array = (JSON.parse_string(FileAccess.get_file_as_string(FIXTURE)).externalResources as Dictionary).values()
	var expected_sidecars := 0
	var right := 0
	var checked := 0
	var details: Array = []
	for material_name: String in SLOTS:
		var material := _material(loader.world_root, material_name)
		if not _expect(material != null, "mode=%s: material %s is in the fixture" % [mode, material_name]):
			continue
		for slot: String in SLOTS[material_name]:
			var texture: Texture2D = material.get(slot)
			var sha := _sha_of(int(SLOTS[material_name][slot]))
			var entry: Dictionary = (index.images as Dictionary).get(sha, {})
			var want := ""
			if not entry.is_empty() and formats & int(VramTextures.FORMAT_BITS[str(entry.format)]):
				want = str(entry.format)
				expected_sidecars += 1
			var got := _gpu_format(texture)
			checked += 1
			details.append("%s.%s=%s(%s)" % [material_name, slot, got.name, got.levels])
			var ok: bool
			if want.is_empty():
				ok = got.name == "uncompressed" and int(got.levels) > 1
			else:
				ok = got.name == want and int(got.levels) == int(entry.mipmaps) + 1
			if ok:
				right += 1
	_expect(checked == 5 and right == checked,
		"mode=%s: every texture is on the GPU in the format the renderer samples, with its mips (%d sidecars expected): %s"
		% [mode, expected_sidecars, details])
	_expect(images.size() == 7, "the fixture names 7 external images")
	RenderingServer.force_draw(false)
	await process_frame
	RenderingServer.force_draw(false)
	var frame := root.get_texture().get_image()
	loader.unload_world()
	loader.queue_free()
	await process_frame
	return frame

func _material(world: Node, material_name: String) -> BaseMaterial3D:
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			if material != null and material.resource_name == material_name:
				return material
	return null

func _sha_of(image_index: int) -> String:
	# The GLB's JSON chunk only: parsing the document would decode every image.
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(FIXTURE))
	var bytes := FileAccess.get_file_as_bytes(FIXTURE.get_base_dir().path_join("world.glb"))
	var document: Dictionary = JSON.parse_string(bytes.slice(20, 20 + bytes.decode_u32(12)).get_string_from_utf8())
	return str(manifest.externalResources.get(str(document.images[image_index].uri), ""))

## {name: bc1|bc5|bc7|uncompressed|unknown, levels} of the texture as the GPU
## holds it.
func _gpu_format(texture: Texture2D) -> Dictionary:
	if texture == null:
		return {"name": "missing", "levels": 0}
	var device := RenderingServer.get_rendering_device()
	if device != null:
		var format := device.texture_get_format(RenderingServer.texture_get_rd_texture(texture.get_rid()))
		for name: String in RD_FORMATS:
			if (RD_FORMATS[name] as Array).has(format.format):
				return {"name": name, "levels": format.mipmaps}
		return {"name": "uncompressed" if format.format < RenderingDevice.DATA_FORMAT_BC1_RGB_UNORM_BLOCK else "unknown",
			"levels": format.mipmaps}
	# Compatibility: read the texture back from GL (glGetCompressedTexImage for
	# a compressed one), which is also how the map cache saves it there.
	var image := texture.get_image()
	if image == null:
		return {"name": "missing", "levels": 0}
	var names := {Image.FORMAT_DXT1: "bc1", Image.FORMAT_RGTC_RG: "bc5", Image.FORMAT_BPTC_RGBA: "bc7"}
	return {"name": names.get(image.get_format(), "uncompressed" if not image.is_compressed() else "unknown"),
		"levels": image.get_mipmap_count() + 1}

func _compare(sidecars: Image, decoded: Image) -> void:
	sidecars.convert(Image.FORMAT_RGB8)
	decoded.convert(Image.FORMAT_RGB8)
	var a := sidecars.get_data()
	var b := decoded.get_data()
	var total := 0
	var magenta := 0
	for offset: int in range(0, a.size(), 3):
		total += absi(a[offset] - b[offset]) + absi(a[offset + 1] - b[offset + 1]) + absi(a[offset + 2] - b[offset + 2])
		if a[offset] > 230 and a[offset + 1] < 30 and a[offset + 2] > 230:
			magenta += 1
	var mean := float(total) / a.size()
	_expect(mean <= MAX_MEAN_DIFF, "the frame drawn from the sidecars matches the decoded one (mean %.2f levels)" % mean)
	_expect(magenta == 0, "no missing-texture magenta in the sidecar frame (%d px)" % magenta)

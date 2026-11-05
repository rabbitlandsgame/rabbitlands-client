extends SceneTree
## AT-C2, the actor VRAM sidecar role of src/actors/actor_images.gd (the one
## actor image extension, wave-2 schedule 1.1 #4). Headless, editor binary
## (`--script`): sidecars are made here, in user://, with the editor's BC
## encoders exactly as tools/vram_encode.gd makes them (EVT1 + zstd DDS with
## the whole chain), and an index.json as tools/build_vram_textures.py writes
## it. The renderer's formats are forced (headless samples none).
##  1. Registration primes the sidecar formats on main; a worker asking first
##     would get none.
##  2. The mixed fixture: URI placeholders, a loose file and three bufferView
##     images of one byte length, a data: URI, base / normal / ORM / cutout
##     sidecars, an image without a sidecar and one indexed for other roles,
##     in one GLB. Each bufferView image gets its own sidecar (BC7 / BC5 / BC1
##     with its whole chain) at its own index, in every slot; the URI textures
##     are the very ResourceLoader ones; everything else is the plain parse's
##     image, byte for byte and without mips.
##  3. Refusals (corrupt, wrong sha256, wrong size, missing file, a format the
##     renderer lacks, ELORIA_VRAM_TEXTURES=0): decoded as before, warned once.
##  4. Pool: a second GLB that embeds the same images gets the same texture
##     instances (sidecar and decoded); the pool is weak.
##  5. ELORIA_ACTOR_IMAGES=legacy is the plain parse; the fallback CPU chain
##     is off by default, on with set_fallback_mips, off again under nomips.
##  6. Discard mode: embedded images are 1x1.
##  7. A worker parse with sidecars finishes while main is blocked.
##  8. The post-parse check: a texture that is not what was produced at its
##     index publishes nothing.
##  9. AW-03's mixed fixture (tests/actor_images_fixture.gd) with sidecars for
##     its two embedded images equals the plain parse everywhere else.
## 10. The prepared-content token follows the index; may_have_mipmaps; the
##     package self-test line; GlbSceneCache diagnostics carry the pool.
## Prints AT_C2_* lines (JSON) for the report.

const Cache := preload("res://src/actors/glb_scene_cache.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const ActorImages := preload("res://src/actors/actor_images.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Fixture := preload("res://tests/actor_images_fixture.gd")
const SIZE := 16
const ROOT := "user://at_c2_actor_images"
const BLOCK_MS := 1500

var checks := 0
var failures := 0


func _init() -> void:
	run.call_deferred()


func check(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("actor images: " + label)


# --- fixture building ------------------------------------------------------

static func sha256(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()


## A SIZE x SIZE image with a per-seed pattern (so encodes differ).
static func pattern(seed: int, alpha := false) -> Image:
	var image := Image.create(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	for y: int in SIZE:
		for x: int in SIZE:
			var r := fposmod(0.13 * seed + x * 0.05, 1.0)
			var g := fposmod(0.37 * seed + y * 0.06, 1.0)
			var b := fposmod(0.71 * seed + (x + y) * 0.03, 1.0)
			var a := 1.0 if not alpha else (1.0 if (x + y) % 3 else 0.0)
			image.set_pixel(x, y, Color(r, g, b, a))
	return image


## PNG bytes padded with zeros after IEND to `length` (decoders stop at IEND),
## so different images can have one byte length.
static func padded_png(image: Image, length: int) -> PackedByteArray:
	var bytes := image.save_png_to_buffer()
	while bytes.size() < length:
		bytes.append(0)
	return bytes


## One triangle per material; images are {"uri"[, "mimeType"]},
## {"view": bytes, "mimeType"} (bufferView) or {"data": bytes, "mime"}.
static func glb(images: Array, materials: Array) -> PackedByteArray:
	var binary := PackedByteArray()
	var views: Array = []
	var accessors: Array = []
	var primitives: Array = []
	for triangle: int in materials.size():
		var x := float(triangle) * 2.0
		var first := accessors.size()
		for chunk: Array in [[PackedFloat32Array([x, 0, 0, x + 1, 0, 0, x, 1, 0]).to_byte_array(), "VEC3"],
				[PackedFloat32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]).to_byte_array(), "VEC3"],
				[PackedFloat32Array([0, 0, 1, 0, 0, 1]).to_byte_array(), "VEC2"]]:
			var bytes: PackedByteArray = chunk[0]
			views.append({"buffer": 0, "byteOffset": binary.size(), "byteLength": bytes.size()})
			var accessor := {"bufferView": views.size() - 1, "componentType": 5126, "count": 3, "type": chunk[1]}
			if accessors.size() == first:
				accessor["min"] = [x, 0, 0]
				accessor["max"] = [x + 1, 1, 0]
			accessors.append(accessor)
			binary.append_array(bytes)
		primitives.append({"attributes": {"POSITION": first, "NORMAL": first + 1, "TEXCOORD_0": first + 2},
			"material": triangle})
	var descriptors: Array = []
	for image: Dictionary in images:
		var descriptor := {}
		if image.has("view"):
			while binary.size() % 4:
				binary.append(0)
			var bytes: PackedByteArray = image.view
			views.append({"buffer": 0, "byteOffset": binary.size(), "byteLength": bytes.size()})
			binary.append_array(bytes)
			descriptor = {"bufferView": views.size() - 1, "mimeType": str(image.get("mimeType", "image/png"))}
		elif image.has("data"):
			descriptor = {"uri": "data:%s;base64,%s" % [str(image.mime), Marshalls.raw_to_base64(image.data)]}
		else:
			descriptor = {"uri": str(image.uri)}
			if image.has("mimeType"):
				descriptor["mimeType"] = image.mimeType
		descriptors.append(descriptor)
	var textures: Array = []
	for index: int in images.size():
		textures.append({"source": index})
	var document := {"asset": {"version": "2.0"}, "buffers": [{"byteLength": binary.size()}],
		"bufferViews": views, "accessors": accessors, "images": descriptors, "textures": textures,
		"materials": materials, "meshes": [{"name": "fixture", "primitives": primitives}],
		"nodes": [{"name": "Fixture", "mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
	return Fixture.glb_bytes(document, binary)


static func store(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()


static func decode_any(bytes: PackedByteArray) -> Image:
	var image := Image.new()
	if bytes.size() > 3 and bytes[0] == 0x89:
		image.load_png_from_buffer(bytes)
	else:
		image.load_jpg_from_buffer(bytes)
	return image


## An EVT1 sidecar of `bytes` with `recipe` (tools/vram_encode.gd's recipes)
## in `directory`/vram, and its index entry.
static func sidecar(directory: String, bytes: PackedByteArray, recipe: String, roles: Array) -> Dictionary:
	var image := decode_any(bytes)
	image.generate_mipmaps()
	var error: Error = FAILED
	match recipe:
		"base", "orm_bc7":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress_from_channels(Image.COMPRESS_BPTC, Image.USED_CHANNELS_RGB)
		"base_alpha":
			image.convert(Image.FORMAT_RGBA8)
			error = image.compress_from_channels(Image.COMPRESS_BPTC, Image.USED_CHANNELS_RGBA)
		"orm":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress_from_channels(Image.COMPRESS_S3TC, Image.USED_CHANNELS_RGB)
		"normal":
			image.convert(Image.FORMAT_RGB8)
			error = image.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_NORMAL)
	if error != OK:
		return {}
	var formats := {Image.FORMAT_DXT1: "bc1", Image.FORMAT_RGTC_RG: "bc5", Image.FORMAT_BPTC_RGBA: "bc7"}
	var dds := image.save_dds_to_buffer()
	var evt := PackedByteArray([0x45, 0x56, 0x54, 0x31])
	evt.resize(16)
	evt.encode_u32(4, dds.size())
	evt.encode_u32(8, 1)
	evt.encode_u32(12, 0)
	evt.append_array(dds.compress(FileAccess.COMPRESSION_ZSTD))
	var sha := sha256(bytes)
	var file := "%s.%s.evt" % [sha, recipe]
	store(directory.path_join("vram").path_join(file), evt)
	return {"file": file, "recipe": recipe, "format": formats.get(image.get_format(), "?"),
		"width": image.get_width(), "height": image.get_height(), "mipmaps": image.get_mipmap_count(),
		"gpuBytes": image.get_data().size(), "rawBytes": dds.size(), "fileBytes": evt.size(),
		"sha256": sha256(evt), "roles": roles}


static func write_index(directory: String, entries: Dictionary) -> void:
	store(directory.path_join("vram/index.json"), JSON.stringify({"schema": 1, "recipeVersion": 1,
		"encoder": "test_actor_images.gd", "images": entries, "excluded": {}}, " ").to_utf8_buffer())


static func remove_tree(path: String) -> void:
	var absolute := ProjectSettings.globalize_path(path)
	if not DirAccess.dir_exists_absolute(absolute):
		return
	for name: String in DirAccess.get_files_at(absolute):
		DirAccess.remove_absolute(absolute.path_join(name))
	for name: String in DirAccess.get_directories_at(absolute):
		remove_tree(absolute.path_join(name))
	DirAccess.remove_absolute(absolute)


## The mixed fixture in `directory` (a fresh folder): body_a.glb and its twin
## body_b.glb, their URI textures, a loose PNG and the vram index. Returns
## {"a", "b", "shas": {name: sha}, "bytes": {name: bytes}, "entries", "uri"}.
func write_mixed(directory: String, with_index := true) -> Dictionary:
	remove_tree(directory)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var uri_image := pattern(1)
	var space_image := pattern(2)
	check(ResourceSaver.save(ImageTexture.create_from_image(uri_image), directory.path_join("uri_tex.res")) == OK
		and ResourceSaver.save(ImageTexture.create_from_image(space_image), directory.path_join("space name.res")) == OK,
		"fixture URI textures saved")
	# Three PNGs of one byte length: a loose file, a normal and an eye base.
	var plain_eq: Array[PackedByteArray] = [pattern(3).save_png_to_buffer(), pattern(4).save_png_to_buffer(),
		pattern(5).save_png_to_buffer()]
	var length := 0
	for bytes: PackedByteArray in plain_eq:
		length = maxi(length, bytes.size())
	length += 16
	var bytes := {"loose": padded_png(pattern(3), length), "normal": padded_png(pattern(4), length),
		"eyes": padded_png(pattern(5), length), "base": pattern(6).save_jpg_to_buffer(0.9),
		"data": pattern(7).save_png_to_buffer(), "orm": pattern(8).save_png_to_buffer(),
		"cutout": pattern(9, true).save_png_to_buffer(), "plain": pattern(10).save_png_to_buffer()}
	store(directory.path_join("loose.png"), bytes.loose)
	var images := [
		{"uri": "uri_tex.res"},                                   # 0 URI placeholder
		{"uri": "loose.png"},                                     # 1 loose file, the shared length
		{"view": bytes.normal},                                   # 2 normal (BC5), the shared length
		{"view": bytes.base, "mimeType": "image/jpeg"},           # 3 base (BC7)
		{"data": bytes.data, "mime": "image/png"},                # 4 data: URI
		{"view": bytes.orm},                                      # 5 ORM (BC1)
		{"view": bytes.cutout},                                   # 6 cutout (BC7 alpha)
		{"view": bytes.plain},                                    # 7 no sidecar
		{"uri": "space%20name.res", "mimeType": "image/png"},     # 8 URI placeholder after the views
		{"view": bytes.eyes},                                     # 9 eye base (BC7), the shared length
		{"view": bytes.base, "mimeType": "image/jpeg"}]           # 10 image 3's bytes as a cutout
	var materials := [
		{"name": "uri", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
		{"name": "loose", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
		{"name": "body", "pbrMetallicRoughness": {"baseColorTexture": {"index": 3},
			"metallicRoughnessTexture": {"index": 5}}, "normalTexture": {"index": 2},
			"occlusionTexture": {"index": 5}, "emissiveTexture": {"index": 4}, "emissiveFactor": [1, 1, 1]},
		{"name": "leaf", "alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 6}}},
		{"name": "plain", "pbrMetallicRoughness": {"baseColorTexture": {"index": 7}}},
		{"name": "spaced", "pbrMetallicRoughness": {"baseColorTexture": {"index": 8}}},
		{"name": "eyes", "pbrMetallicRoughness": {"baseColorTexture": {"index": 9}}},
		{"name": "ghost", "alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 10}}}]
	store(directory.path_join("body_a.glb"), glb(images, materials))
	# The twin embeds the base, the cutout and the plain image again.
	store(directory.path_join("body_b.glb"), glb([{"view": bytes.plain}, {"view": bytes.base, "mimeType": "image/jpeg"},
		{"view": bytes.cutout}], [
		{"name": "twin_plain", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
		{"name": "twin_base", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
		{"name": "twin_leaf", "alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 2}}}]))
	var shas := {}
	for name: String in bytes:
		shas[name] = sha256(bytes[name])
	check((bytes.loose as PackedByteArray).size() == (bytes.normal as PackedByteArray).size()
		and (bytes.normal as PackedByteArray).size() == (bytes.eyes as PackedByteArray).size()
		and shas.loose != shas.normal and shas.normal != shas.eyes, "three different images of one byte length")
	var entries := {}
	if with_index:
		var global := ProjectSettings.globalize_path(directory)
		entries[shas.normal] = sidecar(global, bytes.normal, "normal", ["normal"])
		entries[shas.base] = sidecar(global, bytes.base, "base", ["base"])
		entries[shas.orm] = sidecar(global, bytes.orm, "orm", ["occlusion", "orm"])
		entries[shas.cutout] = sidecar(global, bytes.cutout, "base_alpha", ["base_cutout"])
		entries[shas.eyes] = sidecar(global, bytes.eyes, "base", ["base"])
		# Listed, but a loose file is no bufferView image: never a sidecar.
		entries[shas.loose] = sidecar(global, bytes.loose, "base", ["base"])
		var complete := true
		for sha: String in entries:
			complete = complete and not (entries[sha] as Dictionary).is_empty()
		check(complete, "fixture sidecars encoded (the editor binary's BC encoders)")
		write_index(global, entries)
	return {"a": ProjectSettings.globalize_path(directory.path_join("body_a.glb")),
		"b": ProjectSettings.globalize_path(directory.path_join("body_b.glb")), "shas": shas, "bytes": bytes,
		# The path the extension resolves (absolute, as GLTFDocument's base path).
		"entries": entries, "uri": ResourceLoader.load(ProjectSettings.globalize_path(directory.path_join("uri_tex.res")), "Texture2D"),
		"space": ResourceLoader.load(ProjectSettings.globalize_path(directory.path_join("space name.res")), "Texture2D"),
		"directory": ProjectSettings.globalize_path(directory)}


# --- parsing helpers -----------------------------------------------------------

## An actor parse ({"state", "materials": {name: BaseMaterial3D}, "stats"}).
func actor_parse(path: String, discard := false) -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	ActorImages.enable(state, path, discard)
	var error := document.append_from_file(path, state)
	return {"error": error, "state": state, "materials": by_name(state), "stats": ActorImages.stats(state)}


## The plain GLTFDocument parse of `path` (no actor extension).
func plain_parse(path: String) -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_file(path, state)
	return {"error": error, "state": state, "materials": by_name(state)}


func by_name(state: GLTFState) -> Dictionary:
	var out := {}
	for material: Material in state.get_materials():
		out[material.resource_name] = material
	return out


func texture_of(parse: Dictionary, material: String, slot := BaseMaterial3D.TEXTURE_ALBEDO) -> Texture2D:
	var found: BaseMaterial3D = (parse.materials as Dictionary).get(material) as BaseMaterial3D
	return found.get_texture(slot) if found != null else null


## format/size/mips/pixels of a texture's image ("" when there is none).
func describe(texture: Texture2D) -> String:
	if texture == null:
		return "none"
	var image := texture.get_image()
	if image == null or image.is_empty():
		return "empty"
	return "%d %dx%d mips=%d %s" % [image.get_format(), image.get_width(), image.get_height(),
		image.get_mipmap_count(), image.get_data().hex_encode().sha256_text().left(16)]


func sidecar_image(directory: String, entry: Dictionary) -> Image:
	var loaded := Vram.decode_sidecar({"path": directory.path_join("vram").path_join(str(entry.file)),
		"sha256": entry.sha256, "width": entry.width, "height": entry.height, "format": entry.format,
		"mipmaps": entry.mipmaps})
	return loaded.image


## True when `texture` is the sidecar of `entry`: its format, full chain and bytes.
func is_sidecar(texture: Texture2D, directory: String, entry: Dictionary) -> bool:
	var expected := sidecar_image(directory, entry)
	var image := texture.get_image() if texture != null else null
	return expected != null and image != null and image.get_format() == expected.get_format() \
		and image.get_mipmap_count() == expected.get_mipmap_count() and image.get_mipmap_count() > 0 \
		and image.get_data() == expected.get_data()


func reset(formats := Vram.ALL_FORMATS) -> void:
	Vram.reconfigure()
	Vram.force_formats(formats)
	ActorImages.reset_pool()
	ActorImages.configure()
	ActorImages.set_fallback_mips(ActorImages.FALLBACK_MIPS)


# --- 1: registration primes the formats ----------------------------------------

static func _worker_formats() -> int:
	return Vram.usable_formats()


func check_registration() -> void:
	var fresh := not Quantization.is_registered()
	if fresh:
		check(Vram._formats == -1, "nothing read the sidecar formats before registration")
		var thread := Thread.new()
		thread.start(_worker_formats)
		var early: int = thread.wait_to_finish()
		check(early == 0 and Vram._formats == -1, "a worker asking first gets no formats and caches nothing")
	check(Quantization.ensure_registered(), "main registration completes")
	check(Vram._formats >= 0, "registration primed the sidecar formats on main (%d)" % Vram._formats)
	if not fresh:
		print("AT_C2_SKIP registration already happened; the priming check is weaker")
	check(Quantization._actor_images != null and Quantization._actor_images.get_script() == ActorImages,
		"the one actor image extension is registered")


## The byte match: small images compare whole, larger ones at their edges and
## evenly spaced probes; a range outside the buffer never matches.
func check_same_bytes() -> void:
	var buffer := PackedByteArray()
	for index: int in 12000:
		buffer.append((index * 7919 + 13) % 251)
	var small := buffer.slice(100, 1100)
	check(ActorImages._same_bytes(buffer, 100, small) and not ActorImages._same_bytes(buffer, 101, small),
		"a small image matches at its own offset only")
	var large := buffer.slice(500, 10500)
	check(ActorImages._same_bytes(buffer, 500, large), "a large image matches its own bytes")
	for at: int in [0, 31, large.size() - 1, large.size() - 32, ActorImages.EDGE + int((large.size() - 2 * ActorImages.EDGE) * 0.5 / ActorImages.PROBES)]:
		var changed := large.duplicate()
		changed[at] = changed[at] ^ 0x5A
		check(not ActorImages._same_bytes(buffer, 500, changed), "a large image differing at byte %d does not match" % at)
	check(not ActorImages._same_bytes(buffer, buffer.size() - 100, large), "a range past the buffer never matches")


# --- 2: the mixed fixture --------------------------------------------------------

func check_mixed() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("mixed/races"))
	var directory: String = fixture.directory
	var entries: Dictionary = fixture.entries
	var shas: Dictionary = fixture.shas
	var plain := plain_parse(fixture.a)
	var actor := actor_parse(fixture.a)
	check(int(actor.error) == OK and int(plain.error) == OK, "the mixed fixture parses both ways")
	var stats: Dictionary = actor.stats
	print("AT_C2_MIXED_STATS ", JSON.stringify(stats))
	check(int(stats.get("sidecar", 0)) == 5, "five bufferView images took their sidecar (%s)" % str(stats.get("sidecar")))
	check(int(stats.get("sidecarRoleMismatch", 0)) == 1, "the base indexed for other roles was refused once")
	check(int(stats.get("uriTextures", 0)) == 2 and int(stats.get("unmatched", 0)) == 2,
		"two URI placeholders; the loose file and the data: URI matched no bufferView")
	check(int(stats.get("checkFailed", -1)) == 0 and int(stats.get("published", 0)) >= 6,
		"every produced texture was where it was matched, and published")
	# Sidecars, at their own index, in every slot that samples them.
	var body_albedo := texture_of(actor, "body")
	check(is_sidecar(body_albedo, directory, entries[shas.base]), "body albedo is the base's BC7 sidecar with its chain")
	check(is_sidecar(texture_of(actor, "body", BaseMaterial3D.TEXTURE_NORMAL), directory, entries[shas.normal]),
		"body normal is the BC5 sidecar")
	var orm := texture_of(actor, "body", BaseMaterial3D.TEXTURE_METALLIC)
	check(is_sidecar(orm, directory, entries[shas.orm]) and orm == texture_of(actor, "body", BaseMaterial3D.TEXTURE_ROUGHNESS)
		and orm == texture_of(actor, "body", BaseMaterial3D.TEXTURE_AMBIENT_OCCLUSION),
		"metallic, roughness and occlusion share the BC1 ORM sidecar")
	check(is_sidecar(texture_of(actor, "leaf"), directory, entries[shas.cutout]), "the cutout is its BC7 alpha sidecar")
	check(is_sidecar(texture_of(actor, "eyes"), directory, entries[shas.eyes]),
		"the eye base (same byte length as the normal and the loose file) is its own sidecar")
	check(body_albedo != null and body_albedo.get_meta(ActorImages.META_SHA, "") == shas.base
		and str(body_albedo.get_meta(ActorImages.META_VARIANT, "")).begins_with(shas.base + "|evt:"),
		"sidecar textures carry rl_image_sha and rl_image_variant")
	# URI textures: the ResourceLoader instances.
	check(texture_of(actor, "uri") == fixture.uri and texture_of(actor, "spaced") == fixture.space,
		"both URI placeholders hold the ResourceLoader texture again")
	# Everything else: the plain parse's image, no mips.
	for name: String in ["loose", "plain", "ghost"]:
		var mine := describe(texture_of(actor, name))
		var theirs := describe(texture_of(plain, name))
		check(mine == theirs and "mips=0" in mine, "%s equals the plain parse without mips (%s / %s)" % [name, mine, theirs])
	var emission_mine := describe(texture_of(actor, "body", BaseMaterial3D.TEXTURE_EMISSION))
	check(emission_mine == describe(texture_of(plain, "body", BaseMaterial3D.TEXTURE_EMISSION)) and "mips=0" in emission_mine,
		"the data: URI image equals the plain parse")
	var ghost := texture_of(actor, "ghost")
	check(ghost != body_albedo and ghost.get_meta(ActorImages.META_VARIANT, "") == shas.base + "|decoded|mip-skip=0",
		"image 3's bytes sampled as a cutout are decoded for that index and pooled as decoded")
	var placeholders := 0
	for material: Material in (actor.state as GLTFState).get_materials():
		for slot: int in BaseMaterial3D.TEXTURE_MAX:
			var texture := (material as BaseMaterial3D).get_texture(slot)
			if texture != null and texture.get_width() == 1:
				placeholders += 1
	check(placeholders == 0, "no 1x1 placeholder survives in a material")
	var json_images: Array = (actor.state as GLTFState).get_json().get("images", [])
	check(str(json_images[0].get("uri")) == "uri_tex.res" and str(json_images[8].get("uri")) == "space%20name.res",
		"the URIs are restored in the JSON")
	# The GlbSceneCache helper: the main and the worker path both get them.
	var main_root := Cache._parse_generate(fixture.a, {}, true)
	var worker_root: Node3D = (await on_worker(_worker_generate.bind(str(fixture.a)))).get("root") as Node3D
	check(main_root != null and worker_root != null and albedo(main_root, "body") == body_albedo
		and albedo(worker_root, "body") == body_albedo, "the cache's main and worker parses share the pooled sidecar")
	for node: Node3D in [main_root, worker_root]:
		if node != null:
			node.free()
	print("AT_C2_MIXED ", JSON.stringify({"sidecars": stats.get("sidecar"), "gpuBytes": stats.get("gpuBytes"),
		"body": describe(body_albedo), "normal": describe(texture_of(actor, "body", BaseMaterial3D.TEXTURE_NORMAL)),
		"orm": describe(orm)}))


func albedo(root: Node, material_name: String) -> Texture2D:
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			if material != null and material.resource_name == material_name:
				return material.albedo_texture
	return null


static func _worker_generate(path: String) -> Dictionary:
	return {"root": Cache._parse_generate(path, {}, true)}


func on_worker(callable: Callable) -> Dictionary:
	var thread := Thread.new()
	if thread.start(callable) != OK:
		return {}
	while thread.is_alive():
		await process_frame
	return thread.wait_to_finish()


# --- 3: refusals ---------------------------------------------------------------

func rewrite_index(directory: String, mutate: Callable) -> void:
	var path := directory.path_join("vram/index.json")
	var parsed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutate.call(parsed.images)
	store(path, JSON.stringify(parsed, " ").to_utf8_buffer())


func check_refusals() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("refuse/races"))
	var directory: String = fixture.directory
	var shas: Dictionary = fixture.shas
	var entries: Dictionary = fixture.entries
	# Corrupt the base sidecar, misstate the cutout's size, misstate the eye
	# base's file hash, delete the normal's file.
	var base_file := directory.path_join("vram").path_join(str(entries[shas.base].file))
	var bytes := FileAccess.get_file_as_bytes(base_file)
	bytes[bytes.size() - 1] = bytes[bytes.size() - 1] ^ 0xFF
	store(base_file, bytes)
	rewrite_index(directory, func(images: Dictionary) -> void:
		images[shas.cutout]["width"] = SIZE * 2
		images[shas.cutout]["gpuBytes"] = 1 << 20
		images[shas.eyes]["sha256"] = "0".repeat(64))
	DirAccess.remove_absolute(directory.path_join("vram").path_join(str(entries[shas.normal].file)))
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	var plain := plain_parse(fixture.a)
	var actor := actor_parse(fixture.a)
	var stats: Dictionary = actor.stats
	print("AT_C2_REFUSE_STATS ", JSON.stringify(stats))
	check(int(stats.get("sidecarRejected", 0)) == 4 and int(stats.get("sidecar", 0)) == 1,
		"corrupt, wrong size, wrong sha256 and missing sidecars are refused; the ORM one still applies")
	for pair: Array in [["body", BaseMaterial3D.TEXTURE_ALBEDO], ["body", BaseMaterial3D.TEXTURE_NORMAL],
			["leaf", BaseMaterial3D.TEXTURE_ALBEDO], ["eyes", BaseMaterial3D.TEXTURE_ALBEDO]]:
		var mine := describe(texture_of(actor, pair[0], pair[1]))
		check(mine == describe(texture_of(plain, pair[0], pair[1])) and "mips=0" in mine,
			"refused %s/%d decodes as the plain parse (%s)" % [pair[0], pair[1], mine])
	var warned := 0
	for sha: String in [shas.base, shas.cutout, shas.eyes, shas.normal]:
		if ActorImages._warned.has(sha):
			warned += 1
	check(warned == 4, "each refused sha warned once")
	var again := actor_parse(fixture.a)
	check(int(again.stats.get("pooled", 0)) >= 6, "a second parse reuses the decoded fallbacks from the pool")
	# A format the renderer lacks: only BC7 sampled.
	reset(Vram.FORMAT_BITS.bc7)
	var fresh := write_mixed(ROOT.path_join("formats/races"))
	var limited := actor_parse(fresh.a)
	check(int(limited.stats.get("sidecarUnsupported", 0)) == 2 and int(limited.stats.get("sidecar", 0)) == 3,
		"BC5 and BC1 sidecars decode where the renderer samples only BC7 (%s)" % JSON.stringify(limited.stats))
	check("mips=0" in describe(texture_of(limited, "body", BaseMaterial3D.TEXTURE_NORMAL))
		and "mips=0" in describe(texture_of(limited, "body", BaseMaterial3D.TEXTURE_METALLIC)),
		"the normal and the ORM the renderer cannot sample are decoded")
	# ELORIA_VRAM_TEXTURES=0 turns actor sidecars off too.
	var previous := OS.get_environment(Vram.ENVIRONMENT)
	OS.set_environment(Vram.ENVIRONMENT, "0")
	reset()
	var off := actor_parse(fresh.a)
	check(int(off.stats.get("sidecar", -1)) == 0 and not ActorImages.may_have_mipmaps(fresh.directory),
		"ELORIA_VRAM_TEXTURES=0: no actor sidecar")
	OS.set_environment(Vram.ENVIRONMENT, previous)
	reset()


# --- 4: the pool ------------------------------------------------------------------

func check_pool() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("pool/races"))
	var directory: String = fixture.directory
	var a := actor_parse(fixture.a)
	var b := actor_parse(fixture.b)
	check(texture_of(b, "twin_base") == texture_of(a, "body"), "the shared base sidecar is one texture instance")
	check(texture_of(b, "twin_leaf") == texture_of(a, "leaf"), "the shared cutout sidecar is one texture instance")
	check(texture_of(b, "twin_plain") == texture_of(a, "plain") and "mips=0" in describe(texture_of(b, "twin_plain")),
		"the shared image without a sidecar is one decoded texture instance")
	check(int(b.stats.get("pooled", 0)) == 3 and int(b.stats.get("decoded", 0)) == 0 and int(b.stats.get("sidecar", 0)) == 0,
		"the twin decoded and uploaded nothing (%s)" % JSON.stringify(b.stats))
	var snapshot := Cache.retention_snapshot()
	var pool: Dictionary = (snapshot.get("actor_images", {}) as Dictionary).get("pool", {})
	check(int(pool.get("live_entries", 0)) >= 7 and int(pool.get("hits", 0)) >= 3 and int(pool.get("bytes", 0)) > 0,
		"GlbSceneCache diagnostics carry the actor image pool %s" % JSON.stringify(pool))
	a.clear()
	b.clear()
	var key := pooled_key_of_parse(str(fixture.a))
	check(not key.is_empty() and ActorImages.pooled(key) == null, "the pool holds its textures weakly")
	var without := write_mixed(ROOT.path_join("pool-plain/races"), false)
	var plain := plain_parse(without.a)
	var first := actor_parse(without.a)
	var second := actor_parse(without.b)
	check(int(first.stats.get("sidecar", -1)) == 0 and texture_of(second, "twin_base") == texture_of(first, "body"),
		"without an index the shared base is still one (decoded) texture")
	for name: String in ["body", "leaf", "plain", "eyes", "loose", "ghost"]:
		check(describe(texture_of(first, name)) == describe(texture_of(plain, name)),
			"without an index %s equals the plain parse" % name)
	check(not ActorImages.may_have_mipmaps(without.directory) and ActorImages.may_have_mipmaps(directory),
		"may_have_mipmaps follows the index")


## Parses `path`, checks that the pool serves its live body texture and
## returns that texture's pool key; every holder is released on return.
func pooled_key_of_parse(path: String) -> String:
	var parse := actor_parse(path)
	var texture := texture_of(parse, "body")
	var key := str(texture.get_meta(ActorImages.META_VARIANT, "")) if texture != null else ""
	check(not key.is_empty() and ActorImages.pooled(key) == texture, "the pool serves the live texture")
	return key


# --- 5: switches -------------------------------------------------------------------

func check_switches() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("switch/races"))
	var plain := plain_parse(fixture.a)
	ActorImages.configure("legacy")
	var state := GLTFState.new()
	check(not ActorImages.enable(state, fixture.a) and not ActorImages.may_have_mipmaps(fixture.directory),
		"legacy: the extension is off")
	var legacy := {"state": state, "error": GLTFDocument.new().append_from_file(fixture.a, state)}
	legacy["materials"] = by_name(state)
	for name: String in ["body", "leaf", "plain", "eyes", "uri"]:
		check(describe(texture_of(legacy, name)) == describe(texture_of(plain, name)),
			"legacy %s equals the plain parse" % name)
	check(ActorImages.stats(state).is_empty(), "legacy keeps no actor image state")
	ActorImages.configure()
	check(not ActorImages.fallback_mips(), "decoded actor images get no CPU chain by default (owner question 4)")
	ActorImages.set_fallback_mips(true)
	var mipped := actor_parse(fixture.a)
	var plain_mipped := describe(texture_of(mipped, "plain"))
	check(ActorImages.fallback_mips() and "mips=0" not in plain_mipped
		and str(texture_of(mipped, "plain").get_meta(ActorImages.META_VARIANT)).contains("decoded+cpu-mips"),
		"set_fallback_mips gives decoded images a chain (%s)" % plain_mipped)
	check(is_sidecar(texture_of(mipped, "body"), fixture.directory, fixture.entries[fixture.shas.base]),
		"sidecars are unchanged by the fallback chain")
	ActorImages.configure("nomips")
	check(not ActorImages.fallback_mips(), "nomips overrides the fallback chain")
	var nomips := actor_parse(fixture.a)
	check("mips=0" in describe(texture_of(nomips, "plain"))
		and is_sidecar(texture_of(nomips, "body"), fixture.directory, fixture.entries[fixture.shas.base]),
		"nomips: decoded without a chain, sidecars still apply")
	reset()


# --- 6: discard --------------------------------------------------------------------

func check_discard() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("discard/races"))
	var parse := actor_parse(fixture.a, true)
	check(int(parse.error) == OK and int(parse.stats.get("discarded", 0)) == 9
		and int(parse.stats.get("sidecar", -1)) == 0 and int(parse.stats.get("published", -1)) == 0
		and int(parse.stats.get("decoded", -1)) == 0,
		"discard: every embedded, data: and loose image is a placeholder, nothing published (%s)" % JSON.stringify(parse.stats))
	var body := texture_of(parse, "body")
	check(body != null and body.get_width() == 1 and body.get_height() == 1, "discard: the body albedo is 1x1")
	check(texture_of(parse, "uri") == fixture.uri, "discard keeps the URI textures")


# --- 7: worker while main is blocked ------------------------------------------------

static func _task(path: String, out: Dictionary) -> void:
	var root := Cache._parse_generate(path, {}, true)
	out["ok"] = root != null
	out["end"] = Time.get_ticks_msec()
	if root != null:
		root.free()


func check_worker() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("worker/races"))
	var out := {}
	var task := WorkerThreadPool.add_task(_task.bind(str(fixture.a), out))
	OS.delay_msec(BLOCK_MS)
	var unblocked := Time.get_ticks_msec()
	while not WorkerThreadPool.is_task_completed(task):
		await process_frame
	WorkerThreadPool.wait_for_task_completion(task)
	check(bool(out.get("ok", false)) and int(out.get("end", unblocked)) < unblocked,
		"a WorkerThreadPool actor parse with sidecars finished while main was blocked")
	var totals := ActorImages.totals()
	check(int(totals.get("sidecar", 0)) > 0, "process totals count sidecars")


# --- 8: the post-parse check ----------------------------------------------------------

func check_post_parse() -> void:
	reset()
	var extension: GLTFDocumentExtension = Quantization._actor_images
	var produced := Image.create(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	var other := ImageTexture.create_from_image(Image.create(SIZE * 2, SIZE * 2, false, Image.FORMAT_RGBA8))
	var placeholder := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	var placeholder_texture := ImageTexture.create_from_image(placeholder)
	var pooled := ImageTexture.create_from_image(produced)
	var material := StandardMaterial3D.new()
	material.albedo_texture = other
	material.normal_texture = placeholder_texture
	var state := GLTFState.new()
	state.set_json({"asset": {"version": "2.0"}, "images": [{}, {}]})
	state.set_images([other, placeholder_texture])
	state.set_materials([material])
	ActorImages.enable(state)
	state.set_additional_data(ActorImages.STATS, {})
	state.set_additional_data(ActorImages.PRODUCED, {
		0: {"sha": "a".repeat(64), "key": "a|decoded|mip-skip=0", "kind": "decoded", "width": SIZE,
			"height": SIZE, "format": Image.FORMAT_RGBA8, "mipmaps": false},
		1: {"sha": "b".repeat(64), "key": "b|decoded|mip-skip=0", "kind": "pooled", "width": 1,
			"height": 1, "format": Image.FORMAT_RGBA8, "mipmaps": false, "texture": pooled}})
	check(extension._import_post_parse(state) == OK, "post-parse runs on the crafted state")
	var stats := ActorImages.stats(state)
	check(int(stats.get("checkFailed", 0)) == 1 and int(stats.get("published", 0)) == 0
		and ActorImages.pooled("a|decoded|mip-skip=0") == null,
		"a texture that is not what was produced at its index publishes nothing")
	check(state.get_images()[0] == other and material.albedo_texture == other and not other.has_meta(ActorImages.META_SHA),
		"the parse keeps its own texture there, untagged")
	check(state.get_images()[1] == pooled and material.normal_texture == pooled,
		"a pooled placeholder that is where it was matched is still replaced")
	# A URI texture replaces a null slot too (AW-03: state.images always gets them).
	var uri_texture := ImageTexture.create_from_image(produced)
	var uri_state := GLTFState.new()
	uri_state.set_json({"asset": {"version": "2.0"}, "images": [{"uri": ActorImages.PLACEHOLDER_URI,
		"mimeType": ActorImages.URI_MIME_PREFIX + "0"}]})
	uri_state.set_images([null])
	ActorImages.enable(uri_state)
	uri_state.set_additional_data(ActorImages.STATS, {})
	uri_state.set_additional_data(ActorImages.URI_ORIGINALS, {0: ["texture.res", null]})
	uri_state.set_additional_data(ActorImages.URI_TEXTURES, {0: uri_texture})
	check(extension._import_post_parse(uri_state) == OK and uri_state.get_images()[0] == uri_texture
		and str(uri_state.get_json().images[0].uri) == "texture.res",
		"a URI texture replaces a null image slot and its URI is restored")


# --- 8b: images read from data: URIs and files come before later bufferViews ---------------

## Which images GLTFDocument reads bytes for besides bufferViews and placeholders.
func check_other_images() -> void:
	var directory := ProjectSettings.globalize_path(ROOT.path_join("others"))
	remove_tree(directory)
	store(directory.path_join("same.png"), pattern(12).save_png_to_buffer())
	store(directory.path_join("empty.png"), PackedByteArray())
	var document := {"images": [{"uri": "same.png"}, {"uri": "missing.png"}, {"uri": "data:image/png;base64,"},
		{"uri": "data:image/png;base64,AAAA"},
		{"uri": ActorImages.PLACEHOLDER_URI, "mimeType": ActorImages.URI_MIME_PREFIX + "4"},
		{"bufferView": 0, "mimeType": "image/png"}, {"uri": "empty.png"}]}
	var others := ActorImages._other_images(document, directory)
	check(others == PackedInt32Array([0, 3]),
		"a loose file with bytes and a data: URI with a payload are read; missing, empty, placeholder and bufferView images are not (%s)" % str(others))
	check(ActorImages._other_images(document, "") == PackedInt32Array([3]), "without a base path only the data: URI")


## A data: URI or a loose file whose bytes equal a later bufferView image's:
## GLTFDocument asks for it first, so it must never be taken for that
## bufferView image (a pooled placeholder would land in its slot and survive;
## a sidecar chosen for the bufferView's roles would stand in for it).
func check_other_before_view() -> void:
	reset()
	var same := pattern(11, true).save_png_to_buffer()
	# A: no index; the bytes are pooled by a twin that stays alive.
	var pool_dir := ROOT.path_join("other-pool/races")
	remove_tree(pool_dir)
	store(pool_dir.path_join("same.png"), same)
	store(pool_dir.path_join("twin.glb"), glb([{"view": same}],
		[{"name": "twin", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]))
	store(pool_dir.path_join("mixed.glb"), glb([{"uri": "same.png"}, {"data": same, "mime": "image/png"}, {"view": same}], [
		{"name": "loose_first", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
		{"name": "data_first", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
		{"name": "view_after", "pbrMetallicRoughness": {"baseColorTexture": {"index": 2}}}]))
	var twin := actor_parse(ProjectSettings.globalize_path(pool_dir.path_join("twin.glb")))
	var mixed_path := ProjectSettings.globalize_path(pool_dir.path_join("mixed.glb"))
	var plain := plain_parse(mixed_path)
	var actor := actor_parse(mixed_path)
	var stats: Dictionary = actor.stats
	print("AT_C2_OTHER_POOL_STATS ", JSON.stringify(stats))
	check(int(stats.get("unmatched", 0)) == 2 and int(stats.get("pooled", 0)) == 1 and int(stats.get("checkFailed", -1)) == 0,
		"the loose file and the data: URI are their own images; the bufferView one is pooled (%s)" % JSON.stringify(stats))
	var small := 0
	for material: Material in (actor.state as GLTFState).get_materials():
		for slot: int in BaseMaterial3D.TEXTURE_MAX:
			var texture := (material as BaseMaterial3D).get_texture(slot)
			if texture != null and texture.get_width() == 1:
				small += 1
	check(small == 0, "no 1x1 placeholder survives where a data: URI or a file shares a bufferView's bytes")
	for name: String in ["loose_first", "data_first"]:
		var mine := describe(texture_of(actor, name))
		check(mine == describe(texture_of(plain, name)) and "mips=0" in mine, "%s equals the plain parse (%s)" % [name, mine])
	check(texture_of(actor, "view_after") == texture_of(twin, "twin"), "the bufferView image is the twin's pooled texture")
	# B: an index lists the bytes for an opaque base only; the data: URI samples them as a cutout.
	reset()
	var roles_dir := ROOT.path_join("other-roles/races")
	remove_tree(roles_dir)
	var global := ProjectSettings.globalize_path(roles_dir)
	store(roles_dir.path_join("mixed.glb"), glb([{"data": same, "mime": "image/png"}, {"view": same}], [
		{"name": "data_cutout", "alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
		{"name": "view_base", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}}]))
	var entry := sidecar(global, same, "base", ["base"])
	check(not entry.is_empty(), "the opaque base sidecar is encoded")
	write_index(global, {sha256(same): entry})
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	var roles_path := global.path_join("mixed.glb")
	var roles_plain := plain_parse(roles_path)
	var roles := actor_parse(roles_path)
	print("AT_C2_OTHER_ROLES_STATS ", JSON.stringify(roles.stats))
	var cutout := describe(texture_of(roles, "data_cutout"))
	check(cutout == describe(texture_of(roles_plain, "data_cutout")) and "mips=0" in cutout,
		"the data: cutout is decoded, not the sidecar encoded for the bufferView's opaque base (%s)" % cutout)
	check(is_sidecar(texture_of(roles, "view_base"), global, entry) and int(roles.stats.get("checkFailed", -1)) == 0,
		"the bufferView base is its sidecar and the parse is consistent")
	twin.clear()
	reset()


# --- 9: AW-03's mixed fixture with sidecars --------------------------------------------

func check_aw03_fixture() -> void:
	reset()
	var directory := OS.get_user_data_dir().path_join("at_c2_aw03_fixture")
	remove_tree(directory)
	var fixture := Fixture.write(directory)
	check(not fixture.is_empty(), "AW-03 fixture written")
	if fixture.is_empty():
		return
	var path := str(fixture.path)
	# Its two bufferView images, read back from the GLB: images 2 (PNG) and 3 (JPEG).
	var probe := GLTFState.new()
	GLTFDocument.new().append_from_file(path, probe)
	var document := probe.get_json()
	var buffer: PackedByteArray = probe.get_buffers()[0]
	var entries := {}
	var shas := {}
	for index: int in [2, 3]:
		var view: Dictionary = document.bufferViews[int(document.images[index].bufferView)]
		var bytes := buffer.slice(int(view.get("byteOffset", 0)), int(view.get("byteOffset", 0)) + int(view.byteLength))
		shas[index] = sha256(bytes)
		entries[shas[index]] = sidecar(directory, bytes, "base", ["base"])
	write_index(directory, entries)
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	var plain := plain_parse(path)
	var actor := actor_parse(path)
	print("AT_C2_AW03_FIXTURE_STATS ", JSON.stringify(actor.stats))
	check(int(actor.stats.get("sidecar", 0)) == 2 and int(actor.stats.get("uriTextures", 0)) >= 1,
		"AW-03 fixture: both embedded images take their sidecars among the URI placeholders")
	check(is_sidecar(texture_of(actor, "embedded"), directory, entries[shas[2]])
		and is_sidecar(texture_of(actor, "embedded_jpeg"), directory, entries[shas[3]]),
		"AW-03 fixture: the PNG and the JPEG are their own sidecars")
	var expected: Texture2D = ResourceLoader.load(str(fixture.textures["uri_tex.res"]), "Texture2D")
	check(texture_of(actor, "uri_twice") == expected and texture_of(actor, "embedded_jpeg", BaseMaterial3D.TEXTURE_METALLIC) == expected,
		"AW-03 fixture: URI slots keep the ResourceLoader texture")
	for pair: Array in [["loose", BaseMaterial3D.TEXTURE_ALBEDO], ["data_and_names", BaseMaterial3D.TEXTURE_ALBEDO],
			["data_and_names", BaseMaterial3D.TEXTURE_EMISSION], ["data_and_names", BaseMaterial3D.TEXTURE_AMBIENT_OCCLUSION]]:
		check(describe(texture_of(actor, pair[0], pair[1])) == describe(texture_of(plain, pair[0], pair[1])),
			"AW-03 fixture: %s/%d equals the plain parse" % pair)
	actor.clear()
	plain.clear()
	probe = null
	remove_tree(directory)


# --- 10: token, self-test ------------------------------------------------------------

func check_token_and_self_test() -> void:
	reset()
	var fixture := write_mixed(ROOT.path_join("token/races"))
	var source := ROOT.path_join("token/races/body_a.glb")
	var with_index := Prepared.scene_texture_token(source)
	check(with_index.begins_with("scene-images-v2|actor-images|") and ":ok:" in with_index
		and "actor-mode=" + ActorImages.mode() in with_index, "the actor token names the index (%s)" % with_index)
	rewrite_index(fixture.directory, func(images: Dictionary) -> void:
		images.erase(fixture.shas.loose))
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	var changed := Prepared.scene_texture_token(source)
	check(changed != with_index and ":ok:" in changed, "the token changes with the index bytes")
	DirAccess.remove_absolute(fixture.directory.path_join("vram/index.json"))
	Vram.reconfigure()
	Vram.force_formats(Vram.ALL_FORMATS)
	check(":missing:" in Prepared.scene_texture_token(source), "a missing index is in the token")
	ActorImages.configure("legacy")
	var legacy := Prepared.scene_texture_token(source)
	check("actor-mode=legacy" in legacy and ":missing:" not in legacy, "legacy names no index")
	ActorImages.configure()
	# The package smoke line.
	var tested := write_mixed(ROOT.path_join("selftest/races"))
	var line := ActorImages.self_test(ROOT.path_join("selftest/races"))
	print("AT_C2_SELF_TEST ", line)
	var pattern := RegEx.create_from_string("^actor_images self_test ok entries=([1-9][0-9]*) format=(\\S+) mips=([1-9][0-9]*) decompress=ok$")
	check(pattern.search(line) != null, "self-test line: %s" % line)
	check(ActorImages.self_test(ROOT.path_join("nowhere")).begins_with("actor_images self_test failed"),
		"self-test of a folder without an index fails")
	check(tested.directory != "", "self-test fixture written")
	reset()


func run() -> void:
	var environment := {}
	for key: String in ["RABBITLANDS_PREPARED_CONTENT", "ELORIA_NO_GEOMETRY_CACHE", Vram.ENVIRONMENT]:
		environment[key] = OS.get_environment(key)
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", "1")
	check_registration()
	check_same_bytes()
	await check_mixed()
	check_refusals()
	check_pool()
	check_switches()
	check_discard()
	await check_worker()
	check_post_parse()
	check_other_images()
	check_other_before_view()
	check_aw03_fixture()
	check_token_and_self_test()
	remove_tree(ROOT)
	for key: String in environment:
		OS.set_environment(key, str(environment[key]))
	Vram.reconfigure()
	print("test_actor_images: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

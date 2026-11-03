extends SceneTree
## AW-03, the worker-safe actor glTF parse contract (src/actors/actor_images.gd,
## GlbSceneCache._parse_generate / prepare_actor / install_actor_prepared).
## Headless; run with --script from an imported checkout.
##  1. A worker `prepare_actor` of an equipment glTF with imported URI
##     textures finishes while the main thread is blocked for 2 s; the plain
##     parse of another one waits for the main thread (the probe's control).
##  2. GltfQuantization registers the actor image extension; a foreign document
##     gets ERR_SKIP with its JSON untouched; ELORIA_ACTOR_IMAGES=legacy turns
##     it off. Before registration a worker's prepare_actor is refused and the
##     switch is not written off main. The decoder runs only on bytes with its
##     signature. A spec-gloss document (materials built from texture pixels)
##     keeps its URI textures and equals the plain parse.
##  3. The mixed fixture (tests/actor_images_fixture.gd: loadable URI, loose
##     URI, embedded PNG and JPEG, data: JPEG, '+' and %20 names) as
##     an actor document keeps the very texture ResourceLoader returns in every
##     slot, restores its URIs and equals the plain parse, on main and worker.
##     A release-compressed creature (RLCZ, append_from_buffer) does too.
##  4. Real actor files: today's plain parse (`_parse_generate(path, {}, false)`
##     then pack), the main build (`_build_raw`, now an actor document) and the
##     worker (`prepare_actor` on a Thread, `install_actor_prepared` on main)
##     give the same node tree, node and resource values, texture resources
##     (the same instance for imported ones, the same pixels for embedded
##     ones) and mesh arrays read back headless.
##  5. install_actor_prepared: a changed file, an already cached path and a
##     discarded record free the root and publish nothing.
## RL_AW03_SWEEP: unset = a stratified sample (every race and some of each
## other family); "full" = every actor glTF; an integer N = every Nth file.
## Prints AW03_* lines (JSON) for the measurement report.

const Cache := preload("res://src/actors/glb_scene_cache.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const ActorImages := preload("res://src/actors/actor_images.gd")
const Fixture := preload("res://tests/actor_images_fixture.gd")
const ACTOR_ROOT := "res://assets/actors/native"
const BLOCK_MS := 2000
const MAX_DIFFS := 12
const SKIP_PROPERTIES := ["resource_scene_unique_id", "script"]
## Default sample: every Nth file of each family (1 = all).
const STRIDES := {"races": 1, "hair": 16, "equipment": 30, "creatures": 30, "mounts": 1,
	"shared": 1, "rl_heads": 10}

var checks := 0
var failures := 0
var shared_textures := 0
var compared_textures := 0


func _init() -> void:
	run.call_deferred()


func check(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("actor worker parse: " + label)


# --- deep equality ---------------------------------------------------------

func same(a: Variant, b: Variant, where: String, diffs: Array[String], depth := 0) -> void:
	if diffs.size() >= MAX_DIFFS:
		return
	if typeof(a) != typeof(b):
		diffs.append("%s: %s != %s" % [where, type_string(typeof(a)), type_string(typeof(b))])
		return
	match typeof(a):
		TYPE_OBJECT:
			same_object(a, b, where, diffs, depth)
		TYPE_ARRAY:
			if (a as Array).size() != (b as Array).size():
				diffs.append("%s: size %d != %d" % [where, (a as Array).size(), (b as Array).size()])
				return
			for index: int in (a as Array).size():
				same(a[index], b[index], "%s[%d]" % [where, index], diffs, depth)
		TYPE_DICTIONARY:
			if (a as Dictionary).size() != (b as Dictionary).size():
				diffs.append("%s: keys %s != %s" % [where, str((a as Dictionary).keys()).left(120),
					str((b as Dictionary).keys()).left(120)])
				return
			for key: Variant in a:
				if not (b as Dictionary).has(key):
					diffs.append("%s: missing key %s" % [where, str(key)])
					return
				same(a[key], b[key], "%s.%s" % [where, str(key)], diffs, depth)
		TYPE_FLOAT:
			if a != b and not (is_nan(a) and is_nan(b)):
				diffs.append("%s: %s != %s" % [where, str(a), str(b)])
		_:
			if a != b:
				diffs.append("%s: %s != %s" % [where, str(a).left(80), str(b).left(80)])


func same_object(a: Object, b: Object, where: String, diffs: Array[String], depth: int) -> void:
	if a == null or b == null:
		if a != b:
			diffs.append("%s: null vs object" % where)
		return
	if a == b:
		if a is Texture2D:
			shared_textures += 1
		return
	if a.get_class() != b.get_class():
		diffs.append("%s: class %s != %s" % [where, a.get_class(), b.get_class()])
		return
	if a is Node:
		return # the tree walk compares nodes
	if a is Texture2D:
		same_texture(a as Texture2D, b as Texture2D, where, diffs)
		return
	if not a is Resource or depth > 10:
		return
	same_properties(a, b, where, diffs, depth + 1)
	if a is ArrayMesh:
		var mesh_a := a as ArrayMesh
		var mesh_b := b as ArrayMesh
		for surface: int in mesh_a.get_surface_count():
			same(mesh_a.surface_get_arrays(surface), mesh_b.surface_get_arrays(surface),
				"%s.surface%d.arrays" % [where, surface], diffs, depth + 1)
			same(mesh_a.surface_get_blend_shape_arrays(surface), mesh_b.surface_get_blend_shape_arrays(surface),
				"%s.surface%d.blend_shapes" % [where, surface], diffs, depth + 1)


func same_properties(a: Object, b: Object, where: String, diffs: Array[String], depth: int) -> void:
	for property: Dictionary in a.get_property_list():
		if not int(property.usage) & PROPERTY_USAGE_STORAGE:
			continue
		var name := str(property.name)
		if name in SKIP_PROPERTIES:
			continue
		same(a.get(name), b.get(name), where + "." + name, diffs, depth)


func same_texture(a: Texture2D, b: Texture2D, where: String, diffs: Array[String]) -> void:
	compared_textures += 1
	if not a.resource_path.is_empty() or not b.resource_path.is_empty():
		if a.resource_path != b.resource_path:
			diffs.append("%s: texture %s != %s" % [where, a.resource_path, b.resource_path])
		return
	var image_a := a.get_image()
	var image_b := b.get_image()
	if image_a == null or image_b == null:
		if image_a != image_b:
			diffs.append("%s: one texture has no image" % where)
		return
	if image_a.get_format() != image_b.get_format() or image_a.get_size() != image_b.get_size() \
			or image_a.has_mipmaps() != image_b.has_mipmaps():
		diffs.append("%s: image %s/%s/%s != %s/%s/%s" % [where, image_a.get_format(), image_a.get_size(),
			image_a.has_mipmaps(), image_b.get_format(), image_b.get_size(), image_b.has_mipmaps()])
	elif image_a.get_data() != image_b.get_data():
		diffs.append("%s: image pixels differ" % where)


func same_tree(a: Node, b: Node, where: String, diffs: Array[String]) -> void:
	if diffs.size() >= MAX_DIFFS:
		return
	if a.name != b.name or a.get_class() != b.get_class():
		diffs.append("%s: node %s:%s != %s:%s" % [where, a.name, a.get_class(), b.name, b.get_class()])
		return
	same_properties(a, b, where, diffs, 0)
	if a.get_child_count() != b.get_child_count():
		diffs.append("%s: %d children != %d" % [where, a.get_child_count(), b.get_child_count()])
		return
	for index: int in a.get_child_count():
		same_tree(a.get_child(index), b.get_child(index), where + "/" + str(a.get_child(index).name), diffs)


func scene_diffs(a: PackedScene, b: PackedScene) -> Array[String]:
	var diffs: Array[String] = []
	if a == null or b == null:
		diffs.append("missing scene (%s, %s)" % [a != null, b != null])
		return diffs
	var root_a := a.instantiate()
	var root_b := b.instantiate()
	same_tree(root_a, root_b, str(root_a.name), diffs)
	root_a.free()
	root_b.free()
	return diffs


# --- files -----------------------------------------------------------------

func gltf_files(directory: String, out: Array[String]) -> void:
	for name: String in DirAccess.get_files_at(directory):
		if name.get_extension().to_lower() in ["glb", "gltf"]:
			out.append(directory.path_join(name))
	for child: String in DirAccess.get_directories_at(directory):
		gltf_files(directory.path_join(child), out)


## The JSON chunk of a .glb (or a whole .gltf); {} when unreadable.
func gltf_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var text := ""
	if file.get_length() >= 20 and file.get_buffer(4).get_string_from_ascii() == "glTF":
		file.seek(12)
		var length := file.get_32()
		file.get_32()
		text = file.get_buffer(length).get_string_from_utf8()
	else:
		file.seek(0)
		text = file.get_as_text()
	var parsed: Variant = JSON.parse_string(text)
	return parsed if parsed is Dictionary else {}


func uri_images(path: String) -> PackedStringArray:
	var out := PackedStringArray()
	for image: Variant in gltf_json(path).get("images", []):
		if image is Dictionary and (image as Dictionary).has("uri") and not str(image.uri).begins_with("data:"):
			out.append(str(image.uri))
	return out


func family_of(path: String) -> String:
	return path.trim_prefix(ACTOR_ROOT + "/").get_slice("/", 0)


func sample(files: Array[String]) -> Array[String]:
	var sweep := OS.get_environment("RL_AW03_SWEEP").strip_edges().to_lower()
	var out: Array[String] = []
	var seen := {}
	for path: String in files:
		var family := family_of(path)
		var index := int(seen.get(family, 0))
		seen[family] = index + 1
		var stride := int(STRIDES.get(family, 10))
		if sweep == "full":
			stride = 1
		elif sweep.is_valid_int():
			stride = maxi(1, int(sweep))
		if index % stride == 0:
			out.append(path)
	return out


# --- worker helpers --------------------------------------------------------

static func _worker_prepare(path: String) -> Dictionary:
	var began := Time.get_ticks_usec()
	var record := Cache.prepare_actor(path)
	return {"record": record, "us": Time.get_ticks_usec() - began, "end": Time.get_ticks_msec()}


static func _worker_plain(path: String) -> Dictionary:
	var began := Time.get_ticks_usec()
	var root := Cache._parse_generate(ProjectSettings.globalize_path(path), {}, false)
	var end := Time.get_ticks_msec()
	var ok := root != null
	if ok:
		root.free()
	return {"ok": ok, "us": Time.get_ticks_usec() - began, "end": end}


static func _worker_generate(path: String) -> Dictionary:
	return {"root": Cache._parse_generate(path, {}, true)}


static func _worker_unregistered(path: String) -> Dictionary:
	var record := Cache.prepare_actor(path)
	record["mode"] = ActorImages.mode()
	return record


## Runs `callable` on a Thread and returns its result. Never joins a live
## worker that may be waiting for this (main) thread.
func on_worker(callable: Callable) -> Dictionary:
	var thread := Thread.new()
	if thread.start(callable) != OK:
		return {}
	while thread.is_alive():
		await process_frame
	return thread.wait_to_finish()


## The same with the main thread blocked for BLOCK_MS after the start.
func blocked(callable: Callable) -> Dictionary:
	var thread := Thread.new()
	if thread.start(callable) != OK:
		return {}
	OS.delay_msec(BLOCK_MS)
	var unblocked := Time.get_ticks_msec()
	while thread.is_alive():
		await process_frame
	var result: Dictionary = thread.wait_to_finish()
	result["waited_for_main"] = int(result.get("end", unblocked)) >= unblocked
	return result


# --- 1: the worker does not wait for a blocked main thread ------------------

func check_blocked_main(files: Array[String]) -> void:
	# Two equipment files whose URI textures nothing has loaded yet, disjoint
	# so the control parse cannot reuse the first one's textures.
	var first := ""
	var second := ""
	var first_uris := PackedStringArray()
	for path: String in files:
		if family_of(path) != "equipment":
			continue
		var uris := uri_images(path)
		if uris.is_empty():
			continue
		if first.is_empty():
			first = path
			first_uris = uris
			continue
		var disjoint := true
		for uri: String in uris:
			if first_uris.has(uri):
				disjoint = false
		if disjoint:
			second = path
			break
	check(not first.is_empty() and not second.is_empty(), "two equipment files with distinct URI textures")
	if first.is_empty() or second.is_empty():
		return
	var actor: Dictionary = await blocked(_worker_prepare.bind(first))
	var record: Dictionary = actor.get("record", {})
	var root_value: Variant = record.get("root")
	check(root_value is Node3D and (root_value as Node3D).get_parent() == null
		and not (root_value as Node3D).is_inside_tree(), "prepare_actor returns an unpacked, unparented root")
	check(bool(record.get("actor_images", false)), "the worker parse used the actor image extension")
	check(not bool(actor.get("waited_for_main", true)),
		"a worker actor parse of %s does not wait for a blocked main thread" % first.get_file())
	Cache.discard_actor_prepared(record)
	check(not record.has("root") and not is_instance_valid(root_value), "discard frees the root")
	Cache.discard_actor_prepared(record)
	var plain: Dictionary = await blocked(_worker_plain.bind(second))
	check(bool(plain.get("ok", false)) and bool(plain.get("waited_for_main", false)),
		"control: the plain parse of %s on a worker waits for the main thread" % second.get_file())
	print("AW03_BLOCKED ", JSON.stringify({"actor_file": first.get_file(), "actor_ms": int(actor.get("us", 0)) / 1000.0,
		"actor_waited": actor.get("waited_for_main"), "plain_file": second.get_file(),
		"plain_ms": int(plain.get("us", 0)) / 1000.0, "plain_waited": plain.get("waited_for_main"),
		"block_ms": BLOCK_MS}))


# --- 2: registration and the switch ------------------------------------------

func check_registration() -> void:
	check(Quantization.ensure_registered(), "main registration completes")
	var extension: GLTFDocumentExtension = Quantization._actor_images
	check(extension != null and extension.get_script() == ActorImages,
		"GltfQuantization.ensure_registered registers actor_images.gd")
	if extension == null:
		return
	var state := GLTFState.new()
	state.set_json({"asset": {"version": "2.0"}, "images": [{"uri": "textures/a.jpg", "mimeType": "image/jpeg"}]})
	state.set_base_path(ProjectSettings.globalize_path(ACTOR_ROOT + "/equipment"))
	var before := JSON.stringify(state.get_json())
	check(extension._import_preflight(state, PackedStringArray()) == ERR_SKIP,
		"a document that is not an actor document gets ERR_SKIP")
	check(JSON.stringify(state.get_json()) == before and state.get_additional_data(ActorImages.URI_ORIGINALS) == null,
		"ERR_SKIP leaves a foreign document untouched")
	ActorImages.configure("legacy")
	var legacy_state := GLTFState.new()
	check(not ActorImages.enable(legacy_state) and not ActorImages.is_enabled(legacy_state)
		and not ActorImages.active(), "ELORIA_ACTOR_IMAGES=legacy leaves actor documents to plain GLTFDocument")
	check(not bool(Cache.prepare_actor("res://assets/world/not_an_actor.glb").get("actor_images", true)),
		"prepare_actor reports the legacy switch")
	ActorImages.configure()
	check(ActorImages.mode() != "legacy" and ActorImages.active(), "the default actor image mode is active")
	var foreign := Cache.prepare_actor("res://assets/world/not_an_actor.glb")
	check(str(foreign.get("error", "")) == "not_actor_document" and not foreign.has("root"),
		"prepare_actor refuses a document outside the actor root")
	check(Cache.is_actor_document(ACTOR_ROOT + "/equipment/x.glb")
		and Cache.is_actor_document(ProjectSettings.globalize_path(ACTOR_ROOT + "/races/x.glb"))
		and not Cache.is_actor_document("res://assets/world/x.glb")
		and not Cache.is_actor_document("user://x.glb"), "actor documents are the files under assets/actors")


## Before main has registered the extensions, a worker's prepare_actor is
## refused and the actor image switch is read without being written (main
## writes it during registration). Only meaningful as the first thing run.
func check_worker_before_registration() -> void:
	if Quantization.is_registered():
		print("AW03_SKIP worker-before-registration: extensions already registered")
		return
	var record: Dictionary = await on_worker(_worker_unregistered.bind(ACTOR_ROOT + "/races/absent.glb"))
	check(str(record.get("error", "")) == "unregistered" and not record.has("root")
		and not bool(record.get("actor_images", true)),
		"a worker prepare_actor before main registration is refused as unregistered")
	check(not str(record.get("mode", "")).is_empty() and ActorImages._mode.is_empty(),
		"a worker reads the actor image switch without writing it")


## The decoder only runs on bytes with its signature: a mismatched declared
## type still decodes, and bytes it cannot decode (WebP) leave the image empty
## for GLTFDocument without a decoder error here (the log grep sees any).
func check_decode_signatures() -> void:
	var source := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	source.fill(Color(0.2, 0.6, 0.9))
	var png := source.save_png_to_buffer()
	var expected := Image.new()
	expected.load_png_from_buffer(png)
	var mislabelled := Image.new()
	ActorImages.decode(png, "image/jpeg", mislabelled)
	check(not mislabelled.is_empty() and mislabelled.get_data() == expected.get_data(),
		"a PNG declared image/jpeg decodes as PNG")
	var webp := Image.new()
	ActorImages.decode(source.save_webp_to_buffer(true), "image/webp", webp)
	check(webp.is_empty(), "WebP bytes are left to GLTFDocument")
	var garbage := Image.new()
	ActorImages.decode(PackedByteArray([1, 2, 3]), "", garbage)
	check(garbage.is_empty(), "unknown bytes are left to GLTFDocument")


## The packed scene's albedo, metallic and roughness images as
## "format size mips sha256" strings, everything freed before returning.
func spec_gloss_textures(path: String, actor_document: bool) -> Array[String]:
	var out: Array[String] = []
	var root := Cache._parse_generate(path, {}, actor_document)
	var scene := Cache._pack_generated(path, root) if root != null else null
	if scene == null:
		return out
	var instance: Node = scene.instantiate()
	var meshes: Array[Node] = instance.find_children("*", "MeshInstance3D", true, false)
	var material: BaseMaterial3D = null
	if not meshes.is_empty():
		material = (meshes[0] as MeshInstance3D).mesh.surface_get_material(0) as BaseMaterial3D
	if material != null:
		for slot: int in [BaseMaterial3D.TEXTURE_ALBEDO, BaseMaterial3D.TEXTURE_METALLIC,
				BaseMaterial3D.TEXTURE_ROUGHNESS]:
			var texture := material.get_texture(slot)
			var image: Image = texture.get_image() if texture != null else null
			if image == null:
				out.append("none")
			else:
				out.append("%d %s %s %s" % [image.get_format(), image.get_size(), image.has_mipmaps(),
					image.get_data().hex_encode().sha256_text()])
	instance.free()
	return out


## GLTFDocument converts a KHR_materials_pbrSpecularGlossiness material from
## its textures' pixels during the parse, so such a document keeps its URI
## textures unplaceholdered and its actor parse equals the plain one.
func check_spec_gloss() -> void:
	var directory := OS.get_user_data_dir().path_join("aw03_spec_gloss")
	DirAccess.make_dir_recursive_absolute(directory)
	var diffuse := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	diffuse.fill(Color(0.8, 0.3, 0.2))
	check(ResourceSaver.save(ImageTexture.create_from_image(diffuse), directory.path_join("diffuse.res")) == OK,
		"spec-gloss diffuse texture saved")
	var gloss := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	gloss.fill(Color(0.5, 0.5, 0.5, 0.25))
	var gloss_png := gloss.save_png_to_buffer()
	var binary := PackedByteArray()
	binary.append_array(PackedFloat32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]).to_byte_array())
	binary.append_array(PackedFloat32Array([0, 0, 1, 0, 0, 1]).to_byte_array())
	binary.append_array(gloss_png)
	var document := {"asset": {"version": "2.0"}, "buffers": [{"byteLength": binary.size()}],
		"bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
			{"buffer": 0, "byteOffset": 36, "byteLength": 24},
			{"buffer": 0, "byteOffset": 60, "byteLength": gloss_png.size()}],
		"accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
			"min": [0, 0, 0], "max": [1, 1, 0]},
			{"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"}],
		"images": [{"uri": "diffuse.res"}, {"bufferView": 2, "mimeType": "image/png"}],
		"textures": [{"source": 0}, {"source": 1}],
		"materials": [{"name": "spec_gloss", "extensions": {"KHR_materials_pbrSpecularGlossiness": {
			"diffuseTexture": {"index": 0}, "specularGlossinessTexture": {"index": 1}}}}],
		"extensionsUsed": ["KHR_materials_pbrSpecularGlossiness"],
		"meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "material": 0}]}],
		"nodes": [{"name": "SpecGloss", "mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
	var path := directory.path_join("spec_gloss.glb")
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(Fixture.glb_bytes(document, binary))
	file.close()
	# Headless, the conversion edits the cached diffuse texture's image in
	# place while an earlier parse's state or scene is alive (plain parses
	# drift the same way), so each parse is summarised and freed before the next.
	var plain := spec_gloss_textures(path, false)
	var actor := spec_gloss_textures(path, true)
	check(plain.size() == 3 and plain == actor,
		"spec-gloss: actor parse equals the plain parse %s / %s" % [str(plain), str(actor)])
	var state := GLTFState.new()
	ActorImages.enable(state, path)
	check(GLTFDocument.new().append_from_file(path, state) == OK, "spec-gloss document parses as an actor document")
	check(int(ActorImages.stats(state).get("uriTextures", -1)) == 0,
		"a spec-gloss document's URI textures are not placeholdered")
	state = null
	for name: String in ["spec_gloss.glb", "diffuse.res"]:
		DirAccess.remove_absolute(directory.path_join(name))
	DirAccess.remove_absolute(directory)


# --- 3: the mixed fixture ------------------------------------------------------

func check_fixture() -> void:
	var directory := OS.get_user_data_dir().path_join("aw03_actor_images_fixture")
	var fixture := Fixture.write(directory)
	check(not fixture.is_empty(), "mixed fixture written")
	if fixture.is_empty():
		return
	var path := str(fixture.path)
	var expected: Texture2D = ResourceLoader.load(str(fixture.textures["uri_tex.res"]), "Texture2D")
	check(expected != null, "the fixture's URI texture loads through ResourceLoader")
	print("AW03_FIXTURE_LOADABLE ", JSON.stringify({"loose.png": ResourceLoader.exists(directory.path_join("loose.png")),
		"uri_tex.res": ResourceLoader.exists(str(fixture.textures["uri_tex.res"]))}))
	# The extension's own state, seen directly.
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	check(ActorImages.enable(state, path), "fixture enabled as an actor document")
	var totals_before := ActorImages.totals()
	check(document.append_from_file(path, state) == OK, "fixture parses as an actor document")
	var stats := ActorImages.stats(state)
	print("AW03_FIXTURE_STATS ", JSON.stringify(stats))
	var images: Array = state.get_json().get("images", [])
	check(images.size() == 7 and str(images[0].get("uri")) == "uri_tex.res" and not images[0].has("mimeType")
		and str(images[6].get("uri")) == "space%20name.res" and str(images[6].get("mimeType")) == "image/png",
		"post-parse restores every placeholdered URI and mimeType")
	var parsed_images := state.get_images()
	check(parsed_images.size() == 7 and parsed_images[0] == expected,
		"state.images holds the very texture ResourceLoader returns")
	var materials := state.get_materials()
	var uri_twice := materials[0] as BaseMaterial3D if materials.size() > 0 else null
	var shared := materials[3] as BaseMaterial3D if materials.size() > 3 else null
	check(uri_twice != null and uri_twice.albedo_texture == expected and uri_twice.normal_texture == expected,
		"both slots that held the placeholder now hold the loaded texture")
	check(shared != null and shared.metallic_texture == expected and shared.roughness_texture == expected,
		"another material's slots that share the image hold it too")
	var placeholders := 0
	for material: Material in materials:
		var base := material as BaseMaterial3D
		if base == null:
			continue
		for slot: int in BaseMaterial3D.TEXTURE_MAX:
			var texture := base.get_texture(slot)
			if texture != null and texture.get_width() == 1:
				placeholders += 1
	check(placeholders == 0, "no 1x1 placeholder survives in a material")
	check(int(stats.get("uriTextures", -1)) >= 1 and int(stats.get("decoded", -1)) >= 3
		and int(stats.get("decodeFailed", -1)) == 0,
		"the parse placeholdered the loadable URIs and decoded the embedded images")
	check(int(ActorImages.totals().get("documents", 0)) == int(totals_before.get("documents", 0)) + 1,
		"process totals count the document once")
	var generated := document.generate_scene(state)
	if generated != null:
		generated.free()

	# Today's plain parse, a main actor parse and a worker actor parse.
	var plain_root := Cache._parse_generate(path, {}, false)
	var plain := Cache._pack_generated(path, plain_root) if plain_root != null else null
	var main_root := Cache._parse_generate(path, {}, true)
	var main_scene := Cache._pack_generated(path, main_root) if main_root != null else null
	var worker: Dictionary = await on_worker(_worker_generate.bind(path))
	var worker_root: Node3D = worker.get("root") as Node3D
	var worker_scene := Cache._pack_generated(path, worker_root) if worker_root != null else null
	check(plain != null and main_scene != null and worker_scene != null, "fixture builds all three ways")
	var main_diffs := scene_diffs(plain, main_scene)
	var worker_diffs := scene_diffs(plain, worker_scene)
	check(main_diffs.is_empty(), "fixture: main actor parse equals the plain parse %s" % str(main_diffs))
	check(worker_diffs.is_empty(), "fixture: worker actor parse equals the plain parse %s" % str(worker_diffs))
	var instance := main_scene.instantiate() if main_scene != null else null
	var mesh := (instance.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D).mesh \
		if instance != null else null
	check(mesh != null and mesh.surface_get_material(0).albedo_texture == expected,
		"the packed actor scene's material keeps the loaded texture instance")
	if instance != null:
		instance.free()
	for name: String in ["mixed_images.glb", "uri_tex.res", "plus+name.res", "space name.res", "loose.png"]:
		DirAccess.remove_absolute(directory.path_join(name))
	DirAccess.remove_absolute(directory)


## A release-compressed creature (CreaturePayload RLCZ, append_from_buffer):
## the checkout ships none, so one is made from a real creature GLB.
func check_compressed_creature(files: Array[String]) -> void:
	var source := ""
	for path: String in files:
		if family_of(path) == "creatures" and path.get_extension() == "glb":
			source = path
			break
	check(not source.is_empty(), "a creature GLB to compress")
	if source.is_empty():
		return
	var raw := FileAccess.get_file_as_bytes(source)
	var encoded := raw.compress(FileAccess.COMPRESSION_ZSTD)
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(raw)
	var header := PackedByteArray()
	header.resize(24)
	header.encode_u64(8, raw.size())
	header.encode_u64(16, encoded.size())
	for index: int in 8:
		header[index] = Cache.CreaturePayload.MAGIC.unicode_at(index)
	header.append_array(context.finish())
	header.append_array(encoded)
	var directory := OS.get_user_data_dir().path_join("aw03_rlcz/assets/actors/native/creatures")
	DirAccess.make_dir_recursive_absolute(directory)
	var path := directory.path_join(source.get_file())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(header)
	file.close()
	check(Cache.CreaturePayload.is_compressed(path), "the copy is a release-compressed creature payload")
	var totals_before := ActorImages.totals()
	var plain_root := Cache._parse_generate(path, {}, false)
	var plain := Cache._pack_generated(path, plain_root) if plain_root != null else null
	var worker: Dictionary = await on_worker(_worker_generate.bind(path))
	var worker_root: Node3D = worker.get("root") as Node3D
	var actor := Cache._pack_generated(path, worker_root) if worker_root != null else null
	var diffs := scene_diffs(plain, actor)
	check(plain != null and actor != null and diffs.is_empty(),
		"compressed %s: worker actor parse equals the plain parse %s" % [source.get_file(), str(diffs)])
	var totals := ActorImages.totals()
	check(int(totals.get("documents", 0)) == int(totals_before.get("documents", 0)) + 1
		and int(totals.get("decoded", 0)) > int(totals_before.get("decoded", 0)),
		"the compressed creature went through the actor image extension")
	DirAccess.remove_absolute(path)


# --- 4: real actor files -------------------------------------------------------

func compare_file(path: String, families: Dictionary) -> void:
	var family := family_of(path)
	var row: Dictionary = families.get(family, {"files": 0, "failed": 0, "uriDocs": 0, "uriImages": 0,
		"uriTextures": 0, "uriLeft": 0, "decoded": 0, "plainMs": 0.0, "plainPackMs": 0.0, "actorBuildMs": 0.0,
		"workerMs": 0.0, "installMs": 0.0, "sharedTextures": 0, "examples": []})
	families[family] = row
	var canonical := ProjectSettings.globalize_path(path)
	Cache.clear()
	var totals_before := ActorImages.totals()
	var began := Time.get_ticks_usec()
	var plain_root := Cache._parse_generate(canonical, {}, false)
	row.plainMs += (Time.get_ticks_usec() - began) / 1000.0
	began = Time.get_ticks_usec()
	var plain := Cache._pack_generated(canonical, plain_root) if plain_root != null else null
	row.plainPackMs += (Time.get_ticks_usec() - began) / 1000.0
	began = Time.get_ticks_usec()
	var built := Cache._build_raw(canonical)
	row.actorBuildMs += (Time.get_ticks_usec() - began) / 1000.0
	var worker: Dictionary = await on_worker(_worker_prepare.bind(path))
	row.workerMs += int(worker.get("us", 0)) / 1000.0
	var record: Dictionary = worker.get("record", {})
	var unpacked: bool = record.get("root") is Node3D and (record.root as Node3D).get_parent() == null
	began = Time.get_ticks_usec()
	var installed := Cache.install_actor_prepared(record)
	row.installMs += (Time.get_ticks_usec() - began) / 1000.0
	var worker_scene := Cache._scenes.get(str(record.get("path", canonical))) as PackedScene
	var shared_before := shared_textures
	var diffs := scene_diffs(plain, built)
	var worker_diffs := scene_diffs(plain, worker_scene)
	row.sharedTextures += shared_textures - shared_before
	var totals := ActorImages.totals()
	for key: String in ["uriTextures", "uriLeft", "decoded"]:
		row[key] += int(totals.get(key, 0)) - int(totals_before.get(key, 0))
	var uris := uri_images(path).size()
	row.uriImages += uris
	if uris > 0:
		row.uriDocs += 1
	row.files += 1
	var ok := plain != null and diffs.is_empty() and worker_diffs.is_empty() and installed and unpacked \
		and not record.has("error")
	if not ok:
		row.failed += 1
		if (row.examples as Array).size() < 3:
			(row.examples as Array).append({"file": path.trim_prefix(ACTOR_ROOT + "/"), "main": diffs,
				"worker": worker_diffs, "installed": installed, "unpacked": unpacked,
				"error": record.get("error", "")})
	check(ok, "%s: main %s worker %s installed=%s unpacked=%s error=%s" % [path.trim_prefix(ACTOR_ROOT + "/"),
		str(diffs), str(worker_diffs), installed, unpacked, record.get("error", "")])
	Cache.clear()


func check_real_files(files: Array[String]) -> void:
	var chosen := sample(files)
	var families := {}
	var began := Time.get_ticks_msec()
	for path: String in chosen:
		await compare_file(path, families)
	var total_files := 0
	for family: String in families:
		var row: Dictionary = families[family]
		total_files += int(row.files)
		print("AW03_FAMILY ", family, " ", JSON.stringify(row))
	print("AW03_SUMMARY ", JSON.stringify({"sweep": OS.get_environment("RL_AW03_SWEEP"), "files": total_files,
		"of": files.size(), "seconds": (Time.get_ticks_msec() - began) / 1000.0,
		"comparedTextures": compared_textures, "sharedTextureInstances": shared_textures,
		"actorImageTotals": ActorImages.totals()}))
	check(total_files > 0, "the sample compared at least one actor file")


# --- 5: install rules ---------------------------------------------------------

func check_install_rules(files: Array[String]) -> void:
	var race := ""
	for path: String in files:
		if family_of(path) == "races":
			race = path
			break
	check(not race.is_empty(), "a race file to install")
	if race.is_empty():
		return
	var canonical := ProjectSettings.globalize_path(race)
	Cache.clear()
	var stale := Cache.prepare_actor(race)
	var stale_root: Variant = stale.get("root")
	stale["stamp"] = [0, 0]
	check(not Cache.install_actor_prepared(stale) and not Cache._scenes.has(canonical)
		and not is_instance_valid(stale_root), "a record whose file changed is freed, not published")
	var cached := Cache.packed_scene(race)
	var late := Cache.prepare_actor(race)
	var late_root: Variant = late.get("root")
	check(cached != null and Cache.install_actor_prepared(late) and Cache._scenes.get(canonical) == cached
		and not is_instance_valid(late_root), "an already cached path keeps its scene; the late root is freed")
	Cache.clear()
	var fresh := Cache.prepare_actor(race)
	var installed := Cache.install_actor_prepared(fresh)
	var instance := Cache.instantiate(race)
	check(installed and instance != null and Cache.cached_scene_count() == 1,
		"an installed record serves instantiate() without another parse")
	if instance != null:
		instance.free()
	var operations: Dictionary = Cache.retention_snapshot().timings.get("operations", {})
	check(operations.has(&"actor_prepared_install") or operations.has("actor_prepared_install"),
		"install time is recorded in the cache diagnostics")
	check(Cache.retention_snapshot().has("actor_images"), "the cache diagnostics carry the actor image totals")
	Cache.clear()


func run() -> void:
	var environment := {}
	for key: String in ["RABBITLANDS_PREPARED_CONTENT", "ELORIA_NO_GEOMETRY_CACHE"]:
		environment[key] = OS.get_environment(key)
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", "1")
	await check_worker_before_registration()
	check(Quantization.ensure_registered(), "extensions registered on main before any worker parse")
	var files: Array[String] = []
	gltf_files(ACTOR_ROOT, files)
	files.sort()
	check(files.size() > 100, "actor glTF files found (%d)" % files.size())
	await check_blocked_main(files)
	check_registration()
	check_decode_signatures()
	check_spec_gloss()
	await check_fixture()
	await check_compressed_creature(files)
	await check_real_files(files)
	check_install_rules(files)
	for key: String in environment:
		OS.set_environment(key, str(environment[key]))
	print("test_actor_worker_parse: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

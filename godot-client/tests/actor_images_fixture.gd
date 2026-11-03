extends RefCounted
## One glTF binary that carries every kind of image an actor document can name
## (2026-11 wave-2 schedule 1.1 #4), for tests/test_actor_worker_parse.gd and
## AT-C2's tests/test_actor_images.gd. `write(directory)` puts it and its
## texture files in `directory` (a user:// or absolute folder) and returns
## {"path", "images": [{"kind", "uri"?, "color"}...], "textures": {name: path}}.
##
## Images, in index order:
##   0 uri       "uri_tex.res": a Texture2D resource ResourceLoader loads
##               (stands in for an imported equipment texture); used by two
##               slots of material 0 and by material 3's metal/roughness slot
##   1 loose     "loose.png": a PNG file with no import, so ResourceLoader has
##               nothing and GLTFDocument reads the bytes
##   2 embedded  bufferView PNG, declared image/png
##   3 jpeg      bufferView JPEG, declared image/jpeg
##   4 data      data: URI JPEG with no mimeType property
##   5 plus      "plus+name.res": tells uri_decode and uri_file_decode apart
##   6 space     "space%20name.res" naming "space name.res"
## Five triangles, one per material: 0 albedo+normal = image 0; 1 albedo =
## image 1; 2 albedo = image 2; 3 albedo = image 3, metallic/roughness =
## image 0; 4 albedo = image 4, emission = image 5, occlusion = image 6.

const SIZE := 4


static func _image(color: Color) -> Image:
	var image := Image.create(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	image.fill(color)
	image.set_pixel(1, 2, Color(color.b, color.r, color.g, 1.0))
	return image


static func _save_texture(path: String, color: Color) -> Error:
	return ResourceSaver.save(ImageTexture.create_from_image(_image(color)), path)


static func _store(path: String, bytes: PackedByteArray) -> Error:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_buffer(bytes)
	file.close()
	return OK


static func glb_bytes(document: Dictionary, binary: PackedByteArray) -> PackedByteArray:
	var text := JSON.stringify(document).to_utf8_buffer()
	while text.size() % 4:
		text.append(32)
	while binary.size() % 4:
		binary.append(0)
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


static func write(directory: String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(directory)
	var colors := [Color(0.9, 0.1, 0.1), Color(0.1, 0.8, 0.2), Color(0.1, 0.2, 0.9),
		Color(0.7, 0.7, 0.1), Color(0.6, 0.2, 0.7), Color(0.2, 0.7, 0.7), Color(0.5, 0.5, 0.5)]
	var textures := {"uri_tex.res": directory.path_join("uri_tex.res"),
		"plus+name.res": directory.path_join("plus+name.res"),
		"space name.res": directory.path_join("space name.res")}
	if _save_texture(textures["uri_tex.res"], colors[0]) != OK \
			or _save_texture(textures["plus+name.res"], colors[5]) != OK \
			or _save_texture(textures["space name.res"], colors[6]) != OK:
		return {}
	if _store(directory.path_join("loose.png"), _image(colors[1]).save_png_to_buffer()) != OK:
		return {}
	var embedded := _image(colors[2]).save_png_to_buffer()
	var embedded_jpeg := _image(colors[3]).save_jpg_to_buffer(0.95)
	var data_jpeg := _image(colors[4]).save_jpg_to_buffer(0.95)

	var binary := PackedByteArray()
	var views: Array = []
	var accessors: Array = []
	var primitives: Array = []
	for triangle: int in 5:
		var x := float(triangle) * 2.0
		var positions := PackedFloat32Array([x, 0, 0, x + 1, 0, 0, x, 1, 0]).to_byte_array()
		var normals := PackedFloat32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]).to_byte_array()
		var uvs := PackedFloat32Array([0, 0, 1, 0, 0, 1]).to_byte_array()
		var first := accessors.size()
		for chunk: Array in [[positions, "VEC3"], [normals, "VEC3"], [uvs, "VEC2"]]:
			var bytes: PackedByteArray = chunk[0]
			views.append({"buffer": 0, "byteOffset": binary.size(), "byteLength": bytes.size()})
			var accessor := {"bufferView": views.size() - 1, "componentType": 5126, "count": 3, "type": chunk[1]}
			if chunk[1] == "VEC3" and accessors.size() == first:
				accessor["min"] = [x, 0, 0]
				accessor["max"] = [x + 1, 1, 0]
			accessors.append(accessor)
			binary.append_array(bytes)
		primitives.append({"attributes": {"POSITION": first, "NORMAL": first + 1, "TEXCOORD_0": first + 2},
			"material": triangle})
	var image_views := []
	for bytes: PackedByteArray in [embedded, embedded_jpeg]:
		while binary.size() % 4:
			binary.append(0)
		views.append({"buffer": 0, "byteOffset": binary.size(), "byteLength": bytes.size()})
		image_views.append(views.size() - 1)
		binary.append_array(bytes)
	var document := {
		"asset": {"version": "2.0"}, "buffers": [{"byteLength": binary.size()}],
		"bufferViews": views, "accessors": accessors,
		"images": [
			{"uri": "uri_tex.res", "name": "uri_texture"},
			{"uri": "loose.png", "name": "loose_png"},
			{"bufferView": image_views[0], "mimeType": "image/png", "name": "embedded_png"},
			{"bufferView": image_views[1], "mimeType": "image/jpeg", "name": "embedded_jpeg"},
			{"uri": "data:image/jpeg;base64," + Marshalls.raw_to_base64(data_jpeg), "name": "data_jpeg"},
			{"uri": "plus+name.res", "name": "plus_name"},
			{"uri": "space%20name.res", "mimeType": "image/png", "name": "space_name"}],
		"textures": [{"source": 0}, {"source": 1}, {"source": 2}, {"source": 3}, {"source": 4},
			{"source": 5}, {"source": 6}],
		"materials": [
			{"name": "uri_twice", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}},
				"normalTexture": {"index": 0}},
			{"name": "loose", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
			{"name": "embedded", "pbrMetallicRoughness": {"baseColorTexture": {"index": 2}}},
			{"name": "embedded_jpeg", "pbrMetallicRoughness": {"baseColorTexture": {"index": 3},
				"metallicRoughnessTexture": {"index": 0}}},
			{"name": "data_and_names", "pbrMetallicRoughness": {"baseColorTexture": {"index": 4}},
				"emissiveTexture": {"index": 5}, "emissiveFactor": [1, 1, 1],
				"occlusionTexture": {"index": 6}}],
		"meshes": [{"name": "mixed", "primitives": primitives}],
		"nodes": [{"name": "MixedImages", "mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
	var path := directory.path_join("mixed_images.glb")
	if _store(path, glb_bytes(document, binary)) != OK:
		return {}
	return {"path": path, "textures": textures, "colors": colors,
		"kinds": ["uri", "loose", "embedded", "jpeg", "data", "plus", "space"]}

extends Resource
## Immutable per-load road-field carrier. Decode on a loader worker; no Nodes,
## global strong cache, texture-quality reduction or renderer readback.

const SCHEMA := "rabbitlands-road-terrain-blend-v1"
const MAX_PIXELS := 16 * 1024 * 1024
const MAX_RECORDS := 2 * 1024 * 1024
const LAYOUT: Array[String] = ["u_at_grid_origin", "v_at_grid_origin", "dU_dX", "dU_dZ",
	"dV_dX", "dV_dZ", "style_id", "reserved"]

var document: Dictionary = {}
var metadata_path := ""
var dependencies: Dictionary = {}
var coverage: Image
var coverage_l0: Image
var ids: Image
var coefficients: Image
var id_bytes := PackedByteArray()
var coefficient_styles := PackedByteArray()
var id_stride := 0
var origin := Vector2.ZERO
var extent := Vector2.ONE
var width := 0
var height := 0
var ppm := 0.0
var records_per_row := 0
var record_count := 0
var decoded_bytes := 0
var styles: Array[BaseMaterial3D] = []
var source_candidates: Array[Dictionary] = []
var shader_sources: Dictionary = {}
var coverage_texture: ImageTexture
var id_texture: ImageTexture
var coefficient_texture: ImageTexture

static func read(config: Dictionary, manifest_path: String) -> Dictionary:
	var closure: Dictionary = dependency_closure(config, manifest_path)
	if not bool(closure.get("ok", false)):
		return closure
	if bool(closure.get("absent", false)):
		return closure
	var data: Variant = (load("res://src/world/road_ground/field_data.gd") as Script).new()
	data.document = closure.document
	data.metadata_path = str(closure.metadata_path)
	data.dependencies = closure.files
	var error: String = data._decode(str(closure.metadata_path))
	if not error.is_empty():
		return {"ok": false, "error": error}
	return {"ok": true, "data": data}

## Shared authoritative closure for runtime, cache proof and packaging. Every
## URI is relative and remains inside the loose eloria-assets tree.
static func dependency_closure(config: Dictionary, manifest_path: String) -> Dictionary:
	if config.is_empty():
		return {"ok": true, "absent": true, "files": {}}
	var path: String = safe_path(manifest_path.get_base_dir(), str(config.get("metadata", "")))
	var expected: String = str(config.get("sha256", ""))
	if path.is_empty() or not valid_sha(expected) or FileAccess.get_sha256(path) != expected:
		return {"ok": false, "error": "road_metadata_path_or_hash"}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary or str(parsed.get("schema", "")) != SCHEMA \
			or str(parsed.get("mask_space", "")) != "gltf_scene_world_xz":
		return {"ok": false, "error": "road_metadata_schema"}
	var files: Dictionary = {path: expected}
	var field: Variant = parsed.get("field")
	var rows: Variant = parsed.get("styles")
	if not field is Dictionary or not rows is Array or rows.is_empty() or rows.size() > 2:
		return {"ok": false, "error": "road_field_or_styles"}
	var records: Array = [field.get("triangle_ids", {}), field.get("affine_coefficients", {})]
	for mip: Variant in field.get("coverage_mips", []):
		records.append(mip)
	for record: Variant in records:
		if not record is Dictionary:
			return {"ok": false, "error": "road_resource_record"}
		var digest: String = str(record.get("file_sha256", record.get("sha256", "")))
		var failure: String = _add_file(files, path.get_base_dir(), str(record.get("file", "")), digest)
		if not failure.is_empty():
			return {"ok": false, "error": failure}
	for style: Variant in rows:
		if not style is Dictionary or not style.get("material_document") is Dictionary \
				or not style.get("externalResources") is Dictionary:
			return {"ok": false, "error": "road_material_record"}
		for image: Dictionary in style.material_document.get("images", []):
			var uri: String = str(image.get("uri", ""))
			var failure: String = _add_file(files, path.get_base_dir(), uri, str(style.externalResources.get(uri, "")))
			if not failure.is_empty():
				return {"ok": false, "error": failure}
	for uri: String in parsed.get("resources", {}):
		var failure: String = _add_file(files, path.get_base_dir(), uri, str(parsed.resources[uri]))
		if not failure.is_empty():
			return {"ok": false, "error": failure}
	return {"ok": true, "document": parsed, "metadata_path": path, "files": files}

static func _add_file(files: Dictionary, directory: String, relative: String, digest: String) -> String:
	var path: String = safe_path(directory, relative)
	if path.is_empty() or not valid_sha(digest):
		return "road_resource_path_or_digest"
	if files.has(path):
		return "" if str(files[path]) == digest else "road_resource_conflicting_digest"
	if FileAccess.get_sha256(path) != digest:
		return "road_resource_missing_or_changed: " + relative
	files[path] = digest
	return ""

static func safe_path(directory: String, relative: String) -> String:
	if relative.is_empty() or relative.is_absolute_path() or ":" in relative or "\\" in relative:
		return ""
	var path: String = ProjectSettings.globalize_path(directory).replace("\\", "/").path_join(relative).simplify_path()
	var scope: String = ProjectSettings.globalize_path("res://../eloria-assets").replace("\\", "/").simplify_path().trim_suffix("/")
	return path if path.to_lower().begins_with(scope.to_lower() + "/") else ""

static func valid_sha(value: String) -> bool:
	return value.length() == 64 and RegEx.create_from_string("^[0-9a-f]{64}$").search(value) != null

static func sha(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

func _decode(metadata_path: String) -> String:
	var targets: Variant = document.get("targets")
	if not targets is Array or targets.is_empty() or not valid_matrix(document.get("source_frame_matrix")) \
			or str(document.get("source_frame_node", "")).is_empty():
		return "road_target_frame_contract"
	var names: Dictionary = {}
	for target: Variant in targets:
		if not target is Dictionary or not valid_matrix(target.get("world_matrix")):
			return "road_target_frame_contract"
		var name: String = str(target.get("name", ""))
		if names.has(name) or not (name.begins_with("AuthoredGround_") or name.begins_with("Terrain_")):
			return "road_target_name_contract"
		names[name] = true
	if not names.has(str(document.source_frame_node)):
		return "road_source_frame_not_target"
	var field: Dictionary = document.field
	var grid: Variant = field.get("grid")
	if not grid is Dictionary:
		return "road_grid"
	width = int(grid.get("width", 0))
	height = int(grid.get("height", 0))
	ppm = float(grid.get("pixels_per_metre", 0.0))
	var raw_origin: Variant = grid.get("origin_xz")
	if width < 1 or height < 1 or width * height > MAX_PIXELS or not is_finite(ppm) or ppm != 4.0 \
			or not raw_origin is Array or raw_origin.size() != 2 \
			or str(grid.get("axis_order", "")) != "row_increasing_z,column_increasing_x":
		return "road_grid_bounds"
	origin = Vector2(float(raw_origin[0]), float(raw_origin[1]))
	extent = Vector2(width / ppm, height / ppm)
	if not origin.is_finite():
		return "road_grid_origin"
	var mips: Variant = field.get("coverage_mips")
	if not mips is Array or mips.is_empty():
		return "road_coverage_mips"
	var bytes := PackedByteArray()
	var w: int = width
	var h: int = height
	for level: int in mips.size():
		var mip: Variant = mips[level]
		if not mip is Dictionary or int(mip.get("level", -1)) != level \
				or int(mip.get("width", 0)) != w or int(mip.get("height", 0)) != h:
			return "road_coverage_mip_layout"
		var image := Image.new()
		if image.load(safe_path(metadata_path.get_base_dir(), str(mip.file))) != OK \
				or image.get_width() != w or image.get_height() != h:
			return "road_coverage_decode"
		image.convert(Image.FORMAT_R8)
		if not valid_sha(str(mip.get("decoded_sha256", ""))) or sha(image.get_data()) != str(mip.decoded_sha256):
			return "road_coverage_decoded_hash"
		if level == 0:
			coverage_l0 = image
		bytes.append_array(image.get_data())
		if w == 1 and h == 1 and level != mips.size() - 1:
			return "road_coverage_extra_mips"
		w = maxi(1, w >> 1)
		h = maxi(1, h >> 1)
	if int(mips[-1].width) != 1 or int(mips[-1].height) != 1:
		return "road_coverage_missing_mips"
	coverage = Image.create_from_data(width, height, mips.size() > 1, Image.FORMAT_R8, bytes)
	decoded_bytes = bytes.size()
	var id_record: Dictionary = field.get("triangle_ids", {})
	id_stride = 2 if str(id_record.get("format", "")) == "RG8" else 3 if str(id_record.get("format", "")) == "RGB8" else 0
	if id_stride == 0 or int(id_record.get("width", 0)) != width or int(id_record.get("height", 0)) != height \
			or bool(id_record.get("mipmaps", true)) or int(id_record.get("id_base", 0)) != 1:
		return "road_id_layout"
	var decoded: Dictionary = _decode_zstd(metadata_path, id_record, width * height * id_stride)
	if not bool(decoded.get("ok", false)):
		return str(decoded.error)
	id_bytes = decoded.bytes
	ids = Image.create_from_data(width, height, false, Image.FORMAT_RG8 if id_stride == 2 else Image.FORMAT_RGB8, id_bytes)
	decoded_bytes += id_bytes.size()
	var table: Dictionary = field.get("affine_coefficients", {})
	record_count = int(table.get("record_count", 0))
	records_per_row = int(table.get("records_per_row", 0))
	var tw: int = int(table.get("width", 0))
	var th: int = int(table.get("height", 0))
	if str(table.get("format", "")) != "RGBA32F" or bool(table.get("mipmaps", true)) \
			or table.get("layout") != LAYOUT or record_count < 1 or record_count > MAX_RECORDS \
			or records_per_row != mini(record_count, 1024) or tw != records_per_row * 2 \
			or th != ceili(float(record_count) / records_per_row) or th > 16384 \
			or int(table.get("texels_per_record", 0)) != 2:
		return "road_affine_layout"
	decoded = _decode_zstd(metadata_path, table, tw * th * 16)
	if not bool(decoded.get("ok", false)):
		return str(decoded.error)
	var floats: PackedFloat32Array = (decoded.bytes as PackedByteArray).to_float32_array()
	coefficient_styles.resize(record_count)
	for index: int in floats.size():
		if not is_finite(floats[index]):
			return "road_affine_nonfinite"
	for index: int in record_count:
		var style: int = int(floats[index * 8 + 6])
		if float(style) != floats[index * 8 + 6] or style < 0 or style >= document.styles.size():
			return "road_affine_style_bounds"
		coefficient_styles[index] = style
	for index: int in width * height:
		var record_id: int = _id(index)
		if record_id < 0 or record_id > record_count or (record_id == 0 and coverage_l0.get_pixel(index % width, index / width).r > 0.0):
			return "road_triangle_id_bounds"
	coefficients = Image.create_from_data(tw, th, false, Image.FORMAT_RGBAF, decoded.bytes)
	decoded_bytes += (decoded.bytes as PackedByteArray).size()
	return ""

static func _decode_zstd(metadata_path: String, record: Dictionary, expected: int) -> Dictionary:
	if str(record.get("compression", "")) != "zstd" or str(record.get("byte_order", "")) != "little" \
			or int(record.get("uncompressed_bytes", -1)) != expected or not valid_sha(str(record.get("sha256", ""))):
		return {"ok": false, "error": "road_binary_contract"}
	var stored: PackedByteArray = FileAccess.get_file_as_bytes(safe_path(metadata_path.get_base_dir(), str(record.get("file", ""))))
	# dependency_closure already verifies this, but retain the proof on the
	# exact encoded bytes decompressed if files change between the two reads.
	if sha(stored) != str(record.get("file_sha256", "")):
		return {"ok": false, "error": "road_binary_stored_hash"}
	var bytes: PackedByteArray = stored.decompress(expected, FileAccess.COMPRESSION_ZSTD)
	if bytes.size() != expected or sha(bytes) != str(record.sha256):
		return {"ok": false, "error": "road_binary_decoded_hash_or_size"}
	return {"ok": true, "bytes": bytes}

static func valid_matrix(value: Variant) -> bool:
	if not value is Array or value.size() != 16:
		return false
	for component: Variant in value:
		if not (component is int or component is float) or not is_finite(float(component)):
			return false
	var basis := Basis(Vector3(value[0], value[1], value[2]), Vector3(value[4], value[5], value[6]),
		Vector3(value[8], value[9], value[10]))
	return absf(basis.determinant()) > 0.000000001 and float(value[3]) == 0.0 \
		and float(value[7]) == 0.0 and float(value[11]) == 0.0 and float(value[15]) == 1.0

func _id(pixel: int) -> int:
	var offset: int = pixel * id_stride
	var value: int = int(id_bytes[offset]) | (int(id_bytes[offset + 1]) << 8)
	return value | (int(id_bytes[offset + 2]) << 16) if id_stride == 3 else value

func sample(point: Vector2) -> Dictionary:
	if not Rect2(origin, extent).has_point(point):
		return {"present": false}
	var pixel: Vector2 = (point - origin) * ppm
	var cell := Vector2i(clampi(int(floor(pixel.x)), 0, width - 1), clampi(int(floor(pixel.y)), 0, height - 1))
	var record_id: int = _id(cell.y * width + cell.x)
	if record_id == 0:
		return {"present": false}
	var centred: Vector2 = pixel - Vector2(0.5, 0.5)
	var lower := Vector2i(int(floor(centred.x)), int(floor(centred.y)))
	var blend: Vector2 = centred - Vector2(lower)
	var a: float = coverage_l0.get_pixel(clampi(lower.x, 0, width - 1), clampi(lower.y, 0, height - 1)).r
	var b: float = coverage_l0.get_pixel(clampi(lower.x + 1, 0, width - 1), clampi(lower.y, 0, height - 1)).r
	var c: float = coverage_l0.get_pixel(clampi(lower.x, 0, width - 1), clampi(lower.y + 1, 0, height - 1)).r
	var d: float = coverage_l0.get_pixel(clampi(lower.x + 1, 0, width - 1), clampi(lower.y + 1, 0, height - 1)).r
	var alpha: float = lerpf(lerpf(a, b, blend.x), lerpf(c, d, blend.x), blend.y)
	var style: int = int(coefficient_styles[record_id - 1])
	return {"present": alpha > 0.0, "coverage": alpha, "style_id": style,
		"style": document.styles[style], "field_point": point}

func upload() -> void:
	if coverage_texture == null:
		coverage_texture = ImageTexture.create_from_image(coverage)
		id_texture = ImageTexture.create_from_image(ids)
		coefficient_texture = ImageTexture.create_from_image(coefficients)
		# CPU queries need only L0 alpha, encoded IDs and one byte per record.
		coverage = null
		ids = null
		coefficients = null

extends SceneTree
## The class-texture metadata fast path must not ask the renderer for pixels.
const Ground := preload("res://src/world/look/look_ground.gd")
const Profile := preload("res://src/world/look/look_profile.gd")
var _failures := 0
var _checks := 0

class ObservedTexture:
	extends Texture2D
	var pixels: Image
	var reads := 0
	func _get_width() -> int: return pixels.get_width() if pixels != null else 1
	func _get_height() -> int: return pixels.get_height() if pixels != null else 1
	func _get_format() -> Image.Format: return pixels.get_format() if pixels != null else Image.FORMAT_RGBA8
	func _get_mipmap_count() -> int: return pixels.get_mipmap_count() if pixels != null else 0
	func _has_mipmaps() -> bool: return pixels != null and pixels.has_mipmaps()
	func _get_image() -> Image:
		reads += 1
		return pixels.duplicate() as Image if pixels != null else null

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> void:
	_checks += 1
	if not ok:
		_failures += 1
		push_error(label)

func _pattern(format: Image.Format) -> Image:
	var image := Image.create(8,8,false,format)
	for y: int in 8:
		for x: int in 8:
			image.set_pixel(x,y,Color(float(x)/7.0,float(y)/7.0,float((x+y)%5)/4.0,0.25+float(x%3)*0.25))
	return image

func _test_existing_mips() -> void:
	var observed := ObservedTexture.new()
	observed.pixels = _pattern(Image.FORMAT_RGB8)
	observed.pixels.generate_mipmaps()
	var before := observed.pixels.get_data()
	var result := Ground._class_texture_with_mipmaps(observed)
	_expect(result == observed, "already-mipped source retains the exact Texture2D identity")
	_expect(observed.reads == 0, "already-mipped source performs no pixel readback")
	_expect(observed.pixels.get_data() == before, "metadata fast path preserves every mip byte")

func _test_fallback(format: Image.Format) -> void:
	var observed := ObservedTexture.new()
	observed.pixels = _pattern(format)
	var before := observed.pixels.get_data()
	var expected := observed.pixels.duplicate() as Image
	expected.generate_mipmaps()
	var result := Ground._class_texture_with_mipmaps(observed)
	_expect(observed.reads == 1, "unmipped source retains one legacy fallback read")
	_expect(result != observed and result is ImageTexture, "legacy fallback creates its own mipmapped texture")
	var actual := result.get_image()
	_expect(actual != null and actual.get_format() == expected.get_format(), "fallback retains legacy pixel format")
	_expect(actual != null and actual.get_mipmap_count() == expected.get_mipmap_count(), "fallback retains the complete legacy mip chain")
	_expect(actual != null and actual.get_data() == expected.get_data(), "fallback matches every legacy base/mip byte")
	_expect(not observed.pixels.has_mipmaps() and observed.pixels.get_data() == before, "fallback leaves source texture pixels unchanged")

func _test_missing_pixels() -> void:
	var observed := ObservedTexture.new()
	var result := Ground._class_texture_with_mipmaps(observed)
	_expect(result == observed and observed.reads == 1, "missing CPU pixels preserve legacy source fallback")

func _test_native_header_guards() -> void:
	var header := PackedByteArray()
	header.resize(52)
	for index: int in 4: header[index] = "GST2".to_ascii_buffer()[index]
	header.encode_u32(4,1)
	header.encode_u32(8,8)
	header.encode_u32(12,8)
	header.encode_u32(16,1 << 23)
	header.encode_u32(36,1)
	header.encode_u16(40,8)
	header.encode_u16(42,8)
	header.encode_u32(44,3)
	header.encode_u32(48,Image.FORMAT_RGB8)
	_expect(Ground._class_texture_header_has_mipmaps(header,8,8), "recognized native v1 header declares a valid mip chain")
	_expect(not Ground._class_texture_header_has_mipmaps(header.slice(0,51),8,8), "truncated native header takes legacy fallback")
	_expect(not Ground._class_texture_header_has_mipmaps(header,16,8), "native dimensions must match the loaded texture")
	for change: Array in [[0,0],[4,0],[4,2],[8,0],[12,0],[16,0],[36,4],[44,0],[44,99],[48,Image.FORMAT_MAX]]:
		var malformed := header.duplicate()
		malformed.encode_u32(int(change[0]),int(change[1]))
		_expect(not Ground._class_texture_header_has_mipmaps(malformed,8,8), "unknown/malformed native header takes legacy fallback: "+str(change))
	var malformed := header.duplicate()
	malformed.encode_u16(40,4)
	_expect(not Ground._class_texture_header_has_mipmaps(malformed,8,8), "native image dimensions must match outer dimensions")

func _test_imported_classes() -> void:
	for name: String in Profile.CLASS_TEXTURES:
		var path := str(Profile.CLASS_TEXTURES[name].path)
		var source := load(path) as Texture2D
		_expect(source != null and Ground._class_texture_has_mipmaps(source), "authored class import already contains mips: "+name)
		if source == null: continue
		var diagnostics := {"pixel_reads":0}
		_expect(Ground._class_texture_with_mipmaps(source,diagnostics) == source and int(diagnostics.pixel_reads) == 0,
			"actual imported class fast path performs no pixel readback: "+name)
		var result := Ground.class_texture(name)
		_expect(result == source, "runtime class lookup exercises imported-identity fast path: "+name)
		# Test-only pixel reads; the timed/runtime path above uses metadata only.
		var expected := Image.new()
		_expect(expected.load_png_from_buffer(FileAccess.get_file_as_bytes(path)) == OK, "class reference PNG decodes: "+name)
		expected.generate_mipmaps()
		var actual := result.get_image()
		_expect(actual != null and actual.get_format() == expected.get_format() and actual.get_data() == expected.get_data(),
			"imported lossless base/mips equal the former runtime generation: "+name)
		_expect(Ground.class_texture(name) == source, "repeated class lookup keeps the shared imported identity: "+name)

func _run() -> void:
	_test_existing_mips()
	_test_fallback(Image.FORMAT_RGB8)
	_test_fallback(Image.FORMAT_RGBA8)
	_test_missing_pixels()
	_test_native_header_guards()
	_test_imported_classes()
	print("look ground class textures: ", "PASS" if _failures == 0 else "FAIL", " (",_checks," checks, ",_failures," failures)")
	quit(0 if _failures == 0 else 1)

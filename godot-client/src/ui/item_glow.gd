extends RefCounted
## One effect palette for inventory artwork and worn equipment. The order of
## saved rolls never changes the appearance of the same combination.
const STYLES := {
	"Emberstrike": "fire", "Flamebound": "fire", "Insulated": "fire",
	"Frostbind": "frost", "Frostbound": "frost", "Winterbound": "frost",
	"Siphoning": "arcane", "Mindfire": "arcane", "Runebound": "arcane",
	"Attuned": "arcane", "Warded": "arcane", "Channeling": "arcane",
	"Penetrating": "arcane", "Restorative": "arcane", "Spellguard": "arcane",
	"Soulreave": "soul", "Renewal": "life", "Vital": "life",
	"Irradiated": "radiation", "Shielded": "radiation",
	"Second Wind": "wind", "Balanced": "wind", "Trueflight": "wind",
	"Lightweight": "wind", "Elusive": "wind",
	"Stoneward": "earth", "Sundering": "earth", "Brutal": "earth",
	"Bodkin": "earth", "Reinforced": "earth", "Plated": "earth", "Arrowguard": "earth",
}
const FAMILIES := ["fire", "frost", "arcane", "life", "soul", "radiation", "wind", "earth"]
const COLORS := [Color("ff822e"), Color("75ddff"), Color("b18aff"), Color("67efaa"),
	Color("ed66b7"), Color("c8f44d"), Color("b8f3e7"), Color("e7ba70")]
static var _icons: Dictionary = {}

static func validated(value: Variant, maximum_slot: int) -> Dictionary:
	var result := {}
	if not value is Dictionary or value.size() > maximum_slot + 1: return result
	for raw: Variant in value:
		var key := str(raw)
		if not key.is_valid_int() or int(key) < 0 or int(key) > maximum_slot: continue
		var entry: Variant = value[raw]
		if not entry is Dictionary or entry.get("tier") not in ["magic", "rare"]: continue
		var effects: Variant = entry.get("effects")
		if not effects is Array or effects.is_empty() or effects.size() > 4: continue
		if not effects.all(func(effect: Variant) -> bool: return effect is String and effect.length() <= 64): continue
		if not entry.get("image_id") is float and not entry.get("image_id") is int: continue
		result[key] = entry.duplicate(true)
	return result

static func profile(item: Dictionary) -> Dictionary:
	var tier := str(item.get("tier", "normal"))
	if tier not in ["magic", "rare"]: return {}
	var families: Array[int] = []
	for effect: Variant in item.get("effects", []):
		var effect_name := str(effect).get_slice(":", 0)
		var family := FAMILIES.find(STYLES.get(effect_name, "arcane"))
		if not families.has(family): families.append(family)
	if families.is_empty(): families.append(2)
	families.sort()
	var colors: Array[Color] = []
	for family: int in families: colors.append(COLORS[family])
	return {"families": families, "colors": colors, "strength": 1.0 if tier == "magic" else 1.45,
		"key": tier + ":" + str(families)}

static func icon(source: Texture2D, item: Dictionary) -> Texture2D:
	var style := profile(item)
	if source == null or style.is_empty(): return source
	var key := str(source.get_instance_id()) + ":" + str(style.key)
	if _icons.has(key): return _icons[key] as Texture2D
	var image: Image
	if source is AtlasTexture:
		var atlas := source as AtlasTexture
		image = atlas.atlas.get_image().get_region(Rect2i(atlas.region))
	else:
		image = source.get_image()
	if image == null: return source
	image = image.duplicate()
	if image.is_compressed(): image.decompress()
	image.convert(Image.FORMAT_RGBA8)
	# Bound authoring-resolution artwork to a small cached UI texture. Leave
	# room around the silhouette rather than clipping its halo at the cell edge.
	image.resize(56, 56, Image.INTERPOLATE_LANCZOS)
	_unframe(image)
	var mask := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	mask.blit_rect(image, Rect2i(0, 0, 56, 56), Vector2i(4, 4))
	var blurred := PackedFloat32Array()
	blurred.resize(64 * 64)
	for y: int in 64:
		for x: int in 64:
			var value := 0.0
			for dx: int in range(-4, 5):
				value += mask.get_pixel(clampi(x + dx, 0, 63), y).a * float(5 - absi(dx)) / 25.0
			blurred[y * 64 + x] = value
	var result := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	var colors: Array = style.colors
	for y: int in 64:
		for x: int in 64:
			var alpha := 0.0
			for dy: int in range(-4, 5):
				alpha += blurred[clampi(y + dy, 0, 63) * 64 + x] * float(5 - absi(dy)) / 25.0
			var angle := atan2(float(y) - 31.5, float(x) - 31.5) + PI
			var band := angle / TAU * colors.size()
			var color: Color = colors[int(band) % colors.size()]
			var family: int = style.families[int(band) % colors.size()]
			var detail := 1.0
			match family:
				0: detail = 0.8 + 0.2 * sin(angle * 13.0 + y * 0.8) # embers
				1: detail = 0.7 + 0.3 * pow(absf(cos(angle * 6.0)), 4.0) # ice facets
				2, 5: detail = 0.75 + 0.25 * sin(angle * 9.0) # arcane/radiant rays
				7: detail = 0.85 + 0.15 * cos(angle * 4.0) # warm metallic sheen
			color.a = clampf(alpha * 2.8 * float(style.strength) * detail, 0.0, 0.95)
			result.set_pixel(x, y, color)
	result.blend_rect(mask, Rect2i(0, 0, 64, 64), Vector2i.ZERO)
	var texture := ImageTexture.create_from_image(result)
	if _icons.size() >= 256: _icons.clear()
	# Keep the source alive too: Godot instance IDs must not be recycled while
	# a texture cached by that ID remains in use.
	_icons[key] = texture
	texture.set_meta("source_icon", source)
	return texture

static func _unframe(image: Image) -> void:
	# Painted atlases carry a flat dark backdrop with opaque alpha. Flood only
	# that edge-connected backdrop out of our private copy, so the glow follows
	# the item instead of lighting up the square atlas cell. Enclosed shadows
	# and details remain intact; transparent artwork needs no treatment.
	var background := image.get_pixel(0, 0)
	if background.a < 0.95: return
	var width := image.get_width()
	var height := image.get_height()
	for corner: Vector2i in [Vector2i(width - 1, 0), Vector2i(0, height - 1), Vector2i(width - 1, height - 1)]:
		if _distance(image.get_pixelv(corner), background) > 0.025: return
	var seen := PackedByteArray()
	seen.resize(width * height)
	var queue: Array[Vector2i] = []
	for x: int in width:
		queue.append(Vector2i(x, 0))
		queue.append(Vector2i(x, height - 1))
	for y: int in height:
		queue.append(Vector2i(0, y))
		queue.append(Vector2i(width - 1, y))
	var cursor := 0
	while cursor < queue.size():
		var point := queue[cursor]
		cursor += 1
		if point.x < 0 or point.y < 0 or point.x >= width or point.y >= height: continue
		var offset := point.y * width + point.x
		if seen[offset] != 0: continue
		seen[offset] = 1
		var pixel := image.get_pixelv(point)
		var distance := _distance(pixel, background)
		if distance > 0.07: continue
		pixel.a *= smoothstep(0.008, 0.07, distance)
		image.set_pixelv(point, pixel)
		queue.append(point + Vector2i.LEFT)
		queue.append(point + Vector2i.RIGHT)
		queue.append(point + Vector2i.UP)
		queue.append(point + Vector2i.DOWN)

static func _distance(a: Color, b: Color) -> float:
	return maxf(absf(a.r - b.r), maxf(absf(a.g - b.g), absf(a.b - b.b)))

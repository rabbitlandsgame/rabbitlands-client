extends Control
## Direct 2D cartography under the existing map overlays. Camera3D remains a
## projection/picking coordinate holder; this node never renders a World3D or
## changes its viewport's update flags. Pictures are ordered back to front.
## Each row carries texture, local world-XZ extent, height, and an optional
## Transform3D taking the picture's region frame into the active world frame.

const MASK := preload("res://src/ui/map_background_2d.gdshader")
static var _uvs := PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)])
static var _colours := PackedColorArray([Color.WHITE, Color.WHITE, Color.WHITE, Color.WHITE])
var _camera: Camera3D
var _viewport_size := Vector2i.ZERO
var _pictures: Array[Dictionary] = []

func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	var mask := ShaderMaterial.new()
	mask.shader = MASK
	material = mask
	resized.connect(refresh)

func _ready() -> void:
	if get_parent() is Control:
		set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func configure(camera: Camera3D, viewport_size: Vector2i) -> void:
	_camera = camera
	_viewport_size = viewport_size
	refresh()

func set_pictures(pictures: Array) -> void:
	_pictures.clear()
	for raw: Variant in pictures:
		if not raw is Dictionary or not raw.get("texture") is Texture2D \
				or not raw.get("extent") is Rect2:
			continue
		var extent: Rect2 = raw.extent
		var height: Variant = raw.get("height", 0.0)
		var frame: Variant = raw.get("transform", Transform3D.IDENTITY)
		if extent.size.x <= 0.0 or extent.size.y <= 0.0 \
				or not extent.position.is_finite() or not extent.size.is_finite() \
				or (not height is float and not height is int) or not is_finite(float(height)) \
				or not frame is Transform3D or not frame.is_finite():
			continue
		_pictures.append({"texture": raw.texture, "extent": extent,
			"height": float(height), "transform": frame})
	refresh()

func set_round(is_round: bool) -> void:
	(material as ShaderMaterial).set_shader_parameter("rounded", is_round)
	refresh()

func clear() -> void:
	_pictures.clear()
	refresh()

## Main calls this at its map-refresh cadence after changing the camera.
## No SubViewport redraw, world traversal, physics or model work is requested.
func refresh(viewport_size := Vector2i.ZERO) -> void:
	if viewport_size.x > 0 and viewport_size.y > 0:
		_viewport_size = viewport_size
	var rect := image_rect()
	(material as ShaderMaterial).set_shader_parameter("image_rect",
		Vector4(rect.position.x, rect.position.y, rect.size.x, rect.size.y))
	queue_redraw()

## Matches the existing marker overlays' keep-aspect-centred pixel mapping.
func image_rect() -> Rect2:
	if size.x <= 0.0 or size.y <= 0.0 or _viewport_size.x <= 0 or _viewport_size.y <= 0:
		return Rect2()
	var scale := minf(size.x / float(_viewport_size.x), size.y / float(_viewport_size.y))
	var displayed := Vector2(_viewport_size) * scale
	return Rect2((size - displayed) * 0.5, displayed)

## Derived geometry is cheap, and is also available for projection/picking
## qualification without drawing or allocating meshes/materials per picture.
func projected_pictures() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var rect := image_rect()
	if not is_instance_valid(_camera) or not _camera.is_inside_tree() \
			or rect.size.x <= 0.0 or rect.size.y <= 0.0:
		return result
	var scale := rect.size / Vector2(_viewport_size)
	for picture: Dictionary in _pictures:
		var extent: Rect2 = picture.extent
		var height: float = picture.height
		var frame: Transform3D = picture.transform
		var worlds := PackedVector3Array([
			frame * Vector3(extent.position.x, height, extent.position.y),
			frame * Vector3(extent.end.x, height, extent.position.y),
			frame * Vector3(extent.end.x, height, extent.end.y),
			frame * Vector3(extent.position.x, height, extent.end.y)])
		var points := PackedVector2Array()
		for world: Vector3 in worlds:
			if _camera.is_position_behind(world):
				break
			var point := rect.position + _camera.unproject_position(world) * scale
			if not point.is_finite():
				break
			points.append(point)
		if points.size() != 4:
			continue
		var bounds := Rect2(points[0], Vector2.ZERO)
		for point: Vector2 in points:
			bounds = bounds.expand(point)
		if not bounds.intersects(rect):
			continue
		var texture: Texture2D = picture.texture
		var uvs := _uvs.duplicate()
		# Canvas polygon texture RIDs address the underlying atlas. Respect a
		# cropped Texture2D's logical margins and UV region rather than drawing
		# the complete uncropped image over the cropped world extent.
		var visited := {}
		var valid := true
		while texture is AtlasTexture:
			var atlas := texture as AtlasTexture
			if visited.has(atlas.get_instance_id()) or atlas.atlas == null \
					or atlas.get_width() <= 0 or atlas.get_height() <= 0 \
					or atlas.atlas.get_width() <= 0 or atlas.atlas.get_height() <= 0:
				valid = false
				break
			visited[atlas.get_instance_id()] = true
			var region := atlas.region
			if region.size == Vector2.ZERO:
				region.size = atlas.atlas.get_size()
			var texture_size := Vector2(atlas.get_size())
			var current := Rect2(uvs[0], uvs[2] - uvs[0])
			var opaque := Rect2(atlas.margin.position / texture_size, region.size / texture_size)
			var clipped := current.intersection(opaque)
			if clipped.size.x <= 0.0 or clipped.size.y <= 0.0:
				valid = false
				break
			var low := (clipped.position - current.position) / current.size
			var high := (clipped.end - current.position) / current.size
			var full := points.duplicate()
			points = PackedVector2Array([
				_bilinear(full, low), _bilinear(full, Vector2(high.x, low.y)),
				_bilinear(full, high), _bilinear(full, Vector2(low.x, high.y))])
			uvs = PackedVector2Array([clipped.position, Vector2(clipped.end.x, clipped.position.y),
				clipped.end, Vector2(clipped.position.x, clipped.end.y)])
			for index: int in uvs.size():
				uvs[index] = (region.position + uvs[index] * texture_size - atlas.margin.position) \
					/ Vector2(atlas.atlas.get_size())
			texture = atlas.atlas
		if valid:
			result.append({"points": points, "uvs": uvs, "texture": texture})
	return result

func _draw() -> void:
	for picture: Dictionary in projected_pictures():
		draw_polygon(picture.points, _colours, picture.uvs, picture.texture)

static func _bilinear(points: PackedVector2Array, uv: Vector2) -> Vector2:
	return points[0].lerp(points[1], uv.x).lerp(points[3].lerp(points[2], uv.x), uv.y)

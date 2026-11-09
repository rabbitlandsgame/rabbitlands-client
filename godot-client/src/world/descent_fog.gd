extends RefCounted
## Fog of war over the floor of a descent (descent_v1, server message 188).
##
## A descent floor is one section of a sectioned interior map. The server
## states the floor's grid - `origin` (the server tile of its top-left cell),
## `cell_tiles`, `width` and `height` in cells - and which of its cells the
## party has revealed, one bit a cell: row-major `i = cy * width + cx`, bit
## `i & 7` of byte `i >> 3`, 1 for revealed. Everything here is a pure function
## of that state and the map's CoordinateAdapter, so it is tested without the
## game scene (tests/test_descent_fog.gd).
##
## Main draws three things from it:
## - a black, unshaded volume over every unrevealed cell (`build_mesh`): a top
##   face TOP_METRES above the floor, higher than any wall, and side faces where
##   a revealed cell meets an unrevealed one or the edge of the grid, so the
##   tilted camera cannot look under the edge of the black;
## - a picture over the floor's rectangle for the minimap and the full map
##   (`image`, `extent`), opaque where unrevealed;
## - the test that hides creatures and objects on unrevealed cells
##   (`tile_hidden`).

## The top of the volume above the floor, well above the tallest wall of an
## underground floor (the contract's 7 m), so the black lies over the walls,
## not in them.
const TOP_METRES := 7.0
## The side faces reach this far below the floor, so no seam of light shows
## where they meet uneven ground.
const BELOW_METRES := 1.0
## A grid no larger than this many cells a side is accepted (840 tiles at the
## smallest cell is 840 cells).
const MAX_CELLS := 1024
const BASE64_ALPHABET := "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

## A tile's state on the floor grid (`tile_state`).
const OFF_GRID := -1
const UNREVEALED := 0
const REVEALED := 1


## The explored bits from their base64 text, or an empty array when the text is
## not padded base64 of exactly ceil(width * height / 8) bytes. Checked before
## decoding: Marshalls reports malformed text as an engine error.
static func decode_mask(text: String, width: int, height: int) -> PackedByteArray:
	if width <= 0 or height <= 0 or width > MAX_CELLS or height > MAX_CELLS:
		return PackedByteArray()
	var expected := (width * height + 7) / 8
	if text.length() != ((expected + 2) / 3) * 4:
		return PackedByteArray()
	var padding := 0
	for index: int in range(text.length()):
		var character := text[index]
		if character == "=":
			padding += 1
			continue
		if padding > 0 or not BASE64_ALPHABET.contains(character):
			return PackedByteArray()
	if padding > 2:
		return PackedByteArray()
	var bytes := Marshalls.base64_to_raw(text)
	if bytes.size() != expected:
		return PackedByteArray()
	return bytes


## The floor grid of an open descent state, normalised: {section, origin
## (Vector2i), cell_tiles, width, height, mask}. Empty for a closed state or one
## whose grid is not whole.
static func view(state: Dictionary) -> Dictionary:
	if not bool(state.get("open", false)):
		return {}
	var origin: Variant = state.get("origin")
	var mask: Variant = state.get("mask")
	if not origin is Array or (origin as Array).size() != 2 or not mask is PackedByteArray:
		return {}
	var width := int(state.get("width", 0))
	var height := int(state.get("height", 0))
	var cell_tiles := int(state.get("cell_tiles", 0))
	if width <= 0 or height <= 0 or cell_tiles <= 0 \
			or (mask as PackedByteArray).size() != (width * height + 7) / 8:
		return {}
	return {"section": str(state.get("section", "")),
		"origin": Vector2i(int(origin[0]), int(origin[1])), "cell_tiles": cell_tiles,
		"width": width, "height": height, "mask": mask}


## Whether a map's manifest declares the floor's section: the grid is measured
## on the descent's pool map and means nothing on any other map.
static func applies_to(manifest_data: Dictionary, section: String) -> bool:
	if section.is_empty():
		return false
	var listed: Variant = manifest_data.get("sections", [])
	if not listed is Array:
		return false
	for entry: Variant in listed as Array:
		if entry is Dictionary and str((entry as Dictionary).get("id", "")) == section:
			return true
	return false


## Whether cell (cx, cy) of a `width`-wide grid is revealed. A cell the mask
## does not hold is not.
static func revealed(mask: PackedByteArray, width: int, cx: int, cy: int) -> bool:
	if cx < 0 or cy < 0 or cx >= width:
		return false
	var index := cy * width + cx
	var byte := index >> 3
	if byte >= mask.size():
		return false
	return (mask[byte] >> (index & 7)) & 1 == 1


## The cell holding server tile (x, y): ((x - origin.x) / cell_tiles,
## (y - origin.y) / cell_tiles), rounded down. It may lie off the grid.
static func cell_of(grid: Dictionary, x: int, y: int) -> Vector2i:
	var origin: Vector2i = grid.origin
	var size := int(grid.cell_tiles)
	var dx := x - origin.x
	var dy := y - origin.y
	return Vector2i((dx - posmod(dx, size)) / size, (dy - posmod(dy, size)) / size)


static func on_grid(grid: Dictionary, cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < int(grid.width) and cell.y < int(grid.height)


## OFF_GRID, UNREVEALED or REVEALED for server tile (x, y).
static func tile_state(grid: Dictionary, x: int, y: int) -> int:
	if grid.is_empty():
		return OFF_GRID
	var cell := cell_of(grid, x, y)
	if not on_grid(grid, cell):
		return OFF_GRID
	return REVEALED if revealed(grid.mask, int(grid.width), cell.x, cell.y) else UNREVEALED


## True for a tile on an unrevealed cell of the floor grid. A tile off the
## grid belongs to no fog (another floor's section is hidden by SecretSections).
static func tile_hidden(grid: Dictionary, x: int, y: int) -> bool:
	return tile_state(grid, x, y) == UNREVEALED


static func tile_revealed(grid: Dictionary, x: int, y: int) -> bool:
	return tile_state(grid, x, y) == REVEALED


## What the drawn fog depends on: a new mask, floor or grid changes it; the
## clock and the boss line do not.
static func signature(grid: Dictionary) -> String:
	if grid.is_empty():
		return ""
	return "%s|%d,%d|%d|%dx%d|%s" % [grid.section, grid.origin.x, grid.origin.y,
		int(grid.cell_tiles), int(grid.width), int(grid.height),
		Marshalls.raw_to_base64(grid.mask)]


## Godot position (y = 0) of the corner of cell (cx, cy) nearest the grid's
## origin; (width, height) is the far corner. The adapter is affine, so three
## points place every corner.
static func _corners(grid: Dictionary, adapter: CoordinateAdapter) -> Array[Vector3]:
	var origin: Vector2i = grid.origin
	var size := float(int(grid.cell_tiles))
	var start := adapter.server_to_godot(float(origin.x), float(origin.y), 0.0)
	var step_x := adapter.server_to_godot(float(origin.x) + size, float(origin.y), 0.0) - start
	var step_y := adapter.server_to_godot(float(origin.x), float(origin.y) + size, 0.0) - start
	return [start, step_x, step_y]


## The rectangle the floor grid covers on the ground, in Godot metres (x, z).
static func extent(grid: Dictionary, adapter: CoordinateAdapter) -> Rect2:
	if grid.is_empty() or adapter == null:
		return Rect2()
	var frame := _corners(grid, adapter)
	var far: Vector3 = frame[0] + frame[1] * float(int(grid.width)) + frame[2] * float(int(grid.height))
	var low := Vector2(minf(frame[0].x, far.x), minf(frame[0].z, far.z))
	var high := Vector2(maxf(frame[0].x, far.x), maxf(frame[0].z, far.z))
	return Rect2(low, high - low)


## The map fog: one pixel a cell, opaque black where unrevealed and clear where
## revealed, laid out as the map pictures are (image x along Godot +X, image y
## along Godot +Z, over `extent`). Server y runs north, so with the usual
## inverted Y the grid's first row is the image's last.
static func image(grid: Dictionary, adapter: CoordinateAdapter) -> Image:
	if grid.is_empty() or adapter == null:
		return null
	var width := int(grid.width)
	var height := int(grid.height)
	var frame := _corners(grid, adapter)
	var flip_x: bool = frame[1].x < 0.0
	var flip_y: bool = frame[2].z < 0.0
	var mask: PackedByteArray = grid.mask
	var pixels := PackedByteArray()
	pixels.resize(width * height * 4)
	for cy: int in range(height):
		var row := (height - 1 - cy) if flip_y else cy
		for cx: int in range(width):
			if revealed(mask, width, cx, cy):
				continue
			var column := (width - 1 - cx) if flip_x else cx
			# Black (0, 0, 0) and opaque; revealed pixels stay clear.
			pixels[(row * width + column) * 4 + 3] = 255
	return Image.create_from_data(width, height, false, Image.FORMAT_RGBA8, pixels)


## The volume over the unrevealed cells, one surface, or null when there is
## nothing to draw. `floor_height` is the walking height of the map. Top faces
## are merged along each row; a side face stands on every cell edge with a
## revealed cell on one side and an unrevealed cell or the grid's edge on the
## other (outside the grid is void: nothing is seen past the floor's edge).
static func build_mesh(grid: Dictionary, adapter: CoordinateAdapter, floor_height: float) -> ArrayMesh:
	if grid.is_empty() or adapter == null:
		return null
	var width := int(grid.width)
	var height := int(grid.height)
	var mask: PackedByteArray = grid.mask
	var frame := _corners(grid, adapter)
	var start: Vector3 = frame[0]
	var step_x: Vector3 = frame[1]
	var step_y: Vector3 = frame[2]
	var top := Vector3.UP * (floor_height + TOP_METRES)
	var bottom := Vector3.UP * (floor_height - BELOW_METRES)
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	for cy: int in range(height):
		var cx := 0
		while cx < width:
			if revealed(mask, width, cx, cy):
				cx += 1
				continue
			var first := cx
			while cx < width and not revealed(mask, width, cx, cy):
				cx += 1
			var a := start + step_x * first + step_y * cy
			var b := start + step_x * cx + step_y * cy
			_quad(vertices, normals, indices, a + top, b + top,
				b + step_y + top, a + step_y + top, Vector3.UP)
	# Edges between columns cx - 1 and cx (x = 0..width), then between rows.
	# Each side faces the revealed cell it bounds.
	for cy: int in range(height):
		for cx: int in range(width + 1):
			var west := revealed(mask, width, cx - 1, cy) if cx > 0 else false
			var east := revealed(mask, width, cx, cy) if cx < width else false
			if west == east:
				continue
			var a := start + step_x * cx + step_y * cy
			_quad(vertices, normals, indices, a + bottom, a + step_y + bottom,
				a + step_y + top, a + top, (-step_x if west else step_x).normalized())
	for cy: int in range(height + 1):
		for cx: int in range(width):
			var near := revealed(mask, width, cx, cy - 1) if cy > 0 else false
			var far := revealed(mask, width, cx, cy) if cy < height else false
			if near == far:
				continue
			var a := start + step_x * cx + step_y * cy
			_quad(vertices, normals, indices, a + bottom, a + step_x + bottom,
				a + step_x + top, a + top, (-step_y if near else step_y).normalized())
	if indices.is_empty():
		return null
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


## Black, unshaded and two-sided: the same on Forward+ and Compatibility, with
## no depth tricks, and untouched by the environment's distance fog, which
## would grey the far edge of the black.
static func material() -> StandardMaterial3D:
	var black := StandardMaterial3D.new()
	black.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	black.albedo_color = Color.BLACK
	black.cull_mode = BaseMaterial3D.CULL_DISABLED
	black.disable_fog = true
	return black


static func _quad(vertices: PackedVector3Array, normals: PackedVector3Array,
		indices: PackedInt32Array, a: Vector3, b: Vector3, c: Vector3, d: Vector3,
		normal: Vector3) -> void:
	var base := vertices.size()
	vertices.append_array(PackedVector3Array([a, b, c, d]))
	normals.append_array(PackedVector3Array([normal, normal, normal, normal]))
	indices.append_array(PackedInt32Array([base, base + 1, base + 2, base, base + 2, base + 3]))

extends RefCounted
## Builds one procedural descent floor at runtime from the server's layout
## (descent_layout_v1: server message 188, `kind` "layout"; the server's
## eloria/descent.py `DescentFloor.client_layout` and Descent-Runs.md).
##
## The owner asked for truly procedural dungeons on 2026-11-13: every run of a
## procedural descent has floors nobody has seen before, so nothing about them
## can be baked. The server sends each floor's 2 m cell grid (rock, room,
## corridor, doorway, pillar, chasm), its stairs and the kit pieces its
## generator dressed it with; this draws it the way the baked Serpent floors
## were drawn (build_underground.py, which baked The Serpent Deep's pool until
## then): only the shell is made here - a flagstone floor, a low rock face round
## every wall, stair wells and flights - and everything standing on it is a
## reviewed Meshy kit piece (data/world/descent-themes.json).
##
## The floor matches the server's walk grid cell for cell: the walk floor
## (`Walk_<section>_floor`, with its layer 8 collider like any map's Walk_
## mesh) covers the open and pillar cells and reaches MARGIN metres into the
## rock round them, under the faces; a stair's well or flight fills the cell in
## front of it, which the server closes (`DescentFloor.walk_heights`).
##
## Names follow the baked floors', so the map's machinery treats a built floor
## as it treated a baked one: `Build_<section>_<facing>` rock faces and
## `Build_<section>_mouth<k>` stair mouths are cutaway walls by facing,
## kit pieces set into the faces carry `cutaway_outward`, lamps are light
## markers, and every node sorts into its section by name or position.
##
## Everything here is a pure function of the layout, the theme table and the
## map's CoordinateAdapter (tests/test_descent_floors.gd).

const ROCK := 0
const ROOM := 1
const HALL := 2
const DOOR := 3
const PILLAR := 4
const CHASM := 5
## Half-metre sub-cells: a 2 m cell is SUB x SUB of them.
const SUB_METRES := 0.5
## The walk floor reaches this far into the rock beside open cells, so actors
## on an edge tile stand clear of the faces and the kit pieces set into them.
const MARGIN := 0.5
const WALL_FOOT := -0.15
const FLOOR_UV := 0.22
const WALL_UV := 0.3
## A stair's well or flight: its opening in the face, metres.
const MOUTH_WIDTH := 2.4
const DOWN_TOP := 2.6
const UP_TOP := 3.2
const WELL_BOTTOM := -1.6
const DOWN_STEPS := 4
const UP_STEPS := 5
const UP_RISE := 0.27
const CHASM_DEPTH := 4.0
## Cutaway outward per facing (build_underground.FACE_OUT): a facing names the
## side of the floor its rock is on, in server terms (south is +y).
const FACE_OUT := {"east": Vector3(1, 0, 0), "west": Vector3(-1, 0, 0),
	"south": Vector3(0, 0, -1), "north": Vector3(0, 0, 1)}
const DescentFog := preload("res://src/world/descent_fog.gd")


## The theme table (data/world/descent-themes.json), parsed.
static func load_themes(path := "res://data/world/descent-themes.json") -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary else {}


## Every kit model a floor of these themes may stand, as GlbSceneCache paths.
static func asset_paths(themes: Dictionary) -> PackedStringArray:
	var paths := PackedStringArray()
	var assets: Dictionary = themes.get("assets", {}) as Dictionary
	for name: Variant in assets:
		var path := str(assets[name])
		if not paths.has(path):
			paths.append(path)
	return paths


static func facing_name(nx: float, ny: float) -> String:
	return _Floor.facing_of(nx, ny)


## A shell texture, loaded once a session, with mipmaps even where a fresh
## checkout imported the PNG as a 2D image (as LookGround's class textures).
static func shell_texture(path: String) -> Texture2D:
	return _Floor.shell(path)


## Builds the floor of `layout` (a decoded layout: `cells` a PackedByteArray of
## width * height cell codes) and returns {root: Node3D named
## `Section_<section>_floor`, walls: cutaway wall entries, markers: light
## markers, picture: Image, extent: Rect2, pieces: kit models stood}. `models`
## false leaves the kit pieces out (tests that need only the shell).
static func build(layout: Dictionary, themes: Dictionary, adapter: CoordinateAdapter, models := true) -> Dictionary:
	var drawing := _Floor.new(layout, themes, adapter)
	return drawing.build(models)


class _Floor:
	var layout: Dictionary
	var themes: Dictionary
	var theme: Dictionary
	var adapter: CoordinateAdapter
	var section: String
	var origin: Vector2i
	var width: int
	var height: int
	var cell_tiles: int
	var cells: PackedByteArray
	var sub: int            # sub-cells per cell
	var sw: int             # sub-cell grid size
	var sh: int
	var kind: PackedByteArray    # per sub-cell: the cell code
	var space: PackedByteArray   # 1 where the floor or a stair's well stands (no rock face across it)
	var well: PackedByteArray    # 1 where a stair's well or flight stands (no walk floor)
	var walkable: PackedByteArray  # 1 where the walk floor stands: space but not a well
	var chasm: PackedByteArray   # 1 in a chasm cell
	var well_rects: Array[Rect2i] = []   # sub-cells
	var floor_rects: Array[Rect2i] = []  # sub-cells, the walk floor's quads
	var stairs: Array[Dictionary] = []
	var root: Node3D
	var walls: Array[Dictionary] = []
	var markers: Array[Dictionary] = []
	var pieces := 0
	var rng := RandomNumberGenerator.new()

	func _init(source: Dictionary, theme_table: Dictionary, map_adapter: CoordinateAdapter) -> void:
		layout = source
		themes = theme_table
		adapter = map_adapter
		section = str(layout.get("section", ""))
		var raw_origin: Array = layout.get("origin", [0, 0]) as Array
		origin = Vector2i(int(raw_origin[0]), int(raw_origin[1]))
		width = int(layout.get("width", 0))
		height = int(layout.get("height", 0))
		cell_tiles = int(layout.get("cell_tiles", 2))
		cells = layout.get("cells", PackedByteArray()) as PackedByteArray
		var table: Dictionary = themes.get("themes", {}) as Dictionary
		theme = table.get(str(layout.get("theme", "")), table.get("catacomb", {})) as Dictionary
		sub = int(round(cell_tiles / SUB_METRES))
		sw = width * sub
		sh = height * sub
		rng.seed = int(layout.get("dressing_seed", 0))

	# -- coordinates ------------------------------------------------------

	## A point on the floor in floor tiles (corner based, fractional) at
	## height `h`, in the map's frame.
	func at(tx: float, ty: float, h: float) -> Vector3:
		return adapter.server_to_godot(float(origin.x) + tx, float(origin.y) + ty, h)

	func cell(cx: int, cy: int) -> int:
		if cx < 0 or cy < 0 or cx >= width or cy >= height:
			return ROCK
		return cells[cy * width + cx]

	# -- the grids --------------------------------------------------------

	func classify() -> void:
		# Every grid repeats each cell's code over its sub x sub sub-cells:
		# built a cell row at a time, each row repeated `sub` times.
		kind = PackedByteArray()
		chasm = PackedByteArray()
		for cy: int in range(height):
			var row := PackedByteArray()
			row.resize(sw)
			var gap := PackedByteArray()
			gap.resize(sw)
			for cx: int in range(width):
				var code := cells[cy * width + cx]
				if code == ROCK:
					continue
				for n: int in range(sub):
					row[cx * sub + n] = code
					if code == CHASM:
						gap[cx * sub + n] = 1
			for n: int in range(sub):
				kind.append_array(row)
				chasm.append_array(gap)
		space = PackedByteArray()
		space.resize(sw * sh)
		well = PackedByteArray()
		well.resize(sw * sh)
		# The stairs: each stands one cell in from a wall, facing it; the cell
		# between it and the wall is its well (down) or flight (up).
		for value: Variant in layout.get("stairs", []) as Array:
			var stair: Dictionary = value as Dictionary
			var facing: Array = stair.get("facing", [0, 0]) as Array
			var f := Vector2i(int(facing[0]), int(facing[1]))
			if f == Vector2i.ZERO:
				continue
			var tile := Vector2i(int(stair.get("x", 0)), int(stair.get("y", 0)))
			var here := Vector2i(tile.x / cell_tiles, tile.y / cell_tiles)
			stairs.append({"way": str(stair.get("way", "down")), "facing": f, "cell": here, "well": here + f})
		# The open ground and the wells, then MARGIN round them into the rock
		# (cell by cell: the ring of sub-cells round each such cell).
		var reach := int(round(MARGIN / SUB_METRES))
		var held: Array[Vector2i] = []
		for cy: int in range(height):
			for cx: int in range(width):
				var code := cells[cy * width + cx]
				if code == ROOM or code == HALL or code == DOOR or code == PILLAR:
					held.append(Vector2i(cx, cy))
		for stair: Dictionary in stairs:
			held.append(stair.well)
		for c: Vector2i in held:
			for j: int in range(c.y * sub, (c.y + 1) * sub):
				for i: int in range(c.x * sub, (c.x + 1) * sub):
					if i >= 0 and j >= 0 and i < sw and j < sh:
						space[j * sw + i] = 1
		var grown := space.duplicate()
		for c: Vector2i in held:
			for j: int in range(c.y * sub - reach, (c.y + 1) * sub + reach):
				for i: int in range(c.x * sub - reach, (c.x + 1) * sub + reach):
					if i >= 0 and j >= 0 and i < sw and j < sh and kind[j * sw + i] == ROCK:
						grown[j * sw + i] = 1
		space = grown
		# A well reaches from its stair's cell to the face beyond it: the
		# well's cell and the margin strip behind it, the well's width wide.
		for stair: Dictionary in stairs:
			var w: Vector2i = stair.well
			var f: Vector2i = stair.facing
			var lo := Vector2i(w.x * sub, w.y * sub)
			var hi := Vector2i((w.x + 1) * sub, (w.y + 1) * sub)
			if f.x > 0: hi.x += reach
			if f.x < 0: lo.x -= reach
			if f.y > 0: hi.y += reach
			if f.y < 0: lo.y -= reach
			var zone := Rect2i(lo, hi - lo).intersection(Rect2i(0, 0, sw, sh))
			well_rects.append(zone)
			for j: int in range(zone.position.y, zone.end.y):
				for i: int in range(zone.position.x, zone.end.x):
					well[j * sw + i] = 1
					space[j * sw + i] = 1
		walkable = space.duplicate()
		for zone: Rect2i in well_rects:
			for j: int in range(zone.position.y, zone.end.y):
				for i: int in range(zone.position.x, zone.end.x):
					walkable[j * sw + i] = 0

	## Row `j` of a sub-cell grid; outside the grid, a row of rock.
	func row_of(grid: PackedByteArray, j: int) -> PackedByteArray:
		if j < 0 or j >= sh:
			var empty := PackedByteArray()
			empty.resize(sw)
			return empty
		return grid.slice(j * sw, (j + 1) * sw)

	## The runs of 1 in a row, as [start, end) sub-cell spans.
	func spans(row: PackedByteArray) -> Array[Vector2i]:
		var out: Array[Vector2i] = []
		var start := -1
		for i: int in range(sw):
			if row[i] == 1:
				if start < 0:
					start = i
			elif start >= 0:
				out.append(Vector2i(start, i))
				start = -1
		if start >= 0:
			out.append(Vector2i(start, sw))
		return out

	# -- materials --------------------------------------------------------

	static func facing_of(nx: float, ny: float) -> String:
		if absf(nx) > absf(ny):
			return "east" if nx > 0.0 else "west"
		return "south" if ny > 0.0 else "north"

	static var _textures: Dictionary = {}

	static func shell(path: String) -> Texture2D:
		if path.is_empty() or not ResourceLoader.exists(path):
			return null
		var known: Variant = _textures.get(path)
		if known is Texture2D:
			return known
		var source := load(path) as Texture2D
		var built: Texture2D = source
		if source != null:
			var image := source.get_image()
			if image != null and not image.has_mipmaps() and (not image.is_compressed() or image.decompress() == OK):
				image.generate_mipmaps()
				built = ImageTexture.create_from_image(image)
		_textures[path] = built
		return built

	func texture(key: String) -> Texture2D:
		return shell(str((themes.get("textures", {}) as Dictionary).get(key, "")))

	func colour(value: Variant, fallback: Color) -> Color:
		if value is Array and (value as Array).size() >= 3:
			return Color(float(value[0]), float(value[1]), float(value[2]))
		return fallback

	func floor_material() -> StandardMaterial3D:
		var material := StandardMaterial3D.new()
		material.resource_name = "descent_flagstone"
		var style: Dictionary = theme.get("floor", {}) as Dictionary
		material.albedo_texture = LookGround.class_texture(str(style.get("texture", "flagstone")))
		material.albedo_color = colour(style.get("tint"), Color(.65, .65, .65))
		material.roughness = 1.0
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		return material

	func rock_material() -> StandardMaterial3D:
		var material := StandardMaterial3D.new()
		material.resource_name = "descent_rock_stone"
		material.albedo_texture = texture("rock")
		# The face sits behind its kit pieces: lifted toward their colour so it
		# reads as the same stone in shadow (the baked floors' rockLift).
		material.albedo_color = colour(theme.get("rockLift"), Color.WHITE)
		material.roughness = 0.92
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		return material

	func tread_material() -> StandardMaterial3D:
		var material := StandardMaterial3D.new()
		material.resource_name = "descent_tread_stone"
		material.albedo_texture = texture("tread")
		material.roughness = 0.9
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		return material

	func dark_material() -> StandardMaterial3D:
		var material := StandardMaterial3D.new()
		material.resource_name = "descent_way_on_dark"
		material.albedo_color = Color(0.008, 0.009, 0.011)
		material.roughness = 0.85
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		return material

	# -- geometry helpers -------------------------------------------------

	## A quad whose front faces `normal` (Godot's front faces wind clockwise).
	static func quad(st: SurfaceTool, corners: Array, normal: Vector3, uvs: Array) -> void:
		var a: Vector3 = corners[0]
		var b: Vector3 = corners[1]
		var c: Vector3 = corners[2]
		var order := [0, 1, 2, 0, 2, 3]
		if (b - a).cross(c - a).dot(normal) > 0.0:
			order = [0, 2, 1, 0, 3, 2]
		for index: int in order:
			st.set_normal(normal)
			st.set_uv(uvs[index])
			st.add_vertex(corners[index])

	## The ragged top of a rock face at a point of the map (continuous along
	## every face, so faces meeting at a corner meet at the same height).
	func top_at(point: Vector3) -> float:
		var base := float(theme.get("wallHeight", 3.6))
		return base + 0.45 * sin(0.61 * point.x + 0.37 * point.z) + 0.22 * sin(1.73 * point.z - 1.1 * point.x)

	# -- the walk floor ---------------------------------------------------

	## The walk floor as rectangles of sub-cells: a row's spans carry on down
	## every row that repeats it (rooms are rectangles, so a floor is a few
	## hundred of them).
	func rectangles() -> Array[Rect2i]:
		var out: Array[Rect2i] = []
		var open: Dictionary = {}           # span -> the row it began on
		var previous := PackedByteArray()
		for j: int in range(sh + 1):
			var row := row_of(walkable, j)
			if j > 0 and j < sh and row == previous:
				continue
			var now: Array[Vector2i] = []
			if j < sh:
				now = spans(row)
			for span: Vector2i in open.keys():
				if not now.has(span):
					out.append(Rect2i(span.x, int(open[span]), span.y - span.x, j - int(open[span])))
					open.erase(span)
			for span: Vector2i in now:
				if not open.has(span):
					open[span] = j
			previous = row
		return out

	func walk_floor(material: Material) -> MeshInstance3D:
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		floor_rects = rectangles()
		for rect: Rect2i in floor_rects:
			var x0 := rect.position.x * SUB_METRES
			var x1 := rect.end.x * SUB_METRES
			var y0 := rect.position.y * SUB_METRES
			var y1 := rect.end.y * SUB_METRES
			var corners := [at(x0, y0, 0.0), at(x1, y0, 0.0), at(x1, y1, 0.0), at(x0, y1, 0.0)]
			var uvs := []
			for corner: Vector3 in corners:
				uvs.append(Vector2(corner.x, corner.z) * FLOOR_UV)
			quad(st, corners, Vector3.UP, uvs)
		var count := floor_rects.size()
		var mesh := MeshInstance3D.new()
		mesh.name = "Walk_%s_floor" % section
		if count > 0:
			st.generate_tangents()
			mesh.mesh = st.commit()
			mesh.mesh.surface_set_material(0, material)
		# The walk surface every height ray reads (WorldLoader's Walk_ meshes').
		var body := StaticBody3D.new()
		body.name = mesh.name + "_WalkSurfaceCollision"
		body.collision_layer = 8
		body.collision_mask = 0
		var shape := CollisionShape3D.new()
		if mesh.mesh != null:
			shape.shape = mesh.mesh.create_trimesh_shape()
		body.add_child(shape)
		mesh.add_child(body)
		return mesh

	# -- the rock faces ---------------------------------------------------

	## Every edge between the floor (or a well) and the rock or a chasm, merged
	## into runs: {facing, chasm, a (tiles), b (tiles), into (tile unit, from
	## the floor into the rock)}.
	func runs() -> Array[Dictionary]:
		var found: Array[Dictionary] = []
		# Edges between rows j - 1 and j (lines of constant y): only where the
		# two rows differ.
		var above := row_of(space, -1)
		for j: int in range(0, sh + 1):
			var below := row_of(space, j)
			if above != below:
				var gap_above := row_of(chasm, j - 1)
				var gap_below := row_of(chasm, j)
				var open_run: Dictionary = {}
				for i: int in range(0, sw + 1):
					var edge := {}
					if i < sw and above[i] != below[i]:
						var floor_above := above[i] == 1
						var is_chasm := (gap_below[i] if floor_above else gap_above[i]) == 1
						edge = {"facing": "south" if floor_above else "north", "chasm": is_chasm,
							"into": Vector2(0, 1) if floor_above else Vector2(0, -1)}
					if not open_run.is_empty() and (edge.is_empty() or edge.facing != open_run.facing
							or edge.chasm != open_run.chasm):
						open_run.b = Vector2(i * SUB_METRES, j * SUB_METRES)
						found.append(open_run)
						open_run = {}
					if not edge.is_empty() and open_run.is_empty():
						open_run = {"facing": edge.facing, "chasm": edge.chasm, "into": edge.into,
							"a": Vector2(i * SUB_METRES, j * SUB_METRES)}
			above = below
		# Edges between columns i - 1 and i (lines of constant x): a row's
		# crossings carry on down every row that repeats it.
		var open: Dictionary = {}               # Vector3i(i, floor on the left, chasm) -> first row
		var previous := PackedByteArray()
		var previous_gap := PackedByteArray()
		for j: int in range(0, sh + 1):
			var row := row_of(space, j)
			var gap := row_of(chasm, j)
			if j > 0 and j < sh and row == previous and gap == previous_gap:
				continue
			var crossings: Dictionary = {}
			if j < sh:
				var left := 0
				for i: int in range(0, sw + 1):
					var right := row[i] if i < sw else 0
					if left != right:
						var other := i if left == 1 else i - 1
						var is_chasm := other >= 0 and other < sw and gap[other] == 1
						crossings[Vector3i(i, left, 1 if is_chasm else 0)] = true
					left = right
			for key: Vector3i in open.keys():
				if not crossings.has(key):
					var start := int(open[key])
					found.append({"facing": "east" if key.y == 1 else "west", "chasm": key.z == 1,
						"into": Vector2(1, 0) if key.y == 1 else Vector2(-1, 0),
						"a": Vector2(key.x * SUB_METRES, start * SUB_METRES),
						"b": Vector2(key.x * SUB_METRES, j * SUB_METRES)})
					open.erase(key)
			for key: Vector3i in crossings:
				if not open.has(key):
					open[key] = j
			previous = row
			previous_gap = gap
		return found

	func faces(found: Array[Dictionary], material: Material) -> void:
		var tools: Dictionary = {}
		for run: Dictionary in found:
			var name: String = "Build_%s_%s" % [section, run.facing] if not run.chasm \
				else "Build_%s_chasm" % section
			if not tools.has(name):
				var st := SurfaceTool.new()
				st.begin(Mesh.PRIMITIVE_TRIANGLES)
				tools[name] = st
			var a: Vector2 = run.a
			var b: Vector2 = run.b
			var into: Vector2 = run.into
			var normal_tiles := -into                 # the face looks back into the floor
			var normal := (at(normal_tiles.x, normal_tiles.y, 0.0) - at(0.0, 0.0, 0.0)).normalized()
			var length := a.distance_to(b)
			var steps := maxi(1, int(ceil(length / 1.0)))
			for s: int in range(steps):
				var p := a.lerp(b, float(s) / steps)
				var q := a.lerp(b, float(s + 1) / steps)
				var foot_p := at(p.x, p.y, 0.0)
				var foot_q := at(q.x, q.y, 0.0)
				var top_p: float
				var top_q: float
				var low: float
				if run.chasm:
					# A drop to nowhere: the chasm's side under the floor's edge,
					# looking into the chasm.
					top_p = 0.0
					top_q = 0.0
					low = -CHASM_DEPTH
					normal = -normal
				else:
					top_p = top_at(foot_p)
					top_q = top_at(foot_q)
					low = WALL_FOOT
				var along_p := (p.x if absf(b.x - a.x) > 0.0 else p.y) * WALL_UV
				var along_q := (q.x if absf(b.x - a.x) > 0.0 else q.y) * WALL_UV
				var corners := [at(p.x, p.y, low), at(q.x, q.y, low), at(q.x, q.y, top_q), at(p.x, p.y, top_p)]
				var uvs := [Vector2(along_p, low * WALL_UV), Vector2(along_q, low * WALL_UV),
					Vector2(along_q, top_q * WALL_UV), Vector2(along_p, top_p * WALL_UV)]
				quad(tools[name] as SurfaceTool, corners, normal, uvs)
				if run.chasm:
					normal = -normal
		for name: String in tools:
			var st: SurfaceTool = tools[name]
			st.generate_tangents()
			var mesh := MeshInstance3D.new()
			mesh.name = name
			mesh.mesh = st.commit()
			mesh.mesh.surface_set_material(0, material)
			root.add_child(mesh)
			var facing := name.get_slice("_", name.get_slice_count("_") - 1)
			if FACE_OUT.has(facing):
				var out: Vector3 = FACE_OUT[facing]
				walls.append({"node": name, "outward": [out.x, 0, out.z], "section": section})

	# -- the stairs -------------------------------------------------------

	func stair_mouths(rock: Material, tread: Material, dark: Material) -> void:
		var index := 0
		for stair: Dictionary in stairs:
			var f: Vector2i = stair.facing
			var w: Vector2i = stair.well
			var u := Vector2(f)
			var v := Vector2(-f.y, f.x)
			# The well's near edge (where the stair's cell ends), centred on it.
			var centre := (Vector2(w) + Vector2(0.5, 0.5)) * cell_tiles
			var near := centre - u * (cell_tiles * 0.5)
			var length := float(cell_tiles) + MARGIN          # near edge to the face
			var half := cell_tiles * 0.5
			var p := func(t: float, s: float, h: float) -> Vector3:
				var spot := near + u * t + v * s
				return at(spot.x, spot.y, h)
			var room := (at(-u.x, -u.y, 0.0) - at(0.0, 0.0, 0.0)).normalized()   # back into the room
			var side := (at(v.x, v.y, 0.0) - at(0.0, 0.0, 0.0)).normalized()
			var rock_st := SurfaceTool.new()
			rock_st.begin(Mesh.PRIMITIVE_TRIANGLES)
			var tread_st := SurfaceTool.new()
			tread_st.begin(Mesh.PRIMITIVE_TRIANGLES)
			var dark_st := SurfaceTool.new()
			dark_st.begin(Mesh.PRIMITIVE_TRIANGLES)
			var flat := func(st: SurfaceTool, t0: float, t1: float, s0: float, s1: float, h: float) -> void:
				quad(st, [p.call(t0, s0, h), p.call(t1, s0, h), p.call(t1, s1, h), p.call(t0, s1, h)], Vector3.UP,
					[Vector2(t0, s0) * WALL_UV, Vector2(t1, s0) * WALL_UV, Vector2(t1, s1) * WALL_UV, Vector2(t0, s1) * WALL_UV])
			var across := func(st: SurfaceTool, t: float, s0: float, s1: float, h0: float, h1: float, normal: Vector3) -> void:
				quad(st, [p.call(t, s0, h0), p.call(t, s1, h0), p.call(t, s1, h1), p.call(t, s0, h1)], normal,
					[Vector2(s0, h0) * WALL_UV, Vector2(s1, h0) * WALL_UV, Vector2(s1, h1) * WALL_UV, Vector2(s0, h1) * WALL_UV])
			var along := func(st: SurfaceTool, s: float, t0: float, t1: float, h0: float, h1: float, normal: Vector3) -> void:
				quad(st, [p.call(t0, s, h0), p.call(t1, s, h0), p.call(t1, s, h1), p.call(t0, s, h1)], normal,
					[Vector2(t0, h0) * WALL_UV, Vector2(t1, h0) * WALL_UV, Vector2(t1, h1) * WALL_UV, Vector2(t0, h1) * WALL_UV])
			var down: bool = str(stair.way) != "up"
			var top := DOWN_TOP if down else UP_TOP
			if down:
				# Treads down the well from its lip to under the face; the lower
				# ones go down into the dark the way on leads into.
				var run := (length + 0.4) / DOWN_STEPS
				var rise := -WELL_BOTTOM / (DOWN_STEPS + 0.5)
				for s: int in range(DOWN_STEPS):
					var st: SurfaceTool = tread_st if s < 2 else dark_st
					var t0 := s * run
					var t1 := minf(length, (s + 1) * run)
					flat.call(st, t0, t1, -half, half, -(s + 1) * rise)
					across.call(st, t0, -half, half, -(s + 1) * rise, -s * rise, room)
				# The well's sides, from the floor's edge down to its bottom.
				for sign: float in [-1.0, 1.0]:
					along.call(rock_st, sign * half, 0.0, length + 0.3, WELL_BOTTOM, 0.0, side * -sign)
			else:
				# Stone steps rising from the floor into the rock.
				var run := (length - 0.12) / UP_STEPS
				for s: int in range(UP_STEPS):
					var t0 := s * run
					var t1 := (s + 1) * run
					var low := s * UP_RISE
					var high := (s + 1) * UP_RISE
					flat.call(tread_st, t0, t1, -half, half, high)
					across.call(tread_st, t0, -half, half, low, high, room)
					for sign: float in [-1.0, 1.0]:
						along.call(rock_st, sign * half, t0, length, -0.05, high, side * sign)
			# The dark way on, a hand's breadth in front of the face, and the
			# rock jambs and lintel standing proud of it.
			var face := length - 0.12
			var mouth := MOUTH_WIDTH * 0.5
			across.call(dark_st, face, -mouth, mouth, WELL_BOTTOM if down else 0.0, top, room)
			var jamb := 0.45
			var block := func(t0: float, t1: float, s0: float, s1: float, h0: float, h1: float) -> void:
				flat.call(rock_st, t0, t1, s0, s1, h1)
				across.call(rock_st, t0, s0, s1, h0, h1, room)
				along.call(rock_st, s1, t0, t1, h0, h1, side)
				along.call(rock_st, s0, t0, t1, h0, h1, -side)
			for sign: float in [-1.0, 1.0]:
				var s0 := minf(sign * mouth, sign * (mouth + jamb))
				var s1 := maxf(sign * mouth, sign * (mouth + jamb))
				block.call(face - 0.5, face + 0.4, s0, s1, WALL_FOOT, top + 0.1)
			block.call(face - 0.5, face + 0.4, -(mouth + jamb), mouth + jamb, top, top + 0.55)
			var mesh := MeshInstance3D.new()
			mesh.name = "Build_%s_mouth%d" % [section, index]
			var array_mesh := ArrayMesh.new()
			for pair: Array in [[rock_st, rock], [tread_st, tread], [dark_st, dark]]:
				var st: SurfaceTool = pair[0]
				st.generate_tangents()
				st.commit(array_mesh)
				array_mesh.surface_set_material(array_mesh.get_surface_count() - 1, pair[1])
			mesh.mesh = array_mesh
			root.add_child(mesh)
			var out: Vector3 = FACE_OUT[facing_of(f.x, f.y)]
			walls.append({"node": mesh.name, "outward": [out.x, 0, out.z], "section": section})
			stair["face"] = near + u * length
			index += 1

	# -- kit pieces -------------------------------------------------------

	func place(asset: String, spot: Vector3, yaw: float, scale: float) -> Node3D:
		var path := str((themes.get("assets", {}) as Dictionary).get(asset, ""))
		if path.is_empty():
			return null
		var model := GlbSceneCache.instantiate(path)
		if model == null:
			push_warning("Descent floor: kit piece failed to load: " + path)
			return null
		model.name = "%s_%d" % [asset, pieces]
		model.position = spot
		model.rotation.y = deg_to_rad(yaw)
		model.scale *= scale
		root.add_child(model)
		pieces += 1
		return model

	func lamp(asset: String, spot: Vector3, scale: float) -> void:
		var light: Variant = (themes.get("lamps", {}) as Dictionary).get(asset)
		if not light is Dictionary:
			return
		var row: Dictionary = light
		var colour: Array = (theme.get("lampColour", row.get("color", [1, 1, 1])) as Array)
		markers.append({"id": "%s-lamp-%d" % [section, markers.size()],
			"position": [spot.x, float(row.get("height", 1.3)) * scale, spot.z],
			"color": colour, "energyHint": float(row.get("energy", 1.0)),
			"rangeHint": float(row.get("range", 8.0))})

	## The kit pieces the server's generator stood on the floor (lamps, wall
	## pieces, clutter) and a pillar in every pillar cell.
	func dressing(models: bool) -> void:
		for value: Variant in layout.get("props", []) as Array:
			var prop: Dictionary = value as Dictionary
			var spot := at(float(prop.get("x", 0.0)), float(prop.get("y", 0.0)), 0.0)
			lamp(str(prop.get("asset", "")), spot, 1.0)
			if models:
				place(str(prop.get("asset", "")), spot, float(prop.get("yaw", 0.0)), 1.0)
		if not models:
			return
		var pillar := str(theme.get("pillar", ""))
		for cy: int in range(height):
			for cx: int in range(width):
				if cell(cx, cy) == PILLAR:
					place(pillar, at((cx + 0.5) * cell_tiles, (cy + 0.5) * cell_tiles, 0.0), 0.0, 1.0)

	## Kit pieces set into the rock faces every `spacing` metres, a third of
	## each standing proud (build_underground.dressing's wall rocks), clear of
	## the stair mouths. Each carries its face's outward for the cutaway.
	func wall_pieces(found: Array[Dictionary]) -> void:
		var rocks: Array = theme.get("wallRocks", []) as Array
		if rocks.is_empty():
			return
		var spacing := float(theme.get("spacing", 3.0))
		var counter := 0
		for run: Dictionary in found:
			if run.chasm:
				continue
			var a: Vector2 = run.a
			var b: Vector2 = run.b
			var into: Vector2 = run.into
			var length := a.distance_to(b)
			if length < 1.6:
				continue
			var direction := (b - a) / length
			# Travel so the room lies on the piece's +Z side: an aligned piece's
			# +X runs along the face and its front looks into the room.
			if Vector2(direction.y, -direction.x).dot(-into) < 0.0:
				direction = -direction
			var count := int(floor((length - 1.2) / spacing)) + 1
			var spare := (length - 1.2) - (count - 1) * spacing
			for n: int in range(count):
				var rock: Dictionary = rocks[(counter * 5 + counter / 3) % rocks.size()] as Dictionary
				var scale := 0.85 + float(counter * 37 % 30) / 100.0
				counter += 1
				var proud := float(rock.get("proud", 1.0))
				var d := 0.6 + spare * 0.5 + n * spacing + rng.randf_range(-0.3, 0.3)
				var point := a.lerp(b, clampf(d / length, 0.0, 1.0)) + into * (proud * scale * 0.45)
				var blocked := false
				for stair: Dictionary in stairs:
					if stair.has("face") and point.distance_to(stair.face) < MOUTH_WIDTH * 0.5 + 0.6 + proud * scale:
						blocked = true
				if blocked:
					continue
				var yaw: float
				if bool(rock.get("align", false)):
					var g := at(direction.x, direction.y, 0.0) - at(0.0, 0.0, 0.0)
					yaw = rad_to_deg(atan2(-g.z, g.x))
				else:
					yaw = float(counter * 137 % 360)
				var model := place(str(rock.get("asset", "")), at(point.x, point.y, -0.3), yaw, scale)
				if model != null:
					var out := (at(into.x, into.y, 0.0) - at(0.0, 0.0, 0.0)).normalized()
					model.set_meta("cutaway_outward", Vector3(out.x, 0.0, out.z))

	# -- the map picture --------------------------------------------------

	## The floor as the minimap and full map draw it, laid out as DescentFog's
	## picture (image x along Godot +X, image y along +Z over `extent`).
	func picture(found: Array[Dictionary]) -> Image:
		var colours: Dictionary = theme.get("minimap", {}) as Dictionary
		var floor_colour := colour(_rgb(colours.get("floor")), Color8(84, 78, 60))
		var edge_colour := colour(_rgb(colours.get("edge")), Color8(170, 160, 120))
		var rock_colour := colour(_rgb(colours.get("rock")), Color8(16, 15, 13))
		var well_colour := colour(_rgb(colours.get("well")), Color8(8, 8, 9))
		var step_x := at(1.0, 0.0, 0.0) - at(0.0, 0.0, 0.0)
		var step_y := at(0.0, 1.0, 0.0) - at(0.0, 0.0, 0.0)
		var flip_x := step_x.x < 0.0
		var flip_y := step_y.z < 0.0
		# One pixel a sub-cell (two a metre).
		var image := Image.create(sw, sh, false, Image.FORMAT_RGBA8)
		image.fill(rock_colour)
		var paint := func(rect: Rect2i, shade: Color) -> void:
			var x := sw - rect.end.x if flip_x else rect.position.x
			var y := sh - rect.end.y if flip_y else rect.position.y
			image.fill_rect(Rect2i(x, y, rect.size.x, rect.size.y), shade)
		for rect: Rect2i in floor_rects:
			paint.call(rect, floor_colour)
		for rect: Rect2i in well_rects:
			paint.call(rect, well_colour)
		for cy: int in range(height):
			for cx: int in range(width):
				var code := cells[cy * width + cx]
				if code == CHASM:
					paint.call(Rect2i(cx * sub, cy * sub, sub, sub), Color.BLACK)
				elif code == PILLAR:
					paint.call(Rect2i(cx * sub, cy * sub, sub, sub), edge_colour)
		# The walls: a line of sub-cells along every run, on the floor's side.
		for run: Dictionary in found:
			var a := Vector2i((run.a as Vector2) / SUB_METRES)
			var b := Vector2i((run.b as Vector2) / SUB_METRES)
			var into: Vector2 = run.into
			var line: Rect2i
			if a.y == b.y:
				line = Rect2i(mini(a.x, b.x), a.y - 1 if into.y > 0.0 else a.y, absi(b.x - a.x), 1)
			else:
				line = Rect2i(a.x - 1 if into.x > 0.0 else a.x, mini(a.y, b.y), 1, absi(b.y - a.y))
			paint.call(line.intersection(Rect2i(0, 0, sw, sh)), edge_colour)
		return image

	static func _rgb(value: Variant) -> Variant:
		if value is Array and (value as Array).size() >= 3:
			return [float(value[0]) / 255.0, float(value[1]) / 255.0, float(value[2]) / 255.0]
		return null

	# -- all of it --------------------------------------------------------

	func build(models: bool) -> Dictionary:
		if width <= 0 or height <= 0 or cells.size() != width * height:
			return {}
		classify()
		root = Node3D.new()
		root.name = "Section_%s_floor" % section
		root.set_meta("descent_section", section)
		var floor_mat := floor_material()
		var rock := rock_material()
		root.add_child(walk_floor(floor_mat))
		var found := runs()
		faces(found, rock)
		stair_mouths(rock, tread_material(), dark_material())
		dressing(models)
		if models:
			wall_pieces(found)
		var grid := {"origin": origin, "cell_tiles": cell_tiles, "width": width, "height": height}
		return {"root": root, "walls": walls, "markers": markers, "picture": picture(found),
			"extent": DescentFog.extent(grid, adapter), "pieces": pieces, "section": section}

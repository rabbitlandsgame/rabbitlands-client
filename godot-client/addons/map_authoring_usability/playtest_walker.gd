@tool
extends RefCounted
## Play-test walking inside the editor: a stand-in character that walks the
## open territory the way the server moves a player.
##
## The server walks one-metre logical tiles whose grid its sync tool folds from
## the published package's collision.bin (eloria-server tools/collision_sources
## and sync_authored_collision): a tile is blocked when any of its four
## half-metre cells is, otherwise it takes the highest of them; heights become
## 0.2 m units above the lowest walkable tile and are then coarsened to the
## map's stage: the smallest multiple of 0.2 m that fits the relief into 63
## codes, or on a map with under 12.4 m of relief the smallest of 0.2-0.8 m
## whose largest reachable area is within 1% of the best (choose_stage). The
## walker repeats that fold; on 2026-09-26 it reproduced the server's
## tools/collision/<id>.escg.gz byte for byte for all twelve territories.
##
## A continent-v2 territory publishes its served grid instead
## (collision.servedGrid in its client package's world.json, the catalog
## entry's publishedManifestPath; served-grid.escg.gz beside it): one
## 16-bit code per tile, 50 mm a code above the continent datum, with the climb
## in its own header (1.0 m, 20 codes). The walker loads that file as the
## server vendors it (served_grid.gd, SHA-256 checked against the manifest)
## rather than folding, and walks it with the header's climb and a tile
## walkable whenever its code is not 0. Version 1 grids keep the byte rule
## below: walkable when code & 0x3F is not 0, a climb of 2 codes.
##
## Routes use the server's search (World.find_path): neighbours tried N, NE, E,
## SE, S, SW, W, NW; a step needs both tiles walkable and a code change of at
## most the map's climb (max_walk_height_change, 2, on a version 1 map; the
## header's on a version 2 map); a diagonal also needs both orthogonal steps
## from the same tile; costs 10 and 14 with a Chebyshev estimate; it gives up
## after 100 000 tiles, and a route is at most 512 steps. A click on a blocked
## tile goes to the nearest walkable tile within 19, as the server does. Steps
## take 600 ms walking or 200 ms running (R), times sqrt(2) on a diagonal.
##
## Not modelled: other players and creatures, storage-body footprints and
## legacy floor overrides the live server adds, and anything changed since the
## last publish. Walkway portals and open borders block every step but the one
## a walk is sent to; the server's full table of them is server configuration,
## so the walker only warns when a route steps on a portal or border crossing
## the published package lists. When a route fails, V (or the failure itself)
## tints what the walker can reach, to show where the ground is cut off. An
## unpublished territory uses the live walkability estimate with the same
## rules, so its routes are estimates too (a territory whose manifest declares
## a served grid it does not ship is estimated with the version 2 rules).
## The walker and its route are editor-only helpers and are never saved.
##
## Codes are a PackedInt32Array for both versions. Grids built elsewhere may
## still hand over a version 1 PackedByteArray; it is widened once on use.

const Walkability := preload("res://addons/map_authoring_usability/walkability_overlay.gd")
const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const TimeOfDay := preload("res://addons/map_authoring_usability/time_of_day_preview.gd")
const ServedGrid := preload("res://addons/map_authoring_usability/served_grid.gd")
const NODE_NAME := "__MapAuthoringPlaytest"
## eloria-server settings: player_move_interval_ms, player_run_interval_ms,
## max_walk_height_change; World.find_path limits. MAX_HEIGHT_CHANGE is the
## version 1 climb; a version 2 grid carries its own.
const WALK_SECONDS := 0.6
const RUN_SECONDS := 0.2
const MAX_HEIGHT_CHANGE := 2
## The walk test as a mask: version 1 is the server's `h & 0x3F`, version 2
## any non-zero code (0x3F would block 64, 128, 4,096 ...).
const WALK_BITS_V1 := 0x3F
const WALK_BITS_V2 := 0xFFFF
const SEARCH_LIMIT := 100000
const MAX_ROUTE_STEPS := 512
const FREE_TILE_RADIUS := 20
## The server's sync fold constants (tools/collision_sources, sync_authored_collision).
const UNIT_METRES := 0.2
const MIN_CODE := 1
const MAX_CODE := 63
const STAGE_LADDER := [1, 2, 3, 4]
const STAGE_GAIN := 1.01
const REACH_NODE_NAME := "Reachable"
const REACH_SHADER := """
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, blend_mix;
uniform sampler2D reach : filter_nearest, repeat_disable;
uniform mat4 region_inverse;
uniform vec4 tiles;
varying vec3 local_position;
void vertex() {
	VERTEX += NORMAL * 0.08;
	local_position = (region_inverse * MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}
void fragment() {
	vec2 tile = vec2(floor(local_position.x + tiles.x), floor(tiles.y - local_position.z));
	vec2 uv = (tile + vec2(0.5)) / tiles.zw;
	if (any(lessThan(uv, vec2(0.0))) || any(greaterThanEqual(uv, vec2(1.0)))) discard;
	float value = floor(texture(reach, uv).r * 255.0 + 0.5);
	if (value < 0.5) discard;
	ALBEDO = value < 1.5 ? vec3(0.2, 0.85, 1.0) : vec3(1.0, 0.55, 0.15);
	ALPHA = 0.42;
}
"""
## World DIRS order, which decides between equal-cost routes.
const DIRECTIONS := [Vector2i(0, 1), Vector2i(1, 1), Vector2i(1, 0), Vector2i(1, -1),
	Vector2i(0, -1), Vector2i(-1, -1), Vector2i(-1, 0), Vector2i(-1, 1)]
const BODY_COLOR := Color(1.0, 0.78, 0.18)
const ROUTE_COLOR := Color(1.0, 0.9, 0.35, 0.95)

var active := false
var last_message := ""
## "published" or "live" once a grid is loaded.
var source := ""
## Steps of the current route.
var steps := 0
## Walking (600 ms a metre) or running (200 ms).
var running := false

var _root: Node3D
var _grid: Dictionary = {}
var _node: Node3D
var _body: Node3D
var _line: MeshInstance3D
var _goal_ring: MeshInstance3D
var _route := PackedVector3Array()
var _step_index := 0
var _step_elapsed := 0.0
var _position := Vector3.INF
var _facing := Vector3.FORWARD
var _reach: MeshInstance3D
var _reach_start := Vector2i(-1, -1)


## Loads the walk grid and shows usage. Returns false when there is nothing to
## walk on.
func start(root: Node3D) -> bool:
	stop()
	if root == null or Probe.region_terrain(root) == null:
		last_message = "Play test needs a region territory with terrain."
		return false
	_root = root
	_grid = load_grid(root)
	if _grid.has("error"):
		last_message = String(_grid.error)
		_grid = {}
		_root = null
		return false
	source = String(_grid.source)
	active = true
	_build_nodes()
	last_message = "%s Click the ground to place the walker." % grid_description()
	return true


func stop() -> void:
	active = false
	_route = PackedVector3Array()
	_position = Vector3.INF
	steps = 0
	if _node != null and is_instance_valid(_node):
		if _node.get_parent() != null:
			_node.get_parent().remove_child(_node)
		_node.queue_free()
	_node = null
	_body = null
	_line = null
	_goal_ring = null
	_reach = null
	_root = null
	_grid = {}


func is_placed() -> bool:
	return _position.is_finite()


func is_walking() -> bool:
	return _route.size() >= 2 and _step_index < _route.size() - 1


## The walker's territory-local position (INF before it is placed).
func position() -> Vector3:
	return _position


func route() -> PackedVector3Array:
	return _route


func node() -> Node3D:
	return _node


## What the grid is and how exact it is, in one sentence.
func grid_description() -> String:
	if _grid.is_empty():
		return ""
	if int(_grid.get("format", 1)) == 2:
		var rule := "16-bit heights, %d mm a code, climb %.2f m" % [roundi(float(_grid.unit_metres) *
			1000.0), float(_grid.climb) * float(_grid.unit_metres)]
		if String(_grid.source) == "live":
			return "Play test on the live (unpublished) grid, an estimate of the next publish (%s)." % rule
		return "Play test on the server's served grid from the published package (%s)." % rule
	var stage := "stage %.1f m" % float(_grid.stage_metres)
	if String(_grid.source) == "live":
		return "Play test on the live (unpublished) grid, an estimate of the next publish (%s)." % stage
	return "Play test on the server's walk grid, folded from the published package (%s)." % stage


func hint_lines() -> PackedStringArray:
	var lines := PackedStringArray()
	if not active:
		return lines
	lines.append("Play test (%s grid, %s)" % [source, "running" if running else "walking"])
	lines.append(last_message)
	lines.append("Click: walk there   Shift+click: place   R: walk/run   V: reachable area   " +
		"F: centre on walker   Esc/right-click: stop")
	return lines


## Viewport input while play testing. Returns true when consumed.
func handle_input(camera: Camera3D, event: InputEvent) -> bool:
	if not active:
		return false
	if event is InputEventKey and event.pressed and not event.echo:
		var key := event as InputEventKey
		if key.keycode == KEY_ESCAPE:
			stop()
			last_message = "Play test ended."
			return true
		if key.keycode == KEY_V and not key.ctrl_pressed and not key.alt_pressed:
			show_reachable(not reachable_visible())
			return true
		if key.keycode == KEY_R and not key.ctrl_pressed and not key.alt_pressed:
			running = not running
			last_message = "Now %s (%d ms a metre)." % ["running" if running else "walking",
				roundi((RUN_SECONDS if running else WALK_SECONDS) * 1000.0)]
			return true
		return false
	if not event is InputEventMouseButton or not event.pressed:
		return false
	var button := event as InputEventMouseButton
	if button.button_index == MOUSE_BUTTON_RIGHT:
		stop()
		last_message = "Play test ended."
		return true
	if button.button_index != MOUSE_BUTTON_LEFT or button.alt_pressed or button.ctrl_pressed:
		return false
	var origin := camera.project_ray_origin(button.position)
	var direction := camera.project_ray_normal(button.position)
	var hit: Variant = Probe.ray_hit(_root, origin, direction, 4096.0)
	if not hit is Vector3:
		last_message = "Click the ground."
		return true
	var local := _root.global_transform.affine_inverse() * (hit as Vector3)
	if button.shift_pressed or not is_placed():
		place(local)
	else:
		walk_to(local)
	return true


## Puts the walker on the tile under `local`, or the nearest walkable one.
func place(local: Vector3) -> bool:
	var tile := free_tile(cell_of(local))
	if not is_walkable(tile):
		last_message = "Nothing walkable within %d m of that spot." % (FREE_TILE_RADIUS - 1)
		return false
	_route = PackedVector3Array()
	_step_index = 0
	_step_elapsed = 0.0
	steps = 0
	show_reachable(false)
	_position = cell_point(tile)
	_update_nodes()
	last_message = "Walker placed on tile %d, %d. Click somewhere to walk there." % [tile.x, tile.y]
	return true


## Finds the server's route from the walker to `local` and starts walking it.
func walk_to(local: Vector3) -> bool:
	if not is_placed():
		return place(local)
	var found := find_route(_position, local)
	if found.size() < 2:
		_route = PackedVector3Array()
		_update_nodes()
		return false
	_route = found
	_step_index = 0
	_step_elapsed = 0.0
	_update_nodes()
	return true


## Seconds step `index` of the current route takes at the chosen pace.
func step_duration(index: int) -> float:
	var interval := RUN_SECONDS if running else WALK_SECONDS
	if index < 0 or index >= _route.size() - 1:
		return interval
	var from := _route[index]
	var to := _route[index + 1]
	var diagonal := absf(to.x - from.x) > 0.5 and absf(to.z - from.z) > 0.5
	return interval * (sqrt(2.0) if diagonal else 1.0)


## Moves the walker along its route; call every frame.
func advance(delta: float) -> void:
	if not active or not is_walking():
		return
	_step_elapsed += delta
	while is_walking() and _step_elapsed >= step_duration(_step_index):
		_step_elapsed -= step_duration(_step_index)
		_step_index += 1
	if is_walking():
		var from := _route[_step_index]
		var to := _route[_step_index + 1]
		_position = from.lerp(to, clampf(_step_elapsed / step_duration(_step_index), 0.0, 1.0))
		var flat := Vector3(to.x - from.x, 0.0, to.z - from.z)
		if flat.length_squared() > 0.0001:
			_facing = flat.normalized()
	else:
		_position = _route[_route.size() - 1]
		var seconds := 0.0
		for index in _route.size() - 1:
			seconds += step_duration(index)
		last_message = "Arrived: %d steps, %.1f s %s." % [steps, seconds,
			"running" if running else "walking"]
	_update_body()


# Grid ----------------------------------------------------------------------

## The server's tile grid for the territory:
## {source, format (1 or 2), codes (PackedInt32Array: 0 blocked, else the
##  height code), width, rows, origin (serverOrigin tiles), climb (the codes a
##  step may change), walk_bits (the walk test's mask), stage_factor and
##  stage_metres (version 1), unit_metres and datum_metres (version 2), and for
##  display either the published half-metre bytes and their height encoding,
##  the version 2 codes' own heights, or "root" for terrain heights}.
## In order: a served grid the manifest declares (refused outright if it is
## bad); the version 2 live estimate when the package does not ship it; the
## folded collision.bin; the version 1 live estimate. The manifest is the
## territory's published package as TimeOfDay finds it (published_manifest_path_for:
## a continent-v2 catalog entry's publishedManifestPath, not its stub), or
## `manifest_path` when given (tests).
static func load_grid(root: Node3D, manifest_path := "") -> Dictionary:
	var origin: Vector2i = root.get("server_origin") if root.get("server_origin") is Vector2i \
		else Vector2i.ZERO
	if manifest_path.is_empty():
		manifest_path = TimeOfDay.published_manifest_path_for(String(root.get("region_id")))
	var served := load_served_grid(manifest_path, origin)
	if bool(served.get("missing", false)):
		# The package declares a version 2 grid it does not ship: estimate one.
		var estimate := Walkability.compute_live(root)
		if estimate.has("error"):
			return {"error": "No walk grid: %s" % String(estimate.error)}
		return fold_live(estimate, origin, root, 2)
	if not served.is_empty():
		return served
	var published := Walkability.published_grid(root, manifest_path)
	if not published.has("error") and not is_nan(float(published.get("height_step", NAN))):
		var folded := fold_published(published, origin)
		var manifest: Variant = null
		if not manifest_path.is_empty():
			manifest = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
		if manifest is Dictionary and not folded.has("error"):
			folded["crossings"] = published_crossings(manifest, origin)
		return folded
	var live := Walkability.compute_live(root)
	if live.has("error"):
		return {"error": "No walk grid: %s" % String(live.error)}
	return fold_live(live, origin, root)


## A published version 2 served grid as the walker's tiles, read as the
## server's sync vendors it: {} when the manifest declares none (a version 1
## territory), {error} when the file is refused, {error, missing} when the
## package does not ship it. Its tiles are the server's own, so unlike
## collision.bin it needs no fold; but the scene's server_origin must be the
## frame the package was exported in (served_frame_error).
static func load_served_grid(manifest_path: String, origin: Vector2i) -> Dictionary:
	if manifest_path.is_empty() or not FileAccess.file_exists(manifest_path):
		return {}
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not manifest is Dictionary or ServedGrid.declared(manifest).is_empty():
		return {}
	var served := ServedGrid.load_declared(manifest_path, manifest)
	if served.has("error"):
		return {"error": "The published served grid is refused: %s." % String(served.error),
			"missing": bool(served.get("missing", false))}
	var frame := served_frame_error(manifest, origin, int(served.width), int(served.height))
	if not frame.is_empty():
		return {"error": "The published served grid is refused: %s." % frame}
	var unit := float(served.unit_mm) / 1000.0
	return {"source": "published", "format": 2, "codes": served.codes, "width": int(served.width),
		"rows": int(served.height), "origin": origin, "climb": int(served.climb_units),
		"walk_bits": WALK_BITS_V2, "unit_metres": unit, "datum_metres": float(served.datum_mm) / 1000.0,
		"stage_metres": unit, "crossings": published_crossings(manifest, origin),
		"served_grid": String(served.path), "sha256": String(served.sha256)}


## Why the scene and the package disagree on the served grid's tiles, or "".
## The grid is indexed by server tile and the walker maps the scene's
## territory-local points onto it with the scene's server_origin, so the frame
## the package states under coordinateTransform must be the scene's: the same
## serverOrigin, serverCells equal to the grid's size, one metre a tile, and
## the server's y running against the scene's z. A stale scene would otherwise
## walk every route on the wrong tiles (D2b moved sw_isle's served origin by
## 30 tiles). The version 1 fold refuses the same misalignment through
## collision.originMetres. A manifest that states no transform is not checked.
static func served_frame_error(manifest: Dictionary, origin: Vector2i, width: int,
		rows: int) -> String:
	var transform: Variant = manifest.get("coordinateTransform")
	if not transform is Dictionary:
		return ""
	var frame: Dictionary = transform
	if frame.has("serverOrigin") and _pair(frame.serverOrigin) != origin:
		return "the package's serverOrigin %s is not the scene's server_origin %s" % [
			str(_pair(frame.serverOrigin)), str(origin)]
	if frame.has("serverCells") and _pair(frame.serverCells) != Vector2i(width, rows):
		return "the served grid is %d x %d tiles, the package's serverCells %s" % [width, rows,
			str(_pair(frame.serverCells))]
	if frame.has("metresPerTile") and not is_equal_approx(float(frame.metresPerTile), 1.0):
		return "the package's metresPerTile is %s, not 1" % str(frame.metresPerTile)
	if frame.has("invertServerY") and not bool(frame.invertServerY):
		return "the package's invertServerY is false"
	return ""


## A JSON [x, y] pair (its numbers parse as floats) as tiles; (-1, -1) for
## anything else.
static func _pair(value: Variant) -> Vector2i:
	if value is Array and (value as Array).size() == 2:
		return Vector2i(int(value[0]), int(value[1]))
	return Vector2i(-1, -1)


## Folds a published half-metre EWCG grid onto one-metre server tiles exactly
## as fold_server_grid / requantise / choose_stage / rescale do.
static func fold_published(published: Dictionary, origin: Vector2i) -> Dictionary:
	var bytes: PackedByteArray = published.bytes
	var cells_x := int(published.width)
	var cells_y := int(published.rows)
	if cells_x % 2 != 0 or cells_y % 2 != 0:
		return {"error": "The published walk grid does not fold onto one-metre tiles."}
	# The published frame must start on a tile edge: x0 = -originX, z1 = originY.
	var tile_x0 := float(published.x0) + float(origin.x)
	var tile_y0 := float(origin.y) - float(published.z1)
	if not is_zero_approx(tile_x0) or not is_zero_approx(tile_y0):
		return {"error": "The published walk grid is not aligned to the server tiles."}
	var width := cells_x / 2
	var rows := cells_y / 2
	var folded := PackedByteArray()
	folded.resize(width * rows)
	var lowest := 256
	var highest := 0
	for ty in rows:
		var top := 2 * ty * cells_x
		var bottom := top + cells_x
		var out := ty * width
		for tx in width:
			var column := 2 * tx
			var a := bytes[top + column]
			var b := bytes[top + column + 1]
			var c := bytes[bottom + column]
			var d := bytes[bottom + column + 1]
			if a == 0 or b == 0 or c == 0 or d == 0:
				continue
			var code := maxi(maxi(a, b), maxi(c, d))
			folded[out + tx] = code
			lowest = mini(lowest, code)
			highest = maxi(highest, code)
	var step := float(published.height_step)
	var height_origin := float(published.height_origin)
	var table := _stage_table(func(code: int) -> float: return float(code) * step + height_origin,
		lowest, highest)
	var units: PackedInt32Array = table.units
	var codes_for := func(factor: int) -> PackedInt32Array:
		var lookup := PackedInt32Array()
		lookup.resize(256)
		for code in range(1, 256):
			lookup[code] = _coarsen(units[code], factor)
		var result := PackedInt32Array()
		result.resize(folded.size())
		for index in folded.size():
			result[index] = lookup[folded[index]]
		return result
	var factor := choose_factor(units[highest] - units[lowest] if highest > 0 else 0, codes_for,
		width, rows)
	var codes: PackedInt32Array = codes_for.call(factor)
	return {"source": "published", "format": 1, "codes": codes, "width": width, "rows": rows,
		"origin": origin, "climb": MAX_HEIGHT_CHANGE, "walk_bits": WALK_BITS_V1,
		"stage_factor": factor, "stage_metres": float(factor) * UNIT_METRES, "crossings": {},
		"display_bytes": bytes, "display_width": cells_x, "height_step": step,
		"height_origin": height_origin}


## The live estimate on the same tiles and rules: walkable live tiles, with
## terrain heights re-expressed like a published grid. Format 1 requantises
## them as the version 1 sync does (0.2 m units above the lowest tile, numpy's
## half-to-even rounding, then the stage ladder); format 2 as the version 2
## codec does (50 mm codes above the continent datum, rounded half up, climb
## from the codec's constants).
static func fold_live(live: Dictionary, origin: Vector2i, root: Node3D, format := 1) -> Dictionary:
	var classes: PackedByteArray = live.classes
	var owned: PackedByteArray = (live.owned as Image).get_data()
	var tile := float(live.tile)
	if not is_equal_approx(tile, 1.0):
		return {"error": "The live walkability grid is not on one-metre tiles."}
	var live_width := int(live.width)
	var live_rows := int(live.rows)
	var min_x := floori(float(live.x0) + 0.5 + float(origin.x))
	var max_x := floori(float(live.x0) + float(live_width) - 0.5 + float(origin.x))
	var min_y := floori(float(origin.y) - (float(live.z0) + float(live_rows) - 0.5))
	var max_y := floori(float(origin.y) - (float(live.z0) + 0.5))
	var width := max_x + 1
	var rows := max_y + 1
	if min_x < 0 or min_y < 0:
		return {"error": "The live grid lies outside the server tiles (negative tiles)."}
	var metres := PackedFloat64Array()
	metres.resize(width * rows)
	metres.fill(NAN)
	var lowest := INF
	for row in live_rows:
		for column in live_width:
			var index := row * live_width + column
			var value := classes[index]
			if (value != Walkability.Tile.WALKABLE and value != Walkability.Tile.DECK) or \
					owned[index * 4 + 3] <= 127:
				continue
			var x := float(live.x0) + float(column) + 0.5
			var z := float(live.z0) + float(row) + 0.5
			var height := Walkability._ground(live, x, z)
			if is_nan(height):
				continue
			var tx := floori(x + float(origin.x))
			var ty := floori(float(origin.y) - z)
			metres[ty * width + tx] = height
			lowest = minf(lowest, height)
	if format == 2:
		var served := PackedInt32Array()
		served.resize(width * rows)
		for index in metres.size():
			if is_nan(metres[index]):
				continue
			var code := ServedGrid.quantise_mm(metres[index] * 1000.0)
			if code < 1 or code > ServedGrid.MAX_CODE:
				return {"error": "A live height of %.2f m lies outside the served grid's range." %
					metres[index]}
			served[index] = code
		var unit := float(ServedGrid.UNIT_MM) / 1000.0
		return {"source": "live", "format": 2, "codes": served, "width": width, "rows": rows,
			"origin": origin, "climb": ServedGrid.CLIMB_MM / ServedGrid.UNIT_MM,
			"walk_bits": WALK_BITS_V2, "unit_metres": unit,
			"datum_metres": float(ServedGrid.DATUM_MM) / 1000.0, "stage_metres": unit, "root": root}
	var codes := PackedInt32Array()
	codes.resize(width * rows)
	var highest_units := 1
	var units := PackedInt32Array()
	units.resize(width * rows)
	for index in metres.size():
		if is_nan(metres[index]):
			continue
		units[index] = int(round_half_even((metres[index] - lowest) / UNIT_METRES)) + MIN_CODE
		highest_units = maxi(highest_units, units[index])
	var codes_for := func(stage: int) -> PackedInt32Array:
		var result := PackedInt32Array()
		result.resize(units.size())
		for index in units.size():
			if units[index] > 0:
				result[index] = _coarsen(units[index], stage)
		return result
	var factor := choose_factor(highest_units - MIN_CODE, codes_for, width, rows)
	codes = codes_for.call(factor)
	return {"source": "live", "format": 1, "codes": codes, "width": width, "rows": rows,
		"origin": origin, "climb": MAX_HEIGHT_CHANGE, "walk_bits": WALK_BITS_V1,
		"stage_factor": factor, "stage_metres": float(factor) * UNIT_METRES, "root": root}


## The smallest stage (in 0.2 m units) that fits `relief` units into 63 codes;
## sync_authored_collision.stage_ladder's lower bound.
static func stage_factor(relief: int) -> int:
	return maxi(1, ceili(float(relief) / float(MAX_CODE - MIN_CODE)))


## sync_authored_collision.choose_stage: the stages worth trying are those of
## 1-4 units at or above the relief's lower bound (or just that bound when it
## is higher); the smallest whose largest reachable area is within 1% of the
## best any of them gives wins. `codes_for` builds the grid at one stage.
static func choose_factor(relief: int, codes_for: Callable, width: int, rows: int) -> int:
	var smallest := stage_factor(relief)
	var ladder: Array[int] = []
	for factor: int in STAGE_LADDER:
		if factor >= smallest:
			ladder.append(factor)
	if ladder.is_empty():
		return smallest
	if ladder.size() == 1:
		return ladder[0]
	var scores := {}
	var best := 0
	for factor in ladder:
		scores[factor] = largest_component(codes_for.call(factor), width, rows)
		best = maxi(best, int(scores[factor]))
	for factor in ladder:
		if float(scores[factor]) * STAGE_GAIN >= float(best):
			return factor
	return ladder[ladder.size() - 1]


## The size of the largest set of tiles that can all reach each other. `codes`
## is a PackedInt32Array, or a version 1 PackedByteArray; `climb` and
## `walk_bits` are the grid's (version 1 by default).
static func largest_component(codes: Variant, width: int, rows: int,
		climb := MAX_HEIGHT_CHANGE, walk_bits := WALK_BITS_V1) -> int:
	var tiles := as_codes(codes)
	var seen := PackedByteArray()
	seen.resize(tiles.size())
	var best := 0
	var queue := PackedInt32Array()
	for index in tiles.size():
		if tiles[index] & walk_bits == 0 or seen[index] != 0:
			continue
		best = maxi(best, _flood(tiles, width, rows, index, seen, queue, 1, climb, walk_bits))
	return best


## Codes as the walker's one code type: a PackedInt32Array is used as it is,
## a version 1 PackedByteArray (or an Array) is widened.
static func as_codes(codes: Variant) -> PackedInt32Array:
	if codes is PackedInt32Array:
		return codes
	if codes is PackedByteArray:
		return PackedInt32Array(Array(codes))
	if codes is Array:
		return PackedInt32Array(codes)
	return PackedInt32Array()


## Marks every tile reachable from `start` with `mark` in `seen`; returns how many.
## The step test is _step_ok's (both tiles walkable under `walk_bits`, the code
## change within `climb`) with the corner rule, written out inline: each of the
## four orthogonal steps is tested once and reused for the two diagonals beside
## it. A 2 km version 2 map has 4.2 M tiles, and the reach tint floods it on the
## main thread after every failed route.
static func _flood(codes: PackedInt32Array, width: int, rows: int, start: int,
		seen: PackedByteArray, queue: PackedInt32Array, mark: int, climb: int,
		walk_bits: int) -> int:
	queue.resize(0)
	queue.append(start)
	seen[start] = mark
	var head := 0
	var last_x := width - 1
	var last_y := rows - 1
	var there := 0
	var next := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		var here := codes[current]
		if here & walk_bits == 0:
			continue
		var low := here - climb
		var high := here + climb
		var cx := current % width
		var cy := current / width
		var y_up := false
		var x_up := false
		var y_down := false
		var x_down := false
		if cy < last_y:
			there = codes[current + width]
			y_up = there & walk_bits != 0 and there >= low and there <= high
		if cx < last_x:
			there = codes[current + 1]
			x_up = there & walk_bits != 0 and there >= low and there <= high
		if cy > 0:
			there = codes[current - width]
			y_down = there & walk_bits != 0 and there >= low and there <= high
		if cx > 0:
			there = codes[current - 1]
			x_down = there & walk_bits != 0 and there >= low and there <= high
		# DIRECTIONS order: (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1),
		# (-1, 0), (-1, 1). A diagonal needs both orthogonal steps it cuts.
		if y_up:
			next = current + width
			if seen[next] == 0:
				seen[next] = mark
				queue.append(next)
			if x_up:
				next = current + width + 1
				there = codes[next]
				if seen[next] == 0 and there & walk_bits != 0 and there >= low and there <= high:
					seen[next] = mark
					queue.append(next)
		if x_up:
			next = current + 1
			if seen[next] == 0:
				seen[next] = mark
				queue.append(next)
			if y_down:
				next = current - width + 1
				there = codes[next]
				if seen[next] == 0 and there & walk_bits != 0 and there >= low and there <= high:
					seen[next] = mark
					queue.append(next)
		if y_down:
			next = current - width
			if seen[next] == 0:
				seen[next] = mark
				queue.append(next)
			if x_down:
				next = current - width - 1
				there = codes[next]
				if seen[next] == 0 and there & walk_bits != 0 and there >= low and there <= high:
					seen[next] = mark
					queue.append(next)
		if x_down:
			next = current - 1
			if seen[next] == 0:
				seen[next] = mark
				queue.append(next)
			if y_up:
				next = current + width - 1
				there = codes[next]
				if seen[next] == 0 and there & walk_bits != 0 and there >= low and there <= high:
					seen[next] = mark
					queue.append(next)
	return head


## Per published code: requantised units and the final stage code, as a
## lookup table over 0-255 (requantise rebases on the lowest walkable tile).
static func _stage_table(decode: Callable, lowest: int, highest: int) -> Dictionary:
	var codes := PackedByteArray()
	codes.resize(256)
	if highest == 0:
		return {"codes": codes, "factor": 1, "units": PackedInt32Array()}
	var floor_metres: float = decode.call(lowest)
	var units := PackedInt32Array()
	units.resize(256)
	for code in range(1, 256):
		units[code] = int(round_half_even((float(decode.call(code)) - floor_metres) /
			UNIT_METRES)) + MIN_CODE
	var factor := stage_factor(units[highest] - units[lowest])
	for code in range(1, 256):
		codes[code] = _coarsen(units[code], factor)
	return {"codes": codes, "factor": factor, "units": units}


## rescale(): ceil(units / factor) clamped to the codes an ELM byte holds.
static func _coarsen(units: int, factor: int) -> int:
	if factor == 1:
		return clampi(units, 0, 255)
	return clampi(ceili(float(units) / float(factor)), MIN_CODE, MAX_CODE)


## numpy.round: halves go to the even neighbour.
static func round_half_even(value: float) -> float:
	var lower := floorf(value)
	var fraction := value - lower
	if fraction > 0.5:
		return lower + 1.0
	if fraction < 0.5:
		return lower
	return lower if fmod(lower, 2.0) == 0.0 else lower + 1.0


func grid() -> Dictionary:
	return _grid


## The server tile under a territory-local point (it may be outside the grid).
func cell_of(local: Vector3) -> Vector2i:
	var origin: Vector2i = _grid.origin
	return Vector2i(floori(local.x + float(origin.x)), floori(float(origin.y) - local.z))


func _inside(tile: Vector2i) -> bool:
	return tile.x >= 0 and tile.y >= 0 and tile.x < int(_grid.width) and tile.y < int(_grid.rows)


func code_at(tile: Vector2i) -> int:
	return _codes()[tile.y * int(_grid.width) + tile.x] if _inside(tile) else 0


## The grid's codes as a PackedInt32Array; a version 1 PackedByteArray set by
## other code is widened once and kept.
func _codes() -> PackedInt32Array:
	var codes: Variant = _grid.get("codes")
	if codes is PackedInt32Array:
		return codes
	var widened := as_codes(codes)
	_grid["codes"] = widened
	return widened


## The codes a step may change: the header's on a version 2 grid, 2 otherwise.
func grid_climb() -> int:
	return int(_grid.get("climb", MAX_HEIGHT_CHANGE))


## The walk test's mask: any non-zero code on version 2, `& 0x3F` on version 1.
func grid_walk_bits() -> int:
	return int(_grid.get("walk_bits", WALK_BITS_V1))


func is_walkable(tile: Vector2i) -> bool:
	return code_at(tile) & grid_walk_bits() != 0


## CollisionMap.can_step: both tiles walkable and the code change within the
## map's climb (CollisionMap.climb_for).
func can_step(from: Vector2i, to: Vector2i) -> bool:
	var start := code_at(from)
	var end := code_at(to)
	var bits := grid_walk_bits()
	return start & bits != 0 and end & bits != 0 and absi(end - start) <= grid_climb()


## World.step_allowed for a single step, corners included.
func step_allowed(from: Vector2i, to: Vector2i) -> bool:
	var delta := to - from
	if not can_step(from, to):
		return false
	return delta.x == 0 or delta.y == 0 or (can_step(from, Vector2i(to.x, from.y)) and
		can_step(from, Vector2i(from.x, to.y)))


## World.free_player_tile without occupants: the tile itself when walkable,
## otherwise the first walkable tile ring by ring out to 19.
func free_tile(tile: Vector2i) -> Vector2i:
	if is_walkable(tile):
		return tile
	for radius in range(1, FREE_TILE_RADIUS):
		for dx in range(-radius, radius + 1):
			for dy in range(-radius, radius + 1):
				if maxi(absi(dx), absi(dy)) == radius and is_walkable(tile + Vector2i(dx, dy)):
					return tile + Vector2i(dx, dy)
	return tile


## A tile's centre on the ground the walker stands on (territory-local).
func cell_point(tile: Vector2i) -> Vector3:
	var origin: Vector2i = _grid.origin
	var x := float(tile.x) + 0.5 - float(origin.x)
	var z := float(origin.y) - float(tile.y) - 0.5
	var ground := _terrain_height(Vector2(x, z))
	var y := ground
	var served := String(_grid.get("source", "")) == "published" and int(_grid.get("format", 1)) == 2
	if _grid.has("display_bytes") or served:
		# The published grid knows decks and floors the terrain does not.
		var deck := _served_height(tile) if served else _published_height(tile)
		if not is_nan(deck) and (is_nan(ground) or deck > ground + 0.5):
			y = deck
	return Vector3(x, y if not is_nan(y) else 0.0, z)


## A version 2 tile's own height: the highest of its four half-metre cells, to
## 50 mm (datum + code * unit), or NAN where it is blocked.
func _served_height(tile: Vector2i) -> float:
	var code := code_at(tile)
	if code == 0:
		return NAN
	return float(_grid.datum_metres) + float(code) * float(_grid.unit_metres)


func _published_height(tile: Vector2i) -> float:
	var bytes: PackedByteArray = _grid.display_bytes
	var cells_x := int(_grid.display_width)
	var highest := 0
	for offset: Vector2i in [Vector2i(0, 0), Vector2i(1, 0), Vector2i(0, 1), Vector2i(1, 1)]:
		var column := 2 * tile.x + offset.x
		var row := 2 * tile.y + offset.y
		var index := row * cells_x + column
		if column < cells_x and index < bytes.size():
			highest = maxi(highest, bytes[index])
	return float(_grid.height_origin) + float(highest) * float(_grid.height_step) \
		if highest > 0 else NAN


## World.find_path from the tile under `from_local` to the tile under
## `to_local`: ground points of the route, start included; empty (with
## last_message saying why) when the server would not move.
func find_route(from_local: Vector3, to_local: Vector3) -> PackedVector3Array:
	var result := PackedVector3Array()
	var start := cell_of(from_local)
	if not is_walkable(start):
		last_message = "The walker is not on a walkable tile."
		return result
	var clicked := cell_of(to_local)
	var target := free_tile(clicked)
	if target == start:
		steps = 0
		last_message = "The walker is already there."
		return result
	var path := search(start, target)
	if path.is_empty():
		steps = 0
		show_reachable(true, start)
		last_message = ("You cannot reach that location: the server finds no route%s. %s" +
			" Tinted: blue is where the walker can go, orange is walkable ground cut off from it (V hides).") % [
			" within its 100 000-tile search" if int(_grid.get("last_search_nodes", 0)) > SEARCH_LIMIT
				else "", "The goal is in the walker's reachable area, but farther than the server searches." \
				if is_reachable(target) else "It is fenced, walled, too steep a climb, or cut off."]
		return result
	result.append(cell_point(start))
	for tile in path:
		result.append(cell_point(tile))
	steps = path.size()
	var seconds := 0.0
	var interval := RUN_SECONDS if running else WALK_SECONDS
	var previous := start
	for tile in path:
		var delta := tile - previous
		seconds += interval * (sqrt(2.0) if delta.x != 0 and delta.y != 0 else 1.0)
		previous = tile
	last_message = "%s %d steps, %.1f s." % ["Running" if running else "Walking", steps, seconds]
	if target != clicked:
		last_message += " That spot is blocked, so the route ends on the nearest walkable tile."
	var crossing := crossing_on(path)
	if not crossing.is_empty():
		last_message += (" It steps on %s; the server never walks across a portal it was not " +
			"sent to, so its route goes round it.") % crossing
	if bool(_grid.get("last_search_truncated", false)):
		last_message += " The server walks at most 512 steps per click; click again to go on."
	return result


## The server's A*: returns the tiles after `start` up to `target` (at most 512),
## or empty when the search fails.
func search(start: Vector2i, target: Vector2i) -> Array[Vector2i]:
	var width := int(_grid.width)
	var codes := _codes()
	var climb_codes := grid_climb()
	var bits := grid_walk_bits()
	var count := width * int(_grid.rows)
	var cost := PackedInt32Array()
	cost.resize(count)
	cost.fill(-1)
	var previous := PackedInt32Array()
	previous.resize(count)
	previous.fill(-1)
	var start_index := start.y * width + start.x
	var target_index := target.y * width + target.x
	cost[start_index] = 0
	var discovered := 1
	var heap := PackedInt64Array()
	var nodes := PackedInt32Array()
	# Keys order like the server's (f, sequence) tuples; the sequence indexes nodes.
	_heap_push(heap, 0)
	nodes.append(start_index)
	var sequence := 0
	var destination := -1
	while not heap.is_empty() and discovered <= SEARCH_LIMIT:
		var key := _heap_pop(heap)
		var current := nodes[key & 0xFFFFFFFFFF]
		var cx := current % width
		var cy := current / width
		if maxi(absi(target.x - cx), absi(target.y - cy)) <= 0:
			destination = current
			break
		var here := codes[current]
		for direction: Vector2i in DIRECTIONS:
			var nx := cx + direction.x
			var ny := cy + direction.y
			if not _step_ok(codes, width, count, cx, cy, nx, ny, here, climb_codes, bits):
				continue
			if direction.x != 0 and direction.y != 0 and (
					not _step_ok(codes, width, count, cx, cy, nx, cy, here, climb_codes, bits) or
					not _step_ok(codes, width, count, cx, cy, cx, ny, here, climb_codes, bits)):
				continue
			var next := ny * width + nx
			var new_cost := cost[current] + (14 if direction.x != 0 and direction.y != 0 else 10)
			if cost[next] < 0 or new_cost < cost[next]:
				if cost[next] < 0:
					discovered += 1
				cost[next] = new_cost
				previous[next] = current
				sequence += 1
				var estimate := 10 * maxi(maxi(absi(target.x - nx), absi(target.y - ny)), 0)
				_heap_push(heap, (int(new_cost + estimate) << 40) | sequence)
				nodes.append(next)
	_grid["last_search_nodes"] = discovered
	var path: Array[Vector2i] = []
	if destination < 0:
		_grid["last_search_truncated"] = false
		return path
	var walk := destination
	while walk != start_index:
		path.append(Vector2i(walk % width, walk / width))
		walk = previous[walk]
	path.reverse()
	_grid["last_search_truncated"] = path.size() > MAX_ROUTE_STEPS
	if path.size() > MAX_ROUTE_STEPS:
		path.resize(MAX_ROUTE_STEPS)
	return path


## The first published portal or border crossing a route steps on before its
## last tile, described for the status line, or "".
func crossing_on(path: Array[Vector2i]) -> String:
	var crossings: Dictionary = _grid.get("crossings", {})
	if crossings.is_empty():
		return ""
	for index in path.size() - 1:
		if crossings.has(path[index]):
			return "%s at tile %d, %d" % [String(crossings[path[index]]), path[index].x, path[index].y]
	return ""


## The published package's walk-on portals and border crossing lanes, by tile.
static func published_crossings(manifest: Dictionary, origin: Vector2i) -> Dictionary:
	var result := {}
	for portal: Variant in manifest.get("portals", []):
		if not portal is Dictionary:
			continue
		var record: Dictionary = portal
		var tile := Vector2i(-1, -1)
		if record.get("serverTile") is Array and (record.serverTile as Array).size() == 2:
			tile = Vector2i(int(record.serverTile[0]), int(record.serverTile[1]))
		elif record.get("position") is Array and (record.position as Array).size() == 3:
			tile = Vector2i(floori(float(record.position[0]) + float(origin.x)),
				floori(float(origin.y) - float(record.position[2])))
		if tile.x >= 0:
			result[tile] = "the portal %s" % String(record.get("label", record.get("name", record.get("id", ""))))
	for border: Variant in manifest.get("streamingBorders", []):
		if not border is Dictionary or not (border as Dictionary).get("anchor") is Array or \
				not (border as Dictionary).get("outward") is Array:
			continue
		var record: Dictionary = border
		var anchor := Vector2(float(record.anchor[0]), float(record.anchor[2]))
		var outward := Vector2(float(record.outward[0]), float(record.outward[1]))
		var along := Vector2(-outward.y, outward.x)
		var half := int(record.get("halfWidthTiles", 3))
		for offset in range(-half, half + 1):
			var point := anchor + along * float(offset)
			result[Vector2i(floori(point.x + float(origin.x)), floori(float(origin.y) - point.y))] = \
				"the crossing to %s" % String(record.get("destination", "a neighbour"))
	return result


## Tints the tiles the walker (or `from`) can reach, and walkable tiles it
## cannot (is_reachable answers for one tile). Returns whether it is showing.
func show_reachable(visible: bool, from: Vector2i = Vector2i(-1, -1)) -> bool:
	if not visible or _grid.is_empty():
		if _reach != null and is_instance_valid(_reach):
			_reach.visible = false
		return false
	var start := from if from.x >= 0 else cell_of(_position)
	if not is_walkable(start):
		return false
	var width := int(_grid.width)
	var rows := int(_grid.rows)
	var codes := _codes()
	var bits := grid_walk_bits()
	var seen := PackedByteArray()
	seen.resize(codes.size())
	_flood(codes, width, rows, start.y * width + start.x, seen, PackedInt32Array(), 1, grid_climb(),
		bits)
	var classes := PackedByteArray()
	classes.resize(codes.size())
	for index in codes.size():
		if seen[index] != 0:
			classes[index] = 1
		elif codes[index] & bits != 0:
			classes[index] = 2
	_grid["reach_classes"] = classes
	_grid["reach_seen"] = seen
	_reach_start = start
	_show_reach_texture(classes, width, rows)
	return true


func reachable_visible() -> bool:
	return _reach != null and is_instance_valid(_reach) and _reach.visible


## Whether `tile` is in the last reachable-area flood.
func is_reachable(tile: Vector2i) -> bool:
	var seen: PackedByteArray = _grid.get("reach_seen", PackedByteArray())
	var width := int(_grid.get("width", 0))
	return _inside(tile) and not seen.is_empty() and seen[tile.y * width + tile.x] != 0


func _show_reach_texture(classes: PackedByteArray, width: int, rows: int) -> void:
	if _root == null or _node == null:
		return
	var terrain := Probe.region_terrain(_root)
	var preview := terrain.get_node_or_null("__TerrainPreview") as MeshInstance3D \
		if terrain != null else null
	if preview == null:
		return
	if _reach == null or not is_instance_valid(_reach):
		_reach = MeshInstance3D.new()
		_reach.name = REACH_NODE_NAME
		_reach.top_level = true
		_reach.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var shader := Shader.new()
		shader.code = REACH_SHADER
		var material := ShaderMaterial.new()
		material.shader = shader
		material.render_priority = 4
		_reach.material_override = material
		_node.add_child(_reach)
	_reach.mesh = preview.mesh
	_reach.global_transform = preview.global_transform
	var image := Image.create_from_data(width, rows, false, Image.FORMAT_L8, classes)
	var material := _reach.material_override as ShaderMaterial
	var origin: Vector2i = _grid.origin
	material.set_shader_parameter("reach", ImageTexture.create_from_image(image))
	material.set_shader_parameter("region_inverse", Projection(_root.global_transform.affine_inverse()))
	material.set_shader_parameter("tiles", Vector4(float(origin.x), float(origin.y), float(width),
		float(rows)))
	_reach.visible = true


## One step's walk test (CollisionMap.can_step): both tiles walkable under
## `walk_bits` and the code change within `climb`.
static func _step_ok(codes: PackedInt32Array, width: int, count: int, x: int, y: int,
		nx: int, ny: int, here: int, climb: int, walk_bits: int) -> bool:
	if nx < 0 or ny < 0 or nx >= width or ny * width + nx >= count:
		return false
	var there := codes[ny * width + nx]
	return here & walk_bits != 0 and there & walk_bits != 0 and absi(there - here) <= climb


static func _heap_push(heap: PackedInt64Array, key: int) -> void:
	heap.append(key)
	var index := heap.size() - 1
	while index > 0:
		var parent := (index - 1) >> 1
		if heap[parent] <= key:
			break
		heap[index] = heap[parent]
		index = parent
	heap[index] = key


static func _heap_pop(heap: PackedInt64Array) -> int:
	var top := heap[0]
	var last := heap[heap.size() - 1]
	heap.resize(heap.size() - 1)
	var size := heap.size()
	if size == 0:
		return top
	var index := 0
	while true:
		var child := 2 * index + 1
		if child >= size:
			break
		if child + 1 < size and heap[child + 1] < heap[child]:
			child += 1
		if heap[child] >= last:
			break
		heap[index] = heap[child]
		index = child
	heap[index] = last
	return top


func _terrain_height(point: Vector2) -> float:
	var root: Node3D = _root if _root != null else _grid.get("root") as Node3D
	if root == null:
		return NAN
	var world := root.global_transform * Vector3(point.x, 0.0, point.y)
	var height := Probe.height_at(root, world)
	if is_nan(height):
		return NAN
	return (root.global_transform.affine_inverse() * Vector3(world.x, height, world.z)).y


# Nodes ---------------------------------------------------------------------

func _build_nodes() -> void:
	_node = Node3D.new()
	_node.name = NODE_NAME
	var material := StandardMaterial3D.new()
	material.albedo_color = BODY_COLOR
	material.emission_enabled = true
	material.emission = BODY_COLOR * 0.35
	_body = Node3D.new()
	_body.name = "Walker"
	var capsule := CapsuleMesh.new()
	capsule.radius = 0.32
	capsule.height = 1.8
	capsule.material = material
	var body_mesh := MeshInstance3D.new()
	body_mesh.mesh = capsule
	body_mesh.position = Vector3(0.0, 0.9, 0.0)
	_body.add_child(body_mesh)
	var nose := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(0.18, 0.18, 0.4)
	box.material = material
	nose.mesh = box
	nose.position = Vector3(0.0, 1.45, -0.38)
	_body.add_child(nose)
	_body.visible = false
	_node.add_child(_body)
	var line_material := StandardMaterial3D.new()
	line_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	line_material.vertex_color_use_as_albedo = true
	line_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	line_material.no_depth_test = true
	_line = MeshInstance3D.new()
	_line.name = "Route"
	_line.mesh = ImmediateMesh.new()
	_line.material_override = line_material
	_line.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_node.add_child(_line)
	_goal_ring = MeshInstance3D.new()
	_goal_ring.name = "Goal"
	var torus := TorusMesh.new()
	torus.inner_radius = 0.45
	torus.outer_radius = 0.6
	torus.material = line_material
	_goal_ring.mesh = torus
	_goal_ring.visible = false
	_node.add_child(_goal_ring)
	_root.add_child(_node, false, Node.INTERNAL_MODE_BACK)
	_node.transform = Transform3D.IDENTITY


func _update_nodes() -> void:
	if _node == null:
		return
	var mesh := _line.mesh as ImmediateMesh
	mesh.clear_surfaces()
	if _route.size() >= 2:
		mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for point in _route:
			mesh.surface_set_color(ROUTE_COLOR)
			mesh.surface_add_vertex(point + Vector3(0.0, 0.12, 0.0))
		mesh.surface_end()
		_goal_ring.visible = true
		_goal_ring.position = _route[_route.size() - 1] + Vector3(0.0, 0.08, 0.0)
	else:
		_goal_ring.visible = false
	_update_body()


func _update_body() -> void:
	if _body == null:
		return
	_body.visible = is_placed()
	if is_placed():
		_body.transform = Transform3D(Basis.looking_at(_facing, Vector3.UP), _position)

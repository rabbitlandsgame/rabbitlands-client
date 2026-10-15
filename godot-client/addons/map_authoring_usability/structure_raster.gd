@tool
extends RefCounted
## The bake's structure and deck rules (collision_export.py _mesh_groups,
## structural_mask; glb_reader.rasterise) on the editor's own scene, on the
## served half-metre cells.
##
## Classification follows the exported hierarchy. The exporter renames an
## asset's first scene root to its node name and any further roots to
## "<node name>__companion_<n>_<name>", and lists the node names of solid
## assets in manifest.collision.nodeNames. So a mesh is
## - a deck when a Walk_ node is among its ancestors (the renamed root
##   included) and none of them names a ceiling, soffit, underside or roof,
##   whatever the asset's collision role;
## - solid when its asset is "solid", it sits under the first root, and it is
##   not under a Terrain_ or Walk_ surface (unless that surface is a ceiling).
##
## A deck supports a cell when its highest upward face there (grade at most
## 0.65) is no more than 3 cm below the terrain; the actor then stands on it.
## A solid blocks a cell when any of its triangles crosses the actor's prism
## there (0.5 × 0.5 m, standing + 0.06 m to standing + 2.10 m; separating-axis
## test), and a closed solid also blocks the cells inside it (signed winding
## of a ray from standing + 1.05 m).
##
## A continent-v2 territory publishes through _continent_v2/export_collision.py,
## which adds two rules (gather's `continent_v2`):
## - trunk: a solid model whose file stem contains "tree" blocks only its trunk,
##   a closed 8-gon prism at the narrowest 0.3 m slice of the model between 0.3
##   and 2.1 m (that slice's median radius, clipped to 0.25-1.0 m), from 1 m
##   below the model's origin to 3 m above it;
## - enclosed: an open (not watertight) solid also blocks the ground its blocked
##   shell walls in on every side, except the cells its own Walk_ deck covers.
##
## blocked_cells is pure and runs on a worker thread; everything that reads the
## scene or a Mesh stays on the main thread.

const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")

const CELL := 0.5
const ACTOR_FLOOR_CLEARANCE := 0.06
const ACTOR_HEIGHT := 2.1
const MAX_GRADE := 0.65
const DECK_TOLERANCE := 0.03
const CEILINGS := ["ceiling", "soffit", "underside", "roof"]
## export_collision.py's TRUNK_* constants.
const TRUNK_WORDS := ["tree"]
const TRUNK_BAND_LOW := 0.3
const TRUNK_BAND_HIGH := 2.1
const TRUNK_SLICE := 0.3
const TRUNK_MIN_VERTICES := 8
const TRUNK_RADIUS_MIN := 0.25
const TRUNK_RADIUS_MAX := 1.0
const TRUNK_SIDES := 8
const TRUNK_SPAN_LOW := -1.0
const TRUNK_SPAN_HIGH := 3.0

## Mesh instance id -> {"faces": local triangles in glTF (counter-clockwise)
## order, "closed": bool}. Meshes are immutable once imported; a reimport makes
## a new instance.
static var _mesh_cache := {}


## Every authored asset's meshes as the bake sees them, in root-local space:
## {"solids": [{"key", "name", "signature", "low", "high", "parts": [{"faces",
## "transform", "closed"}], "enclose", "deck"}], "decks": [{"name",
## "triangles"}]}. With `continent_v2` a tree's parts are its trunk prism, and
## "enclose" asks blocked_cells to fill what an open solid walls in, sparing
## "deck" (the asset's own Walk_ triangles).
static func gather(root: Node3D, continent_v2 := false) -> Dictionary:
	var solids: Array = []
	var decks: Array = []
	var assets := root.get_node_or_null("AuthoredAssets")
	if assets == null:
		return {"solids": solids, "decks": decks}
	var inverse := root.global_transform.affine_inverse()
	for asset in assets.get_children():
		if asset.get_script() != ASSET_SCRIPT:
			continue
		var role := String(asset.get("collision_role"))
		var placement := String(asset.get("node_name"))
		if placement.is_empty():
			placement = String(asset.name)
		var roots := _scene_roots(asset as Node3D)
		var parts: Array = []
		var own_deck := PackedVector3Array()
		var signature := PackedStringArray()
		var low := Vector3(INF, INF, INF)
		var high := -low
		for root_index in roots.size():
			var scene_root: Node = roots[root_index]
			var root_name := placement if root_index == 0 else "%s__companion_%d_%s" % [
				placement, root_index, String(scene_root.name)]
			var meshes: Array = [scene_root] if scene_root is MeshInstance3D else []
			meshes.append_array(scene_root.find_children("*", "MeshInstance3D", true, false))
			for mesh_value in meshes:
				var mesh_node := mesh_value as MeshInstance3D
				if mesh_node.mesh == null or not mesh_node.is_visible_in_tree():
					continue
				var names := PackedStringArray([root_name])
				var walk := root_name.begins_with("Walk_")
				var surface := walk or root_name.begins_with("Terrain_")
				var ceiling := _names_ceiling(root_name)
				var current: Node = mesh_node
				while current != scene_root and current != null:
					var label := String(current.name)
					walk = walk or label.begins_with("Walk_")
					surface = surface or label.begins_with("Walk_") or label.begins_with("Terrain_")
					ceiling = ceiling or _names_ceiling(label)
					current = current.get_parent()
				var deck := surface and walk and not ceiling
				var solid := role == "solid" and root_index == 0 and not (surface and not ceiling)
				if not deck and not solid:
					continue
				var shape := mesh_shape(mesh_node.mesh)
				var transform: Transform3D = inverse * mesh_node.global_transform
				if deck:
					var local: PackedVector3Array = shape.faces
					var triangles := PackedVector3Array()
					triangles.resize(local.size())
					for index in local.size():
						triangles[index] = transform * local[index]
					decks.append({"name": String(asset.name), "triangles": triangles})
					own_deck.append_array(triangles)
				if solid:
					parts.append({"faces": shape.faces, "transform": transform,
						"closed": bool(shape.closed), "aabb": mesh_node.mesh.get_aabb()})
					signature.append("%d%s" % [mesh_node.mesh.get_instance_id(), str(transform)])
					var box: AABB = transform * mesh_node.mesh.get_aabb()
					low = low.min(box.position)
					high = high.max(box.end)
		if parts.is_empty():
			continue
		if continent_v2 and _trunk_model(String(asset.get("scene_path"))):
			var prism := trunk(_model_points(asset as Node3D))
			if not prism.is_empty():
				var placed: Transform3D = inverse * (asset as Node3D).global_transform
				var box := AABB(prism[0], Vector3.ZERO)
				for point in prism:
					box = box.expand(point)
				parts = [{"faces": prism, "transform": placed, "closed": true, "aabb": box}]
				signature.append("trunk%s" % str(placed))
				var placed_box: AABB = placed * box
				low = placed_box.position
				high = placed_box.end
		solids.append({"key": "%s#%d" % [placement, asset.get_instance_id()],
			"name": String(asset.name), "parts": parts, "low": low, "high": high,
			"enclose": continent_v2, "deck": own_deck if continent_v2 else PackedVector3Array(),
			"signature": ("v2|" if continent_v2 else "") + "|".join(signature)})
	return {"solids": solids, "decks": decks}


## Whether export_collision.py reads a placement of this scene as a tree: its
## baked source is the .glb itself (a .tscn bakes to a hashed prototype name)
## and the file's stem contains a TRUNK_WORDS word.
static func _trunk_model(scene_path: String) -> bool:
	if not scene_path.get_extension().to_lower() in ["glb", "gltf"]:
		return false
	var stem := scene_path.get_file().get_basename()
	for word: String in TRUNK_WORDS:
		if word in stem:
			return true
	return false


## Every triangle corner of an asset's model, in the model file's own space (the
## imported scene root's), as export_collision.Prototype's `every` holds them.
static func _model_points(asset: Node3D) -> PackedVector3Array:
	var points := PackedVector3Array()
	var content: Node3D = asset.call("content_root")
	if content == null:
		return points
	var to_model := content.global_transform.affine_inverse()
	var meshes: Array = [content] if content is MeshInstance3D else []
	meshes.append_array(content.find_children("*", "MeshInstance3D", true, false))
	for mesh_value in meshes:
		var mesh_node := mesh_value as MeshInstance3D
		if mesh_node.mesh == null:
			continue
		var transform: Transform3D = to_model * mesh_node.global_transform
		var faces: PackedVector3Array = mesh_shape(mesh_node.mesh).faces
		for point in faces:
			points.append(transform * point)
	return points


## export_collision.trunk: the closed prism a tree blocks with, as glTF-wound
## triangles in the model's space, or empty when no slice of TRUNK_BAND holds
## TRUNK_MIN_VERTICES corners (the whole model then stays the solid).
static func trunk(points: PackedVector3Array) -> PackedVector3Array:
	var found := false
	var best_x := 0.0
	var best_z := 0.0
	var best_radius := INF
	var low := TRUNK_BAND_LOW
	while low < TRUNK_BAND_HIGH - 1e-9:
		var top := minf(low + TRUNK_SLICE, TRUNK_BAND_HIGH)
		var xs := PackedFloat64Array()
		var zs := PackedFloat64Array()
		for point in points:
			if point.y >= low and point.y < top:
				xs.append(point.x)
				zs.append(point.z)
		low += TRUNK_SLICE
		if xs.size() < TRUNK_MIN_VERTICES:
			continue
		var cx := 0.0
		var cz := 0.0
		for index in xs.size():
			cx += xs[index]
			cz += zs[index]
		cx /= float(xs.size())
		cz /= float(xs.size())
		var distances := PackedFloat64Array()
		distances.resize(xs.size())
		for index in xs.size():
			distances[index] = sqrt((xs[index] - cx) * (xs[index] - cx) +
				(zs[index] - cz) * (zs[index] - cz))
		distances.sort()
		var middle := distances.size() / 2
		var radius := distances[middle] if distances.size() % 2 == 1 else \
			(distances[middle - 1] + distances[middle]) * 0.5
		if not found or radius < best_radius:
			found = true
			best_x = cx
			best_z = cz
			best_radius = radius
	var prism := PackedVector3Array()
	if not found:
		return prism
	var radius := clampf(best_radius, TRUNK_RADIUS_MIN, TRUNK_RADIUS_MAX)
	var ring: Array[Vector2] = []
	for side in TRUNK_SIDES:
		var angle := float(side) * TAU / float(TRUNK_SIDES)
		ring.append(Vector2(best_x + radius * cos(angle), best_z + radius * sin(angle)))
	var y0 := TRUNK_SPAN_LOW
	var y1 := TRUNK_SPAN_HIGH
	var centre := Vector3(best_x, (y0 + y1) * 0.5, best_z)
	for side in TRUNK_SIDES:
		var a := ring[side]
		var b := ring[(side + 1) % TRUNK_SIDES]
		for face: Array in [
				[Vector3(best_x, y1, best_z), Vector3(a.x, y1, a.y), Vector3(b.x, y1, b.y)],
				[Vector3(best_x, y0, best_z), Vector3(b.x, y0, b.y), Vector3(a.x, y0, a.y)],
				[Vector3(a.x, y0, a.y), Vector3(b.x, y0, b.y), Vector3(b.x, y1, b.y)],
				[Vector3(a.x, y0, a.y), Vector3(b.x, y1, b.y), Vector3(a.x, y1, a.y)]]:
			var p: Vector3 = face[0]
			var q: Vector3 = face[1]
			var r: Vector3 = face[2]
			# Outward winding: structural_mask counts a face up as +1, down as -1.
			if (q - p).cross(r - p).dot((p + q + r) / 3.0 - centre) < 0.0:
				prism.append_array([p, r, q])
			else:
				prism.append_array([p, q, r])
	return prism


## A mesh's triangles in glTF winding (Godot imports them clockwise, so every
## triangle's second and third corners are swapped back) and whether it is
## closed: every edge shared by exactly two triangles, corners matched to
## 6 decimals, as closed_mesh decides.
static func mesh_shape(mesh: Mesh) -> Dictionary:
	var key := mesh.get_instance_id()
	if _mesh_cache.has(key):
		return _mesh_cache[key]
	var godot_faces := mesh.get_faces()
	var faces := PackedVector3Array()
	faces.resize(godot_faces.size() / 3 * 3)
	for index in range(0, faces.size(), 3):
		faces[index] = godot_faces[index]
		faces[index + 1] = godot_faces[index + 2]
		faces[index + 2] = godot_faces[index + 1]
	var shape := {"faces": faces, "closed": closed_faces(faces)}
	_mesh_cache[key] = shape
	return shape


static func closed_faces(faces: PackedVector3Array) -> bool:
	if faces.size() < 12:
		return false
	var ids := {}
	var edges := {}
	for index in range(0, faces.size(), 3):
		var corner := PackedInt32Array()
		for offset in 3:
			var point := faces[index + offset]
			var rounded := Vector3i(roundi(point.x * 1000000.0), roundi(point.y * 1000000.0),
				roundi(point.z * 1000000.0))
			if not ids.has(rounded):
				ids[rounded] = ids.size()
			corner.append(int(ids[rounded]))
		if corner[0] == corner[1] or corner[1] == corner[2] or corner[0] == corner[2]:
			continue
		for pair in [[corner[0], corner[1]], [corner[1], corner[2]], [corner[2], corner[0]]]:
			var edge := Vector2i(mini(pair[0], pair[1]), maxi(pair[0], pair[1]))
			edges[edge] = int(edges.get(edge, 0)) + 1
	if edges.is_empty():
		return false
	for count: int in edges.values():
		if count != 2:
			return false
	return true


## Rasterises deck triangles onto the half-cells of `ground` (see ground_frame)
## and returns {half-cell index: highest upward face height at its centre} for
## the cells a deck supports, plus "sources" naming the deck of each.
static func deck_cells(ground: Dictionary, decks: Array) -> Dictionary:
	var raster := deck_tops(ground, decks)
	var top: Dictionary = raster.top
	var sources: Dictionary = raster.sources
	var columns := int(ground.columns)
	var x0 := float(ground.x0)
	var z0 := float(ground.z0)
	var supported := {}
	var named := {}
	for cell_index: int in top:
		var column := cell_index % columns
		var row := cell_index / columns
		var height := float(top[cell_index])
		if height >= terrain_at(ground, x0 + (float(column) + 0.5) * CELL,
				z0 + (float(row) + 0.5) * CELL) - DECK_TOLERANCE:
			supported[cell_index] = height
			named[cell_index] = sources[cell_index]
	return {"cells": supported, "sources": named}


## Every half-cell a deck's upward faces cover, supported by the ground or not
## (glb_reader.rasterise): {"top": {half-cell index: highest face height},
## "sources": {half-cell index: deck name}}.
static func deck_tops(ground: Dictionary, decks: Array) -> Dictionary:
	var columns := int(ground.columns)
	var rows := int(ground.rows)
	var x0 := float(ground.x0)
	var z0 := float(ground.z0)
	var upward := 1.0 / sqrt(1.0 + MAX_GRADE * MAX_GRADE) - 1e-9
	var top := {}
	var sources := {}
	for deck: Dictionary in decks:
		var triangles: PackedVector3Array = deck.triangles
		var orientation_free := bool(deck.get("either_side", false))
		for index in range(0, triangles.size() - 2, 3):
			var a := triangles[index]
			var b := triangles[index + 1]
			var c := triangles[index + 2]
			var normal := (b - a).cross(c - a)
			var length := normal.length()
			if length <= 1e-9:
				continue
			var rise := absf(normal.y) if orientation_free else normal.y
			if rise / length <= upward:
				continue
			var determinant := (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z)
			if absf(determinant) < 1e-12:
				continue
			var xa := clampi(floori((minf(a.x, minf(b.x, c.x)) - x0) / CELL), 0, columns - 1)
			var xb := clampi(floori((maxf(a.x, maxf(b.x, c.x)) - x0) / CELL), 0, columns - 1)
			var za := clampi(floori((minf(a.z, minf(b.z, c.z)) - z0) / CELL), 0, rows - 1)
			var zb := clampi(floori((maxf(a.z, maxf(b.z, c.z)) - z0) / CELL), 0, rows - 1)
			for row in range(za, zb + 1):
				var z := z0 + (float(row) + 0.5) * CELL
				for column in range(xa, xb + 1):
					var x := x0 + (float(column) + 0.5) * CELL
					var w0 := ((b.z - c.z) * (x - c.x) + (c.x - b.x) * (z - c.z)) / determinant
					var w1 := ((c.z - a.z) * (x - c.x) + (a.x - c.x) * (z - c.z)) / determinant
					if w0 < 0.0 or w1 < 0.0 or w0 + w1 > 1.0:
						continue
					var height := w0 * a.y + w1 * b.y + (1.0 - w0 - w1) * c.y
					var cell_index := row * columns + column
					if height > float(top.get(cell_index, -INF)):
						top[cell_index] = height
						sources[cell_index] = String(deck.name)
	return {"top": top, "sources": sources}


## The half-cell frame and terrain a structure test reads; plain data, so a
## worker thread can hold it.
static func ground_frame(data: Dictionary) -> Dictionary:
	var sub := maxi(roundi(float(data.tile) / CELL), 1)
	return {"heights": data.heights, "grid": data.grid, "cell": data.cell,
		"terrain_x0": data.terrain_x0, "terrain_z0": data.terrain_z0,
		"x0": data.x0, "z0": data.z0, "sub": sub,
		"columns": int(data.width) * sub, "rows": int(data.rows) * sub, "decks": {}}


static func terrain_at(ground: Dictionary, x: float, z: float) -> float:
	var heights: PackedFloat32Array = ground.heights
	var grid: Vector2i = ground.grid
	var cell := float(ground.cell)
	var fx := clampf((x - float(ground.terrain_x0)) / cell, 0.0, float(grid.x) - 1.0000001)
	var fz := clampf((z - float(ground.terrain_z0)) / cell, 0.0, float(grid.y) - 1.0000001)
	var ix := mini(floori(fx), grid.x - 2)
	var iz := mini(floori(fz), grid.y - 2)
	var u := fx - float(ix)
	var v := fz - float(iz)
	var a := heights[iz * grid.x + ix]
	var b := heights[iz * grid.x + ix + 1]
	var c := heights[(iz + 1) * grid.x + ix]
	var d := heights[(iz + 1) * grid.x + ix + 1]
	if u + v <= 1.0:
		return a + (b - a) * u + (c - a) * v
	return d + (c - d) * (1.0 - u) + (b - d) * (1.0 - v)


## What a cached result for this solid depends on: its meshes and placement,
## and the ground it stands on (terrain samples and deck cells under it).
static func solid_signature(solid: Dictionary, ground: Dictionary) -> String:
	var window := _window(solid.low, solid.high, ground)
	var parts := PackedStringArray([String(solid.signature), str(window)])
	var heights: PackedFloat32Array = ground.heights
	var grid: Vector2i = ground.grid
	var cell := float(ground.cell)
	var x_low := float(ground.x0) + float(window.x) * CELL
	var x_high := float(ground.x0) + float(window.y) * CELL
	var z_low := float(ground.z0) + float(window.z) * CELL
	var z_high := float(ground.z0) + float(window.w) * CELL
	var ia := clampi(floori((x_low - float(ground.terrain_x0)) / cell), 0, grid.x - 1)
	var ib := clampi(ceili((x_high - float(ground.terrain_x0)) / cell), 0, grid.x - 1)
	var ja := clampi(floori((z_low - float(ground.terrain_z0)) / cell), 0, grid.y - 1)
	var jb := clampi(ceili((z_high - float(ground.terrain_z0)) / cell), 0, grid.y - 1)
	var samples := PackedFloat32Array()
	for row in range(ja, jb + 1):
		samples.append_array(heights.slice(row * grid.x + ia, row * grid.x + ib + 1))
	parts.append(str(hash(samples)))
	var decks: Dictionary = ground.decks
	if not decks.is_empty():
		var columns := int(ground.columns)
		for row in range(window.z, window.w):
			for column in range(window.x, window.y):
				var cell_index := row * columns + column
				if decks.has(cell_index):
					parts.append("%d:%s" % [cell_index, str(decks[cell_index])])
	return str(hash("|".join(parts)))


## The half-cells (row * columns + column) one solid asset blocks, exactly as
## structural_mask decides them. With `enclose` (a continent-v2 placement), an
## asset with an open part that reaches the actor's height also blocks the
## ground its blocked cells wall in (export_collision.enclosed), except the
## cells `own_deck` (its Walk_ triangles) covers. Pure: reads only its
## arguments.
static func blocked_cells(parts: Array, ground: Dictionary, enclose := false,
		own_deck := PackedVector3Array()) -> PackedInt32Array:
	var columns := int(ground.columns)
	var x0 := float(ground.x0)
	var z0 := float(ground.z0)
	var decks: Dictionary = ground.decks
	var half_x := CELL * 0.5
	var half_y := (ACTOR_HEIGHT - ACTOR_FLOOR_CLEARANCE) * 0.5
	var half_z := CELL * 0.5
	var lift := (ACTOR_FLOOR_CLEARANCE + ACTOR_HEIGHT) * 0.5
	var middle := ACTOR_HEIGHT * 0.5
	var result := {}
	var open_shell := false
	for part: Dictionary in parts:
		var faces: PackedVector3Array = part.faces
		var transform: Transform3D = part.transform
		var closed := bool(part.closed)
		var count := faces.size() / 3 * 3
		if count == 0:
			continue
		var triangles := PackedVector3Array()
		triangles.resize(count)
		var low := Vector3(INF, INF, INF)
		var high := -low
		for index in count:
			var point: Vector3 = transform * faces[index]
			triangles[index] = point
			low = low.min(point)
			high = high.max(point)
		var region := _window(low, high, ground)
		var width := region.y - region.x
		var height := region.w - region.z
		if width <= 0 or height <= 0:
			continue
		var standing := PackedFloat32Array()
		standing.resize(width * height)
		var lowest := INF
		var highest := -INF
		for row in height:
			var z := z0 + (float(region.z + row) + 0.5) * CELL
			for column in width:
				var cell_index := (region.z + row) * columns + region.x + column
				var value: float = decks[cell_index] if decks.has(cell_index) else \
					terrain_at(ground, x0 + (float(region.x + column) + 0.5) * CELL, z)
				standing[row * width + column] = value
				lowest = minf(lowest, value)
				highest = maxf(highest, value)
		if high.y < lowest + ACTOR_FLOOR_CLEARANCE or low.y > highest + ACTOR_HEIGHT:
			continue
		open_shell = open_shell or not closed
		var blocked := PackedByteArray()
		blocked.resize(width * height)
		var winding := PackedInt32Array()
		if closed:
			winding.resize(width * height)
		for index in range(0, count, 3):
			var a := triangles[index]
			var b := triangles[index + 1]
			var c := triangles[index + 2]
			var t_low := a.min(b).min(c)
			var t_high := a.max(b).max(c)
			var window := _window(t_low, t_high, ground)
			if window.x >= window.y or window.z >= window.w:
				continue
			var floor_low := INF
			var floor_high := -INF
			for row in range(window.z, window.w):
				for column in range(window.x, window.y):
					var value := standing[(row - region.z) * width + column - region.x]
					floor_low = minf(floor_low, value)
					floor_high = maxf(floor_high, value)
			var test_prism := t_high.y >= floor_low + ACTOR_FLOOR_CLEARANCE and \
				t_low.y <= floor_high + ACTOR_HEIGHT
			var test_winding := closed and t_high.y > floor_low + middle
			if not test_prism and not test_winding:
				continue
			# Separating axes: the face normal and each edge crossed with each
			# unit axis, with the triangle's projection and the prism's radius.
			var axes: Array[Vector3] = []
			var spans := PackedFloat64Array()
			if test_prism:
				var edges: Array[Vector3] = [b - a, c - b, a - c]
				var candidates: Array[Vector3] = [edges[0].cross(edges[1])]
				for edge in edges:
					candidates.append(Vector3(0.0, -edge.z, edge.y))
					candidates.append(Vector3(edge.z, 0.0, -edge.x))
					candidates.append(Vector3(-edge.y, edge.x, 0.0))
				for axis in candidates:
					var ax := float(axis.x)
					var ay := float(axis.y)
					var az := float(axis.z)
					if ax * ax + ay * ay + az * az < 1e-18:
						continue
					var pa := ax * a.x + ay * a.y + az * a.z
					var pb := ax * b.x + ay * b.y + az * b.z
					var pc := ax * c.x + ay * c.y + az * c.z
					axes.append(axis)
					spans.append(minf(pa, minf(pb, pc)))
					spans.append(maxf(pa, maxf(pb, pc)))
					spans.append(absf(ax) * half_x + absf(ay) * half_y + absf(az) * half_z)
			# The winding ray: the face plane, and its XZ outline turned
			# counter-clockwise with the half-open edge rule.
			var normal_y := 0.0
			var outline: Array[Vector2] = []
			var normal := Vector3.ZERO
			if test_winding:
				normal = (b - a).cross(c - a)
				normal_y = float(normal.y)
				if absf(normal_y) >= 1e-10:
					outline = [Vector2(a.x, a.z), Vector2(b.x, b.z), Vector2(c.x, c.z)]
					var edge_a := outline[1] - outline[0]
					var edge_b := outline[2] - outline[0]
					if float(edge_a.x) * float(edge_b.y) - float(edge_a.y) * float(edge_b.x) < 0.0:
						var swap := outline[1]
						outline[1] = outline[2]
						outline[2] = swap
			var axis_count := axes.size()
			for row in range(window.z, window.w):
				var cz := z0 + (float(row) + 0.5) * CELL
				for column in range(window.x, window.y):
					var local := (row - region.z) * width + column - region.x
					var cx := x0 + (float(column) + 0.5) * CELL
					var stand := float(standing[local])
					if test_prism and blocked[local] == 0:
						var cy := stand + lift
						var overlaps := cx + half_x >= t_low.x and cx - half_x <= t_high.x and \
							cy + half_y >= t_low.y and cy - half_y <= t_high.y and \
							cz + half_z >= t_low.z and cz - half_z <= t_high.z
						var axis_index := 0
						while overlaps and axis_index < axis_count:
							var axis := axes[axis_index]
							var centre := float(axis.x) * cx + float(axis.y) * cy + float(axis.z) * cz
							var radius := spans[axis_index * 3 + 2]
							if spans[axis_index * 3] - centre > radius + 1e-9 or \
									spans[axis_index * 3 + 1] - centre < -radius - 1e-9:
								overlaps = false
							axis_index += 1
						if overlaps:
							blocked[local] = 1
					if not outline.is_empty():
						var inside := true
						for corner in 3:
							var start := outline[corner]
							var stop := outline[(corner + 1) % 3]
							var ex := float(stop.x) - float(start.x)
							var ez := float(stop.y) - float(start.y)
							var side := ex * (cz - float(start.y)) - ez * (cx - float(start.x))
							var inclusive := ez > 0.0 or (ez == 0.0 and ex < 0.0)
							if not (side > 1e-9 or (absf(side) <= 1e-9 and inclusive)):
								inside = false
								break
						if inside:
							var hit := float(a.y) - (float(normal.x) * (cx - float(a.x)) +
								float(normal.z) * (cz - float(a.z))) / normal_y
							if hit > stand + middle:
								winding[local] += 1 if normal_y > 0.0 else -1
		for local in width * height:
			if blocked[local] != 0 or (closed and winding[local] != 0):
				result[(region.z + local / width) * columns + region.x + local % width] = true
	if enclose and open_shell and not result.is_empty():
		_enclosed(result, ground, own_deck)
	return PackedInt32Array(result.keys())


## export_collision.enclosed: adds to `shell` (half-cell index -> true) the
## cells it walls in on every side, those no 4-connected way through unblocked
## cells leads out of (binary_fill_holes), less the cells `own_deck` covers.
static func _enclosed(shell: Dictionary, ground: Dictionary, own_deck: PackedVector3Array) -> void:
	var columns := int(ground.columns)
	var rows := int(ground.rows)
	var c0 := columns
	var c1 := -1
	var r0 := rows
	var r1 := -1
	for cell_index: int in shell:
		c0 = mini(c0, cell_index % columns)
		c1 = maxi(c1, cell_index % columns)
		r0 = mini(r0, cell_index / columns)
		r1 = maxi(r1, cell_index / columns)
	# One free ring round the shell's box is the way out, as the exporter's
	# window (the placement's box and a metre) leaves one.
	c0 = maxi(c0 - 1, 0)
	r0 = maxi(r0 - 1, 0)
	c1 = mini(c1 + 1, columns - 1)
	r1 = mini(r1 + 1, rows - 1)
	var width := c1 - c0 + 1
	var height := r1 - r0 + 1
	# 0 open, 1 shell, 2 reached from outside.
	var state := PackedByteArray()
	state.resize(width * height)
	for cell_index: int in shell:
		state[(cell_index / columns - r0) * width + cell_index % columns - c0] = 1
	var queue := PackedInt32Array()
	for local in width * height:
		var column := local % width
		var row := local / width
		if (column == 0 or row == 0 or column == width - 1 or row == height - 1) and state[local] == 0:
			state[local] = 2
			queue.append(local)
	var head := 0
	while head < queue.size():
		var local := queue[head]
		head += 1
		var column := local % width
		var row := local / width
		for step: Vector2i in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var x := column + step.x
			var y := row + step.y
			if x < 0 or y < 0 or x >= width or y >= height:
				continue
			var next := y * width + x
			if state[next] == 0:
				state[next] = 2
				queue.append(next)
	var deck := {}
	if not own_deck.is_empty():
		deck = deck_tops(ground, [{"name": "", "triangles": own_deck}]).top
	for local in width * height:
		if state[local] != 0:
			continue
		var cell_index := (r0 + local / width) * columns + c0 + local % width
		if not deck.has(cell_index):
			shell[cell_index] = true


## Cell bounds [x, x_end) × [z, z_end) of the half-cells whose centres lie
## within 0.25 m of the XZ box, clipped to the grid (collision_export._window).
static func _window(low: Vector3, high: Vector3, ground: Dictionary) -> Vector4i:
	var margin := 0.25
	var x0 := float(ground.x0)
	var z0 := float(ground.z0)
	var xa := maxi(0, ceili((low.x - margin - x0) / CELL - 0.5))
	var xb := mini(int(ground.columns), floori((high.x + margin - x0) / CELL - 0.5) + 1)
	var za := maxi(0, ceili((low.z - margin - z0) / CELL - 0.5))
	var zb := mini(int(ground.rows), floori((high.z + margin - z0) / CELL - 0.5) + 1)
	return Vector4i(xa, maxi(xa, xb), za, maxi(za, zb))


static func _names_ceiling(name: String) -> bool:
	var lower := name.to_lower()
	for word: String in CEILINGS:
		if word in lower:
			return true
	return false


## The nodes the exporter treats as the asset's scene roots: the source node
## when the asset names one, else the imported scene's top-level children.
static func _scene_roots(asset: Node3D) -> Array[Node]:
	var roots: Array[Node] = []
	var content: Node3D = asset.call("content_root")
	if content == null:
		return roots
	var source := String(asset.get("source_node"))
	if not source.is_empty() and source != ".":
		var named := content.find_child(source, true, false)
		if named != null:
			roots.append(named)
			return roots
	if content.get_child_count() == 0 or content is MeshInstance3D:
		roots.append(content)
		return roots
	for child in content.get_children():
		if child is Node3D:
			roots.append(child)
	return roots

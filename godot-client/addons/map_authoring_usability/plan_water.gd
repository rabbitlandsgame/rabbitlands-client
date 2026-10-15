@tool
extends RefCounted
## Read-only display of the continent plan's water (the rivers and lakes of
## _continent/diagonal-plan.json) over the open territory: the shared water the
## composer adds whether or not the territory's scene has it.
##
## A feature is claimed when this territory replaces it: a scene river or lake
## whose replaces_plan_feature_id names it, or an id in the territory's
## owned_plan_feature_ids. The scene then carries it, so only plan-only water
## is added to the live walkability estimate. Nothing here edits the plan;
## shared topology, mouths, joins and claims are the map team's.
##
## Plan coordinates are continent X, Z with the water level as the third
## value and, optionally, the half-width as the fourth; a river's "width" is a
## half-width too. The territory frame subtracts the scene's
## continent_translation.
## Drawn as an internal, ownerless node, so it is never saved or baked.

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const WATER_SCRIPT := preload("res://src/dev/map_authoring_region/water_region_control.gd")
const PLAN_PATH := "res://../eloria-assets/maps/nymara-regions/_continent/diagonal-plan.json"
const NODE_NAME := "__MapAuthoringPlanWater"
## Plan lakes that have no id, by name, as the composer identifies them
## (authoring.py NAMELESS_PUBLISHED_LAKES).
const NAMELESS_LAKES := {"Moor headwater tarn": "moor_headwater_tarn",
	"Moorwater pool": "moorwater_pool", "Mirror Lake": "mirror_lake"}
## Plan water this far outside the terrain grid is still shown (a bank or a
## lake just over the border shapes the ground at the edge).
const MARGIN := 40.0
const PLAN_ONLY_COLOR := Color(0.3, 0.78, 1.0)
const CLAIMED_COLOR := Color(0.72, 0.72, 0.78)

static var _cache := {}

var last_message := ""
var plan_path := PLAN_PATH
var _node: Node3D
var _mesh: ImmediateMesh


## The plan document, parsed once per file revision; {} when it cannot be read.
static func load_plan(path: String = PLAN_PATH) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var stamp := [FileAccess.get_modified_time(path), FileAccess.get_file_as_bytes(path).size()] \
		if not path.begins_with("res://") or FileAccess.file_exists(ProjectSettings.globalize_path(path)) \
		else []
	var cached: Dictionary = _cache.get(path, {})
	if not cached.is_empty() and cached.stamp == stamp:
		return cached.plan
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	var plan: Dictionary = parsed if parsed is Dictionary else {}
	_cache[path] = {"stamp": stamp, "plan": plan}
	return plan


## The plan's rivers and lakes near `root`'s terrain, in its local frame:
## rivers {id, name, kind "river", points (surface XYZ), halves (half widths),
## claimed, claim}; lakes {id, name, kind "lake", centre, radii, depth, claimed,
## claim}. `claim` says who claims it ("" for plan-only water).
static func features(root: Node3D, plan: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if root == null or plan.is_empty():
		return result
	var translation: Vector3 = root.get("continent_translation") \
		if root.get("continent_translation") is Vector3 else Vector3.ZERO
	var bounds := territory_bounds(root).grow(MARGIN)
	var claims := claims_of(root)
	for value: Variant in plan.get("rivers", []):
		if not value is Dictionary:
			continue
		var river: Dictionary = value
		var points := PackedVector3Array()
		var halves := PackedFloat32Array()
		var box := Rect2()
		var controls: Array = river.get("points", [])
		var samples: Array = controls if bool(river.get("authoredSampled", false)) 			else curved_points(controls)
		for point_value: Variant in samples:
			var point: Array = point_value
			if point.size() < 3:
				continue
			var local := Vector3(float(point[0]) - translation.x, float(point[2]) - translation.y,
				float(point[1]) - translation.z)
			points.append(local)
			# Plan river widths are half-widths from the centreline (landscape.py
			# water_fields), per point when the point carries a fourth value.
			halves.append(float(point[3] if point.size() > 3 else river.get("width", 3.0)))
			box = Rect2(Vector2(local.x, local.z), Vector2.ZERO) if points.size() == 1 else \
				box.expand(Vector2(local.x, local.z))
		if points.size() < 2 or not box.grow(float(river.get("width", 3.0))).intersects(bounds):
			continue
		var identity := String(river.get("id", ""))
		result.append({"id": identity, "name": String(river.get("name", identity)),
			"kind": "river", "points": points, "halves": halves,
			"claimed": claims.has(identity), "claim": String(claims.get(identity, ""))})
	for value: Variant in plan.get("lakes", []):
		if not value is Dictionary:
			continue
		var lake: Dictionary = value
		var centre_value: Array = lake.get("center", [])
		var radii_value: Array = lake.get("radii", [])
		if centre_value.size() < 2 or radii_value.size() < 2:
			continue
		var centre := Vector3(float(centre_value[0]) - translation.x,
			float(lake.get("level", 0.0)) - translation.y, float(centre_value[1]) - translation.z)
		var radii := Vector2(float(radii_value[0]), float(radii_value[1]))
		if not Rect2(Vector2(centre.x, centre.z) - radii, radii * 2.0).intersects(bounds):
			continue
		var identity := String(lake.get("id", NAMELESS_LAKES.get(String(lake.get("name", "")), "")))
		result.append({"id": identity, "name": String(lake.get("name", identity)), "kind": "lake",
			"centre": centre, "radii": radii, "angle": float(lake.get("angle", 0.0)),
			"depth": float(lake.get("depth", 0.0)),
			"claimed": not identity.is_empty() and claims.has(identity),
			"claim": String(claims.get(identity, "")) if not identity.is_empty() else ""})
	return result


## The composer's river centreline (landscape._curved_points): Catmull-Rom
## through the control points, six samples a span, with the level and any
## width interpolated linearly along each span and the last point kept.
static func curved_points(controls: Array) -> Array:
	var result: Array = []
	var count := controls.size()
	if count < 2:
		return controls.duplicate()
	for index in count - 1:
		var a: Array = controls[index]
		var b: Array = controls[index + 1]
		var before: Array = controls[index - 1] if index > 0 else _mirror(a, b)
		var after: Array = controls[index + 2] if index + 2 < count else _mirror(b, a)
		for step in 6:
			var t := float(step) / 6.0
			var sample: Array = []
			for axis in 2:
				var p0 := float(before[axis])
				var p1 := float(a[axis])
				var p2 := float(b[axis])
				var p3 := float(after[axis])
				sample.append(0.5 * (2.0 * p1 + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) *
					t * t + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t))
			for attribute in range(2, mini(a.size(), b.size())):
				sample.append(lerpf(float(a[attribute]), float(b[attribute]), t))
			result.append(sample)
	result.append(controls[count - 1])
	return result


static func _mirror(point: Array, other: Array) -> Array:
	var result: Array = []
	for index in point.size():
		result.append(float(point[index]) * 2.0 - float(other[index]) if index < other.size()
			else float(point[index]))
	return result


## Plan feature id -> who claims it in this territory.
static func claims_of(root: Node3D) -> Dictionary:
	var claims := {}
	var owned: Variant = root.get("owned_plan_feature_ids")
	if owned is PackedStringArray:
		for identity in owned as PackedStringArray:
			claims[identity] = "the territory's owned plan features"
	for container in ["Rivers", "WaterRegions"]:
		var holder := root.get_node_or_null(container)
		if holder == null:
			continue
		for child in holder.get_children():
			if child.get_script() != PATH_SCRIPT and child.get_script() != WATER_SCRIPT:
				continue
			var replaced := String(child.get("replaces_plan_feature_id")) \
				if child.get("replaces_plan_feature_id") != null else ""
			if not replaced.is_empty():
				claims[replaced] = String(child.name)
	return claims


## The terrain grid's X/Z extent in the territory frame.
static func territory_bounds(root: Node3D) -> Rect2:
	var terrain := Probe.region_terrain(root)
	if terrain == null:
		return Rect2()
	var origin: Vector2 = terrain.get("origin")
	var grid: Vector2i = terrain.get("grid_size")
	var cell := float(terrain.get("cell_metres"))
	var to_root: Transform3D = root.global_transform.affine_inverse() * terrain.global_transform
	var box := Rect2()
	var first := true
	for corner: Vector2 in [origin, origin + Vector2(float(grid.x - 1), 0.0) * cell,
			origin + Vector2(0.0, float(grid.y - 1)) * cell, origin + Vector2(grid - Vector2i.ONE) * cell]:
		var point: Vector3 = to_root * Vector3(corner.x, 0.0, corner.y)
		box = Rect2(Vector2(point.x, point.z), Vector2.ZERO) if first else box.expand(Vector2(point.x, point.z))
		first = false
	return box


## Draws the plan water on `root`. Returns whether anything is shown.
func show_on(root: Node3D) -> bool:
	release()
	if root == null or Probe.region_terrain(root) == null:
		last_message = "Open a territory with region terrain to see the plan's water."
		return false
	var plan := load_plan(plan_path)
	if plan.is_empty():
		last_message = "The continent plan (%s) could not be read." % plan_path
		return false
	var found := features(root, plan)
	_node = Node3D.new()
	_node.name = NODE_NAME
	_node.top_level = true
	root.add_child(_node, false, Node.INTERNAL_MODE_BACK)
	_node.global_transform = root.global_transform
	_mesh = ImmediateMesh.new()
	var lines := MeshInstance3D.new()
	lines.mesh = _mesh
	lines.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.no_depth_test = true
	lines.material_override = material
	_node.add_child(lines)
	var plan_only := 0
	if not found.is_empty():
		_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
		for feature in found:
			var color := CLAIMED_COLOR if bool(feature.claimed) else PLAN_ONLY_COLOR
			plan_only += 0 if bool(feature.claimed) else 1
			if String(feature.kind) == "river":
				_draw_river(feature, color)
			else:
				_draw_lake(feature, color)
			_label(feature, color)
		_mesh.surface_end()
	var rivers := found.filter(func(feature: Dictionary) -> bool: return feature.kind == "river").size()
	last_message = ("Continent plan water here: %d river%s and %d lake%s, %d plan-only (blue) and " +
		"%d claimed by this territory (grey). Read-only: the plan is the map team's.") % [
		rivers, "" if rivers == 1 else "s", found.size() - rivers,
		"" if found.size() - rivers == 1 else "s", plan_only, found.size() - plan_only]
	if found.is_empty():
		last_message = "The continent plan has no rivers or lakes near this territory."
	return true


func is_shown() -> bool:
	return _node != null and is_instance_valid(_node)


func node() -> Node3D:
	return _node if is_shown() else null


func release() -> void:
	if _node != null and is_instance_valid(_node):
		if _node.get_parent() != null:
			_node.get_parent().remove_child(_node)
		_node.queue_free()
	_node = null
	_mesh = null


func _draw_river(feature: Dictionary, color: Color) -> void:
	var points: PackedVector3Array = feature.points
	var halves: PackedFloat32Array = feature.halves
	for index in points.size() - 1:
		var a := points[index]
		var b := points[index + 1]
		var along := Vector2(b.x - a.x, b.z - a.z)
		if along.length_squared() < 0.0001:
			continue
		var side := Vector2(-along.y, along.x).normalized()
		_line(a, b, color)
		for sign: float in [-1.0, 1.0]:
			var offset_a := side * halves[index] * sign
			var offset_b := side * halves[index + 1] * sign
			_line(a + Vector3(offset_a.x, 0.0, offset_a.y), b + Vector3(offset_b.x, 0.0, offset_b.y),
				Color(color, 0.7))


func _draw_lake(feature: Dictionary, color: Color) -> void:
	var centre: Vector3 = feature.centre
	var radii: Vector2 = feature.radii
	var turn := float(feature.get("angle", 0.0))
	var segments := 64
	for index in segments:
		var a := TAU * float(index) / float(segments)
		var b := TAU * float(index + 1) / float(segments)
		var p := Vector2(cos(a) * radii.x, sin(a) * radii.y).rotated(turn)
		var q := Vector2(cos(b) * radii.x, sin(b) * radii.y).rotated(turn)
		_line(centre + Vector3(p.x, 0.0, p.y), centre + Vector3(q.x, 0.0, q.y), color)


func _line(a: Vector3, b: Vector3, color: Color) -> void:
	var lift := Vector3(0.0, 0.15, 0.0)
	_mesh.surface_set_color(color)
	_mesh.surface_add_vertex(a + lift)
	_mesh.surface_set_color(color)
	_mesh.surface_add_vertex(b + lift)


func _label(feature: Dictionary, color: Color) -> void:
	var label := Label3D.new()
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.fixed_size = true
	label.pixel_size = 0.0012
	label.modulate = color
	label.outline_size = 8
	label.text = "%s (%s)" % [String(feature.name), "claimed by %s" % String(feature.claim)
		if bool(feature.claimed) else "plan only, map team"]
	var points: Variant = feature.get("points")
	var anchor: Vector3 = (points as PackedVector3Array)[(points as PackedVector3Array).size() / 2] \
		if points is PackedVector3Array else feature.centre
	label.position = anchor + Vector3(0.0, 3.0, 0.0)
	_node.add_child(label)

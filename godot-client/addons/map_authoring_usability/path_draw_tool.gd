@tool
extends RefCounted

const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
## Click-to-draw roads and rivers for authored territories.
##
## Each click on the terrain adds a point; the draft is draped over the ground
## with its full width while drawing. Finishing creates an ordinary
## MapAuthoringRegionPath under Roads or Rivers, the same control the imported
## routes use. The new path gets:
## - a fresh path id and no route or plan-feature replacement (the bake only
##   suppresses a composer route when a path names it exactly);
## - Shape terrain on for roads, as the docs specify for new roads;
## - the territory's own road surface (rivers use the default water);
## - point heights taken from the ground under each click. A road grades the
##   ground between them; a river's heights are its water surface, and the
##   river effect carves the channel below;
## - for rivers, the channel properties the continent composer requires
##   (channelDepth, valleyWidth, bankHeight), copied in proportion from a river
##   the territory already has, else the map team's defaults.
## It is one undo step, and afterwards Godot's normal Path3D tools edit it.
##
## Starting on either end of an existing road (or river) extends that path
## instead: the new points are added to it as one undo step, keeping its id,
## surface and settings. Ctrl+click on an end starts a separate path there.
## Paths the map team owns are never extended: ones that replace a composer
## route or a planned water feature, ones the territory lists as owned, and
## ends that sit on the ownership border (seam tails).

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const NODE_NAME := "__MapAuthoringPathDraft"
const ENDPOINT_SNAP := 2.5
const DEFAULT_WIDTHS := {"road": 4.0, "river": 6.0}
## River channel defaults when the territory has no river to copy: the map
## team's proposed channelDepth and terrainFeather; a bank height and a valley
## of about six widths (never under 30 m) as the plan's own small rivers have.
const RIVER_DEFAULTS := {"channelDepth": 1.45, "terrainFeather": 5.5, "bankHeight": 2.5,
	"bankShelfWidth": 0.0, "cutsRelief": false, "terrainConform": false}
const RIVER_VALLEY_PER_WIDTH := 6.0
const RIVER_MIN_VALLEY := 30.0
## An end this close to the ownership border is a seam tail.
const SEAM_DISTANCE := 4.0
const COLORS := {"road": Color(1.0, 0.82, 0.5), "river": Color(0.35, 0.65, 1.0)}

var kind := ""
var width := 4.0
var points: Array[Vector3] = []
var last_message := ""
var _root: Node3D
var _hover: Variant = null
var _node: MeshInstance3D
var _mesh: ImmediateMesh
## The path being extended (null for a new one) and whether at its first point.
var _extending: Node3D
var _polygon: Array[PackedVector2Array] = []
var _extend_at_start := false


func is_active() -> bool:
	return not kind.is_empty() and _root != null and is_instance_valid(_root)


## Starts drawing a "road" or "river" on `root`. Returns false with a message
## when the scene cannot hold one.
func start(root: Node3D, path_kind: String,
		ownership_polygon: Variant = PackedVector2Array()) -> bool:
	cancel()
	_polygon = GEOMETRY.polygons(ownership_polygon)
	if root == null or Probe.region_terrain(root) == null:
		last_message = "Open a territory with region terrain to draw %ss." % path_kind
		return false
	var container_name := "Roads" if path_kind == "road" else "Rivers"
	if root.get_node_or_null(container_name) == null:
		last_message = "This scene has no %s container." % container_name
		return false
	kind = path_kind
	width = DEFAULT_WIDTHS.get(path_kind, 4.0)
	_root = root
	last_message = "Click the terrain to lay out the %s." % kind
	_redraw()
	return true


func cancel() -> void:
	kind = ""
	points.clear()
	_hover = null
	_extending = null
	_extend_at_start = false
	if _node != null and is_instance_valid(_node):
		if _node.get_parent() != null:
			_node.get_parent().remove_child(_node)
		_node.queue_free()
	_node = null
	_root = null


## Input while drawing. Returns an EditorPlugin.AFTER_GUI_INPUT_* value.
func handle_input(camera: Camera3D, event: InputEvent, undo_redo: EditorUndoRedoManager) -> int:
	if not is_active():
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventMouseMotion:
		_hover = _ground_point(camera, (event as InputEventMouseMotion).position)
		_redraw()
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventKey and event.pressed:
		var key := event as InputEventKey
		if key.keycode == KEY_ESCAPE and not key.echo:
			cancel()
			last_message = "Path discarded."
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if key.keycode in [KEY_ENTER, KEY_KP_ENTER] and not key.echo:
			finish(undo_redo)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if key.keycode == KEY_BACKSPACE:
			if not points.is_empty():
				points.pop_back()
				_redraw()
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if Settings.matches("path_narrower", key) or Settings.matches("path_wider", key):
			var factor := 1.05 if key.shift_pressed else 1.25
			width = clampf(width * (1.0 / factor if Settings.matches("path_narrower", key)
				else factor), MapAuthoringWidthPath.MIN_WIDTH, MapAuthoringWidthPath.MAX_WIDTH)
			_redraw()
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if Settings.matches("toggle_snap", key) and not key.echo:
			Settings.set_value("placement/snap_to_grid",
				not bool(Settings.value("placement/snap_to_grid")))
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		return EditorPlugin.AFTER_GUI_INPUT_PASS
	if event is InputEventMouseButton and event.pressed:
		var button := event as InputEventMouseButton
		if button.button_index == MOUSE_BUTTON_RIGHT:
			finish(undo_redo)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if button.button_index != MOUSE_BUTTON_LEFT or button.alt_pressed:
			return EditorPlugin.AFTER_GUI_INPUT_PASS
		if button.double_click:
			finish(undo_redo)
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		var point: Variant = _ground_point(camera, button.position)
		if point == null:
			last_message = "That click missed the terrain."
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		if points.is_empty() and not button.ctrl_pressed and begin_extension(point as Vector3):
			return EditorPlugin.AFTER_GUI_INPUT_STOP
		add_point(point as Vector3)
		return EditorPlugin.AFTER_GUI_INPUT_STOP
	return EditorPlugin.AFTER_GUI_INPUT_PASS


func add_point(world: Vector3) -> void:
	if not points.is_empty() and points[points.size() - 1].distance_to(world) < 0.25:
		return
	points.append(world)
	if _extending != null:
		last_message = "Extending %s: %d new point%s. Double-click, Enter or right-click finishes." % [
			String(_extending.get("path_id")), points.size() - 1, "" if points.size() == 2 else "s"]
	else:
		last_message = "%d point%s. Double-click, Enter or right-click finishes." % [points.size(),
			"" if points.size() == 1 else "s"]
	_redraw()


## When `world` is on the first or last point of a path of the kind being
## drawn, continues that path from there. Returns whether it did.
func begin_extension(world: Vector3) -> bool:
	var end := endpoint_at(world)
	if end.is_empty():
		return false
	var reason := ownership_reason(end.path, end.position)
	if not reason.is_empty():
		# The click is used up: the path is left alone and nothing is drawn.
		last_message = "%s is not extended here: %s Ctrl+click that end to start a separate %s." % [
			String(end.path.get("path_id")), reason, kind]
		_redraw()
		return true
	_extending = end.path
	_extend_at_start = int(end.index) == 0
	width = float(_extending.get("default_width"))
	points = [end.position as Vector3]
	last_message = ("Extending %s from its %s. Click to add points; Ctrl+click an end to " +
		"start a separate %s there instead.") % [String(_extending.get("path_id")),
		"start" if _extend_at_start else "end", kind]
	if not bool((_extending.get("properties") as Dictionary).get("terrainConform", true)):
		last_message += " It follows the ground without shaping it (Shape terrain off), and so will the new part."
	_redraw()
	return true


## Why the map team owns this path end (so it must not be extended), or "".
func ownership_reason(path: Node, end_world: Vector3) -> String:
	var route := String(path.get("replaces_route_id"))
	if not route.is_empty():
		return "it replaces the composer route %s, which the map team changes." % route
	var feature := String(path.get("replaces_plan_feature_id"))
	if not feature.is_empty():
		return "it replaces the planned water feature %s, which the map team changes." % feature
	var identity := String(path.get("path_id"))
	for field: String in ["owned_route_ids", "owned_plan_feature_ids"]:
		var owned: Variant = _root.get(field)
		if owned is PackedStringArray and identity in (owned as PackedStringArray):
			return "the territory lists it among its owned routes and water."
	var joins := String((path.get("properties") as Dictionary).get("joins", ""))
	if not joins.is_empty():
		return "it joins %s, and shared water topology is the map team's." % joins
	if not _polygon.is_empty():
		var local: Vector3 = _root.global_transform.affine_inverse() * end_world
		var point := Vector2(local.x, local.z)
		var nearest := GEOMETRY.edge_distance(point, _polygon)
		if nearest <= SEAM_DISTANCE or not GEOMETRY.contains(point, _polygon):
			return "that end is a seam tail on the territory border, which the map team changes."
	return ""


## The channel properties a new river needs: copied in proportion from the
## territory's first existing river, else RIVER_DEFAULTS.
static func river_properties(root: Node, identity: String, river_width: float) -> Dictionary:
	var result := RIVER_DEFAULTS.duplicate()
	result["valleyWidth"] = maxf(RIVER_MIN_VALLEY, snappedf(river_width * RIVER_VALLEY_PER_WIDTH, 0.5))
	var container := root.get_node_or_null("Rivers")
	if container != null:
		for child in container.get_children():
			if child.get_script() != PATH_SCRIPT or String(child.get("kind")) != "river":
				continue
			var template: Dictionary = child.get("properties")
			if not (template.has("channelDepth") and template.has("valleyWidth") and
					template.has("bankHeight")):
				continue
			for field: String in ["channelDepth", "bankHeight", "bankShelfWidth", "cutsRelief",
					"terrainFeather", "terrainConform"]:
				if template.has(field):
					result[field] = template[field]
			var template_width := maxf(float(child.get("default_width")), 0.5)
			result["valleyWidth"] = maxf(RIVER_MIN_VALLEY, snappedf(float(template.valleyWidth) *
				river_width / template_width, 0.5))
			break
	result["name"] = identity
	result["joins"] = ""
	return result


func extending() -> Node3D:
	return _extending


## The end (first or last point) of a same-kind path within ENDPOINT_SNAP of
## `world`: {path, index, position}, or empty.
func endpoint_at(world: Vector3) -> Dictionary:
	var container := _root.get_node_or_null("Roads" if kind == "road" else "Rivers")
	if container == null:
		return {}
	var best := {}
	var best_distance := ENDPOINT_SNAP
	for child in container.get_children():
		if child.get_script() != PATH_SCRIPT or (child as Path3D).curve == null or \
				String(child.get("kind")) != kind:
			continue
		var curve := (child as Path3D).curve
		if curve.point_count < 2 or curve.closed:
			continue
		for index: int in [0, curve.point_count - 1]:
			var candidate: Vector3 = (child as Node3D).global_transform * curve.get_point_position(index)
			var distance := Vector2(candidate.x - world.x, candidate.z - world.z).length()
			if distance < best_distance:
				best_distance = distance
				best = {"path": child, "index": index, "position": candidate}
	return best


func length() -> float:
	var total := 0.0
	var all := points.duplicate()
	if _hover is Vector3:
		all.append(_hover)
	for index in range(1, all.size()):
		total += Vector2(all[index].x - all[index - 1].x, all[index].z - all[index - 1].z).length()
	return total


## Creates the path (one undo step) and stops drawing. Returns the new node, or
## null when fewer than two points were placed.
func finish(undo_redo: EditorUndoRedoManager) -> Node3D:
	if not is_active():
		return null
	if points.size() < 2:
		var drawn := kind
		cancel()
		last_message = "A %s needs at least two points; nothing was added." % drawn
		return null
	if _extending != null:
		return _finish_extension(undo_redo)
	var root := _root
	var container := root.get_node("Roads" if kind == "road" else "Rivers") as Node3D
	var path: Node3D = PATH_SCRIPT.new()
	var identity := fresh_path_id(root, kind)
	path.name = identity
	path.set("path_id", identity)
	path.set("kind", kind)
	path.set("routing_role", "required" if kind == "road" else "decorative")
	path.set("properties", {"terrainConform": true, "terrainFeather": 2} if kind == "road"
		else river_properties(root, identity, width))
	path.set("default_width", width)
	var surface: Resource = template_surface(root, kind)
	if surface != null:
		path.set("surface", surface)
	var curve := Curve3D.new()
	var to_container := container.global_transform.affine_inverse()
	for point in points:
		curve.add_point(to_container * point)
	(path as Path3D).curve = curve
	var count := points.size()
	var drawn_kind := kind
	undo_redo.create_action("Draw %s %s (%d points)" % [drawn_kind, identity, count],
		UndoRedo.MERGE_DISABLE, root)
	undo_redo.add_do_method(container, &"add_child", path, true)
	undo_redo.add_do_method(path, &"set_owner", root)
	undo_redo.add_do_reference(path)
	undo_redo.add_undo_method(container, &"remove_child", path)
	undo_redo.commit_action()
	cancel()
	last_message = ("Added %s %s with %d points. Edit its points with the Path3D tools; " +
		"Default Width and Shape terrain are in the Inspector.") % [drawn_kind, identity, count]
	return path


func _finish_extension(undo_redo: EditorUndoRedoManager) -> Node3D:
	var path := _extending
	var curve := (path as Path3D).curve
	var to_path := path.global_transform.affine_inverse()
	var added := points.slice(1)
	var at_start := _extend_at_start
	var identity := String(path.get("path_id"))
	var before := curve.point_count
	undo_redo.create_action("Extend %s %s by %d point%s" % [kind, identity, added.size(),
		"" if added.size() == 1 else "s"], UndoRedo.MERGE_DISABLE, _root)
	for point: Vector3 in added:
		if at_start:
			undo_redo.add_do_method(curve, &"add_point", to_path * point, Vector3.ZERO,
				Vector3.ZERO, 0)
		else:
			undo_redo.add_do_method(curve, &"add_point", to_path * point)
	for index in added.size():
		undo_redo.add_undo_method(curve, &"remove_point",
			0 if at_start else before + added.size() - 1 - index)
	undo_redo.commit_action()
	cancel()
	last_message = "Extended %s by %d point%s at its %s." % [identity, added.size(),
		"" if added.size() == 1 else "s", "start" if at_start else "end"]
	return path


## `road-NN` / `river-NN`, unique among the territory's paths.
static func fresh_path_id(root: Node, path_kind: String) -> String:
	var used := {}
	for container_name in ["Roads", "Rivers"]:
		var container := root.get_node_or_null(container_name)
		if container == null:
			continue
		for child in container.get_children():
			if child.get_script() == PATH_SCRIPT:
				used[String(child.get("path_id"))] = true
				used[String(child.name)] = true
	var index := 1
	var candidate := "%s-%02d" % [path_kind, index]
	while used.has(candidate):
		index += 1
		candidate = "%s-%02d" % [path_kind, index]
	return candidate


## The surface an existing path of this kind uses (a shared .tres), else the
## territory's worn-earth road surface, else a new Worn earth road surface from
## the same factory the bake validates against. Rivers without a template use
## the default water (null).
static func template_surface(root: Node, path_kind: String) -> Resource:
	var container := root.get_node_or_null("Roads" if path_kind == "road" else "Rivers")
	if container != null:
		for child in container.get_children():
			if child.get_script() == PATH_SCRIPT and child.get("surface") != null:
				return child.get("surface")
	if path_kind == "road":
		var fallback := "res://world_authoring/regions/%s/surfaces/worn-earth-road.tres" % \
			String(root.get("region_id"))
		if ResourceLoader.exists(fallback):
			return load(fallback)
		return MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.WORN_EARTH, true)
	return null


func hint_lines() -> PackedStringArray:
	if not is_active():
		return PackedStringArray()
	return PackedStringArray([
		("Extending %s  ·  " % String(_extending.get("path_id")) if _extending != null else "") +
		"Drawing %s  ·  %d point%s  ·  width %.1f m  ·  %.0f m long%s" % [kind, points.size(),
			"" if points.size() == 1 else "s", width, length(),
			"  ·  snap %s m" % str(Settings.value("grid/step")) \
				if bool(Settings.value("placement/snap_to_grid")) else ""],
		("Click: add point  ·  Double-click / Enter / right-click: finish  ·  Backspace: " +
			"remove point  ·  Esc: discard  ·  %s/%s: width  ·  %s: snap") % [
			Settings.shortcut_text("path_narrower"), Settings.shortcut_text("path_wider"),
			Settings.shortcut_text("toggle_snap")],
	])


func _ground_point(camera: Camera3D, screen: Vector2) -> Variant:
	var hit: Variant = Probe.ray_hit(_root, camera.project_ray_origin(screen),
		camera.project_ray_normal(screen), 4096.0)
	if not hit is Vector3:
		return null
	var point := hit as Vector3
	var snapped := _endpoint_snap(point)
	if snapped != null:
		return snapped
	if bool(Settings.value("placement/snap_to_grid")):
		var step := float(Settings.value("grid/step"))
		var local: Vector3 = _root.global_transform.affine_inverse() * point
		local.x = roundf(local.x / step) * step
		local.z = roundf(local.z / step) * step
		point = _root.global_transform * local
	var height := Probe.height_at(_root, point)
	return Vector3(point.x, height if not is_nan(height) else point.y, point.z)


## Joins cleanly onto an existing path: a click near another path's end or
## point lands exactly on it.
func _endpoint_snap(point: Vector3) -> Variant:
	var best: Variant = null
	var best_distance := ENDPOINT_SNAP
	for container_name in ["Roads", "Rivers"]:
		var container := _root.get_node_or_null(container_name)
		if container == null:
			continue
		for child in container.get_children():
			if child.get_script() != PATH_SCRIPT or (child as Path3D).curve == null:
				continue
			var curve := (child as Path3D).curve
			for index in curve.point_count:
				var candidate: Vector3 = (child as Node3D).global_transform * curve.get_point_position(index)
				var distance := Vector2(candidate.x - point.x, candidate.z - point.z).length()
				if distance < best_distance:
					best_distance = distance
					best = candidate
	return best


func _redraw() -> void:
	if not is_active():
		return
	if _node == null or not is_instance_valid(_node):
		_mesh = ImmediateMesh.new()
		_node = MeshInstance3D.new()
		_node.name = NODE_NAME
		_node.mesh = _mesh
		_node.top_level = true
		_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.vertex_color_use_as_albedo = true
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.no_depth_test = true
		_node.material_override = material
		_root.add_child(_node, false, Node.INTERNAL_MODE_BACK)
		_node.global_transform = Transform3D.IDENTITY
	_mesh.clear_surfaces()
	var all: Array[Vector3] = points.duplicate()
	if _hover is Vector3:
		all.append(_hover as Vector3)
	if all.is_empty():
		return
	var color: Color = COLORS.get(kind, Color.WHITE)
	_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for index in all.size():
		_cross(all[index], 0.4, color if index < points.size() else Color(color, 0.6))
	for index in range(1, all.size()):
		var fade := 1.0 if index < points.size() else 0.55
		_draped(all[index - 1], all[index], 0.0, Color(color, fade))
		_draped(all[index - 1], all[index], width * 0.5, Color(color, 0.7 * fade))
		_draped(all[index - 1], all[index], -width * 0.5, Color(color, 0.7 * fade))
	_mesh.surface_end()


func _draped(a: Vector3, b: Vector3, offset: float, color: Color) -> void:
	var flat := Vector2(b.x - a.x, b.z - a.z)
	if flat.length_squared() < 0.0001:
		return
	var side := Vector2(-flat.y, flat.x).normalized() * offset
	var steps := clampi(ceili(flat.length() / 1.5), 1, 200)
	var previous := Vector3.INF
	for step in steps + 1:
		var t := float(step) / float(steps)
		var x := lerpf(a.x, b.x, t) + side.x
		var z := lerpf(a.z, b.z, t) + side.y
		var ground := Probe.height_at(_root, Vector3(x, 0.0, z))
		var y := (ground if not is_nan(ground) else lerpf(a.y, b.y, t)) + 0.12
		var point := Vector3(x, y, z)
		if previous.is_finite():
			_mesh.surface_set_color(color)
			_mesh.surface_add_vertex(previous)
			_mesh.surface_set_color(color)
			_mesh.surface_add_vertex(point)
		previous = point


func _cross(point: Vector3, size: float, color: Color) -> void:
	for axis: Vector3 in [Vector3(size, 0, 0), Vector3(0, 0, size), Vector3(0, size * 2.0, 0)]:
		_mesh.surface_set_color(color)
		_mesh.surface_add_vertex(point - axis * (0.0 if axis.y > 0.0 else 1.0) + Vector3.UP * 0.12)
		_mesh.surface_set_color(color)
		_mesh.surface_add_vertex(point + axis + Vector3.UP * 0.12)

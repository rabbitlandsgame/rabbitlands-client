@tool
extends RefCounted
## "Low spec" view for big territories on modest machines:
## - the 3D view renders at half resolution (the editor's own View option),
## - placed assets, scenery and generated preview meshes farther than a set
##   distance from the camera are not drawn,
## - the editor's frame time readout is shown.
##
## Distance culling goes straight to the RenderingServer, so no node property
## changes and nothing is saved; turning the mode off restores each mesh's own
## visibility range. Meshes added later are picked up by `refresh`.

const CULLED_CONTAINERS := ["AuthoredAssets", "AuthoredScenery", "GeneratedPreview"]
const HALF_RESOLUTION_ID := 14
const FRAME_TIME_ID := 21

var active := false
var distance := 200.0
var _root: Node3D
var _applied := {}
var _signature := -1
## The View menu states before the mode turned them on, restored when it ends.
var _previous_options := {}


## Turns the mode on or off for `root`; returns the number of culled meshes.
func set_active(base: Control, root: Node3D, on: bool, far_metres: float) -> int:
	if on == active and root == _root and is_equal_approx(far_metres, distance):
		return _applied.size()
	restore()
	var was_active := active
	active = on
	distance = far_metres
	for id: int in [HALF_RESOLUTION_ID, FRAME_TIME_ID]:
		if on and not was_active:
			_previous_options[id] = view_option(base, id)
		if on:
			_set_view_option(base, id, true)
		elif was_active:
			_set_view_option(base, id, bool(_previous_options.get(id, false)))
	if on and root != null:
		_root = root
		refresh(true)
	return _applied.size()


## Picks up meshes added since the last call (cheap when nothing changed).
func refresh(force: bool = false) -> void:
	if not active or _root == null or not is_instance_valid(_root):
		return
	var meshes := _meshes(_root)
	if not force and meshes.size() == _signature:
		return
	_signature = meshes.size()
	for mesh in meshes:
		var key := mesh.get_instance_id()
		if _applied.has(key):
			continue
		RenderingServer.instance_geometry_set_visibility_range(mesh.get_instance(), 0.0,
			distance, 0.0, 0.0, RenderingServer.VISIBILITY_RANGE_FADE_DISABLED)
		_applied[key] = true


## Gives every culled mesh its own visibility range back.
func restore() -> void:
	for key: int in _applied:
		var mesh := instance_from_id(key) as GeometryInstance3D
		if mesh == null or not is_instance_valid(mesh):
			continue
		RenderingServer.instance_geometry_set_visibility_range(mesh.get_instance(),
			mesh.visibility_range_begin, mesh.visibility_range_end,
			mesh.visibility_range_begin_margin, mesh.visibility_range_end_margin,
			mesh.visibility_range_fade_mode as RenderingServer.VisibilityRangeFadeMode)
	_applied.clear()
	_signature = -1
	_root = null


func culled_count() -> int:
	return _applied.size()


## Whether the first 3D viewport's View menu has `id` checked.
static func view_option(base: Control, id: int) -> bool:
	for popup in _view_menus(base, id):
		return popup.is_item_checked(popup.get_item_index(id))
	return false


static func _set_view_option(base: Control, id: int, on: bool) -> void:
	if base == null:
		return
	for popup in _view_menus(base, id):
		if popup.is_item_checked(popup.get_item_index(id)) != on:
			popup.id_pressed.emit(id)


## The View menus of the 3D viewports (identified by their Half Resolution and
## View Frame Time items, whose ids are fixed in Node3DEditorViewport).
static func _view_menus(base: Control, id: int) -> Array[PopupMenu]:
	var result: Array[PopupMenu] = []
	if base == null:
		return result
	var wanted := "Half Resolution" if id == HALF_RESOLUTION_ID else "View Frame Time"
	for node in base.find_children("*", "PopupMenu", true, false):
		var popup := node as PopupMenu
		var index := popup.get_item_index(id)
		if index >= 0 and popup.is_item_checkable(index) and popup.get_item_text(index) == wanted:
			result.append(popup)
	return result


static func _meshes(root: Node3D) -> Array[GeometryInstance3D]:
	var result: Array[GeometryInstance3D] = []
	for container_name: String in CULLED_CONTAINERS:
		var container := root.get_node_or_null(NodePath(container_name))
		if container == null:
			continue
		for node in container.find_children("*", "GeometryInstance3D", true, false):
			result.append(node as GeometryInstance3D)
	return result

extends RefCounted
## Whether any overhead text could be drawn this frame, so WorldTextOverlay
## renders its separate pass only while there is text to draw.
##
## The text pass is a second camera over the whole shared world. With no label
## on screen it still culled the scenario, cleared and resolved a native-size
## target and blended it over the frame - every frame, with nameplates off or
## nobody near. This keeps the answer current without walking the world: it
## follows every node on the text layer (world_label_style.gd RENDER_LAYER) as
## it enters and leaves the tree, and every change of its visibility in the
## tree, which is what the renderer draws from. Names, bars and markers are
## hidden by their owners rather than faded out by the renderer, so a count of
## the visible ones is exact; only labels with a visibility range (map and
## object titles) need a distance, and those are checked against the camera
## when nothing else is showing.
##
## It errs one way only: a label it counts may still be off screen, so the
## pass can render with nothing in view, but a label that can be drawn is
## never left out - except that a ranged label moved into range faster than
## LABEL_SPEED, or given a longer range, while nothing else shows is drawn up
## to HOLD_MSEC late. A node is classified as it enters the tree, so text must
## be on the layer by then; every builder of overhead text sets the layer
## before `add_child`.

const LabelStyle := preload("res://src/ui/world_label_style.gd")
## Metres past a label's visibility range that still count as in range. Godot
## measures from the centre of the label's bounds, which sits a little above
## or beside its origin.
const RANGE_SLACK := 4.0
## A scan that found every ranged label out of range holds while the camera's
## movement plus this many metres a second - faster than anything carries a
## label - cannot have closed the smallest gap, and for at most HOLD_MSEC, so
## a label set down in range is drawn that soon. A map of ranged resource and
## entrance titles otherwise cost a distance test each per frame (0.3 us each
## measured, 160 us at 500 titles) whenever nothing else was showing.
const LABEL_SPEED := 30.0
const HOLD_MSEC := 200

var _tree: SceneTree
var _world: World3D
## Instance id -> [node, visible in tree, has a visibility range,
## visibility callable, exit callable].
var _tracked: Dictionary = {}
## Visible text with no visibility range: always counts.
var _unbounded := 0
## Visible text with a visibility range, by instance id: counts when near.
var _bounded: Dictionary = {}
## The last scan that found no ranged label in range: where the camera was,
## when, and how far the nearest label was outside its range. 0 means rescan.
var _clear_at := Vector3.ZERO
var _clear_msec := 0
var _clear_gap := 0.0

## Starts following the text layer of `world` in `tree`, including any text
## already there.
func watch(tree: SceneTree, world: World3D) -> void:
	stop()
	if tree == null or world == null:
		return
	_tree = tree
	_world = world
	_tree.node_added.connect(_on_node_added)
	for node: Node in _tree.root.find_children("*", "GeometryInstance3D", true, false):
		_on_node_added(node)

func stop() -> void:
	if _tree != null and _tree.node_added.is_connected(_on_node_added):
		_tree.node_added.disconnect(_on_node_added)
	for id: int in _tracked.keys():
		_forget(id)
	_bounded.clear()
	_unbounded = 0
	_clear_gap = 0.0
	_tree = null
	_world = null

func watching() -> bool:
	return _tree != null

## How many text nodes are followed, visible or not.
func tracked() -> int:
	return _tracked.size()

## Whether a text node may be drawn by a camera at `camera_position`.
func any_drawable(camera_position: Vector3) -> bool:
	if _unbounded > 0:
		return true
	if _bounded.is_empty():
		return false
	var now := Time.get_ticks_msec()
	if now - _clear_msec < HOLD_MSEC and camera_position.distance_to(_clear_at) \
			+ (now - _clear_msec) * 0.001 * LABEL_SPEED < _clear_gap:
		return false
	var gap := INF
	for id: int in _bounded:
		var node := _bounded[id] as GeometryInstance3D
		var reach: float = node.visibility_range_end
		# A range removed after the label arrived leaves it always in range.
		if reach <= 0.0:
			_clear_gap = 0.0
			return true
		reach += absf(node.visibility_range_end_margin) + RANGE_SLACK
		var distance := camera_position.distance_to(node.global_position)
		if distance <= reach:
			_clear_gap = 0.0
			return true
		gap = minf(gap, distance - reach)
	_clear_at = camera_position
	_clear_msec = now
	_clear_gap = gap
	return false

func _on_node_added(node: Node) -> void:
	var geometry := node as GeometryInstance3D
	if geometry == null or (geometry.layers & LabelStyle.RENDER_LAYER) == 0 \
			or geometry.get_world_3d() != _world:
		return
	var id := geometry.get_instance_id()
	if _tracked.has(id):
		return
	var changed := _on_visibility_changed.bind(id)
	var exiting := _forget.bind(id)
	_tracked[id] = [geometry, false, geometry.visibility_range_end > 0.0, changed, exiting]
	geometry.visibility_changed.connect(changed)
	geometry.tree_exiting.connect(exiting)
	_on_visibility_changed(id)

func _on_visibility_changed(id: int) -> void:
	var entry: Array = _tracked.get(id, [])
	if not entry.is_empty():
		_count(id, entry, (entry[0] as Node3D).is_visible_in_tree())

## Stops following a node: it is leaving the tree (it is followed again if it
## comes back) or the watch is ending.
func _forget(id: int) -> void:
	var entry: Array = _tracked.get(id, [])
	if entry.is_empty():
		return
	_count(id, entry, false)
	var node: Variant = entry[0]
	if is_instance_valid(node):
		var geometry := node as GeometryInstance3D
		if geometry.visibility_changed.is_connected(entry[3]):
			geometry.visibility_changed.disconnect(entry[3])
		if geometry.tree_exiting.is_connected(entry[4]):
			geometry.tree_exiting.disconnect(entry[4])
	_tracked.erase(id)

func _count(id: int, entry: Array, visible: bool) -> void:
	if bool(entry[1]) == visible:
		return
	entry[1] = visible
	if bool(entry[2]):
		if visible:
			_bounded[id] = entry[0]
			_clear_gap = 0.0
		else:
			_bounded.erase(id)
	else:
		_unbounded += 1 if visible else -1

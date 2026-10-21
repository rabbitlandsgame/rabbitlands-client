class_name InteriorCutaway
extends RefCounted

## Keeps an interior visible from the isometric rig.
##
## An interior is a closed box: ceiling on top, four walls around. A camera
## framed for open ground sits above the ceiling and behind the near wall, so
## without a cutaway the player sees a roof and nothing else. This hides the
## ceiling outright and hides whichever wall the camera is currently looking
## through, following the rig as it rotates. Only visibility changes -- the
## collision bodies the world loader built from the same nodes stay in place,
## so a cut-away wall is still solid.
##
## Driven by the manifest's `cutaway` block, so the city (which has no such
## block) is untouched.
##
## A block with `props` also cuts away the scenery set into the walls (any
## node carrying the `cutaway_outward` meta, the wall's outward direction):
## a prop on a wall the camera faces drops out while it stands within
## `radiusMetres` of the player, so the floor around them opens up while the
## rest of the cave keeps its outline. Farther props stay, and the one that
## still covers the player is OccluderFade's.
##
## A wall entry with a `centre` [x, z] is a run of a rock pillar's face (a
## looping cave's holes, build_underground.py): a pillar stands in the room, so
## facing alone cannot say whether it is in the way. Its `outward` points out
## of the pillar, and it drops out by the props' rule (within the radius, facing
## the camera, on the camera's side), judged from its centre.

## How far the focus must move before the props are judged again.
const PROP_STEP_METRES := 0.75
## A hidden prop comes back only this much beyond the radius, so one standing
## on the edge does not flicker as the player shuffles.
const PROP_HYSTERESIS_METRES := 2.0

var _always_hidden: Array[Node3D] = []
var _walls: Array[Dictionary] = []
var _props: Array[Dictionary] = []
var _pillars: Array[Dictionary] = []
var _threshold := 0.2
var _prop_threshold := 0.5
var _prop_radius := 12.0
var _last_yaw := INF
var _last_section := ""
var _last_focus := Vector3.INF

func is_active() -> bool:
	return not _always_hidden.is_empty() or not _walls.is_empty() or not _props.is_empty() 		or not _pillars.is_empty()

## Reads the manifest's cutaway block and resolves it against the loaded scene.
## Returns the number of nodes it took control of.
func configure(manifest: WorldManifest, world_root: Node3D) -> int:
	reset()
	if manifest == null or world_root == null:
		return 0
	var block_value: Variant = manifest.data.get("cutaway", {})
	if not block_value is Dictionary:
		return 0
	var block: Dictionary = block_value as Dictionary
	if block.is_empty():
		return 0
	_threshold = float(block.get("facingThreshold", 0.2))

	var hide_value: Variant = block.get("hideNodes", [])
	if hide_value is Array:
		for name_value: Variant in hide_value as Array:
			var node := _find(world_root, str(name_value))
			if node != null:
				node.visible = false
				_always_hidden.append(node)

	var walls_value: Variant = block.get("walls", [])
	if walls_value is Array:
		for entry_value: Variant in walls_value as Array:
			if not entry_value is Dictionary:
				continue
			var entry: Dictionary = entry_value as Dictionary
			var node := _find(world_root, str(entry.get("node", "")))
			if node == null:
				continue
			var outward := Vector3.ZERO
			var outward_value: Variant = entry.get("outward", [])
			if outward_value is Array and (outward_value as Array).size() >= 3:
				var parts: Array = outward_value as Array
				outward = Vector3(float(parts[0]), 0.0, float(parts[2]))
			if outward.length_squared() < 0.0001:
				continue
			var centre_value: Variant = entry.get("centre")
			if centre_value is Array and (centre_value as Array).size() >= 2:
				var centre: Array = centre_value as Array
				_pillars.append({"node": node, "outward": outward.normalized(),
					"section": str(entry.get("section", "")),
					"position": Vector3(float(centre[0]), 0.0, float(centre[1])), "hidden": false})
				continue
			_walls.append({"node": node, "outward": outward.normalized(),
				"section": str(entry.get("section", ""))})

	var props_value: Variant = block.get("props", null)
	if props_value is Dictionary:
		var props: Dictionary = props_value as Dictionary
		_prop_threshold = float(props.get("facingThreshold", _prop_threshold))
		_prop_radius = float(props.get("radiusMetres", _prop_radius))
		for node: Node in world_root.find_children("*", "Node3D", true, false):
			if not node.has_meta("cutaway_outward"):
				continue
			var outward: Vector3 = node.get_meta("cutaway_outward")
			outward.y = 0.0
			if outward.length_squared() < 0.0001:
				continue
			var spatial := node as Node3D
			_props.append({"node": spatial, "outward": outward.normalized(),
				"position": spatial.global_position, "hidden": false})
	_last_yaw = INF
	_last_section = ""
	_last_focus = Vector3.INF
	return _always_hidden.size() + _walls.size() + _props.size() + _pillars.size()

## Restores everything this instance hid. Safe to call on a freed scene: a
## node is checked before it is cast, because casting a freed object to
## Node3D is an error (it fired on every back-to-back Four Gates interior load).
func reset() -> void:
	for value: Variant in _always_hidden:
		if is_instance_valid(value):
			(value as Node3D).visible = true
	for wall: Dictionary in _walls:
		var value: Variant = wall.get("node")
		if is_instance_valid(value):
			(value as Node3D).visible = true
	for prop: Dictionary in _props + _pillars:
		var value: Variant = prop.get("node")
		if is_instance_valid(value):
			(value as Node3D).visible = true
	_always_hidden.clear()
	_walls.clear()
	_props.clear()
	_pillars.clear()
	_last_yaw = INF
	_last_section = ""
	_last_focus = Vector3.INF

## Hides the walls the camera is looking through. Cheap enough to call every
## frame, but it only touches the scene when the rig has actually turned, the
## player has walked into another section or (for wall props) moved a step.
##
## `section` is SecretSections' current section on a map shown one section at
## a time. A wall the manifest gives a `section` is shown only in its own one,
## and entering a section re-hides the roofs, which SecretSections shows with
## the rest of the section it reveals. `focus` is where the player stands (the
## rig's focus); wall props are judged from it.
func update(camera_yaw_degrees: float, force: bool = false, section: String = "",
		focus: Vector3 = Vector3.INF) -> void:
	if _walls.is_empty() and _always_hidden.is_empty() and _props.is_empty() and _pillars.is_empty():
		return
	var entered := section != _last_section
	var turned := not is_equal_approx(camera_yaw_degrees, _last_yaw)
	var moved := focus.is_finite() and (not _last_focus.is_finite()
		or focus.distance_to(_last_focus) > PROP_STEP_METRES)
	if not force and not entered and not turned and not moved:
		return
	_last_yaw = camera_yaw_degrees
	_last_section = section
	if entered or force:
		for value: Variant in _always_hidden:
			if is_instance_valid(value):
				(value as Node3D).visible = false
	# The rig places the camera at +Z rotated by yaw, so this is the horizontal
	# direction from the player out to the camera.
	var yaw := deg_to_rad(camera_yaw_degrees)
	var to_camera := Vector3(sin(yaw), 0.0, cos(yaw))
	if force or entered or turned:
		for wall: Dictionary in _walls:
			var value: Variant = wall.get("node")
			if not is_instance_valid(value):
				continue
			var node := value as Node3D
			var own: String = wall.get("section", "")
			if not own.is_empty() and not section.is_empty() and own != section:
				node.visible = false
				continue
			var outward: Vector3 = wall.get("outward") as Vector3
			# A wall whose outside faces the camera is between the camera and the
			# room, so it is the one to drop.
			node.visible = outward.dot(to_camera) <= _threshold
	if not _pillars.is_empty() and (force or entered or turned or moved):
		_update_pillars(to_camera, focus, section, force or entered)
	if not _props.is_empty() and focus.is_finite():
		_last_focus = focus
		_update_props(to_camera, focus)

## A wall prop drops out while its wall faces the camera and it stands near
## the player on the camera's side; it returns past the radius plus a margin.
func _update_props(to_camera: Vector3, focus: Vector3) -> void:
	var here := Vector2(focus.x, focus.z)
	for prop: Dictionary in _props:
		var value: Variant = prop.get("node")
		if not is_instance_valid(value):
			continue
		var position: Vector3 = prop.get("position")
		var offset := Vector2(position.x, position.z) - here
		var reach := _prop_radius + (PROP_HYSTERESIS_METRES if bool(prop.get("hidden")) else 0.0)
		var outward: Vector3 = prop.get("outward")
		var hide := offset.length() < reach \
			and outward.dot(to_camera) > _prop_threshold \
			and offset.dot(Vector2(to_camera.x, to_camera.z)) > -3.0
		if hide != bool(prop.get("hidden")):
			prop["hidden"] = hide
			(value as Node3D).visible = not hide

## A pillar's face run: hidden in another section (as walls are), else by the
## props' rule from its centre. With no focus it stands.
func _update_pillars(to_camera: Vector3, focus: Vector3, section: String, refresh: bool) -> void:
	var here := Vector2(focus.x, focus.z) if focus.is_finite() else Vector2.INF
	for pillar: Dictionary in _pillars:
		var value: Variant = pillar.get("node")
		if not is_instance_valid(value):
			continue
		var node := value as Node3D
		var own: String = pillar.get("section", "")
		if not own.is_empty() and not section.is_empty() and own != section:
			node.visible = false
			pillar["hidden"] = true
			continue
		var hide := false
		if here.is_finite():
			var position: Vector3 = pillar.get("position")
			var offset := Vector2(position.x, position.z) - here
			var reach := _prop_radius + (PROP_HYSTERESIS_METRES if bool(pillar.get("hidden")) else 0.0)
			var outward: Vector3 = pillar.get("outward")
			hide = offset.length() < reach and outward.dot(to_camera) > _prop_threshold 				and offset.dot(Vector2(to_camera.x, to_camera.z)) > -3.0
		if refresh or hide != bool(pillar.get("hidden")) or node.visible == hide:
			pillar["hidden"] = hide
			node.visible = not hide

static func _find(root: Node3D, node_name: String) -> Node3D:
	if node_name.is_empty():
		return null
	return root.find_child(node_name, true, false) as Node3D

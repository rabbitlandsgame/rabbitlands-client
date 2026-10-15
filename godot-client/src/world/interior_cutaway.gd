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

var _always_hidden: Array[Node3D] = []
var _walls: Array[Dictionary] = []
var _threshold := 0.2
var _last_yaw := INF

func is_active() -> bool:
	return not _always_hidden.is_empty() or not _walls.is_empty()

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
			_walls.append({"node": node, "outward": outward.normalized()})
	_last_yaw = INF
	return _always_hidden.size() + _walls.size()

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
	_always_hidden.clear()
	_walls.clear()
	_last_yaw = INF

## Hides the walls the camera is looking through. Cheap enough to call every
## frame, but it only touches the scene when the rig has actually turned.
func update(camera_yaw_degrees: float, force: bool = false) -> void:
	if _walls.is_empty():
		return
	if not force and is_equal_approx(camera_yaw_degrees, _last_yaw):
		return
	_last_yaw = camera_yaw_degrees
	# The rig places the camera at +Z rotated by yaw, so this is the horizontal
	# direction from the player out to the camera.
	var yaw := deg_to_rad(camera_yaw_degrees)
	var to_camera := Vector3(sin(yaw), 0.0, cos(yaw))
	for wall: Dictionary in _walls:
		var value: Variant = wall.get("node")
		if not is_instance_valid(value):
			continue
		var node := value as Node3D
		var outward: Vector3 = wall.get("outward") as Vector3
		# A wall whose outside faces the camera is between the camera and the
		# room, so it is the one to drop.
		node.visible = outward.dot(to_camera) <= _threshold

static func _find(root: Node3D, node_name: String) -> Node3D:
	if node_name.is_empty():
		return null
	return root.find_child(node_name, true, false) as Node3D

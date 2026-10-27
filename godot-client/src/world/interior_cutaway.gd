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
##
## Props and pillar runs are filed in a grid of PROP_CELL_METRES squares when
## configured, and a step or a turn judges only those within reach of the
## player and those it has hidden (pass 2, 2026-10-21: the underground grew to
## caves of 16,000 tiles, and judging every rock of every cave on every step
## cost milliseconds a frame while the camera turned). A refresh (entering a
## section, or a forced update) still judges every pillar run, hiding the other
## sections' ones.
##
## A prop may instead name the wall it stands against (WALL_PROP_META, the
## node name of a `walls` entry: the town's dressers, shelves and hearths,
## underground_scenery.gd `cutawayWall`). It is shown and hidden with that
## wall, wherever the player stands, so a room cuts away like a doll's house
## and furniture never floats in front of a dropped wall. Linked during the
## same walk that finds the props, so only a block with `props` links them.
##
## A block with `partitions` (the town's walls between rooms: rows
## {node, section, rooms, centre [x, z], along, normal}, one per node of a
## partition - its wall, trim and the decals hung on it) cuts a partition away
## while it stands between the camera and the player: the player is inside
## its section, on its far side from the camera, and within its span (+2 m).
## Rows sharing a centre and direction are one partition, hidden together with
## every prop whose WALL_PROP_META names one of its nodes, so a banner or a
## shelf never floats in front of a wall that is gone. Hysteresis on both the
## side (0.3 m) and the span (1 m) keeps a player in a doorway from making it
## flicker. Outer walls never follow this rule; they keep the facing rule.
## Before this the partitions only faded (OccluderFade) and their decals and
## props stayed solid in front of the frosted pane (review, 2026-10-27).
##
## A partition running toward the camera is seen edge-on, so the rule above
## passes it, yet with the player standing at its end its top runs down the
## screen over their legs (Hemmen's study/kitchen wall from his bedroom,
## clerk_house-b2, final review 2026-10-27). The sightline rule cuts a
## partition too while it stands in the way of the line from the player's body
## to the camera (sampled at shin, waist and head, half a body to either
## side, against the partition's bounds) and the player is within its span
## (+2 m) - except while the player stands in its own plane within its run,
## a doorway, which the facing rule's hysteresis keeps steady. The camera is
## the world root's viewport camera, or the rig's orbit at the town's camera
## block when there is none.
##
## `screens` answers whether a standing partition of the shown section stands
## between the camera and a point: Main keeps the name of somebody behind one
## off the screen (a name drawn through the wall named a person the player
## could not see: "Corbin Lask" over the Gate Hall).

## The meta a placed prop carries naming its wall's cutaway node.
const WALL_PROP_META := "cutaway_wall"
## How far the focus must move before the props are judged again.
const PROP_STEP_METRES := 0.75
## The side of the grid squares props and pillar runs are filed in.
const PROP_CELL_METRES := 16.0
## A hidden prop comes back only this much beyond the radius, so one standing
## on the edge does not flicker as the player shuffles.
const PROP_HYSTERESIS_METRES := 2.0
## A partition is cut away while the player is within its span plus this...
const PARTITION_SPAN_MARGIN := 2.0
## ...and comes back only this much farther along it.
const PARTITION_SPAN_HYSTERESIS := 1.0
## The player must be this far past a partition (away from the camera) for it
## to drop, and this far back on the camera's side for it to return.
const PARTITION_SIDE_METRES := 0.3
## A partition seen this nearly edge-on (|normal . to camera|) hides nothing
## by the facing rule (the sightline rule judges it).
const PARTITION_FACING := 0.1
## The sightline rule's body: heights above the focus (the player's feet)...
const SIGHTLINE_HEIGHTS: Array[float] = [0.3, 1.0, 1.7]
## ...and how far to either side across the line (half a body's width); a
## cut-away partition returns only once the body is this much wider clear.
const SIGHTLINE_HALF_WIDTH := 0.3
const SIGHTLINE_HYSTERESIS := 0.3

## The camera assumed when the world root's viewport has none (tests, a build
## off the tree): the rig's orbit at the town's camera block.
var fallback_pitch_degrees := -50.0
var fallback_distance := 12.0

var _always_hidden: Array[Node3D] = []
var _walls: Array[Dictionary] = []
## {"nodes": [Node3D], "props": [Node3D], "section", "centre": Vector2,
## "along": Vector2, "normal": Vector2, "half": float, "thick": float (half
## its thickness), "box": AABB (its nodes' bounds), "hidden": bool}
var _partitions: Array[Dictionary] = []
## The world root configured (its viewport's camera is the sightline's end).
var _root: WeakRef = null
## How many props follow a wall (WALL_PROP_META), across all walls.
var _wall_props := 0
var _props: Array[Dictionary] = []
var _pillars: Array[Dictionary] = []
## Grid square (Vector2i) -> the props / pillar runs standing in it.
var _prop_cells: Dictionary = {}
var _pillar_cells: Dictionary = {}
## The props and pillar runs the props' rule hides now (a run hidden because it
## stands in another section is not one: the next refresh judges it).
var _hidden_props: Array = []
var _hidden_pillars: Array = []
var _stamp := 0
var _threshold := 0.2
var _prop_threshold := 0.5
var _prop_radius := 12.0
var _last_yaw := INF
var _last_section := ""
var _last_focus := Vector3.INF

func is_active() -> bool:
	return not _always_hidden.is_empty() or not _walls.is_empty() or not _props.is_empty() \
		or not _pillars.is_empty() or not _partitions.is_empty()

## Reads the manifest's cutaway block and resolves it against the loaded scene.
## Returns the number of nodes it took control of.
func configure(manifest: WorldManifest, world_root: Node3D) -> int:
	reset()
	if manifest == null or world_root == null:
		return 0
	_root = weakref(world_root)
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

	var partitions_value: Variant = block.get("partitions", [])
	if partitions_value is Array:
		_read_partitions(partitions_value as Array, world_root)

	var props_value: Variant = block.get("props", null)
	if props_value is Dictionary:
		var props: Dictionary = props_value as Dictionary
		_prop_threshold = float(props.get("facingThreshold", _prop_threshold))
		_prop_radius = float(props.get("radiusMetres", _prop_radius))
		var walls_by_name: Dictionary = {}
		for wall: Dictionary in _walls:
			walls_by_name[str((wall.node as Node3D).name)] = wall
		# A prop against a partition names one of its nodes: it goes with it.
		for partition: Dictionary in _partitions:
			for node: Node3D in partition.nodes:
				walls_by_name[str(node.name)] = partition
		for node: Node in world_root.find_children("*", "Node3D", true, false):
			if node.has_meta(WALL_PROP_META):
				var owner_wall: Variant = walls_by_name.get(str(node.get_meta(WALL_PROP_META)))
				if owner_wall is Dictionary:
					if not (owner_wall as Dictionary).has("props"):
						(owner_wall as Dictionary)["props"] = []
					((owner_wall as Dictionary).props as Array).append(node)
					_wall_props += 1
					continue
			if not node.has_meta("cutaway_outward"):
				continue
			var outward: Vector3 = node.get_meta("cutaway_outward")
			outward.y = 0.0
			if outward.length_squared() < 0.0001:
				continue
			var spatial := node as Node3D
			_props.append({"node": spatial, "outward": outward.normalized(),
				"position": spatial.global_position, "hidden": false})
	_prop_cells = _cells_of(_props)
	_pillar_cells = _cells_of(_pillars)
	_last_yaw = INF
	_last_section = ""
	_last_focus = Vector3.INF
	var partition_nodes := 0
	for partition: Dictionary in _partitions:
		partition_nodes += (partition.nodes as Array).size()
	return _always_hidden.size() + _walls.size() + _props.size() + _pillars.size() + _wall_props \
		+ partition_nodes

## Groups the `partitions` rows into partitions (one per centre and direction
## in a section) and measures each one's half span along its run from its
## nodes' bounds (the rows carry no length).
func _read_partitions(rows: Array, world_root: Node3D) -> void:
	var by_key: Dictionary = {}
	for row_value: Variant in rows:
		if row_value is not Dictionary:
			continue
		var row: Dictionary = row_value
		var node := _find(world_root, str(row.get("node", "")))
		var centre_value: Variant = row.get("centre")
		var normal_value: Variant = row.get("normal")
		var along_value: Variant = row.get("along")
		if node == null or centre_value is not Array or (centre_value as Array).size() < 2 \
				or normal_value is not Array or (normal_value as Array).size() < 3 \
				or along_value is not Array or (along_value as Array).size() < 3:
			continue
		var normal := Vector2(float(normal_value[0]), float(normal_value[2]))
		var along := Vector2(float(along_value[0]), float(along_value[2]))
		if normal.length_squared() < 0.0001 or along.length_squared() < 0.0001:
			continue
		normal = normal.normalized()
		along = along.normalized()
		var centre := Vector2(float(centre_value[0]), float(centre_value[1]))
		var section := str(row.get("section", ""))
		# One partition whichever way round its rows state the direction.
		var key := "%s|%.2f|%.2f|%.2f" % [section, centre.x, centre.y, absf(along.x)]
		if not by_key.has(key):
			by_key[key] = {"nodes": [], "props": [], "section": section, "centre": centre,
				"along": along, "normal": normal, "half": 0.0, "hidden": false}
			_partitions.append(by_key[key])
		((by_key[key] as Dictionary).nodes as Array).append(node)
	for partition: Dictionary in _partitions:
		var half := 0.0
		var thick := 0.0
		var bounds := AABB()
		var any := false
		for node: Node3D in partition.nodes:
			var box := _root_box(node, world_root)
			bounds = box if not any else bounds.merge(box)
			any = true
			for corner: int in 8:
				var point := box.get_endpoint(corner)
				var flat := Vector2(point.x, point.z) - (partition.centre as Vector2)
				half = maxf(half, absf(flat.dot(partition.along as Vector2)))
				thick = maxf(thick, absf(flat.dot(partition.normal as Vector2)))
		partition["half"] = half
		partition["thick"] = thick
		partition["box"] = bounds

## The node's bounds in the world root's frame; a node without bounds is a
## point at its origin.
static func _root_box(node: Node3D, world_root: Node3D) -> AABB:
	var frame := node.transform
	var parent := node.get_parent() as Node3D
	while parent != null and parent != world_root:
		frame = parent.transform * frame
		parent = parent.get_parent() as Node3D
	if node is VisualInstance3D:
		return frame * (node as VisualInstance3D).get_aabb()
	return AABB(frame.origin, Vector3.ZERO)

## Files `entries` (props or pillar runs, each with a `position`) by grid square.
static func _cells_of(entries: Array[Dictionary]) -> Dictionary:
	var cells := {}
	for entry: Dictionary in entries:
		var at: Vector3 = entry.get("position")
		var key := Vector2i(floori(at.x / PROP_CELL_METRES), floori(at.z / PROP_CELL_METRES))
		if not cells.has(key):
			cells[key] = []
		(cells[key] as Array).append(entry)
	return cells

## What a step or a turn at `focus` judges: the entries filed within `reach` of
## it, then the ones `hidden` now (an entry may come twice; judging is idempotent).
static func _near(cells: Dictionary, hidden: Array, focus: Vector3, reach: float) -> Array:
	var result: Array = []
	for cx in range(floori((focus.x - reach) / PROP_CELL_METRES), floori((focus.x + reach) / PROP_CELL_METRES) + 1):
		for cz in range(floori((focus.z - reach) / PROP_CELL_METRES), floori((focus.z + reach) / PROP_CELL_METRES) + 1):
			result.append_array(cells.get(Vector2i(cx, cz), []) as Array)
	result.append_array(hidden)
	return result

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
		_show_wall_props(wall, true)
	for prop: Dictionary in _props + _pillars:
		var value: Variant = prop.get("node")
		if is_instance_valid(value):
			(value as Node3D).visible = true
	for partition: Dictionary in _partitions:
		_show_partition(partition, true)
	_always_hidden.clear()
	_walls.clear()
	_partitions.clear()
	_wall_props = 0
	_props.clear()
	_pillars.clear()
	_prop_cells.clear()
	_pillar_cells.clear()
	_hidden_props.clear()
	_hidden_pillars.clear()
	_last_yaw = INF
	_last_section = ""
	_last_focus = Vector3.INF
	_root = null

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
	if _walls.is_empty() and _always_hidden.is_empty() and _props.is_empty() and _pillars.is_empty() \
			and _partitions.is_empty():
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
				_show_wall_props(wall, false)
				continue
			var outward: Vector3 = wall.get("outward") as Vector3
			# A wall whose outside faces the camera is between the camera and the
			# room, so it is the one to drop.
			node.visible = outward.dot(to_camera) <= _threshold
			_show_wall_props(wall, node.visible)
	if not _pillars.is_empty() and (force or entered or turned or moved):
		_update_pillars(to_camera, focus, section, force or entered)
	if not _partitions.is_empty() and (force or entered or turned or moved):
		_update_partitions(to_camera, focus, section, force or entered,
			camera_position(camera_yaw_degrees, focus) if focus.is_finite() else Vector3.INF)
	if focus.is_finite() and (not _props.is_empty() or not _partitions.is_empty()):
		_last_focus = focus
	if not _props.is_empty() and focus.is_finite():
		_update_props(to_camera, focus)

## A wall prop drops out while its wall faces the camera and it stands near
## the player on the camera's side; it returns past the radius plus a margin.
func _update_props(to_camera: Vector3, focus: Vector3) -> void:
	var here := Vector2(focus.x, focus.z)
	_stamp += 1
	var still: Array = []
	for prop: Dictionary in _near(_prop_cells, _hidden_props, focus, _prop_radius + PROP_HYSTERESIS_METRES):
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
		if hide and int(prop.get("stamp", -1)) != _stamp:
			prop["stamp"] = _stamp
			still.append(prop)
	_hidden_props = still

## A pillar's face run: hidden in another section (as walls are), else by the
## props' rule from its centre. With no focus it stands.
func _update_pillars(to_camera: Vector3, focus: Vector3, section: String, refresh: bool) -> void:
	var here := Vector2(focus.x, focus.z) if focus.is_finite() else Vector2.INF
	# a refresh judges every run (hiding the other sections'); a step or a turn the ones near the player and the
	# ones the props' rule hid
	var runs: Array = _pillars
	if not refresh:
		runs = _near(_pillar_cells, _hidden_pillars, focus, _prop_radius + PROP_HYSTERESIS_METRES) \
			if focus.is_finite() else _hidden_pillars
	_stamp += 1
	var still: Array = []
	for pillar: Dictionary in runs:
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
		if hide and int(pillar.get("stamp", -1)) != _stamp:
			pillar["stamp"] = _stamp
			still.append(pillar)
	_hidden_pillars = still

## Where the camera stands: the world root's viewport camera, else the rig's
## orbit (`fallback_pitch_degrees`, `fallback_distance`) around `focus` at
## `camera_yaw_degrees`.
func camera_position(camera_yaw_degrees: float, focus: Vector3) -> Vector3:
	var root: Node3D = _root.get_ref() as Node3D if _root != null else null
	if root != null and root.is_inside_tree():
		var camera := root.get_viewport().get_camera_3d()
		if camera != null:
			return camera.global_position
	var yaw := deg_to_rad(camera_yaw_degrees)
	var pitch := deg_to_rad(fallback_pitch_degrees)
	return focus + Vector3(sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch)) * fallback_distance

## Cuts away each partition of the player's section that stands between the
## camera and the player (see the header): by the facing rule, or by the
## sightline rule from `camera` (INF: none). Another section's are left to
## SecretSections, and with no focus every partition stands.
func _update_partitions(to_camera: Vector3, focus: Vector3, section: String, refresh: bool,
		camera_at := Vector3.INF) -> void:
	var camera := Vector2(to_camera.x, to_camera.z)
	for partition: Dictionary in _partitions:
		var own: String = partition.section
		var hidden: bool = partition.hidden
		var hide := false
		if focus.is_finite() and (own.is_empty() or section.is_empty() or own == section):
			var normal: Vector2 = partition.normal
			var facing := camera.dot(normal)
			var offset := Vector2(focus.x, focus.z) - (partition.centre as Vector2)
			# > 0: the player stands on the side away from the camera.
			var beyond := -offset.dot(normal) * signf(facing)
			var along := absf(offset.dot(partition.along as Vector2))
			var reach: float = float(partition.half) + PARTITION_SPAN_MARGIN \
				+ (PARTITION_SPAN_HYSTERESIS if hidden else 0.0)
			hide = absf(facing) > PARTITION_FACING and along <= reach \
				and beyond > (-PARTITION_SIDE_METRES if hidden else PARTITION_SIDE_METRES)
			# The sightline rule: not for a player in the partition's own plane
			# within its run (a doorway), where the facing rule's hysteresis
			# holds (an edge-on partition's plane is its thickness alone).
			var doorway := along <= float(partition.half) and absf(offset.dot(normal)) \
				<= float(partition.thick) + (PARTITION_SIDE_METRES if absf(facing) > PARTITION_FACING else 0.0)
			if not hide and camera_at.is_finite() and along <= reach and not doorway:
				hide = blocks_sight(partition.box as AABB, focus, camera_at,
					SIGHTLINE_HALF_WIDTH + (SIGHTLINE_HYSTERESIS if hidden else 0.0))
		elif not own.is_empty() and not section.is_empty() and own != section:
			# Out of sight with its section; shown again when it is entered.
			partition["hidden"] = false
			continue
		if refresh or hide != hidden:
			partition["hidden"] = hide
			_show_partition(partition, not hide)

## Whether `box` stands in the way of the line from the body at `focus` (the
## player's feet) to `camera`: the line from each of SIGHTLINE_HEIGHTS, and
## from `half_width` to either side across it, meets the box.
static func blocks_sight(box: AABB, focus: Vector3, camera: Vector3, half_width: float) -> bool:
	if box.size == Vector3.ZERO:
		return false
	var flat := Vector2(camera.x - focus.x, camera.z - focus.z)
	var side := Vector3.ZERO
	if flat.length_squared() > 0.0001:
		var across := Vector2(-flat.y, flat.x).normalized()
		side = Vector3(across.x, 0.0, across.y)
	for height: float in SIGHTLINE_HEIGHTS:
		var body := focus + Vector3.UP * height
		for shift: float in [-half_width, 0.0, half_width]:
			if segment_hits(box, body + side * shift, camera + side * shift):
				return true
	return false

## Whether the segment from `from` to `to` meets `box` (slab test).
static func segment_hits(box: AABB, from: Vector3, to: Vector3) -> bool:
	var enter := 0.0
	var leave := 1.0
	var span := to - from
	for axis: int in 3:
		var low: float = box.position[axis]
		var high: float = box.end[axis]
		if absf(span[axis]) < 0.000001:
			if from[axis] < low or from[axis] > high:
				return false
			continue
		var a: float = (low - from[axis]) / span[axis]
		var b: float = (high - from[axis]) / span[axis]
		enter = maxf(enter, minf(a, b))
		leave = minf(leave, maxf(a, b))
		if enter > leave:
			return false
	return true

## Whether a standing partition of the shown section (one drawn now: not cut
## away, not in another section) stands between `from` (the camera) and
## `point`. Main hides the name over an actor's head behind one.
func screens(from: Vector3, point: Vector3) -> bool:
	if _partitions.is_empty() or not from.is_finite() or not point.is_finite():
		return false
	for partition: Dictionary in _partitions:
		if bool(partition.hidden) or (partition.nodes as Array).is_empty():
			continue
		var own: String = partition.section
		if not own.is_empty() and not _last_section.is_empty() and own != _last_section:
			continue
		var first: Variant = (partition.nodes as Array)[0]
		if not is_instance_valid(first) or not (first as Node3D).is_visible_in_tree():
			continue
		if segment_hits(partition.box as AABB, from, point):
			return true
	return false

## The partitions cut away now (diagnostics and tests): their first nodes.
func hidden_partitions() -> Array[Node3D]:
	var result: Array[Node3D] = []
	for partition: Dictionary in _partitions:
		if bool(partition.hidden) and not (partition.nodes as Array).is_empty():
			result.append((partition.nodes as Array)[0])
	return result

static func _show_partition(partition: Dictionary, shown: bool) -> void:
	for value: Variant in partition.get("nodes", []) as Array:
		if is_instance_valid(value):
			(value as Node3D).visible = shown
	_show_wall_props(partition, shown)

## The props standing against `wall` follow its visibility.
static func _show_wall_props(wall: Dictionary, shown: bool) -> void:
	for value: Variant in wall.get("props", []) as Array:
		if is_instance_valid(value):
			(value as Node3D).visible = shown

static func _find(root: Node3D, node_name: String) -> Node3D:
	if node_name.is_empty():
		return null
	return root.find_child(node_name, true, false) as Node3D

class_name SecretSections
extends RefCounted
## Shows a player only the secret they are standing in.
##
## A `<region>_secrets` map carries every secret of a region on one map with
## void between them. The manifest declares `secret: true` and a `sections`
## list, each with `bounds` in metres; the GLB names its nodes per section
## (`Walk_<section>_<material>`, `Build_...`, `Roof_...`). This assigns every
## mesh and light under the world root to the section whose bounds hold its
## centre, then keeps only the current section visible. The minimap and the
## full map are live renders of the same world, so they black out with it.

var _sections: Array[Dictionary] = []
var _members: Dictionary = {}          # section id -> Array[Node3D]
var _loose: Array[Node3D] = []         # nodes no section claims: left visible
var _culled: Array[Node3D] = []        # actors and objects hidden by position
var _current: String = ""
const MARGIN := 3.0


func is_active() -> bool:
	return not _sections.is_empty()


func current_section() -> String:
	return _current


func reset() -> void:
	for id: String in _members.keys():
		# A typed loop variable would cast a freed reference before the check.
		for value: Variant in _members[id] as Array:
			if is_instance_valid(value):
				(value as Node3D).visible = true
	for value: Variant in _culled:
		if is_instance_valid(value):
			(value as Node3D).visible = true
	_sections.clear()
	_members.clear()
	_loose.clear()
	_culled.clear()
	_current = ""


## Reads the manifest's sections and sorts the loaded scene into them.
## Returns how many nodes were claimed by a section.
func configure(manifest: WorldManifest, world_root: Node3D) -> int:
	reset()
	if manifest == null or world_root == null:
		return 0
	if not bool(manifest.data.get("secret", false)):
		return 0
	var listed: Variant = manifest.data.get("sections", [])
	if not listed is Array:
		return 0
	for entry_value: Variant in listed as Array:
		if not entry_value is Dictionary:
			continue
		var entry: Dictionary = entry_value as Dictionary
		var bounds_value: Variant = entry.get("bounds", {})
		if not bounds_value is Dictionary:
			continue
		var bounds: Dictionary = bounds_value as Dictionary
		var lo: Array = bounds.get("min", []) as Array
		var hi: Array = bounds.get("max", []) as Array
		if lo.size() < 2 or hi.size() < 2:
			continue
		_sections.append({
			"id": str(entry.get("id", "")),
			"min": Vector2(float(lo[0]), float(lo[1])),
			"max": Vector2(float(hi[0]), float(hi[1])),
		})
		_members[str(entry.get("id", ""))] = []
	if _sections.is_empty():
		return 0
	var claimed := 0
	for node: Node3D in _spatial_nodes(world_root):
		var section := _section_of_node(node)
		if section.is_empty():
			_loose.append(node)
			continue
		(_members[section] as Array).append(node)
		claimed += 1
	return claimed


## Called with the local player's world position; shows their section only.
func update(player_position: Vector3, force: bool = false) -> void:
	if _sections.is_empty():
		return
	var here := _section_at(Vector2(player_position.x, player_position.z))
	if here.is_empty():
		# between sections (mid-arrival): keep what was shown
		if _current.is_empty() and not force:
			return
		here = _current
	if here == _current and not force:
		return
	_current = here
	for id: String in _members.keys():
		var shown := id == here
		for value: Variant in _members[id] as Array:
			if is_instance_valid(value):
				(value as Node3D).visible = shown


## Actors and server map objects arrive after the scene was sorted and move
## about, so they are judged by where they stand, every frame: only those in
## the player's section are drawn. `keep` (the local player) is never hidden.
func cull_dynamic(nodes: Array, keep: Node3D = null) -> void:
	if _sections.is_empty() or _current.is_empty():
		return
	for value: Variant in nodes:
		if not is_instance_valid(value):
			continue
		var node := value as Node3D
		if node == null or node == keep:
			continue
		if not node.is_inside_tree():
			continue
		var position := node.global_position
		var shown := _section_at(Vector2(position.x, position.z)) == _current
		node.visible = shown
		if not shown and not _culled.has(node):
			_culled.append(node)


func _section_at(point: Vector2, margin: float = MARGIN) -> String:
	for section: Dictionary in _sections:
		var lo: Vector2 = section["min"]
		var hi: Vector2 = section["max"]
		if point.x >= lo.x - margin and point.x <= hi.x + margin \
				and point.y >= lo.y - margin and point.y <= hi.y + margin:
			return str(section["id"])
	return ""


func _section_of_node(node: Node3D) -> String:
	# the node's name carries the section id first, then its centre decides
	var name := node.name
	for section: Dictionary in _sections:
		var id: String = str(section["id"])
		if name.begins_with("Section_" + id) or name.begins_with("Walk_" + id + "_") \
				or name.begins_with("Build_" + id + "_") or name.begins_with("Roof_" + id + "_"):
			return id
	var centre := node.global_position
	if node is VisualInstance3D:
		var aabb: AABB = (node as VisualInstance3D).get_aabb()
		centre = node.global_transform * (aabb.position + aabb.size * 0.5)
	return _section_at(Vector2(centre.x, centre.z), 1.0)


static func _spatial_nodes(root: Node) -> Array[Node3D]:
	var out: Array[Node3D] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		# Old imports and lights may still share the root until the frame ends.
		# Skip the whole retiring subtree, including its unmarked children.
		if node.is_queued_for_deletion():
			continue
		for child: Node in node.get_children():
			stack.append(child)
		if node == root:
			continue
		if node is VisualInstance3D or node is Light3D:
			out.append(node as Node3D)
	return out

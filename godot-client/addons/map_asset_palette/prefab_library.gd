@tool
extends RefCounted
## Reusable groups of placed assets ("prefabs").
##
## A prefab is a small PackedScene under PREFAB_DIRECTORY holding copies of the
## selected authored assets and gameplay markers around a ground-level pivot.
## It is only an authoring convenience: placing one creates ordinary,
## independent AuthoredAssets entries with fresh asset ids, and markers in
## their kind's Gameplay container with fresh record ids and the copy rules
## (marker_library.gd reset_copy: no server bindings, never a default spawn, no
## placement extras; a follow or link to a member follows that member's copy),
## so bakes and snapshots never see the prefab itself.

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")
const MARKER_SCRIPT := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const Markers := preload("res://addons/map_asset_palette/marker_library.gd")
const PREFAB_DIRECTORY := "res://world_authoring/prefabs"
## Tests point this at a disposable folder; editors keep the default.
static var directory := PREFAB_DIRECTORY
const PREFAB_META := &"map_authoring_prefab"
const GROUND_OFFSET_META := &"map_authoring_prefab_ground_offset"
const CATEGORY := "Prefabs"
const ID_PREFIX := "prefab:"
const CONTAINER_NAME := "AuthoredAssets"


static func entries() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var folder := DirAccess.open(directory)
	if folder == null:
		return result
	var files := folder.get_files()
	files.sort()
	for file_name in files:
		if not file_name.ends_with(".tscn"):
			continue
		var path := directory.path_join(file_name)
		var label := file_name.get_basename().capitalize()
		result.append({
			"id": ID_PREFIX + file_name.get_basename(),
			"label": label,
			"category": CATEGORY,
			"scene_path": path,
			"source_node": "",
			"height": 0.0,
			"prefab": true,
			"search_text": "%s %s prefab" % [file_name.get_basename(), label],
		})
	return result


static func is_prefab_entry(entry: Dictionary) -> bool:
	return bool(entry.get("prefab", false))


## Nodes a prefab may capture: placed asset wrappers (and the pilot's cosmetic
## scenery) and gameplay markers of a known kind, never the root, containers,
## generated previews, terrain, paths or water, or a node whose ancestor is
## chosen. Placement puts wrappers under AuthoredAssets and markers under their
## kind's Gameplay container; anything else there would fail the snapshot, so
## the filter is enforced here rather than left to the UI.
static func capturable(root: Node3D, nodes: Array) -> Array[Node3D]:
	var result: Array[Node3D] = []
	var generated := root.get_node_or_null("GeneratedPreview")
	var scenery := root.get_node_or_null("AuthoredScenery")
	var gameplay := root.get_node_or_null(Markers.GAMEPLAY)
	for value in nodes:
		if not value is Node3D:
			continue
		var node := value as Node3D
		if node == root or not root.is_ancestor_of(node) or node.get_parent() == root:
			continue
		if generated != null and generated.is_ancestor_of(node):
			continue
		if node.owner != root:
			continue
		var marker: bool = node.get_script() == MARKER_SCRIPT and gameplay != null and \
			gameplay.is_ancestor_of(node) and Markers.KINDS.has(String(node.get("kind")))
		if node.get_script() != ASSET_SCRIPT and not marker and \
				not (scenery != null and node.get_parent() == scenery):
			continue
		result.append(node)
	var filtered: Array[Node3D] = []
	for node in result:
		var nested := false
		for other in result:
			if other != node and other.is_ancestor_of(node):
				nested = true
				break
		if not nested:
			filtered.append(node)
	return filtered


## Selected nodes a prefab leaves out: markers it cannot place (outside
## Gameplay or of an unknown kind) and other authored controls. Returned so the
## caller can say so instead of dropping them quietly.
static func left_out(root: Node3D, nodes: Array) -> Dictionary:
	var members := capturable(root, nodes)
	var markers := 0
	var other := 0
	for value in nodes:
		if not value is Node3D or value in members or value == root or \
				not root.is_ancestor_of(value) or (value as Node).owner != root or \
				(value as Node).get_parent() == root:
			continue
		var covered := false
		for member in members:
			if member.is_ancestor_of(value):
				covered = true
				break
		if covered:
			continue
		if (value as Node).get_script() == MARKER_SCRIPT:
			markers += 1
		else:
			other += 1
	return {"markers": markers, "other": other}


static func save_selection(root: Node3D, nodes: Array, prefab_name: String) -> Dictionary:
	var members := capturable(root, nodes)
	var skipped := left_out(root, nodes)
	if members.is_empty():
		return {"error": "Select one or more placed assets or gameplay markers to save as a prefab."}
	var file_stem := _file_stem(prefab_name)
	if file_stem.is_empty():
		return {"error": "Give the prefab a name."}
	var centre := Vector3.ZERO
	for member in members:
		centre += member.global_position
	centre /= float(members.size())
	var pivot_height := Probe.height_at(root, centre)
	if is_nan(pivot_height):
		pivot_height = INF
		for member in members:
			pivot_height = minf(pivot_height, member.global_position.y)
	var pivot := Transform3D(Basis.IDENTITY, Vector3(centre.x, pivot_height, centre.z))
	var prefab := Node3D.new()
	prefab.name = file_stem.to_pascal_case()
	var marker_count := 0
	var member_assets := {}
	var member_nodes := {}
	for member in members:
		if member.get_script() == MARKER_SCRIPT:
			marker_count += 1
		elif member.get_script() == ASSET_SCRIPT:
			member_assets[String(member.get("asset_id"))] = true
			member_nodes[String(member.get("node_name"))] = true
			member_nodes[String(member.name)] = true
	prefab.set_meta(PREFAB_META, {"version": 2 if marker_count > 0 else 1,
		"label": prefab_name.strip_edges(), "members": members.size(), "markers": marker_count})
	for member in members:
		var copy := member.duplicate() as Node3D
		if copy == null:
			continue
		if copy.get_script() == MARKER_SCRIPT:
			# The template never carries what a copy must not keep, nor a follow
			# or link to something outside the prefab.
			Markers.reset_copy(copy)
			if not member_assets.has(String(copy.get("follow_asset_id"))):
				copy.set("follow_asset_id", "")
			if not member_nodes.has(String(copy.get("linked_node_name"))):
				copy.set("linked_node_name", "")
		var ground := Probe.height_at(root, member.global_position)
		var offset := member.global_position.y - (ground if not is_nan(ground) else pivot_height)
		copy.set_meta(GROUND_OFFSET_META, offset)
		prefab.add_child(copy, true)
		copy.transform = pivot.affine_inverse() * member.global_transform
		_own_for_packing(copy, prefab, member, root)
	var packed := PackedScene.new()
	var pack_error := packed.pack(prefab)
	prefab.free()
	if pack_error != OK:
		return {"error": "Could not pack the prefab (%s)." % error_string(pack_error)}
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var path := directory.path_join(file_stem + ".tscn")
	var save_error := ResourceSaver.save(packed, path)
	if save_error != OK:
		return {"error": "Could not save %s (%s)." % [path, error_string(save_error)]}
	return {"path": path, "members": members.size(), "markers": marker_count,
		"id": ID_PREFIX + file_stem,
		"left_out_markers": int(skipped.markers), "left_out_other": int(skipped.other)}


## Instantiates a prefab for previewing or placing. Returns {"node": root} whose
## children are the members at their pivot-relative transforms.
static func instantiate(entry: Dictionary) -> Dictionary:
	var path := String(entry.get("scene_path", ""))
	var packed := ResourceLoader.load(path, "PackedScene",
		ResourceLoader.CACHE_MODE_REPLACE) as PackedScene
	if packed == null:
		return {"error": "Could not load prefab %s." % path}
	var node := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	if node == null or not node.has_meta(PREFAB_META):
		if node != null:
			node.free()
		return {"error": "%s is not a map prefab." % path}
	return {"node": node}


## Moves the members out of an instantiated prefab as one undoable action:
## assets into AuthoredAssets with fresh asset ids and independent local
## resources, markers into their kind's Gameplay container with fresh record
## ids, the copy rules, their facing turned with the prefab, and follows and
## links moved onto the placed copies of their members.
static func commit_with_undo(undo_redo: EditorUndoRedoManager, scene_root: Node3D,
		prefab: Node3D, pivot: Transform3D, conform_to_ground: bool, lift: float,
		label: String) -> Array[Node3D]:
	var placed: Array[Node3D] = []
	if undo_redo == null or scene_root == null or prefab == null:
		return placed
	var containers := {}
	var new_containers: Array[Array] = []
	var reserved := {}
	var reserved_records := {}
	var asset_map := {}
	var node_map := {}
	var records: Array[Dictionary] = []
	for member_value in prefab.get_children():
		var member := member_value as Node3D
		if member == null:
			continue
		var parent := _container_for(scene_root, member, containers, new_containers)
		if parent == null:
			continue
		var world := member_world_transform(scene_root, member, pivot, conform_to_ground, lift)
		var owned: Array[Node] = []
		for descendant in _descendants(member):
			if descendant.owner == prefab:
				owned.append(descendant)
		records.append({"node": member, "world": world, "owned": owned, "parent": parent})
	var markers: Array[Node] = []
	for record: Dictionary in records:
		var member := record.node as Node3D
		prefab.remove_child(member)
		# Detaching keeps the prefab root as owner; clear it before the members join
		# the edited scene, or they would point at a freed prefab root.
		member.owner = null
		for descendant: Node in record.owned:
			descendant.owner = null
		member.remove_meta(GROUND_OFFSET_META)
		if member.get_script() == ASSET_SCRIPT:
			var identity := _fresh_asset_id(record.parent, String(member.get("catalog_asset_id")),
				String(member.get("asset_id")), reserved)
			reserved[identity] = true
			asset_map[String(member.get("asset_id"))] = identity
			var node_name := "Authored_%s" % identity.replace(":", "_").replace("-", "_")
			node_map[String(member.get("node_name"))] = node_name
			node_map[String(member.name)] = node_name
			member.set("asset_id", identity)
			member.set("node_name", node_name)
		elif member.get_script() == MARKER_SCRIPT:
			var record_id := Markers.fresh_record_id(scene_root, String(member.get("label")),
				String(member.get("kind")), reserved_records)
			reserved_records[record_id] = true
			member.set("record_id", record_id)
			member.name = record_id
			Markers.reset_copy(member)
			var facing: Vector3 = member.get("facing")
			var turned := pivot.basis.orthonormalized() * facing
			var flat := Vector3(turned.x, 0.0, turned.z)
			if flat.length_squared() > 0.0001:
				member.set("facing", flat.normalized())
			markers.append(member)
		_localize_resources(member)
		for descendant: Node in record.owned:
			_localize_resources(descendant)
	Markers.relink_copies(markers, asset_map, node_map)
	undo_redo.create_action("Place prefab %s (%d members)" % [label, records.size()],
		UndoRedo.MERGE_DISABLE, scene_root)
	for pair: Array in new_containers:
		undo_redo.add_do_method(pair[0], &"add_child", pair[1], true)
		undo_redo.add_do_method(pair[1], &"set_owner", scene_root)
		undo_redo.add_do_reference(pair[1])
	for record: Dictionary in records:
		var member := record.node as Node3D
		undo_redo.add_do_method(record.parent, &"add_child", member, true)
		undo_redo.add_do_method(member, &"set_owner", scene_root)
		for descendant: Node in record.owned:
			undo_redo.add_do_method(descendant, &"set_owner", scene_root)
		undo_redo.add_do_property(member, &"global_transform", record.world)
		undo_redo.add_do_reference(member)
		undo_redo.add_undo_method(record.parent, &"remove_child", member)
		placed.append(member)
	for index in range(new_containers.size() - 1, -1, -1):
		undo_redo.add_undo_method(new_containers[index][0], &"remove_child", new_containers[index][1])
	undo_redo.commit_action()
	prefab.free()
	return placed


## The node a member is placed under: AuthoredAssets for assets, the kind's
## Gameplay container for markers. Missing ones are made (and listed in
## `created` as [parent, node] to add in the undo step); null when a name is
## taken by something that is not a Node3D, or the marker kind is unknown.
static func _container_for(scene_root: Node3D, member: Node3D, known: Dictionary,
		created: Array[Array]) -> Node3D:
	var path := CONTAINER_NAME
	if member.get_script() == MARKER_SCRIPT:
		var kind := String(member.get("kind"))
		if not Markers.KINDS.has(kind):
			return null
		path = "%s/%s" % [Markers.GAMEPLAY, String((Markers.KINDS[kind] as Array)[0])]
	if known.has(path):
		return known[path]
	var parent: Node3D = scene_root
	var walked := ""
	for part in path.split("/"):
		walked = part if walked.is_empty() else walked + "/" + part
		if known.has(walked):
			parent = known[walked]
			continue
		var existing := parent.get_node_or_null(NodePath(part))
		if existing != null and not existing is Node3D:
			return null
		if existing == null:
			existing = Node3D.new()
			existing.name = part
			created.append([parent, existing])
		known[walked] = existing
		parent = existing as Node3D
	return parent


## Where a member lands for a given pivot. With conform_to_ground each member
## keeps its saved height above the terrain instead of the prefab's rigid shape.
static func member_world_transform(scene_root: Node3D, member: Node3D, pivot: Transform3D,
		conform_to_ground: bool, lift: float = 0.0) -> Transform3D:
	var world := pivot * member.transform
	if conform_to_ground and member.has_meta(GROUND_OFFSET_META):
		var ground := Probe.height_at(scene_root, world.origin)
		if not is_nan(ground):
			var offset := float(member.get_meta(GROUND_OFFSET_META)) * pivot.basis.get_scale().y
			world.origin.y = ground + offset + lift
	return world


static func _own_for_packing(copy: Node, prefab: Node3D, original: Node, scene_root: Node) -> void:
	copy.owner = prefab
	for descendant in _descendants(original):
		# Keep instanced content linked: only nodes the edited scene owned (the
		# wrapper's Content instance root, or a starter subtree) join the prefab.
		if descendant.owner != scene_root:
			continue
		var twin := copy.get_node_or_null(original.get_path_to(descendant))
		if twin != null:
			twin.owner = prefab


static func _fresh_asset_id(container: Node, catalog_id: String, fallback: String,
		reserved: Dictionary) -> String:
	var base := (catalog_id if not catalog_id.is_empty() else fallback).to_lower().replace(":", "-")
	for invalid in [" ", ".", "/", "\\", "@", "%"]:
		base = base.replace(invalid, "-")
	while "--" in base:
		base = base.replace("--", "-")
	base = base.trim_prefix("-").trim_suffix("-")
	if base.is_empty():
		base = "asset"
	var used := reserved.duplicate()
	if container != null:
		for child in container.get_children():
			if child.get_script() == ASSET_SCRIPT:
				used[String(child.get("asset_id"))] = true
	var index := 1
	var candidate := "%s-%03d" % [base, index]
	while used.has(candidate):
		index += 1
		candidate = "%s-%03d" % [base, index]
	return candidate


## Gives a placed copy its own Surface/override resources so editing one placed
## prefab never edits another (or the prefab file).
static func _localize_resources(node: Node) -> void:
	for property in node.get_property_list():
		if int(property.usage) & PROPERTY_USAGE_STORAGE == 0 or \
				int(property.usage) & PROPERTY_USAGE_SCRIPT_VARIABLE == 0:
			continue
		var value: Variant = node.get(property.name)
		if value is Resource and _is_local(value as Resource):
			node.set(property.name, (value as Resource).duplicate(true))
		elif value is Array:
			var array := value as Array
			var changed := false
			var copy := array.duplicate()
			for index in copy.size():
				if copy[index] is Resource and _is_local(copy[index] as Resource):
					copy[index] = (copy[index] as Resource).duplicate(true)
					changed = true
			if changed:
				node.set(property.name, copy)


static func _is_local(resource: Resource) -> bool:
	return resource.resource_path.is_empty() or "::" in resource.resource_path


static func _descendants(root: Node) -> Array[Node]:
	var result: Array[Node] = []
	for child in root.get_children():
		result.append(child)
		result.append_array(_descendants(child))
	return result


static func _file_stem(prefab_name: String) -> String:
	var stem := prefab_name.strip_edges().to_snake_case()
	var cleaned := ""
	for character in stem:
		if character.is_valid_identifier() or character.is_valid_int():
			cleaned += character
		elif not cleaned.ends_with("_"):
			cleaned += "_"
	return cleaned.trim_prefix("_").trim_suffix("_")

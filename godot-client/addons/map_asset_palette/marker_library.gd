@tool
extends RefCounted
## Gameplay markers for the Map Assets palette.
##
## Every marker kind the region snapshot exports gets a plain entry. The open
## territory also contributes templates copied from its own markers: a new
## crystal node takes the label, harvest hook and extent that the scene's
## existing crystals use. Position-specific extras (prop positions, destination
## tiles, rotations) are never copied. New markers get fresh record ids and go
## into the saved Gameplay containers as one undo step. Runtime points are
## deliberately absent: they bind certified server records, which are never
## invented in the editor.

const MARKER_SCRIPT := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const CATEGORY := "Gameplay markers"
const ID_PREFIX := "marker:"
const GAMEPLAY := "Gameplay"
const MAX_TEMPLATES_PER_KIND := 10
## kind -> [container below Gameplay, display name, colour]
const KINDS := {
	"spawn": ["Spawns", "Spawn point", Color(0.35, 0.95, 0.45)],
	"portal": ["Portals", "Portal", Color(0.78, 0.48, 1.0)],
	"npc_marker": ["NpcMarkers", "NPC", Color(0.38, 0.66, 1.0)],
	"harvestable": ["Harvestables", "Harvestable", Color(1.0, 0.62, 0.22)],
	"interactive": ["Interactives", "Interactive", Color(0.3, 0.9, 0.95)],
	"landmark": ["Landmarks", "Landmark", Color(1.0, 0.9, 0.42)],
	"ambient_population": ["AmbientPopulation", "Herd / ambient animals", Color(0.96, 0.5, 0.72)],
}
const RUNTIME_POINT_COLOR := Color(0.62, 0.64, 0.68)
## Extras tied to one placement, never copied into a new marker.
const PLACEMENT_EXTRAS := ["propPosition", "destinationTile", "rotationDegrees", "reachable"]


static func color_for(kind: String) -> Color:
	return (KINDS[kind] as Array)[2] if KINDS.has(kind) else RUNTIME_POINT_COLOR


static func is_marker_entry(entry: Dictionary) -> bool:
	return bool(entry.get("marker", false))


## Palette entries for the open scene; empty when it has no Gameplay container.
static func entries(root: Node) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if root == null or root.get_node_or_null(GAMEPLAY) == null:
		return result
	var existing := markers(root)
	for kind: String in KINDS:
		var spec: Array = KINDS[kind]
		result.append(_entry(kind, String(spec[1]), "", {}, "plain"))
		var groups := {}
		for marker in existing:
			if String(marker.get("kind")) != kind:
				continue
			var key := _template_key(kind, marker)
			if key.is_empty():
				continue
			if not groups.has(key):
				groups[key] = {"count": 0, "marker": marker}
			groups[key].count += 1
		var keys := groups.keys()
		keys.sort_custom(func(a: String, b: String) -> bool:
			return int(groups[a].count) > int(groups[b].count) or \
				(int(groups[a].count) == int(groups[b].count) and a < b))
		for index in mini(keys.size(), MAX_TEMPLATES_PER_KIND):
			var key: String = keys[index]
			var sample: Node = groups[key].marker
			result.append(_entry(kind, "%s: %s" % [String(spec[1]), key],
				_template_label(kind, sample), _template_extras(sample), key))
	return result


## Every saved gameplay marker below Gameplay, in scene order.
static func markers(root: Node) -> Array[Node]:
	var result: Array[Node] = []
	var gameplay := root.get_node_or_null(GAMEPLAY) if root != null else null
	if gameplay == null:
		return result
	for child in gameplay.find_children("*", "Marker3D", true, false):
		if child.get_script() == MARKER_SCRIPT:
			result.append(child)
	return result


## A stand-in pin for ghosts and thumbnails: a post with a head, in kind colour.
static func pin_node(kind: String) -> Node3D:
	var root := Node3D.new()
	root.name = "MarkerPin"
	var material := StandardMaterial3D.new()
	material.albedo_color = color_for(kind)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var post := MeshInstance3D.new()
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = 0.06
	cylinder.bottom_radius = 0.06
	cylinder.height = 2.2
	cylinder.material = material
	post.mesh = cylinder
	post.position = Vector3(0.0, 1.1, 0.0)
	root.add_child(post)
	var head := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.32
	sphere.height = 0.64
	sphere.material = material
	head.mesh = sphere
	head.position = Vector3(0.0, 2.35, 0.0)
	root.add_child(head)
	var base := MeshInstance3D.new()
	var disc := CylinderMesh.new()
	disc.top_radius = 0.7
	disc.bottom_radius = 0.7
	disc.height = 0.04
	disc.material = material
	base.mesh = disc
	base.position = Vector3(0.0, 0.02, 0.0)
	root.add_child(base)
	return root


## A new marker node for `entry` at `world_position`, facing along `facing`.
static func create_marker(root: Node3D, entry: Dictionary, world_position: Vector3,
		facing: Vector3) -> Node3D:
	var kind := String(entry.get("marker_kind", "landmark"))
	var marker: Node3D = MARKER_SCRIPT.new()
	var identity := fresh_record_id(root, String(entry.get("marker_label", "")), kind)
	marker.name = identity
	marker.set("record_id", identity)
	marker.set("kind", kind)
	marker.set("label", String(entry.get("marker_label", "")))
	var extras: Dictionary = (entry.get("marker_extras", {}) as Dictionary).duplicate(true)
	if kind == "ambient_population" and extras.has("seed"):
		extras["seed"] = randi() % 100000
	marker.set("extras", extras)
	var flat := Vector3(facing.x, 0.0, facing.z)
	marker.set("facing", flat.normalized() if flat.length_squared() > 0.0001 else Vector3.FORWARD)
	marker.position = world_position
	return marker


## Adds `marker` (positioned in world space) below its kind's container in
## Gameplay as one undo step, creating that container if the scene lacks it.
## Returns the container's path.
static func commit_with_undo(undo_redo: EditorUndoRedoManager, root: Node3D,
		marker: Node3D) -> String:
	var kind := String(marker.get("kind"))
	var gameplay := root.get_node(GAMEPLAY) as Node3D
	var container_name := String((KINDS[kind] as Array)[0])
	var container := gameplay.get_node_or_null(NodePath(container_name)) as Node3D
	var new_container := container == null
	if new_container:
		container = Node3D.new()
		container.name = container_name
	var world_position := marker.position
	undo_redo.create_action("Place %s marker %s" % [kind, String(marker.get("record_id"))],
		UndoRedo.MERGE_DISABLE, root)
	if new_container:
		undo_redo.add_do_method(gameplay, &"add_child", container, true)
		undo_redo.add_do_method(container, &"set_owner", root)
		undo_redo.add_do_reference(container)
	undo_redo.add_do_method(container, &"add_child", marker, true)
	undo_redo.add_do_method(marker, &"set_owner", root)
	undo_redo.add_do_property(marker, &"global_position", world_position)
	undo_redo.add_do_reference(marker)
	undo_redo.add_undo_method(container, &"remove_child", marker)
	if new_container:
		undo_redo.add_undo_method(gameplay, &"remove_child", container)
	undo_redo.commit_action()
	return "%s/%s" % [GAMEPLAY, container_name]


## What every copied gameplay marker loses, whatever made the copy (copy-drag,
## Duplicate, the shared-id fix, a prefab): runtime bindings name certified
## server records of the original, a territory has one default spawn, and
## prop positions, destination tiles, rotations and reachability describe the
## original's placement. Portal destinations are kept and reported instead.
static func reset_copy(marker: Node) -> void:
	var unbound: Array[Dictionary] = []
	marker.set("runtime_bindings", unbound)
	marker.set("default_spawn", false)
	var extras: Dictionary = (marker.get("extras") as Dictionary).duplicate(true)
	for key: String in PLACEMENT_EXTRAS:
		extras.erase(key)
	marker.set("extras", extras)


## Copied markers that followed or linked to a copied asset now follow or link
## to its copy (`asset_map` old asset id -> new, `node_map` old node name ->
## new); ones copied without their asset would jump back onto the original,
## so they stop following and lose the link.
static func relink_copies(copies: Array, asset_map: Dictionary, node_map: Dictionary) -> void:
	for marker: Node in copies:
		if marker.get_script() != MARKER_SCRIPT:
			continue
		var followed := String(marker.get("follow_asset_id"))
		if not followed.is_empty():
			marker.set("follow_asset_id", String(asset_map.get(followed, "")))
		var linked := String(marker.get("linked_node_name"))
		if not linked.is_empty():
			marker.set("linked_node_name", String(node_map.get(linked, "")))


## A note for the status line about what copies still need a look, or "".
static func copy_review_note(copies: Array) -> String:
	var portals := 0
	for copy: Node in copies:
		if copy.get_script() != MARKER_SCRIPT:
			continue
		if String(copy.get("kind")) == "portal" and (not String(copy.get("destination_map")).is_empty() or
				not String(copy.get("destination_spawn")).is_empty()):
			portals += 1
	if portals == 0:
		return ""
	return "%d copied portal%s still lead%s to the original's destination; check %s in the Inspector" % [
		portals, "" if portals == 1 else "s", "s" if portals == 1 else "", "it" if portals == 1 else "them"]


## `<slug>-NN`, unique across every gameplay marker of the territory and any
## ids already handed out in the same batch (`reserved`).
static func fresh_record_id(root: Node, label: String, kind: String,
		reserved: Dictionary = {}) -> String:
	var base := label.strip_edges().to_lower() if not label.strip_edges().is_empty() \
		else String((KINDS.get(kind, ["", kind]) as Array)[1]).to_lower()
	var cleaned := ""
	for character in base:
		if character.is_valid_identifier() or character.is_valid_int():
			cleaned += character
		elif not cleaned.ends_with("-"):
			cleaned += "-"
	cleaned = cleaned.replace("_", "-").trim_prefix("-").trim_suffix("-")
	if cleaned.is_empty():
		cleaned = "marker"
	var used := reserved.duplicate()
	for marker in markers(root):
		used[String(marker.get("record_id"))] = true
	var index := 1
	var candidate := "%s-%02d" % [cleaned, index]
	while used.has(candidate):
		index += 1
		candidate = "%s-%02d" % [cleaned, index]
	return candidate


static func _entry(kind: String, label: String, marker_label: String, extras: Dictionary,
		key: String) -> Dictionary:
	return {
		"id": "%s%s:%s" % [ID_PREFIX, kind, key.to_lower().replace(" ", "-")],
		"label": label,
		"category": CATEGORY,
		"scene_path": "",
		"source_node": "",
		"height": 0.0,
		"marker": true,
		"marker_kind": kind,
		"marker_label": marker_label,
		"marker_extras": extras,
		"search_text": "%s %s %s marker %s" % [label, kind, marker_label, key],
	}


static func _template_key(kind: String, marker: Node) -> String:
	var extras: Dictionary = marker.get("extras")
	var label := String(marker.get("label"))
	match kind:
		"harvestable":
			var family := String(extras.get("kind", ""))
			return "%s (%s)" % [label, family] if not family.is_empty() else label
		"npc_marker":
			return String(extras.get("role", ""))
		"ambient_population":
			return String(extras.get("model", ""))
		"interactive", "landmark":
			return String(extras.get("kind", ""))
	return ""


static func _template_label(kind: String, marker: Node) -> String:
	# Harvestables share a resource name; NPCs, landmarks and interactives are
	# individuals, so a new one starts unnamed rather than as a copy.
	return String(marker.get("label")) if kind == "harvestable" else ""


static func _template_extras(marker: Node) -> Dictionary:
	var extras: Dictionary = (marker.get("extras") as Dictionary).duplicate(true)
	for key: String in PLACEMENT_EXTRAS:
		extras.erase(key)
	return extras

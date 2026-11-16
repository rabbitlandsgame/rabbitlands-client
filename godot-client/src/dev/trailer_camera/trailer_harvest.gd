extends RefCounted
## Harvest nodes for a trailer or audit still. The trailer camera loads a map
## offline, with no server, so the harvest nodes the server lists in the game
## are not there. With ELORIA_TRAILER_HARVEST set it stands the map package's
## own harvestables near the shot as the game would: MapObject3D nodes with the
## package's (or the underground's) presentation, on the walk surface.
##
## ELORIA_TRAILER_HARVEST:
## - "after": as the game draws them now: seated on the ground under their
##   footprint (MapObject3D.set_surface_height) and, on a dark interior, with
##   the cave glint (harvest_glint.gd);
## - "before": as the game drew them before the 2026-11-16 map polish: level
##   at their tile centre's height, 5 cm up, and no glint;
## - unset or anything else: no harvest nodes (the scenery-only stills).

const VARIABLE := "ELORIA_TRAILER_HARVEST"
const CATALOG := "res://data/world/objects.json"
const GLINT := preload("res://src/world/harvest_glint.gd")
const UNDERGROUND := preload("res://src/world/underground_scenery.gd")
## Nodes farther than this from every sample of the shot's path are left out.
const REACH_METRES := 90.0

## The mode the environment asks for, or "".
static func mode() -> String:
	var value := OS.get_environment(VARIABLE).strip_edges().to_lower()
	return value if value in ["before", "after"] else ""

## Stands the harvest nodes of `manifest` (map `map_id`, whose registry entry is
## `registered`) within REACH_METRES of `points` under `parent`, on the ground
## `ground_at` finds (a Callable(Vector3) -> float, NAN for none). Returns how
## many were placed.
static func place(parent: Node3D, manifest: WorldManifest, map_id: String, registered: Dictionary,
		points: PackedVector3Array, ground_at: Callable) -> int:
	var wanted := mode()
	if wanted.is_empty() or manifest == null:
		return 0
	var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
	if catalog is not Dictionary:
		return 0
	var main_script: Script = load("res://src/app/main.gd")
	var presentation: Dictionary = main_script.call("map_presentation_of", map_id, manifest.data, {},
		UNDERGROUND.harvest_presentation(map_id))
	var nodes: Dictionary = presentation.get("nodes", {})
	var glint := wanted == "after" and GLINT.wanted_for(manifest.data, registered)
	var adapter := manifest.coordinate_adapter()
	var placed := 0
	for value: Variant in manifest.data.get("harvestables", []):
		if value is not Dictionary:
			continue
		var entry := value as Dictionary
		var tile: Variant = entry.get("serverTile")
		if tile is not Array or (tile as Array).size() != 2:
			continue
		var identity := int(entry.get("objectId", -1))
		var centre := adapter.tile_center(int(tile[0]), int(tile[1]))
		var near := false
		for point: Vector3 in points:
			if Vector2(point.x - centre.x, point.z - centre.z).length() <= REACH_METRES:
				near = true
				break
		if not near:
			continue
		var node := MapObject3D.new()
		node.configure({"object_id": identity, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
			"x": int(tile[0]), "y": int(tile[1]), "label": str(entry.get("resource", "")), "detail": ""},
			adapter, catalog as Dictionary, false, nodes.get(identity, {}) as Dictionary)
		parent.add_child(node)
		var height := float(ground_at.call(node.global_position + Vector3.UP * 2.0))
		if is_nan(height):
			continue
		if wanted == "after":
			node.set_cave_glint(glint)
			node.set_surface_height(height)
		else:
			node.global_position.y = height + 0.05
		placed += 1
	print("trailer harvest mode=%s map=%s placed=%d glint=%s roofs_hidden=%d" % [wanted, map_id, placed,
		glint, _hide_roofs(manifest, parent)])
	return placed

## An interior's roofs, hidden as the game's cutaway hides them (its manifest's
## `cutaway.hideNodes`), so a still looks into the cave as the game camera does.
static func _hide_roofs(manifest: WorldManifest, parent: Node3D) -> int:
	var cutaway: Variant = manifest.data.get("cutaway")
	if cutaway is not Dictionary:
		return 0
	var hidden := 0
	for value: Variant in (cutaway as Dictionary).get("hideNodes", []):
		var found := parent.find_child(str(value), true, false) as Node3D
		if found != null:
			found.visible = false
			hidden += 1
	return hidden

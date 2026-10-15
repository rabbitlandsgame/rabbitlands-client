@tool
extends RefCounted
## Walkability overlay for authored territories, in three modes:
##
## - PUBLISHED: the exact served grid, read from the territory's published
##   collision.bin (EWCG-v2, half-metre cells). This is what the server walks
##   today, as of the last publish.
## - LIVE: a suggestion computed from the current authoring on 1 m tiles, using
##   the pipeline's rules (collision_export.py): the grade of the terrain
##   triangle is at most MAX_GRADE, water no deeper than WADE, no solid
##   structure in the actor's body height, and inside the owned polygon.
##   Grade, ownership, solids and Walk_ decks follow the bake on its half-metre
##   cells (structure_raster.gd; a continent-v2 territory adds
##   export_collision.py's tree-trunk, enclosed-floor and harvest-node rules,
##   see continent_v2), folded to tiles as the server folds them: a
##   tile is blocked when any of its half-cells is. Solids are checked on a
##   worker thread; until an asset's check finishes it is estimated from its
##   mesh boxes. Water is tested on the same half-cells against where the
##   actor stands (deck or terrain): the sea level, the authored rivers and
##   lakes, and the continent plan's water the territory has not claimed
##   (plan_water.gd). Decks and solids the composer adds outside the scene
##   (thresholds, cave doors, discovery decks) come read-only from the
##   published package (published_context.gd). The certified halo and seam
##   collar at borders are not modelled, so the bake can still differ there.
## - CHANGES: where LIVE disagrees with PUBLISHED, i.e. what the next bake is
##   likely to open or close.
##
## The tint is a second draw of the terrain preview mesh with a small shader;
## it is internal and ownerless, so it is never saved or baked.

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const TopDown := preload("res://addons/map_authoring_usability/top_down_capture.gd")
const TimeOfDay := preload("res://addons/map_authoring_usability/time_of_day_preview.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const WATER_SCRIPT := preload("res://src/dev/map_authoring_region/water_region_control.gd")
const Structures := preload("res://addons/map_authoring_usability/structure_raster.gd")
const PlanWater := preload("res://addons/map_authoring_usability/plan_water.gd")
const Published := preload("res://addons/map_authoring_usability/published_context.gd")
const MARKER_SCRIPT := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")
const NODE_NAME := "__MapAuthoringWalkability"

enum Mode { OFF, PUBLISHED, LIVE, CHANGES }
enum Tile { OUTSIDE, WALKABLE, STEEP, WATER, BLOCKED, DECK }

const MAX_GRADE := 0.65
const WADE := 0.35
## The actor body the bake tests solids against runs from standing + 0.06 m to
## standing + 2.10 m (collision_export.py: ACTOR_HEIGHT is the top, not a length).
const ACTOR_FLOOR_CLEARANCE := 0.06
const ACTOR_HEIGHT := 2.1
const TILE_NAMES := ["outside this territory", "walkable", "too steep", "under water",
	"blocked by a structure", "bridge or walk deck"]
const LEGEND := {
	Mode.PUBLISHED: [["walkable (published)", Color(0.25, 0.85, 0.35)],
		["not walkable (published)", Color(0.9, 0.25, 0.25)]],
	Mode.LIVE: [["walkable", Color(0.25, 0.85, 0.35)], ["too steep (> 0.65)", Color(1.0, 0.6, 0.15)],
		["under water (> 0.35 m; sea, rivers, lakes)", Color(0.2, 0.5, 1.0)],
		["blocked by a structure", Color(0.9, 0.2, 0.25)],
		["bridge / walk deck", Color(0.3, 0.95, 0.9)]],
	Mode.CHANGES: [["newly walkable", Color(0.3, 1.0, 0.6)],
		["newly blocked", Color(1.0, 0.25, 0.8)]],
}
const SHADER_CODE := """
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, blend_mix;

uniform sampler2D live_classes : filter_nearest, repeat_disable;
uniform sampler2D owned_mask : filter_nearest, repeat_disable;
uniform sampler2D published : filter_nearest, repeat_disable;
uniform mat4 region_inverse;
uniform vec4 live_rect;
uniform vec4 published_rect;
uniform int mode = 2;
uniform bool has_published = false;
uniform float opacity = 0.5;
varying vec3 local_position;

void vertex() {
	VERTEX += NORMAL * 0.06;
	local_position = (region_inverse * MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

vec3 live_color(float value) {
	if (value < 1.5) return vec3(0.25, 0.85, 0.35);
	if (value < 2.5) return vec3(1.0, 0.6, 0.15);
	if (value < 3.5) return vec3(0.2, 0.5, 1.0);
	if (value < 4.5) return vec3(0.9, 0.2, 0.25);
	return vec3(0.3, 0.95, 0.9);
}

void fragment() {
	vec2 luv = (local_position.xz - live_rect.xy) / live_rect.zw;
	vec2 puv = vec2((local_position.x - published_rect.x) / published_rect.z,
		(published_rect.y - local_position.z) / published_rect.w);
	bool in_live = all(greaterThanEqual(luv, vec2(0.0))) && all(lessThan(luv, vec2(1.0)));
	bool in_published = has_published && all(greaterThanEqual(puv, vec2(0.0))) &&
		all(lessThan(puv, vec2(1.0)));
	float value = in_live ? floor(texture(live_classes, luv).r * 255.0 + 0.5) : 0.0;
	bool owned = in_live && texture(owned_mask, luv).a > 0.5;
	bool published_walk = in_published && texture(published, puv).r > 0.0;
	vec3 color = vec3(0.0);
	if (mode == 1) {
		if (!in_published) discard;
		color = published_walk ? vec3(0.25, 0.85, 0.35) : vec3(0.9, 0.25, 0.25);
	} else if (mode == 2) {
		if (!owned || value < 0.5) discard;
		color = live_color(value);
	} else {
		if (!owned || !in_published) discard;
		bool live_walk = value > 0.5 && (value < 1.5 || value > 4.5);
		if (live_walk == published_walk) discard;
		color = live_walk ? vec3(0.3, 1.0, 0.6) : vec3(1.0, 0.25, 0.8);
	}
	ALBEDO = color;
	ALPHA = opacity;
}
"""

var mode := Mode.OFF
var last_message := ""
var _root: Node3D
var _node: MeshInstance3D
var _material: ShaderMaterial
var _live: Dictionary = {}
var _published: Dictionary = {}
var _live_signature := ""
var _pending_signature := ""
var _pending_since := 0
## Exact structure results by asset: key -> {signature, cells}. Kept across
## rebuilds, so an edit re-checks only the assets it touched.
var _structure_cache := {}
var _group_task := -1
var _group_jobs: Array = []
var _group_cancel: Array = [false]
var _notice := ""


## Shows `next_mode` on `root`; builds whatever data the mode needs.
func set_mode(root: Node3D, next_mode: int) -> bool:
	mode = next_mode
	if mode == Mode.OFF or root == null or Probe.region_terrain(root) == null:
		release()
		if mode != Mode.OFF:
			last_message = "The walkability overlay needs a territory with region terrain."
			mode = Mode.OFF
		return false
	if _root != root:
		release()
		mode = next_mode
		_root = root
	if _published.is_empty():
		_published = published_grid(root)
	if mode in [Mode.PUBLISHED, Mode.CHANGES] and _published.has("error"):
		# Nothing to show or compare against: say why and switch off.
		var reason := String(_published.error)
		release()
		mode = Mode.OFF
		last_message = reason
		return false
	if mode in [Mode.LIVE, Mode.CHANGES] and _live.is_empty():
		_rebuild_live()
	return _apply()


## Recomputes LIVE now, structures included (the overlay otherwise waits for
## edits to settle and checks structures in the background).
func rebuild() -> void:
	if _root != null and is_instance_valid(_root) and mode in [Mode.LIVE, Mode.CHANGES]:
		_rebuild_live(true)
		_apply()


func is_active() -> bool:
	return mode != Mode.OFF and _node != null and is_instance_valid(_node)


func node() -> MeshInstance3D:
	return _node if _node != null and is_instance_valid(_node) else null


func live_data() -> Dictionary:
	return _live


func published_data() -> Dictionary:
	return _published


## Call regularly: rebuilds LIVE after the terrain or blockers stop changing.
func poll(dragging: bool) -> void:
	if _root == null or not is_instance_valid(_root) or mode == Mode.OFF:
		return
	_sync_mesh()
	_collect_structures()
	if not mode in [Mode.LIVE, Mode.CHANGES] or dragging:
		return
	var signature := live_signature(_root)
	if signature == _live_signature:
		_pending_signature = ""
		return
	if signature != _pending_signature:
		_pending_signature = signature
		_pending_since = Time.get_ticks_msec()
		return
	if Time.get_ticks_msec() - _pending_since >= 600:
		_rebuild_live()
		_apply()


func release() -> void:
	_stop_structures()
	if _node != null and is_instance_valid(_node):
		if _node.get_parent() != null:
			_node.get_parent().remove_child(_node)
		_node.queue_free()
	_node = null
	_root = null
	_live = {}
	_published = {}
	_live_signature = ""
	_pending_signature = ""


## What the cursor tile is, for the readout line. Empty when the overlay is off.
func describe(local: Vector3) -> String:
	if mode == Mode.OFF:
		return ""
	var parts := PackedStringArray()
	if not _published.is_empty() and not _published.has("error"):
		var walk: Variant = published_walkable(local)
		if walk != null:
			parts.append("published %s" % ("walkable" if walk else "not walkable"))
	if not _live.is_empty():
		var tile := live_tile(local)
		if tile >= 0:
			var text := String(TILE_NAMES[tile])
			if tile == Tile.STEEP:
				text += " (grade %.2f)" % grade_at(local)
			elif tile == Tile.BLOCKED:
				var index := _live_index(local)
				text = "blocked by %s" % String(_live.blockers.get(index, "a structure"))
			elif tile == Tile.DECK:
				text = "deck of %s" % String(_live.decks.get(_live_index(local), "a bridge"))
			parts.append("live %s" % text)
	return "  ·  ".join(parts)


func legend() -> Array:
	var items: Array = (LEGEND.get(mode, []) as Array).duplicate(true)
	if mode == Mode.LIVE and structures_pending() > 0:
		for item: Array in items:
			if String(item[0]) == "blocked by a structure":
				item[0] = "blocked by a structure (%d still box estimates)" % structures_pending()
	return items


## Solid assets whose exact check is still running (they show box estimates).
func structures_pending() -> int:
	return _group_jobs.size() if _group_task >= 0 else 0


## A one-off status line (the background check finishing), then "".
func take_notice() -> String:
	var notice := _notice
	_notice = ""
	return notice


## -1 outside the live grid, else a Tile value.
func live_tile(local: Vector3) -> int:
	var index := _live_index(local)
	if index < 0:
		return -1
	if not bool(_live.owned.get_pixel(index % int(_live.width),
			index / int(_live.width)).a > 0.5):
		return Tile.OUTSIDE
	return int((_live.classes as PackedByteArray)[index])


## true / false inside the published grid, null outside it or without one.
func published_walkable(local: Vector3) -> Variant:
	if _published.is_empty() or _published.has("error"):
		return null
	var column := floori((local.x - float(_published.x0)) / float(_published.cell))
	var row := floori((float(_published.z1) - local.z) / float(_published.cell))
	if column < 0 or row < 0 or column >= int(_published.width) or row >= int(_published.rows):
		return null
	return (_published.bytes as PackedByteArray)[row * int(_published.width) + column] > 0


## The pipeline's grade: the plane slope of the terrain triangle under `local`.
func grade_at(local: Vector3) -> float:
	if _live.is_empty():
		return NAN
	return _grade(_live, local.x, local.z)


static func _grade(data: Dictionary, x: float, z: float) -> float:
	var heights: PackedFloat32Array = data.heights
	var grid: Vector2i = data.grid
	var cell := float(data.cell)
	var fx := clampf((x - float(data.terrain_x0)) / cell, 0.0, float(grid.x) - 1.0000001)
	var fz := clampf((z - float(data.terrain_z0)) / cell, 0.0, float(grid.y) - 1.0000001)
	var ix := mini(floori(fx), grid.x - 2)
	var iz := mini(floori(fz), grid.y - 2)
	var u := fx - float(ix)
	var v := fz - float(iz)
	var a := heights[iz * grid.x + ix]
	var b := heights[iz * grid.x + ix + 1]
	var c := heights[(iz + 1) * grid.x + ix]
	var d := heights[(iz + 1) * grid.x + ix + 1]
	var dx := (b - a if u + v <= 1.0 else d - c) / cell
	var dz := (c - a if u + v <= 1.0 else d - b) / cell
	return sqrt(dx * dx + dz * dz)


## The published grid of the open territory, from its package's collision block
## (the published package TimeOfDay finds for the territory, or `manifest_override`).
static func published_grid(root: Node3D, manifest_override := "") -> Dictionary:
	var manifest_path := manifest_override if not manifest_override.is_empty() else \
		TimeOfDay.published_manifest_path_for(String(root.get("region_id")))
	if manifest_path.is_empty():
		return {"error": "No published manifest for this territory, so no published grid."}
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not manifest is Dictionary or not (manifest as Dictionary).get("collision") is Dictionary:
		return {"error": "The published manifest has no collision block."}
	var collision: Dictionary = manifest.collision
	var binary := manifest_path.get_base_dir().path_join(String(collision.get("binary",
		collision.get("file", "collision.bin"))))
	if not FileAccess.file_exists(binary):
		return {"error": "Published collision grid is missing: %s" % binary}
	var bytes := FileAccess.get_file_as_bytes(binary)
	if bytes.size() < 16 or bytes.slice(0, 4).get_string_from_ascii() != "EWCG":
		return {"error": "%s is not an EWCG grid." % binary.get_file()}
	var width := bytes.decode_u32(8)
	var rows := bytes.decode_u32(12)
	var grid := bytes.slice(16)
	if width <= 0 or rows <= 0 or grid.size() != width * rows:
		return {"error": "%s has an unexpected size." % binary.get_file()}
	var origin: Array = collision.get("originMetres", [0.0, 0.0])
	var image := Image.create_from_data(width, rows, false, Image.FORMAT_L8, grid)
	# A walkable cell's byte is its height code: origin + code * step metres.
	var encoding: Dictionary = collision.get("heightEncoding", {}) \
		if collision.get("heightEncoding") is Dictionary else {}
	return {"bytes": grid, "width": width, "rows": rows, "x0": float(origin[0]),
		"z1": float(origin[1]), "cell": float(collision.get("cellMetres", 0.5)),
		"texture": ImageTexture.create_from_image(image), "path": binary,
		"walkable_fraction": float(collision.get("walkableFraction", NAN)),
		"height_origin": float(encoding.get("origin", NAN)),
		"height_step": float(encoding.get("step", NAN))}


const CONTINENT_PLAN_PATH := 	"res://../eloria-assets/maps/nymara-regions/_continent/diagonal-plan.json"


## The sea level the bake floods to, or null for a territory with no published
## manifest. The authoring scene has no sea node, so LIVE compares the saved
## heights against this level. The manifest states it for some territories;
## the rest take the continent plan's sea_level, as the bake itself does.
static func manifest_sea_level(root: Node3D) -> Variant:
	var manifest_path := TimeOfDay.manifest_path_for(String(root.get("region_id")))
	if manifest_path.is_empty():
		return null
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if manifest is Dictionary:
		var water: Variant = ((manifest as Dictionary).get("environment", {}) as Dictionary).get("water")
		if water is Dictionary and (water as Dictionary).has("seaLevel"):
			return float(water.seaLevel)
	if FileAccess.file_exists(CONTINENT_PLAN_PATH):
		var plan: Variant = JSON.parse_string(FileAccess.get_file_as_string(CONTINENT_PLAN_PATH))
		if plan is Dictionary and (plan as Dictionary).has("sea_level"):
			return float(plan.sea_level)
	return 0.0


## Cheap fingerprint of everything LIVE depends on.
static func live_signature(root: Node3D) -> String:
	var terrain := Probe.region_terrain(root)
	var parts := PackedStringArray([str(terrain.get("preview_revision")) if terrain != null else "-"])
	var assets := root.get_node_or_null("AuthoredAssets")
	if assets != null:
		for child in assets.get_children():
			if child.get_script() == ASSET_SCRIPT and String(child.get("collision_role")) != "none":
				parts.append("%s%s" % [String(child.get("collision_role")),
					str((child as Node3D).global_transform)])
	for container in ["WaterRegions", "Bridges", "Rivers"]:
		var node := root.get_node_or_null(container)
		if node == null:
			continue
		for child in node.find_children("*", "Node3D", true, false):
			parts.append("%s%s" % [child.name, str((child as Node3D).global_transform)])
			if child is Path3D and (child as Path3D).curve != null:
				parts.append(str((child as Path3D).curve.get_baked_points().size()))
	return str(hash("|".join(parts)))


func _rebuild_live(exact_now := false) -> void:
	var started := Time.get_ticks_msec()
	_live = compute_live(_root, _structure_cache, not exact_now)
	_live_signature = live_signature(_root)
	_pending_signature = ""
	if _live.has("error"):
		last_message = String(_live.error)
		_live = {}
		return
	_start_structures()
	var pending := (_live.pending as Array).size()
	last_message = "Live walkability rebuilt in %d ms (%d × %d tiles)%s." % [
		Time.get_ticks_msec() - started, int(_live.width), int(_live.rows),
		"; %d of %d solid assets are box estimates until their exact check finishes" % [
			pending, int(_live.solids)] if pending > 0 else ""]


## Hands the solids LIVE could not take from the cache to a worker group.
func _start_structures() -> void:
	if _group_task >= 0 or _live.is_empty():
		return
	var jobs: Array = _live.get("pending", [])
	if jobs.is_empty():
		return
	var ground: Dictionary = _live.ground
	var cancel: Array = [false]
	_group_cancel = cancel
	_group_jobs = jobs
	var work := func(index: int) -> void:
		if cancel[0]:
			return
		var job: Dictionary = jobs[index]
		job["cells"] = Structures.blocked_cells(job.parts, ground, job.enclose, job.deck)
	_group_task = WorkerThreadPool.add_group_task(work, jobs.size(),
		clampi(OS.get_processor_count() / 2, 1, 4), false, "Live walkability structures")


## Takes finished exact results into the cache and redraws with them.
func _collect_structures() -> void:
	if _group_task < 0 or not WorkerThreadPool.is_group_task_completed(_group_task):
		return
	WorkerThreadPool.wait_for_group_task_completion(_group_task)
	_group_task = -1
	var finished := 0
	for job: Dictionary in _group_jobs:
		if job.has("cells"):
			_structure_cache[job.key] = {"signature": job.signature, "cells": job.cells}
			finished += 1
	_group_jobs = []
	if bool(_group_cancel[0]) or finished == 0 or not mode in [Mode.LIVE, Mode.CHANGES]:
		return
	_rebuild_live()
	_apply()
	if structures_pending() == 0:
		_notice = "Live walkability: every solid asset now checked exactly (%d)." % int(_live.solids)


func _stop_structures() -> void:
	if _group_task >= 0:
		_group_cancel[0] = true
		WorkerThreadPool.wait_for_group_task_completion(_group_task)
		_group_task = -1
	_group_jobs = []


## The territory's terrain as the grade and ground samplers read it
## (_grade, _ground, structure_raster.terrain_at), or {"error"}.
static func terrain_frame(root: Node3D) -> Dictionary:
	var terrain := Probe.region_terrain(root)
	if terrain == null:
		return {"error": "No region terrain."}
	var heights: PackedFloat32Array = terrain.call("effective_heights")
	var grid: Vector2i = terrain.get("grid_size")
	var origin: Vector2 = terrain.get("origin")
	if heights.size() != grid.x * grid.y or grid.x < 2 or grid.y < 2:
		return {"error": "The terrain height grid is not ready."}
	var terrain_to_root: Transform3D = root.global_transform.affine_inverse() * terrain.global_transform
	var terrain_origin: Vector3 = terrain_to_root * Vector3(origin.x, 0.0, origin.y)
	return {"heights": heights, "grid": grid, "cell": float(terrain.get("cell_metres")),
		"terrain_x0": terrain_origin.x, "terrain_z0": terrain_origin.z}


## The LIVE classification on 1 m tiles (or the territory's metres per tile).
## Solid assets are checked exactly, reusing `cache` (key -> {signature,
## cells}) where their meshes and ground are unchanged; with `defer` the rest
## are estimated from their mesh boxes and listed in "pending" for a worker
## (with "ground", the frame they need), instead of being checked here.
static func compute_live(root: Node3D, cache: Variant = null, defer := false) -> Dictionary:
	var terrain := Probe.region_terrain(root)
	if terrain == null:
		return {"error": "No region terrain."}
	var heights: PackedFloat32Array = terrain.call("effective_heights")
	var grid: Vector2i = terrain.get("grid_size")
	var cell: float = terrain.get("cell_metres")
	var origin: Vector2 = terrain.get("origin")
	if heights.size() != grid.x * grid.y or grid.x < 2 or grid.y < 2:
		return {"error": "The terrain height grid is not ready."}
	var terrain_to_root: Transform3D = root.global_transform.affine_inverse() * terrain.global_transform
	var terrain_origin: Vector3 = terrain_to_root * Vector3(origin.x, 0.0, origin.y)
	var tile := float(root.get("metres_per_tile")) if root.get("metres_per_tile") != null else 1.0
	tile = tile if tile > 0.0 else 1.0
	var width := roundi(float(grid.x - 1) * cell / tile)
	var rows := roundi(float(grid.y - 1) * cell / tile)
	var classes := PackedByteArray()
	classes.resize(width * rows)
	classes.fill(Tile.WALKABLE)
	var data := {"heights": heights, "grid": grid, "cell": cell, "tile": tile,
		"terrain_x0": terrain_origin.x, "terrain_z0": terrain_origin.z,
		"x0": terrain_origin.x, "z0": terrain_origin.z, "width": width, "rows": rows,
		"classes": classes, "blockers": {}, "decks": {}}
	_grade_pass(data)
	var v2 := continent_v2(root)
	var shapes := Structures.gather(root, v2)
	var published := Published.context_for(root)
	var decks: Array = shapes.decks.duplicate()
	for deck: Dictionary in published.get("decks", []):
		decks.append({"name": "published %s" % String(deck.name), "triangles": deck.triangles})
	var solids: Array = shapes.solids.duplicate()
	solids.append_array(published_solids(published))
	var ground := Structures.ground_frame(data)
	_deck_pass(root, data, ground, decks)
	_water_pass(root, data, ground)
	_structure_pass(data, ground, solids, cache if cache is Dictionary else {}, defer)
	if v2:
		harvest_pass(root, data, ground)
	data.ground = ground
	data.published_decks = (published.get("decks", []) as Array).size()
	data.published_solids = (published.get("solids", []) as Array).size()
	var framing := {"size": Vector2i(width, rows), "rect": Rect2(terrain_origin.x,
		terrain_origin.z, float(width) * tile, float(rows) * tile), "pixels_per_metre": 1.0 / tile}
	var polygon := TopDown.ownership_polygons_local(root)
	var owned: Image
	if not polygon.is_empty():
		owned = TopDown.ownership_mask(framing, polygon)
	else:
		owned = Image.create_empty(width, rows, false, Image.FORMAT_RGBA8)
		owned.fill(Color(1, 1, 1, 1))
	data.owned = owned
	data.owned_texture = ImageTexture.create_from_image(owned)
	data.texture = ImageTexture.create_from_image(Image.create_from_data(width, rows, false,
		Image.FORMAT_L8, data.classes))
	return data


## Whether the territory publishes its collision through the continent-v2
## exporter (_continent_v2/export_collision.py), whose trunk and enclosed rules
## (structure_raster.gd) and harvest-node rule (harvest_pass) LIVE then
## applies: its region authoring spec names a continent-v2 adapter. The spec
## is the catalog entry's authoringSpecPath, else
## the region-authoring-spec.json beside the open scene. Legacy territories
## publish through _continent/collision_export.py and keep its rules.
static func continent_v2(root: Node3D) -> bool:
	var region: Variant = root.get("region_id")
	var spec_path := String(TimeOfDay.catalog_entry(String(region) if region != null else "").get(
		"authoringSpecPath", ""))
	if spec_path.is_empty() and not root.scene_file_path.is_empty():
		spec_path = root.scene_file_path.get_base_dir().path_join("region-authoring-spec.json")
	if spec_path.is_empty() or not FileAccess.file_exists(spec_path):
		return false
	var spec: Variant = JSON.parse_string(FileAccess.get_file_as_string(spec_path))
	return spec is Dictionary and (spec as Dictionary).has("continentV2") and \
		String((spec as Dictionary).get("adapter", "")).begins_with("continent-v2")


## Solid records (structure_raster.gd gather's shape) for the published
## package's composer-only solids; they are already in the territory frame.
static func published_solids(published: Dictionary) -> Array:
	var result: Array = []
	var index := 0
	for solid: Dictionary in published.get("solids", []):
		var triangles: PackedVector3Array = solid.triangles
		if triangles.is_empty():
			continue
		var box := AABB(triangles[0], Vector3.ZERO)
		for point in triangles:
			box = box.expand(point)
		var key := "published:%s:%d" % [String(solid.name), index]
		result.append({"key": key, "name": "published %s" % String(solid.name),
			"parts": [{"faces": triangles, "transform": Transform3D.IDENTITY,
				"closed": Structures.closed_faces(triangles), "aabb": box}],
			"low": box.position, "high": box.end,
			"signature": "%s|%s" % [key, str(published.get("path", ""))]})
		index += 1
	return result


static func _grade_pass(data: Dictionary) -> void:
	var heights: PackedFloat32Array = data.heights
	var grid: Vector2i = data.grid
	var cell := float(data.cell)
	var tile := float(data.tile)
	var width := int(data.width)
	var classes: PackedByteArray = data.classes
	var limit := MAX_GRADE * MAX_GRADE
	if is_equal_approx(cell, tile * 2.0):
		# Fast path: each 2 m terrain cell covers 2 × 2 tiles. A tile takes the
		# worse of the triangles its half-metre cells fall in, like the served
		# grid's fold, so the north-west tile sees only the lower triangle, the
		# south-east only the upper, and the two diagonal tiles both.
		for iz in grid.y - 1:
			var row_a := iz * grid.x
			var row_b := row_a + grid.x
			for ix in grid.x - 1:
				var a := heights[row_a + ix]
				var b := heights[row_a + ix + 1]
				var c := heights[row_b + ix]
				var d := heights[row_b + ix + 1]
				var lower := ((b - a) * (b - a) + (c - a) * (c - a)) / (cell * cell) > limit
				var upper := ((d - c) * (d - c) + (d - b) * (d - b)) / (cell * cell) > limit
				if not lower and not upper:
					continue
				var t := (iz * 2) * width + ix * 2
				if lower:
					classes[t] = Tile.STEEP
				classes[t + 1] = Tile.STEEP
				classes[t + width] = Tile.STEEP
				if upper:
					classes[t + width + 1] = Tile.STEEP
		data.classes = classes
		return
	var rows := int(data.rows)
	for row in rows:
		for column in width:
			var x := (float(column) + 0.5) * tile / cell
			var z := (float(row) + 0.5) * tile / cell
			var ix := mini(floori(x), grid.x - 2)
			var iz := mini(floori(z), grid.y - 2)
			var u := x - float(ix)
			var v := z - float(iz)
			var a := heights[iz * grid.x + ix]
			var b := heights[iz * grid.x + ix + 1]
			var c := heights[(iz + 1) * grid.x + ix]
			var d := heights[(iz + 1) * grid.x + ix + 1]
			var dx := (b - a if u + v <= 1.0 else d - c) / cell
			var dz := (c - a if u + v <= 1.0 else d - b) / cell
			if dx * dx + dz * dz > limit:
				classes[row * width + column] = Tile.STEEP
	data.classes = classes


static func _ground(data: Dictionary, x: float, z: float) -> float:
	var heights: PackedFloat32Array = data.heights
	var grid: Vector2i = data.grid
	var cell := float(data.cell)
	var fx := clampf((x - float(data.terrain_x0)) / cell, 0.0, float(grid.x) - 1.0000001)
	var fz := clampf((z - float(data.terrain_z0)) / cell, 0.0, float(grid.y) - 1.0000001)
	var ix := mini(floori(fx), grid.x - 2)
	var iz := mini(floori(fz), grid.y - 2)
	var u := fx - float(ix)
	var v := fz - float(iz)
	var a := heights[iz * grid.x + ix]
	var b := heights[iz * grid.x + ix + 1]
	var c := heights[(iz + 1) * grid.x + ix]
	var d := heights[(iz + 1) * grid.x + ix + 1]
	if u + v <= 1.0:
		return a + (b - a) * u + (c - a) * v
	return d + (c - d) * (1.0 - u) + (b - d) * (1.0 - v)


## Column and row bounds (inclusive) of the tiles whose centres can lie in the
## XZ box; x > y means empty. Loops stay inline because GDScript lambdas capture
## packed arrays by value, so writes made inside a callback would be lost.
static func _tile_range(data: Dictionary, minimum: Vector2, maximum: Vector2) -> Vector4i:
	var tile := float(data.tile)
	return Vector4i(maxi(floori((minimum.x - float(data.x0)) / tile), 0),
		mini(floori((maximum.x - float(data.x0)) / tile), int(data.width) - 1),
		maxi(floori((minimum.y - float(data.z0)) / tile), 0),
		mini(floori((maximum.y - float(data.z0)) / tile), int(data.rows) - 1))


static func _tile_centre(data: Dictionary, column: int, row: int) -> Vector2:
	var tile := float(data.tile)
	return Vector2(float(data.x0) + (float(column) + 0.5) * tile,
		float(data.z0) + (float(row) + 0.5) * tile)


## Water, per half-metre cell as the bake samples it: a tile is under water
## when any of its half-cells stands (on the terrain, or on a deck that carries
## it) more than WADE below a water surface. The surfaces are the sea level,
## the scene's rivers (point heights along each segment, within its width)
## and water regions, and the continent plan's water the territory has not
## claimed. `plan` stands in for the plan file (tests).
static func _water_pass(root: Node3D, data: Dictionary, ground: Dictionary,
		plan: Dictionary = {}) -> void:
	var wet := PackedByteArray()
	wet.resize(int(data.width) * int(data.rows))
	var sea_level: Variant = manifest_sea_level(root)
	if sea_level != null:
		_sea_cells(data, ground, float(sea_level) - WADE, wet)
	for feature: Dictionary in water_features(root, plan):
		if String(feature.kind) == "segment":
			_segment_cells(data, ground, feature, wet)
		else:
			_ellipse_cells(data, ground, feature, wet)
	var classes: PackedByteArray = data.classes
	for index in wet.size():
		if wet[index] != 0:
			classes[index] = Tile.WATER


## The water surfaces LIVE tests against, in the territory frame:
## {"kind": "segment", "a", "b" (surface points), "half_a", "half_b"} and
## {"kind": "ellipse", "centre" (surface level in y), "radii"}.
static func water_features(root: Node3D, plan: Dictionary = {}) -> Array:
	var result: Array = []
	var inverse := root.global_transform.affine_inverse()
	var rivers := root.get_node_or_null("Rivers")
	if rivers != null:
		for path in rivers.get_children():
			if path.get_script() != PATH_SCRIPT or String(path.get("kind")) != "river":
				continue
			var to_root: Transform3D = inverse * (path as Node3D).global_transform
			var scale := Vector2(to_root.basis.x.x, to_root.basis.x.z).length()
			var points: Array = path.call("snapshot_points")
			for index in points.size() - 1:
				result.append({"kind": "segment", "a": to_root * _vec3(points[index].position),
					"b": to_root * _vec3(points[index + 1].position),
					"half_a": float(points[index].width) * scale * 0.5,
					"half_b": float(points[index + 1].width) * scale * 0.5})
	var lakes := root.get_node_or_null("WaterRegions")
	if lakes != null:
		for lake in lakes.get_children():
			if lake.get_script() == WATER_SCRIPT:
				result.append({"kind": "ellipse",
					"centre": inverse * (lake as Node3D).global_position, "radii": lake.get("radii")})
	var source := plan if not plan.is_empty() else PlanWater.load_plan()
	for feature: Dictionary in PlanWater.features(root, source):
		if bool(feature.claimed):
			continue
		if String(feature.kind) == "river":
			var points: PackedVector3Array = feature.points
			var halves: PackedFloat32Array = feature.halves
			for index in points.size() - 1:
				result.append({"kind": "segment", "a": points[index], "b": points[index + 1],
					"half_a": halves[index], "half_b": halves[index + 1]})
		else:
			result.append({"kind": "ellipse", "centre": feature.centre, "radii": feature.radii,
				"angle": float(feature.get("angle", 0.0))})
	return result


## Where the actor stands on a half-cell: the deck carrying it, else terrain.
static func _standing(ground: Dictionary, cell_index: int, x: float, z: float) -> float:
	var decks: Dictionary = ground.decks
	return float(decks[cell_index]) if decks.has(cell_index) else Structures.terrain_at(ground, x, z)


static func _tile_of(ground: Dictionary, data: Dictionary, cell_index: int) -> int:
	var columns := int(ground.columns)
	var sub := int(ground.sub)
	return (cell_index / columns / sub) * int(data.width) + (cell_index % columns) / sub


## The sea: half-cells standing below `limit` (sea level minus WADE). Terrain
## cells wholly above it are skipped; wholly below it, only a deck can keep a
## half-cell dry.
static func _sea_cells(data: Dictionary, ground: Dictionary, limit: float,
		wet: PackedByteArray) -> void:
	var heights: PackedFloat32Array = data.heights
	var grid: Vector2i = data.grid
	var cell := float(data.cell)
	var decks: Dictionary = ground.decks
	for iz in grid.y - 1:
		for ix in grid.x - 1:
			var a := heights[iz * grid.x + ix]
			var b := heights[iz * grid.x + ix + 1]
			var c := heights[(iz + 1) * grid.x + ix]
			var d := heights[(iz + 1) * grid.x + ix + 1]
			if minf(minf(a, b), minf(c, d)) >= limit:
				continue
			var whole := maxf(maxf(a, b), maxf(c, d)) < limit
			var span := _cell_range(ground, Vector2(float(data.terrain_x0) + float(ix) * cell,
				float(data.terrain_z0) + float(iz) * cell), Vector2.ONE * cell)
			for row in range(span.z, span.w):
				var z := float(ground.z0) + (float(row) + 0.5) * Structures.CELL
				for column in range(span.x, span.y):
					var cell_index := row * int(ground.columns) + column
					var standing: float
					if whole and not decks.has(cell_index):
						standing = -INF
					else:
						standing = _standing(ground, cell_index,
							float(ground.x0) + (float(column) + 0.5) * Structures.CELL, z)
					if standing < limit:
						wet[_tile_of(ground, data, cell_index)] = 1


static func _segment_cells(data: Dictionary, ground: Dictionary, feature: Dictionary,
		wet: PackedByteArray) -> void:
	var first: Vector3 = feature.a
	var second: Vector3 = feature.b
	var first_half := float(feature.half_a)
	var second_half := float(feature.half_b)
	var reach := maxf(first_half, second_half)
	var a := Vector2(first.x, first.z)
	var ab := Vector2(second.x, second.z) - a
	var length_squared := maxf(ab.length_squared(), 0.000001)
	var low := Vector2(minf(first.x, second.x), minf(first.z, second.z)) - Vector2.ONE * reach
	var span := _cell_range(ground, low, Vector2(absf(ab.x), absf(ab.y)) + Vector2.ONE * reach * 2.0)
	for row in range(span.z, span.w):
		var z := float(ground.z0) + (float(row) + 0.5) * Structures.CELL
		for column in range(span.x, span.y):
			var x := float(ground.x0) + (float(column) + 0.5) * Structures.CELL
			var centre := Vector2(x, z)
			var t := clampf((centre - a).dot(ab) / length_squared, 0.0, 1.0)
			if centre.distance_to(a + ab * t) > lerpf(first_half, second_half, t):
				continue
			var cell_index := row * int(ground.columns) + column
			if lerpf(first.y, second.y, t) - _standing(ground, cell_index, x, z) > WADE:
				wet[_tile_of(ground, data, cell_index)] = 1


static func _ellipse_cells(data: Dictionary, ground: Dictionary, feature: Dictionary,
		wet: PackedByteArray) -> void:
	var centre: Vector3 = feature.centre
	var radii: Vector2 = feature.radii
	if radii.x <= 0.0 or radii.y <= 0.0:
		return
	var middle := Vector2(centre.x, centre.z)
	# The plan's lake angle turns x toward z (landscape._ellipse_distance).
	var turn := float(feature.get("angle", 0.0))
	var reach := Vector2.ONE * maxf(radii.x, radii.y)
	var span := _cell_range(ground, middle - reach, reach * 2.0)
	for row in range(span.z, span.w):
		var z := float(ground.z0) + (float(row) + 0.5) * Structures.CELL
		for column in range(span.x, span.y):
			var x := float(ground.x0) + (float(column) + 0.5) * Structures.CELL
			var offset := Vector2(x, z) - middle
			var u := offset.x * cos(turn) + offset.y * sin(turn)
			var v := -offset.x * sin(turn) + offset.y * cos(turn)
			if (u / radii.x) * (u / radii.x) + (v / radii.y) * (v / radii.y) > 1.0:
				continue
			var cell_index := row * int(ground.columns) + column
			if centre.y - _standing(ground, cell_index, x, z) > WADE:
				wet[_tile_of(ground, data, cell_index)] = 1


## Half-cell bounds [x, x_end) x [z, z_end) whose centres fall in the box at
## `position` of `size`, clipped to the grid.
static func _cell_range(ground: Dictionary, position: Vector2, size: Vector2) -> Vector4i:
	var x0 := float(ground.x0)
	var z0 := float(ground.z0)
	var xa := maxi(0, ceili((position.x - x0) / Structures.CELL - 0.5))
	var xb := mini(int(ground.columns), ceili((position.x + size.x - x0) / Structures.CELL - 0.5))
	var za := maxi(0, ceili((position.y - z0) / Structures.CELL - 0.5))
	var zb := mini(int(ground.rows), ceili((position.y + size.y - z0) / Structures.CELL - 0.5))
	return Vector4i(xa, maxi(xa, xb), za, maxi(za, zb))


## A continent-v2 harvest node closes its served tile (export_collision.py
## harvest_mask): the node is a body, harvested from the ring round it. The
## tile is the marker's, as the bake derives it (region_snapshot _server_tile:
## half-cells 2tx..2tx+1 by 2ty..2ty+1 of the served frame).
static func harvest_pass(root: Node3D, data: Dictionary, ground: Dictionary) -> void:
	var gameplay := root.get_node_or_null("Gameplay")
	if gameplay == null:
		return
	var origin: Vector2i = root.get("server_origin") if root.get("server_origin") is Vector2i \
		else Vector2i.ZERO
	var inverse := root.global_transform.affine_inverse()
	var classes: PackedByteArray = data.classes
	var blockers: Dictionary = data.blockers
	var width := int(data.width)
	var sub := int(ground.sub)
	var columns := int(ground.columns)
	var rows := int(ground.rows)
	for marker in gameplay.find_children("*", "Node3D", true, false):
		if marker.get_script() != MARKER_SCRIPT or String(marker.call("output_section")) != "harvestables":
			continue
		var followed: Node3D = marker.call("followed_asset")
		var world: Vector3 = (marker as Node3D).global_position if followed == null else \
			followed.global_transform * Vector3(marker.get("follow_asset_offset"))
		var local: Vector3 = inverse * world
		var tx := floori(local.x + float(origin.x))
		var ty := floori(float(origin.y) - local.z)
		for oz in 2:
			for ox in 2:
				var x := float(tx - origin.x) + 0.25 + 0.5 * float(ox)
				var z := float(origin.y - ty) - 0.25 - 0.5 * float(oz)
				var column := floori((x - float(ground.x0)) / Structures.CELL)
				var row := floori((z - float(ground.z0)) / Structures.CELL)
				if column < 0 or row < 0 or column >= columns or row >= rows:
					continue
				var tile_index := (row / sub) * width + column / sub
				classes[tile_index] = Tile.BLOCKED
				blockers[tile_index] = "harvest node %s" % String(marker.get("record_id"))
	data.classes = classes


## Solid assets as the bake tests them (structure_raster.gd), folded from
## half-cells to tiles. Blocking is final: no deck or water class overrides it.
static func _structure_pass(data: Dictionary, ground: Dictionary, solids: Array,
		cache: Dictionary, defer: bool) -> void:
	var pending: Array = []
	var classes: PackedByteArray = data.classes
	var blockers: Dictionary = data.blockers
	var width := int(data.width)
	var sub := int(ground.sub)
	var columns := int(ground.columns)
	for solid: Dictionary in solids:
		var signature := Structures.solid_signature(solid, ground)
		var cached: Variant = cache.get(solid.key)
		var tiles := PackedInt32Array()
		if cached is Dictionary and String(cached.signature) == signature:
			for cell_index: int in cached.cells:
				tiles.append((cell_index / columns / sub) * width + (cell_index % columns) / sub)
		elif defer:
			pending.append({"key": solid.key, "signature": signature, "parts": solid.parts,
				"enclose": bool(solid.get("enclose", false)),
				"deck": solid.get("deck", PackedVector3Array())})
			tiles = _box_estimate(data, solid)
		else:
			var cells := Structures.blocked_cells(solid.parts, ground,
				bool(solid.get("enclose", false)), solid.get("deck", PackedVector3Array()))
			cache[solid.key] = {"signature": signature, "cells": cells}
			for cell_index in cells:
				tiles.append((cell_index / columns / sub) * width + (cell_index % columns) / sub)
		for tile_index in tiles:
			classes[tile_index] = Tile.BLOCKED
			blockers[tile_index] = String(solid.name)
	data.classes = classes
	data.pending = pending
	data.solids = solids.size()


## The tiles a solid's mesh boxes cover in the actor's body height: the quick
## stand-in shown while its exact check runs.
static func _box_estimate(data: Dictionary, solid: Dictionary) -> PackedInt32Array:
	var tiles := PackedInt32Array()
	var width := int(data.width)
	for part: Dictionary in solid.parts:
		var box := _footprint(part.transform, part.aabb)
		var corners: Array[Vector2] = box.corners
		var span := _tile_range(data, box.minimum, box.maximum)
		for row in range(span.z, span.w + 1):
			for column in range(span.x, span.y + 1):
				var centre := _tile_centre(data, column, row)
				if not _inside_quad(corners, centre):
					continue
				var ground := _ground(data, centre.x, centre.y)
				if float(box.bottom) < ground + ACTOR_HEIGHT and \
						float(box.top) > ground + ACTOR_FLOOR_CLEARANCE:
					tiles.append(row * width + column)
	return tiles


## Walk_ decks (structure_raster.gd) and editor bridges, on half-cells. A tile
## becomes a deck when each of its half-cells is carried by one or stands on
## gentle ground. Water is decided afterwards against where the actor stands.
static func _deck_pass(root: Node3D, data: Dictionary, ground: Dictionary, decks: Array) -> void:
	var sources: Array = decks.duplicate()
	var inverse := root.global_transform.affine_inverse()
	var bridges := root.get_node_or_null("Bridges")
	if bridges != null:
		for bridge in bridges.get_children():
			var start := bridge.get_node_or_null("Start") as Node3D
			var finish := bridge.get_node_or_null("End") as Node3D
			if start == null or finish == null or bridge.get("width") == null:
				continue
			var a: Vector3 = inverse * start.global_position
			var b: Vector3 = inverse * finish.global_position
			var along := Vector2(b.x - a.x, b.z - a.z)
			if along.length_squared() < 0.0001:
				continue
			var flat := Vector2(-along.y, along.x).normalized() * float(bridge.get("width")) * 0.5
			var side := Vector3(flat.x, 0.0, flat.y)
			sources.append({"name": String(bridge.name), "either_side": true,
				"triangles": PackedVector3Array([a + side, b + side, b - side,
					a + side, b - side, a - side])})
	var raster := Structures.deck_cells(ground, sources)
	ground.decks = raster.cells
	var cells: Dictionary = raster.cells
	var names: Dictionary = raster.sources
	var classes: PackedByteArray = data.classes
	var deck_sources: Dictionary = data.decks
	var width := int(data.width)
	var sub := int(ground.sub)
	var columns := int(ground.columns)
	var tiles := {}
	for cell_index: int in cells:
		tiles[(cell_index / columns / sub) * width + (cell_index % columns) / sub] = cell_index
	for tile_index: int in tiles:
		var column := tile_index % width
		var row := tile_index / width
		var spared := true
		for oz in sub:
			for ox in sub:
				var cell_index := (row * sub + oz) * columns + column * sub + ox
				if cells.has(cell_index):
					continue
				var x := float(ground.x0) + (float(column * sub + ox) + 0.5) * Structures.CELL
				var z := float(ground.z0) + (float(row * sub + oz) + 0.5) * Structures.CELL
				if _grade(data, x, z) > MAX_GRADE:
					spared = false
		if classes[tile_index] == Tile.STEEP and not spared:
			continue
		classes[tile_index] = Tile.DECK
		deck_sources[tile_index] = String(names[tiles[tile_index]])
	data.classes = classes


## An oriented box's XZ footprint (as a quad) and its vertical extent.
static func _footprint(transform: Transform3D, box: AABB) -> Dictionary:
	var low := box.position
	var high := box.end
	var quad: Array[Vector2] = []
	for corner in [Vector3(low.x, low.y, low.z), Vector3(high.x, low.y, low.z),
			Vector3(high.x, low.y, high.z), Vector3(low.x, low.y, high.z)]:
		var point: Vector3 = transform * corner
		quad.append(Vector2(point.x, point.z))
	var bottom := INF
	var top := -INF
	for x in [low.x, high.x]:
		for y in [low.y, high.y]:
			for z in [low.z, high.z]:
				var point: Vector3 = transform * Vector3(x, y, z)
				bottom = minf(bottom, point.y)
				top = maxf(top, point.y)
	var minimum := Vector2(INF, INF)
	var maximum := Vector2(-INF, -INF)
	for point in quad:
		minimum = minimum.min(point)
		maximum = maximum.max(point)
	return {"corners": quad, "bottom": bottom, "top": top, "minimum": minimum, "maximum": maximum}


static func _inside_quad(quad: Array[Vector2], point: Vector2) -> bool:
	var sign := 0.0
	for index in 4:
		var a := quad[index]
		var b := quad[(index + 1) % 4]
		var cross := (b - a).cross(point - a)
		if absf(cross) < 0.000001:
			continue
		if sign == 0.0:
			sign = signf(cross)
		elif signf(cross) != sign:
			return false
	return true


static func _vec3(value: Variant) -> Vector3:
	var values: Array = value
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _live_index(local: Vector3) -> int:
	if _live.is_empty():
		return -1
	var column := floori((local.x - float(_live.x0)) / float(_live.tile))
	var row := floori((local.z - float(_live.z0)) / float(_live.tile))
	if column < 0 or row < 0 or column >= int(_live.width) or row >= int(_live.rows):
		return -1
	return row * int(_live.width) + column


func _apply() -> bool:
	if _root == null or not is_instance_valid(_root):
		return false
	if _node == null or not is_instance_valid(_node):
		_node = MeshInstance3D.new()
		_node.name = NODE_NAME
		_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_node.top_level = true
		var shader := Shader.new()
		shader.code = SHADER_CODE
		_material = ShaderMaterial.new()
		_material.shader = shader
		_material.render_priority = 3
		_node.material_override = _material
		_root.add_child(_node, false, Node.INTERNAL_MODE_BACK)
	_sync_mesh()
	_material.set_shader_parameter("mode", int(mode))
	_material.set_shader_parameter("region_inverse",
		Projection(_root.global_transform.affine_inverse()))
	var has_published := not _published.is_empty() and not _published.has("error")
	_material.set_shader_parameter("has_published", has_published)
	if has_published:
		_material.set_shader_parameter("published", _published.texture)
		_material.set_shader_parameter("published_rect", Vector4(float(_published.x0),
			float(_published.z1), float(_published.width) * float(_published.cell),
			float(_published.rows) * float(_published.cell)))
	if not _live.is_empty():
		_material.set_shader_parameter("live_classes", _live.texture)
		_material.set_shader_parameter("owned_mask", _live.owned_texture)
		_material.set_shader_parameter("live_rect", Vector4(float(_live.x0), float(_live.z0),
			float(_live.width) * float(_live.tile), float(_live.rows) * float(_live.tile)))
	_node.visible = true
	if mode == Mode.PUBLISHED and has_published:
		last_message = "Published grid: %s (%d × %d half-metre cells, %.1f%% walkable)." % [
			String(_published.path).get_file(), int(_published.width), int(_published.rows),
			float(_published.walkable_fraction) * 100.0]
	elif mode == Mode.CHANGES and not has_published:
		last_message = "No published grid to compare with; showing nothing."
	return true


func _sync_mesh() -> void:
	if _node == null or not is_instance_valid(_node) or _root == null:
		return
	var terrain := Probe.region_terrain(_root)
	var preview := terrain.get_node_or_null("__TerrainPreview") as MeshInstance3D \
		if terrain != null else null
	if preview == null:
		_node.visible = false
		return
	if _node.mesh != preview.mesh:
		_node.mesh = preview.mesh
	_node.global_transform = preview.global_transform

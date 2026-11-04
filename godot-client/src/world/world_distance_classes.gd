extends RefCounted
## World distance size classes (wave 2 WD-C2; the world-distance plan, section 3.1).
##
## An instance's size class follows from its radius r: the half-diagonal of its
## mesh's AABB scaled by the placement's basis scale (the plan's "prototype mesh
## AABB x instance basis scale"; a turned copy keeps its class). The class sets
## the edge of the static batch cell an instance is drawn from on the
## continent and in gauntlets (`WorldLoader._batch_static_instances`): a
## 180 m cell drew a whole grove whenever one tree in it was in view, so small
## props now share 32 m cells and only the largest pieces 96 m ones. The
## runtime distance pass (WD-C3, `world_distance.gd`) reads the same classes
## for its reach, shadow and LOD rules, and the shared prototype pool (WD-C5,
## `external_mesh_pool.gd`) its rule for which prototypes get generated LODs,
## so every number the owner tunes is in this table.
##
## Membership does not move: which instances batch at all is still decided by
## the loader's legacy grouping (at least `WorldLoader.BATCH_MINIMUM_INSTANCES`
## of one mesh in one `WorldLoader.BATCH_CELL_METRES` cell). A batch is only
## split into its class cells; a member is never turned back into a loose
## node and a loose node never joins a batch. The look passes, paving cache,
## gauntlet contrast and seasons treat batched and loose nodes differently, so
## keeping membership is what keeps the picture the same.
##
## The constants are literals with string keys on purpose:
## `tools/world_draw_budget.py` reads CLASS_RADIUS_LIMITS, CELL_METRES,
## REACH_METRES and TIER_REACH_SCALE from this file.
##
## Pure static helpers: safe on the worker threads that build detached chunks.

## The classes from the smallest up.
const CLASSES: Array[String] = ["S", "M", "L", "XL"]
## The exclusive upper radius (metres) of S, M and L; anything larger is XL.
const CLASS_RADIUS_LIMITS: Array[float] = [1.5, 4.0, 10.0]
## The static batch cell edge per class (metres).
const CELL_METRES := {"S": 32.0, "M": 48.0, "L": 64.0, "XL": 96.0}
## Stamped on every class-split batch (a String, one of CLASSES); a batch
## without it was built by the legacy rule (identity frame, legacy cell).
const CLASS_META := &"rl_distance_class"

# --- Runtime distance pass (WD-C3, world_distance.gd) -----------------------

## How far from the camera's focus a class is always drawn at HIGH (metres);
## 0 = never culled by distance (the far plane only). A node is culled only
## beyond `camera bucket + reach x tier scale + its own extent + margin`
## (WorldDistance.range_end), so nothing within the reach of the focus is
## culled at any zoom.
const REACH_METRES := {"S": 30.0, "M": 70.0, "L": 160.0, "XL": 0.0}
## The reach per graphics quality (LookProfile.Quality names, upper case).
const TIER_REACH_SCALE := {"HIGH": 1.0, "MEDIUM": 0.8, "LOW": 0.6}
## Mesh LOD bias per graphics quality on every classed node. Meshes without
## LODs ignore it, so it changes nothing until generated prototype LODs
## (WD-C5) exist.
const LOD_BIAS := {"HIGH": 1.0, "MEDIUM": 0.4, "LOW": 0.15}
## Whether a class casts the sun's shadow. A flat piece never does.
const CASTS_SHADOW := {"S": false, "M": true, "L": true, "XL": true}
## Flat: a piece lower than this (metres), or lower than FLAT_HEIGHT_RATIO of
## the narrower width of its footprint (`is_flat`).
const FLAT_HEIGHT_METRES := 0.35
const FLAT_HEIGHT_RATIO := 0.15
## Bridge and pier structure (by node name, case-insensitive words, or name
## prefixes): never ranged, because the walk decks it holds up are ground and
## always drawn; a ranged support would leave a floating deck at distance.
const STRUCTURE_PREFIXES: Array[String] = ["AuthoredBridge", "Deck_"]
const STRUCTURE_WORDS: Array[String] = ["bridge", "causeway", "trestle"]
## An object the exporter split by material (its meshes share one parent and
## one placement) is classed, ranged and shadowed as one, by its parts' union
## box, so it never loses a part at distance. Such meshes whose union box is
## wider than this many times the largest part's are not one object, and are
## classed one by one.
const ASSEMBLY_SPREAD := 2.0
## The camera's orbit distance is rounded up to this step (metres), so a zoom
## re-applies the ranges once per step, not every frame.
const CAMERA_BUCKET_METRES := 8.0
## Hysteresis on every range end (metres; VISIBILITY_RANGE_FADE_DISABLED).
## Godot hides a drawn node beyond end + margin and shows a hidden one inside
## end - margin, so the margin is added to the end: the hysteresis band lies
## wholly beyond the reach.
const RANGE_MARGIN_METRES := 4.0
## A node's own extent (its drawn box's half-diagonal: a batch's members
## spread over its cell) is rounded up to this step (metres); nodes of one
## class and step share one SceneTree group and so one range end.
const EXTENT_STEP_METRES := 4.0
## Extents beyond this many steps are not ranged (none is expected: a class
## cell's own diagonal is under 75 m).
const EXTENT_STEPS := 32

# --- Generated prototype LODs (WD-C5, external_mesh_pool.gd) ----------------

## A shared prototype (ExternalMeshPool) gets meshoptimizer LODs
## (ImporterMesh.generate_lods) when the mesh it publishes has at least
## LOD_MIN_TRIANGLES triangles and its mesh box's half-diagonal is at least
## LOD_MIN_RADIUS metres, the S limit: small props stay whole and are culled
## by their reach instead. The generated levels leave the vertices and the
## full index list as they were; LOD_BIAS above decides how early a level is
## drawn (at bias 1.0 only where Godot's 1 px screen-error threshold allows).
## Baked like CELL_METRES: the geometry cook saves the levels with each
## prototype, so changing these needs a MapGeometryPolicy.VERSION bump and a
## re-cook of the prepared world.
const LOD_MIN_TRIANGLES := 600
const LOD_MIN_RADIUS := 1.5
## ImporterMesh.generate_lods' normal_merge_angle and normal_split_angle
## (degrees), the plan's pair: a 25 degree merge keeps the hard edges of cut
## stone and crystal shards apart. The editor's import default merges at 60;
## 13 of the 273 shipped prototypes that qualify come out differently. Godot
## 4.7 no longer reads normal_split_angle (kept for the API: the tree, wall,
## rock and undergrowth give identical levels at 0, 60 and 179).
const LOD_NORMAL_MERGE_ANGLE := 25.0
const LOD_NORMAL_SPLIT_ANGLE := 60.0

## Ground and water by node name, as the continent exporter names them
## (LookGround.kind_of reads the same prefixes): never ranged.
enum Ground { NONE, WATER, TERRAIN, BASE, PATCH, DECK }

## The ground kind `node_name` names. A base is `AuthoredGround_<region>Base`
## (WorldLoader._is_authored_base_terrain); any other authored ground is a
## patch; `Walk_` meshes are walk decks (bridge and pier decks, kit paving).
static func ground_kind(node_name: String) -> Ground:
	if node_name.begins_with("Water_") or node_name.begins_with("Scenery_Water"):
		return Ground.WATER
	if node_name.begins_with("Terrain_") or node_name.begins_with("Walk_Terrain"):
		return Ground.TERRAIN
	if node_name.begins_with("AuthoredGround_"):
		return Ground.BASE if _is_base_name(node_name) else Ground.PATCH
	if node_name.begins_with("Walk_"):
		return Ground.DECK
	return Ground.NONE

## `AuthoredGround_<region>Base` or `AuthoredGround_<region>Base_<...>`, where
## the region part holds no `-` (patch names such as `castle-town-lawn` do).
static func _is_base_name(node_name: String) -> bool:
	var rest := node_name.trim_prefix("AuthoredGround_")
	var at := rest.find("Base")
	if at <= 0 or rest.left(at).contains("-"):
		return false
	var after := rest.substr(at + 4)
	return after.is_empty() or after.begins_with("_")

## Whether a piece `height` metres tall (its placed box's vertical extent)
## whose footprint is `footprint` metres across at its narrowest
## (`footprint_width`) is flat: a slab, a deck, a pad. Measured on the
## footprint's narrower width, a turned copy is exactly as flat as the
## original, and a long low wall or fence (thin across) is not flat.
static func is_flat(height: float, footprint: float) -> bool:
	var tall := absf(height)
	return tall < FLAT_HEIGHT_METRES or tall < FLAT_HEIGHT_RATIO * absf(footprint)

## The narrowest width (metres) of a box of `mesh_size` placed by `basis`, seen
## from above: its outline on the ground plane is the sum of its three placed
## edges, and the narrowest width of that outline lies across one of them.
static func footprint_width(mesh_size: Vector3, basis: Basis) -> float:
	var a := Vector2(basis.x.x, basis.x.z) * mesh_size.x
	var b := Vector2(basis.y.x, basis.y.z) * mesh_size.y
	var c := Vector2(basis.z.x, basis.z.z) * mesh_size.z
	var narrowest := minf(_width_across(a, a, b, c), minf(_width_across(b, a, b, c), _width_across(c, a, b, c)))
	return narrowest if narrowest < INF else 0.0

## The outline's width across `edge` (one of its edges `a`, `b`, `c`); INF for
## an edge seen end-on.
static func _width_across(edge: Vector2, a: Vector2, b: Vector2, c: Vector2) -> float:
	if edge.length_squared() <= 1e-12:
		return INF
	var across := Vector2(-edge.y, edge.x).normalized()
	return absf(a.dot(across)) + absf(b.dot(across)) + absf(c.dot(across))

## Whether `node_name` names bridge or pier structure (STRUCTURE_PREFIXES,
## STRUCTURE_WORDS).
static func is_structure(node_name: String) -> bool:
	for prefix: String in STRUCTURE_PREFIXES:
		if node_name.begins_with(prefix):
			return true
	for word: String in STRUCTURE_WORDS:
		if node_name.containsn(word):
			return true
	return false

## The reach of `distance_class` at `quality_name` (metres from the focus);
## 0 when the class is not ranged.
static func reach_metres(distance_class: String, quality_name: String) -> float:
	var reach := float(REACH_METRES.get(distance_class, 0.0))
	return reach * float(TIER_REACH_SCALE.get(quality_name.to_upper(), 1.0)) if reach > 0.0 else 0.0

## The mesh LOD bias at `quality_name`.
static func lod_bias(quality_name: String) -> float:
	return float(LOD_BIAS.get(quality_name.to_upper(), 1.0))

## Whether a prototype mesh of `triangles` triangles whose mesh box has
## half-diagonal `radius` (metres, its own space) gets generated LODs.
static func generates_lods(triangles: int, radius: float) -> bool:
	return triangles >= LOD_MIN_TRIANGLES and radius >= LOD_MIN_RADIUS

## The camera's orbit distance rounded up to CAMERA_BUCKET_METRES (at least
## one step).
static func camera_bucket(distance: float) -> float:
	var step := CAMERA_BUCKET_METRES
	return maxf(step, ceilf(maxf(distance, 0.0) / step) * step)

## The extent step of a node whose drawn box has half-diagonal `extent`, or -1
## when it is too large to range.
static func extent_step(extent: float) -> int:
	var step := ceili(maxf(extent, 0.0) / EXTENT_STEP_METRES)
	return step if step <= EXTENT_STEPS else -1

## The visibility_range_end of a node of `distance_class` and extent step
## `step` at camera bucket `bucket` and `quality_name`; 0 (not culled) when
## the class has no reach.
static func range_end(distance_class: String, step: int, bucket: float, quality_name: String) -> float:
	var reach := reach_metres(distance_class, quality_name)
	if reach <= 0.0 or step < 0:
		return 0.0
	return bucket + reach + float(step) * EXTENT_STEP_METRES + RANGE_MARGIN_METRES

## The class of an instance of radius `radius` (metres; `placement_radius`).
static func size_class(radius: float) -> String:
	for index: int in CLASS_RADIUS_LIMITS.size():
		if radius < CLASS_RADIUS_LIMITS[index]:
			return CLASSES[index]
	return CLASSES[CLASSES.size() - 1]

## The batch cell edge for `distance_class`, never larger than `cap` when
## `cap` is positive (a manifest's `rendering.batchCellMetres`, or the
## loader's legacy cell). An unknown class takes the cap.
static func cell_metres(distance_class: String, cap := 0.0) -> float:
	if not CELL_METRES.has(distance_class):
		return cap if cap > 0.0 else float(CELL_METRES[CLASSES[CLASSES.size() - 1]])
	var cell := float(CELL_METRES[distance_class])
	return minf(cell, cap) if cap > 0.0 else cell

## The half-diagonal of a box.
static func radius_of(box: AABB) -> float:
	return box.size.length() * 0.5

## An instance's radius: its mesh's box (`mesh_box`, in the mesh's own space)
## scaled by the placement's basis scale. Turning an instance does not change
## its class, so the copies of a prototype placed at different headings share
## their cells.
static func placement_radius(mesh_box: AABB, basis: Basis) -> float:
	return (mesh_box.size * basis.get_scale().abs()).length() * 0.5

## Whether a manifest's batches are split into class cells: continent
## territories and chunks (`continentGeography`) and gauntlets (`gauntlet`),
## the maps the runtime distance pass ranges. Interiors and the older whole
## maps keep the legacy batches exactly: their camera stays within 6-26 m, so
## smaller cells would only add draw calls there (owner question 3 of the plan
## decides whether they join later; this is the one place to change).
static func applies_to(manifest_data: Dictionary) -> bool:
	return manifest_data.get("continentGeography") is Dictionary \
		or manifest_data.get("gauntlet") is Dictionary

## Splits one batch's members into class cells.
##
## `origins` are the members' placements (the cell is taken from the origin,
## as the legacy rule does) and `radii` their `placement_radius`.
## Returns one Dictionary per cell, in the order each cell is first met:
## {"class": String, "members": PackedInt32Array of indices into `origins`}.
## Every index appears exactly once, in its original order within its cell.
static func partition(origins: PackedVector3Array, radii: PackedFloat32Array,
		cap := 0.0) -> Array[Dictionary]:
	var parts: Array[Dictionary] = []
	var slots: Dictionary = {}
	for index: int in origins.size():
		var distance_class := size_class(radii[index] if index < radii.size() else 0.0)
		var cell := cell_metres(distance_class, cap)
		var origin: Vector3 = origins[index]
		var key := "%s|%d|%d|%d" % [distance_class, floori(origin.x / cell),
			floori(origin.y / cell), floori(origin.z / cell)]
		if not slots.has(key):
			slots[key] = parts.size()
			parts.append({"class": distance_class, "members": PackedInt32Array()})
		var part: Dictionary = parts[int(slots[key])]
		var members: PackedInt32Array = part["members"]
		members.append(index)
		part["members"] = members
	return parts

## Where a class-split batch stands: the centre of its members' world boxes,
## so the node's origin and its drawn AABB's centre agree (Godot measures a
## visibility range to the AABB centre). Empty boxes fall back to `origins`.
static func frame_origin(boxes: Array[AABB], origins: PackedVector3Array) -> Vector3:
	var merged := AABB()
	var any := false
	for box: AABB in boxes:
		if not box.size.is_finite() or not box.position.is_finite():
			continue
		merged = box if not any else merged.merge(box)
		any = true
	if any:
		return merged.get_center()
	var sum := Vector3.ZERO
	for origin: Vector3 in origins:
		sum += origin
	return sum / float(origins.size()) if not origins.is_empty() else Vector3.ZERO

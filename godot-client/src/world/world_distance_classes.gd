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
## for its reach, shadow and LOD rules, so every number the owner tunes is in
## this table.
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
## `tools/world_draw_budget.py` reads CLASS_RADIUS_LIMITS and CELL_METRES
## from this file.
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

extends Node
## World distance management: the runtime pass (wave 2 WD-C3; the
## world-distance plan, sections 3.1, 3.2 and 3.4).
##
## Every loaded continent territory, chunk and gauntlet (the maps
## `WorldDistanceClasses.applies_to`) is classed once, as it loads
## (`apply_loaded`, called by WorldLoader after its cache snapshot and before
## the look pass, on whatever thread builds the tree):
## - each drawn prop - a class-split static batch, a pooled prototype
##   placement, a package's own mesh - takes its size class (S/M/L/XL, the
##   batch's `rl_distance_class` or its radius), joins the SceneTree group of
##   its class and extent step and gets a visibility range. An object the
##   exporter split by material (its meshes under one parent, at one
##   placement) is one prop:
##   its parts share the class, range and shadow rule of their union box;
## - small (S) and flat pieces (a slab or deck: low against the narrower
##   width of its footprint and under 1 m, so never a long low wall or an
##   enclosure's ring of walls) stop casting the sun's
##   shadow, and so do ground patches, flat walk decks, and a chunk's
##   `Terrain_` wherever an opaque, shadow-casting
##   `AuthoredGround_<region>Base` in the same root already casts the ground's
##   shadow. A batch's hidden members take the batch's setting, so a member
##   OccluderFade lifts out of its batch casts as the batch did;
## - every classed prop takes the quality's mesh LOD bias.
## Ground (terrain, bases, patches, walk decks) and water are never ranged, nor
## is what must stand with it at any distance: bridge and pier structure
## under the walk decks, and the lamp models whose halos NightLamps draws.
## Nothing else changes: membership, names, materials and transforms are the
## loader's, and the loader's cache snapshot is taken before this pass, so
## cached entries stay tier-neutral (WorldLoader restores what this pass
## changed for the length of a pack).
##
## Culling is relative to the camera's focus (plan 3.2): Godot measures a
## range from the camera to the node's box centre, and this camera orbits
## 1.5-90 m from the player, so a range end is `camera bucket + reach x tier
## scale + the node's own extent + margin` (WorldDistanceClasses.range_end).
## Anything with a point within the reach of the focus is drawn at every zoom,
## a whole batch included.
##
## One `WorldDistance` node (Main creates it under WorldRoot) follows the
## camera: `update` once a frame with the rig's orbit distance and the graphics
## quality. When the bucket, the quality or the camera's detachment (a film)
## changes, it re-applies every range with one `SceneTree.set_group` per group
## (about 0.4-1 ms per 2,400 ranged nodes headless). A tree built while the
## state was different - a chunk prepared on a worker during a zoom, a parked
## world re-adopted - is stamped with the state it was built under (a
## non-persistent root group), so it is caught as it enters the tree and the
## ranges are applied once more; a chunk that arrives under the current state
## costs nothing.
##
## `ELORIA_WORLD_DISTANCE=off` (HardwareTier.world_distance_enabled) turns the
## whole pass off: loads are left exactly as WD-C2 builds them.

const Classes := preload("res://src/world/world_distance_classes.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

## The rig's default orbit distance, used until Main publishes one.
const DEFAULT_CAMERA_DISTANCE := 26.0
## WorldLoader.BATCH_META / BATCH_PATH_META, spelled here so this file never
## preloads the loader (the loader preloads this file).
const BATCH_META := "static_batch"
const BATCH_PATH_META := "static_batch_path"
const BATCH_PREFIX := "StaticBatch_"
## WorldLoader.GROUP_NAME_PREFIX: the loader's grouping of wide sibling lists.
const WORLD_GROUP_PREFIX := "WorldGroup_"
## The ranged classes. XL has no reach; it and the legacy (unclassed) batches
## join LOD_GROUP for the LOD bias alone.
const RANGED_CLASSES: Array[String] = ["S", "M", "L"]
const GROUP_PREFIX := "rl_wd_"
const LOD_GROUP := &"rl_wd_lod"
## A classed root's group: the state its ranges were last applied under.
const STAMP_PREFIX := "rl_wd_at_"
## Properties the pass may write, restored for a cache pack (WorldLoader).
const PROPERTIES: Array[StringName] = [&"cast_shadow", &"visibility_range_end",
	&"visibility_range_end_margin", &"visibility_range_fade_mode", &"lod_bias"]

static var _mutex := Mutex.new()
## The state loads read (`current_state`), published by the node on Main.
static var _state: Dictionary = {}
## Every stamp a root has been given: state key -> group.
static var _stamps: Dictionary = {}
static var _stamp_revision := 0
## class -> group by extent step.
static var _groups: Dictionary = _build_groups()

## False with ELORIA_WORLD_DISTANCE=off: `update` does nothing.
var enabled := true
var camera_distance := DEFAULT_CAMERA_DISTANCE
var quality := -1
var camera_detached := false
## Range re-applies, and how many of them a stale tree entering asked for.
var applies := 0
var refreshes := 0
var last_apply_usec := 0
var max_apply_usec := 0
var _now: Dictionary = {}
var _stamp_keys: Dictionary = {}
var _seen_revision := -1
## Streams `watch` connected (ContinentChunkStream; untyped so this file does
## not depend on the stream, which depends on the loader).
var _streams: Array[Node] = []

func _init() -> void:
	name = "WorldDistance"
	enabled = enabled_by_environment()

## Whether the pass runs (ELORIA_WORLD_DISTANCE is not off).
static func enabled_by_environment() -> bool:
	return HardwareTier.world_distance_enabled()

# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

## The state for an orbit `distance`, a LookProfile.Quality and whether the
## camera is detached from the play rig (a film: nothing is culled).
static func state_for(distance: float, level: int, detached := false) -> Dictionary:
	var bounded := clampi(level, 0, LookProfile.QUALITY_NAMES.size() - 1)
	var bucket := Classes.camera_bucket(distance)
	return {"bucket": bucket, "quality": bounded,
		"quality_name": LookProfile.QUALITY_NAMES[bounded].to_upper(), "detached": detached,
		"key": "%d_%d_%d" % [int(bucket), bounded, int(detached)]}

## The state the next load applies (any thread). Until Main's node publishes
## one, the rig's default distance at the quality in use now (not remembered,
## so a quality set before the first update is never missed).
static func current_state() -> Dictionary:
	_mutex.lock()
	var state := _state.duplicate()
	_mutex.unlock()
	return state if not state.is_empty() else state_for(DEFAULT_CAMERA_DISTANCE, LookProfile.quality())

static func _publish(state: Dictionary) -> void:
	_mutex.lock()
	_state = state.duplicate()
	_mutex.unlock()

static func _stamp_group(key: String) -> StringName:
	_mutex.lock()
	var group: Variant = _stamps.get(key)
	if group == null:
		group = StringName(STAMP_PREFIX + key)
		_stamps[key] = group
		_stamp_revision += 1
	_mutex.unlock()
	return group as StringName

static func _build_groups() -> Dictionary:
	var groups := {}
	for distance_class: String in RANGED_CLASSES:
		var steps: Array[StringName] = []
		for step: int in Classes.EXTENT_STEPS + 1:
			steps.append(StringName("%s%s_%d" % [GROUP_PREFIX, distance_class, step]))
		groups[distance_class] = steps
	return groups

## The group of `distance_class` at extent step `step`.
static func group_of(distance_class: String, step: int) -> StringName:
	return (_groups[distance_class] as Array)[step]

## Forgets the published state and the stamps (tests only).
static func reset_state() -> void:
	_mutex.lock()
	_state = {}
	_stamps = {}
	_stamp_revision += 1
	_mutex.unlock()

# --------------------------------------------------------------------------
# The pass
# --------------------------------------------------------------------------

## Classes and ranges what a freshly loaded `root` draws when `manifest` is a
## continent territory, chunk or gauntlet and the pass is on; {} otherwise.
## Safe on a private worker tree. Returns counts ("ranged", "lod_only",
## "shadows_off", "ground_shadows_off", "usec"); with `record`, also "undo":
## [[node, {property: value before}], ...] for every node it changed.
static func apply_loaded(root: Node3D, manifest: WorldManifest, record := false) -> Dictionary:
	if root == null or manifest == null or not Classes.applies_to(manifest.data) \
			or not enabled_by_environment():
		return {}
	return apply_root(root, current_state(), record)

## The pass itself on `root` under `state` (`state_for`). Idempotent: a
## second run changes nothing but the ranges, to `state`'s.
static func apply_root(root: Node3D, state: Dictionary, record := false) -> Dictionary:
	var began := Time.get_ticks_usec()
	var found := _collect(root)
	var result := {"ranged": 0, "lod_only": 0, "shadows_off": 0, "ground_shadows_off": 0}
	# Node instance id -> [node, {property: value before}], first write only.
	var undo: Variant = {} if record else null
	var bias := Classes.lod_bias(str(state.quality_name))
	var members_by_batch: Dictionary = found.members
	var anchor_sizes: Dictionary = found.anchor_sizes
	for batch: MultiMeshInstance3D in found.batches:
		var members: Array = members_by_batch.get(batch.get_instance_id(), [])
		_apply_batch(batch, members, anchor_sizes, state, bias, result, undo)
	var base_casts: bool = found.base_casts
	for row: Array in found.singles:
		_apply_loose(row[0] as MeshInstance3D, row[1], base_casts, state, bias, result, undo)
	for parts: Array in (found.assemblies as Dictionary).values():
		var size := int(anchor_sizes.get(parts[0][2], 1))
		if parts.size() == 1 and size <= 1:
			# Alone at its placement (a section node's prop): a single.
			_apply_loose(parts[0][0] as MeshInstance3D, parts[0][1], base_casts, state, bias, result, undo)
		else:
			_apply_assembly(parts, size > parts.size(), base_casts, state, bias, result, undo)
	_stamp(root, str(state.key))
	result["usec"] = Time.get_ticks_usec() - began
	if record:
		result["undo"] = (undo as Dictionary).values()
	return result

## One walk: static batches, their members (by batch), every other mesh
## instance with its root-relative placement grouped by assembly, and whether
## an opaque, shadow-casting base is present. Streaming previews and shared
## border cells are skipped, as the batcher skips them.
##
## An assembly is one object the exporter split by material: mesh instances
## under one parent below the root that share their local transform (the
## parts of a split object are drawn from one placement; the props a section
## node such as a gauntlet's `Dress_fort` holds each have their own). Its
## parts are classed, ranged and shadowed as one, so an object never loses its
## small parts at distance (a cart its wheels, a market canopy its posts).
## Each row is [node, placement, assembly key, batched]; `anchor_sizes`
## counts the meshes of every assembly key, batch members included (a key
## missing from it is a single mesh).
static func _collect(root: Node3D) -> Dictionary:
	var batches: Array[MultiMeshInstance3D] = []
	var members: Dictionary = {}
	var rows: Array = []
	var parent_counts: Dictionary = {}
	var base_casts := false
	# Parallel stacks: a node and its root-relative placement.
	var nodes: Array[Node] = [root]
	var placements: Array[Transform3D] = [Transform3D.IDENTITY]
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		var placed: Transform3D = placements.pop_back()
		for child: Node in node.get_children():
			var spatial := child as Node3D
			if spatial == null:
				nodes.append(child)
				placements.append(placed)
				continue
			if String(child.name).begins_with("StreamPreview_") or child.has_meta("stream_borders"):
				continue
			nodes.append(child)
			placements.append(placed * spatial.transform)
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null:
			if node is MultiMeshInstance3D and String(node.name).begins_with(BATCH_PREFIX):
				batches.append(node as MultiMeshInstance3D)
			continue
		if mesh_instance.mesh == null:
			continue
		# The parent a split object's parts share. The root and the loader's own
		# grouping nodes (WorldLoader._regroup_wide_siblings) are not objects: a
		# mesh directly under them is its own assembly.
		var parent := node.get_parent()
		var own := parent == root or String(parent.name).begins_with(WORLD_GROUP_PREFIX)
		var key: Variant = node.get_instance_id() if own else parent.get_instance_id()
		var row: Array = [mesh_instance, placed, key]
		rows.append(row)
		parent_counts[key] = int(parent_counts.get(key, 0)) + 1
		if mesh_instance.has_meta(BATCH_PATH_META) or mesh_instance.has_meta(BATCH_META):
			var batch := _batch_of(mesh_instance, root)
			if batch != null:
				var id := batch.get_instance_id()
				if members.has(id):
					(members[id] as Array).append(row)
				else:
					members[id] = [row]
			row.append(true)
			continue
		row.append(false)
		if not base_casts and Classes.ground_kind(String(mesh_instance.name)) == Classes.Ground.BASE:
			base_casts = _opaque(mesh_instance) and _casts(mesh_instance)
	# Siblings are one assembly only when they share their local transform;
	# a mesh alone under its parent (nearly all of them) is a single.
	var singles: Array = []
	var assemblies: Dictionary = {}
	var anchor_sizes: Dictionary = {}
	for row: Array in rows:
		if int(parent_counts[row[2]]) == 1:
			if not bool(row[3]):
				singles.append(row)
			continue
		row[2] = "%d|%s" % [int(row[2]), (row[0] as Node3D).transform]
		anchor_sizes[row[2]] = int(anchor_sizes.get(row[2], 0)) + 1
		if bool(row[3]):
			continue
		if assemblies.has(row[2]):
			(assemblies[row[2]] as Array).append(row)
		else:
			assemblies[row[2]] = [row]
	return {"batches": batches, "members": members, "singles": singles, "assemblies": assemblies,
		"anchor_sizes": anchor_sizes, "base_casts": base_casts}

static func _batch_of(member: MeshInstance3D, root: Node) -> MultiMeshInstance3D:
	if member.has_meta(BATCH_META):
		var link: Variant = member.get_meta(BATCH_META)
		if link is Object and is_instance_valid(link) and link is MultiMeshInstance3D:
			return link as MultiMeshInstance3D
	var path: Variant = member.get_meta(BATCH_PATH_META) if member.has_meta(BATCH_PATH_META) else null
	return root.get_node_or_null(path as NodePath) as MultiMeshInstance3D if path is NodePath else null

static func _opaque(mesh_instance: MeshInstance3D) -> bool:
	for surface: int in mesh_instance.mesh.get_surface_count():
		var material := mesh_instance.get_active_material(surface) as BaseMaterial3D
		if material != null and material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			return false
	return mesh_instance.visible

## Whether a box `mesh_box` placed by `placed` is flat (Classes.is_flat on its
## vertical extent and its footprint's narrower width).
static func _flat(mesh_box: AABB, placed: Transform3D) -> bool:
	return Classes.is_flat((placed * mesh_box).size.y, Classes.footprint_width(mesh_box.size, placed.basis))

## Pieces drawn at every distance whatever their size: bridge and pier
## structure (the walk decks it carries are ground, never ranged) and the
## lamp models NightLamps gives a halo (the halo is drawn at any distance).
static func _keeps_whole(node_name: String) -> bool:
	return Classes.is_structure(node_name) or not NightLamps.kind_of(node_name).is_empty()

static func _apply_batch(batch: MultiMeshInstance3D, members: Array, anchor_sizes: Dictionary,
		state: Dictionary, bias: float, result: Dictionary, undo: Variant) -> void:
	var multimesh := batch.multimesh
	if multimesh == null or multimesh.mesh == null:
		return
	var mesh_box := multimesh.mesh.get_aabb()
	var member_name := str((members[0][0] as Node).name) if not members.is_empty() \
		else _batch_member_name(str(batch.name))
	var ground := Classes.ground_kind(member_name)
	if ground == Classes.Ground.WATER or ground == Classes.Ground.BASE:
		return
	# A batch that draws parts of material-split objects (an assembly, see
	# `_collect`) keeps its shadow and is never ranged: the objects' other
	# parts are not in it, and they must not lose these at distance.
	var in_assembly := false
	for entry: Array in members:
		if int(anchor_sizes.get(entry[2], 1)) > 1:
			in_assembly = true
			break
	var distance_class := str(batch.get_meta(Classes.CLASS_META, ""))
	var legacy := distance_class.is_empty()
	var flat := true
	var small_or_flat := true
	var union := AABB()
	for index: int in members.size():
		var placed: Transform3D = members[index][1]
		var box := placed * mesh_box
		union = box if index == 0 else union.merge(box)
		# Only while it can still matter: one member that is not flat settles
		# `flat`, and only a legacy batch asks each member.
		var member_flat := Classes.is_flat(box.size.y, Classes.footprint_width(mesh_box.size, placed.basis)) \
			if flat or legacy else false
		flat = flat and member_flat
		if legacy:
			small_or_flat = small_or_flat and (member_flat or not Classes.CASTS_SHADOW[
				Classes.size_class(Classes.placement_radius(mesh_box, placed.basis))])
	if members.is_empty():
		flat = _flat(mesh_box, Transform3D.IDENTITY)
		small_or_flat = flat
	var shadow_off: bool
	if ground != Classes.Ground.NONE:
		shadow_off = ground == Classes.Ground.PATCH or (ground == Classes.Ground.DECK and flat)
	elif in_assembly:
		shadow_off = false
	elif distance_class.is_empty():
		shadow_off = small_or_flat
	else:
		shadow_off = flat or not bool(Classes.CASTS_SHADOW.get(distance_class, true))
	if shadow_off and _casts(batch):
		_note(batch, undo)
		batch.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		result["ground_shadows_off" if ground != Classes.Ground.NONE else "shadows_off"] += 1
	if shadow_off:
		for entry: Array in members:
			var member := entry[0] as MeshInstance3D
			if _casts(member):
				_note(member, undo)
				member.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	if ground != Classes.Ground.NONE:
		return
	if distance_class.is_empty() or not RANGED_CLASSES.has(distance_class) or in_assembly \
			or _keeps_whole(member_name):
		# A legacy batch stands at the identity: its box centre is not where
		# its members are, so it is never ranged. It, XL, assembly parts,
		# structure and lamps take the bias only.
		_join_lod(batch, bias, result, undo)
		return
	var extent: float
	if not members.is_empty() and members.size() >= multimesh.instance_count:
		extent = union.size.length() * 0.5
	else:
		# Members a prepared scene dropped: the drawn box (asked of the
		# rendering server on Main only), else the cell's.
		var drawn := multimesh.get_aabb() if OS.get_thread_caller_id() == OS.get_main_thread_id() else AABB()
		extent = drawn.size.length() * 0.5 if drawn.size.length() > 0.0 \
			else _cell_extent(distance_class)
	var step := Classes.extent_step(extent)
	if step < 0:
		_join_lod(batch, bias, result, undo)
	elif not _authored(batch, group_of(distance_class, step)):
		_join_range(batch, distance_class, step, state, bias, result, undo)

## The ground rules on one ground node of `ground` kind: patches, flat walk
## decks and (when an opaque base casts the ground's shadow, `base_casts`)
## terrain stop casting. Ground is never ranged.
static func _apply_ground(node: MeshInstance3D, ground: Classes.Ground, flat: bool, base_casts: bool,
		result: Dictionary, undo: Variant) -> void:
	var off := ground == Classes.Ground.PATCH \
		or (ground == Classes.Ground.TERRAIN and base_casts) \
		or (ground == Classes.Ground.DECK and flat)
	if off and _casts(node):
		_note(node, undo)
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		result["ground_shadows_off"] += 1

static func _apply_loose(node: MeshInstance3D, placed: Transform3D, base_casts: bool, state: Dictionary,
		bias: float, result: Dictionary, undo: Variant) -> void:
	var ground := Classes.ground_kind(str(node.name))
	var mesh_box := node.mesh.get_aabb()
	var box := placed * mesh_box
	if ground != Classes.Ground.NONE:
		_apply_ground(node, ground, _flat(mesh_box, placed), base_casts, result, undo)
		return
	if not node.visible or node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY \
			or _has_collision(node):
		return
	var distance_class := Classes.size_class(Classes.placement_radius(mesh_box, placed.basis))
	var step := Classes.extent_step(box.size.length() * 0.5) \
		if RANGED_CLASSES.has(distance_class) and not _keeps_whole(str(node.name)) else -1
	var group := group_of(distance_class, step) if step >= 0 else LOD_GROUP
	if _authored(node, group):
		return
	if _casts(node) and (not bool(Classes.CASTS_SHADOW[distance_class]) or _flat(mesh_box, placed)):
		_note(node, undo)
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		result["shadows_off"] += 1
	if step >= 0:
		_join_range(node, distance_class, step, state, bias, result, undo)
	else:
		_join_lod(node, bias, result, undo)

## One material-split object: the loose parts of one assembly (`parts`, rows
## of [node, placement, key, batched], `_collect`); `has_batched` when some of
## its parts are batch members. Ground parts take the ground rules. The other
## parts are classed by their union box and take one shadow rule and one
## range, so they vanish together. They are left alone, as a single node
## would be, when any carries
## collision or a range of its own, and never ranged (the LOD bias only) when
## the object holds ground, structure, a lamp or batched parts; with batched
## parts their shadows stay too, as `_apply_batch` leaves the batch's. Parts
## spread wider than Classes.ASSEMBLY_SPREAD times the largest are not one
## object and are passed one by one.
static func _apply_assembly(parts: Array, has_batched: bool, base_casts: bool, state: Dictionary,
		bias: float, result: Dictionary, undo: Variant) -> void:
	var props: Array = []
	var keep := has_batched
	var untouched := false
	var flat := true
	var union := AABB()
	var largest := 0.0
	for part: Array in parts:
		var node := part[0] as MeshInstance3D
		var placed: Transform3D = part[1]
		var mesh_box := node.mesh.get_aabb()
		var ground := Classes.ground_kind(str(node.name))
		if ground != Classes.Ground.NONE:
			_apply_ground(node, ground, _flat(mesh_box, placed), base_casts, result, undo)
			keep = true
			continue
		var box := placed * mesh_box
		union = box if props.is_empty() else union.merge(box)
		largest = maxf(largest, Classes.radius_of(box))
		flat = flat and _flat(mesh_box, placed)
		keep = keep or _keeps_whole(str(node.name))
		untouched = untouched or _has_collision(node)
		props.append(node)
	if props.is_empty():
		return
	if not has_batched and Classes.radius_of(union) > Classes.ASSEMBLY_SPREAD * largest:
		for part: Array in parts:
			if Classes.ground_kind(str((part[0] as Node).name)) == Classes.Ground.NONE:
				_apply_loose(part[0] as MeshInstance3D, part[1], base_casts, state, bias, result, undo)
		return
	if untouched:
		return
	var distance_class := Classes.size_class(Classes.radius_of(union))
	var step := Classes.extent_step(Classes.radius_of(union)) \
		if RANGED_CLASSES.has(distance_class) and not keep else -1
	var group := group_of(distance_class, step) if step >= 0 else LOD_GROUP
	var drawn: Array[MeshInstance3D] = []
	for node: MeshInstance3D in props:
		if not node.visible or node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY:
			continue
		if _authored(node, group):
			return
		drawn.append(node)
	var shadow_off := not has_batched and (flat or not bool(Classes.CASTS_SHADOW[distance_class]))
	for node: MeshInstance3D in drawn:
		if shadow_off and _casts(node):
			_note(node, undo)
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			result["shadows_off"] += 1
		if step >= 0:
			_join_range(node, distance_class, step, state, bias, result, undo)
		else:
			_join_lod(node, bias, result, undo)

## A range this pass did not give: a node that is not in `group` (the one the
## pass would put it in) yet carries a visibility range is left alone.
static func _authored(node: GeometryInstance3D, group: StringName) -> bool:
	return (node.visibility_range_begin > 0.0 or node.visibility_range_end > 0.0) and not node.is_in_group(group)

## Joins the class/extent group and takes the state's range end.
static func _join_range(node: GeometryInstance3D, distance_class: String, step: int,
		state: Dictionary, bias: float, result: Dictionary, undo: Variant) -> void:
	var end := 0.0 if bool(state.detached) \
		else Classes.range_end(distance_class, step, float(state.bucket), str(state.quality_name))
	_note(node, undo)
	node.add_to_group(group_of(distance_class, step))
	node.visibility_range_end = end
	node.visibility_range_end_margin = Classes.RANGE_MARGIN_METRES
	node.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
	node.lod_bias = bias
	result["ranged"] += 1

static func _join_lod(node: GeometryInstance3D, bias: float, result: Dictionary, undo: Variant) -> void:
	_note(node, undo)
	node.add_to_group(LOD_GROUP)
	node.lod_bias = bias
	result["lod_only"] += 1

static func _casts(node: GeometryInstance3D) -> bool:
	return node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON \
		or node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED

static func _has_collision(node: Node) -> bool:
	for child: Node in node.get_children():
		if child is CollisionObject3D:
			return true
	return false

## Records `node`'s writable properties once, before the pass first changes it.
static func _note(node: GeometryInstance3D, undo: Variant) -> void:
	if undo == null:
		return
	var records := undo as Dictionary
	var id := node.get_instance_id()
	if records.has(id):
		return
	var before := {}
	for property: StringName in PROPERTIES:
		before[property] = node.get(property)
	records[id] = [node, before]

## `StaticBatch_<n>_<first member>` -> the first member's name.
static func _batch_member_name(batch_name: String) -> String:
	var rest := batch_name.trim_prefix(BATCH_PREFIX)
	var cut := rest.find("_")
	return rest.substr(cut + 1) if cut >= 0 else rest

## The largest extent a class cell's batch can have (members anywhere in the
## cell, each up to the class's radius limit).
static func _cell_extent(distance_class: String) -> float:
	var index := Classes.CLASSES.find(distance_class)
	var limit: float = Classes.CLASS_RADIUS_LIMITS[mini(index, Classes.CLASS_RADIUS_LIMITS.size() - 1)]
	return (Classes.cell_metres(distance_class) + 2.0 * limit) * sqrt(3.0) * 0.5

## Gives `root` the stamp of the state its ranges now follow.
static func _stamp(root: Node, key: String) -> void:
	var group := _stamp_group(key)
	for existing: StringName in root.get_groups():
		if String(existing).begins_with(STAMP_PREFIX) and existing != group:
			root.remove_from_group(existing)
	root.add_to_group(group)

## Puts back what `undo` (apply_root's record) says, returning what to put
## back afterwards in the same shape.
static func restore(undo: Array) -> Array:
	var redo: Array = []
	for entry: Array in undo:
		var node := entry[0] as Node
		if not is_instance_valid(node):
			continue
		var now := {}
		var before: Dictionary = entry[1]
		for property: StringName in before:
			now[property] = node.get(property)
			node.set(property, before[property])
		redo.append([node, now])
	return redo

# --------------------------------------------------------------------------
# The node: following the camera
# --------------------------------------------------------------------------

## Once a frame: the rig's orbit `distance`, the LookProfile.Quality in use, and
## whether the rendered camera is detached from the rig (a campaign film or a
## cutaway: nothing is culled while it is). O(1) when nothing changed.
func update(distance: float, level: int, detached := false) -> void:
	camera_distance = distance
	quality = level
	camera_detached = detached
	if not enabled or not is_inside_tree():
		return
	if not _now.is_empty() and Classes.camera_bucket(distance) == float(_now.bucket) \
			and clampi(level, 0, LookProfile.QUALITY_NAMES.size() - 1) == int(_now.quality) \
			and detached == bool(_now.detached):
		_check_stale()
		return
	var state := state_for(distance, level, detached)
	if _now.is_empty() or str(state.key) != str(_now.key):
		var lod := _now.is_empty() or int(state.quality) != int(_now.quality)
		_now = state
		_publish(state)
		_apply_groups(state, lod)
		_restamp(state)
		return
	_check_stale()

## The graphics quality changed (Main's `_apply_graphics_quality`).
func set_quality(level: int) -> void:
	update(camera_distance, level, camera_detached)

## Checks each cell of `stream` (a ContinentChunkStream) as it arrives, in the
## frame it arrives, rather than at the next `update`.
func watch(stream: Node) -> void:
	_streams.assign(_streams.filter(func(known: Variant) -> bool: return is_instance_valid(known)))
	if stream == null or _streams.has(stream) or not stream.has_signal(&"cell_ready"):
		return
	_streams.append(stream)
	stream.connect(&"cell_ready", _on_cell_ready)

func _on_cell_ready(_identity: String, _imported: Node3D) -> void:
	if enabled and not _now.is_empty() and is_inside_tree():
		_check_stale()

## A tree in the scene stamped with another state than the current one: apply
## the ranges again so it follows.
func _check_stale() -> void:
	_refresh_stamp_keys()
	var tree := get_tree()
	var stale := false
	var lod := false
	for key: String in _stamp_keys:
		if key == str(_now.key) or tree.get_node_count_in_group(_stamp_keys[key]) == 0:
			continue
		stale = true
		lod = lod or key.get_slice("_", 1).to_int() != int(_now.quality)
	if stale:
		refreshes += 1
		_apply_groups(_now, lod)
		_restamp(_now)

func _refresh_stamp_keys() -> void:
	_mutex.lock()
	if _seen_revision != _stamp_revision:
		_seen_revision = _stamp_revision
		_stamp_keys = _stamps.duplicate()
	_mutex.unlock()

func _apply_groups(state: Dictionary, lod: bool) -> void:
	var began := Time.get_ticks_usec()
	var tree := get_tree()
	var quality_name := str(state.quality_name)
	var bias := Classes.lod_bias(quality_name)
	for distance_class: String in RANGED_CLASSES:
		var groups: Array = _groups[distance_class]
		for step: int in groups.size():
			var group: StringName = groups[step]
			if tree.get_node_count_in_group(group) == 0:
				continue
			var end := 0.0 if bool(state.detached) \
				else Classes.range_end(distance_class, step, float(state.bucket), quality_name)
			tree.set_group(group, &"visibility_range_end", end)
			if lod:
				tree.set_group(group, &"lod_bias", bias)
	if lod and tree.get_node_count_in_group(LOD_GROUP) > 0:
		tree.set_group(LOD_GROUP, &"lod_bias", bias)
	applies += 1
	last_apply_usec = Time.get_ticks_usec() - began
	max_apply_usec = maxi(max_apply_usec, last_apply_usec)

## Every classed root in the scene now follows `state`.
func _restamp(state: Dictionary) -> void:
	var tree := get_tree()
	var current := _stamp_group(str(state.key))
	_refresh_stamp_keys()
	for key: String in _stamp_keys:
		var group: StringName = _stamp_keys[key]
		if group == current or tree.get_node_count_in_group(group) == 0:
			continue
		for node: Node in tree.get_nodes_in_group(group):
			node.remove_from_group(group)
			node.add_to_group(current)

## What the camera probe and diagnostics record.
func snapshot() -> Dictionary:
	var state := _now if not _now.is_empty() else state_for(camera_distance, maxi(quality, 0), camera_detached)
	var quality_name := str(state.quality_name)
	var reach := {}
	var ends := {}
	var counts := {}
	var tree := get_tree() if is_inside_tree() else null
	for distance_class: String in RANGED_CLASSES:
		reach[distance_class] = Classes.reach_metres(distance_class, quality_name)
		ends[distance_class] = 0.0 if bool(state.detached) \
			else Classes.range_end(distance_class, 0, float(state.bucket), quality_name)
		var count := 0
		if tree != null:
			for group: StringName in _groups[distance_class]:
				count += tree.get_node_count_in_group(group)
		counts[distance_class] = count
	counts["lod_only"] = tree.get_node_count_in_group(LOD_GROUP) if tree != null else 0
	var stamped := 0
	var stale := 0
	if tree != null:
		_refresh_stamp_keys()
		for key: String in _stamp_keys:
			var in_tree := tree.get_node_count_in_group(_stamp_keys[key])
			if key == str(state.key):
				stamped += in_tree
			else:
				stale += in_tree
	return {"enabled": enabled, "camera_distance": camera_distance, "bucket_metres": float(state.bucket),
		"quality": quality_name, "camera_detached": bool(state.detached),
		"reach_metres": reach, "range_end_metres": ends, "lod_bias": Classes.lod_bias(quality_name),
		"nodes": counts, "roots": stamped, "stale_roots": stale, "applies": applies,
		"refreshes": refreshes, "last_apply_us": last_apply_usec, "max_apply_us": max_apply_usec}

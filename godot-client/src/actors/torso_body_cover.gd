class_name TorsoBodyCover
extends RefCounted
## Generated clothing supplies its own fitted backing. Remove the default
## split wardrobe surfaces and covered body faces beneath it.
## Work on a copy of the index buffers: UVs, skinning, materials and the original
## mesh remain intact, and unequipping restores the exact original resource.
##
## A race body (eloria-assets/tools/rebase_race_body.py) is the Human body below
## the neck, weights included, with its race head carried by two "Shared neck
## bridge" surfaces: the Human's own neck faces textured for the race, and a
## join from the Human's neck ring (travel .075 along neck_01 -> Head) up to the
## head rim whose every vertex keeps at least .64 Head/neck_01 weight. Bridge
## faces take the same test as the rest of the body, so a race's neck is cut
## where the Human's is and the bridge above the ring, the visible neck under
## every collar, stays whole. Only the throat differs, see
## FRONT_BRIDGE_MIN_WEIGHT.

const BACKING_NAME := "GeneratedArmorBacking"
const LOW := 0.95
const HIGH := 1.535
const WRIST := 0.665
const NECK_ENVELOPE_MIN_Y := 1.40
const NECK_ENVELOPE_HALF_WIDTH := .18
const NECK_RIM_MIN_Y := 1.35
const NECK_RIM_MAX_Y := 1.55
const NECK_RIM_HALF_WIDTH := .10
const NECK_RIM_MIN_Z := -.11
const NECK_RIM_MAX_Z := .11
const NECK_RIM_INSET := .65
const FRONT_APRON_MIN_Y := 1.403
const FRONT_APRON_MAX_Y := 1.470
const FRONT_APRON_HALF_WIDTH := .032
const FRONT_APRON_MIN_Z := .005
## In front of the canonical neck_01 -> Head axis a bridge is the throat,
## framed by the open front of coats such as 5:184, 5:189 and 5:222. The female
## bridge carries 16 of the Human's throat faces whose lowest corner keeps only
## .32 to .5 Head/neck_01 weight, and the whole-face .5 test cut them into a
## saw-tooth spike in every open front. Bridge faces there stay while every
## corner keeps more than this weight. No corner of a rebuilt bridge is below
## .32, so on today's bodies this keeps every bridge face; the floor still drops
## a face pinned to the chest by a near-zero corner. Behind the axis, and on
## every face that is not bridge (the Human's own throat included), the
## whole-face test applies. Re-checked on the rebuilt bodies 2026-10-07 under
## all 64 generated torsos.
const FRONT_BRIDGE_MIN_WEIGHT := .25
const NECK_AXIS_BASE := Vector3(0., 1.452, -.051)
const NECK_AXIS_TOP := Vector3(0., 1.568, .011)
## A wardrobe-only neckline tucks its open rim behind the fitted shirt. On a
## bridged race the bridge and the race head above this height are the visible
## neck and head, so they stay put, open edges and all.
const WARDROBE_BRIDGE_RIM_MAX_Y := 1.50
const BRIDGE_MATERIAL := "Shared neck bridge"
const RACE_HEAD_MATERIAL := "Race head"

static var _cache: Dictionary = {}

## Covered meshes are shared across equivalent actors for the duration of one
## session. Release those derived resources alongside the imported scene cache
## when leaving a world, so later sessions cannot accumulate stale mesh ids.
static func clear() -> void:
	_cache.clear()

static func covers(point: Vector3, regions: Array = [], preserve_tail: bool = false) -> bool:
	if preserve_tail and is_tail(point):
		return false
	if regions.is_empty():
		return point.y > LOW and point.y < HIGH and absf(point.x) < WRIST
	for region: Vector3 in regions:
		if point.y > region.x and point.y < region.y and absf(point.x) < region.z:
			return true
	return false

static func apply(instance: MeshInstance3D, enabled: bool,
		to_rig: Transform3D, fit: float, regions: Array = [],
		preserve_tail: bool = false,
		mask_to_wardrobe_neckline: bool = false) -> void:
	if not instance.has_meta("uncovered_body_mesh"):
		if not enabled or instance.mesh == null:
			return
		instance.set_meta("uncovered_body_mesh", instance.mesh)
	var original: Mesh = instance.get_meta("uncovered_body_mesh") as Mesh
	if not enabled:
		instance.mesh = original
		return
	# The original shirt collar can extend above the trunk coverage band.
	# Its replacement is the equipped collar; leave neck skin on the body.
	if instance.name.to_lower() == "wardrobe_shirt" and covers(Vector3(0., 1.30, 0.), regions):
		regions = regions.duplicate()
		if regions.is_empty():
			regions.append(Vector3(LOW, HIGH, WRIST))
		regions.append(Vector3(1.40, 1.65, .20))
	var protected_binds := PackedInt32Array()
	if instance.skin != null and instance.name.to_lower() in ["body", "char1", "mesh_node"]:
		var skeleton := instance.get_node_or_null(instance.skeleton) as Skeleton3D
		for bind: int in range(instance.skin.get_bind_count()):
			var bone_name := instance.skin.get_bind_name(bind)
			var bone_index := instance.skin.get_bind_bone(bind)
			# Imported body skins may use numeric binds; rebound equipment uses
			# named binds. Both forms identify the same canonical joints.
			if bone_name.is_empty() and skeleton != null and bone_index >= 0:
				bone_name = skeleton.get_bone_name(bone_index)
			if bone_name in [&"Head", &"neck_01"]:
				protected_binds.append(bind)
	var key := "%s|%s|%s|%s|%s|%s|%s" % [original.get_instance_id(), to_rig,
		fit, regions, preserve_tail, protected_binds, mask_to_wardrobe_neckline]
	if not _cache.has(key):
		_cache[key] = cut(original, to_rig, fit, regions, preserve_tail,
			protected_binds, mask_to_wardrobe_neckline)
	instance.mesh = _cache[key] as Mesh

static func cut(original: Mesh, to_rig: Transform3D, fit: float,
		regions: Array = [], preserve_tail: bool = false,
		protected_binds: PackedInt32Array = PackedInt32Array(),
		mask_to_wardrobe_neckline: bool = false) -> ArrayMesh:
	var result := ArrayMesh.new()
	# Pants and boots also request body coverage, but must never activate the
	# shaped collar mask.  Only a region that reaches the lower neck opts into
	# the geometry-first whole-face neckline below.
	var shaped_neck_active := (mask_to_wardrobe_neckline
		or (not protected_binds.is_empty()
			and covers(Vector3(0., NECK_ENVELOPE_MIN_Y, 0.), regions, preserve_tail)))
	for blend: int in range(original.get_blend_shape_count()):
		result.add_blend_shape(original.get_blend_shape_name(blend))
	if original is ArrayMesh:
		result.blend_shape_mode = (original as ArrayMesh).blend_shape_mode
	# Read every surface before touching any of them. A race's shared body, neck
	# bridge and head are separate surfaces welded along seams, so a detached
	# shell and the true open rim are only known across all of them.
	var passes: Array[Dictionary] = []
	for surface: int in range(original.get_surface_count()):
		var arrays: Array = original.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var source: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if source.is_empty():
			for index: int in range(vertices.size()):
				source.append(index)
		var bones := PackedInt32Array()
		if arrays[Mesh.ARRAY_BONES] is PackedInt32Array:
			bones = arrays[Mesh.ARRAY_BONES] as PackedInt32Array
		var weights := PackedFloat32Array()
		if arrays[Mesh.ARRAY_WEIGHTS] is PackedFloat32Array:
			weights = arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
		var stride: int = bones.size() / maxi(vertices.size(), 1)
		var material := original.surface_get_material(surface)
		var material_name := material.resource_name if material != null else ""
		passes.append({"arrays": arrays, "vertices": vertices, "bones": bones,
			"weights": weights, "stride": stride, "source": source,
			"bridge": material_name == BRIDGE_MATERIAL,
			"head": material_name == RACE_HEAD_MATERIAL, "detached": {}})
	var welded: Array[PackedInt32Array] = []
	if mask_to_wardrobe_neckline:
		welded = _welded_points(passes, to_rig, fit)
		_detached_neck_vertices(passes, welded, to_rig, fit)
	# Classify faces before moving the derived rim. The tuck must not cause
	# coverage to walk down successive torso rows.
	for entry: Dictionary in passes:
		entry["kept"] = _filtered_indices(entry["source"], entry["vertices"],
			entry["bones"], entry["weights"], entry["stride"], to_rig, fit,
			regions, preserve_tail, protected_binds, shaped_neck_active,
			mask_to_wardrobe_neckline, entry["detached"], entry["bridge"])
	if mask_to_wardrobe_neckline:
		_inset_wardrobe_neckline_rim(passes, welded, to_rig, fit)
	for surface: int in range(original.get_surface_count()):
		var entry := passes[surface]
		var arrays: Array = entry["arrays"]
		var kept: PackedInt32Array = entry["kept"]
		var lod_candidates: Dictionary = {}
		var source_lods := _surface_lods(original, surface)
		for distance: Variant in source_lods:
			lod_candidates[distance] = _filtered_indices(
				source_lods[distance] as PackedInt32Array, entry["vertices"],
				entry["bones"], entry["weights"], entry["stride"], to_rig, fit,
				regions, preserve_tail, protected_binds, shaped_neck_active,
				mask_to_wardrobe_neckline, entry["detached"], entry["bridge"])
		var blend_arrays: Array = original.surface_get_blend_shape_arrays(surface)
		# Preserve surface numbering and its material overrides even when a
		# whole wardrobe surface is covered. A zero-area triangle draws nothing.
		if kept.is_empty():
			kept = PackedInt32Array([0, 0, 0])
		var lods: Dictionary = {}
		for distance: Variant in lod_candidates:
			var lod_kept := lod_candidates[distance] as PackedInt32Array
			# Godot rejects empty LODs and levels which do not reduce the base
			# index count. Omitting one keeps the last valid level visible instead
			# of replacing it with a disappearing, degenerate surface.
			if not lod_kept.is_empty() and lod_kept.size() < kept.size():
				lods[distance] = lod_kept
		arrays[Mesh.ARRAY_INDEX] = kept
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays,
			blend_arrays, lods,
			original.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, original.surface_get_material(surface))
	return result

static func _filtered_indices(source: PackedInt32Array,
		vertices: PackedVector3Array, bones: PackedInt32Array,
		weights: PackedFloat32Array, stride: int, to_rig: Transform3D,
		fit: float, regions: Array, preserve_tail: bool,
		protected_binds: PackedInt32Array, shaped_neck_active: bool,
		mask_to_wardrobe_neckline: bool = false,
		detached_neck_vertices: Dictionary = {},
		bridge_surface: bool = false) -> PackedInt32Array:
	var kept := PackedInt32Array()
	for index: int in range(0, source.size(), 3):
		if (mask_to_wardrobe_neckline
				and (detached_neck_vertices.has(source[index])
					or detached_neck_vertices.has(source[index + 1])
					or detached_neck_vertices.has(source[index + 2]))):
			continue
		if _keeps_face(source, index, vertices, bones, weights, stride, to_rig,
				fit, regions, preserve_tail, protected_binds,
				shaped_neck_active, mask_to_wardrobe_neckline, bridge_surface):
			kept.append_array(source.slice(index, index + 3))
	return kept

static func _keeps_face(source: PackedInt32Array, index: int,
		vertices: PackedVector3Array, bones: PackedInt32Array,
		weights: PackedFloat32Array, stride: int, to_rig: Transform3D,
		fit: float, regions: Array, preserve_tail: bool,
		protected_binds: PackedInt32Array, shaped_neck_active: bool,
		mask_to_wardrobe_neckline: bool, bridge_surface: bool = false) -> bool:
	var center := (vertices[source[index]] + vertices[source[index + 1]]
		+ vertices[source[index + 2]]) / 3.0
	var head_weight := 0.0
	var lowest_corner_weight := 1.0
	var all_corners_protected := not protected_binds.is_empty()
	if not protected_binds.is_empty():
		for corner: int in range(3):
			var corner_head_weight := 0.0
			for slot: int in range(stride):
				var offset: int = source[index+corner]*stride+slot
				if bones[offset] in protected_binds:
					corner_head_weight += weights[offset]
			head_weight += corner_head_weight / 3.0
			lowest_corner_weight = minf(lowest_corner_weight, corner_head_weight)
			all_corners_protected = (all_corners_protected
				and corner_head_weight > .5)
	var rest_center: Vector3 = (to_rig * center) / fit
	# Empty regions traditionally mean the whole default torso band. A
	# wardrobe-only collar must not opt into that broad deletion: it owns only
	# the narrow neck envelope, while any explicit trouser/boot regions remain
	# additive.
	var covered := (false if mask_to_wardrobe_neckline and regions.is_empty()
		else covers(rest_center, regions, preserve_tail))
	if (mask_to_wardrobe_neckline
			and rest_center.y > NECK_ENVELOPE_MIN_Y and rest_center.y < HIGH
			and absf(rest_center.x) < NECK_ENVELOPE_HALF_WIDTH):
		covered = true
	# The laced shirt has a small intentional front opening. Preserve only the
	# short central apron behind it so cape colour cannot show through; the low,
	# wide connected apron remains covered and cannot recreate the skin bib.
	if (mask_to_wardrobe_neckline
			and rest_center.y > FRONT_APRON_MIN_Y
			and rest_center.y < FRONT_APRON_MAX_Y
			and absf(rest_center.x) < FRONT_APRON_HALF_WIDTH
			and rest_center.z > FRONT_APRON_MIN_Z):
		covered = false
	# Require the whole low-poly face to be part of the visible neck. A single
	# protected corner otherwise leaves a long skin triangle crossing the collar.
	var neck_envelope := (shaped_neck_active
		and covered
		and rest_center.y > NECK_ENVELOPE_MIN_Y
		and absf(rest_center.x) < NECK_ENVELOPE_HALF_WIDTH)
	var outer_head := head_weight > .5 and not neck_envelope
	# The bridge's throat inside an armour collar keeps its blended faces down to
	# FRONT_BRIDGE_MIN_WEIGHT. The wardrobe-only neckline owns its own front dip.
	if (neck_envelope and bridge_surface and not mask_to_wardrobe_neckline
			and rest_center.z >= _neck_axis_z(rest_center.y)):
		return lowest_corner_weight > FRONT_BRIDGE_MIN_WEIGHT
	# Otherwise fitted collars retain only faces whose complete triangle belongs
	# predominantly to Head/neck_01. Averaging the three corners let a strongly
	# weighted neck vertex keep two torso vertices, producing a long skin wedge
	# through the collar.
	return ((all_corners_protected if neck_envelope else
		(all_corners_protected if shaped_neck_active else outer_head)) or (not neck_envelope
		and not covered))

## Depth of the canonical neck_01 -> Head axis at a rest-space height.
static func _neck_axis_z(y: float) -> float:
	var along := (y - NECK_AXIS_BASE.y) / (NECK_AXIS_TOP.y - NECK_AXIS_BASE.y)
	return lerpf(NECK_AXIS_BASE.z, NECK_AXIS_TOP.z, along)

## Wardrobe-only class torsos expose a shaped opening rather than a horizontal
## band. Keep the neck high at the rear and sides, then dip smoothly only at
## the front centre where the fitted native shirt owns the visible collar.
static func _wardrobe_neckline_y(point: Vector3) -> float:
	var front := smoothstep(-0.040, 0.010, point.z)
	var centre := 1.0 - smoothstep(0.015, 0.100, absf(point.x))
	return lerpf(1.462, 1.450, front * centre)

## The narrow apron mask creates an open edge in coarse source topology. Weld
## UV-split duplicates in rest space, project only that retained edge to one
## smooth curve, and inset it behind the shirt. This keeps the coarse boundary
## behind the collar without deleting another body row. The source mesh
## remains immutable; the moved positions belong to the derived ArrayMesh.
## The rim is found across all surfaces at once: a race's neck bridge meets
## its head and the shared body along welded seams, and finding the rim one
## surface at a time took those seams for open edges, dragged them down to
## the neckline and folded the bridge over the collar. Points of the bridge
## and the race head above WARDROBE_BRIDGE_RIM_MAX_Y never move: they are the
## visible neck and head, and some race heads have open edges under the chin
## that are no neckline.
static func _inset_wardrobe_neckline_rim(passes: Array[Dictionary],
		welded: Array[PackedInt32Array], to_rig: Transform3D, fit: float) -> void:
	var edge_counts := {}
	var neck_points := {}
	for surface: int in range(passes.size()):
		var kept: PackedInt32Array = passes[surface]["kept"]
		var ids: PackedInt32Array = welded[surface]
		var visible_neck := bool(passes[surface]["bridge"]) or bool(passes[surface]["head"])
		for index: int in range(0, kept.size(), 3):
			for corner: int in range(3):
				var edge := _welded_edge(ids[kept[index + corner]],
					ids[kept[index + (corner + 1) % 3]])
				edge_counts[edge] = int(edge_counts.get(edge, 0)) + 1
				if visible_neck:
					neck_points[ids[kept[index + corner]]] = true
	var boundary_points := {}
	for edge_value: Variant in edge_counts:
		if int(edge_counts[edge_value]) != 1:
			continue
		var edge := edge_value as Vector2i
		boundary_points[edge.x] = true
		boundary_points[edge.y] = true
	var from_rig := to_rig.affine_inverse()
	for surface: int in range(passes.size()):
		if (passes[surface]["kept"] as PackedInt32Array).is_empty():
			continue
		var arrays: Array = passes[surface]["arrays"]
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var ids: PackedInt32Array = welded[surface]
		var result := vertices.duplicate()
		for vertex: int in range(vertices.size()):
			if not boundary_points.has(ids[vertex]):
				continue
			var rest_point := (to_rig * vertices[vertex]) / fit
			if (rest_point.y <= NECK_RIM_MIN_Y or rest_point.y >= NECK_RIM_MAX_Y
					or absf(rest_point.x) >= NECK_RIM_HALF_WIDTH
					or rest_point.z <= NECK_RIM_MIN_Z
					or rest_point.z >= NECK_RIM_MAX_Z):
				continue
			if (neck_points.has(ids[vertex])
					and rest_point.y > WARDROBE_BRIDGE_RIM_MAX_Y):
				continue
			rest_point.y = _wardrobe_neckline_y(rest_point)
			rest_point.x *= NECK_RIM_INSET
			rest_point.z *= NECK_RIM_INSET
			result[vertex] = from_rig * (rest_point * fit)
		arrays[Mesh.ARRAY_VERTEX] = result

## Rest-space point ids shared by every surface of one mesh. UV and normal
## splits, and the seams where the neck bridge meets the race head and the
## shared body, all collapse onto one id per position.
static func _welded_points(passes: Array[Dictionary], to_rig: Transform3D,
		fit: float) -> Array[PackedInt32Array]:
	var point_ids := {}
	var result: Array[PackedInt32Array] = []
	for entry: Dictionary in passes:
		var vertices: PackedVector3Array = entry["vertices"]
		var welded := PackedInt32Array()
		welded.resize(vertices.size())
		for vertex: int in range(vertices.size()):
			var point := (to_rig * vertices[vertex]) / fit
			var key := Vector3i(roundi(point.x * 100000.0), roundi(point.y * 100000.0),
				roundi(point.z * 100000.0))
			if not point_ids.has(key):
				point_ids[key] = point_ids.size()
			welded[vertex] = int(point_ids[key])
		result.append(welded)
	return result

static func _welded_edge(first: int, second: int) -> Vector2i:
	return Vector2i(mini(first, second), maxi(first, second))

## Some canonical heads carry a second, disconnected lower-neck shell. It is
## fully Head-weighted, so skinning weights cannot distinguish it from the
## anatomical neck. Find only small components wholly inside the collar band,
## welded across every surface: a race's neck bridge is split into surfaces
## whose fragments are joined to the body and the head only through those
## seams, and one surface at a time took them for loose shells and opened the
## throat. Each pass's "detached" vertex ids also mask generated LOD triangles
## which touch them.
static func _detached_neck_vertices(passes: Array[Dictionary],
		welded: Array[PackedInt32Array], to_rig: Transform3D, fit: float) -> void:
	var rest_points := {}
	for surface: int in range(passes.size()):
		var vertices: PackedVector3Array = passes[surface]["vertices"]
		var ids: PackedInt32Array = welded[surface]
		for vertex: int in range(vertices.size()):
			if not rest_points.has(ids[vertex]):
				rest_points[ids[vertex]] = (to_rig * vertices[vertex]) / fit
	var parents := PackedInt32Array()
	parents.resize(rest_points.size())
	for point_id: int in range(parents.size()):
		parents[point_id] = point_id
	for surface: int in range(passes.size()):
		var source: PackedInt32Array = passes[surface]["source"]
		var ids: PackedInt32Array = welded[surface]
		for index: int in range(0, source.size(), 3):
			var first_root := _component_root(parents, ids[source[index]])
			for corner: int in range(1, 3):
				var other_root := _component_root(parents, ids[source[index + corner]])
				if first_root != other_root:
					parents[other_root] = first_root
	var face_counts := {}
	for surface: int in range(passes.size()):
		var source: PackedInt32Array = passes[surface]["source"]
		var ids: PackedInt32Array = welded[surface]
		for index: int in range(0, source.size(), 3):
			var root := _component_root(parents, ids[source[index]])
			face_counts[root] = int(face_counts.get(root, 0)) + 1
	var minima := {}
	var maxima := {}
	for point_id: int in range(parents.size()):
		var root := _component_root(parents, point_id)
		var point := rest_points[point_id] as Vector3
		minima[root] = point if not minima.has(root) else (minima[root] as Vector3).min(point)
		maxima[root] = point if not maxima.has(root) else (maxima[root] as Vector3).max(point)
	var detached_roots := {}
	for root_value: Variant in face_counts:
		var root := int(root_value)
		var minimum := minima[root] as Vector3
		var maximum := maxima[root] as Vector3
		if (int(face_counts[root]) <= 128
				and minimum.y >= 1.460 and maximum.y <= 1.520
				and maxf(absf(minimum.x), absf(maximum.x)) <= 0.100
				and minimum.z >= -0.110 and maximum.z <= 0.040):
			detached_roots[root] = true
	for surface: int in range(passes.size()):
		var ids: PackedInt32Array = welded[surface]
		var detached := {}
		if not detached_roots.is_empty():
			for vertex: int in range(ids.size()):
				if detached_roots.has(_component_root(parents, ids[vertex])):
					detached[vertex] = true
		passes[surface]["detached"] = detached

static func _component_root(parents: PackedInt32Array, point_id: int) -> int:
	var root := point_id
	while parents[root] != root:
		root = parents[root]
	return root

## Godot 4.7 exposes generated LODs through RenderingServer as packed index
## buffers. Convert them back to the dictionary accepted by ArrayMesh.
static func _surface_lods(original: Mesh, surface: int) -> Dictionary:
	if original is not ArrayMesh:
		return {}
	var raw: Dictionary = RenderingServer.mesh_get_surface(
		original.get_rid(), surface)
	var raw_lods: Variant = raw.get("lods", [])
	if raw_lods is not Array:
		return {}
	var index_width := 2 if int(raw.get("vertex_count", 0)) <= 65536 else 4
	var result: Dictionary = {}
	for lod_value: Variant in raw_lods as Array:
		if lod_value is not Dictionary:
			continue
		var lod := lod_value as Dictionary
		var distance := float(lod.get("edge_length", 0.0))
		var bytes_value: Variant = lod.get("index_data", PackedByteArray())
		if distance <= 0.0 or bytes_value is not PackedByteArray:
			continue
		var bytes := bytes_value as PackedByteArray
		if bytes.is_empty() or bytes.size() % index_width != 0:
			continue
		var indices := PackedInt32Array()
		indices.resize(bytes.size() / index_width)
		for index: int in range(indices.size()):
			var offset := index * index_width
			indices[index] = (bytes.decode_u16(offset) if index_width == 2
				else bytes.decode_u32(offset))
		result[distance] = indices
	return result

## Canonical Rest_Pose geometry. Matches equipment_authoring.tail_region;
## source stripes never split the tail mask. No body vertices or weights move.
static func is_tail(point: Vector3) -> bool:
	if point.y >= .9367 or (point.x <= .13 and point.z >= -.11):
		return false
	var distance := INF
	for side: float in [-1.0, 1.0]:
		var chain := [Vector3(.089 * side, .9321, .0014),
			Vector3(.09109 * side, .52587, .01922),
			Vector3(.089 * side, .09796, -.04823),
			Vector3(.089 * side, .0152, .1132), Vector3(.089 * side, .0152, .2632)]
		for index: int in range(chain.size()-1):
			var a: Vector3 = chain[index]
			var axis: Vector3 = chain[index+1]-a
			var t := clampf((point-a).dot(axis)/axis.length_squared(),0.,1.)
			distance = minf(distance,point.distance_to(a+axis*t))
	return distance > .115

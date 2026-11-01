extends RefCounted
## Posterior torso surface in the live Spine skin frame. A covered point is
## governed by this visible surface even when it already lies clear of it.
const CELL := .08
const MARGIN := .008
const MAX_TEMPLATES := 16
const NativeMath := preload("res://src/actors/cape_native_math.gd")
static var _templates: Dictionary = {}
var _sources: Array[Dictionary] = []
var _grid: Dictionary = {}
var _uv := PackedVector2Array()
var _ab := PackedVector2Array()
var _ac := PackedVector2Array()
var _inverse_area := PackedFloat64Array()
var _heights := PackedVector3Array()
var _normals := PackedVector3Array()
var _bounds: Array[Rect2] = []
var _to_world := Transform3D.IDENTITY
var _from_world := Transform3D.IDENTITY
var _normal_to_world := Basis.IDENTITY
var _configure_usec := 0
var _prepare_usec := 0
var _vertex_count := 0
var _cache_hits := 0
var _actor: WeakRef
var _profile := ""
var _signature := ""
var _skeleton_id := 0
var _refreshes := 0
var _source_vertex_count := 0
var _pose_context: Array = []
var _pose_valid := false
var _pose_cache_hit := false
var _pose_cache_hits := 0
var _native: RefCounted
var _native_ready := false
var _native_enabled := true

func set_native_enabled(value: bool) -> void:
	_native_enabled = value
	_native = null
	_native_ready = false
	_pose_valid = false
	# Configuration owns resolved bind IDs and immutable numeric descriptors.
	# A later configure can enable a class loaded after this instance was made.
	if value and not _sources.is_empty():
		_configure_native()

func get_native_handle() -> RefCounted:
	return _native if _native_ready else null

func _configure_native() -> void:
	_native = null
	_native_ready = false
	if not _native_enabled or not NativeMath.ready() or not ClassDB.class_exists("RabbitLandsCapeBodySurface"):
		return
	var candidate := ClassDB.instantiate("RabbitLandsCapeBodySurface") as RefCounted
	if candidate == null or not candidate.has_method("runtime_info"):
		return
	var info: Dictionary = candidate.call("runtime_info")
	if not bool(info.get("ready", false)) or int(info.get("mounted_cape_body_surface_api", 0)) != 1:
		return
	if bool(info.get("subgrid", false)):
		candidate.call("set_subgrid_enabled", true)
	var descriptors: Array = []
	for source: Dictionary in _sources:
		descriptors.append({"bones": source.bones, "used_binds": source.template.used_binds,
			"surfaces": source.template.surfaces})
	var actor := _actor.get_ref() as Node if _actor != null else null
	var skeleton := instance_from_id(_skeleton_id) as Skeleton3D if actor != null else null
	if skeleton != null and bool(candidate.call("configure_sources", descriptors, skeleton.get_bone_count())):
		_native = candidate

func configure(actor: Node, skeleton: Skeleton3D, profile: String) -> bool:
	var started := Time.get_ticks_usec()
	_sources.clear()
	_clear_grid()
	_vertex_count = 0
	_source_vertex_count = 0
	_cache_hits = 0
	_actor = weakref(actor)
	_profile = profile
	_skeleton_id = skeleton.get_instance_id()
	var meshes := _selected_meshes(actor, profile)
	_signature = _mesh_signature(meshes)
	_refreshes += 1
	_pose_context = []
	_pose_valid = false
	for node: MeshInstance3D in meshes:
		var template := _template(node.mesh, node.skin, skeleton)
		if template.is_empty():
			continue
		var bones := PackedInt32Array()
		var names: PackedStringArray = template.names
		var fallback: PackedInt32Array = template.fallback
		var valid := true
		for i: int in names.size():
			var bone := skeleton.find_bone(names[i]) if not names[i].is_empty() else fallback[i]
			valid = valid and bone >= 0 and bone < skeleton.get_bone_count()
			bones.append(bone)
		if not valid:
			continue
		_sources.append({"node": weakref(node), "template": template, "bones": bones})
		_vertex_count += int(template.vertex_count)
		_source_vertex_count += int(template.source_vertex_count)
	_configure_native()
	_configure_usec = Time.get_ticks_usec() - started
	return _vertex_count > 0

func _selected_meshes(actor: Node, profile: String) -> Array[MeshInstance3D]:
	var candidates: Array[MeshInstance3D] = []
	if profile == "wardrobe":
		var model := actor.get_node_or_null("NativeModel")
		if model != null:
			for value: Node in model.find_children("*", "MeshInstance3D", true, false):
				if str(value.name).begins_with("wardrobe_shirt"):
					candidates.append(value as MeshInstance3D)
	else:
		var equipment: Dictionary = actor.get("_equipment_nodes")
		for value: Variant in equipment.get(5, []):
			if value is MeshInstance3D:
				candidates.append(value as MeshInstance3D)
	var meshes: Array[MeshInstance3D] = []
	for node: MeshInstance3D in candidates:
		if node.is_queued_for_deletion() or not node.is_visible_in_tree() or node.mesh == null \
				or node.has_meta("occlusion_silhouette_clone") \
				or node.mesh is ImmediateMesh or node.mesh is PointMesh:
			continue
		meshes.append(node)
	return meshes

func _mesh_signature(meshes: Array[MeshInstance3D]) -> String:
	var parts := PackedStringArray()
	for node: MeshInstance3D in meshes:
		parts.append("%s:%s:%s" % [node.get_instance_id(), node.mesh.get_instance_id(),
			node.skin.get_instance_id() if node.skin != null else 0])
	return "|".join(parts)

func _template(mesh: Mesh, skin: Skin, skeleton: Skeleton3D) -> Dictionary:
	var key := "%s|%s" % [mesh.get_instance_id(), skin.get_instance_id() if skin != null else 0]
	if _templates.has(key):
		var cached: Dictionary = _templates[key]
		_templates.erase(key)
		_templates[key] = cached
		_cache_hits += 1
		return cached
	var names := PackedStringArray()
	var fallback := PackedInt32Array()
	var binds: Array[Transform3D] = []
	var reference: Array[Transform3D] = []
	var torso_binds := PackedByteArray()
	var shoulder_binds := PackedByteArray()
	if skin != null:
		for i: int in skin.get_bind_count():
			names.append(skin.get_bind_name(i))
			fallback.append(skin.get_bind_bone(i))
			binds.append(skin.get_bind_pose(i))
			var bone := skeleton.find_bone(names[i]) if not names[i].is_empty() else fallback[i]
			if bone < 0 or bone >= skeleton.get_bone_count():return {}
			reference.append(skeleton.get_bone_global_rest(bone) * binds[i])
			var name := str(skeleton.get_bone_name(bone)).to_lower().replace("_", "")
			torso_binds.append(1 if name.begins_with("spine") or name.begins_with("neck") or name.begins_with("clavicle") or name == "pelvis" else 0)
			shoulder_binds.append(1 if "upperarm" in name else 0)
	var surfaces: Array[Dictionary] = []
	var vertex_count := 0
	var source_vertex_count := 0
	var used_binds := {}
	for surface: int in mesh.get_surface_count():
		if mesh is ArrayMesh and (mesh as ArrayMesh).surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
			continue
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		if indices.is_empty():
			for i: int in vertices.size():indices.append(i)
		var starts := PackedInt32Array()
		var slots := PackedInt32Array()
		var points := PackedVector3Array()
		var raw_weights := PackedFloat32Array()
		var unique_vertices := PackedVector3Array()
		var remap := PackedInt32Array()
		var unique := {}
		var reference_points := PackedVector3Array()
		var torso_weights := PackedFloat32Array()
		var shoulder_weights := PackedFloat32Array()
		var bones := PackedInt32Array()
		var weights := PackedFloat32Array()
		var count := 0
		if skin != null:
			if arrays[Mesh.ARRAY_BONES] == null or arrays[Mesh.ARRAY_WEIGHTS] == null:
				return {}
			bones = arrays[Mesh.ARRAY_BONES]
			weights = arrays[Mesh.ARRAY_WEIGHTS]
			count = bones.size() / maxi(1, vertices.size())
			if count not in [4, 8] or weights.size() != bones.size():
				return {}
		for v: int in vertices.size():
			# UV/normal splits do not change a skinned position. Keep distinct
			# influence records distinct; never merge by position alone.
			var signature: Array = [vertices[v]]
			for slot: int in count:
				var at := v * count + slot
				if weights[at] > 0.0:signature.append(bones[at]);signature.append(weights[at])
			if unique.has(signature):
				remap.append(int(unique[signature]))
				continue
			unique[signature] = unique_vertices.size()
			remap.append(unique_vertices.size())
			unique_vertices.append(vertices[v])
			starts.append(slots.size())
			var reference_point := Vector3.ZERO
			var torso_weight := 0.0
			var shoulder_weight := 0.0
			for slot: int in count:
				var at := v * count + slot
				var weight := weights[at]
				if weight <= 0.0:continue
				var bind := bones[at]
				if bind < 0 or bind >= binds.size():return {}
				slots.append(bind)
				points.append((binds[bind] * vertices[v]) * weight)
				raw_weights.append(weight)
				reference_point += (reference[bind] * vertices[v]) * weight
				torso_weight += torso_binds[bind] * weight
				shoulder_weight += shoulder_binds[bind] * weight
			reference_points.append(reference_point)
			torso_weights.append(torso_weight)
			shoulder_weights.append(shoulder_weight)
		starts.append(slots.size())
		var triangles := PackedInt32Array()
		var seen := {}
		for at: int in range(0, indices.size(), 3):
			var a := remap[indices[at]];var b := remap[indices[at + 1]];var c := remap[indices[at + 2]]
			if skin != null:
				var low_y := minf(reference_points[a].y, minf(reference_points[b].y, reference_points[c].y))
				var high_y := maxf(reference_points[a].y, maxf(reference_points[b].y, reference_points[c].y))
				var torso := (torso_weights[a] + torso_weights[b] + torso_weights[c]) / 3.0
				var shoulder := (shoulder_weights[a] + shoulder_weights[b] + shoulder_weights[c]) / 3.0
				if high_y < .9 or low_y > 1.75 or (torso < .35 and not (shoulder >= .35 and high_y >= 1.35)):continue
			var low := mini(a, mini(b, c));var high := maxi(a, maxi(b, c))
			var key_triangle := Vector3i(low, a + b + c - low - high, high)
			if a == b or b == c or a == c or seen.has(key_triangle):continue
			seen[key_triangle] = true
			triangles.append(a);triangles.append(b);triangles.append(c)
		var compact := _compact_surface(unique_vertices, triangles, starts, slots, points, raw_weights)
		surfaces.append(compact)
		for bind: int in compact.slots:used_binds[bind] = true
		vertex_count += (compact.vertices as PackedVector3Array).size()
		source_vertex_count += vertices.size()
	var result := {"mesh": mesh, "skin": skin, "names": names, "fallback": fallback,
		"surfaces": surfaces, "vertex_count": vertex_count, "source_vertex_count": source_vertex_count,
		"used_binds": PackedInt32Array(used_binds.keys())}
	if _templates.size() >= MAX_TEMPLATES:_templates.erase(_templates.keys()[0])
	_templates[key] = result
	return result

func _compact_surface(vertices: PackedVector3Array, triangles: PackedInt32Array,
		starts: PackedInt32Array, slots: PackedInt32Array, points: PackedVector3Array,
		weights: PackedFloat32Array) -> Dictionary:
	var output_vertices := PackedVector3Array();var output_indices := PackedInt32Array()
	var output_starts := PackedInt32Array();var output_slots := PackedInt32Array()
	var output_points := PackedVector3Array();var output_weights := PackedFloat32Array()
	var sums := PackedFloat64Array();var map := {}
	for old: int in triangles:
		if not map.has(old):
			map[old] = output_vertices.size()
			output_vertices.append(vertices[old]);output_starts.append(output_slots.size())
			var sum := 0.0
			for at: int in range(starts[old], starts[old + 1]):
				output_slots.append(slots[at]);output_points.append(points[at]);output_weights.append(weights[at]);sum += weights[at]
			sums.append(sum)
		output_indices.append(int(map[old]))
	output_starts.append(output_slots.size())
	return {"vertices": output_vertices, "indices": output_indices, "starts": output_starts,
		"slots": output_slots, "points": output_points, "weights": output_weights, "sums": sums}

func _clear_grid() -> void:
	_grid.clear()
	_uv.resize(0);_ab.resize(0);_ac.resize(0);_inverse_area.resize(0)
	_heights.resize(0);_normals.resize(0)
	_bounds.clear()

func prepare_pose(skeleton: Skeleton3D, world: Transform3D, spine_skin_frame: Transform3D) -> void:
	var started := Time.get_ticks_usec()
	_pose_cache_hit = false
	_native_ready = false
	var actor := _actor.get_ref() as Node if _actor != null else null
	if actor == null:
		_clear_grid()
		return
	var selected := _selected_meshes(actor, _profile)
	if _skeleton_id != skeleton.get_instance_id() or _signature != _mesh_signature(selected):
		configure(actor, skeleton, _profile)
	_to_world = world * spine_skin_frame
	_from_world = _to_world.affine_inverse()
	_normal_to_world = _to_world.basis.inverse().transposed()
	if _native != null:
		var body_poses: Array[Transform3D] = []
		for bone: int in skeleton.get_bone_count():body_poses.append(skeleton.get_bone_global_pose(bone))
		var rigid_sources: Array[Transform3D] = []
		for source: Dictionary in _sources:
			var node := (source.node as WeakRef).get_ref() as MeshInstance3D
			rigid_sources.append(node.global_transform if node != null else Transform3D.IDENTITY)
		_native_ready = bool(_native.call("prepare_pose", body_poses, world, spine_skin_frame, rigid_sources))
		if _native_ready:
			var native_stats: Dictionary = _native.call("stats")
			_pose_cache_hit = bool(native_stats.get("pose_cache_hit", false))
			_pose_cache_hits = int(native_stats.get("pose_cache_hits", 0))
			_pose_valid = false
			_prepare_usec = Time.get_ticks_usec() - started
			return
	var from_skeleton := spine_skin_frame.affine_inverse()
	var context: Array = [from_skeleton.origin]
	var pose_sets: Array = []
	for source: Dictionary in _sources:
		var bones: PackedInt32Array = source.bones
		var poses: Array[Transform3D] = []
		poses.resize(bones.size())
		for bind: int in source.template.used_binds:
			poses[bind] = from_skeleton * skeleton.get_bone_global_pose(bones[bind])
			context.append(poses[bind])
		if bones.is_empty():
			var node := (source.node as WeakRef).get_ref() as MeshInstance3D
			context.append(_from_world * node.global_transform if node != null else Transform3D.IDENTITY)
		pose_sets.append(poses)
	if _pose_valid and context == _pose_context:
		_pose_cache_hit = true
		_pose_cache_hits += 1
		_prepare_usec = Time.get_ticks_usec() - started
		return
	_pose_context = context
	_clear_grid()
	for source_index: int in _sources.size():
		var source: Dictionary = _sources[source_index]
		var node := (source.node as WeakRef).get_ref() as MeshInstance3D
		if node == null or not node.is_visible_in_tree():continue
		var template: Dictionary = source.template
		var poses: Array[Transform3D] = pose_sets[source_index]
		for surface: Dictionary in template.surfaces:
			var vertices: PackedVector3Array = surface.vertices
			var indices: PackedInt32Array = surface.indices
			var positions := PackedVector3Array()
			positions.resize(vertices.size())
			if poses.is_empty():
				var transform := _from_world * node.global_transform
				for v: int in vertices.size():positions[v] = transform * vertices[v]
			else:
				var starts: PackedInt32Array = surface.starts
				var slots: PackedInt32Array = surface.slots
				var points: PackedVector3Array = surface.points
				var weights: PackedFloat32Array = surface.weights
				var sums: PackedFloat64Array = surface.sums
				for v: int in vertices.size():
					var point := Vector3.ZERO
					for at: int in range(starts[v], starts[v + 1]):
						var pose := poses[slots[at]]
						point += pose.basis * points[at] + pose.origin * weights[at]
					# Composing the inverse frame before a raw-weight blend also
					# weights its translation. Restore that unweighted remainder.
					positions[v] = point + from_skeleton.origin * (1.0 - sums[v])
			for at: int in range(0, indices.size(), 3):
				_add_triangle(positions[indices[at]], positions[indices[at + 1]], positions[indices[at + 2]])
	for candidates: Array in _grid.values():candidates.sort()
	_pose_valid = true
	_prepare_usec = Time.get_ticks_usec() - started

func _add_triangle(a: Vector3, b: Vector3, c: Vector3) -> void:
	var uv := Vector2(a.x, a.y)
	var ab := Vector2(b.x - a.x, b.y - a.y)
	var ac := Vector2(c.x - a.x, c.y - a.y)
	var area := ab.cross(ac)
	if absf(area) < .000000001:return
	var normal := (b - a).cross(c - a).normalized()
	if normal.z > 0.0:normal = -normal
	var index := _uv.size()
	_uv.append(uv);_ab.append(ab);_ac.append(ac);_inverse_area.append(1.0 / area)
	_heights.append(Vector3(a.z, b.z - a.z, c.z - a.z));_normals.append(normal)
	var low := Vector2(minf(a.x, minf(b.x, c.x)), minf(a.y, minf(b.y, c.y)))
	var high := Vector2(maxf(a.x, maxf(b.x, c.x)), maxf(a.y, maxf(b.y, c.y)))
	_bounds.append(Rect2(low - Vector2.ONE * .000001, high - low + Vector2.ONE * .000002))
	var candidate := Vector2(minf(a.z, minf(b.z, c.z)), index)
	for x: int in range(int(floor(low.x / CELL)), int(floor(high.x / CELL)) + 1):
		for y: int in range(int(floor(low.y / CELL)), int(floor(high.y / CELL)) + 1):
			var key := Vector2i(x, y)
			if not _grid.has(key):_grid[key] = []
			(_grid[key] as Array).append(candidate)

func contact(point: Vector3) -> Dictionary:
	if _native_ready:
		var plane: Plane = _native.call("body_plane_at", point)
		return {"covered": plane.normal != Vector3.ZERO, "plane": plane}
	var local := _from_world * point
	var key := Vector2i(int(floor(local.x / CELL)), int(floor(local.y / CELL)))
	if not _grid.has(key):return {"covered": false, "plane": Plane()}
	var uv := Vector2(local.x, local.y)
	var minimum := INF
	var normal := Vector3.ZERO
	var best_index := -1
	for candidate: Vector2 in _grid[key]:
		# Interpolation cannot precede a triangle's minimum vertex height.
		# Keep a tiny tolerance for accepted barycentric boundary roundoff.
		if candidate.x > minimum + .000002:break
		var index := int(candidate.y)
		if not _bounds[index].has_point(uv):continue
		var q := uv - _uv[index]
		var u := q.cross(_ac[index]) * _inverse_area[index]
		var v := _ab[index].cross(q) * _inverse_area[index]
		if u < -.000001 or v < -.000001 or u + v > 1.000001:continue
		var z := _heights[index].x + _heights[index].y * u + _heights[index].z * v
		if z < minimum or (z == minimum and index < best_index):
			minimum = z;normal = _normals[index];best_index = index
	if normal == Vector3.ZERO:return {"covered": false, "plane": Plane()}
	var outward := (_normal_to_world * normal).normalized()
	var surface := _to_world * Vector3(local.x, local.y, minimum) + outward * MARGIN
	return {"covered": true, "plane": Plane(outward, outward.dot(surface))}

func stats() -> Dictionary:
	var native_stats: Dictionary = _native.call("stats") if _native_ready else {}
	return {"meshes": _sources.size(), "vertices": _vertex_count, "triangles": int(native_stats.get("triangles", _uv.size())),
		"source_vertices": _source_vertex_count, "refreshes": _refreshes,
		"configure_usec": _configure_usec, "prepare_usec": _prepare_usec,
		"pose_cache_hit": _pose_cache_hit, "pose_cache_hits": _pose_cache_hits,
		"template_cache_hits": _cache_hits, "template_cache_size": _templates.size(),
		"backend": "native" if _native_ready else "gdscript", "native": native_stats}

extends RefCounted
## Mounted motion uses the approved skin's material coordinates. Contact and
## strain act on that skin, rather than on the old helper-bone pivots.
const Data := preload("res://src/actors/cape_approved_data.gd")
const NativeMath := preload("res://src/actors/cape_native_math.gd")
const COUNT := 12
const FREE := [1, 2, 3, 5, 6, 7, 9, 10, 11]
const EDGE_LIMIT := 1.79
# Residual against an 8 mm posterior guard; 6 mm still leaves 2 mm outside it.
const GAP_LIMIT := .006
const COLD_ITERATIONS := 96
const WARM_ITERATIONS := 96
const DEFENSIVE_CLASP_VERTEX := 946
const DEFENSIVE_HINGE_AXIS := Vector3(.8435855165, -.3599106062, -.3985320965)
const DEFENSIVE_HINGE_DEGREES := 34.0
const BOW_HINGE_DEGREES := 18.0
const MAX_TEMPLATES := 16
const TEMPLATE_FIELDS := [&"_inverse_metric", &"_edge_gains", &"_sample_gains",
	&"_sample_norms", &"_positions", &"_source_positions", &"_weights", &"_active",
	&"_shares", &"_idle_weights", &"_norms", &"_needed", &"_body_points",
	&"_body_weights", &"_body_active", &"_samples", &"_edges", &"_edge_lengths",
	&"_edge_bones", &"_edge_weights", &"_edge_norms", &"_root_weights",
	&"_binds", &"_idle", &"_centres", &"_tips", &"_virtual_sources",
	&"_virtual_factors", &"_virtual_weights", &"_virtual_active", &"_virtual_norms"]
static var _templates: Dictionary = {}
var _inverse_metric: Array[PackedFloat64Array] = []
var _edge_gains: Array[PackedFloat64Array] = []
var _sample_gains: Array[PackedFloat64Array] = []
var _sample_norms := PackedFloat64Array()
var _positions := PackedVector3Array()
var _source_positions := PackedVector3Array()
var _weights: Array[PackedFloat32Array] = []
var _active: Array[PackedInt32Array] = []
var _shares := PackedFloat32Array()
var _idle_weights := PackedVector3Array()
var _norms := PackedFloat32Array()
var _needed := PackedInt32Array()
var _body_points: Array[PackedVector3Array] = []
var _body_weights: Array[PackedFloat32Array] = []
var _body_active: Array[PackedInt32Array] = []
var _samples := PackedInt32Array()
var _edges: Array[Vector2i] = []
var _edge_lengths := PackedFloat32Array()
var _edge_bones: Array[PackedInt32Array] = []
var _edge_weights: Array[PackedFloat32Array] = []
var _edge_norms := PackedFloat32Array()
var _body_bones := PackedInt32Array()
var _root_weights: Array[PackedFloat64Array] = []
var _root_frames: Array[Transform3D] = []
var _root_world := Transform3D.IDENTITY
var _root_reference_normalizers: Array[Transform3D] = []
var _root_neck_fractions := PackedFloat32Array()
var _source_reference_frame := Transform3D.IDENTITY
var _normalized_attachment := false
var _binds: Array[Transform3D] = []
var _idle := PackedVector3Array()
var _centres := PackedVector3Array()
var _tips := PackedVector3Array()
var _world := PackedVector3Array()
var _virtual_sources: Array[Vector3i] = []
var _virtual_factors := PackedVector3Array()
var _virtual_weights: Array[PackedFloat32Array] = []
var _virtual_active: Array[PackedInt32Array] = []
var _virtual_norms := PackedFloat32Array()
var _virtual_world := PackedVector3Array()
var _edge_sample_count := 0
var _last_correction := 0.0
var _last_gap := 0.0
var _last_strain := 1.0
var _profile := ""
var _last_projected := PackedVector3Array()
var _last_basis := Basis.IDENTITY
var _project_usec := 0
var _last_iterations := 0
var _template_cache_hit := false
var _configure_usec := 0
# Presentation state belongs to this helper, never to a cached skin template.
var _actor_ref: WeakRef
var _defensive_weight := 0.0
var _defensive_angle := 0.0
var _defensive_clasp_error := 0.0
var _bow_weight := 0.0
var _bow_angle := 0.0
var _bow_clasp_error := 0.0
# Captured action blends belong to this actor, never to a geometry template.
var _hinge_capture_revision := -1
var _hinge_action: StringName = &""
var _hinge_family := ""
var _hinge_mode := ""
var _hinge_start_angle := 0.0
var _hinge_last_angle := 0.0
var _hinge_clasp_error := 0.0
var _native: RefCounted
var _native_enabled := true
var _native_contacts: Dictionary = {}
var _native_mount := PackedFloat64Array()
var _native_body: RefCounted
var _native_stats: Dictionary = {}

func _clear_configuration() -> void:
	_native = null
	_native_stats.clear()
	_native_contacts.clear()
	_native_mount.clear()
	_native_body = null
	# Array containers stay instance-owned. Packed arrays copy on write, so a
	# later reconfigure cannot mutate an immutable cached template either.
	for field: StringName in TEMPLATE_FIELDS:
		var value: Variant = get(field)
		if value is Array:
			value = value.duplicate()
			value.clear()
		else:
			value.resize(0)
		set(field, value)
	_body_bones = PackedInt32Array()
	_root_frames = []
	_root_world = Transform3D.IDENTITY
	_root_reference_normalizers = []
	_root_neck_fractions = PackedFloat32Array()
	_source_reference_frame = Transform3D.IDENTITY
	_normalized_attachment = false
	_world = PackedVector3Array()
	_virtual_world = PackedVector3Array()
	_edge_sample_count = 0
	_last_projected = PackedVector3Array()
	_last_basis = Basis.IDENTITY
	_last_correction = 0.0
	_last_gap = 0.0
	_last_strain = 1.0
	_project_usec = 0
	_last_iterations = 0
	_template_cache_hit = false
	_configure_usec = 0
	_actor_ref = null
	_defensive_weight = 0.0
	_defensive_angle = 0.0
	_defensive_clasp_error = 0.0
	_bow_weight = 0.0
	_bow_angle = 0.0
	_bow_clasp_error = 0.0
	_clear_corrective_continuity()

func _restore_template(template: Dictionary) -> void:
	_edge_sample_count = int(template.get("edge_sample_count", 0))
	for field: StringName in TEMPLATE_FIELDS:
		var value: Variant = template[field]
		set(field, value.duplicate() if value is Array else value)

func _store_template(key: String, mesh: Mesh, skin: Skin) -> void:
	# Retain resources with the template: its identity stays valid until LRU
	# eviction, including a newly fitted shoulder mesh or attachment Skin.
	var template := {"mesh": mesh, "skin": skin, "edge_sample_count": _edge_sample_count}
	for field: StringName in TEMPLATE_FIELDS:
		var value: Variant = get(field)
		template[field] = value.duplicate() if value is Array else value
	if _templates.size() >= MAX_TEMPLATES:
		_templates.erase(_templates.keys()[0])
	_templates[key] = template

func configure(actor: Node, skeleton: Skeleton3D, profile: String) -> bool:
	var started := Time.get_ticks_usec()
	_clear_configuration()
	_actor_ref = weakref(actor)
	_profile = profile
	_binds = Data.binds(profile)
	_idle = Data.idle(profile)
	if _binds.size() != 17 or _idle.size() != COUNT:
		return false
	_source_reference_frame = skeleton.get_bone_global_rest(
		skeleton.find_bone("spine_03")) * _binds[12]
	var source: Dictionary = Data.catalog().get("fits", {}).get(profile, {})
	var source_surfaces: Array = source.get("surfaces", [])
	var names := Data.bone_names()
	for i: int in range(COUNT, names.size()):
		_body_bones.append(skeleton.find_bone(names[i]))
	_centres.resize(COUNT)
	for chain: int in 3:
		var weights := PackedFloat64Array()
		weights.resize(5)
		_root_weights.append(weights)
	var totals := PackedFloat32Array()
	totals.resize(COUNT)
	var equipment: Dictionary = actor.get("_equipment_nodes")
	var mesh: Mesh = null
	var actual_skin: Skin = null
	for value: Variant in equipment.get(2, []):
		var node := value as MeshInstance3D
		if node != null and node.has_meta("cape_approved_profile"):
			mesh = node.mesh
			actual_skin = node.skin
			break
	if mesh == null or mesh.get_surface_count() != source_surfaces.size():
		return false
	if actual_skin != null and actual_skin.get_bind_count() == 17:
		for i: int in range(COUNT, 17):
			_binds[i] = actual_skin.get_bind_pose(i)
			_body_bones[i - COUNT] = skeleton.find_bone(actual_skin.get_bind_name(i))
	if _body_bones.has(-1):
		return false
	var key := "%s|%s|%s" % [profile, mesh.get_instance_id(),
		actual_skin.get_instance_id() if actual_skin != null else 0]
	if _templates.has(key):
		var template: Dictionary = _templates[key]
		_restore_template(template)
		_templates.erase(key)
		_templates[key] = template
		_template_cache_hit = true
		_configure_attachment_reference(skeleton)
		_configure_native()
		_configure_usec = Time.get_ticks_usec() - started
		return true
	var sample_cells := {}
	var contact_faces: Array[Vector3i] = []
	var contact_factors := PackedVector3Array()
	var contact_edges := {}
	var edge_cells := {}
	var attachment_edges := {}
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var p: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var b: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var w: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var offset := _positions.size()
		var original := Data._vectors3(Data._floats(str(source.get("file", "")),
			source_surfaces[surface].get("positions", {})))
		if original.size() != p.size():
			return false
		_source_positions.append_array(original)
		for v: int in p.size():
			_positions.append(p[v])
			var cape := PackedFloat32Array()
			cape.resize(COUNT)
			var body := PackedVector3Array()
			body.resize(5)
			var bw := PackedFloat32Array()
			bw.resize(5)
			var share := 0.0
			for slot: int in 8:
				var bone := b[v * 8 + slot]
				var weight := w[v * 8 + slot]
				if bone < COUNT:
					cape[bone] += weight
					share += weight
					_centres[bone] += p[v] * weight
					totals[bone] += weight
				elif bone < 17:
					body[bone - COUNT] += (_binds[bone] * p[v]) * weight
					bw[bone - COUNT] += weight
			_weights.append(cape)
			var active := PackedInt32Array()
			var idle := Vector3.ZERO
			var norm := 0.0
			for bone: int in COUNT:
				if cape[bone] > 0.0:
					active.append(bone)
					idle += _idle[bone] * cape[bone]
					if bone in FREE:
						norm += cape[bone] * cape[bone]
			_active.append(active)
			_shares.append(share)
			_idle_weights.append(idle)
			_norms.append(norm)
			_body_points.append(body)
			_body_weights.append(bw)
			var body_active := PackedInt32Array()
			for bone: int in 5:
				if bw[bone] > 0.0:
					body_active.append(bone)
			_body_active.append(body_active)
			for chain: int in 3:
				for bone: int in 5:
					_root_weights[chain][bone] += cape[chain * 4] * bw[bone]
			if share < 0.1:
				continue
			# Preserve both sides of folds in each material cell. Rendering still
			# uses every original vertex and its unchanged eight skin weights.
			var cell := Vector2i(int(floor(p[v].x / 0.045)), int(floor(p[v].y / 0.045)))
			var pair: Vector2i = sample_cells.get(cell, Vector2i(-1, -1))
			var id := offset + v
			if pair.x < 0 or p[v].z < _positions[pair.x].z:
				pair.x = id
			if pair.y < 0 or p[v].z > _positions[pair.y].z:
				pair.y = id
			sample_cells[cell] = pair
		for at: int in range(0, indices.size(), 3):
			var face := Vector3i(offset + indices[at], offset + indices[at + 1], offset + indices[at + 2])
			# A lower panel can rise into the rider during a release or turn.
			# Rest height is therefore not a valid collision coverage filter.
			contact_faces.append(face)
			contact_factors.append(Vector3.ONE / 3.0)
			for side: int in 3:
				var a := offset + indices[at + side]
				var z := offset + indices[at + (side + 1) % 3]
				var length := _source_positions[a].distance_to(_source_positions[z])
				if length < 0.005:
					continue
				var contact_edge := Vector2i(mini(a, z), maxi(a, z))
				if length > .06 and not contact_edges.has(contact_edge):
					# Long skinned edges can cross the torso between their
					# vertices and face centroid. Keep exact rendered-edge
					# samples, rather than separately skinning a rest average.
					contact_faces.append(Vector3i(a, a, z))
					contact_factors.append(Vector3.ONE / 3.0)
					contact_faces.append(Vector3i(a, z, z))
					contact_factors.append(Vector3.ONE / 3.0)
					if length > .12:
						for fraction: float in [.25, .5, .75]:
							contact_faces.append(Vector3i(a, z, z))
							contact_factors.append(Vector3(1.0 - fraction, fraction, 0.0))
					contact_edges[contact_edge] = true
				var centre := (_positions[a] + _positions[z]) * 0.5
				var cell := Vector3i(int(floor(centre.x / .045)), int(floor(centre.y / .045)), side)
				var gradient := 0.0
				for bone: int in FREE:
					gradient += pow(_weights[a][bone] - _weights[z][bone], 2)
				gradient /= length * length
				# A lower row can enter the torso during an upper-body action.
				# Enforce movable source edges throughout the panel, including
				# holdouts outside the sparse certificate's search contexts.
				if gradient > .00001:
					attachment_edges[Vector2i(mini(a, z), maxi(a, z))] = true
				var previous: Dictionary = edge_cells.get(cell, {})
				if gradient > float(previous.get("gradient", -1.0)):
					edge_cells[cell] = {"edge": Vector2i(a, z), "gradient": gradient}
	for value: Vector2i in sample_cells.values():
		_samples.append(value.x)
		if value.y != value.x:
			_samples.append(value.y)
	var support: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/cape_motion/mounted-support-edges.json"))
	if not support is Dictionary or int(support.get("schema_version", 0)) != 1:
		return false
	var certificate: Dictionary = support.get("profiles", {}).get(profile, {})
	var digest := HashingContext.new()
	digest.start(HashingContext.HASH_SHA256)
	digest.update(Data._bytes(str(source.get("file", ""))))
	if int(certificate.get("vertex_count", 0)) != _positions.size() \
			or str(certificate.get("fit_sha256", "")) != str(source.get("sha256", "")) \
			or digest.finish().hex_encode() != str(source.get("sha256", "")):
		return false
	var edges: Array = certificate.get("edges", [])
	if edges.is_empty():
		return false
	edge_cells.clear()
	for i: int in edges.size():
		var pair: Variant = edges[i]
		if not pair is Array or pair.size() != 2:
			return false
		var edge := Vector2i(int(pair[0]), int(pair[1]))
		if edge.x < 0 or edge.y < 0 or edge.x >= _positions.size() or edge.y >= _positions.size() \
				or _source_positions[edge.x].distance_to(_source_positions[edge.y]) < .000001:
			return false
		edge_cells[i] = {"edge": edge}
	var seen := {}
	for value: Dictionary in edge_cells.values():
		var edge: Vector2i = value.edge
		seen[Vector2i(mini(edge.x, edge.y), maxi(edge.x, edge.y))] = true
	for edge: Vector2i in attachment_edges:
		if not seen.has(edge):
			edge_cells[edge] = {"edge": edge}
	var needed := {}
	for index: int in _samples:
		needed[index] = true
	# A triangle can cut through clothing with every corner outside it.
	# These samples are exact barycentric averages of the rendered skin, not
	# a separately skinned average position (which would lose W*p terms).
	for at: int in contact_faces.size():
		var face := contact_faces[at]
		var factors := contact_factors[at]
		var weights := PackedFloat32Array()
		weights.resize(COUNT)
		var active := PackedInt32Array()
		var norm := 0.0
		for bone: int in COUNT:
			if factors == Vector3.ONE / 3.0:
				weights[bone] = (_weights[face.x][bone] + _weights[face.y][bone] + _weights[face.z][bone]) / 3.0
			else:
				weights[bone] = _weights[face.x][bone] * factors.x + _weights[face.y][bone] * factors.y + _weights[face.z][bone] * factors.z
			if weights[bone] > 0.0:
				active.append(bone)
			if bone in FREE:
				norm += weights[bone] * weights[bone]
		if norm < .02:
			continue
		_virtual_sources.append(face)
		_virtual_factors.append(factors)
		if face.x == face.y or face.y == face.z or face.x == face.z:
			_edge_sample_count += 1
		_virtual_weights.append(weights)
		_virtual_active.append(active)
		_virtual_norms.append(norm)
		_samples.append(-_virtual_sources.size())
		needed[face.x] = true
		needed[face.y] = true
		needed[face.z] = true
	for value: Dictionary in edge_cells.values():
		var edge: Vector2i = value.edge
		_edges.append(edge)
		_edge_lengths.append(_source_positions[edge.x].distance_to(_source_positions[edge.y]))
		needed[edge.x] = true
		needed[edge.y] = true
		var bones := PackedInt32Array()
		var weights := PackedFloat32Array()
		var norm := 0.0
		for bone: int in COUNT:
			var weight := _weights[edge.x][bone] - _weights[edge.y][bone]
			if absf(weight) > 0.0000001:
				bones.append(bone)
				weights.append(weight)
				norm += weight * weight
		_edge_bones.append(bones)
		_edge_weights.append(weights)
		_edge_norms.append(norm)
	_needed = PackedInt32Array(needed.keys())
	_build_metric()
	for at: int in _edges.size():
		var edge := _edges[at]
		var row := PackedFloat64Array()
		for bone: int in FREE:
			row.append(_weights[edge.x][bone] - _weights[edge.y][bone])
		var gain := _gain(row)
		_edge_gains.append(gain)
		_edge_norms[at] = _dot(row, gain)
	for index: int in _samples:
		var row := PackedFloat64Array()
		var weights := _contact_weights(index)
		for bone: int in FREE:
			row.append(weights[bone])
		var gain := _gain(row)
		_sample_gains.append(gain)
		_sample_norms.append(_dot(row, gain))
	for i: int in COUNT:
		_centres[i] /= maxf(totals[i], 0.000001)
	for chain: int in 3:
		var total := 0.0
		for weight: float in _root_weights[chain]:
			total += weight
		if total <= .000001:
			_root_weights[chain][0] = 1.0
		else:
			for bone: int in 5:
				_root_weights[chain][bone] /= total
	for chain: int in 3:
		var last := _centres[chain * 4 + 3]
		var low := last.y
		for v: int in _positions.size():
			if _weights[v][chain * 4 + 3] > 0.25:
				low = minf(low, _positions[v].y)
		_tips.append(Vector3(last.x, low, last.z))
	if _samples.is_empty():
		return false
	_configure_attachment_reference(skeleton)
	_configure_native()
	_store_template(key, mesh, actual_skin)
	_configure_usec = Time.get_ticks_usec() - started
	return true

func _dot(a: PackedFloat64Array, b: PackedFloat64Array) -> float:
	var out := 0.0
	for i: int in a.size():
		out += a[i] * b[i]
	return out

func _gain(row: PackedFloat64Array) -> PackedFloat64Array:
	var result := PackedFloat64Array()
	for values: PackedFloat64Array in _inverse_metric:
		result.append(_dot(values, row))
	return result

func _build_metric() -> void:
	var count := FREE.size()
	var rows: Array[PackedFloat64Array] = []
	for i: int in count:
		var row := PackedFloat64Array()
		row.resize(count * 2)
		row[i + count] = 1.0
		row[i] = .00001
		rows.append(row)
	for weights: PackedFloat32Array in _weights:
		for i: int in count:
			for j: int in count:
				rows[i][j] += weights[FREE[i]] * weights[FREE[j]] / float(_weights.size())
	for i: int in count:
		var pivot := rows[i][i]
		for j: int in count * 2:
			rows[i][j] /= pivot
		for other: int in count:
			if other == i:
				continue
			var factor := rows[other][i]
			for j: int in count * 2:
				rows[other][j] -= factor * rows[i][j]
	for row: PackedFloat64Array in rows:
		_inverse_metric.append(row.slice(count, count * 2))

func material_line(frame: Transform3D, chain: int) -> PackedVector3Array:
	var line := PackedVector3Array()
	for link: int in 4:
		var i := chain * 4 + link
		if link == 0 and _root_frames.size() == 3:
			line.append(_root_world * _root_frames[chain] * (_centres[i] + _idle[i]))
		else:
			line.append(frame * (_centres[i] + _idle[i]))
	line.append(frame * (_tips[chain] + _idle[chain * 4 + 3]))
	return line

func posed_material_line(skeleton: Skeleton3D, world: Transform3D,
		chain: int, bones: PackedInt32Array) -> PackedVector3Array:
	# The simulation controls material centroids, not the imported helper
	# pivots. Recover those same controls from the currently displayed palette.
	var line := PackedVector3Array()
	for link: int in 4:
		var i := chain * 4 + link
		line.append(world * skeleton.get_bone_global_pose(bones[link]) *
			_binds[i] * _centres[i])
	var last := chain * 4 + 3
	line.append(world * skeleton.get_bone_global_pose(bones[3]) *
		_binds[last] * _tips[chain])
	return line

func shape_frame(frame: Transform3D, surface: RefCounted) -> Transform3D:
	# Turn the free sheet about its shoulder line as one piece before adding
	# differential row motion. A rigid turn preserves its material edges.
	var angle := deg_to_rad((12.0 if _profile == "armour" else 18.0) + 4.0 * float(surface.get("moving_blend")) + (4.0 if _profile == "armour" else 6.0) * float(surface.get("gallop_blend")))
	var rotation := Basis(Vector3.RIGHT, angle)
	var shoulder := Vector3(0.0, 1.545, -.165 if _profile == "armour" else -.13)
	return frame * Transform3D(rotation, shoulder - rotation * shoulder)

func bone_pose(frame: Transform3D, index: int) -> Transform3D:
	var skin_frame := _root_frames[index / 4] if index % 4 == 0 and _root_frames.size() == 3 else frame
	return skin_frame * Transform3D(Basis.IDENTITY, _idle[index]) * _binds[index].affine_inverse()

func _blend_attachment_frame(spine: Transform3D, neck: Transform3D,
		fraction: float, centre: Vector3) -> Transform3D:
	var a := spine.basis.orthonormalized().get_rotation_quaternion()
	var b := neck.basis.orthonormalized().get_rotation_quaternion()
	if a.dot(b) < 0.0:
		b = -b
	var rotation := Quaternion(lerpf(a.x, b.x, fraction), lerpf(a.y, b.y, fraction),
		lerpf(a.z, b.z, fraction), lerpf(a.w, b.w, fraction)).normalized()
	var basis := Basis(rotation)
	var target := (spine * centre).lerp(neck * centre, fraction)
	return Transform3D(basis, target - basis * centre)

func _configure_attachment_reference(skeleton: Skeleton3D) -> void:
	_root_reference_normalizers.clear()
	_root_neck_fractions.clear()
	_normalized_attachment = _body_bones.size() == 5 \
		and skeleton.get_bone_name(_body_bones[0]) == "spine_03"
	for i: int in range(1, _body_bones.size()):
		_normalized_attachment = _normalized_attachment \
			and skeleton.get_bone_name(_body_bones[i]) == "neck_01"
	if not _normalized_attachment:
		return
	var spine := skeleton.get_bone_global_rest(_body_bones[0]) * _binds[12]
	var neck := skeleton.get_bone_global_rest(_body_bones[1]) * _binds[13]
	for chain: int in 3:
		var fraction := .5
		# Share anatomical support across the yoke. A spine-only centre
		# shears against the neck-supported sides during a bow release.
		_root_neck_fractions.append(fraction)
		var centre := _centres[chain * 4] + _idle[chain * 4]
		var canonical := _blend_attachment_frame(spine, neck, fraction, centre)
		_root_reference_normalizers.append(canonical.affine_inverse() * _source_reference_frame)

## Only three anatomical root frames: no skin samples or contact projection.
## The mounted static-budget hold can call this after posing the body.
func prepare_attachment(skeleton: Skeleton3D, world: Transform3D,
		source_frame: Transform3D) -> void:
	_prepare_attachment_frames(skeleton, world, source_frame)
	var hinge_frame := _root_frames[0] if _root_frames.size() == 3 else Transform3D.IDENTITY
	_apply_defensive_corrective()
	_apply_bow_corrective()
	_apply_corrective_continuity(hinge_frame)

func _prepare_attachment_frames(skeleton: Skeleton3D, world: Transform3D,
		source_frame: Transform3D) -> void:
	_root_world = world
	_root_frames.clear()
	var bodies: Array[Transform3D] = []
	for i: int in 5:
		bodies.append(skeleton.get_bone_global_pose(_body_bones[i]) * _binds[COUNT + i])
	if _normalized_attachment:
		for chain: int in 3:
			var centre := _centres[chain * 4] + _idle[chain * 4]
			var current := _blend_attachment_frame(bodies[0], bodies[1],
				_root_neck_fractions[chain], centre)
			_root_frames.append(current * _root_reference_normalizers[chain])
		return
	# The mounted attachment aliases all five body slots to one torso frame.
	# Its three cape roots share that exact frame and are never simulated.
	if _body_bones.count(_body_bones[0]) == 5:
		for chain: int in 3:
			_root_frames.append(bodies[0])
		return
	var reference := source_frame.basis.orthonormalized().get_rotation_quaternion()
	for chain: int in 3:
		var centre := _centres[chain * 4] + _idle[chain * 4]
		var target := Vector3.ZERO
		var rotation := Quaternion(0, 0, 0, 0)
		for i: int in 5:
			var weight := _root_weights[chain][i]
			target += (bodies[i] * centre) * weight
			var quaternion := bodies[i].basis.orthonormalized().get_rotation_quaternion()
			if quaternion.dot(reference) < 0.0:
				quaternion = -quaternion
			rotation.x += quaternion.x * weight
			rotation.y += quaternion.y * weight
			rotation.z += quaternion.z * weight
			rotation.w += quaternion.w * weight
		var basis := Basis(rotation.normalized())
		_root_frames.append(Transform3D(basis, target - basis * centre))

static func defensive_corrective_recipe() -> Dictionary:
	return {"profile": "wardrobe", "upper_action": "cast_defensive", "chain": 0,
		"pivot_surface": 0, "pivot_vertex": DEFENSIVE_CLASP_VERTEX,
		"pivot_coordinates": "mounted rest vertex plus C0 idle, before current root frame",
		"axis_c0_local": DEFENSIVE_HINGE_AXIS,
		"full_angle_degrees": DEFENSIVE_HINGE_DEGREES,
		"weight": "actual MountedUpperBody.weight, including entry and return",
		"unchanged": "body65, body attachment palettes, other roots, armour and other steady action targets; direct interrupted entry/return carries the captured outgoing hinge",
		"lower_controls": "nine existing free controls retain contact and source-edge projection"}

func _apply_defensive_corrective() -> void:
	_defensive_weight = 0.0
	_defensive_angle = 0.0
	_defensive_clasp_error = 0.0
	if _profile != "wardrobe" or not _normalized_attachment \
			or _root_frames.size() != 3 or _positions.size() <= DEFENSIVE_CLASP_VERTEX \
			or _actor_ref == null:
		return
	var actor := _actor_ref.get_ref() as Node
	if not is_instance_valid(actor):
		return
	var visual := actor.get("_mount_visual") as Node
	if not is_instance_valid(visual):
		return
	var upper := visual.get("upper") as RefCounted
	if upper == null or upper.get("action") != &"cast_defensive":
		return
	var weight := float(upper.get("weight"))
	if not is_finite(weight):
		return
	_defensive_weight = clampf(weight, 0.0, 1.0)
	_defensive_angle = deg_to_rad(DEFENSIVE_HINGE_DEGREES) * _defensive_weight
	if _defensive_angle <= 0.0:
		return
	var frame := _root_frames[0]
	# Turn about the clasp's C0 contribution. Its body-owned contribution and
	# this pivot stay fixed, so the actual eight-weight clasp also stays fixed.
	var pivot_local := _positions[DEFENSIVE_CLASP_VERTEX] + _idle[0]
	var pivot := frame * pivot_local
	var axis := (frame.basis * DEFENSIVE_HINGE_AXIS).normalized()
	var turn := Basis(axis, _defensive_angle)
	_root_frames[0] = Transform3D(turn, pivot - turn * pivot) * frame
	_defensive_clasp_error = pivot.distance_to(_root_frames[0] * pivot_local)

func prepare_pose(skeleton: Skeleton3D, world: Transform3D, source_frame: Transform3D) -> void:
	prepare_attachment(skeleton, world, source_frame)

func _apply_bow_corrective() -> void:
	_bow_weight = 0.0
	_bow_angle = 0.0
	_bow_clasp_error = 0.0
	if _profile != "wardrobe" or not _normalized_attachment \
			or _root_frames.size() != 3 or _positions.size() <= DEFENSIVE_CLASP_VERTEX:
		return
	var actor := _actor_ref.get_ref() as Node if _actor_ref != null else null
	if actor == null:
		return
	var visual := actor.get("_mount_visual") as Node
	var upper: RefCounted = visual.get("upper") as RefCounted if visual != null else null
	if upper == null or upper.get("action") not in [&"ranged_draw", &"ranged_hold", &"ranged_attack"]:
		return
	# Grip remains continuous when the draw clip changes to its hold clip,
	# and fades during return. The clasp itself remains the rotation pivot.
	var weight := float(upper.get("grip_weight"))
	if not is_finite(weight):
		return
	_bow_weight = clampf(weight, 0.0, 1.0)
	_bow_angle = deg_to_rad(BOW_HINGE_DEGREES) * _bow_weight
	if _bow_angle <= 0.0:
		return
	var frame := _root_frames[0]
	var pivot_local := _positions[DEFENSIVE_CLASP_VERTEX] + _idle[0]
	var pivot := frame * pivot_local
	var axis := (frame.basis * DEFENSIVE_HINGE_AXIS).normalized()
	var turn := Basis(axis, _bow_angle)
	_root_frames[0] = Transform3D(turn, pivot - turn * pivot) * frame
	_bow_clasp_error = pivot.distance_to(_root_frames[0] * pivot_local)

func _clear_corrective_continuity() -> void:
	_hinge_capture_revision = -1
	_hinge_action = &""
	_hinge_family = ""
	_hinge_mode = ""
	_hinge_start_angle = 0.0
	_hinge_last_angle = 0.0
	_hinge_clasp_error = 0.0

func _apply_corrective_continuity(reference: Transform3D) -> void:
	var base_angle := _defensive_angle + _bow_angle
	_hinge_clasp_error = maxf(_defensive_clasp_error, _bow_clasp_error)
	if _profile != "wardrobe" or not _normalized_attachment or _root_frames.size() != 3 \
			or _positions.size() <= DEFENSIVE_CLASP_VERTEX:
		_clear_corrective_continuity()
		return
	var actor := _actor_ref.get_ref() as Node if _actor_ref != null else null
	var visual := actor.get("_mount_visual") as Node if actor != null else null
	var upper := visual.get("upper") as RefCounted if visual != null else null
	if upper == null:
		_clear_corrective_continuity()
		return
	var revision_value: Variant = upper.get("_capture_revision")
	if not revision_value is int:
		# Standalone replay fixtures have no presentation history to carry.
		_hinge_last_angle = base_angle
		return
	var revision := int(revision_value)
	var action := StringName(upper.get("action"))
	var returning := bool(upper.get("_returning"))
	var family := "bow" if action in [&"ranged_draw", &"ranged_hold", &"ranged_attack"] \
		else ("defensive" if action == &"cast_defensive" else "other")
	var weight := float(upper.get("weight"))
	if not is_finite(weight):
		_clear_corrective_continuity()
		return
	weight = clampf(weight, 0.0, 1.0)
	if action.is_empty():
		_hinge_mode = ""
		_hinge_start_angle = 0.0
	elif revision != _hinge_capture_revision and _hinge_capture_revision >= 0:
		_hinge_start_angle = _hinge_last_angle
		if returning:
			# The body returns from the captured pose, including a partial entry.
			# Fade that one captured angle, rather than applying entry twice.
			_hinge_mode = "return"
		elif not _hinge_action.is_empty() and not (family == "bow" \
				and _hinge_family == "bow" and _hinge_mode.is_empty()):
			_hinge_mode = "entry"
		else:
			_hinge_mode = ""
	var angle := base_angle
	if _hinge_mode == "return":
		angle = _hinge_start_angle * weight
	elif _hinge_mode == "entry":
		# Defensive's ordinary target already includes entry weight. Bow grip
		# can remain one across a direct action change, so weight its incoming
		# target only here. Ordinary draw/hold/release still uses grip exactly.
		var target := deg_to_rad(DEFENSIVE_HINGE_DEGREES) if family == "defensive" else _bow_angle
		angle = lerpf(_hinge_start_angle, target, weight)
		if weight >= 1.0:
			_hinge_mode = ""
	if absf(angle - base_angle) > .000000001:
		var pivot_local := _positions[DEFENSIVE_CLASP_VERTEX] + _idle[0]
		var pivot := reference * pivot_local
		var axis := (reference.basis * DEFENSIVE_HINGE_AXIS).normalized()
		var turn := Basis(axis, angle)
		_root_frames[0] = Transform3D(turn, pivot - turn * pivot) * reference
		_hinge_clasp_error = pivot.distance_to(_root_frames[0] * pivot_local)
	_hinge_capture_revision = revision
	_hinge_action = action
	_hinge_family = family
	_hinge_last_angle = angle

func lengths(chain: int) -> PackedFloat32Array:
	var line := PackedVector3Array()
	for link: int in 4:
		var i := chain * 4 + link
		line.append(_centres[i] + _idle[i])
	line.append(_tips[chain] + _idle[chain * 4 + 3])
	var out := PackedFloat32Array()
	for link: int in 4:
		out.append(maxf(.02, line[link].distance_to(line[link + 1])))
	return out

func idle_offset(index: int) -> Vector3:
	return _idle[index]

func _point(index: int, translations: PackedVector3Array) -> Vector3:
	if index < 0:
		var sample_id := -index - 1
		var point := _virtual_world[sample_id]
		for bone: int in _virtual_active[sample_id]:
			point += translations[bone] * _virtual_weights[sample_id][bone]
		return point
	var out := _world[index]
	for bone: int in _active[index]:
		out += translations[bone] * _weights[index][bone]
	return out

func _contact_weights(index: int) -> PackedFloat32Array:
	return _virtual_weights[-index - 1] if index < 0 else _weights[index]

func _contact_norm(index: int) -> float:
	return _virtual_norms[-index - 1] if index < 0 else _norms[index]

func project(skeleton: Skeleton3D, world: Transform3D, frame: Transform3D,
		translations: PackedVector3Array, contact: Callable, plane_contact: Callable) -> PackedVector3Array:
	var started := Time.get_ticks_usec()
	if _native != null and _native_enabled and not _native_contacts.is_empty():
		var bodies: Array[Transform3D] = []
		for bone: int in _body_bones:
			bodies.append(skeleton.get_bone_global_pose(bone))
		var result: Dictionary = _native.call("project", world, frame,
			_root_frames, bodies, translations, _native_contacts, _native_mount,
			_native_body, false)
		if result.get("ok", false):
			var projected: PackedVector3Array = result["translations"]
			_native_stats = result["stats"]
			_last_gap = float(_native_stats.get("gap_m", 0.0))
			_last_strain = float(_native_stats.get("strain", 1.0))
			_last_correction = float(_native_stats.get("correction_m", 0.0))
			_last_iterations = int(_native_stats.get("iterations", 0))
			_last_projected = projected.duplicate()
			_last_basis = world.basis * frame.basis
			_project_usec = Time.get_ticks_usec() - started
			return projected
		# A rejected numeric batch must never publish a partial pose. Continue
		# through the complete script solver using its last accepted history.
		_native_stats = {"error": result.get("error", "rejected")}
		_native = null
	elif _native != null:
		# A missing numeric contact packet uses the complete script solver.
		# Its accepted history then supersedes the native solver's prior frame.
		# Resume natively from current particles with a cold projection instead
		# of carrying a stale pose across the fallback interval.
		_native.call("reset")
	var material_scale := world.basis.x.length()
	translations = translations.duplicate()
	for chain: int in 3:
		translations[chain * 4] = Vector3.ZERO
	var cold := _last_projected.size() != COUNT
	var basis := world.basis * frame.basis
	if not cold:
		var carry := basis * _last_basis.inverse()
		for bone: int in FREE:
			translations[bone] = (carry * _last_projected[bone]).lerp(translations[bone], .35)
	# Round the transition from the back into the sheet resting on the rump.
	# Contact and material-edge constraints have final authority afterward.
	var rigid := world * frame
	for chain: int in 3:
		var centreline := PackedVector3Array()
		for link: int in 4:
			var bone := chain * 4 + link
			var base := world * _root_frames[chain] if link == 0 else rigid
			centreline.append(base * (_centres[bone] + _idle[bone]) + translations[bone])
		var spans := lengths(chain)
		for link: int in range(1, 3):
			var fraction := spans[link - 1] / (spans[link - 1] + spans[link])
			var target := centreline[link - 1].lerp(centreline[link + 1], fraction)
			translations[chain * 4 + link] += ((target - centreline[link]) * .12).limit_length(.02)
	_world.resize(_positions.size())
	var bodies: Array[Transform3D] = []
	for bone: int in _body_bones:
		bodies.append(skeleton.get_bone_global_pose(bone))
	for index: int in _needed:
		var upper_share := 0.0
		var upper_idle := Vector3.ZERO
		var upper := Vector3.ZERO
		for chain: int in 3:
			var i := chain * 4
			var weight := _weights[index][i]
			upper_share += weight
			upper_idle += _idle[i] * weight
			upper += (_root_frames[chain] * (_positions[index] + _idle[i])) * weight
		var base := frame * _positions[index] * (_shares[index] - upper_share) + frame.basis * (_idle_weights[index] - upper_idle) + upper
		for bone: int in _body_active[index]:
			base += bodies[bone].basis * _body_points[index][bone] + bodies[bone].origin * _body_weights[index][bone]
		_world[index] = world * base
	_virtual_world.resize(_virtual_sources.size())
	for at: int in _virtual_sources.size():
		var face := _virtual_sources[at]
		var factors := _virtual_factors[at]
		if factors == Vector3.ONE / 3.0:
			_virtual_world[at] = (_world[face.x] + _world[face.y] + _world[face.z]) / 3.0
		else:
			_virtual_world[at] = _world[face.x] * factors.x + _world[face.y] * factors.y + _world[face.z] * factors.z
	_last_correction = 0.0
	_last_gap = 0.0
	var edge_dual := PackedVector3Array()
	edge_dual.resize(_edges.size())
	var normals := PackedVector3Array()
	normals.resize(_samples.size())
	var planes := PackedFloat64Array()
	planes.resize(_samples.size())
	var multipliers := PackedFloat64Array()
	multipliers.resize(_samples.size())
	for at: int in _samples.size():
		var index := _samples[at]
		if _contact_norm(index) < .02:
			continue
		var plane: Plane = plane_contact.call(_point(index, translations))
		normals[at] = plane.normal
		planes[at] = plane.d
	for iteration: int in (COLD_ITERATIONS if cold else WARM_ITERATIONS):
		_last_iterations = iteration + 1
		# The material edges couple neighbouring controls before contact. This
		# limits the steep row changes that otherwise appear as isolated spikes.
		for at: int in _edges.size():
			var edge := _edges[at]
			var delta := _world[edge.x] - _world[edge.y]
			var bones := _edge_bones[at]
			var weights := _edge_weights[at]
			for slot: int in bones.size():
				delta += translations[bones[slot]] * weights[slot]
			var norm := _edge_norms[at]
			delta += edge_dual[at] * norm
			var length := delta.length()
			var maximum := _edge_lengths[at] * material_scale * EDGE_LIMIT
			if norm < 0.0000001:
				continue
			var dual := delta * (maxf(0.0, length - maximum) / maxf(length, .000001) / norm)
			var change := edge_dual[at] - dual
			var gains := _edge_gains[at]
			if change.length_squared() > 0.000000000001:
				for slot: int in FREE.size():
					translations[FREE[slot]] += change * gains[slot]
			edge_dual[at] = dual
		for at: int in _samples.size():
			var index := _samples[at]
			var norm := _sample_norms[at]
			if norm < .0001 or _contact_norm(index) < .02:
				continue
			var point := _point(index, translations)
			if normals[at] == Vector3.ZERO:
				continue
			var distance := planes[at] - point.dot(normals[at])
			var multiplier := maxf(0.0, multipliers[at] + distance / norm)
			var change := normals[at] * (multiplier - multipliers[at])
			var gains := _sample_gains[at]
			if change.length_squared() > 0.000000000001:
				for slot: int in FREE.size():
					var move := change * gains[slot]
					translations[FREE[slot]] += move
					_last_correction = maxf(_last_correction, move.length())
			multipliers[at] = multiplier
		if iteration % 2 == 0:
			continue
		_last_gap = 0.0
		for at: int in _samples.size():
			var index := _samples[at]
			if _contact_norm(index) >= .02:
				var point := _point(index, translations)
				var plane: Plane = plane_contact.call(point)
				var projected := point - plane.normal * minf(0.0, plane.distance_to(point))
				_last_gap = maxf(_last_gap, point.distance_to(projected))
				# Material correction can create a contact that was absent at
				# the target pose. Do not leave that sample inactive all frame.
				if plane.normal != Vector3.ZERO and (normals[at] == Vector3.ZERO or (
						multipliers[at] == 0.0 and point.dot(normals[at]) >= planes[at]
						and plane.distance_to(point) < -GAP_LIMIT)):
					# An inactive clear plane has no stored dual correction. Let
					# the next sweep respond to the current body surface instead.
					normals[at] = plane.normal
					planes[at] = plane.d
		_last_strain = 1.0
		for at: int in _edges.size():
			var edge := _edges[at]
			_last_strain = maxf(_last_strain, _point(edge.x, translations).distance_to(_point(edge.y, translations)) / (_edge_lengths[at] * material_scale))
		if _last_gap < GAP_LIMIT and _last_strain < EDGE_LIMIT + .005:
			break
	_last_projected = translations.duplicate()
	_last_basis = basis
	_project_usec = Time.get_ticks_usec() - started
	return translations

func reset() -> void:
	_last_projected.clear()
	if _native != null:
		_native.call("reset")

func _configure_native() -> void:
	if not _native_enabled or not NativeMath.ready():
		return
	var candidate := ClassDB.instantiate("RabbitLandsCapeProjector") as RefCounted
	if candidate == null:
		return
	# Older API2 payloads only understand centroid samples. Their complete
	# script fallback remains correct for the nonuniform edge factors.
	var capabilities: Dictionary = candidate.call("runtime_info")
	if not bool(capabilities.get("virtual_factors", false)):
		return
	var template := {}
	for field: StringName in TEMPLATE_FIELDS:
		template[field] = get(field)
	template["solver"] = {"edge_limit": EDGE_LIMIT, "gap_limit_m": GAP_LIMIT,
		"cold_iterations": COLD_ITERATIONS, "warm_iterations": WARM_ITERATIONS,
		"strain_tolerance": .005, "activate_contacts": true, "covered_clear": true,
		"exact_memo": true, "trusted_body": true, "parallel_contacts": true,
		"parallel_residuals": bool(capabilities.get("parallel_residuals", false)),
		"refresh_clear_contacts": bool(capabilities.get("refresh_clear_contacts", false))}
	# A stale arithmetic payload cannot implement the current contact policy.
	if not bool(capabilities.get("refresh_clear_contacts", false)):
		return
	if bool(candidate.call("configure", template)):
		_native = candidate

func set_native_enabled(enabled: bool) -> void:
	_native_enabled = enabled
	reset()
	_native = null
	if enabled and not _positions.is_empty():
		_configure_native()

func set_native_contacts(collisions: Dictionary, mount: PackedFloat64Array,
		body_surface: RefCounted) -> void:
	_native_contacts = collisions
	_native_mount = mount
	_native_body = body_surface

func stats() -> Dictionary:
	return {"samples": _samples.size(), "edges": _edges.size(),
		"edge_limit": EDGE_LIMIT, "gap_limit_m": GAP_LIMIT,
		"native_projector": _native != null and _native_enabled,
		"native_stats": _native_stats,
		"triangle_interior_samples": _virtual_sources.size(),
		"edge_interior_samples": _edge_sample_count,
		"gap_m": _last_gap, "correction_m": _last_correction, "strain": _last_strain,
		"project_usec": _project_usec, "iterations": _last_iterations, "root_body_weights": _root_weights,
		"normalized_attachment": _normalized_attachment,
		"root_neck_fractions": _root_neck_fractions,
		"defensive_corrective_weight": _defensive_weight,
		"defensive_corrective_degrees": rad_to_deg(_defensive_angle),
		"defensive_clasp_error_m": _defensive_clasp_error,
		"bow_corrective_weight": _bow_weight,
		"bow_corrective_degrees": rad_to_deg(_bow_angle),
		"bow_clasp_error_m": _bow_clasp_error,
		"hinge_corrective_degrees": rad_to_deg(_hinge_last_angle),
		"hinge_capture_mode": _hinge_mode,
		"hinge_clasp_error_m": _hinge_clasp_error,
		"configure_usec": _configure_usec, "template_cache_hit": _template_cache_hit,
		"template_cache_size": _templates.size()}

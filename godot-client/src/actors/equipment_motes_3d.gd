extends MultiMeshInstance3D
## Short-lived motes sample the real equipment surface, including skin/morph
## pose. Each item has one small fixed budget, shared by all its effects.
const SHADER := preload("res://src/actors/equipment_glow.gdshader")
const RetainedSkin := preload("res://src/mounts/retained_mount_skin.gd")
const MAGIC_COUNT := 4
const RARE_COUNT := 6
const MAX_OPACITY := 0.42
const MAX_DISTANCE := 40.0
static var _samples: Dictionary = {}
static var _material: ShaderMaterial
var _surfaces: Array[Dictionary] = []
var _motes: Array[Dictionary] = []
var _style: Dictionary
var _rng := RandomNumberGenerator.new()

func configure(sources: Array[MeshInstance3D], style: Dictionary, skeleton: Skeleton3D) -> void:
	_style = style
	_rng.seed = get_instance_id()
	layers = 2
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	visibility_range_end = MAX_DISTANCE
	for source: MeshInstance3D in sources:
		var rig := source.get_node_or_null(source.skeleton) as Skeleton3D
		if rig == null: rig = skeleton
		var reference := RetainedSkin.for_secondary(source.mesh, source.skin, rig)
		if not reference.errors.is_empty():
			push_error(str(reference.errors))
			continue
		for point: Dictionary in _mesh_samples(reference.mesh):
			_surfaces.append({"source": source, "skeleton": rig, "point": point})
	if _material == null:
		_material = ShaderMaterial.new()
		_material.shader = SHADER
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.material = _material
	multimesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = true
	multimesh.use_custom_data = true
	multimesh.mesh = quad
	multimesh.instance_count = RARE_COUNT if float(style.strength) > 1.0 else MAGIC_COUNT
	for index: int in multimesh.instance_count:
		var mote := _spawn(index)
		mote.age = mote.lifetime * float(index) / multimesh.instance_count
		_motes.append(mote)
	_process(0.0)

static func _mesh_samples(mesh: Mesh) -> Array[Dictionary]:
	var key := mesh.get_instance_id()
	if _samples.has(key): return _samples[key].points
	var points: Array[Dictionary] = []
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var shapes := mesh.surface_get_blend_shape_arrays(surface)
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES] != null else PackedInt32Array()
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS] != null else PackedFloat32Array()
		var stride := bones.size() / maxi(1, vertices.size())
		for slot: int in mini(16, vertices.size()):
			var index := int(fmod(slot * 0.61803398875, 1.0) * vertices.size())
			var deltas := PackedVector3Array()
			for shape: Array in shapes:
				var positions: PackedVector3Array = shape[Mesh.ARRAY_VERTEX]
				deltas.append(positions[index] - vertices[index] if mesh.blend_shape_mode == Mesh.BLEND_SHAPE_MODE_NORMALIZED else positions[index])
			points.append({"position": vertices[index], "deltas": deltas,
				"bones": bones.slice(index * stride, (index + 1) * stride),
				"weights": weights.slice(index * stride, (index + 1) * stride)})
	if _samples.size() >= 128: _samples.clear()
	_samples[key] = {"mesh": mesh, "points": points}
	return points

func _spawn(index: int) -> Dictionary:
	return {"surface": _rng.randi_range(0, maxi(0, _surfaces.size() - 1)),
		"family_index": index % _style.families.size(), "age": 0.0,
		"lifetime": _rng.randf_range(0.65, 1.15), "size": _rng.randf_range(0.035, 0.05),
		"phase": _rng.randf_range(0.0, TAU)}

func _process(delta: float) -> void:
	if multimesh == null: return
	var camera := get_viewport().get_camera_3d()
	if not is_visible_in_tree() or _surfaces.is_empty() or (camera != null and camera.global_position.distance_squared_to(global_position) > MAX_DISTANCE * MAX_DISTANCE):
		multimesh.visible_instance_count = 0
		return
	multimesh.visible_instance_count = -1
	var bounds := AABB()
	var inverse_basis := global_basis.inverse()
	for index: int in _motes.size():
		var mote: Dictionary = _motes[index]
		mote.age += minf(delta, 0.1)
		if mote.age >= mote.lifetime:
			mote = _spawn(index)
			_motes[index] = mote
		var entry: Dictionary = _surfaces[mote.surface]
		var source: Variant = entry.source
		if not is_instance_valid(source) or not source.is_visible_in_tree():
			multimesh.set_instance_color(index, Color.TRANSPARENT)
			continue
		var age: float = mote.age / mote.lifetime
		var family: int = _style.families[mote.family_index]
		var drift := Vector3(0.0, 0.035 * mote.age, 0.0)
		match family:
			0: drift = Vector3(sin(mote.phase + age * 3.0) * 0.012, mote.age * 0.08, 0.0)
			1: drift.y = -mote.age * 0.045
			2, 4: drift = Vector3(cos(mote.phase + age * 2.0), 0.6, sin(mote.phase + age * 2.0)) * 0.022
			5: drift.x = sin(age * 9.0 + mote.phase) * 0.008
			6: drift = Vector3(0.06, 0.025, 0.0) * mote.age
			7: drift = Vector3.ZERO
		var at := to_local(_posed_point(entry)) + inverse_basis * drift
		var tint: Color = _style.colors[mote.family_index]
		tint.a = smoothstep(0.0, 0.2, age) * (1.0 - smoothstep(0.4, 1.0, age)) * MAX_OPACITY
		# Keep motes tiny in world units even when an imported piece has a
		# large authored scale or the actor's outfit uses a different rig fit.
		multimesh.set_instance_transform(index, Transform3D(inverse_basis.scaled(Vector3.ONE * float(mote.size)), at))
		multimesh.set_instance_color(index, tint)
		multimesh.set_instance_custom_data(index, Color(float(family), mote.phase, 0.0, 0.0))
		bounds = AABB(at, Vector3.ZERO) if index == 0 else bounds.expand(at)
	var smallest_scale := minf(global_basis.x.length(), minf(global_basis.y.length(), global_basis.z.length()))
	custom_aabb = bounds.grow(0.12 / maxf(0.0001, smallest_scale))

func _posed_point(entry: Dictionary) -> Vector3:
	var source: MeshInstance3D = entry.source
	var sample: Dictionary = entry.point
	var vertex: Vector3 = sample.position
	for shape: int in sample.deltas.size():
		vertex += sample.deltas[shape] * source.get_blend_shape_value(shape)
	var rig: Skeleton3D = entry.skeleton
	if source.skin != null and is_instance_valid(rig) and not sample.bones.is_empty():
		var posed := Vector3.ZERO
		for slot: int in sample.bones.size():
			var bind: int = sample.bones[slot]
			var weight: float = sample.weights[slot]
			if weight <= 0.0 or bind < 0 or bind >= source.skin.get_bind_count(): continue
			var bone := rig.find_bone(source.skin.get_bind_name(bind))
			if bone < 0: bone = source.skin.get_bind_bone(bind)
			if bone >= 0 and bone < rig.get_bone_count():
				posed += (rig.get_bone_global_pose(bone) * source.skin.get_bind_pose(bind) * vertex) * weight
		return rig.to_global(posed)
	return source.to_global(vertex)

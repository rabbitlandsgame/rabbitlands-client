extends RefCounted
## Per-corpse materials and one GPU-animated batch of surface fragments.
## Source meshes/materials stay shared and immutable; revival restores overrides.

const BODY_SHADER := preload("res://src/actors/creature_dissolve.gdshader")
const BODY_INCLUDE := preload("res://src/actors/creature_dissolve.gdshaderinc")
const ASH_SHADER := preload("res://src/actors/creature_ash.gdshader")
const SurfaceSampling := preload("res://src/actors/creature_surface_sampling.gd")
const FRAGMENT_COUNT := 320

var _saved: Array[Dictionary] = []
var _materials: Array[ShaderMaterial] = []
var _ash: MultiMeshInstance3D
var _actor: Node3D

func begin(actor: Node3D, seconds: float, seed_value: int) -> void:
	_actor = actor
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var surfaces: Array[Dictionary] = []
	var total_vertices := 0
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var source := node as MeshInstance3D
		# Body meshes use layer 1; map dots, labels and markers have other layers.
		if source.mesh == null or not source.is_visible_in_tree() or source.layers & 1 == 0:
			continue
		var overrides: Array[Material] = []
		var active: Array[Material] = []
		for surface in source.mesh.get_surface_count():
			overrides.append(source.get_surface_override_material(surface))
			active.append(source.get_active_material(surface))
		_saved.append({"mesh": source, "override": source.material_override, "surfaces": overrides})
		var skinning := _skin_transforms(source)
		for surface in source.mesh.get_surface_count():
			var arrays := source.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			if vertices.is_empty():
				continue
			total_vertices += vertices.size()
			surfaces.append({"mesh": source, "arrays": arrays, "skin": skinning,
				"surface":surface, "end": total_vertices, "material": active[surface]})
			var material := _body_material(active[surface])
			source.set_surface_override_material(surface, material)
			_materials.append(material)
		source.material_override = null
	var sampling := SurfaceSampling.virtual_surfaces(surfaces)
	if not sampling.errors.is_empty():
		reset()
		push_error("Invalid creature sampling partition: " + str(sampling.errors))
		return
	surfaces.assign(sampling.surfaces)
	total_vertices = int(sampling.total_vertices)
	if total_vertices == 0:
		return
	var fragments := _sample_fragments(surfaces,total_vertices,rng)
	var points: PackedVector3Array = fragments.points
	var colors: PackedColorArray = fragments.colors
	if points.is_empty():
		return
	var bounds := AABB(points[0], Vector3.ZERO)
	for point: Vector3 in points:
		bounds = bounds.expand(point)
	var longest := maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))
	var grain := clampf(longest * 0.055, 0.045, 0.18)
	var ash_material := ShaderMaterial.new()
	ash_material.shader = ASH_SHADER
	ash_material.set_shader_parameter("dissolve_seconds", seconds)
	_materials.append(ash_material)
	for material: ShaderMaterial in _materials:
		material.set_shader_parameter("dissolve_to_actor", actor.global_transform.affine_inverse())
		material.set_shader_parameter("dissolve_min", bounds.position)
		material.set_shader_parameter("dissolve_size", bounds.size)
		material.set_shader_parameter("dissolve_grain", grain)
	var fragment := BoxMesh.new()
	fragment.size = Vector3.ONE
	var batch := MultiMesh.new()
	batch.transform_format = MultiMesh.TRANSFORM_3D
	batch.use_colors = true
	batch.use_custom_data = true
	batch.mesh = fragment
	batch.instance_count = points.size()
	for index in points.size():
		var size := rng.randf_range(0.12, 0.36) * grain
		var basis := Basis.from_euler(Vector3(rng.randf() * TAU, rng.randf() * TAU, rng.randf() * TAU))
		batch.set_instance_transform(index, Transform3D(basis.scaled(Vector3(size, size * 0.45, size)), points[index]))
		batch.set_instance_color(index, colors[index])
		batch.set_instance_custom_data(index, Color(rng.randf(), 0, 0, 0))
	_ash = MultiMeshInstance3D.new()
	_ash.name = "DissolveAsh"
	_ash.multimesh = batch
	_ash.material_override = ash_material
	_ash.layers = 2 # Gameplay camera only, never either map camera.
	_ash.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_ash.custom_aabb = bounds.grow(3.0)
	actor.add_child(_ash)

func _sample_fragments(surfaces: Array[Dictionary], total_vertices: int, rng: RandomNumberGenerator) -> Dictionary:
	var points := PackedVector3Array()
	var colors := PackedColorArray()
	for index in FRAGMENT_COUNT:
		var pick := rng.randi_range(0, total_vertices - 1)
		for surface: Dictionary in surfaces:
			if pick >= int(surface.end):
				continue
			if int(surface.triangles) < 1:
				break
			# Keep the original surface/triangle RNG ranges and call order.
			# The chosen physical partition supplies only its corner indices.
			var original := rng.randi_range(0,int(surface.triangles)-1)
			var physical: Dictionary = surface
			var local_triangle := original
			if surface.has("partition"):
				var partition: Dictionary = surface.partition
				physical = partition.remainder
				local_triangle = original - partition.ids.bsearch(original)
				for part: Dictionary in partition.selected:
					var found: int = part.ids.bsearch(original)
					if found < part.ids.size() and part.ids[found] == original:
						physical = part.surface; local_triangle = found; break
			var arrays: Array = physical.arrays
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
			var triangle := local_triangle * 3
			var corners := PackedVector3Array()
			for corner in 3:
				var vertex := indices[triangle + corner] if not indices.is_empty() else triangle + corner
				corners.append(_posed_vertex(physical, vertex))
			var u := sqrt(rng.randf())
			var v := rng.randf()
			points.append(corners[0] * (1.0 - u) + corners[1] * u * (1.0 - v) + corners[2] * u * v)
			var base := Color(0.48, 0.43, 0.36)
			if surface.material is BaseMaterial3D:
				base = (surface.material as BaseMaterial3D).albedo_color.lerp(base, 0.65)
			colors.append(base.darkened(rng.randf_range(0.0, 0.35)))
			break
	return {"points":points,"colors":colors}

func update(progress: float) -> void:
	for material: ShaderMaterial in _materials:
		material.set_shader_parameter("dissolve_progress", progress)
	if is_instance_valid(_ash):
		_ash.visible = progress < 1.0

func reset() -> void:
	for saved: Dictionary in _saved:
		if not is_instance_valid(saved.mesh):
			continue
		var source: MeshInstance3D = saved.mesh
		source.material_override = saved.override
		for surface in saved.surfaces.size():
			source.set_surface_override_material(surface, saved.surfaces[surface])
	_saved.clear()
	_materials.clear()
	if is_instance_valid(_ash):
		_ash.free()
	_ash = null

func _body_material(source: Material) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	# Preserve custom creature shaders as well as the usual imported PBR finish.
	if source is ShaderMaterial and (source as ShaderMaterial).shader != null:
		material = source.duplicate() as ShaderMaterial
		var code := material.shader.code
		var entry := RegEx.new()
		entry.compile("void\\s+fragment\\s*\\(\\s*\\)\\s*\\{")
		if entry.search(code) != null:
			# Shader.code is compiled directly; it does not resolve resource-file
			# includes. A replay can also encounter an existing dissolve material;
			# resolve its include and keep exactly one set of functions and calls.
			for path: String in ["creature_dissolve.gdshaderinc", "res://src/actors/creature_dissolve.gdshaderinc"]:
				code = code.replace("#include \"" + path + "\"", BODY_INCLUDE.code)
			if not code.contains("void dissolve_body("):
				code = code.replace("shader_type spatial;", "shader_type spatial;\n" + BODY_INCLUDE.code + "\n")
			if code.count("dissolve_body(") <= 1:
				code = entry.sub(code, "void fragment() {\n dissolve_body((INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz, ALBEDO);\n")
			material.shader = Shader.new()
			material.shader.code = code
			material.next_pass = null
			return material
	material.shader = BODY_SHADER
	if source is BaseMaterial3D:
		var base := source as BaseMaterial3D
		material.set_shader_parameter("base_color", base.albedo_color)
		material.set_shader_parameter("base_texture", base.albedo_texture)
		material.set_shader_parameter("uv_scale", base.uv1_scale)
		material.set_shader_parameter("uv_offset", base.uv1_offset)
		material.set_shader_parameter("surface_roughness", base.roughness)
		material.set_shader_parameter("surface_metallic", base.metallic)
		material.set_shader_parameter("surface_specular", base.metallic_specular)
		material.set_shader_parameter("use_vertex_color", base.vertex_color_use_as_albedo)
		material.set_shader_parameter("use_normal", base.normal_enabled and base.normal_texture != null)
		material.set_shader_parameter("normal_texture", base.normal_texture)
		material.set_shader_parameter("normal_strength", base.normal_scale)
		if base.emission_enabled:
			material.set_shader_parameter("emission_color", Vector3(base.emission.r, base.emission.g, base.emission.b) * base.emission_energy_multiplier)
			material.set_shader_parameter("emission_texture", base.emission_texture)
		if base.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			material.set_shader_parameter("alpha_cutoff", maxf(0.01, base.alpha_scissor_threshold))
	return material

func _skin_transforms(source: MeshInstance3D) -> Array[Transform3D]:
	var transforms: Array[Transform3D] = []
	var skeleton := source.get_node_or_null(source.skeleton) as Skeleton3D
	if source.skin == null or skeleton == null:
		return transforms
	for bind in source.skin.get_bind_count():
		var bone := skeleton.find_bone(source.skin.get_bind_name(bind))
		if bone < 0:
			bone = source.skin.get_bind_bone(bind)
		transforms.append(skeleton.get_bone_global_pose(bone) * source.skin.get_bind_pose(bind)
			if bone >= 0 and bone < skeleton.get_bone_count() else Transform3D.IDENTITY)
	return transforms

func _posed_vertex(surface: Dictionary, index: int) -> Vector3:
	var arrays: Array = surface.arrays
	var source: MeshInstance3D = surface.mesh
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var vertex := vertices[index]
	var transforms: Array[Transform3D] = surface.skin
	if not transforms.is_empty() and arrays[Mesh.ARRAY_BONES] != null and arrays[Mesh.ARRAY_WEIGHTS] != null:
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var stride := bones.size() / vertices.size()
		var posed := Vector3.ZERO
		for slot in stride:
			var offset := index * stride + slot
			var bind := bones[offset]
			if weights[offset] > 0.0 and bind >= 0 and bind < transforms.size():
				posed += (transforms[bind] * vertex) * weights[offset]
		var skeleton := source.get_node(source.skeleton) as Skeleton3D
		return _actor.to_local(skeleton.to_global(posed))
	return _actor.to_local(source.to_global(vertex))

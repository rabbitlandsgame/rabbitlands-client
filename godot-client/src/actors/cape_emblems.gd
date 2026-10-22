extends RefCounted
## Embroidery on the existing imported cape. Secondary UVs are measured on
## its rest mesh, so the emblem follows the same skin, drape and cloth bones.
## Detail albedo keeps the original weave, normal map and three cloth colours.

static var enabled := true
static var _materials: Array[WeakRef] = []
static var _meshes: Dictionary = {}
const CACHE_LIMIT := 64

static func set_enabled(value: bool) -> void:
	enabled = value
	var alive: Array[WeakRef] = []
	for reference: WeakRef in _materials:
		var material := reference.get_ref() as StandardMaterial3D
		if material != null:
			material.detail_enabled = enabled
			alive.append(reference)
	_materials = alive

static func apply(node: MeshInstance3D, texture_path: String) -> void:
	if node.mesh == null or texture_path.is_empty():
		return
	var texture := load(texture_path) as Texture2D
	if texture == null:
		return
	node.mesh = _projected_mesh(node.mesh)
	for surface: int in range(node.mesh.get_surface_count()):
		var source := node.get_active_material(surface) as StandardMaterial3D
		# Lining and border retain their separate colours, without embroidery.
		if source == null or not source.resource_name.ends_with("Base"):
			continue
		var material := source.duplicate() as StandardMaterial3D
		material.detail_albedo = texture
		material.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
		material.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MIX
		material.texture_repeat = false
		material.detail_enabled = enabled
		node.set_surface_override_material(surface, material)
		_materials.append(weakref(material))
	# Long sessions keep only live material references.
	if _materials.size() > 256:
		set_enabled(enabled)

static func _projected_mesh(source: Mesh) -> Mesh:
	var key := source.get_instance_id()
	if _meshes.has(key):
		return _meshes[key][1] as Mesh
	var mesh := ArrayMesh.new()
	for surface: int in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var uv := PackedVector2Array()
		for point: Vector3 in vertices:
			# Half-metre embroidery across the upper-middle back. SVG transparency
			# outside the design and clamp sampling leave the rest plain cloth.
			uv.append(Vector2(0.5 - point.x / 0.52, (1.45 - point.y) / 0.52))
		arrays[Mesh.ARRAY_TEX_UV2] = uv
		mesh.add_surface_from_arrays(source.surface_get_primitive_type(surface),
			arrays, [], {}, source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		mesh.surface_set_material(surface, source.surface_get_material(surface))
	if _meshes.size() >= CACHE_LIMIT:
		_meshes.clear()
	# Retain the source as well: an instance id cannot be reused while cached.
	_meshes[key] = [source, mesh]
	return mesh

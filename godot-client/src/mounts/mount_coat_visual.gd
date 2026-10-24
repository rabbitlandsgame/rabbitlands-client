extends RefCounted
## Per-instance surfaces: shared scene-cache meshes/materials are never mutated.
## Mask only the imported animal, preserving tack and the face/head attachment.
const Coats := preload("res://src/mounts/mount_coats.gd")
const CoatShader := preload("res://src/mounts/mount_coat.gdshader")
var current := "original"
var mount_id := ""
var parts: Array[Dictionary] = []
var rig: Skeleton3D
var protected := {}

func configure(actor: ReplicatedActor3D, id: String, profile: Dictionary) -> void:
	mount_id = id
	rig = actor.get_skeleton()
	var names: Array = profile.get("appearanceProtectedBones", [str(profile.reins.headBone)])
	if id == "moor_pony": names = names + ["Bone_021"]
	for index: int in rig.get_bone_count():
		var parent := index
		while parent >= 0:
			if rig.get_bone_name(parent) in names:
				protected[index] = true
				break
			parent = rig.get_bone_parent(parent)
	for node: Node in actor.get_node("NativeModel").find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh != null:
			var materials: Array = []
			var active: Array = []
			for surface: int in mesh.mesh.get_surface_count():
				materials.append(mesh.get_surface_override_material(surface))
				active.append(mesh.get_active_material(surface))
			parts.append({"node":mesh, "mesh":mesh.mesh, "overrides":materials,
				"materialOverride":mesh.material_override,"active":active,"masked":null})

func apply(coat_id: String) -> void:
	if not Coats.valid(mount_id, coat_id): coat_id = "original"
	if current == coat_id: return
	current = coat_id
	var preset := Coats.preset(mount_id, coat_id)
	for part: Dictionary in parts:
		var node := part.node as MeshInstance3D
		var source := part.mesh as Mesh
		if coat_id == "original":
			node.mesh = source
			node.material_override = part.materialOverride
			for surface: int in source.get_surface_count():
				node.set_surface_override_material(surface, part.overrides[surface])
			continue
		if part.masked == null: part.masked = _masked_mesh(node, source)
		node.mesh = part.masked
		node.material_override = null
		for surface: int in source.get_surface_count():
			var original := part.active[surface] as Material
			if not original is StandardMaterial3D: continue
			var base := original as StandardMaterial3D
			var texture: Texture2D = base.albedo_texture
			# Optional real texture replacement, by original material name. Only
			# repository paths in the curated catalogue can reach this loader.
			var override_path := str(preset.get("textures", {}).get(base.resource_name, ""))
			if not override_path.is_empty() and ResourceLoader.exists(override_path):
				texture = load(override_path) as Texture2D
			if texture == null: continue
			var material := ShaderMaterial.new()
			material.shader = CoatShader
			material.set_shader_parameter("coat_texture",texture)
			material.set_shader_parameter("base_colour",base.albedo_color)
			material.set_shader_parameter("use_vertex_colour",base.vertex_color_use_as_albedo)
			material.set_shader_parameter("coat_colour",Color(str(preset.colour)))
			material.set_shader_parameter("accent_colour",Color(str(preset.accent)))
			material.set_shader_parameter("coat_strength",float(preset.strength))
			material.set_shader_parameter("pattern",int(preset.pattern))
			material.set_shader_parameter("pattern_strength",float(preset.get("patternStrength",0.7)))
			material.set_shader_parameter("pattern_scale",6.0 / maxf(.05,source.get_aabb().size.y))
			material.set_shader_parameter("roughness",base.roughness)
			material.set_shader_parameter("metallic",base.metallic)
			if base.metallic_texture != null:
				material.set_shader_parameter("use_metallic_map",true)
				material.set_shader_parameter("metallic_map",base.metallic_texture)
				material.set_shader_parameter("metallic_channel",_channel(base.metallic_texture_channel))
			if base.roughness_texture != null:
				material.set_shader_parameter("use_roughness_map",true)
				material.set_shader_parameter("roughness_map",base.roughness_texture)
				material.set_shader_parameter("roughness_channel",_channel(base.roughness_texture_channel))
			if base.normal_enabled and base.normal_texture != null:
				material.set_shader_parameter("has_normal",true)
				material.set_shader_parameter("coat_normal",base.normal_texture)
				material.set_shader_parameter("normal_strength",base.normal_scale)
			node.set_surface_override_material(surface,material)

static func _channel(channel: int) -> Vector4:
	if channel == BaseMaterial3D.TEXTURE_CHANNEL_GRAYSCALE: return Vector4(.333333,.333333,.333333,0)
	var result := Vector4.ZERO
	result[clampi(channel,0,3)] = 1.0
	return result

func _masked_mesh(node: MeshInstance3D, source: Mesh) -> ArrayMesh:
	var output := ArrayMesh.new()
	for index: int in source.get_blend_shape_count(): output.add_blend_shape(source.get_blend_shape_name(index))
	output.blend_shape_mode = source.blend_shape_mode
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var colours: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] != null else PackedColorArray()
		if colours.is_empty():
			colours.resize(vertices.size())
			colours.fill(Color.WHITE)
		var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES] != null else PackedInt32Array()
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS] != null else PackedFloat32Array()
		var influences := joints.size() / maxi(1,vertices.size())
		for vertex: int in vertices.size():
			var mask := 1.0
			for influence: int in influences:
				var offset := vertex * influences + influence
				var bind := joints[offset]
				if node.skin == null: continue
				var name := node.skin.get_bind_name(bind)
				var bone := rig.find_bone(name) if not name.is_empty() else node.skin.get_bind_bone(bind)
				if protected.has(bone): mask -= weights[offset]
			colours[vertex].a = clampf(mask,0.0,1.0)
		arrays[Mesh.ARRAY_COLOR] = colours
		# A dedicated rest-coordinate attribute keeps patterns fixed through
		# GPU skinning and corrective morphs, including the eight-weight rigs.
		var rest_coordinates := PackedFloat32Array()
		for vertex: Vector3 in vertices:
			rest_coordinates.append_array([vertex.x,vertex.y,vertex.z])
		arrays[Mesh.ARRAY_CUSTOM0] = rest_coordinates
		var flags: int = (source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS) \
			| (Mesh.ARRAY_CUSTOM_RGB_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT)
		output.add_surface_from_arrays(source.surface_get_primitive_type(surface),arrays,
			source.surface_get_blend_shape_arrays(surface),_surface_lods(source,surface),flags)
		output.surface_set_material(surface,source.surface_get_material(surface))
		output.surface_set_name(surface,source.surface_get_name(surface))
	return output

static func _surface_lods(source: Mesh, surface: int) -> Dictionary:
	var raw: Dictionary = RenderingServer.mesh_get_surface(source.get_rid(),surface)
	var width := 2 if int(raw.get("vertex_count",0)) <= 65536 else 4
	var result := {}
	for lod: Dictionary in raw.get("lods",[]):
		var bytes: PackedByteArray = lod.index_data
		var indices := PackedInt32Array()
		indices.resize(bytes.size()/width)
		for index: int in indices.size():
			indices[index] = bytes.decode_u16(index*width) if width == 2 else bytes.decode_u32(index*width)
		result[float(lod.edge_length)] = indices
	return result

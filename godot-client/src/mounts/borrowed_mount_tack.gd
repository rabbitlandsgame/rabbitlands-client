extends Node3D
## Reuses the imported pony saddle's actual vertices, UVs and material.
## Only saddle-owned triangles are copied; neither source GLB is modified.
var rig: Skeleton3D
var bone := -1
var rest_inverse := Transform3D.IDENTITY
var triangle_count := 0
var vertex_count := 0

func configure(target: Skeleton3D, profile: Dictionary) -> Array[String]:
	rig = target
	bone = rig.find_bone(str(profile.bone))
	if bone < 0:
		return ["Borrowed saddle attachment missing"]
	rest_inverse = rig.get_bone_global_rest(bone).affine_inverse()
	var source := GlbSceneCache.instantiate(str(profile.source))
	if source == null:
		return ["Borrowed saddle source missing"]
	var skeletons := source.find_children("*", "Skeleton3D", true, false)
	if skeletons.is_empty():
		source.free()
		return ["Borrowed saddle source skeleton missing"]
	var original := skeletons[0] as Skeleton3D
	var source_bone := original.find_bone(str(profile.sourceBone))
	if source_bone < 0:
		source.free()
		return ["Borrowed saddle ownership bone missing"]
	var anchor := original.get_bone_global_rest(source_bone).origin
	var point: Array = profile.positionNative
	var values: Array = profile.scale
	var fit_scale := Vector3(values[0], values[1], values[2])
	var destination := Vector3(point[0], point[1], point[2])
	for child: Node in original.get_children():
		if not child is MeshInstance3D:
			continue
		var mesh := child as MeshInstance3D
		if mesh.skin == null:
			continue
		for surface: int in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var influences := joints.size() / vertices.size()
			var selected := PackedByteArray()
			selected.resize(vertices.size())
			for vertex: int in vertices.size():
				var ownership := 0.0
				for influence: int in influences:
					var index := vertex * influences + influence
					if weights[index] <= 0.0:
						continue
					var bind := joints[index]
					var name := mesh.skin.get_bind_name(bind)
					var joint := original.find_bone(name) if not name.is_empty() else mesh.skin.get_bind_bone(bind)
					while joint >= 0 and joint != source_bone:
						joint = original.get_bone_parent(joint)
					if joint == source_bone:
						ownership += weights[index]
				selected[vertex] = 1 if ownership > .95 else 0
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var kept := PackedInt32Array()
			var mapping := {}
			var order := PackedInt32Array()
			for triangle: int in range(0, indices.size(), 3):
				if not (selected[indices[triangle]] and selected[indices[triangle + 1]] and selected[indices[triangle + 2]]):
					continue
				for corner: int in 3:
					var index := indices[triangle + corner]
					if not mapping.has(index):
						mapping[index] = order.size()
						order.append(index)
					kept.append(mapping[index])
			if kept.is_empty():
				continue
			for attribute: int in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TANGENT,
					Mesh.ARRAY_COLOR, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2]:
				if arrays[attribute] == null:
					continue
				var original_values: Variant = arrays[attribute]
				var reduced: Variant = original_values.slice(0, 0)
				var stride := 4 if attribute == Mesh.ARRAY_TANGENT else 1
				for index: int in order:
					for component: int in stride:
						reduced.append(original_values[index * stride + component])
				arrays[attribute] = reduced
			vertices = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL] if arrays[Mesh.ARRAY_NORMAL] != null else PackedVector3Array()
			var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
			for index: int in vertices.size():
				var local := vertices[index] - anchor
				var normal_scale := fit_scale
				# Shorten the borrowed blanket/straps for this narrower horse;
				# the fit stays fixed for every gait rather than stretching in motion.
				if local.y < 0.0:
					local.y *= float(profile.get("dropScale", 1.0))
					normal_scale.y *= float(profile.get("dropScale", 1.0))
				vertices[index] = destination + local * fit_scale
				if not normals.is_empty():
					normals[index] = (normals[index] / normal_scale).normalized()
				if not tangents.is_empty():
					var tangent := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
					tangent = (tangent * normal_scale).normalized()
					tangents[index * 4] = tangent.x
					tangents[index * 4 + 1] = tangent.y
					tangents[index * 4 + 2] = tangent.z
			arrays[Mesh.ARRAY_VERTEX] = vertices
			arrays[Mesh.ARRAY_NORMAL] = normals
			arrays[Mesh.ARRAY_TANGENT] = tangents
			arrays[Mesh.ARRAY_INDEX] = kept
			arrays[Mesh.ARRAY_BONES] = null
			arrays[Mesh.ARRAY_WEIGHTS] = null
			var output := MeshInstance3D.new()
			output.name = "BorrowedPonySaddle"
			var fitted := ArrayMesh.new()
			fitted.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			fitted.surface_set_material(0, mesh.get_active_material(surface))
			output.mesh = fitted
			add_child(output)
			triangle_count += kept.size() / 3
			vertex_count += vertices.size()
	source.free()
	if triangle_count == 0:
		return ["No saddle-owned triangles found in imported source"]
	update_pose()
	return []

func update_pose() -> void:
	global_transform = rig.global_transform * rig.get_bone_global_pose(bone) * rest_inverse

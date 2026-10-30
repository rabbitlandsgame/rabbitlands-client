class_name NecklineSkin
extends RefCounted
## The split body ends at the stock shirt's high, sloping neck opening.
## Equipped collars can sit below that opening, especially at the nape.
## Continue the existing skin rim under the collar. Keep the imported head,
## its UVs and its boundary skinning exact, and remove this lining on unequip.

const STEPS := 4
const NECK_AXIS_Z := -.038

static var _cache := {}

static func clear() -> void:
	_cache.clear()

static func make(source: MeshInstance3D, skeleton: Skeleton3D) -> MeshInstance3D:
	if source.skin == null or source.mesh == null:
		return null
	var original: Mesh = source.get_meta("uncovered_body_mesh", source.mesh) as Mesh
	var key := original.get_instance_id()
	if not _cache.has(key):
		_cache[key] = build(original, source.skin, skeleton)
	var entry: Dictionary = _cache[key]
	if entry.is_empty():
		return null
	var lining := MeshInstance3D.new()
	lining.name = "EquipmentNeckSkin"
	lining.mesh = entry["mesh"]
	lining.skin = source.skin
	lining.transform = skeleton.global_transform.affine_inverse() * source.global_transform
	lining.skeleton = NodePath("..")
	lining.set_meta("native_equipment", true)
	lining.set_meta("neck_source", source)
	lining.set_meta("neck_surfaces", entry["surfaces"])
	refresh_materials(lining)
	return lining

static func refresh_materials(lining: MeshInstance3D) -> void:
	var source := lining.get_meta("neck_source") as MeshInstance3D
	var surfaces: Array = lining.get_meta("neck_surfaces") as Array
	for index: int in range(surfaces.size()):
		lining.set_surface_override_material(index, source.get_active_material(int(surfaces[index])))

static func build(original: Mesh, skin: Skin, skeleton: Skeleton3D) -> Dictionary:
	var neck := -1
	var spine := -1
	for bind: int in range(skin.get_bind_count()):
		var name := skin.get_bind_name(bind)
		if name.is_empty() and skin.get_bind_bone(bind) >= 0:
			name = skeleton.get_bone_name(skin.get_bind_bone(bind))
		if name == &"neck_01":
			neck = bind
		if name == &"spine_03":
			spine = bind
	if neck < 0 or spine < 0:
		return {}
	var points := {}
	var edges := {}
	var arrays: Array[Array] = []
	for surface: int in range(original.get_surface_count()):
		var a := original.surface_get_arrays(surface)
		arrays.append(a)
		var p: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
		var faces: PackedInt32Array = a[Mesh.ARRAY_INDEX]
		var ids := PackedInt32Array()
		for v: Vector3 in p:
			var point := Vector3i(roundi(v.x * 100000),roundi(v.y * 100000),roundi(v.z * 100000))
			if not points.has(point):
				points[point] = points.size()
			ids.append(int(points[point]))
		for index: int in range(0, faces.size(), 3):
			for corner: int in range(3):
				var a_id := faces[index + corner]
				var b_id := faces[index + (corner + 1) % 3]
				var edge := Vector2i(mini(ids[a_id],ids[b_id]),maxi(ids[a_id],ids[b_id]))
				if ids[a_id] == ids[b_id]:
					continue
				if edges.has(edge):
					edges[edge][0] += 1
				else:
					edges[edge] = [1,surface,a_id,b_id,faces[index + (corner + 2) % 3]]
	var strips := {}
	for row: Array in edges.values():
		if int(row[0]) != 1:
			continue
		var a: Array = arrays[int(row[1])]
		var p: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
		var va := p[int(row[2])]
		var vb := p[int(row[3])]
		if not is_neck_rim(va) or not is_neck_rim(vb):
			continue
		if maxf(va.y,vb.y) <= 1.405:
			continue
		if not strips.has(int(row[1])):
			strips[int(row[1])] = []
		strips[int(row[1])].append([int(row[2]),int(row[3]),int(row[4])])
	var mesh := ArrayMesh.new()
	var surfaces := []
	for surface: int in strips:
		var source: Array = arrays[surface]
		var original_p: PackedVector3Array = source[Mesh.ARRAY_VERTEX]
		var original_n: PackedVector3Array = source[Mesh.ARRAY_NORMAL]
		var original_uv: PackedVector2Array = source[Mesh.ARRAY_TEX_UV]
		var original_j: PackedInt32Array = source[Mesh.ARRAY_BONES]
		var original_w: PackedFloat32Array = source[Mesh.ARRAY_WEIGHTS]
		var original_colors: PackedColorArray = source[Mesh.ARRAY_COLOR] if source[Mesh.ARRAY_COLOR] is PackedColorArray else PackedColorArray()
		var original_tangents: PackedFloat32Array = source[Mesh.ARRAY_TANGENT] if source[Mesh.ARRAY_TANGENT] is PackedFloat32Array else PackedFloat32Array()
		var stride: int = original_j.size() / original_p.size()
		var p := PackedVector3Array()
		var n := PackedVector3Array()
		var uv := PackedVector2Array()
		var colors := PackedColorArray()
		var tangents := PackedFloat32Array()
		var joints := PackedInt32Array()
		var weights := PackedFloat32Array()
		var indices := PackedInt32Array()
		for pair: Array in strips[surface]:
			var start := p.size()
			for row: int in range(STEPS + 1):
				var blend := float(row) / STEPS
				for column: int in range(2):
					var v := int(pair[column])
					var vertex := original_p[v]
					# Tuck the continuation inside the fitted collar. The former
					# outward/backward extrusion made a broad skin flap at the
					# nape when a large collar was reduced to the real neck size.
					var bottom := Vector3(vertex.x * .90, minf(vertex.y, 1.395),
						NECK_AXIS_Z + (vertex.z - NECK_AXIS_Z) * .70)
					p.append(vertex.lerp(bottom, blend))
					n.append(original_n[v])
					uv.append(original_uv[v].lerp((original_uv[v] * 2.+original_uv[int(pair[2])]) / 3.,blend))
					if original_colors.size() == original_p.size():
						colors.append(original_colors[v])
					if original_tangents.size() == original_p.size() * 4:
						for component: int in range(4):
							tangents.append(original_tangents[v * 4 + component])
					if row == 0:
						for slot: int in range(stride):
							joints.append(original_j[v * stride + slot])
							weights.append(original_w[v * stride + slot])
						continue
					var dense := {}
					for slot: int in range(stride):
						var j := original_j[v * stride + slot]
						dense[j] = float(dense.get(j,0.)) + original_w[v * stride + slot]*(1. - blend)
					dense[neck] = float(dense.get(neck,0.)) + .55 * blend
					dense[spine] = float(dense.get(spine,0.)) + .45 * blend
					var ranked: Array = dense.keys()
					ranked.sort_custom(func(a: int,b: int) -> bool: return float(dense[a])>float(dense[b]))
					var total := 0.
					for slot: int in range(mini(stride,ranked.size())): total += float(dense[ranked[slot]])
					for slot: int in range(stride):
						joints.append(int(ranked[slot]) if slot < ranked.size() else 0)
						weights.append(float(dense[ranked[slot]]) / total if slot < ranked.size() else 0.)
			for row: int in range(STEPS):
				var first := start + row * 2
				indices.append_array(PackedInt32Array([first,first + 2,first + 1,first + 1,first + 2,first + 3]))
		var a := []
		a.resize(Mesh.ARRAY_MAX)
		a[Mesh.ARRAY_VERTEX]=p
		a[Mesh.ARRAY_NORMAL]=n
		a[Mesh.ARRAY_TEX_UV]=uv
		if not colors.is_empty():
			a[Mesh.ARRAY_COLOR]=colors
		if not tangents.is_empty():
			a[Mesh.ARRAY_TANGENT]=tangents
		a[Mesh.ARRAY_BONES]=joints
		a[Mesh.ARRAY_WEIGHTS]=weights
		a[Mesh.ARRAY_INDEX]=indices
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,a,[],{},
			original.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		mesh.surface_set_material(mesh.get_surface_count() - 1,original.surface_get_material(surface))
		surfaces.append(surface)
	return {} if surfaces.is_empty() else {"mesh":mesh,"surfaces":surfaces}

static func is_neck_rim(p: Vector3) -> bool:
	return p.y>1.365 and p.y<1.54 and absf(p.x)<.135 and p.z>-.18 and p.z<.12

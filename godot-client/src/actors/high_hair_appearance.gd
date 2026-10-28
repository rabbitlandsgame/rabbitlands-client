class_name HighHairAppearance
extends RefCounted
## Optional source-derived Human hair finish. All processing is once on change;
## Low/Medium restore the exact incoming mesh/material references.
##
## The hair finish slider (colour model spec revision 3, 4.7): a saved finish
## runs develop's code exactly; any other position s blends male Parted's own
## Swept and Tousled flows by HairFinish.weights(s), regroups the female Buns
## updo, collapses its central needle-bangs toward their roots and lowers its
## fringe by min(w_swept, 1) (the bangs go, as develop's Swept, at 1), and grows
## the Swept or Tousled hero-lock layer in by min(w, 1). Custom colours
## (AppearanceColours) give the hair (P4) and beard (B2) their dyes.
const HIGH := 2
const SHADER := preload("res://src/actors/high_hair_appearance.gdshader")
const LOCKS := preload("res://src/actors/portrait_hair_locks.gd")
const GROOM := preload("res://src/actors/portrait_groom.gd")
const HAIR_FINISH := preload("res://src/actors/hair_finish.gd")
const COLOURS := preload("res://src/actors/appearance_colours.gd")
## The two imported central needle-bang islands of the female Buns hairstyle.
const NEEDLE_BANG_SIZE := 264
const META := &"rl_high_hair"
const USER_META := &"rl_high_hair_user"
const EXIT_META := &"rl_high_hair_exit"
const CACHE_LIMIT := 24
const MATERIAL_LIMIT := 128
static var _meshes: Dictionary = {}
static var _materials: Dictionary = {}
static var _users: Dictionary = {}
static var _cold_usec := 0
static var _hits := 0

static func _supported(config: Dictionary) -> bool:
	return str(config.get("culture", "")) == "luminous" and str(config.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func _hair_nodes(native_root: Node3D) -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for node: Node in native_root.find_children("*", "MeshInstance3D", true, false):
		if node.get_parent() != null and str(node.get_parent().name).begins_with("AppearanceHair_"):
			result.append(node as MeshInstance3D)
	return result

static func _finish_nodes(native_root: Node3D) -> Array[MeshInstance3D]:
	var result := _hair_nodes(native_root)
	var beard := native_root.find_child("PortraitFacialHair",true,false) as MeshInstance3D
	if beard != null: result.append(beard)
	return result

static func _locally_visible(node: Node3D, native_root: Node3D) -> bool:
	var cursor: Node = node
	while cursor != null:
		if cursor is Node3D and not (cursor as Node3D).visible: return false
		if cursor == native_root: return true
		cursor = cursor.get_parent()
	return false

static func apply(native_root: Node3D, skeleton: Skeleton3D, appearance: Dictionary, config: Dictionary, level: int) -> void:
	if not is_instance_valid(native_root): return
	if level != HIGH or not _supported(config) or not is_instance_valid(skeleton):
		release(native_root)
		return
	var head := skeleton.find_bone("Head")
	if head < 0: return
	var visible_hair := false
	for hair: MeshInstance3D in _hair_nodes(native_root):
		if hair.mesh != null and _locally_visible(hair, native_root): visible_hair = true
	var beard := native_root.find_child("PortraitFacialHair",true,false) as MeshInstance3D
	var visible_beard := beard != null and beard.mesh != null and _locally_visible(beard,native_root)
	if not visible_hair and not visible_beard:
		release(native_root)
		return
	_users[native_root.get_instance_id()] = weakref(native_root)
	native_root.set_meta(USER_META, true)
	if not native_root.has_meta(EXIT_META):
		native_root.tree_exiting.connect(func() -> void: release(native_root), CONNECT_ONE_SHOT)
		native_root.set_meta(EXIT_META, true)
	var detail := clampi(int(appearance.get("hair_detail", 0)), 0, 2)
	var finish := HAIR_FINISH.resolve(appearance)
	var finish_s := int(finish.s) if bool(finish.custom) else -1
	var finish_key := str(detail) if finish_s < 0 else "s%d" % finish_s
	var style := AppearanceVariants.hair_style(int(appearance.get("hair", 0)))
	var length := roundi(CharacterProportions.value(appearance,"hair_length"))
	var volume := roundi(CharacterProportions.value(appearance,"hair_volume"))
	var eye_y := GROOM._eye_height(native_root.find_child("eyes",true,false) as MeshInstance3D,skeleton,skeleton.get_bone_global_rest(head),native_root)
	var color := AppearanceVariants.hair_color(int(appearance.get("hair", 0)))
	if bool(COLOURS.hair(appearance, config).custom):
		color = COLOURS.hair_dye(appearance, config, "P4", style,
			float(finish_s if finish_s >= 0 else HAIR_FINISH.enum_slider(detail)))
	var sex := str(config.get("gender", ""))
	# The hero-lock layer drawn: the saved finish's, or for a slider position
	# the Swept (below Classic) or Tousled (above) layer grown in by min(w, 1).
	var lock_detail := detail
	var growth := 1.0
	if finish_s >= 0:
		var weights := HAIR_FINISH.weights(finish_s)
		lock_detail = 2 if finish_s < 50 else 1
		growth = minf(weights.x if finish_s < 50 else weights.y, 1.0)
		if growth <= 0.0:
			lock_detail = 0
	var head_from_root := skeleton.get_bone_global_rest(head).affine_inverse() * GROOM._to_root(skeleton, native_root).affine_inverse()
	for hair: MeshInstance3D in _hair_nodes(native_root):
		if hair.has_meta("rl_concept_hair") or hair.mesh == null or not _locally_visible(hair, native_root): continue
		var previous: Dictionary = hair.get_meta(META, {})
		var source := hair.mesh
		var original_override := hair.material_override
		var originals: Array[Material] = []
		if not previous.is_empty() and hair.mesh == previous.result:
			source = previous.source
			original_override = previous.override
			originals.assign(previous.surfaces)
		else:
			for surface: int in source.get_surface_count():
				originals.append(hair.get_surface_override_material(surface))
		var authored := hair.get_meta(GROOM.SOURCE_META, source) as Mesh
		var transform := head_from_root * GROOM._to_root(hair, native_root)
		var head_bind := LOCKS.binding(hair.skin,skeleton,&"Head")
		var neck_name: StringName = skeleton.get_bone_name(skeleton.get_bone_parent(head)) if skeleton.get_bone_parent(head)>=0 else &"Head"
		var neck_bind := LOCKS.binding(hair.skin,skeleton,neck_name)
		var key := "%d:%d:%s:%d:%s:%s:%d:%d:%d:%d" % [source.get_instance_id(), authored.get_instance_id(), sex, style, finish_key, transform,length,volume,head_bind,neck_bind]
		var result := _meshes.get(key) as Mesh
		if result == null:
			var started := Time.get_ticks_usec()
			result = _refine(source, authored, transform, sex, style, detail,eye_y,length,volume,head_bind,neck_bind,finish_s)
			_cold_usec += Time.get_ticks_usec() - started
			if _meshes.size() >= CACHE_LIMIT: _meshes.erase(_meshes.keys()[0])
			_meshes[key] = result
		else: _hits += 1
		var layered := not LOCKS.curves(sex,style,lock_detail).is_empty() and result != source
		var high_materials: Array[Material] = []
		for surface: int in source.get_surface_count():
			var original := authored.surface_get_material(surface) as StandardMaterial3D
			var material_key := "%d:%s:%d:%s:%s" % [original.get_instance_id() if original != null else 0, color.to_html(), style, finish_key,layered]
			var material := _materials.get(material_key) as ShaderMaterial
			if material == null:
				material = ShaderMaterial.new()
				material.shader = SHADER
				material.set_shader_parameter("authored_locks",layered)
				material.set_shader_parameter("hair_color", color * (original.albedo_color if original != null else Color.WHITE))
				if original != null:
					material.set_shader_parameter("use_texture", original.albedo_texture != null)
					material.set_shader_parameter("base_texture", original.albedo_texture)
					material.set_shader_parameter("use_normal", original.normal_enabled and original.normal_texture != null)
					material.set_shader_parameter("normal_texture", original.normal_texture)
					material.set_shader_parameter("normal_scale", minf(original.normal_scale, 0.45))
				if _materials.size() >= MATERIAL_LIMIT: _materials.erase(_materials.keys()[0])
				_materials[material_key] = material
			high_materials.append(material)
		hair.material_override = null
		hair.mesh = result
		for surface: int in high_materials.size(): hair.set_surface_override_material(surface, high_materials[surface])
		hair.set_meta(META, {"source":source, "result":result, "override":original_override, "surfaces":originals, "materials":high_materials})
	if visible_beard:
		_apply_beard(beard,skeleton,native_root,appearance,eye_y,config)
	_prune_users()

static func restore(native_root: Node3D) -> void:
	if not is_instance_valid(native_root): return
	for hair: MeshInstance3D in _finish_nodes(native_root):
		if not hair.has_meta(META): continue
		var previous: Dictionary = hair.get_meta(META)
		if hair.mesh == previous.result:
			hair.mesh = previous.source as Mesh
			hair.material_override = previous.override as Material
			for surface: int in mini(previous.surfaces.size(), hair.mesh.get_surface_count()):
				if hair.get_surface_override_material(surface) == previous.materials[surface]:
					hair.set_surface_override_material(surface, previous.surfaces[surface] as Material)
		hair.remove_meta(META)

static func release(native_root: Node3D) -> void:
	if is_instance_valid(native_root):
		restore(native_root)
		native_root.remove_meta(USER_META)
		_users.erase(native_root.get_instance_id())
	_prune_users()

static func _prune_users() -> void:
	for id: int in _users.keys():
		var node := (_users[id] as WeakRef).get_ref() as Node3D
		if not is_instance_valid(node) or not node.has_meta(USER_META): _users.erase(id)
	if _users.is_empty():
		_meshes.clear()
		_materials.clear()
		LOCKS.clear()

static func clear() -> void:
	for reference: WeakRef in _users.values():
		var node := reference.get_ref() as Node3D
		if is_instance_valid(node):
			restore(node)
			node.remove_meta(USER_META)
	_users.clear()
	_meshes.clear()
	_materials.clear()
	LOCKS.clear()
	_cold_usec = 0
	_hits = 0

static func cache_metrics() -> Dictionary:
	_prune_users()
	var bytes := 0
	var packed := 0
	var vertices := 0
	var triangles := 0
	for mesh: Mesh in _meshes.values():
		for surface: int in mesh.get_surface_count():
			var data := RenderingServer.mesh_get_surface(mesh.get_rid(),surface)
			for key: String in ["vertex_data","attribute_data","skin_data","index_data","blend_shape_data"]:
				var buffer: Variant = data.get(key)
				if buffer is PackedByteArray: packed += buffer.size()
			var arrays := mesh.surface_get_arrays(surface)
			vertices += arrays[Mesh.ARRAY_VERTEX].size()
			triangles += arrays[Mesh.ARRAY_INDEX].size() / 3
			for attribute: Variant in arrays:
				if attribute != null: bytes += attribute.to_byte_array().size()
	return {"mesh_entries":_meshes.size(), "material_entries":_materials.size(), "high_users":_users.size(), "array_bytes":bytes,"packed_buffer_bytes":packed,"vertices":vertices,"triangles":triangles,"cold_fit_usec":_cold_usec,"cache_hits":_hits,"texture_bytes_added":0}

static func _flow(point: Vector3, detail: int, style: int, sex: String) -> Vector3:
	if sex != "male" or style != 1 or detail == 0: return GROOM._hair_point(point, 0.075, detail) if detail > 0 else point
	var crown := smoothstep(0.070, 0.155, point.y)
	var fringe := smoothstep(0.005, 0.065, point.z) * crown
	if detail == 1:
		# Broad overlapping sweeps replace the high-frequency sawtooth fringe.
		var wave := 0.5 + 0.5 * sin(point.x * 47.0 + point.z * 24.0 + 0.4)
		return point + Vector3(sin(point.z * 26.0 + point.x * 12.0) * 0.0035 * crown + 0.002 * fringe,
			(0.006 + wave * 0.015) * crown - fringe * (0.003 + 0.008 * pow(sin(point.x * 58.0 + 0.8), 2.0)),
			sin(point.x * 42.0) * 0.003 * crown)
	return point + Vector3(0.010 * fringe, 0.005 * crown + 0.0025 * crown * sin(point.x * 30.0 + point.z * 20.0), -0.006 * fringe)

## Male Parted's flow at a hair finish slider position: its own Swept and
## Tousled offsets blended by HairFinish.weights.
static func _flow_finish(point: Vector3, weights: Vector2, style: int, sex: String) -> Vector3:
	var moved := point
	if weights.x > 0.0:
		moved += (_flow(point, 2, style, sex) - point) * weights.x
	if weights.y > 0.0:
		moved += (_flow(point, 1, style, sex) - point) * weights.y
	return moved

static func _jacobian_finish(point: Vector3, weights: Vector2, style: int, sex: String) -> Basis:
	var e := 0.0001
	var centre := _flow_finish(point, weights, style, sex)
	return Basis((_flow_finish(point + Vector3.RIGHT * e, weights, style, sex) - centre) / e,
		(_flow_finish(point + Vector3.UP * e, weights, style, sex) - centre) / e,
		(_flow_finish(point + Vector3.BACK * e, weights, style, sex) - centre) / e)

static func _jacobian(point: Vector3, detail: int, high: bool, style: int, sex: String) -> Basis:
	var e := 0.0001
	var centre := _flow(point, detail, style, sex) if high else GROOM._hair_point(point, 0.075, detail)
	var axes: Array[Vector3] = []
	for axis: Vector3 in [Vector3.RIGHT, Vector3.UP, Vector3.BACK]:
		axes.append(((_flow(point + axis * e, detail, style, sex) if high else GROOM._hair_point(point + axis * e, 0.075, detail)) - centre) / e)
	return Basis(axes[0], axes[1], axes[2])

static func _refine(source: Mesh, authored: Mesh, to_head: Transform3D, sex: String, style: int, detail: int, eye_y: float = 0.075, length: int = 50, volume: int = 50, head_bind: int = -1, neck_bind: int = -1, finish_s: int = -1) -> Mesh:
	if finish_s >= 0:
		return _refine_finish(source, authored, to_head, sex, style, finish_s, eye_y, length, volume, head_bind, neck_bind)
	# Unknown custom or morph channels retain authored geometry; shading still
	# improves. Production Human hair has neither, but future assets stay safe.
	if source.get_blend_shape_count() > 0: return source
	var result := ArrayMesh.new()
	var from_head := to_head.affine_inverse()
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		if source.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: return source
		for slot: int in range(Mesh.ARRAY_CUSTOM0, Mesh.ARRAY_CUSTOM3 + 1):
			if arrays[slot] != null: return source
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		var input := authored.surface_get_arrays(surface)
		var original_points: PackedVector3Array = input[Mesh.ARRAY_VERTEX]
		var original_normals: PackedVector3Array = input[Mesh.ARRAY_NORMAL]
		var original_tangents: PackedFloat32Array = input[Mesh.ARRAY_TANGENT] if input[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		if sex == "male" and style == 1 and detail > 0 and original_points.size() == points.size():
			for index: int in points.size():
				var local := to_head * original_points[index]
				var flowing := _flow(local,detail,style,sex)
				points[index] = from_head * GROOM._size_hair_point(flowing,eye_y,length,volume)
				var high_j := _jacobian(local, detail, true, style, sex)
				high_j = GROOM._size_hair_jacobian(flowing,eye_y,length,volume)*high_j
				var jacobian := from_head.basis * high_j * to_head.basis
				normals[index] = (jacobian.inverse().transposed() * original_normals[index]).normalized()
				if tangents.size() == points.size() * 4:
					var t := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
					t = (jacobian * t).normalized()
					t = (t - normals[index] * normals[index].dot(t)).normalized()
					for component: int in 3: tangents[index * 4 + component] = t[component]
		if sex == "female" and style == 3 and detail == 2:
			var groups := _updo_groups(arrays, to_head)
			for index: int in points.size():
				var group: int = groups.vertices[index]
				if group == 0: continue
				var centre: Vector3 = groups.centres[group]
				var scale := Vector3(0.92,0.85,0.86) if group == 1 else (Vector3(0.74,0.65,0.74) if group == 2 else Vector3(1.08,0.98,1.18))
				var target := Vector3(-0.014,0.216,-0.082) if group == 1 else (Vector3(0.027,0.216,-0.113) if group == 2 else centre + Vector3(0,0.001,0.001))
				var local_point := target + (to_head * points[index] - centre) * scale
				if group == 8:
					var tail:=1.0-smoothstep(0.04,0.11,local_point.y)
					var side_centre:=signf(local_point.x)*0.085
					local_point.x=lerpf(local_point.x,side_centre+(local_point.x-side_centre)*0.60,tail)
					local_point.z=lerpf(local_point.z,0.035+(local_point.z-0.035)*0.70,tail)
					local_point.y+=0.015*tail
				if group >= 3 and group != 8 and centre.y>0.13 and absf(centre.x)<0.045:
					var swept := 1.0-smoothstep(0.135,0.170,local_point.y)
					local_point += Vector3(signf(centre.x)*0.020,0.025,-0.004)*swept
				points[index] = from_head * local_point
				var j := from_head.basis * Basis.from_scale(scale) * to_head.basis
				normals[index] = (j.inverse().transposed() * normals[index]).normalized()
				if tangents.size() == points.size()*4:
					var t := Vector3(tangents[index*4],tangents[index*4+1],tangents[index*4+2])
					t = j*t
					t = (t-normals[index]*normals[index].dot(t)).normalized()
					for component: int in 3: tangents[index*4+component]=t[component]
			# The two imported central needle-bangs are separate decorative islands.
			# Swept High replaces them with the authored side-parted clumps.
			var kept:=PackedInt32Array()
			var original_indices:PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
			for triangle: int in range(0,original_indices.size(),3):
				var group:int=groups.vertices[original_indices[triangle]]
				if int(groups.sizes.get(group,0)) == 264:continue
				kept.append_array(original_indices.slice(triangle,triangle+3))
			arrays[Mesh.ARRAY_INDEX]=kept
		arrays[Mesh.ARRAY_VERTEX] = points
		arrays[Mesh.ARRAY_NORMAL] = normals
		if not tangents.is_empty(): arrays[Mesh.ARRAY_TANGENT] = tangents
		arrays = _refine_edges(arrays, to_head, 0.012)
		var lods := GROOM._lods(source,surface)
		if surface == 0:
			var layer := LOCKS.append(arrays,from_head,sex,style,detail,head_bind,neck_bind,eye_y,length,volume)
			arrays=layer.arrays
			for threshold: Variant in lods:
				var chain: PackedInt32Array=lods[threshold]
				chain.append_array(layer.added_indices)
				lods[threshold]=chain
			if sex == "female" and style == 3 and detail == 2:
				arrays = _lower_updo_fringe(arrays,to_head)
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods, source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
	return result

## _refine at a hair finish slider position s (not a saved finish): the same
## refinement with the finish continuous. Male Parted blends its flows;
## the female Buns updo regroups, its needle-bangs collapse toward their roots
## and its fringe lowers by g = min(w_swept, 1), the bangs going at g = 1 as in
## develop's Swept; the Swept or Tousled hero-lock layer grows in by min(w, 1).
static func _refine_finish(source: Mesh, authored: Mesh, to_head: Transform3D, sex: String, style: int, s: int, eye_y: float = 0.075, length: int = 50, volume: int = 50, head_bind: int = -1, neck_bind: int = -1) -> Mesh:
	if source.get_blend_shape_count() > 0: return source
	var weights := HAIR_FINISH.weights(s)
	var gather := minf(weights.x, 1.0)
	var lock_detail := 2 if s < 50 else 1
	var growth := minf(weights.x if s < 50 else weights.y, 1.0)
	if growth <= 0.0:
		lock_detail = 0
		growth = 1.0
	var updo := sex == "female" and style == 3 and gather > 0.0
	var result := ArrayMesh.new()
	var from_head := to_head.affine_inverse()
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		if source.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: return source
		for slot: int in range(Mesh.ARRAY_CUSTOM0, Mesh.ARRAY_CUSTOM3 + 1):
			if arrays[slot] != null: return source
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
		var input := authored.surface_get_arrays(surface)
		var original_points: PackedVector3Array = input[Mesh.ARRAY_VERTEX]
		var original_normals: PackedVector3Array = input[Mesh.ARRAY_NORMAL]
		if sex == "male" and style == 1 and original_points.size() == points.size():
			for index: int in points.size():
				var local := to_head * original_points[index]
				var flowing := _flow_finish(local, weights, style, sex)
				points[index] = from_head * GROOM._size_hair_point(flowing,eye_y,length,volume)
				var high_j := _jacobian_finish(local, weights, style, sex)
				high_j = GROOM._size_hair_jacobian(flowing,eye_y,length,volume)*high_j
				var jacobian := from_head.basis * high_j * to_head.basis
				normals[index] = (jacobian.inverse().transposed() * original_normals[index]).normalized()
				if tangents.size() == points.size() * 4:
					var t := Vector3(tangents[index * 4], tangents[index * 4 + 1], tangents[index * 4 + 2])
					t = (jacobian * t).normalized()
					t = (t - normals[index] * normals[index].dot(t)).normalized()
					for component: int in 3: tangents[index * 4 + component] = t[component]
		if updo:
			var groups := _updo_groups(arrays, to_head)
			var roots := _bang_roots(points, groups, to_head)
			for index: int in points.size():
				var group: int = groups.vertices[index]
				if group == 0: continue
				var centre: Vector3 = groups.centres[group]
				var local := to_head * points[index]
				if roots.has(group) and gather < 1.0:
					# A needle-bang collapses toward its root; at gather 1 it is
					# regrouped as develop's Swept does and its triangles go.
					points[index] = from_head * local.lerp(roots[group], gather)
					continue
				var scale := Vector3(0.92,0.85,0.86) if group == 1 else (Vector3(0.74,0.65,0.74) if group == 2 else Vector3(1.08,0.98,1.18))
				var target := Vector3(-0.014,0.216,-0.082) if group == 1 else (Vector3(0.027,0.216,-0.113) if group == 2 else centre + Vector3(0,0.001,0.001))
				var local_point := target + (local - centre) * scale
				if group == 8:
					var tail:=1.0-smoothstep(0.04,0.11,local_point.y)
					var side_centre:=signf(local_point.x)*0.085
					local_point.x=lerpf(local_point.x,side_centre+(local_point.x-side_centre)*0.60,tail)
					local_point.z=lerpf(local_point.z,0.035+(local_point.z-0.035)*0.70,tail)
					local_point.y+=0.015*tail
				if group >= 3 and group != 8 and centre.y>0.13 and absf(centre.x)<0.045:
					var swept := 1.0-smoothstep(0.135,0.170,local_point.y)
					local_point += Vector3(signf(centre.x)*0.020,0.025,-0.004)*swept
				points[index] = from_head * local.lerp(local_point, gather)
				var j := from_head.basis * GROOM._lerp_basis(Basis.IDENTITY, Basis.from_scale(scale), gather) * to_head.basis
				normals[index] = (j.inverse().transposed() * normals[index]).normalized()
				if tangents.size() == points.size()*4:
					var t := Vector3(tangents[index*4],tangents[index*4+1],tangents[index*4+2])
					t = j*t
					t = (t-normals[index]*normals[index].dot(t)).normalized()
					for component: int in 3: tangents[index*4+component]=t[component]
			if gather >= 1.0:
				var kept:=PackedInt32Array()
				var original_indices:PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
				for triangle: int in range(0,original_indices.size(),3):
					var group:int=groups.vertices[original_indices[triangle]]
					if int(groups.sizes.get(group,0)) == NEEDLE_BANG_SIZE:continue
					kept.append_array(original_indices.slice(triangle,triangle+3))
				arrays[Mesh.ARRAY_INDEX]=kept
		arrays[Mesh.ARRAY_VERTEX] = points
		arrays[Mesh.ARRAY_NORMAL] = normals
		if not tangents.is_empty(): arrays[Mesh.ARRAY_TANGENT] = tangents
		arrays = _refine_edges(arrays, to_head, 0.012)
		var lods := GROOM._lods(source,surface)
		if surface == 0:
			var layer := LOCKS.append(arrays,from_head,sex,style,lock_detail,head_bind,neck_bind,eye_y,length,volume,growth)
			arrays=layer.arrays
			for threshold: Variant in lods:
				var chain: PackedInt32Array=lods[threshold]
				chain.append_array(layer.added_indices)
				lods[threshold]=chain
			if updo:
				arrays = _lower_updo_fringe(arrays,to_head,gather)
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods, source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
	return result

## Each central needle-bang's root (head space): the mean of its highest fifth.
static func _bang_roots(points: PackedVector3Array, groups: Dictionary, to_head: Transform3D) -> Dictionary:
	var spans: Dictionary = {}
	for index: int in points.size():
		var group: int = groups.vertices[index]
		if group == 0 or int(groups.sizes.get(group, 0)) != NEEDLE_BANG_SIZE: continue
		var y := (to_head * points[index]).y
		var span: Vector2 = spans.get(group, Vector2(y, y))
		spans[group] = Vector2(minf(span.x, y), maxf(span.y, y))
	var sums: Dictionary = {}
	for index: int in points.size():
		var group: int = groups.vertices[index]
		if not spans.has(group): continue
		var local := to_head * points[index]
		var span: Vector2 = spans[group]
		if local.y < span.y - 0.2 * (span.y - span.x): continue
		var entry: Array = sums.get(group, [Vector3.ZERO, 0])
		sums[group] = [entry[0] + local, entry[1] + 1]
	var roots: Dictionary = {}
	for group: Variant in sums:
		roots[group] = (sums[group][0] as Vector3) / float(maxi(int(sums[group][1]), 1))
	return roots

static func _updo_fringe_point(point: Vector3) -> Vector3:
	var front := smoothstep(0.068,0.085,point.z)
	var centre := 1.0-smoothstep(0.055,0.085,absf(point.x))
	var height := smoothstep(0.075,0.135,point.y)*(1.0-smoothstep(0.155,0.175,point.y))
	return point+Vector3(0,-0.018,0.003)*front*centre*height

## Lower only the existing swept fringe islands after edge refinement. This
## keeps all topology, crown, buns, hanging strands and scalp roots intact.
## `amount` scales the lowering (a hair finish slider position; 1 = Swept).
static func _lower_updo_fringe(arrays: Array, to_head: Transform3D, amount: float = 1.0) -> Array:
	var groups := _updo_groups(arrays,to_head)
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
	var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT] if arrays[Mesh.ARRAY_TANGENT] != null else PackedFloat32Array()
	var from_head := to_head.affine_inverse()
	var e := 0.0001
	for index: int in points.size():
		var group: int = groups.vertices[index]
		if group < 3 or group == 8 or colors[index].r>0.5: continue
		var local := to_head*points[index]
		var moved := _updo_fringe_point(local) if amount >= 1.0 else _updo_fringe_scaled(local, amount)
		if moved == local: continue
		var j := Basis((_updo_fringe_point(local+Vector3.RIGHT*e)-moved)/e,
			(_updo_fringe_point(local+Vector3.UP*e)-moved)/e,
			(_updo_fringe_point(local+Vector3.BACK*e)-moved)/e)
		if amount < 1.0:
			j = Basis((_updo_fringe_scaled(local+Vector3.RIGHT*e, amount)-moved)/e,
				(_updo_fringe_scaled(local+Vector3.UP*e, amount)-moved)/e,
				(_updo_fringe_scaled(local+Vector3.BACK*e, amount)-moved)/e)
		j = from_head.basis*j*to_head.basis
		points[index] = from_head*moved
		normals[index] = (j.inverse().transposed()*normals[index]).normalized()
		if tangents.size() == points.size()*4:
			var t := j*Vector3(tangents[index*4],tangents[index*4+1],tangents[index*4+2])
			t = (t-normals[index]*normals[index].dot(t)).normalized()
			for component: int in 3: tangents[index*4+component]=t[component]
	arrays[Mesh.ARRAY_VERTEX]=points
	arrays[Mesh.ARRAY_NORMAL]=normals
	if not tangents.is_empty(): arrays[Mesh.ARRAY_TANGENT]=tangents
	return arrays

static func _updo_fringe_scaled(point: Vector3, amount: float) -> Vector3:
	return point + (_updo_fringe_point(point) - point) * amount

static func _updo_groups(arrays: Array, to_head: Transform3D) -> Dictionary:
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var parents := PackedInt32Array()
	parents.resize(points.size())
	var ranks := PackedByteArray()
	ranks.resize(points.size())
	var weld: Dictionary = {}
	for index: int in points.size():
		var key := Vector3i((points[index]*100000.0).round())
		parents[index] = int(weld.get(key,index))
		weld[key] = parents[index]
	for corner: int in range(0,indices.size(),3):
		var first := GROOM._component_root(parents,indices[corner])
		for offset: int in [1,2]:
			var second := GROOM._component_root(parents,indices[corner+offset])
			if first == second: continue
			if ranks[first] < ranks[second]:
				parents[first]=second
				first=second
			else:
				parents[second]=first
				if ranks[first]==ranks[second]:ranks[first]+=1
	var bounds: Dictionary = {}
	for index: int in points.size():
		var component := GROOM._component_root(parents,index)
		var point := to_head*points[index]
		var box: Dictionary = bounds.get(component,{"low":point,"high":point,"sum":Vector3.ZERO,"count":0})
		box.low=(box.low as Vector3).min(point)
		box.high=(box.high as Vector3).max(point)
		box.sum+=point
		box.count+=1
		bounds[component]=box
	var selected: Dictionary={}
	var centres: Dictionary={}
	var sizes: Dictionary={}
	var next:=3
	for component: int in bounds:
		var box: Dictionary=bounds[component]
		var centre: Vector3=box.sum/float(box.count)
		var group:=0
		if box.count>500 and box.low.y>0.17 and box.high.z< -0.025:
			group=1 if centre.x<0 else 2
		elif box.count>=600 and box.count<2000 and box.low.y<0.02 and box.high.z>0.05:
			group=8
		elif box.count<600 and box.low.y>0.04 and box.high.z>0.065:
			group=next
			next+=1
		if group>0:
			selected[component]=group
			centres[group]=centre
			sizes[group]=box.count
	var vertices:=PackedInt32Array()
	vertices.resize(points.size())
	for index: int in points.size(): vertices[index]=int(selected.get(GROOM._component_root(parents,index),0))
	return {"vertices":vertices,"centres":centres,"sizes":sizes}

static func _apply_beard(beard: MeshInstance3D, skeleton: Skeleton3D, root: Node3D, appearance: Dictionary, eye_y: float, config: Dictionary = {}) -> void:
	var previous: Dictionary=beard.get_meta(META,{})
	var source:=beard.mesh
	var original:=beard.material_override as ShaderMaterial
	var originals: Array[Material]=[]
	if not previous.is_empty() and beard.mesh==previous.result:
		source=previous.source
		original=previous.override as ShaderMaterial
		originals.assign(previous.surfaces)
	else:
		for surface: int in source.get_surface_count(): originals.append(beard.get_surface_override_material(surface))
	if original==null:return
	var to_head:=skeleton.get_bone_global_rest(skeleton.find_bone("Head")).affine_inverse()*GROOM._to_root(skeleton,root).affine_inverse()*GROOM._to_root(beard,root)
	var key:="beard:%d:%s" % [source.get_instance_id(),to_head]
	var result:=_meshes.get(key) as Mesh
	if result==null:
		var start:=Time.get_ticks_usec()
		result=_refine_beard(source,to_head,eye_y)
		_cold_usec+=Time.get_ticks_usec()-start
		if _meshes.size()>=CACHE_LIMIT:_meshes.erase(_meshes.keys()[0])
		_meshes[key]=result
	var color:=AppearanceVariants.hair_color(int(appearance.get("hair",0)))
	if bool(COLOURS.hair(appearance, config).custom):
		color = COLOURS.hair_dye(appearance, config, "B2", clampi(int(appearance.get("facial_hair", 0)), 0, 5))
	var material_key:="beard:%d:%s" % [original.get_instance_id(),color.to_html()]
	var material:=_materials.get(material_key) as ShaderMaterial
	if material==null:
		material=original.duplicate() as ShaderMaterial
		material.set_shader_parameter("finish_detail",1.0)
		material.set_shader_parameter("hair_color",color)
		if _materials.size()>=MATERIAL_LIMIT:_materials.erase(_materials.keys()[0])
		_materials[material_key]=material
	beard.mesh=result
	beard.material_override=material
	var materials: Array[Material]=[]
	for surface: int in result.get_surface_count(): materials.append(material)
	beard.set_meta(META,{"source":source,"result":result,"override":original,"surfaces":originals,"materials":materials})

static func _refine_beard(source: Mesh, to_head: Transform3D, eye_y: float) -> Mesh:
	if source.get_blend_shape_count()>0:return source
	var result:=ArrayMesh.new()
	var from_head:=to_head.affine_inverse()
	for surface: int in source.get_surface_count():
		var arrays:=source.surface_get_arrays(surface).duplicate(true)
		arrays=_refine_edges(arrays,to_head,0.007)
		var points:PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
		var normals:PackedVector3Array=arrays[Mesh.ARRAY_NORMAL]
		var uv:PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV2]
		for index: int in points.size():
			var side:=signf(uv[index].x)*smoothstep(0.012,0.045,absf(uv[index].x))
			var growth:=uv[index].x-side*0.32*(uv[index].y-eye_y+0.082)
			var relief:=0.00028*(0.5+0.5*cos(growth*540.0+sin(uv[index].y*83.0)*1.4+sin(growth*230.0)*0.6))
			points[index]+=normals[index]*relief
		arrays[Mesh.ARRAY_VERTEX]=points
		result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,[],GROOM._lods(source,surface),source.surface_get_format(surface)&Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface,source.surface_get_material(surface))
	return result

static func _edge(a: int, b: int) -> Vector2i:
	return Vector2i(mini(a,b),maxi(a,b))

static func _refine_edges(arrays: Array, to_head: Transform3D, threshold: float) -> Array:
	var p: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var n: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if indices.is_empty() or n.size() != p.size(): return arrays
	var influences: int = arrays[Mesh.ARRAY_BONES].size() / p.size() if arrays[Mesh.ARRAY_BONES] != null else 0
	var edges: Dictionary = {}
	for corner: int in range(0,indices.size(),3):
		for pair: Vector2i in [Vector2i(0,1),Vector2i(1,2),Vector2i(2,0)]:
			var a := indices[corner + pair.x]
			var b := indices[corner + pair.y]
			var key := _edge(a,b)
			if edges.has(key) or edges.size() >= 1600: continue
			if (to_head.basis * (p[b] - p[a])).length() >= threshold: edges[key] = p.size() + edges.size()
	var output := PackedInt32Array()
	for corner: int in range(0,indices.size(),3):
		var a := indices[corner]
		var b := indices[corner+1]
		var c := indices[corner+2]
		var ab := int(edges.get(_edge(a,b),-1))
		var bc := int(edges.get(_edge(b,c),-1))
		var ca := int(edges.get(_edge(c,a),-1))
		var mask := (1 if ab >= 0 else 0) | (2 if bc >= 0 else 0) | (4 if ca >= 0 else 0)
		match mask:
			0: output.append_array(PackedInt32Array([a,b,c]))
			1: output.append_array(PackedInt32Array([a,ab,c,ab,b,c]))
			2: output.append_array(PackedInt32Array([a,b,bc,a,bc,c]))
			4: output.append_array(PackedInt32Array([a,b,ca,b,c,ca]))
			3: output.append_array(PackedInt32Array([a,ab,c,ab,bc,c,ab,b,bc]))
			5: output.append_array(PackedInt32Array([a,ab,ca,ab,b,c,ab,c,ca]))
			6: output.append_array(PackedInt32Array([a,b,ca,b,bc,ca,bc,c,ca]))
			7: output.append_array(PackedInt32Array([a,ab,ca,ab,b,bc,ca,bc,c,ab,bc,ca]))
	var normals_to_head := to_head.basis.inverse().transposed()
	for key: Vector2i in edges:
		var a := key.x
		var b := key.y
		# Cubic PN edge midpoint: endpoint normals bend the edge continuously.
		# Bounded at 1.2 mm so imported skull/helmet clearance stays conservative.
		var hp := to_head*p[a]
		var hq := to_head*p[b]
		var na := (normals_to_head*n[a]).normalized()
		var nb := (normals_to_head*n[b]).normalized()
		var delta := -(na * (hq-hp).dot(na) + nb * (hp-hq).dot(nb)) * 0.125
		delta = delta.limit_length(0.0012) if na.dot(nb) > 0.45 else Vector3.ZERO
		p.append((p[a]+p[b])*0.5 + to_head.basis.inverse()*delta)
		n.append((n[a]+n[b]).normalized())
		for slot: int in [Mesh.ARRAY_TEX_UV,Mesh.ARRAY_TEX_UV2,Mesh.ARRAY_COLOR]:
			if arrays[slot] != null:
				var attribute: Variant = arrays[slot]
				attribute.append((attribute[a]+attribute[b])*0.5)
				arrays[slot]=attribute
		if arrays[Mesh.ARRAY_TANGENT] != null:
			var t: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
			var tangent := (Vector3(t[a*4],t[a*4+1],t[a*4+2]) + Vector3(t[b*4],t[b*4+1],t[b*4+2])).normalized()
			tangent=(tangent-n[n.size()-1]*n[n.size()-1].dot(tangent)).normalized()
			t.append_array(PackedFloat32Array([tangent.x,tangent.y,tangent.z,t[a*4+3]]))
			arrays[Mesh.ARRAY_TANGENT]=t
		if arrays[Mesh.ARRAY_BONES] != null:
			_append_skin(arrays,a,b,influences)
	arrays[Mesh.ARRAY_VERTEX]=p
	arrays[Mesh.ARRAY_NORMAL]=n
	arrays[Mesh.ARRAY_INDEX]=output
	return arrays

static func _append_skin(arrays: Array, a: int, b: int, influences: int) -> void:
	var bones: PackedInt32Array=arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array=arrays[Mesh.ARRAY_WEIGHTS]
	var combined: Dictionary={}
	for index: int in [a,b]:
		for slot: int in influences:
			var offset := index*influences+slot
			if weights[offset]>0.0: combined[bones[offset]]=float(combined.get(bones[offset],0.0))+weights[offset]*0.5
	var joints: Array=combined.keys()
	joints.sort_custom(func(first: int,second: int)->bool: return combined[first]>combined[second])
	var total:=0.0
	for slot: int in mini(influences,joints.size()): total+=float(combined[joints[slot]])
	for slot: int in influences:
		bones.append(int(joints[slot]) if slot<joints.size() else 0)
		weights.append(float(combined[joints[slot]])/maxf(total,0.00001) if slot<joints.size() else 0.0)
	arrays[Mesh.ARRAY_BONES]=bones
	arrays[Mesh.ARRAY_WEIGHTS]=weights

extends RefCounted
## Reconstruct original sampling surfaces without changing rendered mesh resources.
const KEY := "rabbitlands_surface_partition_v1"

static func _integer(value: Variant, minimum: int, maximum: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) \
		and float(value) == float(int(value)) and int(value) >= minimum and int(value) <= maximum

static func _triangle_count(surface: Dictionary) -> int:
	var arrays: Array = surface.arrays
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
	return (indices.size() if not indices.is_empty() else vertices.size()) / 3

static func _ids(record: Dictionary, count: int) -> Dictionary:
	var values: Variant = record.get("selected_triangles")
	if not values is Array and not values is PackedInt32Array:
		return {"errors":["Partition triangle IDs are missing"]}
	var ids := PackedInt32Array()
	var previous := -1
	for value: Variant in values:
		if not (value is int or value is float) or not is_finite(float(value)) \
				or float(value) != float(int(value)) or int(value) <= previous or int(value) >= count:
			return {"errors":["Partition triangle IDs must be sorted, unique and in range"]}
		ids.append(int(value)); previous = int(value)
	return {"ids":ids,"errors":[]}

static func _reference_surface(surface: Dictionary, record: Dictionary) -> Dictionary:
	if not record.has("reference_skin"):
		return {"surface":surface,"errors":[]}
	var reference: Variant = record.reference_skin
	if not reference is Dictionary:
		return {"errors":["Partition reference skin must be a record"]}
	var slots := 0
	match str(reference.get("layout","")):
		"godot-four-influences-u16-v1": slots = 4
		"godot-eight-influences-u16-v1": slots = 8
		_: return {"errors":["Partition reference skin layout is unsupported"]}
	var source: MeshInstance3D = surface.mesh
	var skeleton := source.get_node_or_null(source.skeleton) as Skeleton3D
	var names: Variant = reference.get("bind_names")
	var encoded: Variant = reference.get("skin_hex")
	var arrays: Array = surface.arrays
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var expected := vertices.size() * slots * 4
	if source.skin == null or skeleton == null or not names is Array \
			or names.size() != source.skin.get_bind_count() or not encoded is String \
			or encoded.length() != expected * 2 or encoded.length() > 32 * 1024 * 1024 \
			or not encoded.is_valid_hex_number(false) or encoded.begins_with("-") or encoded.begins_with("+"):
		return {"errors":["Partition reference skin has invalid storage or bindings"]}
	for bind in names.size():
		var bone := skeleton.find_bone(source.skin.get_bind_name(bind))
		if bone < 0: bone = source.skin.get_bind_bone(bind)
		if bone < 0 or bone >= skeleton.get_bone_count() or skeleton.get_bone_name(bone) != str(names[bind]):
			return {"errors":["Partition reference skin binding names differ"]}
	var packed: PackedByteArray = encoded.hex_decode()
	if packed.size() != expected:
		return {"errors":["Partition reference skin byte count differs"]}
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	bones.resize(vertices.size() * slots); weights.resize(vertices.size() * slots)
	for vertex in vertices.size():
		for slot in slots:
			var offset := vertex * slots * 4
			var bind := packed.decode_u16(offset + slot * 2)
			if bind >= names.size(): return {"errors":["Partition reference skin contains an invalid joint"]}
			bones[vertex * slots + slot] = bind
			# surface_get_arrays returns float32-normalized GPU weights. Keep
			# this conversion in PackedFloat32Array before legacy ash posing.
			weights[vertex * slots + slot] = float(packed.decode_u16(offset + slots * 2 + slot * 2)) / 65535.0
	var copy := surface.duplicate(false)
	var sampling_arrays := arrays.duplicate(false)
	sampling_arrays[Mesh.ARRAY_BONES] = bones
	sampling_arrays[Mesh.ARRAY_WEIGHTS] = weights
	copy.arrays = sampling_arrays
	return {"surface":copy,"errors":[]}

static func virtual_surfaces(actual: Array[Dictionary]) -> Dictionary:
	var groups := {}
	var info := []
	var errors: Array[String] = []
	for surface: Dictionary in actual:
		var source: MeshInstance3D = surface.mesh
		var extras: Variant = source.mesh.get_meta("extras",{})
		var record: Variant = extras.get(KEY) if extras is Dictionary else null
		if record == null:
			info.append({}); continue
		if not record is Dictionary or not _integer(record.get("surface"),0,source.mesh.get_surface_count()-1):
			errors.append("Partition metadata must identify its surface"); info.append({}); continue
		if int(surface.get("surface",0)) != int(record.surface):
			info.append({}); continue
		if not record.get("group") is String or str(record.group).is_empty() \
				or record.get("role","") not in ["remainder","selected"] \
				or not _integer(record.get("source_vertices"),1,2000000) \
				or not _integer(record.get("source_triangles"),1,2000000):
			errors.append("Partition group or role is invalid"); info.append({}); continue
		var scope: Node = source.get_node_or_null(source.skeleton) as Skeleton3D
		if scope == null: scope = source.get_parent()
		var key := str(record.group)+"@"+str(scope.get_instance_id())
		if not groups.has(key): groups[key] = []
		groups[key].append({"surface":surface,"record":record})
		info.append({"key":key,"role":record.role})
	var virtual := {}
	for key: String in groups:
		var members: Array = groups[key]
		var remainders: Array = members.filter(func(member: Dictionary) -> bool: return member.record.role == "remainder")
		if remainders.size() != 1:
			errors.append("Partition group must have one remainder anchor"); continue
		var anchor: Dictionary = remainders[0]
		var vertices := int(anchor.record.get("source_vertices",0))
		var triangles := int(anchor.record.get("source_triangles",0))
		if vertices <= 0 or triangles <= 0 or triangles > 2000000:
			errors.append("Partition original surface counts are invalid"); continue
		var union := _ids(anchor.record,triangles)
		if not union.errors.is_empty(): errors.append_array(union.errors); continue
		if _triangle_count(anchor.surface) != triangles - union.ids.size():
			errors.append("Partition remainder triangle count differs"); continue
		var selected := {}
		var remainder := _reference_surface(anchor.surface,anchor.record)
		if not remainder.errors.is_empty(): errors.append_array(remainder.errors); continue
		for member: Dictionary in members:
			if int(member.record.get("source_vertices",0)) != vertices or int(member.record.get("source_triangles",0)) != triangles:
				errors.append("Partition source counts disagree"); continue
			if member.record.role == "remainder": continue
			var ids := _ids(member.record,triangles)
			if not ids.errors.is_empty(): errors.append_array(ids.errors); continue
			if ids.ids.size() != _triangle_count(member.surface):
				errors.append("Partition selected triangle count differs"); continue
			var restored := _reference_surface(member.surface,member.record)
			if not restored.errors.is_empty(): errors.append_array(restored.errors); continue
			for index in ids.ids.size():
				var original: int = ids.ids[index]
				if selected.has(original): errors.append("Partition selected triangles overlap")
				selected[original] = {"surface":restored.surface,"triangle":index}
		if selected.size() != union.ids.size():
			errors.append("Partition selected triangle union differs"); continue
		for original: int in union.ids:
			if not selected.has(original): errors.append("Partition selected triangle union differs")
		var combined: Dictionary = anchor.surface.duplicate(false)
		combined.triangles = triangles
		combined.partition = {"selected":selected,"ids":union.ids,"remainder":remainder.surface}
		combined.vertices = vertices
		virtual[key] = combined
	if not errors.is_empty(): return {"surfaces":[],"total_vertices":0,"errors":errors}
	var surfaces: Array[Dictionary] = []
	var total := 0
	for index in actual.size():
		var record: Dictionary = info[index]
		if record.get("role","") == "selected": continue
		var surface: Dictionary = virtual[record.key].duplicate(false) if record.has("key") else actual[index].duplicate(false)
		var count := int(surface.vertices) if surface.has("vertices") else (surface.arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		total += count
		surface.end = total
		if not surface.has("triangles"): surface.triangles = _triangle_count(surface)
		surfaces.append(surface)
	return {"surfaces":surfaces,"total_vertices":total,"errors":[]}

static func triangle(surface: Dictionary, original: int) -> Dictionary:
	if not surface.has("partition"): return {"surface":surface,"triangle":original}
	var partition: Dictionary = surface.partition
	if partition.selected.has(original): return partition.selected[original]
	var ids: PackedInt32Array = partition.ids
	return {"surface":partition.remainder,"triangle":original - ids.bsearch(original)}

extends RefCounted
## A corrective-data pilot may rigidly bind static scenery on the wild rig.
## Mount locomotion instead needs the original skin. Restore its exact packed
## skin bytes on a private mesh, leaving vertex/normal/UV/material bytes intact.
const KEY := "rabbitlands_mount_skin_v1"
const LAYOUT := "godot-four-influences-u16-v1"

static func for_mount(source: Mesh, skin: Skin, skeleton: Skeleton3D) -> Dictionary:
	var extras: Variant = source.get_meta("extras",{})
	if not extras is Dictionary or not extras.has(KEY): return {"mesh":source,"errors":[]}
	return for_record(source,skin,skeleton,extras[KEY])

static func for_secondary(source: Mesh, skin: Skin, skeleton: Skeleton3D) -> Dictionary:
	var extras: Variant = source.get_meta("extras",{})
	if extras is Dictionary:
		var partition: Variant = extras.get("rabbitlands_surface_partition_v1",{})
		if partition is Dictionary and partition.has("reference_skin"):
			return for_record(source,skin,skeleton,partition.reference_skin)
	return for_mount(source,skin,skeleton)

static func for_record(source: Mesh, skin: Skin, skeleton: Skeleton3D, record: Variant) -> Dictionary:
	var influences := 0
	if record is Dictionary:
		influences = {LAYOUT:4,"godot-eight-influences-u16-v1":8}.get(record.get("layout",""),0)
	if not source is ArrayMesh or source.get_surface_count() != 1 or source.get_blend_shape_count() != 0 \
			or influences == 0 \
			or skin == null or skeleton == null:
		return {"mesh":null,"errors":["Retained mount skin has an incompatible mesh/layout"]}
	var names: Variant = record.get("bind_names")
	var encoded: Variant = record.get("skin_hex")
	if not names is Array or names.size() != skin.get_bind_count() or not encoded is String \
			or encoded.length() == 0 or encoded.length() > 4 * 1024 * 1024 or encoded.length() % 2 != 0:
		return {"mesh":null,"errors":["Retained mount skin has invalid bindings/storage"]}
	for bind in skin.get_bind_count():
		var bone := skeleton.find_bone(skin.get_bind_name(bind))
		if bone < 0: bone = skin.get_bind_bone(bind)
		if bone < 0 or bone >= skeleton.get_bone_count() or skeleton.get_bone_name(bone) != str(names[bind]):
			return {"mesh":null,"errors":["Retained mount skin binding names differ"]}
	var original := encoded.hex_decode() as PackedByteArray
	var surface := RenderingServer.mesh_get_surface(source.get_rid(),0)
	var vertices := int(surface.get("vertex_count",0))
	if vertices <= 0 or original.size() != vertices * influences * 4 \
			or ((int(surface.get("format",0)) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS) != 0) != (influences == 8) \
			or (surface.get("skin_data",PackedByteArray()) as PackedByteArray).size() != original.size():
		return {"mesh":null,"errors":["Retained mount skin vertex/format size differs"]}
	for vertex in vertices:
		for slot in influences:
			if original.decode_u16(vertex*influences*4+slot*2) >= names.size():
				return {"mesh":null,"errors":["Retained mount skin contains an invalid joint"]}
	if surface.skin_data == original: return {"mesh":source,"errors":[]}
	# Use the engine's serialized surface representation. Updating only the GPU
	# region leaves the CPU arrays stale on some rendering backends; the mount
	# adapter and coat masks both read those arrays during configuration.
	var surfaces: Array = source.get("_surfaces").duplicate(true)
	surfaces[0].skin_data = original
	# The rigid shell's culling boxes belonged only to the root. Rebuild them
	# for the restored influences, including a later return to the original coat.
	var points: PackedVector3Array = source.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var boxes: Array[AABB] = []
	for bind in names.size(): boxes.append(AABB(Vector3.ZERO,-Vector3.ONE))
	for vertex in vertices:
		for slot in influences:
			if original.decode_u16(vertex*influences*4+influences*2+slot*2) == 0: continue
			var bind := original.decode_u16(vertex*influences*4+slot*2)
			boxes[bind] = (AABB(points[vertex],Vector3.ONE * .00001) if boxes[bind].size.x < 0
				else boxes[bind].expand(points[vertex]))
	surfaces[0].bone_aabbs = boxes
	var copy := ArrayMesh.new()
	copy.set("_surfaces",surfaces)
	for key: StringName in source.get_meta_list(): copy.set_meta(key,source.get_meta(key))
	copy.resource_name = source.resource_name
	copy.custom_aabb = source.custom_aabb
	if RenderingServer.mesh_get_surface(copy.get_rid(),0).get("skin_data") != original:
		return {"mesh":null,"errors":["Retained mount skin could not be restored"]}
	return {"mesh":copy,"errors":[]}

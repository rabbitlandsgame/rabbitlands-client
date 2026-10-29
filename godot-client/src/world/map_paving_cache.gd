extends RefCounted
## Bake the existing kit-paving coverage outside play. Runtime binds the raw
## load's current materials to private native meshes without reading GPU data.
const Faces := preload("res://src/world/map_collision_cache.gd")
const Sources := preload("res://src/world/map_geometry_texture_sources.gd")
const Ground := preload("res://src/world/look/look_ground.gd")
const Profile := preload("res://src/world/look/look_profile.gd")
const Installed := preload("res://src/world/installed_world_cache.gd")
const POLICY := "map-paving-coverage-v1"
const DIRECTORY := "user://map-paving-cache"
const VERSION := 1
const MAX_MESHES := 4096
const MAX_SURFACES := 256
const MAX_VERTICES := 4000000
const MAX_BLOB_BYTES := 67108864
const MAX_TOTAL_BYTES := 134217728

static func detailed_diagnostics() -> bool:
	return OS.get_environment("ELORIA_PAVING_DIAGNOSTICS") == "1"

static func policy() -> String:
	return Faces._digest([POLICY,VERSION,Faces.policy(),Profile.KIT_PAVING_CHUNK_METRES,Profile.KIT_PAVING_JOIN_METRES])

static func _root() -> String:
	return DIRECTORY.path_join(policy())

static func _entry_path(source: String) -> String:
	return _root().path_join("entries/"+Faces._digest(Faces._logical(source))+".json")

static func _owned(path: String, extension: String, root := "") -> bool:
	var directory := _root() if root.is_empty() else root
	var local := path == path.replace("\\","/").simplify_path() \
		and path.get_base_dir() == directory.path_join("entries" if extension == "json" else "blobs") \
		and path.get_extension() == extension and Faces._hash(path.get_file().get_basename())
	return local or (root.is_empty() and extension == "res" and Installed.owns_blob(path,"paving",policy(),extension))

static func _read(path: String) -> Dictionary:
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null and _owned(path,"json"): file = FileAccess.open(path+".previous",FileAccess.READ)
	if file == null or file.get_length() > Faces.MAX_METADATA_BYTES: return {}
	var value: Variant = JSON.parse_string(file.get_as_text())
	return value if value is Dictionary else {}

static func _miss(reason: String) -> Dictionary:
	return {"ok":false,"reason":reason,"error":reason,"meshes":{},"bytes":0}

static func _region(source: String) -> Dictionary:
	var manifest := Faces._read(Sources.source_path(Faces._logical(source)))
	var id := str(manifest.get("asset",{}).get("id","")).get_slice("__chunk_",0)
	if id.is_empty() or id.length() > 128: return _miss("paving_region_invalid")
	for character: String in id:
		if not character in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-": return _miss("paving_region_invalid")
	var path := Faces._logical(Profile.region_path(id))
	var actual := Sources.source_path(path)
	return {"ok":true,"id":id,"path":path,"sha256":FileAccess.get_sha256(actual) if FileAccess.file_exists(actual) else ""}

static func _qualified_inputs(source: String, inputs: Array, region: Dictionary) -> Dictionary:
	var rows: Array = inputs.duplicate(true)
	if not str(region.sha256).is_empty():
		var found := false
		for row: Variant in rows:
			if row is Dictionary and row.get("path") == region.path:
				if row.get("sha256") != region.sha256: return _miss("paving_region_changed")
				found = true
		if not found: rows.append({"path":region.path,"sha256":region.sha256})
	if not Faces._inputs(rows,Faces._logical(source)): return _miss("paving_dependency_changed")
	return {"ok":true,"inputs":rows}

static func _eligible(mesh: ArrayMesh, name: String, region: String) -> bool:
	if mesh == null or mesh.get_script() != null or mesh.has_meta(Ground.KIT_MESH_META) \
			or Ground.kind_of(name) != Ground.Kind.DECK or not Ground.is_kit_paving(name,region) \
			or mesh.get_surface_count() == 0 or mesh.get_surface_count() > MAX_SURFACES: return false
	for surface: int in mesh.get_surface_count():
		if (mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) != 0: return false
	return true

static func _signature(mesh: ArrayMesh) -> Dictionary:
	var box := mesh.get_aabb()
	var surfaces: Array = []
	for surface: int in mesh.get_surface_count():
		surfaces.append({"primitive":mesh.surface_get_primitive_type(surface),"format":mesh.surface_get_format(surface),
			"vertices":mesh.surface_get_array_len(surface),"indices":mesh.surface_get_array_index_len(surface),"name":mesh.surface_get_name(surface)})
	return {"surfaces":surfaces,"aabb":[box.position.x,box.position.y,box.position.z,box.size.x,box.size.y,box.size.z]}

static func _signature_schema(signature: Variant) -> bool:
	if not signature is Dictionary or not signature.get("surfaces") is Array \
			or signature.surfaces.is_empty() or signature.surfaces.size() > MAX_SURFACES \
			or not signature.get("aabb") is Array or signature.aabb.size() != 6: return false
	for value: Variant in signature.aabb:
		if not typeof(value) in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(value)) or absf(float(value)) > Faces.MAX_COORDINATE: return false
	var vertices := 0
	for row: Variant in signature.surfaces:
		if not row is Dictionary or not row.get("name") is String: return false
		for field: String in ["primitive","format","vertices","indices"]:
			if not typeof(row.get(field)) in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(row[field])) \
					or float(row[field]) != float(int(row[field])): return false
		if int(row.primitive) < 0 or int(row.primitive) > Mesh.PRIMITIVE_TRIANGLE_STRIP or int(row.format) <= 0 \
				or int(row.vertices) <= 0 or int(row.indices) < 0 or int(row.indices) > MAX_VERTICES*3: return false
		vertices += int(row.vertices)
		if vertices > MAX_VERTICES: return false
	return true

static func _matches(mesh: ArrayMesh, signature: Variant) -> bool:
	if mesh == null or not _signature_schema(signature) or signature.surfaces.size() != mesh.get_surface_count(): return false
	var actual := _signature(mesh)
	# JSON numbers are doubles; its decimal parser can move the last double ULP.
	# Restore native real precision before exact comparison, without a tolerance.
	var box := AABB(Vector3(signature.aabb[0],signature.aabb[1],signature.aabb[2]),
		Vector3(signature.aabb[3],signature.aabb[4],signature.aabb[5]))
	if box != mesh.get_aabb(): return false
	var vertices := 0
	for surface: int in mesh.get_surface_count():
		var row: Variant = signature.surfaces[surface]
		if not row is Dictionary: return false
		for field: String in ["primitive","format","vertices","indices"]:
			if not typeof(row.get(field)) in [TYPE_INT,TYPE_FLOAT] or int(row[field]) != int(actual.surfaces[surface][field]): return false
		if row.get("name") != actual.surfaces[surface].name: return false
		vertices += int(row.vertices)
		if vertices > MAX_VERTICES: return false
	return true

static func _bare(mesh: ArrayMesh, signature: Variant) -> bool:
	if not _matches(mesh,signature) or mesh.get_script() != null or mesh.shadow_mesh != null \
			or mesh.get_blend_shape_count() != 0 or mesh.get_meta(Ground.KIT_MESH_META,false) != true: return false
	for name: StringName in mesh.get_meta_list():
		if name != Ground.KIT_MESH_META: return false
	for surface: int in mesh.get_surface_count():
		if mesh.surface_get_material(surface) != null or (mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) == 0: return false
	return true

static func _extract(packed: PackedScene, region: String) -> Dictionary:
	if packed == null or packed.get_script() != null: return _miss("paving_scene_invalid")
	var state := packed.get_state()
	if state.get_node_count() > Faces.MAX_PATHS*3 or state.get_connection_count() != 0: return _miss("paving_scene_bounds")
	var meshes := {}
	for index: int in state.get_node_count():
		if state.get_node_instance(index) != null or not state.get_node_instance_placeholder(index).is_empty(): return _miss("paving_scene_nested")
		var properties := {}
		for property: int in state.get_node_property_count(index):
			var name := str(state.get_node_property_name(index,property))
			var value: Variant = state.get_node_property_value(index,property)
			if name == "script" and value != null: return _miss("paving_scene_script")
			properties[name] = value
		if str(state.get_node_type(index)) != "MeshInstance3D": continue
		var path := str(state.get_node_path(index)).trim_prefix("./")
		if not Faces._node_path(path): return _miss("paving_node_path")
		var mesh := properties.get("mesh") as ArrayMesh
		if properties.get("material_override") != null or properties.has("metadata/static_batch_path"): continue
		if not _eligible(mesh,str(state.get_node_name(index)),region): continue
		if meshes.has(path) or meshes.size() >= MAX_MESHES: return _miss("paving_mesh_limit")
		meshes[path] = mesh
	return {"ok":true,"meshes":meshes}

static func _write_metadata(path: String, entry: Dictionary) -> bool:
	if not _owned(path,"json") or DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK: return false
	var temporary := Faces._temporary(path)
	if not Faces._write_bytes(temporary,JSON.stringify(entry,"",true,true).to_utf8_buffer()): return false
	if not FileAccess.file_exists(path): return DirAccess.rename_absolute(temporary,path) == OK
	var previous := path+".previous"
	if FileAccess.file_exists(previous) and DirAccess.remove_absolute(previous) != OK: return false
	if DirAccess.rename_absolute(path,previous) != OK: return false
	if DirAccess.rename_absolute(temporary,path) != OK:
		DirAccess.rename_absolute(previous,path)
		return false
	DirAccess.remove_absolute(previous)
	return true

static func write_packed(packed: PackedScene, source: String, digest: String, inputs: Array) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id(): return _miss("paving_producer_requires_main")
	var logical := Faces._logical(source)
	if logical.is_empty() or not Faces._hash(digest): return _miss("paving_source_invalid")
	var region := _region(source)
	if not bool(region.ok): return region
	var qualified := _qualified_inputs(source,inputs,region)
	if not bool(qualified.ok): return qualified
	var extracted := _extract(packed,str(region.id))
	if not bool(extracted.ok): return extracted
	var descriptors := {}
	var total := 0
	var paths: Array = extracted.meshes.keys()
	paths.sort()
	for path: String in paths:
		var raw := extracted.meshes[path] as ArrayMesh
		var baked := Ground.kit_paving_mesh(raw)
		if baked == null: return _miss("paving_bake_failed")
		for surface: int in baked.get_surface_count(): baked.surface_set_material(surface,null)
		baked.set_meta(Ground.KIT_MESH_META,true)
		baked.resource_scene_unique_id = "ArrayMesh_paving"
		var signature := _signature(baked)
		if not _bare(baked,signature): return _miss("paving_bake_invalid")
		var folder := _root().path_join("blobs")
		if DirAccess.make_dir_recursive_absolute(folder) != OK: return _miss("paving_folder_unwritable")
		var temporary := Faces._temporary(folder.path_join("staging"))+".res"
		if ResourceSaver.save(baked,temporary,ResourceSaver.FLAG_COMPRESS) != OK: return _miss("paving_blob_unwritable")
		var file := FileAccess.open(temporary,FileAccess.READ)
		var bytes := int(file.get_length()) if file != null else 0
		file = null
		if bytes <= 0 or bytes > MAX_BLOB_BYTES:
			DirAccess.remove_absolute(temporary)
			return _miss("paving_blob_bounds")
		var sha := FileAccess.get_sha256(temporary)
		var blob := folder.path_join(sha+".res")
		if FileAccess.file_exists(blob):
			DirAccess.remove_absolute(temporary)
			if FileAccess.get_sha256(blob) != sha: return _miss("paving_existing_blob_changed")
		elif DirAccess.rename_absolute(temporary,blob) != OK: return _miss("paving_blob_unwritable")
		descriptors[path] = {"blob":blob,"sha256":sha,"bytes":bytes,"raw":_signature(raw),"baked":signature}
		total += bytes
	if not Faces._inputs(qualified.inputs,logical): return _miss("paving_dependency_changed")
	var entry := {"schema":VERSION,"policy":policy(),"source":logical,"source_digest":digest,
		"region":region,"inputs":qualified.inputs,"meshes":descriptors}
	if not _write_metadata(_entry_path(source),entry): return _miss("paving_metadata_unwritable")
	return {"ok":true,"entry":entry,"bytes":total,"coverage":{"mesh_paths":descriptors.size()}}

static func write_from_geometry(entry: Dictionary) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id(): return _miss("paving_producer_requires_main")
	if entry.get("kind") != "world" or not entry.get("payloads") is Dictionary \
			or entry.payloads.size() > Faces.MAX_PATHS or not Faces._geometry_blob(entry.get("primary"),str(entry.get("policy",""))) \
			or not entry.payloads.has(entry.primary): return _miss("paving_geometry_invalid")
	for path: Variant in entry.payloads:
		if not Faces._geometry_blob(path,str(entry.get("policy",""))) or not Faces._hash(entry.payloads[path]) \
				or FileAccess.get_sha256(path) != entry.payloads[path]: return _miss("paving_geometry_changed")
	if not Faces._inputs(entry.get("inputs"),str(entry.get("source",""))): return _miss("paving_dependency_changed")
	var packed := ResourceLoader.load(str(entry.primary),"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
	return write_packed(packed,str(entry.source),str(entry.get("source_digest","")),entry.inputs)

static func _entry_valid(entry: Dictionary, source: String, digest: String, verified: Dictionary = {}, diagnostics: Dictionary = {}) -> bool:
	var measure := not diagnostics.is_empty()
	var began := Time.get_ticks_usec() if measure else 0
	var valid: bool = not (int(entry.get("schema",0)) != VERSION or entry.get("policy") != policy() \
			or entry.get("source") != Faces._logical(source) or entry.get("source_digest") != digest \
			or not entry.get("meshes") is Dictionary or entry.meshes.size() > MAX_MESHES)
	if measure: diagnostics["policy_us"] = Time.get_ticks_usec()-began
	if not valid: return false
	began = Time.get_ticks_usec() if measure else 0
	var region := _region(source)
	if measure: diagnostics["region_us"] = Time.get_ticks_usec()-began
	if not bool(region.ok) or entry.get("region") != region: return false
	began = Time.get_ticks_usec() if measure else 0
	var input_diagnostics: Dictionary = {"enabled":true} if measure and bool(diagnostics.get("detailed",false)) else {}
	valid = Faces._inputs(entry.get("inputs"),str(entry.source),verified,input_diagnostics)
	if measure:
		diagnostics["inputs_us"] = Time.get_ticks_usec()-began
		diagnostics["inputs"] = input_diagnostics
	if not valid: return false
	if not str(region.sha256).is_empty():
		var declared := false
		for row: Dictionary in entry.inputs:
			if row.path == region.path and row.sha256 == region.sha256: declared = true
		if not declared: return false
	return true

static func acquire(source: String, digest: String, verified: Dictionary = {}) -> Dictionary:
	if Faces._logical(source).is_empty() or not Faces._hash(digest): return _miss("paving_source_invalid")
	var installed := Installed.entry("paving","world|"+Faces._logical(source),policy())
	if not installed.is_empty():
		var result := _acquire_entry(installed,source,digest,verified)
		if bool(result.ok): return result
	return _acquire_entry(_read(_entry_path(source)),source,digest,verified)

static func _acquire_entry(entry: Dictionary, source: String, digest: String, verified: Dictionary = {}) -> Dictionary:
	var began := Time.get_ticks_usec()
	var timings := {"pavingAcquirePolicy":Time.get_ticks_usec()-began}
	began = Time.get_ticks_usec()
	timings["pavingAcquireMetadata"] = Time.get_ticks_usec()-began
	if entry.is_empty(): return _miss("paving_not_prepared")
	var validation := {"enabled":true,"detailed":detailed_diagnostics()}
	if not _entry_valid(entry,source,digest,verified,validation): return _miss("paving_source_or_dependency_changed")
	timings["pavingAcquireEntryPolicy"] = int(validation.get("policy_us",0))
	timings["pavingAcquireRegion"] = int(validation.get("region_us",0))
	timings["pavingAcquireInputs"] = int(validation.get("inputs_us",0))
	began = Time.get_ticks_usec()
	var meshes := {}
	var total := 0
	var vertices := 0
	# Bound the entire request before loading any native Resources.
	for path: Variant in entry.meshes:
		var row: Variant = entry.meshes[path]
		if not Faces._node_path(path) or not row is Dictionary or not _owned(str(row.get("blob","")),"res") \
				or not Faces._hash(row.get("sha256")) or str(row.blob).get_file().get_basename() != row.sha256 \
				or not typeof(row.get("bytes")) in [TYPE_INT,TYPE_FLOAT] or int(row.bytes) <= 0 or int(row.bytes) > MAX_BLOB_BYTES \
				or not _signature_schema(row.get("raw")) or not _signature_schema(row.get("baked")): return _miss("paving_blob_metadata")
		total += int(row.bytes)
		for surface: Dictionary in row.baked.surfaces: vertices += int(surface.vertices)
		if total > MAX_TOTAL_BYTES or vertices > MAX_VERTICES: return _miss("paving_request_bounds")
	for path: Variant in entry.meshes:
		var row: Variant = entry.meshes[path]
		if not Faces._node_path(path) or not row is Dictionary or not _owned(str(row.get("blob","")),"res") \
				or not Faces._hash(row.get("sha256")) or str(row.blob).get_file().get_basename() != row.sha256 \
				or int(row.get("bytes",0)) <= 0 or int(row.get("bytes",0)) > MAX_BLOB_BYTES: return _miss("paving_blob_metadata")
		var file := FileAccess.open(str(row.blob),FileAccess.READ)
		if file == null or file.get_length() != int(row.bytes) or FileAccess.get_sha256(str(row.blob)) != row.sha256:
			return _miss("paving_blob_changed")
		if not ResourceLoader.get_dependencies(str(row.blob)).is_empty(): return _miss("paving_blob_dependencies")
		var mesh := ResourceLoader.load(str(row.blob),"ArrayMesh",ResourceLoader.CACHE_MODE_IGNORE_DEEP) as ArrayMesh
		if not _bare(mesh,row.get("baked")): return _miss("paving_mesh_invalid")
		meshes[path] = mesh
	timings["pavingAcquireNative"] = Time.get_ticks_usec()-began
	timings["pavingDetailedDiagnostics"] = 1 if bool(validation.detailed) else 0
	return {"ok":true,"meshes":meshes,"entry":entry,"bytes":total,"applied_root_id":0,
		"acquire_timings_us":timings,"acquire_input_diagnostics":validation.get("inputs",{})}

static func current(source: String, digest: String) -> bool:
	# Maintenance reuse validates native bytes too; no shared Resource cache.
	return bool(acquire(source,digest).ok)

static func apply(record: Dictionary, root: Node3D) -> int:
	var began := Time.get_ticks_usec()
	var timings := {}
	var validation := {"enabled":true,"detailed":detailed_diagnostics()}
	record["apply_timings_us"] = timings
	var result := _apply(record,root,timings,validation)
	timings["pavingApplyTotal"] = Time.get_ticks_usec()-began
	var fields := {"EntryPolicy":"policy_us","Region":"region_us","Inputs":"inputs_us"}
	for field: String in fields:
		timings["pavingApply"+field] = int(validation.get(fields[field],0))
	record["apply_input_diagnostics"] = validation.get("inputs",{})
	return result

static func _apply(record: Dictionary, root: Node3D, timings: Dictionary, validation: Dictionary) -> int:
	var began := Time.get_ticks_usec()
	if root == null or not bool(record.get("ok",false)) or not record.get("meshes") is Dictionary \
			or int(record.get("applied_root_id",0)) != 0: return 0
	if OS.get_thread_caller_id() != OS.get_main_thread_id() and root.is_inside_tree(): return 0
	if not Profile.enabled_for(root): return 0
	var entry: Dictionary = record.get("entry",{})
	var source := Sources.source_path(str(entry.get("source","")))
	timings["pavingApplyEligibility"] = Time.get_ticks_usec()-began
	began = Time.get_ticks_usec()
	var metadata_path := _entry_path(source)
	timings["pavingApplyPolicy"] = Time.get_ticks_usec()-began
	began = Time.get_ticks_usec()
	var same := _read(metadata_path) == entry or Installed.entry("paving","world|"+Faces._logical(source),policy()) == entry
	timings["pavingApplyMetadata"] = Time.get_ticks_usec()-began
	if not same or not _entry_valid(entry,source,str(entry.get("source_digest","")),{},validation): return 0
	began = Time.get_ticks_usec()
	var plan: Array = []
	for path: Variant in record.meshes:
		if not Faces._node_path(path) or not entry.meshes.has(path): return 0
		var node := root.get_node_or_null(NodePath(path)) as MeshInstance3D
		if node == null or node.material_override != null or node.has_meta("static_batch") \
				or not _eligible(node.mesh as ArrayMesh,str(node.name),str(entry.region.id)) \
				or not _matches(node.mesh as ArrayMesh,entry.meshes[path].raw): return 0
		var mesh := record.meshes[path] as ArrayMesh
		if not _bare(mesh,entry.meshes[path].baked): return 0
		plan.append([node,mesh])
	timings["pavingApplyPlan"] = Time.get_ticks_usec()-began
	began = Time.get_ticks_usec()
	var materials_us := 0
	var detailed := bool(validation.get("detailed",false))
	var material_getter_us := 0
	var material_rid_us := 0
	var material_setter_us := 0
	var name_us := 0
	var setter_us := 0
	for row: Array in plan:
		var node := row[0] as MeshInstance3D
		var mesh := row[1] as ArrayMesh
		var operation_began := Time.get_ticks_usec()
		for surface: int in mesh.get_surface_count():
			var surface_began := Time.get_ticks_usec()
			var current := node.mesh.surface_get_material(surface)
			material_getter_us += Time.get_ticks_usec()-surface_began
			surface_began = Time.get_ticks_usec()
			# Diagnostic-only first call: the setter invokes this lazy getter.
			if detailed and current != null: current.get_rid()
			material_rid_us += Time.get_ticks_usec()-surface_began
			surface_began = Time.get_ticks_usec()
			mesh.surface_set_material(surface,current)
			material_setter_us += Time.get_ticks_usec()-surface_began
		materials_us += Time.get_ticks_usec()-operation_began
		operation_began = Time.get_ticks_usec()
		mesh.resource_name = node.mesh.resource_name
		name_us += Time.get_ticks_usec()-operation_began
		operation_began = Time.get_ticks_usec()
		node.mesh = mesh
		setter_us += Time.get_ticks_usec()-operation_began
	var release_began := Time.get_ticks_usec()
	record["applied_root_id"] = root.get_instance_id()
	(record.meshes as Dictionary).clear()
	timings["pavingApplySurfaceMaterials"] = materials_us
	timings["pavingApplyMaterialGetter"] = material_getter_us
	timings["pavingApplyMaterialRID"] = material_rid_us
	timings["pavingApplyMaterialSetter"] = material_setter_us
	timings["pavingApplyResourceName"] = name_us
	timings["pavingApplyMeshSetter"] = setter_us
	timings["pavingApplyCarrierRelease"] = Time.get_ticks_usec()-release_began
	timings["pavingApplyAssignment"] = Time.get_ticks_usec()-began
	return plan.size()

static func _disk_files() -> PackedStringArray:
	var files := PackedStringArray()
	var directory := DirAccess.open(DIRECTORY)
	if directory == null: return files
	for name: String in directory.get_directories():
		if not Faces._hash(name): continue
		var root := DIRECTORY.path_join(name)
		for folder: String in ["entries","blobs"]:
			var child := DirAccess.open(root.path_join(folder))
			if child == null: continue
			for name_file: String in child.get_files():
				var path := root.path_join(folder).path_join(name_file)
				if _owned(path.trim_suffix(".previous"),"json" if folder == "entries" else "res",root): files.append(path)
	return files

static func total_bytes() -> int:
	var total := 0
	for path: String in _disk_files():
		var file := FileAccess.open(path,FileAccess.READ)
		if file != null: total += file.get_length()
	return total

static func clear_disk() -> int:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or Faces.busy(): return 0
	var count := 0
	for path: String in _disk_files():
		if DirAccess.remove_absolute(path) == OK: count += 1
	return count

static func prune_unreferenced() -> int:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or not Faces.busy(): return 0
	var entries := DirAccess.open(_root().path_join("entries"))
	if entries == null: return 0
	var retained := {}
	for name: String in entries.get_files():
		var path := _root().path_join("entries").path_join(name)
		if not _owned(path.trim_suffix(".previous"),"json"): continue
		var entry := _read(path)
		if entry.get("policy") != policy() or not entry.get("meshes") is Dictionary: return 0
		for row: Variant in entry.meshes.values():
			if not row is Dictionary or not _owned(str(row.get("blob","")),"res"): return 0
			retained[str(row.blob)] = true
	var blobs := DirAccess.open(_root().path_join("blobs"))
	if blobs == null: return 0
	var count := 0
	for name: String in blobs.get_files():
		var path := _root().path_join("blobs").path_join(name)
		if _owned(path,"res") and not retained.has(path) and DirAccess.remove_absolute(path) == OK: count += 1
	return count

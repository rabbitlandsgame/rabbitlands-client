extends RefCounted
## Main-thread, offline-only native geometry serialization. Source resources
## (including pooled meshes/materials) are never modified. Texture pixels are
## represented by stable material-slot bindings instead of native payloads.
const Bindings := preload("res://src/world/map_geometry_texture_bindings.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
const Installed := preload("res://src/world/installed_world_cache.gd")
const SLOT_META := &"rl_geometry_texture_slots"
const POLICY := "map-geometry-native-writer-v2"
const MAX_DEPTH := 96

var root_path := ""
## Only declared pooled prototype meshes are separate blobs. A map/asset's
## remaining geometry, shapes, materials and MultiMesh buffers stay inline in
## its primary scene, avoiding thousands of small runtime file opens.
var external_mesh_ids: Dictionary = {}
## Current write only. Callers use original instance IDs to identify canonical
## prototype meshes after serialization. Keeping old entries here would retain
## an entire continent's geometry and GPU buffers during a large cook.
var saved_resources: Dictionary = {}
var saved_paths: Dictionary = {}
var _records: Dictionary = {}
var _latest_records: Dictionary = {}
var _records_by_path: Dictionary = {}
var _visiting: Dictionary = {}
var _containers: Array = []
var _errors: Array[String] = []
var _sequence := 0
var _owner_sequence := 0
var _configure_error := ""

func configure(path: String) -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id(): return false
	root_path = ""
	_configure_error = ""
	_clear_entry()
	var normalized := path.replace("\\", "/").simplify_path().trim_suffix("/")
	if normalized != path or (not Installed.release_blob_directory(path) and (not normalized.begins_with("user://") \
			or normalized == "user:" or normalized.trim_prefix("user://").is_empty())):
		_configure_error = "geometry blob root must be an owned user:// or scoped release directory"
		return false
	var error := DirAccess.make_dir_recursive_absolute(normalized)
	if error != OK:
		_configure_error = "geometry blob directory is not writable: " + error_string(error)
		return false
	root_path = normalized
	return true

func _clear_entry() -> void:
	saved_resources.clear()
	saved_paths.clear()
	_records.clear()
	_latest_records.clear()
	_records_by_path.clear()
	_visiting.clear()
	_containers.clear()
	_errors.clear()
	_owner_sequence = 0

func _error(message: String) -> void:
	if _errors.is_empty():
		_errors.append(message)

func _failure(message: String) -> Dictionary:
	return {"ok": false, "error": message, "resource": null, "path": "",
		"sha256": "", "payloads": {}, "bindings": {}, "inputs": [],
		"policy": POLICY}

func write(source: Resource) -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return _failure("geometry serialization requires the main thread")
	_clear_entry()
	if not _configure_error.is_empty(): return _failure(_configure_error)
	if root_path.is_empty(): return _failure("geometry writer is not configured")
	if source == null: return _failure("geometry source is null")
	var native := _save_resource(source, 0, {}, true)
	if native == null or not _errors.is_empty():
		return _failure(_errors[0] if not _errors.is_empty() else "geometry serialization failed")
	var record: Dictionary = _latest_records.get(source.get_instance_id(), {})
	if record.is_empty() or str(record.path).get_base_dir() != root_path:
		return _failure("geometry primary did not produce an owned native payload")
	var closure := _closure(str(record.path), record.payloads, record.inputs)
	if not bool(closure.get("ok", false)):
		return _failure(str(closure.get("error", "geometry native closure failed")))
	# Serialize only bindings reachable through the files that actually survived
	# native saving. Files left by a failed/unused branch remain unqualified and
	# are not deleted here; a generation owner may reclaim them after publication.
	var bindings: Dictionary = {}
	for path: String in closure.payloads:
		var reached_record: Dictionary = _records_by_path.get(path, {})
		_merge_unique(bindings, reached_record.get("own_bindings", {}), "binding")
	if not _errors.is_empty(): return _failure(_errors[0])
	var inputs: Array = []
	var logical_paths: Array = record.inputs.keys()
	logical_paths.sort()
	for logical: String in logical_paths:
		inputs.append({"path": logical, "sha256": str(record.inputs[logical])})
	return {"ok": true, "resource": native, "path": str(record.path),
		"sha256": str(record.sha256), "payloads": closure.payloads,
		"bindings": bindings, "inputs": inputs, "policy": POLICY,
		"saved_files": _records_by_path.size()}

func _context() -> Dictionary:
	return {"payloads": {}, "bindings": {}, "own_bindings": {}, "inputs": {}}

func _merge_unique(destination: Dictionary, source: Dictionary, kind: String) -> void:
	for key: Variant in source:
		if destination.has(key) and destination[key] != source[key]:
			if kind in ["binding", "bindings"] and destination[key] is Dictionary and source[key] is Dictionary:
				var merged: Dictionary = Bindings.merge_origin(destination[key], source[key])
				if bool(merged.get("ok",false)):
					destination[key] = merged.origin
					continue
			_error("inconsistent " + kind + " identity: " + str(key))
			return
		destination[key] = source[key]

func _merge_record(context: Dictionary, record: Dictionary) -> void:
	for kind: String in ["payloads", "bindings", "inputs"]:
		_merge_unique(context[kind], record.get(kind, {}), kind)
	# An inline descendant belongs to the current native file, so its slots
	# are that file's own binding closure. External prototypes carry theirs in
	# their own file records instead.
	if str(record.get("path", "")).is_empty():
		_merge_unique(context.own_bindings, record.get("own_bindings", {}), "binding")

func _logical(path: String) -> String:
	if path.begins_with("godot-client/") or path.begins_with("eloria-assets/"):
		return path if path == path.replace("\\", "/").simplify_path() else ""
	return Prepared.logical_source(path)

func _add_input(context: Dictionary, path: String, expected := "") -> void:
	var logical := _logical(path)
	if logical.is_empty() or logical.begins_with("user://"):
		_error("geometry source input is not a portable authored/runtime path: " + path)
		return
	var actual := Prepared.source_path(logical)
	if actual.is_empty() or not FileAccess.file_exists(actual):
		_error("geometry source input is unavailable: " + logical)
		return
	var digest := FileAccess.get_sha256(actual)
	if not _digest(digest) or (not expected.is_empty() and digest != expected):
		_error("geometry source input changed: " + logical)
		return
	_merge_unique(context.inputs, {logical: digest}, "input")

func _binding(source: Texture2D, context: Dictionary) -> String:
	var description: Dictionary = Bindings.describe(source)
	if not bool(description.get("ok", false)):
		_error("geometry texture has no supported runtime origin: " + str(description.get("error", source.get_class())))
		return ""
	var identity := str(description.get("id", ""))
	var origin: Variant = description.get("origin")
	if not _digest(identity) or not origin is Dictionary:
		_error("geometry texture binding is not a stable data identity")
		return ""
	_merge_unique(context.bindings, {identity: origin}, "binding")
	_merge_unique(context.own_bindings, {identity: origin}, "binding")
	var inputs: Variant = description.get("inputs", [])
	if not inputs is Array:
		_error("geometry texture inputs are not an explicit source list")
		return ""
	for value: Variant in inputs:
		if not value is Dictionary or not value.get("path") is String or not _digest(value.get("sha256")):
			_error("geometry texture source input is malformed")
			return ""
		_add_input(context, str(value.path), str(value.sha256))
	return identity

func _walk(value: Variant, context: Dictionary, depth: int, owner: Dictionary) -> Variant:
	if depth > MAX_DEPTH:
		_error("geometry resource graph exceeds the supported depth")
		return null
	if value is Texture2D or value is Image:
		_error("texture/image outside a material slot in geometry resource graph")
		return null
	if value is Script or value is Node or value is Callable or value is Signal or value is RID:
		_error("executable/live object in geometry resource graph")
		return null
	if value is Resource:
		var native := _save_resource(value as Resource, depth + 1, owner)
		if native != null:
			_merge_record(context, _latest_records.get((value as Resource).get_instance_id(), {}))
		return native
	if value is Object:
		_error("non-resource object in geometry resource graph")
		return null
	if value is Array or value is Dictionary:
		for active: Variant in _containers:
			if is_same(active, value):
				_error("cyclic container in geometry resource graph")
				return null
		_containers.append(value)
		if value is Array:
			var array: Array = value.duplicate()
			for index: int in array.size():
				array[index] = _walk(array[index], context, depth + 1, owner)
			_containers.pop_back()
			return array
		var dictionary: Dictionary = value.duplicate()
		for key: Variant in dictionary:
			if key is Object or key is Callable or key is Signal or key is RID:
				_error("object key in geometry resource graph")
				break
			dictionary[key] = _walk(dictionary[key], context, depth + 1, owner)
		_containers.pop_back()
		return dictionary
	if value is String or value is StringName:
		var text := str(value).replace("\\", "/")
		if text.begins_with("user://") or text.begins_with("file://") \
				or (text.length() >= 3 and text.substr(1, 2) == ":/"):
			_error("local filesystem path in geometry resource graph")
			return ""
	if value is PackedStringArray:
		var strings: PackedStringArray = value.duplicate()
		for index: int in strings.size(): strings[index] = str(_walk(strings[index], context, depth + 1, owner))
		return strings
	return value

func _shader_inputs(code: String, original: String, context: Dictionary, visited: Dictionary) -> String:
	var includes := RegEx.new()
	if includes.compile("(?m)^[ \\t]*#include[ \\t]+\"([^\"\\n]+)\"") != OK:
		_error("geometry shader include parser failed")
		return code
	var rewritten := code
	for include: RegExMatch in includes.search_all(code):
		var uri := include.get_string(1)
		var actual := uri
		if not uri.begins_with("res://"):
			if original.is_empty() or not uri.is_relative_path() or ":" in uri:
				_error("relative geometry shader include has no source identity")
				return code
			actual = original.get_base_dir().path_join(uri).simplify_path()
		var logical := _logical(actual)
		if not logical.begins_with("godot-client/"):
			_error("geometry shader include escaped the project")
			return code
		actual = Prepared.source_path(logical)
		_add_input(context, actual)
		if not visited.has(actual):
			visited[actual] = true
			_shader_inputs(FileAccess.get_file_as_string(actual), actual, context, visited)
		rewritten = rewritten.replace("\"" + uri + "\"", "\"" + actual + "\"")
	return rewritten

func _shader_has_defaults(source: Shader) -> bool:
	# Default samplers live on Shader rather than Material, so they cannot be
	# represented by this writer's material-slot binding table.
	if source.has_method("get_default_texture_parameter_list"):
		var defaults: Variant = source.call("get_default_texture_parameter_list")
		if defaults is Array or defaults is PackedStringArray:
			for name: String in defaults:
				if source.get_default_texture_parameter(name) != null: return true
	for uniform: Dictionary in source.get_shader_uniform_list():
		if source.get_default_texture_parameter(str(uniform.get("name", ""))) != null:
			return true
	# An unbound/new Shader can have an empty reflected uniform list until a
	# rendering-server compilation has happened. Inspect sampler declarations
	# as well, rather than silently dropping its configured default textures.
	var samplers := RegEx.new()
	if samplers.compile("\\buniform[ \\t]+(?:(?:lowp|mediump|highp)[ \\t]+)?sampler[A-Za-z0-9_]*[ \\t]+([A-Za-z_][A-Za-z0-9_]*)(?:[ \\t]*\\[[ \\t]*([0-9]+)[ \\t]*\\])?") != OK:
		return true
	for sampler: RegExMatch in samplers.search_all(source.code):
		var length := maxi(1,int(sampler.get_string(2)))
		for index: int in length:
			if source.get_default_texture_parameter(sampler.get_string(1),index) != null:
				return true
	return false

func _packed_data_only(source: PackedScene) -> bool:
	var state := source.get_state()
	if state.get_connection_count() != 0:
		_error("signal connection in geometry scene")
		return false
	for index: int in state.get_node_count():
		if not state.get_node_instance_placeholder(index).is_empty():
			_error("instance placeholder in geometry scene")
			return false
		for property: int in state.get_node_property_count(index):
			if state.get_node_property_name(index, property) == &"script" \
					and state.get_node_property_value(index, property) != null:
				_error("scripted node in geometry scene")
				return false
	return true

func _stable_scene_ids(bundle: Dictionary) -> Dictionary:
	if not bundle.has("node_ids"): return bundle
	var source: Variant = bundle.node_ids
	if not source is PackedInt32Array and not source is PackedInt64Array:
		_error("unsupported generated scene editor-ID storage")
		return bundle
	var ids: Variant = source.duplicate()
	for index: int in ids.size(): ids[index] = index + 1
	# _walk already copied the dictionary; replacing this value never mutates
	# the source PackedScene. Names, hierarchy, order and NodePaths are unchanged.
	bundle.node_ids = ids
	return bundle

func _save_resource(source: Resource, depth: int, owner: Dictionary, force_file := false) -> Resource:
	if depth > MAX_DEPTH or source == null:
		_error("invalid/deep geometry resource graph")
		return null
	var identity := source.get_instance_id()
	var original := source.resource_path
	var named_shader := source is Shader and original.begins_with("res://") and original.get_extension() == "gdshader"
	var separate_file := force_file or (source is Mesh and (external_mesh_ids.has(identity) or external_mesh_ids.has(str(identity))))
	var memo_key := ("shader:" if named_shader else ("file:" if separate_file else str(owner.get("token", "missing")) + ":")) + str(identity)
	if _records.has(memo_key):
		var prior: Dictionary = _records[memo_key]
		_latest_records[identity] = prior
		saved_resources[identity] = prior.resource
		if _owned(str(prior.path)): saved_paths[identity] = prior.path
		return prior.resource as Resource
	if _visiting.has(identity) or source.get_script() != null:
		_error("cyclic/scripted geometry resource: " + source.get_class())
		return null
	if source is Texture2D or source is Image or source is Animation or source is Script:
		_error("unsupported geometry resource: " + source.get_class())
		return null
	if source is PackedScene and not _packed_data_only(source as PackedScene): return null
	_visiting[identity] = true
	var context := _context()
	if source is Shader and _shader_has_defaults(source as Shader):
		_error("Shader default texture cannot be stored in geometry payload")
		_visiting.erase(identity)
		return null
	if named_shader:
		if not FileAccess.file_exists(original) or (source as Shader).code.replace(String.chr(13), "") \
				!= FileAccess.get_file_as_string(original).replace(String.chr(13), ""):
			_error("named geometry shader differs from its source")
		else:
			_add_input(context, original)
			_shader_inputs((source as Shader).code, original, context, {original: true})
		_visiting.erase(identity)
		if not _errors.is_empty(): return null
		context.resource = source
		context.path = original
		context.sha256 = str(context.inputs.get(_logical(original), ""))
		_records[memo_key] = context
		_latest_records[identity] = context
		saved_resources[identity] = source
		return source
	var file_owner := owner
	if separate_file:
		_owner_sequence += 1
		file_owner = {"token": _owner_sequence, "sequence": 0}
	elif file_owner.is_empty():
		_error("inline geometry resource has no native file owner")
		_visiting.erase(identity)
		return null
	var native := source.duplicate(false)
	if native == null:
		_error("geometry resource cannot be duplicated: " + source.get_class())
		_visiting.erase(identity)
		return null
	file_owner.sequence = int(file_owner.sequence) + 1
	# The order is local to this native file, so a shared prototype's IDs do
	# not depend on which chunk happened to visit another material first.
	native.set("resource_scene_unique_id", "%s_geometry_%06d" % [native.get_class(), int(file_owner.sequence)])
	if native is Shader:
		(native as Shader).code = _shader_inputs((source as Shader).code, original, context, {})
	if native is Mesh:
		# Resource.duplicate(false) already copied the immutable vertex/LOD and
		# blend-shape storage. Reassigning _surfaces and blend-shape names in a
		# generic property loop is both redundant and invalid after surfaces exist.
		for surface: int in (source as Mesh).get_surface_count():
			var material := (source as Mesh).surface_get_material(surface)
			var saved: Material = null
			if material != null:
				saved = _save_resource(material, depth + 1, file_owner) as Material
				_merge_record(context, _latest_records.get(material.get_instance_id(), {}))
			(native as Mesh).surface_set_material(surface, saved)
		if source is ArrayMesh and (source as ArrayMesh).shadow_mesh != null:
			var shadow := (source as ArrayMesh).shadow_mesh
			(native as ArrayMesh).shadow_mesh = _save_resource(shadow, depth + 1, file_owner) as ArrayMesh
			_merge_record(context, _latest_records.get(shadow.get_instance_id(), {}))
	var slots: Dictionary = {}
	for property: Dictionary in native.get_property_list():
		var name := str(property.name)
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0 \
				or name in ["resource_path", "resource_name", "resource_local_to_scene", "script"]:
			continue
		if native is Mesh and name in ["_surfaces", "surfaces", "_blend_shape_names", "blend_shape_names", "shadow_mesh"]: continue
		# The file-local deterministic editor label was assigned above.
		if name == "resource_scene_unique_id":
			continue
		var value: Variant = native.get(name)
		if value is Texture2D and native is Material:
			var binding := _binding(value as Texture2D, context)
			if not binding.is_empty():
				slots[name] = binding
				native.set(name, null)
		elif value is Resource or value is Array or value is Dictionary or value is String \
				or value is StringName or value is PackedStringArray or value is Object \
				or value is Callable or value is Signal or value is RID:
			var rewritten: Variant = _walk(value, context, depth + 1, file_owner)
			if native is PackedScene and name == "_bundled" and rewritten is Dictionary:
				rewritten = _stable_scene_ids(rewritten)
			native.set(name, rewritten)
	if native is Material:
		if not slots.is_empty(): native.set_meta(SLOT_META, slots)
		elif native.has_meta(SLOT_META): native.remove_meta(SLOT_META)
	if not _errors.is_empty():
		_visiting.erase(identity)
		return null
	if not separate_file:
		context.resource = native
		context.path = ""
		context.sha256 = ""
		_records[memo_key] = context
		_latest_records[identity] = context
		saved_resources[identity] = native
		_visiting.erase(identity)
		return native
	_sequence += 1
	var extension := "scn" if native is PackedScene else "res"
	var staging := root_path.path_join("writing-%d-%06d.%s" % [OS.get_process_id(), _sequence, extension])
	# Release roots use their stable res://prepared-world namespace, identical
	# in the disposable producer and installed client. Bare relative binary
	# dependencies do not resolve against their owning resource in Godot 4.7.
	var error := ResourceSaver.save(native, staging, ResourceSaver.FLAG_COMPRESS)
	if error != OK:
		_error("geometry native save failed: " + error_string(error))
		_visiting.erase(identity)
		return null
	var digest := FileAccess.get_sha256(staging)
	var final := root_path.path_join(digest + "." + extension)
	if not _digest(digest):
		_error("geometry native payload hash failed")
	elif FileAccess.file_exists(final):
		if FileAccess.get_sha256(final) != digest:
			_error("existing geometry blob differs from its content address")
		else:
			DirAccess.remove_absolute(staging)
	else:
		var renamed := DirAccess.rename_absolute(staging, final)
		if renamed != OK: _error("geometry blob publication failed: " + error_string(renamed))
	_visiting.erase(identity)
	if not _errors.is_empty(): return null
	native.take_over_path(final)
	context.payloads[final] = digest
	context.resource = native
	context.path = final
	context.sha256 = digest
	_records[memo_key] = context
	_latest_records[identity] = context
	_records_by_path[final] = context
	saved_resources[identity] = native
	saved_paths[identity] = final
	return native

static func _digest(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

func _owned(path: String) -> bool:
	return path == path.replace("\\", "/").simplify_path() \
		and path.get_base_dir() == root_path and path.get_extension() in ["res", "scn"] \
		and _digest(path.get_file().get_basename())

func _dependency(value: String, owner_path := "") -> String:
	var path := ""
	for part: String in value.split("::"):
		if part.begins_with("res://") or part.begins_with("user://"):
			if not path.is_empty(): return ""
			path = part
		elif not owner_path.is_empty() and part.is_relative_path() and not part.get_extension().is_empty() \
				and not ":" in part and not "\\" in part:
			if not path.is_empty(): return ""
			path = owner_path.get_base_dir().path_join(part).simplify_path()
	return path if path == path.replace("\\", "/").simplify_path() else ""

func _closure(primary: String, known: Dictionary, inputs: Dictionary) -> Dictionary:
	var pending: Array[String] = [primary]
	var reached: Dictionary = {}
	while not pending.is_empty():
		var path: String = pending.pop_back()
		if reached.has(path): continue
		if not _owned(path) or not known.has(path) or FileAccess.get_sha256(path) != str(known[path]):
			return {"ok": false, "error": "geometry native dependency is missing or changed"}
		reached[path] = known[path]
		for value: String in ResourceLoader.get_dependencies(path):
			var target := _dependency(value,path)
			if target.is_empty(): return {"ok": false, "error": "geometry dependency cannot be resolved"}
			if _owned(target):
				pending.append(target)
			else:
				var logical := _logical(target)
				if logical.is_empty() or not inputs.has(logical) or FileAccess.get_sha256(target) != str(inputs[logical]):
					return {"ok": false, "error": "geometry external dependency is undeclared or changed"}
	return {"ok": true, "payloads": reached}

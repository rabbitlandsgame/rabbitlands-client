extends SceneTree
const Placements := preload("res://src/world/prepared_placements.gd")
## Coordinator-owned offline job: exactly ONE texture variant per fresh process.
## Never run this in a live client or on a worker. Generated files belong only
## in the disposable package project, never authored asset/source directories.
const Prepared := preload("res://src/world/prepared_content.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
const TexturePool := preload("res://src/world/external_texture_pool.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const Archived := preload("res://src/actors/archived_model_policy.gd")
const TextureSizes := preload("res://src/world/prepared_texture_sizes.gd")
const AnimationKeys := preload("res://src/world/prepared_animation_keys.gd")
var _root_path := ""
var _saved: Dictionary = {}
var _visiting: Dictionary = {}
var _payloads: Dictionary = {}
var _inputs: Dictionary = {}
var _shared_images: Dictionary = {}
var _shared_meshes: Dictionary = {}
var _textures: Array[Dictionary] = []
var _sequence := 0
var _errors: Array[String] = []
var _shader_inputs: Dictionary = {}

func _init() -> void:
	_run.call_deferred()

func _error(message: String) -> void:
	_errors.append(message)
	push_error("prepared cook: " + message)

func _file_hash(path: String) -> String:
	return FileAccess.get_sha256(path)

func _add_input(path: String) -> void:
	var logical := Prepared.logical_source(path)
	var digest := _file_hash(path)
	if logical.is_empty() or digest.is_empty():
		_error("unreadable/unscoped input: " + path)
		return
	_inputs[logical] = digest

func _track_source(spec: Dictionary) -> String:
	var logical := str(spec.get("source", ""))
	var source := Prepared.source_path(logical)
	if source.is_empty() or Archived.is_retired_path(source):
		_error("invalid/retired target: " + logical)
		return ""
	_add_input(source)
	var declared: Variant = spec.get("inputs")
	if not declared is Array or declared.is_empty():
		_error("explicit verified input closure required: " + logical)
		return ""
	for value: Variant in declared:
		if not value is Dictionary:
			_error("invalid declared input: " + logical)
			continue
		var input: Dictionary = value
		var path := Prepared.source_path(str(input.get("path", "")))
		if path.is_empty() or _file_hash(path) != str(input.get("sha256", "")):
			_error("declared source bytes changed: " + str(input.get("path", "")))
			continue
		_add_input(path)
	return source

func _shader_code_inputs(code: String, original_path: String) -> String:
	var includes := RegEx.new()
	if includes.compile("(?m)^[ \\t]*#include[ \\t]+\"([^\"\\n]+)\"") != OK:
		_error("internal shader include expression failed")
		return code
	var rewritten := code
	for include: RegExMatch in includes.search_all(code):
		var uri := include.get_string(1)
		var actual := uri
		if not uri.begins_with("res://"):
			if original_path.is_empty() or not uri.is_relative_path() or ":" in uri:
				_error("shader relative include has no relocatable source identity: " + uri)
				continue
			actual = original_path.get_base_dir().path_join(uri).simplify_path()
		var logical := Prepared.logical_source(actual)
		if logical.is_empty() or not logical.begins_with("godot-client/"):
			_error("shader include escaped runtime project: " + uri)
			continue
		actual = Prepared.source_path(logical)
		_add_input(actual)
		if not _shader_inputs.has(actual):
			_shader_inputs[actual] = true
			_shader_code_inputs(FileAccess.get_file_as_string(actual), actual)
		# Native Shader resources move under prepared-content. Keep a relative
		# include pointed at its original verified runtime file after relocation.
		rewritten = rewritten.replace("\"" + uri + "\"", "\"" + actual + "\"")
	return rewritten

func _walk_value(value: Variant) -> Variant:
	if value is String:
		var text := (value as String).replace("\\", "/")
		if text.begins_with("user://") or text.begins_with("file://") \
				or (text.length() >= 3 and text.substr(1, 2) == ":/"):
			_error("filesystem/user-data path in native payload; explicit runtime relocation required")
			return ""
	if value is Node or value is Script or value is Callable or value is Signal:
		_error("live node/script/callback in prepared resource graph")
		return null
	if value is Resource:
		return _save_resource(value as Resource)
	if value is Object:
		_error("non-resource object in prepared resource graph")
		return null
	if value is Array:
		var array: Array = value.duplicate()
		for index: int in array.size():
			array[index] = _walk_value(array[index])
		return array
	if value is Dictionary:
		var dictionary: Dictionary = value.duplicate()
		for key: Variant in dictionary.keys():
			if key is Resource or key is Object:
				_error("object key in prepared resource graph")
				continue
			dictionary[key] = _walk_value(dictionary[key])
		return dictionary
	return value

static func _shader_matches_source(source: Shader, path: String) -> bool:
	return source != null and FileAccess.file_exists(path) \
		and source.code.replace(String.chr(13), "") == FileAccess.get_file_as_string(path).replace(String.chr(13), "")

static func _preserve_named_shader(source: Shader, track: Callable, includes: Callable) -> Shader:
	if source == null or source.get_script() != null:
		return null
	var path := source.resource_path
	if not path.begins_with("res://") or path.get_extension() != "gdshader" \
			or not Prepared.logical_source(path).begins_with("godot-client/") or not FileAccess.file_exists(path):
		return null
	# A named shader's path is a semantic identity used by existing world/look
	# consumers. Preserve only the actual unchanged source; do not mislabel an
	# edited in-memory program as that source. Full input bytes are still SHA'd.
	if not _shader_matches_source(source, path):
		return null
	track.call(path)
	includes.call(source.code, path) # Collect the complete verified include closure.
	return source

func _save_resource(source: Resource) -> Resource:
	var identity := source.get_instance_id()
	if _saved.has(identity):
		return _saved[identity] as Resource
	if _visiting.has(identity) or source.get_script() != null:
		_error("cyclic/scripted resource graph: " + source.get_class())
		return null
	_visiting[identity] = true
	var original_path := source.resource_path
	# Imported images may have source JPEGs only in the build tree; packages
	# carry their .ctex products instead. Those actual runtime inputs must be
	# explicit in spec.inputs. Do not invent a verification dependency on an
	# original file that the ordinary package deliberately does not ship.
	if source is Shader and original_path.begins_with("res://") \
			and original_path.get_extension() == "gdshader" and FileAccess.file_exists(original_path):
		var preserved := _preserve_named_shader(source as Shader, _add_input, _shader_code_inputs)
		if preserved == null:
			_error("named shader differs from its verified original source: " + original_path)
		elif _errors.is_empty():
			_saved[identity] = preserved
		_visiting.erase(identity)
		return preserved if _errors.is_empty() else null
	var resource: Resource
	if source is Texture2D and not source is ImageTexture:
		# Readback is allowed only in this offline main-thread process. Preserve
		# format/size/mips exactly; this is not a new compression recipe.
		var image := (source as Texture2D).get_image()
		if image == null or image.is_empty():
			_error("cannot read native texture during offline preparation")
			_visiting.erase(identity)
			return null
		resource = ImageTexture.create_from_image(image)
		for property: Dictionary in source.get_property_list():
			if str(property.name) == "load_path":
				var import_product := str(source.get("load_path"))
				if not import_product.is_empty():
					_add_input(import_product)
	else:
		resource = source.duplicate(false)
	if resource == null:
		_error("resource cannot be duplicated: " + source.get_class())
		_visiting.erase(identity)
		return null
	if resource is Animation and source is Animation:
		if not AnimationKeys.prepare(source as Animation, resource as Animation):
			_error("unsupported native animation clock layout")
			_visiting.erase(identity)
			return null
	if resource is ImageTexture and source is Texture2D:
		# GPU readback may expose padded compressed storage dimensions.
		# ImageTexture serializes only image, so persist logical size too.
		if not TextureSizes.prepare(source as Texture2D, resource as ImageTexture):
			_error("invalid logical texture size")
			_visiting.erase(identity)
			return null
	if resource is Shader:
		(resource as Shader).code = _shader_code_inputs((source as Shader).code, original_path)
	if resource is ImageTexture:
		var image := (resource as ImageTexture).get_image()
		if image == null or image.is_empty():
			_error("prepared texture has no readable offline image")
			_visiting.erase(identity)
			return null
		_textures.append({"source_class": source.get_class(), "source_path": Prepared.logical_source(original_path) if not original_path.is_empty() else "",
			"width": (resource as ImageTexture).get_width(), "height": (resource as ImageTexture).get_height(),
			"logical_width": (resource as ImageTexture).get_width(), "logical_height": (resource as ImageTexture).get_height(),
			"storage_width": image.get_width(), "storage_height": image.get_height(),
			"format": image.get_format(), "mipmaps": image.get_mipmap_count(),
			"data_bytes": image.get_data_size(), "accounting": "image_data_not_driver_allocation"})
	for property: Dictionary in resource.get_property_list():
		var name := str(property.name)
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0 \
				or name in ["resource_path", "resource_name", "resource_local_to_scene", "script"]:
			continue
		var original: Variant = resource.get(name)
		if original is Resource or original is Array or original is Dictionary or original is String:
			resource.set(name, _walk_value(original))
	if not _errors.is_empty():
		_visiting.erase(identity)
		return null
	# The generic stored-property pass can call ImageTexture.set_image,
	# which resets w/h. Reapply the exact logical dimensions after it too.
	if resource is ImageTexture and source is Texture2D:
		(resource as ImageTexture).set_size_override(Vector2i((source as Texture2D).get_width(), (source as Texture2D).get_height()))
	# Resource.duplicate and stored tracks/keys properties already narrow
	# double clocks. Restore from the original f64 metadata after that walk.
	if resource is Animation and not AnimationKeys.restore_verified(resource as Animation):
		_error("native animation clocks cannot be restored exactly")
		_visiting.erase(identity)
		return null
	if resource is Animation and resource.has_meta(AnimationKeys.PUBLISHED):
		resource.remove_meta(AnimationKeys.PUBLISHED) # Runtime marker never enters saved bytes.
	_sequence += 1
	var extension := "scn" if resource is PackedScene else "res"
	var staging := _root_path.path_join("writing-%06d.%s" % [_sequence, extension])
	var save_error := ResourceSaver.save(resource, staging)
	if save_error != OK:
		_error("native save failed: " + staging + " " + error_string(save_error))
		_visiting.erase(identity)
		return null
	var digest := _file_hash(staging)
	var final := _root_path.path_join(digest + "." + extension)
	if FileAccess.file_exists(final):
		if _file_hash(final) != digest:
			_error("existing content-addressed payload changed: " + final)
		DirAccess.remove_absolute(staging)
	else:
		var rename_error := DirAccess.rename_absolute(staging, final)
		if rename_error != OK:
			_error("native payload rename failed: " + error_string(rename_error))
	resource.take_over_path(final)
	if source is ImageTexture:
		for logical: String in _inputs:
			var sha := str(_inputs[logical])
			if TexturePool._published(sha) == source:
				_shared_images[final] = sha
	if source is Mesh:
		for logical: String in _inputs:
			var key := logical.get_file().get_basename()
			if logical.get_extension() == "glb" and MeshPool._published(key) == source:
				_shared_meshes[final] = key
	_payloads[final] = digest
	_saved[identity] = resource
	_visiting.erase(identity)
	return resource

func _transform_values(value: Transform3D) -> Array:
	return [value.basis.x.x, value.basis.x.y, value.basis.x.z,
		value.basis.y.x, value.basis.y.y, value.basis.y.z,
		value.basis.z.x, value.basis.z.y, value.basis.z.z,
		value.origin.x, value.origin.y, value.origin.z]

func _scene_metadata(packed: PackedScene, logical_source: String) -> Dictionary:
	var root := packed.instantiate() as Node3D
	if root == null:
		_error("prepared pilot requires a Node3D scene root")
		return {}
	var rigs: Array[Dictionary] = []
	var animations: Array[Dictionary] = []
	var placements: Array[Dictionary] = []
	var occurrences: Dictionary = {}
	var pending: Array[Node] = [root]
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		var children := node.get_children()
		children.reverse()
		for child: Node in children:
			pending.append(child)
		if node.get_script() != null:
			_error("scripted node in imported component: " + str(node.name))
		if node is Skeleton3D:
			var skeleton := node as Skeleton3D
			var names: Array[String] = []
			var parents: Array[int] = []
			var rest: Array = []
			var neutral_pose: Array = []
			for bone: int in skeleton.get_bone_count():
				names.append(skeleton.get_bone_name(bone))
				parents.append(skeleton.get_bone_parent(bone))
				rest.append_array(_transform_values(skeleton.get_bone_rest(bone)))
				var position := skeleton.get_bone_pose_position(bone)
				var rotation := skeleton.get_bone_pose_rotation(bone)
				var scale := skeleton.get_bone_pose_scale(bone)
				neutral_pose.append_array([position.x, position.y, position.z,
					rotation.x, rotation.y, rotation.z, rotation.w, scale.x, scale.y, scale.z])
			rigs.append({"path": str(root.get_path_to(skeleton)), "names": names,
				"parents": parents, "rest_affine12": rest, "neutral_pose10": neutral_pose})
		if node is AnimationPlayer:
			var player := node as AnimationPlayer
			for library_name: StringName in player.get_animation_library_list():
				var library := player.get_animation_library(library_name)
				for name: StringName in library.get_animation_list():
					var animation := library.get_animation(name)
					animations.append({"player": str(root.get_path_to(player)),
						"library": str(library_name), "name": str(name),
						"length": animation.length, "tracks": animation.get_track_count(),
						"loop_mode": animation.loop_mode})
		if node is MeshInstance3D:
			var ordinal := int(occurrences.get(str(node.name), 0))
			occurrences[str(node.name)] = ordinal + 1
			var hashing := HashingContext.new()
			hashing.start(HashingContext.HASH_SHA256)
			hashing.update((logical_source + "\n" + str(node.name) + "\n" + str(ordinal)).to_utf8_buffer())
			placements.append({"id": hashing.finish().hex_encode(), "name": str(node.name),
				"node_path": str(root.get_path_to(node)), "ordinal": ordinal,
				"batch_path": str(node.get_meta(WorldLoader.BATCH_PATH_META, NodePath())),
				"batch_index": int(node.get_meta(WorldLoader.BATCH_INDEX_META, -1))})
	root.free()
	return {"rigs": rigs, "animations": animations, "placements": placements,
		"node_policy": "retained_source_nodes", "embedded_compression": "unchanged"}

func _pristine_world(path: String) -> PackedScene:
	# This existing cache snapshot is taken before look/fade/season consumers.
	# Require a fresh isolated cache miss; never pack a currently played scene.
	var loader := WorldLoader.new()
	# The raw reference batches only visible-in-tree meshes in ordinary mode.
	# Owning this disposable loader under the cooker's SceneTree preserves that
	# exact path; an off-tree ordinary loader silently skips static batching.
	root.add_child(loader)
	loader.load_world(path)
	if loader.world_root == null or loader.cache_status != &"miss" or loader._cache_nodes.is_empty():
		_error("world cook requires a raw non-streaming package and fresh cache miss: " + path)
		loader.free()
		return null
	var restore := loader._restore_pristine()
	for node: Node in loader._cache_nodes:
		if is_instance_valid(node):
			if node.get_script() != null:
				_error("scripted node in raw imported world: " + str(node.name))
			# The immutable scene stores the existing root-relative path, not
			# an Object-valued pointer into this temporary live tree.
			if node.has_meta(WorldLoader.BATCH_META):
				node.remove_meta(WorldLoader.BATCH_META)
			node.owner = loader.world_root
	var packed := PackedScene.new()
	var pack_error := packed.pack(loader.world_root)
	loader._undo_pristine(restore)
	loader._release_snapshot()
	loader.free()
	if pack_error != OK:
		_error("pristine world pack failed: " + error_string(pack_error))
		return null
	return packed

func _target(spec: Dictionary) -> Dictionary:
	_inputs.clear()
	_payloads.clear()
	_shared_images.clear()
	_shared_meshes.clear()
	_shader_inputs.clear()
	_textures.clear()
	# Keep the saved-resource map within one target. Every entry must list its
	# full transitive closure even when another target emitted the same bytes.
	_saved.clear()
	_visiting.clear()
	var path := _track_source(spec)
	if path.is_empty() or not _errors.is_empty():
		return {}
	var kind := str(spec.get("kind", ""))
	var native: Resource
	var source_digest := ""
	var token := ""
	var metadata: Dictionary = {}
	var node_policy := str(spec.get("node_policy", "retain"))
	if node_policy not in ["retain", Placements.POLICY] or (kind != "world" and node_policy != "retain"):
		_error("unsupported prepared node policy")
		return {}
	if kind == "world":
		var manifest := WorldManifest.load_file(path)
		if not manifest.is_valid() or manifest.has_streaming_chunks() \
				or not manifest.verify_external_resources().is_empty():
			_error("invalid/territory target; cook its independent child package: " + path)
			return {}
		source_digest = MapSceneCache.package_digest(path, manifest.glb_path())
		token = Vram.cache_token(manifest.data, manifest.glb_path().get_base_dir())
		native = _pristine_world(path)
		if node_policy == Placements.POLICY and native != null:
			var reduced := Placements.cook_reduce(native as PackedScene, manifest, Prepared.logical_source(path) + "|" + source_digest)
			if reduced.is_empty() or int(reduced.get("stats", {}).get("removed_sources", 0)) <= 0:
				_error("reduction target has no qualified static source group: " + path)
				return {}
			native = reduced.scene as PackedScene
			metadata["static_reduction"] = reduced.stats
	elif kind == "scene":
		# Preserves the existing animation-fidelity, embedded world-image and
		# anisotropic-filter policy. Equipment imports stay on this main thread.
		source_digest = _file_hash(path)
		token = Prepared.scene_texture_token(path)
		# The editor's preferred imported actor scene can have generated LODs or
		# compression absent from the shipping raw path. Use that raw path as the
		# preparation reference; qualify importer changes as a separate change.
		native = GlbSceneCache._build_raw(path)
	elif kind == "mesh":
		source_digest = _file_hash(path)
		var prototype := path.get_file().get_basename()
		if Archived.is_retired_prototype(prototype):
			_error("retired prototype target: " + prototype)
			return {}
		var pool_entry: Dictionary = MeshPool.index_for(path).get(prototype, {})
		token = Vram.cache_token({"externalResources": pool_entry.get("images", {})}, path.get_base_dir())
		native = MeshPool.acquire(prototype, path)
	else:
		_error("unknown target kind: " + kind)
		return {}
	if native == null:
		_error("raw target did not build: " + path)
		return {}
	if native is PackedScene:
		metadata.merge(_scene_metadata(native as PackedScene, Prepared.logical_source(path)))
	var saved := _save_resource(native)
	if saved == null or not _errors.is_empty():
		return {}
	metadata["textures"] = _textures.duplicate(true)
	metadata["source_images"] = spec.get("source_images", []).duplicate(true)
	metadata["input_closure_policy"] = "actual-runtime-files-plus-import-products-v1"
	metadata["runtime_import_snapshot"] = spec.get("runtime_import_snapshot", {}).duplicate(true)
	var inputs: Array[Dictionary] = []
	var payloads: Array[Dictionary] = []
	var input_paths := _inputs.keys()
	input_paths.sort()
	for input: String in input_paths:
		inputs.append({"path": input, "sha256": str(_inputs[input])})
	var payload_paths := _payloads.keys()
	payload_paths.sort()
	for payload: String in payload_paths:
		payloads.append({"path": payload, "sha256": str(_payloads[payload])})
	var entry := {"kind": kind, "node_policy": node_policy, "source": Prepared.logical_source(path),
		"source_digest": source_digest, "texture_token": token,
		"engine_policy": Prepared.engine_policy(), "resource": saved.resource_path,
		"inputs": inputs, "payloads": payloads,
		"shared_images": _shared_images.duplicate(), "shared_meshes": _shared_meshes.duplicate(),
		"metadata_json": Prepared.encode_metadata(metadata),
		"texture_skip": Graphics.active_texture_skip(), "format_mask": Vram.usable_formats(),
		"representation": "exact_native_variant", "qualification": "pending_exported_parity"}
	entry["entry_id"] = Prepared.entry_identity(entry)
	return entry

func _run() -> void:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		_error("cooking requires main-thread ownership")
		quit(1)
		return
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 1:
		_error("expected one approved cook-job JSON path after --")
		quit(1)
		return
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(arguments[0])) != OK or not parser.data is Dictionary:
		_error("invalid cook-job JSON")
		quit(1)
		return
	var job: Dictionary = parser.data
	var marker := JSON.new()
	var marker_path := "res://.prepared-cook-project.json"
	if not OS.has_feature("windows") or marker.parse(FileAccess.get_file_as_string(marker_path)) != OK \
			or not marker.data is Dictionary or str(marker.data.get("purpose", "")) != "disposable-native-cook":
		_error("current cook requires a marked disposable Windows project")
		quit(1)
		return
	var expected_user := str(job.get("expected_user_directory", "")).replace("\\", "/").simplify_path()
	var actual_user := ProjectSettings.globalize_path("user://").replace("\\", "/").simplify_path().trim_suffix("/")
	if expected_user.is_empty() or expected_user.to_lower() != actual_user.to_lower() \
			or FileAccess.file_exists(Graphics.SETTINGS_PATH):
		_error("fresh isolated APPDATA/user directory required before touching graphics config")
		quit(1)
		return
	_root_path = str(job.get("output", ""))
	if not _root_path.begins_with("res://prepared-content/") \
			or not Prepared._contained(_root_path, "res://prepared-content") \
			or not job.get("targets") is Array or job.targets.is_empty():
		_error("scoped disposable output and targets required")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(_root_path)
	# No prepared recursion while producing raw references. Set texture quality
	# in this fresh process's isolated config before invoking the job.
	OS.set_environment(Prepared.ENVIRONMENT, "raw")
	var quality := str(job.get("texture_quality", ""))
	if not quality in Graphics.TEXTURE_QUALITIES:
		_error("exact full/half/quarter cook texture policy required")
		quit(1)
		return
	# The coordinator supplies fresh APPDATA isolation. Never change the
	# developer/player profile or infer texture policy from graphics tier.
	var config := ConfigFile.new()
	config.set_value("graphics", "map_texture_quality", quality)
	if config.save(Graphics.SETTINGS_PATH) != OK:
		_error("cannot seed isolated texture policy")
		quit(1)
		return
	Graphics._texture_skip = -1
	OS.set_environment("ELORIA_NO_MAP_CACHE", "")
	MapSceneCache.forget_setting()
	Quantization.ensure_registered()
	Vram.ensure_registered()
	var entries: Array[Dictionary] = []
	for value: Variant in job.targets:
		if not value is Dictionary:
			_error("invalid target record")
			break
		var entry := _target(value as Dictionary)
		if not _errors.is_empty():
			break
		entries.append(entry)
	if not _errors.is_empty():
		quit(1)
		return
	var result := {"schema_version": Prepared.SCHEMA, "policy": Prepared.COOK_POLICY,
		"qualification": "pending_exported_parity", "entries": entries}
	var output := FileAccess.open(_root_path.path_join("variant-catalog.json"), FileAccess.WRITE)
	if output == null:
		_error("cannot write variant catalog")
		quit(1)
		return
	output.store_string(JSON.stringify(result, "\t", true, true))
	output.close()
	GlbSceneCache.clear()
	print("prepared asset cook: PASS entries=", entries.size())
	quit(0)

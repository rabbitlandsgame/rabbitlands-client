extends SceneTree
## External build-source tool. Every res:// dependency must resolve from the
## final normal PCK mounted by --main-pack; no benchmark workload is exported.
const Prepared := preload("res://src/world/prepared_content.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Placements := preload("res://src/world/prepared_placements.gd")
const Manifest := preload("res://src/world/world_manifest.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
const Scenes := preload("res://src/actors/glb_scene_cache.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")
var _failures: Array[String] = []
var _report: Dictionary = {"schema_version": 1, "status": "incomplete", "entries": [],
	"limits": ["exact final-PCK acquisition and resource sanity; does not replace visual/gameplay parity or hardware qualification"]}
var _output := ""
var _stage := ""
var _platform := ""
var _counts := {"mesh_surfaces": 0, "multimesh_instances": 0, "textures": 0,
	"animation_keys": 0, "skeleton_bones": 0, "collision_shapes": 0}

func _init() -> void:
	_run.call_deferred()

func _check(value: bool, reason: String) -> bool:
	if not value:
		_failures.append(reason)
		push_error("prepared release check: " + reason)
	return value

func _path(value: String) -> String:
	return value.replace("\\", "/").simplify_path().trim_suffix("/")

func _same(left: String, right: String) -> bool:
	return _path(left).to_lower() == _path(right).to_lower() if _platform == "windows" else _path(left) == _path(right)

func _inside(path: String, root_path: String) -> bool:
	var value := _path(path).to_lower() if _platform == "windows" else _path(path)
	var parent := _path(root_path).to_lower() if _platform == "windows" else _path(root_path)
	return value == parent or value.begins_with(parent + "/")

func _buffer_probe() -> bool:
	var batch := MultiMesh.new()
	batch.transform_format = MultiMesh.TRANSFORM_3D
	batch.mesh = BoxMesh.new()
	batch.instance_count = 1
	var expected := Transform3D(Basis.IDENTITY, Vector3(1.25, 2.5, 3.75))
	batch.set_instance_transform(0, expected)
	if batch.buffer.size() != 12 or not batch.get_instance_transform(0).is_equal_approx(expected):
		return false
	var path := "user://release-final-buffer-probe.res"
	if FileAccess.file_exists(path) or ResourceSaver.save(batch, path) != OK:
		return false
	batch = null
	var restored := ResourceLoader.load(path, "MultiMesh", ResourceLoader.CACHE_MODE_IGNORE) as MultiMesh
	var valid := restored != null and restored.buffer.size() == 12 \
		and restored.get_instance_transform(0).is_equal_approx(expected)
	var removed := DirAccess.remove_absolute(ProjectSettings.globalize_path(path)) == OK
	return valid and removed

func _material(material: Material, visited: Dictionary) -> void:
	if material == null or visited.has(material.get_instance_id()):
		return
	visited[material.get_instance_id()] = true
	_check(material.get_script() == null, "executable material in prepared instance")
	for property: Dictionary in material.get_property_list():
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0:
			continue
		var value: Variant = material.get(str(property.name))
		if value is Texture2D and not visited.has(value.get_instance_id()):
			visited[value.get_instance_id()] = true
			var texture := value as Texture2D
			_counts.textures += 1
			_check(texture.get_width() > 0 and texture.get_height() > 0, "empty logical texture dimensions")
			var image := texture.get_image()
			_check(image != null and not image.is_empty() and image.get_data_size() > 0, "prepared material texture has no actual readable storage")
		elif value is Material:
			_material(value as Material, visited)

func _mesh(mesh: Mesh, visited: Dictionary) -> void:
	if mesh == null or visited.has(mesh.get_instance_id()):
		return
	visited[mesh.get_instance_id()] = true
	_check(mesh.get_script() == null and mesh.get_surface_count() > 0, "prepared mesh has no data surfaces")
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		_counts.mesh_surfaces += 1
		_check(arrays.size() == Mesh.ARRAY_MAX and arrays[Mesh.ARRAY_VERTEX] is PackedVector3Array \
			and not (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).is_empty(), "prepared mesh surface buffers are not readable")
		_material(mesh.surface_get_material(surface), visited)

func _animation(animation: Animation) -> void:
	if animation == null:
		return
	for track: int in animation.get_track_count():
		for key: int in animation.track_get_key_count(track):
			_counts.animation_keys += 1
			_check(is_finite(animation.track_get_key_time(track, key)) and is_finite(animation.track_get_key_transition(track, key)), "nonfinite prepared animation key")

func _tree_resources(root_node: Node3D) -> void:
	var pending: Array[Node] = [root_node]
	var visited: Dictionary = {}
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		_check(node.get_script() == null, "scripted imported node exposed")
		if node is Node3D:
			_check((node as Node3D).transform.is_finite(), "nonfinite prepared transform")
		if node is MeshInstance3D:
			var instance := node as MeshInstance3D
			_mesh(instance.mesh, visited)
			if instance.mesh != null:
				for surface: int in instance.mesh.get_surface_count():
					_material(instance.get_active_material(surface), visited)
		elif node is MultiMeshInstance3D:
			var batch := node as MultiMeshInstance3D
			if _check(batch.multimesh != null, "prepared MultiMesh is missing"):
				var data := batch.multimesh
				_mesh(data.mesh, visited)
				var stride := (12 if data.transform_format == MultiMesh.TRANSFORM_3D else 8) + (4 if data.use_colors else 0) + (4 if data.use_custom_data else 0)
				_check(data.buffer.size() == stride * data.instance_count, "prepared MultiMesh buffer/count mismatch")
				_counts.multimesh_instances += data.instance_count
				_material(batch.material_override, visited)
		if node is GeometryInstance3D:
			_material((node as GeometryInstance3D).material_overlay, visited)
		if node is Skeleton3D:
			var skeleton := node as Skeleton3D
			_counts.skeleton_bones += skeleton.get_bone_count()
			for bone: int in skeleton.get_bone_count():
				_check(skeleton.get_bone_rest(bone).is_finite(), "nonfinite prepared skeleton rest")
		if node is AnimationPlayer:
			var player := node as AnimationPlayer
			for animation: String in player.get_animation_list():
				_animation(player.get_animation(animation))
		if node is CollisionShape3D:
			_counts.collision_shapes += 1
			_check((node as CollisionShape3D).shape != null, "prepared collision shape is missing")
		for child: Node in node.get_children():
			pending.append(child)

func _identity(row: Dictionary) -> Dictionary:
	var kind := str(row.get("kind", ""))
	var source := Prepared.source_path(str(row.get("source", "")))
	if source.is_empty():
		return {}
	var digest := ""
	var token := ""
	var manifest: RefCounted
	if kind == "world":
		var world := Manifest.load_file(source)
		if not _check(world.is_valid() and not world.has_streaming_chunks() and world.verify_external_resources().is_empty(), "final staged world manifest/external identity is invalid"):
			return {}
		manifest = world
		digest = MapCache.package_digest(source, world.glb_path())
		token = Vram.cache_token(world.data, world.glb_path().get_base_dir())
	elif kind == "scene":
		digest = FileAccess.get_sha256(source)
		token = Prepared.scene_texture_token(source)
	elif kind == "mesh":
		digest = FileAccess.get_sha256(source)
		var pool_entry: Dictionary = MeshPool.index_for(source).get(source.get_file().get_basename(), {})
		token = Vram.cache_token({"externalResources": pool_entry.get("images", {})}, source.get_base_dir())
	else:
		return {}
	return {"source": source, "digest": digest, "token": token, "manifest": manifest}

func _entry(row: Dictionary) -> Dictionary:
	var began := Time.get_ticks_usec()
	OS.set_environment("RABBITLANDS_PREPARED_NODE_POLICY", str(row.get("node_policy", "retain")))
	var identity := _identity(row)
	if not _check(not identity.is_empty() and identity.get("digest") == row.get("source_digest") \
		and identity.get("token") == row.get("texture_token"), "actual final source/texture identity differs from expected entry"):
		return {}
	var record := Prepared.acquire(str(row.kind), str(identity.source), str(identity.digest), str(identity.token), "require-pilot")
	if not _check(str(record.get("status", "")) == "hit" and record.get("entry_id") == row.get("entry_id"), "final package did not acquire its exact required prepared entry: " + str(record.get("reason", ""))):
		return {}
	var detail := {"entry_id": row.entry_id, "kind": row.kind, "source": row.source,
		"node_policy": row.node_policy, "texture_token": identity.token}
	if str(row.kind) == "mesh":
		_mesh(record.get("resource") as Mesh, {})
	else:
		var instance := Lifecycle.instantiate(record)
		if not _check(instance != null, "verified PackedScene failed actual data-only/private-material instantiation"):
			return {}
		get_root().add_child(instance)
		await process_frame
		await process_frame
		if str(row.kind) == "world":
			Placements.install(instance, identity.manifest, record.entry)
		_tree_resources(instance)
		if str(row.node_policy) == Placements.POLICY:
			var before := Placements.snapshot(instance)
			_check(int(before.initial_removed_sources) > 0 and int(before.remaining_node_reduction) > 0, "lazy final package has no actual reduction handles")
			var handles := Placements.handles(instance)
			if not handles.is_empty():
				var restored: MeshInstance3D = handles[0].restore(false)
				var after := Placements.snapshot(instance)
				_check(restored != null and int(after.reified_sources) == int(before.reified_sources) + 1 \
					and int(after.remaining_node_reduction) == int(before.remaining_node_reduction) - 1, "lazy actual final-PCK leaf restoration did not publish exactly once")
				_check(handles[0].restore(false) == restored, "lazy leaf second restoration is not idempotent")
				detail["placements_before"] = before
				detail["placements_after"] = after
				_tree_resources(instance)
		Ownership.refresh(instance)
		get_root().remove_child(instance)
		instance.free()
		record.clear()
		await process_frame
		await process_frame
	detail["elapsed_us"] = Time.get_ticks_usec() - began
	return detail

func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if not _check(arguments.size() == 1, "one external job JSON is required"):
		_finish()
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
	if not _check(parsed is Dictionary, "invalid guard job"):
		_finish()
		return
	var job: Dictionary = parsed
	_platform = str(job.get("platform", ""))
	_stage = _path(str(job.get("expected_stage_root", "")))
	var app := _path(str(job.get("expected_stage_app", "")))
	var output := _path(str(job.get("report", "")))
	if not _check(int(job.get("schema_version", -1)) == 1 and _platform in ["windows", "linux"] \
		and _stage.is_absolute_path() and _same(app, _stage.path_join("app")) \
		and output.is_absolute_path() and not _inside(output, _stage), "invalid stage/output scope; package writes forbidden"):
		_finish()
		return
	_output = output
	var actual_user := _path(ProjectSettings.globalize_path("user://"))
	_report.merge({"stage_app": app, "project_root": Prepared._project_root(),
		"globalized_resource_root": ProjectSettings.globalize_path("res://"),
		"engine_executable": OS.get_executable_path(), "user_directory": actual_user})
	var executable := OS.get_executable_path()
	var guard_name := "RabbitLands-release-guard-editor.exe" if _platform == "windows" else "RabbitLands-release-guard-editor.x86_64"
	var expected_executable := app.path_join(guard_name if OS.has_feature("editor") else ("RabbitLands.exe" if _platform == "windows" else "RabbitLands.x86_64"))
	var resource_root := ProjectSettings.globalize_path("res://")
	if not _check(_same(executable, expected_executable) and _same(executable.get_base_dir(), app) \
		and _same(Prepared._project_root(), app) and (resource_root.is_empty() or not resource_root.is_absolute_path() or _same(resource_root, app)), "verified in-app executable/stage root required; source-project fallback forbidden") \
		or not _check(_same(actual_user, str(job.get("expected_user_directory", ""))) and not _inside(actual_user, _stage) \
			and not FileAccess.file_exists(Graphics.SETTINGS_PATH), "fresh isolated user directory required outside the package"):
		_finish()
		return
	_report["guard_context"] = "verified_editor_in_app" if OS.has_feature("editor") else "exported_executable"
	var catalog_sha := FileAccess.get_sha256(Prepared.CATALOG)
	var catalog_value: Variant = JSON.parse_string(FileAccess.get_file_as_string(Prepared.CATALOG))
	if not _check(Prepared._hex_digest(job.get("catalog_sha256")) and catalog_sha == job.catalog_sha256 \
		and catalog_value is Dictionary, "actual final-PCK catalog byte identity differs"):
		_finish()
		return
	var catalog: Dictionary = catalog_value
	var required: Variant = job.get("required_entries")
	var quality := str(job.get("texture_quality", ""))
	if not _check(int(catalog.get("schema_version", -1)) == Prepared.SCHEMA and catalog.get("policy") == Prepared.COOK_POLICY \
		and catalog.get("entries") is Array and catalog.entries.size() == int(job.get("expected_catalog_entries", -1)) \
		and required is Array and not required.is_empty() and required.size() == int(job.get("expected_entries", -1)) \
		and required.size() <= 128 and catalog.entries.size() <= 512 \
		and quality in Graphics.TEXTURE_QUALITIES, "unsupported catalog, count, required targets or texture quality"):
		_finish()
		return
	var configuration := ConfigFile.new()
	configuration.set_value("graphics", "map_texture_quality", quality)
	if not _check(configuration.save(Graphics.SETTINGS_PATH) == OK, "cannot seed isolated texture policy"):
		_finish()
		return
	Graphics._texture_skip = -1
	var before_nodes := get_node_count()
	var saved_environment: Dictionary = {}
	for key: String in ["RABBITLANDS_PREPARED_CONTENT", "RABBITLANDS_PREPARED_NODE_POLICY"]:
		saved_environment[key] = {"present": OS.has_environment(key), "value": OS.get_environment(key)}
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "require-pilot")
	var adapter := RenderingServer.get_video_adapter_name()
	var adapter_type := int(RenderingServer.get_video_adapter_type())
	var software := (_platform == "windows" and adapter_type == RenderingDevice.DEVICE_TYPE_CPU \
		and ("warp" in adapter.to_lower() or "microsoft basic render driver" in adapter.to_lower())) \
		or (_platform == "linux" and "llvmpipe" in adapter.to_lower())
	_report.merge({"stage_app": app, "project_root": Prepared._project_root(), "catalog_sha256": catalog_sha,
		"catalog_entries": catalog.entries.size(), "texture_quality": quality,
		"graphics": {"policy": "actual-renderer-supported-format-subset-v1", "platform": _platform,
			"rendering_method": RenderingServer.get_current_rendering_method(),
			"rendering_driver": RenderingServer.get_current_rendering_driver_name(), "adapter_name": adapter,
			"adapter_type": adapter_type, "software_adapter": software,
			"detected_format_mask": Vram.usable_formats(), "resource_buffer_probe": _buffer_probe()}})
	_check(software and Vram.usable_formats() == 7 and bool(_report.graphics.resource_buffer_probe), "actual software renderer/BC formats/resource buffers are not qualified")
	var expected_ids: Dictionary = {}
	for value: Variant in required:
		if not _check(value is Dictionary, "invalid required-entry record"):
			break
		var row: Dictionary = value
		var entry_id := str(row.get("entry_id", ""))
		var matches: Array[Dictionary] = []
		for candidate: Variant in catalog.entries:
			if candidate is Dictionary and candidate.get("entry_id") == entry_id:
				matches.append(candidate)
		if not _check(Prepared._hex_digest(entry_id) and not expected_ids.has(entry_id) and matches.size() == 1, "required entry is missing, duplicated or ambiguous"):
			break
		var actual: Dictionary = matches[0]
		var fields_match := true
		for key: String in ["kind", "source", "node_policy", "source_digest", "texture_token"]:
			fields_match = fields_match and row.get(key) == actual.get(key, "retain" if key == "node_policy" else null)
		if not _check(fields_match and int(actual.get("texture_skip", -1)) == Graphics.TEXTURE_QUALITIES.find(quality), "required identity or quality differs from final catalog"):
			break
		expected_ids[entry_id] = true
		if not _failures.is_empty():
			break
		var detail: Dictionary = await _entry(row)
		_report.entries.append(detail)
		if not _failures.is_empty():
			break
	Scenes.clear()
	await process_frame
	await process_frame
	var actual_snapshot := Prepared.snapshot()
	var consumed: Dictionary = {}
	for row: Dictionary in actual_snapshot.consumed_entries:
		consumed[str(row.entry_id)] = true
	_check(consumed == expected_ids and _report.entries.size() == required.size(), "actual acquired/consumed entry identities do not equal complete planned coverage")
	_check(get_node_count() == before_nodes, "transient prepared scene Nodes survived owned cleanup")
	_report["prepared"] = actual_snapshot
	var entry_ids: Array = consumed.keys()
	entry_ids.sort()
	_report["entry_ids"] = entry_ids
	_report["resources"] = _counts.duplicate()
	_report["nodes_before"] = before_nodes
	_report["nodes_after"] = get_node_count()
	for key: String in saved_environment:
		if bool(saved_environment[key].present):
			OS.set_environment(key, str(saved_environment[key].value))
		else:
			OS.unset_environment(key)
	_finish()

func _finish() -> void:
	_report["status"] = "pass" if _failures.is_empty() else "failed"
	_report["failures"] = _failures.duplicate()
	if not _output.is_empty():
		var handle := FileAccess.open(_output, FileAccess.WRITE)
		if handle == null:
			_failures.append("cannot write external guard receipt")
			_report["status"] = "failed"
		else:
			handle.store_string(JSON.stringify(_report, "", true, true) + "\n")
			handle.flush()
			handle.close()
	print("PREPARED_RELEASE_CHECK ", JSON.stringify({"status": _report.status, "entries": _report.entries.size(),
		"failures": _failures, "report": _output}))
	quit(1 if not _failures.is_empty() else 0)

extends SceneTree
## Actual renderer required for lossless ImageTexture/MultiMesh storage checks.
const Storage := preload("res://tools/prepared_native_storage.gd")
const TextureSizes := preload("res://src/world/prepared_texture_sizes.gd")
const AnimationKeys := preload("res://src/world/prepared_animation_keys.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Prepared := preload("res://src/world/prepared_content.gd")
var checks := 0
var failures := 0
var root_path := "user://native-storage-owned"
var known: Dictionary = {}

func _init() -> void:
	_run.call_deferred()

func _check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("native storage: " + message)

func _save(resource: Resource, name: String) -> String:
	var path := root_path.path_join(name)
	_check(Storage.save(resource, path) == OK, "compressed save " + name)
	resource.take_over_path(path)
	known[path] = FileAccess.get_sha256(path)
	var file := FileAccess.open(path, FileAccess.READ)
	_check(file != null and file.get_buffer(4).get_string_from_ascii() == "RSCC", "actual compressed native header " + name)
	return path

func _entry(path: String, inputs: Dictionary = {}) -> Dictionary:
	var result := Storage.closure(path, known, inputs, root_path)
	_check(bool(result.ok), "actual complete dependency closure " + path)
	var payloads: Array[Dictionary] = []
	for native: String in result.get("payloads", {}):
		payloads.append({"path": native, "sha256": str(known[native])})
	var declared_inputs: Array[Dictionary] = []
	for input: String in inputs:
		declared_inputs.append({"path": input, "sha256": str(inputs[input])})
	return {"resource": path, "payloads": payloads, "inputs": declared_inputs}

func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file = null

func _run() -> void:
	_check(not DirAccess.dir_exists_absolute(root_path), "fresh owned fixture namespace")
	DirAccess.make_dir_recursive_absolute(root_path)
	var nodes_before := int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	var image := Image.create(13, 9, true, Image.FORMAT_RGBA8)
	image.fill(Color(0.1, 0.3, 0.7, 1.0))
	image.generate_mipmaps()
	var orphan := _save(image, "embedded-image-orphan.res")
	var texture := ImageTexture.create_from_image(image)
	_check(TextureSizes.prepare(texture, texture), "exact texture metadata seed")
	var shared := _save(texture, "shared-texture.res")
	var other_texture := ImageTexture.create_from_image(image)
	_check(TextureSizes.prepare(other_texture, other_texture), "second texture metadata seed")
	var only_b := _save(other_texture, "only-second-root.res")
	var material_a := StandardMaterial3D.new()
	material_a.albedo_texture = texture
	var root_a := _save(material_a, "first-material.res")
	var material_b := StandardMaterial3D.new()
	material_b.albedo_texture = texture
	material_b.emission_enabled = true
	material_b.emission_texture = other_texture
	var root_b := _save(material_b, "second-material.res")
	var a := _entry(root_a)
	var b := _entry(root_b)
	_check(a.payloads.size() == 2 and b.payloads.size() == 3, "unequal roots share one dependency and retain second-only texture")
	_check(FileAccess.file_exists(orphan) and FileAccess.file_exists(only_b), "entry closure never deletes generation files")
	_check(not a.payloads.any(func(row: Dictionary) -> bool: return str(row.path) == orphan), "embedded Image artifact is absent from actual native dependencies")
	var absent := known.duplicate()
	absent.erase(shared)
	_check(not bool(Storage.closure(root_a, absent, {}, root_path).ok), "existing but unregistered native dependency fails closed")
	var bytes := FileAccess.get_file_as_bytes(shared)
	var changed := bytes.duplicate()
	changed[changed.size() - 1] ^= 1
	_write(shared, changed)
	_check(not bool(Storage.closure(root_a, known, {}, root_path).ok), "same-size native mutation rejects before dependency parsing")
	_write(shared, bytes)
	var backup := "user://native-storage-missing-backup.res"
	_check(DirAccess.rename_absolute(shared, backup) == OK, "temporarily remove owned dependency")
	_check(not bool(Storage.closure(root_a, known, {}, root_path).ok), "missing native dependency fails closed")
	_check(DirAccess.rename_absolute(backup, shared) == OK, "restore exact owned dependency")
	_check(FileAccess.get_sha256(shared) == str(known[shared]), "mutation/missing probes restore original bytes")
	_check(not bool(Storage._dependency_path("uid://unresolved").ok), "UID without canonical path fails closed")
	_check(not bool(Storage._dependency_path("user://a.res::user://b.res").ok), "ambiguous dependency paths fail closed")
	var shader := Shader.new()
	shader.code = "shader_type spatial; void fragment() { ALBEDO = vec3(0.2); }"
	var shader_path := "user://native-storage-external.gdshader"
	_check(ResourceSaver.save(shader, shader_path) == OK, "explicit external shader fixture")
	shader.take_over_path(shader_path)
	var shader_material := ShaderMaterial.new()
	shader_material.shader = shader
	var shader_native := _save(shader_material, "external-material.res")
	_check(not bool(Storage.closure(shader_native, known, {}, root_path).ok), "unknown external native dependency fails closed")
	var external_inputs := {Prepared.logical_source(shader_path): FileAccess.get_sha256(shader_path)}
	_check(bool(Storage.closure(shader_native, known, external_inputs, root_path).ok), "exact explicitly hashed external shader accepted")
	var shader_bytes := FileAccess.get_file_as_bytes(shader_path)
	_write(shader_path, shader_bytes + PackedByteArray([32]))
	_check(not bool(Storage.closure(shader_native, known, external_inputs, root_path).ok), "declared external dependency mutation rejects")
	_write(shader_path, shader_bytes)
	var external_entry := _entry(shader_native, external_inputs)
	var restored_texture := ResourceLoader.load(shared, "ImageTexture", ResourceLoader.CACHE_MODE_IGNORE) as ImageTexture
	_check(restored_texture != null and TextureSizes.restore_verified(restored_texture), "compressed texture readback preserves logical-size metadata")
	var restored_image := restored_texture.get_image()
	_check(restored_texture.get_width() == 13 and restored_texture.get_height() == 9 \
		and restored_image.get_format() == image.get_format() and restored_image.get_mipmap_count() == image.get_mipmap_count() \
		and restored_image.get_data() == image.get_data(), "compressed texture preserves exact GPU data/format/mips and NPOT dimensions")
	var animation := Animation.new()
	var track := animation.add_track(Animation.TYPE_POSITION_3D)
	animation.track_set_path(track, NodePath("Rig:position"))
	animation.position_track_insert_key(track, 1.0 / 30.0, Vector3(1.0, 2.0, 3.0))
	animation.position_track_insert_key(track, 2.000000000245, Vector3(2.0, 3.0, 4.0))
	var candidate := animation.duplicate(false) as Animation
	_check(AnimationKeys.prepare(animation, candidate) and AnimationKeys.restore_verified(candidate), "f64 native animation metadata setup")
	candidate.remove_meta(AnimationKeys.PUBLISHED)
	var animation_path := _save(candidate, "animation.res")
	var restored_animation := ResourceLoader.load(animation_path, "Animation", ResourceLoader.CACHE_MODE_IGNORE) as Animation
	_check(restored_animation != null and AnimationKeys.restore_verified(restored_animation), "compressed animation exact clock restoration")
	_check(restored_animation.track_get_key_time(track, 0) == animation.track_get_key_time(track, 0) \
		and restored_animation.track_get_key_time(track, 1) == animation.track_get_key_time(track, 1) \
		and restored_animation.track_get_key_value(track, 1) == animation.track_get_key_value(track, 1), "compressed animation preserves exact clock and value contract")
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material_a)
	var mesh_path := _save(mesh, "mesh.res")
	var restored_mesh := ResourceLoader.load(mesh_path, "ArrayMesh", ResourceLoader.CACHE_MODE_IGNORE) as ArrayMesh
	_check(restored_mesh != null and restored_mesh.get_surface_count() == 1 \
		and restored_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == arrays[Mesh.ARRAY_VERTEX], "compressed native mesh vertex buffers roundtrip")
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.mesh = mesh
	multi.instance_count = 2
	var transform := Transform3D(Basis.IDENTITY, Vector3(1.25, 2.5, 3.75))
	multi.set_instance_transform(0, Transform3D.IDENTITY)
	multi.set_instance_transform(1, transform)
	var multi_path := _save(multi, "multimesh.res")
	var restored_multi := ResourceLoader.load(multi_path, "MultiMesh", ResourceLoader.CACHE_MODE_IGNORE) as MultiMesh
	_check(restored_multi != null and restored_multi.buffer.size() == 24 and restored_multi.buffer == multi.buffer \
		and restored_multi.get_instance_transform(1) == transform, "compressed actual renderer MultiMesh buffers/transforms roundtrip")
	var scene_root := Node3D.new()
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	scene_root.add_child(instance)
	instance.owner = scene_root
	var scene := PackedScene.new()
	_check(scene.pack(scene_root) == OK, "synthetic shared mesh scene pack")
	scene_root.free()
	var scene_path := _save(scene, "scene.scn")
	var restored_scene := ResourceLoader.load(scene_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var restored_root := Lifecycle.instantiate({"status": "hit", "resource": restored_scene, "entry": {}})
	_check(restored_root != null and restored_root.get_child_count() == 1, "compressed actual scene instantiation")
	if restored_root != null: restored_root.free()
	var entries: Array = [a, b, external_entry, _entry(animation_path), _entry(mesh_path), _entry(multi_path), _entry(scene_path)]
	var invalid_entries := entries.duplicate(true)
	invalid_entries[1].payloads.pop_back()
	_check(not bool(Storage.finalize(root_path, invalid_entries, known).ok), "generation verifies every complete root before any deletion")
	_check(FileAccess.file_exists(orphan) and FileAccess.file_exists(only_b), "failed closure validation preserves orphan/shared queues intact")
	var foreign := root_path.path_join("unowned.txt")
	_write(foreign, PackedByteArray([1, 2, 3]))
	_check(not bool(Storage.finalize(root_path, entries, known).ok), "foreign generation file fails ownership check before deletion")
	_check(FileAccess.file_exists(orphan), "foreign-file failure leaves planned orphan intact")
	DirAccess.remove_absolute(foreign)
	var generated_copy := known.duplicate(true)
	var finalized := Storage.finalize(root_path, entries, known)
	_check(bool(finalized.ok), "generation union finalizes")
	_check(known == generated_copy, "finalization never mutates caller identity maps")
	_check(not FileAccess.file_exists(orphan) and FileAccess.file_exists(shared) and FileAccess.file_exists(only_b), "only truly unreferenced embedded image artifact is removed")
	_check(int(finalized.stats.removed_files) == 1 and int(finalized.stats.reachable_files) == known.size() - 1 \
		and int(finalized.stats.saved_bytes) == int(finalized.stats.reachable_bytes) + int(finalized.stats.removed_bytes), "honest compressed generation byte accounting")
	for entry: Dictionary in entries:
		_check(bool(Storage.closure(str(entry.resource), finalized.payloads, external_inputs, root_path).ok), "all primary roots retain complete exact closure after cleanup")
	for filename: String in DirAccess.get_files_at(root_path):
		DirAccess.remove_absolute(root_path.path_join(filename))
	DirAccess.remove_absolute(root_path)
	DirAccess.remove_absolute(shader_path)
	await process_frame
	await physics_frame
	await process_frame
	_check(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)) == nodes_before, "owned scene cleanup returns Node count")
	print("PREPARED_NATIVE_STORAGE_CHECKS checks=", checks, " failures=", failures)
	quit(1 if failures else 0)

extends SceneTree
## Standalone renderer probe; requires no game assets or autoloads.
func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var batch := MultiMesh.new()
	batch.transform_format = MultiMesh.TRANSFORM_3D
	batch.mesh = mesh
	batch.instance_count = 1
	var transform := Transform3D(Basis.IDENTITY, Vector3(1, 2, 3))
	batch.set_instance_transform(0, transform)
	await process_frame
	var saved := ResourceSaver.save(batch, "user://release-buffer.res") == OK
	var loaded := ResourceLoader.load("user://release-buffer.res", "", ResourceLoader.CACHE_MODE_IGNORE) as MultiMesh
	var valid: bool = saved and loaded != null and loaded.buffer.size() == 12 \
		and loaded.get_instance_transform(0).is_equal_approx(transform) \
		and mesh.get_surface_count() == 1 and mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size() == 3
	print("RABBITLANDS_RELEASE_GRAPHICS ", JSON.stringify({
		"adapter_name": RenderingServer.get_video_adapter_name(),
		"adapter_type": RenderingServer.get_video_adapter_type(),
		"rendering_method": RenderingServer.get_current_rendering_method(),
		"rendering_driver": RenderingServer.get_current_rendering_driver_name(),
		"resource_buffer_probe": valid}))
	loaded = null
	batch = null
	mesh = null
	quit(0 if valid else 1)

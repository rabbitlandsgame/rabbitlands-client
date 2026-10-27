extends SceneTree
## Bake input from the same raw/imported mesh and Head frame used by grooming.
func _init() -> void:
	call_deferred("run")
func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var output := OS.get_environment("RL_STUBBLE_INPUT")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/stubble-inputs")
	DirAccess.make_dir_recursive_absolute(output)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	for sex: String in ["male", "female"]:
		var config: Dictionary = models["luminous_" + sex]
		var source := GlbSceneCache.instantiate(config.scene)
		root.add_child(source)
		var skeleton := source.find_child("*", true, false) as Skeleton3D
		for node: Node in source.find_children("*", "Skeleton3D", true, false):
			skeleton = node as Skeleton3D
			break
		var frame := skeleton.get_bone_global_rest(skeleton.find_bone("Head"))
		var eyes := source.find_child("eyes", true, false) as MeshInstance3D
		var eye_height := PortraitGroom._eye_height(eyes, skeleton, frame, source)
		var body := source.find_child("body", true, false) as MeshInstance3D
		var transform := frame.affine_inverse() * PortraitGroom._to_root(skeleton, source).affine_inverse() * PortraitGroom._to_root(body, source)
		var arrays := body.mesh.surface_get_arrays(0)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var vertices: Array = []
		for index: int in points.size():
			var point := transform * points[index]
			var normal := (transform.basis.inverse().transposed() * normals[index]).normalized()
			vertices.append([point.x, point.y, point.z, uvs[index].x, uvs[index].y, normal.z])
		var record := {"vertices": vertices, "indices": Array(indices), "eye_height": eye_height,
			"source_sha256": FileAccess.get_sha256(config.scene), "source": config.scene}
		FileAccess.open(output.path_join(sex + ".json"), FileAccess.WRITE).store_string(JSON.stringify(record))
		source.free()
	print("STUBBLE_EXPORT: PASS")
	quit()

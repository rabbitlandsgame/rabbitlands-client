extends SceneTree

const REFRESH := preload("res://src/world/object_material_refresh.gd")

var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var timber := _mesh("QuayPlanks")
	var stone := _mesh("QuayStone")
	var record := _override("QuayPlanks", 0)
	_expect(REFRESH.apply_overrides([record], [timber, stone]) == 1 and
		timber.get_surface_override_material(0) is ShaderMaterial and
		stone.get_surface_override_material(0) == null,
		"exact node and surface targeting changes only the declared object slot")
	var material := timber.get_surface_override_material(0) as ShaderMaterial
	_expect(material.get_shader_parameter("uv_scale") == Vector3(0.65, 0.4, 1.0) and
		is_equal_approx(float(material.get_shader_parameter(
			"texture_rotation_radians")), deg_to_rad(23.0)),
		"object mesh UV scale and rotation reach the oriented runtime material")
	var global_catalog := {"schema": REFRESH.SCHEMA,
		"assets": {"quay": [record]}}
	var explicit_empty := {"asset": {"id": "quay"},
		"objectMaterialOverrides": {"schema": REFRESH.SCHEMA, "entries": []}}
	_expect((REFRESH._records_for_manifest(explicit_empty, global_catalog) as Array).is_empty(),
		"an explicit empty child override list suppresses stale global entries")
	var changed_record := record.duplicate(true)
	changed_record.material.rotationDegrees = -31.0
	var inline_manifest := {"asset": {"id": "quay"},
		"objectMaterialOverrides": {"schema": REFRESH.SCHEMA,
			"entries": [changed_record]}}
	var inline_target := _mesh("QuayPlanks")
	var inline_records := REFRESH._records_for_manifest(inline_manifest,
		global_catalog) as Array
	_expect(REFRESH.apply_overrides(inline_records, [inline_target]) == 1 and
		is_equal_approx(float((inline_target.get_surface_override_material(0) as \
		ShaderMaterial).get_shader_parameter("texture_rotation_radians")),
		deg_to_rad(-31.0)),
		"fresh child entries take precedence over different global catalog values")

	var duplicate := _mesh("QuayPlanks")
	print("Expected fail-closed warnings: ambiguous name, changed texture, missing node, invalid slot.")
	_expect(REFRESH.apply_overrides([record], [timber, duplicate]) == 0,
		"ambiguous node names fail closed instead of changing both objects")
	var fallback := _mesh("QuayPlanks")
	var tampered := record.duplicate(true)
	tampered.material.textureSha256.normalTexture = "0".repeat(64)
	_expect(REFRESH.apply_overrides([tampered], [fallback]) == 0 and
		fallback.get_surface_override_material(0) == null,
		"a changed bound detail texture retains the imported GLB material")
	var missing := record.duplicate(true)
	missing.nodeName = "MissingNode"
	var bad_surface := record.duplicate(true)
	bad_surface.surfaceIndex = 4
	_expect(REFRESH.apply_overrides([missing, bad_surface], [fallback]) == 0,
		"missing paths and invalid surface slots never broaden the match")
	var null_optional := record.duplicate(true)
	null_optional.material.normalTexture = null
	null_optional.material.ormTexture = null
	null_optional.material.textureSha256.erase("normalTexture")
	null_optional.material.textureSha256.erase("ormTexture")
	var null_optional_target := _mesh("QuayPlanks")
	var null_optional_applied := REFRESH.apply_overrides([null_optional],
		[null_optional_target])
	var null_optional_material := null_optional_target.get_surface_override_material(
		0) as ShaderMaterial
	_expect(null_optional_applied == 1 and null_optional_material != null and
		null_optional_material.get_shader_parameter("use_normal_map") == false and
		null_optional_material.get_shader_parameter("use_orm_map") == false,
		"catalog null optional textures produce a valid albedo-only material")

	print("object material refresh: %d assertions, %d failures" % [8, failures])
	timber.free()
	stone.free()
	duplicate.free()
	fallback.free()
	inline_target.free()
	null_optional_target.free()
	call_deferred("_finish", 1 if failures else 0)


func _finish(exit_code: int) -> void:
	await process_frame
	quit(exit_code)


func _override(node_name: String, surface_index: int) -> Dictionary:
	var albedo := "res://src/dev/map_authoring_pilot/style/texture_packs/marine-timber/marine-timber-v001.png"
	var normal := "res://src/dev/map_authoring_pilot/style/textures/timber-normal.png"
	var orm := "res://src/dev/map_authoring_pilot/style/textures/timber-orm.png"
	return {"nodeName": node_name, "surfaceIndex": surface_index,
		"material": {"preset": "Marine timber", "albedoTexture": albedo,
			"normalTexture": normal, "ormTexture": orm,
			"textureSha256": {
				"albedoTexture": _sha(albedo), "normalTexture": _sha(normal),
				"ormTexture": _sha(orm)},
			"albedoColor": [1.0, 1.0, 1.0, 1.0], "roughness": 0.84,
			"metallic": 0.0, "normalStrength": 0.8,
			"uvScale": [0.65, 0.4], "uvOffset": [0.1, -0.2],
			"rotationDegrees": 23.0}}


func _sha(path: String) -> String:
	return FileAccess.get_sha256(ProjectSettings.globalize_path(path))


func _mesh(name_value: String) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = name_value
	node.mesh = BoxMesh.new()
	return node


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error(message)

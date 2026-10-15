extends SceneTree

const BLEND := preload("res://src/world/biome_blend_material.gd")
const SURFACE := preload(
	"res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload(
	"res://src/dev/map_authoring_pilot/style/texture_presets.gd")

var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var json_probe := "res://test-artifacts/biome-catalog-cache-probe.json"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(
		json_probe.get_base_dir()))
	_write_text(json_probe, "{\"value\":1}")
	BLEND.begin_source_verification()
	var first_json: Variant = BLEND.cached_json(json_probe)
	_write_text(json_probe, "{\"value\":2}")
	BLEND.begin_source_verification()
	var revised_json: Variant = BLEND.cached_json(json_probe)
	_expect(first_json is Dictionary and int(first_json.value) == 1 and
		revised_json is Dictionary and int(revised_json.value) == 2,
		"an explicit editor refresh invalidates a rapid same-size catalog edit")
	var digest_probe := "res://test-artifacts/biome-source-digest-probe.bin"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(
		digest_probe.get_base_dir()))
	_write_bytes(digest_probe, PackedByteArray([1, 2, 3]))
	BLEND.begin_source_verification()
	var first_digest := BLEND.source_sha256(digest_probe)
	_expect(first_digest == BLEND.source_sha256(digest_probe),
		"unchanged source textures reuse the same verified digest")
	_write_bytes(digest_probe, PackedByteArray([1, 2, 3, 4]))
	_expect(BLEND.source_sha256(digest_probe) != first_digest,
		"changed source texture bytes invalidate the digest cache")
	var mask_path := "res://src/dev/map_authoring_pilot/style/textures/ground-basecolor.png"
	var mask_sha := FileAccess.get_sha256(ProjectSettings.globalize_path(mask_path))
	var moor := SURFACE.from_preset(PRESETS.GRASS)
	moor.enable_region_uv_projection(0.17)
	moor.texture_preset = PRESETS.MOOR_PEAT_HEATHER
	var custom_material := StandardMaterial3D.new()
	custom_material.albedo_texture = load(
		"res://src/dev/map_authoring_pilot/style/textures/stone-basecolor.png")
	custom_material.uv1_scale = Vector3(0.75, 0.5, 1.0)
	custom_material.uv1_offset = Vector3(0.1, 0.2, 0.0)
	var custom := SURFACE.from_material(custom_material, PRESETS.CUSTOM)
	custom.rotation_degrees = 37.0
	var editor := BLEND.create_editor(custom, 0.24, Vector3(1200, 0, 720))
	_expect(editor != null, "saved Custom UV materials create an editor blend material")
	if editor != null:
		var inverse: Vector4 = editor.get_shader_parameter(
			"base_uv_metres_inverse")
		var scale_x: Vector4 = editor.get_shader_parameter("base_uv_scale_x")
		var rotation: Vector4 = editor.get_shader_parameter(
			"base_rotation_radians")
		_expect(is_equal_approx(inverse[0], 0.24) and
			is_equal_approx(scale_x[0], 0.75) and
			is_equal_approx(rotation[0], deg_to_rad(37.0)),
			"Custom scale and rotation reach the shared shader without reinterpretation")
	var named := BLEND.create_editor(moor, 0.17, Vector3.ZERO)
	_expect(named != null and is_equal_approx(float((named.get_shader_parameter(
		"base_uv_scale_x") as Vector4)[0]), 0.25 / 0.17) and
		is_equal_approx(0.17 * float((named.get_shader_parameter(
		"base_uv_scale_x") as Vector4)[0]), 0.25),
		"new terrain presets preserve their 4m world repeat at the saved UV density")
	var secondary_dropdown := SURFACE.from_preset(PRESETS.GRASS)
	secondary_dropdown.enable_region_uv_projection(0.17)
	secondary_dropdown.texture_preset = PRESETS.FOREST_FLOOR_MOSS
	var secondary_material := secondary_dropdown.source_material as BaseMaterial3D
	_expect(is_equal_approx(secondary_material.uv1_scale.x, 0.25 / 0.17),
		"secondary palette dropdown changes use the same terrain-aware repeat")
	secondary_material.uv1_scale = Vector3(0.83, 0.61, 1.0)
	secondary_dropdown.rotation_degrees = 29.0
	secondary_dropdown.enable_region_uv_projection(0.17)
	var authored_secondary := BLEND.surface_palette(secondary_dropdown, 0.17)
	_expect(_array_vec2(authored_secondary.uvScale).is_equal_approx(
		Vector2(0.83, 0.61)) and is_equal_approx(float(
		authored_secondary.rotationDegrees), 29.0),
		"refresh preserves a named preset's authored UV scale and rotation")

	var config := {
		"schema": "eloria-biome-blend-v1",
		"coordinateSpace": "continent-global-xz",
		"origin": [288.0, 1536.0],
		"innerSize": [64, 64], "gutter": 1, "metresPerPixel": 1.5,
		"baseMask": {"path": mask_path, "sha256": mask_sha},
		"secondaryMask": {"path": mask_path, "sha256": mask_sha},
		"palettes": [{"id": "grey_moors:base",
			"base": _palette(PRESETS.MOOR_PEAT_HEATHER,
				"res://src/dev/map_authoring_pilot/style/texture_packs/moor-peat-heather/moor-peat-heather-v001.png",
				1.0, 12.0),
			"secondary": _palette(PRESETS.GRASS,
				"res://src/dev/map_authoring_pilot/style/textures/ground-basecolor.png",
				0.8, -18.0)}],
		"dominantPaletteId": "grey_moors:base",
	}
	var json_config: Variant = JSON.parse_string(JSON.stringify(config))
	_expect(json_config is Dictionary and BLEND._valid_config(json_config),
		"catalog JSON numeric arrays validate after their integer values parse as floats")
	var runtime := BLEND.create_runtime(config, Vector3(290, 0, 1493))
	var runtime_transform: Transform3D = runtime.get_shader_parameter(
		"terrain_to_continent") if runtime != null else Transform3D.IDENTITY
	_expect(runtime != null and runtime_transform.origin == Vector3(290, 0, 1493),
		"portable manifest masks and continent translation create a runtime material")
	if runtime != null:
		_expect(runtime.get_shader_parameter("base_tint_0") == Color.WHITE and
			runtime.get_shader_parameter("base_tint_1") == Color.WHITE,
			"each palette tint binds as an explicit nonzero shader color")
		var secondary_rotation: Vector4 = runtime.get_shader_parameter(
			"secondary_rotation_radians")
		_expect(is_equal_approx(secondary_rotation[0], deg_to_rad(-18.0)),
			"secondary palette rotation is preserved independently")

	var loader := WorldLoader.new()
	loader.manifest = WorldManifest.new()
	loader.manifest.data = {"continentGeography": {"translation": [290, 0, 1493]},
		"biomeBlend": config}
	loader.world_root = Node3D.new()
	loader.add_child(loader.world_root)
	var terrain_group := Node3D.new()
	terrain_group.position = Vector3(8, 0, -12)
	loader.world_root.add_child(terrain_group)
	var terrain := _mesh("AuthoredGround_grey_moorsBase_09_16")
	terrain.position = Vector3(-4, 0, 7)
	terrain_group.add_child(terrain)
	var overlay := _mesh("AuthoredGround_grey_moorsBaseCampGroundRegion_09_16")
	var road := _mesh("Road_grey_moors_09_16")
	_expect(loader._apply_biome_blend([terrain, overlay, road]) == 1 and
		terrain.get_surface_override_material(0) is ShaderMaterial and
		overlay.get_surface_override_material(0) == null and
		road.get_surface_override_material(0) == null,
		"loader replaces only authored base terrain and preserves overlays and roads")
	var assigned := terrain.get_surface_override_material(0) as ShaderMaterial
	var terrain_to_continent: Transform3D = assigned.get_shader_parameter(
		"terrain_to_continent")
	_expect((terrain_to_continent * Vector3.ZERO).is_equal_approx(
		Vector3(294, 0, 1488)),
		"nested imported terrain records its canonical continent transform")
	loader.world_root.position = Vector3(-500, 0, 300)
	_expect(terrain_to_continent == assigned.get_shader_parameter(
		"terrain_to_continent"),
		"stream handoff and recentering do not move the world-space texture phase")
	var neighbour := WorldLoader.new()
	neighbour.manifest = WorldManifest.new()
	neighbour.manifest.data = {"continentGeography": {
		"translation": [400, 0, 1500]}, "biomeBlend": config}
	neighbour.world_root = Node3D.new()
	neighbour.add_child(neighbour.world_root)
	var neighbour_terrain := _mesh("AuthoredGround_grey_moorsBase_09_16")
	neighbour_terrain.position = Vector3(-106, 0, -12)
	neighbour.world_root.add_child(neighbour_terrain)
	neighbour._apply_biome_blend([neighbour_terrain])
	var neighbour_material := neighbour_terrain.get_surface_override_material(
		0) as ShaderMaterial
	var neighbour_transform: Transform3D = neighbour_material.get_shader_parameter(
		"terrain_to_continent")
	_expect((neighbour_transform * Vector3.ZERO).is_equal_approx(
		terrain_to_continent * Vector3.ZERO),
		"repositioned regional chunks agree at the same continent-space sample")
	loader.manifest.data.biomeBlend.baseMask.sha256 = "0".repeat(64)
	var untouched := _mesh("AuthoredGround_grey_moorsBase_10_16")
	_expect(loader._apply_biome_blend([untouched]) == 0 and
		untouched.get_surface_override_material(0) == null,
		"changed mask hashes fail closed to the exported dominant PBR fallback")
	loader.manifest.data.biomeBlend.baseMask.sha256 = mask_sha
	loader.manifest.data.biomeBlend.palettes[0].base.textureSha256.albedoTexture = \
		"0".repeat(64)
	var texture_tamper := _mesh("AuthoredGround_grey_moorsBase_11_16")
	print("Expected fail-closed warnings: changed mask and palette texture hashes.")
	_expect(loader._apply_biome_blend([texture_tamper]) == 0 and
		texture_tamper.get_surface_override_material(0) == null,
		"changed palette texture hashes also retain the dominant PBR fallback")
	loader.manifest.data = {"asset": {"id": "grey_moors__chunk_03_05"},
		"continentGeography": {"translation": [220, 0, 420]},
		"biomeBlend": null}
	var opted_out := _mesh("AuthoredGround_grey_moorsBase_03_05")
	_expect(BLEND.catalog_config(loader.manifest.data) is Dictionary and
		loader._apply_biome_blend([opted_out]) == 0 and
		opted_out.get_surface_override_material(0) == null,
		"a fresh child manifest opt-out suppresses an older global catalog entry")

	print("biome blend material: %d assertions, %d failures" % [19, failures])
	overlay.free()
	road.free()
	untouched.free()
	texture_tamper.free()
	opted_out.free()
	loader.free()
	neighbour.free()
	call_deferred("_finish", 1 if failures else 0)


func _finish(exit_code: int) -> void:
	await process_frame
	quit(exit_code)


func _palette(preset: String, texture: String, scale: float,
		rotation: float) -> Dictionary:
	return {"preset": preset, "albedoTexture": texture,
		"textureSha256": {"albedoTexture": FileAccess.get_sha256(
			ProjectSettings.globalize_path(texture))},
		"albedoColor": [1.0, 1.0, 1.0, 1.0], "roughness": 0.95,
		"metallic": 0.0, "normalStrength": 0.0,
		"baseUvMetresInverse": 0.24, "uvScale": [scale, scale],
		"uvOffset": [0.0, 0.0], "rotationDegrees": rotation}


func _array_vec2(value: Array) -> Vector2:
	return Vector2(float(value[0]), float(value[1]))


func _write_bytes(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()


func _write_text(path: String, value: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(value)
	file.close()


func _mesh(name_value: String) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = name_value
	instance.mesh = BoxMesh.new()
	return instance


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error(message)

extends SceneTree

const ExternalTexturePool := preload("res://src/world/external_texture_pool.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _water(parent: Node3D, name_value: String, at: Vector3) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = name_value
	var plane := PlaneMesh.new()
	plane.material = StandardMaterial3D.new()
	node.mesh = plane
	node.position = at
	parent.add_child(node)
	return node

func _loader(origin: Vector3) -> WorldLoader:
	var loader := WorldLoader.new()
	root.add_child(loader)
	loader.world_root = Node3D.new()
	loader.add_child(loader.world_root)
	loader.manifest = WorldManifest.new()
	loader.manifest.data = {"continentGeography": {}, "streamingBorders": [
		{"globalTranslation": [origin.x, origin.y, origin.z]}]}
	return loader

func _image_load_calls() -> int:
	return int(ExternalTexturePool.retention_snapshot().get("image_load_calls", -1))

func _expect_no_wave_load(loader: WorldLoader, meshes: Array, message: String) -> void:
	var before := _image_load_calls()
	_expect(loader._apply_continent_water(meshes) == 0, message + ": no material is replaced")
	_expect(_image_load_calls() == before, message + ": no wave texture is requested")

func _run() -> void:
	_expect(_image_load_calls() >= 0, "Texture acquisition diagnostics expose image_load_calls")
	var dry := _loader(Vector3(618, 0, 1490))
	var dry_floor := _water(dry.world_root, "Terrain_Floor", Vector3.ZERO)
	var raised_pond := _water(dry.world_root, "Water_RaisedPond", Vector3(0, 5, 0))
	var custom_water := _water(dry.world_root, "Water_CustomShader", Vector3.ZERO)
	var custom_material := ShaderMaterial.new()
	custom_material.shader = preload("res://src/world/continent_water.gdshader")
	(custom_water.mesh as PlaneMesh).material = custom_material
	_expect_no_wave_load(dry, [], "An empty continent chunk")
	_expect_no_wave_load(dry, [dry_floor], "A dry continent chunk")
	_expect_no_wave_load(dry, [raised_pond], "A raised authored pond")
	_expect_no_wave_load(dry, [custom_water], "A named sea-level surface with a non-BaseMaterial shader")
	_expect(dry_floor.get_surface_override_material(0) == null
		and raised_pond.get_surface_override_material(0) == null
		and custom_water.get_surface_override_material(0) == null,
		"Ineligible continent surfaces preserve their authored materials")
	var west := _loader(Vector3(618, 0, 1490))
	var group := Node3D.new()
	group.position = Vector3(12, 0, -4)
	west.world_root.add_child(group)
	var water := _water(group, "Water_Delta", Vector3(30, 0, 20))
	var pond := _water(group, "Water_RaisedPond", Vector3(0, 5, 0))
	var floor := _water(group, "Terrain_Floor", Vector3.ZERO)
	_expect(west._apply_continent_water([water, pond, floor]) == 1,
		"Only sea-level water changes; raised ponds and ground retain their authored materials")
	var material := water.get_surface_override_material(0) as ShaderMaterial
	_expect(bool(material.get_shader_parameter("has_wave_texture"))
		and material.get_shader_parameter("wave_texture") is Texture2D,
		"A region without a packaged water_lake material still loads the shared texture")
	var transform: Transform3D = material.get_shader_parameter("water_to_continent")
	_expect((transform * Vector3.ZERO).is_equal_approx(Vector3(660, 0, 1506)),
		"Nested local placement contributes to the continent water coordinates")
	var east := _loader(Vector3(1144, 0, 1500))
	var peer := _water(east.world_root, "Water_Basin", Vector3(-484, 0, 6))
	east._apply_continent_water([peer])
	var peer_transform: Transform3D = (peer.get_surface_override_material(0) as ShaderMaterial).get_shader_parameter("water_to_continent")
	_expect(transform.is_equal_approx(peer_transform), "Both map frames sample the same water at a shared physical point")
	_expect(material.get_shader_parameter("wave_texture") == (peer.get_surface_override_material(0) as ShaderMaterial).get_shader_parameter("wave_texture"),
		"Independently loaded chunks reuse one actual GPU wave texture")
	var island := _loader(Vector3.ZERO)
	island.manifest.data = {"continentGeography": {"translation": [350, 0, 1410]}}
	var coast := _water(island.world_root, "Water_Sea", Vector3(10, 0, -10))
	_expect(island._apply_continent_water([coast]) == 1,
		"A ferry-only territory applies shared sea rendering without any walking borders")
	var coast_material := coast.get_surface_override_material(0) as ShaderMaterial
	var coast_transform: Transform3D = coast_material.get_shader_parameter("water_to_continent")
	_expect((coast_transform * Vector3.ZERO).is_equal_approx(Vector3(360, 0, 1400)),
		"Ferry-only chunks use their canonical continent placement")
	island.manifest.data.streamingBorders = [{"globalTranslation": [999, 0, 999]}]
	island._apply_continent_water([coast])
	_expect(coast_transform == (coast.get_surface_override_material(0) as ShaderMaterial).get_shader_parameter("water_to_continent"),
		"Canonical geography takes precedence over legacy border placement")
	var shared := _loader(Vector3.ZERO)
	shared.manifest.data = {"asset": {"id": "mirrorhold__chunk_09_08"},
		"continentGeography": {"translation": [840, 0, 650], "geometryMode": "continent-chunks-v1"}}
	var lake := _water(shared.world_root, "Water_mirrorhold_09_08", Vector3(10, 82, -20))
	lake.mesh.surface_get_material(0).resource_name = "water_sea"
	var river := _water(shared.world_root, "Water_mirrorhold_08_08", Vector3(-10, 70, 15))
	river.rotation.x = deg_to_rad(12)
	river.mesh.surface_get_material(0).resource_name = "water_sea"
	var fountain := _water(shared.world_root, "Water_Fountain", Vector3.ZERO)
	fountain.mesh.surface_get_material(0).resource_name = "water_sea"
	var decorative := _water(shared.world_root, "Water_mirrorhold_09_07", Vector3.ZERO)
	decorative.mesh.surface_get_material(0).resource_name = "water_fountain"
	var authored_pool := _water(shared.world_root, "Water_mirrorhold_Pool", Vector3(0, 82, 0))
	authored_pool.mesh.surface_get_material(0).resource_name = "water_sea"
	_expect_no_wave_load(shared, [fountain, decorative, authored_pool],
		"Shared drainage with only decorative, non-sea and nonnumeric water names")
	var shared_loads_before := _image_load_calls()
	_expect(shared._apply_continent_water([lake, river, fountain, decorative, authored_pool]) == 2,
		"Exported elevated lakes and sloping rivers share water; retained fountains and authored pools are excluded")
	_expect(_image_load_calls() == shared_loads_before + 1,
		"Multiple eligible water surfaces request the shared texture once per apply call")
	var lake_material := lake.get_surface_override_material(0) as ShaderMaterial
	var river_material := river.get_surface_override_material(0) as ShaderMaterial
	_expect(lake_material != null and river_material != null,
		"Shared drainage does not depend on a flat sea-level bounding box")
	if lake_material != null and river_material != null:
		var lake_transform: Transform3D = lake_material.get_shader_parameter("water_to_continent")
		var river_transform: Transform3D = river_material.get_shader_parameter("water_to_continent")
		_expect((lake_transform * Vector3.ZERO).is_equal_approx(Vector3(850,82,630)),
			"An elevated lake retains its actual continent-space placement")
		_expect(river_transform.basis.is_equal_approx(river.basis),
			"A sloping river retains the mesh transform used for common ripple phase")
		_expect(lake_material.get_shader_parameter("wave_texture") == material.get_shader_parameter("wave_texture"),
			"Sea, lake and river surfaces reuse one actual wave texture")
	_expect(fountain.get_surface_override_material(0) == null and decorative.get_surface_override_material(0) == null
		and authored_pool.get_surface_override_material(0) == null,
		"Shared-continent water selection cannot recolour decorative surfaces")
	west.world_root.position = Vector3(-526, 0, -10)
	_expect(transform == material.get_shader_parameter("water_to_continent"),
		"A seamless scene rebase does not move the ripple phase")
	var packed := PackedScene.new()
	group.owner = west.world_root
	water.owner = west.world_root
	pond.owner = west.world_root
	floor.owner = west.world_root
	_expect(packed.pack(west.world_root) == OK, "Water overrides can be cached")
	var restored := packed.instantiate() as Node3D
	var restored_material := (restored.get_node(NodePath(str(group.name) + "/Water_Delta")) as MeshInstance3D).get_surface_override_material(0) as ShaderMaterial
	_expect(restored_material != null and restored_material.get_shader_parameter("water_to_continent") == transform,
		"Cached water retains the same continent transform")
	restored.free()
	dry.free()
	west.free()
	east.free()
	island.free()
	shared.free()
	print("continent water: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

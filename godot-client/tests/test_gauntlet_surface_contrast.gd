extends SceneTree
## Shared path/verge materials, cached source preservation and look switching.
const Contrast := preload("res://src/world/gauntlet_surface_contrast.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "test_gauntlet"}, "gauntlet": {},
		"environment": {"sun": {"enabled": true}}}
	var world := Node3D.new()
	root.add_child(world)
	var source := StandardMaterial3D.new()
	source.albedo_color = Color(.72, .65, .58)
	source.roughness = .83
	source.uv1_scale = Vector3(2, 3, 1)
	var image := Image.create(4, 4, false, Image.FORMAT_RGB8)
	image.fill(Color(.72, .78, .82))
	source.albedo_texture = ImageTexture.create_from_image(image)
	var original_colour := source.albedo_color
	var path := _mesh(world, "Walk_Terrain_ground", source)
	var other_path := _mesh(world, "Walk_floor_boss", source)
	var verge := _mesh(world, "Terrain_ground", source)
	var wall := _mesh(world, "Build_shell", source)
	var prop := _mesh(world, "Kit_statue", source)
	var water := _mesh(world, "Water_pool", source)
	var transparent := source.duplicate() as StandardMaterial3D
	transparent.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var threshold := _mesh(world, "Walk_threshold", transparent)
	var glow := source.duplicate() as StandardMaterial3D
	glow.emission_enabled = true
	glow.emission = Color(.08, .03, .14)
	var luminous_path := _mesh(world, "Walk_luminous_road", glow)
	var luminous_verge := _mesh(world, "Terrain_luminous_cliff", glow)
	var lamp := _mesh(world, "Build_lamp", glow)
	var loader := WorldLoader.new()
	root.add_child(loader)
	loader.world_root = world
	loader._snapshot_for_cache()
	_expect(Contrast.apply(manifest, world) == 6, "only opaque path, verge and shell surfaces are adjusted")
	var made := path.get_active_material(0) as BaseMaterial3D
	var verge_made := verge.get_active_material(0) as BaseMaterial3D
	_expect(made != source and made == other_path.get_active_material(0), "paths share one copy of the source")
	_expect(made != verge_made and verge_made != wall.get_active_material(0), "shared source splits by surface role")
	_expect(_luma(made.albedo_color) > 2.0 * _luma(verge_made.albedo_color), "path and verge differ in value even with the same texture")
	_expect(made.albedo_texture == source.albedo_texture and made.roughness == source.roughness
		and made.uv1_scale == source.uv1_scale, "texture detail, roughness and UV repeat are preserved")
	_expect(source.albedo_color == original_colour and path.mesh.surface_get_material(0) == source,
		"source material and mesh remain unchanged")
	_expect(prop.get_active_material(0) == source and water.get_active_material(0) == source
		and threshold.get_active_material(0) == transparent and lamp.get_active_material(0) == glow,
		"props, water, transparent geometry and emissive fixtures remain authored")
	_expect(luminous_path.get_active_material(0) != glow and luminous_verge.get_active_material(0) != glow,
		"luminous amethyst ground also receives route contrast")
	_expect(Contrast.apply(manifest, world) == 0, "repeated application does not compound the tint")
	for mode: int in [LookProfile.Mode.ORIGINAL, LookProfile.Mode.PAINTED_GROUND, LookProfile.Mode.FULL_PAINTED]:
		LookProfile.set_player_mode(mode)
		LookSwitch.sync(world, manifest, true)
		_expect(path.get_active_material(0) == made, "route contrast survives appearance mode %d" % mode)
	# The snapshot predates the presentation pass: cache packing sees the
	# original materials; both a cache hit and a new import can apply it once.
	var undo := loader._restore_pristine()
	var cached := PackedScene.new()
	var packed := cached.pack(world)
	loader._undo_pristine(undo)
	_expect(packed == OK, "the map snapshot packs")
	if packed == OK:
		var restored := cached.instantiate() as Node3D
		root.add_child(restored)
		var restored_path := restored.get_node("Walk_Terrain_ground") as MeshInstance3D
		_expect(not restored_path.get_active_material(0).has_meta(Contrast.APPLIED_META), "cache stores the source appearance")
		_expect(Contrast.apply(manifest, restored) == 6, "cached maps receive the same route contrast")
		restored.free()
	var ordinary := WorldManifest.new()
	ordinary.data = {"environment": {"sun": {"enabled": true}}}
	_expect(Contrast.apply(ordinary, world) == 0, "non-gauntlet maps are unaffected")
	loader._release_snapshot()
	loader.world_root = null
	loader.free()
	world.free()
	print("Gauntlet surface contrast: %s (%d failures)" % ["PASS" if failures == 0 else "FAIL", failures])
	quit(0 if failures == 0 else 1)

func _mesh(parent: Node3D, label: String, material: Material) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name = label
	var plane := PlaneMesh.new()
	plane.material = material
	mesh.mesh = plane
	parent.add_child(mesh)
	mesh.owner = parent
	return mesh

func _luma(colour: Color) -> float:
	var value := colour if RenderingServer.get_current_rendering_method() == "gl_compatibility" else colour.srgb_to_linear()
	return Contrast.LUMA.dot(Vector3(value.r, value.g, value.b))

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

extends SceneTree
## Headless contracts; --roads PATH selects an ignored compact producer fixture.
const Road := preload("res://src/world/road_ground/road_ground.gd")
const Data := preload("res://src/world/road_ground/field_data.gd")
const Feet := preload("res://src/audio/footstep_surface.gd")
const Grass := preload("res://src/world/look/grass_beds.gd")
var failures: Array[String] = []
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_expect(bool(Road.prepare({}, "").get("absent", false)), "absent_legacy_field_is_no_op")
	_expect(not bool(Road.prepare({"metadata": "missing.json", "sha256": "0".repeat(64)}, "res://../eloria-assets/world.json").ok), "required_missing_field_fails")
	_expect(Data.safe_path("res://../eloria-assets", "../../private").is_empty(), "outside_asset_path_rejected")
	_expect(Data.safe_path("res://../eloria-assets", "C:/private").is_empty(), "absolute_resource_rejected")
	_expect(not Road.valid_matrix([1, 2]), "invalid_frame_rejected")
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for index: int in args.size():
		if args[index] == "--roads" and index + 1 < args.size():
			_actual(args[index + 1])
	print(JSON.stringify({"checks": checks, "failures": failures, "gpu_qualified": false}))
	quit(0 if failures.is_empty() else 1)

func _actual(path: String) -> void:
	var config := {"metadata": path.get_file(), "sha256": FileAccess.get_sha256(path)}
	var prepared: Dictionary = Road.prepare(config, path.get_base_dir().path_join("world.json"))
	_expect(bool(prepared.get("ok", false)), "actual_compact_decode: " + str(prepared.get("error", "")))
	if not bool(prepared.get("ok", false)):
		return
	var data: Resource = prepared.data
	_expect(not data.source_candidates.is_empty(), "worker_styles_remain_private")
	_expect(data.styles.size() == data.document.styles.size(), "all_authored_styles_prepared")
	_expect(bool(Road.revalidate(prepared).ok), "publication_closure_revalidated")
	var first_path: String = str(data.dependencies.keys()[0])
	var expected_digest: String = str(data.dependencies[first_path])
	data.dependencies[first_path] = "0".repeat(64)
	_expect(not bool(Road.revalidate(prepared).get("ok", true)), "changed_worker_dependency_fails_publication")
	data.dependencies[first_path] = expected_digest
	var root := Node3D.new()
	get_root().add_child(root)
	var target := MeshInstance3D.new()
	target.name = data.document.source_frame_node
	target.transform = Road.matrix(data.document.source_frame_matrix)
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, PlaneMesh.new().get_mesh_arrays())
	var source := StandardMaterial3D.new()
	source.resource_name = "wood_testBase"
	source.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh.surface_set_material(0, source)
	target.mesh = mesh
	root.add_child(target)
	# A raised blended patch already owns a pass. It must retain that pass's
	# alpha contract while receiving the same road evaluation as the Base.
	var patch := MeshInstance3D.new()
	patch.name = "AuthoredGround_testpatch"
	patch.mesh = mesh
	patch.transform = target.transform
	var patch_source := StandardMaterial3D.new()
	patch_source.cull_mode = BaseMaterial3D.CULL_DISABLED
	patch_source.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	patch_source.albedo_color = Color(0.7, 0.5, 0.3, 0.8)
	patch.set_surface_override_material(0, patch_source)
	root.add_child(patch)
	data.document.targets.append({"name": str(patch.name), "world_matrix": data.document.source_frame_matrix})
	var manifest := WorldManifest.new()
	manifest.data = {"continentGeography": {"region": data.document.region},
		"asset": {"id": str(data.document.region) + "__chunk_" + str(data.document.chunk)}}
	manifest.source_path = path.get_base_dir().path_join("world.json")
	var children: int = root.get_child_count()
	var installed: Dictionary = Road.bind(root, manifest, prepared)
	_expect(bool(installed.get("ok", false)), "existing_pass_bind: " + str(installed.get("error", "")))
	_expect(root.get_child_count() == children, "no_new_visual_or_collision_nodes")
	_expect(data.source_candidates.is_empty(), "publication_releases_private_glb_state")
	if bool(installed.get("ok", false)):
		var bytes: PackedByteArray = data.coverage_l0.get_data()
		var pixel := bytes.find(255)
		_expect(pixel >= 0, "fixture_has_road_interior")
		if pixel >= 0:
			var point := Vector3(data.origin.x + (pixel % data.width + 0.5) / data.ppm,
				0.0, data.origin.y + (pixel / data.width + 0.5) / data.ppm)
			var found: Dictionary = Road.query(target, root.global_transform * point)
			_expect(bool(found.get("present", false)) and float(found.get("coverage", 0.0)) > 0.99, "cpu_query_samples_shared_coverage")
			root.transform = Transform3D(Basis(Vector3.UP, 0.3), Vector3(200.0, 3.0, -400.0))
			var moved: Dictionary = Road.query(target, root.global_transform * point)
			_expect(is_equal_approx(float(moved.get("coverage", -1.0)), float(found.get("coverage", -2.0))), "cpu_query_survives_world_rebase")
			var terrain := MeshInstance3D.new()
			terrain.name = "Terrain_test"
			terrain.mesh = mesh
			root.add_child(terrain)
			var body := StaticBody3D.new()
			body.collision_layer = 8
			terrain.add_child(body)
			var footstep: String = Feet.from_hit({"collider": body, "position": root.global_transform * point})
			_expect(footstep == Feet.from_name(str(found.style.original_material_names[0])), "terrain_footstep_uses_road_style")
			var grass := Grass.new()
			grass._continent = true
			var ground: Vector3 = grass._classify({"collider": body, "position": root.global_transform * point,
				"normal": Vector3.UP, "face_index": 0}, Vector3.UP, [], [], 1)
			_expect(int(ground.x) == Grass.Ground.PATH and is_zero_approx(ground.y), "full_painted_grass_suppressed_by_cpu_road_field")
			grass.free()
			terrain.name = "Walk_AuthoredBridge_test"
			_expect(Feet.from_hit({"collider": body, "position": root.global_transform * point}) == Feet.from_name(source.resource_name), "bridge_ignores_underlying_road_field")
		var current: Material = target.get_active_material(0)
		_expect(current is ShaderMaterial and current.next_pass == null, "existing_single_material_pass")
		var patch_material := patch.get_active_material(0) as ShaderMaterial
		_expect(patch_material != null and patch_material.shader.code.contains("#define LOOK_GROUND_ALPHA"), "existing_patch_keeps_alpha_pass")
		var repeated: Dictionary = Road.rebind(root, manifest)
		_expect(bool(repeated.get("ok", false)), "retained_field_rebind")
	root.free()

func _expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures.append(label)

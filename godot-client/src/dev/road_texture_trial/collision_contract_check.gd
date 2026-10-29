extends SceneTree
## CPU/headless collision qualification against Godot's actual glTF importer.
## --headless --path godot-client --script res://src/dev/road_texture_trial/collision_contract_check.gd -- --trial PATH
const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const MeshExtension := preload("res://src/world/map_mesh_extension.gd")
var _failures: Array[String] = []
var _checks := 0
var _probes: Array[Vector3] = []
var _bodies: Array[Node] = []

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	Quantization.ensure_registered()
	Vram.ensure_registered()
	MeshExtension.ensure_registered()
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var paths: Array[String] = []
	for index: int in args.size():
		if args[index] == "--trial" and index + 1 < args.size():
			paths.append(args[index + 1])
	_expect(not paths.is_empty(), "trial_metadata_supplied")
	for path: String in paths:
		_prepare(path)
	for unused: int in 4:
		await physics_frame
	var space: PhysicsDirectSpaceState3D = root.get_world_3d().direct_space_state
	for point: Vector3 in _probes:
		var original_query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 2.0,
			point - Vector3.UP * 2.0, 8)
		var compact_query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 2.0,
			point - Vector3.UP * 2.0, 16)
		var original: Dictionary = space.intersect_ray(original_query)
		var compact: Dictionary = space.intersect_ray(compact_query)
		_expect(not original.is_empty() and not compact.is_empty(), "both_front_faces_hit")
		if not original.is_empty() and not compact.is_empty():
			_expect((original.position as Vector3).is_equal_approx(compact.position), "importer_collision_height")
			_expect((original.normal as Vector3).is_equal_approx(compact.normal), "importer_collision_normal")
	for body: Node in _bodies:
		body.queue_free()
	await process_frame
	print(JSON.stringify({"checks": _checks, "failures": _failures, "physics_probes": _probes.size(),
		"gpu_used": false, "backface_collision_enabled": false}))
	quit(0 if _failures.is_empty() else 1)

func _prepare(path: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		_expect(false, "trial_metadata_readable")
		return
	if parsed.get("chunks") is Array:
		for relative: Variant in parsed.chunks:
			_prepare(path.get_base_dir().path_join(str(relative)))
		return
	var data: Dictionary = parsed
	var source: String = str(data.get("source_directory", "")).path_join("world.glb")
	_expect(FileAccess.get_sha256(source) == str(data.get("source_glb_sha256", "")), "source_glb_unchanged")
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error: Error = document.append_from_file(source, state)
	_expect(error == OK, "production_gltf_importer")
	if error != OK:
		return
	var json: Dictionary = state.get_json()
	for row: Dictionary in data.get("nodes", []):
		var name: String = str(row.road_node_name)
		var source_mesh := -1
		for node: Dictionary in json.get("nodes", []):
			if str(node.get("name", "")) == name:
				source_mesh = int(node.get("mesh", -1))
		_expect(source_mesh >= 0, "source_road_mesh_exists")
		if source_mesh < 0:
			continue
		var imported: ImporterMesh = (state.get_meshes()[source_mesh] as GLTFMesh).mesh
		var source_faces: PackedVector3Array = _faces(imported, int(row.primitive_index))
		var result: Dictionary = Trial._collider(path.get_base_dir(), row)
		_expect(bool(result.get("ok", false)), "compact_collider_constructed")
		if not bool(result.get("ok", false)):
			continue
		var carrier: MeshInstance3D = result.node
		var compact_body := carrier.get_child(0) as StaticBody3D
		var compact_shape := (compact_body.get_child(0) as CollisionShape3D).shape as ConcavePolygonShape3D
		var compact_faces: PackedVector3Array = compact_shape.get_faces()
		_expect(Trial.MATERIAL._sha(source_faces.to_byte_array()) == Trial.MATERIAL._sha(compact_faces.to_byte_array()),
			"compact_triangles_equal_actual_godot_importer")
		_expect(not compact_shape.backface_collision, "one_sided_collision_preserved")
		var transform: Transform3D = Trial._matrix(row.world_matrix)
		carrier.transform = transform
		compact_body.collision_layer = 16
		root.add_child(carrier)
		_bodies.append(carrier)
		var original := StaticBody3D.new()
		original.collision_layer = 8
		original.transform = transform
		var shape := CollisionShape3D.new()
		var concave := ConcavePolygonShape3D.new()
		concave.set_faces(source_faces)
		shape.shape = concave
		original.add_child(shape)
		root.add_child(original)
		_bodies.append(original)
		for fraction: float in [0.2, 0.5, 0.8]:
			var start: int = (int(source_faces.size() * fraction) / 3) * 3
			for offset: int in range(0, source_faces.size(), 3):
				var at: int = (start + offset) % source_faces.size()
				var a: Vector3 = source_faces[at]
				var b: Vector3 = source_faces[at + 1]
				var c: Vector3 = source_faces[at + 2]
				if absf((b - a).cross(c - a).y) < 0.05:
					continue
				_probes.append(transform * ((a + b + c) / 3.0))
				break

func _faces(mesh: ImporterMesh, surface: int) -> PackedVector3Array:
	var arrays: Array = mesh.get_surface_arrays(surface)
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var faces := PackedVector3Array()
	for index: int in indices:
		faces.append(positions[index])
	return faces

func _expect(ok: bool, label: String) -> void:
	_checks += 1
	if not ok:
		_failures.append(label)

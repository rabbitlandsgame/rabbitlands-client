extends SceneTree
## Read-only export of the actual client's rebound skins for independent LBS QA.

var args := {}

func _init() -> void:
	var values := OS.get_cmdline_user_args()
	for i in range(0, values.size() - 1, 2):
		args[values[i].trim_prefix("--")] = values[i + 1]
	call_deferred("run")

func matrix(t: Transform3D) -> Array:
	return [[t.basis.x.x, t.basis.y.x, t.basis.z.x, t.origin.x],
		[t.basis.x.y, t.basis.y.y, t.basis.z.y, t.origin.y],
		[t.basis.x.z, t.basis.y.z, t.basis.z.z, t.origin.z], [0.0, 0.0, 0.0, 1.0]]

func run() -> void:
	var slug: String = args.get("slug", "luminous_male")
	var path: String = args.get("registry", "res://data/actors/equipment.json")
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 9012, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animation, equipment)
	if not errors.is_empty():
		push_error(str(errors))
		quit(1)
		return
	actor.set_process(false)
	actor.set_physics_process(false)
	var report := {"race": slug, "registry_sha256": FileAccess.get_sha256(path), "body_sha256": FileAccess.get_sha256(models[slug]["scene"]), "assets": {}}
	var selected: PackedStringArray = str(args.get("parts", "4,5,6")).split(",")
	var visuals: PackedStringArray = str(args.get("visuals", "")).split(",", false)
	for key: String in equipment["models"]:
		var model: Dictionary = equipment["models"][key]
		var part := int(key.get_slice(":", 0))
		var visual := int(key.get_slice(":", 1))
		if (not visuals.is_empty() and not visuals.has(str(visual))) or not selected.has(str(part)) or visual == 0 or model.get("attach", "") != "skinned":
			continue
		actor.apply_equipment_visuals({part: visual})
		var resolved := actor._equipment_model_config(part, visual)
		var scene: String = resolved["scene"]
		var surfaces := {}
		for node: Node in actor._equipment_nodes.get(part, []):
			if node is not MeshInstance3D:
				continue
			var mesh := node as MeshInstance3D
			var names := []
			var binds := []
			for bind in range(mesh.skin.get_bind_count()):
				names.append(str(mesh.skin.get_bind_name(bind)))
				binds.append(matrix(mesh.skin.get_bind_pose(bind)))
			var name := str(node.name).trim_prefix("EquipmentSkin_%d_Visual_%d_" % [part, visual])
			surfaces[name] = {"names": names, "binds": binds}
		report["assets"][scene.get_file()] = {"scene": scene, "sha256": FileAccess.get_sha256(scene), "surfaces": surfaces}
		await process_frame
	FileAccess.open(args["out"], FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("RUNTIME_BINDINGS_OK ", slug, " assets=", report["assets"].size())
	actor.queue_free()
	NativeAnimationImporter.clear()
	await process_frame
	quit()

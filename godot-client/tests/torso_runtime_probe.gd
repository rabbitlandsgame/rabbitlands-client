extends SceneTree
## Where does the runtime actually put a torso garment?
##
## The Python fit checker reproduces the runtime's rebind and says the shells
## sit on the body.  If a render disagrees, one of the two is wrong, and the
## cheapest way to find out which is to ask Godot for the skinned bounds it
## computed rather than to look at a picture of them.

const RIG := "luminous_male"

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var models: Dictionary = (_json("res://data/actors/models.json").get(
		"models", {}) as Dictionary)
	var equipment: Dictionary = _json("res://data/actors/equipment.json")
	var config: Dictionary = models.get(RIG, {}) as Dictionary
	var animations: Dictionary = _json(str(config.get("animationMap",
		"res://data/animations/luminous.json")))

	for visual: int in [100, 110, 120, 128, 168]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 1, "x": 0, "y": 0,
			"rotation": 0, "name": "",
			"appearance": {"skin": 1, "hair": 2, "eyes": 3, "shirt": 1,
				"pants": 2, "boots": 3, "head": 1},
			"equipment_visuals": {5: visual}},
			CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true}),
			config, animations, equipment)
		for _settle: int in range(8):
			await process_frame
		print("visual %d  errors=%s" % [visual, errors])
		var skeleton: Skeleton3D = actor.get_skeleton()
		if skeleton != null:
			var spine := skeleton.find_bone("spine_02")
			if spine >= 0:
				print("    spine_02 rest y = %.4f" % skeleton.get_bone_global_rest(spine).origin.y)
		for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
			var mesh_node: MeshInstance3D = node as MeshInstance3D
			if not mesh_node.name.begins_with("EquipmentSkin"):
				continue
			var box: AABB = mesh_node.get_aabb()
			var skinned := mesh_node.mesh.get_aabb() if mesh_node.mesh != null else AABB()
			print("    %s  mesh aabb y %.3f..%.3f  x %.3f..%.3f  skin=%s bones=%d" % [
				mesh_node.name, skinned.position.y,
				skinned.position.y + skinned.size.y,
				skinned.position.x, skinned.position.x + skinned.size.x,
				mesh_node.skin != null,
				mesh_node.skin.get_bind_count() if mesh_node.skin != null else -1])
			if mesh_node.skin != null:
				for index: int in [0, 1, 2]:
					var name := mesh_node.skin.get_bind_name(index)
					var pose := mesh_node.skin.get_bind_pose(index)
					print("        bind %d %s origin=%s scale=%.4f" % [
						index, name, pose.origin, pose.basis.get_scale().x])
		actor.queue_free()
		await process_frame
	quit(0)

func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed as Dictionary if parsed is Dictionary else {}

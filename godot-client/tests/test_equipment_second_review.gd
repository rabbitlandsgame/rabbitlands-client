extends SceneTree
## Regressions from the second equipment review: visible envelopes, veil back,
## and a carried bow whose orientation really belongs to the wrist.
var checks := 0
var failures: Array[String] = []
func _init() -> void:
	call_deferred("run")
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func read_json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary
func run() -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([
		Vector3(.05,1.68,0),Vector3(.06,1.70,0),Vector3(.05,1.72,.01),Vector3(.29,1.70,0)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2])
	var fixture := ArrayMesh.new()
	fixture.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var grid := RLHeadwearFit._envelope([{"mesh":fixture}], "second_review_unused_vertex")
	check(RLHeadwearFit.reach(grid,90.,1.70)<.10,"unused vertices do not push cloth away from the head")
	var models: Dictionary = read_json("res://data/actors/models.json").models
	var equipment := read_json("res://data/actors/equipment.json")
	for sex: String in ["male","female"]:
		var model: Dictionary = models["luminous_"+sex].duplicate(true)
		model["hairStyles"] = []
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id":9052,"x":0,"y":0,"rotation":0,"kind":1,
			"name":"","appearance":{},"equipment_visuals":{}},CoordinateAdapter.new({"walkingHeight":0.}),
			model,read_json("res://data/animations/luminous.json"),equipment)
		check(errors.is_empty(),sex+" configures")
		actor.set_process(false);actor.set_physics_process(false)
		actor.apply_render_quality(ActorRenderQuality.QUALITY_NAMES.find("high"),false)
		actor.apply_equipment_visuals({3:114,5:221})
		for i in range(4):await process_frame
		var found := false
		for node: Node in actor._equipment_nodes.get(3,[]):
			if not str(node.name).ends_with("VeilBacking"):continue
			found = true
			var lining := node as MeshInstance3D
			var bounds := lining.mesh.get_aabb()
			check(lining.skin!=null and lining.get_node(lining.skeleton)==actor.get_skeleton(),sex+" veil backing follows the actual rig")
			check(bounds.position.y<1.63 and bounds.end.y>1.73,sex+" veil backs the skull through the crown")
			check(lining.material_override!=null,sex+" veil backing uses the cloth material")
		check(found,sex+" veil has a continuous back")
		actor.apply_equipment_visuals({0:164,5:225})
		actor.play_action(&"idle",true)
		actor.animation_player.advance(.3);actor.animation_player.pause()
		var skeleton := actor.get_skeleton()
		actor._weapon_carry._process_modification_with_delta(1./60.)
		var grip := actor.combat_presentation.carried_bow_grip()
		var hand := skeleton.find_bone("hand_l")
		var original := skeleton.get_bone_pose_rotation(hand)
		skeleton.set_bone_pose_rotation(hand,original*Quaternion(Vector3.UP,.25))
		var turned := actor.combat_presentation.carried_bow_grip()
		check(grip.basis.get_rotation_quaternion().angle_to(turned.basis.get_rotation_quaternion())>.15,
			sex+" the bow turns with the wrist instead of rotating separately")
		skeleton.set_bone_pose_rotation(hand,original)
		for action: StringName in [&"ranged_draw",&"ranged_hold",&"ranged_attack",&"idle"]:
			actor.play_action(action,true);actor.animation_player.advance(.3);actor.animation_player.pause()
			actor._weapon_carry._process_modification_with_delta(.25)
			actor.combat_presentation.update_pose()
			check(actor.combat_presentation.bow.global_position.is_finite(),sex+" bow action switch "+str(action))
		actor.free();await process_frame
	print("EQUIPMENT_SECOND_REVIEW ",checks," checks; failures=",failures)
	quit(0 if failures.is_empty() else 1)

extends SceneTree
## Export the actual finished, posed body and pack for an independent contact test.
var args := {}

func _init() -> void:
	var values := OS.get_cmdline_user_args()
	for i: int in range(0, values.size()-1, 2): args[values[i].trim_prefix("--")] = values[i+1]
	call_deferred("run")

func posed(node: MeshInstance3D, skeleton: Skeleton3D) -> Dictionary:
	var matrices: Array[Transform3D] = []
	for bind: int in node.skin.get_bind_count():
		var bone := skeleton.find_bone(node.skin.get_bind_name(bind))
		if bone < 0:bone=node.skin.get_bind_bone(bind)
		matrices.append(skeleton.get_bone_global_pose(bone)*node.skin.get_bind_pose(bind))
	var positions := []
	var faces := []
	for surface: int in node.mesh.get_surface_count():
		var arrays := node.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var stride := bones.size()/maxi(vertices.size(),1)
		var offset := positions.size()
		for vertex: int in vertices.size():
			var point := Vector3.ZERO
			for slot: int in stride:
				var at := vertex*stride+slot
				if weights[at]>0.0: point += (matrices[bones[at]]*vertices[vertex])*weights[at]
			point = node.transform*point
			positions.append([point.x,point.y,point.z])
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for corner: int in range(0,indices.size(),3):
			faces.append([offset+indices[corner],offset+indices[corner+1],offset+indices[corner+2]])
	return {"positions":positions,"faces":faces,"name":str(node.name)}

func run() -> void:
	var folder: String = args["out"]
	DirAccess.make_dir_recursive_absolute(folder)
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	if args.has("baseline"):
		var row: Dictionary = equipment.models["2:151"]
		for variant: Dictionary in row.variants.values():
			variant.scene = str(args.baseline).path_join("variants").path_join(str(variant.authoredFor)).path_join("rl-small-pack.glb")
	var races := ["luminous_male","luminous_female"]
	if args.has("races"): races=Array(str(args.races).split(",",false))
	var cases := []
	for race: String in races:
		var config: Dictionary = models[race].duplicate(true)
		config.hairStyles=[]
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
		var errors := actor.configure({"actor_id":9000,"x":0,"y":0,"rotation":0,"kind":1,"name":"","appearance":{},"equipment_visuals":{}},CoordinateAdapter.new({"walkingHeight":0.0}),config,animations,equipment)
		if not errors.is_empty():push_error(str(errors));quit(1);return
		actor.set_process(false);actor.set_physics_process(false)
		var armors := [0]
		if args.has("armors"):
			armors=[]
			for value: String in str(args.armors).split(",",false):armors.append(int(value))
		if args.has("baseline"):armors=[0]
		for armor: int in armors:
			var outfit := {2:151}
			if armor:outfit[5]=armor
			actor.apply_equipment_visuals(outfit)
			await process_frame
			var phases := [[&"idle",0.0],[&"idle",0.3],[&"idle",0.6],[&"walk",0.25],[&"run",0.25]]
			if args.has("baseline"):phases=[[&"idle",0.3]]
			for phase: Array in phases:
				actor.play_action(phase[0],true)
				actor.animation_player.seek(phase[1],true)
				actor.get_skeleton().force_update_all_bone_transforms()
				var body := []
				var body_node := actor._native_model.find_child("body",true,false) as MeshInstance3D
				if body_node != null and body_node.visible:body.append(posed(body_node,actor.get_skeleton()))
				for node: Node in actor._equipment_nodes.get(5,[]):
					if node is MeshInstance3D and (node as MeshInstance3D).visible:
						body.append(posed(node as MeshInstance3D,actor.get_skeleton()))
				var packs := []
				for node: Node in actor._equipment_nodes.get(2,[]):
					if node is MeshInstance3D:packs.append(posed(node as MeshInstance3D,actor.get_skeleton()))
				var shoulder_y := maxf(actor.get_skeleton().get_bone_global_pose(actor.get_skeleton().find_bone("upperarm_l")).origin.y,actor.get_skeleton().get_bone_global_pose(actor.get_skeleton().find_bone("upperarm_r")).origin.y)
				var label := "%s-%d-%s-%s" % [race,armor,str(phase[0]),str(phase[1])]
				var record := {"label":label,"body":body,"packs":packs,"shoulderY":shoulder_y}
				FileAccess.open(folder.path_join(label+".json"),FileAccess.WRITE).store_string(JSON.stringify(record))
				cases.append(label)
		actor.queue_free();await process_frame
	FileAccess.open(folder.path_join("cases.json"),FileAccess.WRITE).store_string(JSON.stringify(cases))
	NativeAnimationImporter.clear()
	print("PACK_SHOULDER_SAMPLES cases=",cases.size())
	quit()

extends SceneTree
const Draft := preload("res://src/dev/giant_rat_mount_draft.gd")
var failures := 0
var checks := 0
var max_rider_error := 0.0
var max_cape_error := 0.0
var min_surface_y := INF
var min_sole_y := INF
var max_rein_error := 0.0
var max_face_error := 0.0
var max_distal_tail_z := -INF

func point_key(point: Vector3) -> Vector3i:
	return Vector3i((point * 10000.0).round())

func _init() -> void: call_deferred("run")

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		if failures <= 8: push_error(message)

func run() -> void:
	var witnesses: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://../eloria-assets/source/mounts/giant_rat/repair-witnesses-v3.json"))
	var face_keys := {}
	var tail_keys := {}
	for p: Array in witnesses.facePoints: face_keys[point_key(Vector3(p[0],p[1],p[2]))] = true
	for p: Array in witnesses.distalTailPoints: tail_keys[point_key(Vector3(p[0],p[1],p[2]))] = true
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	Draft.add_model(models)
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	check(not preload("res://src/mounts/mount_profiles.gd").supports("giant_rat"), "unreviewed draft stays outside the live catalogue")
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id":42,"x":0,"y":0,"rotation":0,"kind":1,"name":"", "equipment_visuals":{2:1}},
			CoordinateAdapter.new({"walkingHeight":0.0}),models[body],JSON.parse_string(FileAccess.get_file_as_string(models[body].animationMap)),equipment)
		check(errors.is_empty(), "canonical equipped rider configures")
		actor.set_process(false);actor.set_physics_process(false)
		var authority := actor.global_transform
		var native := actor.get_node("NativeModel") as Node3D
		var original := native.transform
		errors = Draft.attach(actor, models)
		check(errors.is_empty(), "Giant Rat draft attaches: " + str(errors))
		if not errors.is_empty(): actor.free();continue
		var visual: Variant = actor._mount_visual
		visual.set_process(false)
		check(visual.tack.triangle_count == 638, "uses the complete imported saddle")
		check(visual.pony.animation_player.has_animation("Idle_A") and visual.pony.animation_player.has_animation("Walk") \
			and visual.pony.animation_player.has_animation("Jog"), "all three mount loops import")
		var sk := visual.pony.get_skeleton() as Skeleton3D
		var mesh := visual.pony.get_node("NativeModel").find_children("*","MeshInstance3D",true,false)[0] as MeshInstance3D
		var arrays := mesh.mesh.surface_get_arrays(0)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		var influences := joints.size() / points.size()
		var bind_bones := PackedInt32Array()
		for bind: int in mesh.skin.get_bind_count():
			var bone := sk.find_bone(mesh.skin.get_bind_name(bind))
			bind_bones.append(bone if bone >= 0 else mesh.skin.get_bind_bone(bind))
		var face_ids := {}
		var tail_ids := {}
		var seen_face := {}
		var seen_tail := {}
		var head_bind := bind_bones.find(sk.find_bone("head"))
		for index: int in points.size():
			var key := point_key(points[index])
			if face_keys.has(key):
				face_ids[index] = true
				seen_face[key] = true
			if tail_keys.has(key):
				tail_ids[index] = true
				seen_tail[key] = true
		check(seen_face.size() == face_keys.size(), "all fixed original facial surface witnesses survive import")
		check(seen_tail.size() == tail_keys.size(), "all fixed original distal tail witnesses survive import")
		check(head_bind >= 0, "native head binding imports")
		for gait: String in ["idle","cruise","burst","idle"]:
			Draft.pace(actor,gait)
			actor._presentation_speed = 0.0 if gait == "idle" else (10.0 if gait == "burst" else 7.5)
			actor.play_action(&"idle" if gait == "idle" else &"run",true)
			for frame: int in 90:
				visual._process(1.0/60.0)
				check(actor.global_transform.is_equal_approx(authority), "rider fit preserves authoritative position")
				for error: float in visual.pose.last_errors.values(): max_rider_error=maxf(max_rider_error,error)
				for side: String in ["l","r"]:
					var line: PackedVector3Array = visual.reins.last_points[side]
					max_rein_error=maxf(max_rein_error,visual.reins.to_global(line[-1]).distance_to(visual.reins.grip_world(actor.get_skeleton(),side)))
				for chain: int in 3:
					var cloth: PackedVector3Array = actor._cape_cloth.get("_points")[chain]
					var lengths: PackedFloat32Array = actor._cape_cloth.get("_lengths")[chain]
					for link: int in range(1,cloth.size()): max_cape_error=maxf(max_cape_error,absf(cloth[link].distance_to(cloth[link-1])-lengths[link-1]))
				if frame % 10 == 0:
					var transforms: Array[Transform3D] = []
					for bind: int in bind_bones.size(): transforms.append(sk.global_transform*sk.get_bone_global_pose(bind_bones[bind])*mesh.skin.get_bind_pose(bind))
					for index: int in points.size():
						var p := Vector3.ZERO
						for slot: int in influences:
							var at := index*influences+slot
							if weights[at]>0.0: p += (transforms[joints[at]]*points[index])*weights[at]
						var y := actor.to_local(p).y
						if face_ids.has(index): max_face_error=maxf(max_face_error,p.distance_to(transforms[head_bind]*points[index]))
						if tail_ids.has(index): max_distal_tail_z=maxf(max_distal_tail_z,(sk.global_transform.affine_inverse()*p).z)
						min_surface_y=minf(min_surface_y,y)
						if points[index].y<.045 and points[index].x>-.70 and points[index].z>-.75: min_sole_y=minf(min_sole_y,y)
		Draft.detach(actor)
		check(native.transform.is_equal_approx(original), "dismount restores the on-foot rider")
		check(actor._mount_visual == null, "draft detaches cleanly")
		actor.free()
	check(max_rider_error<.06, "hands and legs reach their riding targets")
	check(max_cape_error<.02, "cape retains its material length")
	check(max_rein_error<.0001, "reins remain connected to the hands")
	check(min_sole_y>-.003, "actual skinned paw soles stay clear of the floor")
	check(min_surface_y>-.006, "whole surface including the tail stays clear of the floor")
	check(max_face_error<.0001, "fixed mouth, cheek and chin surfaces follow the skull throughout every gait")
	check(max_distal_tail_z< -2.5, "the actual distal tail trails behind the rump in every gait")
	var result := {"checks":checks,"failures":failures,"max_rider_contact_error_metres":max_rider_error,
		"max_cape_link_error_metres":max_cape_error,"max_rein_error_metres":max_rein_error,
		"min_sole_height_metres":min_sole_y,"min_surface_height_metres":min_surface_y,
		"max_facial_rigid_attachment_error_metres":max_face_error,"max_distal_tail_native_z_metres":max_distal_tail_z}
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
		FileAccess.open(output.path_join("engine-checks.json"),FileAccess.WRITE).store_string(JSON.stringify(result,"  "))
	print("GIANT_RAT_MOUNT_CHECKS ",JSON.stringify(result))
	NativeAnimationImporter.clear();GlbSceneCache.clear()
	quit(1 if failures else 0)

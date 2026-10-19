extends SceneTree
var failures := 0
var checks := 0
var max_contact := 0.0
var minimum_sole := INF
var max_support_height := 0.0
var max_reach := 0.0
var max_slide := 0.0
var groups: Array[Dictionary] = []
var paw_vertex_count := 0
var normal_error := 0.0
var tangent_error := 0.0
var rotation_step := 0.0
var max_cape_link_error := 0.0

func _init() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		if failures < 8: push_error(message)

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var source := GlbSceneCache.instantiate(models.crystalback_tortoise.scene)
	var source_mesh := source.find_children("*","MeshInstance3D",true,false)[0] as MeshInstance3D
	var original := source_mesh.mesh.surface_get_arrays(0)
	var source_weights: PackedFloat32Array = original[Mesh.ARRAY_WEIGHTS].duplicate()
	for body: String in ["luminous_male", "luminous_female"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		check(actor.configure({"actor_id":42,"x":0,"y":0,"rotation":0,"kind":1,"name":"","equipment_visuals":{2:1}},
			CoordinateAdapter.new({"walkingHeight":0.0}),models[body],JSON.parse_string(FileAccess.get_file_as_string(models[body].animationMap)),equipment).is_empty(),"rider loads")
		actor.set_process(false)
		actor.set_physics_process(false)
		var authority := actor.global_transform
		actor.set_mount_state({"mode":"mounted","mount_id":"crystalback_tortoise","gait":"cruise"},models)
		var visual: Variant = actor._mount_visual
		check(visual != null and visual.pony.rig_name() == "crystalback_tortoise", "actual imported tortoise is mounted")
		visual.set_process(false)
		var fitted_mesh := visual.pony.get_node("NativeModel").find_children("*","MeshInstance3D",true,false)[0] as MeshInstance3D
		var fitted := fitted_mesh.mesh.surface_get_arrays(0)
		for attribute: int in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_TEX_UV,Mesh.ARRAY_INDEX]:
			check(fitted[attribute] == original[attribute], "paw fit retains original geometry/UVs/indices")
		for vertex: int in (original[Mesh.ARRAY_NORMAL] as PackedVector3Array).size():
			normal_error = maxf(normal_error,(original[Mesh.ARRAY_NORMAL][vertex] as Vector3).distance_to(fitted[Mesh.ARRAY_NORMAL][vertex]))
		for value: int in (original[Mesh.ARRAY_TANGENT] as PackedFloat32Array).size():
			tangent_error = maxf(tangent_error,absf(float(original[Mesh.ARRAY_TANGENT][value]) - float(fitted[Mesh.ARRAY_TANGENT][value])))
		check(source_mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_WEIGHTS] == source_weights,"shared unmounted creature skin stays unchanged")
		paw_vertex_count = visual.locomotion.rebound_paw_vertices
		check(paw_vertex_count > 0,"physical paws receive the scoped ownership repair")
		_bind_soles(visual.pony)
		for gait: String in ["walk","cruise","burst"]:
			actor.set_mount_state({"mode":"mounted","mount_id":"crystalback_tortoise","gait":gait},models)
			actor._presentation_speed = {"walk":.5,"cruise":1.5,"burst":2.25}[gait]
			actor.play_action(&"run")
			visual._process(0.0)
			var duration: float = visual.profile.cycleLengths[visual.action]
			var previous := {}
			var first_pose: Array[Transform3D] = []
			var previous_pose: Array[Transform3D] = []
			for sample: int in 193:
				visual.elapsed = duration * sample / 192.0
				visual._process(0.0)
				check(actor.global_transform.is_equal_approx(authority), "mounting preserves player network/camera placement")
				for error: float in visual.pose.last_errors.values(): max_contact = maxf(max_contact,error)
				var adapter: Variant = visual.locomotion
				max_reach = maxf(max_reach,adapter.max_reach_error)
				var poses: Array[Transform3D] = []
				for bone: int in visual.pony.get_skeleton().get_bone_count():
					var pose: Transform3D = visual.pony.get_skeleton().get_bone_global_pose(bone)
					poses.append(pose)
					if not previous_pose.is_empty(): rotation_step = maxf(rotation_step,pose.basis.get_rotation_quaternion().angle_to(previous_pose[bone].basis.get_rotation_quaternion()))
				if sample == 0: first_pose = poses
				if sample == 192:
					for bone: int in poses.size(): check(poses[bone].is_equal_approx(first_pose[bone]),"gait loops return to the same complete body pose")
				previous_pose = poses
				for group: Dictionary in groups:
					for leg: String in group.soles:
						var low := INF
						var centroid := Vector3.ZERO
						for index: int in group.soles[leg]:
							var point := _skin(group,index)
							low = minf(low,point.y)
							centroid += point
						centroid /= group.soles[leg].size()
						minimum_sole = minf(minimum_sole,low)
						var step: Dictionary = adapter.last_targets[leg]
						if step.support:
							max_support_height = maxf(max_support_height,absf(low))
							if previous.has(leg) and previous[leg].support and step.phase >= previous[leg].phase:
								var speed: Vector3 = (centroid - previous[leg].point) / (duration / 192.0)
								var stride: float = visual.profile.locomotionAdapter.gaits[visual.action].stride
								var stance: float = visual.profile.locomotionAdapter.gaits[visual.action].stance
								var expected: Vector3 = group.rig.global_basis * Vector3(0,0,-stride / (duration * stance))
								max_slide = maxf(max_slide,speed.distance_to(expected))
						previous[leg] = {"point":centroid,"support":step.support,"phase":step.phase}
			# Advance real time as well as scrubbing the gait: the cape has its
			# own state and must retain its material length during pace changes.
			for frame: int in 120:
				visual._process(1.0 / 60.0)
				for chain: int in 3:
					var points: PackedVector3Array = actor._cape_cloth.get("_points")[chain]
					var lengths: PackedFloat32Array = actor._cape_cloth.get("_lengths")[chain]
					for link: int in range(1, points.size()):
						max_cape_link_error = maxf(max_cape_link_error,
							absf(points[link].distance_to(points[link - 1]) - lengths[link - 1]))
			actor.play_action(&"idle")
			visual._process(0.0)
			check(visual.action == "idle", "stopping restores a grounded idle")
		actor.set_mount_state({},models)
		actor.free()
		groups.clear()
	check(max_contact < .06,"seated rider hands and feet retain their contact targets")
	check(max_reach < .0001,"all four physical leg chains reach their stance/recovery targets")
	check(minimum_sole > -.001 and max_support_height < .006,"supported sole surfaces remain on the floor")
	check(max_slide < .003,"supported soles follow the authored backward travel without sliding")
	check(normal_error < .0005 and tangent_error < .0005,"normal/tangent repacking retains importer precision")
	check(rotation_step < .2,"full-cycle articulation has no pole flips or sudden joint jumps")
	check(max_cape_link_error < .02,"draped cape retains its authored length through gait changes")
	var report := {"checks":checks,"failures":failures,"max_rider_contact_error":max_contact,
		"max_leg_reach_error":max_reach,"minimum_sole_height":minimum_sole,"max_supported_sole_height":max_support_height,"max_supported_sole_speed_error":max_slide,"rebound_paw_vertices":paw_vertex_count,"normal_repack_error":normal_error,"tangent_repack_error":tangent_error,"max_rotation_step_radians":rotation_step,"max_cape_link_error":max_cape_link_error}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="): FileAccess.open(argument.trim_prefix("--report="),FileAccess.WRITE).store_string(JSON.stringify(report,"  "))
	print("TORTOISE_MOUNT_CHECKS ",JSON.stringify(report))
	source.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)

func _bind_soles(actor: ReplicatedActor3D) -> void:
	var sk := actor.get_skeleton()
	for mesh: MeshInstance3D in actor.get_node("NativeModel").find_children("*","MeshInstance3D",true,false):
		if mesh.skin == null: continue
		var bones := PackedInt32Array()
		for bind: int in mesh.skin.get_bind_count():
			var bone := sk.find_bone(mesh.skin.get_bind_name(bind))
			if bone < 0: bone = mesh.skin.get_bind_bone(bind)
			check(bone >= 0, "native skin binding resolves")
			bones.append(bone)
		for surface: int in mesh.mesh.get_surface_count():
			var arrays := mesh.mesh.surface_get_arrays(surface)
			if arrays[Mesh.ARRAY_BONES] == null: continue
			var group := {"mesh":mesh,"rig":sk,"bones":bones,"arrays":arrays,"soles":{}}
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			for index: int in vertices.size():
				var point: Vector3 = vertices[index]
				if point.y > .025 or absf(point.x) < .3: continue
				var leg := ("fore_" if point.z > 0 else "hind_") + ("l" if point.x > 0 else "r")
				if not group.soles.has(leg): group.soles[leg] = PackedInt32Array()
				group.soles[leg].append(index)
			groups.append(group)

func _skin(group: Dictionary,index: int) -> Vector3:
	var arrays: Array = group.arrays
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var count := joints.size() / vertices.size()
	var value := Vector3.ZERO
	var sk: Skeleton3D = group.rig
	var mesh: MeshInstance3D = group.mesh
	for slot: int in count:
		var at := index * count + slot
		if weights[at] > 0:
			var bind := joints[at]
			value += sk.global_transform * sk.get_bone_global_pose(group.bones[bind]) * mesh.skin.get_bind_pose(bind) * vertices[index] * weights[at]
	return value

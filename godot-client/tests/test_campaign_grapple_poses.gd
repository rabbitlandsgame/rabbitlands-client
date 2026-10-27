extends SceneTree
## Real native rigs: contact, clock ownership, living fall/rise, and cleanup.
var checks:=0
var failures:=0
var measurements:Dictionary={}
func _init() -> void:run.call_deferred()
func expect(value:bool,message:String)->void:
	checks+=1
	if value:print("PASS: ",message)
	else:failures+=1;push_error(message)

func make_actor(type:int,id:int,appearance:Dictionary={},gear:Dictionary={})->ReplicatedActor3D:
	var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var model:Dictionary=registry.models[registry.actorTypes[str(type)]]
	var actor:=ReplicatedActor3D.new();root.add_child(actor)
	var errors:=actor.configure({"actor_id":id,"actor_type":type,"kind":2,"name":"Grapple probe",
		"x":0,"y":0,"rotation":0,"frame":7,"health":50,"max_health":50,"scale":1.0,
		"appearance":appearance,"equipment_visuals":gear},CoordinateAdapter.new({"walkingHeight":0}),model,
		JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap))),equipment)
	expect(errors.is_empty(),"current native actor"+str(type)+" and its existing clips load")
	actor.set_process(false);actor.set_physics_process(false)
	return actor

func bone(actor:ReplicatedActor3D,name:String)->Vector3:
	var skeleton:=actor.get_skeleton()
	return skeleton.global_transform*skeleton.get_bone_global_pose(skeleton.find_bone(name)).origin

func pose(actor:ReplicatedActor3D)->Array[Transform3D]:
	var result:Array[Transform3D]=[]
	for index:int in actor.get_skeleton().get_bone_count():result.append(actor.get_skeleton().get_bone_pose(index))
	return result

func same_pose(actor:ReplicatedActor3D,before:Array[Transform3D])->bool:
	for index:int in before.size():
		if not before[index].is_equal_approx(actor.get_skeleton().get_bone_pose(index)):return false
	return true

func equipment_visibility(actor:ReplicatedActor3D)->Dictionary:
	var result:Dictionary={}
	for part:int in [0,1]:
		for node:Node in actor._equipment_nodes.get(part,[]):
			if node is Node3D:result[node.get_instance_id()]={"node":node,"visible":node.visible}
	return result

func run()->void:
	create_timer(75).timeout.connect(func()->void:push_error("Native grapple checks timed out");quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var goblin:=make_actor(624,31)
	var mother:=make_actor(0,32,{"skin":1,"hair":107,"shirt":5,"pants":4,"boots":1,"head":0,"eyes":2},
		{"0":163,"3":122,"5":189,"4":176,"6":205,"2":100})
	var player:=make_actor(1,33,{}, {"0":164,"1":160})
	# A real string-driven bow plus a deliberately hidden offhand cover both
	# presentation routes and exact visibility restoration.
	for prop:Node3D in player._equipment_nodes.get(1,[]):prop.hide()
	var player_gear:=equipment_visibility(player)
	var bow:=player.combat_presentation.bow
	var bow_visible:=bow.visible
	var carry_active:=player._weapon_carry.active
	expect(not player_gear.is_empty() and is_instance_valid(bow) and bow_visible,
		"the tackle fixture has native hand gear and a visible string-driven bow")
	var mother_gear:=equipment_visibility(mother)
	var previous_mode:=mother.animation_player.callback_mode_process
	var previous_speed:=mother.animation_player.speed_scale
	var original_health:=[goblin._health_current,mother._health_current,player._health_current]
	var original_targets:=[goblin.server_target,mother.server_target,player.server_target]
	goblin.set_cinematic_presentation(Vector3.ZERO,0,&"restraint_hold")
	mother.set_cinematic_presentation(Vector3(0,0,-0.42),0,&"restraint_held")
	goblin.set_cinematic_action_elapsed(3.0);mother.set_cinematic_action_elapsed(3.0)
	var waist:=bone(mother,"pelvis")
	var left:=bone(goblin,"hand_l");var right:=bone(goblin,"hand_r")
	var elbows:=[bone(goblin,"arm_lower_l"),bone(goblin,"arm_lower_r")]
	var torso:=torso_points(mother)
	var contact:=[nearest(left,torso),nearest(right,torso)]
	measurements={"mother_waist":arr(waist),"goblin_hands":[arr(left),arr(right)],
		"goblin_elbows":[arr(elbows[0]),arr(elbows[1])],"torso_surface_distance":contact,"torso_vertices":torso.size()}
	print("NATIVE CONTACT ",JSON.stringify(measurements))
	expect(left.x<waist.x and right.x>waist.x and left.z<waist.z and right.z<waist.z,
		"both goblin hands reach around to the front of the mother's waist")
	expect(elbows[0].x<waist.x-0.22 and elbows[1].x>waist.x+0.22,
		"the elbows remain outside her sides rather than passing both arms through her torso")
	expect(not torso.is_empty() and contact[0]<0.16 and contact[1]<0.16,
		"both grabbing hands contact the current native clothed torso within16cm")
	var stable:=pose(goblin)
	goblin._cinematic_grapple.advance(5.0)
	expect(same_pose(goblin,stable),"authored pose sampling ignores five seconds of autonomous wall time")
	goblin.set_cinematic_presentation(Vector3.ZERO,0,&"restraint_hold")
	goblin.set_cinematic_action_elapsed(3.0)
	expect(same_pose(goblin,stable),"repeating the held cue has no clock reset or accumulated arm rotation")
	await create_timer(0.1).timeout
	goblin._physics_process(0.1)
	expect(same_pose(goblin,stable),"a frozen manual-reading cue keeps its native pose through real time and physics")
	var hidden:=not mother_gear.is_empty()
	for row:Dictionary in mother_gear.values():
		hidden=hidden and not row.node.visible
	expect(hidden,"the restrained woman's held equipment cannot obstruct the wrapped hands")
	# Set the exact entry state immediately before acquiring the player lease;
	# ordinary pre-scene combat refreshes legitimately own these props earlier.
	for prop:Node3D in player._equipment_nodes.get(1,[]):prop.hide()
	player_gear=equipment_visibility(player)
	player.set_cinematic_presentation(Vector3(0,0,1),0,&"tackle_lunge")
	player.set_cinematic_action_elapsed(0.35)
	await create_timer(0.1).timeout
	player.combat_presentation.update_pose()
	var player_hidden:=not bow.visible and not player._weapon_carry.active
	for row:Dictionary in player_gear.values():player_hidden=player_hidden and not row.node.visible
	expect(player_hidden,"a real skeleton/combat refresh keeps both bow and native hand gear suppressed")
	expect(bone(player,"pelvis").y<0.85 and player.current_action!=&"death",
		"the player ducks into a living shoulder-first tackle")
	for actor:ReplicatedActor3D in [goblin,mother,player]:
		var point:=actor.global_position
		actor.set_cinematic_presentation(point,0,&"tackle_fall")
		actor.set_cinematic_action_elapsed(0.95)
		actor.set_cinematic_presentation(point,0,&"tackle_down")
		actor.set_cinematic_action_elapsed(1.0)
		var head_name:="head" if actor==goblin else "Head"
		expect(bone(actor,head_name).y<0.65 and actor.current_action==&"tackle_down" and actor._health_current==50,
			"actor"+str(actor.actor_id)+" settles on the floor without a gameplay death")
		actor.set_cinematic_presentation(point,0,&"tackle_rise")
		actor.set_cinematic_action_elapsed(2.2)
		expect(bone(actor,head_name).y>1.0 and actor.current_action==&"tackle_rise",
			"actor"+str(actor.actor_id)+" rises using its current native rig")
		actor.end_cinematic_presentation()
		expect(actor.current_action==&"idle" and not actor._cinematic_active,
			"actor"+str(actor.actor_id)+" returns to ordinary idle after the grapple lease")
	var restored:=true
	for row:Dictionary in mother_gear.values():restored=restored and row.node.visible==row.visible
	expect(restored and mother.animation_player.callback_mode_process==previous_mode
		and is_equal_approx(mother.animation_player.speed_scale,previous_speed),
		"Skip/end restores every held-equipment visibility and original animation callback/speed")
	var player_restored:=bow.visible==bow_visible and player._weapon_carry.active==carry_active
	for row:Dictionary in player_gear.values():
		player_restored=player_restored and row.node.visible==row.visible
	expect(player_restored,"end restores the player bow, modifier activity, and initially hidden offhand exactly")
	expect([goblin._health_current,mother._health_current,player._health_current]==original_health
		and [goblin.server_target,mother.server_target,player.server_target]==original_targets,
		"all native health and authoritative destinations remain unchanged")
	for actor:ReplicatedActor3D in [goblin,mother,player]:actor.queue_free()
	await process_frame;await process_frame
	NativeAnimationImporter.clear();GlbSceneCache.clear();await process_frame
	print("Native grapple poses: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)

func arr(point:Vector3)->Array:return [point.x,point.y,point.z]
func nearest(point:Vector3,cloud:PackedVector3Array)->float:
	var distance:=INF
	for other:Vector3 in cloud:distance=minf(distance,point.distance_to(other))
	return distance

func torso_points(actor:ReplicatedActor3D)->PackedVector3Array:
	var skeleton:=actor.get_skeleton()
	var result:=PackedVector3Array()
	for mesh:MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
		if not mesh.is_visible_in_tree() or mesh.skin==null or mesh.mesh==null:continue
		var frames:Array[Transform3D]=[];var torso:Array[bool]=[]
		for bind:int in mesh.skin.get_bind_count():
			var index:=skeleton.find_bone(mesh.skin.get_bind_name(bind))
			if index<0:index=mesh.skin.get_bind_bone(bind)
			frames.append(skeleton.global_transform*skeleton.get_bone_global_pose(index)*mesh.skin.get_bind_pose(bind))
			torso.append(str(skeleton.get_bone_name(index)) in ["pelvis","spine_01","spine_02"])
		for surface:int in mesh.mesh.get_surface_count():
			var data:=mesh.mesh.surface_get_arrays(surface)
			if data[Mesh.ARRAY_BONES]==null:continue
			var vertices:PackedVector3Array=data[Mesh.ARRAY_VERTEX]
			var joints:PackedInt32Array=data[Mesh.ARRAY_BONES]
			var weights:PackedFloat32Array=data[Mesh.ARRAY_WEIGHTS]
			var influences:int=joints.size()/vertices.size()
			for index:int in vertices.size():
				var point:=Vector3.ZERO;var body_weight:=0.0
				for slot:int in influences:
					var at:=index*influences+slot
					if weights[at]<=0:continue
					point+=(frames[joints[at]]*vertices[index])*weights[at]
					if torso[joints[at]]:body_weight+=weights[at]
				if body_weight>0.5 and point.y>0.75 and point.y<1.15:result.append(point)
	return result

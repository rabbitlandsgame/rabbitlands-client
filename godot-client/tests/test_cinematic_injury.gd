extends SceneTree
const Injury := preload("res://src/actors/cinematic_injury.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ",message)
	else:
		failures += 1
		push_error(message)

func contact_pose(actor: ReplicatedActor3D) -> Dictionary:
	var skeleton: Skeleton3D = actor._native_skeleton
	var result := {}
	for name: String in ["Head", "pelvis", "foot_l", "foot_r"]:
		result[name] = skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone(name))
	return result

func run() -> void:
	create_timer(90).timeout.connect(func()->void:push_error("Injury checks timed out");quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var model: Dictionary = registry.models[registry.actorTypes["308"]]
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap)))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var original_map := JSON.stringify(mapping)
	var library_path: String = model.animationLibrary
	var original_hash := FileAccess.get_sha256(library_path)
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var adapter := CoordinateAdapter.new({"walkingHeight":2.5})
	var dto := {"actor_id":9182,"actor_type":308,"kind":1,"x":425,"y":316,
		"rotation":90,"name":"Dock Worker","appearance":{},"equipment_visuals":{},"health":35,"max_health":50}
	var errors := actor.configure(dto,adapter,model,mapping,equipment)
	expect(errors.is_empty(),"the actual approved worker config loads: "+str(errors))
	if not errors.is_empty():quit(1);return
	actor.apply_server_state(dto,adapter,true)
	actor.set_physics_process(false)
	var native_target := actor.server_target
	var health := [actor._health_current,actor._health_maximum]
	var bodies := actor.find_children("*","CollisionObject3D",true,false).size()
	var callback := actor.animation_player.callback_mode_process
	var initial_clips := actor.animation_player.get_animation_list()
	expect(not initial_clips.has("cinematic_injury/Hit_Knockback"),"ordinary workers do not eagerly import the injury clips")
	var point := native_target+Vector3(-.48,0,.32)
	actor.set_cinematic_presentation(point,PI/2,&"injury_recoil")
	actor.set_physics_process(false)
	expect(actor.current_action==&"injury_recoil" and actor._cinematic_injury!=null,"the cinematic action uses the native injury presentation path")
	var injury = actor._cinematic_injury
	if injury==null:quit(1);return
	expect(actor.animation_player.current_animation==&"cinematic_injury/Hit_Knockback","recoil plays the real current humanoid knockback clip")
	injury.advance(.2)
	expect(is_equal_approx(injury.elapsed,.2) and actor.animation_player.is_playing(),"recoil advances through the fall instead of seeking directly to the floor")
	actor.set_cinematic_presentation(point,PI/2,&"injury_recoil")
	actor.set_physics_process(false)
	expect(is_equal_approx(injury.elapsed,.2),"a repeated scene cue does not restart the falling worker")
	injury.advance(2.0)
	expect(injury.held and is_equal_approx(injury.elapsed,.55) and not actor.animation_player.is_playing(),"the fall clamps and pauses before the source clip gets up")
	var held_pose := actor._native_skeleton.get_bone_global_pose(actor._native_skeleton.find_bone("pelvis"))
	var completed_contact := contact_pose(actor)
	injury.advance(45)
	expect(held_pose.is_equal_approx(actor._native_skeleton.get_bone_global_pose(actor._native_skeleton.find_bone("pelvis"))),"a long manual dialogue wait retains the same injured pose")
	actor.set_cinematic_presentation(point,PI/2,&"injury_pinned")
	actor.set_physics_process(false)
	expect(injury.held and is_equal_approx(injury.elapsed,.55),"the pinned cue holds the same native fall at the measured contact pose")
	actor.set_cinematic_presentation(point,PI/2,&"injury_pinned")
	actor.set_physics_process(false)
	expect(not actor.animation_player.is_playing(),"ambient refresh cannot restart or get up from a held injury")
	expect(actor.server_target==native_target and health==[actor._health_current,actor._health_maximum],"injury animation leaves authoritative position and health untouched")
	expect(not actor._death_finished and actor.current_action!=&"death", "an injured worker is never presented through the gameplay death state")
	expect(actor.find_children("*","CollisionObject3D",true,false).size()==bodies,"injury presentation adds no collider or movement proof")
	actor.end_cinematic_presentation()
	actor.set_physics_process(false)
	expect(actor.current_action==&"idle" and actor.global_position==native_target,"cleanup restores normal idle at the latest native target")
	expect(actor.animation_player.callback_mode_process==callback,"cleanup restores ordinary animation timing")
	actor.set_cinematic_presentation(point,PI/2,&"injury_pinned")
	actor.set_physics_process(false)
	expect(injury.held and is_equal_approx(injury.elapsed,.55),"a skipped accident or late join enters the held pose immediately without replaying a fall")
	expect(held_pose.is_equal_approx(actor._native_skeleton.get_bone_global_pose(actor._native_skeleton.find_bone("pelvis"))),"direct pinned entry has the same actual pelvis pose as the completed recoil")
	var direct_contact := contact_pose(actor)
	for name: String in direct_contact:
		expect((completed_contact[name] as Transform3D).is_equal_approx(direct_contact[name]),
			"completed recoil preserves the exact direct pinned "+name+" transform")
	actor.end_cinematic_presentation()
	actor.set_physics_process(false)
	for _step: int in range(12): actor.animation_player.advance(1.0/60.0)
	actor.set_cinematic_presentation(point,PI/2,&"injury_recoil")
	actor.set_physics_process(false)
	injury.advance(.03)
	actor.set_cinematic_presentation(point,PI/2,&"injury_pinned")
	actor.set_physics_process(false)
	var interrupted_contact := contact_pose(actor)
	for name: String in direct_contact:
		expect((interrupted_contact[name] as Transform3D).is_equal_approx(direct_contact[name]),
			"Continue after 0.03s cancels the unfinished fall blend at the exact pinned "+name+" transform")
	injury.advance(45)
	actor.set_cinematic_presentation(point,PI/2,&"injury_pinned")
	actor.set_physics_process(false)
	var refreshed_contact := contact_pose(actor)
	for name: String in direct_contact:
		expect((refreshed_contact[name] as Transform3D).is_equal_approx(direct_contact[name]),
			"long waits and repeated pinned cues retain the corrected "+name+" transform")
	expect(actor.server_target==native_target and health==[actor._health_current,actor._health_maximum]
		and actor.current_action!=&"death" and not actor._death_finished,
		"an interrupted cosmetic fall never changes native position, health or life state")
	actor.set_cinematic_presentation(native_target,PI/2,&"injury_standing")
	actor.set_physics_process(false)
	for _step: int in range(300): injury.advance(1.0/60.0)
	expect(actor.animation_player.current_animation==&"cinematic_injury/Idle_Hurt" and actor.animation_player.is_playing(),"the treated worker uses a conscious upright hurt loop")
	var head := actor._native_skeleton.find_bone("Head")
	var head_height: float = (actor._native_skeleton.global_transform * actor._native_skeleton.get_bone_global_pose(head).origin).y
	expect(head_height-native_target.y>1.2,"the treated pose is visibly upright after the native crossfade")
	expect(actor.animation_player.get_animation(&"cinematic_injury/Idle_Hurt").loop_mode==Animation.LOOP_LINEAR,"only the upright hurt alias loops")
	expect(actor.animation_player.get_animation(&"cinematic_injury/Hit_Knockback").loop_mode==Animation.LOOP_NONE,"the falling clip never loops")
	actor.end_cinematic_presentation()
	actor.set_physics_process(false)
	actor.play_action(&"walk")
	expect(actor.current_action==&"walk" and actor.animation_player.is_playing(),"ordinary movement still plays after the injury is released")
	expect(original_map==JSON.stringify(mapping) and original_hash==FileAccess.get_sha256(library_path),"native source clips and the ordinary action map remain unchanged")
	actor.queue_free()
	await process_frame
	print("cinematic injury checks: ",checks-failures,"/",checks)
	quit(1 if failures else 0)

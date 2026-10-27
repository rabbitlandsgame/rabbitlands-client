extends RefCounted
## A reversible, per-view grapple using the current native rigs and clips.
## These aliases never invoke gameplay death or change equipment/health state.
const NAMESPACE := &"cinematic_grapple"
const ACTIONS := [&"restraint_hold",&"restraint_held",&"tackle_lunge",&"tackle_fall",&"tackle_down",&"tackle_rise"]
const FALL_SECONDS := 0.95
const RISE_SECONDS := 2.2
const LUNGE_SECONDS := 0.7
const HUMAN_FALL_TIME := 0.55
const GOBLIN_FALL_TIME := 1.8
var action: StringName = &""
var elapsed := 0.0
var _sampled := false
var _actor: WeakRef
var _skeleton: Skeleton3D
var _player: AnimationPlayer
var _human := false
var _callback_mode := AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
var _speed := 1.0
var _saved_pose: Array[Transform3D] = []
var _equipment: Dictionary = {}
var _weapon_carry: WeakRef
var _weapon_carry_active := false

static func accepts(value: StringName) -> bool: return value in ACTIONS
static func duration(value: StringName) -> float:
	if value==&"tackle_rise":return RISE_SECONDS
	if value==&"tackle_lunge":return LUNGE_SECONDS
	if value in [&"tackle_fall",&"tackle_down"]:return FALL_SECONDS
	return 2.4

func play(actor: Node3D, value: StringName, restart := false) -> bool:
	if not accepts(value) or not bool(actor.get("_cinematic_active")) or actor.get("current_action")==&"death":return false
	var player:=actor.get("animation_player") as AnimationPlayer
	var skeleton:=actor.call("get_skeleton") as Skeleton3D
	if player==null or skeleton==null or not _install(actor,player,skeleton):return false
	if _player!=player:
		clear()
		_actor=weakref(actor);_player=player;_skeleton=skeleton
		_human=(actor.get("_model_config") as Dictionary).has("culture")
		_callback_mode=player.callback_mode_process;_speed=player.speed_scale
		_saved_pose=_pose()
		var carry:=actor.get("_weapon_carry") as SkeletonModifier3D
		if carry!=null:_weapon_carry=weakref(carry);_weapon_carry_active=carry.active;carry.active=false
	if action==value and not restart:return true
	action=value;elapsed=0;_sampled=false
	_player.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	_player.speed_scale=1.0
	sample(0.0,false)
	return true

func sample(seconds: float, authored := true) -> void:
	if not is_instance_valid(_player) or not is_instance_valid(_skeleton) or action==&"":return
	var actor:=_actor.get_ref() as Node3D
	if not is_instance_valid(actor) or actor.get("current_action")==&"death":return
	elapsed=maxf(0.0,seconds);_sampled=_sampled or authored
	_hide_hand_equipment(actor)
	var carry:SkeletonModifier3D=_weapon_carry.get_ref() as SkeletonModifier3D if _weapon_carry!=null else null
	if is_instance_valid(carry):carry.active=false
	var fall:=HUMAN_FALL_TIME if _human else GOBLIN_FALL_TIME
	var falling:=StringName(str(NAMESPACE)+"/Hit_Knockback") if _human else &"Death_A"
	match action:
		&"restraint_hold":
			_seek(&"Fighting_Idle",elapsed)
			_arm(actor,"l",Vector3(-0.09,0.96,-0.50),false)
			_arm(actor,"r",Vector3(0.09,0.96,-0.50),false)
		&"restraint_held":
			_seek(_human_clip("Idle_Hurt"),elapsed)
			var strain:=sin(elapsed*4.0)*0.025
			_arm(actor,"l",Vector3(-0.22,1.04+strain,-0.20),true)
			_arm(actor,"r",Vector3(0.22,1.04-strain,-0.20),true)
		&"tackle_lunge":
			_seek(_human_clip("Crouch_Idle"),elapsed)
			_arm(actor,"l",Vector3(-0.18,1.0,-0.52),true)
			_arm(actor,"r",Vector3(0.18,1.0,-0.52),true)
		&"tackle_fall":_seek(falling,fall*clampf(elapsed/FALL_SECONDS,0.0,1.0))
		&"tackle_down":_seek(falling,fall)
		&"tackle_rise":
			var progress:=clampf(elapsed/RISE_SECONDS,0.0,1.0)
			if _human:
				_seek(falling,fall)
				var start:=_pose()
				var rising:=_human_clip("LayToIdle")
				_seek(rising,progress*_player.get_animation(rising).length)
				_blend(start,smoothstep(0.0,0.20,elapsed))
			elif progress>=0.9999:_seek(&"Idle_A",0.0)
			else:_seek(falling,fall*(1.0-progress))

func advance(delta: float) -> void:
	if not _sampled:sample(elapsed+maxf(0.0,delta),false)

func _human_clip(name: String) -> StringName:return StringName(str(NAMESPACE)+"/"+name)

func _seek(clip: StringName, time: float) -> void:
	if not _player.has_animation(clip):return
	var animation:=_player.get_animation(clip)
	var at:=fposmod(time,animation.length) if animation.loop_mode!=Animation.LOOP_NONE else minf(time,animation.length)
	_player.stop(true);_player.play(clip,0.0);_player.seek(at,true);_player.advance(0.0);_player.pause()

func _pose() -> Array[Transform3D]:
	var result:Array[Transform3D]=[]
	for bone:int in _skeleton.get_bone_count():result.append(_skeleton.get_bone_pose(bone))
	return result

func _blend(from: Array[Transform3D], weight: float) -> void:
	for bone:int in mini(from.size(),_skeleton.get_bone_count()):
		var pose:Transform3D=from[bone].interpolate_with(_skeleton.get_bone_pose(bone),weight)
		_skeleton.set_bone_pose_position(bone,pose.origin)
		_skeleton.set_bone_pose_rotation(bone,pose.basis.get_rotation_quaternion())
		_skeleton.set_bone_pose_scale(bone,pose.basis.get_scale())

func _arm(actor: Node3D, side: String, local_target: Vector3, human: bool) -> void:
	var upper:=_skeleton.find_bone(("upperarm_" if human else "arm_upper_")+side)
	var lower:=_skeleton.find_bone(("lowerarm_" if human else "arm_lower_")+side)
	var hand:=_skeleton.find_bone("hand_"+side)
	if mini(upper,mini(lower,hand))<0:return
	var frame:=_skeleton.global_transform.affine_inverse()*actor.global_transform
	var target:=frame*local_target
	var a:=_skeleton.get_bone_global_pose(upper).origin
	var b:=_skeleton.get_bone_global_pose(lower).origin
	var c:=_skeleton.get_bone_global_pose(hand).origin
	var first:=a.distance_to(b);var second:=b.distance_to(c)
	var direction:Vector3=target-a
	var distance:=clampf(direction.length(),absf(first-second)+0.001,(first+second)*0.98)
	if direction.length_squared()<0.000001:return
	direction=direction.normalized();target=a+direction*distance
	var pole:Vector3=(frame.basis*Vector3(-1 if side=="l" else 1,0,0)).normalized()
	var outward:=pole-direction*pole.dot(direction)
	if outward.length_squared()<0.000001:outward=direction.cross(Vector3.UP)
	var along:float=(first*first-second*second+distance*distance)/(2.0*distance)
	var across:=sqrt(maxf(0.0,first*first-along*along))
	var elbow:=a+direction*along+outward.normalized()*across
	_turn_toward(upper,b-a,elbow-a)
	b=_skeleton.get_bone_global_pose(lower).origin;c=_skeleton.get_bone_global_pose(hand).origin
	_turn_toward(lower,c-b,target-b)

func _turn_toward(bone: int, from: Vector3, to: Vector3) -> void:
	if minf(from.length_squared(),to.length_squared())<0.000001:return
	var global_basis:=_skeleton.get_bone_global_pose(bone).basis.orthonormalized()
	var desired:=Basis(Quaternion(from.normalized(),to.normalized()))*global_basis
	var parent:=_skeleton.get_bone_parent(bone)
	var parent_basis:=_skeleton.get_bone_global_pose(parent).basis.orthonormalized() if parent>=0 else Basis.IDENTITY
	_skeleton.set_bone_pose_rotation(bone,(parent_basis.inverse()*desired).get_rotation_quaternion())

func _hide_hand_equipment(actor: Node3D) -> void:
	for part:int in [0,1]:
		for node:Node in (actor.get("_equipment_nodes") as Dictionary).get(part,[]):
			if node is Node3D:_remember_hide(node)
	var combat:=actor.get("combat_presentation") as CombatPresentation3D
	if is_instance_valid(combat) and is_instance_valid(combat.bow):_remember_hide(combat.bow)

func _remember_hide(node: Node3D) -> void:
	var id:=node.get_instance_id()
	if not _equipment.has(id):_equipment[id]={"node":weakref(node),"visible":node.visible}
	node.hide()

func clear() -> void:
	var actor:=_actor.get_ref() as Node3D if _actor!=null else null
	if is_instance_valid(_player) and action!=&"":
		_player.callback_mode_process=_callback_mode;_player.speed_scale=_speed
	if is_instance_valid(_skeleton) and is_instance_valid(actor) and actor.get("current_action")!=&"death":
		for bone:int in mini(_saved_pose.size(),_skeleton.get_bone_count()):
			var pose:=_saved_pose[bone]
			_skeleton.set_bone_pose_position(bone,pose.origin)
			_skeleton.set_bone_pose_rotation(bone,pose.basis.get_rotation_quaternion())
			_skeleton.set_bone_pose_scale(bone,pose.basis.get_scale())
	for row:Dictionary in _equipment.values():
		var node:Node3D=row.node.get_ref()
		if is_instance_valid(node):node.visible=bool(row.visible)
	var carry:SkeletonModifier3D=_weapon_carry.get_ref() as SkeletonModifier3D if _weapon_carry!=null else null
	if is_instance_valid(carry):carry.active=_weapon_carry_active
	_equipment.clear();_saved_pose.clear();_weapon_carry=null
	_actor=null;_player=null;_skeleton=null;action=&"";elapsed=0;_sampled=false

func _install(actor: Node3D, player: AnimationPlayer, skeleton: Skeleton3D) -> bool:
	var config:Dictionary=actor.get("_model_config")
	if not config.has("culture"):
		return str(config.get("scene","")).ends_with("/mire_goblin.glb") and player.has_animation(&"Death_A")
	if player.has_animation_library(NAMESPACE):return true
	var path:String=actor.call("_external_path",str(config.get("animationLibrary","")))
	if not path.ends_with("Universal_Animation_Library.glb"):return false
	var result:=NativeAnimationImporter.import_library(actor,path,skeleton,config.get("boneAliases",{}),
		PackedStringArray(["Idle_Hurt","Crouch_Idle","Hit_Knockback","LayToIdle"]),PackedStringArray(["Idle_Hurt","Crouch_Idle"]))
	var extra:=result.get("player") as AnimationPlayer
	if extra==null:return false
	if not (result.get("errors",PackedStringArray()) as PackedStringArray).is_empty():extra.free();return false
	var library:=extra.get_animation_library(&"")
	if library==null:extra.free();return false
	player.add_animation_library(NAMESPACE,library);extra.free();return true

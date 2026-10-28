class_name RLHairMotion
extends Node
## Secondary motion for one actor's RL hairstyle: Godot's SpringBoneSimulator3D
## on the hair's own skeleton, set up from the style's `asset.extras.rlHair`:
##
##   {"springs": [{"bones": ["lock_0_0", ...], "stiffness", "drag" (else
##                 "damping"), "gravity", "radius", "tail": [x, y, z]}, ...],
##    "collisions": [{"shape": "sphere"|"capsule", "offset": [x, y, z],
##                    "radius", "height", "axis": [x, y, z]}, ...]}
##
## Collision offsets are in hair_root space; a capsule lies along `axis`. A
## chain's last bone swings over the length of its `tail`. Godot's simulator
## has one damping term (drag), so an asset's separate `damping` is used only
## when it gives no `drag`. The simulator works in world space, so the head's
## own motion and the body's travel swing the locks.
##
## Motion is a budget, not a default. It runs only while `enabled` (HIGH
## quality and the lab's switch, set by RLHeadRig), within RANGE_METRES of the
## active camera, for at most MAX_ACTIVE actors, nearest first, and never while
## the actor rides (the mount pauses every modifier under the rider's skeleton
## and owns their clock). Everyone else's locks rest at their bind pose: an
## inactive SkeletonModifier3D leaves the skeleton's own pose alone. The
## ranking is shared: the first member processed in a frame ranks all of them.

const MAX_ACTIVE := 8
const RANGE_METRES := 12.0

## Every member in the scene, ranked once per frame.
static var _members: Array[RLHairMotion] = []
static var _ranked_frame := -1
## Off switches every member, for a measurement with motion off.
static var globally_enabled := true

var enabled := true:
	set(value):
		enabled = value
		if not enabled:
			_set_running(false)

var _simulator: SpringBoneSimulator3D
var _skeleton: Skeleton3D
var _running := false
var _allowed := false
## The actor (the CharacterBody3D above), found once.
var _actor_node: Node = null
var _actor_found := false


## Builds the simulator on the hair skeleton. False when the style declares no
## springs or names bones the skeleton lacks; the hair then simply stays put.
func configure(skeleton: Skeleton3D, extras: Dictionary) -> bool:
	_skeleton = skeleton
	var springs: Array = []
	for spring: Variant in extras.get("springs", []) as Array:
		if spring is not Dictionary:
			continue
		var bones: Array = (spring as Dictionary).get("bones", []) as Array
		var valid := not bones.is_empty()
		for bone: Variant in bones:
			valid = valid and skeleton.find_bone(str(bone)) >= 0
		if valid:
			springs.append(spring)
		else:
			RLHeadLibrary.warn_once("spring:" + str(bones), "hair spring names missing bones " + str(bones))
	if springs.is_empty():
		return false
	_simulator = SpringBoneSimulator3D.new()
	_simulator.name = "RLHairSprings"
	_simulator.setting_count = springs.size()
	for index: int in springs.size():
		var spring: Dictionary = springs[index]
		var bones: Array = spring["bones"]
		_simulator.set_root_bone_name(index, str(bones[0]))
		_simulator.set_end_bone_name(index, str(bones[bones.size() - 1]))
		# The last bone has no child to aim at: extend it along its parent's
		# direction by the chain's last segment so it swings too.
		_simulator.set_extend_end_bone(index, true)
		_simulator.set_end_bone_direction(index, SkeletonModifier3D.BONE_DIRECTION_FROM_PARENT)
		var tail: Variant = spring.get("tail")
		_simulator.set_end_bone_length(index, Vector3(float(tail[0]), float(tail[1]),
			float(tail[2])).length() if tail is Array and (tail as Array).size() >= 3
			else _last_segment(bones))
		_simulator.set_stiffness(index, float(spring.get("stiffness", 1.0)))
		_simulator.set_drag(index, float(spring.get("drag", spring.get("damping", 0.4))))
		_simulator.set_gravity(index, float(spring.get("gravity", 0.0)))
		_simulator.set_radius(index, float(spring.get("radius", 0.01)))
		_simulator.set_enable_all_child_collisions(index, true)
	skeleton.add_child(_simulator)
	var root_bone := "hair_root" if skeleton.find_bone("hair_root") >= 0 else skeleton.get_bone_name(0)
	for collision_value: Variant in extras.get("collisions", []) as Array:
		if collision_value is not Dictionary:
			continue
		var collision: Dictionary = collision_value
		var shape: SpringBoneCollision3D
		if str(collision.get("shape", "sphere")) == "capsule":
			var capsule := SpringBoneCollisionCapsule3D.new()
			capsule.radius = float(collision.get("radius", 0.08))
			capsule.height = float(collision.get("height", 0.2))
			var axis: Variant = collision.get("axis")
			if axis is Array and (axis as Array).size() >= 3:
				var direction := Vector3(float(axis[0]), float(axis[1]), float(axis[2]))
				if direction.length() > 0.001:
					capsule.rotation_offset = Quaternion(Vector3.UP, direction.normalized())
			shape = capsule
		else:
			var sphere := SpringBoneCollisionSphere3D.new()
			sphere.radius = float(collision.get("radius", 0.09))
			shape = sphere
		shape.bone_name = root_bone
		var offset: Variant = collision.get("offset", [])
		if offset is Array and (offset as Array).size() >= 3:
			shape.position_offset = Vector3(float(offset[0]), float(offset[1]), float(offset[2]))
		_simulator.add_child(shape)
	_simulator.active = false
	return true


func is_running() -> bool:
	return _running


func has_springs() -> bool:
	return _simulator != null


func _enter_tree() -> void:
	if not _members.has(self):
		_members.append(self)


func _exit_tree() -> void:
	_members.erase(self)
	_actor_found = false
	_actor_node = null


func _process(_delta: float) -> void:
	if _simulator == null:
		return
	var frame := Engine.get_process_frames()
	if frame != _ranked_frame:
		_ranked_frame = frame
		_rank(get_viewport().get_camera_3d())
	_set_running(_allowed and not _mounted())


## Allows the MAX_ACTIVE eligible members nearest the camera.
static func _rank(camera: Camera3D) -> void:
	var candidates: Array = []
	for member: RLHairMotion in _members:
		member._allowed = false
		if not is_instance_valid(member) or member._simulator == null or not member.enabled \
				or not globally_enabled or not member.can_process():
			continue
		var anchor := member._skeleton.global_position
		var distance := 0.0
		if camera != null:
			distance = camera.global_position.distance_to(anchor)
			if distance > RANGE_METRES:
				continue
		candidates.append([distance, member])
	candidates.sort_custom(func(a: Array, b: Array) -> bool: return float(a[0]) < float(b[0]))
	for index: int in mini(candidates.size(), MAX_ACTIVE):
		(candidates[index][1] as RLHairMotion)._allowed = true


func _set_running(running: bool) -> void:
	if _simulator == null or running == _running:
		return
	_running = running
	if running:
		# Wake from rest rather than from wherever the locks were left.
		_simulator.reset()
	_simulator.active = running


func _mounted() -> bool:
	if not _actor_found or (_actor_node != null and not is_instance_valid(_actor_node)):
		_actor_found = true
		var walker := get_parent()
		while walker != null and walker is not CharacterBody3D:
			walker = walker.get_parent()
		_actor_node = walker
	if _actor_node == null:
		return false
	var mount: Variant = _actor_node.get("_mount_visual")
	return mount != null and is_instance_valid(mount)


func _last_segment(bones: Array) -> float:
	if bones.size() < 2:
		return 0.05
	var last := _skeleton.get_bone_global_rest(_skeleton.find_bone(str(bones[bones.size() - 1])))
	var before := _skeleton.get_bone_global_rest(_skeleton.find_bone(str(bones[bones.size() - 2])))
	return maxf(0.005, last.origin.distance_to(before.origin))

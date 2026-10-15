extends SkeletonModifier3D
## Verlet cloth for the cape chains on the player rig.
##
## A cape skinned to the spine cannot avoid a leg. Measured against the shared
## clips, the body passes 254 mm behind the cape in a walk and 858 mm in a run,
## and weighting the hem to the thighs does not help: one cape spanning both
## legs follows their average, which is exactly where neither leg is.
##
## So the rig carries three chains of four bones - cape_{l,c,r}_01..04 - that no
## clip in the shared library names, and this drives them. Three chains rather
## than one because a single column cannot twist, and the halves of a cape have
## to part around a leg independently.
##
## The simulation runs in world space, not skeleton space, so the cape trails
## when the actor runs rather than only reacting to the spine bobbing. It is a
## SkeletonModifier3D so the engine orders it after the animation has posed the
## skeleton; writing bone poses from _process would race the AnimationPlayer.

const CHAINS: Array[String] = ["l", "c", "r"]
const LINKS := 4
## Heavier than the real 9.8: a cape driven by a skeleton has no air to push
## against, so weighting it down is what keeps the hem from flying up behind a
## moving actor.
const GRAVITY := Vector3(0.0, -14.0, 0.0)
## Fraction of velocity carried between steps. Cloth that keeps everything
## oscillates forever. 0.84 carried enough momentum to lift the hem well past
## the waist in motion and hold it there; this settles in about a quarter of a
## second and trails lower while travelling.
const DAMPING := 0.72
## Two passes is enough for a four-link chain and is the whole reason this is
## affordable. More iterations buy stiffness nobody can see on a cape.
const RELAX_PASSES := 2
## The leg capsules the cape is pushed out of, as a fraction over the measured
## thigh radius, so cloth rides clear of the skin rather than exactly on it.
const LEG_RADIUS := 0.115
## A frame longer than this is a hitch, not motion: clamping stops a stall from
## flinging the chain and leaving it to swing back for a second afterwards.
const MAX_STEP := 1.0 / 30.0
## Move further than this in one step and the actor was teleported, not walked.
const TELEPORT := 1.5
## Once the anchor is slower than this the wearer has stopped, and the cape
## should come back down briskly instead of drifting: gravity multiplies and
## the damping drops so the swing dies in a fraction of the travelling time.
const SETTLE_SPEED := 0.15
const SETTLE_GRAVITY := 25.0
const SETTLE_DAMPING := 0.30

var _cached := false
var _anchor := -1
var _bones: Array[PackedInt32Array] = []
var _points: Array[PackedVector3Array] = []
var _previous: Array[PackedVector3Array] = []
var _lengths: Array[PackedFloat32Array] = []
## Rest transforms never change after this modifier caches its skeleton. Keeping
## them beside the chain indices avoids asking Skeleton3D for the same twelve
## authored transforms every frame.
var _bone_rests: Array[Array] = []
var _legs: Array[PackedInt32Array] = []
var _settled := false
var _last_anchor := Vector3.ZERO
var _torso := PackedInt32Array()
var _lumbar := PackedInt32Array()
## Collision capsules keep their original order (torso, lumbar, left leg,
## right leg), but share one per-pass snapshot of their unique endpoint bones.
## This snapshot is filled before any cape bone is written.
enum CapsuleKind { TORSO, LUMBAR, LEG }
var _collision_bones := PackedInt32Array()
var _collision_pairs: Array[Vector2i] = []
var _collision_kinds := PackedInt32Array()
var _collision_world := PackedVector3Array()
## A capsule's endpoints, axis and squared span are invariant while the twelve
## cloth points are constrained in one modifier pass. The solver visits four
## capsules for each point in each relaxation pass, so retaining these four
## descriptors avoids recomputing the same axis/span and kind policy 96 times.
var _collision_axes := PackedVector3Array()
var _collision_spans := PackedFloat64Array()
var _collision_radii := PackedFloat64Array()
var _collision_reaches: Array[PackedFloat32Array] = []
var _empty_reach := PackedFloat32Array()
## Optional arithmetic-only extension. GDScript remains the complete fallback;
## the native object never reads the skeleton or writes a bone.
var _native_constraint_kernel: RefCounted
var _native_constraint_kernel_initialized := false
var _native_constraint_status := "disabled"
var _native_constraint_calls := 0
var _native_constraint_fallbacks := 0
## How far the worn torso reaches from each capsule's axis, sampled along it,
## or empty for a bare chest. Measured once per armour by the wearer, which is
## the only place the equipment is known.
var _torso_reach := PackedFloat32Array()
var _lumbar_reach := PackedFloat32Array()
## The trunk capsule is fatter than a leg, and fat enough to clear a bare back,
## which reaches 0.18 behind the spine.
##
## It is only a floor. One number cannot clear the torso ladder: the plainest
## shirt stands 0.196 behind the spine and a plated back reaches 0.29, so a
## capsule sized for either is wrong for the other, and sized for the first it
## let every cuirass in the game through the cloth. The wearer's own reach is
## measured off the armour actually worn and handed in through
## `set_torso_reach`; this is what a bare chest falls back to.
const TORSO_RADIUS := CapeDrape.BARE_TRUNK_RADIUS
## The spine bone's own local axis that points at the chest, found once at
## cache time against the rest hang. Multiplied by the bone's live basis each
## frame it gives a forward that follows the torso's lean and twist without
## being thrown off by an arm swinging across the body during an attack.
var _forward_local := Vector3.ZERO
## The sheet is authored hanging down, but its helper bones inherit the
## spine's tilted bind frame. Simulate a vertical material line and carry
## each bone's offset from it, so straightening the solver does not rotate
## the fabric away from the legs at rest.
var _hang_local := Vector3.DOWN
## Cape points stay this far behind the spine plane. The bone runs down the
## middle of the torso, so a small negative keeps cloth off the chest and the
## sternum while never disturbing a cape already hanging down the back.
const BACK_OFFSET := -0.02


func _cache(skeleton: Skeleton3D) -> bool:
	_cached = true
	_anchor = skeleton.find_bone("spine_03")
	if _anchor < 0:
		return false
	for chain in CHAINS:
		var bones := PackedInt32Array()
		var rests: Array[Transform3D] = []
		for link in range(LINKS):
			var bone := skeleton.find_bone("cape_%s_%02d" % [chain, link + 1])
			if bone < 0:
				return false
			bones.append(bone)
			rests.append(skeleton.get_bone_rest(bone))
		var lengths := PackedFloat32Array()
		for link in range(1, LINKS):
			lengths.append(rests[link].origin.length())
		# The last bone has no child, so its tip repeats its own drop.
		lengths.append(lengths[lengths.size() - 1])
		_bones.append(bones)
		_bone_rests.append(rests)
		_lengths.append(lengths)
		_points.append(PackedVector3Array())
		_previous.append(PackedVector3Array())
	for side in ["l", "r"]:
		var pair := PackedInt32Array()
		pair.append(skeleton.find_bone("thigh_%s" % side))
		pair.append(skeleton.find_bone("calf_%s" % side))
		if pair[0] >= 0 and pair[1] >= 0:
			_legs.append(pair)
	# The trunk keeps the upper sheet off the back the same way the legs
	# keep the hem off the shins; without it the simulation relaxes the
	# top links straight into the shoulder blades.
	var trunk := PackedInt32Array()
	trunk.append(skeleton.find_bone("spine_01"))
	trunk.append(skeleton.find_bone("neck_01"))
	if trunk[0] >= 0 and trunk[1] >= 0:
		_torso = trunk
	# The lumbar capsule covers the waist, between the trunk and the thighs.
	# Without it the lower back and the fauld of a cuirass sat in a gap that
	# no capsule guarded, and the cape crept through them during a lean.
	var lumbar := PackedInt32Array()
	lumbar.append(skeleton.find_bone("pelvis"))
	lumbar.append(skeleton.find_bone("spine_01"))
	if lumbar[0] >= 0 and lumbar[1] >= 0:
		_lumbar = lumbar
	if not _torso.is_empty():
		_cache_collision_pair(_torso, CapsuleKind.TORSO)
	if not _lumbar.is_empty():
		_cache_collision_pair(_lumbar, CapsuleKind.LUMBAR)
	for pair: PackedInt32Array in _legs:
		_cache_collision_pair(pair, CapsuleKind.LEG)
	_collision_world.resize(_collision_bones.size())
	_collision_axes.resize(_collision_pairs.size())
	_collision_spans.resize(_collision_pairs.size())
	_refresh_collision_descriptors()
	# The torso's forward axis, for holding the cape behind the back, taken
	# from the SPINE bone's own orientation rather than the shoulder line: an
	# attack swings one arm across the body, and a forward derived from the
	# arms swung with it, so the "behind the back" plane stopped being behind
	# the torso exactly when the swing threw the cape forward. The spine bone
	# turns with the torso and not the arms. Which of its local axes points at
	# the chest is found once, against the rest hang the cape drapes opposite.
	var anchor_rest := skeleton.get_bone_global_rest(_anchor)
	_hang_local = anchor_rest.basis.inverse() * Vector3.DOWN
	var up_rest := Vector3.UP
	var neck := skeleton.find_bone("neck_01")
	if neck >= 0:
		up_rest = (skeleton.get_bone_global_rest(neck).origin
			- anchor_rest.origin).normalized()
	var hang := skeleton.get_bone_global_rest(_bones[1][1]).origin - anchor_rest.origin
	hang -= up_rest * hang.dot(up_rest)
	if hang.length_squared() > 1e-9:
		hang = hang.normalized()
		var best := -2.0
		for local in [Vector3.RIGHT, Vector3.LEFT, Vector3.UP, Vector3.DOWN,
				Vector3.FORWARD, Vector3.BACK]:
			var world: Vector3 = (anchor_rest.basis * local).normalized()
			var flat := world - up_rest * world.dot(up_rest)
			if flat.length_squared() < 1e-4:
				continue
			# Forward opposes the hang, which points behind.
			var score: float = flat.normalized().dot(-hang)
			if score > best:
				best = score
				_forward_local = local
	_initialize_native_constraint_kernel()
	return true


func _initialize_native_constraint_kernel() -> void:
	if _native_constraint_kernel_initialized:
		return
	_native_constraint_kernel_initialized = true
	var requested := OS.get_environment("ELORIA_NATIVE_PRESENTATION").strip_edges().to_lower()
	if requested not in ["cape", "both", "all", "1"]:
		return
	_native_constraint_status = "requested"
	if not ClassDB.class_exists(&"NativeCapeConstraintKernel"):
		var extension_path := "res://bin/native_crowd.gdextension"
		if not FileAccess.file_exists(extension_path):
			_native_constraint_status = "extension_missing"
			return
		GDExtensionManager.load_extension(extension_path)
	if not ClassDB.class_exists(&"NativeCapeConstraintKernel"):
		_native_constraint_status = "class_unavailable"
		return
	_native_constraint_kernel = ClassDB.instantiate(&"NativeCapeConstraintKernel")
	if _native_constraint_kernel == null:
		_native_constraint_status = "instantiate_failed"
		return
	_native_constraint_status = "active"


func native_constraint_kernel_active() -> bool:
	return _native_constraint_kernel != null


func native_presentation_stats() -> Dictionary:
	return {
		"active": _native_constraint_kernel != null,
		"backend": "native" if _native_constraint_kernel != null else "gdscript",
		"status": _native_constraint_status,
		"nativeCalls": _native_constraint_calls,
		"fallbackCalls": _native_constraint_fallbacks,
	}


func _cache_collision_pair(pair: PackedInt32Array, kind: CapsuleKind) -> void:
	var slots := Vector2i()
	for endpoint: int in range(2):
		var bone: int = pair[endpoint]
		var slot: int = _collision_bones.find(bone)
		if slot < 0:
			slot = _collision_bones.size()
			_collision_bones.append(bone)
		if endpoint == 0:
			slots.x = slot
		else:
			slots.y = slot
	_collision_pairs.append(slots)
	_collision_kinds.append(kind)
	_collision_radii.append(TORSO_RADIUS if kind != CapsuleKind.LEG else LEG_RADIUS)
	_collision_reaches.append(_empty_reach)


## The torso's forward direction in world space, or ZERO if it is undefined.
## Recomputed each frame from the spine bone's live basis so a leaning,
## twisting attack carries the "behind the back" plane with the torso -- and
## only the torso, not the arms.
func _torso_forward(skeleton: Skeleton3D, to_world: Transform3D) -> Vector3:
	if _forward_local == Vector3.ZERO:
		return Vector3.ZERO
	return _torso_forward_from_pose(to_world,
		skeleton.get_bone_global_pose(_anchor))


func _torso_forward_from_pose(to_world: Transform3D,
		anchor_pose: Transform3D) -> Vector3:
	if _forward_local == Vector3.ZERO:
		return Vector3.ZERO
	var basis: Basis = to_world.basis * anchor_pose.basis
	var forward := (basis * _forward_local)
	if forward.length_squared() < 1e-9:
		return Vector3.ZERO
	return forward.normalized()


func _rest_joints(skeleton: Skeleton3D, to_world: Transform3D,
		chain: int) -> PackedVector3Array:
	"""Material-line joints, independent of the helper bones' bind tilt."""
	var frame := skeleton.get_bone_global_pose(_anchor)
	var down := (to_world.basis * frame.basis * _hang_local).normalized()
	return _rest_joints_from_pose(to_world, chain, frame, down)


func _rest_joints_from_pose(to_world: Transform3D, chain: int,
		frame: Transform3D, down: Vector3) -> PackedVector3Array:
	var joints := PackedVector3Array()
	var root_frame := frame * (_bone_rests[chain][0] as Transform3D)
	joints.append(to_world * root_frame.origin)
	for link in range(LINKS):
		joints.append(joints[link] + down * _lengths[chain][link])
	return joints


## The reach the worn torso was measured to have, along each capsule. Empty
## arrays mean a bare chest, which the constant already clears.
func set_torso_reach(trunk: PackedFloat32Array,
		lumbar: PackedFloat32Array) -> void:
	_torso_reach = trunk
	_lumbar_reach = lumbar
	_refresh_collision_descriptors()


func _refresh_collision_descriptors() -> void:
	for capsule: int in range(_collision_kinds.size()):
		var kind: int = _collision_kinds[capsule]
		if kind == CapsuleKind.TORSO:
			_collision_reaches[capsule] = _torso_reach
		elif kind == CapsuleKind.LUMBAR:
			_collision_reaches[capsule] = _lumbar_reach
		else:
			_collision_reaches[capsule] = _empty_reach


func _push_out_of_legs(skeleton: Skeleton3D, to_world: Transform3D,
		point: Vector3) -> Vector3:
	_snapshot_collision_world(skeleton, to_world)
	return _push_out_of_collision_snapshot(to_world, point)


func _snapshot_collision_world(skeleton: Skeleton3D,
		to_world: Transform3D) -> void:
	for slot: int in range(_collision_bones.size()):
		_collision_world[slot] = to_world * skeleton.get_bone_global_pose(
			_collision_bones[slot]).origin
	for capsule: int in range(_collision_pairs.size()):
		var pair: Vector2i = _collision_pairs[capsule]
		var axis := _collision_world[pair.y] - _collision_world[pair.x]
		_collision_axes[capsule] = axis
		_collision_spans[capsule] = axis.length_squared()


func _push_out_of_collision_snapshot(to_world: Transform3D,
		point: Vector3) -> Vector3:
	for capsule: int in range(_collision_pairs.size()):
		var pair: Vector2i = _collision_pairs[capsule]
		point = _push_out_of_capsule_axis(to_world, point,
			_collision_world[pair.x], _collision_axes[capsule],
			_collision_spans[capsule], _collision_radii[capsule],
			_collision_reaches[capsule])
	return point


func _push_out_of_capsule(skeleton: Skeleton3D, to_world: Transform3D,
		point: Vector3, pair: PackedInt32Array, radius: float,
		reach: PackedFloat32Array) -> Vector3:
	var a := to_world * skeleton.get_bone_global_pose(pair[0]).origin
	var b := to_world * skeleton.get_bone_global_pose(pair[1]).origin
	return _push_out_of_capsule_points(to_world, point, a, b, radius, reach)


func _push_out_of_capsule_points(to_world: Transform3D, point: Vector3,
		a: Vector3, b: Vector3, radius: float,
		reach: PackedFloat32Array) -> Vector3:
	var axis := b - a
	var span := axis.length_squared()
	return _push_out_of_capsule_axis(to_world, point, a, axis, span, radius, reach)


func _push_out_of_capsule_axis(to_world: Transform3D, point: Vector3,
		a: Vector3, axis: Vector3, span: float, radius: float,
		reach: PackedFloat32Array) -> Vector3:
	var travel := 0.0 if span < 1e-9 else clampf((point - a).dot(axis) / span, 0.0, 1.0)
	# The reach is sampled along the axis, so how far down the capsule the
	# point sits is exactly the index into it - which holds through a lean or
	# a twist that a height in the rig's rest space would not.
	if not reach.is_empty():
		var at := travel * float(reach.size() - 1)
		var low := int(at)
		var high := mini(low + 1, reach.size() - 1)
		radius = maxf(radius, lerpf(reach[low], reach[high], at - float(low)))
	var near := a + axis * travel
	var away := point - near
	var gap := away.length()
	if gap < radius:
		# Straight out from the bone, or straight back if the point landed
		# exactly on it, which happens the frame a leg swings through.
		var direction := (away / gap) if gap > 1e-5 else -to_world.basis.z.normalized()
		point = near + direction * radius
	return point


func _process_modification_with_delta(delta: float) -> void:
	var skeleton := get_skeleton()
	if skeleton == null:
		return
	if not _cached and not _cache(skeleton):
		return
	if _anchor < 0 or _bones.is_empty():
		return
	var to_world := skeleton.global_transform
	var to_local := to_world.affine_inverse()
	var step := minf(maxf(delta, 0.0), MAX_STEP)
	# Snapshot all animated inputs before any cape output is written. Cape bones
	# are descendants; their writes cannot leak into a later chain's body reads.
	var anchor_pose := skeleton.get_bone_global_pose(_anchor)
	var anchor_world := to_world * anchor_pose.origin
	_snapshot_collision_world(skeleton, to_world)
	var anchor_speed := 0.0 if step <= 0.0 else (
		anchor_world.distance_to(_last_anchor) / step)
	_last_anchor = anchor_world
	var still := anchor_speed < SETTLE_SPEED
	var fall := GRAVITY * (SETTLE_GRAVITY if still else 1.0) * step * step
	var damping := SETTLE_DAMPING if still else DAMPING
	# The back-of-the-torso plane, held for every chain this frame: a cape
	# swings and cannot pass to the chest, which is what an attack's lean and
	# twist made it do.
	var forward := _torso_forward_from_pose(to_world, anchor_pose)
	var plane_at := anchor_world.dot(forward) + BACK_OFFSET \
		if forward != Vector3.ZERO else 0.0
	var down := (to_world.basis * anchor_pose.basis * _hang_local).normalized()
	if _native_constraint_kernel != null and _try_native_constraint_step(
			skeleton, to_world, to_local, anchor_pose, down, fall, damping, forward,
			plane_at, anchor_world.y):
		_settled = true
		return

	for chain in range(_bones.size()):
		var rest := _rest_joints_from_pose(to_world, chain, anchor_pose, down)
		var points := _points[chain]
		if points.size() != rest.size() or not _settled:
			points = rest.duplicate()
			_previous[chain] = rest.duplicate()
		# The root joint is carried by the spine and never simulated.
		points[0] = rest[0]
		var previous := _previous[chain]
		previous[0] = rest[0]
		if points[1].distance_to(rest[1]) > TELEPORT:
			points = rest.duplicate()
			previous = rest.duplicate()
		for index in range(1, points.size()):
			var current := points[index]
			points[index] = current + (current - previous[index]) * damping + fall
			previous[index] = current
		for _pass in range(RELAX_PASSES):
			for index in range(1, points.size()):
				var offset := points[index] - points[index - 1]
				var length := offset.length()
				if length > 1e-6:
					points[index] = points[index - 1] + offset * (
						_lengths[chain][index - 1] / length)
			for index in range(1, points.size()):
				points[index] = _push_out_of_collision_snapshot(to_world, points[index])
				if forward != Vector3.ZERO:
					var ahead := points[index].dot(forward) - plane_at
					if ahead > 0.0:
						points[index] -= forward * ahead
				# A cape hangs from the spine, so it may stream up behind a
				# runner but never above its own attachment -- a corner that
				# crests the anchor is going over the shoulder, not trailing.
				# The anchor clears even a hard run's lift by half a metre, so
				# this frees the whole billow and only stops the spike.
				if points[index].y > anchor_world.y:
					points[index].y = anchor_world.y
		_points[chain] = points
		_previous[chain] = previous

		# Carry the authored bone frame with the material segment. Its origin
		# is offset from that segment, increasingly so down a tilted bind
		# chain. Rotating bones alone turns that offset into an outward hem
		# slope, even when every simulated segment has settled vertically.
		var parent := anchor_pose
		var authored := to_world * parent
		var rest_direction := (rest[1] - rest[0]).normalized()
		for link in range(LINKS):
			var bone := _bones[chain][link]
			var bone_rest: Transform3D = _bone_rests[chain][link]
			authored = authored * bone_rest
			var wanted := (points[link + 1] - points[link]).normalized()
			var turn := Basis.IDENTITY
			if wanted.length_squared() > 0.5:
				turn = Basis(Quaternion(rest_direction, wanted))
			var posed := to_local * Transform3D(turn * authored.basis,
				points[link] + turn * (authored.origin - rest[link]))
			var local_pose := parent.affine_inverse() * posed
			skeleton.set_bone_pose_position(bone, local_pose.origin)
			skeleton.set_bone_pose_rotation(bone, local_pose.basis.get_rotation_quaternion())
			parent = posed
	_settled = true


func _try_native_constraint_step(skeleton: Skeleton3D, to_world: Transform3D,
		to_local: Transform3D, anchor_pose: Transform3D, down: Vector3, fall: Vector3,
		damping: float, forward: Vector3, plane_at: float,
		anchor_y: float) -> bool:
	var rests: Array[PackedVector3Array] = []
	for chain: int in range(_bones.size()):
		rests.append(_rest_joints_from_pose(to_world, chain, anchor_pose, down))
	var solved := bool(_native_constraint_kernel.call("step",
		_points, _previous, rests, _lengths,
		_collision_world, _collision_pairs, _collision_axes,
		_collision_spans, _collision_radii, _collision_reaches,
		fall, damping, forward, plane_at, anchor_y, to_world, _settled))
	if not solved:
		_native_constraint_fallbacks += 1
		return false
	_native_constraint_calls += 1
	for chain: int in range(_bones.size()):
		_write_native_chain_bones(skeleton, chain, rests[chain], anchor_pose,
			to_world, to_local)
	return true


func _write_native_chain_bones(skeleton: Skeleton3D, chain: int,
		rest: PackedVector3Array, anchor_pose: Transform3D,
		to_world: Transform3D, to_local: Transform3D) -> void:
	var points := _points[chain]
	var parent := anchor_pose
	var authored := to_world * parent
	var rest_direction := (rest[1] - rest[0]).normalized()
	for link in range(LINKS):
		var bone := _bones[chain][link]
		var bone_rest: Transform3D = _bone_rests[chain][link]
		authored = authored * bone_rest
		var wanted := (points[link + 1] - points[link]).normalized()
		var turn := Basis.IDENTITY
		if wanted.length_squared() > 0.5:
			turn = Basis(Quaternion(rest_direction, wanted))
		var posed := to_local * Transform3D(turn * authored.basis,
			points[link] + turn * (authored.origin - rest[link]))
		var local_pose := parent.affine_inverse() * posed
		skeleton.set_bone_pose_position(bone, local_pose.origin)
		skeleton.set_bone_pose_rotation(bone,
			local_pose.basis.get_rotation_quaternion())
		parent = posed


func reset() -> void:
	"""Drop the chains back onto their rest hang, for a teleport or a respawn."""
	_settled = false

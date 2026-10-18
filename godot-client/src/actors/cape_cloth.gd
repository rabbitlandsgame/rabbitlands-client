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
## Optional mounted contact, supplied by the mount visual after rider posing.
var _mount_surface: RefCounted
var _mount_last_frame := Transform3D.IDENTITY
var _mount_frame_ready := false
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
## Where the cloth itself hangs, per chain and joint, as offsets from the
## material line in the skeleton's rest space. Empty means the material line.
##
## The material line drops from each chain's root bone, which sits against the
## spine; the sheet the chain carries hangs a hand's width behind it, and the
## cape was conformed offline to the bare legs, so below the seat it leans in
## on them. Simulating the material line put the capsules' clearance on the
## wrong line: the trunk pushed it out to its own surface and the sheet stood
## that hand's width further out again - a flare over the shoulder blades -
## while the hem, carrying the authored lean, followed the legs. The wearer
## measures where the sheet is (`CapeDrape.fabric_line`), and that line is
## what hangs plumb from the yoke and what the body pushes out.
var _fabric_rest: Array[PackedVector3Array] = []
var _anchor_rest_inverse := Basis.IDENTITY
## The legs, hip to knee and knee to ankle (thighs then shins, left then
## right), and how far what is worn reaches behind each, sampled along it
## (`set_shin_reach`).
##
## The leg capsules run hip to knee at a bare thigh's radius. That was all the
## hem had to clear while the material line hung a hand's width in front of
## the cloth. The cloth's own line hangs to the hem behind the calves, and in a
## fighting stance the back leg's shin and greave stood 25-40 mm through it,
## and the Vanguard's kneecops 26 mm above the knee. The native kernel takes
## four capsules and no more, so both solvers keep the measured line off the
## legs the same way, once they have run. A rider's legs hang beside the
## mount, and the mount surface owns the cape there.
const SHIN_RADIUS := CapeDrape.BARE_SHIN_RADIUS
var _shins: Array[PackedInt32Array] = []
var _shin_world := PackedVector3Array()
var _shin_reaches: Array[PackedFloat32Array] = []
## Each shin's back, in its calf bone's frame, and in world space this frame:
## the reach is kept per bearing from it (`CapeDrape.shin_reach`), and turns
## with the leg.
var _shin_back_local := PackedVector3Array()
var _shin_back_world := PackedVector3Array()
## Each shin's furthest reach per sample along it, at any bearing: a stretch of
## cloth further than that from the shin is clear without the bearing lookup.
var _shin_row_reach: Array[PackedFloat32Array] = []
## The cape's cross-section (`CapeDrape.fabric_line`): the chains' rest x off
## the middle one, the sheet's half-width at each joint, and how far its folds
## come in past the chains' line there, CapeDrape.SECTION_BINS from -x to +x
## for each joint. The middle chain carries nearly the whole sheet and the
## cloth between chains is a blend of them, so the legs are kept off the sheet
## where the chains together put it, not off each chain's own line.
var _section_knots := PackedFloat32Array()
var _section_halves := PackedFloat32Array()
var _section_folds := PackedFloat32Array()
var _section_blend := PackedFloat32Array()

func set_mount_surface(surface: RefCounted) -> void:
	_mount_surface = surface
	_mount_frame_ready = false
	reset()


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
	for segment: Array in [["thigh", "calf"], ["calf", "foot"]]:
		for side in ["l", "r"]:
			var shin := PackedInt32Array()
			shin.append(skeleton.find_bone("%s_%s" % [segment[0], side]))
			shin.append(skeleton.find_bone("%s_%s" % [segment[1], side]))
			_shins.append(shin)
			# The rig's back is -z in its rest space.
			_shin_back_local.append(Vector3.ZERO if shin[0] < 0 else
				skeleton.get_bone_global_rest(shin[0]).basis.inverse()
				* Vector3(0.0, 0.0, -1.0))
	# All four or none: the reaches the wearer measures come in this order.
	for shin: PackedInt32Array in _shins:
		if shin[0] < 0 or shin[1] < 0:
			_shins.clear()
			_shin_back_local.clear()
			break
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
	_shin_world.resize(_shins.size() * 2)
	_shin_back_world.resize(_shins.size())
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
	_anchor_rest_inverse = anchor_rest.basis.inverse()
	_hang_local = _anchor_rest_inverse * Vector3.DOWN
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


func _fabric_measured(chain: int) -> bool:
	return chain < _fabric_rest.size() and _fabric_rest[chain].size() == LINKS + 1


## Where the cloth of one chain stands as authored, carried by the spine: the
## material line plus the measured offsets. `carried` turns a rest-space
## offset into world space for this frame.
func _fabric_joints(rest: PackedVector3Array, chain: int,
		carried: Basis) -> PackedVector3Array:
	if not _fabric_measured(chain):
		return rest
	var offsets: PackedVector3Array = _fabric_rest[chain]
	var joints := PackedVector3Array()
	for index: int in range(rest.size()):
		joints.append(rest[index] + carried * offsets[index])
	return joints


## The hang the solver relaxes toward: plumb from the top of the cloth, which
## is where the rigid yoke lets go of it.
func _hang_from(top: Vector3, chain: int, down: Vector3) -> PackedVector3Array:
	var joints := PackedVector3Array()
	joints.append(top)
	for link in range(LINKS):
		joints.append(joints[link] + down * _lengths[chain][link])
	return joints


## Where the cloth hangs behind each chain's material line, joint by joint, in
## the skeleton's rest space (`CapeDrape.fabric_line`); empty for the material
## line itself. `section` is the cape's cross-section, as `fabric_line` gives
## it. The chains drop back onto a new hang.
func set_fabric_line(offsets: Array, section: Array = []) -> void:
	var line: Array[PackedVector3Array] = []
	for chain: Variant in offsets:
		line.append(PackedVector3Array(chain))
	var measured := section.size() == 4
	_section_knots = PackedFloat32Array(section[0]) if measured else PackedFloat32Array()
	_section_halves = PackedFloat32Array(section[1]) if measured else PackedFloat32Array()
	_section_folds = PackedFloat32Array(section[2]) if measured else PackedFloat32Array()
	_section_blend = PackedFloat32Array(section[3]) if measured else PackedFloat32Array()
	if line == _fabric_rest:
		return
	_fabric_rest = line
	_settled = false


## How far the legs reach behind each segment - left thigh, right thigh, left
## shin, right shin - by sample along it and bearing from the leg's back
## (`CapeDrape.shin_reach`): the body's own leg and whatever is worn over it.
## A missing or empty table leaves SHIN_RADIUS.
func set_shin_reach(reaches: Array) -> void:
	_shin_reaches.clear()
	for reach: Variant in reaches:
		_shin_reaches.append(PackedFloat32Array(reach))
	_shin_row_reach.clear()
	var columns := CapeDrape.SHIN_BEARINGS
	for reach: PackedFloat32Array in _shin_reaches:
		var rows := PackedFloat32Array()
		rows.resize(CapeDrape.REACH_SAMPLES)
		rows.fill(SHIN_RADIUS)
		if reach.size() == CapeDrape.REACH_SAMPLES * columns:
			for at: int in range(reach.size()):
				rows[at / columns] = maxf(rows[at / columns], reach[at])
		_shin_row_reach.append(rows)


func _keeps_off_legs() -> bool:
	if _mount_surface != null or _shins.is_empty() \
			or _section_knots.size() != _bones.size() \
			or _section_halves.size() != LINKS + 1 \
			or _section_folds.size() != (LINKS + 1) * CapeDrape.SECTION_BINS \
			or _section_blend.size() != _section_folds.size() * _bones.size():
		return false
	for chain: int in range(_bones.size()):
		if not _fabric_measured(chain):
			return false
	return true


## The measured line moved straight back, away from the chest, until the sheet
## the chains carry - between them and past the outer ones - clears the legs,
## after either solver. Back rather than out from a leg, so a chain does not
## slide across its neighbour. The links are read at their middles too: a link
## from beside the knee to below the calf passed straight through a shin with
## both ends clear of it.
func _keep_off_legs(forward: Vector3, carried: Basis) -> void:
	if forward == Vector3.ZERO:
		return
	# Across the cape is the rig's rest x, carried by the spine: the axis the
	# cross-section was measured along.
	var side := carried * Vector3.RIGHT
	side -= forward * side.dot(forward)
	if side.length_squared() < 1e-6:
		return
	side = side.normalized()
	var bins := CapeDrape.SECTION_BINS
	var deepest := 0.0
	for fold: float in _section_folds:
		deepest = maxf(deepest, fold)
	# What each leg segment can reach: its furthest reach anywhere, and so the
	# heights it spans. A level out of either is not read at all.
	var furthest := PackedFloat32Array()
	var lowest := PackedFloat32Array()
	var highest := PackedFloat32Array()
	for shin: int in range(_shins.size()):
		var reach := SHIN_RADIUS
		if shin < _shin_row_reach.size():
			for row: float in _shin_row_reach[shin]:
				reach = maxf(reach, row)
		furthest.append(reach)
		lowest.append(minf(_shin_world[shin * 2].y, _shin_world[shin * 2 + 1].y) - reach)
		highest.append(maxf(_shin_world[shin * 2].y, _shin_world[shin * 2 + 1].y) + reach)
	for index in range(1, LINKS + 1):
		for third: float in [0.0, 0.5]:
			if third > 0.0 and index == LINKS:
				continue
			var half := lerpf(_section_halves[index],
				_section_halves[mini(index + 1, LINKS)], third)
			var between := 2.0 * half / float(bins - 1)
			var level := PackedVector3Array()
			for chain: int in range(_bones.size()):
				level.append(_level_point(chain, index, third))
			var middle := level[1]
			for shin: int in range(_shins.size()):
				if middle.y < lowest[shin] or middle.y > highest[shin]:
					continue
				var knee := _shin_world[shin * 2]
				var axis := _shin_world[shin * 2 + 1] - knee
				var span := axis.length_squared()
				if span < 1e-9:
					continue
				var travel := clampf((middle - knee).dot(axis) / span, 0.0, 1.0)
				var nearest := clampf((knee + axis * travel - middle).dot(side), -half, half)
				# The cape's line there, its folds at their deepest, still clear
				# of the leg's furthest reach: nothing to read.
				var line := middle + side * nearest
				var along := clampf((line - knee).dot(axis) / span, 0.0, 1.0)
				var gap := line.distance_to(knee + axis * along) - deepest - between
				if gap >= furthest[shin]:
					continue
				# Its neighbours across only when the nearest stretch had to move.
				if _push_section(level, index, third, nearest, half, side, forward,
						shin, knee, axis, span):
					for offset: float in [-between, between]:
						_push_section(level, index, third, clampf(nearest + offset,
							-half, half), half, side, forward, shin, knee, axis, span)


## A chain's point `third` of the way from joint `index` to the next.
func _level_point(chain: int, index: int, third: float) -> Vector3:
	var points := _points[chain]
	return points[index] if third <= 0.0 else points[index].lerp(points[index + 1], third)


## Moves the chains carrying the sheet `across` the cape at one level back until
## that stretch of sheet, its folds in front, clears one leg segment. The sheet
## there is the blend of the chains its skin weights name, each carrying it at
## its own offset across; each chain moves by its share of the push, the least
## that moves the blend as far as it must go. Whether anything had to move.
func _push_section(level: PackedVector3Array, index: int, third: float,
		across: float, half: float, side: Vector3, forward: Vector3, shin: int,
		knee: Vector3, axis: Vector3, span: float) -> bool:
	var count := level.size()
	var bins := CapeDrape.SECTION_BINS
	var joint := float(index) + third
	var column := clampf((across / maxf(half, 1e-4) + 1.0) * 0.5 * float(bins - 1),
		0.0, float(bins) - 1.0001)
	var row := clampf(joint, 0.0, float(LINKS) - 0.0001)
	var low_row := int(row)
	var low_column := int(column)
	var fx := column - float(low_column)
	var fy := row - float(low_row)
	var top := (low_row * bins + low_column) * count
	var bottom := ((low_row + 1) * bins + low_column) * count
	var weights := Vector3.ZERO
	var base := Vector3.ZERO
	var norm := 0.0
	for chain: int in range(count):
		var weight := lerpf(lerpf(_section_blend[top + chain],
			_section_blend[top + count + chain], fx), lerpf(_section_blend[bottom + chain],
			_section_blend[bottom + count + chain], fx), fy)
		weights[chain] = weight
		if weight <= 0.0:
			continue
		base += (level[chain] + side * (across - _section_knots[chain])) * weight
		norm += weight * weight
	if norm <= 1e-6:
		return false
	var sample := base + forward * _section_fold(joint, across, half)
	var back := _band_clearance(shin, sample, forward, knee, axis, span)
	if back <= 0.0:
		return false
	for chain: int in range(count):
		if weights[chain] <= 0.0:
			continue
		var share := back * weights[chain] / norm
		var points := _points[chain]
		points[index] -= forward * share
		if third > 0.0:
			points[index + 1] -= forward * share
		_points[chain] = points
		level[chain] -= forward * share
	return true


## How far the sheet's folds come in past the chains' line at `joint`
## (fractional, down the chains) and `across` the cape, `half` either side.
func _section_fold(joint: float, across: float, half: float) -> float:
	var bins := CapeDrape.SECTION_BINS
	var column := clampf((across / maxf(half, 1e-4) + 1.0) * 0.5 * float(bins - 1),
		0.0, float(bins) - 1.0001)
	var row := clampf(joint, 0.0, float(LINKS) - 0.0001)
	var low_row := int(row)
	var low_column := int(column)
	var fx := column - float(low_column)
	var top := lerpf(_section_folds[low_row * bins + low_column],
		_section_folds[low_row * bins + low_column + 1], fx)
	var bottom := lerpf(_section_folds[(low_row + 1) * bins + low_column],
		_section_folds[(low_row + 1) * bins + low_column + 1], fx)
	return lerpf(top, bottom, row - float(low_row))


func _band_clearance(shin: int, sample: Vector3, forward: Vector3,
		knee: Vector3, axis: Vector3, span: float) -> float:
	if shin < _shin_row_reach.size():
		# Further than the leg reaches anywhere at this height is clear.
		var along := clampf((sample - knee).dot(axis) / span, 0.0, 1.0)
		var row := along * float(CapeDrape.REACH_SAMPLES - 1)
		var rows: PackedFloat32Array = _shin_row_reach[shin]
		var furthest := maxf(rows[int(row)], rows[mini(int(row) + 1,
			CapeDrape.REACH_SAMPLES - 1)])
		if sample.distance_squared_to(knee + axis * along) >= furthest * furthest:
			return 0.0
	return _clear_backward(sample, -forward, shin, knee, axis, span)


func _shin_reach(shin: int) -> PackedFloat32Array:
	return _shin_reaches[shin] if shin < _shin_reaches.size() else _empty_reach


## How far `sample` must move along `back` to leave one shin, whose reach
## depends on where round the shin the sample is: the exit through the radius
## at its bearing, read again where that exit lands, a few times over.
func _clear_backward(sample: Vector3, back: Vector3, shin: int, knee: Vector3,
		axis: Vector3, span: float) -> float:
	var moved := 0.0
	for _settle: int in range(3):
		var at := sample + back * moved
		var travel := (at - knee).dot(axis) / span
		var along := clampf(travel, 0.0, 1.0)
		var away := at - (knee + axis * along)
		var direction := Vector3.ZERO
		if travel > 0.0 and travel < 1.0:
			direction = axis / sqrt(span)
			away -= direction * away.dot(direction)
		var radius := _shin_radius(shin, along, away)
		if away.length_squared() >= radius * radius:
			return moved
		var move := back - direction * back.dot(direction)
		var a := move.length_squared()
		if a < 1e-6:
			return moved + radius - away.length()
		var b := away.dot(move)
		var c := away.length_squared() - radius * radius
		moved += (-b + sqrt(maxf(b * b - a * c, 0.0))) / a + 0.001
	return moved


## The shin's reach at a point `along` it and offset `away` from it.
func _shin_radius(shin: int, along: float, away: Vector3) -> float:
	var reach := _shin_reach(shin)
	var columns := CapeDrape.SHIN_BEARINGS
	if reach.size() != CapeDrape.REACH_SAMPLES * columns or away.length_squared() < 1e-10:
		return SHIN_RADIUS
	var bearing := rad_to_deg(acos(clampf(away.normalized().dot(
		_shin_back_world[shin]), -1.0, 1.0)))
	var column := clampf(bearing / CapeDrape.SHIN_BEARING_STEP - 0.5, 0.0,
		float(columns) - 1.0001)
	var row := along * float(CapeDrape.REACH_SAMPLES - 1)
	var low_row := mini(int(row), CapeDrape.REACH_SAMPLES - 2)
	var low_column := int(column)
	var fy := row - float(low_row)
	var fx := column - float(low_column)
	var top := lerpf(reach[low_row * columns + low_column],
		reach[low_row * columns + low_column + 1], fx)
	var bottom := lerpf(reach[(low_row + 1) * columns + low_column],
		reach[(low_row + 1) * columns + low_column + 1], fx)
	return maxf(SHIN_RADIUS, lerpf(top, bottom, fy))


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
	for shin: int in range(_shins.size()):
		for end: int in range(2):
			_shin_world[shin * 2 + end] = to_world * skeleton.get_bone_global_pose(
				_shins[shin][end]).origin
		_shin_back_world[shin] = (to_world.basis * skeleton.get_bone_global_pose(
			_shins[shin][0]).basis * _shin_back_local[shin]).normalized()


func _push_out_of_collision_snapshot(to_world: Transform3D,
		point: Vector3) -> Vector3:
	for capsule: int in range(_collision_pairs.size()):
		var pair: Vector2i = _collision_pairs[capsule]
		point = _push_out_of_capsule_axis(to_world, point,
			_collision_world[pair.x], _collision_axes[capsule],
			_collision_spans[capsule], _collision_radii[capsule],
			_collision_reaches[capsule])
	if _mount_surface != null:
		point = _mount_surface.call("project", point)
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
	if _mount_surface != null:
		# Mounted cloth travels with the rider. Damping absolute world velocity
		# acted like extreme air drag and flattened the cape at riding speed.
		# Carry both Verlet states, then simulate the remaining local response.
		if _mount_frame_ready:
			var carry := to_world * _mount_last_frame.affine_inverse()
			for chain: int in range(_points.size()):
				var carried := _points[chain]
				var carried_previous := _previous[chain]
				for i: int in range(carried.size()):
					carried[i] = carry * carried[i]
					carried_previous[i] = carry * carried_previous[i]
				_points[chain] = carried
				_previous[chain] = carried_previous
		_mount_last_frame = to_world
		_mount_frame_ready = true
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
	var fall := GRAVITY * (SETTLE_GRAVITY if still and _mount_surface == null else 1.0) * step * step
	var damping := SETTLE_DAMPING if still or _mount_surface != null else DAMPING
	# The back-of-the-torso plane, held for every chain this frame: a cape
	# swings and cannot pass to the chest, which is what an attack's lean and
	# twist made it do.
	var forward := _torso_forward_from_pose(to_world, anchor_pose)
	var plane_at := anchor_world.dot(forward) + BACK_OFFSET \
		if forward != Vector3.ZERO else 0.0
	var down := (to_world.basis * anchor_pose.basis * _hang_local).normalized()
	var anchor_carry := to_world.basis * anchor_pose.basis * _anchor_rest_inverse
	# A mounted cape stays on the GDScript solver: the native kernel has no mount surface.
	if _mount_surface == null and _native_constraint_kernel != null and _try_native_constraint_step(
			skeleton, to_world, to_local, anchor_pose, down, anchor_carry, fall,
			damping, forward, plane_at, anchor_world.y):
		_settled = true
		return

	var fabrics: Array[PackedVector3Array] = []
	for chain in range(_bones.size()):
		var rest := _rest_joints_from_pose(to_world, chain, anchor_pose, down)
		var fabric := _fabric_joints(rest, chain, anchor_carry)
		fabrics.append(fabric)
		if _fabric_measured(chain):
			rest = _hang_from(fabric[0], chain, down)
		var points := _points[chain]
		if points.size() != rest.size() or not _settled:
			points = rest.duplicate() if _mount_surface == null else _mount_surface.call("seed", rest, _lengths[chain])
			_previous[chain] = points.duplicate()
		# The root joint is carried by the spine and never simulated.
		points[0] = rest[0]
		var previous := _previous[chain]
		previous[0] = rest[0]
		if points[1].distance_to(rest[1]) > TELEPORT:
			points = rest.duplicate() if _mount_surface == null else _mount_surface.call("seed", rest, _lengths[chain])
			previous = points.duplicate()
		for index in range(1, points.size()):
			var current := points[index]
			points[index] = current + (current - previous[index]) * damping + fall
			if _mount_surface != null:
				var flow: Vector3 = _mount_surface.call("flow_acceleration", chain, float(index) / LINKS)
				points[index] += flow * step * step
			previous[index] = current
		for _pass in range(RELAX_PASSES if _mount_surface == null else 16):
			for index in range(1, points.size()):
				var offset := points[index] - points[index - 1]
				var length := offset.length()
				if length > 1e-6:
					points[index] = points[index - 1] + offset * (
						_lengths[chain][index - 1] / length)
			var material_length := 0.0
			for index in range(1, points.size()):
				material_length += _lengths[chain][index - 1]
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
				if _mount_surface != null:
					points[index] = _mount_surface.call("limit_lift", points[index], rest[0], material_length, float(index) / LINKS)
		_points[chain] = points
		_previous[chain] = previous
	if _keeps_off_legs():
		_keep_off_legs(forward, anchor_carry)
	for chain in range(_bones.size()):
		_write_chain_bones(skeleton, chain, fabrics[chain], anchor_pose, to_world, to_local)
	_settled = true


func _try_native_constraint_step(skeleton: Skeleton3D, to_world: Transform3D,
		to_local: Transform3D, anchor_pose: Transform3D, down: Vector3,
		carried: Basis, fall: Vector3, damping: float, forward: Vector3,
		plane_at: float, anchor_y: float) -> bool:
	# The kernel simulates whatever line it is handed: the cloth's own hang
	# when it was measured, the material line otherwise.
	var rests: Array[PackedVector3Array] = []
	var fabrics: Array[PackedVector3Array] = []
	for chain: int in range(_bones.size()):
		var rest := _rest_joints_from_pose(to_world, chain, anchor_pose, down)
		var fabric := _fabric_joints(rest, chain, carried)
		if _fabric_measured(chain):
			rest = _hang_from(fabric[0], chain, down)
		rests.append(rest)
		fabrics.append(fabric)
	var solved := bool(_native_constraint_kernel.call("step",
		_points, _previous, rests, _lengths,
		_collision_world, _collision_pairs, _collision_axes,
		_collision_spans, _collision_radii, _collision_reaches,
		fall, damping, forward, plane_at, anchor_y, to_world, _settled))
	if not solved:
		_native_constraint_fallbacks += 1
		return false
	_native_constraint_calls += 1
	if _keeps_off_legs():
		_keep_off_legs(forward, carried)
	for chain: int in range(_bones.size()):
		_write_chain_bones(skeleton, chain, fabrics[chain], anchor_pose,
			to_world, to_local)
	return true


## Carry the authored bone frames with the simulated cloth. A bone's origin is
## offset from the cloth it carries, increasingly so down a tilted bind chain;
## rotating bones alone turns that offset into an outward hem slope, even when
## every simulated segment has settled vertically. So each frame is turned from
## the direction its own stretch of cloth was authored in to the simulated one,
## about the cloth, and the offset rides along. Without a measured line the
## material line stands in for the cloth and every segment starts straight
## down; with one, an authored lean onto the legs is what gets straightened.
func _write_chain_bones(skeleton: Skeleton3D, chain: int,
		fabric: PackedVector3Array, anchor_pose: Transform3D,
		to_world: Transform3D, to_local: Transform3D) -> void:
	var points := _points[chain]
	var measured := _fabric_measured(chain)
	var parent := anchor_pose
	var authored := to_world * parent
	var rest_direction := (fabric[1] - fabric[0]).normalized()
	for link in range(LINKS):
		var bone := _bones[chain][link]
		var bone_rest: Transform3D = _bone_rests[chain][link]
		authored = authored * bone_rest
		if measured:
			rest_direction = (fabric[link + 1] - fabric[link]).normalized()
		var wanted := (points[link + 1] - points[link]).normalized()
		var turn := Basis.IDENTITY
		if wanted.length_squared() > 0.5:
			turn = Basis(Quaternion(rest_direction, wanted))
		var posed := to_local * Transform3D(turn * authored.basis,
			points[link] + turn * (authored.origin - fabric[link]))
		var local_pose := parent.affine_inverse() * posed
		skeleton.set_bone_pose_position(bone, local_pose.origin)
		skeleton.set_bone_pose_rotation(bone,
			local_pose.basis.get_rotation_quaternion())
		parent = posed


func reset() -> void:
	"""Drop the chains back onto their rest hang, for a teleport or a respawn."""
	_settled = false

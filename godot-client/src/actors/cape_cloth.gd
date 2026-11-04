extends SkeletonModifier3D
const ApprovedPlayer := preload("res://src/actors/cape_approved_player.gd")
const MountedFit := preload("res://src/actors/cape_mounted_fit.gd")
const MountedAttachment := preload("res://src/actors/cape_mounted_attachment.gd")
const MountedBodySurface := preload("res://src/actors/cape_mounted_body_surface.gd")
const MountedStatic := preload("res://src/actors/cape_mounted_static.gd")
const NativeCrowd := preload("res://src/runtime/native_crowd.gd")
var _approved_player: RefCounted
var _mounted_fit: RefCounted
var _mounted_body_surface: RefCounted
var _mounted_static: RefCounted
var _mounted_static_active := false
var _mounted_static_bootstrap_started := false
var _mounted_static_recovery := false
var _mounted_static_recovery_elapsed := 0.0
var _mounted_wake_active := false
var _mounted_wake_elapsed := 0.0
const MOUNTED_WAKE_SECONDS := .25
var _fitting_mounted_static := false
var _mounted_static_margin_m := 0.0
var _approved_actor: WeakRef
var _mounted_sources: Array[Dictionary] = []
var _unmounted_lengths: Array[PackedFloat32Array] = []
var _approved_profile := ""
var _approved_geometry_guard := true
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
const WALK_DAMPING := 0.42
## Damp relative motion rather than discarding the wearer's carried velocity.
## Absolute world damping acted like a strong headwind even at walking speed,
## folding the free sheet up against its rigid shoulder section.
const TRAVEL_CARRY := 0.85
var _last_translation := Vector3.INF
## Frame-level motion measurement and fixed-step carried motion have separate
## histories: a display frame may contain more than one simulation step.
var _last_simulation_translation := Vector3.INF
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
var _step_owed := 0.0
const FIXED_STEP := 1.0 / 60.0
## The unmounted solver's step: FIXED_STEP, or MAX_STEP (30 Hz) where the Low
## actor tier asks for it (`set_step_rate`). Mounted cloth keeps its own clock.
var _rate_step := FIXED_STEP
var _held_chain_positions := PackedVector3Array()
var _held_chain_rotations: Array[Quaternion] = []
var _last_anchor := Vector3.INF
var _frame_anchor_speed := 0.0
var _frame_travel_speed := 0.0
var _previous_frame_world := Transform3D.IDENTITY
var _frame_world_ready := false
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
var _native_mounted_constraint_kernel: RefCounted
var _native_mounted_constraint_calls := 0
var _native_mounted_constraint_fallbacks := 0
var _native_mounted_constraint_disabled := false
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
var _anchor_rest_origin := Vector3.ZERO
var _surface_samples: Array = []
var _surface_rest := PackedVector3Array()
var _surface_indices: Array[PackedInt32Array] = []
var _surface_weights: Array[PackedFloat32Array] = []
var _surface_norms := PackedVector2Array()
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

func configure_approved_motion(actor: Node, profile: String) -> void:
	if profile == _approved_profile and _approved_player != null:
		return
	var skeleton := get_skeleton()
	if skeleton == null:
		return
	_restore_mounted_attachment()
	_approved_profile = ""
	_approved_actor = weakref(actor)
	if not _unmounted_lengths.is_empty():
		_lengths = _unmounted_lengths
		_unmounted_lengths = []
	if _approved_player != null:
		for side: String in CHAINS:
			for link: int in LINKS:
				var bone := skeleton.find_bone("cape_%s_%02d" % [side, link + 1])
				if bone >= 0:
					skeleton.reset_bone_pose(bone)
	_approved_player = null
	_mounted_fit = null
	_mounted_body_surface = null
	_clear_mounted_static()
	if not profile.is_empty():
		var player := ApprovedPlayer.new()
		if player.configure(actor, skeleton, profile):
			_approved_player = player
			_approved_profile = profile
			player.hold_idle(skeleton)
	reset()

func _ensure_mounted_fit() -> void:
	if _mounted_fit != null or _approved_player == null or _approved_actor == null:
		return
	var actor := _approved_actor.get_ref() as Node
	if actor == null:
		return
	_install_mounted_attachment(actor)
	if _mounted_sources.is_empty():
		return
	var fitted := MountedFit.new()
	if fitted.configure(actor, get_skeleton(), _approved_profile):
		_mounted_fit = fitted
		var body := MountedBodySurface.new()
		if body.configure(actor, get_skeleton(), _approved_profile):
			_mounted_body_surface = body
	else:
		_restore_mounted_attachment()

func _install_mounted_attachment(actor: Node) -> void:
	if not _mounted_sources.is_empty():
		return
	var equipment: Dictionary = actor.get("_equipment_nodes")
	for value: Variant in equipment.get(2, []):
		var node := value as MeshInstance3D
		if node == null or not node.has_meta("cape_approved_profile"):
			continue
		var fitted := MountedAttachment.build(_approved_profile, node.mesh, get_skeleton(),
			"spine_neck", MountedAttachment.recommended_relief(_approved_profile))
		if fitted.is_empty():
			continue
		_mounted_sources.append({"node": weakref(node), "mesh": node.mesh, "skin": node.skin,
			"fitted_mesh": fitted.mesh, "fitted_skin": fitted.skin})
		node.mesh = fitted.mesh
		node.skin = fitted.skin
		node.set_meta("cape_mounted_attachment", fitted.get("reference_error_m", 0.0))
	if not _mounted_sources.is_empty():
		_refresh_attachment_silhouette()

func _refresh_attachment_silhouette() -> void:
	var actor := _approved_actor.get_ref() as Node if _approved_actor != null else null
	if actor == null:
		return
	var silhouette: Variant = actor.get("_silhouette")
	if silhouette != null and bool(silhouette.call("is_enabled")):
		silhouette.call("rebuild")

func _restore_mounted_attachment() -> void:
	var changed := false
	for source: Dictionary in _mounted_sources:
		var node := (source.node as WeakRef).get_ref() as MeshInstance3D
		if node == null:
			continue
		if node.mesh == source.fitted_mesh and node.skin == source.fitted_skin:
			node.mesh = source.mesh
			node.skin = source.skin
			node.remove_meta("cape_mounted_attachment")
			changed = true
	_mounted_sources.clear()
	if changed:
		_refresh_attachment_silhouette()

func set_approved_geometry_guard(enabled: bool) -> void:
	_approved_geometry_guard = enabled

func approved_motion_stats() -> Dictionary:
	var result: Dictionary = _approved_player.call("stats") if _approved_player != null else {"enabled": false, "fallback": true, "profile": "", "clip": ""}
	result["mounted_fit"] = _approved_player != null and _mount_surface != null
	result["mounted_ready"] = _mounted_fit != null and _mount_surface != null
	if result["mounted_ready"]:
		result["mounted"] = _mounted_fit.call("stats")
		if _mounted_body_surface != null:
			result["mounted_body"] = _mounted_body_surface.call("stats")
	result["mounted_static"] = _mounted_static_active
	result["mounted_static_bootstrap"] = _mounted_static_bootstrap_started
	result["mounted_static_recovery"] = _mounted_static_recovery
	result["mounted_wake_recovery"] = _mounted_wake_active
	if _mounted_static != null:
		result["mounted_static_pose"] = _mounted_static.call("stats")
	return result

func _clear_mounted_static() -> void:
	if _mounted_static != null:
		_mounted_static.call("clear")
	_mounted_static_active = false
	_mounted_static_bootstrap_started = false
	_mounted_static_recovery = false
	_mounted_static_recovery_elapsed = 0.0
	_mounted_wake_active = false
	_mounted_wake_elapsed = 0.0

func hold_mounted_static_pose(context: Dictionary) -> void:
	var skeleton := get_skeleton()
	var actor := _approved_actor.get_ref() as Node3D if _approved_actor != null else null
	if _mount_surface == null or _approved_player == null or actor == null \
			or skeleton == null or not actor.is_visible_in_tree() or not skeleton.is_visible_in_tree():
		return
	if actor.has_method("is_drawn") and not bool(actor.call("is_drawn")):
		return
	if not _cached and not _cache(skeleton):
		return
	_ensure_mounted_fit()
	if _mounted_fit == null:
		return
	_ensure_mounted_lengths(skeleton)
	if _mounted_static == null:
		_mounted_static = MountedStatic.new()
	var key := context.duplicate(true)
	key["profile"] = _approved_profile
	if not _mounted_static_active and bool(_mounted_static.call("has_pose")) \
			and int((_mounted_static.call("stats") as Dictionary).get("rendered_palette_updates", 0)) > 0:
		_mounted_static_recovery = true
		_mounted_static_recovery_elapsed = 0.0
	_mounted_static_active = true
	_mounted_wake_active = false
	if _mounted_static_recovery:
		_mounted_static.call("invalidate_context")
	if bool(_mounted_static.call("request_context", key)):
		# Start from the last accepted displayed material pose, not the rest
		# hang. A failed candidate must never become the next visible hold.
		var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
		_mounted_fit.call("prepare_attachment", skeleton, skeleton.global_transform, frame)
		var previous_roots: Array[Transform3D] = []
		for chain: int in 3:
			previous_roots.append(_mounted_fit.call("bone_pose", frame, chain * LINKS))
		var had_pose := bool(_mounted_static.call("has_pose"))
		var warm_start := had_pose
		if had_pose:
			_mounted_static.call("apply", actor, skeleton, previous_roots)
		var previous_poses: Array[Transform3D] = []
		for chain: PackedInt32Array in _bones:
			for bone: int in chain:
				previous_poses.append(skeleton.get_bone_pose(bone))
		if warm_start:
			_seed_mounted_material_pose(skeleton)
			_mounted_static_bootstrap_started = false
		elif not _mounted_static_bootstrap_started:
			# A first LOW-quality mount has no accepted cape palette to carry.
			# Seed from the mount once, then retain only the private candidate
			# particles across bounded retries until a valid pose is available.
			reset()
			_mounted_static_bootstrap_started = true
		# Fit once with conservative mount clearance. Ordinary display blends
		# and full-quality collision settings survive this bounded attempt.
		var old := Vector4(float(_mount_surface.get("idle_blend")),
			float(_mount_surface.get("moving_blend")), float(_mount_surface.get("gallop_blend")),
			float(_mount_surface.get("clearance")))
		var gait := str(context.get("gait", "idle"))
		var recovery_step := FIXED_STEP
		var tier := int(actor.get("_animation_tier"))
		if tier == AnimationGate.Tier.QUARTER:
			recovery_step *= 4.0
		elif tier == AnimationGate.Tier.HALF:
			recovery_step *= 2.0
		var recovery := 1.0
		if _mounted_static_recovery:
			_mounted_static_recovery_elapsed += recovery_step
			recovery = pow(clampf(_mounted_static_recovery_elapsed / MOUNTED_WAKE_SECONDS, 0.0, 1.0), 2.0)
		_mount_surface.set("idle_blend", lerpf(old.x, 1.0 if gait == "idle" else 0.0, recovery))
		_mount_surface.set("moving_blend", lerpf(old.y, 1.0 if gait in ["trot", "gallop"] else 0.0, recovery))
		_mount_surface.set("gallop_blend", lerpf(old.z, 1.0 if gait == "gallop" else 0.0, recovery))
		_mount_surface.call("update", 0.0, gait)
		_mount_surface.set("clearance", float(_mount_surface.get("clearance")) + MountedStatic.MOUNT_FIT_MARGIN_M * recovery)
		_mounted_static_margin_m = MountedStatic.BODY_FIT_MARGIN_M
		_fitting_mounted_static = true
		if warm_start:
			_fit_mounted_static_material(skeleton)
		else:
			_process_modification_with_delta(FIXED_STEP)
		_fitting_mounted_static = false
		_mounted_static_margin_m = 0.0
		_mount_surface.set("idle_blend", old.x)
		_mount_surface.set("moving_blend", old.y)
		_mount_surface.set("gallop_blend", old.z)
		_mount_surface.call("update", 0.0, gait)
		_mount_surface.set("clearance", old.w)
		var fitness: Dictionary = _mounted_fit.call("stats")
		fitness["finite"] = _mounted_material_pose_is_finite()
		var blending := not str(context.get("upper", "")).is_empty() \
			and (not bool(context.get("blend_settled", true)) or bool(context.get("returning", false)))
		_mounted_static_recovery = _mounted_static_recovery and recovery < 1.0
		if not bool(_mounted_static.call("capture", actor, skeleton, fitness, blending or _mounted_static_recovery)):
			var at := 0
			for chain: PackedInt32Array in _bones:
				for bone: int in chain:
					var pose := previous_poses[at]
					skeleton.set_bone_pose_position(bone, pose.origin)
					skeleton.set_bone_pose_rotation(bone, pose.basis.get_rotation_quaternion())
					skeleton.set_bone_pose_scale(bone, pose.basis.get_scale())
					at += 1
			skeleton.force_update_all_bone_transforms()
			# Discard rejected projector history; the next attempt starts from
			# the accepted palette again, with no failed velocity or warm carry.
			_mounted_fit.call("reset")
			if not warm_start:
				if bool(fitness["finite"]):
					for chain: int in _points.size():
						_previous[chain] = _points[chain].duplicate()
				else:
					_mounted_static_bootstrap_started = false
		else:
			_mounted_static_bootstrap_started = false
	var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
	_mounted_fit.call("prepare_attachment", skeleton, skeleton.global_transform, frame)
	var roots: Array[Transform3D] = []
	for chain: int in 3:
		roots.append(_mounted_fit.call("bone_pose", frame, chain * LINKS))
	_mounted_static.call("apply", actor, skeleton, roots)
	_remember_chain_pose(skeleton)

func _fit_mounted_static_material(skeleton: Skeleton3D) -> void:
	# A held panel already has a material-space shape. Project that exact
	# shape against the new rider pose; gravity and the legacy straight-chain
	# relaxation would rebuild it on every short upper-body blend.
	var world := skeleton.global_transform
	var source_frame: Transform3D = _approved_player.call("skin_frame", skeleton)
	_mounted_fit.call("prepare_pose", skeleton, world, source_frame)
	if _mounted_body_surface != null:
		_mounted_body_surface.call("prepare_pose", skeleton, world, source_frame)
	_snapshot_collision_world(skeleton, world)
	var frame: Transform3D = _mounted_fit.call("shape_frame", source_frame, _mount_surface)
	var fabrics: Array[PackedVector3Array] = []
	for chain: int in 3:
		fabrics.append(_mounted_fit.call("material_line", world * frame, chain))
	_project_mounted_skin(skeleton, world, fabrics)
	var anchor_pose := skeleton.get_bone_global_pose(_anchor)
	for chain: int in 3:
		var points := _points[chain]
		points[LINKS] = fabrics[chain][LINKS] + points[LINKS - 1] - fabrics[chain][LINKS - 1]
		_points[chain] = points
		_previous[chain] = points.duplicate()
		_write_chain_bones(skeleton, chain, fabrics[chain], anchor_pose, world, world.affine_inverse())
	_settled = true

func _ensure_mounted_lengths(skeleton: Skeleton3D) -> void:
	if _mount_surface == null or _mounted_fit == null or not _unmounted_lengths.is_empty():
		return
	_unmounted_lengths = _lengths.duplicate()
	for chain: int in 3:
		_lengths[chain] = _mounted_fit.call("lengths", chain)
		for link: int in LINKS:
			_lengths[chain][link] *= skeleton.global_basis.x.length()
	_settled = false

func _seed_mounted_material_pose(skeleton: Skeleton3D) -> void:
	var world := skeleton.global_transform
	for chain: int in 3:
		var points: PackedVector3Array = _mounted_fit.call("posed_material_line", skeleton,
			world, chain, _bones[chain])
		_points[chain] = points
		_previous[chain] = points.duplicate()
	_settled = true
	_step_owed = 0.0
	_previous_frame_world = world
	_frame_world_ready = true
	_mount_last_frame = world
	_mount_frame_ready = true
	_last_translation = world.origin
	_last_simulation_translation = world.origin
	_last_anchor = world * skeleton.get_bone_global_pose(_anchor).origin

func _mounted_material_pose_is_finite() -> bool:
	for chain: PackedVector3Array in _points:
		for point: Vector3 in chain:
			if not point.is_finite():
				return false
	for chain: PackedVector3Array in _previous:
		for point: Vector3 in chain:
			if not point.is_finite():
				return false
	return true

func _mounted_fit_stats_are_valid(fitness: Dictionary) -> bool:
	var gap := float(fitness.get("gap_m", INF))
	var strain := float(fitness.get("strain", INF))
	return int(fitness.get("iterations", 0)) > 0 and is_finite(gap) and is_finite(strain) \
		and gap <= MountedStatic.MAX_GAP_M and strain <= MountedStatic.MAX_STRAIN

func _resume_mounted_static(skeleton: Skeleton3D) -> void:
	var actor := _approved_actor.get_ref() as Node3D if _approved_actor != null else null
	if actor == null or _mounted_fit == null or _mounted_static == null:
		_clear_mounted_static()
		return
	reset()
	_mount_frame_ready = false
	var world := skeleton.global_transform
	var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
	_mounted_fit.call("prepare_attachment", skeleton, world, frame)
	var roots: Array[Transform3D] = []
	for chain: int in 3:
		roots.append(_mounted_fit.call("bone_pose", frame, chain * LINKS))
	if not bool(_mounted_static.call("apply", actor, skeleton, roots)):
		_clear_mounted_static()
		return
	_seed_mounted_material_pose(skeleton)
	_remember_chain_pose(skeleton)
	# Keep the accepted Actor-space palette for a later FULL -> static tier
	# change. It is refreshed only by accepted full-quality rendered frames.
	_mounted_static.call("invalidate_context")
	_mounted_static_active = false
	_mounted_static_bootstrap_started = false
	_mounted_static_recovery = false
	_mounted_static_recovery_elapsed = 0.0
	_mounted_wake_active = true
	_mounted_wake_elapsed = 0.0

func hold_approved_idle() -> void:
	# These local cape poses remain under spine_03. Body clips name only the
	# original65joints, so a sleeping modifier keeps the fitted idle at no
	# per-frame simulation cost.
	if _approved_player != null and _mount_surface == null:
		_approved_player.call("hold_idle", get_skeleton())

func _apply_approved_frame(skeleton: Skeleton3D, to_world: Transform3D,
		values: PackedVector3Array, delta: float) -> void:
	var anchor_pose := skeleton.get_bone_global_pose(_anchor)
	var carried := to_world.basis * anchor_pose.basis * _anchor_rest_inverse
	var down := (to_world.basis * anchor_pose.basis * _hang_local).normalized()
	var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
	var vectors := to_world.basis * frame.basis
	var inverse_vectors := vectors.inverse()
	var guard := _approved_geometry_guard or bool(_approved_player.call("needs_geometry_guard"))
	var fabrics: Array[PackedVector3Array] = []
	_snapshot_collision_world(skeleton, to_world)
	for chain: int in _bones.size():
		var rest := _rest_joints_from_pose(to_world, chain, anchor_pose, down)
		var fabric := _fabric_joints(rest, chain, carried)
		fabrics.append(fabric)
		var points := fabric.duplicate()
		for link: int in points.size():
			points[link] += vectors * values[chain * LINKS + mini(link, LINKS - 1)]
			if guard and link > 0:
				points[link] = _push_out_of_collision_snapshot(to_world, points[link])
		_points[chain] = points
	var forward := _torso_forward_from_pose(to_world, anchor_pose)
	# The reviewed cage supplies flow, not particle integration. Keep the
	# existing measured leg/fold guards for the wearer's actual kit/proportions.
	if guard:
		if _keeps_off_legs():
			_keep_off_legs(forward, carried)
		_keep_surface_clear(fabrics, to_world * anchor_pose.origin, carried, forward)
	for chain: int in _bones.size():
		for link: int in LINKS:
			values[chain * LINKS + link] = inverse_vectors * (_points[chain][link] - fabrics[chain][link])
		_previous[chain] = _points[chain].duplicate()
	_approved_player.call("write_pose", skeleton, values)
	_approved_player.call("commit", values, delta)
	_remember_chain_pose(skeleton)
	_settled = true

func _remember_chain_pose(skeleton: Skeleton3D) -> void:
	_held_chain_positions.clear()
	_held_chain_rotations.clear()
	for chain: PackedInt32Array in _bones:
		for bone: int in chain:
			_held_chain_positions.append(skeleton.get_bone_pose_position(bone))
			_held_chain_rotations.append(skeleton.get_bone_pose_rotation(bone))

func set_native_mounted_constraint_kernel(backend: RefCounted) -> void:
	_native_mounted_constraint_kernel = backend if not _native_mounted_constraint_disabled else null

func set_mount_surface(surface: RefCounted) -> void:
	_native_mounted_constraint_kernel = null
	_native_mounted_constraint_disabled = false
	_mount_surface = surface
	if surface == null:
		_restore_mounted_attachment()
	_mounted_fit = null
	_mounted_body_surface = null
	_clear_mounted_static()
	_mounted_static_margin_m = 0.0
	if surface == null and not _unmounted_lengths.is_empty():
		_lengths = _unmounted_lengths
		_unmounted_lengths = []
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
	_anchor_rest_origin = anchor_rest.origin
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
	# ELORIA_NATIVE_PRESENTATION (cape, both/1, all) or the feature's default;
	# the kernel comes from the verified client_runtime payload (native_crowd.gd).
	# The status is "disabled" when the cape kernel is not selected.
	var made := NativeCrowd.kernel("cape")
	_native_constraint_status = str(made.status)
	_native_constraint_kernel = made.object as RefCounted


func native_constraint_kernel_active() -> bool:
	return _native_constraint_kernel != null


func native_presentation_stats() -> Dictionary:
	return {
		"active": _native_constraint_kernel != null,
		"backend": "native" if _native_constraint_kernel != null else "gdscript",
		"status": _native_constraint_status,
		"nativeCalls": _native_constraint_calls,
		"fallbackCalls": _native_constraint_fallbacks,
		"mountedBackendAvailable": _native_mounted_constraint_kernel != null,
		"mountedCalls": _native_mounted_constraint_calls,
		"mountedFallbackCalls": _native_mounted_constraint_fallbacks,
		"mountedPointStateOwner": "packed_arrays",
		"counterWindow": "cumulative_since_cloth_node_creation",
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


## The chains carry one sheet. Independent capsule contacts can otherwise
## leave one strip at the knees and its neighbour at the shoulders, folding
## the skinned cloth through itself. Share the row's displacement while
## retaining each root's authored spacing and the cape's measured folds.
## Use the furthest-back contact: moving the other strips back preserves
## the clearance already found by the body and leg constraints.
func _keep_sheet_coherent(carried: Basis, forward: Vector3) -> void:
	if _mount_surface != null or _points.size() != 3 or forward == Vector3.ZERO:
		return
	for chain: int in range(3):
		if not _fabric_measured(chain) or _points[chain].size() != LINKS + 1:
			return
	var side := carried * Vector3.RIGHT
	side = (side - forward * side.dot(forward)).normalized()
	var up := forward.cross(side).normalized()
	for joint: int in range(1, LINKS + 1):
		var middle := _points[1][joint] - _points[1][0]
		var fall := 0.0
		var back := INF
		for chain: int in range(3):
			var displacement := _points[chain][joint] - _points[chain][0]
			fall += displacement.dot(up) / 3.0
			back = minf(back, displacement.dot(forward))
		var displacement := side * middle.dot(side) + up * fall + forward * back
		for chain: int in range(3):
			_points[chain][joint] = _points[chain][0] + displacement


func set_surface_samples(samples: Array) -> void:
	_surface_samples = samples
	_surface_rest.clear()
	_surface_indices.clear()
	_surface_weights.clear()
	_surface_norms.clear()
	for sample: Dictionary in samples:
		_surface_rest.append(sample.position)
		var indices := PackedInt32Array()
		var active_weights := PackedFloat32Array()
		var norms := Vector2.ZERO
		var weights: PackedFloat32Array = sample.weights
		for bone: int in weights.size():
			var weight := weights[bone]
			if weight <= 0.0:
				continue
			indices.append(bone)
			active_weights.append(weight)
			norms.x += weight * weight
			if bone % LINKS > 0:
				norms.y += weight * weight
		_surface_indices.append(indices)
		_surface_weights.append(active_weights)
		_surface_norms.append(norms)


## Project the skinned folds and hem, rather than only the joint line. With
## displacement skinning their positions are exactly the weighted sums below;
## pushing the responsible rows backward clears the rendered fabric too.
## The freely skinned top row may follow that correction in a torso twist;
## the shoulder attachment itself remains held by its spine skin weights.
func _keep_surface_clear(fabrics: Array[PackedVector3Array], anchor: Vector3,
		carried: Basis, forward: Vector3) -> void:
	if _mount_surface != null or forward == Vector3.ZERO or _surface_rest.is_empty() or not _fabric_measured(1):
		return
	# Sample positions and capsule spans do not change within the projection
	# passes. Keep only their active skin weights in the inner loop.
	var world := PackedVector3Array()
	for point: Vector3 in _surface_rest:
		world.append(anchor + carried * (point - _anchor_rest_origin))
	var axes := PackedVector3Array()
	var spans := PackedFloat64Array()
	var limits := PackedVector2Array()
	for shin: int in _shins.size():
		var start := _shin_world[shin * 2]
		var end := _shin_world[shin * 2 + 1]
		axes.append(end - start)
		spans.append(axes[shin].length_squared())
		var radius := SHIN_RADIUS
		if shin < _shin_row_reach.size():
			for reach: float in _shin_row_reach[shin]:
				radius = maxf(radius, reach)
		limits.append(Vector2(minf(start.y, end.y) - radius,
			maxf(start.y, end.y) + radius))
	for _pass: int in 4:
		var displacements := PackedVector3Array()
		for chain: int in _points.size():
			for link: int in LINKS:
				displacements.append(_points[chain][link] - fabrics[chain][link])
		var moved := false
		for sample: int in world.size():
			var indices := _surface_indices[sample]
			var weights := _surface_weights[sample]
			var point := world[sample]
			for at: int in indices.size():
				point += displacements[indices[at]] * weights[at]
			var plane_back := maxf(0.0, (point - anchor).dot(forward) - BACK_OFFSET)
			var first_link := 0 if plane_back > 0.0 else 1
			var norm := _surface_norms[sample].x if first_link == 0 else _surface_norms[sample].y
			if norm < 1e-6:
				continue
			var back := plane_back
			for shin: int in _shins.size():
				if point.y < limits[shin].x or point.y > limits[shin].y or spans[shin] < 1e-9:
					continue
				back = maxf(back, _band_clearance(shin, point, forward,
					_shin_world[shin * 2], axes[shin], spans[shin]))
			if back <= 0.0:
				continue
			moved = true
			for at: int in indices.size():
				var bone := indices[at]
				if bone % LINKS >= first_link:
					displacements[bone] -= forward * (back * weights[at] / norm)
		if not moved:
			return
		for chain: int in _points.size():
			var points := _points[chain]
			for link: int in LINKS:
				points[link] = fabrics[chain][link] + displacements[chain * LINKS + link]
			_points[chain] = points
		_keep_sheet_coherent(carried, forward)


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
	if _mount_surface != null and _mounted_fit != null and _mounted_body_surface != null:
		for iteration: int in 2:
			var plane := _mounted_skin_plane(point)
			if plane.normal == Vector3.ZERO or plane.distance_to(point) >= 0.0:
				break
			point -= plane.normal * plane.distance_to(point)
		return point
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


## Solve the unmounted cape `hz` times a second: 60, the rate every constant
## here was tuned at, or 30 for the Low actor tier
## (`ActorRenderQuality.local_cape_step_hz`). Under a 30 FPS cap a 60 Hz solver
## runs twice per drawn frame. A display frame never feeds the solver more than
## MAX_STEP, so rates below 30 mean 30; zero, negative or 60 and above mean 60.
## Mounted cloth keeps its own clock (see `_simulation_step`).
func set_step_rate(hz: int) -> void:
	_rate_step = MAX_STEP if hz > 0 and hz <= 30 \
		else (1.0 / float(hz) if hz > 30 and hz < 60 else FIXED_STEP)

func step_rate() -> int:
	return roundi(1.0 / _rate_step)

func _simulation_step() -> float:
	# Mounted browser cloth runs at 30 Hz; body, input and riding animation
	# retain their display-frame clock. Static fitting and desktop mounted cloth
	# keep 60 Hz. Unmounted cloth runs at the rate set_step_rate chose.
	if _fitting_mounted_static:
		return FIXED_STEP
	if _mount_surface != null:
		return MAX_STEP if OS.has_feature("web") else FIXED_STEP
	return _rate_step

## One solver step of `steps` x FIXED_STEP seconds (a 30 Hz cape: 2) stands
## for that many steps of the 60 Hz solver its constants were tuned at.
## Returns (damping, gravity scale) for it:
## - x: velocity keeps `damping` per 1/60 s, so `damping ^ steps` per step;
## - y: the gravity in `fall` grows with step^2, k^2 times a 60 Hz fall for k
##   = `steps`, while k damped 60 Hz steps settle at the velocity that
##   k (1 - d^k) / (1 - d) falls give. Scaling `fall` by
##   (1 - d^k) / (k (1 - d)) keeps the 60 Hz terminal velocity, hence its
##   trailing angle in a walk and its settling after a stop. With the settle
##   damping 0.30 that is 0.65 of the step^2 gravity, 0.71-0.86 walking.
## TRAVEL_CARRY needs no factor for that: it adds back (1 - damping) of the
## wearer's travel in the step, which is the corrected per-step share already.
## A bare chain at 30 Hz trails within 2 % of 60 Hz with these. A cape at rest
## on a wearer standing still takes less gravity (`_long_step_rest_scale`).
func _long_step_coefficients(damping: float, steps: float) -> Vector2:
	var decayed := pow(damping, steps)
	if steps <= 1.0 or damping >= 0.999:
		return Vector2(decayed, 1.0)
	return Vector2(decayed, (1.0 - decayed) / (steps * (1.0 - damping)))

## Below the first speed a cape on a wearer standing still is at rest, above
## the second it is still swinging down (m/s, its fastest simulated point).
const REST_SPEED := Vector2(0.05, 0.5)

## How much of a long step's gravity a cape on a wearer standing still takes,
## from at rest to swinging. Where cloth rests on the body or the legs its
## constraints settle it where one step's pull is balanced, so k 60 Hz steps'
## worth in one step (`_long_step_coefficients`) hung a worn 30 Hz cape 2-14 mm
## off the 60 Hz one. At rest it takes one 60 Hz step's pull,
## 1 / (k (1 + d + ... + d^(k-1))) of that, and rests where 60 Hz rests (within
## 0.3 mm measured); swinging it takes all of it and settles as fast as 60 Hz.
## It blends by the cloth's speed over the previous step. Walking keeps the
## whole pull: one 60 Hz step's worth there builds the trail at half speed.
func _long_step_rest_scale(damping: float, steps: float) -> float:
	if steps <= 1.0 or damping >= 0.999:
		return 1.0
	var settled := (1.0 - damping) / (steps * (1.0 - pow(damping, steps)))
	var fastest := 0.0
	for chain: int in range(mini(_points.size(), _previous.size())):
		var points := _points[chain]
		var previous := _previous[chain]
		if points.size() != previous.size():
			continue
		for index: int in range(1, points.size()):
			fastest = maxf(fastest, points[index].distance_squared_to(previous[index]))
	var speed := sqrt(fastest) / (steps * FIXED_STEP)
	return lerpf(settled, 1.0, smoothstep(REST_SPEED.x, REST_SPEED.y, speed))

## The measured sheet's guards (`_keep_sheet_coherent`, `_keep_off_legs`,
## `_keep_surface_clear`) move points without their previous positions, so
## what they move is carried as velocity. Two 60 Hz steps carry such a kick
## 1 + d times (d: the 60 Hz damping), one 30 Hz step once. Returns how far to
## move each guarded point's previous position back, per metre of correction,
## so that the next step carries the k-step share: (1 + d + ... + d^(k-1)) - 1
## after the step's own damping d^k. Walking only: at rest the guards hold the
## sheet against gravity, and an extra carry there would lift it off the body.
## Measured on worn capes: the peak trail in a run went from 23 % to 10 % below
## 60 Hz. What remains (walk about 16 %, steady run 21 % below) comes from
## `_keep_sheet_coherent` moving every strip to the furthest-back one once per
## step: twice a frame at 60 Hz. Without that guard both rates trail alike.
func _long_step_guard_carry(damping: float, steps: float) -> float:
	var decayed := pow(damping, steps)
	if steps <= 1.0 or decayed < 0.001 or damping >= 0.999:
		return 0.0
	return ((1.0 - decayed) / (1.0 - damping) - 1.0) / decayed

func _carry_guard_corrections(before: Array, carry: float) -> void:
	for chain: int in mini(before.size(), _points.size()):
		var was: PackedVector3Array = before[chain]
		var now := _points[chain]
		var previous := _previous[chain]
		if was.size() != now.size() or previous.size() != now.size():
			continue
		# The root joint is carried by the spine and never simulated.
		for index: int in range(1, now.size()):
			previous[index] -= (now[index] - was[index]) * carry
		_previous[chain] = previous

func _process_modification_with_delta(delta: float) -> void:
	# Verlet gravity scales with dt squared. Feeding display-frame jitter into
	# it made an idle cape continually change its equilibrium and wiggle.
	var skeleton := get_skeleton()
	if skeleton == null or (not _cached and not _cache(skeleton)) or _anchor < 0:
		return
	if _mount_surface != null and _approved_player != null and _mounted_fit == null:
		# Delay the mounted-only allocation until the first visible rider pose.
		# Its attachment adapter uses a deterministic canonical reference.
		_ensure_mounted_fit()
	_ensure_mounted_lengths(skeleton)
	if _mounted_static_active and not _fitting_mounted_static:
		_resume_mounted_static(skeleton)
	var world := skeleton.global_transform
	var anchor_world := world * skeleton.get_bone_global_pose(_anchor).origin
	# Measure input motion once per display frame. Re-reading it in two fixed
	# steps would call the second step stationary and multiply its gravity.
	_frame_anchor_speed = (anchor_world.distance_to(_last_anchor) / delta
		if delta > 0.0 and _last_anchor.is_finite() else 0.0)
	_frame_travel_speed = (Vector2(world.origin.x - _last_translation.x,
		world.origin.z - _last_translation.z).length() / delta
		if delta > 0.0 and _last_translation.is_finite() else 0.0)
	_last_anchor = anchor_world
	_last_translation = world.origin
	if _approved_player != null and _mount_surface == null:
		var authored: PackedVector3Array = _approved_player.call("step", skeleton, delta)
		if authored.size() == 12:
			_apply_approved_frame(skeleton, world, authored, delta)
			_previous_frame_world = world
			_frame_world_ready = true
			_step_owed = 0.0
			return
	var elapsed := clampf(delta, 0.0, MAX_STEP)
	if not _frame_world_ready or _previous_frame_world.origin.distance_to(world.origin) > TELEPORT:
		_previous_frame_world = world
		_frame_world_ready = true
	var fixed_step := _simulation_step()
	var next_step_time := fixed_step - _step_owed
	_step_owed += elapsed
	var stepped := false
	while _step_owed + 0.000001 >= fixed_step:
		_step_owed -= fixed_step
		# Spread a display frame's root motion across its fixed steps. Giving
		# both steps the final root position produces a jump followed by a stop.
		var fraction := clampf(next_step_time / maxf(elapsed, 0.000001), 0.0, 1.0)
		_simulate_step(fixed_step, _previous_frame_world.interpolate_with(world, fraction))
		next_step_time += fixed_step
		stepped = true
	_previous_frame_world = world
	if skeleton == null or not _settled:
		return
	# SkeletonModifier3D starts each display frame from the animation input.
	# Reapply the last solved cape on frames shorter than the simulation step;
	# otherwise a fast display alternates between the solved and authored hang.
	if stepped:
		_remember_chain_pose(skeleton)
		_remember_valid_mounted_rendered_pose(skeleton)
	elif _held_chain_positions.size() == _bones.size() * LINKS:
		var index := 0
		for chain: PackedInt32Array in _bones:
			for bone: int in chain:
				skeleton.set_bone_pose_position(bone, _held_chain_positions[index])
				skeleton.set_bone_pose_rotation(bone, _held_chain_rotations[index])
				index += 1
	if _approved_player != null and _mount_surface == null:
		_approved_player.call("observe_fallback", skeleton, delta)


func _remember_valid_mounted_rendered_pose(skeleton: Skeleton3D) -> void:
	if _mount_surface == null or _mounted_fit == null or _mounted_static_active \
			or _fitting_mounted_static:
		return
	var fitness: Dictionary = _mounted_fit.call("stats")
	if not _mounted_fit_stats_are_valid(fitness):
		return
	fitness["finite"] = _mounted_material_pose_is_finite()
	var actor := _approved_actor.get_ref() as Node3D if _approved_actor != null else null
	if actor == null:
		return
	if _mounted_static == null:
		_mounted_static = MountedStatic.new()
	_mounted_static.call("remember_rendered", actor, skeleton, fitness)

func _simulate_step(delta: float, simulation_world: Transform3D) -> void:
	var skeleton := get_skeleton()
	if skeleton == null:
		return
	if not _cached and not _cache(skeleton):
		return
	if _anchor < 0 or _bones.is_empty():
		return
	var to_world := simulation_world
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
	var wake_from: Array[PackedVector3Array] = []
	if _mounted_wake_active and _mount_surface != null and _mounted_fit != null:
		for points: PackedVector3Array in _points:
			wake_from.append(points.duplicate())
	var step := minf(maxf(delta, 0.0), MAX_STEP)
	# Snapshot all animated inputs before any cape output is written. Cape bones
	# are descendants; their writes cannot leak into a later chain's body reads.
	var anchor_pose := skeleton.get_bone_global_pose(_anchor)
	var anchor_world := to_world * anchor_pose.origin
	_snapshot_collision_world(skeleton, to_world)
	var still := _frame_anchor_speed < SETTLE_SPEED
	var fall := GRAVITY * (SETTLE_GRAVITY if still and _mount_surface == null else 1.0) * step * step
	var damping := SETTLE_DAMPING if still or _mount_surface != null else DAMPING
	var walking := not still and _mount_surface == null
	if walking:
		damping = lerpf(WALK_DAMPING, DAMPING, smoothstep(2.0, 4.0, _frame_travel_speed))
	var guard_carry := 0.0
	if step > FIXED_STEP:
		# A 30 Hz step: the Low tier's unmounted cape, or a browser rider. The
		# rider's gravity keeps its step^2 scale, as browser cloth always had.
		var steps := step / FIXED_STEP
		var coefficients := _long_step_coefficients(damping, steps)
		if _mount_surface == null:
			fall *= coefficients.y
			if still:
				fall *= _long_step_rest_scale(damping, steps)
		if walking:
			guard_carry = _long_step_guard_carry(damping, steps)
		damping = coefficients.x
	if walking and _last_simulation_translation.is_finite() and step > 0.0:
		var travel := to_world.origin - _last_simulation_translation
		if travel.length() < TELEPORT:
			fall += travel * (1.0 - damping) * TRAVEL_CARRY
	_last_simulation_translation = to_world.origin
	# The back-of-the-torso plane, held for every chain this frame: a cape
	# swings and cannot pass to the chest, which is what an attack's lean and
	# twist made it do.
	var forward := _torso_forward_from_pose(to_world, anchor_pose)
	var plane_at := anchor_world.dot(forward) + BACK_OFFSET \
		if forward != Vector3.ZERO else 0.0
	var down := (to_world.basis * anchor_pose.basis * _hang_local).normalized()
	var anchor_carry := to_world.basis * anchor_pose.basis * _anchor_rest_inverse
	# Both paths share the existing capsule/Verlet arithmetic. The mounted
	# extension adds the sampled mount surface, flow and sixteen relaxations.
	if _mount_surface != null and _mounted_fit == null and _native_mounted_constraint_kernel != null and _try_native_constraint_step(
			skeleton, to_world, to_local, anchor_pose, down, anchor_carry, fall,
			damping, forward, plane_at, anchor_world.y, true, step):
		_settled = true
		return
	if _mount_surface == null and _native_constraint_kernel != null and _try_native_constraint_step(
			skeleton, to_world, to_local, anchor_pose, down, anchor_carry, fall,
			damping, forward, plane_at, anchor_world.y, false, 0.0, guard_carry):
		_settled = true
		return

	var fabrics: Array[PackedVector3Array] = []
	if _mount_surface != null and _mounted_fit != null:
		var source_frame: Transform3D = _approved_player.call("skin_frame", skeleton)
		_mounted_fit.call("prepare_pose", skeleton, to_world, source_frame)
		if _mounted_body_surface != null:
			_mounted_body_surface.call("prepare_pose", skeleton, to_world, source_frame)
	for chain in range(_bones.size()):
		var rest := _rest_joints_from_pose(to_world, chain, anchor_pose, down)
		var fabric := _fabric_joints(rest, chain, anchor_carry)
		if _mount_surface != null and _mounted_fit != null:
			var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
			frame = _mounted_fit.call("shape_frame", frame, _mount_surface)
			fabric = _mounted_fit.call("material_line", to_world * frame, chain)
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
				if forward != Vector3.ZERO and not (_mount_surface != null and _mounted_fit != null):
					var ahead := points[index].dot(forward) - plane_at
					if ahead > 0.0:
						points[index] -= forward * ahead
				# A cape hangs from the spine, so it may stream up behind a
				# runner but never above its own attachment -- a corner that
				# crests the anchor is going over the shoulder, not trailing.
				# The anchor clears even a hard run's lift by half a metre, so
				# this frees the whole billow and only stops the spike.
				if points[index].y > anchor_world.y and not (_mount_surface != null and _mounted_fit != null):
					points[index].y = anchor_world.y
				if _mount_surface != null:
					var material_side_offset := 0.0
					if _mounted_fit != null:
						var side: Vector3 = _mount_surface.get("side")
						material_side_offset = (fabric[index] - fabric[0]).dot(side)
					points[index] = _mount_surface.call("limit_lift", points[index], rest[0], material_length, float(index) / LINKS, material_side_offset)
		_points[chain] = points
		_previous[chain] = previous
	var guarded: Array = _points.duplicate(true) if guard_carry > 0.0 else []
	_keep_sheet_coherent(anchor_carry, forward)
	if _keeps_off_legs():
		_keep_off_legs(forward, anchor_carry)
	_keep_sheet_coherent(anchor_carry, forward)
	_keep_surface_clear(fabrics, anchor_world, anchor_carry, forward)
	if guard_carry > 0.0:
		_carry_guard_corrections(guarded, guard_carry)
	if _mount_surface != null and _mounted_fit != null:
		_keep_mounted_material_spacing(fabrics)
		if not wake_from.is_empty():
			var blend := pow(clampf(_mounted_wake_elapsed / MOUNTED_WAKE_SECONDS, 0.0, 1.0), 2.0)
			for chain: int in _points.size():
				var points := _points[chain]
				var previous := _previous[chain]
				for link: int in range(1, points.size()):
					points[link] = wake_from[chain][link].lerp(points[link], blend)
					previous[link] = wake_from[chain][link]
				_points[chain] = points
				_previous[chain] = previous
			_mounted_wake_elapsed += step
			_mounted_wake_active = _mounted_wake_elapsed < MOUNTED_WAKE_SECONDS
		_project_mounted_skin(skeleton, to_world, fabrics)
	for chain in range(_bones.size()):
		_write_chain_bones(skeleton, chain, fabrics[chain], anchor_pose, to_world, to_local)
	_settled = true

func _keep_mounted_material_spacing(fabrics: Array[PackedVector3Array]) -> void:
	# Legacy helper columns are straight. The approved cape's weighted row
	# centres widen toward the hem; pinning every row to its root's X would
	# pull each side inward by almost ten centimetres. Carry one lateral wave
	# through the original material spacing instead.
	var side: Vector3 = _mount_surface.get("side")
	for link: int in range(1, LINKS + 1):
		var wave := clampf((_points[1][link] - fabrics[1][link]).dot(side), -.04, .04)
		for chain: int in 3:
			var points := _points[chain]
			var previous := _previous[chain]
			var correction := side * ((fabrics[chain][link] - points[link]).dot(side) + wave)
			points[link] += correction
			previous[link] += correction
			_points[chain] = points
			_previous[chain] = previous

func _mounted_skin_contact(point: Vector3) -> Vector3:
	var plane := _mounted_skin_plane(point)
	return point - plane.normal * minf(0.0, plane.distance_to(point))

func _mounted_skin_plane(point: Vector3) -> Plane:
	var result: Plane = _mount_surface.call("contact_plane", point)
	var depth := -result.distance_to(point) if result.normal != Vector3.ZERO else 0.0
	var covered := false
	if _mounted_body_surface != null:
		var body: Dictionary = _mounted_body_surface.call("contact", point)
		covered = bool(body.get("covered", false))
		var plane: Plane = body.get("plane", Plane())
		if plane.normal != Vector3.ZERO and (result.normal == Vector3.ZERO or -plane.distance_to(point) > depth):
			result = plane
			depth = maxf(depth, -plane.distance_to(point))
	for capsule: int in _collision_pairs.size():
		if covered and _collision_kinds[capsule] in [CapsuleKind.TORSO, CapsuleKind.LUMBAR]:
			continue
		var pair: Vector2i = _collision_pairs[capsule]
		var a := _collision_world[pair.x]
		var axis := _collision_axes[capsule]
		var span := _collision_spans[capsule]
		var travel := 0.0 if span < 0.000001 else clampf((point - a).dot(axis) / span, 0.0, 1.0)
		var radius := _collision_radii[capsule]
		var reach: PackedFloat32Array = _collision_reaches[capsule]
		if not reach.is_empty():
			var at := travel * float(reach.size() - 1)
			radius = maxf(radius, lerpf(reach[int(at)], reach[mini(int(at) + 1, reach.size() - 1)], at - int(at)))
		radius = radius * get_skeleton().global_basis.x.length() + .015 + _mounted_static_margin_m
		var near := a + axis * travel
		var away := point - near
		var gap := radius - away.length()
		if gap > depth and away.length_squared() > .000001:
			var normal := away.normalized()
			result = Plane(normal, (near + normal * radius).dot(normal))
			depth = gap
	return result

func _project_mounted_skin(skeleton: Skeleton3D, world: Transform3D, fabrics: Array[PackedVector3Array]) -> void:
	var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
	frame = _mounted_fit.call("shape_frame", frame, _mount_surface)
	var translations := PackedVector3Array()
	for chain: int in 3:
		for link: int in LINKS:
			translations.append(_points[chain][link] - fabrics[chain][link])
	# The numeric batch replaces the complete contact query, including the
	# actual garment surface. Keep the script path when that surface has no
	# native handle; capsules alone cannot safely stand in for it.
	var native_body: RefCounted = null
	if _mounted_body_surface != null:
		native_body = _mounted_body_surface.call("get_native_handle") as RefCounted
	if native_body != null:
		_mounted_fit.call("set_native_contacts", {
			"collision_world": _collision_world, "collision_pairs": _collision_pairs,
			"collision_axes": _collision_axes, "collision_spans": _collision_spans,
			"collision_radii": _collision_radii, "collision_reaches": _collision_reaches,
			"collision_kinds": _collision_kinds,
			"body_margin_m": .015 + _mounted_static_margin_m},
			_mount_surface.call("native_snapshot", _simulation_step()), native_body)
	else:
		_mounted_fit.call("set_native_contacts", {}, PackedFloat64Array(), null)
	var projected: PackedVector3Array = _mounted_fit.call("project", skeleton, world, frame, translations, _mounted_skin_contact, _mounted_skin_plane)
	for chain: int in 3:
		for link: int in LINKS:
			var bone := chain * LINKS + link
			var correction := projected[bone] - translations[bone]
			_points[chain][link] += correction
			_previous[chain][link] += correction


func _try_native_constraint_step(skeleton: Skeleton3D, to_world: Transform3D,
		to_local: Transform3D, anchor_pose: Transform3D, down: Vector3,
		carried: Basis, fall: Vector3, damping: float, forward: Vector3,
		plane_at: float, anchor_y: float, mounted := false, step := 0.0,
		guard_carry := 0.0) -> bool:
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
	var solved := false
	if mounted:
		solved = bool(_native_mounted_constraint_kernel.call("step_mounted_cape",
			_points, _previous, rests, _lengths,
			_collision_world, _collision_pairs, _collision_axes,
			_collision_spans, _collision_radii, _collision_reaches,
			fall, damping, forward, plane_at, anchor_y, to_world, _settled,
			_mount_surface.call("native_snapshot", step)))
		if not solved:
			_native_mounted_constraint_fallbacks += 1
			_native_mounted_constraint_disabled = true
			_native_mounted_constraint_kernel = null
			return false
		_native_mounted_constraint_calls += 1
	else:
		solved = bool(_native_constraint_kernel.call("step",
			_points, _previous, rests, _lengths,
			_collision_world, _collision_pairs, _collision_axes,
			_collision_spans, _collision_radii, _collision_reaches,
			fall, damping, forward, plane_at, anchor_y, to_world, _settled))
		if not solved:
			_native_constraint_fallbacks += 1
			return false
		_native_constraint_calls += 1
	var guarded: Array = _points.duplicate(true) if guard_carry > 0.0 else []
	_keep_sheet_coherent(carried, forward)
	if _keeps_off_legs():
		_keep_off_legs(forward, carried)
	_keep_sheet_coherent(carried, forward)
	_keep_surface_clear(fabrics, to_world * anchor_pose.origin, carried, forward)
	if guard_carry > 0.0:
		_carry_guard_corrections(guarded, guard_carry)
	for chain: int in range(_bones.size()):
		_write_chain_bones(skeleton, chain, fabrics[chain], anchor_pose,
			to_world, to_local)
	return true


## Measured unmounted cloth uses a displacement lattice: the original bone
## bases retain the folds while skin weights blend the simulated row offsets.
## Mounted cloth and unmeasured rigs retain their original rotating frames,
## including the offset between each bind frame and its material line.
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
		if _approved_player != null:
			# The fitted skin's neutral frame differs from the original helper
			# rest. Use it for legacy/mounted motion as well as authored cages.
			authored = to_world * (_approved_player.call("neutral_bone_pose", skeleton, chain * LINKS + link) as Transform3D)
			if _mount_surface != null and _mounted_fit != null:
				var frame: Transform3D = _approved_player.call("skin_frame", skeleton)
				frame = _mounted_fit.call("shape_frame", frame, _mount_surface)
				authored = to_world * (_mounted_fit.call("bone_pose", frame, chain * LINKS + link) as Transform3D)
		if measured:
			rest_direction = (fabric[link + 1] - fabric[link]).normalized()
		var wanted := (points[link + 1] - points[link]).normalized()
		var turn := Basis.IDENTITY
		if wanted.length_squared() > 0.5:
			turn = Basis(Quaternion(rest_direction, wanted))
		var posed := to_local * Transform3D(turn * authored.basis,
			points[link] + turn * (authored.origin - fabric[link]))
		if measured and (_mount_surface == null or _mounted_fit != null):
			# Measured rows are a displacement lattice for the actual skin.
			# Rotating an off-line bind frame about each independently tilted
			# segment folds its vertices over the neighbouring row in a run.
			# Shared translations retain the authored cross-section and let
			# the existing skin weights interpolate a continuous curved sheet.
			posed = to_local * Transform3D(authored.basis,
				authored.origin + points[link] - fabric[link])
		var local_pose := parent.affine_inverse() * posed
		skeleton.set_bone_pose_position(bone, local_pose.origin)
		skeleton.set_bone_pose_rotation(bone,
			local_pose.basis.get_rotation_quaternion())
		parent = posed


func reset() -> void:
	"""Drop the chains back onto their rest hang, for a teleport or a respawn."""
	_settled = false
	_step_owed = 0.0
	_last_anchor = Vector3.INF
	_last_translation = Vector3.INF
	_last_simulation_translation = Vector3.INF
	_frame_world_ready = false
	var skeleton := get_skeleton()
	if skeleton != null:
		_previous_frame_world = skeleton.global_transform
		_frame_world_ready = true
		_last_translation = _previous_frame_world.origin
		if _anchor >= 0:
			_last_anchor = _previous_frame_world * skeleton.get_bone_global_pose(_anchor).origin
	_held_chain_positions.clear()
	_held_chain_rotations.clear()
	if _approved_player != null:
		_approved_player.call("reset")
	if _mounted_fit != null:
		_mounted_fit.call("reset")

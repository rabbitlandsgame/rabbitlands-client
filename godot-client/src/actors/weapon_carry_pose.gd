extends SkeletonModifier3D
## How a held weapon sits for what the body is doing.
##
## Walking and running aim the wrists after locomotion, keeping each weapon in
## its actual grip while the shoulders and elbows retain the animation's full
## arm swing. The skeleton restores the animation pose after modifiers, so
## this never changes shared clips or leaves a wrist correction behind in
## another action. Each wrist is turned the least way that points its weapon
## ahead, so the hand keeps the roll the stride gives it: hanging palm to the
## thigh with the thumb forward, which is the side the fist grip's blade
## leaves by. Writing one roll for the weapon instead - its edge out to the
## right, as this did while every weapon shared the old socket - lays the
## knuckles of a fist grip out flat, palm down over the hilt.
##
## At ease every rigid held weapon stays in its fighting socket, with the
## fingers closed around that grip. The wrist lowers it ahead by up to 45
## degrees, limited by the piece's reach to keep its far end above the floor.
## Long staves and blades use the same rule; the ranged bow owns its visual
## pose and only asks this modifier to close its left hand at ease.

const TRAVEL_ACTIONS: Array[StringName] = [&"walk", &"run"]

## How far a piece stood on one end may slide through the fist before that end
## is dragged after it, in metres at the piece's full size. A planted haft is
## held loosely and the hand rides up and down it - a quarter metre covers the
## deepest an emote drops the hand - but a blade leant on its tip is held by
## its hilt, which leaves only the play a fist has round a grip.
const PLANT_SLIDE := 0.25
const LEAN_SLIDE := 0.02
## How far off the floor the registry's grip may hold the point a planted or
## leant piece rests on and still set it down there. Through the idle it holds
## a butt a centimetre or two off and a leant tip up to eight at the top of its
## sway; anything farther is a pose that is not the idle's - the bind pose an
## actor is built in, which the first frames of a new actor can still be in
## when they are blended - and setting the piece down there stood a staff on a
## point at shoulder height for as long as it was held.
const SET_DOWN_HEIGHT := 0.15
## And the height it is set down at: the least the registry's grip lets a
## butt or a leant tip come to the floor through the idle
## (import_generated_weapons.FLOOR_CLEARANCE). Set down wherever the frame it
## settles in happens to hold it, a leant greatsword rested its tip eight
## centimetres up for good, at the top of the idle's sway.
const REST_HEIGHTS := {&"plant": 0.01, &"lean": 0.02}
## How near the floor anything else is let come at ease before it is lifted.
const GUARD_HEIGHT := 0.01
## How long the grip has to have been at ease before a piece is set down: the
## grip and the clip cross-fade together, so the last frames of a swing's
## recovery still have the hand on its way back when the grip arrives, and a
## twin-bladed staff set down then stood leant thirty degrees, a blade in the
## floor, for the rest of the idle.
const SET_DOWN_AFTER := 0.1
## How far the set-down end may stray from where the registry's grip would put
## it before it is picked up and set down again. The idle sways that end six
## or seven centimetres and a reel drops the hand a fifth of a metre; farther
## than this, it was set down somewhere the hand has since left.
const SET_DOWN_STRAY := 0.35
## Every rigid weapon stays in its fighting grip at ease. The standing
## idle opens the fingers, so close them and lower the piece at the wrist.
const LOWERED_DEGREES := 45.0
## Less for a piece long enough to reach the floor that low: its far end is
## kept this far above the floor.
const LOWERED_CLEARANCE := 0.08
## The action whose clip holds the fist a held weapon is closed in.
const FIST_ACTION := &"combat_idle"
const FINGERS: Array[String] = ["thumb", "index", "middle", "ring", "pinky"]

var actor: ReplicatedActor3D
var _hands: Array[Dictionary] = []
var _weight := 0.0
## 1 when every weapon is in its idle grip, 0 when every weapon is in its
## fighting grip. It starts at ease, which is how an actor arrives.
var _idle_weight := 1.0
## Seconds the grip has been wholly at ease (SET_DOWN_AFTER).
var _at_ease_for := 0.0

func refresh_equipment() -> void:
	# A weapon drawn while nothing was held takes the grip of the moment;
	# one kept through an equipment change keeps the blend it was part of,
	# and the place it was set down, and a weapon added beside it joins that
	# blend where it stands.
	var was_empty := _hands.is_empty()
	var kept := {}
	for carry: Dictionary in _hands:
		if carry.has("prop") and is_instance_valid(carry.prop):
			kept[carry.prop] = carry
	_hands.clear()
	var skeleton := get_skeleton()
	for part: int in [0, 1]:
		var visual: int = int(actor._equipment_visuals.get(part, 0))
		# The off-hand weapon bank starts at 160; shields keep their own pose.
		if visual == 0 or (part == 1 and visual < 160):
			continue
		var model := actor._equipment_model_config(part, visual)
		if model.has("rangedAnimationScene") or model.get("attach", "") == "ranged_bow":
			var bow_hand := skeleton.find_bone("hand_l")
			if bow_hand >= 0:
				_hands.append({"hand": bow_hand, "side": "l", "finger_only": true})
			continue
		if model.get("attach", "socket") != "socket":
			continue
		var side := "r" if part == 0 else "l"
		var hand := skeleton.find_bone("hand_" + side)
		if hand < 0:
			continue
		for attachment: Node in actor._equipment_nodes.get(part, []):
			if attachment is BoneAttachment3D and attachment.get_child_count() > 0:
				var prop := attachment.get_child(0) as Node3D
				if prop != null:
					var entry := _hand_entry(skeleton, hand, side, prop)
					var before: Dictionary = kept.get(prop, {})
					for key: String in ["anchor", "end", "toward", "floor", "reach"]:
						if before.has(key):
							entry[key] = before[key]
					_hands.append(entry)
	if was_empty:
		_idle_weight = _idle_target()
	_place_idle_grips()
	update_activity()
	if _hands.is_empty():
		_weight = 0.0

## One held prop: the hand, its fighting grip and the mesh corners used
## to predict floor clearance when lowering the wrist.
func _hand_entry(skeleton: Skeleton3D, hand: int, side: String, prop: Node3D) -> Dictionary:
	var fighting: Transform3D = prop.get_meta(&"fighting_grip", prop.transform)
	var entry := {"hand": hand, "side": side, "prop": prop,
		"grip": fighting.basis.orthonormalized()}
	if prop.has_meta(&"idle_grip"):
		# Held in the fist at ease too, and lowered from the wrist: no second
		# grip to ease into, so the piece is put back in the fist it may have
		# been eased out of before the equipment changed.
		prop.transform = fighting
		entry["lowered"] = true
		entry["fist"] = _crossing(fighting, prop.get_meta(&"idle_grip"))
		var bounds := _bounds(prop)
		var corners: Array[Vector3] = []
		for x: float in [bounds.position.x, bounds.end.x]:
			for y: float in [bounds.position.y, bounds.end.y]:
				for z: float in [bounds.position.z, bounds.end.z]:
					corners.append(fighting * Vector3(x, y, z))
		entry["corners"] = corners

		# Read from the combat idle on the first frame it is needed: the
		# equipment can be attached before the clips are installed.
		entry["side"] = side
		return entry
	return entry

## The fist the combat idle closes the hand on `side` into: each finger bone's
## rotation in that clip, as it stands at its first frame. The clip's finger
## rotations are relative to the hand, so they close any hand the same way.
func _fist(skeleton: Skeleton3D, side: String) -> Array:
	var fist: Array = []
	if actor.resolver == null or actor.animation_player == null:
		return fist
	var clip := actor.resolver.clip_for_action(FIST_ACTION)
	if clip == &"" or not actor.animation_player.has_animation(clip):
		return fist
	var animation := actor.animation_player.get_animation(clip)
	var tracks := {}
	for track: int in animation.get_track_count():
		if animation.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			tracks[str(animation.track_get_path(track).get_concatenated_subnames())] = track
	for finger: String in FINGERS:
		for joint: int in range(1, 4):
			var bone_name := "%s_%02d_%s" % [finger, joint, side]
			var bone := skeleton.find_bone(bone_name)
			if bone >= 0 and tracks.has(bone_name):
				fist.append([bone, animation.rotation_track_interpolate(tracks[bone_name], 0.0)])
	return fist

## The box the piece's meshes fill, in the piece's own space, where its length
## runs along Y.
static func _bounds(prop: Node3D) -> AABB:
	var bounds := AABB()
	var first := true
	for node: Node in prop.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		var to_prop := Transform3D.IDENTITY
		var walk: Node = mesh
		while walk != prop and walk is Node3D:
			to_prop = (walk as Node3D).transform * to_prop
			walk = walk.get_parent()
		var box := to_prop * mesh.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
	return bounds

## Where the lengths of a piece held by two grips come nearest each other,
## which for two grips that both close on the same fist is that fist. Two
## lengths too nearly parallel to cross anywhere useful turn about the first
## grip's origin; the slide along the length still lands the second.
static func _crossing(a: Transform3D, b: Transform3D) -> Vector3:
	var u := a.basis.y.normalized()
	var v := b.basis.y.normalized()
	var apart := a.origin - b.origin
	var cosine := u.dot(v)
	var sine_squared := 1.0 - cosine * cosine
	if sine_squared < 0.0001:
		return a.origin
	var along_a := (cosine * v.dot(apart) - u.dot(apart)) / sine_squared
	var along_b := (v.dot(apart) - cosine * u.dot(apart)) / sine_squared
	return ((a.origin + u * along_a) + (b.origin + v * along_b)) * 0.5

func update_activity() -> void:
	var resumed := not active
	active = not _hands.is_empty() and actor.animation_tier() != AnimationGate.Tier.PAUSED
	# Off screen nothing is blended. An actor whose action changed meanwhile
	# comes back in the grip that action asks for, rather than seen easing
	# its weapon there late, and sets a planted piece down afresh.
	if active and resumed:
		_idle_weight = _idle_target()
		_weight = 1.0 if actor.current_action in TRAVEL_ACTIONS else 0.0
		_at_ease_for = 0.0
		for carry: Dictionary in _hands:
			carry.erase("anchor")
		_place_idle_grips()

func _at_ease() -> bool:
	return actor.resolver != null and actor.resolver.is_at_ease(actor.current_action)

func _idle_target() -> float:
	return 1.0 if _at_ease() else 0.0

## Writes the current idle blend onto every prop that has an idle grip, as it
## stands in the registry. Used where no pose is to hand - an equipment change,
## coming back on screen - and refined by the next frame's pass.
func _place_idle_grips() -> void:
	for carry: Dictionary in _hands:
		if carry.has("idle") and is_instance_valid(carry.prop):
			(carry.prop as Node3D).transform = _blend(carry, carry.idle)

## The piece `idle_weight` of the way from its fighting grip to `rest` (in the
## hand's space), turned about the fist and slid through it. Also keeps the
## grip the wrist correction uses in step, so a weapon caught between the two
## while a walk starts is still aimed straight ahead.
func _blend(carry: Dictionary, rest: Transform3D) -> Transform3D:
	var turned := Basis((carry.fighting as Quaternion).slerp(
		rest.basis.get_rotation_quaternion(), _idle_weight))
	carry.grip = turned
	var pivot: Vector3 = carry.pivot
	var placed := turned.scaled(Vector3.ONE * float(carry.size))
	var held := (carry.fighting_hold as Vector3).lerp(rest.affine_inverse() * pivot, _idle_weight)
	return Transform3D(placed, pivot - placed * held)

static func _eased(value: float, target: float, delta: float, crossfade: float) -> float:
	if crossfade <= 0.0:
		return target
	return move_toward(value, target, maxf(delta, 0.0) / crossfade)

func _process_modification_with_delta(delta: float) -> void:
	var crossfade := actor.action_crossfade_seconds
	var idle_target := _idle_target()
	# At ease, or leaving it: the last step of the way out still has to be
	# written. Once in the fist and staying there, nothing is.
	var easing := _idle_weight > 0.0 or idle_target > 0.0
	_idle_weight = _eased(_idle_weight, idle_target, delta, crossfade)
	_at_ease_for = _at_ease_for + maxf(delta, 0.0) if _idle_weight >= 1.0 and idle_target >= 1.0 else 0.0
	var moving := actor.current_action in TRAVEL_ACTIONS
	_weight = _eased(_weight, 1.0 if moving else 0.0, delta, crossfade)
	var skeleton := get_skeleton()
	if _idle_weight > 0.0:
		_hold_lowered(skeleton)
	if easing:
		_ease(skeleton)
	if _weight <= 0.0:
		return
	var to_skeleton := skeleton.global_basis.orthonormalized().inverse() * actor.global_basis.orthonormalized()
	# A slight lift keeps the point clear of the ground while aiming ahead.
	var point := (to_skeleton * Vector3(0.0, 0.10, -1.0)).normalized()
	for carry: Dictionary in _hands:
		# Rotate only the wrist: its position still follows the same shoulder
		# and elbow motion as the unequipped arm throughout the stride. The
		# turn is the shortest arc from where the stride holds the weapon to
		# straight ahead, which leaves no twist about the weapon's length: the
		# hand rolls as the clip rolls it, in either hand and whichever grip,
		# including one caught part way out of the idle grip as a walk starts.
		if carry.has("finger_only"):
			continue
		var hand := skeleton.get_bone_global_pose(carry.hand).basis.orthonormalized()
		var length := (hand * (carry.grip as Basis) * Vector3.UP).normalized()
		_set_basis(skeleton, carry.hand, Basis(Quaternion(length, point)) * hand, _weight)

## Closes the held hand and aims a rigid piece ahead and slightly outward,
## mirrored on the left. The wrist lowers it by up to 45 degrees, reduced
## when any mesh corner would cross the floor-clearance plane.
func _hold_lowered(skeleton: Skeleton3D) -> void:
	var to_skeleton := skeleton.global_basis.orthonormalized().inverse() * actor.global_basis.orthonormalized()
	var down := (to_skeleton * Vector3.DOWN).normalized()
	var to_actor := actor.global_transform.affine_inverse() * skeleton.global_transform
	for carry: Dictionary in _hands:
		if not carry.has("fingers"):
			var fist := _fist(skeleton, carry.side)
			if not fist.is_empty():
				carry["fingers"] = fist
		for finger: Array in carry.get("fingers", []):
			var bone: int = finger[0]
			skeleton.set_bone_pose_rotation(bone, skeleton.get_bone_pose_rotation(bone).slerp(
				finger[1] as Quaternion, _idle_weight))
		if not carry.has("lowered"):
			continue
		var hand := skeleton.get_bone_global_pose(carry.hand)
		var basis := hand.basis.orthonormalized()
		var length := (basis * (carry.grip as Basis) * Vector3.UP).normalized()
		var outward := 0.10 if carry.side == "r" else -0.10
		var level := (to_skeleton * Vector3(outward, 0.0, -1.0)).normalized()
		var low_angle := 0.0
		var high_angle := deg_to_rad(LOWERED_DEGREES)
		var angle := high_angle
		# Predict the lowest point after the turn about the wrist. A length
		# measured from the hilt misses broad spearheads and mauls.
		for attempt: int in 9:
			var wanted := level * cos(angle) + down * sin(angle)
			var wanted_basis := Basis(Quaternion(length, wanted)) * basis
			var pose := Transform3D(wanted_basis, hand.origin)
			var lowest := INF
			for corner: Vector3 in carry.corners:
				lowest = minf(lowest, (to_actor * (pose * corner)).y)
			if lowest >= LOWERED_CLEARANCE:
				low_angle = angle
				if attempt == 0:
					break
			else:
				high_angle = angle
			angle = (low_angle + high_angle) * 0.5
		var wanted := level * cos(low_angle) + down * sin(low_angle)
		_set_basis(skeleton, carry.hand, Basis(Quaternion(length, wanted)) * basis, _idle_weight)

## Places every weapon with an idle grip for this frame's pose: the arms held
## out first, since that moves the hands the pieces are placed from.
func _ease(skeleton: Skeleton3D) -> void:
	if _idle_weight > 0.0:
		for carry: Dictionary in _hands:
			if carry.has("idle") and float(carry.spread) > 0.0 and carry.upperarm >= 0:
				_spread(skeleton, carry)
	else:
		for carry: Dictionary in _hands:
			carry.erase("anchor")
	var to_actor := actor.global_transform.affine_inverse() * skeleton.global_transform
	for carry: Dictionary in _hands:
		if not carry.has("idle") or not is_instance_valid(carry.prop):
			continue
		var hand := to_actor * skeleton.get_bone_global_pose(carry.hand)
		(carry.prop as Node3D).transform = _blend(carry, _rest(carry, hand))

## Holds the upper arm of a hand with an off-hand weapon out from the body,
## about the line the arm hangs along crossed with the way out, as far as the
## piece asks while it is at ease.
func _spread(skeleton: Skeleton3D, carry: Dictionary) -> void:
	var shoulder := skeleton.get_bone_global_pose(carry.upperarm)
	var hand := skeleton.get_bone_global_pose(carry.hand)
	var out := shoulder.origin - skeleton.get_bone_global_pose(carry.across).origin
	out.y = 0.0
	var axis := (hand.origin - shoulder.origin).cross(out)
	if axis.length_squared() < 1e-10:
		return
	var turn := Basis(axis.normalized(), float(carry.spread) * _idle_weight)
	_set_basis(skeleton, carry.upperarm, turn * shoulder.basis.orthonormalized(), 1.0)

## Where the piece is held at ease this frame, in the hand's space: `hand` is
## the hand bone in the actor's own space, whose floor is y = 0.
func _rest(carry: Dictionary, hand: Transform3D) -> Transform3D:
	var idle: Transform3D = carry.idle
	if carry.style == &"plant" or carry.style == &"lean":
		if not carry.has("anchor"):
			# Set down once the grip has settled, from the registry's grip,
			# and the pose has put its end at the floor; until then it is held
			# as the registry has it.
			if _at_ease_for < SET_DOWN_AFTER or not _at_ease() or not _set_down(carry, hand):
				return idle
		return _stood(carry, hand)
	return _lifted(carry, hand, idle)

## Remembers where the lower end of a planted or leant piece meets the floor,
## in the actor's space, and how far it is from the fist - if the registry's
## grip puts it there in this pose (SET_DOWN_HEIGHT); says whether it did.
func _set_down(carry: Dictionary, hand: Transform3D) -> bool:
	var placed := hand * (carry.idle as Transform3D)
	var ends: Array = carry.ends
	var lower := 0 if (placed * (ends[0] as Vector3)).y <= (placed * (ends[1] as Vector3)).y else 1
	var end: Vector3 = ends[lower]
	var anchor := placed * end
	# The end of the piece's length is not always what touches: a maul rests
	# on the rim of its head, a whip on the curl of its last link, up to a
	# head's width below the line of the haft.
	var lowest := minf(anchor.y, (placed * _floor_point(carry, lower)).y)
	if absf(lowest) > SET_DOWN_HEIGHT:
		return false
	var fist := hand * (carry.pivot as Vector3)
	var reach := fist.distance_to(anchor)
	var height: float = REST_HEIGHTS.get(carry.style, lowest) + anchor.y - lowest
	if anchor.y > height:
		# A haft is let down through the hand to the floor; a blade is held
		# by its hilt, so it is leant over instead until its tip reaches it.
		if carry.style == &"plant":
			anchor.y = height
			reach = fist.distance_to(anchor)
		else:
			anchor = _on_floor(fist, anchor - fist, reach, height)
	carry["end"] = end
	carry["toward"] = ((ends[1 - lower] as Vector3) - end).normalized()
	carry["anchor"] = anchor
	carry["floor"] = anchor.y
	carry["reach"] = reach
	return true

## The point of the piece that touches the floor: the registry's, or the end
## of its length that is lower.
static func _floor_point(carry: Dictionary, lower: int) -> Vector3:
	var point: Vector3 = carry.floor_point
	return (carry.ends as Array)[lower] if point == Vector3.INF else point

## The piece stood on its set-down end and leant through the fist, turned the
## least way from how the registry holds it, and slid along its length as far
## as that takes; beyond the slide it allows, the end is dragged after the fist.
func _stood(carry: Dictionary, hand: Transform3D) -> Transform3D:
	var fist := hand * (carry.pivot as Vector3)
	var anchor: Vector3 = carry.anchor
	var reach := fist.distance_to(anchor)
	var slide := (PLANT_SLIDE if carry.style == &"plant" else LEAN_SLIDE) * float(carry.size)
	if absf(reach - float(carry.reach)) > slide:
		anchor = _dragged(carry, fist, anchor, clampf(reach,
			float(carry.reach) - slide, float(carry.reach) + slide))
		carry.anchor = anchor
	var placed := hand * (carry.idle as Transform3D)
	var held := placed * (carry.end as Vector3)
	if Vector2(held.x - anchor.x, held.z - anchor.z).length() > SET_DOWN_STRAY * float(carry.size):
		carry.erase("anchor")
		return carry.idle
	var length := (placed.basis * (carry.toward as Vector3)).normalized()
	var wanted := (fist - anchor).normalized()
	var basis := Basis(Quaternion(length, wanted)) * placed.basis
	return hand.affine_inverse() * Transform3D(basis, anchor - basis * (carry.end as Vector3))

## Where the set-down end goes when the fist has moved farther than the piece
## can slide: along the length to `reach` from the fist, but never under the
## floor it was set down on - there it skids out across the floor instead.
static func _dragged(carry: Dictionary, fist: Vector3, anchor: Vector3, reach: float) -> Vector3:
	var along := (anchor - fist).normalized()
	var moved := fist + along * reach
	if moved.y >= float(carry.floor):
		return moved
	return _on_floor(fist, along, reach, carry.floor)

## The point `height` above the floor and `reach` from the fist, out from under
## it the way `toward` leans.
static func _on_floor(fist: Vector3, toward: Vector3, reach: float, height: float) -> Vector3:
	var drop := fist.y - height
	var flat := Vector3(toward.x, 0.0, toward.z)
	if flat.length_squared() < 1e-8:
		flat = Vector3.FORWARD
	return Vector3(fist.x, height, fist.z) + flat.normalized() * sqrt(maxf(reach * reach - drop * drop, 0.0))

## The idle grip, tilted up about the fist by as little as keeps the piece off
## the floor: the registry's grip clears it through the idle, but a reel drops
## the hand lower than the idle ever does. Measured by the point the grip
## brings nearest the floor, which keeps it nearest through the small turns
## an emote gives the hand; a box round the piece would not do, as the corners
## of a crescent's hang well below its tip and tipped it up and down through
## an idle in which nothing came near the floor.
func _lifted(carry: Dictionary, hand: Transform3D, idle: Transform3D) -> Transform3D:
	var placed := hand * idle
	var ends: Array = carry.ends
	var lower := 0 if (placed * (ends[0] as Vector3)).y <= (placed * (ends[1] as Vector3)).y else 1
	var low := placed * _floor_point(carry, lower)
	if low.y >= GUARD_HEIGHT:
		return idle
	var fist := hand * (carry.pivot as Vector3)
	var reach := low - fist
	var lean := Vector3(reach.x, 0.0, reach.z)
	if lean.length_squared() < 1e-8:
		lean = Vector3.FORWARD
	# Turning about this lifts the low point the way it already leans: the
	# height of a point turned about a level axis through the fist runs
	# fist.y + a cos(turn) + b sin(turn), and the least turn that brings it to
	# GUARD_HEIGHT is solved for directly.
	var axis := lean.normalized().cross(Vector3.UP).normalized()
	var across := reach - axis * axis.dot(reach)
	var a := across.y
	var b := axis.cross(across).y
	var length := sqrt(a * a + b * b)
	if length < 1e-6:
		return idle
	var start := atan2(b, a)
	var swing := acos(clampf((GUARD_HEIGHT - fist.y) / length, -1.0, 1.0))
	var turn := minf(fposmod(start - swing, TAU), fposmod(start + swing, TAU))
	var tilt := Basis(axis, turn)
	return hand.affine_inverse() * (Transform3D(tilt, fist - tilt * fist) * placed)

func _set_basis(skeleton: Skeleton3D, bone: int, basis: Basis, weight: float) -> void:
	var parent := skeleton.get_bone_global_pose(skeleton.get_bone_parent(bone)).basis.orthonormalized()
	var target := (parent.inverse() * basis).get_rotation_quaternion()
	skeleton.set_bone_pose_rotation(bone,
		skeleton.get_bone_pose_rotation(bone).slerp(target, weight))

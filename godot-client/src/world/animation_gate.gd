class_name AnimationGate
extends RefCounted
## Decides how often each animated body in a camera's world is stepped.
##
## An AnimationPlayer costs the same whether or not its body is on screen: the
## mixer blends every track, the skeleton recomputes every bone, and the
## Compatibility renderer re-skins every mesh instance hanging off it, once a
## frame each. Measured on develop that was about five milliseconds a frame for
## sixty idle race actors and three for the Sunmane herd, most of which the
## camera was not looking at. Nothing the player can see changes here: a body
## inside the frustum and near the camera animates as before; one far from the
## camera is advanced every other frame by the time both frames covered, so it
## plays at the same speed with half the updates; one outside the frustum is
## paused where it stands until it comes back.
##
## The gate owns no nodes. A caller captures a camera with `begin`, asks
## `classify` for each body, hands the answer to `apply`, and calls `advance`
## once a frame so the half-rate players are stepped.
##
## A crowd's half-rate bodies take turns: each joins one of two groups, and
## the groups are stepped on alternate frames. Stepped all on the same frame,
## as they once were, they made every other frame carry every half-rate body's
## pose, skeleton update and skinning, and the frame time see-sawed by that
## much. In a crowd the caller may also put the bodies farthest down its
## ranking in QUARTER, stepped every fourth frame in four groups the same way.

enum Tier { FULL, HALF, PAUSED, QUARTER }

## Beyond this distance from the camera a body is stepped every other frame.
## At the isometric rig's default zoom the far edge of the view is about fifty
## metres out; zoomed right out most of the screen is past this.
const HALF_RATE_METRES := 45.0

## How many frames apart a body in each stepped tier is stepped.
const STRIDES := {Tier.HALF: 2, Tier.QUARTER: 4}

var _planes: Array[Plane] = []
var _camera_position := Vector3.ZERO
## Whether a body's skeleton follows its tier too: modifiers stepped with a
## half-rate player, and a paused body's model subtree disabled. Main turns it
## off with the rest of the crowd presentation's gate (crowd_presentation.gd).
var gate_skeletons := true
## Whether the stepped bodies of a tier are spread over its frames; off, every
## half-rate body is stepped on the same frame, as before (crowd_presentation.gd
## `stagger`).
var stagger := true
## The tier a clip that does not loop is played out in on a body the gate
## would pause (ReplicatedActor3D.set_animation_tier).
var one_shot_tier := Tier.HALF
## The stepped players in phase groups: each group holds its tier's `stride`,
## its `phase`, the time it has not yet been stepped by (`delta`) and its
## `members`, every player with the skeleton whose modifiers (cape cloth,
## weapon carry) are stepped with it, or null.
var _groups: Array[Dictionary] = []
## Which group each stepped player is in.
var _group_of: Dictionary = {}
var _tick := 0

func _init() -> void:
	for tier: Tier in [Tier.HALF, Tier.QUARTER]:
		var stride: int = STRIDES[tier]
		for phase: int in stride:
			_groups.append({"tier": tier, "stride": stride, "phase": phase,
				"delta": 0.0, "members": {}})

## Captures `camera` for a round of `classify` calls. With no camera every
## body is FULL, so a scene without one - a headless test, a fixture with its
## own rig - is left exactly as it was.
func begin(camera: Camera3D) -> void:
	_planes.clear()
	_camera_position = Vector3.ZERO
	if camera == null or not camera.is_inside_tree():
		return
	_planes = camera.get_frustum()
	_camera_position = camera.global_position

## The tier for a body whose bounding sphere is `radius` around `anchor`. The
## frustum planes face outward, so a sphere wholly past any of them is out of
## view.
func classify(anchor: Vector3, radius: float) -> Tier:
	if _planes.is_empty():
		return Tier.FULL
	for plane: Plane in _planes:
		if plane.distance_to(anchor) > radius:
			return Tier.PAUSED
	if anchor.distance_to(_camera_position) > HALF_RATE_METRES:
		return Tier.HALF
	return Tier.FULL

## Puts `player` in `tier`. Safe to repeat with the tier it is already in.
## FULL hands the player back to the engine's idle processing, which is what an
## AnimationPlayer runs on by default; HALF and QUARTER take it manual and step
## it from `advance`; PAUSED stops it, and a later FULL resumes it where it
## stopped.
##
## Given the body's `skeleton`, its modifiers follow the same clock: stepped
## with the player at half or quarter rate, on the engine's idle clock
## otherwise. A half-rate body otherwise still solved its cape cloth and
## re-posed its skeleton every frame for a pose that changed every other one.
func apply(player: AnimationPlayer, tier: Tier, skeleton: Skeleton3D = null) -> void:
	if player == null:
		return
	match tier:
		Tier.FULL:
			_leave(player)
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
			player.active = true
		Tier.HALF, Tier.QUARTER:
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
			player.active = true
			_join(player, tier, skeleton)
		Tier.PAUSED:
			_leave(player)
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
			player.active = false
	if skeleton != null and gate_skeletons:
		skeleton.modifier_callback_mode_process = (
			Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL if STRIDES.has(tier)
			else Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_IDLE)

## Puts a stepped player in the emptiest group of its tier, or keeps it in the
## one it is in. Without `stagger` every player of a tier is in its first group.
func _join(player: AnimationPlayer, tier: Tier, skeleton: Skeleton3D) -> void:
	var current: int = int(_group_of.get(player, -1))
	if current >= 0 and _groups[current]["tier"] == tier:
		(_groups[current]["members"] as Dictionary)[player] = skeleton
		return
	_leave(player)
	var chosen := -1
	for index: int in _groups.size():
		var group: Dictionary = _groups[index]
		if group["tier"] != tier:
			continue
		if chosen < 0 or (stagger and (group["members"] as Dictionary).size()
				< (_groups[chosen]["members"] as Dictionary).size()):
			chosen = index
	(_groups[chosen]["members"] as Dictionary)[player] = skeleton
	_group_of[player] = chosen

func _leave(player: Object) -> void:
	var current: int = int(_group_of.get(player, -1))
	if current < 0:
		return
	(_groups[current]["members"] as Dictionary).erase(player)
	_group_of.erase(player)

## Steps the stepped players. Call once per frame with that frame's delta: a
## group is advanced on its turn, every `stride` calls, by the time all of
## those frames covered.
func advance(delta: float) -> void:
	_tick += 1
	for group: Dictionary in _groups:
		group["delta"] = float(group["delta"]) + delta
		if (_tick + int(group["phase"])) % int(group["stride"]) != 0:
			continue
		var step: float = group["delta"]
		group["delta"] = 0.0
		var members: Dictionary = group["members"]
		if members.is_empty():
			continue
		var gone: Array = []
		for value: Variant in members:
			if not is_instance_valid(value):
				gone.append(value)
				continue
			var player: AnimationPlayer = value as AnimationPlayer
			if player.active and player.is_inside_tree():
				player.advance(step)
				var skeleton: Variant = members[value]
				if is_instance_valid(skeleton) and (skeleton as Skeleton3D).is_inside_tree():
					(skeleton as Skeleton3D).advance(step)
		for value: Variant in gone:
			members.erase(value)
			_group_of.erase(value)

## Forgets every player. Live callers restore idle callbacks by default.
## Full-world discard leaves callback modes untouched: these nodes are about to
## be freed, so resetting the gate must not reactivate their queued work. Work
## already queued before this call is not canceled by forgetting membership.
func reset(restore_idle: bool = true) -> void:
	for group: Dictionary in _groups:
		var members: Dictionary = group["members"]
		if restore_idle:
			for value: Variant in members:
				if is_instance_valid(value):
					(value as AnimationPlayer).callback_mode_process = (
						AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE)
				var skeleton: Variant = members[value]
				if is_instance_valid(skeleton):
					(skeleton as Skeleton3D).modifier_callback_mode_process = (
						Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_IDLE)
		members.clear()
		group["delta"] = 0.0
	_group_of.clear()
	_tick = 0
	_planes.clear()

func half_rate_count() -> int:
	return _tier_count(Tier.HALF)

func quarter_rate_count() -> int:
	return _tier_count(Tier.QUARTER)

## How many players each group of `tier` holds, in phase order.
func group_sizes(tier: Tier) -> Array[int]:
	var sizes: Array[int] = []
	for group: Dictionary in _groups:
		if group["tier"] == tier:
			sizes.append((group["members"] as Dictionary).size())
	return sizes

func _tier_count(tier: Tier) -> int:
	var count := 0
	for size: int in group_sizes(tier):
		count += size
	return count

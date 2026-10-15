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

enum Tier { FULL, HALF, PAUSED }

## Beyond this distance from the camera a body is stepped every other frame.
## At the isometric rig's default zoom the far edge of the view is about fifty
## metres out; zoomed right out most of the screen is past this.
const HALF_RATE_METRES := 45.0

var _planes: Array[Plane] = []
var _camera_position := Vector3.ZERO
## The players in the half-rate tier, as a set.
var _half: Dictionary = {}
var _half_delta := 0.0
var _half_turn := false

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
## AnimationPlayer runs on by default; HALF takes it manual and steps it from
## `advance`; PAUSED stops it, and a later FULL resumes it where it stopped.
func apply(player: AnimationPlayer, tier: Tier) -> void:
	if player == null:
		return
	match tier:
		Tier.FULL:
			_half.erase(player)
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
			player.active = true
		Tier.HALF:
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
			player.active = true
			_half[player] = true
		Tier.PAUSED:
			_half.erase(player)
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
			player.active = false

## Steps the half-rate players. Call once per frame with that frame's delta:
## every second call advances them by the time both frames covered.
func advance(delta: float) -> void:
	_half_delta += delta
	_half_turn = not _half_turn
	if _half_turn:
		return
	var step: float = _half_delta
	_half_delta = 0.0
	if _half.is_empty():
		return
	var gone: Array = []
	for value: Variant in _half:
		if not is_instance_valid(value):
			gone.append(value)
			continue
		var player: AnimationPlayer = value as AnimationPlayer
		if player.active and player.is_inside_tree():
			player.advance(step)
	for value: Variant in gone:
		_half.erase(value)

## Forgets every player, handing the half-rate ones back to idle processing.
func reset() -> void:
	for value: Variant in _half:
		if is_instance_valid(value):
			(value as AnimationPlayer).callback_mode_process = (
				AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE)
	_half.clear()
	_half_delta = 0.0
	_half_turn = false
	_planes.clear()

func half_rate_count() -> int:
	return _half.size()

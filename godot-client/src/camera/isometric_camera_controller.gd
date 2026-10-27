class_name IsometricCameraController
extends Node3D

@export_range(-80.0, -15.0) var pitch_degrees := -60.0
@export var yaw_degrees := 0.0
@export_range(3.0, 100.0) var distance := 26.0
@export var zoom_step := 2.5
@export var rotation_sensitivity := 0.25
const KEYBOARD_SPEED_MIN := 15.0
const KEYBOARD_SPEED_MAX := 180.0
const KEYBOARD_SPEED_DEFAULT := 90.0
## Degrees per second for both keyboard orbit axes, independent of mouse sensitivity.
@export var keyboard_speed := KEYBOARD_SPEED_DEFAULT:
	set(value):
		keyboard_speed = clampf(value, KEYBOARD_SPEED_MIN, KEYBOARD_SPEED_MAX) \
			if is_finite(value) else KEYBOARD_SPEED_DEFAULT
# The camera's near plane follows the zoom: a quarter of the orbit distance,
# never wider than the 1 m the scene is authored for, never narrower than
# 0.2 m. The width matters because the client renders through GL
# Compatibility, whose depth buffer is fixed-point: the resolvable depth step
# at distance z is about z^2 / (near * 2^24) metres, so at the engine default
# near of 0.05 every authored 5 mm clearance in the map kits shimmers from
# 100 m away. At 1 m the step is 0.6 mm; even at this floor of 0.2 m it is
# 3 mm, still inside those clearances - and the plane is only ever that
# narrow while the camera sits closer than a metre from its focus, when the
# frame is a portrait and the far vista is mostly out of it.
const NEAR_PLANE_RATIO := 0.25
const NEAR_PLANE_MAX := 1.0
const NEAR_PLANE_MIN := 0.2
# The floor keeps the focused actor outside the (shrinking) near plane: at
# 1.5 m the plane sits 0.375 m out and the actor's surface no closer than
# about a metre. Interiors keep their own tighter limits through their
# manifests' camera blocks, which override these.
@export var min_distance := 1.5
@export var max_distance := 90.0

@onready var camera: Camera3D = %Camera

var focus := Vector3.ZERO
## World-space framing retained when a cinematic hands its view to normal play.
var follow_offset := Vector3.ZERO
var _last_follow_position := Vector3.ZERO
var _follow_arrival := Vector3.INF
var _follow_arrival_until := 0.0
const FOLLOW_ARRIVAL_SECONDS := 6.0
var _rotating := false

func _ready() -> void:
	_update_camera()

func set_focus(value: Vector3) -> void:
	_last_follow_position = value
	if _follow_arrival.is_finite():
		if value.distance_to(_follow_arrival) <= 0.25:
			_follow_arrival = Vector3.INF
		elif Time.get_ticks_msec() / 1000.0 < _follow_arrival_until:
			# The acknowledged native run may still be reaching the staged combat
			# post. Keep its intended framing while orbit and zoom remain usable.
			_update_camera()
			return
		else:
			# A blocked or interrupted run must not cause a delayed camera jump.
			follow_offset = focus - value
			_follow_arrival = Vector3.INF
	focus = value + follow_offset
	_update_camera()

## Adopt an authored look-at view as an ordinary, controllable orbit camera.
## arrival is a visual destination only; this never moves the followed actor.
func adopt_world_view(view: Dictionary, followed_position: Vector3,
		arrival := Vector3.INF) -> bool:
	var pose: Transform3D = view.get("transform", Transform3D.IDENTITY)
	var target: Vector3 = view.get("target", Vector3.INF)
	if not is_instance_valid(camera) or not pose.is_finite() or not target.is_finite() \
			or not followed_position.is_finite(): return false
	var orbit_focus := target - Vector3.UP * 1.2
	var offset := global_basis.inverse() * (pose.origin - orbit_focus)
	var next_distance := offset.length()
	if next_distance < min_distance or next_distance > max_distance: return false
	var next_pitch := -rad_to_deg(asin(clampf(offset.y / next_distance, -1.0, 1.0)))
	if next_pitch < -80.0 or next_pitch > -15.0: return false
	var reference: Vector3 = arrival if arrival.is_finite() else followed_position
	focus = orbit_focus
	follow_offset = orbit_focus - reference
	_last_follow_position = followed_position
	_follow_arrival = reference if reference.distance_to(followed_position) > 0.25 else Vector3.INF
	_follow_arrival_until = Time.get_ticks_msec() / 1000.0 + FOLLOW_ARRIVAL_SECONDS
	distance = next_distance
	pitch_degrees = next_pitch
	yaw_degrees = rad_to_deg(atan2(offset.x, offset.z))
	_rotating = false
	_update_camera()
	camera.fov = float(view.get("fov", camera.fov))
	camera.near = float(view.get("near", camera.near))
	camera.far = float(view.get("far", camera.far))
	return true

func capture_follow_state() -> Dictionary:
	return {"offset":follow_offset, "last_position":_last_follow_position,
		"arrival":_follow_arrival, "remaining":maxf(0.0,
			_follow_arrival_until - Time.get_ticks_msec() / 1000.0)}

func restore_follow_state(state: Dictionary) -> void:
	follow_offset = state.get("offset", Vector3.ZERO)
	_last_follow_position = state.get("last_position", focus - follow_offset)
	_follow_arrival = state.get("arrival", Vector3.INF)
	_follow_arrival_until = Time.get_ticks_msec() / 1000.0 + float(state.get("remaining", 0.0))

## Explicit reset/session boundaries return the pivot to the followed actor.
func reset_follow_offset() -> void:
	focus -= follow_offset
	if _follow_arrival.is_finite(): focus = _last_follow_position
	follow_offset = Vector3.ZERO
	_follow_arrival = Vector3.INF
	_update_camera()

func rebase_world(frame: Transform3D) -> void:
	focus = frame * focus
	_last_follow_position = frame * _last_follow_position
	follow_offset = frame.basis * follow_offset
	if _follow_arrival.is_finite(): _follow_arrival = frame * _follow_arrival
	yaw_degrees += rad_to_deg(frame.basis.get_euler().y)
	_update_camera()

func handle_mouse_button(event: InputEventMouseButton) -> bool:
	if event.button_index == MOUSE_BUTTON_MIDDLE:
		_rotating = event.pressed
		return true
	if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP:
		distance = clampf(distance - zoom_step, min_distance, max_distance)
		_update_camera()
		return true
	if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		distance = clampf(distance + zoom_step, min_distance, max_distance)
		_update_camera()
		return true
	return false

func handle_mouse_motion(event: InputEventMouseMotion) -> bool:
	if _rotating:
		yaw_degrees -= event.relative.x * rotation_sensitivity
		pitch_degrees = clampf(pitch_degrees - event.relative.y * rotation_sensitivity, -80.0, -15.0)
		_update_camera()
		return true
	return false

func cancel_rotation() -> void:
	_rotating = false

## Left/right orbit the player; up/down raise/lower the viewing angle.
func handle_keyboard(axes: Vector2, delta: float) -> void:
	if axes == Vector2.ZERO:
		return
	yaw_degrees -= axes.x * keyboard_speed * delta
	pitch_degrees = clampf(pitch_degrees - axes.y * keyboard_speed * delta, -80.0, -15.0)
	_update_camera()

func screen_to_ground(screen_position: Vector2, ground_height: float) -> Variant:
	var origin := camera.project_ray_origin(screen_position)
	var direction := camera.project_ray_normal(screen_position)
	if absf(direction.y) < 0.0001:
		return null
	var distance_to_plane := (ground_height - origin.y) / direction.y
	if distance_to_plane < 0.0:
		return null
	return origin + direction * distance_to_plane

func ray_origin(screen_position: Vector2) -> Vector3:
	return camera.project_ray_origin(screen_position)

func ray_direction(screen_position: Vector2) -> Vector3:
	return camera.project_ray_normal(screen_position)

func camera_diagnostics() -> Dictionary:
	return {
		"focus": focus,
		"follow_offset": follow_offset,
		"rig_transform": global_transform,
		"camera_transform": camera.global_transform if is_instance_valid(camera) else Transform3D.IDENTITY,
		"yaw_degrees": yaw_degrees,
		"pitch_degrees": pitch_degrees,
		"distance": distance,
	}

func _update_camera() -> void:
	if not is_instance_valid(camera):
		return
	var yaw := deg_to_rad(yaw_degrees)
	var pitch := deg_to_rad(pitch_degrees)
	var offset := Vector3(
		sin(yaw) * cos(pitch),
		-sin(pitch),
		cos(yaw) * cos(pitch)) * distance
	global_position = focus
	camera.position = offset
	camera.near = clampf(distance * NEAR_PLANE_RATIO,
		NEAR_PLANE_MIN, NEAR_PLANE_MAX)
	camera.look_at(global_position + Vector3.UP * 1.2, Vector3.UP)

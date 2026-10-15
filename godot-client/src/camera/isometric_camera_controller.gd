class_name IsometricCameraController
extends Node3D

@export_range(-80.0, -15.0) var pitch_degrees := -60.0
@export var yaw_degrees := 0.0
@export_range(3.0, 100.0) var distance := 26.0
@export var zoom_step := 2.5
@export var rotation_sensitivity := 0.25
@export var pan_sensitivity := 0.012
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
var pan_offset := Vector3.ZERO
var _rotating := false
var _panning := false

func _ready() -> void:
	_update_camera()

func set_focus(value: Vector3) -> void:
	focus = value
	_update_camera()

func rebase_world(frame: Transform3D) -> void:
	focus = frame * focus
	pan_offset = frame.basis * pan_offset
	yaw_degrees += rad_to_deg(frame.basis.get_euler().y)
	_update_camera()

func handle_mouse_button(event: InputEventMouseButton) -> bool:
	if event.button_index == MOUSE_BUTTON_RIGHT:
		_rotating = event.pressed
		return true
	if event.button_index == MOUSE_BUTTON_MIDDLE:
		_panning = event.pressed
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
	if _panning:
		var right := camera.global_basis.x
		var forward := -camera.global_basis.z
		right.y = 0.0
		forward.y = 0.0
		pan_offset += (-right.normalized() * event.relative.x
			+ forward.normalized() * event.relative.y) * distance * pan_sensitivity
		_update_camera()
		return true
	return false

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
		"pan_offset": pan_offset,
		"rig_transform": global_transform,
		"camera_transform": camera.global_transform if is_instance_valid(camera) else Transform3D.IDENTITY,
		"yaw_degrees": yaw_degrees,
		"pitch_degrees": pitch_degrees,
		"distance": distance,
	}

func reset_pan() -> void:
	pan_offset = Vector3.ZERO
	_update_camera()

func _update_camera() -> void:
	if not is_instance_valid(camera):
		return
	var yaw := deg_to_rad(yaw_degrees)
	var pitch := deg_to_rad(pitch_degrees)
	var offset := Vector3(
		sin(yaw) * cos(pitch),
		-sin(pitch),
		cos(yaw) * cos(pitch)) * distance
	global_position = focus + pan_offset
	camera.position = offset
	camera.near = clampf(distance * NEAR_PLANE_RATIO,
		NEAR_PLANE_MIN, NEAR_PLANE_MAX)
	camera.look_at(global_position + Vector3.UP * 1.2, Vector3.UP)

extends RangerBow3D
## Test-only candidate: local bowstring topology and limb flex are retained when
## the exact local draw point/flex are unchanged. World pose, smoothing, recoil,
## and arrow state still update on every pose callback.

var candidate_geometry_rebuilds := 0
var _candidate_valid := false
var _candidate_draw_point := Vector3.ZERO
var _candidate_flex := 0.0
var _candidate_upper: Array[Node3D] = []
var _candidate_lower: Array[Node3D] = []


func set_asset(path: String) -> void:
	var previous: String = _path
	super.set_asset(path)
	if _path == previous and _candidate_valid:
		return
	_candidate_upper.clear()
	_candidate_lower.clear()
	if bow != null:
		for limb: Node in bow.get_children():
			if not limb is Node3D:
				continue
			if String(limb.name).begins_with("Upper"):
				_candidate_upper.append(limb as Node3D)
			elif String(limb.name).begins_with("Lower"):
				_candidate_lower.append(limb as Node3D)
	_candidate_valid = false


func pose(grip: Vector3, draw_hand: Vector3, up: Vector3, forward: Vector3,
		is_drawing: bool, release_time: float, size: float,
		arrow_size := 1.0) -> void:
	global_position = grip
	var back := (draw_hand - grip).normalized() if is_drawing else -forward.normalized()
	if is_drawing:
		_aim_back = back
	elif release_time >= 0.0 and _aim_back.length_squared() > 0.01:
		back = _aim_back
	if absf(back.dot(up)) > 0.95:
		back = -forward.normalized()
	var right := up.cross(back).normalized()
	var pose_basis := Basis(right, back.cross(right).normalized(), back)
	if not is_drawing and release_time < 0.0 and is_inside_tree():
		pose_basis = global_basis.orthonormalized().slerp(pose_basis, 0.2)
	global_basis = pose_basis.scaled(Vector3.ONE * size)
	var draw_point := to_local(draw_hand) if is_drawing else Vector3(0, 0, _tip_z)
	draw_point.x = 0.0
	if release_time >= 0.0:
		draw_point.z += sin(release_time * 95.0) * exp(-release_time * 24.0) * 0.055
	var flex := clampf((draw_point.z-_tip_z)*0.18, -0.025, 0.11)
	if not _candidate_valid or draw_point != _candidate_draw_point \
			or flex != _candidate_flex:
		for limb: Node3D in _candidate_upper:
			limb.rotation.x = flex
		for limb: Node3D in _candidate_lower:
			limb.rotation.x = -flex
		var upper_tip := Basis(Vector3.RIGHT, flex) * Vector3(0, _tip_y, _tip_z)
		var lower_tip := Basis(Vector3.RIGHT, -flex) * Vector3(0, -_tip_y, _tip_z)
		_string.clear_surfaces()
		_string.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _string_material)
		CombatEffectMesh.line(_string, upper_tip, draw_point,
			0.0035, Color(0.82, 0.77, 0.58), Vector3.RIGHT)
		CombatEffectMesh.line(_string, draw_point, lower_tip,
			0.0035, Color(0.82, 0.77, 0.58), Vector3.RIGHT)
		_string.surface_end()
		_candidate_draw_point = draw_point
		_candidate_flex = flex
		_candidate_valid = true
		candidate_geometry_rebuilds += 1
	if arrow != null:
		arrow.scale = Vector3.ONE * arrow_size / maxf(size, 0.01)
		arrow.visible = is_drawing
		arrow.position = draw_point
		arrow.rotation = Vector3.ZERO

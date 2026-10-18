extends Node3D
## Live leather straps between the existing bridle and posed finger grips.
## Like the live bowstring, this attachment does not replace a source model.
var surface := ImmediateMesh.new()
var settings: Dictionary
var last_points: Dictionary = {}
var last_lengths: Dictionary = {}
var last_grip_points: Dictionary = {}
var straps: MeshInstance3D

func configure(profile: Dictionary) -> void:
	settings = profile
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(str(settings.colour))
	material.roughness = .85
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	straps = MeshInstance3D.new()
	straps.name = "LiveReins"
	straps.mesh = surface
	straps.material_override = material
	add_child(straps)

func grip_world(rig: Skeleton3D, side: String) -> Vector3:
	# The line passes through the curled fingers rather than ending at the
	# wrist socket. These bones belong to the unchanged canonical player rig.
	var middle := rig.get_bone_global_pose(rig.find_bone("middle_02_" + side)).origin
	var ring := rig.get_bone_global_pose(rig.find_bone("ring_02_" + side)).origin
	return rig.to_global((middle + ring) * .5)

func grip_exit_world(rig: Skeleton3D, side: String) -> Vector3:
	var index := rig.get_bone_global_pose(rig.find_bone("index_02_" + side)).origin
	var thumb := rig.get_bone_global_pose(rig.find_bone("thumb_02_" + side)).origin
	return rig.to_global((index + thumb) * .5)

func update_contact(anchors: Dictionary, rig: Skeleton3D, seat_basis: Basis, grips: Dictionary = {}, bridle_paths: Array[PackedVector3Array] = []) -> void:
	visible = true
	last_points.clear()
	last_lengths.clear()
	last_grip_points.clear()
	surface.clear_surfaces()
	surface.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for side: String in ["l", "r"]:
		var start: Vector3 = anchors[side]
		var finish := grip_world(rig, side)
		if grips.has(side):
			finish = grips[side][0]
		var sign_value := 1.0 if side == "l" else -1.0
		var points := PackedVector3Array()
		var length := 0.0
		var count := int(settings.segments)
		for index: int in range(count + 1):
			var u := float(index) / count
			var slack := sin(PI * u)
			var point := start.lerp(finish, u)
			# Run outside either side of the mane, with a little hanging slack.
			point += seat_basis.x * sign_value * float(settings.sideClearanceMetres) * slack
			point += Vector3.DOWN * float(settings.sagMetres) * slack
			if index > 0:
				length += point.distance_to(to_global(points[index - 1]))
			points.append(to_local(point))
		_strip(points)
		# The incoming strap enters between the curled fingers, crosses the
		# palm and emerges beside the thumb. A short hanging end makes the
		# actual hold readable from the game camera as well as the side.
		var exit := grip_exit_world(rig, side)
		if grips.has(side):
			exit = grips[side][1]
		var tail := exit + Vector3.DOWN * float(settings.looseEndLengthMetres)
		tail += seat_basis.x * sign_value * float(settings.looseEndSpreadMetres) - seat_basis.z * .025
		var grip_points := PackedVector3Array([to_local(finish), to_local(exit)])
		for index: int in range(1, 9):
			var u := float(index) / 8.0
			var point := exit.lerp(tail, u)
			point += seat_basis.x * sign_value * .015 * sin(PI * u)
			grip_points.append(to_local(point))
		_strip(grip_points)
		last_points[side] = points
		last_lengths[side] = length
		last_grip_points[side] = grip_points
	for path: PackedVector3Array in bridle_paths:
		var points := PackedVector3Array()
		for point: Vector3 in path:
			points.append(to_local(point))
		_strip(points)
	surface.surface_end()

func _strip(points: PackedVector3Array) -> void:
	for index: int in range(points.size() - 1):
		var direction := (points[index + 1] - points[index]).normalized()
		var up := global_basis.inverse() * Vector3.UP
		var across := (up - direction * up.dot(direction)).normalized()
		across = across.rotated(direction, deg_to_rad(float(settings.crossSectionRollDegrees)))
		var wide := across * float(settings.widthMetres) * .5
		var thin := direction.cross(across) * float(settings.thicknessMetres) * .5
		var a := [points[index] + wide + thin, points[index] - wide + thin, points[index] - wide - thin, points[index] + wide - thin]
		var b := [points[index + 1] + wide + thin, points[index + 1] - wide + thin, points[index + 1] - wide - thin, points[index + 1] + wide - thin]
		for face: int in range(4):
			var next := (face + 1) % 4
			_triangle(a[face], a[next], b[next])
			_triangle(a[face], b[next], b[face])

func _triangle(a: Vector3, b: Vector3, c: Vector3) -> void:
	var normal := (b - a).cross(c - a).normalized()
	for point: Vector3 in [a, b, c]:
		surface.surface_set_normal(normal)
		surface.surface_add_vertex(point)

extends RefCounted
## Cloth contact above the approved pony's animated back and rear saddle.
## Native-space envelopes follow their owning bones; no mesh is rewritten.
var rig: Skeleton3D
var envelopes: Array[Dictionary] = []
var back := Vector3.BACK
var side := Vector3.RIGHT
var clearance := .04
var gallop_blend := 0.0
var moving_blend := 0.0
var flow_time := 0.0

func configure(skeleton: Skeleton3D, contact: Array = []) -> void:
	rig = skeleton
	# Bounds fitted to v8's existing body: native rump top 1.38–1.42 m,
	# half-width 0.34 m. The larger envelope also clears interpolated cloth.
	var specs: Array = [
		["hips", Vector3(0.0, 1.02, -.29), Vector3(.41, .50, .90)],
		["Bone_021", Vector3(0.0, 1.30, .12), Vector3(.31, .22, .29)]]
	if not contact.is_empty():
		specs = []
		for entry: Dictionary in contact:
			var center: Array = entry.center
			var radii: Array = entry.radii
			specs.append([entry.bone, Vector3(center[0], center[1], center[2]), Vector3(radii[0], radii[1], radii[2])])
	for spec: Array in specs:
		var bone := rig.find_bone(str(spec[0]))
		if bone >= 0:
			envelopes.append({"bone": bone, "rump": str(spec[0]) == "hips",
				"rest_inverse": rig.get_bone_global_rest(bone).affine_inverse(),
				"center": spec[1], "radii": spec[2], "frame": Transform3D.IDENTITY,
				"inverse": Transform3D.IDENTITY, "rest_height": (spec[2] as Vector3).y})
	update()

func update(delta := 0.0, gait := "idle") -> void:
	# Blend contact height and hang instead of resetting the cloth when the
	# pace changes. The higher, trailing silhouette is reserved for gallop.
	gallop_blend = move_toward(gallop_blend, 1.0 if gait == "gallop" else 0.0, maxf(delta, 0.0) / .4)
	moving_blend = move_toward(moving_blend, 1.0 if gait in ["trot", "gallop"] else 0.0, maxf(delta, 0.0) / .4)
	clearance = lerpf(.04, .08, gallop_blend)
	flow_time += maxf(delta, 0.0)
	for envelope: Dictionary in envelopes:
		if bool(envelope.rump):
			var radii: Vector3 = envelope.radii
			radii.y = float(envelope.rest_height) - .02 * (1.0 - gallop_blend)
			envelope.radii = radii
		var frame := rig.global_transform * rig.get_bone_global_pose(int(envelope.bone)) * (envelope.rest_inverse as Transform3D)
		envelope.frame = frame
		envelope.inverse = frame.affine_inverse()
	back = -(rig.global_basis * Vector3.BACK).normalized()
	side = (rig.global_basis * Vector3.RIGHT).normalized()

func seed(rest: PackedVector3Array, lengths: PackedFloat32Array) -> PackedVector3Array:
	# Start behind the rider, on the upper side of the contact surface. A
	# vertical initial hang starts inside the pony and can settle underneath it.
	var points := rest.duplicate()
	var down := (rest[1] - rest[0]).normalized()
	var angle := deg_to_rad(35.0)
	var direction := (down * cos(angle) + back * sin(angle)).normalized()
	for i: int in range(1, points.size()):
		points[i] = project(points[i - 1] + direction * lengths[i - 1])
	return points

func project(point: Vector3) -> Vector3:
	for envelope: Dictionary in envelopes:
		var inverse: Transform3D = envelope.inverse
		var frame: Transform3D = envelope.frame
		var native := inverse * point
		var center: Vector3 = envelope.center
		var radii: Vector3 = envelope.radii
		var x := (native.x - center.x) / radii.x
		var z := (native.z - center.z) / radii.z
		var radial := x * x + z * z
		if radial >= 1.0:
			continue
		var top := center.y + radii.y * sqrt(1.0 - radial)
		var margin := clearance / maxf(.01, frame.basis.y.length())
		if native.y < top + margin and native.y > center.y - radii.y:
			native.y = top + margin
			point = frame * native
	return point

func flow_acceleration(chain: int, fraction: float) -> Vector3:
	# A travelling wave reaches the hem after the upper sheet. Phase the
	# columns slightly apart so the whole cape does not flap like a board.
	# This goes through the ordinary length/contact solve, never into the
	# rendered vertices directly; the collar stays attached and cloth keeps
	# its authored length. No constant world-speed drag is reintroduced.
	var phase := TAU * 2.2 * flow_time - fraction * 4.2 + float(chain - 1) * .08
	var weight := fraction * fraction
	# Keep the reviewed fore/aft wave in the fabric response. The lateral
	# travelling-wave constraint below keeps it visible against the closer
	# trot contact, with twice the displacement at gallop.
	var ripple := Vector3.UP * (24.0 * sin(phase) + 8.0 * sin(phase * 1.47)) \
		+ back * (12.0 * sin(phase - .6))
	var lift := gallop_blend * (Vector3.UP * 28.0 + back * 45.0)
	var settle := Vector3.DOWN * (28.0 * (1.0 - moving_blend))
	return weight * (lift + settle + ripple * moving_blend)

func limit_lift(point: Vector3, root: Vector3, material_length: float, fraction: float) -> Vector3:
	# Keep the lower sheet draped while travelling rather than letting all
	# four links stream horizontally from the shoulders. Contact wins where
	# the rump stands above the free-hanging limit.
	# With only three independent columns, lateral contact can otherwise
	# spread the two edges apart during a gait change and stretch the sheet.
	# Carry all columns on the same small travelling wave, retaining their
	# shoulder spacing. Feeding this through length/contact relaxation keeps
	# the sheet from stretching; the wave fades to zero at its attachment.
	var wave := .0166 * moving_blend * (1.0 + gallop_blend) * fraction * fraction \
		* sin(TAU * 2.2 * flow_time - fraction * 4.2)
	var sideways := (point - root).dot(side)
	point += side * (wave - sideways)
	point.y = minf(point.y, root.y - material_length * lerpf(.68, .45, gallop_blend))
	return project(point)

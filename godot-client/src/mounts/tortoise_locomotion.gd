extends RefCounted
## In-place four-beat mounted gait on the existing tortoise's physical chains.
## The imported mesh, native animations, rest and skin remain untouched.
var rig: Skeleton3D
var neutral: Array[Transform3D] = []
var legs: Array[Dictionary] = []
var root := -1
var root_rest := Transform3D.IDENTITY
var center := Vector3.ZERO
var tuning: Dictionary
var last_targets := {}
var max_reach_error := 0.0
var rebound_paw_vertices := 0

func configure(skeleton: Skeleton3D, settings: Dictionary) -> Array[String]:
	rig = skeleton
	tuning = settings
	root = rig.find_bone(str(settings.rootBone))
	if root < 0: return ["Tortoise body root missing"]
	root_rest = rig.get_bone_global_rest(root)
	var point: Array = settings.bodyCenter
	center = Vector3(point[0], point[1], point[2])
	for bone: int in rig.get_bone_count(): neutral.append(rig.get_bone_rest(bone))
	for spec: Dictionary in settings.legs:
		var chain := PackedInt32Array()
		for name: String in spec.chain:
			var bone := rig.find_bone(name)
			if bone < 0: return ["Tortoise leg joint missing: " + name]
			chain.append(bone)
		legs.append({"name":spec.name,"chain":chain,"phase":spec.phase,"side":spec.side,
			"foot":rig.get_bone_global_rest(chain[2]).origin + Vector3(0,0,float(spec.trackOffsetZ)),
			"basis":rig.get_bone_global_rest(chain[2]).basis.orthonormalized()})
	_bind_paws()
	return []

func _bind_paws() -> void:
	# The imported rear shin owns part of the claws. Give the physical sole
	# one owner on this mounted instance so bending the shin cannot roll it
	# through the floor. Rest geometry, UVs, materials and the shared source
	# mesh stay intact; only this copied skin's local paw influences change.
	var heights: Array = tuning.pawBlendHeight
	for mesh: MeshInstance3D in rig.find_children("*","MeshInstance3D",true,false):
		if mesh.skin == null: continue
		var bind_bones := PackedInt32Array()
		for bind: int in mesh.skin.get_bind_count():
			var bone := rig.find_bone(mesh.skin.get_bind_name(bind))
			bind_bones.append(bone if bone >= 0 else mesh.skin.get_bind_bone(bind))
		var source := mesh.mesh
		var fitted := ArrayMesh.new()
		for surface: int in source.get_surface_count():
			var arrays := source.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var count := joints.size() / points.size()
			for vertex: int in points.size():
				if points[vertex].y >= float(heights[1]): continue
				var blend := 1.0 - smoothstep(float(heights[0]),float(heights[1]),points[vertex].y)
				for leg: Dictionary in legs:
					var chain: PackedInt32Array = leg.chain
					var owner := bind_bones.find(chain[2])
					var transferable := 0.0
					var member_slots := PackedInt32Array()
					for slot: int in count:
						var at := vertex * count + slot
						var bone := bind_bones[joints[at]]
						while bone >= 0 and bone != chain[0]: bone = rig.get_bone_parent(bone)
						if bone == chain[0]:
							member_slots.append(at)
							transferable += weights[at] * blend
					if transferable <= 0.0: continue
					var target := -1
					for at: int in member_slots:
						if joints[at] == owner: target = at
						weights[at] *= 1.0 - blend
					if target < 0:
						target = member_slots[0]
						transferable += weights[target]
						weights[target] = 0.0
						joints[target] = owner
					weights[target] += transferable
					rebound_paw_vertices += 1
			arrays[Mesh.ARRAY_BONES] = joints
			arrays[Mesh.ARRAY_WEIGHTS] = weights
			fitted.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
			fitted.surface_set_material(surface,source.surface_get_material(surface))
		mesh.mesh = fitted

func apply(gait: String, seconds: float, duration: float) -> void:
	var spec: Dictionary = tuning.gaits[gait]
	var phase := fposmod(seconds / duration, 1.0)
	for bone: int in neutral.size():
		rig.set_bone_pose_position(bone, neutral[bone].origin)
		rig.set_bone_pose_rotation(bone, neutral[bone].basis.get_rotation_quaternion())
		rig.set_bone_pose_scale(bone, neutral[bone].basis.get_scale())
	var roll := deg_to_rad(float(spec.roll)) * sin(TAU * phase)
	var rotation := Basis(Vector3.BACK, roll)
	var lift := -.105 + float(spec.bob) * (1.0 - cos(TAU * phase * 2.0))
	var frame := Transform3D(rotation, center - rotation * center + Vector3.UP * lift)
	var root_pose := frame * root_rest
	var parent := rig.get_bone_parent(root)
	var parent_rest := rig.get_bone_global_rest(parent) if parent >= 0 else Transform3D.IDENTITY
	var local := parent_rest.affine_inverse() * root_pose
	rig.set_bone_pose_position(root, local.origin)
	rig.set_bone_pose_rotation(root, local.basis.get_rotation_quaternion())
	rig.force_update_all_bone_transforms()
	last_targets.clear()
	for leg: Dictionary in legs:
		var step := fposmod(phase - float(leg.phase), 1.0)
		var stance := float(spec.stance)
		var stride := float(spec.stride)
		var offset := stride * (.5 - step / stance)
		var height := 0.0
		if step > stance:
			var swing := (step - stance) / (1.0 - stance)
			# C1 join to the straight support segment, with zero vertical
			# velocity at lift-off and touchdown.
			var slope := -(1.0 - stance) / stance
			var progress := (-2.0 * swing ** 3 + 3.0 * swing ** 2) + slope * (2.0 * swing ** 3 - 3.0 * swing ** 2 + swing)
			offset = stride * (-.5 + progress)
			height = float(spec.lift) * sin(PI * swing) ** 2
		var target: Vector3 = leg.foot + Vector3(0, height, offset)
		var chain: PackedInt32Array = leg.chain
		var a := rig.get_bone_global_pose(chain[0]).origin
		var b := rig.get_bone_global_pose(chain[1]).origin
		var c := rig.get_bone_global_pose(chain[2]).origin
		var first := a.distance_to(b)
		var second := b.distance_to(c)
		var direction := (target - a).normalized()
		var reach := clampf(a.distance_to(target), absf(first - second) + .00001, first + second - .00001)
		max_reach_error = maxf(max_reach_error, absf(reach - a.distance_to(target)))
		var along := (first * first + reach * reach - second * second) / (2.0 * reach)
		var pole := Vector3(float(leg.side), 0, 0)
		var bend := (pole - direction * pole.dot(direction)).normalized()
		var knee := a + direction * along + bend * sqrt(maxf(0.0, first * first - along * along))
		_aim(chain[0], chain[1], knee)
		_aim(chain[1], chain[2], a + direction * reach)
		_set_basis(chain[2], leg.basis)
		rig.force_update_all_bone_transforms()
		last_targets[leg.name] = {"position":target,"support":step <= stance,"phase":step}

func _set_basis(bone: int, basis: Basis) -> void:
	var parent := rig.get_bone_parent(bone)
	var parent_basis := rig.get_bone_global_pose(parent).basis.orthonormalized() if parent >= 0 else Basis.IDENTITY
	rig.set_bone_pose_rotation(bone, (parent_basis.inverse() * basis).get_rotation_quaternion().normalized())

func _aim(bone: int, child: int, target: Vector3) -> void:
	var pose := rig.get_bone_global_pose(bone)
	var before := rig.get_bone_global_pose(child).origin - pose.origin
	_set_basis(bone, Basis(Quaternion(before.normalized(), (target - pose.origin).normalized())) * pose.basis.orthonormalized())
	rig.force_update_all_bone_transforms()

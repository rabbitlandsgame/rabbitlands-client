extends SceneTree
## Shared Human face fields: coherent head parts, neutral restoration and a
## source-preserving High finish. Run with the production renderer for final QA.
const FIT := preload("res://src/actors/character_proportions.gd")
const HIGH := preload("res://src/actors/high_portrait_appearance.gd")
var checks := 0
var failures := 0
var records: Array = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	expect(FIT.face_shape({}).size() == 10 and FIT.face_is_neutral(FIT.face_shape({})), "legacy appearance has ten neutral controls")
	expect(FIT.face_is_neutral(FIT.face_shape({"eye_size": NAN, "eye_tilt": "bad"})), "malformed optional controls have neutral defaults")
	var frame := {"eye_y": .075, "eye_z": .045, "scale": 1.0,
		"eye_left": Vector3(-.030,.075,.045), "eye_right": Vector3(.030,.075,.045)}
	var minimum_determinant := 1.0
	var maximum_inverse_error := 0.0
	var states: Array = []
	for field: String in FIT.FACE_FIELDS:
		for value: int in [0, 100]:
			states.append(FIT.face_shape({field: value}))
	for value: int in [0, 100]:
		var appearance := {}
		for field: String in FIT.FACE_FIELDS:
			appearance[field] = value
		states.append(FIT.face_shape(appearance))
	for shape: PackedFloat32Array in states:
		for x: float in [-.065,-.03,-.015,-.008,0,.008,.015,.03,.065]:
			for y: float in [-.07,-.03,0,.025,.05,.075,.09,.11,.15]:
				var point := Vector3(x,y,.050)
				var moved := FIT.face_point(point, frame, shape)
				var determinant := FIT.face_jacobian(point, frame, shape).determinant()
				minimum_determinant = minf(minimum_determinant, determinant)
				var inverse_error := FIT.inverse_face_point(moved, frame, shape).distance_to(point)
				maximum_inverse_error = maxf(maximum_inverse_error, inverse_error)
				expect(moved.is_finite() and point.distance_to(moved) < .025, "bounded finite combined face field")
				expect(determinant > .15, "sampled extreme field has no fold")
				expect(inverse_error < .000001, "shared inverse recovers canonical point")
		for point: Vector3 in [Vector3(0,-.10,.05),Vector3(0,.16,.05),Vector3(.10,.08,.05),Vector3(0,.07,-.04)]:
			expect(FIT.face_point(point, frame, shape) == point, "neck/cap/ear/rear boundary exactly fixed")
		var left := FIT.face_point(Vector3(-.000001,.075,.05),frame,shape)
		var right := FIT.face_point(Vector3(.000001,.075,.05),frame,shape)
		expect(left.distance_to(right) < .000004, "eye pivots meet at a closed stationary bridge")
	records.append({"minimum_jacobian_determinant":minimum_determinant,"maximum_inverse_error_m":maximum_inverse_error})
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for sex: String in ["male", "female"]:
		var actor := ReplicatedActor3D.new()
		actor.apply_render_quality(1, true)
		root.add_child(actor)
		var errors := actor.configure({"actor_id":9901,"x":0,"y":0,"rotation":0,"kind":1,
			"name":"","appearance":{},"equipment_visuals":{}}, CoordinateAdapter.new({"walkingHeight":0.0}), models["luminous_"+sex], animation, equipment)
		expect(errors.is_empty(), sex + " production actor configures")
		actor.set_process(false)
		actor.set_physics_process(false)
		var native := actor._native_model
		var baseline := {}
		for part: String in HIGH.PARTS:
			var node := native.find_child(part,true,false) as MeshInstance3D
			baseline[part] = {"mesh":node.mesh,"skin":node.skin,"material":node.material_override}
		var canonical_frame := FIT.face_frame(native, actor.get_skeleton())
		for field: String in FIT.FACE_FIELDS:
			for value: int in [0,100]:
				var appearance := {field:value}
				var start := Time.get_ticks_usec()
				actor.apply_appearance_variants(appearance)
				var elapsed := Time.get_ticks_usec()-start
				var maximum_delta := 0.0
				for part: String in HIGH.PARTS:
					var node := native.find_child(part,true,false) as MeshInstance3D
					expect(node.skin == baseline[part].skin,"same canonical skin "+part)
					var delta := compare_mesh(baseline[part].mesh,node.mesh)
					maximum_delta = maxf(maximum_delta,delta)
					if field in ["eye_size","eye_spacing","eye_tilt"] and part == "eyes":
						expect(delta > .00015,"eye control moves eye patch and matching skin")
				var current_frame := FIT.face_frame(native,actor.get_skeleton())
				expect(current_frame == canonical_frame,"shaped eyes never redefine canonical frame")
				expect(maximum_delta > .0003,"visible response to "+field)
				records.append({"sex":sex,"field":field,"value":value,"apply_usec":elapsed,"maximum_delta_m":maximum_delta})
		var appearance := {"face_length":65,"eye_size":15,"eye_tilt":67,"eye_spacing":40,
			"nose_width":25,"lip_fullness":85,"brow_depth":75,"jaw":35,"cheekbones":70,"nose":35}
		actor.apply_appearance_variants(appearance)
		var shaped := {}
		for part: String in HIGH.PARTS:
			var node := native.find_child(part,true,false) as MeshInstance3D
			shaped[part] = {"mesh":node.mesh,"material":node.material_override}
		actor.apply_render_quality(2,true)
		for part: String in HIGH.PARTS:
			var node := native.find_child(part,true,false) as MeshInstance3D
			var meta: Dictionary = node.get_meta(HIGH.META,{})
			expect(meta.get("source") == shaped[part].mesh,"High preserves selected lower-tier source "+part)
			expect(node.get_meta(FIT.SOURCE_META) == baseline[part].mesh,"all High parts retain canonical face source "+part)
		actor.apply_render_quality(1,true)
		for part: String in HIGH.PARTS:
			var node := native.find_child(part,true,false) as MeshInstance3D
			expect(node.mesh == shaped[part].mesh and node.material_override == shaped[part].material,"High restores exact selected head part "+part)
		actor.apply_appearance_variants({})
		for part: String in HIGH.PARTS:
			var node := native.find_child(part,true,false) as MeshInstance3D
			expect(node.mesh == baseline[part].mesh and not node.has_meta(FIT.SOURCE_META),"neutral restores exact mesh and removes face metadata "+part)
		actor.free()
		await process_frame
		expect(HIGH.cache_metrics().high_users == 0 and HIGH.cache_metrics().sculpt_cpu_bytes == 0,"actor removal releases High face resources")
	var output := OS.get_environment("RL_FACE_CONTROL_OUTPUT")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/human-face-controls")
	DirAccess.make_dir_recursive_absolute(output)
	FileAccess.open(output.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"checks":checks,"failures":failures,"records":records},"  "))
	print("Human face controls: ",checks," checks, ",failures," failures")
	quit(1 if failures else 0)

func compare_mesh(source: Mesh, result: Mesh) -> float:
	var maximum := 0.0
	expect(source.get_surface_count() == result.get_surface_count(),"same face surface count")
	for surface: int in source.get_surface_count():
		var before := source.surface_get_arrays(surface)
		var blends := source.surface_get_blend_shape_arrays(surface)
		var lods := FIT.LODS._surface_lods(source,surface)
		FIT.compact(before,blends,lods)
		var after := result.surface_get_arrays(surface)
		var points: PackedVector3Array = before[Mesh.ARRAY_VERTEX]
		var moved: PackedVector3Array = after[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = after[Mesh.ARRAY_NORMAL]
		expect(points.size() == moved.size() and before[Mesh.ARRAY_INDEX] == after[Mesh.ARRAY_INDEX],"cheap shared control preserves topology")
		expect(before[Mesh.ARRAY_TEX_UV] == after[Mesh.ARRAY_TEX_UV],"source UV1 remains anchored")
		expect(before[Mesh.ARRAY_BONES] == after[Mesh.ARRAY_BONES] and before[Mesh.ARRAY_WEIGHTS] == after[Mesh.ARRAY_WEIGHTS],"exact four/eight bone influences")
		for index: int in points.size():
			maximum = maxf(maximum,points[index].distance_to(moved[index]))
			expect(moved[index].is_finite() and normals[index].is_finite() and absf(normals[index].length()-1) < .002,"finite normalized selected face")
	return maximum

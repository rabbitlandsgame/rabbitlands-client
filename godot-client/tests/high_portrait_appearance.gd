extends SceneTree
## Production actor, production renderer, exact quality restoration and UV2
## anchoring checks. RL_HIGH_PORTRAIT_OUTPUT selects ignored evidence output.
const HIGH := preload("res://src/actors/high_portrait_appearance.gd")
var failures := 0
var checks := 0
var stage: Node3D
var camera: Camera3D
var folder := ""
var results: Array = []
var geometry_records: Array = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	folder = OS.get_environment("RL_HIGH_PORTRAIT_OUTPUT")
	if folder.is_empty():
		folder = ProjectSettings.globalize_path("res://test-artifacts/high-portraits")
	DirAccess.make_dir_recursive_absolute(folder)
	root.size = Vector2i(720, 720)
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("1b242b")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("b8c3d0")
	world.environment.ambient_light_energy = 0.62
	stage.add_child(world)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-32, -28, 0)
	key.light_energy = 1.15
	key.light_color = Color("ffe9d1")
	stage.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, 145, 0)
	fill.light_energy = 0.45
	fill.light_color = Color("a1beca")
	stage.add_child(fill)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 0.48
	camera.current = true
	camera.cull_mask = 3
	stage.add_child(camera)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	HIGH.clear()
	check_feature_artwork()
	check_seam_midpoints()
	for sex: String in ["male", "female"]:
		var slug := "luminous_" + sex
		var actor := ReplicatedActor3D.new()
		actor.apply_render_quality(1, true)
		stage.add_child(actor)
		var appearance := {"skin": 2, "eyes": 1, "hair": AppearanceVariants.pack_hair(1 if sex == "male" else 3, 1 if sex == "male" else 14),
			"hair_detail": 1 if sex == "male" else 2, "facial_hair": 0, "jaw": 62 if sex == "male" else 35,
			"cheekbones": 68 if sex == "male" else 70, "nose": 44 if sex == "male" else 35}
		var error := actor.configure({"actor_id": 9901, "x": 0, "y": 0, "rotation": 0, "kind": 1,
			"name": "", "appearance": appearance, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
			models[slug], animation, equipment)
		expect(error.is_empty(), sex + " production actor configures")
		expect(HIGH.cache_metrics().texture_bundles == 0 and HIGH.cache_metrics().mesh_entries == 0,
			"initial Medium loads no High resources")
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.rotation.y = PI
		actor._advance_facing_offset(1.0)
		for node: Node in actor.get_children():
			if node is Node3D and node.name != "NativeModel":
				(node as Node3D).hide()
		freeze(actor, "idle", 0.4)
		var baseline: Dictionary = {}
		for part: String in HIGH.PARTS:
			var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
			baseline[part] = {"mesh": node.mesh, "material": node.material_override, "skin": node.skin}
		for level: int in [1, 2]:
			var started := Time.get_ticks_usec()
			actor.apply_render_quality(level, true)
			var elapsed := Time.get_ticks_usec() - started
			if level == 2:
				expect(HIGH.cache_metrics().texture_bundles == 1, "one shared High texture bundle")
				for part: String in HIGH.PARTS:
					var surface := actor._native_model.find_child(part, true, false) as MeshInstance3D
					var finish := surface.material_override as ShaderMaterial
					expect(bool(finish.get_shader_parameter("portrait_eye_surface")) == (part == "eyes"),
						"wet corneal response is restricted to the existing eye patch " + part)
				var head_triangles := count_head_triangles(actor)
				expect(head_triangles >= 6000 and head_triangles <= 8200, "reviewed 6–8k High head budget")
				results.append({"sex":sex,"head_triangles":head_triangles})
				for part: String in HIGH.PARTS:
					var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
					expect(node.has_meta(HIGH.META), "High artwork applies " + part)
					expect(node.skin == baseline[part].skin, "High retains exact canonical skin binding")
					check_geometry(baseline[part].mesh, node.mesh, part)
					var material := node.material_override as ShaderMaterial
					expect(material.shader == HIGH.SHADER, "High shader active")
					expect(material.get_shader_parameter("skin_color") == (baseline[part].material as ShaderMaterial).get_shader_parameter("skin_color"), "skin selection preserved")
			for angle: String in ["front", "threequarter", "profile"]:
				var skeleton := actor.get_skeleton()
				var focus := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, 0.06, 0)
				var offset: Vector3 = {"front": Vector3(0, .055, 1), "threequarter": Vector3(.4, .055, 1), "profile": Vector3(.95, .055, .02)}[angle]
				camera.position = focus + offset
				camera.look_at(focus)
				await capture("%s-%s-%s" % [sex, "high" if level == 2 else "medium", angle])
			results.append({"sex": sex, "level": level, "apply_usec": elapsed, "cache": HIGH.cache_metrics()})
		if sex in ["male", "female"]:
			for color: int in [0, 2]:
				appearance.eyes = color
				actor.apply_appearance_variants(appearance)
				freeze(actor, "idle", .4)
				var skeleton := actor.get_skeleton()
				var focus := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, .06, 0)
				camera.position = focus + Vector3(.4, .055, 1)
				camera.look_at(focus)
				await capture(sex + "-high-eyes-" + str(color))
			appearance.eyes = 1
			actor.apply_appearance_variants(appearance)
		var original_jaw: int = appearance.jaw
		var canonical_count := int(HIGH.cache_metrics().canonical_mesh_entries)
		var slider_times := []
		for jaw: int in [0, 25, 50, 75, 100, original_jaw]:
			appearance.jaw = jaw
			var start := Time.get_ticks_usec()
			actor.apply_appearance_variants(appearance)
			slider_times.append(Time.get_ticks_usec() - start)
			expect(int(HIGH.cache_metrics().canonical_mesh_entries) == canonical_count, "new slider values reuse canonical sculpt/topology work")
		results.append({"sex": sex, "new_jaw_values": [0,25,50,75,100,original_jaw], "complete_actor_slider_usec": slider_times})
		# Pigment and lighting reviews use the same finished geometry.
		freeze(actor, "idle", .4)
		var review_skeleton := actor.get_skeleton()
		var review_focus := review_skeleton.to_global(review_skeleton.get_bone_global_pose(review_skeleton.find_bone("Head")).origin) + Vector3(0,.06,0)
		camera.position = review_focus + Vector3(.4,.055,1)
		camera.look_at(review_focus)
		for skin: int in [0, 5]:
			appearance.skin = skin
			actor.apply_appearance_variants(appearance)
			freeze(actor, "idle", .4)
			await capture(sex + "-high-skin-" + str(skin))
		appearance.skin = 2
		actor.apply_appearance_variants(appearance)
		freeze(actor, "idle", .4)
		key.rotation_degrees.y = 40
		await capture(sex + "-high-light-right")
		key.rotation_degrees.y = -80
		await capture(sex + "-high-light-left")
		key.rotation_degrees.y = -28
		var body := actor._native_model.find_child("body", true, false) as MeshInstance3D
		var high_mesh := body.mesh
		var uv: PackedVector2Array = body.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2]
		for action: String in ["walk", "run", "idle"]:
			freeze(actor, action, .37)
			expect(body.mesh == high_mesh and body.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2] == uv,
				"High painted coordinates stay exact through " + action)
		actor.apply_render_quality(1, true)
		for part: String in HIGH.PARTS:
			var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
			expect(node.mesh == baseline[part].mesh and node.material_override == baseline[part].material,
				"Medium restores exact refined mesh/material " + part)
		expect(HIGH.cache_metrics().texture_bundles == 0 and HIGH.cache_metrics().mesh_entries == 0,
			"last High user downgrade releases images and mesh cache")
		# The High finish also applies at neutral sliders; changing a face and
		# returning to Medium must recover its new exact baseline, not the old
		# preset or a twice-displaced High mesh.
		appearance.jaw = 50
		appearance.cheekbones = 50
		appearance.nose = 50
		actor.apply_appearance_variants(appearance)
		var neutral_body := actor._native_model.find_child("body", true, false) as MeshInstance3D
		var neutral_source := neutral_body.mesh
		var neutral_material := neutral_body.material_override
		actor.apply_render_quality(2, true)
		check_geometry(neutral_source, neutral_body.mesh, sex + " neutral")
		freeze(actor, "idle", .4)
		for angle: String in ["front", "threequarter", "profile"]:
			var skeleton := actor.get_skeleton()
			var focus := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, .06, 0)
			camera.position = focus + {"front": Vector3(0, .055, 1), "threequarter": Vector3(.4, .055, 1), "profile": Vector3(.95, .055, .02)}[angle]
			camera.look_at(focus)
			await capture(sex + "-neutral-high-" + angle)
		actor.apply_render_quality(1, true)
		expect(neutral_body.mesh == neutral_source and neutral_body.material_override == neutral_material, "neutral exact restore after slider change")
		if sex == "male":
			for style: int in [2, 3, 5]:
				appearance.facial_hair = style
				actor.apply_appearance_variants(appearance)
				var beard := actor._native_model.find_child(HIGH.BEARD, true, false) as MeshInstance3D
				var beard_source := beard.mesh
				var beard_material := beard.material_override
				actor.apply_render_quality(2, true)
				var portrait_source: Dictionary = beard.get_meta(HIGH.META,{})
				expect(beard.mesh != beard_source and portrait_source.get("source") == beard_source
					and portrait_source.get("override") == beard_material,
					"High portrait beard retains exact incoming source mesh/material")
				expect((beard.material_override as ShaderMaterial).shader == (beard_material as ShaderMaterial).shader,
					"independent High grooming retains the beard shader")
				freeze(actor, "idle", .4)
				var skeleton := actor.get_skeleton()
				var focus := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, .06, 0)
				camera.position = focus + Vector3(.4, .055, 1)
				camera.look_at(focus)
				await capture("male-high-beard-" + str(style))
				actor.apply_render_quality(1, true)
				expect(beard.mesh == beard_source and beard.material_override == beard_material, "Medium beard exact restore")
		actor.apply_render_quality(0, true)
		expect(HIGH.cache_metrics().texture_bundles == 0, "Low allocates no High texture")
		appearance.facial_hair = 1
		actor.apply_appearance_variants(appearance)
		actor.apply_render_quality(2, true)
		for part: String in HIGH.PARTS:
			var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
			var material := node.material_override as ShaderMaterial
			expect(bool(material.get_shader_parameter("stubble_enabled"))
				and material.get_shader_parameter("stubble_mask") is Texture2D, "High retains surface-bound stubble pigment")
		actor.apply_render_quality(1, true)
		expect(HIGH.cache_metrics().texture_bundles == 0, "stubble High downgrade also releases resources")
		# A helmet changes body coverage and then restores it. Both resulting
		# lower-tier sources must survive another High round trip exactly.
		for visuals: Dictionary in [{3: 143}, {}]:
			actor.apply_equipment_visuals(visuals)
			var current_body := actor._native_model.find_child("body", true, false) as MeshInstance3D
			var current_mesh := current_body.mesh
			var current_material := current_body.material_override
			actor.apply_render_quality(2, true)
			actor.apply_render_quality(1, true)
			expect(current_body.mesh == current_mesh and current_body.material_override == current_material, "helmet transition exact Medium restore")
		# Release while actively High, rather than only after a downgrade.
		actor.apply_render_quality(2, true)
		actor.free()
		await process_frame
		expect(HIGH.cache_metrics().high_users == 0 and HIGH.cache_metrics().sculpt_cpu_bytes == 0, "actor removal releases High CPU sculpt")
	FileAccess.open(folder.path_join("checks.json"), FileAccess.WRITE).store_string(JSON.stringify({"checks": checks,
		"failures": failures, "results": results, "geometry": geometry_records}, "  "))
	print("High portraits: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)

func freeze(actor: ReplicatedActor3D, action: String, seconds: float) -> void:
	actor.play_action(StringName(action), true)
	actor.animation_player.seek(seconds, true)
	actor.animation_player.pause()
	actor.get_skeleton().force_update_all_bone_transforms()

func check_feature_artwork() -> void:
	for sex: String in ["male", "female"]:
		var prefix := "res://data/actors/portraits_high/" + sex
		var descriptor: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(prefix + ".json"))
		var geometry: Dictionary = descriptor.geometry
		expect(int(descriptor.version) == 4 and int(geometry.stride) == 6 and int(geometry.size) == 256,
			"feature artwork reuses the existing six-channel CPU grid " + sex)
		expect(FileAccess.get_sha256(str(geometry.path)) == str(geometry.sha256), "descriptor identifies exact sculpt payload " + sex)
		expect(float(geometry.baked_max_displacement_m) <= .005501, "feature sculpt retains original displacement clamp")
		var paint := Image.load_from_file(prefix + "-paint.png")
		var regions := Image.load_from_file(prefix + "-regions.png")
		var normal := Image.load_from_file(prefix + "-normal.png")
		expect(paint.get_size() == Vector2i(1024,1024) and regions.get_size() == paint.get_size() and normal.get_size() == paint.get_size(),
			"same three1K shared maps per sex")
		for eye: Dictionary in descriptor.features.eyes:
			var center := Vector2(float(eye.center_m[0]),float(eye.center_m[1]))
			var radius := float(eye.iris_radius_m)
			var projection: Dictionary = descriptor.projection
			var scale := Vector2(1023.0/(float(projection.x_max)-float(projection.x_min)),1023.0/(float(projection.y_max)-float(projection.y_min)))
			var at := Vector2i(roundi((center.x-float(projection.x_min))*scale.x), roundi((float(projection.y_max)-center.y)*scale.y))
			var ring := at + Vector2i(roundi(radius*.55*scale.x),0)
			expect(radius > .004 and radius < .010 and regions.get_pixelv(at).g > .75, "defined pupil stays inside selected iris")
			expect(paint.get_pixelv(at).get_luminance() < paint.get_pixelv(ring).get_luminance()*.50,
				"pupil and variegated iris remain distinct in authored map")
			var curve := normal.get_pixelv(ring)
			expect(absf(curve.r-.5) > .05 and curve.b > .75, "corneal map carries curved surface response")

func check_geometry(source: Mesh, result: Mesh, label: String) -> void:
	expect(source.get_surface_count() == result.get_surface_count(), "surface count preserved " + label)
	for surface: int in source.get_surface_count():
		var a := source.surface_get_arrays(surface)
		var b := result.surface_get_arrays(surface)
		var blends := source.surface_get_blend_shape_arrays(surface)
		var lods := HIGH.LODS._surface_lods(source, surface)
		HIGH.COMPACTOR.compact(a, blends, lods)
		var ai: PackedInt32Array = a[Mesh.ARRAY_INDEX]
		var bi: PackedInt32Array = b[Mesh.ARRAY_INDEX]
		expect(source.get_blend_shape_count() == result.get_blend_shape_count(), "blend shape count preserved")
		expect(bi.size() >= ai.size() and bi.size() - ai.size() < 21000, "bounded head-only triangle refinement " + label)
		var seam_positions := {}
		var maximum_delta := 0.0
		var maximum_seam_gap := 0.0
		for index: int in (a[Mesh.ARRAY_VERTEX] as PackedVector3Array).size():
			var p: Vector3 = a[Mesh.ARRAY_VERTEX][index]
			var q: Vector3 = b[Mesh.ARRAY_VERTEX][index]
			maximum_delta = maxf(maximum_delta, p.distance_to(q))
			expect(p.distance_to(q) < .0085 and q.is_finite(), "bounded finite sculpt including selected face Jacobian " + label)
			expect(a[Mesh.ARRAY_TEX_UV][index] == b[Mesh.ARRAY_TEX_UV][index], "UV1 remains exact " + label)
			var key := Vector3i(roundi(p.x * 1000000), roundi(p.y * 1000000), roundi(p.z * 1000000))
			if seam_positions.has(key):
				maximum_seam_gap = maxf(maximum_seam_gap, q.distance_to(seam_positions[key]))
				expect(q.distance_to(seam_positions[key]) < .000003, "coincident UV seam stays closed " + label)
			else:
				seam_positions[key] = q
		var vertices: PackedVector3Array = b[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = b[Mesh.ARRAY_NORMAL]
		var weights: PackedFloat32Array = b[Mesh.ARRAY_WEIGHTS]
		var width := int(weights.size() / vertices.size())
		var original_weights: PackedFloat32Array = a[Mesh.ARRAY_WEIGHTS]
		var original_bones: PackedInt32Array = a[Mesh.ARRAY_BONES]
		var bones: PackedInt32Array = b[Mesh.ARRAY_BONES]
		expect(width == int(original_weights.size() / (a[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()), "original influence width retained")
		for index: int in original_weights.size():
			expect(weights[index] == original_weights[index] and bones[index] == original_bones[index], "retained vertex keeps exact canonical influence")
		for lod: Variant in HIGH.LODS._surface_lods(result, surface).values():
			for index: int in lod:
				expect(index >= 0 and index < vertices.size(), "retained LOD index stays valid")
		for index: int in vertices.size():
			expect(vertices[index].is_finite() and normals[index].is_finite() and absf(normals[index].length() - 1.0) < .002, "finite normalized High vertex/normal")
			var sum := 0.0
			for influence: int in width:
				sum += weights[index * width + influence]
			expect(absf(sum - 1.0) < .001, "normalized canonical skin weights")
		geometry_records.append({"part": label, "surface": surface, "source_triangles": ai.size() / 3,
			"high_triangles": bi.size() / 3, "vertices": vertices.size(), "max_displacement_m": maximum_delta,
			"max_original_seam_gap_m": maximum_seam_gap})

func check_seam_midpoints() -> void:
	var bundle := HIGH._bundle("male")
	expect(HIGH._normal_mask(Vector3(.080,.140,.030)) > .999,
		"smooth source normals cover outer cheek/temple and forehead beyond displacement fade")
	expect(HIGH._sculpt_mask(Vector3(.080,.140,.030)) < .1,
		"normal coverage does not relax positional seam protections")
	var points := PackedVector3Array([Vector3(-.025,.04,.05), Vector3(.025,.04,.05), Vector3(0,.02,.05),
		Vector3(.025,.04,.05), Vector3(-.025,.04,.05), Vector3(0,.06,.05)])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = points
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK, Vector3.UP, Vector3.UP, Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO, Vector2.ONE, Vector2(.5,0), Vector2(.2,.3), Vector2(.8,.9), Vector2(.1,.7)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,3,4,5])
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array([0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0])
	HIGH._subdivide(arrays, [], Transform3D.IDENTITY, bundle, {}, Vector3.ZERO, false)
	var split: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var positions := {}
	var pairs := 0
	for index: int in range(6, split.size()):
		var p := split[index]
		var key := Vector3i(roundi(p.x * 1000000), roundi(p.y * 1000000), roundi(p.z * 1000000))
		var moved := HIGH._sculpt_point(p, bundle)
		if positions.has(key):
			pairs += 1
			expect(moved == positions[key], "new UV seam midpoint evaluates identically despite unrelated normal/UV")
		positions[key] = moved
	for p: Vector3 in [Vector3(0,-.061,.06), Vector3(.09,.05,.06), Vector3(0,.15,.06), Vector3(0,.04,-.01)]:
		expect(HIGH._sculpt_point(p, bundle) == p, "neck/ear/cap/rear seam displacement exactly zero")
	for x: float in [-.05,0,.05]:
		var p := Vector3(x,.02,.05)
		var frame := {"scale":1.0,"eye_y":.075,"eye_z":.045}
		for shape: Vector3 in [Vector3(-1,-1,-1), Vector3.ONE]:
			var moved := HIGH.COMPACTOR.face_point(p, frame, shape)
			expect(HIGH._canonical(moved, frame, shape).distance_to(p) < .000001, "custom face inverse remains stable at extrema")
	expect(pairs > 0, "fixture actually tests duplicated new edge midpoint")
	HIGH.clear()

func count_head_triangles(actor: ReplicatedActor3D) -> int:
	var total := 0
	var head := actor.get_skeleton().find_bone("Head")
	for part: String in HIGH.PARTS:
		var node := actor._native_model.find_child(part,true,false) as MeshInstance3D
		var head_bind := -1
		for bind: int in node.skin.get_bind_count():
			if node.skin.get_bind_bone(bind) == head or node.skin.get_bind_name(bind) == &"Head":
				head_bind = bind
		for surface: int in node.mesh.get_surface_count():
			var arrays := node.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var width := int(weights.size()/points.size())
			for triangle: int in range(0,indices.size(),3):
				var weight := 0.0
				for corner: int in 3:
					var index := indices[triangle+corner]
					for influence: int in width:
						if bones[index*width+influence] == head_bind:
							weight += weights[index*width+influence]
				if weight/3.0 > .45:
					total += 1
	return total

func capture(name: String) -> void:
	for frame: int in 5:
		await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(folder.path_join(name + ".png")) == OK, "save " + name)
	print("HIGH PORTRAIT RENDER ", name)

extends "res://tests/integration/gear_fit_sweep.gd"
## Close side views and actual neck coverage through production equipment.

func neck_report(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.name.to_lower() != "body" or not mesh.has_meta("uncovered_body_mesh"):
			continue
		var original := mesh.get_meta("uncovered_body_mesh") as Mesh
		for surface: int in range(original.get_surface_count()):
			var a := original.surface_get_arrays(surface)
			var positions: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
			var source: PackedInt32Array = a[Mesh.ARRAY_INDEX]
			var kept := {}
			var drawn: PackedInt32Array = mesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_INDEX]
			for index: int in range(0, drawn.size(), 3):
				kept[Vector3i(drawn[index], drawn[index+1], drawn[index+2])] = true
			var removed := []
			var remaining := []
			for index: int in range(0, source.size(), 3):
				var c := (positions[source[index]] + positions[source[index+1]] + positions[source[index+2]]) / 3.
				if c.y > 1.45 and c.y < 1.535 and absf(c.x) < .09 and c.z < -.04:
					var point := [c.x,c.y,c.z]
					if kept.has(Vector3i(source[index],source[index+1],source[index+2])):
						remaining.append(point)
					else:
						removed.append(point)
			result[str(surface)] = {"kept": remaining, "removed": removed}
			expect(removed.is_empty(), str(actor.actor_id) + " retains the native nape skin")
	return result

func capture_opposite(actor: ReplicatedActor3D, name: String) -> void:
	if output.is_empty():
		return
	var focus := Vector3(0., .95, 0.)
	camera.size = 2.25
	camera.position = focus + Vector3(-4., .05, 0.)
	camera.look_at(focus)
	await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name + ".png")) == OK, name + " captures")

func shaft_samples(scene: Node3D) -> Array:
	var result := []
	for low: float in [.10, .25]:
		for sign_value: float in [-1., 1.]:
			var total := Vector3.ZERO
			var count := 0
			for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
				var mesh := (node as MeshInstance3D).mesh
				for surface: int in mesh.get_surface_count():
					var vertices: PackedVector3Array = mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
					for vertex: Vector3 in vertices:
						if vertex.y >= low and vertex.y < low + .15 and vertex.x * sign_value > 0.:
							total += vertex
							count += 1
			result.append([count, total / maxf(count, 1.)])
	return result

func check_imported_shafts(equipment: Dictionary) -> void:
	# Loading a res:// GLB can succeed while an old editor import still draws
	# its previous shape. Compare the production path to the actual GLB data.
	for key: String in ["4:230", "6:226"]:
		for sex: String in ["male", "female"]:
			var path: String = equipment["models"][key]["variants"]["canonical_human_" + sex]["scene"]
			var imported := GlbSceneCache.instantiate(path)
			var packed := GlbSceneCache._build_raw(ProjectSettings.globalize_path(path))
			expect(imported != null and packed != null, key + " " + sex + " loads both geometry paths")
			if imported == null or packed == null:
				continue
			var source := packed.instantiate() as Node3D
			var actual := shaft_samples(imported)
			var expected := shaft_samples(source)
			for band: int in range(actual.size()):
				expect(actual[band][0] == expected[band][0] and (actual[band][1] as Vector3).distance_to(expected[band][1]) < .001, key + " " + sex + " draws current shaft geometry; refresh Godot imports if this fails")
			imported.free()
			source.free()

func run() -> void:
	output = OS.get_environment("ELORIA_GEAR_ARTIFACTS")
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(640,760)
	stage=Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment=Environment.new()
	world.environment.background_mode=Environment.BG_COLOR
	world.environment.background_color=Color(.13,.16,.19)
	world.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color=Color.WHITE
	world.environment.ambient_light_energy=.65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees=Vector3(-35,-30,0)
	stage.add_child(light)
	camera=Camera3D.new()
	camera.projection=Camera3D.PROJECTION_ORTHOGONAL
	camera.current=true
	stage.add_child(camera)
	var models: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var config_path:=OS.get_environment("ELORIA_GEAR_REGISTRY")
	if config_path.is_empty():config_path="res://data/actors/equipment.json"
	var equipment: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(config_path))
	check_imported_shafts(equipment)
	var animations: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var reports := {}
	for slug: String in ["luminous_male","luminous_female"]:
		var actor:=make_actor(slug,models[slug],animations,equipment)
		for label: String in ["bare","ranger","ranger-nohood","vanguard","warden","arcane-01","rugged-02","rugged-07"]:
			var outfit := {}
			if label.begins_with("ranger"):outfit={4:230,5:225,6:226}
			if label=="ranger":outfit[3]=159
			if label=="vanguard":outfit={3:134,4:220,5:209,6:249}
			if label=="warden":outfit={3:122,4:176,5:189,6:205}
			if label=="arcane-01":outfit={4:179,5:225,6:226}
			if label=="rugged-02":outfit={4:228,5:225,6:226}
			if label=="rugged-07":outfit={4:233,5:225,6:226}
			actor.apply_equipment_visuals(outfit)
			await capture(actor,slug+"-"+label+"-side",true,"Idle_Subtle",true)
			await capture_opposite(actor, slug + "-" + label + "-opposite")
			reports[slug+"-"+label]=neck_report(actor)
		actor.free()
		await process_frame
	if not output.is_empty():
		var file:=FileAccess.open(output.path_join("neck-coverage.json"),FileAccess.WRITE)
		file.store_string(JSON.stringify(reports,"  "))
	NativeAnimationImporter.clear()
	print("EQUIPMENT JOINTS: ",checks," checks, ",failures," failures")
	quit(1 if failures else 0)

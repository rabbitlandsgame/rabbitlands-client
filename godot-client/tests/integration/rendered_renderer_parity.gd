extends SceneTree
## Focused, deterministic Compatibility/Forward+ comparison for the production
## crowd presentation. Run this exact script once per renderer with
## scripts/run_presentation_checks.ps1, then compare the two artifact folders
## with scripts/compare_renderer_parity.py.
##
## The frame deliberately keeps renderer-sensitive paths together: the same
## StandardMaterial3D ground and lighting, the crowd benchmark's two complete
## equipment kits, production name/health overheads, and production spell
## flight/contact geometry at fixed ages. Animation and particles are frozen;
## no real-time simulation is used to choose the captured state.

const SCREEN_SIZE := Vector2i(1280, 720)
const FIXTURE_VERSION := 3
const FULL_KIT_A := {0: 114, 1: 106, 2: 0, 3: 117, 4: 171, 5: 184, 6: 192}
const FULL_KIT_B := {0: 164, 1: 111, 2: 1, 3: 109, 4: 172, 5: 185, 6: 193}
const ACTOR_X := [-3.2, 0.0, 3.2]
const PROBE_TOLERANCE := 3.0 / 255.0
const COLOR_PROBES := [
	{
		"id": "threshold",
		# Exercises both sides of the IEC sRGB 0.04045 threshold.
		"color": Color(0.02, 0.04045, 0.08, 0.70),
		"standard": Vector3(-2.55, 0.012, 2.40),
		"vertex": Vector3(-1.75, 0.014, 2.40),
	},
	{
		"id": "cyan",
		"color": Color(0x6b / 255.0, 0xcd / 255.0, 0xdb / 255.0, 0.34),
		"standard": Vector3(-0.40, 0.012, 2.40),
		"vertex": Vector3(0.40, 0.014, 2.40),
	},
	{
		"id": "orange",
		"color": Color(0xed / 255.0, 0x75 / 255.0, 0x44 / 255.0, 0.34),
		"standard": Vector3(1.75, 0.012, 2.40),
		"vertex": Vector3(2.55, 0.014, 2.40),
	},
]

var _failures := 0
var _artifacts := ""
var _camera: Camera3D
var _actors: Array[ReplicatedActor3D] = []
var _flight: WorldEffect3D
var _contact: WorldEffect3D


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path(
			"res://test-artifacts/renderer-parity")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var stage := Node3D.new()
	stage.name = "RendererParityStage"
	root.add_child(stage)
	_add_environment(stage)
	_add_ground(stage)
	_add_camera(stage)
	_add_color_probes(stage)
	await _add_actors(stage)
	_add_effects(stage)

	# Let imported meshes, labels and fixed geometry reach the render thread.
	# State is already frozen; these frames do not advance animation/effects.
	for _frame: int in range(12):
		await process_frame
	await RenderingServer.frame_post_draw

	var image: Image = root.get_texture().get_image()
	_expect(image != null, "a rendered frame is available")
	if image != null:
		_expect(image.get_size() == SCREEN_SIZE,
			"capture is %dx%d" % [SCREEN_SIZE.x, SCREEN_SIZE.y])
		_expect(_colour_count(image) >= 128,
			"capture contains actors, effects and ground")
		_expect(image.save_png(_artifacts.path_join("renderer-parity.png")) == OK,
			"capture is written")
		var probes := _probe_observations(image)
		for probe: Dictionary in probes:
			_expect(float(probe["maximumAbsoluteRgbDelta"]) <= PROBE_TOLERANCE,
				("%s production shader matches StandardMaterial in %s "
				+ "(max RGB delta %.6f <= %.6f)") % [
					str(probe["id"]), RenderingServer.get_current_rendering_method(),
					float(probe["maximumAbsoluteRgbDelta"]), PROBE_TOLERANCE])
		_write_metadata(probes)

	for actor: ReplicatedActor3D in _actors:
		actor.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("rendered renderer parity: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _add_environment(stage: Node3D) -> void:
	var world := WorldEnvironment.new()
	world.name = "ControlledEnvironment"
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("17232b")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color(0.78, 0.86, 1.0)
	world.environment.ambient_light_energy = 0.62
	stage.add_child(world)

	var key := DirectionalLight3D.new()
	key.name = "ControlledKey"
	key.rotation_degrees = Vector3(-42.0, -28.0, 0.0)
	key.light_color = Color("fff0d2")
	key.light_energy = 1.05
	key.shadow_enabled = false
	stage.add_child(key)


func _add_ground(stage: Node3D) -> void:
	var mesh := BoxMesh.new()
	mesh.size = Vector3(15.0, 0.10, 7.0)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("415254")
	material.roughness = 0.88
	mesh.material = material
	var ground := MeshInstance3D.new()
	ground.name = "StandardMaterialGround"
	ground.mesh = mesh
	ground.position = Vector3(0.0, -0.06, -0.25)
	stage.add_child(ground)


func _add_camera(stage: Node3D) -> void:
	_camera = Camera3D.new()
	_camera.name = "ControlledCamera"
	_camera.current = true
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	# Wide enough to retain the complete right-hand radiation contact geometry.
	_camera.size = 9.5
	_camera.keep_aspect = Camera3D.KEEP_WIDTH
	_camera.cull_mask = 3
	_camera.position = Vector3(0.0, 4.6, 9.2)
	stage.add_child(_camera)
	_camera.look_at(Vector3(0.0, 0.9, 0.0))


func _add_color_probes(stage: Node3D) -> void:
	# Each pair has identical geometry, source color, alpha and additive/unlit
	# state. The left mesh uses StandardMaterial3D's engine-managed color path;
	# the right uses the production spell shader's mesh vertex COLOR path.
	var vertices := PackedVector3Array([
		Vector3(-0.30, 0.0, -0.30), Vector3(0.30, 0.0, -0.30),
		Vector3(0.30, 0.0, 0.30), Vector3(-0.30, 0.0, -0.30),
		Vector3(0.30, 0.0, 0.30), Vector3(-0.30, 0.0, 0.30),
	])
	var uvs := PackedVector2Array()
	for _index: int in vertices.size():
		# The production shader's falloff is exactly one at the UV centre.
		uvs.append(Vector2(0.5, 0.5))
	for probe: Dictionary in COLOR_PROBES:
		var standard_arrays := []
		standard_arrays.resize(Mesh.ARRAY_MAX)
		standard_arrays[Mesh.ARRAY_VERTEX] = vertices
		standard_arrays[Mesh.ARRAY_TEX_UV] = uvs
		var standard_mesh := ArrayMesh.new()
		standard_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, standard_arrays)
		var standard_material := StandardMaterial3D.new()
		standard_material.albedo_color = probe["color"] as Color
		standard_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		standard_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		standard_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		standard_material.cull_mode = BaseMaterial3D.CULL_DISABLED
		standard_mesh.surface_set_material(0, standard_material)
		var standard := MeshInstance3D.new()
		standard.name = "StandardColorControl_" + str(probe["id"])
		standard.mesh = standard_mesh
		standard.position = probe["standard"] as Vector3
		standard.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		stage.add_child(standard)

		var colors := PackedColorArray()
		for _index: int in vertices.size():
			colors.append(probe["color"] as Color)
		var vertex_arrays := []
		vertex_arrays.resize(Mesh.ARRAY_MAX)
		vertex_arrays[Mesh.ARRAY_VERTEX] = vertices
		vertex_arrays[Mesh.ARRAY_COLOR] = colors
		vertex_arrays[Mesh.ARRAY_TEX_UV] = uvs
		var vertex_mesh := ArrayMesh.new()
		vertex_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, vertex_arrays)
		var vertex_material := ShaderMaterial.new()
		vertex_material.shader = load("res://src/world/spell_energy.gdshader") as Shader
		vertex_material.set_shader_parameter("intensity", 1.0)
		vertex_mesh.surface_set_material(0, vertex_material)
		var vertex := MeshInstance3D.new()
		vertex.name = "ProductionVertexColorProbe_" + str(probe["id"])
		vertex.mesh = vertex_mesh
		vertex.position = probe["vertex"] as Vector3
		vertex.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		stage.add_child(vertex)


func _add_actors(stage: Node3D) -> void:
	var model_document: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))
	var animation_document: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/animations/luminous.json"))
	var equipment_document: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	_expect(model_document is Dictionary and animation_document is Dictionary
		and equipment_document is Dictionary, "production actor data loads")
	if not (model_document is Dictionary and animation_document is Dictionary
		and equipment_document is Dictionary):
		return
	var models: Dictionary = (model_document as Dictionary)["models"] as Dictionary
	var animation: Dictionary = animation_document as Dictionary
	var equipment: Dictionary = equipment_document as Dictionary
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var specifications := [
		["Aster Vale", "luminous_female", FULL_KIT_A, 76],
		["Bram Ironwood", "luminous_male", FULL_KIT_B, 54],
		["Cinder Warden", "luminous_female", FULL_KIT_A, 31],
	]
	for index: int in specifications.size():
		var spec: Array = specifications[index] as Array
		var actor := ReplicatedActor3D.new()
		actor.name = "ParityActor%d" % index
		stage.add_child(actor)
		var dto := {
			"actor_id": 9100 + index, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": str(spec[0]), "health": int(spec[3]),
			"max_health": 100, "appearance": {"hair": index},
			"equipment_visuals": (spec[2] as Dictionary).duplicate(),
		}
		var errors: Array[String] = actor.configure(dto, adapter,
			models[str(spec[1])] as Dictionary, animation, equipment)
		_expect(errors.is_empty(), "%s production rig builds: %s" % [spec[0], errors])
		actor.position = Vector3(float(ACTOR_X[index]), 0.0, 0.0)
		actor.rotation.y = PI
		actor.set_physics_process(false)
		actor.set_process(false)
		actor.set_nameplate_visible(true)
		actor.set_health_visible(true)
		actor.play_action(&"combat_idle", true)
		if actor.animation_player != null:
			actor.animation_player.stop()
			actor.animation_player.play(
				actor.resolver.clip_for_action(actor.current_action), 0.0)
			actor.animation_player.seek(0.37, true)
			actor.animation_player.pause()
		if actor.combat_presentation != null:
			actor.combat_presentation.update_pose()
		var skeleton := actor.get_skeleton()
		if skeleton != null:
			var cape := skeleton.get_node_or_null("CapeCloth") as SkeletonModifier3D
			if cape != null:
				cape.active = false
		_actors.append(actor)


func _add_effects(stage: Node3D) -> void:
	_expect(_actors.size() == 3, "three representative actors are present")
	if _actors.size() != 3:
		return
	# Fire flight: real WorldEffect3D/SpellFlight3D, held at an exact fraction
	# of its analytic duration. Its ShaderMaterial consumes mesh vertex COLOR.
	_flight = WorldEffect3D.new()
	_flight.name = "FixedFireFlight"
	stage.add_child(_flight)
	_flight.configure(2, _actors[0].position, _actors[1].position, 8)
	_flight.set_process(false)
	_expect(_flight.flight != null, "production fire flight is created")
	if _flight.flight != null:
		var flight_duration := float(_flight.flight.get("duration"))
		_flight.flight.call("draw_at", flight_duration * 0.56)

	# Radiation contact: the same production ring/detail material at a fixed
	# age. GPU particles are disabled because their simulation is neither needed
	# for the color-space question nor deterministic across two processes.
	_contact = WorldEffect3D.new()
	_contact.name = "FixedRadiationContact"
	stage.add_child(_contact)
	_contact.configure(85, _actors[2].position, null, 6)
	_contact.set_process(false)
	var burst := _contact.get_node_or_null("EffectBurst") as GPUParticles3D
	if burst != null:
		burst.emitting = false
		burst.speed_scale = 0.0
	_contact._process(0.42)


func _write_metadata(probe_observations: Array[Dictionary]) -> void:
	if _actors.size() != 3:
		return
	var centres: Array[Vector2] = []
	var overheads: Array[Vector2] = []
	for actor: ReplicatedActor3D in _actors:
		centres.append(_camera.unproject_position(actor.global_position + Vector3.UP * 0.95))
		overheads.append(_camera.unproject_position(actor.global_position + Vector3.UP * 2.12))
	var flight_a: Vector2 = _camera.unproject_position(
		_actors[0].global_position + Vector3.UP * 0.85)
	var flight_b: Vector2 = _camera.unproject_position(
		_actors[1].global_position + Vector3.UP * 0.85)
	var diagnostics: Array[Dictionary] = []
	for actor: ReplicatedActor3D in _actors:
		diagnostics.append(_actor_diagnostics(actor))
	var regions := {
		# Clear of actors/effects: a control for the engine-managed
		# StandardMaterial3D color and the shared environment/light.
		"ground": [60, 540, 220, 120],
		"equipmentLeft": _rect(centres[0], Vector2(92, 132)),
		"equipmentMiddle": _rect(centres[1], Vector2(92, 132)),
		"equipmentRight": _rect(centres[2], Vector2(92, 132)),
		"overheadLeft": _rect(overheads[0], Vector2(112, 42)),
		"overheadMiddle": _rect(overheads[1], Vector2(112, 42)),
		"overheadRight": _rect(overheads[2], Vector2(112, 42)),
		"fireFlight": _bounds(flight_a, flight_b, Vector2(28, 45)),
		"radiationContact": _rect(
			_camera.unproject_position(_actors[2].global_position + Vector3.UP * 0.42),
			Vector2(125, 105)),
	}
	var probe_definitions := _probe_definitions()
	for probe: Dictionary in probe_definitions:
		regions[str(probe["standardRegion"])] = probe["standardRectangle"]
		regions[str(probe["vertexRegion"])] = probe["vertexRectangle"]
	var metadata := {
		"fixture": "rendered_renderer_parity",
		"fixtureVersion": FIXTURE_VERSION,
		"actualRenderingMethod": RenderingServer.get_current_rendering_method(),
		"videoAdapter": RenderingServer.get_video_adapter_name(),
		"screenSize": [SCREEN_SIZE.x, SCREEN_SIZE.y],
		"fixedState": {
			"animationSeconds": 0.37,
			"flightFraction": 0.56,
			"contactSeconds": 0.42,
			"particlesEnabled": false,
			"capeClothEnabled": false,
			"capeScope": "static authored cape pose; cloth simulation is outside this comparison",
			"equipmentKits": [FULL_KIT_A, FULL_KIT_B, FULL_KIT_A],
		},
		"observedState": diagnostics,
		"regions": regions,
		"colorProbeDefinitions": probe_definitions,
		"colorProbeObservations": probe_observations,
		"productionPaths": [
			"StandardMaterial3D ground", "ReplicatedActor3D equipment",
			"ReplicatedActor3D name and health overheads",
			"WorldEffect3D/SpellFlight3D flight",
			"WorldEffect3D contact ring and detail geometry",
			"spell_energy.gdshader vertex COLOR diagnostic",
		],
	}
	var file := FileAccess.open(_artifacts.path_join("renderer-parity.json"),
		FileAccess.WRITE)
	_expect(file != null, "metadata file opens")
	if file != null:
		file.store_string(JSON.stringify(metadata, "  ") + "\n")


func _probe_definitions() -> Array[Dictionary]:
	var definitions: Array[Dictionary] = []
	for probe: Dictionary in COLOR_PROBES:
		var identifier := str(probe["id"])
		var standard_name := "probe_%s_standard" % identifier
		var vertex_name := "probe_%s_vertex" % identifier
		var color := probe["color"] as Color
		definitions.append({
			"id": identifier,
			"inputSrgb": [color.r, color.g, color.b, color.a],
			"standardRegion": standard_name,
			"vertexRegion": vertex_name,
			"standardRectangle": _rect(
				_camera.unproject_position(probe["standard"] as Vector3), Vector2(22, 12)),
			"vertexRectangle": _rect(
				_camera.unproject_position(probe["vertex"] as Vector3), Vector2(22, 12)),
			"maximumChannelTolerance": PROBE_TOLERANCE,
		})
	return definitions


func _probe_observations(image: Image) -> Array[Dictionary]:
	var observations: Array[Dictionary] = []
	for probe: Dictionary in _probe_definitions():
		var standard := _mean_rgb(image, probe["standardRectangle"] as Array)
		var vertex := _mean_rgb(image, probe["vertexRectangle"] as Array)
		var maximum_delta := maxf(absf(vertex.r - standard.r),
			maxf(absf(vertex.g - standard.g), absf(vertex.b - standard.b)))
		observations.append({
			"id": probe["id"],
			"standardMeanRgb": [standard.r, standard.g, standard.b],
			"vertexMeanRgb": [vertex.r, vertex.g, vertex.b],
			"maximumAbsoluteRgbDelta": maximum_delta,
			"passed": maximum_delta <= PROBE_TOLERANCE,
		})
	return observations


func _mean_rgb(image: Image, rectangle: Array) -> Color:
	var red := 0.0
	var green := 0.0
	var blue := 0.0
	var count := 0
	var left := int(rectangle[0])
	var top := int(rectangle[1])
	var right := left + int(rectangle[2])
	var bottom := top + int(rectangle[3])
	for y: int in range(top, bottom):
		for x: int in range(left, right):
			var pixel := image.get_pixel(x, y)
			red += pixel.r
			green += pixel.g
			blue += pixel.b
			count += 1
	return Color(red / count, green / count, blue / count, 1.0)


func _actor_diagnostics(actor: ReplicatedActor3D) -> Dictionary:
	var equipment_meshes := 0
	var mesh_instances := 0
	for child: Node in actor.find_children("*", "MeshInstance3D", true, false):
		mesh_instances += 1
		if child.has_meta("native_equipment"):
			equipment_meshes += 1
	var poses := {}
	var skeleton := actor.get_skeleton()
	if skeleton != null:
		for bone_name: String in ["Root", "spine_03", "Head", "hand_r", "hand_l"]:
			var bone := skeleton.find_bone(bone_name)
			if bone >= 0:
				poses[bone_name] = _transform_values(skeleton.get_bone_global_pose(bone))
	var pose_text := JSON.stringify(poses)
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(pose_text.to_utf8_buffer())
	var cape_active := false
	if skeleton != null:
		var cape := skeleton.get_node_or_null("CapeCloth") as SkeletonModifier3D
		cape_active = cape != null and cape.active
	return {
		"name": actor.name,
		"action": str(actor.current_action),
		"animation": actor.animation_player.current_animation
			if actor.animation_player != null else "",
		"animationPosition": _rounded(actor.animation_player.current_animation_position)
			if actor.animation_player != null else -1.0,
		"meshInstances": mesh_instances,
		"nativeEquipmentMeshes": equipment_meshes,
		"capeClothActive": cape_active,
		"selectedBonePoseSha256": context.finish().hex_encode(),
	}


func _transform_values(value: Transform3D) -> Array[float]:
	return [
		_rounded(value.basis.x.x), _rounded(value.basis.x.y), _rounded(value.basis.x.z),
		_rounded(value.basis.y.x), _rounded(value.basis.y.y), _rounded(value.basis.y.z),
		_rounded(value.basis.z.x), _rounded(value.basis.z.y), _rounded(value.basis.z.z),
		_rounded(value.origin.x), _rounded(value.origin.y), _rounded(value.origin.z),
	]


func _rounded(value: float) -> float:
	return snappedf(value, 0.000001)


func _rect(centre: Vector2, half_size: Vector2) -> Array[int]:
	var left := clampi(roundi(centre.x - half_size.x), 0, SCREEN_SIZE.x - 1)
	var top := clampi(roundi(centre.y - half_size.y), 0, SCREEN_SIZE.y - 1)
	var right := clampi(roundi(centre.x + half_size.x), left + 1, SCREEN_SIZE.x)
	var bottom := clampi(roundi(centre.y + half_size.y), top + 1, SCREEN_SIZE.y)
	return [left, top, right - left, bottom - top]


func _bounds(a: Vector2, b: Vector2, padding: Vector2) -> Array[int]:
	var left := clampi(floori(minf(a.x, b.x) - padding.x), 0, SCREEN_SIZE.x - 1)
	var top := clampi(floori(minf(a.y, b.y) - padding.y), 0, SCREEN_SIZE.y - 1)
	var right := clampi(ceili(maxf(a.x, b.x) + padding.x), left + 1, SCREEN_SIZE.x)
	var bottom := clampi(ceili(maxf(a.y, b.y) + padding.y), top + 1, SCREEN_SIZE.y)
	return [left, top, right - left, bottom - top]


func _colour_count(image: Image) -> int:
	var colours := {}
	for y: int in range(0, image.get_height(), 6):
		for x: int in range(0, image.get_width(), 6):
			var colour: Color = image.get_pixel(x, y)
			colours[Color8(roundi(colour.r * 255.0), roundi(colour.g * 255.0),
				roundi(colour.b * 255.0), 255)] = true
	return colours.size()


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false

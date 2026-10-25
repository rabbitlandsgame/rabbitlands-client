extends SceneTree
## Offline visual acceptance scenes using the production actor/import paths.
const Preview = preload("res://src/world/terrain_target_preview.gd")
var stage: Node3D
var camera: Camera3D
var directory := ""
var actors: Array[ReplicatedActor3D] = []
var registry: Dictionary
func _init() -> void: run.call_deferred()
func title(text: String) -> void:
	var label := Label.new()
	label.text = text
	label.position = Vector2(24, 18)
	label.add_theme_font_size_override("font_size", 23)
	label.add_theme_color_override("font_color", Color.WHITE)
	root.add_child(label)
func scene() -> void:
	for node: Node in root.get_children():
		if node == stage or node is Label:
			node.queue_free()
	actors.clear()
	stage = Node3D.new()
	root.add_child(stage)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-50, -35, 0)
	light.light_energy = 1.5
	stage.add_child(light)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color("28393e")
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color("c9d3ce")
	env.environment.ambient_light_energy = .65
	stage.add_child(env)
	camera = Camera3D.new()
	camera.fov = 38
	camera.cull_mask = 1 | (1 << 19)
	stage.add_child(camera)
	camera.position = Vector3(8, 12, 14)
	camera.look_at(Vector3.ZERO)
	camera.current = true
func surface(p: Vector3) -> Variant:
	if p.x > 5: return null
	return Vector3(p.x, .23 * p.z + (1.4 if p.x > 1.5 else 0), p.z)
func ground(mesh: Mesh, color: Color) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.mesh = mesh
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 1.0
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	node.material_override = material
	stage.add_child(node)
	return node
func flat_ground() -> void:
	var mesh := PlaneMesh.new()
	mesh.size = Vector2(40, 32)
	ground(mesh, Color("697964"))
func actor(key: String, at: Vector3, rank := 0) -> ReplicatedActor3D:
	var config: Dictionary = registry.models[key]
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var value := ReplicatedActor3D.new()
	stage.add_child(value)
	var dto := {"actor_id": 2000 + actors.size(), "kind": 5, "name": key.replace("_", " "),
		"x": 0, "y": 0, "rotation": 0, "health": 100, "max_health": 100, "boss_rank": rank,
		"appearance": {}, "equipment_visuals": {}}
	var errors := value.configure(dto, CoordinateAdapter.new({}), config, mapping)
	if not errors.is_empty(): push_error(str(errors))
	value.set_physics_process(false)
	value.position = at
	value.rotation.y = .4
	if value.animation_player != null:
		value.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		value.animation_player.advance(.3)
	actors.append(value)
	return value
func capture(name: String) -> void:
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var error := image.save_png(directory.path_join(name + ".png"))
	assert(error == OK)
	print("RENDERED_CAPTURE ", name)
func run() -> void:
	Engine.max_fps = 60
	directory = OS.get_environment("RL_CORRECTNESS_OUT")
	assert(not directory.is_empty())
	DirAccess.make_dir_recursive_absolute(directory)
	root.size = Vector2i(1280, 720)
	root.get_node("Network").call("block_for_hud_preview")
	registry = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	scene()
	title("Spell footprint: slope, raised ground and missing edge")
	ground(Preview.build(Vector3.ZERO, 14, surface, .25), Color("7d6b50"))
	var footprint := ground(Preview.build(Vector3.ZERO, 9, surface, .25), Color(.2, .75, 1, .6))
	var material := footprint.material_override as StandardMaterial3D
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	footprint.position.y = .04
	await capture("terrain-footprint")
	scene()
	title("Boss rank stays readable when ordinary creature banners declutter")
	flat_ground()
	for z: int in 4:
		for x: int in 8:
			var rank := 2 if Vector2i(x, z) == Vector2i(3, 1) else (1 if Vector2i(x, z) == Vector2i(5, 2) else 0)
			var value := actor("rabbit", Vector3(x * 1.5 - 5.25, 0, z * 1.5 - 2.25), rank)
			value.set_overhead_crowded(true)
	await capture("boss-crowd")
	scene()
	title("Current imported models at gameplay distance: player, Tengu, rat, wasp")
	flat_ground()
	var names := ["luminous_male", "luminous_female", "tengu", "giant_rat", "giant_wasp"]
	for index: int in names.size(): actor(names[index], Vector3(index * 3.1 - 6.2, 0, 0))
	camera.size = 18
	camera.position = Vector3(5, 8, 14)
	camera.look_at(Vector3(0, 1, 0))
	await capture("art-idle")
	for value: ReplicatedActor3D in actors:
		value.play_action(&"walk")
		for frame: int in 18: value.animation_player.advance(1.0 / 60)
	await capture("art-travel")
	for value: ReplicatedActor3D in actors:
		value.play_action(&"attack_primary", true)
		for frame: int in 21: value.animation_player.advance(1.0 / 60)
	await capture("art-attack")
	# A dense sequence around actual player attack recovery, at 240Hz.
	for value: ReplicatedActor3D in actors.slice(0, 2):
		value.animation_player.advance(maxf(0, value.animation_player.current_animation_length - .36))
	for sample: int in 8:
		for value: ReplicatedActor3D in actors.slice(0, 2): value.animation_player.advance(1.0 / 240)
		await capture("combat-recovery-%02d" % sample)
	stage.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit()

extends SceneTree
## The embroidery must follow the cape skin and switch on existing and future
## wearers without recolouring cloth or changing shared mesh resources.
const Emblems := preload("res://src/actors/cape_emblems.gd")
var failures := 0
var main: Control
var stage: Node3D
var camera: Camera3D
var artifacts := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path("res://test-artifacts/perk-capes")
	DirAccess.make_dir_recursive_absolute(artifacts)
	root.size = Vector2i(480, 640)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("252c32")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("d9e3e8")
	world.environment.ambient_light_energy = 0.8
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-30, 155, 0)
	light.light_energy = 1.1
	stage.add_child(light)
	camera = Camera3D.new()
	camera.current = true
	camera.cull_mask = 3
	stage.add_child(camera)
	var actor := _spawn(140)
	await _settle(actor)
	var cloth := _embroidered_material(actor)
	_expect(cloth != null, "the cape has embroidered cloth")
	if cloth != null:
		var colour := cloth.albedo_color
		var mesh := _cape_mesh(actor)
		Emblems.set_enabled(false)
		_expect(not cloth.detail_enabled and cloth.albedo_color == colour,
			"existing wearers hide only the emblem")
		await _capture(actor, "gatherer-plain.png")
		var other := _spawn(147)
		_expect(not _embroidered_material(other).detail_enabled,
			"new wearers inherit the preference")
		other.queue_free()
		await process_frame
		Emblems.set_enabled(true)
		_expect(cloth.detail_enabled and _cape_mesh(actor) == mesh,
			"switching back preserves the skinned mesh")
	actor.queue_free()
	await process_frame
	for visual: int in range(140, 150):
		actor = _spawn(visual)
		await _settle(actor)
		_expect(_embroidered_material(actor) != null, "visual %d has an emblem" % visual)
		await _capture(actor, "cape-%d.png" % visual)
		actor.queue_free()
		await process_frame
	main.queue_free()
	await process_frame
	print("perk capes: %s" % ("PASS" if failures == 0 else "FAIL"))
	quit(failures)

func _spawn(visual: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var model: Dictionary = (main.get("models") as Dictionary)["luminous_male"]
	actor.configure({"actor_id": 8200 + visual, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "", "appearance": {}, "equipment_visuals": {"2": visual}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), model,
		main.call("_animation_for_model", model), main.get("equipment_config"))
	actor.server_target = Vector3.ZERO
	actor.global_position = Vector3.ZERO
	actor.rotation.y = 0
	actor.play_action(&"idle")
	return actor

func _cape_mesh(actor: ReplicatedActor3D) -> Mesh:
	for node: Node in (actor.get("_equipment_nodes") as Dictionary).get(2, []):
		if node is MeshInstance3D:
			return (node as MeshInstance3D).mesh
	return null

func _embroidered_material(actor: ReplicatedActor3D) -> StandardMaterial3D:
	for node: Node in (actor.get("_equipment_nodes") as Dictionary).get(2, []):
		if not node is MeshInstance3D:
			continue
		var mesh := node as MeshInstance3D
		for surface: int in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface) as StandardMaterial3D
			if material != null and material.detail_albedo != null:
				return material
	return null

func _settle(actor: ReplicatedActor3D) -> void:
	for frame: int in range(15):
		await process_frame
	var cloth := actor.get("_cape_cloth") as Node
	if cloth != null:
		for step: int in range(120):
			cloth.call("_process_modification_with_delta", 1.0 / 60.0)
	await process_frame

func _capture(actor: ReplicatedActor3D, filename: String) -> void:
	camera.position = Vector3(0, 1.05, 2.8)
	camera.look_at(Vector3(0, 1.0, 0))
	for frame: int in range(3):
		await process_frame
	if DisplayServer.get_name() != "headless":
		var picture := root.get_texture().get_image()
		_expect(picture != null and picture.save_png(artifacts.path_join(filename)) == OK,
			"saved %s" % filename)

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

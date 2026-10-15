extends SceneTree
## Ray-test the actual imported stone footings, including their outer corners.

var failures := 0
var checked := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var loader := WorldLoader.new()
	root.add_child(loader)
	loader.load_world("res://../eloria-assets/maps/lantern-reach/world.json")
	expect(loader.world_root != null, "Lantern Reach loads")
	if loader.world_root == null:
		quit(1)
		return
	var lantern = load("res://src/world/lantern_scene.gd").new()
	root.add_child(lantern)
	lantern.configure(loader.world_root, loader.manifest)
	lantern.set_process(false)
	await physics_frame
	await process_frame
	await physics_frame
	var space: PhysicsDirectSpaceState3D = lantern.get_world_3d().direct_space_state
	for gate: Dictionary in lantern.layout.gates:
		var model: Node3D = lantern.get_node(str(gate.id))
		var feet := 0
		for mesh: MeshInstance3D in model.find_children("GatePosts*", "MeshInstance3D", true, false):
			for surface in mesh.mesh.get_surface_count():
				var material := mesh.get_active_material(surface) as BaseMaterial3D
				if material == null or not str(material.resource_name).begins_with("stone"):
					continue
				var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
				var seen := {}
				for vertex: Vector3 in vertices:
					if absf(vertex.y) > .001 or seen.has(vertex):
						continue
					seen[vertex] = true
					var point := mesh.global_transform * vertex
					var height: Variant = GroundDrape.surface_height(space, point.x, point.z)
					expect(height != null, str(gate.id) + " footing has land under " + str(point))
					if height != null:
						expect(point.y - float(height) <= .025, str(gate.id) + " footing floats")
						expect(float(height) - point.y <= .15, str(gate.id) + " footing is buried")
					checked += 1
					feet += 1
		expect(feet == 8, str(gate.id) + " checks four corners on each stone footing")
	lantern.apply_state({"flags": {"crafted": true, "prepared": true, "lit": true}})
	for parts: Array in lantern.gates.values():
		for part: Node3D in parts:
			expect(not part.visible, "Completed gate leaf opens")
	for mesh: Node in lantern.find_children("GatePosts*", "MeshInstance3D", true, false):
		expect(mesh.visible, "Opened gate retains grounded posts")
	print("Lantern gate grounding: %d footing corners, %d failures" % [checked, failures])
	if "--capture-gates" in OS.get_cmdline_user_args():
		await capture_gates(lantern)
	lantern.queue_free()
	loader.queue_free()
	await process_frame
	quit(1 if failures else 0)

func capture_gates(lantern: Node3D) -> void:
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("17363e")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("d1e1e5")
	environment.environment.ambient_light_energy = .65
	root.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_energy = 1.0
	root.add_child(sun)
	var camera := Camera3D.new()
	camera.fov = 48
	root.add_child(camera)
	for id: String in ["beacon_gate", "return_gate"]:
		var gate: Node3D = lantern.get_node(id)
		var fixed := gate.transform
		camera.position = fixed.origin + Vector3(7, 5.5, 10)
		camera.look_at(fixed.origin + Vector3(0, 1, 0))
		for variant: String in ["before", "after"]:
			if variant == "before":
				for definition: Dictionary in lantern.layout.gates:
					if definition.id == id:
						gate.transform = Transform3D(Basis.IDENTITY, lantern._tile(definition.at))
			else:
				gate.transform = fixed
			await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png("res://../../work-output/" + id + "-" + variant + ".png")

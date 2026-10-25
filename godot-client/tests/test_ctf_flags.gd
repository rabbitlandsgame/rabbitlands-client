extends SceneTree
## The two objective flags must be visually distinguishable on existing clients.
var failures := 0
func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)
func run() -> void:
	var colors: Array[Color] = []
	for team: String in ["red", "blue"]:
		var placed := PlacedObject3D.new()
		root.add_child(placed)
		placed.configure({"object_id": 61000, "model": "ctf_%s_flag" % team}, Vector3(4, 0, 8))
		var mesh := placed.get_node("Shape") as MeshInstance3D
		var material := mesh.mesh.surface_get_material(0) as StandardMaterial3D
		colors.append(material.albedo_color)
		expect(PlacedObject3D.shape_name_for(placed.model) == "banner", "CTF reuses the existing banner")
		expect(placed.global_position == Vector3(4, 0, 8), "Flag uses the server's tile position")
		expect(is_zero_approx(mesh.position.y + mesh.mesh.get_aabb().position.y), "Centred banner geometry rests above its ground anchor")
		var labels := placed.find_children("*", "Label3D", false, false)
		expect(labels.size() == 1, "Flag has one readable objective label")
		if labels.size() == 1:
			expect(labels[0].text == team.capitalize() + " flag", "Label names the team without relying on color")
			expect(labels[0].layers == 1 << 19 and labels[0].fixed_size, "Flag label uses the existing world-text overlay layer and fixed size")
			expect(is_equal_approx(labels[0].pixel_size * 4.0, ReplicatedActor3D.OVERHEAD_PIXEL), "Fixed-size objective text uses the existing readable actor-label calibration")
		placed.free()
	expect(colors[0].r > colors[0].b and colors[1].b > colors[1].r, "Red and blue flags have distinct team colors")
	var late := PlacedObject3D.new()
	late.configure({"object_id": 61002, "model": "ctf_red_flag"}, Vector3(40, 2, 40))
	root.add_child(late)
	await physics_frame
	await physics_frame
	expect(is_equal_approx(late.global_position.y, 2.0) and late.is_physics_processing(), "A missing streamed surface preserves fallback height and retains bounded retry")
	var surface := StaticBody3D.new()
	surface.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	surface.collision_mask = 0
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(8, 0.4, 8)
	collision.shape = box
	surface.add_child(collision)
	root.add_child(surface)
	surface.global_position = Vector3(40, 6, 40)
	for frame: int in 90:
		await physics_frame
		if not late.is_physics_processing(): break
	expect(is_equal_approx(late.global_position.y, 6.2), "Late elevated navigation surface replaces the fallback ground height")
	expect(not late.is_physics_processing(), "A grounded object stops all steady-state grounding queries")
	late.free()
	surface.free()
	print("CTF flags: ", failures, " failures")
	quit(failures)

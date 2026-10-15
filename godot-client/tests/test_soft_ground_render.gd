extends SceneTree

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(256,256)
	viewport.own_world_3d = true
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var base := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(4,4)
	base.mesh = plane
	var green := StandardMaterial3D.new()
	green.albedo_color = Color(.15,.5,.1,1)
	green.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	base.material_override = green
	viewport.add_child(base)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-2,.01,-2),Vector3(2,.01,-2),Vector3(2,.01,2),Vector3(-2,.01,2)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP,Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.ONE,Vector2.DOWN])
	arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color(1,1,1,0),Color.WHITE,Color.WHITE,Color(1,1,1,0)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,0,2,3])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	var soil := StandardMaterial3D.new()
	soil.resource_name = "test_soft_ground"
	soil.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	var texture := Image.create(2,2,false,Image.FORMAT_RGBA8)
	texture.fill(Color(.7,.5,.2,1))
	soil.albedo_texture = ImageTexture.create_from_image(texture)
	mesh.surface_set_material(0,soil)
	var overlay := MeshInstance3D.new()
	overlay.mesh = mesh
	viewport.add_child(overlay)
	var loader := WorldLoader.new()
	loader._apply_material_passes([overlay])
	if OS.get_environment("ELORIA_TEST_PAINTED_MASK") == "1":
		overlay.material_override = LookGround.painted_for(soil, LookGround.Kind.PATCH, mesh, 0)
		assert(overlay.material_override != null)
	var light := DirectionalLight3D.new()
	light.rotation_degrees.x = -90
	viewport.add_child(light)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 4.2
	camera.position = Vector3(0,5,0)
	camera.rotation_degrees.x = -90
	viewport.add_child(camera)
	for i in range(10): await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	var transparent := 0
	var green_pixels := 0
	var soil_pixels := 0
	for y in range(20,236):
		for x in range(20,236):
			var pixel := image.get_pixel(x,y)
			if pixel.a < .99: transparent += 1
			if pixel.g > pixel.r * 1.3: green_pixels += 1
			else: soil_pixels += 1
	var success := transparent == 0 and green_pixels > 1000 and soil_pixels > 1000
	print("soft ground rendered: ", "PASS" if success else "FAIL", " transparent=",transparent," grass=",green_pixels," soil=",soil_pixels)
	var output := OS.get_environment("ELORIA_SOFT_GROUND_CAPTURE")
	if not output.is_empty(): image.save_png(output)
	loader.free()
	viewport.queue_free()
	await process_frame
	quit(0 if success else 1)

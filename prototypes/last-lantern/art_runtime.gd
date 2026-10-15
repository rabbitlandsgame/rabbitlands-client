extends RefCounted

## Models are packaged with their textures and selected native animations.
## Repeated actors share meshes, skins and animations; only cloth tint varies.
static var models: Dictionary = {}

static func instantiate(name: String) -> Node3D:
	if not models.has(name):
		var document := GLTFDocument.new()
		var state := GLTFState.new()
		var error := document.append_from_file(ProjectSettings.globalize_path("res://package/models/"+name+".glb"),state)
		assert(error == OK,"Missing authored model: "+name)
		mipmaps(state)
		var root := document.generate_scene(state)
		var packed := PackedScene.new()
		assert(packed.pack(root) == OK,"Could not cache model: "+name)
		root.free()
		models[name] = packed
	var node: Node3D = (models[name] as PackedScene).instantiate()
	for mesh: MeshInstance3D in node.find_children("*","MeshInstance3D",true,false):
		for surface in range(mesh.mesh.get_surface_count()):
			var mat: BaseMaterial3D = mesh.get_active_material(surface) as BaseMaterial3D
			if mat and mat.albedo_texture:
				mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return node

static func mipmaps(state: GLTFState) -> void:
	# Runtime GLB imports do not receive the editor's texture import pass.
	for value: Variant in state.get_images():
		var texture := value as ImageTexture
		if texture == null: continue
		var image := texture.get_image()
		if image == null or image.is_empty() or image.has_mipmaps(): continue
		if image.is_compressed() and image.decompress() != OK: continue
		image.generate_mipmaps()
		texture.set_image(image)

static func person(color: Color) -> Node3D:
	var root := Node3D.new()
	var body := instantiate("traveler")
	body.name = "Model"
	# Native characters face +Z; the preview follows Godot's -Z convention.
	body.rotation.y = PI
	root.add_child(body)
	for mesh: MeshInstance3D in body.find_children("*","MeshInstance3D",true,false):
		if str(mesh.name).begins_with("wardrobe_"):
			for surface in range(mesh.mesh.get_surface_count()):
				var source := mesh.get_active_material(surface) as StandardMaterial3D
				if source:
					var mat: StandardMaterial3D = source.duplicate()
					mat.albedo_color = color if str(mesh.name).begins_with("wardrobe_shirt") else Color("384855")
					if str(mesh.name).begins_with("wardrobe_boots"):
						mat.albedo_color = Color("493529")
					mesh.set_surface_override_material(surface,mat)
	animate(root,"Idle_A")
	return root

static func animate(root: Node3D, clip: String, speed := 1.0) -> void:
	var players := root.find_children("*","AnimationPlayer",true,false)
	if players.is_empty(): return
	var animator: AnimationPlayer = players[0]
	if not animator.has_animation(clip): return
	if animator.current_animation != clip:
		var animation := animator.get_animation(clip)
		animation.loop_mode = Animation.LOOP_LINEAR if clip in ["Idle_A","Walk","Fighting_Idle","Sword_Attack"] else Animation.LOOP_NONE
		animator.play(clip,.18)
	animator.speed_scale = speed

static func water_material(layout: Dictionary) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = load("res://water.gdshader")
	var mask := Image.create(120,120,false,Image.FORMAT_R8)
	for y in range(120):
		for x in range(120):
			mask.set_pixel(x,y,Color.WHITE if int(layout.walkGrid[y*120+x])>0 else Color.BLACK)
	material.set_shader_parameter("land_mask",ImageTexture.create_from_image(mask))
	return material

static func light_beam() -> MeshInstance3D:
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	var apex := Vector3(0,0,0)
	for i in range(12):
		var a := TAU*i/12
		var b := TAU*(i+1)/12
		mesh.surface_set_color(Color(1,.73,.33,.24))
		mesh.surface_add_vertex(apex)
		mesh.surface_set_color(Color(1,.73,.33,0))
		mesh.surface_add_vertex(Vector3(cos(a)*7,sin(a)*2.2,84))
		mesh.surface_set_color(Color(1,.73,.33,0))
		mesh.surface_add_vertex(Vector3(cos(b)*7,sin(b)*2.2,84))
	mesh.surface_end()
	var result := MeshInstance3D.new()
	result.mesh = mesh
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.no_depth_test = false
	result.material_override = material
	result.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return result

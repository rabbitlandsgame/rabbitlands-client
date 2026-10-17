extends RefCounted
## The approved saturated body and gentle glow, shared by spell presentation.
const BODY_SHADER = preload("res://src/world/spell_body.gdshader")
const GLOW_SHADER = preload("res://src/world/spell_energy.gdshader")
static var _materials: Dictionary = {}
static var _particle_textures: Dictionary = {}
static var _glow_texture: GradientTexture2D

static func body_tint(palette: Color) -> Color:
	# Preserve the exact blue selected in the ice-magic review. Other families
	# retain their hue while gaining enough saturation to show on pale ground.
	if palette.to_html(false) in ["76dbff", "8ce5ff"]:
		return Color("1376c4")
	return Color.from_hsv(palette.h,
		maxf(0.72, palette.s) if palette.s > 0.05 else palette.s,
		minf(0.78, palette.v))

static func energy(palette: Color, power: int, radial: bool) -> ShaderMaterial:
	return _material(palette, power, radial, true)

static func geometry(palette: Color, power: int) -> ShaderMaterial:
	return _material(palette, power, false, false)

static func _material(palette: Color, power: int, radial: bool, soft_edges: bool) -> ShaderMaterial:
	var key := "%s:%d:%s:%s" % [palette.to_html(false), power, radial, soft_edges]
	if _materials.has(key):
		return _materials[key]
	# Match the reviewed P5 appearance and keep the existing power progression.
	var brightness := SpellPresentation.power_intensity(power) / SpellPresentation.power_intensity(5)
	var body := ShaderMaterial.new()
	body.shader = BODY_SHADER
	body.set_shader_parameter("tint", body_tint(palette))
	body.set_shader_parameter("radial", radial)
	body.set_shader_parameter("soft_edges", soft_edges)
	body.set_shader_parameter("intensity", brightness)
	if soft_edges:
		var glow := ShaderMaterial.new()
		glow.shader = GLOW_SHADER
		glow.set_shader_parameter("radial", radial)
		glow.set_shader_parameter("intensity", brightness * 0.40)
		glow.render_priority = 1
		body.next_pass = glow
	else:
		var glow := CombatEffectMesh.material()
		glow.albedo_color.a = brightness * 0.40
		glow.render_priority = 1
		body.next_pass = glow
	_materials[key] = body
	return body

static func particle(palette: Color, power: int) -> StandardMaterial3D:
	var brightness := SpellPresentation.power_intensity(power) / SpellPresentation.power_intensity(5)
	var body := StandardMaterial3D.new()
	body.albedo_texture = particle_texture(body_tint(palette))
	body.albedo_color.a = brightness
	body.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	body.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	body.vertex_color_use_as_albedo = true
	body.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	var glow := body.duplicate() as StandardMaterial3D
	glow.albedo_texture = glow_texture()
	glow.albedo_color = Color(palette, brightness * 0.40)
	glow.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	glow.render_priority = 1
	body.next_pass = glow
	return body

static func particle_texture(tint: Color) -> ImageTexture:
	var key := tint.to_html(false)
	if _particle_textures.has(key):
		return _particle_textures[key]
	const SIZE := 96
	var image := Image.create(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	var pale := tint.lerp(Color.WHITE, 0.82)
	for y: int in range(SIZE):
		for x: int in range(SIZE):
			var radius := (Vector2(x, y) / float(SIZE - 1) * 2.0 - Vector2.ONE).length()
			var coverage := pow(maxf(0.0, 1.0 - radius), 0.65)
			var colour := tint.lerp(pale, (1.0 - smoothstep(0.0, 0.20, radius)) * 0.35)
			colour.a = coverage * 0.94
			image.set_pixel(x, y, colour)
	image.generate_mipmaps()
	var texture := ImageTexture.create_from_image(image)
	_particle_textures[key] = texture
	return texture

static func glow_texture() -> GradientTexture2D:
	if _glow_texture != null:
		return _glow_texture
	var falloff := Gradient.new()
	var colours := PackedColorArray()
	var offsets := PackedFloat32Array()
	for sample: int in range(65):
		var radius := float(sample) / 64.0
		colours.append(Color(1.0, 1.0, 1.0, pow(1.0 - radius, 2.6)))
		offsets.append(radius)
	falloff.colors = colours
	falloff.offsets = offsets
	_glow_texture = GradientTexture2D.new()
	_glow_texture.gradient = falloff
	_glow_texture.fill = GradientTexture2D.FILL_RADIAL
	_glow_texture.fill_from = Vector2(0.5, 0.5)
	_glow_texture.fill_to = Vector2(1.0, 0.5)
	_glow_texture.width = 64
	_glow_texture.height = 64
	return _glow_texture

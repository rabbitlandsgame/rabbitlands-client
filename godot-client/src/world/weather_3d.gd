class_name Weather3D
extends Node3D
## The sky the server said is over this map, and the fires burning on it.
##
## `SEND_WEATHER(100)`, `START_RAIN(15)`, `STOP_RAIN(16)`, `THUNDER(17)`,
## `FIRE_PARTICLES(61)` and `REMOVE_FIRE_AT(62)` were all unallocated, so this
## client had a particle system with nothing to point at: no weather to render
## and no emitter to place.
##
## Nothing here decides anything. What is falling and how hard is the server's,
## because two players standing together have to see the same sky; a client
## rolling its own would drift from everyone else's within a minute. Fires are
## placed by name and tile, and a kind this client does not know is drawn as a
## hearth rather than as nothing, because a fire that is there should be
## visible even if its flavour is not.
##
## Everything is built from primitives and generated textures. Nothing is
## imported, traced or converted.

## The rain volume follows the camera, because rain is everywhere and drawing
## it over the whole map would be millions of particles for one visible cubic
## metre.
const RAIN_BOX := Vector3(34.0, 16.0, 34.0)
const RAIN_HEIGHT := 13.0
## At full intensity. Scaled down by what the server said is falling.
const MAX_RAIN_PARTICLES := 1400
const STORM_PARTICLES := 2200

const FIRE_KINDS: Array[String] = ["hearth", "forge", "pyre"]
## Flame colour per kind: a hearth is warm, a forge is white-hot, a pyre burns
## green because that is this world's funeral fire.
const FIRE_COLOURS: Array[Color] = [
	Color(1.0, 0.62, 0.22), Color(1.0, 0.86, 0.55), Color(0.45, 1.0, 0.62)]
const FIRE_SCALES: Array[float] = [1.0, 0.75, 1.5]

var kind := 0
var intensity := 0

var _rain: GPUParticles3D
var _flash: OmniLight3D
var _flash_seconds := 0.0
var _fires: Dictionary = {}

func _ready() -> void:
	name = "Weather"

## What the server said, applied. Intensity is 0-100; a clear sky carries none.
func set_weather(new_kind: int, new_intensity: int) -> void:
	kind = new_kind
	intensity = new_intensity
	if kind <= 0 or intensity <= 0:
		if _rain != null:
			_rain.emitting = false
		return
	if _rain == null:
		_build_rain()
	var ceiling: int = STORM_PARTICLES if kind >= 2 else MAX_RAIN_PARTICLES
	_rain.amount = maxi(60, int(ceiling * clampf(float(intensity) / 100.0,
		0.05, 1.0)))
	var process: ParticleProcessMaterial = _rain.process_material as ParticleProcessMaterial
	# Storm rain falls harder and more slanted than a shower.
	process.initial_velocity_min = 14.0 if kind >= 2 else 9.0
	process.initial_velocity_max = 22.0 if kind >= 2 else 13.0
	process.direction = Vector3(0.55 if kind >= 2 else 0.15, -1.0, 0.2)
	_rain.emitting = true

## One clap. Severity is 1-5 and decides how bright and how long the flash is;
## the sound is the audio director's, from the server's own sound frame.
func strike(severity: int) -> void:
	if _flash == null:
		_flash = OmniLight3D.new()
		_flash.name = "ThunderFlash"
		_flash.omni_range = 220.0
		_flash.light_color = Color(0.86, 0.9, 1.0)
		_flash.position.y = 40.0
		add_child(_flash)
	_flash.light_energy = clampf(float(severity) * 1.6, 1.0, 9.0)
	_flash_seconds = 0.08 + 0.04 * clampf(float(severity), 1.0, 5.0)

## A fire at a tile. Placing the same tile twice replaces it rather than
## stacking two fires in one place.
func place_fire(position: Vector3, fire_kind: int, tile: Vector2i) -> void:
	remove_fire(tile)
	var index: int = fire_kind if fire_kind >= 0 and fire_kind < FIRE_KINDS.size() else 0
	var fire := GPUParticles3D.new()
	fire.name = "Fire_%d_%d" % [tile.x, tile.y]
	fire.amount = 42
	fire.lifetime = 1.3
	fire.draw_pass_1 = _flame_mesh(FIRE_COLOURS[index])
	fire.process_material = _flame_process(FIRE_COLOURS[index], FIRE_SCALES[index])
	fire.position = position
	fire.emitting = true
	add_child(fire)
	var glow := OmniLight3D.new()
	glow.name = "Glow"
	glow.light_color = FIRE_COLOURS[index]
	glow.light_energy = 1.6 * FIRE_SCALES[index]
	glow.omni_range = 9.0 * FIRE_SCALES[index]
	glow.position.y = 1.1
	fire.add_child(glow)
	_fires[tile] = fire

func remove_fire(tile: Vector2i) -> void:
	var existing: Variant = _fires.get(tile)
	if is_instance_valid(existing):
		(existing as Node).queue_free()
	_fires.erase(tile)

func fire_count() -> int:
	return _fires.size()

func has_fire_at(tile: Vector2i) -> bool:
	return _fires.has(tile)

## Every tile this layer currently has a fire on.
func fire_tiles() -> Array:
	return _fires.keys()

func is_raining() -> bool:
	return _rain != null and _rain.emitting

func rain_particles() -> int:
	return _rain.amount if _rain != null else 0

func clear() -> void:
	set_weather(0, 0)
	for tile: Variant in _fires.keys():
		remove_fire(tile as Vector2i)

func _process(delta: float) -> void:
	if _flash_seconds > 0.0:
		_flash_seconds -= delta
		if _flash != null:
			_flash.light_energy = maxf(0.0, _flash.light_energy - delta * 26.0)
			_flash.visible = _flash_seconds > 0.0

## Rain follows the camera rather than the world, so the box that is drawn is
## always the one the player can see. The height is followed too: this map's
## ground sits about thirty metres up, and a box left at y = 0 rained
## underneath it.
func follow(position: Vector3) -> void:
	global_position = position

func _build_rain() -> void:
	_rain = GPUParticles3D.new()
	_rain.name = "Rain"
	_rain.lifetime = 1.4
	_rain.position.y = RAIN_HEIGHT
	_rain.draw_pass_1 = _drop_mesh()
	_rain.process_material = _rain_process()
	add_child(_rain)

func _rain_process() -> ParticleProcessMaterial:
	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	process.emission_box_extents = RAIN_BOX
	process.direction = Vector3(0.15, -1.0, 0.2)
	process.spread = 4.0
	process.initial_velocity_min = 9.0
	process.initial_velocity_max = 13.0
	process.gravity = Vector3(0.0, -22.0, 0.0)
	process.scale_min = 0.7
	process.scale_max = 1.15
	return process

## One drop: a thin vertical quad, so it reads as a streak rather than a dot.
func _drop_mesh() -> Mesh:
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.07, 1.1)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.80, 0.88, 1.0, 0.75)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	# Fixed-Y billboarding keeps a drop upright as the camera turns. Plain
	# billboarding tips it to face the camera, and keep_scale then holds it at
	# a constant size on screen, which turned every drop into a fat capsule
	# whatever its distance.
	material.billboard_mode = BaseMaterial3D.BILLBOARD_FIXED_Y
	mesh.material = material
	return mesh

func _flame_mesh(colour: Color) -> Mesh:
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.5, 0.5)
	var material := StandardMaterial3D.new()
	material.albedo_color = colour
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	material.albedo_texture = _soft_dot()
	mesh.material = material
	return mesh

func _flame_process(colour: Color, scale: float) -> ParticleProcessMaterial:
	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	process.emission_sphere_radius = 0.35 * scale
	process.direction = Vector3(0.0, 1.0, 0.0)
	process.spread = 14.0
	process.initial_velocity_min = 1.1 * scale
	process.initial_velocity_max = 2.3 * scale
	process.gravity = Vector3(0.0, 0.9, 0.0)
	process.scale_min = 0.4 * scale
	process.scale_max = 1.0 * scale
	var fade := Gradient.new()
	fade.set_color(0, Color(colour.r, colour.g, colour.b, 0.95))
	fade.set_color(1, Color(colour.r * 0.6, colour.g * 0.35, colour.b * 0.2, 0.0))
	var ramp := GradientTexture1D.new()
	ramp.gradient = fade
	process.color_ramp = ramp
	return process

## A soft radial dot, generated rather than imported: a bare quad reads as a
## hard square at any camera distance.
func _soft_dot() -> Texture2D:
	var glow := Gradient.new()
	glow.set_color(0, Color(1.0, 1.0, 1.0, 1.0))
	glow.set_color(1, Color(1.0, 1.0, 1.0, 0.0))
	var texture := GradientTexture2D.new()
	texture.gradient = glow
	texture.fill = GradientTexture2D.FILL_RADIAL
	texture.fill_from = Vector2(0.5, 0.5)
	texture.fill_to = Vector2(1.0, 0.5)
	return texture

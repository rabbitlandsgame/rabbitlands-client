class_name HarvestSparkle3D
extends Node3D
## The glitter around a player who is harvesting, after the legacy client's
## ongoing harvesting eye candy: small warm four-pointed flares that wink in
## and out around the harvester's body and drift slowly upwards for as long as
## the run lasts.
##
## It is state, not an event. The server's harvest-state packet starts it and
## stops it, so it cannot be left glittering after the server ends a run for
## its own reasons - moving, a full backpack, combat. Stopping lets the flares
## already in the air finish rather than cutting them off, then frees itself.

## The visual layer the gameplay camera renders; neither map draws it.
const GAMEPLAY_LAYER := 1
const PARTICLE_COUNT := 18
const LIFETIME_SECONDS := 1.6
## The flares fill a hollow cylinder around the body rather than a ball at its
## middle, so they read as surrounding the harvester instead of covering them.
const RING_RADIUS := 0.55
const RING_INNER_RADIUS := 0.22
const COLUMN_HEIGHT := 1.5
const COLUMN_CENTRE := 0.85
const FLARE_SIZE := 0.34
## The approved copper edge and warm gold core stay visible on pale ground.
const COPPER := Color("69400c")
const GOLD := Color("ffe7a0")

static var _flare_texture: ImageTexture
static var _copper_texture: ImageTexture

var _target: WeakRef
var _particles: GPUParticles3D
var _stopping := false
var _time_left := 0.0

## Starts glittering around `target`, and keeps following it.
func configure(target: Node3D) -> void:
	_target = weakref(target)
	_follow()
	_add_particles()

## Whether the flares are around this actor, and still being emitted.
func is_following(target: Node3D) -> bool:
	return not _stopping and _target != null and _target.get_ref() == target

func is_stopping() -> bool:
	return _stopping

## Stops emitting. Flares already alive finish their twinkle, then it frees.
func stop() -> void:
	if _stopping:
		return
	_stopping = true
	_time_left = LIFETIME_SECONDS
	if _particles != null:
		_particles.emitting = false

func _process(delta: float) -> void:
	if _stopping:
		_time_left -= delta
		if _time_left <= 0.0:
			queue_free()
		return
	if _target == null or not is_instance_valid(_target.get_ref()):
		# The actor went away - a map change, a despawn - before the server
		# said the run was over.
		stop()
		return
	_follow()

func _follow() -> void:
	var target: Node3D = _target.get_ref() as Node3D if _target != null else null
	if is_instance_valid(target) and is_inside_tree():
		global_position = target.global_position

func _add_particles() -> void:
	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_RING
	process.emission_ring_axis = Vector3.UP
	process.emission_ring_radius = RING_RADIUS
	process.emission_ring_inner_radius = RING_INNER_RADIUS
	process.emission_ring_height = COLUMN_HEIGHT
	process.direction = Vector3.UP
	process.spread = 35.0
	process.initial_velocity_min = 0.05
	process.initial_velocity_max = 0.30
	# A faint lift and a slow swirl around the body; the flares hang rather
	# than fly.
	process.gravity = Vector3(0.0, 0.18, 0.0)
	process.tangential_accel_min = 0.1
	process.tangential_accel_max = 0.35
	process.damping_min = 0.2
	process.damping_max = 0.5
	process.angle_min = 0.0
	process.angle_max = 90.0
	process.angular_velocity_min = -40.0
	process.angular_velocity_max = 40.0
	process.scale_min = 0.55
	process.scale_max = 1.15

	# The twinkle: each flare swells, dims, flares again and goes out.
	var twinkle := Curve.new()
	twinkle.add_point(Vector2(0.0, 0.0))
	twinkle.add_point(Vector2(0.18, 1.0))
	twinkle.add_point(Vector2(0.42, 0.35))
	twinkle.add_point(Vector2(0.64, 0.9))
	twinkle.add_point(Vector2(1.0, 0.0))
	var twinkle_texture := CurveTexture.new()
	twinkle_texture.curve = twinkle
	process.scale_curve = twinkle_texture

	var fade := Gradient.new()
	fade.set_color(0, Color(1.0, 1.0, 1.0, 0.0))
	fade.set_color(1, Color(1.0, 1.0, 1.0, 0.0))
	fade.add_point(0.15, Color(1.0, 1.0, 1.0, 1.0))
	fade.add_point(0.42, Color(1.0, 1.0, 1.0, 0.45))
	fade.add_point(0.66, Color(1.0, 1.0, 1.0, 0.95))
	var fade_texture := GradientTexture1D.new()
	fade_texture.gradient = fade
	process.color_ramp = fade_texture

	# The texture owns the copper/gold palette. Retain the initial-ramp path
	# with a neutral color so the seeded particle motion matches the review.
	var initial := Gradient.new()
	initial.set_color(0, Color.WHITE)
	initial.set_color(1, Color.WHITE)
	var initial_texture := GradientTexture1D.new()
	initial_texture.gradient = initial
	process.color_initial_ramp = initial_texture

	var flare := StandardMaterial3D.new()
	flare.albedo_texture = _copper_flare()
	flare.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	flare.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	flare.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
	flare.vertex_color_use_as_albedo = true
	# Particle billboarding, so the flare's own spin is kept.
	flare.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	# The colored body supplies contrast on snow; the original soft star adds
	# a restrained gold glow. Both passes share the particle's fade and spin.
	var glow := flare.duplicate() as StandardMaterial3D
	glow.albedo_texture = _flare()
	glow.albedo_color = Color(1.0, 0.82, 0.32, 0.32)
	glow.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	glow.render_priority = 1
	flare.next_pass = glow
	var quad := QuadMesh.new()
	quad.size = Vector2(FLARE_SIZE, FLARE_SIZE)
	quad.material = flare

	_particles = GPUParticles3D.new()
	_particles.name = "HarvestSparkles"
	_particles.amount = PARTICLE_COUNT
	_particles.lifetime = LIFETIME_SECONDS
	_particles.randomness = 0.35
	_particles.explosiveness = 0.0
	_particles.preprocess = LIFETIME_SECONDS * 0.5
	_particles.process_material = process
	_particles.draw_pass_1 = quad
	_particles.layers = GAMEPLAY_LAYER
	_particles.position = Vector3.UP * COLUMN_CENTRE
	_particles.visibility_aabb = AABB(Vector3(-1.5, -1.5, -1.5), Vector3(3.0, 4.0, 3.0))
	_particles.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_particles)
	_particles.emitting = true

## Review option B: preserve the four-point silhouette with a copper edge.
## Cache the texture so restarting a harvest never rebuilds it.
static func _copper_flare() -> ImageTexture:
	if _copper_texture != null:
		return _copper_texture
	var image := _flare().get_image()
	for y: int in range(image.get_height()):
		for x: int in range(image.get_width()):
			var mask := image.get_pixel(x, y).a
			var tint := COPPER.lerp(GOLD, smoothstep(0.08, 0.85, mask))
			tint.a = pow(mask, 0.65) * 0.94
			image.set_pixel(x, y, tint)
	image.generate_mipmaps()
	_copper_texture = ImageTexture.create_from_image(image)
	return _copper_texture

## A soft four-pointed star: a round glow crossed by two thin rays, generated
## rather than imported. A bare quad reads as a hard square, and a round dot
## alone reads as dust rather than glitter.
static func _flare() -> ImageTexture:
	if _flare_texture != null:
		return _flare_texture
	const SIZE := 48
	var image := Image.create(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	var half := (SIZE - 1) * 0.5
	for y: int in SIZE:
		for x: int in SIZE:
			var dx := absf(x - half) / half
			var dy := absf(y - half) / half
			var glow := pow(maxf(0.0, 1.0 - sqrt(dx * dx + dy * dy)), 2.4)
			var rays := maxf(
				pow(maxf(0.0, 1.0 - dx), 3.0) * pow(maxf(0.0, 1.0 - dy * 9.0), 2.0),
				pow(maxf(0.0, 1.0 - dy), 3.0) * pow(maxf(0.0, 1.0 - dx * 9.0), 2.0))
			var alpha := clampf(glow * 0.9 + rays, 0.0, 1.0)
			image.set_pixel(x, y, Color(1.0, 1.0, 1.0, alpha))
	_flare_texture = ImageTexture.create_from_image(image)
	return _flare_texture

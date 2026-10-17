class_name PresentationEffects
extends Node3D
## A map's `environment.presentation` mist and gulls, around the camera.
##
## Packages have declared presentation effects since the Nymara regions were
## authored (groundMist, mist, gulls, spray, wisps...) and nothing read them.
## This reads two of them, in the one form that needs no more than the
## manifest gives:
##   "mist":  {"enabled": true, "density": 0..1}
##   "gulls": {"enabled": true, "density": 0..1}
## Each is map-wide: it lives in a volume that follows the camera's focus, as
## the rain does (Weather3D), because the manifest gives no geometry for where
## else it would be. An entry that names `zones` (every Nymara one) is left
## alone: a zone is an area the manifest names but does not draw, and placing
## it by guess would be inventing scenery, as AmbientAudioBinder says of its
## regions. Its reader is still to come.
##
## Mist lies on the ground at dawn, dusk and night and in rain, in the haze's
## own colour, so it reads as the far fog come close. Gulls wheel overhead by
## day and keep off in a storm. Both are built from primitives: nothing is
## imported.

const MIST_BOX := Vector3(80.0, 1.6, 80.0)
## Particles at full density.
const MIST_PARTICLES := 150
const MIST_SIZE := Vector2(14.0, 24.0)
## The most a mist puff covers at full strength. It is many faint, wide
## layers over the whole view: fewer, denser puffs in a smaller box gathered
## into one bright cloud round the player, which read as a spotlight.
const MIST_ALPHA := 0.1
## The mist is the haze come close, a little darker so it lies on the ground
## rather than glowing on it.
const MIST_SHADE := 0.88
const GULLS_MAX := 9
## Gulls circle this high above the focus, this far out.
const GULL_HEIGHT := Vector2(14.0, 26.0)
const GULL_RADIUS := Vector2(14.0, 34.0)
const GULL_SPAN := 1.25

var mist_density := 0.0
var gull_density := 0.0

var _mist: GPUParticles3D
var _mist_material: StandardMaterial3D
var _mist_strength := -1.0
var _gulls: MultiMeshInstance3D
var _gull_paths: Array[Dictionary] = []
var _gull_centre := Vector3.INF
var _gull_strength := 0.0
var _time := 0.0

func _ready() -> void:
	name = "PresentationEffects"

## Reads the manifest's presentation block. A map with none (or only zoned
## entries) has no mist and no gulls.
func bind(manifest: WorldManifest) -> void:
	mist_density = 0.0
	gull_density = 0.0
	var environment: Variant = manifest.data.get("environment") if manifest != null else null
	var presentation: Variant = (environment as Dictionary).get("presentation") \
		if environment is Dictionary else null
	if presentation is Dictionary:
		mist_density = _density((presentation as Dictionary).get("mist"))
		gull_density = _density((presentation as Dictionary).get("gulls"))
	if mist_density > 0.0 and _mist == null:
		_build_mist()
	if gull_density > 0.0 and _gulls == null:
		_build_gulls()
	if _mist != null:
		# It keeps drifting whether or not it is drawn, so it is already there
		# when the evening comes rather than filling in over its lifetime.
		_mist.amount = maxi(8, int(MIST_PARTICLES * mist_density))
		_mist.emitting = mist_density > 0.0
		_mist.visible = false
		_mist_strength = -1.0
	if _gulls != null:
		_gulls.multimesh.visible_instance_count = int(round(GULLS_MAX * gull_density))
		_gulls.visible = false
		_gull_centre = Vector3.INF

## A declared map-wide effect's density, or 0 for none, a disabled one or a
## zoned one.
static func _density(entry: Variant) -> float:
	if entry is not Dictionary:
		return 0.0
	var declared: Dictionary = entry
	if not bool(declared.get("enabled", false)) or declared.has("zones"):
		return 0.0
	return clampf(float(declared.get("density", 1.0)), 0.0, 1.0)

## How thick the mist is at `minute` under `overcast`, 0..1 of its density.
static func mist_strength(minute: float, overcast: float) -> float:
	var light := DayNightBinder.daylight(minute)
	return clampf(maxf(1.0 - smoothstep(0.25, 0.65, light), overcast * 0.8), 0.0, 1.0)

## How many of the gulls are out at `minute` under `overcast`, 0..1.
static func gull_strength(minute: float, overcast: float) -> float:
	var light := DayNightBinder.daylight(minute)
	return clampf(smoothstep(0.2, 0.45, light) * (1.0 - smoothstep(0.55, 0.85, overcast)), 0.0, 1.0)

## Every frame: the mist and the gulls follow the camera's focus, at the hour
## and under the weather. `haze` is the fog's current colour. `particles`
## false (the player's particle switch) draws no mist.
func update(focus: Vector3, minute: float, overcast: float, haze: Color, delta: float,
		particles := true) -> void:
	_time += delta
	if _mist != null and mist_density > 0.0:
		var strength := mist_strength(minute, overcast) if particles else 0.0
		_mist.global_position = focus + Vector3(0.0, MIST_BOX.y * 0.5, 0.0)
		_mist.visible = strength > 0.02
		if not is_equal_approx(strength, _mist_strength) or not is_equal_approx(_mist_material.albedo_color.r, haze.r * MIST_SHADE):
			_mist_strength = strength
			_mist_material.albedo_color = Color(haze.r * MIST_SHADE, haze.g * MIST_SHADE,
				haze.b * MIST_SHADE, MIST_ALPHA * strength * mist_density)
	if _gulls != null and gull_density > 0.0:
		_update_gulls(focus, gull_strength(minute, overcast), delta)

func _update_gulls(focus: Vector3, strength: float, delta: float) -> void:
	_gull_strength = move_toward(_gull_strength, strength, delta * 0.25)
	var count := int(round(GULLS_MAX * gull_density * _gull_strength))
	_gulls.visible = count > 0
	if count <= 0:
		return
	# The flock drifts after the player rather than snapping to them.
	if _gull_centre == Vector3.INF or _gull_centre.distance_to(focus) > 200.0:
		_gull_centre = focus
	_gull_centre = _gull_centre.lerp(focus, minf(1.0, delta * 0.15))
	var multimesh := _gulls.multimesh
	multimesh.visible_instance_count = count
	for index: int in count:
		multimesh.set_instance_transform(index, gull_transform(_gull_paths[index], _time, _gull_centre))

## Where one gull is at `time` on its circle round `centre`: facing along the
## circle, banked into the turn, bobbing a little.
static func gull_transform(path: Dictionary, time: float, centre: Vector3) -> Transform3D:
	var angle: float = float(path.phase) + time * float(path.speed)
	var radius: float = float(path.radius)
	var bob := sin(time * 0.7 + float(path.phase) * 3.0) * 1.2
	var at := centre + Vector3(cos(angle) * radius, float(path.height) + bob, sin(angle) * radius)
	var ahead := Vector3(-sin(angle), 0.0, cos(angle)) * signf(float(path.speed))
	var basis := Basis.looking_at(ahead, Vector3.UP).rotated(ahead.normalized(),
		0.35 * signf(float(path.speed)))
	return Transform3D(basis, at)

## The flock's circles, for a test or a capture to read.
func gull_paths() -> Array[Dictionary]:
	return _gull_paths

func _build_mist() -> void:
	_mist = GPUParticles3D.new()
	_mist.name = "Mist"
	_mist.lifetime = 14.0
	_mist.preprocess = 14.0
	_mist.local_coords = false
	_mist.visibility_aabb = AABB(-MIST_BOX * 1.5, MIST_BOX * 3.0)
	_mist.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	process.emission_box_extents = MIST_BOX
	process.direction = Vector3(1.0, 0.0, 0.3)
	process.spread = 40.0
	process.initial_velocity_min = 0.2
	process.initial_velocity_max = 0.6
	process.gravity = Vector3.ZERO
	process.scale_min = MIST_SIZE.x / MIST_SIZE.y
	process.scale_max = 1.0
	var fade := Gradient.new()
	fade.set_color(0, Color(1, 1, 1, 0))
	fade.add_point(0.3, Color(1, 1, 1, 1))
	fade.add_point(0.7, Color(1, 1, 1, 1))
	fade.set_color(fade.get_point_count() - 1, Color(1, 1, 1, 0))
	var ramp := GradientTexture1D.new()
	ramp.gradient = fade
	process.color_ramp = ramp
	_mist.process_material = process
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * MIST_SIZE.y
	_mist_material = StandardMaterial3D.new()
	_mist_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_mist_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_mist_material.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	_mist_material.vertex_color_use_as_albedo = true
	_mist_material.albedo_texture = _soft_dot()
	_mist_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	# Soft where a puff meets the ground or a wall, never a hard line.
	_mist_material.proximity_fade_enabled = true
	_mist_material.proximity_fade_distance = 2.5
	_mist_material.disable_fog = true
	quad.material = _mist_material
	_mist.draw_pass_1 = quad
	add_child(_mist)

func _build_gulls() -> void:
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = _gull_mesh()
	multimesh.instance_count = GULLS_MAX
	_gulls = MultiMeshInstance3D.new()
	_gulls.name = "Gulls"
	_gulls.multimesh = multimesh
	_gulls.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# They wheel round the focus, so their box is the whole flock's.
	_gulls.custom_aabb = AABB(Vector3(-300, -50, -300), Vector3(600, 200, 600))
	add_child(_gulls)
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for index: int in GULLS_MAX:
		_gull_paths.append({"phase": rng.randf() * TAU,
			"speed": rng.randf_range(0.18, 0.32) * (1.0 if rng.randf() < 0.7 else -1.0),
			"radius": rng.randf_range(GULL_RADIUS.x, GULL_RADIUS.y),
			"height": rng.randf_range(GULL_HEIGHT.x, GULL_HEIGHT.y)})

## A gull: a slim body and two swept wings with dark tips, flapped in the
## vertex shader so a flock costs one draw.
func _gull_mesh() -> ArrayMesh:
	var half := GULL_SPAN * 0.5
	var white := Color(0.94, 0.94, 0.92)
	var grey := Color(0.62, 0.64, 0.68)
	var tip := Color(0.12, 0.12, 0.14)
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	# Wing triangles: root leading edge, root trailing edge, tip; each side.
	for side: float in [-1.0, 1.0]:
		vertices.append_array([Vector3(0.04 * side, 0.0, -0.12), Vector3(0.04 * side, 0.0, 0.1),
			Vector3(half * 0.55 * side, 0.03, -0.02)])
		colours.append_array([grey, grey, grey])
		vertices.append_array([Vector3(half * 0.55 * side, 0.03, -0.02), Vector3(0.04 * side, 0.0, 0.1),
			Vector3(half * side, -0.02, 0.12)])
		colours.append_array([grey, grey, tip])
	# Body: a thin diamond nose to tail.
	vertices.append_array([Vector3(0.0, 0.0, -0.32), Vector3(-0.05, 0.0, 0.0), Vector3(0.0, 0.0, 0.3)])
	colours.append_array([white, white, white])
	vertices.append_array([Vector3(0.0, 0.0, -0.32), Vector3(0.0, 0.0, 0.3), Vector3(0.05, 0.0, 0.0)])
	colours.append_array([white, white, white])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colours
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var material := ShaderMaterial.new()
	material.shader = preload("res://src/world/gull_flight.gdshader")
	mesh.surface_set_material(0, material)
	return mesh

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

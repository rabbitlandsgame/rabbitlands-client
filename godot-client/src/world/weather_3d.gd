class_name Weather3D
extends Node3D
## The sky the server said is over this map, and the fires burning on it.
##
## `SEND_WEATHER(100)`, `START_RAIN(15)`, `STOP_RAIN(16)`, `THUNDER(17)`,
## `FIRE_PARTICLES(61)` and `REMOVE_FIRE_AT(62)` were all unallocated, so this
## client had a particle system with nothing to point at: no weather to render
## and no emitter to place.
##
## Nothing here decides anything. What the sky is and what it is becoming is
## the server's, because two players standing together have to see the same
## sky; a client rolling its own would drift from everyone else's within a
## minute. Fires are placed by name and tile, and a kind this client does not
## know is drawn as a hearth rather than as nothing, because a fire that is
## there should be visible even if its flavour is not.
##
## The sky is a look: what falls (none, rain, snow, ash, sand) and six amounts,
## 0..1 - precipitation, clouds, fog, darkness, wind and lightning. A
## weather_state_v1 server sends the look the sky has now and the one it is
## becoming, with the seconds left (`set_state`); this eases what it shows from
## one to the other over that time. A server that only speaks the legacy
## clear/rain/storm pair is drawn as the nearest look (`set_weather`).
## WeatherSky turns the shown look into light (main `_lighting_manifest`);
## the precipitation is drawn here, in a box that follows the camera.
##
## Everything is built from primitives and generated textures. Nothing is
## imported, traced or converted.

## The amounts of a look, in the order the wire sends them after the kind.
const AMOUNTS: Array[String] = ["precipitation", "clouds", "fog", "darkness", "wind", "lightning"]
const FALLS: Array[String] = ["none", "rain", "snow", "ash", "sand"]

## The precipitation volume follows the camera, because rain is everywhere and
## drawing it over the whole map would be millions of particles for one
## visible cubic metre.
const RAIN_BOX := Vector3(34.0, 16.0, 34.0)
const RAIN_HEIGHT := 13.0
## Particles at full precipitation, per kind: the most that is ever drawn.
## What falls is a share of it (amount_ratio), so a change of intensity never
## restarts the system. LOW graphics quality draws half.
const CAPACITY := {"rain": 2200, "snow": 1600, "ash": 1200, "sand": 1800}
const LOW_QUALITY_SHARE := 0.5

## How a legacy pair is drawn: the server's own light_rain, heavy_rain and
## thunderstorm at full intensity (weather.txt), scaled so the rain falls as
## hard as the pair says - what a weather_state_v1 server would have sent.
const LEGACY_LIGHT_RAIN: Array[float] = [0.35, 0.85, 0.22, 0.30, 0.30, 0.0]
const LEGACY_HEAVY_RAIN: Array[float] = [0.85, 1.0, 0.40, 0.45, 0.55, 0.0]
const LEGACY_STORM: Array[float] = [1.0, 1.0, 0.45, 0.60, 0.85, 0.70]
## A legacy change has no time of its own; it eases over this.
const LEGACY_EASE_SECONDS := 5.0

const FIRE_KINDS: Array[String] = ["hearth", "forge", "pyre"]
## Flame colour per kind: a hearth is warm, a forge is white-hot, a pyre burns
## green because that is this world's funeral fire.
const FIRE_COLOURS: Array[Color] = [
	Color(1.0, 0.62, 0.22), Color(1.0, 0.86, 0.55), Color(0.45, 1.0, 0.62)]
const FIRE_SCALES: Array[float] = [1.0, 0.75, 1.5]

## The legacy pair last applied (0 clear, 1 rain, 2 storm), for callers that
## still read it.
var kind := 0
var intensity := 0
## Bumped whenever the shown look moves, so main re-applies the light only
## while it does.
var look_version := 0
## The state's name as the server sent it ("" from a legacy server).
var state_name := ""

var _from := PackedFloat32Array([0, 0, 0, 0, 0, 0])
var _to := PackedFloat32Array([0, 0, 0, 0, 0, 0])
var _shown := PackedFloat32Array([0, 0, 0, 0, 0, 0])
var _from_fall := 0
var _to_fall := 0
var _ease_seconds := 0.0
var _ease_elapsed := 0.0
var _draw := true
var _falls: Dictionary = {}
var _flash: OmniLight3D
var _flash_seconds := 0.0
var _fires: Dictionary = {}

func _ready() -> void:
	name = "Weather"

## The whole sky from a weather_state_v1 server: `current` is the look it has
## now, `target` the one it is becoming, `seconds` the time left (each look is
## the kind then six amounts 0-100, as the wire carries them). `snap` (a sky met
## on arrival) starts from `current`; otherwise the change eases from what is
## shown, so a player who watched the last change never sees a jump.
func set_state(current: Array, target: Array, seconds: float, draw := true,
		snap := false, server_name := "") -> void:
	state_name = server_name
	_draw = draw
	if snap:
		_shown = _amounts(current)
		_from_fall = int(current[0]) if current.size() > 0 else 0
	else:
		_from_fall = _shown_fall()
	_from = _shown.duplicate()
	_to = _amounts(target)
	_to_fall = int(target[0]) if target.size() > 0 else 0
	_ease_seconds = maxf(0.0, seconds)
	_ease_elapsed = 0.0
	var falling := _to_fall > 0 and _to[0] > 0.0
	kind = (2 if _to[5] > 0.0 else 1) if falling else 0
	intensity = int(round(_to[0] * 100.0)) if falling else 0
	if _ease_seconds <= 0.0:
		_finish_ease()
	_update_falls()
	look_version += 1

## What a legacy server said, as the nearest look. Intensity is 0-100; a clear
## sky carries none. `ease` false sets the sky at once (the first sky after
## logging in). The sky follows it whatever `draw_rain` says: the player's
## particle switch turns the drops off, not the weather.
func set_weather(new_kind: int, new_intensity: int, draw_rain := true,
		ease := true) -> void:
	var target: Array = legacy_look(new_kind, new_intensity)
	set_state(target, target, LEGACY_EASE_SECONDS if ease else 0.0, draw_rain,
		not ease)
	kind = new_kind if new_intensity > 0 else 0
	intensity = new_intensity if new_kind > 0 else 0

## The look a legacy (kind, intensity) stands for, as wire numbers.
static func legacy_look(legacy_kind: int, legacy_intensity: int) -> Array:
	if legacy_kind <= 0 or legacy_intensity <= 0:
		return [0, 0, 0, 0, 0, 0, 0]
	var wanted := clampf(float(legacy_intensity) / 100.0, 0.0, 1.0)
	var look: Array[float] = LEGACY_STORM if legacy_kind >= 2 \
		else (LEGACY_LIGHT_RAIN if wanted <= LEGACY_LIGHT_RAIN[0] else LEGACY_HEAVY_RAIN)
	var level := clampf(wanted / look[0], 0.0, 1.0)
	var result: Array = [1]
	for amount: float in look:
		result.append(int(round(amount * level * 100.0)))
	result[1] = int(round(wanted * 100.0))
	return result

## The look shown now: what falls and the six amounts, 0..1.
func look() -> Dictionary:
	var result := {"fall": _shown_fall()}
	for index: int in AMOUNTS.size():
		result[AMOUNTS[index]] = _shown[index]
	return result

## True when the shown sky has any weather in it (wind alone is not).
func has_weather() -> bool:
	for index: int in 4:
		if _shown[index] > 0.001:
			return true
	return _shown[5] > 0.001

## How much the weather darkens the day, for lamps lit in a storm: nothing
## under cloud alone, all of it in a thunderstorm.
func gloom() -> float:
	return smoothstep(0.3, 0.6, _shown[3])

## How much mist the weather lays on the ground (PresentationEffects).
func mistiness() -> float:
	return clampf(maxf(_shown[2], _shown[0] * 0.6), 0.0, 1.0)

## True while the shown look is still easing towards the server's.
func settling() -> bool:
	return _ease_elapsed < _ease_seconds

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

## True when the server says rain is falling and the player draws it (the
## drops may still be fading in or out).
func is_raining() -> bool:
	return _draw and _to_fall == 1 and _to[0] > 0.0

## The drops the rain is heading for, at full ease.
func rain_particles() -> int:
	if not is_raining():
		return 0
	return int(CAPACITY.rain * _to[0] * _quality_share())

## How many particles of a kind (rain, snow, ash, sand) are falling now.
func falling(fall_kind: String) -> int:
	var node: Variant = _falls.get(fall_kind)
	if not is_instance_valid(node) or not (node as GPUParticles3D).emitting:
		return 0
	return int((node as GPUParticles3D).amount * (node as GPUParticles3D).amount_ratio)

func clear() -> void:
	set_weather(0, 0, true, false)
	for tile: Variant in _fires.keys():
		remove_fire(tile as Vector2i)

func _process(delta: float) -> void:
	if settling():
		_ease_elapsed = minf(_ease_seconds, _ease_elapsed + delta)
		var t := _ease_elapsed / _ease_seconds
		for index: int in _shown.size():
			_shown[index] = lerpf(_from[index], _to[index], t)
		if not settling():
			_finish_ease()
		_update_falls()
		look_version += 1
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

func _finish_ease() -> void:
	_shown = _to.duplicate()
	_from = _to.duplicate()
	_from_fall = _to_fall
	_ease_elapsed = _ease_seconds

## What falls while easing: the old kind fading out, the new fading in. One
## kind may be drawn as the other fades, so a change from rain to snow never
## stops the sky falling.
func _fall_amounts() -> Dictionary:
	var amounts := {}
	var t := 1.0 if _ease_seconds <= 0.0 else _ease_elapsed / _ease_seconds
	if _from_fall > 0 and _from_fall < FALLS.size():
		var old: float = _from[0] * (1.0 - t)
		amounts[FALLS[_from_fall]] = old
	if _to_fall > 0 and _to_fall < FALLS.size():
		var new: float = _to[0] * t if _from_fall != _to_fall else lerpf(_from[0], _to[0], t)
		amounts[FALLS[_to_fall]] = new
	return amounts

func _shown_fall() -> int:
	var t := 1.0 if _ease_seconds <= 0.0 else _ease_elapsed / _ease_seconds
	if _to_fall > 0 and (t >= 0.5 or _from_fall == 0):
		return _to_fall
	return _from_fall if _from_fall > 0 else _to_fall

func _update_falls() -> void:
	var amounts := _fall_amounts()
	var wind: float = _shown[4]
	for fall_kind: String in CAPACITY:
		var amount: float = float(amounts.get(fall_kind, 0.0)) if _draw else 0.0
		var node: GPUParticles3D = _falls.get(fall_kind)
		if amount <= 0.001:
			if node != null:
				node.emitting = false
			continue
		if node == null:
			node = _build_fall(fall_kind)
		node.amount_ratio = clampf(amount * _quality_share(), 0.02, 1.0)
		_steer(node, fall_kind, wind, amount)
		node.emitting = true

func _quality_share() -> float:
	return LOW_QUALITY_SHARE if LookProfile.quality() == LookProfile.Quality.LOW else 1.0

## Wind slants what falls; a storm's rain falls harder.
func _steer(node: GPUParticles3D, fall_kind: String, wind: float, amount: float) -> void:
	var process := node.process_material as ParticleProcessMaterial
	match fall_kind:
		"rain":
			process.direction = Vector3(0.15 + 0.6 * wind, -1.0, 0.2)
			process.initial_velocity_min = 9.0 + 5.0 * amount
			process.initial_velocity_max = 13.0 + 9.0 * amount
		"snow", "ash":
			process.direction = Vector3(0.2 + 1.2 * wind, -1.0, 0.25 + 0.4 * wind)
		"sand":
			process.direction = Vector3(1.0, -0.08, 0.35)
			process.initial_velocity_min = 6.0 + 8.0 * wind
			process.initial_velocity_max = 10.0 + 12.0 * wind

func _build_fall(fall_kind: String) -> GPUParticles3D:
	var node := GPUParticles3D.new()
	node.name = fall_kind.capitalize()
	node.amount = int(CAPACITY[fall_kind])
	node.position.y = RAIN_HEIGHT
	node.visibility_aabb = AABB(-RAIN_BOX * 1.6, RAIN_BOX * 3.2)
	var process := ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	process.emission_box_extents = RAIN_BOX
	match fall_kind:
		"rain":
			node.lifetime = 1.4
			node.draw_pass_1 = _drop_mesh()
			process.direction = Vector3(0.15, -1.0, 0.2)
			process.spread = 4.0
			process.initial_velocity_min = 9.0
			process.initial_velocity_max = 13.0
			process.gravity = Vector3(0.0, -22.0, 0.0)
			process.scale_min = 0.7
			process.scale_max = 1.15
		"snow", "ash":
			# Slow and drifting: a flake takes seconds to cross the box.
			node.lifetime = 7.0 if fall_kind == "snow" else 9.0
			node.preprocess = node.lifetime
			node.draw_pass_1 = _flake_mesh(Color(0.96, 0.97, 1.0, 0.9) if fall_kind == "snow"
				else Color(0.36, 0.34, 0.33, 0.85), 0.11 if fall_kind == "snow" else 0.08)
			process.spread = 28.0
			process.initial_velocity_min = 1.2 if fall_kind == "snow" else 0.7
			process.initial_velocity_max = 2.2 if fall_kind == "snow" else 1.3
			process.gravity = Vector3(0.0, -0.6, 0.0)
			process.scale_min = 0.6
			process.scale_max = 1.3
		"sand":
			# Driven sideways, low and fast.
			node.lifetime = 1.6
			node.position.y = 2.0
			node.draw_pass_1 = _flake_mesh(Color(0.86, 0.72, 0.50, 0.55), 0.09)
			process.emission_box_extents = Vector3(RAIN_BOX.x, 3.0, RAIN_BOX.z)
			process.direction = Vector3(1.0, -0.08, 0.35)
			process.spread = 12.0
			process.initial_velocity_min = 8.0
			process.initial_velocity_max = 14.0
			process.gravity = Vector3.ZERO
			process.scale_min = 0.7
			process.scale_max = 1.6
	node.process_material = process
	add_child(node)
	_falls[fall_kind] = node
	return node

static func _amounts(look: Array) -> PackedFloat32Array:
	var result := PackedFloat32Array([0, 0, 0, 0, 0, 0])
	for index: int in 6:
		if look.size() > index + 1:
			result[index] = clampf(float(look[index + 1]) / 100.0, 0.0, 1.0)
	return result

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

## A flake (snow, ash, sand): a soft dot facing the camera.
func _flake_mesh(colour: Color, size: float) -> Mesh:
	var mesh := QuadMesh.new()
	mesh.size = Vector2(size, size)
	var material := StandardMaterial3D.new()
	material.albedo_color = colour
	material.albedo_texture = _soft_dot()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
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

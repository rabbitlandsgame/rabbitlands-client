class_name WorldEnvironmentBinder
extends RefCounted
## Applies a map manifest's `environment` block to the scene's WorldEnvironment
## and sun.
##
## Without this a region loads under the client's generic placeholder
## environment - a flat background colour, cool ambient and no sky or fog -
## which cannot present a region whose art direction is warm daylight over
## open grassland. Maps that declare no `environment` block keep exactly the
## behaviour they had before, so this is additive.
##
## Two authoring dialects are accepted for the same values, because the region
## and the city toolchains grew independently: `topColor`/`zenith`,
## `horizonColor`/`horizon`, `groundBottomColor`/`groundBottom`,
## `groundHorizonColor`/`groundHorizon`, `sunAngleMax`/`sunAngleMaxDegrees`,
## and `white`/`whitePoint`. The first spelling of each pair is canonical for
## new work. The sun may be aimed either by `rotationDegrees` or by a
## `direction` vector.

const DEFAULT_SUN_ROTATION := Vector3(-55.0, -30.0, 0.0)
const DEFAULT_SUN_ENERGY := 1.15
## Depth towards the sun beyond each camera-fitted shadow cascade. Godot's
## 20 m default clips the top of Four Gates' 68 m monument as the camera
## orbits, shortening its shadow even with the light and geometry fixed.
## Cover tall casters outside the view, including the low daytime sun, without
## increasing the maximum shadow distance from the camera.
const SUN_SHADOW_CASTER_DEPTH := 256.0
## How much sun energy reaches the ground inside a shadow. The compatibility
## renderer has no GI or screen-space occlusion, so an opaque shadow is lit by
## ambient alone and every region's shadows read as holes in the ground.
## Raising ambient does not fix that: `ambient_light_energy` does nothing to the
## sky's share, and five regions take all of their ambient from the sky. Letting
## part of the sun through does. It is an amount of energy rather than a fixed
## opacity because the same opacity that suits Westhaven's 1.22 sun all but
## erased the shadows under Ssarathi's 2.35 one.
const SUN_SHADOW_LEAK_ENERGY := 0.42
## However weak a package's sun, its shadows still block at least this much, so
## an overcast map keeps enough shadow to ground what stands in it.
const MIN_SUN_SHADOW_OPACITY := 0.5

## Point lights spawned from a manifest are tagged so the next map can clear
## them without touching lights that belong to the scene.
const MANIFEST_LIGHT_GROUP := "manifest_lights"

static func apply(manifest: WorldManifest, world_environment: WorldEnvironment,
		sun: DirectionalLight3D, light_parent: Node = null) -> bool:
	if manifest == null or world_environment == null:
		return false
	if sun != null:
		sun.directional_shadow_pancake_size = SUN_SHADOW_CASTER_DEPTH
	var raw: Variant = manifest.data.get("environment")
	if raw is not Dictionary:
		_restore_defaults(sun)
		return false
	var declared: Dictionary = raw as Dictionary
	var environment: Environment = Environment.new()

	var sky_value: Variant = declared.get("sky")
	if sky_value is Dictionary:
		var declared_sky: Dictionary = sky_value as Dictionary
		var material: ProceduralSkyMaterial = ProceduralSkyMaterial.new()
		material.sky_top_color = _color(
			_either(declared_sky, "topColor", "zenith"), Color("3d7ec2"))
		material.sky_horizon_color = _color(
			_either(declared_sky, "horizonColor", "horizon"), Color("bcc9cd"))
		material.sky_curve = float(declared_sky.get("curve", 0.15))
		material.ground_bottom_color = _color(
			_either(declared_sky, "groundBottomColor", "groundBottom"), Color("6d5c40"))
		material.ground_horizon_color = _color(
			_either(declared_sky, "groundHorizonColor", "groundHorizon"), Color("b3a07c"))
		material.sun_angle_max = float(_number(
			_either(declared_sky, "sunAngleMax", "sunAngleMaxDegrees"), 12.0))
		material.energy_multiplier = float(declared_sky.get("energy", 1.0))
		var sky: Sky = Sky.new()
		sky.sky_material = material
		environment.sky = sky
		environment.background_mode = Environment.BG_SKY
		environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	else:
		environment.background_mode = Environment.BG_COLOR
		environment.background_color = _color(declared.get("backgroundColor"),
			Color(0.10, 0.15, 0.21))
		environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR

	var ambient_value: Variant = declared.get("ambient")
	if ambient_value is Dictionary:
		var ambient: Dictionary = ambient_value as Dictionary
		if ambient.has("color"):
			# Keep the sky as a source and let skyContribution blend it against
			# the declared colour, so a warm ground bounce can temper a blue sky
			# rather than replacing it.
			environment.ambient_light_color = _color(ambient.get("color"), Color.WHITE)
			if environment.background_mode != Environment.BG_SKY:
				environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.ambient_light_energy = float(ambient.get("energy", 0.85))
		environment.ambient_light_sky_contribution = float(
			ambient.get("skyContribution", 1.0))

	var fog_value: Variant = declared.get("fog")
	if fog_value is Dictionary:
		var fog: Dictionary = fog_value as Dictionary
		environment.fog_enabled = bool(fog.get("enabled", true))
		environment.fog_light_color = _color(fog.get("color"), Color("d8c9a4"))
		environment.fog_density = float(fog.get("density", 0.0016))
		environment.fog_sky_affect = float(fog.get("skyAffect", 0.4))
		environment.fog_aerial_perspective = float(fog.get("aerialPerspective", 0.0))

	var tonemap_value: Variant = declared.get("tonemap")
	if tonemap_value is Dictionary:
		var tonemap: Dictionary = tonemap_value as Dictionary
		environment.tonemap_mode = _tonemap_mode(str(tonemap.get("mode", "filmic")))
		environment.tonemap_exposure = float(tonemap.get("exposure", 1.0))
		environment.tonemap_white = float(_number(
			_either(tonemap, "white", "whitePoint"), 1.0))

	world_environment.environment = environment

	var sun_value: Variant = declared.get("sun")
	if sun_value is Dictionary and sun != null:
		var declared_sun: Dictionary = sun_value as Dictionary
		# An interior declares `"sun": {"enabled": false}`: hiding the key light
		# is what lets its lamps and hearths read as the only light in the room.
		sun.visible = bool(declared_sun.get("enabled", true))
		var rotation: Variant = declared_sun.get("rotationDegrees")
		var direction: Variant = declared_sun.get("direction")
		if rotation is Array and (rotation as Array).size() >= 3:
			var values: Array = rotation as Array
			sun.rotation_degrees = Vector3(float(values[0]), float(values[1]),
				float(values[2]))
		elif direction is Array and (direction as Array).size() >= 3:
			var aim: Array = direction as Array
			var facing := Vector3(float(aim[0]), float(aim[1]),
				float(aim[2])).normalized()
			if facing.length_squared() > 0.0:
				var up := Vector3.UP if absf(facing.dot(Vector3.UP)) < 0.999 \
					else Vector3.FORWARD
				sun.look_at_from_position(Vector3.ZERO, facing, up)
		sun.light_color = _color(declared_sun.get("color"), Color.WHITE)
		sun.light_energy = float(declared_sun.get("energy", DEFAULT_SUN_ENERGY))
		sun.light_indirect_energy = float(declared_sun.get("indirectEnergy", 1.0))
		if declared_sun.has("angularDiameterDegrees"):
			sun.light_angular_distance = float(
				declared_sun.get("angularDiameterDegrees"))
		# A hidden key light must also stop casting: an interior that declares
		# no sun should get no directional shadows across its floor.
		sun.shadow_enabled = sun.visible and bool(declared_sun.get("shadows", true))
		sun.shadow_opacity = sun_shadow_opacity(declared_sun)
	elif sun != null:
		sun.visible = true
		_restore_defaults(sun)

	var parent: Node = light_parent
	if parent == null:
		parent = world_environment.get_parent()
	var lamps: int = _apply_lights(declared, parent)
	if lamps > 0:
		print_debug("world_environment stage=lights count=", lamps)
	return true


## Spawns the manifest's point lights under `parent`, replacing any left over
## from a previously loaded map. An interior has no sky and no sun, so its
## lamps, hearths and crystal fittings are the only light in the room.
static func _apply_lights(declared: Dictionary, parent: Node) -> int:
	if parent == null or not parent.is_inside_tree():
		return 0
	for stale: Node in parent.get_tree().get_nodes_in_group(MANIFEST_LIGHT_GROUP):
		stale.queue_free()
	var raw: Variant = declared.get("lights", [])
	if raw is not Array:
		return 0
	var spawned: int = 0
	for entry_value: Variant in raw as Array:
		if entry_value is not Dictionary:
			continue
		var entry: Dictionary = entry_value as Dictionary
		var light := OmniLight3D.new()
		light.add_to_group(MANIFEST_LIGHT_GROUP)
		light.position = _vector(entry.get("position"), Vector3.ZERO)
		light.light_color = _color(entry.get("color"), Color(1.0, 0.88, 0.72))
		light.light_energy = float(entry.get("energy", 2.0))
		light.omni_range = float(entry.get("range", 10.0))
		light.omni_attenuation = float(entry.get("attenuation", 1.4))
		light.shadow_enabled = bool(entry.get("shadows", false))
		light.name = "ManifestLight_%d" % spawned
		parent.add_child(light)
		spawned += 1
	return spawned


## Applies a map's camera profile. The isometric rig is framed for open ground;
## indoors it sits outside the room and renders the ceiling, so an interior
## declares its own closer, shallower framing and tighter zoom limits. A map
## that declares no `camera` block leaves the rig exactly as it was.
static func apply_camera(manifest: WorldManifest, rig: Node) -> bool:
	if manifest == null or rig == null:
		return false
	var raw: Variant = manifest.data.get("camera", {})
	if raw is not Dictionary:
		return false
	var declared: Dictionary = raw as Dictionary
	if declared.is_empty():
		return false
	if declared.has("minDistance"):
		rig.set("min_distance", float(declared.get("minDistance")))
	if declared.has("maxDistance"):
		rig.set("max_distance", float(declared.get("maxDistance")))
	if declared.has("distance"):
		rig.set("distance", clampf(float(declared.get("distance")),
			float(rig.get("min_distance")), float(rig.get("max_distance"))))
	if declared.has("pitchDegrees"):
		rig.set("pitch_degrees",
			clampf(float(declared.get("pitchDegrees")), -80.0, -15.0))
	if declared.has("zoomStep"):
		rig.set("zoom_step", float(declared.get("zoomStep")))
	if rig.has_method("_update_camera"):
		rig.call("_update_camera")
	return true

static func _restore_defaults(sun: DirectionalLight3D) -> void:
	if sun == null:
		return
	sun.rotation_degrees = DEFAULT_SUN_ROTATION
	sun.light_color = Color.WHITE
	sun.light_energy = DEFAULT_SUN_ENERGY
	sun.light_indirect_energy = 1.0
	sun.shadow_opacity = sun_shadow_opacity({})

## The shadow opacity for a package's noon sun: its own `shadowOpacity` if it
## declares one, otherwise whatever lets SUN_SHADOW_LEAK_ENERGY through.
static func sun_shadow_opacity(declared_sun: Dictionary) -> float:
	var declared: Variant = declared_sun.get("shadowOpacity")
	if declared is float or declared is int:
		return clampf(float(declared), 0.0, 1.0)
	var energy: float = float(_number(declared_sun.get("energy"), DEFAULT_SUN_ENERGY))
	if energy <= 0.0:
		return 1.0
	return clampf(1.0 - SUN_SHADOW_LEAK_ENERGY / energy, MIN_SUN_SHADOW_OPACITY, 1.0)

## First of two accepted spellings that the manifest actually declares.
static func _either(block: Dictionary, canonical: String, alias: String) -> Variant:
	if block.has(canonical):
		return block.get(canonical)
	return block.get(alias)


static func _number(value: Variant, fallback: float) -> float:
	if value is float or value is int:
		return float(value)
	return fallback


static func _vector(value: Variant, fallback: Vector3) -> Vector3:
	if value is Array and (value as Array).size() >= 3:
		var values: Array = value as Array
		return Vector3(float(values[0]), float(values[1]), float(values[2]))
	return fallback


static func _color(value: Variant, fallback: Color) -> Color:
	if value is Array:
		var values: Array = value as Array
		if values.size() >= 3:
			return Color(float(values[0]), float(values[1]), float(values[2]),
				float(values[3]) if values.size() > 3 else 1.0)
	elif value is String:
		return Color(str(value))
	return fallback

static func _tonemap_mode(name: String) -> int:
	match name.to_lower():
		"linear":
			return Environment.TONE_MAPPER_LINEAR
		"reinhard":
			return Environment.TONE_MAPPER_REINHARDT
		"aces":
			return Environment.TONE_MAPPER_ACES
		_:
			return Environment.TONE_MAPPER_FILMIC

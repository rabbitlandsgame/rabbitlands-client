class_name DayNightBinder
extends RefCounted
## Drives the environment from the server's game clock.
##
## `NEW_MINUTE(5)` has always arrived and only ever moved the clock face and the
## compass: the sun, the ambient light and the fog came from the map manifest
## and never changed, so every map was permanently at whatever hour it was
## authored for.
##
## The daylight curve is the server's own, not one invented here. `World`
## computes `daylight = (1 - cos(2*PI*minute/360)) / 2` to decide how far a
## creature can see, with minute 180 the brightest point and minute 0 the
## darkest; this uses exactly that expression, so what the player sees and what
## the server acts on cannot drift apart.
##
## The manifest stays the reference: what a package declares is full daylight,
## and this dims and warms it towards night. A package can opt out with
## `environment.dayNight: {"enabled": false}`, and an interior that declares no
## sun is left alone - its lamps are its whole lighting and dimming them by the
## hour outside would be wrong.

const MINUTES_PER_DAY := 360.0
## How far the sun's key light falls at midnight, as a fraction of noon. At
## 0.06 the moon lit nothing and the world read as flat shapes in the dark;
## this leaves enough of a key for surfaces to keep their form as the sun goes
## down and comes back up.
const NIGHT_SUN_ENERGY := 0.30
## Ambient never reaches zero: a pitch-black world is unplayable and the
## legacy client never went there either. 0.22 was still too near it to play
## in - the ground, the walls and the actors all fell into one silhouette -
## and 0.42 only ever reached the maps that declare an ambient colour of their
## own, because energy does nothing while the sky is the whole ambient source.
const NIGHT_AMBIENT_ENERGY := 0.95
## A fraction of noon is not enough on its own: a map authored for an overcast
## noon of 0.34 would keep a night of 0.32 and stay unplayable while a bright
## one was fine. Night is floored at a level every map can be walked in.
const NIGHT_AMBIENT_FLOOR := 0.74
## Night ambient is not scraped off the night sky. A package that declares no
## `skyContribution` takes all of its ambient from the sky, so at midnight the
## only light the ground had was NIGHT_SKY_TOP itself and the maps whose
## ambient is authored as `skyColor` - the barrens, the moors, the range - went
## black while the far fog stayed lit. At night the sky's share is turned down
## and this moonlit colour takes its place; at noon the package's own
## contribution is restored exactly, so daylight is untouched.
const NIGHT_AMBIENT_COLOUR := Color(0.56, 0.60, 0.74)
const NIGHT_SKY_CONTRIBUTION := 0.15
const NIGHT_SUN_COLOUR := Color(0.46, 0.56, 0.82)
const DAWN_SUN_COLOUR := Color(1.0, 0.72, 0.46)
## The night sky and fog are lifted with the rest: they are most of what the
## far half of an outdoor scene is made of, so leaving them near black would
## undo the ambient the ground just gained.
const NIGHT_SKY_TOP := Color(0.14, 0.18, 0.30)
const NIGHT_SKY_HORIZON := Color(0.27, 0.32, 0.45)
const NIGHT_FOG := Color(0.27, 0.31, 0.42)
## The sun's arc, in degrees of elevation at noon and below the horizon at
## midnight.
const NOON_ELEVATION := -62.0
const MIDNIGHT_ELEVATION := 12.0
## A caster's shadow length is roughly height / tan(elevation above the
## horizon): ~9x its own height at 6 degrees, ~5x at 12, ~2x at 25. Below this
## cutoff the sun is close enough to the horizon that the shadow it throws
## stretches most of the way across the screen behind a walking player - a
## long shadow at dusk reads as atmosphere, one that dominates the view reads
## as broken. Shadows fade in once the sun has climbed clear of that band
## rather than the instant it crosses the horizon.
const SHADOW_ELEVATION_CUTOFF := -15.0
## The moon. Night was one flat ambient wash: MIDNIGHT_ELEVATION is below the
## horizon, so the sun's remaining key shines up into the sky and lights
## nothing on the ground, and no outdoor package declares a lamp. Everything
## therefore took the same light from every side and the world read as
## silhouettes - dark not for want of brightness but for want of a direction.
## The moon rides the sun's own arc half a day away, so it stands highest at
## midnight and sets as the sun rises, and it is the only light with a
## direction while the sun is down.
const MOON_ENERGY := 0.28
const MOON_COLOUR := Color(0.52, 0.60, 0.86)
## Moonlight is gone by the time the sun is properly up: it fades out over the
## first third of the daylight curve, so dawn, noon and dusk are as they were.
const MOON_DAYLIGHT_FADE := 0.35
## The moon throws no shadow of its own. A second shadow-casting directional
## light costs a whole shadow pass - measured at a fifth of the frame rate on
## the Four Gates capture - and what night was missing was the shading, not a
## second set of cast shadows.

## The server's own daylight curve, for a continuous minute.
static func daylight(minute: float) -> float:
	return (1.0 - cos(TAU * minute / MINUTES_PER_DAY)) * 0.5

## How much of the light is dawn or dusk rather than noon or midnight. Peaks
## where the daylight curve is changing fastest, which is sunrise and sunset.
static func twilight(minute: float) -> float:
	return absf(sin(TAU * minute / MINUTES_PER_DAY))

## True when the package wants the hour to drive its environment at all.
static func drives(manifest: WorldManifest) -> bool:
	if manifest == null:
		return false
	var environment: Variant = manifest.data.get("environment")
	if environment is not Dictionary:
		return false
	var declared: Dictionary = environment as Dictionary
	var settings: Variant = declared.get("dayNight")
	if settings is Dictionary and not bool(
			(settings as Dictionary).get("enabled", true)):
		return false
	# An interior declares no sun, or declares it disabled. Its lamps are its
	# lighting; the hour outside does not reach them.
	var sun: Variant = declared.get("sun")
	if sun is not Dictionary:
		return false
	return bool((sun as Dictionary).get("enabled", true))

## Applies the hour to an environment already bound from the manifest. The
## manifest values are read back as the noon reference, so this can run
## repeatedly without drifting.
static func apply(manifest: WorldManifest, world_environment: WorldEnvironment,
		sun: DirectionalLight3D, minute: float, moon: DirectionalLight3D = null) -> bool:
	if not drives(manifest) or world_environment == null or sun == null:
		return false
	_apply_moon(moon, daylight(minute), sun)
	var environment: Environment = world_environment.environment
	if environment == null:
		return false
	var declared: Dictionary = manifest.data.get("environment", {}) as Dictionary
	var light: float = daylight(minute)
	var edge: float = twilight(minute)

	var declared_sun: Dictionary = declared.get("sun", {}) as Dictionary
	var noon_energy: float = float(declared_sun.get("energy", 1.0))
	var noon_colour: Color = _colour(declared_sun.get("color"), Color.WHITE)
	sun.light_energy = lerpf(noon_energy * NIGHT_SUN_ENERGY, noon_energy, light)
	sun.light_color = noon_colour.lerp(NIGHT_SUN_COLOUR, 1.0 - light) \
		.lerp(DAWN_SUN_COLOUR, edge * 0.55)
	sun.rotation_degrees.x = lerpf(MIDNIGHT_ELEVATION, NOON_ELEVATION, light)
	# Gate on the elevation itself rather than a fraction of `light`: a fixed
	# 0.08 cutoff on `light` was never the horizon - MIDNIGHT_ELEVATION is
	# positive (sun below the horizon) and NOON_ELEVATION is negative (sun
	# above it), and that cutoff fell well inside the still-below-horizon side
	# of the interpolation, so the key light kept casting for a while after
	# "sunset" and again before "sunrise". Comparing the interpolated angle
	# directly ties the two together at whatever `light` the crossing actually
	# falls at, and SHADOW_ELEVATION_CUTOFF holds the light off further still,
	# until the shadow it would throw has come down to a sane length.
	sun.shadow_enabled = bool(declared_sun.get("shadows", true)) \
		and sun.rotation_degrees.x < SHADOW_ELEVATION_CUTOFF
	# Border blending hands this a neighbour's manifest, so the opacity follows
	# the region whose light is being applied rather than the one loaded. It is
	# taken from the noon sun, not the current one, so it does not drift with
	# the hour.
	sun.shadow_opacity = WorldEnvironmentBinder.sun_shadow_opacity(declared_sun)

	var declared_ambient: Dictionary = declared.get("ambient", {}) as Dictionary
	var noon_ambient: float = float(declared_ambient.get("energy", 0.85))
	var noon_contribution: float = float(
		declared_ambient.get("skyContribution", 1.0))
	# `skyColor` is the region toolchain's spelling of the same ambient colour
	# the city toolchain calls `color`. WorldEnvironmentBinder only reads the
	# latter, so for half the outdoor maps this is the first time the colour
	# they authored is used at all. A package that names none falls back to the
	# moonlit colour rather than to white, which would bleach its palette.
	var noon_ambient_colour: Color = _colour(_any(declared_ambient,
		["color", "colour", "skyColor"]), NIGHT_AMBIENT_COLOUR)
	environment.ambient_light_energy = lerpf(
		maxf(noon_ambient * NIGHT_AMBIENT_ENERGY, NIGHT_AMBIENT_FLOOR),
		noon_ambient, light)
	environment.ambient_light_sky_contribution = lerpf(
		minf(noon_contribution, NIGHT_SKY_CONTRIBUTION), noon_contribution,
		light)
	environment.ambient_light_color = noon_ambient_colour.lerp(
		NIGHT_AMBIENT_COLOUR, 1.0 - light)

	var sky_material: Variant = environment.sky.sky_material if environment.sky != null else null
	if sky_material is ProceduralSkyMaterial:
		var declared_sky: Dictionary = declared.get("sky", {}) as Dictionary
		var material: ProceduralSkyMaterial = sky_material as ProceduralSkyMaterial
		material.sky_top_color = _colour(
			_either(declared_sky, "topColor", "zenith"), Color("3d7ec2")
			).lerp(NIGHT_SKY_TOP, 1.0 - light)
		material.sky_horizon_color = _colour(
			_either(declared_sky, "horizonColor", "horizon"), Color("bcc9cd")
			).lerp(NIGHT_SKY_HORIZON, 1.0 - light).lerp(DAWN_SUN_COLOUR, edge * 0.35)

	if environment.fog_enabled:
		var declared_fog: Dictionary = declared.get("fog", {}) as Dictionary
		environment.fog_light_color = _colour(declared_fog.get("color"),
			Color("d8c9a4")).lerp(NIGHT_FOG, 1.0 - light)
	return true

## The moon on the sun's arc, half a day away: highest at midnight, below the
## horizon and dark by the time the sun is up. It takes the sun's own azimuth
## turned about, so its shading falls the other way from the day's.
static func _apply_moon(moon: DirectionalLight3D, light: float, sun: DirectionalLight3D) -> void:
	if moon == null:
		return
	var night: float = clampf(1.0 - light / MOON_DAYLIGHT_FADE, 0.0, 1.0)
	moon.light_energy = MOON_ENERGY * night
	moon.light_color = MOON_COLOUR
	moon.rotation_degrees.x = lerpf(NOON_ELEVATION, MIDNIGHT_ELEVATION, light)
	moon.rotation_degrees.y = sun.rotation_degrees.y + 180.0
	moon.rotation_degrees.z = sun.rotation_degrees.z
	moon.visible = night > 0.0
	moon.shadow_enabled = false

static func _either(source: Dictionary, first: String, second: String) -> Variant:
	return source.get(first, source.get(second))

## The first of several spellings a package might have used for one value.
static func _any(source: Dictionary, keys: Array[String]) -> Variant:
	for key: String in keys:
		if source.has(key):
			return source[key]
	return null

static func _colour(value: Variant, fallback: Color) -> Color:
	if value is String:
		return Color(value as String)
	if value is Array and (value as Array).size() >= 3:
		var channels: Array = value as Array
		return Color(float(channels[0]), float(channels[1]), float(channels[2]),
			float(channels[3]) if channels.size() > 3 else 1.0)
	return fallback

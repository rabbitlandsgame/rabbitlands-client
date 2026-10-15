shader_type sky;
// Look pass layer L5: a painted sky (see LookSky). Only installed when
// ELORIA_LOOK=1.
//
// Two skies in one shader. The radiance cubemap, which lights every sky-lit
// map's ambient and reflections, is drawn exactly as develop draws it (the
// engine's procedural sky, or a background colour's flat light), so the
// painted sky changes what the camera sees behind the world and nothing that
// the world is lit by: the default -60 degree view shows no sky at all, and
// its frames must not shift because a cloud moved. Only the background pass,
// what the camera actually sees, is painted: a soft gradient from the
// region's own sky colours, a band of haze at the horizon in exactly the fog's
// colour (so ground far enough away to be fogged dissolves into it), brushed
// cumulus from low-frequency noise and a warm glow round the sun. Below the
// horizon, where the world has not loaded or has ended, the haze carries on
// down and only then gives way to the old ground colour, which is also what a
// straight-down map camera sees, so the minimap's empty space is unchanged.
//
// No TIME: a sky shader that reads it re-renders its radiance every frame.
// No screen texture: this has to run in the compatibility renderer too.

// --- Develop's sky, for the radiance cubemap ---------------------------------
// The engine's ProceduralSkyMaterial, term for term, fed the same values the
// binders give it (LookSky copies them, and the hour's colours, every refresh).
uniform vec4 radiance_top : source_color = vec4(0.385, 0.454, 0.55, 1.0);
uniform vec4 radiance_horizon : source_color = vec4(0.646, 0.656, 0.67, 1.0);
uniform float radiance_curve = 0.15;
uniform float radiance_sky_energy = 1.0;
uniform vec4 radiance_ground_bottom : source_color = vec4(0.2, 0.169, 0.133, 1.0);
uniform vec4 radiance_ground_horizon : source_color = vec4(0.646, 0.656, 0.67, 1.0);
uniform float radiance_ground_curve = 0.02;
uniform float radiance_ground_energy = 1.0;
// Radians, as the engine passes it.
uniform float radiance_sun_angle_max = 0.5236;
uniform float radiance_sun_curve = 0.15;
uniform float radiance_exposure = 1.0;
// A map that declared a background colour rather than a sky was lit (and
// reflected) by that flat colour; it still is.
uniform bool radiance_flat = false;
uniform vec4 radiance_flat_colour : source_color = vec4(0.1, 0.15, 0.21, 1.0);

// --- The painted sky ---------------------------------------------------------
uniform vec4 look_zenith : source_color = vec4(0.24, 0.45, 0.73, 1.0);
uniform vec4 look_horizon : source_color = vec4(0.79, 0.81, 0.77, 1.0);
// The haze: the horizon band and the fog share this colour.
uniform vec4 look_haze : source_color = vec4(0.8, 0.82, 0.78, 1.0);
// Above 1 the horizon's colour holds further up before the zenith's takes over.
uniform float look_gradient_power = 2.6;
// How high the haze band reaches and how far below the horizon it carries
// on, as the sine of the elevation.
uniform float look_haze_height = 0.1;
uniform float look_haze_depth = 0.3;

// Brushed cumulus: fbm value noise on a flat cloud layer, stretched along the
// wind so the masses read as brush strokes rather than as cotton balls.
uniform float look_cloud_scale = 0.9;
uniform float look_cloud_stretch = 0.45;
// The noise is pushed away from its mean by this much before it is cut, so
// the sky breaks into clouds and clear gaps rather than a thin veil.
uniform float look_cloud_contrast = 1.8;
uniform float look_cloud_threshold = 0.62;
uniform float look_cloud_softness = 0.1;
uniform float look_cloud_opacity = 0.85;
uniform vec4 look_cloud_lit : source_color = vec4(1.0, 0.96, 0.88, 1.0);
// The shaded underside, as a share of the sky colour behind it.
uniform float look_cloud_shade = 0.82;
// Clouds fade in above the haze band, from and to these elevations (sines).
uniform vec2 look_cloud_band = vec2(0.03, 0.2);
uniform vec2 look_cloud_offset = vec2(0.0, 0.0);

// The sun's glow: a wide warm halo and a tighter core, tinted by this colour
// over the sun's own light.
uniform vec4 look_sun_glow : source_color = vec4(1.0, 0.82, 0.55, 1.0);
uniform float look_sun_halo = 0.25;
uniform float look_sun_core = 0.6;

// Debug views (LookProfile.SKY_DEBUG_VARIABLE): 1 draws the painted sky flat
// magenta above the horizon and cyan below it, for counting how much of a
// capture is sky; 2 leaves the clouds out; 3 and 4 draw the zenith's and the
// horizon's colour flat, for reading what the grade makes of them.
uniform int look_debug = 0;

vec3 look_procedural_sun(vec3 sky, vec3 dir, bool on, vec3 light_dir,
		float light_size, vec3 light_colour, float light_energy) {
	if (!on) {
		return sky;
	}
	float sun_angle = acos(clamp(dot(light_dir, dir), -1.0, 1.0));
	if (sun_angle < light_size) {
		return light_colour * light_energy;
	}
	if (sun_angle < radiance_sun_angle_max) {
		float c2 = (sun_angle - light_size) / (radiance_sun_angle_max - light_size);
		return mix(light_colour * light_energy, sky,
			clamp(1.0 - pow(1.0 - c2, 1.0 / radiance_sun_curve), 0.0, 1.0));
	}
	return sky;
}

vec3 look_radiance_ground() {
	return radiance_ground_bottom.rgb * radiance_ground_energy * radiance_exposure;
}

vec3 look_to_display(vec3 colour) {
	return pow(max(colour, vec3(0.0)), vec3(1.0 / 2.2));
}

vec3 look_to_light(vec3 colour) {
	return pow(max(colour, vec3(0.0)), vec3(2.2));
}

float look_hash(vec2 p) {
	vec3 p3 = fract(vec3(p.x, p.y, p.x) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

float look_noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(look_hash(i), look_hash(i + vec2(1.0, 0.0)), u.x),
		mix(look_hash(i + vec2(0.0, 1.0)), look_hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float look_fbm(vec2 p) {
	float total = 0.0;
	float amplitude = 0.5;
	mat2 turn = mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8));
	for (int octave = 0; octave < 4; octave++) {
		total += amplitude * look_noise(p);
		p = turn * p * 2.03 + vec2(17.1, 9.2);
		amplitude *= 0.5;
	}
	return total / 0.9375;
}

vec3 look_painted(vec3 dir, bool sun_on, vec3 sun_dir, vec3 sun_colour, float sun_size) {
	float up = max(dir.y, 0.0);
	// Mixed in display space: mixed in linear light, the pale horizon's much
	// larger values carried two thirds of the way up and the sky read grey.
	vec3 sky = look_to_light(mix(look_to_display(look_horizon.rgb),
		look_to_display(look_zenith.rgb), 1.0 - pow(1.0 - up, look_gradient_power)));
	vec2 toward_sun = vec2(0.0, 0.0);
	if (sun_on) {
		float facing = max(dot(dir, sun_dir), 0.0);
		vec3 glow = look_sun_glow.rgb * sun_colour;
		sky += glow * (pow(facing, 6.0) * look_sun_halo + pow(facing, 48.0) * look_sun_core);
		sky = mix(sky, glow * 2.0, smoothstep(cos(max(sun_size, 0.004) * 1.6),
			cos(max(sun_size, 0.004) * 0.7), facing));
		if (length(sun_dir.xz) > 0.01) {
			toward_sun = normalize(sun_dir.xz);
		}
	}

	// A flat cloud layer: the plane's coordinates grow towards the horizon,
	// so the clouds foreshorten into it.
	vec2 plane = dir.xz / (up + 0.12) * look_cloud_scale;
	plane.x *= look_cloud_stretch;
	plane += look_cloud_offset;
	float density = (look_fbm(plane) - 0.5) * look_cloud_contrast + 0.5;
	float cover = smoothstep(look_cloud_threshold - look_cloud_softness,
		look_cloud_threshold + look_cloud_softness, density);
	cover *= smoothstep(look_cloud_band.x, look_cloud_band.y, up) * look_cloud_opacity;
	if (cover > 0.001 && look_debug != 2) {
		// Denser towards the sun means this side faces away from it.
		float ahead = (look_fbm(plane + toward_sun * 0.35) - 0.5) * look_cloud_contrast + 0.5;
		float lit = clamp(0.55 + (density - ahead) * 2.0, 0.0, 1.0);
		float core = smoothstep(look_cloud_threshold, look_cloud_threshold + 0.25, density);
		vec3 shade = sky * look_cloud_shade;
		// Mostly lit: a painted cumulus is a bright mass with a softer
		// underside, not a grey one with a bright rim.
		vec3 cloud = mix(shade, look_cloud_lit.rgb, 0.35 + 0.65 * lit * (1.0 - 0.35 * core));
		sky = mix(sky, cloud, cover);
	}

	float haze = 1.0 - smoothstep(0.0, look_haze_height, up);
	sky = look_to_light(mix(look_to_display(sky), look_to_display(look_haze.rgb), haze));
	return sky;
}

void sky() {
	vec3 dir = EYEDIR;
	if (AT_CUBEMAP_PASS) {
		if (radiance_flat) {
			COLOR = radiance_flat_colour.rgb;
		} else {
			float v_angle = acos(clamp(dir.y, -1.0, 1.0));
			float c = 1.0 - v_angle / (PI * 0.5);
			vec3 sky_colour = mix(radiance_horizon.rgb, radiance_top.rgb,
				clamp(1.0 - pow(1.0 - c, 1.0 / radiance_curve), 0.0, 1.0));
			sky_colour *= radiance_sky_energy;
			sky_colour = look_procedural_sun(sky_colour, dir, LIGHT0_ENABLED,
				LIGHT0_DIRECTION, LIGHT0_SIZE, LIGHT0_COLOR, LIGHT0_ENERGY);
			sky_colour = look_procedural_sun(sky_colour, dir, LIGHT1_ENABLED,
				LIGHT1_DIRECTION, LIGHT1_SIZE, LIGHT1_COLOR, LIGHT1_ENERGY);
			sky_colour = look_procedural_sun(sky_colour, dir, LIGHT2_ENABLED,
				LIGHT2_DIRECTION, LIGHT2_SIZE, LIGHT2_COLOR, LIGHT2_ENERGY);
			sky_colour = look_procedural_sun(sky_colour, dir, LIGHT3_ENABLED,
				LIGHT3_DIRECTION, LIGHT3_SIZE, LIGHT3_COLOR, LIGHT3_ENERGY);
			c = (v_angle - PI * 0.5) / (PI * 0.5);
			vec3 ground = mix(radiance_ground_horizon.rgb, radiance_ground_bottom.rgb,
				clamp(1.0 - pow(1.0 - c, 1.0 / radiance_ground_curve), 0.0, 1.0));
			ground *= radiance_ground_energy;
			COLOR = mix(ground, sky_colour, step(0.0, dir.y)) * radiance_exposure;
		}
	} else {
		vec3 ground = radiance_flat ? radiance_flat_colour.rgb : look_radiance_ground();
		if (look_debug == 1) {
			COLOR = dir.y >= 0.0 ? vec3(4.0, 0.0, 4.0) : vec3(0.0, 4.0, 4.0);
		} else if (look_debug == 3) {
			COLOR = look_zenith.rgb;
		} else if (look_debug == 4) {
			COLOR = look_horizon.rgb;
		} else if (dir.y >= 0.0) {
			COLOR = look_painted(dir, LIGHT0_ENABLED, LIGHT0_DIRECTION, LIGHT0_COLOR,
				LIGHT0_SIZE);
		} else {
			// Unloaded or unbuilt space below the horizon is more haze, deepening
			// to the old ground colour well below it.
			COLOR = mix(look_haze.rgb, ground,
				smoothstep(0.0, look_haze_depth, -dir.y));
		}
		// Break the gradient's 8-bit banding.
		COLOR += (look_hash(FRAGCOORD.xy) - 0.5) * 0.004;
	}
}

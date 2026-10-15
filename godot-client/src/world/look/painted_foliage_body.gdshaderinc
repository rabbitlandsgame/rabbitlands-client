// Look pass layer L3: the body of a painted crown.
//
// Stands in for the StandardMaterial3D a crown imported with - an authored
// tree's alpha-cut leaf material (foliage_amber, foliage_rust, foliage_gold,
// undergrowth) or a kit tree's single atlas material - keeping its texture,
// tint, UVs, cutout and surface (normal, roughness, metallic and occlusion
// maps, see look_standard_surface.gdshaderinc), and painting it:
//
// - the crown lit as one volume: its shading normal is mostly the normal of
//   the ellipsoid its box holds, so the sun falls across the whole crown,
//   top-lit, instead of lighting and darkening every leaf card on its own
//   (which drew each card's edge dark and a crown as a heap of cards);
// - a top light across the crown's height in mesh space, warm and lifted on
//   top, cool and deep underneath (and on the trunk below the crown);
// - fake occlusion towards the crown's centre, so its inner leaves and the
//   gaps between clumps go dark and the clumps read;
// - a clump mottle in mesh space that breaks a flat-shaded blob into masses;
// - a per-crown hue and value jitter from its position in its region;
// - the autumn tame: saturated reds and oranges compressed into a painted
//   range, magenta pulled to crimson, amber towards the top and maroon
//   underneath;
// - a gentle sway, weighted by height so a trunk's foot stays put.
//
// A kit tree is crown and trunk in one surface. They are split here by
// height: below look_crown_min.y (LookProfile.CROWN_FLOOR of the mesh's
// height) is trunk, which takes only the underside shade. The tame is keyed
// on saturated warm texels, which bark is not, so a trunk that reaches up
// into the crown is left its colour.
//
// The painted_foliage*.gdshader files include this after choosing the render
// mode: opaque (kit trees) or alpha-cut (LOOK_FOLIAGE_CUTOUT), and resting
// or faded (LOOK_FOLIAGE_FADE). Only a faded copy - one OccluderFade swaps in
// while the crown stands between the camera and the player - carries the
// discard that opens a hole round the player (look_fade_hole.gdshaderinc), so
// a resting opaque crown keeps the engine's early depth test.
//
// The compatibility renderer shades in sRGB: albedo arrives gamma-encoded
// there and linear in Forward+ (see painted_ground_paint.gdshaderinc). Every
// value below is linear and every hue is a display (sRGB) hue, so the colour
// is decoded on the way in and encoded on the way out.

// Albedo, normal, roughness, metallic, occlusion, emission and UV scale as
// the source material had them.
#include "res://src/world/look/look_standard_surface.gdshaderinc"
#ifdef LOOK_FOLIAGE_FADE
#include "res://src/world/look/look_fade_hole.gdshaderinc"
#endif

uniform float alpha_scissor_threshold = 0.5;

// The crown's box in mesh space (min.y is where the trunk ends), and the
// mesh's own foot, which the sway is weighted from.
uniform vec3 look_crown_min = vec3(-1.0, 0.0, -1.0);
uniform vec3 look_crown_max = vec3(1.0, 2.0, 1.0);
uniform float look_mesh_foot = 0.0;
uniform vec3 look_crown_top = vec3(1.16, 1.08, 0.92);
uniform vec3 look_crown_under = vec3(0.6, 0.65, 0.76);
// The underside of a tamed (warm, saturated) texel: red-brown, not blue,
// which would turn a red crown's shade pink.
uniform vec3 look_crown_under_warm = vec3(0.62, 0.5, 0.46);
uniform float look_crown_light_power = 0.7;
uniform float look_crown_core = 0.72;
uniform vec2 look_crown_core_edge = vec2(0.25, 0.85);
uniform float look_crown_clump_metres = 2.2;
uniform float look_crown_clump = 0.16;
uniform float look_crown_jitter_hue = 7.0;
uniform float look_crown_jitter_value = 0.1;
// 1 tames saturated warm crowns; 0 leaves the hue alone (blossom).
uniform float look_tame = 1.0;
uniform vec2 look_tame_hue = vec2(268.0, 60.0);
uniform vec2 look_tame_from = vec2(0.4, 0.6);
uniform float look_tame_knee = 0.55;
uniform float look_tame_ceiling = 0.8;
uniform float look_tame_magenta_floor = -2.0;
uniform float look_tame_hue_top = 9.0;
uniform float look_tame_hue_under = -5.0;
uniform float look_tame_value = 0.8;
uniform vec2 look_tame_value_from = vec2(0.5, 0.9);
// How much of the shading normal is the crown's ellipsoid rather than the
// leaf card's own (0 the card, 1 the ellipsoid).
uniform float look_crown_volume = 0.7;
uniform float look_crown_volume_lift = 0.35;
uniform float look_sway_metres = 0.07;
uniform float look_sway_speed = 1.1;
// The occluder fade's opacity, driven by OccluderFade on a faded copy. Kept
// as a record of the fade; the faded variants cut the hole look_fade_open
// opens instead (look_fade_hole.gdshaderinc).
uniform float look_fade = 1.0;
// A crown fades out by its own distance from a perspective camera: gone
// nearer than x metres, dithered in between, whole beyond y; cut clean at x
// when y is x (LookProfile.CROWN_NEAR_FADE_METRES; 0, 0 never). The banyans, palms and
// canopies that rise between the -60 degree camera and the ground drew as
// opaque leaf cards over a third of the frame, dark where their undersides
// faced it (vs_road, cw_border_ss, aw_deep_grove); develop blended them.
uniform vec2 look_near_fade = vec2(0.0);
// LookProfile.FOLIAGE_DEBUG_VARIABLE: 1 draws every painted crown flat by its
// view depth (red nearer than 10 m, yellow to 15, green to 20, blue beyond),
// with no near fade, for finding which crowns a frame's canopy is.
uniform int look_debug = 0;

// A hash of the crown's position in its region (0..1), set by LookFoliage
// per material. A batch draws many crowns with one material, so its
// instances add their index.
uniform float look_seed = 0.0;
// The region's tree-crown tint (LookFoliage.crown_tint_at: a region file's
// foliage.crown_tint, faded across its borders), a multiplier on the crown's
// linear colour from the crown up; white (no change) unless a region sets one.
uniform vec3 look_crown_tint = vec3(1.0);

// Height through the crown (0 at its bottom, 1 at its top, below 0 on the
// trunk), distance from its centre (0 there, about 1 on its shell), the
// crown's own seed, and the mesh-space position for the clump mottle.
varying float look_crown_height;
varying float look_crown_radial;
varying flat float look_crown_seed;
varying vec3 look_crown_position;
// The crown ellipsoid's normal at the vertex, in view space.
varying vec3 look_crown_normal;

float look_foliage_hash(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

float look_foliage_noise(vec3 p) {
	vec3 cell = floor(p);
	vec3 f = fract(p);
	vec3 u = f * f * (3.0 - 2.0 * f);
	vec2 lift = vec2(cell.y * 17.0, cell.y * 31.0);
	float a = look_foliage_hash(cell.xz + lift);
	float b = look_foliage_hash(cell.xz + vec2(1.0, 0.0) + lift);
	float c = look_foliage_hash(cell.xz + vec2(0.0, 1.0) + lift);
	float d = look_foliage_hash(cell.xz + vec2(1.0, 1.0) + lift);
	vec2 lift_up = lift + vec2(17.0, 31.0);
	float e = look_foliage_hash(cell.xz + lift_up);
	float g = look_foliage_hash(cell.xz + vec2(1.0, 0.0) + lift_up);
	float h = look_foliage_hash(cell.xz + vec2(0.0, 1.0) + lift_up);
	float k = look_foliage_hash(cell.xz + vec2(1.0, 1.0) + lift_up);
	float low = mix(mix(a, b, u.x), mix(c, d, u.x), u.z);
	float high = mix(mix(e, g, u.x), mix(h, k, u.x), u.z);
	return mix(low, high, u.y);
}

// The renderer's albedo encoding to linear, and back (see the header).
vec3 look_foliage_decode(vec3 colour) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	colour = max(colour, vec3(0.0));
	return mix(pow((colour + vec3(0.055)) * (1.0 / 1.055), vec3(2.4)),
		colour * (1.0 / 12.92), lessThan(colour, vec3(0.04045)));
#else
	return colour;
#endif
}

vec3 look_foliage_encode(vec3 colour) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	colour = clamp(colour, vec3(0.0), vec3(1.0));
	return mix(vec3(1.055) * pow(colour, vec3(1.0 / 2.4)) - vec3(0.055),
		colour * 12.92, lessThan(colour, vec3(0.0031308)));
#else
	return clamp(colour, vec3(0.0), vec3(1.0));
#endif
}

vec3 look_foliage_hsv(vec3 c) {
	vec4 k = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
	vec4 p = mix(vec4(c.bg, k.wz), vec4(c.gb, k.xy), step(c.b, c.g));
	vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
	float d = q.x - min(q.w, q.y);
	float e = 1.0e-10;
	return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 look_foliage_rgb(vec3 c) {
	vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - vec3(3.0));
	return c.z * mix(vec3(1.0), clamp(p - vec3(1.0), 0.0, 1.0), c.y);
}

void vertex() {
	UV = UV * uv1_scale.xy + uv1_offset.xy;
	vec3 size = max(look_crown_max - look_crown_min, vec3(0.001));
	vec3 centre = (look_crown_min + look_crown_max) * 0.5;
	look_crown_height = (VERTEX.y - look_crown_min.y) / size.y;
	look_crown_radial = length((VERTEX - centre) / (size * 0.5));
	look_crown_position = VERTEX;
	look_crown_seed = fract(look_seed + float(INSTANCE_ID) * 0.6180339);
	// MODELVIEW_MATRIX carries a batch instance's own transform here.
	// The position on the crown's box, normalised, leaning up by
	// look_crown_volume_lift: a painter's crown is lit from above, and a tall
	// fir's true ellipsoid normals face sideways all the way up.
	vec3 shell = (VERTEX - centre) / (size * 0.5);
	shell.y += look_crown_volume_lift;
	look_crown_normal = normalize((MODELVIEW_MATRIX * vec4(shell, 0.0)).xyz
		+ vec3(0.0, 0.00001, 0.0));
	// Sway: weighted by the square of the height above the mesh's foot.
	float rise = clamp((VERTEX.y - look_mesh_foot)
		/ max(look_crown_max.y - look_mesh_foot, 0.001), 0.0, 1.0);
	float phase = TIME * look_sway_speed + look_crown_seed * 6.2831853;
	float flutter = 0.3 * sin(phase * 2.7 + VERTEX.y * 0.9 + VERTEX.x * 0.6);
	VERTEX.x += (sin(phase) + flutter) * look_sway_metres * rise * rise;
	VERTEX.z += (sin(phase * 0.77 + 1.3) + flutter) * 0.6 * look_sway_metres * rise * rise;
}

vec3 look_foliage_paint(vec3 albedo) {
	vec3 linear_colour = look_foliage_decode(albedo);
	float crown = smoothstep(-0.04, 0.04, look_crown_height);
	float height = clamp(look_crown_height, 0.0, 1.0);
	float jitter_hue = (look_foliage_hash(vec2(look_crown_seed * 97.0, 3.1)) - 0.5) * 2.0;
	float jitter_value = (look_foliage_hash(vec2(look_crown_seed * 57.0, 8.3)) - 0.5) * 2.0;

	// Hue and saturation, on the colour as it displays.
	vec3 hsv = look_foliage_hsv(pow(clamp(linear_colour, vec3(0.0), vec3(1.0)),
		vec3(1.0 / 2.2)));
	// How much of the top light's and underside's tint a texel takes: a
	// low-chroma crown (Westhaven's olives, whose atlas is a khaki of
	// saturation 0.28; a frosted fir) takes only their value, where the warm
	// top and cool underside turned the olives mauve-pink and the firs silver.
	float tinted = smoothstep(0.25, 0.45, hsv.y);
	float hue = hsv.x * 360.0;
	float signed_hue = hue > 180.0 ? hue - 360.0 : hue;
	float warm = smoothstep(look_tame_hue.x - 360.0 - 12.0, look_tame_hue.x - 360.0,
		signed_hue) * (1.0 - smoothstep(look_tame_hue.y, look_tame_hue.y + 12.0, signed_hue));
	float tame = look_tame * crown * warm
		* smoothstep(look_tame_from.x, look_tame_from.y, hsv.y);
	float pulled = max(signed_hue, look_tame_magenta_floor);
	pulled += mix(look_tame_hue_under, look_tame_hue_top, height);
	signed_hue = mix(signed_hue, pulled, tame);
	signed_hue += jitter_hue * look_crown_jitter_hue * crown;
	float excess = max(hsv.y - look_tame_knee, 0.0);
	float capped = look_tame_knee + excess * (look_tame_ceiling - look_tame_knee)
		/ (1.0 - look_tame_knee);
	hsv.y = mix(hsv.y, capped, tame);
	hsv.z *= mix(1.0, look_tame_value,
		tame * smoothstep(look_tame_value_from.x, look_tame_value_from.y, hsv.z));
	hsv.x = fract(signed_hue / 360.0 + 1.0);
	linear_colour = pow(look_foliage_rgb(hsv), vec3(2.2));

	// Value: top light, core occlusion, clumps, jitter.
	vec3 under = mix(look_crown_under, look_crown_under_warm, tame);
	vec3 luma_weights = vec3(0.2126, 0.7152, 0.0722);
	under = mix(vec3(dot(under, luma_weights)), under, tinted);
	vec3 top = mix(vec3(dot(look_crown_top, luma_weights)), look_crown_top, tinted);
	vec3 light = mix(under, top, pow(height, look_crown_light_power) * crown);
	float core = mix(look_crown_core, 1.0,
		smoothstep(look_crown_core_edge.x, look_crown_core_edge.y, look_crown_radial));
	float clump = 1.0 + (look_foliage_noise(look_crown_position / look_crown_clump_metres)
		- 0.5) * 2.0 * look_crown_clump * crown;
	float value = core * clump * (1.0 + jitter_value * look_crown_jitter_value);
	vec3 tint = mix(vec3(1.0), look_crown_tint, crown);
	return look_foliage_encode(linear_colour * light * value * tint);
}

// Interleaved gradient noise: a one-pixel dither threshold (0..1).
float look_near_noise(vec2 fragment) {
	return fract(52.9829189 * fract(dot(floor(fragment), vec2(0.06711056, 0.00583715))));
}

void fragment() {
	vec4 texel = texture(albedo_texture, UV);
#ifdef LOOK_FOLIAGE_FADE
	if (look_fade_cut(VERTEX, VIEW_MATRIX, PROJECTION_MATRIX, FRAGCOORD.xy)) {
		discard;
	}
#endif
	// Near the camera the crown dissolves (look_near_fade). Only for a
	// perspective camera: a directional light's shadow pass is orthographic
	// and must keep the crown's whole shadow, and the map cameras look down
	// from far above.
	if (look_debug == 0 && look_near_fade.y > 0.0 && PROJECTION_MATRIX[3][3] < 0.5) {
		float depth = -VERTEX.z;
		if (look_near_fade.y > look_near_fade.x + 0.001
				? smoothstep(look_near_fade.x, look_near_fade.y, depth)
					< look_near_noise(FRAGCOORD.xy)
				: depth < look_near_fade.x) {
			discard;
		}
	}
	ALBEDO = look_foliage_paint(texel.rgb * albedo_color.rgb);
#ifdef LOOK_FOLIAGE_CUTOUT
	ALPHA = texel.a * albedo_color.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor_threshold;
#endif
	// The crown's volume normal, from the crown up (a kit tree's trunk keeps
	// its own).
	float volume = look_crown_volume * smoothstep(-0.04, 0.04, look_crown_height);
	NORMAL = normalize(mix(NORMAL, normalize(look_crown_normal), volume));
	vec4 surface = look_standard_surface(UV);
	ROUGHNESS = surface.x;
	METALLIC = surface.y;
	SPECULAR = surface.z;
	if (has_ao) {
		AO = surface.w;
		AO_LIGHT_AFFECT = ao_light_affect;
	}
	if (has_normal_texture) {
		NORMAL_MAP = texture(normal_texture, UV).rgb;
		NORMAL_MAP_DEPTH = normal_scale;
	}
	if (has_emission) {
		EMISSION = look_standard_emission(UV);
	}
	if (look_debug == 1) {
		float depth = -VERTEX.z;
		ALBEDO = vec3(0.0);
		EMISSION = depth < 10.0 ? vec3(2.0, 0.0, 0.0) : depth < 15.0 ? vec3(2.0, 2.0, 0.0)
			: depth < 20.0 ? vec3(0.0, 2.0, 0.0) : vec3(0.0, 0.0, 2.0);
	}
}

// RL hair, beards and their cards.
//
// The texture (named by the material's glTF extras: hair_clump.png for
// clumps, hair_strands.png for cards, beard.png for beards) carries neutral
// luminance in RGB and coverage in A. The actor's hair colour is multiplied
// in. The vertex colours say where each point is: R a random value per lock
// (a little brightness variation), G the position along the lock (0 root, 1
// tip; the roots are darkened), B ambient occlusion and A the keep level for
// hair_detail (below). Godot's own vertex-colour albedo never applies: only
// this shader reads COLOR. Clumps and cards are both alpha-tested in the
// opaque pass - no sorting, and the same in Forward+ and the compatibility
// renderer - and drawn double-sided.
//
// Fine detail (the hair author's hair_detail contract): A = 1 marks core
// geometry (shells, clumps, ribbons, bun, braid, curls, baby hairs); flyaway
// and wisp cards carry a keep level in 0.5-0.95. A fragment with
// A < 1 - hair_detail (the instance uniform, 0..1) gets ALPHA 0 and is dropped
// by the same alpha scissor as the coverage, so it never leaves the opaque
// pass or its depth prepass. 0.5 (the default) shows the authored look; lower
// drops the flyaways from the lowest keep level up, and 0 is smooth. Above 0.5
// nothing more appears: the strands gain up to `detail_contrast` more contrast
// about the atlas's local mean (and the per-lock variation grows) instead, so
// the hair's overall tone and its colour calibration hold. Beards and older
// assets carry A = 1 everywhere, and beards keep the default.
//
// Light is a wrapped Lambert for the soft painted body of the hair plus a
// Kajiya-Kay pair of highlights along the strands: a light primary in the
// hair's own hue (primary_whiteness mixes in white) shifted towards the tip
// and a hair-coloured secondary shifted towards the root. `exposure` sets how
// bright the painted luminance makes the hair colour, calibrated so front-lit
// hair lands near the chosen colour, as the skin is. The
// strand direction is the surface's V direction, rebuilt per pixel from the
// UV derivatives, so the asset needs no tangents.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D strand_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_texture = false;
uniform bool card = false;
uniform float alpha_scissor : hint_range(0.0, 1.0) = 0.5;
uniform float root_darkening : hint_range(0.0, 1.0) = 0.35;
uniform float lock_variation : hint_range(0.0, 0.5) = 0.12;
uniform float occlusion : hint_range(0.0, 1.0) = 0.6;
uniform float wrap : hint_range(0.0, 1.0) = 0.35;
uniform bool anisotropic = true;
uniform float primary_shift = 0.08;
uniform float secondary_shift = -0.1;
uniform float primary_gloss = 90.0;
uniform float secondary_gloss = 22.0;
uniform float primary_strength : hint_range(0.0, 2.0) = 0.13;
uniform float primary_whiteness : hint_range(0.0, 1.0) = 0.3;
// Thin cards (beards, flyaways) turn a strand highlight into light speckles.
uniform float card_primary : hint_range(0.0, 1.0) = 0.3;
uniform float exposure : hint_range(0.5, 4.0) = 2.2;
uniform float secondary_strength : hint_range(0.0, 2.0) = 0.22;
// Extra strand contrast at hair_detail 1 (none at 0.5 and below).
uniform float detail_contrast : hint_range(0.0, 1.0) = 0.35;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
// Half a step of the 8-bit keep level: a core triangle's interpolated A = 1
// can land a hair under 1.0, and a 0.5 card must survive the default.
const float KEEP_TOLERANCE = 0.5 / 255.0;
// The atlas mip whose texels average a neighbourhood of strands.
const float MEAN_LOD = 6.0;

varying vec3 strand;

void fragment() {
	float detail = clamp(hair_detail, 0.0, 1.0);
	bool kept = COLOR.a >= 1.0 - detail - KEEP_TOLERANCE;
	float boost = clamp(detail * 2.0 - 1.0, 0.0, 1.0);
	vec4 atlas;
	if (has_texture) {
		atlas = texture(strand_texture, UV);
	} else {
		// No atlas yet: streaks along the strands, and thin tips on cards.
		float streak = 0.5 + 0.5 * sin(UV.x * 180.0 + sin(UV.y * 9.0) * 2.0);
		float coverage = card ? mix(0.35, 1.2, streak) * (1.0 - smoothstep(0.75, 1.0, COLOR.g)) : 1.0;
		atlas = vec4(vec3(mix(0.78, 1.08, streak)), coverage);
	}
	float root = mix(1.0 - root_darkening, 1.0, smoothstep(0.0, 0.55, COLOR.g));
	float lock = 1.0 + (COLOR.r - 0.5) * 2.0 * lock_variation * (1.0 + boost);
	float shade = mix(1.0, COLOR.b, occlusion);
	float painted = has_texture ? dot(atlas.rgb, LUMA) : atlas.r / 1.5;
	if (has_texture && boost > 0.0) {
		float mean = dot(textureLod(strand_texture, UV, MEAN_LOD).rgb, LUMA);
		painted = max(mean + (painted - mean) * (1.0 + detail_contrast * boost), 0.0);
	}
	float luminance = painted * exposure;
	ALBEDO = hair_color.rgb * clamp(luminance, 0.0, 2.0) * root * lock * shade;
	// A dropped detail fragment fails the scissor below like uncovered atlas
	// (alpha_scissor is above 0 on every RL hair material).
	ALPHA = kept ? atlas.a : 0.0;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
	ROUGHNESS = 0.6;
	// light() replaces only the direct lights; the environment's reflection
	// still uses SPECULAR, and its Fresnel term mirrored the grey sky as silver
	// patches on clumps and beard cards seen edge-on. Hair gets its sheen from
	// the strand highlights below instead.
	SPECULAR = 0.0;
	vec3 dp1 = dFdx(VERTEX);
	vec3 dp2 = dFdy(VERTEX);
	vec2 duv1 = dFdx(UV);
	vec2 duv2 = dFdy(UV);
	vec3 along_v = cross(dp2, NORMAL) * duv1.y + cross(NORMAL, dp1) * duv2.y;
	strand = length(along_v) > 1e-12 ? normalize(along_v) : vec3(0.0, 1.0, 0.0);
}

void light() {
	float n_dot_l = dot(NORMAL, LIGHT);
	float diffuse = clamp((n_dot_l + wrap) / (1.0 + wrap), 0.0, 1.0);
	// A custom light() owns the whole result: Godot does not multiply
	// DIFFUSE_LIGHT by ALBEDO afterwards, so without ALBEDO here every lit
	// clump and beard card took the key light as near-white (measured: a pure
	// green albedo came back with 40-110 of red and blue).
	DIFFUSE_LIGHT += diffuse * ATTENUATION * LIGHT_COLOR * ALBEDO / PI;
	if (anisotropic) {
		vec3 halfway = normalize(LIGHT + VIEW);
		vec3 first = normalize(strand + NORMAL * primary_shift);
		vec3 second = normalize(strand + NORMAL * secondary_shift);
		float t1 = dot(first, halfway);
		float t2 = dot(second, halfway);
		float s1 = pow(sqrt(max(1.0 - t1 * t1, 0.0)), primary_gloss);
		float s2 = pow(sqrt(max(1.0 - t2 * t2, 0.0)), secondary_gloss);
		float lit = smoothstep(-0.1, 0.35, n_dot_l);
		vec3 hue = ALBEDO / max(max(ALBEDO.r, ALBEDO.g), max(ALBEDO.b, 1e-4));
		vec3 primary = mix(hue, vec3(1.0), primary_whiteness);
		float primary_gain = primary_strength * (card ? card_primary : 1.0);
		SPECULAR_LIGHT += (primary * s1 * primary_gain + ALBEDO * s2 * secondary_strength)
			* lit * ATTENUATION * LIGHT_COLOR / PI;
	}
}

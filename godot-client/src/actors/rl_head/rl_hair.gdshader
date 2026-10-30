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
// and wisp cards carry a keep level in 0.5-0.95, and messy extras (strays,
// frizz, loose locks, separated tips) one in 0.05-0.45. A fragment with
// A < 1 - hair_detail (the instance uniform, 0..1) gets ALPHA 0 and is dropped
// by the same alpha scissor as the coverage, so it never leaves the opaque
// pass or its depth prepass. 0.5 (the default) shows the authored look; lower
// drops the flyaways from the lowest keep level up, and 0 is smooth. Above 0.5
// the messy extras fade in (0.55-0.95) and the strands gain up to
// `detail_contrast` more contrast about the atlas's local mean (and the
// per-lock variation grows), so the hair's overall tone and its colour
// calibration hold. Beards and older assets carry A = 1 everywhere, and beards
// keep the default.
//
// The look is a flat, painterly colour mass, as in the concept art: a wrapped
// Lambert for gentle form, the atlas's strand contrast mostly flattened away
// (`flatness`), and only a faint, broad sheen in the hair's own hue from a
// Kajiya-Kay pair of highlights along the strands (a primary shifted towards
// the tip, primary_whiteness mixing in white, and a hair-coloured secondary
// shifted towards the root). `flatness` moves each pixel's painted luminance
// towards its lock's mean - the atlas mip whose texels average a neighbourhood
// of strands (MEAN_LOD) - so the lock-scale tone stays and the fine streaks go;
// it applies after hair_detail's contrast boost.
// Cards (flyaways, beards) flatten towards `card_flat_level` instead: the
// strand atlas's uncovered texels are white fill, so its mips overstate the
// strands' own tone (up to 4x), and the fixed level, the clump atlas's covered
// mean, gives flyaways and beards the mass's tone for the same colour.
// `exposure` sets how bright the painted luminance makes the hair colour,
// calibrated so front-lit hair lands near the chosen colour, as the skin is:
// on the RL head stage (neutral look, Forward+, the groomed hair, before and
// after its 2026-10-28 coverage rebuild) the 75th-percentile hair pixel of Rowan, Mira and Tavi, front
// view, is 1.08, 0.82 and 1.15 times the preset colour's luminance at the
// defaults (geometric mean 1.00; each preset's exposure below is calibrated
// the same way). The response is linear in the colour, so a palette or wheel
// table fitted against these values holds for every hue.
// Beards (`beard`, set on the rl_beard material) are drawn `beard_gain` times
// brighter: their thin cards hang under the jaw, turned from the key light and
// darkened at the roots, and at the flat-painterly defaults without the gain
// Tavi's full beard in his hair's own colour lit to 0.59 of what his hair did
// (the 75th-percentile pixel over the front, three-quarter and profile views on
// the RL head stage; front alone 0.68 against 1.15 times the colour). At 1.7
// both are 1.10 times it (front 1.16 and 1.15), so a lit beard has the hair's
// value for the same colour.
// The strand direction is the surface's V direction, rebuilt per pixel from
// the UV derivatives, so the asset needs no tangents.
//
// Shading presets (the defaults are "flat painterly"; set the uniforms on the
// RL hair materials for the others). "current" is the look before 2026-10-28,
// whose diffuse fell with the square of the colour (see light()): dark hair
// took almost no key light, and its highlights carried 70-90 % of its light.
//
//   uniform             current  slightly flatter  flat painterly  very flat
//   double_albedo          1.0         0.0              0.0           0.0
//   flatness               0.0         0.35             0.65          0.9
//   card_flat_level        -           0.35             0.35          0.35
//   primary_strength       0.13        0.07             0.015         0.0
//   primary_whiteness      0.3         0.15             0.0           0.0
//   card_primary           0.3         0.2              0.2           0.0
//   secondary_strength     0.22        0.14             0.08          0.03
//   secondary_gloss       22.0        18.0             12.0           8.0
//   root_darkening         0.35        0.3              0.25          0.2
//   occlusion              0.6         0.5              0.4           0.3
//   wrap                   0.35        0.4              0.45          0.5
//   lock_variation         0.12        0.12             0.12          0.08
//   exposure               2.2         2.2              2.5           2.55
//
// (primary_gloss 90, primary_shift 0.08 and secondary_shift -0.1 in all;
// beard_gain 1.0 reproduces "current", and its 1.7 was fitted at flat painterly.)
// Measured on Rowan, front view, against "current": the highlights' share of
// the hair's light 69 % -> 19 / 6 / 1 %, strand-scale streak contrast (RMS of
// log luminance about its 3 px blur) -35 / -50 / -55 %, luminance spread
// p90/p10 12.4 -> 5.1 / 4.0 / 3.6. Tavi's full beard (beard colour = hair
// colour, beard_gain 1) went from 0.19 to 0.53 / 0.68 / 0.80 of its colour at
// the 75th percentile, against the hair's 1.09 -> 1.30 / 1.14 / 1.07; with the
// beard_gain default it is 1.16 at flat painterly.
shader_type spatial;
#ifdef RL_BEARD_FEATHER
render_mode blend_mix, depth_prepass_alpha, cull_disabled;
#elif defined(RL_SOFT_ROOTS)
render_mode blend_mix, depth_draw_opaque, cull_disabled, alpha_to_coverage;
#else
render_mode blend_mix, depth_draw_opaque, cull_disabled;
#endif

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D strand_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_texture = false;
uniform bool card = false;
// Tight braids intentionally expose the actor's scalp between their rows.
uniform bool scalp_channels = false;
uniform bool soft_hairline = false;
uniform float alpha_scissor : hint_range(0.0, 1.0) = 0.5;
uniform float root_darkening : hint_range(0.0, 1.0) = 0.25;
uniform float lock_variation : hint_range(0.0, 0.5) = 0.12;
uniform float occlusion : hint_range(0.0, 1.0) = 0.4;
uniform float wrap : hint_range(0.0, 1.0) = 0.45;
uniform bool anisotropic = true;
uniform float primary_shift = 0.08;
uniform float secondary_shift = -0.1;
uniform float primary_gloss = 90.0;
uniform float secondary_gloss = 12.0;
uniform float primary_strength : hint_range(0.0, 2.0) = 0.015;
uniform float primary_whiteness : hint_range(0.0, 1.0) = 0.0;
// Thin cards (beards, flyaways) turn a strand highlight into light speckles.
uniform float card_primary : hint_range(0.0, 1.0) = 0.2;
uniform float exposure : hint_range(0.5, 4.0) = 2.5;
uniform float secondary_strength : hint_range(0.0, 2.0) = 0.08;
// Extra strand contrast at hair_detail 1 (none at 0.5 and below).
uniform float detail_contrast : hint_range(0.0, 1.0) = 0.35;
// How far each pixel's painted luminance moves towards its lock's mean: 0
// keeps the atlas's strand contrast, 1 leaves only the lock-scale tone.
uniform float flatness : hint_range(0.0, 1.0) = 0.65;
// What cards (flyaways, beards) flatten towards (see above).
uniform float card_flat_level : hint_range(0.0, 1.0) = 0.35;
// 1 multiplies ALBEDO into the diffuse light a second time, as the hair was
// first calibrated; only for comparison renders of that look.
uniform float double_albedo : hint_range(0.0, 1.0) = 0.0;
// Beards: how much brighter than the hair the same colour is drawn (see above).
uniform bool beard = false;
uniform float beard_gain : hint_range(0.5, 3.0) = 1.7;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
// Half a step of the 8-bit keep level: a core triangle's interpolated A = 1
// can land a hair under 1.0, and a 0.5 card must survive the default.
const float KEEP_TOLERANCE = 0.5 / 255.0;
// The atlas mip whose texels average a neighbourhood of strands.
const float MEAN_LOD = 6.0;

varying vec3 strand;
varying vec3 rest_position;

void vertex() {
	rest_position = VERTEX;
}

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
	float lock_random = soft_hairline && (!card || beard) ? 0.5 : COLOR.r;
	float lock = 1.0 + (lock_random - 0.5) * 2.0 * lock_variation * (1.0 + boost);
	float shade = mix(1.0, COLOR.b, occlusion);
	float painted = has_texture ? dot(atlas.rgb, LUMA) : atlas.r / 1.5;
	if (has_texture && (boost > 0.0 || flatness > 0.0)) {
		float mean = dot(textureLod(strand_texture, UV, MEAN_LOD).rgb, LUMA);
		painted = max(mean + (painted - mean) * (1.0 + detail_contrast * boost), 0.0);
		painted = mix(painted, card ? card_flat_level : mean, flatness);
	}
	float luminance = painted * exposure;
	ALBEDO = hair_color.rgb * clamp(luminance, 0.0, 2.0) * root * lock * shade * (beard ? beard_gain : 1.0);
	// A dropped detail fragment fails the scissor below like uncovered atlas
	// (alpha_scissor is above 0 on every RL hair material).
	ALPHA = kept ? atlas.a : 0.0;
	if (scalp_channels && rest_position.y > 1.715 && rest_position.z > -0.075) {
		float row = rest_position.x / 0.027;
		float gap = abs(fract(row) - 0.5);
		if (gap < 0.055 && abs(rest_position.x) < 0.078) {
			ALPHA = 0.0;
		}
	}
	if (soft_hairline && ((!card && !beard) || beard)) {
		ALPHA *= smoothstep(0.0, 0.5, COLOR.r);
	}
#ifndef RL_BEARD_FEATHER
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
#endif
#ifdef RL_SOFT_ROOTS
	ALPHA_ANTIALIASING_EDGE = alpha_scissor * 0.5;
	ALPHA_TEXTURE_COORDINATE = UV * vec2(textureSize(strand_texture, 0));
#endif
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
	// Godot 4.7.2 multiplies DIFFUSE_LIGHT by ALBEDO after light(), in Forward+
	// and the compatibility renderer alike (measured 2026-10-28: with ALBEDO
	// pure green and no ALBEDO here, every lit pixel came back with red and
	// blue exactly 0). Multiplying it in here as well made the diffuse fall
	// with the square of the colour (see double_albedo).
	DIFFUSE_LIGHT += diffuse * ATTENUATION * LIGHT_COLOR * mix(vec3(1.0), ALBEDO, double_albedo) / PI;
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

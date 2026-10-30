// RL head skin: face, cranium, ears, neck and the mouth's inner lining.
//
// The albedo is painted lighting-free at a reference tone and recoloured the
// way face_appearance.gdshader recolours the body: the reference divided out,
// the chosen colour multiplied in, and a share of the local detail kept. That
// share is the body's (a fifth) on the neck rim and the head's own on the face
// (rl_head_textures/manifest.json: about 0.55), blended by the Head joint's skin
// weight, so a recoloured neck meets a recoloured body without a seam.
// Lighting is the body's own model (Burley diffuse, Schlick-GGX specular,
// the body's roughness on the rim); the head's own roughness and an optional
// Forward+ subsurface term fade in from the rim with the same weight. (No
// BACKLIGHT: it is transmission for thin sheets, and through a whole skull it
// lit the back of the head from the front key and left the neck-weighted nape
// as a dark patch.)
//
// Painted features, in the manifest's order: freckles, stubble, blush, the
// hairline, lips, the lash line and liner (and its wing), and brows; teeth and
// tongue are rl_mouth.gdshader's. Per-actor colours, amounts and styles are
// instance uniforms: every actor with the same head shares this material. The
// stylised eye (`eye_style_paint.y`, eye_paint from eye_style) thickens and
// darkens the upper lash line, and the lash line fades as a blink closes the
// lid (`lid_closure`).
//
// Brows are a player choice, not art per character: head_<sex>_brows.png holds
// one hair-stroke mask per style (R arched, G straight, B soft, A angled), the
// style picks or blends channels, and the thickness shapes the chosen mask -
// thicker spreads the strokes past their painted edge (a blurrier mip of the
// mask) and lowers the curve's floor so that fringe fills in, thinner raises
// the floor so only the core strokes stay. Without that
// texture, features B is read as the one painted brow, as before.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform bool has_albedo = false;
// R freckle dots, G lips, B the liner's wing (with head_<sex>_brows.png; the one
// painted brow without it), A upper and lower lash line plus liner.
uniform sampler2D features_texture : hint_default_black, filter_linear_mipmap, repeat_disable;
uniform bool has_features = false;
// R stubble, G blush zones, B scalp and hairline, A face (1) vs body-matched neck (0).
uniform sampler2D features2_texture : hint_default_black, filter_linear_mipmap, repeat_disable;
uniform bool has_features2 = false;
// One brow style per channel: R arched, G straight, B soft, A angled.
uniform sampler2D brows_texture : hint_default_black, filter_linear_mipmap, repeat_disable;
uniform bool has_brows = false;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap, repeat_disable;
uniform bool has_normal = false;
uniform vec4 skin_reference : source_color = vec4(0.814, 0.633, 0.532, 1.0);
// Which skin joint is Head (BONE_INDICES index the skin's joints).
uniform int head_bind_index = 2;
uniform float rim_detail_keep : hint_range(0.0, 1.0) = 0.2;
uniform float face_detail_keep : hint_range(0.0, 1.0) = 0.55;
uniform float roughness_value : hint_range(0.0, 1.0) = 0.7;
uniform float specular_value : hint_range(0.0, 1.0) = 0.35;
// The body face material's roughness and specular, which the neck rim takes.
uniform float rim_roughness : hint_range(0.0, 1.0) = 0.85;
uniform float rim_specular : hint_range(0.0, 1.0) = 0.5;
uniform float normal_strength : hint_range(0.0, 2.0) = 0.65;
uniform float subsurface : hint_range(0.0, 1.0) = 0.0;
uniform vec3 freckle_shade : source_color = vec3(0.62, 0.45, 0.36);
// The painted stubble mask peaks near 0.4; this lifts it so full stubble reads
// as a five o'clock shadow rather than a faint tint.
uniform float stubble_gain : hint_range(0.5, 4.0) = 1.8;
uniform float blush : hint_range(0.0, 1.0) = 0.25;
uniform vec3 blush_tint : source_color = vec3(1.0, 0.8, 0.78);
uniform float lip_strength : hint_range(0.0, 1.0) = 0.9;
// The lash line drawn even without liner; liner darkens towards the colour.
uniform float lash_line : hint_range(0.0, 1.0) = 0.35;
uniform vec3 liner_color : source_color = vec3(0.07, 0.05, 0.045);
// The stylised eye's liner (eye_paint, 0..1, from eye_style): the upper line -
// features A is painted near 1 there and fainter along the lower lid - darkens towards
// the liner colour by `liner_paint` and, as the Medium faces paint it, stays a thin line
// over the inner part of the eye and thickens towards the outer corner: it grows up the
// lid by up to `liner_grow` UV at eye_paint 1 (about 1.5 mm on the face; copies of the
// line lifted up to that far, `liner_grow_lod` mip levels soft, so the band keeps a crisp
// edge), scaled along the eye by `liner_taper` (x of it at the inner corner, growing from
// y of the way out to all of it at z); the wing flicks out by at least `liner_paint_wing`.
uniform float liner_grow = 0.0035;
uniform float liner_grow_lod : hint_range(0.0, 4.0) = 0.0;
uniform vec3 liner_taper = vec3(0.0, 0.45, 0.9);
// Where the eye runs along u: |u - face_mid_u| at its inner and its outer corner (the
// texture manifest's `liner_span_u` for the head; liner_span.py measures it).
uniform vec2 liner_span_u = vec2(0.076, 0.132);
uniform float liner_paint : hint_range(0.0, 1.0) = 0.92;
uniform float liner_paint_wing : hint_range(0.0, 1.0) = 0.4;
// The face island's midline in UV: the character's left eye (blink_l, lid_closure.x)
// lies at larger u. The lash line and liner fade out with that side's lid closure.
uniform float face_mid_u = 0.37;
// The brow mask through a contrast curve, pow(clamp((m - floor) / span), gamma):
// the faint fringe drops out and the body of the brow fills. These are the
// curve at thickness 0; thickness -1 and +1 move it to the thin and thick ends.
uniform float brow_floor : hint_range(0.0, 0.5) = 0.04;
uniform float brow_span : hint_range(0.05, 1.0) = 0.5;
uniform float brow_gamma : hint_range(0.3, 2.0) = 0.85;
// (floor, span, gamma) at the thin and the thick end.
uniform vec3 brow_thin = vec3(0.22, 0.4, 1.25);
uniform vec3 brow_thick = vec3(0.0, 0.62, 0.6);
uniform float brow_density : hint_range(0.0, 1.5) = 0.9;
// Thick brows also grow outwards: the mask is maxed with a blurrier mip of
// itself (this many mip levels at thickness 1), lifted by the gain, so the
// strokes spread past their painted edge before the curve fills them.
uniform float brow_spread_lod : hint_range(0.0, 5.0) = 2.5;
uniform float brow_spread_gain : hint_range(0.5, 4.0) = 1.7;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

varying float face_weight;
varying float rest_height;

void vertex() {
	rest_height = VERTEX.y;
	face_weight = 0.0;
	for (int i = 0; i < 4; i++) {
		if (int(BONE_INDICES[i]) == head_bind_index) {
			face_weight += BONE_WEIGHTS[i];
		}
	}
}

// How much of each brow channel a style takes: whole channels at the integer
// styles, a linear blend of the two neighbours in between.
vec4 brow_weights(float style) {
	return clamp(1.0 - abs(vec4(clamp(style, 0.0, 3.0)) - vec4(0.0, 1.0, 2.0, 3.0)), 0.0, 1.0);
}

float speckle(vec2 uv) {
	return fract(sin(dot(floor(uv), vec2(12.9898, 78.233))) * 43758.5453);
}

void fragment() {
	// The face proper; 0 on the neck rim and the joints it shares with the body,
	// and (features2 A) on the neck painted to continue the body's own tone, so
	// the whole neck takes the body's detail share and lighting.
	vec4 features2_texel = has_features2 ? texture(features2_texture, UV) : vec4(0.0, 0.0, 0.0, 1.0);
	float face = smoothstep(0.82, 0.99, face_weight) * features2_texel.a;
	vec3 painted = has_albedo ? texture(albedo_texture, UV).rgb : skin_reference.rgb;
	{
		float reference_luma = max(dot(skin_reference.rgb, LUMA), 0.005);
		vec3 detail = painted / max(skin_reference.rgb, vec3(0.005));
		float value = dot(painted, LUMA) / reference_luma;
		vec3 shading = mix(vec3(value), detail, mix(rim_detail_keep, face_detail_keep, face));
		// Alpha components carry linear body dye (not opacity). Transition
		// continuously over the neck instead of dyeing it with the calibrated
		// face colour and stepping abruptly to the torso's different colour.
		vec3 body_dye = vec3(skin_color.a, brow_color.a, hair_color.a);
		vec3 dye = mix(body_dye, skin_color.rgb, smoothstep(1.48, 1.66, rest_height));
		vec3 albedo = dye * shading;
		vec4 features = has_features ? texture(features_texture, UV) : vec4(0.0);
		vec3 features2 = features2_texel.rgb;
		albedo = mix(albedo, albedo * freckle_shade, clamp(features.r * freckles, 0.0, 1.0));
		if (stubble > 0.0) {
			float dots = mix(0.5, 1.0, speckle(UV * 1400.0));
			vec3 shadow = mix(albedo * 0.55, hair_color.rgb * 0.8, 0.5);
			albedo = mix(albedo, shadow, clamp(features2.r * stubble_gain, 0.0, 1.0) * stubble * dots);
		}
		albedo = mix(albedo, albedo * blush_tint, features2.g * blush);
		// Under a hairstyle only (the rig sets `hairline` to 0 on a bald head):
		// a hint of the hair's colour, as dark as the skin, at the scalp.
		albedo = mix(albedo, hair_color.rgb * value, features2.b * clamp(hairline, 0.0, 0.35));
		// Lips darken with the skin: the tint is scaled by how far the chosen
		// skin sits from the reference tone the lips were painted against.
		float skin_luma = clamp(dot(skin_color.rgb, LUMA) / reference_luma, 0.25, 1.25);
		albedo = mix(albedo, lip_tint.rgb * shading * skin_luma, features.g * lip_strength);
		float line = features.a * mix(lash_line, 1.0, liner);
		float closure = UV.x > face_mid_u ? lid_closure.x : lid_closure.y;
		float eye_paint = clamp(eye_style_paint.y, 0.0, 1.0);
		if (eye_paint > 0.0 && has_features) {
			// The upper line only (painted near 1), and copies of it lifted up the
			// lid, further towards the outer corner; the lift gives way as a squint or
			// blink brings the lid down and stretches it.
			float along = clamp((abs(UV.x - face_mid_u) - liner_span_u.x) / max(liner_span_u.y - liner_span_u.x, 0.001), 0.0, 1.0);
			float taper = mix(liner_taper.x, 1.0, smoothstep(liner_taper.y, liner_taper.z, along));
			float lift = liner_grow * eye_paint * taper * (1.0 - smoothstep(0.0, 0.7, max(closure, lid_closure.z)));
			float lifted = 0.0;
			for (int k = 1; k <= 4; k++) {
				lifted = max(lifted, textureLod(features_texture, UV + vec2(0.0, lift * 0.25 * float(k)), liner_grow_lod).a);
			}
			float upper = max(smoothstep(0.65, 0.9, features.a), smoothstep(0.55, 0.8, lifted));
			line = max(line, upper * liner_paint * eye_paint);
		}
		// A closing lid stretches the painted band over itself: fade it out instead.
		line *= 1.0 - smoothstep(0.1, 0.8, closure);
		albedo = mix(albedo, liner_color, clamp(line, 0.0, 1.0));
		float wing = has_brows ? features.b : 0.0;
		albedo = mix(albedo, liner_color, clamp(wing * max(liner_wing, liner_paint_wing * eye_paint), 0.0, 1.0));
		vec4 style = brow_weights(brow_style);
		float mask = has_brows ? dot(texture(brows_texture, UV), style) : features.b;
		float thickness = clamp(brow_thickness, -1.0, 1.0);
		if (has_brows && thickness > 0.0) {
			float spread = dot(textureLod(brows_texture, UV, brow_spread_lod * thickness), style);
			mask = max(mask, spread * mix(1.0, brow_spread_gain, thickness));
		}
		vec3 curve = thickness >= 0.0
			? mix(vec3(brow_floor, brow_span, brow_gamma), brow_thick, thickness)
			: mix(vec3(brow_floor, brow_span, brow_gamma), brow_thin, -thickness);
		float brow = pow(clamp((mask - curve.x) / max(curve.y, 0.01), 0.0, 1.0), curve.z) * brow_density;
		albedo = mix(albedo, brow_color.rgb, clamp(brow, 0.0, 1.0));
		ALBEDO = albedo;
		ROUGHNESS = mix(rim_roughness, mix(roughness_value, 0.5, features.g), face);
		SPECULAR = mix(rim_specular, specular_value, face);
		SSS_STRENGTH = subsurface * face;
	}
	if (has_normal) {
		NORMAL_MAP = texture(normal_texture, UV).rgb;
		NORMAL_MAP_DEPTH = normal_strength;
	}
}

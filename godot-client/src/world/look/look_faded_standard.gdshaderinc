// Look pass layer L3: a StandardMaterial3D's stand-in while OccluderFade
// fades it, opening a hole round the player.
//
// Develop fades an occluder by blending a copy of its material. The look
// pass dithers it instead (see LookFade), and the engine's own dither for a
// StandardMaterial3D, hashed alpha, is ignored by the compatibility renderer:
// its copies drew fully opaque there. So the copy is this shader, set up by
// LookFade from the source material's own properties. It covers what the
// continent's occluders use (a census of two chunks: albedo, normal,
// roughness, metallic and ambient occlusion textures, emission, vertex colour,
// alpha scissor, one- and two-sided) with the engine's own formulas for them
// (look_standard_surface.gdshaderinc), so a mesh does not change its look as
// it starts to fade; LookFade leaves a material that uses anything else to
// develop's blend.
//
// The painted_ground and painted_foliage shaders cut the same hole round the
// player (look_fade_hole.gdshaderinc), so everything that fades fades alike.
// Only these faded copies carry the discard.
//
// A shader that defines LOOK_STANDARD_RESTING (look_chroma_standard*) is the
// same stand-in at rest, with no hole: the signature-colour layer
// (LookFoliage.keep_chroma) puts it on a region's signature materials to
// scale their chroma by look_chroma, and names the faded variant for
// OccluderFade, which keeps the chroma.

#include "res://src/world/look/look_standard_surface.gdshaderinc"
#include "res://src/world/look/look_fade_hole.gdshaderinc"

uniform bool use_vertex_albedo = false;
uniform bool vertex_albedo_srgb = false;
// 0 opaque, 1 alpha-cut at alpha_scissor_threshold, 2 blended (its alpha
// becomes coverage).
uniform int alpha_mode = 0;
uniform float alpha_scissor_threshold = 0.5;
// The fade's opacity, kept as a record of it; the hole is what cuts.
uniform float look_fade = 1.0;
// The albedo's and emission's chroma, scaled about their own luminance (1
// leaves them as the source material has them).
uniform float look_chroma = 1.0;
// Cut away nearer than this view depth from a perspective camera (0 never):
// an authored tree's trunk and boughs, cut where its crown is
// (painted_foliage_body, LookProfile.CROWN_NEAR_FADE_METRES).
uniform float look_near_cut = 0.0;

vec3 look_standard_chroma(vec3 colour) {
	return max(mix(vec3(dot(colour, vec3(0.2126, 0.7152, 0.0722))), colour, look_chroma),
		vec3(0.0));
}

void vertex() {
	UV = UV * uv1_scale.xy + uv1_offset.xy;
	if (vertex_albedo_srgb) {
		COLOR.rgb = mix(pow((COLOR.rgb + vec3(0.055)) * (1.0 / 1.055), vec3(2.4)),
			COLOR.rgb * (1.0 / 12.92), lessThan(COLOR.rgb, vec3(0.04045)));
	}
}

void fragment() {
	vec4 albedo = texture(albedo_texture, UV) * albedo_color;
	if (use_vertex_albedo) {
		albedo *= COLOR;
	}
	if (alpha_mode == 1 && albedo.a < alpha_scissor_threshold) {
		discard;
	}
	// A blended source's own alpha becomes coverage, cut by the same Bayer
	// blocks as the hole's rim.
	if (alpha_mode == 2 && albedo.a < look_fade_bayer(FRAGCOORD.xy)) {
		discard;
	}
#ifndef LOOK_STANDARD_RESTING
	if (look_fade_cut(VERTEX, VIEW_MATRIX, PROJECTION_MATRIX, FRAGCOORD.xy)) {
		discard;
	}
#endif
	if (look_near_cut > 0.0 && PROJECTION_MATRIX[3][3] < 0.5 && -VERTEX.z < look_near_cut) {
		discard;
	}
	ALBEDO = look_chroma == 1.0 ? albedo.rgb : look_standard_chroma(albedo.rgb);
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
		EMISSION = look_chroma == 1.0 ? look_standard_emission(UV)
			: look_standard_chroma(look_standard_emission(UV));
	}
}

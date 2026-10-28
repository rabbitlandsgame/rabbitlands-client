// RL head eyelashes: alpha-tested cards, near-black brown with a trace of the
// actor's hair colour. lash.png carries the strands' coverage in A; without it
// the cards are drawn solid, which reads as a lash line.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx,
	alpha_to_coverage;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D strand_texture : source_color, filter_linear_mipmap, repeat_disable;
uniform bool has_texture = false;
// Lashes are near-black brown with a trace of the hair colour.
uniform float hair_share : hint_range(0.0, 1.0) = 0.12;
uniform vec3 lash_base : source_color = vec3(0.06, 0.042, 0.034);
uniform float alpha_scissor : hint_range(0.0, 1.0) = 0.35;
// MPFB's lash cards are thick; their coverage is thinned by this (per quality).
uniform float opacity : hint_range(0.0, 1.0) = 0.7;

void fragment() {
	vec4 strands = has_texture ? texture(strand_texture, UV) : vec4(1.0);
	ALBEDO = mix(lash_base, hair_color.rgb, hair_share) * mix(vec3(1.0), strands.rgb, 0.5);
	ALPHA = strands.a * opacity;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
	// With MSAA the cut edge becomes coverage rather than a hard step.
	ALPHA_ANTIALIASING_EDGE = 0.3;
	ALPHA_TEXTURE_COORDINATE = UV * vec2(textureSize(strand_texture, 0));
	ROUGHNESS = 0.6;
	SPECULAR = 0.25;
}

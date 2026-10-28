// RL head eyebrows: alpha-tested cards in the actor's brow colour.
// brow.png carries neutral strands (RGB) and coverage (A). Without it the
// strands are drawn here: hairs running along the card (U runs from the inner
// to the outer end, V across it on the MPFB-derived cards), feathered at the
// card's edges and thinning towards its ends.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D strand_texture : source_color, filter_linear_mipmap, repeat_disable;
uniform bool has_texture = false;
uniform float alpha_scissor : hint_range(0.0, 1.0) = 0.5;
// The card's painted band in V, used only by the procedural strands.
uniform vec2 band = vec2(0.5, 0.98);

void fragment() {
	vec4 strands;
	if (has_texture) {
		strands = texture(strand_texture, UV);
	} else {
		float across = (UV.y - band.x) / max(band.y - band.x, 0.001);
		float body = smoothstep(0.0, 0.25, across) * (1.0 - smoothstep(0.7, 1.0, across));
		float ends = smoothstep(0.0, 0.1, UV.x) * (1.0 - smoothstep(0.75, 1.0, UV.x));
		float hairs = 0.5 + 0.5 * sin(UV.x * 260.0 + sin(UV.y * 40.0) * 3.0 + across * 6.0);
		float coverage = body * ends * mix(0.55, 1.15, hairs);
		strands = vec4(vec3(mix(0.8, 1.1, hairs)), coverage);
	}
	ALBEDO = brow_color.rgb * strands.rgb;
	ALPHA = strands.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
	ROUGHNESS = 0.65;
	SPECULAR = 0.25;
}

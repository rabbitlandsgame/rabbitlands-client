// RL head teeth and tongue: their colour is in the vertex colours (COLOR_0,
// linear), with no texture. A little wet gloss; they sit behind the lips
// until ex_jaw_open or ex_grin parts them.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform float roughness_value : hint_range(0.0, 1.0) = 0.4;
uniform float specular_value : hint_range(0.0, 1.0) = 0.4;

void fragment() {
	ALBEDO = COLOR.rgb;
	ROUGHNESS = roughness_value;
	SPECULAR = specular_value;
}

// RL head cornea: the clear shell over each eyeball. It adds light and never
// darkens - black albedo, blended additively - so all it shows is the wet
// highlight of each light and a faint sheen of the surroundings at grazing
// angles, which is what makes an eye read as alive. HIGH quality only.
shader_type spatial;
render_mode blend_add, depth_draw_never, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform float gloss : hint_range(0.0, 1.0) = 0.035;
uniform float strength : hint_range(0.0, 1.0) = 0.6;
uniform float rim_sheen : hint_range(0.0, 1.0) = 0.06;

void fragment() {
	float grazing = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	ALBEDO = vec3(0.0);
	ROUGHNESS = gloss;
	SPECULAR = strength;
	EMISSION = vec3(rim_sheen * grazing);
}

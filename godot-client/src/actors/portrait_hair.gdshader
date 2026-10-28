shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform sampler2D base_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool use_texture = false;
uniform bool use_normal = false;
uniform vec4 hair_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform float normal_scale = 0.65;
// The hair finish slider (colour model spec revision 3, 4.7). The defaults are
// Tousled and Swept's shading; PortraitGroom sets them only for a slider
// position between the saved finishes, towards the GLB's Classic shading.
uniform float finish_roughness = 0.76;
uniform float finish_specular = 0.24;
uniform float grain_amount = 0.05;

void fragment() {
	vec3 painted = use_texture ? texture(base_texture, UV).rgb : vec3(0.72);
	// Preserve the imported painted locks. A restrained strand highlight gives
	// dark/copper hair readable depth without making a reflective plastic cap.
	float grain = (1.0 - grain_amount) + grain_amount * sin(UV.x * 284.0 + sin(UV.y * 37.0) * 1.8);
	ALBEDO = painted * hair_color.rgb * grain;
	ROUGHNESS = finish_roughness;
	SPECULAR = finish_specular;
	if (use_normal) {
		NORMAL_MAP = texture(normal_texture, UV).rgb;
		NORMAL_MAP_DEPTH = normal_scale;
	}
}

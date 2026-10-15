shader_type spatial;
render_mode depth_draw_opaque, cull_back;

uniform sampler2D soil_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D soil_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 soil_color : source_color = vec4(1.0);
uniform float soil_roughness = 1.0;
uniform float soil_normal_depth = 1.0;
uniform bool has_soil_normal = false;

void fragment() {
	// UV-space coverage stays fixed while a neighbouring scene is adopted.
	// Discard rejected grains without writing fragment alpha: alpha-hash
	// StandardMaterial3D leaks viewport alpha in the GL Compatibility renderer.
	vec2 grain = floor(UV * 80.0);
	float threshold = fract(sin(dot(grain, vec2(12.9898,78.233))) * 43758.5453);
	if (COLOR.a < threshold) { discard; }
	ALBEDO = texture(soil_texture, UV).rgb * soil_color.rgb;
	ROUGHNESS = soil_roughness;
	if (has_soil_normal) {
		NORMAL_MAP = texture(soil_normal, UV).rgb;
		NORMAL_MAP_DEPTH = soil_normal_depth;
	}
}

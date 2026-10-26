shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;
uniform sampler2D base_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool use_texture = false;
uniform bool use_normal = false;
uniform vec4 hair_color : source_color = vec4(0.24,0.10,0.04,1.0);
uniform float normal_scale = 0.45;
// Every phase is tied to imported UVs, not camera/world position or time.
// Suppress subpixel strands analytically as the footprint grows.
float strand(float phase) {
	float footprint = fwidth(phase);
	return cos(phase) * (1.0 - smoothstep(0.65, 2.5, footprint));
}
void fragment() {
	vec3 painted = use_texture ? texture(base_texture,UV).rgb : vec3(0.72);
	float luminance = dot(painted,vec3(0.2126,0.7152,0.0722));
	float flow = UV.x * 254.0 + sin(UV.y * 12.0) * 1.6;
	float fine = strand(flow) * 0.045 + strand(flow * 0.47 + UV.y * 7.0) * 0.035;
	float clumps = strand(UV.x * 42.0 + sin(UV.y * 5.0) * 2.0);
	float glaze = 0.96 + 0.10 * clumps + fine;
	vec3 contrast = mix(vec3(luminance),painted,0.75);
	contrast = max(vec3(0.0), (contrast - vec3(0.4)) * 1.17 + vec3(0.4));
	ALBEDO = contrast * hair_color.rgb * glaze;
	ROUGHNESS = clamp(0.77 + 0.03 * clumps,0.72,0.82);
	SPECULAR = 0.18;
	if (use_normal) {
		NORMAL_MAP = texture(normal_texture,UV).rgb;
		NORMAL_MAP_DEPTH = normal_scale;
	}
}

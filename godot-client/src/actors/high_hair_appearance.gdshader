shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;
uniform sampler2D base_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool use_texture = false;
uniform bool authored_locks = false;
uniform bool use_normal = false;
uniform vec4 hair_color : source_color = vec4(0.24,0.10,0.04,1.0);
uniform float normal_scale = 0.45;
// Every phase is tied to imported UVs, not camera/world position or time.
// Suppress subpixel strands analytically as the footprint grows.
float strand(float phase) {
	float footprint = fwidth(phase);
	return cos(phase) * (1.0 - smoothstep(0.65, 2.5, footprint));
}
vec3 pigment(float shine) {
	float value=dot(hair_color.rgb,vec3(0.2126,0.7152,0.0722));
	vec3 matte=mix(hair_color.rgb,vec3(value),0.10);
	float warm=smoothstep(0.0,0.35,hair_color.r-max(hair_color.g,hair_color.b));
	vec3 light=sqrt(max(hair_color.rgb,vec3(0.0)))*mix(vec3(1.0),vec3(1.0,0.90,0.73),warm);
	return mix(matte,light,0.26*shine);
}
void fragment() {
	if (authored_locks && COLOR.r > 0.5) {
		// UV.y follows each authored sweep. Bands therefore flow along the
		// lock, rather than across a cap or in screen/world coordinates.
		float flow = UV.x*92.0+sin(UV.y*9.0)*0.65;
		float fibers = strand(flow)*0.055+strand(flow*1.87+0.8)*0.025;
		float crest = pow(max(sin(UV.x*6.283185),0.0),0.65);
		float paint = (0.54+0.28*crest+fibers)*(0.88+0.24*COLOR.g);
		paint *= mix(0.62,1.0,smoothstep(0.0,0.24,UV.y));
		ALBEDO = pigment(crest)*paint;
		ROUGHNESS = 0.80;
		SPECULAR = 0.17;
	} else {
		vec3 painted = use_texture ? texture(base_texture,UV).rgb : vec3(0.72);
		float luminance = dot(painted,vec3(0.2126,0.7152,0.0722));
		float flow = UV.x * 254.0 + sin(UV.y * 12.0) * 1.6;
		float fine = strand(flow) * 0.045 + strand(flow * 0.47 + UV.y * 7.0) * 0.035;
		float clumps = strand(UV.x * 42.0 + sin(UV.y * 5.0) * 2.0);
		float glaze = 0.96 + 0.10 * clumps + fine;
		vec3 contrast = mix(vec3(luminance),painted,0.15);
		contrast = max(vec3(0.0), (contrast - vec3(0.4)) * 1.17 + vec3(0.4));
		ALBEDO = contrast * pigment(0.45+0.25*clumps) * glaze * mix(0.80,1.0,smoothstep(0.0,0.65,COLOR.b));
		ROUGHNESS = clamp(0.77 + 0.03 * clumps,0.72,0.82);
		SPECULAR = 0.18;
		if (use_normal) {
			NORMAL_MAP = texture(normal_texture,UV).rgb;
			NORMAL_MAP_DEPTH = normal_scale;
		}
	}
}

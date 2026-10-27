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
// Filter each harmonic before assembling a narrow painted strand. Its mean
// stays constant when the portrait shrinks, avoiding sparkles or dark popping.
float ribbon(float phase) {
	return clamp(0.2734375+0.4375*strand(phase)+0.21875*strand(phase*2.0)
		+0.0625*strand(phase*3.0)+0.0078125*strand(phase*4.0),0.0,1.0);
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
		float seed = COLOR.g*6.283185;
		float flow = UV.x*100.0+sin(UV.y*7.0+seed)*0.45;
		float fibers = strand(flow)*0.065+strand(flow*1.87+seed)*0.030;
		float crest = pow(max(sin(UV.x*6.283185),0.0),0.75);
		// A few broad painted strands carry the warm highlight; finer dark
		// grooves keep that highlight from reading as one smooth clay ridge.
		float painted_strand = ribbon(flow*0.43+seed);
		float grooves = ribbon(flow*1.87+seed);
		float highlight = painted_strand*crest*(0.45+0.55*sin(UV.y*3.141593));
		float paint = (0.46+0.25*crest+fibers-0.04*grooves+0.18*highlight)*(0.85+0.26*COLOR.g);
		paint *= mix(0.62,1.0,smoothstep(0.0,0.24,UV.y));
		ALBEDO = pigment(min(crest*0.8+highlight*0.9,1.3))*paint;
		ROUGHNESS = clamp(0.81-0.08*highlight+0.025*grooves,0.73,0.84);
		SPECULAR = 0.18;
		NORMAL_MAP = normalize(vec3(0.10*strand(flow+1.570796),0.0,1.0))*0.5+0.5;
		NORMAL_MAP_DEPTH = 1.0;
	} else {
		vec3 painted = use_texture ? texture(base_texture,UV).rgb : vec3(0.72);
		float luminance = dot(painted,vec3(0.2126,0.7152,0.0722));
		float flow = UV.x * 254.0 + sin(UV.y * 12.0) * 1.6;
		float fine = strand(flow) * 0.080 + strand(flow * 0.47 + UV.y * 7.0) * 0.055;
		float clumps = strand(UV.x * 42.0 + sin(UV.y * 5.0) * 2.0);
		float ribbons = ribbon(UV.x * 42.0 + sin(UV.y * 5.0) * 2.0);
		float glaze = 0.88 + 0.12 * clumps + fine + 0.10*ribbons;
		vec3 contrast = mix(vec3(luminance),painted,0.15);
		contrast = max(vec3(0.0), (contrast - vec3(0.4)) * 1.35 + vec3(0.4));
		ALBEDO = contrast * pigment(0.45+0.50*ribbons+0.10*clumps) * glaze * mix(0.80,1.0,smoothstep(0.0,0.65,COLOR.b));
		ROUGHNESS = clamp(0.80-0.05*ribbons+0.03*clumps,0.75,0.83);
		SPECULAR = 0.18;
		if (use_normal) {
			NORMAL_MAP = texture(normal_texture,UV).rgb;
			NORMAL_MAP_DEPTH = normal_scale;
		}
	}
}

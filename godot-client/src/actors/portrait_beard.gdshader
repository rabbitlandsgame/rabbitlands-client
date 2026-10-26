shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform vec4 hair_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform float eye_height = 0.075;
uniform float mouth_height = 0.0145;
uniform int style = 5;
uniform float finish_detail = 0.50;

float filtered_stroke(float phase) {
	return cos(phase)*(1.0-smoothstep(0.65,2.5,fwidth(phase)));
}

float moustache_coverage(float x, float y) {
	float centre = -0.052 - 0.014 * pow(clamp(x / 0.042, 0.0, 1.0), 1.4);
	centre += filtered_stroke(x*1700.0+sin(x*240.0))*0.00045;
	float width = mix(0.0085, 0.0045, smoothstep(0.010, 0.039, x));
	float mask = smoothstep(centre - width, centre - width + 0.0025, y);
	mask *= 1.0 - smoothstep(centre + width - 0.0025, centre + width, y);
	return mask * smoothstep(0.001, 0.004, x) * (1.0 - smoothstep(0.036, 0.045, x));
}

float full_beard_coverage(vec2 point, float z) {
	float y = point.y - mouth_height - 0.063;
	float x = abs(point.x);
	float front = smoothstep(-0.012, 0.014, z);
	float tuft = sin(point.x * 580.0 + sin(point.x * 137.0)) * 0.0012 * (1.0-smoothstep(0.65,2.0,fwidth(point.x*580.0)));
	float cheek_top = -0.073 + 0.033 * smoothstep(0.014, 0.070, x) + tuft;
	float jaw = 1.0 - smoothstep(cheek_top - 0.003, cheek_top + 0.004, y);
	float mouth = length(vec2(point.x / 0.024, (y + 0.063) / 0.008));
	jaw *= smoothstep(0.95, 1.18, mouth);
	float moustache = moustache_coverage(x, y);
	float soul = (1.0 - smoothstep(0.007, 0.012, x)) * smoothstep(-0.098, -0.088, y);
	soul *= 1.0 - smoothstep(-0.082, -0.075, y);
	float sideburn = smoothstep(0.056, 0.064, x) * (1.0 - smoothstep(0.075, 0.082, x));
	sideburn *= smoothstep(-0.083, -0.064, y) * (1.0 - smoothstep(0.015, 0.033, y));
	sideburn *= smoothstep(-0.010, -0.002, z) * (1.0 - smoothstep(0.010, 0.018, z));
	float edge = 1.0 - smoothstep(0.073, 0.086, x);
	// Follow a rounded jaw line instead of carrying a square patch down the
	// front of the neck. This stays in canonical face space under every slider.
	float lower_edge = -0.122 + 0.026*smoothstep(0.014,0.067,x) + tuft*0.65;
	float bottom = smoothstep(lower_edge-0.008,lower_edge+0.009,y);
	return clamp(max(max(jaw, max(moustache, soul)) * front, sideburn) * edge * bottom, 0.0, 1.0);
}

float coverage(vec2 point, float z) {
	if (style == 5) { return full_beard_coverage(point, z); }
	float y = point.y - mouth_height - 0.063;
	float x = abs(point.x);
	float front = smoothstep(-0.012, 0.014, z);
	float edge = 1.0 - smoothstep(0.065, 0.085, x);
	float tuft = sin(point.x * 580.0 + sin(point.x * 137.0)) * 0.0015 * (1.0-smoothstep(0.65,2.0,fwidth(point.x*580.0)));
	float bottom = smoothstep(-0.123 + tuft, -0.100 + tuft, y);
	float cheek_top = -0.060 + 0.028 * smoothstep(0.015, 0.060, x) + tuft;
	float jaw = 1.0 - smoothstep(cheek_top - 0.005, cheek_top + 0.006, y);
	float mouth = length(vec2(point.x / 0.024, (y + 0.063) / 0.008));
	float lips_clear = smoothstep(0.90, 1.25, mouth);
	float moustache = smoothstep(-0.066, -0.060, y) * (1.0 - smoothstep(-0.047, -0.040, y));
	moustache *= 1.0 - smoothstep(0.030, 0.046, x);
	float mask = max(jaw * lips_clear, moustache);
	if (style == 2) { mask = moustache_coverage(x, y); }
	if (style == 3) {
		float chin = (1.0 - smoothstep(-0.081, -0.070, y)) * lips_clear;
		mask = max(chin * (1.0 - smoothstep(0.026, 0.042, x)), moustache_coverage(x, y));
	}
	return clamp(mask * front * edge * bottom, 0.0, 1.0);
}

void fragment() {
	// UV1/COLOR.g stay the current fitted skin anchor for High face fitting.
	// Canonical UV2/COLOR.b carry coverage/paint through every facial slider.
	vec2 anchor = UV2;
	float y = anchor.y-mouth_height-0.063;
	float side = sign(anchor.x)*smoothstep(0.012,0.045,abs(anchor.x));
	float growth = anchor.x-side*0.43*(y+0.083);
	growth += side*0.0025*sin((y+0.095)*48.0);
	float phase = growth*2200.0+sin(growth*173.0+anchor.y*91.0)*0.65;
	float moustache = smoothstep(-0.074,-0.064,y);
	float lip_curve = -0.052-0.014*pow(clamp(abs(anchor.x)/0.042,0.0,1.0),1.4);
	float upper_phase = (y-lip_curve)*2400.0+sin(anchor.x*121.0)*0.9;
	float fibers = mix(filtered_stroke(phase),filtered_stroke(upper_phase),moustache);
	float clumps = filtered_stroke(growth*520.0+sin(growth*113.0+anchor.y*31.0)*1.15);
	float broad = 0.82+0.075*clumps+0.085*finish_detail*fibers;
	broad *= 0.96+0.04*sin(growth*147.0+anchor.y*46.0);
	ALBEDO = hair_color.rgb*broad;
	ROUGHNESS = 0.86;
	SPECULAR = 0.16;
	float lips = length(vec2(anchor.x/0.026,(y+0.063)/0.0095));
	float lip_clear = smoothstep(1.00,1.23,lips);
	ALPHA = coverage(anchor,COLOR.b-0.2)*lip_clear;
	ALPHA_SCISSOR_THRESHOLD = 0.36;
}

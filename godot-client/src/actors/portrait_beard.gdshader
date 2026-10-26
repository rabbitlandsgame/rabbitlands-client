shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform vec4 hair_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform float eye_height = 0.075;
uniform int style = 5;

float moustache_coverage(float x, float y) {
	float centre = -0.053 - 0.011 * pow(x / 0.040, 2.0);
	float mask = smoothstep(centre - 0.008, centre - 0.004, y);
	mask *= 1.0 - smoothstep(centre + 0.003, centre + 0.007, y);
	return mask * smoothstep(0.002, 0.007, x) * (1.0 - smoothstep(0.033, 0.043, x));
}

float full_beard_coverage(vec2 point, float z) {
	float y = point.y - eye_height;
	float x = abs(point.x);
	float front = smoothstep(-0.012, 0.014, z);
	float tuft = sin(point.x * 580.0 + sin(point.x * 137.0)) * 0.0012;
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
	float bottom = smoothstep(-0.123 + tuft, -0.100 + tuft, y);
	return clamp(max(max(jaw, max(moustache, soul)) * front, sideburn) * edge * bottom, 0.0, 1.0);
}

float coverage(vec2 point, float z) {
	if (style == 5) { return full_beard_coverage(point, z); }
	float y = point.y - eye_height;
	float x = abs(point.x);
	float front = smoothstep(-0.012, 0.014, z);
	float edge = 1.0 - smoothstep(0.065, 0.085, x);
	float tuft = sin(point.x * 580.0 + sin(point.x * 137.0)) * 0.0015;
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
	// UVs are measured head-space metres, independent of each race's atlas.
	// Fine broken strokes and broad lock shading share the fitted head surface;
	// no texture atlas, transparency layer or simulated strands are required.
	float strands = sin(UV.x * 17300.0 + sin(UV.y * 930.0) * 1.2);
	float locks = 0.92 + 0.08 * smoothstep(-0.8, 0.8,
		sin(UV.x * 950.0 + UV.y * 140.0 + sin(UV.y * 200.0) * 0.8));
	float fiber = mix(0.96, 1.02, smoothstep(-0.8, 0.8, strands));
	// Average subpixel strokes instead of letting them alias during motion.
	float visible_fibers = 1.0 - smoothstep(0.6, 1.5, fwidth(UV.x * 17300.0));
	fiber = mix(0.99, fiber, visible_fibers);
	ALBEDO = hair_color.rgb * fiber * locks * 0.78;
	ROUGHNESS = 0.86;
	SPECULAR = 0.18;
	ALPHA = coverage(UV, COLOR.g - 0.2);
	ALPHA_SCISSOR_THRESHOLD = 0.36;
}

shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform vec4 hair_color : source_color = vec4(0.24, 0.10, 0.04, 1.0);
uniform float density = 1.0;
uniform float eye_height = 0.075;
uniform int style = 5;

float coverage(vec2 point, float z) {
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
	if (style == 2) { mask = moustache; }
	if (style == 3) { mask = max(jaw * lips_clear * (1.0 - smoothstep(0.026, 0.042, x)), moustache); }
	return clamp(mask * front * edge * bottom, 0.0, 1.0);
}

void fragment() {
	// UVs are measured head-space metres, independent of each race's atlas.
	// Fine broken strokes and broad lock shading share the fitted head surface;
	// no texture atlas, transparency layer or simulated strands are required.
	float strands = sin(UV.x * 17300.0 + sin(UV.y * 930.0) * 1.2);
	float broken = sin(UV.y * 15600.0 + UV.x * 9400.0);
	float locks = 0.92 + 0.08 * smoothstep(-0.8, 0.8,
		sin(UV.x * 950.0 + UV.y * 140.0 + sin(UV.y * 200.0) * 0.8));
	float fiber = mix(0.96, 1.02, smoothstep(-0.8, 0.8, strands));
	ALBEDO = hair_color.rgb * fiber * locks * 0.78;
	ROUGHNESS = 0.86;
	SPECULAR = 0.18;
	float stubble = smoothstep(0.25, 0.72, strands * broken);
	ALPHA = coverage(UV, COLOR.g) * mix(stubble, 1.0, density) * (0.91 + 0.09 * broken);
	ALPHA_SCISSOR_THRESHOLD = 0.36;
}

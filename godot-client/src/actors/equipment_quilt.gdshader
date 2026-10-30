shader_type spatial;
render_mode cull_disabled;
uniform sampler2D cloth_texture : source_color, filter_linear_mipmap, repeat_enable;
// The source quilt atlas contains isolated black paint artifacts. Borrow
// nearby fabric colour only inside those dark pixels; keep the quilt UVs,
// stitching, folds and all ordinary fabric pixels in their authored places.
void fragment() {
	vec3 cloth = texture(cloth_texture, UV).rgb;
	float darkest = max(cloth.r, max(cloth.g, cloth.b));
	if (darkest < 0.105) {
		vec3 fabric = vec3(0.0);
		float total = 0.0;
		for (int radius = 1; radius <= 4; radius++) {
			for (int direction = 0; direction < 8; direction++) {
				float angle = float(direction) * 0.785398163;
				vec2 offset = vec2(cos(angle), sin(angle)) * float(radius) * 0.008;
				vec3 neighbor = texture(cloth_texture, UV + offset).rgb;
				float peak = max(neighbor.r, max(neighbor.g, neighbor.b));
				float weight = smoothstep(0.11, 0.18, peak) / float(radius * radius);
				fabric += neighbor * weight;
				total += weight;
			}
		}
		if (total > 0.0) cloth = mix(cloth, fabric / total, 1.0 - smoothstep(0.06, 0.105, darkest));
	}
	ALBEDO = cloth;
	ROUGHNESS = 0.8;
}

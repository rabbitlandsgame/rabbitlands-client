shader_type canvas_item;
render_mode unshaded;

uniform float opacity : hint_range(0.0, 0.8) = 0.30;

void fragment() {
	float left = smoothstep(0.0, 0.035, UV.x);
	float right = 1.0 - smoothstep(0.42, 1.0, UV.x);
	float top = smoothstep(0.0, 0.09, UV.y);
	float bottom = 1.0 - smoothstep(0.65, 1.0, UV.y);
	COLOR = vec4(vec3(0.015, 0.018, 0.016), opacity * left * right * top * bottom);
}

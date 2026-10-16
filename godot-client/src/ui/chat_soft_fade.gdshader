shader_type canvas_item;
render_mode unshaded;

uniform float opacity : hint_range(0.0, 0.8) = 0.30;
uniform float panel_width = 490.0;
uniform float backdrop_width = 650.0;
uniform float right_fade_width = 160.0;

void fragment() {
	float x = UV.x * backdrop_width;
	float left = smoothstep(0.0, 0.025 * panel_width, x);
	float right = 1.0 - smoothstep(panel_width, panel_width + right_fade_width, x);
	float top = smoothstep(0.0, 0.04, UV.y);
	float bottom = 1.0 - smoothstep(0.94, 1.0, UV.y);
	COLOR = vec4(vec3(0.015, 0.018, 0.016), opacity * left * right * top * bottom);
}

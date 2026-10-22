shader_type canvas_item;
render_mode unshaded;

uniform float opacity : hint_range(0.0, 1.0) = 0.30;
uniform float panel_width = 490.0;
uniform float panel_height = 240.0;
uniform vec4 backdrop_color : source_color = vec4(0.015, 0.018, 0.016, 1.0);

void fragment() {
	// Keep every feathered edge the same size when the window is resized.
	float x = UV.x * panel_width;
	float y = UV.y * panel_height;
	float left = smoothstep(0.0, 8.0, x);
	float right = 1.0 - smoothstep(panel_width - 16.0, panel_width, x);
	float top = smoothstep(0.0, 8.0, y);
	float bottom = 1.0 - smoothstep(panel_height - 12.0, panel_height, y);
	// Fully opaque means the complete rectangle, including its outer edges.
	float coverage = opacity >= 1.0 ? 1.0 : left * right * top * bottom;
	COLOR = vec4(backdrop_color.rgb, opacity * backdrop_color.a * coverage);
}

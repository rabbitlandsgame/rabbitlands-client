shader_type canvas_item;
render_mode unshaded;

uniform vec4 image_rect = vec4(0.0);
uniform bool rounded = false;
uniform int hud_palette = 0;
varying vec2 map_local_position;

void vertex() {
	map_local_position = VERTEX;
}

void fragment() {
	vec2 offset = map_local_position - image_rect.xy;
	if (any(lessThan(offset, vec2(0.0))) || any(greaterThan(offset, image_rect.zw))) {
		discard;
	}
	if (rounded) {
		vec2 centre_offset = offset - image_rect.zw * 0.5;
		float radius = min(image_rect.z, image_rect.w) * 0.5;
		if (dot(centre_offset, centre_offset) > radius * radius) {
			discard;
		}
	}
	float luminance = dot(COLOR.rgb, vec3(0.2126, 0.7152, 0.0722));
	if (hud_palette == 1) {
		COLOR.rgb = mix(vec3(0.22, 0.15, 0.08), vec3(0.91, 0.81, 0.59), luminance);
	} else if (hud_palette == 2) {
		COLOR.rgb = mix(vec3(0.10, 0.13, 0.12), vec3(0.48, 0.51, 0.46), luminance);
	}
}

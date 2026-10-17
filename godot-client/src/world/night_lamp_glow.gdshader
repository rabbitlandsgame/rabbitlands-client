shader_type spatial;
// The lit lantern itself: a soft additive halo at each lamp head, drawn by
// NightLamps as one MultiMesh per streamed cell. Each instance's colour is
// its lamp's; `strength` is the hour's (0 by day, 1 at night), so one
// parameter lights or dims every lamp on the map. A slow flicker per lamp
// keeps a row of lanterns from pulsing in step.
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform float strength : hint_range(0.0, 1.0) = 0.0;
uniform float core = 1.6;
// How far towards the camera the halo is drawn, as a fraction of its size.
// The flame sits inside the lantern, whose glass is part of one opaque
// material, so a halo left at the flame is hidden by its own lantern; drawn
// half its size nearer, it shows in front of the glass and is still hidden by
// a wall between the lamp and the camera.
uniform float pull = 0.5;

varying vec4 lamp_colour;
varying float flicker;

void vertex() {
	// Face the camera, keeping the instance's scale (the halo's size).
	float size = length(MODEL_MATRIX[0].xyz);
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0] * size, INV_VIEW_MATRIX[1] * size,
		INV_VIEW_MATRIX[2] * size, MODEL_MATRIX[3]);
	vec3 centre = MODELVIEW_MATRIX[3].xyz;
	MODELVIEW_MATRIX[3].xyz = centre - normalize(centre) * min(pull * size, length(centre) * 0.5);
	lamp_colour = COLOR;
	float phase = float(INSTANCE_ID) * 1.618;
	flicker = 0.9 + 0.06 * sin(TIME * 7.3 + phase) + 0.04 * sin(TIME * 13.1 + phase * 2.0);
}

void fragment() {
	vec2 centred = UV * 2.0 - 1.0;
	float r = length(centred);
	// A bright core and a long soft falloff: reads as a flame behind glass up
	// close and as a point of light across the harbour.
	float halo = pow(clamp(1.0 - r, 0.0, 1.0), 2.2);
	float glow = halo + core * pow(clamp(1.0 - r * 2.6, 0.0, 1.0), 3.0);
	ALBEDO = lamp_colour.rgb * glow * strength * flicker;
	ALPHA = 1.0;
}

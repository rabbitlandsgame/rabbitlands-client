shader_type spatial;
// A gull's wingbeat (PresentationEffects): the wings flap about the body, the
// tips furthest, each bird in its own phase, and every few beats a glide.
render_mode cull_disabled, shadows_disabled;

varying vec3 tint;

void vertex() {
	float phase = float(INSTANCE_ID) * 2.399;
	float beat = sin(TIME * 7.5 + phase);
	// Glide for part of each cycle: the wings hold just above level.
	float glide = smoothstep(0.2, 0.6, sin(TIME * 0.9 + phase * 0.5));
	float reach = abs(VERTEX.x);
	VERTEX.y += mix(beat * 0.34, 0.05, glide) * reach;
	tint = COLOR.rgb;
}

void fragment() {
	ALBEDO = tint;
	ROUGHNESS = 0.9;
}

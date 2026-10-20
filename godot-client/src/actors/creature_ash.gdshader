shader_type spatial;
render_mode cull_disabled;

#include "creature_dissolve.gdshaderinc"

uniform float dissolve_seconds = 4.0;
varying float ash_visibility;

void vertex() {
	vec3 origin = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	vec3 p = (dissolve_to_actor * vec4(origin, 1.0)).xyz;
	float release = dissolve_release(p);
	float age = (dissolve_progress - release) * dissolve_seconds;
	float lifetime = min(1.35, (1.0 - release) * dissolve_seconds);
	float seed = INSTANCE_CUSTOM.r;
	float alive = step(0.0, age) * (1.0 - step(lifetime, age));
	float t = clamp(age / max(lifetime, 0.01), 0.0, 1.0);
	VERTEX *= alive * (1.0 - t * t);
	// Wind carries the dust about a metre, with a little rise and curl.
	vec3 drift = vec3(0.45 + seed * 0.4, 0.28 + seed * 0.35, 0.16 - seed * 0.32) * max(age, 0.0);
	drift += vec3(sin(age * 4.0 + seed * 30.0), 0.0, cos(age * 3.0 + seed * 30.0)) * t * 0.10;
	VERTEX += (inverse(MODEL_MATRIX) * vec4(drift, 0.0)).xyz;
	ash_visibility = alive;
}

void fragment() {
	if (ash_visibility < 0.5) { discard; }
	ALBEDO = COLOR.rgb * 0.38;
	ROUGHNESS = 1.0;
	SPECULAR = 0.1;
}

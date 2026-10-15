shader_type spatial;
render_mode cull_disabled;
uniform sampler2D land_mask : filter_linear, repeat_disable;
varying vec3 world_position;

void vertex() {
	world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = world_position.xz;
	float a = sin(dot(p,vec2(.59,.26))+TIME*.8);
	float b = sin(dot(p,vec2(-.24,.72))-TIME*.55);
	float ripples = sin(dot(p,vec2(2.7,1.5))+a*1.1+TIME)*.5+.5;
	vec2 uv = vec2(world_position.x+.5,-world_position.z+.5)/120.0;
	float near_land = 0.0;
	for (int x=-2;x<=2;x++) {
		for (int y=-2;y<=2;y++) {
			near_land += texture(land_mask,uv+vec2(float(x),float(y))/120.0).r/25.0;
		}
	}
	float in_map = step(0.0,uv.x)*step(uv.x,1.0)*step(0.0,uv.y)*step(uv.y,1.0);
	near_land *= in_map;
	vec3 deep = vec3(.05,.16,.22);
	vec3 shallow = vec3(.13,.29,.29);
	ALBEDO = mix(deep,shallow,clamp(near_land*1.5,0.0,1.0)) + vec3(.009,.018,.02)*ripples;
	float foam = smoothstep(.2,.52,near_land)*(0.35+0.65*pow(ripples,5.0));
	ALBEDO = mix(ALBEDO,vec3(.38,.56,.54),foam*.55);
	NORMAL_MAP = vec3(.5+a*.08,.5+b*.065,1.0);
	NORMAL_MAP_DEPTH = .55;
	ROUGHNESS = .52;
	METALLIC = .08;
	SPECULAR = .3;
}

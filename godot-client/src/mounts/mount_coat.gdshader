shader_type spatial;
render_mode cull_back;
uniform sampler2D coat_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D coat_normal : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool has_normal = false;
uniform bool use_vertex_colour = false;
uniform bool use_metallic_map = false;
uniform bool use_roughness_map = false;
uniform sampler2D metallic_map : filter_linear_mipmap, repeat_enable;
uniform sampler2D roughness_map : filter_linear_mipmap, repeat_enable;
uniform vec4 metallic_channel = vec4(0.0,0.0,1.0,0.0);
uniform vec4 roughness_channel = vec4(0.0,1.0,0.0,0.0);
uniform float normal_strength = 1.0;
uniform vec4 base_colour : source_color = vec4(1.0);
uniform vec4 coat_colour : source_color = vec4(1.0);
uniform vec4 accent_colour : source_color = vec4(0.2,0.2,0.2,1.0);
uniform float coat_strength = 0.8;
uniform float pattern_strength = 0.7;
uniform float pattern_scale = 7.0;
uniform int pattern = 0;
uniform float roughness = 0.8;
uniform float metallic = 0.0;
varying vec3 rest_position;
varying float coat_mask;
void vertex() {
	rest_position = CUSTOM0.xyz;
	coat_mask = COLOR.a;
}
float hash(vec3 p) { return fract(sin(dot(p, vec3(127.1,311.7,74.7))) * 43758.5453); }
void fragment() {
	vec3 original = texture(coat_texture, UV).rgb * base_colour.rgb;
	if (use_vertex_colour) { original *= COLOR.rgb; }
	float light = dot(original, vec3(0.2126,0.7152,0.0722));
	// Preserve dark eyes, noses, hooves and the original coat's spots/stripes.
	float chroma = max(max(original.r,original.g),original.b) - min(min(original.r,original.g),original.b);
	float mask = coat_mask * mix(smoothstep(0.015,0.12,light),1.0,smoothstep(0.05,0.25,chroma));
	vec3 recoloured = coat_colour.rgb * (0.35 + 0.85 * sqrt(light));
	vec3 colour = mix(original, recoloured, coat_strength * mask);
	vec3 p = rest_position * pattern_scale;
	float markings = 0.0;
	if (pattern == 1) {
		// Rest-space cells stay on the skin while the mount articulates.
		vec3 cell = floor(p);
		vec3 center = vec3(hash(cell),hash(cell+3.1),hash(cell+7.7));
		markings = 1.0 - smoothstep(0.24,0.40,length(fract(p)-mix(vec3(0.5),center,0.5)));
	} else if (pattern == 2) {
		float wave = sin(p.z * 4.5 + sin(p.y * 2.3) + 0.6*sin(p.x*3.0));
		markings = smoothstep(0.35,0.70,wave);
	}
	ALBEDO = mix(colour, accent_colour.rgb * (0.4 + light), markings * pattern_strength * mask);
	ROUGHNESS = roughness;
	METALLIC = metallic;
	if (use_metallic_map) { METALLIC *= dot(texture(metallic_map,UV),metallic_channel); }
	if (use_roughness_map) { ROUGHNESS *= dot(texture(roughness_map,UV),roughness_channel); }
	if (has_normal) { NORMAL_MAP = texture(coat_normal,UV).rgb; NORMAL_MAP_DEPTH = normal_strength; }
}

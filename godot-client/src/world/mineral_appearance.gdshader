shader_type spatial;
// Retain the imported rock's painted value/facets. Recolour its purple vein
// pigment per resource; this never modifies or regenerates a source bitmap.
uniform sampler2D base_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 stone_tint : source_color = vec4(0.5,0.5,0.5,1.0);
uniform vec4 mineral_tint : source_color = vec4(0.6,0.4,0.2,1.0);
void fragment() {
    vec3 paint = texture(base_texture,UV).rgb;
    float vein = smoothstep(0.02,0.12,min(paint.r,paint.b)-paint.g);
    float value = dot(paint,vec3(0.2126,0.7152,0.0722));
    ALBEDO = mix(stone_tint.rgb*value*1.5,mineral_tint.rgb*(0.45+value),vein);
    ROUGHNESS = 0.95;
}

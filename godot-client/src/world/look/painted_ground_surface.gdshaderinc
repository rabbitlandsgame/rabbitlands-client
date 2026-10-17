// Look pass layer L2: the body of a painted ground material.
//
// Stands in for the StandardMaterial3D a ground mesh imported with, keeping
// what those materials use - the albedo texture and tint, UV scale and
// offset, the vertex colour where the source took its albedo from it, the
// normal map, roughness and specular - and passing the result through
// look_paint. The painted_ground*.gdshader files include this after choosing
// the render mode the source material had (culling, and whether it blends).
//
// A shader that defines LOOK_GROUND_ALPHA writes alpha as the source did, and
// when use_vertex_alpha is set cuts it by the vertex alpha. The continent
// exporter writes every authored ground patch's and walk deck's coverage into
// vertex alpha (the patch's region weight, the road's edge), but the imported
// StandardMaterial3D never reads vertex colour on a blended surface, so on
// develop those edges are hard steps along the terrain cells. Here the
// coverage is cut at look_rim.x with a narrow step and a noise wobble: a
// broken brush edge, not an airbrushed ramp (see LookProfile.DECK_RIM). The
// cut also wanders in broad lobes a few metres across (look_rim_lobe), so a
// rectangle's side or an ellipse's arc does not read as a ruled line, and
// follows the texture's own grain (look_rim_grain): paving ends stone by
// stone and gravel grain by grain, the light stones outlasting the dark
// joints, as worn ground does.
//
// A region may lay a class texture over its decks and patches
// (LookProfile.CLASS_TEXTURES): its detail, mapped in continent metres, is
// rescaled to the source texture's own mean colour, so the paint classes,
// the palette and every look trim see the colour they always did and only
// the surface's structure changes.
//
// A shader that also defines LOOK_GROUND_EDGE_BAND (the walk decks) darkens
// the ground beyond that edge by look_edge_band, where the deck's geometry
// runs on but its coverage has stopped: the dark verge edging that frames a
// road, a curb where it meets paving. The band has to darken what lies under
// it, so it is black with alpha look_edge_band, and it is drawn a few
// centimetres behind the deck's own plane: road decks overlap and are
// coplanar, and without that one road's band drew a dark line across the
// other road's middle wherever two met.

#include "res://src/world/look/painted_ground_paint.gdshaderinc"

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 albedo_color : source_color = vec4(1.0);
uniform bool use_vertex_albedo = false;
uniform bool vertex_albedo_srgb = false;
uniform bool use_vertex_alpha = false;
// How opaque the surface is inside its coverage (below 1, a glaze).
uniform float look_opacity = 1.0;
// Where the vertex alpha coverage is cut: threshold, half-width of the step,
// noise wobble.
uniform vec3 look_rim = vec3(0.5, 0.06, 0.1);
uniform float look_rim_noise_metres = 0.9;
// Broad lobes in the cut: amplitude (vertex alpha) and size in metres.
uniform vec2 look_rim_lobe = vec2(0.0, 5.0);
// How far the texture's grain moves the cut (vertex alpha per unit of
// relative luminance): light stones stay, dark joints go first.
uniform float look_rim_grain = 0.0;
// A class texture laid over the source's (look_class_metres 0: none), and how
// much of its own hue it keeps against the source's mean colour.
uniform sampler2D look_class_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float look_class_metres = 0.0;
uniform float look_class_hue = 0.5;
// Darkening beyond a road's edge, and the vertex alpha where it begins.
uniform float look_edge_band = 0.0;
uniform float look_edge_band_from = 0.1;
// The band's strength where the road runs through pale paving: a curb.
uniform float look_edge_band_paving = 0.0;
uniform float look_edge_band_push = 0.03;
// The occluder fade (LookFade): OccluderFade drives look_fade_open on a
// faded copy, which then opens the hole round the player that every faded
// look material cuts (look_fade_hole.gdshaderinc). With the pass on the
// ground is never indexed as an occluder, so this is the safety net that
// keeps a painted ground surface from staying solid if it ever is.
uniform float look_fade = 1.0;
#ifdef LOOK_GROUND_ALPHA
#include "res://src/world/look/look_fade_hole.gdshaderinc"
#endif
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_normal_texture = false;
uniform float normal_scale = 1.0;
uniform float roughness_value : hint_range(0.0, 1.0) = 1.0;
uniform float metallic_value : hint_range(0.0, 1.0) = 0.0;
uniform float specular_value : hint_range(0.0, 1.0) = 0.5;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);

// The continent's exports store continent positions in the mesh and place
// them with translation-only wrappers, so object space is the continent frame
// the biome blend paints in: the variation runs on unbroken across chunk
// seams and from terrain onto patches, and a crossing that rebases the world
// does not slide it under the player.
varying vec2 look_ground_xz;

void vertex() {
	UV = UV * uv1_scale.xy + uv1_offset.xy;
	look_ground_xz = VERTEX.xz;
}

void fragment() {
	vec4 texel = texture(albedo_texture, UV);
	// The texture's mean colour: the class texture is rescaled to it, and the
	// grain the cut follows is measured against it.
	vec3 texel_mean = textureLod(albedo_texture, UV, 16.0).rgb;
	if (look_class_metres > 0.0) {
		vec2 class_uv = look_ground_xz / look_class_metres;
		vec3 detail = texture(look_class_texture, class_uv).rgb;
		vec3 detail_mean = max(textureLod(look_class_texture, class_uv, 16.0).rgb, vec3(0.02));
		vec3 recoloured = detail * texel_mean / detail_mean;
		vec3 own_hue = detail * (look_luma(texel_mean) / max(look_luma(detail_mean), 0.02));
		texel.rgb = mix(recoloured, own_hue, look_class_hue);
	}
	vec3 albedo = texel.rgb * albedo_color.rgb;
	vec3 vertex_colour = COLOR.rgb;
	if (vertex_albedo_srgb) {
		vertex_colour = mix(pow((vertex_colour + vec3(0.055)) * (1.0 / 1.055), vec3(2.4)),
			vertex_colour * (1.0 / 12.92), lessThan(vertex_colour, vec3(0.04045)));
	}
	// The smallest mip is the texture's mean colour: the reference the paint
	// classes and lifts by, so a lifted path keeps its texture's grain.
	vec3 reference = texel_mean * albedo_color.rgb;
	if (use_vertex_albedo) {
		albedo *= vertex_colour;
		reference *= vertex_colour;
	}
	vec3 world_normal = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
	if (look_debug > 0) {
		ALBEDO = vec3(0.0);
		EMISSION = look_debug_colour(reference, vertex_colour, look_ground_xz);
	} else {
		ALBEDO = look_paint(albedo, reference, vertex_colour, look_ground_xz, world_normal);
	}
	ROUGHNESS = roughness_value;
	METALLIC = metallic_value;
	SPECULAR = specular_value;
	if (has_normal_texture) {
		NORMAL_MAP = texture(normal_texture, UV).rgb;
		NORMAL_MAP_DEPTH = normal_scale;
	}
#ifdef LOOK_GROUND_ALPHA
	if (look_fade_cut(VERTEX, VIEW_MATRIX, PROJECTION_MATRIX, FRAGCOORD.xy)) {
		discard;
	}
	float coverage = 1.0;
	float band = 0.0;
	if (use_vertex_alpha) {
		vec2 lobe_p = look_ground_xz / look_rim_lobe.y;
		float lobe = 0.65 * look_value_noise(lobe_p + vec2(41.3, 17.9))
			+ 0.35 * look_value_noise(lobe_p * 2.7 + vec2(7.1, 29.3)) - 0.5;
		float grain = look_luma(texel.rgb) / max(look_luma(texel_mean), 0.02) - 1.0;
		float weight = COLOR.a + (look_value_noise(look_ground_xz / look_rim_noise_metres)
			- 0.5) * 2.0 * look_rim.z + lobe * 2.0 * look_rim_lobe.x
			+ clamp(grain, -1.0, 1.0) * look_rim_grain;
		coverage = smoothstep(look_rim.x - look_rim.y, look_rim.x + look_rim.y, weight);
		if (look_debug == 0) {
			band = mix(look_edge_band, look_edge_band_paving,
					look_paving_at(look_ground_xz)) * (1.0 - coverage)
				* smoothstep(look_edge_band_from, look_edge_band_from + 0.1, weight);
		}
	}
	float covered = texel.a * albedo_color.a * coverage * look_opacity;
#ifdef LOOK_GROUND_CUTOUT
	// Coverage on MASK patches must reach the ground edge. Keep opaque depth
	// and viewport alpha while breaking the old solid rectangular boundary.
	vec2 grain = floor(UV * 80.0);
	float threshold = fract(sin(dot(grain, vec2(12.9898, 78.233))) * 43758.5453);
	if (covered <= threshold) { discard; }
#else
	// The road over what lies beneath, and beyond it that ground darkened:
	// covered * road + (1 - covered) * (1 - band) * ground.
	ALPHA = 1.0 - (1.0 - covered) * (1.0 - band);
	ALBEDO *= covered / max(ALPHA, 0.0001);
#endif
#ifdef LOOK_GROUND_EDGE_BAND
	vec3 pushed = VERTEX + normalize(VERTEX) * (band > 0.0 ? look_edge_band_push : 0.0);
	vec4 clip = PROJECTION_MATRIX * vec4(pushed, 1.0);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	DEPTH = clip.z / clip.w * 0.5 + 0.5;
#else
	DEPTH = clip.z / clip.w;
#endif
#endif
#endif
}

// RL head eyes, on the MPFB eye layout: two eyeball islands and a cornea
// shell packed into the texture's top-right corner.
//
// The shell is discarded - the pass is opaque - and the eyeball paints the
// cornea's wet gloss itself: a low roughness over the iris and a small
// catchlight. With eye.png the iris (its alpha) takes the actor's eye colour
// through the texture's own neutral detail and the sclera keeps the texture;
// without it, the iris, limbus and pupil are drawn around the iris centres
// RLHeadLibrary measured off the eye mesh. `eye_look` turns both irises by
// a look angle in radians (x towards model +X, y up) through the same fit.
// `eye_style_paint.x` (iris_scale, derived from the eye_style identity control
// by the rig) draws the iris and pupil larger about the painted iris's centre
// (`painted_iris_*`: eye.png's iris discs, from the texture manifest; the
// fitted iris when unknown) and draws the sclera in out to IRIS_RING of those
// radii to make room, so a stylised eye keeps one continuous eyeball texture.
// The upper lid's shadow over the top of the iris: a hint of it on every eye
// (`iris_lid_shade_base`) and, with `eye_style_paint.y` (eye_paint, from
// eye_style), the stylised eye's painted shadow, as dark as `iris_lid_shade`.
// It stays under the lid (the band is measured from the iris's resting centre,
// not the look-shifted one) and takes the iris's gloss and reflections with it;
// the catchlight stays.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

#include "res://src/actors/rl_head/rl_head_instance.gdshaderinc"

uniform sampler2D eye_texture : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform bool has_texture = false;
uniform vec2 cornea_uv_min = vec2(0.875, 0.875);
uniform vec2 iris_uv_0 = vec2(0.25, 0.6);
uniform vec2 look_x_0 = vec2(0.1, 0.0);
uniform vec2 look_y_0 = vec2(0.0, 0.1);
uniform float iris_radius_0 = 0.085;
uniform vec2 iris_uv_1 = vec2(0.75, 0.2);
uniform vec2 look_x_1 = vec2(0.1, 0.0);
uniform vec2 look_y_1 = vec2(0.0, 0.1);
uniform float iris_radius_1 = 0.085;
// eye.png's painted iris discs: UV centre and radius (radius 0 = not known).
uniform vec3 painted_iris_0 = vec3(0.0);
uniform vec3 painted_iris_1 = vec3(0.0);
uniform vec3 sclera_color : source_color = vec3(0.9, 0.87, 0.83);
uniform float pupil_ratio : hint_range(0.1, 0.7) = 0.36;
uniform float catchlight : hint_range(0.0, 2.0) = 0.55;
// The upper lid's shadow painted over the top of the iris, as the Medium faces
// paint it: this dark at eye_paint 1 (the stylised eye, from eye_style), and
// `iris_lid_shade_base` on every eye. It grows in over `iris_lid_band` (drawn iris
// radii above the iris centre: from x, full from y), so at eye_style +1 the top
// third of the visible iris is in shade.
uniform float iris_lid_shade : hint_range(0.0, 1.0) = 0.8;
uniform float iris_lid_shade_base : hint_range(0.0, 1.0) = 0.15;
uniform vec2 iris_lid_band = vec2(-0.05, 0.25);
// How much of the iris's gloss and reflections the shade takes away.
uniform float iris_lid_gloss : hint_range(0.0, 1.0) = 0.85;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
// Beyond this many painted iris radii from the iris centre the eyeball is
// drawn as painted whatever `iris_scale` says (it stays inside the eyeball's
// UV island; `iris_scale` is clamped below it).
const float IRIS_RING = 1.75;

void fragment() {
	if (UV.x > cornea_uv_min.x && UV.y > cornea_uv_min.y) {
		discard;
	}
	vec2 shift_0 = look_x_0 * eye_look.x + look_y_0 * eye_look.y;
	vec2 shift_1 = look_x_1 * eye_look.x + look_y_1 * eye_look.y;
	vec2 centre_0 = iris_uv_0 + shift_0;
	vec2 centre_1 = iris_uv_1 + shift_1;
	bool first = distance(UV, iris_uv_0) < distance(UV, iris_uv_1);
	vec2 centre = first ? centre_0 : centre_1;
	vec2 shift = first ? shift_0 : shift_1;
	float radius = max(first ? iris_radius_0 : iris_radius_1, 0.0001);
	vec2 up = normalize(first ? look_y_0 : look_y_1);
	vec2 across = normalize(first ? look_x_0 : look_x_1);
	// Stylised iris size: the painted iris radius 1 is drawn at `scale`; the
	// ring between it and IRIS_RING maps linearly onto the painted 1..IRIS_RING.
	float scale = clamp(eye_style_paint.x, 0.6, 1.5);
	float eye_paint = clamp(eye_style_paint.y, 0.0, 1.0);
	vec3 painted_disc = distance(UV, painted_iris_0.xy) < distance(UV, painted_iris_1.xy) ? painted_iris_0 : painted_iris_1;
	float disc_radius = painted_disc.z > 0.0 ? painted_disc.z : radius;
	vec2 magnify_centre = (painted_disc.z > 0.0 ? painted_disc.xy : (first ? iris_uv_0 : iris_uv_1)) + shift;
	float shown = distance(UV, magnify_centre) / disc_radius;
	vec2 uv = UV;
	if (shown < IRIS_RING && abs(scale - 1.0) > 0.0001) {
		float source = shown < scale ? shown / scale
			: 1.0 + (shown - scale) * (IRIS_RING - 1.0) / (IRIS_RING - scale);
		uv = magnify_centre + (UV - magnify_centre) * (source / max(shown, 0.00001));
	}
	float r = distance(uv, centre) / radius;
	// How far this point is from the painted iris it shows, in painted radii (the fitted
	// centre sits about a fitted radius off the painted disc: measured from it, part of a
	// grown, looking iris was carried only partly and a second pupil showed).
	float carry_r = painted_disc.z > 0.0 ? distance(uv, magnify_centre) / painted_disc.z : r;
	vec3 albedo;
	float iris;
	if (has_texture) {
		// Carry the painted iris with the look; the sclera far from it stays put.
		float carried = 1.0 - smoothstep(1.5, 2.6, carry_r);
		vec4 painted = texture(eye_texture, uv - shift * carried);
		iris = painted.a;
		vec3 tinted = eye_color.rgb * clamp(dot(painted.rgb, LUMA) * 1.8, 0.0, 1.5);
		albedo = mix(painted.rgb, tinted, iris);
	} else {
		vec2 offset = uv - centre;
		float angle = atan(offset.y, offset.x);
		float fibres = 0.82 + 0.18 * sin(angle * 41.0 + r * 7.0) * sin(angle * 17.0 - r * 5.0);
		float limbus = smoothstep(0.72, 1.0, r);
		vec3 iris_rgb = eye_color.rgb * fibres * mix(1.18, 0.5, limbus);
		iris_rgb = mix(iris_rgb, eye_color.rgb * 1.35 + 0.04, (1.0 - smoothstep(pupil_ratio, 0.62, r)) * 0.35);
		iris = 1.0 - smoothstep(0.96, 1.05, r);
		float pupil = 1.0 - smoothstep(pupil_ratio - 0.04, pupil_ratio + 0.03, r);
		// Sclera: a touch of warmth and shade towards the corners of the eye.
		vec3 sclera = sclera_color * mix(1.0, 0.82, smoothstep(1.4, 3.2, r));
		albedo = mix(sclera, iris_rgb, iris);
		albedo = mix(albedo, vec3(0.015), pupil);
	}
	// The lid's shadow: how far up the drawn iris this point is, from the iris's
	// resting centre (0 there, 1 at its top edge), so the shade stays under the lid
	// while the iris looks about.
	float above = dot(UV - (magnify_centre - shift), up) / (disc_radius * scale);
	float in_shade = iris * smoothstep(iris_lid_band.x, iris_lid_band.y, above);
	float shade = mix(iris_lid_shade_base, iris_lid_shade, eye_paint) * in_shade;
	albedo *= 1.0 - shade;
	ALBEDO = albedo;
	// The shade takes the iris's gloss with it, in proportion to how dark it is
	// against the stylised eye's full shade; never below none or above full gloss.
	float gloss = clamp(1.0 - iris_lid_gloss * in_shade * (shade / max(iris_lid_shade, 0.001)), 0.0, 1.0);
	ROUGHNESS = mix(0.3, mix(0.3, 0.06, gloss), iris);
	SPECULAR = 0.5 * mix(1.0, gloss, iris);
	vec2 glint = centre + (up * 0.42 - across * 0.32) * radius;
	EMISSION = vec3(catchlight) * (1.0 - smoothstep(0.08, 0.16, distance(uv, glint) / radius));
}

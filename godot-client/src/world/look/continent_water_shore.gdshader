// Look pass: the continent's water with a soft edge where it meets the ground
// (CONTINENT_WATER_SHORE in continent_water.gdshaderinc, LookProfile.WATER_SHORE_*).
// It reads the scene's depth, which puts it in the transparent pass; it
// writes depth as the opaque sea did. LookGround.set_water_shore gives it
// LookProfile.WATER_SHORE_PRIORITY: it draws after the painted ground's
// blended copies (LookGround.glaze_priority), so it blends over the ground
// beneath it, and before every effect, which it never paints over.
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_always;

#define CONTINENT_WATER_SHORE
#include "res://src/world/continent_water.gdshaderinc"

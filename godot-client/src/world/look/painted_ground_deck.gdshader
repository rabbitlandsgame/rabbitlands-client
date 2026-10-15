// Look pass layer L2: painted ground for a walk deck - a worn road drawn
// over the ground with an opaque depth pre-pass and no culling - with the
// dark edging band beyond its rim. See painted_ground_surface.gdshaderinc.
shader_type spatial;
render_mode blend_mix, depth_prepass_alpha, cull_disabled;

#define LOOK_GROUND_ALPHA
#define LOOK_GROUND_EDGE_BAND
#include "res://src/world/look/painted_ground_surface.gdshaderinc"

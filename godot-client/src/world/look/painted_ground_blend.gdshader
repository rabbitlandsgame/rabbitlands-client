// Look pass layer L2: painted ground for a plainly blended two-sided source
// (a translucent authored patch). See painted_ground_surface.gdshaderinc.
shader_type spatial;
render_mode blend_mix, cull_disabled;

#define LOOK_GROUND_ALPHA
#include "res://src/world/look/painted_ground_surface.gdshaderinc"

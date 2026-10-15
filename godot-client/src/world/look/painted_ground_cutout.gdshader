shader_type spatial;
render_mode depth_draw_opaque, cull_disabled;

#define LOOK_GROUND_ALPHA
#define LOOK_GROUND_CUTOUT
#include "res://src/world/look/painted_ground_surface.gdshaderinc"

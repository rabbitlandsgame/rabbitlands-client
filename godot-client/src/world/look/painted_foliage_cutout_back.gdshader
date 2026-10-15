// Look pass layer L3: painted_foliage_cutout.gdshader drawn back-face culled,
// for a single-sided alpha-cut leaf material. See
// painted_foliage_body.gdshaderinc.
shader_type spatial;
render_mode cull_back;

#define LOOK_FOLIAGE_CUTOUT
#include "res://src/world/look/painted_foliage_body.gdshaderinc"

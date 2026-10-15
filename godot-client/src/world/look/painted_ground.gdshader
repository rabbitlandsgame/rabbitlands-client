// Look pass layer L2: painted ground for an opaque, back-face culled source
// (the continent's terrain). See painted_ground_surface.gdshaderinc.
shader_type spatial;
render_mode cull_back;

#include "res://src/world/look/painted_ground_surface.gdshaderinc"

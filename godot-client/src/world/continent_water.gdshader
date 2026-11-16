// The continent's water as the loader puts it in, opaque
// (continent_water.gdshaderinc; look/continent_water_shore.gdshader is the
// look pass's soft-edged copy).
shader_type spatial;
render_mode cull_disabled;

#include "res://src/world/continent_water.gdshaderinc"

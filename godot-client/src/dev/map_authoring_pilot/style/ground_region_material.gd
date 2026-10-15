@tool
class_name MapAuthoringGroundRegionMaterial
extends RefCounted

## Adds a soft world-space footprint to the owned oriented PBR shader. Region
## materials are independent, while identical base shader variants share code.

const ELLIPSE := 0
const RECTANGLE := 1

const _UNIFORM_ANCHOR := \
	"uniform float texture_rotation_radians = 0.0;\n\n"
const _VERTEX_ANCHOR := "void vertex() {\n"
const _FRAGMENT_ANCHOR := "void fragment() {\n"
const _REGION_UNIFORMS := """
uniform vec3 region_world_to_local_x = vec3(1.0, 0.0, 0.0);
uniform vec3 region_world_to_local_y = vec3(0.0, 1.0, 0.0);
uniform vec2 region_half_size = vec2(1.0);
uniform float region_shape = 0.0;
uniform float region_blend_width = 0.0;
uniform float region_opacity = 1.0;
uniform int region_clip_count = 0;
uniform vec2 region_clip_polygon[64];
varying vec2 region_world_xz;

"""
const _REGION_VERTEX := """void vertex() {
	region_world_xz = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
"""
const _REGION_FRAGMENT := """float region_ellipse_inside(vec2 point, vec2 half_size) {
	vec2 positive_size = max(half_size, vec2(0.001));
	float scaled_radius = length(point / positive_size);
	if (scaled_radius < 0.00001) {
		return min(positive_size.x, positive_size.y);
	}
	float gradient_scale = length(point / (positive_size * positive_size));
	return (1.0 - scaled_radius) * scaled_radius /
		max(gradient_scale, 0.00001);
}

float region_rectangle_inside(vec2 point, vec2 half_size) {
	vec2 inward = max(half_size, vec2(0.001)) - abs(point);
	return min(inward.x, inward.y);
}

bool region_clip_contains(vec2 point) {
	if (region_clip_count == 0) { return true; }
	bool inside = false;
	for (int i = 0; i < 64; i++) {
		if (i >= region_clip_count) { break; }
		vec2 a = region_clip_polygon[i];
		vec2 b = region_clip_polygon[(i + 1) % region_clip_count];
		vec2 edge = b - a;
		vec2 delta = point - a;
		float cross_value = edge.x * delta.y - edge.y * delta.x;
		float epsilon = 0.00001 * max(length(edge), 1.0);
		if (abs(cross_value) <= epsilon && dot(delta, edge) >= -epsilon &&
				dot(delta, edge) <= dot(edge, edge) + epsilon) { return true; }
		if ((a.y > point.y) != (b.y > point.y)) {
			float crossing_x = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y);
			if (point.x < crossing_x) { inside = !inside; }
		}
	}
	return inside;
}

void fragment() {
	vec3 world_point = vec3(region_world_xz, 1.0);
	vec2 region_local = vec2(dot(region_world_to_local_x, world_point),
		dot(region_world_to_local_y, world_point));
	if (!region_clip_contains(region_local)) { discard; }
	float inside_distance = region_shape < 0.5 ?
		region_ellipse_inside(region_local, region_half_size) :
		region_rectangle_inside(region_local, region_half_size);
	if (inside_distance <= 0.0) {
		discard;
	}
	float footprint = region_blend_width <= 0.0 ? 1.0 :
		smoothstep(0.0, region_blend_width, inside_distance);
	ALPHA = clamp(footprint * region_opacity, 0.0, 1.0);
"""

static var _shader_variants := {}
static var _warned_sources := {}


static func create(surface: MapAuthoringSurface,
		world_to_local: Transform2D, half_size: Vector2, shape: int,
		blend_width: float, opacity: float,
		render_priority: int, clip_polygon: PackedVector2Array = PackedVector2Array()) -> ShaderMaterial:
	if surface == null or not surface.source_material is BaseMaterial3D:
		_warn_unsupported(surface, "a BaseMaterial3D source is required")
		return null
	if not world_to_local.x.is_finite() or not world_to_local.y.is_finite() or \
			not world_to_local.origin.is_finite() or \
			absf(world_to_local.determinant()) < 0.000001:
		_warn_unsupported(surface, "the world-to-local transform is singular")
		return null
	if not half_size.is_finite() or half_size.x <= 0.0 or half_size.y <= 0.0:
		_warn_unsupported(surface, "both footprint half-size values must be positive")
		return null
	if not is_finite(blend_width) or not is_finite(opacity):
		_warn_unsupported(surface, "blend width and opacity must be finite")
		return null
	var mask_error := MapAuthoringGroundRegion.clip_error(clip_polygon)
	if not mask_error.is_empty():
		_warn_unsupported(surface, mask_error)
		return null
	var oriented := MapAuthoringTexturePresets.create_oriented_material(
		surface.source_material, surface.rotation_degrees, true) as ShaderMaterial
	if oriented == null or oriented.shader == null:
		_warn_unsupported(surface,
			"the source uses material features the region shader cannot preserve")
		return null
	var region_shader := _region_shader(oriented.shader)
	if region_shader == null:
		_warn_unsupported(surface, "the owned PBR shader hooks are unavailable")
		return null
	var parameter_values := {}
	for parameter: Dictionary in oriented.shader.get_shader_uniform_list():
		var parameter_name := StringName(parameter.name)
		parameter_values[parameter_name] = oriented.get_shader_parameter(parameter_name)
	var region := oriented.duplicate(true) as ShaderMaterial
	region.shader = region_shader
	for parameter_name: StringName in parameter_values:
		region.set_shader_parameter(parameter_name, parameter_values[parameter_name])
	region.set_shader_parameter("region_world_to_local_x", Vector3(
		world_to_local.x.x, world_to_local.y.x, world_to_local.origin.x))
	region.set_shader_parameter("region_world_to_local_y", Vector3(
		world_to_local.x.y, world_to_local.y.y, world_to_local.origin.y))
	region.set_shader_parameter("region_half_size", half_size)
	region.set_shader_parameter("region_shape",
		float(RECTANGLE if shape == RECTANGLE else ELLIPSE))
	region.set_shader_parameter("region_blend_width", maxf(blend_width, 0.0))
	region.set_shader_parameter("region_opacity", clampf(opacity, 0.0, 1.0))
	var uniform_polygon := PackedVector2Array()
	uniform_polygon.resize(64)
	for i in clip_polygon.size(): uniform_polygon[i] = clip_polygon[i]
	region.set_shader_parameter("region_clip_count", clip_polygon.size())
	region.set_shader_parameter("region_clip_polygon", uniform_polygon)
	region.render_priority = clampi(render_priority, -128, 127)
	return region


static func _region_shader(base: Shader) -> Shader:
	# Shader source can be presented with platform-specific line endings. Normalize
	# before hook validation and cache lookup so equivalent owned code shares one
	# stable variant across editor and runtime.
	var base_code := base.code.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
	if _shader_variants.has(base_code):
		return _shader_variants[base_code]
	var code := _region_code(base_code)
	if code.is_empty():
		return null
	var shader := Shader.new()
	shader.code = code
	_shader_variants[base_code] = shader
	return shader


static func _region_code(source_code: String) -> String:
	var base_code := source_code.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
	if base_code.count(_UNIFORM_ANCHOR) != 1 or \
			base_code.count(_VERTEX_ANCHOR) != 1 or \
			base_code.count(_FRAGMENT_ANCHOR) != 1:
		return ""
	var code := base_code.replace(
		_UNIFORM_ANCHOR, _UNIFORM_ANCHOR + _REGION_UNIFORMS)
	code = code.replace(_VERTEX_ANCHOR, _REGION_VERTEX)
	code = code.replace(_FRAGMENT_ANCHOR, _REGION_FRAGMENT)
	return code


static func _warn_unsupported(surface: MapAuthoringSurface, reason: String) -> void:
	var key := "null" if surface == null else str(surface.get_instance_id())
	if _warned_sources.has(key):
		return
	if _warned_sources.size() >= 32:
		_warned_sources.erase(_warned_sources.keys()[0])
	_warned_sources[key] = true
	push_warning("Ground region material was not created: %s. " % reason +
		"The original material remains unchanged.")

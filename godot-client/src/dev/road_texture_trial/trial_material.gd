extends RefCounted
## Experimental adapter. Derive the production road shader rather than keeping
## a second copy of its regional paint, class textures, edge noise, or lighting.

const SURFACE_PATH := "res://src/world/look/painted_ground_surface.gdshaderinc"
const INCLUDE := "#include \"res://src/world/look/painted_ground_surface.gdshaderinc\""
static var _shaders: Dictionary = {}

const UNIFORMS := """
// Road trial fields are data, never sRGB colour textures.
uniform sampler2D trial_coverage : filter_linear_mipmap, repeat_disable;
uniform sampler2D trial_uv_field : filter_linear_mipmap, repeat_disable;
uniform vec2 trial_mask_origin = vec2(0.0);
uniform vec2 trial_mask_extent = vec2(1.0);
uniform mat4 trial_mesh_to_mask = mat4(1.0);
uniform vec3 trial_vertex_lift = vec3(0.0, 0.055, 0.0);
uniform vec3 trial_vertex_rgb = vec3(1.0);
uniform bool trial_debug_coverage = false;
varying vec2 trial_mask_xz;
"""

const FRAGMENT_START := """
void fragment() {
	vec2 trial_mask_uv = (trial_mask_xz - trial_mask_origin) / trial_mask_extent;
	// The baker supplies a two-pixel halo. Outside this rectangle there is no
	// source road geometry, so it must never become an accidental noisy road.
	if (any(lessThan(trial_mask_uv, vec2(0.0))) || any(greaterThan(trial_mask_uv, vec2(1.0)))) { discard; }
	float trial_alpha = texture(trial_coverage, trial_mask_uv).r;
	vec2 trial_uv = texture(trial_uv_field, trial_mask_uv).rg * uv1_scale.xy + uv1_offset.xy;
	// The old road is terrain-conformed with flat per-face normals. The terrain
	// render mesh carries smooth normals, so reconstruct its actual face here.
	vec3 trial_dx = dFdx(VERTEX);
	vec3 trial_dy = dFdy(VERTEX);
	vec3 trial_n = normalize(cross(trial_dx, trial_dy));
	if (dot(trial_n, NORMAL) < 0.0) { trial_n = -trial_n; }
	NORMAL = trial_n;
	// Rebuild the road's tangent frame from its unwrapped flow UVs, not the
	// terrain's world-aligned UVs. Godot then applies its ordinary RG normal map.
	vec2 trial_udx = dFdx(trial_uv);
	vec2 trial_udy = dFdy(trial_uv);
	float trial_det = trial_udx.x * trial_udy.y - trial_udy.x * trial_udx.y;
	if (abs(trial_det) > 0.00000001) {
		vec3 trial_t = (trial_dx * trial_udy.y - trial_dy * trial_udx.y) / trial_det;
		vec3 trial_b = (trial_dy * trial_udx.x - trial_dx * trial_udy.x) / trial_det;
		TANGENT = normalize(trial_t - NORMAL * dot(NORMAL, trial_t));
		BINORMAL = normalize(trial_b - NORMAL * dot(NORMAL, trial_b));
	} else {
		TANGENT = normalize(trial_dx - NORMAL * dot(NORMAL, trial_dx));
		BINORMAL = normalize(cross(NORMAL, TANGENT));
	}
	// A zero-alpha texel also represents space with no original ribbon. It
	// cannot be turned opaque by the production edge-grain noise.
	if (trial_alpha <= 0.0) { discard; }
"""

static func build(source: ShaderMaterial) -> Dictionary:
	if source == null or source.shader == null:
		return {"ok": false, "error": "road_material_has_no_shader"}
	var header: String = source.shader.code
	if header.count(INCLUDE) != 1 or not header.contains("#define LOOK_GROUND_ALPHA"):
		return {"ok": false, "error": "unsupported_production_road_shader"}
	var body: String = FileAccess.get_file_as_string(SURFACE_PATH)
	var anchors: Array[String] = [
		"void vertex() {", "void fragment() {", "look_ground_xz = VERTEX.xz;",
		"vec4 texel = texture(albedo_texture, UV);", "vec3 vertex_colour = COLOR.rgb;",
		"float weight = COLOR.a +", "NORMAL_MAP = texture(normal_texture, UV).rgb;",
	]
	for anchor: String in anchors:
		if body.count(anchor) != 1:
			return {"ok": false, "error": "production_shader_contract_changed: " + anchor}
	var cut: int = body.find("void fragment() {")
	var vertex_body: String = body.substr(0, cut)
	var fragment_body: String = body.substr(cut)
	vertex_body = vertex_body.replace("void vertex() {", UNIFORMS + "\nvoid vertex() {")
	vertex_body = vertex_body.replace("look_ground_xz = VERTEX.xz;",
		"look_ground_xz = VERTEX.xz;\n\ttrial_mask_xz = (trial_mesh_to_mask * vec4(VERTEX, 1.0)).xz;\n\tVERTEX += trial_vertex_lift;")
	# Only the fragment's original UV references change. Their scale/offset is
	# applied once in FRAGMENT_START, just as the old vertex shader applied it.
	var uv_words := RegEx.create_from_string("\\bUV\\b")
	fragment_body = uv_words.sub(fragment_body, "trial_uv", true)
	fragment_body = fragment_body.replace("COLOR.rgb", "trial_vertex_rgb")
	fragment_body = fragment_body.replace("COLOR.a", "trial_alpha")
	fragment_body = fragment_body.replace("void fragment() {", FRAGMENT_START)
	# Coverage debug is a separate qualification view, never a timing variant.
	var last_brace: int = fragment_body.rfind("}")
	fragment_body = fragment_body.insert(last_brace,
		"\n\tif (trial_debug_coverage) { ALBEDO = vec3(0.0); EMISSION = vec3(trial_alpha); ALPHA = 1.0; }\n")
	var code: String = header.replace(INCLUDE, vertex_body + fragment_body)
	var key: String = _sha(code.to_utf8_buffer())
	var shader: Shader = _shaders.get(key)
	if shader == null:
		shader = Shader.new()
		shader.code = code
		_shaders[key] = shader
	var result := ShaderMaterial.new()
	result.shader = shader
	result.resource_name = source.resource_name
	result.render_priority = source.render_priority
	for uniform: Dictionary in source.shader.get_shader_uniform_list():
		var name: StringName = StringName(uniform.get("name", ""))
		result.set_shader_parameter(name, source.get_shader_parameter(name))
	return {"ok": true, "material": result,
		"production_surface_sha256": _sha(body.to_utf8_buffer()),
		"derived_shader_sha256": key}

static func _sha(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()

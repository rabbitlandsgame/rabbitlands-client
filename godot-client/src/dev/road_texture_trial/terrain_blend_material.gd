extends RefCounted
## Derive an opaque existing-ground material from the maintained ground paint.
## Road paint has its own uniforms/functions, UVs, tint, and normal-map frame.
## The final blend is before lighting; it approximates separately lit ribbons.

const SURFACE := "res://src/world/look/painted_ground_surface.gdshaderinc"
const PAINT := "res://src/world/look/painted_ground_paint.gdshaderinc"
const INCLUDE := "#include \"res://src/world/look/painted_ground_surface.gdshaderinc\""
const EXTRA_NAMES: Array[String] = [
	"albedo_texture", "albedo_color", "use_vertex_albedo", "vertex_albedo_srgb", "use_vertex_alpha",
	"normal_texture", "has_normal_texture", "normal_scale", "roughness_value", "metallic_value",
	"specular_value", "uv1_scale", "uv1_offset",
]
const FIELD_NAMES: Array[String] = [
	"trial_coverage", "trial_uv_field", "trial_mask_origin", "trial_mask_extent",
	"trial_mesh_to_mask", "trial_vertex_rgb", "trial_debug_coverage",
]
const GLOBALS := """
uniform sampler2D trial_coverage : filter_linear_mipmap, repeat_disable;
uniform sampler2D trial_uv_field : filter_linear_mipmap, repeat_disable;
uniform vec2 trial_mask_origin = vec2(0.0);
uniform vec2 trial_mask_extent = vec2(1.0);
uniform mat4 trial_mesh_to_mask = mat4(1.0);
uniform vec3 trial_vertex_rgb = vec3(1.0);
uniform bool trial_debug_coverage = false;
varying vec2 terrain_blend_mask_xz;

// Match the engine's RG normal reconstruction and strength interpolation.
// Keep unnormalized interpolated tangent vectors, as the source material does.
vec3 terrain_blend_normal_view(vec3 texel, float depth, vec3 n, vec3 t, vec3 b) {
	vec2 xy = texel.rg * 2.0 - vec2(1.0);
	float z = sqrt(max(0.0, 1.0 - dot(xy, xy)));
	return normalize(mix(n, t * xy.x + b * xy.y + n * z, depth));
}
"""

static func build(base: ShaderMaterial, road: ShaderMaterial, shader_cache: Dictionary) -> Dictionary:
	if base == null or road == null or base.shader == null or road.shader == null:
		return {"ok": false, "error": "blend_requires_painted_base_and_road"}
	var header: String = base.shader.code
	if header.count(INCLUDE) != 1 or header.contains("#define LOOK_GROUND_ALPHA") or base.next_pass != null:
		return {"ok": false, "error": "blend_base_must_be_one_opaque_ground_pass"}
	if not road.shader.code.contains("#define LOOK_GROUND_ALPHA"):
		return {"ok": false, "error": "blend_requires_authored_alpha_road"}
	var surface: String = FileAccess.get_file_as_string(SURFACE)
	var paint: String = FileAccess.get_file_as_string(PAINT)
	var anchors: Array[String] = ["void vertex() {", "void fragment() {", "look_ground_xz = VERTEX.xz;",
		"NORMAL_MAP = texture(normal_texture, UV).rgb;", "NORMAL_MAP_DEPTH = normal_scale;",
		"float coverage = 1.0;", "#ifdef LOOK_GROUND_CUTOUT"]
	for anchor: String in anchors:
		if surface.count(anchor) != 1:
			return {"ok": false, "error": "blend_production_surface_contract: " + anchor}
	var fragment_at: int = surface.find("void fragment() {")
	var alpha_at: int = surface.find("#ifdef LOOK_GROUND_ALPHA", fragment_at)
	var coverage_at: int = surface.find("float coverage = 1.0;", alpha_at)
	var coverage_end: int = surface.find("#ifdef LOOK_GROUND_CUTOUT", coverage_at)
	if alpha_at < fragment_at or coverage_at < alpha_at or coverage_end < coverage_at:
		return {"ok": false, "error": "blend_production_fragment_layout"}
	var road_globals := ""
	var uniform_pattern := RegEx.create_from_string("(?m)^uniform\\s+[^;]+;")
	for found: RegExMatch in uniform_pattern.search_all(surface.substr(0, fragment_at)):
		road_globals += found.get_string() + "\n"
	road_globals = _namespace(paint + "\n" + road_globals)
	var road_fragment: String = surface.substr(fragment_at + "void fragment() {".length(),
		alpha_at - fragment_at - "void fragment() {".length())
	var road_coverage: String = surface.substr(coverage_at, coverage_end - coverage_at)
	road_fragment = _road_locals(_namespace(road_fragment))
	road_coverage = _road_locals(_namespace(road_coverage))
	# Derivatives must be evaluated before the coverage-dependent branch.
	road_fragment = road_fragment.replace("texture(road_albedo_texture, road_eval_uv)",
		"textureGrad(road_albedo_texture, road_eval_uv, blend_dudx, blend_dudy)")
	road_fragment = road_fragment.replace("texture(road_normal_texture, road_eval_uv)",
		"textureGrad(road_normal_texture, road_eval_uv, blend_dudx, blend_dudy)")
	road_fragment = road_fragment.replace("texture(road_look_class_texture, road_eval_class_uv)",
		"textureGrad(road_look_class_texture, road_eval_class_uv, blend_xzdx / road_look_class_metres, blend_xzdy / road_look_class_metres)")
	var base_surface: String = surface.replace("look_ground_xz = VERTEX.xz;",
		"look_ground_xz = VERTEX.xz;\n\tterrain_blend_mask_xz = (trial_mesh_to_mask * vec4(VERTEX, 1.0)).xz;")
	base_surface = base_surface.replace("void vertex() {", GLOBALS + "\n" + road_globals + "\nvoid vertex() {")
	base_surface = base_surface.replace("void fragment() {", "void fragment() {\n"
		+ "\tvec3 terrain_blend_base_map = vec3(0.5, 0.5, 1.0);\n\tfloat terrain_blend_base_depth = 1.0;")
	base_surface = base_surface.replace("NORMAL_MAP = texture(normal_texture, UV).rgb;",
		"terrain_blend_base_map = texture(normal_texture, UV).rgb;")
	base_surface = base_surface.replace("NORMAL_MAP_DEPTH = normal_scale;", "terrain_blend_base_depth = normal_scale;")
	var last_brace: int = base_surface.rfind("}")
	base_surface = base_surface.insert(last_brace, _composite(road_fragment, road_coverage))
	var code: String = header.replace(INCLUDE, base_surface)
	var key: String = _sha(code.to_utf8_buffer())
	var shader: Shader = shader_cache.get(key)
	if shader == null:
		shader = Shader.new()
		shader.code = code
		shader_cache[key] = shader
	var material := ShaderMaterial.new()
	material.shader = shader
	material.resource_name = base.resource_name
	material.render_priority = base.render_priority
	var names: Array[String] = []
	for uniform: Dictionary in base.shader.get_shader_uniform_list():
		var name: String = str(uniform.get("name", ""))
		material.set_shader_parameter(StringName(name), base.get_shader_parameter(StringName(name)))
		names.append(name)
	for uniform: Dictionary in road.shader.get_shader_uniform_list():
		var name: String = str(uniform.get("name", ""))
		var mapped: String = _road_name(name)
		material.set_shader_parameter(StringName(mapped), road.get_shader_parameter(StringName(name)))
		names.append(mapped)
	names.append_array(FIELD_NAMES)
	material.set_meta(&"terrain_blend_parameter_names", names)
	material.set_meta(&"terrain_blend_existing_pass", true)
	return {"ok": true, "material": material, "shader_sha256": key,
		"production_surface_sha256": _sha(surface.to_utf8_buffer()),
		"production_paint_sha256": _sha(paint.to_utf8_buffer())}

static func _namespace(code: String) -> String:
	var words: Dictionary = {}
	var pattern := RegEx.create_from_string("\\blook_[A-Za-z0-9_]+\\b")
	for found: RegExMatch in pattern.search_all(code):
		if found.get_string() != "look_ground_xz":
			words[found.get_string()] = true
	for name: String in EXTRA_NAMES:
		words[name] = true
	for name: String in words:
		code = RegEx.create_from_string("\\b" + name + "\\b").sub(code, "road_" + name, true)
	return code

static func _road_name(name: String) -> String:
	return "road_" + name if name.begins_with("look_") or name in EXTRA_NAMES else name

static func _road_locals(code: String) -> String:
	code = code.replace("COLOR.rgb", "trial_vertex_rgb").replace("COLOR.a", "trial_alpha")
	var replacements: Dictionary = {"ALBEDO": "road_eval_albedo", "EMISSION": "road_eval_emission",
		"ROUGHNESS": "road_eval_roughness", "METALLIC": "road_eval_metallic", "SPECULAR": "road_eval_specular",
		"NORMAL_MAP": "road_eval_map", "NORMAL_MAP_DEPTH": "road_eval_depth", "UV": "road_eval_uv"}
	for name: String in ["texel", "texel_mean", "class_uv", "detail", "detail_mean", "recoloured", "own_hue",
		"albedo", "vertex_colour", "reference", "world_normal", "coverage", "band", "lobe_p", "lobe", "grain", "weight", "covered"]:
		replacements[name] = "road_sample_" + name if name == "albedo" else "road_eval_" + name
	for name: String in replacements:
		code = RegEx.create_from_string("\\b" + name + "\\b").sub(code, replacements[name], true)
	return code

static func _composite(road_fragment: String, road_coverage: String) -> String:
	return """
	// The non-road branch keeps the original base material's normal inputs.
	NORMAL_MAP = terrain_blend_base_map;
	NORMAL_MAP_DEPTH = terrain_blend_base_depth;
	vec2 terrain_blend_uv = (terrain_blend_mask_xz - trial_mask_origin) / trial_mask_extent;
	float trial_alpha = texture(trial_coverage, terrain_blend_uv).r;
	if (any(lessThan(terrain_blend_uv, vec2(0.0))) || any(greaterThan(terrain_blend_uv, vec2(1.0)))) {
		trial_alpha = 0.0;
	}
	vec2 road_eval_uv = texture(trial_uv_field, terrain_blend_uv).rg * road_uv1_scale.xy + road_uv1_offset.xy;
	vec3 blend_dpdx = dFdx(VERTEX);
	vec3 blend_dpdy = dFdy(VERTEX);
	vec2 blend_dudx = dFdx(road_eval_uv);
	vec2 blend_dudy = dFdy(road_eval_uv);
	vec2 blend_xzdx = dFdx(look_ground_xz);
	vec2 blend_xzdy = dFdy(look_ground_xz);
	if (trial_alpha > 0.0) {
		vec3 road_eval_albedo = vec3(0.0);
		vec3 road_eval_emission = vec3(0.0);
		float road_eval_roughness = 1.0;
		float road_eval_metallic = 0.0;
		float road_eval_specular = 0.5;
		vec3 road_eval_map = vec3(0.5, 0.5, 1.0);
		float road_eval_depth = 1.0;
""" + road_fragment + "\n" + road_coverage + """
		float terrain_blend_amount = clamp(1.0 - (1.0 - road_eval_covered) * (1.0 - road_eval_band), 0.0, 1.0);
		ALBEDO = ALBEDO * (1.0 - terrain_blend_amount) + road_eval_albedo * road_eval_covered;
		EMISSION = mix(EMISSION, road_eval_emission, terrain_blend_amount);
		ROUGHNESS = mix(ROUGHNESS, road_eval_roughness, terrain_blend_amount);
		METALLIC = mix(METALLIC, road_eval_metallic, terrain_blend_amount);
		SPECULAR = mix(SPECULAR, road_eval_specular, terrain_blend_amount);
		// Road detail follows its flow field. The base's own tangent frame is
		// retained for the final encoded normal sent to the engine.
		float blend_det = blend_dudx.x * blend_dudy.y - blend_dudy.x * blend_dudx.y;
		vec3 blend_n = normalize(cross(blend_dpdx, blend_dpdy));
		if (dot(blend_n, NORMAL) < 0.0) { blend_n = -blend_n; }
		vec3 blend_t = TANGENT;
		vec3 blend_b = BINORMAL;
		if (abs(blend_det) > 0.00000001) {
			vec3 t = (blend_dpdx * blend_dudy.y - blend_dpdy * blend_dudx.y) / blend_det;
			vec3 b = (blend_dpdy * blend_dudx.x - blend_dpdx * blend_dudy.x) / blend_det;
			vec3 projected_t = t - blend_n * dot(blend_n, t);
			if (dot(projected_t, projected_t) > 0.00000001) {
				vec3 candidate_t = normalize(projected_t);
				vec3 candidate_b = normalize(cross(blend_n, candidate_t));
				float handedness = dot(candidate_b, b);
				if (abs(handedness) > 0.00000001) {
					blend_t = candidate_t;
					blend_b = candidate_b * (handedness < 0.0 ? -1.0 : 1.0);
				}
			}
		}
		vec3 blend_base_n = terrain_blend_normal_view(terrain_blend_base_map, terrain_blend_base_depth, NORMAL, TANGENT, BINORMAL);
		vec3 blend_road_n = terrain_blend_normal_view(road_eval_map, road_eval_depth, blend_n, blend_t, blend_b);
		mat3 blend_base_frame = mat3(TANGENT, BINORMAL, NORMAL);
		if (abs(determinant(blend_base_frame)) > 0.00000001) {
			vec3 blend_final_n = normalize(mix(blend_base_n, blend_road_n, terrain_blend_amount));
			vec3 blend_local_n = normalize(inverse(blend_base_frame) * blend_final_n);
			NORMAL_MAP = blend_local_n * 0.5 + vec3(0.5);
			NORMAL_MAP_DEPTH = 1.0;
		}
	}
	if (trial_debug_coverage) {
		ALBEDO = vec3(0.0);
		EMISSION = vec3(trial_alpha);
	}
"""

static func _sha(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()

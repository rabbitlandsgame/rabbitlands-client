extends SceneTree
## Focused CPU checks: generated existing-pass shader and actual producer fields.
## GPU compilation, appearance and timing are qualified by the shared benchmark.

const Blend := preload("res://src/dev/road_texture_trial/terrain_blend_trial.gd")
const BlendMaterial := preload("res://src/dev/road_texture_trial/terrain_blend_material.gd")
const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
var _checks := 0
var _failures: Array[String] = []

func _init() -> void:
	_expect(bool(Blend.apply(null, "", "baseline").ok), "baseline_no_op")
	_expect(not bool(Blend.apply(null, "", "blend").ok), "missing_world_rejected")
	var base := ShaderMaterial.new()
	base.shader = load("res://src/world/look/painted_ground_two_sided.gdshader") as Shader
	base.set_shader_parameter(&"normal_scale", 0.8)
	base.set_shader_parameter(&"look_class", 2)
	var road := ShaderMaterial.new()
	road.shader = load("res://src/world/look/painted_ground_blend.gdshader") as Shader
	road.set_shader_parameter(&"normal_scale", 0.72)
	road.set_shader_parameter(&"look_class", 3)
	road.set_shader_parameter(&"use_vertex_alpha", true)
	var derived: Dictionary = BlendMaterial.build(base, road, {})
	_expect(bool(derived.get("ok", false)), "production_surface_contract: " + str(derived.get("error", "")))
	if bool(derived.get("ok", false)):
		var material: ShaderMaterial = derived.material
		var code: String = material.shader.code
		_expect(code.count("void vertex()") == 1 and code.count("void fragment()") == 1, "one_vertex_and_fragment")
		_expect(not code.contains("#define LOOK_GROUND_ALPHA"), "opaque_existing_pass")
		_expect(not code.contains("VERTEX.y +=") and not code.contains("trial_visual_lift"), "no_vertex_lift")
		_expect(code.contains("road_albedo_texture") and code.contains("road_normal_texture"), "independent_source_textures")
		_expect(code.contains("vec3 road_sample_albedo =") and code.count("vec3 road_eval_albedo =") == 1, "source_colour_does_not_shadow_output")
		_expect(code.contains("road_look_rim_grain") and code.contains("road_look_paint("), "maintained_road_paint_and_edge")
		_expect(code.contains("dFdx(road_eval_uv)") and code.contains("inverse(blend_base_frame)"), "flow_normal_frame")
		_expect(code.find("dFdx(road_eval_uv)") < code.find("if (trial_alpha > 0.0)"), "derivatives_outside_coverage_branch")
		_expect(code.contains("textureGrad(road_albedo_texture") and code.contains("textureGrad(road_normal_texture"), "explicit_road_texture_gradients")
		_expect(not code.contains("TIME"), "qualification_shader_needs_no_clock_freeze")
		_expect(is_equal_approx(float(material.get_shader_parameter(&"normal_scale")), 0.8), "base_uniform_preserved")
		_expect(is_equal_approx(float(material.get_shader_parameter(&"road_normal_scale")), 0.72), "road_uniform_namespaced")
		_expect(material.next_pass == null, "no_additional_material_pass")
		var output: String = OS.get_environment("RL_BLEND_CHECK_SHADER")
		if not output.is_empty():
			var file := FileAccess.open(output, FileAccess.WRITE)
			file.store_string(code)
	base.next_pass = road
	_expect(not bool(BlendMaterial.build(base, road, {}).get("ok", true)), "base_pass_chain_rejected")
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for i: int in args.size():
		if args[i] == "--trial" and i + 1 < args.size():
			_check_trial(args[i + 1])
	print(JSON.stringify({"checks": _checks, "failures": _failures, "gpu_qualified": false}))
	quit(0 if _failures.is_empty() else 1)

func _check_trial(path: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_expect(parsed is Dictionary and str(parsed.get("schema", "")) == Blend.SCHEMA, "producer_schema")
	if not parsed is Dictionary:
		return
	if parsed.get("chunks") is Array:
		for relative: Variant in parsed.chunks:
			_check_trial(path.get_base_dir().path_join(str(relative)))
		return
	_expect(parsed.get("layers", []).size() == 1 and parsed.get("visible_ground_node_names", []).size() == 1, "one_field_one_existing_ground")
	for layer: Dictionary in parsed.get("layers", []):
		var fields: Dictionary = Trial._fields(path.get_base_dir(), layer)
		_expect(bool(fields.get("ok", false)), "actual_field_decode_and_hash: " + str(fields.get("error", "")))
		var source: Dictionary = Trial._source_material(layer)
		_expect(bool(source.get("ok", false)), "actual_road_source_material: " + str(source.get("error", "")))
	for row: Dictionary in parsed.get("nodes", []):
		var collision: Dictionary = Trial._collider(path.get_base_dir(), row)
		_expect(bool(collision.get("ok", false)), "exact_importer_winding_collision: " + str(collision.get("error", "")))
		if collision.get("node") is Node:
			(collision.node as Node).free()

func _expect(condition: bool, label: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)

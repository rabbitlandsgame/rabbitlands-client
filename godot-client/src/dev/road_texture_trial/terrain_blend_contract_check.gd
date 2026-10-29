extends SceneTree
## Focused CPU checks: generated existing-pass shader and actual producer fields.
## GPU compilation, appearance and timing are qualified by the shared benchmark.

const Blend := preload("res://src/dev/road_texture_trial/terrain_blend_trial.gd")
const BlendMaterial := preload("res://src/dev/road_texture_trial/terrain_blend_material.gd")
const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
var _checks := 0
var _failures: Array[String] = []

func _init() -> void:
	_check_sheared_uv_frame()
	_check_affine_uv_reconstruction()
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
		_expect(code.contains("texelFetch(trial_uv_jacobian") and code.contains("inverse(blend_base_frame)"), "selected_triangle_flow_normal_frame")
		_expect(code.find("dFdx(terrain_blend_mask_xz)") < code.find("if (trial_alpha > 0.0)"), "derivatives_outside_coverage_branch")
		_expect(not code.contains("dFdx(road_eval_uv)") and not code.contains("texture(trial_uv_field"), "no_filtered_branch_uv_or_branch_derivative")
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

func _check_sheared_uv_frame() -> void:
	# A sloped plane whose UV-v axis has a component along UV-u. A normal map
	# must use the same orthonormal frame as imported glTF tangents, with its
	# handedness retained. Merely normalizing the raw two axes fails this case.
	var n := Vector3(0.0, 1.0, 1.0).normalized()
	var tangent := Vector3.RIGHT
	var imported_bitangent := n.cross(tangent).normalized()
	for handedness: float in [-1.0, 1.0]:
		var raw_v: Vector3 = tangent * 0.65 + imported_bitangent * handedness
		var rebuilt: Vector3 = n.cross(tangent).normalized()
		if rebuilt.dot(raw_v) < 0.0:
			rebuilt = -rebuilt
		_expect(absf(tangent.dot(raw_v.normalized())) > 0.5, "fixture_has_material_uv_shear")
		_expect(absf(rebuilt.dot(tangent)) < 0.000001 and absf(rebuilt.dot(n)) < 0.000001,
			"sheared_uv_frame_is_orthogonal")
		_expect(rebuilt.is_equal_approx(imported_bitangent * handedness), "sheared_uv_frame_matches_imported_handedness")
		# A pure green-channel normal must point along the imported bitangent;
		# the old projected raw-v axis incorrectly contributed tangent red.
		var normal_map_green := (tangent * 0.0 + rebuilt * 0.8 + n * 0.6).normalized()
		_expect(absf(normal_map_green.dot(tangent)) < 0.000001,
			"green_normal_has_no_shear_induced_tangent_component")

func _check_affine_uv_reconstruction() -> void:
	# Two adjacent texels can belong to unrelated overlapping UV branches.
	# The stored row layout must reconstruct the selected affine map, while
	# its screen footprint remains independent of the other branch's UV.
	var du := Vector2(2.0, 0.5)
	var dv := Vector2(-0.25, 3.0)
	var centre_uv := Vector2(100.0, 200.0)
	var delta := Vector2(0.1, 0.2)
	var reconstructed := centre_uv + Vector2(du.dot(delta), dv.dot(delta))
	_expect(reconstructed.is_equal_approx(Vector2(100.3, 200.575)), "jacobian_component_order_and_affine_reconstruction")
	var screen_step := Vector2(0.01, -0.02)
	var gradient := Vector2(du.dot(screen_step), dv.dot(screen_step))
	_expect(gradient.is_equal_approx(Vector2(0.01, -0.0625)), "jacobian_screen_footprint")
	var unrelated_branch := Vector2(-1000.0, -2000.0)
	_expect((unrelated_branch - centre_uv).length() > gradient.length() * 10000.0,
		"overlap_fixture_exposes_false_cross_branch_lod")

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
		var jacobian: Dictionary = Blend._jacobian(path.get_base_dir(), layer)
		_expect(bool(jacobian.get("ok", false)), "actual_jacobian_decode_and_hash: " + str(jacobian.get("error", "")))
		if bool(jacobian.get("ok", false)):
			var image: Image = (jacobian.texture as ImageTexture).get_image()
			_expect(image.get_format() == Image.FORMAT_RGBAF and not image.has_mipmaps(), "jacobian_full_precision_single_level")
			var malformed: Dictionary = layer.duplicate(true)
			malformed.uv_jacobian.uncompressed_bytes = 1
			_expect(not bool(Blend._jacobian(path.get_base_dir(), malformed).get("ok", true)), "jacobian_wrong_decoded_size_rejected")
			malformed = layer.duplicate(true)
			malformed.uv_jacobian.sha256 = "0".repeat(64)
			_expect(not bool(Blend._jacobian(path.get_base_dir(), malformed).get("ok", true)), "jacobian_wrong_decoded_hash_rejected")
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

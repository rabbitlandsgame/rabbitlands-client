extends SceneTree
## CPU/headless protocol checks. This does not render or qualify appearance.
## --headless --path godot-client --script res://src/dev/road_texture_trial/contract_check.gd -- --trial PATH

const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
const TrialMaterial := preload("res://src/dev/road_texture_trial/trial_material.gd")
var _failures: Array[String] = []
var _checks := 0

func _init() -> void:
	var baseline: Dictionary = Trial.apply(null, "", "baseline")
	_expect(bool(baseline.get("ok", false)) and bool(baseline.metrics.get("no_op", false)), "baseline_is_no_op")
	var bad: Dictionary = Trial.apply(null, "", "mask")
	_expect(not bool(bad.get("ok", true)), "invalid_world_rejected")
	var identity: Array = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
	_expect(Trial._valid_matrix(identity), "identity_frame")
	var singular: Array = identity.duplicate()
	singular[0] = 0
	_expect(not Trial._valid_matrix(singular), "singular_frame_rejected")
	var source := ShaderMaterial.new()
	source.shader = load("res://src/world/look/painted_ground_blend.gdshader") as Shader
	var derived: Dictionary = TrialMaterial.build(source)
	_expect(bool(derived.get("ok", false)), "production_shader_anchors")
	if bool(derived.get("ok", false)):
		var code: String = (derived.material as ShaderMaterial).shader.code
		_expect(code.contains("trial_mesh_to_mask") and code.contains("dFdx(trial_uv)"), "derived_frame_and_flow")
		_expect(code.count("void vertex()") == 1 and code.count("void fragment()") == 1, "single_shader_entry_points")
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for i: int in args.size():
		if args[i] == "--trial" and i + 1 < args.size():
			_check_trial(args[i + 1])
	print(JSON.stringify({"checks": _checks, "failures": _failures, "gpu_appearance_tested": false}))
	quit(0 if _failures.is_empty() else 1)

func _check_trial(path: String) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		_expect(false, "trial_json_readable")
		return
	if parsed.get("chunks") is Array:
		for relative: Variant in parsed.chunks:
			_check_trial(path.get_base_dir().path_join(str(relative)))
		return
	var directory: String = path.get_base_dir()
	for value: Variant in parsed.get("layers", []):
		var layer: Dictionary = value
		var fields: Dictionary = Trial._fields(directory, layer)
		_expect(bool(fields.get("ok", false)), "field_payload: " + str(layer.uv_file) + " " + str(fields.get("error", "")))
		var malformed: Dictionary = layer.duplicate(true)
		malformed["uv_uncompressed_bytes"] = 1
		var rejected: Dictionary = Trial._fields(directory, malformed)
		_expect(not bool(rejected.get("ok", true)), "wrong_decoded_size_rejected")
		var material: Dictionary = layer.material_document.duplicate(true)
		Trial._prune_material_images(material)
		var glb: PackedByteArray = Trial._material_glb(material)
		_expect(glb.decode_u32(0) == 0x46546c67 and glb.decode_u32(8) == glb.size(), "material_glb_container_length")
		_expect(material.images.size() <= 3, "material_load_omits_unrelated_images")
	for value: Variant in parsed.get("nodes", []):
		var collider: Dictionary = Trial._collider(directory, value)
		_expect(bool(collider.get("ok", false)), "exact_collision: " + str(value.get("road_node_name", "")))
		if collider.get("node") is Node:
			(collider.node as Node).free()

func _expect(condition: bool, label: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)

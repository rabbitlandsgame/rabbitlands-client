extends SceneTree
## Type/serialization proof of the actual producer helper. Real cook/parity is
## still required; this never constructs a second SceneTree/cooker instance.
const Cooker := preload("res://tools/cook_prepared_assets.gd")
const BIOME := preload("res://src/world/biome_blend.gdshader")
const WATER := preload("res://src/world/continent_water.gdshader")
var failures := 0

class Probe extends RefCounted:
	var inputs: Dictionary = {}
	var include_requests: Array[Dictionary] = []
	func track(path: String) -> void:
		inputs[path] = FileAccess.get_sha256(path)
	func includes(code: String, path: String) -> String:
		include_requests.append({"path": path, "code": code})
		return code

func _init() -> void:
	_run.call_deferred()
func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("prepared shader identity: " + message)

func _run() -> void:
	var probe := Probe.new()
	for shader: Shader in [BIOME, WATER]:
		var original := shader.resource_path
		var preserved := Cooker._preserve_named_shader(shader, probe.track, probe.includes)
		_expect(preserved == shader and preserved.resource_path == original,
			"actual unchanged named shader Resource and semantic path are preserved")
		_expect(probe.inputs.get(original) == FileAccess.get_sha256(original)
			and probe.include_requests.back().path == original and probe.include_requests.back().code == shader.code,
			"producer tracks original complete bytes and requests transitive include scan in original frame")
		var material := ShaderMaterial.new()
		material.shader = preserved
		var path := "user://prepared-shader-" + original.get_file().get_basename() + ".res"
		_expect(ResourceSaver.save(material, path) == OK, "native material serializes")
		var loaded := ResourceLoader.load(path, "ShaderMaterial", ResourceLoader.CACHE_MODE_IGNORE) as ShaderMaterial
		_expect(loaded != null and loaded.shader == shader and loaded.shader.resource_path == original,
			"native material reload keeps original external shader identity")
		var dependencies := ResourceLoader.get_dependencies(path)
		var seen := false
		for dependency: String in dependencies:
			seen = seen or dependency.ends_with(original)
		_expect(seen, "original shader remains an explicit native runtime dependency")
		if shader == BIOME and loaded != null:
			var mesh := BoxMesh.new()
			_expect(LookGround.painted_for(loaded, LookGround.Kind.BIOME, mesh, 0, "whitehorn_range") != null,
				"existing biome semantic path remains recognizable by actual ground look consumer")
	var generated := Shader.new()
	generated.code = "shader_type spatial; void fragment() { ALBEDO=vec3(0.2); }"
	_expect(Cooker._preserve_named_shader(generated, probe.track, probe.includes) == null,
		"generated shader keeps native externalization path")
	var altered := BIOME.duplicate(false) as Shader
	altered.code += "\n// in-memory changed source\n"
	_expect(not Cooker._shader_matches_source(altered, BIOME.resource_path),
		"modified named program cannot masquerade as verified original source")
	await process_frame
	await process_frame
	print("prepared shader identity tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

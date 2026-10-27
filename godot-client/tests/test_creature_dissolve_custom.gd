extends SceneTree
## Custom face materials must compile during corpse dissolution and restore
## their exact original shader/parameters when a cinematic replay ends.
const Dissolve := preload("res://src/actors/creature_dissolve.gd")
const Face := preload("res://src/actors/face_appearance.gdshader")
var checks := 0
var failures := 0
func _init() -> void: run.call_deferred()
func expect(value: bool, detail: String) -> void:
	checks += 1
	if value: print("PASS: ", detail)
	else:
		failures += 1
		push_error(detail)
func run() -> void:
	var actor := Node3D.new()
	root.add_child(actor)
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	var source := ShaderMaterial.new()
	source.shader = Face
	source.set_shader_parameter("skin_color", Color(0.7,0.4,0.2,1))
	mesh.material_override = source
	actor.add_child(mesh)
	var effect := Dissolve.new()
	effect.begin(actor,4.0,72)
	var patched := mesh.get_surface_override_material(0) as ShaderMaterial
	expect(patched != null and patched != source, "dissolve uses a private copy of the custom face material")
	expect(not patched.shader.code.contains("#include"), "dynamic shader code contains resolved shared functions instead of a file include")
	var names: Array[String] = []
	for uniform: Dictionary in patched.shader.get_shader_uniform_list(): names.append(str(uniform.name))
	expect("dissolve_progress" in names and "skin_color" in names, "the shader compiler accepts both dissolve and original face parameters")
	expect(patched.get_shader_parameter("skin_color") == Color(0.7,0.4,0.2,1), "the custom face's appearance parameters survive dissolution")
	effect.update(0.5)
	expect(is_equal_approx(float(patched.get_shader_parameter("dissolve_progress")),0.5), "the corpse effect reaches its authored middle stage")
	expect(source.shader == Face and not Face.code.contains("dissolve_body"), "shared source shaders are never changed for another actor")
	effect.reset()
	expect(mesh.material_override == source and mesh.get_surface_override_material(0) == null, "ending a replay restores the original material and surface overrides")
	var native_body := ShaderMaterial.new()
	native_body.shader = Dissolve.BODY_SHADER
	for candidate: ShaderMaterial in [patched, native_body]:
		var replay := effect._body_material(candidate)
		expect(not replay.shader.code.contains("#include") and replay.shader.code.count("void dissolve_body(") == 1,
			"reusing a dissolve material resolves its include without duplicating functions")
		expect(replay.shader.code.count("dissolve_body(") == 2,
			"reusing a dissolve material keeps exactly one fragment call")
		var uniforms := replay.shader.get_shader_uniform_list()
		expect(not uniforms.is_empty(), "the shader compiler accepts the replayed native/custom dissolve")
	actor.queue_free()
	await process_frame
	print("Custom dissolve checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

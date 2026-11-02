extends SceneTree
## Validate real shader parsing/uniform contracts and shared variant identity.
## D3D11 compiler behavior still requires the actual browser render check.

func _initialize() -> void: _run.call_deferred()

func _uniforms(shader: Shader) -> PackedStringArray:
	var result := PackedStringArray()
	for uniform: Dictionary in shader.get_shader_uniform_list():
		result.append(str(uniform.name))
	result.sort()
	return result

func _run() -> void:
	var generated := LookGround._biome_painted_shader()
	assert(generated != null)
	for source: Shader in [LookGround.SHADER_OPAQUE, LookGround.SHADER_TWO_SIDED,
			LookGround.SHADER_OVERLAY, LookGround.SHADER_BLEND, LookGround.SHADER_DECK,
			LookGround.SHADER_CUTOUT, generated]:
		var original := source.code
		assert(LookGround.shader_for_renderer(source, false) == source)
		var browser := LookGround.shader_for_renderer(source, true)
		assert(browser != source and browser == LookGround.shader_for_renderer(source, true))
		assert(source.code == original and not original.contains("#define LOOK_WEB_BORDERS"))
		assert(browser.code.count("#define LOOK_WEB_BORDERS") == 1)
		var expected := _uniforms(source)
		assert(expected.size() > 10 and _uniforms(browser) == expected,
			"browser optimization must retain all material uniforms")
	assert(LookGround.shader_for_renderer(null, true) == null)
	print("PASS cached browser ground/biome variants preserve native shaders and uniform contracts")
	quit()

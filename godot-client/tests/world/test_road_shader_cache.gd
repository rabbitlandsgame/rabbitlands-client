extends SceneTree
## Exact-input shader reuse must not share per-chunk material state or retain
## retired Resources. The opt-out exercises the same uncached compositor.
const Composite := preload("res://src/world/road_ground/material.gd")
const Road := preload("res://src/world/road_ground/road_ground.gd")
const Season := preload("res://src/world/season_surfaces.gd")
const Ownership := preload("res://src/world/prepared_material_ownership.gd")
var failures: Array[String] = []
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label)

func _copy(source: ShaderMaterial, code: String) -> ShaderMaterial:
	var result := ShaderMaterial.new()
	result.shader = Shader.new()
	result.shader.code = code
	for uniform: Dictionary in source.shader.get_shader_uniform_list():
		result.set_shader_parameter(StringName(uniform.name), source.get_shader_parameter(StringName(uniform.name)))
	return result

func _same(a: ShaderMaterial, b: ShaderMaterial) -> bool:
	if a.shader.code != b.shader.code or a.render_priority != b.render_priority or a.next_pass != b.next_pass:
		return false
	for uniform: Dictionary in a.shader.get_shader_uniform_list():
		var name := StringName(uniform.name)
		if a.get_shader_parameter(name) != b.get_shader_parameter(name):
			return false
	return a.get_meta(&"terrain_blend_parameter_names") == b.get_meta(&"terrain_blend_parameter_names")

func _weak_program(base: ShaderMaterial, road: ShaderMaterial, styles: Array[BaseMaterial3D], sources: Dictionary) -> WeakRef:
	var unique := _copy(base, base.shader.code + "\n// weak lifetime probe\n")
	var made: Dictionary = Composite.build(unique, road, styles, true, {}, sources)
	return weakref((made.material as ShaderMaterial).shader)

func _seasonal_owner(base: ShaderMaterial, road: ShaderMaterial, styles: Array[BaseMaterial3D], sources: Dictionary) -> MeshInstance3D:
	var unique := _copy(base, base.shader.code + "\n// seasonal ownership probe\n")
	var made: Dictionary = Composite.build(unique, road, styles, true, {}, sources)
	var node := MeshInstance3D.new()
	node.mesh = PlaneMesh.new()
	node.material_override = made.material
	Ownership.attach(node)
	node.material_override = Season.material_for(made.material, Season.Kind.GROUND, node.mesh, 1.0)
	Ownership.refresh(node)
	return node

func _run() -> void:
	var previous := OS.get_environment("ELORIA_ROAD_SHADER_CACHE")
	OS.unset_environment("ELORIA_ROAD_SHADER_CACHE")
	Composite._programs.clear()
	Composite._program_order.clear()
	var source := StandardMaterial3D.new()
	source.albedo_color = Color(0.4, 0.7, 0.2)
	var style := StandardMaterial3D.new()
	style.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	style.albedo_color = Color(0.3, 0.2, 0.1, 0.8)
	var styles: Array[BaseMaterial3D] = [style]
	var base: ShaderMaterial = Road._pbr_adapter(source, true)
	var road: ShaderMaterial = Road._pbr_adapter(style, true)
	var sources := {"surface": FileAccess.get_file_as_string(Composite.SURFACE),
		"paint": FileAccess.get_file_as_string(Composite.PAINT)}
	var local_cache: Dictionary = {}
	var first: Dictionary = Composite.build(base, road, styles, true, local_cache, sources)
	var second: Dictionary = Composite.build(base, road, styles, true, {}, sources)
	_expect(first.ok and second.ok and not first.metrics.shader_cache_hit and second.metrics.shader_cache_hit,
		"separate chunk-local caches reuse an exact live program")
	_expect(first.material != second.material and first.material.shader == second.material.shader,
		"only the immutable Shader is shared")
	var other_base := _copy(base, base.shader.code)
	other_base.set_shader_parameter(&"albedo_color", Color(0.9, 0.1, 0.2))
	var other_style := style.duplicate() as StandardMaterial3D
	other_style.uv1_scale = Vector3(2, 3, 1)
	other_style.albedo_color = Color(0.8, 0.5, 0.3)
	var other_styles: Array[BaseMaterial3D] = [other_style]
	var private: Dictionary = Composite.build(other_base, road, other_styles, true, {}, sources)
	_expect(private.metrics.shader_cache_hit and private.material.shader == first.material.shader,
		"different uniform values reuse only the program")
	_expect(private.material.get_shader_parameter(&"albedo_color") != first.material.get_shader_parameter(&"albedo_color")
		and private.material.get_shader_parameter(&"rg_style_uv") != first.material.get_shader_parameter(&"rg_style_uv"),
		"base tint and style transforms stay private")
	OS.set_environment("ELORIA_ROAD_SHADER_CACHE", "0")
	var control: Dictionary = Composite.build(base, road, styles, true, {}, sources)
	var control_again: Dictionary = Composite.build(base, road, styles, true, {}, sources)
	_expect(not control.metrics.shader_cache_hit and control.material.shader != control_again.material.shader,
		"diagnostic opt-out restores per-call program construction")
	_expect(_same(first.material, control.material) and first.shader_sha256 == control.shader_sha256,
		"cached and uncached shader bytes and every material uniform match")
	var arguments := OS.get_cmdline_user_args()
	for index: int in arguments.size():
		if arguments[index] == "--control" and index + 1 < arguments.size():
			var original: Variant = load(arguments[index + 1])
			var baseline: Dictionary = original.build(base, road, styles, true, {}, sources)
			_expect(_same(first.material, baseline.material) and first.shader_sha256 == baseline.shader_sha256,
				"preserved pre-change compositor matches exact shader bytes and uniforms")
	OS.unset_environment("ELORIA_ROAD_SHADER_CACHE")
	for changed: String in ["base", "road", "surface", "paint", "painted"]:
		var input := sources.duplicate()
		var b := base
		var r := road
		if changed == "base": b = _copy(base, base.shader.code + "\n// base key probe\n")
		if changed == "road": r = _copy(road, road.shader.code + "\n// road key probe\n")
		if changed in ["surface", "paint"]: input[changed] += "\n// source key probe\n"
		var variant: Dictionary = Composite.build(b, r, styles, changed != "painted", {}, input)
		_expect(variant.ok and not variant.metrics.shader_cache_hit, "changed structural input invalidates: " + changed)
	# A consumer must not be able to poison the shared program for later chunks.
	(first.material.shader as Shader).code += "\n// changed after publication\n"
	var repaired: Dictionary = Composite.build(base, road, styles, true, local_cache, sources)
	_expect(not repaired.metrics.shader_cache_hit and repaired.material.shader.code == control.material.shader.code,
		"a mutated shared Shader is rebuilt from authoritative current inputs")
	var expired := _weak_program(base, road, styles, sources)
	_expect(expired.get_ref() == null, "cache does not retain an unreferenced Shader")
	var owner := _seasonal_owner(base, road, styles, sources)
	var seasonal_source := (owner.material_override as Material).get_meta(Season.SOURCE_META) as ShaderMaterial
	var seasonal_program: WeakRef = weakref(seasonal_source.shader)
	seasonal_source = null
	var seasonal_base := _copy(base, base.shader.code + "\n// seasonal ownership probe\n")
	var neighbor: Dictionary = Composite.build(seasonal_base, road, styles, true, {}, sources)
	_expect(neighbor.metrics.shader_cache_hit and neighbor.material.shader == seasonal_program.get_ref(),
		"a live seasonal replacement preserves shader reuse by the next chunk")
	neighbor.clear()
	owner.free()
	_expect(seasonal_program.get_ref() == null, "retiring the seasonal owner releases the original shared Shader")
	var held: Array[ShaderMaterial] = []
	for index: int in Composite.PROGRAM_LIMIT + 1:
		var unique := _copy(base, base.shader.code + "\n// bounded variant %d\n" % index)
		var row: Dictionary = Composite.build(unique, road, styles, true, {}, sources)
		held.append(row.material)
	_expect(Composite._programs.size() <= Composite.PROGRAM_LIMIT
		and Composite._program_order.size() <= Composite.PROGRAM_LIMIT,
		"live variants cannot grow the cache beyond its fixed bound")
	_expect(held[0].shader != null and not held[0].shader.code.is_empty(),
		"eviction preserves programs still held by live materials")
	if previous.is_empty(): OS.unset_environment("ELORIA_ROAD_SHADER_CACHE")
	else: OS.set_environment("ELORIA_ROAD_SHADER_CACHE", previous)
	print(JSON.stringify({"checks": checks, "failures": failures, "first_metrics": first.metrics,
		"reused_metrics": second.metrics, "uncached_metrics": control.metrics}))
	quit(0 if failures.is_empty() else 1)

extends SceneTree
## Guards the Mobile renderer's depth pre-pass for the painted walk decks and
## patches (LookGround.mobile_prepass, painted_ground_*_prepass.gdshader).
##
## Forward+ draws the fully covered fragments of every depth_prepass_alpha
## surface into depth before anything blends; Mobile has no such pass, so on
## the Four Gates plaza a patch sorted after a deck painted over it and every
## deck's edging band drew a black seam across the decks it crosses. Under
## Mobile each painted deck and solid patch therefore chains an opaque copy of
## itself that writes that depth. This test checks, headless (the renderer is
## injected with RendererFamily.override_for_tests):
## - Forward+ and Compatibility get nothing: the painted materials are the
##   ones they were, with no next pass, so they draw exactly as before, and
##   the pre-pass shaders are never loaded (a loaded shader is translated and,
##   on the RenderingDevice renderers, compiled); worker threads asking at
##   once share one load;
## - under Mobile a deck and a solid patch get a pre-pass with the right
##   shader, the main material's uniforms, no look metadata, chained ahead of
##   any next pass the source had; a glaze (PATCH_OPACITY, a tint below the
##   threshold), the opaque, blended and cut-out ground and other materials
##   get none; asking twice chains one pre-pass;
## - LookGround.paint chains it under Mobile only, once, and a seasonal copy
##   (SeasonSurfaces) keeps it; what carries it is ground OccluderFade never
##   fades (LookFade.keeps_solid), so the pre-pass never needs the fade hole;
## - the shader sources: preprocessed as Godot does for each renderer, the
##   deck and patch shaders contain no pre-pass code, and the pre-pass shaders
##   are opaque (they never write ALPHA), unshaded, keep the threshold
##   LookGround.PREPASS_THRESHOLD and keep the include's text anchors the
##   portable road compositor and the season copies cut at.
## The rendered proof (Mobile against Forward+ on an iGPU) is
## tests/integration/rendered_mobile_ground_parity.gd.

const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const SeasonSurfaces := preload("res://src/world/season_surfaces.gd")
const SURFACE := "res://src/world/look/painted_ground_surface.gdshaderinc"
const DECK_PREPASS := "res://src/world/look/painted_ground_deck_prepass.gdshader"
const OVERLAY_PREPASS := "res://src/world/look/painted_ground_overlay_prepass.gdshader"
## Uniforms painted_source_for sets that decide a fragment's alpha or depth.
const COVERAGE_UNIFORMS := ["albedo_texture", "albedo_color", "use_vertex_alpha", "look_rim",
	"look_rim_lobe", "look_rim_grain", "look_rim_noise_metres", "look_opacity", "look_edge_band",
	"look_edge_band_paving", "look_edge_band_from", "look_edge_band_push", "look_paving_rects",
	"look_paving_count", "look_paving_inset", "uv1_scale", "uv1_offset", "look_class_metres"]
const RENDERERS := {"forward_plus": 2, "mobile": 1, "gl_compatibility": 0}

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	if not await _loading():
		# A worker still holds the load: stop before main waits on it too.
		print("test_look_ground_mobile_prepass: FAIL (%d failures)" % failures)
		quit(1)
		return
	_materials()
	_paint()
	_sources()
	RendererFamily.override_for_tests("")
	OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	print("test_look_ground_mobile_prepass: %s (%d failures)" % [
		"PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

func _blended(colour: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = colour
	return material

## Before anything asks under Mobile: Forward+ and Compatibility paint and ask
## for pre-passes without loading the pre-pass shaders (a loaded shader is
## translated by the renderer and, on the RenderingDevice renderers,
## compiled). Then two worker threads ask first at once, as the loader's
## workers paint, and share one loaded shader. They are polled while frames
## run, never joined while alive: like every RL loader worker, a load off the
## main thread may wait for the main thread to serve a RenderingServer call.
func _loading() -> bool:
	var mesh := _mesh_data()
	for method: String in [RendererFamily.FORWARD_PLUS, RendererFamily.COMPATIBILITY]:
		RendererFamily.override_for_tests(method)
		var world := Node3D.new()
		world.name = "ImportedWorld_unloaded"
		root.add_child(world)
		_mesh(world, "Walk_unloaded_highway_4_5", _blended(Color("997a4f")))
		var patch := _blended(Color("c8c4bc"))
		_mesh(world, "AuthoredGround_unloaded_ground-03_4_5", patch)
		LookGround.paint(world)
		var solid := LookGround.painted_for(patch, LookGround.Kind.PATCH, mesh, 0) as ShaderMaterial
		solid.set_shader_parameter(&"look_opacity", 1.0)
		LookGround.mobile_prepass(solid)
		root.remove_child(world)
		world.free()
	RendererFamily.override_for_tests("")
	_expect(not ResourceLoader.has_cached(DECK_PREPASS)
		and not ResourceLoader.has_cached(OVERLAY_PREPASS),
		"forward_plus/gl_compatibility: painting loads no pre-pass shader")
	var threads: Array[Thread] = [Thread.new(), Thread.new()]
	for thread: Thread in threads:
		thread.start(func() -> Shader: return LookGround.prepass_shader(LookGround.SHADER_DECK))
	var deadline := Time.get_ticks_msec() + 60000
	while (threads[0].is_alive() or threads[1].is_alive()) and Time.get_ticks_msec() < deadline:
		await process_frame
	var alive := threads[0].is_alive() or threads[1].is_alive()
	_expect(not alive, "worker threads load the pre-pass shader while frames run")
	if alive:
		return false
	var loaded: Array = [threads[0].wait_to_finish(), threads[1].wait_to_finish()]
	_expect(loaded[0] != null and loaded[0] == loaded[1]
		and (loaded[0] as Shader).resource_path == DECK_PREPASS
		and loaded[0] == LookGround.prepass_shader(LookGround.SHADER_DECK),
		"worker threads asking at once share one loaded pre-pass shader")
	return true

func _materials() -> void:
	var mesh := _mesh_data()
	var deck_source := _blended(Color("997a4f"))
	var original_next := StandardMaterial3D.new()
	deck_source.next_pass = original_next
	for method: String in [RendererFamily.FORWARD_PLUS, RendererFamily.COMPATIBILITY]:
		RendererFamily.override_for_tests(method)
		var paint := LookGround.painted_for(deck_source, LookGround.Kind.DECK, mesh, 0) as ShaderMaterial
		_expect(paint != null and paint.shader == LookGround.SHADER_DECK
			and LookGround.mobile_prepass(paint) == null and paint.next_pass == original_next,
			"%s: a deck gets no pre-pass and keeps its own next pass" % method)
	RendererFamily.override_for_tests(RendererFamily.MOBILE)
	var deck := LookGround.painted_for(deck_source, LookGround.Kind.DECK, mesh, 0) as ShaderMaterial
	var prepass := LookGround.mobile_prepass(deck)
	_expect(prepass != null and prepass.shader != null and prepass.shader.resource_path == DECK_PREPASS
		and prepass.shader == LookGround.prepass_shader(LookGround.SHADER_DECK)
		and deck.next_pass == prepass and prepass.next_pass == original_next
		and prepass.has_meta(LookGround.PREPASS_META),
		"mobile: a deck chains its pre-pass ahead of the source's next pass")
	_expect(deck.shader == LookGround.SHADER_DECK and not deck.has_meta(LookGround.PREPASS_META),
		"mobile: the deck itself keeps the deck shader")
	var same := prepass != null
	for name: String in COVERAGE_UNIFORMS:
		same = same and prepass.get_shader_parameter(name) == deck.get_shader_parameter(name)
	_expect(same, "mobile: the pre-pass has the deck's coverage and depth uniforms")
	_expect(prepass != null and not prepass.has_meta(LookProfile.SOURCE_META)
		and not prepass.has_meta(LookFade.FADED_SHADER_META)
		and prepass.render_priority == deck.render_priority,
		"mobile: the pre-pass names no source and no faded shader (it is no surface material)")
	_expect(LookGround.mobile_prepass(deck) == prepass and deck.next_pass == prepass
		and prepass.next_pass == original_next, "mobile: asking again chains no second pre-pass")
	_expect(LookGround.mobile_prepass(deck, RendererFamily.FORWARD_PLUS) == null,
		"an explicit Forward+ method gets none")

	# Patches: a solid one gets the overlay pre-pass, a glaze none.
	var patch_source := _blended(Color("ffa85c"))
	var glaze := LookGround.painted_for(patch_source, LookGround.Kind.PATCH, mesh, 0) as ShaderMaterial
	_expect(glaze != null and glaze.shader == LookGround.SHADER_OVERLAY
		and is_equal_approx(float(glaze.get_shader_parameter(&"look_opacity")), LookProfile.PATCH_OPACITY)
		and LookGround.mobile_prepass(glaze) == null and glaze.next_pass == null,
		"mobile: a yard glaze (PATCH_OPACITY) never reaches the threshold and gets none")
	var solid := LookGround.painted_for(patch_source, LookGround.Kind.PATCH, mesh, 0) as ShaderMaterial
	solid.set_shader_parameter(&"look_opacity", 1.0)
	var overlay := LookGround.mobile_prepass(solid)
	_expect(overlay != null and overlay.shader != null and overlay.shader.resource_path == OVERLAY_PREPASS
		and overlay.shader == LookGround.prepass_shader(LookGround.SHADER_OVERLAY)
		and solid.next_pass == overlay, "mobile: a solid patch chains the overlay pre-pass")
	_expect(LookGround.prepass_shader(LookGround.SHADER_BLEND) == null
		and LookGround.prepass_shader(null) == null, "only the deck and patch shaders have a pre-pass")
	var shared := LookGround.painted_for(_blended(Color("997a4f")), LookGround.Kind.DECK, mesh, 0) as ShaderMaterial
	var second := LookGround.mobile_prepass(shared)
	_expect(second != null and prepass != null and second != prepass and second.shader == prepass.shader,
		"mobile: every deck's pre-pass shares one loaded shader")
	var faint := LookGround.painted_for(_blended(Color(0.9, 0.8, 0.7, 0.9)), LookGround.Kind.DECK, mesh, 0) \
		as ShaderMaterial
	_expect(faint != null and LookGround.mobile_prepass(faint) == null,
		"mobile: a deck whose tint alpha is below the threshold gets none")
	_expect(LookGround.reaches_prepass(deck) and not LookGround.reaches_prepass(glaze)
		and LookGround.PREPASS_THRESHOLD == 0.99, "reaches_prepass follows opacity times tint alpha")

	# Everything else.
	var terrain_source := StandardMaterial3D.new()
	terrain_source.vertex_color_use_as_albedo = true
	var terrain := LookGround.painted_for(terrain_source, LookGround.Kind.TERRAIN, mesh, 0) as ShaderMaterial
	var blend_source := StandardMaterial3D.new()
	blend_source.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var blend := LookGround.painted_for(blend_source, LookGround.Kind.PATCH, mesh, 0) as ShaderMaterial
	var cutout_source := StandardMaterial3D.new()
	cutout_source.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	var cutout := LookGround.painted_for(cutout_source, LookGround.Kind.PATCH, mesh, 0) as ShaderMaterial
	_expect(terrain != null and terrain.shader == LookGround.SHADER_OPAQUE
		and blend != null and blend.shader == LookGround.SHADER_BLEND
		and cutout != null and cutout.shader == LookGround.SHADER_CUTOUT
		and LookGround.mobile_prepass(terrain) == null and LookGround.mobile_prepass(blend) == null
		and LookGround.mobile_prepass(cutout) == null
		and terrain.next_pass == null and blend.next_pass == null and cutout.next_pass == null,
		"mobile: opaque, blended and cut-out ground gets none (Forward+ pre-passes none of them)")
	_expect(LookGround.mobile_prepass(StandardMaterial3D.new()) == null
		and LookGround.mobile_prepass(null) == null, "mobile: other materials get none")

	# A seasonal copy duplicates the painted deck and keeps its next pass.
	var seasonal := SeasonSurfaces.material_for(deck, SeasonSurfaces.Kind.GROUND, mesh, 1.0)
	_expect(seasonal != null and seasonal != deck and seasonal.next_pass == prepass,
		"mobile: a seasonal copy of a deck keeps the pre-pass")
	RendererFamily.override_for_tests("")

func _paint() -> void:
	var counts := {}
	for method: String in [RendererFamily.FORWARD_PLUS, RendererFamily.MOBILE,
			RendererFamily.COMPATIBILITY]:
		RendererFamily.override_for_tests(method)
		var world := Node3D.new()
		world.name = "ImportedWorld_prepass"
		root.add_child(world)
		var deck_source := _blended(Color("997a4f"))
		var cobble_source := _blended(Color("c8c4bc"))
		var deck_a := _mesh(world, "Walk_prepass_highway-a_prepass_4_5", deck_source)
		var deck_b := _mesh(world, "Walk_prepass_highway-b_prepass_4_5", deck_source)
		var patch := _mesh(world, "AuthoredGround_prepass_ground-03_prepass_4_5", cobble_source)
		var painted := LookGround.paint(world)
		var deck_paint := deck_a.get_surface_override_material(0) as ShaderMaterial
		var patch_paint := patch.get_surface_override_material(0) as ShaderMaterial
		var chained := 0
		for paint: ShaderMaterial in [deck_paint, patch_paint]:
			if paint != null and paint.next_pass != null and paint.next_pass.has_meta(LookGround.PREPASS_META):
				chained += 1
		counts[method] = chained
		_expect(painted == 3 and deck_paint != null and deck_b.get_surface_override_material(0) == deck_paint,
			"%s: paint paints the decks and the patch as before" % method)
		_expect(LookFade.keeps_solid(String(deck_a.name)) and LookFade.keeps_solid(String(patch.name)),
			"%s: what carries a pre-pass is never faded, so the pre-pass needs no occluder hole" % method)
		if method == RendererFamily.MOBILE:
			var opacity := float(patch_paint.get_shader_parameter(&"look_opacity")) if patch_paint != null else 0.0
			_expect(chained == (2 if opacity >= LookGround.PREPASS_THRESHOLD else 1),
				"mobile: paint chains a pre-pass on the deck and on the patch when it is solid (opacity %.2f)" % opacity)
			var before := deck_paint.next_pass
			LookGround.paint(world)
			_expect(deck_paint.next_pass == before and before.next_pass == null,
				"mobile: painting again leaves one pre-pass")
		else:
			_expect(chained == 0 and deck_paint.next_pass == null,
				"%s: paint chains no pre-pass" % method)
		root.remove_child(world)
		world.free()
	RendererFamily.override_for_tests("")

## Preprocesses the shader sources as Godot does for each renderer and checks
## what each one compiles.
func _sources() -> void:
	var deck := FileAccess.get_file_as_string("res://src/world/look/painted_ground_deck.gdshader")
	var overlay := FileAccess.get_file_as_string("res://src/world/look/painted_ground_overlay.gdshader")
	var deck_prepass := FileAccess.get_file_as_string("res://src/world/look/painted_ground_deck_prepass.gdshader")
	var overlay_prepass := FileAccess.get_file_as_string("res://src/world/look/painted_ground_overlay_prepass.gdshader")
	for method: String in RENDERERS:
		for pair: Array in [["deck", deck], ["overlay", overlay]]:
			var active := _preprocess(pair[1], int(RENDERERS[method]))
			_expect(RegEx.create_from_string("look_prepass|prepass_clip|0[.]000002").search(active) == null
				and active.contains("ALPHA = 1.0 - (1.0 - covered) * (1.0 - band);")
				and active.contains("ALBEDO *= covered / max(ALPHA, 0.0001);"),
				"%s: the %s shader compiles no pre-pass code and blends as before" % [method, pair[0]])
		for pair: Array in [["deck", deck_prepass], ["overlay", overlay_prepass]]:
			var active := _preprocess(pair[1], int(RENDERERS[method]))
			var writes_alpha := RegEx.create_from_string("\\bALPHA\\s*=[^=]").search(active) != null
			_expect(not writes_alpha and active.contains("if (look_prepass_alpha < 0.99) {")
				and active.contains("DEPTH") and active.contains("ALBEDO = albedo;"),
				"%s: the %s pre-pass is opaque, keeps the 0.99 threshold and writes depth" % [method, pair[0]])
	for pair: Array in [["deck", deck_prepass, true], ["overlay", overlay_prepass, false]]:
		var code: String = pair[1]
		var first := code.find("render_mode")
		_expect(first >= 0 and code.substr(first).begins_with("render_mode unshaded, cull_disabled, fog_disabled;")
			and code.contains("#define LOOK_GROUND_PREPASS") and code.contains("#define LOOK_GROUND_ALPHA")
			and code.contains("#define LOOK_GROUND_EDGE_BAND") == bool(pair[2]),
			"the %s pre-pass shader is unshaded, two-sided and fog-free, its first render_mode its own" % pair[0])
	_expect(deck.contains("render_mode blend_mix, depth_prepass_alpha, cull_disabled;")
		and overlay.contains("render_mode blend_mix, depth_prepass_alpha, cull_disabled;"),
		"the deck and patch shaders keep their render modes")
	# The portable road compositor and the raw-surface splice cut the include
	# at these anchors, each exactly once (road_ground/material.gd).
	var surface := FileAccess.get_file_as_string(SURFACE)
	var anchored := true
	for anchor: String in ["void vertex() {", "void fragment() {", "look_ground_xz = VERTEX.xz;",
			"NORMAL_MAP = texture(normal_texture, UV).rgb;", "NORMAL_MAP_DEPTH = normal_scale;",
			"float coverage = 1.0;", "#ifdef LOOK_GROUND_CUTOUT", "\tif (look_debug > 0)",
			"\tROUGHNESS = roughness_value;"]:
		anchored = anchored and surface.count(anchor) == 1
	var fragment := surface.find("void fragment() {")
	var alpha := surface.find("#ifdef LOOK_GROUND_ALPHA", fragment)
	var coverage := surface.find("float coverage = 1.0;", alpha)
	var cutout := surface.find("#ifdef LOOK_GROUND_CUTOUT", coverage)
	var debug := surface.find("\tif (look_debug > 0)")
	var roughness := surface.find("\tROUGHNESS = roughness_value;", debug)
	_expect(anchored and fragment < alpha and alpha < coverage and coverage < cutout
		and not surface.substr(fragment, alpha - fragment).to_lower().contains("prepass")
		and not surface.substr(coverage, cutout - coverage).to_lower().contains("prepass")
		and not surface.substr(debug, roughness - debug).to_lower().contains("prepass"),
		"the include keeps the compositor's anchors and no pre-pass code inside the spans it copies")

## `code` as Godot's shader preprocessor leaves it for `renderer`
## (RENDERER_COMPATIBILITY 0, MOBILE 1, FORWARD_PLUS 2): #include inlined,
## #define, #ifdef, #ifndef, #if CURRENT_RENDERER ==/!= RENDERER_*, #else and
## #endif applied; comments and directives dropped.
func _preprocess(code: String, renderer: int, defines: Dictionary = {}) -> String:
	var names := {"RENDERER_COMPATIBILITY": 0, "RENDERER_MOBILE": 1, "RENDERER_FORWARD_PLUS": 2}
	var out := PackedStringArray()
	var stack: Array[bool] = []
	var taken: Array[bool] = []
	for raw: String in code.split("\n"):
		var line := raw.strip_edges()
		var live := not stack.has(false)
		if line.begins_with("#ifdef ") or line.begins_with("#ifndef "):
			var wanted := defines.has(line.get_slice(" ", 1).strip_edges())
			var value := wanted if line.begins_with("#ifdef ") else not wanted
			stack.append(value)
			taken.append(value)
		elif line.begins_with("#if "):
			var parts := line.substr(4).split(" ", false)
			var value := false
			if parts.size() == 3 and parts[0] == "CURRENT_RENDERER" and names.has(parts[2]):
				value = (renderer == int(names[parts[2]])) == (parts[1] == "==")
			else:
				_expect(false, "unexpected directive " + line)
			stack.append(value)
			taken.append(value)
		elif line == "#else":
			stack[stack.size() - 1] = not taken[taken.size() - 1]
		elif line == "#endif":
			stack.pop_back()
			taken.pop_back()
		elif not live:
			continue
		elif line.begins_with("#define "):
			defines[line.get_slice(" ", 1).strip_edges()] = true
		elif line.begins_with("#include "):
			out.append(_preprocess(FileAccess.get_file_as_string(line.get_slice("\"", 1)), renderer, defines))
		elif not line.begins_with("//") and not line.is_empty():
			out.append(raw.get_slice("//", 0) if not raw.strip_edges().begins_with("//") else "")
	return "\n".join(out)

func _mesh_data() -> ArrayMesh:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	for corner: Vector3 in [Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 0, 1)]:
		tool.set_color(Color(1, 1, 1, 0.5))
		tool.set_normal(Vector3.UP)
		tool.set_uv(Vector2(corner.x, corner.z))
		tool.add_vertex(corner)
	return tool.commit()

func _mesh(parent: Node, node_name: String, material: Material) -> MeshInstance3D:
	var mesh := _mesh_data()
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	parent.add_child(node)
	return node

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)

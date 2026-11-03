extends SceneTree
## Guards src/runtime/renderer_family.gd and the look's use of it.
##
## Forward+ and Mobile light in linear space and share one content storage, so
## they take the same colour trims and cache key; only Forward+ has SSAO and
## SSIL; Mobile and Compatibility light 8 lights per mesh instance. The look
## files ask the family, never the engine's method name, so:
## - under Forward+ the look computes exactly what it did before the family
##   existed: tests/renderer_family_look_dump.gd's dump of every region file,
##   the grade, the painted ground, water, kept chroma, borders and grass
##   matches the golden digests (tests/fixtures/renderer_family_look_golden.json,
##   taken from the code before the change) byte for byte, and so does the
##   compatibility renderer's;
## - under Mobile the dump is Forward+'s, except that no screen-space effect is
##   set (as in the compatibility renderer). Before the family, Mobile painted
##   the compatibility renderer's trims.
##
## The golden pins the region files it was taken from (its `inputs` digest).
## After a deliberate retune of a region file the comparison is skipped with a
## note; after a deliberate retune of a look constant it fails. Either way,
## once the change is reviewed, rewrite it with
##   Godot --headless --path godot-client --script tests/test_renderer_family.gd -- --write-golden
## The renderer checks themselves (Mobile equals Forward+) never need a golden.

const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const Dump := preload("res://tests/renderer_family_look_dump.gd")
const GOLDEN_PATH := "res://tests/fixtures/renderer_family_look_golden.json"
const LOOK_DIRECTORY := "res://src/world/look"
## The environment settings only Forward+ sets (LookGrade._grade_screen_space).
const SCREEN_SPACE_PROPERTIES := ["ssao_enabled", "ssao_radius", "ssao_intensity",
	"ssao_power", "ssao_detail", "ssao_light_affect", "ssil_enabled", "ssil_radius",
	"ssil_intensity"]

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_family()
	_look_profile()
	_no_method_names_in_look()
	var dumps := {}
	for method: String in [RendererFamily.FORWARD_PLUS, RendererFamily.MOBILE,
			RendererFamily.COMPATIBILITY]:
		RendererFamily.override_for_tests(method)
		dumps[method] = Dump.dump(root)
	RendererFamily.override_for_tests("")
	_mobile_is_linear(dumps)
	if OS.get_cmdline_user_args().has("--write-golden"):
		_write_golden(dumps)
	else:
		_golden(dumps)
	print("test_renderer_family: %s (%d failures)" % [
		"PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

func _family() -> void:
	var engine := RenderingServer.get_current_rendering_method()
	_expect(RendererFamily.method() == engine,
		"without an override the family reports the engine's method (%s)" % engine)
	var table := {
		RendererFamily.FORWARD_PLUS: [true, true, 0, RendererFamily.FORWARD_PLUS],
		RendererFamily.MOBILE: [true, false, 8, RendererFamily.FORWARD_PLUS],
		RendererFamily.COMPATIBILITY: [false, false, 8, RendererFamily.COMPATIBILITY],
	}
	for method: String in table:
		var expected: Array = table[method]
		_expect(RendererFamily.linear_lighting(method) == expected[0]
			and RendererFamily.screen_space_effects(method) == expected[1]
			and RendererFamily.per_mesh_light_limit(method) == expected[2]
			and RendererFamily.cache_renderer(method) == expected[3],
			"%s: linear %s, screen-space %s, %d lights per mesh, cache key %s"
				% [method, expected[0], expected[1], expected[2], expected[3]])
		RendererFamily.override_for_tests(method)
		_expect(RendererFamily.method() == method
			and RendererFamily.linear_lighting() == expected[0]
			and RendererFamily.screen_space_effects() == expected[1]
			and RendererFamily.per_mesh_light_limit() == expected[2]
			and RendererFamily.cache_renderer() == expected[3],
			"%s: the helpers' defaults follow the override" % method)
		# Loader workers ask too: they must see the same answer.
		var answers: Array = []
		answers.resize(8)
		var task := WorkerThreadPool.add_group_task(func(index: int) -> void:
			answers[index] = [RendererFamily.method(), RendererFamily.linear_lighting()],
			answers.size())
		WorkerThreadPool.wait_for_group_task_completion(task)
		var agreed := true
		for answer: Variant in answers:
			agreed = agreed and answer == [method, expected[0]]
		_expect(agreed, "%s: worker threads get the same answer" % method)
	RendererFamily.override_for_tests("")
	_expect(RendererFamily.method() == engine, "an empty override restores the engine's method")
	_expect(not RendererFamily.linear_lighting("dummy")
		and not RendererFamily.screen_space_effects("dummy")
		and RendererFamily.per_mesh_light_limit("dummy") == 0
		and RendererFamily.cache_renderer("dummy") == "dummy",
		"a method outside the three belongs to no family and keys its own cache")

func _look_profile() -> void:
	LookProfile.reload_regions()
	RendererFamily.override_for_tests(RendererFamily.MOBILE)
	_expect(LookProfile.linear_renderer() and LookProfile.forward_plus()
		and not LookProfile.screen_space_effects(),
		"Mobile is a linear renderer without screen-space effects")
	_expect(LookProfile.map_trim("lantern_reach", "exposure") == 1.04
		and LookProfile.ground_value("lantern_reach", "verge_value_green", -1.0) == 0.9
		and LookProfile.ground_value("lantern_reach", "verge_green_red", -1.0) == 0.55,
		"Mobile reads a region's `_forward` keys")
	_expect(LookProfile.ground_value("no_such_region", "path_luma", -1.0)
			== LookProfile.GROUND_FORWARD.path_luma
		and LookProfile.renderer_exposure() == LookProfile.FORWARD_EXPOSURE
		and LookProfile.sun_warmth() == LookProfile.SUN_WARMTH_FORWARD
		and LookProfile.saturation(1.0) == LookProfile.SATURATION_FORWARD,
		"Mobile takes GROUND_FORWARD and the Forward+ grade trims")
	RendererFamily.override_for_tests(RendererFamily.COMPATIBILITY)
	_expect(not LookProfile.linear_renderer() and not LookProfile.screen_space_effects()
		and LookProfile.map_trim("lantern_reach", "exposure") == 1.6
		and LookProfile.ground_value("lantern_reach", "verge_value_green", -1.0) == 0.82
		and LookProfile.ground_value("no_such_region", "path_luma", -1.0) == -1.0
		and LookProfile.renderer_exposure() == 1.0
		and LookProfile.sun_warmth() == LookProfile.SUN_WARMTH,
		"the compatibility renderer reads its `_compat` and bare keys and no Forward+ default")
	RendererFamily.override_for_tests(RendererFamily.FORWARD_PLUS)
	_expect(LookProfile.linear_renderer() and LookProfile.screen_space_effects()
		and LookProfile.map_trim("lantern_reach", "exposure") == 1.04,
		"Forward+ is a linear renderer with screen-space effects")
	RendererFamily.override_for_tests("")
	LookProfile.reload_regions()

## The look files ask RendererFamily (through LookProfile), never the engine.
func _no_method_names_in_look() -> void:
	var offenders := PackedStringArray()
	for file: String in DirAccess.get_files_at(LOOK_DIRECTORY):
		if file.get_extension() != "gd":
			continue
		var source := FileAccess.get_file_as_string(LOOK_DIRECTORY.path_join(file))
		if source.contains("get_current_rendering_method") or source.contains("\"forward_plus\""):
			offenders.append(file)
	_expect(offenders.is_empty(), "no look file names a rendering method itself (%s)"
		% ", ".join(offenders))

## Mobile's dump is Forward+'s apart from the screen-space settings, which it
## leaves as the compatibility renderer does.
func _mobile_is_linear(dumps: Dictionary) -> void:
	var forward: Dictionary = dumps[RendererFamily.FORWARD_PLUS]
	var mobile: Dictionary = dumps[RendererFamily.MOBILE]
	var compat: Dictionary = dumps[RendererFamily.COMPATIBILITY]
	_expect(Dump.digest(_without_screen_space(mobile)) == Dump.digest(_without_screen_space(forward)),
		"Mobile's look is Forward+'s, byte for byte, but for screen-space effects%s"
			% _first_difference(_without_screen_space(forward), _without_screen_space(mobile)))
	_expect(Dump.digest(mobile.screen_space) == Dump.digest(compat.screen_space)
		and not bool(mobile.scalars.screen_space_effects)
		and bool(forward.scalars.screen_space_effects),
		"Mobile sets no SSAO or SSIL, as the compatibility renderer does")
	_expect(Dump.digest(forward) != Dump.digest(compat),
		"the compatibility renderer's look differs from the linear renderers'")

func _golden(dumps: Dictionary) -> void:
	if not FileAccess.file_exists(GOLDEN_PATH):
		_expect(false, "the golden %s exists" % GOLDEN_PATH)
		return
	var golden: Variant = JSON.parse_string(FileAccess.get_file_as_string(GOLDEN_PATH))
	if golden is not Dictionary:
		_expect(false, "the golden %s is a JSON object" % GOLDEN_PATH)
		return
	var inputs := Dump.inputs_digest()
	if str((golden as Dictionary).get("inputs", "")) != inputs:
		print("SKIP golden: the region files changed since it was taken (inputs %s, golden %s);"
			% [inputs.left(12), str((golden as Dictionary).get("inputs", "")).left(12)]
			+ " rewrite it with -- --write-golden once the change is reviewed")
		return
	for method: String in [RendererFamily.FORWARD_PLUS, RendererFamily.COMPATIBILITY]:
		var expected: Variant = (golden as Dictionary).get(method)
		var actual := Dump.digests(dumps[method])
		var differences := _digest_differences(expected if expected is Dictionary else {}, actual)
		_expect(differences.is_empty(), "%s: the look is byte-identical to the golden%s"
			% [method, "" if differences.is_empty() else " (differs: %s)" % ", ".join(differences)])

func _write_golden(dumps: Dictionary) -> void:
	var golden := {
		"about": "MOB-C1 golden: digests of tests/renderer_family_look_dump.gd per renderer; "
			+ "see tests/test_renderer_family.gd",
		"inputs": Dump.inputs_digest(),
		RendererFamily.FORWARD_PLUS: Dump.digests(dumps[RendererFamily.FORWARD_PLUS]),
		RendererFamily.COMPATIBILITY: Dump.digests(dumps[RendererFamily.COMPATIBILITY]),
	}
	var file := FileAccess.open(GOLDEN_PATH, FileAccess.WRITE)
	_expect(file != null, "the golden can be written to %s" % GOLDEN_PATH)
	if file != null:
		file.store_string(JSON.stringify(golden, "\t", true) + "\n")
		file.close()
		print("WROTE golden %s" % ProjectSettings.globalize_path(GOLDEN_PATH))

func _digest_differences(expected: Dictionary, actual: Dictionary) -> PackedStringArray:
	var out := PackedStringArray()
	for key: String in ["scalars", "screen_space", "borders", "grass_beds"]:
		if str(expected.get(key, "")) != str(actual[key]):
			out.append(key)
	var expected_regions: Variant = expected.get("regions", {})
	var actual_regions: Dictionary = actual.regions
	for id: String in actual_regions:
		if expected_regions is not Dictionary \
				or str((expected_regions as Dictionary).get(id, "")) != str(actual_regions[id]):
			out.append("region '%s'" % id)
	if expected_regions is Dictionary:
		for id: String in expected_regions:
			if not actual_regions.has(id):
				out.append("region '%s' missing" % id)
	return out

func _without_screen_space(value: Variant) -> Variant:
	if value is Dictionary:
		var out := {}
		for key: Variant in value:
			if key is String and (key == "screen_space" or key == "screen_space_effects"
					or SCREEN_SPACE_PROPERTIES.has(key)):
				continue
			out[key] = _without_screen_space(value[key])
		return out
	if value is Array:
		var out := []
		for item: Variant in value:
			out.append(_without_screen_space(item))
		return out
	return value

## Where two dumps first differ, for the failure message ("" when they agree).
func _first_difference(a: Variant, b: Variant, path := "") -> String:
	if typeof(a) != typeof(b):
		return " (first difference at %s)" % path
	if a is Dictionary:
		for key: Variant in a:
			if not (b as Dictionary).has(key):
				return " (first difference at %s/%s)" % [path, key]
			var inner := _first_difference(a[key], b[key], "%s/%s" % [path, key])
			if not inner.is_empty():
				return inner
		return "" if (a as Dictionary).size() == (b as Dictionary).size() \
			else " (first difference at %s)" % path
	if a is Array:
		if (a as Array).size() != (b as Array).size():
			return " (first difference at %s)" % path
		for index: int in (a as Array).size():
			var inner := _first_difference(a[index], b[index], "%s[%d]" % [path, index])
			if not inner.is_empty():
				return inner
		return ""
	return "" if var_to_bytes(a) == var_to_bytes(b) else " (first difference at %s)" % path

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		push_error("FAIL " + message)

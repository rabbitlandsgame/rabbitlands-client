extends SceneTree
## One tiny no-game-data preflight project; never import the full client here.
const Probe := preload("res://tools/release_graphics_probe.gd")
var _report: Dictionary = {"schema_version": 1, "status": "failed", "graphics": {}, "failures": []}
var _output := ""

func _init() -> void:
	_run.call_deferred()

func _path(value: String) -> String:
	return value.replace("\\", "/").simplify_path().trim_suffix("/")

func _same(left: String, right: String, platform: String) -> bool:
	return _path(left).to_lower() == _path(right).to_lower() if platform == "windows" else _path(left) == _path(right)

func _fail(message: String) -> void:
	_report.failures.append(message)

func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 1 or not arguments[0].is_absolute_path() \
		or FileAccess.get_file_as_bytes(arguments[0]).size() > 65536:
		_fail("one bounded absolute preflight job JSON path is required")
		_finish()
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
	if not parsed is Dictionary:
		_fail("preflight job must be a JSON object")
		_finish()
		return
	var job: Dictionary = parsed
	var platform := str(job.get("platform", ""))
	var project := _path(str(job.get("expected_project_root", "")))
	var user := _path(str(job.get("expected_user_directory", "")))
	var output := _path(str(job.get("report", "")))
	var method := str(job.get("expected_rendering_method", ""))
	var driver := str(job.get("expected_rendering_driver", ""))
	var actual_project := _path(ProjectSettings.globalize_path("res://"))
	var actual_user := _path(ProjectSettings.globalize_path("user://"))
	_report.merge({"project_root": actual_project, "user_directory": actual_user,
		"engine_executable": OS.get_executable_path(), "engine_version": Engine.get_version_info()})
	if int(job.get("schema_version", -1)) != 1 or platform not in ["windows", "linux"] \
		or not project.is_absolute_path() or not user.is_absolute_path() or not output.is_absolute_path() \
		or not _same(project, actual_project, platform) or not _same(user, actual_user, platform) \
		or _same(output, arguments[0], platform) or FileAccess.file_exists(output):
		_fail("fresh exact isolated project/user/report paths are required")
		_finish()
		return
	_output = output
	var observation := Probe.observe(platform, "release-preflight-buffer-probe.res")
	_report["graphics"] = observation
	# Preserve all actual fields on failure as well as success. In particular,
	# the numeric CPU classification must not disappear behind a generic gate.
	print("GRAPHICS_PREFLIGHT_OBSERVATION ", JSON.stringify(observation, "", true, true))
	for message: String in Probe.policy_errors(observation, platform, method, driver):
		_fail(message)
	_report["status"] = "pass" if _report.failures.is_empty() else "failed"
	_finish()

func _finish() -> void:
	if not _output.is_empty():
		var file := FileAccess.open(_output, FileAccess.WRITE)
		if file == null:
			_fail("cannot write preflight receipt")
			_report["status"] = "failed"
		else:
			file.store_string(JSON.stringify(_report, "", true, true) + "\n")
			file.flush()
	print("RELEASE_SOFTWARE_GRAPHICS_PREFLIGHT ", JSON.stringify(_report, "", true, true))
	if not _report.failures.is_empty():
		push_error("release graphics preflight: " + "; ".join(_report.failures))
	quit(0 if _report.status == "pass" else 1)

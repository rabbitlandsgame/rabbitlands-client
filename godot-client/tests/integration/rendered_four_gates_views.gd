extends SceneTree

## Captures the Four Gates client comparison set: one aerial plus one view for
## every supplied reference panel, rendered through the production WorldLoader
## with the manifest's own environment.

const SCREEN_SIZE := Vector2i(1600, 900)

var _artifact_directory := ""
var _failures := 0
var _loader: WorldLoader
var _camera: Camera3D

# id, camera position, look target, fov
const VIEWS := [
	["00-aerial", Vector3(690.0, 660.0, 860.0), Vector3(0.0, 20.0, 0.0), 48.0],
	["00b-aerial-north", Vector3(-470.0, 560.0, -700.0), Vector3(0.0, 40.0, -140.0), 48.0],
	["01-south-gate-exterior", Vector3(0.0, 33.6, 418.0), Vector3(0.0, 42.0, 352.0), 58.0],
	["02-gate-passage", Vector3(0.0, 33.6, 322.0), Vector3(0.0, 34.0, 470.0), 62.0],
	["03-causeway-approach", Vector3(0.0, 36.0, 520.0), Vector3(0.0, 48.0, 352.0), 55.0],
	["04-inner-gate-market", Vector3(0.0, 33.6, 246.0), Vector3(0.0, 42.0, 352.0), 60.0],
	["05-bridge-aerial", Vector3(196.0, 128.0, 566.0), Vector3(10.0, 20.0, 468.0), 50.0],
	["06-river-and-farms", Vector3(352.0, 214.0, 566.0), Vector3(60.0, 24.0, 292.0), 52.0],
	["07-central-plaza", Vector3(0.0, 96.0, 206.0), Vector3(0.0, 42.0, 0.0), 55.0],
	["08-ceremonial-arch", Vector3(0.0, 33.6, 176.0), Vector3(0.0, 46.0, 352.0), 60.0],
	["09-mountain-sanctuary", Vector3(0.0, 132.0, -450.0), Vector3(0.0, 86.0, -700.0), 50.0],
	["10-plaza-ground", Vector3(0.0, 33.4, 58.0), Vector3(0.0, 46.0, 0.0), 62.0],
	["11-curtain-wall", Vector3(196.0, 58.0, 196.0), Vector3(258.0, 34.0, 258.0), 58.0],
	["12-residential-street", Vector3(196.0, 33.4, 5.0), Vector3(336.0, 36.0, 5.0), 60.0],
	["13-waterfall-cliff", Vector3(492.0, 46.0, 232.0), Vector3(372.0, 6.0, 174.0), 52.0],
	["14-agricultural-quarter", Vector3(-30.0, 66.0, 176.0), Vector3(64.0, 31.0, 288.0), 58.0],
	["15-sanctuary-stair", Vector3(0.0, 46.0, -540.0), Vector3(0.0, 76.0, -690.0), 55.0],
	["16-market-square", Vector3(-150.0, 42.0, 108.0), Vector3(-196.0, 33.0, 60.0), 60.0],
	["17-plaza-eye-level", Vector3(30.0, 33.4, 54.0), Vector3(0.0, 50.0, 0.0), 65.0],
	["18-west-gate-inside", Vector3(-276.0, 33.6, 0.0), Vector3(-352.0, 42.0, 0.0), 58.0],
	["19-rim-portal-road", Vector3(0.0, 44.0, 636.0), Vector3(0.0, 62.0, 736.0), 55.0],
	["20-rooftops", Vector3(150.0, 74.0, 176.0), Vector3(0.0, 42.0, 20.0), 55.0],
]

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path(
			"res://test-artifacts/four-gates-views")
	DirAccess.make_dir_recursive_absolute(_artifact_directory)
	root.size = SCREEN_SIZE
	var scene: Node3D = (load("res://src/dev/world_validation.tscn") as PackedScene
		).instantiate() as Node3D
	root.add_child(scene)
	_loader = scene.get_node("WorldLoader") as WorldLoader
	var ready: Callable = func() -> bool: return _loader.world_root != null
	_expect(await _wait_for(ready, 240.0), "Four Gates world loads")
	if _loader.world_root == null:
		_finish()
		return
	_expect(WorldEnvironmentBinder.apply(_loader.manifest,
		scene.get_node("Environment") as WorldEnvironment,
		scene.get_node("Sun") as DirectionalLight3D),
		"manifest environment applied")
	(scene.get_node("UI") as CanvasLayer).visible = false
	_camera = scene.get_node("Camera") as Camera3D
	_camera.far = 4000.0
	_camera.near = 0.25

	var only: String = OS.get_environment("ELORIA_VIEWS")
	for view: Array in VIEWS:
		var id: String = str(view[0])
		if not only.is_empty() and not only.contains(id):
			continue
		_camera.fov = float(view[3])
		_camera.global_position = view[1] as Vector3
		_camera.look_at(view[2] as Vector3, Vector3.UP)
		await _capture(id + ".png")
	_finish()

func _wait_for(predicate: Callable, timeout_seconds: float) -> bool:
	var deadline: int = Time.get_ticks_msec() + roundi(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if bool(predicate.call()):
			return true
		await process_frame
	return bool(predicate.call())

func _capture(file_name: String) -> void:
	for _frame: int in range(5):
		await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	var start: int = Time.get_ticks_usec()
	RenderingServer.force_draw(false)
	var frame_usec: int = Time.get_ticks_usec() - start
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"saved %s (%.0f ms/frame software GL)" % [file_name, frame_usec / 1000.0])

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("four gates comparison views: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

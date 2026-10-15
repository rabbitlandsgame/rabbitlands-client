extends SceneTree
## Renders the click-to-walk cross at three points in its life so a reader
## can compare it against the legacy client's: a fresh cross with its corners
## pushed out, a mid-life cross most of the way collapsed, and a late one
## nearly at the centre and nearly faded. The marker's processing is taken
## over manually so each capture shows an exact age rather than whatever the
## frame clock landed on.

const SCREEN_SIZE := Vector2i(960, 540)

var _artifact_directory := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path("res://test-artifacts/four-gates")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var stage := Node3D.new()
	root.add_child(stage)
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_color = Color(0.23, 0.18, 0.12)
	ground_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var ground_mesh := PlaneMesh.new()
	ground_mesh.size = Vector2(20.0, 20.0)
	ground_mesh.material = ground_material
	var ground := MeshInstance3D.new()
	ground.mesh = ground_mesh
	stage.add_child(ground)
	var camera := Camera3D.new()
	stage.add_child(camera)
	camera.position = Vector3(0.0, 4.5, 2.6)
	camera.look_at(Vector3.ZERO)
	camera.current = true

	var marker := HighlightMarker3D.new()
	stage.add_child(marker)
	marker.configure(Vector3.ZERO, 1.0)
	marker.set_process(false)
	await _capture("walk-highlight-fresh.png")
	marker.call("_process", 0.2)
	await _capture("walk-highlight-mid.png")
	marker.call("_process", 0.15)
	await _capture("walk-highlight-late.png")

	print("walk highlight render: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _capture(file_name: String) -> void:
	await process_frame
	await process_frame
	var image_value: Variant = root.get_texture().get_image()
	_expect(image_value is Image, file_name + " captured")
	if not image_value is Image:
		return
	var image: Image = image_value as Image
	_expect(_greenish_pixels(image) > 200,
		file_name + " shows the green cross")
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		file_name + " saved")

## Pixels the additive green cross has visibly brightened: markedly more
## green than the brown ground anywhere near them.
func _greenish_pixels(image: Image) -> int:
	var count := 0
	for y in range(0, image.get_height(), 2):
		for x in range(0, image.get_width(), 2):
			var pixel: Color = image.get_pixel(x, y)
			if pixel.g > pixel.r + 0.15 and pixel.g > pixel.b + 0.15:
				count += 1
	return count

func _expect(condition: bool, label: String) -> void:
	if not condition:
		_failures += 1
		push_error(label)

extends SceneTree
## Captures the production login and character-creation layouts for visual QA.

const SCREEN_SIZE := Vector2i(1280, 720)
const CreationClassIcons := preload("res://src/ui/creation_class_icons.gd")

var failures := 0
var artifact_directory := ""


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error(message)


func _direct_texture(path: String) -> Texture2D:
	var image := Image.new()
	if image.load(ProjectSettings.globalize_path(path)) != OK or image.is_empty():
		return null
	return ImageTexture.create_from_image(image)


func _run() -> void:
	artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifact_directory.is_empty():
		artifact_directory = ProjectSettings.globalize_path(
			"res://test-artifacts/entry-screens")
	_expect(DirAccess.make_dir_recursive_absolute(artifact_directory) == OK,
		"entry-screen artifact directory is writable")
	root.size = SCREEN_SIZE
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	for unused: int in range(5):
		await process_frame
	# A clean worktree may not have editor-generated import sidecars yet. The
	# production loader is still exercised first; direct image decoding only
	# fills missing review art so the capture remains useful in that checkout.
	var background := main.get_node("%LoginBackground") as TextureRect
	if background.texture == null:
		background.texture = _direct_texture(
			"res://assets/ui/eloria_login_waygate_background.jpg")
	var creation_background := main.get_node("%CreationBackdrop") as TextureRect
	if creation_background.texture == null:
		creation_background.texture = _direct_texture(
			"res://assets/ui/eloria_character_creation_background.jpg")
	var class_sheet := _direct_texture(
		"res://assets/ui/eloria_creation_class_icons.png")
	if (main.get_node("%ClassChoice0") as Button).icon == null and class_sheet != null:
		CreationClassIcons.set_sheet_override(class_sheet)
		main.call("_configure_creation_classes")
	(main.get_node("%GameView") as Control).hide()
	(main.get_node("%CreationPanel") as Control).hide()
	(main.get_node("%LoginPanel") as Control).show()
	await _capture("login-screen.png")

	(main.get_node("%LoginPanel") as Control).hide()
	(main.get_node("%CreationPanel") as Control).show()
	# Face-region masks are generated import products and may be absent in the
	# lean review checkout. Keep the underlying authored face material for this
	# capture instead of letting a missing mask make the hero read as black.
	var models := main.get("models") as Dictionary
	for model_key: Variant in models:
		var model := models[model_key] as Dictionary
		if model.has("faceAppearance") and not ResourceLoader.exists(
				str((model.faceAppearance as Dictionary).get("mask", ""))):
			model.erase("faceAppearance")
	var sex := main.get_node("%CreateGender") as OptionButton
	if sex.item_count > 1:
		sex.select(1)
		sex.item_selected.emit(1)
	# Production deliberately starts from a random appearance. Keep visual QA
	# reproducible while still exercising the exact randomization path.
	var capture_rng := RandomNumberGenerator.new()
	capture_rng.seed = 1729
	main.call("_randomize_creation_appearance", capture_rng)
	main.set("preview_yaw", PI + 0.16)
	main.set("preview_pitch", 0.035)
	main.set("preview_distance", 1.95)
	main.call("_update_preview_camera")
	main.call("_refresh_creation_preview")
	for unused: int in range(12):
		await process_frame
	await _capture("character-creation-screen.png")
	main.call("_set_creation_class", 2)
	for unused: int in range(12):
		await process_frame
	await _capture("character-creation-arcanist.png")
	main.queue_free()
	await process_frame
	CreationClassIcons.set_sheet_override(null)
	NativeAnimationImporter.clear()
	print("rendered entry screens: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)


func _capture(file_name: String) -> void:
	for unused: int in range(4):
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		file_name + " renders at reference dimensions")
	if image.is_empty():
		return
	_expect(image.save_png(artifact_directory.path_join(file_name)) == OK,
		file_name + " is saved")

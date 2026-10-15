extends Node
const Release = preload("res://src/updates/release.gd")
const LaunchOptions = preload("res://src/updates/launch_options.gd")
var _root := ""
var _lock := ""
var _worker: Thread
var _owns_lock := false
var _game_pid := 0

func _ready() -> void:
	_root = OS.get_executable_path().get_base_dir()
	_lock = _root.path_join(".eloria-launcher-lock")
	# Atomic directory creation prevents two launchers installing simultaneously.
	if DirAccess.make_dir_absolute(_lock) != OK:
		var owner := Release.read_json(_lock.path_join("owner.json"))
		if owner.is_empty() and Time.get_unix_time_from_system() - FileAccess.get_modified_time(_lock) < 60:
			_fail("Rabbit Lands' launcher is starting. Try again in a moment.")
			return
		if OS.is_process_running(int(owner.get("pid", 0))) or OS.is_process_running(int(owner.get("game_pid", 0))):
			_fail("Rabbit Lands is already running, or its launcher is still starting.")
			return
		if Release.remove_tree(_lock) != OK or DirAccess.make_dir_absolute(_lock) != OK:
			_fail("The launcher lock cannot be opened.")
			return
	_owns_lock = true
	if Release.save_json(_lock.path_join("owner.json"), {"pid": OS.get_process_id()}) != OK:
		_fail("The game folder is not writable. Extract Rabbit Lands to a folder you own.")
		return
	var identity := Release.read_json("res://data/client_release.json")
	_worker = Thread.new()
	if _worker.start(func() -> String: return Release.install(_root, identity)) != OK:
		_fail("The update installer could not start.")
		return
	while _worker.is_alive():
		await get_tree().process_frame
	var error: String = _worker.wait_to_finish()
	_worker = null
	if error != "":
		_fail(error)
		return
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	var user_args := OS.get_cmdline_user_args()
	var defaults := PackedStringArray(Release.read_json(_root.path_join("launcher-defaults.json")).get("args", []))
	LaunchOptions.apply_environment(user_args)
	var args := LaunchOptions.game_arguments(user_args, defaults, _root,
		DisplayServer.get_name() == "headless")
	OS.set_environment("ELORIA_INSTALL_ROOT", _root)
	var pid := OS.create_process(_root.path_join("app/" + binary), args)
	if pid <= 0:
		_fail("Rabbit Lands could not start. The previous game is in .eloria-previous.")
		return
	_game_pid = pid
	Release.save_json(_lock.path_join("owner.json"), {"pid": OS.get_process_id(), "game_pid": pid})
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
	while OS.is_process_running(pid):
		await get_tree().create_timer(1.0).timeout
	_game_pid = 0
	_release_lock()
	get_tree().quit()

func _release_lock() -> void:
	if _owns_lock and (_game_pid == 0 or not OS.is_process_running(_game_pid)):
		Release.remove_tree(_lock)
		_owns_lock = false

func _fail(message: String) -> void:
	_release_lock()
	push_error(message)
	if DisplayServer.get_name() != "headless":
		OS.alert(message, "Rabbit Lands update")
	get_tree().quit(1)

func _exit_tree() -> void:
	if _worker != null:
		_worker.wait_to_finish()
	_release_lock()

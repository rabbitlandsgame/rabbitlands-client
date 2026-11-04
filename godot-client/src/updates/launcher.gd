extends Node
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")
const Download = preload("res://src/updates/package_download.gd")
const Bootstrap = preload("res://src/updates/bootstrap.gd")
const Transport = preload("res://src/updates/update_transport.gd")
const Uninstall = preload("res://src/updates/uninstall.gd")
const LaunchOptions = preload("res://src/updates/launch_options.gd")
# Give the updated game time to load before its old copy is removed.
const BACKUP_CLEANUP_DELAY_MSEC := 60000
# A game that exits with LaunchOptions.RELAUNCH_EXIT_CODE (to restart into the
# renderer its settings now ask for) is started again this many times.
const MAX_RELAUNCHES := 1
var _root := ""
var _guard := Bootstrap.new()
var _transport
var _game_pid := 0
var _backup_cleanup: Thread
var _backup_cleanup_checked := false
var _backup_cleanup_stop := false
var _backup_cleanup_files := 0

func _ready() -> void:
	_transport = _new_transport()
	add_child(_transport)
	var args := OS.get_cmdline_user_args()
	if args.size() == 3 and args[0] == "--handoff":
		await _handoff(args[1], args[2])
		return
	_root = Bootstrap.default_root()
	var root_index := args.find("--root")
	if root_index >= 0:
		if root_index + 1 >= args.size():
			_fail("The installation folder argument is missing.")
			return
		_root = args[root_index + 1].simplify_path()
		args.remove_at(root_index + 1)
		args.remove_at(root_index)
	if OS.get_executable_path().get_file().contains("-uninstall") or "--uninstall" in args:
		await Uninstall.run(self, _root, "--confirm" in args)
		return
	var wait_index := args.find("--wait-for-pid")
	var waiting := wait_index >= 0
	if waiting:
		if wait_index + 1 >= args.size() or not args[wait_index + 1].is_valid_int() or int(args[wait_index + 1]) <= 0:
			_fail("The game restart request is invalid.")
			return
		var pid := int(args[wait_index + 1])
		args.remove_at(wait_index + 1)
		args.remove_at(wait_index)
		for attempt in 120:
			if not Release.lease_process_running(pid):
				break
			_progress("Waiting for Rabbit Lands to close", 0, 1)
			await get_tree().create_timer(0.5).timeout
		if Release.lease_process_running(pid):
			_fail("Rabbit Lands is still running. Close it and run the updater again.")
			return
	var error := Bootstrap.root_error(_root, true)
	if error == "":
		error = _guard.acquire(_root)
		if waiting:
			# The previous launcher releases its lock after noticing the old game
			# has exited. Never install while either process still owns the folder.
			for attempt in 120:
				if error == "":
					break
				await get_tree().create_timer(0.5).timeout
				error = _guard.acquire(_root)
	if error != "":
		_fail(error)
		return
	var identity := Bootstrap.trust()
	var installed := Release.read_json(_root.path_join("app/client-release.json"))
	var own := OS.get_executable_path().simplify_path()
	var installed_helper := _root.path_join(Bootstrap.helper_name("updater", identity))
	var managed_launcher := own.to_lower() == installed_helper.to_lower() if OS.get_name() == "Windows" else own == installed_helper
	# With the lock held, drop helper copies left by earlier handovers.
	var pruned: Variant = await _transport.worker(func() -> Array: return Bootstrap.prune_cache(_root, identity, managed_launcher))
	if pruned is Array:
		for line: Variant in pruned:
			print(line)
	# Downloaded, checksum-named updaters are explicit repair/install entry points.
	# Older shortcuts to the installed canonical helper still open the game first.
	var launch_only: bool = "--launch-only" in args or (managed_launcher and installed.get("release_build", false) == true and not "--install-update" in args and not "--update-only" in args)
	if launch_only:
		if "--launch-only" in args:
			args.remove_at(args.find("--launch-only"))
		error = await _transport.worker(func() -> String: return Release.recover(_root))
		if error != "":
			_fail(error)
			return
		await _launch_game(identity, args)
		return
	Release.save_json(_root.path_join(".rabbitlands-install.json"), {"schema": 1, "repository": identity.repository, "platform": identity.platform})
	error = await _transport.worker(func() -> String:
		return Release.recover(_root) if "--install-manifest" in args else Release.install(_root, identity))
	if error != "":
		_fail(error)
		return
	_progress("Checking for game and updater updates", 0, 1)
	var url := "https://github.com/%s/releases/latest/download/RabbitLands-%s.json" % [identity.repository, identity.platform]
	var manifest_index := args.find("--install-manifest")
	var fetched: Dictionary
	if manifest_index >= 0:
		var file := FileAccess.open(args[manifest_index + 1], FileAccess.READ) if manifest_index + 1 < args.size() else null
		if file == null or file.get_length() > Release.MAX_MANIFEST_BYTES:
			_fail("The installer's signed release information is missing or too large.")
			return
		fetched = {"body": file.get_buffer(file.get_length())}
		file.close()
	else:
		fetched = await _transport.fetch(url)
	if not fetched.has("error"):
		var parsed: Variant = JSON.parse_string(fetched.body.get_string_from_utf8())
		var envelope: Dictionary = parsed if parsed is Dictionary else {}
		var release := Bootstrap.verify(envelope, identity)
		if release.has("error"):
			_fail(release.error)
			return
		if manifest_index >= 0:
			# The shell installer can exit during updater self-replacement. Keep
			# the verified manifest in the durable cache before handing over.
			var cache := Release.cache_for(_root)
			var saved := cache.path_join("installer-manifest.json")
			if Release.is_link(cache) or Release.is_link(saved) or DirAccess.make_dir_recursive_absolute(cache) != OK or Release.save_json(saved, envelope) != OK:
				_fail("The installer's signed release information could not be retained.")
				return
			args[manifest_index + 1] = saved
		var matched: Variant = await _transport.worker(func() -> bool: return Bootstrap.helpers_match(_root, release, identity))
		if matched != true:
			_progress("Updating the updater", 0, 1)
			error = await Bootstrap.prepare_helpers(_root, release, _transport.fetch, _transport.worker)
			if error == "":
				error = Bootstrap.start_handoff(_root, envelope, args)
			if error != "":
				_fail(error)
				return
			_guard.release_lock()
			get_tree().quit()
			return
		release = Release.verify_manifest(envelope, identity)
		if release.has("error") or release.get("schema") != 2:
			_fail(str(release.get("error", "The game package format is unsupported.")))
			return
		var prepared_plan: Dictionary = {}
		error = await Download.prepare(_root, release, _transport.fetch, _transport.worker, _progress, Callable(), prepared_plan)
		if error == "":
			error = await _transport.worker(func() -> String: return Packages.install(_root, release, identity, _progress, prepared_plan.get("checked")))
		if error != "":
			_fail(error)
			return
		var defaults := _root.path_join("launcher-defaults.json")
		var launch_args: Variant = release.get("launch_args", [])
		if not FileAccess.file_exists(defaults) and launch_args is Array:
			if Release.save_json(defaults, {"args": launch_args}) != OK:
				_fail("The game's launch defaults could not be saved.")
				return
	elif not FileAccess.file_exists(_root.path_join("app/client-release.json")) or "--update-only" in args:
		_fail(fetched.error)
		return
	if "--update-only" in args:
		_guard.release_lock()
		get_tree().quit()
		return
	await _launch_game(identity, args)

func _launch_game(identity: Dictionary, args: PackedStringArray) -> void:
	if "--install-update" in args:
		args.remove_at(args.find("--install-update"))
	var manifest_index := args.find("--install-manifest")
	if manifest_index >= 0:
		if manifest_index + 1 >= args.size():
			_fail("The installer's signed release information is missing.")
			return
		args.remove_at(manifest_index + 1)
		args.remove_at(manifest_index)
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	var defaults := PackedStringArray(Release.read_json(_root.path_join("launcher-defaults.json")).get("args", []))
	LaunchOptions.apply_environment(args)
	var game_args := LaunchOptions.game_arguments(args, defaults, _root, _game_headless())
	var resume_index := args.find("--resume-client")
	if resume_index >= 0:
		var context: Variant = JSON.parse_string(Marshalls.base64_to_utf8(args[resume_index + 1])) if resume_index + 1 < args.size() else null
		game_args = LaunchOptions.resume_arguments(context) if context is Dictionary else PackedStringArray()
		if game_args.is_empty():
			_fail("The saved game launch mode is invalid. Start the game from its usual shortcut.")
			return
		LaunchOptions.apply_environment(PackedStringArray(context.user))
	OS.set_environment("ELORIA_INSTALL_ROOT", _root)
	# Announce the relaunch handshake: a game that must restart into another
	# renderer exits with RELAUNCH_EXIT_CODE instead of restarting itself, so
	# this launcher keeps the installation lock across the restart.
	OS.set_environment(LaunchOptions.LAUNCHER_FEATURES_ENV,
		LaunchOptions.launcher_features(OS.get_environment(LaunchOptions.LAUNCHER_FEATURES_ENV)))
	var relaunches := 0
	while true:
		var split := game_args.find("--")
		OS.set_environment(LaunchOptions.CONTEXT_ENV, LaunchOptions.encode_context(
			LaunchOptions.resume_context(game_args, game_args.slice(split + 1))))
		# A start of the renderer Automatic is trialling (none for a headless or
		# compatibility launch); an early error exit gives it up (below).
		var trial := LaunchOptions.trial_renderer(game_args)
		_game_pid = _start_process(_root.path_join("app/" + binary), game_args)
		if _game_pid <= 0:
			# A relaunch can follow a game that started the backup removal. Stop it
			# before _fail gives the lock up (and waits on its alert), so no other
			# updater installs while this one still deletes backup files.
			_finish_backup_cleanup()
			_fail("Rabbit Lands could not start. Run its installer to repair this installation.")
			return
		if DisplayServer.get_name() != "headless":
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
		var started := Time.get_ticks_msec()
		var lease := Release.cache_for(_root).path_join("running-%d.json" % _game_pid)
		while OS.is_process_running(_game_pid):
			# The game's running lease shows the installed build started. This
			# launcher keeps the lock until the game exits, so no update can begin.
			if not _backup_cleanup_checked and Time.get_ticks_msec() - started >= _backup_cleanup_delay_msec() and FileAccess.file_exists(lease):
				_start_backup_cleanup()
			await get_tree().create_timer(1.0).timeout
		var exit_code := OS.get_process_exit_code(_game_pid)
		if LaunchOptions.record_failed_start(trial, exit_code, Time.get_ticks_msec() - started):
			print("Rabbit Lands stopped with exit code %d while trying the %s renderer; Automatic uses the default renderer from now on." % [exit_code, trial])
		if exit_code != LaunchOptions.RELAUNCH_EXIT_CODE:
			break
		if relaunches >= MAX_RELAUNCHES:
			print("Rabbit Lands asked to restart again after a renderer restart; it is not started a second time.")
			break
		# The game asked to start again with the renderer its settings now ask
		# for. The lock stays held; a running backup removal carries on, and
		# one not started yet waits for the new game's own lease.
		relaunches += 1
		game_args = LaunchOptions.relaunch_arguments(game_args)
		var renderer := LaunchOptions.engine_renderer(game_args)
		print("Rabbit Lands asked to restart with another renderer; starting it again with %s."
			% (renderer if renderer != "" else "the default renderer"))
	_finish_backup_cleanup()
	_game_pid = 0
	_guard.release_lock()
	get_tree().quit()

func _start_backup_cleanup() -> void:
	_backup_cleanup_checked = true
	var backup := _root.path_join(".eloria-previous")
	if not DirAccess.dir_exists_absolute(backup):
		return
	print("Removing the previous installation backup %s; the updated game has started." % backup)
	var root := _root
	_backup_cleanup = Thread.new()
	if _backup_cleanup.start(func() -> Error: return Release.remove_backup(root, _backup_cleanup_checkpoint), Thread.PRIORITY_LOW) != OK:
		_backup_cleanup = null

func _backup_cleanup_checkpoint() -> bool:
	# Runs on the cleanup thread before each file. Short pauses keep this
	# one-off burst of deletions from competing with the game's disk reads.
	if _backup_cleanup_stop:
		return true
	_backup_cleanup_files += 1
	if _backup_cleanup_files % 32 == 0:
		OS.delay_msec(10)
	return false

func _finish_backup_cleanup() -> void:
	if _backup_cleanup == null:
		return
	# Stop at the next file so a waiting updater can take the lock. Whatever
	# remains is removed after the next confirmed game start.
	_backup_cleanup_stop = true
	var error: Variant = _backup_cleanup.wait_to_finish()
	_backup_cleanup = null
	if error == OK:
		print("Removed the previous installation backup (%d files)." % _backup_cleanup_files)
	else:
		print("Paused removing the previous installation backup after %d files (%s); it continues after the next game start." % [_backup_cleanup_files, error_string(int(error))])

func _handoff(root: String, manifest: String) -> void:
	var error := Bootstrap.root_error(root)
	var request := Release.read_json(manifest)
	var release := Bootstrap.verify(request.get("envelope", {}), Bootstrap.trust())
	if error != "" or release.has("error") or manifest != Release.cache_for(root).path_join("bootstrap-manifest.json"):
		_fail(error if error != "" else "The updater handover failed verification.")
		return
	for attempt in 120:
		error = _guard.acquire(root)
		if error == "":
			break
		await get_tree().create_timer(0.5).timeout
	if error == "":
		for attempt in 120:
			error = Bootstrap.promote_helpers(root, release, Bootstrap.trust())
			if error == "" or not "still running" in error:
				break
			await get_tree().create_timer(0.5).timeout
	if error == "":
		_guard.release_lock()
		var next_args := PackedStringArray(["--", "--root", root])
		next_args.append_array(PackedStringArray(request.get("args", [])))
		if OS.create_process(root.path_join(Bootstrap.helper_name("updater", Bootstrap.trust())), next_args) <= 0:
			error = "The updated updater could not start. Run it again from the game folder."
	if error != "":
		_fail(error)
	else:
		get_tree().quit()

func _new_transport() -> Node:
	return Transport.new()

# Whether the game starts without a display (as this launcher does). Test
# fixtures override this and `_start_process` to exercise renderer arguments.
func _game_headless() -> bool:
	return DisplayServer.get_name() == "headless"

func _start_process(path: String, game_args: PackedStringArray) -> int:
	return OS.create_process(path, game_args)

func _backup_cleanup_delay_msec() -> int:
	return BACKUP_CLEANUP_DELAY_MSEC

func _progress(phase: String, completed: int, total: int, detail := "") -> void:
	var text := phase + (": " + detail if detail != "" else "")
	if total > 1:
		text += " (%d%%)" % int(100.0 * completed / total)
	get_node("Status").set_deferred("text", text)
	print("RL_PROGRESS|%d|%s" % [int(100.0 * completed / maxi(1, total)), text])

func _fail(message: String) -> void:
	_guard.release_lock()
	push_error(message)
	if DisplayServer.get_name() != "headless":
		OS.alert(message, "Rabbit Lands update")
	get_tree().quit(1)

func _exit_tree() -> void:
	_finish_backup_cleanup()
	if _game_pid == 0:
		_guard.release_lock()

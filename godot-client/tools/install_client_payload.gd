extends Node
## The online setup runs this embedded helper after downloading the signed parts.
const Release = preload("res://src/updates/release.gd")
var _lock := ""
var _owns_lock := false
var _lock_owner: FileAccess
var _last_phase := ""
var _last_progress_ms := -1000

func _progress(phase: String, completed: int, total: int, detail := "") -> void:
	var now := Time.get_ticks_msec()
	if phase == _last_phase and completed < total and now - _last_progress_ms < 250:
		return
	_last_phase = phase
	_last_progress_ms = now
	var percent := clampi(int(100.0 * completed / maxi(total, 1)), 0, 100)
	var message := phase
	if detail != "":
		message += ": " + detail
	print("RL_PROGRESS|%d|%s" % [percent, message])

func _release_lock() -> void:
	if _lock_owner != null:
		_lock_owner.close()
		_lock_owner = null
	if _owns_lock:
		Release.remove_tree(_lock)
		_owns_lock = false

func _lock_root(root: String) -> String:
	_lock = root.path_join(".eloria-launcher-lock")
	var candidate := root.path_join(".eloria-setup-lock-%d-%d" % [OS.get_process_id(), Time.get_ticks_usec()])
	if DirAccess.make_dir_absolute(candidate) != OK:
		return "The installation lock cannot be created."
	if Release.save_json(candidate.path_join("owner.json"), {"pid": OS.get_process_id()}) != OK:
		Release.remove_tree(candidate)
		return "The installation folder is not writable."
	# Publish a nonempty directory atomically; an existing owner's lock wins.
	if DirAccess.rename_absolute(candidate, _lock) != OK:
		var owner_path := _lock.path_join("owner.json")
		var owner := Release.read_json(owner_path)
		var modified := FileAccess.get_modified_time(owner_path)
		var guarded := OS.get_name() == "Windows" and bool(owner.get("guarded", false))
		if Release.is_link(_lock) or owner.is_empty() or modified == 0 or (not guarded and Time.get_unix_time_from_system() - modified < 60) or Release.lease_process_running(int(owner.get("pid", 0))) or Release.lease_process_running(int(owner.get("game_pid", 0))):
			Release.remove_tree(candidate)
			return "Close Rabbit Lands and any other installer before continuing."
		if Release.remove_tree(_lock) != OK or DirAccess.rename_absolute(candidate, _lock) != OK:
			Release.remove_tree(candidate)
			return "Another Rabbit Lands installer or launcher is still working. Wait for it to finish, then run setup again."
	_owns_lock = true
	# Windows denies deletion of an open file. Keep this handle until all cache
	# and game writes finish, even if setup closes or a PID cannot be inspected.
	_lock_owner = FileAccess.open(_lock.path_join("owner.json"), FileAccess.READ_WRITE)
	if _lock_owner == null:
		return "The installation lock cannot be held."
	# Publish this marker only after the handle is held. An abandoned guarded
	# lock can be reclaimed immediately once Windows releases the dead process.
	_lock_owner.store_string(JSON.stringify({"pid": OS.get_process_id(), "guarded": true}))
	_lock_owner.flush()
	if _lock_owner.get_error() != OK:
		return "The installation lock cannot be recorded."
	return ""

func _ready() -> void:
	var error := _install()
	_release_lock()
	if error != "":
		print("RL_ERROR|" + error)
		push_error(error)
		get_tree().quit(1)
	else:
		_progress("Game files installed", 1, 1)
		print("Rabbit Lands installation verified.")
		get_tree().quit(0)

func _exit_tree() -> void:
	_release_lock()

func _install() -> String:
	var args := OS.get_cmdline_user_args()
	if args.size() != 4 or args[0] != "--root" or args[2] != "--parts":
		return "The installer arguments are invalid."
	var root := args[1].simplify_path()
	var parts := args[3].simplify_path()
	if not root.is_absolute_path() or not parts.is_absolute_path() or Release.is_link(root):
		return "Choose a writable installation folder."
	var identity := Release.read_json("res://data/client_release.json")
	var envelope := Release.read_json("res://data/install_manifest.json")
	var release := Release.verify_manifest(envelope, identity, str(identity.get("commit", "")))
	if release.has("error"):
		return release.error
	if DirAccess.make_dir_recursive_absolute(root) != OK:
		return "The installation folder cannot be created."
	var lock_error := _lock_root(root)
	if lock_error != "":
		return lock_error
	var cache := Release.cache_for(root)
	var existing := DirAccess.open(cache)
	if existing != null:
		for name: String in existing.get_files():
			if name.begins_with("running-") and name.ends_with(".json"):
				if Release.lease_process_running(int(Release.read_json(cache.path_join(name)).get("pid", 0))):
					return "Close Rabbit Lands before installing."
	# Verify every source before replacing any cached update or installed data.
	_progress("Verifying downloads", 0, release.parts.size())
	for index in release.parts.size():
		var part: Dictionary = release.parts[index]
		if not Release.check_file(parts.path_join(str(part.url).get_file()), int(part.size), part.sha256):
			return "A downloaded game file failed verification. Run setup again."
		_progress("Verifying downloads", index + 1, release.parts.size())
	if DirAccess.make_dir_recursive_absolute(cache) != OK:
		return "The download cache cannot be created."
	for name: String in ["release.zip", "release.zip.tmp", "pending.json"]:
		var path := cache.path_join(name)
		if FileAccess.file_exists(path) and DirAccess.remove_absolute(path) != OK:
			return "Another Rabbit Lands installer or updater may still be unpacking the game. Wait for it to finish, then run setup again. The download cache could not be opened."
	_progress("Copying downloads", 0, release.parts.size())
	for index in release.parts.size():
		var source := parts.path_join(str(release.parts[index].url).get_file())
		if DirAccess.copy_absolute(source, cache.path_join("part-%04d" % index)) != OK:
			return "A download cannot be copied. Check free disk space."
		_progress("Copying downloads", index + 1, release.parts.size())
	var error := Release.assemble(cache, release, _progress)
	if error != "":
		return error
	if Release.save_json(cache.path_join("pending.json"), envelope) != OK:
		return "The verified installation cannot be recorded."
	for name: String in Release.ROOTS:
		var destination := root.path_join(name)
		if Release.is_link(destination):
			return "The game data folders cannot be links."
		if not DirAccess.dir_exists_absolute(destination) and DirAccess.make_dir_absolute(destination) != OK:
			return "The game data folders cannot be created."
	# Setup also repairs a damaged installation of the same commit.
	return Release.install(root, identity, true, _progress)

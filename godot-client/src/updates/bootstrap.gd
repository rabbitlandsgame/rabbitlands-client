extends RefCounted
const Release = preload("res://src/updates/release.gd")
var _lock := ""
var _guard: FileAccess

static func trust() -> Dictionary:
	return Release.read_json("res://data/client_release.json")

static func verify(envelope: Dictionary, identity: Dictionary) -> Dictionary:
	# Keep this small bootstrap contract stable even when the game package
	# protocol changes. An older updater can verify and install its successor
	# before it attempts to understand that successor's package inventory.
	var release := Release.verify_envelope(envelope, identity)
	if release.has("error"):
		return release
	if release.get("bootstrap_schema") != 1 or release.get("repository") != identity.get("repository") or release.get("platform") != identity.get("platform") or not Release.valid_commit(release.get("commit")) or not release.get("version") is String or "/" in release.version or "\\" in release.version:
		return {"error": "The updater release identity is invalid."}
	var base := "https://github.com/%s/releases/download/client-%s/" % [identity.repository, release.commit]
	var extension := "exe" if identity.platform == "windows" else "x86_64"
	for kind: String in ["updater", "uninstall"]:
		var row: Variant = release.get(kind)
		if not row is Dictionary or (row.get("url") != base + release.version + "-" + kind + "." + extension and not Release.shared_download(row, identity.repository, kind, extension)) or not Release.valid_hash(row.get("sha256")) or not Release.positive_integer(row.get("size"), 512 * 1024 * 1024):
			return {"error": "The updater download is invalid."}
	return release

static func default_root() -> String:
	var beside := OS.get_executable_path().get_base_dir()
	if FileAccess.file_exists(beside.path_join("app/client-release.json")):
		return beside
	if OS.get_name() == "Windows":
		return OS.get_environment("LOCALAPPDATA").path_join("Programs/RabbitLands")
	return OS.get_environment("HOME").path_join("Games/RabbitLands")

static func root_error(root: String, fresh := false) -> String:
	if not root.is_absolute_path() or root != root.simplify_path() or root.get_base_dir() == root or Release.is_link(root) or root in [OS.get_environment("HOME"), OS.get_environment("USERPROFILE")]:
		return "Choose a separate Rabbit Lands installation folder."
	if Release.is_link(root.path_join("app")):
		return "The installed game folder must not be a link."
	var descriptor := Release.read_json(root.path_join("app/client-release.json"))
	if not descriptor.is_empty():
		if descriptor.get("repository") != trust().get("repository") or descriptor.get("platform") != trust().get("platform") or Release.update_owner(descriptor) != "github" or descriptor.get("public_key") != trust().get("public_key"):
			return "This folder belongs to a different distribution or signing key. Use its original installer."
		return ""
	var marker := Release.read_json(root.path_join(".rabbitlands-install.json"))
	if marker.get("repository") == trust().get("repository"):
		return ""
	if fresh:
		var directory := DirAccess.open(root)
		if directory == null or (directory.get_files().is_empty() and directory.get_directories().is_empty()):
			return ""
	return "This is not a recognized Rabbit Lands installation folder."

func acquire(root: String) -> String:
	if DirAccess.make_dir_recursive_absolute(root) != OK:
		return "The game folder is not writable."
	_lock = root.path_join(".eloria-launcher-lock")
	if DirAccess.make_dir_absolute(_lock) != OK:
		var owner := Release.read_json(_lock.path_join("owner.json"))
		var guarded := OS.get_name() == "Windows" and bool(owner.get("guarded", false))
		if Release.is_link(_lock) or (not guarded and Time.get_unix_time_from_system() - FileAccess.get_modified_time(_lock) < 60) or Release.lease_process_running(int(owner.get("pid", 0))) or Release.lease_process_running(int(owner.get("game_pid", 0))):
			return "Close Rabbit Lands and its other updater or installer first."
		# A live Windows owner keeps this directory undeletable via its handle.
		if Release.remove_tree(_lock) != OK or DirAccess.make_dir_absolute(_lock) != OK:
			return "Another Rabbit Lands process is using this installation."
	if Release.save_json(_lock.path_join("owner.json"), {"pid": OS.get_process_id()}) != OK:
		return "The installation lock cannot be recorded."
	_guard = FileAccess.open(_lock.path_join("owner.json"), FileAccess.READ_WRITE)
	if _guard == null:
		return "The installation lock cannot be held."
	_guard.store_string(JSON.stringify({"pid": OS.get_process_id(), "guarded": true}))
	_guard.flush()
	if _guard.get_error() != OK:
		return "The installation lock cannot be held."
	var directory := DirAccess.open(Release.cache_for(root))
	if directory != null:
		for name: String in directory.get_files():
			if name.begins_with("running-") and name.ends_with(".json") and Release.lease_process_running(int(Release.read_json(directory.get_current_dir().path_join(name)).get("pid", 0))):
				release_lock()
				return "Close the running Rabbit Lands game first."
	return ""

func release_lock() -> void:
	if _guard != null:
		_guard.close()
		_guard = null
		Release.remove_tree(_lock)

static func helper_name(kind: String, identity: Dictionary) -> String:
	return "RabbitLands-" + kind + (".exe" if identity.platform == "windows" else ".x86_64")

static func staged_helper(root: String, row: Dictionary) -> String:
	return Release.cache_for(root).path_join("bootstrap/" + row.sha256)

static func prepare_helpers(root: String, release: Dictionary, fetch: Callable, worker: Callable) -> String:
	var identity := trust()
	var directory := Release.cache_for(root).path_join("bootstrap")
	if Release.is_link(Release.cache_for(root)) or Release.is_link(directory) or DirAccess.make_dir_recursive_absolute(directory) != OK:
		return "The updater download cache is not writable."
	for kind: String in ["updater", "uninstall"]:
		var row: Dictionary = release[kind]
		var target := staged_helper(root, row)
		if Release.is_link(target) or Release.is_link(target + ".tmp"):
			return "The updater cache files must not be links."
		var valid: Variant = await worker.call(func() -> bool: return Release.check_file(target, int(row.size), row.sha256))
		if valid == true:
			continue
		var installed := root.path_join(helper_name(kind, identity))
		var own := OS.get_executable_path()
		for candidate: String in [installed, own]:
			valid = await worker.call(func() -> bool: return not Release.is_link(candidate) and Release.check_file(candidate, int(row.size), row.sha256))
			if valid == true:
				if DirAccess.copy_absolute(candidate, target) != OK:
					return "The verified updater could not be staged."
				break
		if valid != true:
			var fetched: Dictionary = await fetch.call(row.url, target + ".tmp", int(row.size))
			if fetched.has("error"):
				return fetched.error
			valid = await worker.call(func() -> bool: return Release.check_file(target + ".tmp", int(row.size), row.sha256))
			if valid != true or DirAccess.rename_absolute(target + ".tmp", target) != OK:
				return "The downloaded updater failed signature-bound checksum verification."
	return ""

static func helpers_match(root: String, release: Dictionary, identity: Dictionary) -> bool:
	for kind: String in ["updater", "uninstall"]:
		var row: Dictionary = release[kind]
		if Release.is_link(root.path_join(helper_name(kind, identity))) or not Release.check_file(root.path_join(helper_name(kind, identity)), int(row.size), row.sha256):
			return false
	return true

static func start_handoff(root: String, envelope: Dictionary, args := PackedStringArray()) -> String:
	var cache := Release.cache_for(root)
	var manifest := cache.path_join("bootstrap-manifest.json")
	if Release.save_json(manifest, {"envelope": envelope, "args": Array(args)}) != OK:
		return "The updater handover could not be recorded."
	var extension := ".exe" if OS.get_name() == "Windows" else ".x86_64"
	var worker := cache.path_join("handoff-%d%s" % [OS.get_process_id(), extension])
	if DirAccess.copy_absolute(OS.get_executable_path(), worker) != OK:
		return "The updater handover helper could not be created."
	if OS.get_name() == "Linux":
		FileAccess.set_unix_permissions(worker, 448)
	var executable := worker
	var arguments := PackedStringArray(["--headless", "--", "--handoff", root, manifest])
	if OS.get_name() == "Linux":
		# The shell installer deletes its temporary folder when this updater
		# exits. Start the worker from a durable folder before Godot saves its
		# initial working directory, which it restores during shutdown.
		# Pass paths and arguments positionally so shell characters stay literal.
		executable = "/bin/sh"
		arguments = PackedStringArray(["-c", 'cd "$1" || exit 1; shift; exec "$@"',
			"rabbitlands-handoff", root, worker]) + arguments
	if OS.create_process(executable, arguments) <= 0:
		return "The updater handover helper could not start."
	return ""

static func promote_helpers(root: String, release: Dictionary, identity: Dictionary) -> String:
	# Never replace a running Windows executable in place. This runs in a copy
	# outside the installation, after the original launcher relinquishes its lock.
	var backup := root.path_join(".rabbitlands-bootstrap-previous")
	if Release.is_link(backup) or DirAccess.make_dir_recursive_absolute(backup) != OK:
		return "The updater backup folder cannot be created."
	for kind: String in ["updater", "uninstall"]:
		var row: Dictionary = release[kind]
		var source := staged_helper(root, row)
		var name := helper_name(kind, identity)
		var target := root.path_join(name)
		if not Release.is_link(target) and Release.check_file(target, int(row.size), row.sha256):
			continue
		if Release.is_link(target) or Release.is_link(target + ".next") or Release.is_link(source) or not Release.check_file(source, int(row.size), row.sha256):
			return "The staged updater failed verification."
		if DirAccess.copy_absolute(source, target + ".next") != OK or not Release.check_file(target + ".next", int(row.size), row.sha256):
			return "The replacement updater could not be written."
		var previous := backup.path_join(name)
		if FileAccess.file_exists(previous) and DirAccess.remove_absolute(previous) != OK:
			return "The updater backup is still in use."
		if FileAccess.file_exists(target) and DirAccess.rename_absolute(target, previous) != OK:
			return "The old updater is still running. Try again after closing it."
		if DirAccess.rename_absolute(target + ".next", target) != OK:
			DirAccess.rename_absolute(previous, target)
			return "The replacement updater could not be installed."
		if identity.platform == "linux":
			FileAccess.set_unix_permissions(target, 493)
	return ""

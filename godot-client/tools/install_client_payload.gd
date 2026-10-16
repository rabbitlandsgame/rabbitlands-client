extends Node
## The online setup runs this embedded helper after downloading the signed parts.
const Release = preload("res://src/updates/release.gd")
var _lock := ""
var _owns_lock := false

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
		if Release.is_link(_lock) or owner.is_empty() or modified == 0 or Time.get_unix_time_from_system() - modified < 60 or OS.is_process_running(int(owner.get("pid", 0))) or OS.is_process_running(int(owner.get("game_pid", 0))):
			Release.remove_tree(candidate)
			return "Close Rabbit Lands and any other installer before continuing."
		if Release.remove_tree(_lock) != OK or DirAccess.rename_absolute(candidate, _lock) != OK:
			Release.remove_tree(candidate)
			return "The installation lock cannot be opened."
	_owns_lock = true
	return ""

func _ready() -> void:
	var error := _install()
	if _owns_lock:
		Release.remove_tree(_lock)
	if error != "":
		push_error(error)
		get_tree().quit(1)
	else:
		print("Rabbit Lands installation verified.")
		get_tree().quit(0)

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
				if OS.is_process_running(int(Release.read_json(cache.path_join(name)).get("pid", 0))):
					return "Close Rabbit Lands before installing."
	# Verify every source before replacing any cached update or installed data.
	for part: Dictionary in release.parts:
		if not Release.check_file(parts.path_join(str(part.url).get_file()), int(part.size), part.sha256):
			return "A downloaded game file failed verification. Run setup again."
	if DirAccess.make_dir_recursive_absolute(cache) != OK:
		return "The download cache cannot be created."
	for name: String in ["pending.json", "release.zip", "release.zip.tmp"]:
		var path := cache.path_join(name)
		if FileAccess.file_exists(path) and DirAccess.remove_absolute(path) != OK:
			return "The download cache is busy."
	for index in release.parts.size():
		var source := parts.path_join(str(release.parts[index].url).get_file())
		if DirAccess.copy_absolute(source, cache.path_join("part-%04d" % index)) != OK:
			return "A download cannot be copied. Check free disk space."
	var error := Release.assemble(cache, release)
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
	return Release.install(root, identity, true)

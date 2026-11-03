extends RefCounted
## Independent ZIP packages. Only signed paths are reused, downloaded or installed.
const Release = preload("res://src/updates/release.gd")
# Room kept free beyond the changed files while they are staged.
const FREE_SPACE_MARGIN := 64 * 1024 * 1024
# File times have one-second (FAT: two-second) resolution. A matching file
# whose time is this close to the scan is hashed again at the commit point.
const RACY_SECONDS := 3

# This receipt stays in memory for one locked download/install transaction.
# Never persist it or use it to skip hashing a file it has not hashed itself.
class CheckedPlan extends RefCounted:
	var needed: Array = []
	var unchanged: Dictionary = {}
	# package id -> indices of members that are missing, damaged, behind a
	# link or spelled in another case. Only these members are unpacked.
	var changed: Dictionary = {}
	# path -> [size, mtime, sha256] of members whose installed bytes matched.
	var snapshot: Dictionary = {}
	# path -> installed spelling, for a file whose name differs only in case.
	var renamed: Dictionary = {}
	# Installed files under app/ and eloria-assets/ that no package lists.
	var retire: Array = []
	# A linked folder inside the game roots keeps the two-root promotion.
	var linked := false
	var started := 0
	var _root: String
	var _inventory_hash: String
	var _used := false

	func _init(root: String, release: Dictionary) -> void:
		_root = root
		_inventory_hash = JSON.stringify(release.packages).sha256_text()
		started = int(Time.get_unix_time_from_system())

	func take(root: String, release: Dictionary) -> bool:
		if _used:
			return false
		_used = true
		return root == _root and JSON.stringify(release.packages).sha256_text() == _inventory_hash

static func validate(release: Dictionary, identity: Dictionary) -> Dictionary:
	if release.has("launch_args"):
		if not release.launch_args is Array or release.launch_args.size() > 32:
			return {"error": "The game launch defaults are invalid."}
		for argument: Variant in release.launch_args:
			if not argument is String or argument.length() > 4096:
				return {"error": "The game launch defaults are invalid."}
	if release.get("repository") != identity.get("repository") or not release.get("version") is String or "/" in release.version or "\\" in release.version:
		return {"error": "The package release identity is invalid."}
	if not release.get("packages") is Array or release.packages.is_empty() or release.packages.size() > 850:
		return {"error": "The package list is invalid."}
	var base := "https://github.com/%s/releases/download/client-%s/" % [identity.repository, release.commit]
	var seen: Dictionary = {}
	var ids: Dictionary = {}
	var total := 0
	var unpacked := 0
	var count := 0
	var parts: Array = []
	for package: Variant in release.packages:
		if not package is Dictionary or not package.get("id") is String or package.id.is_empty() or package.id.length() > 96 or ids.has(package.id):
			return {"error": "A package identity is invalid."}
		for letter in str(package.id):
			if not letter in "abcdefghijklmnopqrstuvwxyz0123456789-":
				return {"error": "A package identity is invalid."}
		ids[package.id] = true
		if not Release.valid_hash(package.get("sha256")) or not Release.positive_integer(package.get("size")) or not package.get("files") is Array or package.files.is_empty() or package.files.size() > 100000 or not package.get("parts") is Array or package.parts.is_empty():
			return {"error": "A package inventory is invalid."}
		var bytes := 0
		for entry: Variant in package.files:
			if not entry is Dictionary or not Release.safe_path(entry.get("path")) or not Release.valid_hash(entry.get("sha256")) or not typeof(entry.get("size")) in [TYPE_INT, TYPE_FLOAT] or not Release.positive_integer(entry.size + 1) or seen.has(str(entry.path).to_lower()):
				return {"error": "A package contains an invalid or duplicate file."}
			seen[str(entry.path).to_lower()] = true
			bytes += int(entry.size)
		if bytes != package.get("unpacked_size") or package.files.size() != package.get("file_count"):
			return {"error": "A package's unpacked sizes do not agree."}
		var packed := 0
		for index in package.parts.size():
			var part: Variant = package.parts[index]
			var url := base + "%s.pkg.%s.zip.%03d" % [release.version, package.id, index + 1]
			if not part is Dictionary or (part.get("url") != url and not Release.shared_download(part, identity.repository)) or not Release.valid_hash(part.get("sha256")) or not Release.positive_integer(part.get("size"), 256 * 1024 * 1024):
				return {"error": "A package download is invalid."}
			packed += int(part.size)
			parts.append(part)
		if packed != int(package.size):
			return {"error": "A package's download sizes do not agree."}
		total += packed
		unpacked += bytes
		count += package.files.size()
	var extension := "exe" if identity.platform == "windows" else "x86_64"
	for kind: String in ["updater", "uninstall"]:
		var helper: Variant = release.get(kind)
		if not helper is Dictionary or (helper.get("url") != base + release.version + "-" + kind + "." + extension and not Release.shared_download(helper, identity.repository, kind, extension)) or not Release.valid_hash(helper.get("sha256")) or not Release.positive_integer(helper.get("size"), 512 * 1024 * 1024):
			return {"error": "The updater or uninstaller download is invalid."}
	if count > 100000 or total != release.get("size") or unpacked != release.get("unpacked_size") or count != release.get("file_count") or parts != release.get("parts") or not Release.valid_hash(release.get("sha256")):
		return {"error": "The package totals do not agree."}
	return release

static func package_path(cache: String, package: Dictionary) -> String:
	return cache.path_join("packages/" + str(package.sha256) + ".zip")

static func matches(root: String, package: Dictionary, directories: Dictionary = {}) -> bool:
	for entry: Dictionary in package.files:
		var path := root.path_join(entry.path)
		if linked_path(root, entry.path, directories) or not Release.check_file(path, int(entry.size), entry.sha256):
			return false
	return true

static func linked_path(root: String, relative: String, directories: Dictionary = {}) -> bool:
	return Release.linked_path(root, relative, directories)

static func plan(root: String, release: Dictionary) -> Array:
	return inspect(root, release).needed

static func inspect(root: String, release: Dictionary, progress := Callable()) -> CheckedPlan:
	# Per file: every installed file is still SHA-256 checked once, and only
	# members that differ are downloaded, unpacked and replaced.
	var checked := CheckedPlan.new(root, release)
	var installed := _installed_files(root, checked)
	# Windows folds case. A member whose installed name differs only in case
	# is replaced so the new spelling lands; folder case is left as installed.
	var folded := OS.get_name() == "Windows"
	var spelled: Dictionary = {}
	if folded:
		for path: String in installed:
			spelled[path.to_lower()] = path
	var claimed: Dictionary = {}
	var directories: Dictionary = {}
	var completed := 0
	for package: Dictionary in release.packages:
		Release.report_progress(progress, "Checking installed packages", completed, release.packages.size(), package.id)
		var members: Array = []
		for index in package.files.size():
			var entry: Dictionary = package.files[index]
			var path: String = entry.path
			var key := path.to_lower() if folded else path
			var actual: String = spelled.get(key, "") if folded else (path if installed.has(path) else "")
			claimed[key] = true
			if actual != "" and actual.get_file() != path.get_file():
				checked.renamed[path] = actual
				members.append(index)
			elif actual == "" or linked_path(root, path, directories) or not Release.check_file(root.path_join(path), int(entry.size), entry.sha256):
				members.append(index)
			else:
				checked.snapshot[path] = [int(entry.size), FileAccess.get_modified_time(root.path_join(path)), entry.sha256]
		checked.unchanged[package.id] = members.is_empty()
		if not members.is_empty():
			checked.changed[package.id] = members
			checked.needed.append(package)
		completed += 1
	for path: String in installed:
		if not claimed.has(path.to_lower() if folded else path):
			checked.retire.append(path)
	Release.report_progress(progress, "Checking installed packages", completed, release.packages.size())
	return checked

static func _installed_files(root: String, checked: CheckedPlan) -> Dictionary:
	# Installed files under the game roots, spelled as on disk. Folder links
	# are noted and never followed; a file link moves as the link itself.
	var files: Dictionary = {}
	for name: String in Release.ROOTS:
		if Release.is_link(root.path_join(name)):
			checked.linked = true
		elif DirAccess.dir_exists_absolute(root.path_join(name)):
			_list_files(root, name, files, checked)
	return files

static func _list_files(root: String, relative: String, files: Dictionary, checked: CheckedPlan) -> void:
	var directory := DirAccess.open(root.path_join(relative))
	if directory == null:
		return
	directory.include_hidden = true
	for name: String in directory.get_files():
		files[relative + "/" + name] = true
	for name: String in directory.get_directories():
		if directory.is_link(name):
			checked.linked = true
		else:
			_list_files(root, relative + "/" + name, files, checked)

static func assemble(cache: String, package: Dictionary) -> String:
	var destination := package_path(cache, package)
	if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK:
		return "The package cache is not writable."
	if package.parts.size() == 1:
		var part: Dictionary = package.parts[0]
		if int(part.size) == int(package.size) and part.sha256 == package.sha256:
			var path := cache.path_join("packages/" + part.sha256 + ".part")
			if not Release.check_file(path, int(part.size), part.sha256):
				return "A package download failed verification."
			if DirAccess.rename_absolute(path, destination) != OK:
				return "The verified package could not be recorded."
			return ""
	var output := FileAccess.open(destination + ".tmp", FileAccess.WRITE)
	if output == null:
		return "There is not enough space for this package."
	for part: Dictionary in package.parts:
		var path := cache.path_join("packages/" + part.sha256 + ".part")
		if not Release.check_file(path, int(part.size), part.sha256):
			return "A package download failed verification."
		var input := FileAccess.open(path, FileAccess.READ)
		while input.get_position() < input.get_length():
			output.store_buffer(input.get_buffer(Release.CHUNK_BYTES))
			if output.get_error() != OK:
				return "The package could not be saved. Check free disk space."
	output.flush()
	output.close()
	if not Release.check_file(destination + ".tmp", int(package.size), package.sha256):
		return "The complete package failed verification."
	if DirAccess.rename_absolute(destination + ".tmp", destination) != OK:
		return "The verified package could not be recorded."
	for part: Dictionary in package.parts:
		DirAccess.remove_absolute(cache.path_join("packages/" + part.sha256 + ".part"))
	return ""

static func extract(archive: String, stage: String, package: Dictionary, members: Array = []) -> String:
	# members: inventory indices to unpack; empty unpacks every file.
	if not Release.check_file(archive, int(package.size), package.sha256):
		return "A package is missing or damaged. Run the updater again."
	var zip := Release.PayloadArchive.new()
	if zip.open(archive) != OK:
		return "A package archive cannot be opened."
	var inventory: Variant = JSON.parse_string(zip.read_file("inventory.json").get_string_from_utf8())
	if inventory != package.files:
		return "A package's files do not match the signed inventory."
	for index: int in (members if not members.is_empty() else range(package.files.size())):
		var entry: Dictionary = package.files[index]
		var path := stage.path_join(entry.path)
		if DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK:
			return "The package staging folder cannot be created."
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			return "The package cannot be unpacked. Check free disk space."
		var remaining := int(entry.size)
		var chunk := 0
		var hash := HashingContext.new()
		hash.start(HashingContext.HASH_SHA256)
		while remaining > 0:
			var bytes := zip.read_file("files/%06d/%06d" % [index, chunk])
			if bytes.size() != mini(Release.CHUNK_BYTES, remaining):
				return "An unpacked package file is incomplete."
			file.store_buffer(bytes)
			hash.update(bytes)
			remaining -= bytes.size()
			chunk += 1
		file.flush()
		var error := file.get_error()
		file.close()
		# Validate the decoded bytes here; install() reads and hashes every
		# staged file again before anything live changes.
		if error != OK or hash.finish().hex_encode() != entry.sha256:
			return "An unpacked package file failed verification."
	return ""

static func install(root: String, release: Dictionary, identity: Dictionary, progress := Callable(), checked: CheckedPlan = null) -> String:
	# All staging is outside the live roots. An existing installation receives
	# only its changed files, each move recorded in a per-file journal first; a
	# fresh one keeps the two-root promotion and legacy journal.
	var interrupted := FileAccess.file_exists(root.path_join(Release.JOURNAL_V2)) or FileAccess.file_exists(root.path_join(".eloria-update-journal.json"))
	var recovery := Release.recover(root)
	if recovery != "":
		return recovery
	var cache := Release.cache_for(root)
	# A plan made before recovery describes files recovery has since moved.
	if checked == null or not checked.take(root, release) or interrupted:
		checked = inspect(root, release, progress)
	if checked.needed.is_empty():
		DirAccess.remove_absolute(cache.path_join("pending.json"))
		return ""
	var fresh := true
	for name: String in Release.ROOTS:
		if Release.is_link(root.path_join(name)):
			return "The installed game folders must not be links."
		fresh = fresh and not DirAccess.dir_exists_absolute(root.path_join(name))
	var error := _install_roots(root, release, identity, progress, checked) if fresh or checked.linked else _install_files(root, release, identity, progress, checked)
	if error != "":
		return error
	Release.save_json(root.path_join(".rabbitlands-install.json"), {"schema": 1, "repository": identity.repository, "platform": identity.platform})
	DirAccess.remove_absolute(cache.path_join("pending.json"))
	Release.remove_tree(cache.path_join("packages"))
	Release.remove_tree(root.path_join(Release.STAGE))
	Release.report_progress(progress, "Game packages installed", 1, 1)
	return ""

static func _install_files(root: String, release: Dictionary, identity: Dictionary, progress: Callable, checked: CheckedPlan) -> String:
	# Stage only the changed members. Matching files are never copied, and are
	# hashed again only if their size or time changed after the scan.
	var cache := Release.cache_for(root)
	var stage := root.path_join(Release.STAGE)
	# An older updater's whole-game backup: recover() has run, so nothing can
	# read it, and this transaction keeps its own per-file backup.
	Release.remove_backup(root)
	var changed_bytes := 0
	for package: Dictionary in checked.needed:
		for member: int in checked.changed[package.id]:
			changed_bytes += int(package.files[member].size)
	var free := space_left(root)
	# 0 also means the volume could not be queried; unpacking reports a real lack.
	if free > 0 and free < changed_bytes + FREE_SPACE_MARGIN:
		return "There is not enough free disk space for this update: %s needed, %s free. Free some space and run the updater again." % [String.humanize_size(changed_bytes + FREE_SPACE_MARGIN), String.humanize_size(free)]
	if Release.remove_tree(stage) != OK or DirAccess.make_dir_recursive_absolute(stage) != OK:
		return "The update staging folder cannot be created."
	var staged: Dictionary = {}
	var staged_directories: Dictionary = {}
	for index in checked.needed.size():
		var package: Dictionary = checked.needed[index]
		Release.report_progress(progress, "Preparing game packages", index, checked.needed.size(), package.id)
		var members: Array = checked.changed[package.id]
		var unpacked := extract(package_path(cache, package), stage, package, members)
		if unpacked != "":
			return unpacked
		for member: int in members:
			var entry: Dictionary = package.files[member]
			if linked_path(stage, entry.path, staged_directories) or not Release.check_file(stage.path_join(entry.path), int(entry.size), entry.sha256):
				return "A staged package failed verification. The installed game was kept."
			staged[entry.path] = entry
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	var error := _required_files_error(func(path: String) -> String: return stage.path_join(path) if staged.has(path) else root.path_join(path), release, identity)
	if error != "":
		return error
	if identity.platform == "linux" and staged.has("app/" + binary) and FileAccess.set_unix_permissions(stage.path_join("app/" + binary), 493) != OK:
		return "The game cannot be marked executable."
	var journal := operations(root, release, checked, staged)
	error = Release.apply_operations(root, journal, progress)
	if error != "":
		return error
	# Commit point: the live tree must now be exactly the signed release.
	error = _required_files_error(func(path: String) -> String: return root.path_join(path), release, identity)
	if error == "":
		error = _placed_error(root, staged)
	if error == "":
		error = _snapshot_error(root, checked)
	if error != "":
		var restored := Release.recover(root)
		return error if restored == "" else restored
	return Release.commit_operations(root, journal)

static func _install_roots(root: String, release: Dictionary, identity: Dictionary, progress: Callable, checked: CheckedPlan) -> String:
	# A fresh installation, or one with a linked folder inside its roots: stage
	# both complete roots and swap them with the legacy two-root journal.
	var cache := Release.cache_for(root)
	var stage := root.path_join(Release.STAGE)
	var backup := root.path_join(".eloria-previous")
	if Release.remove_tree(stage) != OK or DirAccess.make_dir_recursive_absolute(stage) != OK:
		return "The update staging folder cannot be created."
	for name: String in Release.ROOTS:
		if DirAccess.make_dir_recursive_absolute(stage.path_join(name)) != OK:
			return "The update staging folder cannot be created."
	var staged_directories: Dictionary = {}
	for index in release.packages.size():
		var package: Dictionary = release.packages[index]
		Release.report_progress(progress, "Preparing game packages", index, release.packages.size(), package.id)
		if checked.unchanged[package.id]:
			# The plan checked actual files, including pre-package installations.
			# Final stage hashes catch changes made during downloading/copying.
			for entry: Dictionary in package.files:
				var destination := stage.path_join(entry.path)
				if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK or DirAccess.copy_absolute(root.path_join(entry.path), destination) != OK:
					return "The unchanged game files could not be staged. Check free disk space."
		else:
			var error := extract(package_path(cache, package), stage, package)
			if error != "":
				return error
		if not matches(stage, package, staged_directories):
			return "A staged package failed verification. The installed game was kept."
	var required := _required_files_error(func(path: String) -> String: return stage.path_join(path), release, identity)
	if required != "":
		return required
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	if identity.platform == "linux" and FileAccess.set_unix_permissions(stage.path_join("app/" + binary), 493) != OK:
		return "The game cannot be marked executable."
	if Release.remove_tree(backup) != OK or DirAccess.make_dir_recursive_absolute(backup) != OK:
		return "The previous update backup cannot be replaced."
	var original_roots: Array = []
	for name: String in Release.ROOTS:
		if DirAccess.dir_exists_absolute(root.path_join(name)):
			original_roots.append(name)
	if Release.save_json(root.path_join(".eloria-update-journal.json"), {"commit": release.commit, "original_roots": original_roots}) != OK:
		return "The update recovery record cannot be saved."
	var promotion_error := Release.promote_staged(root, progress)
	if promotion_error != "":
		return promotion_error
	if DirAccess.remove_absolute(root.path_join(".eloria-update-journal.json")) != OK:
		return "The update recovery record could not be cleared. Restart the updater."
	if original_roots.is_empty():
		# A fresh installation replaced nothing; drop the empty backup folder.
		Release.remove_backup(root)
	return ""

static func operations(root: String, release: Dictionary, checked: CheckedPlan, staged: Dictionary) -> Dictionary:
	# The recovery journal: retirements first (they can free a path a new
	# file needs), then replacements, then additions. Existence is read now,
	# just before the journal is written, not taken from the earlier scan.
	var retire: Array = []
	var replace: Array = []
	var add: Array = []
	for path: String in checked.retire:
		# Names the journal cannot represent safely stay where they are.
		if Release.safe_path(path) and (FileAccess.file_exists(root.path_join(path)) or Release.is_link(root.path_join(path))):
			retire.append({"path": path, "op": "retire"})
	var created: Dictionary = {}
	var existing: Dictionary = {}
	for path: String in staged:
		var original: String = checked.renamed.get(path, path)
		var operation := {"path": path, "op": "add", "sha256": staged[path].sha256}
		if FileAccess.file_exists(root.path_join(original)) or Release.is_link(root.path_join(original)):
			operation.op = "replace"
			if original != path:
				operation["from"] = original
			replace.append(operation)
		else:
			add.append(operation)
		# Folders this transaction creates, so a rollback can remove them.
		var components := path.split("/")
		for depth in range(1, components.size()):
			var folder := "/".join(components.slice(0, depth))
			if created.has(folder) or existing.has(folder):
				continue
			if DirAccess.dir_exists_absolute(root.path_join(folder)):
				existing[folder] = true
			else:
				created[folder] = true
	return {"schema": 2, "commit": release.commit, "stage": Release.STAGE, "backup": Release.BACKUP_V2,
		"operations": retire + replace + add, "directories": created.keys()}

static func space_left(path: String) -> int:
	# Free bytes on the volume holding path (or its nearest existing parent);
	# 0 when it cannot be queried.
	var probe := path
	while probe != "":
		var directory := DirAccess.open(probe)
		if directory != null:
			return directory.get_space_left()
		if probe.get_base_dir() == probe:
			break
		probe = probe.get_base_dir()
	return 0

static func _required_files_error(locate: Callable, release: Dictionary, identity: Dictionary) -> String:
	var descriptor := Release.read_json(locate.call("app/client-release.json"))
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	if descriptor.get("commit") != release.commit or descriptor.get("platform") != identity.platform or descriptor.get("public_key") != identity.public_key or Release.update_owner(descriptor) != "github" or not FileAccess.file_exists(locate.call("app/" + binary)) or not FileAccess.file_exists(locate.call("app/RabbitLands.pck")):
		return "The update is missing required game files or has a different signing key."
	return ""

static func _placed_error(root: String, staged: Dictionary) -> String:
	# Renames keep content; this proves every staged file arrived in place.
	for path: String in staged:
		if not FileAccess.file_exists(root.path_join(path)) or FileAccess.get_size(root.path_join(path)) != int(staged[path].size):
			return "An updated game file is missing after installation. The installed game was kept; run the updater again."
	return ""

static func _snapshot_error(root: String, checked: CheckedPlan) -> String:
	# Matching files were hashed before the download and never moved. One stat
	# proves each is unchanged, unless its size or time differs or its time is
	# too close to the scan to tell; those are hashed again.
	for path: String in checked.snapshot:
		var expected: Array = checked.snapshot[path]
		var absolute := root.path_join(path)
		var modified := FileAccess.get_modified_time(absolute)
		if modified == int(expected[1]) and modified + RACY_SECONDS < checked.started and FileAccess.file_exists(absolute) and FileAccess.get_size(absolute) == int(expected[0]):
			continue
		if not Release.check_file(absolute, int(expected[0]), expected[2]):
			return "A game file changed while the update was being prepared: %s. The installed game was kept; run the updater again." % path
	return ""

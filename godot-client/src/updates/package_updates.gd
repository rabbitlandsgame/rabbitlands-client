extends RefCounted
## Independent ZIP packages. Only signed paths are reused, downloaded or installed.
const Release = preload("res://src/updates/release.gd")

static func validate(release: Dictionary, identity: Dictionary) -> Dictionary:
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
			if not part is Dictionary or part.get("url") != url or not Release.valid_hash(part.get("sha256")) or not Release.positive_integer(part.get("size"), 256 * 1024 * 1024):
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
		if not helper is Dictionary or helper.get("url") != base + release.version + "-" + kind + "." + extension or not Release.valid_hash(helper.get("sha256")) or not Release.positive_integer(helper.get("size"), 512 * 1024 * 1024):
			return {"error": "The updater or uninstaller download is invalid."}
	if count > 100000 or total != release.get("size") or unpacked != release.get("unpacked_size") or count != release.get("file_count") or parts != release.get("parts") or not Release.valid_hash(release.get("sha256")):
		return {"error": "The package totals do not agree."}
	return release

static func package_path(cache: String, package: Dictionary) -> String:
	return cache.path_join("packages/" + str(package.sha256) + ".zip")

static func matches(root: String, package: Dictionary) -> bool:
	for entry: Dictionary in package.files:
		var path := root.path_join(entry.path)
		if linked_path(root, entry.path) or not Release.check_file(path, int(entry.size), entry.sha256):
			return false
	return true

static func linked_path(root: String, relative: String) -> bool:
	var path := root
	for component: String in relative.split("/"):
		path = path.path_join(component)
		if Release.is_link(path):
			return true
	return false

static func plan(root: String, release: Dictionary) -> Array:
	var needed: Array = []
	for package: Dictionary in release.packages:
		if not matches(root, package):
			needed.append(package)
	return needed

static func assemble(cache: String, package: Dictionary) -> String:
	var destination := package_path(cache, package)
	if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK:
		return "The package cache is not writable."
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

static func extract(archive: String, stage: String, package: Dictionary) -> String:
	if not Release.check_file(archive, int(package.size), package.sha256):
		return "A package is missing or damaged. Run the updater again."
	var zip := Release.PayloadArchive.new()
	if zip.open(archive) != OK:
		return "A package archive cannot be opened."
	var inventory: Variant = JSON.parse_string(zip.read_file("inventory.json").get_string_from_utf8())
	if inventory != package.files:
		return "A package's files do not match the signed inventory."
	for index in package.files.size():
		var entry: Dictionary = package.files[index]
		var path := stage.path_join(entry.path)
		if DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK:
			return "The package staging folder cannot be created."
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			return "The package cannot be unpacked. Check free disk space."
		var remaining := int(entry.size)
		var chunk := 0
		while remaining > 0:
			var bytes := zip.read_file("files/%06d/%06d" % [index, chunk])
			if bytes.size() != mini(Release.CHUNK_BYTES, remaining):
				return "An unpacked package file is incomplete."
			file.store_buffer(bytes)
			remaining -= bytes.size()
			chunk += 1
		file.flush()
		var error := file.get_error()
		file.close()
		if error != OK or not Release.check_file(path, int(entry.size), entry.sha256):
			return "An unpacked package file failed verification."
	return ""

static func install(root: String, release: Dictionary, identity: Dictionary, progress := Callable()) -> String:
	# All staging is outside the live roots. A crash during promotion uses the
	# same two-root journal and recovery as legacy full-game updates.
	var recovery := Release.recover(root)
	if recovery != "":
		return recovery
	var cache := Release.cache_for(root)
	var stage := root.path_join(".eloria-update-stage")
	var backup := root.path_join(".eloria-previous")
	var unchanged: Dictionary = {}
	var complete := true
	for package: Dictionary in release.packages:
		unchanged[package.id] = matches(root, package)
		complete = complete and unchanged[package.id]
	if complete:
		DirAccess.remove_absolute(cache.path_join("pending.json"))
		return ""
	if Release.remove_tree(stage) != OK or DirAccess.make_dir_recursive_absolute(stage) != OK:
		return "The update staging folder cannot be created."
	for name: String in Release.ROOTS:
		if Release.is_link(root.path_join(name)):
			return "The installed game folders must not be links."
		if DirAccess.make_dir_recursive_absolute(stage.path_join(name)) != OK:
			return "The update staging folder cannot be created."
	for index in release.packages.size():
		var package: Dictionary = release.packages[index]
		Release.report_progress(progress, "Preparing game packages", index, release.packages.size(), package.id)
		if unchanged[package.id]:
			# Recheck real file hashes, including for pre-package installations.
			# No unchanged package is downloaded, and user files are not copied.
			for entry: Dictionary in package.files:
				var destination := stage.path_join(entry.path)
				if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK or DirAccess.copy_absolute(root.path_join(entry.path), destination) != OK:
					return "The unchanged game files could not be staged. Check free disk space."
		else:
			var error := extract(package_path(cache, package), stage, package)
			if error != "":
				return error
		if not matches(stage, package):
			return "A staged package failed verification. The installed game was kept."
	var descriptor := Release.read_json(stage.path_join("app/client-release.json"))
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	if descriptor.get("commit") != release.commit or descriptor.get("platform") != identity.platform or descriptor.get("public_key") != identity.public_key or Release.update_owner(descriptor) != "github" or not FileAccess.file_exists(stage.path_join("app/" + binary)) or not FileAccess.file_exists(stage.path_join("app/RabbitLands.pck")):
		return "The update is missing required game files or has a different signing key."
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
	for name: String in Release.ROOTS:
		var current := root.path_join(name)
		if (DirAccess.dir_exists_absolute(current) and DirAccess.rename_absolute(current, backup.path_join(name)) != OK) or DirAccess.rename_absolute(stage.path_join(name), current) != OK:
			var error := Release.recover(root)
			return "The update could not be installed; the previous game was restored." if error == "" else error
	if DirAccess.remove_absolute(root.path_join(".eloria-update-journal.json")) != OK:
		return "The update recovery record could not be cleared. Restart the updater."
	Release.save_json(root.path_join(".rabbitlands-install.json"), {"schema": 1, "repository": identity.repository, "platform": identity.platform})
	DirAccess.remove_absolute(cache.path_join("pending.json"))
	Release.remove_tree(cache.path_join("packages"))
	Release.remove_tree(stage)
	Release.report_progress(progress, "Game packages installed", 1, 1)
	return ""

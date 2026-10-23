extends RefCounted
## Shared by the running game and the small restart launcher. No Python or
## system package manager is needed on a player's computer.
const CHUNK_BYTES := 8 * 1024 * 1024
const MAX_MANIFEST_BYTES := 16 * 1024 * 1024
const ROOTS := ["app", "eloria-assets"]
const DISTRIBUTION_SCHEMA := 1

# Godot's ZIPReader uses 32-bit minizip seek/tell callbacks on Windows,
# even in a 64-bit export. Read our bounded ZIP entries through FileAccess
# instead, preserving the existing signed ZIP/ZIP64 payload format.
class PayloadArchive extends RefCounted:
	const MAX_ENTRY_BYTES := 16 * 1024 * 1024
	const MAX_DIRECTORY_BYTES := 64 * 1024 * 1024
	var _file: FileAccess
	var _entries: Dictionary = {}
	var _directory_offset := 0

	func close() -> void:
		if _file != null:
			_file.close()
			_file = null
		_entries.clear()

	func open(path: String) -> Error:
		close()
		_file = FileAccess.open(path, FileAccess.READ)
		if _file == null:
			return ERR_CANT_OPEN
		if not _read_directory():
			close()
			return ERR_FILE_CORRUPT
		return OK

	func _read_directory() -> bool:
		var length := _file.get_length()
		if length < 22:
			return false
		var tail_size := mini(length, 65535 + 22)
		_file.seek(length - tail_size)
		var tail := _file.get_buffer(tail_size)
		var end := tail.size() - 22
		while end >= 0:
			if tail.decode_u32(end) == 0x06054b50 and end + 22 + tail.decode_u16(end + 20) == tail.size():
				break
			end -= 1
		if end < 0 or tail.decode_u16(end + 4) != 0 or tail.decode_u16(end + 6) != 0 or tail.decode_u16(end + 8) != tail.decode_u16(end + 10):
			return false
		var count := int(tail.decode_u16(end + 10))
		var directory_size := int(tail.decode_u32(end + 12))
		_directory_offset = tail.decode_u32(end + 16)
		var directory_end := length - tail_size + end
		if count == 0xffff or directory_size == 0xffffffff or _directory_offset == 0xffffffff:
			if directory_end < 20:
				return false
			_file.seek(directory_end - 20)
			var locator := _file.get_buffer(20)
			if locator.size() != 20 or locator.decode_u32(0) != 0x07064b50 or locator.decode_u32(4) != 0 or locator.decode_u32(16) != 1:
				return false
			var offset := int(locator.decode_u64(8))
			if offset < 0 or offset > directory_end - 20 - 56:
				return false
			_file.seek(offset)
			var record := _file.get_buffer(56)
			if record.size() != 56 or record.decode_u32(0) != 0x06064b50 or record.decode_u64(4) != 44 or record.decode_u32(16) != 0 or record.decode_u32(20) != 0 or record.decode_u64(24) != record.decode_u64(32):
				return false
			count = record.decode_u64(32)
			directory_size = record.decode_u64(40)
			_directory_offset = record.decode_u64(48)
			directory_end = offset
		if count <= 0 or count > 250000 or directory_size < 46 or directory_size > MAX_DIRECTORY_BYTES or _directory_offset < 0 or _directory_offset > directory_end - directory_size:
			return false
		_file.seek(_directory_offset)
		var directory := _file.get_buffer(directory_size)
		if directory.size() != directory_size:
			return false
		var position := 0
		for index in count:
			if position > directory.size() - 46 or directory.decode_u32(position) != 0x02014b50:
				return false
			var header := directory.slice(position, position + 46)
			var name_size := int(header.decode_u16(28))
			var extra_size := int(header.decode_u16(30))
			var next := position + 46 + name_size + extra_size + header.decode_u16(32)
			if name_size == 0 or next > directory.size() or header.decode_u16(34) != 0:
				return false
			var name := directory.slice(position + 46, position + 46 + name_size).get_string_from_utf8()
			var packed := int(header.decode_u32(20))
			var unpacked := int(header.decode_u32(24))
			var offset := int(header.decode_u32(42))
			var extra := directory.slice(position + 46 + name_size, position + 46 + name_size + extra_size)
			var field := 0
			while field + 4 <= extra.size():
				var field_end := field + 4 + extra.decode_u16(field + 2)
				if field_end > extra.size():
					return false
				if extra.decode_u16(field) == 1:
					var cursor := field + 4
					if unpacked == 0xffffffff:
						if cursor + 8 > field_end:
							return false
						unpacked = extra.decode_u64(cursor)
						cursor += 8
					if packed == 0xffffffff:
						if cursor + 8 > field_end:
							return false
						packed = extra.decode_u64(cursor)
						cursor += 8
					if offset == 0xffffffff:
						if cursor + 8 > field_end:
							return false
						offset = extra.decode_u64(cursor)
				field = field_end
			var method := int(header.decode_u16(10))
			var flags := int(header.decode_u16(8))
			if _entries.has(name) or method not in [0, 8] or flags & ~0x080e or offset < 0 or offset > _directory_offset - 30 or packed < 0 or packed > MAX_ENTRY_BYTES + 65536 or unpacked < 0 or unpacked > MAX_ENTRY_BYTES:
				return false
			_entries[name] = {"offset": offset, "packed": packed, "unpacked": unpacked,
				"method": method, "flags": flags, "crc": header.decode_u32(16)}
			position = next
		return position == directory.size()

	func read_file(name: String) -> PackedByteArray:
		if _file == null or not _entries.has(name):
			return PackedByteArray()
		var entry: Dictionary = _entries[name]
		_file.seek(entry.offset)
		var header := _file.get_buffer(30)
		if header.size() != 30 or header.decode_u32(0) != 0x04034b50 or header.decode_u16(6) != entry.flags or header.decode_u16(8) != entry.method:
			return PackedByteArray()
		var name_size := int(header.decode_u16(26))
		var data_offset := int(entry.offset) + 30 + name_size + header.decode_u16(28)
		if data_offset > _directory_offset - int(entry.packed) or _file.get_buffer(name_size).get_string_from_utf8() != name:
			return PackedByteArray()
		_file.seek(data_offset)
		var bytes := _file.get_buffer(entry.packed)
		if bytes.size() != entry.packed:
			return PackedByteArray()
		if entry.method == 0:
			return bytes if bytes.size() == entry.unpacked else PackedByteArray()
		# ZIP stores raw DEFLATE. A gzip wrapper lets Godot's bounded native
		# decompressor validate its CRC and length without a Python dependency.
		var gzip := PackedByteArray([31, 139, 8, 0, 0, 0, 0, 0, 0, 3])
		gzip.append_array(bytes)
		var footer := PackedByteArray()
		footer.resize(8)
		footer.encode_u32(0, entry.crc)
		footer.encode_u32(4, entry.unpacked)
		gzip.append_array(footer)
		return gzip.decompress(entry.unpacked, FileAccess.COMPRESSION_GZIP)

static func update_owner(identity: Dictionary) -> String:
	# Missing field is a pre-channel GitHub installation. Never infer this from
	# launch arguments, environment variables, or whether Steam is running.
	return str(identity.get("distribution", "github"))

static func external_update_message(identity: Dictionary) -> String:
	if update_owner(identity) == "steam":
		return "A game update is required. Close Rabbit Lands and let Steam update it. If no update appears, restart Steam or verify the installed files."
	return "A game update is required. Download and install the latest Rabbit Lands build from its original download page."

static func lease_process_running(pid: int) -> bool:
	if pid <= 0:
		return false
	# Linux's Godot process table tracks children of this process. A game
	# started by a different launcher is not its child; /proc covers both.
	if OS.get_name() == "Linux":
		return DirAccess.dir_exists_absolute("/proc/%d" % pid)
	return OS.is_process_running(pid)

static func read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

static func save_json(path: String, value: Dictionary) -> Error:
	var file := FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(JSON.stringify(value))
	file.flush()
	var error := file.get_error()
	file.close()
	if error != OK:
		return error
	return DirAccess.rename_absolute(path + ".tmp", path)

static func install_root() -> String:
	return OS.get_executable_path().get_base_dir().get_base_dir().simplify_path()

static func cache_for(root: String) -> String:
	return ProjectSettings.globalize_path("user://client-updates/" + root.sha256_text().left(24))

static func valid_commit(value: Variant) -> bool:
	if not value is String or value.length() != 40:
		return false
	for letter in value:
		if not letter in "0123456789abcdef":
			return false
	return true

static func contains_commit(identity: Dictionary, required: String) -> bool:
	return required == identity.get("commit", "") or required in identity.get("ancestors", [])

static func positive_integer(value: Variant, maximum := 9007199254740991) -> bool:
	return typeof(value) in [TYPE_FLOAT, TYPE_INT] and is_finite(float(value)) and float(value) == floor(float(value)) and value > 0 and value <= maximum

static func https_url(value: Variant) -> bool:
	return value is String and value.begins_with("https://") and value.length() < 4096 and not "\n" in value and not "\r" in value and not " " in value

static func valid_hash(value: Variant) -> bool:
	if not value is String or value.length() != 64:
		return false
	for letter in value:
		if not letter in "0123456789abcdef":
			return false
	return true

static func verify_envelope(envelope: Dictionary, identity: Dictionary) -> Dictionary:
	if update_owner(identity) != "github":
		return {"error": "This installation is updated by its distribution service."}
	if not envelope.get("payload") is String or not envelope.get("signature") is String:
		return {"error": "The release information is invalid."}
	var payload := Marshalls.base64_to_raw(envelope.payload)
	if payload.is_empty() or payload.size() > MAX_MANIFEST_BYTES:
		return {"error": "The release information is too large."}
	var key := CryptoKey.new()
	if key.load_from_string(str(identity.get("public_key", "")), true) != OK:
		return {"error": "The update signing key is missing."}
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(payload)
	if not Crypto.new().verify(HashingContext.HASH_SHA256, hash.finish(), Marshalls.base64_to_raw(envelope.signature), key):
		return {"error": "The release signature could not be verified."}
	var parsed: Variant = JSON.parse_string(payload.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"error": "The release information is invalid."}
	return parsed

static func verify_manifest(envelope: Dictionary, identity: Dictionary, target := "") -> Dictionary:
	var release := verify_envelope(envelope, identity)
	if release.has("error"):
		return release
	if release.get("schema") != 1 and release.get("schema") != 2:
		return {"error": "The update format is unsupported."}
	if not valid_commit(release.get("commit")) or release.get("platform") != identity.get("platform"):
		return {"error": "The release is for a different client."}
	if target != "" and release.commit != target:
		return {"error": "The release does not match the server's client commit."}
	if release.schema == 2:
		return load("res://src/updates/package_updates.gd").validate(release, identity)
	if not valid_hash(release.get("sha256")) or not positive_integer(release.get("size")) or not positive_integer(release.get("unpacked_size")):
		return {"error": "The release size or checksum is invalid."}
	if not release.get("parts") is Array or release.parts.is_empty() or release.parts.size() > 1000:
		return {"error": "The release download list is invalid."}
	var total := 0
	for part: Variant in release.parts:
		if not part is Dictionary or not https_url(part.get("url")) or not valid_hash(part.get("sha256")) or not positive_integer(part.get("size"), 1024 * 1024 * 1024):
			return {"error": "A release download is invalid."}
		total += int(part.size)
	if total != int(release.size):
		return {"error": "The release sizes do not agree."}
	return release

static func check_file(path: String, size: int, digest: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	var length := file.get_length()
	file.close()
	return length == size and FileAccess.get_sha256(path) == digest

static func remove_tree(path: String) -> Error:
	# Never follow a symlink/junction out of an updater-owned directory.
	if is_link(path) or not DirAccess.dir_exists_absolute(path):
		return DirAccess.remove_absolute(path) if FileAccess.file_exists(path) or is_link(path) else OK
	var directory := DirAccess.open(path)
	if directory == null:
		return ERR_CANT_OPEN
	directory.include_hidden = true
	for name: String in directory.get_files():
		var error := DirAccess.remove_absolute(path.path_join(name))
		if error != OK:
			return error
	for name: String in directory.get_directories():
		var error := remove_tree(path.path_join(name))
		if error != OK:
			return error
	return DirAccess.remove_absolute(path)

static func is_link(path: String) -> bool:
	var parent := DirAccess.open(path.get_base_dir())
	return parent != null and parent.is_link(path.get_file())

static func safe_path(path: Variant) -> bool:
	if not path is String or path.is_empty() or path.length() > 1024 or path.is_absolute_path() or "\\" in path or ":" in path:
		return false
	var components: PackedStringArray = str(path).split("/", true)
	if components.size() < 2 or not components[0] in ROOTS:
		return false
	for component: String in components:
		if component in ["", ".", ".."] or component.ends_with(".") or component.ends_with(" ") or component.begins_with(" "):
			return false
		for letter in component:
			if letter.unicode_at(0) < 32 or letter in "<>\"|?*":
				return false
		if component.get_slice(".", 0).to_upper() in ["CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"]:
			return false
	return true

static func report_progress(progress: Callable, phase: String, completed: int, total: int, detail := "") -> void:
	if progress.is_valid():
		progress.call(phase, completed, total, detail)

static func assemble(cache: String, release: Dictionary, progress := Callable()) -> String:
	var output := FileAccess.open(cache.path_join("release.zip.tmp"), FileAccess.WRITE)
	if output == null:
		return "There is not enough writable space for the update."
	var completed := 0
	report_progress(progress, "Preparing game files", 0, int(release.size))
	for index in release.parts.size():
		var part: Dictionary = release.parts[index]
		var path := cache.path_join("part-%04d" % index)
		if not check_file(path, int(part.size), part.sha256):
			return "An update download failed verification."
		var input := FileAccess.open(path, FileAccess.READ)
		while input.get_position() < input.get_length():
			var bytes := input.get_buffer(CHUNK_BYTES)
			output.store_buffer(bytes)
			if output.get_error() != OK:
				return "The update could not be saved. Check free disk space."
			completed += bytes.size()
			report_progress(progress, "Preparing game files", completed, int(release.size))
		input.close()
	output.flush()
	output.close()
	report_progress(progress, "Verifying prepared game files", 0, 1)
	if not check_file(cache.path_join("release.zip.tmp"), int(release.size), release.sha256):
		return "The complete update failed verification."
	report_progress(progress, "Verifying prepared game files", 1, 1)
	if DirAccess.rename_absolute(cache.path_join("release.zip.tmp"), cache.path_join("release.zip")) != OK:
		return "The update could not be saved."
	for index in release.parts.size():
		DirAccess.remove_absolute(cache.path_join("part-%04d" % index))
	return ""

static func extract(archive: String, destination: String, release: Dictionary, identity: Dictionary, progress := Callable()) -> String:
	var zip := PayloadArchive.new()
	if zip.open(archive) != OK:
		return "The update archive cannot be opened."
	# An inventory is signed indirectly by the archive checksum. Each large
	# file is split into 8 MiB chunks so even multi-GB PCKs use bounded memory.
	var inventory_bytes := zip.read_file("inventory.json")
	if inventory_bytes.size() > 16 * 1024 * 1024:
		return "The update inventory is too large."
	var inventory: Variant = JSON.parse_string(inventory_bytes.get_string_from_utf8())
	if not inventory is Array or inventory.is_empty() or inventory.size() > 100000:
		return "The update inventory is invalid."
	var seen: Dictionary = {}
	var total := 0
	var completed := 0
	report_progress(progress, "Unpacking game files", 0, int(release.unpacked_size), "0 of %d files" % inventory.size())
	for index in inventory.size():
		var entry: Variant = inventory[index]
		if not entry is Dictionary or not safe_path(entry.get("path")) or not valid_hash(entry.get("sha256")):
			return "The update contains an invalid file path or size."
		var size: Variant = entry.get("size", -1)
		if not typeof(size) in [TYPE_INT, TYPE_FLOAT] or not positive_integer(size + 1):
			return "The update contains an invalid file path or size."
		var path: String = entry.path
		if seen.has(path.to_lower()):
			return "The update contains duplicate paths."
		seen[path.to_lower()] = true
		total += int(entry.size)
		if total > int(release.unpacked_size):
			return "The unpacked update exceeds its declared size."
		var target := destination.path_join(path)
		if DirAccess.make_dir_recursive_absolute(target.get_base_dir()) != OK:
			return "The update staging folder cannot be created."
		var file := FileAccess.open(target, FileAccess.WRITE)
		if file == null:
			return "The update files cannot be saved."
		var remaining := int(entry.size)
		var chunk := 0
		while remaining > 0:
			var bytes := zip.read_file("files/%06d/%06d" % [index, chunk])
			if bytes.size() != mini(CHUNK_BYTES, remaining):
				return "An update file is incomplete."
			file.store_buffer(bytes)
			if file.get_error() != OK:
				return "An update file cannot be written. Check free disk space."
			remaining -= bytes.size()
			chunk += 1
			completed += bytes.size()
			report_progress(progress, "Unpacking game files", completed, int(release.unpacked_size), "%d of %d files" % [index, inventory.size()])
		file.close()
		if not check_file(target, int(entry.size), entry.sha256):
			return "An extracted update failed verification."
		report_progress(progress, "Unpacking game files", completed, int(release.unpacked_size), "%d of %d files" % [index + 1, inventory.size()])
	zip.close()
	var descriptor := read_json(destination.path_join("app/client-release.json"))
	var binary := "RabbitLands.exe" if identity.platform == "windows" else "RabbitLands.x86_64"
	if total != int(release.unpacked_size) or descriptor.get("commit") != release.commit or descriptor.get("platform") != identity.platform or update_owner(descriptor) != "github" or descriptor.get("public_key") != identity.public_key or not FileAccess.file_exists(destination.path_join("app/" + binary)) or not FileAccess.file_exists(destination.path_join("app/RabbitLands.pck")) or not DirAccess.dir_exists_absolute(destination.path_join("eloria-assets")):
		return "The update is missing required game files or has a different signing key."
	if identity.platform == "linux":
		if FileAccess.set_unix_permissions(destination.path_join("app/" + binary), 493) != OK:
			return "The updated game cannot be marked executable."
	return ""

static func recover(root: String) -> String:
	var journal := root.path_join(".eloria-update-journal.json")
	if not FileAccess.file_exists(journal):
		return ""
	var backup := root.path_join(".eloria-previous")
	var record := read_json(journal)
	if is_link(backup):
		return "The update recovery folder must not be a link."
	for name: String in ROOTS:
		var original := backup.path_join(name)
		if is_link(original) or is_link(root.path_join(name)):
			return "The game recovery folders must not be links."
		if DirAccess.dir_exists_absolute(original):
			var current := root.path_join(name)
			if remove_tree(current) != OK or DirAccess.rename_absolute(original, current) != OK:
				return "Close all running Rabbit Lands windows and restart the launcher to finish recovery."
		elif record.has("original_roots") and name not in record.original_roots:
			if remove_tree(root.path_join(name)) != OK:
				return "The interrupted fresh installation could not be recovered."
	DirAccess.remove_absolute(journal)
	return ""

static func install(root: String, identity: Dictionary, repair := false, progress := Callable()) -> String:
	if update_owner(identity) != "github":
		return "This installation is updated by its distribution service."
	# Also protect games started directly, outside the restart launcher.
	var running_cache := DirAccess.open(cache_for(root))
	if running_cache != null:
		for name: String in running_cache.get_files():
			if name.begins_with("running-") and name.ends_with(".json"):
				var path := cache_for(root).path_join(name)
				var lease := read_json(path)
				if lease_process_running(int(lease.get("pid", 0))):
					return "Close the running Rabbit Lands game before installing its update."
				DirAccess.remove_absolute(path)
	var recovery := recover(root)
	if recovery != "":
		return recovery
	var cache := cache_for(root)
	var envelope := read_json(cache.path_join("pending.json"))
	if envelope.is_empty():
		return ""
	var release := verify_manifest(envelope, identity)
	if release.has("error"):
		DirAccess.remove_absolute(cache.path_join("pending.json"))
		return release.error
	if release.schema == 2:
		return load("res://src/updates/package_updates.gd").install(root, release, identity, progress)
	var current := read_json(root.path_join("app/client-release.json"))
	if not repair and contains_commit(current, release.commit):
		DirAccess.remove_absolute(cache.path_join("pending.json"))
		return ""
	report_progress(progress, "Verifying game archive", 0, 1)
	if not check_file(cache.path_join("release.zip"), int(release.size), release.sha256):
		DirAccess.remove_absolute(cache.path_join("pending.json"))
		return "The downloaded update failed verification. The installed game was kept."
	report_progress(progress, "Verifying game archive", 1, 1)
	var stage := root.path_join(".eloria-update-stage")
	var backup := root.path_join(".eloria-previous")
	for name: String in ROOTS:
		if is_link(root.path_join(name)) or not DirAccess.dir_exists_absolute(root.path_join(name)):
			return "The installed game folders are missing or are links. Extract a fresh client download."
	if remove_tree(stage) != OK or DirAccess.make_dir_recursive_absolute(stage) != OK:
		return "The update staging folder cannot be created."
	var error := extract(cache.path_join("release.zip"), stage, release, identity, progress)
	if error != "":
		remove_tree(stage)
		return error
	report_progress(progress, "Installing verified game files", 0, ROOTS.size())
	if remove_tree(backup) != OK or DirAccess.make_dir_recursive_absolute(backup) != OK:
		return "The previous update backup cannot be replaced."
	var journal := root.path_join(".eloria-update-journal.json")
	if save_json(journal, {"commit": release.commit}) != OK:
		return "The update recovery record cannot be saved."
	for name: String in ROOTS:
		if DirAccess.rename_absolute(root.path_join(name), backup.path_join(name)) != OK or DirAccess.rename_absolute(stage.path_join(name), root.path_join(name)) != OK:
			var rollback := recover(root)
			return "The update could not be installed; the previous game was restored." if rollback == "" else rollback
		report_progress(progress, "Installing verified game files", ROOTS.find(name) + 1, ROOTS.size())
	# Clear the journal before marking the download consumed. A crash before
	# this point rolls the folders back together on the following launch.
	if DirAccess.remove_absolute(journal) != OK:
		return recover(root)
	DirAccess.remove_absolute(cache.path_join("pending.json"))
	DirAccess.remove_absolute(cache.path_join("release.zip"))
	remove_tree(stage)
	return ""

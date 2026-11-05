extends RefCounted
## Shared by the running game and the small restart launcher. No Python or
## system package manager is needed on a player's computer.
const CHUNK_BYTES := 8 * 1024 * 1024
const MAX_MANIFEST_BYTES := 16 * 1024 * 1024
const ROOTS := ["app", "eloria-assets"]
const DISTRIBUTION_SCHEMA := 1
# Per-file package installs (schema 2 and 3 manifests with live roots). Old updaters
# never read these names, so they cannot "recover" a half-applied delta.
const STAGE := ".eloria-update-stage"
const JOURNAL_V2 := ".eloria-update-journal-v2.json"
const BACKUP_V2 := ".eloria-update-backup"
const OPERATION_KINDS := ["retire", "replace", "add"]
const INSTALL_PHASE := "Installing verified game files"
# Signed manifest schemas this updater reads: 1 is one whole-game archive, 2
# lists independent packages, and 3 is schema 2 whose inventory rows may name a
# codec (W2-UD-05, package_updates.gd). Updaters before schema 3 reject it in
# verify_manifest; they still verify its bootstrap rows and replace themselves
# with the helper it names, which reads it.
const CODEC_SCHEMA := 3
# Game content parts may also come from the desktop layout on Cloudflare R2
# (schema 3 only, package_updates.gd). R2 is transport: every part is checked
# against the SHA-256 in the signed manifest, as for GitHub. This base is
# compiled in and never read from a manifest, the server or the environment.
# The R2 release workflow looks for this exact line (desktop_r2.DESKTOP_ASSETS),
# and test fixtures replace it only in their own copies.
const DESKTOP_ASSETS := "https://assets.rabbitlandsgame.com/desktop/v1/"
# Release discovery (W1b): the signed per-platform pointer on R2 is read first;
# any failure (offline, a challenge page, a 404, a bad or stale signature, a
# manifest that does not match it) falls back to the GitHub alias. The pointer
# format is tools/desktop_r2.py's pointer v1.
const POINTER_KIND := "rabbitlands-release-pointer"
const POINTER_SCHEMA := 1
const POINTER_CHANNEL := "live"
const MAX_POINTER_BYTES := 64 * 1024
const POINTER_TIMEOUT_SEC := 15.0
const POINTER_FIELDS := ["kind", "pointer_schema", "repository", "platform", "channel", "sequence", "rollback", "release_id", "run_id", "target"]
const POINTER_TARGET_FIELDS := ["commit", "version", "manifest_sequence", "manifest"]
const POINTER_MANIFEST_FIELDS := ["url", "sha256", "size"]
# Signed sequences are UTC Unix seconds at signing (desktop_r2 MIN/MAX_SEQUENCE).
const MIN_SEQUENCE := 1700000000
const MAX_SEQUENCE := 4102444800
# The installed-release record, in the install root, written after the commit
# point by the updater and the setup helper (package_updates.gd install).
const INSTALL_RECORD := ".rabbitlands-release.json"
# The highest pointer sequence this installation has accepted (update cache).
const POINTER_RECORD := "release-pointer.json"
const OLDER_RELEASE_MESSAGE := "This update is older than the installed game."

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

	func stored(name: String) -> bool:
		# An entry kept without ZIP compression (method 0). A zstd-coded
		# package file's chunks must be stored: the frame is the compression.
		return _entries.has(name) and int(_entries[name].method) == 0

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

static func shared_download(row: Dictionary, repository: String, kind := "pkg", extension := "zip.part") -> bool:
	if not valid_hash(row.get("sha256")):
		return false
	var prefix := "https://github.com/%s/releases/download/client-assets" % repository
	var filename := "/RabbitLands-%s-%s.%s" % [kind, row.sha256, extension]
	return row.get("url") == prefix + filename or (kind == "pkg" and extension == "zip.part" and row.get("url") == prefix + "-" + str(row.sha256).left(1) + filename)

static func r2_part(row: Variant) -> bool:
	# The one R2 form of a content part: DESKTOP_ASSETS + "parts/<sha256>.bin",
	# named by its own signed SHA-256. No other host, prefix, query or spelling.
	return row is Dictionary and valid_hash(row.get("sha256")) and row.get("url") is String and row.url == DESKTOP_ASSETS + "parts/" + str(row.sha256) + ".bin"

static func r2_manifest_url(platform: String, sha256: String) -> String:
	# An immutable copy of a signed manifest, named by the SHA-256 of its envelope.
	return DESKTOP_ASSETS + "manifests/%s/%s.json" % [platform, sha256]

static func pointer_url(platform: String) -> String:
	# The signed live pointer of a platform (read by discovery, W1b).
	return DESKTOP_ASSETS + "channels/live/%s.json" % platform

static func r2_manifest_sha256(url: Variant, platform: String) -> String:
	# The SHA-256 an R2 manifest URL names in its derived form, else "".
	var prefix := DESKTOP_ASSETS + "manifests/%s/" % platform
	if not url is String or not url.begins_with(prefix) or not url.ends_with(".json"):
		return ""
	var named: String = url.trim_prefix(prefix).trim_suffix(".json")
	return named if valid_hash(named) and url == r2_manifest_url(platform, named) else ""

static func target_manifest_url(url: Variant, repository: String, platform: String) -> bool:
	# Where a server notice may point for its required commit: a GitHub release
	# download of this repository, or an immutable R2 manifest copy in its
	# derived form. The manifest itself is still verified in full.
	if not https_url(url):
		return false
	return url.begins_with("https://github.com/%s/releases/download/" % repository) or r2_manifest_sha256(url, platform) != ""

static func parse_body(bytes: PackedByteArray) -> Variant:
	# A downloaded JSON body, or null. Quiet: a challenge page is no log error.
	var json := JSON.new()
	return json.data if json.parse(bytes.get_string_from_utf8()) == OK else null

static func bytes_sha256(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func sequence_value(value: Variant) -> bool:
	return positive_integer(value) and float(value) >= MIN_SEQUENCE and float(value) < MAX_SEQUENCE

static func release_sequence(release: Dictionary) -> int:
	# A signed manifest's sequence. A pre-R2 manifest has none and counts as 0.
	var value: Variant = release.get("sequence")
	return int(value) if sequence_value(value) else 0

static func _exact_fields(value: Variant, fields: Array) -> bool:
	if not value is Dictionary or value.size() != fields.size():
		return false
	for field: String in fields:
		if not value.has(field):
			return false
	return true

static func same_text(value: Variant, expected: Variant) -> bool:
	# Godot refuses to compare a String with a number, so check types first.
	return value is String and expected is String and value == expected

static func same_number(value: Variant, expected: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and typeof(expected) in [TYPE_INT, TYPE_FLOAT] and value == expected

static func verify_pointer(envelope: Variant, identity: Dictionary, high_water := 0) -> Dictionary:
	# A signed pointer v1 for this repository and platform whose sequence is at
	# least `high_water` (the highest pointer or installed sequence seen here).
	# It has no top-level commit, schema or packages, so no release verifier
	# accepts it; a release payload has no "kind", so it never passes here.
	if not envelope is Dictionary:
		return {"error": "The release pointer is invalid."}
	var pointer := verify_envelope(envelope, identity)
	if pointer.has("error"):
		return pointer
	var target: Variant = pointer.get("target")
	var manifest: Variant = target.get("manifest") if target is Dictionary else null
	if not same_text(pointer.get("kind"), POINTER_KIND) or not _exact_fields(pointer, POINTER_FIELDS) or not _exact_fields(target, POINTER_TARGET_FIELDS) or not _exact_fields(manifest, POINTER_MANIFEST_FIELDS):
		return {"error": "The release pointer is invalid."}
	if not same_number(pointer.pointer_schema, POINTER_SCHEMA) or not same_text(pointer.repository, identity.get("repository")) or not same_text(pointer.platform, identity.get("platform")) or not same_text(pointer.channel, POINTER_CHANNEL):
		return {"error": "The release pointer is for a different client."}
	if not sequence_value(pointer.sequence) or not pointer.rollback is bool or not positive_integer(pointer.release_id) or not positive_integer(pointer.run_id):
		return {"error": "The release pointer is invalid."}
	if not valid_commit(target.commit) or not target.version is String or target.version.is_empty() or "/" in target.version or "\\" in target.version or not sequence_value(target.manifest_sequence) or int(target.manifest_sequence) >= int(pointer.sequence):
		return {"error": "The release pointer is invalid."}
	if not valid_hash(manifest.sha256) or not positive_integer(manifest.size, MAX_MANIFEST_BYTES) or not same_text(manifest.url, r2_manifest_url(pointer.platform, manifest.sha256)):
		return {"error": "The release pointer is invalid."}
	if int(pointer.sequence) < high_water:
		return {"error": "The release pointer is older than one this installation has seen."}
	return pointer

static func matches_pointer(release: Dictionary, pointer: Dictionary) -> bool:
	# The verified manifest a pointer names (by SHA-256) carries what it says.
	var target: Dictionary = pointer.target
	return same_text(release.get("commit"), target.commit) and same_text(release.get("version"), target.version) and same_text(release.get("platform"), pointer.platform) and release_sequence(release) == int(target.manifest_sequence)

static func fetch_pointer(transport: Node, identity: Dictionary, high_water := 0) -> Dictionary:
	# GET the platform's pointer with a 15 s timeout and a 64 KiB limit, then
	# verify it. Returns the pointer payload, or {"error"}.
	var fetched: Dictionary = await transport.fetch_pointer(pointer_url(str(identity.get("platform"))))
	if fetched.has("error"):
		return {"error": "The release pointer is unavailable."}
	var body: PackedByteArray = fetched.get("body", PackedByteArray())
	if body.is_empty() or body.size() > MAX_POINTER_BYTES:
		return {"error": "The release pointer is invalid."}
	return verify_pointer(parse_body(body), identity, high_water)

static func fetch_pointed_manifest(transport: Node, pointer: Dictionary) -> Dictionary:
	# GET the immutable manifest a verified pointer names, limited to its size,
	# and require its exact SHA-256. Returns {"body", "envelope", "sha256"} or
	# {"error"}. The caller verifies the envelope and matches_pointer.
	var manifest: Dictionary = pointer.target.manifest
	var fetched: Dictionary = await transport.fetch(manifest.url, "", int(manifest.size))
	if fetched.has("error"):
		return {"error": "The pointed release information is unavailable."}
	var body: PackedByteArray = fetched.get("body", PackedByteArray())
	if body.size() != int(manifest.size) or bytes_sha256(body) != manifest.sha256:
		return {"error": "The pointed release information does not match its pointer."}
	var envelope: Variant = parse_body(body)
	if not envelope is Dictionary:
		return {"error": "The pointed release information is invalid."}
	return {"body": body, "envelope": envelope, "sha256": manifest.sha256}

static func stored_pointer_sequence(root: String) -> int:
	# A missing or unreadable record counts as no mark.
	var record := read_json(cache_for(root).path_join(POINTER_RECORD))
	return int(record.sequence) if same_number(record.get("schema"), 1) and sequence_value(record.get("sequence")) else 0

static func store_pointer_sequence(root: String, sequence: int) -> void:
	# Only ever raised; written with temp + rename.
	if not sequence_value(sequence) or sequence <= stored_pointer_sequence(root):
		return
	var cache := cache_for(root)
	if is_link(cache) or DirAccess.make_dir_recursive_absolute(cache) != OK or is_link(cache.path_join(POINTER_RECORD)):
		return
	save_json(cache.path_join(POINTER_RECORD), {"schema": 1, "sequence": sequence})

static func installed_sequence(root: String, commit: Variant) -> int:
	# The signed sequence of the installed release, from its record. A record of
	# another commit (another installer changed the game since) counts as none,
	# as does a pre-R2 installation without a record.
	var record := read_json(root.path_join(INSTALL_RECORD))
	if not same_number(record.get("schema"), 1) or not valid_commit(commit) or not same_text(record.get("commit"), commit) or not sequence_value(record.get("sequence")):
		return 0
	return int(record.sequence)

static func pointer_high_water(root: String, commit: Variant) -> int:
	return maxi(stored_pointer_sequence(root), installed_sequence(root, commit))

static func save_install_record(root: String, release: Dictionary, manifest_sha256 := "") -> Error:
	# After the commit point: what is installed now, and its signed sequence.
	var record := {"schema": 1, "commit": release.get("commit"), "platform": release.get("platform"), "sequence": release_sequence(release)}
	if valid_hash(manifest_sha256):
		record["manifest_sha256"] = manifest_sha256
	var path := root.path_join(INSTALL_RECORD)
	var error := ERR_FILE_CANT_WRITE if is_link(path) else save_json(path, record)
	if error != OK:
		# Never keep a record that describes an earlier release.
		DirAccess.remove_absolute(path)
	return error

static func downgrade_error(release: Dictionary, installed: int, admitted := false) -> String:
	# Refuse a signed manifest older than the installed release, unless a signed
	# rollback pointer named exactly it (`admitted`). Equal sequences repair.
	if installed > 0 and release_sequence(release) < installed and not admitted:
		return OLDER_RELEASE_MESSAGE
	return ""

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

static func package_manifest(release: Dictionary) -> bool:
	# Schemas 2 and 3 list packages (installed by package_updates.gd). JSON
	# numbers are floats, so compare values, never with Array.has.
	var schema: Variant = release.get("schema")
	return typeof(schema) in [TYPE_INT, TYPE_FLOAT] and (schema == 2 or schema == CODEC_SCHEMA)

static func verify_manifest(envelope: Dictionary, identity: Dictionary, target := "") -> Dictionary:
	var release := verify_envelope(envelope, identity)
	if release.has("error"):
		return release
	if release.get("schema") != 1 and not package_manifest(release):
		return {"error": "The update format is unsupported."}
	if not valid_commit(release.get("commit")) or release.get("platform") != identity.get("platform"):
		return {"error": "The release is for a different client."}
	if target != "" and release.commit != target:
		return {"error": "The release does not match the server's client commit."}
	if package_manifest(release):
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

static func move_file(source: String, target: String) -> Error:
	# Moves a verified file, such as an online setup download leaving its {tmp}
	# for the update cache (tools/install_client_payload.gd, HOOK-B8). On one
	# volume a rename keeps a single copy on disk; across volumes, or when the
	# rename fails, it copies and then removes the source. A linked source is
	# copied, never moved, so the cache holds a plain file. The caller checks
	# the target's size and SHA-256 again before using it. Godot's Windows
	# rename deletes an existing target first, so a missing source must never
	# reach it.
	if not FileAccess.file_exists(source):
		return ERR_FILE_NOT_FOUND
	if not is_link(source) and DirAccess.rename_absolute(source, target) == OK:
		return OK
	var error := DirAccess.copy_absolute(source, target)
	if error == OK and not is_link(source):
		DirAccess.remove_absolute(source)
	return error

static func remove_tree(path: String, stop := Callable()) -> Error:
	# Never follow a symlink/junction out of an updater-owned directory.
	# An optional stop callable runs before each file and can end the removal.
	if is_link(path) or not DirAccess.dir_exists_absolute(path):
		return DirAccess.remove_absolute(path) if FileAccess.file_exists(path) or is_link(path) else OK
	var directory := DirAccess.open(path)
	if directory == null:
		return ERR_CANT_OPEN
	directory.include_hidden = true
	for name: String in directory.get_files():
		if stop.is_valid() and stop.call():
			return ERR_SKIP
		var error := DirAccess.remove_absolute(path.path_join(name))
		if error != OK:
			return error
	for name: String in directory.get_directories():
		var error := remove_tree(path.path_join(name), stop)
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
	# A per-file transaction is undone first; the legacy two-root journal and
	# .eloria-previous stay readable for installs interrupted by older updaters.
	var operations := root.path_join(JOURNAL_V2)
	if FileAccess.file_exists(operations):
		var undone := _recover_operations(root, read_json(operations))
		if undone != "":
			return undone
	elif DirAccess.dir_exists_absolute(root.path_join(BACKUP_V2)) or is_link(root.path_join(BACKUP_V2)):
		# The commit point clears the journal before this backup, so a backup
		# without its journal holds only the files a finished update replaced.
		remove_tree(root.path_join(BACKUP_V2))
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

static func remove_backup(root: String, checkpoint := Callable()) -> Error:
	# recover() is the only reader of the previous installation, and only while
	# a journal exists. Every update empties it before writing a new journal,
	# so once the journal is gone it can be removed in any order or in parts.
	# The caller holds the installation lock and has seen the new game start.
	var journal := root.path_join(".eloria-update-journal.json")
	var backup := root.path_join(".eloria-previous")
	if FileAccess.file_exists(journal) or is_link(backup):
		return ERR_BUSY
	return remove_tree(backup, func() -> bool:
		return FileAccess.file_exists(journal) or (checkpoint.is_valid() and checkpoint.call()))

static func _rename_for_install(source: String, destination: String) -> Error:
	var error := DirAccess.rename_absolute(source, destination)
	# Windows scanners and closing processes can briefly retain folder handles
	# after the game exits. Keep the journal active while waiting, and never
	# overwrite or delete either folder to get around a failed rename.
	if OS.get_name() == "Windows":
		for attempt in 20:
			if error == OK:
				break
			OS.delay_msec(250)
			error = DirAccess.rename_absolute(source, destination)
	return error

static func _promotion_failed(root: String, source: String, destination: String, error: Error) -> String:
	var report := {"timestamp_utc": Time.get_datetime_string_from_system(true),
		"commit": read_json(root.path_join(".eloria-update-journal.json")).get("commit", read_json(root.path_join(JOURNAL_V2)).get("commit", "")),
		"source": source, "destination": destination,
		"error_code": int(error), "error": error_string(error), "recovery_error": "Recovery pending"}
	var report_path := cache_for(root).path_join("last-install-error.json")
	# Record the failed operation before recovery can change the folder layout.
	DirAccess.make_dir_recursive_absolute(cache_for(root))
	save_json(report_path, report)
	var recovery := recover(root)
	report.recovery_error = recovery
	var saved := save_json(report_path, report)
	var message := "The update could not be installed; the previous game was restored." if recovery == "" else recovery
	message += "\nCould not move \"%s\" to \"%s\" (%s, error %d)." % [source, destination, error_string(error), int(error)]
	message += "\nClose Rabbit Lands and other programs using its game folder, then run the updater again."
	if saved == OK:
		message += "\nError report: " + report_path
	return message

static func promote_staged(root: String, progress := Callable()) -> String:
	# Both update formats create the recovery journal before entering here.
	var stage := root.path_join(".eloria-update-stage")
	var backup := root.path_join(".eloria-previous")
	report_progress(progress, "Installing verified game files", 0, ROOTS.size())
	for name: String in ROOTS:
		var current := root.path_join(name)
		var previous := backup.path_join(name)
		if DirAccess.dir_exists_absolute(current):
			var error := _rename_for_install(current, previous)
			if error != OK:
				return _promotion_failed(root, current, previous, error)
		var staged := stage.path_join(name)
		var error := _rename_for_install(staged, current)
		if error != OK:
			return _promotion_failed(root, staged, current, error)
		report_progress(progress, "Installing verified game files", ROOTS.find(name) + 1, ROOTS.size())
	return ""

static func linked_path(root: String, relative: String, directories: Dictionary = {}) -> bool:
	var path := root
	var components := relative.split("/")
	for index in components.size():
		path = path.path_join(components[index])
		# Share ancestor checks only within one scan. Always inspect the leaf,
		# and start with a fresh cache when validating the completed stage.
		if index == components.size() - 1:
			if is_link(path):
				return true
		elif not directories.has(path):
			directories[path] = is_link(path)
		if directories.get(path, false):
			return true
	return false

static func valid_operations(record: Dictionary) -> bool:
	if record.get("schema") != 2 or not valid_commit(record.get("commit")) or record.get("stage") != STAGE or record.get("backup") != BACKUP_V2:
		return false
	if not record.get("operations") is Array or not record.get("directories", []) is Array:
		return false
	var seen: Dictionary = {}
	for operation: Variant in record.operations:
		if not operation is Dictionary or not operation.get("op") in OPERATION_KINDS or not safe_path(operation.get("path")):
			return false
		if operation.has("sha256") and not valid_hash(operation.sha256):
			return false
		# "from" is the installed spelling of a file whose name changes case.
		var original: Variant = operation.get("from", operation.path)
		if not safe_path(original) or str(original).to_lower() != str(operation.path).to_lower() or seen.has(original) or seen.has(operation.path):
			return false
		seen[original] = true
		seen[operation.path] = true
	for directory: Variant in record.get("directories", []):
		if not directory is String or not (directory in ROOTS or safe_path(directory)):
			return false
	return true

static func apply_operations(root: String, journal: Dictionary, progress := Callable()) -> String:
	# Each live change is a rename recorded in the journal before it happens:
	# replace = live -> backup, then stage -> live; add = stage -> live;
	# retire = live -> backup. recover() undoes them in reverse order, so a
	# crash after any rename restores the previous files byte for byte.
	if not valid_operations(journal):
		return "The update operations are invalid."
	var stage := root.path_join(STAGE)
	var backup := root.path_join(BACKUP_V2)
	if is_link(stage) or is_link(backup):
		return "The update folders must not be links."
	if remove_tree(backup) != OK:
		return "The previous update backup cannot be replaced."
	if save_json(root.path_join(JOURNAL_V2), journal) != OK:
		return "The update recovery record cannot be saved."
	var total := 0
	for operation: Dictionary in journal.operations:
		total += 2 if operation.op == "replace" else 1
	var done := 0
	var live_links: Dictionary = {}
	report_progress(progress, INSTALL_PHASE, done, total)
	for operation: Dictionary in journal.operations:
		var path: String = operation.path
		var original: String = operation.get("from", path)
		# Never move through a linked folder. A linked file itself moves as a
		# link (rename does not follow it), like the two-root promotion.
		if linked_path(root, original.get_base_dir(), live_links) or linked_path(root, path.get_base_dir(), live_links):
			return _promotion_failed(root, root.path_join(original), root.path_join(path), ERR_LINK_FAILED)
		if operation.op != "add":
			var moved := _move(root.path_join(original), backup.path_join(original))
			if moved != OK:
				return _promotion_failed(root, root.path_join(original), backup.path_join(original), moved)
			done += 1
			report_progress(progress, INSTALL_PHASE, done, total)
		if operation.op != "retire":
			var placed := _move(stage.path_join(path), root.path_join(path))
			if placed != OK:
				return _promotion_failed(root, stage.path_join(path), root.path_join(path), placed)
			done += 1
			report_progress(progress, INSTALL_PHASE, done, total)
	return ""

static func commit_operations(root: String, journal: Dictionary) -> String:
	# The journal goes first. Afterwards the backup holds only originals that
	# nothing reads, and recover() deletes one left by a crash at this point.
	if DirAccess.remove_absolute(root.path_join(JOURNAL_V2)) != OK:
		return "The update recovery record could not be cleared. Restart the updater."
	remove_tree(root.path_join(BACKUP_V2))
	remove_tree(root.path_join(STAGE))
	for operation: Dictionary in journal.operations:
		if operation.op == "retire":
			_prune_empty_parents(root, operation.path)
	return ""

static func _recover_operations(root: String, record: Dictionary) -> String:
	var stage := root.path_join(STAGE)
	var backup := root.path_join(BACKUP_V2)
	if is_link(stage) or is_link(backup):
		return "The update recovery folder must not be a link."
	if not valid_operations(record):
		return _recover_from_backup(root)
	var live_links: Dictionary = {}
	var operations: Array = record.operations
	for index in range(operations.size() - 1, -1, -1):
		var operation: Dictionary = operations[index]
		var path: String = operation.path
		var original: String = operation.get("from", path)
		if linked_path(root, path.get_base_dir(), live_links) or linked_path(root, original.get_base_dir(), live_links):
			return "The game recovery folders must not be links."
		var live := root.path_join(path)
		var error := OK
		if operation.op == "add":
			if _file_present(live):
				error = _move(live, stage.path_join(path))
		elif _file_present(backup.path_join(original)):
			# The original was moved, so a live file at this path is the new
			# one. Park it in the stage (never delete) and put the original back.
			if operation.op == "replace" and _file_present(live):
				error = _move(live, stage.path_join(path))
			if error == OK:
				error = _move(backup.path_join(original), root.path_join(original))
		if error != OK:
			return "Close all running Rabbit Lands windows and restart the launcher to finish recovery."
	# Remove folders the transaction created, deepest first, once empty again.
	var created: Array = record.get("directories", []).duplicate()
	created.sort_custom(func(a: String, b: String) -> bool: return a.length() > b.length())
	for directory: String in created:
		var path := root.path_join(directory)
		if DirAccess.dir_exists_absolute(path) and not is_link(path) and not _contains_files(path):
			remove_tree(path)
	if DirAccess.remove_absolute(root.path_join(JOURNAL_V2)) != OK:
		return "Close all running Rabbit Lands windows and restart the launcher to finish recovery."
	remove_tree(backup)
	remove_tree(stage)
	return ""

static func _recover_from_backup(root: String) -> String:
	# The journal exists but cannot be read. A power cut can lose a new file's
	# bytes yet keep the renames made after it, and setup recovers through the
	# same call, so refusing here would leave no way back. apply_operations()
	# empties the backup before it writes the journal, so the backup holds
	# exactly the originals this transaction moved: put every one back. What
	# occupies its place was put there by this transaction and is parked in the
	# stage. Added files stay; install() plans again after any recovery and
	# hashes every installed file, so the next update retires or keeps them.
	var stage := root.path_join(STAGE)
	var backup := root.path_join(BACKUP_V2)
	var originals: Array = []
	if not _backup_files(backup, "", originals):
		return "The interrupted update's recovery folder cannot be read. Close other programs using the game folder and restart the launcher."
	# The stage holds only unpacked copies of cached packages and parked files.
	if remove_tree(stage) != OK:
		return "Close all running Rabbit Lands windows and restart the launcher to finish recovery."
	var live_links: Dictionary = {}
	for relative: String in originals:
		# Only safe game paths are ever moved into the backup; anything else in
		# it was never live and goes with the backup below.
		if not safe_path(relative):
			continue
		if linked_path(root, relative.get_base_dir(), live_links):
			return "The game recovery folders must not be links."
		var error := _clear_for_original(root, stage, relative)
		if error == OK:
			error = _move(backup.path_join(relative), root.path_join(relative))
		if error != OK:
			return "Close all running Rabbit Lands windows and restart the launcher to finish recovery."
	if DirAccess.remove_absolute(root.path_join(JOURNAL_V2)) != OK:
		return "Close all running Rabbit Lands windows and restart the launcher to finish recovery."
	remove_tree(backup)
	remove_tree(stage)
	return ""

static func _backup_files(path: String, relative: String, files: Array) -> bool:
	# Files (and file links) under the backup as game-relative paths. Only files
	# are ever moved into it, so a folder link there is refused.
	if not DirAccess.dir_exists_absolute(path):
		return true
	var directory := DirAccess.open(path)
	if directory == null:
		return false
	directory.include_hidden = true
	for name: String in directory.get_files():
		files.append(name if relative == "" else relative + "/" + name)
	for name: String in directory.get_directories():
		if directory.is_link(name) or not _backup_files(path.path_join(name), name if relative == "" else relative + "/" + name, files):
			return false
	return true

static func _clear_for_original(root: String, stage: String, relative: String) -> Error:
	# Before this transaction a folder stood on the way to relative and a file
	# at it. So a file at a folder on the way, or anything but an empty folder
	# at relative itself, was placed by this transaction: park it in the stage.
	var components := relative.split("/")
	for depth in range(2, components.size() + 1):
		var part := "/".join(components.slice(0, depth))
		var path := root.path_join(part)
		var occupied := FileAccess.file_exists(path) or is_link(path)
		if depth == components.size() and not occupied:
			occupied = DirAccess.dir_exists_absolute(path) and _contains_files(path)
		if occupied:
			var target := stage.path_join(part)
			var parent := DirAccess.make_dir_recursive_absolute(target.get_base_dir())
			if parent != OK:
				return parent
			var parked := _rename_for_install(path, target)
			if parked != OK:
				return parked
	return OK

static func _file_present(path: String) -> bool:
	return FileAccess.file_exists(path) or is_link(path)

static func _contains_files(path: String) -> bool:
	if is_link(path):
		return true
	var directory := DirAccess.open(path)
	if directory == null:
		return true
	directory.include_hidden = true
	if not directory.get_files().is_empty():
		return true
	for name: String in directory.get_directories():
		if _contains_files(path.path_join(name)):
			return true
	return false

static func _move(source: String, destination: String) -> Error:
	# Only files move. An empty folder where a file now belongs (a folder that
	# became a file in this release, or the reverse during rollback) is removed
	# first; a folder that still holds files is never replaced.
	if DirAccess.dir_exists_absolute(destination) and not is_link(destination):
		if _contains_files(destination):
			return ERR_ALREADY_EXISTS
		var cleared := remove_tree(destination)
		if cleared != OK:
			return cleared
	var parent := DirAccess.make_dir_recursive_absolute(destination.get_base_dir())
	if parent != OK:
		return parent
	return _rename_for_install(source, destination)

static func _prune_empty_parents(root: String, relative: String) -> void:
	# Remove folders a retired file leaves empty, never a game root itself.
	var components := relative.split("/")
	for depth in range(components.size() - 1, 1, -1):
		var path := root.path_join("/".join(components.slice(0, depth)))
		var listing := DirAccess.open(path) if not is_link(path) else null
		if listing == null:
			return
		listing.include_hidden = true
		if not listing.get_files().is_empty() or not listing.get_directories().is_empty() or DirAccess.remove_absolute(path) != OK:
			return

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
	# A download prepared earlier never replaces a newer installed release.
	# Setup (repair) installs exactly the release it carries.
	if not repair and downgrade_error(release, installed_sequence(root, read_json(root.path_join("app/client-release.json")).get("commit"))) != "":
		DirAccess.remove_absolute(cache.path_join("pending.json"))
		return ""
	if package_manifest(release):
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
	if remove_tree(backup) != OK or DirAccess.make_dir_recursive_absolute(backup) != OK:
		return "The previous update backup cannot be replaced."
	var journal := root.path_join(".eloria-update-journal.json")
	if save_json(journal, {"commit": release.commit}) != OK:
		return "The update recovery record cannot be saved."
	error = promote_staged(root, progress)
	if error != "":
		return error
	# Clear the journal before marking the download consumed. A crash before
	# this point rolls the folders back together on the following launch.
	if DirAccess.remove_absolute(journal) != OK:
		return recover(root)
	DirAccess.remove_absolute(cache.path_join("pending.json"))
	DirAccess.remove_absolute(cache.path_join("release.zip"))
	remove_tree(stage)
	return ""

extends SceneTree
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")
const Download = preload("res://src/updates/package_download.gd")
# The shipped base. Only fixture projects replace it, in their own copies.
const PRODUCTION_ASSETS := "https://assets.rabbitlandsgame.com/desktop/v1/"
var _failures := 0
var _key: CryptoKey
var _root := ""
var _identity: Dictionary

func expect(value: bool, message: String) -> void:
	if not value:
		_failures += 1
		push_error(message)

func write(path: String, text: String) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()

func envelope(payload: Dictionary) -> Dictionary:
	var bytes := JSON.stringify(payload).to_utf8_buffer()
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return {"payload": Marshalls.raw_to_base64(bytes), "signature": Marshalls.raw_to_base64(Crypto.new().sign(HashingContext.HASH_SHA256, hash.finish(), _key))}

func make_download(commit: String, entries := {}) -> Dictionary:
	var descriptor := _identity.duplicate(true)
	descriptor.commit = commit
	descriptor.ancestors = [commit]
	var files: Dictionary = {"app/RabbitLands.exe": "new exe", "app/RabbitLands.pck": "new pck",
		"app/client-release.json": JSON.stringify(descriptor), "eloria-assets/map.json": "new map"}
	files.merge(entries, true)
	var cache := Release.cache_for(_root)
	DirAccess.make_dir_recursive_absolute(cache)
	var zip := ZIPPacker.new()
	zip.open(cache.path_join("release.zip"))
	var inventory: Array = []
	var total := 0
	for path: String in files:
		var bytes: PackedByteArray = str(files[path]).to_utf8_buffer()
		var index := inventory.size()
		inventory.append({"path": path, "size": bytes.size(), "sha256": str(files[path]).sha256_text()})
		zip.start_file("files/%06d/%06d" % [index, 0])
		zip.write_file(bytes)
		zip.close_file()
		total += bytes.size()
	zip.start_file("inventory.json")
	zip.write_file(JSON.stringify(inventory).to_utf8_buffer())
	zip.close_file()
	zip.close()
	var archive := cache.path_join("release.zip")
	var file := FileAccess.open(archive, FileAccess.READ)
	var size := file.get_length()
	file.close()
	var payload := {"schema": 1, "commit": commit, "platform": "windows", "size": size,
		"unpacked_size": total, "sha256": FileAccess.get_sha256(archive),
		"parts": [{"url": "https://github.com/o/r/releases/download/t/a.001", "size": size, "sha256": FileAccess.get_sha256(archive)}]}
	var signed := envelope(payload)
	Release.save_json(cache.path_join("pending.json"), signed)
	return signed

func old_install() -> void:
	Release.remove_tree(_root)
	write(_root.path_join("app/RabbitLands.exe"), "old exe")
	write(_root.path_join("app/RabbitLands.pck"), "old pck")
	write(_root.path_join("app/client-release.json"), JSON.stringify(_identity))
	write(_root.path_join("eloria-assets/map.json"), "old map")

func read(relative: String) -> String:
	return FileAccess.get_file_as_string(_root.path_join(relative))

func present(relative: String) -> bool:
	return FileAccess.file_exists(_root.path_join(relative)) or DirAccess.dir_exists_absolute(_root.path_join(relative))

func per_file_journal(commit: String) -> Dictionary:
	# Retire a map file and a lone file in its own folder, replace the
	# executable, add a file in a new folder.
	var stage := _root.path_join(Release.STAGE)
	write(stage.path_join("app/RabbitLands.exe"), "new exe")
	write(stage.path_join("app/added/new.txt"), "added")
	return {"schema": 2, "commit": commit, "stage": Release.STAGE, "backup": Release.BACKUP_V2,
		"operations": [{"path": "eloria-assets/map.json", "op": "retire"}, {"path": "app/lone/only.txt", "op": "retire"},
			{"path": "app/RabbitLands.exe", "op": "replace", "sha256": "new exe".sha256_text()},
			{"path": "app/added/new.txt", "op": "add", "sha256": "added".sha256_text()}],
		"directories": ["app/added"]}

func check_per_file_operations() -> void:
	var b := "b".repeat(40)
	var good := per_file_journal(b)
	var bad_records: Array = []
	for change: Dictionary in [{"schema": 1}, {"commit": "short"}, {"stage": "elsewhere"}, {"backup": ".eloria-previous"},
			{"operations": [{"path": "app/../x", "op": "add"}]}, {"operations": [{"path": "app/x", "op": "copy"}]},
			{"operations": [{"path": "app/X", "op": "replace", "from": "app/y"}]},
			{"operations": [{"path": "app/x", "op": "add"}, {"path": "app/x", "op": "retire"}]},
			{"directories": ["../outside"]}]:
		var record := good.duplicate(true)
		record.merge(change, true)
		bad_records.append(record)
	expect(Release.valid_operations(good), "a valid per-file journal was refused")
	for record: Dictionary in bad_records:
		expect(not Release.valid_operations(record), "an unsafe per-file journal was accepted: %s" % [record])
		expect(Release.apply_operations(_root, record) != "", "an unsafe per-file journal was applied")
	# Applied, then interrupted before the commit point: every original returns,
	# the new files are parked in the stage, and created folders go away.
	old_install()
	write(_root.path_join("app/lone/only.txt"), "lone")
	var journal := per_file_journal(b)
	expect(Release.apply_operations(_root, journal) == "", "per-file operations failed")
	expect(read("app/RabbitLands.exe") == "new exe" and read("app/added/new.txt") == "added", "per-file operations did not place new files")
	expect(not present("eloria-assets/map.json") and not present("app/lone/only.txt"), "per-file operations did not retire files")
	expect(read(Release.BACKUP_V2 + "/app/RabbitLands.exe") == "old exe", "the replaced original is not in the per-update backup")
	expect(FileAccess.file_exists(_root.path_join(Release.JOURNAL_V2)), "per-file operations ran without a journal")
	expect(Release.remove_backup(_root) == OK, "the legacy backup cleanup refused an update without a legacy journal")
	expect(Release.recover(_root) == "", "an interrupted per-file update could not recover")
	expect(read("app/RabbitLands.exe") == "old exe" and read("eloria-assets/map.json") == "old map" and read("app/lone/only.txt") == "lone", "recovery did not restore the originals")
	expect(not present("app/added"), "recovery kept a folder the update created")
	for name: String in [Release.JOURNAL_V2, Release.BACKUP_V2, Release.STAGE]:
		expect(not present(name), "recovery left " + name)
	# Applied and committed: no backup is kept and emptied folders are removed.
	journal = per_file_journal(b)
	expect(Release.apply_operations(_root, journal) == "" and Release.commit_operations(_root, journal) == "", "per-file operations could not be committed")
	expect(read("app/RabbitLands.exe") == "new exe" and not present("app/lone") and present("app"), "the commit did not finish the update")
	for name: String in [Release.JOURNAL_V2, Release.BACKUP_V2, Release.STAGE, ".eloria-previous"]:
		expect(not present(name), "the commit left " + name)
	expect(Release.recover(_root) == "" and read("app/RabbitLands.exe") == "new exe", "recovery after a commit changed the game")
	# A crash after the commit cleared its journal leaves a backup nothing reads.
	write(_root.path_join(Release.BACKUP_V2 + "/app/RabbitLands.exe"), "old exe")
	expect(Release.recover(_root) == "" and not present(Release.BACKUP_V2), "a backup without its journal was kept")
	expect(read("app/RabbitLands.exe") == "new exe", "removing a stale backup changed the game")
	# A journal that lost its bytes (a power cut can keep the renames made
	# after it) is never applied. Every original in the backup returns, a new
	# file in its place is parked, and an added file stays for the next plan.
	old_install()
	write(_root.path_join("app/lone/only.txt"), "lone")
	journal = per_file_journal(b)
	expect(Release.apply_operations(_root, journal) == "", "per-file operations failed before the journal was lost")
	var lost := FileAccess.open(_root.path_join(Release.JOURNAL_V2), FileAccess.WRITE)
	var zeros := PackedByteArray()
	zeros.resize(256)
	lost.store_buffer(zeros)
	lost.close()
	expect(Release.recover(_root) == "", "a journal that lost its bytes blocked recovery")
	expect(read("app/RabbitLands.exe") == "old exe" and read("eloria-assets/map.json") == "old map" and read("app/lone/only.txt") == "lone", "a lost journal did not bring every original back")
	expect(read("app/added/new.txt") == "added", "a lost journal's added file was not left for the next plan")
	for name: String in [Release.JOURNAL_V2, Release.BACKUP_V2, Release.STAGE]:
		expect(not present(name), "recovery without a readable journal left " + name)
	# Damaged JSON is handled the same way; an empty backup changes nothing.
	write(_root.path_join(Release.JOURNAL_V2), "{damaged")
	expect(Release.recover(_root) == "" and read("app/RabbitLands.exe") == "old exe" and not present(Release.JOURNAL_V2), "a damaged journal without a backup changed the game")
	var free := Packages.space_left(_root)
	expect(free > 0 and Packages.space_left(_root.path_join("missing/child")) > 0, "free disk space could not be read")

func reference_inspect(root: String, release: Dictionary) -> Dictionary:
	# The one-thread scan this updater shipped before FIX-UD, kept as the
	# oracle: per member, a leaf/ancestor link check, then size + SHA-256.
	var installed: Dictionary = {}
	var linked := [false]
	var walk := func(walk: Callable, relative: String) -> void:
		var directory := DirAccess.open(root.path_join(relative))
		if directory == null:
			return
		directory.include_hidden = true
		for name: String in directory.get_files():
			installed[relative + "/" + name] = true
		for name: String in directory.get_directories():
			if directory.is_link(name):
				linked[0] = true
			else:
				walk.call(walk, relative + "/" + name)
	for name: String in Release.ROOTS:
		if Release.is_link(root.path_join(name)):
			linked[0] = true
		elif DirAccess.dir_exists_absolute(root.path_join(name)):
			walk.call(walk, name)
	var folded := OS.get_name() == "Windows"
	var spelled: Dictionary = {}
	for path: String in installed:
		spelled[path.to_lower()] = path
	var claimed: Dictionary = {}
	var directories: Dictionary = {}
	var plan := {"needed": [], "unchanged": {}, "changed": {}, "snapshot": {}, "renamed": {}, "retire": [], "linked": false}
	for package: Dictionary in release.packages:
		var members: Array = []
		for index in package.files.size():
			var entry: Dictionary = package.files[index]
			var path: String = entry.path
			var key := path.to_lower() if folded else path
			var actual: String = spelled.get(key, "") if folded else (path if installed.has(path) else "")
			claimed[key] = true
			if actual != "" and actual.get_file() != path.get_file():
				plan.renamed[path] = actual
				members.append(index)
			elif actual == "" or Release.linked_path(root, path, directories) or FileAccess.get_sha256(root.path_join(path)) != entry.sha256 or FileAccess.get_size(root.path_join(path)) != int(entry.size):
				members.append(index)
			else:
				plan.snapshot[path] = [int(entry.size), FileAccess.get_modified_time(root.path_join(path)), entry.sha256]
		plan.unchanged[package.id] = members.is_empty()
		if not members.is_empty():
			plan.changed[package.id] = members
			plan.needed.append(package.id)
	for path: String in installed:
		if not claimed.has(path.to_lower() if folded else path):
			plan.retire.append(path)
	plan.linked = linked[0]
	return plan

func plan_of(checked: Packages.CheckedPlan) -> Dictionary:
	var needed: Array = []
	for package: Dictionary in checked.needed:
		needed.append(package.id)
	return {"needed": needed, "unchanged": checked.unchanged, "changed": checked.changed, "snapshot": checked.snapshot,
		"renamed": checked.renamed, "retire": checked.retire, "linked": checked.linked}

func write_bytes(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()

func check_parallel_scan() -> void:
	# The threaded scan must make exactly the plan of the one-thread scan:
	# same packages, members, snapshot (size, time, hash), renames, retirements.
	var root := _root + "-scan"
	Release.remove_tree(root)
	var packages: Array = []
	var inventory: Dictionary = {}
	var noise := RandomNumberGenerator.new()
	noise.seed = 42
	var empty_sha := "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
	for package_index in 24:
		var files: Array = []
		for index in 12:
			var path := "%s/pack-%02d/file-%02d.bin" % [Release.ROOTS[package_index % 2], package_index, index]
			var bytes := PackedByteArray()
			bytes.resize(noise.randi_range(1, 3000))
			for at in bytes.size():
				bytes[at] = noise.randi() % 256
			write_bytes(root.path_join(path), bytes)
			var digest := HashingContext.new()
			digest.start(HashingContext.HASH_SHA256)
			digest.update(bytes)
			files.append({"path": path, "size": bytes.size(), "sha256": digest.finish().hex_encode()})
			inventory[path] = bytes
		packages.append({"id": "pack-%02d" % package_index, "files": files})
	# Two large files, hashed first and largest first.
	for name: String in ["app/RabbitLands.pck", "eloria-assets/maps/large.glb"]:
		var large := PackedByteArray()
		large.resize(Packages.SCAN_LARGE_BYTES + (4096 if name.ends_with(".pck") else 0))
		large.fill(7 if name.ends_with(".pck") else 9)
		write_bytes(root.path_join(name), large)
		var digest := HashingContext.new()
		digest.start(HashingContext.HASH_SHA256)
		digest.update(large)
		packages[0].files.append({"path": name, "size": large.size(), "sha256": digest.finish().hex_encode()})
	var release := {"packages": packages}
	# Unchanged files, plus: damaged at the same size, resized, missing, renamed
	# in case (Windows), not listed, a large file damaged at the same size, an
	# empty file that matches and an empty file that should have bytes.
	var damaged: String = packages[3].files[2].path
	var flipped: PackedByteArray = inventory[damaged].duplicate()
	flipped[0] = (flipped[0] + 1) % 256
	write_bytes(root.path_join(damaged), flipped)
	write_bytes(root.path_join(packages[5].files[0].path), PackedByteArray([1, 2, 3]))
	DirAccess.remove_absolute(root.path_join(packages[7].files[4].path))
	var renamed_path: String = packages[9].files[1].path
	if OS.get_name() == "Windows":
		DirAccess.rename_absolute(root.path_join(renamed_path), root.path_join(renamed_path.get_base_dir().path_join(renamed_path.get_file().to_upper())))
	write(root.path_join("app/pack-10/extra-not-listed.txt"), "retire me")
	var resaved := PackedByteArray()
	resaved.resize(Packages.SCAN_LARGE_BYTES)
	resaved.fill(8)
	write_bytes(root.path_join("eloria-assets/maps/large.glb"), resaved)
	packages[11].files.append({"path": "app/pack-11/empty.bin", "size": 0, "sha256": empty_sha})
	write_bytes(root.path_join("app/pack-11/empty.bin"), PackedByteArray())
	packages[12].files.append({"path": "eloria-assets/pack-12/now-empty.bin", "size": 5, "sha256": "fives".sha256_text()})
	write_bytes(root.path_join("eloria-assets/pack-12/now-empty.bin"), PackedByteArray())
	var reference := reference_inspect(root, release)
	var phases: Array = []
	var progress := func(phase: String, completed: int, total: int, _detail := "") -> void:
		phases.append([phase, completed, total])
	for threads: int in [1, 2, 4, 9]:
		phases.clear()
		var checked := Packages.inspect(root, release, progress, threads)
		var plan := plan_of(checked)
		expect(JSON.stringify(plan, "", true) == JSON.stringify(reference, "", true), "a %d-thread scan made another plan:\n%s\nreference:\n%s" % [threads, plan, reference])
		var zeros := 0
		var last := -1
		var ordered := true
		for row: Array in phases:
			expect(row[0] == "Checking installed packages", "the scan reported another phase: %s" % [row])
			zeros += 1 if row[1] == 0 else 0
			ordered = ordered and int(row[1]) >= last and int(row[1]) <= int(row[2])
			last = row[1]
		expect(zeros == 1 and ordered and not phases.is_empty() and phases[-1][1] == phases[-1][2], "%d-thread scan progress is not 0 once, rising, then complete: %s" % [threads, phases])
	var expected_needed := ["pack-00", "pack-03", "pack-05", "pack-07", "pack-12"]
	if OS.get_name() == "Windows":
		expected_needed.insert(4, "pack-09")
	expect(reference.needed == expected_needed and reference.retire == ["app/pack-10/extra-not-listed.txt"] and reference.snapshot.has("app/pack-11/empty.bin") and reference.snapshot.has("app/RabbitLands.pck"), "the scan fixture lost a case: %s" % [reference])
	# A folder link inside the roots is noted and never followed (Windows junction).
	if OS.get_name() == "Windows":
		var target := root + "-outside"
		write(target.path_join("x.bin"), "outside")
		var output: Array = []
		if OS.execute("cmd.exe", ["/c", "mklink", "/J", root.path_join("app/linked").replace("/", "\\"), target.replace("/", "\\")], output) == 0:
			packages[1].files.append({"path": "app/linked/x.bin", "size": 7, "sha256": "outside".sha256_text()})
			reference = reference_inspect(root, release)
			var checked := Packages.inspect(root, release, Callable(), 4)
			expect(checked.linked and reference.linked and JSON.stringify(plan_of(checked), "", true) == JSON.stringify(reference, "", true), "a linked folder changed the threaded plan")
			expect(checked.changed.get("pack-01", []).has(packages[1].files.size() - 1), "a file behind a folder link was trusted")
			DirAccess.remove_absolute(root.path_join("app/linked"))
		Release.remove_tree(target)
	# A file link to the right bytes is replaced, never hashed through. Making a
	# file link needs Developer Mode or elevation on Windows; skip it otherwise.
	var member: String = packages[2].files[3].path
	var outside := root + "-outside-file"
	DirAccess.make_dir_recursive_absolute(outside)
	DirAccess.rename_absolute(root.path_join(member), outside.path_join("real.bin"))
	var made := -1
	if OS.get_name() == "Windows":
		made = OS.execute("cmd.exe", ["/c", "mklink", root.path_join(member).replace("/", "\\"), outside.path_join("real.bin").replace("/", "\\")], [])
	else:
		made = OS.execute("ln", ["-s", outside.path_join("real.bin"), root.path_join(member)], [])
	if made == 0 and Release.is_link(root.path_join(member)):
		reference = reference_inspect(root, release)
		var checked := Packages.inspect(root, release, Callable(), 4)
		expect(checked.changed.get("pack-02", []).has(3) and reference.changed.get("pack-02", []).has(3) and JSON.stringify(plan_of(checked), "", true) == JSON.stringify(reference, "", true), "a file link was hashed through")
		DirAccess.remove_absolute(root.path_join(member))
	else:
		print("SKIP: file links cannot be created here; the file-link scan case did not run.")
		DirAccess.rename_absolute(outside.path_join("real.bin"), root.path_join(member))
	Release.remove_tree(outside)
	# The thread count: auto by default, one restores the sequential scan.
	OS.set_environment("RABBITLANDS_UPDATE_SCAN_THREADS", "1")
	expect(Packages.scan_threads() == 1, "RABBITLANDS_UPDATE_SCAN_THREADS=1 was ignored")
	OS.set_environment("RABBITLANDS_UPDATE_SCAN_THREADS", "99")
	expect(Packages.scan_threads() == Packages.SCAN_THREADS_LIMIT, "the scan thread override is not bounded")
	OS.set_environment("RABBITLANDS_UPDATE_SCAN_THREADS", "many")
	var automatic := clampi(OS.get_processor_count() - 1, 1, Packages.SCAN_THREADS_DEFAULT)
	expect(Packages.scan_threads() == automatic, "an invalid scan thread override was used")
	OS.unset_environment("RABBITLANDS_UPDATE_SCAN_THREADS")
	expect(Packages.scan_threads() == automatic, "the automatic scan thread count changed")
	# The scan's file check: size first, then SHA-256 of the whole file.
	var probe := root.path_join("probe.bin")
	write(probe, "check me")
	expect(Release.check_file(probe, 8, "check me".sha256_text()), "check_file refused a matching file")
	expect(not Release.check_file(probe, 7, "check me".sha256_text()) and not Release.check_file(probe, 8, "check mE".sha256_text()), "check_file accepted a wrong size or hash")
	expect(not Release.check_file(root.path_join("missing.bin"), 0, empty_sha) and not Release.check_file(root, 0, empty_sha), "check_file accepted a missing file or a folder")
	Release.remove_tree(root)

func codec_release(schema: int, row_extra: Dictionary) -> Dictionary:
	# The smallest package manifest validate() accepts, with row_extra merged
	# into its one inventory row.
	var commit := "b".repeat(40)
	var version := "RabbitLands-Windows-20261104-bbbbbbbbb"
	var base := "https://github.com/o/r/releases/download/client-%s/" % commit
	var digest := "c".repeat(64)
	var row := {"path": "app/RabbitLands.pck", "size": 10, "sha256": digest}
	row.merge(row_extra, true)
	var part := {"url": base + version + ".pkg.client.zip.001", "size": 100, "sha256": digest}
	var package := {"id": "client", "sha256": digest, "size": 100, "unpacked_size": 10, "file_count": 1,
		"files": [row], "parts": [part]}
	return {"schema": schema, "bootstrap_schema": 1, "commit": commit, "platform": "windows", "repository": "o/r",
		"version": version, "packages": [package], "size": 100, "unpacked_size": 10, "file_count": 1,
		"parts": [part], "sha256": digest,
		"updater": {"url": base + version + "-updater.exe", "size": 5, "sha256": digest},
		"uninstall": {"url": base + version + "-uninstall.exe", "size": 5, "sha256": digest}}

func check_codec_schema() -> void:
	# Manifest schema 3 (W2-UD-05): the package reader, with zstd inventory rows.
	for schema: Variant in [2, 2.0, 3, 3.0]:
		expect(Release.package_manifest({"schema": schema}), "schema %s is not read as packages" % schema)
	for schema: Variant in [1, 1.0, 4, 3.5, "3", null]:
		expect(not Release.package_manifest({"schema": schema}), "schema %s was read as packages" % schema)
	expect(not Release.package_manifest({}), "a manifest without a schema was read as packages")
	var identity := {"repository": "o/r", "platform": "windows"}
	expect(not Packages.validate(codec_release(2, {}), identity).has("error"), "the schema 2 fixture is invalid")
	expect(not Packages.validate(codec_release(3, {}), identity).has("error"), "schema 3 without codecs was rejected")
	expect(not Packages.validate(codec_release(3, {"codec": "zstd"}), identity).has("error"), "a schema 3 zstd row was rejected")
	expect(Packages.validate(codec_release(2, {"codec": "zstd"}), identity).has("error"), "a codec was accepted under schema 2")
	for codec: Variant in ["ZSTD", "gzip", "", 1, null, ["zstd"]]:
		expect(Packages.validate(codec_release(3, {"codec": codec}), identity).has("error"), "codec %s was accepted" % str(codec))
	# Signed: JSON turns the schema into a float; verify_manifest dispatches it.
	var verified := Release.verify_manifest(envelope(codec_release(3, {"codec": "zstd"})), _identity)
	expect(not verified.has("error") and Release.package_manifest(verified), "a signed schema 3 manifest was rejected: %s" % verified.get("error", ""))
	expect(Release.verify_manifest(envelope(codec_release(2, {"codec": "zstd"})), _identity).has("error"), "a signed schema 2 codec row was accepted")
	expect(Release.verify_manifest(envelope(codec_release(4, {})), _identity).get("error", "") == "The update format is unsupported.", "a future schema was not refused")
	# Chunk frames: exact size or nothing; the caller rejects any other size.
	var plain := PackedByteArray()
	plain.resize(300000)
	for index in plain.size():
		plain[index] = (index * 7 + (index >> 10)) % 251
	var frame := plain.compress(FileAccess.COMPRESSION_ZSTD)
	expect(frame.size() < plain.size() and Packages.decode_chunk(frame, plain.size()) == plain, "a zstd chunk did not round-trip")
	expect(Packages.decode_chunk(frame, plain.size() - 1).is_empty(), "a frame larger than its chunk was decoded")
	expect(Packages.decode_chunk(frame, plain.size() + 1).size() == plain.size(), "a short frame did not come back short")
	var damaged := frame.duplicate()
	damaged[damaged.size() >> 1] = damaged[damaged.size() >> 1] ^ 0x55
	expect(Packages.decode_chunk(damaged, plain.size()) != plain, "a damaged frame decoded to the original bytes")
	expect(Packages.decode_chunk(frame.slice(0, frame.size() >> 1), plain.size()).is_empty(), "a truncated frame was decoded")
	expect(Packages.decode_chunk(plain, plain.size()).is_empty(), "raw bytes were decoded as a zstd frame")
	expect(Packages.decode_chunk(PackedByteArray(), 10).is_empty(), "an empty frame was decoded")
	var full := PackedByteArray()
	full.resize(Release.CHUNK_BYTES)
	full.fill(7)
	expect(Packages.decode_chunk(full.compress(FileAccess.COMPRESSION_ZSTD), Release.CHUNK_BYTES) == full, "a full 8 MiB chunk did not round-trip")

func r2_release(schema: int, packages: int, parts_per_package := 1) -> Dictionary:
	# A package manifest validate() accepts: `packages` one-file packages whose
	# parts all use the R2 form under the compiled base.
	var commit := "b".repeat(40)
	var version := "RabbitLands-Windows-20261104-bbbbbbbbb"
	var github := "https://github.com/o/r/releases/download/client-%s/" % commit
	var rows: Array = []
	var all_parts: Array = []
	for index in packages:
		var parts: Array = []
		for slice in parts_per_package:
			var digest := "a%063x" % (index * 16 + slice + 1)
			parts.append({"url": Release.DESKTOP_ASSETS + "parts/" + digest + ".bin", "size": 10, "sha256": digest})
		rows.append({"id": "p%05d" % index, "sha256": "c".repeat(64), "size": 10 * parts_per_package, "unpacked_size": 1,
			"file_count": 1, "files": [{"path": "app/p%05d.bin" % index, "size": 1, "sha256": "d".repeat(64)}], "parts": parts})
		all_parts.append_array(parts)
	return {"schema": schema, "bootstrap_schema": 1, "commit": commit, "platform": "windows", "repository": "o/r",
		"version": version, "packages": rows, "size": 10 * parts_per_package * packages, "unpacked_size": packages,
		"file_count": packages, "parts": all_parts, "sha256": "c".repeat(64),
		"updater": {"url": github + version + "-updater.exe", "size": 5, "sha256": "c".repeat(64)},
		"uninstall": {"url": github + version + "-uninstall.exe", "size": 5, "sha256": "c".repeat(64)}}

func with_part_url(release: Dictionary, url: String) -> Dictionary:
	# The first part of the first package, and its row in the release's part
	# list, moved to url.
	var changed := release.duplicate(true)
	changed.packages[0].parts[0].url = url
	changed.parts[0].url = url
	return changed

func check_r2_rows() -> void:
	# W1a: content parts may come from R2, only in the derived form under the
	# compiled base and only in schema 3. Helpers stay on GitHub.
	expect(Release.DESKTOP_ASSETS == PRODUCTION_ASSETS, "the shipped R2 base changed: " + Release.DESKTOP_ASSETS)
	var digest := "e".repeat(64)
	var good := {"url": PRODUCTION_ASSETS + "parts/" + digest + ".bin", "size": 1, "sha256": digest}
	expect(Release.r2_part(good), "the derived R2 part form was refused")
	var other := "f".repeat(64)
	var upper := "E".repeat(64)
	var refused := [PRODUCTION_ASSETS + "parts/" + other + ".bin", PRODUCTION_ASSETS.replace("https://", "http://") + "parts/" + digest + ".bin",
		"https://127.0.0.1:8443/desktop/v1/parts/" + digest + ".bin", "https://127.0.0.1/desktop/v1/parts/" + digest + ".bin",
		"https://localhost/desktop/v1/parts/" + digest + ".bin", PRODUCTION_ASSETS.replace("/v1/", "/v2/") + "parts/" + digest + ".bin",
		"https://assets.rabbitlandsgame.com/browser/assets/" + digest + ".bin", "https://assets.rabbitlandsgame.com/desktop/selftest/x/parts/" + digest + ".bin",
		PRODUCTION_ASSETS + "parts/" + digest + ".bin?x=1", PRODUCTION_ASSETS + "parts/" + digest + ".bin#x",
		PRODUCTION_ASSETS + "parts/" + upper + ".bin", PRODUCTION_ASSETS + "parts//" + digest + ".bin",
		PRODUCTION_ASSETS + "parts/" + digest + ".zip", PRODUCTION_ASSETS + "parts/../parts/" + digest + ".bin",
		PRODUCTION_ASSETS + "parts/" + digest + ".bin ", PRODUCTION_ASSETS.to_upper() + "parts/" + digest + ".bin",
		"https://assets.rabbitlandsgame.com.example/desktop/v1/parts/" + digest + ".bin", "https://x@assets.rabbitlandsgame.com/desktop/v1/parts/" + digest + ".bin",
		"https://assets.rabbitlandsgame.com:443/desktop/v1/parts/" + digest + ".bin", PRODUCTION_ASSETS + digest + ".bin",
		"https://github.com/o/r/releases/download/client-assets/RabbitLands-pkg-" + other + ".zip.part"]
	for url: String in refused:
		expect(not Release.r2_part({"url": url, "size": 1, "sha256": digest}), "an R2 part form was accepted: " + url)
	for row: Variant in [{"url": PRODUCTION_ASSETS + "parts/" + upper + ".bin", "sha256": upper}, {"url": 7, "sha256": digest},
			{"sha256": digest}, {"url": good.url}, [good.url], good.url, null]:
		expect(not Release.r2_part(row), "an invalid R2 part row was accepted: %s" % [row])
	expect(Release.r2_manifest_url("windows", digest) == PRODUCTION_ASSETS + "manifests/windows/" + digest + ".json", "the R2 manifest URL changed")
	expect(Release.pointer_url("linux") == PRODUCTION_ASSETS + "channels/live/linux.json", "the R2 pointer URL changed")
	# The schema rule: R2 rows in schema 3 only; GitHub rows in both.
	var identity := {"repository": "o/r", "platform": "windows"}
	var r2 := r2_release(3, 3, 2)
	expect(not Packages.validate(r2, identity).has("error"), "schema 3 R2 rows were refused: %s" % Packages.validate(r2, identity).get("error", ""))
	expect(Packages.validate(r2_release(2, 3, 2), identity).get("error", "") == "A package download is invalid.", "schema 2 accepted R2 rows")
	var first: String = r2.parts[0].sha256
	var shared := "https://github.com/o/r/releases/download/client-assets-%s/RabbitLands-pkg-%s.zip.part" % [first.left(1), first]
	expect(not Packages.validate(with_part_url(r2, shared), identity).has("error"), "schema 3 refused a GitHub row beside R2 rows")
	var github_only := with_part_url(r2_release(2, 1), shared)
	expect(not Packages.validate(github_only, identity).has("error"), "schema 2 refused a GitHub row")
	for url: String in refused:
		var moved := url.replace(digest, first).replace(upper, first.to_upper())
		expect(Packages.validate(with_part_url(r2, moved), identity).get("error", "") == "A package download is invalid.", "schema 3 accepted a part at " + moved)
	for kind: String in ["updater", "uninstall"]:
		var helper := r2.duplicate(true)
		helper[kind].url = PRODUCTION_ASSETS + "parts/" + str(helper[kind].sha256) + ".bin"
		expect(Packages.validate(helper, identity).get("error", "") == "The updater or uninstaller download is invalid.", "an R2 %s row was accepted" % kind)
	# Limits: 2000 packages and 2000 parts in all (the R2 release tools' cap).
	expect(not Packages.validate(r2_release(3, 2000), identity).has("error"), "2000 packages were refused")
	expect(Packages.validate(r2_release(3, 2001), identity).get("error", "") == "The package list is invalid.", "2001 packages were accepted")
	expect(not Packages.validate(r2_release(3, 1000, 2), identity).has("error"), "2000 parts were refused")
	expect(Packages.validate(r2_release(3, 667, 3), identity).get("error", "") == "The package list is invalid.", "2001 parts were accepted")
	# Signed: JSON turns numbers into floats; verify_manifest dispatches schema 3.
	var verified := Release.verify_manifest(envelope(r2), _identity)
	expect(not verified.has("error") and Release.package_manifest(verified), "a signed schema 3 manifest with R2 rows was refused: %s" % verified.get("error", ""))
	expect(Release.verify_manifest(envelope(r2_release(2, 3, 2)), _identity).get("error", "") == "A package download is invalid.", "a signed schema 2 manifest with R2 rows was accepted")
	expect(Release.verify_manifest(envelope(with_part_url(r2, "https://127.0.0.1:8443/desktop/v1/parts/" + first + ".bin")), _identity).has("error"), "the production rules accepted a local part")

func scripted_fetch(actions: Array, content: String, calls: Array) -> Callable:
	# A transport stand-in: each call takes the next action. "ok" writes the
	# part's bytes, "garbage" as many other bytes, "partial" a cut transfer,
	# "drop" no reply; a number is that HTTP status; "copy" fails without one.
	return func(url: String, path: String, _limit: int) -> Dictionary:
		calls.append({"url": url, "stale": FileAccess.file_exists(path)})
		var action: String = str(actions.pop_front()) if not actions.is_empty() else "ok"
		if action == "ok":
			write(path, content)
			return {}
		if action == "garbage":
			write(path, "x".repeat(content.length()))
			return {}
		if action == "partial":
			write(path, content.left(3))
			return {"error": "The update download failed.", "status": 200, "result": HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED}
		if action == "drop":
			return {"error": "The update download failed.", "status": 0, "result": HTTPRequest.RESULT_CONNECTION_ERROR}
		if action == "copy":
			return {"error": "A verified download could not be copied."}
		write(path, "<html>status page</html>")
		return {"error": "The update download failed.", "status": int(action), "result": HTTPRequest.RESULT_SUCCESS}

func check_part_retries() -> void:
	# The per-part retry rule (design 5.5), with zero waits and no network.
	var content := "signed part bytes"
	var part := {"url": PRODUCTION_ASSETS + "parts/" + content.sha256_text() + ".bin", "size": content.length(), "sha256": content.sha256_text()}
	var folder := _root + "-retries"
	DirAccess.make_dir_recursive_absolute(folder)
	var path := folder.path_join(str(part.sha256) + ".part")
	var worker := func(callable: Callable) -> Variant: return callable.call()
	var failed := "The update download failed."
	var cases := [[["ok"], "", 1], [["503", "ok"], "", 2], [["429", "drop", "ok"], "", 3], [["403", "ok"], "", 2],
		[["408", "500", "ok"], "", 3], [["partial", "ok"], "", 2], [["garbage", "ok"], "", 2], [["garbage", "503", "ok"], "", 3],
		[["503", "503", "503", "ok"], failed, 3], [["drop", "drop", "drop"], failed, 3],
		[["404", "ok"], Download.MISSING_ERROR, 1], [["410"], Download.MISSING_ERROR, 1], [["503", "404"], Download.MISSING_ERROR, 2],
		[["garbage", "garbage"], Download.VERIFICATION_ERROR, 2], [["garbage", "503", "garbage"], Download.VERIFICATION_ERROR, 3],
		[["400", "ok"], failed, 1], [["copy", "ok"], "A verified download could not be copied.", 1]]
	for case: Array in cases:
		DirAccess.remove_absolute(path)
		var calls: Array = []
		var waits: Array = []
		var actions: Array = case[0].duplicate()
		var error: String = await Download.download_part(part, path, scripted_fetch(actions, content, calls), worker, Callable(), [0.0, 0.0],
			func(seconds: float) -> void: waits.append(seconds))
		var label := "%s" % [case[0]]
		expect(error == case[1], "%s ended with \"%s\", not \"%s\"" % [label, error, case[1]])
		expect(calls.size() == case[2], "%s made %d attempts, not %d" % [label, calls.size(), case[2]])
		expect(waits.size() == calls.size() - 1, "%s waited %d times for %d attempts" % [label, waits.size(), calls.size()])
		expect(calls.all(func(attempt: Dictionary) -> bool: return not attempt.stale and attempt.url == part.url), "%s reused a stale file or changed the URL: %s" % [label, calls])
		expect(not FileAccess.file_exists(path + ".tmp"), "%s left a temporary file" % label)
		expect(Release.check_file(path, int(part.size), part.sha256) == (error == ""), "%s kept the wrong file" % label)
	# The schedule: at once, then after each wait; no waits means one attempt.
	var calls: Array = []
	var waits: Array = []
	DirAccess.remove_absolute(path)
	var error: String = await Download.download_part(part, path, scripted_fetch(["503", "503", "ok"], content, calls), worker, Callable(), [0.0, 0.0],
		func(seconds: float) -> void: waits.append(seconds))
	expect(error == "" and waits == [0.0, 0.0], "the retry waits were not reported in order: %s" % [waits])
	calls.clear()
	DirAccess.remove_absolute(path)
	error = await Download.download_part(part, path, scripted_fetch(["503", "ok"], content, calls), worker, Callable(), [])
	expect(error == failed and calls.size() == 1, "an empty wait list still retried")
	# A partial file left by an interrupted run never seeds the first attempt.
	calls.clear()
	DirAccess.remove_absolute(path)
	write(path + ".tmp", "stale partial")
	error = await Download.download_part(part, path, scripted_fetch(["ok"], content, calls), worker, Callable(), [0.0, 0.0])
	expect(error == "" and calls.size() == 1 and not calls[0].stale, "a stale partial download seeded the first attempt: %s" % [calls])
	expect(Download.RETRY_WAITS_SEC == [5.0, 30.0], "the production retry waits are not 5 s then 30 s: %s" % [Download.RETRY_WAITS_SEC])
	# Cancellation ends the attempts.
	calls.clear()
	DirAccess.remove_absolute(path)
	error = await Download.download_part(part, path, scripted_fetch(["503", "ok"], content, calls), worker, func() -> bool: return calls.size() >= 1, [0.0, 0.0])
	expect(error == Download.CANCELLED_ERROR and calls.size() == 1 and not FileAccess.file_exists(path + ".tmp"), "a cancelled download went on: %s" % error)
	expect(not await Download.wait(10.0, func() -> bool: return true), "a cancelled wait did not end")
	expect(await Download.wait(0.0), "a zero wait was refused")
	# The classification the transports' statuses feed.
	var table := [[{"status": 0, "result": HTTPRequest.RESULT_CANT_CONNECT}, true, false], [{"status": 0, "result": HTTPRequest.RESULT_TIMEOUT}, true, false],
		[{"status": 200, "result": HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED}, true, false], [{"status": 200, "result": HTTPRequest.RESULT_DOWNLOAD_FILE_WRITE_ERROR}, false, false],
		[{"status": 200, "result": HTTPRequest.RESULT_DOWNLOAD_FILE_CANT_OPEN}, false, false],
		[{"status": 503, "result": HTTPRequest.RESULT_SUCCESS}, true, false], [{"status": 500, "result": HTTPRequest.RESULT_SUCCESS}, true, false],
		[{"status": 429, "result": HTTPRequest.RESULT_SUCCESS}, true, false], [{"status": 403, "result": HTTPRequest.RESULT_SUCCESS}, true, false],
		[{"status": 408, "result": HTTPRequest.RESULT_SUCCESS}, true, false], [{"status": 404, "result": HTTPRequest.RESULT_SUCCESS}, false, true],
		[{"status": 404, "result": HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED}, false, true], [{"status": 410, "result": HTTPRequest.RESULT_SUCCESS}, false, true],
		[{"status": 400, "result": HTTPRequest.RESULT_SUCCESS}, false, false], [{"status": 401, "result": HTTPRequest.RESULT_SUCCESS}, false, false],
		[{}, false, false]]
	for row: Array in table:
		var result: Dictionary = row[0].duplicate()
		result["error"] = "failed"
		expect(Download.retryable(result) == row[1] and Download.missing(result) == row[2], "a fetch result was misclassified: %s" % [row])
	# A request that could not start made no network attempt: final.
	expect(not Download.retryable({"error": "The update download could not start."}), "a request that never started was retried")
	Release.remove_tree(folder)

func check_move_file() -> void:
	# HOOK-B8: the online setup's helper moves a verified download from its
	# {tmp} into the update cache instead of copying it (one copy on disk).
	var folder := _root + "-move"
	Release.remove_tree(folder)
	var source := folder.path_join("tmp/" + "e".repeat(64) + ".bin")
	var target := folder.path_join("cache/packages/" + "e".repeat(64) + ".part.tmp")
	write(source, "verified part bytes")
	write(target, "stale bytes")
	expect(Release.move_file(source, target) == OK, "a verified download could not be moved")
	expect(not FileAccess.file_exists(source), "a moved download stayed in setup's folder")
	expect(FileAccess.get_file_as_string(target) == "verified part bytes", "a moved download lost its bytes or kept the stale file")
	expect(Release.move_file(source, target) != OK, "a missing download was reported as moved")
	expect(FileAccess.get_file_as_string(target) == "verified part bytes", "a failed move changed the cached file")
	Release.remove_tree(folder)

func _initialize() -> void:
	_key = Crypto.new().generate_rsa(2048)
	var a := "a".repeat(40)
	var b := "b".repeat(40)
	var c := "c".repeat(40)
	_identity = {"schema": 1, "commit": a, "ancestors": [a], "platform": "windows", "repository": "o/r", "public_key": _key.save_to_string(true)}
	_root = OS.get_cmdline_user_args()[0]
	expect(Release.contains_commit({"commit": b, "ancestors": [a, c]}, a), "merge ancestry must retain a newer client")
	expect(not Release.contains_commit({"commit": c, "ancestors": [a]}, b), "divergent branch must update")
	for path in ["../escape", "app/../escape", "app/x:stream", "app/CON", "app/X.", "app//x", "/app/x", "other/x", "app\\x"]:
		expect(not Release.safe_path(path), "unsafe path accepted: " + path)
	expect(Release.safe_path("app/assets/models/example.glb"), "ordinary nested paths must work")
	var shared_hash := "a".repeat(64)
	var shared_name := "/RabbitLands-pkg-%s.zip.part" % shared_hash
	expect(Release.shared_download({"sha256": shared_hash,
		"url": "https://github.com/o/r/releases/download/client-assets" + shared_name}, "o/r"),
		"legacy shared package URL must remain valid")
	expect(Release.shared_download({"sha256": shared_hash,
		"url": "https://github.com/o/r/releases/download/client-assets-a" + shared_name}, "o/r"),
		"checksum-partitioned shared package URL must be valid")
	expect(not Release.shared_download({"sha256": shared_hash,
		"url": "https://github.com/o/r/releases/download/client-assets-b" + shared_name}, "o/r"),
		"shared package must reject a mismatched checksum partition")
	old_install()
	var signed := make_download(b)
	var release := Release.verify_manifest(signed, _identity, b)
	expect(not release.has("error"), "valid signed manifest rejected")
	expect(Release.verify_manifest(signed, _identity, c).has("error"), "wrong server target accepted")
	var tampered := signed.duplicate()
	tampered.payload = Marshalls.raw_to_base64("{}".to_utf8_buffer())
	expect(Release.verify_manifest(tampered, _identity).has("error"), "tampered signature accepted")
	expect(Release.install(_root, _identity) == "", "valid restart install failed")
	expect(FileAccess.get_file_as_string(_root.path_join("app/RabbitLands.exe")) == "new exe", "executable not replaced")
	expect(FileAccess.get_file_as_string(_root.path_join("eloria-assets/map.json")) == "new map", "world assets not replaced")
	expect(FileAccess.get_file_as_string(_root.path_join(".eloria-previous/app/RabbitLands.exe")) == "old exe", "backup not preserved")
	expect(not FileAccess.file_exists(Release.cache_for(_root).path_join("pending.json")), "pending marker not consumed")
	old_install()
	make_download(b)
	var lease := Release.cache_for(_root).path_join("running-test.json")
	Release.save_json(lease, {"pid": OS.get_process_id()})
	expect(Release.install(_root, _identity) != "", "an active game was updated")
	expect(FileAccess.get_file_as_string(_root.path_join("app/RabbitLands.exe")) == "old exe", "active game files changed")
	DirAccess.remove_absolute(lease)
	old_install()
	signed = make_download(b, {"app/../outside": "bad"})
	expect(Release.install(_root, _identity) != "", "archive path traversal accepted")
	expect(FileAccess.get_file_as_string(_root.path_join("app/RabbitLands.exe")) == "old exe", "unsafe archive changed installed game")
	old_install()
	make_download(b)
	write(Release.cache_for(_root).path_join("release.zip"), "corrupt")
	expect(Release.install(_root, _identity) != "", "corrupt archive accepted")
	expect(FileAccess.get_file_as_string(_root.path_join("app/RabbitLands.exe")) == "old exe", "corrupt update changed installed game")
	old_install()
	make_download(b)
	var newer := _identity.duplicate()
	newer.commit = c
	newer.ancestors = [a, b]
	write(_root.path_join("app/client-release.json"), JSON.stringify(newer))
	expect(Release.install(_root, _identity) == "", "ahead client update check failed")
	expect(FileAccess.get_file_as_string(_root.path_join("app/RabbitLands.exe")) == "old exe", "ahead client was downgraded")
	old_install()
	DirAccess.make_dir_recursive_absolute(_root.path_join(".eloria-previous"))
	DirAccess.rename_absolute(_root.path_join("app"), _root.path_join(".eloria-previous/app"))
	write(_root.path_join("app/RabbitLands.exe"), "partly installed")
	Release.save_json(_root.path_join(".eloria-update-journal.json"), {"commit": b})
	expect(Release.recover(_root) == "", "interrupted install could not recover")
	expect(FileAccess.get_file_as_string(_root.path_join("app/RabbitLands.exe")) == "old exe", "interrupted install did not restore old executable")
	expect(FileAccess.get_file_as_string(_root.path_join("eloria-assets/map.json")) == "old map", "interrupted install changed untouched world")
	check_per_file_operations()
	check_parallel_scan()
	check_codec_schema()
	check_r2_rows()
	await check_part_retries()
	check_move_file()
	Release.remove_tree(_root)
	print("Client update runtime checks: ", "PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)

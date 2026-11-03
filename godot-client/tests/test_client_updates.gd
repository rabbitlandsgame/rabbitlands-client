extends SceneTree
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")
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
	Release.remove_tree(_root)
	print("Client update runtime checks: ", "PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)

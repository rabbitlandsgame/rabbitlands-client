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
	Release.remove_tree(_root)
	print("Client update runtime checks: ", "PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)

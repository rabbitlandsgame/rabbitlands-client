extends SceneTree
## Updater disk cleanup: the previous installation backup is removed only once
## no journal needs it, and helper copies return to one staged helper.
const Release = preload("res://src/updates/release.gd")
const Bootstrap = preload("res://src/updates/bootstrap.gd")
const DEAD_PID := 999999999
const HELPER_BYTES := 64
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

func old_install() -> void:
	Release.remove_tree(_root)
	Release.remove_tree(Release.cache_for(_root))
	write(_root.path_join("app/RabbitLands.exe"), "old exe")
	write(_root.path_join("app/RabbitLands.pck"), "old pck")
	write(_root.path_join("app/client-release.json"), JSON.stringify(_identity))
	write(_root.path_join("eloria-assets/map.json"), "old map")

func make_download(commit: String) -> void:
	var descriptor := _identity.duplicate(true)
	descriptor.commit = commit
	descriptor.ancestors = [commit]
	var files: Dictionary = {"app/RabbitLands.exe": "exe " + commit, "app/RabbitLands.pck": "pck " + commit,
		"app/client-release.json": JSON.stringify(descriptor), "eloria-assets/map.json": "map " + commit}
	var cache := Release.cache_for(_root)
	DirAccess.make_dir_recursive_absolute(cache)
	var archive := cache.path_join("release.zip")
	var zip := ZIPPacker.new()
	zip.open(archive)
	var inventory: Array = []
	var total := 0
	for path: String in files:
		var bytes: PackedByteArray = str(files[path]).to_utf8_buffer()
		inventory.append({"path": path, "size": bytes.size(), "sha256": str(files[path]).sha256_text()})
		zip.start_file("files/%06d/%06d" % [inventory.size() - 1, 0])
		zip.write_file(bytes)
		zip.close_file()
		total += bytes.size()
	zip.start_file("inventory.json")
	zip.write_file(JSON.stringify(inventory).to_utf8_buffer())
	zip.close_file()
	zip.close()
	var file := FileAccess.open(archive, FileAccess.READ)
	var size := file.get_length()
	file.close()
	Release.save_json(cache.path_join("pending.json"), envelope({"schema": 1, "commit": commit, "platform": "windows",
		"size": size, "unpacked_size": total, "sha256": FileAccess.get_sha256(archive),
		"parts": [{"url": "https://github.com/o/r/releases/download/t/a.001", "size": size, "sha256": FileAccess.get_sha256(archive)}]}))

func text(relative: String) -> String:
	return FileAccess.get_file_as_string(_root.path_join(relative))

func helper_envelope(version: String, content: String) -> Dictionary:
	var commit := "d".repeat(40)
	var base := "https://github.com/%s/releases/download/client-%s/" % [_identity.repository, commit]
	var row := func(kind: String) -> Dictionary:
		return {"url": base + version + "-" + kind + ".exe", "size": content.length(), "sha256": content.sha256_text()}
	return envelope({"bootstrap_schema": 1, "repository": _identity.repository, "platform": _identity.platform,
		"commit": commit, "version": version, "updater": row.call("updater"), "uninstall": row.call("uninstall")})

func helper(version: String) -> String:
	# Equal sizes make a steady cache footprint directly comparable.
	return ("helper " + version + " ").rpad(HELPER_BYTES, "x")

func handoff_copy(pid: int) -> String:
	return Release.cache_for(_root).path_join("handoff-%d%s" % [pid, ".exe" if OS.get_name() == "Windows" else ".x86_64"])

func start_handoff(version: String, pid: int) -> Dictionary:
	# Mirrors the launcher: stage the verified helper, record the request,
	# then leave the copy a handover worker would run from.
	var content := helper(version)
	var signed := helper_envelope(version, content)
	var release := Bootstrap.verify(signed, _identity)
	expect(not release.has("error"), "helper release %s failed verification" % version)
	var fetch := func(_url: String, path: String, _limit: int) -> Dictionary:
		write(path, content)
		return {}
	var worker := func(callable: Callable) -> Variant: return callable.call()
	var error: String = await Bootstrap.prepare_helpers(_root, release, fetch, worker)
	expect(error == "", "helper %s was not staged: %s" % [version, error])
	Release.save_json(Release.cache_for(_root).path_join("bootstrap-manifest.json"), {"envelope": signed, "args": []})
	write(handoff_copy(pid), "running updater copy " + version)
	return release

func helper_footprint() -> int:
	# Every file the self-update leaves behind: handover copies, staged helpers
	# and the replaced helpers kept beside the installation.
	var total := 0
	var cache := Release.cache_for(_root)
	for name: String in DirAccess.get_files_at(cache):
		if name.begins_with("handoff-"):
			total += FileAccess.get_file_as_bytes(cache.path_join(name)).size()
	for folder: String in [cache.path_join("bootstrap"), _root.path_join(".rabbitlands-bootstrap-previous")]:
		if DirAccess.dir_exists_absolute(folder):
			for name: String in DirAccess.get_files_at(folder):
				total += FileAccess.get_file_as_bytes(folder.path_join(name)).size()
	return total

func staged() -> PackedStringArray:
	return DirAccess.get_files_at(Release.cache_for(_root).path_join("bootstrap"))

func check_backup_cleanup() -> void:
	# An interrupted promotion keeps its journal: cleanup must not touch the
	# backup, and recovery still restores the old game.
	old_install()
	DirAccess.make_dir_recursive_absolute(_root.path_join(".eloria-previous"))
	DirAccess.rename_absolute(_root.path_join("app"), _root.path_join(".eloria-previous/app"))
	write(_root.path_join("app/RabbitLands.exe"), "partly installed")
	Release.save_json(_root.path_join(".eloria-update-journal.json"), {"commit": "b".repeat(40)})
	expect(Release.remove_backup(_root) == ERR_BUSY, "a backup was removed while its journal was pending")
	expect(text(".eloria-previous/app/RabbitLands.exe") == "old exe", "a journal's backup was changed")
	expect(Release.recover(_root) == "", "an interrupted update could not recover")
	expect(text("app/RabbitLands.exe") == "old exe" and text("app/RabbitLands.pck") == "old pck", "recovery did not restore the old game")
	expect(text("eloria-assets/map.json") == "old map", "recovery changed an untouched root")
	# A completed update keeps its backup until a confirmed start removes it.
	old_install()
	make_download("b".repeat(40))
	expect(Release.install(_root, _identity) == "", "the update was not installed")
	expect(text(".eloria-previous/app/RabbitLands.exe") == "old exe", "the backup was not kept after install")
	# A launcher stops at its game's exit; the rest continues later.
	var calls := [0]
	var stop_after_one := func() -> bool:
		calls[0] += 1
		return calls[0] > 1
	expect(Release.remove_backup(_root, stop_after_one) == ERR_SKIP, "a stopped backup removal did not report it")
	expect(calls[0] == 2 and DirAccess.dir_exists_absolute(_root.path_join(".eloria-previous")), "a stopped backup removal did not stop at the next file")
	expect(text("app/RabbitLands.exe") == "exe " + "b".repeat(40) and text("eloria-assets/map.json") == "map " + "b".repeat(40), "a partial backup removal changed the live game")
	# A partially removed backup never blocks or weakens the next update.
	make_download("c".repeat(40))
	expect(Release.install(_root, _identity) == "", "an update after a partial backup removal failed")
	expect(text(".eloria-previous/app/RabbitLands.exe") == "exe " + "b".repeat(40), "the next update did not keep its own backup")
	expect(Release.remove_backup(_root) == OK, "the backup was not removed")
	expect(not DirAccess.dir_exists_absolute(_root.path_join(".eloria-previous")), "the backup folder remains")
	expect(text("app/RabbitLands.exe") == "exe " + "c".repeat(40) and text("eloria-assets/map.json") == "map " + "c".repeat(40), "backup removal changed the live game")
	expect(Release.remove_backup(_root) == OK, "removing a missing backup failed")
	# A journal written during removal stops it at the next file.
	make_download("b".repeat(40))
	expect(Release.install(_root, _identity) == "", "a third update was not installed")
	var journal := _root.path_join(".eloria-update-journal.json")
	var journal_mid_removal := func() -> bool:
		Release.save_json(journal, {"commit": "c".repeat(40)})
		return false
	expect(Release.remove_backup(_root, journal_mid_removal) == ERR_SKIP, "a new journal did not stop backup removal")
	expect(Release.remove_backup(_root) == ERR_BUSY, "backup removal ignored a pending journal")
	DirAccess.remove_absolute(journal)

func check_helper_cleanup() -> void:
	old_install()
	for kind: String in ["updater", "uninstall"]:
		write(_root.path_join(Bootstrap.helper_name(kind, _identity)), helper("v0"))
	var cache := Release.cache_for(_root)
	var first: Dictionary = await start_handoff("v1", DEAD_PID)
	expect(Bootstrap.promote_helpers(_root, first, _identity) == "", "the first handover failed")
	# Freshly made copies and an unproven installed helper are kept.
	Bootstrap.prune_cache(_root, _identity, false)
	expect(FileAccess.file_exists(handoff_copy(DEAD_PID)), "a recent handover copy was removed")
	expect(DirAccess.dir_exists_absolute(_root.path_join(".rabbitlands-bootstrap-previous")), "previous helpers were removed before the installed helper ran")
	var removed := Bootstrap.prune_cache(_root, _identity, true, 0)
	expect(removed.size() == 3 and removed[0].begins_with("Removed "), "cleanup did not report what it removed: %s" % [removed])
	var steady := helper_footprint()
	expect(steady == HELPER_BYTES and staged() == PackedStringArray([first.updater.sha256]), "one handover did not settle to one staged helper (%d bytes)" % steady)
	expect(not DirAccess.dir_exists_absolute(_root.path_join(".rabbitlands-bootstrap-previous")), "previous helpers were kept after the installed helper ran")
	# Files the updater did not name this way, and the game's own records, stay.
	var unrelated := [cache.path_join("notes.txt"), cache.path_join("handoff-abc.exe"), cache.path_join("handoff-0123.exe"),
		cache.path_join("bootstrap/readme.txt"), cache.path_join("bootstrap/folder/" + "e".repeat(64)), cache.path_join("pending.json"),
		cache.path_join("packages/" + "f".repeat(64) + ".part"), cache.path_join("running-%d.json" % OS.get_process_id()), handoff_copy(OS.get_process_id())]
	for path: String in unrelated:
		write(path, "keep")
	var second: Dictionary = await start_handoff("v2", DEAD_PID - 1)
	expect(Bootstrap.promote_helpers(_root, second, _identity) == "", "the second handover failed")
	expect(helper_footprint() > steady, "the fixture does not reproduce the helper copy growth")
	Bootstrap.prune_cache(_root, _identity, true, 0)
	expect(staged() == PackedStringArray([second.updater.sha256, "readme.txt"]) or staged() == PackedStringArray(["readme.txt", second.updater.sha256]), "the old staged helper was kept: %s" % [staged()])
	for path: String in unrelated:
		expect(FileAccess.get_file_as_string(path) == "keep", "cleanup removed an unrelated file " + path)
		DirAccess.remove_absolute(path)
	expect(helper_footprint() == steady, "two handovers did not return to the steady helper footprint (%d bytes)" % helper_footprint())
	expect(FileAccess.get_file_as_string(_root.path_join("RabbitLands-updater.exe")) == helper("v2"), "cleanup changed the installed helper")
	# An interrupted handover still has its staged helper and can finish.
	var third: Dictionary = await start_handoff("v3", DEAD_PID - 2)
	write(Bootstrap.staged_helper(_root, third.updater) + ".tmp", "partial download")
	Bootstrap.prune_cache(_root, _identity, true, 0)
	expect(staged() == PackedStringArray([third.updater.sha256]), "an unfinished handover lost its staged helper: %s" % [staged()])
	expect(Bootstrap.promote_helpers(_root, third, _identity) == "", "an interrupted handover could not finish after cleanup")
	expect(FileAccess.get_file_as_string(_root.path_join("RabbitLands-uninstall.exe")) == helper("v3"), "the finished handover installed the wrong helper")
	# Previous helpers stay while a promotion is incomplete.
	write(_root.path_join("RabbitLands-uninstall.exe.next"), "half promoted")
	Bootstrap.prune_cache(_root, _identity, true, 0)
	expect(FileAccess.file_exists(_root.path_join(".rabbitlands-bootstrap-previous/RabbitLands-updater.exe")), "previous helpers were removed during an incomplete promotion")
	DirAccess.remove_absolute(_root.path_join("RabbitLands-uninstall.exe.next"))
	# Without a verifiable handover record, staged helpers are kept.
	write(Bootstrap.staged_helper(_root, second.updater), helper("v2"))
	var tampered := Release.read_json(cache.path_join("bootstrap-manifest.json"))
	tampered.envelope.signature = Marshalls.raw_to_base64("bad".to_utf8_buffer())
	Release.save_json(cache.path_join("bootstrap-manifest.json"), tampered)
	Bootstrap.prune_cache(_root, _identity, true, 0)
	expect(staged().size() == 2, "staged helpers were pruned against an unverified handover record")

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	_key = Crypto.new().generate_rsa(2048)
	var a := "a".repeat(40)
	_identity = {"schema": 1, "commit": a, "ancestors": [a], "platform": "windows", "repository": "o/r", "public_key": _key.save_to_string(true)}
	var args := OS.get_cmdline_user_args()
	_root = args[0] if not args.is_empty() else OS.get_user_data_dir().path_join("client-update-cleanup-fixture")
	_root = _root.replace("\\", "/").simplify_path()
	check_backup_cleanup()
	await check_helper_cleanup()
	Release.remove_tree(Release.cache_for(_root))
	Release.remove_tree(_root)
	print("Client update cleanup checks: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

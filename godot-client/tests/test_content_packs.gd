extends SceneTree
## ContentPacks (src/boot/content_packs.gd, W2-UD-06): a source run is a no-op;
## the pack folder (executable packs/, overrides on editor binaries only); real
## packs written by PCKPacker are mounted, become readable through FileAccess
## and ResourceLoader, and are not mounted twice; feature packs wait for
## include_features; missing, wrong-size, refused and invalid rows fail the
## report without crashing; the diagnostic row; the repair message each
## distribution gets; and mount() itself reading a
## manifest that a mounted pack provides, from RABBITLANDS_CONTENT_PACKS.
## Fixture packs live in an isolated user directory under a unique res:// prefix.

const ContentPacks := preload("res://src/boot/content_packs.gd")

var failures := 0
var root_dir := ""
var tag := ""

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	var stamp := "%d" % Time.get_ticks_usec()
	root_dir = ProjectSettings.globalize_path("user://content-packs-test-" + stamp)
	tag = "res://.rl-content-packs-test-" + stamp
	DirAccess.make_dir_recursive_absolute(root_dir.path_join("packs"))
	DirAccess.make_dir_recursive_absolute(root_dir.path_join("source"))
	_source_run()
	_directory()
	_mounting()
	_failures()
	_diagnostic()
	_repair_message()
	_mount_from_manifest()
	print("test_content_packs: %d failures" % failures)
	quit(1 if failures else 0)

func _write(name: String, text: String) -> String:
	var path := root_dir.path_join("source").path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()
	return path

## A real pack: {res:// target: source file}.
func _pack(file: String, entries: Dictionary) -> int:
	var path := root_dir.path_join(file)
	var packer := PCKPacker.new()
	expect(packer.pck_start(path) == OK, "PCKPacker starts " + file)
	for target: String in entries:
		packer.add_file(target, entries[target])
	expect(packer.flush() == OK, "PCKPacker writes " + file)
	var handle := FileAccess.open(path, FileAccess.READ)
	var size := handle.get_length()
	handle.close()
	return size

func _row(file: String, size: int, feature := "") -> Dictionary:
	return {"file": file, "bytes": size, "entries": 1, "sha256": "", "feature": feature}

func _manifest(rows: Array) -> String:
	return JSON.stringify({"schema": ContentPacks.MANIFEST_SCHEMA, "packs": rows})

func _state(report: Dictionary, file: String) -> String:
	for row: Dictionary in report.get("packs", []):
		if row.get("file") == file:
			return str(row.get("state", ""))
	return "(absent)"

func _source_run() -> void:
	expect(not FileAccess.file_exists(ContentPacks.MANIFEST), "a source checkout has no content pack manifest")
	var report := ContentPacks.mount()
	expect(report.get("state") == "none" and report.get("packs", [1]).is_empty(),
		"a source run mounts nothing: %s" % JSON.stringify(report))
	expect(ContentPacks.current_report().get("state") == "none", "the cumulative report says none")

func _directory() -> void:
	var exe := "C:/Games/RabbitLands/app/RabbitLands.exe"
	var none := PackedStringArray()
	expect(ContentPacks.resolve_directory(none, none, "", exe, false) == "C:/Games/RabbitLands/app/packs",
		"the packs sit in the executable's packs/ folder")
	expect(ContentPacks.resolve_directory(PackedStringArray(["--content-packs=D:/stage/app/packs"]), none, "V", exe, true)
		== "D:/stage/app/packs", "an editor binary takes --content-packs= first")
	expect(ContentPacks.resolve_directory(none, PackedStringArray(["--content-packs=E:/p"]), "", exe, true) == "E:/p",
		"an editor binary takes --content-packs= after -- too")
	expect(ContentPacks.resolve_directory(none, none, "F:/v", exe, true) == "F:/v",
		"an editor binary takes RABBITLANDS_CONTENT_PACKS")
	expect(ContentPacks.resolve_directory(PackedStringArray(["--content-packs="]), none, "", exe, true)
		== "C:/Games/RabbitLands/app/packs", "an empty --content-packs= is ignored")
	expect(ContentPacks.resolve_directory(PackedStringArray(["--content-packs=D:/x"]), none, "F:/v", exe, false)
		== "C:/Games/RabbitLands/app/packs", "a release template ignores both overrides")
	expect(ContentPacks.resolve_directory(none, none, "", "/opt/rl/app/RabbitLands.x86_64", false) == "/opt/rl/app/packs",
		"Linux: beside the executable too")

func _mounting() -> void:
	var alpha := _pack("packs/alpha.pck", {tag + "/alpha.txt": _write("alpha.txt", "alpha bytes")})
	var probe := _write("probe.tres", "[gd_resource type=\"Resource\" format=3]\n\n[resource]\nresource_name = \"probe from beta\"\n")
	var beta := _pack("packs/beta.pck", {tag + "/probe.tres": probe})
	var pilot := _pack("packs/pilot.pck", {tag + "/pilot.txt": _write("pilot.txt", "pilot")})
	var text := _manifest([_row("packs/alpha.pck", alpha), _row("packs/beta.pck", beta),
		_row("packs/pilot.pck", pilot, "prepared-content")])
	expect(not FileAccess.file_exists(tag + "/alpha.txt"), "nothing of a pack is visible before its mount")
	var report := ContentPacks.mount_manifest(text, root_dir.path_join("packs"))
	expect(report.state == "mounted", "required packs mount: %s" % JSON.stringify(report))
	expect(_state(report, "packs/alpha.pck") == "mounted" and _state(report, "packs/beta.pck") == "mounted",
		"each required pack reports mounted")
	expect(_state(report, "packs/pilot.pck") == "skipped", "a feature pack waits for include_features")
	expect(int(report.usec) >= 0 and report.packs.all(func(row: Dictionary) -> bool: return int(row.usec) >= 0),
		"mount times are recorded")
	expect(FileAccess.get_file_as_string(tag + "/alpha.txt") == "alpha bytes", "a mounted file reads through res://")
	var resource := ResourceLoader.load(tag + "/probe.tres", "", ResourceLoader.CACHE_MODE_IGNORE)
	expect(resource != null and resource.resource_name == "probe from beta", "ResourceLoader loads from a mounted pack")
	expect(not FileAccess.file_exists(tag + "/pilot.txt"), "a skipped feature pack stays unmounted")
	var again := ContentPacks.mount_manifest(text, root_dir.path_join("packs"))
	expect(again.state == "mounted" and _state(again, "packs/alpha.pck") == "already",
		"a pack is mounted once per process")
	var features := ContentPacks.mount_manifest(text, root_dir.path_join("packs"), true)
	expect(_state(features, "packs/pilot.pck") == "mounted" and FileAccess.get_file_as_string(tag + "/pilot.txt") == "pilot",
		"include_features mounts the feature pack")

func _failures() -> void:
	var packs := root_dir.path_join("packs")
	var missing := ContentPacks.mount_manifest(_manifest([_row("packs/gone.pck", 100)]), packs)
	expect(missing.state == "failed" and _state(missing, "packs/gone.pck") == "missing", "a missing pack fails the report")
	var sized := _pack("packs/sized.pck", {tag + "/sized.txt": _write("sized.txt", "sized")})
	var wrong := ContentPacks.mount_manifest(_manifest([_row("packs/sized.pck", sized + 1)]), packs)
	expect(wrong.state == "failed" and _state(wrong, "packs/sized.pck") == "size", "a wrong-size pack fails the report")
	expect(not FileAccess.file_exists(tag + "/sized.txt"), "a wrong-size pack is not mounted")
	var garbage := FileAccess.open(packs.path_join("garbage.pck"), FileAccess.WRITE)
	garbage.store_buffer("not a pack at all, only text".to_utf8_buffer())
	garbage.close()
	var refused := ContentPacks.mount_manifest(_manifest([_row("packs/garbage.pck", 28)]), packs)
	expect(refused.state == "failed" and _state(refused, "packs/garbage.pck") == "refused",
		"a pack the engine refuses fails the report: %s" % JSON.stringify(refused))
	for file: String in ["../alpha.pck", "packs/../alpha.pck", "packs/Alpha.pck", "C:/alpha.pck", "packs/alpha.zip",
			"packs/sub/alpha.pck", "alpha.pck"]:
		var invalid := ContentPacks.mount_manifest(_manifest([_row(file, 10)]), packs)
		expect(invalid.state == "failed" and _state(invalid, file) == "invalid", "an invalid pack file is refused: " + file)
	var repeated := ContentPacks.mount_manifest(_manifest([_row("packs/alpha.pck", 1), _row("packs/alpha.pck", 1)]), packs)
	expect(repeated.state == "failed", "a repeated pack row fails the report")
	var negative := ContentPacks.mount_manifest(_manifest([_row("packs/beta.pck", -1)]), packs)
	expect(negative.state == "failed" and _state(negative, "packs/beta.pck") == "invalid", "a row without a size is invalid")
	for text: String in ["{not json", JSON.stringify({"schema": 2, "packs": []}), JSON.stringify({"schema": 1}),
			JSON.stringify([1, 2])]:
		var bad := ContentPacks.mount_manifest(text, packs)
		expect(bad.state == "failed" and bad.packs.size() == 1 and bad.packs[0].state == "invalid",
			"an unreadable manifest fails the report: " + text)
	var optional := ContentPacks.mount_manifest(_manifest([_row("packs/gone-pilot.pck", 5, "prepared-content")]), packs, true)
	expect(optional.state == "mounted" and _state(optional, "packs/gone-pilot.pck") == "missing",
		"a missing feature pack does not fail the required set")
	var empty := ContentPacks.mount_manifest(_manifest([]), packs)
	expect(empty.state == "mounted" and empty.packs.is_empty(), "an empty pack list mounts nothing and passes")

func _diagnostic() -> void:
	var row := ContentPacks.diagnostic_row({"state": "failed", "directory": "D:/p", "usec": 12, "packs": [
		{"file": "packs/a.pck", "bytes": 5, "feature": "", "state": "mounted", "usec": 7},
		{"file": "packs/b.pck", "bytes": 5, "feature": "", "state": "missing", "usec": 0, "error": "not found"}]})
	expect(row.event == "content_packs" and row.state == "failed" and row.directory == "D:/p" and row.usec == 12,
		"the diagnostic names the event, state, folder and total time")
	expect(row.packs.size() == 2 and row.packs[0] == {"file": "packs/a.pck", "state": "mounted", "usec": 7}
		and row.packs[1].get("error") == "not found", "the diagnostic lists each pack's state, time and error")
	expect(row.has("elapsed_ms") and row.has("time_utc"), "the diagnostic has ClientDiagnostics.record's time fields")
	expect(JSON.parse_string(JSON.stringify(row)) is Dictionary, "the diagnostic is one JSON object")

## Steam and standalone builds ship no updater: the message names the repair
## their update owner offers (the descriptor's distribution, GitHub when absent).
func _repair_message() -> void:
	var updater := ContentPacks.repair_message(JSON.stringify({"distribution": "github", "commit": "a"}))
	expect(updater == ContentPacks.REPAIR_MESSAGE and "run the updater" in updater, "a GitHub build asks for the updater")
	for text: String in ["", "{not json", JSON.stringify({"commit": "a"}), JSON.stringify(["steam"]),
			JSON.stringify({"distribution": "itch"})]:
		expect(ContentPacks.repair_message(text) == ContentPacks.REPAIR_MESSAGE,
			"no, an unreadable or an unknown distribution falls back to the updater: " + text)
	var steam := ContentPacks.repair_message(JSON.stringify({"distribution": "steam"}))
	expect("Verify integrity of game files" in steam and not "updater" in steam, "a Steam build asks for Steam's file check")
	var standalone := ContentPacks.repair_message(JSON.stringify({"distribution": "standalone"}))
	expect("original download page" in standalone and not "updater" in standalone,
		"a standalone build asks for a fresh download")
	for message: String in [updater, steam, standalone]:
		expect(message.begins_with("Some game files are missing or damaged. Close the game and "),
			"every message opens alike: " + message)

func _mount_from_manifest() -> void:
	# A core-like pack provides res://data/content_packs.json; mount() then reads
	# it and, on this editor binary, the RABBITLANDS_CONTENT_PACKS folder.
	var other := root_dir.path_join("other-packs")
	DirAccess.make_dir_recursive_absolute(other)
	var gamma_size := _pack("other-packs/gamma.pck", {tag + "/gamma.txt": _write("gamma.txt", "gamma")})
	var manifest := _write("content_packs.json", _manifest([_row("packs/gamma.pck", gamma_size)]))
	_pack("core-like.pck", {ContentPacks.MANIFEST: manifest})
	expect(ProjectSettings.load_resource_pack(root_dir.path_join("core-like.pck"), false), "the core-like pack mounts")
	expect(OS.has_feature("editor"), "the suite runs on an editor binary")
	OS.set_environment(ContentPacks.DIRECTORY_VARIABLE, other)
	var report := ContentPacks.mount()
	OS.unset_environment(ContentPacks.DIRECTORY_VARIABLE)
	expect(report.state == "mounted" and report.directory == other and _state(report, "packs/gamma.pck") == "mounted",
		"mount() reads the manifest and the overridden folder: %s" % JSON.stringify(report))
	expect(FileAccess.get_file_as_string(tag + "/gamma.txt") == "gamma", "the overridden folder's pack is readable")
	expect(ContentPacks.mount() == report, "mount() is idempotent once it mounted")

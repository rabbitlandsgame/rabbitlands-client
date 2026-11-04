extends Node
## The first autoload (project.godot [autoload] ContentPacks, placed before every
## other): mounts the content packs of a split release (W2-UD-06,
## tools/pck_split.py) before any later autoload, the main scene or a script's
## preload can name a resource they hold.
##
## A split release ships app/RabbitLands.pck as a small core pack (scripts,
## scenes, data, every .import and .remap, the UID and class caches, the boot
## closure) and the heavy, rarely changing import products - textures, audio,
## the login videos - in app/packs/*.pck, which the core lists in
## res://data/content_packs.json. Each required pack is checked for existence and
## byte size (hashing every file is the updater's job) and mounted with
## ProjectSettings.load_resource_pack, never replacing a core file. The packs sit
## in OS.get_executable_path().get_base_dir()/packs. An editor binary (a tool
## running --main-pack on a staged core) may name another folder with
## --content-packs=DIR or RABBITLANDS_CONTENT_PACKS=DIR; a release template never
## mounts packs from anywhere but its own install.
##
## No manifest - a source checkout, the editor, a monolithic export - or the web
## build: nothing happens and nothing is printed. A required pack that is
## missing, the wrong size or refused never crashes the game: the client logs a
## content_packs diagnostic with the reason and, with a display, shows a native
## message asking the player to repair the installation the way its update owner
## does (the updater, Steam's file check or a fresh download: repair_message) - a
## deferred dialog could never show: the main scene fails to load without its
## textures.
##
## Self-contained on purpose: the first autoload is compiled before anything is
## mounted, so this script names no other project script and preloads nothing.

const MANIFEST := "res://data/content_packs.json"
const MANIFEST_SCHEMA := 1
const DIRECTORY_ARGUMENT := "--content-packs="
const DIRECTORY_VARIABLE := "RABBITLANDS_CONTENT_PACKS"
const PACKS_DIRECTORY := "packs"
const REPAIR_TITLE := "Rabbit Lands"
const REPAIR_MESSAGE := "Some game files are missing or damaged. Close the game and run the updater to repair."
## The installation's update owner is its release descriptor's "distribution"
## (Release.update_owner: a missing field is a GitHub installation). Steam and
## standalone builds ship no updater, so the message names their own repair.
const RELEASE_DESCRIPTOR := "res://data/client_release.json"
const REPAIR_MESSAGES := {
	"github": REPAIR_MESSAGE,
	"steam": "Some game files are missing or damaged. Close the game and use Steam's Verify integrity of game files to repair.",
	"standalone": "Some game files are missing or damaged. Close the game and install Rabbit Lands again from its original download page to repair.",
}

## The cumulative report of this process's mounts (empty until mount() runs).
static var _report: Dictionary = {}
## Absolute pack path -> true once load_resource_pack accepted it in this process.
static var _mounted: Dictionary = {}
## The repair message is shown once per process.
static var _alerted := false
static var _pack_file := RegEx.create_from_string("^packs/[a-z0-9][a-z0-9-]*\\.pck$")

func _init() -> void:
	mount()

## Mounts the manifest's required packs (and its feature packs too when
## include_features is true) once per process; later calls mount only what is
## still unmounted and return the cumulative report:
## {"schema", "state": "off"|"none"|"mounted"|"failed", "directory", "usec",
##  "packs": [{"file", "bytes", "feature", "state", "usec" (the mount), "check_usec"
##  (existence and size), "error"}]}.
static func mount(include_features := false) -> Dictionary:
	if OS.has_feature("web") or Engine.is_editor_hint():
		if _report.is_empty():
			_report = {"schema": MANIFEST_SCHEMA, "state": "off", "packs": []}
		return _report
	if not FileAccess.file_exists(MANIFEST):
		if _report.is_empty():
			_report = {"schema": MANIFEST_SCHEMA, "state": "none", "packs": []}
		return _report
	if _report.get("state") in ["mounted", "failed"] and not include_features:
		return _report
	var directory := resolve_directory(OS.get_cmdline_args(), OS.get_cmdline_user_args(),
		OS.get_environment(DIRECTORY_VARIABLE), OS.get_executable_path(), OS.has_feature("editor"))
	var report := mount_manifest(FileAccess.get_file_as_string(MANIFEST), directory, include_features)
	_report = report
	print("client_diagnostic ", JSON.stringify(diagnostic_row(report)))
	if report.state == "failed":
		for row: Dictionary in report.packs:
			if not str(row.get("error", "")).is_empty():
				push_error("Content pack %s: %s" % [row.get("file", "?"), row.error])
		if DisplayServer.get_name() != "headless" and not _alerted:
			_alerted = true
			OS.alert(repair_message(FileAccess.get_file_as_string(RELEASE_DESCRIPTOR)
				if FileAccess.file_exists(RELEASE_DESCRIPTOR) else ""), REPAIR_TITLE)
	return report

static func current_report() -> Dictionary:
	return _report.duplicate(true)

## The repair message for a release descriptor's text (the updater's unless the
## descriptor names Steam or a standalone build).
static func repair_message(descriptor_text: String) -> String:
	var json := JSON.new()
	var parsed: Variant = json.data if not descriptor_text.is_empty() and json.parse(descriptor_text) == OK else null
	var update_owner := str(parsed.get("distribution", "github")) if parsed is Dictionary else "github"
	return str(REPAIR_MESSAGES.get(update_owner, REPAIR_MESSAGE))

## The folder holding the pack files: --content-packs=DIR or the variable on an
## editor binary only, else the executable's packs/ folder.
static func resolve_directory(args: PackedStringArray, user_args: PackedStringArray, variable: String,
		executable: String, editor_binary: bool) -> String:
	if editor_binary:
		for argument: String in Array(args) + Array(user_args):
			if argument.begins_with(DIRECTORY_ARGUMENT) and argument.length() > DIRECTORY_ARGUMENT.length():
				return argument.trim_prefix(DIRECTORY_ARGUMENT)
		if not variable.is_empty():
			return variable
	return executable.get_base_dir().path_join(PACKS_DIRECTORY)

## Mounts the packs one manifest text lists from `directory` (no logging; mount()
## logs). A pack another call of this process mounted reports "already".
static func mount_manifest(text: String, directory: String, include_features := false) -> Dictionary:
	var started := Time.get_ticks_usec()
	var report := {"schema": MANIFEST_SCHEMA, "state": "mounted", "directory": directory, "packs": [],
		"usec": 0}
	var json := JSON.new()
	var parsed: Variant = json.data if json.parse(text) == OK else null
	if not parsed is Dictionary or int(parsed.get("schema", 0)) != MANIFEST_SCHEMA \
			or not parsed.get("packs") is Array:
		report.state = "failed"
		report.packs.append({"file": MANIFEST.trim_prefix("res://"), "state": "invalid",
			"error": "the content pack manifest is unreadable or has an unknown schema"})
		report.usec = Time.get_ticks_usec() - started
		return report
	var seen := {}
	for value: Variant in parsed.packs:
		var row := _mount_row(value, directory, include_features, seen)
		report.packs.append(row)
		if row.state in ["missing", "size", "refused", "invalid"] and str(row.get("feature", "")).is_empty():
			report.state = "failed"
	report.usec = Time.get_ticks_usec() - started
	return report

static func _mount_row(value: Variant, directory: String, include_features: bool, seen: Dictionary) -> Dictionary:
	if not value is Dictionary:
		return {"file": "?", "state": "invalid", "error": "a manifest row is not an object"}
	var file := str(value.get("file", ""))
	var feature := str(value.get("feature", ""))
	var row := {"file": file, "bytes": int(value.get("bytes", -1)), "feature": feature, "state": "", "usec": 0}
	if _pack_file.search(file) == null or seen.has(file) or row.bytes < 0:
		row.state = "invalid"
		row.error = "bad or repeated pack row"
		return row
	seen[file] = true
	if not feature.is_empty() and not include_features:
		row.state = "skipped"
		return row
	var path := directory.path_join(file.get_file())
	if _mounted.has(path):
		row.state = "already"
		return row
	var checked := Time.get_ticks_usec()
	var exists := FileAccess.file_exists(path)
	var handle := FileAccess.open(path, FileAccess.READ) if exists else null
	var size := handle.get_length() if handle != null else -1
	handle = null
	row.check_usec = Time.get_ticks_usec() - checked
	if not exists:
		row.state = "missing"
		row.error = "not found at " + path
		return row
	if size != row.bytes:
		row.state = "size"
		row.error = "%d bytes, expected %d" % [size, row.bytes]
		return row
	var started := Time.get_ticks_usec()
	var accepted := ProjectSettings.load_resource_pack(path, false)
	row.usec = Time.get_ticks_usec() - started
	if not accepted:
		row.state = "refused"
		row.error = "the engine did not accept the pack"
		return row
	_mounted[path] = true
	row.state = "mounted"
	return row

## The content_packs record in ClientDiagnostics.record's shape (that script
## cannot be named here: see the header).
static func diagnostic_row(report: Dictionary) -> Dictionary:
	var packs := []
	for row: Dictionary in report.get("packs", []):
		var compact := {"file": row.get("file", ""), "state": row.get("state", ""), "usec": row.get("usec", 0)}
		if row.has("check_usec"):
			compact["check_usec"] = row.check_usec
		if not str(row.get("error", "")).is_empty():
			compact["error"] = row.error
		packs.append(compact)
	return {"event": "content_packs", "state": report.get("state", ""), "directory": report.get("directory", ""),
		"usec": report.get("usec", 0), "packs": packs, "elapsed_ms": Time.get_ticks_msec(),
		"time_utc": Time.get_datetime_string_from_system(true)}

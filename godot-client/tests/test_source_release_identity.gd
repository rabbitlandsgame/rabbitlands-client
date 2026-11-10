extends SceneTree
## What a game declares to the server's release policy: source_identity.gd
## declared(), sent by network_client._send_release_identity.
const Release = preload("res://src/updates/release.gd")
const SourceIdentity = preload("res://src/network/source_identity.gd")
const REQUIRED := "2baffec573a8d992985b9a363137b75b338b6f2e"
var _failures := 0

func expect(value: bool, message: String) -> void:
	if not value:
		_failures += 1
		push_error(message)

func _git(directory: String, arguments: Array) -> String:
	var output: Array = []
	if OS.execute("git", ["-C", directory] + arguments, output) != 0 or output.is_empty():
		return ""
	return str(output[0]).strip_edges()

func _write(path: String, text: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()

## Includes hidden entries: `.git` is hidden, and its objects are read-only on Windows.
func _remove_tree(path: String) -> Error:
	var directory := DirAccess.open(path)
	if directory == null:
		return DirAccess.get_open_error()
	directory.include_hidden = true
	for name in directory.get_directories():
		_remove_tree(path.path_join(name))
	for name in directory.get_files():
		var file := path.path_join(name)
		FileAccess.set_read_only_attribute(file, false)
		DirAccess.remove_absolute(file)
	return DirAccess.remove_absolute(path)

## A throwaway checkout: two commits whose tracked project is godot-client/,
## plus an untracked copy of the project inside it.
func _fixture() -> String:
	var root := OS.get_temp_dir().path_join("rl-source-identity-%d-%d" % [OS.get_process_id(), Time.get_ticks_usec()])
	DirAccess.make_dir_recursive_absolute(root.path_join("godot-client"))
	var identity := ["-c", "user.name=test", "-c", "user.email=test@invalid", "-c", "commit.gpgsign=false"]
	_git(root, ["init", "-q"])
	_write(root.path_join("godot-client/project.godot"), "config_version=5\n")
	_git(root, ["add", "godot-client/project.godot"])
	_git(root, identity + ["commit", "-q", "-m", "first"])
	_write(root.path_join("godot-client/notes.txt"), "second\n")
	_git(root, ["add", "godot-client/notes.txt"])
	_git(root, identity + ["commit", "-q", "-m", "second"])
	DirAccess.make_dir_recursive_absolute(root.path_join("copy"))
	_write(root.path_join("copy/project.godot"), "config_version=5\n")
	return root

func _initialize() -> void:
	# Stamped descriptors are sent exactly as written, and never ask git.
	var installed := {"schema": 1, "commit": REQUIRED, "platform": "windows", "ancestors": [REQUIRED]}
	var browser := {"schema": 1, "commit": REQUIRED, "platform": "source", "distribution": "standalone",
		"ancestors": [REQUIRED]}
	var installed_before := installed.duplicate(true)
	var browser_before := browser.duplicate(true)
	SourceIdentity.reset()
	expect(SourceIdentity.declared(installed) == installed_before, "a stamped installed build declares its own descriptor")
	expect(SourceIdentity.declared(browser) == browser_before, "a stamped browser build declares its own descriptor")
	expect(SourceIdentity._checkout.is_empty(), "a stamped descriptor does not run git")

	# A checkout older than the required release declares its own history and
	# is still refused; a copy that is not its checkout's tracked project, and a
	# folder outside any checkout, declare nothing.
	var fixture := _fixture()
	var old := SourceIdentity.checkout_identity(fixture.path_join("godot-client"))
	var old_head := _git(fixture, ["rev-parse", "HEAD"])
	expect(old.get("commit") == old_head, "a checkout declares HEAD")
	expect(old.get("ancestors", []).size() == 2 and old.ancestors[0] == old_head, "a checkout declares its whole history from HEAD")
	expect(not Release.contains_commit(old, REQUIRED), "a checkout behind the required release does not contain it")
	expect(SourceIdentity.checkout_identity(fixture.path_join("copy")).is_empty(), "an untracked copy of the project declares nothing")
	expect(SourceIdentity.checkout_identity(fixture).is_empty(), "a folder without project.godot declares nothing")
	expect(SourceIdentity.checkout_identity("").is_empty(), "an empty res:// path declares nothing")
	expect(_remove_tree(fixture) == OK and not DirAccess.dir_exists_absolute(fixture), "the fixture checkout is removed")

	# This checkout: the committed stub declares the checkout's git history.
	var project := ProjectSettings.globalize_path("res://")
	var stub := Release.read_json("res://data/client_release.json")
	var stub_before := stub.duplicate(true)
	expect(stub.get("platform") == "source" and str(stub.get("commit", "")) == "",
		"the committed descriptor is the unstamped source stub")
	SourceIdentity.reset()
	var declared := SourceIdentity.declared(stub)
	var head := _git(project, ["rev-parse", "HEAD"])
	expect(declared.get("commit") == head, "this checkout declares HEAD")
	var history: Array = declared.get("ancestors", [])
	expect(history.size() == int(_git(project, ["rev-list", "--count", "HEAD"])), "this checkout declares its whole history")
	for entry: Variant in history:
		if not Release.valid_commit(entry):
			expect(false, "every declared ancestor is a full commit")
			break
	if _git(project, ["rev-parse", "--is-shallow-repository"]) == "false":
		expect(Release.contains_commit(declared, REQUIRED), "this checkout, after the required release, contains it")
	expect(declared.get("platform") == "source" and declared.get("repository") == stub.get("repository"),
		"the stub's other fields are kept")
	expect(stub == stub_before, "the stub itself is not changed")

	print("source release identity tests: %s" % ("PASS" if _failures == 0 else "%d FAILED" % _failures))
	quit(1 if _failures else 0)

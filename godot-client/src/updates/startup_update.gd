extends Node
## Discovery is read-only. Only an accepted prompt may start the installed updater.
const Release = preload("res://src/updates/release.gd")
const Launch = preload("res://src/updates/launch_options.gd")
const Transport = preload("res://src/updates/update_transport.gd")
const REPOSITORY := "rabbitlandsgame/rabbitlands-client"
const COMPATIBILITY_NOTE := "This client may have compatibility issues. Please update as soon as possible."
signal notice_changed(message: String)
var identity: Dictionary = {}
var published: Dictionary = {}
var declined := false
var finished := false
var dialog: AcceptDialog
var _transport: Node

func _ready() -> void:
	if DisplayServer.get_name() == "headless":
		finished = true # A noninteractive process cannot answer an update prompt.
		return
	_check.call_deferred()

func _source_identity() -> Dictionary:
	var result := identity.duplicate(true)
	if not OS.has_feature("editor") and result.get("platform", "source") != "source":
		return result
	result = {"platform": "source", "distribution": "github", "repository": REPOSITORY}
	var output: Array = []
	var directory := ProjectSettings.globalize_path("res://")
	if OS.execute("git", ["-C", directory, "rev-parse", "HEAD"], output) == 0 and not output.is_empty():
		result.commit = str(output[0]).strip_edges()
	output.clear()
	if Release.valid_commit(result.get("commit")) and OS.execute("git", ["-C", directory, "rev-list", "HEAD"], output) == 0:
		result.ancestors = Array(str(output[0]).strip_edges().split("\n"))
	return result

func _check() -> void:
	if Release.update_owner(identity) != "github":
		finished = true
		return
	identity = _source_identity()
	# Store installations retain their store's update ownership.
	if Release.update_owner(identity) != "github" or OS.get_name() not in ["Windows", "Linux"]:
		finished = true
		return
	_transport = _new_transport()
	add_child(_transport)
	var platform := "windows" if OS.get_name() == "Windows" else "linux"
	var key := str(identity.get("public_key", ""))
	if key == "" and FileAccess.file_exists("res://data/update_public.pem"):
		key = FileAccess.get_file_as_string("res://data/update_public.pem")
	var trust := {"distribution": "github", "repository": REPOSITORY, "platform": platform, "public_key": key}
	var fetched: Dictionary = await _transport.fetch("https://github.com/%s/releases/latest/download/RabbitLands-%s.json" % [REPOSITORY, platform])
	if fetched.has("error"):
		# Pre-package releases have no stable alias. Discover their signed manifest
		# through GitHub's public latest-release metadata instead.
		fetched = await _transport.fetch("https://api.github.com/repos/%s/releases/latest" % REPOSITORY)
		var metadata := _body(fetched)
		var manifest_url := ""
		var assets: Variant = metadata.get("assets", [])
		if not assets is Array:
			assets = []
		for asset: Variant in assets:
			if not asset is Dictionary:
				continue
			var name := str(asset.get("name", ""))
			var url := str(asset.get("browser_download_url", ""))
			if name.ends_with("-%s.json" % platform) and url.begins_with("https://github.com/%s/releases/download/" % REPOSITORY):
				manifest_url = url
				break
		fetched = await _transport.fetch(manifest_url) if manifest_url != "" else {"error": "No published client manifest."}
	var envelope := _body(fetched)
	published = published_identity(envelope, trust)
	if published.has("error"):
		finished = true
		return
	var relation := relationship(identity, published)
	if relation == "unknown" and Release.valid_commit(identity.get("commit")):
		fetched = await _transport.fetch("https://api.github.com/repos/%s/compare/%s...%s" % [REPOSITORY, identity.commit, published.commit])
		var compared := _body(fetched)
		# With installed as base and published as head, 'ahead' means an update.
		if compared.get("base_commit") is Dictionary and compared.base_commit.get("sha") == identity.commit:
			relation = {"ahead": "behind", "behind": "ahead", "identical": "current", "diverged": "diverged"}.get(compared.get("status", ""), "unknown")
	if relation == "behind":
		_show_update()
	elif relation == "unknown" and not Release.valid_commit(identity.get("commit")):
		_show_update() # Unidentified custom builds get instructions, never replacement.
	finished = true

static func _body(response: Dictionary) -> Dictionary:
	if response.has("error"):
		return {}
	var value: Variant = JSON.parse_string(response.get("body", PackedByteArray()).get_string_from_utf8())
	return value if value is Dictionary else {}

static func published_identity(envelope: Dictionary, trust: Dictionary) -> Dictionary:
	var release := Release.verify_envelope(envelope, trust)
	if release.has("error"):
		return release
	if not Release.valid_commit(release.get("commit")) or release.get("platform") != trust.platform or release.get("repository", trust.repository) != trust.repository:
		return {"error": "The published release identity is invalid."}
	if release.has("ancestors"):
		if not release.ancestors is Array or release.ancestors.size() > 100000 or not release.commit in release.ancestors:
			return {"error": "The published release history is invalid."}
		for commit: Variant in release.ancestors:
			if not Release.valid_commit(commit):
				return {"error": "The published release history is invalid."}
	return release

static func relationship(installed: Dictionary, release: Dictionary) -> String:
	if Release.contains_commit(installed, release.commit):
		return "current" if installed.get("commit") == release.commit else "ahead"
	if Release.valid_commit(installed.get("commit")) and release.has("ancestors"):
		return "behind" if installed.commit in release.ancestors else "diverged"
	return "unknown"

func can_auto_update() -> bool:
	if OS.has_feature("editor") or not identity.get("release_build", false) or Release.update_owner(identity) != "github":
		return false
	var root := Release.install_root()
	var descriptor := Release.read_json(root.path_join("app/client-release.json"))
	return descriptor == identity and FileAccess.file_exists(updater_path()) and not Release.is_link(updater_path())

func updater_path() -> String:
	return Release.install_root().path_join("RabbitLands-updater.exe" if identity.get("platform") == "windows" else "RabbitLands-updater.x86_64")

static func manual_commands(release: Dictionary, installed: Dictionary) -> String:
	var tag := "client-" + str(release.commit)
	var commands := "git status --short\ngit fetch origin tag %s\ngit log --oneline HEAD..%s\ngit merge --ff-only %s" % [tag, tag, tag]
	if installed.get("platform", "source") == "source":
		commands += "\ngodot --headless --path godot-client --editor --import\ngodot --path godot-client"
	else:
		commands += "\npython godot-client/tools/package_client.py --ref %s --platform %s --no-client-updates --out ../dist/custom-client" % [release.commit, installed.platform]
	return commands

func _show_update() -> void:
	if is_instance_valid(dialog):
		return
	var text := "A newer Rabbit Lands release is available (%s)." % str(published.commit).left(9)
	if not Release.valid_commit(identity.get("commit")):
		text = "The published Rabbit Lands release is %s. This build has no recorded commit to compare." % str(published.commit).left(9)
	if can_auto_update():
		var question := ConfirmationDialog.new()
		question.title = "Rabbit Lands update available"
		question.dialog_text = text + "\n\nUpdate now? The game will close, install the update, and reopen in the same launch mode."
		question.ok_button_text = "Yes, update"
		question.cancel_button_text = "No, keep playing"
		question.confirmed.connect(_accept_update)
		question.canceled.connect(_decline_update)
		dialog = question
	else:
		dialog = AcceptDialog.new()
		dialog.title = "Update your custom build"
		dialog.ok_button_text = "Continue playing"
		var instructions := TextEdit.new()
		instructions.custom_minimum_size = Vector2(690, 340)
		instructions.editable = false
		instructions.add_theme_color_override("font_readonly_color", Color("eeeeee"))
		instructions.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
		instructions.text = text + "\n\nThis custom build or installation without an updater needs a manual update. In your source checkout, review and save local changes, then run:\n\n" + manual_commands(published, identity) + "\n\nUse your Godot 4.7.2 executable in place of godot. If the merge stops because your branch has diverged, merge deliberately.\n\n" + COMPATIBILITY_NOTE
		dialog.add_child(instructions)
		dialog.add_button("Copy commands", false, "copy")
		dialog.custom_action.connect(func(action: StringName) -> void:
			if action == "copy":
				DisplayServer.clipboard_set(manual_commands(published, identity)))
		dialog.confirmed.connect(_decline_update)
		dialog.canceled.connect(_decline_update)
	add_child(dialog)
	dialog.popup_centered()
	notice_changed.emit(text)

func _decline_update() -> void:
	declined = true
	notice_changed.emit(COMPATIBILITY_NOTE)

func _accept_update() -> void:
	# Recheck ownership immediately before spawning. A failed spawn leaves the
	# current game open, with a useful notice instead of a lost session.
	if not can_auto_update():
		notice_changed.emit("The updater is missing or this is a custom build. Run the latest installer to repair it.")
		return
	var args := PackedStringArray(["--", "--root", Release.install_root(), "--install-update", "--wait-for-pid", str(OS.get_process_id()),
		"--resume-client", Launch.encode_context(Launch.current_context(Release.install_root()))])
	if _start_updater(args) <= 0:
		notice_changed.emit("The updater could not start. Keep playing or run it from the game folder. " + COMPATIBILITY_NOTE)
		return
	_close_client()

func _close_client() -> void:
	get_tree().quit()

func _start_updater(args: PackedStringArray) -> int:
	return OS.create_process(updater_path(), args)

func _new_transport() -> Node:
	return Transport.new()

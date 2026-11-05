extends Node
## Discovery is read-only. Only an accepted prompt may start the installed updater.
const Release = preload("res://src/updates/release.gd")
const Launch = preload("res://src/updates/launch_options.gd")
const Transport = preload("res://src/updates/update_transport.gd")
const REPOSITORY := "rabbitlandsgame/rabbitlands-client"
const COMPATIBILITY_NOTE := "This client may have compatibility issues. Please update as soon as possible."
signal notice_changed(message: String)
# A failed server-target rediscovery is tried again after this long at most.
const TARGET_RETRY_MSEC := 300000
var identity: Dictionary = {}
var published: Dictionary = {}
var declined := false
var finished := false
var dialog: AcceptDialog
var _transport: Node
# How this launch found `published`: "pointer", "alias", "api" or "server target".
var discovered_via := ""
# A server's required commit (server_target) and the updater arguments that
# install exactly it, once rediscovery found its signed manifest.
var _target := ""
var _target_args := PackedStringArray()
var _target_retry_msec := 0
var _target_busy := false

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

func _trust() -> Dictionary:
	var key := str(identity.get("public_key", ""))
	if key == "" and FileAccess.file_exists("res://data/update_public.pem"):
		key = FileAccess.get_file_as_string("res://data/update_public.pem")
	return {"distribution": "github", "repository": REPOSITORY, "platform": "windows" if OS.get_name() == "Windows" else "linux", "public_key": key}

# The installation whose release record and pointer mark this game reads: an
# installed build only (a source or editor run keeps no discovery state).
func _install_root() -> String:
	return Release.install_root() if identity.get("platform", "source") != "source" else ""

func _installed_sequence() -> int:
	var root := _install_root()
	return Release.installed_sequence(root, identity.get("commit")) if root != "" else 0

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
	var trust := _trust()
	var platform: String = trust.platform
	var root := _install_root()
	var installed_sequence := _installed_sequence()
	# The signed R2 pointer first. When it names this build's commit or one of
	# its ancestors, this build is current (or ahead): no manifest is fetched.
	var envelope: Dictionary = {}
	var admitted := false
	var pointer: Dictionary = await Release.fetch_pointer(_transport, trust, maxi(Release.stored_pointer_sequence(root), installed_sequence) if root != "" else 0)
	if not pointer.has("error"):
		if root != "":
			Release.store_pointer_sequence(root, int(pointer.sequence))
		if Release.contains_commit(identity, pointer.target.commit):
			discovered_via = "pointer"
			finished = true
			return
		var pointed: Dictionary = await Release.fetch_pointed_manifest(_transport, pointer)
		var candidate: Dictionary = pointed if pointed.has("error") else published_identity(pointed.envelope, trust)
		if not candidate.has("error") and Release.matches_pointer(candidate, pointer):
			envelope = pointed.envelope
			admitted = pointer.rollback
			discovered_via = "pointer"
	if envelope.is_empty():
		envelope = await _alias_envelope(platform)
	published = published_identity(envelope, trust)
	if published.has("error") or Release.downgrade_error(published, installed_sequence, admitted) != "":
		finished = true
		return
	var relation := relationship(identity, published)
	if relation == "unknown" and Release.valid_commit(identity.get("commit")):
		var fetched: Dictionary = await _transport.fetch("https://api.github.com/repos/%s/compare/%s...%s" % [REPOSITORY, identity.commit, published.commit])
		var compared := _body(fetched)
		# With installed as base and published as head, 'ahead' means an update.
		if compared.get("base_commit") is Dictionary and compared.base_commit.get("sha") == identity.commit:
			relation = {"ahead": "behind", "behind": "ahead", "identical": "current", "diverged": "diverged"}.get(compared.get("status", ""), "unknown")
	if relation == "behind":
		_show_update()
	elif relation == "unknown" and not Release.valid_commit(identity.get("commit")):
		_show_update() # Unidentified custom builds get instructions, never replacement.
	finished = true

# Today's discovery: the GitHub latest-release alias, then (for pre-package
# releases without one) the API's latest-release metadata.
func _alias_envelope(platform: String) -> Dictionary:
	var fetched: Dictionary = await _transport.fetch("https://github.com/%s/releases/latest/download/RabbitLands-%s.json" % [REPOSITORY, platform])
	discovered_via = "alias"
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
		discovered_via = "api"
	return _body(fetched)

## The game server requires `commit`, which this build does not contain
## (packet 206, client_updates.gd). Discovery runs again and bypasses the
## pointer, which may be frozen: the GitHub alias first, then the notice's
## `manifest_url` (a GitHub release download or an R2 manifest copy). Only a
## signed manifest of exactly that commit, not older than the installed
## release, is offered; accepting it starts the updater for that commit.
## One rediscovery runs at a time (the transport serves one request at a
## time); a notice that arrives meanwhile is left to a later notice.
func server_target(commit: String, manifest_url: String) -> void:
	if _target_busy or declined or not Release.valid_commit(commit) or commit == _target or Time.get_ticks_msec() < _target_retry_msec or not _interactive():
		return
	_target_busy = true
	_target = commit
	await _rediscover_target(commit, manifest_url)
	_target_busy = false

func _rediscover_target(commit: String, manifest_url: String) -> void:
	while not finished:
		await get_tree().process_frame
	if declined or is_instance_valid(dialog) or _transport == null or Release.contains_commit(identity, commit):
		return
	var trust := _trust()
	var sources: Array[String] = ["https://github.com/%s/releases/latest/download/RabbitLands-%s.json" % [REPOSITORY, trust.platform]]
	if Release.target_manifest_url(manifest_url, REPOSITORY, trust.platform):
		sources.append(manifest_url)
	for url: String in sources:
		var fetched: Dictionary = await _transport.fetch(url)
		var named := Release.r2_manifest_sha256(url, trust.platform)
		if fetched.has("error") or (named != "" and Release.bytes_sha256(fetched.body) != named):
			continue
		var release := published_identity(_body(fetched), trust)
		if release.has("error") or not Release.same_text(release.commit, commit) or Release.downgrade_error(release, _installed_sequence()) != "":
			continue
		# Declined or already prompted meanwhile: an open prompt keeps the
		# release and updater arguments it was shown with.
		if declined or is_instance_valid(dialog):
			return
		published = release
		discovered_via = "server target"
		_target_args = PackedStringArray(["--target-commit=" + commit])
		if sources.size() > 1:
			_target_args.append("--target-manifest-url=" + manifest_url)
		_show_update()
		return
	# Not published yet (or not reachable): a later notice may try again.
	_target = ""
	_target_retry_msec = Time.get_ticks_msec() + TARGET_RETRY_MSEC

# A noninteractive (headless) process cannot answer an update prompt.
func _interactive() -> bool:
	return DisplayServer.get_name() != "headless"

static func _body(response: Dictionary) -> Dictionary:
	if response.has("error"):
		return {}
	var value: Variant = JSON.parse_string(response.get("body", PackedByteArray()).get_string_from_utf8())
	return value if value is Dictionary else {}

static func published_identity(envelope: Dictionary, trust: Dictionary) -> Dictionary:
	var release := Release.verify_envelope(envelope, trust)
	if release.has("error"):
		return release
	# A signed pointer (or any other kind of signed record) is not a release.
	if release.has("kind"):
		return {"error": "The published release identity is invalid."}
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
	if not _target_args.is_empty():
		text = "The game server requires Rabbit Lands release %s." % str(published.commit).left(9)
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
	# A server's required commit: the updater installs exactly that release.
	args.append_array(_target_args)
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

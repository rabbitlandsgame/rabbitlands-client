extends RefCounted
## The build a game run from a source checkout declares to the server.
##
## A checkout's res://data/client_release.json is the committed stub, with no
## commit, so once the server's release policy enforced a minimum (2026-11-10)
## it refused every run from a checkout. A checkout states the commit and history
## git reports for it instead, so the policy admits it at or after the required
## release and refuses an older one, whose recipe list and protocol are older too.
##
## Only an editor-binary run of a real checkout asks git: a stamped descriptor
## (an installed game, a browser build), an export, a web build, or a copy of the
## project that is not its checkout's own tracked project all declare the
## descriptor unchanged. Like every declared build this is not an attestation.
##
## This is game code on purpose, and lives outside src/updates/: release.gd is
## an updater-helper input (tools/desktop_helpers.py HELPER_SCRIPTS), so a change
## there would rebuild the updater and hand every installation over to it for
## nothing, and every src/updates/*.gd is part of the release asset and world
## cache keys (tools/release_asset_cache.py, tools/desktop_release_ci.py).
const Release = preload("res://src/updates/release.gd")
## The server's MAX_ANCESTORS (eloria/client_updates.py).
const MAX_ANCESTORS := 100000

static var _checkout: Dictionary = {}

static func declared(identity: Dictionary) -> Dictionary:
	if identity.get("platform", "source") != "source" or Release.valid_commit(identity.get("commit")):
		return identity
	if not OS.has_feature("editor") or OS.has_feature("web"):
		return identity
	if _checkout.is_empty():
		# Only an answer is kept: a failed lookup is tried again on the next connect.
		_checkout = checkout_identity(ProjectSettings.globalize_path("res://"))
	if _checkout.is_empty():
		return identity
	var result := identity.duplicate(true)
	result.commit = _checkout.commit
	result.ancestors = (_checkout.ancestors as Array).duplicate()
	return result

## HEAD and its whole history for the checkout whose tracked project is
## `directory`, or {} when git cannot say or `directory` is not that project.
static func checkout_identity(directory: String) -> Dictionary:
	if directory.is_empty() or not directory.is_absolute_path() \
			or not FileAccess.file_exists(directory.path_join("project.godot")):
		return {}
	var output: Array = []
	if OS.execute("git", ["-C", directory, "ls-files", "--error-unmatch", "project.godot"], output) != 0:
		return {}
	output.clear()
	if OS.execute("git", ["-C", directory, "rev-list", "HEAD"], output) != 0 or output.is_empty():
		return {}
	var history := Array(str(output[0]).strip_edges().split("\n"))
	if history.is_empty() or history.size() > MAX_ANCESTORS:
		return {}
	for entry: Variant in history:
		if not Release.valid_commit(entry):
			return {}
	return {"commit": history[0], "ancestors": history}

## For tests: forget the cached checkout.
static func reset() -> void:
	_checkout = {}

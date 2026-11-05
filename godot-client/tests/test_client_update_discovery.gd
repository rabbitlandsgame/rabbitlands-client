extends SceneTree
## Release discovery (W1b): the signed R2 pointer, the installed-release record,
## the pointer high-water mark, the downgrade guard, server-target rediscovery
## and the handover hop guard. Every request goes to a scripted in-process
## transport: nothing here reaches a network. Run by run_client_update_tests.py
## in a project whose data/client_release.json holds the test public key.
const Release = preload("res://src/updates/release.gd")
const Bootstrap = preload("res://src/updates/bootstrap.gd")
const LaunchOptions = preload("res://src/updates/launch_options.gd")
const StartupUpdate = preload("res://src/updates/startup_update.gd")
const Launcher = preload("res://src/updates/launcher.gd")
const REPOSITORY := "rabbitlandsgame/rabbitlands-client"
const PRODUCTION_ASSETS := "https://assets.rabbitlandsgame.com/desktop/v1/"
const ALIAS := "https://github.com/rabbitlandsgame/rabbitlands-client/releases/latest/download/RabbitLands-windows.json"
const POINTER := PRODUCTION_ASSETS + "channels/live/windows.json"
const S := 1762300000
var A := "a".repeat(40)
var B := "b".repeat(40)
var C := "c".repeat(40)
var D := "d".repeat(40)
var _failures := 0
var _key: CryptoKey
var _other_key: CryptoKey
var _trust: Dictionary
var _root := ""

class FakeTransport extends "res://src/updates/update_transport.gd":
	# url -> body bytes, or a failure dictionary. Unknown URLs answer 404.
	var responses: Dictionary = {}
	var requests: Array = []
	func fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:
		requests.append({"url": url, "limit": limit, "timeout": _pointer_timeout})
		var response: Variant = responses.get(url)
		if response is Dictionary:
			return response
		if not response is PackedByteArray:
			return {"error": "The update download failed.", "status": 404, "result": HTTPRequest.RESULT_SUCCESS}
		if response.size() > limit:
			return {"error": "The update download failed.", "status": 200, "result": HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED}
		return {"body": response}
	func urls() -> Array:
		return requests.map(func(request: Dictionary) -> String: return request.url)

class SlowTransport extends FakeTransport:
	# Answers a frame later, as a real request does, so overlapping callers interleave.
	func fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:
		await (Engine.get_main_loop() as SceneTree).process_frame
		return super.fetch(url, path, limit)

class TestLauncher extends "res://src/updates/launcher.gd":
	# The real discovery and game-launch code without the updater's startup.
	var launched := PackedStringArray()
	var failed := ""
	func _ready() -> void:
		pass
	func _start_process(_path: String, game_args: PackedStringArray) -> int:
		launched = game_args
		return -1
	func _fail(message: String) -> void:
		failed = message

class CapturingTransport extends "res://src/updates/update_transport.gd":
	# The production transport; only its HTTPRequest objects are kept for inspection.
	var made: Array = []
	func _new_http_request() -> HTTPRequest:
		var request := HTTPRequest.new()
		made.append(request)
		return request

class Client extends "res://src/updates/client_updates.gd":
	# The game's server-notice handling without its HUD and network wiring.
	func _ready() -> void:
		pass

class Probe extends "res://src/updates/startup_update.gd":
	var install_dir := ""
	var fake: Node
	var started := PackedStringArray()
	var closed := false
	func _ready() -> void:
		pass
	func _source_identity() -> Dictionary:
		return identity
	func _install_root() -> String:
		return install_dir
	func can_auto_update() -> bool:
		return true
	func _interactive() -> bool:
		return true
	func _new_transport() -> Node:
		return fake
	func _start_updater(args: PackedStringArray) -> int:
		started = args
		return 123
	func _close_client() -> void:
		closed = true

func expect(value: bool, message: String) -> void:
	if not value:
		_failures += 1
		push_error(message)

var _transports: Array = []

func new_transport() -> FakeTransport:
	var transport := FakeTransport.new()
	_transports.append(transport)
	return transport

func sign_with(payload: Dictionary, key: CryptoKey) -> Dictionary:
	var bytes := JSON.stringify(payload).to_utf8_buffer()
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return {"payload": Marshalls.raw_to_base64(bytes), "signature": Marshalls.raw_to_base64(Crypto.new().sign(HashingContext.HASH_SHA256, hash.finish(), key))}

func signed(payload: Dictionary) -> Dictionary:
	return sign_with(payload, _key)

func bytes_of(envelope: Dictionary) -> PackedByteArray:
	return JSON.stringify(envelope).to_utf8_buffer()

func version_of(commit: String) -> String:
	return "RabbitLands-Windows-20261104-" + commit.left(9)

func manifest(commit: String, sequence: int, ancestors: Array = []) -> Dictionary:
	# Enough for Bootstrap.verify and published_identity (helpers in the shared pool).
	var payload := {"schema": 3, "bootstrap_schema": 1, "commit": commit, "platform": "windows", "repository": REPOSITORY,
		"version": version_of(commit), "ancestors": [commit] + ancestors}
	for kind: String in ["updater", "uninstall"]:
		var digest := (kind + commit).sha256_text()
		payload[kind] = {"url": "https://github.com/%s/releases/download/client-assets/RabbitLands-%s-%s.exe" % [REPOSITORY, kind, digest], "size": 1000, "sha256": digest}
	if sequence > 0:
		payload["sequence"] = sequence
	return payload

func served(transport: FakeTransport, payload: Dictionary, url := "") -> Dictionary:
	# Signs `payload` and serves it at its R2 manifest URL (or `url`).
	var bytes := bytes_of(signed(payload))
	var digest := Release.bytes_sha256(bytes)
	var at := url if url != "" else Release.r2_manifest_url("windows", digest)
	transport.responses[at] = bytes
	return {"bytes": bytes, "sha256": digest, "url": Release.r2_manifest_url("windows", digest), "size": bytes.size()}

func pointer_payload(release: Dictionary, copy: Dictionary, sequence: int, rollback := false) -> Dictionary:
	return {"kind": "rabbitlands-release-pointer", "pointer_schema": 1, "repository": REPOSITORY, "platform": "windows",
		"channel": "live", "sequence": sequence, "rollback": rollback, "release_id": 123456789, "run_id": 987654321,
		"target": {"commit": release.commit, "version": release.version, "manifest_sequence": release.get("sequence", 0),
			"manifest": {"url": copy.url, "sha256": copy.sha256, "size": copy.size}}}

func serve_pointer(transport: FakeTransport, payload: Dictionary) -> void:
	transport.responses[POINTER] = bytes_of(signed(payload))

func installed(commit: String, sequence := 0, mark := 0) -> void:
	# The fixture installation: its descriptor, record and stored pointer mark.
	DirAccess.make_dir_recursive_absolute(_root.path_join("app"))
	Release.save_json(_root.path_join("app/client-release.json"), {"commit": commit, "platform": "windows", "repository": REPOSITORY})
	DirAccess.remove_absolute(_root.path_join(Release.INSTALL_RECORD))
	if sequence > 0:
		expect(Release.save_install_record(_root, {"commit": commit, "platform": "windows", "sequence": sequence}) == OK, "the install record could not be written")
	DirAccess.remove_absolute(Release.cache_for(_root).path_join(Release.POINTER_RECORD))
	if mark > 0:
		Release.store_pointer_sequence(_root, mark)

func deep(value: Variant) -> Variant:
	return JSON.parse_string(JSON.stringify(value))

func changed(base: Dictionary, path: Array, value: Variant) -> Dictionary:
	# A copy of `base` with the field at `path` set (or erased for null).
	var copy: Dictionary = deep(base)
	var node: Dictionary = copy
	for index in path.size() - 1:
		node = node[path[index]]
	if value == null:
		node.erase(path[-1])
	else:
		node[path[-1]] = value
	return copy

func check_pointer_rules() -> void:
	expect(Release.DESKTOP_ASSETS == PRODUCTION_ASSETS, "the shipped R2 base changed")
	expect(Release.pointer_url("windows") == POINTER, "the pointer is not at its derived URL")
	var transport := new_transport()
	var release := manifest(B, S + 100)
	var copy := served(transport, release)
	var base := pointer_payload(release, copy, S + 200)
	var accepted := Release.verify_pointer(signed(base), _trust, S + 200)
	expect(not accepted.has("error") and accepted.target.commit == B, "a valid pointer was refused: %s" % [accepted.get("error", "")])
	expect(not Release.verify_pointer(signed(base), _trust, 0).has("error"), "a pointer was refused without a mark")
	var stale := Release.verify_pointer(signed(base), _trust, S + 201)
	expect(stale.get("error", "").contains("older"), "a pointer older than the mark was accepted")
	expect(Release.verify_pointer(sign_with(base, _other_key), _trust).has("error"), "a pointer signed by another key was accepted")
	var tampered := signed(base)
	tampered.payload = Marshalls.raw_to_base64(JSON.stringify(changed(base, ["target", "commit"], C)).to_utf8_buffer())
	expect(Release.verify_pointer(tampered, _trust).has("error"), "a tampered pointer was accepted")
	expect(Release.verify_pointer("not an envelope", _trust).has("error"), "a non-envelope was accepted")
	var steam := _trust.duplicate()
	steam.distribution = "steam"
	expect(Release.verify_pointer(signed(base), steam).has("error"), "a store installation read a GitHub pointer")
	var refused := {
		"kind": [["kind"], "rabbitlands-desktop-content-set"], "kind number": [["kind"], 1],
		"no kind": [["kind"], null], "extra field": [["extra"], 1], "no run id": [["run_id"], null],
		"release field": [["commit"], B], "schema field": [["schema"], 3], "packages field": [["packages"], []],
		"pointer schema": [["pointer_schema"], 2], "pointer schema text": [["pointer_schema"], "1"],
		"repository": [["repository"], "someone/else"], "platform": [["platform"], "linux"],
		"channel": [["channel"], "test"], "sequence in ms": [["sequence"], (S + 200) * 1000],
		"sequence text": [["sequence"], str(S + 200)], "sequence too small": [["sequence"], 1000],
		"fractional sequence": [["sequence"], S + 200.5], "rollback text": [["rollback"], "false"],
		"release id": [["release_id"], 0], "run id": [["run_id"], -1],
		"target field": [["target", "extra"], 1], "target commit": [["target", "commit"], "B".repeat(40)],
		"short commit": [["target", "commit"], "b".repeat(39)], "version path": [["target", "version"], "a/b"],
		"version empty": [["target", "version"], ""], "version number": [["target", "version"], 7],
		"manifest after pointer": [["target", "manifest_sequence"], S + 200],
		"manifest sequence text": [["target", "manifest_sequence"], str(S + 100)],
		"manifest field": [["target", "manifest", "extra"], 1], "manifest hash": [["target", "manifest", "sha256"], copy.sha256.to_upper()],
		"manifest size": [["target", "manifest", "size"], Release.MAX_MANIFEST_BYTES + 1],
		"manifest size zero": [["target", "manifest", "size"], 0],
		"manifest url host": [["target", "manifest", "url"], copy.url.replace("assets.rabbitlandsgame.com", "assets.example.com")],
		"manifest url platform": [["target", "manifest", "url"], copy.url.replace("/windows/", "/linux/")],
		"manifest url query": [["target", "manifest", "url"], copy.url + "?x=1"],
		"manifest url github": [["target", "manifest", "url"], "https://github.com/%s/releases/download/client-%s/RabbitLands-windows.json" % [REPOSITORY, B]],
		"manifest url other hash": [["target", "manifest", "url"], Release.r2_manifest_url("windows", "e".repeat(64))],
		"manifest url number": [["target", "manifest", "url"], 5],
	}
	for name: String in refused:
		var case: Array = refused[name]
		var result := Release.verify_pointer(signed(changed(base, case[0], case[1])), _trust)
		expect(result.has("error"), "a pointer with a wrong %s was accepted" % [name])
	# Another platform's pointer, even one naming its own platform's manifest.
	var linux := changed(changed(base, ["platform"], "linux"), ["target", "manifest", "url"], copy.url.replace("/windows/", "/linux/"))
	expect(Release.verify_pointer(signed(linux), _trust).has("error"), "a pointer of another platform was accepted")
	# Domain separation: a pointer is no release, and a release is no pointer.
	var pointer_envelope := signed(base)
	expect(Release.verify_manifest(pointer_envelope, _trust).has("error"), "verify_manifest accepted a pointer")
	expect(Bootstrap.verify(pointer_envelope, _trust).has("error"), "Bootstrap.verify accepted a pointer")
	expect(StartupUpdate.published_identity(pointer_envelope, _trust).has("error"), "the game accepted a pointer as a release")
	var kinded := release.duplicate(true)
	kinded["kind"] = "rabbitlands-release-pointer"
	expect(StartupUpdate.published_identity(signed(kinded), _trust).has("error"), "the game accepted a signed record with a kind")
	expect(not StartupUpdate.published_identity(signed(release), _trust).has("error"), "the game refused a release")
	expect(Release.verify_pointer(signed(release), _trust).has("error"), "a release manifest was accepted as a pointer")
	var both := base.duplicate(true)
	both.merge({"commit": B, "schema": 3, "bootstrap_schema": 1})
	expect(Release.verify_pointer(signed(both), _trust).has("error"), "a pointer carrying release fields was accepted")
	# The pointed manifest: its exact bytes, size and identity.
	expect(Release.matches_pointer(release, base), "a release did not match its own pointer")
	expect(not Release.matches_pointer(changed(release, ["sequence"], S + 99), base), "a pointer matched another sequence")
	expect(not Release.matches_pointer(changed(release, ["version"], version_of(C)), base), "a pointer matched another version")
	expect(not Release.matches_pointer(changed(release, ["commit"], C), base), "a pointer matched another commit")
	expect(not Release.matches_pointer(changed(release, ["sequence"], null), base), "a pointer matched a manifest without a sequence")

func check_records() -> void:
	installed(A)
	expect(Release.installed_sequence(_root, A) == 0, "an installation without a record has a sequence")
	expect(Release.save_install_record(_root, {"commit": A, "platform": "windows", "sequence": S}, "f".repeat(64)) == OK, "the record was not saved")
	var record := Release.read_json(_root.path_join(Release.INSTALL_RECORD))
	expect(record.get("schema") == 1 and record.get("commit") == A and record.get("platform") == "windows" and int(record.get("sequence", 0)) == S and record.get("manifest_sha256") == "f".repeat(64), "the record fields are wrong: %s" % [record])
	expect(not FileAccess.file_exists(_root.path_join(Release.INSTALL_RECORD + ".tmp")), "the record was not written by rename")
	expect(Release.installed_sequence(_root, A) == S, "the record's sequence was not read")
	expect(Release.installed_sequence(_root, B) == 0, "a record of another commit was trusted")
	expect(Release.installed_sequence(_root, "not a commit") == 0, "an invalid installed commit was trusted")
	Release.save_install_record(_root, {"commit": A, "platform": "windows"}, "not a hash")
	record = Release.read_json(_root.path_join(Release.INSTALL_RECORD))
	expect(int(record.get("sequence", -1)) == 0 and not record.has("manifest_sha256"), "a pre-R2 release's record is wrong: %s" % [record])
	expect(Release.installed_sequence(_root, A) == 0, "a pre-R2 release has a sequence")
	for text: String in ["{", "[]", '{"schema": "1", "commit": "%s", "sequence": %d}' % [A, S], '{"schema": 1, "commit": 5, "sequence": %d}' % S, '{"schema": 1, "commit": "%s", "sequence": "%d"}' % [A, S], '{"schema": 2, "commit": "%s", "sequence": %d}' % [A, S]]:
		var file := FileAccess.open(_root.path_join(Release.INSTALL_RECORD), FileAccess.WRITE)
		file.store_string(text)
		file.close()
		expect(Release.installed_sequence(_root, A) == 0, "a damaged record was trusted: " + text)
	# The pointer mark: missing or damaged counts as none, and only ever rises.
	var mark := Release.cache_for(_root).path_join(Release.POINTER_RECORD)
	DirAccess.remove_absolute(mark)
	expect(Release.stored_pointer_sequence(_root) == 0, "a missing mark has a value")
	Release.store_pointer_sequence(_root, S + 10)
	expect(Release.stored_pointer_sequence(_root) == S + 10, "the mark was not stored")
	Release.store_pointer_sequence(_root, S + 5)
	expect(Release.stored_pointer_sequence(_root) == S + 10, "the mark was lowered")
	Release.store_pointer_sequence(_root, 12)
	expect(Release.stored_pointer_sequence(_root) == S + 10, "an invalid sequence was stored")
	for text: String in ["", "{", '{"schema": "1", "sequence": %d}' % (S + 10), '{"schema": 1, "sequence": "x"}']:
		var file := FileAccess.open(mark, FileAccess.WRITE)
		file.store_string(text)
		file.close()
		expect(Release.stored_pointer_sequence(_root) == 0, "a damaged mark was trusted: " + text)
	Release.store_pointer_sequence(_root, S + 1)
	expect(Release.stored_pointer_sequence(_root) == S + 1, "a damaged mark was not replaced")
	installed(A, S + 50, S + 20)
	expect(Release.pointer_high_water(_root, A) == S + 50, "the high-water mark ignores the installed release")
	installed(A, S + 50, S + 70)
	expect(Release.pointer_high_water(_root, A) == S + 70, "the high-water mark ignores the stored pointer")
	expect(Release.pointer_high_water(_root, B) == S + 70, "another commit's record raised the mark")

func check_downgrade_guard() -> void:
	var older := manifest(C, S - 100)
	var pre_r2 := manifest(C, 0)
	expect(Release.downgrade_error(older, 0) == "", "an install without a record refused a release (pre-R2 installs behave as before)")
	expect(Release.downgrade_error(older, S) == Release.OLDER_RELEASE_MESSAGE, "an older release was accepted")
	expect(Release.OLDER_RELEASE_MESSAGE == "This update is older than the installed game.", "the downgrade message changed")
	expect(Release.downgrade_error(pre_r2, S) != "", "a pre-R2 manifest (sequence 0) was accepted over an R2 install")
	expect(Release.downgrade_error(older, S, true) == "", "a rollback pointer's release was refused")
	expect(Release.downgrade_error(manifest(B, S), S) == "", "the installed release (repair) was refused")
	expect(Release.downgrade_error(manifest(B, S + 1), S) == "", "a newer release was refused")
	expect(Release.downgrade_error(changed(manifest(B, S + 1), ["sequence"], str(S + 1)), S) != "", "a text sequence counted")

func check_urls_and_arguments() -> void:
	var digest := "e".repeat(64)
	var r2 := Release.r2_manifest_url("windows", digest)
	expect(r2 == PRODUCTION_ASSETS + "manifests/windows/" + digest + ".json", "the R2 manifest URL changed")
	expect(Release.r2_manifest_sha256(r2, "windows") == digest, "the R2 manifest name was not read")
	expect(Release.target_manifest_url(r2, REPOSITORY, "windows"), "an R2 manifest copy was refused as a server target")
	expect(Release.target_manifest_url("https://github.com/%s/releases/download/client-%s/RabbitLands-windows.json" % [REPOSITORY, B], REPOSITORY, "windows"), "a GitHub release manifest was refused")
	for url: Variant in [r2.replace("/windows/", "/linux/"), r2.to_upper(), r2 + "?x", r2.replace(".json", ".bin"), PRODUCTION_ASSETS + "manifests/windows/" + "E".repeat(64) + ".json",
			"http://github.com/%s/releases/download/x/y.json" % REPOSITORY, "https://github.com/other/repo/releases/download/x/y.json",
			PRODUCTION_ASSETS + "channels/live/windows.json", "https://assets.example.com/desktop/v1/manifests/windows/%s.json" % digest, 5, null]:
		expect(not Release.target_manifest_url(url, REPOSITORY, "windows"), "an unknown manifest source was accepted: %s" % [str(url)])
		expect(Release.r2_manifest_sha256(url, "windows") == "", "a non-derived R2 name was read: %s" % [str(url)])
	# Updater-only requests never reach the game or a saved launch context.
	var args := PackedStringArray(["--server=game.example", "--target-commit=" + B, "--target-manifest-url=" + r2, "--handoff-hops=2", "--client-debug"])
	expect(LaunchOptions.without_launcher_flags(args) == PackedStringArray(["--server=game.example", "--client-debug"]), "updater requests leaked to the game")
	var context := LaunchOptions.resume_context(PackedStringArray(["--verbose"]), args)
	expect(context.user == ["--server=game.example", "--client-debug"], "updater requests were saved in a launch context")
	var resumed := LaunchOptions.resume_arguments({"schema": 1, "engine": [], "user": Array(args)})
	expect(not resumed.is_empty() and not "--handoff-hops=2" in resumed and not ("--target-commit=" + B) in resumed, "a saved context passed updater requests on")
	# The request the updater reads, and the next handover's arguments.
	var request := Launcher.update_request(args)
	expect(request.get("target") == B and request.get("target_url") == r2 and request.get("hops") == 2, "the update request was misread: %s" % [request])
	expect(Launcher.update_request(PackedStringArray(["--root", "x"])) == {"target": "", "target_url": "", "hops": 0}, "an ordinary run has a request")
	for bad: Array in [["--target-commit=" + B.to_upper()], ["--target-commit="], ["--target-manifest-url=" + r2], ["--target-commit=" + B, "--target-manifest-url=https://example.com/x.json"],
			["--handoff-hops=x"], ["--handoff-hops=-1"], ["--handoff-hops=1000"]]:
		expect(Launcher.update_request(PackedStringArray(bad)).has("error"), "an invalid update request was accepted: %s" % [str(bad)])
	var next := Launcher.handoff_arguments(args, 3)
	expect(next.count("--handoff-hops=3") == 1 and not "--handoff-hops=2" in next and ("--target-commit=" + B) in next and ("--target-manifest-url=" + r2) in next, "the handover lost the request or the hop count: %s" % [next])
	expect(Launcher.handoff_arguments(PackedStringArray(["--update-only"]), 1) == PackedStringArray(["--update-only", "--handoff-hops=1"]), "the first handover is not counted")
	expect(Launcher.MAX_HANDOFF_HOPS == 3 and Launcher.HOPS_MESSAGE == "Updater versions disagree; try again later.", "the hop guard changed")

func check_transport_limits() -> void:
	# The pointer request: 15 s and 64 KiB; others keep their limits. The URL
	# cannot be parsed, so no request is ever sent.
	var transport := CapturingTransport.new()
	root.add_child(transport)
	var fetched: Dictionary = await transport.fetch_pointer("rabbitlands-test:not-a-url")
	expect(fetched.has("error") and not fetched.has("status"), "an unsendable pointer request was not refused: %s" % [fetched])
	expect(transport.made.size() == 1 and is_equal_approx(transport.made[0].timeout, 15.0) and transport.made[0].body_size_limit == 64 * 1024, "the pointer request has the wrong limits")
	fetched = await transport.fetch("rabbitlands-test:not-a-url")
	expect(transport.made.size() == 2 and is_equal_approx(transport.made[1].timeout, 30.0) and transport.made[1].body_size_limit == Release.MAX_MANIFEST_BYTES, "a manifest request kept the pointer's limits")
	fetched = await transport.fetch("rabbitlands-test:not-a-url", _root.path_join("download.tmp"), 1000)
	expect(transport.made.size() == 3 and is_equal_approx(transport.made[2].timeout, 3600.0), "a file download lost its timeout")
	transport.free()

func check_game_launch_arguments() -> void:
	# The updater strips its own requests before it starts the game.
	var launcher := TestLauncher.new()
	launcher._root = _root
	root.add_child(launcher)
	var url := Release.r2_manifest_url("windows", "e".repeat(64))
	await launcher._launch_game(_trust, PackedStringArray(["--server=game.example", "--install-update", "--target-commit=" + B, "--target-manifest-url=" + url, "--handoff-hops=2", "--client-debug"]))
	expect(launcher.failed.contains("could not start"), "the fixture game start was not reached: " + launcher.failed)
	var user := launcher.launched.slice(launcher.launched.find("--") + 1)
	expect(user == PackedStringArray(["--server=game.example", "--client-debug"]), "updater requests reached the game: %s" % [launcher.launched])
	var context: Variant = JSON.parse_string(Marshalls.base64_to_utf8(OS.get_environment(LaunchOptions.CONTEXT_ENV)))
	expect(context is Dictionary and context.user == ["--server=game.example", "--client-debug"], "updater requests reached the game's launch context: %s" % [str(context)])
	launcher.free()

func new_launcher(transport: FakeTransport) -> TestLauncher:
	var launcher := TestLauncher.new()
	launcher._root = _root
	launcher._transport = transport
	return launcher

func discover(transport: FakeTransport, target := "", target_url := "") -> Dictionary:
	var launcher := new_launcher(transport)
	var result: Dictionary = await launcher._discover(_trust, target, target_url)
	launcher.free()
	return result

func check_launcher_discovery() -> void:
	var current := manifest(A, S)
	var newer := manifest(B, S + 100, [A])
	newer["launch_args"] = ["--a"]
	# Another signed release of exactly the same size: only its SHA-256 differs.
	var same_size := manifest(B, S + 100, [A])
	same_size["launch_args"] = ["--b"]
	expect(bytes_of(signed(same_size)).size() == bytes_of(signed(newer)).size(), "the same-size substitute differs in size")
	var older := manifest(C, S - 100)
	# 1. The pointer first: 64 KiB with the short timeout, then its manifest by size.
	installed(A, S)
	var transport := new_transport()
	var copy := served(transport, newer)
	serve_pointer(transport, pointer_payload(newer, copy, S + 200))
	transport.responses[ALIAS] = bytes_of(signed(current))
	var found := await discover(transport)
	expect(found.get("via") == "pointer" and found.get("body") == copy.bytes and found.get("sha256") == copy.sha256 and found.get("rollback") == false, "the pointer was not used: %s" % [found.get("error", found.get("via"))])
	expect(transport.urls() == [POINTER, copy.url], "pointer discovery requests: %s" % [transport.urls()])
	expect(transport.requests[0].limit == Release.MAX_POINTER_BYTES and is_equal_approx(transport.requests[0].timeout, 15.0), "the pointer is not read with 64 KiB and 15 s: %s" % [transport.requests[0]])
	expect(transport.requests[1].limit == copy.size and is_zero_approx(transport.requests[1].timeout), "the manifest is not limited to its size: %s" % [transport.requests[1]])
	expect(Release.stored_pointer_sequence(_root) == S + 200, "the accepted pointer did not raise the mark")
	# 2. Each pointer failure falls back to the GitHub alias.
	var cases := {
		"missing": func(t: FakeTransport) -> void: t.responses.erase(POINTER),
		"server error": func(t: FakeTransport) -> void: t.responses[POINTER] = {"error": "The update download failed.", "status": 503, "result": 0},
		"challenge page": func(t: FakeTransport) -> void: t.responses[POINTER] = "<html>Just a moment...</html>".to_utf8_buffer(),
		"too large": func(t: FakeTransport) -> void: t.responses[POINTER] = bytes_of(signed(pointer_payload(newer, copy, S + 200))) + " ".repeat(Release.MAX_POINTER_BYTES).to_utf8_buffer(),
		"other key": func(t: FakeTransport) -> void: t.responses[POINTER] = bytes_of(sign_with(pointer_payload(newer, copy, S + 200), _other_key)),
		"stale": func(t: FakeTransport) -> void: serve_pointer(t, pointer_payload(newer, copy, S + 199)),
		"manifest missing": func(t: FakeTransport) -> void: t.responses.erase(copy.url),
		"manifest changed": func(t: FakeTransport) -> void: t.responses[copy.url] = bytes_of(signed(changed(newer, ["launch_args"], ["--x"]))),
		"manifest of the same size": func(t: FakeTransport) -> void: t.responses[copy.url] = bytes_of(signed(same_size)),
		"manifest size": func(t: FakeTransport) -> void: serve_pointer(t, changed(pointer_payload(newer, copy, S + 300), ["target", "manifest", "size"], copy.size - 1)),
		"manifest of another commit": func(t: FakeTransport) -> void: serve_pointer(t, changed(pointer_payload(newer, copy, S + 300), ["target", "commit"], D)),
		"manifest of another sequence": func(t: FakeTransport) -> void: serve_pointer(t, changed(pointer_payload(newer, copy, S + 300), ["target", "manifest_sequence"], S + 101)),
		"manifest signed by another key": func(t: FakeTransport) -> void:
			var bytes := bytes_of(sign_with(newer, _other_key))
			var digest := Release.bytes_sha256(bytes)
			t.responses[Release.r2_manifest_url("windows", digest)] = bytes
			serve_pointer(t, pointer_payload(newer, {"url": Release.r2_manifest_url("windows", digest), "sha256": digest, "size": bytes.size()}, S + 300)),
	}
	for name: String in cases:
		installed(A, S, S + 200)
		transport = new_transport()
		copy = served(transport, newer)
		serve_pointer(transport, pointer_payload(newer, copy, S + 200))
		transport.responses[ALIAS] = bytes_of(signed(current))
		cases[name].call(transport)
		found = await discover(transport)
		expect(found.get("via") == "GitHub alias" and not found.has("error"), "a pointer (%s) did not fall back to the alias: %s" % [name, found])
		expect(transport.urls().back() == ALIAS and transport.urls().count(ALIAS) == 1, "the alias was not read last (%s): %s" % [name, transport.urls()])
		expect(Release.stored_pointer_sequence(_root) >= S + 200, "the mark was lowered (%s)" % [name])
	# 3. A pointer older than the installed release is stale even without a mark.
	installed(A, S + 250)
	transport = new_transport()
	copy = served(transport, newer)
	serve_pointer(transport, pointer_payload(newer, copy, S + 200))
	transport.responses[ALIAS] = bytes_of(signed(manifest(A, S + 250)))
	found = await discover(transport)
	expect(found.get("via") == "GitHub alias", "a pointer older than the installed release was used: %s" % [found])
	expect(transport.urls() == [POINTER, ALIAS], "a stale pointer's manifest was fetched: %s" % [transport.urls()])
	# 4. The downgrade guard: an older manifest only through a rollback pointer naming it.
	installed(B, S + 100)
	transport = new_transport()
	copy = served(transport, older)
	serve_pointer(transport, pointer_payload(older, copy, S + 300))
	transport.responses[ALIAS] = bytes_of(signed(older))
	found = await discover(transport)
	expect(found.get("error") == Release.OLDER_RELEASE_MESSAGE and found.get("fatal") == false, "an older release was installed without a rollback pointer: %s" % [found])
	expect(transport.urls() == [POINTER, copy.url, ALIAS], "downgrade requests: %s" % [transport.urls()])
	installed(B, S + 100)
	serve_pointer(transport, pointer_payload(older, copy, S + 300, true))
	transport.requests.clear()
	found = await discover(transport)
	expect(found.get("via") == "pointer" and found.get("rollback") == true and found.get("sha256") == copy.sha256, "a signed rollback pointer was refused: %s" % [found])
	# ... and a rollback pointer admits only the manifest it names.
	installed(B, S + 100)
	var other_older := manifest(D, S - 50)
	var other_copy := served(transport, other_older)
	serve_pointer(transport, changed(pointer_payload(older, copy, S + 400, true), ["target", "manifest"], {"url": other_copy.url, "sha256": other_copy.sha256, "size": other_copy.size}))
	found = await discover(transport)
	expect(found.has("error"), "a rollback pointer admitted a manifest it does not describe: %s" % [found])
	# A pre-R2 install (no record) accepts the alias as before, even without a sequence.
	installed(A)
	transport = new_transport()
	transport.responses[ALIAS] = bytes_of(signed(manifest(C, 0)))
	found = await discover(transport)
	expect(found.get("via") == "GitHub alias", "a pre-R2 installation refused the alias: %s" % [found])
	# A tampered alias stops the update (as before W1b).
	transport.responses[ALIAS] = bytes_of(sign_with(current, _other_key))
	found = await discover(transport)
	expect(found.get("fatal") == true, "a tampered alias did not stop the update: %s" % [found])
	transport.responses.erase(ALIAS)
	found = await discover(transport)
	expect(found.has("error") and found.get("fatal") == false, "an unreachable alias stopped a launch: %s" % [found])
	# 5. A server target: a pointer naming another commit is skipped, then the
	# alias, then the notice's manifest URL (R2 copy bytes must match its name).
	installed(A, S, S + 200)
	transport = new_transport()
	copy = served(transport, newer)
	serve_pointer(transport, pointer_payload(newer, copy, S + 200))
	transport.responses[ALIAS] = bytes_of(signed(newer))
	var required := manifest(D, S + 150, [A])
	var required_copy := served(transport, required)
	found = await discover(transport, D, required_copy.url)
	expect(found.get("via") == "server target" and found.get("sha256") == required_copy.sha256, "the server target was not found: %s" % [found])
	expect(transport.urls() == [POINTER, ALIAS, required_copy.url], "server target requests: %s" % [transport.urls()])
	transport.requests.clear()
	found = await discover(transport, B)
	expect(found.get("via") == "pointer", "a pointer naming the target was not used: %s" % [found])
	transport.responses[required_copy.url] = bytes_of(signed(changed(required, ["launch_args"], ["--x"])))
	found = await discover(transport, D, required_copy.url)
	expect(found.get("fatal") == true, "an R2 manifest whose bytes differ from its name was used: %s" % [found])
	var github_url := "https://github.com/%s/releases/download/client-%s/RabbitLands-windows.json" % [REPOSITORY, D]
	transport.responses[github_url] = bytes_of(signed(newer))
	found = await discover(transport, D, github_url)
	expect(found.get("fatal") == true and found.get("error") == "The release does not match the server's client commit.", "a manifest of another commit was used for a target: %s" % [found])
	transport.responses[github_url] = bytes_of(signed(required))
	found = await discover(transport, D, github_url)
	expect(found.get("via") == "server target", "a GitHub target manifest was refused: %s" % [found])
	found = await discover(transport, D)
	expect(found.get("fatal") == true, "a target without its manifest was not reported: %s" % [found])
	transport.responses[ALIAS] = bytes_of(signed(required))
	found = await discover(transport, D)
	expect(found.get("via") == "GitHub alias", "a target named by the alias was not used: %s" % [found])
	installed(A, S + 200)
	transport.responses[ALIAS] = bytes_of(signed(required))
	found = await discover(transport, D, github_url)
	expect(found.get("error") == Release.OLDER_RELEASE_MESSAGE and found.get("fatal") == true, "the downgrade guard did not apply to a server target: %s" % [found])

func probe(transport: FakeTransport, commit: String, ancestors: Array = []) -> Probe:
	var startup := Probe.new()
	startup.identity = {"commit": commit, "ancestors": [commit] + ancestors, "platform": "windows", "distribution": "github", "repository": REPOSITORY, "public_key": _trust.public_key, "release_build": true}
	startup.install_dir = _root
	startup.fake = transport
	root.add_child(startup)
	return startup

func check_game_start() -> void:
	var newer := manifest(B, S + 100, [A])
	# 1. The pointer names the installed commit (or an ancestor): no manifest fetch.
	for case: Array in [[B, []], [D, [B]]]:
		installed(case[0], S + 100)
		var transport := new_transport()
		var copy := served(transport, newer)
		serve_pointer(transport, pointer_payload(newer, copy, S + 200))
		transport.responses[ALIAS] = bytes_of(signed(newer))
		var startup := probe(transport, case[0], case[1])
		await startup._check()
		expect(transport.urls() == [POINTER], "the game fetched more than the pointer for a current build: %s" % [transport.urls()])
		expect(startup.finished and not is_instance_valid(startup.dialog) and startup.discovered_via == "pointer", "a current build was prompted")
		expect(Release.stored_pointer_sequence(_root) == S + 200, "the game did not keep the pointer mark")
		startup.free()
	# 2. A newer pointed release: its R2 manifest, then the prompt; the alias is not read.
	installed(A, S)
	var transport := new_transport()
	var copy := served(transport, newer)
	serve_pointer(transport, pointer_payload(newer, copy, S + 200))
	var startup := probe(transport, A)
	await startup._check()
	expect(transport.urls() == [POINTER, copy.url], "the game's pointer discovery requests: %s" % [transport.urls()])
	expect(is_instance_valid(startup.dialog) and startup.published.commit == B and startup.discovered_via == "pointer", "the pointed update was not offered")
	startup._accept_update()
	expect(startup.closed and "--install-update" in startup.started and not startup.started.has("--target-commit=" + B), "the update did not start normally: %s" % [startup.started])
	startup.free()
	# 3. Pointer failures fall back to the alias.
	var same_size := manifest(B, S + 100, [A])
	same_size["launch_args"] = ["--b"]
	newer["launch_args"] = ["--a"]
	for name: String in ["missing", "manifest changed", "manifest of the same size"]:
		installed(A, S)
		transport = new_transport()
		copy = served(transport, newer)
		serve_pointer(transport, pointer_payload(newer, copy, S + 200))
		if name == "missing":
			transport.responses.erase(POINTER)
		elif name == "manifest changed":
			transport.responses[copy.url] = bytes_of(signed(changed(newer, ["launch_args"], ["--x"])))
		else:
			transport.responses[copy.url] = bytes_of(signed(same_size))
			expect(transport.responses[copy.url].size() == copy.size, "the same-size substitute differs in size")
		transport.responses[ALIAS] = bytes_of(signed(newer))
		startup = probe(transport, A)
		await startup._check()
		expect(transport.urls().back() == ALIAS and is_instance_valid(startup.dialog) and startup.discovered_via == "alias", "the game did not fall back to the alias (%s): %s" % [name, transport.urls()])
		startup.free()
	# 4. An alias release older than the installed one is never offered.
	installed(A, S + 500)
	transport = new_transport()
	transport.responses[ALIAS] = bytes_of(signed(newer))
	startup = probe(transport, A)
	await startup._check()
	expect(not is_instance_valid(startup.dialog), "the game offered a release older than the installed one")
	startup.free()
	# 5. A frozen pointer and a server that requires a newer commit: rediscovery
	# bypasses the pointer (alias, then the notice's manifest URL).
	var required := manifest(D, S + 300, [A])
	for source: String in ["alias", "r2 copy"]:
		installed(A, S)
		transport = new_transport()
		var frozen := served(transport, manifest(A, S))
		serve_pointer(transport, pointer_payload(manifest(A, S), frozen, S + 50))
		var required_copy := served(transport, required)
		transport.responses[ALIAS] = bytes_of(signed(required if source == "alias" else newer))
		startup = probe(transport, A)
		await startup._check()
		expect(not is_instance_valid(startup.dialog) and transport.urls() == [POINTER], "a frozen pointer was not 'current'")
		transport.requests.clear()
		await startup.server_target(D, required_copy.url)
		expect(not transport.urls().has(POINTER), "server-target rediscovery read the pointer")
		expect(transport.urls() == ([ALIAS] if source == "alias" else [ALIAS, required_copy.url]), "server-target requests (%s): %s" % [source, transport.urls()])
		expect(is_instance_valid(startup.dialog) and startup.published.commit == D and startup.discovered_via == "server target", "the required release was not offered (%s)" % [source])
		expect(startup.dialog.dialog_text.begins_with("The game server requires Rabbit Lands release " + D.left(9)), "the server-target prompt text: " + startup.dialog.dialog_text)
		startup._accept_update()
		expect(("--target-commit=" + D) in startup.started and ("--target-manifest-url=" + required_copy.url) in startup.started, "the updater was not asked for the required commit: %s" % [startup.started])
		startup.free()
	# ... never with a refusal, for a contained commit, a mismatching R2 copy or an older release.
	installed(A, S)
	transport = new_transport()
	var required_copy := served(transport, required)
	startup = probe(transport, A)
	startup.finished = true
	startup._transport = transport
	startup.declined = true
	await startup.server_target(D, required_copy.url)
	expect(transport.urls().is_empty() and not is_instance_valid(startup.dialog), "a declined update was offered again")
	startup.declined = false
	await startup.server_target(A, required_copy.url)
	expect(transport.urls().is_empty(), "a contained commit was rediscovered")
	transport.responses[required_copy.url] = bytes_of(signed(changed(required, ["launch_args"], ["--x"])))
	await startup.server_target(D, required_copy.url)
	expect(not is_instance_valid(startup.dialog), "an R2 copy whose bytes differ from its name was offered")
	transport.requests.clear()
	await startup.server_target(D, required_copy.url)
	expect(transport.urls().is_empty(), "a failed rediscovery was retried at once")
	startup.free()
	installed(A, S + 400)
	transport = new_transport()
	transport.responses[ALIAS] = bytes_of(signed(required))
	startup = probe(transport, A)
	startup.finished = true
	startup._transport = transport
	await startup.server_target(D, "")
	expect(not is_instance_valid(startup.dialog), "a required release older than the installed one was offered")
	startup.free()
	# One rediscovery at a time: a notice for another commit while one runs
	# starts nothing beside it, so the prompt and its updater arguments agree.
	installed(A, S)
	var slow := SlowTransport.new()
	_transports.append(slow)
	required_copy = served(slow, required)
	var other_copy := served(slow, manifest(C, S + 350, [A]))
	startup = probe(slow, A)
	startup.finished = true
	startup._transport = slow
	startup.server_target(D, required_copy.url)
	startup.server_target(C, other_copy.url)
	await settle(startup)
	expect(slow.urls() == [ALIAS, required_copy.url], "server-target rediscoveries overlapped: %s" % [slow.urls()])
	expect(is_instance_valid(startup.dialog) and startup.published.commit == D and startup.dialog.dialog_text.contains(D.left(9)), "the first required release was not offered")
	startup._accept_update()
	expect(("--target-commit=" + D) in startup.started and not ("--target-commit=" + C) in startup.started, "the prompt and the updater arguments disagree: %s" % [startup.started])
	startup.free()
	# A refusal during the rediscovery leaves the release and arguments untouched.
	startup = probe(slow, A)
	startup.finished = true
	startup._transport = slow
	slow.requests.clear()
	startup.server_target(D, required_copy.url)
	await process_frame
	startup.declined = true
	await settle(startup)
	expect(slow.urls() == [ALIAS, required_copy.url] and not is_instance_valid(startup.dialog), "a refused update was offered: %s" % [slow.urls()])
	expect(startup.published.is_empty() and startup._target_args.is_empty(), "a refused rediscovery changed the offered release: %s" % [startup.published])
	startup.free()

func settle(startup: Probe) -> void:
	# Until no rediscovery runs (and a few frames for any that overlapped).
	for _frame in 600:
		if not startup._target_busy:
			break
		await process_frame
	for _frame in 6:
		await process_frame

func notice(commit: String, url: Variant) -> PackedByteArray:
	return JSON.stringify({"schema": 1, "required_commit": commit, "manifest_url": url}).to_utf8_buffer()

func check_server_notice() -> void:
	# Packet 206 in the game: a required commit this build lacks starts
	# server-target rediscovery; the R2 manifest prefix is a known source.
	var required := manifest(D, S + 300, [A])
	installed(A, S)
	var transport := new_transport()
	var copy := served(transport, required)
	var client := Client.new()
	client.identity = {"commit": A, "ancestors": [A], "platform": "windows", "distribution": "github", "repository": REPOSITORY, "public_key": _trust.public_key, "release_build": true}
	client._status = Label.new()
	client.add_child(client._status)
	root.add_child(client)
	var startup := probe(transport, A)
	startup.finished = true
	startup._transport = transport
	client._startup = startup
	client._on_packet(206, notice(A, copy.url))
	expect(transport.urls().is_empty() and client._status.text == "", "a notice for the installed commit started rediscovery")
	client._on_packet(206, notice(D, copy.url))
	expect(client._status.text == StartupUpdate.COMPATIBILITY_NOTE, "a required update did not show the compatibility note")
	expect(transport.urls() == [ALIAS, copy.url] and is_instance_valid(startup.dialog) and startup.published.commit == D, "a required update was not rediscovered: %s" % [transport.urls()])
	transport.requests.clear()
	client._on_packet(206, notice(D, copy.url))
	expect(transport.urls().is_empty(), "a repeated notice fetched the release again")
	startup.dialog.canceled.emit()
	expect(startup.declined, "declining the required update was not recorded")
	client._on_packet(206, notice(C, copy.url))
	expect(transport.urls().is_empty(), "a refusal was overridden by a server notice")
	startup.free()
	# A notice whose URL is not a string still rediscovers through the alias.
	startup = probe(transport, A)
	startup.finished = true
	startup._transport = transport
	client._startup = startup
	transport.responses[ALIAS] = copy.bytes
	client._on_packet(206, notice(D, 5))
	expect(transport.urls() == [ALIAS] and is_instance_valid(startup.dialog), "a notice without a usable URL did not use the alias: %s" % [transport.urls()])
	startup.free()
	# The older background path (no startup checker) accepts the R2 manifest prefix too.
	client._startup = null
	client._busy = true # queue only: nothing is downloaded here
	client._on_packet(206, notice(D, copy.url))
	expect(client._latest_notice.get("url") == copy.url, "an R2 manifest URL was refused by the background path")
	client._target = ""
	client._on_packet(206, notice(D, "https://assets.example.com/desktop/v1/manifests/windows/%s.json" % copy.sha256))
	expect(client._status.text == "The server's update source is not configured for this installation.", "an unknown manifest host was accepted")
	client.free()

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	_root = args[0]
	_key = CryptoKey.new()
	expect(_key.load(args[1]) == OK, "the test signing key could not be loaded")
	_other_key = Crypto.new().generate_rsa(2048)
	_trust = Bootstrap.trust()
	expect(_trust.get("repository") == REPOSITORY and _trust.get("platform") == "windows", "the fixture trust file is wrong")
	expect(_trust.get("public_key") != FileAccess.get_file_as_string("res://data/update_public.pem"), "the fixture uses the release key")
	Release.remove_tree(_root)
	DirAccess.make_dir_recursive_absolute(_root)
	check_pointer_rules()
	check_records()
	check_downgrade_guard()
	check_urls_and_arguments()
	await check_transport_limits()
	await check_launcher_discovery()
	await check_game_launch_arguments()
	await check_game_start()
	check_server_notice()
	for transport: Variant in _transports:
		if is_instance_valid(transport) and not transport.is_inside_tree():
			transport.free()
	Release.remove_tree(_root)
	Release.remove_tree(Release.cache_for(_root))
	print("Release discovery checks: ", "PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)

extends SceneTree
## R2 content downloads over real local HTTPS (run_client_update_tests.py).
## This runs in a fixture project whose copy of release.gd names the local
## server as DESKTOP_ASSETS; the shipped file and its rules stay unchanged.
## The server serves the fixture's parts and, per request, takes the next
## scripted fault for that path from faults.json and counts requests.
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")
const Download = preload("res://src/updates/package_download.gd")
const PRODUCTION_ASSETS := "https://assets.rabbitlandsgame.com/desktop/v1/"
const VERSION := "RabbitLands-Windows-20261104-bbbbbbbbb"
const FAST_WAITS: Array = [0.05, 0.1]

class LocalTransport extends "res://src/updates/update_transport.gd":
	var certificate_path := ""
	func _new_http_request() -> HTTPRequest:
		# Only this test trusts the local server's certificate; shipped
		# transports keep the system's certificate and host name checks.
		var request := HTTPRequest.new()
		var certificate := X509Certificate.new()
		certificate.load(certificate_path)
		request.set_tls_options(TLSOptions.client(certificate, "localhost"))
		return request

var _failures := 0
var _key: CryptoKey
var _identity: Dictionary
var _served := ""
var _root := ""
var _transport: LocalTransport
var _release: Dictionary
var _envelope: Dictionary
var _paths: Dictionary = {}

func expect(value: bool, message: String) -> void:
	if not value:
		_failures += 1
		push_error(message)

func write_bytes(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()

func write(path: String, text: String) -> void:
	write_bytes(path, text.to_utf8_buffer())

func read(relative: String) -> String:
	return FileAccess.get_file_as_string(_root.path_join(relative))

func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

func envelope(payload: Dictionary) -> Dictionary:
	var bytes := JSON.stringify(payload).to_utf8_buffer()
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return {"payload": Marshalls.raw_to_base64(bytes), "signature": Marshalls.raw_to_base64(Crypto.new().sign(HashingContext.HASH_SHA256, hash.finish(), _key))}

func package_zip(id: String, files: Dictionary) -> Dictionary:
	# The package format the updater reads: inventory.json and one entry per
	# file chunk (each file here fits one 8 MiB chunk).
	var path := _root + "-work/" + id + ".zip"
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var zip := ZIPPacker.new()
	zip.open(path)
	var inventory: Array = []
	for name: String in files:
		var bytes: PackedByteArray = files[name]
		zip.start_file("files/%06d/%06d" % [inventory.size(), 0])
		zip.write_file(bytes)
		zip.close_file()
		inventory.append({"path": name, "size": bytes.size(), "sha256": digest(bytes)})
	zip.start_file("inventory.json")
	zip.write_file(JSON.stringify(inventory).to_utf8_buffer())
	zip.close_file()
	zip.close()
	var archive := FileAccess.get_file_as_bytes(path)
	var unpacked := 0
	for entry: Dictionary in inventory:
		unpacked += int(entry.size)
	return {"id": id, "bytes": archive, "files": inventory, "unpacked_size": unpacked}

func r2_package(id: String, files: Dictionary, slices: int) -> Dictionary:
	# Splits the package into parts and serves each as <base>parts/<sha256>.bin.
	var built := package_zip(id, files)
	var archive: PackedByteArray = built.bytes
	var parts: Array = []
	var step := ceili(archive.size() / float(slices))
	for start in range(0, archive.size(), step):
		var bytes := archive.slice(start, mini(start + step, archive.size()))
		var sha := digest(bytes)
		var url := Release.DESKTOP_ASSETS + "parts/" + sha + ".bin"
		write_bytes(_served.path_join("desktop/v1/parts/" + sha + ".bin"), bytes)
		parts.append({"url": url, "size": bytes.size(), "sha256": sha})
		_paths["%s/%d" % [id, parts.size()]] = "/desktop/v1/parts/" + sha + ".bin"
	return {"id": id, "sha256": digest(archive), "size": archive.size(), "unpacked_size": built.unpacked_size,
		"file_count": built.files.size(), "files": built.files, "parts": parts}

func noise(size: int, seed_value: int) -> PackedByteArray:
	# Incompressible bytes, so a package spans several parts.
	var random := RandomNumberGenerator.new()
	random.seed = seed_value
	var bytes := PackedByteArray()
	bytes.resize(size)
	for index in size:
		bytes[index] = random.randi() % 256
	return bytes

func build_release() -> void:
	var b := "b".repeat(40)
	var descriptor := _identity.duplicate(true)
	descriptor.commit = b
	descriptor.ancestors = [b, _identity.commit]
	var client := r2_package("client", {"app/RabbitLands.pck": noise(40000, 1), "app/client-release.json": JSON.stringify(descriptor).to_utf8_buffer()}, 1)
	var world := r2_package("world", {"eloria-assets/map.json": noise(90000, 2)}, 3)
	# The engine is a CI package on GitHub; the installed copy already matches,
	# so it is never fetched (an R2 release mixes both hosts).
	var engine := package_zip("engine", {"app/RabbitLands.exe": "same exe".to_utf8_buffer()})
	var github := "https://github.com/o/r/releases/download/client-%s/" % b
	var engine_package := {"id": "engine", "sha256": digest(engine.bytes), "size": engine.bytes.size(), "unpacked_size": engine.unpacked_size,
		"file_count": 1, "files": engine.files, "parts": [{"url": github + VERSION + ".pkg.engine.zip.001", "size": engine.bytes.size(), "sha256": digest(engine.bytes)}]}
	var packages := [client, engine_package, world]
	var parts: Array = []
	var size := 0
	var unpacked := 0
	var count := 0
	for package: Dictionary in packages:
		parts.append_array(package.parts)
		size += int(package.size)
		unpacked += int(package.unpacked_size)
		count += int(package.file_count)
	_release = {"schema": 3, "bootstrap_schema": 1, "commit": b, "platform": "windows", "repository": "o/r", "version": VERSION,
		"packages": packages, "parts": parts, "size": size, "unpacked_size": unpacked, "file_count": count, "sha256": "c".repeat(64),
		"updater": {"url": github + VERSION + "-updater.exe", "size": 5, "sha256": "c".repeat(64)},
		"uninstall": {"url": github + VERSION + "-uninstall.exe", "size": 5, "sha256": "c".repeat(64)}}
	_envelope = envelope(_release)

func old_install() -> void:
	Release.remove_tree(_root)
	Release.remove_tree(Release.cache_for(_root))
	write(_root.path_join("app/RabbitLands.exe"), "same exe")
	write(_root.path_join("app/RabbitLands.pck"), "old pck")
	write(_root.path_join("app/client-release.json"), JSON.stringify(_identity))
	write(_root.path_join("eloria-assets/map.json"), "old map")

func faults(script: Dictionary) -> void:
	# Scripted faults, keyed by the fixture's part names ("world/2" and so on).
	var by_path := {}
	for name: String in script:
		by_path[_paths[name]] = script[name]
	write(_served.path_join("faults.json"), JSON.stringify(by_path))

func requests() -> Dictionary:
	var counts := Release.read_json(_served.path_join("requests.json"))
	var named := {}
	for name: String in _paths:
		named[name] = int(counts.get(_paths[name], 0))
	return named

func delta(before: Dictionary, after: Dictionary) -> Dictionary:
	var changed := {}
	for name: String in after:
		if int(after[name]) != int(before.get(name, 0)):
			changed[name] = int(after[name]) - int(before.get(name, 0))
	return changed

func leftovers() -> Array:
	var found: Array = []
	var directory := DirAccess.open(Release.cache_for(_root).path_join("packages"))
	if directory != null:
		for name: String in directory.get_files():
			if name.ends_with(".tmp"):
				found.append(name)
	return found

func prepare(release: Dictionary, waits: Array = FAST_WAITS, cancelled := Callable(), progress := Callable()) -> Array:
	# [error, prepared plan]: the updater's own download step.
	var plan := {}
	var error: String = await Download.prepare(_root, release, _transport.fetch, _transport.worker, progress, cancelled, plan, waits)
	return [error, plan]

func installed_release(release: Dictionary, plan: Dictionary) -> bool:
	var error: String = await _transport.worker(func() -> String: return Packages.install(_root, release, _identity, Callable(), plan.get("checked")))
	expect(error == "", "the R2 release did not install: " + error)
	return error == "" and FileAccess.get_file_as_bytes(_root.path_join("app/RabbitLands.pck")) == noise(40000, 1) and FileAccess.get_file_as_bytes(_root.path_join("eloria-assets/map.json")) == noise(90000, 2) and read("app/RabbitLands.exe") == "same exe"

func check_rules(release: Dictionary) -> void:
	# This copy's base is the local server; production never is.
	expect(Release.DESKTOP_ASSETS.begins_with("https://127.0.0.1:") and Release.DESKTOP_ASSETS != PRODUCTION_ASSETS, "the fixture did not replace the R2 base: " + Release.DESKTOP_ASSETS)
	expect(not release.has("error") and Release.package_manifest(release), "the signed schema 3 R2 manifest was refused: %s" % release.get("error", ""))
	var older := _release.duplicate(true)
	older.schema = 2
	expect(Release.verify_manifest(envelope(older), _identity).get("error", "") == "A package download is invalid.", "schema 2 accepted R2 rows")
	# Only the compiled base counts: the production form is refused in this copy.
	var moved := _release.duplicate(true)
	var first: Dictionary = moved.packages[0].parts[0]
	var url := PRODUCTION_ASSETS + "parts/" + str(first.sha256) + ".bin"
	moved.packages[0].parts[0].url = url
	moved.parts[0].url = url
	expect(Release.verify_manifest(envelope(moved), _identity).get("error", "") == "A package download is invalid.", "a part outside the compiled base was accepted")

func check_transport_status() -> void:
	# The updater transport reports the HTTP status a retry decision needs.
	var temporary := _root + "-work/missing.tmp"
	var result: Dictionary = await _transport.fetch(Release.DESKTOP_ASSETS + "parts/" + "0".repeat(64) + ".bin", temporary, 4096)
	expect(result.has("error") and int(result.get("status", 0)) == 404 and Download.missing(result), "a missing R2 part was not reported as 404: %s" % [result])
	DirAccess.remove_absolute(temporary)

func check_retried_download(release: Dictionary) -> void:
	# Each part meets a different fault and is retried from an empty file.
	old_install()
	faults({"client/1": ["503"], "world/1": ["429", "drop"], "world/2": ["garbage"], "world/3": ["403"]})
	var before := requests()
	var details: Array = []
	var result: Array = await prepare(release, FAST_WAITS, Callable(), func(_phase: String, _done: int, _total: int, detail := "") -> void: details.append(detail))
	var made := delta(before, requests())
	expect(result[0] == "", "the retried R2 download failed: " + str(result[0]))
	expect(made == {"client/1": 2, "world/1": 3, "world/2": 2, "world/3": 2}, "unexpected R2 requests: %s" % [made])
	expect(details.any(func(detail: String) -> bool: return "retrying in" in detail), "a retry wait was not reported: %s" % [details])
	expect(leftovers().is_empty(), "a temporary download was left: %s" % [leftovers()])
	expect(await installed_release(release, result[1]), "the retried R2 release installed the wrong files")

func check_missing_then_resume(release: Dictionary) -> void:
	# A 404 ends at once; verified parts stay and a rerun fetches only the rest.
	old_install()
	faults({"world/2": ["404"]})
	var before := requests()
	var result: Array = await prepare(release)
	var made := delta(before, requests())
	expect(result[0] == Download.MISSING_ERROR, "a missing R2 part did not fail fast: " + str(result[0]))
	expect(made == {"client/1": 1, "world/1": 1, "world/2": 1}, "a missing part was retried or skipped ahead: %s" % [made])
	expect(leftovers().is_empty(), "a temporary download was left after a 404: %s" % [leftovers()])
	expect(read("app/RabbitLands.pck") == "old pck", "a failed download changed the installed game")
	before = requests()
	result = await prepare(release)
	made = delta(before, requests())
	expect(result[0] == "", "the rerun after a 404 failed: " + str(result[0]))
	expect(made == {"world/2": 1, "world/3": 1}, "the rerun did not resume at the missing part: %s" % [made])
	expect(await installed_release(release, result[1]), "the resumed R2 release installed the wrong files")

func check_exhausted(release: Dictionary) -> void:
	# Three failed attempts, after the scheduled waits; two hash mismatches.
	old_install()
	faults({"client/1": ["503", "503", "503", "503"]})
	var before := requests()
	var started := Time.get_ticks_msec()
	var result: Array = await prepare(release, [0.3, 0.6])
	var elapsed := Time.get_ticks_msec() - started
	var made := delta(before, requests())
	expect(result[0] == "The update download failed. Check the internet connection and try again.", "an unavailable server ended with: " + str(result[0]))
	expect(made == {"client/1": 3}, "a failing part was not tried exactly three times: %s" % [made])
	expect(elapsed >= 900, "the retries did not wait 0.3 s then 0.6 s: %d ms" % elapsed)
	old_install()
	faults({"client/1": ["garbage", "garbage"]})
	before = requests()
	result = await prepare(release)
	made = delta(before, requests())
	expect(result[0] == Download.VERIFICATION_ERROR and made == {"client/1": 2}, "a repeated hash mismatch was retried again: %s %s" % [result[0], made])
	expect(leftovers().is_empty() and read("app/RabbitLands.pck") == "old pck", "a refused download was kept or installed")
	faults({})

func check_cancelled_wait(release: Dictionary) -> void:
	# A cancellation ends a long retry wait within a slice.
	old_install()
	faults({"client/1": ["503"]})
	var before := requests()
	var started := Time.get_ticks_msec()
	var result: Array = await prepare(release, [30.0], func() -> bool: return Time.get_ticks_msec() - started > 400)
	var elapsed := Time.get_ticks_msec() - started
	expect(result[0] == Download.CANCELLED_ERROR and elapsed < 5000, "a cancelled retry wait went on: %s after %d ms" % [result[0], elapsed])
	expect(delta(before, requests()) == {"client/1": 1}, "a cancelled download retried")
	faults({})

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var request := Release.read_json(OS.get_cmdline_user_args()[0])
	_served = request.served
	_root = request.root
	_key = Crypto.new().generate_rsa(2048)
	var a := "a".repeat(40)
	_identity = {"schema": 1, "commit": a, "ancestors": [a], "platform": "windows", "repository": "o/r", "public_key": _key.save_to_string(true)}
	# The fixture signs with its own key, never the release key.
	var production_key := FileAccess.get_file_as_string(str(request.get("production_key", "")))
	expect(production_key.begins_with("-----BEGIN PUBLIC KEY-----") and production_key.strip_edges() != str(_identity.public_key).strip_edges(), "the fixture key is not distinct from the release key")
	_transport = LocalTransport.new()
	_transport.certificate_path = request.certificate
	root.add_child(_transport)
	build_release()
	var release := Release.verify_manifest(_envelope, _identity)
	check_rules(release)
	if not release.has("error"):
		await check_transport_status()
		await check_retried_download(release)
		await check_missing_then_resume(release)
		await check_exhausted(release)
		await check_cancelled_wait(release)
	Release.remove_tree(_root)
	Release.remove_tree(_root + "-work")
	Release.remove_tree(Release.cache_for(_root))
	print("R2 content download checks: ", "PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)

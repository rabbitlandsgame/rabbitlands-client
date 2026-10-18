extends SceneTree
const Release = preload("res://src/updates/release.gd")
class Downloader extends "res://src/updates/client_updates.gd":
	var certificate_path: String
	func _ready() -> void:
		pass
	func _new_http_request() -> HTTPRequest:
		# Only this test trusts the local fixture's certificate. The production
		# code keeps ordinary system certificate/hostname verification.
		var request := HTTPRequest.new()
		var certificate := X509Certificate.new()
		certificate.load(certificate_path)
		request.set_tls_options(TLSOptions.client(certificate, "localhost"))
		return request

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var args := OS.get_cmdline_user_args()
	var input := Release.read_json(args[0])
	var downloader := Downloader.new()
	root.add_child(downloader)
	downloader.identity = input.identity
	downloader.certificate_path = input.certificate
	downloader._latest_notice = {"url": input.url, "commit": input.commit}
	downloader._status = Label.new()
	downloader.add_child(downloader._status)
	var current_file := Release.install_root().path_join("app/client-release.json")
	var current := FileAccess.get_file_as_string(current_file) if FileAccess.file_exists(current_file) else ""
	await downloader._download(input.url, input.commit, 0)
	var cache := Release.cache_for(Release.install_root())
	# The local server deliberately fails the first manifest request. Check
	# that a background retry recovers without reconnecting or touching app/.
	if not FileAccess.file_exists(cache.path_join("pending.json")):
		downloader._retry_at_msec = Time.get_ticks_msec()
		var deadline := Time.get_ticks_msec() + 15000
		while not FileAccess.file_exists(cache.path_join("pending.json")) and Time.get_ticks_msec() < deadline:
			await process_frame
	var pending := Release.read_json(cache.path_join("pending.json"))
	var valid := Release.verify_manifest(pending, input.identity, input.commit)
	var okay := not valid.has("error") and Release.check_file(cache.path_join("release.zip"), int(valid.get("size", 0)), str(valid.get("sha256", "")))
	if FileAccess.file_exists(current_file):
		okay = okay and FileAccess.get_file_as_string(current_file) == current
	print("Background download and readiness checks: ", "PASS" if okay else "FAIL")
	downloader.queue_free()
	quit(0 if okay else 1)

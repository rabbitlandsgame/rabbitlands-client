extends SceneTree
const Release = preload("res://src/updates/release.gd")
const Updates = preload("res://src/updates/client_updates.gd")
var failures := 0

func expect(okay: bool, message: String) -> void:
	if not okay:
		failures += 1
		push_error(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var installed := "a".repeat(40)
	var required := "b".repeat(40)
	var cache := Release.cache_for(Release.install_root())
	DirAccess.make_dir_recursive_absolute(cache)
	Release.save_json(cache.path_join("pending.json"), {"sentinel": "untouched"})
	for channel in ["steam", "standalone"]:
		var identity := {"platform": "windows", "distribution": channel, "commit": installed,
			"ancestors": [installed], "public_key": "present", "repository": "o/r"}
		Release.save_json("res://data/client_release.json", identity)
		var updates := Updates.new()
		root.add_child(updates)
		var notice := {"schema": 1, "required_commit": required,
			"manifest_url": "https://github.com/o/r/releases/download/test/manifest.json"}
		updates._on_packet(206, JSON.stringify(notice).to_utf8_buffer())
		expect(updates._status.text.contains("Steam") if channel == "steam" else updates._status.text.contains("download page"), "external update instruction missing")
		expect(updates._request == null and updates._worker == null and not updates._busy, "external build started a GitHub request")
		expect(updates._lease == "", "external build wrote a running lease")
		expect(Release.read_json(cache.path_join("pending.json")).get("sentinel") == "untouched", "external build touched a pending GitHub update")
		expect(Release.verify_manifest({}, identity).has("error"), "external build accepts GitHub manifests")
		expect(Release.install(OS.get_cmdline_user_args()[0], identity) != "", "external build entered installer")
		notice.required_commit = installed
		updates._on_packet(206, JSON.stringify(notice).to_utf8_buffer())
		expect(updates._status.text == "", "compatible Steam build still says update required")
		updates.free()
	Release.save_json("res://data/client_release.json", {"platform": "source"})
	DirAccess.remove_absolute(cache.path_join("pending.json"))
	expect(Release.update_owner({}) == "github", "legacy GitHub installations changed owner")
	print("Store update ownership checks: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)

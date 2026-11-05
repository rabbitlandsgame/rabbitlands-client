extends SceneTree
## Loads, through the engine's resource system, every resource a PCK's .import
## files name and every raw file a job lists (the login videos), and writes what
## it found as JSON (W2-UD-06). package_client runs it twice on a staged
## package, beside nothing loose (an empty working directory):
##
##   record: --main-pack <the exported monolith>
##   verify: --main-pack <the core pack> with the content packs mounted
##
## and compares the reports: the same class, the same size details
## (texture width x height, audio length, scene node count, translation
## messages) and the same import-product and file byte counts. In verify mode
## the products and files are md5-hashed too, which the packager compares with
## the monolith's PCK directory: the engine reads the monolith's exact bytes
## from the split layout. An .import without a remap product (csv_translation,
## skip) is listed with no class: nothing loads by its path.
##
## Usage (an editor binary: release templates refuse --script):
##   godot --headless --main-pack <pck> --script check_split_pack_resources.gd -- <job.json>
## job: {"schema": 1, "mode": "record"|"verify", "report": "<path>",
##       "resources": ["assets/x.png", ...]   (each has a .import in the pack),
##       "files": ["assets/ui/start_screen/a.ogv", ...],
##       "mount_script": "res://src/boot/content_packs.gd"   (verify only)}
## Verify mode calls the mount script's mount() (idempotent; the ContentPacks
## autoload has normally mounted everything already) and fails unless every
## required pack is mounted ("status": "fail" and "failures" in the report).
## Exit code 0 whenever the report was written: the packager judges the runs.

const SCHEMA := 1

func _initialize() -> void:
	var code := 1
	var args := OS.get_cmdline_user_args()
	if args.size() == 1:
		code = _run(args[0])
	else:
		printerr("check_split_pack_resources: pass exactly one job file after --")
	quit(code)

func _run(job_path: String) -> int:
	var job: Variant = JSON.parse_string(FileAccess.get_file_as_string(job_path))
	var mode := str(job.get("mode", "")) if job is Dictionary else ""
	if not job is Dictionary or int(job.get("schema", 0)) != SCHEMA or not mode in ["record", "verify"]:
		printerr("check_split_pack_resources: unreadable job ", job_path)
		return 1
	var verify: bool = job.mode == "verify"
	var report := {"schema": SCHEMA, "mode": job.mode, "status": "pass", "failures": [], "mount": {},
		"resources": {}, "files": {}, "usec": 0}
	var started := Time.get_ticks_usec()
	if verify:
		var mounter := load(str(job.get("mount_script", "res://src/boot/content_packs.gd"))) as Script
		var methods := []
		for method: Dictionary in (mounter.get_script_method_list() if mounter != null else []):
			methods.append(method.name)
		if not "mount" in methods:
			report.failures.append("the content pack mount script did not load")
		else:
			report.mount = mounter.call("mount")
			if report.mount.get("state") != "mounted":
				report.failures.append("content packs are not mounted: %s" % JSON.stringify(report.mount))
	for value: Variant in job.get("resources", []):
		var path := str(value)
		report.resources[path] = _resource(path, verify)
		if report.resources[path].has("error"):
			report.failures.append("%s: %s" % [path, report.resources[path].error])
	for value: Variant in job.get("files", []):
		var path := str(value)
		report.files[path] = _file(path, verify)
		if report.files[path].has("error"):
			report.failures.append("%s: %s" % [path, report.files[path].error])
	report.usec = Time.get_ticks_usec() - started
	if not report.failures.is_empty():
		report.status = "fail"
	var out := FileAccess.open(str(job.get("report", "")), FileAccess.WRITE)
	if out == null:
		printerr("check_split_pack_resources: cannot write ", job.get("report", ""))
		return 1
	out.store_string(JSON.stringify(report, " ", true))
	out.close()
	print("check_split_pack_resources %s: %d resources, %d files, %d failures" % [
		job.mode, report.resources.size(), report.files.size(), report.failures.size()])
	# The packager compares the two runs; a resource the monolith cannot load
	# either is reported, not fatal, so the exit code says only that this ran.
	return 0

func _resource(path: String, hash_products: bool) -> Dictionary:
	var row := {"class": "", "detail": "", "products": {}}
	var config := ConfigFile.new()
	if config.load("res://" + path + ".import") != OK:
		row.error = "its .import is unreadable"
		return row
	for key: String in (config.get_section_keys("remap") if config.has_section("remap") else PackedStringArray()):
		if key == "path" or key.begins_with("path."):
			var product := str(config.get_value("remap", key))
			if FileAccess.file_exists(product):
				row.products[product.trim_prefix("res://")] = _bytes(product, hash_products)
	if row.products.is_empty():
		# No remap product (a csv_translation import names its .translation files
		# directly, a skip/keep import ships nothing): nothing loads by this path.
		row.detail = "no import product"
		return row
	var resource: Resource = ResourceLoader.load("res://" + path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if resource == null:
		row.error = "did not load"
		return row
	row["class"] = resource.get_class()
	row.detail = _detail(resource)
	return row

func _file(path: String, hash_bytes: bool) -> Dictionary:
	var row := _bytes("res://" + path, hash_bytes)
	if int(row.bytes) < 0:
		row.error = "unreadable"
		return row
	var resource: Resource = ResourceLoader.load("res://" + path, "", ResourceLoader.CACHE_MODE_IGNORE) \
		if ResourceLoader.exists("res://" + path) else null
	row["class"] = resource.get_class() if resource != null else ""
	return row

func _bytes(path: String, hash_bytes: bool) -> Dictionary:
	var handle := FileAccess.open(path, FileAccess.READ)
	var row := {"bytes": handle.get_length() if handle != null else -1}
	handle = null
	if hash_bytes and int(row.bytes) >= 0:
		row["md5"] = FileAccess.get_md5(path)
	return row

func _detail(resource: Resource) -> String:
	if resource is Texture2D:
		return "%dx%d" % [resource.get_width(), resource.get_height()]
	if resource is AudioStream:
		return "%.3f s" % resource.get_length()
	if resource is PackedScene:
		return "%d nodes" % resource.get_state().get_node_count()
	if resource is Translation:
		return "%d messages" % resource.get_message_count()
	if resource is Mesh:
		return "%d surfaces" % resource.get_surface_count()
	return ""

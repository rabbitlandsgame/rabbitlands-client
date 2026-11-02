extends SceneTree
const Service := preload("res://src/platform/browser_asset_service.gd")
var service: Node

func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	service = Service.new()
	root.add_child(service)
	service.set_process(false)
	service.groups = {
		"startup":{"archives":[], "dependencies":[]},
		"shared":{"archives":[], "dependencies":[]},
		"map:a":{"archives":[], "dependencies":["shared"]}}
	assert(not service.ensure_groups(["map:a"], "active"))
	assert(service.queue == ["shared", "map:a"])
	assert(service.pins.active.has("shared"))
	service.queue.clear()
	service.states = {"shared":"ready", "map:a":"ready"}
	service.sizes = {"shared":10, "map:a":20}
	service.live_bytes = 30
	service.budget_bytes = 5
	service.touched = {"shared":-5000, "map:a":-5000}
	service._evict()
	assert(service.live_bytes == 30 and service.snapshot().over_budget)
	service.release_groups("active")
	service._evict()
	assert(service.live_bytes == 0 and service.states.is_empty())
	service.states = {"startup":"ready", "shared":"ready", "map:a":"failed"}
	service.errors = {"map:a":"temporary network failure"}
	service.error = "temporary network failure"
	assert(service.retry_failed() == 1)
	assert(service.states == {"startup":"ready", "shared":"ready"} and service.error.is_empty())
	assert(not service.ensure_groups(["map:a"], "active"))
	assert(service.queue == ["map:a"])
	service.queue.clear()
	service.states.clear()
	service.groups.optional = {"archives":[], "dependencies":[]}
	assert(not service.ensure_groups(["optional"]))
	assert(not service.ensure_groups(["map:a"], "active"))
	assert(service.queue == ["shared", "map:a", "optional"])
	service.queue.clear()
	# The same original file is assembled across independently compressed pieces.
	service.current = "fixture"
	service.files.fixture = []
	service.archive_path = "res://fixture.zip"
	var zip := ZIPPacker.new()
	assert(zip.open(service.archive_path) == OK)
	for offset: int in [0,3]:
		assert(zip.start_file("godot-client/assets/test_group.bin.__rlpart_%012d" % offset) == OK)
		zip.write_file(("abc" if offset == 0 else "def").to_utf8_buffer())
		zip.close_file()
	zip.close()
	var bytes: int = await service._unpack(FileAccess.get_sha256(service.archive_path))
	assert(bytes == 6 and FileAccess.get_file_as_bytes("res://assets/test_group.bin").get_string_from_utf8() == "abcdef")
	var evicted: Array = []
	service.files_evicted.connect(func(paths: PackedStringArray) -> void: evicted.append(paths))
	service._remove_files("fixture")
	assert(not FileAccess.file_exists("res://assets/test_group.bin"))
	assert(evicted.size() == 1 and "res://assets/test_group.bin" in evicted[0])
	assert(service._destination("eloria-assets/../private.txt").is_empty())
	assert(service._destination("godot-client/assets/C:/private.txt").is_empty())
	service.free()
	print("browser asset service: dependency pins, eviction, multipart extraction PASS")
	quit()

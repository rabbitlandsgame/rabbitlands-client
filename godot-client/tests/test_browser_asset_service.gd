extends SceneTree
const Service := preload("res://src/platform/browser_asset_service.gd")
var service: Node

class ArchiveProof:
	extends RefCounted
	var sha256 := ""
	var bytes := 0
	var attempts := 0
	func consume(expected: String, expected_bytes: int) -> bool:
		attempts += 1
		var matches := sha256 == expected and bytes == expected_bytes
		sha256 = ""
		bytes = 0
		return matches

func _initialize() -> void: _run.call_deferred()

func _test_archive_proof() -> void:
	var proof := ArchiveProof.new()
	var consumer := Callable(proof, "consume")
	var expected := "a".repeat(64)
	service.archive_path = Service.ARCHIVE
	for version: Variant in [null, "1", true, 2, 1.1]:
		service._configure_archive_proof(version, consumer)
		assert(not service._take_archive_proof(expected, 123))
	assert(proof.attempts == 0)
	for version: Variant in [1, 1.0]:
		service._configure_archive_proof(version, consumer)
		proof.sha256 = expected
		proof.bytes = 123
		assert(service._take_archive_proof(expected, 123))
		assert(not service._take_archive_proof(expected, 123)) # Consumed once.
	proof.sha256 = expected
	proof.bytes = 123
	assert(not service._take_archive_proof("b".repeat(64), 123))
	assert(not service._take_archive_proof(expected, 123)) # Mismatch consumed too.
	proof.sha256 = expected
	proof.bytes = 123
	assert(not service._take_archive_proof(expected, 124))
	assert(not service._take_archive_proof(expected, 123))
	proof.sha256 = expected
	proof.bytes = 123
	var attempts := proof.attempts
	service.archive_path = "res://fixture.zip"
	assert(not service._take_archive_proof(expected, 123))
	service.archive_path = Service.ARCHIVE
	assert(not service._take_archive_proof(expected, -1))
	assert(proof.attempts == attempts) # A custom/native path never calls JS.
	service._configure_archive_proof(1, Callable())
	assert(not service._take_archive_proof(expected, 123))
	service.current = "startup"
	assert(service._unpack_slice_usec() == 12000)
	service.current = "map:a"
	assert(service._unpack_slice_usec() == 2000)
	service.current = "model:actor"
	assert(service._unpack_slice_usec() == 2000)

func _run() -> void:
	service = Service.new()
	root.add_child(service)
	service.set_process(false)
	_test_archive_proof()
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
	service.states.clear()
	service.groups.remote_a = {"archives":[], "dependencies":[]}
	service.groups.remote_b = {"archives":[], "dependencies":[]}
	assert(not service.ensure_groups(["remote_a"], "actor_a", 1))
	assert(not service.ensure_groups(["map:a"], "local_actor", 2))
	assert(not service.ensure_groups(["remote_b"], "actor_b", 1))
	assert(service.queue == ["shared", "map:a", "remote_a", "remote_b"])
	assert(not service.ensure_groups(["remote_b"], "actor_b", 1))
	assert(service.queue == ["shared", "map:a", "remote_a", "remote_b"])
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
	var archive := FileAccess.open(service.archive_path, FileAccess.READ)
	var archive_bytes := archive.get_length()
	archive.close()
	var archive_sha := FileAccess.get_sha256(service.archive_path)
	assert(await service._unpack(archive_sha, archive_bytes + 1) == -1)
	assert(service.snapshot().archive_sha_checks == 0) # Length rejected first.
	assert(not FileAccess.file_exists("res://assets/test_group.bin"))
	assert(await service._unpack("0".repeat(64), archive_bytes) == -1)
	assert(service.snapshot().archive_sha_checks == 1)
	assert(not FileAccess.file_exists("res://assets/test_group.bin"))
	var bytes: int = await service._unpack(archive_sha, archive_bytes)
	assert(bytes == 6 and FileAccess.get_file_as_bytes("res://assets/test_group.bin").get_string_from_utf8() == "abcdef")
	assert(service.snapshot().archive_proof_hits == 0 and service.snapshot().archive_sha_checks == 2)
	var evicted: Array = []
	service.files_evicted.connect(func(paths: PackedStringArray) -> void: evicted.append(paths))
	service._remove_files("fixture")
	assert(not FileAccess.file_exists("res://assets/test_group.bin"))
	assert(evicted.size() == 1 and "res://assets/test_group.bin" in evicted[0])
	assert(service._destination("eloria-assets/../private.txt").is_empty())
	assert(service._destination("godot-client/assets/C:/private.txt").is_empty())
	service.free()
	print("browser asset service: pins, eviction, archive proof/fallback, phase budgets, multipart extraction PASS")
	quit()

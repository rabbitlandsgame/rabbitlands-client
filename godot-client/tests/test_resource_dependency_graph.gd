extends SceneTree
## Source-DAG identity fixture only. Real GLTF launch/join/lifetime is exercised
## separately by test_global_resource_admission; these files are opaque bytes.
const Graph := preload("res://src/runtime/resource_dependency_graph.gd")
const DIRECTORY := "user://source-dependency-graph-fixture"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("resource dependency graph: " + message)

func _write(path: String, content: String) -> String:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_expect(false, "fixture file opens")
		return ""
	file.store_buffer(content.to_utf8_buffer())
	file.close()
	return FileAccess.get_sha256(path)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	var prototype := "a".repeat(64)
	var second_prototype := "c".repeat(64)
	var image_sha := _write(DIRECTORY.path_join("image.png"), "synthetic image source bytes")
	var mesh_sha := _write(DIRECTORY.path_join(prototype + ".glb"), "synthetic prototype source bytes")
	var second_mesh_sha := _write(DIRECTORY.path_join(second_prototype + ".glb"), "different prototype source bytes")
	_write(DIRECTORY.path_join("world.glb"), "synthetic root source bytes including embedded-image bytes")
	var index := {"prototypes": {prototype: {"sha256": mesh_sha, "images": {"image.png": image_sha, "./image.png": image_sha}},
		second_prototype: {"sha256": second_mesh_sha, "images": {"image.png": image_sha}}}}
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	var source := {"schemaVersion": "1.0.0", "asset": {"id": "source-graph-fixture", "glb": "world.glb",
		"units": "meters", "coordinateSystem": {"upAxis": "Y"}, "bounds": {"min": [0,0,0], "max": [1,1,1]}},
		"externalResources": {"image.png": image_sha, "./image.png": image_sha},
		"externalMeshes": {prototype + ".glb": mesh_sha, second_prototype + ".glb": second_mesh_sha},
		"spawnPoints": [], "collision": {}, "navigation": {}}
	var path := DIRECTORY.path_join("world.json")
	_write(path, JSON.stringify(source))
	var manifest := WorldManifest.load_file(path)
	var first := Graph.describe(manifest)
	_expect(bool(first.get("complete", false)) and first.get("nodes", []).size() == 4,
		"actual source SHA graph deduplicates direct and transitive references to one image")
	if not bool(first.get("complete", false)):
		quit(1)
		return
	var mesh: Dictionary = {}
	var image: Dictionary = {}
	for row: Dictionary in first.nodes:
		if row.kind == "prototype" and row.source_sha256 == mesh_sha: mesh = row
		elif row.kind == "image": image = row
	_expect(not mesh.is_empty() and str(mesh.source_sha256) == mesh_sha and mesh_sha != prototype,
		"prototype filename identity is not mistaken for its actual source-file SHA")
	_expect(mesh.get("dependencies", []) == [str(image.get("key", ""))],
		"prototype-to-image dependency is transitive and explicit")
	_expect(first.get("allocation_kind") == "unknown_cpu_gpu_allocation" and not bool(first.verification_reuse),
		"source identity does not claim allocation measurement or sealed content")
	var work: Dictionary = first.verification_work
	_expect(work.full_sha256_reads == 5 and work.full_sha256_references == 9
		and work.full_sha256_reads_deduplicated == 4 and work.index_json_reads == 1
		and work.index_json_references == 2 and work.index_json_reads_deduplicated == 1,
		"two prototypes and canonical path aliases hash each distinct input and parse one current index exactly once")
	var repeated := Graph.describe(manifest)
	_expect(bool(repeated.get("complete", false)) and repeated.nodes == first.nodes
		and repeated.verification_work == work and repeated.verification_dedup_scope == "single_describe_invocation",
		"a later invocation performs all five full SHA reads and the current index parse again")
	_write(DIRECTORY.path_join("image.png"), "Synthetic image source bytes")
	var changed := Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)), "changed image bytes fail closed without timestamp/size reuse")
	_write(DIRECTORY.path_join("image.png"), "synthetic image source bytes")
	index.prototypes[prototype]["sha256"] = "b".repeat(64)
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	changed = Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)), "mutable prototype index cannot silently rewrite an actual source identity")
	_expect(changed.verification_work.index_json_reads == 1,
		"mutated index is freshly read in the next invocation")
	index.prototypes[prototype]["sha256"] = mesh_sha
	# The direct image's actual SHA is already read. A conflicting expected
	# digest for a normalized alias still rejects; dedup never caches trust.
	index.prototypes[prototype].images["image.png"] = "d".repeat(64)
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	changed = Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)) and changed.reason == "prototype_image_digest_mismatch",
		"within-call dedup compares every expected digest against the actual full SHA")
	index.prototypes[prototype].images["image.png"] = image_sha
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	var restored := Graph.describe(manifest)
	_expect(bool(restored.get("complete", false)) and restored.nodes == first.nodes,
		"restored mutable inputs produce the original exact DAG in a fresh invocation")
	source.asset["id"] = "changed-manifest"
	_write(path, JSON.stringify(source))
	changed = Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)) and changed.reason == "joined_manifest_identity_changed",
		"joined builder metadata cannot be paired with newer mutable manifest bytes")
	print("resource dependency graph tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

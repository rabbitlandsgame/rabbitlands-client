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
	var image_sha := _write(DIRECTORY.path_join("image.png"), "synthetic image source bytes")
	var mesh_sha := _write(DIRECTORY.path_join(prototype + ".glb"), "synthetic prototype source bytes")
	_write(DIRECTORY.path_join("world.glb"), "synthetic root source bytes including embedded-image bytes")
	var index := {"prototypes": {prototype: {"sha256": mesh_sha, "images": {"image.png": image_sha}}}}
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	var source := {"schemaVersion": "1.0.0", "asset": {"id": "source-graph-fixture", "glb": "world.glb",
		"units": "meters", "coordinateSystem": {"upAxis": "Y"}, "bounds": {"min": [0,0,0], "max": [1,1,1]}},
		"externalResources": {"image.png": image_sha}, "externalMeshes": {prototype + ".glb": mesh_sha},
		"spawnPoints": [], "collision": {}, "navigation": {}}
	var path := DIRECTORY.path_join("world.json")
	_write(path, JSON.stringify(source))
	var manifest := WorldManifest.load_file(path)
	var first := Graph.describe(manifest)
	_expect(bool(first.get("complete", false)) and first.get("nodes", []).size() == 3,
		"actual source SHA graph deduplicates direct and transitive references to one image")
	if not bool(first.get("complete", false)):
		quit(1)
		return
	var mesh: Dictionary = {}
	var image: Dictionary = {}
	for row: Dictionary in first.nodes:
		if row.kind == "prototype": mesh = row
		elif row.kind == "image": image = row
	_expect(not mesh.is_empty() and str(mesh.source_sha256) == mesh_sha and mesh_sha != prototype,
		"prototype filename identity is not mistaken for its actual source-file SHA")
	_expect(mesh.get("dependencies", []) == [str(image.get("key", ""))],
		"prototype-to-image dependency is transitive and explicit")
	_expect(first.get("allocation_kind") == "unknown_cpu_gpu_allocation" and not bool(first.verification_reuse),
		"source identity does not claim allocation measurement or sealed content")
	_write(DIRECTORY.path_join("image.png"), "different same length image source!")
	var changed := Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)), "changed image bytes fail closed without timestamp/size reuse")
	_write(DIRECTORY.path_join("image.png"), "synthetic image source bytes")
	index.prototypes[prototype]["sha256"] = "b".repeat(64)
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	changed = Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)), "mutable prototype index cannot silently rewrite an actual source identity")
	index.prototypes[prototype]["sha256"] = mesh_sha
	_write(DIRECTORY.path_join("index.json"), JSON.stringify(index))
	source.asset["id"] = "changed-manifest"
	_write(path, JSON.stringify(source))
	changed = Graph.describe(manifest)
	_expect(not bool(changed.get("complete", false)) and changed.reason == "joined_manifest_identity_changed",
		"joined builder metadata cannot be paired with newer mutable manifest bytes")
	print("resource dependency graph tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)

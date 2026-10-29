extends SceneTree
## Tiny read-only-provider/portable-writer contracts. No map cook or renderer.
const Installed := preload("res://src/world/installed_world_cache.gd")
const Writer := preload("res://src/world/map_geometry_writer.gd")
const Geometry := preload("res://src/world/map_geometry_cache.gd")
const Collision := preload("res://src/world/map_collision_cache.gd")
const Paving := preload("res://src/world/map_paving_cache.gd")
var failures := 0
var checks := 0
var folder := ""
var created: Array[String] = []

func _init() -> void:
	run.call_deferred()

func check(ok: bool, label: String) -> void:
	checks += 1
	if ok: print("PASS: " + label)
	else:
		failures += 1
		push_error("installed world: " + label)

func write(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
	if not created.has(path): created.append(path)

func json_bytes(value: Dictionary) -> PackedByteArray:
	return JSON.stringify(value, "", true, true).to_utf8_buffer()

func hex(value: String) -> String:
	return Installed._digest(value.to_utf8_buffer())

func bind_catalog(root: String, catalog: Dictionary, descriptor: String) -> void:
	var encoded := json_bytes(catalog)
	write(root.path_join(catalog.compatibility).path_join("catalog.json"), encoded)
	write(descriptor, json_bytes({"schema": 1, "policy": Installed.POLICY, "variants": {
		catalog.compatibility: {"catalog": catalog.compatibility + "/catalog.json", "sha256": Installed._digest(encoded)}}}))

func portable_writer() -> void:
	var native_scope := "prepared-world/" + hex("writer-%d" % OS.get_process_id()) + "/geometry/" + hex("geometry")
	var first := "res://" + native_scope + "/blobs"
	var stage := folder.path_join("relocated-project")
	var moved := stage.path_join(native_scope).path_join("blobs")
	var root := Node3D.new()
	var child := MeshInstance3D.new()
	child.name = "PreservedMesh"
	child.mesh = ArrayMesh.new()
	root.add_child(child)
	child.owner = root
	var source := PackedScene.new()
	check(source.pack(root) == OK, "tiny source packs")
	var writer := Writer.new()
	check(writer.configure(first), "writer accepts owned user storage")
	writer.external_mesh_ids[child.mesh.get_instance_id()] = hex("prototype")
	var result := writer.write(source)
	check(bool(result.ok) and result.payloads.size() == 2, "portable writer emits scene plus shared mesh: " + str(result.get("error", "")) + " payloads=" + str(result.payloads.size()))
	if bool(result.ok):
		for path: String in result.payloads:
			write(moved.path_join(path.get_file()), FileAccess.get_file_as_bytes(path))
			DirAccess.remove_absolute(path)
		write(stage.path_join("project.godot"), "config_version=5\n[application]\nconfig/name=\"RL native fixture\"\n".to_utf8_buffer())
		var primary := "res://" + native_scope + "/blobs/" + str(result.path).get_file()
		var probe := "extends SceneTree\nfunc _init():\n\tvar scene = ResourceLoader.load(ProjectSettings.globalize_path('%s'), 'PackedScene', ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene\n\tif scene == null:\n\t\tquit(1)\n\t\treturn\n\tvar node = scene.instantiate()\n\tvar mesh = node.get_node_or_null('PreservedMesh') as MeshInstance3D\n\tvar ok = mesh != null and mesh.mesh != null\n\tnode.free()\n\tprint('PORTABLE_NATIVE_CHILD_OK' if ok else 'PORTABLE_NATIVE_CHILD_FAILED')\n\tquit(0 if ok else 1)\n" % primary
		write(stage.path_join("verify.gd"), probe.to_utf8_buffer())
		var output: Array = []
		var exit := OS.execute(OS.get_executable_path(), PackedStringArray(["--headless", "--quit-after", "60", "--path",
			ProjectSettings.globalize_path(stage), "--script", "res://verify.gd"]), output, true, false)
		check(exit == 0 and "PORTABLE_NATIVE_CHILD_OK" in "\n".join(output),
			"absolute primary plus stable res:// child load in relocated project after source originals are removed")
	root.free()

func run() -> void:
	folder = "user://installed-world-contract-%d" % OS.get_process_id()
	var root := folder.path_join("installed")
	var descriptor := folder.path_join("descriptor.json")
	var policies := {"geometry": hex("geometry"), "collision": hex("collision"), "paving": hex("paving")}
	var identity := Installed.compatibility(policies.geometry, policies.collision, policies.paving)
	var key := "world|eloria-assets/maps/fixture/world.json"
	var targets := {}
	var files := {}
	var metadata := {}
	for family: String in Installed.FAMILIES:
		var extension := "scn" if family == "geometry" else ("rlc" if family == "collision" else "res")
		var blob := family.to_utf8_buffer()
		var sha := Installed._digest(blob)
		var relative: String = family + "/" + policies[family] + "/blobs/" + sha + "." + extension
		write(root.path_join(identity).path_join(relative), blob)
		files[relative] = {"sha256": sha, "bytes": blob.size()}
		var entry := {"schema": 1, "source": key.get_slice("|", 1), "policy": policies[family], "inputs": [{"path": "eloria-assets/maps/fixture/world.json", "sha256": hex("source")}]}
		if family == "geometry": entry.merge({"kind": "world", "primary": relative, "payloads": {relative: sha}, "shared_meshes": {}})
		elif family == "collision": entry.merge({"blob": relative, "sha256": sha})
		else: entry["meshes"] = {"Terrain": {"blob": relative, "sha256": sha}}
		var entry_path: String = family + "/" + policies[family] + "/entries/" + hex(key) + ".json"
		var encoded := json_bytes(entry)
		write(root.path_join(identity).path_join(entry_path), encoded)
		files[entry_path] = {"sha256": Installed._digest(encoded), "bytes": encoded.size()}
		targets[family] = entry_path
		metadata[family] = entry
	var catalog := {"schema": 1, "policy": Installed.POLICY, "compatibility": identity, "platform": OS.get_name(),
		"renderer": RenderingServer.get_current_rendering_method(), "engine": Installed._engine(),
		"geometry_policy": policies.geometry, "collision_policy": policies.collision, "paving_policy": policies.paving,
		"scope_sha256": hex("scope"), "registry_sha256": hex("registry"), "target_keys": [key], "targets": {key: targets}, "files": files}
	bind_catalog(root, catalog, descriptor)
	var accepted := Installed._bound_catalogs(descriptor, root)
	check(accepted.size() == 1, "PCK-style descriptor SHA binds a compatible complete catalog")
	if not accepted.is_empty():
		var resolved := accepted[0]
		for family: String in Installed.FAMILIES:
			var entry := Installed._entry(resolved, family, key)
			check(not entry.is_empty() and entry.inputs == metadata[family].inputs, family + " source closure is preserved while cache paths relocate")
		var geometry := Installed._entry(resolved, "geometry", key)
		check(str(geometry.primary).begins_with(root.path_join(identity)) and geometry.payloads.has(geometry.primary), "geometry primary and payload references resolve together")
		var bad := catalog.duplicate(true)
		bad.renderer = "incompatible-renderer"
		check(not Installed._validate_catalog(bad, identity), "other renderer cannot claim cache compatibility")
		bad = catalog.duplicate(true)
		bad.files[targets.geometry].bytes = -1
		check(not Installed._validate_catalog(bad, identity), "invalid file bounds reject catalog")
		bad = catalog.duplicate(true)
		bad.targets[key].geometry = "../outside.json"
		check(not Installed._validate_catalog(bad, identity), "entry traversal rejects catalog")
		write(root.path_join(identity).path_join(targets.geometry), json_bytes({"changed": true}))
		check(Installed._entry(resolved, "geometry", key).is_empty(), "changed installed metadata fails exact SHA acceptance")
		write(root.path_join(identity).path_join("catalog.json"), json_bytes({"changed": true}))
		check(Installed._bound_catalogs(descriptor, root).is_empty(), "changed catalog fails immutable descriptor SHA")
	portable_writer()
	check(Geometry.set_release_output(true).begins_with("res://prepared-world/"), "release output namespace derives from current compatibility policies")
	check(Geometry.set_release_output(false).begins_with("user://"), "release override restores ordinary user cache output")
	# Only our fixture files are removed; all source models remain untouched.
	for path: String in created: DirAccess.remove_absolute(path)
	print("INSTALLED WORLD CACHE: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

extends SceneTree
## A map load hashes its own world.glb and world.json once, for the package
## digest, and names those raw file digests in its load-scoped proof, so the
## geometry, collision and paving inputs that list the same files are not hashed
## again in that load. The combined digest is unchanged, a manifest whose line
## endings were folded is never named, and the collision cache's hashes join the
## proof the paving cache reads next. Run with an isolated user directory.
const MapCache := preload("res://src/world/map_scene_cache.gd")
const Geometry := preload("res://src/world/map_geometry_cache.gd")
const Collision := preload("res://src/world/map_collision_cache.gd")
const DIRECTORY := "user://package-digest-proof-tests"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func write(name: String, bytes: PackedByteArray) -> String:
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	var path := DIRECTORY.path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
	return path

## The per-byte fold every manifest went through before the CR-free fast path.
static func folded(raw: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray()
	for index: int in raw.size():
		if raw[index] == 13 and index + 1 < raw.size() and raw[index + 1] == 10:
			continue
		out.append(raw[index])
	return out

func _run() -> void:
	var glb := write("world.glb", "glTF fixture bytes".to_utf8_buffer())
	var lf := write("world.json", "{\n\"asset\": 1\n}\n".to_utf8_buffer())
	var crlf := write("world_crlf.json", "{\r\n\"asset\": 1\r\n}\r\n".to_utf8_buffer())

	var parts := MapCache.package_digest_parts(lf, glb)
	expect(str(parts.digest) == MapCache.package_digest(lf, glb) and not str(parts.digest).is_empty(),
		"package_digest is the parts' digest")
	expect(str(parts.glb_sha256) == FileAccess.get_sha256(glb), "the glb's own digest is reported")
	expect(str(parts.manifest_sha256) == FileAccess.get_sha256(lf),
		"an LF manifest's raw digest is reported: no byte was folded")
	var folded_parts := MapCache.package_digest_parts(crlf, glb)
	expect(str(folded_parts.digest) == str(parts.digest),
		"a CRLF manifest still digests as its LF twin (server cross-check unchanged)")
	expect(str(folded_parts.manifest_sha256).is_empty() and str(folded_parts.glb_sha256) == str(parts.glb_sha256),
		"a folded manifest's digest is never offered as its file's")
	var missing := MapCache.package_digest_parts(DIRECTORY.path_join("absent.json"), glb)
	expect(str(missing.digest).is_empty() and str(missing.glb_sha256).is_empty()
		and str(missing.manifest_sha256).is_empty() and MapCache.package_digest(DIRECTORY.path_join("absent.json"), glb).is_empty(),
		"an unreadable manifest reports nothing")

	var samples: Array[PackedByteArray] = ["{\"a\": 1}".to_utf8_buffer(), "a\r\nb\rc\r\n".to_utf8_buffer(),
		"\r".to_utf8_buffer(), "\r\n".to_utf8_buffer(), PackedByteArray()]
	var same := true
	for sample: PackedByteArray in samples:
		same = same and MapCache._strip_carriage_returns(sample) == folded(sample)
	expect(same, "the CR-free fast path folds exactly as the byte loop did")

	var manifest := WorldManifest.new()
	manifest.verification_diagnostics = {"failures": 0}
	manifest.package_files_verified = {glb: str(parts.glb_sha256), lf: str(parts.manifest_sha256)}
	var proof := Geometry.world_proof(manifest, str(parts.digest))
	expect(str(proof.get(Geometry.logical(glb), "")) == str(parts.glb_sha256)
		and str(proof.get(Geometry.logical(lf), "")) == str(parts.manifest_sha256),
		"the load's proof names the package's own two files")
	expect(not proof.values().has(str(parts.digest)), "the combined digest is not a file's proof")
	manifest.verification_diagnostics = {"failures": 1}
	expect(Geometry.world_proof(manifest, str(parts.digest)).is_empty(),
		"a load whose verification failed proves nothing")

	var dependency := write("dependency.glb", "dependency".to_utf8_buffer())
	var rows := [{"path": lf, "sha256": FileAccess.get_sha256(lf)},
		{"path": dependency, "sha256": FileAccess.get_sha256(dependency)}]
	var shared := {}
	var diagnostics := {"enabled": true}
	expect(Collision._inputs(rows, lf, shared, diagnostics) and int(diagnostics.get("hash_calls", 0)) == 2,
		"the collision cache hashes inputs its proof does not name")
	expect(str(shared.get(lf, "")) == str(rows[0].sha256) and str(shared.get(dependency, "")) == str(rows[1].sha256),
		"and adds each matching one to the load's proof")
	var again := {"enabled": true}
	expect(Collision._inputs(rows, lf, shared, again) and int(again.get("hash_calls", 0)) == 0
		and int(again.get("proof_hits", 0)) == 2, "the next cache in the same load hashes none of them again")
	write("dependency.glb", "changed".to_utf8_buffer())
	var fresh := {}
	expect(not Collision._inputs(rows, lf, fresh) and not fresh.has(dependency),
		"a changed input still fails a load without that proof, and is not recorded")

	for name: String in ["world.glb", "world.json", "world_crlf.json", "dependency.glb"]:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(DIRECTORY.path_join(name)))
	print("package digest proof: ", failures, " failures")
	quit(failures)

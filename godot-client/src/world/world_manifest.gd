class_name WorldManifest
extends RefCounted

const SUPPORTED_SCHEMA_MAJOR := 1
const ResourceDiagnostics := preload("res://src/world/resource_diagnostics.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")

var source_path := ""
var data: Dictionary = {}
var errors: Array[String] = []
var warnings: Array[String] = []
## Last verification only; no file-stat/read pass is added to count bytes.
var verification_diagnostics: Dictionary = {}
## Exact road dependency hashes verified for this load, never a persistent cache.
var road_ground_verified: Dictionary = {}
## External resource URI -> sha256 of each file this load hashed and found
## matching; the load-scoped proof GeometryCache.world_proof hands on.
var external_verified: Dictionary = {}
## Path -> sha256 of this package's own glb and manifest, as this load hashed
## them for its package digest (MapSceneCache.package_digest_parts; the
## manifest only when its bytes needed no normalising). Load-scoped, as above.
var package_files_verified: Dictionary = {}
## URI -> [path, expected sha256] whose hash `verify_external_resources(true)`
## left to the step that consumes the file (`verify_pending_external`).
var _external_pending: Dictionary = {}
var _verification_timings: Dictionary = {}

static func load_file(path: String) -> WorldManifest:
	var result := WorldManifest.new()
	result.source_path = path
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		result.errors.append("manifest_open_failed: " + path)
		return result
	var parsed = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		result.errors.append("manifest_json_invalid")
		return result
	result.data = parsed
	result._validate()
	return result

func is_valid() -> bool:
	return errors.is_empty()

func asset_id() -> String:
	return str(data.get("asset", {}).get("id", ""))

func glb_path() -> String:
	var relative := str(data.get("asset", {}).get("glb", ""))
	return source_path.get_base_dir().path_join(relative)

func road_ground_config() -> Dictionary:
	var value: Variant = data.get("roadGround", {})
	return value if value is Dictionary else {}

func has_streaming_chunks() -> bool:
	return data.has("streamingChunks")

## Current packages contain loose mutable files and provide no enforceable
## sealed-content provider. Build metadata, a digest manifest, timestamps and
## environment variables do not make those files immutable. Keep verification
## strict until a future provider can attest the bytes actually consumed.
static func external_verification_policy() -> Dictionary:
	return {"mode": "full_hash", "reuse_enabled": false, "sealed_generation": "",
		"reason": "no_enforceable_sealed_installed_content_provider"}

## Checks every external resource of this load and hashes each file (at most
## once per path). With `defer_hashes` every check still runs now, but the
## hashes wait for the step that consumes the files: the loader's raw import
## hashes the very source bytes it decodes, and a VRAM sidecar (hashed as it is
## read) stands in for a source it never reads; `verify_pending_external`
## hashes whatever else is left, with the same failures. Nothing is reused
## from another load.
func verify_external_resources(defer_hashes := false) -> Array[String]:
	var began := Time.get_ticks_usec()
	var timings: Dictionary = {}
	verification_diagnostics = {"resource_references": 0, "hashes_attempted": 0,
		"paths_rejected": 0, "failures": 0, "elapsed_us": 0, "timings": {},
		"policy": external_verification_policy()}
	external_verified = {}
	_external_pending = {}
	_verification_timings = timings
	var digests: Dictionary = {}
	var failures: Array[String] = []
	failures.append_array(VramTextures.image_policy_errors(data, glb_path().get_base_dir()))
	if not failures.is_empty():
		verification_diagnostics.failures = failures.size()
		verification_diagnostics.elapsed_us = Time.get_ticks_usec() - began
		return failures
	var resources: Variant = data.get("externalResources", {})
	if not resources is Dictionary:
		failures.append("externalResources must be a URI-to-SHA256 object")
		verification_diagnostics.failures = failures.size()
		verification_diagnostics.elapsed_us = Time.get_ticks_usec() - began
		return failures
	verification_diagnostics.resource_references = (resources as Dictionary).size()
	var source := ProjectSettings.globalize_path(source_path).replace("\\", "/").simplify_path()
	var scope := ProjectSettings.globalize_path("res://../eloria-assets").replace("\\", "/").simplify_path()
	if not source.to_lower().begins_with(scope.to_lower() + "/"):
		# Isolated validation fixtures can live under user://; ordinary world
		# packages share only within the authored asset tree.
		var user_scope := ProjectSettings.globalize_path("user://").replace("\\", "/").simplify_path().trim_suffix("/")
		scope = user_scope if source.to_lower().begins_with(user_scope.to_lower() + "/") else source.get_base_dir()
	for raw_uri: Variant in resources:
		var uri := str(raw_uri).replace("\\", "/")
		var path := ProjectSettings.globalize_path(glb_path()).replace("\\", "/").get_base_dir().path_join(uri).simplify_path()
		if uri.is_absolute_path() or ":" in uri or not path.to_lower().begins_with(scope.to_lower() + "/"):
			failures.append("external resource outside asset scope: " + uri)
			verification_diagnostics.paths_rejected += 1
			continue
		var expected := str(resources[raw_uri])
		var actual := ""
		# Preserve the original short-circuit: invalid expected digests never
		# cause a file read merely for instrumentation.
		if expected.length() == 64:
			# Only a URI the import reads under this very spelling is deferred; a
			# backslashed or escaped one names another file there, so hash it now.
			if defer_hashes and uri == str(raw_uri) and uri.uri_file_decode() == uri:
				_external_pending[raw_uri] = [path, expected]
				continue
			actual = _hash_once(path, digests)
		if expected.length() != 64 or actual != expected:
			failures.append("external resource missing or digest mismatch: " + uri)
		else:
			external_verified[raw_uri] = expected
	if defer_hashes and not failures.is_empty():
		# A load that fails here reports every failure, hashes included.
		return verify_external_resources(false)
	verification_diagnostics.failures = failures.size()
	verification_diagnostics.hashes_deferred = _external_pending.size()
	verification_diagnostics.elapsed_us = Time.get_ticks_usec() - began
	verification_diagnostics.timings = ResourceDiagnostics.snapshot(timings)
	return failures

## Whether some external resource of this load still waits for its hash.
func external_hashes_pending() -> bool:
	return not _external_pending.is_empty()

## Completes a deferred `verify_external_resources`: hashes every pending file
## once, except the URIs in `attested` (consumed and verified as read: decoded
## source bytes that matched, or a sidecar uploaded in place of the source),
## and fails the URIs in `mismatched` (consumed bytes that did not match)
## without reading them again. Returns the failures the up-front pass would
## have reported for those URIs, in manifest order.
func verify_pending_external(attested: Dictionary = {}, mismatched: Dictionary = {}) -> Array[String]:
	var began := Time.get_ticks_usec()
	var digests: Dictionary = {}
	var failures: Array[String] = []
	# A consumer reads one file per distinct digest; when two pending URIs share
	# a digest but not a path, which file was read is unknown, so neither counts.
	var paths_by_sha: Dictionary = {}
	for raw_uri: Variant in _external_pending:
		var pending: Array = _external_pending[raw_uri]
		var paths: Dictionary = paths_by_sha.get(pending[1], {})
		paths[pending[0]] = true
		paths_by_sha[pending[1]] = paths
	var consumed := 0
	for raw_uri: Variant in data.get("externalResources", {}):
		if not _external_pending.has(raw_uri):
			continue
		var pending: Array = _external_pending[raw_uri]
		var expected := str(pending[1])
		if mismatched.has(raw_uri):
			failures.append("external resource missing or digest mismatch: " + str(raw_uri).replace("\\", "/"))
		elif attested.has(raw_uri) and (paths_by_sha[expected] as Dictionary).size() == 1:
			consumed += 1
		elif _hash_once(str(pending[0]), digests) == expected:
			external_verified[raw_uri] = expected
		else:
			failures.append("external resource missing or digest mismatch: " + str(raw_uri).replace("\\", "/"))
	_external_pending.clear()
	verification_diagnostics.failures = int(verification_diagnostics.get("failures", 0)) + failures.size()
	verification_diagnostics.consumption_attested = int(verification_diagnostics.get("consumption_attested", 0)) + consumed
	verification_diagnostics.elapsed_us = int(verification_diagnostics.get("elapsed_us", 0)) + Time.get_ticks_usec() - began
	verification_diagnostics.timings = ResourceDiagnostics.snapshot(_verification_timings)
	return failures

## FileAccess.get_sha256 of `path`, read once per verification pass however
## many URIs name it.
func _hash_once(path: String, digests: Dictionary) -> String:
	if digests.has(path):
		return str(digests[path])
	var hash_began := Time.get_ticks_usec()
	var actual := FileAccess.get_sha256(path)
	ResourceDiagnostics.record(_verification_timings, &"external_image_hash", hash_began, true)
	verification_diagnostics.hashes_attempted += 1
	digests[path] = actual
	return actual

func coordinate_adapter() -> CoordinateAdapter:
	var asset: Dictionary = data.get("asset", {})
	var coordinate: Dictionary = data.get("coordinateTransform", {})
	if coordinate.is_empty():
		coordinate = {
			"metresPerTile": 1.0,
			"origin": asset.get("origin", [0.0, 0.0, 0.0]),
			"walkingHeight": asset.get("origin", [0.0, 0.0, 0.0])[1],
			"invertServerY": true}
		warnings.append("coordinateTransform missing; using explicit documented defaults")
	return CoordinateAdapter.new(coordinate)

func _validate() -> void:
	var version := str(data.get("schemaVersion", ""))
	if version.is_empty():
		errors.append("schemaVersion missing")
	elif int(version.get_slice(".", 0)) != SUPPORTED_SCHEMA_MAJOR:
		errors.append("unsupported schemaVersion: " + version)
	var asset = data.get("asset")
	if not asset is Dictionary:
		errors.append("asset object missing")
		return
	for key in ["id", "glb", "units", "coordinateSystem", "bounds"]:
		if not asset.has(key):
			errors.append("asset." + key + " missing")
	errors.append_array(VramTextures.image_policy_errors(data, glb_path().get_base_dir()))
	if str(asset.get("units", "")) != "meters":
		errors.append("only metre GLB assets are currently supported")
	var axes: Dictionary = asset.get("coordinateSystem", {})
	if axes.get("upAxis") != "Y":
		errors.append("only Y-up GLB assets are currently supported")
	if not data.has("spawnPoints"):
		warnings.append("spawnPoints missing")
	if not data.has("collision"):
		warnings.append("collision declarations missing")
	if not data.has("navigation"):
		warnings.append("navigation declarations missing")
	if data.has("roadGround"):
		var roads: Variant = data.roadGround
		if not roads is Dictionary:
			errors.append("roadGround must be an object")
		else:
			var path := str(roads.get("metadata", "")).replace("\\", "/")
			var digest := str(roads.get("sha256", ""))
			if path.is_empty() or path.is_absolute_path() or ":" in path or ".." in path.split("/") or not path.ends_with(".json"):
				errors.append("roadGround metadata must be a relative package JSON path")
			if digest.length() != 64 or not digest.is_valid_hex_number(false):
				errors.append("roadGround metadata SHA256 missing or invalid")
	if has_streaming_chunks():
		_validate_chunks()

func _validate_chunks() -> void:
	var config: Variant = data.streamingChunks
	if not config is Dictionary:
		errors.append("streamingChunks must be an object")
		return
	if str(config.get("schemaVersion", "")) != "1.0" or str(config.get("coordinateSpace", "")) != "territory-local":
		errors.append("unsupported streamingChunks schema/coordinateSpace")
	var chunks: Variant = config.get("chunks", [])
	if not chunks is Array or chunks.is_empty():
		errors.append("streamingChunks.chunks must be a nonempty array")
		return
	var ids: Dictionary = {}
	for value: Variant in chunks:
		if not value is Dictionary:
			errors.append("streaming chunk must be an object")
			continue
		var identity := str(value.get("id", ""))
		var path := str(value.get("manifest", "")).replace("\\", "/")
		if identity.is_empty() or ids.has(identity):
			errors.append("streaming chunk id missing or duplicated: " + identity)
		ids[identity] = true
		for field: String in ["estimatedResidentBytes", "geometryResidentBytes", "roadGroundResidentBytes"]:
			if value.has(field) and (not (value[field] is int or value[field] is float) or not is_finite(float(value[field])) or float(value[field]) < 1):
				errors.append("streaming chunk memory estimate must be positive: " + identity)
		# Shared images by content hash; pooled prototypes by identity (the
		# prototype file's stem, which is also a SHA256).
		for field: String in ["sharedResourceResidentBytes", "sharedMeshResidentBytes"]:
			var shared: Variant = value.get(field, {})
			if not shared is Dictionary:
				errors.append("streaming chunk shared resources must be an object: " + identity)
				continue
			for hash: Variant in shared:
				var bytes: Variant = shared[hash]
				if not hash is String or str(hash).length() != 64 or not str(hash).is_valid_hex_number(false):
					errors.append("streaming chunk resource key must be SHA256: " + identity)
				if not (bytes is int or bytes is float) or not is_finite(float(bytes)) or float(bytes) < 0:
					errors.append("streaming chunk shared memory estimate must be nonnegative: " + identity)
		if path.is_absolute_path() or ".." in path.split("/") or not path.ends_with(".json"):
			errors.append("streaming chunk manifest must be a relative package JSON: " + identity)
		var bounds: Variant = value.get("bounds", {})
		if not bounds is Dictionary or not bounds.get("min") is Array or not bounds.get("max") is Array:
			errors.append("streaming chunk bounds missing: " + identity)
			continue
		if bounds.min.size() != 3 or bounds.max.size() != 3:
			errors.append("streaming chunk bounds must contain two vec3: " + identity)
			continue
		for axis: int in 3:
			if not (bounds.min[axis] is int or bounds.min[axis] is float) or not (bounds.max[axis] is int or bounds.max[axis] is float):
				errors.append("streaming chunk bounds must be numeric: " + identity)
			elif not is_finite(float(bounds.min[axis])) or not is_finite(float(bounds.max[axis])) or float(bounds.min[axis]) > float(bounds.max[axis]):
				errors.append("streaming chunk bounds invalid: " + identity)

class_name WorldManifest
extends RefCounted

const SUPPORTED_SCHEMA_MAJOR := 1

var source_path := ""
var data: Dictionary = {}
var errors: Array[String] = []
var warnings: Array[String] = []

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

func has_streaming_chunks() -> bool:
	return data.has("streamingChunks")

func verify_external_resources() -> Array[String]:
	var failures: Array[String] = []
	var resources: Variant = data.get("externalResources", {})
	if not resources is Dictionary:
		failures.append("externalResources must be a URI-to-SHA256 object")
		return failures
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
			continue
		var expected := str(resources[raw_uri])
		if expected.length() != 64 or FileAccess.get_sha256(path) != expected:
			failures.append("external resource missing or digest mismatch: " + uri)
	return failures

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
		for field: String in ["estimatedResidentBytes", "geometryResidentBytes"]:
			if value.has(field) and (not (value[field] is int or value[field] is float) or not is_finite(float(value[field])) or float(value[field]) < 1):
				errors.append("streaming chunk memory estimate must be positive: " + identity)
		var shared: Variant = value.get("sharedResourceResidentBytes", {})
		if not shared is Dictionary:
			errors.append("streaming chunk shared resources must be an object: " + identity)
		else:
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

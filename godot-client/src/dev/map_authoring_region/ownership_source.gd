@tool
extends RefCounted
## Source-file identity is raw SHA-256 plus region ID; vectors are preview only.

const SOURCE_DIR := "eloria-assets/maps/nymara-regions/_continent"
const PLAN_PATH := SOURCE_DIR + "/diagonal-plan.json"
const FEATURE_BASELINE_PATH := SOURCE_DIR + "/ownership/plan-feature-baseline-v1.json"
const SCHEMA := "eloria-continent-ownership-v1"
const STORAGE := preload("res://src/dev/map_authoring_region/storage_contract.gd")


static func contained(root: String, relative: String) -> String:
	var name := relative.replace("\\", "/")
	if name.is_empty() or ":" in name or name.begins_with("/"):
		return ""
	for part in name.split("/", true):
		if part in ["", ".", ".."]:
			return ""
	var target := root.path_join(name)
	# On Windows is_link checks FILE_ATTRIBUTE_REPARSE_POINT, including junctions.
	# Check each ancestor too: simplify_path alone cannot establish containment.
	var component := target
	while not component.is_empty():
		var parent := component.get_base_dir()
		if parent == component or parent.is_empty():
			break
		var directory := DirAccess.open(parent)
		if directory != null and directory.is_link(component.get_file()):
			return ""
		component = parent
	return target


static func load_source(project_directory: String = "") -> Dictionary:
	var project := project_directory
	if project.is_empty():
		project = ProjectSettings.globalize_path("res://")
	project = project.replace("\\", "/").simplify_path().trim_suffix("/")
	var checkout := project.get_base_dir()
	var marker := contained(checkout, "godot-client/project.godot")
	var plan_path := contained(checkout, PLAN_PATH)
	if project.get_file() != "godot-client" or marker.is_empty() or \
			not FileAccess.file_exists(marker) or plan_path.is_empty() or \
			not FileAccess.file_exists(plan_path):
		return {"error": "Ownership source requires a client checkout with godot-client/project.godot and the continent plan; links/junctions are not supported."}
	var plan_bytes := FileAccess.get_file_as_bytes(plan_path)
	var plan: Variant = JSON.parse_string(plan_bytes.get_string_from_utf8())
	if plan is not Dictionary:
		return {"error": "Continent ownership plan is not a JSON object."}
	var base := {"error": "", "selected": false, "checkout": checkout,
		"project": project, "plan_path": plan_path, "plan": plan,
		"plan_sha256": _sha_bytes(plan_bytes), "dependency_paths": PackedStringArray([plan_path])}
	if not plan.has("ownership_contract"):
		return base
	var selection: Variant = plan.ownership_contract
	if selection is not Dictionary or selection.size() != 3 or \
			not selection.has_all(["path", "sha256", "revision"]) or \
			selection.path is not String or selection.revision is not String or \
			String(selection.revision).is_empty() or not _is_sha(selection.sha256):
		return {"error": "ownership_contract requires exactly path, sha256 and revision."}
	var source_path := contained(checkout.path_join(SOURCE_DIR), selection.path)
	if source_path.is_empty() or source_path.get_extension() != "json" or \
			not FileAccess.file_exists(source_path):
		return {"error": "Selected ownership source is missing or escapes containment (including links/junctions)."}
	var bytes := FileAccess.get_file_as_bytes(source_path)
	if _sha_bytes(bytes) != selection.sha256:
		return {"error": "Selected ownership source SHA-256 changed; update the reviewed selection before editing."}
	var document: Variant = JSON.parse_string(bytes.get_string_from_utf8())
	if document is not Dictionary or document.get("schema") != SCHEMA or \
			document.get("revision") != selection.revision or \
			document.get("boundaryRule") != "lexical-region-id" or \
			document.get("regions") is not Dictionary or \
			document.get("bounds") != plan.get("bounds") or plan.get("regions") is not Array:
		return {"error": "Selected ownership source schema/revision/domain does not match the plan."}
	var ids: Array = []
	for row: Variant in plan.regions:
		if row is not Dictionary or row.get("id") is not String or ids.has(row.id) or \
				not document.regions.has(row.id):
			return {"error": "Selected ownership region IDs do not match the plan."}
		ids.append(row.id)
		var record: Variant = document.regions[row.id]
		if record is not Dictionary or record.get("coordinateFrame") is not Dictionary or \
				record.get("baselineStorage") is not Dictionary or record.get("ownershipPolygon") is not Array:
			return {"error": "Selected ownership region record is malformed."}
		var frame: Dictionary = record.coordinateFrame
		var storage: Dictionary = record.baselineStorage
		if not _vector(frame.get("continentTranslation"), 3) or \
				not _vector(frame.get("serverOrigin"), 2) or not _same_vector(frame.get("origin"), [0, 0, 0]) or \
				frame.get("metresPerTile") != 1 or frame.get("invertServerY") != true or \
				not _vector(storage.get("serverCells"), 2) or \
				not _vector(storage.get("collisionOriginMetres"), 2) or \
				not _same_vector(row.get("center"), [frame.continentTranslation[0], frame.continentTranslation[2]]):
			return {"error": "Selected ownership frame differs from the frozen plan translation or supported local frame."}
		if record.ownershipPolygon.size() < 3:
			return {"error": "Selected ownership polygon requires at least three vertices."}
		for point: Variant in record.ownershipPolygon:
			if not _vector(point, 2):
				return {"error": "Selected ownership polygon contains invalid scalar coordinates."}
	if ids.size() != document.regions.size():
		return {"error": "Selected ownership region IDs do not match the plan."}
	base.merge({"selected": true, "source_path": source_path, "document": document,
		"source_sha256": selection.sha256, "region_ids": ids,
		"dependency_paths": PackedStringArray([plan_path, source_path])}, true)
	var baseline_path := contained(checkout, FEATURE_BASELINE_PATH)
	if baseline_path.is_empty():
		return {"error": "Certified plan-feature baseline rejects link/junction indirection."}
	if not FileAccess.file_exists(baseline_path):
		return {"error": "Selected editor ownership requires the certified plan-feature baseline."}
	if FileAccess.file_exists(baseline_path):
		var baseline_bytes := FileAccess.get_file_as_bytes(baseline_path)
		var baseline: Variant = JSON.parse_string(baseline_bytes.get_string_from_utf8())
		var original: Dictionary = plan.duplicate(true)
		original.erase("ownership_contract")
		if baseline is not Dictionary or original != baseline:
			return {"error": "Original plan content differs from its certified feature baseline; only ownership_contract may change."}
		base["feature_baseline_path"] = baseline_path
		base["feature_baseline_sha256"] = _sha_bytes(baseline_bytes)
		base.dependency_paths.append(baseline_path)
	return base


static func region_data(source: Dictionary, region_id: String) -> Dictionary:
	if not String(source.get("error", "")).is_empty() or not source.get("selected", false):
		return source
	if not source.document.regions.has(region_id):
		return {"error": "Region is absent from selected ownership: " + region_id}
	var record: Dictionary = source.document.regions[region_id]
	var binding := {"path": SOURCE_DIR + "/" + String(source.plan.ownership_contract.path).replace("\\", "/"),
		"sha256": source.source_sha256, "revision": source.document.revision, "regionId": region_id,
		"planPath": PLAN_PATH, "planSha256": source.plan_sha256}
	var result := source.duplicate(true)
	result.merge({"binding": binding, "polygon_scalars": record.ownershipPolygon.duplicate(true),
		"frame": record.coordinateFrame, "storage": record.baselineStorage,
		"repository_dependencies": [{"path": PLAN_PATH, "sha256": source.plan_sha256},
			{"path": binding.path, "sha256": binding.sha256}]}, true)
	result.repository_dependencies.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.path < b.path)
	if source.has("feature_baseline_path"):
		result.repository_dependencies.append({"path": FEATURE_BASELINE_PATH, "sha256": source.feature_baseline_sha256})
		result.repository_dependencies.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.path < b.path)
	return result


static func frame_error(data: Dictionary, document: Dictionary) -> String:
	var validation := STORAGE.validate(document.get("server"))
	if not String(validation.error).is_empty():
		return validation.error
	if not data.get("selected", false):
		return String(data.get("error", ""))
	var frame: Dictionary = data.frame
	var storage: Dictionary = data.storage
	var server: Variant = document.get("server")
	if server is not Dictionary or document.get("regionId") != data.binding.regionId or \
			not _same_vector(document.get("continentTranslation"), frame.continentTranslation) or \
			not _same_vector(server.get("origin"), frame.serverOrigin) or \
			server.get("metresPerTile", 1) != frame.metresPerTile or \
			not _same_vector(server.get("localOrigin", [0, 0, 0]), frame.origin) or \
			server.get("invertServerY", true) != frame.invertServerY or \
			(frame.has("walkingHeight") and server.get("walkingHeight") != frame.walkingHeight):
		return "Authoring frame differs from selected frozen ownership source."
	var baseline := STORAGE.bounds({"cells": storage.serverCells,
		"serverStorageVersion": 1, "serverTileMin": storage.get("serverTileMin")})
	if not String(baseline.error).is_empty():
		return "Invalid ownership baseline storage: " + String(baseline.error)
	if not STORAGE.contains(validation, baseline):
		return "Authoring storage must contain the entire frozen ownership baseline."
	return ""


static func scene_error(data: Dictionary, region: Node3D) -> String:
	return String(scene_contract(data, region).error)


static func source_spec(data: Dictionary, region_id: String) -> Dictionary:
	var relative := "godot-client/world_authoring/regions/" + region_id + "/region-authoring-spec.json"
	var path := contained(data.checkout, relative)
	if path.is_empty():
		return {"error": "Region authoring spec path escapes the checkout."}
	if not FileAccess.file_exists(path):
		return {"error": "", "document": {}, "binding": {}}
	var bytes := FileAccess.get_file_as_bytes(path)
	var spec: Variant = JSON.parse_string(bytes.get_string_from_utf8())
	if spec is not Dictionary or spec.get("schema") != "eloria-region-authoring-spec-v1" or spec.get("regionId") != region_id:
		return {"error": "Region authoring spec is invalid or names a different region."}
	return {"error": "", "document": spec, "binding": {"path": relative, "sha256": _sha_bytes(bytes)}}


static func scene_contract(data: Dictionary, region: Node3D) -> Dictionary:
	var initial := String(data.get("error", ""))
	if not initial.is_empty():
		return {"error": initial}
	var source := source_spec(data, String(region.get("region_id")))
	if not String(source.error).is_empty():
		return source
	var translation: Vector3 = region.get("continent_translation")
	var origin: Vector2i = region.get("server_origin")
	var cells: Vector2i = region.get("server_cells")
	var collision: Vector2 = region.get("collision_origin_metres")
	var document := {"regionId": region.get("region_id"),
		"continentTranslation": [translation.x, translation.y, translation.z],
		"server": {"origin": [origin.x, origin.y], "cells": [cells.x, cells.y],
			"collisionOriginMetres": [collision.x, collision.y], "metresPerTile": region.get("metres_per_tile")}}
	var version: int = region.get("server_storage_version")
	var minimum: Vector2i = region.get("server_tile_min")
	if version == 0 and minimum != Vector2i.ZERO:
		return {"error": "A saved nonzero server_tile_min requires server_storage_version = 1."}
	if version != 0:
		document.server.merge({"serverStorageVersion": version, "serverTileMin": [minimum.x, minimum.y]})
	if source.document.is_empty():
		if data.get("selected", false) or version != 0:
			return {"error": "Selected ownership or versioned storage requires the registered region authoring spec."}
	else:
		var spec: Dictionary = source.document
		var spec_error := frame_error(data, spec)
		if not spec_error.is_empty():
			return {"error": spec_error}
		var expected := STORAGE.validate(spec.server)
		if not _same_vector(spec.get("continentTranslation"), document.continentTranslation) or \
				not _same_vector(spec.server.get("origin"), document.server.origin) or \
				expected.cells != cells or expected.minimum != minimum or \
				spec.server.get("metresPerTile", 1) != document.server.metresPerTile:
			return {"error": "Saved scene storage/frame differs from its region authoring spec."}
		# Optional source frame values have no editable scene control; preserve them
		# exactly instead of inventing walkingHeight or silently dropping a field.
		for field: String in ["localOrigin", "invertServerY", "walkingHeight"]:
			if spec.server.has(field):
				document.server[field] = spec.server[field]
		if expected.versioned and version == 0:
			document.server.merge({"serverStorageVersion": 1, "serverTileMin": [0, 0]})
	var message := frame_error(data, document)
	if not message.is_empty():
		return {"error": message}
	return {"error": "", "server": document.server, "source": source}


static func unchanged(data: Dictionary) -> bool:
	var current := region_data(load_source(data.project), data.binding.regionId)
	return String(current.get("error", "")).is_empty() and current.get("binding") == data.binding and \
		current.get("repository_dependencies") == data.repository_dependencies


static func migration_sources(checkout: String, document: Dictionary) -> Dictionary:
	var result := {"error": "", "repository_dependencies": [], "dependency_paths": PackedStringArray()}
	var terrain: Variant = document.get("terrain", {})
	if terrain is not Dictionary:
		return {"error": "Terrain specification must be an object."}
	if not terrain.has("migration"):
		return result
	var migration: Variant = terrain.migration
	if migration is not Dictionary or migration.get("revision") != "global-lattice-envelope-v1" or \
			not _integer_vector(migration.get("globalVertexMin"), 2) or not _is_sha(migration.get("previousGridSha256")) or \
			migration.get("sharedFieldPath") is not String or not _is_sha(migration.get("sharedFieldSha256")):
		return {"error": "Terrain migration provenance is malformed."}
	var manifest_path := contained(checkout, migration.sharedFieldPath)
	if manifest_path.is_empty() or not FileAccess.file_exists(manifest_path) or FileAccess.get_sha256(manifest_path) != migration.sharedFieldSha256:
		return {"error": "Terrain shared-field manifest is missing, changed, or outside the checkout."}
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if manifest is not Dictionary or manifest.get("schema") != "eloria-terrain-shared-field-v1" or manifest.get("lattice") is not Dictionary:
		return {"error": "Terrain shared-field manifest schema is invalid."}
	var lattice: Dictionary = manifest.lattice
	if lattice.get("spacing") != 2 or lattice.get("order") != "row-major-x-fast" or \
			not _integer_vector(lattice.get("vertices"), 2) or min(lattice.vertices[0], lattice.vertices[1]) < 2 or \
			not _vector(lattice.get("originMetres"), 2) or not _vector(terrain.get("origin"), 2) or \
			not _vector(document.get("continentTranslation"), 3):
		return {"error": "Terrain shared-field lattice is invalid."}
	for i in 2:
		if terrain.origin[i] + document.continentTranslation[i * 2] != lattice.originMetres[i] + migration.globalVertexMin[i] * 2:
			return {"error": "Terrain migration globalVertexMin differs from the saved grid identity."}
	result.repository_dependencies.append({"path": migration.sharedFieldPath, "sha256": migration.sharedFieldSha256})
	result.dependency_paths.append(manifest_path)
	for key: String in ["heights", "colors"]:
		var record: Variant = manifest.get(key)
		var encoding := "float32-little-endian" if key == "heights" else "rgba8"
		if record is not Dictionary or record.get("path") is not String or not _is_sha(record.get("sha256")) or record.get("encoding") != encoding:
			return {"error": "Terrain shared-field array metadata is invalid: " + key}
		var path := contained(checkout, record.path)
		if path.is_empty() or not FileAccess.file_exists(path) or FileAccess.get_sha256(path) != record.sha256 or result.dependency_paths.has(path):
			return {"error": "Terrain shared-field array is missing, changed, or outside the checkout: " + key}
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null or file.get_length() != int(lattice.vertices[0]) * int(lattice.vertices[1]) * 4:
			return {"error": "Terrain shared-field array byte count differs from its lattice: " + key}
		file.close()
		result.repository_dependencies.append({"path": record.path, "sha256": record.sha256})
		result.dependency_paths.append(path)
	result.repository_dependencies.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.path < b.path)
	result["migration"] = migration.duplicate(true)
	return result


static func region_migration(source: Dictionary, region_id: String) -> Dictionary:
	var spec_path := contained(source.checkout, "godot-client/world_authoring/regions/" + region_id + "/region-authoring-spec.json")
	if spec_path.is_empty():
		return {"error": "Region terrain spec path escapes the checkout."}
	if not FileAccess.file_exists(spec_path):
		return {"error": "", "repository_dependencies": [], "dependency_paths": PackedStringArray()}
	var spec: Variant = JSON.parse_string(FileAccess.get_file_as_string(spec_path))
	if spec is not Dictionary:
		return {"error": "Region terrain spec is invalid JSON."}
	return migration_sources(source.checkout, spec)


static func _integer_vector(value: Variant, count: int) -> bool:
	if not _vector(value, count):
		return false
	for part: Variant in value:
		if float(part) != floor(float(part)):
			return false
	return true


static func entry_error(root: Node3D, entry: Dictionary) -> String:
	var spec_path := String(entry.get("authoring_spec_path", ""))
	if not spec_path.is_empty():
		if FileAccess.get_sha256(ProjectSettings.globalize_path(spec_path)) != entry.get("authoring_spec_sha256"):
			return "Authoring spec changed since catalog load; refresh before editing."
		var source := region_data(load_source(String(entry.get("ownership_project", ""))), String(entry.id))
		var storage_error := scene_error(source, root)
		if not storage_error.is_empty():
			return storage_error
	if entry.has("ownership_source"):
		var data := region_data(load_source(String(entry.get("ownership_project", ""))), String(entry.id))
		if data.get("binding") != entry.ownership_source:
			return "Selected ownership changed since catalog load; refresh before editing."
		if data.get("repository_dependencies") != entry.get("ownership_repository_dependencies"):
			return "Ownership dependencies changed since catalog load; refresh before editing."
		return scene_error(data, root)
	var expected := String(root.get("ownership_polygon_sha256"))
	return "" if not expected.is_empty() and expected == String(entry.get("ownership_sha256", "")) \
		else "Saved ownership boundary does not match the catalog."


static func validate_for_bake(data: Dictionary, python_executable: String = "") -> Dictionary:
	if not data.get("selected", false):
		return data
	var python := python_executable
	if python.is_empty():
		var arguments := OS.get_cmdline_user_args()
		var index := arguments.find("--python")
		if index >= 0 and index + 1 < arguments.size():
			python = arguments[index + 1]
		else:
			python = "python" if OS.get_name() == "Windows" else "python3"
	var script := contained(data.checkout, SOURCE_DIR + "/ownership_contract.py")
	if script.is_empty() or not FileAccess.file_exists(script):
		return {"error": "Strict Python ownership validator is missing from the checkout."}
	var output: Array = []
	var status := OS.execute(python, PackedStringArray([script, "--plan", data.plan_path,
		"--region", data.binding.regionId]), output, true, false)
	var text := "\n".join(output)
	if status != 0:
		return {"error": "Strict ownership validation failed. Use the build's Python or install its required dependencies in PATH Python.\n" + text}
	var verified: Variant = JSON.parse_string(text)
	if verified is not Dictionary or verified.get("binding") != data.binding or \
			verified.get("repositoryDependencies") != data.repository_dependencies or \
			not _is_sha(verified.get("ownershipPolygonSha256")) or not unchanged(data):
		return {"error": "Ownership inputs changed during strict validation; retry the bake."}
	return {"error": "", "binding": verified.binding,
		"repositoryDependencies": verified.repositoryDependencies,
		"ownershipPolygonSha256": verified.ownershipPolygonSha256}


static func _sha_bytes(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()


static func _is_sha(value: Variant) -> bool:
	return value is String and value.length() == 64 and value == value.to_lower() and value.is_valid_hex_number(false)


static func _vector(value: Variant, count: int) -> bool:
	if value is not Array or value.size() != count:
		return false
	for part: Variant in value:
		if (part is not float and part is not int) or not is_finite(float(part)):
			return false
	return true


static func _same_vector(value: Variant, expected: Array) -> bool:
	if not _vector(value, expected.size()):
		return false
	for index in expected.size():
		if float(value[index]) != float(expected[index]):
			return false
	return true

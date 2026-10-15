class_name MapRegistry
extends RefCounted

## The registry is keyed by Eloria map id, and eloria-server sends that id.
##
## It used to send the path of an Eternal Lands map file instead
## ("./maps/nymara/westhaven.elm"), so a name is still reduced to its basename
## with any extension dropped. That is kept as tolerance, not as a contract: a
## map id has neither a directory nor an extension, so reducing one is a no-op,
## and an older server or a hand-typed console argument still resolves.
static func normalize_server_map_id(value: String) -> String:
	var normalized: String = value.strip_edges().replace("\\", "/")
	while normalized.begins_with("/"):
		normalized = normalized.substr(1)
	while normalized.contains("//"):
		normalized = normalized.replace("//", "/")
	normalized = normalized.get_file()
	if not normalized.get_extension().is_empty():
		normalized = normalized.get_basename()
	return normalized.to_lower()

static func resolve(maps: Dictionary, server_map_id: String) -> Dictionary:
	var wanted: String = normalize_server_map_id(server_map_id)
	var canonical_key: String = ""
	for raw_key: Variant in maps.keys():
		var key: String = str(raw_key)
		if normalize_server_map_id(key) == wanted:
			canonical_key = key
			break
	if canonical_key.is_empty():
		return {}
	var raw_entry: Variant = maps.get(canonical_key, {})
	if not raw_entry is Dictionary:
		return {}
	var entry: Dictionary = raw_entry as Dictionary
	var visited: Dictionary = {}
	while entry.has("alias"):
		if visited.has(canonical_key):
			return {}
		visited[canonical_key] = true
		var alias: String = normalize_server_map_id(str(entry.get("alias", "")))
		canonical_key = ""
		for raw_key: Variant in maps.keys():
			var key: String = str(raw_key)
			if normalize_server_map_id(key) == alias:
				canonical_key = key
				break
		if canonical_key.is_empty():
			return {}
		raw_entry = maps.get(canonical_key, {})
		if not raw_entry is Dictionary:
			return {}
		entry = raw_entry as Dictionary
	var result: Dictionary = entry.duplicate(true)
	result["registryKey"] = canonical_key
	return result

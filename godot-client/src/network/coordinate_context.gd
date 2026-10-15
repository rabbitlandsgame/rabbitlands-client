extends RefCounted
## One synchronous connection context; renderer state never establishes trust.
const Profile = preload("res://src/network/coordinate_profile.gd")
const Transport = preload("res://src/network/coordinate_transport.gd")
var expected: Dictionary = {}
var names: Dictionary = {}
var profiles: Dictionary = {}
var requested := false
var selected := false
var epoch := 0
var map_id := ""
var handles: Dictionary = {}
var pending: Dictionary = {}
var generation := 0

func configure(catalog: Dictionary, map_names: Dictionary = {}) -> Dictionary:
	if selected or requested:
		return Profile.failure("coordinate_catalog_during_session")
	var checked: Dictionary = {}
	var aliases: Dictionary = {}
	for key: Variant in catalog:
		var parsed := Profile.from_registry(catalog[key])
		if not parsed.ok or key != parsed.profile.descriptor().mapId:
			return Profile.failure("coordinate_catalog_profile")
		checked[key] = parsed.profile.descriptor()
		aliases[key] = key
	for name: Variant in map_names:
		var target: Variant = map_names[name]
		if not Profile.map_text(name) or not target is String or not checked.has(target):
			return Profile.failure("coordinate_catalog_name")
		if aliases.has(name) and aliases[name] != target:
			return Profile.failure("coordinate_catalog_ambiguous_name")
		aliases[name] = target
	Profile._freeze(checked)
	Profile._freeze(aliases)
	expected = checked
	names = aliases
	return {"ok": true}

func reset() -> void:
	requested = false
	selected = false
	profiles.clear()
	pending.clear()
	handles.clear()
	epoch = 0
	map_id = ""
	generation += 1

## Programmatic/test seam only. No normal client login advertises the feature.
func prepare_selection() -> Dictionary:
	if requested or selected or expected.is_empty():
		return Profile.failure("coordinate_selection_unavailable")
	requested = true
	return {"ok": true}

func receive(payload: PackedByteArray) -> Dictionary:
	if not pending.is_empty():
		return Profile.failure("coordinate_activation_interrupted")
	var parsed := Transport.decode_context(payload, expected)
	if not parsed.ok:
		return parsed
	var context: Dictionary = parsed.context
	if context.op == "accepted":
		if not requested or selected:
			return Profile.failure("coordinate_unsolicited_acceptance")
		selected = true
		return {"ok": true}
	if not selected:
		return Profile.failure("coordinate_not_selected")
	var additions: Dictionary = {}
	for descriptor: Dictionary in context.profiles:
		var profile: Variant = Profile.parse(descriptor).profile
		if profiles.has(descriptor.mapId) and profiles[descriptor.mapId].canonical_bytes() != profile.canonical_bytes():
			return Profile.failure("coordinate_profile_conflict")
		additions[descriptor.mapId] = profile
	if context.op == "activate":
		if int(context.epoch) != epoch + 1:
			return Profile.failure("coordinate_epoch_sequence")
		pending = context.duplicate(true)
		pending["parsed_profiles"] = additions
	else:
		profiles.merge(additions, true)
	return {"ok": true}

func before_packet(command: int, change_map_command: int) -> Dictionary:
	if not pending.is_empty() and command != change_map_command:
		return Profile.failure("coordinate_activation_interrupted")
	return {"ok": true}

func commit(name: String) -> Dictionary:
	if not selected:
		var canonical: String = str(names.get(name, ""))
		if expected.has(canonical) and expected[canonical].serverTileMin != [0, 0]:
			return Profile.failure("coordinate_offset_without_selection")
		return {"ok": true}
	if pending.is_empty() or names.get(name, "") != pending.mapId:
		return Profile.failure("coordinate_change_map_mismatch")
	profiles.merge(pending.parsed_profiles, true)
	var replacement: Dictionary = {}
	for entry: Dictionary in pending.handles:
		replacement[int(entry.handle)] = entry.mapId
	handles = replacement
	map_id = pending.mapId
	epoch = int(pending.epoch)
	pending.clear()
	return {"ok": true}

func ready() -> bool:
	return selected and epoch > 0 and pending.is_empty() and profiles.has(map_id)

func token() -> Dictionary:
	return {"generation": generation, "epoch": epoch, "map": map_id}

func matches(captured: Dictionary) -> bool:
	return captured == token() and (not selected or ready())

func named_profile(name: String) -> Variant:
	return profiles.get(names.get(name, ""))

## Admin JSON is already logical. Its local catalog can verify a remote map
## without installing a binary decoding profile or changing the active epoch.
func admin_bounds(map: Dictionary) -> Dictionary:
	if map.has("coordinatesSupported") and not map.coordinatesSupported is bool:
		return Profile.failure("coordinate_admin_support_flag")
	var canonical: String = str(names.get(str(map.get("id", "")), ""))
	if not expected.has(canonical):
		return Profile.failure("coordinate_admin_unsupported_map")
	var descriptor: Dictionary = expected[canonical]
	if map.has("coordinateRevision") and map.coordinateRevision != descriptor.coordinateRevision:
		return Profile.failure("coordinate_admin_revision_mismatch")
	for key: String in ["serverTileMin", "serverCells"]:
		if map.has(key):
			if not map[key] is Array or map[key].size() != 2:
				return Profile.failure("coordinate_admin_bounds_mismatch")
			for index: int in range(2):
				if not Profile.number(map[key][index]) or map[key][index] != descriptor[key][index]:
					return Profile.failure("coordinate_admin_bounds_mismatch")
	for index: int in range(2):
		var key: String = ["width", "height"][index]
		if map.has(key) and (not Profile.number(map[key]) or map[key] != descriptor.serverCells[index]):
			return Profile.failure("coordinate_admin_bounds_mismatch")
	if not bool(map.get("coordinatesSupported", true)):
		return Profile.failure("coordinate_admin_unsupported_map")
	return {"ok": true, "mapId": canonical, "minimum": descriptor.serverTileMin.duplicate(),
		"cells": descriptor.serverCells.duplicate()}

func logical_point(name: String, x: Variant, y: Variant) -> Dictionary:
	var profile: Variant = named_profile(name)
	if profile == null:
		return Profile.failure("coordinate_undefined_map")
	for value: Variant in [x, y]:
		if not Profile.number(value) or value < -2147483648 or value > 2147483647 or floor(float(value)) != value:
			return Profile.failure("coordinate_logical_integer")
	return profile.to_wire(int(x), int(y))

func _point(row: Dictionary, name: String) -> Dictionary:
	var profile: Variant = named_profile(name)
	if profile == null:
		return Profile.failure("coordinate_undefined_map")
	var converted: Dictionary = profile.to_logical(row.get("x"), row.get("y"))
	if converted.ok:
		row.x = converted.tile.x
		row.y = converted.tile.y
		if row.has("map_id"):
			row.map_id = names[name]
	return converted

## Decode once before any reducer mutation; failed rows never partially apply.
func convert(event: Dictionary) -> Dictionary:
	if not selected:
		return {"ok": true, "event": event}
	var result: Dictionary = event.duplicate(true)
	var kind: String = str(result.type)
	if kind == "invalid":
		return Profile.failure(str(result.get("error", "coordinate_invalid_packet")))
	if kind == "adjacent_maps":
		return Profile.failure("coordinate_legacy_handle_table")
	if kind in ["actor_commands", "you_are", "ground_bag", "ground_bags", "map_objects",
			"world_object", "teleporters", "teleport", "fire", "play_sound", "ground_missile"] and not ready():
		return Profile.failure("coordinate_no_active_context")
	var rows: Array = []
	var row_maps: Array = []
	match kind:
		"invasion_assistant":
			var state: Dictionary = result.state
			if state.get("kind") == "map":
				if not state.get("map") is Dictionary:
					return Profile.failure("coordinate_admin_map")
				if state.has("coordinatesSupported") and not state.coordinatesSupported is bool:
					return Profile.failure("coordinate_admin_support_flag")
				var bounds := admin_bounds(state.get("map", {}))
				if not bounds.ok:
					if bounds.error != "coordinate_admin_unsupported_map":
						return bounds
					state["coordinatesSupported"] = false
					for key: String in ["locations", "players", "creatures"]:
						state[key] = []
				elif not bool(state.get("coordinatesSupported", true)):
					for key: String in ["locations", "players", "creatures"]:
						state[key] = []
				else:
					var profile: Variant = Profile.from_registry(expected[bounds.mapId]).profile
					for key: String in ["locations", "players", "creatures"]:
						if not state.get(key, []) is Array:
							return Profile.failure("coordinate_admin_rows")
						for row: Variant in state.get(key, []):
							if not row is Dictionary:
								return Profile.failure("coordinate_admin_row")
							for value: Variant in [row.get("x"), row.get("y")]:
								if not Profile.number(value) or floor(float(value)) != value or value < -2147483648 or value > 2147483647:
									return Profile.failure("coordinate_admin_point")
							if not profile.to_wire(int(row.x), int(row.y)).ok:
								return Profile.failure("coordinate_admin_point")
					state["coordinatesSupported"] = true
					state.map["serverTileMin"] = bounds.minimum
					state.map["width"] = bounds.cells[0]
					state.map["height"] = bounds.cells[1]
		"actor_spawn":
			var handle: int = int(result.get("map_handle", 0))
			if not ready() or not handles.has(handle):
				return Profile.failure("coordinate_unknown_actor_handle")
			result["map"] = handles[handle]
			rows.append(result)
			row_maps.append(result.map)
		"ground_bag", "teleport", "fire", "play_sound", "ground_missile":
			rows.append(result)
			row_maps.append(map_id)
		"ground_bags", "map_objects", "world_object":
			rows = result.get("bags", result.get("objects", []))
			for _row: Variant in rows:
				row_maps.append(map_id)
		"teleporters":
			for tile: Vector2i in result.tiles:
				rows.append({"x": tile.x, "y": tile.y})
				row_maps.append(map_id)
		"navigation", "map_marker":
			if kind == "map_marker" or bool(result.active):
				rows.append(result)
				row_maps.append(str(result.get("map_reference", result.map_id)))
		"party":
			for row: Dictionary in result.members:
				if not bool(row.online) and str(row.map_id).is_empty():
					continue
				rows.append(row)
				row_maps.append(str(row.map_id))
		"magic_state":
			var data: Dictionary = result.data
			if data.get("kind") == "recall":
				if not data.get("entries", []) is Array:
					return Profile.failure("coordinate_recall_rows")
				for row: Variant in data.get("entries", []):
					if not row is Dictionary:
						return Profile.failure("coordinate_recall_row")
					var valid := logical_point(str(row.get("map", "")), row.get("x"), row.get("y"))
					if not valid.ok:
						return valid
			elif data.has("x") or data.has("y"):
				if not ready():
					return Profile.failure("coordinate_no_active_context")
				if data.has("map") and names.get(data.map, "") != map_id:
					return Profile.failure("coordinate_magic_map_mismatch")
				if data.has("coordinateRevision") and data.coordinateRevision != profiles[map_id].descriptor().coordinateRevision:
					return Profile.failure("coordinate_magic_revision_mismatch")
				var valid := logical_point(map_id, data.get("x"), data.get("y"))
				if not valid.ok:
					return valid
				data["map"] = map_id
				data["coordinateRevision"] = profiles[map_id].descriptor().coordinateRevision
		"lantern_tutorial":
			var state: Dictionary = result.state
			if bool(state.get("active", false)):
				var valid := logical_point(str(state.map), state.target[0], state.target[1])
				if not valid.ok:
					return valid
	if not rows.is_empty() and not ready():
		return Profile.failure("coordinate_no_active_context")
	for index: int in range(rows.size()):
		var converted := _point(rows[index], row_maps[index])
		if not converted.ok:
			return converted
	if kind == "teleporters":
		var tiles: Array[Vector2i] = []
		for row: Dictionary in rows:
			tiles.append(Vector2i(row.x, row.y))
		result.tiles = tiles
	return {"ok": true, "event": result}

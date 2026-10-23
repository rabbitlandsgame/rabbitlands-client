extends RefCounted
## Public, synthetic fixtures only. These coordinates come from the maintained
## southern-streaming-walk and southern-region-routes fixtures. The client driver
## exercises presentation/streaming; it does not certify server pathfinding.
const MountProfiles := preload("res://src/mounts/mount_profiles.gd")

static func resolution(value: String) -> Vector2i:
	var parts := value.to_lower().split("x")
	if parts.size() != 2 or not parts[0].is_valid_int() or not parts[1].is_valid_int():
		return Vector2i(1280, 720)
	return Vector2i(clampi(int(parts[0]), 320, 7680), clampi(int(parts[1]), 240, 4320))

static func mount_rows(records: Dictionary, count: int, map_id: String) -> Dictionary:
	var rows := {}
	var ids := records.keys()
	ids.sort()
	var profiles := MountProfiles.PATHS.keys()
	profiles.sort()
	# Include the local player. Cycling only the explicitly supported profiles
	# preserves approved content and gives exactly 80 mounts in the 160 fixture.
	for index: int in mini(count, ids.size()):
		var id := int(ids[index])
		var record := records[id] as Dictionary
		record["map"] = map_id
		var profile := str(profiles[index % profiles.size()])
		rows[id] = {"schema_version": 1, "actor_id": id, "owner": str(record.name),
			"map": map_id, "mode": "mounted", "gait": "cruise", "mount_id": profile,
			"selected_mount_id": profile, "step_us": 133333, "endurance_ms": 60000,
			"summon_remaining_ms": 0, "combat_remaining_ms": 0,
			"can_summon": false, "blocked_reason": ""}
	return rows

static func mount_profile_counts(rows: Dictionary) -> Dictionary:
	var counts := {}
	for row: Dictionary in rows.values():
		var id := str(row.mount_id)
		counts[id] = int(counts.get(id, 0)) + 1
	return counts

static func southern_route() -> Array[Dictionary]:
	return [
		{"id": "first-southern-border", "kind": "border", "map": "whitehorn_range",
			"start": [118, 19], "approach": [118, 11],
			"destination": "mirrorhold", "arrival": [43, 372]},
		{"id": "consecutive-southern-border", "kind": "border", "map": "mirrorhold",
			"start": [130, 370], "approach": [130, 378],
			"destination": "amethyst_barrens", "arrival": [10, 308]},
		{"id": "interior-entry", "kind": "interior", "map": "amethyst_barrens",
			"start": [198, 34], "approach": [198, 34],
			"destination": "amethyst_barrens_secrets", "arrival": [298, 26]},
		{"id": "interior-return", "kind": "interior_return", "map": "amethyst_barrens_secrets",
			"start": [298, 26], "approach": [297, 26],
			"destination": "amethyst_barrens", "arrival": [198, 34]},
		{"id": "teleport", "kind": "teleport", "map": "amethyst_barrens",
			"start": [198, 34], "approach": [198, 34],
			"destination": "sunmane_steppe", "arrival": [137, 95]},
		{"id": "return", "kind": "teleport_return", "map": "sunmane_steppe",
			"start": [137, 95], "approach": [137, 95],
			"destination": "whitehorn_range", "arrival": [118, 19]},
	]

static func tile(value: Array) -> Vector2i:
	return Vector2i(int(value[0]), int(value[1]))

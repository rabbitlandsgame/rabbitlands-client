extends RefCounted
## Animation's stored transform-key vectors use real_t, narrowing double key
## times in the pinned engine. Preserve exact original clocks in binary f64
## metadata, then restore once before a verified native resource is published.
const META := &"rl_prepared_animation_keys_v1"
const PUBLISHED := &"rl_prepared_animation_keys_published"
static var _mutex := Mutex.new()

static func _plain(value: Variant, depth: int) -> bool:
	if depth > 64 or value is Object or value is Callable or value is Signal:
		return false
	if value is Array:
		for item: Variant in value:
			if not _plain(item, depth + 1): return false
	elif value is Dictionary:
		for key: Variant in value:
			if not _plain(key, depth + 1) or not _plain(value[key], depth + 1): return false
	return true

static func _values_signature(source: Animation, track: int) -> String:
	var values: Array = []
	for key: int in source.track_get_key_count(track):
		var value: Variant = source.track_get_key_value(track, key)
		if not _plain(value, 0):
			return ""
		values.append(value)
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(values))
	return context.finish().hex_encode()

static func _capture(source: Animation) -> Dictionary:
	if source == null or source.get_script() != null or source.resource_local_to_scene:
		return {}
	var tracks: Array[Dictionary] = []
	for track: int in source.get_track_count():
		if source.track_is_compressed(track):
			return {}
		var values_signature := _values_signature(source, track)
		if values_signature.is_empty():
			return {}
		var times := PackedFloat64Array()
		var transitions := PackedFloat64Array()
		for key: int in source.track_get_key_count(track):
			times.append(source.track_get_key_time(track, key))
			transitions.append(source.track_get_key_transition(track, key))
		tracks.append({"type": source.track_get_type(track), "path": source.track_get_path(track),
			"times": times, "transitions": transitions, "values_sha256": values_signature})
	return {"schema": 1, "tracks": tracks}

static func prepare(source: Animation, candidate: Animation) -> bool:
	# Read the original, not duplicate(false)'s already narrowed key properties.
	var clocks := _capture(source)
	if clocks.is_empty() or candidate == null or candidate == source or candidate.get_script() != null \
			or candidate.resource_local_to_scene:
		return false
	if not _validated(candidate, clocks, true):
		return false
	if candidate.has_meta(PUBLISHED):
		candidate.remove_meta(PUBLISHED)
	candidate.set_meta(META, clocks)
	return true

static func _validated(candidate: Animation, clocks: Variant, require_spacing: bool) -> bool:
	if not clocks is Dictionary:
		return false
	var data: Dictionary = clocks
	if data.get("schema") != 1 or not data.get("tracks") is Array \
			or (data.tracks as Array).size() != candidate.get_track_count():
		return false
	for track: int in candidate.get_track_count():
		if candidate.track_is_compressed(track) or not data.tracks[track] is Dictionary:
			return false
		var row: Dictionary = data.tracks[track]
		if not row.get("type") is int or int(row.type) != candidate.track_get_type(track) \
				or not row.get("path") is NodePath or row.path != candidate.track_get_path(track) \
				or not row.get("times") is PackedFloat64Array \
				or not row.get("transitions") is PackedFloat64Array:
			return false
		if not row.get("values_sha256") is String or str(row.values_sha256).length() != 64 \
				or str(row.values_sha256) != _values_signature(candidate, track):
			return false
		var times: PackedFloat64Array = row.times
		var transitions: PackedFloat64Array = row.transitions
		if times.size() != candidate.track_get_key_count(track) or transitions.size() != times.size():
			return false
		for key: int in times.size():
			var time := float(times[key])
			var transition := float(transitions[key])
			if not is_finite(time) or not is_finite(transition) \
					or float(Vector3(transition, 0.0, 0.0).x) != transition:
				return false
			if key > 0 and (time <= times[key - 1] or is_equal_approx(time, times[key - 1])):
				return false
			# track_set_key_time removes/reinserts and approximately equal clocks
			# replace a neighbour. Reject the entire operation before changing any
			# key if restoring this exact indexed sequence could merge/reorder it.
			if require_spacing and key > 0:
				var previous := candidate.track_get_key_time(track, key - 1)
				if time <= previous or is_equal_approx(time, previous):
					return false
			if require_spacing and key + 1 < times.size():
				var following := candidate.track_get_key_time(track, key + 1)
				if time >= following or is_equal_approx(time, following):
					return false
	return true

static func _matches(candidate: Animation, clocks: Dictionary) -> bool:
	for track: int in candidate.get_track_count():
		var actual_times := PackedFloat64Array()
		var actual_transitions := PackedFloat64Array()
		for key: int in candidate.track_get_key_count(track):
			actual_times.append(candidate.track_get_key_time(track, key))
			actual_transitions.append(candidate.track_get_key_transition(track, key))
		var row: Dictionary = clocks.tracks[track]
		var expected_times: PackedFloat64Array = row.times
		var expected_transitions: PackedFloat64Array = row.transitions
		if actual_times.to_byte_array() != expected_times.to_byte_array() \
				or actual_transitions.to_byte_array() != expected_transitions.to_byte_array():
			return false
	return true

static func _restore(candidate: Animation) -> bool:
	if not candidate.has_meta(META):
		return false
	var clocks: Variant = candidate.get_meta(META)
	if not _validated(candidate, clocks, not candidate.has_meta(PUBLISHED)):
		return false
	var data: Dictionary = clocks
	var identity := var_to_bytes(data)
	if candidate.has_meta(PUBLISHED):
		var published: Variant = candidate.get_meta(PUBLISHED)
		# A later consumer mutation cannot be overwritten or silently blessed.
		return published is PackedByteArray and published == identity and _matches(candidate, data)
	for track: int in candidate.get_track_count():
		var row: Dictionary = data.tracks[track]
		var times: PackedFloat64Array = row.times
		var transitions: PackedFloat64Array = row.transitions
		for key: int in times.size():
			if candidate.track_get_key_time(track, key) != times[key] or times[key] == 0.0:
				candidate.track_set_key_time(track, key, times[key])
			if candidate.track_get_key_transition(track, key) != transitions[key] or transitions[key] == 0.0:
				candidate.track_set_key_transition(track, key, transitions[key])
	if not _validated(candidate, data, false) or not _matches(candidate, data):
		return false
	candidate.set_meta(PUBLISHED, identity)
	return true

static func restore_verified(candidate: Animation) -> bool:
	if candidate == null or candidate.get_script() != null or candidate.resource_local_to_scene:
		return false
	_mutex.lock()
	var accepted := _restore(candidate)
	_mutex.unlock()
	return accepted

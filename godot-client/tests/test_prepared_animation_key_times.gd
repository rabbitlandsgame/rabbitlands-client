extends SceneTree
const Keys := preload("res://src/world/prepared_animation_keys.gd")
var failures := 0
var assertions := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	assertions += 1
	if not value:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

func _source() -> Animation:
	var animation := Animation.new()
	animation.length = 1.0
	var track := animation.add_track(Animation.TYPE_POSITION_3D)
	animation.track_set_path(track, NodePath("Skeleton3D:Hips"))
	var times := [0.0, 1.0 / 30.0, 0.11, 0.7]
	for key: int in times.size():
		animation.track_insert_key(track, times[key], Vector3(key * 0.125, key * 0.25, -key * 0.5), 0.37 + key * 0.1)
	return animation

func _keys(animation: Animation) -> PackedByteArray:
	var tracks: Array = []
	for track: int in animation.get_track_count():
		var times := PackedFloat64Array()
		var transitions := PackedFloat64Array()
		var values: Array = []
		for key: int in animation.track_get_key_count(track):
			times.append(animation.track_get_key_time(track, key))
			transitions.append(animation.track_get_key_transition(track, key))
			values.append(animation.track_get_key_value(track, key))
		tracks.append([animation.track_get_type(track), animation.track_get_path(track), times, transitions, values])
	return var_to_bytes(tracks)

func _candidate(source: Animation) -> Animation:
	var candidate := source.duplicate(false) as Animation
	_expect(Keys.prepare(source, candidate), "producer captures original f64 key clocks before property serialization")
	return candidate

func _reject(candidate: Animation, reason: String) -> void:
	var before := _keys(candidate)
	_expect(not Keys.restore_verified(candidate), reason + " is rejected")
	_expect(_keys(candidate) == before, reason + " leaves all keys/values untouched")
	_expect(not candidate.has_meta(Keys.PUBLISHED), reason + " publishes no active-resource marker")

func _run() -> void:
	var source := _source()
	var expected := _keys(source)
	var candidate := _candidate(source)
	var path := "user://prepared-animation-key-times.res"
	_expect(ResourceSaver.save(candidate, path) == OK, "native Animation resource saves")
	var loaded := ResourceLoader.load(path, "Animation", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as Animation
	_expect(loaded != null and loaded.has_meta(Keys.META), "exact clock metadata survives actual binary Animation save/load")
	_expect(_keys(loaded) != expected, "positive control proves built-in real_t serialization narrows 1/30 key time")
	_expect(Keys.restore_verified(loaded) and _keys(loaded) == expected,
		"verified restore recovers exact f64 times/transitions and unchanged key values")
	var published_bytes: PackedByteArray = loaded.get_meta(Keys.PUBLISHED)
	_expect(Keys.restore_verified(loaded) and _keys(loaded) == expected
		and loaded.get_meta(Keys.PUBLISHED) == published_bytes,
		"cached publication is exact and idempotent")

	# Published cached resources are immutable: reject later mutation rather
	# than silently repairing an Animation that active instances may share.
	loaded.track_set_key_time(0, 1, 0.04)
	var mutated := _keys(loaded)
	_expect(not Keys.restore_verified(loaded) and _keys(loaded) == mutated,
		"later mutation of an active cached Animation rejects without rewriting it")
	loaded = null
	var published := _candidate(source)
	_expect(Keys.restore_verified(published), "metadata mutation control begins with a valid published resource")
	var published_data: Dictionary = published.get_meta(Keys.META)
	published_data.tracks[0].values_sha256 = "0".repeat(64)
	mutated = _keys(published)
	_expect(not Keys.restore_verified(published) and _keys(published) == mutated,
		"later mutation of the published metadata rejects without changing live keys")
	published = null
	published_data = {}

	# Local-to-scene Animation duplication would repeat the engine's narrowed
	# tracks/keys storage after restore. Exercise each guard independently.
	var local_source := _source()
	local_source.resource_local_to_scene = true
	var local_candidate := local_source.duplicate(false) as Animation
	local_candidate.resource_local_to_scene = false # Do not mask source guard.
	var before_source := _keys(local_source)
	var before_local := _keys(local_candidate)
	_expect(not Keys.prepare(local_source, local_candidate),
		"local-to-scene source is rejected even when candidate is not local")
	_expect(_keys(local_source) == before_source and _keys(local_candidate) == before_local
		and not local_candidate.has_meta(Keys.META) and not local_candidate.has_meta(Keys.PUBLISHED),
		"source-local rejection leaves both key sets and candidate metadata unchanged")
	local_source = null
	local_candidate = source.duplicate(false) as Animation
	local_candidate.resource_local_to_scene = true
	before_local = _keys(local_candidate)
	_expect(not Keys.prepare(source, local_candidate),
		"local-to-scene candidate is rejected with an ordinary source")
	_expect(_keys(local_candidate) == before_local and not local_candidate.has_meta(Keys.META)
		and not local_candidate.has_meta(Keys.PUBLISHED),
		"candidate-local rejection leaves keys and metadata untouched")
	local_candidate = _candidate(source)
	local_candidate.resource_local_to_scene = true
	_reject(local_candidate, "unpublished local-to-scene reader input")
	local_candidate = _candidate(source)
	_expect(Keys.restore_verified(local_candidate), "cached local guard starts from exact published clocks")
	var local_published: PackedByteArray = local_candidate.get_meta(Keys.PUBLISHED)
	before_local = _keys(local_candidate)
	local_candidate.resource_local_to_scene = true
	_expect(not Keys.restore_verified(local_candidate) and _keys(local_candidate) == before_local
		and local_candidate.get_meta(Keys.PUBLISHED) == local_published,
		"cached local-to-scene mutation rejects without rewriting keys or its old marker")
	local_candidate = null

	var invalid := _candidate(source)
	var data: Dictionary = invalid.get_meta(Keys.META)
	data.tracks[0].times = PackedFloat32Array(Array(data.tracks[0].times))
	_reject(invalid, "non-f64 time metadata")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	data.tracks[0].transitions = PackedFloat64Array([1.0])
	_reject(invalid, "transition count mismatch")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	data.tracks[0].path = NodePath("Skeleton3D:OtherBone")
	_reject(invalid, "track binding mismatch")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	data.tracks[0].type = Animation.TYPE_ROTATION_3D
	_reject(invalid, "track type mismatch")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	data.tracks[0].values_sha256 = "0".repeat(64)
	_reject(invalid, "key value digest mismatch")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	var times: PackedFloat64Array = data.tracks[0].times
	times[1] = INF
	data.tracks[0].times = times
	_reject(invalid, "non-finite original time")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	times = data.tracks[0].times
	times[2] = times[1]
	data.tracks[0].times = times
	_reject(invalid, "duplicate/reordered target times")
	invalid = _candidate(source)
	data = invalid.get_meta(Keys.META)
	times = data.tracks[0].times
	times[1] = 0.000001
	data.tracks[0].times = times
	_reject(invalid, "approximately coincident insertion that could replace a key")
	invalid = null
	data = {}

	# Exercise the public engine compressor rather than claiming a synthetic
	# metadata flag is actual compressed-track coverage.
	var compressed := Animation.new()
	compressed.length = 4.0
	var track := compressed.add_track(Animation.TYPE_POSITION_3D)
	compressed.track_set_path(track, NodePath("Skeleton3D:Hips"))
	for key: int in 101:
		compressed.track_insert_key(track, key / 30.0, Vector3(key * 0.01, sin(key * 0.1), 0))
	compressed.compress(8192, 120, 4.0)
	_expect(compressed.track_is_compressed(track), "positive control has an actual engine-compressed position track")
	var compressed_copy := compressed.duplicate(false) as Animation
	_expect(not Keys.prepare(compressed, compressed_copy), "unsupported compressed producer input is rejected")
	compressed = null
	compressed_copy = null
	candidate = null
	source = null
	await process_frame
	await process_frame
	print("PREPARED_ANIMATION_KEY_TIMES ", "PASS" if failures == 0 else "FAIL", " assertions=", assertions)
	quit(0 if failures == 0 else 1)

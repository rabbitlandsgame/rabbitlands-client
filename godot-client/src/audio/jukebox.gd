extends Node
## Local music preferences. World cues remain authoritative inputs to rules;
## choosing music never changes gameplay or sends anything to the server.

signal changed
signal preferences_changed

const MODES := ["game", "song", "playlist", "shuffle", "silent"]
const MODE_LABELS := ["Let the game decide", "One song", "Playlist", "Shuffle all music", "Silence"]
const REPEATS := ["off", "all", "one"]
const GROUPS := {"day": "Daytime", "night": "Nighttime", "encounter": "Encounters & events"}
const DEFAULT_PATH := "user://jukebox.cfg"

var storage_path := DEFAULT_PATH
var mode := "game"
var song := ""
var active_playlist := "My playlist"
var playlists: Dictionary = {"My playlist": []}
var shuffle := false
var repeat_mode := "all"
var fade_seconds := 2.0
var rules_enabled := true
var rules: Array[Dictionary] = []
var paused := false
var available := true
var save_error := ""
var game_cue := ""
var active_rule := -1
var game_playback: Callable
var personal_playback: Callable
var playback_track: Callable
var pause_playback: Callable

var _player: Node
var _entries: Dictionary = {}
var _contexts: Dictionary = {}
var _queue: Array[String] = []
var _index := -1
var _route_key := ""
var _selection: Dictionary = {}
var _exhausted := false
var _session := false
var _random := RandomNumberGenerator.new()

func configure(catalog: Array, player: Node) -> void:
	_player = player
	_random.randomize()
	for entry: Dictionary in catalog:
		_entries[str(entry.name)] = entry.duplicate(true)
	_contexts = player.programs
	_player.manual_finishing.connect(_on_finishing)
	_player.manual_finished.connect(_on_finished)
	_player.track_changed.connect(func(_title: String, _creator: String) -> void: changed.emit())
	load_preferences()

func title_for(track: String) -> String:
	return str((_entries.get(track, {}) as Dictionary).get("title", track.capitalize()))

func current_track() -> String:
	return str(playback_track.call()) if playback_track.is_valid() else str(_player.current_track())

func _set_paused() -> void:
	_player.set_paused(paused)
	if pause_playback.is_valid():
		pause_playback.call(paused)

func context_name(key: String) -> String:
	return str(GROUPS.get(key, key.capitalize()))

func contexts() -> Array[String]:
	var keys: Array[String] = []
	keys.assign(_contexts.keys())
	keys.sort()
	return keys

func library(query := "", context := "") -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for key: String in _entries:
		var entry: Dictionary = _entries[key].duplicate(true)
		var tags: Array[String] = []
		for cue: String in _contexts:
			if key in _contexts[cue].get("tracks", []):
				tags.append(cue)
		if not context.is_empty() and context not in tags:
			continue
		var haystack := (title_for(key) + " " + str(entry.get("creator", "")) + " " + " ".join(tags)).to_lower()
		var matches := true
		for word: String in query.to_lower().split(" ", false):
			if not haystack.contains(word):
				matches = false
		if matches:
			entry["title"] = title_for(key)
			entry["contexts"] = tags
			result.append(entry)
	result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.title).naturalnocasecmp_to(str(b.title)) < 0)
	return result

func request_game(cue: String) -> void:
	game_cue = cue
	_session = true
	_apply()

func set_available(value: bool) -> void:
	available = value
	if not value:
		_player.stop()
		if not _exhausted:
			_route_key = ""
	else:
		_apply()
	changed.emit()

func disconnect_session() -> void:
	game_cue = ""
	_session = false
	paused = false
	_route_key = ""
	_queue.clear()
	_index = -1
	_exhausted = false
	_player.stop()
	changed.emit()

func choose(value: String, target := "") -> void:
	if value not in MODES:
		return
	if value == "song" and not _entries.has(target):
		return
	if value == "playlist" and not playlists.has(target):
		return
	mode = value
	if value == "song":
		song = target
	elif value == "playlist":
		active_playlist = target
	_session = true
	paused = false
	_route_key = ""
	_commit()

func set_options(random_order: bool, repetition: String, fade: float, use_rules: bool) -> void:
	shuffle = random_order
	repeat_mode = repetition if repetition in REPEATS else "all"
	fade_seconds = clampf(fade, 0.0, 8.0)
	rules_enabled = use_rules
	_commit()

func create_playlist(label: String) -> bool:
	label = label.strip_edges().left(64)
	if label.is_empty() or playlists.has(label) or playlists.size() >= 64:
		return false
	playlists[label] = []
	if not playlists.has(active_playlist):
		active_playlist = label
	_commit()
	return true

func rename_playlist(old: String, label: String) -> bool:
	label = label.strip_edges().left(64)
	if label.is_empty() or not playlists.has(old) or playlists.has(label):
		return false
	playlists[label] = playlists[old]
	playlists.erase(old)
	if active_playlist == old:
		active_playlist = label
	if _selection.get("mode") == "playlist" and _selection.get("target") == old:
		_selection.target = label
	for rule: Dictionary in rules:
		if rule.mode == "playlist" and rule.target == old:
			rule.target = label
	_commit()
	return true

func delete_playlist(label: String) -> void:
	playlists.erase(label)
	if active_playlist == label:
		active_playlist = str(playlists.keys()[0]) if not playlists.is_empty() else ""
	# Keep references visible, but disable rules whose playlist no longer exists.
	for rule: Dictionary in rules:
		if rule.mode == "playlist" and rule.target == label:
			rule.enabled = false
	_commit()

func edit_playlist(label: String, tracks: Array) -> void:
	if not playlists.has(label):
		return
	playlists[label] = _valid_tracks(tracks)
	_commit()

func set_rules(value: Array) -> void:
	rules = _valid_rules(value)
	_commit()

func effective_selection() -> Dictionary:
	active_rule = -1
	var context := game_cue.trim_prefix("@").get_slice("|", 0)
	if rules_enabled and not game_cue.is_empty():
		for index: int in rules.size():
			var rule := rules[index]
			if bool(rule.enabled) and _matches(str(rule.context), context):
				active_rule = index
				return {"mode": rule.mode, "target": rule.target}
	return {"mode": mode, "target": song if mode == "song" else active_playlist if mode == "playlist" else ""}

func _matches(condition: String, context: String) -> bool:
	match condition:
		"day": return context.ends_with("_day")
		"night": return context.ends_with("_night")
		"encounter": return int((_contexts.get(context, {}) as Dictionary).get("priority", 0)) > 0
	return condition == context

func _apply() -> void:
	if _player == null or not available or not _session:
		return
	var selection := effective_selection()
	if selection.mode != "game" and personal_playback.is_valid():
		personal_playback.call()
	var tracks: Array = []
	match str(selection.mode):
		"song": tracks = [selection.target] if _entries.has(selection.target) else []
		"playlist": tracks = playlists.get(selection.target, [])
		"shuffle": tracks = _entries.keys()
	# Repeated world snapshots do not restart a personal queue, including an ended one.
	var key := JSON.stringify([selection, tracks, shuffle])
	if key != _route_key:
		var current: String = _player.current_track()
		var keep_current := not _route_key.is_empty() and _selection == selection and current in tracks and not _exhausted
		_route_key = key
		_selection = selection.duplicate()
		_exhausted = false
		_queue.assign(tracks)
		_index = -1
		if str(selection.mode) not in ["game", "silent"]:
			if shuffle or selection.mode == "shuffle":
				_shuffle_queue()
			if not _queue.is_empty():
				_index = _queue.find(current) if keep_current else 0
				if not keep_current:
					_player.play_track(_queue[_index], fade_seconds)
			else:
				_player.stop()
	match str(selection.mode):
		"game":
			if game_playback.is_valid():
				game_playback.call(game_cue)
			elif game_cue.is_empty():
				_player.stop()
			elif game_cue.begins_with("@"):
				_player.request(game_cue)
			else:
				# Legacy server beds use the same voices with a single-track program.
				_player.programs["jukebox_legacy"] = {"tracks": [game_cue]}
				_player.request("@jukebox_legacy")
		"silent": _player.stop()
	_set_paused()
	changed.emit()

func _shuffle_queue() -> void:
	var previous: String = _player.current_track()
	for index: int in range(_queue.size() - 1, 0, -1):
		var other := _random.randi_range(0, index)
		var temp := _queue[index]
		_queue[index] = _queue[other]
		_queue[other] = temp
	if _queue.size() > 1 and _queue[0] == previous:
		var temp := _queue[0]
		_queue[0] = _queue[1]
		_queue[1] = temp

func toggle_pause() -> void:
	if _exhausted:
		_route_key = ""
		paused = false
		_apply()
	else:
		paused = not paused
		_set_paused()
	changed.emit()

func can_skip() -> bool:
	return available and not _queue.is_empty()

func queue_ended() -> bool:
	return _exhausted

func skip(direction := 1) -> void:
	if _queue.is_empty() or not available:
		return
	paused = false
	_exhausted = false
	_index = posmod(_index + direction, _queue.size())
	_player.play_track(_queue[_index], fade_seconds)
	changed.emit()

func _advance() -> bool:
	if _queue.is_empty() or _exhausted:
		return false
	if repeat_mode != "one":
		if _index + 1 >= _queue.size():
			if repeat_mode == "off":
				return false
			if shuffle or effective_selection().mode == "shuffle":
				_shuffle_queue()
			_index = 0
		else:
			_index += 1
	_player.play_track(_queue[_index], fade_seconds)
	return true

func _on_finishing() -> void:
	if fade_seconds > 0.0:
		_advance()

func _on_finished() -> void:
	if not _advance():
		_exhausted = true
		_player.stop()
	changed.emit()

func _valid_tracks(value: Array) -> Array[String]:
	var result: Array[String] = []
	for track: Variant in value.slice(0, 512):
		if track is String and _entries.has(track) and track not in result:
			result.append(track)
	return result

func _valid_rules(value: Array) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for raw: Variant in value.slice(0, 128):
		if not raw is Dictionary:
			continue
		var condition := str(raw.get("context", ""))
		var action := str(raw.get("mode", ""))
		if (not _contexts.has(condition) and not GROUPS.has(condition)) or action not in MODES:
			continue
		var target := str(raw.get("target", ""))
		var valid := (action != "song" or _entries.has(target)) and (action != "playlist" or playlists.has(target))
		result.append({"enabled": bool(raw.get("enabled", true)) and valid,
			"context": condition, "mode": action, "target": target})
	return result

func load_preferences() -> void:
	var config := ConfigFile.new()
	if config.load(storage_path) != OK:
		return
	var stored: Variant = config.get_value("jukebox", "playlists", {})
	if stored is Dictionary:
		playlists.clear()
		for label: Variant in stored:
			if label is String and not label.strip_edges().is_empty() and label.length() <= 64 and stored[label] is Array and playlists.size() < 64:
				playlists[label] = _valid_tracks(stored[label])
	mode = str(config.get_value("jukebox", "mode", "game"))
	if mode not in MODES:
		mode = "game"
	song = str(config.get_value("jukebox", "song", ""))
	if not _entries.has(song):
		song = ""
	active_playlist = str(config.get_value("jukebox", "active_playlist", ""))
	if not playlists.has(active_playlist):
		active_playlist = str(playlists.keys()[0]) if not playlists.is_empty() else ""
	shuffle = bool(config.get_value("jukebox", "shuffle", false))
	repeat_mode = str(config.get_value("jukebox", "repeat", "all"))
	if repeat_mode not in REPEATS:
		repeat_mode = "all"
	fade_seconds = clampf(float(config.get_value("jukebox", "fade", 2.0)), 0.0, 8.0)
	rules_enabled = bool(config.get_value("jukebox", "rules_enabled", true))
	var stored_rules: Variant = config.get_value("jukebox", "rules", [])
	rules = _valid_rules(stored_rules) if stored_rules is Array else []

func _commit() -> void:
	var config := ConfigFile.new()
	for pair: Array in [["mode", mode], ["song", song], ["active_playlist", active_playlist],
		["playlists", playlists], ["shuffle", shuffle], ["repeat", repeat_mode],
		["fade", fade_seconds], ["rules_enabled", rules_enabled], ["rules", rules]]:
		config.set_value("jukebox", str(pair[0]), pair[1])
	var error := config.save(storage_path)
	save_error = "Could not save music preferences (%s)." % error_string(error) if error != OK else ""
	_apply()
	preferences_changed.emit()
	changed.emit()

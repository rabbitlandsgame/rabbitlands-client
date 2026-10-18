extends Node
## Two voices keep music continuous while the server changes its context.

signal track_changed(title: String, creator: String)

const AudioMix := preload("res://src/audio/audio_mix.gd")
const DIRECTORY := "res://assets/audio/"
const PROGRAM_PATH := DIRECTORY + "music-program.json"
const CACHE_LIMIT := 4
const AMBIENT_COOLDOWN := 6.0

var entries: Dictionary = {}
var programs: Dictionary = {}
var _players: Array[AudioStreamPlayer] = []
var _gains: Array[float] = [0.0, 0.0]
var _targets: Array[float] = [0.0, 0.0]
var _cache: Dictionary = {}
var _cache_order: Array[String] = []
var _request := ""
var _program := ""
var _track := ""
var _resume := ""
var _active := -1
var _fade := 5.0
var _changed_at := -100.0
var _pending := ""
var _completed_cues: Dictionary = {}
var _random := RandomNumberGenerator.new()

func _ready() -> void:
	_random.randomize()
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(PROGRAM_PATH))
	if value is Dictionary:
		programs = value.get("programs", {})
	for index: int in range(2):
		var player := AudioStreamPlayer.new()
		player.name = "Music%d" % index
		player.bus = AudioMix.CATEGORIES.music.bus
		add_child(player)
		player.finished.connect(_on_finished.bind(index))
		_players.append(player)

func configure(catalog: Array) -> void:
	for raw: Variant in catalog:
		var entry: Dictionary = raw
		entries[str(entry.name)] = entry

func _exit_tree() -> void:
	stop()
	_cache.clear()
	_cache_order.clear()

func current_track() -> String:
	return _track

func request(cue: String) -> bool:
	var parts := cue.trim_prefix("@").split("|")
	var key := str(parts[0])
	if not programs.has(key):
		stop()
		return false
	# A restatement is not a new play, including a completed one-shot cue.
	if cue == _request and _active >= 0:
		_pending = ""
		return true
	var next: Dictionary = programs[key]
	var identity := _cue_identity(cue)
	if bool(next.get("once", false)) and _completed_cues.has(identity):
		return request("@" + str(parts[1])) if parts.size() > 1 else false
	if bool(next.get("once", false)) and _active >= 0 and _cue_identity(_request) == identity:
		# The world clock can change the return pool during the same one-shot.
		_resume = str(parts[1]) if parts.size() > 1 else ""
		_request = cue
		return true
	var previous: Dictionary = programs.get(_program, {})
	var now := Time.get_ticks_msec() / 1000.0
	if (_active >= 0 and _players[_active].playing
			and int(next.get("priority", 0)) == 0
			and int(previous.get("priority", 0)) == 0
			and now - _changed_at < AMBIENT_COOLDOWN):
		_pending = cue
		return true
	_pending = ""
	_request = cue
	_resume = str(parts[1]) if parts.size() > 1 else ""
	_program = key
	_fade = maxf(0.05, float(next.get("fade_seconds", 5.0)))
	# Adjacent contexts can share the playing piece without restarting it.
	if (not bool(next.get("once", false)) and _track in next.get("tracks", [])
			and _active >= 0 and _players[_active].playing):
		return true
	return _start(_choose_track(), _fade)

func stop() -> void:
	for player: AudioStreamPlayer in _players:
		player.stop()
		player.stream = null
	_gains = [0.0, 0.0]
	_targets = [0.0, 0.0]
	_active = -1
	_request = ""
	_pending = ""
	_program = ""
	_track = ""
	_resume = ""
	track_changed.emit("", "")

func _choose_track() -> String:
	var choices: Array = (programs.get(_program, {}) as Dictionary).get("tracks", [])
	var fresh: Array[String] = []
	for raw: Variant in choices:
		var name := str(raw)
		if entries.has(name) and (name != _track or choices.size() == 1):
			fresh.append(name)
	if fresh.is_empty():
		return ""
	# Begin with the authored first choice; vary subsequent full plays.
	return fresh[0] if _active < 0 else fresh[_random.randi_range(0, fresh.size() - 1)]

func _cue_identity(cue: String) -> String:
	var parts := cue.split("|")
	return str(parts[0]) + "|" + str(parts[2]) if parts.size() > 2 else cue

func _stream(name: String) -> AudioStream:
	if _cache.has(name):
		_cache_order.erase(name)
		_cache_order.append(name)
		return _cache[name] as AudioStream
	var entry: Dictionary = entries.get(name, {})
	var path := str(entry.get("file", ""))
	if path.is_empty() or path.contains("..") or path.contains(":"):
		return null
	var source := load(DIRECTORY + path) as AudioStream
	if source == null:
		return null
	_cache[name] = source
	_cache_order.append(name)
	while _cache_order.size() > CACHE_LIMIT:
		_cache.erase(_cache_order.pop_front())
	return source

func _start(name: String, fade: float) -> bool:
	if name.is_empty():
		return false
	var source := _stream(name)
	if source == null:
		return false
	var index := 0 if _active < 0 else 1 - _active
	var player := _players[index]
	player.stop()
	# Loop only a single-piece ambient pool. Multi-piece pools advance in _process.
	var stream := source.duplicate() as AudioStream
	var info: Dictionary = programs[_program]
	var looped: bool = not bool(info.get("once", false)) and info.tracks.size() == 1
	if stream is AudioStreamOggVorbis:
		(stream as AudioStreamOggVorbis).loop = looped
	player.stream = stream
	_gains[index] = 1.0 if _active < 0 or not _players[_active].playing else 0.0
	_targets = [0.0, 0.0]
	_targets[index] = 1.0
	player.volume_db = linear_to_db(maxf(0.00001, _gains[index]))
	player.play()
	_active = index
	_track = name
	_fade = maxf(0.05, fade)
	_changed_at = Time.get_ticks_msec() / 1000.0
	var entry: Dictionary = entries[name]
	track_changed.emit(str(entry.get("title", name)), str(entry.get("creator", "")))
	return true

func _process(delta: float) -> void:
	if _active < 0:
		return
	for index: int in range(2):
		_gains[index] = move_toward(_gains[index], _targets[index], delta / _fade)
		_players[index].volume_db = linear_to_db(maxf(0.00001, _gains[index]))
		if _gains[index] <= 0.0 and _targets[index] == 0.0:
			_players[index].stop()
			_players[index].stream = null
	if not _pending.is_empty() and Time.get_ticks_msec() / 1000.0 - _changed_at >= AMBIENT_COOLDOWN:
		var cue := _pending
		_pending = ""
		request(cue)
	var info: Dictionary = programs.get(_program, {})
	if bool(info.get("once", false)) or info.get("tracks", []).size() <= 1:
		return
	var player := _players[_active]
	if player.playing and player.stream != null:
		var remaining := player.stream.get_length() - player.get_playback_position()
		if remaining <= _fade and _targets[1 - _active] == 0.0 and _gains[1 - _active] == 0.0:
			_start(_choose_track(), minf(_fade, maxf(0.05, remaining)))

func _on_finished(index: int) -> void:
	if index != _active:
		return
	var info: Dictionary = programs.get(_program, {})
	if bool(info.get("once", false)):
		_completed_cues[_cue_identity(_request)] = true
		if _completed_cues.size() > 32:
			_completed_cues.erase(_completed_cues.keys()[0])
		if not _resume.is_empty():
			var cue := "@" + _resume
			request(cue)
		else:
			stop()
	else:
		_start(_choose_track(), _fade)

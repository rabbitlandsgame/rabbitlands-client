extends Node
## Plays Eloria's sounds in answer to what the server said happened.
##
## The client had no audio at all. Everything here is triggered by an
## authoritative event - a harvest the server started, an item it put in the
## backpack, a combat outcome it reported, an effect it announced - or by the
## player's own click on a control. Nothing is played on a guess, and nothing
## is played twice for one event: a repeated snapshot that says the same thing
## is not a new event.
##
## Recorded effects and music retain their source licenses and credits in
## assets/audio/CREDITS.txt. build_native_sounds.py converts retained originals.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

const AudioMix := preload("res://src/audio/audio_mix.gd")
const MusicProgramPlayer := preload("res://src/audio/music_program_player.gd")
signal music_changed(title: String, creator: String)
const CATALOG_PATH := "res://assets/audio/catalog.json"
const AUDIO_DIRECTORY := "res://assets/audio/"
## Enough voices for a busy moment without letting one event drown the rest.
const VOICE_COUNT := 8
## The floor between two steps. The server can restate several movement
## commands in one frame; that is one step, not four.
const STEP_INTERVAL_MSEC := 280
const FOOTSTEP_GAIN := 0.32
const FOOTSTEP_VARIANTS := 3
const RAIN_GAIN := 0.85
const RAIN_FADE_RATE := 0.6

var enabled := true:
	set(value):
		enabled = value
		_update_master()
		if not value:
			stop_all(false)
		else:
			play_music(_requested_music)
var volume_linear := AudioMix.MASTER_DEFAULT:
	set(value):
		volume_linear = clampf(value, 0.0, 1.0)
		_update_master()

var category_volumes: Dictionary = {}

## The world supplies the surface at the authoritative tile, independent of
## actor presentation updates (which are coalesced until the end of a frame).
var surface_at_tile: Callable

var _streams: Dictionary = {}
var _music_streams: Dictionary = {}
var _music_player: AudioStreamPlayer = null
var _music_track := ""
## Keep the server's latest choice while muted, so enabling audio resumes it.
var _requested_music := ""
var _program_player: Node
var _music_entries: Array = []
var _voices: Array[AudioStreamPlayer] = []
var _next_voice := 0
## What the last authoritative snapshot said, so a restatement is not an event.
var _harvesting := false
var _combat_event := -1
var _inventory_totals: Dictionary = {}
## Where the server last said the player was standing, so a step is heard when
## the tile changes rather than on every actor packet.
var _local_tile := Vector2i.ZERO
var _has_local_tile := false
var _last_step_msec := -STEP_INTERVAL_MSEC
var _step_actor_id := -1
var _last_step_variant := -1
var _step_random := RandomNumberGenerator.new()
var _rain_player: AudioStreamPlayer
var _rain_amount := 0.0
var _rain_gain := 0.0

func _ready() -> void:
	name = "AudioDirector"
	AudioMix.ensure_buses()
	_update_master()
	for category: String in AudioMix.CATEGORIES:
		set_category_volume(category, float(AudioMix.CATEGORIES[category].volume))
	_step_random.randomize()
	_load_catalog()
	_program_player = MusicProgramPlayer.new()
	add_child(_program_player)
	_program_player.configure(_music_entries)
	_program_player.track_changed.connect(func(title: String, creator: String) -> void:
		music_changed.emit(title, creator))
	AppState.sound_requested.connect(_on_sound_requested)
	AppState.music_requested.connect(_on_music_requested)
	for index: int in range(VOICE_COUNT):
		var player := AudioStreamPlayer.new()
		player.name = "Voice%d" % index
		add_child(player)
		_voices.append(player)
	AppState.state_changed.connect(_on_state_changed)
	AppState.special_effect_requested.connect(_on_special_effect)

func _update_master() -> void:
	AudioMix.ensure_buses()
	AudioMix.set_volume(AudioMix.MASTER_BUS, volume_linear if enabled else 0.0)

func set_category_volume(category: String, value: float) -> void:
	if not AudioMix.CATEGORIES.has(category):
		return
	category_volumes[category] = clampf(value, 0.0, 1.0)
	AudioMix.set_volume(AudioMix.CATEGORIES[category].bus, category_volumes[category])

## The shown precipitation already follows the server's weather transition.
## The caller supplies an empty look indoors or outside an authenticated game.
## Particle visibility is a graphics choice and does not mute the weather.
func set_weather(look: Dictionary) -> void:
	_rain_amount = clampf(float(look.get("precipitation", 0.0)), 0.0, 1.0) \
		if int(look.get("fall", 0)) == 1 else 0.0

func _process(delta: float) -> void:
	_rain_gain = move_toward(_rain_gain, _rain_amount * RAIN_GAIN if enabled else 0.0,
		delta * RAIN_FADE_RATE)
	if _rain_gain <= 0.0:
		if _rain_player != null:
			_rain_player.stop()
		return
	if _rain_player == null:
		if not _streams.has("rain"):
			return
		_rain_player = AudioStreamPlayer.new()
		_rain_player.name = "RainAmbience"
		_rain_player.bus = AudioMix.CATEGORIES.ambience.bus
		_rain_player.stream = AmbientAudioBinder._looping(_streams["rain"] as AudioStream)
		add_child(_rain_player)
	_rain_player.volume_db = linear_to_db(_rain_gain)
	if not _rain_player.playing:
		_rain_player.play()

## The sounds this client knows about, by name.
func sound_names() -> Array[String]:
	var names: Array[String] = []
	for key: Variant in _streams:
		names.append(str(key))
	names.sort()
	return names

## Plays one sound by name. Returns false when audio is off or the name is not
## in the catalog, so a caller can be tested without listening.
func play(name: String, pitch := 1.0, gain := 1.0) -> bool:
	if not enabled or not _streams.has(name):
		return false
	var player: AudioStreamPlayer = _voices[_next_voice]
	_next_voice = (_next_voice + 1) % _voices.size()
	player.stream = _streams[name] as AudioStream
	var mixed_gain: float = gain * (FOOTSTEP_GAIN if name.begins_with("footstep") else 1.0)
	player.set_meta("gain", mixed_gain)
	player.bus = AudioMix.bus_for_sound(name)
	player.volume_db = linear_to_db(maxf(0.0001, mixed_gain))
	player.pitch_scale = pitch
	player.play()
	return true

## The music beds this client knows about, by name.
func music_names() -> Array[String]:
	var names: Array[String] = []
	for entry: Dictionary in _music_entries:
		names.append(str(entry.name))
	names.sort()
	return names

## What is playing under the map, or "" for silence.
func current_music() -> String:
	if _requested_music.begins_with("@") and _program_player != null:
		return str(_program_player.current_track())
	return _music_track

## Plays the named music bed, looping, or stops the music for "". A track this
## client does not have is silence rather than a guess at a substitute, and it
## says so by returning false.
func play_music(track: String) -> bool:
	_requested_music = track
	if track.begins_with("@"):
		if _music_player != null:
			_music_player.stop()
		_music_track = ""
		return bool(_program_player.request(track)) if enabled and _program_player != null else false
	if _program_player != null:
		_program_player.stop()
	if track == _music_track and _music_player != null and _music_player.playing:
		return not track.is_empty()
	_music_track = ""
	if _music_player != null:
		_music_player.stop()
	if track.is_empty() or not enabled:
		return false
	if not _music_streams.has(track):
		return false
	if _music_player == null:
		_music_player = AudioStreamPlayer.new()
		_music_player.name = "Music"
		_music_player.bus = AudioMix.CATEGORIES.music.bus
		add_child(_music_player)
	_music_player.stream = _music_streams[track] as AudioStream
	_music_player.volume_db = 0.0
	_music_player.play()
	_music_track = track
	music_changed.emit(track.capitalize(), "")
	return true

func stop_all(clear_music_request := true) -> void:
	_rain_amount = 0.0
	_rain_gain = 0.0
	if _rain_player != null:
		_rain_player.stop()
	if _program_player != null:
		_program_player.stop()
	for player: AudioStreamPlayer in _voices:
		player.stop()
	if _music_player != null:
		_music_player.stop()
	_music_track = ""
	if clear_music_request:
		_requested_music = ""

## True while any voice is sounding. Used by the tests rather than by the game.
func is_playing() -> bool:
	for player: AudioStreamPlayer in _voices:
		if player.playing:
			return true
	return false

func _load_catalog() -> void:
	var file := FileAccess.open(CATALOG_PATH, FileAccess.READ)
	if file == null:
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return
	for raw_sound: Variant in (parsed as Dictionary).get("sounds", []):
		var sound: Dictionary = raw_sound as Dictionary
		var stream: Resource = load(
			AUDIO_DIRECTORY + str(sound.get("file", "")))
		if stream is AudioStream:
			_streams[str(sound.get("name", ""))] = stream as AudioStream
	for raw_bed: Variant in (parsed as Dictionary).get("music", []):
		var bed: Dictionary = raw_bed as Dictionary
		_music_entries.append(bed)
		# Retain legacy beds for old servers. Program tracks load on demand.
		if str(bed.get("name", "")) not in ["settlement", "wilds", "depths"]:
			continue
		var music: Resource = load(AUDIO_DIRECTORY + str(bed.get("file", "")))
		if music is AudioStream:
			if music is AudioStreamOggVorbis:
				(music as AudioStreamOggVorbis).loop = true
			elif music is AudioStreamWAV:
				var wav := music as AudioStreamWAV
				wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
				wav.loop_begin = 0
				wav.loop_end = roundi(wav.get_length() * wav.mix_rate)
			_music_streams[str(bed.get("name", ""))] = music as AudioStream

## Sounds and music the server placed. Everything else this director plays is
## its own answer to authoritative state; these two are things the client had
## no way of knowing - what somebody else is doing, and what the map sounds
## like - so they arrive on the wire instead.
func _on_sound_requested(sound: Dictionary) -> void:
	play(str(sound.get("name", "")), 1.0, float(sound.get("gain", 1.0)))

func _on_music_requested(track: String) -> void:
	play_music(track)

func _on_state_changed(path: StringName) -> void:
	match path:
		&"harvest":
			var harvesting: bool = bool(AppState.harvest.get("active", false))
			if harvesting and not _harvesting:
				play("harvest_start")
			_harvesting = harvesting
		&"actors", &"local_actor":
			_on_local_actor_moved()
		&"map":
			_reset_steps()
		&"inventory":
			_on_inventory_changed()
		&"combat_state":
			_on_combat_changed()
		&"connection":
			if AppState.connection_state == "disconnected":
				_harvesting = false
				_combat_event = -1
				_reset_steps()
				_inventory_totals.clear()
				stop_all()

## A backpack that gained something makes the gathering sound. The comparison
## is against the previous authoritative snapshot, so a restatement that
## changes nothing is silent.
func _on_inventory_changed() -> void:
	var totals: Dictionary = {}
	var gained := false
	for raw_slot: Variant in AppState.inventory:
		var item: Dictionary = AppState.inventory[raw_slot] as Dictionary
		var image_id: int = int(item.get("image_id", 0))
		var quantity: int = int(item.get("quantity", 0))
		totals[image_id] = int(totals.get(image_id, 0)) + quantity
		if quantity > int(_inventory_totals.get(image_id, 0)):
			gained = true
	if gained and not _inventory_totals.is_empty():
		play("harvest_gather" if _harvesting else "item_pickup")
	_inventory_totals = totals

## A step is heard when the server says the player is standing somewhere else.
## The first tile after login is not a step - the player did not walk there -
## and a burst of movement commands in one frame is still one step.
func _on_local_actor_moved() -> void:
	var actor: Variant = AppState.actors.get(AppState.local_actor_id)
	if actor is not Dictionary:
		return
	if _step_actor_id != AppState.local_actor_id:
		_reset_steps()
		_step_actor_id = AppState.local_actor_id
	var tile := Vector2i(int((actor as Dictionary).get("x", 0)),
		int((actor as Dictionary).get("y", 0)))
	if _has_local_tile and tile == _local_tile:
		return
	var first_sighting: bool = not _has_local_tile
	var displacement := tile - _local_tile
	_local_tile = tile
	_has_local_tile = true
	var now: int = Time.get_ticks_msec()
	if first_sighting or maxi(absi(displacement.x), absi(displacement.y)) > 2:
		return
	if not enabled or now - _last_step_msec < STEP_INTERVAL_MSEC:
		return
	_last_step_msec = now
	var surface := "dirt"
	if surface_at_tile.is_valid():
		surface = str(surface_at_tile.call(tile))
	var variant := _step_random.randi_range(0, FOOTSTEP_VARIANTS - 1)
	if _last_step_variant >= 0:
		variant = (_last_step_variant + _step_random.randi_range(1, FOOTSTEP_VARIANTS - 1)) % FOOTSTEP_VARIANTS
	_last_step_variant = variant
	var sound := "footstep_%s_%d" % [surface, variant + 1]
	if not _streams.has(sound):
		sound = "footstep"
	play(sound, _step_random.randf_range(0.97, 1.03), _step_random.randf_range(0.94, 1.0))

func _reset_steps() -> void:
	_local_tile = Vector2i.ZERO
	_has_local_tile = false
	_step_actor_id = -1
	_last_step_msec = -STEP_INTERVAL_MSEC
	_last_step_variant = -1

func _on_combat_changed() -> void:
	var event: int = int(AppState.combat_state.get("event", 0))
	if event == _combat_event:
		return
	_combat_event = event
	match event:
		EloriaProtocol.COMBAT_EVENT_HIT, EloriaProtocol.COMBAT_EVENT_INCOMING:
			play("combat_hit")
		EloriaProtocol.COMBAT_EVENT_MISS, EloriaProtocol.COMBAT_EVENT_DODGE:
			play("combat_miss")

func _on_special_effect(_effect: Dictionary) -> void:
	play("world_effect")

class_name AmbientAudioBinder
extends RefCounted
## Turns a manifest's `environment.ambientAudio` into real sound in the scene.
##
## The four-gates package has declared its ambience since it was authored - a
## civic murmur over the central plaza and falling water at every `Waterfall_`
## node - and nothing read it, so every map was silent. This is the client side
## of that contract, in the same shape as the light-marker binder: the package
## names a loop, a gain and where it belongs, and the client plays it.
##
## An entry that names a `nodePrefix` becomes one positional player per matching
## node in the loaded scene, at the declared radius. An entry without one is
## played flat, because a `region` is an area the manifest does not give
## geometry for and guessing a position for it would be inventing placement.
##
## Maps that declare nothing get nothing, which is every package but one.

const AudioMix := preload("res://src/audio/audio_mix.gd")
const AUDIO_DIRECTORY := "res://assets/audio/"
const DEFAULT_GAIN := 0.5
const DEFAULT_RADIUS := 60.0

static func apply(manifest: WorldManifest, parent: Node3D,
		world_scene: Node3D, catalog: PackedStringArray) -> int:
	if manifest == null or parent == null:
		return 0
	AudioMix.ensure_buses()
	var environment: Variant = manifest.data.get("environment", {})
	if environment is not Dictionary:
		return 0
	var entries: Variant = (environment as Dictionary).get("ambientAudio", [])
	if entries is not Array:
		return 0
	var bound := 0
	for raw: Variant in entries as Array:
		if raw is not Dictionary:
			continue
		var entry: Dictionary = raw
		var loop_name: String = str(entry.get("loop", ""))
		if not catalog.has(loop_name):
			# A package may name ambience this client has no sound for. That is
			# the package being ahead of the client, not an error to hide.
			push_warning("ambient audio loop not in the catalog: " + loop_name)
			continue
		var stream: Resource = load(AUDIO_DIRECTORY + loop_name + ".wav")
		if stream is not AudioStream:
			continue
		var volume_db: float = linear_to_db(maxf(0.0001,
			float(entry.get("gain", DEFAULT_GAIN))))
		var prefix: String = str(entry.get("nodePrefix", ""))
		if prefix.is_empty():
			bound += _add_flat(parent, entry, stream as AudioStream, volume_db)
		else:
			bound += _add_positional(parent, world_scene, entry, prefix,
				stream as AudioStream, volume_db)
	return bound

static func _add_flat(parent: Node3D, entry: Dictionary, stream: AudioStream,
		volume_db: float) -> int:
	var player := AudioStreamPlayer.new()
	player.name = str(entry.get("id", "Ambience"))
	player.stream = _looping(stream)
	player.bus = AudioMix.CATEGORIES.ambience.bus
	player.volume_db = volume_db
	player.autoplay = true
	parent.add_child(player)
	return 1

static func _add_positional(parent: Node3D, world_scene: Node3D,
		entry: Dictionary, prefix: String, stream: AudioStream,
		volume_db: float) -> int:
	var bound := 0
	for node: Node3D in _nodes_with_prefix(world_scene, prefix):
		var player := AudioStreamPlayer3D.new()
		player.name = "%s_%d" % [str(entry.get("id", "Ambience")), bound]
		player.stream = _looping(stream)
		player.bus = AudioMix.CATEGORIES.ambience.bus
		player.volume_db = volume_db
		player.max_distance = float(entry.get("radius", DEFAULT_RADIUS))
		player.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		player.autoplay = true
		parent.add_child(player)
		player.global_position = node.global_position
		bound += 1
	return bound

static func _nodes_with_prefix(world_scene: Node3D,
		prefix: String) -> Array[Node3D]:
	var found: Array[Node3D] = []
	if world_scene == null:
		return found
	# Walked in scene order rather than with a stack, so the players a package
	# gets are numbered the way its nodes are.
	var pending: Array[Node] = [world_scene]
	var index := 0
	while index < pending.size():
		var node: Node = pending[index]
		index += 1
		for child: Node in node.get_children():
			pending.append(child)
		if node is Node3D and str(node.name).begins_with(prefix):
			found.append(node as Node3D)
	return found

## WAV streams import as one-shots; ambience has to be told to repeat.
static func _looping(stream: AudioStream) -> AudioStream:
	var copy: AudioStream = stream.duplicate() as AudioStream
	if copy is AudioStreamWAV:
		var wav: AudioStreamWAV = copy as AudioStreamWAV
		wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
		wav.loop_begin = 0
		# Imports may be compressed or stereo: byte count is not frame count.
		wav.loop_end = roundi(wav.get_length() * wav.mix_rate)
	return copy

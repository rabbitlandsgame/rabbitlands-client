extends SceneTree
## Guards the ambience a world package declares for itself.
##
## `environment.ambientAudio` has been in the Four Gates manifest since it was
## authored and nothing read it, so every map was silent. A package names a
## loop, a gain and where it belongs; the client plays exactly that and invents
## no placement of its own.

const AudioMix := preload("res://src/audio/audio_mix.gd")

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var catalog := PackedStringArray(["civic_crowd", "waterfall"])

	# One entry with a node prefix, one without: the shape the shipped Four
	# Gates manifest uses.
	var manifest := WorldManifest.new()
	manifest.data = {"environment": {"ambientAudio": [
		{"id": "city-ambience", "region": "central-plaza",
			"loop": "civic_crowd", "gain": 0.5},
		{"id": "falls-ambience", "nodePrefix": "Waterfall_",
			"loop": "waterfall", "gain": 0.7, "radius": 120}]}}
	var world := Node3D.new()
	world.name = "World"
	for index: int in range(2):
		var falls := Node3D.new()
		falls.name = "Waterfall_%d" % index
		falls.position = Vector3(float(index) * 20.0, 0.0, -30.0)
		world.add_child(falls)
	var other := Node3D.new()
	other.name = "Bridge_0"
	world.add_child(other)
	root.add_child(world)
	var parent := Node3D.new()
	root.add_child(parent)

	var bound: int = AmbientAudioBinder.apply(manifest, parent, world, catalog)
	await process_frame
	_expect(bound == 3,
		"one flat player and one per matching node: %d" % bound)
	var flat: AudioStreamPlayer = parent.get_node_or_null(
		"city-ambience") as AudioStreamPlayer
	_expect(flat != null and flat.stream != null and flat.autoplay,
		"an entry with no node prefix is played flat")
	_expect(flat != null and flat.bus == AudioMix.CATEGORIES.ambience.bus,
		"flat ambience uses the player's ambience volume")
	_expect(flat != null
		and is_equal_approx(db_to_linear(flat.volume_db), 0.5),
		"the gain the package asked for is the gain used")
	var positional: AudioStreamPlayer3D = parent.get_node_or_null(
		"falls-ambience_0") as AudioStreamPlayer3D
	_expect(positional != null
		and is_equal_approx(positional.max_distance, 120.0),
		"a positional entry carries the declared radius")
	_expect(positional != null and positional.bus == AudioMix.CATEGORIES.ambience.bus
		and AudioServer.get_bus_send(AudioServer.get_bus_index(positional.bus)) == AudioMix.MASTER_BUS,
		"positional ambience follows both ambience and master volume")
	_expect(positional != null
		and positional.global_position.is_equal_approx(Vector3(0.0, 0.0, -30.0)),
		"it sits on the node the package named, not at a guess")
	_expect(parent.get_node_or_null("falls-ambience_2") == null,
		"a node outside the prefix is not given a sound")
	var looping: AudioStreamWAV = (positional.stream as AudioStreamWAV
		if positional != null else null)
	_expect(looping != null and looping.loop_mode == AudioStreamWAV.LOOP_FORWARD,
		"ambience repeats rather than playing once and stopping")

	_expect(looping != null and looping.loop_end == roundi(looping.get_length() * looping.mix_rate),
		"compressed ambience loops over decoded frames, not encoded byte count")
	var stereo := AudioStreamWAV.new()
	stereo.format = AudioStreamWAV.FORMAT_16_BITS
	stereo.stereo = true
	stereo.mix_rate = 44100
	var stereo_pcm := PackedByteArray()
	stereo_pcm.resize(22050 * 4)
	stereo.data = stereo_pcm
	var stereo_loop := AmbientAudioBinder._looping(stereo) as AudioStreamWAV
	_expect(stereo_loop.loop_end == 22050,
		"stereo WAV loop length counts frames rather than individual channel samples")

	# A package that declares nothing, and one that names an unknown loop.
	var silent := WorldManifest.new()
	silent.data = {"environment": {"sky": {}}}
	var silent_parent := Node3D.new()
	root.add_child(silent_parent)
	_expect(AmbientAudioBinder.apply(silent, silent_parent, world, catalog) == 0
		and silent_parent.get_child_count() == 0,
		"a package that declares no ambience gets none")
	var unknown := WorldManifest.new()
	unknown.data = {"environment": {"ambientAudio": [
		{"id": "x", "loop": "not_in_the_catalog", "gain": 1.0}]}}
	_expect(AmbientAudioBinder.apply(unknown, silent_parent, world, catalog) == 0,
		"a loop this client has no sound for is skipped, not faked")

	# The shipped package, read from disk rather than hand-built.
	var shipped := WorldManifest.new()
	var file := FileAccess.open(
		"res://../eloria-assets/maps/four-gates/world.json", FileAccess.READ)
	if _expect(file != null, "the Four Gates manifest is readable"):
		var parsed: Variant = JSON.parse_string(file.get_as_text())
		shipped.data = parsed as Dictionary if parsed is Dictionary else {}
		var declared: Array = ((shipped.data.get("environment", {}) as Dictionary)
			.get("ambientAudio", []) as Array)
		_expect(declared.size() == 2,
			"the shipped package still declares its two ambiences")
		var shipped_parent := Node3D.new()
		root.add_child(shipped_parent)
		_expect(AmbientAudioBinder.apply(shipped, shipped_parent, world,
			catalog) >= 1,
			"the shipped declarations bind against a scene with its nodes")

	print("ambient audio tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

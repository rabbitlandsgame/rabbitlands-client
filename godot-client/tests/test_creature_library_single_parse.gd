extends SceneTree
## A creature names its own GLB as its animation library. The warm-up and the
## main-thread retarget take the clips from the scene GlbSceneCache already
## parsed instead of parsing the file a second time; the retargeted library must
## be exactly the one a separate parse produces. Cerberus also carries
## corrective blend-shape tracks.
const Warmup := preload("res://src/actors/actor_resource_warmup.gd")
const CREATURES: Array[String] = ["rabbit", "cerberus"]
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

## "" when both libraries hold the same clips, tracks and keys.
func library_difference(a: AnimationLibrary, b: AnimationLibrary) -> String:
	if a == null or b == null:
		return "missing library"
	if a.get_animation_list() != b.get_animation_list():
		return "clip lists differ"
	for clip: StringName in a.get_animation_list():
		var x := a.get_animation(clip)
		var y := b.get_animation(clip)
		if x.length != y.length or x.loop_mode != y.loop_mode or x.get_track_count() != y.get_track_count():
			return "%s header" % clip
		for track: int in x.get_track_count():
			if x.track_get_path(track) != y.track_get_path(track) or x.track_get_type(track) != y.track_get_type(track) \
					or x.track_get_interpolation_type(track) != y.track_get_interpolation_type(track) \
					or x.track_get_key_count(track) != y.track_get_key_count(track):
				return "%s track %d" % [clip, track]
			for key: int in x.track_get_key_count(track):
				if x.track_get_key_time(track, key) != y.track_get_key_time(track, key) \
						or x.track_get_key_value(track, key) != y.track_get_key_value(track, key):
					return "%s track %d key %d" % [clip, track, key]
	return ""

func detached_rig(packed: PackedScene) -> Node3D:
	var owner := Node3D.new()
	var model := packed.instantiate()
	model.name = "NativeModel"
	owner.add_child(model)
	return owner

func first_skeleton(owner: Node) -> Skeleton3D:
	return owner.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D

func check_creature(name: String, registry: Dictionary) -> void:
	var config: Dictionary = registry.models[name]
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var path := ProjectSettings.globalize_path(str(config.scene))
	var source_path := ProjectSettings.globalize_path(str(config.animationLibrary))
	var aliases: Dictionary = config.get("boneAliases", {})
	var resolver := AnimationResolver.new(animation)
	var result: Dictionary = Warmup._prepare(config, animation)
	var packed := result.get("scenes", {}).get(path) as PackedScene
	expect(NativeAnimationImporter.is_runtime_parse_of(packed, path, source_path),
		name + ": warm-up scene is the library's own runtime parse")
	var shared: Dictionary = result.get("library", {})
	# What the warm-up built before: the same rig, clips from a second parse.
	var owner := detached_rig(packed)
	var separate := NativeAnimationImporter._parse_library(source_path, false) as Node
	var expected := NativeAnimationImporter.prepare_detached(owner, separate, source_path,
		first_skeleton(owner), aliases, resolver.required_clips(), resolver.looping_clips)
	separate.free()
	owner.free()
	expect(not shared.is_empty() and shared.key == expected.key, name + ": library key unchanged")
	var built: Dictionary = shared.get("built", {})
	var difference := library_difference(built.get("library"), expected.built.library)
	expect(difference.is_empty(), name + ": shared-parse clips equal a separate parse " + difference)
	expect(built.get("clips") == expected.built.clips and built.get("errors") == expected.built.errors \
		and built.get("complete_defaults") == expected.built.complete_defaults \
		and built.get("default_tracks_removed") == expected.built.default_tracks_removed,
		name + ": clip list, errors and compaction unchanged")
	# Main-thread retarget on a cache miss: the source is an instance of the
	# cached scene, sharing its resources, not a second parse held for the session.
	GlbSceneCache.install_prepared(result.get("scenes", {}))
	var rig := detached_rig(GlbSceneCache.packed_scene(path))
	var imported := NativeAnimationImporter.import_library(rig, source_path, first_skeleton(rig), aliases,
		resolver.required_clips(), resolver.looping_clips)
	var source := NativeAnimationImporter._source_scene(source_path)
	var player := source.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer if source != null else null
	var probe := GlbSceneCache.runtime_parse(path).instantiate()
	var cached := probe.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	var clip: StringName = cached.get_animation_list()[0]
	expect(player != null and is_same(player.get_animation(clip), cached.get_animation(clip)),
		name + ": main-thread source shares the cached scene's animations")
	probe.free()
	var library := (imported.player as AnimationPlayer).get_animation_library("") if imported.player != null else null
	difference = library_difference(library, expected.built.library)
	expect(difference.is_empty() and imported.errors == expected.built.errors,
		name + ": main-thread retarget equals a separate parse " + difference)
	rig.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()

func run() -> void:
	var previous_mode := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	NativeAnimationImporter.GltfQuantization.ensure_registered()
	NativeAnimationImporter.VramTextures.ensure_registered()
	NativeAnimationImporter.MapMeshExtension.ensure_registered()
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	for name: String in CREATURES:
		expect(registry.models[name].scene == registry.models[name].animationLibrary,
			name + ": scene and animation library are one file")
		check_creature(name, registry)
	if previous_mode.is_empty():
		OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else:
		OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_mode)
	print("creature library single parse: ", failures, " failures")
	quit(failures)

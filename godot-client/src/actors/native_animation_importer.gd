class_name NativeAnimationImporter

extends RefCounted

const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const MapMeshExtension := preload("res://src/world/map_mesh_extension.gd")
const GltfAnimationFidelity := preload("res://src/actors/gltf_animation_fidelity.gd")
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const PreparedContent := preload("res://src/world/prepared_content.gd")
const PreparedLifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
## Retargets a native glTF animation library onto an actor's skeleton.
##
## The shared universal library ships 162 clips built from roughly 226 000
## keyframes. Rebuilding all of them for every actor - once through the glTF
## parser and once again key by key through GDScript - was by far the largest
## cost of spawning an actor, and it was paid again for every duplicate of the
## same model.
##
## Two changes remove that cost without altering a single frame of playback:
##
##   * only the clips the actor's action map can actually request are rebuilt,
##     which is 18 of the 162 for the current maps, and
##   * the finished AnimationLibrary is cached and shared by every actor using
##     the same source file, skeleton path and bone aliases, and the parsed
##     source file itself is kept, so a second rig never re-parses it.
##
## Animation resources are immutable during playback, so one library backing
## many AnimationPlayers is safe; per-actor playback state (current clip,
## speed_scale, seek position) lives on the player, not the library.
## Corrective blend-shape tracks are mapped to each actor's mesh nodes too;
## their defaults participate in RESET so attack and flight repairs survive
## retargeting without persisting into unrelated clips.

static var _libraries: Dictionary = {}
## The parsed library scenes, one per source file, kept for the session. A
## retarget used to parse the 11 MB file again for every rig it met and free
## the result. The parse now happens once - on a worker thread when `prewarm`
## had the chance - and every rig reads from it.
static var _sources: Dictionary = {}
static var _prewarming: Dictionary = {}

static func import_library(owner: Node, source_path: String,
		target_skeleton: Skeleton3D, bone_aliases := {},
		wanted_clips: PackedStringArray = PackedStringArray(),
		looping_clips: PackedStringArray = PackedStringArray()) -> Dictionary:
	var result := {"player": null, "clips": PackedStringArray(),
		"errors": PackedStringArray()}
	if ArchivedModelPolicy.is_retired_path(source_path):
		result["retired"] = true
		return result
	if target_skeleton == null:
		result.errors.append("animation retarget skeleton missing")
		return result
	var skeleton_path := String(owner.get_path_to(target_skeleton))
	# The rig itself is part of the key: two models can sit at the same node
	# path and still expose different bones, and a retargeted library is only
	# reusable by a skeleton with the same bones in the same order.
	var shape_defaults := _blend_shape_defaults(owner)
	var cache_key := _library_key(source_path, skeleton_path, target_skeleton,
		bone_aliases, wanted_clips, looping_clips, shape_defaults)
	var cached: Dictionary = _libraries.get(cache_key, {}) as Dictionary
	if cached.is_empty():
		cached = _build(owner, source_path, skeleton_path, target_skeleton, bone_aliases,
			wanted_clips, looping_clips, shape_defaults)
		_libraries[cache_key] = cached
	result.errors.append_array(cached.get("errors", PackedStringArray()))
	var library: AnimationLibrary = cached.get("library") as AnimationLibrary
	if library == null:
		return result
	var target_player := AnimationPlayer.new()
	# Complete player clips carry explicit defaults for omitted channels, so
	# normalized blending cannot inherit an idle's root yaw in the bow pose.
	# It also avoids a deterministic mix's transient zero-total weight when a
	# large first step consumes the entire crossfade (a visible bind-pose flash).
	# Sparse corrective creature libraries retain their RESET-based policy.
	target_player.deterministic = not bool(cached.get("complete_defaults", false))
	target_player.name = "NativeAnimationPlayer"
	owner.add_child(target_player)
	target_player.add_animation_library("", library)
	result.player = target_player
	result.clips = cached.get("clips", PackedStringArray())
	return result

static func _library_key(path: String, skeleton_path: String, skeleton: Skeleton3D,
		aliases: Dictionary, wanted: PackedStringArray, loops: PackedStringArray,
		defaults: Dictionary) -> String:
	return "%s|%s|%s|%s|%s|%s|%s" % [path, skeleton_path,
		_skeleton_signature(skeleton), JSON.stringify(aliases),
		",".join(wanted), ",".join(loops), JSON.stringify(defaults)]

## Worker-owned detached nodes only. Publication into the session cache is
## separate and always performed on main; no live actor crosses the boundary.
static func prepare_detached(owner: Node, source: Node, path: String,
		skeleton: Skeleton3D, aliases: Dictionary, wanted: PackedStringArray,
		loops: PackedStringArray) -> Dictionary:
	var skeleton_path := String(owner.get_path_to(skeleton))
	var defaults := _blend_shape_defaults(owner)
	return {"key": _library_key(path, skeleton_path, skeleton, aliases, wanted, loops, defaults),
		"built": _build(owner, path, skeleton_path, skeleton, aliases, wanted, loops, defaults, source)}

static func install_prepared(record: Dictionary) -> void:
	if not record.is_empty() and not _libraries.has(record.key):
		_libraries[record.key] = record.built

## Drops every cached library and parsed source. Call when leaving a session.
static func clear() -> void:
	_libraries.clear()
	for path_value: Variant in _prewarming:
		var parsed: Variant = (_prewarming[path_value] as Thread).wait_to_finish()
		if parsed is Node:
			(parsed as Node).free()
	_prewarming.clear()
	for scene_value: Variant in _sources.values():
		if is_instance_valid(scene_value):
			(scene_value as Node).free()
	_sources.clear()

## Parses `source_path` on a worker thread, so the first actor to need it
## finds the scene ready instead of paying for the parse on the main thread
## the moment it arrives. Nothing is parsed twice: a path already parsed, or
## already parsing, is left alone.
##
## The library must name no image by URI that a package imports (the equipment
## textures): GLTFDocument reads such a texture back through the
## RenderingServer, which from a worker waits for the main thread, and
## `_source_scene` joins this worker from the main thread - a deadlock. No
## library names one today; the packaging tests check every animationLibrary
## in models.json.
static func prewarm(source_path: String) -> bool:
	# These dictionaries and worker ownership already belong to main. Reject
	# worker-first API use before reading or changing any of them.
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return false
	if ArchivedModelPolicy.is_retired_path(source_path) or source_path.is_empty():
		return false
	# Standalone users may not have Main. Register the complete runtime set
	# before starting this worker, including map extensions that otherwise
	# could be registered later while this animation parse iterates the list.
	if not GltfQuantization.ensure_registered() or not VramTextures.ensure_registered() \
			or not MapMeshExtension.ensure_registered():
		return false
	if _sources.has(source_path) or _prewarming.has(source_path):
		return true
	var thread := Thread.new()
	if thread.start(_parse_library.bind(source_path)) != OK:
		return false
	_prewarming[source_path] = thread
	return true

static func is_prewarming(source_path: String) -> bool:
	return _prewarming.has(source_path)

static func has_source(source_path: String) -> bool:
	return is_instance_valid(_sources.get(source_path))

## The parsed scene for `source_path`: the prewarm's result, waited for if it
## is still running, or a parse on the spot. Owned here; callers must not
## free it.
static func _source_scene(source_path: String) -> Node:
	var held: Variant = _sources.get(source_path)
	if is_instance_valid(held):
		return held as Node
	var scene: Node = null
	if _prewarming.has(source_path):
		var thread: Thread = _prewarming[source_path] as Thread
		_prewarming.erase(source_path)
		var completion: Variant = thread.wait_to_finish()
		scene = _publish_source(completion)
	if scene == null:
		scene = _publish_source(_parse_library(source_path))
	if scene == null and PreparedContent.selected_mode() == "auto":
		scene = _publish_source(_parse_library(source_path, false))
	if scene != null:
		_sources[source_path] = scene
	return scene

## The glTF parse itself. Safe off the main thread: it builds resources and
## nodes that belong to no tree.
static func _publish_source(completion: Variant) -> Node:
	if completion is Dictionary:
		var entry: Dictionary = completion.get("entry", {})
		var source := PreparedContent.source_path(str(entry.get("source", "")))
		if source.is_empty():
			return null
		var verified := PreparedContent.acquire("scene", source, CreaturePayload.source_sha256(source),
			PreparedContent.scene_texture_token(source))
		return PreparedLifecycle.instantiate(verified)
	return completion as Node if completion is Node else null

static func _parse_library(path: String, allow_prepared := true) -> Variant:
	if not GltfQuantization.ensure_registered():
		push_error("animation glTF parse requires main-thread extension initialization")
		return null
	if allow_prepared and PreparedContent.selected_mode() != "raw":
		var record := PreparedContent.acquire("scene", path, CreaturePayload.source_sha256(path),
			PreparedContent.scene_texture_token(path))
		if str(record.status) == "hit":
			return record # Worker completion contains immutable resources, no Nodes.
		if str(record.status) == "reject":
			return null

	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if CreaturePayload.append(document, path, state) != OK:
		return null
	return document.generate_scene(state, GltfAnimationFidelity.bake_fps(state))

static func _skeleton_signature(skeleton: Skeleton3D) -> String:
	var names := PackedStringArray()
	for bone: int in skeleton.get_bone_count():
		names.append(skeleton.get_bone_name(bone) + str(skeleton.get_bone_rest(bone)))
	return "%d:%d" % [names.size(), hash(names)]

static func cached_library_count() -> int:
	return _libraries.size()

## Main-thread plain-data snapshot; does not join prewarm workers or traverse
## retained scenes/animations. These are session-lifetime strong caches.
static func retention_snapshot() -> Dictionary:
	var removed := 0
	for entry: Dictionary in _libraries.values():
		removed += int(entry.get("default_tracks_removed", 0))
	return {"strong_library_entries": _libraries.size(),
		"default_only_shape_tracks_removed": removed,
		"strong_source_scenes": _sources.size(), "prewarming_sources": _prewarming.size(),
		"bytes_estimate_available": false, "lifetime": "session"}

static func _blend_shape_defaults(owner: Node) -> Dictionary:
	var defaults := {}
	for node: Node in owner.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh is not ArrayMesh:
			continue
		for index: int in mesh_node.mesh.get_blend_shape_count():
			var path := "%s:%s" % [owner.get_path_to(mesh_node), mesh_node.mesh.get_blend_shape_name(index)]
			defaults[path] = mesh_node.get_blend_shape_value(index)
	return defaults

static func _blend_shape_path(owner: Node, source_player: AnimationPlayer,
		source_path: NodePath, target_skeleton: Skeleton3D) -> NodePath:
	# Match the mesh by its path relative to its own rig, never by a global
	# name search: two actors can have identical mesh and corrective names.
	var source_root := source_player.get_node(source_player.root_node)
	var source_mesh := source_root.get_node_or_null(NodePath(source_path.get_concatenated_names())) as MeshInstance3D
	if source_mesh == null or source_mesh.mesh == null:
		return NodePath()
	var source_skeleton := source_mesh.get_node_or_null(source_mesh.skeleton) as Skeleton3D
	if source_skeleton == null:
		return NodePath()
	var target_mesh := target_skeleton.get_node_or_null(source_skeleton.get_path_to(source_mesh)) as MeshInstance3D
	if target_mesh == null or target_mesh.mesh == null:
		return NodePath()
	var shape := source_path.get_concatenated_subnames()
	if target_mesh.find_blend_shape_by_name(shape) < 0:
		return NodePath()
	return NodePath("%s:%s" % [owner.get_path_to(target_mesh), shape])

static func _build(owner: Node, source_path: String, skeleton_path: String,
		target_skeleton: Skeleton3D, bone_aliases: Dictionary,
		wanted_clips: PackedStringArray,
		looping_clips: PackedStringArray, shape_defaults: Dictionary,
		prepared_source: Node = null, compact_rest_tracks := true) -> Dictionary:
	var built := {"library": null, "clips": PackedStringArray(),
		"errors": PackedStringArray()}
	var source_scene := prepared_source if prepared_source != null else _source_scene(source_path)
	if source_scene == null:
		built.errors.append("animation library load failed: " + source_path)
		return built
	var source_player := _find_player(source_scene)
	if source_player == null:
		built.errors.append("animation library has no AnimationPlayer")
		return built
	var library := AnimationLibrary.new()
	# An empty request means "everything the file offers"; the actor path always
	# passes the clips its action map can reach.
	var filter_clips := not wanted_clips.is_empty()
	var source_clips := CombatAnimationLibrary.source_clips(wanted_clips)
	for clip_name in source_player.get_animation_list():
		if filter_clips and not source_clips.has(String(clip_name)):
			continue
		var source := source_player.get_animation(clip_name)
		var target := Animation.new()
		target.length = source.length
		# glTF cannot state that a clip loops, so every runtime-parsed clip
		# arrives one-shot; the action map is where the cycles are declared.
		target.loop_mode = Animation.LOOP_LINEAR \
			if looping_clips.has(String(clip_name)) else source.loop_mode
		for source_track in source.get_track_count():
			var track_path := NodePath()
			if source.track_get_type(source_track) == Animation.TYPE_BLEND_SHAPE:
				track_path = _blend_shape_path(owner, source_player,
					source.track_get_path(source_track), target_skeleton)
				if track_path.is_empty():
					built.errors.append("corrective mesh track has no target: " + str(source.track_get_path(source_track)))
					continue
			else:
				var source_bone := _track_bone(source.track_get_path(source_track))
				var bone := str(bone_aliases.get(source_bone, source_bone))
				if bone.is_empty() or target_skeleton.find_bone(bone) < 0:
					continue
				track_path = NodePath(skeleton_path + ":" + bone)
			# Copy immutable track data in the engine. Reading and reinserting
			# every baked key through script made first-use retargeting hundreds
			# of milliseconds even when the source scene was already resident.
			var target_track := target.get_track_count()
			source.copy_track(source_track, target)
			target.track_set_path(target_track, track_path)
		if target.get_track_count() > 0:
			library.add_animation(clip_name, target)
			built.clips.append(String(clip_name))
	CombatAnimationLibrary.install(library, wanted_clips)
	# A runtime glTF library has no RESET animation. Without a stable blend
	# reference, the first played idle's turned root becomes the rotation base
	# for subsequent crossfades (including a bow aimed 23 degrees off target).
	var reset := Animation.new()
	reset.length = 0.0
	for bone: int in target_skeleton.get_bone_count():
		var rest := target_skeleton.get_bone_rest(bone)
		for type: Animation.TrackType in [Animation.TYPE_POSITION_3D, Animation.TYPE_ROTATION_3D, Animation.TYPE_SCALE_3D]:
			var track := reset.add_track(type)
			reset.track_set_path(track, NodePath(skeleton_path + ":" + target_skeleton.get_bone_name(bone)))
			var value: Variant = rest.origin
			if type == Animation.TYPE_ROTATION_3D:
				value = rest.basis.get_rotation_quaternion()
			elif type == Animation.TYPE_SCALE_3D:
				value = rest.basis.get_scale()
			reset.track_insert_key(track, 0.0, value)
	# Correctives must return to their authored default when switching to a
	# clip that omits them. Bone-only RESET left the previous attack or wing
	# correction applied indefinitely after crossfading back to idle.
	for path: String in shape_defaults:
		var track := reset.add_track(Animation.TYPE_BLEND_SHAPE)
		reset.track_set_path(track, NodePath(path))
		reset.track_insert_key(track, 0.0, shape_defaults[path])
	if library.has_animation(&"RESET"):
		library.remove_animation(&"RESET")
	library.add_animation(&"RESET", reset)
	var complete_defaults := source_path.get_file() == "Universal_Animation_Library.glb"
	if complete_defaults:
		_complete_default_channels(library, reset)
	built["complete_defaults"] = complete_defaults
	# Dense corrective libraries can repeat an unchanged default in hundreds
	# of blend-shape tracks. Deterministic playback already supplies that exact
	# value from RESET when a clip omits the track. Keep RESET intact, including
	# every corrective, and retain every channel with any non-default key.
	built["default_tracks_removed"] = _compact_default_shapes(library, shape_defaults) \
		if compact_rest_tracks and not complete_defaults else 0
	built.clips = library.get_animation_list()
	built.library = library
	if built.clips.is_empty():
		built.errors.append("no animation tracks matched the target skeleton")
	return built

static func _complete_default_channels(library: AnimationLibrary, reset: Animation) -> void:
	for name: StringName in library.get_animation_list():
		if name == &"RESET": continue
		var animation := library.get_animation(name)
		var existing := {}
		for track: int in animation.get_track_count():
			existing["%s|%s" % [animation.track_get_path(track), animation.track_get_type(track)]] = true
		for track: int in reset.get_track_count():
			var key := "%s|%s" % [reset.track_get_path(track), reset.track_get_type(track)]
			if not existing.has(key): reset.copy_track(track, animation)

static func _compact_default_shapes(library: AnimationLibrary, defaults: Dictionary) -> int:
	if defaults.is_empty():
		return 0
	var removed := 0
	for clip: StringName in library.get_animation_list():
		if clip == &"RESET":
			continue
		var animation := library.get_animation(clip)
		for track: int in range(animation.get_track_count() - 1, -1, -1):
			if animation.track_get_type(track) != Animation.TYPE_BLEND_SHAPE:
				continue
			var path := str(animation.track_get_path(track))
			if not defaults.has(path) or animation.track_get_key_count(track) == 0:
				continue
			var constant := true
			for key: int in animation.track_get_key_count(track):
				if animation.track_get_key_value(track, key) != defaults[path]:
					constant = false
					break
			if constant:
				animation.remove_track(track)
				removed += 1
	return removed

static func _find_player(root: Node) -> AnimationPlayer:
	if root is AnimationPlayer:
		return root
	for node in root.find_children("*", "AnimationPlayer", true, false):
		return node as AnimationPlayer
	return null

static func _track_bone(path: NodePath) -> String:
	var subnames := path.get_concatenated_subnames()
	if not subnames.is_empty():
		return subnames.get_slice(":", subnames.get_slice_count(":") - 1)
	var node_path := String(path).get_slice(":", 0)
	return node_path.get_file()

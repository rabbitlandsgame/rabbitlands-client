extends RefCounted
## Low actor tier, hand detail (LAT-L1; owner decision 2026-11-02, Low and the
## Performance preset only: "no finger bones or tracks beyond close range").
##
## A cached "crowd" copy of a humanoid's main animation library with every
## finger bone track removed. Main swaps it onto remote humanoids beyond close
## range at Low and back when they come near; Medium and High never ask, so
## they play exactly what they played before.
##
## Why a library per body. Actors play a plain AnimationPlayer and animations
## are shared, immutable resources (one library per rig signature in
## NativeAnimationImporter), so disabling a track would disable it for the
## local player and near bodies too, and Skeleton3D has no per-instance "do not
## pose this bone". The Universal runtime clip carries 195 tracks (complete
## defaults for 65 bones); without the 40 finger bones' 120 channels it carries
## 75, and the mixer's cost per update falls by about 60 % (LAT-L1 bench,
## tests/integration/benchmark_crowd_animation_variant.gd: 15 -> 6 us per
## advance on 48 orun_male rigs, 20 -> 8 us on 16 configured luminous actors).
##
## What stays exact. Every clip keeps its name, length, loop mode, step and
## markers. Blend-shape, non-bone and every non-finger bone track is copied in
## the engine (Animation.copy_track), so body poses match the full library to
## float precision; RESET is filtered the same way; a clip without a finger
## track is shared, not copied. Variants are cached per source library and rig
## (CACHE_LIMIT, FIFO) with the source strongly referenced, the
## HumanLocomotionPolish pattern, so a freed source's instance id is never
## reused as another library's key.
##
## Fingers are held, not reset. The variant never writes a finger bone and the
## player is non-deterministic, so the fingers keep the last pose the full
## library wrote (a grip stays a grip). The rig's rest fingers differ from the
## animated ones by up to 180 degrees, so a body whose fingers were never
## written (built far away, or never stepped) gets the hold: the full
## library's idle finger rotations at t=0.
##
## State lives on the AnimationPlayer (FULL_META, VARIANT_META), so the actor
## needs only thin calls. A swap keeps the assigned clip, its position, the
## player's speed_scale and whether it was playing. Its cost is the mixer's
## track-cache rebuild over every clip of the player, so a body built at Low
## should take the variant before its first play (no extra rebuild) rather
## than swap later. The per-actor restart alias
## library (play_action's "action_restarts") holds clips of the outgoing
## library; it is dropped with it and rebuilt lazily by the next restart,
## except while a stopped player's assigned clip is one of its aliases.
##
## Refusals (the player keeps, or returns to, its full library):
##   * a pinned body - the actor's call: local, preview, mounted, cinematic or
##     charge-leaping; mount reins, the rider seat and the cinematic clips read
##     or write finger poses;
##   * a deterministic player (absent tracks would blend to rest);
##   * a player carrying a library this module does not manage (cinematic,
##     campaign rescue);
##   * a rig with fewer than MIN_FINGER_BONES finger bones (creatures, mounts);
##   * unless pinned, a body inside its action crossfade; the caller retries on
##     a later sweep.
##
## Library consumers that must see the full library read full_library():
## SpellAnimationLibrary.install(..., source_library) and the mounted visuals
## (the actor restores full hands before it builds one). HumanLocomotionPolish
## installs at build time, before any swap.

const FULL_META := &"crowd_hands_full_library"
const VARIANT_META := &"crowd_hands_variant"
const RESTART_LIBRARY := &"action_restarts"
const MANAGED_LIBRARIES: Array[StringName] = [&"", &"action_restarts", &"spell_variants"]
const MIN_FINGER_BONES := 30
const CACHE_LIMIT := 16
## Main's drain budget. On configured luminous actors (their 88-clip library) a
## swap measured 0.24 ms to the variant and 0.5-1.1 ms back to full (medians of
## two loaded runs, max 0.8 / 2.1 ms, laptop, not pinned): the mixer rebuilds
## its track caches over every clip. The design's 0.04-0.12 ms came from a
## 6-clip library. One per frame is still 30 swaps a second under the 30 FPS
## cap, more than a crowd milling at the 12-15 m band asks for. Deriving a
## variant (about 20-35 ms per actor library, once per session) belongs at
## build time: prepare().
const SWAPS_PER_FRAME := 1
const HOLD_CLIPS: Array[StringName] = [&"Idle_A", &"Idle_Subtle", &"Idle"]
const FINGER_PATTERN := "^(thumb|index|middle|ring|pinky)_\\d+(_leaf)?_[lr]$"

static var _variants: Dictionary = {}
static var _finger_regex: RegEx

# --- Variant -----------------------------------------------------------------

## {library, finger_bones: PackedInt32Array, hold: PackedFloat32Array (x, y, z,
## w per finger bone)}. For a rig without hands `library` is `source` itself
## and the arrays are empty. The returned record is shared: read it only.
static func derive(source: AnimationLibrary, skeleton: Skeleton3D) -> Dictionary:
	var unchanged := {"library": source, "finger_bones": PackedInt32Array(),
		"hold": PackedFloat32Array()}
	if source == null or skeleton == null:
		return unchanged
	var key := "%d|%d" % [source.get_instance_id(), _rig_key(skeleton)]
	if _variants.has(key):
		return _variants[key].record
	var bones := finger_bones(skeleton)
	if bones.size() < MIN_FINGER_BONES:
		return unchanged
	var names := {}
	for bone: int in bones:
		names[skeleton.get_bone_name(bone)] = true
	var paths := {}
	var library := AnimationLibrary.new()
	for name: StringName in source.get_animation_list():
		library.add_animation(name, _without_fingers(source.get_animation(name), names, paths))
	var record := {"library": library, "finger_bones": bones,
		"hold": _hold(source, skeleton, bones)}
	if _variants.size() >= CACHE_LIMIT:
		_variants.erase(_variants.keys()[0])
	_variants[key] = {"source": source, "record": record}
	return record

static func is_finger_bone(bone_name: String) -> bool:
	if _finger_regex == null:
		_finger_regex = RegEx.create_from_string(FINGER_PATTERN)
	return _finger_regex.search(bone_name) != null

static func finger_bones(skeleton: Skeleton3D) -> PackedInt32Array:
	var bones := PackedInt32Array()
	if skeleton == null:
		return bones
	for bone: int in skeleton.get_bone_count():
		if is_finger_bone(skeleton.get_bone_name(bone)):
			bones.append(bone)
	return bones

static func clear() -> void:
	_variants.clear()

static func cached_count() -> int:
	return _variants.size()

# --- Per-player hand detail ----------------------------------------------------

## Shows full or crowd hands on `player`. Returns true only when the library
## actually changed, which is what Main budgets (SWAPS_PER_FRAME). A pinned
## body is always restored to full at once. A request that is refused or
## deferred returns false; hand_detail_full() then still reports the old state.
## `crossfade_seconds` is the actor's action_crossfade_seconds: a body that
## started a crossfaded clip less than that ago is left for a later sweep
## (approximate: read from the clip position since its start).
static func set_hand_detail(player: AnimationPlayer, skeleton: Skeleton3D, full: bool,
		pinned := false, crossfade_seconds := 0.0) -> bool:
	if player == null:
		return false
	var crowd := player.has_meta(FULL_META)
	if full or pinned:
		if not crowd or (not pinned and crossfading(player, crossfade_seconds)):
			return false
		return restore_full(player)
	if crowd or not accepts_variant(player) or crossfading(player, crossfade_seconds):
		return false
	var source := player.get_animation_library(&"")
	var record := _record(player, source, skeleton)
	if record.library == source:
		return false
	var bones: PackedInt32Array = record.finger_bones
	if fingers_unposed(skeleton, bones):
		write_hold(skeleton, record)
	_install(player, record.library)
	player.set_meta(FULL_META, source)
	return true

## Finds or derives this player's variant without swapping. Deriving is a
## one-off per library and rig (a few ms for an actor library, once per
## session); calling this while a body is built keeps it out of Main's
## per-frame swap budget. True when the rig gets a variant.
static func prepare(player: AnimationPlayer, skeleton: Skeleton3D) -> bool:
	if not accepts_variant(player):
		return false
	var source := full_library(player)
	return _record(player, source, skeleton).library != source

## Puts the full library back at once (mounting, cinematics, becoming local or
## leaving Low). Returns true when the library changed.
static func restore_full(player: AnimationPlayer) -> bool:
	if player == null or not player.has_meta(FULL_META):
		return false
	var full := player.get_meta(FULL_META) as AnimationLibrary
	player.remove_meta(FULL_META)
	if full == null:
		return false
	_install(player, full)
	return true

static func hand_detail_full(player: AnimationPlayer) -> bool:
	return player == null or not player.has_meta(FULL_META)

## The library with finger tracks: the one held aside while the crowd variant
## plays, otherwise the player's own main library.
static func full_library(player: AnimationPlayer) -> AnimationLibrary:
	if player == null:
		return null
	if player.has_meta(FULL_META):
		return player.get_meta(FULL_META) as AnimationLibrary
	return player.get_animation_library(&"") if player.has_animation_library(&"") else null

## A clip as the full library has it, finger tracks included, for code that
## samples finger poses from the player's clips (WeaponCarryPose's fist). On a
## full-hands player this is exactly player.get_animation(name).
static func full_animation(player: AnimationPlayer, name: StringName) -> Animation:
	if player == null:
		return null
	if player.has_meta(FULL_META):
		var library := player.get_meta(FULL_META) as AnimationLibrary
		if library != null and library.has_animation(name):
			return library.get_animation(name)
	return player.get_animation(name) if player.has_animation(name) else null

## Whether this player could take the crowd variant at all (rig aside).
static func accepts_variant(player: AnimationPlayer) -> bool:
	if player == null or player.deterministic or not player.has_animation_library(&""):
		return false
	for name: StringName in player.get_animation_library_list():
		if not MANAGED_LIBRARIES.has(name):
			return false
	return true

static func crossfading(player: AnimationPlayer, crossfade_seconds: float) -> bool:
	return crossfade_seconds > 0.0 and player.is_playing() \
		and player.current_animation_position < crossfade_seconds * absf(player.speed_scale)

## True when no finger has left its rest rotation: nothing ever wrote them.
static func fingers_unposed(skeleton: Skeleton3D, bones: PackedInt32Array) -> bool:
	if skeleton == null:
		return false
	for bone: int in bones:
		var rest := skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()
		if not skeleton.get_bone_pose_rotation(bone).is_equal_approx(rest):
			return false
	return true

static func write_hold(skeleton: Skeleton3D, record: Dictionary) -> void:
	var bones: PackedInt32Array = record.get("finger_bones", PackedInt32Array())
	var hold: PackedFloat32Array = record.get("hold", PackedFloat32Array())
	if skeleton == null or hold.size() != bones.size() * 4:
		return
	for index: int in bones.size():
		var at := index * 4
		skeleton.set_bone_pose_rotation(bones[index],
			Quaternion(hold[at], hold[at + 1], hold[at + 2], hold[at + 3]))

# --- Main's gate decisions (pure) ----------------------------------------------

## Hysteresis on the camera distance: full hands nearer than `detail_metres`,
## kept until farther than `release_metres`. INF detail = always full.
static func want_full(camera_distance_squared: float, currently_full: bool,
		detail_metres: float, release_metres: float) -> bool:
	if is_inf(detail_metres):
		return true
	return camera_distance_squared < detail_metres * detail_metres \
		or (currently_full and camera_distance_squared < release_metres * release_metres)

## Drain order for queued swaps {"full": bool, "d2": float}: to-full first,
## then nearest first.
static func swap_before(first: Dictionary, second: Dictionary) -> bool:
	var first_full := bool(first.get("full", false))
	if first_full != bool(second.get("full", false)):
		return first_full
	return float(first.get("d2", 0.0)) < float(second.get("d2", 0.0))

# --- Internals -------------------------------------------------------------------

static func _record(player: AnimationPlayer, source: AnimationLibrary, skeleton: Skeleton3D) -> Dictionary:
	if player.has_meta(VARIANT_META):
		var held: Dictionary = player.get_meta(VARIANT_META)
		if held.get("source") == source:
			return held.record
	var record := derive(source, skeleton)
	player.set_meta(VARIANT_META, {"source": source, "record": record})
	return record

## Swaps library "" keeping the assigned clip, its position and play state.
## stop(true) first: it keeps the pose and clears the playback and blend
## references into the outgoing library before that library is removed.
## A playing restart alias continues as its base clip and the alias library
## goes. A stopped (or finished) player whose assigned clip is an alias keeps
## the alias library: removing it would leave assigned_animation naming a clip
## that no longer exists (an engine error on the next swap or seek).
static func _install(player: AnimationPlayer, library: AnimationLibrary) -> void:
	var playing := player.is_playing()
	var clip: StringName = player.assigned_animation
	var position := player.current_animation_position if playing else 0.0
	var keep_restarts := false
	if str(clip).begins_with(str(RESTART_LIBRARY) + "/"):
		var base: StringName = _restart_base(player, clip) if playing else &""
		keep_restarts = base == &""
		if not keep_restarts:
			clip = base
	player.stop(true)
	if not keep_restarts and player.has_animation_library(RESTART_LIBRARY):
		player.remove_animation_library(RESTART_LIBRARY)
	player.remove_animation_library(&"")
	player.add_animation_library(&"", library)
	if playing and clip != &"" and player.has_animation(clip):
		player.play(clip, 0.0)
		player.seek(position, true)

## The main-library name of the clip a restart alias plays.
static func _restart_base(player: AnimationPlayer, alias: StringName) -> StringName:
	if not player.has_animation(alias):
		return &""
	var animation := player.get_animation(alias)
	var library := player.get_animation_library(&"")
	for name: StringName in library.get_animation_list():
		if library.get_animation(name) == animation:
			return name
	return &""

static func _rig_key(skeleton: Skeleton3D) -> int:
	return hash([skeleton.get_bone_count(), skeleton.get_concatenated_bone_names()])

static func _is_bone_track(animation: Animation, track: int) -> bool:
	var type := animation.track_get_type(track)
	return type == Animation.TYPE_ROTATION_3D or type == Animation.TYPE_POSITION_3D \
		or type == Animation.TYPE_SCALE_3D

## `paths` caches, per track path met in this library, whether it names a
## finger bone: every clip repeats the same few hundred paths, so the string
## test runs once per path rather than once per track.
static func _without_fingers(source: Animation, fingers: Dictionary, paths: Dictionary) -> Animation:
	var count := source.get_track_count()
	var kept := PackedInt32Array()
	for track: int in count:
		var path := source.track_get_path(track)
		var finger: Variant = paths.get(path)
		if finger == null:
			finger = fingers.has(str(path.get_concatenated_subnames()))
			paths[path] = finger
		if not finger or not _is_bone_track(source, track):
			kept.append(track)
	if kept.size() == count:
		return source
	var result := Animation.new()
	result.length = source.length
	result.loop_mode = source.loop_mode
	result.step = source.step
	for track: int in kept:
		source.copy_track(track, result)
	for marker: StringName in source.get_marker_names():
		result.add_marker(marker, source.get_marker_time(marker))
		result.set_marker_color(marker, source.get_marker_color(marker))
	return result

## The idle grip at t=0: the first of HOLD_CLIPS, else the first looping clip.
## A finger without a track there takes RESET's value, else its rest.
static func _hold(source: AnimationLibrary, skeleton: Skeleton3D, bones: PackedInt32Array) -> PackedFloat32Array:
	var clip := _hold_clip(source)
	var reset: Animation = source.get_animation(&"RESET") if source.has_animation(&"RESET") else null
	var from_clip := _rotation_tracks(clip)
	var from_reset := _rotation_tracks(reset)
	var hold := PackedFloat32Array()
	for bone: int in bones:
		var name := skeleton.get_bone_name(bone)
		var rotation := skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()
		if from_clip.has(name):
			rotation = clip.rotation_track_interpolate(int(from_clip[name]), 0.0)
		elif from_reset.has(name):
			rotation = reset.rotation_track_interpolate(int(from_reset[name]), 0.0)
		rotation = rotation.normalized()
		hold.append_array(PackedFloat32Array([rotation.x, rotation.y, rotation.z, rotation.w]))
	return hold

static func _hold_clip(source: AnimationLibrary) -> Animation:
	for name: StringName in HOLD_CLIPS:
		if source.has_animation(name):
			return source.get_animation(name)
	for name: StringName in source.get_animation_list():
		if name != &"RESET" and source.get_animation(name).loop_mode != Animation.LOOP_NONE:
			return source.get_animation(name)
	return null

static func _rotation_tracks(animation: Animation) -> Dictionary:
	var tracks := {}
	if animation == null:
		return tracks
	for track: int in animation.get_track_count():
		if animation.track_get_type(track) == Animation.TYPE_ROTATION_3D:
			tracks[str(animation.track_get_path(track).get_concatenated_subnames())] = track
	return tracks

extends SceneTree
## Compare the current Swan against the unmodified runtime retarget, including
## all corrective values, off-grid samples, RESET and real crossfades.
var failures := 0
func _init() -> void: run.call_deferred()
func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
func owner_for(path: String) -> Node3D:
	var owner := Node3D.new()
	var model := GlbSceneCache.instantiate(path)
	model.name = "NativeModel"
	owner.add_child(model)
	root.add_child(owner)
	for player: AnimationPlayer in model.find_children("*", "AnimationPlayer", true, false):
		player.active = false
	return owner
func mismatch(a: Node3D, b: Node3D) -> float:
	var error := 0.0
	var sk_a := a.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var sk_b := b.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	for bone: int in sk_a.get_bone_count():
		var pa := sk_a.get_bone_pose(bone)
		var pb := sk_b.get_bone_pose(bone)
		error = maxf(error, pa.origin.distance_to(pb.origin))
		for axis: int in 3: error = maxf(error, pa.basis[axis].distance_to(pb.basis[axis]))
	for mesh: MeshInstance3D in a.find_children("*", "MeshInstance3D", true, false):
		var other := b.get_node(a.get_path_to(mesh)) as MeshInstance3D
		for shape: int in mesh.mesh.get_blend_shape_count():
			error = maxf(error, absf(mesh.get_blend_shape_value(shape) - other.get_blend_shape_value(shape)))
	return error
func run() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var config: Dictionary = registry.models.swan
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var resolver := AnimationResolver.new(mapping)
	var reference := owner_for(config.scene)
	var actual := owner_for(config.scene)
	var skeleton := reference.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var source_path := ProjectSettings.globalize_path(config.animationLibrary)
	var original := NativeAnimationImporter._build(reference, source_path,
		str(reference.get_path_to(skeleton)), skeleton, {}, resolver.required_clips(),
		resolver.looping_clips, NativeAnimationImporter._blend_shape_defaults(reference), null, false)
	var actual_sk := actual.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var compact := NativeAnimationImporter._build(actual, source_path,
		str(actual.get_path_to(actual_sk)), actual_sk, {}, resolver.required_clips(),
		resolver.looping_clips, NativeAnimationImporter._blend_shape_defaults(actual))
	expect(original.errors.is_empty() and compact.errors.is_empty(), "both actual retargets build without errors")
	expect(int(compact.default_tracks_removed) > 0, "actual dense Swan contains removable default-only tracks")
	var players: Array[AnimationPlayer] = []
	for pair: Array in [[reference, original.library], [actual, compact.library]]:
		var player := AnimationPlayer.new()
		pair[0].add_child(player)
		player.deterministic = true
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		player.add_animation_library("", pair[1])
		players.append(player)
	expect(original.library.get_animation_list() == compact.library.get_animation_list(), "all clips remain available")
	expect(original.library.get_animation("RESET").get_track_count() == compact.library.get_animation("RESET").get_track_count(), "RESET retains every track")
	var maximum_error := 0.0
	for clip: StringName in original.library.get_animation_list():
		for fraction: float in [0.0, .1337, .393, .7271, .999]:
			for player: AnimationPlayer in players:
				player.play("RESET", 0.0)
				player.seek(0.0, true)
				player.play(clip, 0.0)
				player.seek(player.get_animation(clip).length * fraction, true)
			maximum_error = maxf(maximum_error, mismatch(reference, actual))
		# Start from an attack, then compare the transition with missing tracks.
		for player: AnimationPlayer in players:
			player.play("Sword_Attack", 0.0)
			player.seek(.63, true)
			player.play(clip, .25)
			player.advance(.113)
		maximum_error = maxf(maximum_error, mismatch(reference, actual))
	expect(maximum_error < 0.000001, "all bone poses and corrective values match through samples and crossfades: %s" % maximum_error)
	print("corrective compaction removed=", compact.default_tracks_removed, " max_error=", maximum_error, " failures=", failures)
	reference.free()
	actual.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(failures)

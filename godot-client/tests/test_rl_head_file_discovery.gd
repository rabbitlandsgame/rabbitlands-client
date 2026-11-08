extends SceneTree
## Resource admission discovers names before lazy archives are extracted.
## None of these checks opens a GLB as a scene or changes a rendered face.
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
const Portrait := preload("res://src/actors/rl_head/rl_head_portrait_map.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	var documents := Library._documents.size()
	var scenes := GlbSceneCache._scenes.size()
	var face := RLHeadAppearance.new()
	face.sex = "__rl_discovery_missing_head"
	face.hair = "__rl_discovery_missing_hair"
	face.beard = "__rl_discovery_missing_beard"
	var potential := PackedStringArray([Library.head_path(face.sex),
		Library.hair_path(face.hair,face.sex),Library.beard_path(face.beard)])
	expect(Library.face_paths(face).is_empty(), "ordinary rendering still excludes files that are absent")
	expect(Library.face_paths(face,false,false) == potential,
		"admission returns deterministic head, hair and beard paths before extraction")
	expect(Library.face_paths(face,true,false) == PackedStringArray([potential[1]]),
		"hair-only admission never requests a head or beard")
	expect(Library.face_paths(null,false,false).is_empty(), "an absent face has no potential resources")
	face.hair = "legacy:parted"
	face.beard = RLHeadAppearance.STUBBLE
	expect(Library.face_paths(face,false,false) == PackedStringArray([potential[0]]),
		"painted stubble and legacy hair never invent RL modules")
	var folder := Library.HAIR_DIR
	var names := Library._glb_names_from_sources(folder,PackedStringArray([
		folder+"zeta.glb",folder+"alpha.GLB",folder+"zeta.glb",folder+"nested/hidden.glb",
		folder+"note.json",Library.BEARD_DIR+"other.glb"]))
	expect(names == PackedStringArray(["alpha","zeta"]),
		"compressed source metadata supplies sorted unique direct GLB names only")
	expect(not Library.glb_exists(folder+"__rl_discovery_missing_hair.glb"),
		"metadata discovery never makes an unavailable GLB readable")
	var local := "user://rl-head-discovery-%d/" % Time.get_ticks_usec()
	DirAccess.make_dir_recursive_absolute(local)
	for file: String in ["zeta.glb","alpha.GLB","ignore.json"]:
		var stream := FileAccess.open(local+file,FileAccess.WRITE)
		stream.store_string("discovery-only fixture; never parsed")
		stream.close()
	expect(Library._glb_names(local) == PackedStringArray(["alpha","zeta"]),
		"native directory discovery retains its existing file-only behavior")
	for file: String in ["zeta.glb","alpha.GLB","ignore.json"]:
		DirAccess.remove_absolute(local+file)
	DirAccess.remove_absolute(local)
	var previous := OS.get_environment("RL_HEADS")
	OS.set_environment("RL_HEADS","force")
	ReplicatedActor3D.reload_rl_heads_switch()
	var config := {"culture":"luminous","bodyTemplate":"luminous_male","gender":"male"}
	var appearance := {"hair":1,"hair_module":22,"facial_hair":2}
	var medium := ActorRenderQuality.Quality.MEDIUM
	var high := ActorRenderQuality.Quality.HIGH
	var hair_paths := ReplicatedActor3D.rl_hair_only_files_for(config,appearance,medium,false)
	var selected := Portrait.native_hair(appearance,"male")
	expect(hair_paths == PackedStringArray([Library.hair_path(selected,"male")]),
		"actor admission can request its exact modern native-head hairstyle before extraction")
	var available_hair := ReplicatedActor3D.rl_hair_only_files_for(config,appearance,medium)
	expect(available_hair == ReplicatedActor3D.rl_hair_only_files_for(config,appearance,medium,true),
		"existing callers retain available-only hair defaults")
	for path: String in hair_paths:
		expect(available_hair.has(path) == Library.glb_exists(path), "hair availability still reflects actual files")
	var full_paths := ReplicatedActor3D.rl_head_files_for(config,appearance,high,false)
	expect(full_paths.has(Library.head_path("male")) \
		and full_paths.has(Library.hair_path(Portrait.hair(appearance,"male"),"male")),
		"High head admission includes its actual head and selected hairstyle")
	var available_full := ReplicatedActor3D.rl_head_files_for(config,appearance,high)
	expect(available_full == ReplicatedActor3D.rl_head_files_for(config,appearance,high,true),
		"existing callers retain available-only full-head defaults")
	for path: String in full_paths:
		expect(available_full.has(path) == Library.glb_exists(path), "head availability still reflects actual files")
	expect(ReplicatedActor3D.rl_head_files_for(config,appearance,medium,false).is_empty() \
		and ReplicatedActor3D.rl_hair_only_files_for(config,appearance,high,false).is_empty(),
		"potential discovery preserves quality and renderer selection")
	expect(ReplicatedActor3D.rl_head_files_for({},appearance,high,false).is_empty() \
		and ReplicatedActor3D.rl_hair_only_files_for(config,{"rl_head":{}},medium,false).is_empty(),
		"non-portrait bodies and explicit lab faces retain their existing exclusions")
	OS.set_environment("RL_HEADS","classic")
	ReplicatedActor3D.reload_rl_heads_switch()
	expect(ReplicatedActor3D.rl_head_files_for(config,appearance,high,false).is_empty() \
		and ReplicatedActor3D.rl_hair_only_files_for(config,appearance,medium,false).is_empty(),
		"the classic-head switch still excludes all RL requests")
	OS.set_environment("RL_HEADS",previous)
	ReplicatedActor3D.reload_rl_heads_switch()
	expect(Library._documents.size() == documents and GlbSceneCache._scenes.size() == scenes,
		"file discovery never parses or caches a GLB")
	print("RL head file discovery: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)

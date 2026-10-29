class_name RLHeadLibrary
extends RefCounted
## Finds and reads the RL head's assets, once while any RL head is drawn.
##
## The files ship the way develop ships its native actors
## (tools/package_client.py, actor_shipping):
## * The head, hair and beard GLBs (assets/actors/native/rl_heads/) are a
##   loose-only actor folder: never imported (the local .gdignore AGENTS.md
##   prepares for every loose actor folder keeps them out of a checkout's
##   import, as for races/ and hair/), shipped beside the executable, and read
##   through GlbSceneCache from the globalized path, which GLTFDocument parses
##   raw in a checkout and an export alike. Their only LODs are the authored
##   `_lod<k>` levels.
## * The maps (assets/actors/native/rl_head_textures/) are load()ed through
##   ResourceLoader, from the PCK in an export: each PNG's import settings are
##   committed beside it (VRAM-compressed with mipmaps, BPTC for the
##   channel-packed masks, features2 limited to 1024 px), so a checkout draws
##   what a package ships. manifest.json is packed as a plain file.
## The pieces of a head or a beard, and the shared ShaderMaterials every actor
## draws them with, are cached here; a hairstyle is instanced per actor because
## each actor's hair has a skeleton of its own for its springs.
##
## The asset contract (see RLHeadRig) is read leniently: a missing hairstyle,
## beard or texture is logged once and drawn without, never an error.
##
## Every RLHeadRig is a user from its creation to its deletion (`acquire` /
## `release`). When the last one goes - every Human switched down from High,
## or the last one left the scene - `release_unused` drops the cached pieces,
## textures, materials and parsed documents, GlbSceneCache's scenes of the RL
## files, the body cuts, the headwear refits and the baked identities, as
## develop's own High portrait releases its caches with its last user.

const ROOT := "res://assets/actors/native/rl_heads/"
const HAIR_DIR := ROOT + "hair/"
const BEARD_DIR := ROOT + "beards/"
const TEXTURE_DIR := "res://assets/actors/native/rl_head_textures/"
const MANIFEST_PATH := TEXTURE_DIR + "manifest.json"
const GLB_MESH_EXTRAS := preload("res://src/actors/glb_mesh_extras.gd")
const IDENTITY_BAKE := preload("res://src/actors/rl_head/rl_head_identity_bake.gd")
const SHADERS := {
	"rl_skin": preload("res://src/actors/rl_head/rl_skin.gdshader"),
	"rl_eye": preload("res://src/actors/rl_head/rl_eye.gdshader"),
	"rl_lash": preload("res://src/actors/rl_head/rl_lash.gdshader"),
	"rl_brow": preload("res://src/actors/rl_head/rl_brow.gdshader"),
	"rl_hair": preload("res://src/actors/rl_head/rl_hair.gdshader"),
	"rl_cornea": preload("res://src/actors/rl_head/rl_cornea.gdshader"),
	"rl_mouth": preload("res://src/actors/rl_head/rl_mouth.gdshader"),
	"rl_hidden": preload("res://src/actors/rl_head/rl_hidden.gdshader"),
}
## Imported material name -> the shader that draws it.
const MATERIAL_SHADERS := {
	"rl_skin": "rl_skin", "rl_mouth": "rl_mouth", "rl_eye": "rl_eye",
	"rl_lash": "rl_lash", "rl_brow": "rl_brow", "rl_hair_clump": "rl_hair",
	"rl_hair_card": "rl_hair", "rl_beard": "rl_hair", "rl_cornea": "rl_cornea",
}
## Drawn with the actor's own body material, not one of ours: the clipped
## lower part of the body triangles the cut removes, carrying the body's UVs
## (glTF material extras `useBodyMaterial`). See RLHeadRig.set_body_material.
const BODY_PATCH_MATERIAL := "rl_bodypatch"
## The brow cards stay off while brows are painted (features B).
const DRAW_BROW_CARDS := false
## How much of the lash cards' coverage is kept, by quality (LOW, MEDIUM, HIGH).
const LASH_OPACITY: Array[float] = [0.6, 0.65, 0.7]
## The cornea is drawn from this quality up; below it the shell is skipped.
const CORNEA_QUALITY := ActorRenderQuality.Quality.HIGH
## The MPFB eye layout keeps the cornea shell in this corner of the texture;
## the opaque eye shader discards it and paints the cornea's gloss itself.
const CORNEA_UV_MIN := Vector2(0.875, 0.875)
## Half the angle an iris subtends on the eyeball, about 29 degrees for a
## human eye (11.7 mm across a 24 mm ball).
const IRIS_HALF_ANGLE := 29.0
const LOD_SUFFIX := "_lod"
## `legacy:<style>` hair is the game's own fitted hairstyle on the luminous
## body, drawn through the skinned-hair path (RLHeadRig._build_legacy_hair).
## The RL cranium sits at least 1.5 mm inside the shipped skull, so they fit.
const LEGACY_PREFIX := "legacy:"
const LEGACY_HAIR_DIR := "res://assets/actors/native/hair/fitted/"
const LEGACY_HAIR_STYLES: Array[String] = ["parted", "long", "buns", "buzzed", "bob",
	"ponytail", "braid", "topknot", "mohawk"]

static var _documents: Dictionary = {}
static var _heads: Dictionary = {}
static var _beards: Dictionary = {}
static var _hair_info: Dictionary = {}
static var _textures: Dictionary = {}
static var _materials: Dictionary = {}
static var _manifest: Variant = null
static var _warned: Dictionary = {}
static var _users := 0
## How long the caches outlive their last RL head (see release). A quality
## switch down and back up, or a session's next Human, within it costs no
## reading or parsing; released after it, as develop's High portrait releases
## its own with its last user.
const RETAIN_SECONDS := 120.0
## RETAIN_SECONDS, lowered by tests (0 releases at once).
static var retain_seconds := RETAIN_SECONDS
## Bumped by every acquire, release and clear: a pending timed release only
## acts if nothing happened since it was scheduled.
static var _release_generation := 0
## Global GLB path -> {"holder", "task"}: prewarm parses still on a worker.
static var _warming: Dictionary = {}
## Global GLB paths waiting for their prewarm parse.
static var _warm_queue: PackedStringArray = PackedStringArray()
## Global GLB paths a prewarm published to GlbSceneCache (let go with the rest).
static var _warmed: Dictionary = {}
static var _warm_polling := false
## A full prewarm asked for the renderer's pipelines too (see _warm_pipelines).
static var _pipelines_wanted := false
static var _pipelines_done := false
## The out-of-sight node holding one instance of every RL surface, while it is up.
static var _pipeline_holder: Node3D = null
## Frames the pipeline holder stays in the scene.
const PIPELINE_WARM_FRAMES := 30
## Map files a full prewarm queued; the per-frame poll loads one a frame.
static var _texture_queue: PackedStringArray = PackedStringArray()

## The per-actor values (rl_head_instance.gdshaderinc) each RL shader reads, by
## shader: what a per-face material copy of it carries (see face_material).
const SHADER_VALUES := {
	"rl_skin": ["skin_color", "lip_tint", "brow_color", "hair_color", "freckles", "liner", "stubble",
		"hairline", "brow_style", "brow_thickness", "liner_wing"],
	"rl_eye": ["eye_color", "eye_look"],
	"rl_lash": ["hair_color"],
	"rl_brow": ["brow_color"],
	"rl_hair": ["hair_color", "hair_detail"],
	"rl_cornea": [],
	"rl_mouth": [],
}
const INSTANCE_INCLUDE := "#include \"res://src/actors/rl_head/rl_head_instance.gdshaderinc\""
const MATERIAL_VALUES_DEFINE := "#define RL_MATERIAL_VALUES\n"
## -1 unread, 0 instance uniforms, 1 material values (see material_values).
static var _values_switch := -1
## Shared shader -> its RL_MATERIAL_VALUES compile.
static var _value_shaders: Dictionary = {}
## Shared material id + values -> WeakRef of its per-face copy.
static var _face_materials: Dictionary = {}


## Drops every cached piece, texture and material, for a reload in the lab
## and at the end of a session (ReplicatedActor3D.clear_wardrobe_texture_cache).
static func clear() -> void:
	_release_generation += 1
	release_unused()
	_warned.clear()


## One more RL head drawn (RLHeadRig.attach).
static func acquire() -> void:
	_users += 1
	_release_generation += 1


## One RL head fewer (an RLHeadRig deleted). When the last one goes the caches
## stay for RETAIN_SECONDS (retain_seconds) and are released then if no RL
## head took them again meanwhile: a quality switch back up to High, the next
## creation preview or the next Human to arrive reuses the parsed heads, hair,
## beards, maps and materials instead of reading them again.
static func release() -> void:
	_users = maxi(0, _users - 1)
	if _users > 0:
		return
	_release_generation += 1
	var tree := Engine.get_main_loop() as SceneTree
	if retain_seconds <= 0.0 or tree == null:
		release_unused()
		return
	var generation := _release_generation
	tree.create_timer(retain_seconds, true, false, true).timeout.connect(func() -> void:
		if generation == _release_generation and _users == 0:
			release_unused())


## Whether caches no RL head uses are being kept for RETAIN_SECONDS.
static func retaining() -> bool:
	return _users == 0 and is_loaded()


## Starts the timed release (see release) when no RL head uses the caches, for
## caches filled by `prewarm` that no head took (the quality left High).
static func release_if_unused() -> void:
	if _users == 0 and is_loaded():
		_users = 1
		release()


## Parses RL GLBs on the WorkerThreadPool ahead of their use (by default every
## one a High Human can draw: both head modules, every hairstyle and beard),
## each file its own task, each published to GlbSceneCache on the main thread
## once its task has finished (a per-frame poll, and every `head`, `beard` and
## `hair_info` lookup). The main thread never waits for a task (GlbSceneCache
## "Threads": a parse can need the main thread): a file it needs before its
## task has finished is parsed there as before, and the task's copy is dropped
## when it arrives. The RL files name no texture by URI, so a worker parse
## reads no texture back. Called when the graphics quality is or becomes High
## (ReplicatedActor3D.prewarm_rl_heads): before the actors switch up, so the
## files the first High Humans need are parsed on the worker while this thread
## parses the first of them. A client closing waits for the running parse
## (cancel_warm, then `warming` until false): a process that quits while a
## worker parses can hang.
static func prewarm(paths: PackedStringArray = PackedStringArray()) -> void:
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or not prewarm_enabled():
		return
	if paths.is_empty():
		paths = warm_paths()
	if not GlbSceneCache.GltfQuantization.ensure_registered():
		return
	var started := false
	for path: String in paths:
		var key := ProjectSettings.globalize_path(path)
		if _warming.has(key) or _warm_queue.has(key) or not FileAccess.file_exists(key) \
				or GlbSceneCache.missing(PackedStringArray([key])).is_empty():
			continue
		_warm_queue.append(key)
		started = true
	_start_next_warm()
	if paths == warm_paths():
		started = _queue_textures() or started
		if _pipeline_holder == null and not _pipelines_done:
			_pipelines_wanted = true
			started = true
	if started and not _warm_polling:
		var tree := Engine.get_main_loop() as SceneTree
		if tree != null:
			_warm_polling = true
			tree.process_frame.connect(_poll_warm)


## Starts the next queued parse when none is running: one worker parse at a
## time, beside whatever the main thread parses (several GLTFDocument parses
## on workers at once crashed the headless renderer).
static func _start_next_warm() -> void:
	while _warming.is_empty() and not _warm_queue.is_empty():
		var key := _warm_queue[0]
		_warm_queue.remove_at(0)
		if GlbSceneCache.missing(PackedStringArray([key])).is_empty():
			continue
		# The task writes only its own holder, read here once it has finished.
		var holder := {}
		_warming[key] = {"holder": holder, "task": WorkerThreadPool.add_task(func() -> void:
			holder["scenes"] = GlbSceneCache.prepare(PackedStringArray([key])), false, "RL head GLB parse")}


## Whether prewarm works ahead (RL_HEAD_PREWARM=0 turns it off, for A/B checks).
static func prewarm_enabled() -> bool:
	return OS.get_environment("RL_HEAD_PREWARM").strip_edges() != "0"


## Every RL GLB a High Human can draw: both heads, every hairstyle and beard.
static func warm_paths() -> PackedStringArray:
	var paths := PackedStringArray()
	for sex: String in RLHeadAppearance.SEXES:
		paths.append(head_path(sex))
	for style: String in hair_styles():
		paths.append(hair_path(style))
	for style: String in _glb_names(BEARD_DIR):
		paths.append(beard_path(style))
	return paths


## Publishes every finished prewarm parse (main thread only). A file the main
## thread parsed meanwhile keeps its own copy.
static func collect_warm() -> void:
	if (_warming.is_empty() and _warm_queue.is_empty()) or OS.get_thread_caller_id() != OS.get_main_thread_id():
		return
	for key: Variant in _warming.keys():
		var entry: Dictionary = _warming[key]
		if not WorkerThreadPool.is_task_completed(int(entry["task"])):
			continue
		WorkerThreadPool.wait_for_task_completion(int(entry["task"]))
		_warming.erase(key)
		var scenes: Dictionary = (entry["holder"] as Dictionary).get("scenes", {})
		if not scenes.is_empty():
			GlbSceneCache.install_prepared(scenes)
			_warmed[str(key)] = true
	_start_next_warm()


## Stops the queued prewarm work (the client closing): the parse already
## running finishes on its worker and is published when it arrives; `warming`
## stays true until then. Never waits here.
static func cancel_warm() -> void:
	_warm_queue.clear()
	_texture_queue.clear()
	_pipelines_wanted = false
	if is_instance_valid(_pipeline_holder):
		_pipeline_holder.queue_free()
	_pipeline_holder = null


## Whether a prewarm is still at work: parses, queued maps, the pipeline warm-up.
static func warming() -> bool:
	return not _warming.is_empty() or not _warm_queue.is_empty() or not _texture_queue.is_empty() or _pipelines_wanted \
		or _pipeline_holder != null


## Forward+ compiles a surface's render pipelines when the surface first enters
## a scene, on worker threads, and the first frame that draws it waits for
## them (2.8 s for the first RL head in a fresh session, against 0.1 s for
## develop's classic head: 49 surface pipelines). Once a full prewarm has
## parsed every file, one instance of every RL surface - each head level, beard
## and hairstyle, skinned as the game draws them, with the shared materials
## the game gives them at High - stays out of sight for PIPELINE_WARM_FRAMES,
## so those pipelines are compiled before the first RL head is shown. The
## Compatibility renderer compiles at first draw instead and skips this.
static func _warm_pipelines() -> void:
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null or tree.root == null \
			or RenderingServer.get_current_rendering_method() == "gl_compatibility":
		_pipelines_done = true
		return
	var holder := Node3D.new()
	holder.name = "RLHeadPipelineWarmup"
	# Far below the world, in no camera's sight.
	holder.position = Vector3(0.0, -10000.0, 0.0)
	var quality := ActorRenderQuality.Quality.HIGH
	for path: String in warm_paths():
		var instance := GlbSceneCache.instantiate(ProjectSettings.globalize_path(path))
		if instance == null:
			continue
		var sex := ""
		var style := ""
		if path.begins_with(HAIR_DIR) or path.begins_with(BEARD_DIR):
			style = path.get_file().get_basename()
			sex = "female" if style.begins_with("mira") else "male"
		else:
			sex = path.get_file().get_basename().trim_prefix("rl_head_")
		for node: Node in instance.find_children("*", "MeshInstance3D", true, false):
			var mesh_node := node as MeshInstance3D
			if mesh_node.mesh == null:
				continue
			for surface: int in mesh_node.mesh.get_surface_count():
				var imported := mesh_node.mesh.surface_get_material(surface)
				var shared := material(imported.resource_name if imported != null else "", sex, style, quality)
				if shared != null:
					mesh_node.set_surface_override_material(surface, shared)
		holder.add_child(instance)
	tree.root.add_child(holder)
	_pipeline_holder = holder


## Queues every map under TEXTURE_DIR not loaded yet (an export lists them by
## their .import files); true when any was queued. The maps are loaded on the
## main thread, one a frame (`_poll_warm`): a texture load needs the main
## thread, so waiting for one on ResourceLoader's threads from here can hang.
static func _queue_textures() -> bool:
	if not DirAccess.dir_exists_absolute(TEXTURE_DIR):
		return false
	for listed: String in DirAccess.get_files_at(TEXTURE_DIR):
		var file := listed.trim_suffix(".import").trim_suffix(".remap")
		if file.get_extension().to_lower() != "png" or _texture_queue.has(file) \
				or _textures.has(TEXTURE_DIR + file) or not ResourceLoader.exists(TEXTURE_DIR + file):
			continue
		_texture_queue.append(file)
	return not _texture_queue.is_empty()


static func _poll_warm() -> void:
	collect_warm()
	if not _texture_queue.is_empty():
		texture(_texture_queue[0])
		_texture_queue.remove_at(0)
		return
	if _warming.is_empty() and _warm_queue.is_empty() and _pipelines_wanted:
		_pipelines_wanted = false
		_warm_pipelines()
	if _pipeline_holder != null:
		var frames := int(_pipeline_holder.get_meta(&"frames", 0)) + 1
		_pipeline_holder.set_meta(&"frames", frames)
		if frames >= PIPELINE_WARM_FRAMES:
			_pipeline_holder.queue_free()
			_pipeline_holder = null
			_pipelines_done = true
		return
	if _warming.is_empty():
		var tree := Engine.get_main_loop() as SceneTree
		if not _warm_queue.is_empty():
			return
		if tree != null and tree.process_frame.is_connected(_poll_warm):
			tree.process_frame.disconnect(_poll_warm)
		_warm_polling = false


## How many RL heads hold the caches.
static func users() -> int:
	return _users


## Whether anything is cached (heads, beards, textures, materials, prewarmed files and maps).
static func is_loaded() -> bool:
	return not (_heads.is_empty() and _beards.is_empty() and _textures.is_empty()
		and _materials.is_empty() and _hair_info.is_empty() and _warmed.is_empty()
		and _texture_queue.is_empty())


## Drops every shared RL resource; the next RL head loads them again.
static func release_unused() -> void:
	var paths: Array = _documents.keys()
	for info: Variant in _heads.values():
		if info is Dictionary and (info as Dictionary).has("path"):
			paths.append(str((info as Dictionary)["path"]))
	for style: Variant in _beards.keys():
		paths.append(beard_path(str(style)))
	for style: Variant in _hair_info.keys():
		paths.append(hair_path(str(style)))
	for key: Variant in _warmed.keys():
		paths.append(ProjectSettings.localize_path(str(key)))
	_warmed.clear()
	for path: Variant in paths:
		_forget_scene(str(path))
	_documents.clear()
	_heads.clear()
	_beards.clear()
	_hair_info.clear()
	if is_instance_valid(_pipeline_holder):
		_pipeline_holder.queue_free()
	_pipeline_holder = null
	_pipelines_wanted = false
	_pipelines_done = false
	_textures.clear()
	_texture_queue.clear()
	_warm_queue.clear()
	_materials.clear()
	_face_materials.clear()
	_manifest = null
	RLHeadBodyCut.clear()
	RLHeadwearFit.clear_caches()
	IDENTITY_BAKE.clear()
	RLHeadRig.clear_caches()


## GlbSceneCache keeps each scene it loaded for the session; an RL file it no
## longer needs to hold is let go here (its other entries are untouched).
static func _forget_scene(path: String) -> void:
	if not path.begins_with(ROOT):
		return
	var key := ProjectSettings.globalize_path(path)
	for cache: Dictionary in [GlbSceneCache._scenes, GlbSceneCache._direct_raw_scenes,
			GlbSceneCache._failed, GlbSceneCache._prepared_entries, GlbSceneCache._geometry_entries]:
		cache.erase(key)


## Logs `message` the first time `key` is seen this session: a warning, or a
## plain line for something the contract allows to be absent (`notice`).
static func warn_once(key: String, message: String, notice: bool = false) -> void:
	if _warned.has(key):
		return
	_warned[key] = true
	if notice:
		print("RL heads: " + message)
	else:
		push_warning("RL heads: " + message)


static func head_path(sex: String) -> String:
	return ROOT + "rl_head_%s.glb" % sex


static func hair_path(style: String) -> String:
	return HAIR_DIR + style + ".glb"


## A shipped fitted hairstyle for the luminous body of `sex` (`legacy:<style>`).
static func legacy_hair_path(sex: String, style: String) -> String:
	return LEGACY_HAIR_DIR + "luminous_%s_%s_%s.glb" % [sex, style, sex]


## The shipped fitted hairstyles there are for `sex`, as `legacy:<style>` names.
static func legacy_hair_styles(sex: String) -> PackedStringArray:
	var names := PackedStringArray()
	for style: String in LEGACY_HAIR_STYLES:
		if FileAccess.file_exists(legacy_hair_path(sex, style)):
			names.append(LEGACY_PREFIX + style)
	return names


static func beard_path(style: String) -> String:
	return BEARD_DIR + style + ".glb"


## The hairstyles on disk, by file name without extension.
static func hair_styles() -> PackedStringArray:
	return _glb_names(HAIR_DIR)


## The beards on disk, plus `stubble`, which the skin shader paints.
static func beard_styles() -> PackedStringArray:
	var names := _glb_names(BEARD_DIR)
	if not names.has(RLHeadAppearance.STUBBLE):
		names.append(RLHeadAppearance.STUBBLE)
	return names


## The GLBs in a loose folder. The folder is listed on disk at its globalized
## path, beside the executable in an export: res:// lists only the PCK there,
## which holds none of them.
static func _glb_names(folder: String) -> PackedStringArray:
	var names := PackedStringArray()
	var on_disk := ProjectSettings.globalize_path(folder)
	if not DirAccess.dir_exists_absolute(on_disk):
		return names
	for file: String in DirAccess.get_files_at(on_disk):
		if file.get_extension().to_lower() == "glb":
			names.append(file.get_basename())
	names.sort()
	return names


## Whether a loose GLB is on disk (beside the executable in an export), where
## GlbSceneCache and the readers here open it.
static func glb_exists(path: String) -> bool:
	return FileAccess.file_exists(ProjectSettings.globalize_path(path))


## The parsed glTF JSON of a GLB (only the JSON chunk is read), or {}.
static func glb_document(path: String) -> Dictionary:
	if not _documents.has(path):
		var parsed: Variant = GLB_MESH_EXTRAS._read_glb_json(ProjectSettings.globalize_path(path)) \
			if glb_exists(path) else null
		_documents[path] = parsed if parsed is Dictionary else {}
	return _documents[path] as Dictionary


## A material's glTF extras in a GLB, by material name, or {}.
static func material_extras(path: String, material_name: String) -> Dictionary:
	for material: Variant in glb_document(path).get("materials", []) as Array:
		if material is Dictionary and str((material as Dictionary).get("name", "")) == material_name:
			var extras: Variant = (material as Dictionary).get("extras", {})
			return extras as Dictionary if extras is Dictionary else {}
	return {}


## `asset.extras.<key>` of a GLB, or {}.
static func asset_extras(path: String, key: String) -> Dictionary:
	var asset: Variant = glb_document(path).get("asset", {})
	if asset is not Dictionary:
		return {}
	var extras: Variant = (asset as Dictionary).get("extras", {})
	if extras is not Dictionary:
		return {}
	var value: Variant = (extras as Dictionary).get(key, {})
	return value as Dictionary if value is Dictionary else {}


## Everything the rig needs from one sex's head module, or {} when the file is
## missing. `lods` holds one Array of pieces per LOD level, level 0 first.
static func head(sex: String) -> Dictionary:
	if _heads.has(sex):
		return _heads[sex] as Dictionary
	collect_warm()
	var path := head_path(sex)
	var info := {}
	var lods := _skinned_lods(path, "rl_head") if glb_exists(path) else []
	if lods.is_empty():
		warn_once("head:" + sex, "no head module at " + path)
	else:
		var extras := asset_extras(path, "rlHead")
		var names := PackedStringArray()
		var controls: Array = extras.get("controls", []) as Array
		for control_value: Variant in controls:
			if control_value is Dictionary:
				names.append(str((control_value as Dictionary).get("name", "")))
		var expressions := PackedStringArray()
		for name: Variant in extras.get("expressions", []) as Array:
			var shape := str(name)
			expressions.append(shape if shape.begins_with("ex_") else "ex_" + shape)
		info = {"path": path, "sex": sex, "extras": extras, "controls": controls,
			"control_names": names, "expressions": expressions, "lods": lods,
			"body_cut": extras.get("bodyCut", {}) as Dictionary,
			"eye": _eye_layout(lods[0] as Array)}
	_heads[sex] = info
	return info


## A beard's pieces by LOD, or [] when there is no such file.
static func beard(style: String) -> Array:
	if not _beards.has(style):
		collect_warm()
		var path := beard_path(style)
		var lods: Array = []
		if glb_exists(path):
			lods = _skinned_lods(path, "beard")
		_beards[style] = lods
	return _beards[style] as Array


## The hairstyle's `rlHair` extras, or {} for a missing file (logged once).
static func hair_info(style: String) -> Dictionary:
	if not _hair_info.has(style):
		collect_warm()
		var path := hair_path(style)
		var info := {}
		if glb_exists(path):
			info = {"path": path, "extras": asset_extras(path, "rlHair")}
		else:
			warn_once("hair:" + style, "hairstyle %s missing, drawing the head bald" % style, true)
		_hair_info[style] = info
	return _hair_info[style] as Dictionary


## A fresh instance of a hairstyle's scene, its own skeleton included.
static func instantiate_hair(style: String) -> Node3D:
	var info := hair_info(style)
	if info.is_empty():
		return null
	return GlbSceneCache.instantiate(str(info["path"]))


## The LOD level a mesh node's name states: `<base>_lod<k>` is k, anything
## else is 0.
static func lod_level(node_name: String) -> int:
	var at := node_name.rfind(LOD_SUFFIX)
	if at < 0:
		return 0
	var digits := node_name.substr(at + LOD_SUFFIX.length())
	return int(digits) if digits.is_valid_int() else 0


## The skinned mesh pieces of a head or beard GLB, grouped by LOD level. Each
## piece keeps its mesh, the names of its skin joints and their inverse binds.
## The binds are glTF's own, in model space (the mesh node sits at the scene
## root), so they rebind onto any rig whose skeleton is the body's model
## space - the body's own does - with an identity node transform; the
## Skeleton3D Godot builds for the three-joint chain sits at spine_02 and its
## node transform is deliberately not carried over.
static func _skinned_lods(path: String, base_name: String) -> Array:
	var imported := GlbSceneCache.instantiate(path)
	if imported == null:
		return []
	var by_level: Dictionary = {}
	for node_value: Node in imported.find_children("*", "MeshInstance3D", true, false):
		var source := node_value as MeshInstance3D
		if source.mesh == null:
			continue
		var bones := PackedStringArray()
		var binds: Array[Transform3D] = []
		var skeleton := source.get_node_or_null(source.skeleton) as Skeleton3D
		if source.skin != null:
			for bind: int in source.skin.get_bind_count():
				var bone_name := String(source.skin.get_bind_name(bind))
				if bone_name.is_empty() and skeleton != null and source.skin.get_bind_bone(bind) >= 0:
					bone_name = skeleton.get_bone_name(source.skin.get_bind_bone(bind))
				bones.append(bone_name)
				binds.append(source.skin.get_bind_pose(bind))
		var level := lod_level(str(source.name))
		if not by_level.has(level):
			by_level[level] = []
		(by_level[level] as Array).append({"name": str(source.name), "mesh": source.mesh,
			"bones": bones, "binds": binds, "level": level,
			"head_bind": bones.find("Head")})
	imported.free()
	var levels: Array = by_level.keys()
	levels.sort()
	var lods: Array = []
	for level: Variant in levels:
		lods.append(by_level[level])
	if lods.is_empty():
		warn_once("pieces:" + path, "%s has no %s meshes" % [path, base_name])
	return lods


## Where each eye's iris sits in the eye texture, read off the eye surface
## itself so the procedural fallback and the `look` offset follow whatever
## layout the head uses. For each side, the front of the eyeball (its
## vertex furthest forward, the cornea shell excluded) is the iris centre;
## a least-squares fit of UV against the direction from the eyeball's centre
## gives the 2x2 map from a look angle (radians, x right and y up) to a UV
## shift; and that map at IRIS_HALF_ANGLE is the iris radius.
static func _eye_layout(pieces: Array) -> Dictionary:
	for piece: Dictionary in pieces:
		var mesh := piece["mesh"] as Mesh
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface)
			if material == null or material.resource_name != "rl_eye":
				continue
			var arrays := mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
			var layout := {}
			for side: float in [1.0, -1.0]:
				var fit := _fit_eye(points, uvs, side)
				if not fit.is_empty():
					layout["right" if side > 0.0 else "left"] = fit
			return layout
	return {}


static func _fit_eye(points: PackedVector3Array, uvs: PackedVector2Array, side: float) -> Dictionary:
	var centre := Vector3.ZERO
	var count := 0
	var front := -1
	for index: int in points.size():
		if points[index].x * side <= 0.0 or (uvs[index].x > CORNEA_UV_MIN.x and uvs[index].y > CORNEA_UV_MIN.y):
			continue
		centre += points[index]
		count += 1
		if front < 0 or points[index].z > points[front].z:
			front = index
	if count < 8:
		return {}
	centre /= count
	var axis := (points[front] - centre).normalized()
	var right := Vector3.UP.cross(axis).normalized()
	if right.dot(Vector3.RIGHT) < 0.0:
		right = -right
	var up := axis.cross(right).normalized()
	if up.dot(Vector3.UP) < 0.0:
		up = -up
	var origin := uvs[front]
	# Normal equations for uv - origin = J * (a, b) over the front cap.
	var saa := 0.0
	var sab := 0.0
	var sbb := 0.0
	var sau := Vector2.ZERO
	var sbu := Vector2.ZERO
	for index: int in points.size():
		if points[index].x * side <= 0.0 or (uvs[index].x > CORNEA_UV_MIN.x and uvs[index].y > CORNEA_UV_MIN.y):
			continue
		var direction := (points[index] - centre).normalized()
		if direction.dot(axis) < cos(deg_to_rad(40.0)):
			continue
		var a := atan2(direction.dot(right), direction.dot(axis))
		var b := atan2(direction.dot(up), direction.dot(axis))
		var delta := uvs[index] - origin
		saa += a * a
		sab += a * b
		sbb += b * b
		sau += delta * a
		sbu += delta * b
	var determinant := saa * sbb - sab * sab
	if absf(determinant) < 1e-9:
		return {}
	var column_a := (sau * sbb - sbu * sab) / determinant
	var column_b := (sbu * saa - sau * sab) / determinant
	var radius := deg_to_rad(IRIS_HALF_ANGLE) * (column_a.length() + column_b.length()) * 0.5
	return {"uv": origin, "look_x": column_a, "look_y": column_b, "iris_radius": radius}


# ---------------------------------------------------------------- textures

static func _read_manifest() -> Dictionary:
	if _manifest == null:
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST_PATH)) \
			if FileAccess.file_exists(MANIFEST_PATH) else null
		_manifest = parsed if parsed is Dictionary else {}
	return _manifest as Dictionary


## A value from rl_head_textures/manifest.json, tolerant of its exact shape: the first
## of `keys` (most specific first) found at the top level or under `materials`
## whose entry has `slot`. A per-quality entry ({"high": ..., "low": ...,
## "default": ...}) resolves for `quality`.
static func manifest_value(keys: Array[String], slot: String, quality: int) -> Variant:
	var manifest := _read_manifest()
	var sections: Array[Dictionary] = [manifest]
	if manifest.get("materials") is Dictionary:
		sections.push_front(manifest["materials"] as Dictionary)
	for key: String in keys:
		for section: Dictionary in sections:
			var entry: Variant = section.get(key)
			# `"eye": "eye.png"`: a single file for the key's albedo.
			if entry is String and slot == "albedo":
				return entry
			if entry is not Dictionary or not (entry as Dictionary).has(slot):
				continue
			var value: Variant = (entry as Dictionary)[slot]
			if value is Dictionary:
				var by_quality := value as Dictionary
				var quality_name: String = ActorRenderQuality.quality_name(quality)
				return by_quality.get(quality_name, by_quality.get("default", null))
			return value
	return null


## A map under rl_head_textures/, or null when the file is absent (logged
## once). The maps are imported with the settings committed beside them
## (VRAM-compressed, mipmapped, features2 at 1024 px) and used as imported, in
## a checkout and from a package's PCK alike.
static func texture(file: String) -> Texture2D:
	if file.is_empty():
		return null
	var path := file if file.begins_with("res://") else TEXTURE_DIR + file
	if not _textures.has(path):
		var loaded: Texture2D = null
		if ResourceLoader.exists(path):
			loaded = _with_mipmaps(load(path) as Texture2D, _size_cap(path))
		elif FileAccess.file_exists(path):
			# Not imported yet (a file the lead just dropped in): read it raw so
			# the lab shows it before the next editor import.
			var image := Image.load_from_file(ProjectSettings.globalize_path(path))
			if image != null and not image.is_empty():
				loaded = _with_mipmaps(ImageTexture.create_from_image(image), _size_cap(path))
		if loaded == null:
			warn_once("texture:" + path, "texture %s not there yet, drawing without it" % path, true)
		_textures[path] = loaded
	return _textures[path] as Texture2D


## Head textures are minified hard at gameplay distance. A block-compressed
## import is what the committed import settings make (VRAM-compressed with
## its mip chain; tools/package_client.py and the tests hold every map to
## that) and is used as it is, never read back from the GPU. Anything else -
## a raw file not imported yet, or an import that lost its committed settings
## - gets a mip chain built here, once per texture, first scaled down to its
## map's MAP_SIZE_CAPS size. It stays uncompressed: client code never calls an
## Image compressor (export templates have no BC encoder; compression belongs
## to the committed imports and the package tool, test_build_vram_textures.py).
static func _with_mipmaps(source: Texture2D, max_size: int = 0) -> Texture2D:
	if source == null:
		return null
	if source is CompressedTexture2D:
		if _block_compressed(source.get_format()):
			return source
		warn_once("mips:" + source.resource_path, "%s is imported without VRAM compression; "
			% source.resource_path + "building its mip chain at runtime (commit its import settings)")
	var image := source.get_image()
	if image == null or image.is_empty() or image.has_mipmaps():
		return source
	if image.is_compressed() and image.decompress() != OK:
		return source
	if max_size > 0 and maxi(image.get_width(), image.get_height()) > max_size:
		var scale := float(max_size) / float(maxi(image.get_width(), image.get_height()))
		image.resize(maxi(1, roundi(image.get_width() * scale)), maxi(1, roundi(image.get_height() * scale)),
			Image.INTERPOLATE_LANCZOS)
	image.generate_mipmaps()
	return ImageTexture.create_from_image(image)


## The largest size a mask keeps when it is mipmapped here, by map (the file
## name's suffix); the committed imports set the same `process/size_limit`.
## features2 holds only soft masks (stubble, blush, scalp and the face/neck
## split): at 1024 px close renders match 2048 px within 11/255 on 0.03% of the
## pixels (perf gate 2026-10-28, .local/rl-high/evidence/texcap-*), and each
## sex saves 4.2 MB of video memory. The feature and brow maps stay at 2048 px:
## at 1024 the brow strokes and freckles visibly soften.
const MAP_SIZE_CAPS := {"features2": 1024}


## Whether `format` is a GPU block format (S3TC, RGTC, BPTC, ETC, ASTC): what a
## VRAM-compressed import gives.
static func _block_compressed(format: int) -> bool:
	return format >= Image.FORMAT_DXT1 and format <= Image.FORMAT_ASTC_8x8_HDR


static func _size_cap(path: String) -> int:
	var file := path.get_file().get_basename()
	for map: String in MAP_SIZE_CAPS:
		if file.ends_with("_" + map):
			return int(MAP_SIZE_CAPS[map])
	return 0


## The texture for one material slot: the manifest's choice, else `fallback`.
static func slot_texture(keys: Array[String], slot: String, fallback: String, quality: int) -> Texture2D:
	var named: Variant = manifest_value(keys, slot, quality)
	return texture(str(named) if named is String else fallback)


# ---------------------------------------------------------------- materials

## The shared ShaderMaterial for an imported material name, or null for a name
## the contract does not know (that surface keeps its imported material).
## Shared by every actor with the same head, style and quality: per-actor
## colours and amounts are instance uniforms (RLHeadRig.apply_appearance).
static func material(material_name: String, sex: String, style: String, quality: int) -> ShaderMaterial:
	var kind := str(MATERIAL_SHADERS.get(material_name, ""))
	if kind.is_empty():
		return null
	var key := "%s|%s|%s|%d" % [material_name, sex, style, quality]
	if _materials.has(key):
		return _materials[key] as ShaderMaterial
	var result := ShaderMaterial.new()
	result.shader = SHADERS[kind]
	if (material_name == "rl_brow" and not DRAW_BROW_CARDS) \
			or (material_name == "rl_cornea" and quality < CORNEA_QUALITY):
		result.shader = SHADERS["rl_hidden"]
	result.resource_name = material_name
	match material_name:
		"rl_skin":
			_configure_skin(result, material_name, sex, quality)
		"rl_eye":
			_configure_eye(result, sex, quality)
		"rl_lash", "rl_brow":
			var short := material_name.trim_prefix("rl_")
			var keys: Array[String] = [material_name + "_" + sex, material_name, short]
			var file := short + ".png"
			_set_texture(result, "strand_texture", "has_texture",
				slot_texture(keys, "albedo", file, quality))
			if material_name == "rl_lash":
				result.set_shader_parameter("opacity", LASH_OPACITY[quality])
		"rl_hair_clump", "rl_hair_card", "rl_beard":
			var keys: Array[String] = [material_name + "_" + style, style, material_name]
			# The asset names its texture in the material's glTF extras
			# (`texture`); without that, by convention.
			var asset := beard_path(style) if material_name == "rl_beard" else hair_path(style)
			var extras := material_extras(asset, material_name)
			var file := str(extras.get("texture", ""))
			if file.is_empty():
				file = "beard.png" if material_name == "rl_beard" else "hair_%s.png" % style
			_set_texture(result, "strand_texture", "has_texture",
				slot_texture(keys, "albedo", file, quality))
			result.set_shader_parameter("card", material_name != "rl_hair_clump")
			result.set_shader_parameter("alpha_scissor", 0.5 if material_name == "rl_hair_clump" else 0.35)
			result.set_shader_parameter("anisotropic", quality != ActorRenderQuality.Quality.LOW)
	_materials[key] = result
	return result


static func _set_texture(target: ShaderMaterial, uniform_name: String, flag: String, value: Texture2D) -> void:
	target.set_shader_parameter(uniform_name, value)
	target.set_shader_parameter(flag, value != null)


## Whether the per-actor values are material uniforms on per-face copies of
## the shared materials (face_material) instead of instance uniforms on the
## shared materials themselves: in the Compatibility renderer, whose global
## instance-uniform buffer (4096 items, 16 for every mesh instance with any)
## a crowd of RL heads ran out of between 40 and 160 Humans. RL_HEAD_VALUES
## (`material` or `instance`) forces either, for A/B checks. Read once.
static func material_values() -> bool:
	if _values_switch < 0:
		var value := OS.get_environment("RL_HEAD_VALUES").strip_edges().to_lower()
		if value == "material":
			_values_switch = 1
		elif value == "instance":
			_values_switch = 0
		else:
			_values_switch = 1 if RenderingServer.get_current_rendering_method() == "gl_compatibility" else 0
	return _values_switch == 1


## Reads RL_HEAD_VALUES again on the next check (tests switch it).
static func reload_values_switch() -> void:
	_values_switch = -1


## The values `shared`'s shader reads (SHADER_VALUES), [] for one with none.
static func shader_values(shared: ShaderMaterial) -> Array:
	if shared == null or shared.shader == null:
		return []
	for kind: String in SHADER_VALUES:
		if shared.shader == SHADERS.get(kind):
			return SHADER_VALUES[kind] as Array
	return []


## The material that draws `shared` with `values` (uniform name -> value; only
## the shader's own values are read) as material uniforms: a copy of `shared`
## compiled with RL_MATERIAL_VALUES, shared by every surface asking for the
## same material and values while any of them draws it (a weak cache). A
## material whose shader includes no values (rl_hidden) is returned as it is.
static func face_material(shared: ShaderMaterial, values: Dictionary) -> ShaderMaterial:
	if shared == null or shared.shader == null or _values_shader(shared.shader) == shared.shader:
		# A shader without the per-actor values (rl_hidden) draws as it is.
		return shared
	# A shader that includes them but reads none (rl_mouth, rl_cornea) still
	# declares them: one RL_MATERIAL_VALUES copy for every face, so its
	# surfaces take no instance-uniform block either.
	var names := shader_values(shared)
	var parts := PackedStringArray([str(shared.get_instance_id())])
	for name: String in names:
		parts.append(var_to_str(values.get(name)))
	var key := "|".join(parts)
	var ref := _face_materials.get(key) as WeakRef
	var found := ref.get_ref() as ShaderMaterial if ref != null else null
	if found != null:
		return found
	var copy := ShaderMaterial.new()
	copy.shader = _values_shader(shared.shader)
	copy.resource_name = shared.resource_name
	for uniform: Dictionary in shared.shader.get_shader_uniform_list():
		var value: Variant = shared.get_shader_parameter(str(uniform["name"]))
		if value != null:
			copy.set_shader_parameter(str(uniform["name"]), value)
	for name: String in names:
		if values.has(name):
			copy.set_shader_parameter(name, values[name])
	if _face_materials.size() > 4096:
		for stale: Variant in _face_materials.keys():
			if (_face_materials[stale] as WeakRef).get_ref() == null:
				_face_materials.erase(stale)
	_face_materials[key] = weakref(copy)
	return copy


## `shader` compiled with RL_MATERIAL_VALUES defined (its values as material
## uniforms), made once per shader.
static func _values_shader(shader: Shader) -> Shader:
	var cached := _value_shaders.get(shader.get_instance_id()) as Shader
	if cached != null:
		return cached
	var code := shader.code
	var at := code.find(INSTANCE_INCLUDE)
	var result := shader
	if at >= 0:
		result = Shader.new()
		result.code = code.insert(at, MATERIAL_VALUES_DEFINE)
	_value_shaders[shader.get_instance_id()] = result
	return result


static func _configure_skin(target: ShaderMaterial, material_name: String, sex: String, quality: int) -> void:
	var keys: Array[String] = [material_name + "_" + sex, sex, "head_" + sex, material_name]
	var prefix := "head_%s_" % sex
	_set_texture(target, "albedo_texture", "has_albedo",
		slot_texture(keys, "albedo", prefix + "albedo.png", quality))
	_set_texture(target, "features_texture", "has_features",
		slot_texture(keys, "features", prefix + "features.png", quality))
	_set_texture(target, "features2_texture", "has_features2",
		slot_texture(keys, "features2", prefix + "features2.png", quality))
	# One hair-stroke mask per brow style. Until it exists the shader reads the
	# one painted brow in features B, as before brow styles.
	_set_texture(target, "brows_texture", "has_brows",
		slot_texture(keys, "brows", prefix + "brows.png", quality))
	var normal := slot_texture(keys, "normal", prefix + "normal.png", quality) \
		if quality != ActorRenderQuality.Quality.LOW else null
	_set_texture(target, "normal_texture", "has_normal", normal)
	# Stubble, blush and the hairline are features2's R, G and B.
	# The albedo is painted at a reference tone, divided out exactly as the
	# body's face shader divides out its own (face_appearance.gdshader), so a
	# recoloured neck meets a recoloured body without a seam. The manifest
	# names the head's tone (sRGB); without it, the body's calibrated one.
	var reference: Variant = manifest_value(keys, "skin_reference_srgb", quality)
	if reference is not Array:
		reference = manifest_value(keys, "skinReference", quality)
	if reference is not Array:
		reference = _read_manifest().get("skinReference")
	if reference is not Array:
		reference = body_skin_reference(sex)
	var rgb: Array = reference as Array
	if rgb.size() >= 3:
		target.set_shader_parameter("skin_reference",
			Color(float(rgb[0]), float(rgb[1]), float(rgb[2])))
	var info := head(sex)
	var lods: Array = info.get("lods", []) as Array
	if not lods.is_empty() and not (lods[0] as Array).is_empty():
		target.set_shader_parameter("head_bind_index",
			maxi(0, int(((lods[0] as Array)[0] as Dictionary).get("head_bind", 2))))


static func _configure_eye(target: ShaderMaterial, sex: String, quality: int) -> void:
	var keys: Array[String] = ["rl_eye_" + sex, "rl_eye", "eye"]
	_set_texture(target, "eye_texture", "has_texture", slot_texture(keys, "albedo", "eye.png", quality))
	target.set_shader_parameter("cornea_uv_min", CORNEA_UV_MIN)
	var layout: Dictionary = head(sex).get("eye", {}) as Dictionary
	var index := 0
	for side: String in ["right", "left"]:
		var fit: Dictionary = layout.get(side, {}) as Dictionary
		if fit.is_empty():
			continue
		target.set_shader_parameter("iris_uv_%d" % index, fit["uv"])
		target.set_shader_parameter("look_x_%d" % index, fit["look_x"])
		target.set_shader_parameter("look_y_%d" % index, fit["look_y"])
		target.set_shader_parameter("iris_radius_%d" % index, float(fit["iris_radius"]))
		index += 1


## The luminous body's calibrated skin reference (models.json skinPalette).
static func body_skin_reference(sex: String) -> Array:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	if parsed is not Dictionary:
		return [0.814, 0.633, 0.532]
	var model: Dictionary = ((parsed as Dictionary).get("models", {}) as Dictionary).get(
		"luminous_" + sex, {}) as Dictionary
	var references: Array = ((model.get("skinPalette", {}) as Dictionary).get("references", {})
		as Dictionary).get("body", []) as Array
	return references[0] as Array if not references.is_empty() else [0.814, 0.633, 0.532]

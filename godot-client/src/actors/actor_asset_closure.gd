extends RefCounted
## The actor glTF files a body is built from (avatar-worker plan, AW-04a): the
## closure the actor preparer (actor_resource_warmup.gd) parses on its worker
## before Main builds a remote body, so `ReplicatedActor3D.configure` finds
## every scene in GlbSceneCache and every equipment piece in the actor's
## pieces table instead of parsing them on the main thread.
##
## It names exactly the files `configure` reads through GlbSceneCache for
## the record as presented (Main's `_presentation_dto`: authored NPC looks
## applied), using the actor's own lookups made static:
##   * the race scene (`models.json` "scene"), and for the native female body
##     its repaired shirt mesh (FemaleShirtNeckline);
##   * the game hairstyle (`ReplicatedActor3D.hair_scene_for`, the lookup
##     `_add_hair_variant` makes), read as equipment pieces, unless an RL
##     hairstyle module is drawn instead (below; a High Human draws the game
##     hairstyle while its RL head files are parsed);
##   * every worn equipment model (`equipment_model_config_for`: alias, fit
##     variant for the race), read as equipment pieces, skipping empty bare
##     slots, retired and wardrobe-only pieces; a bow the ranged presentation
##     draws also brings its arrow and the default bow (RangerBow3D).
## In "rl_files", for RLHeadLibrary.request (RL files stay with the RL head
## library and its worker): the RL hairstyle module a portrait Human draws
## without an RL head at `quality` (`rl_hair_only_files_for`), which a build
## would otherwise parse on the main thread.
## With `rl_head` (the player's own body in the game, AW-04d: it draws its RL
## head at once, never the classic head while a worker parses) "rl_files" also
## names the RL head's own files a portrait Human draws at High
## (`ReplicatedActor3D.rl_head_files_for`: head, hairstyle and beard modules).
## Not in it otherwise: the RL head's own files at High (RLHeadLibrary already
## parses them on its worker while the classic head is drawn,
## _rl_head_files_ready), the
## animation library (reported in "libraries": creatures' are prepared with
## their scene by the creature job, a race's is parsed once per session on
## main until AW-04c), and the mount's files (the mount id is reported in
## "mount"; `mount_closure` names them, AW-07: Main asks for them beside a
## rider's body and binds mounts outside the packet handler). A model
## under the creatures folder is a creature: "creature" is true, its scene is
## left to the creature job (scene + retargeted clips) and "scenes" holds only
## what it wears. Only "rl_files" depends on the graphics quality.
##
## Static: it reads the dictionaries it is given and the actor's static
## lookups, never a node or a cache (RL file names are checked on disk; a
## mount's profile is read through MountProfiles, data only);
## `memoized` and `mount_closure` keep what they computed for Main's
## repeated asks.
## Main thread.
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const FemaleShirtNeckline := preload("res://src/actors/female_shirt_neckline.gd")
const MountProfiles := preload("res://src/mounts/mount_profiles.gd")
const CREATURE_ROOT := "res://assets/actors/native/creatures/"
## Closures `memoized` keeps (it starts again when full).
const MEMO_CAPACITY := 256

## Main's repeated asks (every candidate pass asks again for a body that
## waits) cost a few dictionary lookups: computing a Human's closure maps its
## face for the RL hairstyle and checks the file on disk (about 0.8 ms headless
## on the development laptop). Keyed by everything `closure` reads that
## changes per actor; models and equipment are the session's own (a new
## dictionary for either starts the memo again).
static var _memo: Dictionary = {}
static var _memo_models: Dictionary = {}
static var _memo_equipment: Dictionary = {}

## `closure`, remembered for the same inputs. Do not change what it returns.
static func memoized(dto: Dictionary, model_id: String, models: Dictionary,
		equipment_config: Dictionary, quality: int, mount_state: Dictionary = {},
		rl_head := false) -> Dictionary:
	if not is_same(models, _memo_models) or not is_same(equipment_config, _memo_equipment):
		_memo.clear()
		_memo_models = models
		_memo_equipment = equipment_config
	var appearance: Dictionary = dto.get("appearance", {}) as Dictionary
	var visuals: Dictionary = dto.get("equipment_visuals", {}) as Dictionary
	var mount := str(mount_state.get("mount_id", "")) if str(mount_state.get("mode", "")) == "mounted" else ""
	var key := [model_id, quality, int(dto.get("actor_type", -1)), mount, appearance, visuals, rl_head]
	var found: Variant = _memo.get(key)
	if found is Dictionary:
		return found as Dictionary
	var result := closure(dto, model_id, models, equipment_config, quality, mount_state, rl_head)
	if _memo.size() >= MEMO_CAPACITY:
		_memo.clear()
	# Own copies in the key: the record's dictionaries may change later.
	_memo[[model_id, quality, int(dto.get("actor_type", -1)), mount, appearance.duplicate(true),
		visuals.duplicate(true), rl_head]] = result
	return result

static func clear_memo() -> void:
	_memo.clear()
	_memo_models = {}
	_memo_equipment = {}
	_mount_memo.clear()
	_mount_memo_models = {}

## Mount closures by mount id, for the `models` they were computed from.
static var _mount_memo: Dictionary = {}
static var _mount_memo_models: Dictionary = {}

## AW-07: the actor glTF files a mount bind reads
## (MountedPlayerVisual.configure, through GlbSceneCache), in the closure's
## shape for ActorResourceWarmup.request_closure: the mount's own scene and
## the borrowed tack's source scene (BorrowedMountTack; the Moor Pony's saddle
## for most species). Both are read as whole scenes, never as pieces. A
## mount's animation library is its own scene file ("libraries" reports it):
## its clips are retargeted on main from that cached parse (about 1-3 ms
## headless), as for any creature. Empty (nothing to wait for) for a mount
## with no profile or no model, as the bind then draws no mount. Memoized per
## mount id for the same `models`. Main thread.
static func mount_closure(mount_id: String, models: Dictionary) -> Dictionary:
	if not is_same(models, _mount_memo_models):
		_mount_memo.clear()
		_mount_memo_models = models
	var found: Variant = _mount_memo.get(mount_id)
	if found is Dictionary:
		return found as Dictionary
	var scenes := PackedStringArray()
	var libraries := PackedStringArray()
	var result := {"model": mount_id, "creature": true, "scenes": scenes, "pieces": PackedStringArray(),
		"rl_files": PackedStringArray(), "libraries": libraries, "mount": mount_id, "key": ""}
	var config: Dictionary = models.get(mount_id, {}) as Dictionary
	if MountProfiles.supports(mount_id) and not config.is_empty():
		_add(scenes, str(config.get("scene", "")))
		_add(libraries, str(config.get("animationLibrary", "")))
		var tack: Dictionary = MountProfiles.read(mount_id).get("borrowedTack", {}) as Dictionary
		_add(scenes, str(tack.get("source", "")))
		result["key"] = "mount:%s#%s" % [mount_id, "|".join(scenes)]
	_mount_memo[mount_id] = result
	return result

## {model, creature, scenes, pieces, rl_files, libraries, mount, key} for
## `dto` at graphics `quality`, built from `models[model_id]`. "scenes" are the
## files to prepare, in the order a build reads them (race scene first), each
## once; "pieces" the subset read as equipment pieces; "key" a stable name of
## the set (scenes, pieces and RL files).
static func closure(dto: Dictionary, model_id: String, models: Dictionary,
		equipment_config: Dictionary, quality: int, mount_state: Dictionary = {},
		rl_head := false) -> Dictionary:
	var scenes := PackedStringArray()
	var pieces := PackedStringArray()
	var rl_files := PackedStringArray()
	var libraries := PackedStringArray()
	var model_config: Dictionary = models.get(model_id, {}) as Dictionary
	var scene := str(model_config.get("scene", ""))
	var creature := scene.begins_with(CREATURE_ROOT)
	var mount := ""
	if str(mount_state.get("mode", "")) == "mounted":
		mount = str(mount_state.get("mount_id", ""))
	var result := {"model": model_id, "creature": creature, "scenes": scenes, "pieces": pieces,
		"rl_files": rl_files, "libraries": libraries, "mount": mount, "key": ""}
	if model_config.is_empty() or bool(model_config.get("retired", false)) \
			or ArchivedModelPolicy.is_retired_actor_type(int(dto.get("actor_type", -1))):
		# configure() draws no body for these (and no fallback to prepare).
		return result
	var library := str(model_config.get("animationLibrary", ""))
	if not library.is_empty():
		libraries.append(library)
	if not scene.is_empty() and not creature:
		_add(scenes, scene)
		if scene == FemaleShirtNeckline.BODY:
			_add(scenes, FemaleShirtNeckline.REPAIRED)
	var appearance: Dictionary = dto.get("appearance", {}) as Dictionary
	# A portrait Human below High draws an RL hairstyle module instead of the
	# game hairstyle; elsewhere the game hairstyle is drawn.
	rl_files.append_array(ReplicatedActor3D.rl_hair_only_files_for(model_config, appearance, quality))
	var hair := ReplicatedActor3D.hair_scene_for(model_config,
		AppearanceVariants.hair_style(int(appearance.get("hair", 0))))
	if not hair.is_empty() and rl_files.is_empty():
		_add(scenes, hair)
		_add(pieces, hair)
	if rl_head:
		# The RL head the body draws at once at High (its game hairstyle above
		# stays listed: drawn where the RL head draws no module hair or fails).
		for path: String in ReplicatedActor3D.rl_head_files_for(model_config, appearance, quality):
			_add(rl_files, path)
	var parts: Dictionary = equipment_config.get("parts", {}) as Dictionary
	var visuals: Dictionary = dto.get("equipment_visuals", {}) as Dictionary
	for raw_part: Variant in visuals:
		var part := int(raw_part)
		var visual_id := int(visuals[raw_part])
		var part_config: Dictionary = parts.get(str(part), {}) as Dictionary
		if part_config.is_empty() or (visual_id == 0 and bool(part_config.get("bareWhenEmpty", false))):
			continue
		if ArchivedModelPolicy.is_retired_equipment(part, visual_id):
			continue
		var worn := ReplicatedActor3D.equipment_model_config_for(equipment_config, model_config,
			part, visual_id)
		if worn.is_empty() or bool(worn.get("retired", false)):
			continue
		if part == 0:
			var bow := ReplicatedActor3D.ranged_bow_path_for(worn)
			if not bow.is_empty():
				_add(scenes, RangerBow3D.ARROW_PATH)
				_add(scenes, RangerBow3D.DEFAULT_BOW)
				_add(scenes, bow)
		var worn_scene := str(worn.get("scene", ""))
		if worn_scene.is_empty() or bool(worn.get("wardrobeOnly", false)):
			continue
		_add(scenes, worn_scene)
		if str(worn.get("attach", "")) != "ranged_bow":
			_add(pieces, worn_scene)
	result["key"] = "%s#%s#%s" % ["|".join(scenes), "|".join(pieces), "|".join(rl_files)]
	return result

static func _add(list: PackedStringArray, path: String) -> void:
	if not path.is_empty() and not list.has(path):
		list.append(path)

extends RefCounted
## An interior's placed scenery (underground_scenery.gd), laid in slices a
## frame can afford.
##
## A preloader (WorldPark) publishes a whole interior that its worker built
## off the tree. Scenery instances are main-thread work (GlbSceneCache installs
## and instantiates on Main only), so they are added here, a few milliseconds
## at a time, to the root while it is still off the tree, where adding a node
## registers nothing with the renderer or physics. The result is the tree
## `UndergroundScenery.apply` builds, placement for placement.
##
## `step(budget_usec)` returns true once every placement stands; a budget of 0
## finishes in one call (a map change that cannot wait for the slices). The
## prepared visuals the worker built are installed one asset per pass first,
## so the placement loop finds every asset in the cache; an asset the worker
## did not prepare is built here, also one per pass.
const UndergroundScenery := preload("res://src/world/underground_scenery.gd")
const MaterialOwnership := preload("res://src/world/prepared_material_ownership.gd")

const STAGE_STYLE := 0
const STAGE_INSTALL := 1
const STAGE_PREPARE := 2
const STAGE_PLACE := 3
const STAGE_DONE := 4

var map_id := ""
var world: Node3D
var data: Dictionary = {}
var count := 0
var failed := 0
## Microseconds of the longest single slice, of all slices together, and how
## many slices it took.
var max_slice_usec := 0
var total_usec := 0
var slices := 0
var _visuals: Dictionary = {}
var _visual_keys: Array = []
var _paths := PackedStringArray()
var _index := 0
var _stage := STAGE_STYLE
var _scenery: Node3D

## `prepared_visuals` is a worker's GlbSceneCache.prepare result (path ->
## prepared scene); `config` stands in for the map's config file (tests).
func _init(identity: String, root: Node3D, prepared_visuals: Dictionary = {},
		config: Dictionary = {}) -> void:
	map_id = identity
	world = root
	_visuals = prepared_visuals
	_visual_keys = prepared_visuals.keys()
	data = config

func done() -> bool:
	return _stage >= STAGE_DONE

## Placements still to lay (diagnostics; 0 before the config is read).
func remaining() -> int:
	return maxi(0, (data.get("placements", []) as Array).size() - _index) if not done() else 0

## Lays the next slice. True when every placement stands, or when there is
## nothing to lay: no config, a root already dressed, a freed root.
func step(budget_usec: int) -> bool:
	if done():
		return true
	if not is_instance_valid(world):
		_stage = STAGE_DONE
		return true
	var began := Time.get_ticks_usec()
	var unlimited := budget_usec <= 0
	while not done() and (unlimited or Time.get_ticks_usec() - began < budget_usec):
		if _stage == STAGE_STYLE:
			if world.has_node(UndergroundScenery.NODE_NAME):
				_stage = STAGE_DONE
				break
			if data.is_empty():
				data = UndergroundScenery.config_for(map_id)
			if data.is_empty():
				_stage = STAGE_DONE
				break
			var surfaces: Variant = data.get("surfaces", {})
			UndergroundScenery.style_surfaces(world, surfaces if surfaces is Dictionary else {},
				UndergroundScenery.floor_default(map_id, data))
			# As WorldLoader._materialize_geometry_world does after styling a
			# native (geometry-cache) shell: hold the materials just replaced.
			# Nothing to hold on a raw shell.
			MaterialOwnership.refresh(world)
			# As GlbSceneCache keys them (absolute), so a missing one is found again.
			_paths = PackedStringArray()
			for source: String in UndergroundScenery.asset_paths(map_id, data):
				_paths.append(ProjectSettings.globalize_path(source) if source.begins_with("res://") else source)
			_stage = STAGE_INSTALL
		elif _stage == STAGE_INSTALL:
			# The worker's prepared scenes, one asset per pass: each install
			# revalidates its source before publishing it to the cache.
			if _visual_keys.is_empty():
				_visuals = {}
				_stage = STAGE_PREPARE
				continue
			var key: Variant = _visual_keys.pop_back()
			var one := {}
			one[key] = _visuals[key]
			GlbSceneCache.install_prepared(one)
			_visuals.erase(key)
		elif _stage == STAGE_PREPARE:
			var missing := GlbSceneCache.missing(_paths)
			if missing.is_empty():
				_scenery = Node3D.new()
				_scenery.name = UndergroundScenery.NODE_NAME
				world.add_child(_scenery)
				_stage = STAGE_PLACE
				continue
			var path := missing[0]
			var single := PackedStringArray([path])
			if not GlbSceneCache.prepare_bound_main(single):
				GlbSceneCache.install_prepared(GlbSceneCache.prepare(single))
			if not GlbSceneCache.missing(single).is_empty():
				# Not buildable here either; the placement loop warns about it.
				var at := _paths.find(path)
				if at < 0:
					_paths = PackedStringArray() # Unknown key form: stop asking, place what is there.
				else:
					_paths.remove_at(at)
		elif _stage == STAGE_PLACE:
			var placements: Array = data.get("placements", [])
			if _index >= placements.size():
				_stage = STAGE_DONE
				break
			var placement: Dictionary = placements[_index]
			_index += 1
			var path := str((data.get("assets", {}) as Dictionary).get(placement.get("asset", ""), ""))
			var model: Node3D = GlbSceneCache.instantiate(path) if not path.is_empty() else null
			if model == null:
				failed += 1
				push_warning("Interior scenery failed to import: " + path)
				continue
			UndergroundScenery.dress(model, placement, count)
			_scenery.add_child(model)
			count += 1
	var spent := Time.get_ticks_usec() - began
	max_slice_usec = maxi(max_slice_usec, spent)
	total_usec += spent
	slices += 1
	return done()

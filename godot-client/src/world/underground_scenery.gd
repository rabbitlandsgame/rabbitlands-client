extends RefCounted
## Reviewed imported scenery is applied after the map cache snapshot. Keeping
## it outside the packed map also lets an older map cache receive updated art.
##
## One config per interior map (tools/prepare_underground_scenery.py writes
## them all in the same schema): the Landfall underground's caves and the
## Landfall town's rooms. A map with no row here has no placed scenery.
const CONFIGS := {
	"landfall_insides": {"config": "res://data/world/underground-scenery.json",
		# Every cave names its floor; a Walk_ mesh no section claims is earth.
		"floorDefault": "packed_earth"},
	"landfall_town": {"config": "res://data/world/town-scenery.json",
		# A room's floor is the shell's own textured planks, flags or tiles:
		# a section the config does not style keeps them.
		"floorDefault": "authored"},
}
## The underground's config, as it was before the table. Kept for callers that
## read the file directly (tests/integration/landfall_underground.gd).
const CONFIG := "res://data/world/underground-scenery.json"
## The node every placement stands under, on every interior: the loader's and
## the preloader's "already applied" guard, and the tests' handle.
const NODE_NAME := "UndergroundScenery"
const MineralAppearance := preload("res://src/world/mineral_appearance.gd")
const CENOTE_WATER := preload("res://src/world/cenote_water.gdshader")
const DAYLIGHT_SHAFT := preload("res://src/world/daylight_shaft.gdshader")

## The config file for `map_id` (res:// path), or "" for a map with none.
static func config_path(map_id: String) -> String:
	var row: Variant = CONFIGS.get(map_id)
	return str((row as Dictionary).get("config", "")) if row is Dictionary else ""

## Whether `map_id` places imported scenery: it has a config row and the
## config is on disk (an interior whose scenery is not packaged yet has none).
static func applies_to(map_id: String) -> bool:
	var path := config_path(map_id)
	return not path.is_empty() and FileAccess.file_exists(path)

## `map_id`'s parsed config, or {} when it has none or the file names another
## map (a config is only ever read for the map it was written for).
static func config_for(map_id: String) -> Dictionary:
	var path := config_path(map_id)
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if data is not Dictionary or str((data as Dictionary).get("map", "")) != map_id:
		return {}
	return data as Dictionary

## Every distinct model `map_id`'s placements stand, as the paths
## GlbSceneCache is asked for (a preloader prepares them on its worker).
static func asset_paths(map_id: String, data: Dictionary = {}) -> PackedStringArray:
	if data.is_empty():
		data = config_for(map_id)
	var paths := PackedStringArray()
	var assets: Dictionary = data.get("assets", {}) if data.get("assets") is Dictionary else {}
	for placement: Variant in data.get("placements", []) as Array:
		if placement is not Dictionary:
			continue
		var source := str(assets.get((placement as Dictionary).get("asset", ""), ""))
		if not source.is_empty() and not paths.has(source):
			paths.append(source)
	return paths

## How the underground presents its seam and pan nodes, by object id (as a
## string): {resource, variant, yaw}, the config's `harvestPresentation`
## (tools/prepare_underground_scenery.py). The underground package states no
## harvest presentation, so `Main.map_presentation_of` takes these in its
## place. Empty for any other map.
##
## Pass 2 (2026-10-21): a vein node's entry is a `wall` placement,
## {resource, placement: "wall", variant, yaw, inset}: MapObject3D stands the
## label's wall seam (objects.json harvestables.wallVariants) set into the rock
## face, its +Z turned out of the rock by `yaw` and moved `inset` metres back
## from the tile's centre to the face (build_underground.vein_faces).
static func harvest_presentation(map_id: String) -> Dictionary:
	var data := config_for(map_id)
	var listed: Variant = data.get("harvestPresentation", {})
	return listed if listed is Dictionary else {}

static func apply(manifest: WorldManifest, world: Node3D, diagnostics: Dictionary = {}) -> int:
	if manifest == null or world == null or not applies_to(manifest.asset_id()):
		return 0
	if world.has_node(NODE_NAME):
		return 0
	var detailed := OS.get_environment("ELORIA_UNDERGROUND_DIAGNOSTICS") == "1"
	var mark := Time.get_ticks_usec() if detailed else 0
	var data := config_for(manifest.asset_id())
	if data.is_empty():
		return 0
	if detailed:
		diagnostics[&"undergroundConfig"] = Time.get_ticks_usec()-mark
		mark = Time.get_ticks_usec()
	var surfaces: Variant = data.get("surfaces", {})
	style_surfaces(world, surfaces if surfaces is Dictionary else {}, floor_default(manifest.asset_id(), data))
	if detailed:
		diagnostics[&"undergroundStyle"] = Time.get_ticks_usec()-mark
		mark = Time.get_ticks_usec()
	var paths := asset_paths(manifest.asset_id(), data)
	if detailed:
		diagnostics[&"undergroundPaths"] = Time.get_ticks_usec()-mark
		mark = Time.get_ticks_usec()
	# Parsed once a session and shared with the harvest nodes that stand the
	# same files (crystal_cluster): only paths the cache lacks are built.
	if GlbSceneCache.prepare_bound_main(paths):
		# Combined decode/install/texture binding: one asset's CPU Images retire
		# before decoding the next. The placement loop below remains unchanged.
		if detailed: diagnostics[&"undergroundPrepareBound"] = Time.get_ticks_usec()-mark
	else:
		var prepared := GlbSceneCache.prepare(GlbSceneCache.missing(paths))
		if detailed:
			diagnostics[&"undergroundPrepare"] = Time.get_ticks_usec()-mark
			mark = Time.get_ticks_usec()
		GlbSceneCache.install_prepared(prepared)
		prepared.clear()
		if detailed: diagnostics[&"undergroundInstall"] = Time.get_ticks_usec()-mark
	var scenery := Node3D.new()
	scenery.name = NODE_NAME
	world.add_child(scenery)
	var count := 0
	var instantiate_us := 0
	var palette_us := 0
	var attach_us := 0
	var loop_began := Time.get_ticks_usec() if detailed else 0
	for placement: Dictionary in data.placements:
		var path := str(data.assets[placement.asset])
		if detailed: mark = Time.get_ticks_usec()
		var model := GlbSceneCache.instantiate(path)
		if detailed: instantiate_us += Time.get_ticks_usec()-mark
		if model == null:
			push_warning("Underground scenery failed to import: " + path)
			continue
		if detailed: mark = Time.get_ticks_usec()
		dress(model, placement, count)
		if detailed: palette_us += Time.get_ticks_usec()-mark
		if detailed: mark = Time.get_ticks_usec()
		scenery.add_child(model)
		if detailed: attach_us += Time.get_ticks_usec()-mark
		count += 1
	if detailed:
		diagnostics.merge({&"undergroundPlacementLoop":Time.get_ticks_usec()-loop_began,
			&"undergroundInstantiate":instantiate_us,&"undergroundPalette":palette_us,
			&"undergroundAttach":attach_us,&"undergroundPlacements":count,&"undergroundAssets":paths.size()},true)
	return count

## One placement's transform, palette and cutaway metadata, on a model just
## instantiated from its asset (shared by `apply` and InteriorSceneryStepper).
static func dress(model: Node3D, placement: Dictionary, count: int) -> void:
	model.name = str(placement.asset) + "_" + str(count)
	var p: Array = placement.position
	model.position = Vector3(p[0], p[1], p[2])
	model.rotation.y = deg_to_rad(float(placement.get("yaw", 0.0)))
	model.scale *= float(placement.get("scale", 1.0))
	# A town prop drawn left for right (the source's `mirror`): one model in a
	# row of its kind need not repeat its own layout. The renderer flips the
	# face winding of a mirrored instance itself.
	if placement.get("mirror", false) == true:
		model.scale.x = -model.scale.x
	if placement.asset == "mine_rail":
		model.scale.y = .1 # Thin floor dressing, clear of character feet.
	if placement.has("palette"):
		MineralAppearance.apply(model, placement.palette)
	# A rock set into a wall carries the wall's outward direction: the
	# manifest's cutaway drops it near the player while that wall faces the
	# camera (InteriorCutaway props), and OccluderFade fades any other that
	# comes between the camera and the player.
	var outward: Variant = placement.get("outward")
	if outward is Array and (outward as Array).size() >= 3:
		model.set_meta("cutaway_outward", Vector3(outward[0], outward[1], outward[2]))
	# A piece of furniture stood against a room's wall (the town's `wall`
	# props) names that wall's cutaway node: it drops exactly when its wall
	# does (InteriorCutaway.WALL_PROP_META), wherever the player stands.
	var wall := str(placement.get("cutawayWall", ""))
	if not wall.is_empty():
		model.set_meta("cutaway_wall", wall)

## The floor class a Walk_ mesh takes when its section's `surfaces` name none:
## the config's own `floorDefault`, else the map's row (CONFIGS).
static func floor_default(map_id: String, data: Dictionary) -> String:
	if data.has("floorDefault"):
		return str(data.floorDefault)
	var row: Variant = CONFIGS.get(map_id)
	return str((row as Dictionary).get("floorDefault", "packed_earth")) if row is Dictionary else "packed_earth"

## The styling of the section a shell mesh belongs to: `<prefix><section>_...`
## (the builder names Walk_, Build_ and Water_ meshes by section), from the
## config's `surfaces` (build_underground.THEMES via the packager). The longest
## matching section id wins; an unknown section styles as an empty dictionary.
static func section_surfaces(mesh_name: String, prefix: String, surfaces: Dictionary) -> Dictionary:
	var best := ""
	for section: Variant in surfaces:
		var id := str(section)
		if mesh_name.begins_with(prefix + id + "_") and id.length() > best.length():
			best = id
	if best.is_empty() or surfaces[best] is not Dictionary:
		return {}
	return surfaces[best]

static func _colour(value: Variant, fallback: Color) -> Color:
	if value is Array and (value as Array).size() >= 3:
		var parts: Array = value
		return Color(float(parts[0]), float(parts[1]), float(parts[2]))
	return fallback

static func _vector(colour: Color) -> Vector3:
	return Vector3(colour.r, colour.g, colour.b)

## Each section's shell is styled as its theme says (`surfaces`): its floor by
## a class texture and tint, its rock face lifted toward its wall rocks'
## colour, its pools in the shared water shader with the theme's tint, and its
## daylight shafts as added light. A floor no section styles takes
## `fallback_floor`: a class texture (the caves' packed earth), or "authored",
## which leaves the shell's own material untouched (the town's rooms).
static func style_surfaces(world: Node3D, surfaces: Dictionary, fallback_floor := "packed_earth") -> void:
	for mesh: MeshInstance3D in world.find_children("*", "MeshInstance3D", true, false):
		var id := str(mesh.name)
		# Replace the old crystal cones and untextured lamp stand-ins with the
		# imported pieces; retain structural beams, walls and stone burial beds.
		if id.begins_with("Props_") and (id.ends_with("_cave_crystal")
			or id.ends_with("_lamp_glow") or id.ends_with("_dark_iron")):
			mesh.visible = false
		if id.begins_with("Water_"):
			var water := ShaderMaterial.new()
			water.shader = CENOTE_WATER
			var tint: Variant = section_surfaces(id, "Water_", surfaces).get("water")
			if tint is Dictionary:
				# Unset colours keep the shader's (the Cenote Deeps') defaults;
				# the ripple highlight follows the clear colour unless stated.
				var given: Dictionary = tint
				for key: String in ["deep", "clear", "ripple", "glow"]:
					if given.has(key):
						water.set_shader_parameter(key + "_colour", _vector(_colour(given[key], Color.BLACK)))
				if given.has("clear") and not given.has("ripple"):
					water.set_shader_parameter("ripple_colour", _vector(_colour(given.clear, Color.BLACK)) * .075)
			mesh.material_override = water
			continue
		if id.begins_with("Shaft_"):
			var shaft := ShaderMaterial.new()
			shaft.shader = DAYLIGHT_SHAFT
			mesh.material_override = shaft
			continue
		if id.begins_with("Build_"):
			# A cave's rock face sits behind its kit wall rocks: lift its dark
			# cliff texture toward their colour so it reads as the same stone in
			# shadow, not a black sheet (the Cenote Deeps: toward the crags' cream).
			var lift: Variant = section_surfaces(id, "Build_", surfaces).get("rockLift")
			if lift is Array and (lift as Array).size() >= 3:
				var face := mesh.get_active_material(0) as StandardMaterial3D
				# Only a textured face is lifted: an untextured one (a passage
				# mouth's dark way on, pass 2) is its colour, and stays dark.
				if face != null and face.albedo_texture != null:
					face = face.duplicate() as StandardMaterial3D
					face.albedo_color = _colour(lift, Color.WHITE)
					mesh.material_override = face
			continue
		if not id.begins_with("Walk_"):
			continue
		var ground: Variant = section_surfaces(id, "Walk_", surfaces).get("floor", {})
		var floor_style: Dictionary = ground if ground is Dictionary else {}
		var texture := str(floor_style.get("texture", fallback_floor))
		if texture == "authored":
			# The shell's own floor material (the theme's `floor`, e.g. the ice
			# caves' packed snow), tinted: a floor no class texture stands in for.
			var own := mesh.get_active_material(0) as StandardMaterial3D
			if fallback_floor == "authored":
				# A room's planks, flags or tiles are the art: tinted only when its
				# section says so, otherwise left exactly as the shell drew them.
				var tint := _colour(floor_style.get("tint"), Color.WHITE)
				if own != null and not tint.is_equal_approx(Color.WHITE):
					own = own.duplicate() as StandardMaterial3D
					own.albedo_color = tint
					mesh.material_override = own
				continue
			if own != null:
				own = own.duplicate() as StandardMaterial3D
				own.albedo_color = _colour(floor_style.get("tint"), Color.WHITE)
				mesh.material_override = own
				continue
		var material := StandardMaterial3D.new()
		# With mipmaps even where a fresh checkout imported the PNG without.
		material.albedo_texture = LookGround.class_texture(texture)
		material.albedo_color = _colour(floor_style.get("tint"), Color(.65, .65, .65))
		material.roughness = 1
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		mesh.material_override = material

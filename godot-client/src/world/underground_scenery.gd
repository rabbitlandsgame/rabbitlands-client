extends RefCounted
## Reviewed imported scenery is applied after the map cache snapshot. Keeping
## it outside the packed map also lets an older map cache receive updated art.
const CONFIG := "res://data/world/underground-scenery.json"
const MineralAppearance := preload("res://src/world/mineral_appearance.gd")
const CENOTE_WATER := preload("res://src/world/cenote_water.gdshader")
const DAYLIGHT_SHAFT := preload("res://src/world/daylight_shaft.gdshader")

## How the underground presents its seam and pan nodes, by object id (as a
## string): {resource, variant, yaw}, the config's `harvestPresentation`
## (tools/prepare_underground_scenery.py). The underground package states no
## harvest presentation, so `Main.map_presentation_of` takes these in its
## place. Empty for any other map.
static func harvest_presentation(map_id: String) -> Dictionary:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(CONFIG))
	if data is not Dictionary or str((data as Dictionary).get("map", "")) != map_id:
		return {}
	var listed: Variant = (data as Dictionary).get("harvestPresentation", {})
	return listed if listed is Dictionary else {}

static func apply(manifest: WorldManifest, world: Node3D) -> int:
	if manifest.asset_id() != "landfall_insides":
		return 0
	if world.has_node("UndergroundScenery"):
		return 0
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CONFIG))
	var surfaces: Variant = data.get("surfaces", {})
	_style_surfaces(world, surfaces if surfaces is Dictionary else {})
	var paths := PackedStringArray()
	for placement: Dictionary in data.placements:
		var source := str(data.assets[placement.asset])
		if not paths.has(source): paths.append(source)
	# Parsed once a session and shared with the harvest nodes that stand the
	# same files (crystal_cluster): only paths the cache lacks are built.
	GlbSceneCache.install_prepared(GlbSceneCache.prepare(GlbSceneCache.missing(paths)))
	var scenery := Node3D.new()
	scenery.name = "UndergroundScenery"
	world.add_child(scenery)
	var count := 0
	for placement: Dictionary in data.placements:
		var path := str(data.assets[placement.asset])
		var model := GlbSceneCache.instantiate(path)
		if model == null:
			push_warning("Underground scenery failed to import: " + path)
			continue
		model.name = str(placement.asset) + "_" + str(count)
		var p: Array = placement.position
		model.position = Vector3(p[0], p[1], p[2])
		model.rotation.y = deg_to_rad(float(placement.get("yaw", 0.0)))
		model.scale *= float(placement.get("scale", 1.0))
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
		scenery.add_child(model)
		count += 1
	return count

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
## daylight shafts as added light.
static func _style_surfaces(world: Node3D, surfaces: Dictionary) -> void:
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
				if face != null:
					face = face.duplicate() as StandardMaterial3D
					face.albedo_color = _colour(lift, Color.WHITE)
					mesh.material_override = face
			continue
		if not id.begins_with("Walk_"):
			continue
		var ground: Variant = section_surfaces(id, "Walk_", surfaces).get("floor", {})
		var floor_style: Dictionary = ground if ground is Dictionary else {}
		if str(floor_style.get("texture", "")) == "authored":
			# The shell's own floor material (the theme's `floor`, e.g. the ice
			# caves' packed snow), tinted: a floor no class texture stands in for.
			var own := mesh.get_active_material(0) as StandardMaterial3D
			if own != null:
				own = own.duplicate() as StandardMaterial3D
				own.albedo_color = _colour(floor_style.get("tint"), Color.WHITE)
				mesh.material_override = own
				continue
		var material := StandardMaterial3D.new()
		# With mipmaps even where a fresh checkout imported the PNG without.
		material.albedo_texture = LookGround.class_texture(str(floor_style.get("texture", "packed_earth")))
		material.albedo_color = _colour(floor_style.get("tint"), Color(.65, .65, .65))
		material.roughness = 1
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		mesh.material_override = material

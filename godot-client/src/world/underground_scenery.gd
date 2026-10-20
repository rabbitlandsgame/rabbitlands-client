extends RefCounted
## Reviewed imported scenery is applied after the map cache snapshot. Keeping
## it outside the packed map also lets an older map cache receive updated art.
const CONFIG := "res://data/world/underground-scenery.json"
const MineralAppearance := preload("res://src/world/mineral_appearance.gd")
const CENOTE_WATER := preload("res://src/world/cenote_water.gdshader")
const DAYLIGHT_SHAFT := preload("res://src/world/daylight_shaft.gdshader")

static func apply(manifest: WorldManifest, world: Node3D) -> int:
	if manifest.asset_id() != "landfall_insides":
		return 0
	if world.has_node("UndergroundScenery"):
		return 0
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CONFIG))
	_style_surfaces(world)
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
		# The Cenote Deeps' wall rocks stay up when the camera turns: each one
		# that comes between the camera and the player fades (OccluderFade).
		scenery.add_child(model)
		count += 1
	return count

static func _style_surfaces(world: Node3D) -> void:
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
			mesh.material_override = water
			continue
		if id.begins_with("Shaft_"):
			var shaft := ShaderMaterial.new()
			shaft.shader = DAYLIGHT_SHAFT
			mesh.material_override = shaft
			continue
		if id.begins_with("Build_spindle_cavern"):
			# The cenote's rock face sits behind pale Meshy limestone crags:
			# lift its dark cliff texture toward their cream so it reads as the
			# same stone in shadow, not a black sheet.
			var face := mesh.get_active_material(0) as StandardMaterial3D
			if face != null:
				face = face.duplicate() as StandardMaterial3D
				face.albedo_color = Color(2.1, 2.0, 1.75)
				mesh.material_override = face
			continue
		if not id.begins_with("Walk_"):
			continue
		var texture := "packed_earth"
		var tint := Color(.65,.65,.65)
		if id.contains("boarsend_barrow"): texture = "flagstone"
		elif id.contains("spindle_cavern"):
			# The Cenote Deeps: wet limestone gravel, greened by the moss.
			texture = "coastal_gravel"
			tint = Color(.58,.66,.54)
		var material := StandardMaterial3D.new()
		# With mipmaps even where a fresh checkout imported the PNG without.
		material.albedo_texture = LookGround.class_texture(texture)
		material.albedo_color = tint
		material.roughness = 1
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		mesh.material_override = material

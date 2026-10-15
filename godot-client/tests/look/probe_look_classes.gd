extends "res://tests/look/probe_materials.gd"
## Look-migration inventory: what the look pass's generic classifier does with
## every map, so a region's owner knows what its region file has to add.
##
## Loads each target map as probe_materials.gd does (the complete client, a
## local actor at the target, every selected chunk resident), with the look ON
## as the client runs it, and writes one JSON file (ELORIA_INVENTORY_OUT, else
## ELORIA_ARTIFACT_DIR/inventory_look.json). Per map:
##   look       the region id and whether a region file exists; whether the
##              map was graded, its sky painted, its sea decoded
##   ground     every ground surface (LookGround.kind_of) by material: what it
##              was painted as (terrain / biome verge / patch: paving, cobble or
##              glaze / road deck) or why it was left alone (a water shader, a
##              bridge's timber, an invisible threshold, a batched mesh, a
##              material override, a transparency mode the paint does not
##              reproduce); and ground-looking meshes the classifier does not
##              recognise at all
##   grass      the biome blends' layer textures and how grassy each counts
##              (the region's words, then GRASS_LAYER_WORDS, else the default),
##              and the grass beds' placement census around the target
##   foliage    every foliage-looking mesh (probe_materials' word lists) by
##              pattern: painted as an authored crown, a kit tree or a kit
##              shrub, or not painted and why (no crown material or kit word,
##              or a material the painted crown cannot reproduce)
##   roads      points on painted road decks (vertex coverage >= 0.9) near the
##              target, in the survey's frame, for choosing survey shots
## It edits nothing.
##
## Targets: ELORIA_PROBE_TARGETS, a JSON list [{map, x, z}], else
## probe_materials.gd's three pilot maps. Run:
##   Godot --audio-driver Dummy --path godot-client
##     --script res://tests/look/probe_look_classes.gd
## with ELORIA_NO_MAP_CACHE=1 so the chunks import fresh, as the survey renders.

const ROAD_POINTS := 80
const ROAD_POINT_SPACING := 6.0

func _run() -> void:
	# A script error inside a coroutine stops it without quitting; never hang.
	var budget := OS.get_environment("ELORIA_PROBE_TIMEOUT_S")
	create_timer(float(budget) if budget.is_valid_float() else 1800.0).timeout.connect(
		func() -> void:
			push_error("PROBE timed out")
			quit(3))
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	var targets: Array = TARGETS
	var targets_path := OS.get_environment("ELORIA_PROBE_TARGETS")
	if not targets_path.is_empty():
		targets = JSON.parse_string(FileAccess.get_file_as_string(targets_path))
	report.look_enabled = LookProfile.enabled()
	report.rendering_method = RenderingServer.get_current_rendering_method()
	for target: Dictionary in targets:
		var started := Time.get_ticks_msec()
		if not await _load(target):
			report.maps[target.map] = {"error": "failed to load"}
			continue
		var census := await _grass_census()
		var loader: WorldLoader = main.get("world_loader")
		var entry := _look_inventory(loader, target)
		entry.grass.census = census
		entry.summary = _summary(entry)
		entry.load_msec = Time.get_ticks_msec() - started
		report.maps[target.map] = entry
		print("PROBE looked at ", target.map, " (", entry.summary, ")")
	var out := OS.get_environment("ELORIA_INVENTORY_OUT")
	if out.is_empty():
		out = OS.get_environment("ELORIA_ARTIFACT_DIR").path_join("inventory_look.json")
	var file := FileAccess.open(out, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, " "))
	file.close()
	print("PROBE wrote ", out)
	main.call("_on_disconnect_pressed")
	main.get("exterior_stream").clear()
	while not main.get("exterior_stream").is_idle():
		await process_frame
	for i in 6:
		await process_frame
	main.queue_free()
	await process_frame
	quit()

## What the grass beds grew round the target once their build has finished
## (or after eight seconds): tufts per variant (verge, bed, tall). The build's
## own census by ground class is printed as `look_grass stage=built` with
## ELORIA_LOOK_GRASS_DEBUG=1, which probe runners read from the log.
func _grass_census() -> Dictionary:
	var deadline := Time.get_ticks_msec() + 8000
	var beds: LookGrassBeds = null
	while Time.get_ticks_msec() < deadline:
		beds = main.find_child(LookGrassBeds.NODE_NAME, true, false) as LookGrassBeds
		if beds != null and beds._built_once and beds._queue.is_empty():
			break
		await process_frame
	if beds == null:
		return {"grown": false}
	var counts := beds.tuft_counts()
	return {"grown": beds.visible, "built": beds._built_once,
		"tufts": counts[0] + counts[1] + counts[2] if counts.size() == 3 else 0,
		"verge": counts[0] if counts.size() > 0 else 0,
		"bed": counts[1] if counts.size() > 1 else 0,
		"tall": counts[2] if counts.size() > 2 else 0}

func _look_inventory(loader: WorldLoader, target: Dictionary) -> Dictionary:
	var world_root := loader.world_root
	var manifest := loader.manifest
	var region := LookGround.region_of(manifest)
	var roots: Array[Node] = [world_root]
	var residents: Dictionary = main.get("exterior_stream").residents
	for map_id: Variant in residents:
		var resident: Variant = residents[map_id]
		var neighbour: Node = (resident as Dictionary).get("root") as Node \
			if resident is Dictionary else null
		if is_instance_valid(neighbour) and neighbour != world_root:
			roots.append(neighbour)
	var ground := {}
	var unrecognised := {}
	var foliage := {}
	var biome_layers := {}
	var water := {}
	var road_points: Array = []
	var words := LookFoliage.words_for(region)
	var focus := Vector2(float(target.x), float(target.z))
	for scan: Node in roots:
		var scan_region := region if scan == world_root else _root_region(scan, residents)
		for node: Node in scan.find_children("*", "MeshInstance3D", true, false):
			var mesh_instance := node as MeshInstance3D
			if mesh_instance.mesh == null:
				continue
			var node_name := LookFoliage._plain_name(String(mesh_instance.name))
			var kind := LookGround.kind_of(node_name)
			var own := scan == world_root
			if kind != LookGround.Kind.NONE:
				for surface: int in mesh_instance.mesh.get_surface_count():
					var row := _ground_row(mesh_instance, surface, kind, scan_region)
					_tally(ground, "%s|%s|%s" % [row.region, row["class"], row.material], row, node_name)
					if row.biome_textures is Array:
						for texture: Dictionary in row.biome_textures:
							biome_layers["%s|%s" % [row.region, texture.file]] = texture
				if own and kind == LookGround.Kind.DECK:
					_road_points(mesh_instance, node_name, road_points)
				continue
			var names := _material_names(_surfaces_of(mesh_instance))
			var tokens := _tokens(node_name + " " + " ".join(names))
			if _is_water(node_name, mesh_instance):
				var water_row := _water_row(mesh_instance)
				_tally(water, "%s|%s" % [scan_region, water_row.material], water_row, node_name)
				continue
			if _is_ground(mesh_instance, _surfaces_of(mesh_instance), names):
				_tally(unrecognised, "%s|%s" % [scan_region, ",".join(names)],
					{"region": scan_region, "materials": names}, node_name)
				continue
			var looks_like_foliage := (_any(tokens, FOLIAGE_WORDS) or (_any(tokens, TRUNK_WORDS)
				and _any(tokens, CROWN_WORDS))) and not _any(tokens, NOT_FOLIAGE)
			var painted := _foliage_painted(mesh_instance)
			if not looks_like_foliage and not painted:
				continue
			var foliage_row := _foliage_row(mesh_instance, node_name,
				words if own else LookFoliage.words_for(scan_region), scan_region,
				manifest.data.has("continentGeography"))
			_tally(foliage, "%s|%s|%s" % [scan_region, _pattern(node_name), ",".join(names)],
				foliage_row, node_name)
	var environment: Environment = (main.get("world_environment") as WorldEnvironment).environment
	var sky_painted := environment != null and environment.sky != null \
		and environment.sky.sky_material is ShaderMaterial \
		and (environment.sky.sky_material as ShaderMaterial).shader == LookSky.SHADER
	var declared: Variant = manifest.data.get("environment", {})
	var declared_sky: bool = declared is Dictionary and (declared as Dictionary).has("sky")
	var graded := environment != null and environment.adjustment_enabled \
		and environment.tonemap_mode == Environment.TONE_MAPPER_AGX
	road_points.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return focus.distance_to(Vector2(a.x, a.z)) < focus.distance_to(Vector2(b.x, b.z)))
	var spread: Array = []
	for point: Dictionary in road_points:
		var far_enough := true
		for kept: Dictionary in spread:
			far_enough = far_enough and Vector2(point.x, point.z).distance_to(
				Vector2(kept.x, kept.z)) >= ROAD_POINT_SPACING
		if far_enough:
			point.distance = snappedf(focus.distance_to(Vector2(point.x, point.z)), 0.1)
			spread.append(point)
		if spread.size() >= ROAD_POINTS:
			break
	var ground_rows := _rows(ground)
	var foliage_rows := _rows(foliage)
	var entry := {"manifest": manifest.source_path, "target": [target.x, target.z],
		"look": {"region": region, "region_file": LookProfile.region_path(region),
			"region_file_exists": FileAccess.file_exists(LookProfile.region_path(region)),
			"continent": manifest.data.has("continentGeography"),
			"outdoor_sun": LookGround.outdoor(manifest), "graded": graded,
			"sky_painted": sky_painted, "declares_sky": declared_sky,
			"sky_fallback": {"top": "#" + (LookProfile.sky_fallback(region).top as Color).to_html(false),
				"horizon": "#" + (LookProfile.sky_fallback(region).horizon as Color).to_html(false)}
				if not declared_sky else null,
			"neighbours": residents.keys()},
		"ground": ground_rows, "ground_unrecognised": _rows(unrecognised),
		"grass": {"layers": biome_layers.values()},
		"foliage": foliage_rows, "water": _rows(water), "roads": spread,
		"environment_bound": _environment()}
	return entry

## The region a resident neighbour or chunk root reads its file as.
func _root_region(scan: Node, residents: Dictionary) -> String:
	for map_id: Variant in residents:
		var resident: Variant = residents[map_id]
		if resident is Dictionary and (resident as Dictionary).get("root") == scan:
			return String(map_id).get_slice("__chunk_", 0)
	return ""

func _surfaces_of(mesh_instance: MeshInstance3D) -> Array:
	var surfaces: Array = []
	for surface: int in mesh_instance.mesh.get_surface_count():
		surfaces.append(_source_material(mesh_instance, surface))
	return surfaces

## The material the loader gave a surface, under any look paint.
func _source_material(mesh_instance: MeshInstance3D, surface: int) -> Material:
	var active := mesh_instance.get_active_material(surface)
	if active != null and (active.has_meta(LookGround.PAINTED_META)
			or active.has_meta(LookFoliage.PAINTED_META)):
		var own := mesh_instance.mesh.surface_get_material(surface)
		return own if own != null else active
	return active

## One ground surface: what the look painted it as, or why it did not.
func _ground_row(mesh_instance: MeshInstance3D, surface: int, kind: LookGround.Kind,
		region: String) -> Dictionary:
	var active := mesh_instance.get_active_material(surface)
	var source := _source_material(mesh_instance, surface)
	var row := {"region": region, "kind": ["terrain", "biome", "patch", "deck"][int(kind)],
		"material": source.resource_name if source != null else "",
		"biome_textures": null}
	var painted := active != null and active.has_meta(LookGround.PAINTED_META) \
		and active is ShaderMaterial
	if painted:
		var shader_material := active as ShaderMaterial
		var look_class := int(_param(shader_material, &"look_class", -1))
		var label: String = ["terrain", "biome verge", "patch", "road deck"][clampi(look_class, 0, 3)]
		if look_class == int(LookGround.Kind.PATCH):
			if shader_material.get_shader_parameter(&"look_rim") == LookProfile.PAVING_RIM:
				label = "patch: pale paving"
			elif float(_param(shader_material, &"look_opacity", 0.0)) >= 1.0:
				label = "patch: worn cobble (solid)"
			else:
				label = "patch: glaze (yard, litter, soil)"
		if look_class == int(LookGround.Kind.TERRAIN) \
				and float(_param(shader_material, &"look_road_detect", 0.0)) > 0.5:
			label = "terrain (worn roads found by vertex colour)"
		if look_class == int(LookGround.Kind.BIOME) and kind == LookGround.Kind.PATCH:
			label = "biome verge (opaque authored base)"
		row["class"] = "painted: " + label
		var tint: Variant = shader_material.get_shader_parameter(&"albedo_color")
		row.tint = "#" + (tint as Color).to_html(true) if tint is Color else ""
		if source is ShaderMaterial or shader_material.shader != null \
				and not shader_material.shader.resource_path.begins_with("res://src/world/look/"):
			row.biome_textures = _biome_textures(shader_material, region)
	else:
		row["class"] = "left alone: " + _ground_reason(mesh_instance, source, kind)
		if source is BaseMaterial3D:
			row.tint = "#" + (source as BaseMaterial3D).albedo_color.to_html(true)
		if source is ShaderMaterial and (source as ShaderMaterial).shader != null:
			row.shader = (source as ShaderMaterial).shader.resource_path
	return row

func _ground_reason(mesh_instance: MeshInstance3D, source: Material, kind: LookGround.Kind) -> String:
	if mesh_instance.has_meta(LookGround.BATCH_META):
		return "batched (its MultiMesh draws the mesh's own material)"
	if mesh_instance.material_override != null:
		return "material override (%s)" % mesh_instance.material_override.resource_name
	if source == null:
		return "no material"
	if source is ShaderMaterial:
		var shader := (source as ShaderMaterial).shader
		return "shader %s (only the biome blend is painted)" % (shader.resource_path if shader else "?")
	var standard := source as BaseMaterial3D
	if standard == null:
		return source.get_class()
	if standard.albedo_color.a <= 0.01:
		return "invisible walk threshold"
	if kind == LookGround.Kind.DECK and standard.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED \
			and not standard.vertex_color_use_as_albedo:
		return "opaque deck without vertex colour (a bridge's timber or cobble)"
	if standard.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED \
			and standard.cull_mode == BaseMaterial3D.CULL_FRONT:
		return "front-culled"
	if standard.transparency in [BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR,
			BaseMaterial3D.TRANSPARENCY_ALPHA_HASH]:
		return "alpha scissor/hash (not reproduced)"
	return "not painted (region not finished by the loader yet, or painted_for refused it)"

## A biome blend's eight layer textures and how grassy each counts.
func _biome_textures(material: ShaderMaterial, region: String) -> Array:
	var textures: Array = []
	for prefix: String in ["base_albedo_", "secondary_albedo_"]:
		for layer: int in 4:
			var texture: Variant = material.get_shader_parameter(prefix + str(layer))
			if texture is not Texture2D:
				continue
			var file := (texture as Texture2D).resource_path.get_file().to_lower()
			if file.is_empty():
				continue
			var matched := "default"
			var own: Variant = LookProfile.region_section(region, "grass").get("layers")
			if own is Dictionary:
				for word: String in own:
					if file.contains(word):
						matched = "region word " + word
						break
			if matched == "default":
				for word: String in LookProfile.GRASS_LAYER_WORDS:
					if file.contains(word):
						matched = word
						break
			textures.append({"file": file, "region": region,
				"grassiness": LookGrassBeds.grassiness(texture, region), "matched": matched})
	return textures

func _is_water(node_name: String, mesh_instance: MeshInstance3D) -> bool:
	if node_name.begins_with("Water_") or node_name.begins_with("Scenery_Water"):
		return true
	var material := mesh_instance.material_override if mesh_instance.material_override != null \
		else mesh_instance.get_active_material(0)
	if material is ShaderMaterial and (material as ShaderMaterial).shader != null:
		var path := (material as ShaderMaterial).shader.resource_path.get_file()
		return _any(_tokens(path.get_basename()), WATER_WORDS)
	# Whole words: "crownwater_marble" is stone.
	return material != null and _any(_tokens(material.resource_name), WATER_WORDS)

func _water_row(mesh_instance: MeshInstance3D) -> Dictionary:
	var material := mesh_instance.material_override if mesh_instance.material_override != null \
		else mesh_instance.get_active_material(0)
	var row := {"material": material.resource_name if material != null else "",
		"type": material.get_class() if material != null else "none"}
	if material is ShaderMaterial and (material as ShaderMaterial).shader != null:
		row.shader = (material as ShaderMaterial).shader.resource_path
		row.decoded = _param(material as ShaderMaterial, &"look_decode_albedo", false) == true
	elif material is BaseMaterial3D:
		row.tint = "#" + (material as BaseMaterial3D).albedo_color.to_html(true)
	return row

func _foliage_painted(mesh_instance: MeshInstance3D) -> bool:
	for surface: int in mesh_instance.mesh.get_surface_count():
		var active := mesh_instance.get_active_material(surface)
		if active != null and active.has_meta(LookFoliage.PAINTED_META):
			return true
	if mesh_instance.has_meta(LookFoliage.BATCH_META):
		var batch: Variant = mesh_instance.get_meta(LookFoliage.BATCH_META)
		return batch is MultiMeshInstance3D and (batch as MultiMeshInstance3D).material_override != null \
			and (batch as MultiMeshInstance3D).material_override.has_meta(LookFoliage.PAINTED_META)
	return false

func _foliage_row(mesh_instance: MeshInstance3D, node_name: String, words: Dictionary,
		region: String, continent := true) -> Dictionary:
	var kinds: Array = []
	var reasons: Array = []
	var painted := _foliage_painted(mesh_instance)
	for surface: int in mesh_instance.mesh.get_surface_count():
		var source := _source_material(mesh_instance, surface)
		var kind := LookFoliage.kind_of(node_name, source, words) if source != null \
			else LookFoliage.Kind.NONE
		kinds.append(["none", "authored crown", "kit tree", "kit shrub"][int(kind) + 1])
		if painted:
			continue
		if not continent:
			# LookFoliage.paint_loaded paints continent roots only; a region
			# file's foliage section is never read for this map.
			reasons.append("the foliage layer does not run off the continent")
		elif kind == LookFoliage.Kind.NONE:
			reasons.append("no crown material or kit word (%s)" % (source.resource_name
				if source != null else "no material"))
		elif mesh_instance.material_override != null:
			reasons.append("material override")
		elif LookFoliage.painted_for(source, kind, mesh_instance.mesh) == null:
			var standard := source as BaseMaterial3D
			var why := "painted_for refused it"
			if standard != null:
				if standard.transparency not in [BaseMaterial3D.TRANSPARENCY_DISABLED,
						BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR]:
					why = "blended transparency"
				elif standard.cull_mode != BaseMaterial3D.CULL_DISABLED:
					why = "one-sided (culled)"
				elif standard.vertex_color_use_as_albedo:
					why = "vertex colour albedo"
				else:
					var box := mesh_instance.mesh.get_aabb()
					if maxf(box.size.x, box.size.z) > LookProfile.CROWN_MERGED_METRES:
						why = "many plants merged into one mesh"
					else:
						why = "a feature look_standard_surface does not reproduce"
			reasons.append(why)
		else:
			reasons.append("not painted (loader never finished this root through paint_loaded)")
	var box := mesh_instance.get_aabb()
	return {"region": region, "materials": _material_names(_surfaces_of(mesh_instance)),
		"painted": painted, "kinds": kinds, "reasons": reasons,
		"batched": mesh_instance.has_meta(LookFoliage.BATCH_META),
		"aabb_size": [snappedf(box.size.x, 0.1), snappedf(box.size.y, 0.1), snappedf(box.size.z, 0.1)]}

## Points on a painted road deck (vertex coverage at least 0.9), global.
func _road_points(mesh_instance: MeshInstance3D, node_name: String, points: Array) -> void:
	var active := mesh_instance.get_active_material(0) as ShaderMaterial
	if active == null or not active.has_meta(LookGround.PAINTED_META) \
			or float(_param(active, &"look_path_force", 0.0)) < 0.5 \
			or _param(active, &"use_vertex_alpha", false) != true:
		return
	var arrays := mesh_instance.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var colours: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] != null \
		else PackedColorArray()
	if colours.size() != vertices.size():
		return
	var xform := mesh_instance.global_transform
	var step := maxi(1, vertices.size() / 3000)
	for index: int in range(0, vertices.size(), step):
		if colours[index].a < 0.9:
			continue
		var spot := xform * vertices[index]
		points.append({"x": snappedf(spot.x, 0.1), "z": snappedf(spot.z, 0.1),
			"y": snappedf(spot.y, 0.1), "deck": node_name})

## A shader parameter, or `fallback` where the material never set it.
static func _param(material: ShaderMaterial, name: StringName, fallback: Variant) -> Variant:
	var value: Variant = material.get_shader_parameter(name)
	return fallback if value == null else value

func _tally(table: Dictionary, key: String, row: Dictionary, node_name: String) -> void:
	if not table.has(key):
		row.surfaces = 0
		row.patterns = []
		table[key] = row
	var entry: Dictionary = table[key]
	entry.surfaces = int(entry.surfaces) + 1
	var pattern := _pattern(node_name)
	if not (entry.patterns as Array).has(pattern) and (entry.patterns as Array).size() < 6:
		(entry.patterns as Array).append(pattern)

func _rows(table: Dictionary) -> Array:
	var rows: Array = table.values()
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return int(a.surfaces) > int(b.surfaces))
	return rows

func _summary(entry: Dictionary) -> String:
	var painted := 0
	var alone := 0
	for row: Dictionary in entry.ground:
		if String(row["class"]).begins_with("painted"):
			painted += int(row.surfaces)
		else:
			alone += int(row.surfaces)
	var crowns := 0
	var bare := 0
	for row: Dictionary in entry.foliage:
		if bool(row.painted):
			crowns += int(row.surfaces)
		else:
			bare += int(row.surfaces)
	return "ground painted %d, left %d; foliage painted %d, not %d; roads %d; census %s" % [
		painted, alone, crowns, bare, (entry.roads as Array).size(),
		str(entry.grass.get("census", {}).get("tufts", "-"))]

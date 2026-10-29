extends SceneTree
## Headless contract for the RL head (src/actors/rl_head/): the assets against
## their own extras and each other (the shipped head builds pinned, every hair
## and beard fitted to the head shipped beside it, the hairstyles' grooming
## shapes and fine-detail keep levels - which saved finishes show the messy
## band - beards whole), the packaged route
## (loose, never-imported GLBs; imported block-compressed, mipmapped maps used
## as they are), the hair detail uniform
## and the grooming from saved fields with the springs still swinging, the
## appearance byte form, identity and expression kept
## apart through animation, the body cut through torso and cape changes, the
## importer's shape filter, LOD choice per quality, the hooks on the real
## ReplicatedActor3D - activated by tier for every Human at High, with the
## lab's `rl_head` override and the RL_HEADS=classic switch - the hair-motion
## budget and the open-headwear refit (RLHeadwearFit) against the shipped
## placement, which the shipped heads keep unless RL_HEADWEAR_FIT=shipped.
##
##   Godot --headless --path godot-client --script res://tests/test_rl_head.gd

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")

var _failures := 0
var _stage: Node3D


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	_check_assets()
	_check_encoding()
	_check_importer_filter()
	await _check_actor("female", "mira")
	await _check_actor("male", "rowan")
	await _check_body_cut_composition("female")
	await _check_removal("male")
	await _check_dev_switch()
	_check_lod_selection()
	await _check_hair_motion()
	await _check_grooming("male", "Rowan", "rowan_shag", 2)
	await _check_grooming("female", "Mira", "mira_bun", 1)
	await _check_headwear_fit()
	print("rl head: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS ", message)
	else:
		_failures += 1
		push_error("rl head: " + message)


# ---------------------------------------------------------------- assets

func _check_assets() -> void:
	for sex: String in ["female", "male"]:
		var info := RLHeadLibrary.head(sex)
		_expect(not info.is_empty(), "%s head module loads" % sex)
		if info.is_empty():
			continue
		var names: PackedStringArray = info["control_names"]
		_expect(names.size() >= 2, "%s head declares controls (%d)" % [sex, names.size()])
		var mesh := ((info["lods"] as Array)[0] as Array)[0]["mesh"] as Mesh
		var shapes := PackedStringArray()
		for index: int in mesh.get_blend_shape_count():
			shapes.append(str(mesh.get_blend_shape_name(index)))
		var missing := PackedStringArray()
		for control: String in names:
			for side: String in ["_p", "_n"]:
				if not shapes.has("id_" + control + side):
					missing.append("id_" + control + side)
		for expression: String in info["expressions"] as PackedStringArray:
			if not shapes.has(expression):
				missing.append(expression)
		_expect(missing.is_empty(), "%s blend shapes match rlHead extras %s" % [sex, missing])
		var stray := PackedStringArray()
		for shape: String in shapes:
			if not shape.begins_with("id_") and not shape.begins_with("ex_"):
				stray.append(shape)
		_expect(stray.is_empty(), "%s head carries only id_/ex_ shapes %s" % [sex, stray])
		var groups := {}
		for control: Dictionary in info["controls"] as Array:
			groups[str(control.get("group", ""))] = true
		_expect(not groups.has(""), "%s every control names a group" % sex)
		var cut: Dictionary = info["body_cut"]
		_expect(str(cut.get("body", "")) == "luminous_" + sex
			and cut.get("hiddenBodyTriangles") is Array, "%s body cut names its body and triangles" % sex)
		var eye: Dictionary = info["eye"]
		_expect(eye.has("right") and eye.has("left")
			and float((eye["right"] as Dictionary)["iris_radius"]) > 0.01,
			"%s iris centres measured off the eye surface" % sex)
	_check_asset_consistency()
	_check_shipping_route()


## The route a package ships (tools/package_client.py, actor_shipping), taken
## by the checkout too: the GLBs are never imported, so GlbSceneCache parses
## them raw from their globalized path, and the maps come from ResourceLoader
## as their committed imports make them - block-compressed, with a mip chain,
## features2 at 1024 px - used as they are.
func _check_shipping_route() -> void:
	var glbs := 0
	for folder: String in ["", "hair/", "beards/"]:
		for file: String in DirAccess.get_files_at(ProjectSettings.globalize_path(RLHeadLibrary.ROOT + folder)):
			if file.get_extension() == "glb":
				glbs += 1
				var path := RLHeadLibrary.ROOT + folder + file
				_expect(not FileAccess.file_exists(path + ".import"),
					"%s is not editor-imported (loose-only actor)" % path.get_file())
	_expect(glbs >= 8, "the RL GLBs are found on disk (%d)" % glbs)
	_expect(FileAccess.file_exists(RLHeadLibrary.ROOT.path_join(".gdignore")),
		"the RL GLB folder carries its local import guard (AGENTS.md: actor_shipping loose folders)")
	_expect(RLHeadLibrary.hair_styles().size() >= 2 and RLHeadLibrary.beard_styles().size() >= 5,
		"hairstyles and beards are listed from disk %s %s" % [RLHeadLibrary.hair_styles(),
			RLHeadLibrary.beard_styles()])
	var maps := 0
	for file: String in DirAccess.get_files_at(ProjectSettings.globalize_path(RLHeadLibrary.TEXTURE_DIR)):
		if file.get_extension() != "png":
			continue
		maps += 1
		var path := RLHeadLibrary.TEXTURE_DIR + file
		var texture := RLHeadLibrary.texture(file)
		var size := texture.get_size() if texture != null else Vector2.ZERO
		var cap := 1024.0 if file.contains("features2") else 4096.0
		_expect(texture is CompressedTexture2D and texture.resource_path == path,
			"%s is the imported texture, used as it is" % file)
		# CompressedTexture2D does not report its mip chain (has_mipmaps() is
		# false); the image it uploaded does.
		var image := texture.get_image() if texture != null else null
		_expect(image != null and image.has_mipmaps() and Image.FORMAT_DXT1 <= texture.get_format()
			and texture.get_format() <= Image.FORMAT_BPTC_RGBFU and maxf(size.x, size.y) <= cap,
			"%s is block-compressed with mipmaps, %s (format %d, %d mip levels)" % [file, size,
				texture.get_format() if texture != null else -1, image.get_mipmap_count() if image != null else -1])
	_expect(maps >= 13, "every RL map was checked (%d)" % maps)


## The head builds shipped, by sex. The hairstyles and beards beside them were
## fitted to exactly these (2026-10-28: mira_bun and rowan_shag rebuilt with
## the grooming shapes and keep levels, then with the scalp coverage fix and
## the messy band). A new head build needs its hair and beards rebuilt and this
## table changed with them.
const SHIPPED_HEADS := {
	"female": "abd93434b4d06be2f1b55ae5a71f7cc701e1abf286f4939c1f700e92cb523636",
	"male": "cae93a7f3366c5b01fb0134d6048435602686d1eda9edc4c3e73cb9adf6ddbc6",
}
## Every RL hairstyle carries these grooming shapes beside its `id_` shapes.
const GROOMING_SHAPES: Array[String] = ["hl_length_p", "hl_length_n", "hl_volume_p", "hl_volume_n"]
## The hair author's keep-level bands (COLOR_0.A), [low, high]: core geometry,
## authored fine detail (flyaway and wisp cards) and messy extras. A value is
## in a band within KEEP_BAND_SLACK, one 8-bit step (COLOR_0 is normalised u8:
## 0.5 is stored as 127 or 128, 0.45 as 115).
const KEEP_BANDS := {"core": [1.0, 1.0], "fine": [0.5, 0.95], "messy": [0.05, 0.45]}
const KEEP_BAND_SLACK := 1.0 / 255.0
## rl_hair.gdshader keeps a point when COLOR.a >= 1 - hair_detail -
## KEEP_TOLERANCE (half an 8-bit step); _check_messy_band_by_finish models it.
const HAIR_KEEP_TOLERANCE := 0.5 / 255.0

## Hair and facial hair are fitted to one build of a head: each records the
## SHA-256 of the head GLB it was fitted to (`headSHA256`), which must be the
## head shipped for its sex, with no exceptions.
func _check_asset_consistency() -> void:
	var heads := {}
	for sex: String in ["female", "male"]:
		heads[sex] = FileAccess.get_sha256(RLHeadLibrary.head_path(sex))
		_expect(heads[sex] == SHIPPED_HEADS[sex], "the shipped %s head is build %s (%s)" % [sex,
			str(SHIPPED_HEADS[sex]).left(12), str(heads[sex]).left(12)])
	var counted := {"hair/": 0, "beards/": 0}
	for folder: Array in [["hair/", "rlHair"], ["beards/", "rlBeard"]]:
		for file: String in DirAccess.get_files_at(RLHeadLibrary.ROOT + folder[0]):
			if file.get_extension() != "glb":
				continue
			counted[folder[0]] = int(counted[folder[0]]) + 1
			var relative: String = folder[0] + file
			var extras := RLHeadLibrary.asset_extras(RLHeadLibrary.ROOT + relative, folder[1])
			var sex := str(extras.get("sex", ""))
			var recorded := str(extras.get("headSHA256", ""))
			_expect(heads.has(sex), "%s names the head sex it was fitted to (%s)" % [relative, sex])
			if not heads.has(sex):
				continue
			_expect(recorded == heads[sex], "%s was fitted to the shipped %s head (%s against %s)" % [relative,
				sex, recorded.left(12), str(heads[sex]).left(12)])
	_expect(int(counted["hair/"]) >= 2 and int(counted["beards/"]) >= 4,
		"every shipped hairstyle and beard was checked %s" % counted)
	for style: String in RLHeadLibrary.hair_styles():
		_check_hair_asset(style)
	_check_messy_band_by_finish()
	for style: String in RLHeadLibrary.beard_styles():
		if style != RLHeadAppearance.STUBBLE:
			_check_beard_asset(style)


## The hair author's contract on one hairstyle as imported: every level
## carries the head's identity shapes and the four grooming shapes, and every
## keep level (COLOR_0.A) is in one of KEEP_BANDS and nothing else: core
## geometry (1), authored fine detail (0.5..0.95, cards only) or messy extras
## (0.05..0.45, cards or clump locks such as Rowan's fringe-gap locks, shown
## only above level 55). The first level has both fine and messy detail; the
## last is all core.
func _check_hair_asset(style: String) -> void:
	var path := RLHeadLibrary.hair_path(style)
	var extras := RLHeadLibrary.asset_extras(path, "rlHair")
	var head_shapes: int = 2 * (RLHeadLibrary.head(str(extras.get("sex", "female"))).get("controls", []) as Array).size()
	var declared: Array = (extras.get("grooming", {}) as Dictionary).get("shapes", []) as Array
	_expect(declared == GROOMING_SHAPES, "%s declares the grooming shapes %s" % [style, declared])
	var scene := GlbSceneCache.instantiate(path)
	_expect(scene != null, "%s loads" % style)
	if scene == null:
		return
	var wanted := GROOMING_SHAPES.duplicate()
	wanted.sort()
	var levels := {}
	var fine_points := 0
	var messy_points := 0
	var bad: Array = []
	var nodes := scene.find_children("*", "MeshInstance3D", true, false)
	var last_level := 0
	for node: Node in nodes:
		last_level = maxi(last_level, RLHeadLibrary.lod_level(str(node.name)))
	for node: Node in nodes:
		var mesh := (node as MeshInstance3D).mesh
		var level := RLHeadLibrary.lod_level(str(node.name))
		levels[level] = true
		var ids := 0
		var grooming: Array[String] = []
		for index: int in mesh.get_blend_shape_count():
			var shape := str(mesh.get_blend_shape_name(index))
			if shape.begins_with("id_"):
				ids += 1
			elif shape.begins_with("hl_"):
				grooming.append(shape)
		grooming.sort()
		if ids != head_shapes or grooming != wanted:
			bad.append("%s: %d id_, %s" % [node.name, ids, grooming])
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface)
			var kind := material.resource_name if material != null else ""
			var colours: Variant = mesh.surface_get_arrays(surface)[Mesh.ARRAY_COLOR]
			if colours is not PackedColorArray or (colours as PackedColorArray).is_empty():
				bad.append("%s/%s: no COLOR_0" % [node.name, kind])
				continue
			for colour: Color in colours as PackedColorArray:
				var band := _keep_band(colour.a)
				if level == 0 and band == "fine":
					fine_points += 1
				elif level == 0 and band == "messy":
					messy_points += 1
				if band.is_empty() or (band == "fine" and kind != "rl_hair_card") \
						or (level == last_level and band != "core"):
					bad.append("%s/%s: keep level %.3f outside the contract" % [node.name, kind, colour.a])
					break
	_expect(levels.size() == 3 and bad.is_empty(),
		"%s: %d levels, each with %d id_ shapes and the grooming shapes, keep levels in contract %s"
			% [style, levels.size(), head_shapes, bad])
	_expect(fine_points > 0, "%s: its first level has fine-detail cards (%d points)" % [style, fine_points])
	_expect(messy_points > 0, "%s: its first level has messy extras for above level 55 (%d points)"
		% [style, messy_points])
	scene.free()


## The KEEP_BANDS name of keep level `a`, or "" outside every band.
func _keep_band(a: float) -> String:
	for band: String in KEEP_BANDS:
		var limits: Array = KEEP_BANDS[band]
		if a >= float(limits[0]) - KEEP_BAND_SLACK and a <= float(limits[1]) + KEEP_BAND_SLACK:
			return band
	return ""


## What develop's three saved finishes show of the messy band. A finish becomes
## a fine-detail level through RLHeadPortraitMap, and the hair shader keeps a
## point at A >= 1 - level / 100 (less half an 8-bit step), so the messy band
## (0.05..0.45) shows only above level 55. rowan_shag's finishes are Swept 17,
## Classic 33 and Tousled 50 (Tousled, his preset finish, is the authored look):
## no messy point shows on any level. mira_bun's are Swept 50 (her preset finish,
## none shown), Classic 67 and Tousled 83: messier than authored, they show part
## of the band by design, Tousled more of it. Level 100 shows all of it.
func _check_messy_band_by_finish() -> void:
	var shader := load("res://src/actors/rl_head/rl_hair.gdshader") as Shader
	var code := shader.code if shader != null else ""
	_expect(code.contains("const float KEEP_TOLERANCE = 0.5 / 255.0;")
		and code.contains("COLOR.a >= 1.0 - detail - KEEP_TOLERANCE"),
		"rl_hair.gdshader keeps a point at A >= 1 - hair_detail - 0.5/255, the rule modelled here")
	# [sex, hair index (AppearanceVariants), module, levels and whether messy
	# points show at Swept, Classic, Tousled]
	for row: Array in [["male", 1, "rowan_shag", [17, 33, 50], [false, false, false]],
			["female", 3, "mira_bun", [50, 67, 83], [false, true, true]]]:
		var module: String = row[2]
		var messy := _messy_keep_levels(module)
		var total := 0
		for level: int in messy:
			total += (messy[level] as PackedFloat32Array).size()
		var first_total := (messy.get(0, PackedFloat32Array()) as PackedFloat32Array).size()
		var levels: Array = []
		var shows: Array = []
		var counts: Array = []
		for finish: Array in [[2, "Swept"], [0, "Classic"], [1, "Tousled"]]:
			var detail := RLHeadPortraitMap.face({"hair": AppearanceVariants.pack_hair(int(row[1]), 0),
				"hair_detail": finish[0]}, str(row[0])).hair_detail
			var shown := _messy_shown(messy, detail)
			levels.append(detail)
			shows.append(int(shown[0]) > 0)
			counts.append("%s %d: %d of %d first-level points (%d keep values), %d on all levels"
				% [finish[1], detail, shown[1], first_total, shown[2], shown[0]])
		var increasing := int(_messy_shown(messy, int(levels[2]))[0]) >= int(_messy_shown(messy, int(levels[1]))[0])
		_expect(total > 0 and levels == row[3] and shows == row[4] and increasing
			and int(_messy_shown(messy, 100)[0]) == total,
			"%s: the saved finishes are levels %s and show the messy band %s (level 100: all %d points) %s"
				% [module, levels, shows, total, counts])


## Each level's keep values (COLOR_0.A) in the messy band of RL hairstyle
## `style`, by level of detail.
func _messy_keep_levels(style: String) -> Dictionary:
	var result := {}
	var scene := GlbSceneCache.instantiate(RLHeadLibrary.hair_path(style))
	if scene == null:
		return result
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		var values := PackedFloat32Array()
		for surface: int in mesh.get_surface_count():
			var colours: Variant = mesh.surface_get_arrays(surface)[Mesh.ARRAY_COLOR]
			if colours is PackedColorArray:
				for colour: Color in colours as PackedColorArray:
					if _keep_band(colour.a) == "messy":
						values.append(colour.a)
		var level := RLHeadLibrary.lod_level(str(node.name))
		result[level] = (result.get(level, PackedFloat32Array()) as PackedFloat32Array) + values
	scene.free()
	return result


## [points shown on all levels, points shown on the first level, distinct keep
## values shown on the first level] of `messy` at detail level `detail`, by
## rl_hair.gdshader's rule.
func _messy_shown(messy: Dictionary, detail: int) -> Array:
	var threshold := 1.0 - float(detail) / 100.0 - HAIR_KEEP_TOLERANCE
	var points := 0
	var first := 0
	var values := {}
	for level: int in messy:
		for a: float in messy[level] as PackedFloat32Array:
			if a >= threshold:
				points += 1
				if level == 0:
					first += 1
					values[snappedf(a, 0.0001)] = true
	return [points, first, values.size()]


## Beards stay whole at every hair detail: COLOR_0.A = 1 everywhere.
func _check_beard_asset(style: String) -> void:
	var lowest := 1.0
	var surfaces := 0
	for level: Array in RLHeadLibrary.beard(style):
		for piece: Dictionary in level:
			var mesh := piece["mesh"] as Mesh
			for surface: int in mesh.get_surface_count():
				surfaces += 1
				var colours: Variant = mesh.surface_get_arrays(surface)[Mesh.ARRAY_COLOR]
				if colours is not PackedColorArray or (colours as PackedColorArray).is_empty():
					lowest = -1.0
					continue
				for colour: Color in colours as PackedColorArray:
					lowest = minf(lowest, colour.a)
	_expect(surfaces > 0 and lowest >= 0.999, "beard %s is all core geometry (lowest keep level %.3f)"
		% [style, lowest])


# ---------------------------------------------------------------- encoding

func _check_encoding() -> void:
	var names := RLHeadLibrary.head("female").get("control_names", PackedStringArray()) as PackedStringArray
	for preset: String in RLHeadAppearance.preset_names():
		var face := RLHeadAppearance.from_preset(preset)
		_round_trip(face, names, "preset " + preset)
	var random := RandomNumberGenerator.new()
	random.seed = 4242
	for trial: int in 25:
		var face := RLHeadAppearance.new()
		face.sex = "male" if trial % 2 else "female"
		for control: String in names:
			if random.randf() < 0.7:
				face.set_control(control, random.randf_range(-1.0, 1.0))
		face.skin = Color(random.randf(), random.randf(), random.randf())
		face.eyes = Color(random.randf(), random.randf(), random.randf())
		face.hair_color = Color(random.randf(), random.randf(), random.randf())
		face.brow_color = Color(random.randf(), random.randf(), random.randf())
		face.lip_tint = Color(random.randf(), random.randf(), random.randf())
		face.freckles = random.randf()
		face.liner = random.randf()
		face.stubble = random.randf()
		face.hair = ["none", "mira_bun", "a_style_no_registry_lists"][trial % 3]
		face.beard = ["none", "stubble", "full_beard"][trial % 3]
		face.brow_style = float(random.randi_range(0, 12)) / 4.0
		face.brow_thickness = random.randf_range(-1.0, 1.0)
		face.liner_wing = random.randf()
		_round_trip(face, names, "random face %d" % trial)
	var face := RLHeadAppearance.from_preset("mira")
	var bytes := face.encode(names)
	var reordered := names.duplicate()
	reordered.reverse()
	_expect(RLHeadAppearance.decode(bytes, reordered) == null,
		"a different control set is refused, not misread")
	_expect(RLHeadAppearance.decode(bytes.slice(0, 9), names) == null, "cut-short bytes are refused")
	_expect(bytes.size() <= 32, "a face fits in %d bytes" % bytes.size())
	# Version 1 had no brow bytes: it still decodes, with the default brow.
	var control_bytes := (int(bytes[4]) + 1) / 2
	var version_one := bytes.slice(0, 5 + control_bytes + 12)
	version_one.append_array(bytes.slice(5 + control_bytes + 14))
	version_one[0] = 1
	var old := RLHeadAppearance.decode(version_one, names)
	_expect(old != null and old.hair == face.hair and old.beard == face.beard
		and old.brow_style == RLHeadAppearance.DEFAULT_BROW_STYLE and old.brow_thickness == 0.0
		and old.liner_wing == 0.0 and absf(old.freckles - face.freckles) <= 0.034,
		"version 1 bytes decode with the default brow and no wing")
	var mira := RLHeadAppearance.from_preset("mira")
	_expect(mira.brow_style == 0.0 and is_equal_approx(mira.brow_thickness, 0.2)
		and is_equal_approx(mira.liner_wing, 0.8) and str(mira.to_dict()["brow_style"]) == "arched",
		"presets name their brow style; the dictionary form writes the name")
	var blended := RLHeadAppearance.from_dict({"brow_style": 1.5})
	_expect(blended.brow_style == 1.5 and float(blended.to_dict()["brow_style"]) == 1.5,
		"a fractional brow style blends and round-trips as a number")
	var dictionary := face.to_dict()
	var back := RLHeadAppearance.from_dict(dictionary)
	_expect(back.to_dict() == dictionary, "the dictionary form round-trips exactly")
	var edited := RLHeadAppearance.from_dict({"preset": "mira", "controls": {"nose_width": 0.5}})
	_expect(edited.control("nose_width") == 0.5 and edited.hair == face.hair,
		"a dictionary overlays the preset it names")


func _round_trip(face: RLHeadAppearance, names: PackedStringArray, label: String) -> void:
	var bytes := face.encode(names)
	var decoded := RLHeadAppearance.decode(bytes, names)
	var ok := decoded != null and decoded.encode(names) == bytes and decoded.sex == face.sex \
		and decoded.hair == face.hair and decoded.beard == face.beard
	if ok:
		for control: String in names:
			ok = ok and absf(decoded.control(control) - face.control(control)) <= 0.5 / 7.0 + 0.0001
		for pair: Array in [[decoded.skin, face.skin], [decoded.eyes, face.eyes],
				[decoded.lip_tint, face.lip_tint]]:
			var a: Color = pair[0]
			var b: Color = pair[1]
			ok = ok and absf(a.r - b.r) <= 0.017 and absf(a.g - b.g) <= 0.009 and absf(a.b - b.b) <= 0.017
		ok = ok and absf(decoded.freckles - face.freckles) <= 0.034
		ok = ok and absf(decoded.brow_style - face.brow_style) <= 0.125 \
			and absf(decoded.brow_thickness - face.brow_thickness) <= 0.5 / 7.0 + 0.0001 \
			and absf(decoded.liner_wing - face.liner_wing) <= 0.034
	_expect(ok, "byte form round-trips: " + label)


# ---------------------------------------------------------------- importer

func _check_importer_filter() -> void:
	var owner := Node3D.new()
	var mesh_node := MeshInstance3D.new()
	mesh_node.name = "Probe"
	var mesh := ArrayMesh.new()
	for shape: String in ["id_nose_width_p", "ex_blink_l", "Cape_Clearance"]:
		mesh.add_blend_shape(shape)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	var blend := []
	for shape: int in 3:
		var shape_arrays := []
		shape_arrays.resize(Mesh.ARRAY_MAX)
		shape_arrays[Mesh.ARRAY_VERTEX] = arrays[Mesh.ARRAY_VERTEX]
		blend.append(shape_arrays)
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, blend)
	mesh_node.mesh = mesh
	owner.add_child(mesh_node)
	var defaults := NativeAnimationImporter._blend_shape_defaults(owner)
	_expect(defaults.keys() == ["Probe:Cape_Clearance"],
		"the importer keeps RESET defaults for correctives and skips id_/ex_ shapes %s" % [defaults.keys()])
	owner.free()


# ---------------------------------------------------------------- actor

func _rl_actor(sex: String, value: Variant, visuals: Dictionary = {}) -> ReplicatedActor3D:
	return Stage.spawn(_stage, sex, {"rl_head": value}, visuals)


func _shape_values(nodes: Array[MeshInstance3D], prefix: String) -> Dictionary:
	var values := {}
	for mesh_node: MeshInstance3D in nodes:
		for index: int in mesh_node.mesh.get_blend_shape_count():
			var shape := str(mesh_node.mesh.get_blend_shape_name(index))
			if shape.begins_with(prefix):
				values["%s:%s" % [mesh_node.name, shape]] = mesh_node.get_blend_shape_value(index)
	return values


func _check_actor(sex: String, preset: String) -> void:
	var actor := _rl_actor(sex, preset)
	await process_frame
	var rig := actor.rl_head()
	_expect(rig != null, "%s: appearance.rl_head builds an RL head" % preset)
	if rig == null:
		actor.queue_free()
		return
	_expect(actor.animation_player != null and actor.animation_player.has_animation("Walk"),
		"%s: the animation import ran" % preset)
	var library := actor.animation_player.get_animation_library("")
	var reset := library.get_animation(&"RESET")
	var leaked := 0
	for clip: StringName in library.get_animation_list():
		var animation := library.get_animation(clip)
		for track: int in animation.get_track_count():
			var path := str(animation.track_get_path(track))
			if path.contains(":id_") or path.contains(":ex_"):
				leaked += 1
	_expect(reset != null and leaked == 0, "%s: no clip carries an id_/ex_ track" % preset)
	var native := actor.get_node("NativeModel") as Node3D
	for hidden: String in ["eyes", "eyebrows", "scalp"]:
		var node := native.find_child(hidden, true, false) as MeshInstance3D
		_expect(node != null and not node.visible, "%s: body %s hidden" % [preset, hidden])
	var legacy_hair := 0
	for child: Node in actor.get_skeleton().get_children():
		if child.name.begins_with("AppearanceHair_") and child.name != RLHeadRig.HAIR_NODE_NAME \
				and (child as Node3D).visible:
			legacy_hair += 1
	_expect(legacy_hair == 0, "%s: no legacy hairstyle shows under the RL head" % preset)
	var body := native.find_child("body", true, false) as MeshInstance3D
	var cut := RLHeadBodyCut.describe(body.get_meta(&"uncovered_body_mesh") as Mesh,
		str(rig.head_info()["path"]))
	_expect(str(cut.get("method", "")) == "list",
		"%s: the authored triangle list was verified and used %s" % [preset, cut])
	var patch_ok := false
	var head_node: MeshInstance3D = rig.identity_targets()[0]
	for surface: int in head_node.mesh.get_surface_count():
		var imported := head_node.mesh.surface_get_material(surface)
		if imported != null and imported.resource_name == RLHeadLibrary.BODY_PATCH_MATERIAL:
			patch_ok = head_node.get_surface_override_material(surface) == body.get_active_material(0)
	_expect(patch_ok, "%s: the body patch draws with the body's own material" % preset)
	# Identity and expression stay apart, also through animation.
	var names: PackedStringArray = rig.head_info()["control_names"]
	rig.set_control(names[0], 0.8)
	rig.set_control(names[1], -0.6)
	var identity := _shape_values(rig.identity_targets(), "id_")
	_expect(is_equal_approx(float(identity.get("%s:id_%s_p" % [head_node.name, names[0]], 0.0)), 0.8)
		and is_equal_approx(float(identity.get("%s:id_%s_n" % [head_node.name, names[1]], 0.0)), 0.6),
		"%s: controls drive their _p/_n shapes" % preset)
	var expression := rig.expression()
	expression.always_update = true
	expression.set_expression("smile", 1.0, 0.0)
	expression.blink()
	expression.advance(0.1)
	_expect(_shape_values(rig.identity_targets(), "id_") == identity,
		"%s: expressions and blinks leave every id_ weight alone" % preset)
	var smile := _shape_values(rig.expression_targets(), "ex_")
	_expect(float(smile.get("%s:ex_smile" % head_node.name, 0.0)) > 0.99
		and float(smile.get("%s:ex_blink_l" % head_node.name, 0.0)) > 0.3,
		"%s: smile and blink weights written" % preset)
	rig.set_control(names[2], 0.4)
	_expect(_shape_values(rig.expression_targets(), "ex_") == smile,
		"%s: identity changes leave every ex_ weight alone" % preset)
	identity = _shape_values(rig.identity_targets(), "id_")
	expression.set_process(false)
	actor.animation_player.play("Walk")
	for step: int in 6:
		actor.animation_player.advance(0.1)
		await process_frame
	_expect(_shape_values(rig.identity_targets(), "id_") == identity
		and _shape_values(rig.expression_targets(), "ex_") == smile,
		"%s: animation playback leaves id_ and ex_ weights unchanged" % preset)
	_expect(PackedStringArray(expression.available_shapes()).has("ex_blink_r"),
		"%s: expression shapes found on the head" % preset)
	# A brow style, thickness or wing is one instance uniform: nothing else on
	# the head changes, no mesh is rebuilt and no blend shape moves.
	for change: Array in [["brow_style", 1.0], ["brow_thickness", -0.7], ["liner_wing", 0.9]]:
		var before := _instance_values(head_node)
		var shapes_before := _shape_values(rig.identity_targets(), "")
		var nodes_before := rig.identity_targets()
		var face := rig.appearance.duplicate_appearance()
		var field: String = change[0]
		face.set(field, fposmod(float(face.get(field)) + float(change[1]), 3.0) if field == "brow_style"
			else float(change[1]))
		actor.apply_appearance_variants({"rl_head": face.to_dict()})
		var after := _instance_values(head_node)
		var changed: Array = []
		for uniform_name: String in after:
			if after[uniform_name] != before[uniform_name]:
				changed.append(uniform_name)
		_expect(changed == [field] and is_equal_approx(float(after[field]), float(face.get(field)))
			and _shape_values(rig.identity_targets(), "") == shapes_before
			and rig.identity_targets() == nodes_before,
			"%s: changing %s touches only that uniform %s" % [preset, field, changed])
	var hair_style := rig.appearance.hair
	if FileAccess.file_exists(RLHeadLibrary.hair_path(hair_style)):
		var hair_nodes: Array = rig.mesh_nodes()["hair"]
		_expect(not hair_nodes.is_empty() and rig.hair_motion() != null and rig.hair_motion().has_springs(),
			"%s: hairstyle %s drawn with its springs" % [preset, hair_style])
		# Fine detail is one instance uniform on the hair's meshes: the head's
		# uniforms, every blend shape and every mesh node stay as they were.
		_expect(_hair_detail_values(rig) == [0.5], "%s: the authored hair detail (0.5) on every hair level %s"
			% [preset, _hair_detail_values(rig)])
		for level: int in [0, 100, 50]:
			var head_before := _instance_values(head_node)
			var shapes_before := _shape_values(rig.identity_targets(), "")
			var nodes_before := rig.identity_targets()
			var face := rig.appearance.duplicate_appearance()
			face.hair_detail = level
			actor.apply_appearance_variants({"rl_head": face.to_dict()})
			_expect(_hair_detail_values(rig) == [float(level) / 100.0] and _instance_values(head_node) == head_before
				and _shape_values(rig.identity_targets(), "") == shapes_before
				and rig.identity_targets() == nodes_before,
				"%s: hair detail %d is the hair's hair_detail uniform alone %s" % [preset, level,
					_hair_detail_values(rig)])
		var attachment := actor.get_skeleton().get_node_or_null(RLHeadRig.HAIR_NODE_NAME)
		actor.apply_equipment_visuals({3: 134})
		await process_frame
		_expect(attachment != null and not (attachment as Node3D).visible,
			"%s: a hair-covering helm hides the RL hairstyle" % preset)
		actor.apply_equipment_visuals({})
		await process_frame
		_expect((attachment as Node3D).visible, "%s: taking the helm off shows it again" % preset)
	actor.queue_free()
	await process_frame


func _instance_values(mesh_node: MeshInstance3D) -> Dictionary:
	var values := {}
	for uniform_name: String in RLHeadRig.INSTANCE_UNIFORMS:
		values[uniform_name] = mesh_node.get_instance_shader_parameter(uniform_name)
	return values


func _hair_nodes(rig: RLHeadRig) -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for level: Array in rig.mesh_nodes()["hair"] as Array:
		for node: Variant in level:
			if is_instance_valid(node):
				result.append(node as MeshInstance3D)
	return result


## The distinct `hair_detail` values on the hair's meshes, rounded to 1e-4.
func _hair_detail_values(rig: RLHeadRig) -> Array:
	var values: Array = []
	for node: MeshInstance3D in _hair_nodes(rig):
		var value: Variant = node.get_instance_shader_parameter("hair_detail")
		var rounded: Variant = snappedf(float(value), 0.0001) if value != null else null
		if not values.has(rounded):
			values.append(rounded)
	return values


## {shape: weight} of the grooming shapes, when every hair mesh agrees; else
## {"disagree": ...}.
func _grooming_weights(rig: RLHeadRig) -> Dictionary:
	var result := {}
	for node: MeshInstance3D in _hair_nodes(rig):
		var weights := {}
		for shape: String in GROOMING_SHAPES:
			var index := RLHeadRig.shape_index(node, shape)
			weights[shape] = snappedf(node.get_blend_shape_value(index), 0.0001) if index >= 0 else null
		if result.is_empty():
			result = weights
		elif weights != result:
			return {"disagree": [result, weights]}
	return result


# ---------------------------------------------------------------- grooming

## The real RL hairstyles groomed from a Human's saved fields: hair_length and
## hair_volume centred on the module's likeness preset drive its hl_ shapes on
## every level, the hair finish becomes the fine-detail level, nothing is
## rebuilt, beards keep the default detail, and the springs still swing.
func _check_grooming(sex: String, look: String, module: String, other_finish: int) -> void:
	var appearance := HumanPortraitPresets.appearance(look)
	var preset := HumanPortraitPresets.shape(look)
	var actor := Stage.spawn(_stage, sex, appearance)
	await process_frame
	var rig := actor.rl_head()
	_expect(rig != null and rig.appearance.hair == module and rig.draws_module_hair(),
		"%s's saved look draws %s" % [look, module])
	if rig == null or not rig.draws_module_hair():
		actor.queue_free()
		await process_frame
		return
	var authored := {"hl_length_p": 0.0, "hl_length_n": 0.0, "hl_volume_p": 0.0, "hl_volume_n": 0.0}
	_expect(_grooming_weights(rig) == authored and _hair_detail_values(rig) == [0.5],
		"%s at %s's own length, volume and finish draws it as authored %s %s" % [module, look,
			_grooming_weights(rig), _hair_detail_values(rig)])
	var nodes_before := rig.identity_targets()
	for case: Array in [[100, 0, 0], [0, 100, other_finish], [preset.hair_length, preset.hair_volume, preset.hair_detail]]:
		var edited := appearance.duplicate()
		edited.merge({"hair_length": case[0], "hair_volume": case[1], "hair_detail": case[2]}, true)
		actor.apply_appearance_variants(edited)
		await process_frame
		var length := clampf((float(case[0]) - float(preset.hair_length)) / 50.0, -1.0, 1.0)
		var volume := clampf((float(case[1]) - float(preset.hair_volume)) / 50.0, -1.0, 1.0)
		var expected := {"hl_length_p": snappedf(maxf(length, 0.0), 0.0001), "hl_length_n": snappedf(maxf(-length, 0.0), 0.0001),
			"hl_volume_p": snappedf(maxf(volume, 0.0), 0.0001), "hl_volume_n": snappedf(maxf(-volume, 0.0), 0.0001)}
		var detail := snappedf(float(RLHeadPortraitMap.detail_level(RLHeadPortraitMap.finish_slider(case[2]), module)) / 100.0, 0.0001)
		_expect(_grooming_weights(rig) == expected and _hair_detail_values(rig) == [detail]
			and rig.identity_targets() == nodes_before,
			"%s length %d, volume %d, finish %d: hl_ weights %s, detail %.2f, same meshes" % [module, case[0],
				case[1], case[2], _grooming_weights(rig), detail])
	# Longest and fullest, then the springs: the locks still swing off rest
	# when the head moves.
	var edited := appearance.duplicate()
	edited.merge({"hair_length": 100, "hair_volume": 100}, true)
	actor.apply_appearance_variants(edited)
	await process_frame
	var motion := rig.hair_motion()
	_expect(motion != null and motion.has_springs(), "%s keeps its springs at full length" % module)
	if motion != null and motion.has_springs():
		var skeleton: Skeleton3D = motion._skeleton
		var tips: Array[int] = []
		for spring: Variant in (RLHeadLibrary.hair_info(module).get("extras", {}) as Dictionary).get("springs", []) as Array:
			var bones: Array = (spring as Dictionary).get("bones", []) as Array
			if not bones.is_empty():
				tips.append(skeleton.find_bone(str(bones.back())))
		var furthest := [0.0]
		var probe := func() -> void:
			for tip: int in tips:
				furthest[0] = maxf(float(furthest[0]), skeleton.get_bone_global_pose(tip).origin.distance_to(
					skeleton.get_bone_global_rest(tip).origin))
		motion._simulator.modification_processed.connect(probe)
		for step: int in 8:
			actor.global_position.x += 0.25
			await process_frame
		motion._simulator.modification_processed.disconnect(probe)
		_expect(motion.is_running() and float(furthest[0]) > 0.001 and not tips.has(-1),
			"%s at full length and volume: %d spring chains swing (%.1f mm off rest)" % [module, tips.size(),
				float(furthest[0]) * 1000.0])
	actor.queue_free()
	await process_frame
	if sex == "male":
		# A beard is drawn by the same shader and keeps the default detail.
		var bearded := Stage.spawn(_stage, sex, HumanPortraitPresets.appearance("Tavi"))
		await process_frame
		var beard_rig := bearded.rl_head()
		var beard_values: Array = []
		if beard_rig != null:
			for level: Array in beard_rig.mesh_nodes()["beard"] as Array:
				for node: MeshInstance3D in level:
					var value: Variant = node.get_instance_shader_parameter("hair_detail")
					if not beard_values.has(value):
						beard_values.append(value)
		_expect(beard_rig != null and beard_rig.appearance.beard == "full_beard" and not beard_values.is_empty()
			and beard_values.all(func(value: Variant) -> bool: return value == null or is_equal_approx(float(value), 0.5)),
			"Tavi's full beard keeps the default hair detail %s" % [beard_values])
		bearded.queue_free()
		await process_frame


func _hidden_triplets(original: Mesh, head_path: String) -> Dictionary:
	var plan: Dictionary = RLHeadBodyCut._plans.get("%d|%s" % [original.get_instance_id(), head_path], {})
	return plan.get("hidden", {}) as Dictionary


func _cut_is_clean(mesh: Mesh, hidden: Dictionary) -> bool:
	var arrays := mesh.surface_get_arrays(0)
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	for index: int in range(0, indices.size(), 3):
		if hidden.has(RLHeadBodyCut._triplet(indices[index], indices[index + 1], indices[index + 2])):
			return false
	return true


## A body mesh before Human body refinement (which compacts its arrays).
func _unrefined(body: MeshInstance3D) -> Mesh:
	if body.has_meta(CharacterProportions.BODY_RESULT_META) \
			and body.mesh == body.get_meta(CharacterProportions.BODY_RESULT_META):
		return body.get_meta(CharacterProportions.BODY_SOURCE_META) as Mesh
	return body.mesh


func _check_body_cut_composition(sex: String) -> void:
	var actor := _rl_actor(sex, "mira" if sex == "female" else "rowan")
	# The plain actor below High: develop's head, the same shared body.
	var plain := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.MEDIUM, 9301)
	await process_frame
	var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	var plain_body := plain.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	var original := body.get_meta(&"uncovered_body_mesh") as Mesh
	_expect(original == _unrefined(plain_body), "%s: the cut starts from the shared imported body" % sex)
	_expect(_unrefined(body) == body.get_meta(RLHeadBodyCut.CUT_META),
		"%s: body refinement fits the cut mesh, not the other way round" % sex)
	var hidden := _hidden_triplets(original, str(actor.rl_head().head_info()["path"]))
	var bare_cut := _unrefined(body)
	var bare_count := RLHeadRig.mesh_triangles(bare_cut)
	_expect(bare_count == RLHeadRig.mesh_triangles(original) - hidden.size() and _cut_is_clean(bare_cut, hidden),
		"%s: bare body loses exactly the listed triangles (%d)" % [sex, hidden.size()])
	var orders: Array = [
		[{5: Stage.TORSO}, {5: Stage.TORSO, 2: Stage.CAPE}, {2: Stage.CAPE}, {}],
		[{2: Stage.CAPE}, {2: Stage.CAPE, 5: Stage.TORSO}, {5: Stage.TORSO}, {}],
		[{5: Stage.TORSO, 2: Stage.CAPE, 3: 134}, {3: 134}, {}],
	]
	for order: Array in orders:
		for visuals: Dictionary in order:
			actor.apply_equipment_visuals(visuals)
			plain.apply_equipment_visuals(visuals)
			await process_frame
			var torso_worn := visuals.has(5)
			var plain_mesh := _unrefined(plain_body)
			var source := body.get_meta(RLHeadBodyCut.SOURCE_META) as Mesh
			_expect(_cut_is_clean(_unrefined(body), hidden) and source == plain_mesh,
				"%s %s: head cut taken from the same torso cover a plain actor wears" % [sex, visuals])
			if not torso_worn:
				_expect(_unrefined(body) == bare_cut, "%s %s: the bare head cut comes back" % [sex, visuals])
			var scalp := actor.get_node("NativeModel").find_child("scalp", true, false) as MeshInstance3D
			_expect(not scalp.visible, "%s %s: the scalp stays hidden" % [sex, visuals])
	var plain_cover := plain_body.get_meta(&"uncovered_body_mesh", _unrefined(plain_body)) as Mesh
	_expect(plain_cover == original, "%s: TorsoBodyCover still restores the untouched body" % sex)
	actor.queue_free()
	plain.queue_free()
	await process_frame


func _check_removal(sex: String) -> void:
	var actor := _rl_actor(sex, "rowan", {5: Stage.TORSO})
	await process_frame
	var native := actor.get_node("NativeModel") as Node3D
	var body := native.find_child("body", true, false) as MeshInstance3D
	var with_head := RLHeadRig.mesh_triangles(body.mesh)
	# Without the lab's override a High Human draws its own derived RL head...
	actor.apply_appearance_variants({"skin": 2, "hair": 1})
	await process_frame
	_expect(actor.rl_head() != null and actor.rl_head().appearance.preset.is_empty(),
		"%s: dropping rl_head at High draws the face the appearance asks for" % sex)
	# ...and below High none: develop's own head.
	actor.apply_render_quality(ActorRenderQuality.Quality.MEDIUM, false)
	await process_frame
	_expect(actor.rl_head() == null and RLHeadRig.find_on(actor.get_skeleton()) == null,
		"%s: switching to Medium removes the rig" % sex)
	_expect(not body.has_meta(RLHeadBodyCut.CUT_META)
		and RLHeadRig.mesh_triangles(body.mesh) > with_head,
		"%s: the body gets its head back under the torso cover" % sex)
	var eyes := native.find_child("eyes", true, false) as MeshInstance3D
	_expect(eyes.visible and not eyes.has_meta(ReplicatedActor3D.RL_HEAD_SHOWN_META),
		"%s: the body's own eyes return" % sex)
	var legacy := 0
	for child: Node in actor.get_skeleton().get_children():
		if child.name.begins_with("AppearanceHair_"):
			legacy += 1
	_expect(legacy == 1, "%s: the legacy hairstyle returns" % sex)
	actor.apply_render_quality(ActorRenderQuality.Quality.HIGH, false)
	await process_frame
	_expect(actor.rl_head() != null and body.has_meta(RLHeadBodyCut.CUT_META),
		"%s: back at High the RL head is put back on the live actor" % sex)
	actor.queue_free()
	await process_frame


func _check_dev_switch() -> void:
	# The default: every Human at High draws the RL head; Medium and Low do not.
	var female := Stage.spawn(_stage, "female", {"skin": 1})
	var male := Stage.spawn(_stage, "male", {"skin": 1})
	var medium := Stage.spawn(_stage, "female", {"skin": 1}, {}, ActorRenderQuality.Quality.MEDIUM, 9302)
	await process_frame
	_expect(female.rl_head() != null and female.rl_head().appearance.sex == "female",
		"a luminous female at High draws the RL head")
	_expect(male.rl_head() != null and male.rl_head().appearance.sex == "male",
		"a luminous male at High draws the male RL head")
	_expect(medium.rl_head() == null, "a luminous female at Medium keeps develop's head")
	# Headless reports the Forward+ method; the Compatibility renderer keeps
	# develop's High head unless RL_HEADS=all.
	_expect(ReplicatedActor3D.rl_heads_renderer_supported()
		== (RenderingServer.get_current_rendering_method() != "gl_compatibility"),
		"the RL head is drawn in every renderer but Compatibility")
	female.queue_free()
	male.queue_free()
	medium.queue_free()
	# RL_HEADS=classic keeps develop's classic High head, the lab override too.
	OS.set_environment("RL_HEADS", "classic")
	ReplicatedActor3D.reload_rl_heads_switch()
	var plain := Stage.spawn(_stage, "female", {"skin": 1})
	var lab := _rl_actor("female", "mira")
	await process_frame
	_expect(plain.rl_head() == null and lab.rl_head() == null, "RL_HEADS=classic builds no RL head")
	plain.queue_free()
	lab.queue_free()
	OS.set_environment("RL_HEADS", "")
	ReplicatedActor3D.reload_rl_heads_switch()
	# The lab's empty override means no RL head, at any quality.
	var bare := Stage.spawn(_stage, "female", {"skin": 1, "rl_head": ""})
	await process_frame
	_expect(bare.rl_head() == null, "an empty rl_head override builds no RL head")
	bare.queue_free()
	await process_frame


# ---------------------------------------------------------------- LOD

func _check_lod_selection() -> void:
	var skeleton := Skeleton3D.new()
	for bone: String in ["spine_03", "neck_01", "Head"]:
		skeleton.add_bone(bone)
	_stage.add_child(skeleton)
	var info := RLHeadLibrary.head("female")
	var piece: Dictionary = ((info["lods"] as Array)[0] as Array)[0]
	var three_levels: Array = [[piece], [piece], [piece]]
	var expected := {ActorRenderQuality.Quality.HIGH: 3, ActorRenderQuality.Quality.MEDIUM: 2,
		ActorRenderQuality.Quality.LOW: 1}
	for quality: int in expected:
		var rig := RLHeadRig.new()
		rig.quality = quality
		rig.appearance = RLHeadAppearance.from_preset("mira")
		rig._skeleton = skeleton
		skeleton.add_child(rig)
		var levels: Array = rig._instance_levels(three_levels, "Probe", "")
		_expect(levels.size() == expected[quality],
			"%s instances %d of 3 LOD levels" % [ActorRenderQuality.quality_name(quality), levels.size()])
		rig._head_lods = levels
		var name := ActorRenderQuality.quality_name(quality)
		var visible_at := func(distance: float) -> int:
			rig.update_lod(distance)
			for index: int in levels.size():
				if ((levels[index] as Array)[0] as MeshInstance3D).visible:
					return index
			return -1
		var bands: Array = RLHeadRig.LOD_DISTANCES[quality]
		if bands.is_empty():
			_expect(visible_at.call(2.0) == 0 and visible_at.call(60.0) == 0,
				"%s draws its one level at every distance" % name)
		else:
			var first_edge := float(bands[0])
			_expect(visible_at.call(2.0) == 0, "%s shows its first level up close" % name)
			_expect(visible_at.call(first_edge + 0.5) == 0,
				"%s holds the near level inside the hysteresis" % name)
			_expect(visible_at.call(first_edge + 3.0) == 1, "%s hands over past %.0f m" % [name, first_edge])
			_expect(visible_at.call(first_edge - 0.5) == 1 and visible_at.call(2.0) == 0,
				"%s comes back only past the margin" % name)
			_expect(visible_at.call(80.0) == levels.size() - 1, "%s shows its last level far away" % name)
			var shown := 0
			for level: Array in levels:
				shown += 1 if (level[0] as MeshInstance3D).visible else 0
			_expect(shown == 1, "%s keeps exactly one level visible" % name)
		var one_level: Array = rig._instance_levels([[piece]], "Single", "")
		_expect(one_level.size() == 1 and ((one_level[0] as Array)[0] as MeshInstance3D).visible,
			"%s draws a single-mesh asset" % ActorRenderQuality.quality_name(quality))
		rig.free()
	skeleton.free()


# ---------------------------------------------------------------- hair motion

func _check_hair_motion() -> void:
	_expect(ClassDB.class_exists("SpringBoneSimulator3D")
		and ClassDB.class_exists("SpringBoneCollisionSphere3D")
		and ClassDB.class_exists("SpringBoneCollisionCapsule3D"),
		"Godot provides the spring-bone simulator and its collisions")
	var camera := Camera3D.new()
	_stage.add_child(camera)
	camera.current = true
	var members: Array[RLHairMotion] = []
	for index: int in 11:
		var holder := Node3D.new()
		holder.position = Vector3(float(index) * 1.5, 0.0, 0.0)
		_stage.add_child(holder)
		var skeleton := Skeleton3D.new()
		var root_bone := skeleton.add_bone("hair_root")
		var previous := root_bone
		for joint: int in 3:
			var bone := skeleton.add_bone("lock_0_%d" % joint)
			skeleton.set_bone_parent(bone, previous)
			skeleton.set_bone_rest(bone, Transform3D(Basis.IDENTITY, Vector3(0.0, -0.05, 0.0)))
			skeleton.reset_bone_pose(bone)
			previous = bone
		holder.add_child(skeleton)
		var motion := RLHairMotion.new()
		holder.add_child(motion)
		var built := motion.configure(skeleton, {"springs": [{"bones": ["lock_0_0", "lock_0_1", "lock_0_2"],
			"stiffness": 1.0, "damping": 0.4, "gravity": 0.5, "radius": 0.01}],
			"collisions": [{"shape": "sphere", "offset": [0, 0.05, 0], "radius": 0.09},
				{"shape": "capsule", "offset": [0, 0, 0], "radius": 0.05, "height": 0.2}]})
		if index == 0:
			_expect(built and motion.has_springs(), "springs built from rlHair extras")
		members.append(motion)
	camera.global_position = Vector3(0.0, 0.0, 2.0)
	await process_frame
	await process_frame
	var running := 0
	var far_running := false
	for motion: RLHairMotion in members:
		if motion.is_running():
			running += 1
			far_running = far_running or (motion.get_parent() as Node3D).global_position.x > 11.9
	_expect(running == RLHairMotion.MAX_ACTIVE, "at most %d actors swing their hair (%d)"
		% [RLHairMotion.MAX_ACTIVE, running])
	_expect(not far_running, "hair beyond %.0f m rests" % RLHairMotion.RANGE_METRES)
	# The springs really move bones: swing the nearest head sideways and the
	# lock's tip leaves its rest pose. A modifier's pose holds only while the
	# skeleton is being updated, so it is read when the simulator reports.
	var swung := members[0]
	var swung_skeleton := swung.get_parent().get_child(0) as Skeleton3D
	var tip := swung_skeleton.find_bone("lock_0_2")
	var holder := swung.get_parent() as Node3D
	var furthest := [0.0]
	swung._simulator.modification_processed.connect(func() -> void:
		furthest[0] = maxf(float(furthest[0]), swung_skeleton.get_bone_global_pose(tip).origin.distance_to(
			swung_skeleton.get_bone_global_rest(tip).origin)))
	for step: int in 6:
		holder.position.x += 0.25
		await process_frame
	_expect(swung.is_running() and float(furthest[0]) > 0.001,
		"SpringBoneSimulator3D swings a running lock (%.1f mm off rest)" % (float(furthest[0]) * 1000.0))
	for motion: RLHairMotion in members:
		motion.enabled = false
	await process_frame
	var still := true
	for motion: RLHairMotion in members:
		still = still and not motion.is_running()
	_expect(still, "switching motion off (below HIGH, or the lab) stops every chain")
	for motion: RLHairMotion in members:
		motion.get_parent().queue_free()
	camera.queue_free()
	await process_frame


# ---------------------------------------------------------------- headwear

## A plain actor of another race, built as the stage builds a luminous one.
func _race_actor(slug: String, visuals: Dictionary) -> ReplicatedActor3D:
	var config: Dictionary = ((Stage.data("models").get("models", {}) as Dictionary).get(slug, {})
		as Dictionary).duplicate(true)
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	actor.configure({"actor_id": 9400, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
		"appearance": {"skin": 1, "hair": 0}, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config, Stage.data("animation"),
		Stage.data("equipment"))
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.apply_equipment_visuals(visuals)
	return actor


## The head piece's nodes on an actor: the BoneAttachment3D and any refitted
## skinned meshes.
func _head_piece(actor: ReplicatedActor3D) -> Dictionary:
	var attachment: BoneAttachment3D = null
	var refits: Array[MeshInstance3D] = []
	for child: Node in actor.get_skeleton().get_children():
		if child.is_queued_for_deletion():
			continue
		# By role, not name: a part rebuilt while the old one awaits its free
		# gets an engine-made name.
		if child is BoneAttachment3D and child.has_meta("native_equipment") \
				and (child as BoneAttachment3D).bone_name == "Head":
			attachment = child as BoneAttachment3D
		elif child is MeshInstance3D and child.has_meta(&"rl_headwear_fit"):
			refits.append(child as MeshInstance3D)
	return {"attachment": attachment, "refits": refits}


## Largest model-space extent of the piece as drawn at rest.
func _piece_extent(actor: ReplicatedActor3D) -> float:
	var nodes := _head_piece(actor)
	var box := AABB()
	var first := true
	var meshes: Array[MeshInstance3D] = []
	var transforms: Array[Transform3D] = []
	var skeleton := actor.get_skeleton()
	var head_rest := skeleton.get_bone_global_rest(skeleton.find_bone("Head"))
	if not (nodes["refits"] as Array).is_empty():
		for mesh_node: MeshInstance3D in nodes["refits"]:
			meshes.append(mesh_node)
			transforms.append(Transform3D.IDENTITY)
	elif nodes["attachment"] != null:
		for found: Node in (nodes["attachment"] as Node).find_children("*", "MeshInstance3D", true, false):
			var mesh_node := found as MeshInstance3D
			meshes.append(mesh_node)
			var holder := mesh_node.get_parent() as Node3D
			transforms.append(head_rest * holder.transform * mesh_node.transform)
	for index: int in meshes.size():
		for surface: int in meshes[index].mesh.get_surface_count():
			for p: Vector3 in meshes[index].mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]:
				var q := transforms[index] * p
				if first:
					box = AABB(q, Vector3.ZERO)
					first = false
				else:
					box = box.expand(q)
	return maxf(box.size.x, box.size.z)


func _check_headwear_fit() -> void:
	var data := RLHeadwearFit.data()
	_expect(not data.is_empty(), "headwear fit data loads")
	for visual: int in [111, 112, 114, 119]:
		_expect(RLHeadwearFit.has_piece(visual), "open piece 3:%d has a fit" % visual)
	for visual: int in [134, 159, 150, 170]:
		_expect(not RLHeadwearFit.has_piece(visual), "closed piece 3:%d keeps its shipped fit" % visual)
	var circlet := RLHeadwearFit.piece(111)
	_expect(RLHeadwearFit.fit_name(circlet, "female", "") == "female", "bald fit chosen with no hair")
	_expect(RLHeadwearFit.fit_name(circlet, "female", "mira_bun") == "female/mira_bun",
		"a hairstyle's own fit is chosen")
	_expect(RLHeadwearFit.fit_name(circlet, "female", "no_such_style") == "female/*",
		"an unfitted hairstyle takes the fallback fit")
	_expect(RLHeadwearFit.fit_name(circlet, "luminous_female", "") == "luminous_female",
		"the shipped luminous head has a bald fit of its own")
	_expect(not RLHeadwearFit.fits_shipped_body("luminous_male")
		and not RLHeadwearFit.fits_shipped_body("luminous_female"),
		"shipped heads keep the shipped placement by default (D8)")
	# another race's head wears its own variant exactly as before
	var race := _race_actor("greyhaven_female", {3: 111, 5: Stage.TORSO})
	await process_frame
	var plain := _head_piece(race)
	_expect(plain["attachment"] != null and (plain["refits"] as Array).is_empty()
		and (plain["attachment"] as Node).get_child_count() == 1,
		"a greyhaven head wears the circlet exactly as before")
	race.queue_free()
	# a Human below High (no RL head) wears it as shipped
	var medium := Stage.spawn(_stage, "female", {"skin": 1, "hair": 0}, {3: 111, 5: Stage.TORSO},
		ActorRenderQuality.Quality.MEDIUM, 9303)
	await process_frame
	var shipped_piece := _head_piece(medium)
	_expect(shipped_piece["attachment"] != null and (shipped_piece["refits"] as Array).is_empty()
		and (shipped_piece["attachment"] as Node).get_child_count() == 1,
		"a luminous head below High wears the circlet as shipped")
	medium.queue_free()
	# RL_HEADWEAR_FIT=shipped turns the shipped-head fits on (owner decision pending)
	OS.set_environment("RL_HEADWEAR_FIT", "shipped")
	RLHeadwearFit.reload()
	_expect(RLHeadwearFit.fits_shipped_body("luminous_male")
		and not RLHeadwearFit.fits_shipped_body("greyhaven_female"),
		"RL_HEADWEAR_FIT=shipped: luminous refitted, other races left as shipped")
	var legacy := Stage.spawn(_stage, "female", {"skin": 1, "hair": 0}, {3: 111, 5: Stage.TORSO},
		ActorRenderQuality.Quality.MEDIUM, 9304)
	await process_frame
	var shipped := _head_piece(legacy)
	var shipped_key := str((shipped["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if shipped["attachment"] != null else ""
	_expect(not (shipped["refits"] as Array).is_empty() and shipped_key.begins_with("111|luminous_female||"),
		"the shipped luminous head takes its own circlet fit when switched on (%s)" % shipped_key)
	legacy.apply_appearance_variants({"skin": 1, "hair": 2})
	await process_frame
	var haired := _head_piece(legacy)
	var haired_key := str((haired["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if haired["attachment"] != null else ""
	_expect(haired_key.begins_with("111|luminous_female|luminous_female_"),
		"a shipped hairstyle refits the circlet over it (%s)" % haired_key)
	legacy.queue_free()
	OS.set_environment("RL_HEADWEAR_FIT", "")
	RLHeadwearFit.reload()
	var shipped_extent := 0.327  # the human_female variant as shipped, model space
	# an RL head refits it
	var actor := _rl_actor("female", "mira", {3: 111, 5: Stage.TORSO})
	await process_frame
	var fitted := _head_piece(actor)
	var refits: Array = fitted["refits"]
	_expect(refits.size() >= 1, "mira: the circlet is rebuilt for the RL head")
	_expect(fitted["attachment"] != null and (fitted["attachment"] as Node).get_child_count() == 0,
		"mira: the shipped placement is not drawn as well")
	var fitted_extent := _piece_extent(actor)
	_expect(fitted_extent < shipped_extent * 0.85,
		"mira: the circlet is smaller (%.3f m against %.3f m shipped)" % [fitted_extent, shipped_extent])
	var trail_vertices := 0
	for mesh_node: MeshInstance3D in refits:
		_expect(mesh_node.skin != null and mesh_node.skin.get_bind_count() == RLHeadwearFit.BONES.size(),
			"mira: %s is skinned to the head and shoulders" % mesh_node.name)
		var arrays := mesh_node.mesh.surface_get_arrays(0)
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		for index: int in range(0, weights.size(), 4):
			if weights[index] < 0.99:
				trail_vertices += 1
	_expect(trail_vertices > 50, "mira: the ribbons ride the neck and shoulders (%d vertices)" % trail_vertices)
	var key := str((fitted["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, ""))
	_expect(key.contains("mira_bun"), "mira: fitted over her hair (%s)" % key)
	# a closed helm on the RL head is the shipped one
	actor.apply_equipment_visuals({3: 134, 5: Stage.TORSO})
	await process_frame
	var helm := _head_piece(actor)
	_expect((helm["refits"] as Array).is_empty() and helm["attachment"] != null
		and (helm["attachment"] as Node).get_child_count() == 1,
		"mira: a closed helm keeps its shipped placement")
	# back to the circlet, then bald: the fit follows the hair
	actor.apply_equipment_visuals({3: 111, 5: Stage.TORSO})
	await process_frame
	var face := actor.rl_head().appearance.duplicate_appearance()
	face.hair = RLHeadAppearance.NONE
	actor.apply_appearance_variants({"rl_head": face.to_dict()})
	await process_frame
	var bald := _head_piece(actor)
	var bald_key := str((bald["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if bald["attachment"] != null else ""
	_expect(not (bald["refits"] as Array).is_empty() and bald_key.begins_with("111|female||"),
		"mira bald: the circlet is refitted to the bare head (%s)" % bald_key)
	# a game hairstyle under the RL head: the fit follows it
	actor.apply_appearance_variants({"skin": 1, "hair": AppearanceVariants.pack_hair(2, 4)})
	await process_frame
	var long_hair := _head_piece(actor)
	var long_key := str((long_hair["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if long_hair["attachment"] != null else ""
	_expect(not (long_hair["refits"] as Array).is_empty() and long_key.begins_with("111|female|legacy:long|"),
		"a game hairstyle under the RL head refits the circlet over it (%s)" % long_key)
	# below High the shipped head wears the shipped circlet again
	actor.apply_render_quality(ActorRenderQuality.Quality.MEDIUM, false)
	await process_frame
	var restored := _head_piece(actor)
	var restored_key := str((restored["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if restored["attachment"] != null else ""
	_expect((restored["refits"] as Array).is_empty() and restored_key.is_empty()
		and restored["attachment"] != null and (restored["attachment"] as Node).get_child_count() == 1,
		"without the RL head the circlet is the shipped one (%s)" % restored_key)
	actor.queue_free()
	await process_frame

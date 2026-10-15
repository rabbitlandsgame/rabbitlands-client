class_name LookFoliage
extends RefCounted
## Look pass layer L3: paints the crowns - top-lit, clumped, cooler and deeper
## underneath, each a little different from its neighbours, the autumn reds
## and oranges tamed into a painted range, swaying a little in the wind - by
## giving each crown a painted material as its region, chunk or neighbour is
## finished. Does nothing unless LookProfile.enabled().
##
## Two families of crown come out of the exporters (see the look inventory,
## tests/look/probe_materials.gd):
##
## - Authored trees are split into Tree_<n>_<species>_Canopy and _Wood nodes.
##   The canopy draws with an alpha-cut leaf material (foliage_amber, _rust,
##   _gold, and undergrowth); those materials are what is painted, so every
##   canopy, grove and landmark crown that uses them is found whatever its
##   node is called. Trunks (bark_*) are left alone.
## - The kit's Meshy trees and shrubs are one surface with one atlas material
##   for crown and trunk together, recognised by the species words in their
##   node names (LookProfile.KIT_TREE_WORDS, KIT_SHRUB_WORDS, and whatever a
##   region file's `foliage` section adds for its region). Their crown is
##   split from their trunk inside the shader by height, at CROWN_FLOOR of the
##   mesh (measured on their texels; saturation alone does not separate them).
##
## A painted material needs its crown's box, which lives in the mesh, and its
## crown's jitter seed, hashed from the node's position in its region (which a
## seam crossing's rebase does not move). So one is made per source material,
## mesh and seed, and the seeds are rounded to CROWN_JITTER_VARIANTS: a kit
## tree's copies share one mesh and a few materials. The seed is a material
## uniform, not an instance uniform: the compatibility renderer gives instance
## uniforms 16 slots per instance out of 4096, so they ran out at about 256
## crowns ("Too many instances using shader instance variables").
##
## Crowns go in as surface overrides, never into the shared material or mesh,
## and after the loader's cache snapshot, as the ground's do. The loader's
## static batches draw their members through one MultiMesh, so a batch whose
## mesh is a crown gets the painted material as its override, and its hidden
## members get it too: OccluderFade lifts a member out of the batch to fade it,
## and it must then draw the same crown.
##
## Every painted crown also names its dithered variant (LookFade), so a crown
## that stands between the camera and the player dithers out rather than
## staying solid, which is what a ShaderMaterial would otherwise do, and the
## material it stands in for (LookProfile.SOURCE_META), so LookSwitch can put
## that back, and clear a batch's override, when the look is switched off.

const SHADER_OPAQUE := preload("res://src/world/look/painted_foliage.gdshader")
const SHADER_CUTOUT := preload("res://src/world/look/painted_foliage_cutout.gdshader")
const SHADER_OPAQUE_FADED := preload("res://src/world/look/painted_foliage_faded.gdshader")
const SHADER_CUTOUT_FADED := preload("res://src/world/look/painted_foliage_cutout_faded.gdshader")
## The same four for a single-sided source (culled back faces), such as the
## Sunmane steppe's sun_foliage trees.
const SHADER_OPAQUE_BACK := preload("res://src/world/look/painted_foliage_back.gdshader")
const SHADER_CUTOUT_BACK := preload("res://src/world/look/painted_foliage_cutout_back.gdshader")
const SHADER_OPAQUE_BACK_FADED := preload(
	"res://src/world/look/painted_foliage_back_faded.gdshader")
const SHADER_CUTOUT_BACK_FADED := preload(
	"res://src/world/look/painted_foliage_cutout_back_faded.gdshader")
## A signature material's stand-in at rest (`keep_chroma`).
const SHADER_CHROMA := preload("res://src/world/look/look_chroma_standard.gdshader")
const SHADER_CHROMA_TWO_SIDED := preload(
	"res://src/world/look/look_chroma_standard_two_sided.gdshader")

## Marks a material this layer made, so painting a root twice is harmless.
const PAINTED_META := &"look_painted_foliage"
## WorldLoader.BATCH_META: the node is hidden and this MultiMesh draws it.
const BATCH_META := &"static_batch"
## WorldLoader.BATCH_INDEX_META: the member's instance in its batch.
const BATCH_INDEX_META := &"static_batch_index"
## How far apart a batch's instances' seeds are (the golden ratio, as in
## painted_foliage_body.gdshaderinc).
const INSTANCE_SEED_STEP := 0.6180339
## Meta on a root that is not a territory's own - a runtime world object
## (MapObject3D, `paint_object`) - holding the Transform3D from it to its
## territory's frame, so its crowns' jitter seeds and tints are worked out
## where it stands rather than at its own origin.
const PLACE_META := &"look_place"
## Meta on a root: its territory's continent translation (Vector2, x and z),
## so a crown's tint can fade into a neighbour's across a border (LookBorders
## works in continent metres). A root without it is taken to be in them.
const CONTINENT_META := &"look_continent_translation"
## A crown tint is rounded to this many steps per channel before it keys a
## material, so a border's fade costs a handful of materials, not one a tree.
const CROWN_TINT_STEPS := 64.0

enum Kind { NONE = -1, CROWN = 0, KIT_TREE = 1, KIT_SHRUB = 2 }

## Paints a continent map's root as the loader finishes it, like
## LookGround.paint_loaded. The maps outside the continent have no crowns this
## layer can paint (Lantern Reach's wind pines are one merged mesh). Returns
## the surfaces painted.
static func paint_loaded(root: Node, manifest: WorldManifest) -> int:
	if root == null or manifest == null or not manifest.data.has("continentGeography"):
		return 0
	# Against the root, as LookGround.paint_loaded asks (LookProfile.enabled_for).
	if not LookProfile.enabled_for(root):
		return 0
	root.set_meta(CONTINENT_META, translation_of(manifest))
	var painted := paint(root, LookGround.region_of(manifest))
	keep_chroma(root, LookGround.region_of(manifest))
	return painted

## A runtime world object standing on a continent map - a harvest node's model
## (MapObject3D) - is added after its map's root was painted (`paint_loaded`),
## so main paints it here, with that map's `region`: a node whose model is a
## kit plant then shades as the same plant placed beside it does (its crown
## painted, its signature colours kept). `place` is the object's transform in
## its territory's frame and `translation` the territory's continent
## translation (x, z), for its crowns' seeds and tints. Returns the surfaces
## painted.
static func paint_object(root: Node, region := "", place := Transform3D.IDENTITY,
		translation := Vector2.ZERO) -> int:
	if root == null or not LookProfile.enabled():
		return 0
	root.set_meta(PLACE_META, place)
	root.set_meta(CONTINENT_META, translation)
	return paint(root, region) + keep_chroma(root, region)

## A continent manifest's translation (x, z), continent metres.
static func translation_of(manifest: WorldManifest) -> Vector2:
	var geography: Variant = manifest.data.get("continentGeography") if manifest != null else null
	var translation: Variant = (geography as Dictionary).get("translation") \
		if geography is Dictionary else null
	if translation is Array and (translation as Array).size() == 3:
		return Vector2(float(translation[0]), float(translation[2]))
	return Vector2.ZERO

## The signature-colour layer: a region's own colours that the shared grade
## would grey out keep their chroma. Every surface under `root` whose
## StandardMaterial3D is named with one of its region file's
## `props.keep_words` (the Amethyst Barrens' crystals, Ssarathi's and Verdant's
## jade) takes a copy drawn by look_chroma_standard, which lights as the
## source does with its albedo's and emission's chroma scaled by
## `props.keep_chroma` (LookProfile.KEEP_CHROMA_FORWARD / KEEP_CHROMA where it
## sets none), undoing the grade's saturation on them alone. Under
## SATURATION_FORWARD the Barrens' crystals, its namesake, went from
## saturation 0.46 to 0.22, pale lilac rubble on grey scree, and Ssarathi's
## jade court and Verdant's jade stair went grey. The copy names its faded
## variant, so it fades as any stand-in does and keeps its colour while it
## does. Returns the surfaces changed.
static func keep_chroma(root: Node, region := "") -> int:
	if not LookProfile.enabled() or root == null:
		return 0
	var words := LookProfile.keep_words(region)
	if words.is_empty():
		return 0
	var chroma := float(LookProfile.region_value(region, "props", "keep_chroma",
		LookProfile.KEEP_CHROMA_FORWARD if LookProfile.forward_plus() else LookProfile.KEEP_CHROMA))
	var tint: Color = LookProfile.region_value(region, "props", "keep_tint", Color.WHITE)
	var made := {}
	var surfaces := 0
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null or mesh_instance.material_override != null:
			continue
		var batch: MultiMeshInstance3D = null
		if mesh_instance.has_meta(BATCH_META):
			var batch_value: Variant = mesh_instance.get_meta(BATCH_META)
			if batch_value is not MultiMeshInstance3D \
					or mesh_instance.mesh.get_surface_count() != 1:
				continue
			batch = batch_value as MultiMeshInstance3D
		for surface: int in mesh_instance.mesh.get_surface_count():
			# Painted ground and crowns are ShaderMaterials by now and pass;
			# a floor the ground layer leaves alone (an interior's mosaic
			# deck) can be kept.
			var source := mesh_instance.get_active_material(surface) as BaseMaterial3D
			if source == null or not _named_with(source.resource_name, words):
				continue
			var key := source.get_instance_id()
			if not made.has(key):
				made[key] = chroma_copy(source, chroma, tint)
			var copy: ShaderMaterial = made[key]
			if copy == null:
				continue
			mesh_instance.set_surface_override_material(surface, copy)
			if batch != null and batch.material_override == null:
				batch.material_override = copy
			surfaces += 1
	if surfaces > 0:
		print("look_foliage stage=kept_chroma root=%s surfaces=%d materials=%d"
			% [root.name, surfaces, made.size()])
	return surfaces

## `source` drawn by look_chroma_standard with its chroma scaled by `chroma`
## and its tint multiplied by `tint` (a region's `props.keep_tint`), or null
## when that shader cannot draw it as the engine does (it blends, or uses a
## feature look_standard_surface does not reproduce).
static func chroma_copy(source: BaseMaterial3D, chroma: float,
		tint := Color.WHITE) -> ShaderMaterial:
	var cutout := source.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	if (source.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED and not cutout) \
			or not LookFade.reproduces(source):
		return null
	var two_sided := source.cull_mode == BaseMaterial3D.CULL_DISABLED
	var copy := ShaderMaterial.new()
	copy.resource_name = source.resource_name
	copy.set_meta(LookProfile.SOURCE_META, source)
	copy.shader = SHADER_CHROMA_TWO_SIDED if two_sided else SHADER_CHROMA
	copy.render_priority = source.render_priority
	copy.next_pass = source.next_pass
	copy.set_meta(LookFade.FADED_SHADER_META,
		LookFade.SHADER_STANDARD_TWO_SIDED if two_sided else LookFade.SHADER_STANDARD)
	LookFade.copy_standard_surface(source, copy)
	copy.set_shader_parameter(&"use_vertex_albedo", source.vertex_color_use_as_albedo)
	copy.set_shader_parameter(&"vertex_albedo_srgb", source.vertex_color_is_srgb)
	copy.set_shader_parameter(&"alpha_mode", 1 if cutout else 0)
	copy.set_shader_parameter(&"alpha_scissor_threshold", source.alpha_scissor_threshold)
	copy.set_shader_parameter(&"look_chroma", chroma)
	var colour := source.albedo_color
	copy.set_shader_parameter(&"albedo_color",
		Color(colour.r * tint.r, colour.g * tint.g, colour.b * tint.b, colour.a))
	return copy

static func _named_with(material_name: String, words: Array) -> bool:
	var lowered := material_name.to_lower()
	for word: Variant in words:
		if lowered.contains(str(word)):
			return true
	return false

## Paints every crown under `root`, a root of `region` (whose region file may
## name more crown materials and kit words, LookProfile.foliage_words). Safe to
## call again on a root it has already painted.
static func paint(root: Node, region := "") -> int:
	if not LookProfile.enabled() or root == null:
		return 0
	var words := words_for(region)
	var tinting := crown_tints_near(region)
	var made: Dictionary = {}
	var surfaces := 0
	var batches := 0
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null or mesh_instance.material_override != null:
			continue
		var node_name := _plain_name(String(mesh_instance.name))
		if LookGround.kind_of(node_name) != LookGround.Kind.NONE:
			continue
		var batch: MultiMeshInstance3D = null
		if mesh_instance.has_meta(BATCH_META):
			var batch_value: Variant = mesh_instance.get_meta(BATCH_META)
			# A batch has one override for every surface it draws.
			if batch_value is not MultiMeshInstance3D \
					or mesh_instance.mesh.get_surface_count() != 1:
				continue
			batch = batch_value as MultiMeshInstance3D
		var seed := _crown_seed(mesh_instance, root, batch)
		var untamed := _untamed(node_name, words)
		# A batch's members take its tint, as they take its seeds: lifted out
		# of the batch to fade, a member must draw the same crown.
		var tint := Color.WHITE if tinting.is_empty() else crown_tint_from(tinting,
			_crown_place(mesh_instance, root, batch))
		for surface: int in mesh_instance.mesh.get_surface_count():
			var source: Material = mesh_instance.get_active_material(surface)
			if source == null or source.has_meta(PAINTED_META):
				continue
			var kind := kind_of(node_name, source, words)
			var tinted := tint if kind in [Kind.CROWN, Kind.KIT_TREE] else Color.WHITE
			var key := "%d:%d:%.4f" % [source.get_instance_id(),
				mesh_instance.mesh.get_instance_id(), seed]
			if tinted != Color.WHITE:
				key += ":" + tinted.to_html(false)
			if kind == Kind.NONE:
				# An authored tree's trunk and boughs are cut near the camera
				# where its crown is, or they stood alone as a dark tangle of
				# limbs across the frame (cw_border_ss's oak).
				if not is_tree_wood(node_name) or source is not BaseMaterial3D:
					continue
				key = "wood:%d" % source.get_instance_id()
				if not made.has(key):
					var wood := chroma_copy(source as BaseMaterial3D, 1.0)
					if wood != null:
						wood.set_shader_parameter(&"look_near_cut",
							LookProfile.CROWN_NEAR_FADE_METRES.x)
					made[key] = wood
			elif not made.has(key):
				made[key] = painted_for(source, kind, mesh_instance.mesh, untamed, seed, tinted)
			var painted: Material = made[key]
			if painted == null:
				continue
			mesh_instance.set_surface_override_material(surface, painted)
			surfaces += 1
			if batch != null and batch.material_override == null:
				var batch_key := "batch:%d" % batch.get_instance_id()
				# A batched trunk shares its members' copy: it has no seed.
				made[batch_key] = painted if kind == Kind.NONE else painted_for(source, kind,
					mesh_instance.mesh, untamed, _batch_seed(batch, root), tinted)
				batch.material_override = made[batch_key]
				batches += 1
	var materials := 0
	for value: Variant in made.values():
		if value != null:
			materials += 1
	if surfaces > 0:
		print("look_foliage stage=painted root=%s surfaces=%d materials=%d batches=%d"
			% [root.name, surfaces, materials, batches])
	return surfaces

## True for an authored tree's trunk and boughs: Tree_<n>_<species>_Wood, and
## a giant's Landmark_Giant_<n>_Wood.
static func is_tree_wood(node_name: String) -> bool:
	return node_name.ends_with("_Wood") \
		and (node_name.begins_with("Tree_") or node_name.begins_with("Landmark_Giant"))

## The crown materials and kit words that apply to `region`'s roots, by
## LookProfile.FOLIAGE_DEFAULTS key: every map's plus the region file's own.
static func words_for(region := "") -> Dictionary:
	var words := {}
	for key: String in LookProfile.FOLIAGE_DEFAULTS:
		words[key] = LookProfile.foliage_words(region, key)
	return words

## What kind of crown a surface is: an authored crown by its leaf material, a
## kit tree or shrub by the species words in its node's name, or none.
## `words` is `words_for` a region; empty, every map's lists.
static func kind_of(node_name: String, material: Material, words := {}) -> Kind:
	var standard := material as BaseMaterial3D
	if standard == null:
		return Kind.NONE
	if words.is_empty():
		words = words_for()
	if standard.resource_name in (words.crown_materials as Array):
		return Kind.CROWN
	if not node_name.begins_with("kit-"):
		return Kind.NONE
	var parts := node_name.to_lower().split("-", false)
	# Props that carry a plant's word but are not painted as plants: every
	# map's (LookProfile.KIT_NOT_FOLIAGE_WORDS) plus a region's
	# `foliage.plain_words` (sw_isle's clipped garden hedges and flower shrubs
	# keep their own texture: painted as crowns they read as pale grey-green
	# cards and dark slabs).
	var plain: Array = words.get("plain_words", LookProfile.KIT_NOT_FOLIAGE_WORDS)
	for word: String in parts:
		if word in plain:
			return Kind.NONE
	for word: String in parts:
		if word in (words.tree_words as Array):
			return Kind.KIT_TREE
	for word: String in parts:
		if word in (words.shrub_words as Array):
			return Kind.KIT_SHRUB
	return Kind.NONE

## The painted stand-in for `source` on `mesh`, or null when it cannot be
## painted faithfully (it blends, culls its front faces, takes its colour from
## vertex colour, uses a feature look_standard_surface does not reproduce, or
## is many plants merged into one mesh). A single-sided source keeps its
## culling: a closed kit mesh loses nothing, where drawn two-sided it would
## pay for its back faces.
##
## `tint` is the crown tint (`crown_tint_at`), a multiplier on the crown's
## linear colour from the crown up; white leaves the paint as it was.
static func painted_for(source: Material, kind: Kind, mesh: Mesh,
		untamed := false, seed := 0.0, tint := Color.WHITE) -> ShaderMaterial:
	var standard := source as BaseMaterial3D
	if standard == null or kind == Kind.NONE or mesh == null:
		return null
	var cutout := standard.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	if standard.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED and not cutout:
		return null
	if standard.cull_mode == BaseMaterial3D.CULL_FRONT \
			or standard.vertex_color_use_as_albedo or not LookFade.reproduces(standard):
		return null
	var one_sided := standard.cull_mode == BaseMaterial3D.CULL_BACK
	var box := mesh.get_aabb()
	var width := maxf(box.size.x, box.size.z)
	if width > LookProfile.CROWN_MERGED_METRES \
			and width > box.size.y * LookProfile.CROWN_MERGED_RATIO:
		return null
	var floor_share := LookProfile.CROWN_FLOOR if kind == Kind.KIT_TREE else 0.0
	var painted := ShaderMaterial.new()
	painted.resource_name = standard.resource_name
	painted.set_meta(LookProfile.SOURCE_META, source)
	if one_sided:
		painted.shader = SHADER_CUTOUT_BACK if cutout else SHADER_OPAQUE_BACK
	else:
		painted.shader = SHADER_CUTOUT if cutout else SHADER_OPAQUE
	painted.render_priority = standard.render_priority
	painted.next_pass = standard.next_pass
	painted.set_meta(PAINTED_META, true)
	if one_sided:
		painted.set_meta(LookFade.FADED_SHADER_META,
			SHADER_CUTOUT_BACK_FADED if cutout else SHADER_OPAQUE_BACK_FADED)
	else:
		painted.set_meta(LookFade.FADED_SHADER_META,
			SHADER_CUTOUT_FADED if cutout else SHADER_OPAQUE_FADED)
	LookFade.copy_standard_surface(standard, painted)
	painted.set_shader_parameter(&"alpha_scissor_threshold", standard.alpha_scissor_threshold)
	painted.set_shader_parameter(&"look_crown_min", Vector3(box.position.x,
		box.position.y + box.size.y * floor_share, box.position.z))
	painted.set_shader_parameter(&"look_crown_max", box.end)
	painted.set_shader_parameter(&"look_mesh_foot", box.position.y)
	var top := LookProfile.CROWN_TOP
	var under := LookProfile.CROWN_UNDER
	var under_warm := LookProfile.CROWN_UNDER_WARM
	painted.set_shader_parameter(&"look_crown_top", Vector3(top.r, top.g, top.b))
	painted.set_shader_parameter(&"look_crown_under", Vector3(under.r, under.g, under.b))
	painted.set_shader_parameter(&"look_crown_under_warm",
		Vector3(under_warm.r, under_warm.g, under_warm.b))
	painted.set_shader_parameter(&"look_crown_light_power", LookProfile.CROWN_LIGHT_POWER)
	painted.set_shader_parameter(&"look_crown_core", LookProfile.CROWN_CORE)
	painted.set_shader_parameter(&"look_crown_core_edge", LookProfile.CROWN_CORE_EDGE)
	# The lobes are sized to the crown, in its own mesh units: a kit tree's
	# mesh is scaled by its node, and a giant canopy has larger lobes.
	painted.set_shader_parameter(&"look_crown_clump_metres", maxf(
		maxf(box.size.x, box.size.z) / LookProfile.CROWN_LOBES, 0.001))
	painted.set_shader_parameter(&"look_crown_clump", LookProfile.CROWN_CLUMP)
	painted.set_shader_parameter(&"look_crown_jitter_hue", LookProfile.CROWN_JITTER_HUE)
	painted.set_shader_parameter(&"look_crown_jitter_value", LookProfile.CROWN_JITTER_VALUE)
	painted.set_shader_parameter(&"look_tame", 0.0 if untamed else 1.0)
	painted.set_shader_parameter(&"look_tame_hue", LookProfile.TAME_HUE)
	painted.set_shader_parameter(&"look_tame_from", LookProfile.TAME_FROM)
	painted.set_shader_parameter(&"look_tame_knee", LookProfile.TAME_KNEE)
	painted.set_shader_parameter(&"look_tame_ceiling", LookProfile.TAME_CEILING)
	painted.set_shader_parameter(&"look_tame_magenta_floor", LookProfile.TAME_MAGENTA_FLOOR)
	painted.set_shader_parameter(&"look_tame_hue_top", LookProfile.TAME_HUE_TOP)
	painted.set_shader_parameter(&"look_tame_hue_under", LookProfile.TAME_HUE_UNDER)
	painted.set_shader_parameter(&"look_tame_value", LookProfile.TAME_VALUE)
	painted.set_shader_parameter(&"look_tame_value_from", LookProfile.TAME_VALUE_FROM)
	painted.set_shader_parameter(&"look_crown_volume", LookProfile.CROWN_VOLUME)
	painted.set_shader_parameter(&"look_crown_volume_lift", LookProfile.CROWN_VOLUME_LIFT)
	painted.set_shader_parameter(&"look_sway_metres", LookProfile.CROWN_SWAY_METRES)
	painted.set_shader_parameter(&"look_sway_speed", LookProfile.CROWN_SWAY_SPEED)
	painted.set_shader_parameter(&"look_seed", seed)
	painted.set_shader_parameter(&"look_crown_tint", Vector3(tint.r, tint.g, tint.b))
	painted.set_shader_parameter(&"look_fade", 1.0)
	painted.set_shader_parameter(&"look_near_fade", LookProfile.CROWN_NEAR_FADE_METRES)
	painted.set_shader_parameter(&"look_debug",
		clampi(OS.get_environment(LookProfile.FOLIAGE_DEBUG_VARIABLE).to_int(), 0, 1))
	return painted

## The crown's jitter seed (0..1): a hash of its position in `root`, walked up
## through the local transforms because a chunk is painted before it joins
## the tree, and because the world's global frame moves at every seam crossing.
static func seed_of(node: Node3D, root: Node) -> float:
	var place := _place_in(node, root)
	return _hash_seed(hash(Vector2i(roundi(place.origin.x * 4.0),
		roundi(place.origin.z * 4.0))))

## `node`'s transform in `root`'s territory frame: walked up through the local
## transforms (a chunk is painted before it joins the tree), and through the
## root's own place in its territory when it is a runtime object (PLACE_META).
static func _place_in(node: Node3D, root: Node) -> Transform3D:
	var place := node.transform
	var parent := node.get_parent()
	while parent != null and parent != root:
		if parent is Node3D:
			place = (parent as Node3D).transform * place
		parent = parent.get_parent()
	if root != null and root.has_meta(PLACE_META):
		place = (root.get_meta(PLACE_META) as Transform3D) * place
	return place

## Where a crown stands in continent metres (x, z), for its tint: a batch
## member at its batch's centre, as it takes its batch's tint.
static func _crown_place(node: MeshInstance3D, root: Node, batch: MultiMeshInstance3D) -> Vector2:
	var at: Vector3
	if batch != null and batch.multimesh != null:
		at = batch.transform * batch.multimesh.get_aabb().get_center()
	else:
		at = _place_in(node, root) * node.get_aabb().get_center()
	var offset: Vector2 = root.get_meta(CONTINENT_META, Vector2.ZERO) if root != null \
		else Vector2.ZERO
	return Vector2(at.x, at.z) + offset

## The crown tints that apply to `region`'s roots: {} when neither it nor any
## neighbour names one (every region but the ones that tune it, so nothing is
## worked out per crown), else {"region", "own", "neighbours": id -> tint}.
static func crown_tints_near(region: String) -> Dictionary:
	if region.is_empty():
		return {}
	var own: Color = LookProfile.region_value(region, "foliage", "crown_tint", Color.WHITE)
	var neighbours := {}
	for neighbour: String in LookBorders.neighbours_of(region):
		var theirs: Color = LookProfile.region_value(neighbour, "foliage", "crown_tint", Color.WHITE)
		if theirs != Color.WHITE:
			neighbours[neighbour] = theirs
	if own == Color.WHITE and neighbours.is_empty():
		return {}
	return {"region": region, "own": own, "neighbours": neighbours}

## `region`'s tree-crown tint at `xz` (continent metres): its file's
## `foliage.crown_tint` (white where it names none), faded into each
## neighbour's across their border as the ground trims are (LookBorders: the
## two meet at their mean on the border line, and each is its own
## BORDER_FEATHER_METRES inside). The continent-v2 isles' borders are not
## blended (LookBorders builds none for them), so an isle's tint stands to its
## edge. Rounded to CROWN_TINT_STEPS.
static func crown_tint_at(region: String, xz: Vector2) -> Color:
	var tinting := crown_tints_near(region)
	return Color.WHITE if tinting.is_empty() else crown_tint_from(tinting, xz)

static func crown_tint_from(tinting: Dictionary, xz: Vector2) -> Color:
	var own: Color = tinting.own
	var blended := Vector3(own.r, own.g, own.b)
	var selection := LookBorders.near(String(tinting.region), Rect2(xz, Vector2.ZERO),
		LookProfile.BORDER_FEATHER_METRES)
	var names: PackedStringArray = selection.neighbours
	if not names.is_empty():
		var weights := LookBorders.weights(xz, selection)
		var kept := 1.0
		var mixed := Vector3.ZERO
		for slot: int in names.size():
			var theirs: Color = (tinting.neighbours as Dictionary).get(names[slot], Color.WHITE)
			mixed += Vector3(theirs.r, theirs.g, theirs.b) * weights[slot]
			kept -= weights[slot]
		blended = blended * maxf(kept, 0.0) + mixed
	var rounded := (blended * CROWN_TINT_STEPS).round() / CROWN_TINT_STEPS
	return Color(rounded.x, rounded.y, rounded.z)

static func _hash_seed(value: int) -> float:
	return float(posmod(value, 65521)) / 65521.0

## The seed a crown's painted material carries. A crown drawn by its own node
## takes one of CROWN_JITTER_VARIANTS seeds, so the copies of a kit tree share
## a handful of materials instead of one each. A batch member takes exactly
## the seed its batch's shader gives its instance, so lifting it out of the
## batch to fade it does not change its colour.
static func _crown_seed(node: MeshInstance3D, root: Node, batch: MultiMeshInstance3D) -> float:
	if batch != null:
		var index := int(node.get_meta(BATCH_INDEX_META, 0))
		return fposmod(_batch_seed(batch, root) + float(index) * INSTANCE_SEED_STEP, 1.0)
	var variants := float(LookProfile.CROWN_JITTER_VARIANTS)
	return floorf(seed_of(node, root) * variants) / variants

static func _batch_seed(batch: MultiMeshInstance3D, root: Node) -> float:
	return _hash_seed((String(root.name) + String(batch.name)).hash())

## Blossom keeps its colour: the tame is for the autumn crowns.
static func _untamed(node_name: String, words: Dictionary) -> bool:
	for word: String in node_name.to_lower().split("-", false):
		if word in (words.untamed_words as Array):
			return true
	return false

## A neighbour's preview copy is named StreamView_<n>__<original>.
static func _plain_name(node_name: String) -> String:
	if node_name.begins_with("StreamView_"):
		return node_name.get_slice("__", 1)
	return node_name

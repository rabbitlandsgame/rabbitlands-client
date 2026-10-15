class_name OldcraftActorStyle
extends RefCounted
## The painted-surface finish shared by every actor.
##
## This class used to also grow player bones at runtime (persistent pose
## scales on the chest, limbs, head, hands and feet).  The owner removed that
## on 2026-10-05: the scales compounded down each chain - a hand ended up
## about 1.6 times its authored girth - and fought the fitted equipment.
## Bodies now render at their authored proportions, and proportion belongs in
## the body meshes themselves.

const STYLE_VERSION := 2
const MATERIAL_FINISH_META := &"eloria_oldcraft_painted_finish"
const AUTHORED_FINISH_META := &"eloria_oldcraft_authored_finish"

## Oldcraft's materials read as painted color blocks rather than polished
## plastic.  These bounds retain authored textures, tint, transparency,
## emission and metallic masks; only the broad highlight response is softened.
const ROUGHNESS_FLOOR := 0.68
const DIELECTRIC_SPECULAR_CEILING := 0.35
## Preserve the authored normal map, but keep its fine relief subordinate to
## the large painted value shapes. The reference shader uses 0.55; 0.65 keeps
## a little more of Eloria's existing equipment detail.
const NORMAL_SCALE_CEILING := 0.65
## Glasswarden crystals are the one actor surface meant to be glossy. Their
## race-feature material is authored opaque, roughness about 0.2, metallic 0,
## no emission, and named for this prefix (glTF material names survive the
## import as the resource name); the painted floor and the specular cap would
## turn the glass back into chalk, so they leave it as authored.
const GLASS_MATERIAL_PREFIX := "Race feature glass"


## Whether a material keeps its authored gloss instead of the painted finish.
static func is_glass(material: Material) -> bool:
	return material != null and material.resource_name.begins_with(
		GLASS_MATERIAL_PREFIX)


## Applies the finish to one mesh without cloning its mesh, skin, materials or
## textures.  Shared imported materials are marked and touched only once.
static func apply_mesh_finish(mesh_instance: MeshInstance3D) -> int:
	if mesh_instance == null or mesh_instance.mesh == null:
		return 0
	var changed := 0
	var seen: Dictionary = {}
	for surface in mesh_instance.mesh.get_surface_count():
		var material := mesh_instance.get_active_material(surface) as BaseMaterial3D
		if material == null:
			continue
		var identity := material.get_instance_id()
		if seen.has(identity):
			continue
		seen[identity] = true
		if not material.has_meta(AUTHORED_FINISH_META):
			material.set_meta(AUTHORED_FINISH_META, {
				"roughness": material.roughness,
				"metallic_specular": material.metallic_specular,
				"normal_scale": material.normal_scale,
			})
		if not is_glass(material):
			material.roughness = maxf(material.roughness, ROUGHNESS_FLOOR)
			material.metallic_specular = minf(material.metallic_specular,
				DIELECTRIC_SPECULAR_CEILING)
		if material.normal_enabled and material.normal_texture != null:
			material.normal_scale = minf(material.normal_scale,
				NORMAL_SCALE_CEILING)
		material.set_meta(MATERIAL_FINISH_META, STYLE_VERSION)
		changed += 1
	return changed


static func apply_surface_finish(root: Node) -> int:
	if root == null:
		return 0
	var changed := 0
	if root is MeshInstance3D:
		changed += apply_mesh_finish(root as MeshInstance3D)
	for value: Node in root.find_children("*", "MeshInstance3D", true, false):
		changed += apply_mesh_finish(value as MeshInstance3D)
	return changed

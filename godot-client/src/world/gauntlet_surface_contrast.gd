extends RefCounted
## Route readability is part of the map, independent of the painted-look setting.
## Apply after the loader's cache snapshot on both fresh and cached maps. Copies
## are shared by source material and role; imported meshes/textures stay untouched.
## Mean path albedo is about 2.5 times verge albedo under the same light. Tune
## in the renderer's shading space; a linear multiplier alone clips snowy GL paths.

const APPLIED_META := &"gauntlet_surface_contrast"
const SOURCE_META := &"gauntlet_surface_source"
const LUMA := Vector3(.2126, .7152, .0722)

static func apply(manifest: WorldManifest, world: Node3D) -> int:
	if world == null or manifest == null or not manifest.data.get("gauntlet") is Dictionary:
		return 0
	var compatibility := RenderingServer.get_current_rendering_method() == "gl_compatibility"
	var copies: Dictionary = {}
	var means: Dictionary = {}
	var changed := 0
	for node: MeshInstance3D in world.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null or node.material_override != null or node.has_meta("static_batch"):
			continue
		var role := surface_role(str(node.name))
		if role.is_empty():
			continue
		for surface: int in node.mesh.get_surface_count():
			var source := node.get_active_material(surface) as BaseMaterial3D
			if source == null or source.has_meta(APPLIED_META) or source.albedo_color.a < .99 \
					or source.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED \
					or source.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED \
					or (source.emission_enabled and role == "wall"):
				continue
			var key := "%d:%s" % [source.get_instance_id(), role]
			if not copies.has(key):
				var copy := source.duplicate() as BaseMaterial3D
				# Compatibility shades StandardMaterial3D in display space. Measure
				# and scale in the renderer's space so bright snow does not clip to
				# white there, hiding the edge even after the verge is darkened.
				var tint := source.albedo_color if compatibility else source.albedo_color.srgb_to_linear()
				var mean := texture_mean(source.albedo_texture, compatibility, means)
				var luma := maxf(LUMA.dot(mean * Vector3(tint.r, tint.g, tint.b)), .015)
				var target := .30 if compatibility else .24
				var limit := 3.0
				if role == "verge":
					target = .12 if compatibility else .09
					limit = .62
				elif role == "wall":
					target = .16 if compatibility else .12
					limit = .78
				var scale := minf(target / luma, limit)
				var adjusted := Color(tint.r * scale, tint.g * scale, tint.b * scale, source.albedo_color.a)
				copy.albedo_color = adjusted if compatibility else adjusted.linear_to_srgb()
				# The amethyst route has luminous road and cliff materials. Their
				# glow follows the same value trim; skipping them hides the route.
				# Emissive wall fixtures and all Props_/Kit_ scenery stay authored.
				if source.emission_enabled:
					var glow := source.emission if compatibility else source.emission.srgb_to_linear()
					glow = Color(glow.r * scale, glow.g * scale, glow.b * scale, glow.a)
					copy.emission = glow if compatibility else glow.linear_to_srgb()
				copy.set_meta(APPLIED_META, true)
				copy.set_meta(SOURCE_META, source)
				copies[key] = copy
			node.set_surface_override_material(surface, copies[key])
			changed += 1
	return changed

static func texture_mean(texture: Texture2D, compatibility: bool, means: Dictionary) -> Vector3:
	if texture == null:
		return Vector3.ONE
	var id := texture.get_instance_id()
	if means.has(id):
		return means[id]
	var image := texture.get_image()
	var mean := Vector3.ONE
	if image != null and not image.is_empty() and (not image.is_compressed() or image.decompress() == OK):
		mean = Vector3.ZERO
		# A stratified 16x16 sample keeps this load-time measurement small,
		# including textures shared between a path, its bank and a wall.
		for y: int in 16:
			for x: int in 16:
				var texel := image.get_pixel(int((x + .5) * image.get_width() / 16.0),
					int((y + .5) * image.get_height() / 16.0))
				if not compatibility:
					texel = texel.srgb_to_linear()
				mean += Vector3(texel.r, texel.g, texel.b) / 256.0
	means[id] = mean
	return mean

static func surface_role(node_name: String) -> String:
	# Walk_Terrain_ground is the traversable part of the trail terrain, often
	# sharing its texture AND material with Terrain_ground. Test Walk_ first.
	if node_name.begins_with("Walk_"):
		return "path"
	if node_name.begins_with("Terrain_"):
		return "verge"
	if node_name.begins_with("Build_") or node_name.begins_with("Roof_"):
		return "wall"
	return ""

class_name LookSwitch
extends RefCounted
## The settings window's "Painted look" and "Graphics quality", applied to a
## world that is already loaded, without reloading its map.
##
## Every layer of the pass applies itself as its map binds or as its region,
## chunk or neighbour is finished (LookGround, LookFoliage), so a switch that
## only changed LookProfile.enabled() would reach the next map load and nothing
## before it. This is what reaches what is already loaded:
##
## - The materials. `revert` puts back, on every mesh under a root, the
##   material each of the look's stand-ins names as its source
##   (LookProfile.SOURCE_META), clears the overrides the crowns put on the
##   loader's static batches, and gives back the seas the look decoded in
##   place; `apply` paints a root again exactly as the loader or main's bind
##   painted it. Both are safe to repeat, and neither makes anything that
##   outlives the switch: a painted material that is put back is released.
## - The roots. `worlds` lists every root the look paints (the active map,
##   and each chunk and neighbour), and `sync` brings one into line with the
##   switch and marks it (LookProfile.stamp). A root a loader worker finished
##   under the switch's old answer is marked stale (LookProfile.enabled_for),
##   and main syncs it as it arrives: that is what makes a switch during a map
##   load or a seamless crossing safe.
## - The shadows. `apply_shadow_quality` gives the sun and the renderer the
##   graphics quality's shadows, look on or off.
##
## The environment and the sun belong to main, which rebinds develop's own
## environment and grades it again (or not); the grass beds follow the switch
## and the quality by themselves (LookGrassBeds.tend).

## Where the pass's own shaders live: a material drawn by one of them is the
## look's (`look_surfaces`).
const LOOK_SHADERS := "res://src/world/look/"

## Every root the look paints among `active` (the loader's world root: a
## ContinentChunkStream on a chunked territory, whose cells are the roots),
## bound from `manifest`, and `residents` (ExteriorRegionStream.residents), as
## {"root", "manifest", "bound"}. `bound` is true for the active map only: a
## map outside the continent is painted by main's bind, never as a neighbour.
static func worlds(active: Node, manifest: WorldManifest, residents: Dictionary) -> Array[Dictionary]:
	var found: Array[Dictionary] = []
	_include(found, active, manifest, true)
	for resident: Variant in residents.values():
		if resident is Dictionary:
			_include(found, (resident as Dictionary).get("root"),
				(resident as Dictionary).get("manifest") as WorldManifest, false)
	return found

static func _include(found: Array[Dictionary], root: Variant, manifest: WorldManifest,
		bound: bool) -> void:
	if not is_instance_valid(root) or root is not Node or manifest == null \
			or (root as Node).is_queued_for_deletion():
		return
	if root is ContinentChunkStream:
		for cell: Variant in (root as ContinentChunkStream).cells.values():
			if cell is Dictionary:
				_include(found, (cell as Dictionary).get("root"),
					(cell as Dictionary).get("manifest") as WorldManifest, false)
		return
	found.append({"root": root, "manifest": manifest, "bound": bound})

## Brings `root` into line with the switch: paints it (`apply`) while the look
## is on, takes the look off it (`revert`) while it is off, and marks it as
## following the switch's current answer. Returns the surfaces changed.
static func sync(root: Node, manifest: WorldManifest, bound := false) -> int:
	var changed := apply(root, manifest, bound) if LookProfile.enabled() else revert(root)
	LookProfile.stamp(root)
	return changed

## Paints `root` as it would have been painted had the look been on when it
## loaded: a continent map, chunk or neighbour as the loader paints it (its
## ground, crowns and kept colours), and a map outside the continent as main's
## bind paints it, when it is the `bound` one. Returns the surfaces painted.
static func apply(root: Node, manifest: WorldManifest, bound := false) -> int:
	if root == null or manifest == null or not LookProfile.enabled():
		return 0
	if manifest.data.has("continentGeography"):
		return LookGround.paint_loaded(root, manifest) + LookFoliage.paint_loaded(root, manifest)
	return LookGround.paint_bound(root, manifest) if bound else 0

## Takes the look off everything under `root`: every surface drawn by one of
## its stand-ins gets back the material the stand-in names (none, where that
## is the mesh's own), a static batch loses the override a crown or a kept
## colour put on it, and a sea the look decoded in place (its scene script's
## own material, which it still animates) forgets the look's parameters.
## Returns the surfaces and meshes changed.
static func revert(root: Node) -> int:
	if root == null:
		return 0
	var changed := 0
	for node: Node in root.find_children("*", "GeometryInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance != null:
			for surface: int in mesh_instance.get_surface_override_material_count():
				var current := mesh_instance.get_surface_override_material(surface)
				if current == null or not current.has_meta(LookProfile.SOURCE_META):
					continue
				var original := source_of(current)
				var own: Material = mesh_instance.mesh.surface_get_material(surface) \
					if mesh_instance.mesh != null and surface < mesh_instance.mesh.get_surface_count() \
					else null
				mesh_instance.set_surface_override_material(surface,
					null if original == own else original)
				changed += 1
		var geometry := node as GeometryInstance3D
		var override := geometry.material_override
		if override == null:
			continue
		if node is MultiMeshInstance3D and override.has_meta(LookProfile.SOURCE_META):
			# The loader never gives a batch an override; the crowns did.
			geometry.material_override = null
			changed += 1
		elif override is ShaderMaterial and undecode(override as ShaderMaterial):
			changed += 1
	if changed > 0:
		print("look_switch stage=reverted root=%s changed=%d" % [root.name, changed])
	return changed

## The material `material` stands in for, following a stand-in of a stand-in
## (a kept colour over a decoded pool) back to the loader's own.
static func source_of(material: Material) -> Material:
	var found := material
	var hops := 0
	while found != null and found.has_meta(LookProfile.SOURCE_META) and hops < 8:
		found = found.get_meta(LookProfile.SOURCE_META) as Material
		hops += 1
	return found

## Gives a sea decoded in place (LookGround.decode_water) its own colours back:
## the look's parameters are cleared, which leaves the shader's defaults, as
## on a client that never had the look. Returns whether it had been decoded.
static func undecode(material: ShaderMaterial) -> bool:
	if material.get_shader_parameter(&"look_decode_albedo") != true:
		return false
	material.set_shader_parameter(&"look_decode_albedo", null)
	material.set_shader_parameter(&"look_sea_value", null)
	return true

## How many surfaces and meshes under `root` still draw something of the
## look's: a stand-in, a batch override or a decoded sea. 0 once the look is
## switched off; for tests and probes.
static func look_surfaces(root: Node) -> int:
	if root == null:
		return 0
	var count := 0
	for node: Node in root.find_children("*", "GeometryInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance != null:
			for surface: int in mesh_instance.get_surface_override_material_count():
				if _looks(mesh_instance.get_surface_override_material(surface)):
					count += 1
		if _looks((node as GeometryInstance3D).material_override):
			count += 1
	return count

static func _looks(material: Material) -> bool:
	if material == null:
		return false
	if material.has_meta(LookProfile.SOURCE_META):
		return true
	var shader_material := material as ShaderMaterial
	if shader_material == null:
		return false
	if shader_material.get_shader_parameter(&"look_decode_albedo") == true:
		return true
	return shader_material.shader != null \
		and shader_material.shader.resource_path.begins_with(LOOK_SHADERS)

## Gives the sun's shadows the graphics quality's cascades, and the renderer
## its shadow atlas and edge filters. They are the renderer's, so they apply
## whether the look is on or off, and at HIGH they are Godot's defaults, as
## the client always drew them. The atlas and the filters are global to the
## renderer; the cascades are the sun's, the scene's one shadow-casting light,
## which outlives every map and which no binder re-aims them on.
static func apply_shadow_quality(sun: DirectionalLight3D) -> void:
	RenderingServer.directional_shadow_atlas_set_size(
		int(LookProfile.quality_value("shadow_atlas")), LookProfile.SHADOW_ATLAS_16_BITS)
	var filter := int(LookProfile.quality_value("shadow_filter")) as RenderingServer.ShadowQuality
	RenderingServer.directional_soft_shadow_filter_set_quality(filter)
	RenderingServer.positional_soft_shadow_filter_set_quality(filter)
	if sun == null:
		return
	match int(LookProfile.quality_value("shadow_splits")):
		1:
			sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
		2:
			sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
		_:
			sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS

extends SceneTree
## Lantern Mine lighting is applied every frame the player is in the mine.
## Repeated frames must keep the lit result exactly while doing no repeated
## work: the section's lamps are found once per section, the clock's regrading
## is still undone, and Compatibility's nearest-eight lamp choice is made again
## only once the focus has moved a metre.
const Lighting := preload("res://src/world/lantern_mine_lighting.gd")
const MarkerBinder := preload("res://src/world/light_marker_binder.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(value: bool, message: String) -> void:
	checks += 1
	if value: print("PASS: ", message)
	else: failures += 1; push_error("FAIL: " + message)

func _lit_gates(lamps: Array) -> int:
	var lit := 0
	# A typed loop variable would cast a freed lamp before the check.
	for lamp: Variant in lamps:
		if is_instance_valid(lamp) and (lamp as OmniLight3D).is_visible_in_tree(): lit += 1
	return lit

func run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Mine lighting frame checks timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var manifest := WorldManifest.new()
	manifest.data = JSON.parse_string(FileAccess.get_file_as_string("res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"))
	var owner := WorldEnvironment.new(); root.add_child(owner)
	var original := Environment.new(); original.ambient_light_energy = 0.55; owner.environment = original
	var sun := DirectionalLight3D.new(); root.add_child(sun); sun.light_energy = 0.8
	var moon := DirectionalLight3D.new(); root.add_child(moon); moon.light_energy = 0.3
	var markers := Node3D.new(); root.add_child(markers)
	MarkerBinder.apply(manifest, markers)
	var mine_lamp := markers.get_node("lantern_mine-lamp-0") as OmniLight3D
	var native_energy := mine_lamp.light_energy
	var native_range := mine_lamp.omni_range
	var lighting := Lighting.new()
	lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	var dark := owner.environment
	var first_lamps := lighting.lamps.duplicate()
	expect(lighting.is_active() and first_lamps.size() == 18, "the mine's eighteen lamps are found on entry")
	for frame: int in range(5):
		lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	expect(owner.environment == dark and lighting.lamps == first_lamps,
		"later frames keep the same environment and the same lamps")
	var warm := true
	for lamp: OmniLight3D in lighting.lamps:
		warm = warm and is_equal_approx(lamp.light_energy, Lighting.LANTERN_ENERGY) \
			and is_equal_approx(lamp.omni_range, Lighting.LANTERN_RANGE) and lamp.light_color == Color(1.0, 0.7, 0.4)
	expect(warm, "the lamps stay lit across frames")
	# The clock's regrading writes the shared environment and the sun between
	# frames; the next frame takes it back.
	dark.ambient_light_energy = 0.9; dark.fog_enabled = true; dark.background_mode = Environment.BG_SKY
	sun.light_energy = 0.7
	lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	expect(is_equal_approx(dark.ambient_light_energy, Lighting.AMBIENT_ENERGY) and not dark.fog_enabled
		and dark.background_mode == Environment.BG_COLOR and is_zero_approx(sun.light_energy),
		"a regraded environment and sun are put back on the next frame")
	# Another section finds its own lamps again.
	lighting.apply(manifest, "old_seam", owner, sun, moon, markers)
	var seam := true
	for lamp: OmniLight3D in lighting.lamps:
		seam = seam and str(lamp.name).begins_with("old_seam-lamp-")
	expect(seam and not lighting.lamps.is_empty(), "moving to another mine section rebinds that section's lamps")
	expect(mine_lamp.light_energy == native_energy and mine_lamp.omni_range == native_range,
		"the section left behind gets its native lamps back")

	# Compatibility's per-mesh light budget: the nearest eight lamps, chosen
	# again only after the focus has moved a metre.
	lighting.apply(manifest, "lantern_upper_galleries", owner, sun, moon, markers)
	lighting.set("_compatibility", true)
	var focus := Vector3(605, 0, 121)
	lighting.apply(manifest, "lantern_upper_galleries", owner, sun, moon, markers, focus)
	var lamps: Array = lighting.lamps.duplicate()
	expect(lamps.size() > Lighting.COMPATIBILITY_LIGHT_LIMIT and _lit_gates(lamps) == Lighting.COMPATIBILITY_LIGHT_LIMIT,
		"Compatibility lights the nearest eight lamps")
	# Show every gate by hand: a frame that does not choose again leaves them.
	for lamp: OmniLight3D in lamps:
		(lamp.get_parent() as Node3D).visible = true
	lighting.apply(manifest, "lantern_upper_galleries", owner, sun, moon, markers, focus + Vector3(0.5, 0, 0))
	expect(_lit_gates(lamps) == lamps.size(), "a focus that moved half a metre keeps the last choice")
	lighting.apply(manifest, "lantern_upper_galleries", owner, sun, moon, markers, focus + Vector3(3, 0, 0))
	expect(_lit_gates(lamps) == Lighting.COMPATIBILITY_LIGHT_LIMIT, "a focus that moved three metres chooses again")
	# A lamp freed under the lighting is skipped rather than failing the pass.
	(lamps[0] as OmniLight3D).free()
	lighting.apply(manifest, "lantern_upper_galleries", owner, sun, moon, markers, focus + Vector3(9, 0, 0))
	expect(_lit_gates(lamps) == Lighting.COMPATIBILITY_LIGHT_LIMIT, "a freed lamp is skipped when choosing again")
	lighting.before_regrade(WorldManifest.new(), "")
	expect(not lighting.is_active() and owner.environment == original and is_equal_approx(sun.light_energy, 0.7),
		"leaving restores the environment and the sun")
	markers.free(); lighting.clear()
	owner.free(); sun.free(); moon.free()
	await process_frame
	print("Lantern Mine lighting frames: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

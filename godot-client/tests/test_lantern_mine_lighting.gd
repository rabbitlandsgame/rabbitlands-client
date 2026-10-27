extends SceneTree
## Standard cave lighting uses the published region and its existing lamps.
const Lighting := preload("res://src/world/lantern_mine_lighting.gd")
const Presenter := preload("res://src/world/campaign_rescue_presentation.gd")
const MarkerBinder := preload("res://src/world/light_marker_binder.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if value: print("PASS: ", message)
	else: failures += 1; push_error(message)

func run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Mine lighting checks timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var manifest := WorldManifest.new()
	manifest.data = JSON.parse_string(FileAccess.get_file_as_string("res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"))
	var exterior := WorldManifest.new(); exterior.data = {"asset":{"id":"landfall"}}
	expect(manifest.asset_id() == "landfall_insides" and manifest.data.sections.size() > 10,
		"the current published underground includes many independent sections")
	expect(Lighting.section_at(manifest, Vector3(55, 0, 688)) == "lantern_mine"
		and Lighting.section_at(manifest, Vector3(177, 0, 688)) == "pinebrow_workings",
		"actual published bounds distinguish Lantern Mine from neighboring interiors")
	var owner := WorldEnvironment.new(); root.add_child(owner)
	var original := Environment.new(); original.ambient_light_energy = 0.55; owner.environment = original
	var sun := DirectionalLight3D.new(); root.add_child(sun); sun.light_energy = 0.8
	var moon := DirectionalLight3D.new(); root.add_child(moon); moon.light_energy = 0.3
	var markers := Node3D.new(); root.add_child(markers)
	var marker_count := MarkerBinder.apply(manifest, markers)
	var daylight := markers.get_node("lantern_mine-daylight") as OmniLight3D
	var native := markers.get_node("lantern_mine-lamp-0") as OmniLight3D
	var other := markers.get_node("pinebrow_workings-lamp-0") as OmniLight3D
	var other_energy := other.light_energy
	var daylight_energy := daylight.light_energy
	var native_energy := native.light_energy
	var native_range := native.omni_range
	var lighting := Lighting.new()
	lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	expect(lighting.is_active() and is_equal_approx(owner.environment.ambient_light_energy, 0.003),
		"entering the mine is dark without a quest, cinematic, event or campaign snapshot")
	expect(is_zero_approx(sun.light_energy) and is_zero_approx(moon.light_energy)
		and owner.environment.reflected_light_source == Environment.REFLECTION_SOURCE_DISABLED
		and is_zero_approx(owner.environment.ambient_light_sky_contribution),
		"sun, moon, sky ambient and reflected fill cannot wash out the dark mine")
	var warm := lighting.lamps.size() == 10
	for lamp: OmniLight3D in lighting.lamps:
		warm = warm and is_equal_approx(lamp.light_energy, 2.4) and is_equal_approx(lamp.omni_range, 16.0)
		warm = warm and lamp.light_color == Color(1.0, 0.7, 0.4)
	expect(warm and markers.get_child_count() == marker_count,
		"all ten existing native lanterns provide broad warm pools without duplicate lights")
	expect(is_zero_approx(daylight.light_energy) and daylight.visible and other.light_energy == other_energy,
		"only Lantern Mine's artificial daylight fill is suppressed; room visibility stays owned by sections")
	var dark := owner.environment
	lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	expect(owner.environment == dark and markers.get_child_count() == marker_count,
		"repeated frame updates reuse one environment and the same real marker lights")
	owner.environment.ambient_light_energy = 0.9; sun.light_energy = 0.6; moon.light_energy = 0.2
	lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	expect(is_equal_approx(owner.environment.ambient_light_energy, 0.003) and is_zero_approx(sun.light_energy)
		and is_zero_approx(moon.light_energy), "ordinary clock regrading cannot brighten the mine between scenes")
	var presenter := Presenter.new(); root.add_child(presenter)
	presenter.apply_snapshot({}, CoordinateAdapter.new(), "landfall_insides", func(_at: Vector3) -> float: return 0.0)
	presenter.apply_environment(owner, sun, moon)
	presenter.clear()
	expect(owner.environment == dark and lighting.is_active() and is_equal_approx(native.light_energy, 2.4),
		"clearing an absent, skipped or finished rescue cannot remove standard mine lighting")
	# SecretSections may hide these before room transition. The lighting lease
	# never writes visibility when restoring its energy/range changes.
	daylight.hide(); native.hide()
	lighting.before_regrade(manifest, "pinebrow_workings")
	expect(owner.environment == original and is_equal_approx(original.ambient_light_energy, 0.55)
		and is_equal_approx(sun.light_energy, 0.6) and is_equal_approx(moon.light_energy, 0.2),
		"leaving for another underground section restores its normal environment before regrading")
	expect(native.light_energy == native_energy and native.omni_range == native_range
		and daylight.light_energy == daylight_energy and not native.visible and not daylight.visible,
		"leaving restores marker values while preserving the section cull's hidden state")
	lighting.apply(manifest, "pinebrow_workings", owner, sun, moon, markers)
	expect(not lighting.is_active() and owner.environment == original and other.light_energy == other_energy,
		"unrelated underground rooms retain their existing atmosphere and lamps")
	lighting.apply(exterior, "lantern_mine", owner, sun, moon, markers)
	expect(not lighting.is_active(), "an identically named section on another map cannot acquire mine lighting")
	var stage_markers := Node3D.new(); root.add_child(stage_markers); MarkerBinder.apply(manifest, stage_markers)
	expect(lighting.set_cinematic_region(manifest, Vector3(55, 0, 660), stage_markers),
		"a scoped cutaway can select the real published mine by stage focus while its player remains outdoors")
	lighting.apply(exterior, "", owner, sun, moon, markers)
	expect(lighting.is_active() and native.light_energy == native_energy
		and is_equal_approx((stage_markers.get_node("lantern_mine-lamp-0") as OmniLight3D).light_energy, 2.4),
		"the cinematic context lights only its existing stage lamps instead of unrelated outdoor markers")
	lighting.clear_cinematic_region(); lighting.before_regrade(exterior, "")
	expect(not lighting.is_active() and owner.environment == original,
		"cutaway fade-out restores ordinary outdoor lighting independently of the real player's location")
	expect(not lighting.set_cinematic_region(manifest, Vector3(177, 0, 688), stage_markers),
		"a cutaway focus in Pinebrow cannot activate Lantern Mine's profile")
	lighting.apply(exterior, "", owner, sun, moon, markers)
	expect(owner.environment == original, "invalid or ended cinematic overrides fail back to normal gameplay")
	lighting.apply(manifest, "lantern_mine", owner, sun, moon, markers)
	markers.free(); lighting.clear()
	expect(owner.environment == original and not lighting.is_active(), "map exit cleans up safely even when native marker nodes have already been freed")
	presenter.free(); owner.free(); sun.free(); moon.free(); stage_markers.free()
	await process_frame
	print("Lantern Mine lighting: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

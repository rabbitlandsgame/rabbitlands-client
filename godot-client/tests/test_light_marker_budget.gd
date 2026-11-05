extends SceneTree
## One marker-light budget (LightMarkerBudget): the nearest N marker lights to
## the camera's focus burn, N by quality (6/12/24) and never more than the
## renderer lights on one mesh (8 in Mobile and Compatibility). Lights fade
## 0.3 s when the focus moves, come on at once with a room SecretSections
## shows, never have their own `visible` written, and a LanternMineLighting
## lamp's energy is never touched. The night-lamp and fire pools keep 6 + 2 on
## those renderers.
##
## Last: the Landfall Town and Landfall Insides markers, sorted by
## SecretSections as in the game, walked across 20 focus points each under
## Forward+, Mobile and Compatibility at LOW, MEDIUM and HIGH: on the limited
## renderers no more than 8 marker lights are ever drawn, mid-fade too.

const Budget := preload("res://src/world/light_marker_budget.gd")
const RendererFamily := preload("res://src/runtime/renderer_family.gd")
const Lighting := preload("res://src/world/lantern_mine_lighting.gd")
const METHODS: Array[String] = ["forward_plus", "mobile", "gl_compatibility"]
const LOW := 0
const MEDIUM := 1
const HIGH := 2

var checks := 0
var failures := 0
var _clock := 0.0

func _init() -> void:
	run.call_deferred()

func expect(value: bool, message: String) -> void:
	checks += 1
	if value:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func run() -> void:
	create_timer(600).timeout.connect(func() -> void:
		push_error("light budget checks timed out")
		quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	_limits()
	_weather_fires()
	_few_lights_untouched()
	_nearest_and_hysteresis()
	_fades_forward_plus()
	_fades_limited()
	await _sections_and_signals()
	await _hidden_root_shown_again()
	_leases_and_outside_writes()
	_zero_energy_and_release()
	_lantern_mine_with_budget()
	_mine_entered_mid_fade()
	await _main_hook()
	await _town_high_untouched()
	for map: String in ["landfall_town", "landfall_insides"]:
		await _walk_map(map)
	RendererFamily.override_for_tests("")
	await process_frame
	print("Light marker budget: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

# --- limits ------------------------------------------------------------------

func _limits() -> void:
	for method: String in METHODS:
		var limited := method != "forward_plus"
		var budget := [Budget.light_limit(LOW, method), Budget.light_limit(MEDIUM, method),
			Budget.light_limit(HIGH, method)]
		expect(budget == ([6, 8, 8] if limited else [6, 12, 24]),
			"%s marker lights by quality LOW/MEDIUM/HIGH: %s" % [method, budget])
		var lamps := [NightLamps.light_limit(LOW, method), NightLamps.light_limit(MEDIUM, method),
			NightLamps.light_limit(HIGH, method)]
		var fires := [Weather3D.fire_light_limit(LOW, method), Weather3D.fire_light_limit(MEDIUM, method),
			Weather3D.fire_light_limit(HIGH, method)]
		if limited:
			expect(lamps == [4, 6, 6] and fires == [2, 2, 2],
				"%s night lamps %s and fires %s: 8 together at most on a chunk's ground" % [method, lamps, fires])
		else:
			expect(lamps == NightLamps.LIGHTS_BY_QUALITY and fires == Weather3D.FIRE_LIGHTS_BY_QUALITY,
				"Forward+ keeps the night-lamp %s and fire %s pools exactly" % [lamps, fires])
	RendererFamily.override_for_tests("mobile")
	expect(Budget.light_limit(HIGH) == 8 and NightLamps.light_limit(HIGH) == 6
		and Weather3D.fire_light_limit(HIGH) == 2, "the renderer in use decides when none is named")
	RendererFamily.override_for_tests("")
	expect(Budget.light_limit(HIGH, "some_future_method") == 24,
		"a method the client does not know has no per-mesh limit")

func _weather_fires() -> void:
	var layer := Weather3D.new()
	root.add_child(layer)
	layer.set_effects_enabled(true)
	for index: int in 10:
		layer.place_fire(Vector3(index, 0, 0), 0, Vector2i(index, 0))
	var before := LookProfile.player_quality()
	for method: String in METHODS:
		RendererFamily.override_for_tests(method)
		for quality: int in [LOW, MEDIUM, HIGH]:
			LookProfile.set_player_quality(quality)
			layer.refresh_graphics()
			var glowing := 0
			for tile: Variant in layer.fire_tiles():
				var fire := (layer.get("_fires") as Dictionary)[tile] as Node
				if (fire.get_node("Glow") as OmniLight3D).visible:
					glowing += 1
			expect(glowing == Weather3D.fire_light_limit(quality, method)
				and glowing == (2 if method != "forward_plus" else Weather3D.FIRE_LIGHTS_BY_QUALITY[quality]),
				"%s quality %d: %d of 10 fires give light" % [method, quality, glowing])
	RendererFamily.override_for_tests("")
	LookProfile.set_player_quality(before)
	layer.free()

# --- a row of lights ---------------------------------------------------------

## `count` marker lights 2 m apart along x, 1 m up, energy 2, under a new root.
func _row(count: int, energy := 2.0) -> Array:
	var lights_root := Node3D.new()
	lights_root.name = "MapLights"
	root.add_child(lights_root)
	var markers: Array = []
	for index: int in count:
		markers.append({"id": "row-%d" % index, "position": [index * 2.0, 1.0, 0.0],
			"energyHint": energy, "rangeHint": 6.0})
	var manifest := WorldManifest.new()
	manifest.data = {"lighting": {"markers": markers}}
	LightMarkerBinder.apply(manifest, lights_root)
	var lights: Array = lights_root.get_children()
	return [lights_root, lights]

func _drawn(lights: Array) -> PackedInt32Array:
	var out := PackedInt32Array()
	for index: int in lights.size():
		var value: Variant = lights[index]
		if is_instance_valid(value) and (value as OmniLight3D).is_visible_in_tree():
			out.append(index)
	return out

func _tick(budget: RefCounted, focus: Vector3, seconds: float) -> void:
	_clock += seconds
	budget.call("update", focus, _clock)

func _at(x: float) -> Vector3:
	return Vector3(x, 0.0, 0.0)

func _few_lights_untouched() -> void:
	var made := _row(5)
	var lights_root: Node3D = made[0]
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(lights_root)
	expect(LightMarkerBinder.budgeted(lights_root), "a bound root is marked for the other light users")
	_tick(budget, _at(0), 0.1)
	_tick(budget, _at(30), 0.5)
	var intact := lights_root.get_child_count() == 5
	for child: Node in lights_root.get_children():
		intact = intact and child is OmniLight3D and (child as OmniLight3D).is_visible_in_tree() \
			and is_equal_approx((child as OmniLight3D).light_energy, 2.0)
	expect(intact, "five lights under a budget of six keep the tree exactly as bound, no gate added")
	budget.bind(null)
	expect(not LightMarkerBinder.budgeted(lights_root), "letting go unmarks the root")
	lights_root.free()

func _nearest_and_hysteresis() -> void:
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	expect(_drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5]),
		"LOW lights the six nearest at once on binding: %s" % _drawn(lights))
	var untouched := true
	for value: Variant in lights:
		var light := value as OmniLight3D
		untouched = untouched and light.visible and is_equal_approx(light.light_energy, 2.0)
	expect(untouched, "the lights' own visibility and energy are left as bound")
	var gated := 0
	for value: Variant in lights:
		var gate := LightMarkerBinder.gate_of(value as OmniLight3D)
		if gate != null:
			gated += 1
			expect(str(gate.name) == LightMarkerBinder.GATE_PREFIX + str((value as Node).name)
				and gate.get_parent() == lights_root and gate.transform == Transform3D.IDENTITY,
				"a gate sits between its light and the root at the root's origin")
	expect(gated == 6, "only the six lights that went out got a gate: %d" % gated)
	_tick(budget, _at(4), 0.25)
	expect(_drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5]),
		"a focus inside the lit group changes nothing")
	_tick(budget, _at(10), 0.25)
	_tick(budget, _at(10), 0.5)
	expect(_drawn(lights) == PackedInt32Array([1, 2, 3, 4, 5, 6]),
		"the four nearest always burn; the last two slots keep lit lamps within rank 8 (1 and 2 stay, 7 waits): %s"
			% _drawn(lights))
	_tick(budget, _at(12), 0.25)
	_tick(budget, _at(12), 0.5)
	expect(_drawn(lights) == PackedInt32Array([2, 3, 4, 5, 6, 7]),
		"a lamp that fell to rank 8 hands its slot over: %s" % _drawn(lights))
	budget.quality_override = HIGH
	_tick(budget, _at(12), 0.25)
	expect(_drawn(lights).size() == 12, "HIGH (24) lights all twelve")
	budget.quality_override = MEDIUM
	_tick(budget, _at(12), 0.25)
	_tick(budget, _at(12), 0.5)
	expect(_drawn(lights).size() == 12, "MEDIUM (12) in Forward+ keeps all twelve")
	RendererFamily.override_for_tests("gl_compatibility")
	_tick(budget, _at(12), 0.25)
	_tick(budget, _at(12), 0.5)
	expect(_drawn(lights).size() == 8, "MEDIUM in Compatibility keeps the per-mesh 8: %s" % _drawn(lights))
	RendererFamily.override_for_tests("")
	budget.bind(null)
	lights_root.free()

func _fades_forward_plus() -> void:
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	var leaving := lights[0] as OmniLight3D
	var coming := lights[6] as OmniLight3D
	_tick(budget, _at(10), 0.25)
	expect(leaving.is_visible_in_tree() and is_equal_approx(leaving.light_energy, 2.0)
		and coming.is_visible_in_tree() and is_zero_approx(coming.light_energy),
		"Forward+: the light that leaves starts fading out while the new one starts from dark")
	_tick(budget, _at(10), 0.15)
	expect(absf(leaving.light_energy - 1.0) < 0.05 and absf(coming.light_energy - 1.0) < 0.05,
		"halfway through 0.3 s both are at half energy: %.2f / %.2f" % [leaving.light_energy, coming.light_energy])
	expect(_drawn(lights).size() == 7, "Forward+ fades the two across each other (one extra light for 0.3 s)")
	_tick(budget, _at(10), 0.16)
	expect(not leaving.is_visible_in_tree() and is_equal_approx(leaving.light_energy, 2.0)
		and coming.is_visible_in_tree() and is_equal_approx(coming.light_energy, 2.0),
		"after 0.3 s the old light is out at its own energy, the new one fully on")
	expect(leaving.visible, "going out never wrote the light's own visibility")
	budget.bind(null)
	lights_root.free()

func _fades_limited() -> void:
	RendererFamily.override_for_tests("mobile")
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = MEDIUM
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	expect(_drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5, 6, 7]), "Mobile MEDIUM lights eight")
	var most := 0
	_tick(budget, _at(14), 0.05)
	most = maxi(most, _drawn(lights).size())
	expect(_drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5, 6, 7]),
		"under the per-mesh limit the two leaving keep their slots while they fade; 8 and 9 wait")
	for step: int in 20:
		_tick(budget, _at(14), 0.05)
		most = maxi(most, _drawn(lights).size())
	expect(most <= 8, "never more than eight drawn, mid-fade too: %d" % most)
	expect(_drawn(lights) == PackedInt32Array([2, 3, 4, 5, 6, 7, 8, 9]),
		"once the two are out the waiting two come on: %s" % _drawn(lights))
	var settled := true
	for value: Variant in lights:
		settled = settled and is_equal_approx((value as OmniLight3D).light_energy, 2.0)
	expect(settled, "every light ends at its own energy")
	# LOW (6) under the same limit has two spare slots, so it fades across.
	budget.quality_override = LOW
	_tick(budget, _at(14), 0.25)
	_tick(budget, _at(14), 0.5)
	most = 0
	_tick(budget, _at(0), 0.25)
	for step: int in 12:
		most = maxi(most, _drawn(lights).size())
		_tick(budget, _at(0), 0.05)
	expect(most <= 8 and _drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5]),
		"Mobile LOW walks back to the six nearest without passing eight: %d %s" % [most, _drawn(lights)])
	budget.bind(null)
	lights_root.free()
	RendererFamily.override_for_tests("")

func _sections_and_signals() -> void:
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	# SecretSections hides the three nearest (another room): no update call;
	# the visibility signal has the budget choose again before the frame.
	for index: int in 3:
		(lights[index] as OmniLight3D).visible = false
	await process_frame
	var drawn := _drawn(lights)
	expect(drawn == PackedInt32Array([3, 4, 5, 6, 7, 8]),
		"hidden lights are not counted; the next nearest take their slots before the next frame: %s" % drawn)
	expect(not (lights[0] as OmniLight3D).visible and not (lights[1] as OmniLight3D).visible,
		"the hidden lights stay hidden: SecretSections owns their visibility")
	_tick(budget, _at(0), 0.5)
	for index: int in 3:
		(lights[index] as OmniLight3D).visible = true
	await process_frame
	var back := lights[0] as OmniLight3D
	expect(back.is_visible_in_tree() and is_equal_approx(back.light_energy, 2.0),
		"a light shown with its room comes on at once at full energy, no fade")
	_tick(budget, _at(0), 0.5)
	expect(_drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5]), "and the far three go out again")
	# The root hidden (a cutaway's stage): nothing counts, nothing is written.
	lights_root.visible = false
	await process_frame
	expect(_drawn(lights).is_empty() and (budget.stats().counted as int) == 0,
		"a hidden root counts no light")
	lights_root.visible = true
	await process_frame
	expect(_drawn(lights) == PackedInt32Array([0, 1, 2, 3, 4, 5]), "shown again, the six nearest at once")
	budget.bind(null)
	lights_root.free()

## A root hidden (a cutaway's stage) while its room changes, then shown again
## with every light it shows behind a shut gate: the root's being shown reaches
## none of those lights, so the budget must hear it from the root itself.
func _hidden_root_shown_again() -> void:
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	_tick(budget, _at(22), 0.25)
	for step: int in 10:
		_tick(budget, _at(22), 0.1)
	var lit := _drawn(lights)
	expect(lit.size() == 6 and not lit.has(0), "walked to the far end, six burn there: %s" % lit)
	lights_root.visible = false
	await process_frame
	# SecretSections hides the lit room while the root is hidden.
	for index: int in lit:
		(lights[index] as OmniLight3D).visible = false
	await process_frame
	var others := PackedInt32Array()
	for index: int in lights.size():
		if not lit.has(index):
			others.append(index)
	lights_root.visible = true
	await process_frame
	expect(_drawn(lights) == others,
		"the root shown again lights the room it shows before the frame, though no light heard of it: %s"
			% _drawn(lights))
	_tick(budget, _at(22), 0.25)
	expect(_drawn(lights) == others, "and keeps it lit: %s" % _drawn(lights))
	budget.bind(null)
	lights_root.free()

func _leases_and_outside_writes() -> void:
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	var held := lights[6] as OmniLight3D
	held.set_meta(LightMarkerBinder.LEASE_META, "test")
	held.light_energy = 3.0
	_tick(budget, _at(12), 0.25)
	expect(held.is_visible_in_tree() and is_equal_approx(held.light_energy, 3.0),
		"a leased light comes on at once, its energy untouched")
	var steady := true
	for step: int in 8:
		_tick(budget, _at(12), 0.05)
		steady = steady and is_equal_approx(held.light_energy, 3.0)
	expect(steady, "no fade writes a leased light's energy")
	_tick(budget, _at(0), 0.25)
	expect(not held.is_visible_in_tree() and is_equal_approx(held.light_energy, 3.0),
		"a leased light goes out at once, energy still its owner's")
	held.remove_meta(LightMarkerBinder.LEASE_META)
	_tick(budget, _at(0), 0.5)
	# Another system writes a light's energy while it fades out: its value wins.
	var fading := lights[0] as OmniLight3D
	_tick(budget, _at(14), 0.25)
	_tick(budget, _at(14), 0.1)
	fading.light_energy = 5.0
	_tick(budget, _at(14), 0.05)
	expect(not fading.is_visible_in_tree() and is_equal_approx(fading.light_energy, 5.0),
		"an energy written by someone else mid-fade is kept and the fade ends")
	budget.bind(null)
	lights_root.free()

func _zero_energy_and_release() -> void:
	RendererFamily.override_for_tests("gl_compatibility")
	var made := _row(12)
	var lights_root: Node3D = made[0]
	var lights: Array = made[1]
	var budget := Budget.new()
	budget.quality_override = HIGH
	budget.bind(lights_root)
	_tick(budget, _at(0), 0.1)
	var dark := lights[1] as OmniLight3D
	dark.light_energy = 0.0
	var masked := lights[2] as OmniLight3D
	masked.light_cull_mask = 0
	_tick(budget, _at(0), 0.25)
	_tick(budget, _at(0), 0.5)
	expect(not dark.is_visible_in_tree() and not masked.is_visible_in_tree() and dark.visible and masked.visible,
		"a shown light at zero energy or with mask 0 is gated out: it would still take a per-mesh slot")
	expect(_drawn(lights) == PackedInt32Array([0, 3, 4, 5, 6, 7, 8, 9]),
		"their slots go to the next nearest: %s" % _drawn(lights))
	dark.light_energy = 2.0
	masked.light_cull_mask = 0xFFFFF
	(lights[11] as OmniLight3D).free()
	_tick(budget, _at(22), 0.25)
	expect(_drawn(lights).size() <= 8, "a freed light is skipped")
	budget.release()
	var open := true
	for value: Variant in lights:
		if not is_instance_valid(value):
			continue
		var light := value as OmniLight3D
		open = open and light.is_visible_in_tree() and is_equal_approx(light.light_energy, 2.0)
	expect(open and not LightMarkerBinder.budgeted(lights_root),
		"letting go opens every gate at every light's own energy")
	lights_root.free()
	RendererFamily.override_for_tests("")

func _lantern_mine_with_budget() -> void:
	var manifest := WorldManifest.new()
	manifest.data = JSON.parse_string(FileAccess.get_file_as_string(
		"res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"))
	var owner := WorldEnvironment.new()
	root.add_child(owner)
	owner.environment = Environment.new()
	var markers := Node3D.new()
	root.add_child(markers)
	LightMarkerBinder.apply(manifest, markers)
	RendererFamily.override_for_tests("mobile")
	var lighting := Lighting.new()
	var focus := Vector3(605, 0, 121)
	# Without a budget (a cutaway's stage lights), Mobile now limits too.
	lighting.apply(manifest, "lantern_upper_galleries", owner, null, null, markers, focus)
	var lit := 0
	var gates_named := true
	for lamp: OmniLight3D in lighting.lamps:
		if lamp.is_visible_in_tree():
			lit += 1
		var gate := LightMarkerBinder.gate_of(lamp)
		gates_named = gates_named and gate != null and str(gate.name).begins_with(LightMarkerBinder.GATE_PREFIX)
		expect(lamp.has_meta(LightMarkerBinder.LEASE_META), "a mine lamp carries the mine's lease")
	expect(lit == Lighting.COMPATIBILITY_LIGHT_LIMIT and gates_named,
		"Mobile without a budget: the mine keeps its nearest eight lamps through the shared gates")
	lighting.before_regrade(WorldManifest.new(), "")
	var clean := true
	for node: Node in markers.get_children():
		if node.is_queued_for_deletion():
			continue
		clean = clean and node is OmniLight3D and not node.has_meta(LightMarkerBinder.LEASE_META)
	expect(clean, "leaving takes the mine's gates and leases away again")
	# With a budget the mine leaves the lamps to it.
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(markers)
	lighting.apply(manifest, "lantern_upper_galleries", owner, null, null, markers, focus)
	var gateless := true
	for row: Dictionary in (lighting.get("_markers") as Dictionary).values():
		gateless = gateless and not row.has("gate")
	expect(gateless, "under a budget the mine makes no gates of its own")
	var energies := {}
	for lamp: OmniLight3D in lighting.lamps:
		energies[lamp] = lamp.light_energy
	_tick(budget, focus, 0.1)
	for step: int in 12:
		_tick(budget, focus + Vector3(step * 2.0, 0, 0), 0.1)
	var held := true
	for lamp: OmniLight3D in lighting.lamps:
		held = held and is_equal_approx(lamp.light_energy, Lighting.LANTERN_ENERGY)
	expect(held, "the budget never writes a mine lamp's energy (LanternMine's LANTERN_ENERGY stays)")
	lighting.clear()
	budget.bind(null)
	RendererFamily.override_for_tests("")
	markers.free()
	owner.free()

## LanternMine keeps each lamp's own energy to put back on leaving. Lighting
## the mine while the budget fades some of its lamps (a mine cinematic ending
## with the player in the mine) must keep their resting energy, not the fade's.
func _mine_entered_mid_fade() -> void:
	var manifest := WorldManifest.new()
	manifest.data = JSON.parse_string(FileAccess.get_file_as_string(
		"res://../eloria-assets/maps/continent-v2/landfall_insides/client/world.json"))
	var owner := WorldEnvironment.new()
	root.add_child(owner)
	owner.environment = Environment.new()
	var markers := Node3D.new()
	root.add_child(markers)
	LightMarkerBinder.apply(manifest, markers)
	var lamps: Array = []
	var bound_energy := {}
	for node: Node in markers.get_children():
		var light := node as OmniLight3D
		bound_energy[light] = light.light_energy
		if str(light.name).begins_with("lantern_upper_galleries-lamp-"):
			lamps.append(light)
	RendererFamily.override_for_tests("forward_plus")
	var budget := Budget.new()
	budget.quality_override = LOW
	budget.bind(markers)
	var start: Vector3 = (lamps[0] as OmniLight3D).position
	var away := start + Vector3(60, 0, 0)
	_tick(budget, start, 0.1)
	_tick(budget, start, 0.5)
	_tick(budget, away, 0.25)
	_tick(budget, away, 0.1)
	var fading := 0
	for lamp: OmniLight3D in lamps:
		if lamp.light_energy > 0.01 and lamp.light_energy < float(bound_energy[lamp]) - 0.01:
			fading += 1
	expect(fading > 0, "walking away leaves %d gallery lamps fading out" % fading)
	var lighting := Lighting.new()
	lighting.apply(manifest, "lantern_upper_galleries", owner, null, null, markers, away)
	lighting.before_regrade(WorldManifest.new(), "")
	var kept := true
	for lamp: OmniLight3D in lamps:
		kept = kept and is_equal_approx(lamp.light_energy, float(bound_energy[lamp]))
	expect(kept, "leaving the mine puts back each lamp's own energy, not the one it had mid-fade")
	lighting.clear()
	budget.bind(null)
	var clean := true
	for node: Node in markers.find_children("*", "OmniLight3D", true, false):
		clean = clean and not node.has_meta(LightMarkerBinder.RESTING_ENERGY_META)
	expect(clean, "letting go leaves no fade mark on any light")
	RendererFamily.override_for_tests("")
	markers.free()
	owner.free()

## Once main.gd carries the B5 hook, its marker rig is budgeted on every load.
func _main_hook() -> void:
	var source := FileAccess.get_file_as_string("res://src/app/main.gd")
	if not source.contains("light_marker_budget"):
		print("SKIP: main.gd has no light_marker_budget hook yet (B5 applies it)")
		return
	root.size = Vector2i(1280, 720)
	var scene: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	await process_frame
	var markers: Array = []
	for index: int in 30:
		markers.append({"id": "hook-%d" % index, "position": [index * 1.0, 1.0, 0.0]})
	var manifest := WorldManifest.new()
	manifest.data = {"schemaVersion": "1.0",
		"asset": {"id": "light_budget_probe", "name": "Light Budget Probe", "glb": "world.glb",
			"units": "meters", "coordinateSystem": {"upAxis": "Y"}, "bounds": {}},
		"lighting": {"markers": markers}}
	scene.call("_on_world_loaded", manifest)
	await process_frame
	var rig := scene.get("map_light_root") as Node3D
	var budget: RefCounted = scene.get("light_marker_budget")
	expect(rig != null and budget != null and LightMarkerBinder.budgeted(rig) and bool(budget.call("is_bound")),
		"main binds the budget to the marker rig it just bound")
	scene.queue_free()
	await process_frame

# --- Landfall Town and Landfall Insides --------------------------------------

## Forward+ HIGH in Landfall Town is promised byte-identical: no room shows
## more than its 24, so walking the 20 points adds no gate, changes no
## visibility and writes no energy.
func _town_high_untouched() -> void:
	var manifest := WorldManifest.new()
	manifest.data = JSON.parse_string(FileAccess.get_file_as_string(
		"res://../eloria-assets/maps/continent-v2/landfall_town/client/world.json"))
	var world := Node3D.new()
	root.add_child(world)
	var lights_root := Node3D.new()
	world.add_child(lights_root)
	LightMarkerBinder.apply(manifest, lights_root)
	var lights: Array = lights_root.get_children()
	var energy := {}
	for value: Variant in lights:
		energy[value] = (value as OmniLight3D).light_energy
	var sections := SecretSections.new()
	sections.configure(manifest, world)
	RendererFamily.override_for_tests("forward_plus")
	var budget := Budget.new()
	budget.quality_override = HIGH
	budget.bind(lights_root)
	var points := _sample_points(manifest, lights)
	var previous := points[0]
	var drawn_ok := true
	for point: Vector3 in points:
		sections.update(point)
		await process_frame
		for step: int in 16:
			_tick(budget, previous.lerp(point, minf(1.0, (step + 1) / 8.0)), 0.05)
		previous = point
		for value: Variant in lights:
			var light := value as OmniLight3D
			drawn_ok = drawn_ok and light.is_visible_in_tree() == light.visible
	var untouched := lights_root.get_child_count() == lights.size()
	for value: Variant in lights:
		var light := value as OmniLight3D
		untouched = untouched and light.get_parent() == lights_root \
			and is_equal_approx(light.light_energy, float(energy[light]))
	expect(untouched and drawn_ok and lights.size() == 112,
		"Landfall Town at Forward+ HIGH: %d lights walked over 20 points, no gate added, no energy written"
			% lights.size())
	budget.bind(null)
	RendererFamily.override_for_tests("")
	sections.reset()
	world.free()
	await process_frame

## The focus points: for the ten sections with the most marker lights, the
## lights' centre and the light furthest from it, a little below the lamps.
func _sample_points(manifest: WorldManifest, lights: Array) -> Array[Vector3]:
	var by_section := {}
	for value: Variant in lights:
		var light := value as OmniLight3D
		var section := Lighting.section_at(manifest, light.position)
		if section.is_empty():
			continue
		if not by_section.has(section):
			by_section[section] = []
		(by_section[section] as Array).append(light.position)
	var ids: Array = by_section.keys()
	ids.sort_custom(func(a: String, b: String) -> bool:
		var sa: int = (by_section[a] as Array).size()
		var sb: int = (by_section[b] as Array).size()
		return sa > sb or (sa == sb and a < b))
	var points: Array[Vector3] = []
	for id: String in ids.slice(0, 10):
		var spots: Array = by_section[id]
		var centre := Vector3.ZERO
		for spot: Vector3 in spots:
			centre += spot
		centre /= spots.size()
		var far: Vector3 = spots[0]
		for spot: Vector3 in spots:
			if Vector2(spot.x - centre.x, spot.z - centre.z).length() > Vector2(far.x - centre.x, far.z - centre.z).length():
				far = spot
		points.append(Vector3(centre.x, centre.y - 1.5, centre.z))
		points.append(Vector3(far.x, far.y - 1.5, far.z))
	return points

func _walk_map(map: String) -> void:
	var manifest := WorldManifest.new()
	manifest.data = JSON.parse_string(FileAccess.get_file_as_string(
		"res://../eloria-assets/maps/continent-v2/%s/client/world.json" % map))
	var world := Node3D.new()
	world.name = "World"
	root.add_child(world)
	var lights_root := Node3D.new()
	lights_root.name = "MapLights"
	world.add_child(lights_root)
	var bound := LightMarkerBinder.apply(manifest, lights_root)
	var lights: Array = lights_root.get_children()
	var energy := {}
	for value: Variant in lights:
		energy[value] = (value as OmniLight3D).light_energy
	var sections := SecretSections.new()
	sections.configure(manifest, world)
	var points := _sample_points(manifest, lights)
	expect(points.size() == 20, "%s: %d marker lights, 20 focus points over its ten fullest sections" % [map, bound])
	var owner := WorldEnvironment.new()
	root.add_child(owner)
	owner.environment = Environment.new()
	var lighting := Lighting.new()
	for method: String in METHODS:
		RendererFamily.override_for_tests(method)
		for quality: int in [LOW, MEDIUM, HIGH]:
			var budget := Budget.new()
			budget.quality_override = quality
			var wanted := Budget.light_limit(quality, method)
			var cap := RendererFamily.per_mesh_light_limit(method)
			budget.bind(lights_root)
			var most := 0
			var settled_ok := true
			var nearest_ok := true
			var energy_ok := true
			var mine_ok := true
			var covered := 0
			var covering := 0
			var worst_cover := 1.0
			var worst_usec := 0
			var previous := points[0]
			for point: Vector3 in points:
				sections.update(point)
				await process_frame
				for step: int in 32:
					var focus := previous.lerp(point, minf(1.0, (step + 1) / 8.0))
					_tick(budget, focus, 0.05)
					if map == "landfall_insides":
						lighting.apply(manifest, sections.current_section(), owner, null, null, lights_root, focus)
					var drawn := _drawn(lights).size()
					most = maxi(most, drawn)
				previous = point
				worst_usec = maxi(worst_usec, budget.last_choice_usec)
				# Settled: exactly the budget, the nearest always among it.
				var counted: Array = []
				for value: Variant in lights:
					var light := value as OmniLight3D
					if light.visible and light.light_cull_mask != 0 and light.light_energy > 0.0:
						counted.append([light.position.distance_squared_to(point), light])
				counted.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
				var lit := budget.lit_lights()
				if lit.size() != mini(wanted, counted.size()):
					settled_ok = false
					print("  %s %s q%d at %s: %d lit of %d counted, wanted %d" % [map, method, quality, point,
						lit.size(), counted.size(), wanted])
				# The nearest wanted - EDGE_SLOTS always burn (a tie at the
				# boundary, within the budget's 1/1024 m^2 key, may go either way).
				var core := maxi(wanted - Budget.EDGE_SLOTS, 0)
				var bound_at := INF if counted.size() <= core else float(counted[core][0]) - 0.01
				for entry: Array in counted:
					if float(entry[0]) < bound_at and not (entry[1] as OmniLight3D).is_visible_in_tree():
						nearest_ok = false
				var lit_here := 0
				var reaching := 0
				for entry: Array in counted:
					var light := entry[1] as OmniLight3D
					if sqrt(float(entry[0])) <= light.omni_range:
						reaching += 1
						if light.is_visible_in_tree():
							lit_here += 1
					if light.has_meta(LightMarkerBinder.LEASE_META):
						mine_ok = mine_ok and (is_equal_approx(light.light_energy, Lighting.LANTERN_ENERGY)
							or str(light.name).ends_with("-daylight"))
				covered += lit_here
				covering += reaching
				if reaching > 0:
					worst_cover = minf(worst_cover, float(lit_here) / reaching)
				for value: Variant in lights:
					var light := value as OmniLight3D
					if not light.has_meta(LightMarkerBinder.LEASE_META) \
							and not is_equal_approx(light.light_energy, float(energy[light])):
						energy_ok = false
			var label := "%s %s %s" % [map, method, ["LOW", "MEDIUM", "HIGH"][quality]]
			if cap > 0:
				expect(most <= cap, "%s: never more than %d marker lights drawn over 20 points, mid-fade too: %d"
					% [label, cap, most])
			else:
				expect(most <= wanted + Budget.EDGE_SLOTS,
					"%s: at most N + %d = %d drawn while fading across: %d" % [label, Budget.EDGE_SLOTS,
						wanted + Budget.EDGE_SLOTS, most])
			expect(settled_ok and nearest_ok, "%s: settled at each point on min(N=%d, shown) with the nearest %d lit"
				% [label, wanted, maxi(wanted - Budget.EDGE_SLOTS, 0)])
			expect(energy_ok, "%s: every light not leased ends at its bound energy" % label)
			if map == "landfall_insides":
				expect(mine_ok, "%s: mine lamps keep LanternMine's energy" % label)
			print("  %s: lights reaching the focus lit %d/%d (worst point %.0f%%), slowest choice %d us"
				% [label, covered, covering, worst_cover * 100.0, worst_usec])
			lighting.before_regrade(WorldManifest.new(), "")
			budget.bind(null)
	RendererFamily.override_for_tests("")
	lighting.clear()
	sections.reset()
	world.free()
	owner.free()
	await process_frame

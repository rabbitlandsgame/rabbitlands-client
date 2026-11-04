extends SceneTree
## Parity of the 2D overhead banner model (src/ui/overhead/overhead_banner.gd,
## wave 2 OV-2) with today's 3D banner, headless.
##
## The test drives a real ReplicatedActor3D and an OverheadBanner through the
## same states - each actor setter followed by the banner setter OV-3 will
## forward it to (the `_op_*` functions below are that forwarding table) - and
## compares every part: visibility, text, colour and outline colour (alpha
## included), offset and size in design pixels, font and outline sizes, wrap
## width and anchor height. The actor's nodes are only read. Node values are
## converted as the design says: Label3D `offset * pixel_size / OVERHEAD_PIXEL`
## (= offset / RASTER_SCALE for overhead text) and QuadMesh `center_offset /
## OVERHEAD_PIXEL`, y flipped.
##
## States (four actors: a player with a guild tag, an NPC, a creature and a
## PK player with server colours):
## - layout: banner parts (32 combinations) x title/occupation (4) x status
##   counts 0, 1, 6, 7, 13 x health digits 1-5;
## - visibility: fade 1/0.5/0 x crowded x crowd-hidden x alive/0 health x boss
##   0/1/2 x quest x speech x name setting x health setting x drawn;
## - walk: 1500 seeded random single-setter steps per actor, scale, combat
##   pointer, marker style and TextColors overrides included, re-swept while
##   out of range as main.gd does;
## - refresh: guild refreshes through apply_server_state.
## For every state the model's items are also checked against its parts: each
## drawn part has exactly one operation, at its offset and size, in its pass,
## with its colour once the item's fade applies.
##
## Golden numbers. Each state's visible parts are folded into SHA-256 digests
## per 512 states and every 128th state is kept in full in
## tests/fixtures/overhead_banner_layout_golden.json. `--write-golden` (user
## argument, after `--`) writes it, only while the node path exists and every
## state matched it, from the model's values. Afterwards (and after OV-3 has
## removed the nodes) the model is compared with the golden, so the port stays
## pinned to today's banner. Feature-detected: with the node path the actor's
## nodes are compared; with an `overhead()` accessor (OV-3) the actor's own
## banner is.
##
## One known difference is accounted rather than failed: a speech line cleared
## (or expired) while the actor was out of draw range comes back with the rest
## of the actor today (set_drawn(true) re-shows every node it hid); the model
## keeps it cleared. Printed as `known speech divergences`.
##
## Also: the model's constants and static helpers equal the actor's, the 2D
## shaping widths against the 3D layout measure (informative), and the banner
## on an OverheadLayer (lazy item registration, fade/crowding without
## re-records, pulse, tree visibility, unregister).

const Banner := preload("res://src/ui/overhead/overhead_banner.gd")
const Style := preload("res://src/ui/overhead/overhead_style.gd")
const Item := preload("res://src/ui/overhead/overhead_item.gd")
const LayerScript := preload("res://src/ui/overhead/overhead_layer.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const StatusIcons := preload("res://src/ui/status_effect_icons.gd")
const TargetMarkerStyle := preload("res://src/actors/target_marker_style.gd")
const WORLD_LABEL_STYLE := preload("res://src/ui/world_label_style.gd")
const COMBAT_TARGET_MARKER := preload("res://src/actors/combat_target_marker_3d.gd")

const GOLDEN_PATH := "res://tests/fixtures/overhead_banner_layout_golden.json"
const GOLDEN_FORMAT := 1
const SAMPLE_EVERY := 128
const DIGEST_BLOCK := 512
const WALK_STEPS := 1500
const POSITION_EPSILON := 0.001
const COLOUR_EPSILON := 0.0001
const SAMPLE_EPSILON := 0.002
const MISMATCH_DETAIL_LIMIT := 25
## The accessor OV-3 gives ReplicatedActor3D (design 4.4); feature-detected,
## so it is named here rather than called by a literal nothing defines yet.
const OVERHEAD_ACCESSOR := &"overhead"

const ACTORS := [
	{"label": "player", "dto": {"actor_id": 9101, "kind": 1, "name": "Wren Ashdown",
		"guild_tag": "RL", "guild_colour": 3, "boss_rank": 0}},
	{"label": "npc", "dto": {"actor_id": 9102, "kind": 2, "name": "Ammet Sorrel", "boss_rank": 0}},
	{"label": "creature", "dto": {"actor_id": 9103, "kind": 5, "name": "Mire Goblin", "boss_rank": 1}},
	{"label": "pk", "dto": {"actor_id": 9104, "kind": 4, "name": "Kestrel Vane", "name_colour": 5,
		"guild_tag": "WOLF", "guild_colour": 7, "boss_rank": 0}},
]
const TEXTS := [["", ""], ["Orchard scout", ""], ["", "Grove-Keeper"],
	["Warden of the Fells", "Innkeeper"]]
const STATUS_SETS := [[], ["poison"],
	["poison", "cripple", "expose_heat", "expose_cold", "expose_magic", "expose_radiation"],
	["poison", "cripple", "expose_heat", "expose_cold", "expose_magic", "expose_radiation", "shield"],
	["poison", "cripple", "expose_heat", "expose_cold", "expose_magic", "expose_radiation",
		"stun", "root", "sunder", "mark", "challenge", "focus_lock", "haste"]]
const DIGITS := [[4, 7], [26, 42], [189, 315], [2458, 4096], [18849, 31415]]
const SPEECH_SHORT := "Well met."
const SPEECH_LONG := "Mind the ford, traveller: the river rose overnight and the stones by the mill are under a hand of water."
const ROLES: Array[String] = ["world_player", "world_npc", "world_creature", "world_pk",
	"world_guild", "world_title", "world_occupation", "world_health", "world_speech", "world_quest"]

class Pair extends RefCounted:
	var label := ""
	var phase := ""
	var actor: ReplicatedActor3D
	## The OverheadBanner the test drives (untyped: called dynamically).
	var model
	var drawn := true
	var target := false
	var style: Dictionary = {}
	var speech_stale := false
	var index := 0
	var hashing: HashingContext
	var in_block := 0
	var digests: Array[String] = []

var failures := 0
var write_golden := false
var node_mode := false
var accessor_mode := false
var states_compared := 0
var parts_compared := 0
var ops_checked := 0
var mismatches := 0
var known_speech_divergences := 0
var _detail_reported := 0
var _stage: Node3D
var _adapter: CoordinateAdapter
var _golden: Dictionary = {}
var _golden_samples: Dictionary = {}
var _digests: Dictionary = {}
var _samples: Array = []
var _build_usec := 0
var _builds := 0
var _phase_counts: Dictionary = {}

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	write_golden = "--write-golden" in OS.get_cmdline_user_args()
	TextColors.reset()
	_adapter = CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	_stage = Node3D.new()
	_stage.name = "ParityStage"
	root.add_child(_stage)
	await process_frame
	_load_golden()
	_check_constants()
	_check_static_helpers()
	_detect_modes()
	var started := Time.get_ticks_msec()
	for spec: Dictionary in ACTORS:
		_run_layout(spec)
		await _settle()
	for spec: Dictionary in ACTORS:
		_run_visibility(spec)
		await _settle()
	for index: int in range(ACTORS.size()):
		_run_walk(ACTORS[index], index)
		await _settle()
	_run_refresh(ACTORS[0])
	await _settle()
	print("parity: %d states, %d parts compared, %d op checks, %d mismatches, %d known speech divergences, %.1f s" % [
		states_compared, parts_compared, ops_checked, mismatches, known_speech_divergences,
		(Time.get_ticks_msec() - started) / 1000.0])
	print("parity phases: ", _phase_counts)
	if node_mode or accessor_mode:
		expect(mismatches == 0, "every part of every state matches the %s (%d states, %d parts)" % [
			"3D node path" if node_mode else "actor's own banner", states_compared, parts_compared])
	expect(ops_checked == states_compared, "every state's items were checked against its parts")
	if _builds > 0:
		print("COST block build (layout + ops, headless): %.1f us mean over %d builds" % [
			float(_build_usec) / _builds, _builds])
	_check_speech_divergence()
	_check_shaping_widths()
	await _check_layer()
	_finish_golden()
	TextColors.reset()
	_stage.queue_free()
	await process_frame
	print("overhead banner parity: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _settle() -> void:
	for child: Node in _stage.get_children():
		child.queue_free()
	await process_frame

# --- Modes and golden -------------------------------------------------------------

func _detect_modes() -> void:
	var probe := _make_pair(ACTORS[0], "probe")
	node_mode = probe.actor.get_node_or_null("Nameplate") is Label3D
	accessor_mode = not node_mode and probe.actor.has_method(OVERHEAD_ACCESSOR)
	print("modes: node path %s, overhead() accessor %s, golden %s" % [node_mode, accessor_mode,
		"write" if write_golden else ("compare" if not _golden.is_empty() else "absent")])
	expect(node_mode or accessor_mode or not _golden.is_empty(),
		"something to compare the model with (node path, accessor or golden)")
	probe.actor.queue_free()

func _load_golden() -> void:
	if write_golden or not FileAccess.file_exists(GOLDEN_PATH):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(GOLDEN_PATH))
	if not parsed is Dictionary:
		expect(false, "the golden file parses")
		return
	_golden = parsed
	for sample: Dictionary in _golden.get("samples", []):
		_golden_samples[str(sample.key)] = sample

func _finish_golden() -> void:
	if write_golden:
		if not node_mode:
			expect(false, "--write-golden needs the node path (stage-B tree)")
			return
		if mismatches > 0 or failures > 0:
			expect(false, "golden not written: the model does not match the node path")
			return
		var lines := PackedStringArray()
		lines.append("{")
		lines.append("\"format\": %d," % GOLDEN_FORMAT)
		lines.append("\"written_by\": %s," % JSON.stringify(
			"tests/test_overhead_banner_parity.gd --write-golden: model values after every state matched the 3D node path"))
		lines.append("\"engine\": %s," % JSON.stringify(Engine.get_version_info().string))
		lines.append("\"font\": %s," % JSON.stringify(_font_identity()))
		lines.append("\"units\": %s," % JSON.stringify(
			"design pixels, y down, from the anchor; part = [text, colour, outline colour, offset x, offset y, width, height, font size, outline size, wrap width, anchor y]"))
		lines.append("\"sample_every\": %d, \"digest_block\": %d," % [SAMPLE_EVERY, DIGEST_BLOCK])
		lines.append("\"phases\": %s," % JSON.stringify(_phase_counts))
		lines.append("\"digests\": %s," % JSON.stringify(_digests))
		lines.append("\"samples\": [")
		for index: int in range(_samples.size()):
			lines.append(JSON.stringify(_samples[index]) + ("," if index < _samples.size() - 1 else ""))
		lines.append("]")
		lines.append("}")
		var file := FileAccess.open(GOLDEN_PATH, FileAccess.WRITE)
		expect(file != null, "golden file opens for writing")
		if file != null:
			file.store_string("\n".join(lines) + "\n")
			file.close()
			print("golden written: %s (%d samples, %d digest groups)" % [GOLDEN_PATH, _samples.size(), _digests.size()])
		return
	if _golden.is_empty():
		print("golden: absent (run with -- --write-golden in the stage-B tree)")
		return
	expect(int(_golden.get("format", 0)) == GOLDEN_FORMAT, "golden format %d" % GOLDEN_FORMAT)
	var golden_digests: Dictionary = _golden.get("digests", {})
	var differing: Array[String] = []
	for key: String in golden_digests:
		if JSON.stringify(golden_digests[key]) != JSON.stringify(_digests.get(key, [])):
			differing.append(key)
	for key: String in _digests:
		if not golden_digests.has(key):
			differing.append(key)
	if not differing.is_empty() and str(_golden.get("font", "")) != _font_identity():
		print("golden font differs: %s vs %s" % [_golden.get("font", ""), _font_identity()])
	expect(differing.is_empty(), "every state digest equals the golden (%d groups; differing: %s)" % [
		golden_digests.size(), differing])
	var compared := 0
	for key: String in _golden_samples:
		compared += 1
	expect(compared == _golden_samples.size() and _golden_samples.size() == int(_golden.get("samples", []).size()),
		"golden samples indexed")

func _font_identity() -> String:
	var font := Style.font()
	return "%s %s (%s)" % [font.get_font_name(), font.get_font_style_name(), font.resource_path]

# --- Pairs and the forwarding table -----------------------------------------------

func _make_pair(spec: Dictionary, phase: String) -> Pair:
	var pair := Pair.new()
	pair.label = str(spec.label)
	pair.phase = phase
	var dto: Dictionary = (spec.dto as Dictionary).duplicate()
	for field: String in ["x", "y", "rotation"]:
		dto[field] = 0
	dto["scale"] = 1.0
	dto["health"] = 20
	dto["max_health"] = 20
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	actor.configure(dto, _adapter, {}, {}, {}, false)
	actor.set_physics_process(false)
	actor.set_process(false)
	pair.actor = actor
	# configure()'s overhead calls, in its order (_add_nameplate).
	var model := Banner.new()
	model.attach(actor)
	model.set_creature(int(dto.kind) == Banner.CREATURE_ACTOR_KIND)
	model.set_boss_rank(int(dto.get("boss_rank", 0)),
		actor.banner_head_height() + ReplicatedActor3D.NAMEPLATE_CLEARANCE)
	model.set_name_info(Banner.name_info(dto))
	model.set_vitals(int(dto.health), int(dto.max_health))
	model.set_status_effects(dto.get("status_effects", dto.get("negative_statuses", [])))
	pair.model = model
	pair.hashing = HashingContext.new()
	pair.hashing.start(HashingContext.HASH_SHA256)
	return pair

func _op_parts(pair: Pair, options: Dictionary) -> void:
	pair.actor.set_banner_parts(options)
	pair.model.set_banner_parts(options)

func _op_title(pair: Pair, title: String) -> void:
	pair.actor.set_title(title)
	pair.model.set_title(title)

func _op_occupation(pair: Pair, occupation: String) -> void:
	pair.actor.set_occupation(occupation)
	pair.model.set_occupation(occupation)

func _op_vitals(pair: Pair, current: int, maximum: int) -> void:
	pair.actor.apply_vitals(current, maximum)
	pair.model.set_vitals(current, maximum)

func _op_health_visible(pair: Pair, enabled: bool) -> void:
	pair.actor.set_health_visible(enabled)
	pair.model.set_health_visible(enabled)

func _op_nameplate_visible(pair: Pair, enabled: bool) -> void:
	pair.actor.set_nameplate_visible(enabled)
	pair.model.set_nameplate_visible(enabled)

func _op_fade(pair: Pair, fade: float) -> void:
	pair.actor.set_overhead_fade(fade)
	pair.model.set_fade(fade)

func _op_crowded(pair: Pair, crowded: bool) -> void:
	pair.actor.set_overhead_crowded(crowded)
	pair.model.set_crowded(crowded)

func _op_crowd_hidden(pair: Pair, hidden: bool) -> void:
	pair.actor.set_crowd_hidden(hidden)
	pair.model.set_crowd_hidden(hidden)

## set_drawn; on the way back the actor also restates its combat marker.
func _op_drawn(pair: Pair, enabled: bool) -> void:
	pair.actor.set_drawn(enabled)
	pair.model.set_drawn(enabled)
	pair.drawn = enabled
	if enabled:
		pair.model.set_pointer(pair.target, pair.actor.head_height(), pair.style)

## main.gd sweeps out-of-range actors again on every pass (set_drawn(false)).
func _sweep(pair: Pair) -> void:
	if not pair.drawn:
		pair.actor.set_drawn(false)

func _op_status(pair: Pair, effects: Array) -> void:
	pair.actor.set_status_effects(effects)
	pair.model.set_status_effects(effects)

func _op_quest(pair: Pair, available: bool) -> void:
	pair.actor.set_quest_available(available)
	pair.model.set_quest_available(available)

func _op_speech(pair: Pair, text: String, colour: Color) -> void:
	pair.actor.show_speech_bubble(text, 600000, colour)
	pair.model.show_speech(text, colour)
	pair.speech_stale = false

func _op_clear_speech(pair: Pair) -> void:
	pair.actor.clear_speech_bubble()
	pair.model.clear_speech()
	# Cleared out of range: the node path shows it again on the way back.
	pair.speech_stale = not pair.drawn

func _op_boss(pair: Pair, rank: int) -> void:
	var height: float = pair.actor.banner_head_height() + ReplicatedActor3D.NAMEPLATE_CLEARANCE
	pair.actor.set_boss_rank(rank)
	pair.model.set_boss_rank(rank, height)

## set_server_scale lifts the overhead block (with no native body to NAMEPLATE_HEIGHT
## times the scale) and restates the combat marker's head height.
func _op_scale(pair: Pair, value: float) -> void:
	var next := maxf(0.01, value)
	var changed := not is_equal_approx(next, pair.actor.server_scale)
	pair.actor.set_server_scale(value)
	if changed:
		pair.model.lift(ReplicatedActor3D.NAMEPLATE_HEIGHT * pair.actor.server_scale)
		pair.model.set_pointer(pair.target and pair.drawn, pair.actor.head_height(), pair.style)

func _op_target(pair: Pair, enabled: bool) -> void:
	pair.actor.set_combat_target(enabled)
	pair.target = enabled
	pair.model.set_pointer(enabled and pair.drawn, pair.actor.head_height(), pair.style)

func _op_marker_style(pair: Pair, appearance: Dictionary) -> void:
	pair.actor.set_target_marker_style(appearance)
	pair.style = appearance
	pair.model.set_pointer(pair.target and pair.drawn, pair.actor.head_height(), appearance)

## TextColors notifies every actor; the banner hears it from its actor.
func _op_text_colour(pair: Pair, role: String, colour: Variant) -> void:
	if colour == null:
		TextColors.reset(role)
	else:
		TextColors.set_color(role, colour as Color)
	pair.model.refresh_colours(role)

static func _parts_options(bits: int) -> Dictionary:
	return {"names": (bits & 1) != 0, "health_bar": (bits & 2) != 0,
		"health_numbers": (bits & 4) != 0, "status_icons": (bits & 8) != 0,
		"background": (bits & 16) != 0}

# --- Phases -------------------------------------------------------------------------

func _run_layout(spec: Dictionary) -> void:
	var pair := _make_pair(spec, "layout")
	_op_health_visible(pair, true)
	for digits: Array in DIGITS:
		for effects: Array in STATUS_SETS:
			for texts: Array in TEXTS:
				for bits: int in range(32):
					_op_vitals(pair, int(digits[0]), int(digits[1]))
					_op_status(pair, effects)
					_op_title(pair, str(texts[0]))
					_op_occupation(pair, str(texts[1]))
					_op_parts(pair, _parts_options(bits))
					_compare_state(pair, "parts=%d title=%s occupation=%s status=%d hp=%d/%d" % [
						bits, texts[0], texts[1], effects.size(), digits[0], digits[1]], true)
	_close_pair(pair)

func _run_visibility(spec: Dictionary) -> void:
	var pair := _make_pair(spec, "visibility")
	_op_title(pair, "Orchard scout")
	_op_status(pair, ["poison", "cripple", "shield"])
	if str(spec.label) == "npc":
		_op_occupation(pair, "Ferry-Warden")
	var speaking := false
	for fade: float in [1.0, 0.5, 0.0]:
		for crowded: bool in [false, true]:
			for hidden: bool in [false, true]:
				for health: int in [13, 0]:
					for boss: int in [0, 1, 2]:
						for quest: bool in [false, true]:
							for speech: bool in [false, true]:
								for name_setting: bool in [true, false]:
									for health_setting: bool in [true, false]:
										for drawn: bool in [true, false]:
											if drawn:
												_op_drawn(pair, true)
											_op_fade(pair, fade)
											_op_crowded(pair, crowded)
											_op_crowd_hidden(pair, hidden)
											_op_vitals(pair, health, 20)
											_op_boss(pair, boss)
											_op_quest(pair, quest)
											_op_nameplate_visible(pair, name_setting)
											_op_health_visible(pair, health_setting)
											if speech and not speaking:
												_op_speech(pair, SPEECH_LONG, Color(0.96, 0.91, 0.78))
											elif not speech and speaking:
												_op_clear_speech(pair)
											speaking = speech
											if not drawn:
												_op_drawn(pair, false)
											_sweep(pair)
											_compare_state(pair, "fade=%.1f crowded=%s hidden=%s hp=%d boss=%d quest=%s speech=%s names=%s health=%s drawn=%s" % [
												fade, crowded, hidden, health, boss, quest, speech, name_setting,
												health_setting, drawn])
	_close_pair(pair)

func _run_walk(spec: Dictionary, seed_index: int) -> void:
	var pair := _make_pair(spec, "walk")
	var random := RandomNumberGenerator.new()
	random.seed = 0x0E2B + seed_index * 7919
	var titles := ["", "Orchard scout", "Warden of the Fells", "Ironclad Vanguard of Eloria"]
	var occupations := ["", "Grove-Keeper", "  Ferry-Warden ", "Innkeeper"]
	var vitals := [[20, 20], [13, 20], [0, 20], [25, 20], [5, 0], [1, 1], [318, 9999], [-1, -1]]
	var fades := [1.0, 0.75, 0.5, 0.0, 1.3, -0.2]
	var scales := [1.0, 1.6, 0.5, 2.0]
	var effects_pool: Array = StatusIcons.TEXTURES.keys()
	effects_pool.append_array(["unknown", "poison"])
	var styles := [{}, {"triangle_size": 50.0}, {"triangle_size": 300.0, "triangle_thickness": 25.0,
		"triangle_color": Color(0.2, 0.9, 0.4)}, {"triangle_size": 140.0, "triangle_thickness": 260.0}]
	var speeches := [SPEECH_SHORT, SPEECH_LONG, "", "Ho there!\nOver here."]
	var speaking := false
	for step: int in range(WALK_STEPS):
		var choice := random.randi_range(0, 19)
		var described := ""
		match choice:
			0:
				var bits := random.randi_range(0, 31)
				_op_parts(pair, _parts_options(bits))
				described = "parts %d" % bits
			1:
				var title: String = titles[random.randi_range(0, titles.size() - 1)]
				_op_title(pair, title)
				described = "title %s" % title
			2:
				var occupation: String = occupations[random.randi_range(0, occupations.size() - 1)]
				_op_occupation(pair, occupation)
				described = "occupation %s" % occupation
			3, 4:
				var pair_values: Array = vitals[random.randi_range(0, vitals.size() - 1)]
				_op_vitals(pair, int(pair_values[0]), int(pair_values[1]))
				described = "vitals %d/%d" % [pair_values[0], pair_values[1]]
			5:
				var on := random.randi_range(0, 1) == 1
				_op_health_visible(pair, on)
				described = "health visible %s" % on
			6:
				var on := random.randi_range(0, 3) > 0
				_op_nameplate_visible(pair, on)
				described = "names visible %s" % on
			7:
				var fade: float = fades[random.randi_range(0, fades.size() - 1)]
				_op_fade(pair, fade)
				described = "fade %.2f" % fade
			8:
				var on := random.randi_range(0, 2) == 0
				_op_crowded(pair, on)
				described = "crowded %s" % on
			9:
				var on := random.randi_range(0, 3) == 0
				_op_crowd_hidden(pair, on)
				described = "crowd hidden %s" % on
			10:
				var on := random.randi_range(0, 2) > 0
				_op_drawn(pair, on)
				described = "drawn %s" % on
			11:
				var effects: Array = []
				for count: int in range(random.randi_range(0, 9)):
					effects.append(effects_pool[random.randi_range(0, effects_pool.size() - 1)])
				_op_status(pair, effects)
				described = "status %s" % [effects]
			12:
				var on := random.randi_range(0, 1) == 1
				_op_quest(pair, on)
				described = "quest %s" % on
			13:
				if speaking and random.randi_range(0, 1) == 0:
					_op_clear_speech(pair)
					speaking = false
					described = "clear speech"
				else:
					var text: String = speeches[random.randi_range(0, speeches.size() - 1)]
					var colour := Color(random.randf(), random.randf(), random.randf())
					_op_speech(pair, text, colour)
					speaking = true
					described = "speech %s" % text.left(12)
			14:
				var rank := random.randi_range(-1, 3)
				_op_boss(pair, rank)
				described = "boss %d" % rank
			15:
				var value: float = scales[random.randi_range(0, scales.size() - 1)]
				_op_scale(pair, value)
				described = "scale %.1f" % value
			16:
				var on := random.randi_range(0, 1) == 1
				_op_target(pair, on)
				described = "target %s" % on
			17:
				var appearance: Dictionary = styles[random.randi_range(0, styles.size() - 1)]
				_op_marker_style(pair, appearance)
				described = "marker style %s" % [appearance]
			18:
				var role: String = ROLES[random.randi_range(0, ROLES.size() - 1)]
				if random.randi_range(0, 3) == 0:
					_op_text_colour(pair, role, null)
					described = "colour reset %s" % role
				else:
					var colour := Color(random.randf(), random.randf(), random.randf(),
						[1.0, 1.0, 0.8, 0.5][random.randi_range(0, 3)])
					_op_text_colour(pair, role, colour)
					described = "colour %s %s" % [role, colour.to_html(true)]
			19:
				# Speech expiry: the actor's own timer clears the line.
				pair.actor.clear_speech_bubble()
				pair.model.clear_speech()
				pair.speech_stale = not pair.drawn
				speaking = false
				described = "speech expired"
		_sweep(pair)
		_compare_state(pair, "step %d: %s" % [step, described])
	_op_text_colour(pair, "", null)
	_close_pair(pair)

## A guild refresh arrives as an actor packet (apply_server_state), which also
## restates the boss rank, the scale and the status effects.
func _run_refresh(spec: Dictionary) -> void:
	var pair := _make_pair(spec, "refresh")
	_op_health_visible(pair, true)
	var base: Dictionary = (spec.dto as Dictionary).duplicate()
	for field: String in ["x", "y", "rotation"]:
		base[field] = 0
	var packets := [
		{"guild_tag": "RLX", "guild_colour": 9},
		{"guild_tag": "", "guild_colour": 0},
		{"name": "Wren Ashdown-Hale", "guild_tag": "RL", "guild_colour": 3, "scale": 1.6},
		{"name_colour": 4, "boss_rank": 2, "status_effects": ["poison", "haste"]},
		{"kind": 2, "map_type": 2, "scale": 1.0, "boss_rank": 0},
	]
	for packet: Dictionary in packets:
		var dto := base.duplicate()
		dto.merge(packet, true)
		var height: float = pair.actor.banner_head_height() + ReplicatedActor3D.NAMEPLATE_CLEARANCE
		var scale_before: float = pair.actor.server_scale
		pair.actor.apply_server_state(dto, _adapter)
		# apply_server_state's overhead calls, in its order.
		pair.model.set_boss_rank(int(dto.get("boss_rank", 0)), height)
		if dto.has("scale") and not is_equal_approx(maxf(0.01, float(dto.scale)), scale_before):
			pair.model.lift(ReplicatedActor3D.NAMEPLATE_HEIGHT * pair.actor.server_scale)
		pair.model.set_name_info(Banner.name_info(dto))
		pair.model.set_status_effects(dto.get("status_effects", dto.get("negative_statuses", [])))
		base = dto
		_compare_state(pair, "packet %s" % [packet])
	_close_pair(pair)

func _close_pair(pair: Pair) -> void:
	_flush_digest(pair)
	var key := "%s/%s" % [pair.phase, pair.label]
	_digests[key] = pair.digests
	_phase_counts[key] = pair.index
	pair.actor.queue_free()

# --- Comparison ---------------------------------------------------------------------

func _compare_state(pair: Pair, inputs: String, timed := false) -> void:
	var model = pair.model
	states_compared += 1
	if timed:
		# The block's build on its own: layout (cached widths) and operations.
		var build_started := Time.get_ticks_usec()
		model.build_now()
		_build_usec += Time.get_ticks_usec() - build_started
		_builds += 1
	if node_mode or accessor_mode:
		var names: Array[StringName] = model.part_names()
		if node_mode:
			var icons := pair.actor.get_node_or_null("StatusIcons")
			if icons != null:
				for child: Node in icons.get_children():
					var icon_name := StringName("StatusIcons/%s" % child.name)
					if not icon_name in names:
						names.append(icon_name)
		for part_name: StringName in names:
			parts_compared += 1
			var actual := _actor_part(pair, part_name)
			var expected: Dictionary = model.part(part_name)
			var problem := _difference(part_name, actual, expected)
			if problem.is_empty():
				continue
			if part_name == Banner.SPEECH_BUBBLE and pair.speech_stale and bool(actual.get("visible", false)) \
					and not bool(expected.get("visible", false)):
				known_speech_divergences += 1
				continue
			mismatches += 1
			if _detail_reported < MISMATCH_DETAIL_LIMIT:
				_detail_reported += 1
				push_error("MISMATCH %s/%s #%d [%s] %s: %s" % [pair.phase, pair.label, pair.index,
					inputs, part_name, problem])
	var op_problem := _check_ops(model)
	ops_checked += 1
	if not op_problem.is_empty():
		mismatches += 1
		if _detail_reported < MISMATCH_DETAIL_LIMIT:
			_detail_reported += 1
			push_error("OPS %s/%s #%d [%s]: %s" % [pair.phase, pair.label, pair.index, inputs, op_problem])
	_record(pair, inputs)

func _actor_part(pair: Pair, part_name: StringName) -> Dictionary:
	if node_mode:
		return _node_part(pair.actor, part_name)
	var banner: Variant = pair.actor.call(OVERHEAD_ACCESSOR)
	return (banner as RefCounted).call("part", part_name) if banner != null else {}

## A part as the 3D banner draws it, in the model's units.
func _node_part(actor: Node3D, part_name: StringName) -> Dictionary:
	var path := "CombatTargetMarker/Pointer" if part_name == Banner.POINTER else str(part_name)
	var node := actor.get_node_or_null(path) as Node3D
	if node == null:
		return {"visible": false}
	var result := {"visible": node.is_visible_in_tree(), "anchor": actor.to_local(node.global_position)}
	if node is Label3D:
		var label := node as Label3D
		var factor := label.pixel_size / Style.OVERHEAD_PIXEL
		var font: Font = label.font if label.font != null else ThemeDB.fallback_font
		var wrap := label.width if label.autowrap_mode != TextServer.AUTOWRAP_OFF else 0.0
		var measured: Vector2
		if wrap > 0.0:
			measured = font.get_multiline_string_size(label.text, HORIZONTAL_ALIGNMENT_CENTER, wrap,
				label.font_size, -1, TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND
					| TextServer.BREAK_ADAPTIVE)
		else:
			measured = Vector2(font.get_string_size(label.text, HORIZONTAL_ALIGNMENT_LEFT, -1,
				label.font_size).x, font.get_height(label.font_size))
		result.merge({"kind": "text", "text": label.text, "colour": label.modulate,
			"outline_colour": label.outline_modulate, "alpha": label.modulate.a,
			"offset": Vector2(label.offset.x, -label.offset.y) * factor, "size": measured * factor,
			"font_size": label.font_size * factor, "outline_size": label.outline_size * factor,
			"wrap_width": wrap * factor})
	elif node is MeshInstance3D:
		var quad := (node as MeshInstance3D).mesh as QuadMesh
		var material := quad.material as StandardMaterial3D
		result.merge({"kind": "rect", "text": "", "colour": material.albedo_color,
			"outline_colour": material.albedo_color, "alpha": material.albedo_color.a,
			"offset": Vector2(quad.center_offset.x, -quad.center_offset.y) / Style.OVERHEAD_PIXEL,
			"size": quad.size / Style.OVERHEAD_PIXEL, "font_size": 0.0, "outline_size": 0.0,
			"wrap_width": 0.0, "texture": material.albedo_texture})
	else:
		var icons: Array[String] = []
		for child: Node in node.get_children():
			icons.append(str(child.name))
		result.merge({"kind": "group", "icons": icons})
	return result

## "" when `actual` (node or actor banner) and `expected` (model) agree.
func _difference(part_name: StringName, actual: Dictionary, expected: Dictionary) -> String:
	if expected.is_empty():
		return "the model has no part %s" % part_name
	var visible := bool(actual.get("visible", false))
	if visible != bool(expected.visible):
		return "visible %s vs model %s" % [visible, expected.visible]
	if part_name == Banner.STATUS_ICONS:
		var icons: Array = actual.get("icons", [])
		if JSON.stringify(icons) != JSON.stringify(expected.icons) and (visible or not icons.is_empty()):
			return "icons %s vs %s" % [icons, expected.icons]
		return ""
	if not visible:
		return ""
	var is_text := float(expected.font_size) > 0.0
	if is_text and str(actual.get("text", "")) != str(expected.text):
		return "text '%s' vs '%s'" % [actual.get("text", ""), expected.text]
	var offset: Vector2 = actual.get("offset", Vector2.INF)
	var model_offset: Vector2 = expected.offset
	if part_name == Banner.QUEST_MARKER:
		# The marker's Tween may have moved it along its bob (36 to 42 px up).
		if absf(offset.x - model_offset.x) > POSITION_EPSILON or offset.y > -Style.QUEST_RISE_FROM + POSITION_EPSILON \
				or offset.y < -Style.QUEST_RISE_TO - POSITION_EPSILON:
			return "offset %s outside the bob from %s" % [offset, model_offset]
	elif not offset.is_equal_approx(model_offset) and offset.distance_to(model_offset) > POSITION_EPSILON:
		return "offset %s vs %s" % [offset, model_offset]
	var size: Vector2 = actual.get("size", Vector2.INF)
	if size.distance_to(expected.size) > (0.01 if is_text else POSITION_EPSILON):
		return "size %s vs %s" % [size, expected.size]
	for field: String in ["font_size", "outline_size", "wrap_width"]:
		if absf(float(actual.get(field, -1.0)) - float(expected[field])) > POSITION_EPSILON:
			return "%s %s vs %s" % [field, actual.get(field), expected[field]]
	var anchor: Vector3 = actual.get("anchor", Vector3.INF)
	if anchor.distance_to(expected.anchor) > 0.0001:
		return "anchor %s vs %s" % [anchor, expected.anchor]
	var colour: Color = actual.get("colour", Color.TRANSPARENT)
	if part_name == Banner.QUEST_MARKER:
		var from: Color = expected.colour
		if not _on_segment(colour, from, from.lightened(Style.QUEST_LIGHTEN)):
			return "colour %s off the pulse from %s" % [colour, from]
	elif not _same_colour(colour, expected.colour):
		return "colour %s vs %s" % [colour, expected.colour]
	if float(expected.outline_size) > 0.0 and not _same_colour(actual.get("outline_colour", Color.TRANSPARENT),
			expected.outline_colour):
		return "outline colour %s vs %s" % [actual.get("outline_colour"), expected.outline_colour]
	if str(actual.get("kind", "")) == "rect":
		var texture: Texture2D = actual.get("texture")
		var model_texture: Texture2D = expected.texture
		if (texture == null) != (model_texture == null):
			return "texture %s vs %s" % [texture, model_texture]
		if part_name != Banner.HEALTH_BAR_FILL and texture != model_texture:
			return "texture %s vs %s" % [texture, model_texture]
	return ""

static func _same_colour(a: Color, b: Color) -> bool:
	return absf(a.r - b.r) <= COLOUR_EPSILON and absf(a.g - b.g) <= COLOUR_EPSILON \
		and absf(a.b - b.b) <= COLOUR_EPSILON and absf(a.a - b.a) <= COLOUR_EPSILON

static func _on_segment(value: Color, from: Color, to: Color) -> bool:
	var span := Vector4(to.r - from.r, to.g - from.g, to.b - from.b, to.a - from.a)
	var at := Vector4(value.r - from.r, value.g - from.g, value.b - from.b, value.a - from.a)
	var length := span.length_squared()
	var t := at.dot(span) / length if length > 0.0 else 0.0
	return t >= -0.001 and t <= 1.001 and (at - span * clampf(t, 0.0, 1.0)).length() <= 0.002

## The model's items against its parts: one op per drawn part, in its pass, at
## its place, in its colour once the item's fade and pass tints apply.
func _check_ops(model: RefCounted) -> String:
	model.call("build_now")
	for item_name: StringName in [Banner.ITEM_BLOCK, Banner.ITEM_BOSS, Banner.ITEM_QUEST,
			Banner.ITEM_SPEECH, Banner.ITEM_POINTER]:
		var item: Item = model.call("item", item_name)
		var ops: Array = item.ops()
		var sources: Array[StringName] = model.call("op_sources", item_name)
		if ops.size() != sources.size():
			return "%s: %d ops for %d sources" % [item_name, ops.size(), sources.size()]
		var faded := item_name == Banner.ITEM_BLOCK or item_name == Banner.ITEM_BOSS
		var item_fade: float = item.fade
		if faded and absf(item_fade - float(model.call("fade"))) > 0.000001:
			return "%s fade %s vs banner %s" % [item_name, item_fade, model.call("fade")]
		if not faded and item_fade != 1.0:
			return "%s is faded (%s)" % [item_name, item_fade]
		var pulse_offset := Vector2.ZERO
		var pulse_colour := Color.WHITE
		if item.has_pulse():
			var state: Array = item.pulse_state(int(model.call("quest_start_usec")))
			pulse_offset = state[0]
			pulse_colour = state[1]
		var covered := {}
		for index: int in range(ops.size()):
			var op: Array = ops[index]
			var source := sources[index]
			covered[source] = true
			var part: Dictionary = model.call("part", source)
			if part.is_empty():
				return "%s op %d: unknown part %s" % [item_name, index, source]
			var kind := int(op[0])
			var fill_pass := int(op[1])
			if kind == Item.OP_RECT or kind == Item.OP_TEXTURE_RECT:
				var rect: Rect2 = op[2]
				var expected_rect := Rect2((part.offset as Vector2) - (part.size as Vector2) * 0.5, part.size)
				if rect.position.distance_to(expected_rect.position) > POSITION_EPSILON \
						or rect.size.distance_to(expected_rect.size) > POSITION_EPSILON:
					return "%s %s rect %s vs %s" % [item_name, source, rect, expected_rect]
				var tint: Color = op[3] if kind == Item.OP_RECT else op[4]
				if not _same_colour(Color(tint, tint.a * item_fade), part.colour):
					return "%s %s colour %s x %s vs %s" % [item_name, source, tint, item_fade, part.colour]
				if kind == Item.OP_TEXTURE_RECT and op[3] != part.texture:
					return "%s %s texture" % [item_name, source]
				var wanted_pass := Style.PASS_BACKING
				match source:
					Banner.HEALTH_BAR_BACKGROUND:
						wanted_pass = Style.PASS_BAR_BACK
					Banner.HEALTH_BAR_FILL:
						wanted_pass = Style.PASS_BAR_FILL
					Banner.OVERHEAD_BACKGROUND:
						wanted_pass = Style.PASS_BACKING
					_:
						wanted_pass = Style.PASS_ICONS
				if fill_pass != wanted_pass:
					return "%s %s pass %d vs %d" % [item_name, source, fill_pass, wanted_pass]
			elif kind == Item.OP_TEXT:
				if str(op[4]) != str(part.text):
					return "%s %s text '%s' vs '%s'" % [item_name, source, op[4], part.text]
				var scale := item.scale
				for pair_check: Array in [[float(op[5]) * scale, part.font_size, "font"],
						[float(op[9]) * scale, part.outline_size, "outline"],
						[float(op[6]) * scale, part.wrap_width, "wrap"]]:
					if absf(float(pair_check[0]) - float(pair_check[1])) > POSITION_EPSILON:
						return "%s %s %s %s vs %s" % [item_name, source, pair_check[2], pair_check[0], pair_check[1]]
				var at: Vector2 = (op[2] as Vector2) + pulse_offset
				var half_width := Banner.text_width(str(part.text), int(op[5])) * 0.5
				match int(op[7]):
					HORIZONTAL_ALIGNMENT_RIGHT:
						at.x -= half_width
					HORIZONTAL_ALIGNMENT_LEFT:
						at.x += half_width
				if int(op[8]) != VERTICAL_ALIGNMENT_CENTER or at.distance_to(part.offset) > POSITION_EPSILON:
					return "%s %s at %s (align %d/%d) vs offset %s" % [item_name, source, op[2], op[7], op[8], part.offset]
				var fill: Color = (op[3] as Color) * (pulse_colour if item.has_pulse() else Color.WHITE)
				if not _same_colour(Color(fill, fill.a * item_fade), part.colour):
					return "%s %s colour %s vs %s" % [item_name, source, fill, part.colour]
				if int(op[9]) > 0:
					var outline: Color = op[10]
					if not _same_colour(Color(outline, outline.a * item_fade), part.outline_colour):
						return "%s %s outline %s vs %s" % [item_name, source, outline, part.outline_colour]
				var wanted_fill := Style.PASS_BACKING if item_name == Banner.ITEM_POINTER else Style.PASS_TEXT
				var wanted_outline := Style.PASS_POINTER_OUTLINE if item_name == Banner.ITEM_POINTER \
					else Style.PASS_TEXT_OUTLINE
				if fill_pass != wanted_fill or int(op[11]) != wanted_outline:
					return "%s %s passes %d/%d" % [item_name, source, fill_pass, op[11]]
		var part_names: Array[StringName] = model.call("part_names")
		for part_name: StringName in part_names:
			if part_name == Banner.STATUS_ICONS:
				continue
			var part: Dictionary = model.call("part", part_name)
			if part.item != item_name or not part.visible:
				continue
			if float(part.font_size) > 0.0 and str(part.text).is_empty():
				continue
			if not covered.has(part_name):
				return "%s: visible part %s has no op" % [item_name, part_name]
			if not item.visible:
				return "%s: part %s visible in a hidden item" % [item_name, part_name]
	return ""

# --- Records, digests and samples ---------------------------------------------------

static func _round(value: float) -> float:
	var rounded := snappedf(value, 0.001)
	return 0.0 if rounded == 0.0 else rounded

func _record(pair: Pair, inputs: String) -> void:
	var model = pair.model
	var lines := PackedStringArray()
	var parts := {}
	var part_names: Array[StringName] = model.call("part_names")
	for part_name: StringName in part_names:
		var part: Dictionary = model.call("part", part_name)
		if not part.visible:
			continue
		if part_name == Banner.STATUS_ICONS:
			var icons := PackedStringArray(part.icons)
			lines.append("%s=%s" % [part_name, ",".join(icons)])
			parts[str(part_name)] = [",".join(icons)]
			continue
		var offset: Vector2 = part.offset
		var size: Vector2 = part.size
		var values := [str(part.text), (part.colour as Color).to_html(true),
			(part.outline_colour as Color).to_html(true), _round(offset.x), _round(offset.y),
			_round(size.x), _round(size.y), _round(part.font_size), _round(part.outline_size),
			_round(part.wrap_width), _round((part.anchor as Vector3).y)]
		parts[str(part_name)] = values
		lines.append("%s=%s|%s|%s|%.3f,%.3f|%.3f,%.3f|%.3f|%.3f|%.3f|%.3f" % [part_name, values[0],
			values[1], values[2], values[3], values[4], values[5], values[6], values[7], values[8],
			values[9], values[10]])
	var canonical := ";".join(lines) + "\n"
	pair.hashing.update(canonical.to_utf8_buffer())
	pair.in_block += 1
	if pair.in_block >= DIGEST_BLOCK:
		_flush_digest(pair)
	var key := "%s/%s/%d" % [pair.phase, pair.label, pair.index]
	if pair.index % SAMPLE_EVERY == 0:
		var sample := {"key": key, "inputs": inputs, "parts": parts}
		if write_golden:
			_samples.append(sample)
		elif _golden_samples.has(key):
			var problem := _sample_difference(_golden_samples[key], sample)
			if not problem.is_empty():
				mismatches += 1
				if _detail_reported < MISMATCH_DETAIL_LIMIT:
					_detail_reported += 1
					push_error("GOLDEN %s [%s]: %s" % [key, inputs, problem])
	pair.index += 1

func _flush_digest(pair: Pair) -> void:
	if pair.in_block == 0:
		return
	pair.digests.append(pair.hashing.finish().hex_encode())
	pair.hashing = HashingContext.new()
	pair.hashing.start(HashingContext.HASH_SHA256)
	pair.in_block = 0

func _sample_difference(golden: Dictionary, sample: Dictionary) -> String:
	var expected: Dictionary = golden.get("parts", {})
	var actual: Dictionary = sample.parts
	if str(golden.get("inputs", "")) != str(sample.inputs):
		return "inputs '%s' vs golden '%s'" % [sample.inputs, golden.get("inputs", "")]
	for part_name: String in expected:
		if not actual.has(part_name):
			return "%s missing (golden %s)" % [part_name, expected[part_name]]
	for part_name: String in actual:
		if not expected.has(part_name):
			return "%s not in the golden" % part_name
		var have: Array = actual[part_name]
		var want: Array = expected[part_name]
		if have.size() != want.size():
			return "%s fields %s vs %s" % [part_name, have, want]
		for index: int in range(have.size()):
			if have[index] is float or want[index] is float:
				if absf(float(have[index]) - float(want[index])) > SAMPLE_EPSILON:
					return "%s field %d %s vs golden %s" % [part_name, index, have[index], want[index]]
			elif str(have[index]) != str(want[index]):
				return "%s field %d %s vs golden %s" % [part_name, index, have[index], want[index]]
	return ""

# --- Constants, helpers, divergence, widths, layer -----------------------------------

func _check_constants() -> void:
	expect(Banner.NAMEPLATE_HEIGHT == ReplicatedActor3D.NAMEPLATE_HEIGHT
		and Banner.CREATURE_ACTOR_KIND == ReplicatedActor3D.CREATURE_ACTOR_KIND
		and Banner.MEASURE_SCALE == WORLD_LABEL_STYLE.RASTER_SCALE,
		"nameplate height, creature kind and the layout measure scale are the actor's")
	var marker: Node3D = COMBAT_TARGET_MARKER.new()
	var pointer: Label3D = marker.get("pointer")
	expect(Banner.POINTER_TEXT == pointer.text and Banner.POINTER_COLOUR == COMBAT_TARGET_MARKER.COLOUR
		and Banner.POINTER_BORDER == COMBAT_TARGET_MARKER.BORDER
		and Style.POINTER_FONT_SIZE == pointer.font_size and Style.POINTER_OUTLINE_SIZE == pointer.outline_size
		and is_equal_approx(Style.POINTER_PIXEL, pointer.pixel_size),
		"the pointer's glyph, colours and sizes are CombatTargetMarker's")
	var defaults := Banner.pointer_style({})
	expect(int(defaults.font_size) == pointer.font_size and int(defaults.outline_size) == pointer.outline_size
		and defaults.colour == pointer.modulate, "the default marker style sizes the pointer as today")
	marker.free()
	var mine := Banner.health_bar_texture()
	var theirs: GradientTexture2D = ReplicatedActor3D._health_bar_texture()
	expect(mine.width == theirs.width and mine.height == theirs.height and mine.fill_from == theirs.fill_from
		and mine.fill_to == theirs.fill_to and mine.gradient.colors == theirs.gradient.colors
		and mine.gradient.offsets == theirs.gradient.offsets, "the bar fill's shading is the actor's")

func _check_static_helpers() -> void:
	var dtos := [{"kind": 1, "name": "A"}, {"kind": 2}, {"kind": 4}, {"kind": 5}, {"kind": 5, "enhanced": true},
		{"kind": 1, "map_type": 2}, {"kind": 1, "name_colour": 5, "guild_colour": 7, "guild_tag": "X"},
		{"kind": 5, "name_colour": 99}, {"kind": 2, "name_colour": 3, "extra": 1}]
	var problems: Array[String] = []
	for overridden: bool in [false, true]:
		if overridden:
			for role: String in ROLES:
				TextColors.set_color(role, Color(0.3, 0.6, 0.9, 0.8))
		for dto: Dictionary in dtos:
			var info := Banner.name_info(dto)
			if info != ReplicatedActor3D._name_info(dto):
				problems.append("name_info %s" % [dto])
			if Banner.name_colour_role(info) != ReplicatedActor3D.name_color_role(dto):
				problems.append("role %s" % [dto])
			if Banner.name_colour(info) != ReplicatedActor3D._nameplate_colour(dto):
				problems.append("name colour %s" % [dto])
			if Banner.guild_tag_colour(info) != ReplicatedActor3D.guild_tag_color(dto):
				problems.append("guild colour %s" % [dto])
	TextColors.reset()
	for step: int in range(-2, 13):
		var ratio := step / 10.0
		if Banner.health_colour(ratio) != ReplicatedActor3D._health_colour(ratio):
			problems.append("health colour %.1f" % ratio)
	expect(problems.is_empty(), "name, role, guild and health colours equal the actor's statics %s" % [problems])

## Today a speech line cleared while the actor was out of draw range comes
## back when it returns (set_drawn(true) re-shows the nodes it hid). The model
## keeps it cleared; OV-3 takes the model's rule (owner sign-off item).
func _check_speech_divergence() -> void:
	if not node_mode:
		return
	var pair := _make_pair(ACTORS[1], "divergence")
	_op_speech(pair, SPEECH_SHORT, Color.WHITE)
	_op_drawn(pair, false)
	_sweep(pair)
	_op_clear_speech(pair)
	_op_drawn(pair, true)
	var node_speech := _node_part(pair.actor, Banner.SPEECH_BUBBLE)
	var model_speech: Dictionary = pair.model.call("part", Banner.SPEECH_BUBBLE)
	print("speech cleared out of range, back in range: node path visible=%s, model visible=%s" % [
		node_speech.visible, model_speech.visible])
	expect(not bool(model_speech.visible), "the model keeps a cleared speech line hidden after a return to range")
	pair.actor.queue_free()

## How far the 2D layer's shaped widths (TextLine at the design size) are from
## the 3D layout's measure (4x raster / 4). Informative for OV-7; bounded.
func _check_shaping_widths() -> void:
	var texts: Array = []
	for spec: Dictionary in ACTORS:
		texts.append([str(spec.dto.name), Style.NAMEPLATE_FONT_SIZE])
		if spec.dto.has("guild_tag"):
			texts.append(["  [%s]" % spec.dto.guild_tag, Style.NAMEPLATE_FONT_SIZE])
	for title: Array in TEXTS:
		texts.append([str(title[0]), Style.TITLE_FONT_SIZE])
		if not str(title[1]).is_empty():
			texts.append(["<%s>" % title[1], Style.OCCUPATION_FONT_SIZE])
	for digits: Array in DIGITS:
		texts.append(["%d/%d" % [digits[0], digits[1]], Style.HEALTH_NUMBER_FONT_SIZE])
		texts.append(["%d/%d" % [digits[1], digits[1]], Style.HEALTH_NUMBER_FONT_SIZE])
	var worst := 0.0
	var worst_text := ""
	for entry: Array in texts:
		if str(entry[0]).is_empty():
			continue
		var line := TextLine.new()
		line.add_string(str(entry[0]), Style.font(), int(entry[1]))
		var delta := absf(line.get_size().x - Banner.text_width(str(entry[0]), int(entry[1])))
		if delta > worst:
			worst = delta
			worst_text = str(entry[0])
	print("shaping: 2D TextLine width vs the 3D layout measure, worst %.3f design px ('%s', %d texts)" % [
		worst, worst_text, texts.size()])
	expect(worst < 2.0, "2D shaping widths stay within 2 design px of the 3D layout measure (%.3f)" % worst)

## The banner on a real OverheadLayer (headless, update_now called directly).
func _check_layer() -> void:
	root.size = Vector2i(1920, 1080)
	await process_frame
	var container := TextureRect.new()
	container.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	root.add_child(container)
	container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1920, 1080)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	container.add_child(viewport)
	var world_stage := Node3D.new()
	viewport.add_child(world_stage)
	var camera := Camera3D.new()
	camera.fov = 50.0
	camera.near = 0.5
	world_stage.add_child(camera)
	camera.current = true
	camera.global_transform = Transform3D(Basis.from_euler(Vector3(deg_to_rad(-60.0), 0.0, 0.0)),
		Vector3(0.0, 22.5, 13.0))
	var layer := LayerScript.new()
	layer.shape_budget_usec = 1000000
	layer.rerecord_budget_usec = 1000000
	layer.snap_origins = false
	root.add_child(layer)
	layer.configure(viewport, container)
	layer.active = true
	await process_frame
	var actor := Node3D.new()
	world_stage.add_child(actor)
	var banner := Banner.new()
	banner.attach(actor)
	banner.set_name_info({"kind": 2, "name": "Ammet Sorrel"})
	banner.set_vitals(13, 20)
	banner.set_health_visible(true)
	banner.set_title("Orchard scout")
	banner.set_status_effects(["poison", "shield"])
	expect(layer.accepts(actor) and not layer.accepts(_stage),
		"the layer accepts the game-world actor and not one in another world")
	banner.register(layer)
	expect(layer.item_count() == 1, "an actor with only a block costs the layer one item (%d)" % layer.item_count())
	layer.update_now()
	var block: Item = banner.item(Banner.ITEM_BLOCK)
	# World-view pixels to the layer's canvas units (the view control's rect).
	var view_scale := container.size / Vector2(viewport.size)
	var expected := camera.unproject_position(actor.to_global(Vector3(0.0, Banner.NAMEPLATE_HEIGHT, 0.0))) \
		* view_scale
	expect(block.is_drawn() and block.drawn_origin().distance_to(expected) < 0.01 and banner.builds >= 1,
		"the block is built, recorded and drawn at the projected name height (%s vs %s)" % [
			block.drawn_origin(), expected])
	var built := banner.builds
	var rerecords := layer.rerecords_total
	banner.set_fade(0.5)
	layer.update_now()
	banner.set_crowded(true)
	layer.update_now()
	expect(banner.builds == built and layer.rerecords_total == rerecords and not block.is_drawn(),
		"fade and crowding change no content: no build, no re-record; crowding hides the block")
	banner.set_crowded(false)
	banner.set_fade(1.0)
	banner.set_vitals(9, 20)
	layer.update_now()
	expect(banner.builds == built + 1 and layer.rerecords_total == rerecords + 1 and block.is_drawn(),
		"a health change builds and re-records the block once")
	banner.set_quest_available(true, 0)
	layer.now_usec_override = 0
	banner.show_speech(SPEECH_LONG, Color.WHITE)
	layer.update_now()
	var quest: Item = banner.item(Banner.ITEM_QUEST)
	var speech: Item = banner.item(Banner.ITEM_SPEECH)
	var k := layer.canvas_scale()
	expect(layer.item_count() == 3 and quest.is_drawn() and speech.is_drawn()
		and is_equal_approx(quest.drawn_origin().y, block.drawn_origin().y - Style.QUEST_RISE_FROM * k)
		and quest.pass_modulate(Style.PASS_TEXT) == TextColors.color("world_quest"),
		"quest and speech join on first use; the quest mark starts 36 px up in the quest colour")
	expect(quest.anchor == block.anchor and speech.anchor == block.anchor,
		"block, quest and speech share one anchor (projected once)")
	banner.set_drawn(false)
	layer.update_now()
	expect(not block.is_drawn() and not quest.is_drawn() and not speech.is_drawn(),
		"an actor out of draw range draws nothing")
	banner.set_drawn(true)
	actor.visible = false
	layer.update_now()
	expect(not block.is_drawn() and not speech.is_drawn(), "a hidden actor node hides its banner")
	actor.visible = true
	banner.lift(3.0)
	built = banner.builds
	rerecords = layer.rerecords_total
	layer.update_now()
	var lifted := camera.unproject_position(actor.to_global(Vector3(0.0, 3.0, 0.0))) * view_scale
	expect(block.drawn_origin().distance_to(lifted) < 0.01 and banner.builds == built
		and layer.rerecords_total == rerecords, "lift moves the anchor without a re-record")
	banner.set_pointer(true, 2.0)
	banner.set_boss_rank(2, 2.6)
	layer.update_now()
	var pointer: Item = banner.item(Banner.ITEM_POINTER)
	var boss: Item = banner.item(Banner.ITEM_BOSS)
	expect(layer.item_count() == 5 and pointer.is_drawn() and boss.is_drawn()
		and is_equal_approx(pointer.drawn_scale(), k * Style.design_scale(Style.POINTER_PIXEL)),
		"pointer and boss tag join when shown; the pointer keeps its own scale")
	# A scaled item's glyphs are rasterised at the size it is drawn at (the
	# TextServer size cache gets size x oversampling x scale), not minified.
	var scaled := Item.new(actor, Vector3(0.0, 1.0, 0.0), &"Scaled")
	scaled.scale = 0.5
	scaled.add_text("Scaled probe", 28, Vector2.ZERO, Color.WHITE)
	layer.add_item(scaled)
	layer.update_now()
	var raster := maxf(Style.OVERSAMPLING_STEP, snappedf(layer.oversampling() * 0.5, Style.OVERSAMPLING_STEP))
	var wanted_size := Vector2i(roundi(28 * raster), 0)
	var cached := false
	for rid: RID in Style.font().get_rids():
		if wanted_size in TextServerManager.get_primary_interface().font_get_size_cache_list(rid):
			cached = true
	expect(scaled.is_drawn() and cached,
		"a half-scale item's 28 px text is rasterised at %s px (oversampling %.3f x 0.5)" % [
			wanted_size.x, layer.oversampling()])
	layer.remove_item(scaled)
	# Three anchors (block, boss, pointer) on one node: one watch, all follow it.
	expect(layer.anchor_count() == 3 and layer.watched_node_count() == 1,
		"three anchors on one actor are watched through one set of connections (%d anchors, %d nodes)" % [
			layer.anchor_count(), layer.watched_node_count()])
	actor.visible = false
	layer.update_now()
	var none_drawn := not block.is_drawn() and not boss.is_drawn() and not pointer.is_drawn() \
		and not quest.is_drawn()
	actor.visible = true
	layer.update_now()
	expect(none_drawn and block.is_drawn() and boss.is_drawn() and pointer.is_drawn(),
		"hiding and showing the actor node hides and shows every item on every anchor")
	banner.unregister()
	expect(layer.item_count() == 0 and banner.layer() == null and layer.watched_node_count() == 0
		and actor.visibility_changed.get_connections().is_empty()
		and actor.tree_exiting.get_connections().is_empty(),
		"unregister removes every item and the layer's connections to the actor")
	layer.queue_free()
	container.queue_free()
	await process_frame

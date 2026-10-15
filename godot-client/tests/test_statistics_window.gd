extends SceneTree
## The Statistics tab: a character on the left, skills on the right.
##
## It was one bbcode document in three columns, which meant the two things a
## player most wants to see could not be drawn at all: a bar showing how far
## through a level a skill is, and a button that spends a pick point. Both are
## controls, and bbcode has neither.
##
## The grouping is a decision rather than a taxonomy. Magic and Summoning sit
## under Combat because that is what they are used for here, and Potion under
## Crafting because it is mixed at a bench.

const MAIN := "res://src/app/main.gd"

var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_grouping()
	_every_skill_appears_once()
	_the_window_is_built_from_controls()
	_the_bar_reads_the_level_not_the_lifetime()
	_colour_bands()
	print("statistics window: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _source() -> String:
	return FileAccess.get_file_as_string(MAIN)

func _grouping() -> void:
	var main = load(MAIN)
	var groups: Array = main.SKILL_GROUPS
	_expect(groups.size() == 3, "three groups")
	var by_name := {}
	for group: Array in groups:
		by_name[str(group[0])] = group[1]
	_expect(by_name.has("Combat") and by_name.has("Crafting")
		and by_name.has("Gathering"), "Combat, Crafting and Gathering")
	var combat: Array = by_name.get("Combat", [])
	_expect(combat.has("magic") and combat.has("summoning"),
		"magic and summoning are fought with, so they sit under Combat")
	_expect(not by_name.has("Magic"),
		"and there is no separate Magic group left")
	_expect((by_name.get("Crafting", []) as Array).has("potion"),
		"potion is mixed at a bench, so it sits under Crafting")

func _every_skill_appears_once() -> void:
	var main = load(MAIN)
	var seen: Array[String] = []
	for group: Array in main.SKILL_GROUPS:
		for skill: Variant in group[1] as Array:
			_expect(not seen.has(str(skill)),
				"%s is in one group only" % str(skill))
			seen.append(str(skill))
	# Overall is the footer rather than a row in a group, so it is the one
	# skill deliberately absent from the grouping.
	for skill: String in main.EXPERIENCE_SKILLS:
		if skill == "overall":
			_expect(not seen.has(skill), "overall is the footer, not a group row")
			continue
		_expect(seen.has(skill), "%s is on the page somewhere" % skill)

func _the_window_is_built_from_controls() -> void:
	var source: String = _source()
	_expect(not source.is_empty(), "main.gd is readable")
	_expect(source.contains("func _build_statistics_tab("),
		"the tab is built rather than written as bbcode")
	_expect(source.contains("stats_text.hide()"),
		"and the text panel it replaced is hidden, not deleted")
	_expect(source.contains("func _stats_skill_row("),
		"a skill is a row with a bar in it")
	_expect(source.contains("func _stats_spend_row("),
		"an attribute is a row with a button in it")
	_expect(source.contains("func _experience_colour("),
		"and how far along reads as a colour as well as a length")

func _the_bar_reads_the_level_not_the_lifetime() -> void:
	# At high levels the lifetime fraction barely moves, so a bar measuring it
	# would never visibly fill. The bar measures progress inside the level.
	var hud := load(MAIN).new() as Control
	var row := hud.call("_stats_skill_row", "attack", {"attack":40, "attack_base":40,
		"attack_exp":859115, "attack_exp_next":900302}) as Control
	_expect(is_equal_approx((row.get_node("Experience/Bar") as ProgressBar).value, 0.5),
		"the bar measures progress between the current and next level floors")
	_expect((row.get_node("Experience/Totals") as Label).text == "859,115 / 900,302",
		"the totals beside it are still the lifetime figures")
	row.free()
	hud.free()

func _colour_bands() -> void:
	var main = load(MAIN)
	var nearly: Color = main._experience_colour(0.95)
	var halfway: Color = main._experience_colour(0.6)
	var started: Color = main._experience_colour(0.05)
	_expect(nearly != halfway and halfway != started,
		"each band is its own colour")
	_expect(nearly.g > started.g,
		"and nearly-there is the greener end, which is the one to look for")

func _expect(condition: bool, description: String) -> void:
	if condition:
		return
	_failures += 1
	push_error("statistics window: %s" % description)
	printerr("FAIL ", description)

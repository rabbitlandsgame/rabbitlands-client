extends SceneTree
## Guards the commands this client answers itself.
##
## The console had no command table, so every `#` command went out as raw text,
## including the ones no server has ever implemented. These are the ones about
## the player's own screen. Nothing here touches gameplay, and anything not in
## the table has to reach the server untouched - deciding locally what the
## server should have answered is the mistake this codebase avoids.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var console := ConsoleCommands.new()
	console.current_map = "four_gates"
	console.current_tile = Vector2i(770, 481)

	# Anything the table does not name goes to the server untouched.
	for passed_through: String in ["#quests", "#sp shield 2", "hello there",
			"#auction browse", "#give Gold Coins 5"]:
		_expect(not console.run(passed_through).handled,
			"%s is left for the server" % passed_through)

	# Marks: the player's own annotation of their own screen.
	var marked: ConsoleCommands.Result = console.run("#mark Reed bank")
	_expect(marked.handled and marked.changed
		and console.marks.size() == 1
		and int(console.marks[0].get("x", 0)) == 770
		and str(console.marks[0].get("map", "")) == "four_gates",
		"#mark records the tile the client was told it is standing on")
	_expect(console.run("#mark Reed bank").handled and console.marks.size() == 1,
		"marking the same label again moves it rather than duplicating it")
	_expect(console.run("#markpos 100 200 Ferry").handled
		and console.marks.size() == 2
		and int(console.marks[1].get("y", 0)) == 200,
		"#markpos takes an explicit tile")
	_expect(console.run("#markpos 100").lines[0].contains("Usage"),
		"a malformed #markpos says how to use it rather than guessing")
	var listed: ConsoleCommands.Result = console.run("#marks")
	_expect(listed.lines.size() == 3
		and listed.lines[1].contains("Reed bank"),
		"#marks lists this map's marks")
	_expect(console.run("#unmark Ferry").changed and console.marks.size() == 1,
		"#unmark removes one")
	_expect(not console.run("#unmark Nothing").changed,
		"removing a mark that is not there changes nothing")
	console.current_map = "mirrorhold"
	console.current_tile = Vector2i(40, 50)
	console.run("#mark Reed bank")
	_expect(console.marks.size() == 2
		and console.run("#marks").lines.size() == 2,
		"different maps can each have a mark with the same label")
	_expect(console.run("#unmark Reed bank").changed
		and console.marks.size() == 1
		and str(console.marks[0].get("map", "")) == "four_gates"
		and int(console.marks[0].get("x", 0)) == 770,
		"#unmark removes the current map's mark and preserves the other map's")
	_expect(not console.run("#unmark Reed bank").changed
		and console.marks.size() == 1,
		"#unmark never removes a mark that only exists on another map")
	console.current_map = "four_gates"

	# Ignore and filter decide what the player is shown, and nothing else.
	console.run("#ignore Griefer")
	_expect(console.ignored == ["griefer"],
		"#ignore is case-insensitive: %s" % str(console.ignored))
	_expect(not console.allows("Griefer", "Griefer: buy my things")
		and console.allows("Friend", "Friend: hello"),
		"an ignored speaker is hidden and everyone else is not")
	console.run("#filter SELLING")
	_expect(not console.allows("Friend", "Friend: SELLING everything")
		and not console.allows("Friend", "Friend: selling everything"),
		"a filtered word is hidden whatever its case")
	console.run("#unignore griefer")
	console.run("#unfilter selling")
	_expect(console.allows("Griefer", "Griefer: buy my things")
		and console.ignored.is_empty() and console.filters.is_empty(),
		"both lists can be emptied again")

	# Aliases expand only at the start of a line, and never eat a message.
	console.run("#alias wb Welcome back!")
	_expect(console.expand("wb") == "Welcome back!"
		and console.expand("wb friend") == "Welcome back! friend"
		and console.expand("nowb") == "nowb"
		and console.expand("say wb") == "say wb",
		"an alias expands its own head and nothing else")
	console.run("#unalias wb")
	_expect(console.expand("wb") == "wb", "and can be removed")

	# Arithmetic, and the refusal that keeps it arithmetic.
	_expect(console.run("#calc 12 * (3 + 4)").lines[0].contains("84"),
		"#calc works out an expression")
	var refused: String = console.run("#calc OS.execute('ls')").lines[0]
	_expect(refused.contains("numbers"),
		"#calc refuses anything that is not arithmetic: " + refused)
	_expect(console.run("#calc").lines[0].contains("Usage"),
		"#calc with nothing says how to use it")

	# Searching what the server has already said.
	var history: Array = [{"channel": 0, "text": "Salina: fresh reeds today"},
		{"channel": 0, "text": "Toran: the road is clear"}]
	var found: ConsoleCommands.Result = console.run("#find reeds", history)
	_expect(found.lines.size() == 2 and found.lines[1].contains("Salina"),
		"#find searches what the client was told")
	_expect(console.run("#find dragons", history).lines[0].contains("Nothing"),
		"and says so when nothing matches")

	# Completion and help.
	_expect(console.completions("#mark") == ["#mark", "#markpos", "#marks"],
		"completion offers every command with that prefix: %s"
			% str(console.completions("#mark")))
	_expect(console.completions("#zzz").is_empty(),
		"and nothing for a prefix no command has")
	var help: ConsoleCommands.Result = console.run("#help")
	_expect(help.lines.size() == ConsoleCommands.COMMANDS.size() + 2,
		"#help lists every command in the table")
	_expect(help.send_on and not console.run("#marks").send_on
		and not console.run("#calc 1 + 1").send_on,
		"and #help alone goes on to the server, which lists its own")

	# Away.
	_expect(console.run("#afk gone for tea").changed
		and console.afk_reason == "gone for tea",
		"#afk records the reason")
	_expect(console.run("#afk").lines[0].contains("No longer")
		and console.afk_reason.is_empty(),
		"and clears it")

	print("console command tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

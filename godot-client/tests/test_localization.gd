extends SceneTree
## Guards the translation table and the screenshot binding.
##
## Every string in the client was hardcoded. The translation system is adopted
## here rather than retrofitted later, when it costs far more: the table is a
## CSV Godot imports, the project loads it, and the first slice of windows
## reads through `tr()`.
##
## This suite deliberately checks the **mechanism** rather than claiming the
## whole client is translated. The traceability row states exactly how much is
## converted and what is not.

const TABLE := "res://data/i18n/strings.csv"
const TRANSLATION := "res://data/i18n/strings.en.translation"
## The windows converted in this pass. Anything else is still hardcoded, which
## is recorded rather than implied.
const CONVERTED: Array[String] = [
	"res://src/ui/settings_window.gd",
	"res://src/ui/player_info_panel.gd",
]

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var keys: Array[String] = _table_keys()
	_expect(keys.size() >= 25,
		"the table carries the strings this pass converted: %d" % keys.size())

	var translation: Resource = load(TRANSLATION)
	_expect(translation is Translation,
		"the CSV is imported as a Translation resource Godot can load")
	if translation is Translation:
		var loaded: Translation = translation as Translation
		var missing: Array[String] = []
		for key: String in keys:
			if str(loaded.get_message(key)).is_empty():
				missing.append(key)
		_expect(missing.is_empty(),
			"every key in the table has an English string: %s" % str(missing))

	var registered: Variant = ProjectSettings.get_setting(
		"internationalization/locale/translations", PackedStringArray())
	_expect(PackedStringArray(registered).has(TRANSLATION),
		"the project loads the table, so tr() works without any setup")

	# Every key the converted windows ask for has to exist, or the player sees
	# the key itself on screen.
	var asked: Array[String] = []
	for path: String in CONVERTED:
		var file := FileAccess.open(path, FileAccess.READ)
		if not _expect(file != null, "%s is readable" % path):
			continue
		var source: String = file.get_as_text()
		var search := 0
		while true:
			var start: int = source.find("tr(\"", search)
			if start < 0:
				break
			var end: int = source.find("\"", start + 4)
			if end < 0:
				break
			asked.append(source.substr(start + 4, end - start - 4))
			search = end
	_expect(not asked.is_empty(), "the converted windows do ask for strings")
	var unknown: Array[String] = []
	for key: String in asked:
		if not keys.has(key):
			unknown.append(key)
	_expect(unknown.is_empty(),
		"every key a window asks for is in the table: %s" % str(unknown))

	# tr() resolves through the running TranslationServer, not just the file.
	TranslationServer.set_locale("en")
	var window := Control.new()
	root.add_child(window)
	_expect(window.tr("ELORIA_SETTINGS_TITLE") == "Settings",
		"tr() resolves a key to its English string: %s"
			% window.tr("ELORIA_SETTINGS_TITLE"))
	_expect(window.tr("ELORIA_NOT_A_KEY") == "ELORIA_NOT_A_KEY",
		"and an unknown key comes back unchanged rather than empty")
	_expect(window.tr("ELORIA_SCREENSHOT_SAVED").format({"path": "shot.png"})
			== "Screenshot saved to shot.png",
		"a string with placeholders formats: %s"
			% window.tr("ELORIA_SCREENSHOT_SAVED").format({"path": "shot.png"}))

	# The screenshot binding, and a real file on disk.
	_expect(InputMap.has_action("screenshot")
		and not InputMap.action_get_events("screenshot").is_empty(),
		"the screenshot action is declared and bound")
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	for _settle: int in range(3):
		await process_frame
	# Headless has no framebuffer, so a capture cannot succeed here - and the
	# point of this case is that it says so rather than reporting a file it
	# did not write. The capture itself is proved under a real display by
	# tests/integration/rendered_screenshot.gd.
	var saved: String = str(main.call("_save_screenshot"))
	var lines: Array = (root.get_node("/root/AppState").get("chat_lines")
		as Array)
	var last: String = (str((lines[lines.size() - 1] as Dictionary).get(
		"text", "")) if not lines.is_empty() else "")
	_expect(saved.is_empty() and last.contains("could not be saved"),
		"with nothing rendered the player is told it failed, not given a path"
			+ ": " + last)

	print("localization tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

func _table_keys() -> Array[String]:
	var keys: Array[String] = []
	var file := FileAccess.open(TABLE, FileAccess.READ)
	if file == null:
		_expect(false, "the translation table is readable")
		return keys
	var header := true
	while not file.eof_reached():
		var row: PackedStringArray = file.get_csv_line()
		if row.is_empty() or row[0].is_empty():
			continue
		if header:
			header = false
			_expect(row[0] == "keys" and row.size() >= 2,
				"the table has a keys column and at least one locale")
			continue
		keys.append(row[0])
	return keys

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

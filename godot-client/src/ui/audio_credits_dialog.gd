extends AcceptDialog
## Credits remain readable offline and link to the creators and license terms.

const CREDITS_PATH := "res://assets/audio/CREDITS.txt"
var credits: RichTextLabel

func _ready() -> void:
	name = "AudioCredits"
	title = "Audio credits"
	exclusive = true
	min_size = Vector2i(480, 300)
	get_ok_button().text = "Close"
	credits = RichTextLabel.new()
	credits.name = "CreditsText"
	credits.bbcode_enabled = true
	credits.selection_enabled = true
	credits.add_theme_font_size_override("normal_font_size", 15)
	add_child(credits)
	credits.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	credits.offset_left = 18
	credits.offset_top = 12
	credits.offset_right = -18
	credits.offset_bottom = -55
	var text := FileAccess.get_file_as_string(CREDITS_PATH)
	if text.is_empty():
		push_error("Audio credits are missing from this game package")
		text = "Audio credits could not be loaded."
	var links := RegEx.new()
	links.compile("https://[^\\s]+")
	credits.text = links.sub(text, "[url=$0]$0[/url]", true)
	credits.meta_clicked.connect(_open_source)

func _open_source(meta: Variant) -> void:
	var url := str(meta)
	if url.begins_with("https://"):
		OS.shell_open(url)

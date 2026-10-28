class_name RLHeadAppearance
extends RefCounted
## One RL head face: the sex of the head module, the identity
## controls that drive its `id_*` blend shapes, the colours and painted
## features of its skin, eyes and hair, and the hair and facial-hair styles.
##
## Pure data. RLHeadRig turns it into meshes and shader parameters; nothing
## here touches a node. Three forms exist:
##   * this object, which the rig and the lab work with,
##   * a Dictionary (`to_dict` / `from_dict`), the same keys as one entry of
##     data/actors/rl_head_presets.json plus `preset`, `stubble` and `version`,
##     which is what an actor's `appearance.rl_head` carries,
##   * a compact byte form (`encode` / `decode`), a proposal for the wire that
##     is NOT wired into the protocol; see ENCODING_VERSION below.
##
## Control values run from -1 to 1; a control missing from `controls` is 0,
## the head as authored. Colours are sRGB, like AppearanceVariants' palettes.

const PRESETS_PATH := "res://data/actors/rl_head_presets.json"
const NONE := "none"
## The beard name that is drawn by the skin shader rather than a beard GLB.
const STUBBLE := "stubble"
## How much stubble the `stubble` beard paints when nothing else says.
const DEFAULT_STUBBLE := 0.6
const SEXES: Array[String] = ["female", "male"]

## Version 2 of the byte form, little-endian:
##
##   offset  size  field
##   0       1     version (2)
##   1       1     flags: bit 0 = male head; bits 1-7 reserved, 0
##   2       2     control-set hash: FNV-1a over the comma-joined control names
##                 the encoder was given, folded to 16 bits (`control_set_hash`)
##   4       1     N, the number of controls that follow
##   5       N/2   controls, 4 bits each, two to a byte, control i in byte
##                 5 + i / 2, the low nibble first. Code c in 1..15 is the value
##                 (c - 8) / 7, so -1, 0 and 1 are exact and a step is 1/7;
##                 code 0 is reserved and decodes as 0.
##   +0      10    skin, eyes, hair colour, brow colour, lip tint: RGB565 each
##   +10     1     freckles (low nibble), liner (high nibble): amount * 15
##   +11     1     stubble (low nibble); high nibble reserved, 0
##   +12     1     brow style in quarter steps, 0..12 (low nibble: 0 arched,
##                 4 straight, 8 soft, 12 angled, a blend between); brow
##                 thickness (high nibble), coded like a control
##   +13     1     liner wing (low nibble): amount * 15; high nibble reserved, 0
##   +14     1+    hair style: an index into HAIR_STYLES, or 255 followed by
##                 one length byte and that many UTF-8 bytes for a name the
##                 registry does not list
##   ...     1+    facial hair: the same, against BEARD_STYLES
##
## Version 1 is version 2 without bytes +12 and +13; it still decodes, with
## the default brow (soft, thickness 0) and no wing.
##
## Controls are written in the order of the head's `rlHead.controls`, which is
## what both ends pass as `control_names`; the hash lets a decoder holding a
## different revision of the head notice instead of misreading the nibbles.
## With the heads' 21 controls a face is 32 bytes.
const ENCODING_VERSION := 2
## Append-only registries for the style bytes. A name not listed travels inline.
const HAIR_STYLES: Array[String] = [NONE, "mira_bun", "rowan_shag", "legacy:parted",
	"legacy:long", "legacy:buns", "legacy:buzzed", "legacy:bob", "legacy:ponytail",
	"legacy:braid", "legacy:topknot", "legacy:mohawk"]
const BEARD_STYLES: Array[String] = [NONE, STUBBLE, "full_beard", "short_beard",
	"moustache", "goatee"]
## The painted brow styles, by `brow_style`: one channel each of
## head_<sex>_brows.png. A fractional style blends its two neighbours.
const BROW_STYLES: Array[String] = ["arched", "straight", "soft", "angled"]
const DEFAULT_BROW_STYLE := 2.0
const INLINE_STYLE := 255
const CONTROL_STEPS := 7.0

var sex := "female"
## The preset this face started from, kept for the lab and for diagnostics.
var preset := ""
var label := ""
var controls: Dictionary = {}
var skin := Color(0.85, 0.66, 0.55)
var eyes := Color(0.30, 0.45, 0.60)
var hair_color := Color(0.25, 0.14, 0.08)
var brow_color := Color(0.20, 0.12, 0.07)
var lip_tint := Color(0.75, 0.45, 0.42)
var freckles := 0.0
var liner := 0.0
var stubble := 0.0
var hair := NONE
var beard := NONE
## 0 arched, 1 straight, 2 soft, 3 angled (BROW_STYLES); fractions blend.
var brow_style := DEFAULT_BROW_STYLE
## -1 thin to 1 thick.
var brow_thickness := 0.0
## 0 to 1: how far the liner flicks out past the outer corner of the eye.
var liner_wing := 0.0
## An RL hairstyle's length and volume, -1 to 1 (0 as authored), and its
## finish 0..2 (PortraitCustomization `hair_detail`), through the hairstyle's
## optional `hl_` blend shapes (RLHeadRig). Not part of the byte form.
var hair_length := 0.0
var hair_volume := 0.0
var hair_detail := 0
## The facial hair's own colour when `beard_color_set` (a beard card texture
## lights differently from a hairstyle's), else the hair colour. Not part of
## the byte form.
var beard_color := Color(0.25, 0.14, 0.08)
var beard_color_set := false

static var _presets: Dictionary = {}
static var _presets_loaded := false


## Every preset in data/actors/rl_head_presets.json, by name. Read once.
static func presets() -> Dictionary:
	if not _presets_loaded:
		_presets_loaded = true
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PRESETS_PATH))
		if parsed is Dictionary and (parsed as Dictionary).get("presets") is Dictionary:
			_presets = (parsed as Dictionary)["presets"] as Dictionary
		else:
			push_warning("RL heads: no presets in " + PRESETS_PATH)
	return _presets


## Drops the cached presets so an edited file is read again (the lab's reload).
static func reload_presets() -> void:
	_presets_loaded = false
	_presets = {}


## The preset names for one sex, in file order; every name when `for_sex` is "".
static func preset_names(for_sex := "") -> PackedStringArray:
	var names := PackedStringArray()
	for name: String in presets():
		if for_sex.is_empty() or str((presets()[name] as Dictionary).get("sex", "")) == for_sex:
			names.append(name)
	return names


## A named preset, or null when the file has no such entry.
static func from_preset(name: String) -> RLHeadAppearance:
	var entry: Variant = presets().get(name)
	if entry is not Dictionary:
		return null
	var result := RLHeadAppearance.new()
	result._merge(entry as Dictionary)
	result.preset = name
	if result.label.is_empty():
		result.label = name.capitalize()
	return result


## The dictionary form, overlaid on the preset it names (`preset`) when it
## names one, so `{"preset": "mira", "eyes": [0.2, 0.4, 0.7]}` is Mira with
## blue eyes. A `controls` entry replaces the preset's controls as a whole.
## Unknown keys are ignored.
static func from_dict(data: Dictionary) -> RLHeadAppearance:
	var result: RLHeadAppearance = null
	var preset_name := str(data.get("preset", ""))
	if not preset_name.is_empty():
		result = from_preset(preset_name)
	if result == null:
		result = RLHeadAppearance.new()
		result.preset = preset_name
	result._merge(data)
	return result


## What `appearance.rl_head` may hold: a preset name or the dictionary form.
## Anything else, and an unknown preset name, is null.
static func from_value(value: Variant) -> RLHeadAppearance:
	if value is RLHeadAppearance:
		return (value as RLHeadAppearance).duplicate_appearance()
	if value is String or value is StringName:
		return from_preset(str(value))
	if value is Dictionary:
		return from_dict(value as Dictionary)
	return null


func duplicate_appearance() -> RLHeadAppearance:
	return RLHeadAppearance.from_dict(to_dict())


func to_dict() -> Dictionary:
	return {
		"version": ENCODING_VERSION,
		"preset": preset,
		"label": label,
		"sex": sex,
		"controls": controls.duplicate(),
		"skin": _color_array(skin),
		"eyes": _color_array(eyes),
		"hair_color": _color_array(hair_color),
		"brow_color": _color_array(brow_color),
		"lip_tint": _color_array(lip_tint),
		"freckles": freckles,
		"liner": liner,
		"stubble": stubble,
		"hair": hair,
		"beard": beard,
		"brow_style": brow_style_value(),
		"brow_thickness": snappedf(brow_thickness, 0.0001),
		"liner_wing": snappedf(liner_wing, 0.0001),
		"hair_length": snappedf(hair_length, 0.0001),
		"hair_volume": snappedf(hair_volume, 0.0001),
		"hair_detail": hair_detail,
		"beard_color": _color_array(beard_color) if beard_color_set else null,
	}


## The brow style as the dictionary form writes it: its name when it is one
## of BROW_STYLES, else the blend as a number.
func brow_style_value() -> Variant:
	if is_equal_approx(brow_style, roundf(brow_style)):
		return BROW_STYLES[clampi(roundi(brow_style), 0, BROW_STYLES.size() - 1)]
	return snappedf(brow_style, 0.0001)


## A brow style from a name in BROW_STYLES or a number, clamped to 0..3.
static func brow_style_from(value: Variant, fallback: float = DEFAULT_BROW_STYLE) -> float:
	if value is String or value is StringName:
		var index := BROW_STYLES.find(str(value).to_lower())
		return float(index) if index >= 0 else fallback
	if value is float or value is int:
		return clampf(float(value), 0.0, float(BROW_STYLES.size() - 1))
	return fallback


## The control's value, 0 when it is not set.
func control(name: String) -> float:
	return float(controls.get(name, 0.0))


## Sets one control, clamped to [-1, 1]. A zero is removed rather than stored,
## so two faces that look the same compare equal.
func set_control(name: String, value: float) -> void:
	value = clampf(value, -1.0, 1.0)
	if is_zero_approx(value):
		controls.erase(name)
	else:
		controls[name] = value


## How much stubble the skin shader paints: the explicit amount, or the
## default for the `stubble` beard when no amount was given.
func stubble_amount() -> float:
	if stubble > 0.0:
		return stubble
	return DEFAULT_STUBBLE if beard == STUBBLE else 0.0


func _merge(data: Dictionary) -> void:
	if data.has("sex"):
		var wanted := str(data["sex"]).to_lower()
		sex = wanted if SEXES.has(wanted) else sex
	if data.has("label"):
		label = str(data["label"])
	if data.get("controls") is Dictionary:
		# A dictionary that names its controls names all of them: overlaying it
		# on the preset's would bring back a control the face had reset to 0.
		controls.clear()
		for name: Variant in data["controls"]:
			set_control(str(name), float((data["controls"] as Dictionary)[name]))
	skin = _color(data.get("skin"), skin)
	eyes = _color(data.get("eyes"), eyes)
	hair_color = _color(data.get("hair_color"), hair_color)
	brow_color = _color(data.get("brow_color"), brow_color)
	lip_tint = _color(data.get("lip_tint"), lip_tint)
	freckles = clampf(float(data.get("freckles", freckles)), 0.0, 1.0)
	liner = clampf(float(data.get("liner", liner)), 0.0, 1.0)
	stubble = clampf(float(data.get("stubble", stubble)), 0.0, 1.0)
	if data.has("hair"):
		hair = _style_name(data["hair"])
	if data.has("beard"):
		beard = _style_name(data["beard"])
	if data.has("brow_style"):
		brow_style = brow_style_from(data["brow_style"], brow_style)
	brow_thickness = clampf(float(data.get("brow_thickness", brow_thickness)), -1.0, 1.0)
	liner_wing = clampf(float(data.get("liner_wing", liner_wing)), 0.0, 1.0)
	hair_length = clampf(float(data.get("hair_length", hair_length)), -1.0, 1.0)
	hair_volume = clampf(float(data.get("hair_volume", hair_volume)), -1.0, 1.0)
	hair_detail = clampi(int(data.get("hair_detail", hair_detail)), 0, 2)
	if data.get("beard_color") != null and data.has("beard_color"):
		beard_color = _color(data["beard_color"], beard_color)
		beard_color_set = true


static func _style_name(value: Variant) -> String:
	var name := str(value).strip_edges()
	return NONE if name.is_empty() or name == "<null>" else name


static func _color(value: Variant, fallback: Color) -> Color:
	if value is Color:
		return value
	if value is Array and (value as Array).size() >= 3:
		var rgb: Array = value
		return Color(clampf(float(rgb[0]), 0.0, 1.0), clampf(float(rgb[1]), 0.0, 1.0),
			clampf(float(rgb[2]), 0.0, 1.0))
	if value is String and Color.html_is_valid(value):
		return Color.html(value)
	return fallback


static func _color_array(color: Color) -> Array:
	return [snappedf(color.r, 0.0001), snappedf(color.g, 0.0001), snappedf(color.b, 0.0001)]


# ---------------------------------------------------------------- byte form

## The 16-bit control-set hash in the byte form's header.
static func control_set_hash(control_names: PackedStringArray) -> int:
	var hash_value := 0x811C9DC5
	for byte: int in ",".join(control_names).to_utf8_buffer():
		hash_value = ((hash_value ^ byte) * 0x01000193) & 0xFFFFFFFF
	return (hash_value ^ (hash_value >> 16)) & 0xFFFF


## The byte form (see ENCODING_VERSION). `control_names` is the head's
## `rlHead.controls` order; controls set here but not named there are dropped.
func encode(control_names: PackedStringArray) -> PackedByteArray:
	var bytes := PackedByteArray()
	bytes.append(ENCODING_VERSION)
	bytes.append(1 if sex == "male" else 0)
	var set_hash := control_set_hash(control_names)
	bytes.append(set_hash & 0xFF)
	bytes.append((set_hash >> 8) & 0xFF)
	var count := mini(control_names.size(), 255)
	bytes.append(count)
	for index: int in range(0, count, 2):
		var low := _control_code(control(control_names[index]))
		var high := _control_code(control(control_names[index + 1])) if index + 1 < count else 0
		bytes.append(low | (high << 4))
	for color: Color in [skin, eyes, hair_color, brow_color, lip_tint]:
		var packed := _rgb565(color)
		bytes.append(packed & 0xFF)
		bytes.append((packed >> 8) & 0xFF)
	bytes.append(_amount_code(freckles) | (_amount_code(liner) << 4))
	bytes.append(_amount_code(stubble))
	bytes.append(_brow_style_code(brow_style) | (_control_code(brow_thickness) << 4))
	bytes.append(_amount_code(liner_wing))
	_append_style(bytes, hair, HAIR_STYLES)
	_append_style(bytes, beard, BEARD_STYLES)
	return bytes


## Reads the byte form back (version 2, or 1 with the default brow and no
## wing), or null when it is another version, is cut short, or was written for
## a different control set (the hash disagrees).
static func decode(bytes: PackedByteArray, control_names: PackedStringArray) -> RLHeadAppearance:
	if bytes.size() < 5 or not (bytes[0] in [1, ENCODING_VERSION]):
		return null
	var version: int = bytes[0]
	var set_hash := bytes[2] | (bytes[3] << 8)
	if set_hash != control_set_hash(control_names):
		push_warning("RL heads: appearance bytes were written for another control set")
		return null
	var result := RLHeadAppearance.new()
	result.sex = "male" if bytes[1] & 1 else "female"
	var count: int = bytes[4]
	var offset := 5
	var control_bytes := (count + 1) / 2
	if bytes.size() < offset + control_bytes + (12 if version == 1 else 14):
		return null
	for index: int in count:
		var packed: int = bytes[offset + index / 2]
		var code := (packed >> 4) & 0xF if index % 2 else packed & 0xF
		if index < control_names.size():
			result.set_control(control_names[index], _control_value(code))
	offset += control_bytes
	var colors: Array[Color] = []
	for color_index: int in 5:
		colors.append(_from_rgb565(bytes[offset] | (bytes[offset + 1] << 8)))
		offset += 2
	result.skin = colors[0]
	result.eyes = colors[1]
	result.hair_color = colors[2]
	result.brow_color = colors[3]
	result.lip_tint = colors[4]
	result.freckles = float(bytes[offset] & 0xF) / 15.0
	result.liner = float((bytes[offset] >> 4) & 0xF) / 15.0
	result.stubble = float(bytes[offset + 1] & 0xF) / 15.0
	offset += 2
	if version >= 2:
		result.brow_style = clampf(float(bytes[offset] & 0xF) / 4.0, 0.0, float(BROW_STYLES.size() - 1))
		result.brow_thickness = _control_value((bytes[offset] >> 4) & 0xF)
		result.liner_wing = float(bytes[offset + 1] & 0xF) / 15.0
		offset += 2
	var hair_read := _read_style(bytes, offset, HAIR_STYLES)
	if hair_read.is_empty():
		return null
	result.hair = hair_read[0]
	var beard_read := _read_style(bytes, int(hair_read[1]), BEARD_STYLES)
	if beard_read.is_empty():
		return null
	result.beard = beard_read[0]
	return result


static func _control_code(value: float) -> int:
	return clampi(roundi(clampf(value, -1.0, 1.0) * CONTROL_STEPS), -7, 7) + 8


static func _control_value(code: int) -> float:
	return 0.0 if code == 0 else float(code - 8) / CONTROL_STEPS


static func _brow_style_code(style: float) -> int:
	return clampi(roundi(clampf(style, 0.0, float(BROW_STYLES.size() - 1)) * 4.0), 0, 12)


static func _amount_code(amount: float) -> int:
	return clampi(roundi(clampf(amount, 0.0, 1.0) * 15.0), 0, 15)


static func _rgb565(color: Color) -> int:
	var r := clampi(roundi(clampf(color.r, 0.0, 1.0) * 31.0), 0, 31)
	var g := clampi(roundi(clampf(color.g, 0.0, 1.0) * 63.0), 0, 63)
	var b := clampi(roundi(clampf(color.b, 0.0, 1.0) * 31.0), 0, 31)
	return (r << 11) | (g << 5) | b


static func _from_rgb565(packed: int) -> Color:
	return Color(float((packed >> 11) & 31) / 31.0, float((packed >> 5) & 63) / 63.0,
		float(packed & 31) / 31.0)


static func _append_style(bytes: PackedByteArray, name: String, registry: Array[String]) -> void:
	var index := registry.find(name)
	if index >= 0 and index < INLINE_STYLE:
		bytes.append(index)
		return
	var utf8 := name.to_utf8_buffer()
	utf8.resize(mini(utf8.size(), 255))
	bytes.append(INLINE_STYLE)
	bytes.append(utf8.size())
	bytes.append_array(utf8)


## [name, offset after it], or [] when the bytes run out.
static func _read_style(bytes: PackedByteArray, offset: int, registry: Array[String]) -> Array:
	if offset >= bytes.size():
		return []
	var code: int = bytes[offset]
	if code != INLINE_STYLE:
		return [registry[code] if code < registry.size() else NONE, offset + 1]
	if offset + 1 >= bytes.size():
		return []
	var length: int = bytes[offset + 1]
	if offset + 2 + length > bytes.size():
		return []
	return [bytes.slice(offset + 2, offset + 2 + length).get_string_from_utf8(), offset + 2 + length]

class_name HairFinish
extends RefCounted
## The hair finish slider (colour model spec revision 3, 2.9 and 4.7): PC/3
## `hair_finish` 0 means "the PC/1 `hair_detail` enum, as today"; 1..101 is the
## slider s = value - 1 from 0 (sleekest) to 100 (messiest). Develop's three
## finishes sit at exact, frozen positions - Swept 25, Classic 50, Tousled 75 -
## and a value on one of them is saved as that enum with hair_finish 0, so old
## and new picks of the same finish are byte-identical. Older recipients and
## PC/2 servers get the nearest enum in `hair_detail` (written by the client);
## a custom slider value whose nearest enum disagrees with the saved
## `hair_detail` (an old client changed the finish) falls back to the enum.
## Pure; nothing here touches a node.

## hair_detail 0 Classic, 1 Tousled, 2 Swept -> slider position.
const ENUM_SLIDER: Array[int] = [50, 75, 25]
## Extrapolation gain at the ends (owner decision Q-N10: 1.6 at s = 0 and 100,
## 1 between Swept and Tousled), so the ends are sleeker than Swept and messier
## than Tousled on the game's own hairstyles.
const E_MAX := 1.6
const MAXIMUM := 101


## The slider position of a saved finish (hair_detail 0..2).
static func enum_slider(detail: int) -> int:
	return ENUM_SLIDER[clampi(detail, 0, 2)]


## The nearest saved finish to slider position s: 0-37 Swept (2), 38-62
## Classic (0), 63-100 Tousled (1). No ties.
static func nearest_enum(s: int) -> int:
	if s <= 37:
		return 2
	if s <= 62:
		return 0
	return 1


## The saved form of slider position s (0..100): {"hair_detail", "hair_finish"}.
## A position on a saved finish is that enum with hair_finish 0; any other is
## the nearest enum and s + 1.
static func canonical(s: int) -> Dictionary:
	s = clampi(s, 0, 100)
	for detail: int in 3:
		if ENUM_SLIDER[detail] == s:
			return {"hair_detail": detail, "hair_finish": 0}
	return {"hair_detail": nearest_enum(s), "hair_finish": s + 1}


static func _field(appearance: Dictionary, name: String, maximum: int) -> int:
	var value: Variant = appearance.get(name, 0)
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(value)) \
			or floor(float(value)) != float(value):
		return 0
	return clampi(int(value), 0, maximum)


## The finish to draw: {"enum": hair_detail 0..2, "s": slider 0..100,
## "custom": bool}. custom is false - develop's path, the enum's own code -
## when hair_finish is 0 (Auto), typed on the enum's own position (Rule C),
## or guarded (its nearest enum is not the saved hair_detail).
static func resolve(appearance: Dictionary) -> Dictionary:
	var detail := _field(appearance, "hair_detail", 2)
	var wire := _field(appearance, "hair_finish", MAXIMUM)
	var result := {"enum": detail, "s": enum_slider(detail), "custom": false}
	if wire <= 0:
		return result
	var s := wire - 1
	if s == enum_slider(detail) or nearest_enum(s) != detail:
		return result
	result["s"] = s
	result["custom"] = true
	return result


## The extrapolation gain e(s): 1 for 25 <= s <= 75, rising linearly to E_MAX
## at s = 0 and at s = 100.
static func gain(s: float) -> float:
	if s < 25.0:
		return 1.0 + (E_MAX - 1.0) * (25.0 - s) / 25.0
	if s > 75.0:
		return 1.0 + (E_MAX - 1.0) * (s - 75.0) / 25.0
	return 1.0


## The finish weights at slider position s: x = w_swept, y = w_tousled, each
## 0 at Classic (50), 1 at its own finish (25 / 75), up to E_MAX at the ends.
static func weights(s: float) -> Vector2:
	var e := gain(s)
	return Vector2(clampf((50.0 - s) / 25.0, 0.0, 1.0) * e, clampf((s - 50.0) / 25.0, 0.0, 1.0) * e)


## The shared finish weight w = min(1, w_swept + w_tousled) that drives the
## custom material (roughness, specular, grain) and the discrete elements.
static func material_weight(s: float) -> float:
	var w := weights(s)
	return minf(1.0, w.x + w.y)

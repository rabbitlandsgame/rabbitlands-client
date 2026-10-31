class_name CharacterAge
extends RefCounted
## Cosmetic amounts only: no chronological age, identity or gameplay changes.
## eye_color's unused alpha carries two exact seven-bit amounts. Alpha 1 is
## the legacy value and stays unchanged when both options are off.
const GREY := Color(0.76, 0.77, 0.75)

static func amount(look: Dictionary, field: String) -> float:
	if look.get("rl_head") is Dictionary and (look.rl_head as Dictionary).has(field):
		# Offline head/fit labs carry normalized amounts in this explicit override.
		var authored: Variant = (look.rl_head as Dictionary).get(field, 0.0)
		return clampf(float(authored), 0.0, 1.0) if typeof(authored) in [TYPE_INT, TYPE_FLOAT] \
			and is_finite(float(authored)) else 0.0
	var value: Variant = look.get(field, 0)
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(value)) \
			or floor(float(value)) != float(value):
		return 0.0
	return float(clampi(int(value), 0, 100)) / 100.0

static func packed(skin_age: float, hair_grey: float) -> float:
	var age := roundi(clampf(skin_age, 0.0, 1.0) * 100.0) if is_finite(skin_age) else 0
	var grey := roundi(clampf(hair_grey, 0.0, 1.0) * 100.0) if is_finite(hair_grey) else 0
	return 1.0 if age == 0 and grey == 0 else float(2 + age + 128 * grey)

static func unpacked(carrier: float) -> Vector2:
	if not is_finite(carrier) or carrier < 1.5:
		return Vector2.ZERO
	var value := maxi(0, roundi(carrier - 2.0))
	return Vector2(clampi(value & 127, 0, 100), clampi(value >> 7, 0, 100)) / 100.0

## Classic hair has no strand chart. Blend its dye while keeping its authored
## texture and the saved base colour. High RL modules add strand variation.
static func grey_colour(colour: Color, amount_value: float) -> Color:
	if not is_finite(amount_value) or amount_value <= 0.0:
		return colour
	var result := colour.lerp(GREY, clampf(amount_value, 0.0, 1.0))
	result.a = colour.a
	return result

extends RefCounted
## The skin's painted scalp is an underlay for most hairstyles. Short coils
## already carry their fitted scalp: the broader skin mask would otherwise
## paint a flat strip of hair colour below their nape.
const SELF_COVERED_STYLES := ["short_coils_male"]


static func amount(resolved_style: String, haired: bool, under_hair: float) -> float:
	if not haired or resolved_style in SELF_COVERED_STYLES:
		return 0.0
	return under_hair

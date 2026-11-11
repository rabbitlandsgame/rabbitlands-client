extends RefCounted

static func color(tier: String) -> Color:
	return Color("83b4ff") if tier == "magic" else Color("ffd75c") if tier == "rare" else Color("e4ded1")

static func display_name(item_name: String, _tier: String) -> String:
	return item_name

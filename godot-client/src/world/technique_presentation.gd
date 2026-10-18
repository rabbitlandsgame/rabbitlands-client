extends RefCounted
## Cosmetic vocabulary shared by the live world and the book's isolated demo.
## Contact seconds are visual timing, never hit tests or gameplay delays.
const PROFILES := {
	"heavy_blow": ["dcb77c", "Technique_Heavy", "attack_primary", 0.34],
	"measured_strike": ["d7edf1", "Technique_Precise", "attack_primary", 0.26],
	"fighting_retreat": ["9bb9ce", "", "", 0.0],
	"charge": ["e4c28a", "Technique_Heavy", "attack_primary", 0.28],
	"challenge": ["dd996e", "Technique_Challenge", "defend", 0.0],
	"second_wind": ["88c8b3", "Technique_Breath", "defend", 0.0],
	"war_cry": ["e6c780", "Technique_Rally", "defend", 0.0],
	"executioners_stroke": ["db8b75", "Technique_Heavy", "attack_primary", 0.34],
	"shield_bash": ["e2c47e", "Technique_Shield_Bash", "attack_primary", 0.30],
	"brace": ["a1bfd5", "Technique_Brace", "defend", 0.0],
	"intercept": ["8bcbbd", "Technique_Brace", "defend", 0.0],
	"cleave": ["d7d5b3", "Technique_Cleave", "attack_secondary", 0.30],
	"sunder": ["d9a477", "Technique_Heavy", "attack_primary", 0.34],
	"flurry": ["d1e6e8", "Technique_Flurry", "attack_primary", 0.19],
	"hamstring": ["c9988c", "Technique_Low_Cut", "attack_secondary", 0.26],
	"riposte": ["c5ddea", "Technique_Brace", "defend", 0.0],
	"backstab": ["c98783", "Technique_Precise", "attack_primary", 0.26],
	"lunge": ["d5e4dc", "Technique_Thrust", "attack_primary", 0.25],
	"keep_at_bay": ["b8c9d0", "Technique_Thrust", "attack_primary", 0.25],
	"aimed_shot": ["e5c882", "Combat_Bow_Release", "ranged_attack", 0.0],
	"pinning_shot": ["a8c4c8", "Combat_Bow_Release", "ranged_attack", 0.0],
	"volley": ["d3c493", "Combat_Bow_Release", "ranged_attack", 0.0],
	"step_back": ["adbfc9", "", "", 0.0],
	"mark_target": ["dfad85", "Combat_Bow_Release", "ranged_attack", 0.0],
}
const RANGED := ["aimed_shot", "pinning_shot", "volley", "mark_target"]
const SUPPORT := ["fighting_retreat", "challenge", "second_wind", "war_cry", "brace", "intercept", "riposte", "step_back"]

static func color_for(key: String) -> Color:
	return Color(PROFILES[key][0]) if PROFILES.has(key) else Color.WHITE

static func motion_for(key: String, phase: String) -> Array:
	if not PROFILES.has(key) or phase in ["impact", "pulse"]: return []
	if key == "charge" and phase == "activate": return []
	if key == "riposte" and phase == "counter": return ["Technique_Riposte", "attack_primary"]
	var profile: Array = PROFILES[key]
	return [profile[1], profile[2]] if not str(profile[1]).is_empty() else []

static func contact_delay(key: String, phase: String, distance: float) -> float:
	if key in RANGED: return clampf(distance / 28.0, 0.12, 0.65)
	if phase in ["impact", "activate", "pulse"]: return 0.0
	if phase == "counter": return 0.27
	return float(PROFILES[key][3]) if PROFILES.has(key) else 0.0

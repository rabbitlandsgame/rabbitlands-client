extends "res://src/app/main.gd"
## Count the production view refreshes while retaining their real behavior.
var refresh_counts := {"stats": 0, "spells": 0, "crafting": 0}
var rendered_health := -1

func _sync_stats() -> void:
	refresh_counts.stats += 1
	rendered_health = int(AppState.stats.get("health", -1))
	super._sync_stats()

func _sync_spells() -> void:
	refresh_counts.spells += 1
	super._sync_spells()

func _sync_manufacturing() -> void:
	refresh_counts.crafting += 1
	super._sync_manufacturing()

func reset_refresh_counts() -> void:
	refresh_counts = {"stats": 0, "spells": 0, "crafting": 0}

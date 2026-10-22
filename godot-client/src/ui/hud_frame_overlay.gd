extends Node2D
## Draw rectangular HUD frames once in the game canvas, at a uniform width.
const Chrome := preload("res://src/ui/hud_panel_chrome.gd")
var panels: Array[Dictionary] = []

func _draw() -> void:
	for panel: Dictionary in panels:
		Chrome.draw_rect_border(self, panel.rect, panel.neighbours, panel.config)

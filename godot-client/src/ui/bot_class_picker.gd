extends MenuButton
## One shared class picker for the party and gauntlet prepare windows.

signal class_chosen(class_id: int)

const CLASSES := ["Vanguard · Tank", "Ranger · Ranged damage", "Arcanist · Spell damage", "Warden · Healer"]

func _ready() -> void:
	text = "Add bot"
	tooltip_text = "Choose a bot's class. Bots count toward difficulty and receive no loot share."
	for class_id: int in range(CLASSES.size()):
		get_popup().add_item(CLASSES[class_id], class_id)
	get_popup().id_pressed.connect(func(class_id: int) -> void: class_chosen.emit(class_id))

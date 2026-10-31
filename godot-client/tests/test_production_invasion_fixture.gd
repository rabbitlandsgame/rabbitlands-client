extends SceneTree
## Pure fixture data: no world, actors, imports, rendering or server connection.
const Benchmark := preload("res://tests/integration/crowd_presentation_benchmark.gd")
var checks := 0
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("production invasion fixture: " + message)

func _run() -> void:
	_check(Benchmark.cells_for("phase4").size() == 12, "historical phase4 membership retained")
	_check(Benchmark.cells_for("production-undead").size() == 3, "three explicit production populations")
	var largest: Dictionary = Benchmark.production_undead_records(500, Vector2i(453, 168), "twinbrook")
	for remote: int in [160, 300, 500]:
		var records: Dictionary = Benchmark.production_undead_records(remote, Vector2i(453, 168), "twinbrook")
		_check(records.size() == remote + 1, "remote creatures plus one observer: %d" % remote)
		var occupied := {}
		var counts := {}
		for id: int in records:
			var record: Dictionary = records[id]
			_check(record == largest[id], "smaller fixture is a stable prefix")
			var size: Vector2i = record.get("footprint", Vector2i.ONE)
			for y: int in size.y:
				for x: int in size.x:
					var tile := Vector2i(record.x + x, record.y + y)
					_check(not occupied.has(tile), "creature footprints do not overlap")
					occupied[tile] = true
			if int(record.kind) == 5:
				_check(record.actor_type in [746, 745, 671] and record.scale == 1.0, "retained pure-creature DTO")
				_check(size == (Vector2i(2, 2) if record.actor_type == 671 else Vector2i.ONE), "server footprint retained")
				counts[record.name] = int(counts.get(record.name, 0)) + 1
		_check(counts.size() == 3, "all three species supplied")
		var active: Array[int] = Benchmark.production_undead_active_ids(records)
		var species: Dictionary = Benchmark.production_undead_activity_species(records, active)
		_check(active.size() == (remote + 2) / 3 and species.size() == 3, "activity includes all species")
		if remote == 300:
			_check(species == {"zombie": 34, "skeleton": 33, "drowned_lich_king": 33}, "300-creature activity balanced")
	var gauntlet: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(Benchmark.GAUNTLET_FIXTURE))
	var authored: Dictionary = Benchmark.authored_gauntlet_records(gauntlet)
	_check(authored.size() == 22, "authored pulse is 21 creatures plus observer")
	_check(Benchmark.cells_for(Benchmark.GAUNTLET_CELL).size() == 1, "authored selector explicit")
	for row: Dictionary in gauntlet.actors:
		var record: Dictionary = authored[int(row.actorId)]
		_check(Vector2i(record.x, record.y) == Vector2i(row.tile[0], row.tile[1]), "exact authored spawn tile retained")
		_check(record.scale == 1.0 and record.footprint == Vector2i.ONE, "DTO scale not model import scale")
	print("production invasion fixture: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

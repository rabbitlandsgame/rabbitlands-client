extends SceneTree
const Placement := preload("res://src/ui/quest_tracker_placement.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures += 1; push_error(message)

func avoids(rect: Rect2, obstacles: Array[Rect2], gap := 8.0) -> bool:
	for obstacle: Rect2 in obstacles:
		if obstacle.has_area() and rect.intersects(obstacle.grow(gap)): return false
	return true

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var view := Rect2(0,0,1280,720)
	var preferred := Rect2(900,100,300,110)
	var minimap: Array[Rect2] = [Rect2(1010,500,250,200)]
	expect(Placement.place(preferred,view,minimap) == preferred,"a clear preferred position remains unchanged")
	expect(Placement.place(Rect2(-40,800,300,110),view,[]) == Rect2(0,610,300,110),
		"offscreen positions clamp inside the viewport without resizing")
	expect(Placement.place(Rect2(0,0,300,100),Rect2(50,20,800,600),[]) == Rect2(50,20,300,100),
		"clamping respects a viewport with a nonzero origin")
	preferred = Rect2(980,420,280,120); minimap = [Rect2(1000,400,260,260)]
	var placed := Placement.place(preferred,view,minimap)
	expect(placed == Rect2(980,272,280,120) and avoids(placed,minimap),
		"the nearest clear position is above a bottom-right minimap")
	var moved_map: Array[Rect2] = [Rect2(350,180,280,240)]
	placed = Placement.place(Rect2(400,220,240,100),Rect2(0,0,1000,700),moved_map)
	expect(placed == Rect2(400,72,240,100),"a user-moved minimap is avoided at its actual location")
	var tall: Array[Rect2] = [Rect2(700,50,300,500)]
	placed = Placement.place(Rect2(680,100,240,100),Rect2(0,0,1000,700),tall)
	expect(placed == Rect2(452,100,240,100) and avoids(placed,tall),
		"left wins when it is closer than a feasible move below")
	var left_wall: Array[Rect2] = [Rect2(0,0,200,600)]
	expect(Placement.place(Rect2(100,200,200,100),Rect2(0,0,1000,700),left_wall) == Rect2(208,200,200,100),
		"right is used when the left and upper alternatives cannot fit")
	var top_wall: Array[Rect2] = [Rect2(0,0,1000,100)]
	expect(Placement.place(Rect2(400,50,240,100),Rect2(0,0,1000,700),top_wall) == Rect2(400,108,240,100),
		"a full-width upper obstacle can be avoided below")
	var intersecting: Array[Rect2] = [Rect2(240,240,120,120),Rect2(350,0,50,600),Rect2(80,250,140,100)]
	var saved := intersecting.duplicate()
	preferred = Rect2(250,250,100,100)
	placed = Placement.place(preferred,Rect2(0,0,600,600),intersecting)
	expect(placed == Rect2(242,132,100,100) and avoids(placed,intersecting),
		"edge combinations find a nearby diagonal gap when direct alternatives collide")
	expect(intersecting == saved and preferred == Rect2(250,250,100,100),
		"placement changes neither obstacle coordinates nor the caller's saved preference")
	expect(Placement.place(preferred,Rect2(0,0,600,600),intersecting) == placed,
		"identical inputs produce a deterministic placement")
	var no_space: Array[Rect2] = [Rect2(0,0,200,200)]
	preferred = Rect2(-20,180,100,100)
	placed = Placement.place(preferred,Rect2(0,0,200,200),no_space)
	expect(placed == Rect2(0,100,100,100),"no-space fallback keeps the preferred clamped position even when overlapped")
	expect(placed.size == preferred.size and preferred.position == Vector2(-20,180),
		"no-space fallback never shrinks the card or edits saved coordinates")
	var exact_gap: Array[Rect2] = [Rect2(208,100,100,50)]
	preferred = Rect2(100,100,100,50)
	expect(Placement.place(preferred,view,exact_gap,8.0) == preferred,"touching the specified gap is already clear")
	expect(Placement.place(preferred,view,exact_gap,9.0) == Rect2(99,100,100,50),
		"a larger requested gap produces the nearest necessary move")
	var empty_markers: Array[Rect2] = [Rect2(120,120,0,0),Rect2(5000,5000,200,200)]
	expect(Placement.place(preferred,view,empty_markers) == preferred,"empty and fully offscreen obstacles create no phantom exclusions")
	for dimensions: Vector2 in [Vector2(900,460),Vector2(1280,720),Vector2(1920,1080)]:
		for size: Vector2 in [Vector2(300,103),Vector2(340,44),Vector2(320,280)]:
			var viewport := Rect2(Vector2.ZERO,dimensions)
			var obstacle := Rect2(dimensions-Vector2(265,265),Vector2(245,245))
			var obstacles: Array[Rect2] = [obstacle]
			var requested := Rect2(dimensions-size-Vector2(18,18),size)
			var result := Placement.place(requested,viewport,obstacles)
			expect(viewport.encloses(result) and result.size == size,"each supported card size stays bounded without resizing")
			expect(avoids(result,obstacles),"each supported viewport has a clear placement around its minimap")
	print("Quest tracker placement: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)

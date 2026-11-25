extends PanelContainer
## Reuses the existing Oldcraft artwork; decoration owns no input or layout.
const PARCHMENT := preload("res://assets/ui/oldcraft_inspired/eloria_parchment.png")
const CARVED_FRAME := preload("res://assets/ui/oldcraft_inspired/eloria_carved_frame.png")

var paper := false:
	set(value):
		paper = value
		if is_node_ready():
			_apply_surface()
			queue_redraw()

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	_apply_surface()
	resized.connect(queue_redraw)

func _apply_surface() -> void:
	if paper:
		var style := StyleBoxTexture.new()
		style.texture = PARCHMENT
		style.region_rect = Rect2(64,64,1126,1126)
		style.texture_margin_left = 24; style.texture_margin_right = 24
		style.texture_margin_top = 24; style.texture_margin_bottom = 24
		style.modulate_color = Color(1.0,0.985,0.96)
		style.content_margin_left = 20; style.content_margin_right = 20
		style.content_margin_top = 28; style.content_margin_bottom = 18
		add_theme_stylebox_override("panel",style)
	else:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("30231a")
		style.border_color = Color("6e5031")
		style.set_border_width_all(2); style.set_corner_radius_all(3)
		style.set_content_margin_all(18)
		style.shadow_color = Color(0.035,0.025,0.018,0.55)
		style.shadow_size = 6; style.shadow_offset = Vector2(0,3)
		add_theme_stylebox_override("panel",style)

func _draw() -> void:
	if size.x < 2 or size.y < 2: return
	var bounds := Rect2(Vector2.ZERO,size)
	if paper:
		var edge := StyleBoxFlat.new()
		edge.bg_color = Color.TRANSPARENT
		edge.border_color = Color(0.49,0.34,0.16,0.52)
		edge.set_border_width_all(1)
		draw_style_box(edge,bounds)
		# A light wash calms the reused grain behind the offer's dark ink.
		draw_rect(bounds.grow(-1),Color(1.0,0.99,0.95,0.10))
		_pin(Vector2(15,14),4.5)
		_pin(Vector2(size.x-15,14),4.5)
	else:
		if size.x > 10 and size.y > 10:
			draw_texture_rect(PARCHMENT,bounds.grow(-5),false,Color(0.27,0.19,0.12,0.42))
		_draw_frame()
		for point: Vector2 in [Vector2(10,10),Vector2(size.x-10,10),
				Vector2(10,size.y-10),Vector2(size.x-10,size.y-10)]:
			_pin(point,4.0)

func _draw_frame() -> void:
	# Crop away the art's transparent surround. Fixed narrow edge slices keep
	# the carved surround modest on both short rows and tall noticeboards.
	var edge := minf(16.0,minf(size.x,size.y)*0.25)
	var source_x := PackedFloat32Array([42,152,1107,1217])
	var source_y := PackedFloat32Array([82,192,1069,1179])
	var target_x := PackedFloat32Array([0,edge,size.x-edge,size.x])
	var target_y := PackedFloat32Array([0,edge,size.y-edge,size.y])
	for row: int in 3:
		for column: int in 3:
			if row == 1 and column == 1: continue
			var target := Rect2(target_x[column],target_y[row],
				target_x[column+1]-target_x[column],target_y[row+1]-target_y[row])
			var source := Rect2(source_x[column],source_y[row],
				source_x[column+1]-source_x[column],source_y[row+1]-source_y[row])
			draw_texture_rect_region(CARVED_FRAME,target,source)

func _pin(point: Vector2, radius: float) -> void:
	draw_circle(point+Vector2(0.7,1.4),radius+0.8,Color(0.06,0.035,0.01,0.40))
	draw_circle(point,radius,Color("67441f"))
	draw_circle(point+Vector2(-0.4,-0.5),radius-0.9,Color("ac8244"))
	draw_circle(point+Vector2(-1.0,-1.2),maxf(0.8,radius*0.29),Color("e0c07c"))
	draw_arc(point,radius-0.35,0.25,2.6,10,Color(0.28,0.17,0.07,0.75),0.8,true)

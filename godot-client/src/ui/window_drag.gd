class_name WindowDrag
extends Node
## Moves one window by its title bar, the way Eternal Lands moves every one of
## its windows.
##
## Only the inventory, the ground bag and the minimap could be moved here, and
## each carried its own copy of the same handler. This is that behaviour as a
## single node: it is added as a child of the window it moves, so a window that
## is freed takes its dragging with it, and a window that has never been shown
## costs nothing.
##
## The window is kept inside the viewport and off the fixed resource rail. A
## window dragged until its title bar left the screen could not be dragged
## back, so the clamp is what keeps a moved window recoverable rather than a
## tidiness rule.

## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0
const RESERVED_BOTTOM_BAR := 40.0
const EDGE_MARGIN := 6.0

## Emitted when a drag ends, for a caller that remembers where its window was.
signal moved(to: Vector2)

var window: Control
## Optional fixed bottom surface, for HUDs taller than the default reserve.
var bottom_hud: Control

var _dragging := false
var _grab_offset := Vector2.ZERO

func _ready() -> void:
	window.visibility_changed.connect(_clamp_when_visible)
	window.resized.connect(_clamp_when_visible)
	window.get_viewport().size_changed.connect(_clamp_when_visible)

func _clamp_when_visible() -> void:
	if is_instance_valid(window) and window.is_visible_in_tree():
		clamp_into_view.call_deferred()

## Makes `target` draggable by `handle`. The handle is usually the window's
## header row; where a window has no header it is the title label, which is the
## same thing the player aims at.
static func attach(target: Control, handle: Control) -> WindowDrag:
	if target == null or handle == null:
		return null
	var dragger := WindowDrag.new()
	dragger.name = "WindowDrag"
	dragger.window = target
	target.add_child(dragger)
	# A header that ignores the mouse cannot be grabbed, and a label inside it
	# that stops the mouse would swallow the grab before the header sees it.
	handle.mouse_filter = Control.MOUSE_FILTER_STOP
	for child: Node in handle.get_children():
		if child is Label:
			(child as Label).mouse_filter = Control.MOUSE_FILTER_IGNORE
	handle.mouse_default_cursor_shape = Control.CURSOR_MOVE
	handle.gui_input.connect(dragger._on_handle_input.bind(handle))
	return dragger

func _on_handle_input(event: InputEvent, handle: Control) -> void:
	if not is_instance_valid(window):
		return
	if event is InputEventMouseButton:
		var click: InputEventMouseButton = event as InputEventMouseButton
		if click.button_index != MOUSE_BUTTON_LEFT:
			return
		_dragging = click.pressed
		if click.pressed:
			window.move_to_front()
			_grab_offset = click.global_position - window.global_position
		else:
			moved.emit(window.position)
		handle.accept_event()
	elif event is InputEventMouseMotion and _dragging:
		window.global_position = (event as InputEventMouseMotion).global_position - _grab_offset
		clamp_into_view()
		handle.accept_event()

## Keeps the window on screen and clear of the rail. `maxf` rather than a plain
## clamp because a window larger than the space left is pinned to the near edge
## instead of being pushed off the far one.
func clamp_into_view() -> void:
	if not is_instance_valid(window):
		return
	var bounds: Vector2 = window.get_viewport_rect().size
	var size: Vector2 = window.size * window.scale
	var bottom: float = bounds.y - RESERVED_BOTTOM_BAR
	if is_instance_valid(bottom_hud):
		bottom = minf(bottom, bottom_hud.global_position.y)
	var limit := Vector2(
		maxf(EDGE_MARGIN, bounds.x - RESERVED_RIGHT_RAIL - size.x),
		maxf(EDGE_MARGIN, bottom - size.y - EDGE_MARGIN))
	window.global_position = Vector2(
		clampf(window.global_position.x, EDGE_MARGIN, limit.x),
		clampf(window.global_position.y, EDGE_MARGIN, limit.y))

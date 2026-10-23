class_name WindowStack
extends Node
## Godot picks Controls in scene order, independently of their drawing z_index.
## Keep gameplay windows as siblings and derive their drawing order from that
## same list so the surface the player sees also owns the pointer.

const STACK_META := &"rabbitlands_window_stack"
const WINDOW_Z := 20
const MODAL_Z := 300

var surface: Control
var _windows: Array[Control] = []
var _modals: Array[Control] = []
var _full_window_views: Array[Control] = []
var _world_surface: Control
var _decorations: Dictionary = {}
var _overlays: Dictionary = {}
var _visibility: Dictionary = {}
var _updating := false
var _modal_update_pending := false

func configure(parent_surface: Control) -> void:
	surface = parent_surface
	surface.child_order_changed.connect(_sync_layers)

func register(window: Control, modal := false) -> void:
	if window == null or window in _windows:
		return
	if window.get_parent() != surface:
		window.reparent(surface)
	_windows.append(window)
	if modal:
		_modals.append(window)
	window.set_meta(STACK_META, self)
	window.mouse_filter = Control.MOUSE_FILTER_STOP
	_visibility[window] = window.visible
	window.visibility_changed.connect(_on_visibility_changed.bind(window))
	window.tree_entered.connect(func(): _sync_layers.call_deferred())
	if window not in _full_window_views:
		window.move_to_front()
	_sync_layers()

## Background views cover the world without covering the player's HUD.
## Keep their GUI order below the HUD too; z_index alone cannot route clicks.
func register_full_window_view(window: Control, world_surface: Control) -> void:
	if window == null or window in _full_window_views:
		return
	_world_surface = world_surface
	_full_window_views.append(window)
	register(window)

func decorate(window: Control, decorations: Array) -> void:
	_decorations[window] = decorations
	_sync_layers()

## Top-level editors keep screen coordinates, but belong to their window's
## drawing group rather than a fixed z_index above every other window.
func attach_overlay(window: Control, overlay: Control) -> void:
	_overlays[overlay] = window
	_sync_layers()

## Also works for standalone windows used by previews and tools. A docked
## inventory activates its containing storage window without moving its layout.
static func activate(window: Control) -> void:
	var stack := window.get_meta(STACK_META, null) as WindowStack
	if stack == null:
		window.move_to_front()
		return
	var target := window
	var ancestor := window.get_parent()
	while ancestor != null and ancestor != stack.surface:
		if ancestor is Control and ancestor in stack._windows:
			target = ancestor as Control
		ancestor = ancestor.get_parent()
	if target in stack._full_window_views:
		stack._raise_modals()
		return
	target.move_to_front()
	stack._sync_layers()
	stack._raise_modals()
	var focus := window.get_viewport().gui_get_focus_owner()
	if focus != null and focus != target and not target.is_ancestor_of(focus):
		focus.release_focus()

func _on_visibility_changed(window: Control) -> void:
	var was_visible: bool = _visibility.get(window, false)
	_visibility[window] = window.visible
	# Showing the whole game view also emits this signal for its children,
	# while their parent is busy propagating visibility and cannot reorder them.
	if window.visible and not was_visible:
		activate(window)

## Run before Godot's GUI dispatch. Clicking any exposed part of a window,
## including a button or scroll area, activates it without replaying the click.
func handle_pointer(event: InputEvent) -> void:
	if not event is InputEventMouseButton or not event.pressed:
		return
	_raise_modals()
	_sync_layers()
	var children := surface.get_children()
	children.reverse()
	for child: Node in children:
		if child is Control and child in _windows and child not in _full_window_views \
				and (child as Control).is_visible_in_tree() \
				and (child as Control).get_global_rect().has_point(event.position):
			activate(child as Control)
			return

func _sync_layers() -> void:
	if _updating or not is_instance_valid(surface) or not surface.is_inside_tree() \
			or surface.is_queued_for_deletion():
		return
	_updating = true
	var rank := 0
	for child: Node in surface.get_children():
		if not child is Control or not child in _windows:
			continue
		var window := child as Control
		window.z_as_relative = false
		if window in _full_window_views:
			window.z_index = 0
			continue
		window.z_index = (MODAL_Z if window in _modals else WINDOW_Z) + rank * 4
		for index: int in (_decorations.get(window, []) as Array).size():
			var raw_decoration: Variant = _decorations[window][index]
			if not is_instance_valid(raw_decoration):
				continue
			var decoration := raw_decoration as Control
			decoration.z_as_relative = false
			decoration.z_index = window.z_index - 2 + index
		rank += 1
	for window: Control in _windows:
		if is_instance_valid(window) and window.get_parent() != surface:
			# Storage can temporarily dock the inventory inside its own panel.
			window.z_as_relative = true
			window.z_index = 0
	for raw_overlay: Variant in _overlays:
		if not is_instance_valid(raw_overlay) or not is_instance_valid(_overlays[raw_overlay]):
			continue
		var overlay := raw_overlay as Control
		var host: Control = _overlays[overlay]
		var ancestor := host.get_parent()
		while ancestor != null and ancestor != surface:
			if ancestor is Control and ancestor in _windows:
				host = ancestor as Control
			ancestor = ancestor.get_parent()
		overlay.z_as_relative = false
		overlay.z_index = host.z_index + 1
	_updating = false
	# child_order_changed is emitted while the parent is still moving a child;
	# it can update drawing properties here, but must defer further reordering.
	if not _modal_update_pending:
		_modal_update_pending = true
		_raise_modals.call_deferred()

func _raise_modals() -> void:
	if not is_instance_valid(surface) or not surface.is_inside_tree() \
			or surface.is_queued_for_deletion():
		return
	_modal_update_pending = true
	if is_instance_valid(_world_surface) and _world_surface.get_parent() == surface:
		var next_index := _world_surface.get_index() + 1
		for view: Control in _full_window_views:
			if is_instance_valid(view) and view.get_parent() == surface:
				if view.get_index() != next_index:
					surface.move_child(view, next_index)
				next_index += 1
	for modal: Control in _modals:
		if is_instance_valid(modal) and modal.is_visible_in_tree():
			modal.move_to_front()
	_modal_update_pending = false

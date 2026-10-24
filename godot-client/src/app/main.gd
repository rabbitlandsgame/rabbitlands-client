extends Control

const Diagnostics = preload("res://src/diagnostics/client_diagnostics.gd")
const ClientRuntime = preload("res://src/runtime/client_runtime.gd")
const RustRiderPose = preload("res://src/mounts/rust_rider_pose.gd")
var client_runtime := ClientRuntime.new()
const ExperienceCurve = preload("res://src/state/experience_curve.gd")
const SeasonSky = preload("res://src/world/season_sky.gd")
const SeasonSurfaces = preload("res://src/world/season_surfaces.gd")
const SurfaceRefreshQueue = preload("res://src/world/chunk_surface_refresh.gd")
const ExternalMeshPool = preload("res://src/world/external_mesh_pool.gd")
const ExternalTexturePool = preload("res://src/world/external_texture_pool.gd")
const LanternGuideScript = preload("res://src/ui/lantern_guide.gd")
const WindowStackScript = preload("res://src/ui/window_stack.gd")
const LanternSceneScript = preload("res://src/world/lantern_scene.gd")
const BellSceneScript = preload("res://src/world/bell_scene.gd")
const RoadSceneScript = preload("res://src/world/road_scene.gd")
const SkySceneScript = preload("res://src/world/sky_scene.gd")
const CartographyOwnershipGeometry = preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
var lantern_guide: Control
var window_stack: Node
var lantern_scene: Node3D

const AppearanceChoices = preload("res://src/actors/appearance_choices.gd")
const OldcraftEntryStyleScript = preload("res://src/ui/oldcraft_entry_style.gd")
const OldcraftDialogueStyleScript = preload("res://src/ui/oldcraft_dialogue_style.gd")
const CreationArchetypes = preload("res://src/ui/creation_archetypes.gd")
const CreationClassIcons = preload("res://src/ui/creation_class_icons.gd")
const WardrobeShirtFitScript = preload("res://src/actors/wardrobe_shirt_fit.gd")
const NewCharacterIntroScript = preload("res://src/camera/new_character_intro.gd")
## Delay Node allocation until entry: inherited scenes may replace the script
## after construction, before these helpers have a parent to own them.
@onready var character_intro := NewCharacterIntroScript.new()
const ArrivalCurtainScript = preload("res://src/ui/arrival_curtain.gd")
const ArrivalPrewarmScript = preload("res://src/world/arrival_prewarm.gd")
## The loading screen from signing in, or a far arrival, until the character
## stands on loaded ground (_update_arrival).
@onready var arrival_curtain := ArrivalCurtainScript.new()
## The respawn destination's ground on another map, loaded while dead.
var respawn_prewarm := ArrivalPrewarmScript.new()
## The beam's ground, loaded quietly while completed gauntlet loot is split.
var gauntlet_prewarm := ArrivalPrewarmScript.new()
@onready var quest_trail := preload("res://src/world/quest_trail_3d.gd").new()

@onready var login_panel: Control = %LoginPanel
@onready var game_view: Control = %GameView
@onready var creation_panel: Control = %CreationPanel
@onready var new_character_button: Button = %NewCharacter
@onready var create_name: LineEdit = %CreateName
@onready var create_password: LineEdit = %CreatePassword
@onready var create_confirm: LineEdit = %CreateConfirm
@onready var create_race: OptionButton = %CreateRace
@onready var create_gender: OptionButton = %CreateGender
@onready var create_status: Label = %CreateStatus
@onready var creation_class_title: Label = %ClassTitle
@onready var creation_class_tagline: Label = %ClassTagline
@onready var creation_class_description: Label = %ClassDescription
@onready var creation_class_page: Label = %ClassPage
@onready var creation_class_starting_items: Label = %ClassStartingItems
@onready var show_creation_class_gear: CheckBox = %ShowClassGear
@onready var preview_container: SubViewportContainer = %CharacterPreview
@onready var preview_viewport: SubViewport = $CreationPanel/Columns/CharacterPreview/Viewport
@onready var preview_root: Node3D = %PreviewRoot
@onready var preview_camera: Camera3D = %PreviewCamera
@onready var preview_key_light: DirectionalLight3D = %KeyLight
@onready var preview_fill_light: DirectionalLight3D = %FillLight
@onready var preview_rim_light: DirectionalLight3D = %RimLight
@onready var host_edit: LineEdit = %Host
@onready var port_edit: SpinBox = %Port
## A launch-only override for local developer servers; never saved as a preference.
var _dev_plain_tcp := false
@onready var user_edit: LineEdit = %Username
@onready var password_edit: LineEdit = %Password
@onready var connect_button: Button = %Connect
@onready var login_button: Button = %Login
@onready var status_label: Label = %Status
@onready var world_root: Node3D = %WorldRoot
@onready var camera_rig: IsometricCameraController = %CameraRig

# Preloaded, and left untyped, so the script resolves without depending on
# Godot's global class-name cache -- that cache is a build artifact and is
# stale in a working copy until the editor next scans the project.
const InteriorCutawayScript := preload("res://src/world/interior_cutaway.gd")
const SecretSectionsScript := preload("res://src/world/secret_sections.gd")
const OccluderFadeScript := preload("res://src/world/occluder_fade_manager.gd")
const CrowdPresentationScript := preload("res://src/world/crowd_presentation.gd")
const LiveEffectBudgetScript := preload("res://src/world/live_effect_budget.gd")
const UndergroundSceneryScript := preload("res://src/world/underground_scenery.gd")
const InvasionAssistantScript := preload("res://src/ui/invasion_assistant.gd")
const ExtensionWindowsScript := preload("res://src/ui/extension_windows.gd")
const MapViewScript := preload("res://src/world/map_view.gd")
const MapMarkerOverlayScript := preload("res://src/ui/map_marker_overlay.gd")
const ContinentMapScript := preload("res://src/ui/continent_map.gd")
const MinimapMarkerOverlayScript := preload("res://src/ui/minimap_marker_overlay.gd")
const NearbyIndicatorScript := preload("res://src/ui/nearby_indicator.gd")
const InterestProtocol := preload("res://src/network/interest_protocol.gd")
const PlayerInfoPanelScript := preload("res://src/ui/player_info_panel.gd")
const AudioDirectorScript := preload("res://src/audio/audio_director.gd")
const AudioMix := preload("res://src/audio/audio_mix.gd")
const FootstepSurface := preload("res://src/audio/footstep_surface.gd")
const SpellsWindowScript := preload("res://src/ui/spells_window.gd")
const SummoningWindowScript := preload("res://src/ui/summoning_window.gd")
const EmotesWindowScript := preload("res://src/ui/emotes_window.gd")
const RangingWindowScript := preload("res://src/ui/ranging_window.gd")
const MountsWindowScript := preload("res://src/ui/mounts_window.gd")
const BannerDisplayMenuScript := preload("res://src/ui/banner_display_menu.gd")
const GuildWindowScript := preload("res://src/ui/guild_window.gd")
const LeaderboardsWindowScript := preload("res://src/ui/leaderboards_window.gd")
const SettingsWindowScript := preload("res://src/ui/settings_window.gd")
const GraphicsOptions := preload("res://src/world/graphics_options.gd")
const GraphicsLaunchOptions := preload("res://src/updates/launch_options.gd")
const CapeEmblems := preload("res://src/actors/cape_emblems.gd")
const TargetMarkerStyle := preload("res://src/actors/target_marker_style.gd")
const ChatHudScript := preload("res://src/ui/chat_hud.gd")
const ChatMessages := preload("res://src/ui/chat_messages.gd")
const ChatLogTabsScript := preload("res://src/ui/chat_log_tabs.gd")
const LoginBackdropScript := preload("res://src/ui/login_backdrop.gd")
const ReferenceWindowScript := preload("res://src/ui/reference_window.gd")
const ActiveBuffBarScript := preload("res://src/ui/active_buff_bar.gd")
const StatusEffectIcons := preload("res://src/ui/status_effect_icons.gd")
const KeyBindings := preload("res://src/ui/key_bindings.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
var interior_cutaway: RefCounted = InteriorCutawayScript.new()
## On a secrets map, only the secret the player stands in is drawn; the rest
## of the map (and so the minimap and full map, which render the same world)
## stays black.
var secret_sections: RefCounted = SecretSectionsScript.new()
var occluder_fade: RefCounted = OccluderFadeScript.new()
var invasion_assistant_window
var extension_windows: Control
@onready var gameplay_camera: Camera3D = %Camera
@onready var world_loader: WorldLoader = %WorldLoader
var exterior_stream: ExteriorRegionStream
var _continuous_map_handoff := false
var _retained_traveller := -1
var _retained_until := 0
var _stream_lighting_at := 0
@onready var fallback_ground: MeshInstance3D = $GameView/ViewportContainer/Viewport/WorldRoot/Ground
@onready var world_environment: WorldEnvironment = $GameView/ViewportContainer/Viewport/WorldRoot/Environment
@onready var world_sun: DirectionalLight3D = $GameView/ViewportContainer/Viewport/WorldRoot/Sun
## The night's only directed light: dark and hidden while the sun is up.
@onready var world_moon: DirectionalLight3D = $GameView/ViewportContainer/Viewport/WorldRoot/Moon

var ambient_population: AmbientPopulation
var map_light_root: Node3D
@onready var main_viewport: SubViewport = $GameView/ViewportContainer/Viewport
@onready var viewport_container: TextureRect = $GameView/ViewportContainer
@onready var map_viewport: SubViewport = %MapViewport
@onready var map_camera: Camera3D = %MapCamera
@onready var full_map_viewport: SubViewport = %FullMapViewport
@onready var full_map_camera: Camera3D = %FullMapCamera
@onready var map_marker_title: Label = %MapMarkerTitle
@onready var map_marker_list: RichTextLabel = %MapMarkerList
@onready var minimap: TextureRect = %Minimap
@onready var minimap_frame: Panel = %MinimapFrame
@onready var full_map: Control = %FullMap
@onready var map_image: TextureRect = %MapImage
@onready var map_title: Label = %MapTitle
@onready var map_coordinates: Label = %MapCoordinates
@onready var map_cursor_coordinates: Label = %MapCursorCoordinates
@onready var continent_button: TextureButton = %ContinentButton
@onready var current_map_button: Button = %CurrentMapButton
@onready var region_preview: TextureRect = %RegionPreview
@onready var continent_view: Control = %ContinentView
@onready var continent_image: TextureRect = %ContinentImage
@onready var health_bar: ProgressBar = %Health
@onready var health_text: Label = %HealthText
@onready var mana_bar: ProgressBar = %Mana
@onready var mana_text: Label = %ManaText
@onready var action_bar: ProgressBar = %Action
@onready var action_text: Label = %ActionText
@onready var health_bottom: ProgressBar = %HealthBottom
@onready var health_bottom_text: Label = %HealthBottomText
@onready var ether_bottom: ProgressBar = %EtherBottom
@onready var ether_bottom_text: Label = %EtherBottomText
@onready var food_bottom: ProgressBar = %FoodBottom
@onready var food_bottom_text: Label = %FoodBottomText
@onready var load_bottom: ProgressBar = %LoadBottom
@onready var load_bottom_text: Label = %LoadBottomText
@onready var action_bottom: ProgressBar = %ActionBottom
@onready var action_bottom_text: Label = %ActionBottomText
@onready var experience_bottom: ProgressBar = %ExperienceBottom
@onready var experience_bottom_text: Label = %ExperienceBottomText
@onready var bottom_meters: HBoxContainer = %BottomMeters
@onready var skill_rows: VBoxContainer = %SkillRows
@onready var experience_skill_label: Label = %ExperienceSkillLabel
@onready var hud_timer_label: Label = %HudTimer
@onready var knowledge_bar: ProgressBar = %KnowledgeBar
@onready var knowledge_text: Label = %KnowledgeText
@onready var fps_label: Label = %FpsLabel
@onready var hud_indicators: HBoxContainer = %HudIndicators
@onready var clock_text: Label = %ClockText
@onready var clock_hand: Line2D = %ClockHand
@onready var clock_face: TextureRect = %ClockFace
@onready var compass_needle: Line2D = %CompassNeedle
@onready var compass_face: TextureRect = %CompassFace
@onready var hud_logo: TextureRect = %HudLogo
@onready var right_rail: Panel = %RightRail
@onready var actor_resource_overlay: PanelContainer = %ActorResourceOverlay
@onready var overhead_player_name: Label = %OverheadPlayerName
@onready var overhead_health_row: HBoxContainer = %HealthRow
@onready var overhead_ether_row: HBoxContainer = %EtherRow
@onready var overhead_food_row: HBoxContainer = %FoodRow
@onready var overhead_action_row: HBoxContainer = %ActionRow
@onready var overhead_load_row: HBoxContainer = %LoadRow
@onready var stats_panel: Control = %StatsPanel
@onready var stats_text: RichTextLabel = %StatsText
@onready var stats_tabs: TabContainer = %StatsTabs
## The Perks tab and its parts, built in code beside the scene's own tabs.
var perk_tab: MarginContainer
var perk_summary: Label
var perk_rows: VBoxContainer
var perk_filters: HBoxContainer
var perk_hint: Label
#: Which tab of the perk window is showing. Empty is "All".
var _perk_filter: String = ""
var purchase_confirm: PanelContainer
var purchase_prompt: Label
## What the confirmation dialog is currently asking about: the kind the
## server understands and the name it takes, or empty when nothing is asked.
var _pending_purchase: Array[String] = []
@onready var stats_close: Button = %StatsClose
@onready var counter_categories: ItemList = %CounterCategories
@onready var counter_text: RichTextLabel = %CounterText
@onready var session_xp_text: RichTextLabel = %SessionXpText
@onready var session_reset: Button = %SessionReset
@onready var inventory_panel: Control = %InventoryPanel
@onready var inventory_header: Control = $GameView/InventoryPanel/Content/Header
@onready var inventory_resize_grip: Control = %InventoryResizeGrip
@onready var inventory_grid: GridContainer = %InventoryGrid
@onready var equipment_grid: GridContainer = %EquipmentGrid
@onready var inventory_body: HBoxContainer = %InventoryBody
@onready var equipment_column: VBoxContainer = %EquipmentColumn
@onready var backpack_column: VBoxContainer = %BackpackColumn
@onready var inventory_description: RichTextLabel = %InventoryDescription
@onready var inventory_use_button: Button = %InventoryUse
@onready var inventory_equip_button: Button = %InventoryEquip
@onready var inventory_unequip_button: Button = %InventoryUnequip
@onready var inventory_inspect_button: Button = %InventoryInspect
@onready var inventory_store_all: Button = %InventoryStoreAll
@onready var inventory_get_all: Button = %InventoryGetAll
@onready var inventory_drop_all: Button = %InventoryDropAll
@onready var inventory_mix_all: Button = %InventoryMixAll
@onready var inventory_item_lists: Button = %InventoryItemLists
@onready var inventory_load: Label = %InventoryLoad
@onready var item_lists_panel: Control = %ItemListsPanel
@onready var saved_item_lists: ItemList = %SavedItemLists
@onready var item_list_name: LineEdit = %ItemListName
@onready var item_list_entries: TextEdit = %ItemListEntries
@onready var item_list_status: Label = %ItemListStatus
@onready var item_list_save: Button = %ItemListSave
@onready var item_list_delete: Button = %ItemListDelete
@onready var item_list_get: Button = %ItemListGet
@onready var item_lists_close: Button = %ItemListsClose
@onready var sit_button: Button = %SitButton
@onready var attack_button: Button = %AttackButton
@onready var trade_button: Button = %TradeButton
@onready var look_button: Button = %LookButton
@onready var spell_power_down: Button = %SpellPowerDown
@onready var spell_power_value: Label = %SpellPowerValue
@onready var spell_power_up: Button = %SpellPowerUp
@onready var trade_panel: Control = %TradePanel
@onready var trade_partner: Label = %TradePartner
@onready var trade_source: ItemList = %TradeSource
@onready var trade_source_type: OptionButton = %TradeSourceType
@onready var trade_storage_category: OptionButton = %TradeStorageCategory
@onready var trade_own_offers: ItemList = %TradeOwnOffers
@onready var trade_other_offers: ItemList = %TradeOtherOffers
@onready var trade_quantity: SpinBox = %TradeQuantity
@onready var trade_status: Label = %TradeStatus
@onready var trade_offer_button: Button = %TradeOffer
@onready var trade_remove_button: Button = %TradeRemove
@onready var trade_accept_button: Button = %TradeAccept
@onready var trade_reject_button: Button = %TradeReject
@onready var trade_storage_destination: CheckBox = %TradeStorageDestination
@onready var storage_panel: Control = %StoragePanel
@onready var storage_categories: ItemList = %StorageCategories
@onready var storage_type: OptionButton = %StorageType
@onready var storage_sort: OptionButton = %StorageSort
@onready var storage_items: ItemList = %StorageItems
@onready var storage_inventory: ItemList = %StorageInventory
@onready var storage_quantity: SpinBox = %StorageQuantity
@onready var storage_status: Label = %StorageStatus
@onready var storage_deposit_button: Button = %StorageDeposit
@onready var storage_withdraw_button: Button = %StorageWithdraw
@onready var storage_inspect_button: Button = %StorageInspect
@onready var ground_bag_panel: Control = %GroundBagPanel
@onready var inventory_quantity_bar: HBoxContainer = %InventoryQuantityBar
@onready var inventory_quantity_edit: LineEdit = %InventoryQuantityEdit
@onready var carried_item: TextureRect = %CarriedItem
@onready var ground_bag_header: Control = %GroundBagHeader
@onready var ground_bag_grid: GridContainer = %GroundBagGrid
@onready var ground_bag_drop_button: Button = %GroundBagDrop
@onready var ground_bag_resize_grip: Button = %GroundBagResizeGrip
@onready var knowledge_list: ItemList = %KnowledgeList
@onready var knowledge_detail: RichTextLabel = %KnowledgeDetail
@onready var knowledge_known_only: CheckBox = %KnowledgeKnownOnly
@onready var manufacturing_panel: Control = %ManufacturingPanel
@onready var manufacturing_filter: LineEdit = %ManufacturingFilter
@onready var manufacturing_list: ItemList = %ManufacturingList
@onready var manufacturing_detail: RichTextLabel = %ManufacturingDetail
@onready var manufacturing_status: Label = %ManufacturingStatus
@onready var manufacturing_mix_one: Button = %ManufacturingMixOne
@onready var manufacturing_mix_all: Button = %ManufacturingMixAll
@onready var quick_slot_container: GridContainer = %ItemSlots
@onready var spell_slot_container: GridContainer = %SpellSlots
@onready var spell_status: Label = %SpellStatus
@onready var player_map_marker: MeshInstance3D = %PlayerMapMarker
@onready var map_label: Label = %MapLabel
@onready var actor_label: Label = %ActorLabel
@onready var chat_output: RichTextLabel = %ChatOutput
@onready var chat_input: LineEdit = %ChatInput
@onready var chat_panel: PanelContainer = %ChatPanel
@onready var chat_hud: PanelContainer = %ChatWindow
var system_chat_hud: PanelContainer
var chat_log_tabs: HFlowContainer
@onready var console_panel: PanelContainer = %ConsolePanel
@onready var connection_banner: Label = %ConnectionBanner
@onready var harvest_banner: Label = %HarvestBanner
@onready var reading_panel: PanelContainer = %ReadingPanel
@onready var reading_title: Label = %ReadingTitle
@onready var reading_close: Button = %ReadingClose
@onready var reading_progress: ProgressBar = %ReadingProgress
@onready var reading_detail: RichTextLabel = %ReadingDetail
@onready var popup_panel: PanelContainer = %PopupPanel
@onready var popup_title: Label = %PopupTitle
@onready var popup_text: RichTextLabel = %PopupText
@onready var popup_options: VBoxContainer = %PopupOptions
@onready var popup_confirm: Button = %PopupConfirm
@onready var popup_dismiss: Button = %PopupDismiss
@onready var console_output: RichTextLabel = %ConsoleOutput
@onready var console_diagnostics_button: Button = %ConsoleDiagnostics
@onready var diagnostics_output: RichTextLabel = %DiagnosticsOutput
var settings_panel: PanelContainer
@onready var sound_enabled: CheckButton = %SoundEnabled
@onready var sound_volume: HSlider = %SoundVolume
@onready var sound_volume_value: Label = %SoundVolumeValue
@onready var minimap_size: HSlider = %MinimapSize
@onready var minimap_size_value: Label = %MinimapSizeValue
@onready var show_through_obstacles: CheckButton = %ShowThroughObstacles
@onready var ui_scale_slider: HSlider = %UiScale
@onready var ui_scale_value: Label = %UiScaleValue
@onready var equipment_side: OptionButton = %EquipmentSide
@onready var minimap_north: Label = %North
@onready var minimap_east: Label = %East
@onready var minimap_south: Label = %South
@onready var minimap_west: Label = %West
@onready var selected_target: Label = %SelectedTarget
@onready var dialogue_panel: Control = %DialoguePanel
@onready var dialogue_name: Label = %DialogueName
@onready var dialogue_text: RichTextLabel = %DialogueText
@onready var dialogue_options: VBoxContainer = %DialogueOptions
@onready var login_background: TextureRect = %LoginBackground
var start_screen_backdrop: Control
@onready var login_logo: TextureRect = %LoginLogo

var actor_nodes: Dictionary = {}
var ground_bag_nodes: Dictionary = {}
## The click-to-walk crosses currently collapsing, keyed by destination tile
## so a re-click restarts a tile's mark instead of stacking a brighter copy.
## Each marker frees itself when its half second is up.
var walk_highlight_markers: Dictionary = {}
var map_object_nodes: Dictionary = {}
## How the current map's own package presents its world objects
## (`_bind_map_presentation`): {"map": the server map it was read for,
## "nodes": object id -> MapObject3D.presentation, "groupings": the package's
## harvestGroupings}. Object ids repeat across maps, so nothing here is used
## for any other map; empty until the map binds, and for a package that states
## no presentation.
var _map_presentation: Dictionary = {}
## Server-placed map markers on the current map, keyed by the server's marker id.
var map_marker_nodes: Dictionary = {}
var player_mark_nodes: Dictionary = {}
var map_marker_overlay: Control
## The minimap's marks. Both maps draw marks in pixels at every map extent.
var minimap_marker_overlay: Control
## Short-lived world effects the server announced. Kept only so a test can see
## what is on screen; each one frees itself when it finishes.
var world_effects: Array = []
var _world_effects_compact_at := 32
## The glitter around the player while they harvest; null when they are not.
var harvest_sparkle: HarvestSparkle3D
## The sky and the fires the server placed on this map.
var weather_layer: Weather3D
## False until the first sky after logging in, which is set at once; every
## later change of weather eases in.
var _weather_synced := false
## The map the weather was last synced for: a sky met by crossing into
## another map eases in over at least Weather3D.CROSSING_EASE_SECONDS.
var _weather_map := ""
var _weather_lighting_at := 0
## The weather look the light was last applied under (Weather3D.look_version),
## so the sky is applied again while the weather eases, its last step included.
var _weather_applied_version := -1
## Whether that look had any weather in it, so the haze is put back once it clears.
var _weather_applied_active := false
## The streamed maps' own lamps, lit at dusk and through the night.
var night_lamps: NightLamps
## The map's declared mist and gulls (environment.presentation).
var presentation_effects: PresentationEffects
## Objects the server placed into this map after it loaded, by object id.
var placed_object_nodes: Dictionary = {}
var audio_director: Node
var map_ambience_root: Node3D
var spells_window: Control
var summoning_window: Control
var emotes_window: Control
var ranging_window: Control
var mounts_window: Control
## The Techniques tab inside the Spells & Techniques window. The Tab-held
## technique ring and the quick spell slots aim through it.
var techniques_panel: VBoxContainer
var technique_ring: Control
var guild_window: Control
var leaderboards_window: Control
var settings_window: Control
var reference_window: Control
## Client-side presentation switches. None of them changes what the server
## decides; they change what this machine draws.
var _shadows_enabled := true
var _effects_enabled := true
var _nameplates_enabled := true
var _target_marker_style := TargetMarkerStyle.defaults()
## Trailer capture (`_configure_trailer_capture`): off unless the client was
## launched with TRAILER_CAPTURE_ARGUMENT. 0 draws the HUD, 1 the world alone,
## 2 the world without nameplates. Never saved.
var _trailer_capture_enabled := false
var _trailer_capture_level := 0
var _trailer_capture_layer: CanvasLayer
var _name_distance_metres := NAME_DISTANCE_DEFAULT_METRES
## The player's crowd settings (Graphics): how many other actors are drawn with
## a body at once, and how many of the nearest other capes sway at High.
var _crowd_bodies := SettingsWindowScript.CROWD_BODIES_DEFAULT
var _swaying_capes := SettingsWindowScript.SWAYING_CAPES_DEFAULT
## "+N nearby" in the lower corner of the minimap (nearby_indicator.gd).
var nearby_indicator: Label
## A distant player's dot from the presence rows is drawn a size down from a
## dot with a body under it: it is where they were up to a second ago.
const PRESENCE_DOT_RADIUS := 3.0
## How long the crowd setting must rest before a changed actor cap is
## re-declared to the server, and which change is the latest.
const ACTOR_CAP_REDECLARE_SECONDS := 0.5
var _actor_cap_declaration := 0
var _presence_tiles := PackedVector2Array()
var _presence_mark_pool: Array[Dictionary] = []
var _fps_limit := 0
var _render_scale := 1.0
var _map_texture_quality := "full"
var _renderer_preference := "auto"
var _startup_renderer_preference := GraphicsLaunchOptions.saved_renderer()
var _applying_graphics_preset := false
var _player_notes := ""
## True while the loaded package lets the hour drive its environment. An
## interior does not, and neither does a package that opts out.
var console_commands := ConsoleCommands.new()
var _console_history: Array[String] = []
var _console_history_index := 0
var _day_night_active := false
var _day_night_refresh_msec := 0
## The power the next cast asks for. Presentational: the server states what
## each effect may reach and refuses anything it will not allow.
var requested_spell_power := 1
var magic_selection: Control
var spell_loadout = preload("res://src/ui/spell_loadout.gd").new()
var casting_bar: Control
var spell_wheel: Control
var _magic_area_preview: MeshInstance3D
var player_info_panel: Control
var active_buff_bar: Control
var local_status_grid: GridContainer
var _local_status_effects: Array[String] = []
## Server map objects whose tile has no navigation surface beneath it on the
## rendered map. Misplaced content rather than a client fault, but silent
## unless somebody counts it.
var _ungrounded_map_objects: Dictionary = {}
var models: Dictionary = {}
var actor_type_models: Dictionary = {}
var npc_looks: Dictionary = {}
var npc_characters: Dictionary = {}
var creation_options: Array = []
var selected_creation_class := 0
var creation_class_gear_visible := true
var _creation_appearance_rng := RandomNumberGenerator.new()
## Orun and Mycelari are amber-eyed (owner call, October 2026): creation opens
## a new one on Amber gold and the Randomize roll keeps to the two ambers.
## Appearance ids, not menu rows: 3 Amber gold, 9 Amber orange.
const AMBER_EYED_CULTURES := ["orun", "mycelari"]
const AMBER_EYES: Array[int] = [3, 9]
var animation_config: Dictionary = {}
var animation_configs: Dictionary = {}
var map_registry: Dictionary = {}
## The models that stand on the server's world objects, by resource and by
## role; see `map_object_3d.gd`. Loaded once here because every object placed
## has to be handed it - an object given no registry falls back to a ring on
## the ground, which is what the whole harvestable layer did while this was
## never loaded at all.
var world_object_models: Dictionary = {}
var cartography: Dictionary = {}
var cartography_regions: Array = []
## Region outlines in continent picture pixels, for which territory a map click is on.
var _region_polygons: Array[Array] = []
## The continent picture and the regions' tab maps are decoded the first
## time the map window opens, not at startup: the continent alone is a
## 1600-pixel image nobody sees before pressing Tab.
var continent_map: Control
var _continent_texture: Texture2D
var _cartography_loaded := false
var _v2_cartography: Dictionary = {}
var _continent_frame := ""
var _continent_textures: Dictionary = {}
## Overlay-local indices map to the combined cartography table's region indices.
var _continent_region_indices: Array[int] = []
var _tab_map_textures: Dictionary = {}
## Keep detailed images for visible regions and the most recent preview.
## The wider overview uses the small images warmed in _tab_map_textures.
var _tab_map_detail_textures: Dictionary = {}
var _map_detail_visible: Dictionary = {}
## Which region the big map is showing as a preview, or -1 for none, with
## that map's own adapter so the cursor can name the tile under it.
var _preview_region_index := -1
var _preview_adapter: CoordinateAdapter
const StorageOverlayScript := preload("res://src/ui/storage_map_overlay.gd")
var _storage_preview_overlay: Control
var _storage_continent_overlay: Control
const EntranceOverlayScript := preload("res://src/ui/entrance_map_overlay.gd")
var _entrance_preview_overlay: Control
var _entrance_continent_overlay: Control
const ServiceOverlayScript := preload("res://src/ui/service_map_overlay.gd")
var _service_preview_overlay: Control
var _service_continent_overlay: Control
## The Landfall boat network's routes and docks on the continent picture.
const BoatRouteOverlayScript := preload("res://src/ui/boat_route_overlay.gd")
var _boat_continent_overlay: Control
var equipment_config: Dictionary = {}
var item_atlas := ItemAtlas.new()
var spell_catalog := SpellCatalog.new()
var manufacturing_catalog := ManufacturingCatalog.new()
var knowledge_catalog: Array[String] = []
var gameplay_world: World3D
var loaded_server_map := ""
var adapter := CoordinateAdapter.new({"walkingHeight": 0.0, "invertServerY": true})
var preview_actor: ReplicatedActor3D
var pending_create_username := ""
var pending_create_password := ""
var preview_yaw := PI + 0.28
## Where the preview camera looks. Not the world origin: the coordinate
## adapter places a tile at its own centre, so the body stands half a tile
## off it, and a camera fixed on the origin framed it a hundred pixels wide
## of the disc it is meant to be standing on.
var preview_focus := Vector3(0.0, 1.0, 0.0)
var preview_pitch := 0.12
## Character creation is a hero stage, not a distant model viewer. This fills
## most of the preview height at the default zoom while retaining wheel room in
## both directions.
var preview_distance := 1.95
var inventory_slot_buttons: Array[Button] = []
var inventory_quantity_labels: Array[Label] = []
var equipment_slot_buttons: Array[Button] = []
var quick_slot_buttons: Array[Button] = []
var spell_slot_buttons: Array[Button] = []
var selected_inventory_slot := -1
var selected_trade_side := ""
var trade_destinations: PackedByteArray = PackedByteArray()
var trade_was_open := false
var selected_storage_side := ""
## The stored-items organizer. Both are this client's own view of the shelf:
## nothing is sent to the server, and the positions it withdraws by are
## unaffected by how the list happens to be filtered or ordered.
var storage_type_filter := ""
var storage_sort_mode := "name"
## The last storage order worked out, and what it was worked out from. A
## deposit changes a count, not a name, so most replies sort nothing.
var _storage_sort_key: Array = []
var _storage_sort_order: Array = []
var selected_manufacturing_recipe := -1
var manufacturing_server_status := "Select a recipe."
## More than anyone mixes in one sitting, and small enough that a typed digit
## too many is caught here rather than by the server.
const MANUFACTURING_MAX_QUANTITY := 1000
## The manufacturing window. These are built rather than laid out in the
## scene, because none of them has a fixed shape: there are as many skill tabs
## as the served recipes mention skills, as many tool rows as the selected
## recipe needs tools, and a queue has no rows at all until somebody fills it.
var manufacturing_tabs: HFlowContainer
var manufacturing_side: VBoxContainer
var _inventory_metadata_at := 0
var manufacturing_tool_rows: VBoxContainer
var manufacturing_quantity: LineEdit
var manufacturing_source: CheckButton
var manufacturing_ready_only: CheckButton
var manufacturing_ready_preference := true
var manufacturing_queue_rows: VBoxContainer
var manufacturing_queue_start: Button
var manufacturing_skill := ""
## Queued batches, `{recipe, wanted, made}`, worked from the top. The queue
## lives here rather than on the server because the server mixes one batch at
## a time and says when each one ends; a second copy of the list over there
## would be another thing to keep in step and would buy nothing. The cost is
## that a queue does not survive logging out, which is the honest trade.
var manufacturing_queue: Array[Dictionary] = []
var manufacturing_queue_running := false
var manufacturing_queue_index := 0
## Batches asked for and not yet seen the end of, oldest first. Two can be
## outstanding at once: Mix Now cuts a queued batch short, so that batch's end
## and the start of the one replacing it are both in flight. Which one ended
## is settled by the name of what was being made, because the inventory window
## can start a mix too and its batch belongs to no queue entry.
var _mix_pending: Array[Dictionary] = []
var cooldown_display_second := -1
var _chat_tab := "all"
var _current_map_display_name := "Unknown map"
var _minimap_scale := 1.0
var _minimap_orientation := MINIMAP_DEFAULT_ORIENTATION
var _minimap_zoom := MINIMAP_ZOOM_DEFAULT
## Tab map extent relative to its default framing. Below 1 it magnifies the
## cursor's location; above 1 a continent exterior shows its neighbours.
var _full_map_region_id := ""
var _full_map_zoom := 1.0
var _full_map_base_size := 0.0
var _full_map_base_position := Vector3.ZERO
var _full_map_zoomable := false
## Cursor zoom and manual pan hold their world position until returning to
## the current map restores player follow. Delay a click until release so a drag
## never also sends a movement command.
var _full_map_panned := false
var _full_map_pan_position := Vector3.ZERO
var _full_map_pan_press: InputEventMouseButton
var _full_map_pan_origin := Vector3.ZERO
var _full_map_pan_dragging := false
var _full_map_cursor_inside := false
var _full_map_cursor_position := Vector2.ZERO
## The final map click, rather than an intermediate crossing in a route.
var _map_walk_target: Dictionary = {}
var _minimap_marker_scale := 1.0
var _minimap_border := MINIMAP_DEFAULT_BORDER
## "square" or "round". A round minimap is the map masked to the circle its
## frame holds, which is the shape the compass letters were always arranged in.
var _minimap_shape := MINIMAP_DEFAULT_SHAPE
## Which marker types are drawn, keyed by MINIMAP_MARKER_TYPES.
var _minimap_marker_types: Dictionary = _default_minimap_marker_types()
var _map_environment: Environment
## Develop's environment for the bound map: a copy taken as WorldEnvironmentBinder
## built it, before the look painted its sky or graded it, and the manifest it
## was bound from. The look's switch rebinds from it (`_rebind_look_environment`)
## rather than binding the manifest again, which would re-aim a sun a seamless
## crossing has turned with the world and spawn the map's lamps twice.
## The copy holds no Sky of its own (`_unlooked_sky` keeps what one is made of):
## the renderer allocates a live Sky's radiance maps whether anything draws it
## or not, which cost every player 37 MiB of video memory on every map with a
## sky, look on or off.
var _unlooked_environment: Environment
## The sky of `_unlooked_environment` as its material, radiance size and process
## mode, assembled into a Sky again only when the switch restores it; empty on a
## map whose background is a colour.
var _unlooked_sky: Dictionary = {}
var _environment_manifest: WorldManifest
var _minimap_dragging := false
var _minimap_drag_offset := Vector2.ZERO
var _inventory_scale := 1.0
var _inventory_dragging := false
var _inventory_resizing := false
var _inventory_drag_offset := Vector2.ZERO
var _inventory_resize_start_mouse := Vector2.ZERO
var _inventory_resize_start_scale := 1.0
var _equipment_side := "left"
var _ui_scale := 1.0
var _show_through_obstacles := true
var _bulk_exclusions: Dictionary = {
	"store": [false, false, false, false],
	"drop": [false, false, false, false]}
var _item_lists: Dictionary = {}
var classic_storage: ClassicStorageWorkspace
var _store_options_menu: PopupMenu
var _drop_options_menu: PopupMenu
var _minimap_menu: PopupMenu
var _minimap_orientation_menu: PopupMenu
var _minimap_marker_type_menu: PopupMenu
var _minimap_visualization_menu: PopupMenu
var _minimap_marker_size_menu: PopupMenu
var _minimap_shape_menu: PopupMenu
var _minimap_window_size_menu: PopupMenu
var _minimap_border_menu: PopupMenu
## Kept so the round/square choice can round the frame's own corners off. The
## style is built in `_apply_eloria_theme()` along with every other window's.
var _minimap_panel_style: StyleBoxFlat
var _minimap_mask_material: ShaderMaterial
var _minimap_visible := false
## Set when the socket dropped without the player asking. The next successful
## login resynchronises rather than trusting anything from before the drop.
var _resync_after_reconnect := false
var _reading_completed_index := -1
var _reading_shown_index := -1
var _reading_hidden := false
var _popup_radio_groups: Dictionary = {}
var _popup_radio_buttons: Dictionary = {}
var _popup_entries: Dictionary = {}
var _session_started_msec := 0
var _experience_snapshot: Dictionary = {}
var _session_xp_gain: Dictionary = {}
var _session_xp_max: Dictionary = {}
var _session_xp_last: Dictionary = {}
var _session_distance := 0
var _last_distance_tile := Vector2i(-99999, -99999)
## The server owns every lifetime total. The "this session" column is the
## difference against the totals as they stood when the session or the reset
## started, which is presentation of authoritative numbers, not a second count.
var _counter_session_baseline: Dictionary = {}
var _keyboard_moving := false
var _keyboard_running := false
var _keyboard_direction := Vector2i.ZERO
var _keyboard_goal_tile := Vector2i(-99999, -99999)
var _keyboard_refresh_msec := 0
## The intent epoch the held direction was last sent under, or -1 when the
## keyboard is walking by MOVE_TO (or not at all).
var _keyboard_intent_epoch := -1
var _ground_bag_get_all_requested_msec := -1
var _ground_bag_get_all_bag_id := -1
## The inventory slot riding on the cursor in walk mode, or -1. Eternal Lands
## picks an item up on the first click and puts it down on the second; the
## slot number is the whole of the state, because the item itself never leaves
## the server's inventory until the placing click is answered.
var _carried_slot := -1
## The storage position riding on the cursor, or -1: Eternal Lands' storage
## carry. Each click on the backpack then withdraws the selected quantity.
## Positions index the server's sorted storage list and shift when a kind of
## item comes or goes, so the item's picture and name ride along with it.
var _storage_carried_position := -1
var _storage_carried_item: Dictionary = {}
var _inventory_quantities: Array[int] = INVENTORY_QUANTITY_DEFAULTS.duplicate()
var _inventory_tool := "grab"
## Whether the next item description may open the detail window. The short line
## and the detail window are two readings of the same server reply, so which
## one the player gets is decided here rather than by asking the server twice.
var _detail_popup_allowed := false
var _ground_bag_scale := 1.0
var _ground_bag_resizing := false
var _ground_bag_resize_start_mouse := Vector2.ZERO
var _ground_bag_resize_start_scale := 1.0
var _selected_quantity_box := 0
var _editing_quantity_box := -1
var inventory_quantity_buttons: Array[Button] = []
var ground_bag_slot_buttons: Array[Button] = []
var ground_bag_quantity_labels: Array[Label] = []
var _ground_bag_dragging := false
var _ground_bag_drag_offset := Vector2.ZERO
var _selected_counter_category := ""
#: Counters whose breakdown is open. A row opens on its own and stays open
#: while the totals underneath it change, so this is remembered here rather
#: than rebuilt with the rows.
var _open_counters: Dictionary = {}
var counter_tabs: HBoxContainer
var stats_pools: HBoxContainer
var stats_character: VBoxContainer
var stats_pickpoint_summary: Label
var stats_pickpoint_status: Label
var stats_pickpoint_confirm: Button
var _pickpoint_draft: Dictionary = {}
var _pickpoint_submitting := false
var stats_skills: VBoxContainer
var stats_overall: HBoxContainer
var stats_perk_line: Label
var counter_body: VBoxContainer
var _interaction_mode := "walk"
## Alt held down. While it is, an ordinary click attacks whatever it lands on,
## so the move icon shows the attack icon to say so. It is a preview and not a
## mode: letting Alt go puts the move icon back, and it never disturbs an
## attack mode the player chose from the HUD.
var _alt_attack_preview := false
## The action pointer: the cursor names what a click would do (walk, talk,
## attack, harvest...), the way the legacy client's does. Refreshed on a short
## clock rather than per motion event, because the answer also changes while
## the mouse holds still - the camera turns, an actor walks under the pointer,
## a mode button is pressed.
var mouse_cursors := MouseCursors.new()
var _cursor_refresh_msec := 0
var _encyclopedia_bookmarks: Array = []
var _hud_icon_regions: Dictionary = {}
var _hud_active_atlas: Texture2D
var _hud_inactive_atlas: Texture2D
var _hud_button_state_mask := -1
var _hud_state_buttons: Array[Button] = []
var _minimap_refresh_msec := 0
var _full_map_refresh_msec := 0
var _preview_updates_enabled := true
var _world_sync_queued := false
var _storage_sync_queued := false
var _actor_surface_samples: Dictionary = {}
var _grounded_actors: Dictionary = {}
var _actor_surface_snap_pending := false
## Completion spans include deferred/physics waits; actual loop work is
## recorded separately so diagnostics do not mistake waiting for CPU work.
var _surface_followup_pending := 0
var _surface_followup_stats: Dictionary = {}
var _surface_work_stats: Dictionary = {}
var _surface_refresh_queue = SurfaceRefreshQueue.new()
var _surface_refresh_running := false
var _surface_refresh_epoch := 0
var _surface_refresh_inflight := 0
var _surface_spatial_stats: Dictionary = {"batches": 0, "full_batches": 0, "notifications": 0,
	"invalidated_regions": 0, "actor_visits": 0, "actor_placement_attempts": 0,
	"object_visits": 0, "object_placement_attempts": 0, "binding_candidates": 0}
var _local_placement_logged := false
## Set when `_sync_world` ran out of spawn budget with actors still to
## build; the next frame picks them up.
var _spawn_backlog := false
## Full body creation has one count/time allowance per rendered process frame,
## shared by initial arrivals and later deferred-body promotion. Placeholder
## creation and parked-body reuse retain their own existing behavior.
var _actor_creation_frame := -1
var _actor_creation_count := 0
var _actor_creation_spent_usec := 0
var _actor_creation_priority_seen: Dictionary = {}
var _actor_creation_overrun_seen := false
## Bounded scalar diagnostics, never a per-actor or per-frame history.
var _actor_creation_totals: Dictionary = {"builds": 0, "priorityBypasses": 0,
	"atomicOverruns": 0, "framesOverBudget": 0, "maximumAtomicUsec": 0,
	"maximumFrameUsec": 0, "maximumBuildsInFrame": 0}
## The local character's arrival while its ground streams in behind the
## curtain: {position, started, ready}. Empty when none is pending.
var _arrival: Dictionary = {}
## A fresh map load waiting for the curtain to be on screen, so a whole map's
## synchronous build happens behind it instead of freezing the last view.
var _deferred_map_load := false
## Frames the curtain stays up after the character is grounded.
var _arrival_settle_frames := 0
## The local character was spawned and the server has not yet been told it
## stands on loaded ground (`_report_arrival`).
var _arrival_unreported := false
## An arrival that has not loaded by then is grounded synchronously, and a
## curtain still up is lowered: neither may strand a player.
const ARRIVAL_TIMEOUT_MSEC := 30000
const ARRIVAL_CURTAIN_LIMIT_MSEC := 60000
## The region's picture under the map cameras, or null on a map without one.
var _map_picture: MeshInstance3D
## The ground the current region's picture lies on: what the other regions'
## pictures sink below, since only a loaded region publishes its own.
var _map_picture_height := 0.0
## Regions whose tab-map textures are still to be decoded ahead of a crossing.
var _map_picture_warmup: Array[String] = []
var _map_picture_warmup_armed := false
## The other regions' pictures, keyed by normalized map id: a quad under each
## resident's root, so it stands in that map's rigid frame, and one in
## world_root for every region that is not loaded.
var _neighbour_pictures: Dictionary = {}
## Neighbour map id -> {transform, adapter}: the framed adapters actors on
## resident neighbours are placed through, rebuilt when the root moves.
var _neighbour_adapters: Dictionary = {}
## Decides which actors animate this frame, and how often; see AnimationGate.
var animation_gate: AnimationGate = AnimationGate.new()
var _animation_gate_refresh_msec := 0
## One walk of the animation gate over the actors, spread across the frames of
## a refresh period (`_update_animation_gate`): the ids it walks, how far it
## has got, what it measures from, and what it has gathered for its end.
var _gate_sweep_active := false
var _gate_sweep_whole := false
## Whether a sliced sweep left the overhead declutter for the next frame, and
## the target it keeps visible (`_finish_gate_sweep`).
var _declutter_due := false
var _declutter_due_target := -1
var _gate_sweep_ids: Array = []
var _gate_sweep_index := 0
var _gate_now := 0
var _gate_local: Node3D
var _gate_here := Vector3.ZERO
var _gate_fighting := -1
var _gate_reference := Vector3.ZERO
var _gate_camera_at := Vector3.ZERO
var _gate_build_candidates: Array = []
var _gate_releases: Array = []
var _gate_built := 0
var _gate_ranked: Array = []
var _gate_built_ranked: Array = []
var _gate_full_rate: Array = []
var _gate_capes: Array = []
## Which actors get a body, and which removed ones are kept for a return; see
## crowd_presentation.gd. `effect_budget` bounds the combat visuals alive at
## once. Both read RABBITLANDS_CROWD_PRESENTATION, which benchmarks use to turn
## each part off.
var crowd = CrowdPresentationScript.new()
var effect_budget = LiveEffectBudgetScript.new()
## Which actor the selection ring and the overhead target were last given to,
## so a pass only touches the actors whose answer changed.
var _selection_ring_actor := -1
var _overhead_target_actor := -1
## Built bodies (not deferred), recounted on every gate pass and kept up to
## date in between by the passes that build or remove one; the body cap reads it.
var _built_bodies := 0
## How far the body cap reaches this pass: the distance of the cap-th nearest
## actor in range, INF with no cap or fewer actors than it.
var _body_cap_distance := INF
## Counts nodes AppState removed in bulk (KILL_ALL_ACTORS, a dropped
## connection) since the last pass; see `_sync_world`.
var _actor_roster_generation_seen := -1
## The statistics window's built parts fall behind the stats packets while
## it is hidden; they are rebuilt when it is next shown.
var _stats_window_stale := true
## The last chat line each log rendered, so a new line can be appended to
## it rather than the log rebuilt. See `_append_chat_line`.
var _chat_tail: Dictionary = {}
var _console_tail: Dictionary = {}
## Command 226's item descriptions by slot, rebuilt when the server sends a
## new list rather than searched for every slot of every refresh.
var _described_slots: Dictionary = {}
var _described_source: Array = []
var _hud_meter_order: Array[String] = ["mana", "food", "health", "load", "action", "experience"]
var _hud_meter_visible: Dictionary = {
	"mana": true, "food": true, "health": true,
	"load": true, "action": true, "experience": true}
var _selected_experience_skill := "harvesting"
## The rail's countdown/stopwatch, kept to Eternal Lands' behaviour: click to
## start or stop, shift+click to change mode, middle-click to reset, wheel to
## set the countdown start. The value only ever lives here - it is a kitchen
## timer, not game state.
var _hud_timer_stopwatch := false
var _hud_timer_running := false
var _hud_timer_seconds := 90
var _hud_timer_start_seconds := 90
var _hud_timer_last_tick_msec := 0
## Which parts of the legacy HUD are drawn, in Eternal Lands' terms. Persisted
## under [hud] and toggled from the settings window's HUD tab.
var _hud_element_options: Dictionary = {
	"show_fps": true, "show_game_seconds": true, "hud_timer": true,
	"knowledge_bar": true, "side_stats": true, "indicators": true,
	"analog_clock": true, "digital_clock": true, "chat_timestamps": true,
	# Damage and healing float over whoever took them, kept as three switches
	# because the three are wanted at different times.
	"damage_numbers_self": true, "damage_numbers_players": true,
	"damage_numbers_creatures": true}
## The health each actor was last seen at, so the next update is a change
## rather than a number. Cleared with the actors it describes.
var _actor_health_seen: Dictionary = {}
## The per-skill rail rows, keyed by stat name, each holding bar + labels.
var _skill_row_nodes: Dictionary = {}
## The indicator letters, keyed by their Eternal Lands letter.
var _indicator_labels: Dictionary = {}
## Private messages that arrived and have not been acknowledged by clicking
## the M indicator, which is exactly what Eternal Lands' M indicator counts.
var _unseen_pm_count := 0
var _fps_refresh_msec := 0
var _hud_layout_list: ItemList
var hud_workspace: Control
var _hud_layout_visible: CheckButton
var _hud_skill_selector: OptionButton
var _floating_feedback_layer: Control
var _world_text_overlay: TextureRect
var _pending_floating_feedback: Array[Dictionary] = []
var _floating_feedback_flush_queued := false
var _active_floating_labels: Array[Label] = []
var _last_skill_experience_msec := -100000
## Persisted banner key -> the checkbox shared with the main settings window.
var _banner_option_boxes: Dictionary = {}
var _banner_background_style: StyleBoxFlat
const CreatureBannerSettings := preload("res://src/ui/creature_banner_settings.gd")
const BannerColors := preload("res://src/ui/banner_colors.gd")
var _creature_banner_options := CreatureBannerSettings.defaults()
const MountControls := preload("res://src/mounts/mount_controls.gd")
@onready var mount_status := MountControls.new()
var _mount_banner_options: Dictionary = MountControls.default_options()
var _actor_hud_menu: Variant

const FLOATING_FEEDBACK_ROW_HEIGHT := 21.0
const FLOATING_FEEDBACK_MAX_ROWS := 4
const FLOATING_FEEDBACK_RISE := 58.0
const FLOATING_FEEDBACK_LIFETIME := 1.5
const FLOATING_FEEDBACK_FADE_DELAY := 0.5
const FLOATING_FEEDBACK_OVERALL_GRACE_MSEC := 250

const HUD_SKILLS: Array[String] = [
	"attack", "defense", "harvesting", "alchemy", "magic", "potion",
	"summoning", "manufacturing", "crafting", "engineering", "tailoring",
	"ranging", "overall"]

## Eternal Lands drives its overhead banner from the right-click menu built in
## gamewin.c, and every entry there is its own switch. The menu keeps EL's
## wording and order, with the action-point pair Eloria adds appended to the
## bar/number block. Keys are what eloria_hud.cfg stores.
const BANNER_OPTION_NODES := {
	"show_names": "ShowNames",
	"health_bar": "ShowHealthBar", "health_numbers": "ShowHealthNumbers",
	"ether_bar": "ShowEtherBar", "ether_numbers": "ShowEtherNumbers",
	"food_bar": "ShowFoodBar", "food_numbers": "ShowFoodNumbers",
	"action_bar": "ShowActionBar", "action_numbers": "ShowActionNumbers",
	"load_bar": "ShowLoadBar", "load_numbers": "ShowLoadNumbers",
	"instance_mode": "InstanceMode", "speech_bubbles": "SpeechBubbles",
	"banner_background": "BannerBackground", "sit_lock": "SitLock",
	"ranging_lock": "RangingLock", "menu_disabled": "DisableMenu"}

const BANNER_OPTION_DEFAULTS := {
	"show_names": true,
	"health_bar": true, "health_numbers": true,
	"ether_bar": true, "ether_numbers": true,
	"food_bar": true, "food_numbers": true,
	"action_bar": true, "action_numbers": true,
	"load_bar": false, "load_numbers": false,
	"instance_mode": false, "speech_bubbles": false,
	"banner_background": false, "sit_lock": false,
	"ranging_lock": false, "menu_disabled": false}

## Row name, the switch that shows its bar, the switch that shows its numbers,
## and the colour ramp actors.c uses for it.
const BANNER_ROWS := [
	["HealthRow", "health_bar", "health_numbers", "health"],
	["EtherRow", "ether_bar", "ether_numbers", "ether"],
	["FoodRow", "food_bar", "food_numbers", "food"],
	["ActionRow", "action_bar", "action_numbers", "action"],
	["LoadRow", "load_bar", "load_numbers", "load"]]

const BANNER_BAR_MIN_WIDTH := 46.0
## client_serv.h: BOW_LONG through BOW_CROSS are the ranged weapon visuals, and
## gamewin.c gates Ranging Lock on exactly that span.
const RANGE_WEAPON_FIRST := 64
const RANGE_WEAPON_LAST := 68
## interface.c defaults instance_mode_banner_height to five banner lines.
const BANNER_INSTANCE_LIFT_ROWS := 5.0
## World metres between the top of your head and the foot of your own banner.
const BANNER_HEAD_CLEARANCE := 0.15
const SPEECH_BUBBLE_MSEC := 5000

const SETTINGS_PATH := "user://eloria_hud.cfg"
const KEYBOARD_LOOKAHEAD_TILES := 4
const KEYBOARD_REFRESH_MSEC := 360
const GROUND_BAG_GET_ALL_TIMEOUT_MSEC := 1000
const GROUND_BAG_SLOT_COUNT := 20
## The legacy client's six editable quantity boxes and their defaults. The
## selected one is the amount every drop and every pick-up uses.
const INVENTORY_QUANTITY_DEFAULTS: Array[int] = [1, 5, 10, 20, 50, 100]
## Seven digits: a stack can run into the millions on a long-lived character,
## and a box that cannot hold the number cannot be used to move it.
const INVENTORY_QUANTITY_MAX := 9999999
const INVENTORY_QUANTITY_DIGITS := 7

## What a left click on an item does. Right-clicking an item steps through
## these in order, and the Use, Equip, Unequip and Inspect buttons each select
## one, so the buttons and the click do the same thing by the same names.
const INVENTORY_TOOLS: Array[String] = ["grab", "use", "inspect"]
const INVENTORY_TOOL_LABELS := {
	"grab": "Move", "use": "Use", "equip": "Equip", "unequip": "Unequip",
	"inspect": "Inspect",
}
## The widths that border can be set to, narrowest first. The band is also the
## only thing the minimap window can be dragged by, so the narrowest is a band
## a mouse can still find rather than none at all: a minimap that cannot be
## moved is worse than one with a visible edge.
## Masks the minimap render to the circle its frame holds. A shader rather than
## a cut-out texture, because the frame is any of five sizes and a texture cut
## for one of them is a jagged edge at the other four.
const MINIMAP_MASK_SHADER := """
shader_type canvas_item;
uniform bool rounded = false;
uniform int hud_palette = 0;
void fragment() {
	if (rounded) {
		vec2 offset = UV - vec2(0.5);
		if (dot(offset, offset) > 0.25) {
			discard;
		}
	}
	float luminance = dot(COLOR.rgb, vec3(0.2126, 0.7152, 0.0722));
	if (hud_palette == 1) {
		COLOR.rgb = mix(vec3(0.22, 0.15, 0.08), vec3(0.91, 0.81, 0.59), luminance);
	} else if (hud_palette == 2) {
		COLOR.rgb = mix(vec3(0.10, 0.13, 0.12), vec3(0.48, 0.51, 0.46), luminance);
	}
}
"""
const MINIMAP_BORDER_STEPS: Array[float] = [8.0, 16.0, 27.0, 40.0]
const MINIMAP_BORDER_LABELS: Array[String] = ["Minimal", "Thin", "Normal", "Wide"]
## How a fresh installation shows the minimap, before the player picks
## anything: a round map with the least frame, turned the way the camera
## faces so up on the minimap is ahead on screen.
const MINIMAP_DEFAULT_ORIENTATION := "viewport_up"
const MINIMAP_DEFAULT_SHAPE := "round"
const MINIMAP_DEFAULT_BORDER: float = MINIMAP_BORDER_STEPS[0]
## What the minimap window's size option offers, matching the range the
## settings window's slider already moves between so the two cannot disagree.
const MINIMAP_SIZE_STEPS: Array[float] = [0.75, 1.0, 1.25, 1.5, 1.75]
## What the marker size option offers. These multiply the pixel radii in
## `minimap_marker_overlay.gd`, which is the whole size of a mark now that the
## zoom no longer contributes to it.
const MINIMAP_MARKER_SCALES: Array[float] = [0.6, 0.8, 1.0, 1.3, 1.7]
const MINIMAP_MARKER_SCALE_LABELS: Array[String] = [
	"Tiny", "Small", "Normal", "Large", "Huge"]
## Every kind of mark the minimap draws, in the order the marker-types menu
## lists them, with the label each is switched on and off by. The keys are also
## the settings-file keys, so a type added here is remembered without anything
## else being taught about it.
const MINIMAP_MARKER_TYPES: Array[StringName] = [&"self", &"player", &"npc",
	&"creature", &"invasion", &"harvest", &"interactive", &"portal",
	&"entrance", &"exit", &"marker"]
const MINIMAP_MARKER_TYPE_LABELS := {
	&"self": "Your position", &"player": "Players", &"npc": "NPCs",
	&"creature": "Creatures", &"invasion": "Invasion creatures",
	&"harvest": "Harvest nodes", &"interactive": "Interactives",
	&"portal": "Portals", &"exit": "Map exits",
	&"entrance": "Insides entrances",
	&"marker": "Map markers",
}
## The floor under the ambient light the two map cameras render with, so a
## minimap at midnight is still a map.
const MAP_MINIMUM_AMBIENT := 0.9
## Breathing room inside each bottom-rail icon button, so the painted frame the
## icon carries does not touch its neighbour or the panel border.
const HUD_ICON_PADDING := 2.0

## Eternal Lands' indicator letters, their meanings, and how each state is
## honestly known here. G (glow perk) and A (summon attack-at-will) have no
## server signal on this fork, so they render as unavailable rather than
## pretending a state.
const HUD_INDICATORS: Array[Array] = [
	["S", "Special Day", "Ordinary Day"],
	["H", "Harvesting", "Not Harvesting"],
	["P", "Poison (not stated by this server)", "Poison (not stated by this server)"],
	["M", "Recent Messages", "No Messages"],
	["R", "Ranging Lock On", "Ranging Lock Off"],
	["G", "Glow Perk (not on this server)", "Glow Perk (not on this server)"],
	["A", "Attack at Will (not on this server)", "Attack at Will (not on this server)"]]

## One rail stat row. The rail's font is ten pixels and its line box is
## thirteen, so a twelve-pixel row cut every descender in half; fourteen holds
## the line with the text centred in it.
const SKILL_ROW_HEIGHT := 14.0

## The rail's stat rows, in Eternal Lands' order and abbreviations.
const SKILL_ROW_SPECS: Array[Array] = [
	["att", "attack"], ["def", "defense"], ["har", "harvesting"],
	["alc", "alchemy"], ["mag", "magic"], ["pot", "potion"],
	["sum", "summoning"], ["man", "manufacturing"], ["cra", "crafting"],
	["eng", "engineering"], ["tai", "tailoring"], ["ran", "ranging"],
	["oa", "overall"]]
## Cell 24 of the HUD atlas: the standing figure the sit icon wears while the
## player is seated.
const STAND_ICON_REGION := Rect2(0, 96, 32, 32)

const INDICATOR_ACTIVE_COLOUR := Color(0.95, 0.76, 0.52)
const INDICATOR_INACTIVE_COLOUR := Color(0.40, 0.30, 0.20)
const INDICATOR_UNAVAILABLE_COLOUR := Color(0.20, 0.15, 0.10)

## Nothing may cover the fixed resource rail down the right-hand edge; this is
## the margin draggable scene windows are clamped against.
const RESERVED_RIGHT_RAIL_MARGIN := 96.0

## The GUI palette Eternal Lands paints every window with (elwindows.c):
## borders, frames and title text in gui_color, hover fills in the inverse.
const EL_GUI_COLOUR := Color(0.77, 0.57, 0.39)
const EL_GUI_INVERT_COLOUR := Color(0.32, 0.23, 0.15)
const EL_GUI_BRIGHT_COLOUR := Color(0.95, 0.76, 0.52)
## How much of the continent the Tab map frames: 1 is the region and the
## collar of its neighbours. The wheel can magnify up to 400% around the
## player or pull back over the continent's pictures.
const FULL_MAP_ZOOM_STEP := 1.25
const FULL_MAP_ZOOM_MIN := 0.25
const FULL_MAP_ZOOM_MAX := 6.0
const FULL_MAP_PAN_THRESHOLD := 6.0
## How many metres of ground the minimap camera covers, and the bounds the
## scroll wheel moves it between.
const MINIMAP_ZOOM_DEFAULT := 180.0
const MINIMAP_ZOOM_MIN := 60.0
const MINIMAP_ZOOM_MAX := 480.0
const MINIMAP_ZOOM_STEP := 1.25
const UI_SCALE_MIN := 0.5
const UI_SCALE_MAX := 1.5
# The minimap and the full map are extra renders of the whole 3D world through
# their own cameras. Both used to redraw every frame, visible or not, which
# tripled the client's raster and shadow cost for two top-down views that read
# identically at a fraction of the rate.
const MINIMAP_REFRESH_MSEC := 66
const FULL_MAP_REFRESH_MSEC := 200
## The action pointer re-reads what it is over ten times a second: quick
## enough that the swap reads as immediate, and rare enough that its three
## pick rays never matter.
const ACTION_CURSOR_REFRESH_MSEC := 100
## The sky only has to keep up with a six-hour day; twice a second is already
## finer than the eye can follow and costs a handful of property writes.
const DAY_NIGHT_REFRESH_MSEC := 500
## The animation gate re-reads which actors the camera can see ten times a
## second: the camera and the actors both move smoothly, so that set changes
## far more slowly than the frame rate does.
const ANIMATION_GATE_REFRESH_MSEC := 100
## The animation gate's walk over the actors is spread over this many frames.
## At 60 FPS that is the refresh period; at a lower frame rate a sweep takes
## longer, which still never leaves an actor unclassified for long.
const GATE_SWEEP_SLICES := 6
## How far from the player another actor is still drawn in the world. Past
## this its body and its name come off the viewport and only its map dot is
## left, so it still marks the minimap and the full map. The isometric rig
## frames about fifty metres at its default zoom, so this is comfortably past
## what the camera shows. What prompted it was Crownwater, where the lagoon is
## open enough to read the names of everyone on a pavilion a hundred and sixty
## metres away, stacked over the water in front of the player.
const ACTOR_DRAW_DISTANCE_METRES := 80.0
## The visual layer the region's own map picture is drawn on, and the only
## layer the map cameras render while a picture is installed.
const MAP_PICTURE_LAYER := 8
## How far each further region's picture lies below the current one, so two
## pictures whose rectangles overlap never fight over the same ground.
const MAP_PICTURE_SINK_METRES := 0.05
## How far from the player another actor's name, title and health bar still
## show. The block is drawn at a fixed screen size so it stays readable at any
## zoom, which also means a name sixty metres off is as large as one at arm's
## length, and a castle gate read as a field of labels. So the block
## fades out over the last few metres before this distance, the body carries on
## to the draw distance, and the player can move it from the Graphics settings.
## The slider's range lives with the slider, in settings_window.gd.
const NAME_DISTANCE_DEFAULT_METRES := SettingsWindowScript.NAME_DISTANCE_DEFAULT
const NAME_FADE_METRES := 5.0
## The launch argument (after `--`) that arms trailer capture, and the fixed,
## unbindable key that cycles it (`_configure_trailer_capture`).
const TRAILER_CAPTURE_ARGUMENT := "--trailer-capture"
const TRAILER_CAPTURE_KEY := KEY_F9
## How many actors `_sync_world` builds in one pass. A spawn is a couple of
## milliseconds of model, skin and equipment work, so a pack of twenty
## arriving together was one long frame; the rest follow on the next frames.
const ACTOR_SPAWN_BUDGET := 4
## The chat panel shows this many of the newest lines. The console shows the
## whole buffer AppState keeps.
const CHAT_PANEL_LINES := 100
## How many submitted lines the console remembers for its up/down history.
const CONSOLE_HISTORY_LIMIT := 60
## The fork's spell quickbar. Twelve slots on Alt+1-0, Alt+- and Alt+=,
## which is where Eternal Lands puts K_SPELL1..12 (keys.c); the legacy
## client showed six of them, and the catalog has more than six spells.
const SPELL_QUICK_SLOTS := 12
## The ceilings the server enforces on what a pick point can buy, so the "+"
## is not offered on a line that is already full. They are the server's, from
## `eloria/perks.py`; a purchase is still the server's to refuse.
## Only for a server too old to send ELORIA_ATTRIBUTE_STATE, which is also the
## only kind of server these six names still describe. A current one sends its
## own ceiling with every attribute.
const ATTRIBUTE_MAXIMUM := 48
const LEGACY_ATTRIBUTES: Array[Array] = [["Physique", "physique"],
	["Coordination", "coordination"], ["Reasoning", "reasoning"],
	["Will", "will"], ["Instinct", "instinct"], ["Vitality", "vitality"]]
const NEXUS_MAXIMUM := 10
const INVENTORY_MIN_SCALE := 0.65
const INVENTORY_MAX_SCALE := 1.75
const TILE_DIRECTIONS: Array[Vector2i] = [
	Vector2i(0, -1), Vector2i(1, -1), Vector2i(1, 0), Vector2i(1, 1),
	Vector2i(0, 1), Vector2i(-1, 1), Vector2i(-1, 0), Vector2i(-1, -1)]
const EXPERIENCE_SKILLS: Array[String] = [
	"attack", "defense", "harvesting", "alchemy", "magic", "potion",
	"summoning", "manufacturing", "crafting", "engineering", "tailoring",
	"ranging", "overall"]

func _ready() -> void:
	client_runtime.initialize()
	crowd.configure(OS.get_environment("RABBITLANDS_CROWD_PRESENTATION"),
		OS.get_environment("RABBITLANDS_CROWD_BODY_CAP"),
		OS.get_environment("RABBITLANDS_CROWD_TUNING"))
	effect_budget.enabled = crowd.effects
	animation_gate.gate_skeletons = crowd.gate
	animation_gate.stagger = crowd.stagger
	animation_gate.one_shot_tier = (AnimationGate.Tier.QUARTER if crowd.quarter
		else AnimationGate.Tier.HALF)
	world_root.add_child(quest_trail)
	add_child(character_intro)
	add_child(arrival_curtain)
	character_intro.conversation_requested.connect(_request_arrival_conversation)
	character_intro.conversation_ended.connect(_end_arrival_conversation)
	Diagnostics.record("main_scene_initializing")
	var client_updates := preload("res://src/updates/client_updates.gd").new()
	add_child(client_updates)
	# Before any map load, and on the main thread: registering the map image
	# extension edits a list that a worker import iterates (vram_textures.gd).
	VramTextures.ensure_registered()
	lantern_guide = LanternGuideScript.new()
	game_view.add_child(lantern_guide)
	lantern_guide.configure(self)
	actor_resource_overlay.get_node("Rows").add_child(mount_status)
	mount_status.display_changed.connect(_layout_actor_resource_overlay)
	var model_registry: Dictionary = _json("res://data/actors/models.json")
	models = model_registry.get("models", {})
	actor_type_models = model_registry.get("actorTypes", {})
	npc_looks = model_registry.get("npcLooks", {})
	npc_characters = _json("res://data/actors/npc_characters.json")
	creation_options = model_registry.get("creationOptions", [])
	animation_config = _json("res://data/animations/luminous.json")
	animation_configs["res://data/animations/luminous.json"] = animation_config
	var registry_document := _json("res://data/maps/registry.json")
	map_registry = registry_document.get("maps", {})
	var coordinate_catalog: Dictionary = Network.configure_coordinate_profiles(
		registry_document.get("coordinateProfiles", {}), registry_document.get("coordinateMapNames", {}), map_registry)
	if not coordinate_catalog.ok:
		push_error("Invalid coordinate registry: " + str(coordinate_catalog.error))
	exterior_stream = ExteriorRegionStream.new()
	exterior_stream.name = "ExteriorRegionStream"
	world_root.add_child(exterior_stream)
	exterior_stream.configure(map_registry)
	exterior_stream.coordinate_context = Network.coordinates
	Network.coordinate_route_cancelled.connect(func() -> void:
		exterior_stream.pending_walk.clear()
		_clear_map_walk_target())
	Network.movement_requested.connect(_on_movement_requested)
	get_tree().auto_accept_quit = false
	get_tree().root.close_requested.connect(_close_client)
	world_object_models = _json("res://data/world/objects.json")
	# The nine Eloria extension windows live in their own script: main.gd is
	# already long enough that nine more windows would make it unreadable, and
	# they share one seam - the fork's extension protocol.
	map_marker_overlay = MapMarkerOverlayScript.new()
	map_marker_overlay.name = "MapMarkerOverlay"
	map_marker_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_image.add_child(map_marker_overlay)
	map_marker_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	map_marker_overlay.configure(full_map_camera, adapter, full_map_viewport.size)
	minimap_marker_overlay = MinimapMarkerOverlayScript.new()
	minimap_marker_overlay.name = "MinimapMarkerOverlay"
	minimap_marker_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	minimap.add_child(minimap_marker_overlay)
	minimap_marker_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	minimap_marker_overlay.configure(map_camera, map_viewport.size)
	nearby_indicator = NearbyIndicatorScript.new()
	minimap.add_child(nearby_indicator)
	audio_director = AudioDirectorScript.new()
	audio_director.surface_at_tile = _footstep_surface_at
	add_child(audio_director)
	player_info_panel = PlayerInfoPanelScript.new()
	game_view.add_child(player_info_panel)
	# The three legacy windows Eternal Lands opens from its icon row: the spell
	# book, the emote picker and the ranging readout. Each lives in its own
	# script; main.gd only opens them and lends them a network seam.
	spells_window = SpellsWindowScript.new()
	game_view.add_child(spells_window)
	spells_window.reserve_bottom_hud($GameView/Quickbar)
	techniques_panel = spells_window.get("techniques_panel") as VBoxContainer
	techniques_panel.call("configure", Network.technique_request,
		_technique_creature_target, _technique_player_target)
	techniques_panel.connect("place_on_bar", _place_technique_on_bar)
	# Configured further down, once the spell catalog has read its data file:
	# the window builds its group rows from the catalog it is handed.
	summoning_window = SummoningWindowScript.new()
	game_view.add_child(summoning_window)
	# Also configured further down: it builds its rows from the manufacturing
	# catalog, which is read at the same point the spell catalog is.
	emotes_window = EmotesWindowScript.new()
	game_view.add_child(emotes_window)
	emotes_window.call("configure", _perform_emote)
	ranging_window = RangingWindowScript.new()
	game_view.add_child(ranging_window)
	mounts_window = MountsWindowScript.new()
	game_view.add_child(mounts_window)
	%MountsButton.pressed.connect(func() -> void: mounts_window.call("toggle"))
	(mounts_window.get("panel") as Control).visibility_changed.connect(func() -> void: _sync_hud_button_states(true))
	guild_window = GuildWindowScript.new()
	game_view.add_child(guild_window)
	guild_window.call("configure", Network.send_chat)
	leaderboards_window = LeaderboardsWindowScript.new()
	game_view.add_child(leaderboards_window)
	leaderboards_window.call("configure", Network.send_chat, model_registry, equipment_config)
	%LeaderboardsButton.icon = _external_texture("res://assets/ui/menu-icons/leaderboard.png")
	%LeaderboardsButton.expand_icon = true
	%LeaderboardsButton.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
	%LeaderboardsButton.vertical_icon_alignment = VERTICAL_ALIGNMENT_CENTER
	%LeaderboardsButton.text = ""
	%LeaderboardsButton.toggle_mode = true
	%LeaderboardsButton.pressed.connect(func() -> void: leaderboards_window.call("toggle"))
	(leaderboards_window.get("panel") as Control).visibility_changed.connect(func() -> void: _sync_hud_button_states(true))
	settings_window = SettingsWindowScript.new()
	game_view.add_child(settings_window)
	settings_panel = settings_window.panel
	settings_window.setting_changed.connect(_on_client_setting_changed)
	settings_window.binding_changed.connect(_on_binding_changed)
	reference_window = ReferenceWindowScript.new()
	game_view.add_child(reference_window)
	reference_window.notes_changed.connect(_on_notes_changed)
	reference_window.bookmarks_changed.connect(_on_encyclopedia_bookmarks_changed)
	active_buff_bar = ActiveBuffBarScript.new()
	active_buff_bar.bottom_hud = $GameView/Quickbar
	game_view.add_child(active_buff_bar)
	active_buff_bar.configure(spell_catalog)
	extension_windows = ExtensionWindowsScript.new()
	game_view.add_child(extension_windows)
	extension_windows.configure(item_atlas, lantern_guide)
	_configure_service_buttons()
	extension_windows.gauntlet_loot_window.configure(item_atlas, model_registry, equipment_config)
	extension_windows.combat_hud_preference_changed.connect(_save_hud_settings)
	invasion_assistant_window = InvasionAssistantScript.new()
	add_child(invasion_assistant_window)
	invasion_assistant_window.configure_monitor_dock(_invasion_monitor_dock_rect)
	invasion_assistant_window.configure_registry(map_registry)
	invasion_assistant_window.coordinate_context = Network.coordinates
	invasion_assistant_window.command_requested.connect(
		_on_invasion_assistant_command_requested)
	cartography = _json("res://data/maps/cartography.json")
	cartography_regions = (cartography.get("regions", []) as Array).duplicate()
	_v2_cartography = _json("res://data/maps/cartography-continent-v2.json")
	cartography_regions.append_array(_continent_v2_tab_maps(cartography))
	var detail_maps: Dictionary = _json("res://data/maps/map-details.json").get("regions", {}) as Dictionary
	for region: Dictionary in cartography_regions:
		var detail: Dictionary = detail_maps.get(str(region.get("serverMap", "")), {}) as Dictionary
		var tab_map: Dictionary = region.get("tabMap", {}) as Dictionary
		if not detail.is_empty() and detail.get("worldMin") == tab_map.get("worldMin") \
				and detail.get("worldMax") == tab_map.get("worldMax"):
			tab_map["detail"] = detail
	_region_polygons.clear()
	invasion_assistant_window.configure_cartography(cartography_regions)
	equipment_config = preload(
		"res://src/actors/equipment_registry_snapshot_cache.gd").prepare(
		_json("res://data/actors/equipment.json"))
	item_atlas.configure(_json("res://data/items/atlases.json"))
	spell_catalog.configure(_json("res://data/spells/catalog.json"))
	spells_window.call("configure", spell_catalog, _cast_spell_by_id)
	magic_selection = preload("res://src/ui/magic_selection.gd").new()
	magic_selection.catalog = spell_catalog
	add_child(magic_selection)
	magic_selection.status_changed.connect(func(message: String) -> void: spell_status.text = message)
	AppState.magic_state_received.connect(_on_magic_state)
	var death_panel := preload("res://src/ui/death_panel.gd").new()
	death_panel.actor_for_player = func() -> Variant: return actor_nodes.get(AppState.local_actor_id)
	game_view.add_child(death_panel)
	spell_loadout.configure(spell_catalog)
	magic_selection.cast_submitted.connect(spell_loadout.remember_cast)
	magic_selection.target_validator = _spell_target_candidate
	spells_window.set_loadout(spell_loadout)
	casting_bar = preload("res://src/ui/casting_bar.gd").new()
	casting_bar.loadout = spell_loadout
	casting_bar.dock_anchor = $GameView/ItemQuickbar
	casting_bar.item_slots = quick_slot_container
	casting_bar.dock_rail = right_rail
	casting_bar.dock_top = $GameView/EloriaLogoFrame
	casting_bar.dock_bottom = $GameView/ResourceHud
	casting_bar.dock_footer = $GameView/RailMeters
	casting_bar.bottom_hud = $GameView/Quickbar
	casting_bar.reserved_right_width = 96.0
	casting_bar.z_index = 7
	game_view.add_child(casting_bar)
	casting_bar.layout_changed.connect(_save_hud_settings)
	magic_selection.z_index = 8
	casting_bar.cast_slot.connect(_cast_spell_slot)
	casting_bar.edit_slot.connect(spells_window.edit_prepared_slot)
	casting_bar.open_book.connect(_on_spells_button_pressed)
	spell_wheel = preload("res://src/ui/quick_spell_ring.gd").new()
	spell_wheel.loadout = spell_loadout
	spell_wheel.preferences = spell_loadout.ring_preferences
	spell_wheel.preferences_changed.connect(spell_loadout.save_ring_preferences)
	spell_wheel.target_validator = _spell_target_candidate
	spell_wheel.tutorial_action.connect(_magic_ring_ui)
	spell_wheel.anchor_provider = _spell_wheel_anchor
	spell_wheel.can_open = _can_open_spell_wheel
	spell_wheel.z_index = 250
	game_view.add_child(spell_wheel)
	spell_wheel.spell_chosen.connect(_begin_prepared_cast)
	spell_wheel.opened.connect(func():
		spell_wheel.move_to_front()
		magic_selection.cancel()
		spells_window.close()
		_stop_keyboard_movement()
		_magic_ring_ui(20))
	casting_bar.open_wheel.connect(spell_wheel.open_wheel)
	# Hold Z (technique_ring) for the technique ring; it aims through the
	# Techniques tab exactly as the tab and the quick slots do.
	technique_ring = preload("res://src/ui/technique_ring.gd").new()
	technique_ring.set("techniques", techniques_panel)
	technique_ring.set("anchor_provider", _spell_wheel_anchor)
	technique_ring.set("can_open", _can_open_technique_ring)
	technique_ring.z_index = 250
	game_view.add_child(technique_ring)
	spell_loadout.changed.connect(func():
		magic_selection.target_mode = spell_loadout.targeting_mode()
		spell_wheel.preferences = spell_loadout.ring_preferences
		_sync_spells())
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--magic-mode="):
			spell_loadout.set_mode(argument.trim_prefix("--magic-mode="))

	manufacturing_catalog.configure(_json("res://data/manufacturing/recipes.json"))
	summoning_window.call("configure", manufacturing_catalog, item_atlas,
		_summon_by_ingredients, _request_summon_behavior)
	var knowledge_catalog_value: Variant = _json(
		"res://data/knowledge/catalog.json").get("entries", [])
	if knowledge_catalog_value is Array:
		for raw_knowledge_name: Variant in knowledge_catalog_value as Array:
			knowledge_catalog.append(str(raw_knowledge_name))
	# The encyclopedia builds half its pages out of these, so a recipe, spell,
	# book, region or skill the client does not have cannot appear on a page.
	reference_window.call("configure_catalogues", {
		"manufacturing": manufacturing_catalog, "spells": spell_catalog,
		"books": knowledge_catalog, "regions": cartography_regions,
		"items": item_atlas, "skills": EXPERIENCE_SKILLS})
	Network.connection_state_changed.connect(_on_connection_state_changed)
	Network.protocol_error.connect(func(message: String): status_label.text = "Protocol error: " + message)
	Network.reconnect_progress.connect(_on_reconnect_progress)
	AppState.login_succeeded.connect(_on_login_succeeded)
	AppState.login_failed.connect(_on_login_failed)
	AppState.character_created.connect(_on_character_created)
	AppState.character_creation_failed.connect(_on_character_creation_failed)
	AppState.state_changed.connect(_on_state_changed)
	AppState.floating_feedback_requested.connect(_on_floating_feedback_requested)
	AppState.special_effect_requested.connect(_on_special_effect_requested)
	AppState.actor_animation_requested.connect(_on_actor_animation_requested)
	AppState.missile_fired.connect(_on_missile_fired)
	AppState.ground_missile_fired.connect(_on_ground_missile_fired)
	AppState.thunder_struck.connect(_on_thunder_struck)
	AppState.teleport_seen.connect(_on_teleport_seen)
	weather_layer = Weather3D.new()
	world_root.add_child(weather_layer)
	night_lamps = NightLamps.new()
	world_root.add_child(night_lamps)
	presentation_effects = PresentationEffects.new()
	world_root.add_child(presentation_effects)
	world_loader.load_completed.connect(_on_world_loaded)
	world_loader.load_failed.connect(_on_world_load_failed)
	if mouse_cursors.configure("res://assets/ui/cursors/cursors.json"):
		mouse_cursors.install_text_caret()
		mouse_cursors.apply(MouseCursors.ARROW)
	viewport_container.gui_input.connect(_on_world_gui_input)
	minimap.gui_input.connect(_on_minimap_gui_input)
	minimap_frame.gui_input.connect(_on_minimap_frame_gui_input)
	map_image.gui_input.connect(_on_full_map_gui_input)
	map_image.mouse_exited.connect(_on_full_map_mouse_exited)
	map_image.visibility_changed.connect(_on_full_map_visibility_changed)
	clock_face.gui_input.connect(_on_clock_gui_input)
	compass_face.gui_input.connect(_on_compass_gui_input)
	continent_button.pressed.connect(_on_continent_button_pressed)
	current_map_button.pressed.connect(_show_current_map_view)
	region_preview.gui_input.connect(_on_region_preview_gui_input)
	region_preview.mouse_exited.connect(_on_region_preview_mouse_exited)
	_bind_shared_world()
	viewport_container.texture = main_viewport.get_texture()
	_world_text_overlay = preload("res://src/ui/world_text_overlay.gd").new()
	game_view.add_child(_world_text_overlay)
	game_view.move_child(_world_text_overlay, viewport_container.get_index() + 1)
	_world_text_overlay.configure(main_viewport)
	minimap.texture = map_viewport.get_texture()
	map_image.texture = full_map_viewport.get_texture()
	full_map.hide()
	console_panel.hide()
	settings_panel.hide()
	stats_panel.hide()
	inventory_panel.hide()
	item_lists_panel.hide()
	trade_panel.hide()
	storage_panel.hide()
	ground_bag_panel.hide()
	manufacturing_panel.hide()
	game_view.hide()
	creation_panel.hide()
	_populate_creation_races()
	_populate_creation_sexes()
	_populate_creation_choices()
	_configure_creation_classes()
	_configure_creation_layout()
	_creation_appearance_rng.randomize()
	_randomize_creation_appearance()
	_update_preview_camera()
	_apply_eloria_art()
	start_screen_backdrop = LoginBackdropScript.new()
	login_background.add_child(start_screen_backdrop)
	_configure_banner_menu()
	_apply_eloria_theme()
	# The crest is deliberately outside the compact login card so the painted
	# scene can breathe. Keep that detached overlay coupled to the card even in
	# tests and utility flows that call LoginPanel.hide() directly.
	login_panel.visibility_changed.connect(_sync_login_logo_visibility)
	_sync_login_logo_visibility()
	_configure_window_layers()
	_configure_cartography()
	_load_hud_settings()
	_refresh_service_tooltips()
	# Explicit launch options select a server without changing saved settings.
	_apply_connection_launch_options(OS.get_cmdline_user_args())
	_configure_trailer_capture(OS.get_cmdline_user_args())
	_configure_inventory_menus()
	_configure_minimap_menu()
	_build_inventory_slots()
	_build_equipment_slots()
	_build_ground_bag_slots()
	_build_inventory_quantity_boxes()
	classic_storage = ClassicStorageWorkspace.new()
	classic_storage.name = "ClassicStorageWorkspace"
	add_child(classic_storage)
	classic_storage.configure(self)
	_bind_quick_slots()
	_bind_spell_slots()
	$GameView/SpellQuickbar.hide()
	_reset_trade_destinations()
	trade_source.item_selected.connect(_on_trade_source_selected)
	trade_source_type.item_selected.connect(_on_trade_source_type_selected)
	trade_storage_category.item_selected.connect(_on_trade_storage_category_selected)
	trade_own_offers.item_selected.connect(_on_trade_own_selected)
	trade_other_offers.item_selected.connect(_on_trade_other_selected)
	storage_categories.item_selected.connect(_on_storage_category_selected)
	storage_items.item_selected.connect(_on_storage_item_selected)
	storage_inventory.item_selected.connect(_on_storage_inventory_selected)
	storage_type.item_selected.connect(_on_storage_type_selected)
	storage_sort.item_selected.connect(_on_storage_sort_selected)
	_build_storage_sort_modes()
	ground_bag_header.gui_input.connect(_on_ground_bag_header_gui_input)
	knowledge_list.item_selected.connect(_on_knowledge_selected)
	knowledge_known_only.toggled.connect(_on_knowledge_filter_toggled)
	stats_tabs.tab_changed.connect(_on_stats_tab_changed)
	stats_text.meta_clicked.connect(_on_stats_meta_clicked)
	_build_perks_tab()
	stats_close.pressed.connect(func() -> void: stats_panel.hide())
	stats_panel.visibility_changed.connect(_on_stats_panel_visibility_changed)
	stats_panel.minimum_size_changed.connect(_fit_stats_window_to_viewport.call_deferred)
	_build_counters_tab()
	_build_statistics_tab()
	session_reset.pressed.connect(_reset_session_tracking)
	manufacturing_list.item_selected.connect(_on_manufacturing_selected)
	manufacturing_filter.text_changed.connect(_on_manufacturing_filter_changed)
	_build_manufacturing_window()
	chat_hud.tab_selected.connect(_on_chat_tab_pressed)
	chat_hud.channel_selected.connect(_on_channel_tab_pressed)
	_build_chat_surfaces()
	_build_hud_layout_menu()
	_configure_unified_settings()
	_load_hud_layout()
	_connect_hud_context_inputs(%Quickbar)
	_build_skill_rows()
	_build_hud_indicators()
	hud_timer_label.gui_input.connect(_on_hud_timer_gui_input)
	knowledge_bar.gui_input.connect(_on_knowledge_bar_gui_input)
	if reference_window.has_signal("buddy_add_requested"):
		reference_window.connect("buddy_add_requested", _on_buddy_add_requested)
	_apply_hud_element_options()
	get_viewport().size_changed.connect(_on_window_size_changed)
	call_deferred("_on_window_size_changed")
	sound_enabled.toggled.connect(_on_sound_enabled_toggled)
	sound_volume.value_changed.connect(_on_sound_volume_changed)
	minimap_size.value_changed.connect(_on_minimap_size_changed)
	ui_scale_slider.value_changed.connect(_on_ui_scale_changed)
	show_through_obstacles.toggled.connect(_on_show_through_obstacles_toggled)
	equipment_side.add_item("Left", 0)
	equipment_side.add_item("Right", 1)
	equipment_side.select(1 if _equipment_side == "right" else 0)
	equipment_side.item_selected.connect(_on_equipment_side_selected)
	inventory_store_all.pressed.connect(_on_inventory_store_all_pressed)
	inventory_get_all.pressed.connect(_on_inventory_get_all_pressed)
	inventory_drop_all.pressed.connect(_on_inventory_drop_all_pressed)
	inventory_mix_all.pressed.connect(_on_inventory_mix_all_pressed)
	inventory_item_lists.pressed.connect(_on_inventory_item_lists_pressed)
	inventory_store_all.gui_input.connect(_on_bulk_button_gui_input.bind("store"))
	inventory_drop_all.gui_input.connect(_on_bulk_button_gui_input.bind("drop"))
	inventory_header.gui_input.connect(_on_inventory_header_gui_input)
	inventory_resize_grip.gui_input.connect(_on_inventory_resize_grip_gui_input)
	ground_bag_resize_grip.gui_input.connect(_on_ground_bag_resize_grip_gui_input)
	for tool_button: Button in [inventory_use_button, inventory_equip_button,
			inventory_unequip_button, inventory_inspect_button]:
		tool_button.toggle_mode = true
	_sync_inventory_tool_buttons()
	saved_item_lists.item_selected.connect(_on_saved_item_list_selected)
	item_list_save.pressed.connect(_on_item_list_save_pressed)
	item_list_delete.pressed.connect(_on_item_list_delete_pressed)
	item_list_get.pressed.connect(_on_item_list_get_pressed)
	item_lists_close.pressed.connect(func() -> void: item_lists_panel.hide())
	%ConsoleClose.pressed.connect(_toggle_console)
	console_diagnostics_button.toggled.connect(_on_console_diagnostics_toggled)
	popup_confirm.pressed.connect(_on_popup_confirm_pressed)
	popup_dismiss.pressed.connect(_on_popup_dismiss_pressed)
	popup_panel.hide()
	harvest_banner.hide()
	reading_panel.hide()
	reading_close.pressed.connect(_on_reading_close_pressed)
	_session_started_msec = Time.get_ticks_msec()
	_apply_equipment_side()
	_sync_saved_item_lists()
	_sync_channel_tabs()
	_sync_stats()
	_configure_window_stack()
	hud_workspace = preload("res://src/ui/hud_workspace.gd").new()
	game_view.add_child(hud_workspace)
	hud_workspace.configure.call_deferred(self)
	_start_client_diagnostics()

func _start_client_diagnostics() -> void:
	Diagnostics.record("main_scene_ready")
	var timer := Timer.new()
	timer.wait_time = 30.0
	timer.timeout.connect(_record_client_snapshot)
	add_child(timer)
	timer.start()
	_record_client_snapshot_after_frames()

func _record_client_snapshot_after_frames() -> void:
	# Use process frames, not a GPU readback: a broken renderer must not stall
	# the diagnostic itself. Headless runs have no frame_post_draw signal.
	await get_tree().process_frame
	await get_tree().process_frame
	_record_client_snapshot()

func _record_client_snapshot() -> void:
	Diagnostics.record("viewport_snapshot", client_diagnostic_snapshot())

func client_diagnostic_snapshot() -> Dictionary:
	var active_camera := main_viewport.get_camera_3d()
	var local_actor: Variant = actor_nodes.get(AppState.local_actor_id)
	var row := {
		"authenticated": AppState.authenticated, "connection": AppState.connection_state,
		"server_map": AppState.current_map, "loaded_map": loaded_server_map,
		"login_visible": login_panel.is_visible_in_tree(),
		"game_visible": game_view.is_visible_in_tree(),
		"window_size": str(get_window().size), "viewport_size": str(main_viewport.size),
		"container_size": str(viewport_container.size),
		"viewport_update_mode": main_viewport.render_target_update_mode,
		"render_scale": _render_scale,
		"actor_creation_budget": actor_creation_budget_snapshot(),
		"ambient_creation_pending": ambient_creation_pending_count(),
		"map_texture_mip_skip": GraphicsOptions.active_texture_skip(),
		"map_texture_preference": _map_texture_quality,
		"crowd_body_cap": crowd.body_cap,
		"effect_limits": effect_budget.describe().limits,
		"viewport_texture_bound": viewport_container.texture == main_viewport.get_texture(),
		"world_bound": gameplay_world != null,
		"map_root_present": is_instance_valid(world_loader.world_root),
		"map_cache_enabled": MapSceneCache.is_enabled(), "map_cache_status": str(world_loader.cache_status),
		"map_load_phases_us": world_loader.load_phases.duplicate(),
		"surface_work": surface_work_snapshot(),
		"loader_work": world_loader.diagnostic_snapshot(),
		"streaming_work": exterior_stream.diagnostic_snapshot(),
		"client_runtime": client_runtime.snapshot(),
		"resource_retention": {
			"actor_scenes": GlbSceneCache.retention_snapshot(),
			"animations": NativeAnimationImporter.retention_snapshot(),
			"world_meshes": ExternalMeshPool.retention_snapshot(),
			"world_textures": ExternalTexturePool.retention_snapshot()},
		"actors_received": AppState.actors.size(), "actors_presented": actor_nodes.size(),
		"local_actor_received": AppState.actors.has(AppState.local_actor_id),
		"local_actor_presented": is_instance_valid(local_actor),
		"camera_present": active_camera != null,
		"fallback_ground_visible": fallback_ground.is_visible_in_tree(),
		"appearance": LookProfile.mode_name(LookProfile.mode()), "painted_look": LookProfile.enabled(), "quality": LookProfile.quality_name(LookProfile.quality()),
		"vram_mode": VramTextures.mode_name(), "vram_formats": VramTextures.format_names(VramTextures.usable_formats()),
		"fps": Engine.get_frames_per_second(), "frames_drawn": Engine.get_frames_drawn(),
		"visible_objects": main_viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_OBJECTS_IN_FRAME),
		"draw_calls": main_viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME),
		"primitives": main_viewport.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_PRIMITIVES_IN_FRAME),
		"video_memory_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
		"static_memory_bytes": OS.get_static_memory_usage()
	}
	if active_camera != null:
		row["camera_position"] = str(active_camera.global_position)
		row["camera_rotation"] = str(active_camera.global_rotation_degrees)
		row["camera_cull_mask"] = active_camera.cull_mask
		row["camera_near"] = active_camera.near
		row["camera_far"] = active_camera.far
	row["camera_focus"] = str(camera_rig.focus)
	if is_instance_valid(local_actor) and local_actor is Node3D:
		row["local_actor_position"] = str((local_actor as Node3D).global_position)
		row["local_actor_visible"] = (local_actor as Node3D).is_visible_in_tree()
	if world_loader.world_root is ContinentChunkStream:
		var chunks := world_loader.world_root as ContinentChunkStream
		row["chunks_resident"] = chunks.cells.size()
		row["chunks_have_focus"] = chunks.has_focus
		row["chunk_resident_bytes"] = chunks.resident_bytes
		row["chunk_revision"] = chunks.revision
	return row

func _bind_shared_world() -> void:
	gameplay_world = world_root.get_world_3d()
	if gameplay_world == null:
		push_error("world_binding stage=resolve error=WorldRoot_has_no_World3D")
		return
	map_viewport.world_3d = gameplay_world
	full_map_viewport.world_3d = gameplay_world
	_sync_map_viewport_activity()
	print_debug("world_binding stage=shared world=", gameplay_world)

func _process(delta: float) -> void:
	if AppState.authenticated and AppState.inventory_metadata_dirty and Network._link_ready() \
			and Time.get_ticks_msec() >= _inventory_metadata_at:
		AppState.inventory_metadata_dirty = false
		_inventory_metadata_at = Time.get_ticks_msec() + 500
		Network.send_chat("#inventory")
	_update_preview_viewport()
	_update_action_cursor()
	if audio_director != null and weather_layer != null:
		var weather_map := MapRegistry.resolve(map_registry, AppState.current_map)
		var outdoors := not weather_map.is_empty() and not weather_map.has("interiorOf") \
			and not weather_map.has("insidesOf")
		audio_director.set_weather(weather_layer.look() \
			if AppState.authenticated and outdoors else {})
	_update_arrival()
	_report_arrival()
	if _spawn_backlog:
		_spawn_backlog = false
		_queue_world_sync()
	if game_view.visible:
		_update_carried_item()
		_update_map_viewports()
		_update_local_actor_follow()
		_update_character_intro(delta)
		_update_keyboard_camera(delta)
		_update_attached_map_markers()
		var trail_actor: Variant = actor_nodes.get(AppState.local_actor_id)
		if is_instance_valid(trail_actor):
			quest_trail.update_trail(delta, (trail_actor as Node3D).global_position)
		_update_map_walk_target()
		if AppState.actors.has(AppState.local_actor_id) and not _world_input_blocked():
			exterior_stream.update_position(camera_rig.focus)
		# Look pass: a chunk or neighbour finished under the switch's old
		# answer follows the new one as it arrives, before anything fades it.
		_reconcile_look()
		# Look pass (a no-op with the look off, and it takes the beds away
		# when the look or the graphics quality stops growing them): grow the
		# grass beds around the camera's focus on whatever map is bound.
		LookGrassBeds.tend(world_root, world_loader.world_root, world_loader.manifest,
			exterior_stream.residents, camera_rig.focus)
		if Time.get_ticks_msec() >= _stream_lighting_at:
			_stream_lighting_at = Time.get_ticks_msec() + 100
			_update_border_lighting()
		# While rain arrives or clears the sky eases, so the light is applied
		# again until it has settled (the border update above does this on a
		# map with streaming borders; the isles have none).
		if weather_layer != null \
				and weather_layer.look_version != _weather_applied_version \
				and Time.get_ticks_msec() >= _weather_lighting_at:
			_weather_lighting_at = Time.get_ticks_msec() + 100
			_apply_day_night()
		var gloom := weather_layer.gloom() if weather_layer != null else 0.0
		if night_lamps != null:
			night_lamps.update(camera_rig.focus, AppState.continuous_game_minute(),
				gloom, _day_night_active)
		if presentation_effects != null and world_environment.environment != null:
			presentation_effects.update(camera_rig.focus, AppState.continuous_game_minute(),
				weather_layer.mistiness() if weather_layer != null else 0.0, gloom,
				world_environment.environment.fog_light_color, delta, _effects_enabled)
		_update_animation_gate(delta)
		_update_model_builds()
		# Rain is everywhere, so only the box the player is standing in is
		# drawn. Left at the world origin it fell a hundred metres away from
		# whoever was watching it.
		if weather_layer != null:
			weather_layer.follow(camera_rig.global_position)
		# Sections first: entering one shows its whole shell, and the cutaway
		# then takes the camera-facing walls and the roof back out of it.
		_update_secret_sections()
		interior_cutaway.update(camera_rig.yaw_degrees, false, secret_sections.current_section(),
			camera_rig.focus)
		_update_occluder_fade(delta)
		_update_keyboard_movement()
		_update_session_distance()
		_update_legacy_clock_and_compass()
		_update_actor_resource_overlay()
		_update_cooldown_overlays()
		_update_magic_preview()
		_update_hud_timer()
		_update_fps_label()
		var display_second: int = floori(float(Time.get_ticks_msec()) / 1000.0)
		if display_second != cooldown_display_second:
			cooldown_display_second = display_second
			_sync_quick_slots()
			if stats_panel.visible and stats_tabs.current_tab == 3:
				_sync_session_experience()
		_sync_hud_button_states()

## Drives the two map SubViewports on demand instead of leaving them on
## UPDATE_ALWAYS. Each requests a single redraw, so a hidden map costs nothing
## and a visible one refreshes fast enough to read as live.
func _update_map_viewports() -> void:
	var now: int = Time.get_ticks_msec()
	if minimap_frame.visible and now >= _minimap_refresh_msec:
		_minimap_refresh_msec = now + MINIMAP_REFRESH_MSEC
		_update_map_detail_levels()
		map_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
		# The marks are drawn over that image and follow the same camera, so
		# they are collected when it is redrawn and never while it is hidden.
		minimap_marker_overlay.set_marks(_collect_minimap_marks())
	if _day_night_active and now >= _day_night_refresh_msec:
		_day_night_refresh_msec = now + DAY_NIGHT_REFRESH_MSEC
		_apply_day_night()
	if full_map.visible and map_image.visible and now >= _full_map_refresh_msec:
		_full_map_refresh_msec = now + FULL_MAP_REFRESH_MSEC
		_update_full_map_focus()
		_update_map_detail_levels()
		if _full_map_cursor_inside:
			_update_full_map_cursor(_full_map_cursor_position)
		full_map_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
		# Refresh projected markers alongside the terrain, including visibility
		# changes when the player enters a different secret section.
		map_marker_overlay.set_live_marks(_collect_minimap_marks())
		map_marker_overlay.set_markers(_current_map_markers())
		map_marker_overlay.set_waypoints(_collect_map_waypoints())
		map_marker_overlay.queue_redraw()

## The character preview renders its own 3D scene. It only needs to run while
## the creation panel is on screen.
func _update_preview_viewport() -> void:
	var wanted: bool = creation_panel.visible
	if wanted == _preview_updates_enabled:
		return
	_preview_updates_enabled = wanted
	preview_viewport.render_target_update_mode = (SubViewport.UPDATE_ALWAYS
		if wanted else SubViewport.UPDATE_DISABLED)

func _request_map_redraw() -> void:
	_minimap_refresh_msec = 0
	_full_map_refresh_msec = 0

func _text_entry_active() -> bool:
	var focus: Control = get_viewport().gui_get_focus_owner()
	return focus is LineEdit or focus is TextEdit

## The new-character intro and the loading curtain both own the screen while
## they are up: the world takes no input and the exterior preloads wait.
func _world_input_blocked() -> bool:
	return character_intro.blocks_input() or arrival_curtain.blocks_input() \
		or (hud_workspace != null and hud_workspace.is_open())

const CAMERA_ACTIONS := ["camera_rotate_left", "camera_rotate_right", "camera_tilt_up", "camera_tilt_down"]

func _keyboard_camera_allowed() -> bool:
	return _ring_allowed() and get_viewport().gui_get_focus_owner() == null \
		and not (spell_wheel != null and spell_wheel.visible) \
		and not (technique_ring != null and technique_ring.visible) \
		and not (leaderboards_window != null and leaderboards_window.is_open()) \
		and not (_actor_hud_menu != null and _actor_hud_menu.visible)

func _update_keyboard_camera(delta: float) -> void:
	if not _keyboard_camera_allowed():
		return
	# Exact modifiers let a rebound Ctrl/Alt/Shift key coexist with its bare key.
	var axes := Vector2(
		float(Input.is_action_pressed("camera_rotate_right", true)) - float(Input.is_action_pressed("camera_rotate_left", true)),
		float(Input.is_action_pressed("camera_tilt_up", true)) - float(Input.is_action_pressed("camera_tilt_down", true)))
	camera_rig.handle_keyboard(axes, delta)

func _update_keyboard_movement() -> void:
	if _world_input_blocked():
		_stop_keyboard_movement()
		return
	if (spell_wheel != null and spell_wheel.visible) or (technique_ring != null and technique_ring.visible) \
			or _text_entry_active() or trade_panel.visible \
			or full_map.visible or (leaderboards_window != null and leaderboards_window.is_open()) \
			or console_panel.visible or settings_panel.visible or item_lists_panel.visible \
			or (_actor_hud_menu != null and _actor_hud_menu.visible) \
			or Input.is_key_pressed(KEY_ALT) or Input.is_key_pressed(KEY_CTRL):
		_stop_keyboard_movement()
		return
	var actor_value: Variant = AppState.actors.get(AppState.local_actor_id)
	var actor_node_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if not actor_value is Dictionary or not actor_node_value is ReplicatedActor3D \
			or not is_instance_valid(actor_node_value as ReplicatedActor3D):
		_stop_keyboard_movement()
		return
	if _movement_locked(Input.is_key_pressed(KEY_CTRL)):
		_stop_keyboard_movement()
		return
	var dto: Dictionary = actor_value as Dictionary
	var input_axes := _movement_axes_for_actions(
		Input.is_action_pressed("move_north"),
		Input.is_action_pressed("move_south"),
		Input.is_action_pressed("move_west"),
		Input.is_action_pressed("move_east"))
	var forward_input: int = input_axes.x
	var right_input: int = input_axes.y
	if forward_input == 0 and right_input == 0:
		_stop_keyboard_movement()
		return
	# Sample the current view every frame so rotating the camera also steers
	# held keys. The actor's facing follows its steps and never feeds back here.
	var direction: Vector2i = _camera_relative_tile_direction(forward_input, right_input)
	if direction == Vector2i.ZERO:
		_stop_keyboard_movement()
		return
	var origin := Vector2i(int(dto.get("x", 0)), int(dto.get("y", 0)))
	var now: int = Time.get_ticks_msec()
	var run: bool = Input.is_key_pressed(KEY_SHIFT)
	if Network.move_intent_enabled:
		_update_keyboard_intent(direction, run, now)
		return
	var close_to_goal: bool = maxi(absi(_keyboard_goal_tile.x - origin.x),
		absi(_keyboard_goal_tile.y - origin.y)) <= 1
	if _keyboard_moving and direction == _keyboard_direction and run == _keyboard_running \
			and not close_to_goal and now < _keyboard_refresh_msec:
		return
	var target: Vector2i = origin + direction * KEYBOARD_LOOKAHEAD_TILES
	exterior_stream.pending_walk.clear()
	var error: Error = Network.move_to(target, run)
	if error == OK:
		_keyboard_moving = true
		_keyboard_running = run
		_keyboard_direction = direction
		_keyboard_goal_tile = target
		_keyboard_refresh_msec = now + KEYBOARD_REFRESH_MSEC
	else:
		push_warning("keyboard MOVE_TO failed: " + error_string(error))
		_keyboard_moving = false

## Held-direction walking (keyboard_intent_v1, once the server takes it): the
## server steps the player at its own pace while a direction is held, so the
## direction is sent when it changes, when the server changes the epoch (a map
## change) and as a keep-alive, instead of a MOVE_TO every 360 ms.
func _update_keyboard_intent(direction: Vector2i, run: bool, now: int) -> void:
	if _keyboard_moving and _keyboard_intent_epoch == Network.move_intent_epoch \
			and direction == _keyboard_direction and run == _keyboard_running \
			and now < _keyboard_refresh_msec:
		return
	exterior_stream.pending_walk.clear()
	var error: Error = Network.move_intent(direction, run)
	if error == OK:
		_keyboard_moving = true
		_keyboard_running = run
		_keyboard_direction = direction
		_keyboard_goal_tile = Vector2i(-99999, -99999)
		_keyboard_intent_epoch = Network.move_intent_epoch
		_keyboard_refresh_msec = now + Network.move_intent_keepalive_msec
	else:
		push_warning("keyboard intent failed: " + error_string(error))
		_keyboard_moving = false

func _movement_axes_for_actions(north_pressed: bool, south_pressed: bool,
		west_pressed: bool, east_pressed: bool) -> Vector2i:
	var forward_input: int = (1 if north_pressed else 0) - (1 if south_pressed else 0)
	var right_input: int = (1 if east_pressed else 0) - (1 if west_pressed else 0)
	return Vector2i(forward_input, right_input)

func _camera_relative_tile_direction(forward_input: int, right_input: int) -> Vector2i:
	var forward: Vector3 = -camera_rig.camera.global_basis.z
	var right: Vector3 = camera_rig.camera.global_basis.x
	forward.y = 0.0
	right.y = 0.0
	var movement: Vector3 = forward.normalized() * clampi(forward_input, -1, 1) \
		+ right.normalized() * clampi(right_input, -1, 1)
	if movement.is_zero_approx():
		return Vector2i.ZERO
	# Combine the keys before snapping to the server's eight tile directions.
	# The adapter accounts for maps with either orientation of the server Y axis.
	var yaw: float = atan2(-movement.x, -movement.z)
	var direction := Vector2i.ZERO
	var smallest_angle := INF
	for candidate: Vector2i in TILE_DIRECTIONS:
		var candidate_yaw: float = adapter.direction_to_godot(candidate)
		var difference: float = absf(wrapf(candidate_yaw - yaw, -PI, PI))
		if difference < smallest_angle:
			smallest_angle = difference
			direction = candidate
	return direction

func _stop_keyboard_movement() -> void:
	if not _keyboard_moving:
		return
	if _keyboard_intent_epoch >= 0:
		# A release: the server stops the player where it has them.
		var released: Error = Network.move_intent(Vector2i.ZERO)
		if released != OK and released != ERR_UNAVAILABLE:
			push_warning("keyboard release failed: " + error_string(released))
		_clear_keyboard_movement_tracking()
		return
	var actor_value: Variant = AppState.actors.get(AppState.local_actor_id)
	if actor_value is Dictionary:
		var dto: Dictionary = actor_value as Dictionary
		var origin := Vector2i(int(dto.get("x", 0)), int(dto.get("y", 0)))
		var error: Error = Network.move_to(origin, false)
		if error != OK:
			push_warning("keyboard stop failed: " + error_string(error))
	_clear_keyboard_movement_tracking()

func _clear_keyboard_movement_tracking() -> void:
	_keyboard_moving = false
	_keyboard_running = false
	_keyboard_direction = Vector2i.ZERO
	_keyboard_goal_tile = Vector2i(-99999, -99999)
	_keyboard_refresh_msec = 0
	_keyboard_intent_epoch = -1

func _clear_local_turn_prediction() -> void:
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if actor_value is ReplicatedActor3D and is_instance_valid(actor_value as ReplicatedActor3D):
		(actor_value as ReplicatedActor3D).clear_turn_prediction()

## Q and E ask the server to turn. The rendered facing comes from the actor
## command the server broadcasts in reply, which is also what makes the turn
## visible to every other player; the local rotation below is only a prediction
## that reply confirms. Nothing is decided here.
func _turn_local_actor(left: bool) -> void:
	var error: Error = Network.turn(left)
	if error != OK:
		push_warning("turn failed: " + error_string(error))
		return
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if actor_value is ReplicatedActor3D and is_instance_valid(actor_value as ReplicatedActor3D):
		(actor_value as ReplicatedActor3D).predict_turn(PI / 4.0 if left else -PI / 4.0)

func _apply_connection_launch_options(arguments: PackedStringArray) -> void:
	_dev_plain_tcp = arguments.has("--dev-plain-tcp")
	host_edit.text = "127.0.0.1" if _dev_plain_tcp else "game.rabbitlandsgame.com"
	port_edit.value = 2000 if _dev_plain_tcp else 2001
	for argument: String in arguments:
		if argument.begins_with("--server="):
			host_edit.text = argument.trim_prefix("--server=")
		elif argument.begins_with("--port="):
			var value := argument.trim_prefix("--port=")
			if value.is_valid_int() and int(value) > 0 and int(value) <= 65535:
				port_edit.value = int(value)

func _on_connect_pressed() -> void:
	if AppState.connection_state != "disconnected":
		Network.disconnect_from_server()
		return
	connect_button.disabled = true
	login_button.disabled = true
	status_label.text = "Connecting…"
	_save_hud_settings()
	var error := Network.connect_to_server(
		host_edit.text.strip_edges(), int(port_edit.value),
		not _dev_plain_tcp, _trusted_certificate_path())
	if error != OK:
		status_label.text = "Connection failed: " + error_string(error)
		connect_button.disabled = false

## A development server signs its own certificate, which no trust store will
## accept. If the player has dropped that certificate next to their settings,
## it is trusted in addition to the system store - which is different from
## trusting anything, and keeps verification on for real servers.
func _trusted_certificate_path() -> String:
	var path := "user://eloria-server.crt"
	return path if FileAccess.file_exists(path) else ""

func _on_new_character_pressed() -> void:
	if AppState.connection_state != "connected":
		status_label.text = "Connect to the server before creating a character."
		return
	_set_login_screen_visible(false)
	creation_panel.show()
	_refresh_creation_preview()
	character_intro.prewarm(MapRegistry.resolve(map_registry, NewCharacterIntroScript.MAP), world_root)

func _on_creation_back_pressed() -> void:
	character_intro.cancel()
	_clear_pending_creation()
	creation_panel.hide()
	_set_login_screen_visible(true)

## The painted scenery and its animation belong only to the login screen. Hiding
## both together means the ambient pass has no draw cost during creation or in
## crowded gameplay scenes.
func _set_login_screen_visible(value: bool) -> void:
	login_panel.visible = value
	login_background.visible = value
	login_logo.visible = value


func _sync_login_logo_visibility() -> void:
	login_logo.visible = login_panel.visible
	login_background.visible = login_panel.visible
	if is_instance_valid(start_screen_backdrop):
		start_screen_backdrop.set_active(login_panel.visible)

func _on_create_race_item_selected(_index: int) -> void:
	_populate_creation_sexes()
	_populate_creation_choices(true)
	_refresh_creation_preview()

func _on_create_gender_item_selected(_index: int) -> void:
	_populate_creation_choices()
	_refresh_creation_preview()

func _on_create_appearance_changed(_value: float) -> void:
	_refresh_creation_preview()

func _on_randomize_creation_pressed() -> void:
	_randomize_creation_appearance()

## Rolls race and sex before the seven appearance selectors so every press can
## produce a genuinely different character silhouette. Calling and account
## fields deliberately live outside this list, and selecting without emitting
## each control's signal lets the completed look rebuild the preview once.
## Tests can pass a seeded generator without changing the generator used by the
## live button or the one-time initial roll.
func _randomize_creation_appearance(rng: RandomNumberGenerator = null) -> void:
	var source := rng if rng != null else _creation_appearance_rng
	if create_race.item_count > 0:
		create_race.select(source.randi_range(0, create_race.item_count - 1))
		_populate_creation_sexes()
	if create_gender.item_count > 0:
		create_gender.select(source.randi_range(0, create_gender.item_count - 1))
	_populate_creation_choices(true)
	var selectors: Array[OptionButton] = [
		%CreateSkin, %CreateHair, %CreateHairColor, %CreateEyes,
		%CreateShirt, %CreatePants, %CreateBoots,
	]
	var culture := AppearanceVariants.culture_for_actor_type(create_gender.get_selected_id())
	for selector: OptionButton in selectors:
		if selector.item_count <= 0:
			continue
		if selector == %CreateEyes and AMBER_EYED_CULTURES.has(culture):
			# One draw either way, so a seed rolls the same sequence of choices.
			var amber: int = AMBER_EYES[source.randi_range(0, AMBER_EYES.size() - 1)]
			selector.select(selector.get_item_index(amber))
			continue
		selector.select(source.randi_range(0, selector.item_count - 1))
	_refresh_creation_preview()

func _on_create_pressed() -> void:
	var username := create_name.text.strip_edges()
	var password := create_password.text
	if username.length() < 3 or username.length() > 20:
		create_status.text = "Name must contain 3–20 characters."
		return
	if password.length() < 4:
		create_status.text = "Password must contain at least 4 characters."
		return
	if password != create_confirm.text:
		create_status.text = "Passwords do not match."
		return
	pending_create_username = username
	pending_create_password = password
	create_status.text = "Creating character…"
	var appearance: Dictionary = _creation_appearance()
	appearance["actor_type"] = create_gender.get_selected_id()
	var error := Network.create_character(username, password, appearance,
		CreationArchetypes.id_at(selected_creation_class))
	if error != OK:
		create_status.text = "Creation request failed: " + error_string(error)
		_clear_pending_creation()

func _on_character_created() -> void:
	# Only an accepted creation in this session arms the arrival; ordinary
	# logins, reconnects and later map changes never replay it.
	if pending_create_username.is_empty():
		return
	character_intro.prewarm(MapRegistry.resolve(map_registry, NewCharacterIntroScript.MAP), world_root)
	character_intro.arm(main_viewport)
	create_status.text = "Character created. Entering Eloria…"
	user_edit.text = pending_create_username
	var username := pending_create_username
	var password := pending_create_password
	create_password.clear()
	create_confirm.clear()
	_clear_pending_creation()
	var error := Network.login(username, password)
	if error != OK:
		create_status.text = "Created, but login failed to send: " + error_string(error)
		character_intro.cancel()
		creation_panel.hide()
		_set_login_screen_visible(true)

func _on_character_creation_failed(message: String) -> void:
	create_status.text = "Creation failed: " + message
	_clear_pending_creation()

func _clear_pending_creation() -> void:
	pending_create_username = ""
	pending_create_password = ""

func _refresh_creation_preview() -> void:
	if is_instance_valid(preview_actor):
		preview_actor.queue_free()
	preview_actor = ReplicatedActor3D.new()
	preview_root.add_child(preview_actor)
	var actor_type: int = create_gender.get_selected_id()
	var appearance: Dictionary = _creation_appearance()
	# Modified 2026-08-28 for Eloria Client: the creation bytes are equipment
	# visual ids now, so the preview resolves them exactly as the world does.
	# Building the dto by hand here would preview a different wardrobe from the
	# one the character spawns wearing.
	var dto := _presentation_dto({"actor_id": 0, "x": 0, "y": 0, "rotation": 0,
		"actor_type": actor_type, "kind": 1, "name": "",
		"appearance": appearance})
	# A class is authoritative for starting inventory but remains independent of
	# race and sex.  Its creation-screen equipment is a representative preview;
	# the same selected class id is sent separately from the eight appearance
	# bytes when the player creates the character.
	dto["equipment_visuals"] = (_creation_class_loadout()
		if creation_class_gear_visible else {})
	var model_id := _model_for_actor(dto)
	var model_config: Dictionary = models.get(model_id, {}) as Dictionary
	var errors := preview_actor.configure(dto,
		CoordinateAdapter.new({"walkingHeight": 0.0}), model_config,
		_animation_for_model(model_config), equipment_config)
	preview_actor.set_nameplate_visible(false)
	preview_actor.apply_render_quality(LookProfile.quality(), true)
	_frame_preview_actor()
	if not errors.is_empty():
		create_status.text = "Preview warnings: " + "; ".join(errors)
	else:
		create_status.text = "%s starting items will be granted for any race. Drag to rotate." % \
			creation_class_title.text

func _populate_creation_races() -> void:
	var races: Dictionary = {}
	for option: Dictionary in creation_options:
		var config: Dictionary = models.get(str(option.get("model", "")), {})
		var culture := str(config.get("culture", ""))
		var label := str(option.get("label", "")).trim_suffix(" Female").trim_suffix(" Male")
		races[culture] = label
	var cultures: Array = races.keys()
	cultures.sort_custom(func(a: String, b: String) -> bool:
		return str(races[a]).naturalnocasecmp_to(str(races[b])) < 0)
	create_race.clear()
	for culture: String in cultures:
		create_race.add_item(str(races[culture]))
		var index := create_race.item_count - 1
		create_race.set_item_metadata(index, culture)
		if culture == "luminous":
			create_race.select(index)

func _populate_creation_sexes() -> void:
	var previous := str(create_gender.get_selected_metadata()) if create_gender.item_count > 0 else "female"
	var culture := str(create_race.get_selected_metadata())
	create_gender.clear()
	for option: Dictionary in creation_options:
		var config: Dictionary = models.get(str(option.get("model", "")), {})
		if str(config.get("culture", "")) != culture:
			continue
		var sex := str(config.get("gender", ""))
		create_gender.add_item(sex.capitalize(), int(option.get("actorType", 1)))
		var index := create_gender.item_count - 1
		create_gender.set_item_metadata(index, sex)
		if sex == previous:
			create_gender.select(index)

func _populate_creation_choices(reset_skin := false) -> void:
	var culture := AppearanceVariants.culture_for_actor_type(create_gender.get_selected_id())
	AppearanceChoices.populate(%CreateSkin, AppearanceChoices.options("skin", culture))
	if reset_skin and culture != "luminous":
		%CreateSkin.select(%CreateSkin.get_item_index(0))
	AppearanceChoices.populate(%CreateEyes, AppearanceChoices.options("eyes"))
	if reset_skin and AMBER_EYED_CULTURES.has(culture):
		# A new Orun or Mycelari opens on amber eyes. Only the creation default:
		# a stored character keeps its eye byte.
		%CreateEyes.select(%CreateEyes.get_item_index(AMBER_EYES[0]))
	AppearanceChoices.populate(%CreateHair, AppearanceChoices.options("hair"))
	AppearanceChoices.populate(%CreateHairColor, AppearanceChoices.options("hair_color"))
	AppearanceChoices.populate(%CreateShirt, AppearanceChoices.options("wardrobe", culture, AppearanceVariants.PART_SHIRT))
	AppearanceChoices.populate(%CreatePants, AppearanceChoices.options("wardrobe", culture, AppearanceVariants.PART_PANTS))
	AppearanceChoices.populate(%CreateBoots, AppearanceChoices.options("wardrobe", culture, AppearanceVariants.PART_BOOTS))

func _creation_class_buttons() -> Array[Button]:
	var buttons: Array[Button] = [
		%ClassChoice0, %ClassChoice1, %ClassChoice2, %ClassChoice3]
	return buttons

func _configure_creation_classes() -> void:
	show_creation_class_gear.set_pressed_no_signal(creation_class_gear_visible)
	var buttons := _creation_class_buttons()
	for index: int in range(buttons.size()):
		var entry: Dictionary = CreationArchetypes.at(index)
		var button: Button = buttons[index]
		button.tooltip_text = "%s — %s" % [
			str(entry.get("label", "Class")), str(entry.get("tagline", ""))]
		button.icon = CreationClassIcons.icon_for(str(entry.get("key", "")))
		button.text = ("" if button.icon != null
			else str(entry.get("label", "?")).left(1))
	_update_creation_class_ui()

func _configure_creation_layout() -> void:
	create_status.size_flags_vertical = Control.SIZE_FILL
	var form := get_node("CreationPanel/Columns/FormPanel/Form") as VBoxContainer
	var fields := VBoxContainer.new()
	fields.name = "CreationFields"
	fields.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	fields.add_theme_constant_override("separation", 6)
	var scroll := ScrollContainer.new()
	scroll.name = "CreationFieldsScroll"
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	form.add_child(scroll)
	form.move_child(scroll, 0)
	scroll.add_child(fields)
	for child: Node in form.get_children():
		if child != scroll and child.name != "Actions" and child != create_status:
			child.reparent(fields)
	(get_node("%FormPanel") as Control).custom_minimum_size.x = 520
	for picker: OptionButton in [get_node("%CreateSkin"), get_node("%CreateHair"),
			get_node("%CreateEyes"), get_node("%CreateHairColor"), get_node("%CreateShirt"),
			get_node("%CreatePants"), get_node("%CreateBoots")]:
		picker.custom_minimum_size.x = 180
		picker.item_selected.connect(func(index: int) -> void:
			picker.tooltip_text = picker.get_item_text(index))
	var rail := get_node("%ClassRail") as Control
	var class_content := rail.get_node("ClassContent") as Control
	var class_scroll := ScrollContainer.new()
	class_scroll.name = "ClassScroll"
	class_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	rail.add_child(class_scroll)
	class_content.reparent(class_scroll)
	class_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL

func _update_creation_class_ui() -> void:
	selected_creation_class = posmod(selected_creation_class,
		CreationArchetypes.count())
	var entry: Dictionary = CreationArchetypes.at(selected_creation_class)
	creation_class_title.text = str(entry.get("label", "Adventurer"))
	creation_class_tagline.text = str(entry.get("tagline", ""))
	creation_class_description.text = str(entry.get("description", ""))
	creation_class_starting_items.text = str(entry.get("starting_items", ""))
	creation_class_page.text = "%d / %d" % [
		selected_creation_class + 1, CreationArchetypes.count()]
	var buttons := _creation_class_buttons()
	for index: int in range(buttons.size()):
		buttons[index].set_pressed_no_signal(index == selected_creation_class)

func _creation_class_loadout() -> Dictionary:
	return CreationArchetypes.loadout_at(selected_creation_class)

func _on_creation_class_chosen(index: int) -> void:
	_set_creation_class(index)

func _on_creation_class_rotated(direction: int) -> void:
	_set_creation_class(selected_creation_class + direction)

func _set_creation_class(index: int) -> void:
	selected_creation_class = posmod(index, CreationArchetypes.count())
	_update_creation_class_ui()
	if is_instance_valid(preview_actor):
		preview_actor.apply_equipment_visuals(_creation_class_loadout()
			if creation_class_gear_visible else {})
		_frame_preview_actor()
	create_status.text = "%s selected. These starting items apply to every race." % \
		creation_class_title.text

func _on_creation_class_gear_toggled(enabled: bool) -> void:
	creation_class_gear_visible = enabled
	if is_instance_valid(preview_actor):
		preview_actor.apply_equipment_visuals(_creation_class_loadout() if enabled else {})
		_frame_preview_actor()
	create_status.text = ("Class gear preview shown."
		if enabled else "Class gear hidden so you can inspect wardrobe colours.")

func _creation_appearance() -> Dictionary:
	return {
		"skin": %CreateSkin.get_selected_id(),
		"hair": AppearanceVariants.pack_hair(%CreateHair.get_selected_id(), %CreateHairColor.get_selected_id()),
		"eyes": %CreateEyes.get_selected_id(),
		"head": 0,
		# Reinstated 2026-09-02 for Eloria Client: the race bodies' painted
		# outfits are split into their own wardrobe surfaces now, so these
		# three bytes recolour the shirt, the trousers and the boots the way
		# the create packet always intended.
		"shirt": %CreateShirt.get_selected_id(), "pants": %CreatePants.get_selected_id(),
		"boots": %CreateBoots.get_selected_id(),
	}

func _on_character_preview_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse_button: InputEventMouseButton = event as InputEventMouseButton
		if not mouse_button.pressed:
			return
		if mouse_button.button_index == MOUSE_BUTTON_WHEEL_UP:
			preview_distance = maxf(1.5, preview_distance - 0.3)
		elif mouse_button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			preview_distance = minf(7.0, preview_distance + 0.3)
		else:
			return
		_update_preview_camera()
		preview_container.accept_event()
	elif event is InputEventMouseMotion:
		var mouse_motion: InputEventMouseMotion = event as InputEventMouseMotion
		if (mouse_motion.button_mask & (MOUSE_BUTTON_MASK_LEFT |
				MOUSE_BUTTON_MASK_RIGHT)) == 0:
			return
		preview_yaw -= mouse_motion.relative.x * 0.01
		preview_pitch = clampf(preview_pitch + mouse_motion.relative.y * 0.008,
			-0.35, 0.65)
		_update_preview_camera()
		preview_container.accept_event()

## Put the camera, and the disc, where the body actually stands.
func _frame_preview_actor() -> void:
	if not is_instance_valid(preview_actor):
		return
	var stand: Vector3 = preview_actor.position
	preview_focus = Vector3(stand.x, 1.0, stand.z)
	var ground: Node3D = preview_root.get_node_or_null("PreviewGround") as Node3D
	if ground != null:
		ground.position = Vector3(stand.x, ground.position.y, stand.z)
	var styled_stage: Node3D = preview_root.get_node_or_null("OldcraftStage") as Node3D
	if styled_stage != null:
		styled_stage.position = Vector3(stand.x, 0.0, stand.z)
	_update_preview_camera()

func _update_preview_camera() -> void:
	if preview_camera == null:
		return
	var focus := preview_focus
	var horizontal: float = cos(preview_pitch) * preview_distance
	preview_camera.position = focus + Vector3(sin(preview_yaw) * horizontal,
		sin(preview_pitch) * preview_distance, cos(preview_yaw) * horizontal)
	preview_camera.look_at(focus)
	_update_preview_lights()

## Modified 2026-08-28 for Eloria Client: the creation preview used to be lit by
## one fixed shadow-casting sun in a viewport with no environment.  Whatever the
## sun pointed away from rendered black, so the face was in shadow the moment
## the panel opened and only the side the player rotated *away* from was ever
## visible.  The rig now orbits with the camera - key over the viewer's
## shoulder, fill opposite it, rim behind the model - on top of the ambient the
## preview environment contributes, so no facing is ever unlit.
func _update_preview_lights() -> void:
	_aim_preview_light(preview_key_light, preview_yaw + 0.55,
		clampf(preview_pitch + 0.50, 0.20, 1.10))
	_aim_preview_light(preview_fill_light, preview_yaw - 1.95, 0.22)
	_aim_preview_light(preview_rim_light, preview_yaw + PI, 0.42)

func _aim_preview_light(light: DirectionalLight3D, yaw: float, pitch: float) -> void:
	# A DirectionalLight3D shines down its own -Z, so aiming it at the focus
	# from a point on the orbit is the same as choosing a light direction.
	if light == null:
		return
	var horizontal: float = cos(pitch)
	var source := Vector3(sin(yaw) * horizontal, sin(pitch), cos(yaw) * horizontal)
	light.look_at_from_position(source * 4.0 + Vector3(0.0, 1.0, 0.0),
		Vector3(0.0, 1.0, 0.0), Vector3.UP)

func _on_login_pressed() -> void:
	character_intro.cancel()
	if AppState.authenticated:
		return
	if AppState.connection_state != "connected":
		status_label.text = "Connect to the server first."
		return
	if user_edit.text.is_empty() or password_edit.text.is_empty():
		status_label.text = "Enter username and password."
		return
	login_button.disabled = true
	status_label.text = "Authenticating…"
	var error := Network.login(user_edit.text, password_edit.text)
	password_edit.clear()
	if error != OK:
		status_label.text = "Login send failed: " + error_string(error)
		login_button.disabled = false
		return
	# Up before LOG_IN_OK: it and CHANGE_MAP arrive in one burst, and the world
	# is built behind the curtain, never in front of the player.
	arrival_curtain.begin("Signing in…")
	arrival_curtain.set_progress(0.05)

func _on_login_submitted(_text: String) -> void:
	if AppState.connection_state == "disconnected":
		_on_connect_pressed()
	elif AppState.connection_state == "connected":
		_on_login_pressed()

func _on_map_button_pressed() -> void:
	_toggle_full_map()
	_sync_hud_button_states(true)

func _on_walk_button_pressed() -> void:
	# It is showing the attack icon, so it does what the attack icon does.
	if _alt_attack_preview and _interaction_mode != "attack":
		_on_attack_button_pressed()
		return
	_interaction_mode = "walk"
	var local_actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	if bool(local_actor.get("sitting", false)):
		var error: Error = Network.set_sitting(false)
		if error != OK:
			push_warning("STAND_UP failed: " + error_string(error))
	_sync_hud_button_states(true)

func _on_sit_button_pressed() -> void:
	var local_actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	var error: Error = Network.set_sitting(not bool(local_actor.get("sitting", false)))
	if error != OK:
		push_warning("SIT_DOWN failed: " + error_string(error))

func _on_attack_button_pressed() -> void:
	_interaction_mode = "attack"
	_attack_selected_actor()
	_sync_hud_button_states(true)

## Asks the server to describe the selected player. The window that opens is
## the server's reply and nothing else: the client does not remember what it
## asked about, because the reply names the actor itself.
func _on_look_button_pressed() -> void:
	var actor_id: int = AppState.selected_actor_id
	if not _is_tradeable_player(actor_id, AppState.actors.get(actor_id, {})):
		return
	var error: Error = Network.look_at_player(actor_id)
	if error != OK:
		push_warning("GET_PLAYER_INFO failed: " + error_string(error))

## The trade icon is a mode, as it is in Eternal Lands: it arms trade, the
## pointer turns to the trade glyph over players, and the next click on one
## asks them (`_actor_click_action`). A player already selected is asked at
## once. It used to be greyed out until a player was selected, which read as
## broken. Esc or the walk icon puts the mode down; right-click cycles onward.
func _on_trade_button_pressed() -> void:
	_interaction_mode = "trade"
	_cursor_refresh_msec = 0
	var actor_id: int = AppState.selected_actor_id
	var dto: Dictionary = AppState.actors.get(actor_id, {})
	if _is_tradeable_player(actor_id, dto):
		print_debug("trade_input command=TRADE_WITH target_actor_id=", actor_id,
			" redacted_bytes=not_sensitive")
		var error: Error = Network.trade_with(actor_id)
		if error != OK:
			push_warning("TRADE_WITH failed: " + error_string(error))
	_sync_hud_button_states(true)

func _reset_world_action() -> void:
	_interaction_mode = "walk"
	_set_inventory_tool("grab")
	_cursor_refresh_msec = 0
	_sync_hud_button_states(true)

## Use the click handler's target priority and capabilities so cycling cannot
## arm a tool that does nothing at this position. Move always remains a way
## back to the normal contextual pointer.
func _available_world_actions_at(viewport_position: Vector2) -> Array[String]:
	var actions: Array[String] = ["walk"]
	var actor_id: int = _pick_actor(viewport_position)
	if actor_id >= 0:
		if actor_id == AppState.local_actor_id and _ground_bag_below_player() >= 0:
			actions.append("pick")
		var dto: Dictionary = AppState.actors.get(actor_id, {})
		for action: String in MouseCursors.WORLD_ACTIONS:
			if action != "walk" and _actor_click_action(actor_id, dto, false, action) == action:
				actions.append(action)
		return actions
	if _pick_ground_bag(viewport_position) >= 0:
		actions.append("pick")
		return actions
	var map_object: MapObject3D = _pick_map_object(viewport_position)
	if map_object != null:
		actions.append("harvest" if map_object.is_harvestable() else "use")
		actions.append("look")
	return actions

func _cycle_world_action(viewport_position: Vector2) -> void:
	var actions: Array[String] = _available_world_actions_at(viewport_position)
	var index: int = MouseCursors.WORLD_ACTIONS.find(_interaction_mode)
	for step: int in range(1, MouseCursors.WORLD_ACTIONS.size() + 1):
		var action: String = MouseCursors.WORLD_ACTIONS[
			(index + step) % MouseCursors.WORLD_ACTIONS.size()]
		if action in actions:
			_interaction_mode = action
			break
	match _interaction_mode:
		"use":
			_set_inventory_tool("use")
		"look":
			_set_inventory_tool("inspect")
		"walk":
			_set_inventory_tool("grab")
	_cursor_refresh_msec = 0
	_update_action_cursor()
	_sync_hud_button_states(true)

func _on_chat_button_pressed() -> void:
	_show_chat_input()

func _build_chat_surfaces() -> void:
	system_chat_hud = ChatHudScript.new()
	system_chat_hud.name = "SystemChatWindow"
	system_chat_hud.feed_role = "system"
	system_chat_hud.preferences_path = chat_hud.preferences_path
	game_view.add_child(system_chat_hud)
	for surface: PanelContainer in [chat_hud, system_chat_hud]:
		surface.z_index = 20
		surface.options_requested.connect(func() -> void: settings_window.open_tab("Chat"))
		surface.configuration_changed.connect(_on_chat_configuration_changed)
		surface.urls_requested.connect(func() -> void: reference_window.call("open_urls"))
		surface.log_requested.connect(func() -> void:
			if not console_panel.visible:
				_toggle_console()
			chat_log_tabs.select("system" if surface == system_chat_hud else "chat")
			_sync_console())
	chat_log_tabs = ChatLogTabsScript.new()
	var content := console_panel.get_node("Content")
	console_output.context_menu_enabled = true
	console_output.shortcut_keys_enabled = true
	console_output.mouse_default_cursor_shape = Control.CURSOR_IBEAM
	console_output.tooltip_text = "Drag to select text. Ctrl+C or right-click → Copy."
	var urls_button := Button.new()
	urls_button.name = "URLs"
	urls_button.text = "URLs"
	urls_button.tooltip_text = "Links seen this session; F2 opens the latest"
	urls_button.pressed.connect(func() -> void: reference_window.call("open_urls"))
	var log_header := content.get_node("Header")
	# Keep actions beside the title, clear of HUD rails at the right edge.
	var log_title: Label = log_header.get_node("Title")
	log_title.text = "CHAT LOG · ~ to close"
	log_title.tooltip_text = "Full session history. Press ~ to close."
	log_title.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	log_header.add_child(urls_button)
	log_header.move_child(urls_button, 1)
	content.add_child(chat_log_tabs)
	content.move_child(chat_log_tabs, 1)
	chat_log_tabs.tab_selected.connect(func(_key: String) -> void: _sync_console())
	chat_log_tabs.sync(AppState.active_channels, AppState.chat_history)
	for line: Dictionary in AppState.chat_lines:
		chat_hud.remember_peer(ChatMessages.peer(line))
	_on_chat_configuration_changed("", null)

func _on_chat_configuration_changed(key: String, _value: Variant) -> void:
	var combined := bool(chat_hud.options.get("combined", false))
	if key == "combined":
		_chat_tab = "all"
		chat_hud.select_tab("all")
	system_chat_hud.set_feed_suppressed(combined)
	_sync_chat()
	_refresh_unified_settings()

func _on_invasion_assistant_command_requested(command: String) -> void:
	var error := Network.send_chat(command)
	if error != OK:
		AppState.append_local_message(
			"Invasion assistant request failed: %s" % error_string(error))

func _show_chat_input() -> void:
	chat_hud.open_chat(true)
	WindowStackScript.activate(chat_hud)
	chat_input.show()
	chat_input.grab_focus()
	_sync_hud_button_states(true)

func _hide_chat_input() -> void:
	chat_input.release_focus()
	chat_hud.finish_typing()
	_sync_hud_button_states(true)

## Reacts to a map panel opening or closing. _update_map_viewports() owns the
## redraw schedule; this only ever idles a hidden viewport or asks a freshly
## shown one for its first frame. Setting UPDATE_ALWAYS here put a visible
## minimap back on full-rate world rendering for up to a whole throttle
## interval, which is exactly the cost the throttle exists to remove.
func _sync_map_viewport_activity() -> void:
	map_viewport.render_target_update_mode = (
		SubViewport.UPDATE_ONCE if minimap_frame.visible
		else SubViewport.UPDATE_DISABLED)
	full_map_viewport.render_target_update_mode = (
		SubViewport.UPDATE_ONCE if full_map.visible and map_image.visible
		else SubViewport.UPDATE_DISABLED)


func _toggle_full_map() -> void:
	if full_map.visible:
		full_map.hide()
		_sync_map_viewport_activity()
		return
	console_panel.hide()
	_close_settings()
	_show_current_map_view()
	full_map.show()
	if bool(AppState.lantern_tutorial.get("active",false)):
		Network.tutorial_ui(1)
	_request_map_redraw()
	_sync_map_viewport_activity()

func _toggle_minimap() -> void:
	_minimap_visible = not minimap_frame.visible
	minimap_frame.visible = _minimap_visible
	_request_map_redraw()
	_sync_map_viewport_activity()
	_save_hud_settings()

func _toggle_console() -> void:
	if console_panel.visible:
		console_panel.hide()
		return
	full_map.hide()
	_close_settings()
	console_diagnostics_button.set_pressed_no_signal(false)
	_on_console_diagnostics_toggled(false)
	_sync_console()
	_sync_diagnostics()
	_layout_full_window_views()
	console_panel.show()
	chat_hud.input.release_focus()

## World annotations belong to the covered scene beneath the map and console.
## Follow visibility signals so close buttons, Escape and direct show/hide agree.
func _sync_world_overlay_visibility() -> void:
	var world_visible := not full_map.visible and not console_panel.visible
	_world_text_overlay.visible = world_visible
	_floating_feedback_layer.visible = world_visible
	_update_actor_resource_overlay()

## The console panel shows either the session message history or the protocol
## diagnostics. Undecoded packets and decode errors were reduced into AppState
## and emitted with no listener at all, so every gap in the client's protocol
## coverage failed completely silently; this is where they surface.
func _on_console_diagnostics_toggled(enabled: bool) -> void:
	console_output.visible = not enabled
	diagnostics_output.visible = enabled
	chat_log_tabs.visible = not enabled
	if enabled:
		_sync_diagnostics()

func _sync_diagnostics() -> void:
	if diagnostics_output == null or not diagnostics_output.visible:
		return
	var lines: Array[String] = []
	lines.append("[b]Undecoded server opcodes this session[/b]")
	if AppState.unknown_packets.is_empty():
		lines.append("  none")
	else:
		var opcodes: Array = AppState.unknown_packets.keys()
		opcodes.sort()
		for raw_opcode: Variant in opcodes:
			var record: Dictionary = AppState.unknown_packets[raw_opcode] as Dictionary
			lines.append("  %3d  x%-5d  last payload %d bytes, %s ago" % [
				int(raw_opcode), int(record.get("count", 0)),
				int(record.get("size", 0)),
				_elapsed_text(int(record.get("msec", 0)))])
		lines.append("  total undecoded packets: %d" % AppState.unknown_packet_count)
	lines.append("
[b]Recent decode errors[/b]")
	if AppState.recent_protocol_errors.is_empty():
		lines.append("  none")
	else:
		for index: int in range(AppState.recent_protocol_errors.size() - 1, -1, -1):
			var failure: Dictionary = AppState.recent_protocol_errors[index]
			lines.append("  %3d  %s  (%d bytes, %s ago)" % [
				int(failure.get("command", -1)), str(failure.get("error", "")),
				int(failure.get("size", 0)),
				_elapsed_text(int(failure.get("msec", 0)))])
	lines.append("
[b]World objects[/b]")
	lines.append("  server objects on this map: %d" % AppState.map_objects.size())
	if _ungrounded_map_objects.is_empty():
		lines.append("  all of them sit on the rendered navigation surface")
	else:
		lines.append("  [color=#ffb066]%d have no navigation surface beneath them[/color]"
			% _ungrounded_map_objects.size())
		var listed: int = 0
		for raw_object_id: Variant in _ungrounded_map_objects:
			if listed >= 8:
				lines.append("    …")
				break
			lines.append("    %d  %s" % [int(raw_object_id),
				str(_ungrounded_map_objects[raw_object_id])])
			listed += 1
	lines.append("
[b]Connection[/b]")
	lines.append("  state: %s%s" % [AppState.connection_state,
		"  (reconnect attempt %d)" % Network.reconnect_attempt()
		if Network.is_reconnecting() else ""])
	lines.append("  server clock: %s" % (
		"%d (synchronised %s ago)" % [AppState.server_timestamp,
			_elapsed_text(AppState.last_clock_sync_msec)]
		if AppState.last_clock_sync_msec > 0 else "never synchronised"))
	lines.append("  game minute: %d (%02d:%02d)" % [AppState.game_minute,
		AppState.game_minute / 60, AppState.game_minute % 60])
	diagnostics_output.text = "
".join(lines)

func _elapsed_text(msec: int) -> String:
	if msec <= 0:
		return "unknown"
	var seconds: int = maxi(0, (Time.get_ticks_msec() - msec) / 1000)
	if seconds < 60:
		return "%ds" % seconds
	return "%dm%02ds" % [seconds / 60, seconds % 60]

func _on_options_pressed() -> void:
	settings_window.toggle()
	if settings_window.is_open():
		console_panel.hide()
	audio_director.play("ui_click" if settings_window.is_open() else "ui_close")

## Compatibility entry point for existing callers; Options and Ctrl+O open
## the same tabbed settings window.
func _on_more_settings_pressed() -> void:
	_on_options_pressed()

## Reuse the original scene controls and their handlers, then retire their
## popup shells. Every entry point now shares settings_window.panel.
func _configure_unified_settings() -> void:
	var old_panel := get_node("%SettingsControls") as Control
	var content := old_panel.get_node("Content")
	for section_and_rows: Array in [
			["HUD", ["UiScaleRow"]],
			["Minimap", ["MinimapHint", "MinimapSizeRow"]],
			["Graphics", ["ShowThroughObstacles"]],
			["Audio", ["SoundRow", "AudioCreditsButton"]],
			["Inventory", ["EquipmentSideRow"]],
			["Gameplay", ["ReferenceButton"]]]:
		var page: VBoxContainer = settings_window.page_body(str(section_and_rows[0]))
		for row_name: String in section_and_rows[1]:
			var row := content.get_node(row_name) as Control
			row.reparent(page, false)
			if row_name == "UiScaleRow":
				page.move_child(row, 0)
	settings_window.add_audio_controls()
	for category: String in audio_director.category_volumes:
		settings_window.restore_value("audio_" + category,
			audio_director.category_volumes[category])
	# The banner controls themselves retain their names and persisted keys.
	var actor_hud_menu := get_node("%BannerControls") as Control
	var banners_page: VBoxContainer = settings_window.page_body("Banners")
	(%DisableMenu as CheckBox).text = "Disable character right-click menu"
	var mount_heading := Label.new()
	mount_heading.text = "Mount status below character bars"
	banners_page.add_child(mount_heading)
	for key: String in MountControls.OPTION_LABELS:
		settings_window._add_toggle(banners_page,
			"mount_banner_" + key, MountControls.OPTION_LABELS[key], true)
	var character_heading := Label.new()
	character_heading.text = "Character banner"
	banners_page.add_child(character_heading)
	(actor_hud_menu.get_node("Options") as Control).reparent(banners_page, false)
	actor_hud_menu.queue_free()
	settings_panel = settings_window.panel
	old_panel.queue_free()
	settings_panel.visibility_changed.connect(func() -> void:
		chat_hud.options_button.set_pressed_no_signal(settings_window.is_open())
		_sync_hud_button_states(true))
	settings_window.refresh_requested.connect(_refresh_unified_settings)

	settings_window._add_toggle(settings_window.page_body("Minimap"),
		"minimap_visible", "Show minimap", false)
	settings_window.add_choice("Minimap", "minimap_orientation", "Orientation",
		["North up", "Player up", "Viewport up"],
		["north_up", "player_up", "viewport_up"])
	settings_window.add_choice("Minimap", "minimap_shape", "Shape",
		["Square", "Round"], ["square", "round"])
	settings_window.add_choice("Minimap", "minimap_border", "Border width",
		MINIMAP_BORDER_LABELS, MINIMAP_BORDER_STEPS)
	settings_window.add_choice("Minimap", "minimap_marker_scale", "Marker size",
		MINIMAP_MARKER_SCALE_LABELS, MINIMAP_MARKER_SCALES)
	settings_window._add_number(settings_window.page_body("Minimap"),
		"minimap_zoom", "Visible map range (metres)", MINIMAP_ZOOM_MIN,
		MINIMAP_ZOOM_MAX, MINIMAP_ZOOM_DEFAULT)
	for type: StringName in MINIMAP_MARKER_TYPES:
		settings_window._add_toggle(settings_window.page_body("Minimap"),
			"minimap_marker_" + str(type), str(MINIMAP_MARKER_TYPE_LABELS[type]), true)
	for key: String in ["inventory_scale", "ground_bag_scale"]:
		settings_window._add_number(settings_window.page_body("Inventory"), key,
			"Inventory scale" if key == "inventory_scale" else "Ground bag scale",
			INVENTORY_MIN_SCALE, INVENTORY_MAX_SCALE, 1.0, 0.05)
	settings_window._add_toggle(settings_window.page_body("Inventory"),
		"storage_docked", "Dock inventory in storage window", false)
	for index: int in INVENTORY_QUANTITY_DEFAULTS.size():
		settings_window._add_number(settings_window.page_body("Inventory"),
			"quantity_%d" % index, "Quantity shortcut %d" % (index + 1),
			1, INVENTORY_QUANTITY_MAX, INVENTORY_QUANTITY_DEFAULTS[index])
	var quantity_labels: Array[String] = []
	for index: int in INVENTORY_QUANTITY_DEFAULTS.size():
		quantity_labels.append("Shortcut %d" % (index + 1))
	settings_window.add_choice("Inventory", "selected_quantity", "Active quantity",
		quantity_labels, range(INVENTORY_QUANTITY_DEFAULTS.size()))
	for kind: String in ["store", "drop"]:
		for index: int in 4:
			settings_window._add_toggle(settings_window.page_body("Inventory"),
				"protect_%s_%d" % [kind, index], "%s All: protect %s" % [
					"Store" if kind == "store" else "Drop",
					["first row", "last row", "first column", "last column"][index]], false)
	settings_window._add_toggle(settings_window.page_body("Spells"),
		"spell_bar_expanded", "Show spell bar", true)
	settings_window._add_toggle(settings_window.page_body("Spells"),
		"spell_bar_docked", "Attach spell bar to HUD", true)
	casting_bar.settings_body.reparent(settings_window.page_body("Spells"), false)
	casting_bar.settings_body.show()
	casting_bar.settings_requested.connect(func() -> void:
		settings_window.open_tab("Spells"))
	var backdrop_labels: Array[String] = []
	var backdrop_values: Array = []
	for backdrop: Dictionary in LoginBackdropScript.BACKDROPS:
		backdrop_labels.append(str(backdrop.label))
		backdrop_values.append(str(backdrop.id))
	settings_window.add_choice("Gameplay", "start_backdrop", "Login background",
		backdrop_labels, backdrop_values)
	settings_window._add_toggle(settings_window.page_body("Gameplay"),
		"start_animated", "Animate login background", true)
	settings_window._add_number(settings_window.page_body("HUD"),
		"invasion_assistant_scale", "Invasion assistant size",
		InvasionAssistantScript.MIN_SCALE, InvasionAssistantScript.MAX_SCALE, 1.0, 0.05)
	_refresh_unified_settings.call_deferred()

## A single read of live preferences keeps sliders, switches and menus in
## agreement without firing their change handlers or writing the file.
func _refresh_unified_settings() -> void:
	if settings_window == null or _hud_layout_list == null:
		return
	var values := {
		"minimap_visible": _minimap_visible, "minimap_orientation": _minimap_orientation,
		"minimap_shape": _minimap_shape, "minimap_border": _minimap_border,
		"minimap_marker_scale": _minimap_marker_scale, "minimap_zoom": _minimap_zoom,
		"combat_hud": extension_windows.combat_hud_enabled,
		"combat_hud_pinned": extension_windows.combat_hud_pinned,
		"timer_stopwatch": _hud_timer_stopwatch, "timer_start_seconds": _hud_timer_start_seconds,
		"inventory_scale": _inventory_scale, "ground_bag_scale": _ground_bag_scale,
		"storage_docked": classic_storage.docked, "selected_quantity": _selected_quantity_box,
		"spell_bar_docked": casting_bar.docked, "spell_bar_expanded": casting_bar.panel.visible,
		"shadows": _shadows_enabled, "particles": _effects_enabled,
		"cape_emblems": CapeEmblems.enabled,
		"nameplates": _nameplates_enabled, "rotation_sensitivity": camera_rig.rotation_sensitivity,
		"render_scale": _render_scale, "map_texture_quality": _map_texture_quality,
		"renderer": _renderer_preference, "decorative_grass": GraphicsOptions.decorative_grass,
		"keyboard_speed": camera_rig.keyboard_speed,
		"start_backdrop": start_screen_backdrop.selected_id,
		"start_animated": start_screen_backdrop.animation_enabled,
		"invasion_assistant_scale": invasion_assistant_window._preferred_scale,
	}
	values.merge(_hud_element_options)
	for key: String in _target_marker_style:
		values["target_" + key] = _target_marker_style[key]
	for key: String in _mount_banner_options:
		values["mount_banner_" + key] = _mount_banner_options[key]
	for mode: String in CreatureBannerSettings.MODES:
		for option: String in CreatureBannerSettings.OPTION_LABELS:
			values[CreatureBannerSettings.setting_key(mode, option)] = _creature_banner_options[mode][option]
	for option: String in chat_hud.options:
		values["chat_" + option] = chat_hud.options[option]
	if system_chat_hud != null:
		for option: String in system_chat_hud.options:
			values["system_chat_" + option] = system_chat_hud.options[option]
	for type: StringName in MINIMAP_MARKER_TYPES:
		values["minimap_marker_" + str(type)] = bool(_minimap_marker_types.get(type, true))
	for index: int in _inventory_quantities.size():
		values["quantity_%d" % index] = _inventory_quantities[index]
	for kind: String in ["store", "drop"]:
		for index: int in 4:
			values["protect_%s_%d" % [kind, index]] = _bulk_exclusions[kind][index]
	for key: String in values:
		settings_window.restore_value(key, values[key])
	sound_enabled.set_pressed_no_signal(audio_director.enabled)
	sound_volume.set_value_no_signal(audio_director.volume_linear)
	sound_volume_value.text = "%d%%" % roundi(audio_director.volume_linear * 100.0)
	for category: String in audio_director.category_volumes:
		settings_window.restore_value("audio_" + category,
			audio_director.category_volumes[category])
	minimap_size.set_value_no_signal(_minimap_scale)
	minimap_size_value.text = "%d%%" % roundi(_minimap_scale * 100.0)
	ui_scale_slider.set_value_no_signal(_ui_scale)
	show_through_obstacles.set_pressed_no_signal(_show_through_obstacles)
	equipment_side.select(1 if _equipment_side == "right" else 0)
	settings_window.restore_fps_limit(_fps_limit)
	settings_window.restore_name_distance(_name_distance_metres)
	settings_window.restore_crowd_settings(_crowd_bodies, _swaying_capes)
	settings_window.restore_look(LookProfile.player_mode(), LookProfile.look_forced())
	settings_window.restore_quality(LookProfile.player_quality(), LookProfile.quality_forced())
	_refresh_graphics_restart_notice()
	casting_bar.refresh()
	_refresh_hud_layout_menu()

func _on_audio_credits_pressed() -> void:
	var dialog := get_node_or_null("AudioCredits") as AcceptDialog
	if dialog == null:
		dialog = (load("res://src/ui/audio_credits_dialog.gd") as GDScript).new() as AcceptDialog
		add_child(dialog)
	dialog.popup_centered_clamped(Vector2i(740, 540))

func _close_settings() -> void:
	settings_window.close()

func _on_stats_button_pressed() -> void:
	if (bool(AppState.trade.get("open", false))
			or bool(AppState.storage.get("open", false))):
		return
	stats_panel.visible = not stats_panel.visible
	if stats_panel.visible:
		_road_ui(12)
		inventory_panel.hide()
		manufacturing_panel.hide()
		stats_tabs.current_tab = 0
		_sync_stats()
	_sync_hud_button_states(true)

func _configure_service_buttons() -> void:
	var icons := preload("res://src/ui/service_menu_icons.gd")
	for button: Button in [%ExchangeButton, %StoragePreviewButton]:
		button.icon = icons.texture(button == %StoragePreviewButton)
		button.expand_icon = true
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.toggle_mode = true
	%ExchangeButton.pressed.connect(func() -> void: extension_windows.call("toggle_marketplace"))
	%StoragePreviewButton.pressed.connect(_toggle_storage_preview)
	(extension_windows.get("market_panel") as Control).visibility_changed.connect(func() -> void: _sync_hud_button_states(true))
	storage_panel.visibility_changed.connect(func() -> void: _sync_hud_button_states(true))
	_refresh_service_tooltips()

func _refresh_service_tooltips() -> void:
	%ExchangeButton.tooltip_text = "Exchange · Browse prices and manage listings [%s]" % settings_window.call("binding_text", "toggle_exchange")
	%StoragePreviewButton.tooltip_text = "Storage preview · View only [%s]" % settings_window.call("binding_text", "toggle_storage_preview")

func _toggle_storage_preview() -> void:
	if bool(AppState.storage.get("open", false)):
		_on_storage_close_pressed()
	else:
		AppState.storage["read_only"] = true
		Network.send_chat("#storage view")

func _on_inventory_button_pressed() -> void:
	if bool(AppState.trade.get("open", false)):
		return
	inventory_panel.visible = not inventory_panel.visible
	if inventory_panel.visible:
		_on_storage_close_pressed()
		_road_ui(16)
		stats_panel.hide()
		manufacturing_panel.hide()
		# Ask for the enriched view of what the ordinary inventory packet
		# already told us. Command 226 never replaces that inventory: it only
		# names the items the icon ids stand for.
		Network.send_chat("#inventory")
		_sync_inventory()
	_sync_hud_button_states(true)

func _on_knowledge_button_pressed() -> void:
	if (bool(AppState.trade.get("open", false))
			or bool(AppState.storage.get("open", false))):
		return
	var was_knowledge_open: bool = stats_panel.visible and stats_tabs.current_tab == 1
	stats_panel.visible = not was_knowledge_open
	if stats_panel.visible:
		stats_tabs.current_tab = 1
		inventory_panel.hide()
		manufacturing_panel.hide()
		full_map.hide()
		_sync_knowledge()
	_sync_hud_button_states(true)

func _on_manufacturing_button_pressed() -> void:
	if (bool(AppState.trade.get("open", false))
			or bool(AppState.storage.get("open", false))):
		return
	manufacturing_panel.visible = not manufacturing_panel.visible
	if manufacturing_panel.visible:
		_road_ui(10)
		inventory_panel.hide()
		stats_panel.hide()
		full_map.hide()
		_sync_manufacturing()
	_sync_hud_button_states(true)

func _on_manufacturing_selected(index: int) -> void:
	selected_manufacturing_recipe = _list_metadata_int(manufacturing_list, index)
	manufacturing_server_status = "Ready for server validation."
	_sync_manufacturing_detail()

func _on_manufacturing_filter_changed(_text: String) -> void:
	_sync_manufacturing()

## The scene connects its two mix buttons to these two names. What the buttons
## say and do is set in `_build_manufacturing_window`; the node names and the
## method names the scene points at are the scene's, and renaming them there
## would be a merge conflict here for no gain.
func _on_manufacturing_mix_one_pressed() -> void:
	_mix_selected_now()

func _on_manufacturing_mix_all_pressed() -> void:
	_enqueue_selected()

func _on_manufacturing_close_pressed() -> void:
	manufacturing_panel.hide()

## Straight to the server, ahead of anything queued. If the queue was working
## an entry, that batch is cut short - no work is lost, because the server
## reports how many came out - and the entry is asked for again, for what is
## left of it, once this batch ends.
func _mix_selected_now() -> void:
	if selected_manufacturing_recipe < 0:
		return
	_start_mix(selected_manufacturing_recipe, _manufacturing_quantity_value(), -1)

func _enqueue_selected() -> void:
	if selected_manufacturing_recipe < 0:
		return
	manufacturing_queue.append({"recipe": selected_manufacturing_recipe,
		"wanted": _manufacturing_quantity_value(), "made": 0})
	manufacturing_server_status = "Added to the queue."
	_sync_manufacturing_queue()
	_sync_manufacturing_detail()

func _on_manufacturing_queue_remove_pressed(position: int) -> void:
	if position < 0 or position >= manufacturing_queue.size():
		return
	manufacturing_queue.remove_at(position)
	if manufacturing_queue_index > position:
		manufacturing_queue_index -= 1
	_sync_manufacturing_queue()

func _on_manufacturing_queue_clear_pressed() -> void:
	_road_ui(18)
	manufacturing_queue.clear()
	manufacturing_queue_running = false
	manufacturing_queue_index = 0
	manufacturing_server_status = "Queue cleared."
	_sync_manufacturing_queue()
	_sync_manufacturing_detail()

## Start working down the list, or stop. Stopping leaves the batch already
## with the server to finish: it is one mix, and cancelling it would throw
## away whatever it had made.
func _on_manufacturing_queue_start_pressed() -> void:
	if manufacturing_queue_running:
		_road_ui(18)
		manufacturing_queue_running = false
		manufacturing_server_status = "Queue stopped after this batch."
		_sync_manufacturing_queue()
		return
	if manufacturing_queue.is_empty():
		return
	_road_ui(17)
	manufacturing_queue_running = true
	manufacturing_queue_index = 0
	_advance_manufacturing_queue()

## Tools wear out, so the usual reason a familiar recipe stops working is a
## broken hatchet rather than a missing plank - and the answer was to leave
## the window, open storage, find the tool and come back to a window that is
## already standing next to it.
func _on_manufacturing_take_tool_pressed(tool_name: String) -> void:
	var error: Error = Network.tool_request(tool_name)
	manufacturing_server_status = ("Asked storage for a %s." % tool_name
		if error == OK else "Tool request failed: " + error_string(error))
	manufacturing_status.text = manufacturing_server_status

## Ask for a batch, by recipe rather than by the inventory positions the
## ingredients sit in. `MANUFACTURE_THIS` can only name positions, which makes
## mixing out of storage unsayable in it: the materials are in no position.
##
## `position` is the queue entry the batch belongs to, or -1 for Mix Now.
func _start_mix(recipe_index: int, wanted: int, position: int) -> void:
	var definition: Dictionary = manufacturing_catalog.recipe(recipe_index)
	if definition.is_empty():
		return
	var from_storage: bool = _manufacturing_from_storage()
	var error: Error = Network.mix_request(recipe_index, wanted, from_storage)
	if error != OK:
		manufacturing_server_status = "Mix request failed: " + error_string(error)
		manufacturing_status.text = manufacturing_server_status
		return
	_mix_pending.append({"output": str(definition.get("output", "")),
		"entry": position})
	manufacturing_server_status = "Making %d × %s from %s." % [wanted,
		str(definition.get("output", "")),
		"storage" if from_storage else "your pack"]
	manufacturing_status.text = manufacturing_server_status

## Send the batch the queue is on, or stop when the list runs out. One at a
## time and from the top: that is what the server can do, and what a list
## means. Nothing is sent while a batch is still outstanding.
func _advance_manufacturing_queue() -> void:
	while manufacturing_queue_running and _mix_pending.is_empty():
		if manufacturing_queue_index >= manufacturing_queue.size():
			manufacturing_queue_running = false
			manufacturing_server_status = "Queue finished."
			break
		var entry: Dictionary = manufacturing_queue[manufacturing_queue_index]
		var left: int = int(entry.get("wanted", 1)) - int(entry.get("made", 0))
		if left <= 0:
			manufacturing_queue_index += 1
			continue
		_start_mix(int(entry.get("recipe", -1)), left, manufacturing_queue_index)
		break
	_sync_manufacturing_queue()

## A batch has ended - finished, out of materials, taken over by Mix Now, or
## interrupted by another action. The server says how many came out, which is
## the only way to tell six torches from two, and the reason the queue can move
## on without watching an inventory that has simply stopped changing.
func _on_mix_state_changed() -> void:
	var state: Dictionary = AppState.mix_state
	if not bool(state.get("running", false)) and not _mix_pending.is_empty():
		var run: Dictionary = _mix_pending[0]
		if str(state.get("output", "")) == str(run.get("output", "")):
			_mix_pending.remove_at(0)
			_settle_mix_run(run, int(state.get("made", 0)),
				bool(state.get("interrupted", false)))
	_sync_manufacturing()

func _settle_mix_run(run: Dictionary, made: int, interrupted := false) -> void:
	if not interrupted:
		manufacturing_server_status = ("Crafting failed: no %s made. Check the recipe requirements and supplies." % str(run.get("output", "items"))
			if made == 0 else "Made %d %s." % [made, str(run.get("output", "items"))])
	var position: int = int(run.get("entry", -1))
	if position >= 0 and position < manufacturing_queue.size():
		var entry: Dictionary = manufacturing_queue[position]
		entry["made"] = int(entry.get("made", 0)) + made
		# A batch still outstanding means Mix Now cut this one short, and an
		# interrupted one was stopped by something else the player did; either
		# way the entry keeps its place and is asked for again. Otherwise the
		# batch ran to its end or ran out of materials, and asking again would
		# only fail the same way.
		if (_mix_pending.is_empty() and not interrupted
				and manufacturing_queue_index == position):
			manufacturing_queue_index = position + 1
	# Whatever interrupted the batch - a harvest - is what the player is doing
	# now, and the next batch would end it in turn, because starting a mix
	# stops a harvest. So the queue waits for Start rather than move on.
	if interrupted and manufacturing_queue_running:
		manufacturing_queue_running = false
		manufacturing_server_status = ("Mixing was interrupted, so the queue"
			+ " stopped. Start it again to carry on.")
		_sync_manufacturing_queue()
	if manufacturing_queue_running and _mix_pending.is_empty():
		_advance_manufacturing_queue()

func _on_knowledge_selected(index: int) -> void:
	var knowledge_index: int = _list_metadata_int(knowledge_list, index)
	if knowledge_index < 0 or knowledge_index >= knowledge_catalog.size():
		return
	AppState.select_knowledge(knowledge_index)
	var error: Error = Network.get_knowledge_info(knowledge_index)
	if error != OK:
		push_warning("GET_KNOWLEDGE_INFO failed: " + error_string(error))

func _on_knowledge_filter_toggled(_enabled: bool) -> void:
	_sync_knowledge()

func _on_knowledge_close_pressed() -> void:
	stats_panel.hide()

func _on_inventory_close_pressed() -> void:
	if classic_storage != null and classic_storage.is_inventory_docked():
		_on_storage_close_pressed()
		return
	inventory_panel.hide()

func _on_inventory_use_pressed() -> void:
	_choose_inventory_tool("use")

func _on_inventory_equip_pressed() -> void:
	_choose_inventory_tool("equip")

func _on_inventory_unequip_pressed() -> void:
	_choose_inventory_tool("unequip")

func _on_inventory_inspect_pressed() -> void:
	_choose_inventory_tool("inspect")

func _configure_inventory_menus() -> void:
	inventory_store_all.text = "Store All"
	inventory_store_all.tooltip_text = "Store all backpack stacks. Protect equipment or supplies using the Protection button."
	var protection := Button.new()
	protection.name = "StorageProtection"
	protection.text = "Protection…"
	protection.tooltip_text = "Choose backpack rows or columns to keep when using Store All."
	inventory_store_all.get_parent().add_child(protection)
	protection.pressed.connect(func():
		_store_options_menu.position = Vector2i(protection.global_position + Vector2(0, protection.size.y))
		_store_options_menu.popup())
	_store_options_menu = PopupMenu.new()
	_drop_options_menu = PopupMenu.new()
	for menu: PopupMenu in [_store_options_menu, _drop_options_menu]:
		for label: String in ["Protect first row", "Protect last row",
				"Protect first column", "Protect last column"]:
			menu.add_check_item(label)
		inventory_panel.add_child(menu)
	_store_options_menu.id_pressed.connect(_on_bulk_option_selected.bind("store"))
	_drop_options_menu.id_pressed.connect(_on_bulk_option_selected.bind("drop"))
	_sync_bulk_option_menus()

func _sync_bulk_option_menus() -> void:
	for menu_and_key: Array in [[_store_options_menu, "store"], [_drop_options_menu, "drop"]]:
		var menu: PopupMenu = menu_and_key[0] as PopupMenu
		var values: Array = _bulk_exclusions.get(str(menu_and_key[1]), []) as Array
		for index: int in range(4):
			menu.set_item_checked(index, index < values.size() and bool(values[index]))

func _on_bulk_button_gui_input(event: InputEvent, kind: String) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse: InputEventMouseButton = event as InputEventMouseButton
	if not mouse.pressed or mouse.button_index != MOUSE_BUTTON_RIGHT:
		return
	var menu: PopupMenu = _store_options_menu if kind == "store" else _drop_options_menu
	menu.position = Vector2i(get_viewport().get_mouse_position())
	menu.popup()
	(inventory_store_all if kind == "store" else inventory_drop_all).accept_event()

func _on_bulk_option_selected(option_id: int, kind: String) -> void:
	if option_id < 0 or option_id >= 4:
		return
	var values: Array = (_bulk_exclusions.get(kind, [false, false, false, false]) as Array).duplicate()
	values[option_id] = not bool(values[option_id])
	_bulk_exclusions[kind] = values
	_sync_bulk_option_menus()
	_save_hud_settings()

func _inventory_slot_is_protected(slot: int, kind: String) -> bool:
	var values: Array = _bulk_exclusions.get(kind, [false, false, false, false]) as Array
	return ((bool(values[0]) and slot < 6)
		or (bool(values[1]) and slot >= 30)
		or (bool(values[2]) and slot % 6 == 0)
		or (bool(values[3]) and slot % 6 == 5))

func _on_inventory_store_all_pressed() -> void:
	if bool(AppState.storage.get("read_only", false)):
		inventory_description.text = "Storage preview is view only. Visit a storage keeper or chest to transfer items."
		return
	if not bool(AppState.storage.get("open", false)):
		inventory_description.text = "Open storage before using Sto All."
		return
	var sent := 0
	var slots: Array = AppState.inventory.keys()
	slots.sort()
	for raw_slot: Variant in slots:
		var slot: int = int(raw_slot)
		if slot < 0 or slot >= 36 or _inventory_slot_is_protected(slot, "store"):
			continue
		var item: Dictionary = AppState.inventory.get(slot, {}) as Dictionary
		if not item.is_empty() and Network.deposit_storage(slot,
				int(item.get("quantity", 0))) == OK:
			sent += 1
	inventory_description.text = "Sto All sent %d stack%s to the server." % [
		sent, "" if sent == 1 else "s"]

func _on_inventory_get_all_pressed() -> void:
	var bag_id: int = _ground_bag_below_player()
	if bag_id < 0:
		inventory_description.text = "There is no ground bag below your character."
		return
	_ground_bag_get_all_requested_msec = Time.get_ticks_msec()
	_ground_bag_get_all_bag_id = bag_id
	if bool(AppState.ground_bag.get("open", false)) \
			and int(AppState.ground_bag.get("bag_id", -1)) == bag_id:
		_ground_bag_get_all_requested_msec = -1
		_ground_bag_get_all_bag_id = -1
		var sent: int = _request_all_ground_bag_items()
		inventory_description.text = _ground_bag_get_all_message(sent)
		return
	AppState.begin_ground_bag_inspection(bag_id)
	var error: Error = Network.inspect_bag(bag_id)
	if error != OK:
		_ground_bag_get_all_requested_msec = -1
		_ground_bag_get_all_bag_id = -1
		inventory_description.text = "Could not open the ground bag: " + error_string(error)
		push_warning("Get All INSPECT_BAG failed: " + error_string(error))
	else:
		inventory_description.text = "Opening the ground bag below you…"

func _ground_bag_below_player() -> int:
	var actor_value: Variant = AppState.actors.get(AppState.local_actor_id)
	if not actor_value is Dictionary:
		return -1
	var actor: Dictionary = actor_value as Dictionary
	var actor_x: int = int(actor.get("x", -99999))
	var actor_y: int = int(actor.get("y", -99999))
	for raw_bag_id: Variant in AppState.ground_bags:
		var bag_value: Variant = AppState.ground_bags.get(raw_bag_id)
		if bag_value is Dictionary:
			var bag: Dictionary = bag_value as Dictionary
			if int(bag.get("x", -99998)) == actor_x \
					and int(bag.get("y", -99998)) == actor_y:
				return int(raw_bag_id)
	return -1

func _ground_bag_get_all_message(sent: int) -> String:
	if sent <= 0:
		return "The ground bag is empty."
	return ("Get All requested %d ground stack%s. The server will leave anything "
		+ "that exceeds your free slots or load capacity in the open bag.") % [
		sent, "" if sent == 1 else "s"]

func _on_inventory_drop_all_pressed() -> void:
	var sent := 0
	var slots: Array = AppState.inventory.keys()
	slots.sort()
	for raw_slot: Variant in slots:
		var slot: int = int(raw_slot)
		if slot < 0 or slot >= 36 or _inventory_slot_is_protected(slot, "drop"):
			continue
		var item: Dictionary = AppState.inventory.get(slot, {}) as Dictionary
		if not item.is_empty() and Network.drop_inventory_item(slot,
				int(item.get("quantity", 0))) == OK:
			sent += 1
	inventory_description.text = "Drop All sent %d stack%s to the server." % [
		sent, "" if sent == 1 else "s"]

func _on_inventory_mix_all_pressed() -> void:
	if selected_manufacturing_recipe < 0:
		manufacturing_panel.show()
		manufacturing_panel.move_to_front()
		manufacturing_status.text = "Select a recipe, then use Mix All."
		return
	# As many as the ingredients run to. The manufacturing window's own box is
	# a batch size somebody chose for that window; this button has never asked
	# for one and asking here would be a second place to keep it.
	_start_mix(selected_manufacturing_recipe, MANUFACTURING_MAX_QUANTITY, -1)

func _on_inventory_item_lists_pressed() -> void:
	if classic_storage != null:
		classic_storage.show_lists()
		return
	_sync_saved_item_lists()
	item_lists_panel.show()
	item_lists_panel.move_to_front()

func _sync_saved_item_lists() -> void:
	if classic_storage != null:
		classic_storage.refresh_favorites()
		return
	if saved_item_lists == null:
		return
	saved_item_lists.clear()
	var names: Array = _item_lists.keys()
	names.sort_custom(func(a: Variant, b: Variant) -> bool:
		return str(a).naturalnocasecmp_to(str(b)) < 0)
	for raw_name: Variant in names:
		var name: String = str(raw_name)
		var index: int = saved_item_lists.item_count
		saved_item_lists.add_item(name)
		saved_item_lists.set_item_metadata(index, name)

func _on_saved_item_list_selected(index: int) -> void:
	if index < 0 or index >= saved_item_lists.item_count:
		return
	var name: String = str(saved_item_lists.get_item_metadata(index))
	if classic_storage != null:
		classic_storage.activate_list(name)
		return
	item_list_name.text = name
	item_list_entries.text = str(_item_lists.get(name, ""))
	item_list_status.text = "Loaded %s." % name

func _parse_item_list(text: String) -> Array[Dictionary]:
	var parsed: Array[Dictionary] = []
	for raw_line: String in text.split("\n"):
		var line: String = raw_line.strip_edges().replace(",", ":")
		if line.is_empty() or line.begins_with("#"):
			continue
		var parts: PackedStringArray = line.split(":", false, 1)
		if parts.size() != 2 or not parts[0].strip_edges().is_valid_int() \
				or not parts[1].strip_edges().is_valid_int():
			return []
		var image_id: int = int(parts[0].strip_edges())
		var quantity: int = int(parts[1].strip_edges())
		if image_id < 0 or quantity <= 0:
			return []
		parsed.append({"image_id": image_id, "quantity": quantity})
	return parsed

func _on_item_list_save_pressed() -> void:
	if classic_storage != null:
		classic_storage.rename_list()
		return
	var name: String = item_list_name.text.strip_edges()
	var entries: Array[Dictionary] = _parse_item_list(item_list_entries.text)
	if name.is_empty() or entries.is_empty():
		item_list_status.text = "Enter a name and valid image_id:quantity lines."
		return
	_item_lists[name] = item_list_entries.text.strip_edges()
	_save_hud_settings()
	_sync_saved_item_lists()
	item_list_status.text = "Saved %s (%d item types)." % [name, entries.size()]

func _on_item_list_delete_pressed() -> void:
	if classic_storage != null:
		classic_storage.delete_list()
		return
	var name: String = item_list_name.text.strip_edges()
	if _item_lists.erase(name):
		_save_hud_settings()
		_sync_saved_item_lists()
		item_list_name.clear()
		item_list_entries.clear()
		item_list_status.text = "Deleted %s." % name

func _on_item_list_get_pressed() -> void:
	if classic_storage != null:
		classic_storage.collect_list()
		return
	if not bool(AppState.storage.get("open", false)):
		item_list_status.text = "Open the relevant storage category first."
		return
	var wanted: Array[Dictionary] = _parse_item_list(item_list_entries.text)
	if wanted.is_empty():
		item_list_status.text = "The list has no valid entries."
		return
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	var request_count := 0
	var missing: Array[String] = []
	for request: Dictionary in wanted:
		var remaining: int = int(request.get("quantity", 0))
		var positions: Array = items.keys()
		positions.sort()
		positions.reverse()
		for raw_position: Variant in positions:
			var item: Dictionary = items.get(int(raw_position), {}) as Dictionary
			if int(item.get("image_id", -1)) != int(request.get("image_id", -2)):
				continue
			var quantity: int = mini(remaining, int(item.get("quantity", 0)))
			if quantity > 0 and Network.withdraw_storage(int(raw_position), quantity) == OK:
				remaining -= quantity
				request_count += 1
			if remaining <= 0:
				break
		if remaining > 0:
			missing.append("#%d ×%d" % [int(request.get("image_id", 0)), remaining])
	item_list_status.text = ("Requested %d stack%s." % [request_count,
		"" if request_count == 1 else "s"]
		+ (" Missing " + ", ".join(missing) + "." if not missing.is_empty() else ""))

func _trade_source_items() -> Dictionary:
	if trade_source_type.get_selected_id() == 2:
		if (not bool(AppState.trade.get("storage_available", false))
				or not bool(AppState.storage.get("open", false)) or not _storage_stock_ready()):
			return {}
		return AppState.storage.get("items", {}) as Dictionary
	return AppState.trade.get("source_inventory", {}) as Dictionary

func _on_trade_source_type_selected(_index: int) -> void:
	_sync_trade()

func _on_trade_storage_category_selected(index: int) -> void:
	var category_id: int = trade_storage_category.get_item_id(index)
	AppState.storage["category_id"] = category_id
	var error: Error = Network.get_storage_category(category_id)
	if error != OK:
		push_warning("GET_STORAGE_CATEGORY failed: " + error_string(error))
	_sync_trade()

func _on_trade_source_selected(index: int) -> void:
	selected_trade_side = "source"
	var slot: int = _trade_list_slot(trade_source, index)
	var source_inventory: Dictionary = _trade_source_items()
	var item_value: Variant = source_inventory.get(slot)
	if item_value is Dictionary:
		trade_quantity.max_value = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
		trade_quantity.value = mini(int(trade_quantity.value), int(trade_quantity.max_value))
	_sync_trade_actions()

func _on_trade_own_selected(_index: int) -> void:
	selected_trade_side = "own"
	_sync_trade_actions()

func _on_trade_other_selected(_index: int) -> void:
	selected_trade_side = "other"
	_sync_trade_actions()

func _on_trade_storage_destination_toggled(enabled: bool) -> void:
	if not bool(AppState.trade.get("storage_available", false)):
		return
	var selected: PackedInt32Array = trade_other_offers.get_selected_items()
	if selected.is_empty():
		return
	var offer_slot: int = _trade_list_slot(trade_other_offers, int(selected[0]))
	if offer_slot >= 0 and offer_slot < trade_destinations.size():
		trade_destinations[offer_slot] = 2 if enabled else 1

func _on_trade_offer_pressed() -> void:
	var selected: PackedInt32Array = trade_source.get_selected_items()
	if selected.is_empty():
		return
	var slot: int = _trade_list_slot(trade_source, int(selected[0]))
	var source_inventory: Dictionary = _trade_source_items()
	var item_value: Variant = source_inventory.get(slot)
	if not item_value is Dictionary:
		return
	var item: Dictionary = item_value as Dictionary
	var quantity: int = clampi(int(trade_quantity.value), 1, int(item.get("quantity", 1)))
	var error: Error = (Network.put_storage_on_trade(slot, quantity)
		if trade_source_type.get_selected_id() == 2
		else Network.put_inventory_on_trade(slot, quantity))
	if error != OK:
		push_warning("PUT_OBJECT_ON_TRADE failed: " + error_string(error))

func _on_trade_remove_pressed() -> void:
	var selected: PackedInt32Array = trade_own_offers.get_selected_items()
	if selected.is_empty():
		return
	var offer_slot: int = _trade_list_slot(trade_own_offers, int(selected[0]))
	var own_offers: Dictionary = AppState.trade.get("own_offers", {}) as Dictionary
	var offer_value: Variant = own_offers.get(offer_slot)
	if not offer_value is Dictionary:
		return
	var offer: Dictionary = offer_value as Dictionary
	var quantity: int = clampi(int(trade_quantity.value), 1, int(offer.get("quantity", 1)))
	var error: Error = Network.remove_trade_item(offer_slot, quantity)
	if error != OK:
		push_warning("REMOVE_OBJECT_FROM_TRADE failed: " + error_string(error))

func _on_trade_inspect_pressed() -> void:
	var list: ItemList = trade_other_offers if selected_trade_side == "other" else trade_own_offers
	var selected: PackedInt32Array = list.get_selected_items()
	if selected.is_empty():
		return
	var offer_slot: int = _trade_list_slot(list, int(selected[0]))
	var error: Error = Network.look_at_trade_item(offer_slot, list == trade_other_offers)
	if error != OK:
		push_warning("LOOK_AT_TRADE_ITEM failed: " + error_string(error))

func _on_trade_accept_pressed() -> void:
	if not bool(AppState.trade.get("open", false)):
		return
	var error: Error = Network.accept_trade(trade_destinations)
	if error != OK:
		push_warning("ACCEPT_TRADE failed: " + error_string(error))

func _on_trade_reject_pressed() -> void:
	if not bool(AppState.trade.get("open", false)):
		return
	var error: Error = Network.reject_trade()
	if error != OK:
		push_warning("REJECT_TRADE failed: " + error_string(error))

func _on_trade_cancel_pressed() -> void:
	if not bool(AppState.trade.get("open", false)):
		return
	trade_status.text = "Cancelling trade and restoring offers…"
	var error: Error = Network.exit_trade()
	if error != OK:
		push_warning("EXIT_TRADE failed: " + error_string(error))

func _on_storage_category_selected(index: int) -> void:
	var category_id: int = _list_metadata_int(storage_categories, index)
	if category_id < 0:
		return
	var error: Error = Network.get_storage_category(category_id)
	if error != OK:
		push_warning("GET_STORAGE_CATEGORY failed: " + error_string(error))

func _on_storage_item_selected(index: int) -> void:
	selected_storage_side = "storage"
	var position: int = _list_metadata_int(storage_items, index)
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	var item_value: Variant = items.get(position)
	if item_value is Dictionary:
		storage_quantity.max_value = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
		storage_quantity.value = mini(int(storage_quantity.value), int(storage_quantity.max_value))
	_sync_storage_actions()

func _on_storage_inventory_selected(index: int) -> void:
	selected_storage_side = "inventory"
	var slot: int = _list_metadata_int(storage_inventory, index)
	var item_value: Variant = AppState.inventory.get(slot)
	if item_value is Dictionary:
		storage_quantity.max_value = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
		storage_quantity.value = mini(int(storage_quantity.value), int(storage_quantity.max_value))
	_sync_storage_actions()

func _on_storage_deposit_pressed() -> void:
	var selected: PackedInt32Array = storage_inventory.get_selected_items()
	if selected.is_empty():
		return
	var slot: int = _list_metadata_int(storage_inventory, int(selected[0]))
	var item_value: Variant = AppState.inventory.get(slot)
	if not item_value is Dictionary:
		return
	var quantity: int = clampi(int(storage_quantity.value), 1,
		int((item_value as Dictionary).get("quantity", 1)))
	var error: Error = Network.deposit_storage(slot, quantity)
	if error != OK:
		push_warning("DEPOSIT_ITEM failed: " + error_string(error))

func _on_storage_withdraw_pressed() -> void:
	var selected: PackedInt32Array = storage_items.get_selected_items()
	if selected.is_empty():
		return
	var position: int = _list_metadata_int(storage_items, int(selected[0]))
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	var item_value: Variant = items.get(position)
	if not item_value is Dictionary:
		return
	var quantity: int = clampi(int(storage_quantity.value), 1,
		int((item_value as Dictionary).get("quantity", 1)))
	var error: Error = Network.withdraw_storage(position, quantity)
	if error != OK:
		push_warning("WITHDRAW_ITEM failed: " + error_string(error))

func _on_storage_inspect_pressed() -> void:
	var selected: PackedInt32Array = storage_items.get_selected_items()
	if selected.is_empty():
		return
	var position: int = _list_metadata_int(storage_items, int(selected[0]))
	var error: Error = Network.look_at_storage_item(position)
	if error != OK:
		push_warning("LOOK_AT_STORAGE_ITEM failed: " + error_string(error))

func _on_storage_close_pressed() -> void:
	Network.send_chat("#storage close")
	AppState.close_storage()

## The bag grid mirrors Eternal Lands: a left click takes the quantity in the
## box below, so picking something up is one gesture rather than select-then-
## press. A right click asks the server what the stack is instead.
func _on_ground_bag_slot_pressed(index: int) -> void:
	var position: int = _ground_bag_slot_position(index)
	if position < 0:
		return
	var items: Dictionary = AppState.ground_bag.get("items", {}) as Dictionary
	var item_value: Variant = items.get(position)
	if not item_value is Dictionary:
		return
	var available: int = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
	var quantity: int = (available if Input.is_key_pressed(KEY_CTRL)
		else mini(available, _selected_quantity()))
	var error: Error = Network.pick_up_ground_item(position, quantity)
	if error != OK:
		push_warning("PICK_UP_ITEM failed: " + error_string(error))

func _ground_bag_slot_position(index: int) -> int:
	if index < 0 or index >= ground_bag_slot_buttons.size():
		return -1
	return int(ground_bag_slot_buttons[index].get_meta("bag_position", -1))

func _on_ground_bag_slot_gui_input(event: InputEvent, index: int) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse: InputEventMouseButton = event as InputEventMouseButton
	if not mouse.pressed or mouse.button_index != MOUSE_BUTTON_RIGHT:
		return
	# The item in hand goes back first; only an empty hand looks.
	if _has_carry():
		_cancel_carry()
	else:
		_on_ground_bag_look_pressed(index)
	ground_bag_slot_buttons[index].accept_event()

func _on_ground_bag_pick_all_pressed() -> void:
	_request_all_ground_bag_items()

func _request_all_ground_bag_items() -> int:
	var items: Dictionary = AppState.ground_bag.get("items", {}) as Dictionary
	var positions: Array = items.keys()
	positions.sort()
	var sent := 0
	for raw_position: Variant in positions:
		var position: int = int(raw_position)
		var item_value: Variant = items.get(position)
		if item_value is Dictionary:
			var quantity: int = int((item_value as Dictionary).get("quantity", 0))
			if quantity > 0:
				var error: Error = Network.pick_up_ground_item(position, quantity)
				if error != OK:
					push_warning("PICK_UP_ITEM failed: " + error_string(error))
				else:
					sent += 1
	return sent

func _on_ground_bag_drop_pressed() -> void:
	var slot: int = selected_inventory_slot
	if slot < 0 or slot >= 36:
		return
	var item_value: Variant = AppState.inventory.get(slot)
	if not item_value is Dictionary:
		return
	var available: int = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
	var quantity: int = (available if Input.is_key_pressed(KEY_CTRL)
		else mini(available, _selected_quantity()))
	var error: Error = Network.drop_inventory_item(slot, quantity)
	if error != OK:
		push_warning("DROP_ITEM failed: " + error_string(error))

func _on_ground_bag_close_pressed() -> void:
	_close_ground_bag()

func _close_ground_bag() -> void:
	var error: Error = Network.close_bag()
	if error != OK:
		push_warning("CLOSE_BAG failed: " + error_string(error))
	AppState.close_ground_bag()

func _on_disconnect_pressed() -> void:
	Network.disconnect_from_server()

func _close_client() -> void:
	# Keep serving rendering/physics commands until a private loader completes;
	# joining a live import while the rendering server shuts down can deadlock.
	character_intro.cancel()
	gauntlet_prewarm.discard()
	await get_tree().process_frame
	exterior_stream.clear()
	while not exterior_stream.is_idle():
		await get_tree().process_frame
	get_tree().quit()

func _exit_tree() -> void:
	RustRiderPose.close_batches()
	client_runtime.close()
	mouse_cursors.release()
	occluder_fade.reset()
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	NativeAnimationImporter.clear()
	# Released here, before the rendering server goes: otherwise the picture's
	# and the cached tab-map textures are reported leaked at exit.
	_remove_map_picture()
	_tab_map_textures.clear()
	_tab_map_detail_textures.clear()

func _on_login_succeeded() -> void:
	Diagnostics.record("login_succeeded", {"server_map": AppState.current_map})
	# A new session's first sky is already there, not eased in.
	_weather_synced = false
	spell_loadout.load_profile("%s:%d/%s" % [host_edit.text.strip_edges().to_lower(), int(port_edit.value), user_edit.text.strip_edges().to_lower()])
	# Tell the server which Eloria extensions this client implements. Without
	# it the server serves the legacy dialogue and raw-text fallback for every
	# extension, which is what it had been doing for this client since it was
	# written.
	var capabilities_error: Error = Network.send_client_capabilities()
	if capabilities_error != OK:
		push_warning("#clientcaps failed: " + error_string(capabilities_error))
	# A new session has said nothing yet about what it holds back.
	nearby_indicator.show_count(0)
	if _resync_after_reconnect:
		# This session follows a dropped connection, so nothing that arrived
		# before the drop can be trusted. Ask for the three authoritative
		# snapshots everything else is derived from.
		_resync_after_reconnect = false
		var resync_error: Error = Network.request_resync()
		if resync_error != OK:
			push_warning("resync failed: " + error_string(resync_error))
		else:
			AppState.append_local_message(
				"Reconnected. Rebuilding world state from the server.", 3)
	_set_login_screen_visible(false)
	creation_panel.hide()
	_hide_chat_input()
	game_view.show()
	_sync_connection_banner()
	# Restore the saved minimap visibility. _clear_world_presentation() hides
	# the frame on disconnect, so this is what brings it back for the next
	# session rather than leaving the player to press Alt+M every time.
	minimap_frame.visible = _minimap_visible
	_request_map_redraw()
	_sync_map_viewport_activity()
	map_label.text = "Entering world…"
	if arrival_curtain.is_showing():
		arrival_curtain.set_text("Entering Rabbit Lands…")
		arrival_curtain.set_progress(0.1)
	_load_server_map()
	_sync_world()
	_record_client_snapshot_after_frames()

func _on_login_failed(message: String) -> void:
	_end_arrival()
	if character_intro.is_active():
		character_intro.cancel()
		creation_panel.hide()
		_set_login_screen_visible(true)
	Diagnostics.record("login_failed")
	status_label.text = "Login failed: " + message
	login_button.disabled = false

func _on_connection_state_changed(value: String) -> void:
	if value == "disconnected":
		character_intro.cancel()
		_end_arrival()
		respawn_prewarm.discard()
		gauntlet_prewarm.discard()
		_pickpoint_draft.clear()
		_pickpoint_submitting = false
	status_label.text = ("Securing the connection…" if value == "securing"
		else value.capitalize())
	connect_button.text = "Disconnect" if value == "connected" else "Connect"
	connect_button.disabled = value == "connecting" or value == "securing"
	login_button.disabled = value != "connected" or AppState.authenticated
	new_character_button.disabled = value != "connected" or AppState.authenticated
	var was_in_world: bool = game_view.visible
	if value == "disconnected" and was_in_world:
		_clear_world_presentation()
		game_view.hide()
		_set_login_screen_visible(true)
		status_label.text = "Disconnected"
	if value == "connected" and _resync_after_reconnect:
		# The socket came back on its own. The password was never retained, so
		# the player authenticates again; the resync happens once they are back
		# in the world.
		status_label.text = "Reconnected. Enter your password to resume."
		password_edit.grab_focus()
	_sync_connection_banner()

## The connection state, wherever the player is looking. Anything other than a
## live authenticated session is worth saying out loud: a silently dead socket
## looks exactly like a quiet server.
func _sync_connection_banner() -> void:
	if connection_banner == null:
		return
	var state: String = AppState.connection_state
	if state == "connected" and AppState.authenticated:
		connection_banner.hide()
		return
	var text: String = ""
	match state:
		"reconnecting":
			text = "Connection lost - reconnecting (attempt %d of %d)…" % [
				Network.reconnect_attempt(), Network.RECONNECT_DELAYS_MSEC.size()]
		"connecting":
			text = "Connecting…"
		"securing":
			text = "Securing the connection…"
		"connected":
			text = ("Connected securely - not signed in" if Network.is_secure()
				else "Connected - not signed in")
		_:
			text = "Disconnected"
	connection_banner.text = text
	connection_banner.show()

func _on_reconnect_progress(attempt: int, total: int, delay_msec: int) -> void:
	_resync_after_reconnect = true
	status_label.text = "Connection lost. Reconnecting in %.1fs (attempt %d of %d)…" % [
		float(delay_msec) / 1000.0, attempt, total]
	AppState.append_local_message(
		"Connection lost. Reconnecting in %.1f seconds (attempt %d of %d)."
			% [float(delay_msec) / 1000.0, attempt, total], 3)
	_sync_connection_banner()

func _clear_world_presentation() -> void:
	RustRiderPose.close_batches()
	# No actor survives this clear. Forget stepped members before queueing
	# any body, without reactivating its animation or skeleton callbacks.
	animation_gate.reset(false)
	client_runtime.reset_session()
	SeasonSurfaces.set_season({})
	quest_trail.clear()
	character_intro.cancel()
	_clear_map_walk_target()
	for effect: Variant in world_effects:
		if is_instance_valid(effect): effect.queue_free()
	world_effects.clear()
	for raw_node: Variant in actor_nodes.values():
		if is_instance_valid(raw_node):
			(raw_node as Node).queue_free()
	actor_nodes.clear()
	crowd.clear()
	_built_bodies = 0
	for raw_bag_node: Variant in ground_bag_nodes.values():
		if is_instance_valid(raw_bag_node):
			(raw_bag_node as Node).queue_free()
	ground_bag_nodes.clear()
	for raw_marker_node: Variant in walk_highlight_markers.values():
		if is_instance_valid(raw_marker_node):
			(raw_marker_node as Node).queue_free()
	walk_highlight_markers.clear()
	for raw_object_node: Variant in map_object_nodes.values():
		if is_instance_valid(raw_object_node):
			(raw_object_node as Node).queue_free()
	map_object_nodes.clear()
	_map_presentation = {}
	_ungrounded_map_objects.clear()
	for markers: Dictionary in [map_marker_nodes, player_mark_nodes]:
		for marker: Node in markers.values():
			if is_instance_valid(marker):
				marker.queue_free()
		markers.clear()
	var no_marks: Array[Dictionary] = []
	map_marker_overlay.set_live_marks(no_marks)
	map_marker_overlay.set_waypoints(no_marks)
	map_marker_overlay.set_markers(no_marks)
	map_marker_overlay.set_player_marks(no_marks)
	if is_instance_valid(map_light_root):
		map_light_root.queue_free()
	map_light_root = null
	_actor_surface_samples.clear()
	_grounded_actors.clear()
	# The parsed model and animation caches are only worth holding for the
	# session they were built in.
	TorsoBodyCover.clear()
	WardrobeShirtFitScript.clear()
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	occluder_fade.reset()
	exterior_stream.clear()
	_retained_traveller = -1
	world_loader.unload_world()
	# Cancel both queued work and an old coroutine waiting on physics. A later
	# session's queue must not be cleared by that coroutine when it resumes.
	_surface_refresh_epoch += 1
	_surface_refresh_queue.clear()
	_surface_refresh_running = false
	_surface_refresh_inflight = 0
	_surface_followup_pending = 0
	loaded_server_map = ""
	full_map.hide()
	inventory_panel.hide()
	stats_panel.hide()
	trade_panel.hide()
	storage_panel.hide()
	ground_bag_panel.hide()
	manufacturing_panel.hide()
	item_lists_panel.hide()
	dialogue_panel.hide()
	OldcraftDialogueStyleScript.sync_visibility(self, false)
	console_panel.hide()
	_close_settings()
	minimap_frame.hide()
	chat_output.clear()
	system_chat_hud.output.clear()
	chat_hud.preview_feed.clear_messages()
	system_chat_hud.preview_feed.clear_messages()
	console_output.clear()
	chat_hud.reset_destinations()
	chat_log_tabs.sync([], [])
	chat_log_tabs.select("all")
	_chat_tab = "all"
	_chat_tail = {}
	_console_tail = {}
	selected_target.text = "Target: none"

func _input(event: InputEvent) -> void:
	if hud_workspace != null and hud_workspace.is_open():
		hud_workspace.handle_input(event)
		return
	if arrival_curtain.blocks_input():
		return
	if _actor_hud_menu != null and _actor_hud_menu.visible:
		if _actor_hud_menu.handle_event(event):
			get_viewport().set_input_as_handled()
		# Checkbox/tab keys belong to the popover; gameplay hotkeys wait.
		return
	if character_intro.blocks_input():
		if character_intro.allows_dialogue():
			if event is InputEventKey and event.is_pressed() \
					and (event as InputEventKey).physical_keycode == KEY_ESCAPE:
				AppState.close_dialogue()
				character_intro.dismiss_conversation()
				get_viewport().set_input_as_handled()
			return # Dialogue buttons and their keyboard navigation remain usable.
		if character_intro.playing and event is InputEventKey and event.is_pressed() \
				and (event as InputEventKey).physical_keycode == KEY_ESCAPE:
			character_intro.finish(camera_rig, actor_nodes.get(AppState.local_actor_id) as Node3D)
		get_viewport().set_input_as_handled()
		return
	if _trailer_capture_enabled and event is InputEventKey and (event as InputEventKey).pressed \
			and not (event as InputEventKey).echo \
			and (event as InputEventKey).physical_keycode == TRAILER_CAPTURE_KEY:
		_cycle_trailer_capture()
		get_viewport().set_input_as_handled()
		return
	# A drag can end over a window that consumes the release before gui_input.
	if event is InputEventMouseButton and not event.pressed \
			and event.button_index == MOUSE_BUTTON_MIDDLE:
		camera_rig.handle_mouse_button(event as InputEventMouseButton)
	if technique_ring != null:
		if technique_ring.call("handle_event", event):
			_stop_keyboard_movement()
			get_viewport().set_input_as_handled()
			return
		if technique_ring.visible: return
	if spell_wheel != null:
		if spell_wheel.handle_event(event):
			_set_attack_modifier(false)
			get_viewport().set_input_as_handled()
			return
		if spell_wheel.visible: return
	if window_stack != null:
		window_stack.handle_pointer(event)
	# Camera arrows belong to the world before GUI navigation can focus a button.
	# Consume repeats too; motion itself is sampled once per frame below.
	if event is InputEventKey and _keyboard_camera_allowed():
		for action: String in CAMERA_ACTIONS:
			if event.is_action(action, true):
				get_viewport().set_input_as_handled()
				return
	if event is InputEventKey and (event as InputEventKey).echo:
		return
	_track_attack_modifier(event)
	if _handle_bound_action(event):
		get_viewport().set_input_as_handled()

## Each ring may open (and stay open) only while the other is shut; the rest
## of the rules are the same for both (`_ring_allowed`).
func _can_open_technique_ring() -> bool:
	return _ring_allowed() and not (spell_wheel != null and spell_wheel.visible)

func _can_open_spell_wheel() -> bool:
	return _ring_allowed() and not (technique_ring != null and technique_ring.visible)

func _ring_allowed() -> bool:
	return game_view.visible and not _world_input_blocked() and not _text_entry_active() \
		and not popup_panel.visible and not purchase_confirm.visible \
		and not dialogue_panel.visible and not trade_panel.visible \
		and not storage_panel.visible and not full_map.visible \
		and not console_panel.visible and not settings_panel.visible \
		and not item_lists_panel.visible and not magic_selection.popup.visible

func _spell_wheel_anchor() -> Vector2:
	var actor_position: Variant = _actor_effect_position(AppState.local_actor_id)
	if actor_position is Vector3 and gameplay_camera != null:
		var body: Vector3 = actor_position + Vector3(0, 0.9, 0)
		if not gameplay_camera.is_position_behind(body):
			var point := gameplay_camera.unproject_position(body)
			return viewport_container.get_global_transform() * (point * viewport_container.size / Vector2(main_viewport.size))
	return viewport_container.get_global_rect().get_center()

## Watches Alt so the move icon can say what a click would do. Every key and
## mouse event carries the modifier state it was sent with, and Alt itself
## arrives as a key event of its own, so both are read here rather than polled.
func _track_attack_modifier(event: InputEvent) -> void:
	if event is InputEventKey:
		var key: InputEventKey = event as InputEventKey
		if key.physical_keycode == KEY_ALT or key.keycode == KEY_ALT:
			_set_attack_modifier(key.pressed)
		else:
			_set_attack_modifier(key.alt_pressed)
	elif event is InputEventWithModifiers:
		_set_attack_modifier((event as InputEventWithModifiers).alt_pressed)

func _set_attack_modifier(held: bool) -> void:
	if _alt_attack_preview == held:
		return
	_alt_attack_preview = held
	_sync_hud_button_states(true)

## Alt-tabbing away leaves the key down as far as this client is concerned,
## and the release lands in another window. The icon would stay on attack.
func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT 			or what == NOTIFICATION_WM_WINDOW_FOCUS_OUT:
		_set_attack_modifier(false)
		_cancel_full_map_drag()
		if is_instance_valid(camera_rig):
			camera_rig.cancel_rotation()
		for action: String in CAMERA_ACTIONS:
			Input.action_release(action)

## Bindings that have to beat a focused HUD control, which is why they are
## resolved here instead of in _unhandled_input().
##
## Every branch is an InputMap action. Raw keycode comparisons used to shadow
## `toggle_inventory`, `turn_left` and `turn_right`, so rebinding those actions
## appeared to work and changed nothing, while `toggle_map`, `toggle_minimap`
## and `toggle_console` were resolved twice - once by keycode here and once by
## action in _unhandled_input(). Returns true when the event was consumed.
func _handle_bound_action(event: InputEvent) -> bool:
	if settings_window != null and not str(settings_window.get("capturing")).is_empty():
		return false
	var focus := get_viewport().gui_get_focus_owner()
	if (focus is LineEdit or focus is TextEdit or focus is RichTextLabel) \
			and (event.is_action_pressed("ui_copy", false, true) \
			or event.is_action_pressed("ui_cut", false, true) \
			or event.is_action_pressed("ui_paste", false, true) \
			or event.is_action_pressed("ui_text_select_all", false, true)):
		return false # Text controls own clipboard shortcuts, even if rebound.
	# F2 is useful while composing a reply too, and never opens on key repeat.
	if game_view.visible and event.is_action_pressed("open_last_url", false, true):
		var result: Error = reference_window.call("open_last_url")
		if result == ERR_DOES_NOT_EXIST:
			AppState.append_local_message("No URLs have appeared in chat this session.")
		elif result != OK:
			AppState.append_local_message("Could not open the browser. Use URLs to copy the link.")
		return true
	# A focused text field owns its own characters and its own clipboard
	# shortcuts. Several of these actions default to bare printable keys, so
	# without this a backtick typed into chat would also open the console.
	if _text_entry_active():
		if event.is_action_pressed("cancel") and chat_input.has_focus():
			_hide_chat_input()
			return true
		return false
	# Connection control is reachable before the world exists, so it is
	# resolved ahead of the game-view gate below.
	if event.is_action_pressed("connect"):
		_on_connect_pressed()
		return true
	if event.is_action_pressed("disconnect"):
		_on_disconnect_pressed()
		return true
	if not game_view.visible:
		return false
	if event.is_action_pressed("toggle_range_lock", false, true):
		var lock_box: CheckBox = _banner_option_boxes["ranging_lock"] as CheckBox
		lock_box.button_pressed = not lock_box.button_pressed
		return true
	# Before focused HUD buttons. Text entry and key
	# capture were excluded above; Ctrl+R remains the guild window shortcut.
	var mount_request := preload("res://src/mounts/mount_hotkeys.gd").request_for_event(
		event, AppState.actor_mounts.get(AppState.local_actor_id, {}))
	if not mount_request.is_empty():
		Network.send_chat(mount_request)
		return true
	# After leaving typing, a separate Escape discards the draft before
	# the same press can close another window.
	if event.is_action_pressed("cancel") and not chat_input.text.is_empty():
		chat_input.clear()
		_hide_chat_input()
		return true
	if event.is_action_pressed("toggle_exchange", false, true):
		extension_windows.call("toggle_marketplace")
		return true
	if event.is_action_pressed("toggle_storage_preview", false, true):
		_toggle_storage_preview()
		return true
	if event.is_action_pressed("toggle_inventory"):
		_on_inventory_button_pressed()
		return true
	# Exact match: the map is a bare Tab, so Alt+Tab (switching windows),
	# Ctrl+Tab and Shift+Tab do not open it as well.
	if event.is_action_pressed("toggle_map", false, true):
		_toggle_full_map()
		return true
	if event.is_action_pressed("toggle_minimap"):
		_toggle_minimap()
		return true
	if event.is_action_pressed("toggle_console"):
		_toggle_console()
		return true
	# Exact match, and ahead of turn_right: turning is a bare E, and Godot
	# matches an action without comparing modifiers unless it is asked to, so
	# Ctrl+E would otherwise turn the player as well as open the encyclopedia.
	if event.is_action_pressed("toggle_encyclopedia", false, true):
		_on_encyclopedia_button_pressed()
		return true
	if event.is_action_pressed("recenter_viewport"):
		_recenter_viewport_on_player()
		return true
	if event.is_action_pressed("turn_left"):
		_turn_local_actor(true)
		return true
	if event.is_action_pressed("turn_right"):
		_turn_local_actor(false)
		return true
	if event.is_action_pressed("cancel") and console_panel.visible:
		console_panel.hide()
		return true
	return false

func _recenter_viewport_on_player() -> void:
	_update_local_actor_follow()

func _unhandled_input(event: InputEvent) -> void:
	if _actor_hud_menu != null and _actor_hud_menu.visible:
		return
	if _world_input_blocked():
		return
	if not game_view.visible:
		return
	# While the settings window is waiting for a key, every key press belongs
	# to it: otherwise rebinding "attack" would attack.
	if settings_window != null and not str(settings_window.get("capturing")).is_empty():
		if event is InputEventKey and (event as InputEventKey).pressed:
			settings_window.call("apply_capture", event)
			get_viewport().set_input_as_handled()
		return
	for spell_slot: int in range(SPELL_QUICK_SLOTS):
		if event.is_action_pressed("quick_spell_%d" % (spell_slot + 1)):
			# A blocked spell still owns its shortcut; it must never use an item.
			if _can_open_spell_wheel():
				_cast_spell_slot(spell_slot)
			get_viewport().set_input_as_handled()
			return
	if event.is_action_pressed("screenshot"):
		_save_screenshot()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("attack_selected"):
		_attack_selected_actor()
		get_viewport().set_input_as_handled()
		return
	for slot: int in range(8):
		# Compare modifiers too, including when the spell shortcut was rebound.
		if event.is_action_pressed("quick_item_%d" % (slot + 1), false, true):
			# Text controls can leave Ctrl+number unhandled; typing must not use an item.
			if not _text_entry_active():
				_use_inventory_slot(slot)
			get_viewport().set_input_as_handled()
			return
	# toggle_map, toggle_minimap and toggle_console are deliberately absent:
	# _handle_bound_action() owns them so they can be rebound. Seeing through
	# obstacles is not offered for rebinding, so it is still resolved here.
	if event.is_action_pressed("toggle_show_through_obstacles"):
		_toggle_show_through_obstacles()
		get_viewport().set_input_as_handled()
		return
	# The legacy window keys, each opening the window Eternal Lands binds it
	# to. They are resolved here rather than in _handle_bound_action() so a
	# focused text field keeps its own Ctrl shortcuts (Ctrl+A selects text
	# before it opens the statistics). They must also run before chat_focus:
	# that action is a bare T, Godot's inexact matching lets a bare binding
	# claim a modified press, and Ctrl+T would focus the chat instead of
	# opening the ranging window - the turn_right/Ctrl+E collision over again.
	var window_actions: Array[Array] = [
		["toggle_spells", _on_spells_button_pressed],
		["toggle_summoning", _on_summoning_button_pressed],
		["toggle_manufacture", _on_manufacturing_button_pressed],
		["toggle_emotes", _on_emotes_button_pressed],
		["toggle_quest_journal", _on_quest_button_pressed],
		["toggle_buddy", _on_buddy_button_pressed],
		["toggle_stats", _on_stats_button_pressed],
		["toggle_ranging", _on_ranging_button_pressed],
		["toggle_techniques", _on_techniques_button_pressed],
		["toggle_help", _on_help_button_pressed],
		["toggle_notepad", _on_info_button_pressed],
		["toggle_options", _on_options_pressed],
		["toggle_mail", func() -> void: extension_windows.call("toggle_mail")],
		["toggle_party", func() -> void: extension_windows.call("toggle_party")],
		["toggle_guild", func() -> void: guild_window.call("toggle")],
		["toggle_leaderboards", func() -> void: leaderboards_window.call("toggle")],
		["toggle_achievements",
			func() -> void: extension_windows.call("toggle_achievements")]]
	for action_and_handler: Array in window_actions:
		if event.is_action_pressed(str(action_and_handler[0]), false, true):
			(action_and_handler[1] as Callable).call()
			get_viewport().set_input_as_handled()
			return
	# Not a window: it asks the server to open its own summon-behaviour popup.
	# Resolved here with the window keys because it is the same kind of Ctrl
	# binding and wants the same place in the order.
	if event.is_action_pressed("summon_behavior"):
		_request_summon_behavior()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("combat_target"):
		_request_combat_target()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("chat_focus"):
		_show_chat_input()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("cancel"):
		if popup_panel.visible:
			# The popup is modal: it takes the cancel before anything under it.
			_on_popup_dismiss_pressed()
		elif not magic_selection.pending.is_empty() or not magic_selection.active_target_cast.is_empty():
			magic_selection.cancel()
		elif bool(AppState.autocast.get("active", false)):
			# Escape stops repeat casting before it closes anything else.
			Network.magic_request({"op": "cancel"})
		elif extension_windows != null and extension_windows.close_top():
			pass
		elif player_info_panel != null and player_info_panel.is_open():
			player_info_panel.close()
		elif spells_window != null and bool(spells_window.call("is_open")):
			spells_window.call("close")
		elif summoning_window != null and bool(summoning_window.call("is_open")):
			summoning_window.call("close")
		elif emotes_window != null and bool(emotes_window.call("is_open")):
			emotes_window.call("close")
		elif mounts_window != null and bool(mounts_window.call("is_open")):
			mounts_window.call("close")
		elif ranging_window != null and bool(ranging_window.call("is_open")):
			ranging_window.call("close")
		elif techniques_panel != null and str(techniques_panel.get("pending_key")) != "":
			techniques_panel.call("cancel_pending")
		elif leaderboards_window != null and bool(leaderboards_window.call("is_open")):
			leaderboards_window.call("close")
		elif guild_window != null and bool(guild_window.call("is_open")):
			guild_window.call("close")
		elif settings_window != null and settings_window.is_open():
			settings_window.close()
		elif reference_window != null and reference_window.is_open():
			reference_window.close()
		elif _has_carry():
			_cancel_carry()
		elif _interaction_mode != "walk" and not bool(AppState.trade.get("open", false)):
			_reset_world_action()
		elif chat_input.has_focus():
			_hide_chat_input()
		elif settings_panel.visible:
			_close_settings()
		elif console_panel.visible:
			console_panel.hide()
		elif dialogue_panel.visible:
			AppState.close_dialogue()
		elif bool(AppState.trade.get("open", false)):
			_on_trade_cancel_pressed()
		elif bool(AppState.storage.get("open", false)):
			_on_storage_close_pressed()
		elif bool(AppState.ground_bag.get("open", false)):
			_close_ground_bag()
		elif item_lists_panel.visible:
			item_lists_panel.hide()
		elif manufacturing_panel.visible:
			manufacturing_panel.hide()
		elif inventory_panel.visible:
			inventory_panel.hide()
		elif stats_panel.visible:
			stats_panel.hide()
		elif full_map.visible:
			full_map.hide()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("toggle_sit"):
		var local_actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
		var wants_to_sit: bool = not bool(local_actor.get("sitting", false))
		var sit_error: Error = Network.set_sitting(wants_to_sit)
		if sit_error != OK:
			push_warning("SIT_DOWN failed: " + error_string(sit_error))
		get_viewport().set_input_as_handled()
		return

func _on_world_gui_input(event: InputEvent) -> void:
	if _world_input_blocked():
		viewport_container.accept_event()
		return
	if event is InputEventMouseButton and not event.pressed \
			and event.button_index == MOUSE_BUTTON_MIDDLE:
		camera_rig.handle_mouse_button(event as InputEventMouseButton)
	if (not game_view.visible or full_map.visible
			or trade_panel.visible
			or manufacturing_panel.visible):
		# The world takes no clicks behind these windows, but a right click
		# on it still puts back whatever is in hand, as it does everywhere.
		if (game_view.visible and _has_carry() and event is InputEventMouseButton
				and (event as InputEventMouseButton).pressed
				and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_RIGHT):
			_cancel_carry()
			viewport_container.accept_event()
		return
	if event is InputEventMouseButton:
		var mouse_button: InputEventMouseButton = event as InputEventMouseButton
		if mouse_button.button_index == MOUSE_BUTTON_RIGHT:
			if mouse_button.pressed:
				if not magic_selection.pending.is_empty() or not magic_selection.active_target_cast.is_empty():
					magic_selection.cancel()
				elif _has_carry():
					_cancel_carry()
				elif AppState.authenticated and _pick_actor(_local_viewport_position(mouse_button.position)) == AppState.local_actor_id:
					_open_actor_hud_menu(mouse_button.position)
				else:
					_cycle_world_action(_local_viewport_position(mouse_button.position))
			viewport_container.accept_event()
			return
		if camera_rig.handle_mouse_button(mouse_button):
			viewport_container.accept_event()
			return
		if mouse_button.pressed and mouse_button.button_index == MOUSE_BUTTON_LEFT:
			_handle_world_click(mouse_button, _local_viewport_position(mouse_button.position))
			viewport_container.accept_event()
	elif event is InputEventMouseMotion:
		var mouse_motion: InputEventMouseMotion = event as InputEventMouseMotion
		if camera_rig.handle_mouse_motion(mouse_motion):
			viewport_container.accept_event()

func _open_actor_hud_menu(local_position: Vector2) -> void:
	if _banner_option("menu_disabled"):
		return
	_sync_banner_context_menu()
	_stop_keyboard_movement()
	_actor_hud_menu.open_at(viewport_container.get_global_transform() * local_position)

func _configure_banner_menu() -> void:
	for key: String in BANNER_OPTION_NODES:
		var box: CheckBox = get_node("%" + str(BANNER_OPTION_NODES[key])) as CheckBox
		box.set_pressed_no_signal(bool(BANNER_OPTION_DEFAULTS[key]))
		box.toggled.connect(_on_banner_option_toggled)
		_banner_option_boxes[key] = box
	_actor_hud_menu = BannerDisplayMenuScript.new()
	game_view.add_child(_actor_hud_menu)
	_actor_hud_menu.option_changed.connect(func(group: String, key: String, value: bool) -> void:
		if group == "mount":
			_set_mount_banner_option(key, value)
		elif _banner_option_boxes.has(key):
			(_banner_option_boxes[key] as CheckBox).button_pressed = value)
	_actor_hud_menu.mounts_requested.connect(func() -> void: mounts_window.call("open"))
	_actor_hud_menu.settings_requested.connect(func() -> void: settings_window.open_tab("Banners"))
	_actor_hud_menu.color_changed.connect(func(item: String, color: Color) -> void:
		hud_workspace.change_banner_color(item, color))
	_actor_hud_menu.color_sync_changed.connect(func(item: String, enabled: bool) -> void:
		hud_workspace.set_banner_color_sync(item, enabled))
	_actor_hud_menu.color_sync_all_changed.connect(func(enabled: bool) -> void:
		hud_workspace.set_banner_color_sync("all", enabled))
	_actor_hud_menu.colors_reset_requested.connect(func() -> void: hud_workspace.reset_banner_colors())
	_connect_banner_context_inputs(actor_resource_overlay, "Character")

func _connect_banner_context_inputs(control: Control, section: String) -> void:
	if control == mount_status:
		section = "Mount"
	if not control is BaseButton:
		control.mouse_filter = Control.MOUSE_FILTER_PASS
	control.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT \
				and AppState.authenticated and (section == "Mount" or not _banner_option("menu_disabled")):
			_sync_banner_context_menu()
			_stop_keyboard_movement()
			_actor_hud_menu.open_at(control.get_global_transform() * event.position, section)
			control.accept_event())
	for child: Node in control.get_children():
		if child is Control:
			_connect_banner_context_inputs(child, section)

func _sync_banner_context_menu() -> void:
	if _actor_hud_menu == null:
		return
	var character := {}
	for key: String in BANNER_OPTION_NODES:
		character[key] = _banner_option(key)
	_actor_hud_menu.sync_options(character, _mount_banner_options)
	_sync_banner_color_controls()

func _banner_item_color(item: String, fallback: Color) -> Color:
	if hud_workspace == null:
		return fallback
	return BannerColors.resolve(item, hud_workspace.model.working.get("banner_colors", {}),
		hud_workspace.model.working.resource_colors, fallback)

func _sync_banner_color_controls() -> void:
	if hud_workspace == null:
		return
	var options: Dictionary = hud_workspace.model.working.get("banner_colors", {})
	var resources: Dictionary = hud_workspace.model.working.resource_colors
	_actor_hud_menu.color_controls.sync_colors(options, resources)
	settings_window.restore_banner_colors(options, resources)

func _apply_banner_colors() -> void:
	for row_spec: Array in BANNER_ROWS:
		var row := _banner_row(str(row_spec[0]))
		var bar := row.get_node("Bar") as ProgressBar
		var item := str(row_spec[3])
		_paint_banner_row(row, _banner_item_color(item, _banner_colour(item, bar.value / maxf(1, bar.max_value))))
	var dto: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	overhead_player_name.add_theme_color_override("font_color", _banner_item_color("name",
		EloriaProtocol.el_text_colour(int(dto.get("name_colour", 0)))))
	mount_status.status.add_theme_color_override("font_color", _banner_item_color("mount", Color.WHITE))

func _set_mount_banner_option(key: String, value: bool) -> void:
	if not _mount_banner_options.has(key):
		return
	_mount_banner_options[key] = value
	mount_status.set_options(_mount_banner_options)
	_sync_banner_context_menu()
	_save_hud_settings()

func _banner_option(key: String) -> bool:
	var box_value: Variant = _banner_option_boxes.get(key)
	if box_value is CheckBox:
		return (box_value as CheckBox).button_pressed
	return bool(BANNER_OPTION_DEFAULTS.get(key, false))

func _on_banner_option_toggled(_enabled: bool) -> void:
	_apply_banner_options()
	_sync_banner_context_menu()
	# The R indicator letter reads the ranging-lock switch, so it follows the
	# toggle rather than waiting for the next unrelated state change.
	_sync_hud_indicators()
	_save_hud_settings()

## Settings keeps the character's right-click entry point recoverable.
func _on_banner_menu_enabled_toggled(pressed: bool) -> void:
	var box: CheckBox = _banner_option_boxes["menu_disabled"] as CheckBox
	box.set_pressed_no_signal(not pressed)
	_apply_banner_options()
	_save_hud_settings()

## Called for every switch on the banner menu because EL's options are not
## independent of one another: a row disappears once both its bar and its
## numbers are off, the panel is only as tall as the rows left standing, and
## instance mode selects its own creature preferences and hides other players.
func _apply_banner_options() -> void:
	overhead_player_name.visible = _banner_option("show_names")
	for row_spec: Array in BANNER_ROWS:
		var row: HBoxContainer = _banner_row(str(row_spec[0]))
		var show_bar: bool = _banner_option(str(row_spec[1]))
		var show_numbers: bool = _banner_option(str(row_spec[2]))
		(row.get_node("Bar") as ProgressBar).visible = show_bar
		(row.get_node("Number") as Label).visible = show_numbers
		row.visible = show_bar or show_numbers
	_apply_banner_background()
	_apply_banner_colors()
	for id: Variant in actor_nodes:
		var node_value: Variant = actor_nodes[id]
		if node_value is ReplicatedActor3D and is_instance_valid(node_value as ReplicatedActor3D):
			var actor: ReplicatedActor3D = node_value as ReplicatedActor3D
			_apply_actor_banner_options(int(id), actor)
			if not _banner_option("speech_bubbles"):
				actor.clear_speech_bubble()
	_layout_actor_resource_overlay()
	_update_actor_resource_overlay()
	_animation_gate_refresh_msec = 0

func _creature_banner_profile() -> Dictionary:
	return _creature_banner_options["instance" if _banner_option("instance_mode") else "normal"]

func _apply_actor_banner_options(id: int, actor: ReplicatedActor3D) -> void:
	actor.set_nameplate_visible(_nameplate_visible_for(id))
	var dto: Dictionary = AppState.actors.get(id, {})
	actor.set_banner_parts(_creature_banner_profile() \
		if int(dto.get("kind", 0)) == ReplicatedActor3D.CREATURE_ACTOR_KIND else {})

## EL draws a flat black rectangle behind the banner when the alpha background
## is on (actors.c) and nothing at all when it is off, so the switch swaps the
## panel style rather than hiding the panel.
func _apply_banner_background() -> void:
	if _banner_background_style == null:
		var style := StyleBoxFlat.new()
		style.bg_color = Color(0.0, 0.0, 0.0, 0.6)
		style.set_content_margin_all(2.0)
		style.content_margin_left = 6.0
		style.content_margin_right = 6.0
		_banner_background_style = style
	if _banner_option("banner_background"):
		actor_resource_overlay.add_theme_stylebox_override(
			"panel", _banner_background_style)
		return
	var empty := StyleBoxEmpty.new()
	empty.set_content_margin_all(2.0)
	empty.content_margin_left = 6.0
	empty.content_margin_right = 6.0
	actor_resource_overlay.add_theme_stylebox_override("panel", empty)

## Local chat arrives already formatted as "Speaker: what they said", which is
## the same shape EL parses in text.c before handing the remainder to the
## speaker's overtext. Anything without a name that matches a visible actor is
## left in the chat log alone.
func _capture_speech_bubble_from_chat() -> void:
	if not _banner_option("speech_bubbles") or AppState.chat_lines.is_empty():
		return
	var line: Dictionary = AppState.chat_lines.back() as Dictionary
	if not _chat_line_allowed(line):
		return
	if int(line.get("channel", -1)) != 0:
		return
	var text: String = str(line.get("text", ""))
	var separator: int = text.find(": ")
	if separator <= 0:
		return
	var speaker: String = text.substr(0, separator).strip_edges()
	var spoken: String = text.substr(separator + 2).strip_edges()
	if spoken.is_empty():
		return
	for id: Variant in AppState.actors:
		var dto: Dictionary = AppState.actors[id] as Dictionary
		if str(dto.get("name", "")) != speaker:
			continue
		var node_value: Variant = actor_nodes.get(id)
		if node_value is ReplicatedActor3D and is_instance_valid(
				node_value as ReplicatedActor3D):
			(node_value as ReplicatedActor3D).show_speech_bubble(
				spoken, SPEECH_BUBBLE_MSEC)
		return

## Range lock holds position with a bow or crossbow equipped, while still
## allowing target clicks to shoot. Sit lock also blocks attacks that could
## stand the player up; Ctrl deliberately overrides that lock.
func _movement_locked(ctrl_pressed: bool) -> bool:
	return _actor_input_locked(ctrl_pressed) \
		or (_banner_option("ranging_lock") and _range_weapon_equipped())

func _actor_input_locked(ctrl_pressed: bool) -> bool:
	if _world_input_blocked():
		return true
	var local_actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	if bool(AppState.death.get("dead", false)) or int(local_actor.get("health", 1)) <= 0:
		return true
	if (_banner_option("sit_lock") and not ctrl_pressed
			and bool(local_actor.get("sitting", false))):
		return true
	return false

func _range_weapon_equipped() -> bool:
	var local_actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	var appearance: Dictionary = local_actor.get("appearance", {}) as Dictionary
	var weapon: int = int(appearance.get("weapon", 0))
	return weapon >= RANGE_WEAPON_FIRST and weapon <= RANGE_WEAPON_LAST

func _banner_row(row_name: String) -> HBoxContainer:
	return actor_resource_overlay.get_node("Rows/" + row_name) as HBoxContainer

## Creature banners use their own normal/instance choices. Other actors keep
## the character name switch and instance display's existing suppression.
func _nameplate_visible_for(actor_id: int) -> bool:
	if actor_id == AppState.local_actor_id:
		return false
	if not _nameplates_enabled or _trailer_capture_level >= 2:
		return false
	var dto: Dictionary = AppState.actors.get(actor_id, {})
	if int(dto.get("kind", 0)) == ReplicatedActor3D.CREATURE_ACTOR_KIND:
		return bool(_creature_banner_profile().visible)
	if _banner_option("instance_mode"):
		return false
	return _banner_option("show_names")

## Which actor the player is actually fighting. A health pair rides on every
## actor packet, so the client could draw a bar over everything in sight - but
## a field of bars says nothing, and the one that has to be readable at a
## glance is the target's. A ranged shot lined up on someone counts as
## fighting them, and takes precedence the same way the target readout does.
func _combat_target_actor_id() -> int:
	var local_actor: Dictionary = AppState.actors.get(
		AppState.local_actor_id, {}) as Dictionary
	var aiming_at: int = int(local_actor.get("aiming_at", -1))
	if aiming_at >= 0:
		return aiming_at
	if bool(AppState.combat_state.get("active", false)):
		return int(AppState.combat_state.get("target_id", -1))
	return -1

## Who wears a health bar over their head. Anything that can fight does:
## another player, whether or not you are fighting them, and any creature.
## Scenery does not. The server gives a shopkeeper or a gate warden 20 of 20
## health like everybody else (`NPCActor` in the server's world.py), so the
## client used to hang a full bar over every trader in a market - a row of
## bars that never move and say nothing. They keep a bare name, unless you
## have actually picked a fight with one, which the combat packets say.
##
## The three answers are the minimap's own, so the map and the field agree
## about which of them each actor is.
func _overhead_health_for(actor_id: int, dto: Dictionary,
		target_id: int) -> bool:
	if actor_id == target_id:
		return true
	return _minimap_actor_type(dto) != &"npc"

## Hands every actor its answer to those questions. A pass over the actors one
## frame changed uses `_sync_overhead_health_for` instead.
func _sync_overhead_health() -> void:
	var target_id: int = _combat_target_actor_id()
	_overhead_target_actor = target_id
	for id: Variant in actor_nodes:
		var node_value: Variant = actor_nodes[id]
		if not (node_value is ReplicatedActor3D) or not is_instance_valid(
				node_value as ReplicatedActor3D):
			continue
		var actor := node_value as ReplicatedActor3D
		actor.set_combat_target(int(id) == target_id)
		actor.set_health_visible(
			_overhead_health_for(int(id),
				AppState.actors.get(id, {}) as Dictionary, target_id))

## Eternal Lands makes every bar as long as the widest number string beside it
## so the rows line up, then sizes the banner to whatever is left switched on.
## Godot keeps a container at whatever size it was last given, so the explicit
## reset_size() is what actually shrinks the box when a row goes away.
func _layout_actor_resource_overlay() -> void:
	var widest := BANNER_BAR_MIN_WIDTH
	for row_spec: Array in BANNER_ROWS:
		var row: HBoxContainer = _banner_row(str(row_spec[0]))
		if not row.visible:
			continue
		var number: Label = row.get_node("Number") as Label
		widest = maxf(widest, number.get_theme_font("font").get_string_size(
			number.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0,
			number.get_theme_font_size("font_size")).x)
	var bar_width: float = ceilf(widest)
	for row_spec: Array in BANNER_ROWS:
		var row: HBoxContainer = _banner_row(str(row_spec[0]))
		var bar: ProgressBar = row.get_node("Bar") as ProgressBar
		var number: Label = row.get_node("Number") as Label
		bar.custom_minimum_size.x = bar_width
		number.custom_minimum_size.x = bar_width
	actor_resource_overlay.reset_size()

func _on_chat_tab_pressed(tab: String) -> void:
	_chat_tab = tab
	chat_hud.select_tab(tab)
	if tab in ["general", "local"]:
		chat_hud.set_destination("local")
	elif tab in ["party", "guild", "private"] or tab.begins_with("channel:"):
		chat_hud.set_destination(tab)
	_sync_chat()
	chat_hud.open_chat()

func _on_channel_tab_pressed(channel_index: int) -> void:
	if channel_index < 0 or channel_index >= AppState.active_channels.size():
		return
	if int(AppState.active_channels[channel_index]) <= 0:
		return
	# The legacy selection packet has only three slots. Native sends address
	# the channel number explicitly, including the fourth membership.
	if channel_index < 3:
		var error: Error = Network.set_active_channel(channel_index)
		if error != OK:
			push_warning("SET_ACTIVE_CHANNEL failed: " + error_string(error))
		AppState.active_channel_index = channel_index
	_on_chat_tab_pressed("channel:%d" % int(AppState.active_channels[channel_index]))

func _sync_channel_tabs() -> void:
	_chat_tab = chat_hud.sync_channels(AppState.active_channels, _chat_tab)
	if chat_log_tabs != null:
		chat_log_tabs.sync(AppState.active_channels, AppState.chat_history)
	_sync_chat()

func _reveal_chat_messages() -> void:
	var line := _last_chat_line()
	if line.is_empty() or not _chat_line_allowed(line):
		return
	if _chat_line_shown(line):
		chat_hud.reveal_message(_formatted_chat_line(line), _chat_line_colour(line))
	if ChatMessages.kind(line) == "system" and not bool(chat_hud.options.get("combined", false)):
		system_chat_hud.reveal_message(_formatted_chat_line(line), _chat_line_colour(line))

func _on_minimap_gui_input(event: InputEvent) -> void:
	if _handle_minimap_drag(event):
		return
	if event is InputEventMouseButton:
		var wheel: InputEventMouseButton = event as InputEventMouseButton
		if wheel.pressed and (wheel.button_index == MOUSE_BUTTON_WHEEL_UP
				or wheel.button_index == MOUSE_BUTTON_WHEEL_DOWN):
			_zoom_minimap(wheel.button_index == MOUSE_BUTTON_WHEEL_UP)
			minimap.accept_event()
			return
	_handle_map_gui_input(event, minimap, map_viewport, map_camera, "minimap")

## The scroll wheel over the minimap changes how much ground it frames. The
## camera is orthographic, so its size is the width in metres directly.
func _zoom_minimap(closer: bool) -> void:
	var previous: float = _minimap_zoom
	var step: float = 1.0 / MINIMAP_ZOOM_STEP if closer else MINIMAP_ZOOM_STEP
	_minimap_zoom = clampf(_minimap_zoom * step,
		MINIMAP_ZOOM_MIN, MINIMAP_ZOOM_MAX)
	if is_equal_approx(previous, _minimap_zoom):
		return
	_apply_minimap_zoom()
	_save_hud_settings()

func _apply_minimap_zoom() -> void:
	map_camera.size = _minimap_zoom
	# The minimap render is throttled, so a zoom would otherwise not be seen
	# until the next scheduled frame.
	if minimap_frame.visible:
		map_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE

## The scroll wheel over the Tab map frames more or less of the continent
## around the region. Every region's picture stands whether or not it is
## loaded, so zooming out shows the neighbours, and a click out there walks
## the legs to it the way a click just past the seam always has. Magnifying
## past the default view holds the ground under the pointer in place.
func _zoom_full_map(closer: bool, at := Vector2.INF) -> void:
	if _full_map_base_size <= 0.0:
		return
	_cancel_full_map_drag()
	var pixel: Variant = null
	var anchor := Vector3.ZERO
	if at.is_finite():
		pixel = _texture_to_viewport_position(at, map_image, full_map_viewport.size)
		if not pixel is Vector2:
			return
		anchor = full_map_camera.project_ray_origin(pixel)
	var previous: float = _full_map_zoom
	var step: float = 1.0 / FULL_MAP_ZOOM_STEP if closer else FULL_MAP_ZOOM_STEP
	_full_map_zoom = clampf(_full_map_zoom * step, FULL_MAP_ZOOM_MIN,
		FULL_MAP_ZOOM_MAX if _full_map_zoomable else 1.0)
	# Always stop at the default framing when crossing it from either limit.
	if (previous < 1.0 and _full_map_zoom > 1.0) or (previous > 1.0 and _full_map_zoom < 1.0) \
			or is_equal_approx(_full_map_zoom, 1.0):
		_full_map_zoom = 1.0
	if is_equal_approx(previous, _full_map_zoom):
		return
	if _full_map_zoom < 1.0 and pixel is Vector2:
		full_map_camera.size = _full_map_base_size * _full_map_zoom
		_full_map_pan_position = full_map_camera.global_position + anchor \
			- full_map_camera.project_ray_origin(pixel)
		_full_map_panned = true
	else:
		_full_map_panned = false
	_apply_full_map_zoom()

func _apply_full_map_zoom() -> void:
	if _full_map_base_size <= 0.0:
		return
	full_map_camera.size = _full_map_base_size * _full_map_zoom
	_update_full_map_focus()
	map_marker_overlay.configure(full_map_camera, adapter, full_map_viewport.size)
	_request_map_redraw()

func _update_full_map_focus() -> void:
	if _full_map_base_size <= 0.0:
		return
	var focus := _full_map_base_position
	if _full_map_zoom < 1.0:
		if _full_map_panned:
			focus.x = _full_map_pan_position.x
			focus.z = _full_map_pan_position.z
		else:
			var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
			if is_instance_valid(actor_value) and actor_value is Node3D:
				var actor := actor_value as Node3D
				focus.x = actor.global_position.x
				focus.z = actor.global_position.z
	full_map_camera.global_position = focus

func _cancel_full_map_drag() -> void:
	_full_map_pan_press = null
	_full_map_pan_dragging = false

func _handle_full_map_pan_input(event: InputEvent) -> bool:
	if _full_map_zoom >= 1.0 or _full_map_base_size <= 0.0 or _map_input_blocked():
		_cancel_full_map_drag()
		return false
	if event is InputEventMouseButton:
		var mouse := event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return false
		var pixel: Variant = _texture_to_viewport_position(mouse.position, map_image, full_map_viewport.size)
		if mouse.pressed:
			if pixel is Vector2:
				_full_map_pan_press = mouse.duplicate() as InputEventMouseButton
				_full_map_pan_origin = full_map_camera.global_position
				_full_map_pan_dragging = false
		elif _full_map_pan_press != null:
			_pan_full_map(mouse.position)
			var click := _full_map_pan_press if not _full_map_pan_dragging else null
			_cancel_full_map_drag()
			if click != null and pixel is Vector2:
				_handle_map_gui_input(click, map_image, full_map_viewport, full_map_camera, "full_map")
		return true
	if event is InputEventMouseMotion and _full_map_pan_press != null:
		var motion := event as InputEventMouseMotion
		if (motion.button_mask & MOUSE_BUTTON_MASK_LEFT) == 0:
			_cancel_full_map_drag()
			return false
		_pan_full_map(motion.position)
		return true
	return false

## Translate the camera opposite the pointer so the grabbed ground follows
## the hand. Use the displayed image size, including rectangular letterboxing,
## and ray origins so the drag works at every zoom and window scale.
func _pan_full_map(at: Vector2) -> void:
	var drag := at - _full_map_pan_press.position
	if not _full_map_pan_dragging and drag.length() < FULL_MAP_PAN_THRESHOLD:
		return
	var target := Vector2(full_map_viewport.size)
	var displayed := map_image.size
	if map_image.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT_CENTERED:
		displayed = target * minf(displayed.x / target.x, displayed.y / target.y)
	if displayed.x <= 0.0 or displayed.y <= 0.0:
		return
	var pixels := drag * target / displayed
	var world_delta := full_map_camera.project_ray_origin(pixels) - full_map_camera.project_ray_origin(Vector2.ZERO)
	_full_map_pan_position = _full_map_pan_origin - world_delta
	_full_map_panned = true
	_full_map_pan_dragging = true
	_update_full_map_focus()
	map_marker_overlay.queue_redraw()
	_request_map_redraw()
	map_image.tooltip_text = ""
	map_coordinates.text = "Coordinates: —"

func _on_full_map_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var wheel: InputEventMouseButton = event as InputEventMouseButton
		if wheel.pressed and (wheel.button_index == MOUSE_BUTTON_WHEEL_UP
				or wheel.button_index == MOUSE_BUTTON_WHEEL_DOWN):
			_zoom_full_map(wheel.button_index == MOUSE_BUTTON_WHEEL_UP, wheel.position)
			_update_full_map_cursor(wheel.position)
			map_image.accept_event()
			return
	if _handle_full_map_pan_input(event):
		if event is InputEventMouseMotion or event is InputEventMouseButton:
			_update_full_map_cursor(event.position)
		map_image.accept_event()
		return
	if event is InputEventMouseMotion:
		var mouse_motion: InputEventMouseMotion = event as InputEventMouseMotion
		_update_full_map_cursor(mouse_motion.position)
		return
	_handle_map_gui_input(event, map_image, full_map_viewport, full_map_camera, "full_map")

func _update_full_map_cursor(at: Vector2) -> void:
	_full_map_cursor_inside = true
	_full_map_cursor_position = at
	map_cursor_coordinates.hide()
	map_image.tooltip_text = map_marker_overlay.label_at(at)
	var pixel: Variant = _texture_to_viewport_position(at, map_image, full_map_viewport.size)
	if not pixel is Vector2:
		map_coordinates.text = "Coordinates: outside map image"
		return
	var tile: Variant = _map_target_tile(full_map_camera, pixel)
	if tile is Vector2i:
		map_coordinates.text = "Coordinates: %d, %d" % [tile.x, tile.y]
		_show_map_cursor_coordinates(map_image, at, tile)
	else:
		map_coordinates.text = "Coordinates: outside walkable map"

func _show_map_cursor_coordinates(control: Control, at: Vector2, tile: Vector2i) -> void:
	map_cursor_coordinates.text = "X: %d, Y: %d" % [tile.x, tile.y]
	map_cursor_coordinates.reset_size()
	var margin := Vector2(4, 4)
	var maximum := (control.size - map_cursor_coordinates.size - margin).max(margin)
	map_cursor_coordinates.position = control.position + (at + Vector2(14, 18)).clamp(margin, maximum)
	map_cursor_coordinates.show()

func _on_full_map_visibility_changed() -> void:
	_cancel_full_map_drag()
	_full_map_cursor_inside = false
	map_cursor_coordinates.hide()

func _on_full_map_mouse_exited() -> void:
	_full_map_cursor_inside = false
	map_cursor_coordinates.hide()
	map_image.tooltip_text = ""
	if map_image.visible:
		map_coordinates.text = "Coordinates: —"

func _on_compass_gui_input(event: InputEvent, surface: Control = null) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse_button: InputEventMouseButton = event as InputEventMouseButton
	if not mouse_button.pressed or mouse_button.button_index != MOUSE_BUTTON_LEFT:
		return
	if _world_input_blocked():
		return
	var clicked: Control = compass_face if surface == null else surface
	var tile_value: Variant = _local_actor_server_tile()
	if not tile_value is Vector2i:
		AppState.append_local_message("Your position is not available yet.")
		clicked.accept_event()
		return
	var tile: Vector2i = tile_value as Vector2i
	var location: String = "%s (%d, %d)" % [_current_map_display_name, tile.x, tile.y]
	if mouse_button.shift_pressed:
		var message := _chat_message_for_tab("My Position: " + location)
		if message.is_empty():
			AppState.append_local_message("Select a chat destination before sharing your position.")
		else:
			var share_error: Error = Network.send_private_message(message.substr(1)) if message.begins_with("/") else Network.send_chat(message)
			if share_error != OK:
				AppState.append_local_message("Could not share your position: " + error_string(share_error))
	elif mouse_button.ctrl_pressed:
		if AppState.active_channel_number() <= 0:
			AppState.append_local_message(
				"Join or select a numeric channel before sharing your position.")
		else:
			var share_error: Error = Network.send_chat("@My Position: " + location)
			if share_error != OK:
				AppState.append_local_message(
					"Could not share your position: " + error_string(share_error))
	else:
		AppState.append_local_message("My Position: " + location)
	clicked.accept_event()

func _on_clock_gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse_button: InputEventMouseButton = event as InputEventMouseButton
	if not mouse_button.pressed or mouse_button.button_index != MOUSE_BUTTON_LEFT:
		return
	var date_error: Error = Network.request_server_date()
	var time_error: Error = Network.request_server_time()
	if date_error != OK or time_error != OK:
		AppState.append_local_message("Server date/time request failed: %s" %
			error_string(date_error if date_error != OK else time_error))
	clock_face.accept_event()

func _local_actor_server_tile() -> Variant:
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if not actor_value is Node3D or not is_instance_valid(actor_value as Node3D):
		return null
	return adapter.godot_to_server((actor_value as Node3D).global_position)

func _map_input_blocked() -> bool:
	return (_world_input_blocked() or not game_view.visible or trade_panel.visible
		or manufacturing_panel.visible)

func _handle_map_gui_input(event: InputEvent, map_control: TextureRect,
		map_render_viewport: SubViewport, camera: Camera3D, source: String) -> void:
	if _map_input_blocked():
		return
	if not event is InputEventMouseButton:
		return
	var mouse_button: InputEventMouseButton = event as InputEventMouseButton
	if not mouse_button.pressed or mouse_button.button_index != MOUSE_BUTTON_LEFT:
		return
	var selecting_spell := not Network.magic_pending.is_empty() and Network.magic_scope in ["burst", "location"]
	if not selecting_spell and _movement_locked(mouse_button.ctrl_pressed):
		map_control.accept_event()
		return
	var viewport_position_value: Variant = _texture_to_viewport_position(
		mouse_button.position, map_control, map_render_viewport.size)
	if not viewport_position_value is Vector2:
		map_control.accept_event()
		return
	var viewport_position: Vector2 = viewport_position_value as Vector2
	var target_value: Variant = _map_target_tile(camera, viewport_position)
	print_debug("map_input source=", source, " local_click=", mouse_button.position,
		" viewport=", viewport_position, " server_tile=", target_value,
		" command=", "RUN_TO" if mouse_button.shift_pressed else "MOVE_TO")
	# Whose ground the click is on decides the walk, not whether it falls inside
	# this map's square of served cells: that square reaches far into every
	# neighbour's ground, so a click on the neighbour's side went to the server
	# as a walk on this map and stopped at the border.
	var click_point: Variant = _map_click_point(camera, viewport_position)
	var owner: String = _map_owning_point(click_point as Vector3) if click_point is Vector3 else ""
	var here_map: String = MapRegistry.normalize_server_map_id(AppState.current_map)
	var elsewhere: bool = (owner != here_map) if not owner.is_empty() else (
		target_value is Vector2i and not _tile_inside_current_map(target_value as Vector2i))
	if target_value is Vector2i and elsewhere:
		# Past the seam: the neighbour that owns the ground is walked to in legs,
		# the way a world click on its resident ground is.
		_map_click_beyond(camera, viewport_position, mouse_button.shift_pressed, source, owner)
		map_control.accept_event()
		return
	if target_value is Vector2i:
		exterior_stream.pending_walk.clear()
		_clear_keyboard_movement_tracking()
		_clear_local_turn_prediction()
		var move_error: Error = Network.move_to(target_value as Vector2i,
			mouse_button.shift_pressed)
		if move_error != OK:
			push_warning("%s MOVE_TO failed: %s" % [source, error_string(move_error)])
		elif not selecting_spell:
			_set_map_walk_target(MapRegistry.normalize_server_map_id(AppState.current_map), target_value)
	map_control.accept_event()

func _map_target_tile(camera: Camera3D, viewport_position: Vector2) -> Variant:
	var point: Variant = _map_click_point(camera, viewport_position)
	if not point is Vector3:
		return null
	return adapter.godot_to_server(point as Vector3)

## The ground under a map click: the navigation surface where the ray meets
## one, else the walking-height plane (the map cameras look straight down, so
## the plane gives the same x and z past the current map's ground).
func _map_click_point(camera: Camera3D, viewport_position: Vector2) -> Variant:
	if not is_instance_valid(camera):
		return null
	var ray_origin: Vector3 = camera.project_ray_origin(viewport_position)
	var ray_direction: Vector3 = camera.project_ray_normal(viewport_position)
	var point: Variant = _navigation_ray_position(ray_origin, ray_direction)
	if not point is Vector3:
		if absf(ray_direction.y) < 0.0001:
			return null
		var distance_to_ground: float = (adapter.walking_height - ray_origin.y) / ray_direction.y
		if distance_to_ground < 0.0:
			return null
		point = ray_origin + ray_direction * distance_to_ground
	return point

## The map whose own ground a point of the current map's frame stands on, by
## the territory outlines both maps draw as dashed lines; empty where no
## territory holds the point.
func _map_owning_point(point: Vector3) -> String:
	var region_index: int = _region_index_for_map(AppState.current_map)
	if region_index < 0 or not cartography is Dictionary:
		return ""
	var continent: Dictionary = (cartography as Dictionary).get("continent", {}) as Dictionary
	var origin: Array = continent.get("originMetres", []) as Array
	var metres_per_pixel: float = float(continent.get("metresPerPixel", 0.0))
	var translation: Array = (cartography_regions[region_index] as Dictionary).get("globalTranslation", []) as Array
	if origin.size() != 2 or metres_per_pixel <= 0.0 or translation.size() != 3:
		return ""
	var pixel := Vector2((point.x + float(translation[0]) - float(origin[0])) / metres_per_pixel,
		(point.z + float(translation[2]) - float(origin[1])) / metres_per_pixel)
	var frame: String = _cartography_frame(region_index)
	for index: int in range(cartography_regions.size()):
		if _cartography_frame(index) != frame:
			continue
		if CartographyOwnershipGeometry.contains(pixel, _region_polygon_components(index)):
			return MapRegistry.normalize_server_map_id(str(
				(cartography_regions[index] as Dictionary).get("serverMap", "")))
	return ""

## The continent frame a cartography row belongs to: empty for the continent
## the picture shows, "continent-v2" for the rebuilt one's territories. Their
## outlines share the picture's pixel lattice but no ground with it, so outlines
## are compared and drawn only within one frame.
func _cartography_frame(index: int) -> String:
	return str((cartography_regions[index] as Dictionary).get("frame", ""))

## A region's outline in continent picture pixels, built once per cartography.
func _region_polygon_components(index: int) -> Array[PackedVector2Array]:
	if _region_polygons.size() != cartography_regions.size():
		_region_polygons.clear()
		for region_value: Variant in cartography_regions:
			var row: Dictionary = region_value as Dictionary
			_region_polygons.append(CartographyOwnershipGeometry.polygons(
				row.get("continentPolygons", [row.get("continentPolygon", [])])))
	var result: Array[PackedVector2Array] = []
	result.assign(_region_polygons[index])
	return result

## Whether a tile lies inside the current map's served cells.
func _tile_inside_current_map(tile: Vector2i) -> bool:
	var manifest: WorldManifest = world_loader.manifest if world_loader != null else null
	var coordinates: Dictionary = manifest.data.get("coordinateTransform", {}) as Dictionary if manifest != null else {}
	return ExteriorRegionStream.tile_inside(coordinates, tile)

## A map click past the seam: the neighbour that holds the point gets the walk
## order in legs (the first to the surveyed crossing, the rest at the map
## change); a point no neighbour holds is not a place to walk to.
func _map_click_beyond(camera: Camera3D, viewport_position: Vector2, run: bool, source: String,
		owner := "") -> void:
	var point_value: Variant = _map_click_point(camera, viewport_position)
	if not point_value is Vector3 or _movement_locked(false):
		return
	var point: Vector3 = point_value as Vector3
	var beyond: Dictionary = exterior_stream.map_at_local(point, owner)
	if beyond.is_empty():
		print_debug("map_input source=", source, " beyond the seam, no region holds ", point)
		AppState.append_local_message("There is no map there to walk to.", 3)
		return
	var leg_value: Variant = exterior_stream.arm_walk_to(str(beyond.map), beyond.tile as Vector2i, run, point)
	if not leg_value is Vector3:
		print_debug("map_input source=", source, " no seamless road to ", beyond.map)
		AppState.append_local_message("No road leads from here to %s." % _region_name_for_map(str(beyond.map)), 3)
		return
	var leg: Vector3 = leg_value as Vector3
	_clear_keyboard_movement_tracking()
	_clear_local_turn_prediction()
	var selecting_spell := not Network.magic_pending.is_empty() and Network.magic_scope in ["burst", "location"]
	var move_error: Error = Network.move_to(adapter.godot_to_server(leg), run)
	if move_error != OK:
		exterior_stream.pending_walk.clear()
		push_warning("%s MOVE_TO failed: %s" % [source, error_string(move_error)])
		return
	if not selecting_spell:
		_set_map_walk_target(str(beyond.map), beyond.tile)
	print_debug("map_input source=", source, " walk to ", beyond.map, " tile=", beyond.tile, " via seam leg=", leg)
	_show_walk_highlight(adapter.godot_to_server(point), point.y)

func _set_map_walk_target(map_id: String, tile: Vector2i) -> void:
	_map_walk_target = {"map": map_id, "tile": tile,
		"last_actor_tile": Vector2i(-99999, -99999), "last_progress_msec": Time.get_ticks_msec()}
	_update_map_walk_target()

func _clear_map_walk_target() -> void:
	_map_walk_target.clear()
	if map_marker_overlay != null:
		map_marker_overlay.set_walk_target(null)
	if minimap_marker_overlay != null:
		minimap_marker_overlay.set_walk_target(null)

func _on_movement_requested(tile: Vector2i) -> void:
	# A route issues new seam legs as maps change. Other movement replaces
	# the map click, including keyboard movement and clicks in the world.
	if not exterior_stream.pending_walk.is_empty() \
			and exterior_stream.pending_walk.get("leg_tile") == tile:
		return
	_clear_map_walk_target()

func _update_map_walk_target() -> void:
	if _map_walk_target.is_empty():
		return
	var here := MapRegistry.normalize_server_map_id(AppState.current_map)
	var target_map: String = _map_walk_target.map
	var tile: Vector2i = _map_walk_target.tile
	var routed: bool = not exterior_stream.pending_walk.is_empty() \
		and str(exterior_stream.pending_walk.get("map", "")) == target_map \
		and exterior_stream.pending_walk.get("tile") == tile
	if here != target_map and not routed:
		_clear_map_walk_target()
		return
	var target_adapter := adapter if here == target_map else CoordinateAdapter.new(exterior_stream.region_coordinates(target_map))
	var point := target_adapter.tile_center(tile.x, tile.y)
	if here != target_map:
		var frame: Variant = exterior_stream.region_transform(target_map)
		if not frame is Transform3D:
			_clear_map_walk_target()
			return
		point = frame * point
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if is_instance_valid(actor_value) and actor_value is Node3D:
		var position: Vector3 = (actor_value as Node3D).global_position
		var actor_tile := adapter.godot_to_server(position)
		if actor_tile != _map_walk_target.last_actor_tile:
			_map_walk_target.last_actor_tile = actor_tile
			_map_walk_target.last_progress_msec = Time.get_ticks_msec()
		if here == target_map and Vector2(position.x, position.z).distance_to(Vector2(point.x, point.z)) < adapter.metres_per_tile * 0.25:
			_clear_map_walk_target()
			return
	# A blocked or interrupted walk must not leave a permanent destination.
	if Time.get_ticks_msec() - int(_map_walk_target.last_progress_msec) > 3000:
		_clear_map_walk_target()
		return
	map_marker_overlay.set_walk_target(point)
	minimap_marker_overlay.set_walk_target(point)

static func _control_to_viewport_position(local_position: Vector2,
		control_size: Vector2, target_size: Vector2i) -> Vector2:
	if control_size.x <= 0.0 or control_size.y <= 0.0:
		return local_position
	return local_position * Vector2(target_size) / control_size

static func _texture_to_viewport_position(local_position: Vector2,
		texture_rect: TextureRect, target_size: Vector2i) -> Variant:
	var control_size: Vector2 = texture_rect.size
	var target: Vector2 = Vector2(target_size)
	if control_size.x <= 0.0 or control_size.y <= 0.0 or target.x <= 0.0 or target.y <= 0.0:
		return null
	if texture_rect.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT_CENTERED:
		var scale: float = minf(control_size.x / target.x, control_size.y / target.y)
		var displayed_size: Vector2 = target * scale
		var displayed_origin: Vector2 = (control_size - displayed_size) * 0.5
		if not Rect2(displayed_origin, displayed_size).has_point(local_position):
			return null
		return (local_position - displayed_origin) * target / displayed_size
	return _control_to_viewport_position(local_position, control_size, target_size)

func _handle_world_click(event: InputEventMouseButton, viewport_position: Vector2) -> void:
	_clear_map_walk_target()
	exterior_stream.pending_walk.clear()
	if not Network.magic_pending.is_empty() and Network.magic_scope in ["burst", "location"]:
		var tile: Variant = _map_target_tile(gameplay_camera, viewport_position)
		if tile is Vector2i: magic_selection.confirm_location(tile)
		return
	if _carried_slot >= 0:
		_drop_carry()
		return
	var picked_actor_id: int = _pick_actor(viewport_position)
	if picked_actor_id >= 0:
		# A technique armed from the Techniques window takes the creature
		# clicked next, the way a pending spell takes its target.
		if techniques_panel != null and bool(techniques_panel.call("fire_at", picked_actor_id)):
			AppState.select_actor(picked_actor_id)
			return
		# A bag at your own feet outranks your own body: you are not a click
		# target for yourself, so the click opens the sack you are standing
		# over. A pending actor spell still wins - clicking yourself casts
		# at yourself.
		if (picked_actor_id == AppState.local_actor_id
				and AppState.pending_spell_target != "actor"
				and _interaction_mode in ["walk", "pick"]):
			var bag_below: int = _ground_bag_below_player()
			if bag_below >= 0:
				_open_ground_bag(bag_below)
				return
		AppState.select_actor(picked_actor_id)
		var selected_dto: Dictionary = AppState.actors.get(picked_actor_id, {})
		match _actor_click_action(picked_actor_id, selected_dto, event.alt_pressed):
			"spell":
				magic_selection.confirm_actor(picked_actor_id)
			"attack":
				if _actor_input_locked(event.ctrl_pressed):
					return
				_send_attack(picked_actor_id)
			"trade":
				var trade_error: Error = Network.trade_with(picked_actor_id)
				if trade_error != OK:
					push_warning("TRADE_WITH failed: " + error_string(trade_error))
			"talk":
				var touch_error: Error = Network.touch_actor(picked_actor_id)
				if touch_error != OK:
					push_warning("TOUCH_PLAYER failed: " + error_string(touch_error))
			"look":
				var look_error: Error = Network.look_at_player(picked_actor_id)
				if look_error != OK:
					push_warning("GET_PLAYER_INFO failed: " + error_string(look_error))
		return
	var picked_bag_id: int = _pick_ground_bag(viewport_position)
	if AppState.pending_spell_target == "actor":
		return
	if picked_bag_id >= 0:
		if _interaction_mode in ["walk", "pick"]:
			_open_ground_bag(picked_bag_id)
		return
	var picked_object: MapObject3D = _pick_map_object(viewport_position)
	if picked_object != null:
		if (_interaction_mode in ["walk", "look"]
				or (_interaction_mode == "harvest" and picked_object.is_harvestable())
				or (_interaction_mode == "use" and not picked_object.is_harvestable())):
			_activate_map_object(picked_object, event.alt_pressed or _interaction_mode == "look")
		return
	# Attack tools, including the temporary Alt sword, never turn a missed
	# target into a movement order.
	if _interaction_mode != "walk" or event.alt_pressed:
		return
	var ray_origin: Vector3 = camera_rig.ray_origin(viewport_position)
	var ray_direction: Vector3 = camera_rig.ray_direction(viewport_position)
	var point: Variant = _navigation_ray_position(ray_origin, ray_direction)
	var neighbor_point: Variant = exterior_stream.pick_neighbor(
		gameplay_world.direct_space_state, ray_origin, ray_direction, event.shift_pressed)
	if neighbor_point is Vector3:
		point = neighbor_point
	if not point is Vector3:
		var ground_height: float = adapter.walking_height
		if actor_nodes.has(AppState.local_actor_id):
			var local_actor_node: Node3D = actor_nodes.get(AppState.local_actor_id) as Node3D
			if is_instance_valid(local_actor_node):
				ground_height = local_actor_node.global_position.y
		point = camera_rig.screen_to_ground(viewport_position, ground_height)
	print_debug("world_input local_click=", event.position, " viewport=", viewport_position,
		" ray_origin=", ray_origin, " ray_direction=", ray_direction, " intersection=", point)
	if point is Vector3:
		if _movement_locked(event.ctrl_pressed):
			exterior_stream.pending_walk.clear()
			return
		var tile: Vector2i = adapter.godot_to_server(point as Vector3)
		print_debug("world_input godot=", point, " server_tile=", tile,
			" command=", "RUN_TO" if event.shift_pressed else "MOVE_TO")
		_clear_keyboard_movement_tracking()
		_clear_local_turn_prediction()
		var move_error: Error = Network.move_to(tile, event.shift_pressed)
		if move_error != OK:
			exterior_stream.pending_walk.clear()
			push_warning("MOVE_TO failed: " + error_string(move_error))
		else:
			var clicked: Vector3 = exterior_stream.pending_walk.get("world_point", point)
			_show_walk_highlight(adapter.godot_to_server(clicked), clicked.y)

## Opens one ground bag: the optimistic reducer state first, so the window
## can say it is opening, then the request the server answers with contents.
func _open_ground_bag(bag_id: int) -> void:
	print_debug("ground_bag_input command=INSPECT_BAG bag_id=", bag_id,
		" redacted_bytes=not_sensitive")
	AppState.begin_ground_bag_inspection(bag_id)
	var inspect_error: Error = Network.inspect_bag(bag_id)
	if inspect_error != OK:
		push_warning("INSPECT_BAG failed: " + error_string(inspect_error))

## The legacy client's click feedback: a walk order marks its destination
## with a collapsing green cross, so the player sees where the click landed
## before the server answers. The mark is for the click itself - it draws for
## the order sent, not for any packet coming back - which is exactly how the
## reference does it.
func _show_walk_highlight(tile: Vector2i, ground_height: float) -> void:
	if not _effects_enabled:
		return
	for stale_tile: Variant in walk_highlight_markers.keys():
		if not is_instance_valid(walk_highlight_markers[stale_tile]):
			walk_highlight_markers.erase(stale_tile)
	var existing_value: Variant = walk_highlight_markers.get(tile)
	if existing_value is HighlightMarker3D:
		(existing_value as HighlightMarker3D).restart()
		return
	var marker := HighlightMarker3D.new()
	world_root.add_child(marker)
	var destination: Vector3 = adapter.tile_center(tile.x, tile.y)
	destination.y = ground_height
	marker.configure(destination, adapter.metres_per_tile)
	walk_highlight_markers[tile] = marker

func _on_state_changed(path: StringName) -> void:
	if _actor_hud_menu != null and (not AppState.authenticated \
			or path in [&"map", &"npc_dialogue", &"trade", &"storage", &"popup", &"death"]):
		_actor_hud_menu.close()
	# Protocol diagnostics are the one path that must work before login: a
	# decode failure during the handshake is exactly what the panel exists to
	# show, and the session is not authenticated when it happens.
	if path == &"protocol_unknown" or path == &"protocol_errors":
		_sync_diagnostics()
		return
	if not AppState.authenticated:
		return
	match path:
		&"adjacent_maps":
			_queue_map_picture_warmup()
		&"lantern_tutorial":
			quest_trail.apply_state(AppState.lantern_tutorial, adapter, AppState.current_map)
			if AppState.lantern_tutorial.get("active", false) and AppState.lantern_tutorial.get("ring_training", false):
				if spell_loadout.mode != "wheel": spell_loadout.set_mode("wheel")
			if bool(AppState.lantern_tutorial.get("active", false)) and int(AppState.popup.get("popup_id", -1)) in [4000, 4001, 4002]:
				AppState.close_popup()
			lantern_guide.apply_state(AppState.lantern_tutorial)
			if is_instance_valid(lantern_scene): lantern_scene.apply_state(AppState.lantern_tutorial)
		&"map":
			_pickpoint_draft.clear()
			_pickpoint_submitting = false
			_load_server_map()
			# Carried actors still name their source map until the arrival packets.
			# Re-sampling them here can miss destination ground and drop the
			# traveller (and camera) to the map's flat fallback height.
			_sync_world({} if _continuous_map_handoff else null)
			_update_console_location()
			# Markers survive a map change; which of them belong here does not.
			_sync_map_markers()
		&"death":
			_prefetch_respawn()
		&"gauntlet_loot":
			_prefetch_gauntlet_exit()
		&"actors":
			# A busy map emits this once per actor packet. Rebuilding the whole
			# actor presentation for each of them repeated the same work many
			# times inside a single frame; coalescing collapses a burst into one
			# pass without delaying anything past the frame it arrived in.
			_queue_world_sync()
		&"local_actor":
			# YOU_ARE can arrive after this actor was already built as a remote
			# one. Refresh the role once here so LOW/MEDIUM keep this cape without
			# paying for a mesh walk on every ordinary actor packet.
			_apply_actor_render_quality()
			_queue_world_sync()
		&"actor_footprints":
			# The table arrives after login - the server can only send it once
			# this client has said it can decode it, which is after LOG_IN_OK -
			# so actors are usually already on screen and already drawn as one
			# tile each. Re-syncing is what takes them to the size the server
			# has actually reserved for them.
			_queue_world_sync()
		&"chat":
			_on_pickpoint_reply()
			_capture_speech_bubble_from_chat()
			_count_unseen_private_messages()
			_hold_mix_report_in_window()
			_append_chat_line()
			if not bool(_last_chat_line().get("in_window", false)):
				_reveal_chat_messages()
		&"almanac":
			_sync_hud_indicators()
			_sync_season_surfaces()
			_apply_day_night()
		&"channels":
			_sync_channel_tabs()
		&"invasion_assistant":
			var kind := str(AppState.invasion_assistant.get("last_kind", ""))
			var update: Dictionary = AppState.invasion_assistant.get(kind, {}) as Dictionary
			if not update.is_empty():
				invasion_assistant_window.apply_update(update)
		&"clock":
			_update_legacy_clock_and_compass()
			_apply_day_night()
			_sync_diagnostics()
		&"attributes", &"techniques":
			_sync_stats()
		&"autocast":
			_sync_autocast()
		&"perks", &"perk_catalog":
			_sync_stats()
			_sync_perk_catalog()
		&"counters":
			_sync_counters()
		&"mix_state":
			_on_mix_state_changed()
		&"stats":
			_sync_stats()
			_sync_spells()
			_sync_manufacturing()
		&"inventory", &"inventory_text", &"inventory_state":
			if path == &"inventory_text" and manufacturing_panel.visible:
				manufacturing_server_status = AppState.inventory_text
			_sync_inventory()
			_sync_spells()
			_sync_manufacturing()
			# The stored side does not change with the backpack, and rebuilding
			# it for every inventory line and every command 226 cost three full
			# refreshes per deposit. Only the backpack column follows.
			if path != &"inventory_text" and bool(AppState.storage.get("open", false)):
				_sync_storage_backpack()
			if bool(AppState.ground_bag.get("open", false)):
				_sync_ground_bag()
		&"achievements_state":
			_sync_counters()
		&"actor_titles":
			_sync_actor_titles()
		&"quest_offers":
			_sync_quest_offers()
		&"actor_occupations":
			_sync_actor_occupations()
			# The dialogue header names what its person does, and the packet
			# can land after the window has opened.
			if bool(AppState.npc_dialogue.get("open", false)):
				_sync_dialogue()
		&"mount_states":
			for mount_actor_id: Variant in actor_nodes:
				_apply_actor_mount(mount_actor_id)
		&"mount_deltas":
			for mount_actor_id: Variant in AppState.mount_deltas.presentation_ids(actor_nodes):
				_apply_actor_mount(mount_actor_id)
		&"presence":
			nearby_indicator.show_count(AppState.presence.nearby_hidden)
		&"experience_state":
			_sync_stats()
		&"worn_slots", &"degraded_items":
			# Which slots are worn changes independently of what is in them,
			# so the icons are redrawn on the mask as well as on the contents.
			_sync_inventory()
			if bool(AppState.storage.get("open", false)):
				_sync_storage()
		&"world_objects":
			_sync_placed_objects()
		&"weather":
			_sync_weather()
		&"fires":
			_sync_fires()
		&"item_detail":
			# The description is written whichever tool asked for it; only the
			# window is withheld. See `_describe_slot`.
			var short_line: String = _short_item_line()
			if not short_line.is_empty():
				inventory_description.text = short_line
		&"inventory_cooldowns":
			_sync_quick_slots()
		&"spells":
			_sync_spells()
		&"selection":
			_sync_selection()
		&"combat_state":
			# Which actor wears the overhead bar changes with the fight, not
			# with the actor packets, so it is re-read here as well: only the
			# old and the new target can have changed.
			_sync_overhead_health_for([])
			_sync_manufacturing()
		&"npc_dialogue":
			_sync_dialogue()
		&"popup":
			_sync_popup()
		&"trade":
			_sync_trade()
		&"storage":
			# A category arrives as a stock packet, a description packet and
			# often a text line, back to back; one refresh covers all of them.
			_queue_storage_sync()
		&"map_objects":
			_sync_map_objects()
			_snap_all_map_objects_to_surface.call_deferred()
		&"map_markers":
			_sync_map_markers()
		&"spell_power":
			_sync_spells()
		&"harvest":
			_sync_harvest_indicator()
		&"reading":
			_sync_reading()
		&"ground_bags":
			_sync_ground_bags()
		&"ground_bag":
			_sync_ground_bag()
		&"knowledge":
			_sync_knowledge()
			_sync_manufacturing()
			_sync_reading()

func _queue_world_sync() -> void:
	if _world_sync_queued:
		return
	_world_sync_queued = true
	_flush_world_sync.call_deferred()

func _flush_world_sync() -> void:
	if not _world_sync_queued:
		return
	_world_sync_queued = false
	_sync_world(AppState.take_changed_actors())
	_sync_selection()

func _queue_storage_sync() -> void:
	if _storage_sync_queued:
		return
	_storage_sync_queued = true
	_flush_storage_sync.call_deferred()

func _flush_storage_sync() -> void:
	if not _storage_sync_queued:
		return
	_storage_sync_queued = false
	_sync_storage()

func _load_server_map() -> void:
	if AppState.current_map.is_empty() or loaded_server_map == AppState.current_map:
		return
	var normalized_map: String = MapRegistry.normalize_server_map_id(AppState.current_map)
	Diagnostics.record("map_requested", {"server_map": AppState.current_map, "map": normalized_map})
	var entry: Dictionary = MapRegistry.resolve(map_registry, AppState.current_map)
	if entry.is_empty():
		Diagnostics.record("map_registry_missing", {"map": normalized_map})
		map_label.text = "Map: " + AppState.current_map + " (GLB package unavailable)"
		push_error("map_registry_miss server_id=%s normalized=%s keys=%s" % [
			AppState.current_map, normalized_map, map_registry.keys()])
		return
	var handoff := exterior_stream.take_ready(normalized_map, world_loader, camera_rig.focus)
	if character_intro.is_active():
		if normalized_map == NewCharacterIntroScript.MAP and character_intro.pending:
			var preloaded: Dictionary = character_intro.take_preload(normalized_map)
			if not preloaded.is_empty():
				handoff = {"resident": preloaded, "continuous": false}
		else:
			character_intro.cancel()
	if handoff.is_empty() and not character_intro.blocks_input():
		# A respawn onto another map adopts the ground loaded while dead.
		var prewarmed: Dictionary = gauntlet_prewarm.take(normalized_map)
		if prewarmed.is_empty():
			prewarmed = respawn_prewarm.take(normalized_map)
		if not prewarmed.is_empty():
			handoff = {"resident": prewarmed, "continuous": false}
		else:
			# A fresh load: the arrival is built behind the curtain. A whole map is
			# built on the frame it loads, so it waits for the curtain to be drawn.
			if not arrival_curtain.is_showing():
				arrival_curtain.begin("Entering %s…" % _friendly_map_name(AppState.current_map))
			if not respawn_prewarm.streams(ProjectSettings.globalize_path(str(entry.get("manifest", "")))) \
					and not arrival_curtain.has_drawn():
				_deferred_map_load = true
				return
	_deferred_map_load = false
	_arrival = {}
	if arrival_curtain.is_showing():
		arrival_curtain.set_text("Entering %s…" % _friendly_map_name(AppState.current_map))
	_continuous_map_handoff = bool(handoff.get("continuous", false))
	_retained_traveller = AppState.local_actor_id if _continuous_map_handoff else -1
	_retained_until = Time.get_ticks_msec() + 3000
	if _continuous_map_handoff:
		var rebase: Transform3D = handoff.rebase
		_rebase_streamed_world(rebase)
	loaded_server_map = AppState.current_map
	_actor_surface_samples.clear()
	if not _continuous_map_handoff:
		_grounded_actors.clear()
	_local_placement_logged = false
	animation_gate.reset()
	# The shared animation library is parsed on a worker thread while the map
	# itself loads, so the first actor to arrive finds it ready.
	_prewarm_shared_animation_libraries()
	_current_map_display_name = _friendly_map_name(AppState.current_map)
	adapter = CoordinateAdapter.new(entry.get("coordinateTransform", {}))
	# The overlay was handed the placeholder adapter _ready() builds before any
	# map exists - one metre per tile from a (0, 0) origin - and never heard
	# about the real one, so every marker projected as though its server tile
	# were a position in metres. The plaza, then at tile (768, 768) on the
	# 1536-tile grid Four Gates used before it went to a metre a tile, drew
	# in the far corner
	# of the map instead of the middle of it.
	map_marker_overlay.configure(full_map_camera, adapter, full_map_viewport.size)
	_neighbour_adapters.clear()
	# A seamless crossing keeps every actor node: the server keeps their
	# records too, re-filing the ones on the map arrived at as its own and
	# the ones on the map left as its neighbours, and _rebase_streamed_world
	# has carried the nodes into the new frame. Any other change of map
	# empties the table, as the server's KILL_ALL_ACTORS empties AppState's.
	# Bodies parked for a return belong to the map being left either way.
	crowd.clear()
	for actor_id: Variant in actor_nodes.keys():
		if _continuous_map_handoff or int(actor_id) == _retained_traveller:
			continue
		var raw_actor_node: Variant = actor_nodes[actor_id]
		if is_instance_valid(raw_actor_node):
			(raw_actor_node as Node).queue_free()
		actor_nodes.erase(actor_id)
	for bag_node_value: Variant in ground_bag_nodes.values():
		if is_instance_valid(bag_node_value):
			(bag_node_value as Node).queue_free()
	ground_bag_nodes.clear()
	for marker_node_value: Variant in walk_highlight_markers.values():
		if is_instance_valid(marker_node_value):
			(marker_node_value as Node).queue_free()
	walk_highlight_markers.clear()
	for object_node_value: Variant in map_object_nodes.values():
		if is_instance_valid(object_node_value):
			(object_node_value as Node).queue_free()
	map_object_nodes.clear()
	_map_presentation = {}
	_ungrounded_map_objects.clear()
	var manifest_resource: String = str(entry.get("manifest", ""))
	var manifest_path: String = ProjectSettings.globalize_path(manifest_resource)
	print_debug("map_resolved server_id=", AppState.current_map,
		" normalized=", normalized_map, " registry_key=", entry.get("registryKey", ""),
		" manifest_resource=", manifest_resource, " manifest_path=", manifest_path)
	if not handoff.is_empty():
		if not _continuous_map_handoff:
			occluder_fade.reset()
		world_loader.adopt_world(handoff.resident)
	else:
		occluder_fade.reset()
		exterior_stream.clear(true) # A preload miss must not cancel the expected road continuation.
		# CHANGE_MAP precedes the destination actor packet. Delay chunk disk
		# reads until that packet supplies the actual login/teleport arrival.
		world_loader.load_world(manifest_path, Vector3.INF, true)

func _rebase_streamed_world(rebase: Transform3D) -> void:
	camera_rig.rebase_world(rebase)
	# The destination may use rotated coordinates. Transform the sun with the
	# terrain and camera so crossing the seam keeps the same physical direction.
	world_sun.global_basis = rebase.basis * world_sun.global_basis
	world_moon.global_basis = rebase.basis * world_moon.global_basis
	# Every actor node rides the rebase: the world moved under all of them, and
	# the ones on the map just left are placed through its resident frame next.
	for actor_id: Variant in actor_nodes.keys():
		var carried: Variant = actor_nodes[actor_id]
		if is_instance_valid(carried):
			(carried as ReplicatedActor3D).rebase_world(rebase)
	var traveller: Variant = actor_nodes.get(_retained_traveller)
	if is_instance_valid(traveller):
		exterior_stream.last_handoff["traveller_at_rebase"] = traveller.global_position
		exterior_stream.last_handoff["target_at_rebase"] = traveller.server_target

func _on_world_loaded(manifest: WorldManifest) -> void:
	Diagnostics.record("map_loaded", {"map": manifest.asset_id(), "cache": str(world_loader.cache_status),
		"load_phases_us": world_loader.load_phases.duplicate()})
	var binding_started := Time.get_ticks_usec()
	var binding_steps: Dictionary = {}
	var step_started := binding_started
	exterior_stream.activate(loaded_server_map, world_loader.world_root, manifest)
	_watch_chunk_surfaces()
	binding_steps["activate"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_bind_shared_world()
	binding_steps["bind_shared_world"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	if is_instance_valid(lantern_scene):
		lantern_scene.queue_free()
	lantern_scene = null
	if manifest.asset_id() in ["lantern_reach", "bellwatch", "stillglass", "reedway", "cinderbank", "echo_court", "wayfarer_bastion", "lantern_exchange", "waystone_yard"]:
		lantern_scene = RoadSceneScript.new() if manifest.asset_id() not in ["lantern_reach", "bellwatch", "stillglass"] else SkySceneScript.new() if manifest.asset_id() == "stillglass" else BellSceneScript.new() if manifest.asset_id() == "bellwatch" else LanternSceneScript.new()
		world_root.add_child(lantern_scene)
		lantern_scene.configure(world_loader.world_root, manifest)
		lantern_scene.apply_state(AppState.lantern_tutorial)
	# Look pass (a no-op with the look off): paint the ground of a
	# map outside the continent now that its scene has set its materials up.
	# Continent regions and chunks are painted by the loader.
	LookGround.paint_bound(world_loader.world_root, manifest)
	_sync_season_surfaces()
	# Look pass: on an interior every occluder fades as develop fades it.
	LookFade.bind(manifest)
	fallback_ground.hide()
	# Regions and interiors may declare their own sky, sun, fog, tonemap, point
	# lights and camera framing. Maps that do not keep the client's previous
	# placeholder environment unchanged.
	if not _continuous_map_handoff:
		if WorldEnvironmentBinder.apply(manifest, world_environment, world_sun, world_root) \
				and world_environment.environment != null:
			# Develop's own environment, for the look's switch to rebind from.
			# A map that declares none keeps the one before it, and so does this.
			_keep_unlooked_environment(world_environment.environment)
		_environment_manifest = manifest
		# Look pass (a no-op with the look off): paint the sky before the map
		# cameras take their (ungraded) copy of the environment.
		LookSky.install(manifest, world_environment)
	if not _continuous_map_handoff:
		WorldEnvironmentBinder.apply_camera(manifest, camera_rig)
	_bind_light_markers(manifest)
	if presentation_effects != null:
		presentation_effects.bind(manifest)
	binding_steps["light_markers"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_apply_day_night()
	binding_steps["day_night"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_update_border_lighting()
	binding_steps["border_lighting"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_bind_ambient_audio(manifest)
	binding_steps["ambient_audio"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_populate_ambient_life(manifest)
	binding_steps["ambient_life"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_current_map_display_name = str(
		manifest.data.get("asset", {}).get("name", manifest.asset_id()))
	map_label.text = "Map: " + _current_map_display_name
	map_title.text = _current_map_display_name.to_upper()
	current_map_button.text = "Current: " + _current_map_display_name
	_configure_interior_cutaway(manifest)
	binding_steps["interior_cutaway"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_configure_secret_sections(manifest)
	binding_steps["secret_sections"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_configure_occluder_fade(manifest)
	binding_steps["occluder_fade"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_configure_full_map(manifest)
	binding_steps["full_map"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_install_map_picture(manifest)
	binding_steps["map_picture"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_queue_map_picture_warmup()
	binding_steps["map_picture_warmup"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_request_map_redraw()
	binding_steps["map_redraw"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	# A seamless crossing keeps every actor node, rebased with the world, and
	# the server keeps their records: presenting the whole table again here
	# cost 90-1,125 ms on the handoff frame (the sixteenth's first live proof),
	# while the traveller walked on and the camera check read it as a jump.
	# Only actors the server changes are presented after such a crossing;
	# any other map load presents the table it just received.
	_sync_world({} if _continuous_map_handoff else null)
	binding_steps["sync_world"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_sync_ground_bags()
	binding_steps["sync_ground_bags"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	_bind_map_presentation(manifest)
	_sync_map_objects()
	binding_steps["sync_map_objects"] = (Time.get_ticks_usec() - step_started) / 1000.0; step_started = Time.get_ticks_usec()
	# The carried actors stand on the same ground after the rebase; their
	# next packet re-samples the surface they stand on.
	if not _continuous_map_handoff:
		_snap_all_actors_to_surface.call_deferred()
	_snap_all_ground_bags_to_surface.call_deferred()
	_snap_all_map_objects_to_surface.call_deferred()
	if _continuous_map_handoff:
		exterior_stream.last_handoff["binding_ms"] = (Time.get_ticks_usec() - binding_started) / 1000.0
		binding_steps["snap_deferred"] = (Time.get_ticks_usec() - step_started) / 1000.0
		exterior_stream.last_handoff["binding_steps"] = binding_steps
	_record_client_snapshot_after_frames()

func _bind_light_markers(manifest: WorldManifest) -> void:
	# Braziers, hearths and shrine lamps the map declares as markers. Interiors
	# rely on them for their whole lighting; outdoor maps use them as warm fill
	# after sundown. Maps that declare none are left alone.
	if is_instance_valid(map_light_root):
		map_light_root.queue_free()
	map_light_root = null
	var root_node := Node3D.new()
	root_node.name = "MapLights"
	world_root.add_child(root_node)
	var bound: int = LightMarkerBinder.apply(manifest, root_node)
	if bound == 0:
		root_node.queue_free()
		return
	map_light_root = root_node
	print_debug("light_markers map=", AppState.current_map, " bound=", bound)

## Moves the environment to the hour the server is keeping. The manifest is
## the noon reference and the daylight curve is the server's own, so the sky
## the player sees and the visibility the server acts on cannot drift apart.
##
## Runs on every clock packet and on a slow timer between them, because the
## server states a whole minute at a time and one minute of real time is a
## visible jump if nothing carries it forward.
## Tells the console where the player is, so `#mark` has a tile to record.
func _update_console_location() -> void:
	console_commands.current_map = EloriaProtocol.map_id_from_reference(
		AppState.current_map)
	var actor: Variant = AppState.actors.get(AppState.local_actor_id)
	console_commands.current_tile = (Vector2i(
		int((actor as Dictionary).get("x", 0)),
		int((actor as Dictionary).get("y", 0)))
		if actor is Dictionary else null)

func _apply_day_night() -> void:
	if world_loader.manifest == null:
		return
	var lighting := _lighting_manifest()
	_day_night_active = DayNightBinder.apply(lighting,
		world_environment, world_sun, AppState.continuous_game_minute(), world_moon)
	# The binder leaves the haze's density as the map bound it; rain thickens
	# it (the look's haze re-reads it below, with the look off this is it).
	var active := weather_layer != null and weather_layer.has_weather()
	if (active or _weather_applied_active) and lighting != null \
			and world_environment.environment != null:
		var fog: Variant = (lighting.data.get("environment", {}) as Dictionary).get("fog")
		if fog is Dictionary and (fog as Dictionary).has("density"):
			world_environment.environment.fog_density = float((fog as Dictionary).density)
	_weather_applied_active = active
	_weather_applied_version = weather_layer.look_version if weather_layer != null else -1
	_hold_shadow_switch()
	_sync_map_environment()
	# Look pass (a no-op with the look off): re-grade what the
	# binders just rewrote. After the map copy, so the maps stay ungraded.
	LookGrade.apply(lighting, world_environment, world_sun)
	# Look pass: and give the painted sky and its haze the hour's colours.
	LookSky.apply(lighting, world_environment, AppState.continuous_game_minute())

## The Graphics tab's "Directional shadows", held over the binders. The map's
## bind and the hour both decide whether the sun may cast (an interior's
## hidden sun, a sun below the horizon) and wrote the flag outright, so a
## player's Off lasted until the next clock packet or border update, and an
## Off saved in the settings file never reached a map at all. They still
## decide when it may cast; the switch decides whether it does.
func _hold_shadow_switch() -> void:
	if not _shadows_enabled:
		world_sun.shadow_enabled = false

## The lighting the binders apply: the (border-blended) manifest at the
## camera's focus, under the weather the server says is falling (WeatherSky).
func _lighting_manifest() -> WorldManifest:
	var lighting := exterior_stream.lighting_manifest(camera_rig.focus)
	lighting = SeasonSky.seasonal(lighting, AppState.almanac.get("season", {}) as Dictionary)
	return WeatherSky.weathered_look(lighting, weather_layer.look()) \
		if weather_layer != null else lighting

## Bind seasonal scenery after map/appearance changes; month changes only
## update shared material uniforms, so existing and newly streamed trees agree.
func _sync_season_surfaces() -> void:
	var started := Time.get_ticks_usec()
	SeasonSurfaces.set_season(AppState.almanac.get("season", {}) as Dictionary)
	for world: Dictionary in LookSwitch.worlds(world_loader.world_root,
			world_loader.manifest, exterior_stream.residents):
		SeasonSurfaces.apply(world.root as Node, world.manifest as WorldManifest)
	_record_surface_work(&"season", started)

func _update_border_lighting() -> void:
	var lighting := _lighting_manifest()
	if lighting == null or not lighting.data.has("streamingBorders"):
		return
	# Reuse the bound sky; changing a border's colour must not allocate a new
	# sky or respawn the map's lamps every frame.
	var declared: Dictionary = lighting.data.environment
	var environment := world_environment.environment
	# Border proximity changes the atmosphere, not the sun's direction. Keep
	# the bound heading; DayNightBinder alone advances its elevation with time.
	if environment != null:
		environment.fog_density = float(declared.get("fog", {}).get("density", environment.fog_density))
		environment.adjustment_saturation = float(declared.get("saturation", 1))
	DayNightBinder.apply(lighting, world_environment, world_sun, AppState.continuous_game_minute(), world_moon)
	_hold_shadow_switch()
	# Look pass (a no-op with the look off): the lines above undo
	# the grade's fog and saturation every 100 ms, so it is re-applied here.
	LookGrade.apply(lighting, world_environment, world_sun)
	# Look pass: and the sky's haze, over the border's blended colours.
	LookSky.apply(lighting, world_environment, AppState.continuous_game_minute())

## The maps are navigation aids, not scenery. Rendered through the world's own
## environment they went as dark as the world did, and a minimap nobody can
## read at night is a minimap that only works half the time. Both map cameras
## get their own copy of the environment with a floor under the ambient, so
## night still reads as night on them but the streets stay legible.
func _sync_map_environment() -> void:
	var source: Environment = world_environment.environment
	if source == null:
		for uncovered: Camera3D in [map_camera, full_map_camera]:
			uncovered.environment = null
		return
	if _map_environment == null or _map_environment.sky != source.sky:
		_map_environment = source.duplicate() as Environment
	_map_environment.background_mode = source.background_mode
	_map_environment.sky = source.sky
	_map_environment.ambient_light_source = source.ambient_light_source
	_map_environment.ambient_light_color = source.ambient_light_color
	_map_environment.ambient_light_energy = maxf(
		source.ambient_light_energy, MAP_MINIMUM_AMBIENT)
	_map_environment.fog_enabled = false
	for lit: Camera3D in [map_camera, full_map_camera]:
		lit.environment = _map_environment

## The ambience a package declares for itself. Four Gates has named a civic
## murmur and its waterfalls since it was authored and nothing played them.
func _bind_ambient_audio(manifest: WorldManifest) -> void:
	if is_instance_valid(map_ambience_root):
		map_ambience_root.queue_free()
	map_ambience_root = null
	if not bool(audio_director.enabled):
		return
	var root_node := Node3D.new()
	root_node.name = "MapAmbience"
	world_root.add_child(root_node)
	var bound: int = AmbientAudioBinder.apply(manifest, root_node,
		world_loader.world_root, PackedStringArray(
			audio_director.call("sound_names") as Array))
	if bound == 0:
		root_node.queue_free()
		return
	map_ambience_root = root_node
	print_debug("ambient_audio map=", AppState.current_map, " bound=", bound)

func _populate_ambient_life(manifest: WorldManifest) -> void:
	# Scenery livestock declared by the map. Networked actors are untouched.
	var chunk_stream := world_loader.world_root as ContinentChunkStream
	if chunk_stream != null:
		if is_instance_valid(ambient_population) and ambient_population.get_parent() == world_root:
			ambient_population.clear()
			ambient_population.queue_free()
		ambient_population = chunk_stream.get_node_or_null("AmbientPopulation") as AmbientPopulation
		if ambient_population == null:
			ambient_population = AmbientPopulation.new()
			ambient_population.name = "AmbientPopulation"
			chunk_stream.add_child(ambient_population)
	elif not is_instance_valid(ambient_population) or ambient_population.get_parent() != world_root:
		ambient_population = AmbientPopulation.new()
		ambient_population.name = "AmbientPopulation"
		world_root.add_child(ambient_population)
	var population := ambient_population
	population.apply_render_quality(LookProfile.quality())
	await get_tree().physics_frame
	if not is_instance_valid(population) or ambient_population != population \
			or gameplay_world == null or world_loader.manifest != manifest:
		return
	population.apply_render_quality(LookProfile.quality())
	var spawned: int = population.populate(manifest,
		gameplay_world.direct_space_state, chunk_stream)
	if spawned > 0:
		print_debug("ambient_population map=", AppState.current_map, " spawned=", spawned)

func _snap_all_actors_to_surface() -> void:
	if _actor_surface_snap_pending:
		return
	_actor_surface_snap_pending = true
	await get_tree().physics_frame
	_actor_surface_snap_pending = false
	var started := Time.get_ticks_usec()
	for actor_value: Variant in actor_nodes.values():
		if not is_instance_valid(actor_value):
			continue
		var actor: ReplicatedActor3D = actor_value as ReplicatedActor3D
		var actor_adapter := _adapter_for_actor(AppState.actors.get(actor.actor_id, {}) as Dictionary)
		if actor_adapter != null:
			_place_actor_on_surface(actor, true, actor_adapter.fallback_height())
	_record_surface_work(&"actor_ground", started, actor_nodes.size())

func _snap_all_ground_bags_to_surface() -> void:
	await get_tree().physics_frame
	for bag_value: Variant in ground_bag_nodes.values():
		var bag: GroundBag3D = bag_value as GroundBag3D
		if is_instance_valid(bag):
			_place_ground_bag_on_surface(bag)

func _on_world_load_failed(errors: Array[String]) -> void:
	Diagnostics.record("map_load_failed", {"errors": errors})
	fallback_ground.show()
	map_label.text = "Map load failed: " + "; ".join(errors)
	_record_client_snapshot_after_frames()

## True while the local character must wait for its ground: it has no node yet
## (signing in, a map change, a teleport or respawn) and the streamed cells
## under its arrival are not resident. The first such call starts the
## asynchronous arrival (ContinentChunkStream.begin_arrival) and raises the
## curtain; _update_arrival releases it. An arrival whose ground is already
## resident (a short hop, ground prefetched while dead) is not held at all.
## A character already standing keeps walking: its streamed lead covers it.
func _hold_for_arrival() -> bool:
	var stream := world_loader.world_root as ContinentChunkStream
	var local_id: int = AppState.local_actor_id
	if stream == null or adapter == null or character_intro.pending \
			or not AppState.actors.has(local_id) or actor_nodes.has(local_id):
		return false
	var arriving: Dictionary = AppState.actors[local_id]
	# Across a seamless crossing the record names the map it came from.
	if str(arriving.get("map", AppState.current_map)) != AppState.current_map:
		return false
	var position: Vector3 = adapter.tile_center(int(arriving.x), int(arriving.y))
	if not _arrival.is_empty() and (_arrival.position as Vector3).is_equal_approx(position):
		# Once the curtain is on screen the actors are built behind it while the
		# ground loads (their models are main-thread work the worker's imports
		# overlap); the local character stays hidden until its ground is there.
		return not bool(_arrival.ready) and not arrival_curtain.has_drawn()
	if stream.has_focus and stream.arrival_resident(position):
		return false
	stream.begin_arrival(position)
	_arrival = {"position": position, "started": Time.get_ticks_msec(), "ready": false}
	if not arrival_curtain.is_showing():
		arrival_curtain.begin("Entering %s…" % _friendly_map_name(AppState.current_map))
	arrival_curtain.set_progress(0.15)
	Diagnostics.record("arrival_started", {"map": AppState.current_map,
		"position": [position.x, position.y, position.z]})
	return true

## Each frame: a deferred whole-map load once the curtain is drawn; a pending
## arrival's progress, and its release once every cell framing it is resident;
## then the curtain lowered once the character stands grounded for a few frames.
func _update_arrival() -> void:
	if _deferred_map_load:
		if not AppState.authenticated:
			_deferred_map_load = false
		elif arrival_curtain.has_drawn():
			_deferred_map_load = false
			_load_server_map()
			_sync_world()
		return
	if not _arrival.is_empty() and not bool(_arrival.ready):
		var stream := world_loader.world_root as ContinentChunkStream
		var position: Vector3 = _arrival.position
		var waited := Time.get_ticks_msec() - int(_arrival.started)
		if stream == null:
			_arrival.ready = true
		else:
			var progress := stream.arrival_progress(position)
			arrival_curtain.set_progress(0.15 + 0.75 * float(progress.x) / maxf(1.0, float(progress.y)))
			if progress.x >= progress.y:
				_arrival.ready = true
			elif waited > ARRIVAL_TIMEOUT_MSEC:
				# Never strand a player behind the curtain: ground the arrival the
				# way the client did before it loaded in the background.
				push_warning("arrival: %d of %d cells after %d ms; loading the rest now" % [
					progress.x, progress.y, waited])
				world_loader.ensure_chunk_arrival(position)
				_arrival.ready = true
		if bool(_arrival.ready):
			_arrival_settle_frames = 0
			# A full pass: changes that arrived while held were not presented.
			var building := Time.get_ticks_usec()
			_sync_world()
			var arrived: Variant = actor_nodes.get(AppState.local_actor_id)
			if is_instance_valid(arrived):
				var local_node := arrived as ReplicatedActor3D
				local_node.visible = true
				_place_actor_on_surface(local_node, true, adapter.fallback_height())
			_snap_all_actors_to_surface.call_deferred()
			Diagnostics.record("arrival_ready", {"map": AppState.current_map, "msec": waited,
				"spawn_ms": (Time.get_ticks_usec() - building) / 1000.0})
		return
	if not arrival_curtain.is_showing():
		return
	if not AppState.authenticated and AppState.connection_state != "connected":
		_end_arrival()
		return
	var local_id: int = AppState.local_actor_id
	var standing: bool = actor_nodes.has(local_id) and _grounded_actors.has(local_id)
	if standing or arrival_curtain.elapsed_msec() > ARRIVAL_CURTAIN_LIMIT_MSEC:
		arrival_curtain.set_progress(1.0)
		_arrival_settle_frames += 1
		if _arrival_settle_frames >= 3:
			_arrival_settle_frames = 0
			_arrival = {}
			arrival_curtain.finish()
	else:
		_arrival_settle_frames = 0
		if actor_nodes.has(local_id):
			arrival_curtain.set_progress(0.95)

func _arrival_pending() -> bool:
	return not _arrival.is_empty() and not bool(_arrival.ready)

func _end_arrival() -> void:
	_arrival = {}
	_deferred_map_load = false
	_arrival_settle_frames = 0
	_arrival_unreported = false
	arrival_curtain.cancel()

## The server keeps a character it has just put somewhere out of every fight
## until the client says it is drawn on loaded ground (`arrival_ready_v1`,
## server eloria/arrival_grace.py). Said once per spawn of the local
## character: visible, grounded, and no loading screen in front of the player.
## The map lets the server ignore a report about an arrival it has replaced.
func _report_arrival() -> void:
	if not _arrival_unreported or _arrival_pending() or arrival_curtain.blocks_input():
		return
	var local_id: int = AppState.local_actor_id
	var node: Variant = actor_nodes.get(local_id)
	if not is_instance_valid(node) or not (node as Node3D).visible \
			or not _grounded_actors.has(local_id):
		return
	_arrival_unreported = false
	if AppState.authenticated and Network._link_ready():
		Network.send_chat("#arrived " + AppState.current_map)
	Diagnostics.record("arrival_reported", {"map": AppState.current_map})

## Prepare the server's beam destination while the completed loot is reviewed.
## The hidden stream is adopted by _load_server_map when the party exits.
func _prefetch_gauntlet_exit() -> void:
	var loot: Dictionary = AppState.gauntlet_loot
	var destination: Variant = loot.get("exit_destination")
	if loot.get("phase", "") not in ["complete", "ended", "sent"] or bool(loot.get("exited", false)) or not destination is Dictionary:
		gauntlet_prewarm.discard()
		return
	var target: Dictionary = destination
	var server_map := str(target.get("map", ""))
	var map_id: String = MapRegistry.normalize_server_map_id(server_map)
	if map_id == MapRegistry.normalize_server_map_id(AppState.current_map):
		gauntlet_prewarm.discard()
		return
	var entry: Dictionary = MapRegistry.resolve(map_registry, server_map)
	if not entry.is_empty():
		gauntlet_prewarm.prewarm(entry, map_id, Vector2i(int(target.x), int(target.y)), world_root)

## While dead, the ground where a respawn will land is loaded in the background
## (the death state's `destination`): kept resident on this map, or prewarmed
## in a hidden stream on another, so clicking respawn needs no loading.
func _prefetch_respawn() -> void:
	var stream := world_loader.world_root as ContinentChunkStream
	var destination: Variant = AppState.death.get("destination")
	if not bool(AppState.death.get("dead", false)) or not destination is Dictionary:
		if stream != null:
			stream.clear_prefetch()
		if not bool(AppState.death.get("dead", false)):
			respawn_prewarm.discard()
		return
	var target: Dictionary = destination
	var server_map := str(target.get("map", ""))
	var tile := Vector2i(int(target.get("x", -1)), int(target.get("y", -1)))
	if server_map.is_empty() or tile.x < 0 or tile.y < 0:
		return
	var map_id: String = MapRegistry.normalize_server_map_id(server_map)
	if map_id == MapRegistry.normalize_server_map_id(AppState.current_map):
		respawn_prewarm.discard()
		if stream != null and adapter != null:
			stream.prefetch(PackedVector3Array([adapter.tile_center(tile.x, tile.y)]))
		return
	if stream != null:
		stream.clear_prefetch()
	var entry: Dictionary = MapRegistry.resolve(map_registry, server_map)
	if not entry.is_empty():
		respawn_prewarm.prewarm(entry, map_id, tile, world_root)

## Brings the actor nodes in line with AppState. Given `changed` - the ids
## AppState has written since the last pass - only those actors are visited;
## without it every actor is, which is what a map load and the fixtures need.
## An actor with no node yet is built either way, at most ACTOR_SPAWN_BUDGET
## of them per process frame, within the shared elapsed allowance.
func _sync_world(changed: Variant = null) -> void:
	# A whole map waiting for the curtain, or a character whose ground is still
	# streaming in: nothing is placed on ground that is not there yet.
	if _deferred_map_load or _hold_for_arrival():
		_spawn_backlog = true
		return
	# The background worker owns arrival imports during creation. Let it finish
	# the actual spawn instead of falling back to a synchronous login prime.
	if character_intro.pending and world_loader.world_root is ContinentChunkStream \
			and (world_loader.world_root as ContinentChunkStream).has_focus \
			and adapter != null and AppState.actors.has(AppState.local_actor_id):
		var arriving: Dictionary = AppState.actors[AppState.local_actor_id]
		if not (world_loader.world_root as ContinentChunkStream).arrival_resident(
				adapter.tile_center(int(arriving.x), int(arriving.y))):
			_spawn_backlog = true
			return
	if adapter != null and AppState.actors.has(AppState.local_actor_id):
		var arrival_actor: Dictionary = AppState.actors[AppState.local_actor_id]
		# Across a seamless crossing the record keeps the map it was spawned on
		# until the server sends it again, and its tiles belong to that map: read
		# through the arriving map's adapter they named a chunk in its far corner,
		# which was then loaded on the handoff frame (the sixteenth's live proof:
		# 1-2 s a crossing, the traveller walking on meanwhile).
		var record_map: String = str(arrival_actor.get("map", AppState.current_map))
		# An arrival loading behind the curtain is the worker's: no synchronous prime.
		if record_map == AppState.current_map and not _arrival_pending() \
				and world_loader.ensure_chunk_arrival(adapter.tile_center(int(arrival_actor.x), int(arrival_actor.y))):
			_actor_surface_samples.clear()
			# The chunk just attached has no physics body until the next physics
			# frame: the actors presented below ray past it onto their fallback
			# height, so they are placed again after that frame (a seamless
			# crossing no longer re-snaps the whole table at its binding).
			_snap_all_actors_to_surface.call_deferred()
			_snap_all_map_objects_to_surface.call_deferred()
	map_label.text = "Map: " + (AppState.current_map if not AppState.current_map.is_empty() else "loading")
	_remove_stale_actor_nodes(changed)
	var visit: Array = (AppState.actors.keys() if changed == null
		else (changed as Dictionary).keys())
	var arriving: Dictionary = {}
	for id: Variant in visit:
		if not AppState.actors.has(id):
			# Marked and gone again inside the same frame.
			continue
		if actor_nodes.has(id):
			_present_actor(id)
		else:
			arriving[id] = true
	# Anything still without a node - left from an earlier pass's budget, or
	# never in the change set - is built too, within the same budget.
	if changed != null and actor_nodes.size() + arriving.size() < AppState.actors.size():
		for id: Variant in AppState.actors:
			if not actor_nodes.has(id):
				arriving[id] = true
	_spawn_arrivals(arriving.keys())
	actor_label.text = "Actors: %d" % AppState.actors.size()
	if AppState.local_actor_id >= 0 and actor_nodes.has(AppState.local_actor_id) and AppState.actors.has(AppState.local_actor_id):
		_update_local_actor_follow()
		var local_dto: Dictionary = AppState.actors[AppState.local_actor_id]
		var continuation: Dictionary = {}
		if not Network.coordinates.selected or (Network.coordinates.ready() and str(local_dto.get("map", "")) == Network.coordinates.map_id):
			continuation = exterior_stream.take_continuation(MapRegistry.normalize_server_map_id(AppState.current_map))
		if not continuation.is_empty():
			Network.move_to(continuation.tile, bool(continuation.run))
		overhead_player_name.text = ReplicatedActor3D.banner_name(local_dto, "Player")
		# You get no nameplate of your own - _nameplate_visible_for skips the
		# local actor - so this banner is the only place your own name colour
		# can show. Demigod mode is the one that turns it green.
		overhead_player_name.add_theme_color_override("font_color",
			_banner_item_color("name", EloriaProtocol.el_text_colour(int(local_dto.get("name_colour", 0)))))
		var current_health := int(local_dto.get("health", 0))
		var maximum_health := maxi(1, int(local_dto.get("max_health", 1)))
		if AppState.stats.is_empty():
			_set_meter(health_bar, health_text, current_health, maximum_health, "Health")
			_set_meter(health_bottom, health_bottom_text,
				current_health, maximum_health, "Health")
			_set_overhead_meter(overhead_health_row, current_health,
				maximum_health, "health")
			_layout_actor_resource_overlay()
	if changed == null:
		_sync_overhead_health()
	else:
		_sync_overhead_health_for(visit + arriving.keys())

## Takes away the nodes of actors AppState no longer has. A pass with a change
## set looks only at those ids - REMOVE_ACTOR marks what it removes - and walks
## every node only when there is no change set, when AppState emptied the table
## in bulk, or when there are more nodes than records. Walking every node on
## every changed frame was one of the costs that grew with the crowd.
##
## A body the server takes away is parked rather than freed when it can be
## (crowd_presentation.gd), so the same actor stepping back into view wears it
## again instead of being rebuilt.
func _remove_stale_actor_nodes(changed: Variant) -> void:
	var generation: int = AppState.actor_roster_generation
	var full: bool = (changed == null or generation != _actor_roster_generation_seen
		or actor_nodes.size() > AppState.actors.size())
	_actor_roster_generation_seen = generation
	var candidates: Array = actor_nodes.keys() if full else (changed as Dictionary).keys()
	if not full and _retained_traveller >= 0:
		candidates.append(_retained_traveller)
	var now: int = Time.get_ticks_msec()
	for id: Variant in candidates:
		if not actor_nodes.has(id) or AppState.actors.has(id):
			continue
		if int(id) == _retained_traveller and now < _retained_until:
			continue
		# An entry can already be dangling: anything that frees an actor node
		# without going through this map leaves the dictionary holding a freed
		# object, and calling queue_free() on that crashes the engine rather
		# than raising. Guarding here is what makes a map change safe while
		# actors are still being torn down.
		# Casting first is not safe: `as Node` on a freed object raises and
		# aborts the whole function, so the entry would never be erased.
		var stale_actor: Variant = actor_nodes[id]
		if is_instance_valid(stale_actor):
			var stale_node := stale_actor as ReplicatedActor3D
			if stale_node != null and not stale_node.is_model_deferred():
				_built_bodies = maxi(0, _built_bodies - 1)
			var parked: bool = (stale_node != null and int(id) != AppState.local_actor_id
				and not stale_node.is_model_deferred()
				and crowd.park_node(int(id), stale_node,
					str(stale_node.get_meta(&"identity_key", "")), now))
			if parked:
				stale_node.pause_for_parking(animation_gate)
			else:
				(stale_actor as Node).queue_free()
		actor_nodes.erase(id)
		crowd.forget(int(id))
		_actor_surface_samples.erase(id)
		_grounded_actors.erase(id)
		# Otherwise a recycled actor id inherits the last health of whoever
		# held it before, and the next update floats a change nobody took.
		_actor_health_seen.erase(id)
	crowd.expire_parked(now)

## Gives each arriving actor a node. The player's own is always built at once.
## With lazy bodies (crowd_presentation.gd) the nearest arrivals inside the
## build radius share the per-process-frame count/time allowance, and every other
## arrival gets a deferred node now - its map dot, and a stand-in if it is in
## view - whose body `_update_model_builds` builds nearest first. Without them
## the rest simply wait for a later pass, as they always did.
func _actor_creation_begin_frame(process_frame: int = -1) -> void:
	var frame := Engine.get_process_frames() if process_frame < 0 else process_frame
	if frame == _actor_creation_frame:
		return
	_actor_creation_frame = frame
	_actor_creation_count = 0
	_actor_creation_spent_usec = 0
	_actor_creation_priority_seen.clear()
	_actor_creation_overrun_seen = false

func _actor_creation_may_start(id: int, process_frame: int = -1) -> bool:
	_actor_creation_begin_frame(process_frame)
	if _actor_creation_count < ACTOR_SPAWN_BUDGET \
			and _actor_creation_spent_usec < crowd.BUILD_BUDGET_USEC:
		return true
	# At most three distinct critical ids in a frame, each admitted once beyond
	# the ordinary allowance. Rapid target/selection changes cannot grow this.
	return id >= 0 and _crowd_priority_actor(id) and _actor_creation_priority_seen.size() < 3 \
		and not _actor_creation_priority_seen.has(id)

func _record_actor_creation(id: int, elapsed_usec: int, process_frame: int = -1) -> void:
	_actor_creation_begin_frame(process_frame)
	var cost := maxi(0, elapsed_usec)
	var priority := id >= 0 and _crowd_priority_actor(id)
	if priority:
		if _actor_creation_count >= ACTOR_SPAWN_BUDGET \
				or _actor_creation_spent_usec >= crowd.BUILD_BUDGET_USEC:
			_actor_creation_totals.priorityBypasses += 1
		_actor_creation_priority_seen[id] = true
	_actor_creation_count += 1
	_actor_creation_spent_usec += cost
	_actor_creation_totals.builds += 1
	_actor_creation_totals.maximumAtomicUsec = maxi(_actor_creation_totals.maximumAtomicUsec, cost)
	_actor_creation_totals.maximumFrameUsec = maxi(_actor_creation_totals.maximumFrameUsec, _actor_creation_spent_usec)
	_actor_creation_totals.maximumBuildsInFrame = maxi(_actor_creation_totals.maximumBuildsInFrame, _actor_creation_count)
	if cost > crowd.BUILD_BUDGET_USEC:
		_actor_creation_totals.atomicOverruns += 1
	if _actor_creation_spent_usec > crowd.BUILD_BUDGET_USEC and not _actor_creation_overrun_seen:
		_actor_creation_totals.framesOverBudget += 1
		_actor_creation_overrun_seen = true

func actor_creation_budget_snapshot(process_frame: int = -1) -> Dictionary:
	_actor_creation_begin_frame(process_frame)
	return {"processFrame": _actor_creation_frame, "bodiesThisFrame": _actor_creation_count,
		"microsecondsThisFrame": _actor_creation_spent_usec,
		"bodyLimit": ACTOR_SPAWN_BUDGET, "microsecondLimit": crowd.BUILD_BUDGET_USEC,
		"totals": _actor_creation_totals.duplicate()}

func _actor_arrival_priority(id: int) -> int:
	if id == AppState.local_actor_id:
		return 0
	if id == AppState.selected_actor_id:
		return 1
	if id == _combat_target_actor_id():
		return 2
	return 3

func _spawn_arrivals(arriving: Array) -> void:
	if arriving.is_empty():
		return
	var reference := _crowd_reference_point()
	var ranked: Array = []
	for index: int in arriving.size():
		var id: int = int(arriving[index])
		if not AppState.actors.has(id) or actor_nodes.has(id):
			continue
		var distance := _record_distance(AppState.actors[id] as Dictionary, reference)
		ranked.append([_actor_arrival_priority(id), distance if crowd.lazy else float(index), id, distance])
	ranked.sort_custom(func(a: Array, b: Array) -> bool:
		if a[0] != b[0]: return a[0] < b[0]
		if a[1] != b[1]: return a[1] < b[1]
		return a[2] < b[2])
	var deferred := 0
	for pair: Array in ranked:
		var id: int = int(pair[2])
		var wants_body: bool = not crowd.lazy or _crowd_priority_actor(id) \
			or (float(pair[3]) <= crowd.BUILD_RADIUS_METRES and _body_cap_allows(id, float(pair[3])))
		if wants_body and _actor_creation_may_start(id):
			_spawn_actor(id)
		elif crowd.lazy and deferred < crowd.DEFERRED_SPAWNS_PER_PASS:
			_spawn_actor(id, false)
			deferred += 1
		else:
			_spawn_backlog = true

## Where crowd distances are measured from: the player's body, else the tile
## their record names, else the camera's focus.
func _crowd_reference_point() -> Vector3:
	var local_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if is_instance_valid(local_value):
		return (local_value as Node3D).global_position
	var record: Dictionary = AppState.actors.get(AppState.local_actor_id, {}) as Dictionary
	if not record.is_empty() and adapter != null:
		return adapter.tile_center(int(record.get("x", 0)), int(record.get("y", 0)))
	return camera_rig.focus if camera_rig != null else Vector3.ZERO

## The ground distance from `reference` to the tile an actor record names, or
## INF when its map is not placed yet.
func _record_distance(dto: Dictionary, reference: Vector3) -> float:
	var actor_adapter: CoordinateAdapter = _adapter_for_actor(dto)
	if actor_adapter == null:
		return INF
	var at: Vector3 = actor_adapter.tile_center(int(dto.get("x", 0)), int(dto.get("y", 0)))
	return Vector2(at.x - reference.x, at.z - reference.z).length()

## Whether an actor this far away may have a body under the optional body cap:
## inside the cap's distance (`_update_animation_gate`). The player, their
## target and their selection always may.
func _body_cap_allows(id: int, distance: float) -> bool:
	if crowd.body_cap <= 0 or _crowd_priority_actor(id):
		return true
	return distance <= _body_cap_distance

func _crowd_priority_actor(id: int) -> bool:
	return id == AppState.local_actor_id or id == AppState.selected_actor_id \
		or id == _combat_target_actor_id()

## `_sync_overhead_health` for the actors one pass touched. Their own answers
## change only with their records; everyone else's only when the target does,
## which takes the bar off the old target and puts it on the new one.
func _sync_overhead_health_for(ids: Array) -> void:
	var target_id: int = _combat_target_actor_id()
	if target_id != _overhead_target_actor:
		var previous: int = _overhead_target_actor
		_overhead_target_actor = target_id
		_apply_overhead_health(previous, target_id)
		_apply_overhead_health(target_id, target_id)
	for id: Variant in ids:
		_apply_overhead_health(int(id), target_id)

func _apply_overhead_health(id: int, target_id: int) -> void:
	var node_value: Variant = actor_nodes.get(id)
	if not (node_value is ReplicatedActor3D) or not is_instance_valid(
			node_value as ReplicatedActor3D):
		return
	var actor := node_value as ReplicatedActor3D
	actor.set_combat_target(id == target_id)
	actor.set_health_visible(_overhead_health_for(id,
		AppState.actors.get(id, {}) as Dictionary, target_id))

## Applies an actor's current AppState record to the node it already has.
func _present_actor(id: Variant) -> void:
	var dto: Dictionary = _presentation_dto(AppState.actors[id])
	var existing_actor: ReplicatedActor3D = actor_nodes[id] as ReplicatedActor3D
	var actor_adapter: CoordinateAdapter = _adapter_for_actor(dto)
	if actor_adapter == null:
		return
	existing_actor.apply_server_state(dto, actor_adapter)
	_apply_actor_mount(id)
	# Before apply_vitals, which is what overwrites the old value.
	_report_health_change(int(id), int(dto.get("health", 0)),
		int(dto.get("max_health", 0)), existing_actor)
	existing_actor.apply_vitals(int(dto.get("health", 0)),
		int(dto.get("max_health", 0)))
	_apply_actor_banner_options(int(id), existing_actor)
	# A deferred actor out of draw range shows nothing to stand on the ground:
	# its map dot needs only the tile. Its body is put on the ground when built.
	if not existing_actor.is_model_deferred() or existing_actor.is_drawn():
		_place_actor_on_surface(existing_actor, false, actor_adapter.fallback_height())

## Builds the node for an actor that has none yet, or - given `previous` - in
## place of the node it has: `build` false makes a deferred node without a body
## (crowd_presentation.gd). A replacement carries on the old node's motion.
func _spawn_actor(id: Variant, build := true,
		previous: ReplicatedActor3D = null) -> bool:
	var dto: Dictionary = _presentation_dto(AppState.actors[id])
	var actor_adapter: CoordinateAdapter = _adapter_for_actor(dto)
	if actor_adapter == null:
		# Its map is a neighbour that is not resident yet: built on a later pass.
		_spawn_backlog = true
		return false
	var identity: String = CrowdPresentationScript.identity_key(dto)
	if previous == null:
		var parked := crowd.take_parked(int(id), identity) as ReplicatedActor3D
		if parked != null:
			_revive_actor(id, parked, dto, actor_adapter)
			return true
	var creates_body: bool = build or int(id) == AppState.local_actor_id or not crowd.lazy
	if creates_body and not _actor_creation_may_start(int(id)):
		_spawn_backlog = true
		return false
	var creation_started := Time.get_ticks_usec()
	var node := ReplicatedActor3D.new()
	node.name = "Actor_%d" % id
	node.set_meta(&"identity_key", identity)
	world_root.add_child(node)
	actor_nodes[id] = node
	var model_id := _model_for_actor(dto)
	var model_config: Dictionary = models.get(model_id, {}) as Dictionary
	var errors := node.configure(dto, actor_adapter, model_config,
		_animation_for_model(model_config), equipment_config,
		build or int(id) == AppState.local_actor_id or not crowd.lazy)
	if not node.is_model_deferred():
		_built_bodies += 1
	node.apply_render_quality(LookProfile.quality(), int(id) == AppState.local_actor_id)
	if not errors.is_empty():
		push_warning("Actor %d: %s" % [id, "; ".join(errors)])
	node.adopt_command_memory_from(previous)
	node.apply_server_state(dto, actor_adapter, true)
	_fit_lantern_map_marker(node, "MapDot")
	node.set_combat_effects_enabled(_effects_enabled)
	node.set_target_marker_style(_target_marker_style)
	_apply_actor_banner_options(int(id), node)
	node.set_title(str(AppState.actor_titles.get(int(id), "")))
	node.set_occupation(str(AppState.actor_occupations.get(int(id), "")))
	node.set_quest_available(AppState.quest_offer_actors.has(int(id)))
	_apply_actor_mount(id)
	_place_actor_on_surface(node, true, actor_adapter.fallback_height())
	node.adopt_presentation_from(previous)
	node.set_selected(int(id) == AppState.selected_actor_id)
	if int(id) == AppState.local_actor_id:
		# Built behind the curtain, shown once its ground is resident.
		node.visible = not _arrival_pending()
		_arrival_unreported = true
		_sync_harvest_sparkle()
	elif crowd.lazy:
		# Drawn or not from the start, rather than from the next gate pass: a
		# deferred actor far off would otherwise show its stand-in and its name
		# for up to a tenth of a second.
		node.set_drawn(_crowd_reference_point().distance_to(node.global_position)
			<= ACTOR_DRAW_DISTANCE_METRES)
	if creates_body:
		_record_actor_creation(int(id), Time.get_ticks_usec() - creation_started)
	return true

## Puts a parked body back for the actor it was parked for: the same steps a
## new node takes, on a node that already has its model.
func _revive_actor(id: Variant, node: ReplicatedActor3D, dto: Dictionary,
		actor_adapter: CoordinateAdapter) -> void:
	actor_nodes[id] = node
	_built_bodies += 1
	node.apply_server_state(dto, actor_adapter, true)
	node.apply_vitals(int(dto.get("health", 0)), int(dto.get("max_health", 0)))
	_apply_actor_banner_options(int(id), node)
	node.set_title(str(AppState.actor_titles.get(int(id), "")))
	node.set_occupation(str(AppState.actor_occupations.get(int(id), "")))
	node.set_quest_available(AppState.quest_offer_actors.has(int(id)))
	# Parked bodies were absent from live quality changes. Reconcile before
	# mount/tack attachment so every returned visual inherits current policy.
	node.apply_render_quality(LookProfile.quality(), int(id) == AppState.local_actor_id)
	_apply_actor_mount(id)
	_place_actor_on_surface(node, true, actor_adapter.fallback_height())
	node.set_selected(int(id) == AppState.selected_actor_id)
	node.set_drawn(_crowd_reference_point().distance_to(node.global_position)
		<= ACTOR_DRAW_DISTANCE_METRES)
	# Paused while parked; it animates meanwhile, as a body coming into view
	# does, until the gate's next sweep gives it its tier.
	node.set_animation_tier(AnimationGate.Tier.HALF if crowd.gate
		else AnimationGate.Tier.FULL, animation_gate)

## Builds the bodies of deferred actors that have come within range, nearest
## first: the candidates are ranked on each gate pass, and this builds as many
## a process frame as the arrival-shared count/time allowance permits.
## Each is a new node in the deferred one's place, carrying on its motion.
func _update_model_builds() -> void:
	if not crowd.lazy:
		return
	# Critical bodies must not wait behind a stale distance-ranked candidate queue.
	var priority_ids := [AppState.local_actor_id, AppState.selected_actor_id, _combat_target_actor_id()]
	var seen: Dictionary = {}
	for raw_id: int in priority_ids:
		if raw_id < 0 or seen.has(raw_id) or not AppState.actors.has(raw_id):
			continue
		seen[raw_id] = true
		var value: Variant = actor_nodes.get(raw_id)
		if is_instance_valid(value) and value is ReplicatedActor3D \
				and (value as ReplicatedActor3D).is_model_deferred() and _actor_creation_may_start(raw_id):
			if _replace_actor_node(raw_id, true):
				crowd.builds += 1
	_actor_creation_begin_frame()
	var started := Time.get_ticks_usec()
	var remaining := maxi(0, crowd.BUILD_BUDGET_USEC - _actor_creation_spent_usec)
	while crowd.pending_candidates() > 0 and _actor_creation_may_start(-1) \
			and Time.get_ticks_usec() - started < remaining:
		var id: int = crowd.next_candidate()
		if id < 0:
			break
		var node_value: Variant = actor_nodes.get(id)
		if not is_instance_valid(node_value) or not AppState.actors.has(id):
			continue
		var deferred := node_value as ReplicatedActor3D
		if deferred == null or not deferred.is_model_deferred():
			continue
		var reference: Vector3 = _crowd_reference_point()
		if not _body_cap_allows(id, Vector2(deferred.global_position.x - reference.x,
				deferred.global_position.z - reference.z).length()):
			continue
		if _replace_actor_node(id, true):
			crowd.builds += 1

## Swaps an actor's node for a new one with (`build`) or without its body. The
## old node is hidden at once and freed at the end of the frame, so nothing
## holding it this frame finds it gone mid-call.
func _replace_actor_node(id: int, build: bool) -> bool:
	# Validity before the cast: `as` on a freed node raises.
	var previous_value: Variant = actor_nodes.get(id)
	if not is_instance_valid(previous_value):
		return false
	var previous := previous_value as ReplicatedActor3D
	if previous == null:
		return false
	actor_nodes.erase(id)
	_spawn_actor(id, build, previous)
	if not actor_nodes.has(id):
		# The map it stands on is not placed now: keep the old node instead.
		actor_nodes[id] = previous
		return false
	if not previous.is_model_deferred():
		_built_bodies = maxi(0, _built_bodies - 1)
	previous.visible = false
	previous.collision_layer = 0
	previous.process_mode = Node.PROCESS_MODE_DISABLED
	previous.queue_free()
	_apply_overhead_health(id, _overhead_target_actor)
	return true

## Bind mount presentation to the current player identity and map, including
## state received before a visible actor's model finished loading.
func _apply_actor_mount(id: Variant) -> void:
	var node := actor_nodes.get(id) as ReplicatedActor3D
	if node == null:
		return
	node.set_mount_state(AppState.mount_state_for_actor(int(id)), models)

func _sync_quest_offers() -> void:
	for id: Variant in actor_nodes:
		var node := actor_nodes[id] as ReplicatedActor3D
		if is_instance_valid(node):
			node.set_quest_available(AppState.quest_offer_actors.has(int(id)))

func _sync_actor_titles() -> void:
	for id: Variant in actor_nodes:
		var node_value: Variant = actor_nodes[id]
		if node_value is ReplicatedActor3D and is_instance_valid(node_value as ReplicatedActor3D):
			(node_value as ReplicatedActor3D).set_title(
				str(AppState.actor_titles.get(int(id), "")))

## Push NPC occupations onto the people they describe: the line under the
## name. Like the titles, it rides its own packet (command 210) rather than
## the display name, and the server sends it after the actors, so this runs
## for whoever is already on screen and `_spawn_actor` for whoever comes later.
func _sync_actor_occupations() -> void:
	for id: Variant in actor_nodes:
		var node_value: Variant = actor_nodes[id]
		if node_value is ReplicatedActor3D and is_instance_valid(node_value as ReplicatedActor3D):
			(node_value as ReplicatedActor3D).set_occupation(
				str(AppState.actor_occupations.get(int(id), "")))

## The occupation of the person a dialogue is with, for its header. Each option
## names the actor it answers; before any option has arrived the window is
## matched by name, which SEND_NPC_INFO cuts to 19 bytes.
static func dialogue_occupation(dialogue: Dictionary, actors: Dictionary,
		occupations: Dictionary) -> String:
	var raw_options: Variant = dialogue.get("options", [])
	if raw_options is Array:
		for raw_option: Variant in raw_options as Array:
			if raw_option is Dictionary:
				var answering: int = int((raw_option as Dictionary).get("actor_id", -1))
				if answering >= 0:
					return str(occupations.get(answering, ""))
	var wanted: String = str(dialogue.get("name", "")).strip_edges().to_lower()
	if wanted.is_empty():
		return ""
	var cut: bool = wanted.to_utf8_buffer().size() >= 19
	for raw_id: Variant in actors:
		var person: String = str((actors[raw_id] as Dictionary).get("name", "")).to_lower()
		if person == wanted or (cut and person.begins_with(wanted)):
			return str(occupations.get(int(raw_id), ""))
	return ""

func _update_local_actor_follow() -> void:
	if AppState.local_actor_id < 0:
		return
	var target_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if not target_value is Node3D:
		return
	var target: Node3D = target_value as Node3D
	if not is_instance_valid(target):
		return
	var focus_position: Vector3 = target.global_position
	if not character_intro.blocks_input():
		camera_rig.set_focus(focus_position)
	map_camera.global_position = focus_position + Vector3(0, 220, 0)
	var minimap_heading := 0.0
	if _minimap_orientation == "player_up":
		minimap_heading = target.rotation.y
	elif _minimap_orientation == "viewport_up":
		minimap_heading = deg_to_rad(camera_rig.yaw_degrees)
	map_camera.rotation = Vector3(-PI * 0.5, minimap_heading, 0.0)
	# Repositioning the four compass letters is only observable while the
	# minimap is on screen.
	if minimap_frame.visible:
		_layout_minimap_cardinals()
	# Render above the actor and ignore depth so roofs/bridges cannot hide the
	# local-position dot in either top-down map camera.
	player_map_marker.global_position = focus_position + Vector3(0, 5.0, 0)
	player_map_marker.visible = true

func _update_character_intro(delta: float) -> void:
	if not character_intro.is_active():
		return
	var guide_ready := false
	var guide: Node3D
	var guide_id := -1
	for id: Variant in actor_nodes:
		var dto: Dictionary = AppState.actors.get(id, {})
		if int(dto.get("kind", 0)) == 2 and str(dto.get("name", "")) == "Nash":
			guide = actor_nodes[id] as Node3D
			guide_id = int(id)
			guide_ready = AppState.quest_offer_actors.has(guide_id)
			break
	character_intro.update(delta, camera_rig,
		actor_nodes.get(AppState.local_actor_id) as Node3D,
		_grounded_actors.has(AppState.local_actor_id), guide_ready, guide, guide_id, AppState.npc_dialogue)

func _request_arrival_conversation(actor_id: int) -> void:
	AppState.close_dialogue()
	Network.send_chat("#arrival_intro talk %d" % actor_id)

func _end_arrival_conversation() -> void:
	if AppState.authenticated and Network._link_ready():
		Network.send_chat("#arrival_intro end")

## The ray sample only changes when the actor stands somewhere else, but this
## used to fire for every actor on every actor packet - hundreds of physics
## queries a second on a populated map. The sample is now cached per actor and
## repeated only when its tile moves, or when the caller forces it after a map
## load.
func _place_actor_on_surface(actor: ReplicatedActor3D, force := false, fallback_height := NAN) -> void:
	if not is_instance_valid(actor) or gameplay_world == null:
		return
	var actor_position: Vector3 = actor.server_target
	var sample := Vector2(actor_position.x, actor_position.z)
	if not force and _actor_surface_samples.get(actor.actor_id) == sample:
		return
	var ray_start: Vector3 = Vector3(actor_position.x, 400.0, actor_position.z)
	var ray_end: Vector3 = Vector3(actor_position.x, -100.0, actor_position.z)
	# A neighbour's ground stands on the preview layer while its map is not
	# the active one; an actor across the seam is placed on it. An actor on
	# the client's own map rays the navigation layer alone, as it always did:
	# on the handoff frame the map just left still stands at its old place
	# for the physics server, and with the preview layer in the mask the
	# traveller arriving over a seam was set 48-58 m up on that map's ground
	# (the sixteenth's live proof, five crossings). The traveller is on the
	# client's own map by definition, whatever map its record still names.
	var record: Dictionary = AppState.actors.get(actor.actor_id, {}) as Dictionary
	var across_seam: bool = (actor.actor_id != AppState.local_actor_id
		and str(record.get("map", AppState.current_map)) != AppState.current_map)
	var mask: int = WorldLoader.NAVIGATION_SURFACE_LAYER
	if across_seam:
		mask |= ExteriorRegionStream.PREVIEW_SURFACE_LAYER
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(ray_start, ray_end, mask)
	var hit: Dictionary = gameplay_world.direct_space_state.intersect_ray(query)
	var hit_position_value: Variant = hit.get("position")
	if hit_position_value is Vector3:
		var hit_position: Vector3 = hit_position_value as Vector3
		actor.set_surface_height(hit_position.y + 0.02)
		_actor_surface_samples[actor.actor_id] = sample
		_grounded_actors[actor.actor_id] = true
		# render_diagnostics() walks the actor's whole subtree and builds a
		# dictionary per mesh. Its arguments were evaluated on every placement
		# even in release builds, so it is now a one-shot per map load.
		if actor.actor_id == AppState.local_actor_id and not _local_placement_logged:
			_local_placement_logged = true
			print_debug("local_actor_placement map=", AppState.current_map,
				" actor_id=", actor.actor_id, " server_target=", actor_position,
				" navigation_hit=", hit_position, " render=", actor.render_diagnostics(),
				" camera=", camera_rig.camera_diagnostics())
	else:
		# A seam can cross a two-metre terrain cell owned by the neighbour.
		# Until that streamed cell's physics is ready, keep the height we last
		# measured instead of dropping to the map's unrelated walking height.
		# A miss remains uncached so later updates can sample the same tile.
		_actor_surface_samples.erase(actor.actor_id)
		# Off the edge of this map's own ground. Where a border is open, the tile a
		# walker steps onto to cross it is the neighbour's first tile, which this
		# map's geometry does not cover; the neighbour's does, resident on the
		# preview layer and standing where it belongs until the handoff. Its ground
		# is sampled there before the map's flat walking height, which set a
		# traveller 9 to 94 m off the ground it stood on for the frame before a
		# crossing (the eighteenth's live proof: every camera jump it found). The
		# gates never met this: their threshold deck spans the border on both maps.
		if not across_seam:
			var beside: Dictionary = gameplay_world.direct_space_state.intersect_ray(
				PhysicsRayQueryParameters3D.create(ray_start, ray_end, ExteriorRegionStream.PREVIEW_SURFACE_LAYER))
			var beside_position: Variant = beside.get("position")
			if beside_position is Vector3:
				actor.set_surface_height((beside_position as Vector3).y + 0.02)
				_grounded_actors[actor.actor_id] = true
				return
		if _grounded_actors.has(actor.actor_id):
			return
		var fallback: float = adapter.walking_height if is_nan(fallback_height) else fallback_height
		actor.set_surface_height(fallback + 0.02)
		if actor.actor_id == AppState.local_actor_id:
			push_warning("local_actor_placement navigation_miss map=%s actor_id=%d target=%s fallback_y=%.3f" % [
				AppState.current_map, actor.actor_id, actor_position, fallback + 0.02])

## The adapter that places an actor: the active map's for an actor on it, and
## for an actor on a neighbouring map, that map's own adapter carried through
## the rigid frame its resident root stands in. Null while the neighbour is
## not resident: the actor waits for its ground rather than standing on ours.
func _adapter_for_actor(dto: Dictionary) -> CoordinateAdapter:
	var actor_map: String = str(dto.get("map", ""))
	if actor_map.is_empty() or actor_map == AppState.current_map:
		return adapter
	var normalized: String = MapRegistry.normalize_server_map_id(actor_map)
	if normalized == MapRegistry.normalize_server_map_id(AppState.current_map):
		return adapter
	var resident: Variant = exterior_stream.residents.get(normalized)
	if not resident is Dictionary:
		return null
	var root: Node3D = (resident as Dictionary).get("root") as Node3D
	var manifest: WorldManifest = (resident as Dictionary).get("manifest") as WorldManifest
	if not is_instance_valid(root) or manifest == null:
		return null
	var cached: Variant = _neighbour_adapters.get(normalized)
	if cached is Dictionary and (cached as Dictionary).get("transform") == root.transform:
		return (cached as Dictionary).get("adapter") as CoordinateAdapter
	var framed := FramedCoordinateAdapter.wrap(manifest.coordinate_adapter(), root.transform)
	_neighbour_adapters[normalized] = {"transform": root.transform, "adapter": framed}
	return framed

## The Tab map and the minimap draw the region's own picture, not the resident
## chunks. A chunk-streamed territory holds only the chunks around the player,
## so a live render of the world framed to the whole region showed the
## resident chunks in a field of nothing. Every region ships its picture
## (minimap.webp, one pixel a metre, north up, framed by cartography.json as
## the full-map camera frames the region); it is laid on the ground on a
## visual layer only the map cameras render, and while it stands they render
## nothing else. The dots and marks are drawn over it as before. A map
## without a picture (an interior) keeps the live render.
func _install_map_picture(manifest: WorldManifest) -> void:
	_remove_map_picture()
	var region_index: int = _region_index_for_map(AppState.current_map)
	var minimap: Dictionary = manifest.data.get("minimap", {}) as Dictionary
	var texture: Texture2D = null
	var tab_map: Dictionary = {}
	if region_index >= 0 and not minimap.is_empty():
		var region: Dictionary = cartography_regions[region_index] as Dictionary
		texture = _tab_map_texture(region)
		if texture != null:
			texture = _tab_map_detail_texture(region)
		tab_map = region.get("tabMap", {}) as Dictionary
	var extent: Rect2 = MapPicture.extent(minimap, tab_map) if texture != null else Rect2()
	if texture == null or extent.size.x <= 0.0 or extent.size.y <= 0.0:
		_set_map_cameras_picture(false)
		return
	_map_picture_height = MapPicture.height_below(manifest.data)
	_map_picture = MapPicture.build(texture, extent, _map_picture_height, MAP_PICTURE_LAYER)
	world_root.add_child(_map_picture)
	_set_map_cameras_picture(true)
	_install_neighbour_pictures()

func _remove_map_picture() -> void:
	_map_detail_visible.clear()
	if is_instance_valid(_map_picture):
		_map_picture.hide()
		_map_picture.queue_free()
	_map_picture = null
	# Far-region pictures share world_root, so a map handoff does not change
	# their parent. Their transforms and depths still belong to the departure
	# map. Rebuild them with the new picture; the decoded textures stay cached.
	for picture: Variant in _neighbour_pictures.values():
		if is_instance_valid(picture):
			(picture as Node3D).hide()
			(picture as Node).queue_free()
	_neighbour_pictures.clear()

## The region boundaries in the current map's frame: every region's cartography
## polygon (continent picture pixels, north up) turned into metres of this map,
## with its name at its label point and the current region flagged. Both map
## overlays draw them as dashed lines; the Tab map names the neighbours.
func _map_boundaries() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var region_index: int = _region_index_for_map(AppState.current_map)
	if region_index < 0 or not cartography is Dictionary:
		return result
	var continent: Dictionary = (cartography as Dictionary).get("continent", {}) as Dictionary
	var origin: Array = continent.get("originMetres", []) as Array
	var metres_per_pixel: float = float(continent.get("metresPerPixel", 0.0))
	var translation: Array = (cartography_regions[region_index] as Dictionary).get("globalTranslation", []) as Array
	if origin.size() != 2 or metres_per_pixel <= 0.0 or translation.size() != 3:
		return result
	var height: float = adapter.walking_height if adapter != null else 0.0
	var frame: String = _cartography_frame(region_index)
	for index: int in range(cartography_regions.size()):
		if _cartography_frame(index) != frame:
			continue
		var region: Dictionary = cartography_regions[index] as Dictionary
		var label_pixel: Array = region.get("continentLabel", []) as Array
		var label := Vector3.INF
		if label_pixel.size() == 2:
			label = Vector3(float(origin[0]) + float(label_pixel[0]) * metres_per_pixel - float(translation[0]), height,
				float(origin[1]) + float(label_pixel[1]) * metres_per_pixel - float(translation[2]))
		var first := true
		for polygon: PackedVector2Array in _region_polygon_components(index):
			var points := PackedVector3Array()
			for pixel: Vector2 in polygon:
				points.append(Vector3(float(origin[0]) + pixel.x * metres_per_pixel - float(translation[0]), height,
					float(origin[1]) + pixel.y * metres_per_pixel - float(translation[2])))
			result.append({"name": str(region.get("name", "")), "points": points,
				"label": label if first else Vector3.INF, "current": index == region_index})
			first = false
	return result

func _update_map_boundaries() -> void:
	var boundaries: Array[Dictionary] = _map_boundaries()
	map_marker_overlay.set_boundaries(boundaries)
	if minimap_marker_overlay != null:
		minimap_marker_overlay.set_boundaries(boundaries)

## The other regions' pictures beside the current one: the minimap's window
## reaches past the seam and the Tab map frames a collar of the neighbours, and
## the grey background there read as a hole in the world. Every exterior region
## the registry places on the continent gets a quad of its own picture on the
## map layer, whether or not its package is loaded: a resident neighbour's
## stands under its root (the rigid frame it stands in, so it travels with it)
## at its own picture height, and every other region stands in world_root on
## the frame the stream surveys for it. The current map's picture is built
## first and stands in its own frame as before. Called after the current
## picture is laid and whenever the stream's resident table changes.
func _install_neighbour_pictures() -> void:
	var detail_plan_changed := false
	if exterior_stream != null and not exterior_stream.residents_changed.is_connected(_install_neighbour_pictures):
		exterior_stream.residents_changed.connect(_install_neighbour_pictures)
	var residents: Dictionary = exterior_stream.residents if exterior_stream != null else {}
	var wanted: Array[String] = exterior_stream.continent_maps() if exterior_stream != null else ([] as Array[String])
	for map_id: String in residents.keys():
		if not wanted.has(map_id):
			wanted.append(map_id)
	# A picture whose frame changed - a region loaded, or the map swapped under
	# it at a crossing - is dropped here and built again below in its new one.
	for stale_id: String in _neighbour_pictures.keys():
		var stale: Variant = _neighbour_pictures[stale_id]
		var resident_root: Node3D = (residents.get(stale_id, {}) as Dictionary).get("root") as Node3D
		var frame: Node = resident_root if is_instance_valid(resident_root) else world_root
		if (not wanted.has(stale_id) or not is_instance_valid(stale)
				or (stale as Node).get_parent() != frame):
			if is_instance_valid(stale):
				(stale as Node).queue_free()
			_neighbour_pictures.erase(stale_id)
			detail_plan_changed = true
	for map_id: String in wanted:
		if _neighbour_pictures.has(map_id):
			continue
		var picture: Variant = _build_region_picture(map_id, residents.get(map_id, {}) as Dictionary)
		if picture is MeshInstance3D:
			_neighbour_pictures[map_id] = picture
			detail_plan_changed = true
	if detail_plan_changed:
		_map_detail_visible.clear()

## One region's picture: its own minimap pixels, framed as the Tab map frames
## that region. A resident region is laid under its root at its manifest's
## picture height; any other is laid in world_root on the join the stream
## surveys for it (or the continent translations the registry publishes), with
## its extent read from the published cartography, which carries the same crop
## the manifest would give. Those pictures sink a little for each further
## region so that two never fight over the same ground; the cameras look
## straight down, so the depth itself is never seen.
func _build_region_picture(map_id: String, resident: Dictionary) -> Variant:
	var region_index: int = _region_index_for_map(map_id)
	if region_index < 0 or exterior_stream == null:
		return null
	var region: Dictionary = cartography_regions[region_index] as Dictionary
	var texture: Texture2D = _tab_map_texture(region)
	if texture == null:
		return null
	var tab_map: Dictionary = region.get("tabMap", {}) as Dictionary
	var root: Node3D = resident.get("root") as Node3D
	var manifest: WorldManifest = resident.get("manifest") as WorldManifest
	var loaded: bool = is_instance_valid(root) and manifest != null
	var extent: Rect2 = (MapPicture.extent(manifest.data.get("minimap", {}) as Dictionary, tab_map)
		if loaded else MapPicture.tab_map_extent(tab_map))
	if extent.size.x <= 0.0 or extent.size.y <= 0.0:
		return null
	var height: float = (MapPicture.height_below(manifest.data) if loaded
		else _map_picture_height - MAP_PICTURE_SINK_METRES * float(region_index + 1))
	var picture := MapPicture.build(texture, extent, height, MAP_PICTURE_LAYER)
	if loaded:
		root.add_child(picture)
		return picture
	var frame_value: Variant = exterior_stream.region_transform(map_id)
	if not frame_value is Transform3D:
		picture.queue_free()
		return null
	world_root.add_child(picture)
	picture.transform = frame_value as Transform3D
	return picture

## The neighbours' pictures ahead of the crossing: a seamless handoff must not
## pay for a webp decode and an upload while the traveller drifts to its
## server target, so the textures of the maps the server lists as adjacent
## are decoded on the frames after a map load, one a frame, into the same
## cache the Tab map reads. The crossing then builds a quad over a cached
## texture. Called after each world load and whenever the adjacency changes.
func _queue_map_picture_warmup() -> void:
	var names: Array[String] = []
	for name_value: Variant in AppState.adjacent_maps.values():
		names.append(str(name_value))
	# The Tab map draws every region of the continent, loaded or not, so the
	# rest follow the adjacent ones into the cache a frame at a time.
	if exterior_stream != null:
		for map_id: String in exterior_stream.continent_maps():
			if not names.has(map_id):
				names.append(map_id)
	for name: String in names:
		var region_index: int = _region_index_for_map(name)
		if region_index < 0:
			continue
		var key: String = str((cartography_regions[region_index] as Dictionary).get("serverMap", ""))
		if _tab_map_textures.has(key) or _map_picture_warmup.has(name):
			continue
		_map_picture_warmup.append(name)
	if _map_picture_warmup.is_empty() or _map_picture_warmup_armed:
		return
	_map_picture_warmup_armed = true
	get_tree().create_timer(0.1).timeout.connect(_warm_one_map_picture, CONNECT_ONE_SHOT)

## Decodes one queued region's texture; re-arms for the next on a later frame.
func _warm_one_map_picture() -> void:
	_map_picture_warmup_armed = false
	if _map_picture_warmup.is_empty():
		return
	var name: String = _map_picture_warmup.pop_front()
	var region_index: int = _region_index_for_map(name)
	if region_index >= 0:
		_tab_map_texture(cartography_regions[region_index] as Dictionary)
	if not _map_picture_warmup.is_empty():
		_map_picture_warmup_armed = true
		get_tree().create_timer(0.1).timeout.connect(_warm_one_map_picture, CONNECT_ONE_SHOT)

## What the map cameras render: the picture alone while one stands, else the
## live world on layer 1 as they always did.
func _set_map_cameras_picture(picture: bool) -> void:
	var mask: int = MAP_PICTURE_LAYER if picture else 1
	map_camera.cull_mask = mask
	full_map_camera.cull_mask = mask

func _footstep_surface_at(tile: Vector2i) -> String:
	if gameplay_world == null or adapter == null:
		return "dirt"
	var actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	var footprint: Vector2i = AppState.footprint_for_actor_type(int(actor.get("actor_type", 0)))
	return FootstepSurface.at_position(gameplay_world.direct_space_state,
		adapter.footprint_center(tile.x, tile.y, footprint))

func _navigation_ray_position(origin: Vector3, direction: Vector3) -> Variant:
	if gameplay_world == null:
		return null
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(
		origin, origin + direction * 2000.0, WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit: Dictionary = gameplay_world.direct_space_state.intersect_ray(query)
	var position_value: Variant = hit.get("position")
	return position_value if position_value is Vector3 else null

func _sync_ground_bags() -> void:
	for raw_id: Variant in ground_bag_nodes.keys():
		var bag_id: int = int(raw_id)
		if not AppState.ground_bags.has(bag_id):
			var stale_value: Variant = ground_bag_nodes.get(bag_id)
			if is_instance_valid(stale_value):
				(stale_value as Node).queue_free()
			ground_bag_nodes.erase(bag_id)
	for raw_id: Variant in AppState.ground_bags:
		var bag_id: int = int(raw_id)
		var dto_value: Variant = AppState.ground_bags.get(bag_id)
		if not dto_value is Dictionary:
			continue
		var dto: Dictionary = dto_value as Dictionary
		if ground_bag_nodes.has(bag_id):
			var existing: GroundBag3D = ground_bag_nodes.get(bag_id) as GroundBag3D
			if is_instance_valid(existing):
				existing.global_position = adapter.tile_center(
					int(dto.get("x", 0)), int(dto.get("y", 0)))
				_place_ground_bag_on_surface(existing)
			continue
		var bag: GroundBag3D = GroundBag3D.new()
		bag.configure(dto, adapter)
		world_root.add_child(bag)
		ground_bag_nodes[bag_id] = bag
		_place_ground_bag_on_surface(bag)

func _place_ground_bag_on_surface(bag: GroundBag3D) -> void:
	_fit_lantern_map_marker(bag, "BagMapMarker")
	if not is_instance_valid(bag) or gameplay_world == null:
		return
	var ray_start: Vector3 = Vector3(bag.global_position.x, 400.0, bag.global_position.z)
	var ray_end: Vector3 = Vector3(bag.global_position.x, -100.0, bag.global_position.z)
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(
		ray_start, ray_end, WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit: Dictionary = gameplay_world.direct_space_state.intersect_ray(query)
	var position_value: Variant = hit.get("position")
	if position_value is Vector3:
		bag.set_surface_height((position_value as Vector3).y)
	else:
		bag.set_surface_height(adapter.walking_height)

func _sync_ground_bag() -> void:
	var is_open: bool = bool(AppState.ground_bag.get("open", false))
	ground_bag_panel.visible = is_open
	if not is_open:
		return
	# Both windows stay up together so items can move either way, and the world
	# underneath stays visible and clickable while they are open.
	if not inventory_panel.visible:
		inventory_panel.show()
		_sync_hud_button_states(true)
	_fill_ground_bag_grid(AppState.ground_bag.get("items", {}) as Dictionary)
	_sync_ground_bag_actions()
	_clamp_ground_bag_window_to_viewport()
	if _ground_bag_get_all_requested_msec >= 0:
		var requested_age: int = (Time.get_ticks_msec()
			- _ground_bag_get_all_requested_msec)
		var requested_bag_id: int = _ground_bag_get_all_bag_id
		_ground_bag_get_all_requested_msec = -1
		_ground_bag_get_all_bag_id = -1
		if requested_age <= GROUND_BAG_GET_ALL_TIMEOUT_MSEC \
				and int(AppState.ground_bag.get("bag_id", -1)) == requested_bag_id:
			var sent: int = _request_all_ground_bag_items()
			inventory_description.text = _ground_bag_get_all_message(sent)

func _sync_ground_bag_actions() -> void:
	var slot: int = selected_inventory_slot
	var droppable: bool = (slot >= 0 and slot < 36
		and AppState.inventory.get(slot) is Dictionary)
	ground_bag_drop_button.disabled = not droppable
	if droppable:
		var item: Dictionary = AppState.inventory.get(slot) as Dictionary
		ground_bag_drop_button.tooltip_text = ("Drop %d of the %d in inventory slot %d"
			% [mini(int(item.get("quantity", 1)), _selected_quantity()),
			int(item.get("quantity", 1)), slot + 1])
	else:
		ground_bag_drop_button.tooltip_text = ("Select an item in the inventory window"
			+ " to drop it here")

## Asks the server what the selected ground item is. The bag packet carries an
## image id and a quantity, so the description can only come from the server.
func _on_ground_bag_look_pressed(index: int) -> void:
	var slot: int = _ground_bag_slot_position(index)
	if slot < 0:
		return
	var error: Error = Network.look_at_ground_item(slot)
	if error != OK:
		push_warning("LOOK_AT_GROUND_ITEM failed: " + error_string(error))

## The reading window. The server models a book as research rather than as
## pages of text: using a book from the backpack consumes it and starts a
## timer, pages tick down, and the knowledge bit is set on completion. There is
## no page content on the wire to turn through, so this reports the thing that
## actually exists - which book, how far through, and what it unlocks - instead
## of a page-turning window with nothing behind it.
func _sync_reading() -> void:
	if reading_panel == null:
		return
	# Keep wrapping text from retaining a transient minimum height before the
	# anchored panel receives its final width. Longer details can scroll.
	reading_detail.fit_content = false
	var active: bool = bool(AppState.reading.get("active", false))
	var index: int = int(AppState.reading.get("index", -1))
	if not active:
		if _reading_completed_index >= 0:
			_present_completed_reading()
			return
		reading_panel.hide()
		return
	_reading_completed_index = index
	_reading_hidden = _reading_hidden and index == _reading_shown_index
	_reading_shown_index = index
	if _reading_hidden:
		reading_panel.hide()
		return
	var total: int = maxi(1, int(AppState.reading.get("pages_total", 1)))
	var read: int = clampi(int(AppState.reading.get("pages_read", 0)), 0, total)
	reading_title.text = "Reading %s" % _knowledge_title(index)
	reading_progress.max_value = total
	reading_progress.value = read
	reading_detail.text = ("%d of %d pages read (%d%%)
"
		+ "Reading finishes on its own; food keeps it going.") % [
		read, total, roundi(100.0 * float(read) / float(total))]
	reading_panel.show()

## Reading finished. The knowledge bit arrives as its own packet, so this shows
## what was actually gained rather than assuming completion implies it.
func _present_completed_reading() -> void:
	var index: int = _reading_completed_index
	_reading_completed_index = -1
	_reading_shown_index = -1
	_reading_hidden = false
	if not AppState.known_knowledge.has(index):
		reading_panel.hide()
		return
	reading_title.text = "Finished %s" % _knowledge_title(index)
	reading_progress.max_value = 1
	reading_progress.value = 1
	reading_detail.text = ("[color=#8fdc8f]Knowledge gained.[/color]
"
		+ "Recipes that needed it are now available.")
	reading_panel.show()

func _knowledge_title(index: int) -> String:
	if index >= 0 and index < knowledge_catalog.size():
		return knowledge_catalog[index]
	return "knowledge #%d" % index

func _on_reading_close_pressed() -> void:
	# Hiding the window does not stop the reading: the server owns that, and
	# there is no command to interrupt research.
	_reading_hidden = true
	reading_panel.hide()

func _sync_knowledge() -> void:
	if not stats_panel.visible or stats_tabs.current_tab != 1:
		return
	knowledge_list.clear()
	var known_only: bool = knowledge_known_only.button_pressed
	for knowledge_index: int in range(knowledge_catalog.size()):
		var is_known: bool = AppState.known_knowledge.has(knowledge_index)
		if known_only and not is_known:
			continue
		var item_index: int = knowledge_list.item_count
		knowledge_list.add_item("%s  %s" % ["[Read]" if is_known else "[Unread]",
			knowledge_catalog[knowledge_index]])
		knowledge_list.set_item_metadata(item_index, knowledge_index)
		knowledge_list.set_item_tooltip(item_index,
			"Knowledge #%d — %s" % [knowledge_index, "read" if is_known else "unread"])
		if knowledge_index == AppState.selected_knowledge:
			knowledge_list.select(item_index)
	var owned_count: int = AppState.known_knowledge.size()
	if AppState.selected_knowledge < 0 or AppState.selected_knowledge >= knowledge_catalog.size():
		knowledge_detail.text = ("Select an entry to request its server description.\n"
			+ "Read %d of %d knowledge entries." % [owned_count, knowledge_catalog.size()])
		return
	var selected_index: int = AppState.selected_knowledge
	var status: String = "Read" if AppState.known_knowledge.has(selected_index) else "Unread"
	var server_text: String = AppState.knowledge_text
	knowledge_detail.text = "%s\nStatus: %s\nKnowledge ID: %d\n\n%s" % [
		knowledge_catalog[selected_index], status, selected_index,
		server_text if not server_text.is_empty() else "Waiting for the server description…"]

## The manufacturing window, built around the list and detail panes the scene
## already holds. What is added here is everything with no fixed shape: a tab
## per mixing skill, a row per tool, a quantity that can be typed or stepped,
## and a queue.
func _build_manufacturing_window() -> void:
	var content: Node = manufacturing_filter.get_parent()
	manufacturing_status.custom_minimum_size.x = 620
	manufacturing_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	manufacturing_list.custom_minimum_size = Vector2(260, 210)
	manufacturing_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	(manufacturing_list.get_parent() as Control).size_flags_vertical = Control.SIZE_EXPAND_FILL
	manufacturing_filter.placeholder_text = "Search by name, ingredient or tool"
	manufacturing_ready_only = CheckButton.new()
	manufacturing_ready_only.name = "ManufacturingReadyOnly"
	manufacturing_ready_only.text = "Has ingredients only"
	manufacturing_ready_only.button_pressed = manufacturing_ready_preference
	manufacturing_ready_only.toggled.connect(func(pressed: bool) -> void:
		manufacturing_ready_preference = pressed
		_sync_manufacturing())
	content.add_child(manufacturing_ready_only)
	content.move_child(manufacturing_ready_only, manufacturing_filter.get_index() + 1)

	manufacturing_tabs = HFlowContainer.new()
	manufacturing_tabs.name = "ManufacturingTabs"
	manufacturing_tabs.alignment = FlowContainer.ALIGNMENT_CENTER
	content.add_child(manufacturing_tabs)
	content.move_child(manufacturing_tabs, manufacturing_filter.get_index())

	# The detail pane moves into a column of its own, so everything that acts
	# on the selected recipe sits under the description of it.
	manufacturing_side = VBoxContainer.new()
	manufacturing_side.name = "ManufacturingSide"
	manufacturing_side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	manufacturing_side.add_theme_constant_override("separation", 6)
	var side_column := VBoxContainer.new()
	side_column.name = "ManufacturingSideColumn"
	side_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	manufacturing_list.get_parent().add_child(side_column)
	var side_scroll := ScrollContainer.new()
	side_scroll.name = "ManufacturingDetailScroll"
	side_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	side_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	side_scroll.custom_minimum_size = Vector2(300, 120)
	side_column.add_child(side_scroll)
	side_scroll.add_child(manufacturing_side)
	manufacturing_detail.get_parent().remove_child(manufacturing_detail)
	manufacturing_side.add_child(manufacturing_detail)
	manufacturing_detail.owner = self
	manufacturing_detail.size_flags_vertical = Control.SIZE_EXPAND_FILL
	manufacturing_detail.custom_minimum_size.y = 120
	manufacturing_detail.custom_minimum_size.x = 300

	manufacturing_tool_rows = VBoxContainer.new()
	manufacturing_tool_rows.name = "ManufacturingTools"
	side_column.add_child(manufacturing_tool_rows)
	side_column.add_child(_manufacturing_quantity_row())

	# The scene's two mix buttons become Mix Now and Add To Queue. Reused
	# rather than hidden and replaced: the scene owns their names and the
	# methods it connects them to, and a second pair of buttons beside two
	# dead ones is worse than a pair whose node names have aged.
	var actions := HBoxContainer.new()
	actions.name = "ManufacturingActions"
	manufacturing_source = CheckButton.new()
	manufacturing_source.name = "Source"
	manufacturing_source.text = "From storage"
	manufacturing_source.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	manufacturing_source.toggled.connect(func(_pressed: bool) -> void:
		_sync_manufacturing())
	actions.add_child(manufacturing_source)
	for button: Button in [manufacturing_mix_one, manufacturing_mix_all]:
		button.get_parent().remove_child(button)
		actions.add_child(button)
	manufacturing_mix_one.text = "MIX NOW"
	manufacturing_mix_one.tooltip_text = "Start this batch now, ahead of the queue"
	manufacturing_mix_all.text = "ADD TO QUEUE"
	manufacturing_mix_all.tooltip_text = "Put this batch at the end of the queue"
	side_column.add_child(actions)
	for button: Button in [manufacturing_mix_one, manufacturing_mix_all]:
		button.owner = self

	var queue: Control = _manufacturing_queue_section()
	content.add_child(queue)
	content.move_child(queue, manufacturing_status.get_index())

## How many to make. Typed or stepped: the box is the value and the buttons
## only move it, so somebody who wants forty does not press one thirty-nine
## times.
func _manufacturing_quantity_row() -> Control:
	var row := HBoxContainer.new()
	row.name = "ManufacturingQuantity"
	var label := Label.new()
	label.name = "Label"
	label.text = "Quantity"
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(label)
	row.add_child(_manufacturing_step_button("−", -1))
	manufacturing_quantity = LineEdit.new()
	manufacturing_quantity.name = "Value"
	manufacturing_quantity.text = "1"
	manufacturing_quantity.alignment = HORIZONTAL_ALIGNMENT_CENTER
	manufacturing_quantity.custom_minimum_size = Vector2(64, 0)
	manufacturing_quantity.tooltip_text = ("How many to make, 1 to %d"
		% MANUFACTURING_MAX_QUANTITY)
	manufacturing_quantity.text_changed.connect(_on_manufacturing_quantity_changed)
	manufacturing_quantity.text_submitted.connect(func(_text: String) -> void:
		_set_manufacturing_quantity(_manufacturing_quantity_value()))
	manufacturing_quantity.focus_exited.connect(func() -> void:
		_set_manufacturing_quantity(_manufacturing_quantity_value()))
	row.add_child(manufacturing_quantity)
	row.add_child(_manufacturing_step_button("+", 1))
	return row

func _manufacturing_step_button(text: String, step: int) -> Button:
	var button := Button.new()
	button.name = "Step%s" % ("Up" if step > 0 else "Down")
	button.text = text
	button.custom_minimum_size = Vector2(28, 0)
	button.pressed.connect(func() -> void:
		_set_manufacturing_quantity(_manufacturing_quantity_value() + step))
	return button

## Read back clamped, always. An empty box on the way to "12" is somebody
## mid-thought rather than a zero, so it is left alone while it is being typed
## in and only rewritten when something else moves the value.
func _manufacturing_quantity_value() -> int:
	if manufacturing_quantity == null:
		return 1
	return clampi(int(manufacturing_quantity.text.strip_edges()), 1,
		MANUFACTURING_MAX_QUANTITY)

func _set_manufacturing_quantity(value: int) -> void:
	if manufacturing_quantity == null:
		return
	manufacturing_quantity.text = str(clampi(value, 1, MANUFACTURING_MAX_QUANTITY))
	manufacturing_quantity.caret_column = manufacturing_quantity.text.length()

func _on_manufacturing_quantity_changed(text: String) -> void:
	var digits := ""
	for character: String in text:
		if character >= "0" and character <= "9":
			digits += character
	if digits != text:
		manufacturing_quantity.text = digits
		manufacturing_quantity.caret_column = digits.length()

func _manufacturing_queue_section() -> Control:
	var box := VBoxContainer.new()
	box.name = "ManufacturingQueue"
	var head := HBoxContainer.new()
	head.name = "Head"
	var title := Label.new()
	title.name = "Title"
	title.text = "PRODUCTION QUEUE"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	manufacturing_queue_start = Button.new()
	manufacturing_queue_start.name = "Start"
	manufacturing_queue_start.text = "START QUEUE"
	manufacturing_queue_start.pressed.connect(_on_manufacturing_queue_start_pressed)
	head.add_child(manufacturing_queue_start)
	var clear := Button.new()
	clear.name = "Clear"
	clear.text = "Clear"
	clear.pressed.connect(_on_manufacturing_queue_clear_pressed)
	head.add_child(clear)
	box.add_child(head)
	manufacturing_queue_rows = VBoxContainer.new()
	manufacturing_queue_rows.name = "Rows"
	var scroll := ScrollContainer.new()
	scroll.name = "QueueScroll"
	scroll.custom_minimum_size.y = 72
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	manufacturing_queue_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_child(scroll)
	scroll.add_child(manufacturing_queue_rows)
	return box

## Whether a batch would be drawn from the storage box. The toggle alone is
## not enough: walking away from storage has to stop meaning storage, and the
## server is the only thing that knows how far away the keeper is.
func _manufacturing_from_storage() -> bool:
	return (manufacturing_source != null and manufacturing_source.button_pressed
		and bool(AppState.mix_state.get("near_storage", false)))

## A tab per mixing skill the served recipes actually mention, and an "All"
## that is not a skill. Nothing local decides the list, so a profile that adds
## a skill grows a tab without being told about it.
func _manufacturing_skills() -> Array[String]:
	var skills: Array[String] = []
	for index: int in range(manufacturing_catalog.count()):
		var skill: String = str(manufacturing_catalog.recipe(index).get("skill", ""))
		if not skill.is_empty() and not skills.has(skill):
			skills.append(skill)
	skills.sort()
	return skills

func _sync_manufacturing_tabs() -> void:
	if manufacturing_tabs == null:
		return
	for child: Node in manufacturing_tabs.get_children():
		manufacturing_tabs.remove_child(child)
		child.queue_free()
	manufacturing_tabs.add_child(_manufacturing_tab("All", ""))
	for skill: String in _manufacturing_skills():
		manufacturing_tabs.add_child(_manufacturing_tab(skill.capitalize(), skill))

func _manufacturing_tab(text: String, skill: String) -> Button:
	var tab := Button.new()
	tab.name = "Tab%s" % text.replace(" ", "").validate_node_name()
	tab.text = text
	tab.toggle_mode = true
	tab.button_pressed = manufacturing_skill == skill
	# The same picture the encyclopedia shelves that skill under, so the two
	# windows name it the same way. The All tab is not a skill, and asks for
	# the sheet's own picture for "everything".
	var icon: Texture2D = SubjectIcons.icon_for("all" if skill.is_empty() else skill)
	if icon != null:
		tab.icon = icon
		tab.add_theme_constant_override("h_separation", 6)
	tab.pressed.connect(func() -> void:
		manufacturing_skill = skill
		_sync_manufacturing())
	return tab

func _sync_manufacturing() -> void:
	if not manufacturing_panel.visible:
		return
	_sync_manufacturing_source()
	_sync_manufacturing_tabs()
	manufacturing_list.clear()
	var filter_text: String = manufacturing_filter.text.strip_edges().to_lower()
	for recipe_index: int in range(manufacturing_catalog.count()):
		var definition: Dictionary = manufacturing_catalog.recipe(recipe_index)
		if (not manufacturing_skill.is_empty()
				and str(definition.get("skill", "")) != manufacturing_skill):
			continue
		if not filter_text.is_empty() and not _manufacturing_searchable(
				definition).contains(filter_text):
			continue
		var availability := _manufacturing_availability(recipe_index)
		var reasons: Array = availability.get("reasons", []) as Array
		if manufacturing_ready_only.button_pressed and not bool(availability.get("ingredients_available", false)):
			continue
		var reason_lines: Array[String] = []
		for reason_value: Variant in reasons:
			reason_lines.append(str(reason_value))
		var item_index: int = manufacturing_list.item_count
		manufacturing_list.add_item("%s  %s — %s %d" % [
			"[Ready]" if reasons.is_empty() else "[Blocked]",
			str(definition.get("output", "Unknown")),
			str(definition.get("skill", "skill")).capitalize(),
			int(definition.get("level", 0))])
		manufacturing_list.set_item_metadata(item_index, recipe_index)
		manufacturing_list.set_item_tooltip(item_index,
			"Ready for server validation" if reasons.is_empty()
			else "\n".join(reason_lines))
		var output_icon: Texture2D = item_atlas.icon_for(
			int(definition.get("outputImageId", -1)))
		if output_icon != null:
			manufacturing_list.set_item_icon(item_index, output_icon)
		if recipe_index == selected_manufacturing_recipe:
			manufacturing_list.select(item_index)
	if manufacturing_list.get_selected_items().is_empty():
		selected_manufacturing_recipe = -1
	_sync_manufacturing_detail()
	_sync_manufacturing_queue()

func _manufacturing_availability(recipe_index: int) -> Dictionary:
	var availability := manufacturing_catalog.availability(recipe_index,
		AppState.inventory, AppState.known_knowledge, AppState.stats,
		AppState.inventory_names)
	var definition := manufacturing_catalog.recipe(recipe_index)
	if definition.get("skill", "") == "summoning":
		var nexus := int(definition.get("animalNexus", 0))
		if int(AppState.stats.get("animal_nexus", 0)) < nexus:
			availability.reasons.append("Needs Animal Nexus %d" % nexus)
		if bool(AppState.combat_state.get("active", false)):
			availability.reasons.append("You cannot summon while in combat")
	return availability

## What the search box matches against: the result, the skill, and everything
## the recipe consumes or needs to hand. Searching for "hatchet" should find
## what a hatchet is for, not only the hatchet.
func _manufacturing_searchable(definition: Dictionary) -> String:
	var text: String = "%s %s" % [str(definition.get("output", "")),
		str(definition.get("skill", ""))]
	for key: String in ["ingredients", "tools"]:
		var listed: Variant = definition.get(key, [])
		if listed is Array:
			for value: Variant in listed as Array:
				if value is Dictionary:
					text += " " + str((value as Dictionary).get("name", ""))
	return text.to_lower()

func _sync_manufacturing_detail() -> void:
	var failed := manufacturing_server_status.to_lower().contains("fail") or manufacturing_server_status.to_lower().contains("interrupted")
	manufacturing_status.add_theme_color_override("font_color", Color(1.0, 0.38, 0.32) if failed else Color(0.88, 0.9, 0.82))
	_sync_manufacturing_source()
	var definition: Dictionary = manufacturing_catalog.recipe(
		selected_manufacturing_recipe)
	if definition.is_empty():
		manufacturing_detail.text = ("No recipes match these filters. Check your ingredients or turn off Has ingredients only."
			if manufacturing_list.item_count == 0 else "Select a recipe to see what it takes.")
		manufacturing_status.text = manufacturing_server_status
		_sync_manufacturing_tools([])
		manufacturing_mix_one.disabled = true
		manufacturing_mix_all.disabled = true
		return
	var from_storage: bool = _manufacturing_from_storage()
	var lines: Array[String] = ["[b]%s[/b]" % str(definition.get("output", "Unknown")),
		"%s level %d  •  %d experience  •  food %d  •  mana %d" % [
			str(definition.get("skill", "skill")).capitalize(),
			int(definition.get("level", 0)), int(definition.get("experience", 0)),
			int(definition.get("food", 0)), int(definition.get("mana", 0))],
		"", "Ingredients:"]
	var ingredients_value: Variant = definition.get("ingredients", [])
	if ingredients_value is Array:
		for ingredient_value: Variant in ingredients_value as Array:
			if not ingredient_value is Dictionary:
				continue
			var ingredient: Dictionary = ingredient_value as Dictionary
			var name: String = str(ingredient.get("name", "Unknown"))
			var line: String = "  • %s ×%d" % [name,
				int(ingredient.get("quantity", 0))]
			var carried: int = _carried_count(name)
			if not from_storage and carried >= 0:
				line += "  (carrying %d)" % carried
			lines.append(line)
	var knowledge: String = str(definition.get("knowledge", ""))
	if not knowledge.is_empty():
		lines.append("Knowledge: " + knowledge)
	var availability := _manufacturing_availability(selected_manufacturing_recipe)
	var reasons: Array = availability.get("reasons", []) as Array
	if from_storage:
		# The client has never been sent the contents of the storage box, so
		# it cannot say whether a mix will succeed; only the server can, and
		# it says so plainly when it refuses.
		lines.append("\nDrawing from storage, which this window cannot see. "
			+ "The server refuses if the box is short.")
	elif reasons.is_empty():
		lines.append("\nReady. The server remains authoritative for skill chance, "
			+ "special days, combat, capacity, and ingredient state.")
	else:
		lines.append("\nUnavailable:")
		for reason_value: Variant in reasons:
			lines.append("  • " + str(reason_value))
	manufacturing_detail.text = "\n".join(lines)
	manufacturing_status.text = manufacturing_server_status
	_sync_manufacturing_tools(manufacturing_catalog.tool_state(
		selected_manufacturing_recipe, AppState.inventory, AppState.inventory_names))
	# Blocked by what the client can see is only a fair reason to refuse when
	# the client can see the source. Mixing from storage is always offered and
	# the server answers it.
	manufacturing_mix_one.disabled = not from_storage and not reasons.is_empty()
	manufacturing_mix_all.disabled = false

## How many of an item are being carried, or -1 when the client cannot say.
## Without the server's slot names an item is only recognisable by artwork,
## which several items share, and a wrong count is worse than no count.
func _carried_count(name: String) -> int:
	if AppState.inventory_names.is_empty():
		return -1
	var total := 0
	for slot_value: Variant in AppState.inventory:
		var slot: int = int(slot_value)
		if str(AppState.inventory_names.get(slot, "")) != name:
			continue
		var item_value: Variant = AppState.inventory.get(slot)
		if item_value is Dictionary:
			total += int((item_value as Dictionary).get("quantity", 0))
	return total

## The storage toggle is the server's to allow: whether a storage keeper is
## close enough is a distance to an actor this client is never told the role
## of, so the window waits to be told rather than guessing. Guessing would
## grey the control out in the one place somebody wanted it.
func _sync_manufacturing_source() -> void:
	if manufacturing_source == null:
		return
	var near: bool = bool(AppState.mix_state.get("near_storage", false))
	manufacturing_source.disabled = not near
	if not near and manufacturing_source.button_pressed:
		# Walking away from storage cannot leave the window pointed at a box
		# it can no longer reach.
		manufacturing_source.set_pressed_no_signal(false)
	manufacturing_source.tooltip_text = ("Take the ingredients from your storage box"
		if near else "Stand next to a storage keeper to mix from storage")
	if manufacturing_ready_only != null:
		var from_storage := _manufacturing_from_storage()
		manufacturing_ready_only.disabled = from_storage
		manufacturing_ready_only.set_pressed_no_signal(
			manufacturing_ready_preference and not from_storage)
		manufacturing_ready_only.tooltip_text = (
			"Storage contents aren't shown here. Switch to your inventory to filter by ingredients."
			if from_storage else "Show recipes with ingredients in your pack. Select a recipe to check food, mana, tools and books.")

## One row per tool, and a way to fix a missing one without leaving.
##
## A tool is held rather than consumed, so it is wanted in hand however the
## ingredients are sourced - which is why the button is offered whenever
## storage is in reach, not only when the window is mixing out of it.
func _sync_manufacturing_tools(tools: Array[Dictionary]) -> void:
	if manufacturing_tool_rows == null:
		return
	for child: Node in manufacturing_tool_rows.get_children():
		manufacturing_tool_rows.remove_child(child)
		child.queue_free()
	if tools.is_empty():
		return
	var heading := Label.new()
	heading.name = "Heading"
	heading.text = "Tools"
	manufacturing_tool_rows.add_child(heading)
	var near: bool = bool(AppState.mix_state.get("near_storage", false))
	for tool: Dictionary in tools:
		var tool_name: String = str(tool.get("name", "tool"))
		var held: bool = bool(tool.get("held", false))
		var row := HBoxContainer.new()
		row.name = "Tool%s" % tool_name.replace(" ", "").validate_node_name()
		var label := Label.new()
		label.name = "Name"
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if held:
			label.text = "%s — to hand" % tool_name
		elif bool(tool.get("ambiguous", false)):
			label.text = "%s — shares artwork; cannot tell" % tool_name
		else:
			label.text = "%s — missing" % tool_name
			row.modulate = Color(1, 1, 1, 0.75)
		row.add_child(label)
		if not held:
			var take := Button.new()
			take.name = "Take"
			take.text = "Take from storage"
			take.disabled = not near
			take.tooltip_text = ("Take one out of your storage box" if near
				else "Stand next to a storage keeper to do this")
			take.pressed.connect(_on_manufacturing_take_tool_pressed.bind(tool_name))
			row.add_child(take)
		manufacturing_tool_rows.add_child(row)

func _sync_manufacturing_queue() -> void:
	if manufacturing_queue_rows == null:
		return
	for child: Node in manufacturing_queue_rows.get_children():
		manufacturing_queue_rows.remove_child(child)
		child.queue_free()
	manufacturing_queue_start.text = ("STOP QUEUE" if manufacturing_queue_running
		else "START QUEUE")
	manufacturing_queue_start.disabled = manufacturing_queue.is_empty()
	if manufacturing_queue.is_empty():
		var empty := Label.new()
		empty.name = "Empty"
		empty.text = "Nothing queued. Pick a recipe and add it."
		manufacturing_queue_rows.add_child(empty)
		return
	for position: int in range(manufacturing_queue.size()):
		manufacturing_queue_rows.add_child(_manufacturing_queue_row(position))

## One queued batch. Only the entry the queue has reached is being worked; the
## rest wait their turn, because the server mixes one batch at a time and a
## list means the order it is written in.
func _manufacturing_queue_row(position: int) -> Control:
	var entry: Dictionary = manufacturing_queue[position]
	var made: int = int(entry.get("made", 0))
	var wanted: int = maxi(1, int(entry.get("wanted", 1)))
	var working: bool = (manufacturing_queue_running
		and position == manufacturing_queue_index)
	var row := HBoxContainer.new()
	row.name = "Queued%d" % position
	if made >= wanted:
		row.modulate = Color(1, 1, 1, 0.6)
	var label := Label.new()
	label.name = "Name"
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.text = "%d. %s ×%d" % [position + 1, str(manufacturing_catalog.recipe(
		int(entry.get("recipe", -1))).get("output", "Unknown")), wanted]
	row.add_child(label)
	var bar := ProgressBar.new()
	bar.name = "Progress"
	bar.custom_minimum_size = Vector2(120, 0)
	bar.max_value = wanted
	bar.value = made
	bar.tooltip_text = "%d of %d made" % [made, wanted]
	row.add_child(bar)
	var state := Label.new()
	state.name = "State"
	state.custom_minimum_size = Vector2(72, 0)
	state.text = ("Working" if working else ("Done" if made >= wanted else "Waiting"))
	row.add_child(state)
	if not working:
		var remove := Button.new()
		remove.name = "Remove"
		remove.text = "✕"
		remove.tooltip_text = "Take this out of the queue"
		remove.pressed.connect(_on_manufacturing_queue_remove_pressed.bind(position))
		row.add_child(remove)
	return row

## Anything the camera has to look through to see the player is blended towards
## glass. Only actual imported active/resident roots are indexed, so actors,
## ground bags and the camera rig are never candidates. Promotion retains the
## same root's materials and fade progress.
func _configure_occluder_fade(manifest: WorldManifest) -> void:
	var count: int = occluder_fade.sync_worlds(manifest, world_loader.world_root, exterior_stream.residents)
	occluder_fade.set_enabled(_show_through_obstacles)
	print_debug("occluder_fade stage=indexed map=", AppState.current_map,
		" meshes=", count)

## The probe needs both ends of the sight line, and the local actor is absent
## between a map change and the first actor list, so a frame without one simply
## lets whatever is faded blend back to solid.
func _update_occluder_fade(delta: float) -> void:
	occluder_fade.sync_worlds(world_loader.manifest, world_loader.world_root, exterior_stream.residents)
	var target_value: Variant = actor_nodes.get(AppState.local_actor_id)
	var target: Node3D = target_value as Node3D if target_value is Node3D else null
	occluder_fade.update(delta, gameplay_camera, target)

## Which actors animate this frame, and how often. Every actor's skeleton
## used to be posed and every skinned mesh re-skinned every frame whether or
## not the camera could see it, which was most of the frame on a populated
## map. The half-rate players are stepped from here every frame; who is in
## which tier is re-read on a slower clock. The local player is never gated:
## the camera is looking at them by definition.
##
## The re-read walks every actor, so it is spread over `GATE_SWEEP_SLICES`
## frames instead of done in one: at 300 actors the whole walk was a 2-3 ms
## frame ten times a second, which a 60 Hz frame's 95th percentile sees, the
## more so when it fell on a frame that also carried a burst of server steps.
func _update_animation_gate(delta: float) -> void:
	animation_gate.advance(delta)
	client_runtime.observe_gate(animation_gate)
	if _declutter_due:
		_declutter_due = false
		_declutter_actor_overheads(_declutter_due_target)
	var now: int = Time.get_ticks_msec()
	if not _gate_sweep_active:
		if now < _animation_gate_refresh_msec:
			return
		# A clock at 0 is a fixture asking for the whole walk now; the old gate
		# (crowd presentation off) always walks everyone in one frame.
		var whole: bool = _animation_gate_refresh_msec <= 0 or not crowd.gate
		_animation_gate_refresh_msec = now + ANIMATION_GATE_REFRESH_MSEC
		_begin_gate_sweep(now, whole)
	animation_gate.begin(gameplay_camera)
	var total: int = _gate_sweep_ids.size()
	var stop: int = total if _gate_sweep_whole else mini(total,
		_gate_sweep_index + ceili(float(total) / float(GATE_SWEEP_SLICES)))
	while _gate_sweep_index < stop:
		_gate_classify(_gate_sweep_ids[_gate_sweep_index])
		_gate_sweep_index += 1
	if _gate_sweep_index >= total:
		_finish_gate_sweep()

## Starts one walk over the actors. Where "far away" is measured from is the
## player, not the camera, so that swinging or zooming the rig does not make
## bodies come and go around them; it and the camera are read once a sweep.
func _begin_gate_sweep(now: int, whole: bool) -> void:
	_gate_sweep_active = true
	_gate_sweep_whole = whole
	_gate_sweep_ids = actor_nodes.keys()
	_gate_sweep_index = 0
	_gate_now = now
	var local_value: Variant = actor_nodes.get(AppState.local_actor_id)
	_gate_local = local_value as Node3D if is_instance_valid(local_value) else null
	_gate_here = _gate_local.global_position if _gate_local != null else Vector3.ZERO
	_gate_fighting = _combat_target_actor_id()
	_gate_reference = _gate_here if _gate_local != null else _crowd_reference_point()
	_gate_camera_at = (gameplay_camera.global_position
		if gameplay_camera != null and gameplay_camera.is_inside_tree() else _gate_here)
	_gate_build_candidates = []
	_gate_releases = []
	_gate_built = 0
	_gate_ranked = []
	_gate_built_ranked = []
	_gate_full_rate = []
	_gate_capes = []

## One actor's part of the sweep: its tier, whether it is drawn, its name's
## fade, and - for the crowd presentation - its build rank or release.
func _gate_classify(raw_id: Variant) -> void:
	var actor_value: Variant = actor_nodes.get(raw_id)
	if not is_instance_valid(actor_value):
		return
	var actor: ReplicatedActor3D = actor_value as ReplicatedActor3D
	if actor == null or not actor.is_inside_tree():
		return
	if int(raw_id) == AppState.local_actor_id:
		actor.set_drawn(true)
		_gate_built += 1
		actor.set_animation_tier(AnimationGate.Tier.FULL, animation_gate)
		return
	var tier: AnimationGate.Tier = animation_gate.classify(actor.global_position + Vector3.UP,
		actor.view_radius())
	var distance: float = (0.0 if _gate_local == null
		else _gate_here.distance_to(actor.global_position))
	var drawn: bool = distance <= ACTOR_DRAW_DISTANCE_METRES
	actor.set_drawn(drawn)
	# A body too far away to be drawn has nothing to show for being animated;
	# the frustum alone left those in view of the camera at full or half rate.
	if not drawn and crowd.gate:
		tier = AnimationGate.Tier.PAUSED
	# Whoever the player is fighting keeps their name and bar at any range: a
	# shot lined up from across a field still needs both.
	actor.set_overhead_fade(1.0 if int(raw_id) == _gate_fighting
		else nameplate_fade(distance, _name_distance_metres))
	if crowd.lazy:
		var ground: float = Vector2(actor.global_position.x - _gate_reference.x,
			actor.global_position.z - _gate_reference.z).length()
		var priority: bool = _crowd_priority_actor(int(raw_id))
		if actor.is_model_deferred():
			# Past the body cap only the map dot is left (crowd_presentation.gd).
			actor.set_crowd_hidden(not priority and ground > _body_cap_distance)
			if ground <= crowd.BUILD_RADIUS_METRES and not actor.corpse_faded():
				_gate_build_candidates.append([ground, int(raw_id)])
				if not priority:
					_gate_ranked.append(ground)
		else:
			_gate_built += 1
			if not priority:
				_gate_ranked.append(ground)
				_gate_built_ranked.append([ground, int(raw_id)])
			if crowd.release_due(int(raw_id), ground > crowd.RELEASE_RADIUS_METRES
					and not priority, _gate_now):
				_gate_releases.append([ground, int(raw_id)])
	else:
		_gate_built += 1
	# Paused bodies rank behind every other: a strike can still wake one for its
	# clip (`set_animation_tier`), and its cape with it.
	if crowd.gate and actor.wears_cape_cloth():
		_gate_capes.append([_gate_camera_at.distance_squared_to(actor.global_position)
			+ (1.0e9 if tier == AnimationGate.Tier.PAUSED else 0.0), actor])
	if crowd.gate and (tier == AnimationGate.Tier.FULL
			or (tier == AnimationGate.Tier.HALF and crowd.quarter)):
		# Settled when the sweep ends (`_apply_crowd_full_rate`); a body that
		# has just come into view animates meanwhile. Past 45 m a body is never
		# stepped more often than every other frame.
		_gate_full_rate.append([_gate_camera_at.distance_squared_to(actor.global_position),
			actor, tier])
		if actor.animation_tier() == AnimationGate.Tier.PAUSED \
				or (tier == AnimationGate.Tier.HALF and actor.animation_tier() == AnimationGate.Tier.FULL):
			actor.set_animation_tier(AnimationGate.Tier.HALF, animation_gate)
		return
	actor.set_animation_tier(tier, animation_gate)

## What needs the whole crowd: full-rate ranks, the cloth budget, the body
## count and cap, the build ranks, releases, and the overhead declutter.
func _finish_gate_sweep() -> void:
	_gate_sweep_active = false
	_gate_sweep_ids = []
	_apply_crowd_full_rate(_gate_full_rate)
	_apply_cloth_budget(_gate_capes)
	_built_bodies = _gate_built
	if crowd.lazy:
		_body_cap_distance = INF
		if crowd.body_cap > 0 and _gate_ranked.size() > crowd.body_cap:
			_gate_ranked.sort()
			_body_cap_distance = float(_gate_ranked[crowd.body_cap - 1])
			for pair: Array in _gate_built_ranked:
				if float(pair[0]) > _body_cap_distance + crowd.BODY_CAP_HYSTERESIS_METRES:
					_gate_releases.append(pair)
		crowd.set_candidates(_gate_build_candidates)
		_release_bodies(_gate_releases)
	# The declutter walks the whole crowd again, so a sliced sweep leaves it to
	# the next frame rather than add it to the frame that already carries the
	# sweep's crowd-wide decisions. A whole walk (a fixture, the old gate)
	# declutters at once.
	if _gate_sweep_whole:
		_declutter_actor_overheads(_gate_fighting)
	else:
		_declutter_due = true
		_declutter_due_target = _gate_fighting
	_gate_full_rate = []
	_gate_capes = []

## Full-rate animation for the bodies nearest the camera only. In a crowd of
## more than `FULL_RATE_BODIES` animated bodies in view, the farther ones are
## stepped at half rate - every other frame, by the time both frames covered,
## so they move at the same speed - as bodies beyond 45 m always were. A clip
## that does not loop plays out at half rate there too (`set_animation_tier`).
## With the quarter tier, bodies beyond 45 m are ranked too, and every body
## after the next `HALF_RATE_BODIES` is stepped every fourth frame.
func _apply_crowd_full_rate(full_rate: Array) -> void:
	if full_rate.size() > crowd.full_rate_bodies:
		full_rate.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	var rank: int = 0
	for entry: Array in full_rate:
		# A body replaced during the sweep is not ranked; its successor is next time.
		if not is_instance_valid(entry[1]):
			continue
		var tier := AnimationGate.Tier.HALF
		if rank < crowd.full_rate_bodies and entry[2] == AnimationGate.Tier.FULL:
			tier = AnimationGate.Tier.FULL
		elif crowd.quarter and rank >= crowd.full_rate_bodies + crowd.half_rate_bodies:
			tier = AnimationGate.Tier.QUARTER
		(entry[1] as ReplicatedActor3D).set_animation_tier(tier, animation_gate)
		rank += 1

## Cape cloth for the caped bodies nearest the camera only. The solver is the
## largest per-body cost of an equipped crowd (about 0.2 ms a cape a frame
## headless on the development laptop, nearer 0.4 ms rendered), so past
## `CLOTH_BODIES` a cape hangs as every non-local cape already does below High
## quality. At most `CLOTH_BODIES` simulate; one that is simulating counts as
## `CLOTH_HYSTERESIS` places nearer than it is, so it keeps its cloth until a
## cape that many places nearer needs the room or it falls that far past the
## limit, and capes on the boundary do not take turns as the crowd mills. (The
## hysteresis once let a simulating cape stay without counting against the
## limit, and a milling crowd settled at twelve.)
func _apply_cloth_budget(capes: Array) -> void:
	if capes.size() <= crowd.cloth_bodies:
		for entry: Array in capes:
			if is_instance_valid(entry[1]):
				(entry[1] as ReplicatedActor3D).set_cape_cloth_allowed(true)
		return
	capes.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	var bodies: Array[ReplicatedActor3D] = []
	var claims: Array = []
	for entry: Array in capes:
		if not is_instance_valid(entry[1]):
			continue
		var actor := entry[1] as ReplicatedActor3D
		var rank: int = bodies.size()
		var keeping: int = crowd.CLOTH_HYSTERESIS if actor.cape_cloth_allowed() else 0
		bodies.append(actor)
		if rank < crowd.cloth_bodies + keeping:
			claims.append([rank - keeping, rank])
	claims.sort_custom(func(a: Array, b: Array) -> bool:
		return a[0] < b[0] if a[0] != b[0] else a[1] < b[1])
	var allowed: Dictionary = {}
	for claim: Array in claims.slice(0, crowd.cloth_bodies):
		allowed[int(claim[1])] = true
	for rank: int in bodies.size():
		bodies[rank].set_cape_cloth_allowed(allowed.has(rank))

## Gives up the bodies `_update_animation_gate` found far out of range for long
## enough, or past the body cap's distance by more than its hysteresis,
## farthest first and a few a pass: each becomes a deferred node again.
func _release_bodies(releases: Array) -> void:
	if releases.is_empty():
		return
	releases.sort_custom(func(a: Array, b: Array) -> bool: return a[0] > b[0])
	var done: Dictionary = {}
	for pair: Array in releases:
		if done.size() >= crowd.RELEASES_PER_PASS:
			break
		var id: int = int(pair[1])
		if done.has(id) or not actor_nodes.has(id):
			continue
		done[id] = true
		_replace_actor_node(id, false)
		crowd.forget(id)
		crowd.releases += 1

## Keep player banners readable without making creatures hide one another.
## A creature yields only to visible player banners; the combat target stays
## readable even there. NPC and player banners retain their overlap filtering.
## Bodies and interaction targets remain independent of overhead visibility.
func _declutter_actor_overheads(target_id: int) -> void:
	var candidates: Array[Dictionary] = []
	for raw_id: Variant in actor_nodes:
		var actor := actor_nodes[raw_id] as ReplicatedActor3D
		if not is_instance_valid(actor) or not actor.is_inside_tree():
			continue
		if int(raw_id) == AppState.local_actor_id or actor.overhead_fade() <= 0.0:
			actor.set_overhead_crowded(false)
			continue
		var point := actor.global_position + Vector3.UP * (actor.head_height() + 0.35)
		if gameplay_camera.is_position_behind(point):
			actor.set_overhead_crowded(true)
			continue
		var dto: Dictionary = AppState.actors.get(raw_id, {})
		var actor_type := _minimap_actor_type(dto)
		var priority := 0 if int(raw_id) == target_id else (2 if actor_type in [&"creature", &"invasion"] else 1)
		var screen := gameplay_camera.unproject_position(point)
		if not Rect2(Vector2.ZERO, Vector2(main_viewport.size)).grow(80).has_point(screen):
			actor.set_overhead_crowded(true)
			continue
		candidates.append({"actor": actor, "id": int(raw_id), "priority": priority,
			"type": actor_type,
			"distance": actor.global_position.distance_squared_to(camera_rig.focus),
			"rect": overhead_block_rect(screen, str(dto.get("name", "")),
				actor.occupation(), actor.status_effect_count())})
	candidates.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if a.priority != b.priority: return a.priority < b.priority
		if a.distance != b.distance: return a.distance < b.distance
		return a.id < b.id)
	var occupied: Array[Rect2] = []
	var player_occupied: Array[Rect2] = []
	if actor_resource_overlay.visible:
		var scale_to_view := Vector2(main_viewport.size) / viewport_container.size
		var own := actor_resource_overlay.get_global_rect()
		var own_rect := Rect2((own.position - viewport_container.global_position) * scale_to_view,
			own.size * scale_to_view)
		occupied.append(own_rect)
		player_occupied.append(own_rect)
	for candidate: Dictionary in candidates:
		var crowded := false
		var creature: bool = candidate.type in [&"creature", &"invasion"]
		var obstacles: Array[Rect2] = player_occupied if creature else occupied
		if candidate.id != target_id:
			for previous: Rect2 in obstacles:
				if previous.grow(3).intersects(candidate.rect):
					crowded = true
					break
		(candidate.actor as ReplicatedActor3D).set_overhead_crowded(crowded)
		if not crowded and not creature:
			occupied.append(candidate.rect)
			if candidate.type == &"player" and (candidate.actor as ReplicatedActor3D)._overhead_shown():
				player_occupied.append(candidate.rect)

## The screen space an actor's overhead block claims when names are
## decluttered: the name, and the health row under it, round `screen`. An
## occupation is a line more of the same block, under the name: it claims its
## own width and pushes the block's bottom down a line, so two NPCs standing
## close do not draw one's occupation through the other's name.
static func overhead_block_rect(screen: Vector2, actor_name: String,
		occupation: String = "", negative_status_count: int = 0) -> Rect2:
	var width := maxf(110.0, _overhead_text_width(actor_name, 12) + 12.0)
	var height := 38.0
	if not occupation.is_empty():
		width = maxf(width, _overhead_text_width("<%s>" % occupation,
			ReplicatedActor3D.OCCUPATION_FONT_SIZE) + 12.0)
		height += ReplicatedActor3D.OCCUPATION_DROP
	var top := 12.0
	if negative_status_count > 0:
		width = maxf(width, StatusEffectIcons.width(negative_status_count) + 8.0)
		var rise: float = ReplicatedActor3D.NEGATIVE_STATUS_RISE
		top = rise + ReplicatedActor3D.NEGATIVE_STATUS_SIZE * 0.5 + 2.0 + StatusEffectIcons.extra_height(negative_status_count)
		height += top - 12.0
	return Rect2(screen - Vector2(width * 0.5, top), Vector2(width, height))

## Text widths for the overhead blocks, by size and text. The declutter pass
## measured every name in view with the font ten times a second; a crowd's
## names do not change between passes. Emptied when it grows past a few
## thousand entries, so a long session cannot grow it without bound.
static var _overhead_text_widths: Dictionary = {}

static func _overhead_text_width(text: String, font_size: int) -> float:
	var key := "%d|%s" % [font_size, text]
	if not _overhead_text_widths.has(key):
		if _overhead_text_widths.size() >= 4096:
			_overhead_text_widths.clear()
		_overhead_text_widths[key] = ThemeDB.fallback_font.get_string_size(
			text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	return float(_overhead_text_widths[key])

## How much of an actor's overhead block shows at this distance from the
## player: all of it up to `NAME_FADE_METRES` short of the name distance,
## nothing from the name distance on, and a straight fade between.
static func nameplate_fade(distance: float, name_distance: float) -> float:
	return clampf((name_distance - distance) / NAME_FADE_METRES, 0.0, 1.0)

## Interiors are closed boxes, so the isometric rig would render their ceiling
## and near wall. The manifest names the nodes to cut away; maps without a
## `cutaway` block (the city) are left exactly as loaded.
## A secrets map declares `secret: true` and its sections; everything that is
## not the player's section is hidden, which is what keeps the rest of the
## map off the viewport, the minimap and the full map.
func _configure_secret_sections(manifest: WorldManifest) -> void:
	var count: int = secret_sections.call("configure", manifest, world_root)
	if count > 0:
		_update_secret_sections(true)


func _update_secret_sections(force: bool = false) -> void:
	if not bool(secret_sections.call("is_active")):
		return
	var local_actor_node: Node3D = actor_nodes.get(AppState.local_actor_id) as Node3D
	if local_actor_node == null:
		return
	var previous_section: String = secret_sections.current_section()
	secret_sections.call("update", local_actor_node.global_position, force)
	if secret_sections.current_section() != previous_section:
		_full_map_panned = false
		_configure_full_map(world_loader.manifest)
		_request_map_redraw()
	# whoever and whatever stands in another secret stays unseen
	secret_sections.call("cull_dynamic", actor_nodes.values(), local_actor_node)
	secret_sections.call("cull_dynamic", map_object_nodes.values())


func _configure_interior_cutaway(manifest: WorldManifest) -> void:
	var count: int = interior_cutaway.configure(manifest, world_root)
	if count > 0:
		interior_cutaway.update(camera_rig.yaw_degrees, true)
		print_debug("interior_cutaway stage=applied map=", AppState.current_map,
			" nodes=", count)


func _configure_full_map(manifest: WorldManifest) -> void:
	_cancel_full_map_drag()
	var map_id := MapRegistry.normalize_server_map_id(AppState.current_map)
	if map_id.is_empty():
		map_id = manifest.asset_id()
	var changed_map := map_id != _full_map_region_id
	if changed_map:
		_full_map_region_id = map_id
		_full_map_zoom = 1.0
		_full_map_panned = false
	# A continent exterior shows a buffer of its neighbours around it.
	var buffer: float = MapViewScript.NEIGHBOUR_BUFFER_METRES if manifest.data.has("continentGeography") else 0.0
	MapViewScript.configure(full_map_camera, full_map_viewport,
		MapViewScript.bounds_for(manifest, secret_sections.current_section()), buffer)
	# Every map can magnify around the cursor. Only continent exteriors can
	# pull back past their default framing to show neighbouring regions.
	_full_map_base_size = full_map_camera.size
	_full_map_base_position = full_map_camera.global_position
	_full_map_zoomable = buffer > 0.0
	if not _full_map_zoomable:
		_full_map_zoom = minf(_full_map_zoom, 1.0)
	_apply_full_map_zoom()
	_update_map_boundaries()
	if changed_map and _cartography_loaded:
		_show_current_map_view()
	player_map_marker.scale = Vector3(.18,1,.18) if manifest.asset_id() in ["lantern_reach", "bellwatch", "stillglass", "reedway", "cinderbank", "echo_court", "wayfarer_bastion", "lantern_exchange", "waystone_yard"] else Vector3.ONE

## The map window's cartography: the continent picture and the regions on it.
## Both are the client's own tab maps - every exterior region's minimap.webp,
## laid out to scale by eloria-assets/tools/build_continent_map.py - so what a
## region looks like from the continent is what it looks like on arrival, the
## way the legacy map window's continent opened onto each map's own picture.
func _configure_cartography() -> void:
	_service_preview_overlay = ServiceOverlayScript.new()
	region_preview.add_child(_service_preview_overlay)
	_service_preview_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# First of the continent's marks, so the routes run under the other dots.
	_boat_continent_overlay = BoatRouteOverlayScript.new()
	_boat_continent_overlay.name = "BoatRoutes"
	_boat_continent_overlay.z_index = 1
	continent_image.add_child(_boat_continent_overlay)
	_boat_continent_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_service_continent_overlay = ServiceOverlayScript.new()
	_service_continent_overlay.z_index = 1
	continent_image.add_child(_service_continent_overlay)
	_service_continent_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_storage_preview_overlay = StorageOverlayScript.new()
	region_preview.add_child(_storage_preview_overlay)
	_storage_preview_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_storage_continent_overlay = StorageOverlayScript.new()
	_storage_continent_overlay.z_index = 1
	continent_image.add_child(_storage_continent_overlay)
	_storage_continent_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_entrance_preview_overlay = EntranceOverlayScript.new()
	region_preview.add_child(_entrance_preview_overlay)
	_entrance_preview_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_entrance_continent_overlay = EntranceOverlayScript.new()
	_entrance_continent_overlay.z_index = 2
	continent_image.add_child(_entrance_continent_overlay)
	_entrance_continent_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	continent_map = ContinentMapScript.new()
	continent_map.name = "ContinentMap"
	continent_view.add_child(continent_map)
	continent_map.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	continent_map.region_selected.connect(_preview_continent_region)
	continent_map.region_hovered.connect(_hover_continent_region)
	continent_map.gui_input.connect(_on_continent_map_gui_input)
	continent_map.mouse_exited.connect(_set_hovered_dock.bind(-1))
	_configure_continent_overlay(_active_continent_data())

func _active_continent_data() -> Dictionary:
	var index := _region_index_for_map(AppState.current_map)
	if index >= 0 and _cartography_frame(index) == "continent-v2":
		var overview: Dictionary = _v2_cartography.get("overview", {}) as Dictionary
		if not overview.is_empty():
			return overview
	return cartography.get("continent", {}) as Dictionary

func _configure_continent_overlay(continent: Dictionary) -> void:
	var image_size: Array = continent.get("imageSize", []) as Array
	var rects: Array[Dictionary] = []
	_continent_region_indices.clear()
	var frame := str(continent.get("frame", ""))
	if not frame.is_empty():
		for value: Variant in continent.get("regions", []):
			var row: Dictionary = value as Dictionary
			var index := _region_index_for_map(str(row.get("serverMap", "")))
			var rect: Array = row.get("rect", []) as Array
			if index < 0 or _cartography_frame(index) != frame or rect.size() != 4:
				continue
			_continent_region_indices.append(index)
			rects.append({"name": str(row.get("name", "")),
				"rect": Rect2(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])),
				"polygons": row.get("polygons", []), "label": row.get("label", [])})
	else:
		for index: int in range(cartography_regions.size()):
			var region: Dictionary = cartography_regions[index] as Dictionary
			var rect: Array = region.get("continentRect", []) as Array
			if not _cartography_frame(index).is_empty() or rect.size() != 4:
				continue
			_continent_region_indices.append(index)
			rects.append({"name": str(region.get("name", "Unknown region")),
				"rect": Rect2(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])),
				"polygon": region.get("continentPolygon", []), "label": region.get("continentLabel", [])})
	if image_size.size() == 2:
		continent_map.configure(Vector2(float(image_size[0]), float(image_size[1])), rects)
		var origin: Array = continent.get("originMetres", [0, 0]) as Array
		var minimum := Vector2(float(origin[0]), float(origin[1]))
		var pixels := Vector2(float(image_size[0]), float(image_size[1]))
		var marks: Array = []
		var entrances: Array = []
		var services: Array = []
		var marker_pixels: Array[Vector2] = []
		for index: int in _continent_region_indices:
			var region: Dictionary = cartography_regions[index] as Dictionary
			var translation: Array = region.get("globalTranslation", [0, 0, 0]) as Array
			for value: Variant in region.get("serviceMarkers", []):
				var mark: Dictionary = (value as Dictionary).duplicate()
				var at: Array = mark["position"] as Array
				mark["position"] = [float(at[0]) + float(translation[0]), float(at[1]) + float(translation[2])]
				services.append(mark)
				marker_pixels.append((Vector2(float(mark.position[0]), float(mark.position[1])) - minimum)
					/ float(continent.get("metresPerPixel", 1.0)))
			for value: Variant in region.get("storageMarkers", []):
				var mark: Dictionary = (value as Dictionary).duplicate()
				var at: Array = mark["position"] as Array
				mark["position"] = [float(at[0]) + float(translation[0]), float(at[1]) + float(translation[2])]
				marks.append(mark)
				marker_pixels.append((Vector2(float(mark.position[0]), float(mark.position[1])) - minimum)
					/ float(continent.get("metresPerPixel", 1.0)))
			for value: Variant in region.get("entranceMarkers", []):
				var mark: Dictionary = (value as Dictionary).duplicate()
				var at: Array = mark["position"] as Array
				mark["position"] = [float(at[0]) + float(translation[0]), float(at[1]) + float(translation[2])]
				entrances.append(mark)
				marker_pixels.append((Vector2(float(mark.position[0]), float(mark.position[1])) - minimum)
					/ float(continent.get("metresPerPixel", 1.0)))
		# The boat network is written in the picture's own metres.
		var boats: Dictionary = {}
		if not frame.is_empty() and frame == str(_v2_cartography.get("frame", "")):
			boats = _v2_cartography.get("boatNetwork", {}) as Dictionary
		var docks: Array = boats.get("docks", []) as Array
		for value: Variant in docks:
			var at: Array = (value as Dictionary).get("position", [0, 0]) as Array
			marker_pixels.append((Vector2(float(at[0]), float(at[1])) - minimum)
				/ float(continent.get("metresPerPixel", 1.0)))
		continent_map.set_marker_positions(marker_pixels)
		continent_map.set_dock_legend(not docks.is_empty())
		_boat_continent_overlay.configure(minimum,
			minimum + pixels * float(continent.get("metresPerPixel", 1.0)), pixels, docks)
		_boat_continent_overlay.set_routes(boats.get("routes", []) as Array)
		_service_continent_overlay.configure(minimum,
			minimum + pixels * float(continent.get("metresPerPixel", 1.0)), pixels, services)
		_storage_continent_overlay.configure(minimum,
			minimum + pixels * float(continent.get("metresPerPixel", 1.0)), pixels, marks)
		_entrance_continent_overlay.configure(minimum,
			minimum + pixels * float(continent.get("metresPerPixel", 1.0)), pixels, entrances)
		var region_names: Array = []
		for value: Variant in continent.get("regions", []):
			var row: Dictionary = value as Dictionary
			var at: Array = row.get("label", []) as Array
			if at.size() == 2:
				region_names.append({"label":row.get("name", ""), "position":[
					minimum.x+float(at[0])*float(continent.get("metresPerPixel", 1.0)),
					minimum.y+float(at[1])*float(continent.get("metresPerPixel", 1.0))]})
		_entrance_continent_overlay.set_region_names(region_names)

func _preview_continent_region(local_index: int) -> void:
	if local_index >= 0 and local_index < _continent_region_indices.size():
		_preview_region(_continent_region_indices[local_index])

func _hover_continent_region(local_index: int) -> void:
	_on_continent_region_hovered(_continent_region_indices[local_index]
		if local_index >= 0 and local_index < _continent_region_indices.size() else -1)

## The cursor over a boat dock lifts its routes and names its destinations.
## The overlay map takes the input; the boat marks share its picture.
func _on_continent_map_gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseMotion:
		return
	var at: Vector2 = _boat_continent_overlay.get_global_transform().affine_inverse() * (
		continent_map.get_global_transform() * (event as InputEventMouseMotion).position)
	_set_hovered_dock(_boat_continent_overlay.dock_at(at))

func _set_hovered_dock(index: int) -> void:
	if index == _boat_continent_overlay.hovered_dock():
		return
	_boat_continent_overlay.set_hovered_dock(index)
	_hover_continent_region(continent_map.hovered_region())

## Decode only the active group's picture, once per group, when Tab opens.
func _ensure_cartography_textures() -> void:
	var continent := _active_continent_data()
	var frame := str(continent.get("frame", ""))
	if _cartography_loaded and frame == _continent_frame:
		return
	_cartography_loaded = true
	_continent_frame = frame
	_configure_continent_overlay(continent)
	if not _continent_textures.has(frame):
		_continent_textures[frame] = _external_texture(str(continent.get("texture", "")))
	_continent_texture = _continent_textures[frame] as Texture2D
	continent_image.texture = _continent_texture

## A region's tab map: the pixels of its minimap the live Tab map would frame,
## decoded once and kept.
func _tab_map_texture(region: Dictionary) -> Texture2D:
	var key: String = str(region.get("serverMap", ""))
	if _tab_map_textures.has(key):
		return _tab_map_textures[key] as Texture2D
	var tab_map: Dictionary = region.get("tabMap", {}) as Dictionary
	var whole: Texture2D = _external_texture(str(tab_map.get("texture", "")))
	var texture: Texture2D = whole
	var crop: Array = tab_map.get("region", []) as Array
	if whole != null and crop.size() == 4:
		var rect := Rect2(float(crop[0]), float(crop[1]), float(crop[2]), float(crop[3]))
		if rect.position != Vector2.ZERO or rect.size != whole.get_size():
			var atlas := AtlasTexture.new()
			atlas.atlas = whole
			atlas.region = rect
			texture = atlas
	_tab_map_textures[key] = texture
	return texture

func _tab_map_detail_texture(region: Dictionary) -> Texture2D:
	var detail: Dictionary = (region.get("tabMap", {}) as Dictionary).get("detail", {}) as Dictionary
	if detail.is_empty():
		return _tab_map_texture(region)
	var key: String = str(region.get("serverMap", ""))
	if _tab_map_detail_textures.has(key):
		var cached: Texture2D = _tab_map_detail_textures[key]
		_tab_map_detail_textures.erase(key)
		_tab_map_detail_textures[key] = cached
		return cached
	var image := Image.new()
	var error := image.load(ProjectSettings.globalize_path(str(detail.get("texture", ""))))
	if error != OK or image.is_empty():
		return _tab_map_texture(region)
	image.generate_mipmaps()
	var texture := ImageTexture.create_from_image(image)
	while _tab_map_detail_textures.size() >= maxi(2, _map_detail_visible.size() + 1):
		var evicted := false
		for old_key: String in _tab_map_detail_textures.keys():
			if old_key != MapRegistry.normalize_server_map_id(AppState.current_map) and not _map_detail_visible.has(old_key):
				_tab_map_detail_textures.erase(old_key)
				evicted = true
				break
		if not evicted:
			break
	_tab_map_detail_textures[key] = texture
	return texture

## Zooming or panning onto a neighbour should expose its detail too. Sample
## the visible ground's owners, keeping a bounded set of up to five regions.
func _update_map_detail_levels() -> void:
	if _neighbour_pictures.is_empty():
		return
	var wanted := {MapRegistry.normalize_server_map_id(AppState.current_map): true}
	var views: Array[Array] = []
	if full_map.visible and map_image.visible and _full_map_zoom < 1.0:
		views.append([full_map_camera, full_map_viewport.size])
	if minimap_frame.visible:
		views.append([map_camera, map_viewport.size])
	for view: Array in views:
		var camera: Camera3D = view[0]
		for fraction: Vector2 in [Vector2(.5, .5), Vector2(.1, .1), Vector2(.9, .1),
				Vector2(.1, .9), Vector2(.9, .9), Vector2(.5, .1), Vector2(.5, .9),
				Vector2(.1, .5), Vector2(.9, .5)]:
			var owner := _map_owning_point(camera.project_ray_origin(Vector2(view[1]) * fraction))
			if not owner.is_empty() and wanted.size() < 5:
				wanted[owner] = true
	if wanted == _map_detail_visible:
		return
	_map_detail_visible = wanted
	for map_id: String in _neighbour_pictures:
		var picture := _neighbour_pictures[map_id] as MeshInstance3D
		if not is_instance_valid(picture):
			continue
		var region_index := _region_index_for_map(map_id)
		if region_index < 0:
			continue
		var region: Dictionary = cartography_regions[region_index]
		var material := picture.mesh.surface_get_material(0) as StandardMaterial3D
		material.albedo_texture = (_tab_map_detail_texture(region) if wanted.has(map_id)
			else _tab_map_texture(region))
	# Release detailed images when their regions leave both map views.
	for key: String in _tab_map_detail_textures.keys():
		if not wanted.has(key) and key != str((cartography_regions[_preview_region_index] as Dictionary).get("serverMap", "") if _preview_region_index >= 0 else ""):
			_tab_map_detail_textures.erase(key)

## A region's name as the cartography writes it, for a line the player reads.
func _region_name_for_map(server_map: String) -> String:
	var region_index: int = _region_index_for_map(server_map)
	if region_index < 0:
		return server_map
	return str((cartography_regions[region_index] as Dictionary).get("name", server_map))

func _region_index_for_map(server_map: String) -> int:
	var wanted: String = MapRegistry.normalize_server_map_id(server_map)
	if wanted.is_empty():
		return -1
	for region_index: int in range(cartography_regions.size()):
		var region_value: Variant = cartography_regions[region_index]
		if region_value is Dictionary and MapRegistry.normalize_server_map_id(
				str((region_value as Dictionary).get("serverMap", ""))) == wanted:
			return region_index
	return -1

func _continent_name() -> String:
	return str(_active_continent_data().get("name", "Nymara"))

const CONTINENT_HINT := "Click a region to see its map. Your server map will not change."

## The small map in the sidebar shows whichever of the two the big map is not,
## and a click swaps them: the legacy map window's one control.
func _on_continent_button_pressed() -> void:
	if continent_view.visible:
		_show_current_map_view()
	else:
		_show_continent_view()

func _show_current_map_view() -> void:
	_full_map_cursor_inside = false
	map_cursor_coordinates.hide()
	_layout_full_window_views()
	_cancel_full_map_drag()
	_full_map_panned = false
	_update_full_map_focus()
	_ensure_cartography_textures()
	continent_view.hide()
	region_preview.hide()
	_preview_region_index = -1
	map_image.show()
	_sync_map_viewport_activity()
	continent_button.texture_normal = _continent_texture
	continent_button.tooltip_text = "Show the " + _continent_name() + " continent"
	map_title.text = _current_map_display_name.to_upper()
	map_coordinates.text = "Coordinates: —"

func _show_continent_view() -> void:
	map_cursor_coordinates.hide()
	_ensure_cartography_textures()
	map_image.hide()
	region_preview.hide()
	_preview_region_index = -1
	_sync_map_viewport_activity()
	continent_view.show()
	_boat_continent_overlay.set_hovered_dock(-1)
	continent_map.set_current_region(_continent_region_indices.find(_region_index_for_map(AppState.current_map)))
	# The live render keeps its last frame while its viewport idles.
	continent_button.texture_normal = full_map_viewport.get_texture()
	continent_button.tooltip_text = "Return to your current map"
	map_title.text = _continent_name().to_upper() + " CONTINENT"
	map_coordinates.text = CONTINENT_HINT

func _on_continent_region_hovered(region_index: int) -> void:
	if not continent_view.visible:
		return
	# A dock names its boats over the region it stands in.
	var dock_text: String = _boat_continent_overlay.hover_text()
	if not dock_text.is_empty():
		map_coordinates.text = dock_text
		return
	if region_index < 0 or region_index >= cartography_regions.size():
		map_coordinates.text = CONTINENT_HINT
		return
	var region: Dictionary = cartography_regions[region_index] as Dictionary
	map_coordinates.text = "Click to see " + str(region.get("name", "the region"))
	if region_index == _region_index_for_map(AppState.current_map):
		map_coordinates.text += " (where you are)"

## Shows a region's tab map without leaving the map you are on. The map you
## are standing on is the live one, your marker and the server's pins
## included, so asking for it returns to that rather than to a still of it.
func _preview_region(region_index: int) -> void:
	if region_index < 0 or region_index >= cartography_regions.size():
		return
	var region_value: Variant = cartography_regions[region_index]
	if not region_value is Dictionary:
		return
	var region: Dictionary = region_value as Dictionary
	if region_index == _region_index_for_map(AppState.current_map):
		_show_current_map_view()
		return
	var texture: Texture2D = _tab_map_detail_texture(region)
	if texture == null:
		map_coordinates.text = "No map of %s has been drawn yet." % str(
			region.get("name", "that region"))
		return
	_ensure_cartography_textures()
	continent_view.hide()
	map_image.hide()
	_sync_map_viewport_activity()
	region_preview.texture = texture
	var preview_map: Dictionary = region.get("tabMap", {}) as Dictionary
	var low: Array = preview_map.get("worldMin", [0, 0]) as Array
	var high: Array = preview_map.get("worldMax", [1, 1]) as Array
	_service_preview_overlay.configure(Vector2(float(low[0]), float(low[1])),
		Vector2(float(high[0]), float(high[1])), texture.get_size(), region.get("serviceMarkers", []))
	_storage_preview_overlay.configure(Vector2(float(low[0]), float(low[1])),
		Vector2(float(high[0]), float(high[1])), texture.get_size(), region.get("storageMarkers", []))
	_entrance_preview_overlay.configure(Vector2(float(low[0]), float(low[1])),
		Vector2(float(high[0]), float(high[1])), texture.get_size(), region.get("entranceMarkers", []))
	region_preview.show()
	_preview_region_index = region_index
	var entry: Dictionary = MapRegistry.resolve(map_registry, str(region.get("serverMap", "")))
	_preview_adapter = CoordinateAdapter.new(entry.get("coordinateTransform", {}))
	continent_button.texture_normal = _continent_texture
	continent_button.tooltip_text = "Show the " + _continent_name() + " continent"
	map_title.text = str(region.get("name", "REGION")).to_upper()
	map_coordinates.text = "Coordinates: —"

## The server tile under a point on the preview. The image is north-up at a
## known world extent and the map's own transform turns metres into tiles,
## so the sidebar reads the same numbers it would over the live map.
func _preview_tile_at(local_position: Vector2) -> Variant:
	if _preview_region_index < 0 or _preview_region_index >= cartography_regions.size():
		return null
	if region_preview.texture == null or _preview_adapter == null:
		return null
	var tab_map: Dictionary = (cartography_regions[_preview_region_index]
		as Dictionary).get("tabMap", {}) as Dictionary
	var low: Array = tab_map.get("worldMin", []) as Array
	var high: Array = tab_map.get("worldMax", []) as Array
	if low.size() != 2 or high.size() != 2:
		return null
	var texture_size: Vector2 = region_preview.texture.get_size()
	var pixel_value: Variant = _texture_to_viewport_position(
		local_position, region_preview, Vector2i(texture_size))
	if not pixel_value is Vector2:
		return null
	var pixel: Vector2 = pixel_value as Vector2
	var world := Vector3(
		float(low[0]) + pixel.x / texture_size.x * (float(high[0]) - float(low[0])),
		_preview_adapter.walking_height,
		float(low[1]) + pixel.y / texture_size.y * (float(high[1]) - float(low[1])))
	return _preview_adapter.godot_to_server(world)

func _on_region_preview_gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseMotion:
		return
	map_cursor_coordinates.hide()
	var tile_value: Variant = _preview_tile_at((event as InputEventMouseMotion).position)
	if tile_value is Vector2i:
		var tile: Vector2i = tile_value as Vector2i
		map_coordinates.text = "Coordinates: %d, %d" % [tile.x, tile.y]
		_show_map_cursor_coordinates(region_preview, event.position, tile)
		var service_label: String = _service_preview_overlay.label_at((event as InputEventMouseMotion).position)
		if not service_label.is_empty():
			map_coordinates.text += " — " + service_label
		var storage_label: String = _storage_preview_overlay.label_at((event as InputEventMouseMotion).position)
		if not storage_label.is_empty():
			map_coordinates.text += " — " + storage_label
		var entrance_label: String = _entrance_preview_overlay.label_at((event as InputEventMouseMotion).position)
		if not entrance_label.is_empty():
			map_coordinates.text += " — " + entrance_label
	else:
		map_coordinates.text = "Coordinates: outside map image"

func _on_region_preview_mouse_exited() -> void:
	map_cursor_coordinates.hide()
	if region_preview.visible:
		map_coordinates.text = "Coordinates: —"

func _friendly_map_name(server_map: String) -> String:
	# Normalisation already reduces every spelling the server uses - its own
	# file reference included - to the Eloria map id, so this only has to know
	# the ids and the one the city still answers to.
	var normalized: String = MapRegistry.normalize_server_map_id(server_map)
	if normalized in ["four_gates", "four-gates"]:
		return "Four Gates City"
	return normalized.replace("_", " ").replace("-", " ").capitalize()

func _load_hud_settings() -> void:
	var config: ConfigFile = ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		var spell_bar_layout: Variant = config.get_value("hud", "spell_quickbar", {})
		if spell_bar_layout is Dictionary:
			casting_bar.restore_hud_layout(spell_bar_layout)
		# Older clients saved an opt-in TLS switch. Migrate it immediately so
		# returning players use TLS too, even before changing any preferences.
		# Host and port were never saved; the scene now defaults to TLS/2001.
		if config.get_value("connection", "secure", false) != true:
			config.set_value("connection", "secure", true)
			var migration_error := config.save(SETTINGS_PATH)
			if migration_error != OK:
				push_warning("Could not migrate connection settings: " + error_string(migration_error))
		_minimap_scale = clampf(float(config.get_value(
			"hud", "minimap_scale", 1.0)), 0.75, 1.75)
		_ui_scale = clampf(float(config.get_value(
			"hud", "ui_scale", 1.0)), UI_SCALE_MIN, UI_SCALE_MAX)
		_show_through_obstacles = bool(config.get_value(
			"hud", "show_through_obstacles", true))
		_minimap_orientation = str(config.get_value(
			"hud", "minimap_orientation", MINIMAP_DEFAULT_ORIENTATION))
		if _minimap_orientation not in ["north_up", "player_up", "viewport_up"]:
			_minimap_orientation = MINIMAP_DEFAULT_ORIENTATION
		_minimap_zoom = clampf(float(config.get_value(
			"hud", "minimap_zoom", MINIMAP_ZOOM_DEFAULT)),
			MINIMAP_ZOOM_MIN, MINIMAP_ZOOM_MAX)
		_minimap_marker_scale = clampf(float(config.get_value(
			"hud", "minimap_marker_scale", 1.0)),
			MINIMAP_MARKER_SCALES[0], MINIMAP_MARKER_SCALES[-1])
		_minimap_border = clampf(float(config.get_value(
			"hud", "minimap_border", MINIMAP_DEFAULT_BORDER)),
			MINIMAP_BORDER_STEPS[0], MINIMAP_BORDER_STEPS[-1])
		_minimap_shape = str(config.get_value(
			"hud", "minimap_shape", MINIMAP_DEFAULT_SHAPE))
		if _minimap_shape not in ["square", "round"]:
			_minimap_shape = MINIMAP_DEFAULT_SHAPE
		for type: StringName in MINIMAP_MARKER_TYPES:
			_minimap_marker_types[type] = bool(config.get_value(
				"hud", "minimap_marker_%s" % type, true))
		extension_windows.call("set_combat_hud_enabled",
			bool(config.get_value("hud", "combat_hud", true)))
		extension_windows.call("set_combat_hud_pinned",
			bool(config.get_value("hud", "combat_hud_pinned", false)))
		var combat_hud_where: Variant = config.get_value(
			"hud", "combat_hud_position", Vector2.ZERO) if config.has_section_key(
			"hud", "combat_hud_position") else null
		if combat_hud_where is Vector2:
			extension_windows.call("set_combat_hud_position",
				combat_hud_where as Vector2)
		var position_value: Variant = config.get_value(
			"hud", "minimap_position", Vector2(16.0, 42.0))
		if position_value is Vector2:
			minimap_frame.position = position_value as Vector2
		# The minimap's position and scale persisted but its visibility did
		# not, so every session started with the map hidden and nothing but
		# Alt+M would show it again.
		_minimap_visible = bool(config.get_value("hud", "minimap_visible", false))
		for option_key: String in _hud_element_options:
			_hud_element_options[option_key] = bool(config.get_value(
				"hud", option_key, _hud_element_options[option_key]))
		_hud_timer_stopwatch = bool(config.get_value("hud", "timer_stopwatch", false))
		_hud_timer_start_seconds = clampi(int(config.get_value(
			"hud", "timer_start_seconds", 90)), 0, 9 * 60 + 59)
		_hud_timer_seconds = 0 if _hud_timer_stopwatch else _hud_timer_start_seconds
		_ground_bag_scale = clampf(float(config.get_value(
			"ground_bag", "window_scale", 1.0)),
			INVENTORY_MIN_SCALE, INVENTORY_MAX_SCALE)
		_inventory_scale = clampf(float(config.get_value(
			"inventory", "window_scale", 1.0)),
			INVENTORY_MIN_SCALE, INVENTORY_MAX_SCALE)
		var inventory_position_value: Variant = config.get_value(
			"inventory", "window_position", inventory_panel.position)
		if inventory_position_value is Vector2:
			inventory_panel.position = inventory_position_value as Vector2
		_equipment_side = str(config.get_value("inventory", "equipment_side", "left"))
		var bag_position_value: Variant = config.get_value(
			"inventory", "bag_window_position", ground_bag_panel.position)
		if bag_position_value is Vector2:
			ground_bag_panel.position = bag_position_value as Vector2
		var quantities_value: Variant = config.get_value("inventory", "quantities", [])
		if quantities_value is Array 				and (quantities_value as Array).size() == _inventory_quantities.size():
			for index: int in range(_inventory_quantities.size()):
				_inventory_quantities[index] = clampi(
					int((quantities_value as Array)[index]), 1, INVENTORY_QUANTITY_MAX)
		_selected_quantity_box = clampi(int(config.get_value(
			"inventory", "selected_quantity", 0)), 0, _inventory_quantities.size() - 1)
		var bulk_value: Variant = config.get_value("inventory", "bulk_exclusions", {})
		if bulk_value is Dictionary:
			for kind: String in ["store", "drop"]:
				var options_value: Variant = (bulk_value as Dictionary).get(kind)
				if options_value is Array and (options_value as Array).size() == 4:
					_bulk_exclusions[kind] = (options_value as Array).duplicate()
		var lists_value: Variant = config.get_value("inventory", "item_lists", {})
		if lists_value is Dictionary:
			_item_lists = (lists_value as Dictionary).duplicate(true)
		_player_notes = str(config.get_value("notes", "text", ""))
		var stored_bookmarks: Variant = config.get_value(
			"encyclopedia", "bookmarks", [])
		if stored_bookmarks is Array:
			_encyclopedia_bookmarks = (stored_bookmarks as Array).duplicate(true)
		_shadows_enabled = bool(config.get_value("graphics", "shadows", true))
		_effects_enabled = bool(config.get_value("graphics", "particles", true))
		CapeEmblems.set_enabled(bool(config.get_value("graphics", "cape_emblems", true)))
		_nameplates_enabled = bool(
			config.get_value("graphics", "nameplates", true))
		_set_name_distance(config.get_value(
			"graphics", "name_distance", NAME_DISTANCE_DEFAULT_METRES))
		_set_crowd_settings(config.get_value("graphics", "crowd_bodies",
			SettingsWindowScript.CROWD_BODIES_DEFAULT), config.get_value(
			"graphics", "swaying_capes", SettingsWindowScript.SWAYING_CAPES_DEFAULT))
		camera_rig.rotation_sensitivity = float(config.get_value(
			"camera", "rotation_sensitivity", camera_rig.rotation_sensitivity))
		camera_rig.keyboard_speed = float(config.get_value(
			"camera", "keyboard_speed", IsometricCameraController.KEYBOARD_SPEED_DEFAULT))
		# keys.ini holds the bindings now. The settings file's old copy is read
		# only when there is no keys.ini yet, to carry a player's keys over.
		var stored_bindings: Variant = config.get_value("controls", "bindings", {})
		if stored_bindings is Dictionary and not FileAccess.file_exists(KeyBindings.PATH):
			settings_window.call("restore_bindings", stored_bindings)
		var stored_marks: Variant = config.get_value("console", "marks", [])
		if stored_marks is Array:
			for raw_mark: Variant in stored_marks as Array:
				if raw_mark is Dictionary:
					console_commands.marks.append(raw_mark as Dictionary)
		for key_and_list: Array in [["ignored", console_commands.ignored],
				["filters", console_commands.filters]]:
			var stored: Variant = config.get_value("console",
				str(key_and_list[0]), [])
			if stored is Array:
				for entry: Variant in stored as Array:
					(key_and_list[1] as Array[String]).append(str(entry))
		var stored_aliases: Variant = config.get_value("console", "aliases", {})
		if stored_aliases is Dictionary:
			console_commands.aliases = (stored_aliases as Dictionary).duplicate()
		audio_director.enabled = bool(config.get_value("audio", "enabled", true))
		audio_director.volume_linear = clampf(float(config.get_value(
			"audio", "volume", AudioMix.MASTER_DEFAULT)), 0.0, 1.0)
		for category: String in AudioMix.CATEGORIES:
			audio_director.set_category_volume(category, float(config.get_value(
				"audio", category + "_volume", AudioMix.CATEGORIES[category].volume)))
		for banner_key: String in BANNER_OPTION_NODES:
			var box: CheckBox = _banner_option_boxes[banner_key] as CheckBox
			box.set_pressed_no_signal(bool(config.get_value(
				"banner", banner_key, BANNER_OPTION_DEFAULTS[banner_key])))
		for key: String in _mount_banner_options:
			_mount_banner_options[key] = bool(config.get_value("mount_banner", key, true))
	mount_status.set_options(_mount_banner_options)
	_creature_banner_options = CreatureBannerSettings.read(config)
	_target_marker_style = TargetMarkerStyle.read(config)
	_apply_target_marker_style()
	_apply_fps_limit(config.get_value("graphics", "fps_limit", 0))
	_render_scale = GraphicsOptions.render_scale(config.get_value("graphics", "render_scale", 1.0))
	_map_texture_quality = GraphicsOptions.texture_quality(config.get_value("graphics", "map_texture_quality", "full"))
	_renderer_preference = GraphicsLaunchOptions.renderer_name(config.get_value("graphics", "renderer", "auto"))
	GraphicsOptions.decorative_grass = bool(config.get_value("graphics", "decorative_grass", true))
	_apply_render_scale()
	_load_look_settings(config)
	reference_window.call("configure", console_commands,
		settings_window.get("BINDABLE"), _player_notes, _encyclopedia_bookmarks)
	sound_enabled.set_pressed_no_signal(bool(audio_director.enabled))
	sound_volume.set_value_no_signal(float(audio_director.volume_linear))
	sound_volume_value.text = "%d%%" % roundi(
		float(audio_director.volume_linear) * 100.0)
	for category: String in audio_director.category_volumes:
		settings_window.restore_value("audio_" + category,
			audio_director.category_volumes[category])
	minimap_size.set_value_no_signal(_minimap_scale)
	ui_scale_slider.set_value_no_signal(_ui_scale)
	show_through_obstacles.set_pressed_no_signal(_show_through_obstacles)
	settings_window.call("restore_toggle", "combat_hud",
		bool(extension_windows.get("combat_hud_enabled")))
	settings_window.call("restore_name_distance", _name_distance_metres)
	settings_window.call("restore_crowd_settings", _crowd_bodies, _swaying_capes)
	settings_window.call("restore_toggle", "cape_emblems", CapeEmblems.enabled)
	for option_key: String in _hud_element_options:
		settings_window.call("restore_toggle", option_key,
			bool(_hud_element_options[option_key]))
	_apply_ui_scale()
	_apply_minimap_scale()
	_apply_minimap_zoom()
	_apply_inventory_scale(_inventory_scale)
	_apply_ground_bag_scale(_ground_bag_scale)
	_apply_banner_options()
	settings_window.call("load_keys_file")
	_refresh_unified_settings()

func _on_ui_scale_changed(value: float) -> void:
	_ui_scale = clampf(value, UI_SCALE_MIN, UI_SCALE_MAX)
	_apply_ui_scale()
	_save_hud_settings()

## The window already scales the HUD with its size; this factor rides on top of
## that so players can trade HUD size for screen space. It only moves the canvas
## the HUD is laid out in - the world render target is resized to match in
## _on_window_size_changed(), so the world always renders at window resolution.
func _on_show_through_obstacles_toggled(pressed: bool) -> void:
	_show_through_obstacles = pressed
	_apply_show_through_obstacles()
	_save_hud_settings()

func _toggle_show_through_obstacles() -> void:
	show_through_obstacles.button_pressed = not show_through_obstacles.button_pressed

## The local player's sight line only. Fading every obstacle in front of every
## actor would strip the map bare and would be a wallhack rather than a
## convenience, so the probe is deliberately never aimed at the rest of
## `actor_nodes`.
func _apply_show_through_obstacles() -> void:
	occluder_fade.set_enabled(_show_through_obstacles)

func _apply_ui_scale() -> void:
	var window: Window = get_window()
	if window != null:
		window.content_scale_factor = _ui_scale
	ui_scale_value.text = "%d%%" % roundi(_ui_scale * 100.0)
	_on_window_size_changed()

func _on_minimap_size_changed(value: float) -> void:
	_minimap_scale = clampf(value, 0.75, 1.75)
	_apply_minimap_scale()
	_save_hud_settings()

## Sound is the player's own choice about their own machine, so it is kept in
## the same settings file as the rest of the HUD preferences.
func _on_sound_enabled_toggled(pressed: bool) -> void:
	audio_director.enabled = pressed
	if is_instance_valid(map_ambience_root):
		# Ambience is a scene node rather than a voice on the director, so it
		# has to be silenced here as well.
		map_ambience_root.queue_free()
		map_ambience_root = null
	if pressed:
		audio_director.play("ui_click")
		if world_loader.manifest != null:
			_bind_ambient_audio(world_loader.manifest)
	_save_hud_settings()

func _on_sound_volume_changed(value: float) -> void:
	audio_director.volume_linear = value
	sound_volume_value.text = "%d%%" % roundi(value * 100.0)
	_save_hud_settings()

func _save_hud_settings() -> void:
	var config: ConfigFile = ConfigFile.new()
	config.load(SETTINGS_PATH)
	config.set_value("notes", "text", _player_notes)
	# A developer's plain TCP session must never become a saved player default.
	config.set_value("connection", "secure", true)
	config.set_value("encyclopedia", "bookmarks", _encyclopedia_bookmarks)
	config.set_value("graphics", "shadows", _shadows_enabled)
	config.set_value("graphics", "particles", _effects_enabled)
	config.set_value("graphics", "cape_emblems", CapeEmblems.enabled)
	config.set_value("graphics", "nameplates", _nameplates_enabled)
	config.set_value("graphics", "name_distance", _name_distance_metres)
	config.set_value("graphics", "crowd_bodies", _crowd_bodies)
	config.set_value("graphics", "swaying_capes", _swaying_capes)
	config.set_value("graphics", "fps_limit", _fps_limit)
	config.set_value("graphics", "render_scale", _render_scale)
	config.set_value("graphics", "map_texture_quality", _map_texture_quality)
	config.set_value("graphics", "renderer", _renderer_preference)
	config.set_value("graphics", "decorative_grass", GraphicsOptions.decorative_grass)
	TargetMarkerStyle.write(config, _target_marker_style)
	# The player's own choices, not what ELORIA_LOOK or ELORIA_LOOK_QUALITY
	# made of them for this session.
	config.set_value("graphics", "appearance", LookProfile.mode_name(LookProfile.player_mode()))
	if config.has_section_key("graphics", "look"):
		config.erase_section_key("graphics", "look")
	config.set_value("graphics", "quality", LookProfile.quality_name(LookProfile.player_quality()))
	config.set_value("hud", "combat_hud",
		bool(extension_windows.get("combat_hud_enabled")))
	config.set_value("hud", "combat_hud_pinned",
		bool(extension_windows.get("combat_hud_pinned")))
	config.set_value("hud", "combat_hud_position",
		extension_windows.call("combat_hud_position"))
	config.set_value("hud", "spell_quickbar", casting_bar.hud_layout())
	config.set_value("camera", "rotation_sensitivity",
		float(camera_rig.rotation_sensitivity))
	config.set_value("camera", "keyboard_speed", camera_rig.keyboard_speed)
	config.set_value("console", "marks", console_commands.marks)
	config.set_value("console", "ignored", console_commands.ignored)
	config.set_value("console", "filters", console_commands.filters)
	config.set_value("console", "aliases", console_commands.aliases)
	config.set_value("audio", "enabled", bool(audio_director.enabled))
	config.set_value("audio", "volume", float(audio_director.volume_linear))
	for category: String in audio_director.category_volumes:
		config.set_value("audio", category + "_volume",
			float(audio_director.category_volumes[category]))
	config.set_value("hud", "minimap_scale", _minimap_scale)
	config.set_value("hud", "ui_scale", _ui_scale)
	config.set_value("hud", "show_through_obstacles", _show_through_obstacles)
	config.set_value("hud", "minimap_orientation", _minimap_orientation)
	config.set_value("hud", "minimap_zoom", _minimap_zoom)
	config.set_value("hud", "minimap_position", minimap_frame.position)
	config.set_value("hud", "minimap_visible", _minimap_visible)
	config.set_value("hud", "minimap_marker_scale", _minimap_marker_scale)
	config.set_value("hud", "minimap_border", _minimap_border)
	config.set_value("hud", "minimap_shape", _minimap_shape)
	for type: StringName in MINIMAP_MARKER_TYPES:
		config.set_value("hud", "minimap_marker_%s" % type,
			bool(_minimap_marker_types.get(type, true)))
	for option_key: String in _hud_element_options:
		config.set_value("hud", option_key, bool(_hud_element_options[option_key]))
	config.set_value("hud", "timer_stopwatch", _hud_timer_stopwatch)
	config.set_value("hud", "timer_start_seconds", _hud_timer_start_seconds)
	config.set_value("inventory", "window_scale", _inventory_scale)
	config.set_value("ground_bag", "window_scale", _ground_bag_scale)
	config.set_value("inventory", "window_position",
		classic_storage.standalone_inventory_position() if classic_storage != null else inventory_panel.position)
	config.set_value("inventory", "equipment_side", _equipment_side)
	config.set_value("inventory", "bag_window_position", ground_bag_panel.position)
	config.set_value("inventory", "quantities", _inventory_quantities)
	config.set_value("inventory", "selected_quantity", _selected_quantity_box)
	config.set_value("inventory", "bulk_exclusions", _bulk_exclusions)
	config.set_value("inventory", "item_lists", _item_lists)
	for banner_key: String in BANNER_OPTION_NODES:
		config.set_value("banner", banner_key, _banner_option(banner_key))
	for key: String in _mount_banner_options:
		config.set_value("mount_banner", key, _mount_banner_options[key])
	CreatureBannerSettings.write(config, _creature_banner_options)
	var error: Error = config.save(SETTINGS_PATH)
	if error != OK:
		push_warning("HUD settings save failed: " + error_string(error))
	if hud_workspace != null:
		hud_workspace.sync_settings()
	if settings_window.is_open():
		_refresh_unified_settings()

func _apply_minimap_scale() -> void:
	var frame_size: float = roundf(264.0 * _minimap_scale)
	var border_size: float = roundf(_minimap_border * _minimap_scale)
	minimap_frame.offset_right = minimap_frame.offset_left + frame_size
	minimap_frame.offset_bottom = minimap_frame.offset_top + frame_size
	minimap.offset_left = border_size
	minimap.offset_top = border_size
	minimap.offset_right = -border_size
	minimap.offset_bottom = -border_size
	minimap.custom_minimum_size = Vector2.ZERO
	var maximum: Vector2 = (game_view.size - Vector2(WindowDrag.RESERVED_RIGHT_RAIL,
		WindowDrag.RESERVED_BOTTOM_BAR) - Vector2.ONE * frame_size).max(Vector2.ZERO)
	minimap_frame.position = Vector2(
		clampf(minimap_frame.position.x, 0.0, maximum.x),
		clampf(minimap_frame.position.y, 30.0, maxf(30.0, maximum.y)))
	minimap_size_value.text = "%d%%" % roundi(_minimap_scale * 100.0)
	# The round mask is cut to the frame, so a resize re-cuts it.
	_apply_minimap_shape()
	_layout_minimap_cardinals()

func _on_inventory_header_gui_input(event: InputEvent) -> void:
	if classic_storage != null and classic_storage.is_inventory_docked():
		classic_storage.drag_docked_header(event)
		return
	if event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return
		_inventory_dragging = mouse.pressed
		if mouse.pressed:
			inventory_panel.move_to_front()
			_inventory_drag_offset = (get_viewport().get_mouse_position()
				- inventory_panel.global_position)
		else:
			_save_hud_settings()
		inventory_header.accept_event()
	elif event is InputEventMouseMotion and _inventory_dragging:
		inventory_panel.global_position = (get_viewport().get_mouse_position()
			- _inventory_drag_offset)
		_clamp_inventory_window_to_viewport()
		inventory_header.accept_event()

func _on_ground_bag_header_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return
		_ground_bag_dragging = mouse.pressed
		if mouse.pressed:
			ground_bag_panel.move_to_front()
			_ground_bag_drag_offset = (get_viewport().get_mouse_position()
				- ground_bag_panel.global_position)
		else:
			_save_hud_settings()
		ground_bag_header.accept_event()
	elif event is InputEventMouseMotion and _ground_bag_dragging:
		ground_bag_panel.global_position = (get_viewport().get_mouse_position()
			- _ground_bag_drag_offset)
		_clamp_ground_bag_window_to_viewport()
		ground_bag_header.accept_event()

func _clamp_ground_bag_window_to_viewport() -> void:
	if game_view.size.x <= 0.0 or game_view.size.y <= 0.0:
		return
	var game_origin: Vector2 = game_view.global_position
	var local_position: Vector2 = ground_bag_panel.global_position - game_origin
	var maximum: Vector2 = (game_view.size
		- ground_bag_panel.size * _ground_bag_scale
		- Vector2(8.0, 8.0)).max(Vector2(8.0, 8.0))
	ground_bag_panel.global_position = game_origin + Vector2(
		clampf(local_position.x, 8.0, maximum.x),
		clampf(local_position.y, 8.0, maximum.y))

func _on_inventory_resize_grip_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return
		_inventory_resizing = mouse.pressed
		if mouse.pressed:
			inventory_panel.move_to_front()
			_inventory_resize_start_mouse = get_viewport().get_mouse_position()
			_inventory_resize_start_scale = _inventory_scale
		else:
			_save_hud_settings()
		inventory_resize_grip.accept_event()
	elif event is InputEventMouseMotion and _inventory_resizing:
		var delta: Vector2 = (get_viewport().get_mouse_position()
			- _inventory_resize_start_mouse)
		var base_size: Vector2 = inventory_panel.size
		if base_size.x <= 0.0 or base_size.y <= 0.0:
			return
		var normalized := Vector2(delta.x / base_size.x, delta.y / base_size.y)
		var scale_delta: float = (normalized.x if absf(normalized.x) >= absf(normalized.y)
			else normalized.y)
		_apply_inventory_scale(_inventory_resize_start_scale + scale_delta)
		inventory_resize_grip.accept_event()

func _on_ground_bag_resize_grip_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index != MOUSE_BUTTON_LEFT:
			return
		_ground_bag_resizing = mouse.pressed
		if mouse.pressed:
			ground_bag_panel.move_to_front()
			_ground_bag_resize_start_mouse = get_viewport().get_mouse_position()
			_ground_bag_resize_start_scale = _ground_bag_scale
		else:
			_save_hud_settings()
		ground_bag_resize_grip.accept_event()
	elif event is InputEventMouseMotion and _ground_bag_resizing:
		var delta: Vector2 = (get_viewport().get_mouse_position()
			- _ground_bag_resize_start_mouse)
		var base_size: Vector2 = ground_bag_panel.size
		if base_size.x <= 0.0 or base_size.y <= 0.0:
			return
		var normalized := Vector2(delta.x / base_size.x, delta.y / base_size.y)
		var scale_delta: float = (normalized.x if absf(normalized.x) >= absf(normalized.y)
			else normalized.y)
		_apply_ground_bag_scale(_ground_bag_resize_start_scale + scale_delta)
		ground_bag_resize_grip.accept_event()

func _apply_ground_bag_scale(requested_scale: float) -> void:
	var maximum_scale: float = INVENTORY_MAX_SCALE
	if game_view.size.x > 0.0 and game_view.size.y > 0.0 \
			and ground_bag_panel.size.x > 0.0 and ground_bag_panel.size.y > 0.0:
		maximum_scale = minf(maximum_scale, minf(
			(game_view.size.x - 16.0) / ground_bag_panel.size.x,
			(game_view.size.y - 16.0) / ground_bag_panel.size.y))
	maximum_scale = maxf(INVENTORY_MIN_SCALE, maximum_scale)
	_ground_bag_scale = clampf(requested_scale, INVENTORY_MIN_SCALE, maximum_scale)
	ground_bag_panel.scale = Vector2.ONE * _ground_bag_scale
	_clamp_ground_bag_window_to_viewport()

func _apply_inventory_scale(requested_scale: float) -> void:
	var maximum_scale: float = INVENTORY_MAX_SCALE
	if game_view.size.x > 0.0 and game_view.size.y > 0.0 \
			and inventory_panel.size.x > 0.0 and inventory_panel.size.y > 0.0:
		maximum_scale = minf(maximum_scale, minf(
			(game_view.size.x - 16.0) / inventory_panel.size.x,
			(game_view.size.y - 16.0) / inventory_panel.size.y))
	maximum_scale = maxf(INVENTORY_MIN_SCALE, maximum_scale)
	_inventory_scale = clampf(requested_scale, INVENTORY_MIN_SCALE, maximum_scale)
	inventory_panel.scale = Vector2.ONE * _inventory_scale
	_clamp_inventory_window_to_viewport()

func _clamp_inventory_window_to_viewport() -> void:
	if classic_storage != null and classic_storage.is_inventory_docked():
		classic_storage.layout_dock()
		return
	if game_view.size.x <= 0.0 or game_view.size.y <= 0.0:
		return
	var visible_size: Vector2 = inventory_panel.size * _inventory_scale
	var game_origin: Vector2 = game_view.global_position
	var local_position: Vector2 = inventory_panel.global_position - game_origin
	# The right margin keeps the window off the fixed resource rail, which
	# nothing may cover; every script-built window already respects the same
	# reserve.
	var maximum: Vector2 = (game_view.size - visible_size
		- Vector2(RESERVED_RIGHT_RAIL_MARGIN, WindowDrag.RESERVED_BOTTOM_BAR + 8.0)).max(Vector2(8.0, 8.0))
	local_position = Vector2(
		clampf(local_position.x, 8.0, maximum.x),
		clampf(local_position.y, 8.0, maximum.y))
	inventory_panel.global_position = game_origin + local_position

func _on_equipment_side_selected(index: int) -> void:
	_equipment_side = "right" if index == 1 else "left"
	_apply_equipment_side()
	_save_hud_settings()

func _apply_equipment_side() -> void:
	if equipment_column == null or inventory_body == null:
		return
	inventory_body.move_child(equipment_column,
		inventory_body.get_child_count() - 1 if _equipment_side == "right" else 0)

## The minimap's right-click menu. It began as three orientation radio items at
## the top level, which is all there was to choose; the marker work added
## enough choices that a flat list would have been twenty items deep and the
## orientation would have been three of them. Each group is a submenu of its
## own instead - Orientation, Marker types, Visualization - so the menu opens
## as three words and the player descends into the one they came for.
func _configure_minimap_menu() -> void:
	_minimap_menu = PopupMenu.new()
	_minimap_orientation_menu = _build_minimap_submenu("Orientation",
		["North always up", "Rotate with player", "Rotate with viewport"],
		_on_minimap_orientation_selected)
	_minimap_menu.add_child(_minimap_orientation_menu)
	_minimap_menu.add_submenu_node_item("Orientation", _minimap_orientation_menu)

	# The marker types are check items rather than radios: they are nine
	# independent switches, and a player hiding creature dots is not thereby
	# choosing to see anything else.
	_minimap_marker_type_menu = PopupMenu.new()
	_minimap_marker_type_menu.name = "MarkerTypes"
	_minimap_marker_type_menu.hide_on_checkable_item_selection = false
	for index: int in range(MINIMAP_MARKER_TYPES.size()):
		_minimap_marker_type_menu.add_check_item(
			str(MINIMAP_MARKER_TYPE_LABELS[MINIMAP_MARKER_TYPES[index]]), index)
	_minimap_marker_type_menu.id_pressed.connect(_on_minimap_marker_type_toggled)
	_minimap_menu.add_child(_minimap_marker_type_menu)
	_minimap_menu.add_submenu_node_item("Marker types", _minimap_marker_type_menu)

	_minimap_visualization_menu = PopupMenu.new()
	_minimap_visualization_menu.name = "Visualization"
	_minimap_marker_size_menu = _build_minimap_submenu("MarkerSize",
		MINIMAP_MARKER_SCALE_LABELS, _on_minimap_marker_scale_selected)
	_minimap_shape_menu = _build_minimap_submenu("Shape", ["Square", "Round"],
		_on_minimap_shape_selected)
	var size_labels: Array[String] = []
	for step: float in MINIMAP_SIZE_STEPS:
		size_labels.append("%d%%" % roundi(step * 100.0))
	_minimap_window_size_menu = _build_minimap_submenu("WindowSize", size_labels,
		_on_minimap_size_step_selected)
	_minimap_border_menu = _build_minimap_submenu("Border", MINIMAP_BORDER_LABELS,
		_on_minimap_border_selected)
	for submenu: PopupMenu in [_minimap_marker_size_menu, _minimap_shape_menu,
			_minimap_window_size_menu, _minimap_border_menu]:
		_minimap_visualization_menu.add_child(submenu)
	_minimap_visualization_menu.add_submenu_node_item("Marker size",
		_minimap_marker_size_menu)
	_minimap_visualization_menu.add_submenu_node_item("Minimap shape",
		_minimap_shape_menu)
	_minimap_visualization_menu.add_submenu_node_item("Minimap size",
		_minimap_window_size_menu)
	_minimap_visualization_menu.add_submenu_node_item("Border width",
		_minimap_border_menu)
	_minimap_menu.add_child(_minimap_visualization_menu)
	_minimap_menu.add_submenu_node_item("Visualization", _minimap_visualization_menu)

	minimap_frame.add_child(_minimap_menu)
	_sync_minimap_menu()

## One submenu of radio items, ids running from zero in the order given.
func _build_minimap_submenu(submenu_name: String, labels: Array,
		handler: Callable) -> PopupMenu:
	var submenu := PopupMenu.new()
	submenu.name = submenu_name
	for index: int in range(labels.size()):
		submenu.add_radio_check_item(str(labels[index]), index)
	submenu.id_pressed.connect(handler)
	return submenu

func _sync_minimap_menu() -> void:
	if _minimap_menu == null:
		return
	var orientations: Array[String] = ["north_up", "player_up", "viewport_up"]
	for index: int in range(orientations.size()):
		_minimap_orientation_menu.set_item_checked(index,
			_minimap_orientation == orientations[index])
	for index: int in range(MINIMAP_MARKER_TYPES.size()):
		_minimap_marker_type_menu.set_item_checked(index,
			bool(_minimap_marker_types.get(MINIMAP_MARKER_TYPES[index], true)))
	_check_one_of(_minimap_marker_size_menu,
		_nearest_step(MINIMAP_MARKER_SCALES, _minimap_marker_scale))
	_check_one_of(_minimap_shape_menu, 1 if _minimap_shape == "round" else 0)
	_check_one_of(_minimap_window_size_menu,
		_nearest_step(MINIMAP_SIZE_STEPS, _minimap_scale))
	_check_one_of(_minimap_border_menu,
		_nearest_step(MINIMAP_BORDER_STEPS, _minimap_border))

func _check_one_of(menu: PopupMenu, chosen: int) -> void:
	for index: int in range(menu.item_count):
		menu.set_item_checked(index, index == chosen)

## Which step a stored value sits on. The settings window's slider moves the
## minimap size continuously, so a value between two steps is real and has to
## tick the step it is nearest rather than none of them.
static func _nearest_step(steps: Array[float], value: float) -> int:
	var chosen := 0
	for index: int in range(steps.size()):
		if absf(steps[index] - value) < absf(steps[chosen] - value):
			chosen = index
	return chosen

static func _default_minimap_marker_types() -> Dictionary:
	var defaults: Dictionary = {}
	for type: StringName in MINIMAP_MARKER_TYPES:
		defaults[type] = true
	return defaults

func _on_minimap_orientation_selected(id: int) -> void:
	match id:
		1: _minimap_orientation = "player_up"
		2: _minimap_orientation = "viewport_up"
		_: _minimap_orientation = "north_up"
	_sync_minimap_menu()
	_save_hud_settings()

func _on_minimap_marker_type_toggled(id: int) -> void:
	if id < 0 or id >= MINIMAP_MARKER_TYPES.size():
		return
	var type: StringName = MINIMAP_MARKER_TYPES[id]
	_minimap_marker_types[type] = not bool(_minimap_marker_types.get(type, true))
	_apply_minimap_marker_settings()
	_sync_minimap_menu()
	_save_hud_settings()

func _on_minimap_marker_scale_selected(id: int) -> void:
	_minimap_marker_scale = MINIMAP_MARKER_SCALES[clampi(
		id, 0, MINIMAP_MARKER_SCALES.size() - 1)]
	_apply_minimap_marker_settings()
	_sync_minimap_menu()
	_save_hud_settings()

func _on_minimap_shape_selected(id: int) -> void:
	_minimap_shape = "round" if id == 1 else "square"
	if hud_workspace != null and hud_workspace.manages_layout():
		hud_workspace.change_part("minimap", "map_shape", _minimap_shape)
	_apply_minimap_shape()
	_sync_minimap_menu()
	_save_hud_settings()

## The same setting the settings window's slider moves, so the slider is moved
## with it: two controls over one value that disagree are two bugs waiting.
func _on_minimap_size_step_selected(id: int) -> void:
	_minimap_scale = MINIMAP_SIZE_STEPS[clampi(
		id, 0, MINIMAP_SIZE_STEPS.size() - 1)]
	minimap_size.set_value_no_signal(_minimap_scale)
	_apply_minimap_scale()
	_sync_minimap_menu()
	_save_hud_settings()

func _on_minimap_border_selected(id: int) -> void:
	_minimap_border = MINIMAP_BORDER_STEPS[clampi(
		id, 0, MINIMAP_BORDER_STEPS.size() - 1)]
	_apply_minimap_scale()
	_sync_minimap_menu()
	_save_hud_settings()

func _apply_minimap_marker_settings() -> void:
	if minimap_marker_overlay == null:
		return
	minimap_marker_overlay.set_enabled_types(_minimap_marker_types)
	minimap_marker_overlay.set_marker_scale(_minimap_marker_scale)
	minimap_marker_overlay.set_round(_minimap_shape == "round")

## Rounds the minimap off, or squares it up again. The render is masked in a
## shader rather than by a texture, so the mask follows the frame at every size
## the player can set; the frame's own corners are rounded to match, and the
## marker overlay masks itself the same way so a mark cannot be drawn on the
## border the map no longer reaches.
func _apply_minimap_shape() -> void:
	var is_round: bool = _minimap_shape == "round"
	if _minimap_mask_material == null:
		var shader := Shader.new()
		shader.code = MINIMAP_MASK_SHADER
		_minimap_mask_material = ShaderMaterial.new()
		_minimap_mask_material.shader = shader
	_minimap_mask_material.set_shader_parameter("rounded", is_round)
	minimap.material = _minimap_mask_material
	if _minimap_panel_style != null:
		var radius: int = (roundi(minimap_frame.size.x * 0.5) if is_round else 1)
		_minimap_panel_style.corner_radius_top_left = radius
		_minimap_panel_style.corner_radius_top_right = radius
		_minimap_panel_style.corner_radius_bottom_left = radius
		_minimap_panel_style.corner_radius_bottom_right = radius
	_apply_minimap_marker_settings()

## Everything the minimap marks, as world positions the overlay can project.
##
## The positions are read off the nodes rather than out of AppState, because a
## node stands where the world is drawing it this frame and the packet names a
## tile the actor may already be walking off. A mark whose type the player
## switched off is still gathered here and dropped by the overlay, so the
## switch is read in one place rather than in five.
func _collect_minimap_marks() -> Array[Dictionary]:
	var marks: Array[Dictionary] = []
	var service_names := {}
	for service: Dictionary in _current_service_records():
		service_names[str(service.get("name", "")).to_lower()] = true
	var entrance_ids := _current_entrance_ids()
	var border_labels := _current_border_exit_labels()
	if player_map_marker != null and player_map_marker.visible:
		marks.append({"position": player_map_marker.global_position,
			"type": &"self", "colour": Color.WHITE,
			"radius": MinimapMarkerOverlayScript.SELF_RADIUS})
	for raw_id: Variant in actor_nodes:
		var actor_id: int = int(raw_id)
		# The local player already has the white mark above; a second dot
		# under it says nothing and is never the one being looked for.
		if actor_id == AppState.local_actor_id:
			continue
		# Validity before the cast: `as` on a freed node raises and aborts the
		# whole collection, and an actor can be freed with its entry still here.
		var actor_value: Variant = actor_nodes[raw_id]
		if not is_instance_valid(actor_value):
			continue
		var actor: ReplicatedActor3D = actor_value as ReplicatedActor3D
		if actor == null or not actor.is_visible_in_tree():
			continue
		var dto: Dictionary = AppState.actors.get(actor_id, {}) as Dictionary
		if int(dto.get("kind", 0)) == ReplicatedActor3D.CREATURE_ACTOR_KIND \
				and (int(dto.get("health", 1)) <= 0 or not bool(dto.get("alive", true))):
			continue
		if int(dto.get("kind", 0)) == 2 and service_names.has(str(dto.get("name", "")).to_lower()):
			continue
		marks.append({"position": actor.global_position,
			"type": _minimap_actor_type(dto),
			"colour": ReplicatedActor3D.map_dot_colour(dto)})
	for raw_object: Variant in map_object_nodes.values():
		if not is_instance_valid(raw_object):
			continue
		var map_object: MapObject3D = raw_object as MapObject3D
		if map_object == null or not map_object.is_visible_in_tree():
			continue
		if entrance_ids.has(map_object.object_id):
			continue
		if map_object.is_exit() and border_labels.has(map_object.destination().to_lower()):
			continue
		# A grouped harvest node is marked by its grouping, once.
		if map_object.grouped:
			continue
		var mark: Dictionary = {"position": map_object.global_position,
			"type": _minimap_object_type(map_object),
			"colour": map_object.map_dot_colour()}
		# A waygate and a way off the map are letters, as the legend has them.
		var glyph: String = map_object.map_glyph()
		if not glyph.is_empty():
			mark["glyph"] = glyph
		marks.append(mark)
	for raw_marker: Variant in map_marker_nodes.values():
		if not is_instance_valid(raw_marker):
			continue
		var marker: MapMarker3D = raw_marker as MapMarker3D
		if marker == null or not marker.is_visible_in_tree():
			continue
		marks.append({"position": marker.global_position, "type": &"marker",
			"colour": MapMarker3D.MARKER_COLOUR,
			"radius": MinimapMarkerOverlayScript.PIN_RADIUS})
	marks.append_array(_current_entrance_marks())
	marks.append_array(_current_service_marks())
	marks.append_array(_harvest_grouping_marks())
	marks.append_array(quest_trail.map_marks())
	marks.append_array(_presence_marks())
	return marks

## Players beyond the area of interest, from the server's once-a-second
## presence rows (presence_state.gd): a player's mark without a body under it.
## Players with a body are skipped there; they have their own mark above.
##
## Presence dots are all beyond the area of interest, so while only the
## minimap is open most of them are off it: those beyond the corner of its view
## are skipped before any mark is made. The marks themselves are kept and
## moved rather than made afresh for every refresh.
func _presence_marks() -> Array[Dictionary]:
	var marks: Array[Dictionary] = []
	if AppState.presence.dot_count() == 0:
		return marks
	var centre := Vector2.ZERO
	var reach := INF
	var own: Dictionary = AppState.actors.get(AppState.local_actor_id, {}) as Dictionary
	if not full_map.visible and not own.is_empty():
		centre = Vector2(float(own.get("x", 0)), float(own.get("y", 0)))
		# Half the view's height to a corner is 0.71 of it; the rest is margin.
		reach = map_camera.size * 0.75 / maxf(adapter.metres_per_tile, 0.01)
	AppState.presence.tiles(Time.get_ticks_msec(), AppState.actors, _presence_tiles,
		centre, reach)
	while _presence_mark_pool.size() < _presence_tiles.size():
		_presence_mark_pool.append({"position": Vector3.ZERO, "type": &"player",
			"colour": ReplicatedActor3D.MAP_DOT_COLOUR, "radius": PRESENCE_DOT_RADIUS})
	# The adapter is affine, so one tile's centre and its two steps place
	# every dot without a call per dot.
	var origin: Vector3 = adapter.server_to_godot(0.5, 0.5)
	var step_x: Vector3 = adapter.server_to_godot(1.5, 0.5) - origin
	var step_y: Vector3 = adapter.server_to_godot(0.5, 1.5) - origin
	for index: int in range(_presence_tiles.size()):
		var tile: Vector2 = _presence_tiles[index]
		var mark: Dictionary = _presence_mark_pool[index]
		mark["position"] = origin + step_x * tile.x + step_y * tile.y
		marks.append(mark)
	return marks

func _current_service_records() -> Array:
	var index := _region_index_for_map(AppState.current_map)
	if index < 0:
		return []
	return (cartography_regions[index] as Dictionary).get("serviceMarkers", []) as Array

func _current_service_marks() -> Array[Dictionary]:
	var marks: Array[Dictionary] = []
	for value: Variant in _current_service_records():
		var record: Dictionary = value as Dictionary
		var at: Array = record.get("position", []) as Array
		if at.size() == 2:
			marks.append({"position": Vector3(float(at[0]), float(record.get("height", 0.0)), float(at[1])),
				"type": &"npc", "colour": ServiceOverlayScript.dot_colour(record),
				"glyph": "", "label": str(record.get("label", "Shop"))})
	return marks

## A whole walking border has no single exit point to mark. View-only links
## can join coastlines served by ferries, so those keep their discrete exits.
func _current_border_exit_labels() -> Dictionary:
	var labels := {}
	if exterior_stream == null:
		return labels
	var current := MapRegistry.normalize_server_map_id(AppState.current_map)
	for link: Dictionary in exterior_stream.links:
		if not bool(link.get("seamless", false)) or bool(link.get("visualOnly", false)):
			continue
		var ends: Array = link.ends
		for index: int in 2:
			if str(ends[index].map) != current:
				continue
			var destination := str(ends[1 - index].map)
			var entry: Dictionary = map_registry.get(destination, {})
			var label := str(entry.get("label", destination.replace("_", " ").capitalize()))
			labels[label.to_lower()] = true
	return labels

func _current_entrance_records() -> Array:
	var index := _region_index_for_map(AppState.current_map)
	if index < 0:
		return []
	return (cartography_regions[index] as Dictionary).get("entranceMarkers", []) as Array

func _current_entrance_ids() -> Dictionary:
	var result := {}
	for value: Variant in _current_entrance_records():
		result[int((value as Dictionary).get("objectId", -1))] = true
	return result

func _current_entrance_marks() -> Array[Dictionary]:
	var marks: Array[Dictionary] = []
	for value: Variant in _current_entrance_records():
		var record: Dictionary = value as Dictionary
		var at: Array = record.get("position", []) as Array
		if at.size() == 2:
			marks.append({"position": Vector3(float(at[0]), float(record.get("height", 0.0)), float(at[1])),
				"type": &"entrance", "colour": EntranceOverlayScript.DOT_COLOUR,
				"glyph": "", "label": str(record.get("label", "Entrance"))})
	return marks

## Which switch a world object's mark answers to.
static func _minimap_object_type(map_object: MapObject3D) -> StringName:
	if map_object.is_exit():
		return &"exit"
	if map_object.is_portal():
		return &"portal"
	return &"harvest" if map_object.is_harvestable() else &"interactive"

## Waygates and exits use glyphs on the full map, with names on hover.
func _collect_map_waypoints() -> Array[Dictionary]:
	var waypoints: Array[Dictionary] = []
	var entrance_ids := _current_entrance_ids()
	var border_labels := _current_border_exit_labels()
	for raw_object: Variant in map_object_nodes.values():
		if not is_instance_valid(raw_object):
			continue
		var map_object: MapObject3D = raw_object as MapObject3D
		if map_object == null or not map_object.is_visible_in_tree():
			continue
		if entrance_ids.has(map_object.object_id):
			continue
		if map_object.is_exit() and border_labels.has(map_object.destination().to_lower()):
			continue
		var glyph: String = map_object.map_glyph()
		if glyph.is_empty() and not map_object.is_storage():
			continue
		waypoints.append({"position": map_object.global_position, "glyph": glyph,
			"colour": map_object.map_dot_colour(),
			"label": map_object.label if map_object.is_storage() else map_object.destination()})
	waypoints.append_array(_current_entrance_marks())
	waypoints.append_array(_current_service_marks())
	# A grouping has no glyph: its dot is a live mark, and this names it on hover.
	for mark: Dictionary in _harvest_grouping_marks():
		waypoints.append({"position": mark.position, "glyph": "", "colour": mark.colour,
			"label": mark.label})
	return waypoints

## Which switch an actor's dot answers to. What colour that dot is drawn in is
## decided by `ReplicatedActor3D` from the same two fields; this only decides
## which of the marker-type switches turns it off.
static func _minimap_actor_type(dto: Dictionary) -> StringName:
	var kind: int = int(dto.get("kind", 0))
	if kind == ReplicatedActor3D.CREATURE_ACTOR_KIND:
		return (&"invasion" if int(dto.get("name_colour", 0))
			== ReplicatedActor3D.INVASION_NAME_COLOUR else &"creature")
	# EL's HUMAN, COMPUTER_CONTROLLED_HUMAN and PKABLE_HUMAN. Everything else
	# the server replicates and does not call a creature is scenery: a trader,
	# a guard, a gate warden.
	return &"player" if kind in [1, 3, 4] else &"npc"

func _on_minimap_frame_gui_input(event: InputEvent) -> void:
	if _handle_minimap_drag(event):
		return
	if event is InputEventMouseButton:
		var mouse: InputEventMouseButton = event as InputEventMouseButton
		if mouse.button_index == MOUSE_BUTTON_RIGHT and mouse.pressed:
			_minimap_menu.position = Vector2i(get_viewport().get_mouse_position())
			_minimap_menu.popup()
			minimap_frame.accept_event()
			return

func _handle_minimap_drag(event: InputEvent) -> bool:
	if _world_input_blocked() or not event is InputEventMouse:
		return false
	var mouse := event as InputEventMouse
	var modern: bool = hud_workspace != null and hud_workspace.manages_layout()
	var at := minimap_frame.get_global_transform().affine_inverse() * mouse.global_position
	var pointer := game_view.get_global_transform().affine_inverse() * mouse.global_position
	if event is InputEventMouseButton:
		var click := event as InputEventMouseButton
		if click.button_index != MOUSE_BUTTON_LEFT: return false
		if click.pressed:
			var display_scale := minimap_frame.get_global_transform().get_scale().abs()
			var border := maxf(10.0 / maxf(0.01, minf(display_scale.x, display_scale.y)), _minimap_border * _minimap_scale)
			var on_border: bool
			if _minimap_shape == "round":
				var radius := minf(minimap_frame.size.x, minimap_frame.size.y) * 0.5
				var distance := at.distance_to(minimap_frame.size * 0.5)
				on_border = distance >= radius - border and distance <= radius + 1
			else:
				on_border = not Rect2(Vector2.ONE * border, minimap_frame.size - Vector2.ONE * border * 2).has_point(at)
			if not on_border: return false
			_minimap_dragging = true
			_minimap_drag_offset = pointer - minimap_frame.position
			if modern: hud_workspace._remember_moved("minimap", false)
		elif _minimap_dragging:
			_minimap_dragging = false
			if modern: hud_workspace._remember_moved("minimap")
			else: _save_hud_settings()
		else: return false
	elif event is InputEventMouseMotion and _minimap_dragging:
		var minimum := Vector2(6, 6) if modern else Vector2(0, 30)
		var reserved := Vector2(6, 6) if modern else Vector2(WindowDrag.RESERVED_RIGHT_RAIL, WindowDrag.RESERVED_BOTTOM_BAR)
		var maximum := (game_view.size - reserved - minimap_frame.size * minimap_frame.scale).max(minimum)
		minimap_frame.position = (pointer - _minimap_drag_offset).clamp(minimum, maximum)
		if modern: hud_workspace._remember_moved("minimap", false)
	else: return false
	minimap_frame.accept_event()
	return true

func _layout_minimap_cardinals() -> void:
	if minimap_north == null:
		return
	var labels: Array[Label] = [minimap_north, minimap_east, minimap_south, minimap_west]
	var modern: bool = is_instance_valid(hud_workspace) and not hud_workspace.model.working.legacy
	for label: Label in labels: label.visible = not modern
	if modern: return
	var center: Vector2 = minimap_frame.size * 0.5
	var radius: float = maxf(12.0, minf(minimap_frame.size.x,
		minimap_frame.size.y) * 0.5 - 9.0)
	var heading: float = map_camera.rotation.y
	for index: int in range(labels.size()):
		var angle: float = -PI * 0.5 + float(index) * PI * 0.5 - heading
		labels[index].position = center + Vector2(cos(angle), sin(angle)) * radius \
			- labels[index].size * 0.5

func _configure_window_layers() -> void:
	actor_resource_overlay.z_index = 1
	carried_item.z_index = 400
	_make_scene_windows_draggable()

func _configure_window_stack() -> void:
	window_stack = WindowStackScript.new()
	window_stack.name = "WindowStack"
	game_view.add_child(window_stack)
	window_stack.configure(game_view)
	_layout_full_window_views()
	# The Tab map covers HUD parts in both drawing and pointer order. Normal
	# window activation still lets explicitly opened windows appear above it.
	window_stack.register(full_map)
	window_stack.register_full_window_view(console_panel, viewport_container)
	full_map.visibility_changed.connect(_sync_world_overlay_visibility)
	console_panel.visibility_changed.connect(_sync_world_overlay_visibility)
	_sync_world_overlay_visibility()
	# Reminder cards are HUD surfaces below all windows, including for input.
	game_view.move_child(lantern_guide, viewport_container.get_index() + 1)
	var tracker: Control = extension_windows.get("tracked_quest")
	tracker.reparent(game_view)
	tracker.z_index = 8
	game_view.move_child(tracker, lantern_guide.get_index() + 1)
	for panel: Control in [stats_panel, inventory_panel, dialogue_panel,
			trade_panel, storage_panel, ground_bag_panel, manufacturing_panel,
			item_lists_panel, reading_panel, chat_hud, system_chat_hud]:
		window_stack.register(panel)
	for controller: Control in [spells_window, summoning_window, emotes_window,
			ranging_window, mounts_window, guild_window, leaderboards_window, settings_window,
			reference_window, player_info_panel]:
		window_stack.register(controller.get("panel"))
	for panel: Control in extension_windows._cascade():
		window_stack.register(panel)
	window_stack.decorate(dialogue_panel, [get_node("%DialogueBackdrop"),
		get_node("%DialogueFrameTexture")])
	window_stack.attach_overlay(inventory_panel, inventory_quantity_edit)
	window_stack.register(purchase_confirm, true)
	window_stack.register(popup_panel, true)

## Every window moves by its title bar, as Eternal Lands moves all of its own.
## The inventory and the ground bag keep their own handlers: those two also
## carry a resize grip and remember where they were left, and the shared
## dragger has no business in either. The console and the full map are not
## popups but full-screen views, so neither is offered a handle it would only
## use to slide itself off the edge.
func _make_scene_windows_draggable() -> void:
	for panel_and_handle: Array in [
			[stats_panel, "Content/Header"],
			[trade_panel, "Content/Title"],
			[storage_panel, "Content/Title"],
			[manufacturing_panel, "Content/Title"],
			[item_lists_panel, "Content/Header"],
			[dialogue_panel, "DialogueContent/DialogueName"],
			[popup_panel, "PopupContent/PopupTitle"],
			[reading_panel, "ReadingContent/ReadingHeader"]]:
		var panel: Control = panel_and_handle[0] as Control
		if panel == null:
			continue
		var handle: Control = panel.get_node_or_null(
			str(panel_and_handle[1])) as Control
		if handle == null:
			push_warning("window drag handle missing: " + str(panel_and_handle[1]))
			continue
		WindowDrag.attach(panel, handle)

func _sync_chat() -> void:
	_render_chat_feed(chat_output, AppState.chat_lines.filter(
		func(line: Dictionary) -> bool: return _chat_line_shown(line)), CHAT_PANEL_LINES)
	if system_chat_hud != null:
		_render_chat_feed(system_chat_hud.output, AppState.chat_lines.filter(
			func(line: Dictionary) -> bool: return _system_line_shown(line)), CHAT_PANEL_LINES)
	_chat_tail = _last_chat_line()

func _render_chat_feed(target: RichTextLabel, lines: Array, cap: int = 0) -> void:
	target.clear()
	target.scroll_following = true
	var start := maxi(0, lines.size() - cap) if cap > 0 else 0
	for line: Dictionary in lines.slice(start):
		_append_chat_text(target, line)
	target.scroll_to_line(maxi(0, target.get_line_count() - 1))

func _sync_console() -> void:
	if chat_log_tabs == null:
		return
	chat_log_tabs.sync(AppState.active_channels, AppState.chat_history)
	_render_chat_feed(console_output, AppState.chat_history.filter(
		func(line: Dictionary) -> bool: return _console_line_shown(line)))
	_console_tail = _last_chat_line()

func _last_chat_line() -> Dictionary:
	return {} if AppState.chat_lines.is_empty() else AppState.chat_lines.back() as Dictionary

func _chat_line_shown(line: Dictionary) -> bool:
	if not _chat_line_allowed(line) or bool(line.get("in_window", false)):
		return false
	if ChatMessages.kind(line) == "system" and not bool(chat_hud.options.get("combined", false)):
		return false
	return ChatMessages.matches(line, _chat_tab)

func _system_line_shown(line: Dictionary) -> bool:
	return ChatMessages.kind(line) == "system" and _chat_line_allowed(line) and not bool(line.get("in_window", false))

func _console_line_shown(line: Dictionary) -> bool:
	return _chat_line_allowed(line) and ChatMessages.matches(line, chat_log_tabs.selected)

func _chat_channel_number(line: Dictionary) -> int:
	return ChatMessages.channel_number(line)

## Append only the new matching line, preserving a reader's scroll position.
## Filter and history changes rebuild deliberately; normal traffic does not.
func _append_chat_line() -> void:
	var lines: Array = AppState.chat_lines
	var count := lines.size()
	var line: Dictionary = lines.back() as Dictionary if count > 0 else {}
	var previous: Dictionary = lines[count - 2] as Dictionary if count >= 2 else {}
	if chat_log_tabs != null:
		chat_log_tabs.observe(line)
	chat_hud.remember_peer(ChatMessages.peer(line))
	if count >= 2 and is_same(previous, _chat_tail):
		_chat_tail = line
		if _chat_line_shown(line):
			_append_to_chat_feed(chat_output, line, CHAT_PANEL_LINES)
		if _system_line_shown(line):
			_append_to_chat_feed(system_chat_hud.output, line, CHAT_PANEL_LINES)
	else:
		_sync_chat()
	if count >= 2 and is_same(previous, _console_tail):
		_console_tail = line
		if _console_line_shown(line):
			_append_to_chat_feed(console_output, line)
	else:
		_sync_console()

func _append_to_chat_feed(target: RichTextLabel, line: Dictionary, cap: int = 0) -> void:
	var scroll := target.get_v_scroll_bar()
	var following := scroll.value >= scroll.max_value - scroll.page - 2
	target.scroll_following = following
	_append_chat_text(target, line)
	while cap > 0 and target.get_paragraph_count() > cap + 1:
		target.remove_paragraph(0, true)
	if following:
		target.scroll_to_line(maxi(0, target.get_line_count() - 1))

const MIX_REPORT_PREFIX := "You successfully mixed "

func _hold_mix_report_in_window() -> void:
	var line := _last_chat_line()
	if (int(line.get("channel", -1)) == 0
			and str(line.get("text", "")).begins_with(MIX_REPORT_PREFIX)
			and (inventory_panel.is_visible_in_tree() or manufacturing_panel.is_visible_in_tree())):
		line["in_window"] = true

func _chat_line_allowed(line: Dictionary) -> bool:
	if ChatMessages.kind(line) == "system":
		return true
	return console_commands.allows(ChatMessages.speaker(line), str(line.get("text", "")))

func _chat_line_visible(channel: int) -> bool:
	return ChatMessages.matches({"channel": channel}, _chat_tab)

func _formatted_chat_line(line: Dictionary) -> String:
	var category := ChatMessages.kind(line)
	var prefix := ""
	var text := str(line.get("text", ""))
	match category:
		"private":
			prefix = "[Private] "
			if text.begins_with("[PM from "):
				text = text.trim_prefix("[PM from ").trim_suffix("]")
			elif text.begins_with("[PM to "):
				prefix = "[To %s] " % ChatMessages.peer(line)
				text = text.substr(text.find(": ") + 2).trim_suffix("]")
		"guild": prefix = "[Guild] "
		"system": prefix = "[Client] " if int(line.get("channel", 0)) == AppState.LOCAL_CHAT_CHANNEL else "[System] "
		"local": prefix = "[Local] "
		"channel":
			var number := _chat_channel_number(line)
			prefix = "[#%d] " % number if number > 0 else "[Channel] "
			text = text.trim_prefix("[%d] " % number)
	if bool(_hud_element_options.get("chat_timestamps", true)):
		var stamp := str(line.get("stamp", ""))
		if not stamp.is_empty():
			prefix = "[%s] %s" % [stamp, prefix]
	return prefix + text

func _chat_line_colour(line: Dictionary) -> Color:
	var palette := {"local": Color("eee3c8"), "party": Color("9bdff1"),
		"private": Color("d2b4f4"), "guild": Color("e1cf92"), "channel": Color("b3dfad")}
	var colour := int(line.get("colour", 0))
	var category := ChatMessages.kind(line)
	return palette.get(category,
		EloriaProtocol.el_text_colour(colour) if colour > 0 else Color("d6cbaa"))

func _append_chat_text(target: RichTextLabel, line: Dictionary) -> void:
	# Literal text prevents player-supplied BBCode from becoming UI markup.
	target.push_color(_chat_line_colour(line))
	target.add_text(_formatted_chat_line(line) + "\n")
	target.pop()

func _chat_message_for_tab(message: String) -> String:
	if message.begins_with("/") or message.begins_with("#") or message.begins_with("@"):
		return message
	var target := str(chat_hud.destination_key)
	if target.begins_with("channel:"):
		var number := int(target.trim_prefix("channel:"))
		return "@@%d %s" % [number, message] if number in AppState.active_channels else ""
	if target.begins_with("pm:"):
		return "/%s %s" % [target.trim_prefix("pm:"), message]
	match target:
		"party": return "#p " + message
		"guild": return "#gm " + message
		"private": return ""
	return message

func _sync_stats() -> void:
	var stats: Dictionary = AppState.stats
	_track_experience()
	var health: int = int(stats.get("health", 0))
	var max_health: int = maxi(1, int(stats.get("max_health", 1)))
	var ether: int = int(stats.get("ether", 0))
	var max_ether: int = maxi(1, int(stats.get("max_ether", 1)))
	var food: int = int(stats.get("food", 0))
	var max_food: int = maxi(45, food)
	var carried: int = int(stats.get("carried", 0))
	var capacity: int = maxi(0, int(stats.get("capacity", 0)))
	var free_space: int = clampi(capacity - carried, 0, capacity)
	var action_pool := _action_pool(stats)
	var action: int = action_pool.x
	var max_action: int = action_pool.y
	_set_meter(health_bar, health_text, health, max_health, "Health")
	_set_meter(mana_bar, mana_text, ether, max_ether, "Ethereality")
	_set_meter(action_bar, action_text, action, max_action, "Action")
	_set_meter(health_bottom, health_bottom_text, health, max_health, "Health")
	_set_meter(ether_bottom, ether_bottom_text, ether, max_ether, "Mana")
	_set_meter(food_bottom, food_bottom_text, food, max_food, "Food")
	_set_meter(load_bottom, load_bottom_text, free_space, capacity, "Free space")
	_set_meter(action_bottom, action_bottom_text, action, max_action, "Action")
	_sync_experience_meter(stats)
	_set_overhead_meter(overhead_health_row, health, max_health, "health")
	_set_overhead_meter(overhead_ether_row, ether, max_ether, "ether")
	_set_overhead_meter(overhead_food_row, food, max_food, "food")
	_set_overhead_meter(overhead_action_row, action, max_action, "action")
	_set_overhead_meter(overhead_load_row, carried, capacity, "load")
	_layout_actor_resource_overlay()
	if inventory_load != null:
		inventory_load.text = "Load: %d / %d" % [int(stats.get("carried", 0)),
			int(stats.get("capacity", 0))]
	_sync_skill_rows(stats)
	_sync_hud_indicators()
	_sync_knowledge_bar()
	_sync_stats_window(stats)

## The statistics document, the counters page and the session table are
## rebuilt from controls - milliseconds per call - and the packets that drive
## them arrive with every health, food and experience tick. While the window
## is hidden they only go stale; showing it rebuilds them.
func _sync_stats_window(stats: Dictionary) -> void:
	if not stats_panel.visible:
		_stats_window_stale = true
		return
	_stats_window_stale = false
	_sync_statistics_document(stats)
	_sync_session_experience()
	_sync_counters()

func _on_stats_panel_visibility_changed() -> void:
	if stats_panel.visible and _stats_window_stale:
		_sync_stats_window(AppState.stats)
	_fit_stats_window_to_viewport.call_deferred()

## Leave the window's header and footer on screen at larger UI scales. The
## tab bodies scroll within this height instead of pushing the window below
## the viewport, where its last perk and scrollbar would be unreachable.
func _fit_stats_window_to_viewport() -> void:
	if not stats_panel.is_visible_in_tree():
		return
	var dragger := stats_panel.get_node_or_null("WindowDrag") as WindowDrag
	if dragger == null:
		return
	var available: Vector2 = game_view.size - Vector2(
		dragger.reserved_right + dragger.edge_margin * 2,
		dragger.reserved_bottom + dragger.edge_margin * 2)
	stats_panel.size = Vector2(690, 545).min(available.max(Vector2.ONE))
	dragger.clamp_into_view()

## How the skills are grouped, and in what order.
##
## Magic and Summoning sit under Combat because that is what they are used
## for here, and Potion under Crafting because it is mixed at a bench. The
## groups exist to make thirteen rows readable, not to mirror a taxonomy.
## How big a skill's icon is drawn in the statistics table. The art is 32,
## which is the size the shelves and tab strips want; a table thirteen rows
## deep wants something that sits inside a row instead.
const STATS_SKILL_ICON := 20.0

## How big a perk's emblem is drawn. The art is 32 and a perk row is two
## lines deep, so it is drawn at its own size rather than scaled.
const PERK_EMBLEM_SIZE := 32.0

const SKILL_GROUPS: Array[Array] = [
	["Combat", ["attack", "defense", "ranging", "magic", "summoning"]],
	["Crafting", ["manufacturing", "crafting", "engineering", "tailoring",
		"potion", "alchemy"]],
	["Gathering", ["harvesting"]],
]

## The Statistics tab. The scene still holds the text panel this replaced;
## it is hidden rather than deleted, because a bar and a spend button are
## controls and bbcode has neither.
func _build_statistics_tab() -> void:
	stats_text.hide()
	var columns := HBoxContainer.new()
	columns.name = "StatsColumns"
	columns.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 16)
	stats_text.get_parent().add_child(columns)

	var left := VBoxContainer.new()
	left.name = "Character"
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.size_flags_stretch_ratio = 2.0
	columns.add_child(left)
	left.add_child(_stats_heading("Character"))
	var allocation := HBoxContainer.new()
	allocation.name = "PickpointAllocation"
	left.add_child(allocation)
	stats_pickpoint_summary = Label.new()
	stats_pickpoint_summary.name = "AvailablePickpoints"
	stats_pickpoint_summary.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	allocation.add_child(stats_pickpoint_summary)
	stats_pickpoint_confirm = Button.new()
	stats_pickpoint_confirm.name = "ConfirmPickpoints"
	stats_pickpoint_confirm.text = "Confirm"
	stats_pickpoint_confirm.tooltip_text = "Permanently spend the selected pickpoints"
	stats_pickpoint_confirm.pressed.connect(_confirm_pickpoints)
	allocation.add_child(stats_pickpoint_confirm)
	stats_pickpoint_status = Label.new()
	stats_pickpoint_status.name = "PickpointStatus"
	stats_pickpoint_status.custom_minimum_size.x = 240
	stats_pickpoint_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	left.add_child(stats_pickpoint_status)
	stats_pools = HBoxContainer.new()
	stats_pools.name = "Pools"
	stats_pools.add_theme_constant_override("separation", 8)
	left.add_child(stats_pools)
	var left_scroll := ScrollContainer.new()
	left_scroll.name = "CharacterScroll"
	left_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	left.add_child(left_scroll)
	stats_character = VBoxContainer.new()
	stats_character.name = "CharacterBody"
	stats_character.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left_scroll.add_child(stats_character)
	stats_perk_line = Label.new()
	stats_perk_line.name = "PerkLine"
	stats_perk_line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	left.add_child(stats_perk_line)

	var right := VBoxContainer.new()
	right.name = "Skills"
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.size_flags_stretch_ratio = 3.0
	columns.add_child(right)
	right.add_child(_stats_heading("Skills & Experience"))
	var right_scroll := ScrollContainer.new()
	right_scroll.name = "SkillScroll"
	right_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	right.add_child(right_scroll)
	stats_skills = VBoxContainer.new()
	stats_skills.name = "SkillBody"
	stats_skills.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right_scroll.add_child(stats_skills)
	stats_overall = HBoxContainer.new()
	stats_overall.name = "Overall"
	right.add_child(stats_overall)

static func _stats_heading(text: String) -> Label:
	var label := Label.new()
	label.name = "Heading"
	label.text = text
	label.add_theme_color_override("font_color", EL_GUI_BRIGHT_COLOUR)
	return label

## The whole document, rebuilt from the statistics the server last sent.
func _sync_statistics_document(stats: Dictionary) -> void:
	if stats_character == null:
		return
	# Keep the preview stable until the complete server reply arrives.
	if _pickpoint_submitting:
		return
	for host: Node in [stats_pools, stats_character, stats_skills, stats_overall]:
		for child: Node in host.get_children():
			host.remove_child(child)
			child.queue_free()

	var health: int = int(stats.get("health", 0))
	var max_health: int = maxi(1, int(stats.get("max_health", 1)))
	var ether: int = int(stats.get("ether", 0))
	var max_ether: int = maxi(1, int(stats.get("max_ether", 1)))
	var action_pool := _action_pool(stats)
	var action: int = action_pool.x
	var max_action: int = action_pool.y
	for pool: Array in [["Material", health, max_health],
			["Ethereal", ether, max_ether], ["Action", action, max_action]]:
		stats_pools.add_child(_stats_pool(str(pool[0]), int(pool[1]),
			int(pool[2])))

	stats_character.add_child(_stats_heading("Attributes"))
	for row: Dictionary in _attribute_rows(stats):
		var value: int = int(row.value)
		stats_character.add_child(_stats_spend_row(str(row.label), value,
			value, "attribute", str(row.key), int(row.maximum)))
	stats_character.add_child(_stats_heading("Nexus"))
	for pair: Array in [["Human", "human_nexus"], ["Animal", "animal_nexus"],
			["Vegetal", "vegetal_nexus"], ["Inorganic", "inorganic_nexus"],
			["Artificial", "artificial_nexus"], ["Magic", "magic_nexus"]]:
		var key: String = str(pair[1])
		var current: int = int(stats.get(key, 0))
		var base: int = int(stats.get(key + "_base", current))
		stats_character.add_child(_stats_spend_row(str(pair[0]), current, base,
			"nexus", key, NEXUS_MAXIMUM))
	stats_character.add_child(_stats_value_row("Food",
		str(int(stats.get("food", 0)))))
	for pair: Array in _research_lines(stats):
		stats_character.add_child(_stats_value_row(str(pair[0]), str(pair[1])))

	var names: Array[String] = []
	for raw_perk: Variant in AppState.perks:
		var perk: Dictionary = raw_perk as Dictionary
		# Where a perk came from is worth saying: one you are wearing goes
		# when the cape does, and a player looking at this list should not
		# have to work out which of these they actually own.
		var suffix: String = " (from equipment)" if bool(
			perk.get("from_gear", false)) else ""
		names.append("%s%s" % [str(perk.get("name", "")), suffix])
	stats_perk_line.text = "Perks:  %s" % (
		"none yet" if names.is_empty() else "  •  ".join(names))

	var head := HBoxContainer.new()
	head.name = "Head"
	head.add_child(_stats_cell("Skill", true))
	head.add_child(_stats_cell("Level", false, HORIZONTAL_ALIGNMENT_RIGHT))
	head.add_child(_stats_cell("Experience", false, HORIZONTAL_ALIGNMENT_RIGHT,
		260))
	stats_skills.add_child(head)
	for group: Array in SKILL_GROUPS:
		stats_skills.add_child(_stats_heading(str(group[0])))
		for raw_skill: Variant in group[1] as Array:
			stats_skills.add_child(_stats_skill_row(str(raw_skill), stats))
	stats_overall.add_child(_stats_skill_row("overall", stats))
	_refresh_pickpoint_controls()

static func _stats_pool(title: String, value: int, maximum: int) -> Control:
	var box := VBoxContainer.new()
	box.name = title
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var label := Label.new()
	label.name = "Title"
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.text = title
	box.add_child(label)
	var amount := Label.new()
	amount.name = "Value"
	amount.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	amount.text = "%d / %d" % [value, maximum]
	amount.add_theme_color_override("font_color", Color(0.6, 0.6, 1.0))
	box.add_child(amount)
	return box

## Minus only undoes the draft; committed points are never removed here.
func _stats_spend_row(label: String, current: int, base: int, kind: String,
		key: String, maximum: int) -> Control:
	var row := HBoxContainer.new()
	row.name = "Row%s" % key.replace(" ", "").validate_node_name()
	row.set_meta("allocation", "%s:%s" % [kind, key])
	row.set_meta("current", current)
	row.set_meta("base", base)
	row.set_meta("maximum", maximum)
	row.add_child(_stats_cell(label, true))
	var remove := Button.new()
	remove.name = "Remove"
	remove.custom_minimum_size = Vector2(30, 0)
	remove.focus_mode = Control.FOCUS_NONE
	remove.text = "−"
	remove.tooltip_text = "Undo one unconfirmed point in %s" % label
	remove.pressed.connect(_adjust_pickpoint.bind(kind, key, -1))
	row.add_child(remove)
	var value := _stats_cell("", false, HORIZONTAL_ALIGNMENT_RIGHT, 90)
	value.name = "Value"
	row.add_child(value)
	var spend := Button.new()
	spend.name = "Spend"
	spend.custom_minimum_size = Vector2(30, 0)
	spend.focus_mode = Control.FOCUS_NONE
	spend.text = "+"
	spend.tooltip_text = "Preview one more point in %s" % label
	spend.add_theme_color_override("font_color", Color(0.45, 0.85, 0.45))
	spend.pressed.connect(_adjust_pickpoint.bind(kind, key, 1))
	row.add_child(spend)
	return row

func _draft_pickpoints() -> int:
	var total := 0
	for amount: int in _pickpoint_draft.values():
		total += amount
	return total

func _refresh_pickpoint_controls() -> void:
	var total := _draft_pickpoints()
	var remaining := _available_pickpoints() - total
	var valid := remaining >= 0
	var found := 0
	for row: Node in stats_character.get_children():
		if not row.has_meta("allocation"):
			continue
		var amount := int(_pickpoint_draft.get(row.get_meta("allocation"), 0))
		found += amount
		var base := int(row.get_meta("base"))
		var maximum := int(row.get_meta("maximum"))
		valid = valid and (amount == 0 or base + amount <= maximum)
		var value := row.get_node("Value") as Label
		value.text = "%d / %d" % [int(row.get_meta("current")) + amount, base + amount]
		value.modulate = Color("a1e899") if amount > 0 else Color.WHITE
		value.tooltip_text = "%d unconfirmed point(s)" % amount if amount > 0 else ""
		(row.get_node("Remove") as Button).disabled = _pickpoint_submitting or amount == 0
		(row.get_node("Spend") as Button).disabled = _pickpoint_submitting or remaining <= 0 or base + amount >= maximum
	valid = valid and found == total
	stats_pickpoint_summary.text = "Pickpoints available: %s" % _grouped(maxi(0, remaining))
	stats_pickpoint_confirm.disabled = _pickpoint_submitting or total == 0 or not valid
	stats_pickpoint_confirm.text = "Confirming…" if _pickpoint_submitting else "Confirm"
	stats_pickpoint_status.text = ("Confirming %d pickpoints…" % total if _pickpoint_submitting
		else "Your points changed. Reduce the selection before confirming." if not valid
		else "%d selected · Confirm to spend" % total if total > 0
		else "Use − and + to choose your points.")

func _adjust_pickpoint(kind: String, key: String, delta: int) -> void:
	if _pickpoint_submitting or delta not in [-1, 1]:
		return
	var id := "%s:%s" % [kind, key]
	var amount := int(_pickpoint_draft.get(id, 0))
	var target: Node
	for row: Node in stats_character.get_children():
		if str(row.get_meta("allocation", "")) == id:
			target = row
			break
	if target == null:
		return
	if delta > 0 and (_available_pickpoints() <= _draft_pickpoints()
			or int(target.get_meta("base")) + amount >= int(target.get_meta("maximum"))):
		return
	if delta < 0 and amount == 0:
		return
	amount += delta
	if amount == 0:
		_pickpoint_draft.erase(id)
	else:
		_pickpoint_draft[id] = amount
	if delta < 0:
		_road_ui(19)
	_refresh_pickpoint_controls()

func _confirm_pickpoints() -> void:
	if _pickpoint_submitting:
		return
	_refresh_pickpoint_controls()
	if stats_pickpoint_confirm.disabled:
		return
	var entries: PackedStringArray = []
	for id: String in _pickpoint_draft:
		entries.append("%s:%d" % [id, int(_pickpoint_draft[id])])
	var error := Network.send_chat("#spend batch " + ",".join(entries))
	if error != OK:
		stats_pickpoint_status.text = "Could not confirm. Your choices are still here."
		return
	_pickpoint_submitting = true
	_refresh_pickpoint_controls()

func _on_pickpoint_reply() -> void:
	if not _pickpoint_submitting or AppState.chat_lines.is_empty():
		return
	var line: Dictionary = AppState.chat_lines.back()
	if int(line.get("channel", -1)) != 0:
		return
	var reply := str(line.get("text", ""))
	var accepted := reply.begins_with("Pickpoint allocation confirmed: ")
	if not accepted and not reply.begins_with("Pickpoint allocation rejected: ") and not reply.begins_with("Syntax: #spend"):
		return
	_pickpoint_submitting = false
	if accepted:
		_pickpoint_draft.clear()
	_sync_stats()
	stats_pickpoint_status.text = "Pickpoints confirmed." if accepted else reply

func _stats_value_row(label: String, value: String) -> Control:
	var row := HBoxContainer.new()
	row.name = "Value"
	row.add_child(_stats_cell(label, true))
	row.add_child(_stats_cell(value, false, HORIZONTAL_ALIGNMENT_RIGHT, 90))
	row.add_child(_stats_spacer(30))
	return row

## One skill: its level, how far through the level it is, and the totals.
##
## The bar measures progress inside the current level rather than towards the
## lifetime figure beside it. Those are different questions and the level is
## the one a player is actually working on - at high levels the lifetime
## fraction barely moves, and a bar that never visibly filled would say
## nothing at all.
func _stats_skill_row(skill: String, stats: Dictionary) -> Control:
	var level: int = int(stats.get("overall_level", 0)) if skill == "overall" \
		else int(stats.get(skill, 0))
	var base: int = level if skill == "overall" else int(
		stats.get(skill + "_base", level))
	var experience: int = _experience_total(skill, stats)
	var next_experience: int = int(stats.get(skill + "_exp_next", 0))
	var floor_experience: int = _experience_floor_for_level(base)
	var span: int = maxi(1, next_experience - floor_experience)
	var into: int = clampi(experience - floor_experience, 0, span)
	var fraction: float = 1.0 if _skill_is_capped(skill, stats) else float(into) / float(span)

	var row := HBoxContainer.new()
	row.name = "Skill%s" % skill.capitalize()
	row.add_child(_stats_skill_icon(skill))
	row.add_child(_stats_cell(skill.capitalize(), true))
	row.add_child(_stats_cell("%d / %d" % [level, base], false,
		HORIZONTAL_ALIGNMENT_RIGHT, 90))
	var meter := HBoxContainer.new()
	meter.name = "Experience"
	meter.custom_minimum_size = Vector2(260, 0)
	var bar := ProgressBar.new()
	bar.name = "Bar"
	bar.custom_minimum_size = Vector2(70, 12)
	bar.show_percentage = false
	bar.max_value = 1.0
	bar.value = fraction
	bar.modulate = _experience_colour(fraction)
	meter.add_child(bar)
	var totals := Label.new()
	totals.name = "Totals"
	totals.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	totals.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	totals.text = _experience_text(skill, stats)
	meter.add_child(totals)
	row.add_child(meter)
	return row

## How far along reads as a colour as well as a length, so a glance at the
## column finds the skill that is nearly there without reading any numbers.
static func _experience_colour(fraction: float) -> Color:
	if fraction >= 0.85:
		return Color(0.55, 0.90, 0.50)      # nearly a level
	if fraction >= 0.5:
		return Color(0.85, 0.75, 0.35)      # past halfway
	if fraction >= 0.2:
		return Color(0.80, 0.55, 0.30)
	return Color(0.65, 0.40, 0.32)          # only just started

## The subject icon for a skill, drawn down to the height of a table row.
##
## Thirteen rows of art at its native size would be a column of pictures with
## a table beside it; the list is read down the names, and the icon is there
## to be recognised in passing. A skill with nothing drawn for it still gets
## the spacer, so the names stay in one column.
static func _stats_skill_icon(skill: String) -> Control:
	var frame := TextureRect.new()
	frame.name = "Icon"
	frame.custom_minimum_size = Vector2(STATS_SKILL_ICON, STATS_SKILL_ICON)
	frame.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	frame.texture = SubjectIcons.icon_for(skill)
	return frame

static func _stats_cell(text: String, grow: bool,
		alignment: int = HORIZONTAL_ALIGNMENT_LEFT,
		width: int = 120) -> Label:
	var label := Label.new()
	label.text = text
	label.horizontal_alignment = alignment
	if grow:
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	else:
		label.custom_minimum_size = Vector2(width, 0)
	return label

static func _stats_spacer(width: int) -> Control:
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(width, 0)
	return spacer


## One row of a statistics section: the label on the left and the value right
## aligned in its own cell, so every value in that section lines up whatever
## the labels happen to measure.
static func _stat_row(label: String, value: String, spaced := false) -> String:
	var gap: String = "\n" if spaced else ""
	# Cells are left to size themselves to their contents. Fixed expand ratios
	# were tried and made it worse: they narrow the value column until
	# "1000/1000" wraps mid-number.
	return "[cell]%s%s[/cell][cell]%s[/cell]" % [gap, label,
		"[right]%s[/right]" % value if not value.is_empty() else ""]

## A heading across a section's columns.
static func _stat_heading(text: String, spaced := false,
		columns := 2) -> String:
	var gap: String = "\n" if spaced else ""
	var cells: String = "[cell]%s%s[/cell]" % [gap, text]
	for _column: int in range(columns - 1):
		cells += "[cell] [/cell]"
	return cells

## Thousands separators. A seven-figure experience total is unreadable as a
## bare run of digits, and these columns now carry several of them.
static func _grouped(value: int) -> String:
	var digits: String = str(absi(value))
	var grouped: String = ""
	while digits.length() > 3:
		grouped = "," + digits.substr(digits.length() - 3) + grouped
		digits = digits.substr(0, digits.length() - 3)
	grouped = digits + grouped
	return ("-" + grouped) if value < 0 else grouped

## The attributes to draw, newest source first.
##
## Every one of these is bought directly now, so there is no longer a split
## between attributes and the cross attributes derived from them. Which ones
## exist is the server's to say: it sends the names, the values and the
## ceilings together, and this holds no list of its own to go stale. The
## fallback reads the six fixed slots of the legacy stats packet, and its
## names are right for exactly the servers that leave the wide packet unsent.
func _attribute_rows(stats: Dictionary) -> Array[Dictionary]:
	var rows: Array[Dictionary] = []
	for raw_attribute: Variant in AppState.attributes:
		rows.append(raw_attribute as Dictionary)
	if not rows.is_empty():
		return rows
	for label_and_key: Array in LEGACY_ATTRIBUTES:
		var key: String = str(label_and_key[1])
		rows.append({"key": key, "label": str(label_and_key[0]),
			"value": int(stats.get(key + "_base", stats.get(key, 0))),
			"maximum": ATTRIBUTE_MAXIMUM})
	return rows

static func _stat_pair(stats: Dictionary, key: String) -> String:
	return "%d/%d" % [int(stats.get(key, 0)), int(stats.get(key + "_base", stats.get(key, 0)))]

## The spend control drawn beside one buyable line, or nothing at all.
##
## It is a link rather than a button because these rows are cells in a bbcode
## table, and the whole statistics document is one RichTextLabel. What it says
## is only ever what the server has already told this client: the pick points
## come from the stats packet, the ceilings from the same packet's own values,
## and a perk's refusal is the server's sentence, quoted.
static func _spend_link(kind: String, name: String, affordable: bool) -> String:
	if not affordable:
		return ""
	return " [url=spend:%s:%s][color=#7fd87f][b]+[/b][/color][/url]" % [kind, name]

## How many pick points the server says are unspent.
func _available_pickpoints() -> int:
	var earned: int = int(AppState.stats.get("pickpoints_earned",
		AppState.stats.get("overall", 0)))
	return earned - int(AppState.stats.get("pickpoints_spent", 0))

func _on_stats_meta_clicked(meta: Variant) -> void:
	var parts: PackedStringArray = str(meta).split(":", false)
	if parts.size() != 3 or parts[0] != "spend":
		return
	_ask_to_spend(parts[1], parts[2])

## Perks keep their priced confirmation; attributes and nexus use the draft.
func _ask_to_spend(kind: String, name: String) -> void:
	if kind in ["attribute", "nexus"]:
		_adjust_pickpoint(kind, name, 1)
		return
	_pending_purchase = [kind, name]
	var readable: String = name.capitalize()
	match kind:
		"nexus":
			purchase_prompt.text = (
				"Spend 1 pick point to raise your %s nexus?" % readable)
		"perk":
			var cost: int = 0
			var gold: int = 0
			for raw_perk: Variant in AppState.perk_catalog:
				var perk: Dictionary = raw_perk as Dictionary
				if str(perk.get("name", "")).to_lower() == name.to_lower():
					cost = int(perk.get("pickpoints", 0))
					gold = int(perk.get("gold", 0))
			var price: String = ("%d pick points" % cost if cost > 0
				else "no pick points" if cost == 0
				else "and gain %d pick points" % -cost)
			if gold > 0:
				price += " and %s gold" % _grouped(gold)
			readable = str(name)
			purchase_prompt.text = "Take the %s perk for %s?" % [
				readable, price]
		_:
			purchase_prompt.text = (
				"Spend 1 pick point to raise your %s?" % readable)
	purchase_confirm.show()
	# Nothing lays this panel out - it hangs off the root rather than a
	# container - so it is sized to its own contents and then centred on the
	# viewport, which is where a question about to spend something belongs.
	purchase_confirm.reset_size()
	purchase_confirm.position = (get_viewport_rect().size
		- purchase_confirm.size) * 0.5
	purchase_confirm.move_to_front()

## The server owns every one of these rules; this only asks. What comes back
## is a line of text and fresh stats, perks and catalogue packets, so the
## window redraws from the server's answer rather than from the request.
func _on_purchase_cancelled() -> void:
	if not _pending_purchase.is_empty(): _road_ui(19)
	_pending_purchase.clear()
	purchase_confirm.hide()

func _on_purchase_confirmed() -> void:
	purchase_confirm.hide()
	if _pending_purchase.size() != 2:
		return
	var error: Error = Network.send_chat("#spend %s %s" % [
		_pending_purchase[0], _pending_purchase[1]])
	if error != OK:
		push_warning("#spend failed: " + error_string(error))
	_pending_purchase.clear()

## The Counters tab. The scene still holds the list and the text panel this
## replaced; both are hidden rather than deleted, because the scene is shared
## and a node removed there is a merge conflict here.
func _build_counters_tab() -> void:
	counter_categories.hide()
	counter_text.hide()
	var column := VBoxContainer.new()
	column.name = "CounterContent"
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.size_flags_vertical = Control.SIZE_EXPAND_FILL
	counter_text.get_parent().add_child(column)
	counter_tabs = HBoxContainer.new()
	counter_tabs.name = "CounterTabs"
	counter_tabs.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(counter_tabs)
	var scroll := ScrollContainer.new()
	scroll.name = "CounterScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	counter_body = VBoxContainer.new()
	counter_body.name = "CounterBody"
	counter_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(counter_body)

## The Perks tab, built here rather than in the scene because the perk table
## is the server's and arrives on the wire; there is nothing to lay out until
## it does.
func _build_perks_tab() -> void:
	perk_tab = MarginContainer.new()
	perk_tab.name = "Perks"
	stats_tabs.add_child(perk_tab)
	var column := VBoxContainer.new()
	column.name = "PerkContent"
	perk_tab.add_child(column)
	perk_summary = Label.new()
	perk_summary.name = "PerkSummary"
	perk_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	perk_summary.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(perk_summary)
	# The tabs the shelf is divided into. "All" is first and always there;
	# the rest are whatever the server said its perks belong to, so a
	# category invented later needs no change here.
	perk_filters = HBoxContainer.new()
	perk_filters.name = "PerkFilters"
	perk_filters.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(perk_filters)
	var scroll := ScrollContainer.new()
	scroll.name = "PerkScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	perk_rows = VBoxContainer.new()
	perk_rows.name = "PerkRows"
	perk_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(perk_rows)
	perk_hint = Label.new()
	perk_hint.name = "PerkHint"
	perk_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	perk_hint.text = "Select a perk to view its next tier."
	perk_hint.modulate = Color(1, 1, 1, 0.55)
	column.add_child(perk_hint)

	# An in-HUD panel rather than a ConfirmationDialog: every other window
	# this client draws is one of these, and a native dialog would be the
	# only piece of the game wearing the desktop's chrome.
	purchase_confirm = PanelContainer.new()
	purchase_confirm.name = "PurchaseConfirm"
	purchase_confirm.mouse_filter = Control.MOUSE_FILTER_STOP
	# Above the statistics panel that raises it, and below the server's own
	# popup at 40, which is the one thing that should interrupt this.
	purchase_confirm.z_index = 35
	purchase_confirm.hide()
	# Beside the other windows rather than on the root: they are all children
	# of the game view, and a question about spending has to come up over the
	# statistics panel that asked it.
	game_view.add_child(purchase_confirm)
	var confirm_column := VBoxContainer.new()
	confirm_column.name = "PurchaseBody"
	purchase_confirm.add_child(confirm_column)
	purchase_prompt = Label.new()
	purchase_prompt.name = "PurchasePrompt"
	purchase_prompt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	purchase_prompt.custom_minimum_size = Vector2(360.0, 0.0)
	confirm_column.add_child(purchase_prompt)
	var confirm_buttons := HBoxContainer.new()
	confirm_buttons.name = "PurchaseButtons"
	confirm_buttons.alignment = BoxContainer.ALIGNMENT_END
	confirm_column.add_child(confirm_buttons)
	var confirm_yes := Button.new()
	confirm_yes.name = "PurchaseYes"
	confirm_yes.text = "Spend"
	confirm_yes.pressed.connect(_on_purchase_confirmed)
	confirm_buttons.add_child(confirm_yes)
	var confirm_no := Button.new()
	confirm_no.name = "PurchaseNo"
	confirm_no.text = "Cancel"
	confirm_no.pressed.connect(_on_purchase_cancelled)
	confirm_buttons.add_child(confirm_no)
	_sync_perk_catalog()

## Redraws the Perks tab from the catalogue the server sent. A perk it refuses
## carries the refusal instead of a Take button, in the server's own words -
## this window decides nothing about who may have what.
func _sync_perk_catalog() -> void:
	if perk_rows == null:
		return
	for child: Node in perk_rows.get_children():
		perk_rows.remove_child(child)
		child.queue_free()
	perk_summary.text = "Pick points available: %d" % _available_pickpoints()
	_sync_perk_filters()
	if AppState.perk_catalog.is_empty():
		var waiting := Label.new()
		waiting.name = "PerksWaiting"
		waiting.text = "The server has not listed the perks it offers."
		perk_rows.add_child(waiting)
		return
	var shown: int = 0
	for raw_perk: Variant in AppState.perk_catalog:
		var perk: Dictionary = raw_perk as Dictionary
		if not _perk_filter.is_empty() and str(
				perk.get("category", "")) != _perk_filter:
			continue
		perk_rows.add_child(_perk_row(perk))
		shown += 1
	if shown == 0:
		var empty := Label.new()
		empty.name = "PerksEmpty"
		empty.text = "No perks in this category."
		perk_rows.add_child(empty)

## The tabs, rebuilt from whatever categories the server actually sent. A tab
## for a category with nothing in it would be a promise the shelf cannot keep.
func _sync_perk_filters() -> void:
	if perk_filters == null:
		return
	for child: Node in perk_filters.get_children():
		perk_filters.remove_child(child)
		child.queue_free()
	var categories: Array[String] = []
	for raw_perk: Variant in AppState.perk_catalog:
		var category: String = str((raw_perk as Dictionary).get("category", ""))
		if not category.is_empty() and not categories.has(category):
			categories.append(category)
	if categories.is_empty():
		return
	categories.sort()
	for name: String in ([""] + categories):
		var tab := Button.new()
		tab.name = "Filter%s" % ("All" if name.is_empty()
			else name.replace(" ", "").validate_node_name())
		tab.text = "All" if name.is_empty() else name
		tab.toggle_mode = true
		tab.button_pressed = name == _perk_filter
		tab.focus_mode = Control.FOCUS_NONE
		# The server names these categories, so a category it adds draws no
		# picture rather than the wrong one.
		var icon: Texture2D = SubjectIcons.icon_for(
			"all" if name.is_empty() else name)
		if icon != null:
			tab.icon = icon
			tab.add_theme_constant_override("h_separation", 6)
		tab.pressed.connect(_on_perk_filter_chosen.bind(name))
		perk_filters.add_child(tab)

func _on_perk_filter_chosen(category: String) -> void:
	if _perk_filter == category:
		return
	_perk_filter = category
	_sync_perk_catalog()

## One row: what it is, how far you have taken it, what the next step costs,
## and the button that buys it. Every number here is the server's - the tier
## it is at, the tier it stops at, the price of the step, and its own reason
## for refusing one.
func _perk_row(perk: Dictionary) -> Control:
	var perk_name: String = str(perk.get("name", ""))
	var owned: int = int(perk.get("tier", 0))
	var maximum: int = maxi(1, int(perk.get("max_tier", 1)))
	var blocker: String = str(perk.get("blocker", ""))
	var maxed: bool = owned >= maximum

	var frame := PanelContainer.new()
	# Node names keep spaces, and a row is looked up by name; the perk names
	# with two words would otherwise be the awkward ones.
	frame.name = "Perk%s" % perk_name.replace(" ", "").validate_node_name()
	if maxed or not blocker.is_empty():
		# Dimmed rather than hidden: a perk you cannot take today is still
		# one you are choosing against, and it has to stay readable.
		frame.modulate = Color(1, 1, 1, 0.55)
	var row := HBoxContainer.new()
	row.name = "Row"
	row.add_theme_constant_override("separation", 12)
	frame.add_child(row)

	# The emblem leads the row. A perk the server has added and nothing has
	# been drawn for keeps the space, so the names stay in one column rather
	# than one row starting further left than the rest.
	var emblem := TextureRect.new()
	emblem.name = "Emblem"
	emblem.custom_minimum_size = Vector2(PERK_EMBLEM_SIZE, PERK_EMBLEM_SIZE)
	emblem.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	emblem.texture = PerkIcons.icon_for(perk_name)
	row.add_child(emblem)

	var text := VBoxContainer.new()
	text.name = "Text"
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(text)
	var title := Label.new()
	title.name = "Name"
	title.text = perk_name
	text.add_child(title)
	var detail := Label.new()
	detail.name = "Detail"
	detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail.text = str(perk.get("description", ""))
	detail.modulate = Color(1, 1, 1, 0.75)
	text.add_child(detail)

	row.add_child(_perk_pips(owned, maximum))

	var price := Label.new()
	price.name = "Price"
	price.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	price.custom_minimum_size = Vector2(140, 0)
	price.text = "" if maxed else _perk_price(perk)
	row.add_child(price)

	var take := Button.new()
	take.name = "Take"
	take.custom_minimum_size = Vector2(110, 0)
	if maxed:
		# There is nothing left to sell, so the button stops being one.
		take.text = "OWNED"
		take.disabled = true
		take.tooltip_text = "Every tier of %s is yours." % perk_name
	else:
		take.text = "TAKE"
		take.disabled = not blocker.is_empty()
		# The tooltip is the server's own refusal where there is one. This
		# window decides nothing about who may have what.
		take.tooltip_text = blocker if not blocker.is_empty() else str(
			perk.get("description", ""))
		take.pressed.connect(_ask_to_spend.bind("perk", perk_name))
	row.add_child(take)
	return frame

## The tier strip: one box per tier, filled up to the tier owned, with the
## count under it. Three boxes is the whole perk system at a glance, which a
## sentence saying "tier 1 of 3" is not.
func _perk_pips(owned: int, maximum: int) -> Control:
	var column := VBoxContainer.new()
	column.name = "Tiers"
	column.custom_minimum_size = Vector2(84, 0)
	var boxes := HBoxContainer.new()
	boxes.name = "Pips"
	boxes.alignment = BoxContainer.ALIGNMENT_CENTER
	boxes.add_theme_constant_override("separation", 4)
	column.add_child(boxes)
	for index: int in range(maximum):
		var pip := Panel.new()
		pip.name = "Pip%d" % (index + 1)
		pip.custom_minimum_size = Vector2(16, 16)
		pip.modulate = (Color(0.85, 0.66, 0.34) if index < owned
			else Color(1, 1, 1, 0.22))
		boxes.add_child(pip)
	var count := Label.new()
	count.name = "Count"
	count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	count.text = "%d / %d" % [owned, maximum]
	count.modulate = Color(1, 1, 1, 0.7)
	column.add_child(count)
	return column

## What the next tier costs, in the shape the window shows it: "3 PP - 500 G".
static func _perk_price(perk: Dictionary) -> String:
	var cost: int = int(perk.get("pickpoints", 0))
	var gold: int = int(perk.get("gold", 0))
	var parts: Array[String] = []
	if cost > 0:
		parts.append("%d PP" % cost)
	elif cost < 0:
		# A perk that pays pick points out rather than in.
		parts.append("+%d PP" % -cost)
	else:
		parts.append("free")
	if gold > 0:
		parts.append("%s G" % _grouped(gold))
	return "  \u2022  ".join(parts)

func _on_stats_tab_changed(tab: int) -> void:
	if tab == 1:
		_sync_knowledge()
	elif tab == 2:
		_sync_counters()
		if stats_panel.visible and AppState.lantern_tutorial.get("tutorial", "") == "second_bell":
			Network.tutorial_ui(4)
	elif tab == 3:
		_sync_session_experience()

func _track_experience() -> void:
	for skill: String in EXPERIENCE_SKILLS:
		var key: String = skill + "_exp"
		if not AppState.stats.has(key):
			continue
		var current: int = int(AppState.stats[key])
		if _experience_snapshot.has(skill):
			var gain: int = current - int(_experience_snapshot[skill])
			if gain > 0:
				_session_xp_gain[skill] = int(_session_xp_gain.get(skill, 0)) + gain
				_session_xp_last[skill] = gain
				_session_xp_max[skill] = maxi(int(_session_xp_max.get(skill, 0)), gain)
		_experience_snapshot[skill] = current

func _sync_session_experience() -> void:
	if session_xp_text == null:
		return
	var cells: Array[String] = ["[cell][b]Skill[/b][/cell]",
		"[cell][right][b]Total Exp[/b][/right][/cell]",
		"[cell][right][b]Max Exp[/b][/right][/cell]",
		"[cell][right][b]Last Exp[/b][/right][/cell]"]
	for skill: String in EXPERIENCE_SKILLS:
		cells.append("[cell]%s[/cell]" % skill.capitalize())
		cells.append("[cell][right]%d[/right][/cell]" % int(_session_xp_gain.get(skill, 0)))
		cells.append("[cell][right]%d[/right][/cell]" % int(_session_xp_max.get(skill, 0)))
		cells.append("[cell][right]%d[/right][/cell]" % int(_session_xp_last.get(skill, 0)))
	var seconds: int = maxi(0, (Time.get_ticks_msec() - _session_started_msec) / 1000)
	var xp_for_rate: int = int(_session_xp_gain.get("overall", 0))
	if xp_for_rate <= 0:
		for skill: String in EXPERIENCE_SKILLS:
			if skill != "overall":
				xp_for_rate += int(_session_xp_gain.get(skill, 0))
	var rate: float = float(xp_for_rate) * 60.0 / maxf(1.0, float(seconds))
	session_xp_text.text = ("[table=4]%s[/table]\n\nSession Time      %02d:%02d:%02d\n"
		+ "Exp/Min           %.2f\nDistance          %d") % ["".join(cells),
		seconds / 3600, (seconds / 60) % 60, seconds % 60, rate, _session_distance]

func _reset_session_tracking() -> void:
	_session_started_msec = Time.get_ticks_msec()
	_session_xp_gain.clear()
	_session_xp_max.clear()
	_session_xp_last.clear()
	_experience_snapshot.clear()
	_counter_session_baseline = AppState.activity_counters.duplicate()
	_session_distance = 0
	_last_distance_tile = Vector2i(-99999, -99999)
	_track_experience()
	_sync_session_experience()
	_sync_counters()

func _update_session_distance() -> void:
	var actor_value: Variant = AppState.actors.get(AppState.local_actor_id)
	if not actor_value is Dictionary:
		return
	var actor: Dictionary = actor_value as Dictionary
	var tile := Vector2i(int(actor.get("x", 0)), int(actor.get("y", 0)))
	if _last_distance_tile.x < -90000:
		_last_distance_tile = tile
		return
	var distance: int = maxi(absi(tile.x - _last_distance_tile.x),
		absi(tile.y - _last_distance_tile.y))
	if distance > 0 and distance <= 4:
		_session_distance += distance
	_last_distance_tile = tile

## The counters window: six pages of totals, each row opening into what it is
## made of, with that page's achievements underneath.
##
## Every part of the arrangement is the server's - which page a total sits on,
## what a row opens into, and what an achievement is working towards. The
## client used to show one total at a time out of a dropdown, and the nineteen
## finer tallies were a second flat list that said nothing about the first.
func _sync_counters() -> void:
	if counter_body == null:
		return
	if not stats_panel.visible:
		_stats_window_stale = true
		return
	for child: Node in counter_body.get_children():
		counter_body.remove_child(child)
		child.queue_free()
	_sync_counter_tabs()
	var categories: Array = AppState.counter_layout.get("categories", []) as Array
	if categories.is_empty():
		var waiting := Label.new()
		waiting.name = "CountersWaiting"
		waiting.text = "Waiting for server counters"
		counter_body.add_child(waiting)
		return
	var page: Dictionary = _counter_page(categories)
	counter_body.add_child(_counter_table(page))
	var achievements: Control = _counter_achievements(str(page.get("name", "")))
	if achievements != null:
		counter_body.add_child(achievements)

## Which page is showing: the one chosen, or the first, so the window is never
## blank while a valid arrangement is loaded.
func _counter_page(categories: Array) -> Dictionary:
	for raw: Variant in categories:
		var page: Dictionary = raw as Dictionary
		if str(page.get("name", "")) == _selected_counter_category:
			return page
	var first: Dictionary = categories[0] as Dictionary
	_selected_counter_category = str(first.get("name", ""))
	return first

func _sync_counter_tabs() -> void:
	if counter_tabs == null:
		return
	for child: Node in counter_tabs.get_children():
		counter_tabs.remove_child(child)
		child.queue_free()
	for raw: Variant in AppState.counter_layout.get("categories", []) as Array:
		var page_name: String = str((raw as Dictionary).get("name", ""))
		var tab := Button.new()
		tab.name = "Counters%s" % page_name.replace(" ", "").validate_node_name()
		tab.text = page_name
		tab.toggle_mode = true
		tab.button_pressed = page_name == _selected_counter_category
		tab.focus_mode = Control.FOCUS_NONE
		tab.pressed.connect(_on_counter_page_chosen.bind(page_name))
		counter_tabs.add_child(tab)

func _on_counter_page_chosen(page_name: String) -> void:
	if _selected_counter_category == page_name:
		return
	_selected_counter_category = page_name
	_sync_counters()

## One page of totals. Session is this client's own arithmetic against a
## baseline taken at login; Global is the server's confirmed number.
func _counter_table(page: Dictionary) -> Control:
	var table := VBoxContainer.new()
	table.name = "CounterTable"
	var head := HBoxContainer.new()
	head.name = "Head"
	head.add_child(_counter_cell("", true))
	head.add_child(_counter_cell("Session", false, HORIZONTAL_ALIGNMENT_RIGHT))
	head.add_child(_counter_cell("Global", false, HORIZONTAL_ALIGNMENT_RIGHT))
	head.add_child(_counter_spacer())
	table.add_child(head)
	var breakdowns: Dictionary = AppState.counter_layout.get(
		"breakdowns", {}) as Dictionary
	for raw: Variant in page.get("counters", []) as Array:
		var counter: String = str(raw)
		table.add_child(_counter_row(counter, breakdowns.has(counter)))
		if _open_counters.has(counter) and breakdowns.has(counter):
			for detail: Variant in breakdowns[counter] as Array:
				table.add_child(_counter_detail(detail as Dictionary))
	return table

func _counter_row(counter: String, expandable: bool) -> Control:
	var total: int = int(AppState.activity_counters.get(counter, 0))
	var session: int = maxi(0, total - int(
		_counter_session_baseline.get(counter, 0)))
	var row := HBoxContainer.new()
	row.name = "Counter%s" % counter.replace(" ", "").validate_node_name()
	row.add_child(_counter_cell(counter, true))
	row.add_child(_counter_cell(_grouped(session), false,
		HORIZONTAL_ALIGNMENT_RIGHT))
	row.add_child(_counter_cell(_grouped(total), false,
		HORIZONTAL_ALIGNMENT_RIGHT))
	if expandable:
		var arrow := Button.new()
		arrow.name = "Expand"
		# The glyph turns rather than the label changing, so the control says
		# which way it goes rather than what it is called.
		arrow.text = "v" if _open_counters.has(counter) else ">"
		arrow.custom_minimum_size = Vector2(36, 0)
		arrow.focus_mode = Control.FOCUS_NONE
		arrow.tooltip_text = "What %s is made of" % counter
		arrow.pressed.connect(_on_counter_expanded.bind(counter))
		row.add_child(arrow)
	else:
		# No arrow at all rather than one that opens nothing: an empty
		# breakdown is worse than none, because it looks like a fault.
		row.add_child(_counter_spacer())
	return row

func _counter_detail(detail: Dictionary) -> Control:
	var row := HBoxContainer.new()
	row.name = "Detail"
	var label: Label = _counter_cell("    %s" % str(detail.get("label", "")), true)
	label.modulate = Color(1, 1, 1, 0.7)
	row.add_child(label)
	# A breakdown carries the lifetime tally only. The server keeps no session
	# figure for these, and inventing one here would be the client counting
	# again - which is the mistake the totals themselves were built to end.
	row.add_child(_counter_cell("", false, HORIZONTAL_ALIGNMENT_RIGHT))
	var value: Label = _counter_cell(_grouped(int(detail.get("value", 0))),
		false, HORIZONTAL_ALIGNMENT_RIGHT)
	value.modulate = Color(1, 1, 1, 0.7)
	row.add_child(value)
	row.add_child(_counter_spacer())
	return row

func _on_counter_expanded(counter: String) -> void:
	if _open_counters.has(counter):
		_open_counters.erase(counter)
	else:
		_open_counters[counter] = true
	_sync_counters()

static func _counter_cell(text: String, grow: bool,
		alignment: int = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var label := Label.new()
	label.text = text
	label.horizontal_alignment = alignment
	if grow:
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	else:
		label.custom_minimum_size = Vector2(120, 0)
	return label

static func _counter_spacer() -> Control:
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(36, 0)
	return spacer

## This page's achievements: what each is working towards, how far along, and
## a tick when there is nothing left of it to do.
func _counter_achievements(page: String) -> Control:
	var rows: Array = AppState.counter_layout.get("achievements", []) as Array
	var mine: Array[Dictionary] = []
	for raw: Variant in rows:
		var row: Dictionary = raw as Dictionary
		if str(row.get("category", "")) == page:
			mine.append(row)
	if mine.is_empty():
		return null
	var box := VBoxContainer.new()
	box.name = "Achievements"
	var title := Label.new()
	title.name = "Title"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.text = "%s Achievements" % page
	box.add_child(title)
	for row: Dictionary in mine:
		var line := HBoxContainer.new()
		line.name = "Achievement"
		line.add_child(_counter_cell(str(row.get("title", "")), true))
		var bar := ProgressBar.new()
		bar.name = "Progress"
		bar.custom_minimum_size = Vector2(220, 14)
		bar.show_percentage = false
		bar.max_value = maxf(1.0, float(row.get("target", 1)))
		bar.value = float(row.get("progress", 0))
		line.add_child(bar)
		line.add_child(_counter_cell("%s / %s" % [
			_grouped(int(row.get("progress", 0))),
			_grouped(int(row.get("target", 1)))], false,
			HORIZONTAL_ALIGNMENT_RIGHT))
		var tick := Label.new()
		tick.name = "Done"
		tick.custom_minimum_size = Vector2(36, 0)
		tick.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		# A tick only where the whole ladder is finished. A bar that filled
		# and emptied into the next rung is progress, not completion.
		tick.text = "✓" if bool(row.get("done", false)) else ""
		line.add_child(tick)
		box.add_child(line)
	return box


## Reading progress. `researching` is the knowledge index the character has
## open, 1024 meaning none; `research_completed` and `research_total` are pages.
## All three were decoded into the statistics slice and read by nothing, so a
## player researching a book had no way to see how far through it they were.
## What the server says is being read, as statistics-table rows. The title can
## be long, so it gets a row of its own rather than being squeezed into the
## value column beside the page count.
## What is being read, as (label, value) pairs for the statistics column.
## `_research_rows` says the same thing in bbcode for the places that still
## draw text; both read the same three fields, and neither invents a number.
func _research_lines(stats: Dictionary) -> Array[Array]:
	var index: int = int(stats.get("researching", 1024))
	var total: int = int(stats.get("research_total", 0))
	if index >= 1024 or total <= 0:
		return [["Researching", "nothing"]]
	var completed: int = clampi(int(stats.get("research_completed", 0)), 0, total)
	var title: String = (knowledge_catalog[index]
		if index >= 0 and index < knowledge_catalog.size()
		else "knowledge #%d" % index)
	return [["Researching", "%d%%" % roundi(
			100.0 * float(completed) / float(total))],
		["  " + title, "%d/%d pages" % [completed, total]]]

func _research_rows(stats: Dictionary) -> Array[String]:
	var index: int = int(stats.get("researching", 1024))
	var total: int = int(stats.get("research_total", 0))
	if index >= 1024 or total <= 0:
		return [_stat_row("Researching", "nothing")]
	var completed: int = clampi(int(stats.get("research_completed", 0)), 0, total)
	var title: String = (knowledge_catalog[index]
		if index >= 0 and index < knowledge_catalog.size() else "knowledge #%d" % index)
	return [_stat_row("Researching", "%d%%" % roundi(
			100.0 * float(completed) / float(total))),
		_stat_row("  " + title, "%d/%d pages" % [completed, total])]

func _sync_experience_meter(stats: Dictionary) -> void:
	var skill: String = _selected_experience_skill
	var current_experience: int = _experience_total(skill, stats)
	var next_experience: int = int(stats.get(skill + "_exp_next", 0))
	var level: int = _experience_level_for_skill(skill, stats)
	var capped: bool = _skill_is_capped(skill, stats)
	var level_floor: int = _experience_floor_for_level(level)
	if next_experience <= level_floor:
		level_floor = 0
	var progress_maximum: int = 1 if capped else maxi(1, next_experience - level_floor)
	var progress_value: int = progress_maximum if capped else clampi(
		current_experience - level_floor, 0, progress_maximum)
	experience_bottom.max_value = progress_maximum
	experience_bottom.value = progress_value
	# Eternal Lands writes the experience still to go left of the bar and the
	# watched skill's name at its right end; the full pair lives in the tooltip.
	experience_bottom_text.text = "Max level" if capped else _grouped(
		maxi(0, next_experience - current_experience))
	experience_skill_label.text = skill.capitalize()
	var experience_tooltip: String = "%s experience: %s" % [skill.capitalize(),
		_experience_text(skill, stats)]
	experience_bottom_text.tooltip_text = experience_tooltip
	experience_bottom.tooltip_text = experience_tooltip
	experience_skill_label.tooltip_text = experience_tooltip

static func _experience_floor_for_level(level: int) -> int:
	return ExperienceCurve.for_level(level)

static func _experience_level_for_skill(skill: String, stats: Dictionary) -> int:
	if skill == "overall":
		return int(stats.get("overall_level", stats.get("overall_base", 0)))
	return int(stats.get(skill + "_base", stats.get(skill, 0)))

static func _skill_is_capped(skill: String, stats: Dictionary) -> bool:
	return _experience_level_for_skill(skill, stats) >= ExperienceCurve.max_level_for(skill)

## The rail's side stats list, built the way Eternal Lands draws it: one thin
## row per skill, a green fill behind the text showing how far through the
## level the skill is, the watched skill's name in the GUI gold. Clicking a row
## watches that skill on the bottom experience bar, as the legacy client does.
func _build_skill_rows() -> void:
	for spec: Array in SKILL_ROW_SPECS:
		var key: String = str(spec[1])
		var row := ProgressBar.new()
		row.name = "SkillRow" + key.capitalize()
		# Tall enough for the whole line box, not just the x-height: at twelve
		# pixels the descender of "eng" was sliced off by the row's own frame.
		row.custom_minimum_size = Vector2(0.0, SKILL_ROW_HEIGHT)
		row.max_value = 1.0
		row.show_percentage = false
		row.mouse_filter = Control.MOUSE_FILTER_STOP
		var background := StyleBoxFlat.new()
		background.bg_color = Color(0.02, 0.02, 0.02, 0.6)
		background.border_color = EL_GUI_COLOUR
		background.set_border_width_all(1)
		var fill := StyleBoxFlat.new()
		# The side-stats bar colour hud_misc_window.c uses: a quiet green that
		# stays behind white text without swallowing it.
		fill.bg_color = Color(0.24, 0.40, 0.16, 0.9)
		row.add_theme_stylebox_override("background", background)
		row.add_theme_stylebox_override("fill", fill)
		var name_label := Label.new()
		name_label.name = "Name"
		name_label.text = str(spec[0])
		name_label.add_theme_font_size_override("font_size", 10)
		name_label.add_theme_color_override("font_color", Color.WHITE)
		name_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		name_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		name_label.offset_left = 3.0
		name_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		row.add_child(name_label)
		var value_label := Label.new()
		value_label.name = "Value"
		value_label.text = "0"
		value_label.add_theme_font_size_override("font_size", 10)
		value_label.add_theme_color_override("font_color", Color.WHITE)
		value_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		value_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		value_label.offset_right = -3.0
		value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		value_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		row.add_child(value_label)
		row.gui_input.connect(_on_skill_row_gui_input.bind(key))
		skill_rows.add_child(row)
		_skill_row_nodes[key] = row

func _sync_skill_rows(stats: Dictionary) -> void:
	for spec: Array in SKILL_ROW_SPECS:
		var key: String = str(spec[1])
		var row_value: Variant = _skill_row_nodes.get(key)
		if not row_value is ProgressBar:
			continue
		var row: ProgressBar = row_value as ProgressBar
		var level: int = int(stats.get("overall_level", 0)) \
			if key == "overall" else int(stats.get(key, 0))
		(row.get_node("Value") as Label).text = str(level)
		var name_label: Label = row.get_node("Name") as Label
		name_label.add_theme_color_override("font_color",
			EL_GUI_BRIGHT_COLOUR if key == _selected_experience_skill else Color.WHITE)
		var current_experience: int = _experience_total(key, stats)
		var next_experience: int = int(stats.get(key + "_exp_next", 0))
		var base_level: int = _experience_level_for_skill(key, stats)
		var capped: bool = _skill_is_capped(key, stats)
		var level_floor: int = _experience_floor_for_level(base_level)
		if next_experience <= level_floor:
			level_floor = 0
		var span: int = maxi(1, next_experience - level_floor)
		row.value = 1.0 if capped else clampf(
			float(current_experience - level_floor) / float(span), 0.0, 1.0)
		row.tooltip_text = ("%s %d - Max level\n%s XP earned" % [key.capitalize(), level,
			_grouped(current_experience)] if capped else "%s %d - %s experience to go" % [
			key.capitalize(), level, _grouped(maxi(0, next_experience - current_experience))])
		row.tooltip_text += "\nClick to watch this skill on the experience bar"

func _on_skill_row_gui_input(event: InputEvent, key: String) -> void:
	if not (event is InputEventMouseButton
			and (event as InputEventMouseButton).pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	_selected_experience_skill = key
	_sync_experience_meter(AppState.stats)
	_sync_skill_rows(AppState.stats)
	_save_hud_layout()

## The Eternal Lands indicator letters at the bottom right: lit letters are
## states the server has actually stated this session; letters the fork has no
## signal for stay at the "unavailable" shade instead of guessing.
func _build_hud_indicators() -> void:
	for spec: Array in HUD_INDICATORS:
		var letter := Label.new()
		letter.name = "Indicator" + str(spec[0])
		letter.text = str(spec[0])
		letter.custom_minimum_size = Vector2(14.0, 0.0)
		letter.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		letter.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		letter.add_theme_font_size_override("font_size", 14)
		letter.add_theme_color_override("font_color", INDICATOR_INACTIVE_COLOUR)
		letter.mouse_filter = Control.MOUSE_FILTER_STOP
		letter.gui_input.connect(_on_indicator_gui_input.bind(str(spec[0])))
		hud_indicators.add_child(letter)
		_indicator_labels[str(spec[0])] = letter
	_sync_hud_indicators()

func _sync_hud_indicators() -> void:
	if _indicator_labels.is_empty():
		return
	var available: Dictionary = {
		"S": not AppState.almanac.is_empty(),
		"H": true, "P": false, "M": true, "R": true, "G": false, "A": false}
	var active: Dictionary = {
		"S": str(AppState.almanac.get("kind", "ordinary")) != "ordinary",
		"H": bool(AppState.harvest.get("active", false)),
		"P": false,
		"M": _unseen_pm_count > 0,
		"R": _banner_option("ranging_lock"),
		"G": false, "A": false}
	for spec: Array in HUD_INDICATORS:
		var letter_key: String = str(spec[0])
		var letter: Label = _indicator_labels[letter_key] as Label
		var is_available: bool = bool(available.get(letter_key, false))
		var is_active: bool = bool(active.get(letter_key, false))
		var colour: Color = INDICATOR_UNAVAILABLE_COLOUR
		if is_available:
			colour = INDICATOR_ACTIVE_COLOUR if is_active else INDICATOR_INACTIVE_COLOUR
		letter.add_theme_color_override("font_color", colour)
		var described: String = str(spec[1]) if is_active else str(spec[2])
		if letter_key == "M" and _unseen_pm_count > 0:
			described += " [%d]" % _unseen_pm_count
		letter.tooltip_text = described

func _on_indicator_gui_input(event: InputEvent, letter_key: String) -> void:
	if not (event is InputEventMouseButton
			and (event as InputEventMouseButton).pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	match letter_key:
		"S":
			# What Eternal Lands' #day prints: the day in force, from the
			# almanac packet the server already sent.
			if AppState.almanac.is_empty():
				AppState.append_local_message("The server has not stated the day yet.")
			else:
				AppState.append_local_message("Today: %s - %s" % [
					str(AppState.almanac.get("name", "an ordinary day")),
					str(AppState.almanac.get("description", ""))])
				var season := SeasonSky.summary(AppState.almanac.get("season", {}) as Dictionary)
				if not season.is_empty():
					AppState.append_local_message(season)
		"M":
			_unseen_pm_count = 0
			_sync_hud_indicators()

## The countdown/stopwatch line in the rail, as hud_timer.cpp behaves: click
## starts and stops, shift+click swaps mode, middle-click resets, the wheel
## sets the countdown start (Ctrl fine steps, Alt coarse). Green while it
## runs, red while it stands.
func _update_hud_timer() -> void:
	if not _hud_timer_running:
		return
	var now: int = Time.get_ticks_msec()
	if now - _hud_timer_last_tick_msec < 1000:
		return
	_hud_timer_last_tick_msec = now
	if _hud_timer_stopwatch:
		_hud_timer_seconds = mini(_hud_timer_seconds + 1, 9 * 60 + 59)
	else:
		_hud_timer_seconds -= 1
		if _hud_timer_seconds <= 0:
			_hud_timer_seconds = 0
			_hud_timer_running = false
			audio_director.play("ui_close")
	_sync_hud_timer_label()

func _sync_hud_timer_label() -> void:
	hud_timer_label.text = "%s%d:%02d" % [
		"S" if _hud_timer_stopwatch else "C",
		_hud_timer_seconds / 60, _hud_timer_seconds % 60]
	hud_timer_label.add_theme_color_override("font_color",
		Color(0.5, 1.0, 0.5) if _hud_timer_running else Color(1.0, 0.5, 0.5))

func _on_hud_timer_gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton:
		return
	var click: InputEventMouseButton = event as InputEventMouseButton
	if not click.pressed:
		return
	match click.button_index:
		MOUSE_BUTTON_LEFT:
			if click.shift_pressed:
				_hud_timer_stopwatch = not _hud_timer_stopwatch
				_hud_timer_running = false
				_hud_timer_seconds = 0 if _hud_timer_stopwatch \
					else _hud_timer_start_seconds
				_save_hud_settings()
			else:
				if not _hud_timer_stopwatch and _hud_timer_seconds <= 0:
					_hud_timer_seconds = _hud_timer_start_seconds
				_hud_timer_running = not _hud_timer_running
				_hud_timer_last_tick_msec = Time.get_ticks_msec()
		MOUSE_BUTTON_MIDDLE:
			_hud_timer_running = false
			_hud_timer_seconds = 0 if _hud_timer_stopwatch else _hud_timer_start_seconds
		MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN:
			if _hud_timer_stopwatch:
				return
			var step: int = 5
			if click.ctrl_pressed:
				step = 1
			elif click.alt_pressed:
				step = 30
			if click.button_index == MOUSE_BUTTON_WHEEL_DOWN:
				step = -step
			_hud_timer_start_seconds = clampi(
				_hud_timer_start_seconds + step, 0, 9 * 60 + 59)
			if not _hud_timer_running:
				_hud_timer_seconds = _hud_timer_start_seconds
			_save_hud_settings()
		_:
			return
	_sync_hud_timer_label()

## The knowledge bar under the stats list: research progress as the server
## states it in the statistics packet, "Idle" when it states none.
func _sync_knowledge_bar() -> void:
	var stats: Dictionary = AppState.stats
	var index: int = int(stats.get("researching", 1024))
	var total: int = int(stats.get("research_total", 0))
	if index >= 1024 or total <= 0:
		knowledge_bar.value = 0.0
		knowledge_text.text = "Idle"
		knowledge_bar.tooltip_text = "Researching nothing"
		return
	var completed: int = clampi(int(stats.get("research_completed", 0)), 0, total)
	var percent: int = roundi(100.0 * float(completed) / float(total))
	knowledge_bar.value = float(percent)
	knowledge_text.text = "%d%%" % percent
	knowledge_bar.tooltip_text = "Researching %s: %d of %d pages" % [
		(knowledge_catalog[index] if index >= 0 and index < knowledge_catalog.size()
			else "knowledge #%d" % index), completed, total]

func _on_knowledge_bar_gui_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton
			and (event as InputEventMouseButton).pressed
			and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT):
		return
	var stats: Dictionary = AppState.stats
	var index: int = int(stats.get("researching", 1024))
	var total: int = int(stats.get("research_total", 0))
	if index >= 1024 or total <= 0:
		AppState.append_local_message(
			"You are not researching anything for the time being")
		return
	AppState.append_local_message("Researching %s: %d of %d pages" % [
		(knowledge_catalog[index] if index >= 0 and index < knowledge_catalog.size()
			else "knowledge #%d" % index),
		clampi(int(stats.get("research_completed", 0)), 0, total), total])

## Which of the legacy HUD elements are drawn. The switches live on the
## settings window's HUD tab and persist under [hud], the way Eternal Lands
## keeps them in el.ini.
func _apply_hud_element_options() -> void:
	fps_label.visible = bool(_hud_element_options.get("show_fps", true))
	_sync_chat()
	hud_timer_label.visible = bool(_hud_element_options.get("hud_timer", true))
	knowledge_bar.visible = bool(_hud_element_options.get("knowledge_bar", true))
	skill_rows.visible = bool(_hud_element_options.get("side_stats", true))
	hud_indicators.visible = bool(_hud_element_options.get("indicators", true))
	clock_text.visible = bool(_hud_element_options.get("digital_clock", true))
	clock_face.visible = bool(_hud_element_options.get("analog_clock", true))
	_sync_hud_timer_label()
	_sync_knowledge_bar()

func _update_fps_label() -> void:
	if not fps_label.visible:
		return
	var now: int = Time.get_ticks_msec()
	if now < _fps_refresh_msec:
		return
	_fps_refresh_msec = now + 500
	fps_label.text = "FPS: %d" % roundi(Engine.get_frames_per_second())

## Every &"chat" emit is exactly one appended line (the three append sites in
## AppState each emit once), so only the tail needs looking at. Counting by a
## remembered index broke the moment the 1000-line cap started dropping the
## head: the size stops moving while lines keep arriving. Clicking M is the
## acknowledgement that clears the count.
func _count_unseen_private_messages() -> void:
	var lines: Array = AppState.chat_lines
	if lines.is_empty():
		return
	if int((lines[lines.size() - 1] as Dictionary).get("channel", 0)) == 1:
		_unseen_pm_count += 1
		_sync_hud_indicators()

## Eternal Lands writes only the current value, left of the bar, and names the
## attribute on hover; the overhead banner rows keep the full pair. The rail's
## legacy vertical bars pass their own labels through here too, so the format
## is decided once.
static func _set_meter(bar: ProgressBar, label: Label, value: int,
		maximum: int, title: String) -> void:
	bar.max_value = maxi(1, maximum)
	bar.value = clampi(value, 0, maxi(1, maximum))
	label.text = str(value)
	var described: String = "%s: %d / %d" % [title, value, maximum]
	label.tooltip_text = described
	bar.tooltip_text = described

func _set_overhead_meter(row: HBoxContainer, value: int, maximum: int,
		colour_kind: String) -> void:
	var bar: ProgressBar = row.get_node("Bar") as ProgressBar
	var label: Label = row.get_node("Number") as Label
	var safe_maximum: int = maxi(1, maximum)
	bar.max_value = safe_maximum
	bar.value = clampi(value, 0, safe_maximum)
	label.text = "%d/%d" % [value, maximum]
	var colour: Color = _banner_item_color(colour_kind, _banner_colour(colour_kind,
		float(value) / float(safe_maximum)))
	_paint_banner_row(row, colour)

static func _paint_banner_row(row: HBoxContainer, colour: Color) -> void:
	var bar := row.get_node("Bar") as ProgressBar
	var label := row.get_node("Number") as Label
	var fill: StyleBoxFlat = bar.get_theme_stylebox("fill") as StyleBoxFlat
	if fill != null:
		fill.bg_color = colour
	label.add_theme_color_override("font_color", colour)

## Eternal Lands recolours a banner meter as it drains rather than fixing one
## colour per stat: actors.c set_health_color() ramps green to red, and
## set_banner_colour_general() walks ether and food between the named
## banner.*.zero and banner.*.full colours. Action points are Eloria's own, so
## they follow the same shape between the two ends of the HUD purple.
static func _banner_colour(kind: String, percent: float) -> Color:
	var fraction: float = clampf(percent, 0.0, 1.0)
	match kind:
		"health":
			return Color(clampf((1.0 - fraction) * 2.0, 0.0, 1.0),
				clampf(fraction / 1.25 * 2.0, 0.0, 1.0), 0.0)
		"ether":
			return Color(0.7, 0.7, 1.0).lerp(Color(0.4, 0.4, 1.0), fraction)
		"food":
			return Color(1.0, 0.5, 0.0).lerp(Color(1.0, 1.0, 0.0), fraction)
		"load":
			return Color("c49c72")
	return Color(1.0, 0.55, 0.9).lerp(Color(0.73, 0.28, 0.86), fraction)

func _update_legacy_clock_and_compass() -> void:
	# Carried forward at the pace the server's minutes actually arrive (an
	# invasion master's #speed changes it), a real minute each until two have
	# been seen, and never on into a minute the server has not stated.
	var through_minute := 0.0
	if AppState.game_minute_anchor_msec > 0:
		var interval_msec: int = AppState.game_minute_interval_msec
		if interval_msec <= 0:
			interval_msec = 60000
		through_minute = clampf(
			float(Time.get_ticks_msec() - AppState.game_minute_anchor_msec)
				/ float(interval_msec), 0.0, 59.0 / 60.0)
	var minute_fraction: float = fmod(float(AppState.game_minute) + through_minute, 360.0)
	var display_minute: int = floori(minute_fraction)
	# Eternal Lands' digital clock is H:MM, with seconds behind an option; its
	# analog dial is the whole 360-minute day - one degree per game minute - so
	# the sun-and-moon face reads as day and night.
	if bool(_hud_element_options.get("show_game_seconds", true)):
		var display_game_second: int = floori(fmod(minute_fraction, 1.0) * 60.0)
		clock_text.text = "%d:%02d:%02d" % [display_minute / 60,
			display_minute % 60, display_game_second]
	else:
		clock_text.text = "%d:%02d" % [display_minute / 60, display_minute % 60]
	clock_hand.rotation = deg_to_rad(minute_fraction)
	compass_needle.rotation = deg_to_rad(-camera_rig.yaw_degrees)

func _update_actor_resource_overlay() -> void:
	_sync_local_status_icons()
	if full_map.visible or console_panel.visible or not _banner_has_content():
		if actor_resource_overlay.visible:
			actor_resource_overlay.hide()
		return
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if not actor_value is Node3D or not is_instance_valid(actor_value as Node3D):
		actor_resource_overlay.hide()
		return
	var world_position: Vector3 = _above_head(actor_value as Node3D)
	if gameplay_camera.is_position_behind(world_position):
		actor_resource_overlay.hide()
		return
	var viewport_position: Vector2 = gameplay_camera.unproject_position(world_position)
	var viewport_scale := Vector2.ONE
	if main_viewport.size.x > 0 and main_viewport.size.y > 0:
		viewport_scale = viewport_container.size / Vector2(main_viewport.size)
	var screen_position: Vector2 = viewport_container.position + viewport_position * viewport_scale
	# Instance mode lifts your own banner clear of the melee so it stays legible
	# in a crowd, the way EL raises it by instance_mode_banner_height lines.
	var instance_lift: float = (BANNER_INSTANCE_LIFT_ROWS * _banner_row_height()
		if _banner_option("instance_mode") else 0.0)
	var overlay_position: Vector2 = screen_position - Vector2(
		actor_resource_overlay.size.x * 0.5,
		actor_resource_overlay.size.y + 8.0 + instance_lift)
	actor_resource_overlay.position = Vector2(
		clampf(overlay_position.x, 4.0,
			maxf(4.0, game_view.size.x - actor_resource_overlay.size.x - 90.0)),
		clampf(overlay_position.y, 34.0,
			maxf(34.0, game_view.size.y - actor_resource_overlay.size.y - 86.0)))
	actor_resource_overlay.show()

## Just over an actor's head, where your own banner and the experience that
## floats up out of it are hung: from the top of the body rather than a fixed
## height over the feet, which left a head's height of empty air above a
## human-sized player. Mounted actors use a fixed height above the seat so
## the banner does not bounce with the rider's animation.
func _above_head(actor_node: Node3D) -> Vector3:
	var head: float = (float(actor_node.call("banner_head_height"))
		if actor_node.has_method("banner_head_height") else 2.8 - BANNER_HEAD_CLEARANCE)
	return actor_node.global_position + Vector3(0.0, head + BANNER_HEAD_CLEARANCE, 0.0)

func _sync_local_status_icons() -> void:
	var dto: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	var next: Array[String] = StatusEffectIcons.known(dto.get("status_effects", dto.get("negative_statuses", [])))
	if not _nameplates_enabled or int(dto.get("health", 0)) <= 0:
		next.clear()
	if next == _local_status_effects:
		return
	_local_status_effects = next
	if not is_instance_valid(local_status_grid):
		local_status_grid = GridContainer.new()
		local_status_grid.name = "LocalStatusIcons"
		local_status_grid.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		local_status_grid.add_theme_constant_override("h_separation", int(StatusEffectIcons.GAP))
		local_status_grid.add_theme_constant_override("v_separation", int(StatusEffectIcons.GAP))
		var rows := actor_resource_overlay.get_node("Rows")
		rows.add_child(local_status_grid)
		rows.move_child(local_status_grid, 0)
	for child: Node in local_status_grid.get_children():
		local_status_grid.remove_child(child)
		child.queue_free()
	local_status_grid.columns = maxi(1, mini(StatusEffectIcons.COLUMNS, next.size()))
	local_status_grid.visible = not next.is_empty()
	for effect: String in next:
		var icon := TextureRect.new()
		icon.name = effect
		icon.custom_minimum_size = Vector2.ONE * StatusEffectIcons.SIZE
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.texture = StatusEffectIcons.TEXTURES[effect]
		icon.tooltip_text = effect.replace("expose_", "Weakness: ").replace("_", " ").capitalize()
		icon.mouse_filter = Control.MOUSE_FILTER_PASS
		local_status_grid.add_child(icon)

func _banner_has_content() -> bool:
	if mount_status.wants_banner():
		return true
	if not _local_status_effects.is_empty():
		return true
	if _banner_option("show_names"):
		return true
	for row_spec: Array in BANNER_ROWS:
		if _banner_option(str(row_spec[1])) or _banner_option(str(row_spec[2])):
			return true
	return false

func _banner_row_height() -> float:
	return maxf(1.0, _banner_row("HealthRow").get_combined_minimum_size().y)

## Draws the arrow the server said was loosed. The shot is already resolved -
## the damage arrives in its own packet - so this decides nothing, and an
## actor the client has not been told about is not guessed at.
func _on_missile_fired(shot: Dictionary) -> void:
	var source := actor_nodes.get(int(shot.get("source_actor_id", -1))) as ReplicatedActor3D
	var release_origin: Variant = null
	if is_instance_valid(source):
		release_origin = source.ranged_release_origin()
		source.set_combat_effects_enabled(_effects_enabled)
		source.play_action(&"ranged_attack", true)
	if not _effects_enabled:
		return
	var from_value: Variant = _actor_effect_position(
		int(shot.get("source_actor_id", -1)))
	var to_value: Variant = _actor_effect_position(
		int(shot.get("target_actor_id", -1)))
	if not from_value is Vector3 or not to_value is Vector3:
		return
	if not _admit_effect(&"missile", [int(shot.get("source_actor_id", -1)),
			int(shot.get("target_actor_id", -1))]):
		return
	var missile := MissileFlight3D.new()
	world_root.add_child(missile)
	missile.configure(from_value as Vector3, to_value as Vector3, release_origin)
	_track_effect(missile, &"missile")

## Objects the server put into this map after it loaded. Everything the client
## knew about a map used to arrive with the map, so nothing could change while
## anybody was looking at it.
func _sync_placed_objects() -> void:
	for raw_id: Variant in AppState.world_objects:
		var object_id: int = int(raw_id)
		if placed_object_nodes.has(object_id):
			continue
		var placed: Dictionary = AppState.world_objects[object_id] as Dictionary
		var node := PlacedObject3D.new()
		world_root.add_child(node)
		node.configure(placed, adapter.tile_center(
			int(placed.get("x", 0)), int(placed.get("y", 0))))
		placed_object_nodes[object_id] = node
	for object_id: Variant in placed_object_nodes.keys():
		if AppState.world_objects.has(object_id):
			continue
		var stale: Variant = placed_object_nodes[object_id]
		if is_instance_valid(stale):
			(stale as Node).queue_free()
		placed_object_nodes.erase(object_id)

## Somebody arrived or left by a portal. The actor packets already say who
## moved; this says where the two ends were, which is the part a client cannot
## work out - by the time it hears about an arrival the departure has gone.
func _on_teleport_seen(teleport: Dictionary) -> void:
	if not _effects_enabled:
		return
	var at: Vector3 = adapter.tile_center(int(teleport.get("x", 0)),
		int(teleport.get("y", 0)))
	if not _admit_effect(&"spell", [], at):
		return
	var effect := WorldEffect3D.new()
	world_root.add_child(effect)
	# 1 is the beneficial class, which rises; 0 falls. Arriving rises out of
	# the ground and leaving sinks into it.
	effect.configure(1 if bool(teleport.get("arriving", true)) else 0, at)
	_track_effect(effect, &"spell")

## The sky the server said is over this map. Nothing here decides anything:
## what is falling and how hard is on the wire, because two players standing
## together have to see the same sky.
func _sync_weather() -> void:
	if weather_layer == null:
		return
	# The particle switch turns the drops off, not the weather: the sky still
	# greys under rain the player has chosen not to draw. The first sky after
	# logging in is already there; every change after it eases in, a new
	# map's included, so walking across a border into rain darkens the sky
	# over a few steps rather than at the line. A weather_state_v1 server says
	# how long the change takes (counted from when its frame arrived); a
	# legacy one does not, and its change eases over LEGACY_EASE_SECONDS.
	var first := not _weather_synced
	_weather_synced = true
	var map := str(AppState.current_map)
	var crossed := not first and map != _weather_map
	_weather_map = map
	var state: Dictionary = AppState.weather_state
	if not state.is_empty():
		var left := maxf(0.0, float(state.seconds)
			- float(Time.get_ticks_msec() - int(state.at_msec)) / 1000.0)
		if crossed:
			left = maxf(left, Weather3D.CROSSING_EASE_SECONDS)
		weather_layer.set_state(state.current, state.target, left, _effects_enabled,
			first, str(state.name))
	else:
		weather_layer.set_weather(int(AppState.weather.get("kind", 0)),
			int(AppState.weather.get("intensity", 0)), _effects_enabled, not first)
	if first:
		_apply_day_night()

## The fires burning on this map, placed by tile. A fire the server removes
## goes out; one it has not mentioned was never lit.
func _sync_fires() -> void:
	if weather_layer == null:
		return
	for tile: Variant in AppState.fires:
		var fire_tile: Vector2i = tile as Vector2i
		if not weather_layer.has_fire_at(fire_tile):
			weather_layer.place_fire(
				adapter.tile_center(fire_tile.x, fire_tile.y),
				int(AppState.fires[fire_tile]), fire_tile)
	for tile: Variant in weather_layer.fire_tiles():
		if not AppState.fires.has(tile):
			weather_layer.remove_fire(tile as Vector2i)

func _on_thunder_struck(severity: int) -> void:
	if weather_layer != null and _effects_enabled:
		weather_layer.strike(severity)
	audio_director.play("world_effect")

## An arrow on its way to a tile rather than into an actor: a practice shot,
## or a miss.
##
## A miss used to be drawn as a shot at the target it missed, which is the one
## thing it was not - so every miss looked like a hit. The tile is the server's
## decision, arriving on the wire, so two clients watching one shot draw the
## same arrow instead of each inventing a scatter.
func _on_ground_missile_fired(shot: Dictionary) -> void:
	var source := actor_nodes.get(int(shot.get("source_actor_id", -1))) as ReplicatedActor3D
	var release_origin: Variant = null
	if is_instance_valid(source):
		release_origin = source.ranged_release_origin()
		source.set_combat_effects_enabled(_effects_enabled)
		source.play_action(&"ranged_attack", true)
	if not _effects_enabled:
		return
	var from_value: Variant = _actor_effect_position(
		int(shot.get("source_actor_id", -1)))
	if not from_value is Vector3:
		return
	var landing: Vector3 = adapter.tile_center(
		int(shot.get("x", 0)), int(shot.get("y", 0)))
	if not _admit_effect(&"missile", [int(shot.get("source_actor_id", -1))]):
		return
	var missile := MissileFlight3D.new()
	world_root.add_child(missile)
	missile.configure(from_value as Vector3, landing, release_origin, true)
	_track_effect(missile, &"missile")

## Draws what the server said just happened, where it happened.
##
## Nothing is inferred about the effect: an actor the client has never been
## told about has no position, so nothing is drawn for it rather than a guess
## at the middle of the map.
func _on_special_effect_requested(effect: Dictionary) -> void:
	var source := actor_nodes.get(int(effect.get("actor_id", -1))) as ReplicatedActor3D
	var action := SpellPresentation.action_for_effect(int(effect.get("effect", -1)))
	if is_instance_valid(source) and not action.is_empty():
		source.set_combat_effects_enabled(_effects_enabled)
		source.set_spell_variant(int(effect.get("effect", -1)))
		source.play_action(action, effect.has("release_delay"))
	var origin_value: Variant = _actor_effect_position(int(effect.get("actor_id", -1)))
	if not origin_value is Vector3:
		return
	var target_value: Variant = _actor_effect_position(int(effect.get("target_id", -1)))
	if not _effects_enabled:
		return
	if not _admit_effect(&"spell", [int(effect.get("actor_id", -1)),
			int(effect.get("target_id", -1))]):
		return
	var world_effect := WorldEffect3D.new()
	world_root.add_child(world_effect)
	world_effect.configure(int(effect.get("effect", -1)),
		origin_value as Vector3, target_value, int(effect.get("power", 1)))
	world_effect.bind_actors(source,
		actor_nodes.get(int(effect.get("target_id", -1))) as Node3D)
	if effect.has("release_delay"):
		world_effect.configure_timing(float(effect.release_delay), float(effect.get("flight_duration", 0.0)))
	_track_effect(world_effect, &"spell")

## The server asked an actor to play a named action. An action this client has
## no clip for plays nothing: `play_action` looks the name up in the animation
## map and returns if it finds nothing, so an unknown action is ignored rather
## than guessed at. The words that came with an emote arrive as chat either
## way, so nothing is lost by staying still.
func _on_actor_animation_requested(animation: Dictionary) -> void:
	var node: Variant = actor_nodes.get(int(animation.get("actor_id", -1)))
	if not is_instance_valid(node):
		return
	if str(animation.get("action", "")) == "cast_exit" and (node as ReplicatedActor3D).current_action not in [&"cast_channel", &"cast_channel_enter"]:
		return
	(node as ReplicatedActor3D).set_combat_effects_enabled(_effects_enabled)
	if animation.has("visual_effect"):
		(node as ReplicatedActor3D).set_spell_variant(int(animation.visual_effect))
	(node as ReplicatedActor3D).play_action(
		StringName(str(animation.get("action", ""))))
	if animation.has("power") and (node as ReplicatedActor3D).combat_presentation != null:
		(node as ReplicatedActor3D).combat_presentation.set_spell_power(int(animation.power))

func _actor_effect_position(actor_id: int) -> Variant:
	if actor_id < 0:
		return null
	var node: Variant = actor_nodes.get(actor_id)
	if not is_instance_valid(node):
		return null
	return (node as Node3D).global_position

## Whether a combat visual of `kind` between these actors, or at `at`, is drawn
## (live_effect_budget.gd). One involving the player, their target or their
## selection always is. One whose actors are all beyond the draw distance is
## not, since none of their bodies is drawn there either; the rest are drawn
## while the budget has room.
func _admit_effect(kind: StringName, actor_ids: Array, at := Vector3.INF) -> bool:
	if not crowd.effects:
		return true
	var priority := false
	var seen := false
	for raw_id: Variant in actor_ids:
		var id: int = int(raw_id)
		if id < 0:
			continue
		priority = priority or _crowd_priority_actor(id)
		var node: Variant = actor_nodes.get(id)
		seen = seen or (is_instance_valid(node) and (node as ReplicatedActor3D).is_drawn())
	if at.is_finite():
		# Across the ground only: a tile's centre carries the map's flat
		# fallback height, not the terrain's.
		var reference: Vector3 = _crowd_reference_point()
		seen = seen or Vector2(at.x - reference.x, at.z - reference.z).length() \
			<= ACTOR_DRAW_DISTANCE_METRES
	if not priority and not seen:
		return false
	return effect_budget.admit(kind, priority)

## Keeps a combat visual in `world_effects` and counts it against the budget.
## The list is compacted when it has doubled rather than filtered on every
## append, which walked every live effect for each new one.
func _track_effect(node: Node, kind: StringName) -> void:
	effect_budget.track(node, kind)
	world_effects.append(node)
	if world_effects.size() > _world_effects_compact_at:
		world_effects = world_effects.filter(func(effect: Variant) -> bool:
			return is_instance_valid(effect))
		_world_effects_compact_at = world_effects.size() * 2 + 32

func _on_floating_feedback_requested(feedback: Dictionary) -> void:
	# Gains that land together (a skill plus the overall total, or several stats
	# in one partial stats packet) are collected for the frame so the group can
	# be filtered and stacked instead of every entry spawning on its own.
	_pending_floating_feedback.append(feedback)
	if _floating_feedback_flush_queued:
		return
	_floating_feedback_flush_queued = true
	_flush_floating_feedback.call_deferred()

func _flush_floating_feedback() -> void:
	_floating_feedback_flush_queued = false
	var pending: Array[Dictionary] = _pending_floating_feedback
	_pending_floating_feedback = []
	var merged: Array[Dictionary] = []
	var experience_rows: Dictionary = {}
	for feedback: Dictionary in pending:
		if str(feedback.get("kind", "")) != "experience":
			merged.append(feedback)
			continue
		var key := "%s/%s/%s" % [feedback.get("skill", ""),
			feedback.get("bonus", false), feedback.get("permanent", false)]
		if experience_rows.has(key):
			var row: Dictionary = merged[int(experience_rows[key])]
			row.amount = int(row.get("amount", 0)) + int(feedback.get("amount", 0))
		else:
			experience_rows[key] = merged.size()
			merged.append(feedback.duplicate())
	pending = merged
	var has_skill_experience := false
	for feedback: Dictionary in pending:
		if _is_skill_experience(feedback):
			has_skill_experience = true
			break
	if has_skill_experience:
		_last_skill_experience_msec = Time.get_ticks_msec()
	for feedback: Dictionary in pending:
		# Overall experience is the sum of the skill gains, so repeating it next
		# to the skill that produced it says nothing new. The timestamp covers
		# the case where the server splits the two gains across frames.
		if str(feedback.get("kind", "")) == "experience" \
				and str(feedback.get("skill", "")) == "overall" \
				and not bool(feedback.get("bonus", false)):
			if has_skill_experience:
				continue
			if Time.get_ticks_msec() - _last_skill_experience_msec \
					< FLOATING_FEEDBACK_OVERALL_GRACE_MSEC:
				continue
		_spawn_floating_feedback(feedback)

static func _is_skill_experience(feedback: Dictionary) -> bool:
	return str(feedback.get("kind", "")) == "experience" \
		and str(feedback.get("skill", "")) != "overall" \
		and not bool(feedback.get("bonus", false))

func _spawn_floating_feedback(feedback: Dictionary) -> void:
	if not game_view.visible or AppState.local_actor_id < 0:
		return
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	if not actor_value is Node3D or not is_instance_valid(actor_value as Node3D):
		return
	var world_position: Vector3 = _above_head(actor_value as Node3D)
	if gameplay_camera.is_position_behind(world_position):
		return
	var viewport_position: Vector2 = gameplay_camera.unproject_position(world_position)
	var viewport_scale := Vector2.ONE
	if main_viewport.size.x > 0 and main_viewport.size.y > 0:
		viewport_scale = viewport_container.size / Vector2(main_viewport.size)
	var screen_position: Vector2 = viewport_container.position + viewport_position * viewport_scale
	var kind: String = str(feedback.get("kind", "experience"))
	var skill: String = str(feedback.get("skill", "skill"))
	var label: Label = Label.new()
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 17 if kind == "level" else 14)
	label.add_theme_color_override("font_outline_color", Color(0.015, 0.02, 0.025, 0.98))
	label.add_theme_constant_override("outline_size", 4)
	if kind == "level":
		label.text = "Level %d %s" % [int(feedback.get("level", 0)), skill.capitalize()]
		label.add_theme_color_override("font_color", Color(1.0, 0.78, 0.22, 1.0))
	else:
		label.text = "+%d %s" % [int(feedback.get("amount", 0)), skill.capitalize()]
		label.add_theme_color_override("font_color", Color(0.45, 1.0, 0.38, 1.0))
	_floating_feedback_layer.add_child(label)
	label.reset_size()
	# Out of the top of your own banner, a line clear of the name, or out of
	# the top of your head when the banner is switched off.
	var floor_y: float = ((actor_resource_overlay.position.y
		if actor_resource_overlay.visible else screen_position.y) - label.size.y)
	label.position = Vector2(screen_position.x - label.size.x * 0.5,
		_floating_feedback_row(floor_y - FLOATING_FEEDBACK_ROW_HEIGHT, floor_y))
	_active_floating_labels.append(label)
	var tween: Tween = create_tween().set_parallel(true)
	tween.tween_property(label, "position",
		label.position - Vector2(0.0, FLOATING_FEEDBACK_RISE),
		FLOATING_FEEDBACK_LIFETIME).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.tween_property(label, "modulate:a", 0.0,
		FLOATING_FEEDBACK_LIFETIME - FLOATING_FEEDBACK_FADE_DELAY).set_delay(
		FLOATING_FEEDBACK_FADE_DELAY)
	tween.finished.connect(func() -> void:
		_active_floating_labels.erase(label)
		label.queue_free())

func _floating_feedback_row(preferred_y: float, lowest_y: float) -> float:
	# Messages drift upwards, so a new one takes the first free row at or below
	# the preferred height rather than landing on top of one still on screen -
	# down as far as `lowest_y`, which keeps it off the banner, and upwards
	# from the preferred row once that room is used.
	var occupied: Array[float] = []
	for index: int in range(_active_floating_labels.size() - 1, -1, -1):
		var other: Label = _active_floating_labels[index]
		if is_instance_valid(other):
			occupied.append(other.position.y)
		else:
			_active_floating_labels.remove_at(index)
	var candidates: Array[float] = []
	var row_y: float = preferred_y
	while row_y <= lowest_y:
		candidates.append(row_y)
		row_y += FLOATING_FEEDBACK_ROW_HEIGHT
	for step: int in range(1, FLOATING_FEEDBACK_MAX_ROWS + 1):
		candidates.append(preferred_y - FLOATING_FEEDBACK_ROW_HEIGHT * float(step))
	for candidate: float in candidates:
		var free := true
		for y: float in occupied:
			if absf(y - candidate) < FLOATING_FEEDBACK_ROW_HEIGHT:
				free = false
				break
		if free:
			return candidate
	return candidates[candidates.size() - 1]

func _on_window_size_changed() -> void:
	_fit_hud_action_buttons.call_deferred()
	_fit_stats_window_to_viewport.call_deferred()
	_layout_full_window_views()
	# Match the render viewport to the actual drawable area so resizing changes
	# camera aspect instead of stretching a fixed 16:9 render target. The
	# container reports canvas units, which the content-scale system multiplies
	# onto the screen; rendering at that size would pin the world to the 1280x720
	# design resolution and upscale it, so the scale factor is applied here to
	# render at the window's true pixel size.
	var render_scale: Vector2 = get_viewport().get_final_transform().get_scale()
	var target_size := Vector2i(
		maxi(1, roundi(viewport_container.size.x * maxf(render_scale.x, 0.01))),
		maxi(1, roundi(viewport_container.size.y * maxf(render_scale.y, 0.01))))
	if main_viewport.size != target_size:
		main_viewport.size = target_size
	OldcraftDialogueStyleScript.layout(self)

## Keep all action icons reachable as the bar gains windows or the UI scales.
func _fit_hud_action_buttons() -> void:
	if hud_workspace != null and hud_workspace.manages_layout():
		hud_workspace.queue_layout()
		return
	var available_width := maxf(200, game_view.size.x - right_rail.size.x)
	var meter_bars: Array[ProgressBar] = []
	var meter_fixed := 0.0
	var visible_meters := 0
	for meter: Node in bottom_meters.get_children():
		if not (meter as Control).visible: continue
		visible_meters += 1
		var parts := 0
		for child: Node in meter.get_children():
			if not child is Control or not (child as Control).visible: continue
			parts += 1
			if child is ProgressBar: meter_bars.append(child)
			else: meter_fixed += (child as Control).get_combined_minimum_size().x
		meter_fixed += (meter as Container).get_theme_constant("separation") * maxi(0, parts - 1)
	meter_fixed += bottom_meters.get_theme_constant("separation") * maxi(0, visible_meters - 1)
	var bar_width := floorf(clampf((available_width - 12 - meter_fixed) / maxf(1, meter_bars.size()), 16, 84))
	for bar: ProgressBar in meter_bars:
		bar.custom_minimum_size.x = bar_width
	var row := $GameView/Quickbar/QuickRows/Buttons as HBoxContainer
	var buttons: Array[Button] = []
	var fixed_width := 0.0
	for child: Node in row.get_children():
		if child is Button:
			buttons.append(child)
		elif child is Control:
			fixed_width += (child as Control).get_combined_minimum_size().x
	var width := available_width - fixed_width - 12.0 \
		- row.get_theme_constant("separation") * (row.get_child_count() - 1)
	var cell := floorf(clampf(width / maxf(1, buttons.size()), 20, 44))
	for button: Button in buttons:
		button.custom_minimum_size = Vector2(cell, cell)
		button.add_theme_constant_override("icon_max_width", int(cell - HUD_ICON_PADDING * 2))
	# A prior minimum-width overflow can leave an anchored panel expanded left.
	(%Quickbar as Control).offset_left = 0
	(%Quickbar as Control).offset_right = -right_rail.size.x

func _invasion_monitor_dock_rect() -> Rect2:
	var area := viewport_container.get_global_rect()
	area.end = Vector2(minf(area.end.x, right_rail.get_global_rect().position.x),
		minf(area.end.y, (%Quickbar as Control).get_global_rect().position.y))
	return area


func _layout_full_window_views() -> void:
	# Fill the client canvas independently of movable HUD parts and presets.
	for view: Control in [full_map, console_panel]:
		view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func _sync_hud_button_states(force := false) -> void:
	if _hud_icon_regions.is_empty():
		return
	# Runs every frame. Resolving every unique-name node and formatting a
	# dictionary into a signature string each time allocated for nothing; the
	# buttons are resolved once and the comparison is now a bitmask.
	if _hud_state_buttons.is_empty():
		_hud_state_buttons = [%WalkButton, %MapButton, %SitButton, %AttackButton,
			%TradeButton, %LookButton, %InventoryButton, %StatsButton,
			%KnowledgeButton, %ManufacturingButton, %ChatButton, %DisconnectButton,
			%EncyclopediaButton, %SpellsButton, %EmotesButton, %QuestButton,
			%InfoButton, %BuddyButton, %ConsoleButton, %HelpButton,
			%RangingButton, %MinimapButton, %OptionsButton, %MountsButton, %LeaderboardsButton,
			%ExchangeButton, %StoragePreviewButton]
	var local_actor: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	var sitting: bool = bool(local_actor.get("sitting", false))
	var stats_open: bool = stats_panel.visible
	var stats_tab: int = stats_tabs.current_tab
	var quest_panel_value: Variant = extension_windows.get("quest_panel")
	var states: Array[bool] = [
		_interaction_mode == "walk" and not sitting,
		full_map.visible,
		sitting,
		_interaction_mode == "attack",
		_interaction_mode == "trade" or bool(AppState.trade.get("open", false)),
		_interaction_mode == "look" or bool(AppState.player_info.get("open", false)),
		inventory_panel.visible,
		stats_open and stats_tab != 1,
		stats_open and stats_tab == 1,
		manufacturing_panel.visible,
		chat_input.has_focus(),
		AppState.connection_state == "connected",
		reference_window != null and bool(reference_window.call("is_encyclopedia_open")),
		spells_window != null and bool(spells_window.call("is_open")),
		emotes_window != null and bool(emotes_window.call("is_open")),
		quest_panel_value is Control and (quest_panel_value as Control).visible,
		_reference_tab_open(1),
		_reference_tab_open(5),
		console_panel.visible,
		_reference_tab_open(0),
		ranging_window != null and bool(ranging_window.call("is_open")),
		minimap_frame.visible,
		settings_panel.visible,
		mounts_window != null and bool(mounts_window.call("is_open")),
		leaderboards_window != null and bool(leaderboards_window.call("is_open")),
		extension_windows != null and (extension_windows.get("market_panel") as Control).visible,
		storage_panel.visible]
	# Only while the player has not chosen attack mode from the HUD: a mode
	# they picked stays picked, and Alt must not appear to be what put it there.
	var attack_preview: bool = _alt_attack_preview and _interaction_mode != "attack"
	var mask: int = 0
	for index: int in states.size():
		if states[index]:
			mask |= 1 << index
	if attack_preview:
		mask |= 1 << states.size()
	# Availability rides in the same signature. An icon's colour now follows
	# whether its action can be taken at all, and that changes when the
	# selection changes without any of the states above moving.
	for index: int in _hud_state_buttons.size():
		if not _hud_state_buttons[index].disabled:
			mask |= 1 << (states.size() + 1 + index)
	if not force and mask == _hud_button_state_mask:
		return
	_hud_button_state_mask = mask
	for index: int in _hud_state_buttons.size():
		var button: Button = _hud_state_buttons[index]
		var active: bool = states[index]
		button.set_pressed_no_signal(active)
		# Eternal Lands greys only what it will not let you use. Everything
		# available is drawn in colour whether or not its window is open, and
		# an open window says so with the lit frame its pressed style carries.
		var atlas: Texture2D = (_hud_inactive_atlas if button.disabled
			else _hud_active_atlas)
		# A button the atlas has no art for yet (Techniques) keeps its label.
		if atlas != null and _hud_icon_regions.has(button):
			button.icon = _atlas_region(atlas, _icon_region_for(button, sitting))
	_apply_attack_preview(attack_preview)

## The sit icon is a pair, the way icon_window.cpp's sit/stand multi-icon is:
## seated, it shows the stand icon, because standing is what pressing it does.
func _icon_region_for(button: Button, sitting: bool) -> Rect2:
	if button == sit_button and sitting:
		return STAND_ICON_REGION
	return _hud_icon_regions[button] as Rect2

## The move icon while Alt is held: it wears the attack icon and does what the
## attack icon does, and goes back to itself the moment Alt is let go. Nothing
## about the interaction mode changes, so an attack mode chosen from the HUD is
## untouched by holding Alt or letting it go.
func _apply_attack_preview(previewing: bool) -> void:
	var walk_button: Button = %WalkButton
	if previewing:
		if _hud_active_atlas != null:
			walk_button.icon = _atlas_region(_hud_active_atlas,
				_hud_icon_regions[%AttackButton] as Rect2)
		walk_button.tooltip_text = ("Alt is held: a click attacks what it lands"
			+ " on; clicking empty ground keeps you in place. Let Alt go for walk mode")
	else:
		walk_button.tooltip_text = "Walk mode; hold Shift while clicking to run"

func _build_hud_layout_menu() -> void:
	_floating_feedback_layer = Control.new()
	_floating_feedback_layer.name = "FloatingFeedbackLayer"
	_floating_feedback_layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_floating_feedback_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_floating_feedback_layer.z_index = 18
	game_view.add_child(_floating_feedback_layer)

	var content := VBoxContainer.new()
	content.name = "LowerHudLayout"
	content.add_theme_constant_override("separation", 6)
	settings_window.page_body("HUD").add_child(content)
	var title := Label.new()
	title.text = "LOWER HUD INDICATORS"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	content.add_child(title)
	var help := Label.new()
	help.text = "Select a bar, then reorder or hide it."
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(help)
	_hud_layout_list = ItemList.new()
	_hud_layout_list.custom_minimum_size = Vector2(310.0, 185.0)
	_hud_layout_list.item_selected.connect(_on_hud_layout_item_selected)
	content.add_child(_hud_layout_list)
	var order_actions := HBoxContainer.new()
	var move_up := Button.new()
	move_up.text = "Move up"
	move_up.pressed.connect(_on_hud_layout_move.bind(-1))
	order_actions.add_child(move_up)
	var move_down := Button.new()
	move_down.text = "Move down"
	move_down.pressed.connect(_on_hud_layout_move.bind(1))
	order_actions.add_child(move_down)
	content.add_child(order_actions)
	_hud_layout_visible = CheckButton.new()
	_hud_layout_visible.text = "Show selected indicator"
	_hud_layout_visible.toggled.connect(_on_hud_layout_visibility_toggled)
	content.add_child(_hud_layout_visible)
	var skill_row := HBoxContainer.new()
	var skill_label := Label.new()
	skill_label.text = "Experience skill"
	skill_row.add_child(skill_label)
	_hud_skill_selector = OptionButton.new()
	_hud_skill_selector.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for skill: String in HUD_SKILLS:
		_hud_skill_selector.add_item(skill.capitalize())
		_hud_skill_selector.set_item_metadata(_hud_skill_selector.item_count - 1, skill)
	_hud_skill_selector.item_selected.connect(_on_hud_skill_selected)
	skill_row.add_child(_hud_skill_selector)
	content.add_child(skill_row)

func _connect_hud_context_inputs(control: Control) -> void:
	if not control.gui_input.is_connected(_on_lower_hud_gui_input):
		control.gui_input.connect(_on_lower_hud_gui_input)
	for child: Node in control.get_children():
		if child is Control:
			_connect_hud_context_inputs(child as Control)

func _on_lower_hud_gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse_event: InputEventMouseButton = event as InputEventMouseButton
	if not mouse_event.pressed or mouse_event.button_index != MOUSE_BUTTON_RIGHT:
		return
	_refresh_hud_layout_menu()
	settings_window.open_tab("HUD")
	get_viewport().set_input_as_handled()

func _refresh_hud_layout_menu() -> void:
	var previous_selection: int = 0
	var selected: PackedInt32Array = _hud_layout_list.get_selected_items()
	if not selected.is_empty():
		previous_selection = int(selected[0])
	_hud_layout_list.clear()
	for meter_key: String in _hud_meter_order:
		var index: int = _hud_layout_list.item_count
		_hud_layout_list.add_item(meter_key.capitalize())
		_hud_layout_list.set_item_metadata(index, meter_key)
		_hud_layout_list.set_item_custom_fg_color(index,
			Color(0.91, 0.86, 0.70) if bool(_hud_meter_visible.get(meter_key, true))
			else Color(0.48, 0.48, 0.48))
	if _hud_layout_list.item_count > 0:
		_hud_layout_list.select(clampi(previous_selection, 0,
			_hud_layout_list.item_count - 1))
		_on_hud_layout_item_selected(int(_hud_layout_list.get_selected_items()[0]))
	for option_index: int in range(_hud_skill_selector.item_count):
		if str(_hud_skill_selector.get_item_metadata(option_index)) == _selected_experience_skill:
			_hud_skill_selector.select(option_index)
			break

func _on_hud_layout_item_selected(index: int) -> void:
	if index < 0 or index >= _hud_layout_list.item_count:
		return
	var meter_key: String = str(_hud_layout_list.get_item_metadata(index))
	_hud_layout_visible.set_pressed_no_signal(bool(_hud_meter_visible.get(meter_key, true)))

func _on_hud_layout_move(direction: int) -> void:
	var selected: PackedInt32Array = _hud_layout_list.get_selected_items()
	if selected.is_empty():
		return
	var source: int = int(selected[0])
	var destination: int = clampi(source + direction, 0, _hud_meter_order.size() - 1)
	if source == destination:
		return
	var meter_key: String = _hud_meter_order[source]
	_hud_meter_order.remove_at(source)
	_hud_meter_order.insert(destination, meter_key)
	_apply_hud_meter_layout()
	_refresh_hud_layout_menu()
	_hud_layout_list.select(destination)
	_on_hud_layout_item_selected(destination)
	_save_hud_layout()

func _on_hud_layout_visibility_toggled(enabled: bool) -> void:
	var selected: PackedInt32Array = _hud_layout_list.get_selected_items()
	if selected.is_empty():
		return
	var meter_key: String = str(_hud_layout_list.get_item_metadata(int(selected[0])))
	_hud_meter_visible[meter_key] = enabled
	_apply_hud_meter_layout()
	_refresh_hud_layout_menu()
	_save_hud_layout()

func _on_hud_skill_selected(index: int) -> void:
	if index < 0 or index >= _hud_skill_selector.item_count:
		return
	_selected_experience_skill = str(_hud_skill_selector.get_item_metadata(index))
	_sync_stats()
	_save_hud_layout()

func _meter_node(meter_key: String) -> Control:
	match meter_key:
		"mana": return %ManaMeter
		"food": return %FoodMeter
		"health": return %HealthMeter
		"load": return %LoadMeter
		"action": return %ActionMeter
		"experience": return %ExperienceMeter
		_: return null

func _apply_hud_meter_layout() -> void:
	for index: int in range(_hud_meter_order.size()):
		var meter_key: String = _hud_meter_order[index]
		var meter: Control = _meter_node(meter_key)
		if meter == null:
			continue
		bottom_meters.move_child(meter, index)
		meter.visible = bool(_hud_meter_visible.get(meter_key, true))
	_fit_hud_action_buttons.call_deferred()

func _load_hud_layout() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		var saved_order_value: Variant = config.get_value("lower_hud", "order", _hud_meter_order)
		if saved_order_value is Array:
			var saved_order: Array = saved_order_value as Array
			var validated: Array[String] = []
			for raw_key: Variant in saved_order:
				var key: String = str(raw_key)
				if _hud_meter_order.has(key) and not validated.has(key):
					validated.append(key)
			if validated.size() == _hud_meter_order.size():
				_hud_meter_order = validated
		for meter_key: String in _hud_meter_order:
			_hud_meter_visible[meter_key] = bool(config.get_value(
				"lower_hud", "show_" + meter_key, true))
		var saved_skill: String = str(config.get_value(
			"lower_hud", "experience_skill", _selected_experience_skill))
		if HUD_SKILLS.has(saved_skill):
			_selected_experience_skill = saved_skill
	_apply_hud_meter_layout()

func _save_hud_layout() -> void:
	var config := ConfigFile.new()
	# Preserve settings owned by the minimap/options UI in the same config file.
	config.load(SETTINGS_PATH)
	config.set_value("lower_hud", "order", _hud_meter_order)
	for meter_key: String in _hud_meter_order:
		config.set_value("lower_hud", "show_" + meter_key,
			bool(_hud_meter_visible.get(meter_key, true)))
	config.set_value("lower_hud", "experience_skill", _selected_experience_skill)
	var error: Error = config.save(SETTINGS_PATH)
	if error != OK:
		push_warning("Unable to save lower HUD preferences: " + error_string(error))
	if hud_workspace != null:
		hud_workspace.sync_settings()

## Writes a stack count over a slot at the largest size that still fits it.
static func _set_slot_quantity(label: Label, quantity: int) -> void:
	var text: String = str(quantity)
	label.text = text
	label.add_theme_font_size_override("font_size",
		11 if text.length() <= 4 else (9 if text.length() <= 6 else 8))

func _add_slot_quantity_label(button: Button) -> Label:
	var quantity: Label = Label.new()
	quantity.name = "Quantity"
	quantity.mouse_filter = Control.MOUSE_FILTER_IGNORE
	quantity.anchor_left = 0.0
	quantity.anchor_top = 1.0
	quantity.anchor_right = 1.0
	quantity.anchor_bottom = 1.0
	quantity.offset_left = 2.0
	quantity.offset_top = -17.0
	quantity.offset_right = -3.0
	quantity.offset_bottom = -2.0
	quantity.clip_text = false
	quantity.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	quantity.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	quantity.add_theme_font_size_override("font_size", 11)
	quantity.add_theme_color_override("font_color", Color.WHITE)
	quantity.add_theme_color_override("font_outline_color", Color(0.02, 0.02, 0.02))
	quantity.add_theme_constant_override("outline_size", 3)
	button.add_child(quantity)
	return quantity

func _ground_bag_tooltip(item: Dictionary) -> String:
	var image_id: int = int(item.get("image_id", 0))
	var tooltip: String = "Item image #%d — quantity %d" % [image_id,
		int(item.get("quantity", 0))]
	if item_atlas.uses_substitute(image_id):
		tooltip += "
Independent Rabbit Lands icon substitute for legacy image #%d." % image_id
	return tooltip + ("
Left click picks up the inventory quantity (Ctrl for all);"
		+ " right click asks the server what it is.")

func _build_ground_bag_slots() -> void:
	for index: int in range(GROUND_BAG_SLOT_COUNT):
		var button: Button = Button.new()
		button.custom_minimum_size = Vector2(44.0, 44.0)
		button.expand_icon = true
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.focus_mode = Control.FOCUS_NONE
		button.clip_contents = true
		button.text = ""
		button.tooltip_text = "Empty bag slot"
		button.disabled = true
		button.set_meta("bag_position", -1)
		button.action_mode = BaseButton.ACTION_MODE_BUTTON_PRESS
		button.pressed.connect(_on_ground_bag_slot_pressed.bind(index))
		button.gui_input.connect(_on_ground_bag_slot_gui_input.bind(index))
		ground_bag_grid.add_child(button)
		ground_bag_slot_buttons.append(button)
		ground_bag_quantity_labels.append(_add_slot_quantity_label(button))

func _fill_ground_bag_grid(items: Dictionary) -> void:
	var positions: Array = items.keys()
	positions.sort()
	var index := 0
	for raw_position: Variant in positions:
		if index >= ground_bag_slot_buttons.size():
			break
		var item_value: Variant = items.get(raw_position)
		if not item_value is Dictionary:
			continue
		var item: Dictionary = item_value as Dictionary
		var button: Button = ground_bag_slot_buttons[index]
		button.set_meta("bag_position", int(raw_position))
		button.icon = item_atlas.icon_for(int(item.get("image_id", 0)))
		button.disabled = false
		button.tooltip_text = _ground_bag_tooltip(item)
		ground_bag_quantity_labels[index].text = str(int(item.get("quantity", 0)))
		index += 1
	if index >= ground_bag_slot_buttons.size() and positions.size() > index:
		push_warning("Ground bag holds more stacks than the grid can show: %d of %d"
			% [index, positions.size()])
	for empty_index: int in range(index, ground_bag_slot_buttons.size()):
		var empty_button: Button = ground_bag_slot_buttons[empty_index]
		empty_button.set_meta("bag_position", -1)
		empty_button.icon = null
		empty_button.disabled = true
		empty_button.tooltip_text = "Empty bag slot"
		ground_bag_quantity_labels[empty_index].text = ""

func _build_inventory_slots() -> void:
	for slot: int in range(36):
		var button: Button = Button.new()
		button.custom_minimum_size = Vector2(44.0, 44.0)
		button.expand_icon = true
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.focus_mode = Control.FOCUS_NONE
		button.clip_contents = true
		button.text = ""
		button.tooltip_text = "Empty inventory slot %d" % (slot + 1)
		button.disabled = true
		# Item slots act on the press, as Eternal Lands does: waiting for the
		# release lost every click whose release slid onto the next slot.
		# A double-click is still taken by the gui_input handler, which runs
		# before the button sees the press.
		button.action_mode = BaseButton.ACTION_MODE_BUTTON_PRESS
		button.pressed.connect(_on_inventory_slot_pressed.bind(slot))
		button.gui_input.connect(_on_inventory_slot_gui_input.bind(slot))
		inventory_grid.add_child(button)
		inventory_slot_buttons.append(button)
		inventory_quantity_labels.append(_add_slot_quantity_label(button))

func _build_equipment_slots() -> void:
	for index: int in range(8):
		var button: Button = Button.new()
		button.custom_minimum_size = Vector2(44.0, 44.0)
		button.expand_icon = true
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.focus_mode = Control.FOCUS_NONE
		button.text = ""
		button.tooltip_text = "Generic legacy equipment position %d" % (index + 1)
		button.disabled = true
		button.action_mode = BaseButton.ACTION_MODE_BUTTON_PRESS
		button.pressed.connect(_on_equipment_slot_pressed.bind(36 + index))
		button.gui_input.connect(_on_inventory_slot_gui_input.bind(36 + index))
		equipment_grid.add_child(button)
		equipment_slot_buttons.append(button)

func _bind_quick_slots() -> void:
	var slot: int = 0
	for child: Node in quick_slot_container.get_children():
		if child is Button:
			var button: Button = child as Button
			button.focus_mode = Control.FOCUS_NONE
			button.action_mode = BaseButton.ACTION_MODE_BUTTON_PRESS
			button.pressed.connect(_on_quick_slot_pressed.bind(slot))
			button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			button.expand_icon = true
			button.text = ""
			var shortcut := Label.new()
			shortcut.name = "Shortcut"
			shortcut.text = str(slot + 1)
			shortcut.mouse_filter = Control.MOUSE_FILTER_IGNORE
			shortcut.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			shortcut.add_theme_font_size_override("font_size", 8)
			button.add_child(shortcut)
			shortcut.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
			shortcut.offset_top = 1.0
			shortcut.offset_bottom = 12.0
			quick_slot_buttons.append(button)
			slot += 1

func _bind_spell_slots() -> void:
	var slot := 0
	for child: Node in spell_slot_container.get_children():
		if child is Button:
			var button: Button = child as Button
			button.focus_mode = Control.FOCUS_NONE
			button.pressed.connect(_cast_spell_slot.bind(slot))
			spell_slot_buttons.append(button)
			slot += 1
	_sync_spells()

func _sync_inventory() -> void:
	inventory_load.text = "Load: %d / %d" % [int(AppState.stats.get("carried", 0)),
		int(AppState.stats.get("capacity", 0))]
	for slot: int in range(inventory_slot_buttons.size()):
		var button: Button = inventory_slot_buttons[slot]
		var item_value: Variant = AppState.inventory.get(slot)
		if item_value is Dictionary:
			var item: Dictionary = item_value as Dictionary
			var image_id: int = int(item.get("image_id", 0))
			button.icon = _slot_icon(image_id, slot)
			if classic_storage != null:
				button.icon = classic_storage.crop_icon(button.icon)
			button.text = ""
			_set_slot_quantity(inventory_quantity_labels[slot],
				int(item.get("quantity", 0)))
			button.tooltip_text = _inventory_tooltip(item, slot)
			button.disabled = false
		else:
			button.icon = null
			button.text = ""
			inventory_quantity_labels[slot].text = ""
			# Only an item in hand goes anywhere: a selection is not a carry,
			# and an empty slot used to pull the last selected item across.
			if _carried_slot >= 0:
				button.tooltip_text = "Put the carried item in slot %d" % (slot + 1)
			elif _storage_carried_position >= 0:
				button.tooltip_text = "Withdraw the carried stored item"
			else:
				button.tooltip_text = "Empty inventory slot %d" % (slot + 1)
			# An empty slot stays enabled so that its frame is drawn. Godot
			# renders a disabled button flat, which made the grid vanish
			# whenever nothing was selected: the slots are the shape of the
			# window and belong on screen whether or not they hold anything.
			# Pressing an empty one with nothing in hand does nothing.
			button.disabled = false
	_sync_equipment_slots()
	_sync_quick_slots()
	if selected_inventory_slot >= 0:
		var selected_value: Variant = AppState.inventory.get(selected_inventory_slot)
		if selected_value is Dictionary:
			var selected_item: Dictionary = selected_value as Dictionary
			inventory_use_button.tooltip_text = ("Left click uses the item"
				if bool(selected_item.get("inventory_usable", false))
				and _inventory_cooldown_remaining(selected_inventory_slot) <= 0
				else "The selected item cannot be used right now")
		else:
			selected_inventory_slot = -1
	if not AppState.inventory_text.is_empty():
		inventory_description.text = AppState.inventory_text
	elif selected_inventory_slot >= 0 and AppState.inventory.has(selected_inventory_slot):
		inventory_description.text = _inventory_tooltip(
			AppState.inventory[selected_inventory_slot], selected_inventory_slot)
	else:
		inventory_description.text = "Select an item to inspect it."
	if ground_bag_panel.visible:
		_sync_ground_bag_actions()

func _sync_equipment_slots() -> void:
	for index: int in range(equipment_slot_buttons.size()):
		var slot: int = 36 + index
		var button: Button = equipment_slot_buttons[index]
		var item_value: Variant = AppState.inventory.get(slot)
		if item_value is Dictionary:
			var item: Dictionary = item_value as Dictionary
			button.icon = _slot_icon(int(item.get("image_id", 0)), slot)
			if classic_storage != null:
				button.icon = classic_storage.crop_icon(button.icon)
			button.text = ""
			var worn_tooltip: String = (_inventory_tooltip(item, slot)
				+ "\nEquipped position %d" % (index + 1))
			if _carried_slot >= 0 and _carried_slot < 36:
				worn_tooltip += ("\nDropping the item in hand here takes this one off"
					+ " when the two cannot both be worn.")
			button.tooltip_text = worn_tooltip
			button.disabled = false
		else:
			button.icon = null
			button.text = ""
			button.tooltip_text = ("Equip the carried item in generic wear position %d" % (index + 1)
				if _carried_slot >= 0 else "Empty generic equipment position %d" % (index + 1))
			button.disabled = false
	_sync_inventory_tool_buttons()

func _sync_quick_slots() -> void:
	for slot: int in range(quick_slot_buttons.size()):
		var quick_button: Button = quick_slot_buttons[slot]
		var shortcut: String = settings_window.call("binding_text", "quick_item_%d" % (slot + 1))
		var quick_item_value: Variant = AppState.inventory.get(slot)
		if quick_item_value is Dictionary:
			var quick_item: Dictionary = quick_item_value as Dictionary
			var usable: bool = bool(quick_item.get("inventory_usable", false))
			var cooldown_seconds: int = _inventory_cooldown_remaining(slot)
			quick_button.icon = _slot_icon(int(quick_item.get("image_id", 0)), slot)
			quick_button.expand_icon = true
			quick_button.text = ""
			quick_button.disabled = not usable or cooldown_seconds > 0
			var quick_tooltip: String = (_inventory_tooltip(quick_item, slot)
				+ "\nQuick slot: %d  Quantity: %d" % [slot + 1,
					int(quick_item.get("quantity", 0))])
			quick_tooltip += "\nShortcut: " + shortcut
			if cooldown_seconds > 0:
				quick_tooltip += "\nCooldown: %d seconds" % cooldown_seconds
			elif not usable:
				quick_tooltip += "\nThis item cannot be used directly."
			quick_tooltip += "\nScroll this column for more item shortcuts."
			quick_button.tooltip_text = quick_tooltip
		else:
			quick_button.icon = null
			quick_button.text = ""
			quick_button.disabled = true
			quick_button.tooltip_text = ("Empty item quick slot\nShortcut: " + shortcut
				+ "\nScroll this column for more item shortcuts.")
	if selected_inventory_slot >= 0:
		var selected_value: Variant = AppState.inventory.get(selected_inventory_slot)
		if selected_value is Dictionary:
			var selected_item: Dictionary = selected_value as Dictionary
			inventory_use_button.tooltip_text = ("Left click uses the item"
				if bool(selected_item.get("inventory_usable", false))
				and _inventory_cooldown_remaining(selected_inventory_slot) <= 0
				else "The selected item cannot be used right now")

func _sync_spells() -> void:
	if casting_bar != null: casting_bar.refresh()
	for slot: int in range(spell_slot_buttons.size()):
		var button: Button = spell_slot_buttons[slot]
		if slot >= spell_catalog.default_quick_slots.size():
			button.icon = null
			button.text = ""
			button.tooltip_text = "Empty spell quick slot"
			button.disabled = true
			continue
		var spell_id: int = spell_catalog.default_quick_slots[slot]
		var definition: Dictionary = spell_catalog.spell(spell_id)
		var reasons: Array[String] = spell_catalog.unavailable_reasons(
			spell_id, AppState.known_knowledge, AppState.stats, AppState.inventory)
		if not AppState.pending_spell_target.is_empty():
			reasons.append("Complete the pending spell target first")
		button.icon = spell_catalog.icon_for(spell_id)
		button.expand_icon = true
		button.text = ""
		button.disabled = false
		button.tooltip_text = _spell_tooltip(definition, reasons, slot)
	_sync_spell_power_controls()
	match AppState.pending_spell_target:
		"actor":
			spell_status.text = "Select an actor for the spell"
		"location":
			spell_status.text = "Select a ground location for the spell"
		_:
			spell_status.text = _spell_result_text(AppState.last_spell_result)

## What a player presses for one spell quick slot, written the way the key
## is labelled rather than as a slot number. The tenth slot is Alt+0 and the
## last two are the two keys right of it, which is where Eternal Lands puts
## them; a slot with no binding says so instead of naming a key.
func _spell_slot_shortcut(slot: int) -> String:
	const LABELS: Array[String] = ["1", "2", "3", "4", "5", "6", "7", "8", "9",
		"0", "-", "="]
	if slot < 0 or slot >= LABELS.size():
		return "unbound"
	return "Alt+%s" % LABELS[slot]

func _spell_tooltip(definition: Dictionary, reasons: Array[String], slot: int) -> String:
	var lines: Array[String] = [str(definition.get("name", "Unknown spell")),
		str(definition.get("description", "")), "Mana: %d  Magic: %d" % [
			int(definition.get("mana", 0)), int(definition.get("level", 0))],
		"Shortcut: %s" % _spell_slot_shortcut(slot)]
	var effect: String = str(definition.get("effect", ""))
	if AppState.spell_power.has(effect):
		var stated: Dictionary = AppState.spell_power[effect] as Dictionary
		lines.append("Power %d of %d allowed" % [
			mini(requested_spell_power, int(stated.get("limit", 1))),
			int(stated.get("limit", 1))])
	if reasons.is_empty():
		lines.append("Ready; the server validates the cast")
	else:
		lines.append_array(reasons)
	return "\n".join(lines)

## The power stepper. Its ceiling is the highest limit the server stated for
## any effect: the client never works a limit out from a Magic level, and a
## cast is clamped to the limit the server stated for that effect.
func _sync_spell_power_controls() -> void:
	var ceiling: int = 1
	for raw_effect: Variant in AppState.spell_power:
		var stated: Dictionary = AppState.spell_power[raw_effect] as Dictionary
		ceiling = maxi(ceiling, int(stated.get("limit", 1)))
	requested_spell_power = clampi(requested_spell_power, 1, ceiling)
	spell_power_value.text = "P%d" % requested_spell_power
	spell_power_down.disabled = requested_spell_power <= 1
	spell_power_up.disabled = requested_spell_power >= ceiling

## Trailer capture, for filming and never a player setting: launched with
## `-- --trailer-capture`, TRAILER_CAPTURE_KEY cycles the HUD, a clean feed of
## the world alone, and the clean feed without nameplates (see
## src/dev/trailer_camera/README.md). The clean feed draws the world
## viewport's own texture over everything, so a window, popup or chat line
## that opens underneath during a take never reaches the recording; the HUD
## still takes input beneath it. Without the argument the key does nothing.
func _configure_trailer_capture(arguments: PackedStringArray) -> void:
	_trailer_capture_enabled = arguments.has(TRAILER_CAPTURE_ARGUMENT)
	if not _trailer_capture_enabled or _trailer_capture_layer != null:
		return
	_trailer_capture_layer = CanvasLayer.new()
	_trailer_capture_layer.name = "TrailerCaptureFeed"
	_trailer_capture_layer.layer = 128
	_trailer_capture_layer.visible = false
	var feed := TextureRect.new()
	feed.name = "WorldFeed"
	feed.texture = main_viewport.get_texture()
	feed.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	feed.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	feed.stretch_mode = TextureRect.STRETCH_SCALE
	feed.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_trailer_capture_layer.add_child(feed)
	add_child(_trailer_capture_layer)
	game_view.visibility_changed.connect(_sync_trailer_capture)
	print("trailer_capture enabled: %s cycles HUD, clean feed, clean feed without nameplates" % [
		OS.get_keycode_string(TRAILER_CAPTURE_KEY)])

func _cycle_trailer_capture() -> void:
	_trailer_capture_level = (_trailer_capture_level + 1) % 3
	_sync_trailer_capture()
	# Nameplates follow level 2 through _nameplate_visible_for.
	_apply_banner_options()
	print("trailer_capture level=", _trailer_capture_level)

## The clean feed only ever covers the game view: at the login screen, or
## after a disconnect, there is no world to film.
func _sync_trailer_capture() -> void:
	if _trailer_capture_layer != null:
		_trailer_capture_layer.visible = _trailer_capture_level > 0 and game_view.visible

## Saves what is on screen. The legacy client bound this to a dedicated key
## and so does this one; the file goes to the user directory, because a client
## may be installed somewhere it cannot write.
func _save_screenshot() -> String:
	var image: Image = get_viewport().get_texture().get_image()
	if image == null:
		AppState.append_local_line(tr("ELORIA_SCREENSHOT_FAILED").format(
			{"reason": "there is nothing rendered yet"}))
		return ""
	var directory := "user://screenshots"
	DirAccess.make_dir_recursive_absolute(directory)
	var path: String = "%s/rabbitlands-%s.png" % [directory,
		Time.get_datetime_string_from_system(false, true).replace(":", "-")]
	var error: Error = image.save_png(path)
	if error != OK:
		AppState.append_local_line(tr("ELORIA_SCREENSHOT_FAILED").format(
			{"reason": error_string(error)}))
		return ""
	AppState.append_local_line(tr("ELORIA_SCREENSHOT_SAVED").format(
		{"path": ProjectSettings.globalize_path(path)}))
	audio_director.play("ui_click")
	return path

## Apply the same validated frame cap at startup and after a settings change.
func _apply_fps_limit(value: Variant) -> void:
	# Old or invalid preferences keep the default of no explicit frame cap.
	_fps_limit = int(value) if value is int and value in SettingsWindowScript.FPS_LIMITS else 0
	Engine.max_fps = _fps_limit
	settings_window.call("restore_fps_limit", _fps_limit)

## The painted look and the graphics quality from the settings file. A file
## from before they existed, or one holding a value this build cannot read,
## leaves the defaults (Painted ground, HIGH). Main keeps no copy of either:
## LookProfile holds the player's choice and resolves it against ELORIA_LOOK
## and ELORIA_LOOK_QUALITY, so every layer and this file ask one place. A
## settings file read again while a map is up (a test does) applies at once.
func _load_look_settings(config: ConfigFile) -> void:
	var look_changed := LookProfile.set_player_mode(LookProfile.mode_from_settings(config))
	var quality_value: Variant = config.get_value("graphics", "quality",
		LookProfile.quality_name(LookProfile.QUALITY_DEFAULT))
	var level: int = LookProfile.quality_named(str(quality_value)) \
		if quality_value is String else -1
	LookProfile.set_player_quality(
		level if level >= 0 else LookProfile.QUALITY_DEFAULT)
	settings_window.call("restore_look", LookProfile.player_mode(), LookProfile.look_forced())
	settings_window.call("restore_quality", LookProfile.player_quality(),
		LookProfile.quality_forced())
	# The shadows are the renderer's: set once here, before any map, whatever
	# the switch says.
	LookSwitch.apply_shadow_quality(world_sun)
	if look_changed:
		_apply_look_switch()
	# Apply even when the player's stored value stayed the same. A developer or
	# test can change ELORIA_LOOK_QUALITY before this reload, in which case
	# set_player_quality's before and after effective values are already equal.
	_apply_graphics_quality()

## The painted look turned on or off in the settings window (or its file read
## again): everything already loaded follows at once, without reloading the
## map. The fades come to rest first, because a faded occluder holds on to the
## resting materials the switch replaces; every loaded root (the map, each
## chunk and neighbour) is then painted, or given its own materials back
## (LookSwitch); the sun gives back the grade's warmth; and the environment is
## rebound from develop's copy and graded again, or not. The grass beds follow
## by themselves (LookGrassBeds.tend), and a root still being built follows as
## it arrives (`_reconcile_look`).
func _apply_look_switch() -> void:
	var started := Time.get_ticks_usec()
	occluder_fade.release()
	var roots := 0
	var surfaces := 0
	for world: Dictionary in LookSwitch.worlds(world_loader.world_root,
			world_loader.manifest, exterior_stream.residents):
		surfaces += LookSwitch.sync(world.root as Node, world.manifest as WorldManifest,
			bool(world.bound))
		surfaces += SeasonSurfaces.apply(world.root as Node, world.manifest as WorldManifest, true)
		roots += 1
	# The runtime world objects are painted with their map, not as a root.
	for raw_object: Variant in map_object_nodes.values():
		if is_instance_valid(raw_object):
			surfaces += _paint_map_object_look(raw_object as MapObject3D)
	if not LookProfile.full_painted():
		LookGrade.revert_key(world_sun)
	_rebind_look_environment()
	_request_map_redraw()
	print("look_switch stage=applied look=%s roots=%d surfaces=%d milliseconds=%.1f"
		% [LookProfile.enabled(), roots, surfaces, (Time.get_ticks_usec() - started) / 1000.0])

## The graphics quality changed: the shadows at once (LookSwitch), the actor
## meshes and cape solvers, and the grade's screen-space effects, glow and the
## sky's clouds by grading the environment again. The grass beds rebuild at the
## new reach and density by themselves (LookGrassBeds.tend).
func _apply_graphics_quality() -> void:
	LookSwitch.apply_shadow_quality(world_sun)
	crowd.set_quality(LookProfile.quality())
	effect_budget.quality = LookProfile.quality()
	if weather_layer != null:
		weather_layer.set_effects_enabled(_effects_enabled)
	_apply_actor_render_quality()
	_apply_ambient_render_quality()
	_apply_day_night()
	_apply_login_backdrop_quality()
	_update_border_lighting()
	print("look_quality stage=applied quality=", LookProfile.quality_name(LookProfile.quality()))

func _apply_render_scale() -> void:
	main_viewport.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	main_viewport.scaling_3d_scale = _render_scale

func _refresh_graphics_restart_notice() -> void:
	settings_window.graphics_restart_notice.visible = (
		GraphicsOptions.TEXTURE_QUALITIES.find(_map_texture_quality) != GraphicsOptions.active_texture_skip()
		or _renderer_preference != _startup_renderer_preference)

## A one-shot preset. Individual controls remain editable afterward, and the
## renderer stays the player's choice. Preserve essential spell/projectile cues.
func _apply_performance_preset() -> void:
	_applying_graphics_preset = true
	var values := {"quality": LookProfile.Quality.LOW,
		"appearance": LookProfile.Mode.PAINTED_GROUND, "fps_limit": 30,
		"render_scale": 0.75, "map_texture_quality": "half", "crowd_bodies": 60,
		"swaying_capes": 0, "shadows": false, "particles": true,
		"decorative_grass": false, "name_distance": 20.0}
	for key: String in values:
		_on_client_setting_changed("Graphics", key, values[key])
	_applying_graphics_preset = false
	_save_hud_settings()
	_refresh_unified_settings()

## Quality tunes the fallback painting's lightweight drift. Video playback is
## controlled by the entry screen's saved Animate switch at every quality.
func _apply_login_backdrop_quality() -> void:
	var level := clampi(int(LookProfile.quality()), 0, 2)
	var backdrop_material := login_background.material as ShaderMaterial
	if backdrop_material == null:
		return
	var animation_strengths: Array[float] = [0.0, 0.55, 1.0]
	var motion_amounts: Array[float] = [0.0, 0.0012, 0.0024]
	backdrop_material.set_shader_parameter("animation_strength",
		animation_strengths[level])
	backdrop_material.set_shader_parameter("motion_amount", motion_amounts[level])

## Existing actors change in place; new world and preview actors receive the
## same resolved quality immediately after configure.  Pass local status on
## every update because cape simulation deliberately keeps the player's cape.
func _apply_actor_render_quality() -> void:
	var level: int = LookProfile.quality()
	for raw_id: Variant in actor_nodes:
		var actor_value: Variant = actor_nodes[raw_id]
		if actor_value is ReplicatedActor3D and is_instance_valid(actor_value):
			(actor_value as ReplicatedActor3D).apply_render_quality(
				level, int(raw_id) == AppState.local_actor_id)
	if is_instance_valid(preview_actor):
		preview_actor.apply_render_quality(level, true)

## Active and retained territory populations have the same quality immediately.
## Population-local quality polling still covers a population attaching later.
func _ambient_life_populations() -> Array[AmbientPopulation]:
	var populations: Array[AmbientPopulation] = []
	if is_instance_valid(ambient_population) and not ambient_population.is_queued_for_deletion():
		populations.append(ambient_population)
	var roots: Array[Node] = []
	if is_instance_valid(world_root):
		roots.append(world_root)
	if world_loader != null and is_instance_valid(world_loader.world_root):
		roots.append(world_loader.world_root)
	for resident: Dictionary in exterior_stream.residents.values():
		var resident_root := resident.get("root") as Node
		if is_instance_valid(resident_root):
			roots.append(resident_root)
	for resident_root: Node in roots:
		var population := resident_root.get_node_or_null("AmbientPopulation") as AmbientPopulation
		if is_instance_valid(population) and not population.is_queued_for_deletion() and population not in populations:
			populations.append(population)
	return populations

func _apply_ambient_render_quality(level: int = -1) -> void:
	var quality := LookProfile.quality() if level < 0 else level
	for population: AmbientPopulation in _ambient_life_populations():
		population.apply_render_quality(quality)

func ambient_creation_pending_count() -> int:
	var pending := 0
	for population: AmbientPopulation in _ambient_life_populations():
		pending += population.pending_creation_count()
	return pending

## Puts develop's environment for the bound map back, from the copy taken as
## it was bound, paints its sky again if the look is on, and lets the hour and
## the border blend rewrite it and the grade follow, in the order a bind does.
## Nothing to do before the first map, whose placeholder the look never touches.
func _rebind_look_environment() -> void:
	if _unlooked_environment == null or _environment_manifest == null:
		return
	world_environment.environment = _unlooked_environment_copy()
	LookSky.install(_environment_manifest, world_environment)
	_apply_day_night()
	_update_border_lighting()

## Keeps an independent environment snapshot without constructing a temporary
## Sky. GLES3 keeps new skies on a renderer dirty list until its next update;
## cloning then discarding a Sky before that update can orphan its radiance.
func _keep_unlooked_environment(environment: Environment) -> void:
	var sky: Sky = environment.sky
	# A shallow copy initially shares Sky. Detach it from the copy before
	# deep-copying the remaining resources; never change the live environment.
	var without_sky := environment.duplicate(false) as Environment
	without_sky.sky = null
	_unlooked_environment = without_sky.duplicate(true) as Environment
	_unlooked_sky = {}
	if sky == null:
		return
	var kept_material: Material = null
	if sky.sky_material != null:
		kept_material = sky.sky_material.duplicate(true) as Material
	_unlooked_sky = {
		"material": kept_material,
		"radiance_size": sky.radiance_size,
		"process_mode": sky.process_mode,
	}

## A fresh environment from develop's copy, with a new Sky assembled from the
## kept parts. The material is copied again because the hour recolours a
## procedural sky's material in place (DayNightBinder), and the kept one has to
## stay as the binder made it for the next switch.
func _unlooked_environment_copy() -> Environment:
	var environment := _unlooked_environment.duplicate(true) as Environment
	if _unlooked_sky.is_empty():
		return environment
	var sky := Sky.new()
	var material: Material = _unlooked_sky.material
	if material != null:
		sky.sky_material = material.duplicate(true) as Material
	sky.radiance_size = _unlooked_sky.radiance_size
	sky.process_mode = _unlooked_sky.process_mode
	environment.sky = sky
	return environment

## A root a loader worker finished under the look switch's old answer (a
## chunk or neighbour that was being built as the player switched) follows the
## new one as it arrives. Nothing is walked unless some root is stale
## (LookProfile.any_stale), which only happens for a moment after a switch.
## The fades are left alone: a stale root is a new arrival this frame, which
## `_update_occluder_fade` has not probed yet, so nothing of it is faded, and
## releasing every fade would only snap the walls around the player solid.
func _reconcile_look() -> void:
	if not LookProfile.any_stale():
		return
	var stale: Array[Dictionary] = []
	for world: Dictionary in LookSwitch.worlds(world_loader.world_root,
			world_loader.manifest, exterior_stream.residents):
		if LookProfile.stale(world.root as Node):
			stale.append(world)
	if stale.is_empty():
		return
	for world: Dictionary in stale:
		var surfaces := LookSwitch.sync(world.root as Node, world.manifest as WorldManifest,
			bool(world.bound))
		SeasonSurfaces.apply(world.root as Node, world.manifest as WorldManifest, true)
		print("look_switch stage=reconciled root=%s look=%s surfaces=%d"
			% [(world.root as Node).name, LookProfile.enabled(), surfaces])

## An old or hand-edited preference is held to the slider's range. The fades
## are worked out on the animation gate's clock, so the next frame is asked to
## rather than waiting out the rest of its tenth of a second.
func _set_name_distance(value: Variant) -> void:
	var metres: float = (float(value) if value is float or value is int
		else NAME_DISTANCE_DEFAULT_METRES)
	_name_distance_metres = clampf(metres, SettingsWindowScript.NAME_DISTANCE_MIN,
		SettingsWindowScript.NAME_DISTANCE_MAX)
	_animation_gate_refresh_msec = 0

## The player's crowd settings, clamped to the sliders' ranges and handed to
## the crowd presentation, which keeps any value the environment forces for a
## benchmark. The next gate sweep applies them.
func _set_crowd_settings(bodies: Variant, capes: Variant) -> void:
	_crowd_bodies = clampi(int(bodies) if bodies is int or bodies is float
		else SettingsWindowScript.CROWD_BODIES_DEFAULT,
		SettingsWindowScript.CROWD_BODIES_MIN, SettingsWindowScript.CROWD_BODIES_MAX)
	_swaying_capes = clampi(int(capes) if capes is int or capes is float
		else SettingsWindowScript.SWAYING_CAPES_DEFAULT,
		SettingsWindowScript.SWAYING_CAPES_MIN, SettingsWindowScript.SWAYING_CAPES_MAX)
	crowd.set_player_budgets(_crowd_bodies, _swaying_capes)
	_animation_gate_refresh_msec = 0
	_sync_declared_actor_cap()

## The actor cap this client declares to the server (`actor_cap:<N>` in
## `#clientcaps`) follows the crowd setting: the server is asked for no more
## players and creatures than are drawn with a body, and never more than the
## protocol's 160 (interest_protocol.gd `declared_actor_cap`). At the
## setting's default of 160 the declaration is 160, which is what a client
## that declares nothing gets.
func _sync_declared_actor_cap() -> void:
	var cap: int = InterestProtocol.declared_actor_cap(_crowd_bodies)
	if cap == int(Network.declared_actor_cap):
		return
	Network.declared_actor_cap = cap
	# In a session the cap changes with `#actorcap`, which only a server
	# running player interest takes (it has sent presence); any other server
	# is told at the next login. It goes once the slider has come to rest.
	if not AppState.authenticated or not AppState.presence.active:
		return
	_actor_cap_declaration += 1
	var declaration: int = _actor_cap_declaration
	get_tree().create_timer(ACTOR_CAP_REDECLARE_SECONDS).timeout.connect(func() -> void:
		if (declaration == _actor_cap_declaration and AppState.authenticated
				and AppState.presence.active):
			Network.send_chat(InterestProtocol.actor_cap_command(int(Network.declared_actor_cap))))

## Preferences apply locally. Only the target-mode and autogather buttons
## send commands owned by the server.
func _on_client_setting_changed(section: String, key: String,
		value: Variant) -> void:
	if section == "Banners" and key.begins_with("banner_color"):
		if key == "banner_colors_reset":
			hud_workspace.reset_banner_colors()
		elif key.begins_with("banner_color_sync_"):
			hud_workspace.set_banner_color_sync(key.trim_prefix("banner_color_sync_"), bool(value))
		else:
			hud_workspace.change_banner_color(key.trim_prefix("banner_color_"), value)
		return
	if section == "Banners" and key.begins_with("creature_banner_"):
		for mode: String in CreatureBannerSettings.MODES:
			var prefix := "creature_banner_" + mode + "_"
			if not key.begins_with(prefix):
				continue
			var option := key.trim_prefix(prefix)
			if not CreatureBannerSettings.OPTION_LABELS.has(option):
				return
			_creature_banner_options[mode][option] = bool(value)
			_apply_banner_options()
			_refresh_unified_settings()
			_save_hud_settings()
			return
		return
	if section == "Banners" and key.begins_with("target_"):
		if key == "target_markers_reset":
			_target_marker_style = TargetMarkerStyle.defaults()
		else:
			var property := key.trim_prefix("target_")
			if not TargetMarkerStyle.DEFAULTS.has(property): return
			_target_marker_style[property] = value
			_target_marker_style = TargetMarkerStyle.normalise(_target_marker_style)
		_apply_target_marker_style()
		_save_hud_settings()
		return
	if key.begins_with("mount_banner_"):
		_set_mount_banner_option(key.trim_prefix("mount_banner_"), bool(value))
		return
	if section == "Audio" and key.begins_with("audio_"):
		audio_director.set_category_volume(key.trim_prefix("audio_"), float(value))
		_save_hud_settings()
		return
	if section == "Chat":
		var surface: PanelContainer = system_chat_hud if key.begins_with("system_chat_") else chat_hud
		var option := key.trim_prefix("system_chat_") if key.begins_with("system_chat_") else key.trim_prefix("chat_")
		if option == "reset_layout":
			surface.reset_layout()
		else:
			surface.set_option(option, value)
		return
	if key.begins_with("minimap_marker_") and key != "minimap_marker_scale":
		var type := StringName(key.trim_prefix("minimap_marker_"))
		if type in MINIMAP_MARKER_TYPES:
			_minimap_marker_types[type] = bool(value)
			_apply_minimap_marker_settings()
			_save_hud_settings()
		return
	if key.begins_with("quantity_"):
		var index := int(key.trim_prefix("quantity_"))
		_inventory_quantities[index] = clampi(int(value), 1, INVENTORY_QUANTITY_MAX)
		_sync_inventory_quantity_boxes()
		_save_hud_settings()
		return
	if key.begins_with("protect_"):
		var parts := key.split("_")
		_bulk_exclusions[parts[1]][int(parts[2])] = bool(value)
		_sync_bulk_option_menus()
		_save_hud_settings()
		return
	if _hud_element_options.has(key) and section == "HUD":
		_hud_element_options[key] = bool(value)
		_apply_hud_element_options()
		_save_hud_settings()
		return
	match key:
		"minimap_visible":
			_minimap_visible = bool(value)
			minimap_frame.visible = _minimap_visible
			_request_map_redraw()
		"minimap_orientation":
			_minimap_orientation = str(value)
			_request_map_redraw()
		"minimap_shape":
			_minimap_shape = str(value)
			_apply_minimap_shape()
		"minimap_border":
			_minimap_border = float(value)
			_apply_minimap_scale()
		"minimap_marker_scale":
			_minimap_marker_scale = float(value)
			_apply_minimap_marker_settings()
		"minimap_zoom":
			_minimap_zoom = clampf(float(value), MINIMAP_ZOOM_MIN, MINIMAP_ZOOM_MAX)
			_apply_minimap_zoom()
		"inventory_scale":
			_apply_inventory_scale(float(value))
		"ground_bag_scale":
			_apply_ground_bag_scale(float(value))
		"storage_docked":
			classic_storage.set_docked(bool(value))
		"selected_quantity":
			_on_quantity_box_pressed(int(value))
		"spell_bar_docked":
			casting_bar.set_docked(bool(value))
		"spell_bar_expanded":
			casting_bar.set_expanded(bool(value))
		"combat_hud_pinned":
			extension_windows.set_combat_hud_pinned(bool(value))
		"timer_stopwatch", "timer_start_seconds":
			if key == "timer_stopwatch":
				_hud_timer_stopwatch = bool(value)
			else:
				_hud_timer_start_seconds = clampi(int(value), 0, 599)
			_hud_timer_running = false
			_hud_timer_seconds = 0 if _hud_timer_stopwatch else _hud_timer_start_seconds
			_sync_hud_timer_label()
		"start_backdrop":
			start_screen_backdrop.select_backdrop(str(value))
		"start_animated":
			start_screen_backdrop.set_animation_enabled(bool(value))
		"invasion_assistant_scale":
			invasion_assistant_window.resize_to_scale(float(value))
		"fps_limit":
			_apply_fps_limit(value)
		"performance_preset":
			_apply_performance_preset()
			return
		"render_scale":
			_render_scale = GraphicsOptions.render_scale(value)
			_apply_render_scale()
		"map_texture_quality":
			_map_texture_quality = GraphicsOptions.texture_quality(value)
			_refresh_graphics_restart_notice()
		"renderer":
			_renderer_preference = GraphicsLaunchOptions.renderer_name(value)
			_refresh_graphics_restart_notice()
		"decorative_grass":
			GraphicsOptions.decorative_grass = bool(value)
			if not GraphicsOptions.decorative_grass:
				LookGrassBeds.clear(world_root)
		"appearance":
			if LookProfile.set_player_mode(int(value)):
				_apply_look_switch()
		"look":
			# Compatibility for older authoring and capture tools.
			if LookProfile.set_player_look(bool(value)):
				_apply_look_switch()
		"quality":
			if LookProfile.set_player_quality(int(value)):
				_apply_graphics_quality()
		"shadows":
			_shadows_enabled = bool(value)
			world_sun.shadow_enabled = _shadows_enabled and world_sun.visible
			# The hour decides whether the sun may cast at all (none below the
			# horizon), so it is asked again rather than overruled.
			_apply_day_night()
		"particles":
			_effects_enabled = bool(value)
			if not _effects_enabled:
				for effect: Variant in world_effects:
					if is_instance_valid(effect) and effect.is_in_group("technique_visual_effects"): effect.queue_free()
			for actor_value: Variant in actor_nodes.values():
				if is_instance_valid(actor_value):
					(actor_value as ReplicatedActor3D).set_combat_effects_enabled(_effects_enabled)
			for object_value: Variant in map_object_nodes.values():
				if is_instance_valid(object_value):
					(object_value as MapObject3D).set_particles_enabled(_effects_enabled)
			_sync_harvest_sparkle()
			# The rain's drops follow the switch at once; the sky keeps its
			# weather either way.
			if weather_layer != null:
				weather_layer.set_effects_enabled(_effects_enabled)
		"cape_emblems":
			CapeEmblems.set_enabled(bool(value))
		"nameplates":
			_nameplates_enabled = bool(value)
			_apply_banner_options()
		"name_distance":
			_set_name_distance(value)
		"crowd_bodies":
			_set_crowd_settings(value, _swaying_capes)
		"swaying_capes":
			_set_crowd_settings(_crowd_bodies, value)
		"combat_hud":
			extension_windows.call("set_combat_hud_enabled", bool(value))
		"rotation_sensitivity":
			camera_rig.rotation_sensitivity = float(value)
		"keyboard_speed":
			camera_rig.keyboard_speed = float(value)
		"target_mode_strong":
			Network.send_chat("#targetmode strong")
		"target_mode_weak":
			Network.send_chat("#targetmode weak")
		"autogather":
			Network.send_chat("#autogather")
		"magic_autocast":
			Network.magic_request({"op": "autocast", "enabled": bool(value)})
	# Commands on Gameplay belong to the server; its local preferences still
	# save immediately.
	if not _applying_graphics_preset and key not in ["target_mode_strong", "target_mode_weak", "autogather", "magic_autocast"]:
		_save_hud_settings()

func _apply_target_marker_style() -> void:
	for actor: Variant in actor_nodes.values():
		if is_instance_valid(actor):
			(actor as ReplicatedActor3D).set_target_marker_style(_target_marker_style)

func _on_binding_changed(_action: String) -> void:
	_refresh_service_tooltips()
	_save_hud_settings()
	_sync_quick_slots()
	# Quick spell badges and the Techniques hint name the keys they use.
	casting_bar.refresh()
	techniques_panel.call("sync")
	# The help page is generated from the bindings, so it follows a rebind.
	reference_window.call("_refresh_help")

func _on_notes_changed(text: String) -> void:
	_player_notes = text
	_save_hud_settings()

## A bookmark is the player's own, like a note: it is kept in the client's
## settings file and never goes near the server.
func _on_encyclopedia_bookmarks_changed(bookmarks: Array) -> void:
	_encyclopedia_bookmarks = bookmarks
	_save_hud_settings()

## The encyclopedia icon on the lower HUD, and Ctrl+E. Both open the reference
## window on its encyclopedia page, and close it again from that page.
func _on_encyclopedia_button_pressed() -> void:
	var was_open: bool = bool(reference_window.call("is_encyclopedia_open"))
	reference_window.call("toggle_encyclopedia")
	audio_director.play("ui_close" if was_open else "ui_click")
	_sync_hud_button_states(true)

## Help, the player's notes, the addresses the server has linked, and the
## encyclopedia. Opened from the settings panel beside the other windows.
func _on_reference_pressed() -> void:
	reference_window.toggle()
	audio_director.play("ui_click" if reference_window.is_open() else "ui_close")

## The Eternal Lands spell book: the icon-row window with the catalog grouped
## the way the legacy client groups it. Casting goes through the same seam the
## quickbar uses, so the two can never disagree about what a cast sends.
func _on_spells_button_pressed() -> void:
	spells_window.toggle()
	if spells_window.is_open() and AppState.lantern_tutorial.get("tutorial", "") in ["borrowed_sky", "followup"]:
		Network.tutorial_ui(7)
	audio_director.play("ui_click" if spells_window.is_open() else "ui_close")
	_sync_hud_button_states(true)

## The summoning window: the catalog's summoning recipes on their own, with
## what each creature costs written beside it.
func _on_summoning_button_pressed() -> void:
	summoning_window.call("toggle")
	if bool(summoning_window.call("is_open")): _road_ui(11)
	audio_director.play("ui_click" if bool(summoning_window.call("is_open"))
		else "ui_close")

## Summoning is a mix whose result is a creature, so it goes out as the same
## MANUFACTURE_THIS the manufacture window sends. One seam, so the two windows
## can never disagree about what asking for a mix looks like on the wire.
func _summon_by_ingredients(selection: Array[Dictionary]) -> void:
	var error: Error = Network.manufacture(selection, 1)
	if error != OK:
		push_warning("MANUFACTURE_THIS summon failed: " + error_string(error))

## Asks the server to open its own summon-behaviour popup. There is no packet
## for "open a popup" - the server offers it on a command and on touching one
## of your own summons - so the command is what the hotkey and the window's
## button both send.
func _request_summon_behavior() -> void:
	var error: Error = Network.send_chat("#summon_behavior")
	if error != OK:
		push_warning("#summon_behavior failed: " + error_string(error))

## Asks the server to open its combat-target popup: which of several creatures
## attacking you at once you turn to fight. Same shape as the summon-behaviour
## key above - a standing preference on the character, offered on a command,
## and answered through the ordinary popup reply.
func _request_combat_target() -> void:
	var error: Error = Network.send_chat("#targetmode")
	if error != OK:
		push_warning("#targetmode failed: " + error_string(error))

func _on_emotes_button_pressed() -> void:
	emotes_window.toggle()
	audio_director.play("ui_click" if emotes_window.is_open() else "ui_close")
	_sync_hud_button_states(true)

func _on_quest_button_pressed() -> void:
	extension_windows.call("toggle_quest_journal")
	_sync_hud_button_states(true)

## Ctrl+X: the Spells & Techniques window, opened on Techniques.
func _on_techniques_button_pressed() -> void:
	spells_window.call("toggle_techniques")
	audio_director.play("ui_click" if spells_window.is_open() else "ui_close")
	_sync_hud_button_states(true)

## The Techniques tab's "+": the first empty quick spell slot takes it.
func _place_technique_on_bar(key: String) -> void:
	var index: int = int(spell_loadout.call("first_empty_slot"))
	if index < 0:
		AppState.append_local_message("Every quick spell slot is in use. Drag the technique onto the one to replace.")
		return
	spell_loadout.call("assign_technique", index, key)
	AppState.append_local_message("%s is on quick spell slot %d." % [
		str(techniques_panel.get("rows").get(key, {}).get("name", key)), index + 1])

## A creature a technique may be aimed at: something this player could attack
## that is not another player.
func _technique_creature_target(actor_id: int) -> bool:
	var actor: Dictionary = AppState.actors.get(actor_id, {})
	return int(actor.get("kind", 0)) not in [1, 4] and _is_attackable_actor(actor_id, actor)

## Another player, for Intercept; the server checks they are in the party.
func _technique_player_target(actor_id: int) -> bool:
	var actor: Dictionary = AppState.actors.get(actor_id, {})
	return actor_id != AppState.local_actor_id and int(actor.get("kind", 0)) in [1, 4]

## The action points a meter shows. The legacy stats slots 113/114 carry pick
## points on this server, so a techniques_v1 server's real pool wins.
func _action_pool(stats: Dictionary) -> Vector2i:
	if AppState.techniques.has("action_points"):
		return Vector2i(int(AppState.techniques.get("action_points", 0)),
			maxi(1, int(AppState.techniques.get("max_action_points", 1))))
	return Vector2i(int(stats.get("action_points", 0)),
		maxi(1, int(stats.get("max_action_points", 1))))

## Repeat casting: the Gameplay box follows the server, and while a spell is
## repeating the spell status line says so and how to stop it.
func _sync_autocast() -> void:
	settings_window.call("restore_toggle", "magic_autocast", bool(AppState.autocast.get("enabled", false)))
	if bool(AppState.autocast.get("active", false)):
		var spell: Dictionary = spell_catalog.spell(int(AppState.autocast.get("spell_id", -1))) if spell_catalog != null else {}
		spell_status.text = "Repeating %s every round · click elsewhere or press Esc to stop" % str(spell.get("name", "a spell"))
	elif spell_status.text.begins_with("Repeating "):
		spell_status.text = ""

func _on_ranging_button_pressed() -> void:
	ranging_window.toggle()
	if ranging_window.is_open() and AppState.lantern_tutorial.get("tutorial", "") == "second_bell":
		Network.tutorial_ui(5)
	audio_director.play("ui_click" if ranging_window.is_open() else "ui_close")
	_sync_hud_button_states(true)

func _on_console_button_pressed() -> void:
	_toggle_console()
	_sync_hud_button_states(true)

func _on_minimap_button_pressed() -> void:
	_toggle_minimap()
	_sync_hud_button_states(true)

## The reference window's pages behind their Eternal Lands icons: Info is the
## notepad and the link list, Buddy the list the server states, Help the keys
## and commands. Each icon opens its page, or closes the window from that page,
## exactly the way the encyclopedia icon already treats its own.
func _on_info_button_pressed() -> void:
	_toggle_reference_tab(1)

func _on_buddy_button_pressed() -> void:
	_toggle_reference_tab(5)

func _on_help_button_pressed() -> void:
	_toggle_reference_tab(0)

func _toggle_reference_tab(tab: int) -> void:
	var tabs: TabContainer = reference_window.get("tabs") as TabContainer
	var was_here: bool = reference_window.call("is_open") and tabs.current_tab == tab
	if was_here:
		reference_window.call("close")
	else:
		if not reference_window.call("is_open"):
			reference_window.call("toggle")
		tabs.current_tab = tab
	audio_director.play("ui_close" if was_here else "ui_click")
	_sync_hud_button_states(true)

func _reference_tab_open(tab: int) -> bool:
	if reference_window == null or not bool(reference_window.call("is_open")):
		return false
	return (reference_window.get("tabs") as TabContainer).current_tab == tab

## Casts one catalogued spell: the spells window's seam onto the network. The
## same checks the quickbar makes, because it is the same cast.
func _cast_spell_by_id(spell_id: int) -> void:
	var power: int = spell_loadout.power_for(spell_id)
	_begin_prepared_cast(spell_id, power)

func _on_magic_state(data: Dictionary) -> void:
	if data.get("kind") == "target_cast":
		# Apply the preceding movement/turn actor snapshots first. A deferred
		# turn must not replace the channel we are about to start.
		_present_target_cast.call_deferred(data)
		return
	if data.get("kind") == "technique_effect":
		_on_technique_effect(data)
		return
	if data.get("kind") == "spell_impact":
		_on_special_effect_requested(data)
		return
	if data.get("kind") != "burst": return
	var source := actor_nodes.get(int(data.get("actor_id", -1))) as ReplicatedActor3D
	if is_instance_valid(source) and data.has("release_delay"):
		source.set_combat_effects_enabled(_effects_enabled)
		source.set_spell_variant(int(data.effect))
		source.play_action(SpellPresentation.action_for_effect(int(data.effect)), true)
	if not _effects_enabled: return
	var origin: Vector3 = adapter.tile_center(int(data.x), int(data.y))
	if not _admit_effect(&"spell", [int(data.get("actor_id", -1))], origin): return
	var effect := WorldEffect3D.new()
	world_root.add_child(effect)
	var sampled: Variant = _navigation_ray_position(origin + Vector3(0, 200, 0), Vector3.DOWN)
	if sampled is Vector3: origin.y = sampled.y
	if is_instance_valid(source) and data.has("release_delay"):
		effect.configure(int(data.effect), source.global_position, origin, int(data.power))
		effect.bind_actors(source, null)
	else:
		effect.configure(int(data.effect), origin, null, int(data.power))
	effect.configure_area(float(data.get("radius", 4.0)) * adapter.metres_per_tile, str(data.get("scope", "burst")))
	if data.has("release_delay"):
		effect.configure_timing(float(data.release_delay), float(data.get("flight_duration", 0.0)))
	_track_effect(effect, &"spell")

func _present_target_cast(data: Dictionary) -> void:
	var caster := actor_nodes.get(int(data.get("actor_id", -1))) as ReplicatedActor3D
	if not is_instance_valid(caster): return
	if data.get("phase") == "channel":
		var caster_adapter := _adapter_for_actor(AppState.actors.get(caster.actor_id, {}))
		if caster_adapter == null: return
		caster.face_for_spell(caster_adapter.rotation_to_godot(int(data.rotation)))
		caster.set_combat_effects_enabled(_effects_enabled)
		caster.play_action(&"cast_channel_enter")
		if caster.combat_presentation != null:
			caster.combat_presentation.set_spell_power(int(data.get("power", 1)))
	elif data.get("phase") in ["approach", "cancelled"] and caster.current_action in [&"cast_channel_enter", &"cast_channel"]:
		caster.play_action(&"cast_exit")

func _on_technique_effect(data: Dictionary) -> void:
	var key := str(data.get("key", ""))
	var presentation = preload("res://src/world/technique_presentation.gd")
	if not presentation.PROFILES.has(key): return
	var source := actor_nodes.get(int(data.get("actor_id", -1))) as ReplicatedActor3D
	if not is_instance_valid(source) or source.current_action == &"death": return
	var phase := str(data.get("phase", "strike"))
	if phase not in ["strike", "counter", "activate", "shot", "impact", "pulse", "land"]: return
	if phase == "land" and key != "charge": return
	if key == "charge" and phase == "activate" and data.has("leap"):
		var route := _charge_leap_route(source, data.leap)
		if route.size() < 2: return
		source.begin_charge_leap(route, float(data.leap.get("duration", 0.36)))
	else:
		if key == "charge" and phase in ["land", "strike"]: source.end_charge_leap()
		source.play_technique(key, phase)
	if not _effects_enabled: return
	# The live-effect budget replaces the old 48-node ceiling, which asked the
	# scene tree for the whole group on every technique.
	if crowd.effects:
		if not _admit_effect(&"technique", [int(data.get("actor_id", -1)),
				int(data.get("target_id", -1))]): return
	elif get_tree().get_nodes_in_group("technique_visual_effects").size() >= 48: return
	var target := actor_nodes.get(int(data.get("target_id", -1))) as Node3D
	var effect = preload("res://src/world/technique_effect_3d.gd").new()
	world_root.add_child(effect)
	effect.configure(key, phase, source, target, bool(data.get("hit", false)))
	_track_effect(effect, &"technique")

func _charge_leap_route(source: ReplicatedActor3D, value: Variant) -> PackedVector3Array:
	var route := PackedVector3Array()
	if not value is Dictionary: return route
	var origin: Variant = value.get("origin", [])
	var offsets: Variant = value.get("offsets", [])
	if not origin is Array or origin.size() != 2 or not offsets is Array or offsets.size() < 2 or offsets.size() > 13: return route
	var record: Dictionary = AppState.actors.get(source.actor_id, {}) as Dictionary
	var actor_adapter := _adapter_for_actor(record)
	if actor_adapter == null: return route
	var mask: int = WorldLoader.NAVIGATION_SURFACE_LAYER
	if source.actor_id != AppState.local_actor_id and str(record.get("map", AppState.current_map)) != AppState.current_map:
		mask |= ExteriorRegionStream.PREVIEW_SURFACE_LAYER
	for offset: Variant in offsets:
		if not offset is Array or offset.size() != 2: return PackedVector3Array()
		if absf(float(offset[0])) > 12 or absf(float(offset[1])) > 12: return PackedVector3Array()
		var point := actor_adapter.footprint_center(int(origin[0]) + int(offset[0]), int(origin[1]) + int(offset[1]), source.footprint)
		point.y = source.server_target.y
		if gameplay_world != null:
			var query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 2000.0, point + Vector3.DOWN * 2000.0,
				mask)
			var hit := gameplay_world.direct_space_state.intersect_ray(query)
			if hit.get("position") is Vector3: point.y = (hit.position as Vector3).y + 0.02
		route.append(point)
	return route

## The emote picker's seam onto the network: the same packet `#emote <name>`
## already sends. The server stays the judge of what the name means.
func _perform_emote(emote_name: String) -> void:
	var error: Error = Network.do_emote(emote_name)
	if error != OK:
		push_warning("DO_EMOTE failed: " + error_string(error))

## The reference window's Add buddy button. Asking is a chat command the
## server answers; the list itself only ever changes when the server restates it.
func _on_buddy_add_requested(buddy_name: String) -> void:
	var error: Error = Network.send_chat("#add_buddy " + buddy_name)
	if error != OK:
		push_warning("add_buddy failed: " + error_string(error))

func _on_spell_power_down_pressed() -> void:
	requested_spell_power = maxi(1, requested_spell_power - 1)
	_sync_spells()
	spells_window.requested_power = requested_spell_power
	spells_window.sync()

func _on_spell_power_up_pressed() -> void:
	requested_spell_power += 1
	_sync_spells()
	spells_window.requested_power = requested_spell_power
	spells_window.sync()

## The power this cast asks for: the stepper, clamped to what the server said
## this effect may reach. With no stated limit the legacy frame is sent, which
## is the frame without a power byte at all.
func _cast_power_for(spell_id: int) -> int:
	var effect: String = spell_catalog.effect_for(spell_id)
	if not AppState.spell_power.has(effect):
		return 0
	var stated: Dictionary = AppState.spell_power[effect] as Dictionary
	return mini(requested_spell_power, maxi(1, int(stated.get("limit", 1))))

func _spell_result_text(result: Dictionary) -> String:
	if result.is_empty():
		return "Spells synchronize with the server"
	var spell_id: int = int(result.get("spell_id", -1))
	var definition: Dictionary = spell_catalog.spell(spell_id)
	var spell_name: String = str(definition.get("name", "spell"))
	match int(result.get("status", 0)):
		1: return "%s cast successfully" % spell_name
		2: return "%s was rejected" % spell_name
		3: return "Invalid or unknown spell"
		4: return "Select an actor for %s" % spell_name
		5: return "Select a location for %s" % spell_name
		_: return "Spell response received"

func _cast_spell_slot(slot: int) -> void:
	if slot < 0 or slot >= spell_loadout.slots.size(): return
	var entry: Dictionary = spell_loadout.slots[slot]
	if not str(entry.get("technique", "")).is_empty():
		# A technique on the quick bar is aimed like one from the ring or tab.
		techniques_panel.call("use", str(entry.technique))
		return
	if int(entry.id) < 0:
		spells_window.edit_prepared_slot(slot)
		return
	_begin_prepared_cast(int(entry.id), int(entry.power))

func _magic_ring_ui(action: int) -> void:
	if AppState.lantern_tutorial.get("active", false) and AppState.lantern_tutorial.get("tutorial", "") == "borrowed_sky" and AppState.lantern_tutorial.get("key", "") == "book":
		Network.tutorial_ui(action)

func _begin_prepared_cast(spell_id: int, power: int) -> void:
	var stated: Dictionary = AppState.spell_power.get(spell_catalog.effect_for(spell_id), {})
	power = mini(power, maxi(1, int(stated.get("limit", 1))))
	magic_selection.begin(spell_id, power, AppState.selected_actor_id)
	spells_window.close()

func _spell_target_candidate(spell_id: int, actor_id: int) -> bool:
	var actor: Dictionary = AppState.actors.get(actor_id, {})
	if actor.is_empty():
		return false
	var spell: Dictionary = spell_catalog.spell(spell_id)
	if not bool(actor.get("alive", int(actor.get("health", 0)) > 0)):
		return actor_id != AppState.local_actor_id and int(actor.get("kind", 0)) in [1, 4] \
			and spell.get("scope") == "target" and spell.get("effect") == "heal"
	if bool(spell.get("hostile", false)):
		if spell.get("effect") == "mana_drain" and int(actor.get("kind", 0)) not in [1, 4]: return false
		if spell.get("effect") == "disrupt" and not ReplicatedActor3D.is_summon(actor): return false
		return _is_attackable_actor(actor_id, actor)
	return actor_id == AppState.local_actor_id or int(actor.get("kind", 0)) in [1, 4] or _is_tutorial_companion(actor_id)

func _update_magic_preview() -> void:
	var aiming := not Network.magic_pending.is_empty() and Network.magic_scope in ["burst", "location"]
	if _magic_area_preview != null: _magic_area_preview.visible = false
	if not aiming or full_map.visible: return
	var hovered: Control = get_viewport().gui_get_hovered_control()
	if hovered != null and hovered != viewport_container and not viewport_container.is_ancestor_of(hovered): return
	var position := _local_viewport_position(viewport_container.get_local_mouse_position())
	var tile: Variant = _map_target_tile(gameplay_camera, position)
	if not tile is Vector2i: return
	if _magic_area_preview == null:
		_magic_area_preview = MeshInstance3D.new()
		_magic_area_preview.mesh = PlaneMesh.new()
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		_magic_area_preview.material_override = material
		_magic_area_preview.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		world_root.add_child(_magic_area_preview)
	var width := 9.0 if Network.magic_scope == "burst" else 1.0
	(_magic_area_preview.mesh as PlaneMesh).size = Vector2.ONE * width * adapter.metres_per_tile
	var point: Vector3 = adapter.tile_center(tile.x, tile.y)
	var sampled: Variant = _navigation_ray_position(point + Vector3(0, 200, 0), Vector3.DOWN)
	if sampled is Vector3: point.y = sampled.y
	_magic_area_preview.position = point + Vector3(0, 0.05, 0)
	var player: Dictionary = AppState.actors.get(AppState.local_actor_id, {})
	var in_range := maxi(absi(tile.x - int(player.get("x", tile.x))), absi(tile.y - int(player.get("y", tile.y)))) <= 15
	(_magic_area_preview.material_override as StandardMaterial3D).albedo_color = Color(0.2, 0.75, 1.0, 0.3) if in_range else Color(1.0, 0.2, 0.1, 0.3)
	_magic_area_preview.visible = true

## Draws each item cooldown as a proportional drain over its slot, in both
## the quick bar and the inventory grid. `maximum_msec` came off the wire in
## every cooldown packet and was stored and never read, so a cooldown was a
## disabled button with a number in a tooltip and no sense of how far through
## it was. Runs every frame: it only moves an anchor and sets a label, and a
## chunky one-second step would defeat the point of showing progress at all.
func _update_cooldown_overlays() -> void:
	for slot: int in range(quick_slot_buttons.size()):
		_apply_cooldown_shade(quick_slot_buttons[slot], slot)
	for slot: int in range(inventory_slot_buttons.size()):
		_apply_cooldown_shade(inventory_slot_buttons[slot], slot)

func _apply_cooldown_shade(button: Button, slot: int) -> void:
	var shade: ColorRect = _cooldown_shade(button)
	var seconds_label: Label = button.get_node("Seconds") as Label
	var cooldown_value: Variant = AppState.inventory_cooldowns.get(slot)
	if not cooldown_value is Dictionary:
		shade.visible = false
		seconds_label.visible = false
		return
	var cooldown: Dictionary = cooldown_value as Dictionary
	var remaining_msec: int = int(cooldown.get("end_msec", 0)) - Time.get_ticks_msec()
	var maximum_msec: int = maxi(1, int(cooldown.get("maximum_msec", 0)))
	if remaining_msec <= 0:
		shade.visible = false
		seconds_label.visible = false
		return
	shade.visible = true
	seconds_label.visible = true
	# The shade drains from full to empty as the cooldown runs out.
	shade.anchor_top = 1.0 - clampf(float(remaining_msec) / float(maximum_msec),
		0.0, 1.0)
	seconds_label.text = str(maxi(1, ceili(float(remaining_msec) / 1000.0)))

## The shade's own anchor moves as it drains, so the seconds label is added
## as its sibling rather than its child: nested inside the shade, the label
## inherited the shrinking rect and drifted down the icon over the course of
## the cooldown instead of staying centered on it.
func _cooldown_shade(button: Button) -> ColorRect:
	var existing: ColorRect = button.get_node_or_null("Cooldown") as ColorRect
	if existing != null:
		return existing
	var shade := ColorRect.new()
	shade.name = "Cooldown"
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	shade.color = Color(0.05, 0.06, 0.09, 0.66)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.visible = false
	button.add_child(shade)
	var seconds := Label.new()
	seconds.name = "Seconds"
	seconds.mouse_filter = Control.MOUSE_FILTER_IGNORE
	seconds.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	seconds.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	seconds.set_anchors_preset(Control.PRESET_FULL_RECT)
	seconds.visible = false
	button.add_child(seconds)
	return shade

func _inventory_cooldown_remaining(slot: int) -> int:
	var cooldown_value: Variant = AppState.inventory_cooldowns.get(slot)
	if not cooldown_value is Dictionary:
		return 0
	var cooldown: Dictionary = cooldown_value as Dictionary
	var remaining_msec: int = int(cooldown.get("end_msec", 0)) - Time.get_ticks_msec()
	return maxi(0, ceili(float(remaining_msec) / 1000.0))

## Builds a slot tooltip. The quantity and the traits always come from the
## authoritative inventory packet; command 226 only adds the names, categories
## and weights that packet has no room for, and is ignored where the two
## disagree about how much is in the slot.
func _inventory_tooltip(item: Dictionary, slot: int) -> String:
	var traits: Array[String] = []
	for flag_and_label: Array in [
		["inventory_usable", "usable"], ["stackable", "stackable"],
		["resource", "resource"], ["reagent", "reagent"]]:
		if bool(item.get(flag_and_label[0], false)):
			traits.append(str(flag_and_label[1]))
	var image_id: int = int(item.get("image_id", 0))
	var described: Dictionary = _inventory_description_for(slot)
	var heading: String = (str(described.get("name", ""))
		if not str(described.get("name", "")).is_empty()
		else str(AppState.inventory_names.get(slot, "Item image #%d" % image_id)))
	var tooltip: String = "%s — quantity %d%s" % [heading,
		int(item.get("quantity", 0)), " — " + ", ".join(traits) if not traits.is_empty() else ""]
	if not str(described.get("category", "")).is_empty():
		tooltip += "
%s — %d EMU each" % [str(described.get("category", "")),
			int(described.get("emu", 0))]
	if item_atlas.uses_substitute(image_id):
		tooltip += "\nIndependent Rabbit Lands icon substitute for legacy image #%d." % image_id
	return tooltip

## The command 226 entry for a slot, or an empty dictionary when the server has
## not described that slot.
## Floats the change in an actor's health over that actor.
##
## Derived from the health the server already sends for every visible actor
## rather than from a new packet: the damage is in the difference, and asking
## for it separately would be asking twice for something already on the wire.
##
## Three switches rather than one, because the three cases are wanted in
## different situations: your own damage while soloing, other players' while
## healing a party, creatures' while judging whether a fight is going your way.
func _report_health_change(actor_id: int, health: int, max_health: int,
		actor: ReplicatedActor3D) -> void:
	var previous: Variant = _actor_health_seen.get(actor_id)
	_actor_health_seen[actor_id] = health
	if max_health <= 0 or not (previous is int):
		return
	var delta: int = health - int(previous)
	if delta == 0:
		return
	var is_self: bool = actor_id == AppState.local_actor_id
	var option: String = ("damage_numbers_self" if is_self
		else ("damage_numbers_players" if _is_player_actor(actor_id)
			else "damage_numbers_creatures"))
	if not bool(_hud_element_options.get(option, true)):
		return
	_spawn_health_change_label(actor, delta)

func _is_player_actor(actor_id: int) -> bool:
	var actor_value: Variant = AppState.actors.get(actor_id)
	if not actor_value is Dictionary:
		return false
	return int((actor_value as Dictionary).get("kind", 0)) == 0

## The same rise-and-fade the experience labels use, over whichever actor took
## the hit rather than always over the player.
func _spawn_health_change_label(actor: ReplicatedActor3D, delta: int) -> void:
	if not game_view.visible or not is_instance_valid(actor):
		return
	var priority: bool = _crowd_priority_actor(actor.actor_id)
	# A body too far away to be drawn floats no number either, and past the
	# live-effect budget only the player's own fight still does.
	if crowd.effects and not priority and not actor.is_drawn():
		return
	var now := Time.get_ticks_msec()
	for active: Label in _active_floating_labels:
		if is_instance_valid(active) and int(active.get_meta("feedback_actor", -1)) == actor.actor_id \
				and int(active.get_meta("feedback_sign", 0)) == signi(delta) \
				and now - int(active.get_meta("feedback_started", 0)) < 200:
			var amount := int(active.text) + delta
			active.text = "+%d" % amount if amount > 0 else str(amount)
			return
	var world_position: Vector3 = actor.global_position + Vector3(0.0, 2.45, 0.0)
	if gameplay_camera.is_position_behind(world_position):
		return
	var viewport_position: Vector2 = gameplay_camera.unproject_position(world_position)
	var viewport_scale := Vector2.ONE
	if main_viewport.size.x > 0 and main_viewport.size.y > 0:
		viewport_scale = viewport_container.size / Vector2(main_viewport.size)
	var screen_position: Vector2 = (viewport_container.position
		+ viewport_position * viewport_scale)
	if not effect_budget.admit(&"number", priority):
		return
	var label: Label = Label.new()
	label.set_meta("feedback_actor", actor.actor_id)
	label.set_meta("feedback_sign", signi(delta))
	label.set_meta("feedback_started", now)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 15)
	label.add_theme_color_override("font_outline_color", Color(0.015, 0.02, 0.025, 0.98))
	label.add_theme_constant_override("outline_size", 4)
	label.text = ("+%d" % delta) if delta > 0 else str(delta)
	label.add_theme_color_override("font_color",
		Color(0.42, 0.94, 0.45, 1.0) if delta > 0 else Color(0.96, 0.36, 0.30, 1.0))
	_floating_feedback_layer.add_child(label)
	effect_budget.track(label, &"number")
	label.reset_size()
	label.position = Vector2(screen_position.x - label.size.x * 0.5,
		_floating_feedback_row(screen_position.y, screen_position.y))
	_active_floating_labels.append(label)
	var tween: Tween = create_tween().set_parallel(true)
	tween.tween_property(label, "position",
		label.position - Vector2(0.0, FLOATING_FEEDBACK_RISE),
		FLOATING_FEEDBACK_LIFETIME).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.tween_property(label, "modulate:a", 0.0,
		FLOATING_FEEDBACK_LIFETIME - FLOATING_FEEDBACK_FADE_DELAY).set_delay(
		FLOATING_FEEDBACK_FADE_DELAY)
	tween.finished.connect(func() -> void:
		_active_floating_labels.erase(label)
		label.queue_free())

## One skill's experience for the statistics table.
##
## The wide packet is only resent at point boundaries below the wire limit.
## Keep using live stats there, and prefer the wide total once stats saturate.
func _experience_total(skill: String, stats: Dictionary) -> int:
	var earned: int = int(stats.get(skill + "_exp", 0))
	var wide: Variant = AppState.experience64.get(skill)
	if wide is Dictionary and (earned >= 0xFFFFFFFF or not stats.has(skill + "_exp")):
		return int((wide as Dictionary).get("experience", earned))
	return earned

## At the cap, earned XP and post-cap points replace the unreachable next level.
func _experience_text(skill: String, stats: Dictionary) -> String:
	var earned: int = _experience_total(skill, stats)
	if _skill_is_capped(skill, stats):
		var wide: Variant = AppState.experience64.get(skill)
		var points: int = int((wide as Dictionary).get("post_cap_points", 0)) \
			if wide is Dictionary else 0
		if points > 0:
			return "%s (+%d) · Max level" % [_grouped(earned), points]
		return "%s · Max level" % _grouped(earned)
	return "%s / %s" % [_grouped(earned),
		_grouped(int(stats.get(skill + "_exp_next", 0)))]

## An inventory or equipment slot's icon, drawn worn when the server says that
## slot holds worn goods. The slot rather than the image id is what decides it:
## a degraded item shares its artwork with the fresh one it came from, so the
## picture alone cannot answer the question - which is exactly why Eternal
## Lands drew the worn one mirrored instead of giving it a second icon.
func _slot_icon(image_id: int, slot: int) -> Texture2D:
	if AppState.is_worn_slot(slot):
		var worn: Texture2D = item_atlas.worn_icon_for(image_id)
		if worn != null:
			return worn
	return item_atlas.icon_for(image_id)

## The same decision for a window that knows the item's name instead of a slot.
func _named_icon(image_id: int, name: String) -> Texture2D:
	if AppState.is_degraded_item(name):
		var worn: Texture2D = item_atlas.worn_icon_for(image_id)
		if worn != null:
			return worn
	return item_atlas.icon_for(image_id)

func _inventory_description_for(slot: int) -> Dictionary:
	var items: Array = AppState.inventory_state.get("items", []) as Array
	# The server replaces the list whole with each command 226, so the list's
	# identity says whether the map built from it still holds.
	if not is_same(items, _described_source):
		_described_source = items
		_described_slots.clear()
		for entry: Variant in items:
			if entry is Dictionary:
				_described_slots[int((entry as Dictionary).get("slot", -1))] = entry
	var described: Dictionary = _described_slots.get(slot, {}) as Dictionary
	var item: Dictionary = AppState.inventory.get(slot, {}) as Dictionary
	if not described.is_empty() and int(described.get("image_id", -1)) != int(item.get("image_id", -2)):
		return {}
	return described

## Walk mode is Eternal Lands' move action, so a click there lifts the item
## onto the cursor instead of only selecting it. Every other mode keeps the
## select-and-inspect behaviour.
## The six quantity boxes along the bottom of the inventory, as the legacy
## client has them: a left click selects one, a right click edits it, and an
## edit left empty falls back to that box's default.
func _build_inventory_quantity_boxes() -> void:
	for index: int in range(INVENTORY_QUANTITY_DEFAULTS.size()):
		var button: Button = Button.new()
		button.custom_minimum_size = Vector2(0.0, 26.0)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.focus_mode = Control.FOCUS_NONE
		button.toggle_mode = true
		button.pressed.connect(_on_quantity_box_pressed.bind(index))
		button.gui_input.connect(_on_quantity_box_gui_input.bind(index))
		inventory_quantity_bar.add_child(button)
		inventory_quantity_buttons.append(button)
	inventory_quantity_edit.max_length = INVENTORY_QUANTITY_DIGITS
	inventory_quantity_edit.text_submitted.connect(_on_quantity_edit_submitted)
	inventory_quantity_edit.focus_exited.connect(_commit_quantity_edit)
	_sync_inventory_quantity_boxes()

func _sync_inventory_quantity_boxes() -> void:
	for index: int in range(inventory_quantity_buttons.size()):
		var button: Button = inventory_quantity_buttons[index]
		button.text = str(_inventory_quantities[index])
		button.set_pressed_no_signal(index == _selected_quantity_box)
		button.tooltip_text = ("Use %d for drops and pick-ups. Right click to change it."
			% _inventory_quantities[index])

## The amount every drop and pick-up uses until the player picks another box.
func _selected_quantity() -> int:
	if _selected_quantity_box < 0 or _selected_quantity_box >= _inventory_quantities.size():
		return 1
	return maxi(1, _inventory_quantities[_selected_quantity_box])

func _on_quantity_box_pressed(index: int) -> void:
	_commit_quantity_edit()
	_selected_quantity_box = index
	_sync_inventory_quantity_boxes()
	_save_hud_settings()

func _on_quantity_box_gui_input(event: InputEvent, index: int) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse: InputEventMouseButton = event as InputEventMouseButton
	if not mouse.pressed or mouse.button_index != MOUSE_BUTTON_RIGHT:
		return
	_begin_quantity_edit(index)
	inventory_quantity_buttons[index].accept_event()

func _begin_quantity_edit(index: int) -> void:
	var button: Button = inventory_quantity_buttons[index]
	_editing_quantity_box = index
	inventory_quantity_edit.text = str(_inventory_quantities[index])
	inventory_quantity_edit.size = button.size
	inventory_quantity_edit.scale = inventory_panel.get_global_transform().get_scale()
	inventory_quantity_edit.global_position = button.global_position
	inventory_quantity_edit.visible = true
	inventory_quantity_edit.grab_focus()
	inventory_quantity_edit.select_all()

func _on_quantity_edit_submitted(_text: String) -> void:
	_commit_quantity_edit()

## An empty or unreadable box resets to its default rather than becoming zero,
## which would make every later drop a no-op.
func _commit_quantity_edit() -> void:
	var index: int = _editing_quantity_box
	if index < 0:
		return
	_editing_quantity_box = -1
	var typed: String = inventory_quantity_edit.text.strip_edges()
	var value: int = (int(typed) if typed.is_valid_int()
		else INVENTORY_QUANTITY_DEFAULTS[index])
	_inventory_quantities[index] = clampi(value, 1, INVENTORY_QUANTITY_MAX)
	_selected_quantity_box = index
	inventory_quantity_edit.visible = false
	inventory_quantity_edit.release_focus()
	_sync_inventory_quantity_boxes()
	_save_hud_settings()

func _carry_enabled() -> bool:
	return _interaction_mode == "walk"

func _begin_carry(slot: int) -> void:
	var item_value: Variant = AppState.inventory.get(slot)
	if not item_value is Dictionary:
		return
	var item: Dictionary = item_value as Dictionary
	_storage_carried_position = -1
	_storage_carried_item = {}
	_carried_slot = slot
	carried_item.texture = _slot_icon(int(item.get("image_id", 0)), slot)
	var quantity: int = int(item.get("quantity", 0))
	(carried_item.get_node("Quantity") as Label).text = (str(quantity)
		if quantity > 1 else "")
	carried_item.visible = true
	_update_carried_item()

## Lifts a stored stack onto the cursor, as the reference storage window does.
## Each click on the backpack then withdraws the selected quantity into
## whichever slot the server picks, and the stack stays in hand until what is
## left is no more than one click takes.
func _begin_storage_carry(position: int) -> void:
	if bool(AppState.storage.get("read_only", false)): return
	var item_value: Variant = (AppState.storage.get("items", {}) as Dictionary).get(position)
	if not item_value is Dictionary:
		return
	var item: Dictionary = item_value as Dictionary
	var item_name: String = _storage_name_of(position)
	_carried_slot = -1
	_storage_carried_position = position
	_storage_carried_item = {"image_id": int(item.get("image_id", 0)), "name": item_name,
		"category_id": int(AppState.storage.get("category_id", -1))}
	carried_item.texture = _named_icon(int(item.get("image_id", 0)), item_name)
	carried_item.visible = true
	_update_carried_item()
	_sync_inventory()

## True while anything rides the cursor: a backpack or worn item, or a stack
## lifted out of storage.
func _has_carry() -> bool:
	return _carried_slot >= 0 or _storage_carried_position >= 0

func _cancel_carry() -> void:
	_carried_slot = -1
	_storage_carried_position = -1
	_storage_carried_item = {}
	carried_item.visible = false
	carried_item.texture = null
	_sync_inventory()

func _update_carried_item() -> void:
	if not _has_carry():
		return
	var quantity := 0
	if _storage_carried_position >= 0:
		# Withdrawn to nothing, another category opened, or storage closed.
		var stored: Dictionary = _storage_carry_item()
		if stored.is_empty():
			_cancel_carry()
			return
		quantity = int(stored.get("quantity", 0))
	else:
		# The server may empty the slot underneath us - a stack consumed, a
		# trade settled, the last of a stack dropped - and a cursor still
		# holding a phantom would place nothing.
		if not AppState.inventory.has(_carried_slot):
			_cancel_carry()
			return
		# The count in hand follows the authoritative slot, so dropping part
		# of the stack shows what is left to keep dropping.
		quantity = int((AppState.inventory.get(_carried_slot, {})
			as Dictionary).get("quantity", 0))
	(carried_item.get_node("Quantity") as Label).text = (str(quantity)
		if quantity > 1 else "")
	carried_item.global_position = (get_viewport().get_mouse_position()
		- carried_item.size * 0.5)

## The stored stack in hand as the server's latest list has it, or an empty
## dictionary once it is gone. A kind of item coming into storage or leaving
## it shifts every position after it, so the carry follows its item by picture
## and name rather than trusting the position it was picked up at.
func _storage_carry_item() -> Dictionary:
	if (_storage_carried_position < 0 or not bool(AppState.storage.get("open", false))
			or int(AppState.storage.get("category_id", -1))
				!= int(_storage_carried_item.get("category_id", -1))):
		return {}
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	if _is_storage_carry_at(_storage_carried_position, items):
		return items[_storage_carried_position] as Dictionary
	for raw_position: Variant in items:
		if _is_storage_carry_at(int(raw_position), items):
			_storage_carried_position = int(raw_position)
			return items[raw_position] as Dictionary
	return {}

func _is_storage_carry_at(position: int, items: Dictionary) -> bool:
	var item_value: Variant = items.get(position)
	return (item_value is Dictionary
		and int((item_value as Dictionary).get("image_id", -1))
			== int(_storage_carried_item.get("image_id", -2))
		and _storage_name_of(position) == str(_storage_carried_item.get("name", "")))

## Whether the open category's stock and its descriptions have both arrived.
## Until they have, a position may name a different item than the one shown.
func _storage_stock_ready() -> bool:
	var category_id: int = int(AppState.storage.get("category_id", -1))
	return (int(AppState.storage.get("items_category_id", category_id)) == category_id
		and int(AppState.storage.get("described_category_id", category_id)) == category_id)

## A click on the backpack with a stored stack in hand withdraws the selected
## quantity. The server chooses the slot, as it does for the Withdraw button.
func _withdraw_storage_carry() -> void:
	var stored: Dictionary = _storage_carry_item()
	if stored.is_empty():
		_cancel_carry()
		return
	if not _storage_stock_ready():
		return
	var available: int = maxi(1, int(stored.get("quantity", 1)))
	var quantity: int = mini(available, _selected_quantity())
	var error: Error = Network.withdraw_storage(_storage_carried_position, quantity)
	if error != OK:
		# Nothing was sent, so nothing left storage.
		push_warning("WITHDRAW_ITEM failed: " + error_string(error))
		return
	if quantity >= available:
		_cancel_carry()

## A click on the storage grid with a backpack item in hand deposits the
## selected quantity. As with drops on the ground, the rest stays in hand for
## the next click and the hand empties with the stack.
func _deposit_carry() -> void:
	var slot: int = _carried_slot
	var item_value: Variant = AppState.inventory.get(slot)
	if not item_value is Dictionary:
		_cancel_carry()
		return
	if slot >= 36:
		inventory_description.text = "Take that off before storing it."
		return
	var available: int = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
	var quantity: int = mini(available, _selected_quantity())
	var error: Error = Network.deposit_storage(slot, quantity)
	if error != OK:
		push_warning("DEPOSIT_ITEM failed: " + error_string(error))
		return
	if quantity >= available:
		_cancel_carry()

## Alt+click stores a whole backpack stack while storage is open, the
## reference items window's quick store.
func _store_inventory_stack(slot: int) -> void:
	var quantity: int = int((AppState.inventory.get(slot, {}) as Dictionary).get("quantity", 0))
	if quantity <= 0:
		return
	var error: Error = Network.deposit_storage(slot, quantity)
	if error != OK:
		inventory_description.text = "Could not store the stack: " + error_string(error)
		push_warning("DEPOSIT_ITEM failed: " + error_string(error))
		return
	inventory_description.text = "Storing %s from slot %d." % [_grouped(quantity), slot + 1]

## Answers the placing click. Equipping, unequipping and reordering are all the
## same authoritative move; only the destination slot differs, and the server
## decides whether it is allowed.
func _place_carry(destination: int) -> void:
	var source: int = _carried_slot
	if source < 0 or source == destination:
		_cancel_carry()
		return
	_carried_slot = -1
	carried_item.visible = false
	carried_item.texture = null
	_move_inventory_item(source, destination)
	_sync_inventory()

## Clicking the world puts the stack down. The server answers by creating a
## bag on the tile, or by adding to the bag already standing there. Dropping
## part of the stack keeps the rest in hand, so more clicks keep dropping;
## the hand only empties with the stack (Ctrl drops it whole).
func _drop_carry() -> void:
	var source: int = _carried_slot
	if source < 0:
		return
	var item_value: Variant = AppState.inventory.get(source)
	if not item_value is Dictionary:
		_cancel_carry()
		return
	var available: int = maxi(1, int((item_value as Dictionary).get("quantity", 1)))
	var quantity: int = (available if Input.is_key_pressed(KEY_CTRL)
		else mini(available, _selected_quantity()))
	var error: Error = Network.drop_inventory_item(source, quantity)
	if error != OK:
		# Nothing was sent, so nothing left the hand.
		push_warning("DROP_ITEM failed: " + error_string(error))
		return
	if quantity >= available:
		_cancel_carry()
		return
	_sync_inventory()

func _on_inventory_slot_pressed(slot: int) -> void:
	# A stored stack in hand is withdrawn by any click on the backpack, full
	# slot or empty; the server picks where it lands.
	if _storage_carried_position >= 0:
		_withdraw_storage_carry()
		return
	if _carried_slot >= 0:
		_place_carry(slot)
		return
	# Nothing in hand and nothing here: nothing to do. A selection is not a
	# carry, and must not pull the last item touched across.
	if not AppState.inventory.has(slot):
		return
	# Ctrl+click drops the whole stack to the ground, whatever tool is in
	# hand - the reference items window's "Left-click +ctrl to drop all".
	# Worn slots stay out of it: worn gear is unequipped first, as there.
	if slot < 36 and Input.is_key_pressed(KEY_CTRL):
		_drop_inventory_stack(slot)
		return
	selected_inventory_slot = slot
	AppState.inventory_text = ""
	_apply_inventory_tool(slot)
	_sync_equipment_slots()
	_sync_inventory()

## Drops all of one carried stack. The server answers by creating a bag at
## your feet, or by adding to the one already standing there.
func _drop_inventory_stack(slot: int) -> void:
	var item: Dictionary = AppState.inventory.get(slot, {}) as Dictionary
	var quantity: int = int(item.get("quantity", 0))
	if quantity <= 0:
		return
	var error: Error = Network.drop_inventory_item(slot, quantity)
	if error != OK:
		inventory_description.text = "Could not drop the stack: " + error_string(error)
		push_warning("DROP_ITEM failed: " + error_string(error))
		return
	inventory_description.text = "Dropped %s from slot %d into the bag at your feet." % [
		_grouped(quantity), slot + 1]
	_sync_inventory()

## Carries out the current tool on a slot. Every tool but a pick-up ends by
## asking the server what the item is, because the line along the bottom of the
## window should say what was last touched whichever tool was in hand; only
## Inspect lets the answer open the detail window. Lifting an item onto the
## cursor asks nothing, as in the reference client: the line is written from
## what the client already knows, and a look per pick-up was a packet per move.
func _apply_inventory_tool(slot: int) -> void:
	match _inventory_tool:
		"use":
			if slot < 36:
				_use_inventory_slot(slot)
		"equip":
			if slot < 36:
				var wear: int = _first_empty_slot(36, 44)
				if wear >= 0:
					_move_inventory_item(slot, wear)
		"unequip":
			if slot >= 36:
				var carry: int = _first_empty_slot(0, 36)
				if carry >= 0:
					_move_inventory_item(slot, carry)
		"grab":
			if _carry_enabled():
				_begin_carry(slot)
				return
	_describe_slot(slot, _inventory_tool == "inspect")

## Asks the server what an item is. `with_window` decides whether the reply is
## allowed to open the detail window; the short line is written either way.
func _describe_slot(slot: int, with_window: bool) -> void:
	_detail_popup_allowed = with_window
	if extension_windows != null:
		extension_windows.set("detail_popup_allowed", with_window)
	inventory_description.text = "[%s]  Asking about slot %d…" % [
		str(INVENTORY_TOOL_LABELS.get(_inventory_tool, _inventory_tool)), slot + 1]
	var error: Error = Network.look_at_inventory_item(slot)
	if error != OK:
		push_warning("LOOK_AT_INVENTORY_ITEM failed: " + error_string(error))

## Right-clicking an item takes the next tool and describes what is under the
## cursor without opening anything, so the player can see what the new tool
## would act on before using it. Usable items keep Use in the cycle during a
## cooldown; the use action itself waits until the item is ready.
func _cycle_inventory_tool(slot: int) -> void:
	var index: int = INVENTORY_TOOLS.find(_inventory_tool)
	var next_tool: String = INVENTORY_TOOLS[(index + 1) % INVENTORY_TOOLS.size()]
	if next_tool == "use" and not _slot_has_usable_item(slot):
		next_tool = "inspect"
	_set_inventory_tool(next_tool)
	if AppState.inventory.has(slot):
		selected_inventory_slot = slot
		_describe_slot(slot, false)
	_sync_inventory()

## The four action buttons are the same mechanism as the right-click cycle:
## each one takes its tool, and applies it at once to whatever is already
## selected, so a player can work either way round.
func _choose_inventory_tool(tool: String) -> void:
	_set_inventory_tool(tool)
	if selected_inventory_slot >= 0 and AppState.inventory.has(selected_inventory_slot):
		_apply_inventory_tool(selected_inventory_slot)
	_sync_inventory()

func _set_inventory_tool(tool: String) -> void:
	_inventory_tool = tool
	_sync_inventory_tool_buttons()

## The buttons show which tool is in hand, since the cursor does not change.
func _sync_inventory_tool_buttons() -> void:
	for pair: Array in [[inventory_use_button, "use"],
			[inventory_equip_button, "equip"],
			[inventory_unequip_button, "unequip"],
			[inventory_inspect_button, "inspect"]]:
		var button: Button = pair[0] as Button
		if button != null:
			button.button_pressed = _inventory_tool == str(pair[1])

func _on_inventory_slot_gui_input(event: InputEvent, slot: int) -> void:
	if not event is InputEventMouseButton:
		return
	var mouse: InputEventMouseButton = event as InputEventMouseButton
	if not mouse.pressed:
		return
	# A right click puts back whatever is in hand before it does anything
	# else, as in the reference client; only an empty hand cycles the tool.
	if mouse.button_index == MOUSE_BUTTON_RIGHT:
		if _has_carry():
			_cancel_carry()
		else:
			_cycle_inventory_tool(slot)
		get_viewport().set_input_as_handled()
		return
	if mouse.button_index != MOUSE_BUTTON_LEFT:
		return
	# Alt+click stores the whole stack while storage is open. Read from the
	# event, which carries the modifier the click was made with.
	if (mouse.alt_pressed and not _has_carry() and slot < 36
			and AppState.inventory.has(slot)
			and bool(AppState.storage.get("open", false))):
		_store_inventory_stack(slot)
		get_viewport().set_input_as_handled()
		return
	# Double-clicking a stack wears it, and double-clicking a worn piece
	# takes it off - whichever tool is in hand. The event is taken here so
	# the button never sees the second press: without that the grab tool
	# would place the carry the first click picked up, and the move would
	# race the one this sends. With a stored stack in hand every click is
	# another withdrawal, so a quick second one is left to the button.
	if (mouse.double_click and _storage_carried_position < 0
			and AppState.inventory.has(slot)):
		if slot < 36:
			_equip_inventory_slot(slot)
		else:
			_unequip_inventory_slot(slot)
		get_viewport().set_input_as_handled()

## The wear position a double-click asks for: a free one where there is
## one, and otherwise the first, which the server overrules with the
## position of the piece being replaced. All eight are only ever full
## when one of every kind is worn, so there is always such a piece.
func _wear_destination() -> int:
	var wear: int = _first_empty_slot(36, 44)
	return wear if wear >= 0 else 36

## Wears what is in a backpack slot. The wear position sent is only a
## suggestion: the server puts the piece where the piece it replaces was
## standing, so swapping a helmet for a helmet keeps the position the player
## gave it, and a piece with nothing to replace takes a free position -
## worn gear it can be worn alongside is never taken off to make room.
func _equip_inventory_slot(slot: int) -> void:
	# The first of the two clicks may have picked the stack up. The second is
	# not a placing click, so the hand is emptied before the move is sent.
	if _carried_slot >= 0:
		_cancel_carry()
	selected_inventory_slot = slot
	_move_inventory_item(slot, _wear_destination())
	_sync_inventory()
	# After the refresh, which would otherwise write the server's last
	# inventory line over this one.
	inventory_description.text = "[%s]  Wearing what is in slot %d…" % [
		str(INVENTORY_TOOL_LABELS.get("equip", "Equip")), slot + 1]

## The backpack slot a double-click asks to unequip into: the first free
## one, or -1 with none free. Unlike wearing, there is no piece already
## standing at the destination for the server to have swapped out, so
## with nothing free the move is not sent - the same rule the Unequip
## tool already follows.
func _unequip_destination() -> int:
	return _first_empty_slot(0, 36)

## Takes off what is worn in an equipment slot.
func _unequip_inventory_slot(slot: int) -> void:
	if _carried_slot >= 0:
		_cancel_carry()
	selected_inventory_slot = slot
	var carry: int = _unequip_destination()
	if carry < 0:
		inventory_description.text = "Your backpack has no free slot to take that off into."
		_sync_inventory()
		return
	_move_inventory_item(slot, carry)
	_sync_inventory()
	# After the refresh, which would otherwise write the server's last
	# inventory line over this one.
	inventory_description.text = "[%s]  Taking off equipped position %d…" % [
		str(INVENTORY_TOOL_LABELS.get("unequip", "Unequip")), slot - 35]

## Composes the one-line summary written along the bottom of the inventory when
## the server describes an item. It reports only what arrived in the reply.
func _short_item_line() -> String:
	var detail: Dictionary = AppState.item_detail
	var parts: Array[String] = []
	var item_name: String = str(detail.get("name", ""))
	if not item_name.is_empty():
		parts.append(item_name)
	var category: String = str(detail.get("category", ""))
	if not category.is_empty():
		parts.append(category)
	var quantity: int = int(detail.get("quantity", 0))
	if quantity > 1:
		parts.append("x%s" % _grouped(quantity))
	if bool(detail.get("equipped", false)):
		parts.append("equipped")
	if parts.is_empty():
		return ""
	return "[%s]  %s" % [
		str(INVENTORY_TOOL_LABELS.get(_inventory_tool, _inventory_tool)),
		"  -  ".join(parts)]

func _on_equipment_slot_pressed(slot: int) -> void:
	# A stored stack is withdrawn into the backpack, never straight onto the
	# body; the reference equipment grid ignores it the same way.
	if _storage_carried_position >= 0:
		return
	if _carried_slot >= 0:
		_place_carry(slot)
		return
	if not AppState.inventory.has(slot):
		return
	selected_inventory_slot = slot
	_apply_inventory_tool(slot)
	_sync_equipment_slots()
	_sync_inventory()

func _first_empty_slot(start: int, end: int) -> int:
	for slot: int in range(start, end):
		if not AppState.inventory.has(slot):
			return slot
	return -1

func _move_inventory_item(source: int, destination: int) -> void:
	var error: Error = Network.move_inventory_item(source, destination)
	if error != OK:
		push_warning("MOVE_INVENTORY_ITEM failed: " + error_string(error))

func _on_quick_slot_pressed(slot: int) -> void:
	_use_inventory_slot(slot)

func _use_inventory_slot(slot: int) -> void:
	var item_value: Variant = AppState.inventory.get(slot)
	if not item_value is Dictionary:
		return
	var item: Dictionary = item_value as Dictionary
	if not bool(item.get("inventory_usable", false)) or _inventory_cooldown_remaining(slot) > 0:
		return
	var error: Error = Network.use_inventory_item(slot)
	if error != OK:
		push_warning("USE_INVENTORY_ITEM failed: " + error_string(error))

## Console history and tab completion. Up and down walk what has been sent,
## Tab completes a command this client answers itself - a name the server owns
## is not completed here, because the client does not have that list.
func _on_chat_input_gui_input(event: InputEvent) -> void:
	if not event is InputEventKey or not (event as InputEventKey).pressed:
		return
	var key: InputEventKey = event as InputEventKey
	match key.physical_keycode:
		KEY_UP:
			_recall_console_history(-1)
		KEY_DOWN:
			_recall_console_history(1)
		KEY_TAB:
			_complete_console_command()
		_:
			return
	chat_input.accept_event()

func _recall_console_history(step: int) -> void:
	if _console_history.is_empty():
		return
	_console_history_index = clampi(_console_history_index + step, 0,
		_console_history.size())
	chat_input.text = ("" if _console_history_index >= _console_history.size()
		else _console_history[_console_history_index])
	chat_input.caret_column = chat_input.text.length()

func _complete_console_command() -> void:
	var typed: String = chat_input.text.strip_edges()
	if not typed.begins_with("#") or typed.contains(" "):
		return
	var matches: Array[String] = console_commands.completions(typed)
	if matches.is_empty():
		return
	if matches.size() == 1:
		chat_input.text = matches[0] + " "
		chat_input.caret_column = chat_input.text.length()
		return
	# More than one: complete as far as they agree and show the choices.
	var shared: String = matches[0]
	for candidate: String in matches:
		while not candidate.begins_with(shared) and shared.length() > typed.length():
			shared = shared.substr(0, shared.length() - 1)
	chat_input.text = shared
	chat_input.caret_column = shared.length()
	AppState.append_local_line("  ".join(matches))

func _on_chat_submitted(text: String) -> void:
	var message: String = text.strip_edges()
	if message.is_empty():
		_hide_chat_input()
		return
	_console_history.append(message)
	if _console_history.size() > CONSOLE_HISTORY_LIMIT:
		_console_history.remove_at(0)
	_console_history_index = _console_history.size()
	message = console_commands.expand(message)
	# A command this client answers itself never reaches the server: the
	# server has no opinion about who the player is ignoring. `#help` is the
	# exception - the client lists its half and the server answers with the
	# commands it takes from this player.
	var local: ConsoleCommands.Result = console_commands.run(
		message, AppState.chat_history)
	if local.handled:
		for line: String in local.lines:
			AppState.append_local_line(line)
		if local.changed:
			_save_hud_settings()
			_sync_map_markers()
			# Apply ignore/unignore and word-filter changes to existing lines too.
			_sync_chat()
			_sync_console()
		if local.send_on:
			var sent: Error = Network.send_chat("#help")
			if sent != OK:
				push_warning("RAW_TEXT failed: " + error_string(sent))
		chat_input.clear()
		_hide_chat_input()
		return
	# `#emote <name>` is the server's command, but it has a packet of its own,
	# so the client sends that rather than the text. The server answers the
	# typed form too, for a client that has no `DO_EMOTE`.
	if message.begins_with("#emote "):
		var wanted: String = message.substr(7).strip_edges()
		if not wanted.is_empty():
			var emote_error: Error = Network.do_emote(wanted)
			if emote_error == OK:
				chat_input.clear()
				_hide_chat_input()
			else:
				push_warning("DO_EMOTE failed: " + error_string(emote_error))
			return
	message = _chat_message_for_tab(message)
	if message.is_empty():
		AppState.append_local_message("Choose a private recipient or an available joined channel before sending.")
		return
	var is_private := message.begins_with("/") and message.length() > 1
	var error: Error = (Network.send_private_message(message.substr(1))
		if is_private else Network.send_chat(message))
	if error == OK:
		chat_input.clear()
		_hide_chat_input()
	else:
		push_warning(("SEND_PM" if is_private else "RAW_TEXT")
			+ " failed: " + error_string(error))

func _sync_trade() -> void:
	var is_open: bool = bool(AppState.trade.get("open", false))
	trade_panel.visible = is_open
	if not is_open:
		selected_trade_side = ""
		trade_was_open = false
		trade_source_type.select(0)
		_reset_trade_destinations()
		return
	if not trade_was_open:
		trade_was_open = true
		_reset_trade_destinations()
	if not bool(AppState.trade.get("storage_available", false)):
		_reset_trade_destinations()
		trade_source_type.select(0)
	trade_source_type.set_item_disabled(1, not bool(AppState.trade.get("storage_available", false)))
	var from_storage: bool = trade_source_type.get_selected_id() == 2
	trade_storage_category.visible = from_storage
	trade_storage_category.clear()
	for category: Dictionary in AppState.storage.get("categories", []):
		var category_id: int = int(category.get("id", -1))
		trade_storage_category.add_item(str(category.get("name", "Category")), category_id)
		if category_id == int(AppState.storage.get("category_id", -1)):
			trade_storage_category.select(trade_storage_category.item_count - 1)
	inventory_panel.hide()
	stats_panel.hide()
	full_map.hide()
	storage_panel.hide()
	if classic_storage != null:
		classic_storage.refresh()
	manufacturing_panel.hide()
	trade_partner.text = "Trading with %s%s" % [
		str(AppState.trade.get("partner", "another player")),
		" — storage trading available" if bool(
			AppState.trade.get("storage_available", false)) else ""]
	_fill_trade_list(trade_source, _trade_source_items(), "Storage" if from_storage else "Inventory")
	_fill_trade_list(trade_own_offers,
		AppState.trade.get("own_offers", {}) as Dictionary, "Offer")
	_fill_trade_list(trade_other_offers,
		AppState.trade.get("other_offers", {}) as Dictionary, "Offer")
	var own_accepts: int = int(AppState.trade.get("own_accepts", 0))
	var other_accepts: int = int(AppState.trade.get("other_accepts", 0))
	trade_status.text = "You: %s  •  %s: %s" % [
		_trade_acceptance_text(own_accepts), str(AppState.trade.get("partner", "Partner")),
		_trade_acceptance_text(other_accepts)]
	if own_accepts == 0:
		trade_accept_button.text = "Accept offer (1/2)"
		trade_accept_button.disabled = false
	elif own_accepts == 1 and other_accepts >= 1:
		trade_accept_button.text = "Confirm trade (2/2)"
		trade_accept_button.disabled = false
	elif own_accepts == 1:
		trade_accept_button.text = "Waiting for partner"
		trade_accept_button.disabled = true
	else:
		trade_accept_button.text = "Confirmed — waiting"
		trade_accept_button.disabled = true
	trade_reject_button.disabled = own_accepts == 0 and other_accepts == 0
	_sync_trade_actions()

func _fill_trade_list(list_control: ItemList, items: Dictionary, prefix: String) -> void:
	list_control.clear()
	var slots: Array = items.keys()
	slots.sort()
	for raw_slot: Variant in slots:
		var slot: int = int(raw_slot)
		var item_value: Variant = items.get(slot)
		if not item_value is Dictionary:
			continue
		var item: Dictionary = item_value as Dictionary
		var image_id: int = int(item.get("image_id", 0))
		var index: int = list_control.item_count
		# Source type 1 is the offering player's backpack and 2 is their
		# storage, which is only offered where a storage NPC is in range for
		# both sides. Saying which it came from is the whole point of the
		# server sending it.
		var source: String = "  (storage)" if int(item.get("source_type", 1)) == 2 else ""
		var item_name: String = "Item #%d" % image_id
		if prefix == "Storage":
			var stored_name: String = _storage_name_of(slot)
			if not stored_name.is_empty():
				item_name = stored_name
		elif prefix == "Inventory":
			item_name = str(AppState.inventory_names.get(slot, item_name))
		var label: String = "%s ×%d%s" % [item_name, int(item.get("quantity", 0)), source]
		list_control.add_item(label)
		list_control.set_item_tooltip(index, label)
		list_control.set_item_metadata(index, slot)
		var icon: Texture2D = item_atlas.icon_for(image_id)
		if icon != null:
			list_control.set_item_icon(index, icon)

func _trade_list_slot(list_control: ItemList, index: int) -> int:
	if index < 0 or index >= list_control.item_count:
		return -1
	var metadata: Variant = list_control.get_item_metadata(index)
	return int(metadata) if metadata != null else -1

func _sync_trade_actions() -> void:
	trade_offer_button.disabled = trade_source.get_selected_items().is_empty()
	trade_remove_button.disabled = trade_own_offers.get_selected_items().is_empty()
	var selected_other: PackedInt32Array = trade_other_offers.get_selected_items()
	var destination_available: bool = (bool(AppState.trade.get("storage_available", false))
		and not selected_other.is_empty())
	trade_storage_destination.disabled = not destination_available
	var destination_is_storage: bool = false
	if destination_available:
		var offer_slot: int = _trade_list_slot(trade_other_offers, int(selected_other[0]))
		destination_is_storage = (offer_slot >= 0 and offer_slot < trade_destinations.size()
			and int(trade_destinations[offer_slot]) == 2)
	trade_storage_destination.set_pressed_no_signal(destination_is_storage)

func _reset_trade_destinations() -> void:
	trade_destinations.resize(16)
	trade_destinations.fill(1)

func _trade_acceptance_text(value: int) -> String:
	match value:
		1: return "accepted"
		2: return "confirmed"
		_: return "reviewing"

func _sync_storage() -> void:
	if bool(AppState.trade.get("open", false)):
		_sync_trade()
		return
	inventory_store_all.disabled = bool(AppState.storage.get("read_only", false))
	var is_open: bool = bool(AppState.storage.get("open", false))
	storage_panel.visible = is_open
	if not is_open:
		selected_storage_side = ""
		if _storage_carried_position >= 0:
			_cancel_carry()
		if classic_storage != null:
			classic_storage.refresh()
		return
	stats_panel.hide()
	trade_panel.hide()
	manufacturing_panel.hide()
	storage_categories.clear()
	var active_category: int = int(AppState.storage.get("category_id", -1))
	var raw_categories: Variant = AppState.storage.get("categories", [])
	if raw_categories is Array:
		for raw_category: Variant in raw_categories:
			if not raw_category is Dictionary:
				continue
			var category: Dictionary = raw_category as Dictionary
			var index: int = storage_categories.item_count
			storage_categories.add_item(str(category.get("name", "Category")))
			storage_categories.set_item_metadata(index, int(category.get("id", -1)))
			if int(category.get("id", -1)) == active_category:
				storage_categories.select(index)
	_sync_storage_organizer()
	_fill_storage_item_list(storage_items,
		AppState.storage.get("items", {}) as Dictionary, "Stored")
	var message: String = str(AppState.storage.get("text", ""))
	storage_status.text = (message if not message.is_empty() else
		"Select an inventory item to deposit or a stored item to withdraw.")
	_sync_storage_backpack()
	if classic_storage != null:
		classic_storage.refresh()

## The storage window's backpack column, which is all of it that follows the
## inventory.
func _sync_storage_backpack() -> void:
	var backpack: Dictionary = {}
	for raw_slot: Variant in AppState.inventory:
		var slot: int = int(raw_slot)
		if slot >= 0 and slot < 36:
			backpack[slot] = AppState.inventory[raw_slot]
	_fill_storage_item_list(storage_inventory, backpack, "Inventory")
	_sync_storage_actions()

## The sort orders the stored list offers, as (mode, label) pairs. The mode is
## the value `storage_sort_mode` holds and the dropdown carries as metadata.
const STORAGE_SORT_MODES: Array[Array] = [
	["name", "Name"], ["strength", "Strength"], ["rarity", "Rarity"]]
const STORAGE_RARITY_LABELS: Array[String] = [
	"Common", "Uncommon", "Rare", "Epic", "Legendary"]

func _build_storage_sort_modes() -> void:
	storage_sort.clear()
	for index: int in range(STORAGE_SORT_MODES.size()):
		var mode: Array = STORAGE_SORT_MODES[index]
		storage_sort.add_item(str(mode[1]))
		storage_sort.set_item_metadata(index, str(mode[0]))
		if str(mode[0]) == storage_sort_mode:
			storage_sort.select(index)

## The server's description of one stored position, or an empty dictionary
## where the server has not described it (an older server, or a row that
## arrived before its description did).
func _storage_description_for(position: int) -> Dictionary:
	var described: Variant = AppState.storage.get("described", {})
	if not described is Dictionary:
		return {}
	var row: Variant = (described as Dictionary).get(position)
	return row as Dictionary if row is Dictionary else {}

## Rebuilds the Type dropdown from whatever the open category actually holds,
## so each category offers exactly its own types and nothing else.
func _sync_storage_organizer() -> void:
	var items: Dictionary = AppState.storage.get("items", {}) as Dictionary
	var subtypes: Array[String] = []
	for raw_position: Variant in items:
		var subtype: String = str(_storage_description_for(
			int(raw_position)).get("subtype", ""))
		if not subtype.is_empty() and not subtypes.has(subtype):
			subtypes.append(subtype)
	subtypes.sort()
	# A category whose items are all one type has nothing to filter.
	var worth_filtering: bool = subtypes.size() > 1
	storage_type.disabled = not worth_filtering
	if not worth_filtering:
		storage_type_filter = ""
	if not subtypes.has(storage_type_filter):
		storage_type_filter = ""
	storage_type.clear()
	storage_type.add_item("All types")
	storage_type.set_item_metadata(0, "")
	for subtype: String in subtypes:
		var index: int = storage_type.item_count
		storage_type.add_item(subtype)
		storage_type.set_item_metadata(index, subtype)
		if subtype == storage_type_filter:
			storage_type.select(index)
	if storage_type_filter.is_empty():
		storage_type.select(0)

## Sorts descending for the numeric orders, because "best first" is what a
## player means by strength or rarity; name sorts A to Z. Ties fall back to
## the name so the list never reshuffles between identical redraws.
func _storage_sorted_positions(items: Dictionary) -> Array:
	var positions: Array = items.keys()
	positions.sort()
	var mode: String = storage_sort_mode
	var key: Array = [mode, positions, AppState.storage.get("described", {})]
	if key == _storage_sort_key:
		return _storage_sort_order.duplicate()
	# Copied, so a description edited in place cannot pass for the old one.
	_storage_sort_key = key.duplicate(true)
	_storage_sort_order = _storage_order_of(positions.duplicate(), mode)
	return _storage_sort_order.duplicate()

func _storage_order_of(positions: Array, mode: String) -> Array:
	# Each row is looked up once, not twice per comparison: sorting a full
	# category through the lookups cost milliseconds on every storage reply.
	var names: Dictionary = {}
	for raw_position: Variant in positions:
		names[raw_position] = _storage_name_of(int(raw_position))
	if mode == "name":
		positions.sort_custom(func(left: Variant, right: Variant) -> bool:
			return str(names[left]).naturalnocasecmp_to(str(names[right])) < 0)
		return positions
	var key: String = "strength" if mode == "strength" else "rarity"
	var values: Dictionary = {}
	for raw_position: Variant in positions:
		values[raw_position] = int(_storage_description_for(int(raw_position)).get(key, 0))
	positions.sort_custom(func(left: Variant, right: Variant) -> bool:
		var left_value: int = int(values[left])
		var right_value: int = int(values[right])
		if left_value == right_value:
			return str(names[left]).naturalnocasecmp_to(str(names[right])) < 0
		return left_value > right_value)
	return positions

func _storage_name_of(position: int) -> String:
	return str(_storage_description_for(position).get("name", ""))

func _on_storage_type_selected(index: int) -> void:
	var metadata: Variant = storage_type.get_item_metadata(index)
	storage_type_filter = str(metadata) if metadata != null else ""
	_fill_storage_item_list(storage_items,
		AppState.storage.get("items", {}) as Dictionary, "Stored")
	_sync_storage_actions()
	if classic_storage != null:
		classic_storage.refresh()

func _on_storage_sort_selected(index: int) -> void:
	var metadata: Variant = storage_sort.get_item_metadata(index)
	storage_sort_mode = str(metadata) if metadata != null else "name"
	_fill_storage_item_list(storage_items,
		AppState.storage.get("items", {}) as Dictionary, "Stored")
	_sync_storage_actions()
	if classic_storage != null:
		classic_storage.refresh()

## Rows are rewritten in place, and a row whose text and icon have not changed
## is left alone: shaping the text of every row again cost most of a storage
## reply, when a deposit changes one count. The selection is dropped, as a
## clear() dropped it, so it can never point at a row that now shows another
## item.
func _fill_storage_item_list(list_control: ItemList, items: Dictionary, prefix: String) -> void:
	list_control.deselect_all()
	var row := 0
	# Only the stored side is described by the server, so only it can be
	# organized; the inventory column keeps its plain positional order.
	var stored: bool = list_control == storage_items
	var positions: Array = _storage_sorted_positions(items) if stored else items.keys()
	if not stored:
		positions.sort()
	for raw_position: Variant in positions:
		var position: int = int(raw_position)
		var item_value: Variant = items.get(position)
		if not item_value is Dictionary:
			continue
		var item: Dictionary = item_value as Dictionary
		var described: Dictionary = _storage_description_for(position) if stored else {}
		if stored and not storage_type_filter.is_empty() \
				and str(described.get("subtype", "")) != storage_type_filter:
			continue
		var image_id: int = int(item.get("image_id", 0))
		var name: String = str(described.get("name", "")) if stored else str(AppState.inventory_names.get(position, ""))
		var label: String = ""
		if name.is_empty():
			label = "%s %d  •  item #%d  ×%d" % [prefix, position + 1,
				image_id, int(item.get("quantity", 0))]
		elif not stored:
			label = "%s  ×%d" % [name, int(item.get("quantity", 0))]
		else:
			label = "%s  ×%d  •  %s" % [name, int(item.get("quantity", 0)),
				_storage_row_detail(described)]
		var icon: Texture2D = _named_icon(image_id, name)
		# An item without a tooltip of its own shows its text as one.
		if row >= list_control.item_count:
			list_control.add_item(label, icon)
		else:
			if list_control.get_item_text(row) != label:
				list_control.set_item_text(row, label)
			if list_control.get_item_icon(row) != icon:
				list_control.set_item_icon(row, icon)
		list_control.set_item_metadata(row, position)
		row += 1
	while list_control.item_count > row:
		list_control.remove_item(list_control.item_count - 1)

## The trailing detail on a described row: its type, plus whichever figure
## the current sort is ordering by, so the ordering is legible on the row.
func _storage_row_detail(described: Dictionary) -> String:
	var subtype: String = str(described.get("subtype", ""))
	if storage_sort_mode == "strength":
		return "%s  •  strength %d" % [subtype, int(described.get("strength", 0))]
	if storage_sort_mode == "rarity":
		var rarity: int = clampi(int(described.get("rarity", 0)), 0,
			STORAGE_RARITY_LABELS.size() - 1)
		return "%s  •  %s" % [subtype, STORAGE_RARITY_LABELS[rarity]]
	return subtype

func _list_metadata_int(list_control: ItemList, index: int) -> int:
	if index < 0 or index >= list_control.item_count:
		return -1
	var metadata: Variant = list_control.get_item_metadata(index)
	return int(metadata) if metadata != null else -1

func _sync_storage_actions() -> void:
	if bool(AppState.storage.get("read_only", false)):
		storage_deposit_button.disabled = true
		storage_withdraw_button.disabled = true
		storage_inspect_button.disabled = storage_items.get_selected_items().is_empty()
		return
	var inventory_selected: bool = not storage_inventory.get_selected_items().is_empty()
	var storage_selected: bool = not storage_items.get_selected_items().is_empty()
	storage_deposit_button.disabled = not inventory_selected
	storage_withdraw_button.disabled = not storage_selected
	storage_inspect_button.disabled = not storage_selected

func _sync_selection() -> void:
	var dto: Dictionary = AppState.actors.get(AppState.selected_actor_id, {})
	if dto.is_empty():
		selected_target.text = "Target: none"
	else:
		selected_target.text = "Target: %s  Health: %d / %d%s" % [
			str(dto.get("name", "Actor %d" % AppState.selected_actor_id)),
			int(dto.get("health", 0)), int(dto.get("max_health", 0)),
			("  [combat]" if bool(dto.get("in_combat", false)) else "")
				+ ("  [hastened]" if (int(dto.get("buffs", 0))
					& EloriaProtocol.ACTOR_BUFF_DOUBLE_SPEED) != 0 else "")]
	var local_actor: Dictionary = AppState.actors.get(
		AppState.local_actor_id, {}) as Dictionary
	var aiming_at: int = int(local_actor.get("aiming_at", -1))
	if aiming_at >= 0:
		var aimed: Dictionary = AppState.actors.get(aiming_at, {}) as Dictionary
		selected_target.text = "Aiming at %s%s" % [
			str(aimed.get("name", "actor %d" % aiming_at)),
			"  Health: %d / %d" % [int(aimed.get("health", 0)),
				int(aimed.get("max_health", 0))] if not aimed.is_empty() else ""]
	var can_attack: bool = _is_attackable_actor(AppState.selected_actor_id, dto)
	attack_button.disabled = not can_attack
	attack_button.tooltip_text = ("Attack selected target [A] or Alt-click; the server approaches and validates combat"
		if can_attack else "Select a living player or creature to attack")
	var can_trade: bool = _is_tradeable_player(AppState.selected_actor_id, dto)
	look_button.disabled = not can_trade
	look_button.tooltip_text = ("Ask the server to describe the selected player"
		if can_trade else "Select a player to look at")
	# Never disabled: with nobody selected it arms trade mode instead.
	trade_button.tooltip_text = ("Request or accept trade with the selected player; both players must be within four tiles"
		if can_trade else "Arm trade, then click a player to request or accept a trade; both players must be within four tiles")
	# Only the actor losing the ring and the one gaining it change; a node built
	# later is given its answer when it is built. This ran over every actor after
	# every changed frame.
	if _selection_ring_actor != AppState.selected_actor_id:
		var previous: Variant = actor_nodes.get(_selection_ring_actor)
		if is_instance_valid(previous):
			(previous as ReplicatedActor3D).set_selected(false)
		_selection_ring_actor = AppState.selected_actor_id
	var selected: Variant = actor_nodes.get(AppState.selected_actor_id)
	if is_instance_valid(selected):
		(selected as ReplicatedActor3D).set_selected(true)

## What a left click on this actor does, in the terms the cursor table decides
## in. Its own function because the pointer and the click have to agree, and
## a test can now hold one against the other: MouseCursors.choose promised the
## sword over every live creature, in walk mode as much as attack mode, while
## the handler only ever attacked in attack mode or with Alt held. A plain
## click merely selected - which is why, mid-fight, clicking another of the
## creatures on you did nothing at all and the target could not be changed.
##
## A live creature is attacked by a plain click, the way the reference client
## does it (UNDER_MOUSE_ANIMAL in check_cursor_change). Players are not: the
## pointer offers them a look until attack mode or Alt says otherwise, and a
## stray click in a crowd must not open a fight with one.
func _actor_click_action(actor_id: int, dto: Dictionary,
		alt_pressed: bool, mode := "") -> String:
	if mode.is_empty():
		mode = _interaction_mode
	if dto.is_empty():
		return "none"
	# A spell waiting for an actor claims whoever is under the pointer, you
	# included; every other action here is about somebody else.
	if AppState.pending_spell_target == "actor":
		return "spell"
	if mode == "look" and int(dto.get("kind", 0)) in [1, 4] \
			and not alt_pressed:
		return "look"
	if actor_id == AppState.local_actor_id:
		return "none"
	if alt_pressed and _is_attackable_actor(actor_id, dto):
		return "attack"
	match mode:
		"attack":
			return "attack" if _is_attackable_actor(actor_id, dto) else "none"
		"trade":
			return "trade" if _is_tradeable_player(actor_id, dto) else "none"
		"use", "pick", "harvest", "look":
			return "none"
		"talk":
			return "talk" if (int(dto.get("kind", 0)) == 2 \
				or _is_tutorial_companion(actor_id) or ReplicatedActor3D.is_summon(dto)) else "none"
	# NPCs and summons are the two actors a plain click talks to. TOUCH_PLAYER
	# on your own summon is how the server opens the behaviour popup, so it
	# has to outrank the attack below - a summon is a creature kind.
	if int(dto.get("kind", 0)) == 2 or _is_tutorial_companion(actor_id) or ReplicatedActor3D.is_summon(dto):
		return "talk"
	if _is_creature_actor(dto) and _is_attackable_actor(actor_id, dto):
		return "attack"
	return "none"

## The kinds the cursor table reads as a creature rather than a player, so
## both halves of the promise draw the line in the same place.
func _is_creature_actor(dto: Dictionary) -> bool:
	return int(dto.get("kind", 0)) in [3, 5]

func _is_tutorial_companion(actor_id: int) -> bool:
	var tutorial: Dictionary = AppState.lantern_tutorial
	if not bool(tutorial.get("active", false)) or tutorial.get("tutorial", "") != "borrowed_sky":
		return false
	for companion_id: Variant in tutorial.get("talk_actor_ids", []):
		if int(companion_id) == actor_id:
			return true
	return false

func _is_attackable_actor(actor_id: int, dto: Dictionary) -> bool:
	if actor_id < 0 or actor_id == AppState.local_actor_id or dto.is_empty():
		return false
	if _is_tutorial_companion(actor_id):
		return false
	var kind: int = int(dto.get("kind", 0))
	return kind in [1, 3, 4, 5] and bool(dto.get("alive", int(dto.get("health", 0)) > 0))

func _is_tradeable_player(actor_id: int, dto: Dictionary) -> bool:
	if actor_id < 0 or actor_id == AppState.local_actor_id or dto.is_empty():
		return false
	if _is_tutorial_companion(actor_id):
		return false
	var kind: int = int(dto.get("kind", 0))
	return kind in [1, 4] and bool(dto.get("alive", int(dto.get("health", 0)) > 0))

func _attack_selected_actor() -> void:
	var actor_id: int = AppState.selected_actor_id
	var dto: Dictionary = AppState.actors.get(actor_id, {})
	if _is_attackable_actor(actor_id, dto):
		_send_attack(actor_id)

func _send_attack(actor_id: int) -> void:
	print_debug("combat_input command=ATTACK_SOMEONE target_actor_id=", actor_id,
		" redacted_bytes=not_sensitive")
	var error: Error = Network.attack_actor(actor_id)
	if error != OK:
		push_warning("ATTACK_SOMEONE failed: " + error_string(error))

## A server-driven modal question. The server had no way to ask the player
## anything at all: DISPLAY_POPUP(83) fell through to an unknown packet and
## POPUP_REPLY(50) had no encoder.
##
## The legacy contract decides the shape: a popup that contains a radio option
## or a text entry gets a send button and answers when it is pressed; one
## built only from text options answers the moment a button is clicked and
## closes, because each option *is* the action.
func _sync_popup() -> void:
	for child: Node in popup_options.get_children():
		if is_instance_valid(child):
			child.queue_free()
	_popup_radio_groups.clear()
	_popup_entries.clear()
	if not bool(AppState.popup.get("open", false)):
		popup_panel.hide()
		return
	popup_title.text = str(AppState.popup.get("title", "")).strip_edges()
	popup_text.text = str(AppState.popup.get("text", ""))
	var needs_confirm := false
	var radio_buttons: Dictionary = {}
	for raw_option: Variant in AppState.popup.get("options", []) as Array:
		var option: Dictionary = raw_option as Dictionary
		var option_type: int = int(option.get("option_type", -1))
		var group: int = int(option.get("group", 0))
		var label: String = str(option.get("label", ""))
		match option_type:
			EloriaProtocol.POPUP_DISPLAY_TEXT:
				var display := Label.new()
				display.text = label
				display.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				popup_options.add_child(display)
			EloriaProtocol.POPUP_TEXT_OPTION:
				var action := Button.new()
				action.text = label
				action.pressed.connect(_on_popup_option_pressed.bind(
					group, int(option.get("value", 0))))
				popup_options.add_child(action)
			EloriaProtocol.POPUP_RADIO_OPTION:
				needs_confirm = true
				var choice := CheckBox.new()
				choice.text = label
				choice.toggled.connect(_on_popup_radio_toggled.bind(
					group, int(option.get("value", 0))))
				popup_options.add_child(choice)
				var siblings: Array = radio_buttons.get(group, []) as Array
				siblings.append(choice)
				radio_buttons[group] = siblings
			EloriaProtocol.POPUP_TEXT_ENTRY:
				needs_confirm = true
				var prompt := Label.new()
				prompt.text = label
				popup_options.add_child(prompt)
				var entry := LineEdit.new()
				entry.max_length = 255
				popup_options.add_child(entry)
				_popup_entries[group] = entry
	_popup_radio_buttons = radio_buttons
	popup_confirm.visible = needs_confirm
	# A dismissable popup is not the same as an answered one: dismissing sends
	# nothing, which is what the legacy client does when a popup is closed.
	popup_dismiss.visible = true
	_close_panels_for_popup()
	popup_panel.show()
	popup_panel.move_to_front()

## The popup is modal, so the windows that own the keyboard or the pointer are
## closed underneath it rather than left fighting for input.
func _close_panels_for_popup() -> void:
	full_map.hide()
	console_panel.hide()
	_close_settings()
	item_lists_panel.hide()
	_sync_map_viewport_activity()

func _on_popup_radio_toggled(pressed: bool, group: int, value: int) -> void:
	if not pressed:
		if int(_popup_radio_groups.get(group, -1)) == value:
			_popup_radio_groups.erase(group)
		return
	_popup_radio_groups[group] = value
	# One selection per group: the wire carries exactly one answer per group.
	var index := 0
	for raw_button: Variant in _popup_radio_buttons.get(group, []) as Array:
		var button: CheckBox = raw_button as CheckBox
		var option_value: int = _popup_radio_value(group, index)
		if option_value != value and button.button_pressed:
			button.set_pressed_no_signal(false)
		index += 1

func _popup_radio_value(group: int, index: int) -> int:
	var seen := 0
	for raw_option: Variant in AppState.popup.get("options", []) as Array:
		var option: Dictionary = raw_option as Dictionary
		if int(option.get("option_type", -1)) != EloriaProtocol.POPUP_RADIO_OPTION:
			continue
		if int(option.get("group", 0)) != group:
			continue
		if seen == index:
			return int(option.get("value", 0))
		seen += 1
	return -1

func _on_popup_option_pressed(group: int, value: int) -> void:
	_send_popup_reply({group: value})

func _on_popup_confirm_pressed() -> void:
	var answers: Dictionary = {}
	for raw_group: Variant in _popup_radio_groups:
		answers[int(raw_group)] = int(_popup_radio_groups[raw_group])
	for raw_group: Variant in _popup_entries:
		var entry: LineEdit = _popup_entries[raw_group] as LineEdit
		if is_instance_valid(entry):
			answers[int(raw_group)] = entry.text
	_send_popup_reply(answers)

## Dismissing answers nothing. The server asked; declining to answer is a
## legitimate outcome and must not be reported as a choice.
func _on_popup_dismiss_pressed() -> void:
	AppState.close_popup()

func _send_popup_reply(answers: Dictionary) -> void:
	var popup_id: int = int(AppState.popup.get("popup_id", -1))
	if popup_id < 0:
		return
	var error: Error = Network.popup_reply(popup_id, answers)
	if error != OK:
		push_warning("POPUP_REPLY failed: " + error_string(error))
		return
	AppState.close_popup()

func _sync_dialogue() -> void:
	var dialogue: Dictionary = AppState.npc_dialogue
	dialogue_panel.visible = bool(dialogue.get("open", false)) and (
		not str(dialogue.get("text", "")).strip_edges().is_empty()
		or not (dialogue.get("options", []) as Array).is_empty())
	OldcraftDialogueStyleScript.sync_visibility(self, dialogue_panel.visible)
	if not dialogue_panel.visible:
		return
	# Dialogue the server flagged as belonging to a quest is marked as such,
	# which is the whole point of the flag: a player could not previously tell
	# a quest line from small talk, and neither could this client.
	var quest_id: int = int(dialogue.get("quest_id", 0))
	var is_quest: bool = bool(dialogue.get("quest", false))
	# The person's occupation follows the name, as it does under it in the world.
	var speaker: String = str(dialogue.get("name", "NPC"))
	var occupation: String = dialogue_occupation(dialogue, AppState.actors,
		AppState.actor_occupations)
	if not occupation.is_empty():
		speaker += "  <%s>" % occupation
	dialogue_name.text = ("%s  [Quest %d]" % [speaker,
		quest_id] if is_quest and quest_id > 0
		else speaker)
	dialogue_text.text = str(dialogue.get("text", ""))
	for child: Node in dialogue_options.get_children():
		dialogue_options.remove_child(child)
		child.queue_free()
	var raw_options: Variant = dialogue.get("options", [])
	var valid_options: Array[Dictionary] = []
	if raw_options is Array:
		for raw_option: Variant in raw_options:
			if not raw_option is Dictionary:
				continue
			valid_options.append(raw_option as Dictionary)
	OldcraftDialogueStyleScript.update_state(self, is_quest, quest_id,
		not valid_options.is_empty())
	for option_index: int in range(valid_options.size()):
		var option: Dictionary = valid_options[option_index]
		var button: Button = Button.new()
		button.text = OldcraftDialogueStyleScript.option_label(
			str(option.get("label", "Continue")), is_quest)
		OldcraftDialogueStyleScript.style_option(button, is_quest, option_index)
		button.pressed.connect(_on_dialogue_option.bind(
			int(option.get("actor_id", -1)), int(option.get("response_id", -1))))
		dialogue_options.add_child(button)
	OldcraftDialogueStyleScript.layout_content(self)

func _on_dialogue_option(actor_id: int, response_id: int) -> void:
	if actor_id < 0 or response_id < 0:
		return
	var error: Error = Network.respond_to_npc(actor_id, response_id)
	if error != OK:
		push_warning("RESPOND_TO_NPC failed: " + error_string(error))

func _viewport_position(global_position: Vector2) -> Vector2:
	var local_position: Vector2 = viewport_container.get_global_transform().affine_inverse() * global_position
	return _local_viewport_position(local_position)

func _local_viewport_position(local_position: Vector2) -> Vector2:
	if viewport_container.size.x <= 0.0 or viewport_container.size.y <= 0.0:
		return local_position
	return local_position * Vector2(main_viewport.size) / viewport_container.size

func _pick_actor(viewport_position: Vector2) -> int:
	if gameplay_world == null:
		push_warning("world_input actor_pick skipped: World3D unavailable")
		return -1
	var origin: Vector3 = camera_rig.ray_origin(viewport_position)
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(
		origin, origin + camera_rig.ray_direction(viewport_position) * 2000.0, 2)
	var hit: Dictionary = gameplay_world.direct_space_state.intersect_ray(query)
	var collider_value: Variant = hit.get("collider")
	if collider_value is ReplicatedActor3D:
		return (collider_value as ReplicatedActor3D).actor_id
	return -1

## World objects the server declared for this map. This is the pick layer the
## client never had: the world click handler tried actors, then ground bags,
## then the navigation surface, and stopped, so no rendered prop was ever
## clickable and the whole harvestable layer was unreachable.
func _pick_map_object(viewport_position: Vector2) -> MapObject3D:
	if gameplay_world == null:
		return null
	var origin: Vector3 = camera_rig.ray_origin(viewport_position)
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(
		origin, origin + camera_rig.ray_direction(viewport_position) * 2000.0,
		MapObject3D.PICK_LAYER)
	var hit: Dictionary = gameplay_world.direct_space_state.intersect_ray(query)
	var collider_value: Variant = hit.get("collider")
	return MapObject3D.from_pick_collider(collider_value)

## A plain click acts on the object; Alt inspects it instead. Every outcome is
## a request: the server decides range, tools, level and whether anything
## happens at all.
func _activate_map_object(map_object: MapObject3D, inspect: bool) -> void:
	_clear_map_walk_target()
	exterior_stream.pending_walk.clear()
	if inspect:
		var look_error: Error = Network.look_at_map_object(map_object.object_id)
		if look_error != OK:
			push_warning("LOOK_AT_MAP_OBJECT failed: " + error_string(look_error))
		return
	if map_object.is_harvestable():
		# HARVEST is a toggle on the server: sending it for the node already
		# being harvested stops the run.
		var harvest_error: Error = Network.harvest(map_object.object_id)
		if harvest_error != OK:
			push_warning("HARVEST failed: " + error_string(harvest_error))
		return
	var use_error: Error = Network.use_map_object(map_object.object_id)
	if use_error != OK:
		push_warning("USE_MAP_OBJECT failed: " + error_string(use_error))

func _sync_map_objects() -> void:
	for raw_id: Variant in map_object_nodes.keys():
		var object_id: int = int(raw_id)
		if not AppState.map_objects.has(object_id):
			var stale: Variant = map_object_nodes.get(object_id)
			if is_instance_valid(stale):
				(stale as Node).queue_free()
			map_object_nodes.erase(object_id)
	for raw_id: Variant in AppState.map_objects:
		var object_id: int = int(raw_id)
		var dto_value: Variant = AppState.map_objects.get(object_id)
		if not dto_value is Dictionary:
			continue
		if map_object_nodes.has(object_id):
			continue
		var map_object := MapObject3D.new()
		var catalog := world_object_models
		if EloriaProtocol.map_id_from_reference(AppState.current_map) in LANTERN_AUTHORED_MAPS:
			# The island authors its caches, bench and chart. Retain native
			# picking and resource models without putting a second prop on top.
			catalog = world_object_models.duplicate(true)
			catalog["interactives"] = {"roles":{},"models":{},"mapAuthored":{
				"Storage":true,"Crafting Station":true,"Information":true}}
		var region_entry: Dictionary = map_registry.get(AppState.current_map, {})
		var landscape_crossing: bool = bool(region_entry.get("landscapeTransitions", false)) and str(dto_value.get("label", "")) == "Portal"
		map_object.configure(dto_value as Dictionary, adapter, catalog, landscape_crossing,
			_object_presentation(object_id))
		map_object.set_particles_enabled(_effects_enabled)
		_fit_lantern_map_marker(map_object, "MapMarker")
		world_root.add_child(map_object)
		map_object_nodes[object_id] = map_object
		_paint_map_object_look(map_object)
		_place_map_object_on_surface(map_object)
	if is_instance_valid(lantern_scene) and lantern_scene.has_method("bind_map_objects"):
		lantern_scene.bind_map_objects(map_object_nodes)
	_bind_promoted_scenery()
	map_marker_overlay.set_waypoints(_collect_map_waypoints())
	_request_map_redraw()
	_sync_harvest_indicator()

## The lantern island's maps, whose packages author their caches, bench and
## chart (and, on Cinderbank and Reedway, their resources' pick shapes).
const LANTERN_AUTHORED_MAPS := ["lantern_reach", "bellwatch", "stillglass", "reedway",
	"cinderbank", "echo_court", "wayfarer_bastion", "lantern_exchange", "waystone_yard"]
## The maps whose layout.json authors pick shapes for their resources.
const LANTERN_PICK_SHAPE_MAPS := ["cinderbank", "reedway"]
## The harvest presentation schema this client reads (a package's
## `harvestablesSchema`; eloria-assets/maps/continent-v2/_continent_v2/
## harvest_presentation.py). A package naming another is read as one that
## states no presentation.
const HARVEST_PRESENTATION_SCHEMA := "eloria-harvest-presentation-v1"
## A harvest grouping's map mark, in pixels: a little larger than one node's
## dot (the overlays' BASE_RADIUS, 4), as it stands for a whole field.
const HARVEST_GROUPING_RADIUS := 6.0

## Reads how the map just bound presents its world objects
## (`map_presentation_of`), for this map only. Objects the server listed
## while the map was still loading were built without it; when the package
## states any, they are built again by the `_sync_map_objects` that follows.
func _bind_map_presentation(manifest: WorldManifest) -> void:
	var here := EloriaProtocol.map_id_from_reference(AppState.current_map)
	_map_presentation = map_presentation_of(here,
		manifest.data if manifest != null else {}, _lantern_pick_shapes(here),
		UndergroundSceneryScript.harvest_presentation(here))
	if (_map_presentation.nodes as Dictionary).is_empty() \
			and (_map_presentation.groupings as Array).is_empty():
		return
	for raw_object: Variant in map_object_nodes.values():
		if is_instance_valid(raw_object):
			(raw_object as Node).queue_free()
	map_object_nodes.clear()

## A lantern map's authored pick shapes by object id (its layout.json
## `presentation.pickShapes`), or {}.
static func _lantern_pick_shapes(map_id: String) -> Dictionary:
	if map_id not in LANTERN_PICK_SHAPE_MAPS:
		return {}
	var layout: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://../eloria-assets/maps/" + map_id + "/layout.json"))
	if layout is not Dictionary:
		return {}
	var shapes: Variant = ((layout as Dictionary).get("presentation", {}) as Dictionary).get(
		"pickShapes", {})
	return shapes if shapes is Dictionary else {}

## How the package `manifest` (a world.json, parsed) of `map_id` presents its
## world objects: {"map", "nodes": object id -> MapObject3D.presentation,
## "groupings": its harvestGroupings}. A harvest node takes its entry's
## `variant`, `yaw`, `footprint`, `grouping` and `bind`, and is `grouped` when
## the package names its grouping (the maps then mark the grouping once);
## `picks` are authored pick shapes by object id. A package published before
## the harvest presentation (no `harvestablesSchema`) presents nothing.
## `authored` is the client's own presentation of nodes such a package leaves
## bare, by object id - the underground's seams and pans
## (underground_scenery.gd `harvest_presentation`): their `variant`, `yaw`
## and `footprint`. A node the package presents keeps the package's.
static func map_presentation_of(map_id: String, manifest: Dictionary,
		picks: Dictionary = {}, authored: Dictionary = {}) -> Dictionary:
	var nodes := {}
	var groupings: Array[Dictionary] = []
	# Read only under the schema it was written with: the older packages'
	# harvestables (the twelve territories', the underground's) are other
	# records with other keys, and present nothing here.
	var schema := str(manifest.get("harvestablesSchema", ""))
	var readable := schema == HARVEST_PRESENTATION_SCHEMA
	if not readable and not schema.is_empty():
		push_warning("map %s: harvest presentation %s is not %s; its nodes are presented as before"
			% [map_id, schema, HARVEST_PRESENTATION_SCHEMA])
	var named := {}
	if readable:
		var listed: Variant = manifest.get("harvestGroupings", [])
		for value: Variant in (listed if listed is Array else []):
			if value is Dictionary and not str((value as Dictionary).get("id", "")).is_empty():
				groupings.append(value as Dictionary)
				named[str((value as Dictionary).id)] = true
		var entries: Variant = manifest.get("harvestables", [])
		for value: Variant in (entries if entries is Array else []):
			if value is not Dictionary:
				continue
			var entry := value as Dictionary
			var identity: Variant = entry.get("objectId")
			if identity is not int and identity is not float:
				continue
			var hint := {}
			for key: String in ["variant", "yaw", "footprint", "grouping", "bind"]:
				if entry.has(key):
					hint[key] = entry[key]
			if named.has(str(hint.get("grouping", ""))):
				hint["grouped"] = true
			if not hint.is_empty():
				nodes[int(identity)] = hint
	for key: Variant in authored:
		if authored[key] is not Dictionary or not str(key).is_valid_int() \
				or nodes.has(int(str(key))):
			continue
		var hint := {}
		# `placement` and `inset`: the underground's wall nodes (MapObject3D.is_wall_placed)
		for field: String in ["variant", "yaw", "footprint", "placement", "inset"]:
			if (authored[key] as Dictionary).has(field):
				hint[field] = authored[key][field]
		if not hint.is_empty():
			nodes[int(str(key))] = hint
	for key: Variant in picks:
		if picks[key] is Dictionary and str(key).is_valid_int():
			var hint: Dictionary = nodes.get(int(str(key)), {})
			hint["pick"] = picks[key]
			nodes[int(str(key))] = hint
	return {"map": map_id, "nodes": nodes, "groupings": groupings}

## This object's entry in the current map's presentation, or {} when the
## presentation was read for another map (or none was).
func _object_presentation(object_id: int) -> Dictionary:
	if str(_map_presentation.get("map", "")) != EloriaProtocol.map_id_from_reference(
			AppState.current_map):
		return {}
	return (_map_presentation.get("nodes", {}) as Dictionary).get(object_id, {}) as Dictionary

## Look-pass parity for a runtime world object: its map's root was painted as
## it loaded (LookFoliage.paint_loaded), before the server listed this object,
## so the object is painted here with the same region, and a node and the
## identical kit plant beside it shade the same. Off, the look's stand-ins
## are put back (LookSwitch.revert). Only continent maps are painted.
func _paint_map_object_look(map_object: MapObject3D) -> int:
	var manifest: WorldManifest = world_loader.manifest if world_loader != null else null
	if manifest == null or not manifest.data.has("continentGeography") \
			or not is_instance_valid(map_object):
		return 0
	# Seasonal stand-ins may be on an object even in Original mode.
	var changed := LookSwitch.revert(map_object)
	if LookProfile.full_painted():
		var translation: Array = (manifest.data.continentGeography as Dictionary).get(
			"translation", [0.0, 0.0, 0.0]) as Array
		changed += LookFoliage.paint_object(map_object, LookGround.region_of(manifest),
			map_object.transform, Vector2(float(translation[0]), float(translation[2]))
			if translation.size() == 3 else Vector2.ZERO)
	return changed + SeasonSurfaces.apply(map_object, manifest, true)

## Promoted scenery: each harvest node whose package names a placed kit node
## (`MapObject3D.bound_node_name`) is bound to that node's mesh in the map's
## own chunk once the chunk is resident (ContinentChunkStream.cells, by the
## package's `bind.chunk`), and again whenever it comes back after streaming
## out (`_on_chunk_surface_ready`). A map without chunks holds every placement
## under its one root.
func _bind_promoted_scenery() -> void:
	if world_loader == null or not is_instance_valid(world_loader.world_root):
		return
	var started := Time.get_ticks_usec()
	var wanted: Dictionary = {}
	for raw_object: Variant in map_object_nodes.values():
		if is_instance_valid(raw_object):
			_collect_promoted_scenery(raw_object as MapObject3D, wanted)
	_apply_promoted_scenery(wanted)
	_record_surface_work(&"scenery_bind", started, map_object_nodes.size())

func _collect_promoted_scenery(map_object: MapObject3D, wanted: Dictionary) -> bool:
	if not is_instance_valid(map_object) or map_object.bound_node_name.is_empty() \
			or map_object.placement_bound():
		return false
	var chunk := str((map_object.presentation.get("bind", {}) as Dictionary).get("chunk", ""))
	if not wanted.has(chunk):
		wanted[chunk] = {}
	if not (wanted[chunk] as Dictionary).has(map_object.bound_node_name):
		wanted[chunk][map_object.bound_node_name] = []
	(wanted[chunk][map_object.bound_node_name] as Array).append(map_object)
	return true

func _apply_promoted_scenery(wanted: Dictionary) -> void:
	if world_loader == null or not is_instance_valid(world_loader.world_root):
		return
	var stream := world_loader.world_root as ContinentChunkStream
	for chunk: String in wanted:
		var placed_root: Node = world_loader.world_root
		if stream != null:
			placed_root = (stream.cells.get(chunk, {}) as Dictionary).get("root") as Node
		if not is_instance_valid(placed_root):
			continue
		var found := _named_nodes(placed_root, wanted[chunk] as Dictionary)
		for node_name: String in found:
			for map_object: MapObject3D in wanted[chunk][node_name]:
				if is_instance_valid(map_object):
					map_object.bind_placement(found[node_name] as Node3D)

## The Node3Ds under `root` whose names are keys of `names`, nearest first;
## the walk stops as soon as all are found (a kit placement is a child of its
## chunk's root).
static func _named_nodes(root: Node, names: Dictionary) -> Dictionary:
	var found := {}
	var queue: Array[Node] = [root]
	while not queue.is_empty() and found.size() < names.size():
		var node: Node = queue.pop_front()
		for child: Node in node.get_children():
			var child_name := String(child.name)
			if names.has(child_name) and child is Node3D and not found.has(child_name):
				found[child_name] = child
			queue.append(child)
	return found

## A chunk streaming out takes its placements with it: the nodes bound to
## them let go, and bind again when it returns.
func _on_chunk_cell_retiring(identity: String, imported: Node3D) -> void:
	# Chunk IDs repeat across territories. A neighbour's retirement must not
	# release an unrelated binding on the current map with the same ID.
	if not is_instance_valid(imported) or imported.get_parent() != world_loader.world_root:
		return
	for raw_object: Variant in map_object_nodes.values():
		if not is_instance_valid(raw_object):
			continue
		var map_object := raw_object as MapObject3D
		if map_object != null and not map_object.bound_node_name.is_empty() and str(
				(map_object.presentation.get("bind", {}) as Dictionary).get("chunk", "")) == identity:
			map_object.release_placement()

## One map mark per harvest grouping the current map's package names, at its
## centre (`centreTile`), in the harvest colour and a little larger than one
## node's dot, named on hover. A grouping none of whose nodes the server
## lists, or none visible, is not marked.
func _harvest_grouping_marks() -> Array[Dictionary]:
	var marks: Array[Dictionary] = []
	if str(_map_presentation.get("map", "")) != EloriaProtocol.map_id_from_reference(
			AppState.current_map):
		return marks
	var members := {}
	for raw_object: Variant in map_object_nodes.values():
		if not is_instance_valid(raw_object):
			continue
		var map_object := raw_object as MapObject3D
		if map_object == null or not map_object.grouped or not map_object.is_visible_in_tree():
			continue
		if not members.has(map_object.grouping):
			members[map_object.grouping] = []
		(members[map_object.grouping] as Array).append(map_object.global_position)
	for grouping: Dictionary in (_map_presentation.get("groupings", []) as Array):
		var identity := str(grouping.get("id", ""))
		if not members.has(identity):
			continue
		var mean := Vector3.ZERO
		for at: Vector3 in members[identity]:
			mean += at
		mean /= float((members[identity] as Array).size())
		var tile: Variant = grouping.get("centreTile")
		var position := mean
		if tile is Array and (tile as Array).size() == 2 and adapter != null:
			position = adapter.tile_center(int(tile[0]), int(tile[1]))
			position.y = mean.y
		marks.append({"position": position, "type": &"harvest",
			"colour": MapObject3D.HARVEST_COLOUR, "radius": HARVEST_GROUPING_RADIUS,
			"label": str(grouping.get("name", identity)), "grouping": identity})
	return marks

func _fit_lantern_map_marker(node: Node3D, marker_name: String) -> void:
	# The standard discs span 12–14 metres on the large regional maps.
	# On this 120-metre island they would cover entire lesson locations.
	if EloriaProtocol.map_id_from_reference(AppState.current_map) not in ["lantern_reach", "bellwatch", "stillglass", "reedway", "cinderbank", "echo_court", "wayfarer_bastion", "lantern_exchange", "waystone_yard"]: return
	var marker := node.get_node_or_null(marker_name) as Node3D
	if marker: marker.scale = Vector3(.18, 1, .18)

## Draws the markers the server placed for the map the player is standing on.
##
## A marker keeps its map: the server states which map each belongs to and never
## withdraws one because the player walked elsewhere, so a marker for another
## map is held and hidden rather than discarded and guessed at again later.
func _sync_map_markers() -> void:
	quest_trail.apply_state(AppState.lantern_tutorial, adapter, AppState.current_map)
	# Both sides are reduced the same way: the marker names its map as the
	# server's own file reference, and CHANGE_MAP names the current one the
	# same way, so neither is compared to a path the other never uses.
	var here: String = EloriaProtocol.map_id_from_reference(AppState.current_map)
	for raw_id: Variant in map_marker_nodes.keys():
		var marker_id: int = int(raw_id)
		var marker_value: Variant = AppState.map_markers.get(marker_id)
		var still_here: bool = (marker_value is Dictionary
			and str((marker_value as Dictionary).get("map_id", "")) == here)
		if still_here:
			continue
		var stale: Variant = map_marker_nodes.get(marker_id)
		if is_instance_valid(stale):
			(stale as Node).queue_free()
		map_marker_nodes.erase(marker_id)
	for raw_id: Variant in AppState.map_markers:
		var marker_id: int = int(raw_id)
		var dto_value: Variant = AppState.map_markers.get(marker_id)
		if not dto_value is Dictionary:
			continue
		var dto: Dictionary = dto_value as Dictionary
		if str(dto.get("map_id", "")) != here:
			continue
		var marker: MapMarker3D = map_marker_nodes.get(marker_id) as MapMarker3D
		if not is_instance_valid(marker):
			marker = MapMarker3D.new()
			world_root.add_child(marker)
			map_marker_nodes[marker_id] = marker
		marker.configure(dto, adapter)
		_fit_lantern_map_marker(marker, "Pin")
		_place_map_marker_on_surface(marker)
	_update_attached_map_markers()
	_sync_player_mark_nodes()
	_sync_map_marker_list()
	_request_map_redraw()

func _update_attached_map_markers() -> void:
	for raw_marker: Variant in map_marker_nodes.values():
		if not is_instance_valid(raw_marker):
			continue
		var marker := raw_marker as MapMarker3D
		marker.visible = not character_intro.owns_guide_beacon(marker.target_actor_id)
		if marker.target_actor_id < 0:
			continue
		var dto: Dictionary = AppState.actors.get(marker.target_actor_id, {})
		if dto.is_empty() or str(dto.get("map", AppState.current_map)) != AppState.current_map:
			continue
		var actor_value: Variant = actor_nodes.get(marker.target_actor_id)
		if not is_instance_valid(actor_value):
			continue
		var actor := actor_value as Node3D
		if actor != null and not actor.is_queued_for_deletion():
			marker.follow_actor(actor.global_position)

func _sync_player_mark_nodes() -> void:
	var wanted: Dictionary = {}
	for mark: Dictionary in _current_player_marks():
		var key: String = str(mark.get("label", "Mark"))
		wanted[key] = true
		var marker: MapMarker3D = player_mark_nodes.get(key) as MapMarker3D
		if not is_instance_valid(marker):
			marker = MapMarker3D.new()
			world_root.add_child(marker)
			player_mark_nodes[key] = marker
		marker.configure(mark, adapter, false)
		_place_map_marker_on_surface(marker)
	for key: Variant in player_mark_nodes.keys():
		if not wanted.has(key):
			var stale: Node = player_mark_nodes[key] as Node
			if is_instance_valid(stale):
				stale.queue_free()
			player_mark_nodes.erase(key)

## The pins are readable as shapes on both map cameras, but a full map covers a
## whole map: no label drawn at that scale can be read. The sidebar lists what
## each pin is, in the server's own words, beside the legend that explains the
## rest of the map.
func _sync_map_marker_list() -> void:
	var lines: Array[String] = []
	for raw_id: Variant in map_marker_nodes:
		var marker: Variant = map_marker_nodes[raw_id]
		if not is_instance_valid(marker):
			continue
		var pin: MapMarker3D = marker as MapMarker3D
		lines.append("[color=#fac638]◆[/color] %s  (%d, %d)" % [
			pin.label if not pin.label.is_empty() else "Marker",
			pin.server_tile.x, pin.server_tile.y])
	for mark: Dictionary in console_commands.marks:
		if str(mark.get("map", "")) != EloriaProtocol.map_id_from_reference(
				AppState.current_map):
			continue
		lines.append("[color=#7fd4ff]*[/color] %s  (%d, %d)" % [
			str(mark.get("label", "Mark")), int(mark.get("x", 0)),
			int(mark.get("y", 0))])
	map_marker_list.text = "
".join(lines)
	map_marker_title.visible = not lines.is_empty()
	map_marker_list.visible = not lines.is_empty()
	map_marker_overlay.set_markers(_current_map_markers())
	map_marker_overlay.set_player_marks(_current_player_marks())

## The marks the player made for themselves on this map. Presentational: they
## are the player's own annotation of their own screen, they never leave the
## client, and the server is not told about them.
func _current_player_marks() -> Array[Dictionary]:
	var here: String = EloriaProtocol.map_id_from_reference(AppState.current_map)
	var mine: Array[Dictionary] = []
	for mark: Dictionary in console_commands.marks:
		if str(mark.get("map", "")) == here:
			mine.append(mark)
	return mine

## The markers the server placed on the map the player is standing on.
func _current_map_markers() -> Array[Dictionary]:
	var here: String = EloriaProtocol.map_id_from_reference(AppState.current_map)
	var markers: Array[Dictionary] = []
	for raw_id: Variant in AppState.map_markers:
		var marker_value: Variant = AppState.map_markers[raw_id]
		if not marker_value is Dictionary:
			continue
		var marker: Dictionary = marker_value as Dictionary
		if str(marker.get("map_id", "")) == here:
			var projected: Dictionary = marker.duplicate()
			var node: Variant = map_marker_nodes.get(int(marker.marker_id))
			if is_instance_valid(node):
				projected["position"] = (node as MapMarker3D).global_position
			markers.append(projected)
	return markers

func _place_map_marker_on_surface(marker: MapMarker3D) -> void:
	if not is_instance_valid(marker):
		return
	var sampled: Variant = _navigation_ray_position(
		marker.global_position + Vector3(0.0, 200.0, 0.0), Vector3.DOWN)
	if sampled is Vector3:
		marker.set_surface_height((sampled as Vector3).y)

## Grounds one world object, and notices when it cannot be grounded at all.
##
## A server object whose tile has no navigation surface under it is misplaced
## content: the server is describing somewhere the rendered map does not have.
## That is worth counting rather than leaving as an invisible marker hanging in
## the air, so it appears in the protocol diagnostics panel.
func _place_map_object_on_surface(map_object: MapObject3D) -> void:
	if not is_instance_valid(map_object):
		return
	var sampled: Variant = _navigation_ray_position(
		map_object.global_position + Vector3(0.0, 200.0, 0.0), Vector3.DOWN)
	if sampled is Vector3:
		map_object.set_surface_height((sampled as Vector3).y)
		_ungrounded_map_objects.erase(map_object.object_id)
		return
	_ungrounded_map_objects[map_object.object_id] = map_object.label

func _snap_all_map_objects_to_surface() -> void:
	await get_tree().physics_frame
	var started := Time.get_ticks_usec()
	for raw_object: Variant in map_object_nodes.values():
		_place_map_object_on_surface(raw_object as MapObject3D)
	for raw_marker: Variant in map_marker_nodes.values():
		_place_map_marker_on_surface(raw_marker as MapMarker3D)
	for raw_marker: Variant in player_mark_nodes.values():
		_place_map_marker_on_surface(raw_marker as MapMarker3D)
	_record_surface_work(&"object_ground", started,
		map_object_nodes.size() + map_marker_nodes.size() + player_mark_nodes.size())

## Map objects and markers are placed on the rendered navigation surface when
## the server lists them. On a streamed territory the chunk beneath a distant
## object attaches later, so each chunk arrival places them again; otherwise a
## harvestable far from the arrival stayed ungrounded until the next map change.
func _watch_chunk_surfaces() -> void:
	if not exterior_stream.residents_changed.is_connected(_on_resident_surfaces_changed):
		exterior_stream.residents_changed.connect(_on_resident_surfaces_changed)
	_watch_surface_stream(world_loader.world_root)
	for resident: Dictionary in exterior_stream.residents.values():
		_watch_surface_stream(resident.get("root") as Node3D)

func _watch_surface_stream(surface_root: Node3D) -> void:
	var chunk_stream := surface_root as ContinentChunkStream
	if chunk_stream != null and not chunk_stream.cell_ready.is_connected(_on_chunk_surface_ready):
		chunk_stream.cell_ready.connect(_on_chunk_surface_ready)
	if chunk_stream != null and not chunk_stream.cell_retiring.is_connected(_on_chunk_cell_retiring):
		chunk_stream.cell_retiring.connect(_on_chunk_cell_retiring)
	# The lamps the territory places, the neighbours' included.
	if chunk_stream != null and night_lamps != null:
		night_lamps.watch(chunk_stream)

func _on_resident_surfaces_changed() -> void:
	_watch_chunk_surfaces()
	_apply_ambient_render_quality()
	_surface_refresh_queue.queue_full()
	_schedule_surface_refresh()

func _on_chunk_surface_ready(identity: String, imported: Node3D) -> void:
	if _surface_refresh_queue.queue_chunk(identity, imported):
		_schedule_surface_refresh()

func _schedule_surface_refresh() -> void:
	_surface_followup_pending = _surface_refresh_inflight + _surface_refresh_queue.pending_notifications()
	if _surface_refresh_running or _surface_refresh_queue.pending_notifications() == 0:
		return
	_surface_refresh_running = true
	_flush_surface_refresh.call_deferred(_surface_refresh_epoch)

func _flush_surface_refresh(epoch: int) -> void:
	await get_tree().physics_frame
	if epoch != _surface_refresh_epoch:
		return
	var batch: Dictionary = _surface_refresh_queue.take()
	if int(batch.notifications) == 0:
		_surface_refresh_running = false
		_surface_refresh_inflight = 0
		_surface_followup_pending = 0
		return
	_surface_refresh_inflight = int(batch.notifications)
	_surface_followup_pending = _surface_refresh_inflight + _surface_refresh_queue.pending_notifications()
	var started := Time.get_ticks_usec()
	var actor_visits := 0
	var actor_placement_attempts := 0
	var object_visits := 0
	var object_placement_attempts := 0
	var binding_candidates := 0
	if SurfaceRefreshQueue.has_live_changes(batch):
		var full := bool(batch.full)
		var step_started := Time.get_ticks_usec()
		if full:
			_sync_season_surfaces()
		else:
			SeasonSurfaces.set_season(AppState.almanac.get("season", {}) as Dictionary)
			for region: Dictionary in batch.regions:
				var live: Dictionary = SurfaceRefreshQueue.live_region(region)
				if not live.is_empty():
					SeasonSurfaces.apply(live.imported as Node, live.manifest as WorldManifest)
			_record_surface_work(&"season", step_started, (batch.regions as Array).size())
		_record_surface_span(_surface_followup_stats, &"season", Time.get_ticks_usec() - int(batch.queued_usec))
		var priorities: Dictionary = {}
		for actor_id: int in [AppState.local_actor_id, AppState.selected_actor_id, _combat_target_actor_id()]:
			if actor_id >= 0:
				priorities[actor_id] = true
		step_started = Time.get_ticks_usec()
		for actor_value: Variant in actor_nodes.values():
			if not is_instance_valid(actor_value):
				continue
			var actor := actor_value as ReplicatedActor3D
			if actor == null:
				continue
			actor_visits += 1
			var ungrounded := not _grounded_actors.has(actor.actor_id) or not _actor_surface_samples.has(actor.actor_id)
			if not SurfaceRefreshQueue.should_refresh(batch, actor.server_target,
					priorities.has(actor.actor_id), ungrounded):
				continue
			var actor_adapter := _adapter_for_actor(AppState.actors.get(actor.actor_id, {}) as Dictionary)
			if actor_adapter != null:
				_place_actor_on_surface(actor, true, actor_adapter.fallback_height())
				actor_placement_attempts += 1
		_record_surface_work(&"actor_ground", step_started, actor_visits)
		_record_surface_span(_surface_followup_stats, &"actor_ground", Time.get_ticks_usec() - int(batch.queued_usec))
		var changed: Dictionary = SurfaceRefreshQueue.current_chunks(batch, world_loader.world_root)
		var wanted: Dictionary = {}
		step_started = Time.get_ticks_usec()
		# Each object is visited once: collect current-map bindings during the
		# same pass that filters navigation rays for the changed surfaces.
		for object_value: Variant in map_object_nodes.values():
			if not is_instance_valid(object_value):
				continue
			var map_object := object_value as MapObject3D
			if map_object == null:
				continue
			object_visits += 1
			if SurfaceRefreshQueue.should_refresh(batch, map_object.global_position, false,
					_ungrounded_map_objects.has(map_object.object_id)):
				_place_map_object_on_surface(map_object)
				object_placement_attempts += 1
			var chunk := str((map_object.presentation.get("bind", {}) as Dictionary).get("chunk", ""))
			if (full or changed.has(chunk)) and _collect_promoted_scenery(map_object, wanted):
				binding_candidates += 1
		for markers: Dictionary in [map_marker_nodes, player_mark_nodes]:
			for marker_value: Variant in markers.values():
				if not is_instance_valid(marker_value):
					continue
				var marker := marker_value as MapMarker3D
				if marker == null:
					continue
				object_visits += 1
				if SurfaceRefreshQueue.should_refresh(batch, marker.global_position, priorities.has(marker.target_actor_id)):
					_place_map_marker_on_surface(marker)
					object_placement_attempts += 1
		_record_surface_work(&"object_ground", step_started, object_visits)
		_record_surface_span(_surface_followup_stats, &"object_ground", Time.get_ticks_usec() - int(batch.queued_usec))
		step_started = Time.get_ticks_usec()
		_apply_promoted_scenery(wanted)
		_record_surface_work(&"scenery_bind", step_started, binding_candidates)
		_record_surface_span(_surface_followup_stats, &"scenery_bind", Time.get_ticks_usec() - int(batch.queued_usec))
	_record_surface_work(&"surface_batch", started, actor_visits + object_visits)
	_record_surface_span(_surface_followup_stats, &"surface_batch",
		Time.get_ticks_usec() - int(batch.queued_usec), int(batch.notifications))
	_surface_spatial_stats.batches += 1
	if bool(batch.full):
		_surface_spatial_stats.full_batches += 1
	_surface_spatial_stats.notifications += int(batch.notifications)
	_surface_spatial_stats.invalidated_regions += int(batch.invalidated_regions)
	_surface_spatial_stats.actor_visits += actor_visits
	_surface_spatial_stats.actor_placement_attempts += actor_placement_attempts
	_surface_spatial_stats.object_visits += object_visits
	_surface_spatial_stats.object_placement_attempts += object_placement_attempts
	_surface_spatial_stats.binding_candidates += binding_candidates
	_surface_refresh_inflight = 0
	_surface_refresh_running = false
	_surface_followup_pending = _surface_refresh_queue.pending_notifications()
	if _surface_followup_pending > 0:
		_schedule_surface_refresh()

static func _record_surface_span(stats: Dictionary, label: StringName,
		elapsed: int, items := 0) -> void:
	var row: Dictionary = stats.get(label, {"count": 0, "total_usec": 0,
		"max_usec": 0, "last_usec": 0, "items": 0})
	row.count = int(row.count) + 1
	row.total_usec = int(row.total_usec) + elapsed
	row.max_usec = maxi(int(row.max_usec), elapsed)
	row.last_usec = elapsed
	row.items = int(row.items) + items
	stats[label] = row

func _record_surface_work(label: StringName, started: int, items := 0) -> void:
	_record_surface_span(_surface_work_stats, label, Time.get_ticks_usec() - started, items)

func surface_work_snapshot() -> Dictionary:
	return {"pending": _surface_followup_pending,
		"completion_wall": _surface_followup_stats.duplicate(true),
		"work": _surface_work_stats.duplicate(true),
		"spatial": _surface_spatial_stats.duplicate(),
		"queued": _surface_refresh_queue.snapshot(), "running": _surface_refresh_running}

## The "now harvesting" indicator. The stock client drove this by matching an
## exact English phrase out of the chat stream; this reads the authoritative
## harvest-state packet instead, so it survives a reworded message and cannot
## be left stuck on when the server stops the run for its own reasons - moving,
## a full backpack, or combat.
func _sync_harvest_indicator() -> void:
	_sync_hud_indicators()
	var active: bool = bool(AppState.harvest.get("active", false))
	var active_object: int = int(AppState.harvest.get("object_id", -1))
	for raw_object: Variant in map_object_nodes.values():
		var map_object: MapObject3D = raw_object as MapObject3D
		if is_instance_valid(map_object):
			map_object.set_active(active and map_object.object_id == active_object)
	_sync_harvest_sparkle()
	if harvest_banner == null:
		return
	if not active:
		harvest_banner.hide()
		return
	harvest_banner.text = "Harvesting %s" % str(AppState.harvest.get("resource", ""))
	harvest_banner.show()

## Glitter around the player for as long as the server says they are
## harvesting, the way the legacy client's harvesting eye candy did. Only the
## local player's run is on the wire, so only the local player glitters.
func _sync_harvest_sparkle() -> void:
	var active: bool = bool(AppState.harvest.get("active", false))
	# Checked before the cast: `as` on a freed node raises.
	var actor_value: Variant = actor_nodes.get(AppState.local_actor_id)
	var actor: ReplicatedActor3D = (actor_value as ReplicatedActor3D
		) if is_instance_valid(actor_value) else null
	var wanted: bool = active and _effects_enabled and actor != null
	if is_instance_valid(harvest_sparkle):
		if wanted and harvest_sparkle.is_following(actor):
			return
		harvest_sparkle.stop()
	harvest_sparkle = null
	if not wanted:
		return
	harvest_sparkle = HarvestSparkle3D.new()
	harvest_sparkle.name = "HarvestSparkle"
	world_root.add_child(harvest_sparkle)
	harvest_sparkle.configure(actor)

func _pick_ground_bag(viewport_position: Vector2) -> int:
	if gameplay_world == null:
		return -1
	var origin: Vector3 = camera_rig.ray_origin(viewport_position)
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(
		origin, origin + camera_rig.ray_direction(viewport_position) * 2000.0,
		GroundBag3D.PICK_LAYER)
	var hit: Dictionary = gameplay_world.direct_space_state.intersect_ray(query)
	var collider_value: Variant = hit.get("collider")
	if collider_value is GroundBag3D:
		return (collider_value as GroundBag3D).bag_id
	return -1

## Keeps the pointer stating what a click would do. Ten refreshes a second is
## enough to feel immediate and keeps the three pick rays off the per-motion
## path; the apply call itself is free when the answer has not changed.
func _update_action_cursor() -> void:
	if not mouse_cursors.loaded():
		return
	var now: int = Time.get_ticks_msec()
	if now < _cursor_refresh_msec:
		return
	_cursor_refresh_msec = now + ACTION_CURSOR_REFRESH_MSEC
	mouse_cursors.apply(MouseCursors.choose(_cursor_context()))

## What the pointer is over, in the terms the cursor table decides on. Empty
## means "not over the world" - the login screen, a window, the HUD - which
## the table answers with the plain arrow.
func _cursor_context() -> Dictionary:
	if not game_view.visible or gameplay_world == null:
		return {}
	var hovered: Control = get_viewport().gui_get_hovered_control()
	if hovered != viewport_container:
		# The interface hovers with cursors of their own: an item slot shows
		# what the tool in hand would do to the stack under the pointer.
		if hovered is Button:
			var slot_target: String = _slot_cursor_target(hovered as Button)
			if not slot_target.is_empty():
				return {"target": slot_target}
		return {}
	return _cursor_context_at(_local_viewport_position(
		viewport_container.get_local_mouse_position()))

## What this slot button promises the pointer, in the cursor table's terms, or
## "" for a slot a click would do nothing with. The hand moves the item - the
## carry in hand is placed here, or the stack under the pointer is picked up,
## equipped, unequipped or Ctrl-dropped; the finger uses it; the eye looks at
## it. This is the promise, so it must match _on_inventory_slot_pressed.
func _slot_cursor_target(button: Button) -> String:
	if bool(button.get_meta("gauntlet_loot_inspect", false)):
		return "item_inspect"
	var slot: int = inventory_slot_buttons.find(button)
	if slot < 0:
		var equipment_index: int = equipment_slot_buttons.find(button)
		if equipment_index < 0:
			return ""
		slot = 36 + equipment_index
	if _storage_carried_position >= 0:
		return "item_grab" if slot < 36 else ""
	if _carried_slot >= 0:
		return "item_grab"
	if not AppState.inventory.has(slot):
		return ""
	if slot < 36 and Input.is_key_pressed(KEY_CTRL):
		return "item_grab"
	match _inventory_tool:
		"grab":
			return "item_grab" if _carry_enabled() else ""
		"equip":
			return "item_grab" if slot < 36 else ""
		"unequip":
			return "item_grab" if slot >= 36 else ""
		"use":
			# Keep the Use cursor while a usable item cools down, matching
			# the selected tool. The use action still checks its cooldown.
			return "item_use" if _slot_has_usable_item(slot) else "item_inspect"
		"inspect":
			return "item_inspect"
	return ""

## Whether this slot offers the Use tool, regardless of its current cooldown.
## Worn gear and items the server did not mark usable only offer inspection.
func _slot_has_usable_item(slot: int) -> bool:
	if slot < 0 or slot >= 36:
		return false
	var item_value: Variant = AppState.inventory.get(slot)
	if not item_value is Dictionary:
		return false
	return bool((item_value as Dictionary).get("inventory_usable", false))

## The world half of the pointer question, split from the hover gate so a test
## can ask it about any spot without owning the operating system's mouse.
func _cursor_context_at(viewport_position: Vector2) -> Dictionary:
	var context: Dictionary = {
		"over_world": true,
		"mode": _interaction_mode,
		"alt": _alt_attack_preview,
		"spell_target": AppState.pending_spell_target,
	}
	# The same ray order the click handler resolves in: actors win over bags,
	# bags over world objects, so the pointer promises what the click does.
	var actor_id: int = _pick_actor(viewport_position)
	if actor_id >= 0:
		var dto: Dictionary = AppState.actors.get(actor_id, {})
		var kind: int = int(dto.get("kind", 0))
		if actor_id == AppState.local_actor_id:
			# A bag at your own feet outranks your own body: you are not a
			# click target for yourself, and the click handler resolves the
			# same way. A pending actor spell still claims you - clicking
			# yourself casts at yourself.
			if AppState.pending_spell_target != "actor" \
					and _interaction_mode in ["walk", "pick"] \
					and _ground_bag_below_player() >= 0:
				context["target"] = "bag"
				return context
			context["target"] = "self"
		elif kind == 2 or _is_tutorial_companion(actor_id):
			context["target"] = "npc"
		elif ReplicatedActor3D.is_summon(dto):
			context["target"] = "summon"
		elif _is_creature_actor(dto):
			context["target"] = "creature"
		else:
			# Players, and any kind this client cannot attack, trade with or
			# greet: the honest promise for those is a look.
			context["target"] = "player"
		context["alive"] = bool(dto.get("alive", int(dto.get("health", 0)) > 0))
		return context
	if _pick_ground_bag(viewport_position) >= 0:
		context["target"] = "bag"
		return context
	var map_object: MapObject3D = _pick_map_object(viewport_position)
	if map_object != null:
		if map_object.is_harvestable():
			context["target"] = "harvest"
		elif map_object.offers_map_change():
			context["target"] = "portal"
		else:
			context["target"] = "interactive"
	return context

## Rabbit Lands artwork derived from the selected Discord identity.
## Preserve existing scene controls and compatibility-sensitive resource paths.
func _apply_rabbitlands_branding() -> void:
	login_logo.texture = _external_texture("res://assets/branding/rabbitlands-logo.png")
	hud_logo.texture = _external_texture("res://assets/branding/rabbitlands-mark.png")
	for target: TextureRect in [login_logo, hud_logo]:
		target.tooltip_text = "Rabbit Lands"


func _apply_eloria_art() -> void:
	login_background.texture = _external_texture(
		"res://assets/ui/eloria_login_landfall_background.png")
	%CreationBackdrop.texture = _external_texture(
		"res://assets/ui/eloria_character_creation_background.jpg")
	_apply_rabbitlands_branding()
	_hud_active_atlas = _external_texture("res://assets/ui/eloria_gamebuttons.png")
	_hud_inactive_atlas = _external_texture("res://assets/ui/eloria_gamebuttons_inactive.png")
	%MountsButton.icon = _external_texture("res://assets/ui/menu-icons/mounts.png")
	if _hud_active_atlas != null:
		# The Godot HUD atlas uses one canonical row-major icon order.  Keeping
		# these regions contiguous makes the art easy to audit and prevents the
		# legacy atlas's highlighted-state pairs from being mistaken for actions.
		_hud_icon_regions = {
			%WalkButton: Rect2(0, 0, 32, 32), %ChatButton: Rect2(32, 0, 32, 32),
			%LookButton: Rect2(64, 0, 32, 32),
			%KnowledgeButton: Rect2(96, 0, 32, 32), %AttackButton: Rect2(128, 0, 32, 32),
			%StatsButton: Rect2(160, 0, 32, 32),
			%DisconnectButton: Rect2(192, 0, 32, 32), %SitButton: Rect2(224, 0, 32, 32),
			%TradeButton: Rect2(0, 32, 32, 32), %InventoryButton: Rect2(32, 32, 32, 32),
			%ManufacturingButton: Rect2(64, 32, 32, 32),
			%EncyclopediaButton: Rect2(96, 32, 32, 32),
			%MapButton: Rect2(128, 32, 32, 32),
			%SpellsButton: Rect2(192, 32, 32, 32), %EmotesButton: Rect2(224, 32, 32, 32),
			%QuestButton: Rect2(0, 64, 32, 32), %InfoButton: Rect2(32, 64, 32, 32),
			%BuddyButton: Rect2(64, 64, 32, 32), %ConsoleButton: Rect2(96, 64, 32, 32),
			%HelpButton: Rect2(128, 64, 32, 32), %OptionsButton: Rect2(160, 64, 32, 32),
			%RangingButton: Rect2(192, 64, 32, 32), %MinimapButton: Rect2(224, 64, 32, 32)}
		for button_value: Variant in _hud_icon_regions:
			var icon_button: Button = button_value as Button
			icon_button.icon = _atlas_region(_hud_active_atlas,
				_hud_icon_regions[button_value] as Rect2)
			icon_button.text = ""
			icon_button.expand_icon = true
			icon_button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			icon_button.vertical_icon_alignment = VERTICAL_ALIGNMENT_CENTER
			icon_button.toggle_mode = true
		_sync_hud_button_states(true)
	var hud_atlas: Texture2D = _external_texture("res://assets/ui/eloria_hud_atlas.png")
	if hud_atlas != null:
		%ClockFace.texture = _atlas_region(hud_atlas, Rect2(0, 128, 64, 64))
		%CompassFace.texture = _atlas_region(hud_atlas, Rect2(32, 192, 64, 64))
	# Refresh once after imports are available. The helper caches both the one
	# shared sheet and its four AtlasTextures, so selecting a class allocates no
	# textures and performs no image decoding.
	_configure_creation_classes()

static func _atlas_region(atlas: Texture2D, region: Rect2) -> AtlasTexture:
	var texture: AtlasTexture = AtlasTexture.new()
	texture.atlas = atlas
	texture.region = region
	return texture

## The window chrome is Eternal Lands' (elwindows.c): near-black bodies, a
## one-pixel gui_color border, hover fills in the inverse colour. The old
## blue-teal boxes read as another game's UI next to the legacy client.
##
## The bodies are opaque, which is Eternal Lands' own "Use Opaque Window
## Backgrounds" option rather than its default. Nameplates are Label3D drawn
## inside the world viewport, so a translucent window cannot cover one: every
## name and health bar behind a window read straight through it and fought
## with the text on top. Opaque is what puts a window in front of them.
func _apply_eloria_theme() -> void:
	var eloria_theme: Theme = Theme.new()
	var panel: StyleBoxFlat = StyleBoxFlat.new()
	panel.bg_color = Color(0.043, 0.034, 0.024, 1.0)
	panel.border_color = Color(EL_GUI_COLOUR, 0.95)
	panel.set_border_width_all(1)
	panel.corner_radius_top_left = 1
	panel.corner_radius_top_right = 1
	panel.corner_radius_bottom_left = 1
	panel.corner_radius_bottom_right = 1
	panel.set_content_margin_all(4.0)
	eloria_theme.set_stylebox("panel", "PanelContainer", panel)
	var button: StyleBoxFlat = panel.duplicate() as StyleBoxFlat
	button.bg_color = Color(0.03, 0.02, 0.01, 0.55)
	button.set_border_width_all(1)
	button.set_content_margin_all(4.0)
	eloria_theme.set_stylebox("normal", "Button", button)
	var button_hover: StyleBoxFlat = button.duplicate() as StyleBoxFlat
	button_hover.bg_color = Color(EL_GUI_INVERT_COLOUR, 0.95)
	button_hover.border_color = EL_GUI_BRIGHT_COLOUR
	eloria_theme.set_stylebox("hover", "Button", button_hover)
	eloria_theme.set_stylebox("pressed", "Button", button_hover)
	var field: StyleBoxFlat = button.duplicate() as StyleBoxFlat
	field.bg_color = Color(0.02, 0.015, 0.01, 0.85)
	eloria_theme.set_stylebox("normal", "LineEdit", field)
	eloria_theme.set_color("font_color", "Label", Color(0.91, 0.86, 0.70))
	eloria_theme.set_color("font_color", "Button", Color(0.93, 0.80, 0.58))
	theme = eloria_theme
	var map_style := panel.duplicate() as StyleBoxFlat
	map_style.set_border_width_all(0)
	map_style.set_content_margin_all(0.0)
	full_map.add_theme_stylebox_override("panel", map_style)
	# The chat frame owns its border; the message area needs no second box.
	chat_panel.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	chat_output.add_theme_constant_override("outline_size", 1)
	chat_output.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.9))
	chat_output.add_theme_color_override("default_color", Color("eee3c8"))
	_style_right_rail(panel)
	var minimap_panel_style: StyleBoxFlat = panel.duplicate() as StyleBoxFlat
	minimap_panel_style.set_border_width_all(6)
	minimap_panel_style.border_color = Color(0.86, 0.64, 0.25, 1.0)
	minimap_frame.add_theme_stylebox_override("panel", minimap_panel_style)
	_minimap_panel_style = minimap_panel_style
	var map_sidebar_style: StyleBoxFlat = panel.duplicate() as StyleBoxFlat
	map_sidebar_style.bg_color = Color(0.0, 0.0, 0.0, 0.98)
	($GameView/FullMap/MapLayout/Sidebar as PanelContainer).add_theme_stylebox_override(
		"panel", map_sidebar_style)
	# Each icon carries its own painted frame right up to the edge of its
	# 32-pixel cell, so with no margin at all the frames butted against each
	# other and against the panel border, and the end ones read as cut off.
	var empty_button: StyleBoxEmpty = StyleBoxEmpty.new()
	empty_button.set_content_margin_all(HUD_ICON_PADDING)
	# An open window used to be told apart by its icon being the coloured one.
	# Now that every icon the player can actually use is coloured, the open
	# window needs a mark of its own, so it takes the lit frame Eternal Lands
	# gives a highlighted icon.
	var active_icon := StyleBoxFlat.new()
	active_icon.bg_color = Color(EL_GUI_INVERT_COLOUR, 0.95)
	active_icon.border_color = EL_GUI_BRIGHT_COLOUR
	active_icon.set_border_width_all(1)
	active_icon.set_content_margin_all(HUD_ICON_PADDING)
	var hover_icon: StyleBoxFlat = active_icon.duplicate() as StyleBoxFlat
	hover_icon.bg_color = Color(EL_GUI_INVERT_COLOUR, 0.5)
	hover_icon.border_color = Color(EL_GUI_COLOUR, 0.75)
	for child: Node in $GameView/Quickbar/QuickRows/Buttons.get_children():
		if child is Button:
			var icon_button: Button = child as Button
			icon_button.flat = true
			icon_button.focus_mode = Control.FOCUS_NONE
			# Twenty-three icons share the bar now, so each cell is trimmed to
			# what fits; the icons are still 40px against Eternal Lands' 32.
			icon_button.custom_minimum_size = Vector2(
				40.0 + HUD_ICON_PADDING * 2.0, 40.0 + HUD_ICON_PADDING * 2.0)
			for state_name: String in ["normal", "disabled", "focus"]:
				icon_button.add_theme_stylebox_override(state_name, empty_button)
			icon_button.add_theme_stylebox_override("hover", hover_icon)
			for state_name: String in ["pressed", "hover_pressed"]:
				icon_button.add_theme_stylebox_override(state_name, active_icon)
	for quick_button: Button in quick_slot_buttons + spell_slot_buttons:
		quick_button.focus_mode = Control.FOCUS_NONE
	_style_meter(health_bar, Color(0.17, 0.82, 0.22, 1.0))
	_style_meter(health_bottom, Color(0.9, 0.16, 0.14, 1.0))
	_style_meter(food_bottom, Color(0.96, 0.78, 0.16, 1.0))
	_style_meter(load_bottom, Color(0.62, 0.43, 0.34, 1.0))
	_style_meter(experience_bottom, Color(0.18, 0.76, 0.22, 1.0))
	for ether_bar: ProgressBar in [mana_bar, ether_bottom]:
		_style_meter(ether_bar, Color(0.24, 0.31, 1.0, 1.0))
	for points_bar: ProgressBar in [action_bar, action_bottom]:
		_style_meter(points_bar, Color(0.73, 0.28, 0.86, 1.0))
	for row_spec: Array in BANNER_ROWS:
		_style_banner_meter(_banner_row(str(row_spec[0])).get_node("Bar") as ProgressBar)
	# Login and creation keep their own heavier fantasy frame and moonlit
	# preview stage rather than inheriting the compact in-game HUD chrome.
	OldcraftEntryStyleScript.apply(self)
	# NPC communication uses a shared parchment surface and compact choices.
	# The helper applies static styles; no actor update pays for this treatment.
	OldcraftDialogueStyleScript.apply(self)

## The right rail used to be six separate boxes with gaps between them, so its
## left edge was six short lines rather than one. One panel now spans the whole
## height behind them and owns the only border; everything sitting in it is
## given a flat, marginless box so the rail reads as a single connected bar and
## the offsets in the scene place content exactly.
func _style_right_rail(panel: StyleBoxFlat) -> void:
	# The rail and the bottom bar are the two opaque fixtures of Eternal
	# Lands' HUD - its wooden frame - so unlike the windows they get a solid
	# warm brown rather than the see-through black.
	var rail_style: StyleBoxFlat = panel.duplicate() as StyleBoxFlat
	rail_style.bg_color = Color(0.16, 0.12, 0.075, 1.0)
	rail_style.set_corner_radius_all(0)
	rail_style.set_content_margin_all(4.0)
	right_rail.add_theme_stylebox_override("panel", rail_style)
	# The bottom panel overlaps the rail's one-pixel left border. Its opaque
	# fill hides that border below the join, leaving one continuous HUD frame.
	var bottom_style: StyleBoxFlat = rail_style.duplicate() as StyleBoxFlat
	bottom_style.border_width_right = 0
	bottom_style.content_margin_top = 2.0
	(%Quickbar as PanelContainer).add_theme_stylebox_override(
		"panel", bottom_style)
	var seamless: StyleBoxEmpty = StyleBoxEmpty.new()
	for framed: Control in [$GameView/EloriaLogoFrame as Control,
			$GameView/SpellQuickbar as Control, $GameView/ItemQuickbar as Control,
			$GameView/ResourceHud as Control, $GameView/RailMeters as Control,
			$GameView/ClockFrame as Control,
			$GameView/CompassFrame as Control]:
		framed.add_theme_stylebox_override("panel", seamless)
	# A rail 62 pixels wide has no room for the theme's 4-pixel button padding
	# four times over: the power row measured 67 and pushed the whole spell
	# column back out of the rail it is supposed to sit in.
	var tight: StyleBoxEmpty = StyleBoxEmpty.new()
	tight.set_content_margin_all(1.0)
	for control: Button in [%SpellPowerDown as Button, %SpellPowerUp as Button]:
		for state: String in ["normal", "hover", "pressed", "disabled", "focus"]:
			control.add_theme_stylebox_override(state, tight)
	# The slot placeholders are "S12" and "8", not labels anyone reads. At the
	# theme size they filled a 26-pixel cell on their own. Read off the scene
	# rather than the bound arrays, which are filled after the theme is applied.
	for column: Node in [quick_slot_container as Node, spell_slot_container as Node]:
		for slot: Node in column.get_children():
			if slot is Button:
				(slot as Button).add_theme_font_size_override("font_size", 9)

## The overhead bars are not the HUD's bars. Eternal Lands draws only the
## filled part and a one-pixel black frame, leaving the world visible through
## whatever is missing, so these get their own transparent-backed style instead
## of the bordered wells the bottom meters use. The fill colour is repainted
## per update by _set_overhead_meter().
static func _style_banner_meter(bar: ProgressBar) -> void:
	var background := StyleBoxFlat.new()
	background.bg_color = Color(0.0, 0.0, 0.0, 0.0)
	background.border_color = Color(0.0, 0.0, 0.0, 0.95)
	background.set_border_width_all(1)
	var fill := StyleBoxFlat.new()
	fill.bg_color = Color(0.17, 0.82, 0.22, 1.0)
	bar.add_theme_stylebox_override("background", background)
	bar.add_theme_stylebox_override("fill", fill)

static func _style_meter(bar: ProgressBar, color: Color) -> void:
	var background := StyleBoxFlat.new()
	background.bg_color = Color(0.015, 0.02, 0.025, 0.96)
	background.border_color = Color(0.72, 0.53, 0.22, 0.9)
	background.set_border_width_all(1)
	var fill := background.duplicate() as StyleBoxFlat
	fill.bg_color = color
	fill.border_color = color.lightened(0.18)
	bar.add_theme_stylebox_override("background", background)
	bar.add_theme_stylebox_override("fill", fill)

static func _external_texture(path: String) -> Texture2D:
	if path.begins_with("res://assets/") and ResourceLoader.exists(path):
		var imported: Resource = ResourceLoader.load(path)
		if imported is Texture2D:
			return imported as Texture2D
		push_warning("Imported UI texture load failed: " + path)
		return null
	var absolute_path: String = ProjectSettings.globalize_path(path)
	var image: Image = Image.new()
	var error: Error
	if path.get_extension().to_lower() == "dds":
		var bytes: PackedByteArray = FileAccess.get_file_as_bytes(absolute_path)
		error = image.load_dds_from_buffer(bytes)
	else:
		error = image.load(absolute_path)
	if error != OK or image.is_empty():
		push_warning("UI texture load failed: " + path)
		return null
	return ImageTexture.create_from_image(image)

func _model_for_actor(dto: Dictionary) -> String:
	var character := NpcCharacterLooks.find(dto, npc_characters)
	if not character.is_empty():
		return str(character["model"])
	var actor_type_value := int(dto.get("actor_type", 1))
	var actor_type := str(actor_type_value)
	var kind := int(dto.get("kind", 0))
	# Player actor IDs are not safe for NPC wire records: the server may send an
	# enhanced packet for an NPC while keeping the legacy actor_type byte at 1.
	# Nymara NPC/creature/enemy IDs occupy the dedicated 200+ registry range.
	if actor_type_models.has(actor_type) and (kind in [1, 4] or actor_type_value >= 200):
		return str(actor_type_models[actor_type])
	# The server uses the enhanced wire layout for most NPCs so their appearance
	# bytes survive replication. Registry actor type wins for native NPCs and
	# creatures; actor kind decides the fallback for unknown records.
	if kind not in [1, 4]:
		return ""
	return "luminous_female" if actor_type_value == 0 else "luminous_male"

func _presentation_dto(dto: Dictionary) -> Dictionary:
	# Keep the actor record shallow. Named NPCs get a separate appearance
	# dictionary; other actors share their unchanged appearance with the state.
	var character := NpcCharacterLooks.find(dto, npc_characters)
	var result: Dictionary = NpcCharacterLooks.present(dto, character)
	# Creation bytes (skin, hair, shirt, pants, boots, head, eyes) select skinned
	# surfaces already authored into each actor GLB, so they are deliberately
	# never reinterpreted as rigid BoneAttachment3D equipment and contribute
	# nothing here. AppearanceVariants used to expose a function for that which
	# returned {} unconditionally and was still called on every actor build; the
	# refusal is stated here instead of hidden behind a call.
	#
	# The legacy visual ids below 100 are real equipment, not creation
	# leftovers, so they are not dropped. An authored NPC look is applied last
	# and outranks the server's appearance bytes, which is how a Four Gates
	# guard keeps its guard gear without an alias hijacking the shared legacy id
	# for every other actor.
	var visuals: Dictionary = {}
	var server_visuals: Dictionary = dto.get("equipment_visuals", {}) as Dictionary
	for raw_part: Variant in server_visuals:
		visuals[int(raw_part)] = int(server_visuals[raw_part])
	var look: Dictionary = npc_looks.get(str(int(dto.get("actor_type", -1))), {}) as Dictionary
	if not character.is_empty():
		look = character
	var look_visuals: Dictionary = look.get("equipmentVisuals", {}) as Dictionary
	for raw_part: Variant in look_visuals:
		visuals[int(raw_part)] = int(look_visuals[raw_part])
	result["equipment_visuals"] = visuals
	# How much ground this actor stands on. Keyed by actor type because a
	# footprint belongs to the species, and defaulted to a single tile, so an
	# older server that never sends the table leaves every actor exactly where
	# it drew them before.
	result["footprint"] = AppState.footprint_for_actor_type(
		int(dto.get("actor_type", -1)))
	return result

## Starts parsing every animation library that more than one model shares -
## the universal race library today - on a worker thread. The parse is the
## bulk of the first actor's spawn cost, and it was paid on the main thread
## the moment that actor arrived, which is the moment the map finished
## loading.
func _prewarm_shared_animation_libraries() -> void:
	var users: Dictionary = {}
	for model_value: Variant in models.values():
		if not model_value is Dictionary:
			continue
		var path: String = str((model_value as Dictionary).get("animationLibrary", ""))
		if not path.is_empty():
			users[path] = int(users.get(path, 0)) + 1
	for path_value: Variant in users:
		if int(users[path_value]) >= 2:
			NativeAnimationImporter.prewarm(
				ReplicatedActor3D._external_path(str(path_value)))

func _animation_for_model(model_config: Dictionary) -> Dictionary:
	var path := str(model_config.get("animationMap", "res://data/animations/luminous.json"))
	if not animation_configs.has(path):
		animation_configs[path] = _json(path)
	return animation_configs[path] as Dictionary

## The rebuilt continent's tab maps (cartography-continent-v2.json, written by
## eloria-assets/maps/continent-v2/_continent_v2/publish_cartography.py): rows
## of cartography.json's shape, on their own frame and with no rectangle on its
## picture, appended after its regions. Their outlines are in its pixel lattice;
## a file written for another lattice is left out rather than misplaced.
static func _continent_v2_tab_maps(legacy: Dictionary) -> Array:
	var tab_maps: Dictionary = _json("res://data/maps/cartography-continent-v2.json")
	var lattice: Dictionary = tab_maps.get("lattice", {}) as Dictionary
	var continent: Dictionary = legacy.get("continent", {}) as Dictionary
	if (str(lattice.get("originMetres", [])) != str(continent.get("originMetres", []))
			or float(lattice.get("metresPerPixel", 0.0)) != float(continent.get("metresPerPixel", -1.0))):
		return []
	return tab_maps.get("regions", []) as Array

static func _json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}

func _road_ui(code: int) -> void:
	if str(AppState.lantern_tutorial.get("tutorial", "")) == "followup":
		Network.tutorial_ui(code)

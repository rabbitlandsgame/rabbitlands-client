# Territory authoring workspace

The **Territories** dock keeps one saved authored territory active and lets you
show any number of neighboring territories as read-only references. All twelve
registered exterior territories have saved scenes and authoring specifications:

- [Sunmane Steppe](../world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn)
- [Amethyst Barrens](../world_authoring/regions/amethyst_barrens/amethyst_barrens.tscn)
- [Mirrorhold](../world_authoring/regions/mirrorhold/mirrorhold.tscn)
- [Whitehorn Range](../world_authoring/regions/whitehorn_range/whitehorn_range.tscn)
- [Amberwood](../world_authoring/regions/amberwood/amberwood.tscn)
- [Crownwater](../world_authoring/regions/crownwater/crownwater.tscn)
- [Four Gates](../world_authoring/regions/four_gates/four_gates.tscn)
- [Grey Moors](../world_authoring/regions/grey_moors/grey_moors.tscn)
- [Manymouth Delta](../world_authoring/regions/manymouth_delta/manymouth_delta.tscn)
- [Ssarathi Ruins](../world_authoring/regions/ssarathi_ruins/ssarathi_ruins.tscn)
- [Verdant Stair](../world_authoring/regions/verdant_stair/verdant_stair.tscn)
- [Westhaven](../world_authoring/regions/westhaven/westhaven.tscn)

Use **Open** to make a territory active. The action opens its native scene tab
through Godot; an already open tab and its unsaved changes follow the editor's
normal save prompt. Select several rows under **Read-only references** to view
neighboring territories together. The workspace never reloads, rewrites, or
auto-saves an inactive scene.

Saved authored source is preferred for a reference; otherwise the dock loads the
territory's current published `world.glb`. The row and tooltip show the source
kind, revision, path, and digest. Reference placement uses the difference
between the reference and active continent translations. Displayed terrain is
clipped to the current manifest ownership polygon. An authored scene is hidden
if its saved ownership hash does not match that polygon. The cyan line marks the
boundary. Clipping affects temporary editor display meshes only. Reference
nodes are internal and ownerless: they are not editable gameplay controls,
cannot receive Map Assets palette placement, and are excluded from saved scene
bytes and continent-authoring snapshots. **Hide all** removes references and
restores the active terrain preview's prior visibility.

Press **Ctrl+S** to save the active scene. The region's **Bake continent
authoring snapshot** button is an active-scene diagnostic; it does not publish a
region. The normal continent build consumes every registered saved scene.
Imported roads start with **Shape terrain** disabled, so moving or deleting one
changes its route and rendering while leaving saved ground unchanged. Enable
**Shape terrain** when an edited road should grade its terrain. Newly created
roads shape terrain by default. Landforms, including islands, are saved ground;
water feature controls edit water independently of the terrain.

To change saved ground directly, use **Territories → Sculpt terrain in 3D**,
choose a brush, and drag on the active terrain. [Terrain sculpting](terrain-sculpting.md)
explains the protected border, undo/save behavior, and how sculpted heights feed
the normal build.

Whole-feature water ownership follows the registered source IDs: Amberwood owns
`western_river`, `amber_tributary`, and `whitehorn_torrent`; Grey Moors owns
`moor_tributary`, `moor_headwater_tarn`, and `moorwater_pool`; Manymouth Delta
owns `western_distributary` and `eastern_distributary`. The existing Sunmane,
Amethyst, Mirrorhold, and Whitehorn claims are unchanged. Ferry landing edits
are checked against connected geometry, and their source connection IDs remain
part of the saved ownership. Runtime markers without a matching visible
landmark use dedicated `RuntimePoints`; not every marker represents a visible
object.

Boundary changes are validated. The all-twelve build uses each saved scene's
exact terrain; legacy mixed-state seam and post-support corrections skip
saved-owned targets. Fixed neighboring approach corrections on procedural
shoulders may need refreshing and recertifying if their source terrain or route
changes. They cannot overwrite a neighboring territory after it becomes saved
authored.

Ferry landings move with their saved quay controls and are checked against the
connected bank and water. A saved endpoint does not receive a regenerated quay
or native approach road. Deleting its quay disables that ferry connection
rather than restoring a generated replacement.

## Terrain appearance

Select **Terrain**, expand **Base Surface**, and choose a named **Texture** to
change the territory's main ground. The new ground textures repeat about every
four metres at the territory's saved Terrain UV setting; Texture Rotation and
advanced UV scale remain saved per Surface. Enable **Biome Blend** on the Base
Surface to
let adjacent opted-in territories share a soft, world-aligned boundary. The
exported dominant material remains the fallback on clients that cannot load a
blend mask.

Opted terrain replaces the old absolute biome vertex colour with its selected
palette. Local Ground Regions and roads remain separate meshes, so their saved
paint and materials are unchanged.

Each territory may add one **Biome Palette** entry on Terrain. Give it a stable
Id, choose the landscape Role that should reveal it, and choose its local
Surface. The build turns an existing landscape weight such as woodland,
grassland, heath, wetland, rock, snow, sand, or limestone into the secondary
mix; there is no separate paint layer to keep in sync. Ground Regions still
provide explicit local patches and
continue to draw over the shared base. Roads, rivers, water, and object Surface
overrides also retain their own materials.

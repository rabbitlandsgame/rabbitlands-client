# Map editor usability

The map editor still runs inside Godot, but the placement and viewport tools now work more like a dedicated map editor. Three plugins are involved:

- **Map Assets** (`addons/map_asset_palette`): the asset library with its drop-in model folder, ghost placement, and prefabs.
- **Map Authoring Usability** (`addons/map_authoring_usability`): the cursor readout, the cursor grid, the **Map tools** menu, the toolbar toggles, the selection bar, groups and copies, readable gameplay markers, the walkability overlay, road and river drawing, the continent plan's water, the concept master overlay, ground regions and plateaus, scatter, the play-test walker, the **Minimap** and **Review notes** docks, the low-spec view, the time-of-day preview and the top-down capture.
- **Territories** (`addons/map_authoring_workspace`): now also has sculpt brush keys (see [terrain-sculpting.md](terrain-sculpting.md)), heightmap import with a preview and an area picked on the map, and a **Browse…** map picker.

The map team's answers on what each tool may write are in [map-team-editor-contracts.md](map-team-editor-contracts.md).

Everything in this document works in production region scenes, and everything except the terrain-based tools works in the pilot. None of it changes the save, snapshot, or bake contracts. Ghosts, grids, pins, the walker and every other helper are ownerless nodes, so they are never packed into a scene. The only new thing a scene saves besides ordinary controls is the group tag on grouped objects; the snapshot's geometry and gameplay records ignore it, although saving the scene changes its source hash as any save does. Review notes live in a separate file beside the scene that nothing references (see [Review notes](#review-notes)). Every edit goes through Godot's normal undo history, which you can see and jump through in the **History** dock next to FileSystem.

## Toolbar

The 3D toolbar has one-click toggles next to **Map tools** and **Time**:

| Button | What it switches |
|---|---|
| **Grid** | The cursor grid all the time (off: only while placing). |
| **Snap** | Grid snapping for placement, copies and drawn points (same as G). |
| **Ground**, **Plateau** | Open the ground-region or plateau options (see below). |
| **Pins** | Gameplay marker pins and labels. |
| **Walk** | The walkability overlay mode (a small menu). |
| **Play** | The play-test walker. |
| **Low spec** | The low-spec view. |

The buttons and the **Map tools** menu always agree; either can be used.

## Place assets

### Choose and arm an asset

1. Open **Map Assets**. The library is a thumbnail grid; switch **Grid** off for a plain list.
2. Search, or pick a category. Prefabs appear in their own **Prefabs** category.
3. Select an asset and press **Place on terrain**, or double-click the asset.

Thumbnails are rendered from the models themselves and cached in the editor cache folder, so only the first open of the library takes time.

### The territory's own kit

With a territory open, its own kit is listed too: every `.glb` in the `assets/prototypes` folder beside its scene, under **Territory kit: scenery** (walk-through pieces) and **Territory kit: structures** (solid ones). So more of a territory's tents, rocks or trees are placed or scattered straight from the palette, rather than by copying a placed one.

- **Same identity as the copies already placed.** A piece the scene already uses keeps that copy's catalog id (for example `sunmane:kit-cart`) and its most common collision role.
- **New pieces.** A piece nobody has placed yet is named `<prefix>:<file>`, with the prefix the scene's kit copies use. It starts walk-through when its file name says ground cover (shrub, grass, scrub, sage, bones, tree, scree and the like), otherwise solid.
- **Adding pieces.** Sunmane's ground cover and herding props are exported by `eloria-assets/maps/nymara-regions/sunmane_steppe/source/export_editor_kit.py` from the territory's own kit builders; `--check` confirms the committed files match.

### Place it

A see-through, blue-tinted ghost follows the cursor over the terrain. It shows exactly what the next click will create.

| Input | Action |
|---|---|
| Click | Place the asset. With **Keep placing** on (the default), you stay in placement mode, so you can click again and again. |
| Right-click or Escape | Stop placing. |
| Alt+drag | Orbit the camera, as usual. |
| Q / E, or Shift+mouse wheel | Turn the asset (15° steps). |
| Page Up / Page Down | Raise or lower it (0.25 m steps). |
| Home / End | Grow or shrink it (10% steps). |
| Shift with any of the keys above | Use fine steps: 1°, 0.05 m or 1%. |
| Backspace | Reset turn, height and size. |
| G | Toggle snapping to the territory grid. |

Two text lines at the bottom of the 3D view show the current turn, lift, size and snap, and list these keys.

### Placement options

The **Placement options** section of the dock has these settings:

- **Keep placing**: stay in placement mode after each click.
- **Random turn**: give each placed asset a random turn.
- **Size ±**: vary each placed asset's size by up to this percentage.
- **Align to slope**: tilt the asset so it follows the terrain slope.
- **Snap to grid** and **Grid**: snap placement to the grid, and set its spacing in metres. The default is 1 m, which is one server tile in production regions.

The ghost is re-rolled after every click, so it always shows what the next click will create.

These options are per-user preferences stored under **Editor Settings > Map Authoring**. Every key in the table above can be rebound under **Editor Settings > Shortcuts > Map Authoring**.

### Add your own models (no JSON)

Any `.glb`, `.tscn` or `.scn` file under `res://assets/world/library/` is a palette asset. A first-level subfolder names its category: `library/Rocks/boulder.glb` is listed as **Boulder** under **Library: Rocks**; files directly in `library/` are under **Library**. Press **Refresh** after adding files yourself.

**Import models…** does the copying for you: type a category (for example `Rocks`) and pick one or more `.glb`/`.gltf` files anywhere on disk. A `.glb` is copied as it is; a `.gltf` is converted to one self-contained `.glb`, because the bake accepts only static GLB sources. Nothing is overwritten, and the palette lists the models once Godot has imported them. A `.gltf` dropped into the folder by hand is not listed; Refresh says so. **Folder** shows the library in the FileSystem dock.

Library assets place like catalog ones. Their catalog id is `library:<category>/<name>`, and the scene path goes into the snapshot like any other asset's. Being listed is not the same as being admitted to production: prefer self-contained static GLB models with a Node3D root, metre-scale geometry and PBR textures; the bake still checks surfaces and paths.

Selecting a library asset lists under **Check before use** anything the bake or the game will not carry as the editor shows it. The scene file is read without running any of its scripts. The list covers:

- a root that is not a Node3D;
- scripts (they never run in the game);
- custom shaders, which do not survive the export to GLB;
- triplanar materials, which the bake does not support;
- no mesh at all;
- any side longer than 80 m, the library extractor's limit for one asset and usually a unit slip. The collision role starts from the category name (`solid` when it contains "structure", "interactive" or "landmark", otherwise `none`). Treat that as a suggestion, choose `walk_surface` deliberately, and leave collision changes to the map team's review.

### What gets created

Assets are placed as before. They become `MapAuthoringAssetControl` wrappers under `AuthoredAssets`, with a fresh asset id, the catalog id, the scene path and the default collision role. Grounding uses the visible mesh bounds, and each click is one undo step.

## Cursor readout and grid

### Cursor readout

While the cursor is over authored terrain, the bottom-left of the 3D view shows:

- territory-local X and Z in metres;
- the server tile, using the snapshot conversion `floor(x/metres_per_tile + server_origin.x)`, `floor(server_origin.y - z/metres_per_tile)`;
- the ground height;
- the number of selected placements.

### Cursor grid

The cursor grid is a small grid that drapes over the terrain around the cursor and follows its height. It turns gold while snapping and marks the exact snap point.

Choose when it appears with **Map tools > Cursor grid**: **Off**, **While placing** (the default) or **Always**. **Map tools > Cursor readout** hides the text line.

The grid needs region terrain. The pilot has no fast height query, so the grid is not shown there.

## Map tools menu

**Map tools** in the 3D toolbar works on the current selection. It only ever touches assets, cosmetic scenery and gameplay markers. Terrain patches, paths, bridges, water and ground regions are never moved by it.

| Item | What it does |
|---|---|
| **Drop selection to ground** | Re-seats each object's visible base on the terrain under it. Use it after sculpting, because objects do not reground automatically. |
| **Rotate each 90°** | Turns every object about its own pivot, not the selection centre. |
| **Random turn for each**, **Random size for each** | Scatter variation. Random size keeps each object's base on the ground. It uses the **Size ±** amount, or ±15% when that is 0. |
| **Save selection as prefab** | Saves the selection as a prefab (see below). |
| **Group selection**, **Ungroup** | See [Groups and copies](#groups-and-copies). |
| **Duplicate with fresh ids** | Copies the selection one grid step south-east with new ids (see below). |
| **Show the continent plan's water** | Draws the plan's rivers and lakes over the territory, read-only (see [The continent plan's water](#the-continent-plans-water)). |
| **Show the concept master on the terrain** | Lays the coordinate-locked concept art over the terrain, read-only (see [Concept master](#concept-master)). |
| **Scatter the selected asset…** | Paints or erases copies of the asset chosen in Map Assets (see [Scatter](#scatter)). |
| **Play test** | Starts or stops the play-test walker. |
| **Low spec view** | Switches the low-spec view. |
| **Time of day preview…** | Opens the time panel (see below). |
| **Capture top-down image…** | Saves a map image of the territory (see below). |

Each item is a single undo step. The items can be given keys under **Editor Settings > Shortcuts > Map Authoring**; they are unbound by default.

## Selection bar

While placed assets, scenery or markers are selected, a bar under the 3D view shows what is selected and lets you type exact values:

- **X / Y / Z**: territory-local metres (the same frame as the cursor readout).
- **Turn**: degrees about the vertical axis. **Size**: uniform scale; a single asset keeps its visible base on the ground.
- With several objects the bar shows their centre. Typing X, Y or Z moves them together; **Turn by** and **Scale by** turn or scale the whole selection about its centre and then reset to 0 and 1.
- Buttons: **Drop**, **Rotate 90°**, **Duplicate**, **Group**, **Ungroup**, **Edit members** and **Save prefab**.

Every change is one undo step.

## Groups and copies

**Groups.** Select two or more placed objects and press **Ctrl+G** in the 3D view (or **Group** in the selection bar or Map tools). Clicking any member then selects the whole group, so it moves, turns and copies as one. **Ctrl+Shift+G** ungroups.

- **Pick one member:** double-click it, or press **Edit members**. The group stays open for single picks until you select something outside it.
- **What is saved:** each member keeps its place in `AuthoredAssets` or `Gameplay`; a group is only a `map_authoring_group` tag in the members' node metadata (not the asset's exported `metadata` dictionary). The snapshot's object and gameplay records ignore it; saving the scene still changes its source hash, as any save does.
- Ctrl+G and Ctrl+Shift+G group only while the 3D view has keyboard focus (click in it first). Elsewhere Godot's own **Group Selected Nodes** shortcut, which makes clicks on children select their parent, takes those keys. The **Group** button always does the map group.

**Copies.** Hold **Alt** and drag a selected object: a ghost of the selection follows the cursor and the copies are dropped where you release (Esc cancels). **Duplicate** in the selection bar or Map tools copies one grid step away instead. Either way the copies are one undo step and are selected afterwards.

- Every copy gets a fresh asset id or marker record id, its own copies of local material overrides, and new group ids (a copied group becomes a new group).
- Each copy keeps its height above the ground, so copies on a slope sit on the ground.
- A marker that follows or links to a copied asset follows or links to the copy; one copied without its asset stops following and loses the link.
- Runtime bindings are never copied, a copied default spawn is not a default spawn, and the extras that describe one placement (`propPosition`, `destinationTile`, `rotationDegrees`, `reachable`) are dropped.
- Portal destinations are kept. The status line says how many copied portals still lead to the original's destination, so you can check them in the Inspector.
- With **Snap** on, the drag moves in whole grid steps.

**Godot's Ctrl+D.** It keeps the original asset and record ids, and the snapshot rejects two objects with one id. In the 3D view, Ctrl+D on placed objects is therefore redirected: it duplicates them in place with fresh ids. A duplicate made another way (the Scene dock's Duplicate) is caught within a second: a warning appears at the top of the 3D view and **Map tools > Give duplicated copies fresh ids** fixes it in one undo step. Only the copies change; the originals keep their ids. Ids are compared the way the snapshot compares them (assets together, each gameplay kind on its own), and duplicates a scene already had when it opened, such as Manymouth's retained `stelae-court` pair, are left alone.

Alt+drag on empty ground, or while placing, still orbits the camera.

## Prefabs

### Save a prefab

1. Select placed assets and, if you like, gameplay markers.
2. Type a name next to **Save selection** in Map Assets, then press it (or use **Map tools > Save selection as prefab**).

The prefab is written to `res://world_authoring/prefabs/<name>.tscn`, and **Folder** shows it in the FileSystem dock.

### Place a prefab

Prefabs hold placed assets and gameplay markers. Other controls (paths, water, terrain) are left out, and the message says how many. A marker is saved without what a copy must not keep (runtime bindings, a default spawn, placement extras), and a follow or link to something outside the prefab is dropped.

Place a prefab like any other asset: the ghost shows every member, and turn, lift, size and snap apply to the whole group.

- Markers go into their kind's container under `Gameplay` with fresh record ids, and turn with the prefab. A marker that followed or linked to an asset in the prefab follows or links to that asset's placed copy.
- Copied portals keep their destination, and the status line says so.

- Members follow the terrain. Each member keeps the height above the ground it had when the prefab was saved, so a camp placed on a slope still sits on the ground.
- Each placement creates ordinary, independent assets. They get fresh asset ids and their own copies of local material overrides.
- Placing a prefab is one undo step. The prefab file itself never enters a bake or snapshot.

## Gameplay markers

### Place markers

**Map Assets** has a **Gameplay markers** category. It offers one plain entry for each marker kind the region snapshot exports:

- Spawn point
- Portal
- NPC
- Harvestable
- Interactive
- Landmark
- Herd / ambient animals

**Templates.** The open territory also adds templates copied from its own markers, for example "Harvestable: Crystal (mineral)". A template copies that group's label (for harvestables) and extras, such as the harvest hook, extent, NPC role or herd model. Position-specific extras are never copied: prop positions, destination tiles and rotations.

**Placing.** Markers place like assets: a coloured ghost pin follows the cursor, and snapping, lift and keep-placing all work. Q/E turn a spawn's or portal's facing.

**What gets created.** Each new marker gets a fresh record id of the form `<label>-NN`, unique in the territory. It goes into its kind's `Gameplay` container, and each marker placement is one undo step.

**Follow-up in the Inspector:**
- Portals still need **Destination Map** and **Destination Spawn**.
- NPCs start unnamed.

**Runtime points are left out.** They bind certified server records, so they are never created in the editor.

### Readable markers

Every gameplay marker is drawn as a coloured pin with its label (or record id):

| Colour | Kind |
|---|---|
| Green | Spawn |
| Violet | Portal |
| Blue | NPC |
| Orange | Harvestable |
| Cyan | Interactive |
| Gold | Landmark |
| Pink | Herd |
| Grey | Runtime point |

- Spawns and portals show a facing arrow.
- Harvestables show their extent, and herds show their radius.
- Labels fade out beyond 140 m.
- Switch pins or labels off under **Map tools > Gameplay markers**.

## Walkability overlay

**Map tools > Walkability overlay** tints the terrain in one of three modes.

| Mode | What it shows |
|---|---|
| **Published grid (exact)** | The served grid from the territory's published `collision.bin` (EWCG-v2, half-metre cells), exactly as the server walks it after the last publish. |
| **Live suggestion from authoring** | A 1 m-tile estimate from the current scene, using the bake's rules in `collision_export.py`. Rebuilds itself about half a second after edits settle; not during a sculpt stroke. |
| **Changes since publish** | Tiles where the live suggestion disagrees with the published grid: what the next bake is likely to open (green) or close (magenta). |

A legend sits at the top right of the 3D view. The cursor readout adds the tile's published state and its live class: "too steep (grade 0.82)", "blocked by Camp00_Cart", "deck of Harbour_Stair".

The live suggestion classifies each tile as follows:

- **Grade.** The terrain triangle's slope must be at most 0.65. This is computed exactly from the saved heights, and a tile takes the worst of the triangles its half-cells fall in, like the served grid's fold.
- **Water.** A tile is blocked when any of its half-cells stands more than 0.35 m under water, measured from where the actor stands there (a deck that carries the cell, else the terrain). A deck over a river keeps the cells it carries dry; a deck that only partly covers deep water leaves the tile under water. Water means:
  - the sea level from the territory's manifest (or the continent plan);
  - authored rivers, using their point heights as the water surface;
  - water regions;
  - the continent plan's rivers and lakes that this territory has not claimed (see [The continent plan's water](#the-continent-plans-water)).
- **Structures.** These are exact: the bake's own test (`structural_mask`) runs on the editor's meshes at every half-metre cell, and a tile is blocked when any of its four cells is.
  - A triangle blocks a cell when it crosses the actor's body there: 0.5 × 0.5 m, from 0.06 m to 2.10 m above where the actor stands.
  - A closed mesh also blocks the cells inside it.
  - A roof over head height leaves a doorway open, while a fence blocks only its rails.
  - Which meshes count follows the exported hierarchy. A mesh is solid when its asset is `solid` and it sits under the asset's first scene root, unless it is under a `Terrain_` or `Walk_` surface that is not a ceiling. Further scene roots are exported as companions, which the bake does not treat as solid.
  - On 26 September 2026 the port matched the bake's Python cell for cell on all 159 of Sunmane's solid assets. The editor checks solids on a worker thread and reuses results for assets whose meshes and ground did not change; until an asset's check finishes it is estimated from its mesh boxes, and the legend says how many still are.
- **Decks.** A mesh is a deck when a `Walk_` node is among its ancestors (the asset's node name counts) and none of them names a ceiling, soffit, underside or roof, whatever the asset's collision role. A `walk_surface` asset without a `Walk_` node makes no deck in the bake, so it makes none here either. A deck supports a cell when its highest upward face there is no more than 3 cm below the terrain; the actor then stands on it. Procedural bridges use their deck quads.
  - A tile is a deck when each of its half-cells is carried or stands on gentle ground.
  - A deck never overrides a structure, and only partly covering deep water leaves a tile under water.
  - Decks matched the bake on Sunmane too: the same supported cells and the same heights.
- **Composer context.** The published package also has decks and solids the scene doesn't contain: border thresholds, cave-door decks, discovery decks, designed decks. They are read, read-only, from the package the bake reads (`world.glb`), using the bake's own naming rules. Anything whose names match something the scene carries (a placed asset, a bridge) is left out, so the scene's own version wins. The cursor readout names them "published …".
- **Ownership.** Only land inside the territory's ownership polygon is shown.

How close it gets, measured on 27 September 2026 against the published grids of the 27 September release (owned tiles that agree):

| Territory | Agreement | Territory | Agreement |
|---|---|---|---|
| Amberwood | 99.71% | Mirrorhold | 100.00% |
| Amethyst Barrens | 99.98% | Ssarathi Ruins | 99.99% |
| Crownwater | 99.98% | Sunmane Steppe | 99.99% |
| Four Gates | 99.46% | Verdant Stair | 99.99% |
| Grey Moors | 99.95% | Westhaven | 99.99% |
| Manymouth Delta | 99.76% | Whitehorn Range | 99.96% |

The remaining differences are all water along river banks: live calls a few bank tiles water that the published grid walks.

A full rebuild takes 1.5–4 s with every solid checked, and well under a second when the checks are reused.

Where it still differs:

- **River banks.** The composer blends a plan river's levels across bends, which the editor doesn't copy, so a few bank tiles near the 0.35 m limit differ.
- **Bake-only rules.** The certified seam collar and gate halos are not reproduced.
- **Unpublished edits.** When the scene is newer than its package, the difference is the edits, which **Changes since publish** shows. On 26 September Sunmane agreed only 94% for that reason, because 128 of its objects had moved since its last publish; its republished package now agrees 99.99%.

Use **Published grid** for the truth, and **Changes since publish** to judge an edit.

## Draw roads and rivers

**Map tools > Draw road** (or **Draw river**) lays out a new path by clicking on the terrain:

| Input | Action |
|---|---|
| Click | Add a point. The draft drapes over the ground at its full width while you draw. |
| Double-click, Enter or right-click | Finish. |
| Backspace | Remove the last point. |
| Esc | Discard the draft. |
| `[` / `]` | Change the width (Shift gives fine steps). |
| G | Toggle grid snapping. |

A click within 2.5 m of an existing path point snaps onto it exactly, so new paths join cleanly.

**Extend a road.** Start drawing on either end of an existing road (or river) and the new points are added to that path instead of a new one: it keeps its id, surface, width and settings. Starting on the last point appends; starting on the first point adds the new points in front. The extension is one undo step. To start a separate path at an end, Ctrl+click it.

Paths the map team owns are never extended. The click says why, and Ctrl+click still starts a separate path there. They are:

- a path that replaces a composer route or a planned water feature;
- a path the territory lists among its owned routes or plan features;
- a river that joins shared water;
- an end within 4 m of the ownership border, or past it (a seam tail).

An extension keeps the path's point widths on their points: a width set on the old first point stays on it when points are added in front, and undo puts them back.

Finishing creates an ordinary `MapAuthoringRegionPath` under `Roads` or `Rivers`, as one undo step:

- **Id:** a fresh `road-NN` or `river-NN`.
- **Replacements:** no route or plan-feature replacement, since the bake only suppresses a composer route that a path names exactly.
- **Routing role:** `required` for roads and `decorative` for rivers. The baseline pipeline only validates this role.
- **Shape terrain:** on for roads, with feather 2, as new roads should be.
- **Surface:**
  - roads: the territory's road surface, or a Worn earth road surface from the same factory the bake checks;
  - rivers: default water.
- **Point heights:** taken from the ground under each click. A road grades the ground between them. A river's heights are its water surface, and the river carves its channel below.
- **River channel:** the composer refuses a river without `channelDepth`, `valleyWidth` and `bankHeight`, so a drawn river always has them.
  - If the territory already has a river, the new one copies its depth, bank and feather, with the valley scaled to the new width.
  - Otherwise it gets the map team's defaults: depth 1.45 m, feather 5.5 m, bank 2.5 m, and a valley of six widths (at least 30 m). Shape terrain is off.

Afterwards Godot's Path3D tools and the Inspector edit the path as usual.

Drawing, asset placement and sculpting are mutually exclusive; starting one stops the others.

## Play test

**Play** (or **Map tools > Play test**) puts a stand-in character on the open territory:

| Input | Action |
|---|---|
| Click the ground | Place the walker, then walk it there on the next clicks. |
| Shift+click | Place the walker somewhere else. |
| R | Switch between walking and running. |
| F | Centre the 3D view on the walker. |
| Esc or right-click | Stop the play test. |

The route is the one the server would take:

- **Grid.** The server walks one-metre tiles. Its grid is folded from the territory's published package (`collision.bin`): a tile is blocked when any of its four half-metre cells is, otherwise it takes the highest, and heights become codes at the map's stage (1.4 m on Sunmane, 4.8 m on Whitehorn). The walker repeats that fold; on 26 September 2026 it matched the server's grids byte for byte on all twelve territories.
  - The stage is chosen the server's way. It tries the stages its ladder allows and keeps the smallest whose largest connected area is within 1% of the best. A low-relief map can therefore get a coarser stage than its relief alone needs.
- **Served grid (continent-v2 maps).** A territory whose `world.json` declares `collision.servedGrid` publishes the server's grid itself: `served-grid.escg.gz`, one 16-bit code per tile, 50 mm a code above the continent datum (−100 m), with the climb in its own header (1.0 m). The server vendors that file byte for byte, so the walker loads it rather than folding `collision.bin` (`served_grid.gd`; the format is eloria-server's `docs/served-grid.md`). It is read as strictly as the server's sync reads it: `servedGrid` must name its `binary`, the file's SHA-256 must equal `servedGrid.sha256` exactly (lowercase hex), the gzip must be one member with nothing after it, the header's CRC must match the codes, and the header must state the unit, climb and datum `world.json` gives. When the package states a `coordinateTransform`, its `serverOrigin` must be the scene's `server_origin` and its `serverCells` the grid's size (one metre a tile, server y inverted), so a stale scene is refused rather than walked on the wrong tiles. Any of these failing stops the play test with the reason. Older territories keep the folded grid above.
- **Steps.** Neighbours are tried N, NE, E, SE, S, SW, W, NW. A step needs both tiles walkable and a code change of at most the map's climb: 2 codes (`max_walk_height_change`) on a folded grid, 20 codes (1.0 m) on a served grid, where any non-zero code is walkable (a folded grid keeps the server's `code & 0x3F`). A diagonal also needs both of its orthogonal steps. The search gives up after 100 000 tiles, a route is at most 512 steps (click again to go on), and a click on a blocked tile goes to the nearest walkable tile within 19.
- **Pace.** 600 ms a metre walking and 200 ms running, times √2 on a diagonal.
- **Heights.** The walker stands on the terrain, or on the published deck height where a bridge or floor is higher (on a served grid, the tile's own 50 mm height).

A territory that has never been published uses the live walkability suggestion with the same rules; those routes are estimates. One whose manifest declares a served grid it does not ship is estimated with the served rules (heights rounded half up to 50 mm codes, 1.0 m climb). The live server also accounts for other players and creatures, doors and portals, storage-body footprints and a few legacy floors, which the walker does not. Loading the grid takes about 0.1 s on Sunmane, and 0.4–0.9 s for a 2046 × 2046 served grid (the SHA-256, gunzip, row delta and CRC). Routes take 30–600 ms, and up to about a second when the search runs out. The reach tint after a failed route floods the whole grid on the main thread: about 3 s on a 2046 × 2046 served grid.

**When a route fails**, the reachable area is tinted: blue where the walker can go, orange for walkable ground cut off from it. **V** shows or hides the tint at any time. The message says whether the goal lies in the walker's area but beyond the server's search, or is fenced, walled, too steep a climb or cut off.

**Portals and border lanes.** A route that steps on a published walk-on portal or a border crossing lane on the way (not as its goal) is flagged. The server never walks across a portal it was not sent to, so its route goes round it. The walker only warns here, because the full portal table and the exterior connections are server configuration.

The walker, its route line, goal ring and tint are never saved. Starting placement, sculpting, road drawing or a ground tool ends the play test.

## Paint ground regions

**Ground** (or **Map tools > Paint ground regions…**) opens the options: a surface (one the territory already uses, or a texture preset), the shape, feather, opacity and priority. **Start drawing**, then press where a region's centre goes and drag out its size. Each release adds an ordinary ground region control under `Ground/Regions` with a fresh `ground-NN` id, one undo step each; the tool stays armed until Esc (with no draft) or right-click. `[` and `]` change the feather.

- **Turn:** Q and E turn the next shape 15° (5° with Shift). The region keeps that yaw, and the dragged corner sets its size along the turned sides.
- **Paint along a stroke** (the **Mode** option): press and drag to lay a region of the **Brush size** every 60% of the brush along the drag. The whole stroke is one undo step. Stamps outside the owned land are left out, and the stroke stops at the 127-region limit; the message says how many were placed.

- A shared surface file is reused as it is, so later edits to it change every region using it; a surface embedded in another region is copied, and a preset makes a new local surface.
- The region and its feather must stay inside the land the territory owns.
- A territory holds at most 127 ground regions, the most the terrain preview draws; the tool refuses more.

## Stamp plateaus

**Plateau** (or **Map tools > Stamp plateaus…**) creates terrain patches under `Terrain/Patches` the same way: press at the centre, drag out the size. **Level at a height (Set)** flattens the ground to the chosen height above the point you pressed; **Raise or lower (Add)** moves it by a delta. Page Up and Page Down change the height, `[` / `]` the feather, and Q / E turn it. Each stamp is a `stamp-NN` patch, one undo step.

- A stamp may only touch ground the sculpt brush could edit fully: none of its terrain samples may be locked or in the faded border band. The tool refuses a stamp that reaches them, and it only starts once the Territories dock has loaded the territory's borders.
- Patches apply before road and river shaping, so a road running through a plateau still grades its own corridor.
- A plateau shapes terrain only: it does not make ground walkable (the 0.65 grade, water and structure rules still apply) and cannot make caves or overhangs.

## Import a heightmap

**Territories > Import heightmap…** writes a greyscale image into the terrain's sparse sculpt layer. Choose the image, **Replace heights** or **Offset heights (add)**, the height black maps to and the height white maps to (there is no implied scale), and the area it covers in terrain metres (it starts as the whole terrain grid). The image's top row is north.

- **Pick area on map** hides the dialog. Drag a rectangle on the terrain in the 3D view, and the dialog comes back with the area filled in. Esc or right-click keeps the area as it was.
- **Preview** shows the result on the terrain without keeping it and without an undo step. **Import** keeps it as one undo step back to the ground as it was before the preview, and **Cancel** puts the ground back.

- **Replace** sets each editable sample to the image's height; **Offset** adds the image's height to what is there.
- Borders are protected as for the brush: locked samples never change and the fade band blends in. The original base height file is never rewritten, and the layer stays bound to it, so a changed base rejects the layer.
- It is one undo step, saved with the scene like any sculpt. Patches and road and river shaping still apply on top, so the finished ground can differ from the image where those are.

## Minimap

The **Minimap** dock shows the open territory from above, north up, clipped to the land it owns:

- the 3D camera as a blue dot with its view direction;
- the selection as orange squares;
- gameplay markers in their pin colours (when **Pins** is on);
- the play-test walker and its route.

Click or drag on the minimap to move the 3D view there. The view centres on the spot and keeps its angle and zoom; the selection is left as it was.

The picture is rendered from the scene when a territory opens, at 0.5 px/m (**Editor Settings > Map Authoring > Minimap**), lit at noon unless the time preview is on, so it shows unpublished source edits. The dock brightens its copy so the owned land reads at a steady level, because a map seen straight down at a territory's own light can be dim. That is for reading the map only; top-down captures are left as rendered. Press **Refresh** after large edits. The overlays follow the scene continuously.

The menu next to **Refresh** switches between **Live**, **Last published**, **Side by side**, **Concept master** and **Live beside concept**.

- **Last published** is the package's own minimap image (`world.json` `minimap`), cut to the same frame so the two line up. It is what the game shows now and has none of the unpublished edits.
- **Concept master** is the coordinate-locked concept art for the territory (see [Concept master](#concept-master)), cut the same way.

The overlays and click-to-jump work on every picture. Review notes show as small diamonds, orange for open and grey for resolved, following the notes dock's filter.

**Why the terrain can look darker in the editor than in the game.** A controlled render on 26 September 2026 compared the editor preview with the game's own loader. Both used the Compatibility renderer, the manifest's noon light and exposure, one camera, and grey cards.

- **Amberwood:** the preview and the game agree within 1%.
- **Sunmane:** the game shows the base ground with its plain exported material, while the editor draws the biome blend the continent catalog defines.
  - The game's loader applies the blend only to nodes named `AuthoredGround_<region id>Base`.
  - Sunmane's package keeps its already-published name `AuthoredGround_SunmaneBase`.
  - The fix belongs to the runtime or the exporter, not to the editor preview.

It is the only territory where this happens.

## The continent plan's water

**Map tools > Show the continent plan's water** draws the rivers and lakes of `_continent/diagonal-plan.json` that reach the open territory, in its own frame.

- **Claimed water (grey)** is water the territory replaces: a scene river or lake whose **Replaces Plan Feature Id** names it, or an id in the territory's owned plan features.
- **Plan-only water (blue)** is the map team's. The composer adds it whether or not the scene has it.
- **Shape.** Rivers follow the composer's own centreline: a Catmull-Rom curve through the plan's points, six samples a span. Plan widths are half-widths from the centreline, as the composer reads them. Lakes honour their angle.
- **Labels** give each feature's name and who claims it.
- **Walkability:** the live walkability suggestion floods under plan-only water too.

The display is read-only: nothing edits the plan, and shared topology, mouths, joins and claims stay with the map team. It is never saved.

## Scatter

**Map tools > Scatter the selected asset…** paints copies of the asset chosen in the Map Assets dock (not a marker or prefab). The options are:

- the brush radius;
- the density (copies per 100 m²);
- the minimum spacing;
- random turn;
- size variation;
- the seed.

Press and drag in the 3D view.

- **Where copies go.** A stamp is taken where the stroke starts and every brush radius along it. Each stamp tries density × area spots spread over the brush and keeps those at least the spacing from every copy already kept and from placed copies of the same asset, inside the owned land.
- **Undo.** A stroke is one undo step.
- **Seeds.** The same seed gives the same spots, and each committed stroke moves to the next seed.
- **Keys.** `[` / `]` change the radius, Page Up and Page Down the density. Esc discards a stroke; right-click stops.
- **What is saved.** Only ordinary asset wrappers, exactly as if each copy had been placed by hand, with fresh ids and the asset's collision role suggestion. The seed is used only while placing.
- **Avoid.** Copies can avoid four kinds of ground, each a checkbox that starts on. A refused spot uses no random numbers, so a seed still gives the same spots.
  - water: the sea, rivers, water regions and the plan's unclaimed water;
  - steep ground: steeper than **Steepest ground**, 0.65 by default;
  - roads: their width plus half a metre;
  - structures: the footprints of solid assets.
- **Erase.** **Mode: Erase copies**, or X while the tool is armed, removes every placed copy of the chosen asset under the stroke, including copies placed earlier, as one undo step. Nothing else is ever removed.

This is not foliage painting: there is no density map or LOD, and dense grass still needs the map team's foliage budget.

## Review notes

The **Review notes** dock keeps comments pinned to spots in the open territory. It stores them in `<region>.editor-notes.json` beside the region scene, in the map team's proposed format (`eloria-editor-notes-v1`: `regionId`, and notes with `id`, territory-local `position`, `text` and `status` open or resolved).

- **Add at click**, then click the spot, to pin a note with the typed text. Ids run `review-001`, `review-002` and so on.
- **Edit.** **Save text**, **Resolve** or **Reopen**, and **Delete…** (which asks first) change the chosen note. **Go to** (or a double-click) moves the 3D view to it.
- **Pins.** Open notes show as orange pins and resolved ones as grey, in the 3D view and on the minimap. The pins are internal and never saved.
- **Filter.** Show all, open or resolved notes; the list, pins and minimap follow it, and the dock counts open and resolved notes.
- **No undo.** Notes are not scene edits: every change is written to the file straight away.
- **Problems.** A notes file with problems keeps working for its valid notes, and the dock lists what is wrong. Problems are an unsupported schema, a different region, duplicate ids, bad positions, text or statuses. Such a file is never rewritten, so nothing in it is lost or silently fixed.
- **Kept out of the game.** Nothing references the file, so the snapshot, bake and runtime never see it; the test checks that a snapshot is identical with and without notes. The client package leaves out `*.editor-notes.json` (`tools/package_client.py`).

## Concept master

**Map tools > Show the concept master on the terrain** lays the coordinate-locked concept art over the territory as a design reference. The art comes from `work-output/continent-region-masters`, which replaces the older regional concepts as the visual boundary authority.

- **Placement.** Each region's `contract.json` places its master. `cropRectWorld` gives continent X and Z at exactly 1 m a pixel, north (−Z) at the top, with 96 m of context around the ownership. The territory frame subtracts the scene's continent translation.
- **Boundaries.** White is the current (develop) ownership and magenta the proposed one from the contract.
- **Minimap.** The same picture is a minimap mode, alone or beside the live render.
- **Settings.** The package is found above the project automatically; **Editor Settings > Map Authoring > Concept > Masters Folder** points elsewhere, and **Opacity** sets the overlay's strength.

It is concept art, not a heightmap, and not an ownership change. Nothing edits the scene or the package, and the overlay is never saved.

## Open a territory by map

**Territories > Browse…** shows every territory as its published minimap. Click one to open its authored scene. The open territory and territories without an authored source are shown but cannot be picked.

## Low spec view

**Low spec** makes big territories lighter to work in:

- the 3D view renders at half resolution (Godot's own **View > Half Resolution**);
- placed assets, scenery and generated preview meshes more than 200 m from the camera are not drawn (**Editor Settings > Map Authoring > Performance > Far Asset Metres**);
- Godot's frame-time readout is shown, and the cursor readout adds frames per second.

The distance culling is set on the renderer directly, so no node property changes and nothing is saved. Switching it off restores each mesh's own visibility range and the view options as they were. The setting is remembered and reapplied when a territory opens.

## Time of day preview

The **Time** button in the 3D toolbar opens a small panel. Turn on **Preview time of day**, then drag the slider or press **Midnight**, **Dawn**, **Noon** or **Dusk**.

- **Same lighting as the game.** The territory's published manifest (`world.json`) supplies the noon sky, sun, ambient light and fog. `DayNightBinder` then moves them to the chosen hour, which is the game's own day/night curve.
- **Game clock.** A day is 360 game minutes, shown like the in-game clock: noon is 3:00 and midnight is 0:00.
- **Moon.** At night the moon takes over as the only directional light, as in the game. Night deliberately stays readable, because the game floors its ambient light.
- **Editor only.** The sun, moon and environment are internal, ownerless nodes, so they are never saved or baked. The preview follows you when you switch territory scenes.
- **Scenes with their own lighting.** Scenes that save their own Sun or WorldEnvironment, such as the pilot, are left alone, because that is authored lighting. The panel explains why the preview is unavailable there.
- **No manifest.** A territory without a readable manifest gets a plain clear-day fallback.

## Top-down capture

**Map tools > Capture top-down image…** saves a clean, north-up picture of the open territory. Use it for minimap work or as a tracing reference. The dialog sets:

- **Save PNG to:** by default `Pictures/Eloria map captures/<region>-top-down.png`, outside the project.
- **Resolution in px/m:** 1 px/m makes one pixel one server tile. Images are capped at 8192 px per side.
- **Include neighbour references:** off by default.
- **Only the land this territory owns:** on by default. The terrain grid is a rectangle larger than the territory, so this crops the image to the ownership polygon and makes land outside it transparent.

What the capture does:

- **Lighting.** It uses the time-of-day preview if that is on; otherwise noon from the manifest.
- **What is left out.** Fog is left out and ambient light gets the in-game minimap's floor. The ghost, cursor grid and sculpt ring are hidden during the shot.
- **Sidecar.** A `.json` file next to the PNG records the territory-local bounds, metres per pixel, orientation, height range and lighting, so any pixel maps back to authoring metres and server tiles.
- **Helpers stay out.** Marker pins, the walkability tint and path drafts are hidden during the shot.

The image shows the authoring preview as the editor renders it, not the published `world.glb`.

## Tests

The focused editor test builds a disposable 41×41 region fixture under `res://test-artifacts/map-usability/`. It checks:

- that the fast terrain probe matches the exact triangle ray test;
- the tile readout and the placement transforms;
- ghost placement, the hotkeys and keep-placing;
- snapping and undo;
- the cursor grid;
- the batch tools and prefabs;
- the sculpt brush keys, Ctrl inversion and Flatten sampling;
- the time-of-day preview, on both the fallback and Sunmane's real manifest;
- marker templates, placement, facing and the readable-marker overlay;
- the walkability grade rule tile by tile, live water, structures and decks, and Sunmane's real published grid;
- the structure and deck port against the bake's own fixtures: an arch doorway, a low lintel, a closed solid's interior, a thin edge-on wall, `Walk_` and ceiling naming, companion roots; and the background check swapping box estimates for exact results;
- the continent plan's water: claims, the frame, plan-only flooding and the read-only display;
- water judged per half-cell against the deck or ground each stands on; the published package's composer decks and solids read from a GLB (and Sunmane's real package);
- the concept master's placement by contract, its minimap cut and terrain overlay (and Sunmane's real package);
- the published minimap resample (Westhaven's frame) and the side-by-side view;
- road and river drawing, endpoint snapping, road extension at either end with width anchors kept, undo and discard; river channel properties; owned roads left alone;
- groups (Ctrl+G, selection expansion, double-click to open), Duplicate and Alt+drag copies with fresh ids;
- the selection bar's fields and buttons;
- the play-test walker: the published-grid fold and five routes checked against results from the server's own fold functions and a replica of its A*, the stage ladder against the server's choose_stage, legal server steps on the fixture, walking and running pace, refusal of cut-off goals, the reachable-area flood, portal and border-lane warnings, the nearest-free-tile redirect, and Sunmane's 792 x 792 fold;
- the contract guards: copied default spawns, the Ctrl+D redirect, shared-id detection and fixing (per section, pre-existing duplicates kept), copies dropping bindings and placement extras and following their copied asset, and prefabs placing markers with fresh ids;
- ground regions and plateaus (sizes, surfaces, turning, strokes, ownership and border refusals, the 127 limit, undo) and heightmap import (Replace and Offset, orientation, border protection, stale layers, untouched base bytes, preview and cancel, the area picked on the map);
- scatter (seeded spots, spacing, avoiding water, steep ground, roads and structures, erasing only its own copies, fresh ids, one undo step) and review notes (the sidecar, validation, pins, the filter, the dock's buttons, the package exclusion);
- the minimap's framing, pixel mapping, overlays and camera jump;
- the territory picker's thumbnails and open request;
- the library folder and model import, including `.gltf` conversion and skipping, and the admission notes;
- the low-spec view and the toolbar toggles;
- top-down framing and ownership clipping;
- that no helper node (ghost, grid, preview lights, walker, copy ghost, focus helper) is ever saved, and that group tags are.

```powershell
& 'C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64_console.exe' --editor --headless --path . --script res://tests/test_map_authoring_usability_editor.gd
```

The test waits for the editor to finish its first scan before opening the fixture, and restores every Editor Settings value it changes.

`tests/test_continent_authoring_framework.gd` also checks that a review-notes file beside a scene leaves its snapshot and sidecar files unchanged.

`tests/test_map_authoring_served_grid.gd` (headless, no editor) checks the served-grid reader and the walker on it against eloria-server's fixtures, whose byte copies are in `tests/fixtures/`: the golden `served_grid_golden.escg.gz`, its description `served_grid_golden.json`, and the two odd-sized files the description lists (5 × 7, row deltas that wrap, filter 1 gzipped and filter 0 raw). The SHA-256 of the golden file and of its description are literals in this test and in the server's `tests/test_served_grid_format.py`, so a fixture or its answers changed on one side alone fail that side; `.gitattributes` keeps their bytes exact. A fixture rebuild on the server means copying every fixture file here and updating both literals. It checks the header, the decoded codes and sample tiles; the reach from four seeds through the walker's flood and reach tint; the server's route through the fixture's corridor; codes 64, 128, 4,096 and 32,704 walking through every walk path; the 1.0 m climb (20 codes legal, 21 not) and the corner rule; the inlined flood against the plain step rule; every header and payload refusal, bytes after the gzip stream and dimensions that overflow; a tampered file; a package's `servedGrid` block (hash, unit, climb, datum, a missing file or binary, an uppercase hash) and its frame against the scene's; `load_grid`'s order through a manifest path (served, refused, missing, version 1); the live estimate's half-up quantisation; and the decode time of a 2046 × 2046 grid. Set `ELORIA_SERVED_GRID_FLOOD_TIMING=1` to time the walker's flood over that grid as well.

```powershell
& 'C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64_console.exe' --headless --path . --script res://tests/test_map_authoring_served_grid.gd
```

`tests/test_terrain_sculpt_editor.gd` now uses an isolated catalog, manifest and authoring spec under `test-artifacts/terrain-sculpt/`, checks that the edited scene is exactly its fixture before any input or save, and stops without saving otherwise.

## Not in this editor yet

The map team's answers (see [map-team-editor-contracts.md](map-team-editor-contracts.md)) set the order and the owners:

- **Polygon lakes, ponds and shorelines** come after an explicit polygon-water contract; the plan's water is shown read-only meanwhile.
- **Grass and foliage painting** needs a foliage runtime budget first; the scatter tool places ordinary assets meanwhile.
- **Named place labels** on the in-game map need a label schema, client rendering and a naming policy.
- **Lights, particles and sound emitters** have runtime support for manifest lights, but the twelve territory manifests carry no lights today, and Four Gates' `effects` are material effects on named nodes. Authoring them from scenes needs a new snapshot contract.
- **NPC walking paths** need a server patrol feature first.
- **Walkability overrides** come last, and only as areas that remove walkability; forcing ground walkable is not planned.

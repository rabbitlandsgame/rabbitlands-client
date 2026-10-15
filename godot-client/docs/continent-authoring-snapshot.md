# Continent authoring snapshot

Surface `albedoColor` and road `wornTint` arrays are saved in Godot's editor
sRGB colour space, including an unmodified linear alpha component. Production
GLB exporters convert RGB to linear `baseColorFactor` values at the output
boundary. Imported prototype GLB material factors are already linear and are
left unchanged unless an authored surface override replaces them.

The saved Godot scene is the authoring source. A headless bake writes a
deterministic snapshot which the existing continent composer consumes before
terrain partitioning, collision, chunks, manifests, and publication.

The Sunmane source scene lives at
`res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn`. Its root is
a `MapAuthoringRegion` with these saved containers:

```
SunmaneSteppe
|- Terrain                 MapAuthoringTerrainControl
|  `- Patches              MapAuthoringTerrainPatch children
|- Ground
|  `- Regions              MapAuthoringGroundRegion children
|- Roads                   MapAuthoringRegionPath children
|- Rivers                  MapAuthoringRegionPath children
|- WaterRegions            MapAuthoringRegionWater children
|- Bridges                 MapAuthoringRegionBridge children
|- AuthoredAssets          MapAuthoringAssetControl children
|- Gameplay
|  |- Spawns               MapAuthoringGameplayMarker children
|  |- Portals              MapAuthoringGameplayMarker children
|  |- Interactives         MapAuthoringGameplayMarker children
|  |- Landmarks            MapAuthoringGameplayMarker children
|  |- Harvestables         MapAuthoringGameplayMarker children
|  |- NpcMarkers           MapAuthoringGameplayMarker children
|  `- RuntimePoints        individually editable server-only positions
`- GeneratedPreview        disposable, unsaved generated children
```

The scene uses territory-local metres: +X east, +Y up, and +Z south. Object
transforms are serialized as 16-number glTF column-major matrices. IDs are
explicit saved properties and must be unique in their section. Node names are
labels and do not silently replace IDs.

## Version 1 shape

The default output is
`eloria-assets/maps/nymara-regions/sunmane_steppe/authoring/continent-authoring.json`.
Sidecar paths are relative to that JSON, stay inside its directory, and carry
SHA-256 digests. In Sunmane, `terrain.baseHeights` is the natural 2 m landform
before road or river effects. Terrain patches and shaping paths remain separate
authoring features, so moving or deleting one of those features cannot leave
its old terrain effect behind.

An imported territory may instead keep its certified, already graded terrain
as the explicit saved base. Its imported roads have **Shape terrain** off and
follow that existing ground. Moving, widening, or deleting one of those roads
does not automatically heal or move the terrain beneath it. Turn **Shape
terrain** on to make that road's curve heights grade the ground, or add saved
terrain patches for deliberate height edits. New roads default to **Shape
terrain** on. This Inspector control writes the existing
`properties.terrainConform` value; it is not a second saved terrain mode.

Region path **Snapshot mode** defaults to **Baked curve**, which samples the
Bezier curve at **Snapshot spacing** intervals. Choose **Control polygon** for
a path whose saved control positions and per-point widths must be exported as
straight segments without resampling the full curve. Moving an interior
control then leaves the other exported stations in place. Bezier handles are
ignored in this mode; the Inspector warns when they are present. Closed paths
include a final segment back to the first control.

An imported terrain may also provide `terrain.baseColors`, a full-grid
RGBA8-sRGB sidecar with exactly `width * height * 4` bytes. The authoring
preview and production terrain export use those vertex colours under the
normal base material; Texture Regions remain independent overlays. Scenes
without the optional sidecar retain the procedural terrain-colour behavior.

Elliptical plan water uses saved `WaterRegions` controls. Moving a control
changes its centre and water level, while `radii` changes its horizontal
domain. Rotation and scale fail the bake because the production ellipse has no
lossless rotated or scaled representation. The imported plan depth is shown as
reference metadata only: authored regions keep their saved resolved ground,
so actual depth is water level minus that ground. Edit the terrain itself to
change the bed. `replacements.planFeatureIds` is the persistent authority
registry; deleting or disabling a claimed water control removes the feature
and never revives the retired procedural lake or river. Feature claims must be
globally unique across all authored territory snapshots.

```json
{
  "schema": "eloria-continent-authoring-v1",
  "regionId": "sunmane_steppe",
  "coordinateSpace": "territory-local",
  "axes": {"x": "east", "y": "up", "z": "south"},
  "continentTranslation": [1200.0, 0.0, 720.0],
  "server": {
    "metresPerTile": 1.0,
    "origin": [194, 292],
    "cells": [792, 792],
    "collisionOriginMetres": [-194.0, 292.0]
  },
  "sources": {
    "scene": {
      "path": "godot-client/world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn",
      "sha256": "<64 lowercase hex>"
    },
    "runtimeBindingSeed": {
      "path": "godot-client/world_authoring/regions/sunmane_steppe/runtime-bindings.seed.json",
      "sha256": "<64 lowercase hex>"
    },
    "dependencies": [
      {"path": "godot-client/world_authoring/regions/sunmane_steppe/base-heights.f32le", "sha256": "<64 lowercase hex>"}
    ]
  },
  "authority": {
    "terrain": true,
    "water": true,
    "paths": true,
    "objects": true,
    "gameplay": true
  },
  "replacements": {
    "routeIds": ["sunmane_steppe-road-to-mirrorhold"],
    "planFeatureIds": []
  },
  "terrain": {
    "origin": [-194.0, -500.0],
    "cellMetres": 2.0,
    "previewUvMetresInverse": 0.24,
    "width": 397,
    "height": 397,
    "baseHeights": {
      "path": "base-heights.f32le",
      "sha256": "<64 lowercase hex>",
      "encoding": "float32-le"
    },
	"resolvedHeights": {
	  "path": "resolved-heights.f32le",
	  "sha256": "<64 lowercase hex>",
	  "encoding": "float32-le",
	  "includes": ["patches", "road-earthworks", "river-cuts"]
	},
    "baseColors": {
      "path": "base-colors.rgba8",
      "sha256": "<64 lowercase hex>",
      "encoding": "rgba8-srgb"
    },
    "baseSurface": {"preset": "Grass", "rotationDegrees": 0.0},
    "patches": []
  },
  "groundRegions": [],
  "waterRegions": [
    {
      "id": "mirror-lake",
      "shape": "ellipse",
      "replacesPlanFeatureId": "mirror_lake",
      "name": "Mirror Lake",
      "center": [53.6788, 181.4641],
      "level": 80.0,
      "radii": [48.0, 33.0],
      "depth": 4.0
    }
  ],
  "paths": [
    {
      "id": "road-to-mirrorhold",
      "kind": "road",
      "routingRole": "required",
      "replacesRouteId": "sunmane_steppe-road-to-mirrorhold",
      "replacesPlanFeatureId": null,
      "closed": false,
      "surface": {"preset": "Worn earth", "rotationDegrees": 0.0},
      "points": [
        {"position": [-2.0, 26.4, 1.0], "width": 8.0},
        {"position": [18.0, 26.1, -12.0], "width": 8.0}
      ],
      "properties": {}
    }
  ],
  "bridges": [],
  "objects": [
    {
      "id": "sunmane-south-gate",
      "nodeName": "Gate_South",
      "assetId": "continent:sunmane-gate",
      "scenePath": "res://assets/world/continent/sunmane-gate.glb",
      "sourceNode": "",
	  "bakedSource": {
		"path": "godot-client/assets/world/continent/sunmane-gate.glb",
		"sha256": "<64 lowercase hex>",
		"sourceNode": "."
	  },
      "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 14, 25, -8, 1],
      "collisionRole": "solid",
	  "materialOverrides": [],
      "metadata": {}
    }
  ],
  "gameplay": {
    "spawnPoints": [],
    "portals": [],
    "interactives": [],
    "landmarks": [],
    "harvestables": [],
    "npcMarkers": [],
    "ambientPopulation": [],
    "runtimePoints": [],
    "runtimeBindings": [
      {
        "id": "npcs.txt:118:Caravan Doctor Nesrin@200:80",
        "source": {"path": "config/eloria/npcs.txt", "line": 118,
          "recordId": "Caravan Doctor Nesrin", "oldTile": [200, 80]},
        "marker": {"section": "runtimePoints", "id": "runtime-npc-caravan-doctor-nesrin"},
		"targetOffset": [0, 0, 0],
        "role": "npc",
        "roads": "marker",
        "provenance": {"sourceReportSha256": "<64 lowercase hex>",
          "sourceProfileSha256": "<64 lowercase hex>"}
      }
    ]
  },
  "seams": {
    "ownershipPolygonSha256": "<64 lowercase hex>",
    "anchors": []
  }
}
```

Runtime bindings qualify a marker by both section and ID because an interactive
and a portal may deliberately share an ID. `targetOffset` stores the certified
territory-local horizontal metres `[dx, 0, dz]` from that marker to this specific server
record. Moving a shared marker translates every bound endpoint while preserving
distinct door, return, and other alias offsets. RuntimePoint bindings use zero.
The reviewed seed is saved on the region root and hash-bound both explicitly
and in `sources.dependencies`, so additions or identity changes require a
reviewed seed update rather than a nearest-point guess.

Every path has an explicit `routingRole` (`required` or `decorative`). A
composer route is suppressed only when `replacesRouteId` names that exact
route. A river overrides a planned water feature only when
`replacesPlanFeatureId` names it. Empty values serialize as JSON `null`; the
composer never guesses replacements from proximity.

Path point `width` values are the full rendered width in metres. The Godot
preview uses half of that value on each side of the curve. Consumers of older
composer APIs that accept a radius or half-width must divide this value by two.

`replacements` is saved on the region root independently of the current path
nodes. Deleting a path therefore cannot resurrect its old procedural route or
water feature. Every non-null path replacement must occur in the matching
registry. If a required composer route remains registered without exactly one
authored replacement path, the build fails and names the missing route. A
registered optional route or water feature may deliberately have no path.

Supported local surfaces serialize as a preset, rotation, and explicit PBR
texture references when needed. Ground regions also serialize shape,
transform, size, blend, opacity, and priority. A custom shader without a
production material mapping is a bake error that names the authored node.
Terrain and ground-region mesh UVs use territory-local X/Z metres multiplied
by `terrain.previewUvMetresInverse`; the saved surface UV scale, offset, and
rotation are applied afterward. Named region textures use this UV projection
in both preview and production. Custom triplanar materials are rejected because
the production exporter cannot preserve that projection. Color arrays keep the
Godot Inspector's sRGB channel values; glTF writers convert RGB to linear once,
while alpha remains unchanged.

Objects keep their original `scenePath` and `sourceNode` as editor provenance.
Production consumes the hash-bound `bakedSource`. A whole-root GLB uses
`sourceNode: "."`; picker sources such as `.tscn` templates are converted once
per unique source/subtree to a reusable GLB in the snapshot's `prototypes`
directory. Object `materialOverrides` contain `meshNodePath`, `surfaceIndex`,
and `surface`. Duplicate targets, negative indices, and edits inside the saved
`Content` instance are bake errors; move the wrapper or use its supported
override resources instead.

Gameplay marker transforms are the positional source of truth. The bake keeps
the marker's stable ID and link fields, derives `position` and `serverTile`, and
merges its `extras` fields without allowing extras to replace identity or
position fields.

For named exterior road/ferry portals, distinguish the saved marker from the
published crossing. The source snapshot remains unchanged: its `serverTile`
is the projection of the editable marker, and its `destinationTile` is retained
from extras. Final world manifests preserve the marker's exact local XYZ,
ID, label, name, type, destination map and other authored fields, but publish
`serverTile` and `destinationTile` from the certified crossing. A walk departs
on a legal settled lane and arrives at that same physical cell in the other
map's frame; a ferry uses the destination quay's explicit arrival. Marker XYZ
need not project to that published trigger tile.

Runtime connection endpoint XYZ stays at the derived crossing, independently
of marker XYZ, for navigation fallback and preloading. Packed crossing lanes
remain the normal walking route authority. Published-data editor playtests
use the final manifest `serverTile`, so they indicate the actual trigger.
Export rejects ambiguous identities, incompatible frames and invalid source
projections; collision, ownership, legal-step and reachability checks still
decide which crossing lanes can be published. Moving a marker does not reshape
terrain or make its projected tile a legal border crossing.

Markers with `follow_asset_id` store an asset-local offset. Their exported
absolute position is derived from the current object transform during every
bake, and the record includes both `assetId` and the production node link.

Seam anchors use `{id, anchor: [x, y, z], ...}` records. The exporter sorts
them by stable ID before writing JSON, so scene array order does not affect the
snapshot.

## Headless bake

Normal builds refresh the snapshot with:

```text
godot --headless --path <repo>/godot-client --script res://src/dev/map_authoring_region/region_bake_cli.gd -- --scene res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn --output <repo>/eloria-assets/maps/nymara-regions/sunmane_steppe/authoring/continent-authoring.json
```

Exit code 0 means the JSON and both height sidecars were written. Validation
failures return 1; invalid arguments or a scene load failure return 2. A normal
build locates Godot from its explicit `--godot` option, then `ELORIA_GODOT`, a
known checkout binary, and finally `PATH`. If the saved scene is newer than its
snapshot and no Godot executable is available, the build fails instead of
using stale authoring data.

`seams.ownershipPolygonSha256` is SHA-256 over the UTF-8 bytes of compact
canonical JSON for the ordered `World.polygons[regionId]` point array, using
Python `json.dumps(points, separators=(",", ":"), ensure_ascii=False)`.

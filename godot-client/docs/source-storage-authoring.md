# Source storage contracts

The region spec's `server` object owns the logical storage rectangle. Its saved
scene and normal snapshot must agree. Storage growth does not change logical
tile numbers or the tile-to-world frame.

```json
{
  "origin": [242, 182],
  "cells": [486, 486],
  "serverStorageVersion": 1,
  "serverTileMin": [-50, 0],
  "collisionOriginMetres": [-292, 182]
}
```

This is a schema example, not an activated source change. With minimum `(mx,my)`,
valid logical tiles occupy `[mx,mx+width) × [my,my+height)`. Array column and row
are `(x-mx,y-my)`. `storage_bounds.StorageBounds` centralizes these conversions,
containment and conservative union. Width/height may be rectangular and must
be in `1..2048`; publisher-specific square/six-cell restrictions remain separate.
Logical minima and inclusive maxima must fit signed 32-bit coordinates.

Omitting both version/minimum fields keeps historical zero-minimum behavior.
Supplying either requires both; version must be `1`. Python source documents
require actual integers, excluding booleans. Godot JSON permits exactly integral
numeric values because its JSON reader stores numbers as doubles. Fractional,
nonfinite, malformed and unsupported values fail rather than falling back.

Saved scenes expose `server_storage_version` and `server_tile_min`. Scene version
`0` means omitted historical metadata and is valid only with a zero minimum.
Scene/spec omitted and explicit zero minima compare semantically. A nonzero
saved minimum cannot be discarded when the version control is left at zero.
Two different storage rectangles fail scene/spec comparison even if both contain
the historical baseline.

The current authoring frame supports zero local origin, one metre tiles and
inverted server Y. Physical collision origin is validated as
`[minX-serverOriginX, serverOriginY-minY]`. Explicit unsupported `localOrigin`,
`metresPerTile` or `invertServerY` fails with a diagnostic; changing storage never
changes those transforms. Optional source `walkingHeight` is validated as finite
and copied unchanged into new snapshots. It is not inferred or recomputed here.
Current production ownership/spec sources do not provide a frozen walkingHeight;
complete runtime-frame publication still needs verified provenance for it.

Selected ownership keeps its `coordinateFrame` exact and its `baselineStorage`
immutable. Live storage must contain the full baseline rectangle. The ownership
source's historical `serverTileMin` is not a new live versioned declaration;
its existing bytes remain untouched.

Normal export adds `sources.authoringSpec = {path, sha256}` when a registered
spec exists. Paths are checkout-relative and reject traversal/link indirection.
The exporter captures source bytes before exporting and checks the source and
scene contract again immediately before writing the snapshot. Captured editor
entries reject changed spec bytes before editing. Python loading checks the
binding, semantic frame/storage equality and current contract hash, and includes
the spec in composition dependencies. Explicit versioned snapshots require this
binding; older implicit-zero snapshots retain their existing compatibility path.

This foundation does not activate ownership or expand production storage. World
composition, EWCG/ELM folding, publisher finalization and runtime transport still
require their separately reviewed min-aware consumer work.

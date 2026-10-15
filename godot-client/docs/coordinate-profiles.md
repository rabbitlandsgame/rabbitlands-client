# Coordinate profile codec prerequisite (version 1)

These pure helpers reserve S→C `ELORIA_COORDINATE_CONTEXT=208`, C→S
`ELORIA_MAP_COMMAND=204`, and capability `map_storage_coords_v1`. The capability
is **not advertised**, and the extensions are not connected to normal dispatch,
login, Session, world state, or movement. Existing packets retain their bytes.

`CoordinateProfile` (Python) and `coordinate_profile.gd` (Godot) hold immutable
snapshots independent of a session. Exports are defensive copies. Typed creation
requires integer version/minima/dimensions; the explicit `from_registry` boundary
also accepts exactly integral JSON numbers, including `1.0`, because Godot JSON
uses binary64. Both reject bools, fractions, nonfinite numbers, and out-of-range
values. Storage version is exactly 1, dimensions are 1..2048, and both minima and
inclusive logical maxima fit signed int32. Conversion is `wire=logical-min` and
its inverse, with strict half-open bounds and no wrapping or clamping. Zero-min
0, 1023, 1024, and 2047 remain unsigned and unchanged.

## Canonical profile record

All multibyte values are little-endian. Mandatory order:

| Field | Encoding |
| --- | --- |
| Domain and encoding version | 25 ASCII bytes `ELORIA-COORDINATE-PROFILE`, byte 0, byte 1 |
| Canonical map ID | u8 byte length (1..255), exact UTF-8 bytes, no NUL |
| Storage version | u8, exactly 1 |
| Logical minimum | two signed i32: x, y |
| Dimensions | two u16: width, height |
| Frame flags | u8: bit 0 `invertServerY`, bit 1 `walkingHeight` present; other bits zero |
| Frame | nine IEEE754 binary64: `serverOrigin[x,y]`, `origin[x,y,z]`, `metresPerTile`, `continentTranslation[x,y,z]` |
| Optional walking height | one binary64, only when flag bit 1 is set |
| Collision digest | raw SHA256, 32 bytes |
| Coordinate revision | SHA256 of every preceding byte, raw 32 bytes |

The canonical hash input is 146+map-ID-byte-length bytes (154 with walking
height); the complete transmitted record is 178+length (186 with walking height).
Map IDs preserve case, punctuation and Unicode. Callers resolve legacy aliases
to the authoritative registry identity before construction; helpers do not
rename maps or normalize Unicode. Expected-registry association checks that exact
identity and all canonical fields, not merely a supplied revision string.

Every frame number must be finite; scale must be positive. Negative zero is
normalized to positive zero when constructing a profile. A raw record containing
negative-zero bits is noncanonical and rejected. Source frame meanings remain
unchanged. The caller supplies resolved authoritative values (including existing
defaults); no transform defaults are invented by the codec. `walkingHeight` is
included only when present in the authoritative coordinate transform; absence is
distinct from a numeric zero. No JSON serialization participates in hashing.

`collisionSha256` means SHA256 of the entire **uncompressed ELM payload**, including
its header and cells, before runtime blockers, masks, erosion, or floor overrides.
A gzip wrapper contributes no bytes. The publisher and server loader must later
verify this provenance and grid dimensions against the actual asset. This phase
validates the supplied digest's format and its binding into the revision only;
it does not read or publish collision assets. This is a coordinate revision, not
a change to terrainRevision or existing package-digest behavior.

The descriptor has exactly `mapId`, `serverStorageVersion`, `serverTileMin`,
`serverCells` (a rectangular pair within this new API), `frame`, `collisionSha256`,
and `coordinateRevision`. Frame has exactly the five mandatory named fields in
the table plus optional `walkingHeight`. Digests are lowercase 64-hex strings.
This API does not change the existing scalar `serverCells` representation used
elsewhere. Unknown/missing fields, revision mismatch, unknown versions, truncated
or trailing bytes, and an expected-registry mismatch fail closed.

## Extension payloads

Existing command/u16-length framing is unchanged. Context payloads are at most
32,768 bytes. They begin with u8 version 1 and u8 operation:

- `0 accepted`: exactly these two bytes.
- `1 define`: u16 profile count (1..64), then each u16 record length and complete
  profile record.
- `2 activate`: the same profile sequence, followed by nonzero u32 epoch,
  length-prefixed map ID, u16 handle count (1..64), then u16 handle and
  length-prefixed map ID for each entry. Every profile must appear exactly once
  in the handle table; handle 0 must identify the active map. Duplicate handles,
  duplicate maps, missing definitions, or unknown registry profiles fail.

Every define/activate decode synchronously compares all records with the supplied
expected registry before returning success. These codecs have no mutable profile
table or epoch activation state; decoding `accepted` does not negotiate a session.

Map commands are u8 version 1, nonzero u32 epoch, u8 inner command, then its body.
Only MOVE_TO(1), RUN_TO(6), and FIRE_MISSILE_AT_OBJECT(51) accept an exact four-byte body of two
u16 storage coordinates in 0..2047. ELORIA_MAGIC_REQUEST(202) accepts 1..4096 bytes
of UTF-8 JSON object; point values in that JSON remain logical, potentially signed.
The common lexical gate rejects non-standard constants, nonfinite numbers,
invalid number spelling, trailing commas, unescaped controls, and nesting beyond
64 containers, before native structural parsing. Magic action/field semantics are
not validated here. The largest envelope is 4102 bytes. Other commands, including
nested 204 envelopes, are rejected. Epoch freshness is deliberately a later
session-boundary responsibility.

## Validation and remaining integration

Both checkouts carry identical `tests/fixtures/coordinate-profile-v1.json` with
canonical bytes, records, contexts, commands, and invalid cases. Python tests run
independently with `python -m pytest tests/test_coordinate_profiles.py`; client
tests run with Godot `--headless --path godot-client --script
res://tests/test_coordinate_profiles.gd`. The task QA generator
`make-coordinate-goldens.py --check` reproduces and compares both fixture copies.
Test processes must use the task's four-CPU wrapper.

Follow-on reviewed phases must implement publisher/registry and collision binding;
narrow pre-login negotiation and legacy login/transition guards; synchronous
expected-profile setup; ordered activation before any map coordinates; complete
map-aware conversion of every coordinate family; rejection of unknown adjacent
handles; stale epoch rejection and delayed-producer guards; reconnect reset; and
signed logical JSON/render/editor consumers. Capability advertisement and negative
map activation must wait until that complete path is tested. No saved coordinate,
stable ID, source transform, live portal XYZ, or data artifact changes in this phase.

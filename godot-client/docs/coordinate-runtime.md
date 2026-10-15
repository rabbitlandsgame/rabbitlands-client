# Client coordinate runtime (inactive transport)

`Network` owns one synchronous `coordinate_context.gd` instance. Normal login
and `CLIENT_CAPABILITIES` still do not request `map_storage_coords_v1`. The only
selection seam is programmatic `Network.coordinates.prepare_selection()` followed
by the accepted server context packet. Calling it does not send a capability.

## Expected registry contract

Main reads the existing lightweight `res://data/maps/registry.json` once, before
connecting. The optional top-level fields are:

- `coordinateProfiles`: canonical map ID to complete descriptor specified in
  `coordinate-profiles.md`. `Profile.from_registry` checks every field and hashes
  canonical binary64 frame/bounds/collision bytes. Descriptors are frozen copies.
- `coordinateMapNames`: exact server name to canonical map ID. Publishers include
  each `MapDefinition.client_name` and canonical self name. Self names are also
  installed automatically; conflicting aliases and unknown targets fail. No
  basename, case, path, renderer alias or filename guessing authenticates a name.

`Network.configure_coordinate_profiles(catalog, names, registry_maps)` returns
`{ok}` or `{ok:false,error}`. Failure blocks login. Registry map transforms that
declare a nonzero `serverTileMin` must have a matching expected descriptor; the
client never synthesizes profiles from a `Vector3`, an asynchronous scene load or
the advisory map digest. An absent optional catalog retains ordinary legacy mode.
Locally known offset profiles cannot commit a legacy CHANGE_MAP.

The catalog currently needs publisher output before real use. Runtime private
tutorial IDs need an explicitly verified template-derived catalog/name contract;
there is no implicit template alias or guessed identity frame. Unknown capable
profiles fail before row reduction.

## Packet boundary and state

AppState checks context ordering before its native actor-command shortcut.
`accepted` requires a prior explicit request. `define` verifies all remote
profiles against the expected catalog and cannot replace an immutable profile.
`activate` must use exactly the next nonzero epoch and prepares a complete
profile/handle table. The very next packet must be CHANGE_MAP with an exact
trusted name for that canonical map. Only that packet installs epoch/map/handles,
before any existing `state_changed` reducer signals. Pending activation blocks
point intents. Resync uses `define`, leaving map, handles and epoch unchanged.

Decoded events pass through one transactional conversion before storage or
signals: actor spawns use their own strict handle mapping; bags, clickable/runtime
objects, teleporters/teleport events, fire/sound and ground missiles use the
committed active profile. Markers, active navigation and party rows use their
explicit trusted names and require a preceding profile definition. Offline empty
party rows and inactive navigation sentinels are untouched. One invalid row
rejects its entire list. Carried actors keep their canonical map and logical point;
handle reuse never converts them again. Actor-command deltas remain logical.

Recall/tutorial JSON stays logical and requires defined profiles for its explicit
map names. A burst with supplied `map` or `coordinateRevision` must match the
committed active profile; mismatches are fatal before emission. Missing burst
association fields currently bind to that committed context, as allowed by the
design's compatibility option. Server producers still must cancel delayed stale
events, including same-map events. No client point conversion changes JSON IDs,
vitals, radii, distances, power or opaque recall keys.

Admin logical JSON may use the verified local expected catalog without a binary
peer definition. Supplied `serverTileMin`, `serverCells`, `width` and `height`
must match. Known-map positional rows must contain integral in-bounds points.
Unknown maps or `coordinatesSupported:false` show an unsupported view, discard
positional rows and disable coordinate submissions. The admin UI rejects delayed
responses for another selection and accepts signed minima in its map canvas,
spinboxes and group location checks. Admin text commands remain logical.

Fatal context errors disable reconnect and reset the session. Receive-buffer
draining watches a connection generation; synchronous disconnect cannot leave a
later packet in the same burst applied. Disconnect/reconnect clears received
profiles, handles, pending activation, epoch, buffered bytes, magic selections and
route intents, while retaining the immutable local expected catalog.

## Outbound intents and signed consumers

MOVE/RUN/ground shots convert within active bounds before raw unsigned packing and
use command 204. All selected magic requests use the same epoch envelope, with
signed logical JSON unchanged. No command is sent before committed activation.
Pending magic captures connection generation/map/epoch and is invalidated before
the map signal; invalidation never emits a cancel into the destination context.

Road continuations capture that token. Only the immediately expected next map can
adopt a new epoch; same-map teleport, unrelated map, rapid A→B→A and reconnect
invalidate the route. KILL_ALL_ACTORS cancels routes. Main waits for the local actor
DTO to belong to the committed map before continuing a carried road click.

Ground aim and console/admin selection use explicit presence instead of `(-1,-1)`.
Audio uses a separate previous-tile flag, retaining first-sighting silence.
Exterior click bounds subtract `serverTileMin` solely for containment checks;
world/tile transforms and persisted logical points are never rebased.

## Focused verification

`tests/test_coordinate_runtime.gd` has 160 assertions covering the context,
conversion families, real AppState map-signal ordering, drain-stop after fatal
pair/handle failure, atomic rejected chunks, carried actors, command envelopes,
stale magic/road tokens, signed consumers, admin selection switches and audio.
Its capture helper overrides only sending; it makes no network connection.

Existing suites passed: coordinate profiles (1,965 assertions), exterior walking
continuations, console commands and invasion assistant. The invasion suite uses
isolated QA APPDATA so preference tests never modify actual user settings.
The existing protocol suite still reports exactly its three documented baseline
failures: two capability inventory assertions and Four Gates walking height.
No baseline expectations were changed. Native reducer source keeps signed int64
delta arithmetic; a native extension build/run is not claimed by this slice.

All tests ran with the four-core limiter and exact process-tree timeouts, without
full import, installation, active-map data generation or negotiation activation.

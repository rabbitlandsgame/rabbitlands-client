# Migration risk register

| Risk | Impact | Mitigation / evidence gate |
|---|---|---|
| Login payload varies by legacy/version flow | Authentication failure | capture and compare legacy frame before verification claim |
| Shared numeric IDs differ by direction | Wrong reducer/action | direction-specific enums and fixtures |
| TCP fragmentation/coalescing | corruption/desync | buffered decoder tests |
| Enhanced actor optional tail | misaligned actor parsing | fixtures from server serializers and legacy decoder |
| Axis/scale mismatch | movement/map drift | one coordinate adapter with map landmarks |
| GLB skeleton variation | joint artifacts | native import, per-model profiles, validation scene |
| Root motion fights replication | actor drift | animation root motion disabled for replicated transform |
| UI parity scope | schedule/quality risk | traceability matrix and vertical-slice priorities |
| Private server integration unavailable in CI | false confidence | opt-in local integration suite; never mock acceptance |
| Asset size/import time | build instability | registries, import cache, LOD and validation reports |

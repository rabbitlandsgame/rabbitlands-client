extends RefCounted
## Shared producer/consumer generation for native scenes and derived CPU data.
## Bump when loader changes alter geometry, collision, hierarchy or batching.
const VERSION := 2 # Ground roads use external fields and Terrain physics; bridges stay native.

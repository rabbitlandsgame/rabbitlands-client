extends RefCounted
## Shared producer/consumer generation for native scenes and derived CPU data.
## Bump when loader changes alter geometry, collision, hierarchy or batching.
## 4 - shared scenery images preserve original policies and full mip chains.
## 5 - continent/gauntlet static batches split into size-class cells with centred
##     frames (WD-C2); shared prototypes carry generated LODs (WD-C5).
const VERSION := 5 # Size-class batch cells (WD-C2) and generated prototype LODs (WD-C5).

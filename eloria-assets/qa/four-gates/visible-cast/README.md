# Four Gates visible-cast repair

This pass targets the two NPCs actually spawned in the reported Four Gates
scene rather than relying on unspawned profession actors.

| Server name | Actor type | Client model | Budget |
| --- | ---: | --- | ---: |
| Toran | 307 | `luminous_official_m` | 2,946 vertices / 5,716 faces |
| Nima Vey | 309 | `luminous_merchant_m` | 2,564 vertices / 4,868 faces |

Toran now has a formal robe, cape, mantle, belt, clasps, jewelry and formal
head silhouette. Nima has a merchant coat, ledger, belt, buckle, pouches and
asymmetric bags. Both use dedicated lowered-arm idle animations. Their 1024px
atlases reserve broad regions for ivory cloth, teal panels, antique-gold trim
and leather rather than using the previous nearly uniform cyan material.

The PNG images here are topology diagnostics. Acceptance still requires a
fresh in-client capture of actor types 307 and 309 generated from the same
commit.

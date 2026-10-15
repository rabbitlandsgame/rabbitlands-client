# The First Commission

**Trading and marketplace storyboard · Proposal · Solo · 30–40 minutes · Ten core frames**

[Illustrated storyboard](storyboard.html) · [Collection](../README.md) · [Shared contract](../design-contract.md)

The repaired workshop has its first outside customer. At **Lantern Exchange**, **Clerk Venn** gives the player a modest practice budget and a request for road supplies. The player buys what is missing, exchanges a surplus bundle, sells the remainder and completes a delivery. The order board visibly changes from incomplete to packed to dispatched.

**Venn:** “Count the goods, count the coins, and make sure both sides mean the same exchange.”

This is a clearly labeled rehearsal economy. **Pella, practice trader**, is a scripted session-backed partner, not a pretend human player. Marketplace counterparties always exist in the private exercise. Real supply, demand, social trust and earning a profit are not guaranteed by completing it.

## Access and four-gate map

Offer at the first marketplace visit or after the workshop. Borrow a separate pack, storage and coin balance. The practice budget is calculated from authored merchant prices and private listings, enough for the cheapest valid route plus a disclosed recovery allowance. No funds, listings, notifications, mail, items or proceeds may touch public services.

Propose **112 × 112 tiles**. Ledger Court (56,56) holds Venn, Storage and the order board. North (56,87) is Merchant Row, East (87,56) the Trading Awning, South (56,25) the Exchange Desk and West (25,56) Dispatch.

| Gate | Composition | Purpose |
| --- | --- | --- |
| North · Merchant Row | One clearly stocked vendor and readable price labels | NPC buy/sell, quantity and capacity |
| East · Trading Awning | Practice partner beside storage, nearby open ground | Reciprocal trade, review and cancellation |
| South · Exchange Desk | Private listings, own-listing and escrow views | Unit prices, buy, list, cancel and collect |
| West · Dispatch | Revised order and departure cart | Independent procurement and reconciliation |

The map is a compact route through services, not four UI lectures. Each stop produces goods needed for the visible commission.

## Ten storyboard frames

### 01 · A budget with a purpose — 3 minutes

**Picture:** The commission board shows two missing material bundles and one owned surplus bundle beside the practice coin count.

**Voice:** “Bring the order home with coins left to carry it.”

**Play:** Accept practice funds through ordinary inventory receipt, inspect the order's exact item names/quantities and compare them with the pack and Storage. Find the first material already owned. Leave a bulky irrelevant bundle in Storage before shopping.

**Learn:** Procurement begins with stock, total costs and room for the result. Owned material need not be bought again.

**Evidence:** Accurate stock state, actual transfer and order shortfall calculation. No credit for purchasing redundant items.

**Recovery / observe:** Budget feedback updates from real transactions, not a scripted progress counter. If a player spends poorly later, offer a labeled practice reset of the remaining order. Can the tester identify what is truly missing?

### 02 · The merchant's price — 3 minutes

**Picture:** North's vendor offers the required material beside two optional goods. The quantity selector and coin balance remain visible.

**Voice:** “The price belongs to this amount. Check it before you buy.”

**Play:** Use the real merchant window to buy a small required quantity. Inspect the total inventory increase and actual gold deduction. Sell an eligible surplus item through the merchant's normal sell path and compare its offered price with the purchase price, without implying they are equal.

**Learn:** Buying and selling are different transactions; unit price, selected quantity and total spend must agree.

**Evidence:** Completed merchant purchase and sale, exact item/coin deltas and updated remaining order. Requests and window openings are insufficient.

**Recovery / observe:** Test insufficient funds and full capacity with a small reversible practice setup. Verify the vendor actually stocks and accepts the chosen items; do not rely on a global item list as proof of merchant availability.

### 03 · An exchange needs two people — 3 minutes

**Picture:** Pella waits beneath the East awning. The native trade icon is visible and both actors fit comfortably on screen.

**Voice:** “Ask me to trade. Then wait for the answer.”

**Play:** Approach Pella and request trade through the real actor interaction. Observe the reciprocal acceptance before the trade window opens. In a short second attempt, receive Pella's request and accept it normally. The current server requires both players on the same map within four tiles.

**Learn:** A trade request is an invitation, not a completed transfer. Both participants and distance matter.

**Evidence:** Real reciprocal request/accept state and an open session connecting the intended actor IDs. Pella uses the ordinary session protocol.

**Recovery / observe:** Expired request or moving out of range gets a clear retry. Do not auto-accept on the player's behalf. Record accidental targeting of the merchant or another nearby actor.

### 04 · Read both sides twice — 4 minutes

**Picture:** Both offer panes show a material bundle and coins. Pella's practice label remains visible above the panel.

**Voice:** “Look at both offers. Ready is not finished.”

**Play:** Offer a precise quantity, inspect Pella's item/quantity and use the native first acceptance. Pella openly revises a quantity as a teaching beat; observe both accept states reset. Review the corrected offers, complete both acceptance stages and inspect the resulting goods and coins.

**Learn:** Trade has a two-stage mutual acceptance, and changed offers invalidate earlier acceptance. Inspect the actual offered item, including instance details when available.

**Evidence:** Offer mutation, acceptance reset and one atomic completed exchange. The script never confirms for the player.

**Recovery / observe:** Unexpected failure leaves goods owned or restored correctly. If the player catches the revised quantity immediately, accept that and continue. Do not disguise the scripted change as a real player's deception.

### 05 · Leaving an unfinished deal — 3 minutes

**Picture:** The same awning now has a clearly marked exit space and Storage next to the participants.

**Voice:** “If it is not the trade you want, stop it.”

**Play:** Begin a second small offer and reject it before final completion. Verify offered goods return. Then complete a valid trade using the native storage destination when both participants are actually beside Storage. Observe the received item in its chosen destination.

**Learn:** Cancellation is available before commitment; storage routing has proximity and destination rules.

**Evidence:** No net transfer on reject, followed by one completed correctly routed trade. Do not label an offered item as lost just because it temporarily leaves the pack display.

**Recovery / observe:** Test departure from range and disconnect as engineering cases, not compulsory novice tricks. A full inventory must produce recovery rather than silent disappearance. Ask the tester to locate the received item themselves.

### 06 · A listing is a quantity at a price — 4 minutes

**Picture:** South's exchange lists two material stacks with different quantities and unit prices. Their totals differ visibly in the guide's proposed calculation aid.

**Voice:** “Cheap each can still mean too much altogether.”

**Play:** Browse actual private listings, compare quantities and unit prices, then buy a small required listing through the current marketplace Buy control. This control currently purchases the entire selected listing. For a partial quantity use the supported `#auction buy <listing_id> <quantity>` command after inspecting the listing ID.

**Learn:** Marketplace Buy All and a partial purchase are different requests; refresh when a listing changes.

**Evidence:** One real escrow purchase, correct total spend and exact quantity received. At least one guided comparison must make the distinction useful.

**Recovery / observe:** Keep every introductory whole listing affordable. Native total-cost confirmation and quantity UI are proposed improvements, not existing controls. Never depict a confirmation dialog the current client does not show.

### 07 · Put the surplus to work — 4 minutes

**Picture:** A surplus stack disappears from the pack into the player's own listings view; it has a persistent listing ID.

**Voice:** “Listed goods are held for the buyer. They are not still in your pack.”

**Play:** Verify the current inventory slot and list a small surplus with `#auction sell <inventory_slot> <quantity> <unit_price>`. Inspect the own-listings view and authoritative expiration. Cancel one listing, then inspect return escrow and collect it. A second valid listing remains for the next scene.

**Learn:** Listing reserves actual goods; cancel moves them to return escrow rather than directly back into inventory.

**Evidence:** Exact listing creation, removal from ownership, cancellation and collected return. Reordering the pack requires rechecking the slot before listing.

**Recovery / observe:** There is no assumed native selling form. The source audit found help saying seven days while creation defaults to 365; reconcile that text before shipping. The lesson uses the listing's actual expiry, not the stale help value.

### 08 · A sale is not money in the pack yet — 3 minutes

**Picture:** Pella purchases the remaining private listing. The escrow balance rises while the inventory coin count initially stays unchanged.

**Voice:** “The exchange has your proceeds. Collect what you can carry.”

**Play:** Wait for the scripted partner's actual marketplace purchase, open the own/escrow view and collect proceeds. Compare pending and collected balances. In an optional short retry, leave insufficient capacity for a return item, observe it remain pending, free space and collect again.

**Learn:** A completed sale, available proceeds and collected inventory are distinct states. Collection can be limited by capacity.

**Evidence:** Counterparty purchase transaction, seller proceeds, one collection and cleared corresponding escrow balance. No reward granted by an arbitrary scene timer.

**Recovery / observe:** A dropped partner session must reconnect and reconcile the sale ID before retrying. Do not buy the listing twice. The player should find their money without assuming a notification itself transferred it.

### 09 · Complete the commission — 6 minutes

**Picture:** West's customer changes one material and quantity. Merchant and marketplace options remain accessible; some stock is already in Storage.

**Voice:** “This is the final order. Choose where the missing goods should come from.”

**Play:** Reconcile stock, compare a merchant offer with at least two private listings, buy only what is missing, collect any pending proceeds and deliver the exact goods. Change listing stack sizes and stored stock from the guided example. An affordable route is guaranteed; a profit is not required.

**Learn:** Combine stock checking, total prices, source choice and escrow into an independent plan.

**Evidence:** Correct delivery, nonnegative practice budget and transactions consistent with actual shortfalls. Accept merchant-only or marketplace-heavy solutions if they satisfy the constraints.

**Recovery / observe:** Bounded replenishment is clearly marked assisted. Record whole-stack mistakes, stale selection recovery and whether the player checks existing returns before buying replacements.

### 10 · A ledger that balances — 2 minutes

**Picture:** The commission cart is packed. Venn closes the practice ledger and all private listings are reconciled.

**Voice:** “Outside this exchange, another person chooses the price and the answer.”

**Play:** Review the practice transaction summary, leave the isolated economy and inspect the restored real balance. Browse a real offer if desired without purchasing. Identify whether it is a merchant price or a player listing and show its actual quantity.

**Learn:** Practice guarantees a counterparty; public trading does not. No training price is promised as a market value.

**Evidence:** No open practice offer, listing, proceeds or return attached to public identity; permanent balances/items unchanged; stamp once.

**Recovery / observe:** Exit must reconcile in-flight transactions before restoring the real profile. Later transfer asks the player to inspect and cost an affordable trade; no public transaction or message is compulsory.

## Optional desks and feature coverage

| Feature | Lesson | Demonstration |
| --- | --- | --- |
| Merchant buy/sell, quantity, cost and capacity | 01–02 | Exact inventory and coin deltas |
| Reciprocal request, distance and partner identity | 03 | Genuine trade session |
| Offer inspection, two-stage accept and reset | 04 | Changed offer requires new acceptance |
| Reject, range/disconnect recovery, Storage routing | 05 | No transfer on cancel; selected destination used |
| Browse, unit versus total, Buy All and partial quantity | 06 | Correct purchase from real escrow |
| Listing exact stock, own listings, cancel and collect | 07 | Goods move through listing and return ownership |
| Offline proceeds and partial-capacity collection | 08 | Pending versus collected balances |
| Renewal and expiration | Desk A · an old notice | Renew an existing private listing; collect a disclosed already-aged fixture through the actual expiry path. Never wait a year or accelerate the public clock |
| Competing purchase and stale listing | Desk B · one bundle left | Scripted partner buys the selected stock; read genuine rejection, refresh and choose another offer |
| Tracked equipment identity/rarity | Desk C · two similar blades | Inspect and trade a specific instance; validate exact identity after receipt |

Optional desks take 4–6 minutes. Social trust, negotiation and real demand require an optional two-human session; scripted practice can teach only mechanics and review habits.

## Implementation dependencies and audit

The major new dependency is a separate practice economy namespace spanning auctions, escrow, item instances, trades, merchant stock, notifications and database writes. It must survive reconnect and be destroyed/reconciled without touching public listings. Borrowed Sky's public-action block cannot simply be removed for the player. Add explicitly scoped service access and scripted authenticated partner sessions. New content includes the market map, order board and ledger feedback.

Resolve the auction help/expiry mismatch and clearly label native Buy as whole-listing behavior. Recommended follow-up UI work includes total-cost/quantity review, safe exact-item listing and cancel/renew controls; until implemented, teach the actual commands. Current buying is immediate, so any pre-purchase review must occur before the real action.

Audit changed offers after acceptance, full receiving inventory, one side leaving Storage, two identical item names, slot reorder, vanished/partially bought listing, invalid quantity/price, own-listing purchase rejection, cancel/renew after sale, duplicate collect, disconnect on each transaction boundary and concurrent private markets. Require exact balances and instance ownership after every case.

## Human playtest emphasis

Target 5/6 completing mutual review/cancel and locating proceeds, and 4/6 completing the revised order within budget without mechanical hints. At least 5/6 should distinguish unit price from the actual whole-stack cost through a purchase decision. Run two ordinary clients to validate reciprocal acceptance and offer reset. A later inspection-only public task tests transfer without requiring real spending or unsolicited contact.

## Source audit

- [Auction service](../../../../dev-server/eloria/auction.py) and [commands](../../../../dev-server/eloria/server.py): listing, expiry, partial purchases, cancellation and collection; help inconsistency recorded above.
- [World trade and merchant runtime](../../../../dev-server/eloria/world.py), [shops](../../../../dev-server/eloria/shops.py), [item instances](../../../../dev-server/eloria/item_instances.py): atomic ownership, two-stage acceptance and routing.
- [Native extension windows](../../../godot-client/src/ui/extension_windows.gd) and [main client](../../../godot-client/src/app/main.gd): actual merchant, Buy All, collection and trade controls.

# Encyclopedia ledger

The Encyclopedia tab uses a dense reference table above a resizable article preview. The topic rail remains visible. Select a row to inspect it; double-click or choose **Open full article** to read the complete page. Full articles retain breadcrumbs, section links and related pages. Back restores the previous filters, page and selected entry.

Search covers titles, summaries, article text, structured sections, ingredients, tools, required books and facts. Words match without regard to case or order. Topic and entry-type filters combine with search. Sorting and filtering cover the complete installed catalogue before pagination, including entries on other pages.

The level column means a recipe's **recommended** level or a spell's **unlock** level. Maximum-level and book-requirement filters apply only where that information exists. A missing level is placed after numbered levels when sorting. Bookmark controls keep article keys in the existing player settings; earlier article, category and search bookmarks still work. Saved filtered views also restore their filters. The other Reference tabs keep their compact size.

## Content review: 8 November 2026

Reviewed the written reference pages against current client behavior and server development sources, including server `7e59dec`. Rebuilt comparison catalogues independently and verified all 472 recipes, 66 knowledge entries, 89 spells (including aliases and families), and 34 generated perk pages. Recipe and knowledge content matched; their item-source hashes needed refreshing. The matching server manifest's item-source hash and item count were also corrected.

Corrections include:

- Night affects creature visibility; weather has an authoritative per-map scheduler.
- Ranged weapons can fire in melee with penalties; maximum range increases with Ranging.
- Harvesting definitions contain recommended levels, experience, intervals and tool requirements. The client does not include a complete resource-location directory.
- Recipe levels are recommendations. Attempts can fail and critical failures can consume materials; rare results stop a running batch. Tools, knowledge, food and applicable nexus requirements still matter.
- Spell references distinguish base Power 1 costs, unlock and recommended levels, and Magic nexus requirements. Spell-family tomes appear in the book pages with links back to the spells they unlock.
- Storage preview, nearby-storage mixing, NPC prices and priced gauntlet allocations now have current descriptions.
- Former development placeholders are player-facing guides. Their existing page IDs remain valid for bookmarks.
- Structured authored sections and related links are retained and searchable; the previous entry loader dropped them.

The review describes the installed catalogues and current source behavior. Live eligibility, offers, prices, events and destinations are still decided by the connected server. Authored guides require editorial review when those rules change; the automated audit checks the reproducible catalogue content and leftover placeholders.

## Validation

Run the focused rendered ledger checks and the existing encyclopedia checks with Godot:

```
Godot --path godot-client --script res://tests/test_encyclopedia_ledger.gd
Godot --path godot-client --script res://tests/test_encyclopedia.gd
```

The ledger checks save screenshots under the ignored `godot-client/test-artifacts/encyclopedia-ledger/` directory and use an isolated player profile when invoked by the local check runner.

Re-run the source audit with a current server checkout:

```
python tools/audit_encyclopedia.py --server-root <server-checkout>
```

Comparison catalogues and the audit report stay in the ignored `.local/encyclopedia-audit/` directory. The audit never modifies the supplied server checkout. Client catalogue-source checks and the server's catalogue-content checks cover the companion metadata changes.

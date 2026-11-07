# Merchant shop

The compact shop uses **Buy** and **Sell** tabs with a six-column item grid.
The grid fits its contents up to a bounded scrolling height; searches and sparse
stock do not reserve empty rows.
Sell shows only owned items that the merchant buys. Prices appear below each
icon; sale tiles also show the owned count. Hover for the full item name and
price, or select an item to read its description in the shop.

Type buttons filter the merchant's actual categories. The category strip
scrolls horizontally when needed. Search matches canonical item names, display
names and categories, and combines with the selected type. Sorting offers name
in both directions, price in both directions, or item type. Sale-price sorting
compares the price per item, including fractional bundle prices.

Quantity shortcuts **1**, **5**, **10** and **100** sit beside the quantity controls.
They set an exact amount without submitting a trade. The Buy/Sell button is at
the bottom right. The quantity controls and Max retain the server's carrying, gold, ownership
and sale-bundle limits. The transaction button shows the total gold. Filtering
out the selected item clears the transaction; changing sort order preserves a
selection that remains visible. A pending trade remains disabled while browsing.

The shop packet does not currently include item categories. The client uses
the served catalogue's public name/category metadata in
`godot-client/data/items/categories.json`. Unrecognized goods appear under
**Other** and remain searchable. Refresh metadata after category changes:

```powershell
python tools/generate_item_categories.py --server-root C:/path/to/rabbitlands-server
```

The export includes only item names, normalized storage categories and a source
checksum. Prices, quantities and transaction identities always come from the
live merchant packet.

Focused checks use the supported local Godot executable:

```text
--headless --path godot-client --script res://tests/test_merchant_catalog.gd
--path godot-client --script res://tests/integration/rendered_merchant_shop_backpack.gd
```

Set `ELORIA_ARTIFACT_DIR` to a local ignored directory to save rendered frames
from the integration check. Capture requires a graphical renderer.

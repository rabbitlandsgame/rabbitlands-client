# Equipment effect artwork

32 individual transparent effect glyphs were generated for Rabbit Lands on
November 11, 2026 using OpenAI's built-in image generation tool. Each glyph
uses a broad, matte painted silhouette suited to the compact storage ledger.
The full prompt for every image is recorded in [manifest.json](manifest.json).

The generated PNGs retain their original alpha and resolution. Their authored
Godot import settings limit runtime textures to 96 pixels with lossless
compression and mipmaps; the ledger displays them at 30 pixels. This preserves
the authoring source while keeping the runtime texture footprint small.

The icon mapping and readable roll presentation live in
`src/ui/item_effect_icons.gd`. The server's complete effect description remains
available on hover. Generated originals and authoring receipts are also kept in
the ignored local asset-authoring workspace.

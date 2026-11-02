# Browser hosting

Use a small Cloudflare Pages launcher and Cloudflare R2 Standard for the asset
archives. The current packaged assets are about 2.6 GB; keep them separate from
the launcher and gameplay server. The player's browser runs the client, decodes
assets and renders the world on their CPU/GPU. Hosting assets does not move that
work to the server.

The prototype's current asset origin is
`https://assets.rabbitlandsgame.com/browser/assets/` on R2. The launch website
remains a local development prototype; connecting the asset domain does not
publish the launch page or deploy the gameplay server.

## Recommended setup

| Component | Suggested location |
| --- | --- |
| Canonical browser launcher | `https://play.rabbitlandsgame.com` on Pages |
| Content-addressed engine and asset files | R2 custom domain, for example `https://assets.rabbitlandsgame.com/browser/` |
| Gameplay connection | Existing server through a secure `wss://` endpoint |

Pages supports **20,000 files on its Free plan**, with a **25 MiB maximum per
file**. Keep larger WASM, PCK and archive files in R2. See
[Pages limits](https://developers.cloudflare.com/pages/platform/limits/).

R2 Standard includes **10 GB-month of storage, 1 million Class A operations
(writes/listing), and 10 million Class B operations (reads) per month**, with
**free Internet egress**. The asset set fits the storage allowance, but retained
versions and other account usage also count. These allowances do not apply to
Infrequent Access. See [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

R2 requires subscription checkout and a valid payment method. Usage beyond the
allowance is billed: this is not a hard-capped free plan. See
[R2 setup](https://developers.cloudflare.com/r2/get-started/) and
[Cloudflare billing policy](https://developers.cloudflare.com/billing/understand/billing-policy/).
Use a custom domain for production caching; `r2.dev` is a rate-limited development
endpoint. The domain must be in the same Cloudflare account as the bucket. See
[public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/).

Keep the launcher on one canonical HTTPS origin so browser storage and saved
folder permissions remain associated with the same site. Configure:

- `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp` on launcher responses for the
  threaded client. See [Godot's serving requirements](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html#serving-the-files).
  Pages supports a
  [`_headers` file](https://developers.cloudflare.com/pages/configuration/headers/).
- Asset CORS allowing `GET` and `HEAD` from the canonical launcher origin.
  Cross-origin fetches must succeed under that isolation policy. See
  [R2 CORS](https://developers.cloudflare.com/r2/buckets/cors/).
- Correct MIME types, including `application/wasm`, and HTTPS asset URLs plus
  secure WebSockets. Keep any connection-origin allowlist matched to the launcher.
- Immutable hash-named files with long cache lifetimes. Publish matching catalogs
  only after their files are available; allow catalogs and launch pages to refresh.

## Local files and repeat visits

The client verifies downloaded files and saves them locally. Browser storage is
the default; supported desktop browsers also offer a player-selected folder.
A folder makes the saved archives visible and manageable outside the browser.
The browser may ask for permission again. Browser storage can be cleared or
evicted, and unavailable or damaged files must be downloaded again.

The first visit still downloads the engine and assets needed for the selected
character and maps. Later visits reuse verified files; updates fetch changed
content, while newly visited areas fetch their missing files. Local storage
reduces network transfers, not rendering costs, and online play still needs the
game server. See [browser controls](browser-controls.md).

## itch.io and Steam

An itch.io build can contain a small launcher with externally hosted HTTPS
assets. Its default HTML5 ZIP limits are **500 MB extracted total, 200 MB per
file, and 1,000 files**. See
[itch.io HTML5 hosting](https://itch.io/docs/creators/html5). Threaded builds must
enable itch's [SharedArrayBuffer option](https://itch.io/t/2025776/experimental-sharedarraybuffer-support)
and satisfy its cross-origin restrictions.

Recommend a link to the canonical full-page client for folder storage. The
current client disables its folder picker in frames, and browsers prohibit new
file permissions in cross-origin frames. See the
[File System Access specification](https://wicg.github.io/file-system-access/).
Keep itch as an optional launch/discovery channel rather than relying on raw
itch CDN URLs as an external asset host; itch supports its project page and Game
Embed entry points, as explained in its
[hosting guidance](https://itch.io/t/2025776/experimental-sharedarraybuffer-support).

A browser version can coexist with a Steam release; Valve documents distribution
through other stores. Its comparable-offer rules concern **Steam keys**, and
should not be presented as a blanket pricing rule for an independent browser
version. See [Steam Keys](https://partner.steamgames.com/doc/features/keys).
The Steam build's in-game purchases must use Steam Wallet. Do not direct players
from that build to an external checkout without Steam Wallet. See
[purchase requirements](https://partner.steamgames.com/doc/features/microtransactions)
and [build review](https://partner.steamgames.com/doc/store/review_process).
Confirm app-specific distribution and monetization terms before release.

Provider limits checked on 2026-11-02; consult the linked documentation before
publishing.

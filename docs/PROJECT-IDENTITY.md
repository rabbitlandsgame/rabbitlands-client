# Rabbit Lands project identity and compatibility

Rabbit Lands (RL) is an independently developed fantasy MMORPG featuring exploration, combat, crafting, magic, character progression, and a persistent multiplayer world. Its official domain is rabbitlandsgame.com. The setting may continue to be called Eloria.

Rabbit Lands is not officially affiliated with Eternal Lands or its developers. Existing upstream licenses and third-party attribution remain applicable.

## Local workspace

Keep `rabbitlands-client` and `rabbitlands-server` as sibling checkouts. The recommended Windows workspace is `C:\rabbitlands`. Local databases, certificates, private signing keys, editor caches, and engine binaries are not published in either repository.

## Branches and optional validation

`master` is the stable default branch. Work on `develop`, review the intended changes, and explicitly merge into `master` when a release is ready. In the prepared local workspace, `develop` tracks local `master` and pushes to `origin/develop`.

No GitHub Actions workflows are included. Existing tests remain available for manual use. Run the focused checks relevant to a change; the historical full suites are optional and are not automatic merge requirements.

## Legacy identifiers

The `eloria` Python package, `config/eloria`, `eloria-assets`, resource paths, protocol constants, persisted settings and database names are retained where changing them would break compatibility. These identify stable internal formats or world content. Public application, packaging, distribution and repository names use Rabbit Lands.

Do not rename player databases or Docker data volumes without explicitly mapping the existing data. Rebranding does not reset accounts, characters, inventories or progression.

## Public connection configuration

The canonical configurable game hostname is `game.rabbitlandsgame.com`. The client defaults to verified native TLS on TCP 2001. Localhost and custom hosts remain supported; the explicit `--dev-plain-tcp` launch option selects plain TCP for local testing (default `127.0.0.1:2000`) without saving an insecure player preference. Website HTTPS reverse proxies do not replace the game's TCP listener. Update downloads use HTTPS separately.

Public play requires DNS pointing to the actual host, appropriate TCP firewall rules, and a valid certificate when TLS is enabled. Domain registration alone does not establish a running game service. Production DNS, hosting, certificates and existing player data are managed separately.
## Historical audit records

Historical revision tokens in older QA, provenance and benchmark records are opaque migration references, not Git commits reachable in these repositories. Original history and the private reference mapping are retained separately. Historical tools that replay those revisions require the private original checkout; run their original versions there. They are optional and are not merge requirements. Current gameplay content is loaded from the committed runtime assets and configuration.

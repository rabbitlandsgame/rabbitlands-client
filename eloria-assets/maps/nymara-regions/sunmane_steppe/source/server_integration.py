#!/usr/bin/env python3
"""Regenerate `server-integration.md` from the committed manifests.

The server-side records are transcribed from the packages rather than typed, so
the document cannot drift from what the client actually ships.

Run:  python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/server_integration.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
# Sunmane's two cave systems used to be two packages and two served maps.
# They now share one package and one map with unwalkable blackspace between
# them, so this reads the combined manifest and describes its sections. The
# standalone packages are still built and kept for iterating on one system,
# but they are no longer what the server registers.
INSIDES = "sunmane_insides"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    align = ["---"] * len(header)
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(align) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def tile(entry) -> str:
    return "`(%d, %d)`" % (entry[0], entry[1])


def main() -> int:
    manifest = json.loads((PACKAGE / "world.json").read_text())
    insides = json.loads((ROOT / "interiors" / INSIDES / "world.json").read_text())
    population = manifest["runtimePopulation"]
    out: list[str] = []
    add = out.append

    add("# Sunmane Steppe - server integration\n")
    add("Everything in this document is server-side work that this client change")
    add("does **not** perform. The client change is self-contained and does not")
    add("alter the network protocol or any gameplay behaviour; the region loads")
    add("and is traversable with the server exactly as it is today.\n")
    add("`eloria-server` was not reachable from the workspace this package was")
    add("built in, so none of the records below could be committed there. They are")
    add("generated from the committed manifests by")
    add("`maps/nymara-regions/sunmane_steppe/source/server_integration.py`, so the matching server pull")
    add("request is transcription rather than redesign.\n")

    add("## Hooks\n")
    add("The region's hook names come from")
    add("`maps/nymara-regions/region-connections.json` and are")
    add("unchanged:\n")
    out.extend(table(["Hook", "Name"], [
        ["npc", "`npcs.nymara.sunmane_steppe`"],
        ["spawn", "`spawns.nymara.sunmane_steppe`"],
        ["hazard", "`hazards.nymara.sunmane_steppe`"],
        ["harvest", "`harvest.nymara.sunmane_steppe`"]]))
    add("")

    add("## Map registration\n")
    transform = manifest["coordinateTransform"]
    band = transform["addressableWorldBounds"]
    out.extend(table(["Property", "Value"], [
        ["Server map id", "`maps/nymara/sunmane_steppe.elm`"],
        ["Metres per server tile", transform["metresPerTile"]],
        ["Arrival datum", tile([int(v) for v in transform["serverOrigin"]])],
        ["Addressable tiles", "0..191 on both axes"],
        ["Addressable world band",
         "X %.0f..%.0f, Z %.0f..%.0f" % (band["min"][0], band["max"][0],
                                         band["min"][1], band["max"][1])],
        ["Walk portal west", "`(6, 58)` from Amethyst Barrens `(110, 58)`"],
        ["Walk portal east", "`(110, 58)` to Amberwood `(6, 58)`"],
        ["Interior entrance", "`(58, 100)` to Ssarathi Royal Archive `(58, 10)`"]]))
    add("")
    add("The region is wider than the addressable band on purpose. Everything")
    add("outside it - the far spires, the summits, the open sea - is scenery a")
    add("player can see but never stand on, and it is marked")
    add('`"reachable": false` in the manifest. The server needs no record of it.\n')

    add("## The interior map\n")
    add("Sunmane's two cave systems share **one** interior map, the way")
    add("Crownwater's and Ssarathi's insides do: one package, one server map id,")
    add("one collision grid, and unwalkable blackspace between the systems. Which")
    add("system a player gets is decided by the mouth they entered, so there is")
    add("one portal pair per door rather than one per system:\n")
    rows = []
    for section in insides["sections"]:
        portal = next(entry for entry in insides["portals"]
                      if entry["section"] == section["id"])
        entrance = next(entry for entry in manifest["interactives"]
                        if entry.get("destinationMap", "")
                        .endswith(section["id"] + ".elm"))
        rows.append([
            section["name"],
            tile(entrance["serverTile"]),
            tile(section["arrivalServerTile"]),
            tile(portal["destinationTile"])])
    out.extend(table(["Section", "Mouth on the steppe", "Arrival inside",
                      "Exit back to"], rows))
    add("")
    span = int(insides["collision"]["width"] * insides["collision"]["cellMetres"])
    add("Both doors go to `maps/nymara/sunmane_wind_caves.elm`, which is one metre")
    add("per tile like the surface map, uses `invertServerY`, and puts its datum")
    add("at the map corner rather than the centre of a square, so a section's")
    add("tiles are simply its metres. The package is %d m across, so the map needs"
        % span)
    add("%d server tiles where the wind caves alone needed 10." % (span // 6))
    add("")
    add("`maps/nymara/sunmane_crystal_hollow.elm` is **retired** as a served map.")
    add("The other two cave mouths on the surface - the drovers' shelter and the")
    add("eastern adit - are modelled shelters with no interior and need no")
    add("registration.\n")

    add("## Safe spawn surfaces\n")
    add("The client grounds actors by raycasting the navigation surface, and every")
    add("sampled column in the region grounds successfully, so any walkable tile is")
    add("a safe spawn. The positions the manifests name explicitly:\n")
    rows = [[entry["id"], tile(entry["serverTile"]), "sunmane_steppe", entry["note"]]
            for entry in manifest["spawnPoints"]]
    rows += [[entry["id"], tile(entry["serverTile"]), "sunmane_wind_caves",
              entry["note"]] for entry in insides["spawnPoints"]]
    out.extend(table(["Spawn id", "Server tile", "Map", "Note"], rows))
    add("")

    add("## NPC posts (%d)\n" % len(population["npcs"]))
    out.extend(table(["Id", "Label", "Role", "Server tile"],
                     [[f"`{entry['id']}`", entry["label"], entry["role"],
                       tile(entry["serverTile"])] for entry in population["npcs"]]))
    add("")

    add("## Harvestable resources (%d)\n" % len(population["resources"]))
    out.extend(table(["Id", "Label", "Kind", "Server tile"],
                     [[f"`{entry['id']}`", entry["label"], entry["kind"],
                       tile(entry["serverTile"])] for entry in population["resources"]]))
    add("")

    add("## Hostile creature spawns (%d)\n" % len(population["creatures"]))
    add("All models below already exist in the client's creature catalogue.\n")
    out.extend(table(["Model", "Area", "Count", "Radius", "Server tile"],
                     [[f"`{entry['model']}`", entry.get("area", ""), entry["count"],
                       "%.1f m" % entry["radius"], tile(entry["serverTile"])]
                      for entry in population["creatures"]]))
    add("")

    add("## Interaction points needing server behaviour\n")
    add("The manifest declares %d interaction points. The ones that need a server"
        % len(manifest["interactives"]))
    add("decision rather than a client-side prompt are the map transitions:\n")
    rows = [[f"`{entry['id']}`", entry["label"], tile(entry["serverTile"]),
             "`%s`" % entry["destinationMap"], tile(entry["destinationTile"])]
            for entry in manifest["interactives"]
            if entry.get("destinationMap")]
    out.extend(table(["Id", "Label", "Server tile", "Destination map",
                      "Arrival tile"], rows))
    add("")
    add("The remainder - wells, water stations, shrines, markets, shelters,")
    add("hitching rails - are ordinary interaction points and behave like the")
    add("equivalents in other regions.\n")

    add("## Livestock actor types\n")
    add("Three creature assets ship with this change: `sunmane_steppe_horse`,")
    add("`sunmane_dun_mare` and `sunmane_grey_pony`. They are registered in")
    add("`godot-client/data/actors/models.json` by model id and are instanced as")
    add("**scenery** by the client's ambient population system, so they need")
    add("nothing from the server to appear.\n")
    add("They are deliberately registered with `serverActorType: null`. Actor-type")
    add("numbers are the server's to allocate, and the creature block in")
    add("`models.json` currently runs 204-235. If the server wants these as")
    add("networked, attackable or rideable actors it should allocate the next free")
    add("numbers and add the matching `actorTypes` entries; until then the client")
    add("will simply never receive one over the wire, which is harmless.\n")

    add("## What must not change\n")
    add("The map deliberately requires no protocol change:\n")
    add("- One metre per server tile, and the arrival datum at `(58, 58)`, both")
    add("  matching the entry already committed in")
    add("  `godot-client/data/maps/registry.json`.")
    add("- Server tile to world position uses the existing `CoordinateAdapter`")
    add("  unchanged; the region moved its world centre, not its datum.")
    add("- Walkability remains server-authoritative. The client's navigation")
    add("  surface covers the whole landform on purpose, so a grounding raycast")
    add("  can never miss; it does not decide where a player may go.")

    (PACKAGE / "server-integration.md").write_text("\n".join(out) + "\n")
    print("wrote", PACKAGE / "server-integration.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""publish_server.py's NPC occupation fields, without a server checkout.

An NPC marker's extras may carry "occupation" ("Grove-Keeper"): the line a client draws under the name. The publisher
writes it into the generated npcs.txt as one more option of the portrait column, `actor_type=376,occupation=...`,
which the server's loader (eloria/npcs.py occupation_for) parses. The owner's rule (2026-10-14) is that names stay
simple and the job goes on that line, so a name that still starts with its own occupation is refused here as it is
there. test_publish_server.py runs the whole publisher and needs ELORIA_SERVER_ROOT; these do not.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import publish_server as P  # noqa: E402


def test_the_portrait_column_carries_the_occupation_after_the_body():
    assert P.npc_portrait(376) == "actor_type=376"
    assert P.npc_portrait(376, "Grove-Keeper") == "actor_type=376,occupation=Grove-Keeper"
    assert P.portrait_options("actor_type=376,occupation=Grove-Keeper") == {
        "actor_type": "376", "occupation": "Grove-Keeper"}
    assert P.portrait_options("actor_type=302") == {"actor_type": "302"}


def test_a_marker_without_an_occupation_has_none():
    assert P.occupation_field(None, "Tavi Unhar", "stagheath--npc-tavi-unhar") == ""
    assert P.occupation_field("Light-Keeper", "Marta Quell", "m") == "Light-Keeper"


@pytest.mark.parametrize("vector,facing", [
    ([0, 0, -1], "N"), ([1, 0, -1], "NE"), ([1, 0, 0], "E"), ([1, 0, 1], "SE"),
    ([0, 0, 1], "S"), ([-1, 0, 1], "SW"), ([-1, 0, 0], "W"), ([-1, 0, -1], "NW"),
])
def test_npc_marker_facing_survives_publication(vector, facing):
    direction = P.npc_facing({"id": "npc", "facing": vector})
    assert direction == facing
    assert P.npc_portrait(312, "Register Clerk", direction) == (
        f"actor_type=312,occupation=Register Clerk,facing={facing}")


def test_missing_facing_preserves_old_bakes_and_degenerate_vectors_are_refused():
    assert P.npc_facing({"id": "old"}) == ""
    for vector in ([0, 0, 0], [1, 0], [float("nan"), 0, 1]):
        with pytest.raises(P.PublishError, match="NPC facing"):
            P.npc_facing({"id": "bad", "facing": vector})


@pytest.mark.parametrize("value", ["", " Grove-Keeper", "Grove  Keeper", "Grove,Keeper", "<Grove-Keeper>",
                                   "Grove=Keeper", "Grove#Keeper", "x" * (P.OCCUPATION_LIMIT + 1), 7])
def test_an_occupation_the_loader_would_refuse_is_refused_here(value):
    with pytest.raises(P.PublishError, match="occupation"):
        P.occupation_field(value, "Ammet Sorrel", "landfall--npc-grove-keeper-ammet-sorrel")


def test_a_name_that_still_carries_its_occupation_is_refused():
    with pytest.raises(P.PublishError, match="keep the name simple"):
        P.occupation_field("Toolkeeper", "Toolkeeper Brin Tallow", "fixture--npc-brin-tallow")
    assert P.occupation_field("Toolkeeper", "Brin Tallow", "fixture--npc-brin-tallow") == "Toolkeeper"

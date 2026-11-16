"""A territory may newly place a pooled prototype another committed territory already ships.

publish_finish refuses to pool a fresh mesh onto a prototype whose texture policy directory differs; a fresh continent
export carries no policy extras, so every prototype pooled from the Nymara territories differs. publish_client passes
the whole continent's committed set as inherited (continent_inherited_prototypes): border flora carried across a seam
(2026-11-16) then reuses the prototype, images and policy the continent ships today. These cases check that set on
the committed packages and that the policy check honours it.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_client_inherited.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
sys.path.insert(0, str(V2))
import frames  # noqa: E402
import publish_client as PC  # noqa: E402
import publish_finish as PF  # noqa: E402
import shared_meshes as SM  # noqa: E402

PACKAGES = {region: CHECKOUT / "eloria-assets/maps/continent-v2" / region / "client" for region in frames.regions(CHECKOUT)}


@pytest.fixture(scope="module")
def continent():
    return PC.continent_inherited_prototypes(CHECKOUT)


def test_the_continent_set_is_the_union_of_every_committed_package(continent):
    union = frozenset().union(*(PF.published_prototypes(p) for p in PACKAGES.values()))
    assert union and continent == union


def test_some_prototype_is_shipped_by_one_package_and_not_another(continent):
    # the case the union exists for: a kit one territory ships and its neighbour does not
    shipped = {region: PF.published_prototypes(p) for region, p in PACKAGES.items()}
    assert any(continent - own for own in shipped.values())


def test_the_policy_check_lets_an_inherited_prototype_through_and_refuses_otherwise(tmp_path, continent):
    index = json.loads((CHECKOUT / "eloria-assets/maps/_shared/meshes/index.json").read_bytes())["prototypes"]
    nymara = sorted(p for p in continent
                    if any("nymara-regions" in uri for uri in (index.get(p) or {}).get("images", {})))
    assert nymara, "no committed continent prototype is pooled from the Nymara territories"
    identity = nymara[0]
    target = SM.POOL / f"{identity}.glb"
    prototype, _ = SM.read_glb(target)
    # a fresh export of the same mesh: same images, kept beside the export (no policy extras)
    incoming = json.loads(json.dumps(prototype))
    for image in incoming.get("images", []):
        image.pop("extras", None)
        if image.get("uri"):
            image["uri"] = Path(image["uri"]).name
    source = tmp_path / "chunk" / "world.glb"
    source.parent.mkdir()
    SM._check_prototype_policy(incoming, 0, source, prototype, target, inherited=True)
    explicit, existing = SM._mesh_image_policies(prototype, 0, target)
    fresh_explicit, fresh = SM._mesh_image_policies(incoming, 0, source)
    assert explicit and not fresh_explicit and existing != fresh    # the refusal the inherited set answers
    with pytest.raises(ValueError, match="original texture policy differs"):
        SM._check_prototype_policy(incoming, 0, source, prototype, target, inherited=False)

from pathlib import Path
from types import SimpleNamespace
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mirror_access_geometry as M
import scene_io as S


def test_saved_mirrorhold_authority_skips_duplicate_bank_access(tmp_path):
    world = SimpleNamespace(authoring_snapshots={"mirrorhold": object()})
    output = tmp_path / "mirror-bank-access.glb"

    assert M.build_mirror_access(world, object(), output) == []
    document, _body = S.GR.load(output)
    assert document["scenes"][0]["nodes"] == []
    assert world.mirror_bank_access == [{
        "authority": "saved-authored-assets", "region": "mirrorhold"}]
    assert world.mirror_bank_opening == {
        "authority": "saved-resolved-terrain", "region": "mirrorhold"}

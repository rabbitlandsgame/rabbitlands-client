"""Prepared prototype identities must use the runtime's original caller policy."""
from pathlib import Path
import re
import sys

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import build_vram_textures as vram


def test_producer_and_final_guard_share_runtime_prototype_policy_projection():
    runtime = (CLIENT / "src/world/external_mesh_pool.gd").read_text()
    helper = runtime.split("static func _image_manifest(entry: Dictionary)", 1)[1].split("static func ", 1)[0]
    mapping = dict(re.findall(r'"(externalResources|externalImagePolicies)": entry.get\("([^"]+)"', helper))
    assert mapping == {"externalResources": "images", "externalImagePolicies": "imagePolicies"}
    for name in ("cook_prepared_assets.gd", "check_prepared_release.gd"):
        code = (CLIENT / "tools" / name).read_text()
        assert "Vram.cache_token(MeshPool._image_manifest(pool_entry)," in code
        assert 'Vram.cache_token({"externalResources": pool_entry.get("images", {})}' not in code

    # The canonical pixel copy can live in an eligible pool while the original
    # caller deliberately remains excluded. Dropping imagePolicies changes the
    # effective resource contract despite an identical source SHA.
    uri = "../../nymara-regions/_continent/shared-assets/" + "a" * 64 + ".jpg"
    entry = {"images": {uri: "a" * 64}, "imagePolicies": {uri: ["../images"]}}
    manifest = {target: entry[source] for target, source in mapping.items()}
    assert manifest["externalImagePolicies"][uri] == ["../images"]
    record = {"path": Path("canonical.jpg"), "roles": {("normal", "OPAQUE")},
              "maps": {"_shared/meshes"}, "cutoffs": set()}
    original = vram.delivery_policy(record, Path("maps/_shared/images"), skip=["_shared/images"])
    canonical = vram.delivery_policy(record, Path("maps/nymara-regions/_continent/shared-assets"), skip=["_shared/images"])
    assert original["recipe"] is None and original["reason"] == "excluded_by_caller"
    assert canonical["recipe"] == "normal"

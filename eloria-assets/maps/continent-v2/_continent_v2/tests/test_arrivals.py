"""Hash-bound defaults refuse changed content, mixed authority and frame/ownership drift."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import arrivals as A
import frames as F
import ownership as O


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw = (json.dumps(value,indent=1)+"\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def generated(tmp_path):
    frame = F.Frame("fixture","Fixture",(3,7),(12,12),(100.,0.,200.))
    partition = tmp_path/"eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/sections_spec.json"
    spec_sha = write(partition,{"fixture":True})
    record = {"schema":A.SCHEMA,"map":"fixture","id":"generated-arrival-fixture","default":True,"generated":True,
              "position":[0.5,12.,0.5],"serverTile":[3,6],"facing":[0.,0.,-1.],"frame":A.frame_record(frame),
              "provenance":{"algorithm":A.ALGORITHM,"clientBaseCommit":"1"*40,"sectionsSpecSha256":spec_sha,
                            "frameSha256":A.frame_sha256(frame),"sourceWorldSha256":"2"*64,
                            "sourceCollisionSha256":"3"*64,"sourceServedGridSha256":"4"*64}}
    relative = "eloria-assets/maps/continent-v2/fixture/content/arrival.json"
    binding = {"path":relative,"sha256":write(tmp_path/relative,record)}
    spec = tmp_path/"godot-client/world_authoring/regions/fixture/region-authoring-spec.json"
    write(spec,{"gameplay":{"generatedArrival":binding}})
    write(tmp_path/"eloria-assets/maps/continent-v2/fixture/world.json",{"continentGeography":{"ownershipPolygons":[[[98,198],[103,198],[103,203],[98,203]]]}})
    doc = {"regionId":"fixture","gameplay":{"spawnPoints":[]},"generatedArrival":copy.deepcopy(record),"sources":{"generatedArrival":binding}}
    return tmp_path,frame,doc,record,binding


def test_generated_default_is_separate_from_conserved_markers(generated):
    root,frame,doc,record,_ = generated
    assert A.resolve(doc,frame,root) == record
    assert doc["gameplay"]["spawnPoints"] == []


def test_bake_json_round_trip_accepts_last_bit_but_refuses_changed_coordinates(generated):
    import math
    root, frame, doc, record, _ = generated
    doc["generatedArrival"]["position"][1] = math.nextafter(record["position"][1], math.inf)
    assert A.resolve(doc, frame, root) == record
    doc["generatedArrival"]["position"][1] += 1e-6
    with pytest.raises(A.ArrivalError, match="source/bake binding"):
        A.resolve(doc, frame, root)
    assert not A._bake_json_equal({"tile": [3, 6]}, {"tile": [3.000000000000001, 6]})
    assert not A._bake_json_equal({"default": True}, {"default": 1})


@pytest.mark.parametrize("fault",["source","bake","tile","frame","ownership","mixed"])
def test_generated_refuses_stale_or_ambiguous_authority(generated,fault):
    root,frame,doc,record,binding = generated
    if fault == "source":
        (root/binding["path"]).write_bytes(b"{}")
    elif fault == "bake":
        doc["generatedArrival"]["position"][0] += 1
    elif fault == "mixed":
        doc["gameplay"]["spawnPoints"].append({"default":True})
    elif fault == "ownership":
        write(root/"eloria-assets/maps/continent-v2/fixture/world.json",{"continentGeography":{"ownershipPolygon":[[200,200],[210,200],[210,210],[200,210]]}})
    else:
        if fault == "tile":
            record["serverTile"][0] += 1
        else:
            record["frame"]["origin"][0] += 1
        binding["sha256"] = write(root/binding["path"],record)
        write(root/"godot-client/world_authoring/regions/fixture/region-authoring-spec.json",{"gameplay":{"generatedArrival":binding}})
        doc["generatedArrival"] = record
    with pytest.raises(A.ArrivalError):
        A.resolve(doc,frame,root)


@pytest.mark.parametrize("path",["../arrival.json","/arrival.json","C:/arrival.json","a/../../arrival.json","a\\arrival.json"])
def test_arrival_reference_cannot_escape_checkout(tmp_path,path):
    with pytest.raises(A.ArrivalError):
        A.contained(tmp_path,path)


def test_multipart_union_excludes_gap_and_refuses_missing_component():
    rings = [[[0,0],[2,0],[2,2],[0,2]],[[5,0],[7,0],[7,2],[5,2]]]
    assert O.contains([1,3,6],[1,1,1],rings).tolist() == [True,False,True]
    assert O.contains(2,1,rings,boundary=True)
    with pytest.raises(ValueError):
        O.rings([rings[0],[[float("nan"),0],[1,0],[1,1]]])
    with pytest.raises(ValueError):
        O.rings([rings[0],rings[0]])

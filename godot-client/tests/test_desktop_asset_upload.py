"""Desktop R2 uploader (tools/upload_desktop_assets.py) against fakes: no live R2, GitHub or network.

The fake S3 client replays botocore's event pipeline (before-parameter-build,
before-call, before-send), so the SDK guard runs in every test. Tests marked
"real botocore" also drive a real botocore client whose requests are answered
in-process by a before-send emulator; they are skipped when botocore is not
importable.
"""
import ast
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import threading
import traceback
import types
import urllib.parse

import pytest

GODOT = Path(__file__).resolve().parents[1]
TOOLS = GODOT / "tools"
sys.path.insert(0, str(TOOLS))
import desktop_r2 as r2  # noqa: E402
import upload_desktop_assets as up  # noqa: E402

COMMITTED_PEM = (GODOT / "data/update_public.pem").read_bytes()
ACCOUNT = "f00dfacef00dfacef00dfacef00dface"
KEY_ID = "AKIDCANARY0123456789abcdef"
SECRET = "SECRETCANARYsecretcanary0123456789ABCDEFxyz"
ENDPOINT = f"https://{ACCOUNT}.r2.cloudflarestorage.com"
CANARIES = (ACCOUNT, KEY_ID, SECRET, ENDPOINT)
COMMIT = "0123456789abcdef0123456789abcdef01234567"
PREVIOUS = "fedcba9876543210fedcba9876543210fedcba98"
TAG = f"client-{COMMIT}"
SEQUENCE = 1_762_300_000
SHA_A = "a" * 64

try:
    from botocore import exceptions as botocore_exceptions
except ImportError:  # the SDK is optional for most tests
    botocore_exceptions = None

needs_botocore = pytest.mark.skipif(botocore_exceptions is None, reason="botocore is not importable")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaked(text) -> list:
    text = str(text).casefold()
    return [value for value in CANARIES if value.casefold() in text]


def chain(error):
    seen = []
    while error is not None and all(error is not item for item in seen):
        seen.append(error)
        error = error.__cause__ or error.__context__
    return seen


def assert_clean_exception(error):
    for item in chain(error):
        text = str(item) + repr(item) + repr(item.args) + "".join(traceback.format_exception(item))
        assert not leaked(text), (type(item).__name__, leaked(text))


# --- Keys and configuration ----------------------------------------------------

def _rsa():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return types.SimpleNamespace(
        private=key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()),
        public=key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo))


@pytest.fixture(scope="session")
def test_key():
    key = _rsa()
    assert key.public != COMMITTED_PEM
    return key


@pytest.fixture(scope="session")
def other_key():
    return _rsa()


@pytest.fixture
def credentials(tmp_path):
    path = tmp_path / "private" / "r2-desktop.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"endpoint_url": ENDPOINT, "bucket": r2.BUCKET, "access_key_id": KEY_ID,
                                "secret_access_key": SECRET,
                                "public_base_url": "https://assets.rabbitlandsgame.com/browser/assets/"}))
    return path


@pytest.fixture(autouse=True)
def forget_secrets():
    yield
    up._SECRETS.clear()


# --- Fake S3 (replays botocore's event pipeline) -----------------------------------

def client_error(code, status, message="error"):
    response = {"Error": {"Code": code, "Message": message}, "ResponseMetadata": {"HTTPStatusCode": status}}
    if botocore_exceptions is not None:
        return botocore_exceptions.ClientError(response, "Operation")

    class ClientError(Exception):
        pass
    error = ClientError(f"An error occurred ({code}): {message}")
    error.response = response
    return error


class FakeModel:
    def __init__(self, name):
        self.name = name


class FakeEvents:
    def __init__(self):
        self.handlers = {}

    def register_first(self, event, handler, unique_id=None):
        self.handlers.setdefault(event, []).insert(0, handler)

    def emit(self, event, **kwargs):
        for handler in self.handlers.get(event, []):
            handler(**kwargs)


class FakeBody:
    def __init__(self, data):
        self.stream = io.BytesIO(data)

    def read(self, amount=None):
        return self.stream.read(amount)

    def close(self):
        pass


METHODS = {"HeadObject": "HEAD", "GetObject": "GET", "PutObject": "PUT", "ListObjectsV2": "GET"}


class FakeS3:
    """An in-memory R2 with conditional-write semantics. `inject` maps an
    operation (or (operation, key)) to a callable run before the operation."""

    def __init__(self):
        self.meta = types.SimpleNamespace(events=FakeEvents())
        self.objects = {}
        self.calls = []
        self.puts = []
        self.inject = {}
        self.hide_once = set()
        self.lock = threading.Lock()

    def _pipeline(self, name, params):
        context = {}
        self.meta.events.emit("before-parameter-build.s3", params=params, model=FakeModel(name), context=context)
        headers = {}
        if "IfNoneMatch" in params:
            headers["If-None-Match"] = params["IfNoneMatch"]
        if "IfMatch" in params:
            headers["If-Match"] = params["IfMatch"]
        if name == "PutObject":
            headers["Content-Length"] = str(params["ContentLength"])
        if name == "ListObjectsV2":
            request = {"method": "GET", "url_path": "?list-type=2", "headers": headers,
                       "query_string": {"list-type": 2, "prefix": params.get("Prefix")}}
        else:
            request = {"method": METHODS[name], "url_path": "/" + params["Key"], "headers": headers, "query_string": {}}
        self.meta.events.emit("before-call.s3", model=FakeModel(name), params=request, context=context)
        self.meta.events.emit("before-send.s3", request=types.SimpleNamespace(method=request["method"], headers=headers))
        key = params.get("Key", params.get("Prefix"))
        with self.lock:
            self.calls.append((name, key))
        hook = self.inject.get((name, key)) or self.inject.get(name)
        if hook:
            hook(params)

    def seed(self, key, data, *, sequence=None, selftest=False, metadata_sha=None, content_type=None):
        headers = r2.object_headers(key, sha(data), sequence=sequence, selftest=selftest)
        self.objects[key] = {"body": data, "ContentType": content_type or headers["ContentType"],
                             "CacheControl": headers["CacheControl"],
                             "Metadata": {**headers["Metadata"], **({"sha256": metadata_sha} if metadata_sha else {})},
                             "ETag": '"' + hashlib.md5(data).hexdigest() + '"', "ChecksumSHA256": None}

    def head_object(self, **params):
        self._pipeline("HeadObject", params)
        key = params["Key"]
        with self.lock:
            hidden = key in self.hide_once
            self.hide_once.discard(key)
            item = None if hidden else self.objects.get(key)
        if item is None:
            raise client_error("404", 404, "Not Found")
        result = {"ContentLength": len(item["body"]), "ContentType": item["ContentType"],
                  "CacheControl": item["CacheControl"], "Metadata": dict(item["Metadata"]), "ETag": item["ETag"]}
        if params.get("ChecksumMode") == "ENABLED" and item["ChecksumSHA256"]:
            result["ChecksumSHA256"] = item["ChecksumSHA256"]
        return result

    def get_object(self, **params):
        self._pipeline("GetObject", params)
        item = self.objects.get(params["Key"])
        if item is None:
            raise client_error("NoSuchKey", 404, "The specified key does not exist.")
        return {"Body": FakeBody(item["body"]), "ETag": item["ETag"], "ContentLength": len(item["body"])}

    def put_object(self, **params):
        self._pipeline("PutObject", params)
        body = params["Body"]
        data = body if isinstance(body, bytes) else body.read()
        assert len(data) == params["ContentLength"]
        if "ChecksumSHA256" in params and params["ChecksumSHA256"] != base64.b64encode(hashlib.sha256(data).digest()).decode():
            raise client_error("BadDigest", 400)
        key = params["Key"]
        with self.lock:
            existing = self.objects.get(key)
            if params.get("IfNoneMatch") == "*" and existing is not None:
                raise client_error("PreconditionFailed", 412, f"pre-condition failed for {ACCOUNT}")
            if "IfMatch" in params and (existing is None or existing["ETag"] != params["IfMatch"]):
                raise client_error("PreconditionFailed", 412)
            self.objects[key] = {"body": data, "ContentType": params["ContentType"], "CacheControl": params["CacheControl"],
                                 "Metadata": dict(params["Metadata"]), "ETag": '"' + hashlib.md5(data).hexdigest() + '"',
                                 "ChecksumSHA256": params.get("ChecksumSHA256")}
            self.puts.append((key, {name: value for name, value in params.items() if name != "Body"}))
        return {"ETag": self.objects[key]["ETag"]}

    def list_objects_v2(self, **params):
        self._pipeline("ListObjectsV2", params)
        prefix = params["Prefix"]
        return {"Contents": [{"Key": key, "Size": len(item["body"])} for key, item in sorted(self.objects.items())
                             if key.startswith(prefix)], "IsTruncated": False}

    def put_keys(self):
        return [key for key, _ in self.puts]


def factory_for(fake, created=None):
    def factory(config, guard):
        if created is not None:
            created.append(guard)
        guard.install(fake)
        return fake
    return factory


# --- Fake anonymous HTTPS -------------------------------------------------------------

class FakeHttp:
    """Public custom-domain reads come from the fake bucket; GitHub from `routes`."""

    def __init__(self, s3=None):
        self.s3 = s3
        self.routes = {}
        self.calls = []
        self.hits = {}
        self.lock = threading.Lock()

    def request(self, method, url, *, limit, headers=None, keep_body=True):
        with self.lock:
            self.calls.append((method, url))
        route = self.routes.get((method, url)) or self.routes.get(url)
        if callable(route):
            route = route(method, headers or {})
        if route is not None:
            status, response_headers, body = route
        elif url.startswith(r2.PUBLIC_ORIGIN) and self.s3 is not None:
            item = self.s3.objects.get(url[len(r2.PUBLIC_ORIGIN):])
            if item is None:
                return up.HttpResponse(404, {"cf-cache-status": "MISS"})
            body = item["body"]
            cache = "DYNAMIC"
            if url.endswith(".bin") and method == "GET":
                with self.lock:
                    cache = "HIT" if self.hits.get(url) else "MISS"
                    self.hits[url] = True
            status, response_headers = 200, {"content-length": str(len(body)), "cf-cache-status": cache,
                                             "etag": item["ETag"]}
            ranged = (headers or {}).get("Range")
            if ranged and method == "GET":
                start, end = map(int, ranged[len("bytes="):].split("-"))
                body = body[start:end + 1]
                status = 206
                response_headers["content-range"] = f"bytes {start}-{end}/{len(item['body'])}"
        else:
            return up.HttpResponse(404, {})
        if method == "HEAD":
            return up.HttpResponse(status, {"content-length": str(len(body)), **response_headers})
        if len(body) > limit:
            raise up.UploadError("http-too-large", url)
        return up.HttpResponse(status, response_headers, body if keep_body else b"", sha(body), len(body))


# --- Content fixtures -------------------------------------------------------------------

def version_for(platform="windows", commit=COMMIT):
    return f"RabbitLands-{platform.capitalize()}-20261104-{commit[:9]}"


def make_set(parts, *, pem=COMMITTED_PEM, platform="windows"):
    names = [("release-descriptor", "app/client-release.json"), ("client", "app/RabbitLands.pck")]
    names += [(f"records-{index:02d}", f"app/data/items-{index}.json") for index in range(2, len(parts))]
    packages = [{"id": pid, "sha256": digest, "size": size, "unpacked_size": 10, "file_count": 1,
                 "files": [{"path": path, "size": 10, "sha256": "c" * 64}],
                 "parts": [{"url": r2.part_url(digest), "size": size, "sha256": digest}]}
                for (pid, path), (digest, size) in zip(names, parts)]
    return {"kind": r2.SET_KIND, "set_schema": 1, "source": "r2", "repository": r2.REPOSITORY, "commit": COMMIT,
            "platform": platform, "version": version_for(platform), "public_key_sha256": sha(pem),
            "asset_base": r2.DESKTOP_ASSETS, "ci_paths": [*r2.CI_PATHS, *r2.CI_PREFIXES], "packages": packages,
            "optional_packages": []}


def make_content(tmp_path, *, sizes=(3000, 5000, 7000), prefix=None, pem=COMMITTED_PEM, seed=1):
    root = tmp_path / "out"
    (root / "parts").mkdir(parents=True, exist_ok=True)
    generator = random.Random(seed)
    parts = []
    for size in sizes:
        data = generator.randbytes(size)
        digest = sha(data)
        path = root / "parts" / f"RabbitLands-pkg-{digest}.zip.part"
        path.write_bytes(data)
        parts.append(types.SimpleNamespace(sha256=digest, size=size, path=path, data=data,
                                           key=r2.part_key(digest, prefix=prefix)))
    content_set = make_set([(part.sha256, part.size) for part in parts], pem=pem)
    set_bytes = r2.canonical_bytes(content_set)
    (root / "set.json").write_bytes(set_bytes)
    plan = {"kind": up.PLAN_KIND, "plan_schema": 1, "platform": "windows", "set_sha256": sha(set_bytes),
            "set_bytes_path": "set.json",
            "rows": [{"key": part.key, "sha256": part.sha256, "size": part.size, "kind": "new",
                      "local_path": f"parts/{part.path.name}"} for part in parts]}
    plan_path = root / "upload-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2))
    return types.SimpleNamespace(root=root, plan_path=plan_path, plan=plan, parts=parts, set_bytes=set_bytes,
                                 set_sha256=sha(set_bytes), set_key=r2.set_key("windows", sha(set_bytes), prefix=prefix))


def save_plan(content):
    content.plan_path.write_text(json.dumps(content.plan, indent=2))


def receipt_of(path):
    return json.loads(Path(path).read_text())


def run_content(content, credentials, tmp_path, fake, *, created=None, **options):
    receipt = tmp_path / "receipts" / "content.json"
    try:
        return up.run_content(content.plan_path, credentials, receipt, client_factory=factory_for(fake, created),
                              **options), receipt_of(receipt)
    except r2.DesktopR2Error as error:
        error.receipt = receipt_of(receipt) if receipt.exists() else None
        raise


# --- Content mode ------------------------------------------------------------------------

def test_content_uploads_every_part_then_the_set_last(tmp_path, credentials):
    content = make_content(tmp_path)
    fake = FakeS3()
    result, receipt = run_content(content, credentials, tmp_path, fake)
    keys = fake.put_keys()
    assert sorted(keys[:-1]) == sorted(part.key for part in content.parts) and keys[-1] == content.set_key
    for key, params in fake.puts:
        assert params["IfNoneMatch"] == "*" and "IfMatch" not in params
        assert params["CacheControl"] == r2.IMMUTABLE_CACHE_CONTROL
        assert base64.b64decode(params["ChecksumSHA256"]).hex() == params["Metadata"]["sha256"]
    # Every PUT is followed by a verifying HEAD of the same key.
    for key in keys:
        index = fake.calls.index(("PutObject", key))
        assert ("HeadObject", key) in fake.calls[index + 1:]
    assert result["counts"] == {"uploaded": 4, "resumed": 0, "reused": 0}
    assert {row["result"] for row in receipt["objects"]} == {"uploaded"} and receipt["failures"] == []
    assert receipt["set_key"] == content.set_key and receipt["bucket"] == r2.BUCKET
    assert fake.objects[content.set_key]["ContentType"] == "application/json"


def test_corrupt_new_row_means_no_client_is_created(tmp_path, credentials):
    content = make_content(tmp_path)
    bad = content.parts[1].path
    bad.write_bytes(bytes(byte ^ 1 for byte in bad.read_bytes()))
    fake, created = FakeS3(), []
    with pytest.raises(up.UploadError) as caught:
        run_content(content, credentials, tmp_path, fake, created=created)
    assert caught.value.code == "plan-local-rows"
    assert created == [] and fake.calls == []
    assert caught.value.receipt["failures"] == [{"key": content.parts[1].key, "error_code": "local-sha256"}]


@pytest.mark.parametrize("damage", ["missing", "size"])
def test_missing_or_resized_new_row_means_no_client(tmp_path, credentials, damage):
    content = make_content(tmp_path)
    if damage == "missing":
        content.parts[0].path.unlink()
    else:
        content.parts[0].path.write_bytes(b"short")
    fake, created = FakeS3(), []
    with pytest.raises(up.UploadError):
        run_content(content, credentials, tmp_path, fake, created=created)
    assert created == [] and fake.calls == []


def test_absent_reused_row_is_refused_and_never_uploaded(tmp_path, credentials):
    content = make_content(tmp_path)
    row = content.plan["rows"][0]
    content.plan["rows"][0] = {"key": row["key"], "sha256": row["sha256"], "size": row["size"], "kind": "reused"}
    save_plan(content)
    fake = FakeS3()
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake)
    assert row["key"] not in fake.put_keys() and content.set_key not in fake.put_keys()
    assert {"key": row["key"], "error_code": "reused-missing"} in fake_receipt_failures(tmp_path)


def fake_receipt_failures(tmp_path):
    return receipt_of(tmp_path / "receipts" / "content.json")["failures"]


def test_present_reused_row_is_head_checked_not_uploaded(tmp_path, credentials):
    content = make_content(tmp_path)
    part = content.parts[0]
    content.plan["rows"][0] = {"key": part.key, "sha256": part.sha256, "size": part.size, "kind": "reused"}
    save_plan(content)
    fake = FakeS3()
    fake.seed(part.key, part.data)
    result, receipt = run_content(content, credentials, tmp_path, fake)
    assert part.key not in fake.put_keys() and ("HeadObject", part.key) in fake.calls
    assert result["counts"]["reused"] == 1


def test_reused_row_with_other_bookkeeping_is_refused(tmp_path, credentials):
    content = make_content(tmp_path)
    part = content.parts[0]
    content.plan["rows"][0] = {"key": part.key, "sha256": part.sha256, "size": part.size, "kind": "reused"}
    save_plan(content)
    fake = FakeS3()
    fake.seed(part.key, part.data, metadata_sha="b" * 64)
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake)
    assert {"key": part.key, "error_code": "reused-mismatch"} in fake_receipt_failures(tmp_path)


def test_rerun_after_release_local_parts_works(tmp_path, credentials):
    content = make_content(tmp_path)
    fake = FakeS3()
    result, receipt = run_content(content, credentials, tmp_path, fake, release=True)
    assert receipt["released_local_parts"] == {"files": 3, "bytes": 15000}
    assert not any(part.path.exists() for part in content.parts)
    rewritten = json.loads(content.plan_path.read_text())
    assert {row["kind"] for row in rewritten["rows"]} == {"reused"} and all("local_path" not in row for row in rewritten["rows"])
    puts = len(fake.puts)
    result, receipt = run_content(content, credentials, tmp_path, fake)
    assert len(fake.puts) == puts
    assert result["counts"] == {"uploaded": 0, "resumed": 1, "reused": 3}


def test_release_local_parts_waits_for_a_complete_upload(tmp_path, credentials):
    content = make_content(tmp_path)
    fake = FakeS3()
    fake.seed(content.parts[2].key, b"other bytes")
    before = content.plan_path.read_text()
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake, release=True)
    assert all(part.path.exists() for part in content.parts) and content.plan_path.read_text() == before


def test_matching_objects_are_resumed_without_put(tmp_path, credentials):
    content = make_content(tmp_path)
    fake = FakeS3()
    for part in content.parts:
        fake.seed(part.key, part.data)
    fake.seed(content.set_key, content.set_bytes)
    result, _ = run_content(content, credentials, tmp_path, fake)
    assert fake.puts == [] and result["counts"] == {"uploaded": 0, "resumed": 4, "reused": 0}


@pytest.mark.parametrize("difference", ["sha256", "length", "content-type"])
def test_existing_differing_object_is_a_conflict_and_never_overwritten(tmp_path, credentials, difference):
    content = make_content(tmp_path)
    part = content.parts[0]
    fake = FakeS3()
    if difference == "sha256":
        fake.seed(part.key, part.data, metadata_sha="b" * 64)
    elif difference == "length":
        fake.seed(part.key, part.data + b"x", metadata_sha=part.sha256)
    else:
        fake.seed(part.key, part.data, content_type="application/zip")
    before = dict(fake.objects[part.key])
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake)
    assert fake.objects[part.key] == before and part.key not in fake.put_keys()
    assert content.set_key not in fake.objects
    assert {"key": part.key, "error_code": "conflict"} in fake_receipt_failures(tmp_path)


def test_412_then_rehead_resumes_an_equal_object(tmp_path, credentials):
    content = make_content(tmp_path)
    part = content.parts[0]
    fake = FakeS3()
    fake.seed(part.key, part.data)
    fake.hide_once.add(part.key)  # the first HEAD misses it: another writer is racing
    result, receipt = run_content(content, credentials, tmp_path, fake)
    heads = [call for call in fake.calls if call == ("HeadObject", part.key)]
    assert len(heads) == 2 and part.key not in fake.put_keys()
    assert {"key": part.key, "bytes": part.size, "sha256": part.sha256, "result": "resumed"} in receipt["objects"]


def test_412_then_rehead_refuses_a_different_object(tmp_path, credentials):
    content = make_content(tmp_path)
    part = content.parts[0]
    fake = FakeS3()
    fake.seed(part.key, b"someone else's bytes")
    fake.hide_once.add(part.key)
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake)
    assert fake.objects[part.key]["body"] == b"someone else's bytes"
    assert {"key": part.key, "error_code": "conflict"} in fake_receipt_failures(tmp_path)


def test_verify_after_put_catches_a_bad_object(tmp_path, credentials):
    content = make_content(tmp_path)
    part = content.parts[0]
    fake = FakeS3()
    original = fake.put_object

    def corrupt(**params):
        result = original(**params)
        if params["Key"] == part.key:
            fake.objects[part.key]["Metadata"]["sha256"] = "e" * 64
        return result
    fake.put_object = corrupt
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake)
    assert {"key": part.key, "error_code": "verify-failed"} in fake_receipt_failures(tmp_path)
    assert content.set_key not in fake.objects


def test_set_is_not_uploaded_when_any_part_fails(tmp_path, credentials):
    content = make_content(tmp_path)
    fake = FakeS3()
    fake.inject[("PutObject", content.parts[1].key)] = lambda params: (_ for _ in ()).throw(client_error("InternalError", 500))
    with pytest.raises(up.IncompleteError):
        run_content(content, credentials, tmp_path, fake)
    assert content.set_key not in fake.put_keys()
    assert {"key": content.parts[1].key, "error_code": "PutObject:InternalError:500"} in fake_receipt_failures(tmp_path)


def test_no_checksum_header_escape(tmp_path, credentials):
    content = make_content(tmp_path)
    fake = FakeS3()
    run_content(content, credentials, tmp_path, fake, checksum_header=False)
    assert all("ChecksumSHA256" not in params for _, params in fake.puts)


@pytest.mark.parametrize("edit, code", [
    (lambda plan, parts: plan["rows"].append({**plan["rows"][0], "sha256": "d" * 64}), "plan-extra-row"),
    (lambda plan, parts: plan["rows"].pop(), "plan-missing-part"),
    (lambda plan, parts: plan["rows"][0].update(size=plan["rows"][0]["size"] + 1), "plan-row-size"),
    (lambda plan, parts: plan["rows"][0].update(key=plan["rows"][0]["key"].replace(".bin", ".zip.part")), "plan-row-key"),
    (lambda plan, parts: plan["rows"][0].update(key="browser/assets/" + plan["rows"][0]["sha256"] + ".bin"), "plan-row-key"),
    (lambda plan, parts: plan["rows"][0].update(key=plan["rows"][0]["key"] + "\n"), "plan-row-key"),
    (lambda plan, parts: plan["rows"].append(dict(plan["rows"][0])), "plan-duplicate-row"),
    (lambda plan, parts: plan["rows"][0].update(kind="maybe"), "plan-row-shape"),
    (lambda plan, parts: plan["rows"][0].pop("local_path"), "plan-row-shape"),
    (lambda plan, parts: plan.update(set_sha256="f" * 64), "plan-set-sha256"),
    (lambda plan, parts: plan.update(platform="macos"), "plan-platform"),
    (lambda plan, parts: plan.update(extra=True), "plan-shape"),
    (lambda plan, parts: plan.update(kind="something-else"), "plan-kind"),
])
def test_plan_rows_must_be_exactly_the_sets_parts(tmp_path, credentials, edit, code):
    content = make_content(tmp_path)
    edit(content.plan, content.parts)
    save_plan(content)
    fake, created = FakeS3(), []
    with pytest.raises(up.UploadError) as caught:
        run_content(content, credentials, tmp_path, fake, created=created)
    assert caught.value.code == code and created == [] and fake.calls == []


def test_plan_set_must_validate_as_an_r2_set(tmp_path, credentials):
    content = make_content(tmp_path)
    content_set = json.loads(content.set_bytes)
    content_set["source"] = "ci"
    data = r2.canonical_bytes(content_set)
    (content.root / "set.json").write_bytes(data)
    content.plan["set_sha256"] = sha(data)
    save_plan(content)
    with pytest.raises(r2.SetError):
        run_content(content, credentials, tmp_path, FakeS3())


def test_selftest_keys_are_refused_in_a_production_plan(tmp_path, credentials):
    content = make_content(tmp_path, prefix="desktop/selftest/20261104-0a1b2c3d/")
    with pytest.raises(up.UploadError) as caught:
        run_content(content, credentials, tmp_path, FakeS3())
    assert caught.value.code == "plan-row-key"


def test_workers_are_capped_at_four(tmp_path, credentials):
    content = make_content(tmp_path)
    with pytest.raises(up.UploadError) as caught:
        run_content(content, credentials, tmp_path, FakeS3(), workers=5)
    assert caught.value.code == "workers"
    with pytest.raises(SystemExit) as exited:
        up.build_parser().parse_args(["content", "--plan", "p", "--credentials", "c", "--receipt", "r", "--workers", "5"])
    assert exited.value.code == 2
    for mode in ("publish", "selftest", "verify-public"):
        assert any(action.dest == "workers" and list(action.choices) == [1, 2, 3, 4]
                   for action in up.build_parser()._subparsers._group_actions[0].choices[mode]._actions)


def git_repository(path):
    path.mkdir(parents=True, exist_ok=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=environment)
    return path


def test_receipt_inside_a_worktree_is_refused_unless_ignored(tmp_path, credentials):
    content = make_content(tmp_path)
    repository = git_repository(tmp_path / "repo")
    fake, created = FakeS3(), []
    with pytest.raises(up.UploadError) as caught:
        up.run_content(content.plan_path, credentials, repository / "receipt.json", client_factory=factory_for(fake, created))
    assert caught.value.code == "receipt-location" and created == [] and not (repository / "receipt.json").exists()
    (repository / ".gitignore").write_text("ignored/\n")
    (repository / "ignored").mkdir()
    result = up.run_content(content.plan_path, credentials, repository / "ignored" / "receipt.json",
                            client_factory=factory_for(fake))
    assert result["ok"] and (repository / "ignored" / "receipt.json").is_file()


def test_plan_inside_an_unignored_worktree_is_refused(tmp_path, credentials):
    repository = git_repository(tmp_path / "repo")
    content = make_content(repository)
    with pytest.raises(up.UploadError) as caught:
        run_content(content, credentials, tmp_path, FakeS3())
    assert caught.value.code == "plan-location"


# --- SDK guard (pure handler checks) ------------------------------------------------------

def guard(selftest=False):
    return up.SdkGuard(bucket=r2.BUCKET, selftest=selftest)


PART_KEY = f"desktop/v1/parts/{SHA_A}.bin"
POINTER_KEY = "desktop/v1/channels/live/windows.json"


def put_params(key=PART_KEY, **extra):
    return {"Bucket": r2.BUCKET, "Key": key, "Body": b"x", "ContentLength": 1, "ContentType": "application/octet-stream",
            "CacheControl": r2.IMMUTABLE_CACHE_CONTROL, "Metadata": {"sha256": SHA_A}, **extra}


@pytest.mark.parametrize("operation", ["DeleteObject", "DeleteObjects", "CopyObject", "UploadPart", "UploadPartCopy",
                                       "CreateMultipartUpload", "CompleteMultipartUpload", "AbortMultipartUpload",
                                       "PutBucketLifecycleConfiguration", "PutBucketCors", "PutObjectAcl",
                                       "PutBucketPolicy", "RenameObject", "RestoreObject", "ListObjects",
                                       "ListMultipartUploads", "PutObjectRetention", "DeleteBucket", None, 7])
def test_guard_refuses_every_other_operation(operation):
    with pytest.raises(up.GuardError) as caught:
        guard().inspect(operation, {"Bucket": r2.BUCKET, "Key": PART_KEY})
    assert caught.value.code == "sdk-operation"


@pytest.mark.parametrize("key", [
    "browser/assets/" + SHA_A + ".zip", "browser/licenses/godot-cpp-LICENSE.md", "desktop/v1/parts/" + SHA_A + ".zip.part",
    "desktop/v1/parts/../../browser/assets/x.bin", PART_KEY + "\n", PART_KEY.upper(), "desktop/v2/parts/" + SHA_A + ".bin",
    "desktop/selftest/20261104-0a1b2c3d/parts/" + SHA_A + ".bin", "", None, b"desktop/v1/parts/x.bin",
])
def test_guard_refuses_keys_that_fail_the_production_guard(key):
    for operation in ("HeadObject", "GetObject"):
        with pytest.raises(up.GuardError) as caught:
            guard().inspect(operation, {"Bucket": r2.BUCKET, "Key": key})
        assert caught.value.code == "sdk-key"
    with pytest.raises(up.GuardError):
        guard().inspect("PutObject", put_params(key=key, IfNoneMatch="*"))


def test_selftest_guard_admits_only_its_prefix():
    selftest_key = f"desktop/selftest/20261104-0a1b2c3d/parts/{SHA_A}.bin"
    assert guard(selftest=True).inspect("HeadObject", {"Bucket": r2.BUCKET, "Key": selftest_key})["key"] == selftest_key
    for key in (PART_KEY, POINTER_KEY, "browser/assets/" + SHA_A + ".bin"):
        with pytest.raises(up.GuardError):
            guard(selftest=True).inspect("HeadObject", {"Bucket": r2.BUCKET, "Key": key})
    with pytest.raises(up.GuardError):
        guard(selftest=True).inspect("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": "desktop/v1/"})


@pytest.mark.parametrize("extra", [{}, {"IfMatch": '"abc"'}, {"IfNoneMatch": "*", "IfMatch": '"abc"'},
                                   {"IfNoneMatch": "etag"}, {"IfNoneMatch": ""}])
def test_guard_refuses_immutable_puts_without_if_none_match(extra):
    with pytest.raises(up.GuardError) as caught:
        guard().inspect("PutObject", put_params(**extra))
    assert caught.value.code == "sdk-unconditional-put"


@pytest.mark.parametrize("extra", [{}, {"IfNoneMatch": "*", "IfMatch": '"abc"'}, {"IfMatch": "abc"},
                                   {"IfMatch": '"a b"'}, {"IfMatch": ""}])
def test_guard_requires_a_condition_on_pointer_puts(extra):
    with pytest.raises(up.GuardError) as caught:
        guard().inspect("PutObject", put_params(key=POINTER_KEY, **extra))
    assert caught.value.code == "sdk-pointer-condition"
    assert guard().inspect("PutObject", put_params(key=POINTER_KEY, IfMatch='"abc"'))["condition"] == ("if-match", '"abc"')
    assert guard().inspect("PutObject", put_params(key=POINTER_KEY, IfNoneMatch="*"))["condition"] == ("if-none-match", "*")


@pytest.mark.parametrize("operation, params, code", [
    ("PutObject", put_params(IfNoneMatch="*", ACL="public-read"), "sdk-parameter"),
    ("PutObject", put_params(IfNoneMatch="*", ContentLength=r2.MAX_PART_BYTES + 1), "sdk-length"),
    ("PutObject", put_params(IfNoneMatch="*", ContentLength=0), "sdk-length"),
    ("PutObject", put_params(key=POINTER_KEY, IfNoneMatch="*", ContentLength=r2.MAX_POINTER_BYTES + 1), "sdk-length"),
    ("GetObject", {"Bucket": r2.BUCKET, "Key": PART_KEY, "ResponseContentType": "text/html"}, "sdk-parameter"),
    ("GetObject", {"Bucket": r2.BUCKET, "Key": PART_KEY, "Range": "bytes=0-1,5-6"}, "sdk-parameter"),
    ("HeadObject", {"Bucket": "another-bucket", "Key": PART_KEY}, "sdk-bucket"),
    ("HeadObject", {"Bucket": r2.BUCKET, "Key": PART_KEY, "ChecksumMode": "DISABLED"}, "sdk-parameter"),
    ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": "browser/"}, "sdk-key"),
    ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": ""}, "sdk-key"),
    ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": "desktop/", "Delimiter": "/"}, "sdk-parameter"),
    ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": "desktop/", "EncodingType": "xml"}, "sdk-parameter"),
])
def test_guard_refuses_unexpected_parameters(operation, params, code):
    with pytest.raises(up.GuardError) as caught:
        guard().inspect(operation, params)
    assert caught.value.code == code


def test_guard_admits_the_encoding_type_botocore_adds_to_listings():
    mark = guard().inspect("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": "desktop/", "EncodingType": "url"})
    assert mark == {"operation": "ListObjectsV2", "prefix": "desktop/"}


def test_selftest_guard_bound_to_its_prefix_refuses_other_nonces():
    mine, other = "desktop/selftest/20261104-0a1b2c3d/", "desktop/selftest/20261104-ffffffff/"
    bound = up.SdkGuard(bucket=r2.BUCKET, selftest=True, prefix=mine)
    assert bound.inspect("HeadObject", {"Bucket": r2.BUCKET, "Key": f"{mine}parts/{SHA_A}.bin"})["key"].startswith(mine)
    assert bound.inspect("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": mine})["prefix"] == mine
    for operation, params in (("HeadObject", {"Bucket": r2.BUCKET, "Key": f"{other}parts/{SHA_A}.bin"}),
                              ("PutObject", put_params(key=f"{other}parts/{SHA_A}.bin", IfNoneMatch="*")),
                              ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": r2.SELFTEST_ROOT}),
                              ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": other})):
        with pytest.raises(up.GuardError) as caught:
            bound.inspect(operation, params)
        assert caught.value.code == "sdk-key"
    for prefix in ("desktop/v1/", r2.SELFTEST_ROOT, mine[:-1], mine + "x/", "desktop/selftest/2026-0a1b2c3d/", 7):
        with pytest.raises(up.GuardError):
            up.SdkGuard(bucket=r2.BUCKET, selftest=True, prefix=prefix)
    with pytest.raises(up.GuardError):
        up.SdkGuard(bucket=r2.BUCKET, prefix=mine)


def test_guard_before_call_refuses_unchecked_or_altered_requests():
    item = guard()
    context = {}
    item.check_parameters(params=put_params(IfNoneMatch="*"), model=FakeModel("PutObject"), context=context)
    good = {"method": "PUT", "url_path": "/" + PART_KEY, "headers": {"If-None-Match": "*"}}
    item.check_request(model=FakeModel("PutObject"), params=good, context=context)
    for model, params, ctx in [
        (FakeModel("PutObject"), good, {}),                                                    # never checked
        (FakeModel("DeleteObject"), good, context),                                            # another operation
        (FakeModel("PutObject"), {**good, "method": "DELETE"}, context),
        (FakeModel("PutObject"), {**good, "url_path": "/browser/assets/x.bin"}, context),
        (FakeModel("PutObject"), {**good, "headers": {}}, context),                            # condition dropped
        (FakeModel("PutObject"), {**good, "headers": {"If-None-Match": "*", "If-Match": '"x"'}}, context),
    ]:
        with pytest.raises(up.GuardError):
            item.check_request(model=model, params=params, context=ctx)


def test_guard_is_bound_to_the_desktop_bucket():
    with pytest.raises(up.GuardError):
        up.SdkGuard(bucket="other-bucket")


# --- Real botocore: the guard on the real pipeline, answered in-process ------------------------

class R2Emulator:
    """A before-send handler that answers botocore requests like R2 (no network)."""

    def __init__(self, fail=None):
        self.objects = {}
        self.sent = []
        self.fail = fail
        self.hide_once = set()

    def __call__(self, request, **_):
        from botocore.awsrequest import AWSResponse
        self.sent.append((request.method, request.url))
        if self.fail is not None:
            raise self.fail(request)
        parts = urllib.parse.urlsplit(request.url)
        path = urllib.parse.unquote(parts.path)
        key = path[len(f"/{r2.BUCKET}/"):]
        headers = {name.lower(): (value.decode() if isinstance(value, bytes) else value)
                   for name, value in request.headers.items()}

        def respond(status, response_headers=None, body=b""):
            raw = types.SimpleNamespace(stream=lambda **kw: iter([body]), read=io.BytesIO(body).read, close=lambda: None)
            return AWSResponse(request.url, status, {"Content-Length": str(len(body)), **(response_headers or {})}, raw)

        def error(code, status):
            body = f'<?xml version="1.0"?><Error><Code>{code}</Code><Message>m</Message></Error>'.encode()
            return respond(status, {"Content-Type": "application/xml"}, body)
        if request.method == "GET" and "list-type=2" in parts.query.split("&"):
            query = urllib.parse.parse_qs(parts.query)
            prefix = query.get("prefix", [""])[0]
            rows = "".join(f"<Contents><Key>{urllib.parse.quote(name, safe='')}</Key><Size>{len(item['body'])}</Size>"
                           "</Contents>" for name, item in sorted(self.objects.items()) if name.startswith(prefix))
            body = (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult><Name>{r2.BUCKET}</Name>'
                    f"<Prefix>{urllib.parse.quote(prefix, safe='')}</Prefix><EncodingType>url</EncodingType>"
                    f"<IsTruncated>false</IsTruncated>{rows}</ListBucketResult>").encode()
            return respond(200, {"Content-Type": "application/xml"}, body)
        item = None if key in self.hide_once else self.objects.get(key)
        self.hide_once.discard(key)
        if request.method == "HEAD":
            if item is None:
                return respond(404)
            return respond(200, {"Content-Length": str(len(item["body"])), "ETag": item["etag"], **item["headers"]})
        if request.method == "GET":
            if item is None:
                return error("NoSuchKey", 404)
            if "range" in headers:
                start, end = map(int, headers["range"][len("bytes="):].split("-"))
                return respond(206, {"ETag": item["etag"], "Content-Range": f"bytes {start}-{end}/{len(item['body'])}"},
                               item["body"][start:end + 1])
            return respond(200, {"ETag": item["etag"]}, item["body"])
        if request.method == "PUT":
            body = request.body if isinstance(request.body, bytes) else request.body.read()
            existing = self.objects.get(key)
            if headers.get("if-none-match") == "*" and existing is not None:
                return error("PreconditionFailed", 412)
            if "if-match" in headers and (existing is None or existing["etag"] != headers["if-match"]):
                return error("PreconditionFailed", 412)
            kept = {name: value for name, value in headers.items()
                    if name.startswith("x-amz-meta-") or name in ("content-type", "cache-control")}
            self.objects[key] = {"body": body, "etag": '"' + hashlib.md5(body).hexdigest() + '"', "headers": kept}
            return respond(200, {"ETag": self.objects[key]["etag"]})
        raise AssertionError(request.method)


def real_client(credentials, emulator, *, selftest=False, budget=None, prefix=None):
    config = up.load_config(credentials)
    client = up.create_client(config, up.SdkGuard(bucket=r2.BUCKET, selftest=selftest, budget=budget, prefix=prefix),
                              attempts=1)
    client.meta.events.register("before-send.s3", emulator)
    return client


@needs_botocore
def test_real_botocore_selftest_reads_pass_the_bound_guard(credentials):
    """The listing, checksum HEAD and ranged GET the self-test makes, on the real request pipeline."""
    prefix = "desktop/selftest/20261104-0a1b2c3d/"
    key = f"{prefix}parts/{SHA_A}.bin"
    emulator = R2Emulator()
    emulator.objects[key] = {"body": b"0123456789", "etag": '"e1"', "headers": {}}
    emulator.objects[f"desktop/selftest/20261104-ffffffff/parts/{SHA_A}.bin"] = {"body": b"x", "etag": '"e2"',
                                                                                 "headers": {}}
    bucket = up.Bucket(real_client(credentials, emulator, selftest=True, prefix=prefix), selftest=True)
    assert bucket.list(prefix) == [{"key": key, "size": 10}]
    assert bucket.head(key, checksum=True)["ContentLength"] == 10
    assert bucket.get(key, 10, byte_range="bytes=0-3")[0] == b"0123"
    sent = len(emulator.sent)
    for call in (lambda: bucket.list(r2.SELFTEST_ROOT),
                 lambda: bucket.head(f"desktop/selftest/20261104-ffffffff/parts/{SHA_A}.bin")):
        with pytest.raises(up.GuardError):
            call()
    assert len(emulator.sent) == sent


@needs_botocore
@pytest.mark.parametrize("call", [
    lambda c: c.delete_object(Bucket=r2.BUCKET, Key=PART_KEY),
    lambda c: c.delete_objects(Bucket=r2.BUCKET, Delete={"Objects": [{"Key": PART_KEY}]}),
    lambda c: c.copy_object(Bucket=r2.BUCKET, Key=PART_KEY, CopySource={"Bucket": r2.BUCKET, "Key": "browser/x"}),
    lambda c: c.create_multipart_upload(Bucket=r2.BUCKET, Key=PART_KEY),
    lambda c: c.put_bucket_lifecycle_configuration(Bucket=r2.BUCKET, LifecycleConfiguration={"Rules": []}),
    lambda c: c.put_bucket_cors(Bucket=r2.BUCKET, CORSConfiguration={"CORSRules": []}),
    lambda c: c.list_objects_v2(Bucket=r2.BUCKET, Prefix="browser/"),
    lambda c: c.head_object(Bucket=r2.BUCKET, Key="browser/assets/" + SHA_A + ".zip"),
    lambda c: c.get_object(Bucket=r2.BUCKET, Key=PART_KEY + "\n"),
    lambda c: c.put_object(Bucket=r2.BUCKET, Key=PART_KEY, Body=b"x", ContentLength=1),
    lambda c: c.put_object(Bucket=r2.BUCKET, Key=POINTER_KEY, Body=b"x", ContentLength=1),
    lambda c: c.upload_fileobj(io.BytesIO(b"x"), r2.BUCKET, PART_KEY),
    lambda c: c.generate_presigned_url("delete_object", Params={"Bucket": r2.BUCKET, "Key": PART_KEY}),
])
def test_real_botocore_guard_refuses_before_any_request(credentials, call):
    emulator = R2Emulator()
    client = real_client(credentials, emulator)
    with pytest.raises(Exception) as caught:
        call(client)
    assert any(isinstance(item, up.GuardError) for item in chain(caught.value)) or isinstance(caught.value, up.GuardError)
    assert emulator.sent == []


@needs_botocore
def test_real_botocore_content_upload_resume_conflict_and_412(tmp_path, credentials):
    content = make_content(tmp_path)
    emulator = R2Emulator()
    factory = lambda config, guard: real_client(credentials, emulator)  # noqa: E731
    receipt = tmp_path / "receipts" / "real.json"
    result = up.run_content(content.plan_path, credentials, receipt, client_factory=factory)
    assert result["counts"]["uploaded"] == 4
    stored = emulator.objects[content.parts[0].key]
    assert stored["headers"]["x-amz-meta-sha256"] == content.parts[0].sha256
    assert stored["headers"]["cache-control"] == r2.IMMUTABLE_CACHE_CONTROL
    result = up.run_content(content.plan_path, credentials, receipt, client_factory=factory)
    assert result["counts"] == {"uploaded": 0, "resumed": 4, "reused": 0}
    emulator.hide_once.add(content.parts[1].key)
    sent = len(emulator.sent)
    result = up.run_content(content.plan_path, credentials, receipt, client_factory=factory)
    assert ("PUT", f"{ENDPOINT}/{r2.BUCKET}/{content.parts[1].key}") in emulator.sent[sent:]
    assert result["counts"]["resumed"] == 4
    emulator.objects[content.parts[2].key]["headers"]["x-amz-meta-sha256"] = "b" * 64
    with pytest.raises(up.IncompleteError):
        up.run_content(content.plan_path, credentials, receipt, client_factory=factory)
    assert {"key": content.parts[2].key, "error_code": "conflict"} in receipt_of(receipt)["failures"]


@needs_botocore
def test_real_botocore_pointer_if_match(credentials):
    emulator = R2Emulator()
    bucket = up.Bucket(real_client(credentials, emulator))
    up.put_pointer(bucket, POINTER_KEY, b'{"one":1}', sequence=SEQUENCE, condition={"IfNoneMatch": "*"})
    etag = emulator.objects[POINTER_KEY]["etag"]
    up.put_pointer(bucket, POINTER_KEY, b'{"two":2}', sequence=SEQUENCE + 1, condition={"IfMatch": etag})
    with pytest.raises(up.SdkError) as caught:
        up.put_pointer(bucket, POINTER_KEY, b'{"three":3}', sequence=SEQUENCE + 2, condition={"IfMatch": etag})
    assert caught.value.precondition_failed and caught.value.status == 412
    assert emulator.objects[POINTER_KEY]["body"] == b'{"two":2}'
    assert emulator.objects[POINTER_KEY]["headers"]["cache-control"] == r2.POINTER_CACHE_CONTROL


@needs_botocore
@pytest.mark.parametrize("kind", ["EndpointConnectionError", "SSLError", "ReadTimeoutError", "ConnectTimeoutError"])
def test_real_botocore_transport_errors_are_sanitized(tmp_path, credentials, capfd, kind):
    content = make_content(tmp_path)
    exception = getattr(botocore_exceptions, kind)
    emulator = R2Emulator(fail=lambda request: exception(endpoint_url=request.url, error=f"failure at {request.url}"))
    receipt = tmp_path / "receipts" / "real.json"
    with pytest.raises(up.IncompleteError) as caught:
        up.run_content(content.plan_path, credentials, receipt,
                       client_factory=lambda config, guard: real_client(credentials, emulator))
    assert emulator.sent, "the request reached the transport"
    assert_clean_exception(caught.value)
    out, err = capfd.readouterr()
    assert not leaked(out + err) and not leaked(receipt.read_text())
    assert {row["error_code"] for row in receipt_of(receipt)["failures"]} == {f"HeadObject:{kind}"}


# --- Leaks: injected SDK failures leave no secret anywhere -------------------------------

def transport_errors():
    url = f"{ENDPOINT}/{r2.BUCKET}/{PART_KEY}"
    if botocore_exceptions is not None:
        be = botocore_exceptions
        return [be.EndpointConnectionError(endpoint_url=url),
                be.SSLError(endpoint_url=url, error=f"certificate verify failed for {ACCOUNT}"),
                be.ReadTimeoutError(endpoint_url=url, error=f"read timeout {KEY_ID}"),
                be.ConnectTimeoutError(endpoint_url=url, error=f"connect timeout {SECRET}"),
                be.ClientError({"Error": {"Code": "AccessDenied", "Message": f"key {KEY_ID} account {ACCOUNT}"},
                                "ResponseMetadata": {"HTTPStatusCode": 403, "HostId": ACCOUNT}}, "PutObject"),
                be.ClientError({"Error": {"Code": ACCOUNT, "Message": SECRET}}, "PutObject")]

    def make(name, text):
        return type(name, (Exception,), {})(text)
    return [make("EndpointConnectionError", f'Could not connect to the endpoint URL: "{url}"'),
            make("SSLError", f"SSL validation failed for {url} {ACCOUNT}"),
            make("ReadTimeoutError", f'Read timeout on endpoint URL: "{url}" {KEY_ID}'),
            make("ConnectTimeoutError", f'Connect timeout on endpoint URL: "{url}" {SECRET}'),
            client_error("AccessDenied", 403, f"key {KEY_ID} account {ACCOUNT}"),
            client_error(ACCOUNT, 400, SECRET)]


ERROR_IDS = ["EndpointConnectionError", "SSLError", "ReadTimeoutError", "ConnectTimeoutError", "ClientError",
             "ClientErrorSecretCode"]


def install_fake_boto3(monkeypatch, error):
    boto3 = types.ModuleType("boto3")
    session = types.ModuleType("boto3.session")

    class Session:
        def client(self, *args, **kwargs):
            raise error
    session.Session = Session
    boto3.session = session
    botocore = types.ModuleType("botocore")
    config = types.ModuleType("botocore.config")
    config.Config = lambda **kwargs: kwargs
    botocore.config = config
    for name, module in (("boto3", boto3), ("boto3.session", session), ("botocore", botocore),
                         ("botocore.config", config)):
        monkeypatch.setitem(sys.modules, name, module)


def raiser(error):
    def hook(params):
        raise error
    return hook


@pytest.mark.parametrize("stage", ["create", "head", "put"])
@pytest.mark.parametrize("index", range(6), ids=ERROR_IDS)
def test_injected_sdk_failures_leak_nothing(tmp_path, credentials, capsys, monkeypatch, stage, index):
    error = transport_errors()[index]
    content = make_content(tmp_path)
    fake = FakeS3()
    if stage == "create":
        install_fake_boto3(monkeypatch, error)
    else:
        fake.inject["HeadObject" if stage == "head" else "PutObject"] = raiser(error)
        monkeypatch.setattr(up, "create_client", factory_for(fake))
    receipt = tmp_path / "receipts" / "leak.json"
    code = up.main(["content", "--plan", str(content.plan_path), "--credentials", str(credentials),
                    "--receipt", str(receipt)])
    out, err = capsys.readouterr()
    assert code != 0 and not leaked(out + err), leaked(out + err)
    assert not leaked(receipt.read_text())
    with pytest.raises(r2.DesktopR2Error) as caught:
        up.run_content(content.plan_path, credentials, receipt)
    assert_clean_exception(caught.value)
    assert not leaked(receipt.read_text())


@pytest.mark.parametrize("index", range(6), ids=ERROR_IDS)
def test_injected_failure_in_publish_leaks_nothing(tmp_path, credentials, capsys, monkeypatch, test_key, index):
    error = transport_errors()[index]
    world = publish_world(tmp_path, test_key, monkeypatch)
    world.fake.inject[("GetObject", POINTER_KEY)] = raiser(error)
    receipt = tmp_path / "receipts" / "publish.json"
    with pytest.raises(r2.DesktopR2Error) as caught:
        up.run_publish(TAG, ["windows"], credentials, receipt, http=world.http, client_factory=factory_for(world.fake))
    assert_clean_exception(caught.value)
    assert not leaked(receipt.read_text()) and not leaked(capsys.readouterr())
    assert POINTER_KEY not in world.fake.objects


def test_sdk_wrapper_raises_without_context():
    error = transport_errors()[0]

    def call():
        raise error
    with pytest.raises(up.SdkError) as caught:
        up._sdk("HeadObject", call)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert caught.value.error_code == "EndpointConnectionError"


def test_secret_error_codes_are_replaced():
    up._register_secrets(r2.R2Config(
        bucket=r2.BUCKET, public_base_url=None, endpoint_url=ENDPOINT, account_id=ACCOUNT, access_key_id=KEY_ID,
        secret_access_key=SECRET))
    with pytest.raises(up.SdkError) as caught:
        up._sdk("PutObject", raiser(client_error(ACCOUNT, 400, SECRET)), None)
    assert caught.value.error_code == "ClientError" and not leaked(str(caught.value))
    assert up.redact(f"x {ENDPOINT.upper()} y") == "x [redacted] y"


def test_malformed_configs_leak_nothing(tmp_path, capsys):
    content = make_content(tmp_path)
    bad = tmp_path / "private" / "bad.json"
    bad.parent.mkdir()
    bad.write_text(json.dumps({"endpoint_url": ENDPOINT + ":" + SECRET, "bucket": r2.BUCKET, "access_key_id": KEY_ID,
                               "secret_access_key": SECRET}))
    code = up.main(["content", "--plan", str(content.plan_path), "--credentials", str(bad),
                    "--receipt", str(tmp_path / "receipts" / "r.json")])
    out, err = capsys.readouterr()
    assert code == 2 and "config-endpoint" in err and not leaked(out + err)
    assert not leaked((tmp_path / "receipts" / "r.json").read_text())


def test_sdk_loggers_are_silenced(capfd):
    for name in up.SDK_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.propagate is False and any(isinstance(h, logging.NullHandler) for h in logger.handlers)
    logging.getLogger("urllib3.connectionpool").warning("Connection pool is full, discarding connection: %s",
                                                        f"{ACCOUNT}.r2.cloudflarestorage.com")
    logging.getLogger("botocore.endpoint").error("Sending http request to %s", ENDPOINT)
    out, err = capfd.readouterr()
    assert not leaked(out + err)


def test_no_sdk_debug_switch_or_machine_paths_in_the_tool():
    source = (TOOLS / "upload_desktop_assets.py").read_text()
    assert "--debug" not in source and "set_stream_logger" not in source and "logging.DEBUG" not in source
    for fragment in ("C:/", "C:\\", "/Users/", "AppData", "scratchpad", "worktrees/", ".local/browser-prototype"):
        assert fragment not in source


# --- AST allowlist of client methods ------------------------------------------------------

S3_CLIENT_METHODS = frozenset("""
abort_multipart_upload can_paginate close complete_multipart_upload copy copy_object create_bucket
create_bucket_metadata_configuration create_bucket_metadata_table_configuration create_multipart_upload create_session
delete_bucket delete_bucket_analytics_configuration delete_bucket_cors delete_bucket_encryption
delete_bucket_intelligent_tiering_configuration delete_bucket_inventory_configuration delete_bucket_lifecycle
delete_bucket_metadata_configuration delete_bucket_metadata_table_configuration delete_bucket_metrics_configuration
delete_bucket_ownership_controls delete_bucket_policy delete_bucket_replication delete_bucket_tagging
delete_bucket_website delete_object delete_object_annotation delete_object_tagging delete_objects
delete_public_access_block download_file download_fileobj generate_presigned_post generate_presigned_url
get_bucket_abac get_bucket_accelerate_configuration get_bucket_acl get_bucket_analytics_configuration get_bucket_cors
get_bucket_encryption get_bucket_intelligent_tiering_configuration get_bucket_inventory_configuration
get_bucket_lifecycle get_bucket_lifecycle_configuration get_bucket_location get_bucket_logging
get_bucket_metadata_configuration get_bucket_metadata_table_configuration get_bucket_metrics_configuration
get_bucket_notification get_bucket_notification_configuration get_bucket_ownership_controls get_bucket_policy
get_bucket_policy_status get_bucket_replication get_bucket_request_payment get_bucket_tagging get_bucket_versioning
get_bucket_website get_object get_object_acl get_object_annotation get_object_attributes get_object_legal_hold
get_object_lock_configuration get_object_retention get_object_tagging get_object_torrent get_paginator
get_public_access_block get_waiter head_bucket head_object list_bucket_analytics_configurations
list_bucket_intelligent_tiering_configurations list_bucket_inventory_configurations list_bucket_metrics_configurations
list_buckets list_directory_buckets list_multipart_uploads list_object_annotations list_object_versions list_objects
list_objects_v2 list_parts put_bucket_abac put_bucket_accelerate_configuration put_bucket_acl
put_bucket_analytics_configuration put_bucket_cors put_bucket_encryption put_bucket_intelligent_tiering_configuration
put_bucket_inventory_configuration put_bucket_lifecycle put_bucket_lifecycle_configuration put_bucket_logging
put_bucket_metrics_configuration put_bucket_notification put_bucket_notification_configuration
put_bucket_ownership_controls put_bucket_policy put_bucket_replication put_bucket_request_payment put_bucket_tagging
put_bucket_versioning put_bucket_website put_object put_object_acl put_object_annotation put_object_legal_hold
put_object_lock_configuration put_object_retention put_object_tagging put_public_access_block rename_object
restore_object select_object_content update_bucket_metadata_annotation_table_configuration
update_bucket_metadata_inventory_table_configuration update_bucket_metadata_journal_table_configuration
update_object_encryption upload_file upload_fileobj upload_part upload_part_copy write_get_object_response
_make_api_call _emit_api_params
""".split())
# Client attributes that perform no S3 operation (`close` also names file and body closes).
NEUTRAL = frozenset({"close", "can_paginate", "meta", "exceptions", "waiter_names"})


def s3_universe():
    names = set(S3_CLIENT_METHODS)
    if botocore_exceptions is not None:
        import botocore.session
        client = botocore.session.get_session().create_client(
            "s3", region_name="auto", endpoint_url="https://" + "0" * 32 + ".r2.cloudflarestorage.com",
            aws_access_key_id="AKIDEXAMPLE000000000", aws_secret_access_key="example-secret-0000000000")
        names |= {name for name in dir(client) if not name.startswith("__")}
    return frozenset(names - NEUTRAL)


def test_client_method_allowlist_in_the_tool_source():
    assert up.CLIENT_METHODS == {"head_object", "get_object", "put_object", "list_objects_v2"}
    tree = ast.parse((TOOLS / "upload_desktop_assets.py").read_text())
    universe = s3_universe()
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert attributes & universe == up.CLIENT_METHODS
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not (strings & (universe - up.CLIENT_METHODS))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr",
                                                                                              "delattr", "eval", "exec",
                                                                                              "__import__"):
            assert node.func.id == "getattr" and isinstance(node.args[1], ast.Constant), ast.dump(node)
            assert node.args[1].value not in universe
    assert not {name for name in attributes if "delete" in name.casefold() or name in ("unregister", "copy")}


# --- Publish -----------------------------------------------------------------------------------

def make_release(test_key, *, platform="windows", commit=COMMIT, sequence=SEQUENCE, pointer_sequence=None,
                 rollback=False, release_id=4242, parts=(), ancestors=None, set_sha256=SHA_A, sign_with=None,
                 schema=3):
    version = version_for(platform, commit)
    packages = [{"id": f"pkg-{index}", "sha256": digest, "size": len(data), "unpacked_size": 1, "file_count": 1,
                 "files": [{"path": f"app/p{index}.bin", "size": 1, "sha256": "c" * 64}],
                 "parts": [{"url": r2.part_url(digest), "size": len(data), "sha256": digest}]}
                for index, (digest, data) in enumerate(parts)]
    engine = "e" * 64
    packages.append({"id": "engine", "sha256": engine, "size": 1234, "unpacked_size": 1, "file_count": 1,
                     "files": [{"path": "app/RabbitLands.exe", "size": 1, "sha256": "c" * 64}],
                     "parts": [{"url": r2.github_pool_url(engine), "size": 1234, "sha256": engine}]})
    updater = {"url": f"{r2.GITHUB_DOWNLOADS}client-assets/RabbitLands-updater-{'9' * 64}.exe", "size": 4321,
               "sha256": "9" * 64}
    payload = {"schema": schema, "bootstrap_schema": 1, "repository": r2.REPOSITORY, "commit": commit,
               "ancestors": ancestors if ancestors is not None else [commit, PREVIOUS], "launch_args": [],
               "platform": platform, "version": version, "packages": packages,
               "parts": [part for package in packages for part in package["parts"]], "updater": updater,
               **r2.manifest_additions(platform=platform, sequence=sequence, helpers_fingerprint="d" * 64,
                                       root_files=[], source="r2", set_sha256=set_sha256)}
    manifest = up.sign_envelope(r2.canonical_bytes(payload), (sign_with or test_key).private)
    pointer_payload = r2.pointer_payload(platform=platform, sequence=pointer_sequence or sequence + 100,
                                         rollback=rollback, release_id=release_id, run_id=7, commit=commit,
                                         version=version, manifest_sequence=sequence, manifest_sha256=sha(manifest),
                                         manifest_size=len(manifest))
    pointer = up.sign_envelope(r2.pointer_bytes(pointer_payload, platform=platform), test_key.private)
    return types.SimpleNamespace(manifest=manifest, pointer=pointer, version=version, payload=payload,
                                 sequence=pointer_payload["sequence"], engine=engine, updater=updater)


def github_routes(http, release, *, tag=TAG, release_id=4242, latest=PREVIOUS, draft=False, prerelease=False,
                  platform="windows", visible=True):
    api = f"{up.GITHUB_API}repos/{r2.REPOSITORY}/releases"
    assets = [{"name": r2.pointer_asset_name(platform), "size": len(release.pointer), "state": "uploaded"},
              {"name": f"{release.version}-{platform}.json", "size": len(release.manifest), "state": "uploaded"}]
    record = {"id": release_id, "tag_name": tag, "draft": draft, "prerelease": prerelease, "assets": assets}
    http.routes[f"{api}/tags/{tag}"] = (200, {}, json.dumps(record).encode()) if visible else (404, {}, b"")
    http.routes[f"{api}/latest"] = (200, {}, json.dumps({"id": 1, "tag_name": f"client-{latest}", "draft": False,
                                                         "prerelease": False, "assets": []}).encode())
    http.routes[f"{r2.GITHUB_DOWNLOADS}{tag}/{r2.pointer_asset_name(platform)}"] = (200, {}, release.pointer)
    http.routes[f"{r2.GITHUB_DOWNLOADS}{tag}/{release.version}-{platform}.json"] = (200, {}, release.manifest)
    http.routes[("HEAD", r2.github_pool_url(release.engine))] = (200, {"content-length": "1234"}, b"")
    http.routes[("HEAD", release.updater["url"])] = (200, {"content-length": "4321"}, b"")


def publish_world(tmp_path, test_key, monkeypatch, **options):
    monkeypatch.setattr(up, "committed_public_key", lambda: test_key.public)
    fake = FakeS3()
    data = [random.Random(index).randbytes(1000 + index) for index in range(3)]
    parts = [(sha(item), item) for item in data]
    for digest, item in parts:
        fake.seed(r2.part_key(digest), item)
    set_bytes = b'{"set":true}'
    fake.seed(r2.set_key("windows", sha(set_bytes)), set_bytes)
    release = make_release(test_key, parts=parts, set_sha256=sha(set_bytes), **options)
    http = FakeHttp(fake)
    github_routes(http, release)
    return types.SimpleNamespace(fake=fake, http=http, release=release, parts=parts, set_bytes=set_bytes)


def publish(world, credentials, tmp_path, *, rollback=False, receipt="publish.json"):
    return up.run_publish(TAG, ["windows"], credentials, tmp_path / "receipts" / receipt, rollback=rollback,
                          http=world.http, client_factory=factory_for(world.fake))


def test_publish_first_pointer_with_if_none_match(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    result = publish(world, credentials, tmp_path)
    manifest_key = r2.manifest_key("windows", sha(world.release.manifest))
    puts = dict(world.fake.puts)
    assert list(puts) == [manifest_key, POINTER_KEY]
    assert puts[manifest_key]["IfNoneMatch"] == "*"
    assert puts[POINTER_KEY]["IfNoneMatch"] == "*" and "IfMatch" not in puts[POINTER_KEY]
    assert puts[POINTER_KEY]["CacheControl"] == "no-store"
    assert puts[POINTER_KEY]["Metadata"] == {"sha256": sha(world.release.pointer), "sequence": str(world.release.sequence)}
    assert world.fake.objects[POINTER_KEY]["body"] == world.release.pointer
    assert result["platforms"]["windows"]["result"] == "published"
    receipt = receipt_of(tmp_path / "receipts" / "publish.json")
    assert receipt["high_water"] == {"windows": world.release.sequence} and receipt["result"] == "complete"
    assert receipt["platforms"]["windows"]["public"]["pointer"]["status"] == 200
    assert ("GET", r2.pointer_url("windows")) in world.http.calls
    # Every R2 part was HEADed through S3 and the GitHub rows anonymously before any write.
    first_put = world.fake.calls.index(("PutObject", manifest_key))
    for digest, _ in world.parts:
        assert world.fake.calls.index(("HeadObject", r2.part_key(digest))) < first_put
    assert ("HEAD", r2.github_pool_url(world.release.engine)) in world.http.calls


def live_pointer(test_key, *, sequence, commit=PREVIOUS):
    release = make_release(test_key, commit=commit, sequence=sequence - 100, pointer_sequence=sequence)
    return release.pointer


def test_publish_replaces_a_live_pointer_with_if_match(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    old = live_pointer(test_key, sequence=world.release.sequence - 50)
    world.fake.seed(POINTER_KEY, old, sequence=world.release.sequence - 50)
    etag = world.fake.objects[POINTER_KEY]["ETag"]
    result = publish(world, credentials, tmp_path)
    params = dict(world.fake.puts)[POINTER_KEY]
    assert params["IfMatch"] == etag and "IfNoneMatch" not in params
    assert result["platforms"]["windows"]["previous_sequence"] == world.release.sequence - 50
    assert world.fake.objects[POINTER_KEY]["body"] == world.release.pointer


def test_publish_is_idempotent_on_a_byte_equal_live_pointer(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    publish(world, credentials, tmp_path)
    puts = len(world.fake.puts)
    result = publish(world, credentials, tmp_path)
    assert len(world.fake.puts) == puts
    assert result["platforms"]["windows"]["result"] == "already-live"


@pytest.mark.parametrize("case", ["not-published", "draft", "prerelease", "already-latest", "latest-not-ancestor",
                                  "rollback-flag", "rollback-not-latest", "release-id", "commit"])
def test_publish_refuses_wrong_release_state_and_writes_nothing(tmp_path, credentials, monkeypatch, test_key, case):
    options = {"release_id": 999} if case == "release-id" else {}
    if case == "commit":
        options = {"commit": PREVIOUS, "ancestors": [PREVIOUS]}
    if case == "latest-not-ancestor":
        options = {"ancestors": [COMMIT]}
    if case == "rollback-not-latest":
        options = {"rollback": True}
    world = publish_world(tmp_path, test_key, monkeypatch, **options)
    if case == "commit":
        github_routes(world.http, world.release)  # the asset of client-COMMIT names another commit
    if case in ("not-published", "draft", "prerelease", "already-latest"):
        github_routes(world.http, world.release, visible=case != "not-published", draft=case == "draft",
                      prerelease=case == "prerelease", latest=COMMIT if case == "already-latest" else PREVIOUS)
    rollback = case in ("rollback-flag", "rollback-not-latest")
    with pytest.raises(up.UploadError) as caught:
        publish(world, credentials, tmp_path, rollback=rollback)
    expected = {"not-published": "release-not-published", "draft": "release-draft", "prerelease": "release-prerelease",
                "already-latest": "release-already-latest", "latest-not-ancestor": "latest-not-ancestor",
                "rollback-flag": "rollback-mismatch", "rollback-not-latest": "release-not-latest",
                "release-id": "pointer-release-id", "commit": "pointer-commit"}[case]
    assert caught.value.code == expected
    assert world.fake.puts == [] and POINTER_KEY not in world.fake.objects


def test_publish_rollback_requires_github_latest_first(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch, rollback=True)
    github_routes(world.http, world.release, latest=COMMIT)
    old = live_pointer(test_key, sequence=world.release.sequence - 1)
    world.fake.seed(POINTER_KEY, old, sequence=world.release.sequence - 1)
    result = publish(world, credentials, tmp_path, rollback=True)
    assert result["platforms"]["windows"]["rollback"] is True


@pytest.mark.parametrize("case", ["garbage", "other-key", "stale", "equal-sequence", "below-receipt",
                                  "missing-with-receipt"])
def test_publish_refuses_bad_live_pointer_states(tmp_path, credentials, monkeypatch, test_key, other_key, case):
    world = publish_world(tmp_path, test_key, monkeypatch)
    sequence = world.release.sequence
    if case == "garbage":
        world.fake.seed(POINTER_KEY, b"<html>challenge</html>", sequence=sequence - 1)
    elif case == "other-key":
        forged = make_release(other_key, commit=PREVIOUS, sequence=sequence - 200, pointer_sequence=sequence - 1).pointer
        world.fake.seed(POINTER_KEY, forged, sequence=sequence - 1)
    elif case in ("stale", "equal-sequence"):
        newer = live_pointer(test_key, sequence=sequence + (10 if case == "stale" else 0))
        world.fake.seed(POINTER_KEY, newer, sequence=sequence)
    elif case == "below-receipt":
        world.fake.seed(POINTER_KEY, live_pointer(test_key, sequence=sequence - 20), sequence=sequence - 20)
    receipt = tmp_path / "receipts" / "publish.json"
    if case in ("below-receipt", "missing-with-receipt"):
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"kind": up.RECEIPT_KIND, "mode": "publish", "high_water": {"windows": sequence - 10}}))
    before = world.fake.objects.get(POINTER_KEY)
    with pytest.raises(up.UploadError) as caught:
        publish(world, credentials, tmp_path)
    assert caught.value.code == {"garbage": "live-pointer-unverifiable", "other-key": "live-pointer-unverifiable",
                                 "stale": "pointer-stale", "equal-sequence": "pointer-stale",
                                 "below-receipt": "live-pointer-rolled-back",
                                 "missing-with-receipt": "live-pointer-missing"}[case]
    assert world.fake.puts == [] and world.fake.objects.get(POINTER_KEY) == before
    if case in ("below-receipt", "missing-with-receipt"):
        assert receipt_of(receipt)["high_water"] == {"windows": sequence - 10}


@pytest.mark.parametrize("case", ["part-missing", "part-mismatch", "set-missing", "github-row", "manifest-conflict",
                                  "pointer-race", "manifest-signature", "manifest-hash", "pointer-signature"])
def test_publish_keeps_the_old_pointer_on_any_failure(tmp_path, credentials, monkeypatch, test_key, other_key, case):
    world = publish_world(tmp_path, test_key, monkeypatch,
                          **({"sign_with": other_key} if case == "manifest-signature" else {}))
    old = live_pointer(test_key, sequence=world.release.sequence - 5)
    world.fake.seed(POINTER_KEY, old, sequence=world.release.sequence - 5)
    manifest_key = r2.manifest_key("windows", sha(world.release.manifest))
    if case == "part-missing":
        del world.fake.objects[r2.part_key(world.parts[1][0])]
    elif case == "part-mismatch":
        world.fake.objects[r2.part_key(world.parts[1][0])]["Metadata"]["sha256"] = "b" * 64
    elif case == "set-missing":
        del world.fake.objects[r2.set_key("windows", sha(world.set_bytes))]
    elif case == "github-row":
        world.http.routes[("HEAD", world.release.updater["url"])] = (404, {}, b"")
    elif case == "manifest-conflict":
        world.fake.seed(manifest_key, b"other manifest bytes")
    elif case == "pointer-race":
        def race(params):
            world.fake.objects[POINTER_KEY]["ETag"] = '"' + "1" * 32 + '"'
        world.fake.inject[("PutObject", POINTER_KEY)] = race
    elif case == "manifest-hash":
        world.http.routes[f"{r2.GITHUB_DOWNLOADS}{TAG}/{world.release.version}-windows.json"] = (
            200, {}, world.release.manifest[:-2] + b" }")
    elif case == "pointer-signature":
        world.http.routes[f"{r2.GITHUB_DOWNLOADS}{TAG}/{r2.pointer_asset_name('windows')}"] = (
            200, {}, make_release(other_key, parts=world.parts, set_sha256=sha(world.set_bytes)).pointer)
    before = dict(world.fake.objects[POINTER_KEY])
    with pytest.raises(up.UploadError):
        publish(world, credentials, tmp_path)
    assert world.fake.objects[POINTER_KEY]["body"] == old and world.fake.objects[POINTER_KEY]["Metadata"] == before["Metadata"]
    assert POINTER_KEY not in world.fake.put_keys()


def two_platform_world(tmp_path, test_key, monkeypatch, *, linux_part_present=True):
    world = publish_world(tmp_path, test_key, monkeypatch)
    linux_data = b"linux-only part bytes"
    linux = make_release(test_key, platform="linux", parts=[(sha(linux_data), linux_data)],
                         set_sha256=sha(world.set_bytes))
    world.fake.seed(r2.set_key("linux", sha(world.set_bytes)), world.set_bytes)
    if linux_part_present:
        world.fake.seed(r2.part_key(sha(linux_data)), linux_data)
    api = f"{up.GITHUB_API}repos/{r2.REPOSITORY}/releases"
    assets = []
    for platform, release in (("windows", world.release), ("linux", linux)):
        assets += [{"name": r2.pointer_asset_name(platform), "size": len(release.pointer), "state": "uploaded"},
                   {"name": f"{release.version}-{platform}.json", "size": len(release.manifest), "state": "uploaded"}]
        world.http.routes[f"{r2.GITHUB_DOWNLOADS}{TAG}/{r2.pointer_asset_name(platform)}"] = (200, {}, release.pointer)
        world.http.routes[f"{r2.GITHUB_DOWNLOADS}{TAG}/{release.version}-{platform}.json"] = (200, {}, release.manifest)
    world.http.routes[f"{api}/tags/{TAG}"] = (200, {}, json.dumps({"id": 4242, "tag_name": TAG, "draft": False,
                                                                     "prerelease": False, "assets": assets}).encode())
    world.linux, world.linux_data = linux, linux_data
    return world


def test_publish_preflights_every_platform_before_any_write(tmp_path, credentials, monkeypatch, test_key):
    world = two_platform_world(tmp_path, test_key, monkeypatch, linux_part_present=False)
    receipt = tmp_path / "receipts" / "both.json"
    with pytest.raises(up.UploadError) as caught:
        up.run_publish(TAG, ["windows", "linux"], credentials, receipt, http=world.http,
                       client_factory=factory_for(world.fake))
    assert caught.value.code == "release-objects" and world.fake.puts == []
    world.fake.seed(r2.part_key(sha(world.linux_data)), world.linux_data)
    result = up.run_publish(TAG, ["windows", "linux"], credentials, receipt, http=world.http,
                            client_factory=factory_for(world.fake))
    assert [key.rsplit("/", 2)[-2] + "/" + key.rsplit("/", 1)[-1][:5] for key in world.fake.put_keys()] == [
        "windows/" + sha(world.release.manifest)[:5], "live/windo", "linux/" + sha(world.linux.manifest)[:5],
        "live/linux"]
    assert receipt_of(receipt)["high_water"] == {"windows": world.release.sequence, "linux": world.linux.sequence}
    assert set(result["platforms"]) == {"windows", "linux"}


def test_cli_publish_uses_anonymous_github_and_the_guarded_client(tmp_path, credentials, monkeypatch, test_key, capsys):
    world = publish_world(tmp_path, test_key, monkeypatch)
    monkeypatch.setattr(up, "Http", lambda: world.http)
    monkeypatch.setattr(up, "create_client", factory_for(world.fake))
    code = up.main(["publish", "--release", TAG, "--platform", "windows", "--credentials", str(credentials),
                    "--receipt", str(tmp_path / "receipts" / "cli.json")])
    out, err = capsys.readouterr()
    assert code == 0 and "pointer published" in out and not leaked(out + err)
    assert world.fake.objects[POINTER_KEY]["body"] == world.release.pointer
    code = up.main(["publish", "--release", "client-notacommit", "--platform", "windows", "--credentials",
                    str(credentials), "--receipt", str(tmp_path / "receipts" / "cli.json")])
    assert code == 2 and "release-tag" in capsys.readouterr().err


@pytest.mark.parametrize("operation", ["HeadObject", "PutObject"])
@pytest.mark.parametrize("index", range(6), ids=ERROR_IDS)
def test_injected_publish_failures_at_other_operations_leak_nothing(tmp_path, credentials, capsys, monkeypatch,
                                                                    test_key, operation, index):
    world = publish_world(tmp_path, test_key, monkeypatch)
    world.fake.inject[operation] = raiser(transport_errors()[index])
    monkeypatch.setattr(up, "Http", lambda: world.http)
    monkeypatch.setattr(up, "create_client", factory_for(world.fake))
    receipt = tmp_path / "receipts" / "publish.json"
    code = up.main(["publish", "--release", TAG, "--platform", "windows", "--credentials", str(credentials),
                    "--receipt", str(receipt)])
    out, err = capsys.readouterr()
    assert code != 0 and not leaked(out + err) and not leaked(receipt.read_text())
    with pytest.raises(r2.DesktopR2Error) as caught:
        up.run_publish(TAG, ["windows"], credentials, receipt, http=world.http, client_factory=factory_for(world.fake))
    assert_clean_exception(caught.value)
    assert POINTER_KEY not in world.fake.objects


def test_run_content_installs_the_production_guard(tmp_path, credentials):
    content = make_content(tmp_path)
    fake, created = FakeS3(), []
    run_content(content, credentials, tmp_path, fake, created=created)
    assert len(created) == 1 and created[0].selftest is False and created[0].budget is None
    with pytest.raises(up.GuardError):
        fake._pipeline("DeleteObject", {"Bucket": r2.BUCKET, "Key": content.parts[0].key})
    with pytest.raises(up.GuardError):
        fake._pipeline("PutObject", put_params(key=content.parts[0].key))
    with pytest.raises(up.GuardError):
        fake._pipeline("HeadObject", {"Bucket": r2.BUCKET, "Key": "browser/assets/" + SHA_A + ".zip"})


def test_cli_argument_rules(capsys):
    assert up.main(["verify-public", "--platform", "windows", "--set-sha256", "XYZ"]) == 2
    assert "set-sha256" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        up.build_parser().parse_args(["selftest", "--work", "w", "--credentials", "c", "--receipt", "r"])
    with pytest.raises(up.UploadError) as caught:
        up.Http().request("GET", "http://assets.rabbitlandsgame.com/x", limit=1)
    assert caught.value.code == "http-url"
    with pytest.raises(up.UploadError):
        up.Http().request("PUT", r2.pointer_url("windows"), limit=1)


def test_check_policy_writes_a_receipt_on_failure(tmp_path, test_key):
    http, policy = policy_world(tmp_path, test_key, latest=PREVIOUS)
    receipt = tmp_path / "receipts" / "policy.json"
    with pytest.raises(up.UploadError):
        up.run_check_policy(policy, http=http, public_pem=test_key.public, receipt_path=receipt)
    assert receipt_of(receipt)["result"] == "failed" and receipt_of(receipt)["error_code"] == "latest-commit"


def test_publish_records_the_sequence_once_the_pointer_is_accepted(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    world.http.routes[r2.pointer_url("windows")] = (200, {}, b"stale edge bytes")
    with pytest.raises(up.UploadError) as caught:
        publish(world, credentials, tmp_path)
    assert caught.value.code == "public-verify"
    receipt = receipt_of(tmp_path / "receipts" / "publish.json")
    assert receipt["high_water"] == {"windows": world.release.sequence} and receipt["result"] == "failed"


def test_publish_writes_the_sequence_to_disk_before_the_read_back(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    receipt = tmp_path / "receipts" / "publish.json"
    seen = {}

    def pointer_read(method, headers):
        seen.update(receipt_of(receipt))  # what a killed run would leave behind
        return 200, {}, world.release.pointer
    world.http.routes[("GET", r2.pointer_url("windows"))] = pointer_read
    publish(world, credentials, tmp_path)
    assert seen["high_water"] == {"windows": world.release.sequence} and "finished_utc" not in seen
    assert receipt_of(receipt)["result"] == "complete"


def test_publish_412_after_an_accepted_attempt_counts_as_published(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    old = live_pointer(test_key, sequence=world.release.sequence - 5)
    world.fake.seed(POINTER_KEY, old, sequence=world.release.sequence - 5)

    def accepted_then_412(params):  # a retried request whose first attempt R2 stored
        world.fake.seed(POINTER_KEY, world.release.pointer, sequence=world.release.sequence)
        raise client_error("PreconditionFailed", 412)
    world.fake.inject[("PutObject", POINTER_KEY)] = accepted_then_412
    result = publish(world, credentials, tmp_path)
    assert result["platforms"]["windows"]["result"] == "published"
    assert receipt_of(tmp_path / "receipts" / "publish.json")["high_water"] == {"windows": world.release.sequence}


def test_publish_refuses_file_inputs_outside_selftest(tmp_path, credentials, test_key):
    with pytest.raises(up.UploadError) as caught:
        up.LocalRelease({"windows": (tmp_path / "p.json", tmp_path / "m.json")}, selftest=False)
    assert caught.value.code == "publish-file-input"
    with pytest.raises(up.UploadError) as caught:
        up.run_publish(TAG, ["windows"], credentials, tmp_path / "r.json", source=types.SimpleNamespace())
    assert caught.value.code == "publish-file-input"
    for flag in ("--manifest", "--pointer", "--public-key", "--manifest-file", "--file"):
        with pytest.raises(SystemExit) as exited:
            up.build_parser().parse_args(["publish", "--release", TAG, "--platform", "windows", "--credentials", "c",
                                          "--receipt", "r", flag, "x.json"])
        assert exited.value.code == 2


def test_selftest_trust_must_not_be_the_release_key(test_key):
    assert test_key.public != COMMITTED_PEM
    assert up.require_test_key(test_key.public) == test_key.public
    with pytest.raises(up.UploadError) as caught:
        up.require_test_key(COMMITTED_PEM)
    assert caught.value.code == "selftest-key"
    with pytest.raises(up.UploadError):
        up.require_test_key(COMMITTED_PEM.replace(b"\n", b"\r\n"))


def test_unreadable_publish_receipt_is_not_silently_reset(tmp_path, credentials, monkeypatch, test_key):
    world = publish_world(tmp_path, test_key, monkeypatch)
    receipt = tmp_path / "receipts" / "publish.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{not json")
    with pytest.raises(up.UploadError) as caught:
        publish(world, credentials, tmp_path)
    assert caught.value.code == "receipt-state" and receipt.read_text() == "{not json"


# --- Self-test ---------------------------------------------------------------------------------

SELFTEST_SIZES = (1024, 2048, 4096, 8 * 1024 * 1024 + 1)


def run_selftest(tmp_path, credentials, fake, http, *, created=None, **options):
    return up.run_selftest(tmp_path / "work", credentials, tmp_path / "receipts" / "selftest.json",
                           client_factory=factory_for(fake, created), http=http, sleep=lambda seconds: None,
                           sizes=options.pop("sizes", SELFTEST_SIZES), **options)


def test_selftest_end_to_end_against_fakes(tmp_path, credentials):
    fake, created = FakeS3(), []
    result = run_selftest(tmp_path, credentials, fake, FakeHttp(fake), created=created)
    failed = [row for row in result["checks"] if not row["ok"]]
    assert result["ok"] and not failed, failed
    prefix = result["prefix"]
    assert re.fullmatch(r"desktop/selftest/[0-9]{8}-[0-9a-f]{8}/", prefix)
    assert [(guard.selftest, guard.prefix) for guard in created] == [(True, prefix)]
    range_check = next(row for row in result["checks"] if row["name"] == "public-range-206")
    assert range_check["checked"] == 1
    assert all(key.startswith(prefix) for key in fake.objects) and all(key.startswith(prefix) for key, _ in fake.puts)
    assert result["ledger_bytes"] <= up.SELFTEST_BUDGET_BYTES
    names = {row["name"] for row in result["checks"]}
    assert {"upload", "rerun-resumes", "reused-rows", "conflict-refused", "if-none-match-412", "checksum-sha256",
            "pointer-if-match", "pointer-stale-etag-412", "inventory", "public-parts", "public-range-206",
            "public-json"} <= names
    content_puts = [key for key, _ in fake.puts if "/parts/" in key or "/sets/" in key]
    assert content_puts[-1].startswith(prefix + "sets/windows/")
    pointer_puts = [params for key, params in fake.puts if key.endswith("channels/live/windows.json")]
    assert [("IfNoneMatch" in params, "IfMatch" in params) for params in pointer_puts] == [(True, False), (False, True)]
    test_public = (tmp_path / "work" / "keys" / "selftest-public.pem").read_bytes()
    assert test_public != COMMITTED_PEM
    receipt = receipt_of(tmp_path / "receipts" / "selftest.json")
    assert receipt["result"] == "complete" and not leaked(json.dumps(receipt))


def test_selftest_rerun_resumes_the_same_prefix(tmp_path, credentials):
    fake = FakeS3()
    http = FakeHttp(fake)
    first = run_selftest(tmp_path, credentials, fake, http)
    puts = len(fake.puts)
    second = run_selftest(tmp_path, credentials, fake, http)
    assert second["ok"] and second["prefix"] == first["prefix"]
    assert len(fake.puts) == puts  # the two probes are refused with 412; nothing else is written
    ledger = json.loads((tmp_path / "work" / "put-ledger.json").read_text())
    assert ledger["used_bytes"] == second["ledger_bytes"] <= up.SELFTEST_BUDGET_BYTES


def test_selftest_canary_keeps_a_refused_put_within_budget(tmp_path, credentials):
    fake = FakeS3()
    fake.inject["PutObject"] = raiser(client_error("InvalidArgument", 400))  # e.g. the checksum header refused
    with pytest.raises(up.SdkError):
        run_selftest(tmp_path, credentials, fake, FakeHttp(fake))
    state = json.loads((tmp_path / "work" / "state.json").read_text())
    smallest = min(state["parts"], key=lambda row: row["size"])
    assert [call for call in fake.calls if call[0] == "PutObject"] == [
        ("PutObject", f"{state['prefix']}parts/{smallest['sha256']}.bin")]
    ledger = json.loads((tmp_path / "work" / "put-ledger.json").read_text())
    assert ledger["used_bytes"] == min(SELFTEST_SIZES)
    receipt = receipt_of(tmp_path / "receipts" / "selftest.json")
    assert receipt["result"] == "failed" and receipt["error_code"] == "PutObject:InvalidArgument:400"
    # The escape then still fits the budget.
    fake.inject.clear()
    result = run_selftest(tmp_path, credentials, fake, FakeHttp(fake), checksum_header=False)
    assert result["ok"] and result["ledger_bytes"] <= up.SELFTEST_BUDGET_BYTES


def test_selftest_budget_is_enforced(tmp_path, credentials):
    fake = FakeS3()
    with pytest.raises(up.UploadError) as caught:
        run_selftest(tmp_path, credentials, fake, FakeHttp(fake), budget_bytes=1_000_000)
    assert caught.value.code == "selftest-budget" and fake.calls == []
    budget = up.PutBudget(tmp_path / "ledger.json", 5000)
    budget.charge(4000)
    with pytest.raises(up.GuardError):
        budget.charge(1001)
    assert up.PutBudget(tmp_path / "ledger.json", 5000).used == 4000
    with pytest.raises(up.UploadError):
        up.PutBudget(tmp_path / "other.json", up.SELFTEST_BUDGET_BYTES + 1)


def test_private_writes_retry_a_briefly_locked_rename(tmp_path, monkeypatch):
    """Windows refuses a rename onto a file a scanner holds open for a moment."""
    real_replace, failures = os.replace, []

    def flaky(source, target):
        if len(failures) < 2:
            failures.append(target)
            raise PermissionError(5, "Access is denied")
        real_replace(source, target)
    monkeypatch.setattr(up.os, "replace", flaky)
    monkeypatch.setattr(up.time, "sleep", lambda seconds: None)
    target = tmp_path / "ledger.json"
    up.write_private(target, b"{}")
    assert target.read_bytes() == b"{}" and len(failures) == 2
    monkeypatch.setattr(up.os, "replace", lambda source, target: (_ for _ in ()).throw(PermissionError(5, "denied")))
    with pytest.raises(PermissionError):
        up.write_private(target, b"{\"new\":1}", attempts=3)
    assert target.read_bytes() == b"{}" and [path.name for path in tmp_path.iterdir()] == ["ledger.json"]


def test_selftest_budget_counts_every_put_attempt(tmp_path):
    budget = up.PutBudget(tmp_path / "ledger.json", 3000)
    for _ in range(2):
        budget.check_send(request=types.SimpleNamespace(method="PUT", headers={"Content-Length": b"1000"}))
    budget.check_send(request=types.SimpleNamespace(method="HEAD", headers={}))
    assert (budget.used, budget.puts) == (2000, 2)
    with pytest.raises(up.GuardError):
        budget.check_send(request=types.SimpleNamespace(method="PUT", headers={}))


@needs_botocore
def test_real_botocore_selftest_guard_charges_and_scopes(tmp_path, credentials):
    emulator = R2Emulator()
    budget = up.PutBudget(tmp_path / "ledger.json", 10)
    client = real_client(credentials, emulator, selftest=True, budget=budget)
    key = f"desktop/selftest/20261104-0a1b2c3d/parts/{SHA_A}.bin"
    client.put_object(Bucket=r2.BUCKET, Key=key, Body=b"12345", ContentLength=5, IfNoneMatch="*",
                      ContentType="application/octet-stream", CacheControl=r2.IMMUTABLE_CACHE_CONTROL,
                      Metadata={"sha256": SHA_A})
    assert budget.used == 5
    with pytest.raises(up.GuardError):
        client.put_object(Bucket=r2.BUCKET, Key=key.replace("a", "b"), Body=b"123456", ContentLength=6,
                          IfNoneMatch="*", ContentType="application/octet-stream",
                          CacheControl=r2.IMMUTABLE_CACHE_CONTROL, Metadata={"sha256": SHA_A})
    with pytest.raises(up.GuardError):
        client.head_object(Bucket=r2.BUCKET, Key=PART_KEY)
    assert len(emulator.sent) == 1


# --- verify-public and check-policy ---------------------------------------------------------

def public_world(tmp_path):
    fake = FakeS3()
    content = make_content(tmp_path)
    for part in content.parts:
        fake.seed(part.key, part.data)
    fake.seed(content.set_key, content.set_bytes)
    return fake, content, FakeHttp(fake)


def test_verify_public_heads_before_every_get(tmp_path):
    fake, content, http = public_world(tmp_path)
    summary = up.run_verify_public("windows", content.set_sha256, http=http,
                                   receipt_path=tmp_path / "receipts" / "verify.json")
    assert summary["ok"] and summary["verified"] == 3
    for part in content.parts:
        url = r2.public_url(part.key)
        assert http.calls.index(("HEAD", url)) < http.calls.index(("GET", url))
    assert receipt_of(tmp_path / "receipts" / "verify.json")["result"] == "complete"


def test_verify_public_reports_missing_and_wrong_parts(tmp_path):
    fake, content, http = public_world(tmp_path)
    del fake.objects[content.parts[0].key]
    fake.objects[content.parts[1].key]["body"] = bytes(len(content.parts[1].data))
    summary = up.run_verify_public("windows", content.set_sha256, http=http)
    assert not summary["ok"] and summary["failed"] == 2
    assert ("GET", r2.public_url(content.parts[0].key)) not in http.calls  # a 404 HEAD never leads to a GET


def test_verify_public_sample(tmp_path):
    fake, content, http = public_world(tmp_path)
    summary = up.run_verify_public("windows", content.set_sha256, http=http, sample=1, seed=3)
    assert summary["parts"] == 1 and summary["sample_seed"] == 3


def test_verify_public_refuses_other_set_bytes(tmp_path):
    fake, content, http = public_world(tmp_path)
    with pytest.raises(up.UploadError) as caught:
        up.run_verify_public("windows", "f" * 64, http=http)
    assert caught.value.code == "set-missing"


def policy_world(tmp_path, test_key, *, latest=COMMIT, pointer_commit=COMMIT):
    fake = FakeS3()
    http = FakeHttp(fake)
    manifests = {}
    for platform in r2.PLATFORMS:
        release = make_release(test_key, platform=platform, commit=pointer_commit)
        fake.seed(r2.manifest_key(platform, sha(release.manifest)), release.manifest)
        fake.seed(r2.pointer_key(platform), release.pointer, sequence=release.sequence)
        manifests[platform] = f"{r2.GITHUB_DOWNLOADS}client-{COMMIT}/{version_for(platform)}-{platform}.json"
    http.routes[f"{up.GITHUB_API}repos/{r2.REPOSITORY}/releases/latest"] = (
        200, {}, json.dumps({"id": 1, "tag_name": f"client-{latest}", "draft": False, "prerelease": False}).encode())
    policy = tmp_path / "client_updates.json"
    policy.write_text(json.dumps({"schema": 1, "required_commit": COMMIT, "enforce": True, "manifests": manifests}))
    return http, policy


def test_check_policy_passes_when_pointers_and_latest_agree(tmp_path, test_key):
    http, policy = policy_world(tmp_path, test_key)
    result = up.run_check_policy(policy, http=http, public_pem=test_key.public)
    assert result["ok"] and set(result["platforms"]) == set(r2.PLATFORMS)


@pytest.mark.parametrize("case, code", [("latest", "latest-commit"), ("pointer", "pointer-commit"),
                                        ("manifest-url", "policy-manifests"), ("key", "signature")])
def test_check_policy_refuses_disagreement(tmp_path, test_key, other_key, case, code):
    http, policy = policy_world(tmp_path, test_key, latest=PREVIOUS if case == "latest" else COMMIT,
                                pointer_commit=PREVIOUS if case == "pointer" else COMMIT)
    if case == "manifest-url":
        document = json.loads(policy.read_text())
        document["manifests"]["linux"] = "https://example.com/manifest.json"
        policy.write_text(json.dumps(document))
    with pytest.raises(up.UploadError) as caught:
        up.run_check_policy(policy, http=http, public_pem=other_key.public if case == "key" else test_key.public)
    assert caught.value.code == code


# --- Anonymous HTTPS rules --------------------------------------------------------------------

@pytest.mark.parametrize("url, redirect, ok", [
    ("https://api.github.com/repos/x", False, True), ("https://github.com/x", False, True),
    ("https://assets.rabbitlandsgame.com/desktop/v1/parts/x.bin", False, True),
    ("http://assets.rabbitlandsgame.com/x", False, False), ("https://evil.example/x", False, False),
    ("https://user:pass@github.com/x", False, False), ("https://github.com:8443/x", False, False),
    (f"{ENDPOINT}/x", False, False), ("https://release-assets.githubusercontent.com/x", False, False),
    ("https://release-assets.githubusercontent.com/x", True, True), ("http://objects.githubusercontent.com/x", True, False),
])
def test_anonymous_http_hosts(url, redirect, ok):
    assert up._allowed_url(url, redirect=redirect) is ok


# --- Requirements file ---------------------------------------------------------------------------

def test_requirements_are_hash_locked_with_exact_versions():
    text = (TOOLS / "desktop-r2-requirements.txt").read_text()
    lines = [line for line in text.replace("\\\n", " ").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    pins = {}
    for line in lines:
        fields = line.split()
        match = re.fullmatch(r"([a-z0-9-]+)==([0-9][0-9a-z.]*)", fields[0])
        assert match, line
        hashes = fields[1:]
        assert hashes and all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", item) for item in hashes), line
        assert len(set(hashes)) == len(hashes)
        pins[match[1]] = match[2]
    assert set(pins) == {"boto3", "botocore", "s3transfer", "jmespath", "urllib3", "python-dateutil", "six",
                         "cryptography", "cffi", "pycparser"}
    assert pins["boto3"] == pins["botocore"]
    assert "--require-hashes --no-deps" in text and not re.search(r"[<>~!]=|>|<", "\n".join(lines))

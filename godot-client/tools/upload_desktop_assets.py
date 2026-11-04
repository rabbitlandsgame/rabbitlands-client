"""Upload, publish and verify desktop release content on Cloudflare R2.

Modes:
  content        upload the parts of a content set from an upload plan, then the set
  publish        copy a published release's signed manifest and pointer to R2
  selftest       the small end-to-end proof under a fresh desktop/selftest/ prefix
  verify-public  anonymous HEAD, then GET and SHA-256, of a set's parts on the custom domain
  check-policy   anonymous gate before the server's required_commit is raised

R2, Cloudflare and every R2 credential are untrusted transport. Players accept
bytes only against rows of a manifest signed by the release key; the R2
metadata and ETags read here are bookkeeping for this tool, never integrity.

Rules this tool enforces in code:
  * every key passes desktop_r2.guard_key before any SDK call (production
    mode: the desktop/v1 shapes; self-test mode: only its nonce prefix), and
    again in botocore handlers that also refuse every operation except
    HeadObject, GetObject, PutObject and ListObjectsV2 (prefix desktop/), and
    every immutable PUT without IfNoneMatch='*';
  * conditional create and never overwrite; the signed pointer is the only
    mutable object and is replaced only with IfMatch; never delete; no
    multipart; one bounded PUT per object; at most 4 workers;
  * SDK failures are reduced to an operation, an error code and an HTTP
    status, raised with no exception context; the SDK loggers are silenced;
    the endpoint, account id, key id and secret never reach stdout, stderr,
    receipts or exception text;
  * receipts, plans and self-test material live outside every Git worktree or
    in an ignored location; `publish` reads releases only anonymously from
    GitHub and takes no file inputs outside self-test mode.

Dependencies: desktop-r2-requirements.txt (hash-locked, exact versions),
installed with `--require-hashes --no-deps` outside every repository.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings

import desktop_r2 as r2

TOOLS = Path(__file__).resolve().parent
PUBLIC_KEY_PATH = TOOLS.parent / "data" / "update_public.pem"

MAX_WORKERS = 4
# Self-test uploads across the whole workflow stay at or below this many bytes.
SELFTEST_BUDGET_BYTES = 100_000_000
SELFTEST_SIZES = (64 * 1024, 1024 * 1024, 8 * 1024 * 1024, 64 * 1024 * 1024)
SELFTEST_PLATFORM = "windows"
PLAN_KIND = "rabbitlands-desktop-upload-plan"
PLAN_SCHEMA = 1
RECEIPT_KIND = "rabbitlands-desktop-r2-receipt"
RECEIPT_SCHEMA = 1
LEDGER_KIND = "rabbitlands-desktop-selftest-ledger"
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_STATE_BYTES = 64 * 1024 * 1024
MAX_API_BYTES = 8 * 1024 * 1024
HTTP_TIMEOUT = 60
USER_AGENT = "RabbitLands-desktop-r2/1"
# What the desktop updater sends (src/updates/package_download.gd).
UPDATER_HEADERS = {"User-Agent": "RabbitLands-Client", "Accept": "application/octet-stream",
                   "Cache-Control": "no-cache"}
GITHUB_API = "https://api.github.com/"
GITHUB_DOWNLOADS = r2.GITHUB_DOWNLOADS
API_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
HTTP_HOSTS = frozenset({"api.github.com", "github.com", urllib.parse.urlsplit(r2.PUBLIC_ORIGIN).hostname})
REDIRECT_HOST_SUFFIXES = (".githubusercontent.com",)
POINTER_WRITE_INTERVAL = 1.1  # R2 accepts one write per second per key
SDK_LOGGERS = ("botocore", "boto3", "urllib3", "s3transfer")
# The only client methods this tool calls; a test checks the source against it.
CLIENT_METHODS = frozenset({"head_object", "get_object", "put_object", "list_objects_v2"})
MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
PRECONDITION_CODES = frozenset({"PreconditionFailed", "ConditionalRequestConflict"})

_OPERATION_PARAMETERS = {
    "HeadObject": frozenset({"Bucket", "Key", "ChecksumMode"}),
    "GetObject": frozenset({"Bucket", "Key", "Range"}),
    "PutObject": frozenset({"Bucket", "Key", "Body", "ContentLength", "ContentType", "CacheControl", "Metadata",
                            "IfNoneMatch", "IfMatch", "ChecksumSHA256"}),
    # botocore itself adds EncodingType='url' to every ListObjectsV2 (and decodes
    # the keys); its handler is more specific than ours, so it runs first.
    "ListObjectsV2": frozenset({"Bucket", "Prefix", "ContinuationToken", "MaxKeys", "EncodingType"}),
}
_HTTP_METHODS = {"HeadObject": "HEAD", "GetObject": "GET", "PutObject": "PUT", "ListObjectsV2": "GET"}
assert frozenset(_OPERATION_PARAMETERS) == r2.ALLOWED_OPERATIONS

_ETAG = re.compile(r'"[0-9A-Za-z-]{1,128}"')
_TAG = re.compile(r"client-([0-9a-f]{40})")
_ERROR_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.]{0,63}")
_CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_RANGE = re.compile(r"bytes=[0-9]{1,12}-[0-9]{0,12}")


# --- Output hygiene ------------------------------------------------------------

def silence_sdk_logging() -> None:
    """SDK and urllib3 log records (which can name the endpoint host) go nowhere."""
    for name in SDK_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
            logger.addHandler(logging.NullHandler())
        logger.propagate = False
    warnings.filterwarnings("ignore", module=r"(?:botocore|boto3|urllib3|s3transfer)(?:\.|$)")


silence_sdk_logging()

_SECRETS: list[str] = []
_SECRETS_LOCK = threading.Lock()


def _register_secrets(config) -> None:
    with _SECRETS_LOCK:
        for value in config.secret_values():
            if value and value not in _SECRETS:
                _SECRETS.append(value)
        _SECRETS.sort(key=len, reverse=True)


def redact(text) -> str:
    """Defence in depth: replace any loaded secret-set value (case-insensitive)."""
    text = str(text)
    for value in list(_SECRETS):
        text = re.sub(re.escape(value), "[redacted]", text, flags=re.IGNORECASE)
    return text


def emit(message, *, error: bool = False) -> None:
    print(redact(message), file=sys.stderr if error else sys.stdout, flush=True)


# --- Errors ----------------------------------------------------------------------

class UploadError(r2.DesktopR2Error):
    """A refusal or failure with a stable code; its text never holds secret values."""

    def __init__(self, code: str, detail: str = ""):
        self.detail = detail
        super().__init__(code, detail)


class GuardError(UploadError):
    """The SDK guard refused a call before it reached the network."""


class IncompleteError(UploadError):
    """Work ran but did not finish; the receipt lists what failed."""


class SdkError(UploadError):
    """A sanitized SDK failure: the operation, an error code and the HTTP status only."""

    def __init__(self, operation: str, error_code: str, status: int | None = None):
        self.operation = operation
        self.error_code = error_code
        self.status = status
        super().__init__("sdk", f"{operation} {error_code}" + ("" if status is None else f" HTTP {status}"))

    @property
    def missing(self) -> bool:
        return self.error_code in MISSING_CODES

    @property
    def precondition_failed(self) -> bool:
        return self.status in (409, 412) or self.error_code in PRECONDITION_CODES

    @property
    def receipt_code(self) -> str:
        return f"{self.operation}:{self.error_code}" + ("" if self.status is None else f":{self.status}")


def _detail(error: r2.DesktopR2Error) -> str:
    text = str(error)
    return text[len(error.code) + 2:] if text.startswith(error.code + ": ") else ""


def error_code(error: BaseException) -> str:
    """The receipt form of a failure: never exception text."""
    if isinstance(error, SdkError):
        return error.receipt_code
    if isinstance(error, r2.DesktopR2Error):
        return error.code
    name = type(error).__name__
    return name if _CLASS_NAME.fullmatch(name) else "Error"


def _classify(error: BaseException) -> tuple[str, int | None]:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        info = response.get("Error")
        code = info.get("Code") if isinstance(info, dict) else None
        meta = response.get("ResponseMetadata")
        status = meta.get("HTTPStatusCode") if isinstance(meta, dict) else None
        if not (isinstance(code, str) and _ERROR_CODE.fullmatch(code) and redact(code) == code):
            code = "ClientError"
        return code, status if type(status) is int and 100 <= status <= 599 else None
    name = type(error).__name__
    return (name if _CLASS_NAME.fullmatch(name) and redact(name) == name else "Error"), None


def _sdk(operation: str, call, /, *args, **kwargs):
    """Run one SDK call. A failure becomes an SdkError raised with no exception
    context, so neither its text nor the chain can carry the endpoint URL."""
    failure = refusal = None
    try:
        return call(*args, **kwargs)
    except r2.DesktopR2Error as error:
        refusal = (type(error) if isinstance(error, UploadError) else UploadError, error.code, _detail(error))
    except Exception as error:  # noqa: BLE001 - every SDK failure is reduced to its code
        failure = _classify(error)
    if refusal is not None:
        kind, code, detail = refusal
        if kind is SdkError:
            kind = UploadError
        raise kind(code, detail)
    raise SdkError(operation, *failure)


# --- Small helpers -------------------------------------------------------------

def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _refuse_constant(name):
    raise ValueError("non-finite number")


def strict_json(data: bytes):
    """Strict JSON (UTF-8, no duplicate keys, NaN or Infinity); None when malformed."""
    value = None
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=_refuse_constant)
        ok = True
    except (UnicodeDecodeError, ValueError, RecursionError, TypeError, AttributeError):
        ok = False
    return value if ok else None


def _read_limited(path: Path, limit: int, code: str) -> bytes:
    ok = True
    data = b""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            ok = False
        else:
            data = path.read_bytes()
    except OSError:
        ok = False
    if not ok or len(data) > limit:
        raise UploadError(code, path.name)
    return data


def private_path(path, what: str) -> Path:
    """`path` resolved, when it is outside every Git worktree or Git ignores it."""
    target = None
    try:
        target = r2.require_private_path(Path(path))
    except r2.OutputPathError:
        target = None
    if target is None:
        raise UploadError(f"{what}-location", "use a path outside every Git worktree, or an ignored one")
    return target


def write_private(path: Path, data: bytes, *, attempts: int = 20) -> None:
    """Atomic write (temporary file, then rename) of a private file.

    On Windows a rename onto a file that another process (a virus scanner or
    the indexer) holds open for a moment fails with PermissionError, so the
    rename is retried briefly; the temporary file never replaces a partial one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_bytes(data)
    for attempt in range(1, attempts + 1):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == attempts:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05 * attempt)


def check_workers(workers) -> int:
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise UploadError("workers", f"use 1 to {MAX_WORKERS} workers")
    return workers


def hash_file(path: Path) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _check_selftest_prefix(prefix) -> str:
    """`prefix` when it is exactly one `desktop/selftest/<YYYYMMDD>-<8 hex>/` prefix."""
    ok = False
    try:
        ok = (type(prefix) is str and prefix.startswith(r2.SELFTEST_ROOT) and prefix.endswith("/")
              and r2.selftest_prefix(*prefix[len(r2.SELFTEST_ROOT):-1].split("-", 1)) == prefix)
    except (TypeError, r2.DesktopR2Error):
        ok = False
    if not ok:
        raise GuardError("sdk-prefix", ascii(prefix)[:80])
    return prefix


def _object_limit(key: str) -> int:
    if r2.is_pointer_key(key):
        return r2.MAX_POINTER_BYTES
    if key.endswith(".json"):
        return r2.MAX_SET_BYTES
    return r2.MAX_PART_BYTES


# --- Trust (signatures; the private key never reaches this tool) ---------------

def committed_public_key() -> bytes:
    """The release public key of this checkout (godot-client/data/update_public.pem)."""
    data = _read_limited(PUBLIC_KEY_PATH, 64 * 1024, "public-key")
    r2.public_key_sha256(data)
    return data


def _public_numbers(pem: bytes):
    from cryptography.hazmat.primitives import serialization
    numbers = None
    try:
        numbers = serialization.load_pem_public_key(pem).public_numbers()
    except (ValueError, TypeError, AttributeError):
        numbers = None
    return numbers


def require_test_key(public_pem: bytes) -> bytes:
    """Self-test keys must not be the release key, by bytes or by modulus."""
    committed = committed_public_key()
    numbers = _public_numbers(public_pem) if type(public_pem) is bytes else None
    if numbers is None:
        raise UploadError("selftest-key", "the self-test public key is unreadable")
    if public_pem.strip() == committed.strip() or numbers == _public_numbers(committed):
        raise UploadError("selftest-key", "the self-test key must differ from update_public.pem")
    return public_pem


def verify_envelope(data: bytes, public_pem: bytes, *, limit: int) -> tuple[bytes, dict]:
    """Check a signed `{payload, signature}` envelope; return the payload bytes and object."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    r2.check_envelope(data, limit=limit)
    envelope = strict_json(data)
    payload = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    verified = False
    try:
        serialization.load_pem_public_key(public_pem).verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        verified = True
    except (InvalidSignature, ValueError, TypeError, AttributeError):
        verified = False
    if not verified:
        raise UploadError("signature", "the envelope is not signed by the expected key")
    value = strict_json(payload)
    if not isinstance(value, dict):
        raise UploadError("envelope-payload", "the signed payload is not a JSON object")
    return payload, value


def sign_envelope(payload: bytes, private_pem: bytes) -> bytes:
    """Self-test only: sign with a throwaway test key (production signing is CI's)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(private_pem, password=None)
    signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return json.dumps({"payload": _b64(payload), "signature": _b64(signature)}, separators=(",", ":"),
                      sort_keys=True).encode("ascii")


# --- SDK guard and client ------------------------------------------------------

class PutBudget:
    """Self-test PUT byte cap, persisted in a private ledger and charged per attempt."""

    def __init__(self, ledger: Path, limit: int = SELFTEST_BUDGET_BYTES):
        if type(limit) is not int or not 0 < limit <= SELFTEST_BUDGET_BYTES:
            raise UploadError("selftest-budget", f"the budget is at most {SELFTEST_BUDGET_BYTES} bytes")
        self.path = ledger
        self.limit = limit
        self.lock = threading.Lock()
        self.used = 0
        self.puts = 0
        if ledger.exists():
            state = strict_json(_read_limited(ledger, MAX_STATE_BYTES, "selftest-ledger"))
            if (not isinstance(state, dict) or state.get("kind") != LEDGER_KIND
                    or type(state.get("used_bytes")) is not int or type(state.get("puts")) is not int
                    or state["used_bytes"] < 0):
                raise UploadError("selftest-ledger", "the self-test ledger is malformed")
            self.used, self.puts = state["used_bytes"], state["puts"]

    def charge(self, length: int) -> None:
        with self.lock:
            if type(length) is not int or length < 0 or self.used + length > self.limit:
                raise GuardError("selftest-budget", f"{self.used} + {length} bytes would exceed {self.limit}")
            self.used += length
            self.puts += 1
            write_private(self.path, json.dumps({"kind": LEDGER_KIND, "used_bytes": self.used, "puts": self.puts,
                                                 "limit": self.limit, "updated_utc": _utc_now()}).encode("ascii"))

    def check_send(self, request=None, **_):
        """botocore `before-send`: every PUT attempt (retries included) is charged."""
        if str(getattr(request, "method", "")).upper() != "PUT":
            return None
        headers = getattr(request, "headers", {}) or {}
        value = headers.get("Content-Length")
        length = None
        try:
            length = int(value)
        except (TypeError, ValueError):
            length = None
        if length is None:
            raise GuardError("selftest-budget", "a self-test PUT without Content-Length")
        self.charge(length)
        return None


class SdkGuard:
    """botocore event handlers that limit this tool's client to the desktop layout.

    They limit the tool, not the credential: the owner narrows the credential
    itself (a separate desktop token and bucket lock rules).
    """

    MARK = "rabbitlands_desktop_guard"

    def __init__(self, *, bucket: str, selftest: bool = False, budget: PutBudget | None = None,
                 prefix: str | None = None):
        if bucket != r2.BUCKET:
            raise GuardError("sdk-bucket", "the desktop guard serves the desktop asset bucket only")
        if prefix is not None and not selftest:
            raise GuardError("sdk-prefix", "only a self-test guard is bound to a key prefix")
        self.bucket = bucket
        self.selftest = selftest
        self.budget = budget
        # A self-test run reaches only the one nonce prefix it created.
        self.prefix = None if prefix is None else _check_selftest_prefix(prefix)

    def install(self, client) -> None:
        events = client.meta.events
        events.register_first("before-parameter-build.s3", self.check_parameters,
                              unique_id="rabbitlands-desktop-guard-parameters")
        events.register_first("before-call.s3", self.check_request, unique_id="rabbitlands-desktop-guard-call")
        if self.budget is not None:
            events.register_first("before-send.s3", self.budget.check_send,
                                  unique_id="rabbitlands-desktop-guard-budget")

    def _refuse(self, code: str, detail: str = ""):
        raise GuardError(code, detail)

    def inspect(self, name, params) -> dict:
        """The call's guard record, or a GuardError (pure: no SDK needed)."""
        if type(name) is not str or name not in r2.ALLOWED_OPERATIONS:
            self._refuse("sdk-operation", ascii(name)[:80])
        if not isinstance(params, dict):
            self._refuse("sdk-parameters")
        unknown = sorted(set(params) - _OPERATION_PARAMETERS[name])
        if unknown:
            self._refuse("sdk-parameter", ",".join(ascii(item)[:40] for item in unknown))
        if params.get("Bucket") != self.bucket:
            self._refuse("sdk-bucket")
        if name == "ListObjectsV2":
            prefix = params.get("Prefix")
            try:
                r2.guard_list_prefix(prefix, selftest=self.selftest)
                allowed = True
            except r2.KeyGuardError:
                allowed = False
            if not allowed or (self.prefix is not None and not prefix.startswith(self.prefix)):
                self._refuse("sdk-key", ascii(prefix)[:120])
            if params.get("EncodingType", "url") != "url":
                self._refuse("sdk-parameter", "EncodingType")
            return {"operation": name, "prefix": prefix}
        key = params.get("Key")
        outside = self.prefix is not None and type(key) is str and not key.startswith(self.prefix)
        if not r2.is_allowed_key(key, selftest=self.selftest) or outside:
            self._refuse("sdk-key", ascii(key)[:120])
        mark = {"operation": name, "key": key}
        if name == "HeadObject" and params.get("ChecksumMode") not in (None, "ENABLED"):
            self._refuse("sdk-parameter", "ChecksumMode")
        if name == "GetObject" and "Range" in params and not (type(params["Range"]) is str
                                                              and _RANGE.fullmatch(params["Range"])):
            self._refuse("sdk-parameter", "Range")
        if name == "PutObject":
            size = params.get("ContentLength")
            if type(size) is not int or not 0 < size <= _object_limit(key):
                self._refuse("sdk-length", key)
            if_none, if_match = params.get("IfNoneMatch"), params.get("IfMatch")
            if r2.is_pointer_key(key):
                first = if_none == "*" and if_match is None
                replace = if_none is None and type(if_match) is str and _ETAG.fullmatch(if_match) is not None
                if not (first or replace):
                    self._refuse("sdk-pointer-condition", key)
            elif if_none != "*" or if_match is not None:
                self._refuse("sdk-unconditional-put", key)
            mark["condition"] = ("if-none-match", "*") if if_none == "*" else ("if-match", if_match)
        return mark

    def check_parameters(self, params=None, model=None, context=None, **_):
        """`before-parameter-build.s3`: the API parameters as this tool passed them."""
        mark = self.inspect(getattr(model, "name", None), params)
        if not isinstance(context, dict):
            self._refuse("sdk-context")
        context[self.MARK] = mark

    def check_request(self, model=None, params=None, context=None, **_):
        """`before-call.s3`: the serialized request must be the one that was checked."""
        name = getattr(model, "name", None)
        mark = context.get(self.MARK) if isinstance(context, dict) else None
        if name not in r2.ALLOWED_OPERATIONS or not isinstance(mark, dict) or mark.get("operation") != name:
            self._refuse("sdk-unchecked", ascii(name)[:80])
        if not isinstance(params, dict) or str(params.get("method", "")).upper() != _HTTP_METHODS[name]:
            self._refuse("sdk-request", "method")
        if name == "ListObjectsV2":
            query = params.get("query_string")
            if not isinstance(query, dict) or query.get("prefix") != mark["prefix"]:
                self._refuse("sdk-request", "prefix")
            return None
        path = urllib.parse.unquote(str(params.get("url_path", "")).split("?", 1)[0])
        if path not in ("/" + mark["key"], f"/{self.bucket}/{mark['key']}"):
            self._refuse("sdk-request", "path")
        if name == "PutObject":
            headers = {str(key).lower(): value for key, value in (params.get("headers") or {}).items()}
            header, value = mark["condition"]
            other = "if-match" if header == "if-none-match" else "if-none-match"
            if headers.get(header) != value or other in headers:
                self._refuse("sdk-request", "condition")
        return None


def create_client(config: r2.R2Config, guard: SdkGuard, *, attempts: int = 4):
    """A guarded boto3 S3 client. Never print, log or store its arguments."""
    available = True
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        available = False
    if not available:
        raise UploadError("sdk-missing", "install desktop-r2-requirements.txt with --require-hashes --no-deps")

    def build():
        session = boto3.session.Session()
        return session.client("s3", config=Config(
            signature_version="s3v4", max_pool_connections=2 * MAX_WORKERS, connect_timeout=20, read_timeout=120,
            retries={"total_max_attempts": attempts, "mode": "standard"},
            request_checksum_calculation="when_required", response_checksum_validation="when_required"),
            **config.client_kwargs())
    client = _sdk("CreateClient", build)
    guard.install(client)
    return client


def load_config(credentials) -> r2.R2Config:
    config = r2.load_r2_config(credentials)
    _register_secrets(config)
    return config


class Bucket:
    """The only path from this tool to S3: guarded keys and sanitized failures."""

    def __init__(self, client, name: str = r2.BUCKET, *, selftest: bool = False, checksum_header: bool = True):
        self.client = client
        self.name = name
        self.selftest = selftest
        self.checksum_header = checksum_header

    def _key(self, key: str) -> str:
        return r2.guard_key(key, selftest=self.selftest)

    def head(self, key: str, *, checksum: bool = False) -> dict | None:
        key = self._key(key)
        extra = {"ChecksumMode": "ENABLED"} if checksum else {}
        try:
            return _sdk("HeadObject", self.client.head_object, Bucket=self.name, Key=key, **extra)
        except SdkError as error:
            if error.missing:
                return None
            raise

    def get(self, key: str, limit: int, *, byte_range: str | None = None) -> tuple[bytes, str | None] | None:
        key = self._key(key)

        def fetch():
            extra = {"Range": byte_range} if byte_range else {}
            response = self.client.get_object(Bucket=self.name, Key=key, **extra)
            body = response["Body"]
            try:
                data = body.read(limit + 1)
            finally:
                body.close()
            return data, response.get("ETag")
        try:
            data, etag = _sdk("GetObject", fetch)
        except SdkError as error:
            if error.missing:
                return None
            raise
        if len(data) > limit:
            raise UploadError("object-too-large", key)
        return data, etag

    def put(self, key: str, source, *, size: int, sha256: str, headers: dict, condition: dict) -> dict:
        key = self._key(key)
        if type(size) is not int or not 0 < size <= _object_limit(key):
            raise UploadError("object-size", key)
        arguments = {"Bucket": self.name, "Key": key, "ContentLength": size, **headers, **condition}
        if self.checksum_header:
            arguments["ChecksumSHA256"] = _b64(bytes.fromhex(sha256))
        if isinstance(source, (bytes, bytearray)):
            if len(source) != size:
                raise UploadError("object-size", key)
            return _sdk("PutObject", self.client.put_object, Body=bytes(source), **arguments)
        with open(source, "rb") as stream:
            return _sdk("PutObject", self.client.put_object, Body=stream, **arguments)

    def list(self, prefix: str) -> list[dict]:
        prefix = r2.guard_list_prefix(prefix, selftest=self.selftest)
        rows, token = [], None
        for _ in range(1000):
            arguments = {"Bucket": self.name, "Prefix": prefix}
            if token:
                arguments["ContinuationToken"] = token
            response = _sdk("ListObjectsV2", self.client.list_objects_v2, **arguments)
            rows.extend({"key": item.get("Key"), "size": item.get("Size")} for item in response.get("Contents") or [])
            token = response.get("NextContinuationToken")
            if not response.get("IsTruncated"):
                return rows
            if not token:
                break
        raise UploadError("list-incomplete", prefix)


def _matches(head: dict | None, *, size: int, sha256: str, headers: dict) -> bool:
    return (isinstance(head, dict) and head.get("ContentLength") == size
            and (head.get("Metadata") or {}).get("sha256") == sha256
            and head.get("ContentType") == headers["ContentType"]
            and head.get("CacheControl") == headers["CacheControl"])


def put_immutable(bucket: Bucket, key: str, source, *, size: int, sha256: str) -> str:
    """Create an immutable object once: 'uploaded', or 'resumed' when an equal one exists.

    An existing differing object is a conflict and is never replaced. Every
    PUT carries IfNoneMatch='*'; a 412 means another writer won the race, so
    the object is HEADed again and resumed or refused. Every PUT is verified
    by a HEAD afterwards.
    """
    if r2.is_pointer_key(key):
        raise UploadError("pointer-immutable", key)
    headers = r2.object_headers(key, sha256, selftest=bucket.selftest)
    head = bucket.head(key)
    if head is not None:
        if _matches(head, size=size, sha256=sha256, headers=headers):
            return "resumed"
        raise UploadError("conflict", key)
    raced = False
    try:
        bucket.put(key, source, size=size, sha256=sha256, headers=headers, condition={"IfNoneMatch": "*"})
    except SdkError as error:
        if not error.precondition_failed:
            raise
        raced = True
    head = bucket.head(key)
    if not _matches(head, size=size, sha256=sha256, headers=headers):
        raise UploadError("conflict" if raced else "verify-failed", key)
    return "resumed" if raced else "uploaded"


def verify_reused(bucket: Bucket, key: str, *, size: int, sha256: str) -> str:
    """A reused row must already exist with the right length and bookkeeping; never uploaded."""
    head = bucket.head(key)
    if head is None:
        raise UploadError("reused-missing", key)
    if not _matches(head, size=size, sha256=sha256, headers=r2.object_headers(key, sha256, selftest=bucket.selftest)):
        raise UploadError("reused-mismatch", key)
    return "reused"


def put_pointer(bucket: Bucket, key: str, data: bytes, *, sequence: int, condition: dict) -> None:
    """The only overwrite: a signed pointer, with IfMatch (or IfNoneMatch='*' the first time)."""
    if not r2.is_pointer_key(key):
        raise UploadError("pointer-key", key)
    headers = r2.object_headers(key, r2.sha256_hex(data), sequence=sequence, selftest=bucket.selftest)
    bucket.put(key, data, size=len(data), sha256=r2.sha256_hex(data), headers=headers, condition=condition)


# --- Receipts ----------------------------------------------------------------------

class Receipt:
    """A private, sanitized record, written even when the run fails."""

    def __init__(self, path: Path, mode: str, **fields):
        self.path = path
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.data = {"kind": RECEIPT_KIND, "receipt_schema": RECEIPT_SCHEMA, "mode": mode, "bucket": r2.BUCKET,
                     "started_utc": _utc_now(), "objects": [], "failures": [], **fields}

    def add_object(self, key: str, size: int, sha256: str, result: str, **extra) -> None:
        with self.lock:
            self.data["objects"].append({"key": key, "bytes": size, "sha256": sha256, "result": result, **extra})

    def add_failure(self, key: str, code: str) -> None:
        with self.lock:
            self.data["failures"].append({"key": key, "error_code": code})

    def set(self, **fields) -> None:
        with self.lock:
            self.data.update(fields)

    @property
    def failures(self) -> list:
        return self.data["failures"]

    def write(self, *, final: bool = True) -> None:
        """Write the receipt; `final=False` is a checkpoint during the run."""
        with self.lock:
            stamp = "finished_utc" if final else "checkpoint_utc"
            self.data[stamp] = _utc_now()
            self.data["duration_seconds"] = round(time.monotonic() - self.started, 3)
            text = json.dumps(self.data, indent=2, sort_keys=True, ensure_ascii=True)
        write_private(self.path, (redact(text) + "\n").encode("ascii"))


# --- Content upload ------------------------------------------------------------------

@dataclass(frozen=True)
class PlanRow:
    key: str
    sha256: str
    size: int
    kind: str
    path: Path | None = None


@dataclass
class Plan:
    path: Path
    platform: str
    set_sha256: str
    set_bytes: bytes
    set_key: str
    rows: list[PlanRow]
    document: dict = field(repr=False)


_PLAN_FIELDS = frozenset({"kind", "plan_schema", "platform", "set_sha256", "set_bytes_path", "rows"})


def _set_parts(content_set: dict) -> dict:
    parts = {}
    for group in ("packages", "optional_packages"):
        for package in content_set.get(group) or []:
            for part in package["parts"]:
                parts[part["sha256"]] = part["size"]
    return parts


def load_plan(path, *, public_key_sha256: str, prefix: str | None = None) -> Plan:
    """Read and check an upload plan and its set. No SDK, no network.

    Plan: {kind, plan_schema, platform, set_sha256, set_bytes_path, rows:
    [{key, sha256, size, kind: "new", local_path} | {key, sha256, size, kind:
    "reused"}]}. Paths are absolute or relative to the plan. The rows must be
    exactly the set's parts, each at its derived key.
    """
    plan_path = private_path(path, "plan")
    document = strict_json(_read_limited(plan_path, MAX_PLAN_BYTES, "plan-unreadable"))
    if not isinstance(document, dict) or set(document) != _PLAN_FIELDS:
        raise UploadError("plan-shape", "expected {kind, plan_schema, platform, set_sha256, set_bytes_path, rows}")
    if (document["kind"] != PLAN_KIND or type(document["plan_schema"]) is not int
            or document["plan_schema"] != PLAN_SCHEMA):
        raise UploadError("plan-kind")
    platform = document["platform"]
    if platform not in r2.PLATFORMS:
        raise UploadError("plan-platform", ascii(platform)[:40])
    set_sha256 = document["set_sha256"]
    if type(set_sha256) is not str or not re.fullmatch("[0-9a-f]{64}", set_sha256):
        raise UploadError("plan-set-sha256")
    if type(document["set_bytes_path"]) is not str or not document["set_bytes_path"]:
        raise UploadError("plan-set-path")
    set_path = plan_path.parent / document["set_bytes_path"]
    set_bytes = _read_limited(set_path, r2.MAX_SET_BYTES, "plan-set-unreadable")
    if r2.sha256_hex(set_bytes) != set_sha256:
        raise UploadError("plan-set-sha256", "the set bytes do not match set_sha256")
    content_set = r2.parse_set_bytes(set_bytes)
    r2.validate_set(content_set, public_key_sha256=public_key_sha256, platform=platform, source="r2",
                    reader_cap=r2.READER_CAP_W1A)
    expected = _set_parts(content_set)
    rows, seen = [], set()
    if type(document["rows"]) is not list:
        raise UploadError("plan-rows")
    for index, row in enumerate(document["rows"]):
        if not isinstance(row, dict):
            raise UploadError("plan-row", str(index))
        kind = row.get("kind")
        fields = {"key", "sha256", "size", "kind"} | ({"local_path"} if kind == "new" else set())
        if kind not in ("new", "reused") or set(row) != fields:
            raise UploadError("plan-row-shape", str(index))
        sha256, size = row["sha256"], row["size"]
        if type(sha256) is not str or sha256 not in expected:
            raise UploadError("plan-extra-row", ascii(row.get("key"))[:120])
        if type(size) is not int or size != expected[sha256]:
            raise UploadError("plan-row-size", row["key"] if type(row["key"]) is str else str(index))
        if row["key"] != r2.part_key(sha256, prefix=prefix):
            raise UploadError("plan-row-key", ascii(row["key"])[:120])
        if sha256 in seen:
            raise UploadError("plan-duplicate-row", row["key"])
        seen.add(sha256)
        local = None
        if kind == "new":
            if type(row["local_path"]) is not str or not row["local_path"]:
                raise UploadError("plan-row-path", row["key"])
            local = plan_path.parent / row["local_path"]
        rows.append(PlanRow(row["key"], sha256, size, kind, local))
    missing = sorted(set(expected) - seen)
    if missing:
        raise UploadError("plan-missing-part", f"{len(missing)} set parts have no row, first {missing[0]}")
    return Plan(plan_path, platform, set_sha256, set_bytes, r2.set_key(platform, set_sha256, prefix=prefix), rows,
                document)


def check_new_rows(plan: Plan, *, workers: int, receipt: Receipt) -> int:
    """Size and SHA-256 of every new row's local file, before any client exists."""
    def check(row: PlanRow) -> str | None:
        path = row.path
        if path.is_symlink() or not path.is_file():
            return "local-missing"
        if path.stat().st_size != row.size:
            return "local-size"
        return None if hash_file(path) == row.sha256 else "local-sha256"
    new_rows = [row for row in plan.rows if row.kind == "new"]
    problems = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check, row): row for row in new_rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                problem = future.result()
            except OSError:
                problem = "local-unreadable"
            if problem:
                problems += 1
                receipt.add_failure(row.key, problem)
    if problems:
        raise UploadError("plan-local-rows", f"{problems} new rows failed their local size or SHA-256 check")
    return sum(row.size for row in new_rows)


@dataclass
class ContentResult:
    results: dict
    uploaded_bytes: int
    seconds: float


def upload_content(bucket: Bucket, plan: Plan, receipt: Receipt, *, workers: int, phase: str | None = None,
                   progress=None) -> ContentResult:
    """Parts first (new: create once; reused: must exist), the set last and only
    after every part is verified."""
    extra = {"phase": phase} if phase else {}
    results = {}
    uploaded = 0
    started = time.monotonic()
    failures_before = len(receipt.failures)

    def one(row: PlanRow) -> str:
        if row.kind == "reused":
            return verify_reused(bucket, row.key, size=row.size, sha256=row.sha256)
        return put_immutable(bucket, row.key, row.path, size=row.size, sha256=row.sha256)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, row): row for row in plan.rows}
        for count, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001 - recorded by code, never by text
                receipt.add_failure(row.key, error_code(error))
            else:
                results[row.key] = result
                uploaded += row.size if result == "uploaded" else 0
                receipt.add_object(row.key, row.size, row.sha256, result, **extra)
            if progress and (count % 50 == 0 or count == len(plan.rows)):
                failed = len(receipt.failures) - failures_before
                progress(f"Verified {len(results)}/{len(plan.rows)} parts; failures {failed}")
    failed = len(receipt.failures) - failures_before
    if failed:
        raise IncompleteError("upload-incomplete", f"{failed} parts failed; the set was not uploaded")
    result = put_immutable(bucket, plan.set_key, plan.set_bytes, size=len(plan.set_bytes), sha256=plan.set_sha256)
    results[plan.set_key] = result
    uploaded += len(plan.set_bytes) if result == "uploaded" else 0
    receipt.add_object(plan.set_key, len(plan.set_bytes), plan.set_sha256, result, **extra, last=True)
    return ContentResult(results, uploaded, time.monotonic() - started)


def release_local_parts(plan: Plan) -> tuple[int, int]:
    """After a fully verified upload: rewrite the plan (new rows become reused),
    then delete those local part files. Local files only; never R2."""
    released = [row for row in plan.rows if row.kind == "new"]
    if not released:
        return 0, 0
    document = dict(plan.document)
    document["rows"] = [{"key": row.key, "sha256": row.sha256, "size": row.size, "kind": "reused"} for row in plan.rows]
    write_private(plan.path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("ascii"))
    count = size = 0
    for row in released:
        if row.path.is_file() and not row.path.is_symlink():
            row.path.unlink()
            count += 1
            size += row.size
    return count, size


def run_content(plan_path, credentials, receipt_path, *, workers: int = MAX_WORKERS, release: bool = False,
                checksum_header: bool = True, client_factory=None) -> dict:
    receipt_path = private_path(receipt_path, "receipt")
    check_workers(workers)
    receipt = Receipt(receipt_path, "content")
    try:
        config = load_config(credentials)
        plan = load_plan(plan_path, public_key_sha256=r2.public_key_sha256(committed_public_key()))
        receipt.set(platform=plan.platform, set_key=plan.set_key, set_sha256=plan.set_sha256,
                    rows={"new": sum(row.kind == "new" for row in plan.rows),
                          "reused": sum(row.kind == "reused" for row in plan.rows)})
        new_bytes = check_new_rows(plan, workers=workers, receipt=receipt)
        emit(f"Checked {len(plan.rows)} plan rows ({new_bytes:,} new bytes); uploading to {config.bucket}")
        client = (client_factory or create_client)(config, SdkGuard(bucket=config.bucket))
        bucket = Bucket(client, config.bucket, checksum_header=checksum_header)
        result = upload_content(bucket, plan, receipt, workers=workers, progress=emit)
        receipt.set(uploaded_bytes=result.uploaded_bytes,
                    bytes_per_second=round(result.uploaded_bytes / result.seconds) if result.seconds > 0 else None)
        if release:
            files, size = release_local_parts(plan)
            receipt.set(released_local_parts={"files": files, "bytes": size})
        counts = {name: sum(value == name for value in result.results.values())
                  for name in ("uploaded", "resumed", "reused")}
        receipt.set(result="complete", counts=counts)
        emit(f"Content set {plan.set_sha256} is complete: {counts}")
        return {"ok": True, "counts": counts, "set_key": plan.set_key}
    except Exception as error:
        receipt.set(result="failed", error_code=error_code(error))
        raise
    finally:
        receipt.write()


# --- Anonymous HTTPS -----------------------------------------------------------------

def _allowed_url(url, *, redirect: bool = False) -> bool:
    if type(url) is not str:
        return False
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    return (parts.scheme == "https" and not parts.username and not parts.password and parts.port in (None, 443)
            and (host in HTTP_HOSTS or (redirect and host.endswith(REDIRECT_HOST_SUFFIXES))))


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_url(newurl, redirect=True):
            raise UploadError("http-redirect", ascii(urllib.parse.urlsplit(str(newurl)).hostname or "")[:80])
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class HttpResponse:
    status: int
    headers: dict
    body: bytes = b""
    sha256: str | None = None
    length: int = 0


class Http:
    """Anonymous HTTPS to GitHub and the custom domain only (no credentials)."""

    def __init__(self, *, timeout: int = HTTP_TIMEOUT):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_SafeRedirects())

    def request(self, method: str, url: str, *, limit: int, headers: dict | None = None,
                keep_body: bool = True) -> HttpResponse:
        if method not in ("GET", "HEAD") or not _allowed_url(url):
            raise UploadError("http-url", ascii(url)[:160])
        request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
        failure = None
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            result = HttpResponse(error.code, {key.lower(): value for key, value in error.headers.items()})
            error.close()
            return result
        except UploadError as error:
            failure = (error.code, error.detail)
        except Exception as error:  # noqa: BLE001 - reduced to its class name
            failure = ("http-error", type(error).__name__)
        if failure:
            raise UploadError(*failure)
        try:
            with response:
                status = response.status
                head = {key.lower(): value for key, value in response.headers.items()}
                if method == "HEAD":
                    return HttpResponse(status, head)
                hasher, chunks, total = hashlib.sha256(), [], 0
                while chunk := response.read(1 << 20):
                    total += len(chunk)
                    if total > limit:
                        failure = ("http-too-large", url)
                        break
                    hasher.update(chunk)
                    if keep_body:
                        chunks.append(chunk)
        except Exception as error:  # noqa: BLE001
            failure = ("http-error", type(error).__name__)
        if failure:
            raise UploadError(*failure)
        return HttpResponse(status, head, b"".join(chunks), hasher.hexdigest(), total)


class GitHubRelease:
    """Anonymous, public reads of published releases (production publish and policy checks)."""

    def __init__(self, http: Http, repository: str = r2.REPOSITORY):
        self.http = http
        self.repository = repository

    def _json(self, url: str):
        response = self.http.request("GET", url, limit=MAX_API_BYTES, headers=API_HEADERS)
        return response.status, strict_json(response.body) if response.status == 200 else None

    def _checked(self, value, code: str) -> dict:
        if (not isinstance(value, dict) or type(value.get("id")) is not int or type(value.get("tag_name")) is not str
                or not _TAG.fullmatch(value["tag_name"])):
            raise UploadError(code, "the GitHub release record is malformed")
        if value.get("draft") is not False:
            raise UploadError("release-draft", value["tag_name"])
        if value.get("prerelease") is not False:
            raise UploadError("release-prerelease", value["tag_name"])
        return value

    def release(self, tag: str) -> dict:
        if type(tag) is not str or not _TAG.fullmatch(tag):
            raise UploadError("release-tag", ascii(tag)[:80])
        status, value = self._json(f"{GITHUB_API}repos/{self.repository}/releases/tags/{tag}")
        if status == 404:
            raise UploadError("release-not-published", f"{tag} is not a published release (drafts are not public)")
        if status != 200:
            raise UploadError("github-api", f"HTTP {status}")
        value = self._checked(value, "release-record")
        if value["tag_name"] != tag:
            raise UploadError("release-record", "the API returned another tag")
        return value

    def latest(self) -> dict:
        status, value = self._json(f"{GITHUB_API}repos/{self.repository}/releases/latest")
        if status != 200:
            raise UploadError("github-latest", f"HTTP {status}")
        return self._checked(value, "latest-record")

    def _asset_entry(self, release: dict, name: str) -> dict | None:
        assets = release.get("assets")
        found = next((asset for asset in assets or [] if isinstance(asset, dict) and asset.get("name") == name), None)
        page = 1
        while found is None and page <= 10:
            status, rows = self._json(f"{GITHUB_API}repos/{self.repository}/releases/{release['id']}/assets"
                                      f"?per_page=100&page={page}")
            if status != 200 or not isinstance(rows, list) or not rows:
                break
            found = next((asset for asset in rows if isinstance(asset, dict) and asset.get("name") == name), None)
            page += 1
        return found

    def asset(self, release: dict, name: str, limit: int) -> bytes:
        entry = self._asset_entry(release, name)
        if entry is None:
            raise UploadError("release-asset-missing", name)
        if entry.get("state") != "uploaded" or type(entry.get("size")) is not int or not 0 < entry["size"] <= limit:
            raise UploadError("release-asset", name)
        url = f"{GITHUB_DOWNLOADS}{release['tag_name']}/{urllib.parse.quote(name)}"
        response = self.http.request("GET", url, limit=limit)
        if response.status != 200 or response.length != entry["size"]:
            raise UploadError("release-asset-download", f"{name} HTTP {response.status}")
        return response.body


# --- Publish ---------------------------------------------------------------------------

@dataclass
class CheckedRelease:
    platform: str
    pointer_bytes: bytes
    pointer: dict
    manifest_bytes: bytes
    manifest: dict
    manifest_sha256: str
    manifest_key: str
    pointer_key: str

    @property
    def sequence(self) -> int:
        return self.pointer["sequence"]


@dataclass
class LiveState:
    sequence: int | None
    condition: dict
    already_live: bool


class LocalRelease:
    """Self-test only: pointer and manifest envelopes from local files."""

    def __init__(self, files: dict, *, selftest: bool):
        if not selftest:
            raise UploadError("publish-file-input", "file inputs are accepted only in self-test mode")
        self.files = {platform: (Path(pointer), Path(manifest)) for platform, (pointer, manifest) in files.items()}

    def pointer(self, platform: str) -> bytes:
        return _read_limited(self.files[platform][0], r2.MAX_POINTER_BYTES, "pointer-file")

    def manifest(self, platform: str, version: str) -> bytes:
        return _read_limited(self.files[platform][1], r2.MAX_ENVELOPE_BYTES, "manifest-file")


def check_release_pair(pointer_bytes: bytes, manifest_for, *, platform: str, public_pem: bytes,
                       prefix: str | None = None, commit: str | None = None, release_id: int | None = None,
                       rollback: bool = False) -> CheckedRelease:
    """Verify a signed pointer and the signed manifest it names (no R2 access)."""
    pointer_raw, pointer = verify_envelope(pointer_bytes, public_pem, limit=r2.MAX_POINTER_BYTES)
    r2.validate_pointer(pointer, platform=platform, prefix=prefix)
    if r2.pointer_bytes(pointer, platform=platform, prefix=prefix) != pointer_raw:
        raise UploadError("pointer-not-canonical", platform)
    target = pointer["target"]
    if commit is not None and target["commit"] != commit:
        raise UploadError("pointer-commit", f"{platform}: the pointer names another commit")
    if release_id is not None and pointer["release_id"] != release_id:
        raise UploadError("pointer-release-id", f"{platform}: the pointer was signed for another release")
    if pointer["rollback"] is not rollback:
        raise UploadError("rollback-mismatch", f"{platform}: pass --rollback exactly for a signed rollback pointer")
    manifest_bytes = manifest_for(platform, target["version"])
    digest = r2.sha256_hex(manifest_bytes)
    if digest != target["manifest"]["sha256"] or len(manifest_bytes) != target["manifest"]["size"]:
        raise UploadError("pointer-manifest-hash", f"{platform}: the manifest differs from the one the pointer names")
    _, manifest = verify_envelope(manifest_bytes, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
    if (type(manifest.get("schema")) is not int or manifest["schema"] != 3 or manifest.get("bootstrap_schema") != 1
            or manifest.get("repository") != r2.REPOSITORY or manifest.get("platform") != platform
            or manifest.get("commit") != target["commit"] or manifest.get("version") != target["version"]):
        raise UploadError("manifest-identity",
                          f"{platform}: the manifest is not the schema-3 release the pointer names")
    r2.validate_manifest_additions(manifest, platform=platform)
    if manifest["sequence"] != target["manifest_sequence"]:
        raise UploadError("pointer-manifest-sequence", platform)
    ancestors = manifest.get("ancestors")
    if type(ancestors) is not list or not all(type(item) is str for item in ancestors):
        raise UploadError("manifest-ancestors", platform)
    return CheckedRelease(platform, pointer_bytes, pointer, manifest_bytes, manifest, digest,
                          r2.manifest_key(platform, digest, prefix=prefix), r2.pointer_key(platform, prefix=prefix))


def check_latest(latest: dict, tag: str, releases: list[CheckedRelease], *, rollback: bool) -> str:
    latest_tag = latest["tag_name"]
    if rollback:
        if latest_tag != tag:
            raise UploadError("release-not-latest", "a rollback pointer goes live only after GitHub latest names it")
        return latest_tag
    if latest_tag == tag:
        raise UploadError("release-already-latest", "forward releases go live on R2 before GitHub latest flips")
    latest_commit = _TAG.fullmatch(latest_tag)[1]
    for release in releases:
        if latest_commit not in release.manifest["ancestors"]:
            raise UploadError("latest-not-ancestor", f"{release.platform}: GitHub latest is not an ancestor")
    return latest_tag


def _release_rows(manifest: dict) -> list[dict]:
    rows = []
    for group in ("packages", "optional_packages"):
        packages = manifest.get(group) or []
        if type(packages) is not list:
            raise UploadError("manifest-packages", group)
        for package in packages:
            parts = package.get("parts") if isinstance(package, dict) else None
            if type(parts) is not list or not parts:
                raise UploadError("manifest-packages", group)
            rows.extend(parts)
    for kind in ("updater", "uninstall"):
        if kind in manifest:
            rows.append(manifest[kind])
    unique = {}
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("url")) is not str or type(row.get("size")) is not int
                or row["size"] < 1 or type(row.get("sha256")) is not str
                or not re.fullmatch("[0-9a-f]{64}", row["sha256"])):
            raise UploadError("manifest-row", "a download row is malformed")
        if unique.setdefault(row["url"], row) != row:
            raise UploadError("manifest-row", "one URL with two identities")
    return list(unique.values())


def check_release_objects(bucket: Bucket, http, release: CheckedRelease, receipt: Receipt, *, prefix: str | None,
                          workers: int) -> int:
    """HEAD every part the manifest names (S3 for R2 rows, anonymous for GitHub
    rows) and the content set, before anything is written."""
    github = f"{GITHUB_DOWNLOADS}"

    def check(row: dict) -> None:
        if row["url"] == r2.part_url(row["sha256"]):
            key = r2.part_key(row["sha256"], prefix=prefix)
            head = bucket.head(key)
            if head is None:
                raise UploadError("part-missing", key)
            if not _matches(head, size=row["size"], sha256=row["sha256"],
                            headers=r2.object_headers(key, row["sha256"], selftest=bucket.selftest)):
                raise UploadError("part-mismatch", key)
        elif row["url"].startswith(github + "client-"):
            response = http.request("HEAD", row["url"], limit=0)
            if response.status != 200 or response.headers.get("content-length") != str(row["size"]):
                raise UploadError("github-row", f"HTTP {response.status}")
        else:
            raise UploadError("part-host", ascii(row["url"])[:160])
    rows = _release_rows(release.manifest)
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check, row): row for row in rows}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as error:  # noqa: BLE001
                failed += 1
                receipt.add_failure(futures[future]["url"], error_code(error))
    content = release.manifest["content"]
    if content["source"] == "r2":
        key = r2.set_key(release.platform, content["set"]["sha256"], prefix=prefix)
        head = bucket.head(key)
        if head is None or (head.get("Metadata") or {}).get("sha256") != content["set"]["sha256"]:
            failed += 1
            receipt.add_failure(key, "set-missing")
    if failed:
        raise UploadError("release-objects", f"{release.platform}: {failed} of {len(rows)} named objects are missing")
    return len(rows)


def check_live_pointer(bucket: Bucket, release: CheckedRelease, *, high_water: dict, public_pem: bytes,
                       prefix: str | None) -> LiveState:
    """Read and verify the live pointer; decide the write condition. Writes nothing."""
    mark = high_water.get(release.platform, 0)
    live = bucket.get(release.pointer_key, r2.MAX_POINTER_BYTES)
    if live is None:
        if mark:
            raise UploadError("live-pointer-missing", f"{release.platform}: the receipt records an earlier pointer")
        return LiveState(None, {"IfNoneMatch": "*"}, False)
    data, etag = live
    if data == release.pointer_bytes:
        if release.sequence < mark:
            raise UploadError("live-pointer-rolled-back", f"{release.platform}: older than the receipt's pointer")
        return LiveState(release.sequence, {}, True)
    problem = None
    try:
        _, payload = verify_envelope(data, public_pem, limit=r2.MAX_POINTER_BYTES)
        r2.validate_pointer(payload, platform=release.platform, prefix=prefix)
    except r2.DesktopR2Error as error:
        problem = error.code
    if problem:
        raise UploadError("live-pointer-unverifiable", f"{release.platform}: {problem}; stop and report")
    sequence = payload["sequence"]
    if sequence < mark:
        raise UploadError("live-pointer-rolled-back",
                          f"{release.platform}: live sequence {sequence} < receipt {mark}; stop and report")
    if release.sequence <= sequence:
        raise UploadError("pointer-stale", f"{release.platform}: pointer {release.sequence} <= live {sequence}; "
                                           "re-run the publish job so it signs a newer pointer")
    if type(etag) is not str or not _ETAG.fullmatch(etag):
        raise UploadError("live-pointer-etag", release.platform)
    return LiveState(sequence, {"IfMatch": etag}, False)


def _load_high_water(receipt_path: Path) -> dict:
    """The last pointer sequence per platform, from the previous publish receipt at this path."""
    if not receipt_path.exists():
        return {}
    state = strict_json(_read_limited(receipt_path, MAX_STATE_BYTES, "receipt-state"))
    marks = state.get("high_water") if isinstance(state, dict) else None
    if (not isinstance(state, dict) or state.get("kind") != RECEIPT_KIND or state.get("mode") != "publish"
            or not isinstance(marks, dict)
            or any(key not in r2.PLATFORMS or type(value) is not int or value < 0 for key, value in marks.items())):
        raise UploadError("receipt-state", "the previous publish receipt is unreadable; refusing to lose its sequences")
    return dict(marks)


def publish_checked(bucket: Bucket, http, releases: list[CheckedRelease], receipt: Receipt, *, public_pem: bytes,
                    high_water: dict, prefix: str | None, workers: int, sleep=time.sleep) -> dict:
    """Pre-flight every platform, then per platform: manifest (immutable), then
    pointer (IfMatch), then S3 and anonymous read-back. A failure before a
    pointer PUT leaves that platform's live pointer as it was."""
    selftest = prefix is not None
    live = {}
    for release in releases:
        count = check_release_objects(bucket, http, release, receipt, prefix=prefix, workers=workers)
        live[release.platform] = check_live_pointer(bucket, release, high_water=high_water, public_pem=public_pem,
                                                    prefix=prefix)
        emit(f"{release.platform}: {count} named objects present; live pointer "
             f"{'already this release' if live[release.platform].already_live else 'checked'}")
    platforms = {}
    for release in releases:
        state = live[release.platform]
        manifest_result = put_immutable(bucket, release.manifest_key, release.manifest_bytes,
                                        size=len(release.manifest_bytes), sha256=release.manifest_sha256)
        receipt.add_object(release.manifest_key, len(release.manifest_bytes), release.manifest_sha256, manifest_result)
        if state.already_live:
            pointer_result = "already-live"
        else:
            raced = False
            try:
                put_pointer(bucket, release.pointer_key, release.pointer_bytes, sequence=release.sequence,
                            condition=state.condition)
            except SdkError as error:
                if not error.precondition_failed:
                    raise
                raced = True
            if raced:
                # A retried PUT whose first attempt R2 accepted also ends in 412:
                # then the live pointer is already this one.
                current = bucket.get(release.pointer_key, r2.MAX_POINTER_BYTES)
                if current is None or current[0] != release.pointer_bytes:
                    raise UploadError("pointer-race",
                                      f"{release.platform}: the live pointer changed; nothing was replaced")
            pointer_result = "published"
        # R2 accepted (or already holds) this pointer: record its sequence on disk
        # before any read-back, so a later failure or a killed run keeps the mark.
        high_water[release.platform] = max(high_water.get(release.platform, 0), release.sequence)
        receipt.set(high_water=high_water)
        receipt.write(final=False)
        receipt.add_object(release.pointer_key, len(release.pointer_bytes), r2.sha256_hex(release.pointer_bytes),
                           pointer_result)
        check = bucket.get(release.pointer_key, r2.MAX_POINTER_BYTES)
        if check is None or check[0] != release.pointer_bytes:
            raise UploadError("pointer-verify", release.platform)
        public = {}
        for name, key, data in (("pointer", release.pointer_key, release.pointer_bytes),
                                ("manifest", release.manifest_key, release.manifest_bytes)):
            response = http.request("GET", r2.public_url(key, selftest=selftest), limit=len(data))
            public[name] = {"status": response.status, "sha256": response.sha256,
                            "cache": response.headers.get("cf-cache-status")}
            if response.status != 200 or response.body != data:
                raise UploadError("public-verify", f"{release.platform} {name}: the custom domain serves other bytes")
        platforms[release.platform] = {
            "result": pointer_result, "manifest_key": release.manifest_key, "manifest_sha256": release.manifest_sha256,
            "pointer_key": release.pointer_key, "sequence": release.sequence, "previous_sequence": state.sequence,
            "commit": release.pointer["target"]["commit"], "rollback": release.pointer["rollback"],
            "live_pointer_verified": True, "public": public}
        receipt.set(high_water=high_water, platforms=platforms)
        emit(f"{release.platform}: pointer {pointer_result} (sequence {release.sequence})")
        if selftest and pointer_result == "published" and release is not releases[-1]:
            sleep(POINTER_WRITE_INTERVAL)
    return platforms


def run_publish(tag: str, platforms, credentials, receipt_path, *, rollback: bool = False, source=None, http=None,
                client_factory=None, workers: int = MAX_WORKERS) -> dict:
    """Production publish: anonymous GitHub reads, committed release key, no file inputs."""
    if source is not None and not isinstance(source, GitHubRelease):
        raise UploadError("publish-file-input", "production publish reads releases only from GitHub")
    receipt_path = private_path(receipt_path, "receipt")
    check_workers(workers)
    platforms = list(platforms)
    if not platforms or len(set(platforms)) != len(platforms) or any(p not in r2.PLATFORMS for p in platforms):
        raise UploadError("platforms", "name each platform once")
    if type(tag) is not str or not _TAG.fullmatch(tag):
        raise UploadError("release-tag", ascii(tag)[:80])
    high_water = _load_high_water(receipt_path)
    receipt = Receipt(receipt_path, "publish", release=tag, high_water=dict(high_water), rollback=rollback)
    try:
        config = load_config(credentials)
        http = http or Http()
        source = source or GitHubRelease(http)
        public_pem = committed_public_key()
        record = source.release(tag)
        releases = []
        for platform in platforms:
            pointer_bytes = source.asset(record, r2.pointer_asset_name(platform), r2.MAX_POINTER_BYTES)
            releases.append(check_release_pair(
                pointer_bytes, lambda p, version: source.asset(record, f"{version}-{p}.json", r2.MAX_ENVELOPE_BYTES),
                platform=platform, public_pem=public_pem, commit=_TAG.fullmatch(tag)[1], release_id=record["id"],
                rollback=rollback))
        receipt.set(latest_before=check_latest(source.latest(), tag, releases, rollback=rollback))
        client = (client_factory or create_client)(config, SdkGuard(bucket=config.bucket))
        bucket = Bucket(client, config.bucket)
        result = publish_checked(bucket, http, releases, receipt, public_pem=public_pem, high_water=high_water,
                                 prefix=None, workers=workers)
        receipt.set(result="complete")
        return {"ok": True, "platforms": result}
    except Exception as error:
        receipt.set(result="failed", error_code=error_code(error))
        raise
    finally:
        receipt.write()


# --- verify-public and check-policy --------------------------------------------------

def _public_get_verified(http, url: str, size: int, sha256: str) -> dict:
    """HEAD first (a premature GET can edge-cache a 404), then GET + SHA-256."""
    head = http.request("HEAD", url, limit=0)
    if head.status != 200 or head.headers.get("content-length") != str(size):
        raise UploadError("public-head", f"HTTP {head.status}")
    response = http.request("GET", url, limit=size, keep_body=False)
    if response.status != 200 or response.length != size or response.sha256 != sha256:
        raise UploadError("public-get", f"HTTP {response.status}")
    return {"head_cache": head.headers.get("cf-cache-status"), "cache": response.headers.get("cf-cache-status"),
            "meta_sha256_exposed": "x-amz-meta-sha256" in head.headers}


def run_verify_public(platform: str, set_sha256: str, *, sample: int | None = None, seed: int | None = None,
                      receipt_path=None, workers: int = MAX_WORKERS, http=None, prefix: str | None = None,
                      public_key_sha256: str | None = None) -> dict:
    """The owner's independent check, through the custom domain only (no credentials)."""
    receipt_path = private_path(receipt_path, "receipt") if receipt_path else None
    check_workers(workers)
    if sample is not None and (type(sample) is not int or sample < 1):
        raise UploadError("sample", "use a positive sample size")
    http = http or Http()
    selftest = prefix is not None
    receipt = Receipt(receipt_path, "verify-public", platform=platform, set_sha256=set_sha256) if receipt_path else None
    try:
        set_url = r2.public_url(r2.set_key(platform, set_sha256, prefix=prefix), selftest=selftest)
        head = http.request("HEAD", set_url, limit=0)
        if head.status != 200:
            raise UploadError("set-missing", f"HTTP {head.status}")
        response = http.request("GET", set_url, limit=r2.MAX_SET_BYTES)
        if response.status != 200 or response.sha256 != set_sha256:
            raise UploadError("set-sha256", "the public set bytes differ from the requested hash")
        content_set = r2.parse_set_bytes(response.body)
        r2.validate_set(content_set, platform=platform, source="r2", reader_cap=r2.READER_CAP_W1A,
                        public_key_sha256=public_key_sha256 or r2.public_key_sha256(committed_public_key()))
        parts = sorted(_set_parts(content_set).items())
        if sample is not None and sample < len(parts):
            seed = seed if seed is not None else secrets.randbits(32)
            parts = sorted(random.Random(seed).sample(parts, sample))
        verified, failed, total = 0, 0, 0

        def check(item):
            sha256, size = item
            return _public_get_verified(http, r2.public_url(r2.part_key(sha256, prefix=prefix), selftest=selftest),
                                        size, sha256)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(check, item): item for item in parts}
            for future in as_completed(futures):
                sha256, size = futures[future]
                key = r2.part_key(sha256, prefix=prefix)
                try:
                    detail = future.result()
                except Exception as error:  # noqa: BLE001
                    failed += 1
                    if receipt:
                        receipt.add_failure(key, error_code(error))
                else:
                    verified += 1
                    total += size
                    if receipt:
                        receipt.add_object(key, size, sha256, "verified", **detail)
        summary = {"ok": failed == 0, "parts": len(parts), "verified": verified, "failed": failed, "bytes": total,
                   "sample_seed": seed}
        emit(f"verify-public {platform} {set_sha256}: {verified}/{len(parts)} parts verified, {failed} failed")
        if receipt:
            receipt.set(result="complete" if failed == 0 else "failed", summary=summary)
        return summary
    except Exception as error:
        if receipt:
            receipt.set(result="failed", error_code=error_code(error))
        raise
    finally:
        if receipt:
            receipt.write()


def run_check_policy(policy_path, *, http=None, receipt_path=None, public_pem: bytes | None = None) -> dict:
    """Both live pointers verify and name required_commit; so does GitHub latest."""
    receipt_path = private_path(receipt_path, "receipt") if receipt_path else None
    receipt = Receipt(receipt_path, "check-policy") if receipt_path else None
    try:
        result = _check_policy(policy_path, http=http or Http(), public_pem=public_pem or committed_public_key())
        if receipt:
            receipt.set(result="complete", summary=result)
        return result
    except Exception as error:
        if receipt:
            receipt.set(result="failed", error_code=error_code(error))
        raise
    finally:
        if receipt:
            receipt.write()


def _check_policy(policy_path, *, http, public_pem: bytes) -> dict:
    policy = strict_json(_read_limited(Path(policy_path), 1024 * 1024, "policy-unreadable"))
    if (not isinstance(policy, dict) or policy.get("schema") != 1 or not r2.valid_commit(policy.get("required_commit"))
            or type(policy.get("enforce")) is not bool or not isinstance(policy.get("manifests"), dict)):
        raise UploadError("policy-shape", "expected {schema 1, required_commit, enforce, manifests}")
    commit = policy["required_commit"]
    if set(policy["manifests"]) != set(r2.PLATFORMS):
        raise UploadError("policy-manifests", "the policy must name a manifest for every platform")
    result = {"required_commit": commit, "platforms": {}}
    for platform in r2.PLATFORMS:
        response = http.request("GET", r2.pointer_url(platform), limit=r2.MAX_POINTER_BYTES)
        if response.status != 200:
            raise UploadError("live-pointer-missing", f"{platform}: HTTP {response.status}")
        _, pointer = verify_envelope(response.body, public_pem, limit=r2.MAX_POINTER_BYTES)
        r2.validate_pointer(pointer, platform=platform)
        target = pointer["target"]
        if target["commit"] != commit:
            raise UploadError("pointer-commit", f"{platform}: the live pointer names another commit")
        manifest = http.request("GET", target["manifest"]["url"], limit=target["manifest"]["size"])
        if manifest.status != 200 or manifest.sha256 != target["manifest"]["sha256"]:
            raise UploadError("live-manifest", f"{platform}: the pointer's manifest is not served")
        _, payload = verify_envelope(manifest.body, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
        if payload.get("commit") != commit or payload.get("platform") != platform:
            raise UploadError("live-manifest", f"{platform}: the manifest names another release")
        github_url = f"{GITHUB_DOWNLOADS}client-{commit}/{target['version']}-{platform}.json"
        if policy["manifests"][platform] not in (github_url, target["manifest"]["url"]):
            raise UploadError("policy-manifests", f"{platform}: the policy names another manifest")
        result["platforms"][platform] = {"sequence": pointer["sequence"],
                                         "manifest_sha256": target["manifest"]["sha256"]}
    latest = GitHubRelease(http).latest()
    if latest["tag_name"] != f"client-{commit}":
        raise UploadError("latest-commit", "GitHub latest names another release")
    result["ok"] = True
    emit(f"Policy {commit} matches both live pointers and GitHub latest.")
    return result


# --- Self-test ----------------------------------------------------------------------

def _selftest_state(work: Path, sizes) -> dict:
    path = work / "state.json"
    if path.exists():
        state = strict_json(_read_limited(path, MAX_STATE_BYTES, "selftest-state"))
        problem = None
        try:
            if state.get("kind") != "rabbitlands-desktop-selftest-state":
                problem = "state.json is malformed"
            elif r2.selftest_prefix(*state["prefix"][len(r2.SELFTEST_ROOT):-1].split("-", 1)) != state["prefix"]:
                problem = "state.json names another prefix form"
            elif [row["size"] for row in state["parts"]] != list(sizes):
                problem = "this work folder was made with other part sizes"
            elif not all(re.fullmatch("[0-9a-f]{64}", state[name]) for name in ("conflict_x", "conflict_b")):
                problem = "state.json is malformed"
            elif (not r2.MIN_SEQUENCE <= state["sequence"] < r2.MAX_SEQUENCE - 100
                  or not r2.valid_commit(state["commit"])):
                problem = "state.json is malformed"
        except (AttributeError, KeyError, TypeError, ValueError, r2.DesktopR2Error):
            problem = "state.json is malformed"
        if problem:
            raise UploadError("selftest-state", problem)
        return state
    prefix = r2.new_selftest_prefix()
    state = {"kind": "rabbitlands-desktop-selftest-state", "prefix": prefix, "created_utc": _utc_now(),
             "sequence": int(time.time()), "commit": hashlib.sha256(prefix.encode("ascii")).hexdigest()[:40],
             "parts": []}
    parts = work / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    for size in sizes:
        data = os.urandom(size)
        digest = r2.sha256_hex(data)
        (parts / f"{digest}.bin").write_bytes(data)
        state["parts"].append({"size": size, "sha256": digest})
    for name in ("x", "b"):
        data = os.urandom(64 * 1024)
        (work / "conflict").mkdir(exist_ok=True)
        (work / "conflict" / f"{name}.bin").write_bytes(data)
        state[f"conflict_{name}"] = r2.sha256_hex(data)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (work / "keys").mkdir(exist_ok=True)
    write_private(work / "keys" / "selftest-private.pem", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    write_private(work / "keys" / "selftest-public.pem", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    write_private(path, json.dumps(state, indent=2, sort_keys=True).encode("ascii"))
    return state


def selftest_materials(work: Path, state: dict) -> dict:
    """Deterministic set, plans, manifest and pointers for this work folder's state."""
    prefix, commit, sequence = state["prefix"], state["commit"], state["sequence"]
    public_pem = require_test_key(_read_limited(work / "keys" / "selftest-public.pem", 64 * 1024, "selftest-key"))
    private_pem = _read_limited(work / "keys" / "selftest-private.pem", 64 * 1024, "selftest-key")
    for row in state["parts"]:
        path = work / "parts" / f"{row['sha256']}.bin"
        if not path.is_file() or path.stat().st_size != row["size"] or hash_file(path) != row["sha256"]:
            raise UploadError("selftest-state", f"part {row['sha256']} is missing or changed")
    date = prefix[len(r2.SELFTEST_ROOT):len(r2.SELFTEST_ROOT) + 8]
    version = f"RabbitLands-Windows-{date}-{commit[:9]}"
    names = [("release-descriptor", "app/client-release.json"), ("client", "app/RabbitLands.pck")]
    names += [(f"selftest-{index}", f"eloria-assets/selftest/part-{index}.bin")
              for index in range(2, len(state["parts"]))]
    packages = []
    for (pid, path), row in zip(names, state["parts"]):
        packages.append({"id": pid, "sha256": row["sha256"], "size": row["size"], "unpacked_size": row["size"],
                         "file_count": 1, "files": [{"path": path, "size": row["size"], "sha256": row["sha256"]}],
                         "parts": [{"url": r2.part_url(row["sha256"]), "size": row["size"], "sha256": row["sha256"]}]})
    public_sha = r2.public_key_sha256(public_pem)
    content_set = {"kind": r2.SET_KIND, "set_schema": r2.SET_SCHEMA, "source": "r2", "repository": r2.REPOSITORY,
                   "commit": commit, "platform": SELFTEST_PLATFORM, "version": version, "public_key_sha256": public_sha,
                   "asset_base": r2.DESKTOP_ASSETS, "ci_paths": [*r2.CI_PATHS, *r2.CI_PREFIXES],
                   "packages": packages, "optional_packages": [], "builder": {"selftest": True}}
    r2.validate_set(content_set, public_key_sha256=public_sha, platform=SELFTEST_PLATFORM, source="r2")
    set_bytes = r2.canonical_bytes(content_set)
    set_sha = r2.sha256_hex(set_bytes)
    write_private(work / "set.json", set_bytes)
    rows = [{"key": r2.part_key(row["sha256"], prefix=prefix), "sha256": row["sha256"], "size": row["size"]}
            for row in state["parts"]]
    for name, kind in (("upload-plan.json", "new"), ("upload-plan-reused.json", "reused")):
        plan = {"kind": PLAN_KIND, "plan_schema": PLAN_SCHEMA, "platform": SELFTEST_PLATFORM, "set_sha256": set_sha,
                "set_bytes_path": "set.json",
                "rows": [{**row, "kind": kind,
                          **({"local_path": f"parts/{row['sha256']}.bin"} if kind == "new" else {})}
                         for row in rows]}
        write_private(work / name, (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("ascii"))
    release = {"schema": 3, "bootstrap_schema": 1, "repository": r2.REPOSITORY, "commit": commit, "ancestors": [commit],
               "launch_args": [], "platform": SELFTEST_PLATFORM, "version": version,
               "size": sum(p["size"] for p in packages), "unpacked_size": sum(p["unpacked_size"] for p in packages),
               "file_count": sum(p["file_count"] for p in packages),
               "sha256": r2.sha256_hex(json.dumps(packages, sort_keys=True, separators=(",", ":")).encode("ascii")),
               "packages": packages, "parts": [part for p in packages for part in p["parts"]],
               **r2.manifest_additions(platform=SELFTEST_PLATFORM, sequence=sequence,
                                       helpers_fingerprint=r2.sha256_hex(b"rabbitlands-selftest"), root_files=[],
                                       source="r2", set_sha256=set_sha)}
    manifest = sign_envelope(r2.canonical_bytes(release), private_pem)
    write_private(work / "manifest-windows.json", manifest)
    pointers = []
    for index, offset in ((1, 10), (2, 20)):
        payload = r2.pointer_payload(platform=SELFTEST_PLATFORM, sequence=sequence + offset, rollback=False,
                                     release_id=1, run_id=index, commit=commit, version=version,
                                     manifest_sequence=sequence, manifest_sha256=r2.sha256_hex(manifest),
                                     manifest_size=len(manifest), prefix=prefix)
        data = sign_envelope(r2.pointer_bytes(payload, platform=SELFTEST_PLATFORM, prefix=prefix), private_pem)
        write_private(work / f"pointer-{index}-windows.json", data)
        pointers.append(work / f"pointer-{index}-windows.json")
    planned = (sum(row["size"] for row in state["parts"]) + len(set_bytes) + len(manifest)
               + sum(path.stat().st_size for path in pointers) + 2 * 64 * 1024)
    return {"prefix": prefix, "public_pem": public_pem, "set_sha256": set_sha, "set_bytes": set_bytes,
            "manifest": work / "manifest-windows.json", "pointers": pointers, "planned_bytes": planned}


class _Checks:
    def __init__(self, receipt: Receipt):
        self.receipt = receipt
        self.rows = []

    def add(self, name: str, ok: bool, **observed) -> bool:
        """Record one check. A row with `skipped` proved nothing: it prints
        `[skip]`, not `[ok]`, so the console never presents it as a pass."""
        self.rows.append({"name": name, "ok": bool(ok), **observed})
        self.receipt.set(checks=self.rows)
        emit(f"[{'FAIL' if not ok else 'skip' if observed.get('skipped') else 'ok'}] {name}")
        return ok


def _expect_refusal(call) -> str | None:
    """Run `call`; return the refusal code it raised (None when it succeeded)."""
    try:
        call()
    except r2.DesktopR2Error as error:
        return error.code if not isinstance(error, SdkError) else error.receipt_code
    return None


def run_selftest(work, credentials, receipt_path, *, ledger=None, budget_bytes: int = SELFTEST_BUDGET_BYTES,
                 sizes=SELFTEST_SIZES, workers: int = MAX_WORKERS, checksum_header: bool = True, client_factory=None,
                 http=None, sleep=time.sleep) -> dict:
    """The R2 self-test (design App. C, steps 1-8 and 12) under one nonce prefix.

    The work folder keeps the prefix and generated material, so a rerun resumes
    the same objects. The ledger caps PUT bytes across runs at `budget_bytes`.
    Nothing is deleted; objects stay for a later owner-approved cleanup.
    """
    work = private_path(work, "work")
    receipt_path = private_path(receipt_path, "receipt")
    ledger = private_path(ledger or work / "put-ledger.json", "ledger")
    check_workers(workers)
    receipt = Receipt(receipt_path, "selftest")
    checks = _Checks(receipt)
    try:
        work.mkdir(parents=True, exist_ok=True)
        state = _selftest_state(work, sizes)
        materials = selftest_materials(work, state)
        prefix = materials["prefix"]
        receipt.set(prefix=prefix, planned_bytes=materials["planned_bytes"], budget_bytes=budget_bytes)
        if materials["planned_bytes"] > budget_bytes:
            raise UploadError("selftest-budget", f"planned {materials['planned_bytes']} > {budget_bytes} bytes")
        budget = PutBudget(ledger, budget_bytes)
        receipt.set(ledger_before=budget.used)
        config = load_config(credentials)
        http = http or Http()
        client = (client_factory or create_client)(config, SdkGuard(bucket=config.bucket, selftest=True, budget=budget,
                                                                    prefix=prefix))
        bucket = Bucket(client, config.bucket, selftest=True, checksum_header=checksum_header)
        public_sha = r2.public_key_sha256(materials["public_pem"])

        # 2. Upload: every object PUT (or resumed by an earlier run) and verified, the set last.
        plan = load_plan(work / "upload-plan.json", public_key_sha256=public_sha, prefix=prefix)
        check_new_rows(plan, workers=workers, receipt=receipt)
        puts = budget.puts
        # The smallest part alone first: a PUT the bucket refuses outright (the
        # checksum header, a permission) then costs its bytes of the budget, not
        # the whole set's, and a rerun with --no-checksum-header still fits.
        canary = min(plan.rows, key=lambda row: row.size)
        receipt.add_object(canary.key, canary.size, canary.sha256, put_immutable(
            bucket, canary.key, canary.path, size=canary.size, sha256=canary.sha256), phase="canary")
        first = upload_content(bucket, plan, receipt, workers=workers, phase="upload")
        checks.add("upload", all(value in ("uploaded", "resumed") for value in first.results.values()),
                   results=sorted(set(first.results.values())), puts=budget.puts - puts,
                   uploaded_bytes=first.uploaded_bytes,
                   put_bytes_per_second=round(first.uploaded_bytes / first.seconds) if first.uploaded_bytes else None)
        # 3. Reruns: all resumed, then all reused, with no PUT.
        puts = budget.puts
        again = upload_content(bucket, plan, receipt, workers=workers, phase="rerun")
        checks.add("rerun-resumes", set(again.results.values()) == {"resumed"} and budget.puts == puts,
                   puts=budget.puts - puts)
        reused_plan = load_plan(work / "upload-plan-reused.json", public_key_sha256=public_sha, prefix=prefix)
        reused = upload_content(bucket, reused_plan, receipt, workers=workers, phase="reused")
        parts_reused = all(reused.results[row.key] == "reused" for row in reused_plan.rows)
        checks.add("reused-rows", parts_reused and budget.puts == puts, puts=budget.puts - puts)

        # 4. Conflict: other bytes already at X's key are refused and left unchanged.
        x_sha, b_sha = state["conflict_x"], state["conflict_b"]
        conflict_key = f"{prefix}conflict/{x_sha}.bin"
        placed = put_immutable(bucket, conflict_key, work / "conflict" / "b.bin", size=64 * 1024, sha256=b_sha)
        before = bucket.head(conflict_key)
        code = _expect_refusal(lambda: put_immutable(bucket, conflict_key, work / "conflict" / "x.bin",
                                                     size=64 * 1024, sha256=x_sha))
        after = bucket.head(conflict_key)
        unchanged = bool(before and after and before.get("ETag") == after.get("ETag")
                         and (after.get("Metadata") or {}).get("sha256") == b_sha)
        checks.add("conflict-refused", code == "conflict" and unchanged, placed=placed, refusal=code)

        # 5. IfNoneMatch on an existing object: expect 412. The smallest part and
        # its own bytes, so an R2 that ignored the header would change nothing.
        rows_by_size = sorted(plan.rows, key=lambda row: row.size)
        small = rows_by_size[0]
        code = _expect_refusal(lambda: bucket.put(
            small.key, small.path, size=small.size, sha256=small.sha256,
            headers=r2.object_headers(small.key, small.sha256, selftest=True), condition={"IfNoneMatch": "*"}))
        checks.add("if-none-match-412", code is not None and code.endswith(":412"), observed=code)
        head = bucket.head(small.key, checksum=True)
        expected_checksum = _b64(bytes.fromhex(small.sha256))
        checks.add("checksum-sha256", not checksum_header or (head or {}).get("ChecksumSHA256") == expected_checksum,
                   reported=(head or {}).get("ChecksumSHA256") is not None,
                   **({} if checksum_header else {"skipped": "--no-checksum-header: no ChecksumSHA256 was sent"}))

        # 6. Pointers: first with IfNoneMatch, then IfMatch with the live ETag, then a stale ETag -> 412.
        pointer_key = r2.pointer_key(SELFTEST_PLATFORM, prefix=prefix)
        high_water = dict(state.get("high_water") or {})
        live = bucket.get(pointer_key, r2.MAX_POINTER_BYTES)
        pending = list(materials["pointers"])
        live_bytes = live[0] if live else None
        if live_bytes == pending[1].read_bytes():
            pending = []
        elif live_bytes == pending[0].read_bytes():
            pending = pending[1:]
        for index, pointer in enumerate(pending):
            if index:
                sleep(POINTER_WRITE_INTERVAL)
            source = LocalRelease({SELFTEST_PLATFORM: (pointer, materials["manifest"])}, selftest=True)
            checked = check_release_pair(source.pointer(SELFTEST_PLATFORM), source.manifest,
                                         platform=SELFTEST_PLATFORM, public_pem=materials["public_pem"], prefix=prefix)
            publish_checked(bucket, http, [checked], receipt, public_pem=materials["public_pem"],
                            high_water=high_water, prefix=prefix, workers=workers, sleep=sleep)
            state["high_water"] = high_water
            write_private(work / "state.json", json.dumps(state, indent=2, sort_keys=True).encode("ascii"))
        live = bucket.get(pointer_key, r2.MAX_POINTER_BYTES)
        final = materials["pointers"][1].read_bytes()
        checks.add("pointer-if-match", live is not None and live[0] == final, written=len(pending))
        sleep(POINTER_WRITE_INTERVAL)
        stale = '"' + "0" * 32 + '"'
        code = _expect_refusal(lambda: put_pointer(bucket, pointer_key, final, sequence=state["sequence"] + 20,
                                                   condition={"IfMatch": stale}))
        after = bucket.get(pointer_key, r2.MAX_POINTER_BYTES)
        checks.add("pointer-stale-etag-412", code is not None and code.endswith(":412") and after and after[0] == final,
                   observed=code)
        checks.add("lock-rule", True, skipped="no owner lock rule is configured for the self-test prefix")

        # Inventory of this prefix only.
        listed = {row["key"]: row["size"] for row in bucket.list(prefix)}
        expected = {row.key for row in plan.rows} | {plan.set_key, conflict_key, pointer_key,
                                                     r2.manifest_key(SELFTEST_PLATFORM,
                                                                     r2.sha256_hex(materials["manifest"].read_bytes()),
                                                                     prefix=prefix)}
        checks.add("inventory", expected <= set(listed) and all(key.startswith(prefix) for key in listed),
                   objects=len(listed), bytes=sum(listed.values()))

        # 8. Anonymous HTTPS on the custom domain: HEAD before every GET (records cache behaviour).
        public, public_failures = {}, 0
        for row in rows_by_size:
            url = r2.public_url(row.key, selftest=True)
            try:
                detail = _public_get_verified(http, url, row.size, row.sha256)
                if row.size <= 8 * 1024 * 1024:
                    again = http.request("GET", url, limit=row.size, keep_body=False)
                    detail["second_cache"] = again.headers.get("cf-cache-status")
                    detail["second_sha256_ok"] = again.sha256 == row.sha256
                else:
                    ranged = http.request("GET", url, limit=1 << 20, headers={"Range": "bytes=0-1048575"})
                    detail["range_status"] = ranged.status
                    detail["content_range"] = ranged.headers.get("content-range")
            except r2.DesktopR2Error as error:
                public_failures += 1
                detail = {"error_code": error_code(error)}
            public[row.key] = detail
        probe = rows_by_size[min(1, len(rows_by_size) - 1)]
        updater = http.request("GET", r2.public_url(probe.key, selftest=True), limit=probe.size,
                               headers=UPDATER_HEADERS, keep_body=False)
        checks.add("public-parts", public_failures == 0 and updater.status == 200 and updater.sha256 == probe.sha256,
                   parts=public, updater_headers={"status": updater.status,
                                                  "cache": updater.headers.get("cf-cache-status"),
                                                  "sha256_ok": updater.sha256 == probe.sha256})
        large = [detail for detail in public.values() if "range_status" in detail]
        checks.add("public-range-206", bool(large) and all(detail["range_status"] == 206 for detail in large),
                   checked=len(large))
        json_cache = {}
        for name, key, data in (("set", plan.set_key, materials["set_bytes"]),
                                ("pointer", pointer_key, final)):
            response = http.request("GET", r2.public_url(key, selftest=True), limit=len(data))
            json_cache[name] = {"status": response.status, "equal": response.body == data,
                                "cache": response.headers.get("cf-cache-status")}
        checks.add("public-json", all(row["status"] == 200 and row["equal"] for row in json_cache.values()),
                   objects=json_cache)
        ok = all(row["ok"] for row in checks.rows)
        receipt.set(result="complete" if ok else "failed", ledger_after=budget.used, puts_total=budget.puts,
                    public_base=r2.PUBLIC_ORIGIN + prefix)
        return {"ok": ok, "prefix": prefix, "checks": checks.rows, "ledger_bytes": budget.used}
    except Exception as error:
        receipt.set(result="failed", error_code=error_code(error))
        raise
    finally:
        receipt.write()


# --- Command line ------------------------------------------------------------------

def _workers(parser):
    parser.add_argument("--workers", type=int, choices=range(1, MAX_WORKERS + 1), default=MAX_WORKERS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upload_desktop_assets.py", description=__doc__.split("\n\n")[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    content = modes.add_parser("content", help="upload a content set's parts from an upload plan, then the set")
    content.add_argument("--plan", required=True, type=Path)
    content.add_argument("--credentials", required=True, type=Path)
    content.add_argument("--receipt", required=True, type=Path)
    content.add_argument("--release-local-parts", action="store_true",
                         help="after a verified upload, mark new rows reused and delete their local files")
    content.add_argument("--no-checksum-header", action="store_true")
    _workers(content)
    publish = modes.add_parser("publish", help="copy a published release's manifest and pointer to R2")
    publish.add_argument("--release", required=True, help="client-<40 hex commit>")
    publish.add_argument("--platform", required=True, action="append", choices=r2.PLATFORMS)
    publish.add_argument("--credentials", required=True, type=Path)
    publish.add_argument("--receipt", required=True, type=Path, help="reuse the same path: it keeps the sequences")
    publish.add_argument("--rollback", action="store_true", help="the signed pointer is a rollback pointer")
    _workers(publish)
    selftest = modes.add_parser("selftest", help="the small end-to-end proof under desktop/selftest/")
    selftest.add_argument("--work", required=True, type=Path)
    selftest.add_argument("--credentials", required=True, type=Path)
    selftest.add_argument("--receipt", required=True, type=Path)
    selftest.add_argument("--ledger", required=True, type=Path,
                          help="PUT byte ledger; pass the same path to every self-test run (100 MB cap in total)")
    selftest.add_argument("--no-checksum-header", action="store_true")
    _workers(selftest)
    verify = modes.add_parser("verify-public", help="anonymous HEAD, GET and SHA-256 of a set's parts")
    verify.add_argument("--platform", required=True, choices=r2.PLATFORMS)
    verify.add_argument("--set-sha256", required=True)
    verify.add_argument("--sample", type=int)
    verify.add_argument("--seed", type=int)
    verify.add_argument("--receipt", type=Path)
    _workers(verify)
    policy = modes.add_parser("check-policy", help="gate before the server's required_commit changes")
    policy.add_argument("--policy", required=True, type=Path)
    policy.add_argument("--receipt", type=Path)
    return parser


def _dispatch(args) -> dict:
    if args.mode == "content":
        return run_content(args.plan, args.credentials, args.receipt, workers=args.workers,
                           release=args.release_local_parts, checksum_header=not args.no_checksum_header)
    if args.mode == "publish":
        return run_publish(args.release, args.platform, args.credentials, args.receipt, rollback=args.rollback,
                           workers=args.workers)
    if args.mode == "selftest":
        return run_selftest(args.work, args.credentials, args.receipt, ledger=args.ledger, workers=args.workers,
                            checksum_header=not args.no_checksum_header)
    if args.mode == "verify-public":
        if not re.fullmatch("[0-9a-f]{64}", args.set_sha256):
            raise UploadError("set-sha256", "expected 64 lowercase hex digits")
        return run_verify_public(args.platform, args.set_sha256, sample=args.sample, seed=args.seed,
                                 receipt_path=args.receipt, workers=args.workers)
    return run_check_policy(args.policy, receipt_path=args.receipt)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _dispatch(args)
    except IncompleteError as error:
        emit(f"Incomplete: {error}. The receipt lists each failure; a rerun resumes.", error=True)
        return 1
    except r2.DesktopR2Error as error:
        emit(f"Refused: {error}", error=True)
        return 2
    except KeyboardInterrupt:
        emit("Interrupted.", error=True)
        return 130
    except Exception as error:  # noqa: BLE001 - never print exception text (it can name the endpoint)
        emit(f"Failed: {error_code(error)}", error=True)
        return 1
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Signed desktop release manifests and pointers, built and signed in Python.

One writer for the release payload of the R2 workflow (desktop-release-r2.yml):

  payload()        the schema-2 or schema-3 release payload: the content set's
                   packages (R2 or GitHub-pool rows), the CI packages (`engine`,
                   `native-runtime`, GitHub pool) and the updater/uninstaller
                   rows (legacy `client-assets` pool), with the same fields,
                   order rules and totals as client_release.publish_artifacts,
                   plus the signed R2 fields `sequence`, `helpers_fingerprint`,
                   `root_files` and `content`
  check_payload()  a Python mirror of package_updates.gd validate, plus the R2
                   and schema rules, run before anything is signed
  sign()/verify()  RSA PKCS#1 v1.5 over SHA-256 of the exact payload bytes, the
                   envelope `{"payload", "signature"}` that sign_client_release.gd
                   writes and Release.verify_envelope reads
  pointer_envelope()  the signed release pointer (desktop_r2 pointer v1)

The schema follows the packaged commit's own reader: schema 3 only when that
commit's src/updates/release.gd declares `const CODEC_SCHEMA := 3` (UD-05u),
otherwise schema 2. Derived R2 part rows also need the R2-aware reader, which
declares `const DESKTOP_ASSETS := "<desktop_r2.DESKTOP_ASSETS>"` (W1a); without
it an `r2` content source is refused, so CI never signs a manifest whose own
updater would reject it.

Trust: the release key signs; R2 and GitHub are transport. Signing is
deterministic, so a Python signature equals the one sign_client_release.gd makes
for the same key and payload bytes. The private key never leaves memory here.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import subprocess

import desktop_r2 as r2

SCHEMA_PACKAGES = 2
SCHEMA_CODEC = 3
BOOTSTRAP_SCHEMA = 1
HELPER_KINDS = ("updater", "uninstall")
HELPER_EXTENSIONS = {"windows": "exe", "linux": "x86_64"}
ENGINE_PACKAGE, NATIVE_PACKAGE = r2.CI_PACKAGE_IDS
ENGINE_PATHS = {"windows": "app/RabbitLands.exe", "linux": "app/RabbitLands.x86_64"}
NATIVE_PREFIX = r2.CI_PREFIXES[0]
MAX_LAUNCH_ARGS = 32
MAX_LAUNCH_ARG = 4096
MAX_HELPER_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_FILES = 100000
MAX_ANCESTORS = 100000
MAX_ROOT_FILES = 64     # launchers, README, credits, launch defaults: a handful
RELEASE_GD = "godot-client/src/updates/release.gd"
PACKAGE_UPDATES_GD = "godot-client/src/updates/package_updates.gd"
PUBLIC_KEY = "godot-client/data/update_public.pem"
POOL_BASE = f"https://github.com/{r2.REPOSITORY}/releases/download/{r2.POOL_TAG}"

# The reader declarations, matched on whole lines of the commit's GDScript.
_CODEC_SCHEMA = re.compile(r"^const CODEC_SCHEMA := 3[ \t]*(?:#.*)?$", re.M)
_DESKTOP_ASSETS = re.compile(r'^const DESKTOP_ASSETS := "' + re.escape(r2.DESKTOP_ASSETS) + r'"[ \t]*(?:#.*)?$', re.M)
_PACKAGE_LIMIT = re.compile(r"release\.packages\.size\(\) > ([0-9]{1,6})")
_HELPER_NAME = re.compile(r"RabbitLands-(updater|uninstall)-([0-9a-f]{64})\.(exe|x86_64)")


class ManifestError(r2.DesktopR2Error):
    pass


class SigningError(r2.DesktopR2Error):
    pass


def _quote(value) -> str:
    text = ascii(value)
    return text if len(text) <= 120 else text[:117] + "..."


def _is_int(value, minimum=0, maximum=r2.MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _is_hash(value) -> bool:
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


# --- What the packaged commit's reader accepts ----------------------------------

class ReaderCapabilities:
    """The manifest features a commit's updater reads, from its own declarations."""

    def __init__(self, *, schema3: bool, r2_rows: bool, package_limit: int):
        self.schema3 = schema3
        self.r2_rows = schema3 and r2_rows
        self.package_limit = package_limit

    @property
    def schema(self) -> int:
        return SCHEMA_CODEC if self.schema3 else SCHEMA_PACKAGES

    @property
    def reader_cap(self) -> int:
        """The part cap validate_set applies: 2000 only with the R2-aware reader (W1a)."""
        return r2.READER_CAP_W1A if self.r2_rows and self.package_limit >= r2.READER_CAP_W1A else r2.READER_CAP

    def __eq__(self, other) -> bool:
        return isinstance(other, ReaderCapabilities) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (f"ReaderCapabilities(schema={self.schema}, r2_rows={self.r2_rows}, "
                f"package_limit={self.package_limit})")


def reader_capabilities(release_gd: str, package_updates_gd: str | None = None) -> ReaderCapabilities:
    """Capabilities from the text of a commit's release.gd (and package_updates.gd).

    The package limit is the smallest `release.packages.size() > N` check in
    package_updates.gd, 850 when none is found: a conservative reading never
    lets CI sign more packages than the reader takes.
    """
    if type(release_gd) is not str:
        raise ManifestError("reader", "release.gd text is required")
    limits = [int(value) for value in _PACKAGE_LIMIT.findall(package_updates_gd or "")]
    limit = min(limits) if limits else r2.READER_CAP
    return ReaderCapabilities(schema3=_CODEC_SCHEMA.search(release_gd) is not None,
                              r2_rows=_DESKTOP_ASSETS.search(release_gd) is not None,
                              package_limit=max(1, min(limit, r2.READER_CAP_W1A)))


def _git_show(repo: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    return result.stdout.decode("utf-8") if result.returncode == 0 else None


def commit_capabilities(repo: Path, commit: str) -> ReaderCapabilities:
    """The reader of `commit` in `repo`, read from Git (no checkout needed)."""
    if not r2.valid_commit(commit):
        raise ManifestError("commit", _quote(commit))
    release_gd = _git_show(repo, commit, RELEASE_GD)
    if release_gd is None:
        raise ManifestError("reader", f"{RELEASE_GD} is missing at {commit}")
    return reader_capabilities(release_gd, _git_show(repo, commit, PACKAGE_UPDATES_GD))


def commit_public_key(repo: Path, commit: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{PUBLIC_KEY}"], capture_output=True)
    if result.returncode != 0:
        raise ManifestError("public-key", f"{PUBLIC_KEY} is missing at {commit}")
    r2.public_key_sha256(result.stdout)
    return result.stdout


# --- Row rules -------------------------------------------------------------------

def helper_url(sha256: str, kind: str, platform: str) -> str:
    """The legacy `client-assets` URL that released bootstraps download helpers from."""
    return f"{POOL_BASE}/RabbitLands-{kind}-{sha256}.{HELPER_EXTENSIONS[platform]}"


def helper_row_problem(row, kind: str, platform: str) -> str | None:
    if not isinstance(row, dict) or set(row) != {"url", "size", "sha256"}:
        return "helper-row"
    if not _is_hash(row["sha256"]) or not _is_int(row["size"], 1, MAX_HELPER_BYTES):
        return "helper-identity"
    if row["url"] != helper_url(row["sha256"], kind, platform):
        return "helper-url"
    return None


def _ci_part_problem(part) -> str | None:
    if not isinstance(part, dict) or set(part) != {"url", "size", "sha256"}:
        return "ci-part"
    if not _is_hash(part["sha256"]) or not _is_int(part["size"], 1, r2.MAX_PART_BYTES):
        return "ci-part-identity"
    if part["url"] != r2.github_pool_url(part["sha256"]):
        return "ci-part-url"
    return None


def _check_files(package: dict, folded: dict, *, ci: bool, platform: str) -> int:
    files = package.get("files")
    if type(files) is not list or not files or len(files) > MAX_PACKAGE_FILES:
        raise ManifestError("package-files", _quote(package.get("id")))
    unpacked = 0
    for entry in files:
        if not isinstance(entry, dict) or not set(entry) <= {"path", "size", "sha256", "codec"}:
            raise ManifestError("file", _quote(package.get("id")))
        path = entry.get("path")
        if ci:
            if not r2.safe_path(path) or not r2.is_ci_path(path):
                raise ManifestError("ci-package-path", _quote(path))
            expected = ENGINE_PATHS[platform] if package["id"] == ENGINE_PACKAGE else None
            if (expected and path != expected) or (not expected and not path.startswith(NATIVE_PREFIX)):
                raise ManifestError("ci-package-path", _quote(path))
        else:
            problem = r2.path_problem(path)
            if problem:
                raise ManifestError(problem, _quote(path))
        if path.casefold() in folded:
            raise ManifestError("path-duplicate", _quote(path))
        folded[path.casefold()] = path
        if not _is_int(entry.get("size")) or not _is_hash(entry.get("sha256")):
            raise ManifestError("file-identity", _quote(path))
        if "codec" in entry and entry["codec"] not in r2.CODECS:
            raise ManifestError("codec", _quote(path))
        unpacked += entry["size"]
    if package.get("unpacked_size") != unpacked or package.get("file_count") != len(files):
        raise ManifestError("package-totals", _quote(package.get("id")))
    return unpacked


def _check_package(package, *, source: str | None, folded: dict, ids: set, platform: str) -> None:
    if not isinstance(package, dict):
        raise ManifestError("package")
    pid = package.get("id")
    if type(pid) is not str or not re.fullmatch(r"[a-z0-9-]{1,96}", pid) or pid in ids:
        raise ManifestError("package-id", _quote(pid))
    ids.add(pid)
    ci = source is None
    if ci != (pid in r2.CI_PACKAGE_IDS):
        raise ManifestError("package-ci" if not ci else "ci-package-id", pid)
    if "codec" in package and package["codec"] not in r2.CODECS:
        raise ManifestError("codec", pid)
    if not _is_hash(package.get("sha256")) or not _is_int(package.get("size"), 1):
        raise ManifestError("package-identity", pid)
    _check_files(package, folded, ci=ci, platform=platform)
    parts = package.get("parts")
    if type(parts) is not list or not parts:
        raise ManifestError("package-parts", pid)
    for part in parts:
        problem = _ci_part_problem(part) if ci else (
            None if isinstance(part, dict) and _is_hash(part.get("sha256"))
            and _is_int(part.get("size"), 1, r2.MAX_PART_BYTES) and r2.part_url_matches(part, source)
            and set(part) == {"url", "size", "sha256"} else "part")
        if problem:
            raise ManifestError(problem, _quote(part.get("url") if isinstance(part, dict) else part))
    if sum(part["size"] for part in parts) != package["size"]:
        raise ManifestError("package-size", pid)
    if len(parts) == 1 and parts[0]["sha256"] != package["sha256"]:
        raise ManifestError("package-single-part", pid)


def _uses_codec(packages) -> bool:
    return any("codec" in package or any("codec" in entry for entry in package["files"]) for package in packages)


def packages_sha256(packages: list) -> str:
    """The payload's `sha256`: exactly publish_artifacts' digest of its package rows."""
    return hashlib.sha256(json.dumps(packages, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _check_identity(identity) -> None:
    if not isinstance(identity, dict) or identity.get("repository") != r2.REPOSITORY:
        raise ManifestError("identity-repository")
    if not r2.valid_commit(identity.get("commit")):
        raise ManifestError("identity-commit")
    if identity.get("platform") not in r2.PLATFORMS:
        raise ManifestError("identity-platform")
    ancestors = identity.get("ancestors")
    if (type(ancestors) is not list or not ancestors or len(ancestors) > MAX_ANCESTORS
            or ancestors[0] != identity["commit"] or not all(r2.valid_commit(item) for item in ancestors)
            or len(set(ancestors)) != len(ancestors)):
        raise ManifestError("identity-ancestors", "git rev-list of the commit, the commit first")


def _check_version(version, platform: str, commit: str) -> str:
    """`RabbitLands-<Platform>-<8 digits>-<commit[:9]>`: the stage name, no path separators."""
    match = re.fullmatch(r"RabbitLands-(Windows|Linux)-[0-9]{8}-([0-9a-f]{9})", version) \
        if type(version) is str else None
    if not match or match[1].lower() != platform or match[2] != commit[:9]:
        raise ManifestError("version", _quote(version))
    return version


def _check_launch_args(args) -> list:
    if (type(args) is not list or len(args) > MAX_LAUNCH_ARGS
            or not all(type(item) is str and len(item) <= MAX_LAUNCH_ARG for item in args)):
        raise ManifestError("launch-args")
    return list(args)


# --- The payload -----------------------------------------------------------------

def payload(*, identity: dict, version: str, content_packages: list, ci_packages: list, helpers: dict,
            launch_args: list, capabilities: ReaderCapabilities, source: str, set_sha256: str, sequence: int,
            helpers_fingerprint: str, root_files: list, optional_packages: list | None = None) -> dict:
    """The release payload CI signs for one platform.

    Equal to client_release.publish_artifacts' release-payload.json for the same
    rows, apart from the schema (that of the commit's reader), the hosting of
    content parts (derived R2 URLs for `r2`) and the added fields.
    """
    _check_identity(identity)
    platform, commit = identity["platform"], identity["commit"]
    if source not in r2.SOURCES:
        raise ManifestError("source", _quote(source))
    if not isinstance(capabilities, ReaderCapabilities):
        raise ManifestError("reader")
    schema = capabilities.schema
    if source == "r2" and not capabilities.schema3:
        raise ManifestError("r2-needs-schema-3", "the commit's reader lacks the schema-3 declaration")
    if source == "r2" and not capabilities.r2_rows:
        raise ManifestError("reader-lacks-r2", "the commit's reader does not declare the R2 base")
    _check_version(version, platform, commit)
    optional = list(optional_packages or [])
    if optional:
        raise ManifestError("optional-packages", "optional packages wait for the UD-07b reader")
    ids, folded = set(), {}
    for package in content_packages:
        _check_package(package, source=source, folded=folded, ids=ids, platform=platform)
    ci_ids = set()
    for package in ci_packages:
        _check_package(package, source=None, folded=folded, ids=ids, platform=platform)
        ci_ids.add(package["id"])
    if ENGINE_PACKAGE not in ci_ids:
        raise ManifestError("ci-engine-missing")
    for pid, path in r2.REQUIRED_PACKAGES.items():
        if not any(package["id"] == pid and any(entry["path"] == path for entry in package["files"])
                   for package in content_packages):
            raise ManifestError("required-package", pid)
    packages = sorted([*content_packages, *ci_packages], key=lambda package: package["id"])
    if schema == SCHEMA_PACKAGES and _uses_codec(packages):
        raise ManifestError("codec-needs-schema-3")
    parts = [part for package in packages for part in package["parts"]]
    if len(packages) > capabilities.package_limit or len(parts) > capabilities.reader_cap:
        raise ManifestError("reader-cap-exceeded", f"{len(packages)} packages, {len(parts)} parts")
    if not isinstance(helpers, dict) or set(helpers) != set(HELPER_KINDS):
        raise ManifestError("helpers")
    for kind in HELPER_KINDS:
        problem = helper_row_problem(helpers[kind], kind, platform)
        if problem:
            raise ManifestError(problem, kind)
    release = {"schema": schema, "bootstrap_schema": BOOTSTRAP_SCHEMA, "repository": identity["repository"],
               "commit": commit, "ancestors": list(identity["ancestors"]),
               "launch_args": _check_launch_args(launch_args), "platform": platform, "version": version,
               "size": sum(package["size"] for package in packages),
               "unpacked_size": sum(package["unpacked_size"] for package in packages),
               "file_count": sum(package["file_count"] for package in packages),
               "sha256": packages_sha256(packages), "packages": packages, "parts": parts,
               **{kind: dict(helpers[kind]) for kind in HELPER_KINDS}}
    if type(root_files) is not list or len(root_files) > MAX_ROOT_FILES:
        raise ManifestError("root-files", "at most 64 root files")
    release.update(r2.manifest_additions(platform=platform, sequence=sequence,
                                         helpers_fingerprint=helpers_fingerprint, root_files=root_files,
                                         source=source, set_sha256=set_sha256))
    return check_payload(release, identity, capabilities)


def check_payload(release, identity: dict, capabilities: ReaderCapabilities) -> dict:
    """Refuse a payload the commit's updater would refuse (package_updates.gd
    validate mirrored), and anything outside the R2 rules. Returns `release`."""
    _check_identity(identity)
    if not isinstance(release, dict):
        raise ManifestError("payload")
    if type(release.get("schema")) is not int or release["schema"] != capabilities.schema:
        raise ManifestError("schema", _quote(release.get("schema")))
    if release.get("bootstrap_schema") != BOOTSTRAP_SCHEMA or type(release["bootstrap_schema"]) is not int:
        raise ManifestError("bootstrap-schema")
    for field in ("repository", "commit", "platform", "ancestors"):
        if release.get(field) != identity[field]:
            raise ManifestError("identity-" + field)
    platform = identity["platform"]
    _check_launch_args(release.get("launch_args"))
    _check_version(release.get("version"), platform, identity["commit"])
    packages = release.get("packages")
    if type(packages) is not list or not packages or len(packages) > capabilities.package_limit:
        raise ManifestError("packages")
    source = release.get("content", {}).get("source") if isinstance(release.get("content"), dict) else None
    if source not in r2.SOURCES:
        raise ManifestError("content-source")
    if release["schema"] == SCHEMA_PACKAGES and _uses_codec(packages):
        raise ManifestError("codec-needs-schema-3")
    ids, folded, parts = set(), {}, []
    for package in packages:
        is_ci = isinstance(package, dict) and package.get("id") in r2.CI_PACKAGE_IDS
        _check_package(package, source=None if is_ci else source, folded=folded, ids=ids, platform=platform)
        parts.extend(package["parts"])
    if [package["id"] for package in packages] != sorted(package["id"] for package in packages):
        raise ManifestError("package-order")
    if source == "r2" and not capabilities.r2_rows:
        raise ManifestError("reader-lacks-r2")
    if len(parts) > capabilities.reader_cap:
        raise ManifestError("reader-cap-exceeded", f"{len(parts)} parts")
    if parts != release.get("parts"):
        raise ManifestError("parts")
    if sum(package["file_count"] for package in packages) > MAX_PACKAGE_FILES:
        raise ManifestError("file-count", "the updater reads at most 100000 files")
    for name, value in (("size", sum(p["size"] for p in packages)),
                        ("unpacked_size", sum(p["unpacked_size"] for p in packages)),
                        ("file_count", sum(p["file_count"] for p in packages)),
                        ("sha256", packages_sha256(packages))):
        if release.get(name) != value:
            raise ManifestError("totals", name)
    for kind in HELPER_KINDS:
        problem = helper_row_problem(release.get(kind), kind, platform)
        if problem:
            raise ManifestError(problem, kind)
    r2.validate_manifest_additions(release, platform=platform)
    return release


def payload_bytes(release: dict) -> bytes:
    """The exact bytes that are signed: canonical JSON (sorted keys, ASCII, no spaces)."""
    return r2.canonical_bytes(release)


# --- Signing -----------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def envelope_bytes(payload: bytes, signature: bytes) -> bytes:
    """`{"payload":...,"signature":...}`: the bytes sign_client_release.gd writes (JSON.stringify)."""
    return json.dumps({"payload": _b64(payload), "signature": _b64(signature)}, separators=(",", ":"),
                      sort_keys=True).encode("ascii")


def load_signing_key(private_pem: bytes, public_pem: bytes):
    """The release private key, refused unless it is RSA and matches `public_pem`.

    Errors never contain key material.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    private = expected = None
    try:
        private = serialization.load_pem_private_key(private_pem, password=None)
        expected = serialization.load_pem_public_key(public_pem)
    except (TypeError, ValueError, binascii.Error):
        private = expected = None
    if not isinstance(private, rsa.RSAPrivateKey) or not isinstance(expected, rsa.RSAPublicKey):
        raise SigningError("signing-key", "the signing key is not an unencrypted RSA PEM key")
    if private.public_key().public_numbers() != expected.public_numbers():
        raise SigningError("signing-key-mismatch", "the signing key does not match the commit's public key")
    return private


def sign(payload: bytes, private_key) -> bytes:
    """A signed envelope over the exact `payload` bytes (deterministic PKCS#1 v1.5)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    if type(payload) is not bytes or not payload:
        raise SigningError("payload")
    return envelope_bytes(payload, private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256()))


def verify(data: bytes, public_pem: bytes, *, limit: int = r2.CLIENT_MANIFEST_LIMIT) -> tuple[bytes, dict]:
    """Check an envelope's signature against `public_pem`; return payload bytes and object."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    r2.check_envelope(data, limit=limit)
    envelope = json.loads(data)
    payload = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    verified = False
    try:
        serialization.load_pem_public_key(public_pem).verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        verified = True
    except (InvalidSignature, ValueError, TypeError):
        verified = False
    if not verified:
        raise SigningError("signature", "the envelope is not signed by the expected key")
    value = r2._parse_json(payload)
    if not isinstance(value, dict):
        raise SigningError("envelope-payload", "the signed payload is not a JSON object")
    return payload, value


def sign_manifest(release: dict, identity: dict, capabilities: ReaderCapabilities, private_key,
                  public_pem: bytes) -> tuple[bytes, dict]:
    """Check, sign and re-verify one payload; return the envelope and the size gate result."""
    check_payload(release, identity, capabilities)
    data = payload_bytes(release)
    envelope = sign(data, private_key)
    gate = r2.check_envelope(envelope)  # at most 15 MiB: released clients cap manifests at 16 MiB
    signed, value = verify(envelope, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
    if signed != data or value != release:
        raise SigningError("verify-after-sign")
    return envelope, gate


def pointer_envelope(*, platform: str, sequence: int, rollback: bool, release_id: int, run_id: int,
                     manifest: bytes, private_key, public_pem: bytes) -> bytes:
    """Sign a pointer v1 naming the signed `manifest` envelope (its own R2 copy)."""
    _, release = verify(manifest, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
    if release.get("platform") != platform or release.get("schema") != SCHEMA_CODEC:
        raise SigningError("pointer-manifest", "a pointer names a schema-3 manifest of its platform")
    r2.validate_manifest_additions(release, platform=platform)
    value = r2.pointer_payload(platform=platform, sequence=sequence, rollback=rollback, release_id=release_id,
                               run_id=run_id, commit=release["commit"], version=release["version"],
                               manifest_sequence=release["sequence"], manifest_sha256=r2.sha256_hex(manifest),
                               manifest_size=len(manifest))
    envelope = sign(r2.pointer_bytes(value, platform=platform), private_key)
    r2.check_pointer_envelope(envelope)
    verify(envelope, public_pem, limit=r2.MAX_POINTER_BYTES)
    return envelope

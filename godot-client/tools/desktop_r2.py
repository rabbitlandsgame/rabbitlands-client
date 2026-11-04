"""Desktop asset delivery from Cloudflare R2: layout, formats and validators.

Pure Python: no SDK, network or Godot. The local packer, the R2 uploader and the
Actions release tool share these rules, so CI never signs content that the
updater would refuse, and the uploader never writes outside the desktop layout.

R2, Cloudflare and every R2 credential are untrusted transport. Every byte a
player installs is checked against a row of a manifest signed by the release
key. Nothing here treats R2 metadata, ETags or a content set's own
informational fields (`asset_base`, `ci_paths`, `builder`, `qualification`) as
a source of trust: validators use this module's constants only.

Errors are DesktopR2Error subclasses with a stable `code`. Their text never
contains credential values; config errors carry no input text at all and are
raised with no exception context.
"""
from __future__ import annotations

import base64
import binascii
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib.parse import urlsplit

REPOSITORY = "rabbitlandsgame/rabbitlands-client"
BUCKET = "rabbit-lands-assets"
PUBLIC_ORIGIN = "https://assets.rabbitlandsgame.com/"
LAYOUT_PREFIX = "desktop/v1/"
# To be compiled into src/updates/release.gd; never read from a manifest, a
# set, the server or the environment.
DESKTOP_ASSETS = PUBLIC_ORIGIN + LAYOUT_PREFIX
SELFTEST_ROOT = "desktop/selftest/"
PLATFORMS = ("windows", "linux")
CHANNELS = ("live",)
SOURCES = ("r2", "ci")

SET_KIND = "rabbitlands-desktop-content-set"
SET_SCHEMA = 1
POINTER_KIND = "rabbitlands-release-pointer"
POINTER_SCHEMA = 1

# Paths CI builds (engine, native runtime). The local content set never
# carries them, in any spelling; CI names their packages itself.
CI_PATHS = ("app/RabbitLands.exe", "app/RabbitLands.x86_64")
CI_PREFIXES = ("app/bin/client_runtime/",)
CI_PACKAGE_IDS = ("engine", "native-runtime")
# Required package -> a file it must carry (CI's identity cross-check reads it).
REQUIRED_PACKAGES = {"release-descriptor": "app/client-release.json", "client": "app/RabbitLands.pck"}

# Mirrors of src/updates/release.gd and package_updates.gd limits.
ROOTS = ("app", "eloria-assets")
RESERVED_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
                            *(f"LPT{n}" for n in range(1, 10))})
MAX_PATH_LENGTH = 1024
MAX_FILES = 100000
MAX_PART_BYTES = 256 * 1024 * 1024
MAX_SAFE_INTEGER = 2 ** 53 - 1  # Godot parses JSON numbers as doubles
READER_CAP = 850        # package_updates.gd today
READER_CAP_W1A = 2000   # once both the R2-aware reader and the writer allow it
READER_CAPS = (READER_CAP, READER_CAP_W1A)
CODECS = ("zstd",)

# `.com` is native code Windows runs that has no magic bytes to sniff.
NATIVE_SUFFIXES = (".exe", ".dll", ".so", ".dylib", ".x86_64", ".com")
GDEXTENSION_SUFFIX = ".gdextension"
# Loose files the engine itself reads beside the executable or under res://
# when the core pack lacks them (project overrides, the extension list). They
# would bypass CI's check of the core pack, so content never carries them.
ENGINE_FILES = ("app/override.cfg",)
ENGINE_DIRECTORY = ".godot"
SNIFF_BYTES = 4096
_PE_HEADER_LIMIT = 16 * 1024 * 1024
_MACHO_MAGICS = frozenset(bytes.fromhex(value) for value in (
    "feedface", "feedfacf", "cefaedfe", "cffaedfe",   # thin, both byte orders
    "cafebabe", "bebafeca", "cafebabf", "bfbafeca"))  # universal (fat, fat64)

MAX_SET_BYTES = 32 * 1024 * 1024
MAX_ENVELOPE_BYTES = 15 * 1024 * 1024       # gate at signing
CLIENT_MANIFEST_LIMIT = 16 * 1024 * 1024    # what released clients accept
MAX_POINTER_BYTES = 64 * 1024
# Signed sequences are UTC Unix seconds; the bounds catch milliseconds.
MIN_SEQUENCE = 1_700_000_000
MAX_SEQUENCE = 4_102_444_800

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
POINTER_CACHE_CONTROL = "no-store"
# The only S3 operations the desktop uploader may issue (enforced by its SDK
# handler); deletes and every bucket-level call stay out of reach.
ALLOWED_OPERATIONS = frozenset({"HeadObject", "GetObject", "PutObject", "ListObjectsV2"})
# The secret set: never printed, logged, put in receipts or error text. The
# account id is the endpoint's first host label. Bucket and public base are not secret.
SECRET_CONFIG_FIELDS = ("endpoint_url", "access_key_id", "secret_access_key")
NON_SECRET_CONFIG_FIELDS = ("bucket", "public_base_url")
MAX_CONFIG_BYTES = 64 * 1024

GITHUB_DOWNLOADS = f"https://github.com/{REPOSITORY}/releases/download/"
POOL_TAG = "client-assets"

_HEX64 = "[0-9a-f]{64}"
_PLATFORM = "(?:windows|linux)"
_NONCE_PREFIX = "desktop/selftest/[0-9]{8}-[0-9a-f]{8}/"
_PRODUCTION_KEYS = (
    re.compile(rf"desktop/v1/parts/{_HEX64}\.bin"),
    re.compile(rf"desktop/v1/(?:sets|manifests)/{_PLATFORM}/{_HEX64}\.json"),
    re.compile(rf"desktop/v1/channels/live/{_PLATFORM}\.json"),
)
_SELFTEST_KEY = re.compile(_NONCE_PREFIX + rf"(?:(?:parts|conflict|lock)/{_HEX64}\.bin|"
                           rf"(?:sets|manifests)/{_PLATFORM}/{_HEX64}\.json|channels/live/{_PLATFORM}\.json)")
_SELFTEST_PREFIX = re.compile(_NONCE_PREFIX)
_POINTER_KEY = re.compile(rf"desktop/(?:v1|selftest/[0-9]{{8}}-[0-9a-f]{{8}})/channels/live/{_PLATFORM}\.json")
_LIST_PREFIX = re.compile(r"desktop/[a-z0-9/._-]*")
_HASH = re.compile(_HEX64)
_COMMIT = re.compile("[0-9a-f]{40}")
_VERSION = re.compile(r"RabbitLands-(Windows|Linux)-[0-9]{8}-([0-9a-f]{9})")
_PACKAGE_ID = re.compile(r"[a-z0-9-]{1,96}")
_FEATURE = re.compile(r"[a-z0-9-]{1,64}")
_PATH_CHARS = re.compile(r"[A-Za-z0-9._ /-]+")
# Root files include the profile launchers, e.g. `RabbitLands (debug console).bat`.
_ROOT_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ ()-]{0,127}")
_VERSIONED_SO = re.compile(r"\.so(?:\.[0-9]+)+\Z")
_LOCAL_PATH = re.compile(r"[A-Za-z]:|/|~|file:", re.IGNORECASE)
_ACCOUNT_HOST = re.compile(r"([a-f0-9]{32})(?:\.(?:eu|us|fedramp))?\.r2\.cloudflarestorage\.com")
_ACCESS_KEY = re.compile(r"[A-Za-z0-9]{16,128}")
_SECRET_KEY = re.compile(r"[A-Za-z0-9+/=_-]{16,256}")


class DesktopR2Error(ValueError):
    """A refusal with a stable `code`; its text never contains secret values."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


class KeyGuardError(DesktopR2Error):
    pass


class FormatError(DesktopR2Error):
    pass


class SetError(DesktopR2Error):
    pass


class PointerError(DesktopR2Error):
    pass


class ManifestError(DesktopR2Error):
    pass


class EnvelopeError(DesktopR2Error):
    pass


class OutputPathError(DesktopR2Error):
    pass


class ConfigError(DesktopR2Error):
    """Malformed R2 configuration. Fixed text only: no values, paths or causes."""

    MESSAGES = {
        "config-unreadable": "The R2 configuration file cannot be read.",
        "config-too-large": "The R2 configuration file is too large.",
        "config-not-json": "The R2 configuration is not a JSON object.",
        "config-endpoint": "Use the bucket's HTTPS R2 S3 endpoint.",
        "config-bucket": "The R2 bucket is not the desktop asset bucket.",
        "config-access-key": "The R2 access key id is missing or malformed.",
        "config-secret": "The R2 secret access key is missing or malformed.",
        "config-public-base": "The R2 public base URL is malformed.",
        "config-location": "The R2 configuration must not be a tracked or unignored repository file.",
    }

    def __init__(self, code: str):
        super().__init__(code, self.MESSAGES[code])


def _quote(value) -> str:
    """A short, ASCII-only rendering of an offending (non-secret) value."""
    text = ascii(value)
    return text if len(text) <= 120 else text[:117] + "..."


def _is_int(value, minimum=0, maximum=MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _is_hash(value) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def valid_commit(value) -> bool:
    return type(value) is str and _COMMIT.fullmatch(value) is not None


def _require_hash(value, error=FormatError) -> str:
    if not _is_hash(value):
        raise error("hash", _quote(value))
    return value


def _require_platform(value, error=FormatError) -> str:
    if type(value) is not str or value not in PLATFORMS:
        raise error("platform", _quote(value))
    return value


def public_key_sha256(pem: bytes) -> str:
    """SHA-256 of the exact bytes of a commit's godot-client/data/update_public.pem."""
    if type(pem) is not bytes or b"PUBLIC KEY" not in pem or b"PRIVATE" in pem:
        raise FormatError("public-key", "expected the public PEM bytes")
    return hashlib.sha256(pem).hexdigest()


# --- Key guard ---------------------------------------------------------------

def guard_key(key, *, selftest: bool = False) -> str:
    """Return `key` when it is a desktop key of the current mode, else refuse.

    Production mode admits only the four `desktop/v1/` shapes; self-test mode
    admits only the nonce-prefixed self-test shapes. `fullmatch` (never `$`)
    refuses a trailing newline. Nothing under `browser/` or any other prefix
    ever passes, not even for HEAD.
    """
    if type(key) is str:
        if selftest:
            if _SELFTEST_KEY.fullmatch(key):
                return key
        elif any(pattern.fullmatch(key) for pattern in _PRODUCTION_KEYS):
            return key
    raise KeyGuardError("key", _quote(key))


def is_allowed_key(key, *, selftest: bool = False) -> bool:
    try:
        guard_key(key, selftest=selftest)
    except KeyGuardError:
        return False
    return True


def is_pointer_key(key) -> bool:
    """The only mutable keys: a channel pointer (production or self-test)."""
    return type(key) is str and _POINTER_KEY.fullmatch(key) is not None


def guard_list_prefix(prefix, *, selftest: bool = False) -> str:
    """ListObjectsV2 prefixes stay inside `desktop/` (self-test: its own root)."""
    if (type(prefix) is str and _LIST_PREFIX.fullmatch(prefix) and ".." not in prefix and "//" not in prefix
            and (not selftest or prefix.startswith(SELFTEST_ROOT))):
        return prefix
    raise KeyGuardError("list-prefix", _quote(prefix))


def new_selftest_prefix(today: datetime.date | None = None) -> str:
    """A fresh, never-probed `desktop/selftest/<YYYYMMDD>-<8 hex>/` prefix."""
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    return selftest_prefix(today.strftime("%Y%m%d"), secrets.token_hex(4))


def selftest_prefix(date: str, nonce: str) -> str:
    prefix = f"{SELFTEST_ROOT}{date}-{nonce}/"
    if type(date) is not str or type(nonce) is not str or not _SELFTEST_PREFIX.fullmatch(prefix):
        raise KeyGuardError("selftest-prefix", _quote(prefix))
    return prefix


def _layout_base(prefix: str | None) -> str:
    if prefix is None:
        return LAYOUT_PREFIX
    if type(prefix) is not str or not _SELFTEST_PREFIX.fullmatch(prefix):
        raise KeyGuardError("selftest-prefix", _quote(prefix))
    return prefix


# --- Keys and URLs -----------------------------------------------------------

def part_key(sha256: str, *, prefix: str | None = None) -> str:
    return guard_key(f"{_layout_base(prefix)}parts/{_require_hash(sha256)}.bin", selftest=prefix is not None)


def set_key(platform: str, sha256: str, *, prefix: str | None = None) -> str:
    return guard_key(f"{_layout_base(prefix)}sets/{_require_platform(platform)}/{_require_hash(sha256)}.json",
                     selftest=prefix is not None)


def manifest_key(platform: str, sha256: str, *, prefix: str | None = None) -> str:
    return guard_key(f"{_layout_base(prefix)}manifests/{_require_platform(platform)}/{_require_hash(sha256)}.json",
                     selftest=prefix is not None)


def pointer_key(platform: str, channel: str = "live", *, prefix: str | None = None) -> str:
    if channel not in CHANNELS:
        raise KeyGuardError("channel", _quote(channel))
    return guard_key(f"{_layout_base(prefix)}channels/{channel}/{_require_platform(platform)}.json",
                     selftest=prefix is not None)


def public_url(key: str, *, selftest: bool = False) -> str:
    """The anonymous HTTPS URL of a guarded key on the custom domain."""
    return PUBLIC_ORIGIN + guard_key(key, selftest=selftest)


def part_url(sha256: str) -> str:
    """The only accepted R2 form of a content part URL: `<base>parts/<sha256>.bin`."""
    return public_url(part_key(sha256))


def set_url(platform: str, sha256: str) -> str:
    return public_url(set_key(platform, sha256))


def manifest_url(platform: str, sha256: str, *, prefix: str | None = None) -> str:
    return public_url(manifest_key(platform, sha256, prefix=prefix), selftest=prefix is not None)


def pointer_url(platform: str, channel: str = "live") -> str:
    return public_url(pointer_key(platform, channel))


def key_from_url(url, *, selftest: bool = False) -> str:
    """The R2 key of a public desktop URL; refuses every other host and form."""
    if type(url) is str and url.startswith(PUBLIC_ORIGIN):
        key = url[len(PUBLIC_ORIGIN):]
        if is_allowed_key(key, selftest=selftest) and public_url(key, selftest=selftest) == url:
            return key
    raise KeyGuardError("url", _quote(url))


def github_pool_url(sha256: str, *, partitioned: bool = True) -> str:
    """Today's GitHub shared-download form for a package part (`ci` content).

    `partitioned` is what release_storage.PartWriter(shared="partitioned")
    writes; the legacy unpartitioned pool is still accepted by released clients.
    """
    _require_hash(sha256)
    tag = f"{POOL_TAG}-{sha256[0]}" if partitioned else POOL_TAG
    return f"{GITHUB_DOWNLOADS}{tag}/RabbitLands-pkg-{sha256}.zip.part"


def derived_part_url(sha256: str, source: str) -> str:
    if source == "r2":
        return part_url(sha256)
    if source == "ci":
        return github_pool_url(sha256)
    raise FormatError("source", _quote(source))


def part_url_matches(row, source: str) -> bool:
    """A part row's URL is exactly a derived form of its own SHA-256 for `source`."""
    if not isinstance(row, dict) or not _is_hash(row.get("sha256")):
        return False
    url, digest = row.get("url"), row["sha256"]
    if source == "r2":
        return url == part_url(digest)
    if source == "ci":
        return url in (github_pool_url(digest), github_pool_url(digest, partitioned=False))
    return False


def rewrite_part_urls(packages: list) -> list:
    """Copies of package rows whose parts use the derived R2 URL (idempotent).

    PartWriter names local parts `RabbitLands-pkg-<sha>.zip.part`; the R2 key
    is a pure function of the part's SHA-256, so rewriting after the build is
    exact, also for reused rows.
    """
    result = []
    for package in packages:
        copy = dict(package)
        copy["parts"] = [{**part, "url": part_url(part["sha256"])} for part in package["parts"]]
        result.append(copy)
    return result


def object_headers(key: str, sha256: str, *, sequence: int | None = None, selftest: bool = False) -> dict:
    """PutObject headers and bookkeeping metadata (never integrity) for a key."""
    guard_key(key, selftest=selftest)
    _require_hash(sha256)
    if is_pointer_key(key):
        _require_sequence(sequence, FormatError)
        return {"ContentType": "application/json", "CacheControl": POINTER_CACHE_CONTROL,
                "Metadata": {"sha256": sha256, "sequence": str(sequence)}}
    if sequence is not None:
        raise FormatError("sequence", "only pointers carry a sequence")
    content_type = "application/octet-stream" if key.endswith(".bin") else "application/json"
    return {"ContentType": content_type, "CacheControl": IMMUTABLE_CACHE_CONTROL, "Metadata": {"sha256": sha256}}


# --- Canonical JSON ----------------------------------------------------------

def _canonical_problem(value, depth: int = 0) -> str | None:
    if depth > 64:
        return "canonical-depth"
    if value is None or type(value) in (bool, str):
        return None
    if type(value) is int:
        return None if -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER else "canonical-int-range"
    if type(value) is float:
        return "canonical-float"
    if type(value) is list:
        return next((problem for item in value if (problem := _canonical_problem(item, depth + 1))), None)
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            return "canonical-key"
        return next((problem for item in value.values() if (problem := _canonical_problem(item, depth + 1))), None)
    return "canonical-type"


def canonical_bytes(value) -> bytes:
    """Stable bytes: sorted keys, no whitespace, ASCII escapes, no floats.

    Integers stay within 2**53 so Godot's JSON (doubles) reads them exactly.
    A set's SHA-256 is taken over exactly these bytes.
    """
    problem = _canonical_problem(value)
    if problem:
        raise FormatError(problem)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _refuse_constant(name):
    raise ValueError("non-finite number")


def _parse_json(data: bytes, encoding: str = "utf-8"):
    """Strict JSON (no duplicate keys, NaN or Infinity); None when malformed."""
    value = None
    try:
        value = json.loads(data.decode(encoding), object_pairs_hook=_strict_object, parse_constant=_refuse_constant)
        ok = True
    except (UnicodeDecodeError, ValueError, RecursionError):
        ok = False
    return value if ok else None


def parse_set_bytes(data: bytes) -> dict:
    """Parse set bytes and require them to be canonical (a rerun is byte-identical)."""
    if type(data) is not bytes or len(data) > MAX_SET_BYTES:
        raise SetError("set-size")
    value = _parse_json(data)
    if not isinstance(value, dict):
        raise SetError("set-json")
    if _canonical_problem(value) or canonical_bytes(value) != data:
        raise SetError("set-not-canonical")
    return value


# --- Paths and executable hygiene --------------------------------------------

def safe_path(path) -> bool:
    """A Python mirror of src/updates/release.gd Release.safe_path."""
    if (type(path) is not str or not path or len(path) > MAX_PATH_LENGTH or path.startswith("/")
            or "\\" in path or ":" in path):
        return False
    components = path.split("/")
    if len(components) < 2 or components[0] not in ROOTS:
        return False
    for component in components:
        if (component in ("", ".", "..") or component.endswith(".") or component.endswith(" ")
                or component.startswith(" ")):
            return False
        if any(ord(letter) < 32 or letter in '<>"|?*' for letter in component):
            return False
        if component.split(".", 1)[0].upper() in RESERVED_NAMES:
            return False
    return True


def _ci_entries() -> tuple[str, ...]:
    return tuple(path.casefold() for path in CI_PATHS) + tuple(prefix.rstrip("/").casefold() for prefix in CI_PREFIXES)


def is_ci_path(path: str) -> bool:
    """Case-insensitively equal to, under, or an ancestor of a CI-owned path."""
    folded = path.casefold()
    return any(folded == entry or folded.startswith(entry + "/") or entry.startswith(folded + "/")
               for entry in _ci_entries())


def has_native_suffix(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    return name.endswith(NATIVE_SUFFIXES) or _VERSIONED_SO.search(name) is not None


def is_gdextension(path: str) -> bool:
    return path.casefold().endswith(GDEXTENSION_SUFFIX)


def is_engine_file(path: str) -> bool:
    """A loose engine control file: `app/override.cfg` or anything under a `.godot` folder."""
    folded = path.casefold()
    return folded in ENGINE_FILES or ENGINE_DIRECTORY in folded.split("/")


def path_problem(path) -> str | None:
    """The first content-path rule `path` breaks, or None (duplicates are set-wide)."""
    if not safe_path(path):
        return "path-unsafe"
    if "~" in path:
        return "path-tilde"  # 8.3 short-name aliases such as RABBIT~1.EXE
    if not _PATH_CHARS.fullmatch(path):
        return "path-ascii"
    if is_ci_path(path):
        return "ci-path"
    if is_engine_file(path):
        return "engine-file"
    if is_gdextension(path) and not path.casefold().startswith(tuple(p.casefold() for p in CI_PREFIXES)):
        return "gdextension"
    if has_native_suffix(path):
        return "native-extension"
    return None


def sniff_native(head: bytes, size: int | None = None) -> str | None:
    """'pe', 'elf' or 'macho' when `head` starts like a native executable.

    PE means `MZ` with a `PE\\0\\0` signature at e_lfanew; a bare `MZ` is data.
    When e_lfanew lies past `head` and could lie inside the file, the header
    cannot be ruled out and the bytes count as PE.
    """
    if head[:4] == b"\x7fELF":
        return "elf"
    if head[:4] in _MACHO_MAGICS:
        return "macho"
    if head[:2] == b"MZ" and len(head) >= 0x40:
        offset = int.from_bytes(head[0x3C:0x40], "little")
        if offset + 4 <= len(head):
            return "pe" if head[offset:offset + 4] == b"PE\0\0" else None
        if size is None or offset + 4 <= size:
            return "pe"
    return None


def sniff_file(path: Path) -> str | None:
    """`sniff_native` on a file, reading the PE signature wherever e_lfanew puts it."""
    with open(path, "rb") as stream:
        head = stream.read(SNIFF_BYTES)
        if head[:2] == b"MZ" and len(head) >= 0x40:
            offset = int.from_bytes(head[0x3C:0x40], "little")
            if offset + 4 > len(head):
                size = os.fstat(stream.fileno()).st_size
                if offset + 4 > size:
                    return None
                if offset > _PE_HEADER_LIMIT:
                    return "pe"
                stream.seek(offset)
                return "pe" if stream.read(4) == b"PE\0\0" else None
    return sniff_native(head)


def stage_sniffer(stage: Path):
    """A `validate_set(sniff=...)` callback reading files of a local stage.

    Links and paths that resolve outside the stage are refused, as
    asset_packages.build refuses links.
    """
    root = Path(stage).resolve()

    def sniff(relative: str) -> str | None:
        target = root / relative
        if target.is_symlink() or not target.resolve().is_relative_to(root) or not target.is_file():
            raise SetError("stage-file", _quote(relative))
        return sniff_file(target)
    return sniff


def _local_path_strings(value, depth: int = 0):
    """Strings in a set that look like local paths (privacy: the set is public)."""
    if depth > 64:
        return
    if type(value) is str:
        if "\\" in value or _LOCAL_PATH.match(value):
            yield value
    elif type(value) is list:
        for item in value:
            yield from _local_path_strings(item, depth + 1)
    elif type(value) is dict:
        for key, item in value.items():
            yield from _local_path_strings(key, depth + 1)
            yield from _local_path_strings(item, depth + 1)


# --- Content set -------------------------------------------------------------

def _check_package(package, *, optional: bool, source: str, ids: set, folded: dict, part_sizes: dict,
                   files_out: list) -> tuple[int, int, int]:
    if not isinstance(package, dict):
        raise SetError("package", "not an object")
    pid = package.get("id")
    if type(pid) is not str or not _PACKAGE_ID.fullmatch(pid):
        raise SetError("package-id", _quote(pid))
    if pid in ids:
        raise SetError("package-duplicate", pid)
    if pid in CI_PACKAGE_IDS:
        raise SetError("package-ci", pid)
    ids.add(pid)
    if optional and (type(package.get("feature")) is not str or not _FEATURE.fullmatch(package["feature"])):
        raise SetError("package-feature", pid)
    if "codec" in package and package["codec"] not in CODECS:
        raise SetError("codec", pid)
    if not _is_hash(package.get("sha256")) or not _is_int(package.get("size"), 1):
        raise SetError("package-identity", pid)
    files = package.get("files")
    if type(files) is not list or not files or len(files) > MAX_FILES:
        raise SetError("package-files", pid)
    unpacked = 0
    for entry in files:
        if not isinstance(entry, dict):
            raise SetError("file", pid)
        path = entry.get("path")
        problem = path_problem(path)
        if problem:
            raise SetError(problem, _quote(path))
        key = path.casefold()
        if key in folded:
            raise SetError("path-duplicate", _quote(path))
        folded[key] = path
        if not _is_int(entry.get("size")) or not _is_hash(entry.get("sha256")):
            raise SetError("file-identity", _quote(path))
        if "codec" in entry and entry["codec"] not in CODECS:
            raise SetError("codec", _quote(path))
        unpacked += entry["size"]
        files_out.append(path)
    if package.get("unpacked_size") != unpacked or type(package.get("unpacked_size")) is not int:
        raise SetError("package-unpacked-size", pid)
    if package.get("file_count") != len(files) or type(package.get("file_count")) is not int:
        raise SetError("package-file-count", pid)
    parts = package.get("parts")
    if type(parts) is not list or not parts:
        raise SetError("package-parts", pid)
    packed = 0
    for part in parts:
        if not isinstance(part, dict) or not _is_hash(part.get("sha256")):
            raise SetError("part-identity", pid)
        if not _is_int(part.get("size"), 1, MAX_PART_BYTES):
            raise SetError("part-size", pid)
        if not part_url_matches(part, source):
            raise SetError("part-url", _quote(part.get("url")))
        if part_sizes.setdefault(part["sha256"], part["size"]) != part["size"]:
            raise SetError("part-conflict", pid)
        packed += part["size"]
    if packed != package["size"]:
        raise SetError("package-size", pid)
    if len(parts) == 1 and parts[0]["sha256"] != package["sha256"]:
        # The updater installs a one-part package only when its part is the package.
        raise SetError("package-single-part", pid)
    return len(parts), package["size"], unpacked


def validate_set(content_set, *, public_key_sha256: str, commit: str | None = None, platform: str | None = None,
                 source: str | None = None, reader_cap: int = READER_CAP, sniff=None) -> dict:
    """Check an unsigned content set; return a summary.

    Mirrors package_updates.gd validate, so CI never signs what the updater
    refuses, plus the R2 rules: derived part URLs from this module's constants
    (the set's `asset_base` and `ci_paths` are never consulted), ASCII-only
    paths, case-insensitive CI-path exclusion, no native-code files and, with
    `sniff(path) -> kind | None`, no native magic bytes. `public_key_sha256` is
    the SHA-256 of the commit's update_public.pem; `reader_cap` is the target
    reader's package/part cap (850 today, 2000 after the R2-aware reader). These checks are
    hygiene, not containment: content GDScript is trusted by attestation.
    """
    if not isinstance(content_set, dict):
        raise SetError("set", "not an object")
    problem = _canonical_problem(content_set)
    if problem:
        raise SetError(problem)
    if content_set.get("kind") != SET_KIND or type(content_set.get("set_schema")) is not int \
            or content_set["set_schema"] != SET_SCHEMA:
        raise SetError("set-kind")
    leaked = next(_local_path_strings(content_set), None)
    if leaked is not None:
        raise SetError("set-local-path", _quote(leaked))
    if content_set.get("repository") != REPOSITORY:
        raise SetError("repository", _quote(content_set.get("repository")))
    if not valid_commit(content_set.get("commit")) or (commit is not None and content_set["commit"] != commit):
        raise SetError("commit", _quote(content_set.get("commit")))
    set_platform = content_set.get("platform")
    if set_platform not in PLATFORMS or (platform is not None and set_platform != platform):
        raise SetError("platform", _quote(set_platform))
    set_source = content_set.get("source")
    if set_source not in SOURCES or (source is not None and set_source != source):
        raise SetError("source", _quote(set_source))
    version = content_set.get("version")
    match = _VERSION.fullmatch(version) if type(version) is str else None
    if not match or match[1].lower() != set_platform or match[2] != content_set["commit"][:9]:
        raise SetError("version", _quote(version))
    if not _is_hash(public_key_sha256):
        raise SetError("public-key", "expected the commit's update_public.pem SHA-256")
    if content_set.get("public_key_sha256") != public_key_sha256:
        raise SetError("public-key", _quote(content_set.get("public_key_sha256")))
    if reader_cap not in READER_CAPS:
        raise SetError("reader-cap", _quote(reader_cap))
    packages = content_set.get("packages")
    optional = content_set.get("optional_packages", [])
    if type(packages) is not list or not packages:
        raise SetError("packages")
    if type(optional) is not list:
        raise SetError("optional-packages")

    ids, folded, part_sizes, paths = set(), {}, {}, []
    part_count = packed = unpacked = 0
    for rows, is_optional in ((packages, False), (optional, True)):
        for package in rows:
            parts, size, files_size = _check_package(package, optional=is_optional, source=set_source, ids=ids,
                                                     folded=folded, part_sizes=part_sizes, files_out=paths)
            part_count += parts
            packed += size
            unpacked += files_size
    directories = {key.rsplit("/", depth)[0] for key in folded for depth in range(1, key.count("/"))}
    clash = next((folded[key] for key in folded if key in directories), None)
    if clash is not None:
        raise SetError("path-file-dir-conflict", _quote(clash))
    if len(paths) > MAX_FILES:
        raise SetError("file-count")
    # Every package (CI ones included) has at least one part, so this one
    # count also bounds the reader's package cap.
    reserved = len(CI_PACKAGE_IDS)
    if part_count + reserved > reader_cap:
        raise SetError("reader-cap-exceeded", f"{part_count} parts + {reserved} CI packages > {reader_cap}")
    required_rows = {package["id"]: package for package in packages}
    for pid, path in REQUIRED_PACKAGES.items():
        if pid not in required_rows or path not in (entry["path"] for entry in required_rows[pid]["files"]):
            raise SetError("required-package", pid)
    if sniff is not None:
        for path in paths:
            kind = sniff(path)
            if kind is not None:
                raise SetError("native-magic", f"{_quote(path)} ({kind})")
    return {"platform": set_platform, "source": set_source, "commit": content_set["commit"],
            "packages": len(packages), "optional_packages": len(optional), "parts": part_count,
            "files": len(paths), "bytes": packed, "unpacked_bytes": unpacked,
            "reader_slots": part_count + reserved, "reader_cap": reader_cap}


# --- Release manifest additions (schema 3) -----------------------------------

def _require_sequence(value, error) -> int:
    if not _is_int(value, MIN_SEQUENCE, MAX_SEQUENCE - 1):
        raise error("sequence", _quote(value))
    return value


def _check_root_files(rows) -> list:
    if type(rows) is not list:
        raise ManifestError("root-files")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "size", "sha256"}:
            raise ManifestError("root-file", "expected {name, size, sha256}")
        name = row["name"]
        if (type(name) is not str or not _ROOT_FILE.fullmatch(name) or name.endswith((".", " "))
                or name.split(".", 1)[0].upper() in RESERVED_NAMES or name.casefold() in seen):
            raise ManifestError("root-file-name", _quote(name))
        seen.add(name.casefold())
        if not _is_int(row["size"]) or not _is_hash(row["sha256"]):
            raise ManifestError("root-file-identity", _quote(name))
    return rows


def manifest_additions(*, platform: str, sequence: int, helpers_fingerprint: str, root_files: list,
                       source: str, set_sha256: str) -> dict:
    """The signed schema-3 fields R2 delivery adds to a release payload."""
    _require_platform(platform, ManifestError)
    content = {"source": source, "set": {"sha256": _require_hash(set_sha256, ManifestError)}}
    if source == "r2":
        content["set"]["url"] = set_url(platform, set_sha256)
    elif source != "ci":
        raise ManifestError("source", _quote(source))
    additions = {"sequence": _require_sequence(sequence, ManifestError),
                 "helpers_fingerprint": _require_hash(helpers_fingerprint, ManifestError),
                 "root_files": [dict(row) for row in _check_root_files(root_files)], "content": content}
    validate_manifest_additions(additions, platform=platform)
    return additions


def validate_manifest_additions(release, *, platform: str) -> dict:
    """Check the added fields of a schema-3 payload (informational ones included)."""
    if not isinstance(release, dict):
        raise ManifestError("manifest")
    _require_platform(platform, ManifestError)
    _require_sequence(release.get("sequence"), ManifestError)
    _require_hash(release.get("helpers_fingerprint"), ManifestError)
    _check_root_files(release.get("root_files"))
    content = release.get("content")
    if not isinstance(content, dict) or set(content) != {"source", "set"} or content["source"] not in SOURCES:
        raise ManifestError("content")
    entry = content["set"]
    expected = {"sha256", "url"} if content["source"] == "r2" else {"sha256"}
    if not isinstance(entry, dict) or set(entry) != expected or not _is_hash(entry.get("sha256")):
        raise ManifestError("content-set")
    if content["source"] == "r2" and entry["url"] != set_url(platform, entry["sha256"]):
        raise ManifestError("content-set-url", _quote(entry["url"]))
    return release


# --- Pointer (payload of a signed envelope) ----------------------------------

_POINTER_FIELDS = frozenset({"kind", "pointer_schema", "repository", "platform", "channel", "sequence", "rollback",
                             "release_id", "run_id", "target"})
_TARGET_FIELDS = frozenset({"commit", "version", "manifest_sequence", "manifest"})
_MANIFEST_FIELDS = frozenset({"url", "sha256", "size"})
# Fields every existing release verifier reads at top level. Their absence is
# the domain separation: Bootstrap.verify, Release.verify_manifest and the
# field game's published_identity all refuse a payload without a top-level commit.
RELEASE_ONLY_FIELDS = frozenset({"commit", "schema", "bootstrap_schema", "packages", "parts", "ancestors",
                                 "updater", "uninstall"})


def pointer_asset_name(platform: str) -> str:
    """`RabbitLands-<platform>-pointer.json`: never matched by the old API fallback,
    which picks the first asset ending in `-<platform>.json`."""
    name = f"RabbitLands-{_require_platform(platform, PointerError)}-pointer.json"
    if name.endswith(tuple(f"-{other}.json" for other in PLATFORMS)):
        raise PointerError("asset-name", name)
    return name


def pointer_payload(*, platform: str, sequence: int, rollback: bool, release_id: int, run_id: int, commit: str,
                    version: str, manifest_sequence: int, manifest_sha256: str, manifest_size: int,
                    channel: str = "live", prefix: str | None = None) -> dict:
    """A validated pointer payload v1. `prefix` is for self-tests only."""
    payload = {"kind": POINTER_KIND, "pointer_schema": POINTER_SCHEMA, "repository": REPOSITORY,
               "platform": platform, "channel": channel, "sequence": sequence, "rollback": rollback,
               "release_id": release_id, "run_id": run_id,
               "target": {"commit": commit, "version": version, "manifest_sequence": manifest_sequence,
                          "manifest": {"url": manifest_url(_require_platform(platform, PointerError),
                                                           _require_hash(manifest_sha256, PointerError),
                                                           prefix=prefix),
                                       "sha256": manifest_sha256, "size": manifest_size}}}
    return validate_pointer(payload, platform=platform, prefix=prefix)


def validate_pointer(payload, *, platform: str | None = None, prefix: str | None = None) -> dict:
    """Refuse anything but an exact pointer v1 for this repository and platform."""
    if not isinstance(payload, dict) or payload.get("kind") != POINTER_KIND:
        raise PointerError("pointer-kind")
    if RELEASE_ONLY_FIELDS & set(payload):
        raise PointerError("pointer-release-field", ",".join(sorted(RELEASE_ONLY_FIELDS & set(payload))))
    if set(payload) != _POINTER_FIELDS:
        raise PointerError("pointer-fields")
    if type(payload["pointer_schema"]) is not int or payload["pointer_schema"] != POINTER_SCHEMA:
        raise PointerError("pointer-schema")
    if payload["repository"] != REPOSITORY:
        raise PointerError("repository", _quote(payload["repository"]))
    if payload["platform"] not in PLATFORMS or (platform is not None and payload["platform"] != platform):
        raise PointerError("platform", _quote(payload["platform"]))
    if payload["channel"] not in CHANNELS:
        raise PointerError("channel", _quote(payload["channel"]))
    sequence = _require_sequence(payload["sequence"], PointerError)
    if type(payload["rollback"]) is not bool:
        raise PointerError("rollback")
    if not _is_int(payload["release_id"], 1) or not _is_int(payload["run_id"], 1):
        raise PointerError("release-run")
    target = payload["target"]
    if not isinstance(target, dict) or set(target) != _TARGET_FIELDS:
        raise PointerError("target")
    if not valid_commit(target["commit"]):
        raise PointerError("target-commit", _quote(target["commit"]))
    match = _VERSION.fullmatch(target["version"]) if type(target["version"]) is str else None
    if not match or match[1].lower() != payload["platform"] or match[2] != target["commit"][:9]:
        raise PointerError("target-version", _quote(target["version"]))
    if _require_sequence(target["manifest_sequence"], PointerError) >= sequence:
        raise PointerError("sequence-order", "the pointer is signed after its manifest")
    manifest = target["manifest"]
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS or not _is_hash(manifest["sha256"]):
        raise PointerError("target-manifest")
    if not _is_int(manifest["size"], 1, MAX_ENVELOPE_BYTES):
        raise PointerError("target-manifest-size", _quote(manifest["size"]))
    if manifest["url"] != manifest_url(payload["platform"], manifest["sha256"], prefix=prefix):
        raise PointerError("target-manifest-url", _quote(manifest["url"]))
    problem = _canonical_problem(payload)
    if problem:
        raise PointerError(problem)
    return payload


def pointer_bytes(payload, *, platform: str | None = None, prefix: str | None = None) -> bytes:
    """The canonical payload bytes that the release key signs (`prefix`: self-test pointers)."""
    return canonical_bytes(validate_pointer(payload, platform=platform, prefix=prefix))


# --- Envelopes -----------------------------------------------------------------

def check_envelope(data: bytes, *, limit: int = MAX_ENVELOPE_BYTES) -> dict:
    """Size and shape gate for a signed `{payload, signature}` envelope.

    Release envelopes are at most 15 MiB at signing (released clients cap them
    at 16 MiB); pass `limit=MAX_POINTER_BYTES` for a pointer. The signature is
    not checked here.
    """
    if type(data) is not bytes or not data:
        raise EnvelopeError("envelope")
    if len(data) > limit:
        raise EnvelopeError("envelope-too-large", f"{len(data)} > {limit} bytes")
    envelope = _parse_json(data)
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"} \
            or any(type(envelope[key]) is not str for key in envelope):
        raise EnvelopeError("envelope-shape")
    payload = signature = None
    try:
        payload = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
    except (binascii.Error, ValueError):
        pass
    if not payload or not signature:
        raise EnvelopeError("envelope-base64")
    if len(payload) > CLIENT_MANIFEST_LIMIT:
        raise EnvelopeError("envelope-payload-too-large")
    return {"bytes": len(data), "payload_bytes": len(payload), "limit": limit, "margin": limit - len(data)}


def check_pointer_envelope(data: bytes) -> dict:
    return check_envelope(data, limit=MAX_POINTER_BYTES)


# --- Private R2 configuration ------------------------------------------------

class R2Config:
    """Parsed R2 upload settings. `repr`/`str` show only non-secret fields."""

    __slots__ = ("bucket", "public_base_url", "_endpoint_url", "_account_id", "_access_key_id",
                 "_secret_access_key")

    def __init__(self, *, bucket, public_base_url, endpoint_url, account_id, access_key_id, secret_access_key):
        self.bucket = bucket
        self.public_base_url = public_base_url
        self._endpoint_url = endpoint_url
        self._account_id = account_id
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key

    def __repr__(self) -> str:
        return f"R2Config(bucket={self.bucket!r}, public_base_url={self.public_base_url!r})"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("R2Config is not serializable")

    def client_kwargs(self) -> dict:
        """Arguments for boto3.client('s3', ...). Never log or print them."""
        return {"endpoint_url": self._endpoint_url, "aws_access_key_id": self._access_key_id,
                "aws_secret_access_key": self._secret_access_key, "region_name": "auto"}

    def secret_values(self) -> tuple[str, ...]:
        """The secret set: endpoint, its host, the account id, key id and secret."""
        return (self._endpoint_url, urlsplit(self._endpoint_url).hostname or "", self._account_id,
                self._access_key_id, self._secret_access_key)


def contains_secret(text, config: R2Config) -> bool:
    """True when `text` contains any secret-set value (case-insensitive)."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    folded = str(text).casefold()
    return any(value and value.casefold() in folded for value in config.secret_values())


def _config_location_ok(path: Path) -> bool:
    try:
        require_private_path(path)
    except OutputPathError:
        return False
    return True


def load_r2_config(path, *, check_location: bool = True) -> R2Config:
    """Read and validate a private R2 config: {endpoint_url, bucket,
    access_key_id, secret_access_key[, public_base_url]}.

    The path is always an explicit argument; committed code holds no machine
    path. Every failure raises ConfigError with fixed text and no exception
    context, so neither the message, the traceback nor the exception chain can
    carry the file's content.
    """
    code = None
    data = b""
    try:
        target = Path(path)
        if target.stat().st_size > MAX_CONFIG_BYTES:
            code = "config-too-large"
        else:
            data = target.read_bytes()
    except (OSError, TypeError, ValueError):
        code = "config-unreadable"
    if code:
        raise ConfigError(code)
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigError("config-too-large")
    if check_location and not _config_location_ok(Path(path)):
        raise ConfigError("config-location")
    settings = _parse_json(data, "utf-8-sig")
    if not isinstance(settings, dict):
        raise ConfigError("config-not-json")

    endpoint = settings.get("endpoint_url")
    account = None
    if type(endpoint) is str:
        endpoint = endpoint.strip()
        try:
            parts = urlsplit(endpoint)
            port = parts.port
            host = parts.hostname or ""
            match = _ACCOUNT_HOST.fullmatch(host)
            if (parts.scheme == "https" and not parts.username and not parts.password and not parts.query
                    and not parts.fragment and parts.path in ("", "/") and port in (None, 443) and match
                    and not any(ord(letter) < 33 or ord(letter) > 126 for letter in endpoint)):
                account = match[1]
        except ValueError:
            account = None
    if account is None:
        raise ConfigError("config-endpoint")
    # The compiled public base serves this bucket only.
    if settings.get("bucket") != BUCKET:
        raise ConfigError("config-bucket")
    key_id = settings.get("access_key_id")
    key_id = key_id.strip() if type(key_id) is str else None
    if not key_id or not _ACCESS_KEY.fullmatch(key_id):
        raise ConfigError("config-access-key")
    secret = settings.get("secret_access_key")
    secret = secret.strip() if type(secret) is str else None
    if not secret or not _SECRET_KEY.fullmatch(secret):
        raise ConfigError("config-secret")
    public = settings.get("public_base_url")
    if public is not None and (type(public) is not str or not public.startswith(PUBLIC_ORIGIN)
                               or any(ord(letter) < 33 or ord(letter) > 126 for letter in public)):
        raise ConfigError("config-public-base")
    return R2Config(bucket=BUCKET, public_base_url=public, endpoint_url="https://" + urlsplit(endpoint).hostname,
                    account_id=account, access_key_id=key_id, secret_access_key=secret)


# --- Private output locations --------------------------------------------------

def _git_environment() -> dict:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def require_private_path(path) -> Path:
    """Refuse a path inside a Git worktree unless Git ignores it.

    Receipts, plans, sets and credentials must never become (or sit beside)
    tracked source. A path outside every worktree passes; inside one, `git
    check-ignore` must confirm it (a tracked file never counts as ignored).
    """
    target = Path(os.path.abspath(Path(path)))
    try:
        target = target.resolve()
    except OSError:
        pass
    existing = target
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    probe = existing if existing.is_dir() else existing.parent
    inside = any((folder / ".git").exists() for folder in (probe, *probe.parents))
    if not inside:
        return target
    # check-ignore exits 0 only for an ignored, untracked path; 1 when not
    # ignored or tracked; 128 outside a work tree. Its output is never decoded.
    try:
        ignored = subprocess.run(["git", "-C", str(probe), "check-ignore", "-q", "--", str(target)],
                                 capture_output=True, env=_git_environment(), timeout=60).returncode
    except (OSError, subprocess.SubprocessError):
        ignored = None
    if ignored == 0:
        return target
    raise OutputPathError("path-not-ignored", "use a location outside every worktree or an ignored one")

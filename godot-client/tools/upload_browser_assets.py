"""Upload only a browser manifest's verified files to an existing R2 bucket.

Requires boto3 in the operator's local Python environment. Credentials are read
from an ignored JSON file, never copied into the game, logs or upload receipt.
This does not configure public access, publish a launcher, or delete objects.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def payloads(stage: Path) -> list[dict]:
    stage = stage.resolve()
    manifest = json.loads((stage / "site/browser-assets.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported browser manifest")
    rows = [manifest["wasm"], *manifest.get("libraries", []), *manifest["pack"]["parts"], *manifest["archives"]]
    for group in manifest.get("groups", {}).values():
        rows.extend(group["archives"])
    unique = {}
    for row in rows:
        name, digest, size = row["file"], row["sha256"], row["bytes"]
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or name not in
                [digest + suffix for suffix in (".bin", ".wasm", ".zip")] or
                type(size) is not int or not 0 < size <= 64 * 1024 * 1024):
            raise ValueError("Invalid browser payload entry")
        item = {"file": name, "sha256": digest, "bytes": size}
        if name in unique and unique[name] != item:
            raise ValueError("Conflicting browser payload entries")
        unique[name] = item
    result = []
    # Validate the COMPLETE whitelist before making the first cloud mutation.
    for name, row in sorted(unique.items()):
        source = (stage / "assets" / name).resolve()
        if not source.is_relative_to(stage / "assets") or source.stat().st_size != row["bytes"]:
            raise ValueError("Missing or wrong-sized payload: " + name)
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != row["sha256"]:
            raise ValueError("Payload integrity mismatch: " + name)
        result.append({**row, "source": source, "key": "browser/assets/" + name,
                       "content_type": {".wasm": "application/wasm", ".zip": "application/zip"}.get(source.suffix, "application/octet-stream")})
    notice = stage / "site/godot-cpp-LICENSE.md"
    data = notice.read_bytes()
    result.append({"source": notice, "file": notice.name, "key": "browser/licenses/" + notice.name,
                   "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "content_type": "text/markdown; charset=utf-8"})
    return result


def client_from_file(path: Path):
    import boto3
    from botocore.config import Config
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    endpoint = urlsplit(settings["endpoint_url"].strip())
    if (endpoint.scheme != "https" or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
            or endpoint.path not in ("", "/") or endpoint.port not in (None, 443) or not re.fullmatch(
                r"[a-fA-F0-9]{32}(?:\.(?:eu|us|fedramp))?\.r2\.cloudflarestorage\.com", endpoint.hostname or "")):
        raise ValueError("Use the bucket's HTTPS R2 S3 endpoint")
    bucket = settings["bucket"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Invalid R2 bucket name")
    client = boto3.client("s3", endpoint_url=endpoint.geturl().rstrip("/"),
        aws_access_key_id=settings["access_key_id"].strip(), aws_secret_access_key=settings["secret_access_key"].strip(),
        region_name="auto", config=Config(signature_version="s3v4", max_pool_connections=16,
            connect_timeout=20, read_timeout=120, retries={"max_attempts": 4, "mode": "standard"}))
    return client, bucket


def upload(client, bucket: str, row: dict) -> dict:
    from botocore.exceptions import ClientError
    cache_control = "public, max-age=31536000, immutable" if row["key"].startswith("browser/assets/") else "public, max-age=3600"
    def check(head):
        return (head["ContentLength"] == row["bytes"] and head.get("Metadata", {}).get("sha256") == row["sha256"]
                and head.get("ContentType") == row["content_type"] and head.get("CacheControl") == cache_control)
    try:
        head = client.head_object(Bucket=bucket, Key=row["key"])
    except ClientError as error:
        if str(error.response.get("Error", {}).get("Code")) not in ("404", "NoSuchKey", "NotFound"):
            raise
    else:
        if not check(head):
            raise ValueError("Existing object differs; refusing to overwrite: " + row["key"])
        return {"key": row["key"], "bytes": row["bytes"], "sha256": row["sha256"], "uploaded": False}
    # Bounded single PUTs preserve each file's known length and avoid unfinished
    # multipart uploads. The manifest limits every payload to at most 64 MiB.
    with row["source"].open("rb") as stream:
        client.put_object(Bucket=bucket, Key=row["key"], Body=stream, ContentLength=row["bytes"],
            ContentType=row["content_type"], CacheControl=cache_control, Metadata={"sha256": row["sha256"]})
    if not check(client.head_object(Bucket=bucket, Key=row["key"])):
        raise ValueError("Remote verification failed: " + row["key"])
    return {"key": row["key"], "bytes": row["bytes"], "sha256": row["sha256"], "uploaded": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    rows = payloads(args.stage)
    client, bucket = client_from_file(args.credentials)
    completed, failures = [], []
    print(f"Uploading {len(rows)} verified files ({sum(row['bytes'] for row in rows):,} bytes) to {bucket}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(upload, client, bucket, row): row for row in rows}
        for future in as_completed(futures):
            try:
                completed.append(future.result())
            except Exception as error:
                # Never echo SDK request data or credentials in error messages.
                code = getattr(error, "response", {}).get("Error", {}).get("Code", type(error).__name__)
                failures.append({"key": futures[future]["key"], "error": str(code)})
            count = len(completed) + len(failures)
            if count % 50 == 0 or count == len(rows):
                print(f"Verified {len(completed)}/{len(rows)}; failures {len(failures)}", flush=True)
    result = {"bucket": bucket, "total_files": len(rows), "verified_bytes": sum(row["bytes"] for row in completed),
              "files": sorted(completed, key=lambda row: row["key"]), "failures": failures}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if failures:
        raise SystemExit("Upload incomplete; see the sanitized receipt. Reruns resume matching objects.")


if __name__ == "__main__":
    main()

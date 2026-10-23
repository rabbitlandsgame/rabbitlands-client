"""Prepare a draft and run native builds for desktop-release.yml."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from types import SimpleNamespace

import build_release as release
import package_client as package
import runner_release
import setup_runner_tools
import shared_release_assets
import release_asset_cache

SECRET = "CLIENT_UPDATE_SIGNING_KEY"


def workflow_commit() -> str:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != release.REPOSITORY
            or os.environ.get("GITHUB_REF") not in ("refs/heads/master", "refs/heads/develop")
            or os.environ.get("GITHUB_EVENT_NAME") not in ("push", "workflow_dispatch")):
        raise ValueError("Release automation must run in this repository on master or develop.")
    if os.environ["GITHUB_EVENT_NAME"] == "push" and os.environ["GITHUB_REF"] != "refs/heads/master":
        raise ValueError("Automatic release builds run only on master.")
    sha = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or package.git("rev-parse", "HEAD").strip() != sha:
        raise ValueError("The checkout must match the workflow's exact source commit.")
    return sha


def prepare() -> tuple[str, int]:
    sha = workflow_commit()
    if os.environ.get("SIGNING_KEY_AVAILABLE") != "true":
        raise ValueError(f"Configure the repository Actions secret {SECRET} before running a release.")
    runner_release.authorize()
    entries = [item for item in release.github_releases()
               if re.fullmatch(r"client-[0-9a-f]{40}", item["tag_name"])]
    if any(item["tag_name"] == f"client-{sha}" and not item["draft"] for item in entries):
        raise ValueError("This commit already has a published release. Build a newer commit, or return that release to draft before rebuilding it.")
    drafts = [item for item in entries if item["draft"]]
    if len(drafts) > 1:
        raise ValueError("More than one client draft exists; choose one before starting automation.")
    if drafts:
        draft = drafts[0]
    else:
        tag = f"client-{sha}"
        release.gh("release", "create", tag, "--repo", release.REPOSITORY, "--draft", "--target", sha,
                   "--title", f"Rabbit Lands {sha[:9]}", "--notes", "Desktop builds are being prepared. This release remains a draft.")
        # A newly created draft can briefly be absent from the release listing.
        # Re-read the same tag; never create a second destination on a retry.
        draft = None
        for delay in (0, 1, 2, 4, 8):
            if delay:
                time.sleep(delay)
            draft = release.github_release(tag)
            if draft is not None:
                break
    if (not draft or not draft["draft"]
            or draft["author"]["login"] not in (release.ACCOUNT, "github-actions[bot]")):
        raise ValueError("The draft must belong to the Rabbit Lands account or this repository's workflow.")
    release_id = draft["id"]
    shared_release_assets.ensure(sha)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"commit={sha}\nrelease_id={release_id}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"Building Windows and Linux from `{sha}` into draft release `{release_id}`.\n")
    return sha, release_id


def check_signing_key(key: bytes, public: bytes) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    try:
        private = serialization.load_pem_private_key(key, password=None)
        expected = serialization.load_pem_public_key(public)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{SECRET} must contain the existing unencrypted RSA PEM key.") from error
    if (not isinstance(private, rsa.RSAPrivateKey)
            or not isinstance(expected, rsa.RSAPublicKey)
            or private.public_key().public_numbers() != expected.public_numbers()):
        raise ValueError("The Actions signing key does not match this commit's public update key.")


def build(platform: str, release_id: int) -> Path:
    sha = workflow_commit()
    # Remove the secret from the environment before starting installers or Godot.
    key = os.environ.pop(SECRET, "").encode("ascii")
    public = package.git("show", f"{sha}:godot-client/data/update_public.pem").encode("ascii")
    check_signing_key(key, public)
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    tool_root = temp / "rabbitlands-toolchain"
    config = setup_runner_tools.install(platform, tool_root)
    previous = {name: os.environ.get(name) for name in config["env"]}
    try:
        os.environ.update(config["env"])
        with tempfile.TemporaryDirectory(prefix="rabbitlands-signing-", dir=temp) as private:
            key_path = Path(private) / "signing.pem"
            with key_path.open("xb") as output:
                os.chmod(key_path, 0o600)
                output.write(key)
            return runner_release.build(SimpleNamespace(platform=platform, ref=sha,
                out=temp / "rabbitlands-releases", godot=config["godot"], iscc=config.get("iscc"),
                update_signing_key=key_path, tool_root=[tool_root], draft_release_id=release_id,
                asset_cache=temp / "rabbitlands-asset-cache" / platform,
                server="game.rabbitlandsgame.com:2001"))
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    cache = commands.add_parser("cache-key")
    cache.add_argument("--platform", choices=("windows", "linux"), required=True)
    target = commands.add_parser("build")
    target.add_argument("--platform", choices=("windows", "linux"), required=True)
    target.add_argument("--release-id", type=int, required=True)
    options = parser.parse_args()
    try:
        if options.command == "prepare":
            prepare()
        elif options.command == "cache-key":
            key = release_asset_cache.input_key(package.git, workflow_commit(), options.platform)
            with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
                output.write(f"key={key}\n")
        else:
            build(options.platform, options.release_id)
    except (OSError, ValueError, package.PackageError) as error:
        print(f"Release automation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

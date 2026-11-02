"""Open the local prototype with its own saved downloads and graphics profile."""
import argparse
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8060/")
    parser.add_argument("--profile", type=Path, default=REPO / ".local/browser-prototype/browser-profile")
    parser.add_argument("--chrome", type=Path, help="Chrome executable; detected on Windows by default")
    parser.add_argument("--graphics-backend", choices=("auto", "gl", "vulkan", "d3d11"),
                        default="gl" if os.name == "nt" else "auto",
                        help="Prototype Chrome backend; Windows GL avoids the observed D3D11 map shader reset")
    args = parser.parse_args()
    url = urlsplit(args.url)
    storage_fragment = re.fullmatch(r"rl-assets=(browser|[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12})", url.fragment)
    if url.username or url.password or (url.fragment and not storage_fragment) or not url.hostname or not (
            url.scheme == "https" or url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}):
        parser.error("Use HTTPS or the local prototype address, without credentials; only a saved asset-location fragment is supported")
    profile = args.profile.resolve()
    if not profile.is_relative_to(REPO / ".local"):
        parser.error("Keep the prototype's separate browser profile inside this worktree's ignored .local folder")
    candidates = [Path(os.environ.get(key, "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
                  for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    chrome = args.chrome or next((path for path in candidates if path.is_file()), None)
    if chrome is None or not chrome.is_file():
        parser.error("Chrome was not found; supply its executable with --chrome")
    profile.mkdir(parents=True, exist_ok=True)
    graphics = [] if args.graphics_backend == "auto" else [f"--use-angle={args.graphics_backend}"]
    subprocess.Popen([str(chrome), f"--user-data-dir={profile}", "--new-window",
                      "--no-first-run", "--no-default-browser-check", "--force-high-performance-gpu",
                      *graphics, args.url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Opened Rabbit Lands: {args.url}")


if __name__ == "__main__":
    main()

"""Serve a generated browser prototype on loopback with worker isolation headers."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def list_directory(self, _path):
        self.send_error(403, "Directory listing disabled")


class AssetHandler(Handler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        # Asset responses don't need the launch page's isolation headers.
        SimpleHTTPRequestHandler.end_headers(self)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--port", type=int, default=8060)
    parser.add_argument("--assets", action="store_true", help="Serve only generated payload files with CORS")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.assets:
        import re
        if not directory.is_dir() or not any(directory.iterdir()) or any(
                not p.is_file() or not re.fullmatch(r"[a-f0-9]{64}\.(zip|bin|wasm)", p.name) for p in directory.iterdir()):
            parser.error("Choose the generated assets folder containing only hash-named payloads")
    elif not (directory / "index.html").is_file():
        parser.error("Choose the generated site folder containing index.html")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(AssetHandler if args.assets else Handler, directory=str(directory)))
    print(f"Rabbit Lands browser prototype: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

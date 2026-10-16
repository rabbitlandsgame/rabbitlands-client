"""Bounded, resumable HTTP transfers for large model files."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
import time
import urllib.request


def download_file(url, destination, size, workers=12):
    destination = Path(destination)
    if destination.is_file() and destination.stat().st_size == size:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    parts = destination.with_name(destination.name + ".parts")
    parts.mkdir(exist_ok=True)
    chunk_size = 32 * 1024 * 1024
    ranges = [(i, start, min(size, start + chunk_size) - 1)
              for i, start in enumerate(range(0, size, chunk_size))]

    def fetch(item):
        index, start, end = item
        path = parts / f"{index:05d}"
        expected = end - start + 1
        if path.is_file() and path.stat().st_size == expected:
            return expected
        # A distinct query avoids intermediary caches confusing different byte ranges.
        ranged_url = url + ("&" if "?" in url else "?") + f"rl_range={start}-{end}"
        request = urllib.request.Request(ranged_url, headers={"Range": f"bytes={start}-{end}"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    content_range = response.headers.get("Content-Range")
                    if response.status == 206:
                        if content_range != f"bytes {start}-{end}/{size}":
                            raise ValueError("Server returned an unexpected byte range")
                    elif not (response.status == 200 and start == 0 and end + 1 == size):
                        raise ValueError("Server did not honor the bounded download")
                    temp = path.with_suffix(".tmp")
                    with temp.open("wb") as stream:
                        shutil.copyfileobj(response, stream, length=1024 * 1024)
                if temp.stat().st_size != expected:
                    raise ValueError("Incomplete download chunk")
                temp.replace(path)
                return expected
            except Exception as error:
                if attempt == 2:
                    raise RuntimeError(f"Download failed for {destination.name}, chunk {index}: {type(error).__name__}") from None
                time.sleep(2 ** attempt)

    completed, reported = 0, time.monotonic()
    print(f"Fetching {destination.name} ({size / 1e9:.2f} GB)", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, item) for item in ranges]
        for future in as_completed(futures):
            completed += future.result()
            if time.monotonic() - reported >= 15:
                print(f"  {destination.name}: {completed / size:.0%}", flush=True)
                reported = time.monotonic()
    assembled = destination.with_name(destination.name + ".assembling")
    with assembled.open("wb") as stream:
        for index, _, _ in ranges:
            with (parts / f"{index:05d}").open("rb") as chunk:
                shutil.copyfileobj(chunk, stream, length=8 * 1024 * 1024)
    if assembled.stat().st_size != size:
        raise RuntimeError(f"Incorrect assembled size: {destination.name}")
    assembled.replace(destination)
    for index, _, _ in ranges:
        (parts / f"{index:05d}").unlink()
    parts.rmdir()

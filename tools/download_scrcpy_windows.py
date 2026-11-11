# Download latest scrcpy Windows x64 portable package into tools/scrcpy
# Uses only Python standard library.

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = HERE / "scrcpy"
API = "https://api.github.com/repos/Genymobile/scrcpy/releases/latest"


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "AndroidScrcpyManager"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url: str, out: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "AndroidScrcpyManager"})
    with urllib.request.urlopen(req, timeout=120) as r, out.open("wb") as f:
        shutil.copyfileobj(r, f)


def main() -> int:
    if DEST.joinpath("scrcpy.exe").exists():
        print("scrcpy already exists:", DEST)
        return 0

    print("Fetching latest scrcpy release...")
    data = get_json(API)
    assets = data.get("assets", [])
    candidates = []
    for a in assets:
        name = a.get("name", "")
        if name.endswith(".zip") and "win64" in name.lower():
            candidates.append(a)
    if not candidates:
        print("Cannot find win64 zip in latest release.")
        print("Download manually from: https://github.com/Genymobile/scrcpy/releases")
        return 2

    asset = candidates[0]
    url = asset["browser_download_url"]
    name = asset["name"]

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / name
        print("Downloading:", name)
        download(url, tmp)

        extract = Path(td) / "extract"
        extract.mkdir()
        print("Extracting...")
        with zipfile.ZipFile(tmp, "r") as z:
            z.extractall(extract)

        roots = [p for p in extract.iterdir() if p.is_dir()]
        if not roots:
            print("Bad zip structure.")
            return 3

        src = roots[0]
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.copytree(src, DEST)

    if not DEST.joinpath("scrcpy.exe").exists():
        print("scrcpy.exe not found after extract.")
        return 4

    print("Installed scrcpy to:", DEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

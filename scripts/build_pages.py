"""Stage a clean Shinylive bundle and export static site to _site/ for GitHub Pages."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE_DIR = ROOT / "_shinylive_src"
OUT_DIR = ROOT / "_site"

# Only copy browser-safe modules (omit grant_finder/sources.py so Shinylive
# does not try to bundle server-only dependencies like httpx/feedparser/bs4).
FILES_TO_COPY = [
    "app.py",
    "styles.css",
    "grant_finder/__init__.py",
    "grant_finder/models.py",
    "grant_finder/scoring.py",
    "grant_finder/storage.py",
    "data/grants_cache.json",
]


def main() -> None:
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    for rel in FILES_TO_COPY:
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(f"Required file missing for Shinylive bundle: {src}")
        dst = STAGE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    shinylive_bin = Path(sys.executable).parent / "shinylive"
    exe = str(shinylive_bin) if shinylive_bin.exists() else "shinylive"
    cmd = [exe, "export", str(STAGE_DIR), str(OUT_DIR)]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Shinylive static site exported to {OUT_DIR}")


if __name__ == "__main__":
    main()

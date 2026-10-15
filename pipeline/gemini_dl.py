"""Tool unduh gambar Gemini: clipboard (Copy image address) -> file.

Dipakai otomasi UI: klik kanan gambar > Copy image address, lalu
panggil download_clipboard_image() — tanpa dialog Save manual.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import requests


def read_clipboard() -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        capture_output=True, text=True)
    return (r.stdout or "").strip()


def download_image(url: str, dest: Path, timeout: int = 120) -> Path:
    if not url.startswith(("http://", "https://")):
        raise RuntimeError(f"clipboard bukan URL gambar: {url[:80]}")
    r = requests.get(url, timeout=timeout, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0 Safari/537.36"),
        "Referer": "https://gemini.google.com/",
    })
    if r.status_code != 200 or len(r.content) < 5000:
        raise RuntimeError(
            f"unduh gagal: HTTP {r.status_code}, {len(r.content)} bytes")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def download_clipboard_image(dest: Path) -> Path:
    """Ambil URL dari clipboard lalu unduh ke dest."""
    return download_image(read_clipboard(), dest)


def verify_png(path: Path, min_width: int = 400) -> dict:
    """Pastikan file adalah gambar valid. Return info dasar."""
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
        fmt = im.format
    if w < min_width:
        raise RuntimeError(f"gambar terlalu kecil: {w}x{h}")
    return {"format": fmt, "width": w, "height": h,
            "bytes": path.stat().st_size}

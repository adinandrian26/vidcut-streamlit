"""Menjalankan skrip pipeline sebagai subproses, kembalikan output teks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent.parent  # D:\Automation VidCut
WEB_ROOT = Path(__file__).resolve().parent.parent          # D:\Automation VidCut\web_vidcut


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    script = args[0]
    script_path = Path(script)
    if not script_path.is_absolute():
        # coba relatif ke web_vidcut dulu, lalu root lama
        for base in (WEB_ROOT, APP_ROOT):
            cand = base / script
            if cand.exists():
                script = str(cand)
                break
    p = subprocess.run(
        [sys.executable, script, *args[1:]],
        cwd=str(cwd or WEB_ROOT),
        capture_output=True,
        text=True,
        timeout=3600,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")

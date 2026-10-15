"""Job folders: web_vidcut/jobs/<slug>/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "jobs"


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    return s or "proyek_baru"


def job_dir(slug: str) -> Path:
    d = JOBS / slugify(slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "images").mkdir(exist_ok=True)
    return d


def list_jobs() -> list[str]:
    if not JOBS.exists():
        return []
    return sorted(p.name for p in JOBS.iterdir() if p.is_dir())

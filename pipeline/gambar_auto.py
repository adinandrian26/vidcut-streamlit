"""Generate gambar otomatis via Gemini browser, HEADLESS di background.

Memakai ulang fungsi gemini_batch.py (root repo): kirim prompt per shot,
tunggu gambar, unduh ke images/. Berjalan per batch agar bisa dicicil.

Profil khusus: <repo>/profile_auto (bukan Chrome utama user), jadi:
- tidak ada jendela Chrome yang terbuka,
- tidak berebut profil dengan browser harian,
- login cukup SEKALI via gemini_login.py.
"""
from __future__ import annotations

import importlib.util
import random
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent.parent
AUTO_PROFILE = APP_ROOT / "profile_auto"


def _load_gb():
    spec = importlib.util.spec_from_file_location(
        "gemini_batch", str(APP_ROOT / "gemini_batch.py"))
    gb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gb)
    return gb


def open_auto_context(p, headless: bool = True):
    """Buka konteks Playwright headless di profil otomasi."""
    AUTO_PROFILE.mkdir(exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        str(AUTO_PROFILE),
        headless=headless,
        channel="chrome",
        ignore_default_args=["--enable-automation",
                             "--disable-blink-features=AutomationControlled"],
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(_load_gb().GEMINI_URL)
    return ctx, page


def _is_logged_in(page, gb) -> bool:
    """Login = kotak prompt ada DAN tidak ada link login Google.

    (Halaman logged-out Gemini tetap menampilkan kotak prompt,
    jadi cek input saja tidak cukup.)
    """
    try:
        has_input = page.locator(gb.SEL["input"]).count() > 0
        has_login = page.locator("a[href*=ServiceLogin]").count() > 0
        return has_input and not has_login
    except Exception:
        return False


def check_login(timeout_ms: int = 15000) -> bool:
    """Cek cepat (headless) apakah profil otomasi sudah login Gemini."""
    gb = _load_gb()
    sync_playwright, _ = gb.pw_modules()
    try:
        with sync_playwright() as p:
            ctx, page = open_auto_context(p, headless=True)
            try:
                page.wait_for_selector(gb.SEL["input"], timeout=timeout_ms)
                page.wait_for_timeout(3000)
                return _is_logged_in(page, gb)
            except Exception:
                return False
            finally:
                ctx.close()
    except Exception:
        return False


def run_batch(job_dir: Path, batch_size: int = 5,
              progress=None, log=None) -> dict:
    """Generate maksimal batch_size gambar yang hilang. Return ringkasan."""
    gb = _load_gb()
    gb.SHOTS_FILE = job_dir / "shots.json"
    gb.OUT_DIR = job_dir / "images"
    shots = gb.load_shots()
    todo = [s for s in shots if not gb.already_done(s["id"])][:batch_size]
    if not todo:
        return {"total": len(shots), "done": 0, "failed": [], "sisa": 0}

    sync_playwright, PWTimeout = gb.pw_modules()
    done, failed = 0, []
    with sync_playwright() as p:
        ctx, page = open_auto_context(p, headless=True)
        try:
            page.wait_for_selector(gb.SEL["input"], timeout=20000)
            page.wait_for_timeout(3000)
            if not _is_logged_in(page, gb):
                raise RuntimeError(
                    "Profil otomasi belum login Gemini. Jalankan sekali: "
                    "python web_vidcut/gemini_login.py "
                    "(login manual di jendela yang terbuka), lalu klik lagi.")
            in_chat = 0
            for n, shot in enumerate(todo, 1):
                if in_chat >= gb.CHAT_EVERY:
                    gb.new_chat(page, PWTimeout)
                    in_chat = 0
                ok = False
                for _ in range(1 + gb.RETRIES):
                    try:
                        gb.generate_one(page, shot, PWTimeout)
                        ok = True
                        break
                    except gb.StopRun:
                        raise
                    except Exception as e:
                        if log:
                            log(f"shot {shot['id']:03d} gagal: {e} — chat baru")
                        gb.new_chat(page, PWTimeout)
                        in_chat = 0
                if ok:
                    done += 1
                    in_chat += 1
                    if log:
                        log(f"shot {shot['id']:03d} tersimpan ({done}/{len(todo)})")
                else:
                    failed.append(shot["id"])
                if progress:
                    progress(n, len(todo))
                time.sleep(max(1.0, gb.DELAY + random.uniform(-gb.JITTER, gb.JITTER)))
        finally:
            ctx.close()
    sisa = len([s for s in shots if not gb.already_done(s["id"])])
    return {"total": len(shots), "done": done, "failed": failed, "sisa": sisa}

"""Sinkron model dari config opencode lokal + eksekusi via `opencode run`.

Hanya membaca nama provider/model. Tidak pernah membaca atau
menampilkan API key / secret apa pun.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "opencode"
CONFIG_FILES = ("opencode.jsonc", "opencode.json", "opencode.jsonc.bak")


def _load_json_lenient(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    lines = [l for l in text.splitlines() if not l.strip().startswith("//")]
    data = json.loads("\n".join(lines))
    return data if isinstance(data, dict) else {}


def sync_opencode_models() -> list[str]:
    """Kumpulkan semua id model format provider/model dari config lokal."""
    found: set[str] = set()
    for name in ("opencode.jsonc", "opencode.json"):
        p = CONFIG_DIR / name
        if not p.exists():
            continue
        try:
            data = _load_json_lenient(p)
        except (OSError, ValueError):
            continue
        providers = data.get("provider", {})
        if not isinstance(providers, dict):
            continue
        for pname, cfg in providers.items():
            if not isinstance(cfg, dict):
                continue
            models = cfg.get("models", {})
            if isinstance(models, dict):
                for m in models:
                    found.add(f"{pname}/{m}")
    slim = CONFIG_DIR / "oh-my-opencode-slim.json"
    if slim.exists():
        try:
            data = _load_json_lenient(slim)
        except (OSError, ValueError):
            data = {}
        presets = data.get("presets", {})
        if isinstance(presets, dict):
            for group in presets.values():
                if not isinstance(group, dict):
                    continue
                for agent in group.values():
                    if isinstance(agent, dict):
                        m = agent.get("model")
                        if isinstance(m, str) and "/" in m:
                            found.add(m.split("#")[0])
    return sorted(found)


def run_opencode_model(model_id: str, prompt: str, workdir: Path,
                       timeout: int = 300) -> str:
    """Jalankan `opencode run -m <model> <prompt>`, kembalikan output teks."""
    if not re.fullmatch(r"[\w\-.]+/[\w\-.]+", model_id):
        raise RuntimeError(f"id model tidak valid: {model_id}")
    if shutil.which("opencode") is None:
        raise RuntimeError("CLI opencode tidak ditemukan di PATH.")
    try:
        # shell=True: opencode terpasang sebagai shim .cmd/.ps1 via npm,
        # yang hanya bisa dieksekusi lewat cmd.exe di Windows.
        p = subprocess.run(
            ["opencode", "run", "-m", model_id, prompt],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"opencode timeout ({timeout}s).") from e
    except OSError as e:
        raise RuntimeError(f"gagal jalankan opencode: {e}") from e
    if p.returncode != 0:
        err = (p.stderr or p.stdout)[:300]
        if "524" in err:
            raise RuntimeError(
                "provider timeout (HTTP 524): server KelontongAI tidak menjawab "
                "tepat waktu. Coba lagi, atau potong naskah jadi bagian kecil.")
        raise RuntimeError(f"opencode gagal: {err}")
    return (p.stdout or "").strip()


def split_chunks(text: str, max_chars: int = 3000) -> list[str]:
    """Pecah naskah per paragraf agar tiap request ke model tetap pendek.

    Paragraf raksasa (> max_chars) dipecah lagi per kalimat.
    """
    paras: list[str] = []
    for p in (x.strip() for x in text.split("\n")):
        if not p:
            continue
        if len(p) <= max_chars:
            paras.append(p)
        else:
            sents = re.split(r"(?<=[.!?…])\s+", p)
            cur = ""
            for s in sents:
                if len(cur) + len(s) + 1 <= max_chars:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        paras.append(cur)
                    cur = s
            if cur:
                paras.append(cur)
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= max_chars:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def polish_naskah(model_id: str, instruksi: str, naskah: str,
                  workdir: Path, timeout: int = 300,
                  progress=None) -> str:
    """Poles naskah panjang per bagian agar tidak kena timeout provider."""
    chunks = split_chunks(naskah)
    outs = []
    for i, ch in enumerate(chunks, 1):
        prompt = (f"{instruksi}\n\nBagian {i} dari {len(chunks)}, "
                  f"poles hanya bagian ini:\n{ch}")
        outs.append(run_opencode_model(model_id, prompt, workdir, timeout))
        if progress:
            progress(i, len(chunks))
    return "\n\n".join(outs)

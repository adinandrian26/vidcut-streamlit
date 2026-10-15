"""Model presets + OpenAI-compatible chat call.

API key tidak pernah ditulis ke log. Key diambil dari sidebar atau
st.secrets (lihat .streamlit/secrets.toml.example).
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MODELS_FILE = ROOT / "models.json"

DEFAULT_PRESETS = {
    "presets": [
        {
            "name": "KelontongAI (isi endpoint & model)",
            "base_url": "https://api.contoh-provider.com/v1",
            "model": "isi-nama-model",
        },
        {
            "name": "Gratisan opencode (isi endpoint & model)",
            "base_url": "https://api.contoh-gratis.com/v1",
            "model": "isi-nama-model-gratis",
        },
    ]
}


def load_presets() -> dict:
    if not MODELS_FILE.exists():
        MODELS_FILE.write_text(
            json.dumps(DEFAULT_PRESETS, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return json.loads(MODELS_FILE.read_text(encoding="utf-8"))


def _guard_placeholder(base_url: str) -> None:
    if "contoh" in base_url or "example" in base_url:
        raise RuntimeError(
            "endpoint masih contoh — ganti dengan endpoint asli provider, "
            "atau pilih preset KelontongAI.")


def list_models(base_url: str, api_key: str, timeout: int = 30) -> list[str]:
    """Ambil daftar id model dari endpoint OpenAI-compatible (GET /models).

    Dipakai tombol "Tes koneksi & sinkron model": sekaligus membuktikan
    API key konek dan mengisi pilihan model otomatis.
    """
    _guard_placeholder(base_url)
    url = base_url.rstrip("/") + "/models"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"tidak bisa hubungi endpoint: {e}") from e
    if r.status_code == 401:
        raise RuntimeError("API key ditolak (401). Periksa key.")
    if r.status_code == 404:
        raise RuntimeError("endpoint /models tidak ada (404). Periksa base URL.")
    if r.status_code != 200:
        raise RuntimeError(f"endpoint error {r.status_code}: {r.text[:200]}")
    try:
        ids = [m["id"] for m in r.json()["data"]]
    except (KeyError, TypeError, ValueError) as e:
        raise RuntimeError(
            f"format daftar model tidak dikenal: {r.text[:200]}") from e
    if not ids:
        raise RuntimeError("endpoint tidak mengembalikan model apa pun.")
    return sorted(ids)


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    timeout: int = 120,
) -> str:
    _guard_placeholder(base_url)
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"tidak bisa hubungi endpoint model: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(f"endpoint model error {r.status_code}: {r.text[:300]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"respons model tidak dikenal: {r.text[:300]}") from e

"""Generate naskah cerita gaya explainer dari judul.

Gaya mengacu ke referensi: Relic Explains, Ink Explainer, dan
SAM StoryOfAncientMan — judul pertanyaan besar, hook di 10 detik
pertama, bahasa santai sehari-hari, fakta bertahap per adegan,
kalimat pendek visual, tutup refleksi + ajakan diskusi.

Strategi anti-timeout: outline dulu (pendek), lalu tulis per babak
satu per satu, digabung di akhir.
"""
from __future__ import annotations

import re
from pathlib import Path

GAYA = """Kamu penulis naskah video explainer Bahasa Indonesia gaya kanal
Relic Explains / Ink Explainer / StoryOfAncientMan.

Aturan gaya (wajib):
- Buka dengan pertanyaan besar yang bikin penasaran (hook, maks 10 detik baca).
- Bahasa santai sehari-hari: pakai "kamu", "bayangin", "coba pikir".
- Jelaskan bertahap, satu fakta satu adegan, pakai analogi sederhana.
- Kalimat pendek (maks 20 kata), satu ide per kalimat.
- Tanpa judul bab, tanpa stage direction, tanpa emoji — hanya narasi dibacakan.
- Tutup dengan satu pertanyaan refleksi + ajakan tulis pendapat di komentar."""

DURASI = {
    "Pendek ±3 mnt (±450 kata)": {"babak": 4, "kata": 450},
    "Sedang ±8 mnt (±1200 kata)": {"babak": 7, "kata": 1200},
    "Panjang ±15 mnt (±2000 kata)": {"babak": 10, "kata": 2000},
}


def _minta_outline(tanya, judul: str, n_babak: int) -> list[str]:
    out = tanya(
        f"{GAYA}\n\nTopik: {judul}\n\n"
        f"Buatkan outline {n_babak} babak untuk video ini. "
        f"Balas HANYA daftar bernomor, satu baris per babak, "
        f"format: '1. <kalimat topik babak>'. Tanpa pembuka/penutup."
    )
    babak = []
    for line in out.splitlines():
        m = re.match(r"\s*\d+[.)]\s*(.+)", line.strip())
        if m:
            babak.append(m.group(1).strip())
    if len(babak) < 2:
        raise RuntimeError("outline dari model tidak bisa dibaca.")
    return babak[:n_babak]


def _tulis_babak(tanya, judul: str, i: int, n: int, topik: str,
                 kata_per_babak: int) -> str:
    return tanya(
        f"{GAYA}\n\nTopik video: {judul}\n\n"
        f"Tulis babak {i} dari {n} tentang: {topik}\n"
        f"Panjang ±{kata_per_babak} kata. Balas HANYA narasi babak ini, "
        f"tanpa label babak, tanpa pembuka/penutup."
    ).strip()


def generate_cerita(tanya, judul: str, durasi_label: str,
                    progress=None) -> str:
    """tanya(prompt) -> str. Kembalikan naskah lengkap."""
    target = DURASI[durasi_label]
    n = target["babak"]
    kata = max(120, target["kata"] // n)
    total = n + 1
    if progress:
        progress(0, total, "Membuat outline...")
    babak = _minta_outline(tanya, judul, n)
    bagian = []
    for i, topik in enumerate(babak, 1):
        if progress:
            progress(i, total, f"Menulis babak {i}/{len(babak)}...")
        bagian.append(_tulis_babak(tanya, judul, i, len(babak), topik, kata))
    return "\n\n".join(bagian)


def tanya_via_opencode(model_id: str, workdir: Path):
    from pipeline import opencode_models

    def tanya(prompt: str) -> str:
        return opencode_models.run_opencode_model(model_id, prompt, workdir)
    return tanya


def tanya_via_endpoint(base_url: str, api_key: str, model: str):
    from pipeline import models

    def tanya(prompt: str) -> str:
        return models.chat_completion(
            base_url, api_key, model, [{"role": "user", "content": prompt}])
    return tanya

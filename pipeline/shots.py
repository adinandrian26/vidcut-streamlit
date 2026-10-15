"""Shotlist 1 gambar per kalimat + prompt visual stick figure."""
from __future__ import annotations

import json
import re
from pathlib import Path

MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]

SCENES = [
    (["selfi", "media sosial", "unggah", "foto", "video"], "stickman woman taking selfie with smartphone"),
    (["mewah", "restoran", "kelas atas", "mahal"], "stickman character dining in fancy restaurant"),
    (["tas bermerek", "bermerek", "belanja"], "stickman woman holding shopping bags with luxury items"),
    (["pirang", "glowing", "penampilan", "cantik", "modis"], "stickman woman looking in mirror, dressed fashionably"),
    (["taiwan", "kota", "gedung"], "stickman standing in modern city with tall buildings"),
    (["kampung", "halaman", "desa"], "simple village houses, stickman walking on rural road"),
    (["kagum", "iri"], "stickman looking at phone with envious expression"),
    (["keluarga", "anak", "orang tua", "suami", "istri"], "stickman family, mother father and child together"),
    (["rindu", "kesepian", "sunyi", "sendiri", "sendirian"], "lonely stickman sitting alone in dark room"),
    (["kerja", "penghasilan", "gaji", "tabungan"], "stickman working hard, carrying heavy boxes"),
    (["utang", "keuangan", "pengeluaran"], "stickman calculating money with worried face, bills"),
    (["perceraian", "perpisahan", "retak", "berantakan"], "two stickman walking away from each other, broken heart"),
    (["komunikasi", "telepon"], "stickman making video call on smartphone"),
    (["komentar", "pujian", "dihargai"], "stickman reading positive comments on phone, happy"),
    (["senyum", "bahagia", "ceria"], "smiling happy stickman character"),
    (["sedih", "menyakitkan", "luka", "menangis"], "sad stickman crying, teardrop"),
    (["banding"], "two stickman comparing their phones side by side"),
    (["renung", "pikir", "tanya", "pertanyaan"], "stickman thinking with question mark above head"),
    (["waktu", "jam"], "stickman looking at clock, time passing concept"),
    (["rumah", "renovasi"], "simple house illustration, stickman repairing roof"),
    (["pulang", "kembali"], "stickman with suitcase arriving home at airport"),
    (["berhasil", "sukses", "menang"], "victorious stickman raising arms, trophy"),
    (["masa depan", "impian", "harapan", "mimpi"], "stickman looking at sunrise, hopeful future"),
    (["sederhana"], "stickman content with simple life, small house"),
    (["diskusi", "komentar kolom"], "group of stickman characters discussing together"),
]

FALLBACK = "stickman woman with smartphone in city, emotional storytelling scene"
STYLE = ("flat vector illustration, thick black stickman character, minimalist "
         "cartoon style, simple pastel background, clean flat design, no text, "
         "ratio 16:9")


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        out.extend(
            s.strip()
            for s in re.split(r"(?<=[.!?…])\s+", para)
            if s.strip()
        )
    return out


def scene_for(sent: str) -> str:
    low = sent.lower()
    for keys, scene in SCENES:
        if any(k in low for k in keys):
            return scene
    return FALLBACK


def build(job: Path, sentences: list[str]) -> dict:
    """Tulis shotlist.md, image_prompts.md, shots.json. Return ringkasan.

    Format shotlist mengikuti make_shotlist.py agar cocok dengan
    build_timeline.py: ID | Kutipan narasi | Deskripsi visual | Emosi | SFX.
    Gambar per kalimat memakai pola images/NNN.png + motion berputar
    (disimpan di shots.json agar konsisten dengan timeline).
    """
    rows = ["| ID | Kutipan narasi | Deskripsi visual | Emosi | SFX |",
            "|----|----------------|------------------|-------|-----|"]
    prompts = ["# Image Prompts (Gemini browser, Profile 3)", ""]
    shots = []
    for i, s in enumerate(sentences, 1):
        motion = MOTIONS[(i - 1) % len(MOTIONS)]
        visual = f"{STYLE}. Scene: {scene_for(s)}"
        rows.append(f"| {i} | {s.replace('|', '/')} | {visual} | - | - |")
        prompts.append(f"## {i:03d}\n{s}\n\n{visual}\n")
        shots.append({"id": i, "motion": motion,
                      "image": f"{i:03d}.png", "prompt": visual})
    (job / "shotlist.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (job / "image_prompts.md").write_text("\n".join(prompts), encoding="utf-8")
    (job / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"kalimat": len(sentences)}

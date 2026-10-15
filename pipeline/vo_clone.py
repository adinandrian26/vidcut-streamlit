#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate VO gaya tiruan per preset + tulis vo.srt.

Preset 'homo_sapiens' meniru gaya narasi referensi
assets/referensi_homo_sapiens.mp3 (pitch rendah, tempo cepat-energik,
jeda dramatis, intonasi bervariasi per jenis kalimat).

Pakai: python vo_clone.py --naskah naskah.txt --out-mp3 vo.mp3
       --out-srt vo.srt --preset homo_sapiens
"""
from __future__ import annotations

import argparse
import asyncio
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

random.seed(42)

PRESETS = {
    # Diukur dari referensi: pitch median ~113 Hz, tempo energik.
    "homo_sapiens": {
        "voice": "id-ID-ArdiNeural",
        "q": ("+4%", "+4Hz", 0.55),   # tanya: naik, penasaran
        "x": ("+8%", "+1Hz", 0.45),   # seru: cepat, energi
        "s": ("+1%", "-5Hz", 0.30),   # biasa: rendah, tenang
        "para_pause": 0.75,
    },
}


def split_sentences(text: str) -> list[tuple[str, str, bool]]:
    out: list[tuple[str, str, bool]] = []
    for para in (p.strip() for p in text.split("\n")):
        if not para:
            continue
        sents = re.findall(r"[^.!?…]+[.!?…]+|[^.!?…]+$", para)
        sents = [s.strip() for s in sents if s.strip()]
        for j, s in enumerate(sents):
            kind = "q" if s.endswith("?") else ("x" if s.endswith("!") else "s")
            out.append((s, kind, j == len(sents) - 1))
    return out


def _adj(spec: str, delta: int, unit: str) -> str:
    m = re.match(r"([+-])(-?\d+)", spec)
    sign, num = m.group(1), int(m.group(2))
    val = max(-12, min(12, num + delta))
    return f"{sign}{val}{unit}" if val >= 0 else f"{sign}{-val}{unit}"


def prosody(sent: str, kind: str, cfg: dict) -> tuple[str, str]:
    rate, pitch, _ = cfg[kind]
    rate = _adj(rate, random.choice([-1, 0, 0, 1]), "%")
    pitch = _adj(pitch, random.choice([-2, -1, 0, 1, 2]), "Hz")
    if len(sent) > 160:
        rate = _adj(rate, -2, "%")
    return rate, pitch


def ffprobe_dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1",
                        str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def sec_to_ts(t: float) -> str:
    t = max(0.0, t)
    h, m = int(t // 3600), int((t % 3600) // 60)
    s, ms = int(t % 60), int(round((t - int(t)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


async def synth(sent: str, voice: str, rate: str, pitch: str,
                path: Path, tries: int = 4) -> None:
    import asyncio as _aio
    import edge_tts as _et
    for attempt in range(tries):
        try:
            comm = _et.Communicate(sent, voice, rate=rate, pitch=pitch)
            await comm.save(str(path))
            if path.stat().st_size > 500:
                return
        except Exception:
            if attempt == tries - 1:
                raise
            await _aio.sleep(1.5 * (attempt + 1))


async def build(naskah: Path, out_mp3: Path, out_srt: Path,
                preset: str) -> None:
    cfg = PRESETS[preset]
    naskah = naskah.resolve()
    out_mp3 = out_mp3.resolve()
    out_srt = out_srt.resolve()
    sentences = split_sentences(naskah.read_text(encoding="utf-8"))
    if not sentences:
        raise SystemExit("ERROR: naskah kosong.")
    tmp = Path(tempfile.mkdtemp(prefix="voclon_"))
    srt_lines, parts, t = [], [], 0.0
    total = len(sentences)
    pauses_used: list[float] = []
    for i, (sent, kind, para_end) in enumerate(sentences, 1):
        rate, pitch = prosody(sent, kind, cfg)
        piece = tmp / f"seg_{i:04d}.mp3"
        await synth(sent, cfg["voice"], rate, pitch, piece)
        d = ffprobe_dur(piece)
        srt_lines.append("%d\n%s --> %s\n%s\n"
                         % (i, sec_to_ts(t), sec_to_ts(t + d), sent))
        parts.append(piece)
        pause = cfg["para_pause"] if para_end else cfg[kind][2]
        pauses_used.append(pause)
        t += d + pause
        if i % 20 == 0:
            print(f"  {i}/{total}", flush=True)
    # jeda sesuai jenis kalimat agar audio cocok dengan vo.srt
    pauses = sorted(set(pauses_used))
    sil_files: dict[float, Path] = {}
    for pz in pauses:
        sp = tmp / f"sil_{int(pz * 1000):04d}.mp3"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "anullsrc=r=24000:cl=mono", "-t", str(pz),
                        "-c:a", "libmp3lame", str(sp)], check=True)
        sil_files[pz] = sp
    lst = tmp / "list.txt"
    lines: list[str] = []
    for p, pz in zip(parts, pauses_used):
        lines.append(f"file '{p.as_posix()}'")
        lines.append(f"file '{sil_files[pz].name}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    import shutil
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c:a", "libmp3lame", "-q:a", "4",
                    str(out_mp3)], check=True, cwd=str(tmp))
    out_srt.write_text("\n".join(srt_lines), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"OK: {out_mp3} ({len(sentences)} kalimat) -> {out_srt}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--naskah", required=True)
    ap.add_argument("--out-mp3", required=True)
    ap.add_argument("--out-srt", required=True)
    ap.add_argument("--preset", default="homo_sapiens",
                    choices=list(PRESETS))
    args = ap.parse_args()
    asyncio.run(build(Path(args.naskah), Path(args.out_mp3),
                      Path(args.out_srt), args.preset))


if __name__ == "__main__":
    main()

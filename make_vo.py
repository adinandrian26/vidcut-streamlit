#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""naskah.txt -> vo.mp3 + vo.srt memakai edge-tts (id-ID-ArdiNeural).
Setiap kalimat disintesis terpisah supaya timestamp SRT presisi,
lalu semua potongan digabung dengan ffmpeg. Durasi mp3 >= akhir cue terakhir.
Butuh: pip install edge-tts  (dan ffmpeg di PATH).
"""
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path

VOICE = "id-ID-ArdiNeural"
RATE = "+0%"

SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")

def split_sentences(text):
    text = re.sub(r"\s+", " ", text.replace("\r\n", "\n")).strip()
    sents = [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]
    out = []
    for s in sents:
        if len(s) <= 120:
            out.append(s)
            continue
        # pecah kalimat panjang di koma terdekat
        parts, cur = [], ""
        for w in s.split(" "):
            cand = (cur + " " + w).strip()
            if len(cand) <= 120 and ("," in w or len(cand) < 90):
                cur = cand
                if w.endswith(","):
                    parts.append(cur); cur = ""
            else:
                if cur: parts.append(cur)
                cur = w
        if cur: parts.append(cur)
        out.extend(parts)
    return out


def ffprobe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", str(p)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def sec_to_ts(t):
    t = max(0.0, t)
    h, m = int(t // 3600), int((t % 3600) // 60)
    s, ms = int(t % 60), int(round((t - int(t)) * 1000))
    if ms == 1000: s, ms = s + 1, 0
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--naskah", default="naskah.txt")
    ap.add_argument("--out-mp3", default="vo.mp3")
    ap.add_argument("--out-srt", default="vo.srt")
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--rate", default=RATE)
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        sys.exit("ERROR: ffmpeg/ffprobe tidak ada di PATH.")
    try:
        import edge_tts  # noqa
    except ImportError:
        sys.exit("ERROR: edge-tts belum terpasang. Jalankan: pip install edge-tts")

    text = Path(args.naskah).read_text(encoding="utf-8-sig")
    sentences = split_sentences(text)
    if not sentences:
        sys.exit("ERROR: naskah kosong.")

    tmp = Path(tempfile.mkdtemp(prefix="vo_"))
    srt_lines, mp3_parts, t = [], [], 0.0
    gap = 0.05  # jeda antar kalimat (detik)

    async_impl = None
    import asyncio, edge_tts as et

    async def synth(s, path, tries=4):
        import asyncio as _aio
        for attempt in range(tries):
            try:
                comm = et.Communicate(s, args.voice, rate=args.rate)
                await comm.save(str(path))
                if path.stat().st_size > 0:
                    return
            except Exception as e:
                if attempt == tries - 1:
                    raise
                print("  retry %d/%d: %s" % (attempt + 1, tries - 1, e))
                await _aio.sleep(2 * (attempt + 1))

    async def synth_all():
        # Satu event loop menghindari overhead asyncio.run per kalimat.
        # Empat request simultan mempercepat naskah panjang tanpa membanjiri TTS.
        sem = asyncio.Semaphore(4)
        async def one(i, s):
            async with sem:
                await synth(s, tmp / ("seg_%03d.mp3" % i))
        await asyncio.gather(*(one(i, s) for i, s in enumerate(sentences)))

    asyncio.run(synth_all())
    for i, s in enumerate(sentences):
        piece = tmp / ("seg_%03d.mp3" % i)
        d = ffprobe_dur(piece)
        start, end = t, t + d
        srt_lines.append("%d\n%s --> %s\n%s\n" % (i + 1, sec_to_ts(start),
                                                  sec_to_ts(end), s))
        mp3_parts.append(piece)
        t = end + gap

    # gabung audio dengan jeda kecil
    lst = tmp / "list.txt"
    lines = []
    for p in mp3_parts:
        lines.append("file '%s'" % p.as_posix())
        lines.append("file 'sil.mp3'")
    # silence 50ms
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=24000:cl=mono", "-t", str(gap),
                    "-c:a", "libmp3lame", str(tmp / "sil.mp3")], check=True)
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c:a", "libmp3lame", "-q:a", "4",
                    args.out_mp3], check=True)

    total = ffprobe_dur(args.out_mp3)
    Path(args.out_srt).write_text("\n".join(srt_lines), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK: %s (%.2f s), %d cue -> %s" % (args.out_mp3, total, len(srt_lines),
                                             args.out_srt))
    if total + 0.01 < t:
        print("WARNING: durasi mp3 (%.2f) < akhir cue terakhir (%.2f)" % (total, t))


if __name__ == "__main__":
    main()

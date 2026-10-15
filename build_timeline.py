#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TUGAS C: vo.srt + shotlist.md -> timeline.json + subtitle.srt
Python 3 standar, tanpa library eksternal."""
import argparse, difflib, json, re, sys
from pathlib import Path

MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]


# ---------- parsing ----------

def parse_shotlist(path):
    """Tabel markdown: ID | Kutipan narasi | Deskripsi visual | Emosi | SFX"""
    scenes = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if re.fullmatch(r"[-: ]+", cells[0] or "-") or cells[0].lower() == "id":
            continue
        sid = cells[0]
        if not re.fullmatch(r"\d+", sid):
            continue
        quote = cells[1] if len(cells) > 1 else ""
        sfx_raw = cells[4] if len(cells) > 4 else ""
        sfx = [] if sfx_raw.strip() in ("", "-") else [
            s.strip() for s in sfx_raw.split(",") if s.strip()]
        scenes.append({"id": int(sid), "narration": quote, "sfx": sfx})
    scenes.sort(key=lambda s: s["id"])
    return scenes


def ts_to_sec(ts):
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    """Return list of dict: index, start, end, text (multi-baris digabung spasi)."""
    text = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues = []
    for block in blocks:
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        idx = lines[0].strip()
        m = re.match(
            r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1] if len(lines) > 1 else "")
        if not m:
            m = re.match(
                r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[0])
            if not m:
                continue
            body = lines[1:]
        else:
            body = lines[2:]
        cues.append({
            "index": idx,
            "start": ts_to_sec(m.group(1)),
            "end": ts_to_sec(m.group(2)),
            "text": " ".join(body).strip(),
        })
    return cues


# ---------- matching ----------

def normalize(s):
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def first_words(s, n=5):
    w = normalize(s).split()
    return " ".join(w[:n])


def match_cues(scenes, cues):
    """Berjalan maju, tidak pernah mundur. Return (per-scene cue list/None, warnings)."""
    warnings = []
    pos = 0  # posisi cue terakhir yang dipakai
    for sc in scenes:
        found = None
        key = first_words(sc["narration"], 5)
        if key:
            for i in range(pos, len(cues)):
                if key in normalize(cues[i]["text"]):
                    found = i
                    break
        if found is None:
            # fallback: SequenceMatcher 0.6 pada gabungan 2 cue berurutan
            target = normalize(sc["narration"])
            best_ratio, best_i = 0.0, None
            for i in range(pos, max(pos, len(cues) - 1)):
                joined = normalize(cues[i]["text"] + " " + cues[i + 1]["text"])
                r = difflib.SequenceMatcher(None, target, joined).ratio()
                if r > best_ratio:
                    best_ratio, best_i = r, i
            if best_i is not None and best_ratio >= 0.6:
                found = best_i
        if found is None:
            warnings.append(
                "Scene S%03d: kutipan narasi tidak ditemukan di vo.srt "
                "(pencarian dari cue ke-%d)." % (sc["id"], pos + 1))
            sc["_cue"] = None
        else:
            sc["_cue"] = found
            pos = found + 1
    return warnings


# ---------- timeline ----------

def build_timeline(scenes, cues, warnings):
    scenes_out = []
    starts = []
    for sc in scenes:
        ci = sc.get("_cue")
        if ci is None:
            starts.append(None)
        else:
            starts.append(round(cues[ci]["start"], 2))
    # scene tanpa cue: start = end scene sebelumnya (= start scene berikutnya yang valid
    # atau dibiarkan mengikuti sebelumnya); kita pakai start scene sebelumnya
    for i, sc in enumerate(scenes):
        if starts[i] is None:
            starts[i] = starts[i - 1] if i > 0 else 0.0
    # end = start scene berikutnya, tanpa celah; pastikan menaik
    n = len(scenes)
    duration = round(cues[-1]["end"], 2) if cues else 0.0
    for i, sc in enumerate(scenes):
        if i < n - 1:
            end = starts[i + 1]
            if end <= starts[i]:
                end = starts[i]  # jaga supaya durasi >= 0
        else:
            end = duration
            if end <= starts[i]:
                end = starts[i] + 0.1
        motion = MOTIONS[i % len(MOTIONS)]
        sfx_list = [{"file": s, "at": starts[i], "volume": 0.6} for s in sc["sfx"]]
        scenes_out.append({
            "id": "S%03d" % sc["id"],
            "start": round(starts[i], 2),
            "end": round(end, 2),
            "image": "%03d.png" % sc["id"],
            "narration": sc["narration"],
            "motion": motion,
            "transition": "cut",
            "sfx": sfx_list,
        })
    return scenes_out


# ---------- subtitle ----------

def wrap_42(text):
    """Pecah teks jadi chunk <=42 char, maksimal 2 baris per cue.
    Return list of cue-text (string, bisa 1-2 baris)."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= 42:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    # gabung 2 baris per cue
    cues = []
    for i in range(0, len(lines), 2):
        pair = lines[i:i + 2]
        cues.append("\n".join(pair))
    return cues


def sec_to_ts(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def build_subtitles(cues):
    out = []
    n = 1
    for c in cues:
        chunks = wrap_42(c["text"])
        if not chunks:
            continue
        dur = c["end"] - c["start"]
        total_chars = sum(len(ch.replace("\n", " ")) for ch in chunks)
        t = c["start"]
        for j, ch in enumerate(chunks):
            chars = len(ch.replace("\n", " "))
            share = dur * chars / total_chars if total_chars else dur / len(chunks)
            start = t
            end = c["end"] if j == len(chunks) - 1 else t + share
            out.append("%d\n%s --> %s\n%s\n" % (
                n, sec_to_ts(start), sec_to_ts(end), ch))
            t = end
            n += 1
    return "\n".join(out)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srt", default="vo.srt")
    ap.add_argument("--shotlist", default="shotlist.md")
    ap.add_argument("--out", default="timeline.json")
    ap.add_argument("--srt-out", default="subtitle.srt")
    args = ap.parse_args()

    scenes = parse_shotlist(args.shotlist)
    cues = parse_srt(args.srt)
    if not scenes:
        sys.exit("ERROR: tidak ada scene terbaca dari %s" % args.shotlist)
    if not cues:
        sys.exit("ERROR: tidak ada cue terbaca dari %s" % args.srt)

    warnings = match_cues(scenes, cues)
    scenes_out = build_timeline(scenes, cues, warnings)
    duration = scenes_out[-1]["end"] if scenes_out else 0.0

    timeline = {
        "video": {"title": "", "fps": 30, "resolution": "1920x1080",
                  "duration": duration},
        "scenes": scenes_out,
        "warnings": warnings,
    }
    Path(args.out).write_text(json.dumps(timeline, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    Path(args.srt_out).write_text(build_subtitles(cues), encoding="utf-8")
    print("OK: %d scene, durasi %.2f detik, %d warning"
          % (len(scenes_out), duration, len(warnings)))
    for w in warnings:
        print("  WARNING:", w)


if __name__ == "__main__":
    main()

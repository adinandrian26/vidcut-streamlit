#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TUGAS D: render final.mp4 dari timeline.json + images + vo + sfx + subs."""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

ZOOM_EXPR = {
    "zoom_in":  "min(1+0.08*on/{frames},1.08)",
    "zoom_out": "1.08-0.08*on/{frames}",
}
PAN_EXPR = {
    "pan_left":  ("(iw-iw/zoom)*(1-on/{frames})", "(ih-ih/zoom)/2"),
    "pan_right": ("(iw-iw/zoom)*(on/{frames})",   "(ih-ih/zoom)/2"),
}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit("FFMPEG ERROR:\n" + r.stderr[-3000:])
    return r


def esc_sub_path(p):
    """Escape path Windows untuk filter subtitles: D\:/path/..."""
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def clip_filter(motion, frames):
    """zoompan filter untuk satu scene; output 1920x1080@30fps."""
    fps = 30
    if motion in ZOOM_EXPR:
        z = ZOOM_EXPR[motion].format(frames=frames)
        x, y = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    else:
        xfmt, y = PAN_EXPR[motion]
        x = xfmt.format(frames=frames)
        z = "1"  # zoom 1 untuk pan murni -> pakai zoom minimal 1
    return (
        "scale=2400:1350:force_original_aspect_ratio=increase,"
        "crop=2400:1350,"
        "zoompan=z='%s':x='%s':y='%s':d=%d:s=1920x1080:fps=%d"
        % (z, x, y, frames, fps)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", default="timeline.json")
    ap.add_argument("--images", default="images")
    ap.add_argument("--vo", default="vo.mp3")
    ap.add_argument("--sfx-dir", default="sfx")
    ap.add_argument("--music", default=None)
    ap.add_argument("--subs", default="subtitle.srt")
    ap.add_argument("--out", default="final.mp4")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ERROR: ffmpeg tidak ditemukan di PATH. "
                 "Install dulu (mis. winget install Gyan.FFmpeg).")

    tl = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    fps = int(tl["video"].get("fps", 30))
    W, H = (854, 480) if args.preview else (1920, 1080)
    out_size = "%dx%d" % (W, H)
    tmp = Path(tempfile.mkdtemp(prefix="vidcut_"))

    # --- 1. render tiap scene jadi klip ---
    clips = []
    for i, sc in enumerate(tl["scenes"]):
        img = Path(args.images) / sc["image"]
        if not img.exists():
            print("WARNING: gambar tidak ada, skip scene %s: %s" % (sc["id"], img))
            continue
        dur = max(0.1, sc["end"] - sc["start"])
        frames = max(1, round(dur * fps))
        out = tmp / ("clip_%03d.mp4" % i)
        vf = clip_filter(sc.get("motion", "zoom_in"), frames)
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(img),
             "-vf", vf + ",scale=%s" % out_size + ",setsar=1,format=yuv420p",
             "-t", "%.3f" % dur, "-r", str(fps),
             "-c:v", "libx264", "-preset", ("veryfast" if args.preview else "medium"),
             "-an", str(out)])
        clips.append(out)

    if not clips:
        sys.exit("ERROR: tidak ada klip yang bisa dirender.")

    # --- 2. concat video ---
    lst = tmp / "list.txt"
    lst.write_text("".join("file '%s'\n" % c.as_posix().replace("'", "'\\''")
                           for c in clips), encoding="utf-8")
    concat = tmp / "concat.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(concat)])

    # --- 3. audio: vo + sfx (adelay) + music ---
    total_ms = int((tl["scenes"][-1]["end"]) * 1000)
    a_inputs, a_filters = [], []
    idx = 0
    a_inputs += ["-i", args.vo]
    a_filters.append("[%d:a]volume=1.0[a0]" % idx)
    idx += 1
    for si, sc in enumerate(tl["scenes"]):
        for sfx in sc.get("sfx", []):
            p = Path(args.sfx_dir) / sfx["file"]
            if not p.exists():
                print("WARNING: SFX tidak ada, dilewati: %s" % p)
                continue
            a_inputs += ["-i", str(p)]
            delay = int(sc["start"] * 1000) + int(sfx.get("at", sc["start"]) * 1000) \
                if sfx.get("at") is None else int(sfx["at"] * 1000)
            a_filters.append(
                "[%d:a]adelay=%d|%d,volume=%.2f[a%d]" % (idx, delay, delay,
                                                         sfx.get("volume", 0.6), idx))
            idx += 1
    if args.music and Path(args.music).exists():
        a_inputs += ["-i", args.music]
        a_filters.append("[%d:a]volume=0.12,atrim=0:%.3f[am]" % (idx, total_ms / 1000))
        labels = ["a0", "am"]
        idx += 1
    else:
        labels = ["a0"]
    labels += ["a%d" % k for k in range(1, idx - (1 if "am" in labels else 0))]
    a_filters.append("%samix=inputs=%d:normalize=0[aout]"
                     % ("".join("[" + l + "]" for l in labels), len(labels)))
    mixed = tmp / "audio.m4a"
    run(["ffmpeg", "-y", *a_inputs,
         "-filter_complex", ";".join(a_filters),
         "-map", "[aout]", "-t", "%.3f" % (total_ms / 1000),
         "-c:a", "aac", "-b:a", "192k", str(mixed)])

    # --- 4. mux + burn subtitle ---
    sub_arg = "subtitles='%s'" % esc_sub_path(str(Path(args.subs).resolve()))
    total_dur = tl["scenes"][-1]["end"] - tl["scenes"][0]["start"]
    run(["ffmpeg", "-y", "-i", str(concat), "-i", str(mixed),
         "-vf", sub_arg + ",format=yuv420p",
         "-t", "%.3f" % total_dur,
         "-c:v", "libx264", "-preset", ("veryfast" if args.preview else "medium"),
         "-c:a", "aac", "-b:a", "192k", "-af", "apad", args.out])

    shutil.rmtree(tmp, ignore_errors=True)
    print("OK: %s" % args.out)


if __name__ == "__main__":
    main()

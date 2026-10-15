import json
import streamlit as st

from pipeline import jobs, runner

st.session_state.setdefault("job", "proyek_baru")
st.title("Timeline CapCut")
st.caption("Langkah 4 — timeline.json + subtitle, render, lalu masuk CapCut.")

job_path = jobs.job_dir(st.session_state["job"])
st.info(f"Job: `{st.session_state['job']}`")

vo_srt = job_path / "vo.srt"
shotlist = job_path / "shotlist.md"
timeline = job_path / "timeline.json"
subtitle = job_path / "subtitle.srt"

with st.container(border=True):
    st.subheader("1. Bangun timeline")
    if st.button("Build timeline", icon=":material/timeline:", type="primary"):
        if not vo_srt.exists() or not shotlist.exists():
            st.error("Butuh vo.srt (halaman VO) dan shotlist.md (halaman Gambar).")
        else:
            with st.spinner("Membangun timeline..."):
                rc, out = runner.run(
                    ["build_timeline.py", "--srt", str(vo_srt),
                     "--shotlist", str(shotlist), "--out", str(timeline),
                     "--srt-out", str(subtitle)],
                    cwd=job_path,
                )
            with st.expander("Log build", expanded=rc != 0):
                st.code(out[-4000:])
            if rc == 0:
                st.success("Timeline selesai.")
                st.rerun()
            else:
                st.error("Build gagal — lihat log.")

if timeline.exists():
    tl = json.loads(timeline.read_text(encoding="utf-8"))
    with st.container(border=True):
        st.metric("Scene", len(tl["scenes"]))
        st.metric("Durasi (detik)", tl["video"]["duration"])
        if tl.get("warnings"):
            st.warning("Warnings:")
            st.code("\n".join(tl["warnings"][:20]))
        else:
            st.success("Tanpa warnings.")
    st.download_button("Unduh timeline.json", data=timeline.read_bytes(),
                       file_name="timeline.json", key="dl_tl")
    st.download_button("Unduh subtitle.srt", data=subtitle.read_bytes(),
                       file_name="subtitle.srt", key="dl_sub")

with st.container(border=True):
    st.subheader("2. Render preview (opsional)")
    if st.button("Render preview 480p", icon=":material/preview:"):
        with st.spinner("Rendering..."):
            rc, out = runner.run(
                ["build_video.py", "--timeline", str(timeline),
                 "--images", str(job_path / "images"),
                 "--vo", str(job_path / "vo.mp3"),
                 "--sfx-dir", str(job_path / "sfx"),
                 "--subs", str(subtitle),
                 "--out", str(job_path / "preview.mp4"), "--preview"],
                cwd=job_path,
            )
        with st.expander("Log render", expanded=rc != 0):
            st.code(out[-4000:])
        if rc == 0:
            st.video(str(job_path / "preview.mp4"))

with st.container(border=True):
    st.subheader("3. Masuk CapCut")
    st.caption("CapCut harus dalam keadaan TERTUTUP sebelum langkah ini.")
    draft_name = st.text_input("Nama draft CapCut", value=st.session_state["job"],
                               key="draft_name")
    if st.button("Tulis ke draft CapCut", icon=":material/movie:"):
        with st.spinner("Menulis draft..."):
            rc, out = runner.run(
                ["rebuild_capcut.py", "--name", draft_name,
                 "--timeline", str(timeline),
                 "--images", str(job_path / "images"),
                 "--vo", str(job_path / "vo.mp3"),
                 "--sfx-dir", str(job_path / "sfx")],
            )
        with st.expander("Log CapCut", expanded=True):
            st.code(out[-4000:])
        if rc == 0:
            st.success("Draft ditulis. Buka CapCut dan klik proyeknya.")
        else:
            st.error("Gagal — lihat log.")

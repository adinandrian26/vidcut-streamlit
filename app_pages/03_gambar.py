import streamlit as st

from pipeline import jobs, shots

st.session_state.setdefault("job", "proyek_baru")
st.title("Gambar")
st.caption("Langkah 3 — prompt per kalimat, generate di tab Gemini yang terbuka.")

job_path = jobs.job_dir(st.session_state["job"])
img_dir = job_path / "images"
st.info(f"Job: `{st.session_state['job']}`")

naskah_file = job_path / "naskah.txt"
if not naskah_file.exists():
    st.warning("Belum ada naskah.")
    st.stop()

kalimat = shots.split_sentences(naskah_file.read_text(encoding="utf-8"))
st.caption(f"{len(kalimat)} kalimat = {len(kalimat)} gambar (1 per kalimat).")

if st.button("Buat shotlist + prompt gambar", icon=":material/image:", type="primary"):
    info = shots.build(job_path, kalimat)
    st.success(f"{info['kalimat']} prompt dibuat: shotlist.md, image_prompts.md, shots.json.")

shots_file = job_path / "shots.json"
if shots_file.exists():
    import json
    data = json.loads(shots_file.read_text(encoding="utf-8"))
    ada = {p.stem for p in img_dir.glob("*.png")}
    missing = [s["id"] for s in data if f"{s['id']:03d}" not in ada]
    with st.container(border=True):
        st.subheader("Kelengkapan gambar")
        st.metric("Sudah ada", f"{len(data) - len(missing)} / {len(data)}")
        if missing:
            st.warning(f"Belum ada: {missing[:20]}{'...' if len(missing) > 20 else ''}")
        else:
            st.success("Semua gambar lengkap.")
    with st.expander("Isi image_prompts.md (awal)"):
        st.code("\n".join((job_path / "image_prompts.md").read_text(
            encoding="utf-8").splitlines()[:30]))

    st.subheader("Tambah gambar manual")
    up = st.file_uploader("Upload PNG (nama 001.png, 002.png, ...)",
                          type=["png"], accept_multiple_files=True, key="img_upload")
    if up:
        for f in up:
            (img_dir / f.name).write_bytes(f.getvalue())
        st.success(f"{len(up)} file disimpan.")
        st.rerun()

with st.container(border=True):
    st.subheader("Generate otomatis (Chrome terbuka)")
    st.caption("Memakai tab Gemini di Chrome yang sedang terbuka (sudah login). "
               "Tidak membuka Chrome baru. Nama file terurut otomatis.")
    batch = st.number_input("Jumlah per klik", min_value=1, max_value=20,
                            value=3, step=1, key="batch_n")
    if st.button("Generate otomatis", icon=":material/auto_awesome:",
                 type="primary"):
        import json as _json
        import subprocess as _sp
        import sys as _sys
        shots_file = job_path / "shots.json"
        if not shots_file.exists():
            st.error("Buat shotlist + prompt dulu.")
        else:
            data = _json.loads(shots_file.read_text(encoding="utf-8"))
            ada = {p.stem for p in img_dir.glob("*.png")}
            hilang = [s["id"] for s in data if f"{s['id']:03d}" not in ada]
            if not hilang:
                st.info("Semua gambar sudah lengkap.")
            else:
                mulai = min(hilang)
                bar = st.progress(0, text="Menyiapkan...")
                box = st.empty()
                logs: list[str] = []

                def _run():
                    p = _sp.Popen(
                        [_sys.executable, "gen_gambar.py", "--job",
                         st.session_state["job"], "--mulai", str(mulai),
                         "--jumlah", str(int(batch))],
                        cwd=str(job_path.parent.parent),
                        stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True)
                    for line in p.stdout:
                        line = line.rstrip()
                        if line:
                            logs.append(line)
                            box.code("\n".join(logs[-12:]))
                            if "tersimpan" in line:
                                jadi = sum(1 for l in logs if "tersimpan" in l)
                                bar.progress(
                                    min(jadi / int(batch), 1.0),
                                    text=f"{jadi} gambar jadi...")
                    p.wait()
                    return p.returncode

                with st.spinner("Generate via Chrome terbuka — jangan tutup Chrome..."):
                    rc = _run()
                if rc != 0:
                    st.error("Tool berhenti dengan error — lihat log di atas.")
                sisa = [s["id"] for s in data
                        if f"{s['id']:03d}" not in
                        {p.stem for p in img_dir.glob("*.png")}]
                if sisa:
                    st.warning(f"Belum lengkap, sisa {len(sisa)}. Klik lagi untuk lanjut.")
                else:
                    st.success("Semua gambar lengkap.")
                st.rerun()

with st.container(border=True):
    st.subheader("Cek status login")

with st.container(border=True):
    st.subheader("Alur Gemini browser (laptop ini)")
    st.markdown(
        "1. Buka Chrome **Profile 3** ke `https://gemini.google.com/app?hl=id`.\n"
        "2. Kirim tiap prompt dari `image_prompts.md` satu per satu.\n"
        "3. Simpan hasil sebagai `images/001.png`, `002.png`, ... sesuai ID.\n"
        "4. Klik **Cek ulang** di bawah untuk perbarui status."
    )
    if st.button("Cek ulang", icon=":material/refresh:"):
        st.rerun()

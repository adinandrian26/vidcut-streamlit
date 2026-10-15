import streamlit as st

from pipeline import cerita, jobs, models, opencode_models

st.session_state.setdefault("job", "proyek_baru")
st.title("Naskah & model")
st.caption("Langkah 1 — pilih job, atur model, tulis naskah.")

cfg = models.load_presets()
names = [p["name"] for p in cfg["presets"]]

with st.container(border=True):
    st.subheader("Mau bikin cerita apa hari ini?")
    judul = st.text_input("Judul cerita", placeholder="mis. kenapa hanya homo sapiens yang tersisa",
                          key="new_job_name", label_visibility="collapsed")
    durasi = st.selectbox("Durasi cerita", list(cerita.DURASI.keys()),
                          index=1, key="durasi_cerita")
    if st.button("Bikin cerita", icon=":material/auto_stories:", type="primary"):
        if not judul.strip():
            st.error("Isi dulu mau bikin cerita apa.")
        else:
            mc = st.session_state.get("model_cfg", {})
            if mc.get("source") == "opencode" and mc.get("model"):
                tanya = cerita.tanya_via_opencode(
                    mc["model"], jobs.job_dir(jobs.slugify(judul)))
            elif mc.get("source", "endpoint") == "endpoint" and mc.get("model"):
                if not (mc.get("base_url") and mc.get("api_key")):
                    st.error("Lengkapi endpoint dan API key dulu, "
                             "atau pakai model Opencode.")
                    st.stop()
                tanya = cerita.tanya_via_endpoint(
                    mc["base_url"], mc["api_key"], mc["model"])
            else:
                st.error("Pilih model dulu di bagian Model.")
                st.stop()
            slug = jobs.slugify(judul)
            bar = st.progress(0, text="Mulai...")
            try:
                with st.spinner("Menulis cerita..."):
                    hasil = cerita.generate_cerita(
                        tanya, judul, durasi,
                        progress=lambda i, n, t: bar.progress(
                            i / n, text=t))
            except RuntimeError as e:
                st.error(str(e))
            else:
                st.session_state["job"] = slug
                (jobs.job_dir(slug) / "naskah.txt").write_text(
                    hasil, encoding="utf-8")
                st.session_state["naskah_text"] = hasil
                st.success(f"Cerita `{slug}` jadi — naskah terisi otomatis. "
                           f"{len(hasil.split())} kata.")
                st.rerun()

job_path = jobs.job_dir(st.session_state["job"])
st.info(f"Folder job: `{job_path}`")

st.session_state.setdefault("sumber_model", "KelontongAI")


def _apply_preset():
    cfg = models.load_presets()
    sel = next(p for p in cfg["presets"] if p["name"] == st.session_state["preset_select"])
    st.session_state["base_url"] = sel.get("base_url", "")
    st.session_state["model_name_text"] = sel.get("model", "")
    st.session_state.pop("synced_models", None)


with st.container(border=True):
    st.subheader("Model")
    sumber = st.segmented_control(
        "Sumber model", ["KelontongAI", "Opencode"], key="sumber_model")
    if sumber == "KelontongAI":
        preset = st.selectbox("Preset model", names, key="preset_select",
                              on_change=_apply_preset)
        sel = next(p for p in cfg["presets"] if p["name"] == preset)
        base_url = st.text_input("Endpoint (OpenAI-compatible base URL)",
                                 value=sel.get("base_url", ""), key="base_url")
        try:
            default_key = st.secrets.get("api_key", "")
        except Exception:
            default_key = ""
        api_key = st.text_input("API key", value="", type="password",
                                placeholder=default_key and "(terisi dari secrets)" or "tempel API key",
                                key="api_key")
        key = api_key or default_key
        if st.button("Tes koneksi & sinkron model", icon=":material/sync:"):
            if not base_url or not key:
                st.session_state.pop("synced_models", None)
                st.error("Isi endpoint dan API key dulu.")
            else:
                with st.spinner("Menghubungi endpoint..."):
                    try:
                        ids = models.list_models(base_url, key)
                    except RuntimeError as e:
                        st.session_state.pop("synced_models", None)
                        st.error(str(e))
                    else:
                        st.session_state["synced_models"] = ids
                        st.success(f"Terkoneksi — {len(ids)} model tersinkron otomatis.")
                        st.rerun()
        synced = st.session_state.get("synced_models", [])
        if synced:
            st.success(f"{len(synced)} model tersinkron dari endpoint.",
                       icon=":material/check_circle:")
            idx = synced.index(sel.get("model", "")) if sel.get("model", "") in synced else 0
            model_name = st.selectbox("Nama model (dari endpoint)", synced,
                                      index=idx, key="model_name_pick")
            if st.button("Ketik manual", icon=":material/edit:"):
                st.session_state.pop("synced_models", None)
                st.rerun()
        else:
            model_name = st.text_input("Nama model", value=sel.get("model", ""),
                                       key="model_name_text")
        st.session_state["model_cfg"] = {
            "source": "endpoint",
            "base_url": base_url,
            "api_key": key,
            "model": model_name,
            "synced": bool(synced),
        }
    else:
        st.caption("Model opencode laptop ini (KelontongAI + gratisan). "
                   "Jalan via CLI, tanpa API key tambahan.")
        oc_ids = st.session_state.get("synced_oc_models", [])
        if not oc_ids:
            st.session_state["model_cfg"] = {"source": "opencode", "model": ""}
            if st.button("Sinkron model opencode", icon=":material/sync:"):
                with st.spinner("Membaca config opencode..."):
                    ids = opencode_models.sync_opencode_models()
                if not ids:
                    st.error("Tidak ada model terbaca dari config opencode.")
                else:
                    st.session_state["synced_oc_models"] = ids
                    st.success(f"{len(ids)} model opencode tersinkron.")
                    st.rerun()
        else:
            oc_model = st.selectbox("Model opencode", oc_ids, key="oc_model_pick")
            st.session_state["model_cfg"] = {
                "source": "opencode",
                "model": oc_model,
            }
            st.success(f"Aktif: {oc_model} (via opencode CLI).",
                       icon=":material/check_circle:")

with st.container(border=True):
    st.subheader("Naskah")
    naskah_file = job_path / "naskah.txt"
    uploaded = st.file_uploader("Upload naskah (.txt)", type=["txt"], key="naskah_upload")
    if uploaded is not None:
        naskah_file.write_bytes(uploaded.getvalue())
    start_text = naskah_file.read_text(encoding="utf-8") if naskah_file.exists() else ""
    naskah = st.text_area("Isi naskah (Bahasa Indonesia)", value=start_text,
                          height=300, key="naskah_text")
    words = len(naskah.split())
    st.caption(f"{words} kata — estimasi ±{words / 140:.1f} menit VO.")
    if st.button("Simpan naskah", icon=":material/save:", type="primary"):
        naskah_file.write_text(naskah, encoding="utf-8")
        st.success(f"Tersimpan: {naskah_file}")

with st.container(border=True):
    st.subheader("Poles naskah dengan model (opsional)")
    _mc = st.session_state.get("model_cfg", {})
    if _mc.get("model"):
        st.caption(f"Aktif: `{_mc.get('model')}` "
                   f"({'opencode CLI' if _mc.get('source') == 'opencode' else 'endpoint API'}).")
    else:
        st.caption("Belum ada model aktif.")
    instruksi = st.text_input(
        "Instruksi poles",
        value="Rapikan naskah dokumenter ini tanpa mengubah fakta dan urutan. Kembalikan hanya naskah hasil poles.",
        key="polish_instr",
    )
    if st.button("Poles via model", icon=":material/auto_fix_high:"):
        mc = st.session_state.get("model_cfg", {})
        if not naskah.strip():
            st.error("Naskah masih kosong.")
        elif mc.get("source") == "opencode" and mc.get("model"):
            bar = st.progress(0, text="Memoles per bagian...")
            with st.spinner(f"Memoles via {mc['model']}..."):
                try:
                    hasil = opencode_models.polish_naskah(
                        mc["model"], instruksi, naskah,
                        jobs.job_dir(st.session_state["job"]),
                        progress=lambda i, n: bar.progress(
                            i / n, text=f"Bagian {i}/{n}..."),
                    )
                except RuntimeError as e:
                    st.error(str(e))
                else:
                    st.session_state["naskah_text"] = hasil
                    st.success("Hasil poles masuk ke kolom naskah — klik Simpan naskah.")
                    st.rerun()
        elif mc.get("source", "endpoint") == "endpoint" and mc.get("model"):
            if not (mc.get("base_url") and mc.get("api_key")):
                st.error("Lengkapi endpoint dan API key dulu, "
                         "atau sinkron model opencode.")
            else:
                with st.spinner("Memoles naskah..."):
                    try:
                        hasil = models.chat_completion(
                            mc["base_url"], mc["api_key"], mc["model"],
                            [{"role": "user",
                              "content": f"{instruksi}\n\nNASKAH:\n{naskah}"}],
                        )
                    except RuntimeError as e:
                        st.error(str(e))
                    else:
                        st.session_state["naskah_text"] = hasil
                        st.success("Hasil poles masuk ke kolom naskah — klik Simpan naskah.")
                        st.rerun()
        else:
            st.error("Pilih model dulu (sinkron endpoint atau opencode).")
